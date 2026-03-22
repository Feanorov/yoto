from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from infrastructure.db.repositories import QueueRecord


@dataclass(slots=True)
class EditorialAdjustment:
    content_type: str
    total_delta: float = 0.0
    reasons: tuple[str, ...] = field(default_factory=tuple)
    rule_deltas: dict[str, float] = field(default_factory=dict)

    def to_snapshot(self, *, base_total: float | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            'content_type': self.content_type,
            'total_delta': round(float(self.total_delta or 0.0), 2),
            'reasons': list(self.reasons),
            'rule_deltas': {key: round(float(value), 2) for key, value in self.rule_deltas.items()},
        }
        if base_total is not None:
            payload['base_total'] = round(float(base_total), 2)
            payload['final_total'] = round(float(base_total) + float(self.total_delta or 0.0), 2)
        return payload


class EditorialStreamController:
    RECENT_WINDOW = 6
    NO_FOUR_SAME_TYPE_PENALTY = 100.0
    EVENT_GAP_BONUS = 32.0
    FREEBIE_BONUS_WHEN_FILLER_PRESENT = 18.0
    FILLER_DISCOUNT_PENALTY_WHEN_FREEBIE_PRESENT = 18.0
    SAME_LANE_REPEAT_PENALTY = 18.0
    LONG_DISCOUNT_STREAK_STEP = 30.0
    DISCOUNT_RUN_BREAKER_MIN_STREAK = 4
    ROUNDUP_RUN_BREAKER_BONUS = 140.0
    FREEBIE_RUN_BREAKER_BONUS = 120.0
    EVENT_RUN_BREAKER_BONUS = 90.0

    def score_candidate(
        self,
        record: QueueRecord,
        candidates: Iterable[QueueRecord],
        recent_stream: list[dict[str, Any]],
    ) -> EditorialAdjustment:
        candidate_pool = list(candidates)
        current_type = self._content_type(record)
        recent_window = list(recent_stream[: self.RECENT_WINDOW])
        rule_deltas: dict[str, float] = {}
        leading_type_streak = self._leading_content_type_streak(recent_window, current_type)
        leading_discount_streak = self._leading_content_type_streak(recent_window, 'discount')

        if leading_type_streak >= 3:
            rule_deltas['same_content_type_streak_penalty'] = -self.NO_FOUR_SAME_TYPE_PENALTY

        if current_type == 'discount' and leading_type_streak >= 4:
            rule_deltas['long_discount_streak_penalty'] = -(
                (leading_type_streak - 3) * self.LONG_DISCOUNT_STREAK_STEP
            )

        if leading_discount_streak >= self.DISCOUNT_RUN_BREAKER_MIN_STREAK:
            if current_type == 'roundup':
                rule_deltas['discount_run_breaker_bonus'] = self.ROUNDUP_RUN_BREAKER_BONUS
            elif current_type == 'freebie':
                rule_deltas['discount_run_breaker_bonus'] = self.FREEBIE_RUN_BREAKER_BONUS
            elif current_type == 'event':
                rule_deltas['discount_run_breaker_bonus'] = self.EVENT_RUN_BREAKER_BONUS

        if current_type == 'event' and recent_window and not any(self._content_type_from_stream_entry(item) == 'event' for item in recent_window):
            rule_deltas['event_gap_bonus'] = self.EVENT_GAP_BONUS

        has_freebie_candidate = any(self._content_type(candidate) == 'freebie' for candidate in candidate_pool)
        has_filler_discount_candidate = any(self._is_filler_discount(candidate) for candidate in candidate_pool)
        if current_type == 'freebie' and has_filler_discount_candidate:
            rule_deltas['freebie_over_filler_bonus'] = self.FREEBIE_BONUS_WHEN_FILLER_PRESENT
        if self._is_filler_discount(record) and has_freebie_candidate:
            rule_deltas['filler_discount_penalty'] = -self.FILLER_DISCOUNT_PENALTY_WHEN_FREEBIE_PRESENT

        lane = str(record.decision_json.get('lane') or record.lane)
        same_lane_count = sum(1 for item in recent_window if str(item.get('lane') or '') == lane)
        if same_lane_count > 0:
            rule_deltas['same_lane_repeat_penalty'] = -(same_lane_count * self.SAME_LANE_REPEAT_PENALTY)

        total_delta = round(sum(rule_deltas.values()), 2)
        return EditorialAdjustment(
            content_type=current_type,
            total_delta=total_delta,
            reasons=tuple(rule_deltas.keys()),
            rule_deltas={key: round(value, 2) for key, value in rule_deltas.items()},
        )

    def _leading_content_type_streak(
        self,
        recent_stream: list[dict[str, Any]],
        content_type: str,
    ) -> int:
        streak = 0
        for item in recent_stream:
            if self._content_type_from_stream_entry(item) != content_type:
                break
            streak += 1
        return streak

    @staticmethod
    def _content_type(record: QueueRecord) -> str:
        declared = str(record.decision_json.get('content_type') or '').strip().lower()
        if declared in {'event', 'freebie', 'discount', 'roundup'}:
            return declared
        lane = str(record.decision_json.get('lane') or record.lane)
        if record.offer.is_event or lane == 'event_festival':
            return 'event'
        if record.offer.is_freebie or lane == 'breaking_freebie':
            return 'freebie'
        return 'discount'

    def _is_filler_discount(self, record: QueueRecord) -> bool:
        lane = str(record.decision_json.get('lane') or record.lane)
        return lane == 'backlog_filler' and self._content_type(record) == 'discount'

    @staticmethod
    def _content_type_from_stream_entry(entry: dict[str, Any]) -> str:
        content_type = str(entry.get('content_type') or '').strip().lower()
        if content_type in {'event', 'freebie', 'discount', 'roundup'}:
            return content_type
        lane = str(entry.get('lane') or '').strip().lower()
        offer_kind = str(entry.get('offer_kind') or '').strip().lower()
        if offer_kind in {'festival', 'event'} or lane == 'event_festival':
            return 'event'
        if offer_kind == 'freebie' or lane == 'breaking_freebie':
            return 'freebie'
        return 'discount'
