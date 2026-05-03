from __future__ import annotations

from pathlib import Path

from infrastructure.render.cards.visual_decision_engine import build_cover_decision, resolve_cover_decision_asset_bridge
from tools.ai_card_smoke import MINIMAL_SMOKE_GAMES


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


def test_visual_decision_engine_civilization_prefers_gameplay_assets() -> None:
    game_input = dict(MINIMAL_SMOKE_GAMES[1])
    decision = build_cover_decision(
        game_title=game_input['title'],
        genre=game_input['genre'],
        tags=game_input['tags'],
        short_description=game_input['short_description'],
        offer_type=game_input['offer_type'],
        asset_candidates=game_input['asset_candidates'],
    ).to_dict()

    assert decision['genre_cluster'] == 'gameplay_first'
    assert decision['visual_type'] == 'gameplay'
    assert decision['layout_type'] in {'gameplay_frame', 'landscape_scene_crop'}
    assert decision['use_ai'] is False
    assert decision['image_source_type'] == 'steam_screenshot'


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
