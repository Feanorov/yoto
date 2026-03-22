from __future__ import annotations

from datetime import datetime, timedelta

from domain.entities.offer import AssetBundle, OfferKind, OfferSource
from domain.policies.dedup_policy import DedupPolicy, PublicationRecord
from domain.policies.decision_policy import DecisionPolicy
from domain.policies.editorial_policy import EditorialPolicy
from domain.policies.quality_gate_policy import QualityGatePolicy

from .test_caption_builder_arch import make_offer


def test_quality_gate_rejects_dlc() -> None:
    offer = make_offer()
    offer.is_dlc = True
    policy = QualityGatePolicy(min_review_count=50, publisher_whitelist=set())
    result = policy.evaluate(offer)
    assert result.accepted is False
    assert 'dlc_blocked' in result.reasons



def test_dedup_allows_final_push_even_for_same_price() -> None:
    offer = make_offer()
    now = datetime(2026, 3, 10, 12, 0)
    offer.promo_end = now + timedelta(hours=12)
    offer.discount_percent = 90
    history = PublicationRecord(
        game_id=offer.game_id,
        franchise_key=offer.franchise_key,
        source='steam',
        posted_at=now - timedelta(days=2),
        price_after_minor=offer.price_after_minor,
        discount_percent=offer.discount_percent,
        lane='high_value_discount',
        promo_end=offer.promo_end,
        best_price_minor=offer.price_after_minor,
    )
    policy = DedupPolicy(cooldown_game_days=30, franchise_cooldown_hours=12)
    result = policy.evaluate(offer, history, None, now)
    assert result.accepted is True
    assert result.is_final_push is True



def test_decision_policy_keeps_strong_epic_freebie_as_breaking() -> None:
    offer = make_offer()
    offer.source = OfferSource.EPIC
    offer.offer_kind = OfferKind.FREEBIE
    offer.price_before_minor = 69900
    offer.price_after_minor = 0
    policy = DecisionPolicy(
        quality_gate=QualityGatePolicy(min_review_count=50, publisher_whitelist=set()),
        editorial_policy=EditorialPolicy(min_game_of_the_day_score=65),
    )
    dedup = DedupPolicy().evaluate(offer, None, None, datetime(2026, 3, 10, 12, 0))
    decision = policy.decide(offer, dedup, datetime(2026, 3, 10, 12, 0), game_of_day_used=False)
    assert decision is not None
    assert decision.decision.lane.value == 'breaking_freebie'
    assert decision.decision.template_id == 'epic_free'



def test_decision_policy_demotes_weak_freebie_to_roundup() -> None:
    offer = make_offer()
    offer.offer_kind = OfferKind.FREEBIE
    offer.price_before_minor = 19900
    offer.price_after_minor = 0
    offer.review_score = 42
    offer.review_count = 25
    offer.assets = AssetBundle()
    policy = DecisionPolicy(
        quality_gate=QualityGatePolicy(min_review_count=10, publisher_whitelist=set()),
        editorial_policy=EditorialPolicy(min_game_of_the_day_score=65),
    )
    dedup = DedupPolicy().evaluate(offer, None, None, datetime(2026, 3, 10, 12, 0))
    decision = policy.decide(offer, dedup, datetime(2026, 3, 10, 12, 0), game_of_day_used=False)
    assert decision is not None
    assert decision.decision.lane.value == 'backlog_filler'
    assert decision.decision.queue_bucket == 'reserve'
    assert 'freebie_low_signal' in decision.decision.reasons



def test_editorial_importance_lifts_flagship_discount_over_generic_deal() -> None:
    flagship = make_offer()
    flagship.title = 'Dead Cells'
    flagship.franchise_key = 'dead-cells'
    flagship.review_score = 96
    flagship.review_count = 140000
    flagship.discount_percent = 50
    flagship.price_before_minor = 89900
    flagship.price_after_minor = 44900

    generic = make_offer()
    generic.title = 'Generic Super Sale'
    generic.franchise_key = 'generic-super-sale'
    generic.review_score = 79
    generic.review_count = 3200
    generic.discount_percent = 85
    generic.price_before_minor = 89900
    generic.price_after_minor = 13400

    policy = DecisionPolicy(
        quality_gate=QualityGatePolicy(min_review_count=50, publisher_whitelist=set()),
        editorial_policy=EditorialPolicy(min_game_of_the_day_score=65),
    )
    now = datetime(2026, 3, 10, 12, 0)
    flagship_outcome = policy.decide(flagship, DedupPolicy().evaluate(flagship, None, None, now), now, game_of_day_used=False)
    generic_outcome = policy.decide(generic, DedupPolicy().evaluate(generic, None, None, now), now, game_of_day_used=False)

    assert flagship_outcome.accepted is True
    assert generic_outcome.accepted is True
    assert 'editorial_importance:standout_title' in flagship_outcome.decision.reasons
    assert flagship_outcome.decision.score > generic_outcome.decision.score



def test_decision_policy_marks_secondary_discount_for_roundup() -> None:
    offer = make_offer()
    offer.title = 'Mid Tier Discount'
    offer.franchise_key = 'mid-tier-discount'
    offer.review_score = 82
    offer.review_count = 3200
    offer.discount_percent = 62
    offer.price_before_minor = 79900
    offer.price_after_minor = 30300

    policy = DecisionPolicy(
        quality_gate=QualityGatePolicy(min_review_count=50, publisher_whitelist=set()),
        editorial_policy=EditorialPolicy(min_game_of_the_day_score=65),
    )
    outcome = policy.decide(offer, DedupPolicy().evaluate(offer, None, None, datetime(2026, 3, 10, 12, 0)), datetime(2026, 3, 10, 12, 0), game_of_day_used=False)

    assert outcome.accepted is True
    assert outcome.decision.lane.value == 'high_value_discount'
    assert outcome.decision.queue_bucket == 'reserve'
    assert 'roundup_discount' in outcome.decision.reasons
