from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from domain.entities.decision import Decision, Lane
from domain.entities.decision_debug_artifact import DecisionDebugArtifact
from domain.entities.editorial_control import ControlImpact, EditorialControl
from domain.entities.offer import Offer
from domain.policies.dedup_policy import DedupDecision
from domain.policies.editorial_policy import EditorialPolicy
from domain.policies.quality_gate_policy import QualityGatePolicy, QualityGateResult


@dataclass(frozen=True, slots=True)
class DecisionOutcome:
    offer: Offer
    quality: QualityGateResult
    dedup: DedupDecision
    control: ControlImpact
    decision: Decision | None
    debug: DecisionDebugArtifact
    accepted: bool


@dataclass(slots=True)
class DecisionPolicy:
    quality_gate: QualityGatePolicy
    editorial_policy: EditorialPolicy

    def decide(
        self,
        offer: Offer,
        dedup: DedupDecision,
        now_local: datetime,
        game_of_day_used: bool,
        editorial_control: EditorialControl | None = None,
    ) -> DecisionOutcome:
        control = editorial_control.evaluate_offer(offer) if editorial_control else ControlImpact()
        quality = self.quality_gate.evaluate(offer, control)
        source_state = str(offer.metadata.get('source_state') or 'healthy')
        if not quality.accepted:
            debug = DecisionDebugArtifact(
                offer_id=offer.offer_id,
                quality_gate_passed=False,
                quality_reasons=quality.reasons,
                dedup_passed=dedup.accepted,
                dedup_reason=dedup.reason,
                cooldown_triggered='cooldown' in dedup.reason,
                manual_control_reasons=control.manual_reasons,
                source_state=source_state,
            )
            return DecisionOutcome(offer, quality, dedup, control, None, debug, False)

        if not dedup.accepted:
            debug = DecisionDebugArtifact(
                offer_id=offer.offer_id,
                quality_gate_passed=True,
                quality_reasons=quality.reasons,
                dedup_passed=False,
                dedup_reason=dedup.reason,
                cooldown_triggered='cooldown' in dedup.reason,
                manual_control_reasons=control.manual_reasons,
                source_state=source_state,
            )
            return DecisionOutcome(offer, quality, dedup, control, None, debug, False)

        decision = self.editorial_policy.classify_lane(offer, dedup, now_local, game_of_day_used)
        decision = self._apply_manual_control(decision, control)
        if not self.editorial_policy.allow_during_quiet_hours(decision, now_local):
            decision = Decision(
                lane=decision.lane,
                score=decision.score,
                must_ship=decision.must_ship,
                reasons=decision.reasons + ('quiet_hours_reserve',),
                queue_bucket='reserve',
                template_id=decision.template_id,
            )

        debug = DecisionDebugArtifact(
            offer_id=offer.offer_id,
            quality_gate_passed=True,
            quality_reasons=quality.reasons,
            dedup_passed=True,
            dedup_reason=dedup.reason,
            lane_selection_reason=decision.reasons,
            cooldown_triggered='cooldown' in dedup.reason,
            template_selected=decision.template_id,
            manual_control_reasons=control.manual_reasons,
            source_state=source_state,
        )
        return DecisionOutcome(offer, quality, dedup, control, decision, debug, True)

    def _apply_manual_control(self, decision: Decision, control: ControlImpact) -> Decision:
        lane = decision.lane
        template_id = decision.template_id
        reasons = list(decision.reasons)

        if control.force_game_of_day:
            lane = Lane.GAME_OF_THE_DAY
            template_id = 'game_of_the_day'
            reasons.append('manual_force_game_of_day')
        elif control.force_lane:
            forced_lane = self._parse_lane(control.force_lane)
            if forced_lane is not None:
                lane = forced_lane
                template_id = self._template_for_lane(forced_lane)
                reasons.append(f'manual_force_lane:{forced_lane.value}')

        score = decision.score + control.priority_boost + control.force_priority
        if control.priority_boost:
            reasons.append('manual_whitelist_priority_boost')
        if control.force_priority:
            reasons.append('manual_force_priority')

        return Decision(
            lane=lane,
            score=score,
            must_ship=decision.must_ship or control.is_forced,
            reasons=tuple(reasons),
            queue_bucket=decision.queue_bucket,
            template_id=template_id,
        )

    @staticmethod
    def _parse_lane(value: str) -> Lane | None:
        normalized = (value or '').strip().lower()
        for lane in Lane:
            if lane.value == normalized:
                return lane
        return None

    @staticmethod
    def _template_for_lane(lane: Lane) -> str:
        return {
            Lane.BREAKING_FREEBIE: 'epic_free',
            Lane.EVENT_FESTIVAL: 'festival_event',
            Lane.GAME_OF_THE_DAY: 'game_of_the_day',
            Lane.FINAL_PUSH: 'final_push',
            Lane.HIGH_VALUE_DISCOUNT: 'steam_discount',
            Lane.BACKLOG_FILLER: 'steam_discount',
        }.get(lane, 'steam_discount')