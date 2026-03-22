from __future__ import annotations

from datetime import datetime
from pathlib import Path

from application.use_cases.plan_queue import PlanQueueUseCase, PlannedCandidate
from dealbot.settings import AppSettings, EditorialConfig, EditorialControlConfig, OperationalConfig, StaticConfig, SteamAccessConfig
from domain.entities.decision import Lane
from domain.entities.offer import OfferKind, OfferSource
from domain.policies.dedup_policy import DedupPolicy
from domain.policies.decision_policy import DecisionPolicy
from domain.policies.editorial_policy import EditorialPolicy
from domain.policies.quality_gate_policy import QualityGatePolicy
from infrastructure.db.repositories import Repositories

from .support import make_test_settings
from .test_caption_builder_arch import make_offer


class StubIngest:
    def __init__(self, offers):
        self.offers = offers

    async def execute(self, now):
        return self.offers


class StubEnrich:
    async def enrich(self, offers, limit):
        return offers


def make_settings(tmp_path: Path) -> AppSettings:
    return make_test_settings(
        tmp_path,
        static=StaticConfig(planned_queue_size=3, reserve_queue_size=3),
        dry_run=True,
    )


def test_plan_queue_builds_planned_and_reserve(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    repositories = Repositories(settings.db_path)
    repositories.initialize()

    first = make_offer()
    first.offer_id = 'steam:1'
    first.game_id = '1'
    first.title = 'Action One'
    first.franchise_key = 'action-one'
    second = make_offer()
    second.offer_id = 'epic:2'
    second.game_id = '2'
    second.source = OfferSource.EPIC
    second.offer_kind = OfferKind.FREEBIE
    second.price_after_minor = 0
    second.discount_percent = 100
    second.title = 'Epic Freebie'
    second.franchise_key = 'epic-freebie'
    second.genres = ['Adventure']
    third = make_offer()
    third.offer_id = 'steam:3'
    third.game_id = '3'
    third.title = 'Strategy Three'
    third.franchise_key = 'strategy-three'
    third.genres = ['Strategy']

    planner = PlanQueueUseCase(
        settings=settings,
        repositories=repositories,
        ingest_source=StubIngest([first, second, third]),
        enrich_offer=StubEnrich(),
        decision_policy=DecisionPolicy(
            quality_gate=QualityGatePolicy(min_review_count=50, publisher_whitelist=set()),
            editorial_policy=EditorialPolicy(min_game_of_the_day_score=65),
        ),
        dedup_policy=DedupPolicy(),
    )

    import asyncio

    plan = asyncio.run(planner.execute(datetime(2026, 3, 10, 12, 0), datetime(2026, 3, 10, 12, 0)))
    assert len(plan.planned) >= 1
    assert len(plan.reserve) >= 1
    assert plan.planned[0].decision_json['lane'] in {'breaking_freebie', 'high_value_discount', 'game_of_the_day'}
    assert plan.planned[0].decision_json['recommended_post_mode'] == 'solo_post'
    assert any(item.decision_json['recommended_post_mode'] == 'roundup_candidate' for item in plan.reserve)
    planned_queue = repositories.list_queue('planned')
    reserve_queue = repositories.list_queue('reserve')
    assert planned_queue
    assert reserve_queue
    assert plan.context['source'] == 'current_queue'
    queue_snapshot_at = datetime.fromisoformat(plan.context['queue_snapshot_at'])
    assert planned_queue[0].created_at == queue_snapshot_at
    assert reserve_queue[0].created_at == queue_snapshot_at


def make_candidate(
    offer_id: str,
    title: str,
    *,
    lane: str,
    score: float,
    offer_kind: OfferKind = OfferKind.DISCOUNT,
    source: OfferSource = OfferSource.STEAM,
) -> PlannedCandidate:
    offer = make_offer()
    source_ref = offer_id.split(':', 1)[-1]
    offer.offer_id = offer_id
    offer.source_ref = source_ref
    offer.game_id = source_ref
    offer.franchise_key = title.lower().replace(' ', '-')
    offer.title = title
    offer.offer_kind = offer_kind
    offer.source = source
    if offer_kind == OfferKind.FREEBIE:
        offer.price_before_minor = 29900
        offer.price_after_minor = 0
        offer.discount_percent = 100
    elif offer_kind in {OfferKind.EVENT, OfferKind.FESTIVAL}:
        offer.price_before_minor = None
        offer.price_after_minor = None
        offer.discount_percent = 0
    decision_json = {
        'lane': lane,
        'template_id': 'festival_event' if lane == Lane.EVENT_FESTIVAL.value else 'steam_discount',
        'must_ship': False,
        'queue_bucket': 'reserve',
        'decision_reasons': [lane],
        'quality_reasons': ['test'],
        'dedup_reason': 'new_offer',
        'score': score,
        'manual_force_override': False,
        'selection_outcome': 'accepted_pending_selection',
        'recommended_post_mode': None,
        'debug': {},
    }
    return PlannedCandidate(score=score, offer=offer, decision_json=decision_json)



def make_planner(tmp_path: Path, *, reserve_size: int = 10) -> PlanQueueUseCase:
    settings = make_test_settings(
        tmp_path,
        static=StaticConfig(planned_queue_size=3, reserve_queue_size=reserve_size),
        dry_run=True,
    )
    repositories = Repositories(settings.db_path)
    repositories.initialize()
    return PlanQueueUseCase(
        settings=settings,
        repositories=repositories,
        ingest_source=StubIngest([]),
        enrich_offer=StubEnrich(),
        decision_policy=DecisionPolicy(
            quality_gate=QualityGatePolicy(min_review_count=50, publisher_whitelist=set()),
            editorial_policy=EditorialPolicy(min_game_of_the_day_score=65),
        ),
        dedup_policy=DedupPolicy(),
    )



def test_plan_queue_reserve_diversification_caps_high_value_discount_and_promotes_breakers(tmp_path: Path) -> None:
    planner = make_planner(tmp_path, reserve_size=10)
    reserve = [
        make_candidate(f'steam:{index}', f'Reserve Discount {index}', lane=Lane.HIGH_VALUE_DISCOUNT.value, score=120.0 - index)
        for index in range(10)
    ]
    deferred = [
        make_candidate('epic:201', 'Deferred Freebie', lane=Lane.BACKLOG_FILLER.value, score=18.0, offer_kind=OfferKind.FREEBIE, source=OfferSource.EPIC),
        make_candidate('event:202', 'Deferred Event', lane=Lane.EVENT_FESTIVAL.value, score=10.0, offer_kind=OfferKind.FESTIVAL, source=OfferSource.EVENT),
        make_candidate('steam:203', 'Deferred Filler', lane=Lane.BACKLOG_FILLER.value, score=40.0),
    ]

    reserve, deferred = planner._rebalance_reserve_diversity(reserve, deferred)
    reserve = planner._apply_selection_outcome(reserve, 'reserve', 'roundup_candidate')

    high_value_count = sum(1 for item in reserve if item.decision_json['lane'] == Lane.HIGH_VALUE_DISCOUNT.value)
    breaker_titles = {item.offer.title for item in reserve if planner._candidate_content_type(item) in {'freebie', 'event'}}

    assert len(reserve) == 10
    assert high_value_count == 8
    assert breaker_titles == {'Deferred Freebie', 'Deferred Event'}
    assert 'Deferred Filler' not in {item.offer.title for item in reserve}
    for item in reserve:
        assert item.decision_json['selection_outcome'] == 'reserve'
        assert item.decision_json['recommended_post_mode'] == 'roundup_candidate'



def test_plan_queue_reserve_diversification_uses_other_non_high_value_lanes_when_breakers_are_exhausted(tmp_path: Path) -> None:
    planner = make_planner(tmp_path, reserve_size=10)
    reserve = [
        make_candidate(f'steam:{index}', f'Reserve Discount {index}', lane=Lane.HIGH_VALUE_DISCOUNT.value, score=110.0 - index)
        for index in range(10)
    ]
    deferred = [
        make_candidate('epic:301', 'Deferred Freebie', lane=Lane.BACKLOG_FILLER.value, score=18.0, offer_kind=OfferKind.FREEBIE, source=OfferSource.EPIC),
        make_candidate('steam:302', 'Deferred Mid Discount', lane=Lane.BACKLOG_FILLER.value, score=55.0),
    ]

    reserve, deferred = planner._rebalance_reserve_diversity(reserve, deferred)

    lanes = [item.decision_json['lane'] for item in reserve]
    titles = {item.offer.title for item in reserve}
    assert lanes.count(Lane.HIGH_VALUE_DISCOUNT.value) == 8
    assert 'Deferred Freebie' in titles
    assert 'Deferred Mid Discount' in titles



def test_plan_queue_reserve_diversification_no_valid_alternatives_leaves_reserve_unchanged(tmp_path: Path) -> None:
    planner = make_planner(tmp_path, reserve_size=10)
    reserve = [
        make_candidate(f'steam:{index}', f'Reserve Discount {index}', lane=Lane.HIGH_VALUE_DISCOUNT.value, score=100.0 - index)
        for index in range(10)
    ]
    deferred = [
        make_candidate('steam:401', 'Deferred Discount One', lane=Lane.HIGH_VALUE_DISCOUNT.value, score=15.0),
        make_candidate('steam:402', 'Deferred Discount Two', lane=Lane.HIGH_VALUE_DISCOUNT.value, score=14.0),
    ]

    rebalanced_reserve, rebalanced_deferred = planner._rebalance_reserve_diversity(list(reserve), list(deferred))

    assert [item.offer.offer_id for item in rebalanced_reserve] == [item.offer.offer_id for item in reserve]
    assert [item.offer.offer_id for item in rebalanced_deferred] == [item.offer.offer_id for item in deferred]

