from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from application.use_cases.plan_queue import PlanQueueUseCase
from dealbot.settings import StaticConfig
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



def make_settings(tmp_path: Path):
    return make_test_settings(
        tmp_path,
        static=StaticConfig(planned_queue_size=1, reserve_queue_size=1),
        dry_run=True,
    )



def test_plan_queue_separates_capacity_hold_from_hard_suppress(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    repositories = Repositories(settings.db_path)
    repositories.initialize()

    flagship = make_offer()
    flagship.offer_id = 'steam:100'
    flagship.game_id = '100'
    flagship.franchise_key = 'dead-cells'
    flagship.title = 'Dead Cells'
    flagship.review_score = 96
    flagship.review_count = 140000
    flagship.discount_percent = 50
    flagship.price_before_minor = 89900
    flagship.price_after_minor = 44900

    strong = make_offer()
    strong.offer_id = 'steam:101'
    strong.game_id = '101'
    strong.franchise_key = 'strong-deal'
    strong.title = 'Strong Deal'
    strong.review_score = 88
    strong.review_count = 7000
    strong.discount_percent = 80
    strong.price_before_minor = 79900
    strong.price_after_minor = 15900

    roundup = make_offer()
    roundup.offer_id = 'steam:102'
    roundup.game_id = '102'
    roundup.franchise_key = 'roundup-deal'
    roundup.title = 'Roundup Deal'
    roundup.review_score = 82
    roundup.review_count = 3200
    roundup.discount_percent = 62
    roundup.price_before_minor = 69900
    roundup.price_after_minor = 26500

    weak = make_offer()
    weak.offer_id = 'steam:103'
    weak.game_id = '103'
    weak.franchise_key = 'weak-deal'
    weak.title = 'Weak Deal'
    weak.review_score = 65
    weak.review_count = 10
    weak.discount_percent = 85
    weak.price_before_minor = 69900
    weak.price_after_minor = 9900

    planner = PlanQueueUseCase(
        settings=settings,
        repositories=repositories,
        ingest_source=StubIngest([flagship, strong, roundup, weak]),
        enrich_offer=StubEnrich(),
        decision_policy=DecisionPolicy(
            quality_gate=QualityGatePolicy(min_review_count=50, publisher_whitelist=set()),
            editorial_policy=EditorialPolicy(min_game_of_the_day_score=65),
        ),
        dedup_policy=DedupPolicy(),
    )

    plan = asyncio.run(planner.execute(datetime(2026, 3, 10, 12, 0), datetime(2026, 3, 10, 12, 0)))

    assert plan.context['selection_summary'] == {
        'solo_post': 1,
        'roundup_candidate': 1,
        'capacity_hold': 1,
        'hard_suppress': 1,
    }
    assert plan.metrics['selection.solo_post'] == 1
    assert plan.metrics['selection.roundup_candidate'] == 1
    assert plan.metrics['selection.capacity_hold'] == 1
    assert plan.metrics['selection.hard_suppress'] == 1
    assert plan.planned[0].decision_json['recommended_post_mode'] == 'solo_post'
    assert plan.reserve[0].decision_json['recommended_post_mode'] == 'roundup_candidate'
