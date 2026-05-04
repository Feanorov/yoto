from __future__ import annotations

import io
import json
from pathlib import Path
import shutil

from PIL import Image

from infrastructure.render.cards.asset_sources.asset_cache import AssetCacheDownloadResult
from tools.ai_card_smoke import MINIMAL_SMOKE_GAMES, SMOKE_LOCAL_LANDSCAPE_ASSET, run_scenario


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new('RGBA', (1, 1), (255, 0, 0, 255)).save(buffer, format='PNG')
    return buffer.getvalue()


def _clear_test_cache(identifier: str) -> None:
    cache_dir = Path(__file__).resolve().parents[1] / 'output' / 'cards' / 'official_asset_cache' / 'steam' / identifier
    shutil.rmtree(cache_dir, ignore_errors=True)


def test_ai_card_smoke_current_env_reports_ai_runtime(tmp_path: Path) -> None:
    result = run_scenario(scenario='current_env', output_root=tmp_path)

    assert Path(result['image_path']).exists()
    assert Path(result['manifest_path']).exists()
    assert result['scenario'] == 'current_env'
    assert result['provider_attempted'] == 'comfyui'
    assert result['provider'] == 'comfyui'
    assert result['ai_attempted'] is True
    assert result['ai_succeeded'] is True
    assert result['quality_checked'] is True
    assert result['quality_passed'] is True
    assert result['quality_reject_reason'] is None
    assert result['quality_metrics']['width'] >= result['quality_metrics']['required_width']
    assert result['quality_metrics']['height'] >= result['quality_metrics']['required_height']
    assert result['ai_source_mode'] == 'reference_assisted'
    assert result['reference_assets_used'] is True
    assert result['reference_asset_count'] == 1
    assert result['generated_image_origin'] == 'local_reference_asset'
    assert result['workflow_mode'] == 'scene_content_reference_assisted'
    assert result['prompt_intent'] == 'shot_focused_cinematic_grounded'
    assert result['asset_source_mode'] == 'fixture_fallback'
    assert result['asset_ingestion_mode'] in {'remote_templates_only', 'local_with_errors'}
    assert result['asset_candidates_count'] == 3
    assert 'manifest_entry_not_found' in result['asset_source_errors']
    assert result['asset_source_used_fixture_fallback'] is True
    assert result['asset_download_enabled'] is False
    assert result['asset_download_attempted'] is False
    assert result['asset_download_status'] == 'disabled'
    assert result['asset_download_error'] is None
    assert 'cinematic keyframe shot' in result['prompt_summary']
    assert result['grounding_used'] is True
    assert 'title' in result['grounding_fields_used']
    assert 'genre' in result['grounding_fields_used']
    assert 'tags' in result['grounding_fields_used']
    assert 'short_description' in result['grounding_fields_used']
    assert 'artwork_metadata' in result['grounding_fields_used']
    assert 'title=AI Provider Smoke' in result['grounding_summary']
    assert 'no ui' in result['negative_prompt_summary']
    assert result['cover_decision_card_strategy_version'] == 'v2_mvp'
    assert result['cover_decision_card_type'] in {
        'simple_hero',
        'composite_deal_candidate',
        'official_promo_candidate',
        'giveaway_free',
        'last_resort_official',
        'safe_fallback',
    }
    assert result['cover_decision_card_type_reason'].startswith('card_type:')
    assert result['cover_decision_decision_trace']['card_strategy']['card_type'] == result['cover_decision_card_type']
    assert result['fallback_used'] is False
    assert result['fallback_reason'] is None
    assert result['final_source'] == 'ai'
    assert result['outcome'] == 'ai_runtime'


def test_ai_card_smoke_current_env_supports_hero_action_focus_variant(tmp_path: Path) -> None:
    result = run_scenario(
        scenario='current_env',
        output_root=tmp_path,
        prompt_variant='hero_action_focus',
    )

    assert Path(result['image_path']).exists()
    assert Path(result['manifest_path']).exists()
    assert result['provider'] == 'comfyui'
    assert result['ai_attempted'] is True
    assert result['ai_succeeded'] is True
    assert result['prompt_variant'] == 'hero_action_focus'
    assert result['prompt_intent'] == 'hero_action_focus'
    assert 'hero action frame' in result['prompt_summary']
    assert 'one dominant foreground subject' in result['prompt_summary']
    assert 'close or medium-close framing' in result['prompt_summary']
    assert result['grounding_used'] is True
    assert result['final_source'] == 'ai'
    assert result['outcome'] == 'ai_runtime'


def test_ai_card_smoke_current_env_supports_minimal_game_fixture(tmp_path: Path) -> None:
    game_input = dict(MINIMAL_SMOKE_GAMES[0])
    result = run_scenario(
        scenario='current_env',
        output_root=tmp_path,
        game_input=game_input,
        game_set='minimal',
    )

    assert Path(result['image_path']).exists()
    assert Path(result['manifest_path']).exists()
    assert result['game_set'] == 'minimal'
    assert result['game_slug'] == game_input['slug']
    assert result['asset_source_mode'] == 'steam_cdn_manifest'
    assert result['asset_ingestion_mode'] == 'mixed_local_remote'
    assert result['asset_candidates_count'] >= 6
    assert result['asset_source_errors'] == []
    assert result['asset_source_used_fixture_fallback'] is False
    assert result['asset_download_enabled'] is False
    assert result['asset_download_attempted'] is False
    assert result['asset_download_status'] == 'disabled'
    assert result['game_title'] == game_input['title']
    assert result['genre'] == game_input['genre']
    assert result['tags'] == game_input['tags']
    assert result['short_description'] == game_input['short_description']
    assert result['prompt_variant'] == 'shot_focused_cinematic_grounded'
    assert result['output_path'] == result['image_path']
    assert game_input['slug'] in result['run_root']
    assert result['provider_attempted'] is None
    assert result['provider'] == 'artwork'
    assert result['ai_attempted'] is False
    assert result['ai_succeeded'] is False
    assert result['decision_asset_used'] is True
    assert result['decision_asset_use_reason'] == 'cover_decision_selected_official_asset'
    assert result['decision_asset_reject_reason'] is None
    assert result['actual_image_source_type'] == result['cover_decision_image_source_type']
    assert result['actual_image_path_or_url'] == result['cover_decision_selected_asset']['path_or_url']
    assert Path(result['actual_image_path_or_url']).exists()
    assert result['decision_asset_matches_actual_source'] is True
    assert result['final_source'] == 'asset'
    assert result['outcome'] == 'official_asset'


def test_ai_card_smoke_manifest_includes_visual_intent_fields(tmp_path: Path) -> None:
    game_input = dict(MINIMAL_SMOKE_GAMES[0])
    result = run_scenario(
        scenario='current_env',
        output_root=tmp_path,
        game_input=game_input,
        game_set='minimal',
    )
    manifest = json.loads(Path(result['manifest_path']).read_text(encoding='utf-8'))
    provider_cover_decision = manifest['provider_metadata']['cover_decision']
    trace_visual_intent = provider_cover_decision['decision_trace']['visual_intent']

    assert result['cover_decision']['visual_intent_type']
    assert result['cover_decision']['visual_intent_reason'].startswith('visual_intent:')
    assert result['cover_decision']['visual_intent_version'] == 'v1_mvp'
    assert provider_cover_decision['visual_intent_type'] == result['cover_decision']['visual_intent_type']
    assert provider_cover_decision['visual_intent_reason'] == result['cover_decision']['visual_intent_reason']
    assert provider_cover_decision['visual_intent_version'] == 'v1_mvp'
    assert trace_visual_intent['visual_intent_type'] == provider_cover_decision['visual_intent_type']
    assert trace_visual_intent['visual_intent_version'] == 'v1_mvp'


def test_ai_card_smoke_current_env_supports_game_eval_seed_layout(tmp_path: Path) -> None:
    game_input = dict(MINIMAL_SMOKE_GAMES[1])
    result = run_scenario(
        scenario='current_env',
        output_root=tmp_path,
        game_input=game_input,
        game_set='minimal',
        seed=3,
        game_eval=True,
    )
    rejected_screenshot = next(
        item for item in result['cover_decision_rejected_assets'] if item.get('source_type') == 'steam_screenshot'
    )

    assert Path(result['image_path']).exists()
    assert Path(result['manifest_path']).exists()
    assert result['game_eval'] is True
    assert result['seed'] == 3
    assert result['game_slug'] == game_input['slug']
    assert result['asset_source_mode'] == 'steam_cdn_manifest'
    assert result['asset_ingestion_mode'] == 'mixed_local_remote'
    assert result['asset_candidates_count'] >= 5
    assert result['asset_source_errors'] == []
    assert result['prompt_variant'] == 'shot_focused_cinematic_grounded'
    assert result['output_path'] == result['image_path']
    assert 'ai_eval' in result['run_root']
    assert f"seed_{result['seed']}" in result['run_root']
    assert result['provider_metadata']['seed'] == 3
    assert result['provider_metadata']['output_path'] == result['image_path']
    assert result['provider'] == 'artwork'
    assert result['ai_attempted'] is False
    assert result['decision_asset_used'] is True
    assert result['actual_image_source_type'] == result['cover_decision_image_source_type']
    assert result['actual_image_source_type'] != 'steam_screenshot'
    assert 'ui_heavy_screenshot_for_single_title' in rejected_screenshot['rejection_reasons']
    assert result['final_source'] == 'asset'
    assert result['outcome'] == 'official_asset'


def test_ai_card_smoke_download_assets_rejects_civilization_ui_screenshot(tmp_path: Path) -> None:
    png_bytes = _png_bytes()
    screenshot_cache_path = (
        Path(__file__).resolve().parents[1]
        / 'output'
        / 'cards'
        / 'official_asset_cache'
        / 'steam'
        / '289070'
        / 'steam_screenshot_1.jpg'
    )
    screenshot_cache_path.unlink(missing_ok=True)
    try:
        def fake_downloader(*, remote_url: str, cache_path: str, timeout_seconds: int, max_bytes: int) -> AssetCacheDownloadResult:
            target = Path(cache_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(png_bytes)
            return AssetCacheDownloadResult(
                cache_path=str(target),
                cache_status='downloaded',
                download_attempted=True,
                bytes_written=len(png_bytes),
                content_type='image/png',
            )

        game_input = dict(MINIMAL_SMOKE_GAMES[1])
        result = run_scenario(
            scenario='quality_reject',
            output_root=tmp_path,
            game_input=game_input,
            game_set='minimal',
            download_assets=True,
            asset_downloader=fake_downloader,
        )
        rejected_screenshot = next(
            item for item in result['cover_decision_rejected_assets'] if item.get('source_type') == 'steam_screenshot'
        )

        assert result['cover_decision_image_source_type'] != 'steam_screenshot'
        assert result['decision_asset_used'] is True
        assert Path(screenshot_cache_path).exists()
        assert result['actual_image_path_or_url'] == result['selected_asset_cache_path']
        assert result['actual_image_path_or_url'] != str(screenshot_cache_path)
        assert result['actual_image_path_or_url'] != SMOKE_LOCAL_LANDSCAPE_ASSET
        assert Path(result['actual_image_path_or_url']).exists()
        assert 'ui_heavy_screenshot_for_single_title' in rejected_screenshot['rejection_reasons']
        assert result['provider'] == 'artwork'
        assert result['final_source'] == 'asset'
    finally:
        screenshot_cache_path.unlink(missing_ok=True)


def test_ai_card_smoke_broken_comfyui_falls_back_without_crash(tmp_path: Path) -> None:
    result = run_scenario(scenario='broken_comfyui', output_root=tmp_path)

    assert Path(result['image_path']).exists()
    assert Path(result['manifest_path']).exists()
    assert result['scenario'] == 'broken_comfyui'
    assert result['provider_attempted'] == 'comfyui'
    assert result['provider'] == 'placeholder'
    assert result['quality_checked'] is False
    assert result['quality_passed'] is False
    assert result['quality_reject_reason'] is None
    assert result['ai_source_mode'] == 'pure_generation'
    assert result['reference_assets_used'] is False
    assert result['reference_asset_count'] == 0
    assert result['generated_image_origin'] == 'comfyui_runtime_unavailable'
    assert result['workflow_mode'] == 'scene_content_pure'
    assert result['fallback_used'] is True
    assert result['fallback_reason'] == 'placeholder_ai_failed'
    assert result['final_source'] == 'fallback'
    assert result['outcome'] == 'ai_fallback'
    assert result['selected_source'] == 'placeholder'
    assert result['decision_reason'] == 'placeholder_ai_failed'
    assert result['ai_attempted'] is True
    assert result['ai_succeeded'] is False
    assert result['scenario_metadata']['requested_ai_provider'] == 'comfyui'
    assert result['scenario_metadata']['simulated_ai_failure'] == 'timeout'


def test_ai_card_smoke_quality_reject_falls_back_without_crash(tmp_path: Path) -> None:
    result = run_scenario(scenario='quality_reject', output_root=tmp_path)

    assert Path(result['image_path']).exists()
    assert Path(result['manifest_path']).exists()
    assert result['scenario'] == 'quality_reject'
    assert result['provider_attempted'] == 'comfyui'
    assert result['provider'] == 'placeholder'
    assert result['ai_attempted'] is True
    assert result['ai_succeeded'] is False
    assert result['quality_checked'] is True
    assert result['quality_passed'] is False
    assert result['quality_reject_reason'] == 'image_below_required_size'
    assert result['quality_metrics']['width'] == 64
    assert result['quality_metrics']['height'] == 64
    assert result['quality_metrics']['required_width'] == 1280
    assert result['quality_metrics']['required_height'] == 720
    assert result['ai_source_mode'] == 'pure_generation'
    assert result['reference_assets_used'] is False
    assert result['reference_asset_count'] == 0
    assert result['generated_image_origin'] == 'synthetic_quality_reject'
    assert result['workflow_mode'] == 'scene_content_pure'
    assert result['fallback_used'] is True
    assert result['fallback_reason'] == 'placeholder_ai_quality_reject'
    assert result['final_source'] == 'fallback'
    assert result['outcome'] == 'ai_fallback'
    assert result['selected_source'] == 'placeholder'
    assert result['decision_reason'] == 'placeholder_ai_quality_reject'
    assert result['scenario_metadata']['requested_ai_provider'] == 'comfyui'
    assert result['scenario_metadata']['simulated_ai_failure'] == 'quality_reject'


def test_ai_card_smoke_quality_reject_uses_valid_decision_asset_before_ai(tmp_path: Path) -> None:
    game_input = dict(MINIMAL_SMOKE_GAMES[0])
    result = run_scenario(
        scenario='quality_reject',
        output_root=tmp_path,
        game_input=game_input,
        game_set='minimal',
    )
    selected_asset = result['cover_decision_selected_asset']
    selected_asset_metadata = selected_asset['metadata']
    selected_asset_path = Path(selected_asset['path_or_url'])

    assert result['offer_type'] == game_input['offer_type']
    assert result['asset_source_mode'] == 'steam_cdn_manifest'
    assert result['asset_ingestion_mode'] == 'mixed_local_remote'
    assert result['cover_decision']['genre_cluster'] == 'character_driven'
    assert result['cover_decision_genre_cluster'] == 'character_driven'
    assert result['cover_decision_visual_type'] == 'character'
    assert result['cover_decision_use_ai'] is False
    assert result['cover_decision_ai_fallback_reason'] is None
    assert result['cover_decision_official_assets_available'] is True
    assert result['cover_decision_official_assets_rejected_count'] >= 1
    assert result['cover_decision_readability_score'] >= 0.55
    assert result['cover_decision_focus_score'] >= 0.50
    assert result['cover_decision_image_source_type'] in {
        'official_press_key_art',
        'steam_library_capsule',
        'steam_main_capsule',
    }
    assert result['cover_decision_layout_type'] in {'portrait_single', 'portrait_single_logo_safe'}
    assert result['cover_decision_decision_reason'].startswith('official_first_selected')
    assert selected_asset == result['cover_decision']['selected_asset']
    assert selected_asset['source_type'] == result['cover_decision_image_source_type']
    assert selected_asset['source_type'] != 'placeholder'
    assert selected_asset['accepted'] is True
    assert selected_asset_path.exists()
    assert selected_asset_path == Path(selected_asset_metadata['cache_path'])
    assert selected_asset_metadata['cache_status'] in {'cached', 'downloaded'}
    assert isinstance(result['cover_decision_rejected_assets'], list)
    assert isinstance(result['cover_decision_decision_trace'], dict)
    assert 'thresholds' in result['cover_decision_decision_trace']
    assert result['provider'] == 'artwork'
    assert result['ai_attempted'] is False
    assert result['decision_asset_used'] is True
    assert result['decision_asset_use_reason'] == 'cover_decision_selected_official_asset'
    assert result['decision_asset_reject_reason'] is None
    assert result['actual_image_source_type'] == result['cover_decision_image_source_type']
    assert result['actual_image_source_type'] != 'placeholder'
    assert result['actual_image_path_or_url'] == selected_asset['path_or_url']
    assert result['selected_asset_cache_path'] == selected_asset_metadata['cache_path']
    assert result['selected_asset_cache_status'] in {'cached', 'downloaded'}
    assert result['decision_asset_matches_actual_source'] is True
    assert result['final_source'] == 'asset'
    assert result['outcome'] == 'official_asset'


def test_ai_card_smoke_quality_reject_rejects_nonlocal_bundle_decision_asset(tmp_path: Path) -> None:
    game_input = dict(MINIMAL_SMOKE_GAMES[4])
    result = run_scenario(
        scenario='quality_reject',
        output_root=tmp_path,
        game_input=game_input,
        game_set='minimal',
    )

    assert result['cover_decision_genre_cluster'] == 'bundle_multi_item'
    assert result['asset_source_mode'] == 'local_manifest'
    assert result['asset_ingestion_mode'] == 'local_with_errors'
    assert result['asset_source_errors'] == []
    assert result['cover_decision_visual_type'] == 'collage'
    assert result['cover_decision_use_ai'] is False
    assert result['decision_asset_used'] is False
    assert result['decision_asset_use_reason'] is None
    assert result['decision_asset_reject_reason'] == 'invalid_or_nonlocal_asset_path'
    assert result['actual_image_source_type'] == 'placeholder'
    assert result['actual_image_path_or_url'] is None
    assert result['decision_asset_matches_actual_source'] is False
    assert result['provider'] == 'placeholder'
    assert result['ai_attempted'] is True
    assert result['fallback_used'] is True
    assert result['final_source'] == 'fallback'
    assert result['outcome'] == 'ai_fallback'


def test_ai_card_smoke_quality_reject_remote_only_asset_stays_out_of_renderer(tmp_path: Path) -> None:
    _clear_test_cache('999993')
    result = run_scenario(
        scenario='quality_reject',
        output_root=tmp_path,
        game_input={
            'slug': 'remote_download_success_demo',
            'store_id': 'steam:remote_download_success_demo',
            'source_hint': 'steam',
            'steam_app_id': '999993',
            'title': 'Remote Download Success Demo',
            'platform': 'STEAM',
            'offer_type': 'discount',
            'genre': 'roguelike action',
            'tags': ['hero', 'combat'],
            'short_description': 'A remote-only smoke title with CDN-derived assets and no cached local files.',
            'asset_candidates': [],
        },
        game_set='minimal',
    )

    assert result['asset_source_mode'] == 'steam_cdn_manifest'
    assert result['asset_ingestion_mode'] == 'remote_templates_only'
    assert result['decision_asset_used'] is False
    assert result['selected_asset_remote_url'] is not None
    assert result['selected_asset_cache_path'] is not None
    assert result['selected_asset_cache_status'] == 'not_requested'
    assert result['decision_asset_reject_reason'] == 'remote_not_cached'
    assert result['provider'] == 'placeholder'
    assert result['fallback_used'] is True
    assert result['final_source'] == 'fallback'
    assert result['outcome'] == 'ai_fallback'


def test_ai_card_smoke_download_assets_promotes_downloaded_remote_candidate(tmp_path: Path) -> None:
    _clear_test_cache('999994')
    png_bytes = _png_bytes()

    def fake_downloader(*, remote_url: str, cache_path: str, timeout_seconds: int, max_bytes: int) -> AssetCacheDownloadResult:
        target = Path(cache_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(png_bytes)
        return AssetCacheDownloadResult(
            cache_path=str(target),
            cache_status='downloaded',
            download_attempted=True,
            bytes_written=len(png_bytes),
            content_type='image/png',
        )

    result = run_scenario(
        scenario='quality_reject',
        output_root=tmp_path,
        game_input={
            'slug': 'remote_download_failure_demo',
            'store_id': 'steam:remote_download_failure_demo',
            'source_hint': 'steam',
            'steam_app_id': '999994',
            'title': 'Remote Download Failure Demo',
            'platform': 'STEAM',
            'offer_type': 'discount',
            'genre': 'roguelike action',
            'tags': ['hero', 'combat'],
            'short_description': 'A remote-only smoke title with CDN-derived assets and no cached local files.',
            'asset_candidates': [],
        },
        game_set='minimal',
        download_assets=True,
        asset_downloader=fake_downloader,
    )

    assert result['asset_download_enabled'] is True
    assert result['asset_download_attempted'] is True
    assert result['asset_download_status'] == 'downloaded'
    assert result['asset_download_error'] is None
    assert 1 <= result['downloaded_asset_count'] <= 3
    assert result['failed_asset_count'] == 0
    assert result['selected_asset_cache_status'] == 'downloaded'
    assert result['decision_asset_used'] is True
    assert result['provider'] == 'artwork'
    assert result['fallback_used'] is False
    assert result['final_source'] == 'asset'
    assert result['outcome'] == 'official_asset'


def test_ai_card_smoke_download_assets_failure_keeps_fallback_safe(tmp_path: Path) -> None:
    _clear_test_cache('999995')
    def fake_downloader(*, remote_url: str, cache_path: str, timeout_seconds: int, max_bytes: int) -> AssetCacheDownloadResult:
        return AssetCacheDownloadResult(
            cache_path=cache_path,
            cache_status='failed',
            download_attempted=True,
            error='offline_guarded_failure',
        )

    result = run_scenario(
        scenario='quality_reject',
        output_root=tmp_path,
        game_input={
            'slug': 'remote_download_failure_demo_retry',
            'store_id': 'steam:remote_download_failure_demo_retry',
            'source_hint': 'steam',
            'steam_app_id': '999995',
            'title': 'Remote Download Failure Demo Retry',
            'platform': 'STEAM',
            'offer_type': 'discount',
            'genre': 'roguelike action',
            'tags': ['hero', 'combat'],
            'short_description': 'A remote-only smoke title with CDN-derived assets and no cached local files.',
            'asset_candidates': [],
        },
        game_set='minimal',
        download_assets=True,
        asset_downloader=fake_downloader,
    )

    assert result['asset_download_enabled'] is True
    assert result['asset_download_attempted'] is True
    assert result['asset_download_status'] == 'failed'
    assert result['asset_download_error'] is not None
    assert 1 <= result['failed_asset_count'] <= 3
    assert result['selected_asset_cache_status'] == 'failed'
    assert result['decision_asset_used'] is False
    assert result['decision_asset_reject_reason'] == 'remote_not_cached'
    assert result['provider'] == 'placeholder'
    assert result['fallback_used'] is True
    assert result['final_source'] == 'fallback'
