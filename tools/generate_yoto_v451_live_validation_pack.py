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

from application.use_cases.offline_validation_snapshot import OfflineValidationSnapshotManager
from domain.entities.offer import Offer
from infrastructure.clients.base_http import ResilientHttpClient
from infrastructure.render.cards.renderer_selector import CardRendererRouter

OUTPUT_ROOT = REPO_ROOT / 'output' / 'cards'
LIVE_OUTPUT_ROOT = OUTPUT_ROOT / 'live_validation_v45'
DEFAULT_DB_PATH = REPO_ROOT / 'data' / 'dealbot.sqlite3'
DB_PATH = DEFAULT_DB_PATH
DEFAULT_LIMIT = 26
TARGET_EPIC_FREEBIES = 2


@dataclass(slots=True)
class ValidationCase:
    slug: str
    label: str
    offer: Offer
    template_id: str
    notes: list[str]
    origin: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run the production YOTO V4 live validation pack.')
    parser.add_argument('--limit', type=int, default=DEFAULT_LIMIT, help='Maximum number of offers to render.')
    parser.add_argument('--db-path', type=Path, default=None, help='Explicit SQLite database path to read queue state from.')
    parser.add_argument(
        '--offline-snapshot',
        nargs='?',
        const='latest',
        default=None,
        help='Read queue state from an offline validation snapshot. Omit the value to use the latest snapshot.',
    )
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


def _load_queue_items() -> list[tuple[Offer, str]]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute('SELECT offer_json, decision_json FROM queue_items ORDER BY score DESC').fetchall()
    items: list[tuple[Offer, str]] = []
    for row in rows:
        offer = Offer.from_snapshot(json.loads(row['offer_json']))
        decision = json.loads(row['decision_json'])
        items.append((offer, str(decision.get('template_id') or 'steam_discount')))
    return items


def _load_archived_epic_freebies(*, exclude_offer_ids: set[str], limit: int) -> list[tuple[Offer, str]]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT artifact_json FROM post_artifacts WHERE artifact_json LIKE '%\"source\": \"epic\"%' ORDER BY created_at DESC"
    ).fetchall()
    items: list[tuple[Offer, str]] = []
    seen_titles: set[str] = set()
    for row in rows:
        payload = json.loads(row['artifact_json'])
        render_inputs = payload.get('render_inputs') or {}
        offer_payload = render_inputs.get('offer') or {}
        decision_payload = render_inputs.get('decision') or {}
        if not offer_payload:
            continue
        offer = Offer.from_snapshot(offer_payload)
        if offer.offer_id in exclude_offer_ids or offer.offer_id in {existing.offer_id for existing, _ in items}:
            continue
        if offer.title in seen_titles or not offer.is_freebie:
            continue
        template_id = str(decision_payload.get('template_id') or payload.get('template_id') or 'epic_free')
        items.append((offer, template_id))
        seen_titles.add(offer.title)
        if len(items) >= limit:
            break
    return items


def _case_notes(offer: Offer, origin: str) -> list[str]:
    asset_urls = [asset for asset in (offer.assets.hero, offer.assets.header, offer.assets.screenshot, offer.assets.fallback) if asset]
    notes = [offer.offer_kind.value, origin]
    if offer.is_freebie:
        notes.append('freebie')
    if offer.is_event:
        notes.append('event')
    if len(offer.title) >= 32:
        notes.append('long_title')
    notes.append('has_screenshot' if offer.assets.screenshot else 'no_screenshot')
    if asset_urls and all('capsule' in asset.lower() for asset in asset_urls):
        notes.append('capsule_only_assets')
    elif any('capsule' in asset.lower() for asset in asset_urls):
        notes.append('capsule_mixed_assets')
    return notes


def build_cases(limit: int = DEFAULT_LIMIT) -> list[ValidationCase]:
    queue_items = _load_queue_items()
    queue_offer_ids = {offer.offer_id for offer, _ in queue_items}
    archived_epic = _load_archived_epic_freebies(exclude_offer_ids=queue_offer_ids, limit=TARGET_EPIC_FREEBIES)

    selected: list[ValidationCase] = []
    seen_offer_ids: set[str] = set()

    def add_case(offer: Offer, template_id: str, *, origin: str) -> None:
        if offer.offer_id in seen_offer_ids or len(selected) >= limit:
            return
        seen_offer_ids.add(offer.offer_id)
        selected.append(
            ValidationCase(
                slug=f'{offer.source.value}_{_slugify(offer.title)}',
                label=f'{offer.source.value.upper()} / {offer.title}',
                offer=offer,
                template_id=template_id,
                notes=_case_notes(offer, origin),
                origin=origin,
            )
        )

    for offer, template_id in queue_items:
        add_case(offer, template_id, origin='queue')
    for offer, template_id in archived_epic:
        add_case(offer, template_id, origin='archived_epic')
    return selected[:limit]


def _build_summary(cases: list[dict[str, object]]) -> dict[str, int]:
    summary = {
        'cards_rendered': len(cases),
        'screenshot_selected': 0,
        'store_header_selected': 0,
        'capsule_rejected': 0,
        'fallback_used': 0,
        'renderer_fallback_used': 0,
        'gameplay_candidates_evaluated': 0,
        'gameplay_ui_like_rejected': 0,
        'gameplay_frames_selected': 0,
    }
    for case in cases:
        hero_source_type = str(case.get('hero_source_type') or '')
        if hero_source_type == 'screenshot':
            summary['screenshot_selected'] += 1
        elif hero_source_type == 'header':
            summary['store_header_selected'] += 1
        if bool(case.get('capsule_rejected')):
            summary['capsule_rejected'] += 1
        if bool(case.get('fallback_used')):
            summary['fallback_used'] += 1
        if bool(case.get('renderer_fallback_used')):
            summary['renderer_fallback_used'] += 1
        summary['gameplay_candidates_evaluated'] += int(case.get('gameplay_candidates_count') or 0)
        summary['gameplay_ui_like_rejected'] += int(case.get('gameplay_rejected_ui_like') or 0)
        summary['gameplay_frames_selected'] += int(case.get('gameplay_selected_count') or 0)
    return summary


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
    return cards_dir, cache_dir, output_root / 'validation_manifest.json'


async def render_validation_pack(limit: int = DEFAULT_LIMIT, *, output_root: Path = LIVE_OUTPUT_ROOT) -> tuple[Path, dict[str, int]]:
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
                    'source': case.offer.source.value,
                    'offer_kind': case.offer.offer_kind.value,
                    'template_id': case.template_id,
                    'origin': case.origin,
                    'notes': case.notes,
                    'image_path': str(result.image_path),
                    'hero_source_type': snapshot.get('hero_source_type'),
                    'hero_selection_reason': snapshot.get('hero_selection_reason'),
                    'fallback_used': snapshot.get('hero_fallback_used'),
                    'capsule_rejected': snapshot.get('hero_capsule_rejected'),
                    'gameplay_candidates_count': snapshot.get('gameplay_candidates_count'),
                    'gameplay_selected_count': snapshot.get('gameplay_selected_count'),
                    'gameplay_selection_reason': snapshot.get('gameplay_selection_reason'),
                    'gameplay_rejected_ui_like': snapshot.get('gameplay_rejected_ui_like'),
                    'gameplay_score_summary': snapshot.get('gameplay_score_summary'),
                    'renderer_fallback_used': snapshot.get('renderer_fallback_used'),
                    'renderer_selected': snapshot.get('renderer_selected'),
                    'render_warnings': snapshot.get('render_warnings'),
                    'hero_selection': snapshot.get('hero_selection'),
                    'gameplay_selection': snapshot.get('gameplay_selection'),
                }
            )

    _contact_sheet(contact_inputs, contact_sheet_path)
    summary = _build_summary(results)
    manifest = {
        'manifest_version': 'yoto_v4.5_live_validation',
        'created_at': datetime.utcnow().isoformat() + 'Z',
        'output_root': str(output_root),
        'cards_dir': str(cards_dir),
        'contact_sheet_path': str(contact_sheet_path),
        'case_count': len(results),
        'selection_strategy': 'all current queue offers plus archived real Epic freebies when the live queue has none',
        'summary': summary,
        'cases': results,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    return output_root, summary


def resolve_db_path(args: argparse.Namespace) -> Path:
    if args.db_path is not None:
        return Path(args.db_path)
    if args.offline_snapshot is not None:
        manager = OfflineValidationSnapshotManager(REPO_ROOT / 'output' / 'offline_validation')
        return manager.resolve(args.offline_snapshot).base_db_path
    return DEFAULT_DB_PATH


def main() -> None:
    global DB_PATH

    args = parse_args()
    DB_PATH = resolve_db_path(args)
    root, summary = asyncio.run(render_validation_pack(limit=args.limit))
    print(json.dumps({'output_root': str(root), 'summary': summary}, ensure_ascii=False))


if __name__ == '__main__':
    main()

