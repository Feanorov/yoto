from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta
import json
from pathlib import Path
from types import SimpleNamespace

from application.use_cases.dry_run_render import RenderResult
from application.use_cases.generate_video_manifests import GenerateVideoManifestsUseCase
from application.use_cases.publish_next import PublishNextUseCase
from dealbot.settings import AppSettings
from domain.entities.analytics_artifact import AnalyticsArtifact
from domain.entities.offer import OfferKind, OfferSource
from domain.entities.post_artifact import PostArtifact
from infrastructure.db.repositories import Repositories
from infrastructure.video.manifest_writer import VideoManifestWriter

from .support import make_test_settings
from .test_caption_builder_arch import make_offer


class ExplodingRenderUseCase:
    async def execute(self, offer, decision_json):
        raise AssertionError('roundup publish should bypass dry-run rendering')


class StaticRenderUseCase:
    def __init__(self, image_path: Path, idempotency_key: str = 'normal-key') -> None:
        self.image_path = image_path
        self.idempotency_key = idempotency_key

    async def execute(self, offer, decision_json):
        artifact = PostArtifact(
            offer_id=offer.offer_id,
            caption_html='<b>caption</b>',
            hashtags=['#steam'],
            template_id='steam_discount',
            render_inputs={'offer': offer.to_snapshot(), 'decision': decision_json},
            assets_used=[],
            idempotency_key=self.idempotency_key,
            caption_hash='caption-hash',
            image_hash='image-hash',
            render_diagnostics={
                'renderer_selected': 'yoto_v4',
                'renderer_fallback_used': False,
                'hero_fallback_used': False,
                'used_placeholder_artwork': False,
                'render_warnings': [],
            },
        )
        return RenderResult(artifact=artifact, image_path=self.image_path)


class RecordingPublisher:
    def __init__(self) -> None:
        self.calls = 0
        self.images: list[Path] = []
        self.captions: list[str] = []

    async def publish_photo(self, image_path: Path, caption_html: str):
        self.calls += 1
        self.images.append(image_path)
        self.captions.append(caption_html)
        return SimpleNamespace(message_id=3000 + self.calls)


def make_settings(tmp_path: Path, *, dry_run: bool = False) -> AppSettings:
    base = make_test_settings(tmp_path, dry_run=dry_run)
    return replace(
        base,
        card_output_dir=tmp_path / 'output' / 'cards',
        analytics_output_dir=tmp_path / 'output' / 'analytics',
    )


def make_decision_json(
    lane: str,
    *,
    score: float,
    queue_bucket: str = 'planned',
    template_id: str = 'steam_discount',
    content_type: str | None = None,
) -> dict:
    decision = {
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
        decision['content_type'] = content_type
    return decision


def make_offer_variant(
    offer_id: str,
    title: str,
    *,
    offer_kind: OfferKind = OfferKind.DISCOUNT,
    source: OfferSource | None = None,
):
    offer = make_offer()
    source_ref = offer_id.split(':', 1)[-1]
    offer.offer_id = offer_id
    offer.source_ref = source_ref
    offer.game_id = source_ref
    offer.franchise_key = title.lower().replace(' ', '-')
    offer.title = title
    offer.offer_kind = offer_kind
    offer.store_url = f'https://store.steampowered.com/app/{source_ref}'
    if source is not None:
        offer.source = source
    elif offer_kind == OfferKind.FREEBIE:
        offer.source = OfferSource.EPIC
    elif offer_kind in {OfferKind.EVENT, OfferKind.FESTIVAL}:
        offer.source = OfferSource.EVENT

    if offer_kind == OfferKind.FREEBIE:
        offer.price_before_minor = 69900
        offer.price_after_minor = 0
        offer.discount_percent = 100
        offer.store_url = f'https://store.epicgames.com/uk/p/{source_ref}'
    return offer


def seed_published_outbox(repo: Repositories, offer, decision_json: dict, published_at: datetime, *, idempotency_key: str | None = None) -> None:
    payload = {
        'schema_version': 1,
        'offer_id': offer.offer_id,
        'artifact': {
            'offer_id': offer.offer_id,
            'caption_html': '<b>seed</b>',
            'hashtags': [],
            'template_id': decision_json.get('template_id'),
            'render_inputs': {'offer': offer.to_snapshot(), 'decision': decision_json},
            'assets_used': [],
            'idempotency_key': idempotency_key or f'seed-{offer.offer_id}-{published_at.timestamp()}',
            'caption_hash': f'caption-{offer.offer_id}',
            'image_hash': f'image-{offer.offer_id}',
            'render_diagnostics': {},
            'decision_debug': {},
            'telegram_message_id': None,
        },
        'offer': offer.to_snapshot(),
        'decision': decision_json,
    }
    now = published_at.isoformat()
    with repo.connect() as connection:
        connection.execute(
            """
            INSERT INTO publish_outbox(
                idempotency_key, caption_hash, image_hash, image_path, telegram_message_id, published_at,
                payload_json, status, attempt_count, last_error, next_attempt_at, claimed_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload['artifact']['idempotency_key'],
                payload['artifact']['caption_hash'],
                payload['artifact']['image_hash'],
                None,
                2000,
                now,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                'published',
                1,
                None,
                None,
                None,
                now,
                now,
            ),
        )


def queue_window_key(records) -> str:
    return min(record.created_at for record in records).replace(microsecond=0).isoformat()


def seed_roundup_snapshot(
    repo: Repositories,
    settings: AppSettings,
    *,
    run_key: str,
    created_at: datetime,
    queue_snapshot_at: str,
    roundup_id: str,
    title: str,
    item_records,
    extra_items: list[dict] | None = None,
    omit_context: bool = False,
    context_override: dict | None = None,
    card_render_diagnostics: dict | None = None,
) -> Path:
    analytics_dir = settings.analytics_output_dir
    cards_dir = settings.card_output_dir
    analytics_dir.mkdir(parents=True, exist_ok=True)
    cards_dir.mkdir(parents=True, exist_ok=True)
    card_path = cards_dir / f'{roundup_id}.png'
    card_path.write_bytes(b'roundup-card')
    items = [
        {
            'offer_id': record.offer.offer_id,
            'title': record.offer.title,
            'store_url': record.offer.store_url,
            'store': record.offer.source.value,
            'source': record.offer.source.value,
            'lane': record.decision_json['lane'],
            'score': float(record.decision_json.get('score') or record.score or 0.0),
            'discount_percent': record.offer.discount_percent,
            'review_score': record.offer.review_score,
            'is_freebie': record.offer.is_freebie,
            'price_after_minor': record.offer.price_after_minor,
            'price_line': 'Live reserve item',
            'callout': 'Reserve roundup item',
            'summary_line': record.offer.title,
            'reason_tags': list(record.decision_json.get('decision_reasons') or []),
        }
        for record in item_records
    ]
    if extra_items:
        items.extend(extra_items)
    context = context_override
    if context is None and not omit_context:
        context = {
            'source': 'current_queue',
            'queue_snapshot_at': queue_snapshot_at,
        }
    payload = {
        'roundup_version': 1,
        'run_key': run_key,
        'created_at': created_at.isoformat(),
        'roundup_count': 1,
        'roundups': [
            {
                'roundup_id': roundup_id,
                'title': title,
                'intro': 'Roundup intro',
                'group_type': 'mixed',
                'theme_label': 'Digest',
                'item_count': len(items),
                'items': items,
                'telegram_draft': {
                    'title': title,
                    'intro': 'Roundup intro',
                    'item_lines': [],
                    'closing_cta': 'CTA',
                    'caption_html': f'<b>{title}</b>\\nRoundup caption',
                },
                'card_asset_path': str(card_path),
                'card_render_diagnostics': dict(card_render_diagnostics or {}),
            }
        ],
    }
    if context is not None:
        payload['context'] = context
    json_path = analytics_dir / f'{run_key}_roundup_snapshot_roundups.json'
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    repo.save_analytics_artifact(
        AnalyticsArtifact(
            artifact_type='roundup_snapshot',
            subject_id='roundups',
            run_key=run_key,
            created_at=created_at,
            payload_json=payload,
            json_path=json_path,
            csv_path=analytics_dir / f'{run_key}_roundup_snapshot_roundups.csv',
        )
    )
    return card_path


def test_publish_next_publishes_roundup_virtual_candidate_and_bypasses_render(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, dry_run=False)
    repo = Repositories(settings.db_path)
    repo.initialize()
    now = datetime(2026, 3, 13, 12, 0)

    planned = make_offer_variant('steam:201', 'Planned Discount')
    reserve_one = make_offer_variant('steam:301', 'Reserve One')
    reserve_two = make_offer_variant('steam:302', 'Reserve Two')
    reserve_three = make_offer_variant('steam:303', 'Reserve Three')
    repo.replace_queue('planned', [(250.0, planned, make_decision_json('high_value_discount', score=250.0))])
    repo.replace_queue(
        'reserve',
        [
            (220.0, reserve_one, make_decision_json('high_value_discount', score=220.0, queue_bucket='reserve')),
            (218.0, reserve_two, make_decision_json('high_value_discount', score=218.0, queue_bucket='reserve')),
            (216.0, reserve_three, make_decision_json('high_value_discount', score=216.0, queue_bucket='reserve')),
        ],
    )
    reserve_records = repo.list_queue('reserve')
    for offset in range(5):
        seed_published_outbox(
            repo,
            make_offer_variant(f'steam:recent{offset}', f'Recent Discount {offset}'),
            make_decision_json('high_value_discount', score=120.0 - offset),
            now - timedelta(minutes=offset + 1),
        )

    card_path = seed_roundup_snapshot(
        repo,
        settings,
        run_key='20260313T120000Z',
        created_at=now - timedelta(minutes=1),
        queue_snapshot_at=queue_window_key(reserve_records),
        roundup_id='roundup_live_digest',
        title='Roundup: Reserve Digest',
        item_records=reserve_records,
    )

    publisher = RecordingPublisher()
    video_manifests = GenerateVideoManifestsUseCase(repo, VideoManifestWriter(settings.video_manifest_output_dir))
    use_case = PublishNextUseCase(settings, repo, ExplodingRenderUseCase(), publisher, video_manifests=video_manifests)
    result = asyncio.run(use_case.execute(now, now))

    assert result is not None
    assert result.offer_id == 'roundup:roundup_live_digest'
    assert result.lane == 'roundup_digest'
    assert result.reason == 'published'
    assert publisher.calls == 1
    assert publisher.images == [card_path]
    assert publisher.captions == ['<b>Roundup: Reserve Digest</b>\\nRoundup caption']
    assert repo.list_queue('reserve') == []
    outbox = repo.get_outbox_record('roundup:roundup_live_digest:20260313T120000Z')
    assert outbox is not None
    assert outbox.status == 'published'
    assert outbox.payload_json['decision']['content_type'] == 'roundup'
    assert outbox.payload_json['decision']['roundup_id'] == 'roundup_live_digest'
    assert repo.list_recent_published_stream(limit=1)[0]['content_type'] == 'roundup'
    assert repo.get_game_history(reserve_one.game_id) is not None
    assert repo.get_game_history(reserve_two.game_id) is not None
    assert repo.get_game_history(reserve_three.game_id) is not None
    assert result.analytics['render']['image_path'] == str(card_path)
    roundup_injection = result.analytics['selection']['roundup_injection']
    assert roundup_injection['status'] == 'candidate_ready'
    assert roundup_injection['reason'] == 'candidate_ready'
    assert roundup_injection['lookup_mode'] == 'strict'
    assert roundup_injection['roundup_id'] == 'roundup_live_digest'
    assert result.analytics['render']['render_diagnostics']['template_id'] == 'roundup_digest'
    assert result.analytics['render']['render_diagnostics']['renderer_selected'] == 'yoto_v4'
    manifest_files = list(settings.video_manifest_output_dir.glob('*_video_manifest_*.json'))
    assert len(manifest_files) == 1
    manifest_payload = json.loads(manifest_files[0].read_text(encoding='utf-8'))
    assert manifest_payload['manifest_version'] == 2
    assert manifest_payload['content_type'] == 'roundup'
    assert manifest_payload['context']['roundup_id'] == 'roundup_live_digest'


def test_publish_next_roundup_diagnostics_reports_snapshot_not_found_reason(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, dry_run=True)
    repo = Repositories(settings.db_path)
    repo.initialize()
    now = datetime(2026, 3, 13, 12, 0)
    image_path = tmp_path / 'normal-card.png'
    image_path.write_bytes(b'card')

    planned = make_offer_variant('steam:390', 'Planned Discount')
    reserve_one = make_offer_variant('steam:391', 'Reserve One')
    reserve_two = make_offer_variant('steam:392', 'Reserve Two')
    repo.replace_queue('planned', [(180.0, planned, make_decision_json('high_value_discount', score=180.0))])
    repo.replace_queue(
        'reserve',
        [
            (160.0, reserve_one, make_decision_json('high_value_discount', score=160.0, queue_bucket='reserve')),
            (159.0, reserve_two, make_decision_json('high_value_discount', score=159.0, queue_bucket='reserve')),
        ],
    )

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    result = asyncio.run(use_case.execute(now, now))

    assert result is not None
    assert result.offer_id == 'steam:390'
    roundup_injection = result.analytics['selection']['roundup_injection']
    assert roundup_injection['status'] == 'rejected'
    assert roundup_injection['reason'] == 'snapshot_not_found'
    assert roundup_injection['lookup_mode'] == 'strict'


def test_publish_next_roundup_fallback_accepts_latest_canonical_snapshot_with_missing_context(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, dry_run=True)
    repo = Repositories(settings.db_path)
    repo.initialize()
    now = datetime(2026, 3, 13, 12, 0)

    planned = make_offer_variant('steam:393', 'Planned Discount')
    reserve_one = make_offer_variant('steam:394', 'Reserve One')
    reserve_two = make_offer_variant('steam:395', 'Reserve Two')
    reserve_three = make_offer_variant('steam:396', 'Reserve Three')
    repo.replace_queue('planned', [(340.0, planned, make_decision_json('high_value_discount', score=340.0))])
    repo.replace_queue(
        'reserve',
        [
            (171.0, reserve_one, make_decision_json('high_value_discount', score=171.0, queue_bucket='reserve')),
            (170.0, reserve_two, make_decision_json('high_value_discount', score=170.0, queue_bucket='reserve')),
            (169.0, reserve_three, make_decision_json('high_value_discount', score=169.0, queue_bucket='reserve')),
        ],
    )
    reserve_records = repo.list_queue('reserve')
    for offset in range(5):
        lane = 'final_push' if offset % 2 == 0 else 'game_of_the_day'
        seed_published_outbox(
            repo,
            make_offer_variant(f'steam:fallback{offset}', f'Recent Discount {offset}'),
            make_decision_json(lane, score=120.0 - offset),
            now - timedelta(minutes=offset + 1),
        )

    seed_roundup_snapshot(
        repo,
        settings,
        run_key='20260313T120100Z',
        created_at=now - timedelta(minutes=1),
        queue_snapshot_at=queue_window_key(reserve_records),
        roundup_id='roundup_missing_context',
        title='Roundup: Missing Context',
        item_records=reserve_records,
        omit_context=True,
    )

    use_case = PublishNextUseCase(settings, repo, ExplodingRenderUseCase(), RecordingPublisher())
    result = asyncio.run(use_case.execute(now, now))

    assert result is not None
    assert result.offer_id == 'roundup:roundup_missing_context'
    roundup_injection = result.analytics['selection']['roundup_injection']
    assert roundup_injection['status'] == 'candidate_ready'
    assert roundup_injection['reason'] == 'candidate_ready'
    assert roundup_injection['lookup_mode'] == 'fallback'
    assert roundup_injection['strict_rejection_reason'] == 'snapshot_context_missing_source'


def test_publish_next_skips_roundup_when_recent_roundup_exists(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, dry_run=True)
    repo = Repositories(settings.db_path)
    repo.initialize()
    now = datetime(2026, 3, 13, 12, 0)
    image_path = tmp_path / 'normal-card.png'
    image_path.write_bytes(b'card')

    planned = make_offer_variant('steam:401', 'Planned Discount')
    reserve_one = make_offer_variant('steam:402', 'Reserve One')
    reserve_two = make_offer_variant('steam:403', 'Reserve Two')
    reserve_three = make_offer_variant('steam:404', 'Reserve Three')
    repo.replace_queue('planned', [(180.0, planned, make_decision_json('high_value_discount', score=180.0))])
    repo.replace_queue(
        'reserve',
        [
            (160.0, reserve_one, make_decision_json('high_value_discount', score=160.0, queue_bucket='reserve')),
            (159.0, reserve_two, make_decision_json('high_value_discount', score=159.0, queue_bucket='reserve')),
            (158.0, reserve_three, make_decision_json('high_value_discount', score=158.0, queue_bucket='reserve')),
        ],
    )
    reserve_records = repo.list_queue('reserve')
    roundup_offer = make_offer_variant('roundup:history', 'Recent Roundup')
    seed_published_outbox(
        repo,
        roundup_offer,
        make_decision_json('roundup_digest', score=200.0, queue_bucket='reserve', template_id='roundup_digest', content_type='roundup'),
        now - timedelta(minutes=1),
        idempotency_key='roundup:history:20260313T110000Z',
    )
    seed_roundup_snapshot(
        repo,
        settings,
        run_key='20260313T120500Z',
        created_at=now - timedelta(minutes=1),
        queue_snapshot_at=queue_window_key(reserve_records),
        roundup_id='roundup_should_skip',
        title='Roundup: Should Skip',
        item_records=reserve_records,
    )

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    result = asyncio.run(use_case.execute(now, now))

    assert result is not None
    assert result.offer_id == 'steam:401'
    assert result.lane == 'high_value_discount'
    assert result.reason == 'dry_run'
    roundup_injection = result.analytics['selection']['roundup_injection']
    assert roundup_injection['status'] == 'rejected'
    assert roundup_injection['reason'] == 'recent_roundup_spacing_blocked'


def test_publish_next_skips_roundup_when_roundup_item_already_published(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, dry_run=True)
    repo = Repositories(settings.db_path)
    repo.initialize()
    now = datetime(2026, 3, 13, 12, 0)
    image_path = tmp_path / 'normal-card.png'
    image_path.write_bytes(b'card')

    planned = make_offer_variant('steam:501', 'Planned Discount')
    reserve_one = make_offer_variant('steam:502', 'Reserve One')
    reserve_two = make_offer_variant('steam:503', 'Reserve Two')
    reserve_three = make_offer_variant('steam:504', 'Reserve Three')
    repo.replace_queue('planned', [(190.0, planned, make_decision_json('high_value_discount', score=190.0))])
    repo.replace_queue(
        'reserve',
        [
            (170.0, reserve_one, make_decision_json('high_value_discount', score=170.0, queue_bucket='reserve')),
            (169.0, reserve_two, make_decision_json('high_value_discount', score=169.0, queue_bucket='reserve')),
            (168.0, reserve_three, make_decision_json('high_value_discount', score=168.0, queue_bucket='reserve')),
        ],
    )
    reserve_records = repo.list_queue('reserve')
    repo.record_publication(reserve_one, 'high_value_discount', 444)
    seed_roundup_snapshot(
        repo,
        settings,
        run_key='20260313T121000Z',
        created_at=now - timedelta(minutes=1),
        queue_snapshot_at=queue_window_key(reserve_records),
        roundup_id='roundup_published_item',
        title='Roundup: Published Item',
        item_records=reserve_records,
        omit_context=True,
    )

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    result = asyncio.run(use_case.execute(now, now))

    assert result is not None
    assert result.offer_id == 'steam:501'
    assert result.lane == 'high_value_discount'
    assert result.reason == 'dry_run'
    roundup_injection = result.analytics['selection']['roundup_injection']
    assert roundup_injection['status'] == 'rejected'
    assert roundup_injection['reason'] == 'roundup_item_already_published'
    assert roundup_injection['lookup_mode'] == 'fallback'


def test_publish_next_skips_roundup_when_roundup_item_missing_from_reserve(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, dry_run=True)
    repo = Repositories(settings.db_path)
    repo.initialize()
    now = datetime(2026, 3, 13, 12, 0)
    image_path = tmp_path / 'normal-card.png'
    image_path.write_bytes(b'card')

    planned = make_offer_variant('steam:601', 'Planned Discount')
    reserve_one = make_offer_variant('steam:602', 'Reserve One')
    reserve_two = make_offer_variant('steam:603', 'Reserve Two')
    repo.replace_queue('planned', [(195.0, planned, make_decision_json('high_value_discount', score=195.0))])
    repo.replace_queue(
        'reserve',
        [
            (171.0, reserve_one, make_decision_json('high_value_discount', score=171.0, queue_bucket='reserve')),
            (170.0, reserve_two, make_decision_json('high_value_discount', score=170.0, queue_bucket='reserve')),
        ],
    )
    reserve_records = repo.list_queue('reserve')
    missing_offer = make_offer_variant('steam:604', 'Missing Reserve')
    extra_item = {
        'offer_id': missing_offer.offer_id,
        'title': missing_offer.title,
        'store_url': missing_offer.store_url,
        'store': missing_offer.source.value,
        'source': missing_offer.source.value,
        'lane': 'high_value_discount',
        'score': 169.0,
        'discount_percent': missing_offer.discount_percent,
        'review_score': missing_offer.review_score,
        'is_freebie': missing_offer.is_freebie,
        'price_after_minor': missing_offer.price_after_minor,
        'price_line': 'Missing item',
        'callout': 'Not in reserve',
        'summary_line': missing_offer.title,
        'reason_tags': ['high_value_discount'],
    }
    seed_roundup_snapshot(
        repo,
        settings,
        run_key='20260313T121500Z',
        created_at=now - timedelta(minutes=1),
        queue_snapshot_at=queue_window_key(reserve_records),
        roundup_id='roundup_missing_item',
        title='Roundup: Missing Item',
        item_records=reserve_records,
        extra_items=[extra_item],
        omit_context=True,
    )

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    result = asyncio.run(use_case.execute(now, now))

    assert result is not None
    assert result.offer_id == 'steam:601'
    assert result.lane == 'high_value_discount'
    assert result.reason == 'dry_run'
    roundup_injection = result.analytics['selection']['roundup_injection']
    assert roundup_injection['status'] == 'rejected'
    assert roundup_injection['reason'] == 'roundup_item_not_in_reserve'
    assert roundup_injection['lookup_mode'] == 'fallback'




def test_publish_next_controlled_reserve_release_holds_roundup_candidate_while_stream_is_healthy(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, dry_run=True)
    repo = Repositories(settings.db_path)
    repo.initialize()
    now = datetime(2026, 3, 13, 12, 0)
    image_path = tmp_path / 'normal-card.png'
    image_path.write_bytes(b'card')

    planned = make_offer_variant('steam:641', 'Planned Discount')
    reserve_one = make_offer_variant('steam:642', 'Reserve One')
    reserve_two = make_offer_variant('steam:643', 'Reserve Two')
    reserve_three = make_offer_variant('steam:644', 'Reserve Three')
    repo.replace_queue('planned', [(150.0, planned, make_decision_json('high_value_discount', score=150.0))])
    repo.replace_queue(
        'reserve',
        [
            (171.0, reserve_one, make_decision_json('high_value_discount', score=171.0, queue_bucket='reserve')),
            (170.0, reserve_two, make_decision_json('high_value_discount', score=170.0, queue_bucket='reserve')),
            (169.0, reserve_three, make_decision_json('high_value_discount', score=169.0, queue_bucket='reserve')),
        ],
    )
    reserve_records = repo.list_queue('reserve')
    seed_roundup_snapshot(
        repo,
        settings,
        run_key='20260313T121600Z',
        created_at=now - timedelta(minutes=1),
        queue_snapshot_at=queue_window_key(reserve_records),
        roundup_id='roundup_held_healthy',
        title='Roundup: Held Healthy',
        item_records=reserve_records,
    )

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    result = asyncio.run(use_case.execute(now, now))

    assert result is not None
    assert result.offer_id == 'steam:641'
    assert result.lane == 'high_value_discount'
    assert result.reason == 'dry_run'


def test_publish_next_discount_run_breaker_prefers_roundup_candidate_over_discount_run(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, dry_run=True)
    repo = Repositories(settings.db_path)
    repo.initialize()
    now = datetime(2026, 3, 13, 12, 0)

    planned = make_offer_variant('steam:651', 'Planned Discount')
    reserve_one = make_offer_variant('steam:652', 'Reserve One')
    reserve_two = make_offer_variant('steam:653', 'Reserve Two')
    reserve_three = make_offer_variant('steam:654', 'Reserve Three')
    repo.replace_queue('planned', [(340.0, planned, make_decision_json('high_value_discount', score=340.0))])
    repo.replace_queue(
        'reserve',
        [
            (171.0, reserve_one, make_decision_json('high_value_discount', score=171.0, queue_bucket='reserve')),
            (170.0, reserve_two, make_decision_json('high_value_discount', score=170.0, queue_bucket='reserve')),
            (169.0, reserve_three, make_decision_json('high_value_discount', score=169.0, queue_bucket='reserve')),
        ],
    )
    reserve_records = repo.list_queue('reserve')
    for offset in range(5):
        lane = 'final_push' if offset % 2 == 0 else 'game_of_the_day'
        seed_published_outbox(
            repo,
            make_offer_variant(f'steam:breaker{offset}', f'Recent Discount {offset}'),
            make_decision_json(lane, score=120.0 - offset),
            now - timedelta(minutes=offset + 1),
        )

    seed_roundup_snapshot(
        repo,
        settings,
        run_key='20260313T121700Z',
        created_at=now - timedelta(minutes=1),
        queue_snapshot_at=queue_window_key(reserve_records),
        roundup_id='roundup_breaker_bonus',
        title='Roundup: Breaker Bonus',
        item_records=reserve_records,
    )

    use_case = PublishNextUseCase(settings, repo, ExplodingRenderUseCase(), RecordingPublisher())
    result = asyncio.run(use_case.execute(now, now))

    assert result is not None
    assert result.offer_id == 'roundup:roundup_breaker_bonus'
    assert result.lane == 'roundup_digest'
    assert result.reason == 'dry_run'
    adjustment = result.analytics['selection']['editorial_adjustment']
    assert adjustment['content_type'] == 'roundup'
    assert adjustment['rule_deltas']['discount_run_breaker_bonus'] == 140.0


def test_publish_next_roundup_publish_preserves_roundup_render_diagnostics(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, dry_run=False)
    repo = Repositories(settings.db_path)
    repo.initialize()
    now = datetime(2026, 3, 13, 12, 0)

    reserve_one = make_offer_variant('steam:801', 'Reserve One')
    reserve_two = make_offer_variant('steam:802', 'Reserve Two')
    reserve_three = make_offer_variant('steam:803', 'Reserve Three')
    repo.replace_queue(
        'reserve',
        [
            (220.0, reserve_one, make_decision_json('high_value_discount', score=220.0, queue_bucket='reserve')),
            (218.0, reserve_two, make_decision_json('high_value_discount', score=218.0, queue_bucket='reserve')),
            (216.0, reserve_three, make_decision_json('high_value_discount', score=216.0, queue_bucket='reserve')),
        ],
    )
    reserve_records = repo.list_queue('reserve')
    for offset in range(5):
        seed_published_outbox(
            repo,
            make_offer_variant(f'steam:recentdx{offset}', f'Recent Discount {offset}'),
            make_decision_json('high_value_discount', score=120.0 - offset),
            now - timedelta(minutes=offset + 1),
        )

    seed_roundup_snapshot(
        repo,
        settings,
        run_key='20260313T122500Z',
        created_at=now - timedelta(minutes=1),
        queue_snapshot_at=queue_window_key(reserve_records),
        roundup_id='roundup_diag_digest',
        title='Roundup: Diagnostics',
        item_records=reserve_records,
        card_render_diagnostics={
            'renderer_selected': 'yoto_v4',
            'renderer_fallback_used': False,
            'hero_fallback_used': False,
            'lead_artwork_selected_offer_id': 'steam:801',
            'lead_artwork_selection_reason': 'highest_weighted_roundup_item_artwork',
            'selected_asset_path': str(settings.card_output_dir / 'roundup_diag_digest.png'),
            'render_warnings': [],
        },
    )

    publisher = RecordingPublisher()
    video_manifests = GenerateVideoManifestsUseCase(repo, VideoManifestWriter(settings.video_manifest_output_dir))
    use_case = PublishNextUseCase(settings, repo, ExplodingRenderUseCase(), publisher, video_manifests=video_manifests)
    result = asyncio.run(use_case.execute(now, now))

    assert result is not None
    diagnostics = result.analytics['render']['render_diagnostics']
    assert diagnostics['renderer_selected'] == 'yoto_v4'
    assert diagnostics['lead_artwork_selected_offer_id'] == 'steam:801'
    assert diagnostics['lead_artwork_selection_reason'] == 'highest_weighted_roundup_item_artwork'
    outbox = repo.get_outbox_record('roundup:roundup_diag_digest:20260313T122500Z')
    assert outbox is not None
    stored = outbox.payload_json['artifact']['render_diagnostics']
    assert stored['renderer_selected'] == 'yoto_v4'
    assert stored['lead_artwork_selected_offer_id'] == 'steam:801'


def test_publish_next_emits_card_qa_summary_artifact(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, dry_run=True)
    repo = Repositories(settings.db_path)
    repo.initialize()
    now = datetime(2026, 3, 13, 12, 0)
    image_path = tmp_path / 'normal-card.png'
    image_path.write_bytes(b'card')

    planned = make_offer_variant('steam:901', 'Planned Discount')
    repo.replace_queue('planned', [(180.0, planned, make_decision_json('high_value_discount', score=180.0))])
    for offset in range(2):
        seed_published_outbox(
            repo,
            make_offer_variant(f'steam:qa{offset}', f'Published Discount {offset}'),
            make_decision_json('high_value_discount', score=140.0 - offset),
            now - timedelta(minutes=offset + 1),
        )

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    result = asyncio.run(use_case.execute(now, now))

    assert result is not None
    qa_summary = result.analytics['render']['card_qa_summary']
    assert qa_summary['card_type_mix']['DISCOUNT'] >= 1
    assert qa_summary['renderer_fallback_count'] == 0
    assert qa_summary['hero_fallback_count'] == 0
    with repo.connect() as connection:
        row = connection.execute(
            "SELECT payload_json FROM analytics_artifacts WHERE artifact_type = 'card_qa_summary'"
        ).fetchone()
    assert row is not None
    payload = json.loads(row['payload_json'])
    assert payload['card_type_mix']['DISCOUNT'] >= 1
    assert payload['leading_card_family_streak']['length'] >= 1


def test_publish_next_roundup_publish_is_idempotent(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, dry_run=True)
    repo = Repositories(settings.db_path)
    repo.initialize()
    now = datetime(2026, 3, 13, 12, 0)
    image_path = tmp_path / 'normal-card.png'
    image_path.write_bytes(b'card')

    planned = make_offer_variant('steam:701', 'Planned Discount')
    reserve_one = make_offer_variant('steam:702', 'Reserve One')
    reserve_two = make_offer_variant('steam:703', 'Reserve Two')
    reserve_three = make_offer_variant('steam:704', 'Reserve Three')
    repo.replace_queue('planned', [(185.0, planned, make_decision_json('high_value_discount', score=185.0))])
    repo.replace_queue(
        'reserve',
        [
            (172.0, reserve_one, make_decision_json('high_value_discount', score=172.0, queue_bucket='reserve')),
            (171.0, reserve_two, make_decision_json('high_value_discount', score=171.0, queue_bucket='reserve')),
            (170.0, reserve_three, make_decision_json('high_value_discount', score=170.0, queue_bucket='reserve')),
        ],
    )
    reserve_records = repo.list_queue('reserve')
    roundup_id = 'roundup_idempotent'
    run_key = '20260313T122000Z'
    seed_roundup_snapshot(
        repo,
        settings,
        run_key=run_key,
        created_at=now - timedelta(minutes=1),
        queue_snapshot_at=queue_window_key(reserve_records),
        roundup_id=roundup_id,
        title='Roundup: Idempotent',
        item_records=reserve_records,
    )
    synthetic_offer = make_offer_variant(f'roundup:{roundup_id}', 'Roundup: Idempotent')
    seed_published_outbox(
        repo,
        synthetic_offer,
        make_decision_json('roundup_digest', score=200.0, queue_bucket='reserve', template_id='roundup_digest', content_type='roundup'),
        now - timedelta(minutes=1),
        idempotency_key=f'roundup:{roundup_id}:{run_key}',
    )

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    result = asyncio.run(use_case.execute(now, now))

    assert result is not None
    assert result.offer_id == 'steam:701'
    assert result.lane == 'high_value_discount'
    assert result.reason == 'dry_run'
    assert len(repo.list_queue('reserve')) == 3

