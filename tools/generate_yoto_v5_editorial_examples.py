from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
import sqlite3
import sys

import httpx
from PIL import Image, ImageDraw, ImageFont, ImageOps

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from application.editorial import select_editorial_phrase
from domain.entities.offer import Offer
from infrastructure.clients.base_http import ResilientHttpClient
from infrastructure.render.cards.renderer_selector import CardRendererRouter

OUTPUT_ROOT = REPO_ROOT / 'output' / 'cards' / 'editorial_examples_v51'
DB_PATH = REPO_ROOT / 'data' / 'dealbot.sqlite3'
DEFAULT_LIMIT = 6
TARGET_PHRASES = (
    'City builder',
    'Deckbuilder hit',
    'Co-op favorite',
    'Roguelike hit',
    'Factory builder',
    'Tower defense',
    'Strategy classic',
    'Metroidvania hit',
    'Racing hit',
    'Sports sim',
    'Colony sim',
    'Park builder',
    'Top rated indie',
    'Player favorite',
    'Critically loved',
    'Hidden indie gem',
    'Community favorite',
    'Steam bestseller',
    'Trending hit',
    'Fan favorite',
)


@dataclass(slots=True)
class ExampleCase:
    slug: str
    label: str
    offer: Offer
    template_id: str
    editorial_phrase: str
    origin: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Render YOTO V5.1 editorial examples.')
    parser.add_argument('--limit', type=int, default=DEFAULT_LIMIT, help='Maximum number of cards to render.')
    return parser.parse_args()


def _font(size: int) -> ImageFont.ImageFont:
    for name in ('arialbd.ttf', 'arial.ttf', 'DejaVuSans-Bold.ttf', 'DejaVuSans.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _slugify(value: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '_', value.lower()).strip('_')
    return slug or 'offer'


def _load_queue_items() -> list[tuple[Offer, str, str]]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute('SELECT offer_json, decision_json FROM queue_items ORDER BY score DESC').fetchall()
    items: list[tuple[Offer, str, str]] = []
    for row in rows:
        offer = Offer.from_snapshot(json.loads(row['offer_json']))
        decision = json.loads(row['decision_json'])
        items.append((offer, str(decision.get('template_id') or 'steam_discount'), 'queue'))
    return items


def _load_archived_offers(limit: int = 400) -> list[tuple[Offer, str, str]]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute('SELECT artifact_json FROM post_artifacts ORDER BY created_at DESC LIMIT ?', (limit,)).fetchall()
    items: list[tuple[Offer, str, str]] = []
    for row in rows:
        payload = json.loads(row['artifact_json'])
        render_inputs = payload.get('render_inputs') or {}
        offer_payload = render_inputs.get('offer') or {}
        decision_payload = render_inputs.get('decision') or {}
        if not offer_payload:
            continue
        offer = Offer.from_snapshot(offer_payload)
        template_id = str(decision_payload.get('template_id') or payload.get('template_id') or 'steam_discount')
        items.append((offer, template_id, 'archive'))
    return items


def build_cases(limit: int = DEFAULT_LIMIT) -> list[ExampleCase]:
    candidates = _load_queue_items() + _load_archived_offers()
    cases: list[ExampleCase] = []
    seen_offer_ids: set[str] = set()
    seen_phrases: set[str] = set()

    for target_phrase in TARGET_PHRASES:
        if len(cases) >= limit:
            break
        matching: list[tuple[Offer, str, str, str]] = []
        for offer, template_id, origin in candidates:
            if offer.offer_id in seen_offer_ids:
                continue
            phrase = select_editorial_phrase(offer)
            if phrase != target_phrase:
                continue
            matching.append((offer, template_id, origin, phrase))
        if not matching:
            continue
        offer, template_id, origin, phrase = max(
            matching,
            key=lambda item: (int(item[0].review_count or 0), int(item[0].review_score or 0), item[0].title),
        )
        seen_offer_ids.add(offer.offer_id)
        seen_phrases.add(phrase)
        cases.append(
            ExampleCase(
                slug=f"{phrase.lower().replace(' ', '_')}_{_slugify(offer.title)}",
                label=f'{phrase} / {offer.title}',
                offer=offer,
                template_id=template_id,
                editorial_phrase=phrase,
                origin=origin,
            )
        )

    if len(cases) >= limit:
        return cases[:limit]

    for offer, template_id, origin in candidates:
        if offer.offer_id in seen_offer_ids:
            continue
        phrase = select_editorial_phrase(offer)
        if phrase is None or phrase in seen_phrases:
            continue
        seen_offer_ids.add(offer.offer_id)
        seen_phrases.add(phrase)
        cases.append(
            ExampleCase(
                slug=f"{phrase.lower().replace(' ', '_')}_{_slugify(offer.title)}",
                label=f'{phrase} / {offer.title}',
                offer=offer,
                template_id=template_id,
                editorial_phrase=phrase,
                origin=origin,
            )
        )
        if len(cases) >= limit:
            break

    return cases[:limit]


def _contact_sheet(items: list[tuple[str, Path]], output_path: Path) -> None:
    if not items:
        return
    thumb_size = (360, 202)
    cols = 3
    rows = (len(items) + cols - 1) // cols
    cell_w = 400
    cell_h = 274
    sheet = Image.new('RGB', (cols * cell_w + 20, rows * cell_h + 20), '#091019')
    draw = ImageDraw.Draw(sheet)
    label_font = _font(18)
    small_font = _font(13)
    for index, (label, image_path) in enumerate(items):
        with Image.open(image_path) as image:
            thumb = ImageOps.fit(image.convert('RGB'), thumb_size)
        col = index % cols
        row = index // cols
        x = 20 + col * cell_w
        y = 20 + row * cell_h
        sheet.paste(thumb, (x, y))
        draw.text((x, y + 214), label, fill='white', font=label_font)
        draw.text((x, y + 238), image_path.name, fill='#8fa0b3', font=small_font)
    sheet.save(output_path)


def _prepare_output_root(output_root: Path) -> tuple[Path, Path, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    cards_dir = output_root / 'cards'
    cache_dir = output_root / 'asset_cache'
    for directory in (cards_dir, cache_dir):
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True, exist_ok=True)
    return cards_dir, cache_dir, output_root / 'editorial_manifest.json'


async def render_examples(limit: int = DEFAULT_LIMIT, *, output_root: Path = OUTPUT_ROOT) -> tuple[Path, list[dict[str, object]]]:
    cards_dir, cache_dir, manifest_path = _prepare_output_root(output_root)
    contact_sheet_path = output_root / 'contact_sheet.png'
    renderer = CardRendererRouter(cards_dir, renderer_mode='yoto_v4', fallback_to_legacy=True, cache_dir=cache_dir)
    cases = build_cases(limit=limit)
    results: list[dict[str, object]] = []
    contact_inputs: list[tuple[str, Path]] = []

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        http = ResilientHttpClient(client)
        for case in cases:
            result = await renderer.render(http, case.offer, case.template_id)
            snapshot = result.diagnostics.to_snapshot()
            contact_inputs.append((case.label, result.image_path))
            results.append(
                {
                    'offer_id': case.offer.offer_id,
                    'title': case.offer.title,
                    'origin': case.origin,
                    'template_id': case.template_id,
                    'editorial_phrase': snapshot.get('editorial_phrase'),
                    'hero_source_type': snapshot.get('hero_source_type'),
                    'hero_selection_reason': snapshot.get('hero_selection_reason'),
                    'fallback_used': snapshot.get('hero_fallback_used'),
                    'image_path': str(result.image_path),
                }
            )

    _contact_sheet(contact_inputs, contact_sheet_path)
    manifest = {
        'manifest_version': 'yoto_v5.1_editorial_examples',
        'created_at': datetime.utcnow().isoformat() + 'Z',
        'output_root': str(output_root),
        'cards_dir': str(cards_dir),
        'contact_sheet_path': str(contact_sheet_path),
        'case_count': len(results),
        'cases': results,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    return output_root, results


if __name__ == '__main__':
    args = parse_args()
    root, results = asyncio.run(render_examples(limit=args.limit))
    print(json.dumps({'output_root': str(root), 'case_count': len(results)}, ensure_ascii=False))
