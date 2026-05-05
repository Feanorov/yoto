from __future__ import annotations

import io
import json
from pathlib import Path
import shutil

from PIL import Image

from infrastructure.render.cards.asset_sources.asset_cache import AssetCacheDownloadResult
from infrastructure.render.cards.image_providers import ArtworkImageProvider, ImageResolutionRequest, ResolvedImage, YotoImageResolver
from infrastructure.render.cards.visual_decision_engine import build_cover_decision
from tools.ai_card_smoke import (
    ASSET_POOL_DIAGNOSTIC_VERSION,
    GAME_EVAL_EXPANDED_SMOKE_GAMES,
    MINIMAL_SMOKE_GAMES,
    SMOKE_LOCAL_LANDSCAPE_ASSET,
    classify_outcome,
    infer_fallback_reason,
    infer_fallback_used,
    infer_final_source,
    render_ai_card_smoke,
    resolve_asset_candidates_for_game,
    run_scenario,
)


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new('RGBA', (1, 1), (255, 0, 0, 255)).save(buffer, format='PNG')
    return buffer.getvalue()


def _clear_test_cache(identifier: str) -> None:
    cache_dir = Path(__file__).resolve().parents[1] / 'output' / 'cards' / 'official_asset_cache' / 'steam' / identifier
    shutil.rmtree(cache_dir, ignore_errors=True)


class _FakeProvider:
    def __init__(self, result: ResolvedImage | None, *, enabled: bool = True) -> None:
        self.result = result
        self.enabled = enabled
        self.calls = 0

    def resolve(self, request: ImageResolutionRequest) -> ResolvedImage | None:
        self.calls += 1
        return self.result


def _resolver_request(*, cover_decision: dict[str, object], mode: str = 'ai_first') -> ImageResolutionRequest:
    return ImageResolutionRequest(
        artwork_path=None,
        title='Bridge Safety Smoke',
        platform='STEAM',
        slug='bridge_safety_smoke',
        card_type='DISCOUNT',
        lane='high_value_discount',
        mode=mode,
        priority='',
        image_size=(1280, 720),
        cover_decision=cover_decision,
    )


def _write_test_png(path: Path, *, color: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', (1280, 720), color).save(path, format='PNG')


def _remote_only_game_input(*, steam_app_id: str, slug: str, title: str) -> dict[str, object]:
    return {
        'slug': slug,
        'store_id': f'steam:{slug}',
        'source_hint': 'steam',
        'steam_app_id': steam_app_id,
        'title': title,
        'platform': 'STEAM',
        'offer_type': 'discount',
        'genre': 'roguelike action',
        'tags': ['hero', 'combat'],
        'short_description': 'A remote-only smoke title with CDN-derived assets and no cached local files.',
        'asset_candidates': [],
    }


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


def test_ai_card_smoke_manifest_includes_visual_rescue_fields(tmp_path: Path) -> None:
    game_input = dict(MINIMAL_SMOKE_GAMES[2])
    result = run_scenario(
        scenario='current_env',
        output_root=tmp_path,
        game_input=game_input,
        game_set='minimal',
    )
    manifest = json.loads(Path(result['manifest_path']).read_text(encoding='utf-8'))
    provider_cover_decision = manifest['provider_metadata']['cover_decision']
    trace_visual_rescue = provider_cover_decision['decision_trace']['visual_rescue']

    assert provider_cover_decision['rescue_needed'] == result['cover_decision']['rescue_needed']
    assert provider_cover_decision['rescue_type'] == result['cover_decision']['rescue_type']
    assert provider_cover_decision['rescue_version'] == 'v1_mvp'
    assert trace_visual_rescue['rescue_needed'] == provider_cover_decision['rescue_needed']
    assert trace_visual_rescue['rescue_type'] == provider_cover_decision['rescue_type']
    assert trace_visual_rescue['rescue_version'] == 'v1_mvp'
    assert result['rescue_needed'] == result['visual_rescue']['rescue_needed']
    assert result['rescue_type'] == result['visual_rescue']['rescue_type']
    assert result['rescue_version'] == 'v1_mvp'


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


def test_ai_card_smoke_expanded_game_definitions_include_steam_app_ids_for_real_asset_eval() -> None:
    missing_steam_ids = [
        str(game_input.get('slug'))
        for game_input in GAME_EVAL_EXPANDED_SMOKE_GAMES
        if not str(game_input.get('steam_app_id') or '').strip()
    ]

    assert missing_steam_ids == []
    assert all(bool(game_input.get('real_asset_eval_expected', False)) for game_input in GAME_EVAL_EXPANDED_SMOKE_GAMES)
    assert all(game_input.get('local_assets') == {} for game_input in GAME_EVAL_EXPANDED_SMOKE_GAMES)


def test_ai_card_smoke_expanded_supported_games_resolve_steam_cdn_candidate_pools() -> None:
    for game_input in GAME_EVAL_EXPANDED_SMOKE_GAMES:
        payload = resolve_asset_candidates_for_game(dict(game_input))
        source_origins = {
            str(
                candidate.get('source_origin')
                or (candidate.get('metadata') or {}).get('source_origin')
                or ''
            ).strip()
            for candidate in payload['asset_candidates']
            if isinstance(candidate, dict)
        }

        assert payload['asset_source_mode'] == 'steam_cdn_manifest'
        assert payload['asset_ingestion_mode'] in {'mixed_local_remote', 'remote_templates_only'}
        assert payload['asset_candidates_count'] > 1
        assert any(origin == 'steam_cdn_manifest' for origin in source_origins)
        assert 'steam_screenshot' in payload['asset_candidate_source_types']


def test_ai_card_smoke_game_eval_writes_asset_pool_diagnostics(tmp_path: Path) -> None:
    batch_root = render_ai_card_smoke(
        scenario='quality_reject',
        output_root=tmp_path,
        game_set='minimal',
        game_eval=True,
        seeds_per_game=1,
    )
    diagnostics_path = batch_root / 'asset_pool_diagnostics.json'

    assert diagnostics_path.exists()

    payload = json.loads(diagnostics_path.read_text(encoding='utf-8'))
    assert payload['run_id'] == batch_root.name
    assert payload['diagnostic_version'] == ASSET_POOL_DIAGNOSTIC_VERSION
    assert payload['errors'] == []

    hades = next(item for item in payload['games'] if item['slug'] == 'hades_ii')
    hades_suspicious = next(item for item in hades['candidates'] if item['suspicious_fixture'] is True)

    assert hades['asset_source_mode'] == 'steam_cdn_manifest'
    assert hades['asset_ingestion_mode'] == 'mixed_local_remote'
    assert hades['candidate_count'] == len(hades['candidates'])
    assert hades['selected']['image_source_type'] in {'official_press_key_art', 'steam_library_capsule', 'steam_main_capsule'}
    assert 'remote_url' in hades['selected']
    assert 'cache_path' in hades['selected']
    assert 'selected_asset_cache_status' in hades['selected']
    assert 'local_cached_file_exists' in hades['selected']
    assert 'fallback_reason' in hades['selected']
    assert any(item['source_family'] == 'steam_cdn' for item in hades['candidates'])
    assert hades_suspicious['source_family'] == 'local_manifest'
    assert hades_suspicious['is_local_path'] is True
    assert hades_suspicious['local_file_exists'] is True
    assert hades_suspicious['path_or_url'].endswith('fallback_game_image.png')

    civilization = next(item for item in payload['games'] if item['slug'] == 'civilization_vi')
    civilization_suspicious = next(item for item in civilization['candidates'] if item['suspicious_fixture'] is True)

    assert civilization_suspicious['source_family'] == 'local_manifest'
    assert civilization_suspicious['path_or_url'].endswith('game.png')
    assert civilization_suspicious['debug']['selection_ranking'] is not None

    pacific_drive = next(item for item in payload['games'] if item['slug'] == 'pacific_drive')

    assert pacific_drive['steam_cdn_candidate_count'] == 0
    assert pacific_drive['local_manifest_candidate_count'] >= 1
    assert pacific_drive['suspicious_fixture_only'] is True
    assert 'missing_steam_app_id' in str(pacific_drive['no_steam_cdn_reason'] or '')


def test_ai_card_smoke_expanded_game_eval_uses_real_official_candidate_pools(tmp_path: Path) -> None:
    batch_root = render_ai_card_smoke(
        scenario='quality_reject',
        output_root=tmp_path,
        game_set='expanded',
        game_eval=True,
        seeds_per_game=1,
    )
    diagnostics_path = batch_root / 'asset_pool_diagnostics.json'

    assert diagnostics_path.exists()

    payload = json.loads(diagnostics_path.read_text(encoding='utf-8'))
    assert payload['diagnostic_version'] == ASSET_POOL_DIAGNOSTIC_VERSION
    assert payload['errors'] == []
    assert len(payload['games']) == len(GAME_EVAL_EXPANDED_SMOKE_GAMES)

    for game in payload['games']:
        assert str(game.get('steam_app_id') or '').strip()
        assert game['real_asset_eval_expected'] is True
        assert game['asset_source_mode'] == 'steam_cdn_manifest'
        assert game['candidate_count'] > 1
        assert game['steam_cdn_candidate_count'] >= 1
        assert game['local_manifest_candidate_count'] == 0
        assert game['suspicious_fixture_only'] is False
        assert game['no_steam_cdn_reason'] is None


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


def test_ai_card_smoke_nonlocal_smoke_selected_official_does_not_silently_fall_to_ai(tmp_path: Path) -> None:
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
    assert result['ai_attempted'] is False
    assert result['ai_succeeded'] is False
    assert result['fallback_used'] is True
    assert result['fallback_reason'] == 'official_asset_bridge_invalid'
    assert result['final_source'] == 'fallback'
    assert result['outcome'] == 'ai_hard_failure'
    assert result['rescue_needed'] is True
    assert result['rescue_reason'] == 'rescue:bridge_or_valid_asset_required:official_asset_bridge_invalid'
    assert result['rescue_type'] == 'bridge_or_valid_asset_required'
    assert 'invalid_or_nonlocal_asset_path' in result['rescue_blockers']


def test_ai_card_smoke_quality_reject_remote_only_asset_triggers_bridge_cache_request(tmp_path: Path) -> None:
    _clear_test_cache('999993')
    png_bytes = _png_bytes()
    download_calls: list[tuple[str, str]] = []

    def fake_downloader(*, remote_url: str, cache_path: str, timeout_seconds: int, max_bytes: int) -> AssetCacheDownloadResult:
        download_calls.append((remote_url, cache_path))
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

    game_input = _remote_only_game_input(
        steam_app_id='999993',
        slug='remote_bridge_cache_request_demo',
        title='Remote Bridge Cache Request Demo',
    )
    asset_payload = resolve_asset_candidates_for_game(dict(game_input))
    pre_cache_decision = build_cover_decision(
        game_title=str(game_input['title']),
        genre=str(game_input['genre']),
        tags=[str(item) for item in game_input['tags']],
        short_description=str(game_input['short_description']),
        offer_type=str(game_input['offer_type']),
        asset_candidates=asset_payload['asset_candidates'],
    ).to_dict()
    result = run_scenario(
        scenario='quality_reject',
        output_root=tmp_path,
        game_input=game_input,
        game_set='minimal',
        asset_downloader=fake_downloader,
    )

    assert result['asset_source_mode'] == 'steam_cdn_manifest'
    assert result['asset_ingestion_mode'] == 'remote_templates_only'
    assert len(download_calls) == 1
    assert result['cover_decision_image_source_type'] == pre_cache_decision['image_source_type']
    assert result['cover_decision_selected_asset']['source_type'] == pre_cache_decision['selected_asset']['source_type']
    assert result['selected_asset_remote_url'] is not None
    assert result['selected_asset_cache_path'] is not None
    assert result['selected_asset_cache_status'] == 'downloaded'
    assert result['selected_asset_cache_status'] != 'not_requested'
    assert result['selected_asset_local_file_exists'] is True
    assert result['selected_asset_cache_download_attempted'] is True
    assert result['selected_asset_cache_error'] is None
    assert result['decision_asset_used'] is True
    assert result['actual_image_path_or_url'] == result['selected_asset_cache_path']
    assert Path(str(result['selected_asset_cache_path'])).exists()
    assert result['provider'] == 'artwork'
    assert result['fallback_used'] is False
    assert result['final_source'] == 'asset'
    assert result['outcome'] == 'official_asset'


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
        game_input=_remote_only_game_input(
            steam_app_id='999994',
            slug='remote_download_failure_demo',
            title='Remote Download Failure Demo',
        ),
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
    assert result['selected_asset_cache_status'] in {'cached', 'downloaded'}
    assert result['selected_asset_local_file_exists'] is True
    assert isinstance(result['selected_asset_cache_download_attempted'], bool)
    assert result['selected_asset_cache_error'] is None
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
        game_input=_remote_only_game_input(
            steam_app_id='999995',
            slug='remote_download_failure_demo_retry',
            title='Remote Download Failure Demo Retry',
        ),
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
    assert result['selected_asset_local_file_exists'] is False
    assert result['selected_asset_cache_download_attempted'] is True
    assert result['selected_asset_cache_error'] == 'offline_guarded_failure'
    assert result['decision_asset_used'] is False
    assert result['decision_asset_reject_reason'] == 'remote_not_cached'
    assert result['provider'] == 'placeholder'
    assert result['fallback_used'] is True
    assert result['final_source'] == 'fallback'


def test_ai_card_smoke_bridge_cache_failure_keeps_fallback_safe_without_bulk_download(tmp_path: Path) -> None:
    _clear_test_cache('999996')

    def fake_downloader(*, remote_url: str, cache_path: str, timeout_seconds: int, max_bytes: int) -> AssetCacheDownloadResult:
        return AssetCacheDownloadResult(
            cache_path=cache_path,
            cache_status='failed',
            download_attempted=True,
            error='bridge_cache_failure',
        )

    result = run_scenario(
        scenario='quality_reject',
        output_root=tmp_path,
        game_input=_remote_only_game_input(
            steam_app_id='999996',
            slug='remote_bridge_cache_failure_demo',
            title='Remote Bridge Cache Failure Demo',
        ),
        game_set='minimal',
        asset_downloader=fake_downloader,
    )

    assert result['asset_download_enabled'] is False
    assert result['asset_download_attempted'] is False
    assert result['asset_download_status'] == 'disabled'
    assert result['selected_asset_cache_status'] == 'failed'
    assert result['selected_asset_cache_status'] != 'not_requested'
    assert result['selected_asset_cache_download_attempted'] is True
    assert result['selected_asset_cache_error'] == 'bridge_cache_failure'
    assert result['selected_asset_local_file_exists'] is False
    assert result['decision_asset_used'] is False
    assert result['decision_asset_reject_reason'] == 'remote_not_cached'
    assert result['provider'] == 'placeholder'
    assert result['fallback_used'] is True
    assert result['final_source'] == 'fallback'


def test_valid_cached_official_asset_still_uses_asset(tmp_path: Path) -> None:
    cached_asset_path = tmp_path / 'official_asset_cache' / 'steam_main_capsule.png'
    generated_asset_path = tmp_path / 'generated' / 'ai.png'
    _write_test_png(cached_asset_path, color='#4477aa')
    _write_test_png(generated_asset_path, color='#22aa55')

    ai_provider = _FakeProvider(
        ResolvedImage(
            image=Image.new('RGB', (1280, 720), '#22aa55'),
            metadata={
                'selected_source': 'ai',
                'provider_name': 'ai',
                'asset_path': str(generated_asset_path.resolve()),
            },
        )
    )
    resolver = YotoImageResolver(
        artwork_provider=ArtworkImageProvider(),
        ai_provider=ai_provider,
        placeholder_provider=_FakeProvider(
            ResolvedImage(
                image=Image.new('RGB', (1280, 720), '#111111'),
                metadata={'selected_source': 'placeholder', 'provider_name': 'placeholder'},
            )
        ),
        mode='ai_first',
    )

    result = resolver.resolve(
        _resolver_request(
            cover_decision={
                'use_ai': False,
                'image_source_type': 'steam_main_capsule',
                'selected_asset': {
                    'source_type': 'steam_main_capsule',
                    'path_or_url': 'https://cdn.example.com/steam_main_capsule.png',
                    'cache_path': str(cached_asset_path),
                    'metadata': {
                        'cache_path': str(cached_asset_path),
                        'cache_status': 'downloaded',
                    },
                },
            }
        )
    )

    final_source = infer_final_source(str(result.metadata.get('selected_source') or ''))

    assert final_source == 'asset'
    assert result.metadata['decision_asset_used'] is True
    assert result.metadata['decision_asset_reject_reason'] is None
    assert result.metadata['actual_image_source_type'] == 'steam_main_capsule'
    assert result.metadata['actual_image_path_or_url'] == str(cached_asset_path.resolve())
    assert result.metadata['decision_asset_matches_actual_source'] is True
    assert ai_provider.calls == 0


def test_nonlocal_smoke_selected_official_does_not_silently_fall_to_ai(tmp_path: Path) -> None:
    generated_asset_path = tmp_path / 'generated' / 'ai.png'
    _write_test_png(generated_asset_path, color='#22aa55')

    ai_provider = _FakeProvider(
        ResolvedImage(
            image=Image.new('RGB', (1280, 720), '#22aa55'),
            metadata={
                'selected_source': 'ai',
                'provider_name': 'ai',
                'asset_path': str(generated_asset_path.resolve()),
            },
        )
    )
    resolver = YotoImageResolver(
        artwork_provider=ArtworkImageProvider(),
        ai_provider=ai_provider,
        placeholder_provider=_FakeProvider(
            ResolvedImage(
                image=Image.new('RGB', (1280, 720), '#111111'),
                metadata={'selected_source': 'placeholder', 'provider_name': 'placeholder'},
            )
        ),
        mode='ai_first',
    )

    result = resolver.resolve(
        _resolver_request(
            cover_decision={
                'use_ai': False,
                'image_source_type': 'steam_main_capsule',
                'selected_asset': {
                    'source_type': 'steam_main_capsule',
                    'path_or_url': 'smoke://bundle/item_01_capsule.png',
                    'metadata': {
                        'source_origin': 'local_manifest',
                        'cache_status': 'missing',
                    },
                },
            }
        )
    )

    final_source = infer_final_source(str(result.metadata.get('selected_source') or ''))
    fallback_used = infer_fallback_used(final_source)
    fallback_reason = infer_fallback_reason(
        fallback_used=fallback_used,
        decision_reason=result.metadata.get('decision_reason'),
    )
    outcome = classify_outcome(
        final_source=final_source,
        ai_attempted=bool(result.metadata.get('ai_attempted', False)),
        ai_succeeded=bool(result.metadata.get('ai_succeeded', False)),
        fallback_used=fallback_used,
    )

    assert final_source != 'ai'
    assert result.metadata['selected_source'] == 'placeholder'
    assert result.metadata['actual_image_source_type'] != 'ai_generated'
    assert result.metadata['decision_asset_used'] is False
    assert result.metadata['decision_asset_reject_reason'] == 'invalid_or_nonlocal_asset_path'
    assert fallback_used is True
    assert fallback_reason == 'official_asset_bridge_invalid'
    assert outcome == 'ai_hard_failure'
    assert ai_provider.calls == 0


def test_ai_still_allowed_when_cover_decision_use_ai_true(tmp_path: Path) -> None:
    generated_asset_path = tmp_path / 'generated' / 'ai.png'
    _write_test_png(generated_asset_path, color='#22aa55')

    ai_provider = _FakeProvider(
        ResolvedImage(
            image=Image.new('RGB', (1280, 720), '#22aa55'),
            metadata={
                'selected_source': 'ai',
                'provider_name': 'ai',
                'asset_path': str(generated_asset_path.resolve()),
            },
        )
    )
    resolver = YotoImageResolver(
        artwork_provider=ArtworkImageProvider(),
        ai_provider=ai_provider,
        placeholder_provider=_FakeProvider(
            ResolvedImage(
                image=Image.new('RGB', (1280, 720), '#111111'),
                metadata={'selected_source': 'placeholder', 'provider_name': 'placeholder'},
            )
        ),
        mode='ai_first',
    )

    result = resolver.resolve(
        _resolver_request(
            cover_decision={
                'use_ai': True,
                'image_source_type': 'ai_generated',
                'selected_asset': {
                    'source_type': 'ai_generated',
                    'path_or_url': 'ai://generated/strategy_core',
                },
            }
        )
    )

    final_source = infer_final_source(str(result.metadata.get('selected_source') or ''))
    fallback_used = infer_fallback_used(final_source)
    outcome = classify_outcome(
        final_source=final_source,
        ai_attempted=bool(result.metadata.get('ai_attempted', False)),
        ai_succeeded=bool(result.metadata.get('ai_succeeded', False)),
        fallback_used=fallback_used,
    )

    assert final_source == 'ai'
    assert result.metadata['actual_image_source_type'] == 'ai_generated'
    assert result.metadata['cover_decision_use_ai'] is True
    assert result.metadata['decision_asset_used'] is False
    assert result.metadata['decision_asset_reject_reason'] == 'decision_prefers_ai'
    assert result.metadata['decision_reason'] == 'ai_generated_missing_artwork'
    assert outcome == 'ai_runtime'
    assert ai_provider.calls == 1
