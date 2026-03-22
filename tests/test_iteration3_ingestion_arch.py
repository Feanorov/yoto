from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

from application.use_cases.ingest_source import IngestSourceUseCase
from application.use_cases.normalize_offer import normalize_calendar_events
from application.use_cases.plan_queue import PlanQueueUseCase
from dealbot.settings import StaticConfig
from domain.entities.offer import Offer, OfferKind, OfferSource
from domain.policies.dedup_policy import DedupPolicy
from domain.policies.decision_policy import DecisionPolicy
from domain.policies.editorial_policy import EditorialPolicy
from domain.policies.quality_gate_policy import QualityGatePolicy
from infrastructure.db.repositories import Repositories

from .support import make_test_settings
from .test_caption_builder_arch import make_offer


class StubSteamClient:
    def __init__(self, rows: list[dict], source_state: dict[str, str] | None = None) -> None:
        self.rows = rows
        self.source_state = source_state or {'mode': 'healthy', 'reason': 'fresh'}

    async def search_specials(self, limit: int) -> list[dict]:
        return self.rows[:limit]


class StubEpicClient:
    def __init__(self, offers: list[dict] | None = None) -> None:
        self.offers = offers or []

    async def get_free_games(self) -> list[dict]:
        return self.offers


class StubSteamEventsClient:
    def __init__(self, events: list[dict]) -> None:
        self.events = events

    async def list_events(self, now: datetime) -> list[dict]:
        return self.events


class StubIngest:
    def __init__(self, offers: list[Offer]) -> None:
        self.offers = offers

    async def execute(self, now: datetime) -> list[Offer]:
        return self.offers


class StubEnrich:
    async def enrich(self, offers: list[Offer], limit: int) -> list[Offer]:
        return offers


def make_event_offer(
    offer_id: str,
    title: str,
    store_url: str,
    now: datetime,
    *,
    starts_delta: timedelta = timedelta(hours=-2),
    ends_delta: timedelta = timedelta(days=5),
) -> Offer:
    offer = make_offer()
    offer.offer_id = offer_id
    offer.source = OfferSource.EVENT
    offer.source_ref = offer_id.split(':', 1)[-1]
    offer.offer_kind = OfferKind.FESTIVAL
    offer.game_id = offer.source_ref
    offer.franchise_key = offer.source_ref.replace(':', '-')
    offer.title = title
    offer.store_url = store_url
    offer.price_before_minor = None
    offer.price_after_minor = None
    offer.discount_percent = 0
    offer.promo_start = now + starts_delta
    offer.promo_end = now + ends_delta
    offer.review_score = None
    offer.review_count = None
    offer.achievements_count = None
    offer.has_trading_cards = False
    offer.tags = [title]
    offer.genres = [title]
    offer.short_description = f'{title} event'
    return offer


def make_discount_offer(
    offer_id: str,
    title: str,
    *,
    genre: str,
    tag: str | None = None,
) -> Offer:
    offer = make_offer()
    offer.offer_id = offer_id
    offer.source_ref = offer_id.split(':', 1)[-1]
    offer.game_id = offer.source_ref
    offer.franchise_key = offer.source_ref.replace(':', '-')
    offer.title = title
    offer.genres = [genre]
    offer.tags = [tag] if tag else [genre]
    return offer


def test_normalize_calendar_events_filters_expired_and_normalizes_event_fields(tmp_path: Path) -> None:
    calendar_path = tmp_path / 'calendar.json'
    now = datetime(2026, 3, 10, 12, 0)
    payload = {
        'events': [
            {
                'id': 'spring-fest-2026',
                'title': 'Steam Strategy Fest Remastered®',
                'url': 'https://store.steampowered.com/sale/strategy-fest',
                'image_url': 'https://example.com/strategy-fest.png',
                'description': 'Massive tactics discounts.',
                'starts_at': '2026-03-10T09:00:00Z',
                'ends_at': '2026-03-17T17:00:00Z',
                'hashtags': ['#Strategy Fest', 'strategy-fest', ''],
            },
            {
                'id': 'expired-event',
                'title': 'Old Event',
                'url': 'https://store.steampowered.com/sale/old-event',
                'starts_at': '2026-03-01T09:00:00Z',
                'ends_at': '2026-03-02T17:00:00Z',
            },
        ]
    }
    calendar_path.write_text(json.dumps(payload), encoding='utf-8-sig')

    offers = normalize_calendar_events(calendar_path, now)

    assert len(offers) == 1
    event = offers[0]
    assert event.offer_id == 'event:spring-fest-2026'
    assert event.title == 'Steam Strategy Fest'
    assert event.is_event is True
    assert event.tags == ['strategy_fest']
    assert event.short_description == 'Massive tactics discounts.'
    assert event.assets.hero == 'https://example.com/strategy-fest.png'
    assert event.promo_start == datetime(2026, 3, 10, 9, 0)
    assert event.promo_end == datetime(2026, 3, 17, 17, 0)


def test_ingest_source_dedupes_calendar_and_auto_events_by_store_url(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path)
    now = datetime(2026, 3, 10, 12, 0)
    settings.calendar_events_path.write_text(
        json.dumps(
            {
                'events': [
                    {
                        'id': 'calendar-fest',
                        'title': 'Calendar Strategy Fest',
                        'url': 'https://store.steampowered.com/sale/strategy-fest',
                        'starts_at': '2026-03-10T09:00:00Z',
                        'ends_at': '2026-03-17T17:00:00Z',
                    }
                ]
            }
        ),
        encoding='utf-8',
    )
    steam_client = StubSteamClient(
        [
            {
                'app_id': 100,
                'title': 'Steam Deal',
                'store_url': 'https://store.steampowered.com/app/100',
                'price_before': 20000,
                'price_after': 10000,
                'discount_percent': 50,
                'image_url': 'https://example.com/steam-deal.png',
            }
        ]
    )
    events_client = StubSteamEventsClient(
        [
            {
                'id': 'auto-fest',
                'title': 'Auto Strategy Fest',
                'url': 'https://store.steampowered.com/sale/strategy-fest',
                'starts_at': '2026-03-10T08:00:00Z',
                'ends_at': '2026-03-18T17:00:00Z',
            }
        ]
    )
    use_case = IngestSourceUseCase(settings, steam_client, StubEpicClient(), events_client)

    offers = asyncio.run(use_case.execute(now))

    assert len(offers) == 2
    steam_offer = next(offer for offer in offers if offer.source == OfferSource.STEAM)
    event_offer = next(offer for offer in offers if offer.source == OfferSource.EVENT)
    assert steam_offer.metadata['source_state'] == 'healthy'
    assert steam_offer.metadata['steam_state_reason'] == 'fresh'
    assert event_offer.offer_id == 'event:calendar-fest'
    assert event_offer.title == 'Calendar Strategy Fest'


def test_plan_queue_builds_sale_event_context_and_links_related_discounts(tmp_path: Path) -> None:
    now = datetime(2026, 3, 10, 12, 0)
    settings = make_test_settings(
        tmp_path,
        static=StaticConfig(planned_queue_size=4, reserve_queue_size=4),
        sale_event_mode='auto',
    )
    repositories = Repositories(settings.db_path)
    repositories.initialize()

    visual_fest = make_event_offer(
        'event:visual-fest',
        'Steam Visual Novel Fest',
        'https://store.steampowered.com/sale/visual-novel-fest',
        now,
    )
    strategy_fest = make_event_offer(
        'event:strategy-fest',
        'Steam Strategy Fest',
        'https://store.steampowered.com/sale/strategy-fest',
        now,
    )
    linked = make_discount_offer(
        'steam:42',
        'Mystery of the Lantern',
        genre='Visual Novel',
        tag='Visual Novel Fest',
    )
    unrelated = make_discount_offer(
        'steam:43',
        'Action Blast',
        genre='Action',
        tag='Action',
    )

    planner = PlanQueueUseCase(
        settings=settings,
        repositories=repositories,
        ingest_source=StubIngest([visual_fest, strategy_fest, linked, unrelated]),
        enrich_offer=StubEnrich(),
        decision_policy=DecisionPolicy(
            quality_gate=QualityGatePolicy(min_review_count=50, publisher_whitelist=set()),
            editorial_policy=EditorialPolicy(min_game_of_the_day_score=65),
        ),
        dedup_policy=DedupPolicy(),
    )

    plan = asyncio.run(planner.execute(now, now))

    assert plan.context['sale_event_mode'] == 'auto'
    assert plan.context['active'] is True
    assert plan.context['active_event_offer_ids'] == ['event:strategy-fest', 'event:visual-fest']
    assert 'steam_visual_novel_fest' in plan.context['phrase_tokens']
    assert plan.metrics['sale_event.context_active'] == 1
    assert plan.metrics['sale_event.active_events'] == 2
    assert plan.metrics['sale_event.linked_candidates'] == 1
    assert sum(1 for item in plan.planned if item.offer.is_event) == 1
    assert sum(1 for item in plan.reserve if item.offer.is_event) == 1
    selected_items = [*plan.planned, *plan.reserve]
    linked_candidate = next(item for item in selected_items if item.offer.offer_id == 'steam:42')
    assert linked_candidate.decision_json['recommended_post_mode'] in {'solo_post', 'roundup_candidate'}
    assert linked_candidate.decision_json['debug']['sale_event'] == {
        'mode': 'auto',
        'active': False,
        'linked': True,
    }

def _build_planner(tmp_path: Path, offers: list[Offer], *, sale_event_mode: str) -> PlanQueueUseCase:
    settings = make_test_settings(
        tmp_path,
        static=StaticConfig(planned_queue_size=4, reserve_queue_size=4),
        sale_event_mode=sale_event_mode,
    )
    repositories = Repositories(settings.db_path)
    repositories.initialize()
    return PlanQueueUseCase(
        settings=settings,
        repositories=repositories,
        ingest_source=StubIngest(offers),
        enrich_offer=StubEnrich(),
        decision_policy=DecisionPolicy(
            quality_gate=QualityGatePolicy(min_review_count=50, publisher_whitelist=set()),
            editorial_policy=EditorialPolicy(min_game_of_the_day_score=65),
        ),
        dedup_policy=DedupPolicy(),
    )


def test_ingest_source_turns_auto_events_into_normal_offer_objects(tmp_path: Path) -> None:
    from application.use_cases.normalize_offer import normalize_auto_event

    settings = make_test_settings(tmp_path, degraded_sources=frozenset({'steam', 'epic'}))
    now = datetime(2026, 3, 10, 12, 0)
    raw_event = {
        'id': 'tower-defense-fest',
        'title': 'Steam Tower Defense Fest',
        'url': 'https://store.steampowered.com/category/tower_defense',
        'image_url': 'https://example.com/tower-defense-fest.png',
        'description': 'A focused event for tower defense deals.',
        'starts_at': '2026-03-10T09:00:00Z',
        'ends_at': '2026-03-17T17:00:00Z',
        'hashtags': ['#TowerDefense'],
    }
    use_case = IngestSourceUseCase(
        settings,
        StubSteamClient([]),
        StubEpicClient(),
        StubSteamEventsClient([raw_event]),
    )

    offers = asyncio.run(use_case.execute(now))

    assert len(offers) == 1
    event_offer = offers[0]
    assert isinstance(event_offer, Offer)
    assert event_offer.source == OfferSource.EVENT
    assert event_offer.offer_kind == OfferKind.FESTIVAL
    assert event_offer.is_event is True
    assert event_offer.to_snapshot() == normalize_auto_event(raw_event, now).to_snapshot()


def test_sale_event_auto_mode_only_activates_for_live_events(tmp_path: Path) -> None:
    now = datetime(2026, 3, 10, 12, 0)
    planner = _build_planner(tmp_path / 'auto-mode', [], sale_event_mode='auto')
    live_event = make_event_offer(
        'event:live-fest',
        'Steam Live Fest',
        'https://store.steampowered.com/sale/live-fest',
        now,
    )
    future_event = make_event_offer(
        'event:future-fest',
        'Steam Future Fest',
        'https://store.steampowered.com/sale/future-fest',
        now,
        starts_delta=timedelta(days=1),
        ends_delta=timedelta(days=7),
    )

    assert planner._build_sale_event_context([future_event], now) is None
    context = planner._build_sale_event_context([live_event], now)
    assert context is not None
    assert context.mode == 'auto'
    assert context.event_offer_ids == frozenset({'event:live-fest'})


def test_sale_event_force_mode_can_use_nonexpired_future_event(tmp_path: Path) -> None:
    now = datetime(2026, 3, 10, 12, 0)
    planner = _build_planner(tmp_path / 'force-mode', [], sale_event_mode='force')
    future_event = make_event_offer(
        'event:future-fest',
        'Steam Future Fest',
        'https://store.steampowered.com/sale/future-fest',
        now,
        starts_delta=timedelta(days=1),
        ends_delta=timedelta(days=7),
    )

    context = planner._build_sale_event_context([future_event], now)

    assert context is not None
    assert context.mode == 'force'
    assert context.event_offer_ids == frozenset({'event:future-fest'})


def test_sale_event_off_mode_disables_context_even_with_live_event(tmp_path: Path) -> None:
    now = datetime(2026, 3, 10, 12, 0)
    planner = _build_planner(tmp_path / 'off-mode', [], sale_event_mode='off')
    live_event = make_event_offer(
        'event:live-fest',
        'Steam Live Fest',
        'https://store.steampowered.com/sale/live-fest',
        now,
    )

    assert planner._build_sale_event_context([live_event], now) is None


def test_normal_selection_is_unchanged_without_sale_event_context(tmp_path: Path) -> None:
    now = datetime(2026, 3, 10, 12, 0)
    offers = [
        make_discount_offer('steam:201', 'Action One', genre='Action', tag='Action'),
        make_discount_offer('steam:202', 'Strategy Two', genre='Strategy', tag='Strategy'),
    ]
    planner_auto = _build_planner(tmp_path / 'auto-normal', offers, sale_event_mode='auto')
    planner_off = _build_planner(tmp_path / 'off-normal', [offer for offer in offers], sale_event_mode='off')

    auto_plan = asyncio.run(planner_auto.execute(now, now))
    off_plan = asyncio.run(planner_off.execute(now, now))

    assert auto_plan.context['active'] is False
    assert off_plan.context['active'] is False
    assert [item.offer.offer_id for item in auto_plan.planned] == [item.offer.offer_id for item in off_plan.planned]
    assert [item.offer.offer_id for item in auto_plan.reserve] == [item.offer.offer_id for item in off_plan.reserve]
    assert all('sale_event' not in item.decision_json['debug'] for item in auto_plan.planned)
    assert all('sale_event' not in item.decision_json['debug'] for item in off_plan.planned)
