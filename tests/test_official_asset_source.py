from __future__ import annotations

import io
from pathlib import Path
import shutil

from PIL import Image

from infrastructure.render.cards.asset_sources.asset_cache import AssetCacheDownloadResult
from infrastructure.render.cards.asset_sources.official_asset_source import (
    DEFAULT_LOCAL_OFFICIAL_ASSET_MANIFEST_PATH,
    MAX_DOWNLOAD_CANDIDATES_PER_GAME,
    resolve_official_asset_candidates,
)
from tools.ai_card_smoke import DEFAULT_SMOKE_GAME, MINIMAL_SMOKE_GAMES


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new('RGBA', (1, 1), (255, 0, 0, 255)).save(buffer, format='PNG')
    return buffer.getvalue()


def _clear_test_cache(identifier: str) -> None:
    cache_dir = Path(__file__).resolve().parents[1] / 'output' / 'cards' / 'official_asset_cache' / 'steam' / identifier
    shutil.rmtree(cache_dir, ignore_errors=True)


def test_official_asset_source_steam_manifest_returns_cached_and_remote_candidates() -> None:
    game_input = dict(MINIMAL_SMOKE_GAMES[0])

    result = resolve_official_asset_candidates(
        game_title=game_input['title'],
        steam_app_id=game_input.get('steam_app_id'),
        store_id=game_input.get('store_id'),
        slug=game_input.get('slug'),
        source_hint=game_input.get('source_hint'),
        existing_metadata={
            'game_title': game_input['title'],
            'steam_app_id': game_input.get('steam_app_id'),
            'store_id': game_input.get('store_id'),
            'slug': game_input.get('slug'),
            'source_hint': game_input.get('source_hint'),
        },
        fallback_asset_candidates=game_input.get('asset_candidates'),
    )

    assert Path(DEFAULT_LOCAL_OFFICIAL_ASSET_MANIFEST_PATH).exists()
    assert result.asset_source_mode == 'steam_cdn_manifest'
    assert result.asset_ingestion_mode == 'mixed_local_remote'
    assert result.asset_source_errors == []
    assert result.manifest_entry_id == game_input['slug']
    assert result.used_fixture_fallback is False
    assert result.asset_candidates
    assert [item['priority'] for item in result.asset_candidates] == sorted(
        item['priority'] for item in result.asset_candidates
    )
    assert any(item['source_type'] == 'steam_library_capsule' for item in result.asset_candidates)
    assert any(item['source_type'] == 'steam_header_capsule' for item in result.asset_candidates)
    assert any(item['source_type'] == 'official_press_key_art' for item in result.asset_candidates)
    assert any(item['cache_status'] == 'cached' for item in result.asset_candidates)
    assert any(item['remote_url'] for item in result.asset_candidates)


def test_official_asset_source_keeps_local_manifest_bundle_compatibility() -> None:
    game_input = dict(MINIMAL_SMOKE_GAMES[4])

    result = resolve_official_asset_candidates(
        game_title=game_input['title'],
        store_id=game_input.get('store_id'),
        slug=game_input.get('slug'),
        source_hint=game_input.get('source_hint'),
        existing_metadata={
            'game_title': game_input['title'],
            'store_id': game_input.get('store_id'),
            'slug': game_input.get('slug'),
            'source_hint': game_input.get('source_hint'),
        },
        fallback_asset_candidates=game_input.get('asset_candidates'),
    )

    assert result.asset_source_mode == 'local_manifest'
    assert result.asset_source_errors == []
    assert result.used_fixture_fallback is False
    assert len(result.asset_candidates) == 4
    assert all(item['source_origin'] == 'local_manifest' for item in result.asset_candidates)


def test_official_asset_source_direct_epic_generation_uses_cache_contract() -> None:
    result = resolve_official_asset_candidates(
        game_title='Epic Showcase Demo',
        epic_slug='epic-showcase-demo',
        asset_urls={
            'epic_offer_image': 'https://cdn1.epicgames.com/epic-showcase-demo/offer-image.jpg',
        },
        existing_metadata={
            'game_title': 'Epic Showcase Demo',
            'epic_slug': 'epic-showcase-demo',
        },
    )

    assert result.asset_source_mode == 'epic_manifest'
    assert result.asset_ingestion_mode == 'remote_templates_only'
    assert result.asset_source_errors == []
    assert len(result.asset_candidates) == 2
    assert {item['source_type'] for item in result.asset_candidates} == {
        'epic_offer_image',
        'epic_library_landscape',
    }
    assert all(item['remote_url'] for item in result.asset_candidates)
    assert all(item['cache_status'] == 'not_requested' for item in result.asset_candidates)
    assert all(item['cache_path'] for item in result.asset_candidates)


def test_official_asset_source_keeps_fixture_fallback_for_unmapped_smoke_game() -> None:
    result = resolve_official_asset_candidates(
        game_title=DEFAULT_SMOKE_GAME['title'],
        store_id=DEFAULT_SMOKE_GAME.get('store_id'),
        slug=DEFAULT_SMOKE_GAME.get('slug'),
        source_hint=DEFAULT_SMOKE_GAME.get('source_hint'),
        existing_metadata={
            'game_title': DEFAULT_SMOKE_GAME['title'],
            'store_id': DEFAULT_SMOKE_GAME.get('store_id'),
            'slug': DEFAULT_SMOKE_GAME.get('slug'),
            'source_hint': DEFAULT_SMOKE_GAME.get('source_hint'),
        },
        fallback_asset_candidates=DEFAULT_SMOKE_GAME.get('asset_candidates'),
    )

    assert result.asset_source_mode == 'fixture_fallback'
    assert 'manifest_entry_not_found' in result.asset_source_errors
    assert result.used_fixture_fallback is True
    assert len(result.asset_candidates) == len(DEFAULT_SMOKE_GAME['asset_candidates'])
    assert all(item['source_origin'] == 'fixture_fallback' for item in result.asset_candidates)


def test_official_asset_source_downloads_only_top_remote_candidates(tmp_path: Path) -> None:
    _clear_test_cache('999991')
    png_bytes = _png_bytes()
    calls: list[tuple[str, str, int, int]] = []

    def fake_downloader(*, remote_url: str, cache_path: str, timeout_seconds: int, max_bytes: int) -> AssetCacheDownloadResult:
        calls.append((remote_url, cache_path, timeout_seconds, max_bytes))
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

    result = resolve_official_asset_candidates(
        game_title='Remote Download Success Demo',
        steam_app_id='999991',
        store_id='steam:remote_download_success_demo',
        slug='remote_download_success_demo',
        source_hint='steam',
        existing_metadata={
            'game_title': 'Remote Download Success Demo',
            'store_id': 'steam:remote_download_success_demo',
            'slug': 'remote_download_success_demo',
            'source_hint': 'steam',
            'steam_app_id': '999991',
            'genre': 'roguelike action',
            'tags': ['hero', 'combat'],
            'short_description': 'A remote-only smoke title with CDN-derived assets and no cached local files.',
            'offer_type': 'discount',
        },
        download_assets=True,
        asset_downloader=fake_downloader,
    )

    assert result.asset_source_mode == 'steam_cdn_manifest'
    assert result.asset_download_enabled is True
    assert result.asset_download_attempted is True
    assert result.asset_download_status == 'downloaded'
    assert result.asset_download_error is None
    assert 1 <= result.downloaded_asset_count <= MAX_DOWNLOAD_CANDIDATES_PER_GAME
    assert result.cached_asset_count == 0
    assert result.failed_asset_count == 0
    assert 1 <= len(calls) <= MAX_DOWNLOAD_CANDIDATES_PER_GAME
    assert all(item[2] == 10 for item in calls)
    assert all(item[3] == 8 * 1024 * 1024 for item in calls)
    downloaded_candidates = [item for item in result.asset_candidates if item['cache_status'] == 'downloaded']
    assert len(downloaded_candidates) == result.downloaded_asset_count
    assert all(item['path_or_url'] == item['cache_path'] for item in downloaded_candidates)


def test_official_asset_source_failed_download_preserves_local_cache_contract() -> None:
    _clear_test_cache('999992')
    def fake_downloader(*, remote_url: str, cache_path: str, timeout_seconds: int, max_bytes: int) -> AssetCacheDownloadResult:
        return AssetCacheDownloadResult(
            cache_path=cache_path,
            cache_status='failed',
            download_attempted=True,
            error='offline_guarded_failure',
        )

    result = resolve_official_asset_candidates(
        game_title='Remote Download Failure Demo',
        steam_app_id='999992',
        store_id='steam:remote_download_failure_demo',
        slug='remote_download_failure_demo',
        source_hint='steam',
        existing_metadata={
            'game_title': 'Remote Download Failure Demo',
            'store_id': 'steam:remote_download_failure_demo',
            'slug': 'remote_download_failure_demo',
            'source_hint': 'steam',
            'steam_app_id': '999992',
            'genre': 'roguelike action',
            'tags': ['hero', 'combat'],
            'short_description': 'A remote-only smoke title with CDN-derived assets and no cached local files.',
            'offer_type': 'discount',
        },
        download_assets=True,
        asset_downloader=fake_downloader,
    )

    assert result.asset_download_enabled is True
    assert result.asset_download_attempted is True
    assert result.asset_download_status == 'failed'
    assert result.asset_download_error is not None
    assert 1 <= result.failed_asset_count <= MAX_DOWNLOAD_CANDIDATES_PER_GAME
    assert any(error.startswith('asset_download_failed:') for error in result.asset_source_errors)
    failed_candidates = [item for item in result.asset_candidates if item['cache_status'] == 'failed']
    assert len(failed_candidates) == result.failed_asset_count
    assert all(item['path_or_url'] == item['cache_path'] for item in failed_candidates)
