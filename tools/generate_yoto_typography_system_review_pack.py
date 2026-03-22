from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import shutil
import sys
from types import ModuleType
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from infrastructure.render.cards.yoto_card_engine_v4 import YotoCardData as CurrentYotoCardData
from infrastructure.render.cards.yoto_card_engine_v4 import YotoCardEngineV4 as CurrentYotoCardEngineV4
from infrastructure.render.cards.yoto_card_engine_v4 import YotoCardType as CurrentYotoCardType


OUTPUT_ROOT = REPO_ROOT / 'output' / 'cards'
REVIEW_PREFIX = 'premium_finish_review_'
CACHE_DIR = REPO_ROOT / 'video_generator' / 'assets' / 'cache'
SOURCE_DIR = OUTPUT_ROOT / 'v41_acceptance_sources'
ROUNDUP_SNAPSHOT_GLOB = '*_roundup_snapshot_roundups.json'

CACHE_FILES = {
    'turnip_boy': CACHE_DIR / '8e1d77c0450dd201fecb8df9dc7603bbfc06b5966968d6a2573e7d8c8d48af74.png',
    'slay_the_spire': CACHE_DIR / 'a8af2ae28d36505e900953dd197ad6f0308f35db8e0b5bbd54c8a39933057a6b.jpg',
    'motorfest': CACHE_DIR / 'a067029839678e5361029c007e107bdc89bad8e72cb0ad22cc09f375d5b8113e.jpg',
    'black_desert': CACHE_DIR / '3a53525a75a796d027b222d66422dc3ae56e9d670166e09579220596f4f5cc9a.jpg',
}

MONTH_DEADLINE = '\u0437\u0430\u0431\u0440\u0430\u0442\u0438 \u0434\u043e 12 \u0431\u0435\u0440\u0435\u0437\u043d\u044f, 18:00'
EVENT_DEADLINE = '\u0434\u043e 18 \u0431\u0435\u0440\u0435\u0437\u043d\u044f, 20:00'


@dataclass(slots=True)
class ReviewCase:
    slug: str
    label: str
    family: str
    traits: list[str]
    payload: object
    before_path: Path | None


@dataclass(slots=True)
class RenderedCase:
    case: ReviewCase
    image_path: Path
    diagnostics: dict[str, object]
    before_exists: bool
    comparison_path: Path | None
    before_path: Path | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Render the premium YOTO multi-family finish review pack.')
    parser.add_argument('--before-root', type=Path, default=None, help='Optional previous review-pack root used for before/after comparisons.')
    parser.add_argument('--engine-path', type=Path, default=None, help='Optional engine file path for rendering baseline packs from an alternate renderer file.')
    return parser.parse_args()


def _json_ready(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    return value


def _font(size: int, *, bold: bool = True) -> ImageFont.ImageFont:
    candidates = ('segoeuib.ttf', 'arialbd.ttf', 'DejaVuSans-Bold.ttf') if bold else ('segoeui.ttf', 'arial.ttf', 'DejaVuSans.ttf')
    font_dir = REPO_ROOT / 'video_generator' / 'assets' / 'fonts'
    for name in candidates:
        try:
            path = font_dir / name
            if path.exists():
                return ImageFont.truetype(str(path), size)
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _load_engine_module(engine_path: Path | None) -> tuple[type, type, type, str]:
    if engine_path is None:
        return CurrentYotoCardData, CurrentYotoCardEngineV4, CurrentYotoCardType, 'current'
    resolved = engine_path.resolve()
    spec = importlib.util.spec_from_file_location('yoto_card_engine_override', resolved)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Could not load engine module from {resolved}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module.YotoCardData, module.YotoCardEngineV4, module.YotoCardType, str(resolved)


def build_sparse_header_source(path: Path) -> None:
    image = Image.new('RGB', (1600, 900), '#07131c')
    draw = ImageDraw.Draw(image)
    for y in range(900):
        ratio = y / 899
        color = (
            int(7 + (14 - 7) * ratio),
            int(19 + (40 - 19) * ratio),
            int(28 + (58 - 28) * ratio),
        )
        draw.line((0, y, 1600, y), fill=color)
    draw.rounded_rectangle((140, 120, 1450, 480), radius=64, outline='#2aef99', width=6)
    draw.rounded_rectangle((170, 146, 620, 244), radius=28, fill='#2aef99')
    draw.text((250, 170), 'LIVE SIGNAL', fill='#07120d', font=_font(46))
    draw.text((168, 280), 'STEAM NEXT FEST', fill='white', font=_font(120))
    draw.text((176, 442), 'official blog header / logo-heavy source', fill='#b8d3e8', font=_font(36, bold=False))
    draw.line((160, 590, 1440, 590), fill='#2aef99', width=10)
    draw.text((178, 630), 'This source intentionally stresses sparse header-only artwork.', fill='#dbe9f4', font=_font(32, bold=False))
    image.save(path)


def _prepare_output_root(output_root: Path) -> tuple[Path, Path, Path, Path, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    cards_dir = output_root / 'cards'
    pairs_dir = output_root / 'pairs'
    manifest_path = output_root / 'review_manifest.json'
    after_sheet_path = output_root / 'after_contact_sheet.png'
    comparison_sheet_path = output_root / 'comparison_contact_sheet.png'
    for directory in (cards_dir, pairs_dir):
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True, exist_ok=True)
    return cards_dir, pairs_dir, manifest_path, after_sheet_path, comparison_sheet_path


def _contact_sheet(items: list[tuple[str, Path]], output_path: Path, *, thumb_size: tuple[int, int], cols: int) -> None:
    if not items:
        return
    rows = (len(items) + cols - 1) // cols
    cell_w = thumb_size[0] + 42
    cell_h = thumb_size[1] + 76
    sheet = Image.new('RGB', (cols * cell_w + 20, rows * cell_h + 20), '#091019')
    draw = ImageDraw.Draw(sheet)
    label_font = _font(18)
    small_font = _font(13, bold=False)
    for index, (label, image_path) in enumerate(items):
        with Image.open(image_path) as image:
            thumb = ImageOps.fit(image.convert('RGB'), thumb_size)
        col = index % cols
        row = index // cols
        x = 20 + col * cell_w
        y = 20 + row * cell_h
        sheet.paste(thumb, (x, y))
        draw.text((x, y + thumb_size[1] + 10), label, fill='white', font=label_font)
        draw.text((x, y + thumb_size[1] + 36), image_path.name, fill='#8fa0b3', font=small_font)
    sheet.save(output_path)


def _comparison_card(before_path: Path, after_path: Path, label: str, output_path: Path) -> Path:
    with Image.open(before_path) as before_image, Image.open(after_path) as after_image:
        before_thumb = ImageOps.fit(before_image.convert('RGB'), (520, 292))
        after_thumb = ImageOps.fit(after_image.convert('RGB'), (520, 292))
    canvas = Image.new('RGB', (1100, 392), '#081019')
    draw = ImageDraw.Draw(canvas)
    canvas.paste(before_thumb, (20, 60))
    canvas.paste(after_thumb, (560, 60))
    label_font = _font(24)
    caption_font = _font(16, bold=False)
    draw.text((20, 18), label, fill='white', font=label_font)
    draw.text((20, 360), 'Before', fill='#9db0c4', font=caption_font)
    draw.text((560, 360), 'After', fill='#9db0c4', font=caption_font)
    draw.rectangle((19, 59, 541, 353), outline='#2a3948', width=1)
    draw.rectangle((559, 59, 1081, 353), outline='#2a3948', width=1)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)
    return output_path


def _latest_roundup_snapshot() -> Path | None:
    candidates = sorted((REPO_ROOT / 'output' / 'analytics').glob(ROUNDUP_SNAPSHOT_GLOB))
    return candidates[-1] if candidates else None


def _resolve_before_map(before_root: Path | None) -> dict[str, Path]:
    if before_root is None:
        return {}
    root = before_root.resolve()
    manifest_path = root / 'review_manifest.json'
    if manifest_path.exists():
        payload = json.loads(manifest_path.read_text(encoding='utf-8'))
        mapping: dict[str, Path] = {}
        for case in payload.get('cases', []):
            slug = str(case.get('slug') or '').strip()
            after_path = Path(str(case.get('after_path') or '')).resolve()
            if slug and after_path.exists():
                mapping[slug] = after_path
        return mapping
    cards_dir = root / 'cards'
    if not cards_dir.exists():
        return {}
    mapping = {}
    for image_path in cards_dir.glob('yoto_card_*.png'):
        slug = image_path.stem.removeprefix('yoto_card_')
        mapping[slug] = image_path.resolve()
    return mapping


def _make_payload(data_cls: type, payload: dict[str, Any]) -> object:
    return data_cls.from_mapping(payload)


def _build_roundup_case(data_cls: type, type_cls: type) -> ReviewCase | None:
    snapshot_path = _latest_roundup_snapshot()
    if snapshot_path is None:
        return None
    payload = json.loads(snapshot_path.read_text(encoding='utf-8'))
    roundups = payload.get('roundups') or []
    if not roundups:
        return None
    roundup = roundups[0]
    diagnostics = roundup.get('card_render_diagnostics') or {}
    score_summary = diagnostics.get('hero_score_summary') or []
    selected = next((item for item in score_summary if item.get('selected')), score_summary[0] if score_summary else None)
    artwork_path = Path(str((selected or {}).get('materialized_path') or '')) if selected else None
    if artwork_path is not None and not artwork_path.exists():
        artwork_path = None
    title = str(roundup.get('title') or 'Top picks')
    item_count = int(roundup.get('item_count') or 0)
    list_label = str(roundup.get('theme_label') or 'Editorial picks')
    return ReviewCase(
        slug='typography_top_list_roundup',
        label='TOP_LIST / Roundup / editorial case',
        family='TOP_LIST',
        traits=['top_list', 'roundup', 'editorial_case'],
        payload=_make_payload(
            data_cls,
            {
                'title': title,
                'platform': 'STEAM',
                'type': type_cls.TOP_LIST,
                'artwork_path': artwork_path,
                'slug': 'typography_top_list_roundup',
                'platform_badge': 'STEAM TOP',
                'sticker_header': 'TOP LIST',
                'sticker_text': f'Top {item_count or 5}',
                'brand_micro_label': '\u0432\u0438\u0431\u0456\u0440 \u0440\u0435\u0434\u0430\u043a\u0446\u0456\u0457',
                'list_label': list_label,
                'editorial_phrase': str(diagnostics.get('editorial_phrase') or ''),
                'hero_selection': diagnostics.get('hero_selection'),
            },
        ),
        before_path=Path(str(roundup.get('card_asset_path') or '')) if roundup.get('card_asset_path') else None,
    )


def _build_cases(data_cls: type, type_cls: type) -> list[ReviewCase]:
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    sparse_source = SOURCE_DIR / 'sparse_header_source.png'
    if not sparse_source.exists():
        build_sparse_header_source(sparse_source)

    cases = [
        ReviewCase(
            slug='typography_free_epic_turnip_boy',
            label='FREE_GAME / real art / logo-heavy',
            family='FREE_GAME',
            traits=['free_game', 'real_art', 'logo_heavy'],
            payload=_make_payload(
                data_cls,
                {
                    'title': 'Turnip Boy Robs a Bank',
                    'platform': 'EPIC',
                    'type': type_cls.FREE_GAME,
                    'deadline': MONTH_DEADLINE,
                    'old_price': '699 \u0433\u0440\u043d',
                    'artwork_path': CACHE_FILES['turnip_boy'],
                    'slug': 'typography_free_epic_turnip_boy',
                    'brand_micro_label': '\u0456\u0433\u0440\u043e\u0432\u0456 \u0440\u043e\u0437\u0434\u0430\u0447\u0456',
                    'hero_selection': {
                        'selected_source': 'hero',
                        'reason': 'selected_primary_hero',
                        'candidates_evaluated': 1,
                        'rejected_capsules': [],
                        'score_summary': [
                            {
                                'asset_url': 'https://example.com/turnip_boy_logo_art.png',
                                'selected': True,
                                'text_coverage_ratio': 0.44,
                                'horizontal_text_block': False,
                                'promotional_layout': False,
                            }
                        ],
                        'fallback_used': False,
                    },
                },
            ),
            before_path=OUTPUT_ROOT / 'yoto_card_v41_freebie_turnip_boy_robs_a_bank.png',
        ),
        ReviewCase(
            slug='typography_free_fallback',
            label='FREE_GAME / fallback / no image',
            family='FREE_GAME',
            traits=['free_game', 'fallback', 'low_asset'],
            payload=_make_payload(
                data_cls,
                {
                    'title': 'Mystery Weekly Free Drop',
                    'platform': 'EPIC',
                    'type': type_cls.FREE_GAME,
                    'deadline': MONTH_DEADLINE,
                    'old_price': '499 \u0433\u0440\u043d',
                    'artwork_path': None,
                    'slug': 'typography_free_fallback',
                    'brand_micro_label': 'fallback mode',
                },
            ),
            before_path=OUTPUT_ROOT / 'yoto_card_v41_no_image_fallback.png',
        ),
        ReviewCase(
            slug='typography_discount_slay_the_spire',
            label='DISCOUNT / bright art',
            family='DISCOUNT',
            traits=['discount', 'bright_art'],
            payload=_make_payload(
                data_cls,
                {
                    'title': 'Slay the Spire',
                    'platform': 'STEAM',
                    'type': type_cls.DISCOUNT,
                    'deadline': '\u0434\u043e 18 \u0431\u0435\u0440\u0435\u0437\u043d\u044f, 19:00',
                    'old_price': '525 \u0433\u0440\u043d',
                    'current_price': '-75%',
                    'artwork_path': CACHE_FILES['slay_the_spire'],
                    'slug': 'typography_discount_slay_the_spire',
                    'brand_micro_label': '\u0441\u0438\u0433\u043d\u0430\u043b \u0437\u043d\u0438\u0436\u043e\u043a',
                },
            ),
            before_path=OUTPUT_ROOT / 'yoto_card_v41_discount_slay_the_spire.png',
        ),
        ReviewCase(
            slug='typography_discount_black_desert_dark',
            label='DISCOUNT / dark art',
            family='DISCOUNT',
            traits=['discount', 'dark_art'],
            payload=_make_payload(
                data_cls,
                {
                    'title': 'Black Desert Online',
                    'platform': 'STEAM',
                    'type': type_cls.DISCOUNT,
                    'deadline': '\u0434\u043e 15 \u0431\u0435\u0440\u0435\u0437\u043d\u044f, 17:00',
                    'old_price': '1199 \u0433\u0440\u043d',
                    'current_price': '-60%',
                    'artwork_path': CACHE_FILES['black_desert'],
                    'slug': 'typography_discount_black_desert_dark',
                    'brand_micro_label': '\u0441\u0438\u0433\u043d\u0430\u043b \u0437\u043d\u0438\u0436\u043e\u043a',
                },
            ),
            before_path=None,
        ),
        ReviewCase(
            slug='typography_discount_black_desert_long',
            label='DISCOUNT / long title',
            family='DISCOUNT',
            traits=['discount', 'long_title'],
            payload=_make_payload(
                data_cls,
                {
                    'title': 'Black Desert Online: Land of the Morning Light Deluxe Founder Celebration Collection',
                    'platform': 'STEAM',
                    'type': type_cls.DISCOUNT,
                    'deadline': '\u0434\u043e 15 \u0431\u0435\u0440\u0435\u0437\u043d\u044f, 17:00',
                    'old_price': '1199 \u0433\u0440\u043d',
                    'current_price': '-60%',
                    'artwork_path': CACHE_FILES['black_desert'],
                    'slug': 'typography_discount_black_desert_long',
                    'brand_micro_label': '\u0441\u0438\u0433\u043d\u0430\u043b \u0437\u043d\u0438\u0436\u043e\u043a',
                },
            ),
            before_path=OUTPUT_ROOT / 'yoto_card_v41_long_title_black_desert.png',
        ),
        ReviewCase(
            slug='typography_festival_motorfest',
            label='FESTIVAL / event art',
            family='FESTIVAL',
            traits=['festival', 'event_art'],
            payload=_make_payload(
                data_cls,
                {
                    'title': 'The Crew Motorfest Season 09',
                    'platform': 'UBISOFT',
                    'type': type_cls.FESTIVAL,
                    'deadline': EVENT_DEADLINE,
                    'artwork_path': CACHE_FILES['motorfest'],
                    'slug': 'typography_festival_motorfest',
                    'platform_badge': 'LIVE EVENT',
                    'brand_micro_label': '\u0440\u0430\u0434\u0430\u0440 \u043f\u043e\u0434\u0456\u0439',
                    'editorial_phrase': 'Season spotlight',
                },
            ),
            before_path=OUTPUT_ROOT / 'yoto_card_v41_festival_the_crew_motorfest_season_09.png',
        ),
        ReviewCase(
            slug='typography_festival_sparse_asset',
            label='FESTIVAL / sparse logo-heavy source',
            family='FESTIVAL',
            traits=['festival', 'sparse_source', 'logo_heavy'],
            payload=_make_payload(
                data_cls,
                {
                    'title': 'Steam Next Fest',
                    'platform': 'STEAM',
                    'type': type_cls.FESTIVAL,
                    'deadline': EVENT_DEADLINE,
                    'artwork_path': sparse_source,
                    'slug': 'typography_festival_sparse_asset',
                    'platform_badge': 'STEAM EVENT',
                    'brand_micro_label': '\u0440\u0430\u0434\u0430\u0440 \u043f\u043e\u0434\u0456\u0439',
                    'editorial_phrase': 'Live event radar',
                    'hero_selection': {
                        'selected_source': 'header',
                        'reason': 'selected_store_header',
                        'candidates_evaluated': 1,
                        'rejected_capsules': [],
                        'score_summary': [
                            {
                                'asset_url': str(sparse_source),
                                'selected': True,
                                'text_coverage_ratio': 0.48,
                                'horizontal_text_block': False,
                                'promotional_layout': False,
                            }
                        ],
                        'fallback_used': False,
                    },
                },
            ),
            before_path=OUTPUT_ROOT / 'yoto_card_v41_sparse_asset_steam_next_fest.png',
        ),
    ]
    roundup_case = _build_roundup_case(data_cls, type_cls)
    if roundup_case is not None:
        cases.append(roundup_case)
    return cases


def render_review_pack(*, before_root: Path | None = None, engine_path: Path | None = None) -> tuple[Path, dict[str, object]]:
    data_cls, engine_cls, type_cls, engine_source = _load_engine_module(engine_path)
    timestamp = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    output_root = OUTPUT_ROOT / f'{REVIEW_PREFIX}{timestamp}'
    cards_dir, pairs_dir, manifest_path, after_sheet_path, comparison_sheet_path = _prepare_output_root(output_root)
    engine = engine_cls(cards_dir)
    before_map = _resolve_before_map(before_root)

    rendered_cases: list[RenderedCase] = []
    after_sheet_inputs: list[tuple[str, Path]] = []
    comparison_sheet_inputs: list[tuple[str, Path]] = []
    blockers: list[str] = []

    cases = _build_cases(data_cls, type_cls)
    if not any(case.family == 'TOP_LIST' for case in cases):
        blockers.append('missing_roundup_case')

    for case in cases:
        artwork_path = getattr(case.payload, 'artwork_path', None)
        if artwork_path is not None and isinstance(artwork_path, Path) and not artwork_path.exists():
            blockers.append(f'missing_artwork:{case.slug}')
        result = engine.render_card(case.payload)
        effective_before = before_map.get(case.slug, case.before_path)
        comparison_path: Path | None = None
        before_exists = bool(effective_before and effective_before.exists())
        if before_exists and effective_before is not None:
            comparison_path = _comparison_card(effective_before, result.image_path, case.label, pairs_dir / f'{case.slug}_before_after.png')
            comparison_sheet_inputs.append((case.label, comparison_path))
        elif effective_before is not None:
            blockers.append(f'missing_before:{effective_before}')
        rendered_cases.append(
            RenderedCase(
                case=case,
                image_path=result.image_path,
                diagnostics=_json_ready(asdict(result.diagnostics)),
                before_exists=before_exists,
                comparison_path=comparison_path,
                before_path=effective_before,
            )
        )
        after_sheet_inputs.append((case.label, result.image_path))

    _contact_sheet(after_sheet_inputs, after_sheet_path, thumb_size=(360, 202), cols=3)
    _contact_sheet(comparison_sheet_inputs, comparison_sheet_path, thumb_size=(360, 128), cols=2)

    manifest = {
        'manifest_version': 'yoto_premium_finish_review_v2',
        'finish_system': 'premium_finish_v2',
        'created_at': datetime.utcnow().isoformat() + 'Z',
        'engine_source': engine_source,
        'before_root': str(before_root.resolve()) if before_root is not None else None,
        'output_root': str(output_root),
        'cards_dir': str(cards_dir),
        'pairs_dir': str(pairs_dir),
        'after_contact_sheet_path': str(after_sheet_path),
        'comparison_contact_sheet_path': str(comparison_sheet_path),
        'case_count': len(rendered_cases),
        'blockers': blockers,
        'cases': [
            {
                'slug': item.case.slug,
                'label': item.case.label,
                'family': item.case.family,
                'traits': list(item.case.traits),
                'before_path': str(item.before_path) if item.before_path else None,
                'before_exists': item.before_exists,
                'after_path': str(item.image_path),
                'comparison_path': str(item.comparison_path) if item.comparison_path else None,
                'diagnostics': item.diagnostics,
            }
            for item in rendered_cases
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    return output_root, manifest


def main() -> None:
    args = parse_args()
    output_root, manifest = render_review_pack(before_root=args.before_root, engine_path=args.engine_path)
    print(json.dumps({'output_root': str(output_root), 'case_count': manifest['case_count'], 'blockers': manifest['blockers']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
