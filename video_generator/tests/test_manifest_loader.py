from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image

from video_generator.infrastructure.asset_resolver import AssetResolver
from video_generator.infrastructure.manifest_loader import ManifestLoader


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        return


@contextmanager
def serve_directory(directory: Path):
    handler = partial(QuietHandler, directory=str(directory))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f'http://{host}:{port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def write_manifest(tmp_path: Path, *, asset_refs, context: dict | None = None) -> Path:
    manifest_path = tmp_path / '20260310T120000Z_video_manifest_offer.json'
    manifest_path.write_text(
        json.dumps(
            {
                'short_title': 'Short title',
                'hook_line': 'Hook line',
                'summary_line': 'Summary line',
                'urgency_line': 'Urgency line',
                'asset_refs': asset_refs,
                'context': context or {'store': 'Steam', 'offer_kind': 'discount'},
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )
    return manifest_path


def test_manifest_loader_accepts_current_list_style_asset_refs(tmp_path: Path) -> None:
    manifest_path = write_manifest(
        tmp_path,
        asset_refs=[
            'https://cdn.example.com/game_header.jpg',
            'https://cdn.example.com/library_capsule.jpg',
            'https://cdn.example.com/ss_12345.jpg',
        ],
    )

    manifest = ManifestLoader().load(manifest_path)

    assert manifest.manifest_version == 1
    assert manifest.run_key == '20260310T120000Z'
    assert manifest.asset_refs == {
        'game_image': 'https://cdn.example.com/game_header.jpg',
        'background': 'https://cdn.example.com/ss_12345.jpg',
    }


def test_manifest_loader_accepts_smoke_manifest_dict_payload() -> None:
    manifest_path = Path(__file__).resolve().parents[1] / 'smoke_test' / 'manifests' / '20260311T003000Z_video_manifest_smoke_test.json'

    manifest = ManifestLoader().load(manifest_path)

    assert manifest.template_hint == 'deadline-push'
    assert manifest.asset_refs['game_image'].endswith('game.png')
    assert manifest.asset_refs['background'].endswith('background.png')
    assert manifest.context['store'] == 'Steam'


def test_asset_resolver_downloads_steam_remote_assets(tmp_path: Path) -> None:
    remote_dir = tmp_path / 'remote-steam'
    remote_dir.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', (460, 215), (120, 80, 90)).save(remote_dir / 'steam_header.jpg')
    Image.new('RGB', (1280, 720), (30, 40, 60)).save(remote_dir / 'steam_ss.jpg')

    with serve_directory(remote_dir) as base_url:
        manifest_path = write_manifest(
            tmp_path,
            asset_refs={
                'game_image': f'{base_url}/steam_header.jpg',
                'background': f'{base_url}/steam_ss.jpg',
            },
            context={'store': 'Steam', 'offer_kind': 'discount'},
        )
        manifest = ManifestLoader().load(manifest_path)
        resolver = AssetResolver(assets_dir=tmp_path / 'assets')
        assets = resolver.resolve(manifest)

    assert assets.game_image.used_fallback is False
    assert assets.background.used_fallback is False
    assert assets.game_image.path.exists()
    assert assets.background.path.exists()
    assert assets.game_image.path != resolver.fallback_game_image
    assert assets.background.path != resolver.default_background
    assert all(not warning.startswith('game_image:') for warning in assets.warnings)
    assert all(not warning.startswith('background:') for warning in assets.warnings)


def test_asset_resolver_downloads_epic_remote_assets(tmp_path: Path) -> None:
    remote_dir = tmp_path / 'remote-epic'
    remote_dir.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', (640, 360), (80, 110, 150)).save(remote_dir / 'epic_cover.png')
    Image.new('RGB', (1600, 900), (20, 30, 40)).save(remote_dir / 'epic_background.png')

    with serve_directory(remote_dir) as base_url:
        manifest_path = write_manifest(
            tmp_path,
            asset_refs={
                'game_image': f'{base_url}/epic_cover.png',
                'background': f'{base_url}/epic_background.png',
            },
            context={'store': 'Epic Games Store', 'offer_kind': 'freebie'},
        )
        manifest = ManifestLoader().load(manifest_path)
        resolver = AssetResolver(assets_dir=tmp_path / 'assets')
        assets = resolver.resolve(manifest)

    assert assets.game_image.used_fallback is False
    assert assets.background.used_fallback is False
    assert assets.game_image.path.exists()
    assert assets.background.path.exists()
    assert assets.game_image.path != resolver.fallback_game_image
    assert assets.background.path != resolver.default_background
    assert all(not warning.startswith('game_image:') for warning in assets.warnings)
    assert all(not warning.startswith('background:') for warning in assets.warnings)


def test_asset_resolver_falls_back_safely_for_partial_missing_assets(tmp_path: Path) -> None:
    manifest_path = write_manifest(
        tmp_path,
        asset_refs={'game_image': 'missing.png'},
        context={'store': 'Steam', 'offer_kind': 'discount'},
    )

    manifest = ManifestLoader().load(manifest_path)
    assets = AssetResolver(assets_dir=tmp_path / 'assets').resolve(manifest)

    assert assets.game_image.used_fallback is True
    assert assets.background.used_fallback is True
    assert assets.store_badge is None
    assert 'game_image:file_missing' in assets.warnings
    assert 'background:file_missing' in assets.warnings
