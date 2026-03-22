from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Lane(str, Enum):
    BREAKING_FREEBIE = "breaking_freebie"
    EVENT_FESTIVAL = "event_festival"
    GAME_OF_THE_DAY = "game_of_the_day"
    HIGH_VALUE_DISCOUNT = "high_value_discount"
    FINAL_PUSH = "final_push"
    BACKLOG_FILLER = "backlog_filler"
    ROUNDUP_DIGEST = "roundup_digest"


@dataclass(frozen=True, slots=True)
class Decision:
    lane: Lane
    score: float
    must_ship: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)
    queue_bucket: str = "planned"
    template_id: str = "steam_discount"
