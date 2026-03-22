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
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageStat

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from application.use_cases.offline_validation_snapshot import OfflineValidationSnapshotManager
from domain.entities.offer import Offer
from infrastructure.clients.base_http import ResilientHttpClient
from infrastructure.render.cards.renderer_selector import CardRendererRouter

DEFAULT_DB_PATH = REPO_ROOT / 'data' / 'dealbot.sqlite3'
OUTPUT_ROOT = REPO_ROOT / 'output' / 'cards'
REVIEW_PREFIX = 'discount_family_review_'
REQUIRED_CASES = (
    'high_discount',
    'medium_discount',
    'bright_art',
    'dark_art',
    'logo_heavy_art',
    'weaker_asset_case',
    'short_title',
    'long_title',
)


@dataclass(slots=True)
class CandidateCase:
    offer: Offer
    template_id: str
    bucket: str
    lane: str
    score: float


@dataclass(slots=True)
class RenderedCase:
    offer: Offer
    template_id: str
    bucket: str
    lane: str
    score: float
    image_path: Path
    diagnostics: dict[str, object]
    hero_luminance: float
    title_length: int
    hero_score: float
    text_coverage_ratio: float
    logo_heavy: bool
    weaker_asset_score: float



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Generate a multi-case YOTO discount-family composition review pack.')
    parser.add_argument('--db-path', type=Path, default=None, help='Explicit SQLite database path to read queue state from.')
    parser.add_argument(
        '--offline-snapshot',
        nargs='?',
        const='golden',
        default='golden',
        help='Read queue state from an offline validation snapshot. Defaults to the golden snapshot.',
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



def _selected_score_item(score_summary: object) -> dict[str, object] | None:
    if not isinstance(score_summary, list):
        return None
    for item in score_summary:
        if isinstance(item, dict) and item.get('selected'):
            return dict(item)
    if score_summary and isinstance(score_summary[0], dict):
        return dict(score_summary[0])
    return None



def _logo_heavy(score_item: dict[str, object] | None) -> bool:
    if not score_item:
        return False
    text_coverage_ratio = float(score_item.get('text_coverage_ratio') or 0.0)
    if text_coverage_ratio >= 0.40:
        return True
    if text_coverage_ratio >= 0.32 and bool(score_item.get('horizontal_text_block')):
        return True
    return bool(score_item.get('promotional_layout'))



def _load_discount_candidates(db_path: Path) -> list[CandidateCase]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = con.execute('SELECT offer_json, decision_json, bucket, lane, score FROM queue_items ORDER BY score DESC').fetchall()
    cases: list[CandidateCase] = []
    for row in rows:
        offer = Offer.from_snapshot(json.loads(row['offer_json']))
        decision = json.loads(row['decision_json'])
        template_id = str(decision.get('template_id') or 'steam_discount')
        if template_id != 'steam_discount' and not (offer.source.value == 'steam' and offer.offer_kind.value == 'discount'):
            continue
        cases.append(
            CandidateCase(
                offer=offer,
                template_id=template_id,
                bucket=str(row['bucket'] or ''),
                lane=str(row['lane'] or ''),
                score=float(row['score'] or 0.0),
            )
        )
    return cases



def _prepare_output_root(output_root: Path) -> tuple[Path, Path, Path, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    cards_dir = output_root / 'cards'
    cache_dir = output_root / 'asset_cache'
    manifest_path = output_root / 'review_manifest.json'
    contact_sheet_path = output_root / 'contact_sheet.png'
    for directory in (cards_dir, cache_dir):
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True, exist_ok=True)
    return cards_dir, cache_dir, manifest_path, contact_sheet_path



def _hero_luminance(image_path: Path) -> float:
    with Image.open(image_path) as image:
        hero = image.convert('L').crop((0, 0, image.width, 468))
        return round(float(ImageStat.Stat(hero).mean[0]) / 255.0, 4)



def _contact_sheet(items: list[tuple[str, Path]], output_path: Path) -> None:
    if not items:
        return
    thumb_size = (360, 202)
    cols = 4
    rows = (len(items) + cols - 1) // cols
    cell_w = 400
    cell_h = 278
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
        draw.text((x, y + 240), image_path.name, fill='#8fa0b3', font=small_font)
    sheet.save(output_path)



def _pick_category_cases(cases: list[RenderedCase]) -> dict[str, RenderedCase]:
    def pick(name: str, ordered: list[RenderedCase], *, allow_selected: bool = False, selected_ids: set[str]) -> RenderedCase:
        for case in ordered:
            if allow_selected or case.offer.offer_id not in selected_ids:
                return case
        return ordered[0]

    selected_ids: set[str] = set()
    category_map: dict[str, RenderedCase] = {}

    high_discount_order = sorted(cases, key=lambda case: (case.offer.discount_percent, case.score), reverse=True)
    category_map['high_discount'] = pick('high_discount', high_discount_order, selected_ids=selected_ids)
    selected_ids.add(category_map['high_discount'].offer.offer_id)

    medium_discount_candidates = [case for case in cases if 35 <= case.offer.discount_percent <= 65]
    if not medium_discount_candidates:
        medium_discount_candidates = list(cases)
    medium_discount_order = sorted(medium_discount_candidates, key=lambda case: (abs(case.offer.discount_percent - 50), -case.score))
    category_map['medium_discount'] = pick('medium_discount', medium_discount_order, selected_ids=selected_ids)
    selected_ids.add(category_map['medium_discount'].offer.offer_id)

    bright_order = sorted(cases, key=lambda case: (case.hero_luminance, case.score), reverse=True)
    category_map['bright_art'] = pick('bright_art', bright_order, selected_ids=selected_ids)
    selected_ids.add(category_map['bright_art'].offer.offer_id)

    dark_order = sorted(cases, key=lambda case: (case.hero_luminance, -case.score))
    category_map['dark_art'] = pick('dark_art', dark_order, selected_ids=selected_ids)
    selected_ids.add(category_map['dark_art'].offer.offer_id)

    logo_candidates = [case for case in cases if case.logo_heavy]
    if not logo_candidates:
        logo_candidates = sorted(cases, key=lambda case: (case.text_coverage_ratio, case.score), reverse=True)
    logo_order = sorted(logo_candidates, key=lambda case: (case.text_coverage_ratio, case.score), reverse=True)
    category_map['logo_heavy_art'] = pick('logo_heavy_art', logo_order, selected_ids=selected_ids)
    selected_ids.add(category_map['logo_heavy_art'].offer.offer_id)

    weaker_order = sorted(cases, key=lambda case: (case.weaker_asset_score, case.hero_score, case.hero_luminance))
    category_map['weaker_asset_case'] = pick('weaker_asset_case', weaker_order, selected_ids=selected_ids)
    selected_ids.add(category_map['weaker_asset_case'].offer.offer_id)

    short_order = sorted(cases, key=lambda case: (case.title_length, -case.score))
    category_map['short_title'] = pick('short_title', short_order, selected_ids=selected_ids)
    selected_ids.add(category_map['short_title'].offer.offer_id)

    long_order = sorted(cases, key=lambda case: (case.title_length, case.score), reverse=True)
    category_map['long_title'] = pick('long_title', long_order, selected_ids=selected_ids)
    return category_map



def _resolve_db_path(args: argparse.Namespace) -> Path:
    if args.db_path is not None:
        return Path(args.db_path)
    if args.offline_snapshot is not None:
        manager = OfflineValidationSnapshotManager(REPO_ROOT / 'output' / 'offline_validation')
        return manager.resolve(args.offline_snapshot).base_db_path
    return DEFAULT_DB_PATH


async def render_review_pack(db_path: Path) -> tuple[Path, dict[str, object]]:
    timestamp = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    output_root = OUTPUT_ROOT / f'{REVIEW_PREFIX}{timestamp}'
    cards_dir, cache_dir, manifest_path, contact_sheet_path = _prepare_output_root(output_root)
    candidates = _load_discount_candidates(db_path)
    renderer = CardRendererRouter(cards_dir, renderer_mode='yoto_v4', fallback_to_legacy=True, cache_dir=cache_dir)
    rendered_cases: list[RenderedCase] = []

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        http = ResilientHttpClient(client)
        for candidate in candidates:
            result = await renderer.render(http, candidate.offer, candidate.template_id)
            snapshot = result.diagnostics.to_snapshot()
            selected_item = _selected_score_item(snapshot.get('hero_score_summary'))
            hero_score = float((selected_item or {}).get('score') or 0.0)
            text_coverage_ratio = float((selected_item or {}).get('text_coverage_ratio') or 0.0)
            fallback_used = bool(snapshot.get('hero_fallback_used')) or bool(snapshot.get('render_warnings'))
            rendered_cases.append(
                RenderedCase(
                    offer=candidate.offer,
                    template_id=candidate.template_id,
                    bucket=candidate.bucket,
                    lane=candidate.lane,
                    score=candidate.score,
                    image_path=result.image_path,
                    diagnostics=snapshot,
                    hero_luminance=_hero_luminance(result.image_path),
                    title_length=len(candidate.offer.title),
                    hero_score=hero_score,
                    text_coverage_ratio=text_coverage_ratio,
                    logo_heavy=_logo_heavy(selected_item),
                    weaker_asset_score=(0.0 if fallback_used else 100.0) + hero_score,
                )
            )

    category_map = _pick_category_cases(rendered_cases)
    review_by_offer_id: dict[str, dict[str, object]] = {}
    for category, case in category_map.items():
        entry = review_by_offer_id.setdefault(
            case.offer.offer_id,
            {
                'offer_id': case.offer.offer_id,
                'title': case.offer.title,
                'template_id': case.template_id,
                'bucket': case.bucket,
                'lane': case.lane,
                'score': round(case.score, 2),
                'source': case.offer.source.value,
                'discount_percent': case.offer.discount_percent,
                'price_before_minor': case.offer.price_before_minor,
                'price_after_minor': case.offer.price_after_minor,
                'image_path': str(case.image_path),
                'hero_luminance': case.hero_luminance,
                'title_length': case.title_length,
                'hero_score': round(case.hero_score, 2),
                'text_coverage_ratio': round(case.text_coverage_ratio, 3),
                'logo_heavy': case.logo_heavy,
                'diagnostics': case.diagnostics,
                'review_categories': [],
            },
        )
        entry['review_categories'].append(category)

    review_cases = sorted(
        review_by_offer_id.values(),
        key=lambda case: min(REQUIRED_CASES.index(category) for category in case['review_categories']),
    )

    contact_inputs = []
    for case in review_cases:
        categories = ', '.join(case['review_categories'])
        contact_inputs.append((f"{case['title']} [{categories}]", Path(case['image_path'])))
    _contact_sheet(contact_inputs, contact_sheet_path)

    summary = {
        'rendered_discount_cards': len(rendered_cases),
        'review_case_count': len(review_cases),
        'logo_heavy_cases': sum(1 for case in rendered_cases if case.logo_heavy),
        'fallback_or_warning_cases': sum(1 for case in rendered_cases if bool(case.diagnostics.get('render_warnings')) or bool(case.diagnostics.get('hero_fallback_used'))),
        'brightest_hero_luminance': max(case.hero_luminance for case in rendered_cases) if rendered_cases else 0.0,
        'darkest_hero_luminance': min(case.hero_luminance for case in rendered_cases) if rendered_cases else 0.0,
    }
    manifest = {
        'manifest_version': 'yoto_discount_family_review_v1',
        'created_at': datetime.utcnow().isoformat() + 'Z',
        'db_path': str(db_path),
        'output_root': str(output_root),
        'cards_dir': str(cards_dir),
        'contact_sheet_path': str(contact_sheet_path),
        'required_categories': list(REQUIRED_CASES),
        'summary': summary,
        'review_cases': review_cases,
        'all_cases': [
            {
                'offer_id': case.offer.offer_id,
                'title': case.offer.title,
                'template_id': case.template_id,
                'bucket': case.bucket,
                'lane': case.lane,
                'score': round(case.score, 2),
                'source': case.offer.source.value,
                'discount_percent': case.offer.discount_percent,
                'image_path': str(case.image_path),
                'hero_luminance': case.hero_luminance,
                'title_length': case.title_length,
                'hero_score': round(case.hero_score, 2),
                'text_coverage_ratio': round(case.text_coverage_ratio, 3),
                'logo_heavy': case.logo_heavy,
                'render_warnings': case.diagnostics.get('render_warnings'),
                'hero_source_type': case.diagnostics.get('hero_source_type'),
                'hero_selection_reason': case.diagnostics.get('hero_selection_reason'),
                'top_zone_layout_mode': (case.diagnostics.get('text_payload') or {}).get('top_zone_layout_mode'),
                'composition_mode': (case.diagnostics.get('text_payload') or {}).get('composition_mode'),
                'meta_alignment': case.diagnostics.get('meta_alignment'),
            }
            for case in rendered_cases
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    return output_root, summary



def main() -> None:
    args = parse_args()
    db_path = _resolve_db_path(args)
    output_root, summary = asyncio.run(render_review_pack(db_path))
    print(json.dumps({'output_root': str(output_root), 'summary': summary}, ensure_ascii=False))


if __name__ == '__main__':
    main()
