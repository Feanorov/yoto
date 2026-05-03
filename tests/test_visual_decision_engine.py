from __future__ import annotations

from pathlib import Path

from infrastructure.render.cards.visual_decision_engine import build_cover_decision, resolve_cover_decision_asset_bridge
from tools.ai_card_smoke import MINIMAL_SMOKE_GAMES, SMOKE_LOCAL_LANDSCAPE_ASSET, SMOKE_LOCAL_PORTRAIT_ASSET


def test_visual_decision_engine_hades_prefers_official_character_art() -> None:
    game_input = dict(MINIMAL_SMOKE_GAMES[0])
    decision = build_cover_decision(
        game_title=game_input['title'],
        genre=game_input['genre'],
        tags=game_input['tags'],
        short_description=game_input['short_description'],
        offer_type=game_input['offer_type'],
        asset_candidates=game_input['asset_candidates'],
    ).to_dict()

    assert decision['genre_cluster'] == 'character_driven'
    assert decision['visual_type'] == 'character'
    assert decision['use_ai'] is False
    assert decision['image_source_type'] in {'official_press_key_art', 'steam_main_capsule'}
    assert decision['layout_type'] in {'portrait_single', 'portrait_single_logo_safe'}
    assert decision['selected_asset']['readability_score'] >= 0.55
    assert decision['selected_asset']['focus_score'] >= 0.50


def test_visual_decision_engine_hades_does_not_saturate_top_scores() -> None:
    game_input = dict(MINIMAL_SMOKE_GAMES[0])
    decision = build_cover_decision(
        game_title=game_input['title'],
        genre=game_input['genre'],
        tags=game_input['tags'],
        short_description=game_input['short_description'],
        offer_type=game_input['offer_type'],
        asset_candidates=game_input['asset_candidates'],
    ).to_dict()

    asset_scores = [dict(item) for item in decision['asset_scores'] if isinstance(item, dict)]
    top_two = asset_scores[:2]

    assert len(top_two) == 2
    assert top_two[0]['asset_metadata_enriched'] is True
    assert top_two[0]['scoring_reason']
    assert top_two[0]['readability_score'] < 1.0
    assert top_two[0]['focus_score'] < 1.0
    assert top_two[0]['total_score'] < 1.0
    assert top_two[1]['total_score'] < 1.0
    assert top_two[0]['total_score'] > top_two[1]['total_score']
    assert 'readability_delta_capped' in top_two[0]['scoring_reason']
    assert 'focus_delta_capped' in top_two[0]['scoring_reason']


def test_visual_decision_engine_forza_prefers_official_scene_sources() -> None:
    game_input = dict(MINIMAL_SMOKE_GAMES[3])
    decision = build_cover_decision(
        game_title=game_input['title'],
        genre=game_input['genre'],
        tags=game_input['tags'],
        short_description=game_input['short_description'],
        offer_type=game_input['offer_type'],
        asset_candidates=game_input['asset_candidates'],
    ).to_dict()

    assert decision['genre_cluster'] == 'motion_vehicle'
    assert decision['visual_type'] == 'scene'
    assert decision['use_ai'] is False
    assert decision['image_source_type'] != 'ai_generated'
    assert decision['layout_type'] == 'landscape_scene_crop'


def test_visual_decision_engine_rejects_unresolved_template_only_screenshot() -> None:
    decision = build_cover_decision(
        game_title='Dave the Diver',
        genre='underwater adventure',
        tags=['harpoon', 'gameplay'],
        short_description='Dive into a readable underwater adventure scene.',
        offer_type='discount',
        asset_candidates=[
            {
                'source_type': 'steam_screenshot',
                'width': 1920,
                'height': 1080,
                'kind': 'screenshot',
                'path_or_url': 'D:\\Telegram_portable_bundle\\output\\cards\\official_asset_cache\\steam\\missing\\steam_screenshot_1.jpg',
                'metadata': {
                    'template_only': True,
                    'gameplay_focus': 'harpoon fishing',
                    'remote_url': 'https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/000000/ss_template_01.jpg',
                    'cache_path': 'D:\\Telegram_portable_bundle\\output\\cards\\official_asset_cache\\steam\\missing\\steam_screenshot_1.jpg',
                    'cache_status': 'failed',
                    'asset_download_error': 'http_error:404',
                },
            },
            {
                'source_type': 'official_press_key_art',
                'width': 1800,
                'height': 2700,
                'kind': 'key_art',
                'path_or_url': SMOKE_LOCAL_PORTRAIT_ASSET,
                'metadata': {
                    'subject_focus': 'character',
                    'closeup': True,
                    'logo_safe': True,
                },
            },
        ],
    ).to_dict()

    screenshot_asset = next(item for item in decision['asset_scores'] if item['source_type'] == 'steam_screenshot')

    assert decision['use_ai'] is False
    assert decision['image_source_type'] == 'official_press_key_art'
    assert screenshot_asset['accepted'] is False
    assert 'template_only_screenshot_not_available' in screenshot_asset['rejection_reasons']
    assert 'hard_reject:template_only_screenshot_not_available' in screenshot_asset['scoring_reason']


def test_visual_decision_engine_civilization_rejects_ui_heavy_gameplay_screenshot() -> None:
    game_input = dict(MINIMAL_SMOKE_GAMES[1])
    decision = build_cover_decision(
        game_title=game_input['title'],
        genre=game_input['genre'],
        tags=game_input['tags'],
        short_description=game_input['short_description'],
        offer_type=game_input['offer_type'],
        asset_candidates=game_input['asset_candidates'],
    ).to_dict()

    screenshot_asset = next(item for item in decision['asset_scores'] if item['source_type'] == 'steam_screenshot')

    assert decision['genre_cluster'] == 'gameplay_first'
    assert decision['visual_type'] == 'gameplay'
    assert decision['layout_type'] in {'gameplay_frame', 'landscape_scene_crop'}
    assert decision['use_ai'] is False
    assert decision['image_source_type'] in {'official_press_key_art', 'steam_library_hero'}
    assert screenshot_asset['accepted'] is False
    assert 'ui_heavy_screenshot_for_single_title' in screenshot_asset['rejection_reasons']
    assert 'missing_readable_focus' in screenshot_asset['rejection_reasons']
    assert 'hard_reject:ui_heavy_screenshot_for_single_title' in screenshot_asset['scoring_reason']


def test_visual_decision_engine_dave_stays_official_first() -> None:
    game_input = dict(MINIMAL_SMOKE_GAMES[2])
    decision = build_cover_decision(
        game_title=game_input['title'],
        genre=game_input['genre'],
        tags=game_input['tags'],
        short_description=game_input['short_description'],
        offer_type=game_input['offer_type'],
        asset_candidates=game_input['asset_candidates'],
    ).to_dict()

    assert decision['genre_cluster'] in {'gameplay_first', 'cute_cozy_symbolic'}
    assert decision['visual_type'] in {'gameplay', 'scene'}
    assert decision['use_ai'] is False
    assert decision['image_source_type'] != 'ai_generated'


def test_visual_decision_engine_bundle_prefers_collage_layout() -> None:
    game_input = dict(MINIMAL_SMOKE_GAMES[4])
    decision = build_cover_decision(
        game_title=game_input['title'],
        genre=game_input['genre'],
        tags=game_input['tags'],
        short_description=game_input['short_description'],
        offer_type=game_input['offer_type'],
        asset_candidates=game_input['asset_candidates'],
    ).to_dict()

    assert decision['genre_cluster'] == 'bundle_multi_item'
    assert decision['visual_type'] == 'collage'
    assert decision['layout_type'] in {'two_tile_split', 'three_tile_collage', 'four_tile_franchise'}
    assert decision['use_ai'] is False
    assert decision['selected_asset']['selection_mode'] == 'collage'
    assert len(decision['selected_asset']['assets']) >= 2


def test_visual_decision_engine_allows_ai_only_after_official_failures() -> None:
    decision = build_cover_decision(
        game_title='Tiny Horror Prototype',
        genre='horror',
        tags=['dark', 'atmospheric'],
        short_description='A dark atmospheric prototype with only a tiny unusable official image.',
        offer_type='discount',
        asset_candidates=[
            {
                'source_type': 'official_press_key_art',
                'width': 220,
                'height': 120,
                'kind': 'key_art',
                'path_or_url': 'smoke://tiny_horror/official_tiny.png',
                'metadata': {
                    'scene_focus': 'dark corridor',
                },
            },
            {
                'source_type': 'ai_generated',
                'width': 1280,
                'height': 720,
                'kind': 'generated_preview',
                'path_or_url': 'ai://preview/tiny_horror',
                'metadata': {
                    'prompt_intent': 'shot_focused_cinematic_grounded',
                },
            },
        ],
    ).to_dict()

    decision_trace = decision['decision_trace']
    asset_summary = decision_trace['asset_summary']
    selected_strategy = decision_trace['selected_strategy']

    assert decision['genre_cluster'] == 'atmospheric_scene'
    assert decision['visual_type'] == 'scene'
    assert decision['use_ai'] is True
    assert decision['image_source_type'] == 'ai_generated'
    assert asset_summary['official_assets_available'] is True
    assert asset_summary['official_assets_rejected_count'] >= 1
    assert selected_strategy['ai_fallback_reason'] == 'all_official_assets_failed_thresholds'
    assert 'readability_below_threshold' in selected_strategy['rejection_reasons']


def test_visual_decision_engine_bridge_accepts_real_local_official_asset() -> None:
    game_input = dict(MINIMAL_SMOKE_GAMES[0])
    cover_decision = build_cover_decision(
        game_title=game_input['title'],
        genre=game_input['genre'],
        tags=game_input['tags'],
        short_description=game_input['short_description'],
        offer_type=game_input['offer_type'],
        asset_candidates=game_input['asset_candidates'],
    ).to_dict()

    bridge = resolve_cover_decision_asset_bridge(cover_decision)

    assert bridge.candidate_valid is True
    assert bridge.selected_asset_source_type in {'official_press_key_art', 'steam_main_capsule'}
    assert bridge.resolved_local_path is not None
    assert Path(bridge.resolved_local_path).exists()
    assert bridge.decision_asset_use_reason == 'cover_decision_selected_official_asset'
    assert bridge.decision_asset_reject_reason is None


def test_visual_decision_engine_bridge_rejects_nonlocal_or_aggregate_assets() -> None:
    bundle_input = dict(MINIMAL_SMOKE_GAMES[4])
    bundle_decision = build_cover_decision(
        game_title=bundle_input['title'],
        genre=bundle_input['genre'],
        tags=bundle_input['tags'],
        short_description=bundle_input['short_description'],
        offer_type=bundle_input['offer_type'],
        asset_candidates=bundle_input['asset_candidates'],
    ).to_dict()

    bundle_bridge = resolve_cover_decision_asset_bridge(bundle_decision)
    smoke_bridge = resolve_cover_decision_asset_bridge(
        {
            'use_ai': False,
            'selected_asset': {
                'source_type': 'official_press_key_art',
                'path_or_url': 'smoke://invalid/nonlocal.png',
            },
        }
    )
    ai_bridge = resolve_cover_decision_asset_bridge(
        {
            'use_ai': False,
            'selected_asset': {
                'source_type': 'ai_generated',
                'path_or_url': 'ai://preview/nonlocal',
            },
        }
    )

    assert bundle_bridge.candidate_valid is False
    assert bundle_bridge.decision_asset_reject_reason == 'invalid_or_nonlocal_asset_path'
    assert smoke_bridge.candidate_valid is False
    assert smoke_bridge.decision_asset_reject_reason == 'invalid_or_nonlocal_asset_path'
    assert ai_bridge.candidate_valid is False
    assert ai_bridge.decision_asset_reject_reason == 'invalid_or_nonlocal_asset_path'


def test_visual_decision_engine_prefers_clickable_asset_over_empty_scene_press_art() -> None:
    decision = build_cover_decision(
        game_title='Nightfall Tactics',
        genre='action rpg',
        tags=['hero', 'fantasy'],
        short_description='A lone hero returns to a ruined kingdom.',
        offer_type='discount',
        asset_candidates=[
            {
                'source_type': 'official_press_key_art',
                'width': 1600,
                'height': 2400,
                'kind': 'key_art',
                'path_or_url': 'smoke://official/empty_scene.png',
                'metadata': {
                    'scene_focus': 'foggy ruins',
                    'background': 'distant castle horizon',
                    'landscape': True,
                    'panorama': True,
                },
            },
            {
                'source_type': 'steam_main_capsule',
                'width': 1232,
                'height': 706,
                'kind': 'main_capsule',
                'path_or_url': SMOKE_LOCAL_LANDSCAPE_ASSET,
                'metadata': {
                    'subject_focus': 'hero',
                    'logo_safe': True,
                    'closeup': True,
                },
            },
        ],
    ).to_dict()

    clickable_asset = next(
        item for item in decision['asset_scores'] if item['path_or_url'] == SMOKE_LOCAL_LANDSCAPE_ASSET
    )
    empty_scene_asset = next(
        item for item in decision['asset_scores'] if item['path_or_url'] == 'smoke://official/empty_scene.png'
    )

    assert decision['use_ai'] is False
    assert decision['image_source_type'] == 'steam_main_capsule'
    assert clickable_asset['total_score'] > empty_scene_asset['total_score']
    assert empty_scene_asset['accepted'] is False
    assert 'missing_readable_focus' in empty_scene_asset['rejection_reasons']
    assert 'vdr1_clickable_asset_bonus' in clickable_asset['scoring_reason']
    assert 'vdr1_missing_readable_focus_penalty' in empty_scene_asset['scoring_reason']
    assert 'vdr1_empty_scene_penalty' in empty_scene_asset['scoring_reason']


def test_visual_decision_engine_penalizes_text_heavy_capsules() -> None:
    decision = build_cover_decision(
        game_title='Mystic Quest',
        genre='action rpg',
        tags=['hero'],
        short_description='A hero fights through ruins.',
        offer_type='discount',
        asset_candidates=[
            {
                'source_type': 'steam_main_capsule',
                'width': 1232,
                'height': 706,
                'kind': 'main_capsule',
                'path_or_url': SMOKE_LOCAL_LANDSCAPE_ASSET,
                'metadata': {
                    'subject_focus': 'hero',
                    'logo_safe': True,
                    'text_heavy': True,
                    'marketing_copy': 'deluxe edition out now',
                },
            },
            {
                'source_type': 'steam_main_capsule',
                'width': 1232,
                'height': 706,
                'kind': 'main_capsule',
                'path_or_url': SMOKE_LOCAL_PORTRAIT_ASSET,
                'metadata': {
                    'subject_focus': 'hero',
                    'logo_safe': True,
                    'marketing_pose': 'closeup action',
                },
            },
        ],
    ).to_dict()

    clean_asset = next(item for item in decision['asset_scores'] if item['path_or_url'] == SMOKE_LOCAL_PORTRAIT_ASSET)
    text_heavy_asset = next(
        item for item in decision['asset_scores'] if item['path_or_url'] == SMOKE_LOCAL_LANDSCAPE_ASSET
    )

    assert decision['image_source_type'] == 'steam_main_capsule'
    assert decision['selected_asset']['path_or_url'] == SMOKE_LOCAL_PORTRAIT_ASSET
    assert clean_asset['total_score'] > text_heavy_asset['total_score']
    assert 'vdr1_text_heavy_penalty' in text_heavy_asset['scoring_reason']


def test_visual_decision_engine_penalizes_non_bundle_collage_art() -> None:
    decision = build_cover_decision(
        game_title='Nightfall Tactics',
        genre='action rpg',
        tags=['hero', 'fantasy'],
        short_description='A lone hero returns to a ruined kingdom.',
        offer_type='discount',
        asset_candidates=[
            {
                'source_type': 'official_press_key_art',
                'width': 1600,
                'height': 2400,
                'kind': 'key_art',
                'path_or_url': 'smoke://official/group_art.png',
                'metadata': {
                    'group': 'ensemble',
                    'multiple_characters': True,
                    'collection': True,
                    'poster_layout': True,
                },
            },
            {
                'source_type': 'steam_library_capsule',
                'width': 600,
                'height': 900,
                'kind': 'library_capsule',
                'path_or_url': SMOKE_LOCAL_PORTRAIT_ASSET,
                'metadata': {
                    'subject_focus': 'hero',
                    'logo_safe': True,
                },
            },
        ],
    ).to_dict()

    clickable_asset = next(
        item for item in decision['asset_scores'] if item['path_or_url'] == SMOKE_LOCAL_PORTRAIT_ASSET
    )
    collage_like_asset = next(
        item for item in decision['asset_scores'] if item['path_or_url'] == 'smoke://official/group_art.png'
    )

    assert decision['use_ai'] is False
    assert decision['image_source_type'] == 'steam_library_capsule'
    assert clickable_asset['total_score'] > collage_like_asset['total_score']
    assert 'vdr1_no_collage_penalty' in collage_like_asset['scoring_reason']


def test_visual_decision_engine_allows_gameplay_focus_without_hero_gate() -> None:
    decision = build_cover_decision(
        game_title='Iron Vanguard',
        genre='strategy tactics',
        tags=['battlefield', 'squad tactics'],
        short_description='Squads clash across a readable battlefield with a clear center push.',
        offer_type='discount',
        asset_candidates=[
            {
                'source_type': 'steam_screenshot',
                'width': 1920,
                'height': 1080,
                'kind': 'screenshot',
                'path_or_url': SMOKE_LOCAL_LANDSCAPE_ASSET,
                'metadata': {
                    'gameplay_focus': 'frontline clash',
                    'combat': True,
                    'battlefield_event': 'central breach',
                    'unit_formation': 'clear center push',
                },
            },
            {
                'source_type': 'official_press_key_art',
                'width': 1600,
                'height': 2400,
                'kind': 'key_art',
                'path_or_url': 'smoke://iron_vanguard/statue_art.png',
                'metadata': {
                    'symbolic_art': True,
                    'background': 'empty haze',
                    'atmosphere': 'abstract monument',
                },
            },
        ],
    ).to_dict()

    gameplay_asset = next(item for item in decision['asset_scores'] if item['source_type'] == 'steam_screenshot')
    symbolic_asset = next(item for item in decision['asset_scores'] if item['path_or_url'] == 'smoke://iron_vanguard/statue_art.png')

    assert decision['use_ai'] is False
    assert decision['image_source_type'] == 'steam_screenshot'
    assert gameplay_asset['accepted'] is True
    assert 'vdr1_focus_profile_gameplay_bonus' in gameplay_asset['scoring_reason']
    assert 'missing_readable_focus' not in gameplay_asset['rejection_reasons']
    assert symbolic_asset['accepted'] is False
    assert 'missing_readable_focus' in symbolic_asset['rejection_reasons']


def test_visual_decision_engine_allows_composed_atmosphere_scene() -> None:
    decision = build_cover_decision(
        game_title='Whispering Vale',
        genre='atmospheric exploration',
        tags=['moody', 'landscape'],
        short_description='A moody valley scene with strong depth and silhouette composition.',
        offer_type='discount',
        asset_candidates=[
            {
                'source_type': 'steam_library_hero',
                'width': 1800,
                'height': 900,
                'kind': 'library_hero',
                'path_or_url': 'smoke://whispering_vale/atmosphere_scene.png',
                'metadata': {
                    'lighting': 'high contrast dusk',
                    'landmarks': 'ruined arch',
                    'vista': 'valley depth',
                },
            },
            {
                'source_type': 'official_press_key_art',
                'width': 1600,
                'height': 2400,
                'kind': 'key_art',
                'path_or_url': 'smoke://whispering_vale/empty_symbol.png',
                'metadata': {
                    'abstract_art': True,
                    'background': 'empty haze',
                },
            },
        ],
    ).to_dict()

    atmosphere_asset = next(
        item for item in decision['asset_scores'] if item['path_or_url'] == 'smoke://whispering_vale/atmosphere_scene.png'
    )
    empty_asset = next(
        item for item in decision['asset_scores'] if item['path_or_url'] == 'smoke://whispering_vale/empty_symbol.png'
    )

    assert decision['use_ai'] is False
    assert decision['image_source_type'] == 'steam_library_hero'
    assert atmosphere_asset['accepted'] is True
    assert 'vdr1_focus_profile_atmosphere_bonus' in atmosphere_asset['scoring_reason']
    assert atmosphere_asset['total_score'] > empty_asset['total_score']
    assert 'missing_readable_focus' in empty_asset['rejection_reasons']


def test_visual_decision_engine_motion_vehicle_library_hero_can_replace_failed_template_screenshot() -> None:
    decision = build_cover_decision(
        game_title='Forza Horizon 5',
        genre='open-world racing',
        tags=['supercar drift', 'festival speed'],
        short_description='A racing festival surges through bright desert roads with a clear vehicle focus.',
        offer_type='discount',
        asset_candidates=[
            {
                'source_type': 'steam_screenshot',
                'width': 1920,
                'height': 1080,
                'kind': 'screenshot',
                'path_or_url': 'D:\\Telegram_portable_bundle\\output\\cards\\official_asset_cache\\steam\\missing\\steam_screenshot_1.jpg',
                'metadata': {
                    'template_only': True,
                    'vehicle_focus': 'supercar drift',
                    'speed_lines': True,
                    'remote_url': 'https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/1551360/ss_template_01.jpg',
                    'cache_path': 'D:\\Telegram_portable_bundle\\output\\cards\\official_asset_cache\\steam\\missing\\steam_screenshot_1.jpg',
                    'cache_status': 'failed',
                    'asset_download_error': 'http_error:404',
                },
            },
            {
                'source_type': 'steam_library_hero',
                'width': 1800,
                'height': 900,
                'kind': 'library_hero',
                'path_or_url': SMOKE_LOCAL_LANDSCAPE_ASSET,
                'metadata': {
                    'remote_url': 'https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/1551360/library_hero.jpg',
                    'cache_status': 'cached',
                },
            },
        ],
    ).to_dict()

    library_hero_asset = next(item for item in decision['asset_scores'] if item['source_type'] == 'steam_library_hero')
    screenshot_asset = next(item for item in decision['asset_scores'] if item['source_type'] == 'steam_screenshot')

    assert decision['use_ai'] is False
    assert decision['image_source_type'] == 'steam_library_hero'
    assert library_hero_asset['accepted'] is True
    assert screenshot_asset['accepted'] is False
    assert screenshot_asset['accepted'] is False
    assert 'template_only_screenshot_not_available' in screenshot_asset['rejection_reasons']

def test_visual_decision_engine_prefers_hero_asset_over_capsule_when_both_valid() -> None:
    decision = build_cover_decision(
        game_title='Neon Pursuit',
        genre='open-world racing',
        tags=['vehicle', 'drift', 'speed'],
        short_description='A fast vehicle action scene with a clear hero car.',
        offer_type='discount',
        asset_candidates=[
            {
                'source_type': 'steam_library_capsule',
                'width': 600,
                'height': 900,
                'kind': 'library_capsule',
                'path_or_url': SMOKE_LOCAL_PORTRAIT_ASSET,
                'metadata': {
                    'logo_safe': True,
                    'vehicle_focus': 'cover car',
                },
            },
            {
                'source_type': 'steam_library_hero',
                'width': 1800,
                'height': 900,
                'kind': 'library_hero',
                'path_or_url': SMOKE_LOCAL_LANDSCAPE_ASSET,
                'metadata': {
                    'vehicle_focus': 'hero car drift',
                    'foreground': 'supercar',
                    'action': 'high speed turn',
                },
            },
        ],
    ).to_dict()

    capsule_asset = next(item for item in decision['asset_scores'] if item['source_type'] == 'steam_library_capsule')
    hero_asset = next(item for item in decision['asset_scores'] if item['source_type'] == 'steam_library_hero')

    assert decision['use_ai'] is False
    assert decision['image_source_type'] == 'steam_library_hero'
    assert hero_asset['total_score'] > capsule_asset['total_score']


def test_visual_decision_engine_rejects_invalid_collage_candidate_before_ai_fallback() -> None:
    decision = build_cover_decision(
        game_title='Ultimate Strategy Collection',
        genre='strategy collection',
        tags=['bundle', 'strategy'],
        short_description='A bundle candidate with an invalid unresolved collage asset.',
        offer_type='bundle',
        asset_candidates=[
            {
                'source_type': 'collage',
                'width': 1920,
                'height': 1080,
                'kind': 'collage',
                'path_or_url': None,
                'metadata': {
                    'collection': True,
                    'multi_item': True,
                },
            },
            {
                'source_type': 'ai_generated',
                'width': 1280,
                'height': 720,
                'kind': 'generated_preview',
                'path_or_url': 'ai://preview/ultimate_strategy_collection',
                'metadata': {
                    'prompt_intent': 'shot_focused_cinematic_grounded',
                },
            },
        ],
    ).to_dict()

    rejected_collage = next(item for item in decision['asset_scores'] if item['source_type'] == 'collage')

    assert decision['use_ai'] is True
    assert decision['image_source_type'] == 'ai_generated'
    assert rejected_collage['accepted'] is False
    assert 'asset_path_or_url_missing' in rejected_collage['rejection_reasons']
    assert 'rejected_asset_type' in rejected_collage['rejection_reasons']
