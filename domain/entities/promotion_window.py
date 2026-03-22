from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class PromotionWindow:
    start: datetime | None
    end: datetime | None

    def is_active(self, now: datetime) -> bool:
        if self.start and now < self.start:
            return False
        if self.end and now > self.end:
            return False
        return True

    def ends_within(self, now: datetime, delta: timedelta) -> bool:
        return self.end is not None and now <= self.end <= now + delta
