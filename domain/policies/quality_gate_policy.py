from __future__ import annotations

from dataclasses import dataclass, field

from domain.entities.editorial_control import ControlImpact
from domain.entities.offer import Offer


@dataclass(frozen=True, slots=True)
class QualityGateResult:
    accepted: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class QualityGatePolicy:
    min_review_count: int
    publisher_whitelist: set[str]

    def evaluate(self, offer: Offer, control_impact: ControlImpact | None = None) -> QualityGateResult:
        impact = control_impact or ControlImpact()
        if impact.force_skip:
            return QualityGateResult(False, ('manual_force_skip',) + impact.manual_reasons)
        if impact.blacklist_reasons:
            return QualityGateResult(False, ('manual_blacklist',) + impact.blacklist_reasons)

        reasons: list[str] = []
        if offer.adult_flag:
            reasons.append('adult_content')
        if offer.is_dlc:
            reasons.append('dlc_blocked')
        if offer.is_soundtrack:
            reasons.append('soundtrack_blocked')
        if offer.is_demo:
            reasons.append('demo_blocked')
        if reasons:
            return QualityGateResult(False, tuple(reasons))

        if offer.is_freebie or offer.is_event:
            return QualityGateResult(True, ('event_or_freebie',) + impact.manual_reasons)

        publisher = (offer.publisher_name or '').strip().lower()
        if publisher and publisher in self.publisher_whitelist:
            return QualityGateResult(True, ('publisher_whitelist',) + impact.manual_reasons)

        if impact.has_manual_allowance:
            return QualityGateResult(True, ('manual_control_allow',) + impact.manual_reasons)

        if (offer.review_count or 0) >= self.min_review_count:
            return QualityGateResult(True, ('review_threshold',))

        return QualityGateResult(False, ('review_threshold_not_met',))