from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from application.use_cases.plan_queue import PlanQueueUseCase
from dealbot.settings import StaticConfig
from domain.policies.content_lane_policy import ContentLanePolicy
from domain.policies.dedup_policy import DedupPolicy
from domain.policies.decision_policy import DecisionPolicy
from domain.policies.editorial_policy import EditorialPolicy
from domain.policies.quality_gate_policy import QualityGatePolicy
from infrastructure.db.repositories import Repositories

from .support import make_test_settings
from .test_caption_builder_arch import make_offer
from .test_iteration3_ingestion_arch import make_event_offer


class StubIngest:
    def __init__(self, offers):
        self.offers = offers

    async def execute(self, now):
        return self.offers


class StubEnrich:
    async def enrich(self, offers, limit):
        return offers


HERO_FIXTURES = [
    ('steam:201', 'Slay the Spire', 'slay-the-spire', 'Card Battler'),
    ('steam:202', 'Hearts of Iron IV', 'hearts-of-iron-iv', 'Strategy'),
    ('steam:203', 'Crusader Kings III', 'crusader-kings-iii', 'Grand Strategy'),
    ('steam:204', 'Dead Space', 'dead-space', 'Shooter'),
    ('steam:205', 'Grand Theft Auto V', 'grand-theft-auto-v', 'Open World'),
]


def make_settings(tmp_path: Path):
    return make_test_settings(
        tmp_path,
        static=StaticConfig(planned_queue_size=4, reserve_queue_size=4),
        dry_run=True,
    )


def make_hero_offer(offer_id: str, title: str, franchise_key: str, genre: str):
    offer = make_offer()
    offer.offer_id = offer_id
    offer.source_ref = offer_id.split(':', 1)[-1]
    offer.game_id = offer.source_ref
    offer.franchise_key = franchise_key
    offer.title = title
    offer.genres = [genre]
    offer.tags = [genre]
    offer.review_score = 95
    offer.review_count = 120000
    offer.discount_percent = 50
    offer.price_before_minor = 89900
    offer.price_after_minor = 44900
    return offer


def make_strong_offer() -> object:
    offer = make_offer()
    offer.offer_id = 'steam:299'
    offer.source_ref = '299'
    offer.game_id = '299'
    offer.franchise_key = 'strong-secondary'
    offer.title = 'Strong Secondary Deal'
    offer.genres = ['Action']
    offer.tags = ['Action']
    offer.review_score = 88
    offer.review_count = 7000
    offer.discount_percent = 80
    offer.price_before_minor = 79900
    offer.price_after_minor = 15900
    return offer


def test_content_lane_policy_adds_hero_bonus_slots_only_under_real_pressure() -> None:
    policy = ContentLanePolicy()

    assert policy.hero_discount_bonus_slots(6, 4, 6) == 0
    assert policy.hero_discount_bonus_slots(6, 5, 7) == 1
    assert policy.hero_discount_bonus_slots(6, 9, 12) == 2
    assert policy.hero_discount_bonus_slots(1, 1, 2) == 0


def test_plan_queue_promotes_overflow_hero_discount_into_solo_slots(tmp_path: Path) -> None:
    now = datetime(2026, 3, 10, 12, 0)
    settings = make_settings(tmp_path)
    repositories = Repositories(settings.db_path)
    repositories.initialize()

    event = make_event_offer(
        'event:hero-fest',
        'Steam Hero Festival',
        'https://store.steampowered.com/sale/hero-fest',
        now,
    )
    heroes = [make_hero_offer(*fixture) for fixture in HERO_FIXTURES]
    strong = make_strong_offer()

    planner = PlanQueueUseCase(
        settings=settings,
        repositories=repositories,
        ingest_source=StubIngest([event, *heroes, strong]),
        enrich_offer=StubEnrich(),
        decision_policy=DecisionPolicy(
            quality_gate=QualityGatePolicy(min_review_count=50, publisher_whitelist=set()),
            editorial_policy=EditorialPolicy(min_game_of_the_day_score=65),
        ),
        dedup_policy=DedupPolicy(),
    )

    plan = asyncio.run(planner.execute(now, now))

    hero_solo = [item for item in plan.planned if 'hero_discount' in item.decision_json['decision_reasons']]
    hero_roundup = [item for item in plan.reserve if 'hero_discount' in item.decision_json['decision_reasons']]

    assert len(plan.planned) == 5
    assert any(item.offer.is_event for item in plan.planned)
    assert len(hero_solo) == 4
    assert len(hero_roundup) == 1
    assert plan.metrics['selection.hero_discount_bonus_slots'] == 1
    assert any('strong_discount' in item.decision_json['decision_reasons'] for item in plan.reserve)
