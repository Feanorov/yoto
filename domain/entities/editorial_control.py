from __future__ import annotations

from dataclasses import dataclass, field

from domain.entities.offer import Offer


@dataclass(frozen=True, slots=True)
class ControlMatcher:
    game_ids: frozenset[str] = field(default_factory=frozenset)
    franchise_keys: frozenset[str] = field(default_factory=frozenset)
    publishers: frozenset[str] = field(default_factory=frozenset)
    developers: frozenset[str] = field(default_factory=frozenset)
    tags: frozenset[str] = field(default_factory=frozenset)
    offer_kinds: frozenset[str] = field(default_factory=frozenset)

    def match(self, offer: Offer) -> tuple[str, ...]:
        reasons: list[str] = []
        if offer.game_id and offer.game_id in self.game_ids:
            reasons.append(f'game_id:{offer.game_id}')
        if offer.franchise_key and offer.franchise_key in self.franchise_keys:
            reasons.append(f'franchise_key:{offer.franchise_key}')
        publisher = (offer.publisher_name or '').strip().lower()
        if publisher and publisher in self.publishers:
            reasons.append(f'publisher:{publisher}')
        developer = (offer.developer_name or '').strip().lower()
        if developer and developer in self.developers:
            reasons.append(f'developer:{developer}')
        normalized_tags = {item.strip().lower() for item in list(offer.tags) + list(offer.genres) if item and item.strip()}
        reasons.extend(f'tag:{tag}' for tag in sorted(normalized_tags.intersection(self.tags)))
        if offer.offer_kind.value in self.offer_kinds:
            reasons.append(f'offer_kind:{offer.offer_kind.value}')
        return tuple(reasons)


@dataclass(frozen=True, slots=True)
class OverrideRule:
    name: str
    matcher: ControlMatcher = field(default_factory=ControlMatcher)
    force_lane: str | None = None
    force_priority: float = 0.0
    force_skip: bool = False
    force_game_of_day: bool = False

    def match(self, offer: Offer) -> tuple[str, ...]:
        return self.matcher.match(offer)


@dataclass(frozen=True, slots=True)
class ControlImpact:
    blacklist_reasons: tuple[str, ...] = field(default_factory=tuple)
    whitelist_reasons: tuple[str, ...] = field(default_factory=tuple)
    override_names: tuple[str, ...] = field(default_factory=tuple)
    override_reasons: tuple[str, ...] = field(default_factory=tuple)
    force_lane: str | None = None
    force_priority: float = 0.0
    force_skip: bool = False
    force_game_of_day: bool = False
    priority_boost: float = 0.0

    @property
    def manual_reasons(self) -> tuple[str, ...]:
        reasons = list(self.blacklist_reasons) + list(self.whitelist_reasons) + list(self.override_reasons)
        reasons.extend(f'override:{name}' for name in self.override_names)
        return tuple(reasons)

    @property
    def has_manual_allowance(self) -> bool:
        return bool(self.whitelist_reasons or self.override_names or self.force_lane or self.force_game_of_day or self.force_priority)

    @property
    def is_forced(self) -> bool:
        return self.force_skip or self.force_game_of_day or self.force_lane is not None


@dataclass(frozen=True, slots=True)
class EditorialControl:
    blacklist: ControlMatcher = field(default_factory=ControlMatcher)
    whitelist: ControlMatcher = field(default_factory=ControlMatcher)
    overrides: tuple[OverrideRule, ...] = field(default_factory=tuple)
    whitelist_priority_boost: float = 20.0

    def evaluate_offer(self, offer: Offer) -> ControlImpact:
        blacklist_reasons = self.blacklist.match(offer)
        whitelist_reasons = self.whitelist.match(offer)
        override_names: list[str] = []
        override_reasons: list[str] = []
        force_lane = None
        force_priority = 0.0
        force_skip = False
        force_game_of_day = False

        for rule in self.overrides:
            reasons = rule.match(offer)
            if not reasons:
                continue
            override_names.append(rule.name)
            override_reasons.extend(reasons)
            if force_lane is None and rule.force_lane:
                force_lane = rule.force_lane
            force_priority += float(rule.force_priority or 0.0)
            force_skip = force_skip or bool(rule.force_skip)
            force_game_of_day = force_game_of_day or bool(rule.force_game_of_day)

        return ControlImpact(
            blacklist_reasons=blacklist_reasons,
            whitelist_reasons=whitelist_reasons,
            override_names=tuple(override_names),
            override_reasons=tuple(override_reasons),
            force_lane=force_lane,
            force_priority=force_priority,
            force_skip=force_skip,
            force_game_of_day=force_game_of_day,
            priority_boost=self.whitelist_priority_boost if whitelist_reasons else 0.0,
        )