from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass(slots=True)
class Metrics:
    counters: Counter = field(default_factory=Counter)

    def inc(self, key: str, value: int = 1) -> None:
        self.counters[key] += value

    def snapshot(self) -> dict[str, int]:
        return dict(self.counters)
