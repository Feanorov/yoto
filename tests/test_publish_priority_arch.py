from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import json
from pathlib import Path

from application.use_cases.publish_next import PublishNextUseCase
from infrastructure.db.repositories import Repositories
from domain.entities.offer import OfferKind, OfferSource

from .support import make_test_settings
from .test_caption_builder_arch import make_offer
from .test_publish_reliability_arch import RecordingPublisher, StaticRenderUseCase


def make_decision_json(
    lane: str,
    *,
    score: float,
    queue_bucket: str = 'planned',
    must_ship: bool = False,
    manual_force_override: bool = False,
) -> dict:
    return {
        'lane': lane,
        'template_id': 'final_push' if lane == 'final_push' else 'steam_discount',
        'must_ship': must_ship,
        'queue_bucket': queue_bucket,
        'decision_reasons': [lane],
        'quality_reasons': ['review_threshold'],
        'dedup_reason': 'new_offer',
        'is_final_push': lane == 'final_push',
        'is_historical_best': False,
        'price_improved_minor': 0,
        'score': score,
        'previous_price_minor': None,
        'previous_posted_at': None,
        'best_price_minor': None,
        'manual_force_override': manual_force_override,
        'debug': {},
    }


def make_settings(tmp_path: Path):
    return make_test_settings(tmp_path, dry_run=True)


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
    elif offer_kind in {OfferKind.EVENT, OfferKind.FESTIVAL}:
        offer.price_before_minor = None
        offer.price_after_minor = None
        offer.discount_percent = 0
    return offer


def seed_published_outbox(repo: Repositories, offer, decision_json: dict, published_at: datetime) -> None:
    payload = {
        'schema_version': 1,
        'offer_id': offer.offer_id,
        'artifact': {
            'offer_id': offer.offer_id,
            'template_id': decision_json.get('template_id'),
            'assets_used': [],
            'caption_hash': f'caption-{offer.offer_id}',
            'image_hash': f'image-{offer.offer_id}',
            'idempotency_key': f'seed-{offer.offer_id}-{published_at.timestamp()}',
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
                f'seed-{offer.offer_id}-{published_at.timestamp()}',
                f'caption-{offer.offer_id}',
                f'image-{offer.offer_id}',
                None,
                1000,
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


def test_publish_next_prefers_priority_over_fifo_order(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')

    backlog = make_offer()
    backlog.offer_id = 'steam:10'
    backlog.game_id = '10'
    backlog.franchise_key = 'backlog-deal'
    backlog.title = 'Backlog Deal'
    backlog.promo_end = datetime(2026, 3, 12, 18, 0)

    final_push = make_offer()
    final_push.offer_id = 'steam:20'
    final_push.game_id = '20'
    final_push.franchise_key = 'final-push-deal'
    final_push.title = 'Final Push Deal'
    final_push.promo_end = datetime(2026, 3, 12, 13, 0)

    repo.replace_queue(
        'planned',
        [
            (95.0, backlog, make_decision_json('high_value_discount', score=95.0)),
            (70.0, final_push, make_decision_json('final_push', score=70.0, must_ship=True)),
        ],
    )

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    result = asyncio.run(use_case.execute(datetime(2026, 3, 12, 12, 0), datetime(2026, 3, 12, 12, 0)))

    assert result is not None
    assert result.offer_id == 'steam:20'
    assert result.lane == 'final_push'
    assert result.analytics['selection']['publish_priority']['lane'] == 'final_push'


def test_publish_next_skips_capped_lane_and_uses_next_candidate(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')

    capped = make_offer()
    capped.offer_id = 'steam:30'
    capped.game_id = '30'
    capped.franchise_key = 'already-used-game-of-day'
    capped.title = 'Already Used Game Of Day'
    capped.promo_end = datetime(2026, 3, 13, 18, 0)

    fallback = make_offer()
    fallback.offer_id = 'steam:40'
    fallback.game_id = '40'
    fallback.franchise_key = 'fallback-deal'
    fallback.title = 'Fallback Deal'
    fallback.promo_end = datetime(2026, 3, 14, 18, 0)

    repo.increment_daily_lane('2026-03-12', 'game_of_the_day')
    repo.replace_queue(
        'planned',
        [
            (130.0, capped, make_decision_json('game_of_the_day', score=130.0)),
            (92.0, fallback, make_decision_json('high_value_discount', score=92.0)),
        ],
    )

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    result = asyncio.run(use_case.execute(datetime(2026, 3, 12, 12, 0), datetime(2026, 3, 12, 12, 0)))

    assert result is not None
    assert result.offer_id == 'steam:40'
    assert result.lane == 'high_value_discount'



def test_publish_next_editorial_control_penalizes_fourth_same_content_type(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')
    now = datetime(2026, 3, 12, 12, 0)

    seed_published_outbox(repo, make_offer_variant('steam:101', 'Recent Discount One'), make_decision_json('high_value_discount', score=110.0), now - timedelta(minutes=1))
    seed_published_outbox(repo, make_offer_variant('steam:102', 'Recent Discount Two'), make_decision_json('backlog_filler', score=90.0), now - timedelta(minutes=2))
    seed_published_outbox(repo, make_offer_variant('steam:103', 'Recent Discount Three'), make_decision_json('final_push', score=80.0), now - timedelta(minutes=3))
    seed_published_outbox(repo, make_offer_variant('event:104', 'Recent Event', offer_kind=OfferKind.FESTIVAL, source=OfferSource.EVENT), make_decision_json('event_festival', score=50.0), now - timedelta(minutes=4))

    current = make_offer_variant('steam:201', 'Current Discount')
    repo.replace_queue('planned', [(345.0, current, make_decision_json('high_value_discount', score=345.0))])

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    result = asyncio.run(use_case.execute(now, now))

    assert result is not None
    adjustment = result.analytics['selection']['editorial_adjustment']
    assert result.offer_id == 'steam:201'
    assert adjustment['content_type'] == 'discount'
    assert adjustment['rule_deltas']['same_content_type_streak_penalty'] == -100.0
    assert 'long_discount_streak_penalty' not in adjustment['rule_deltas']


def test_publish_next_editorial_control_surfaces_event_when_no_recent_event(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')
    now = datetime(2026, 3, 12, 12, 0)

    seed_published_outbox(repo, make_offer_variant('steam:301', 'Recent Discount One'), make_decision_json('final_push', score=110.0), now - timedelta(minutes=1))
    seed_published_outbox(repo, make_offer_variant('epic:302', 'Recent Freebie', offer_kind=OfferKind.FREEBIE, source=OfferSource.EPIC), make_decision_json('breaking_freebie', score=95.0), now - timedelta(minutes=2))
    seed_published_outbox(repo, make_offer_variant('steam:303', 'Recent Discount Two'), make_decision_json('game_of_the_day', score=100.0), now - timedelta(minutes=3))
    seed_published_outbox(repo, make_offer_variant('steam:304', 'Recent Discount Three'), make_decision_json('backlog_filler', score=80.0), now - timedelta(minutes=4))

    event_offer = make_offer_variant('event:305', 'Current Event', offer_kind=OfferKind.FESTIVAL, source=OfferSource.EVENT)
    discount_offer = make_offer_variant('steam:306', 'Current Discount')
    repo.replace_queue(
        'planned',
        [
            (250.0, discount_offer, make_decision_json('high_value_discount', score=250.0)),
            (20.0, event_offer, make_decision_json('event_festival', score=20.0)),
        ],
    )

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    result = asyncio.run(use_case.execute(now, now))

    assert result is not None
    assert result.offer_id == 'event:305'
    assert result.lane == 'event_festival'
    assert result.analytics['selection']['editorial_adjustment']['rule_deltas']['event_gap_bonus'] == 32.0


def test_publish_next_editorial_control_prefers_freebie_over_filler_discount(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')
    now = datetime(2026, 3, 12, 12, 0)

    seed_published_outbox(repo, make_offer_variant('steam:401', 'Recent Discount One'), make_decision_json('final_push', score=110.0), now - timedelta(minutes=1))
    seed_published_outbox(repo, make_offer_variant('steam:402', 'Recent Discount Two'), make_decision_json('game_of_the_day', score=100.0), now - timedelta(minutes=2))
    seed_published_outbox(repo, make_offer_variant('steam:403', 'Recent Discount Three'), make_decision_json('final_push', score=90.0), now - timedelta(minutes=3))
    seed_published_outbox(repo, make_offer_variant('steam:404', 'Recent Discount Four'), make_decision_json('game_of_the_day', score=80.0), now - timedelta(minutes=4))

    filler_offer = make_offer_variant('steam:405', 'Filler Discount')
    freebie_offer = make_offer_variant('epic:406', 'Freebie Pick', offer_kind=OfferKind.FREEBIE, source=OfferSource.EPIC)
    repo.replace_queue('planned', [(100.0, filler_offer, make_decision_json('backlog_filler', score=100.0))])
    repo.replace_queue('reserve', [(-300.0, freebie_offer, make_decision_json('breaking_freebie', score=-300.0, queue_bucket='reserve'))])

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    result = asyncio.run(use_case.execute(now, now))

    assert result is not None
    assert result.offer_id == 'epic:406'
    assert result.lane == 'breaking_freebie'
    assert result.analytics['selection']['editorial_adjustment']['rule_deltas']['freebie_over_filler_bonus'] == 18.0
    assert result.analytics['selection']['editorial_adjustment']['rule_deltas']['discount_run_breaker_bonus'] == 120.0



def test_publish_next_controlled_reserve_release_holds_reserve_freebie_while_stream_is_healthy(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')
    now = datetime(2026, 3, 12, 12, 0)

    planned_discount = make_offer_variant('steam:407', 'Planned Discount')
    reserve_freebie = make_offer_variant('epic:408', 'Held Freebie', offer_kind=OfferKind.FREEBIE, source=OfferSource.EPIC)
    repo.replace_queue('planned', [(180.0, planned_discount, make_decision_json('high_value_discount', score=180.0))])
    repo.replace_queue('reserve', [(250.0, reserve_freebie, make_decision_json('breaking_freebie', score=250.0, queue_bucket='reserve'))])

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    result = asyncio.run(use_case.execute(now, now))

    assert result is not None
    assert result.offer_id == 'steam:407'
    assert result.lane == 'high_value_discount'
    assert result.reason == 'dry_run'
    assert len(repo.list_queue('reserve')) == 1



def test_publish_next_controlled_reserve_release_releases_reserve_event_when_planned_is_empty(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')
    now = datetime(2026, 3, 12, 12, 0)

    reserve_discount = make_offer_variant('steam:409', 'Reserve Discount')
    reserve_event = make_offer_variant('event:410', 'Reserve Event', offer_kind=OfferKind.FESTIVAL, source=OfferSource.EVENT)
    repo.replace_queue('planned', [])
    repo.replace_queue(
        'reserve',
        [
            (260.0, reserve_discount, make_decision_json('high_value_discount', score=260.0, queue_bucket='reserve')),
            (60.0, reserve_event, make_decision_json('event_festival', score=60.0, queue_bucket='reserve')),
        ],
    )

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    result = asyncio.run(use_case.execute(now, now))

    assert result is not None
    assert result.offer_id == 'event:410'
    assert result.lane == 'event_festival'
    assert result.reason == 'dry_run'


def test_publish_next_editorial_control_penalizes_recent_same_lane_repetition(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')
    now = datetime(2026, 3, 12, 12, 0)

    seed_published_outbox(repo, make_offer_variant('steam:501', 'Recent High Value One'), make_decision_json('high_value_discount', score=110.0), now - timedelta(minutes=1))
    seed_published_outbox(repo, make_offer_variant('event:502', 'Recent Event', offer_kind=OfferKind.FESTIVAL, source=OfferSource.EVENT), make_decision_json('event_festival', score=80.0), now - timedelta(minutes=2))
    seed_published_outbox(repo, make_offer_variant('steam:503', 'Recent High Value Two'), make_decision_json('high_value_discount', score=100.0), now - timedelta(minutes=3))
    seed_published_outbox(repo, make_offer_variant('steam:504', 'Recent Final Push'), make_decision_json('final_push', score=90.0), now - timedelta(minutes=4))

    current = make_offer_variant('steam:505', 'Current High Value')
    repo.replace_queue('planned', [(254.0, current, make_decision_json('high_value_discount', score=254.0))])

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    result = asyncio.run(use_case.execute(now, now))

    assert result is not None
    adjustment = result.analytics['selection']['editorial_adjustment']
    assert result.offer_id == 'steam:505'
    assert adjustment['rule_deltas']['same_lane_repeat_penalty'] == -36.0


def test_publish_next_editorial_control_is_soft_and_does_not_empty_selection(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')
    now = datetime(2026, 3, 12, 12, 0)

    seed_published_outbox(repo, make_offer_variant('steam:601', 'Recent Discount One'), make_decision_json('high_value_discount', score=110.0), now - timedelta(minutes=1))
    seed_published_outbox(repo, make_offer_variant('steam:602', 'Recent Discount Two'), make_decision_json('backlog_filler', score=90.0), now - timedelta(minutes=2))
    seed_published_outbox(repo, make_offer_variant('steam:603', 'Recent Discount Three'), make_decision_json('final_push', score=80.0), now - timedelta(minutes=3))

    current = make_offer_variant('steam:604', 'Current Discount')
    repo.replace_queue('planned', [(180.0, current, make_decision_json('high_value_discount', score=180.0))])

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    result = asyncio.run(use_case.execute(now, now))

    assert result is not None
    assert result.offer_id == 'steam:604'
    assert result.reason == 'dry_run'
    assert result.analytics['selection']['editorial_adjustment']['total_delta'] < 0
    assert 'same_content_type_streak_penalty' in result.analytics['selection']['editorial_adjustment']['reasons']



def test_publish_next_editorial_control_breaks_long_discount_streak_with_freebie(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')
    now = datetime(2026, 3, 12, 12, 0)

    seed_published_outbox(repo, make_offer_variant('steam:701', 'Recent Discount One'), make_decision_json('final_push', score=110.0), now - timedelta(minutes=1))
    seed_published_outbox(repo, make_offer_variant('steam:702', 'Recent Discount Two'), make_decision_json('game_of_the_day', score=100.0), now - timedelta(minutes=2))
    seed_published_outbox(repo, make_offer_variant('steam:703', 'Recent Discount Three'), make_decision_json('final_push', score=90.0), now - timedelta(minutes=3))
    seed_published_outbox(repo, make_offer_variant('steam:704', 'Recent Discount Four'), make_decision_json('game_of_the_day', score=80.0), now - timedelta(minutes=4))
    seed_published_outbox(repo, make_offer_variant('steam:705', 'Recent Discount Five'), make_decision_json('final_push', score=70.0), now - timedelta(minutes=5))

    discount_offer = make_offer_variant('steam:706', 'Current Discount')
    freebie_offer = make_offer_variant('epic:707', 'Current Freebie', offer_kind=OfferKind.FREEBIE, source=OfferSource.EPIC)
    repo.replace_queue(
        'planned',
        [
            (260.0, discount_offer, make_decision_json('high_value_discount', score=260.0)),
            (210.0, freebie_offer, make_decision_json('backlog_filler', score=210.0)),
        ],
    )

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    result = asyncio.run(use_case.execute(now, now))

    assert result is not None
    assert result.offer_id == 'epic:707'
    assert result.lane == 'backlog_filler'
    adjustment = result.analytics['selection']['editorial_adjustment']
    assert adjustment['content_type'] == 'freebie'
    assert adjustment['rule_deltas']['discount_run_breaker_bonus'] == 120.0



def test_publish_next_editorial_control_remains_soft_when_only_discounts_exist(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')
    now = datetime(2026, 3, 12, 12, 0)

    seed_published_outbox(repo, make_offer_variant('steam:801', 'Recent Discount One'), make_decision_json('final_push', score=110.0), now - timedelta(minutes=1))
    seed_published_outbox(repo, make_offer_variant('steam:802', 'Recent Discount Two'), make_decision_json('game_of_the_day', score=100.0), now - timedelta(minutes=2))
    seed_published_outbox(repo, make_offer_variant('steam:803', 'Recent Discount Three'), make_decision_json('final_push', score=90.0), now - timedelta(minutes=3))
    seed_published_outbox(repo, make_offer_variant('steam:804', 'Recent Discount Four'), make_decision_json('game_of_the_day', score=80.0), now - timedelta(minutes=4))
    seed_published_outbox(repo, make_offer_variant('steam:805', 'Recent Discount Five'), make_decision_json('final_push', score=70.0), now - timedelta(minutes=5))

    current = make_offer_variant('steam:806', 'Current Discount')
    repo.replace_queue('planned', [(260.0, current, make_decision_json('high_value_discount', score=260.0))])

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    result = asyncio.run(use_case.execute(now, now))

    assert result is not None
    assert result.offer_id == 'steam:806'
    assert result.reason == 'dry_run'
    adjustment = result.analytics['selection']['editorial_adjustment']
    assert adjustment['rule_deltas']['same_content_type_streak_penalty'] == -100.0
    assert adjustment['rule_deltas']['long_discount_streak_penalty'] == -60.0
    assert 'discount_run_breaker_bonus' not in adjustment['rule_deltas']



def test_publish_next_discount_run_breaker_surfaces_event_over_discount_run(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')
    now = datetime(2026, 3, 12, 12, 0)

    seed_published_outbox(repo, make_offer_variant('steam:901', 'Recent Discount One'), make_decision_json('final_push', score=110.0), now - timedelta(minutes=1))
    seed_published_outbox(repo, make_offer_variant('steam:902', 'Recent Discount Two'), make_decision_json('game_of_the_day', score=100.0), now - timedelta(minutes=2))
    seed_published_outbox(repo, make_offer_variant('steam:903', 'Recent Discount Three'), make_decision_json('final_push', score=90.0), now - timedelta(minutes=3))
    seed_published_outbox(repo, make_offer_variant('steam:904', 'Recent Discount Four'), make_decision_json('game_of_the_day', score=80.0), now - timedelta(minutes=4))
    seed_published_outbox(repo, make_offer_variant('steam:905', 'Recent Discount Five'), make_decision_json('final_push', score=70.0), now - timedelta(minutes=5))

    discount_offer = make_offer_variant('steam:906', 'Current Discount')
    event_offer = make_offer_variant('event:907', 'Current Event', offer_kind=OfferKind.FESTIVAL, source=OfferSource.EVENT)
    repo.replace_queue(
        'planned',
        [
            (420.0, discount_offer, make_decision_json('high_value_discount', score=420.0)),
            (0.0, event_offer, make_decision_json('event_festival', score=0.0)),
        ],
    )

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    result = asyncio.run(use_case.execute(now, now))

    assert result is not None
    assert result.offer_id == 'event:907'
    adjustment = result.analytics['selection']['editorial_adjustment']
    assert adjustment['content_type'] == 'event'
    assert adjustment['rule_deltas']['discount_run_breaker_bonus'] == 90.0
    assert adjustment['rule_deltas']['event_gap_bonus'] == 32.0



def test_publish_next_discount_run_breaker_does_not_apply_without_long_discount_streak(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')
    now = datetime(2026, 3, 12, 12, 0)

    seed_published_outbox(repo, make_offer_variant('steam:1001', 'Recent Discount One'), make_decision_json('final_push', score=110.0), now - timedelta(minutes=1))
    seed_published_outbox(repo, make_offer_variant('steam:1002', 'Recent Discount Two'), make_decision_json('game_of_the_day', score=100.0), now - timedelta(minutes=2))
    seed_published_outbox(repo, make_offer_variant('steam:1003', 'Recent Discount Three'), make_decision_json('final_push', score=90.0), now - timedelta(minutes=3))

    discount_offer = make_offer_variant('steam:1004', 'Current Discount')
    freebie_offer = make_offer_variant('epic:1005', 'Current Freebie', offer_kind=OfferKind.FREEBIE, source=OfferSource.EPIC)
    repo.replace_queue(
        'planned',
        [
            (260.0, discount_offer, make_decision_json('high_value_discount', score=260.0)),
            (210.0, freebie_offer, make_decision_json('backlog_filler', score=210.0)),
        ],
    )

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    result = asyncio.run(use_case.execute(now, now))

    assert result is not None
    assert result.offer_id == 'steam:1004'
    adjustment = result.analytics['selection']['editorial_adjustment']
    assert adjustment['content_type'] == 'discount'
    assert 'discount_run_breaker_bonus' not in adjustment['rule_deltas']
