from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import sys
from typing import Any

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from video_generator.application.use_cases.build_voice_ready_package import BuildVoiceReadyPackageUseCase
from video_generator.domain.scene_planner import ScenePlanner
from video_generator.domain.template_selector import TemplateSelector
from video_generator.infrastructure.asset_resolver import AssetResolver
from video_generator.infrastructure.ffmpeg_renderer import FFmpegRenderer
from video_generator.infrastructure.font_loader import FontLoader
from video_generator.infrastructure.manifest_loader import ManifestLoader
from video_generator.infrastructure.scene_image_renderer import SceneImageRenderer
from video_generator.infrastructure.structured_logger import StructuredLogger

OUTPUT_ROOT = REPO_ROOT / 'output' / 'video_voice_ready'
VIDEO_MANIFESTS_DIR = REPO_ROOT / 'output' / 'video_manifests'
TEMP_DIR = REPO_ROOT / 'temp'


@dataclass(slots=True)
class ManifestSummary:
    manifest_path: Path
    family: str
    content_type: str
    short_title: str
    run_key: str
    discount_percent: int
    summary_length: int
    has_local_visual: bool


@dataclass(slots=True)
class ReviewCase:
    case_id: str
    label: str
    family: str
    source_kind: str
    manifest_path: Path


PERCENT_RE = re.compile(r'(\d{1,3})%')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Generate a multi-family voice-ready YOTO review pack.')
    parser.add_argument('--output-root', type=Path, default=OUTPUT_ROOT)
    parser.add_argument('--skip-preview-video', action='store_true', help='Skip preview MP4 rendering and emit scene assets only.')
    return parser.parse_args()


def build_voice_ready_use_case(output_dir: Path) -> BuildVoiceReadyPackageUseCase:
    logger = StructuredLogger('voice_ready_review_pack')
    asset_resolver = AssetResolver(logger=logger)
    scene_renderer = SceneImageRenderer(
        asset_resolver=asset_resolver,
        font_loader=FontLoader(logger=logger),
        logger=logger,
    )
    return BuildVoiceReadyPackageUseCase(
        manifest_loader=ManifestLoader(),
        asset_resolver=asset_resolver,
        template_selector=TemplateSelector(),
        scene_planner=ScenePlanner(),
        scene_renderer=scene_renderer,
        ffmpeg_renderer=FFmpegRenderer(logger=logger),
        output_dir=output_dir,
        logger=logger,
    )


def discover_manifest_summaries() -> list[ManifestSummary]:
    candidates = list(VIDEO_MANIFESTS_DIR.glob('*_video_manifest_*.json'))
    candidates.extend(
        path
        for path in TEMP_DIR.rglob('*_video_manifest_*.json')
        if path.is_file() and 'roundup' in path.name.lower()
    )
    summaries: list[ManifestSummary] = []
    seen: set[Path] = set()
    for path in sorted(candidates):
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        family = family_from_payload(payload)
        content_type = str(payload.get('content_type') or '').strip().lower()
        short_title = str(payload.get('short_title') or payload.get('offer_id') or path.stem)
        run_key = str(payload.get('run_key') or '')
        source_artifact = payload.get('source_artifact') or {}
        if not isinstance(source_artifact, dict):
            source_artifact = {}
        asset_refs = payload.get('asset_refs') or {}
        if not isinstance(asset_refs, dict):
            asset_refs = {}
        local_visual = any(
            is_existing_local_path(candidate)
            for candidate in (source_artifact.get('image_path'), asset_refs.get('card_image'))
        )
        summaries.append(
            ManifestSummary(
                manifest_path=path,
                family=family,
                content_type=content_type,
                short_title=short_title,
                run_key=run_key,
                discount_percent=extract_discount_percent(payload),
                summary_length=len(str(payload.get('summary_line') or '')),
                has_local_visual=local_visual,
            )
        )
    return summaries


def family_from_payload(payload: dict[str, Any]) -> str:
    content_type = str(payload.get('content_type') or (payload.get('context') or {}).get('content_type') or '').strip().lower()
    context = payload.get('context') or {}
    lane = str(context.get('lane') or '').strip().lower()
    template_id = str(context.get('template_id') or '').strip().lower()
    offer_kind = str(context.get('offer_kind') or '').strip().lower()
    template_hint = str(payload.get('template_hint') or '').strip().lower()
    if content_type == 'roundup' or lane == 'roundup_digest' or template_id == 'roundup_digest':
        return 'TOP_LIST'
    if content_type == 'freebie' or offer_kind == 'freebie' or template_hint == 'freebie-flash':
        return 'FREE_GAME'
    if content_type == 'event' or offer_kind in {'event', 'festival'} or template_hint == 'event-countdown':
        return 'FESTIVAL'
    return 'DISCOUNT'


def is_existing_local_path(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    candidate = Path(value)
    return candidate.is_absolute() and candidate.exists() and candidate.is_file()


def extract_discount_percent(payload: dict[str, Any]) -> int:
    voice_facts = payload.get('voice_facts') or {}
    if isinstance(voice_facts.get('discount_percent'), int):
        return int(voice_facts['discount_percent'])
    for value in (payload.get('hook_line'), payload.get('caption_html')):
        if not isinstance(value, str):
            continue
        match = PERCENT_RE.search(value)
        if match:
            return int(match.group(1))
    return 0


def choose_cases(review_root: Path, summaries: list[ManifestSummary]) -> list[ReviewCase]:
    free_games = [summary for summary in summaries if summary.family == 'FREE_GAME']
    discounts = [summary for summary in summaries if summary.family == 'DISCOUNT']
    festivals = [summary for summary in summaries if summary.family == 'FESTIVAL']
    top_lists = [summary for summary in summaries if summary.family == 'TOP_LIST']

    cases: list[ReviewCase] = []
    used_paths: set[Path] = set()

    free_real = pick_latest(free_games)
    if free_real is not None:
        used_paths.add(free_real.manifest_path)
        cases.append(
            ReviewCase(
                case_id='free_game_real',
                label='FREE_GAME / real art / strong case',
                family='FREE_GAME',
                source_kind='repo_manifest',
                manifest_path=free_real.manifest_path,
            )
        )

    free_sparse = pick_sparse_free_game(free_games, used_paths, avoid_title=free_real.short_title if free_real is not None else None)
    if free_sparse is None:
        free_sparse_path = write_fixture_manifest(review_root, 'free_game_sparse', free_game_sparse_fixture())
        cases.append(
            ReviewCase(
                case_id='free_game_sparse',
                label='FREE_GAME / fallback or sparse case',
                family='FREE_GAME',
                source_kind='fixture_manifest',
                manifest_path=free_sparse_path,
            )
        )
    else:
        used_paths.add(free_sparse.manifest_path)
        cases.append(
            ReviewCase(
                case_id='free_game_sparse',
                label='FREE_GAME / fallback or sparse case',
                family='FREE_GAME',
                source_kind='repo_manifest',
                manifest_path=free_sparse.manifest_path,
            )
        )

    discount_strong = pick_best(discounts, used_paths, key=lambda item: (item.discount_percent, item.run_key, item.short_title))
    if discount_strong is None:
        raise RuntimeError('No discount manifests available for review pack.')
    used_paths.add(discount_strong.manifest_path)
    cases.append(
        ReviewCase(
            case_id='discount_strong',
            label='DISCOUNT / strong value case',
            family='DISCOUNT',
            source_kind='repo_manifest',
            manifest_path=discount_strong.manifest_path,
        )
    )

    discount_long = pick_best(discounts, used_paths, key=lambda item: (len(item.short_title), item.run_key, item.discount_percent))
    if discount_long is None:
        discount_long = discount_strong
    else:
        used_paths.add(discount_long.manifest_path)
    cases.append(
        ReviewCase(
            case_id='discount_long_title',
            label='DISCOUNT / long-title or darker case',
            family='DISCOUNT',
            source_kind='repo_manifest',
            manifest_path=discount_long.manifest_path,
        )
    )

    festival_case = pick_latest(festivals)
    if festival_case is not None:
        cases.append(
            ReviewCase(
                case_id='festival_event',
                label='FESTIVAL / event framing case',
                family='FESTIVAL',
                source_kind='repo_manifest',
                manifest_path=festival_case.manifest_path,
            )
        )

    top_list_case = pick_latest(top_lists)
    if top_list_case is None:
        top_list_path = write_fixture_manifest(review_root, 'top_list_roundup', top_list_fixture())
        cases.append(
            ReviewCase(
                case_id='top_list_roundup',
                label='TOP_LIST / editorial roundup case',
                family='TOP_LIST',
                source_kind='fixture_manifest',
                manifest_path=top_list_path,
            )
        )
    else:
        cases.append(
            ReviewCase(
                case_id='top_list_roundup',
                label='TOP_LIST / editorial roundup case',
                family='TOP_LIST',
                source_kind='repo_manifest',
                manifest_path=top_list_case.manifest_path,
            )
        )

    return cases


def pick_latest(items: list[ManifestSummary]) -> ManifestSummary | None:
    if not items:
        return None
    return sorted(items, key=lambda item: (item.has_local_visual, item.run_key, item.manifest_path.name))[-1]


def pick_best(
    items: list[ManifestSummary],
    used_paths: set[Path],
    *,
    key,
) -> ManifestSummary | None:
    available = [item for item in items if item.manifest_path not in used_paths]
    if not available:
        return None
    return sorted(available, key=lambda item: (item.has_local_visual, key(item)))[-1]


def pick_sparse_free_game(
    items: list[ManifestSummary],
    used_paths: set[Path],
    *,
    avoid_title: str | None = None,
) -> ManifestSummary | None:
    available = [item for item in items if item.manifest_path not in used_paths]
    if avoid_title is not None:
        alternate = [item for item in available if item.short_title != avoid_title]
        if alternate:
            available = alternate
    if not available:
        return None
    return sorted(available, key=lambda item: (not item.has_local_visual, item.summary_length, item.run_key, item.manifest_path.name))[0]


def write_fixture_manifest(review_root: Path, case_id: str, payload: dict[str, Any]) -> Path:
    fixtures_dir = review_root / 'fixtures'
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    image_path = fixtures_dir / f'{case_id}.png'
    Image.new('RGB', (1080, 1920), (52, 74, 104)).save(image_path)
    payload['asset_refs'] = {
        'game_image': str(image_path),
        'background': str(image_path),
        'card_image': str(image_path),
    }
    payload.setdefault('source_artifact', {'image_path': str(image_path)})
    manifest_path = fixtures_dir / f'{case_id}.json'
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    return manifest_path


def free_game_sparse_fixture() -> dict[str, Any]:
    return {
        'manifest_version': 2,
        'run_key': 'fixture_free_game_sparse',
        'created_at': '2026-03-20T12:30:00',
        'offer_id': 'fixture:free-game-sparse',
        'short_title': 'Free Game Fixture',
        'hook_line': '\u0411\u0435\u0437\u043a\u043e\u0448\u0442\u043e\u0432\u043d\u0430 \u0440\u043e\u0437\u0434\u0430\u0447\u0430 \u0432\u0436\u0435 \u0430\u043a\u0442\u0438\u0432\u043d\u0430.',
        'summary_line': '\u041f\u0440\u043e \u0433\u0440\u0443 \u043c\u0430\u043b\u043e \u0442\u0435\u043a\u0441\u0442\u0443, \u0442\u043e\u0436 \u043f\u0430\u043a\u0435\u0442 \u0439\u0434\u0435 \u0432\u0456\u0434 \u0444\u0430\u043a\u0442\u0443 \u0440\u043e\u0437\u0434\u0430\u0447\u0456.',
        'urgency_line': '\u0417\u0430\u0431\u0440\u0430\u0442\u0438 \u043c\u043e\u0436\u043d\u0430 \u0434\u043e 21 \u0431\u0435\u0440\u0435\u0437\u043d\u044f 2026, 15:00.',
        'cta_line': '\u041f\u043e\u0441\u0438\u043b\u0430\u043d\u043d\u044f \u0432 \u043f\u043e\u0441\u0442\u0456.',
        'content_type': 'freebie',
        'template_hint': 'freebie-flash',
        'context': {
            'store': 'Epic Games Store',
            'offer_kind': 'freebie',
            'lane': 'breaking_freebie',
            'content_type': 'freebie',
        },
        'voice_facts': {
            'title': 'Free Game Fixture',
            'free_access_type': 'keep_forever',
            'promo_end': '2026-03-21T15:00:00',
        },
    }


def top_list_fixture() -> dict[str, Any]:
    return {
        'manifest_version': 2,
        'run_key': 'fixture_top_list_roundup',
        'created_at': '2026-03-20T12:35:00',
        'offer_id': 'fixture:top-list',
        'short_title': 'Fixture Roundup',
        'hook_line': 'Fixture Roundup',
        'summary_line': 'Fixture One \u00b7 Fixture Two \u00b7 Fixture Three',
        'urgency_line': '\u041f\u0435\u0440\u0435\u0433\u043b\u044f\u043d\u044c \u0434\u043e\u0431\u0456\u0440\u043a\u0443, \u043f\u043e\u043a\u0438 \u0446\u0456 \u043f\u0440\u043e\u043f\u043e\u0437\u0438\u0446\u0456\u0457 \u0449\u0435 \u0430\u043a\u0442\u0438\u0432\u043d\u0456.',
        'cta_line': '\u041f\u043e\u0432\u043d\u0430 \u0434\u043e\u0431\u0456\u0440\u043a\u0430 \u0432 \u043f\u043e\u0441\u0442\u0456.',
        'content_type': 'roundup',
        'template_hint': 'deal-spotlight',
        'context': {
            'store': 'Steam',
            'offer_kind': 'discount',
            'lane': 'roundup_digest',
            'template_id': 'roundup_digest',
            'content_type': 'roundup',
            'video_template_intent': 'roundup_digest',
        },
        'roundup_items': [
            {'title': 'Fixture One', 'discount_percent': 95, 'offer_kind': 'discount'},
            {'title': 'Fixture Two', 'discount_percent': 90, 'offer_kind': 'discount'},
            {'title': 'Fixture Three', 'discount_percent': 85, 'offer_kind': 'discount'},
            {'title': 'Fixture Four', 'discount_percent': 80, 'offer_kind': 'discount'},
        ],
    }


def build_review_markdown(review_root: Path, case_results: list[dict[str, Any]]) -> str:
    lines = [
        '# Voice-Ready Review Pack',
        '',
        f'- Review Root: `{review_root}`',
        f'- Case Count: `{len(case_results)}`',
        '',
    ]
    for case in case_results:
        lines.extend(
            [
                f"## {case['label']}",
                f"- Family: `{case['family']}`",
                f"- Source: `{case['source_kind']}`",
                f"- Manifest: `{case['manifest_path']}`",
                f"- Package Dir: `{case['package_dir']}`",
                f"- Review: `{case['review_path']}`",
                f"- Script: `{case['voice_script_path']}`",
                f"- Timed Script: `{case['timed_script_path']}`",
                f"- Scene Plan: `{case['scene_plan_path']}`",
                f"- Preview Video: `{case['preview_video_path'] or 'not rendered'}`",
                f"- Warnings: `{len(case['warnings'])}`",
                '',
            ]
        )
    return '\n'.join(lines)


def main() -> int:
    args = parse_args()
    timestamp = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    review_root = args.output_root / f'review_pack_{timestamp}'
    packages_dir = review_root / 'packages'
    packages_dir.mkdir(parents=True, exist_ok=True)

    summaries = discover_manifest_summaries()
    cases = choose_cases(review_root, summaries)
    use_case = build_voice_ready_use_case(packages_dir)

    case_results: list[dict[str, Any]] = []
    failures: list[str] = []
    for case in cases:
        result = use_case.execute(case.manifest_path, render_preview_video=not args.skip_preview_video)
        if result.status != 'packaged':
            failures.append(f"{case.case_id}: {result.error}")
            continue
        case_results.append(
            {
                'case_id': case.case_id,
                'label': case.label,
                'family': case.family,
                'source_kind': case.source_kind,
                'manifest_path': str(case.manifest_path),
                'package_dir': str(result.package_dir),
                'package_manifest_path': str(result.package_manifest_path),
                'review_path': str(result.review_path),
                'voice_script_path': str(result.voice_script_path),
                'timed_script_path': str(result.timed_script_path),
                'scene_plan_path': str(result.scene_plan_path),
                'preview_video_path': str(result.preview_video_path) if result.preview_video_path else None,
                'warnings': list(result.warnings),
            }
        )

    review_manifest = {
        'manifest_version': 'voice_ready_review_pack_v1',
        'created_at': datetime.utcnow().isoformat() + 'Z',
        'review_root': str(review_root),
        'packages_root': str(packages_dir),
        'case_count': len(case_results),
        'failures': failures,
        'cases': case_results,
    }
    review_manifest_path = review_root / 'review_manifest.json'
    review_manifest_path.write_text(json.dumps(review_manifest, ensure_ascii=False, indent=2), encoding='utf-8')

    review_md_path = review_root / 'review.md'
    review_md_path.write_text(build_review_markdown(review_root, case_results), encoding='utf-8')

    print(f'review_root={review_root}')
    print(f'review_manifest={review_manifest_path}')
    print(f'review_markdown={review_md_path}')
    print(f'case_count={len(case_results)} failures={len(failures)}')
    if failures:
        for failure in failures:
            print(f'failed_case={failure}')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
