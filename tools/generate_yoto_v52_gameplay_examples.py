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

from domain.entities.offer import Offer
from infrastructure.clients.base_http import ResilientHttpClient
from infrastructure.render.cards.renderer_selector import CardRendererRouter

OUTPUT_ROOT = REPO_ROOT / 'output' / 'cards' / 'gameplay_selection_examples_v1'
DB_PATH = REPO_ROOT / 'data' / 'dealbot.sqlite3'
DEFAULT_SCAN_LIMIT = 16
CATEGORY_ORDER = ('action_heavy', 'strategy_builder', 'later_better')
CATEGORY_LABELS = {
    'action_heavy': 'Action-heavy',
    'strategy_builder': 'Strategy / Builder',
    'later_better': 'Weak early -> better later',
}
ACTION_TITLE_HINTS = (
    'black desert',
    'the crew motorfest',
    'deep rock galactic',
    'dead space',
    'world war z',
    'far cry',
)
STRATEGY_TITLE_HINTS = (
    'cities: skylines',
    'hearts of iron iv',
    'satisfactory',
    'bloons td 6',
    'age of wonders 4',
    'kingdom rush 5',
)


@dataclass(slots=True)
class QueueCase:
    offer: Offer
    template_id: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Render Smart Gameplay Selection example cards.')
    parser.add_argument('--scan-limit', type=int, default=DEFAULT_SCAN_LIMIT, help='Maximum number of queue offers to scan.')
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


def _load_queue_items(limit: int) -> list[QueueCase]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute('SELECT offer_json, decision_json FROM queue_items ORDER BY score DESC LIMIT ?', (limit,)).fetchall()
    items: list[QueueCase] = []
    for row in rows:
        offer = Offer.from_snapshot(json.loads(row['offer_json']))
        decision = json.loads(row['decision_json'])
        items.append(QueueCase(offer=offer, template_id=str(decision.get('template_id') or 'steam_discount')))
    return items


def _terms(offer: Offer) -> set[str]:
    values = [offer.title, *offer.tags, *offer.genres]
    terms: set[str] = set()
    for value in values:
        normalized = str(value or '').strip().lower()
        if normalized:
            terms.add(normalized)
    return terms


def _is_action_heavy(offer: Offer) -> bool:
    title = offer.title.lower()
    terms = _terms(offer)
    return any(token in title for token in ACTION_TITLE_HINTS) or any(token in terms for token in {'action', 'shooter', 'co-op', 'racing'})


def _is_strategy_builder(offer: Offer) -> bool:
    title = offer.title.lower()
    terms = _terms(offer)
    return any(token in title for token in STRATEGY_TITLE_HINTS) or any(token in terms for token in {'strategy', 'simulation', 'builder', 'tower_defense'})


def _is_later_better(snapshot: dict[str, object]) -> bool:
    selection = snapshot.get('gameplay_selection') or {}
    if not isinstance(selection, dict):
        return False
    selected_urls = set(str(item) for item in selection.get('selected_urls', []) if item)
    summary = snapshot.get('gameplay_score_summary') or []
    if not isinstance(summary, list) or not selected_urls:
        return False
    selected_indices = [int(item.get('index') or 0) for item in summary if isinstance(item, dict) and item.get('asset_url') in selected_urls]
    if not selected_indices:
        return False
    earliest_selected = min(selected_indices)
    for item in summary:
        if not isinstance(item, dict):
            continue
        if int(item.get('index') or 0) >= earliest_selected:
            continue
        if str(item.get('rejection_reason') or '') in {'ui_like_frame', 'low_information_frame', 'logo_or_title_frame'}:
            return True
    return False


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
    return cards_dir, cache_dir, output_root / 'gameplay_manifest.json'


def _build_summary(cases: list[dict[str, object]]) -> dict[str, int]:
    return {
        'cards_rendered': len(cases),
        'gameplay_candidates_evaluated': sum(int(case.get('gameplay_candidates_count') or 0) for case in cases),
        'gameplay_ui_like_rejected': sum(int(case.get('gameplay_rejected_ui_like') or 0) for case in cases),
        'gameplay_frames_selected': sum(int(case.get('gameplay_selected_count') or 0) for case in cases),
    }


async def render_examples(scan_limit: int = DEFAULT_SCAN_LIMIT, *, output_root: Path = OUTPUT_ROOT) -> tuple[Path, dict[str, int], list[dict[str, object]]]:
    cards_dir, cache_dir, manifest_path = _prepare_output_root(output_root)
    contact_sheet_path = output_root / 'contact_sheet.png'
    renderer = CardRendererRouter(cards_dir, renderer_mode='yoto_v4', fallback_to_legacy=True, cache_dir=cache_dir)
    queue_items = _load_queue_items(scan_limit)
    selected_by_category: dict[str, dict[str, object]] = {}
    rendered_cases: list[dict[str, object]] = []

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        http = ResilientHttpClient(client)
        for item in queue_items:
            result = await renderer.render(http, item.offer, item.template_id)
            snapshot = result.diagnostics.to_snapshot()
            case = {
                'offer_id': item.offer.offer_id,
                'title': item.offer.title,
                'slug': _slugify(item.offer.title),
                'template_id': item.template_id,
                'image_path': str(result.image_path),
                'hero_source_type': snapshot.get('hero_source_type'),
                'hero_selection_reason': snapshot.get('hero_selection_reason'),
                'fallback_used': snapshot.get('hero_fallback_used'),
                'gameplay_candidates_count': snapshot.get('gameplay_candidates_count'),
                'gameplay_selected_count': snapshot.get('gameplay_selected_count'),
                'gameplay_selection_reason': snapshot.get('gameplay_selection_reason'),
                'gameplay_rejected_ui_like': snapshot.get('gameplay_rejected_ui_like'),
                'gameplay_selection': snapshot.get('gameplay_selection'),
                'gameplay_score_summary': snapshot.get('gameplay_score_summary'),
            }
            rendered_cases.append(case)

            if 'action_heavy' not in selected_by_category and _is_action_heavy(item.offer) and int(snapshot.get('gameplay_selected_count') or 0) >= 2:
                selected_by_category['action_heavy'] = case
            if 'strategy_builder' not in selected_by_category and _is_strategy_builder(item.offer) and int(snapshot.get('gameplay_selected_count') or 0) >= 2:
                selected_by_category['strategy_builder'] = case
            if 'later_better' not in selected_by_category and _is_later_better(snapshot):
                selected_by_category['later_better'] = case
            if len(selected_by_category) == len(CATEGORY_ORDER):
                break

    selected_cases: list[dict[str, object]] = []
    seen_offer_ids: set[str] = set()
    for category in CATEGORY_ORDER:
        case = selected_by_category.get(category)
        if not case or str(case['offer_id']) in seen_offer_ids:
            continue
        enriched = dict(case)
        enriched['category'] = category
        enriched['category_label'] = CATEGORY_LABELS[category]
        selected_cases.append(enriched)
        seen_offer_ids.add(str(case['offer_id']))

    if len(selected_cases) < 3:
        for case in rendered_cases:
            if str(case['offer_id']) in seen_offer_ids:
                continue
            fallback_case = dict(case)
            fallback_case['category'] = f'additional_{len(selected_cases) + 1}'
            fallback_case['category_label'] = 'Additional case'
            selected_cases.append(fallback_case)
            seen_offer_ids.add(str(case['offer_id']))
            if len(selected_cases) >= 3:
                break

    contact_inputs = [
        (f"{case['category_label']} / {case['title']}", Path(str(case['image_path'])))
        for case in selected_cases
    ]
    _contact_sheet(contact_inputs, contact_sheet_path)
    summary = _build_summary(selected_cases)
    manifest = {
        'manifest_version': 'yoto_v5.2_gameplay_examples',
        'created_at': datetime.utcnow().isoformat() + 'Z',
        'output_root': str(output_root),
        'cards_dir': str(cards_dir),
        'contact_sheet_path': str(contact_sheet_path),
        'scan_limit': scan_limit,
        'selected_case_count': len(selected_cases),
        'summary': summary,
        'cases': selected_cases,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    return output_root, summary, selected_cases


if __name__ == '__main__':
    args = parse_args()
    root, summary, cases = asyncio.run(render_examples(scan_limit=args.scan_limit))
    print(json.dumps({'output_root': str(root), 'summary': summary, 'case_count': len(cases)}, ensure_ascii=False))
