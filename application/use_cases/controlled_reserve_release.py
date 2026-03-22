from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from infrastructure.db.repositories import QueueRecord


@dataclass(slots=True)
class ReleaseDecision:
    visible_reserve_candidates: list[QueueRecord]
    visible_roundup_candidate: QueueRecord | None
    reason: str
    released_content_type: str | None = None


class ControlledReserveRelease:
    DISCOUNT_STREAK_TRIGGER = 4
    NON_DISCOUNT_LOOKBACK = 4
    RELEASE_PRIORITY = ('roundup', 'freebie', 'event')

    def release(
        self,
        *,
        planned_candidates: list[QueueRecord],
        reserve_candidates: list[QueueRecord],
        roundup_candidate: QueueRecord | None,
        recent_stream: list[dict[str, Any]],
    ) -> ReleaseDecision:
        visible_reserve: list[QueueRecord] = []
        protected_by_type: dict[str, list[QueueRecord]] = {content_type: [] for content_type in self.RELEASE_PRIORITY}

        for record in reserve_candidates:
            content_type = self._candidate_type(record)
            if content_type in protected_by_type:
                protected_by_type[content_type].append(record)
            else:
                visible_reserve.append(record)

        if roundup_candidate is not None:
            protected_by_type['roundup'].append(roundup_candidate)

        if not any(protected_by_type.values()):
            return ReleaseDecision(
                visible_reserve_candidates=visible_reserve,
                visible_roundup_candidate=None,
                reason='no_protected_breakers',
            )

        release_reason = self._release_reason(planned_candidates, recent_stream)
        if release_reason is None:
            return ReleaseDecision(
                visible_reserve_candidates=visible_reserve,
                visible_roundup_candidate=None,
                reason='held_healthy',
            )

        released_type, released_record = self._choose_breaker(protected_by_type)
        if released_record is None:
            return ReleaseDecision(
                visible_reserve_candidates=visible_reserve,
                visible_roundup_candidate=None,
                reason=release_reason,
            )

        if released_type == 'roundup':
            return ReleaseDecision(
                visible_reserve_candidates=visible_reserve,
                visible_roundup_candidate=released_record,
                reason=release_reason,
                released_content_type=released_type,
            )

        visible_reserve.append(released_record)
        return ReleaseDecision(
            visible_reserve_candidates=visible_reserve,
            visible_roundup_candidate=None,
            reason=release_reason,
            released_content_type=released_type,
        )

    def _release_reason(
        self,
        planned_candidates: list[QueueRecord],
        recent_stream: list[dict[str, Any]],
    ) -> str | None:
        if not planned_candidates:
            return 'planned_candidates_empty'

        leading_discount_streak = self._leading_content_type_streak(recent_stream, 'discount')
        if leading_discount_streak >= self.DISCOUNT_STREAK_TRIGGER:
            return 'leading_discount_streak'

        recent_window = list(recent_stream[: self.NON_DISCOUNT_LOOKBACK])
        if len(recent_window) == self.NON_DISCOUNT_LOOKBACK and not any(
            self._content_type_from_stream_entry(item) != 'discount' for item in recent_window
        ):
            return 'no_non_discount_last_four'

        return None

    def _choose_breaker(self, protected_by_type: dict[str, list[QueueRecord]]) -> tuple[str | None, QueueRecord | None]:
        for content_type in self.RELEASE_PRIORITY:
            candidates = protected_by_type.get(content_type) or []
            if not candidates:
                continue
            return content_type, max(candidates, key=self._breaker_sort_key)
        return None, None

    @staticmethod
    def _breaker_sort_key(record: QueueRecord) -> tuple[float, float, int]:
        decision_score = float(record.decision_json.get('score') or record.score or 0.0)
        return (decision_score, float(record.score or 0.0), -int(record.row_id))

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
    def _candidate_type(record: QueueRecord) -> str:
        declared = str(record.decision_json.get('content_type') or '').strip().lower()
        if declared in {'roundup', 'freebie', 'event', 'discount'}:
            return declared
        lane = str(record.decision_json.get('lane') or record.lane).strip().lower()
        if lane == 'roundup_digest' or str(record.offer.offer_id).startswith('roundup:'):
            return 'roundup'
        if getattr(record.offer, 'is_event', False) or lane == 'event_festival':
            return 'event'
        if getattr(record.offer, 'is_freebie', False) or lane == 'breaking_freebie':
            return 'freebie'
        return 'discount'

    @staticmethod
    def _content_type_from_stream_entry(entry: dict[str, Any]) -> str:
        content_type = str(entry.get('content_type') or '').strip().lower()
        if content_type in {'roundup', 'freebie', 'event', 'discount'}:
            return content_type
        lane = str(entry.get('lane') or '').strip().lower()
        offer_kind = str(entry.get('offer_kind') or '').strip().lower()
        if lane == 'roundup_digest' or content_type == 'roundup':
            return 'roundup'
        if offer_kind in {'festival', 'event'} or lane == 'event_festival':
            return 'event'
        if offer_kind == 'freebie' or lane == 'breaking_freebie':
            return 'freebie'
        return 'discount'
