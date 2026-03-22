from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from application.use_cases.dry_run_render import RenderResult
from application.use_cases.generate_video_manifests import GenerateVideoManifestsUseCase
from application.use_cases.publish_next import PublishNextUseCase
from domain.entities.offer import AssetBundle, OfferKind, OfferSource
from domain.entities.post_artifact import PostArtifact
from infrastructure.db.repositories import QueueRecord, Repositories
from infrastructure.video.manifest_writer import VideoManifestWriter

from .support import make_test_settings
from .test_caption_builder_arch import make_offer


class StaticRenderUseCase:
    def __init__(self, image_path: Path, idempotency_key: str = 'offer-video-key') -> None:
        self.image_path = image_path
        self.idempotency_key = idempotency_key

    async def execute(self, offer, decision_json):
        artifact = PostArtifact(
            offer_id=offer.offer_id,
            caption_html='<b>caption</b>',
            hashtags=['#steam'],
            template_id=str(decision_json.get('template_id') or 'steam_discount'),
            render_inputs={'offer': offer.to_snapshot(), 'decision': decision_json},
            assets_used=[str(self.image_path)],
            idempotency_key=self.idempotency_key,
            caption_hash='caption-hash',
            image_hash='image-hash',
            render_diagnostics={
                'renderer_selected': 'yoto_v4',
                'renderer_fallback_used': False,
                'hero_asset_used': 'https://example.com/header.png',
                'render_warnings': [],
            },
            decision_debug={'caption': {'voice_mode': 'indirect'}},
        )
        return RenderResult(artifact=artifact, image_path=self.image_path)


class RecordingPublisher:
    def __init__(self) -> None:
        self.calls = 0

    async def publish_photo(self, image_path: Path, caption_html: str):
        self.calls += 1
        return SimpleNamespace(message_id=4400 + self.calls)


def make_decision_json(
    lane: str = 'high_value_discount',
    *,
    score: float = 180.0,
    queue_bucket: str = 'planned',
    template_id: str = 'steam_discount',
    content_type: str | None = None,
) -> dict:
    payload = {
        'lane': lane,
        'template_id': template_id,
        'must_ship': False,
        'queue_bucket': queue_bucket,
        'decision_reasons': [lane],
        'quality_reasons': ['review_threshold'],
        'dedup_reason': 'new_offer',
        'score': score,
        'manual_force_override': False,
        'debug': {},
    }
    if content_type:
        payload['content_type'] = content_type
    return payload


def make_offer_artifact(offer, decision_json: dict, image_path: Path) -> PostArtifact:
    return PostArtifact(
        offer_id=offer.offer_id,
        caption_html='<b>caption</b>',
        hashtags=['#steam'],
        template_id=str(decision_json.get('template_id') or 'steam_discount'),
        render_inputs={'offer': offer.to_snapshot(), 'decision': decision_json},
        assets_used=[str(image_path)],
        idempotency_key='offer-manifest-key',
        caption_hash='caption-hash',
        image_hash='image-hash',
        render_diagnostics={
            'renderer_selected': 'yoto_v4',
            'renderer_fallback_used': False,
            'hero_asset_used': 'https://example.com/header.png',
            'render_warnings': [],
        },
        decision_debug={'caption': {'voice_mode': 'indirect'}},
    )


def make_roundup_record(now: datetime, image_path: Path) -> tuple[QueueRecord, PostArtifact]:
    item_one = make_offer()
    item_one.offer_id = 'steam:11'
    item_one.source_ref = '11'
    item_one.game_id = '11'
    item_one.franchise_key = 'item-one'
    item_one.title = 'Roundup Item One'

    item_two = make_offer()
    item_two.offer_id = 'steam:12'
    item_two.source_ref = '12'
    item_two.game_id = '12'
    item_two.franchise_key = 'item-two'
    item_two.title = 'Roundup Item Two'

    roundup_offer = make_offer()
    roundup_offer.offer_id = 'roundup:roundup_digest'
    roundup_offer.source = OfferSource.EVENT
    roundup_offer.source_ref = 'roundup_digest'
    roundup_offer.offer_kind = OfferKind.DISCOUNT
    roundup_offer.game_id = 'roundup:roundup_digest'
    roundup_offer.franchise_key = 'roundup-digest'
    roundup_offer.title = 'Roundup: Reserve Digest'
    roundup_offer.assets = AssetBundle(fallback=str(image_path))

    decision_json = {
        'lane': 'roundup_digest',
        'template_id': 'roundup_digest',
        'must_ship': False,
        'queue_bucket': 'reserve',
        'decision_reasons': ['roundup_digest'],
        'quality_reasons': ['roundup_artifact_ready'],
        'dedup_reason': 'roundup_snapshot',
        'score': 220.0,
        'manual_force_override': False,
        'content_type': 'roundup',
        'roundup_id': 'roundup_digest',
        'roundup_run_key': '20260314T120000Z',
        'roundup_intro': 'Йото витягнув ще кілька сильних пропозицій.',
        'roundup_closing_cta': 'Переглянь добірку, поки ці пропозиції ще активні.',
        'roundup_caption_html': '<b>Roundup: Reserve Digest</b>\nRoundup caption',
        'roundup_card_asset_path': str(image_path),
        'roundup_item_offer_ids': [item_one.offer_id, item_two.offer_id],
        'roundup_item_offers': [item_one.to_snapshot(), item_two.to_snapshot()],
        'debug': {},
    }
    artifact = PostArtifact(
        offer_id=roundup_offer.offer_id,
        caption_html=decision_json['roundup_caption_html'],
        hashtags=[],
        template_id='roundup_digest',
        render_inputs={'offer': roundup_offer.to_snapshot(), 'decision': decision_json},
        assets_used=[str(image_path)],
        idempotency_key='roundup:roundup_digest:20260314T120000Z',
        caption_hash='roundup-caption-hash',
        image_hash='roundup-image-hash',
        render_diagnostics={
            'renderer_selected': 'yoto_v4',
            'renderer_fallback_used': False,
            'selected_asset_path': str(image_path),
            'lead_artwork_selected_offer_id': item_one.offer_id,
            'render_warnings': [],
        },
    )
    return (
        QueueRecord(
            row_id=1,
            bucket='reserve',
            lane='roundup_digest',
            score=220.0,
            offer=roundup_offer,
            decision_json=decision_json,
            created_at=now,
        ),
        artifact,
    )


def test_generate_video_manifests_emit_offer_post_persists_v2_payload(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path)
    repo = Repositories(settings.db_path)
    repo.initialize()
    writer = VideoManifestWriter(settings.video_manifest_output_dir)
    use_case = GenerateVideoManifestsUseCase(repo, writer)
    now = datetime(2026, 3, 14, 12, 0)
    image_path = tmp_path / 'offer-card.png'
    image_path.write_bytes(b'card')

    offer = make_offer()
    decision_json = make_decision_json()
    repo.replace_queue('planned', [(180.0, offer, decision_json)])
    record = repo.list_queue('planned')[0]
    artifact = make_offer_artifact(offer, decision_json, image_path)

    manifest = use_case.emit_offer_post(now, record, artifact, image_path)

    assert manifest is not None
    assert manifest.json_path is not None and manifest.json_path.exists()
    payload = json.loads(manifest.json_path.read_text(encoding='utf-8'))
    assert payload['manifest_version'] == 2
    assert payload['content_type'] == 'discount'
    assert payload['caption_html'] == '<b>caption</b>'
    assert payload['asset_refs']['card_image'] == str(image_path)
    assert payload['render_diagnostics']['renderer_selected'] == 'yoto_v4'
    assert payload['caption_debug']['voice_mode'] == 'indirect'
    assert payload['context']['content_type'] == 'discount'
    assert payload['voice_facts']['discount_percent'] == offer.discount_percent
    assert payload['voice_facts']['free_access_type'] is None
    with repo.connect() as connection:
        row = connection.execute('SELECT payload_json FROM video_manifests').fetchone()
    assert row is not None


def test_generate_video_manifests_event_manifest_backfills_card_image_from_artifact(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path)
    repo = Repositories(settings.db_path)
    repo.initialize()
    writer = VideoManifestWriter(settings.video_manifest_output_dir)
    use_case = GenerateVideoManifestsUseCase(repo, writer)
    now = datetime(2026, 3, 14, 12, 2)
    image_path = tmp_path / 'event-card.png'
    image_path.write_bytes(b'card')

    offer = make_offer()
    offer.offer_id = 'event:festival:10'
    offer.source = OfferSource.EVENT
    offer.source_ref = 'festival:10'
    offer.offer_kind = OfferKind.FESTIVAL
    offer.game_id = 'festival:10'
    offer.franchise_key = 'steam-tower-defense-fest'
    offer.title = 'Steam Tower Defense Fest'
    offer.assets = AssetBundle(
        hero='https://cdn.example.com/event-hero-small.png',
        screenshot='https://cdn.example.com/event-screenshot-small.png',
        fallback='https://cdn.example.com/event-fallback-small.png',
    )
    offer.price_before_minor = None
    offer.price_after_minor = None
    offer.discount_percent = 0
    decision_json = make_decision_json(lane='event_festival', template_id='festival_event', content_type='event')
    repo.replace_queue('planned', [(180.0, offer, decision_json)])
    record = repo.list_queue('planned')[0]
    artifact = PostArtifact(
        offer_id=offer.offer_id,
        caption_html='<b>festival</b>',
        hashtags=['#festival'],
        template_id='festival_event',
        render_inputs={'offer': offer.to_snapshot(), 'decision': decision_json},
        assets_used=['https://cdn.example.com/event-hero-small.png', str(image_path)],
        idempotency_key='event-manifest-key',
        caption_hash='caption-hash',
        image_hash='image-hash',
        render_diagnostics={
            'renderer_selected': 'yoto_v4',
            'renderer_fallback_used': False,
            'hero_asset_used': 'https://cdn.example.com/event-hero-small.png',
            'render_warnings': [],
        },
        decision_debug={'caption': {'voice_mode': 'indirect'}},
    )

    manifest = use_case.emit_offer_post(now, record, artifact, image_path=None)

    assert manifest is not None
    assert manifest.json_path is not None and manifest.json_path.exists()
    payload = json.loads(manifest.json_path.read_text(encoding='utf-8'))
    assert payload['content_type'] == 'event'
    assert payload['asset_refs']['card_image'] == str(image_path)
    assert payload['asset_refs']['game_image'] == 'https://cdn.example.com/event-hero-small.png'
    assert payload['asset_refs']['background'] == 'https://cdn.example.com/event-screenshot-small.png'
    assert payload['source_artifact']['image_path'] == str(image_path)
    assert payload['context']['content_type'] == 'event'
    assert payload['voice_facts']['title'] == 'Steam Tower Defense Fest'


def test_generate_video_manifests_emit_roundup_post_persists_v2_payload(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path)
    repo = Repositories(settings.db_path)
    repo.initialize()
    writer = VideoManifestWriter(settings.video_manifest_output_dir)
    use_case = GenerateVideoManifestsUseCase(repo, writer)
    now = datetime(2026, 3, 14, 12, 5)
    image_path = tmp_path / 'roundup-card.png'
    image_path.write_bytes(b'roundup-card')

    record, artifact = make_roundup_record(now, image_path)

    manifest = use_case.emit_roundup_post(now, record, artifact, image_path)

    assert manifest is not None
    assert manifest.json_path is not None and manifest.json_path.exists()
    payload = json.loads(manifest.json_path.read_text(encoding='utf-8'))
    assert payload['manifest_version'] == 2
    assert payload['content_type'] == 'roundup'
    assert payload['context']['roundup_id'] == 'roundup_digest'
    assert payload['asset_refs']['card_image'] == str(image_path)
    assert payload['asset_refs']['game_image'] == str(image_path)
    assert len(payload['roundup_items']) == 2
    assert payload['render_diagnostics']['lead_artwork_selected_offer_id'] == 'steam:11'
    assert payload['context']['content_type'] == 'roundup'
    assert payload['voice_facts']['item_count'] == 2


def test_publish_next_emits_offer_video_manifest_after_successful_publish(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path, dry_run=False)
    repo = Repositories(settings.db_path)
    repo.initialize()
    now = datetime(2026, 3, 14, 12, 10)
    image_path = tmp_path / 'published-card.png'
    image_path.write_bytes(b'card')

    offer = make_offer()
    repo.replace_queue('planned', [(200.0, offer, make_decision_json())])
    emitter = GenerateVideoManifestsUseCase(repo, VideoManifestWriter(settings.video_manifest_output_dir))
    use_case = PublishNextUseCase(
        settings,
        repo,
        StaticRenderUseCase(image_path),
        RecordingPublisher(),
        video_manifests=emitter,
    )

    result = asyncio.run(use_case.execute(now, now))

    assert result is not None
    assert result.reason == 'published'
    manifest_files = list(settings.video_manifest_output_dir.glob('*_video_manifest_*.json'))
    assert len(manifest_files) == 1
    payload = json.loads(manifest_files[0].read_text(encoding='utf-8'))
    assert payload['manifest_version'] == 2
    assert payload['context']['published'] is True
    assert payload['source_artifact']['image_path'] == str(image_path)


def test_publish_next_does_not_emit_video_manifest_on_dry_run(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path, dry_run=True)
    repo = Repositories(settings.db_path)
    repo.initialize()
    now = datetime(2026, 3, 14, 12, 15)
    image_path = tmp_path / 'dry-run-card.png'
    image_path.write_bytes(b'card')

    offer = make_offer()
    repo.replace_queue('planned', [(200.0, offer, make_decision_json())])
    emitter = GenerateVideoManifestsUseCase(repo, VideoManifestWriter(settings.video_manifest_output_dir))
    use_case = PublishNextUseCase(
        settings,
        repo,
        StaticRenderUseCase(image_path, idempotency_key='dry-run-key'),
        RecordingPublisher(),
        video_manifests=emitter,
    )

    result = asyncio.run(use_case.execute(now, now))

    assert result is not None
    assert result.reason == 'dry_run'
    assert list(settings.video_manifest_output_dir.glob('*_video_manifest_*.json')) == []
    with repo.connect() as connection:
        count = connection.execute('SELECT COUNT(*) AS count FROM video_manifests').fetchone()['count']
    assert int(count) == 0




