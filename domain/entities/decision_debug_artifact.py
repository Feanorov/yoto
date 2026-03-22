from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DecisionDebugArtifact:
    offer_id: str
    quality_gate_passed: bool
    quality_reasons: tuple[str, ...] = field(default_factory=tuple)
    dedup_passed: bool = False
    dedup_reason: str = ''
    lane_selection_reason: tuple[str, ...] = field(default_factory=tuple)
    diversity_constraints: tuple[str, ...] = field(default_factory=tuple)
    cooldown_triggered: bool = False
    template_selected: str = ''
    manual_control_reasons: tuple[str, ...] = field(default_factory=tuple)
    source_state: str = 'healthy'
    render_warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_snapshot(self) -> dict[str, Any]:
        return {
            'offer_id': self.offer_id,
            'quality_gate_passed': self.quality_gate_passed,
            'quality_reasons': list(self.quality_reasons),
            'dedup_passed': self.dedup_passed,
            'dedup_reason': self.dedup_reason,
            'lane_selection_reason': list(self.lane_selection_reason),
            'diversity_constraints': list(self.diversity_constraints),
            'cooldown_triggered': self.cooldown_triggered,
            'template_selected': self.template_selected,
            'manual_control_reasons': list(self.manual_control_reasons),
            'source_state': self.source_state,
            'render_warnings': list(self.render_warnings),
        }