from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
import shutil
import sys
from typing import Any

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dealbot.settings import load_rendering_config
from infrastructure.render.cards.asset_sources.official_asset_source import resolve_official_asset_candidates
from infrastructure.render.cards.image_providers import ComfyUIImageProvider, ImageResolutionRequest, ResolvedImage
from infrastructure.render.cards.visual_decision_engine import build_cover_decision, build_visual_rescue_decision
from infrastructure.render.cards.yoto_card_engine_v4 import CARD_SIZE, YotoCardData, YotoCardEngineV4, YotoCardType

OUTPUT_ROOT = REPO_ROOT / 'output' / 'cards'
VALID_SCENARIOS = ('current_env', 'broken_comfyui', 'quality_reject', 'pure_generation')
DEFAULT_PROMPT_VARIANT = 'shot_focused_cinematic_grounded'
VALID_PROMPT_VARIANTS = (DEFAULT_PROMPT_VARIANT, 'hero_action_focus')
DEFAULT_GAME_SET = 'synthetic'
VALID_GAME_SETS = (DEFAULT_GAME_SET, 'minimal')
DEFAULT_EVAL_GAME_SET = 'minimal'
DEFAULT_SEEDS_PER_GAME = 1
BROKEN_COMFYUI_URL = 'http://127.0.0.1:9/broken-timeout'
SMOKE_LOCAL_LANDSCAPE_ASSET = str((REPO_ROOT / 'video_generator' / 'smoke_test' / 'assets' / 'game.png').resolve())
SMOKE_LOCAL_PORTRAIT_ASSET = str((REPO_ROOT / 'video_generator' / 'assets' / 'fallback_game_image.png').resolve())


def make_asset_candidate(
    source_type: str,
    width: int,
    height: int,
    kind: str,
    path_or_url: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        'source_type': source_type,
        'width': int(width),
        'height': int(height),
        'kind': kind,
        'path_or_url': path_or_url,
        'metadata': dict(metadata or {}),
    }


DEFAULT_SMOKE_GAME = {
    'slug': 'ai_card_smoke',
    'store_id': 'smoke:ai_card_smoke',
    'source_hint': 'smoke_fixture',
    'steam_app_id': None,
    'epic_slug': None,
    'title': 'AI Provider Smoke',
    'platform': 'STEAM',
    'type': YotoCardType.DISCOUNT,
    'offer_type': 'discount',
    'deadline': 'until 30 Apr, 18:00',
    'old_price': '899 UAH',
    'current_price': '-75%',
    'platform_badge': 'STEAM DISCOUNT',
    'brand_micro_label': 'smoke runtime',
    'lane': 'high_value_discount',
    'genre': 'co-op action shooter',
    'tags': ['co-op', 'sci-fi', 'industrial combat', 'squad push'],
    'short_description': 'A squad of armored operatives fights forward through a hostile industrial sci-fi facility under heavy fire and sparks.',
    'artwork_metadata': {
        'subject': 'armored squad leader in the foreground',
        'action': 'pushing forward while returning fire',
        'setting': 'industrial sci-fi facility corridor',
        'atmosphere': 'sparks, smoke, urgency',
        'lighting': 'hard rim light and muzzle flash',
    },
    'asset_candidates': [
        make_asset_candidate(
            'official_press_key_art',
            1800,
            2700,
            'key_art',
            'smoke://ai_provider_smoke/key_art.png',
            metadata={
                'subject_focus': 'character',
                'composition': 'foreground squad leader',
                'logo_safe': True,
                'scene_energy': 'combat sparks',
            },
        ),
        make_asset_candidate(
            'steam_screenshot',
            1920,
            1080,
            'screenshot',
            'smoke://ai_provider_smoke/gameplay_frame.png',
            metadata={
                'gameplay_focus': 'co-op firefight',
                'combat_clarity': 'high',
                'foreground_action': 'squad push',
            },
        ),
        make_asset_candidate(
            'ai_generated',
            1280,
            720,
            'generated_preview',
            'ai://preview/ai_provider_smoke',
            metadata={
                'prompt_intent': 'shot_focused_cinematic_grounded',
            },
        ),
    ],
}
MINIMAL_SMOKE_GAMES = (
    {
        'slug': 'hades_ii',
        'store_id': 'steam:hades_ii',
        'source_hint': 'steam',
        'steam_app_id': '1145350',
        'title': 'Hades II',
        'platform': 'STEAM',
        'type': YotoCardType.DISCOUNT,
        'offer_type': 'discount',
        'deadline': 'until 30 Apr, 18:00',
        'old_price': '1299 UAH',
        'current_price': '-20%',
        'platform_badge': 'STEAM DISCOUNT',
        'brand_micro_label': 'minimal smoke',
        'lane': 'high_value_discount',
        'genre': 'roguelike action',
        'tags': ['mythic underworld', 'witch combat', 'arcane dash', 'moonlit ruins'],
        'short_description': 'The Princess of the Underworld fights through moonlit ruins and infernal chambers with blades, sorcery, and ritual momentum.',
        'artwork_metadata': {
            'subject': 'young battle witch in the foreground',
            'action': 'lunging forward with glowing blades and sigils',
            'setting': 'moonlit underworld ruins',
            'atmosphere': 'embers, smoke trails, occult energy',
            'lighting': 'high contrast moonlight and green magic flare',
        },
        'asset_candidates': [
            make_asset_candidate(
                'official_press_key_art',
                1800,
                2700,
                'key_art',
                SMOKE_LOCAL_PORTRAIT_ASSET,
                metadata={
                    'subject_focus': 'character',
                    'composition': 'foreground hero portrait',
                    'logo_safe': True,
                    'weapon_emphasis': 'glowing blades',
                },
            ),
            make_asset_candidate(
                'steam_main_capsule',
                1232,
                706,
                'main_capsule',
                'smoke://hades_ii/steam_main_capsule.png',
                metadata={
                    'subject_focus': 'character',
                    'logo_safe': True,
                    'marketing_pose': 'hero action',
                },
            ),
            make_asset_candidate(
                'steam_screenshot',
                1920,
                1080,
                'screenshot',
                'smoke://hades_ii/gameplay_screenshot.png',
                metadata={
                    'gameplay_focus': 'combat',
                    'effects': 'green magic',
                },
            ),
            make_asset_candidate(
                'ai_generated',
                1280,
                720,
                'generated_preview',
                'ai://preview/hades_ii',
                metadata={
                    'prompt_intent': 'hero_action_focus',
                },
            ),
        ],
    },
    {
        'slug': 'civilization_vi',
        'store_id': 'steam:civilization_vi',
        'source_hint': 'steam',
        'steam_app_id': '289070',
        'title': 'Civilization VI',
        'platform': 'STEAM',
        'type': YotoCardType.DISCOUNT,
        'offer_type': 'discount',
        'deadline': 'until 30 Apr, 18:00',
        'old_price': '999 UAH',
        'current_price': '-85%',
        'platform_badge': 'STEAM DISCOUNT',
        'brand_micro_label': 'minimal smoke',
        'lane': 'high_value_discount',
        'genre': 'turn-based strategy',
        'tags': ['world map', 'city building', 'historic leaders', 'wonders'],
        'short_description': 'A growing empire expands across a colorful world map with fortified cities, marching armies, and monumental wonders.',
        'artwork_metadata': {
            'subject': 'commanding ruler overlooking a growing capital',
            'action': 'directing expansion across a strategic world map',
            'setting': 'sunlit capital city with distant armies and wonders',
            'atmosphere': 'grand scale, clarity, strategic tension',
            'lighting': 'bright golden daylight with crisp horizon detail',
        },
        'asset_candidates': [
            make_asset_candidate(
                'steam_screenshot',
                1920,
                1080,
                'screenshot',
                SMOKE_LOCAL_LANDSCAPE_ASSET,
                metadata={
                    'gameplay_focus': 'world map',
                    'hud_visible': True,
                    'city_builder_clarity': 'high',
                    'strategy_layer': 'empire overview',
                },
            ),
            make_asset_candidate(
                'steam_library_hero',
                3840,
                1240,
                'library_hero',
                'smoke://civilization_vi/library_hero.png',
                metadata={
                    'scene_focus': 'leaders and landmarks',
                    'map_context': 'broad empire scene',
                },
            ),
            make_asset_candidate(
                'official_press_key_art',
                1600,
                2400,
                'key_art',
                'smoke://civilization_vi/official_key_art.png',
                metadata={
                    'subject_focus': 'leader portrait',
                    'poster_layout': True,
                },
            ),
            make_asset_candidate(
                'ai_generated',
                1280,
                720,
                'generated_preview',
                'ai://preview/civilization_vi',
                metadata={
                    'prompt_intent': 'shot_focused_cinematic_grounded',
                },
            ),
        ],
    },
    {
        'slug': 'dave_the_diver',
        'store_id': 'steam:dave_the_diver',
        'source_hint': 'steam',
        'steam_app_id': '1868140',
        'title': 'Dave the Diver',
        'platform': 'STEAM',
        'type': YotoCardType.DISCOUNT,
        'offer_type': 'discount',
        'deadline': 'until 30 Apr, 18:00',
        'old_price': '699 UAH',
        'current_price': '-30%',
        'platform_badge': 'STEAM DISCOUNT',
        'brand_micro_label': 'minimal smoke',
        'lane': 'high_value_discount',
        'genre': 'adventure management sim',
        'tags': ['underwater exploration', 'harpoon hunt', 'tropical reef', 'night sushi bar'],
        'short_description': 'A diver explores a vibrant blue reef by day to catch unusual fish, then races back to support a bustling sushi bar at night.',
        'artwork_metadata': {
            'subject': 'heavyset diver in clear foreground water',
            'action': 'aiming a harpoon at fast tropical fish',
            'setting': 'sunlit reef with coral walls and schools of fish',
            'atmosphere': 'playful, busy, vivid underwater life',
            'lighting': 'bright aqua shafts of light through water',
        },
        'asset_candidates': [
            make_asset_candidate(
                'steam_screenshot',
                1920,
                1080,
                'screenshot',
                SMOKE_LOCAL_LANDSCAPE_ASSET,
                metadata={
                    'gameplay_focus': 'underwater exploration',
                    'harpoon_action': True,
                    'readable_subject': 'diver and fish',
                },
            ),
            make_asset_candidate(
                'steam_library_hero',
                3840,
                1240,
                'library_hero',
                'smoke://dave_the_diver/library_hero.png',
                metadata={
                    'scene_focus': 'reef and diver',
                    'color_palette': 'bright aqua',
                },
            ),
            make_asset_candidate(
                'official_press_key_art',
                1600,
                2400,
                'key_art',
                'smoke://dave_the_diver/official_key_art.png',
                metadata={
                    'subject_focus': 'diver character',
                    'poster_layout': True,
                },
            ),
        ],
    },
    {
        'slug': 'forza_horizon_5',
        'store_id': 'steam:forza_horizon_5',
        'source_hint': 'steam',
        'steam_app_id': '1551360',
        'title': 'Forza Horizon 5',
        'platform': 'STEAM',
        'type': YotoCardType.DISCOUNT,
        'offer_type': 'discount',
        'deadline': 'until 30 Apr, 18:00',
        'old_price': '1599 UAH',
        'current_price': '-50%',
        'platform_badge': 'STEAM DISCOUNT',
        'brand_micro_label': 'minimal smoke',
        'lane': 'high_value_discount',
        'genre': 'open-world racing',
        'tags': ['supercar', 'desert sprint', 'dust trail', 'festival energy'],
        'short_description': 'A bright performance car tears across Mexican roads and desert trails, kicking up dust while crowd-lined festival scenery flashes past.',
        'artwork_metadata': {
            'subject': 'low-slung supercar dominating the foreground',
            'action': 'drifting hard through a fast desert corner',
            'setting': 'sunny Mexican highway near festival structures',
            'atmosphere': 'speed, heat shimmer, crowd excitement',
            'lighting': 'high contrast afternoon sun with reflective bodywork',
        },
        'asset_candidates': [
            make_asset_candidate(
                'steam_screenshot',
                2560,
                1440,
                'screenshot',
                SMOKE_LOCAL_LANDSCAPE_ASSET,
                metadata={
                    'vehicle_focus': 'supercar drift',
                    'scene_focus': 'desert road',
                    'speed_lines': True,
                    'crowd_energy': 'festival',
                },
            ),
            make_asset_candidate(
                'official_press_key_art',
                1600,
                2400,
                'key_art',
                'smoke://forza_horizon_5/official_key_art.png',
                metadata={
                    'vehicle_focus': 'hero car',
                    'poster_layout': True,
                    'logo_safe': True,
                },
            ),
            make_asset_candidate(
                'steam_library_hero',
                3840,
                1240,
                'library_hero',
                'smoke://forza_horizon_5/library_hero.png',
                metadata={
                    'scene_focus': 'open road vista',
                    'vehicle_focus': 'sports car',
                },
            ),
            make_asset_candidate(
                'ai_generated',
                1280,
                720,
                'generated_preview',
                'ai://preview/forza_horizon_5',
                metadata={
                    'prompt_intent': 'shot_focused_cinematic_grounded',
                },
            ),
        ],
    },
    {
        'slug': 'ultimate_strategy_collection',
        'store_id': 'steam:ultimate_strategy_collection',
        'source_hint': 'steam',
        'steam_app_id': None,
        'title': 'Ultimate Strategy Collection',
        'platform': 'STEAM',
        'type': YotoCardType.DISCOUNT,
        'offer_type': 'bundle',
        'deadline': 'until 30 Apr, 18:00',
        'old_price': '2199 UAH',
        'current_price': '-65%',
        'platform_badge': 'STEAM BUNDLE',
        'brand_micro_label': 'minimal smoke',
        'lane': 'high_value_discount',
        'genre': 'strategy franchise bundle',
        'tags': ['bundle', 'franchise', 'multi-item', 'grand strategy'],
        'short_description': 'A multi-game franchise bundle gathers several strategy favorites into one discounted pack with distinct official key art for each entry.',
        'artwork_metadata': {
            'subject': 'franchise lineup',
            'action': 'multiple games represented at once',
            'setting': 'bundle marketing collage',
            'atmosphere': 'editorial franchise overview',
            'lighting': 'clean promotional lighting',
        },
        'asset_candidates': [
            make_asset_candidate(
                'steam_main_capsule',
                1232,
                706,
                'main_capsule',
                'smoke://ultimate_strategy_collection/item_01_capsule.png',
                metadata={
                    'franchise': 'entry_one',
                    'series': 'strategy collection',
                    'logo_safe': True,
                    'multi_item': True,
                },
            ),
            make_asset_candidate(
                'steam_main_capsule',
                1232,
                706,
                'main_capsule',
                'smoke://ultimate_strategy_collection/item_02_capsule.png',
                metadata={
                    'franchise': 'entry_two',
                    'series': 'strategy collection',
                    'logo_safe': True,
                    'multi_item': True,
                },
            ),
            make_asset_candidate(
                'steam_main_capsule',
                1232,
                706,
                'main_capsule',
                'smoke://ultimate_strategy_collection/item_03_capsule.png',
                metadata={
                    'franchise': 'entry_three',
                    'series': 'strategy collection',
                    'logo_safe': True,
                    'multi_item': True,
                },
            ),
            make_asset_candidate(
                'steam_main_capsule',
                1232,
                706,
                'main_capsule',
                'smoke://ultimate_strategy_collection/item_04_capsule.png',
                metadata={
                    'franchise': 'entry_four',
                    'series': 'strategy collection',
                    'logo_safe': True,
                    'multi_item': True,
                },
            ),
        ],
    },
)


def build_smoke_data(
    *,
    run_key: str,
    artwork_path: Path,
    game_input: dict[str, Any] | None = None,
    seed: int | None = None,
) -> YotoCardData:
    selected_game = game_input or DEFAULT_SMOKE_GAME
    tags = [str(item) for item in selected_game.get('tags') or [] if str(item).strip()]
    artwork_metadata = selected_game.get('artwork_metadata')
    base_slug = str(selected_game.get('slug') or 'ai_card_smoke').strip() or 'ai_card_smoke'
    slug = f'{base_slug}_seed_{int(seed)}' if seed is not None else f'{base_slug}_{run_key}'
    return YotoCardData(
        title=str(selected_game.get('title') or 'AI Provider Smoke'),
        platform=str(selected_game.get('platform') or 'STEAM'),
        type=selected_game.get('type') or YotoCardType.DISCOUNT,
        deadline=str(selected_game.get('deadline') or 'until 30 Apr, 18:00'),
        old_price=str(selected_game.get('old_price') or '899 UAH'),
        current_price=str(selected_game.get('current_price') or '-75%'),
        artwork_path=artwork_path,
        slug=slug,
        platform_badge=str(selected_game.get('platform_badge') or 'STEAM DISCOUNT'),
        brand_micro_label=str(selected_game.get('brand_micro_label') or 'smoke runtime'),
        lane=str(selected_game.get('lane') or 'high_value_discount'),
        genre=str(selected_game.get('genre') or '').strip() or None,
        tags=tags or None,
        short_description=str(selected_game.get('short_description') or '').strip() or None,
        artwork_metadata=dict(artwork_metadata) if isinstance(artwork_metadata, dict) else None,
        cover_decision=(
            dict(selected_game.get('cover_decision'))
            if isinstance(selected_game.get('cover_decision'), dict)
            else None
        ),
    )


def build_image_request(engine: YotoCardEngineV4, data: YotoCardData) -> ImageResolutionRequest:
    card_type = data.normalized_type()
    return ImageResolutionRequest(
        artwork_path=data.artwork_path,
        title=data.title,
        platform=data.platform,
        slug=data.normalized_slug(),
        card_type=card_type.value,
        lane=data.lane,
        mode=engine.image_provider_mode,
        priority=engine.image_resolver.derive_priority(data.lane),
        image_size=CARD_SIZE,
        deadline=data.deadline,
        old_price=data.old_price,
        current_price=data.current_price,
        platform_badge=data.platform_badge,
        brand_micro_label=data.brand_micro_label,
        genre=data.genre,
        tags=[str(item) for item in data.tags or []] or None,
        short_description=data.short_description,
        artwork_metadata=dict(data.artwork_metadata) if data.artwork_metadata else None,
        cover_decision=dict(data.cover_decision) if isinstance(data.cover_decision, dict) else None,
    )


def infer_provider(engine: YotoCardEngineV4, selected_source: str) -> str:
    selected_source = str(selected_source or '').strip().lower()
    if selected_source == 'ai':
        return str(getattr(engine.image_resolver.ai_provider, 'provider_name', 'ai'))
    if selected_source in {'artwork', 'placeholder'}:
        provider = getattr(engine.image_resolver, f'{selected_source}_provider', None)
        return str(getattr(provider, 'provider_name', selected_source))
    return 'unknown'


def infer_final_source(selected_source: str) -> str:
    normalized = str(selected_source or '').strip().lower()
    if normalized == 'ai':
        return 'ai'
    if normalized == 'artwork':
        return 'asset'
    return 'fallback'


def infer_provider_attempted(*, ai_provider: Any, ai_attempted: bool) -> str | None:
    if not ai_attempted:
        return None
    value = str(getattr(ai_provider, 'provider_name', '') or '').strip()
    return value or None


def infer_fallback_used(final_source: str) -> bool:
    return str(final_source or '').strip().lower() == 'fallback'


def infer_fallback_reason(*, fallback_used: bool, decision_reason: Any) -> str | None:
    if not fallback_used:
        return None
    value = str(decision_reason or '').strip()
    return value or 'fallback_without_reason'


def classify_outcome(*, final_source: str, ai_attempted: bool, ai_succeeded: bool, fallback_used: bool) -> str:
    if final_source == 'asset':
        return 'official_asset'
    if ai_attempted and ai_succeeded and final_source == 'ai' and not fallback_used:
        return 'ai_runtime'
    if ai_attempted and (not ai_succeeded) and fallback_used:
        return 'ai_fallback'
    return 'ai_hard_failure'


def json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    return value


def safe_filename_token(value: Any, *, default: str) -> str:
    raw = str(value or '').strip()
    if not raw:
        return default
    token = ''.join(character if character.isalnum() or character in {'-', '_'} else '_' for character in raw)
    token = token.strip('_')
    return token or default


def resolve_output_png_path(*, image_path: Any, cards_dir: Path) -> Path:
    candidate_paths: list[Path] = []
    raw_image_path = str(image_path or '').strip()
    if raw_image_path:
        candidate_paths.append(Path(raw_image_path))
    if cards_dir.exists():
        candidate_paths.extend(
            sorted(
                (
                    path
                    for path in cards_dir.rglob('*')
                    if path.is_file() and path.suffix.lower() == '.png'
                ),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        )

    seen_paths: set[str] = set()
    for candidate_path in candidate_paths:
        try:
            resolved_path = candidate_path.resolve()
        except OSError:
            continue
        resolved_key = str(resolved_path)
        if resolved_key in seen_paths:
            continue
        seen_paths.add(resolved_key)
        if not resolved_path.exists() or not resolved_path.is_file():
            continue
        if resolved_path.suffix.lower() != '.png':
            continue
        try:
            with Image.open(resolved_path) as output_image:
                output_image.load()
                if str(output_image.format or '').upper() != 'PNG':
                    continue
        except (FileNotFoundError, OSError, ValueError):
            continue
        return resolved_path

    raise RuntimeError('missing_output_png')


def review_image_filename(*, game_slug: Any, seed: Any, source_type: Any) -> str:
    slug_token = safe_filename_token(game_slug, default='unknown_game')
    seed_token = safe_filename_token(seed, default='none')
    source_token = safe_filename_token(source_type, default='unknown_source')
    return f'{slug_token}__seed_{seed_token}__{source_token}.png'


def copy_review_image_for_result(*, result: dict[str, Any], review_cards_dir: Path) -> Path:
    run_root_value = str(result.get('run_root') or '').strip()
    cards_dir = Path(run_root_value) / 'cards' if run_root_value else review_cards_dir
    source_image_path = resolve_output_png_path(
        image_path=result.get('image_path') or result.get('output_path'),
        cards_dir=cards_dir,
    )
    source_type = (
        result.get('actual_image_source_type')
        or result.get('cover_decision_image_source_type')
        or result.get('selected_source')
        or 'unknown_source'
    )
    review_path = review_cards_dir / review_image_filename(
        game_slug=result.get('game_slug'),
        seed=result.get('seed'),
        source_type=source_type,
    )
    if review_path.exists():
        stem = review_path.stem
        suffix = review_path.suffix
        duplicate_index = 2
        while review_path.exists():
            review_path = review_cards_dir / f'{stem}__dup_{duplicate_index}{suffix}'
            duplicate_index += 1
    shutil.copy2(source_image_path, review_path)
    return review_path.resolve()


def resolve_asset_candidates_for_game(
    selected_game: dict[str, Any],
    *,
    download_assets: bool = False,
    asset_downloader: Any | None = None,
) -> dict[str, Any]:
    fallback_asset_candidates = [
        dict(item)
        for item in selected_game.get('asset_candidates') or []
        if isinstance(item, dict)
    ]
    source_result = resolve_official_asset_candidates(
        game_title=str(selected_game.get('title') or ''),
        steam_app_id=str(selected_game.get('steam_app_id') or '').strip() or None,
        epic_slug=str(selected_game.get('epic_slug') or '').strip() or None,
        asset_urls=selected_game.get('asset_urls') if isinstance(selected_game.get('asset_urls'), (dict, list, tuple)) else None,
        local_assets=selected_game.get('local_assets') if isinstance(selected_game.get('local_assets'), (dict, list, tuple)) else None,
        store_id=str(selected_game.get('store_id') or '').strip() or None,
        slug=str(selected_game.get('slug') or '').strip() or None,
        source_hint=str(selected_game.get('source_hint') or '').strip() or None,
        existing_metadata={
            'game_title': selected_game.get('title'),
            'store_id': selected_game.get('store_id'),
            'slug': selected_game.get('slug'),
            'source_hint': selected_game.get('source_hint'),
            'steam_app_id': selected_game.get('steam_app_id'),
            'epic_slug': selected_game.get('epic_slug'),
            'asset_urls': selected_game.get('asset_urls'),
            'local_assets': selected_game.get('local_assets'),
            'offer_type': selected_game.get('offer_type'),
            'genre': selected_game.get('genre'),
            'tags': [str(item) for item in selected_game.get('tags') or [] if str(item).strip()],
        },
        fallback_asset_candidates=fallback_asset_candidates,
        download_assets=bool(download_assets),
        asset_downloader=asset_downloader,
    )
    asset_candidates = [dict(item) for item in source_result.asset_candidates]
    return {
        'asset_candidates': asset_candidates,
        'asset_source_mode': source_result.asset_source_mode,
        'asset_ingestion_mode': source_result.asset_ingestion_mode,
        'asset_candidates_count': len(asset_candidates),
        'asset_candidate_source_types': [
            str(item.get('source_type') or '')
            for item in asset_candidates
            if str(item.get('source_type') or '').strip()
        ],
        'asset_source_errors': [str(item) for item in source_result.asset_source_errors if str(item).strip()],
        'asset_source_manifest_path': source_result.manifest_path,
        'asset_source_manifest_entry_id': source_result.manifest_entry_id,
        'asset_source_used_fixture_fallback': bool(source_result.used_fixture_fallback),
        'asset_download_enabled': bool(source_result.asset_download_enabled),
        'asset_download_attempted': bool(source_result.asset_download_attempted),
        'asset_download_status': str(source_result.asset_download_status or 'disabled'),
        'asset_download_error': source_result.asset_download_error,
        'downloaded_asset_count': int(source_result.downloaded_asset_count),
        'cached_asset_count': int(source_result.cached_asset_count),
        'failed_asset_count': int(source_result.failed_asset_count),
    }


def selected_asset_remote_cache_fields(selected_asset: dict[str, Any] | None) -> tuple[str | None, str | None, str | None]:
    if not isinstance(selected_asset, dict):
        return None, None, None
    metadata = dict(selected_asset.get('metadata')) if isinstance(selected_asset.get('metadata'), dict) else {}
    remote_url = str(selected_asset.get('remote_url') or metadata.get('remote_url') or '').strip() or None
    cache_path = str(selected_asset.get('cache_path') or metadata.get('cache_path') or '').strip() or None
    cache_status = str(selected_asset.get('cache_status') or metadata.get('cache_status') or '').strip() or None
    return remote_url, cache_path, cache_status


def normalize_decision_asset_reject_reason(
    *,
    decision_asset_used: bool,
    raw_reason: Any,
    selected_asset: dict[str, Any] | None,
) -> str | None:
    if decision_asset_used:
        return None
    remote_url, _cache_path, cache_status = selected_asset_remote_cache_fields(selected_asset)
    if remote_url and str(cache_status or '').strip().lower() != 'cached':
        return 'remote_not_cached'
    value = str(raw_reason or '').strip()
    return value or None


class BrokenComfyUIProvider:
    provider_name = 'comfyui'

    def __init__(self, *, base_url: str, failure_mode: str = 'timeout', enabled: bool = True) -> None:
        self.base_url = base_url
        self.failure_mode = failure_mode
        self.enabled = enabled
        self.ai_source_mode = 'pure_generation'
        self.reference_assets_enabled = False
        self.workflow_mode = 'scene_content_pure'
        self.generated_image_origin = 'comfyui_runtime_unavailable'

    def resolve(self, request: ImageResolutionRequest) -> None:
        _ = request
        return None


class QualityRejectComfyUIProvider:
    provider_name = 'comfyui'

    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self.ai_source_mode = 'pure_generation'
        self.reference_assets_enabled = False
        self.workflow_mode = 'scene_content_pure'
        self.generated_image_origin = 'synthetic_quality_reject'

    def resolve(self, request: ImageResolutionRequest) -> ResolvedImage:
        width = min(64, max(1, int(request.image_size[0] // 8)))
        height = min(64, max(1, int(request.image_size[1] // 8)))
        image = Image.new('RGB', (width, height), '#101820')
        return ResolvedImage(
            image=image,
            metadata={
                'selected_source': 'ai',
                'provider_name': self.provider_name,
                'provider': 'comfyui',
                'status': 'success',
                'simulated_quality': 'reject',
                'ai_source_mode': 'pure_generation',
                'reference_assets_used': False,
                'reference_asset_count': 0,
                'generated_image_origin': 'synthetic_quality_reject',
                'workflow_mode': 'scene_content_pure',
                'prompt_intent': 'scene_content_image',
                'prompt_summary': 'scene-only game-world visual for AI Provider Smoke: simulated pure generation quality reject',
                'negative_prompt_summary': 'no ui, interface, overlay, text, banner, poster, card frame',
            },
        )


def infer_ai_source_mode(*, ai_provider: Any, resolved_metadata: dict[str, Any], final_source: str) -> str:
    if final_source == 'asset':
        return 'official_asset'
    value = str(resolved_metadata.get('ai_source_mode') or '').strip()
    if value:
        return value
    provider_value = str(getattr(ai_provider, 'ai_source_mode', '') or '').strip()
    if provider_value:
        return provider_value
    return 'fallback' if final_source != 'ai' else 'unknown'


def infer_reference_assets_used(*, ai_provider: Any, resolved_metadata: dict[str, Any]) -> bool:
    if 'reference_assets_used' in resolved_metadata:
        return bool(resolved_metadata.get('reference_assets_used'))
    return bool(getattr(ai_provider, 'reference_assets_enabled', False))


def infer_reference_asset_count(*, resolved_metadata: dict[str, Any], reference_assets_used: bool) -> int:
    if 'reference_asset_count' in resolved_metadata:
        try:
            return int(resolved_metadata.get('reference_asset_count') or 0)
        except (TypeError, ValueError):
            return 0
    return 1 if reference_assets_used else 0


def infer_generated_image_origin(*, ai_provider: Any, resolved_metadata: dict[str, Any], final_source: str) -> str:
    if final_source == 'asset':
        return 'local_official_asset'
    value = str(resolved_metadata.get('generated_image_origin') or '').strip()
    if value:
        return value
    provider_value = str(getattr(ai_provider, 'generated_image_origin', '') or '').strip()
    if provider_value:
        return provider_value
    return 'fallback_placeholder' if final_source != 'ai' else 'unknown'


def infer_workflow_mode(*, ai_provider: Any, resolved_metadata: dict[str, Any], final_source: str) -> str | None:
    if final_source == 'asset':
        return 'official_asset_bridge'
    value = str(resolved_metadata.get('workflow_mode') or '').strip()
    if value:
        return value
    provider_value = str(getattr(ai_provider, 'workflow_mode', '') or '').strip()
    if provider_value:
        return provider_value
    return 'fallback' if final_source != 'ai' else None


def infer_comfyui_diagnostic(*, ai_provider: Any, resolved_metadata: dict[str, Any], key: str, default: Any = None) -> Any:
    if key in resolved_metadata:
        return resolved_metadata.get(key)
    latest = getattr(ai_provider, 'latest_diagnostics', None)
    if isinstance(latest, dict) and key in latest:
        return latest.get(key)
    return default


def infer_prompt_variant(*, ai_provider: Any, resolved_metadata: dict[str, Any]) -> str:
    value = str(resolved_metadata.get('prompt_variant') or '').strip()
    if value:
        return value
    provider_value = str(getattr(ai_provider, 'prompt_variant', '') or '').strip()
    if provider_value:
        return provider_value
    return DEFAULT_PROMPT_VARIANT


def infer_prompt_intent(*, ai_provider: Any, resolved_metadata: dict[str, Any], prompt_variant: str) -> str:
    value = str(resolved_metadata.get('prompt_intent') or '').strip()
    if value:
        return value
    provider_value = str(getattr(ai_provider, 'prompt_intent', '') or '').strip()
    if provider_value:
        return provider_value
    normalized = str(prompt_variant or DEFAULT_PROMPT_VARIANT).strip().lower()
    if normalized in VALID_PROMPT_VARIANTS:
        return normalized
    return DEFAULT_PROMPT_VARIANT


def normalize_game_set(value: object) -> str:
    normalized = str(value or DEFAULT_GAME_SET).strip().lower() or DEFAULT_GAME_SET
    if normalized in VALID_GAME_SETS:
        return normalized
    return DEFAULT_GAME_SET


def resolve_selected_game_set(*, game_set: str, game_eval: bool) -> str:
    normalized = normalize_game_set(game_set)
    if game_eval and normalized == DEFAULT_GAME_SET:
        return DEFAULT_EVAL_GAME_SET
    return normalized


def resolve_game_inputs(game_set: str) -> list[dict[str, Any]]:
    normalized = normalize_game_set(game_set)
    if normalized == 'minimal':
        return [dict(item) for item in MINIMAL_SMOKE_GAMES]
    return [dict(DEFAULT_SMOKE_GAME)]


def configure_engine_for_scenario(
    engine: YotoCardEngineV4,
    scenario: str,
    *,
    prompt_variant: str = DEFAULT_PROMPT_VARIANT,
) -> dict[str, Any]:
    if scenario == 'broken_comfyui':
        engine.image_provider_mode = 'ai_first'
        engine.comfyui_enabled = True
        engine.comfyui_url = BROKEN_COMFYUI_URL
        engine.image_resolver.ai_provider = BrokenComfyUIProvider(base_url=BROKEN_COMFYUI_URL, failure_mode='timeout')
        if engine.image_resolver.ai_provider is not None:
            engine.image_resolver.ai_provider.enabled = True
        return {
            'scenario': scenario,
            'requested_ai_provider': 'comfyui',
            'requested_ai_source_mode': 'pure_generation',
            'requested_mode': engine.image_provider_mode,
            'requested_comfyui_url': engine.comfyui_url,
            'requested_prompt_variant': prompt_variant,
            'simulated_ai_failure': 'timeout',
            'config_source': 'smoke_scenario_override',
        }
    if scenario == 'quality_reject':
        engine.image_provider_mode = 'ai_first'
        engine.comfyui_enabled = True
        engine.comfyui_url = BROKEN_COMFYUI_URL
        engine.image_resolver.ai_provider = QualityRejectComfyUIProvider(enabled=True)
        return {
            'scenario': scenario,
            'requested_ai_provider': 'comfyui',
            'requested_ai_source_mode': 'pure_generation',
            'requested_mode': engine.image_provider_mode,
            'requested_comfyui_url': engine.comfyui_url,
            'requested_prompt_variant': prompt_variant,
            'simulated_ai_failure': 'quality_reject',
            'config_source': 'smoke_scenario_override',
        }
    if scenario == 'pure_generation':
        rendering = load_rendering_config(REPO_ROOT)
        engine.image_provider_mode = 'ai_first'
        engine.comfyui_enabled = True
        engine.comfyui_url = rendering.comfyui_url
        engine.image_resolver.ai_provider = ComfyUIImageProvider(
            enabled=True,
            base_url=engine.comfyui_url,
            reference_assets_enabled=False,
            prompt_variant=prompt_variant,
            timeout_seconds=90.0,
        )
        return {
            'scenario': scenario,
            'requested_ai_provider': 'comfyui',
            'requested_ai_source_mode': 'pure_generation',
            'requested_mode': engine.image_provider_mode,
            'requested_comfyui_url': engine.comfyui_url,
            'requested_comfyui_checkpoint': rendering.comfyui_checkpoint,
            'requested_prompt_variant': prompt_variant,
            'config_source': 'smoke_pure_generation_override',
        }
    if scenario == 'current_env':
        rendering = load_rendering_config(REPO_ROOT)
        engine.image_provider_mode = rendering.image_provider_mode
        engine.comfyui_enabled = rendering.comfyui_enabled
        engine.comfyui_url = rendering.comfyui_url
        engine.image_resolver.ai_provider = ComfyUIImageProvider(
            enabled=rendering.comfyui_enabled,
            base_url=engine.comfyui_url,
            reference_assets_enabled=True,
            prompt_variant=prompt_variant,
        )
        return {
            'scenario': scenario,
            'requested_ai_provider': str(getattr(engine.image_resolver.ai_provider, 'provider_name', 'ai')),
            'requested_ai_source_mode': 'reference_assisted',
            'requested_mode': engine.image_provider_mode,
            'requested_comfyui_url': engine.comfyui_url,
            'requested_comfyui_checkpoint': rendering.comfyui_checkpoint,
            'requested_prompt_variant': prompt_variant,
            'config_source': '.env' if (REPO_ROOT / '.env').exists() else 'dealbot.settings defaults',
        }
    raise ValueError(f'Unsupported scenario: {scenario}')


def run_scenario(
    *,
    scenario: str,
    output_root: Path = OUTPUT_ROOT,
    prompt_variant: str = DEFAULT_PROMPT_VARIANT,
    game_input: dict[str, Any] | None = None,
    game_set: str = DEFAULT_GAME_SET,
    seed: int | None = None,
    game_eval: bool = False,
    result_root: Path | None = None,
    run_key: str | None = None,
    download_assets: bool = False,
    asset_downloader: Any | None = None,
) -> dict[str, Any]:
    normalized_prompt_variant = str(prompt_variant or DEFAULT_PROMPT_VARIANT).strip().lower() or DEFAULT_PROMPT_VARIANT
    if normalized_prompt_variant not in VALID_PROMPT_VARIANTS:
        raise ValueError(f'Unsupported prompt variant: {prompt_variant}')
    normalized_game_set = resolve_selected_game_set(game_set=game_set, game_eval=game_eval)
    if seed is not None and int(seed) < 1:
        raise ValueError(f'Unsupported seed: {seed}')
    selected_game = dict(DEFAULT_SMOKE_GAME if game_input is None else game_input)
    game_slug = str(selected_game.get('slug') or 'ai_card_smoke').strip() or 'ai_card_smoke'
    offer_type = str(selected_game.get('offer_type') or '').strip() or None
    asset_source_payload = resolve_asset_candidates_for_game(
        selected_game,
        download_assets=download_assets,
        asset_downloader=asset_downloader,
    )
    asset_candidates = [dict(item) for item in asset_source_payload['asset_candidates']]
    asset_source_mode = str(asset_source_payload.get('asset_source_mode') or 'empty')
    asset_ingestion_mode = str(asset_source_payload.get('asset_ingestion_mode') or 'empty')
    asset_candidates_count = int(asset_source_payload.get('asset_candidates_count') or 0)
    asset_candidate_source_types = [
        str(item)
        for item in asset_source_payload.get('asset_candidate_source_types') or []
        if str(item).strip()
    ]
    asset_source_errors = [
        str(item)
        for item in asset_source_payload.get('asset_source_errors') or []
        if str(item).strip()
    ]
    asset_source_manifest_path = asset_source_payload.get('asset_source_manifest_path')
    asset_source_manifest_entry_id = asset_source_payload.get('asset_source_manifest_entry_id')
    asset_source_used_fixture_fallback = bool(
        asset_source_payload.get('asset_source_used_fixture_fallback', False)
    )
    asset_download_enabled = bool(asset_source_payload.get('asset_download_enabled', False))
    asset_download_attempted = bool(asset_source_payload.get('asset_download_attempted', False))
    asset_download_status = str(asset_source_payload.get('asset_download_status') or 'disabled')
    asset_download_error = asset_source_payload.get('asset_download_error')
    downloaded_asset_count = int(asset_source_payload.get('downloaded_asset_count') or 0)
    cached_asset_count = int(asset_source_payload.get('cached_asset_count') or 0)
    failed_asset_count = int(asset_source_payload.get('failed_asset_count') or 0)
    run_key = run_key or datetime.utcnow().strftime('%Y%m%dT%H%M%S%fZ')
    seed_value = int(seed) if seed is not None else None
    if result_root is not None:
        run_root = result_root
    elif game_eval:
        seed_label = f'seed_{seed_value or 1}'
        run_root = output_root / 'ai_eval' / game_slug / normalized_prompt_variant / seed_label
    else:
        run_root = output_root / f'ai_card_smoke_{scenario}_{game_slug}_{normalized_prompt_variant}_{run_key}'
    cards_dir = run_root / 'cards'
    cards_dir.mkdir(parents=True, exist_ok=True)

    missing_artwork_path = run_root / 'missing_artwork.png'
    engine = YotoCardEngineV4(cards_dir)
    scenario_metadata = configure_engine_for_scenario(engine, scenario, prompt_variant=normalized_prompt_variant)
    data = build_smoke_data(run_key=run_key, artwork_path=missing_artwork_path, game_input=selected_game, seed=seed_value)
    game_tags = [str(item) for item in data.tags or [] if str(item).strip()]
    scenario_metadata['game_set'] = normalized_game_set
    scenario_metadata['game_eval'] = bool(game_eval)
    scenario_metadata['game_slug'] = game_slug
    scenario_metadata['game_title'] = data.title
    scenario_metadata['genre'] = data.genre
    scenario_metadata['tags'] = list(game_tags)
    scenario_metadata['short_description'] = data.short_description
    scenario_metadata['offer_type'] = offer_type
    scenario_metadata['asset_source_mode'] = asset_source_mode
    scenario_metadata['asset_ingestion_mode'] = asset_ingestion_mode
    scenario_metadata['asset_candidates_count'] = asset_candidates_count
    scenario_metadata['asset_candidate_source_types'] = list(asset_candidate_source_types)
    scenario_metadata['asset_candidates'] = json_ready(asset_candidates)
    scenario_metadata['asset_source_errors'] = list(asset_source_errors)
    scenario_metadata['asset_source_manifest_path'] = asset_source_manifest_path
    scenario_metadata['asset_source_manifest_entry_id'] = asset_source_manifest_entry_id
    scenario_metadata['asset_source_used_fixture_fallback'] = asset_source_used_fixture_fallback
    scenario_metadata['asset_download_enabled'] = asset_download_enabled
    scenario_metadata['asset_download_attempted'] = asset_download_attempted
    scenario_metadata['asset_download_status'] = asset_download_status
    scenario_metadata['asset_download_error'] = asset_download_error
    scenario_metadata['downloaded_asset_count'] = downloaded_asset_count
    scenario_metadata['cached_asset_count'] = cached_asset_count
    scenario_metadata['failed_asset_count'] = failed_asset_count
    scenario_metadata['seed'] = seed_value
    cover_decision_payload = json_ready(
        build_cover_decision(
            game_title=data.title,
            genre=data.genre,
            tags=game_tags,
            short_description=data.short_description,
            offer_type=offer_type,
            asset_candidates=asset_candidates,
            current_price=data.current_price,
            old_price=data.old_price,
        ).to_dict()
    )
    cover_decision_selected_asset = (
        dict(cover_decision_payload.get('selected_asset'))
        if isinstance(cover_decision_payload.get('selected_asset'), dict)
        else None
    )
    cover_decision_rejected_assets = [
        dict(item)
        for item in cover_decision_payload.get('rejected_assets') or []
        if isinstance(item, dict)
    ]
    cover_decision_decision_trace = (
        dict(cover_decision_payload.get('decision_trace'))
        if isinstance(cover_decision_payload.get('decision_trace'), dict)
        else {}
    )
    cover_decision_selected_strategy = (
        dict(cover_decision_decision_trace.get('selected_strategy'))
        if isinstance(cover_decision_decision_trace.get('selected_strategy'), dict)
        else {}
    )
    cover_decision_asset_summary = (
        dict(cover_decision_decision_trace.get('asset_summary'))
        if isinstance(cover_decision_decision_trace.get('asset_summary'), dict)
        else {}
    )
    cover_decision_readability_score = (
        cover_decision_selected_asset.get('readability_score')
        if cover_decision_selected_asset is not None
        else None
    )
    cover_decision_focus_score = (
        cover_decision_selected_asset.get('focus_score')
        if cover_decision_selected_asset is not None
        else None
    )
    cover_decision_asset_metadata_enriched = bool(
        cover_decision_selected_asset.get('asset_metadata_enriched', False)
        if cover_decision_selected_asset is not None
        else False
    )
    cover_decision_orientation = (
        cover_decision_selected_asset.get('orientation')
        if cover_decision_selected_asset is not None
        else None
    )
    cover_decision_aspect_ratio = (
        cover_decision_selected_asset.get('aspect_ratio')
        if cover_decision_selected_asset is not None
        else None
    )
    cover_decision_estimated_focus = (
        cover_decision_selected_asset.get('estimated_focus')
        if cover_decision_selected_asset is not None
        else None
    )
    cover_decision_estimated_subject_scale = (
        cover_decision_selected_asset.get('estimated_subject_scale')
        if cover_decision_selected_asset is not None
        else None
    )
    cover_decision_estimated_visual_density = (
        cover_decision_selected_asset.get('estimated_visual_density')
        if cover_decision_selected_asset is not None
        else None
    )
    cover_decision_composition_bias = (
        cover_decision_selected_asset.get('composition_bias')
        if cover_decision_selected_asset is not None
        else None
    )
    cover_decision_source_strength = (
        cover_decision_selected_asset.get('source_strength')
        if cover_decision_selected_asset is not None
        else None
    )
    cover_decision_official_asset_score_boost = (
        cover_decision_selected_asset.get('official_asset_score_boost')
        if cover_decision_selected_asset is not None
        else None
    )
    cover_decision_scoring_reason = (
        cover_decision_selected_asset.get('scoring_reason')
        if cover_decision_selected_asset is not None
        else None
    )
    cover_decision_rejection_reason = (
        cover_decision_selected_asset.get('rejection_reason')
        if cover_decision_selected_asset is not None
        else None
    )
    cover_decision_ai_fallback_reason = cover_decision_selected_strategy.get('ai_fallback_reason')
    cover_decision_card_type = cover_decision_payload.get('card_type')
    cover_decision_card_type_reason = cover_decision_payload.get('card_type_reason')
    cover_decision_card_strategy_version = cover_decision_payload.get('card_strategy_version')
    cover_decision_card_type_inputs = (
        dict(cover_decision_payload.get('card_type_inputs'))
        if isinstance(cover_decision_payload.get('card_type_inputs'), dict)
        else {}
    )
    data.cover_decision = dict(cover_decision_payload)
    request = build_image_request(engine, data)
    resolver_trace: dict[str, Any] | None = None
    resolved_metadata: dict[str, Any] = {}
    original_resolve = engine.image_resolver.resolve

    def capture_resolve(image_request: ImageResolutionRequest):
        nonlocal resolver_trace, resolved_metadata
        resolved = original_resolve(image_request)
        resolver_trace = json_ready(resolved.metadata.get('resolver_trace'))
        resolved_metadata = json_ready(dict(resolved.metadata))
        return resolved

    engine.image_resolver.resolve = capture_resolve
    try:
        render_result = engine.render_card(data)
    finally:
        engine.image_resolver.resolve = original_resolve
    output_image_path = resolve_output_png_path(
        image_path=render_result.image_path,
        cards_dir=cards_dir,
    )

    diagnostics = json_ready(asdict(render_result.diagnostics))
    provider_metadata = {
        'selected_source': diagnostics.get('selected_source'),
        'decision_reason': diagnostics.get('decision_reason'),
        'image_provider_mode': diagnostics.get('image_provider_mode'),
        'image_priority': diagnostics.get('image_priority'),
        'image_pipeline_version': diagnostics.get('image_pipeline_version'),
        'ai_attempted': diagnostics.get('ai_attempted'),
        'ai_succeeded': diagnostics.get('ai_succeeded'),
        'resolver_trace': resolver_trace,
        'request': json_ready(asdict(request)),
        'game_set': normalized_game_set,
        'game_eval': bool(game_eval),
        'game_slug': game_slug,
        'game_title': data.title,
        'genre': data.genre,
        'tags': list(game_tags),
        'short_description': data.short_description,
        'offer_type': offer_type,
        'asset_source_mode': asset_source_mode,
        'asset_ingestion_mode': asset_ingestion_mode,
        'asset_candidates_count': asset_candidates_count,
        'asset_candidate_source_types': list(asset_candidate_source_types),
        'asset_candidates': json_ready(asset_candidates),
        'asset_source_errors': list(asset_source_errors),
        'asset_source_manifest_path': asset_source_manifest_path,
        'asset_source_manifest_entry_id': asset_source_manifest_entry_id,
        'asset_source_used_fixture_fallback': asset_source_used_fixture_fallback,
        'seed': seed_value,
        'cover_decision': cover_decision_payload,
        'cover_decision_asset_metadata_enriched': cover_decision_asset_metadata_enriched,
        'cover_decision_orientation': cover_decision_orientation,
        'cover_decision_aspect_ratio': cover_decision_aspect_ratio,
        'cover_decision_estimated_focus': cover_decision_estimated_focus,
        'cover_decision_estimated_subject_scale': cover_decision_estimated_subject_scale,
        'cover_decision_estimated_visual_density': cover_decision_estimated_visual_density,
        'cover_decision_composition_bias': cover_decision_composition_bias,
        'cover_decision_source_strength': cover_decision_source_strength,
        'cover_decision_official_asset_score_boost': cover_decision_official_asset_score_boost,
        'cover_decision_scoring_reason': cover_decision_scoring_reason,
        'cover_decision_rejection_reason': cover_decision_rejection_reason,
    }
    selected_source = str(provider_metadata.get('selected_source') or 'unknown')
    provider = infer_provider(engine, selected_source)
    final_source = infer_final_source(selected_source)
    ai_attempted = bool(provider_metadata.get('ai_attempted', False))
    ai_succeeded = bool(provider_metadata.get('ai_succeeded', False))
    ai_provider = getattr(engine.image_resolver, 'ai_provider', None)
    provider_attempted = infer_provider_attempted(ai_provider=ai_provider, ai_attempted=ai_attempted)
    fallback_used = infer_fallback_used(final_source)
    fallback_reason = infer_fallback_reason(
        fallback_used=fallback_used,
        decision_reason=diagnostics.get('decision_reason'),
    )
    quality_checked = bool(resolved_metadata.get('quality_checked', False))
    quality_passed = bool(resolved_metadata.get('quality_passed', False))
    quality_reject_reason = resolved_metadata.get('quality_reject_reason')
    quality_metrics = resolved_metadata.get('quality_metrics')
    actual_image_source_type = resolved_metadata.get('actual_image_source_type')
    actual_image_path_or_url = resolved_metadata.get('actual_image_path_or_url')
    decision_asset_used = bool(resolved_metadata.get('decision_asset_used', False))
    decision_asset_use_reason = resolved_metadata.get('decision_asset_use_reason')
    decision_asset_reject_reason = normalize_decision_asset_reject_reason(
        decision_asset_used=decision_asset_used,
        raw_reason=resolved_metadata.get('decision_asset_reject_reason'),
        selected_asset=cover_decision_selected_asset,
    )
    decision_asset_matches_actual_source = bool(
        resolved_metadata.get('decision_asset_matches_actual_source', False)
    )
    selected_asset_remote_url, selected_asset_cache_path, selected_asset_cache_status = (
        selected_asset_remote_cache_fields(cover_decision_selected_asset)
    )
    prompt_variant_value = infer_prompt_variant(
        ai_provider=ai_provider,
        resolved_metadata=resolved_metadata,
    )
    prompt_intent = infer_prompt_intent(
        ai_provider=ai_provider,
        resolved_metadata=resolved_metadata,
        prompt_variant=prompt_variant_value,
    )
    prompt_summary = resolved_metadata.get('prompt_summary')
    negative_prompt_summary = resolved_metadata.get('negative_prompt_summary')
    grounding_used = bool(resolved_metadata.get('grounding_used', False))
    grounding_fields_used = [str(item) for item in resolved_metadata.get('grounding_fields_used') or [] if str(item).strip()]
    grounding_summary = resolved_metadata.get('grounding_summary')
    visual_intent = resolved_metadata.get('visual_intent')
    visual_intent_reason = resolved_metadata.get('visual_intent_reason')
    variation_enabled = bool(resolved_metadata.get('variation_enabled', False))
    variation_slots = (
        json_ready(dict(resolved_metadata.get('variation_slots')))
        if isinstance(resolved_metadata.get('variation_slots'), dict)
        else None
    )
    variation_id = resolved_metadata.get('variation_id')
    variation_camera = resolved_metadata.get('variation_camera')
    variation_moment = resolved_metadata.get('variation_moment')
    variation_focus = resolved_metadata.get('variation_focus')
    variation_composition = resolved_metadata.get('variation_composition')
    external_seed = resolved_metadata.get('external_seed')
    ksampler_seed = resolved_metadata.get('ksampler_seed')
    seed_propagated = bool(resolved_metadata.get('seed_propagated', False))
    ai_source_mode = infer_ai_source_mode(
        ai_provider=ai_provider,
        resolved_metadata=resolved_metadata,
        final_source=final_source,
    )
    reference_assets_used = infer_reference_assets_used(
        ai_provider=ai_provider,
        resolved_metadata=resolved_metadata,
    )
    reference_asset_count = infer_reference_asset_count(
        resolved_metadata=resolved_metadata,
        reference_assets_used=reference_assets_used,
    )
    generated_image_origin = infer_generated_image_origin(
        ai_provider=ai_provider,
        resolved_metadata=resolved_metadata,
        final_source=final_source,
    )
    workflow_mode = infer_workflow_mode(
        ai_provider=ai_provider,
        resolved_metadata=resolved_metadata,
        final_source=final_source,
    )
    comfyui_stage = infer_comfyui_diagnostic(
        ai_provider=ai_provider,
        resolved_metadata=resolved_metadata,
        key='comfyui_stage',
    )
    comfyui_stage_success = bool(
        infer_comfyui_diagnostic(
            ai_provider=ai_provider,
            resolved_metadata=resolved_metadata,
            key='comfyui_stage_success',
            default=False,
        )
    )
    comfyui_failure_stage = infer_comfyui_diagnostic(
        ai_provider=ai_provider,
        resolved_metadata=resolved_metadata,
        key='comfyui_failure_stage',
    )
    comfyui_failure_reason = infer_comfyui_diagnostic(
        ai_provider=ai_provider,
        resolved_metadata=resolved_metadata,
        key='comfyui_failure_reason',
    )
    comfyui_http_status = infer_comfyui_diagnostic(
        ai_provider=ai_provider,
        resolved_metadata=resolved_metadata,
        key='comfyui_http_status',
    )
    comfyui_http_reason = infer_comfyui_diagnostic(
        ai_provider=ai_provider,
        resolved_metadata=resolved_metadata,
        key='comfyui_http_reason',
    )
    comfyui_prompt_id = infer_comfyui_diagnostic(
        ai_provider=ai_provider,
        resolved_metadata=resolved_metadata,
        key='comfyui_prompt_id',
    )
    comfyui_history_found = bool(
        infer_comfyui_diagnostic(
            ai_provider=ai_provider,
            resolved_metadata=resolved_metadata,
            key='comfyui_history_found',
            default=False,
        )
    )
    comfyui_image_ref_found = bool(
        infer_comfyui_diagnostic(
            ai_provider=ai_provider,
            resolved_metadata=resolved_metadata,
            key='comfyui_image_ref_found',
            default=False,
        )
    )
    comfyui_image_fetch_ok = bool(
        infer_comfyui_diagnostic(
            ai_provider=ai_provider,
            resolved_metadata=resolved_metadata,
            key='comfyui_image_fetch_ok',
            default=False,
        )
    )
    comfyui_response_body = infer_comfyui_diagnostic(
        ai_provider=ai_provider,
        resolved_metadata=resolved_metadata,
        key='comfyui_response_body',
    )
    comfyui_response_body_excerpt = infer_comfyui_diagnostic(
        ai_provider=ai_provider,
        resolved_metadata=resolved_metadata,
        key='comfyui_response_body_excerpt',
    )
    comfyui_submit_url = infer_comfyui_diagnostic(
        ai_provider=ai_provider,
        resolved_metadata=resolved_metadata,
        key='comfyui_submit_url',
    )
    comfyui_request_payload = infer_comfyui_diagnostic(
        ai_provider=ai_provider,
        resolved_metadata=resolved_metadata,
        key='comfyui_request_payload',
    )
    comfyui_request_payload_excerpt = infer_comfyui_diagnostic(
        ai_provider=ai_provider,
        resolved_metadata=resolved_metadata,
        key='comfyui_request_payload_excerpt',
    )
    comfyui_request_top_level_keys = infer_comfyui_diagnostic(
        ai_provider=ai_provider,
        resolved_metadata=resolved_metadata,
        key='comfyui_request_top_level_keys',
    )
    comfyui_request_node_count = infer_comfyui_diagnostic(
        ai_provider=ai_provider,
        resolved_metadata=resolved_metadata,
        key='comfyui_request_node_count',
    )
    comfyui_checkpoint_name = infer_comfyui_diagnostic(
        ai_provider=ai_provider,
        resolved_metadata=resolved_metadata,
        key='comfyui_checkpoint_name',
    )
    comfyui_checkpoint_requested = infer_comfyui_diagnostic(
        ai_provider=ai_provider,
        resolved_metadata=resolved_metadata,
        key='comfyui_checkpoint_requested',
    )
    comfyui_checkpoint_used = infer_comfyui_diagnostic(
        ai_provider=ai_provider,
        resolved_metadata=resolved_metadata,
        key='comfyui_checkpoint_used',
    )
    comfyui_checkpoint_available = infer_comfyui_diagnostic(
        ai_provider=ai_provider,
        resolved_metadata=resolved_metadata,
        key='comfyui_checkpoint_available',
    )
    comfyui_positive_prompt_summary = infer_comfyui_diagnostic(
        ai_provider=ai_provider,
        resolved_metadata=resolved_metadata,
        key='comfyui_positive_prompt_summary',
    )
    comfyui_negative_prompt_summary = infer_comfyui_diagnostic(
        ai_provider=ai_provider,
        resolved_metadata=resolved_metadata,
        key='comfyui_negative_prompt_summary',
    )
    outcome = classify_outcome(
        final_source=final_source,
        ai_attempted=ai_attempted,
        ai_succeeded=ai_succeeded,
        fallback_used=fallback_used,
    )
    visual_rescue = build_visual_rescue_decision(
        card_type=cover_decision_payload.get('card_type'),
        image_source_type=cover_decision_payload.get('image_source_type'),
        visual_intent_type=cover_decision_payload.get('visual_intent_type'),
        missing_visual_requirements=cover_decision_payload.get('missing_visual_requirements'),
        preferred_asset_families=cover_decision_payload.get('preferred_asset_families'),
        decision_reason=diagnostics.get('decision_reason'),
        decision_asset_reject_reason=decision_asset_reject_reason,
        final_source=final_source,
        outcome=outcome,
    ).to_dict()
    manifest = {
        'created_at': datetime.utcnow().isoformat() + 'Z',
        'scenario': scenario,
        'game_set': normalized_game_set,
        'game_eval': bool(game_eval),
        'game_slug': game_slug,
        'game_title': data.title,
        'genre': data.genre,
        'tags': list(game_tags),
        'short_description': data.short_description,
        'offer_type': offer_type,
        'asset_source_mode': asset_source_mode,
        'asset_ingestion_mode': asset_ingestion_mode,
        'asset_candidates_count': asset_candidates_count,
        'asset_candidate_source_types': list(asset_candidate_source_types),
        'asset_candidates': json_ready(asset_candidates),
        'asset_source_errors': list(asset_source_errors),
        'asset_source_manifest_path': asset_source_manifest_path,
        'asset_source_manifest_entry_id': asset_source_manifest_entry_id,
        'asset_source_used_fixture_fallback': asset_source_used_fixture_fallback,
        'asset_download_enabled': asset_download_enabled,
        'asset_download_attempted': asset_download_attempted,
        'asset_download_status': asset_download_status,
        'asset_download_error': asset_download_error,
        'downloaded_asset_count': downloaded_asset_count,
        'cached_asset_count': cached_asset_count,
        'failed_asset_count': failed_asset_count,
        'seed': seed_value,
        'run_root': str(run_root),
        'image_provider_mode': engine.image_provider_mode,
        'provider_attempted': provider_attempted,
        'provider': provider,
        'fallback_used': fallback_used,
        'fallback_reason': fallback_reason,
        'final_source': final_source,
        'outcome': outcome,
        'quality_checked': quality_checked,
        'quality_passed': quality_passed,
        'quality_reject_reason': quality_reject_reason,
        'quality_metrics': quality_metrics,
        'selected_asset_remote_url': selected_asset_remote_url,
        'selected_asset_cache_path': selected_asset_cache_path,
        'selected_asset_cache_status': selected_asset_cache_status,
        'actual_image_source_type': actual_image_source_type,
        'actual_image_path_or_url': actual_image_path_or_url,
        'decision_asset_used': decision_asset_used,
        'decision_asset_use_reason': decision_asset_use_reason,
        'decision_asset_reject_reason': decision_asset_reject_reason,
        'decision_asset_matches_actual_source': decision_asset_matches_actual_source,
        'ai_source_mode': ai_source_mode,
        'reference_assets_used': reference_assets_used,
        'reference_asset_count': reference_asset_count,
        'generated_image_origin': generated_image_origin,
        'workflow_mode': workflow_mode,
        'comfyui_stage': comfyui_stage,
        'comfyui_stage_success': comfyui_stage_success,
        'comfyui_failure_stage': comfyui_failure_stage,
        'comfyui_failure_reason': comfyui_failure_reason,
        'comfyui_http_status': comfyui_http_status,
        'comfyui_http_reason': comfyui_http_reason,
        'comfyui_prompt_id': comfyui_prompt_id,
        'comfyui_history_found': comfyui_history_found,
        'comfyui_image_ref_found': comfyui_image_ref_found,
        'comfyui_image_fetch_ok': comfyui_image_fetch_ok,
        'comfyui_response_body': comfyui_response_body,
        'comfyui_response_body_excerpt': comfyui_response_body_excerpt,
        'comfyui_submit_url': comfyui_submit_url,
        'comfyui_request_payload': comfyui_request_payload,
        'comfyui_request_payload_excerpt': comfyui_request_payload_excerpt,
        'comfyui_request_top_level_keys': comfyui_request_top_level_keys,
        'comfyui_request_node_count': comfyui_request_node_count,
        'comfyui_checkpoint_name': comfyui_checkpoint_name,
        'comfyui_checkpoint_requested': comfyui_checkpoint_requested,
        'comfyui_checkpoint_used': comfyui_checkpoint_used,
        'comfyui_checkpoint_available': comfyui_checkpoint_available,
        'comfyui_positive_prompt_summary': comfyui_positive_prompt_summary,
        'comfyui_negative_prompt_summary': comfyui_negative_prompt_summary,
        'prompt_variant': prompt_variant_value,
        'prompt_intent': prompt_intent,
        'prompt_summary': prompt_summary,
        'negative_prompt_summary': negative_prompt_summary,
        'grounding_used': grounding_used,
        'grounding_fields_used': grounding_fields_used,
        'grounding_summary': grounding_summary,
        'visual_intent': visual_intent,
        'visual_intent_reason': visual_intent_reason,
        'visual_rescue': visual_rescue,
        'rescue_needed': bool(visual_rescue.get('rescue_needed', False)),
        'rescue_reason': visual_rescue.get('rescue_reason'),
        'rescue_type': visual_rescue.get('rescue_type'),
        'rescue_preferred_asset_families': [
            str(item)
            for item in visual_rescue.get('rescue_preferred_asset_families') or []
            if str(item).strip()
        ],
        'rescue_blockers': [
            str(item)
            for item in visual_rescue.get('rescue_blockers') or []
            if str(item).strip()
        ],
        'rescue_version': visual_rescue.get('rescue_version'),
        'variation_enabled': variation_enabled,
        'variation_id': variation_id,
        'variation_slots': variation_slots,
        'variation_camera': variation_camera,
        'variation_moment': variation_moment,
        'variation_focus': variation_focus,
        'variation_composition': variation_composition,
        'external_seed': external_seed,
        'ksampler_seed': ksampler_seed,
        'seed_propagated': seed_propagated,
        'cover_decision': cover_decision_payload,
        'cover_decision_genre_cluster': cover_decision_payload.get('genre_cluster'),
        'cover_decision_visual_type': cover_decision_payload.get('visual_type'),
        'cover_decision_image_source_type': cover_decision_payload.get('image_source_type'),
        'cover_decision_layout_type': cover_decision_payload.get('layout_type'),
        'cover_decision_use_ai': bool(cover_decision_payload.get('use_ai', False)),
        'cover_decision_decision_reason': cover_decision_payload.get('decision_reason'),
        'cover_decision_decision_trace': cover_decision_decision_trace,
        'cover_decision_card_type': cover_decision_card_type,
        'cover_decision_card_type_reason': cover_decision_card_type_reason,
        'cover_decision_card_strategy_version': cover_decision_card_strategy_version,
        'cover_decision_card_type_inputs': cover_decision_card_type_inputs,
        'cover_decision_readability_score': cover_decision_readability_score,
        'cover_decision_focus_score': cover_decision_focus_score,
        'cover_decision_asset_metadata_enriched': cover_decision_asset_metadata_enriched,
        'cover_decision_orientation': cover_decision_orientation,
        'cover_decision_aspect_ratio': cover_decision_aspect_ratio,
        'cover_decision_estimated_focus': cover_decision_estimated_focus,
        'cover_decision_estimated_subject_scale': cover_decision_estimated_subject_scale,
        'cover_decision_estimated_visual_density': cover_decision_estimated_visual_density,
        'cover_decision_composition_bias': cover_decision_composition_bias,
        'cover_decision_source_strength': cover_decision_source_strength,
        'cover_decision_official_asset_score_boost': cover_decision_official_asset_score_boost,
        'cover_decision_scoring_reason': cover_decision_scoring_reason,
        'cover_decision_rejection_reason': cover_decision_rejection_reason,
        'cover_decision_selected_asset': cover_decision_selected_asset,
        'cover_decision_rejected_assets': cover_decision_rejected_assets,
        'cover_decision_ai_fallback_reason': cover_decision_ai_fallback_reason,
        'cover_decision_official_assets_available': bool(
            cover_decision_asset_summary.get('official_assets_available', False)
        ),
        'cover_decision_official_assets_rejected_count': int(
            cover_decision_asset_summary.get('official_assets_rejected_count') or 0
        ),
        'cover_decision_rejection_reasons': [
            str(item)
            for item in cover_decision_selected_strategy.get('rejection_reasons') or []
            if str(item).strip()
        ],
        'selected_source': selected_source,
        'decision_reason': diagnostics.get('decision_reason'),
        'ai_attempted': ai_attempted,
        'ai_succeeded': ai_succeeded,
        'ai_provider_class': type(ai_provider).__name__ if ai_provider is not None else None,
        'ai_provider_enabled': bool(getattr(ai_provider, 'enabled', False)) if ai_provider is not None else False,
        'effective_config': {
            'image_provider_mode': engine.image_provider_mode,
            'comfyui_enabled': engine.comfyui_enabled,
            'comfyui_url': engine.comfyui_url,
        },
        'scenario_metadata': scenario_metadata,
        'provider_metadata': provider_metadata,
        'resolver_trace': resolver_trace,
        'diagnostics': diagnostics,
        'output_path': str(output_image_path),
        'image_path': str(output_image_path),
        'review_image_path': None,
    }
    manifest['provider_metadata']['provider_attempted'] = provider_attempted
    manifest['provider_metadata']['provider'] = provider
    manifest['provider_metadata']['fallback_used'] = fallback_used
    manifest['provider_metadata']['fallback_reason'] = fallback_reason
    manifest['provider_metadata']['final_source'] = final_source
    manifest['provider_metadata']['quality_checked'] = quality_checked
    manifest['provider_metadata']['quality_passed'] = quality_passed
    manifest['provider_metadata']['quality_reject_reason'] = quality_reject_reason
    manifest['provider_metadata']['quality_metrics'] = quality_metrics
    manifest['provider_metadata']['actual_image_source_type'] = actual_image_source_type
    manifest['provider_metadata']['actual_image_path_or_url'] = actual_image_path_or_url
    manifest['provider_metadata']['decision_asset_used'] = decision_asset_used
    manifest['provider_metadata']['decision_asset_use_reason'] = decision_asset_use_reason
    manifest['provider_metadata']['decision_asset_reject_reason'] = decision_asset_reject_reason
    manifest['provider_metadata']['decision_asset_matches_actual_source'] = decision_asset_matches_actual_source
    manifest['provider_metadata']['ai_source_mode'] = ai_source_mode
    manifest['provider_metadata']['reference_assets_used'] = reference_assets_used
    manifest['provider_metadata']['reference_asset_count'] = reference_asset_count
    manifest['provider_metadata']['generated_image_origin'] = generated_image_origin
    manifest['provider_metadata']['workflow_mode'] = workflow_mode
    manifest['provider_metadata']['comfyui_stage'] = comfyui_stage
    manifest['provider_metadata']['comfyui_stage_success'] = comfyui_stage_success
    manifest['provider_metadata']['comfyui_failure_stage'] = comfyui_failure_stage
    manifest['provider_metadata']['comfyui_failure_reason'] = comfyui_failure_reason
    manifest['provider_metadata']['comfyui_http_status'] = comfyui_http_status
    manifest['provider_metadata']['comfyui_http_reason'] = comfyui_http_reason
    manifest['provider_metadata']['comfyui_prompt_id'] = comfyui_prompt_id
    manifest['provider_metadata']['comfyui_history_found'] = comfyui_history_found
    manifest['provider_metadata']['comfyui_image_ref_found'] = comfyui_image_ref_found
    manifest['provider_metadata']['comfyui_image_fetch_ok'] = comfyui_image_fetch_ok
    manifest['provider_metadata']['comfyui_response_body'] = comfyui_response_body
    manifest['provider_metadata']['comfyui_response_body_excerpt'] = comfyui_response_body_excerpt
    manifest['provider_metadata']['comfyui_submit_url'] = comfyui_submit_url
    manifest['provider_metadata']['comfyui_request_payload'] = comfyui_request_payload
    manifest['provider_metadata']['comfyui_request_payload_excerpt'] = comfyui_request_payload_excerpt
    manifest['provider_metadata']['comfyui_request_top_level_keys'] = comfyui_request_top_level_keys
    manifest['provider_metadata']['comfyui_request_node_count'] = comfyui_request_node_count
    manifest['provider_metadata']['comfyui_checkpoint_name'] = comfyui_checkpoint_name
    manifest['provider_metadata']['comfyui_checkpoint_requested'] = comfyui_checkpoint_requested
    manifest['provider_metadata']['comfyui_checkpoint_used'] = comfyui_checkpoint_used
    manifest['provider_metadata']['comfyui_checkpoint_available'] = comfyui_checkpoint_available
    manifest['provider_metadata']['comfyui_positive_prompt_summary'] = comfyui_positive_prompt_summary
    manifest['provider_metadata']['comfyui_negative_prompt_summary'] = comfyui_negative_prompt_summary
    manifest['provider_metadata']['prompt_variant'] = prompt_variant_value
    manifest['provider_metadata']['prompt_intent'] = prompt_intent
    manifest['provider_metadata']['prompt_summary'] = prompt_summary
    manifest['provider_metadata']['negative_prompt_summary'] = negative_prompt_summary
    manifest['provider_metadata']['grounding_used'] = grounding_used
    manifest['provider_metadata']['grounding_fields_used'] = grounding_fields_used
    manifest['provider_metadata']['grounding_summary'] = grounding_summary
    manifest['provider_metadata']['visual_intent'] = visual_intent
    manifest['provider_metadata']['visual_intent_reason'] = visual_intent_reason
    manifest['provider_metadata']['visual_rescue'] = visual_rescue
    manifest['provider_metadata']['variation_enabled'] = variation_enabled
    manifest['provider_metadata']['variation_id'] = variation_id
    manifest['provider_metadata']['variation_slots'] = variation_slots
    manifest['provider_metadata']['variation_camera'] = variation_camera
    manifest['provider_metadata']['variation_moment'] = variation_moment
    manifest['provider_metadata']['variation_focus'] = variation_focus
    manifest['provider_metadata']['variation_composition'] = variation_composition
    manifest['provider_metadata']['external_seed'] = external_seed
    manifest['provider_metadata']['ksampler_seed'] = ksampler_seed
    manifest['provider_metadata']['seed_propagated'] = seed_propagated
    manifest['provider_metadata']['game_set'] = normalized_game_set
    manifest['provider_metadata']['game_eval'] = bool(game_eval)
    manifest['provider_metadata']['game_slug'] = game_slug
    manifest['provider_metadata']['game_title'] = data.title
    manifest['provider_metadata']['genre'] = data.genre
    manifest['provider_metadata']['tags'] = list(game_tags)
    manifest['provider_metadata']['short_description'] = data.short_description
    manifest['provider_metadata']['offer_type'] = offer_type
    manifest['provider_metadata']['asset_source_mode'] = asset_source_mode
    manifest['provider_metadata']['asset_ingestion_mode'] = asset_ingestion_mode
    manifest['provider_metadata']['asset_candidates_count'] = asset_candidates_count
    manifest['provider_metadata']['asset_candidate_source_types'] = list(asset_candidate_source_types)
    manifest['provider_metadata']['asset_candidates'] = json_ready(asset_candidates)
    manifest['provider_metadata']['asset_source_errors'] = list(asset_source_errors)
    manifest['provider_metadata']['asset_source_manifest_path'] = asset_source_manifest_path
    manifest['provider_metadata']['asset_source_manifest_entry_id'] = asset_source_manifest_entry_id
    manifest['provider_metadata']['asset_source_used_fixture_fallback'] = asset_source_used_fixture_fallback
    manifest['provider_metadata']['asset_download_enabled'] = asset_download_enabled
    manifest['provider_metadata']['asset_download_attempted'] = asset_download_attempted
    manifest['provider_metadata']['asset_download_status'] = asset_download_status
    manifest['provider_metadata']['asset_download_error'] = asset_download_error
    manifest['provider_metadata']['downloaded_asset_count'] = downloaded_asset_count
    manifest['provider_metadata']['cached_asset_count'] = cached_asset_count
    manifest['provider_metadata']['failed_asset_count'] = failed_asset_count
    manifest['provider_metadata']['seed'] = seed_value
    manifest['provider_metadata']['selected_asset_remote_url'] = selected_asset_remote_url
    manifest['provider_metadata']['selected_asset_cache_path'] = selected_asset_cache_path
    manifest['provider_metadata']['selected_asset_cache_status'] = selected_asset_cache_status
    manifest['provider_metadata']['cover_decision'] = cover_decision_payload
    manifest['provider_metadata']['cover_decision_genre_cluster'] = cover_decision_payload.get('genre_cluster')
    manifest['provider_metadata']['cover_decision_visual_type'] = cover_decision_payload.get('visual_type')
    manifest['provider_metadata']['cover_decision_image_source_type'] = cover_decision_payload.get('image_source_type')
    manifest['provider_metadata']['cover_decision_layout_type'] = cover_decision_payload.get('layout_type')
    manifest['provider_metadata']['cover_decision_use_ai'] = bool(cover_decision_payload.get('use_ai', False))
    manifest['provider_metadata']['cover_decision_decision_reason'] = cover_decision_payload.get('decision_reason')
    manifest['provider_metadata']['cover_decision_decision_trace'] = cover_decision_decision_trace
    manifest['provider_metadata']['cover_decision_card_type'] = cover_decision_card_type
    manifest['provider_metadata']['cover_decision_card_type_reason'] = cover_decision_card_type_reason
    manifest['provider_metadata']['cover_decision_card_strategy_version'] = cover_decision_card_strategy_version
    manifest['provider_metadata']['cover_decision_card_type_inputs'] = cover_decision_card_type_inputs
    manifest['provider_metadata']['cover_decision_readability_score'] = cover_decision_readability_score
    manifest['provider_metadata']['cover_decision_focus_score'] = cover_decision_focus_score
    manifest['provider_metadata']['cover_decision_asset_metadata_enriched'] = cover_decision_asset_metadata_enriched
    manifest['provider_metadata']['cover_decision_orientation'] = cover_decision_orientation
    manifest['provider_metadata']['cover_decision_aspect_ratio'] = cover_decision_aspect_ratio
    manifest['provider_metadata']['cover_decision_estimated_focus'] = cover_decision_estimated_focus
    manifest['provider_metadata']['cover_decision_estimated_subject_scale'] = cover_decision_estimated_subject_scale
    manifest['provider_metadata']['cover_decision_estimated_visual_density'] = cover_decision_estimated_visual_density
    manifest['provider_metadata']['cover_decision_composition_bias'] = cover_decision_composition_bias
    manifest['provider_metadata']['cover_decision_source_strength'] = cover_decision_source_strength
    manifest['provider_metadata']['cover_decision_official_asset_score_boost'] = cover_decision_official_asset_score_boost
    manifest['provider_metadata']['cover_decision_scoring_reason'] = cover_decision_scoring_reason
    manifest['provider_metadata']['cover_decision_rejection_reason'] = cover_decision_rejection_reason
    manifest['provider_metadata']['cover_decision_selected_asset'] = cover_decision_selected_asset
    manifest['provider_metadata']['cover_decision_rejected_assets'] = cover_decision_rejected_assets
    manifest['provider_metadata']['cover_decision_ai_fallback_reason'] = cover_decision_ai_fallback_reason
    manifest['provider_metadata']['cover_decision_official_assets_available'] = bool(
        cover_decision_asset_summary.get('official_assets_available', False)
    )
    manifest['provider_metadata']['cover_decision_official_assets_rejected_count'] = int(
        cover_decision_asset_summary.get('official_assets_rejected_count') or 0
    )
    manifest['provider_metadata']['cover_decision_rejection_reasons'] = [
        str(item)
        for item in cover_decision_selected_strategy.get('rejection_reasons') or []
        if str(item).strip()
    ]
    manifest['provider_metadata']['output_path'] = str(output_image_path)
    manifest['provider_metadata']['image_path'] = str(output_image_path)
    manifest['provider_metadata']['review_image_path'] = None
    manifest_path = run_root / 'ai_card_smoke_manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    return {
        **manifest,
        'manifest_path': str(manifest_path),
    }


def print_run_result(result: dict[str, Any], *, run_index: int, total_runs: int, debug_ai: bool = False) -> None:
    print('card_pipeline = yoto_card_engine_v4')
    print(f'run = {run_index}/{total_runs}')
    print(f"scenario = {result['scenario']}")
    print(f"game_set = {result.get('game_set') or DEFAULT_GAME_SET}")
    print(f"game_eval = {str(bool(result.get('game_eval', False))).lower()}")
    print(f"game_slug = {result.get('game_slug') or 'none'}")
    print(f"game_title = {result.get('game_title') or 'none'}")
    print(f"genre = {result.get('genre') or 'none'}")
    print(f"tags = {','.join(result.get('tags') or []) or 'none'}")
    print(f"short_description = {result.get('short_description') or 'none'}")
    print(f"offer_type = {result.get('offer_type') or 'none'}")
    print(f"asset_source_mode = {result.get('asset_source_mode') or 'none'}")
    print(f"asset_ingestion_mode = {result.get('asset_ingestion_mode') or 'none'}")
    print(f"asset_candidates_count = {int(result.get('asset_candidates_count') or 0)}")
    print(f"asset_candidate_source_types = {','.join(result.get('asset_candidate_source_types') or []) or 'none'}")
    print(f"asset_source_errors = {','.join(result.get('asset_source_errors') or []) or 'none'}")
    print(f"asset_download_enabled = {str(bool(result.get('asset_download_enabled', False))).lower()}")
    print(f"asset_download_attempted = {str(bool(result.get('asset_download_attempted', False))).lower()}")
    print(f"asset_download_status = {result.get('asset_download_status') or 'none'}")
    print(f"asset_download_error = {result.get('asset_download_error') or 'none'}")
    print(f"downloaded_asset_count = {int(result.get('downloaded_asset_count') or 0)}")
    print(f"cached_asset_count = {int(result.get('cached_asset_count') or 0)}")
    print(f"failed_asset_count = {int(result.get('failed_asset_count') or 0)}")
    print(f"seed = {result.get('seed') if result.get('seed') is not None else 'none'}")
    print(f"image_provider_mode = {result['image_provider_mode']}")
    print(f"provider_attempted = {result.get('provider_attempted') or 'none'}")
    print(f"provider = {result['provider']}")
    print(f"fallback_used = {str(bool(result.get('fallback_used', False))).lower()}")
    print(f"fallback_reason = {result.get('fallback_reason') or 'none'}")
    print(f"quality_checked = {str(bool(result.get('quality_checked', False))).lower()}")
    print(f"quality_passed = {str(bool(result.get('quality_passed', False))).lower()}")
    print(f"quality_reject_reason = {result.get('quality_reject_reason') or 'none'}")
    print(f"ai_source_mode = {result.get('ai_source_mode') or 'none'}")
    print(f"reference_assets_used = {str(bool(result.get('reference_assets_used', False))).lower()}")
    print(f"reference_asset_count = {int(result.get('reference_asset_count') or 0)}")
    print(f"generated_image_origin = {result.get('generated_image_origin') or 'none'}")
    print(f"workflow_mode = {result.get('workflow_mode') or 'none'}")
    print(f"comfyui_stage = {result.get('comfyui_stage') or 'none'}")
    print(f"comfyui_stage_success = {str(bool(result.get('comfyui_stage_success', False))).lower()}")
    print(f"comfyui_failure_stage = {result.get('comfyui_failure_stage') or 'none'}")
    print(f"comfyui_failure_reason = {result.get('comfyui_failure_reason') or 'none'}")
    print(f"comfyui_http_status = {result.get('comfyui_http_status') if result.get('comfyui_http_status') is not None else 'none'}")
    print(f"comfyui_http_reason = {result.get('comfyui_http_reason') or 'none'}")
    print(f"comfyui_prompt_id = {result.get('comfyui_prompt_id') or 'none'}")
    print(f"comfyui_history_found = {str(bool(result.get('comfyui_history_found', False))).lower()}")
    print(f"comfyui_image_ref_found = {str(bool(result.get('comfyui_image_ref_found', False))).lower()}")
    print(f"comfyui_image_fetch_ok = {str(bool(result.get('comfyui_image_fetch_ok', False))).lower()}")
    print(f"comfyui_checkpoint_requested = {result.get('comfyui_checkpoint_requested') or 'none'}")
    print(f"comfyui_checkpoint_used = {result.get('comfyui_checkpoint_used') or 'none'}")
    print(f"comfyui_checkpoint_available = {result.get('comfyui_checkpoint_available') if result.get('comfyui_checkpoint_available') is not None else 'none'}")
    print(f"prompt_variant = {result.get('prompt_variant') or 'none'}")
    print(f"prompt_intent = {result.get('prompt_intent') or 'none'}")
    print(f"prompt_summary = {result.get('prompt_summary') or 'none'}")
    print(f"negative_prompt_summary = {result.get('negative_prompt_summary') or 'none'}")
    print(f"grounding_used = {str(bool(result.get('grounding_used', False))).lower()}")
    print(f"grounding_fields_used = {','.join(result.get('grounding_fields_used') or []) or 'none'}")
    print(f"grounding_summary = {result.get('grounding_summary') or 'none'}")
    print(f"visual_intent = {result.get('visual_intent') or 'none'}")
    print(f"visual_intent_reason = {result.get('visual_intent_reason') or 'none'}")
    print(f"variation_enabled = {str(bool(result.get('variation_enabled', False))).lower()}")
    print(f"variation_id = {result.get('variation_id') or 'none'}")
    print(f"variation_slots = {json.dumps(result.get('variation_slots') or {}, ensure_ascii=False)}")
    print(f"variation_camera = {result.get('variation_camera') or 'none'}")
    print(f"variation_moment = {result.get('variation_moment') or 'none'}")
    print(f"variation_focus = {result.get('variation_focus') or 'none'}")
    print(f"variation_composition = {result.get('variation_composition') or 'none'}")
    print(f"external_seed = {result.get('external_seed') if result.get('external_seed') is not None else 'none'}")
    print(f"ksampler_seed = {result.get('ksampler_seed') if result.get('ksampler_seed') is not None else 'none'}")
    print(f"seed_propagated = {str(bool(result.get('seed_propagated', False))).lower()}")
    print(f"cover_decision.genre_cluster = {result.get('cover_decision_genre_cluster') or 'none'}")
    print(f"cover_decision.visual_type = {result.get('cover_decision_visual_type') or 'none'}")
    print(f"cover_decision.image_source_type = {result.get('cover_decision_image_source_type') or 'none'}")
    print(f"cover_decision.layout_type = {result.get('cover_decision_layout_type') or 'none'}")
    print(f"cover_decision.use_ai = {str(bool(result.get('cover_decision_use_ai', False))).lower()}")
    print(f"cover_decision.decision_reason = {result.get('cover_decision_decision_reason') or 'none'}")
    print(f"cover_decision.card_type = {result.get('cover_decision_card_type') or 'none'}")
    print(f"cover_decision.card_type_reason = {result.get('cover_decision_card_type_reason') or 'none'}")
    print(f"cover_decision.card_strategy_version = {result.get('cover_decision_card_strategy_version') or 'none'}")
    print(
        "cover_decision.card_type_inputs = "
        f"{json.dumps(result.get('cover_decision_card_type_inputs') or {}, ensure_ascii=False)}"
    )
    print(
        "cover_decision.decision_trace = "
        f"{json.dumps(result.get('cover_decision_decision_trace') or {}, ensure_ascii=False)}"
    )
    print(
        "readability_score = "
        f"{result.get('cover_decision_readability_score') if result.get('cover_decision_readability_score') is not None else 'none'}"
    )
    print(
        "focus_score = "
        f"{result.get('cover_decision_focus_score') if result.get('cover_decision_focus_score') is not None else 'none'}"
    )
    print(f"asset_metadata_enriched = {str(bool(result.get('cover_decision_asset_metadata_enriched', False))).lower()}")
    print(f"orientation = {result.get('cover_decision_orientation') or 'none'}")
    print(
        "aspect_ratio = "
        f"{result.get('cover_decision_aspect_ratio') if result.get('cover_decision_aspect_ratio') is not None else 'none'}"
    )
    print(f"estimated_focus = {result.get('cover_decision_estimated_focus') or 'none'}")
    print(f"estimated_subject_scale = {result.get('cover_decision_estimated_subject_scale') or 'none'}")
    print(f"estimated_visual_density = {result.get('cover_decision_estimated_visual_density') or 'none'}")
    print(f"composition_bias = {result.get('cover_decision_composition_bias') or 'none'}")
    print(
        "source_strength = "
        f"{result.get('cover_decision_source_strength') if result.get('cover_decision_source_strength') is not None else 'none'}"
    )
    print(
        "official_asset_score_boost = "
        f"{result.get('cover_decision_official_asset_score_boost') if result.get('cover_decision_official_asset_score_boost') is not None else 'none'}"
    )
    print(f"scoring_reason = {result.get('cover_decision_scoring_reason') or 'none'}")
    print(f"rejection_reason = {result.get('cover_decision_rejection_reason') or 'none'}")
    print(
        "selected_asset = "
        f"{json.dumps(result.get('cover_decision_selected_asset') or {}, ensure_ascii=False)}"
    )
    print(
        "rejected_assets = "
        f"{json.dumps(result.get('cover_decision_rejected_assets') or [], ensure_ascii=False)}"
    )
    print(f"ai_fallback_reason = {result.get('cover_decision_ai_fallback_reason') or 'none'}")
    print(f"selected_asset.remote_url = {result.get('selected_asset_remote_url') or 'none'}")
    print(f"selected_asset.cache_path = {result.get('selected_asset_cache_path') or 'none'}")
    print(f"selected_asset.cache_status = {result.get('selected_asset_cache_status') or 'none'}")
    print(f"actual_image_source_type = {result.get('actual_image_source_type') or 'none'}")
    print(f"actual_image_path_or_url = {result.get('actual_image_path_or_url') or 'none'}")
    print(f"decision_asset_used = {str(bool(result.get('decision_asset_used', False))).lower()}")
    print(f"decision_asset_use_reason = {result.get('decision_asset_use_reason') or 'none'}")
    print(f"decision_asset_reject_reason = {result.get('decision_asset_reject_reason') or 'none'}")
    print(
        "decision_asset_matches_actual_source = "
        f"{str(bool(result.get('decision_asset_matches_actual_source', False))).lower()}"
    )
    print(f"final_source = {result['final_source']}")
    print(f"decision_reason = {result['decision_reason']}")
    print(f"ai_attempted = {str(result['ai_attempted']).lower()}")
    print(f"ai_succeeded = {str(result['ai_succeeded']).lower()}")
    print(f"outcome = {result['outcome']}")
    print(f"output_path = {result.get('output_path') or result['image_path']}")
    print(f"image_path = {result['image_path']}")
    print(f"review_image_path = {result.get('review_image_path') or 'none'}")
    print(f"manifest_path = {result['manifest_path']}")
    if debug_ai:
        scenario_metadata = result.get('scenario_metadata', {})
        effective_config = result.get('effective_config', {})
        provider_metadata = result.get('provider_metadata', {})
        print('debug_ai = on')
        print(f"decision_flow.game_set = {result.get('game_set')}")
        print(f"decision_flow.game_eval = {result.get('game_eval')}")
        print(f"decision_flow.game_slug = {result.get('game_slug')}")
        print(f"decision_flow.game_title = {result.get('game_title')}")
        print(f"decision_flow.genre = {result.get('genre')}")
        print(f"decision_flow.tags = {result.get('tags')}")
        print(f"decision_flow.short_description = {result.get('short_description')}")
        print(f"decision_flow.offer_type = {result.get('offer_type')}")
        print(f"decision_flow.asset_source_mode = {result.get('asset_source_mode')}")
        print(f"decision_flow.asset_ingestion_mode = {result.get('asset_ingestion_mode')}")
        print(f"decision_flow.asset_candidates_count = {result.get('asset_candidates_count')}")
        print(f"decision_flow.asset_candidate_source_types = {result.get('asset_candidate_source_types')}")
        print(f"decision_flow.asset_source_errors = {result.get('asset_source_errors')}")
        print(f"decision_flow.asset_source_manifest_path = {result.get('asset_source_manifest_path')}")
        print(f"decision_flow.asset_source_manifest_entry_id = {result.get('asset_source_manifest_entry_id')}")
        print(f"decision_flow.asset_source_used_fixture_fallback = {result.get('asset_source_used_fixture_fallback')}")
        print(f"decision_flow.asset_download_enabled = {result.get('asset_download_enabled')}")
        print(f"decision_flow.asset_download_attempted = {result.get('asset_download_attempted')}")
        print(f"decision_flow.asset_download_status = {result.get('asset_download_status')}")
        print(f"decision_flow.asset_download_error = {result.get('asset_download_error')}")
        print(f"decision_flow.downloaded_asset_count = {result.get('downloaded_asset_count')}")
        print(f"decision_flow.cached_asset_count = {result.get('cached_asset_count')}")
        print(f"decision_flow.failed_asset_count = {result.get('failed_asset_count')}")
        print(f"decision_flow.seed = {result.get('seed')}")
        print(f"decision_flow.output_path = {result.get('output_path')}")
        print(f"decision_flow.config_source = {scenario_metadata.get('config_source')}")
        print(f"decision_flow.requested_ai_provider = {scenario_metadata.get('requested_ai_provider')}")
        print(f"decision_flow.requested_ai_source_mode = {scenario_metadata.get('requested_ai_source_mode')}")
        print(f"decision_flow.requested_mode = {scenario_metadata.get('requested_mode')}")
        print(f"decision_flow.requested_comfyui_checkpoint = {scenario_metadata.get('requested_comfyui_checkpoint')}")
        print(f"decision_flow.requested_prompt_variant = {scenario_metadata.get('requested_prompt_variant')}")
        print(f"decision_flow.ai_provider_class = {result.get('ai_provider_class')}")
        print(f"decision_flow.ai_provider_enabled = {str(bool(result.get('ai_provider_enabled', False))).lower()}")
        print(f"decision_flow.image_provider_mode = {effective_config.get('image_provider_mode')}")
        print(f"decision_flow.requested_comfyui_url = {scenario_metadata.get('requested_comfyui_url')}")
        print(f"decision_flow.provider_attempted = {provider_metadata.get('provider_attempted')}")
        print(f"decision_flow.selected_source = {result.get('selected_source')}")
        print(f"decision_flow.final_source = {result.get('final_source')}")
        print(f"decision_flow.provider_metadata.provider = {provider_metadata.get('provider')}")
        print(f"decision_flow.provider_metadata.fallback_used = {provider_metadata.get('fallback_used')}")
        print(f"decision_flow.provider_metadata.fallback_reason = {provider_metadata.get('fallback_reason')}")
        print(f"decision_flow.provider_metadata.quality_checked = {provider_metadata.get('quality_checked')}")
        print(f"decision_flow.provider_metadata.quality_passed = {provider_metadata.get('quality_passed')}")
        print(f"decision_flow.provider_metadata.quality_reject_reason = {provider_metadata.get('quality_reject_reason')}")
        print(f"decision_flow.provider_metadata.quality_metrics = {provider_metadata.get('quality_metrics')}")
        print(f"decision_flow.provider_metadata.selected_asset_remote_url = {provider_metadata.get('selected_asset_remote_url')}")
        print(f"decision_flow.provider_metadata.selected_asset_cache_path = {provider_metadata.get('selected_asset_cache_path')}")
        print(f"decision_flow.provider_metadata.selected_asset_cache_status = {provider_metadata.get('selected_asset_cache_status')}")
        print(f"decision_flow.provider_metadata.actual_image_source_type = {provider_metadata.get('actual_image_source_type')}")
        print(f"decision_flow.provider_metadata.actual_image_path_or_url = {provider_metadata.get('actual_image_path_or_url')}")
        print(f"decision_flow.provider_metadata.decision_asset_used = {provider_metadata.get('decision_asset_used')}")
        print(f"decision_flow.provider_metadata.decision_asset_use_reason = {provider_metadata.get('decision_asset_use_reason')}")
        print(f"decision_flow.provider_metadata.decision_asset_reject_reason = {provider_metadata.get('decision_asset_reject_reason')}")
        print(
            "decision_flow.provider_metadata.decision_asset_matches_actual_source = "
            f"{provider_metadata.get('decision_asset_matches_actual_source')}"
        )
        print(f"decision_flow.provider_metadata.ai_source_mode = {provider_metadata.get('ai_source_mode')}")
        print(f"decision_flow.provider_metadata.reference_assets_used = {provider_metadata.get('reference_assets_used')}")
        print(f"decision_flow.provider_metadata.reference_asset_count = {provider_metadata.get('reference_asset_count')}")
        print(f"decision_flow.provider_metadata.generated_image_origin = {provider_metadata.get('generated_image_origin')}")
        print(f"decision_flow.provider_metadata.workflow_mode = {provider_metadata.get('workflow_mode')}")
        print(f"decision_flow.provider_metadata.comfyui_stage = {provider_metadata.get('comfyui_stage')}")
        print(f"decision_flow.provider_metadata.comfyui_stage_success = {provider_metadata.get('comfyui_stage_success')}")
        print(f"decision_flow.provider_metadata.comfyui_failure_stage = {provider_metadata.get('comfyui_failure_stage')}")
        print(f"decision_flow.provider_metadata.comfyui_failure_reason = {provider_metadata.get('comfyui_failure_reason')}")
        print(f"decision_flow.provider_metadata.comfyui_http_status = {provider_metadata.get('comfyui_http_status')}")
        print(f"decision_flow.provider_metadata.comfyui_http_reason = {provider_metadata.get('comfyui_http_reason')}")
        print(f"decision_flow.provider_metadata.comfyui_prompt_id = {provider_metadata.get('comfyui_prompt_id')}")
        print(f"decision_flow.provider_metadata.comfyui_history_found = {provider_metadata.get('comfyui_history_found')}")
        print(f"decision_flow.provider_metadata.comfyui_image_ref_found = {provider_metadata.get('comfyui_image_ref_found')}")
        print(f"decision_flow.provider_metadata.comfyui_image_fetch_ok = {provider_metadata.get('comfyui_image_fetch_ok')}")
        print(f"decision_flow.provider_metadata.comfyui_submit_url = {provider_metadata.get('comfyui_submit_url')}")
        print(f"decision_flow.provider_metadata.comfyui_response_body_excerpt = {provider_metadata.get('comfyui_response_body_excerpt')}")
        print(f"decision_flow.provider_metadata.comfyui_request_payload_excerpt = {provider_metadata.get('comfyui_request_payload_excerpt')}")
        print(f"decision_flow.provider_metadata.comfyui_request_top_level_keys = {provider_metadata.get('comfyui_request_top_level_keys')}")
        print(f"decision_flow.provider_metadata.comfyui_request_node_count = {provider_metadata.get('comfyui_request_node_count')}")
        print(f"decision_flow.provider_metadata.comfyui_checkpoint_name = {provider_metadata.get('comfyui_checkpoint_name')}")
        print(f"decision_flow.provider_metadata.comfyui_checkpoint_requested = {provider_metadata.get('comfyui_checkpoint_requested')}")
        print(f"decision_flow.provider_metadata.comfyui_checkpoint_used = {provider_metadata.get('comfyui_checkpoint_used')}")
        print(f"decision_flow.provider_metadata.comfyui_checkpoint_available = {provider_metadata.get('comfyui_checkpoint_available')}")
        print(f"decision_flow.provider_metadata.comfyui_positive_prompt_summary = {provider_metadata.get('comfyui_positive_prompt_summary')}")
        print(f"decision_flow.provider_metadata.comfyui_negative_prompt_summary = {provider_metadata.get('comfyui_negative_prompt_summary')}")
        print(f"decision_flow.provider_metadata.prompt_variant = {provider_metadata.get('prompt_variant')}")
        print(f"decision_flow.provider_metadata.prompt_intent = {provider_metadata.get('prompt_intent')}")
        print(f"decision_flow.provider_metadata.prompt_summary = {provider_metadata.get('prompt_summary')}")
        print(f"decision_flow.provider_metadata.negative_prompt_summary = {provider_metadata.get('negative_prompt_summary')}")
        print(f"decision_flow.provider_metadata.grounding_used = {provider_metadata.get('grounding_used')}")
        print(f"decision_flow.provider_metadata.grounding_fields_used = {provider_metadata.get('grounding_fields_used')}")
        print(f"decision_flow.provider_metadata.grounding_summary = {provider_metadata.get('grounding_summary')}")
        print(f"decision_flow.provider_metadata.visual_intent = {provider_metadata.get('visual_intent')}")
        print(f"decision_flow.provider_metadata.visual_intent_reason = {provider_metadata.get('visual_intent_reason')}")
        print(f"decision_flow.provider_metadata.variation_enabled = {provider_metadata.get('variation_enabled')}")
        print(f"decision_flow.provider_metadata.variation_id = {provider_metadata.get('variation_id')}")
        print(f"decision_flow.provider_metadata.variation_slots = {provider_metadata.get('variation_slots')}")
        print(f"decision_flow.provider_metadata.variation_camera = {provider_metadata.get('variation_camera')}")
        print(f"decision_flow.provider_metadata.variation_moment = {provider_metadata.get('variation_moment')}")
        print(f"decision_flow.provider_metadata.variation_focus = {provider_metadata.get('variation_focus')}")
        print(f"decision_flow.provider_metadata.variation_composition = {provider_metadata.get('variation_composition')}")
        print(f"decision_flow.provider_metadata.external_seed = {provider_metadata.get('external_seed')}")
        print(f"decision_flow.provider_metadata.ksampler_seed = {provider_metadata.get('ksampler_seed')}")
        print(f"decision_flow.provider_metadata.seed_propagated = {provider_metadata.get('seed_propagated')}")
        print(f"decision_flow.provider_metadata.game_set = {provider_metadata.get('game_set')}")
        print(f"decision_flow.provider_metadata.game_eval = {provider_metadata.get('game_eval')}")
        print(f"decision_flow.provider_metadata.game_slug = {provider_metadata.get('game_slug')}")
        print(f"decision_flow.provider_metadata.game_title = {provider_metadata.get('game_title')}")
        print(f"decision_flow.provider_metadata.genre = {provider_metadata.get('genre')}")
        print(f"decision_flow.provider_metadata.tags = {provider_metadata.get('tags')}")
        print(f"decision_flow.provider_metadata.short_description = {provider_metadata.get('short_description')}")
        print(f"decision_flow.provider_metadata.offer_type = {provider_metadata.get('offer_type')}")
        print(f"decision_flow.provider_metadata.asset_source_mode = {provider_metadata.get('asset_source_mode')}")
        print(f"decision_flow.provider_metadata.asset_ingestion_mode = {provider_metadata.get('asset_ingestion_mode')}")
        print(f"decision_flow.provider_metadata.asset_candidates_count = {provider_metadata.get('asset_candidates_count')}")
        print(f"decision_flow.provider_metadata.asset_candidate_source_types = {provider_metadata.get('asset_candidate_source_types')}")
        print(f"decision_flow.provider_metadata.asset_source_errors = {provider_metadata.get('asset_source_errors')}")
        print(f"decision_flow.provider_metadata.asset_source_manifest_path = {provider_metadata.get('asset_source_manifest_path')}")
        print(f"decision_flow.provider_metadata.asset_source_manifest_entry_id = {provider_metadata.get('asset_source_manifest_entry_id')}")
        print(f"decision_flow.provider_metadata.asset_source_used_fixture_fallback = {provider_metadata.get('asset_source_used_fixture_fallback')}")
        print(f"decision_flow.provider_metadata.asset_download_enabled = {provider_metadata.get('asset_download_enabled')}")
        print(f"decision_flow.provider_metadata.asset_download_attempted = {provider_metadata.get('asset_download_attempted')}")
        print(f"decision_flow.provider_metadata.asset_download_status = {provider_metadata.get('asset_download_status')}")
        print(f"decision_flow.provider_metadata.asset_download_error = {provider_metadata.get('asset_download_error')}")
        print(f"decision_flow.provider_metadata.downloaded_asset_count = {provider_metadata.get('downloaded_asset_count')}")
        print(f"decision_flow.provider_metadata.cached_asset_count = {provider_metadata.get('cached_asset_count')}")
        print(f"decision_flow.provider_metadata.failed_asset_count = {provider_metadata.get('failed_asset_count')}")
        print(f"decision_flow.provider_metadata.seed = {provider_metadata.get('seed')}")
        print(f"decision_flow.provider_metadata.output_path = {provider_metadata.get('output_path')}")
        print(f"decision_flow.provider_metadata.image_path = {provider_metadata.get('image_path')}")
        print(f"decision_flow.provider_metadata.review_image_path = {provider_metadata.get('review_image_path')}")
        print(f"decision_flow.provider_metadata.final_source = {provider_metadata.get('final_source')}")
        print(
            "decision_flow.provider_metadata.cover_decision_asset_metadata_enriched = "
            f"{provider_metadata.get('cover_decision_asset_metadata_enriched')}"
        )
        print(f"decision_flow.provider_metadata.cover_decision_orientation = {provider_metadata.get('cover_decision_orientation')}")
        print(f"decision_flow.provider_metadata.cover_decision_aspect_ratio = {provider_metadata.get('cover_decision_aspect_ratio')}")
        print(f"decision_flow.provider_metadata.cover_decision_estimated_focus = {provider_metadata.get('cover_decision_estimated_focus')}")
        print(
            "decision_flow.provider_metadata.cover_decision_estimated_subject_scale = "
            f"{provider_metadata.get('cover_decision_estimated_subject_scale')}"
        )
        print(
            "decision_flow.provider_metadata.cover_decision_estimated_visual_density = "
            f"{provider_metadata.get('cover_decision_estimated_visual_density')}"
        )
        print(f"decision_flow.provider_metadata.cover_decision_composition_bias = {provider_metadata.get('cover_decision_composition_bias')}")
        print(f"decision_flow.provider_metadata.cover_decision_source_strength = {provider_metadata.get('cover_decision_source_strength')}")
        print(
            "decision_flow.provider_metadata.cover_decision_official_asset_score_boost = "
            f"{provider_metadata.get('cover_decision_official_asset_score_boost')}"
        )
        print(f"decision_flow.provider_metadata.cover_decision_scoring_reason = {provider_metadata.get('cover_decision_scoring_reason')}")
        print(f"decision_flow.provider_metadata.cover_decision_rejection_reason = {provider_metadata.get('cover_decision_rejection_reason')}")
        print(
            "decision_flow.cover_decision = "
            f"{json.dumps(result.get('cover_decision') or {}, indent=2, ensure_ascii=False)}"
        )
        print('resolver_trace =')
        print(json.dumps(result.get('resolver_trace') or {}, indent=2, ensure_ascii=False))


def build_summary(
    *,
    scenario: str,
    requested_runs: int,
    results: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    prompt_variants: list[str],
    compare_prompt_variants: bool,
    game_set: str,
    game_eval: bool,
    seeds_per_game: int,
) -> dict[str, Any]:
    game_titles = sorted({str(item.get('game_title')) for item in results if item.get('game_title')})
    seeds = sorted({int(item.get('seed')) for item in results if item.get('seed') is not None})
    return {
        'scenario': scenario,
        'game_set': game_set,
        'game_eval': bool(game_eval),
        'game_titles': game_titles,
        'game_count': len(game_titles),
        'seeds': seeds,
        'seeds_per_game': int(seeds_per_game),
        'total_runs': requested_runs,
        'prompt_variants': list(prompt_variants),
        'compare_prompt_variants': bool(compare_prompt_variants),
        'completed_runs': len(results),
        'ai_runtime_count': sum(1 for item in results if item.get('outcome') == 'ai_runtime'),
        'ai_fallback_count': sum(1 for item in results if item.get('outcome') == 'ai_fallback'),
        'ai_hard_failure_count': sum(1 for item in results if item.get('outcome') == 'ai_hard_failure') + len(errors),
        'comfyui_provider_runs': sum(1 for item in results if item.get('provider') == 'comfyui'),
        'ai_attempted_true_runs': sum(1 for item in results if item.get('ai_attempted') is True),
        'ai_attempted_false_runs': sum(1 for item in results if item.get('ai_attempted') is False),
        'ai_succeeded_runs': sum(1 for item in results if item.get('ai_succeeded') is True),
        'fallback_used_runs': sum(1 for item in results if item.get('fallback_used') is True),
        'quality_checked_runs': sum(1 for item in results if item.get('quality_checked') is True),
        'quality_passed_runs': sum(1 for item in results if item.get('quality_passed') is True),
        'quality_reject_runs': sum(1 for item in results if item.get('quality_checked') is True and item.get('quality_passed') is False),
        'pure_generation_runs': sum(1 for item in results if item.get('ai_source_mode') == 'pure_generation'),
        'reference_assisted_runs': sum(1 for item in results if item.get('ai_source_mode') == 'reference_assisted'),
        'reference_assets_used_runs': sum(1 for item in results if item.get('reference_assets_used') is True),
        'distinct_comfyui_failure_stages': sorted(
            {
                str(item.get('comfyui_failure_stage'))
                for item in results
                if item.get('comfyui_failure_stage')
            }
        ),
        'all_ai_attempted_false': bool(results) and all(item.get('ai_attempted') is False for item in results),
        'errors': len(errors),
    }


def render_ai_card_smoke(
    *,
    scenario: str,
    runs: int = 1,
    output_root: Path = OUTPUT_ROOT,
    debug_ai: bool = False,
    prompt_variant: str = DEFAULT_PROMPT_VARIANT,
    compare_prompt_variants: bool = False,
    game_set: str = DEFAULT_GAME_SET,
    game_eval: bool = False,
    seeds_per_game: int = DEFAULT_SEEDS_PER_GAME,
    download_assets: bool = False,
) -> Path:
    selected_prompt_variant = str(prompt_variant or DEFAULT_PROMPT_VARIANT).strip().lower() or DEFAULT_PROMPT_VARIANT
    if selected_prompt_variant not in VALID_PROMPT_VARIANTS:
        raise ValueError(f'Unsupported prompt variant: {prompt_variant}')
    selected_game_set = resolve_selected_game_set(game_set=game_set, game_eval=game_eval)
    game_inputs = resolve_game_inputs(selected_game_set)
    selected_seeds_per_game = max(1, int(seeds_per_game or DEFAULT_SEEDS_PER_GAME))
    prompt_variants = list(VALID_PROMPT_VARIANTS if compare_prompt_variants else (selected_prompt_variant,))
    total_runs = max(1, int(runs))
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    total_result_runs = (
        len(game_inputs) * len(prompt_variants) * selected_seeds_per_game
        if game_eval
        else total_runs * len(game_inputs) * len(prompt_variants)
    )
    current_result_run = 0
    batch_key = datetime.utcnow().strftime('%Y%m%dT%H%M%S%fZ')
    batch_root = (
        output_root / 'ai_eval_batches' / f'ai_card_smoke_batch_{scenario}_{batch_key}'
        if game_eval
        else output_root / f'ai_card_smoke_batch_{scenario}_{batch_key}'
    )
    batch_root.mkdir(parents=True, exist_ok=True)
    review_cards_dir = batch_root / 'review_cards'
    review_cards_dir.mkdir(parents=True, exist_ok=True)
    batch_manifest_path = batch_root / 'batch_summary.json'

    run_indices = [1] if game_eval else list(range(1, total_runs + 1))
    seed_values = list(range(1, selected_seeds_per_game + 1)) if game_eval else [None]

    for run_index in run_indices:
        for game_input in game_inputs:
            game_title = str(game_input.get('title') or 'unknown')
            game_slug = str(game_input.get('slug') or 'unknown')
            game_genre = str(game_input.get('genre') or 'none')
            game_tags = [str(item) for item in game_input.get('tags') or [] if str(item).strip()]
            game_short_description = str(game_input.get('short_description') or 'none')
            for seed_value in seed_values:
                shared_run_key = datetime.utcnow().strftime('%Y%m%dT%H%M%S%fZ')
                for variant in prompt_variants:
                    result_root = (
                        output_root / 'ai_eval' / game_slug / variant / f'seed_{seed_value}'
                        if game_eval and seed_value is not None
                        else None
                    )
                    current_result_run += 1
                    try:
                        result = run_scenario(
                            scenario=scenario,
                            output_root=output_root,
                            prompt_variant=variant,
                            game_input=game_input,
                            game_set=selected_game_set,
                            seed=seed_value,
                            game_eval=game_eval,
                            result_root=result_root,
                            run_key=shared_run_key,
                            download_assets=download_assets,
                        )
                        review_image_path = copy_review_image_for_result(
                            result=result,
                            review_cards_dir=review_cards_dir,
                        )
                        result['review_image_path'] = str(review_image_path)
                        provider_metadata = result.get('provider_metadata')
                        if isinstance(provider_metadata, dict):
                            provider_metadata['review_image_path'] = str(review_image_path)
                    except Exception as exc:
                        error = {
                            'run': current_result_run,
                            'scenario_run': run_index,
                            'game_set': selected_game_set,
                            'game_eval': bool(game_eval),
                            'game_slug': game_slug,
                            'game_title': game_title,
                            'genre': game_genre,
                            'tags': list(game_tags),
                            'short_description': game_short_description,
                            'prompt_variant': variant,
                            'seed': seed_value,
                            'outcome': 'ai_hard_failure',
                            'error_type': exc.__class__.__name__,
                            'message': str(exc),
                        }
                        errors.append(error)
                        print(f'run = {current_result_run}/{total_result_runs}')
                        print(f"scenario = {scenario}")
                        print(f"game_set = {selected_game_set}")
                        print(f"game_eval = {str(bool(game_eval)).lower()}")
                        print(f"game_slug = {game_slug}")
                        print(f"game_title = {game_title}")
                        print(f"genre = {game_genre}")
                        print(f"tags = {','.join(game_tags) or 'none'}")
                        print(f"short_description = {game_short_description}")
                        print(f"seed = {seed_value if seed_value is not None else 'none'}")
                        print(f"prompt_variant = {variant}")
                        print('image_provider_mode = unknown')
                        print('provider_attempted = unknown')
                        print(f"provider = error")
                        print('fallback_used = false')
                        print('fallback_reason = none')
                        print('quality_checked = false')
                        print('quality_passed = false')
                        print('quality_reject_reason = none')
                        print('ai_source_mode = fallback')
                        print('reference_assets_used = false')
                        print('reference_asset_count = 0')
                        print('generated_image_origin = fallback_placeholder')
                        print('workflow_mode = fallback')
                        print('comfyui_stage = none')
                        print('comfyui_stage_success = false')
                        print('comfyui_failure_stage = none')
                        print('comfyui_failure_reason = none')
                        print('comfyui_http_status = none')
                        print('comfyui_http_reason = none')
                        print('comfyui_prompt_id = none')
                        print('comfyui_history_found = false')
                        print('comfyui_image_ref_found = false')
                        print('comfyui_image_fetch_ok = false')
                        print('comfyui_checkpoint_requested = none')
                        print('comfyui_checkpoint_used = none')
                        print('comfyui_checkpoint_available = none')
                        print('final_source = error')
                        print('decision_reason = error')
                        print('ai_attempted = false')
                        print('ai_succeeded = false')
                        print(f"outcome = ai_hard_failure")
                        print(f"error_type = {error['error_type']}")
                        print(f"error = {error['message']}")
                        continue

                    results.append(result)
                    print_run_result(result, run_index=current_result_run, total_runs=total_result_runs, debug_ai=debug_ai)

    summary = build_summary(
        scenario=scenario,
        requested_runs=total_result_runs,
        results=results,
        errors=errors,
        prompt_variants=prompt_variants,
        compare_prompt_variants=compare_prompt_variants,
        game_set=selected_game_set,
        game_eval=game_eval,
        seeds_per_game=selected_seeds_per_game,
    )
    batch_manifest = {
        'created_at': datetime.utcnow().isoformat() + 'Z',
        'review_cards_path': str(review_cards_dir),
        'summary': summary,
        'results': results,
        'errors': errors,
    }
    batch_manifest_path.write_text(json.dumps(batch_manifest, indent=2, ensure_ascii=False), encoding='utf-8')

    print('summary:')
    print(f"game_set = {summary['game_set']}")
    print(f"game_eval = {str(summary['game_eval']).lower()}")
    print(f"game_count = {summary['game_count']}")
    print(f"game_titles = {','.join(summary['game_titles']) if summary['game_titles'] else 'none'}")
    print(f"seeds = {','.join(str(item) for item in summary['seeds']) if summary['seeds'] else 'none'}")
    print(f"seeds_per_game = {summary['seeds_per_game']}")
    print(f"total_runs = {summary['total_runs']}")
    print(f"ai_runtime_count = {summary['ai_runtime_count']}")
    print(f"ai_fallback_count = {summary['ai_fallback_count']}")
    print(f"ai_hard_failure_count = {summary['ai_hard_failure_count']}")
    print(f"comfyui_provider_runs = {summary['comfyui_provider_runs']}")
    print(f"ai_attempted_true_runs = {summary['ai_attempted_true_runs']}")
    print(f"ai_attempted_false_runs = {summary['ai_attempted_false_runs']}")
    print(f"ai_succeeded_runs = {summary['ai_succeeded_runs']}")
    print(f"fallback_used_runs = {summary['fallback_used_runs']}")
    print(f"quality_checked_runs = {summary['quality_checked_runs']}")
    print(f"quality_passed_runs = {summary['quality_passed_runs']}")
    print(f"quality_reject_runs = {summary['quality_reject_runs']}")
    print(f"pure_generation_runs = {summary['pure_generation_runs']}")
    print(f"reference_assisted_runs = {summary['reference_assisted_runs']}")
    print(f"reference_assets_used_runs = {summary['reference_assets_used_runs']}")
    print(f"distinct_comfyui_failure_stages = {','.join(summary['distinct_comfyui_failure_stages']) if summary['distinct_comfyui_failure_stages'] else 'none'}")
    print(f"prompt_variants = {','.join(summary['prompt_variants']) if summary['prompt_variants'] else 'none'}")
    print(f"compare_prompt_variants = {str(summary['compare_prompt_variants']).lower()}")
    print(f"all_ai_attempted_false = {str(summary['all_ai_attempted_false']).lower()}")
    print(f"errors = {summary['errors']}")
    print(f'review_cards_path = {review_cards_dir}')
    print(f'batch_manifest_path = {batch_manifest_path}')
    return batch_root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Minimal E2E smoke for YOTO card provider routing.')
    parser.add_argument('scenario', nargs='?', default='current_env', choices=VALID_SCENARIOS)
    parser.add_argument('--runs', type=int, default=1)
    parser.add_argument('--debug-ai', action='store_true')
    parser.add_argument('--prompt-variant', default=DEFAULT_PROMPT_VARIANT, choices=VALID_PROMPT_VARIANTS)
    parser.add_argument('--game-set', default=DEFAULT_GAME_SET, choices=VALID_GAME_SETS)
    parser.add_argument('--game-eval', action='store_true')
    parser.add_argument('--seeds-per-game', type=int, default=DEFAULT_SEEDS_PER_GAME)
    parser.add_argument('--compare-prompt-variants', action='store_true')
    parser.add_argument('--download-assets', action='store_true')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    render_ai_card_smoke(
        scenario=args.scenario,
        runs=args.runs,
        debug_ai=args.debug_ai,
        prompt_variant=args.prompt_variant,
        game_set=args.game_set,
        game_eval=args.game_eval,
        seeds_per_game=args.seeds_per_game,
        compare_prompt_variants=args.compare_prompt_variants,
        download_assets=args.download_assets,
    )


if __name__ == '__main__':
    main()
