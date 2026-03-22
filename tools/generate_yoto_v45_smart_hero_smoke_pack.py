from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys

import httpx
from PIL import Image, ImageDraw, ImageFont, ImageOps

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from domain.entities.offer import Offer
from infrastructure.clients.base_http import ResilientHttpClient
from infrastructure.render.cards.renderer_selector import CardRendererRouter

OUTPUT_ROOT = REPO_ROOT / 'output' / 'cards'
DB_PATH = REPO_ROOT / 'data' / 'dealbot.sqlite3'


@dataclass(slots=True)
class SmokeCase:
    slug: str
    label: str
    offer: Offer
    template_id: str
    notes: list[str]


def _font(size: int) -> ImageFont.ImageFont:
    for name in ('arialbd.ttf', 'arial.ttf', 'DejaVuSans-Bold.ttf', 'DejaVuSans.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _load_queue_offers() -> dict[str, tuple[Offer, str]]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT offer_json, decision_json FROM queue_items ORDER BY score DESC").fetchall()
    offers: dict[str, tuple[Offer, str]] = {}
    for row in rows:
        offer = Offer.from_snapshot(json.loads(row['offer_json']))
        decision = json.loads(row['decision_json'])
        offers[offer.title] = (offer, str(decision.get('template_id') or 'steam_discount'))
    return offers


def build_cases() -> list[SmokeCase]:
    queue_offers = _load_queue_offers()
    dead_cells, dead_cells_template = queue_offers['Dead Cells']
    deponia, deponia_template = queue_offers['Deponia']
    hoi4, hoi4_template = queue_offers['Hearts of Iron IV']
    return [
        SmokeCase(
            slug='v451_dead_cells_discount',
            label='V4.5.1 / Dead Cells Discount',
            offer=dead_cells,
            template_id=dead_cells_template,
            notes=['discount', 'smart hero selection', 'live assets'],
        ),
        SmokeCase(
            slug='v451_deponia_freebie',
            label='V4.5.1 / Deponia Freebie',
            offer=deponia,
            template_id=deponia_template,
            notes=['freebie', 'capsule-like case', 'smart rejection'],
        ),
        SmokeCase(
            slug='v451_hearts_of_iron_iv_discount',
            label='V4.5.1 / Hearts of Iron IV',
            offer=hoi4,
            template_id=hoi4_template,
            notes=['discount', 'weak-header case', 'screenshot should win'],
        ),
    ]


def _build_summary(cases: list[dict[str, object]]) -> dict[str, int]:
    summary = {
        'total_cards_rendered': len(cases),
        'screenshot_heroes_selected': 0,
        'store_heroes_selected': 0,
        'capsule_rejected': 0,
        'fallback_used': 0,
        'gameplay_candidates_evaluated': 0,
        'gameplay_ui_like_rejected': 0,
        'gameplay_frames_selected': 0,
    }
    for case in cases:
        hero_source = str(case.get('hero_source') or '')
        if hero_source == 'screenshot':
            summary['screenshot_heroes_selected'] += 1
        elif hero_source in {'hero', 'header', 'fallback'}:
            summary['store_heroes_selected'] += 1
        if bool(case.get('capsule_rejected')):
            summary['capsule_rejected'] += 1
        if bool(case.get('fallback_used')):
            summary['fallback_used'] += 1
        summary['gameplay_candidates_evaluated'] += int(case.get('gameplay_candidates_count') or 0)
        summary['gameplay_ui_like_rejected'] += int(case.get('gameplay_rejected_ui_like') or 0)
        summary['gameplay_frames_selected'] += int(case.get('gameplay_selected_count') or 0)
    return summary


def _contact_sheet(items: list[tuple[str, Path]], output_path: Path) -> None:
    thumb_size = (420, 236)
    rows = len(items)
    sheet = Image.new('RGB', (470, rows * 306 + 20), '#091019')
    draw = ImageDraw.Draw(sheet)
    label_font = _font(22)
    small_font = _font(14)
    for index, (label, image_path) in enumerate(items):
        with Image.open(image_path) as image:
            thumb = ImageOps.fit(image.convert('RGB'), thumb_size)
        x = 24
        y = 20 + index * 306
        sheet.paste(thumb, (x, y))
        draw.text((x, y + 246), label, fill='white', font=label_font)
        draw.text((x, y + 274), image_path.name, fill='#8fa0b3', font=small_font)
    sheet.save(output_path)


async def render_smoke_pack() -> Path:
    run_key = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    preview_root = OUTPUT_ROOT / f'smoke_yoto_v451_{run_key}'
    cards_dir = preview_root / 'cards'
    cache_dir = preview_root / 'asset_cache'
    manifest_path = preview_root / 'smoke_manifest.json'
    contact_sheet_path = preview_root / 'smoke_contact_sheet.png'
    for directory in (cards_dir, cache_dir):
        directory.mkdir(parents=True, exist_ok=True)

    renderer = CardRendererRouter(cards_dir, renderer_mode='yoto_v4', fallback_to_legacy=False, cache_dir=cache_dir)
    cases = build_cases()
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
                    'slug': case.slug,
                    'label': case.label,
                    'notes': case.notes,
                    'template_id': case.template_id,
                    'offer_id': case.offer.offer_id,
                    'title': case.offer.title,
                    'image_path': str(result.image_path),
                    'hero_source': snapshot.get('hero_source_type'),
                    'hero_reason': snapshot.get('hero_selection_reason'),
                    'hero_candidates_count': snapshot.get('hero_candidates_count'),
                    'capsule_rejected': snapshot.get('hero_capsule_rejected'),
                    'fallback_used': snapshot.get('hero_fallback_used'),
                    'gameplay_candidates_count': snapshot.get('gameplay_candidates_count'),
                    'gameplay_selected_count': snapshot.get('gameplay_selected_count'),
                    'gameplay_selection_reason': snapshot.get('gameplay_selection_reason'),
                    'gameplay_rejected_ui_like': snapshot.get('gameplay_rejected_ui_like'),
                    'gameplay_selection': snapshot.get('gameplay_selection'),
                    'hero_selection': snapshot.get('hero_selection'),
                    'diagnostics': snapshot,
                }
            )

    _contact_sheet(contact_inputs, contact_sheet_path)
    manifest = {
        'manifest_version': 'yoto_v4.5.1',
        'created_at': datetime.utcnow().isoformat() + 'Z',
        'preview_root': str(preview_root),
        'cards_dir': str(cards_dir),
        'contact_sheet_path': str(contact_sheet_path),
        'case_count': len(results),
        'summary': _build_summary(results),
        'cases': results,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    return preview_root


if __name__ == '__main__':
    root = asyncio.run(render_smoke_pack())
    print(root)
