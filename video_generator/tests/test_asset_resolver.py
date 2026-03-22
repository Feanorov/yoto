from datetime import datetime
from pathlib import Path

from PIL import Image

from video_generator.domain.entities import VideoManifest
from video_generator.infrastructure.asset_resolver import AssetResolver
from video_generator.infrastructure.structured_logger import StructuredLogger


def make_manifest(tmp_path: Path, *, game_image: Path, background: Path, card_image: Path) -> VideoManifest:
    manifest_path = tmp_path / 'event_manifest.json'
    manifest_path.write_text('{}', encoding='utf-8')
    return VideoManifest(
        manifest_version=2,
        run_key='20260314T120000Z',
        created_at=datetime(2026, 3, 14, 12, 0, 0),
        offer_id='event:test',
        short_title='Steam Event',
        hook_line='????? ??? ??????.',
        summary_line='????????? ??????? ???????? ??????????.',
        urgency_line='??? ?????????? ?????.',
        asset_refs={
            'game_image': str(game_image),
            'background': str(background),
            'card_image': str(card_image),
        },
        template_hint='event-countdown',
        context={
            'lane': 'event_festival',
            'offer_kind': 'event',
            'store': 'Steam',
        },
        source_path=manifest_path,
        manifest_hash='event-hash',
    )


def test_event_assets_retry_with_card_image_before_placeholder(tmp_path: Path) -> None:
    small = tmp_path / 'small.png'
    card = tmp_path / 'card.png'
    Image.new('RGB', (184, 69), (120, 60, 40)).save(small)
    Image.new('RGB', (900, 1200), (40, 90, 140)).save(card)

    manifest = make_manifest(tmp_path, game_image=small, background=small, card_image=card)
    resolver = AssetResolver(assets_dir=tmp_path / 'assets', logger=StructuredLogger('asset_resolver_test'))

    resolved = resolver.resolve(manifest)

    assert resolved.game_image.path == card
    assert resolved.background.path == card
    assert resolved.game_image.used_fallback is False
    assert resolved.background.used_fallback is False
    assert resolved.warnings == ('missing badge',)
