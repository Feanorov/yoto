from __future__ import annotations

from domain.entities.offer import Offer
from domain.policies.quality_gate_policy import QualityGatePolicy, QualityGateResult


class EvaluateQualityUseCase:
    def __init__(self, policy: QualityGatePolicy) -> None:
        self.policy = policy

    def execute(self, offer: Offer) -> QualityGateResult:
        return self.policy.evaluate(offer)
