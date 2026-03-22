from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from domain.entities.offer import Offer

from .content_lane_policy import ContentLanePolicy


@dataclass(frozen=True, slots=True)
class PublishPriority:
    lane: str
    bucket: str
    total: float
    lane_priority: float
    decision_score: float
    must_ship_bonus: float
    reserve_penalty: float
    urgency_bonus: float
    lane_repeat_penalty: float
    manual_override_bonus: float

    def to_snapshot(self) -> dict[str, Any]:
        return {
            'lane': self.lane,
            'bucket': self.bucket,
            'total': self.total,
            'lane_priority': self.lane_priority,
            'decision_score': self.decision_score,
            'must_ship_bonus': self.must_ship_bonus,
            'reserve_penalty': self.reserve_penalty,
            'urgency_bonus': self.urgency_bonus,
            'lane_repeat_penalty': self.lane_repeat_penalty,
            'manual_override_bonus': self.manual_override_bonus,
        }


class PublishPriorityEngine:
    MUST_SHIP_BONUS = 45.0
    MANUAL_OVERRIDE_BONUS = 18.0
    RESERVE_PENALTY = 30.0
    REPEAT_LANE_PENALTY = 24.0

    def __init__(self, lane_policy: ContentLanePolicy | None = None) -> None:
        self.lane_policy = lane_policy or ContentLanePolicy()

    def evaluate(
        self,
        *,
        offer: Offer,
        lane: str,
        bucket: str,
        decision_score: float,
        must_ship: bool,
        manual_force_override: bool,
        lane_published_today: int,
        now_utc: datetime,
    ) -> PublishPriority:
        lane_priority = self.lane_policy.publish_priority(lane)
        must_ship_bonus = self.MUST_SHIP_BONUS if must_ship else 0.0
        reserve_penalty = self.RESERVE_PENALTY if bucket == 'reserve' and not must_ship else 0.0
        urgency_bonus = self._urgency_bonus(offer, now_utc)
        lane_repeat_penalty = 0.0 if must_ship else lane_published_today * self.REPEAT_LANE_PENALTY
        manual_override_bonus = self.MANUAL_OVERRIDE_BONUS if manual_force_override else 0.0
        total = (
            lane_priority
            + float(decision_score or 0.0)
            + must_ship_bonus
            + urgency_bonus
            + manual_override_bonus
            - reserve_penalty
            - lane_repeat_penalty
        )
        return PublishPriority(
            lane=lane,
            bucket=bucket,
            total=round(total, 2),
            lane_priority=lane_priority,
            decision_score=float(decision_score or 0.0),
            must_ship_bonus=must_ship_bonus,
            reserve_penalty=reserve_penalty,
            urgency_bonus=urgency_bonus,
            lane_repeat_penalty=lane_repeat_penalty,
            manual_override_bonus=manual_override_bonus,
        )

    @staticmethod
    def _urgency_bonus(offer: Offer, now_utc: datetime) -> float:
        if offer.promo_end is None:
            return 0.0
        hours_left = max((offer.promo_end - now_utc).total_seconds() / 3600, 0.0)
        if hours_left <= 6:
            return 26.0
        if hours_left <= 12:
            return 18.0
        if hours_left <= 24:
            return 12.0
        if hours_left <= 48:
            return 6.0
        if hours_left <= 72:
            return 2.0
        return 0.0
