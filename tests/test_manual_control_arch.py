from __future__ import annotations

from datetime import datetime

from domain.entities.editorial_control import ControlMatcher, EditorialControl, OverrideRule
from domain.policies.dedup_policy import DedupPolicy
from domain.policies.decision_policy import DecisionPolicy
from domain.policies.editorial_policy import EditorialPolicy
from domain.policies.quality_gate_policy import QualityGatePolicy

from .test_caption_builder_arch import make_offer


def test_quality_gate_rejects_manual_blacklist() -> None:
    offer = make_offer()
    control = EditorialControl(blacklist=ControlMatcher(game_ids=frozenset({offer.game_id})))
    policy = QualityGatePolicy(min_review_count=50, publisher_whitelist=set())
    result = policy.evaluate(offer, control.evaluate_offer(offer))
    assert result.accepted is False
    assert 'manual_blacklist' in result.reasons


def test_quality_gate_allows_manual_whitelist() -> None:
    offer = make_offer()
    offer.review_count = 0
    control = EditorialControl(whitelist=ControlMatcher(publishers=frozenset({'test publisher'})))
    policy = QualityGatePolicy(min_review_count=50, publisher_whitelist=set())
    result = policy.evaluate(offer, control.evaluate_offer(offer))
    assert result.accepted is True
    assert 'manual_control_allow' in result.reasons


def test_decision_policy_applies_force_lane_override() -> None:
    offer = make_offer()
    control = EditorialControl(
        overrides=(
            OverrideRule(
                name='force-final-push',
                matcher=ControlMatcher(game_ids=frozenset({offer.game_id})),
                force_lane='final_push',
                force_priority=33,
            ),
        ),
    )
    policy = DecisionPolicy(
        quality_gate=QualityGatePolicy(min_review_count=50, publisher_whitelist=set()),
        editorial_policy=EditorialPolicy(min_game_of_the_day_score=65),
    )
    dedup = DedupPolicy().evaluate(offer, None, None, datetime(2026, 3, 10, 12, 0))
    outcome = policy.decide(offer, dedup, datetime(2026, 3, 10, 12, 0), game_of_day_used=False, editorial_control=control)
    assert outcome.accepted is True
    assert outcome.decision.lane.value == 'final_push'
    assert outcome.decision.template_id == 'final_push'
    assert outcome.decision.score >= 33