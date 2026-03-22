from __future__ import annotations

from dataclasses import dataclass

from domain.entities.decision import Lane


@dataclass(frozen=True, slots=True)
class LaneRule:
    planning_priority: float
    publish_priority: float
    daily_cap: int | None = None


DEFAULT_RULE = LaneRule(planning_priority=100.0, publish_priority=100.0)
DEFAULT_LANE_RULES = {
    Lane.BREAKING_FREEBIE: LaneRule(planning_priority=600.0, publish_priority=640.0),
    Lane.EVENT_FESTIVAL: LaneRule(planning_priority=520.0, publish_priority=560.0),
    Lane.GAME_OF_THE_DAY: LaneRule(planning_priority=470.0, publish_priority=520.0, daily_cap=1),
    Lane.FINAL_PUSH: LaneRule(planning_priority=420.0, publish_priority=600.0, daily_cap=1),
    Lane.HIGH_VALUE_DISCOUNT: LaneRule(planning_priority=320.0, publish_priority=340.0),
    Lane.BACKLOG_FILLER: LaneRule(planning_priority=220.0, publish_priority=240.0),
    Lane.ROUNDUP_DIGEST: LaneRule(planning_priority=300.0, publish_priority=360.0),
}


class ContentLanePolicy:
    HERO_DISCOUNT_BONUS_MAX = 2
    HERO_DISCOUNT_TRIGGER_SPAN = 3

    def __init__(self, rules: dict[Lane, LaneRule] | None = None) -> None:
        self.rules = dict(DEFAULT_LANE_RULES)
        if rules:
            self.rules.update(rules)

    def rule_for(self, lane: Lane | str) -> LaneRule:
        if isinstance(lane, Lane):
            return self.rules.get(lane, DEFAULT_RULE)
        for known_lane in Lane:
            if known_lane.value == lane:
                return self.rules.get(known_lane, DEFAULT_RULE)
        return DEFAULT_RULE

    def planning_priority(self, lane: Lane | str) -> float:
        return self.rule_for(lane).planning_priority

    def publish_priority(self, lane: Lane | str) -> float:
        return self.rule_for(lane).publish_priority

    def hero_discount_bonus_slots(
        self,
        base_planned_size: int,
        hero_candidate_count: int,
        planned_candidate_count: int,
    ) -> int:
        if base_planned_size < 3 or hero_candidate_count < 2:
            return 0
        if planned_candidate_count <= base_planned_size:
            return 0
        saturation_threshold = max(3, base_planned_size - 1)
        if hero_candidate_count < saturation_threshold:
            return 0
        bonus = 1
        if hero_candidate_count >= base_planned_size + self.HERO_DISCOUNT_TRIGGER_SPAN:
            bonus += 1
        return min(bonus, self.HERO_DISCOUNT_BONUS_MAX)

    @staticmethod
    def hero_discount_solo_floor(planned_capacity: int, hero_candidate_count: int, hero_bonus_slots: int) -> int:
        if hero_bonus_slots <= 0 or planned_capacity <= 0 or hero_candidate_count <= 0:
            return 0
        return min(hero_candidate_count, max(1, planned_capacity - 1))

    def quota_blocked(
        self,
        lane: Lane | str,
        lane_usage: dict[str, int],
        *,
        manual_force_override: bool = False,
    ) -> bool:
        if manual_force_override:
            return False
        rule = self.rule_for(lane)
        if rule.daily_cap is None:
            return False
        lane_value = lane.value if isinstance(lane, Lane) else lane
        return lane_usage.get(lane_value, 0) >= rule.daily_cap

    @staticmethod
    def event_slot_blocked(offer_is_event: bool, event_slot_limit: int | None, event_slots_used: int) -> bool:
        return bool(event_slot_limit is not None and offer_is_event and event_slots_used >= event_slot_limit)

    @staticmethod
    def event_slot_cost(offer_is_event: bool) -> int:
        return 1 if offer_is_event else 0
