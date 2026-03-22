from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
import re

from dealbot.settings import AppSettings
from domain.entities.decision import Lane
from domain.entities.offer import Offer
from domain.policies.content_lane_policy import ContentLanePolicy
from domain.policies.dedup_policy import DedupPolicy
from domain.policies.decision_policy import DecisionOutcome, DecisionPolicy
from infrastructure.db.repositories import Repositories
from infrastructure.editorial.control_loader import EditorialControlLoader
from infrastructure.observability.metrics import Metrics

from .enrich_offer import EnrichOfferUseCase
from .ingest_source import IngestSourceUseCase


SALE_EVENT_MODE_AUTO = 'auto'
SALE_EVENT_MODE_FORCE = 'force'
SALE_EVENT_MODE_OFF = 'off'
SALE_EVENT_LINKED_SCORE_BONUS = 6.0
SALE_EVENT_EVENT_SLOT_LIMIT = 1
SALE_EVENT_STOPWORDS = {
    'a',
    'all',
    'and',
    'event',
    'fest',
    'festival',
    'for',
    'game',
    'games',
    'here',
    'is',
    'now',
    'of',
    'on',
    'sale',
    'steam',
    'the',
    'through',
    'with',
}


@dataclass(slots=True)
class PlannedCandidate:
    score: float
    offer: Offer
    decision_json: dict


@dataclass(slots=True)
class QueuePlan:
    planned: list[PlannedCandidate]
    reserve: list[PlannedCandidate]
    metrics: dict[str, int]
    context: dict


@dataclass(frozen=True, slots=True)
class SaleEventContext:
    mode: str
    event_offer_ids: frozenset[str]
    phrase_tokens: frozenset[str]
    word_tokens: frozenset[str]


class PlanQueueUseCase:
    RESERVE_BREAKER_FLOOR = 2
    RESERVE_HIGH_VALUE_DISCOUNT_CAP = 8

    def __init__(
        self,
        settings: AppSettings,
        repositories: Repositories,
        ingest_source: IngestSourceUseCase,
        enrich_offer: EnrichOfferUseCase,
        decision_policy: DecisionPolicy,
        dedup_policy: DedupPolicy,
        content_lanes: ContentLanePolicy | None = None,
        control_loader: EditorialControlLoader | None = None,
        metrics: Metrics | None = None,
    ) -> None:
        self.settings = settings
        self.repositories = repositories
        self.ingest_source = ingest_source
        self.enrich_offer = enrich_offer
        self.decision_policy = decision_policy
        self.dedup_policy = dedup_policy
        self.content_lanes = content_lanes or ContentLanePolicy()
        self.control_loader = control_loader
        self.metrics = metrics or Metrics()
        self.logger = logging.getLogger(__name__)

    async def execute(self, now_utc: datetime, now_local: datetime) -> QueuePlan:
        self.metrics = Metrics()
        queue_snapshot_at = datetime.utcnow().replace(microsecond=0)
        editorial_control = self.control_loader.load() if self.control_loader else None
        offers = await self.ingest_source.execute(now_utc)
        ingest_sources = dict(getattr(self.ingest_source, 'last_run_sources', {}) or {})
        self.metrics.inc('offers.ingested_total', len(offers))
        for source_name, snapshot in ingest_sources.items():
            self.metrics.inc(f'offers.ingested.source.{source_name}', int(snapshot.get('offers') or 0))
        offers = await self.enrich_offer.enrich(offers, self.settings.static.steam_enrich_limit)
        self.metrics.inc('offers.enriched_total', len(offers))

        sale_event_mode = self._sale_event_mode()
        sale_event_context = self._build_sale_event_context(offers, now_utc)
        if sale_event_context is not None:
            self.metrics.inc('sale_event.context_active')
            self.metrics.inc('sale_event.active_events', len(sale_event_context.event_offer_ids))

        day_key = now_local.date().isoformat()
        existing_lane_usage = {
            lane.value: self.repositories.get_daily_lane_count(day_key, lane.value)
            for lane in Lane
        }
        game_of_day_already_used = existing_lane_usage.get(Lane.GAME_OF_THE_DAY.value, 0) >= 1

        candidates: list[PlannedCandidate] = []
        for offer in offers:
            game_history = self.repositories.get_game_history(offer.game_id)
            franchise_history = self.repositories.get_franchise_history(offer.franchise_key)
            dedup = self.dedup_policy.evaluate(offer, game_history, franchise_history, now_utc)
            outcome = self.decision_policy.decide(
                offer=offer,
                dedup=dedup,
                now_local=now_local,
                game_of_day_used=game_of_day_already_used,
                editorial_control=editorial_control,
            )
            if not outcome.accepted:
                self._record_rejection_metrics(outcome)
                self.logger.debug('decision_debug=%s', outcome.debug.to_snapshot())
                continue

            sale_event_linked = self._is_sale_event_linked(offer, sale_event_context)
            if sale_event_linked:
                self.metrics.inc('sale_event.linked_candidates')
            score = self._score_offer(outcome, now_utc, sale_event_linked)
            decision_json = self._build_decision_json(score, outcome, game_history)
            self._attach_sale_event_debug(decision_json, offer, sale_event_context, sale_event_linked)
            candidates.append(
                PlannedCandidate(
                    score=score,
                    offer=offer,
                    decision_json=decision_json,
                )
            )
            self.metrics.inc(f'lane.candidate.{outcome.decision.lane.value}')

        planned_pool = [item for item in candidates if item.decision_json['queue_bucket'] == 'planned']
        hero_candidate_count = self._count_hero_discount(planned_pool)
        hero_bonus_slots = self.content_lanes.hero_discount_bonus_slots(
            self.settings.static.planned_queue_size,
            hero_candidate_count,
            len(planned_pool),
        )
        planned_size = self.settings.static.planned_queue_size + hero_bonus_slots
        reserve_size = max(self.settings.static.reserve_queue_size - hero_bonus_slots, 0)

        planned, remaining = self._select_candidates(
            planned_pool,
            planned_size,
            existing_lane_usage.copy(),
            event_slot_limit=SALE_EVENT_EVENT_SLOT_LIMIT if sale_event_context is not None else None,
        )
        planned, remaining = self._protect_hero_discount_slots(
            planned,
            remaining,
            hero_floor=self.content_lanes.hero_discount_solo_floor(
                planned_size,
                hero_candidate_count,
                hero_bonus_slots,
            ),
        )
        reserve_source = remaining + [item for item in candidates if item.decision_json['queue_bucket'] == 'reserve']
        reserve, _ = self._select_candidates(
            reserve_source,
            reserve_size,
            existing_lane_usage.copy(),
            event_slot_limit=None,
        )
        deferred = self._collect_deferred_candidates(candidates, planned, reserve)
        reserve, deferred = self._rebalance_reserve_diversity(reserve, deferred)
        planned = self._apply_selection_outcome(planned, 'planned', 'solo_post')
        reserve = self._apply_selection_outcome(reserve, 'reserve', 'roundup_candidate')

        self.repositories.replace_queue(
            'planned',
            [(item.score, item.offer, item.decision_json) for item in planned],
            created_at=queue_snapshot_at,
        )
        self.repositories.replace_queue(
            'reserve',
            [(item.score, item.offer, item.decision_json) for item in reserve],
            created_at=queue_snapshot_at,
        )
        self.metrics.inc('selection.accepted_total', len(candidates))
        self.metrics.inc('selection.solo_post', len(planned))
        self.metrics.inc('selection.roundup_candidate', len(reserve))
        self.metrics.inc('selection.capacity_hold', len(deferred))
        if hero_bonus_slots:
            self.metrics.inc('selection.hero_discount_bonus_slots', hero_bonus_slots)
        self.metrics.inc('queue.depth.planned', len(planned))
        self.metrics.inc('queue.depth.reserve', len(reserve))
        context = self._sale_event_context_snapshot(sale_event_mode, sale_event_context)
        context['source'] = 'current_queue'
        context['queue_snapshot_at'] = queue_snapshot_at.isoformat()
        context['ingest_sources'] = ingest_sources
        context['selection_summary'] = {
            'solo_post': len(planned),
            'roundup_candidate': len(reserve),
            'capacity_hold': len(deferred),
            'hard_suppress': self.metrics.snapshot().get('selection.hard_suppress', 0),
        }
        self.logger.info('Queue planned=%s reserve=%s deferred=%s hero_bonus=%s metrics=%s', len(planned), len(reserve), len(deferred), hero_bonus_slots, self.metrics.snapshot())
        return QueuePlan(
            planned=planned,
            reserve=reserve,
            metrics=self.metrics.snapshot(),
            context=context,
        )

    def _record_rejection_metrics(self, outcome: DecisionOutcome) -> None:
        self.metrics.inc('selection.hard_suppress')
        if not outcome.quality.accepted:
            self.metrics.inc('quality.reject_total')
            for reason in outcome.quality.reasons:
                self.metrics.inc(f'quality.reject.{reason}')
            return
        if not outcome.dedup.accepted:
            self.metrics.inc(f'dedup.reject.{outcome.dedup.reason}')

    def _build_decision_json(self, score: float, outcome: DecisionOutcome, game_history) -> dict:
        return {
            'lane': outcome.decision.lane.value,
            'template_id': outcome.decision.template_id,
            'must_ship': outcome.decision.must_ship,
            'queue_bucket': outcome.decision.queue_bucket,
            'decision_reasons': list(outcome.decision.reasons),
            'quality_reasons': list(outcome.quality.reasons),
            'dedup_reason': outcome.dedup.reason,
            'is_final_push': outcome.dedup.is_final_push,
            'is_historical_best': outcome.dedup.is_historical_best,
            'price_improved_minor': outcome.dedup.price_improved_minor,
            'score': round(score, 2),
            'previous_price_minor': game_history.price_after_minor if game_history else None,
            'previous_posted_at': game_history.posted_at.isoformat() if game_history else None,
            'best_price_minor': game_history.best_price_minor if game_history else None,
            'manual_force_override': outcome.control.is_forced,
            'selection_outcome': 'accepted_pending_selection',
            'recommended_post_mode': None,
            'debug': outcome.debug.to_snapshot(),
        }

    def _attach_sale_event_debug(
        self,
        decision_json: dict,
        offer: Offer,
        sale_event_context: SaleEventContext | None,
        sale_event_linked: bool,
    ) -> None:
        if sale_event_context is None:
            return
        debug = dict(decision_json.get('debug') or {})
        debug['sale_event'] = {
            'mode': sale_event_context.mode,
            'active': offer.offer_id in sale_event_context.event_offer_ids,
            'linked': sale_event_linked,
        }
        decision_json['debug'] = debug

    def _score_offer(self, outcome: DecisionOutcome, now_utc: datetime, sale_event_linked: bool) -> float:
        offer = outcome.offer
        score = outcome.decision.score
        score += min(offer.discount_percent, 100) * 0.55
        score += min(offer.review_score or 0, 100) * 0.35
        score += min(offer.review_count or 0, 10000) / 800
        score += min(offer.achievements_count or 0, 2000) / 200
        if offer.has_trading_cards:
            score += 4.0
        reasons = set(outcome.decision.reasons)
        if offer.is_freebie:
            if outcome.decision.lane == Lane.BREAKING_FREEBIE:
                score += 14.0
            elif 'freebie_roundup_candidate' in reasons:
                score += 5.0
            else:
                score += 1.5
        if 'hero_discount' in reasons:
            score += 10.0
        elif 'roundup_discount' in reasons:
            score -= 6.0
        if 'freebie_low_signal' in reasons:
            score -= 10.0
        if outcome.dedup.price_improved_minor:
            score += min(outcome.dedup.price_improved_minor / 1000, 25)
        if outcome.dedup.is_historical_best:
            score += 8.0
        if offer.promo_end:
            hours_left = max((offer.promo_end - now_utc).total_seconds() / 3600, 0)
            if hours_left <= 24:
                score += 10.0
            elif hours_left <= 48:
                score += 5.0
        if sale_event_linked:
            score += SALE_EVENT_LINKED_SCORE_BONUS
        return round(score, 2)

    def _planning_value(self, item: PlannedCandidate) -> float:
        return self.content_lanes.planning_priority(item.decision_json['lane']) + item.score

    @staticmethod
    def _is_hero_discount_candidate(item: PlannedCandidate) -> bool:
        return 'hero_discount' in set(item.decision_json.get('decision_reasons') or [])

    def _count_hero_discount(self, items: list[PlannedCandidate]) -> int:
        return sum(1 for item in items if self._is_hero_discount_candidate(item))

    def _protect_hero_discount_slots(
        self,
        selected: list[PlannedCandidate],
        remaining: list[PlannedCandidate],
        *,
        hero_floor: int,
    ) -> tuple[list[PlannedCandidate], list[PlannedCandidate]]:
        if hero_floor <= 0:
            return selected, remaining

        hero_selected = self._count_hero_discount(selected)
        if hero_selected >= hero_floor:
            return selected, remaining

        remaining_heroes = [item for item in remaining if self._is_hero_discount_candidate(item)]
        replaceable = [
            item
            for item in selected
            if not self._is_hero_discount_candidate(item)
            and not item.offer.is_event
            and not bool(item.decision_json.get('must_ship'))
        ]
        remaining_heroes.sort(key=self._planning_value, reverse=True)
        replaceable.sort(key=self._planning_value)

        while hero_selected < hero_floor and remaining_heroes and replaceable:
            incoming = remaining_heroes.pop(0)
            outgoing = replaceable.pop(0)
            selected[selected.index(outgoing)] = incoming
            remaining.remove(incoming)
            remaining.append(outgoing)
            hero_selected += 1

        return selected, remaining

    def _select_candidates(
        self,
        candidates: list[PlannedCandidate],
        size: int,
        lane_usage: dict[str, int],
        event_slot_limit: int | None,
    ) -> tuple[list[PlannedCandidate], list[PlannedCandidate]]:
        remaining = candidates[:]
        selected: list[PlannedCandidate] = []
        last_source = None
        last_genre = None
        last_franchise = None
        event_slots_used = 0

        while remaining and len(selected) < size:
            best_index = None
            best_value = None
            for index, item in enumerate(remaining):
                lane = item.decision_json['lane']
                if self._quota_blocked(item, lane_usage):
                    continue
                if self._event_slot_blocked(item, event_slot_limit, event_slots_used):
                    continue
                primary_genre = self._primary_genre(item.offer)
                if last_source and item.offer.source.value == last_source and self._has_alternative_source(remaining, last_source, lane_usage, event_slot_limit, event_slots_used):
                    continue
                if last_genre and primary_genre and primary_genre == last_genre and self._has_alternative_genre(remaining, last_genre, lane_usage, event_slot_limit, event_slots_used):
                    continue
                if last_franchise and item.offer.franchise_key == last_franchise and self._has_alternative_franchise(remaining, last_franchise, lane_usage, event_slot_limit, event_slots_used):
                    continue
                value = self._planning_value(item)
                if best_value is None or value > best_value:
                    best_value = value
                    best_index = index
            if best_index is None:
                break
            picked = remaining.pop(best_index)
            picked.decision_json['debug'] = self._decorate_debug(picked, last_source, last_genre, last_franchise)
            selected.append(picked)
            lane_usage[picked.decision_json['lane']] = lane_usage.get(picked.decision_json['lane'], 0) + 1
            if event_slot_limit is not None and picked.offer.is_event:
                event_slots_used += self.content_lanes.event_slot_cost(picked.offer.is_event)
            last_source = picked.offer.source.value
            last_genre = self._primary_genre(picked.offer)
            last_franchise = picked.offer.franchise_key

        selected_ids = {item.offer.offer_id for item in selected}
        leftovers = [item for item in remaining if item.offer.offer_id not in selected_ids]
        return selected, leftovers

    def _decorate_debug(
        self,
        item: PlannedCandidate,
        last_source: str | None,
        last_genre: str | None,
        last_franchise: str | None,
    ) -> dict:
        debug = dict(item.decision_json.get('debug') or {})
        constraints: list[str] = []
        primary_genre = self._primary_genre(item.offer)
        if last_source:
            constraints.append('source_alternation' if item.offer.source.value != last_source else 'source_repeat_no_alternative')
        if last_genre and primary_genre:
            constraints.append('genre_alternation' if primary_genre != last_genre else 'genre_repeat_no_alternative')
        if last_franchise:
            constraints.append('franchise_alternation' if item.offer.franchise_key != last_franchise else 'franchise_repeat_no_alternative')
        debug['diversity_constraints'] = constraints
        return debug

    @staticmethod
    def _apply_selection_outcome(
        items: list[PlannedCandidate],
        selection_outcome: str,
        recommended_post_mode: str,
    ) -> list[PlannedCandidate]:
        for item in items:
            item.decision_json['selection_outcome'] = selection_outcome
            item.decision_json['recommended_post_mode'] = recommended_post_mode
            debug = dict(item.decision_json.get('debug') or {})
            debug['selection_outcome'] = selection_outcome
            item.decision_json['debug'] = debug
        return items

    @staticmethod
    def _collect_deferred_candidates(
        candidates: list[PlannedCandidate],
        planned: list[PlannedCandidate],
        reserve: list[PlannedCandidate],
    ) -> list[PlannedCandidate]:
        selected_ids = {item.offer.offer_id for item in planned} | {item.offer.offer_id for item in reserve}
        return [item for item in candidates if item.offer.offer_id not in selected_ids]

    def _rebalance_reserve_diversity(
        self,
        reserve: list[PlannedCandidate],
        deferred: list[PlannedCandidate],
    ) -> tuple[list[PlannedCandidate], list[PlannedCandidate]]:
        if not reserve or not deferred:
            return reserve, deferred

        reserve_pool = list(reserve)
        deferred_pool = list(deferred)

        while self._reserve_breaker_count(reserve_pool) < self.RESERVE_BREAKER_FLOOR:
            outgoing_index = self._lowest_high_value_discount_index(reserve_pool)
            incoming_index = self._best_deferred_diversifier_index(deferred_pool, breakers_only=True)
            if outgoing_index is None or incoming_index is None:
                break
            self._swap_reserve_candidate(reserve_pool, deferred_pool, outgoing_index, incoming_index)

        while self._reserve_high_value_discount_count(reserve_pool) > self.RESERVE_HIGH_VALUE_DISCOUNT_CAP:
            outgoing_index = self._lowest_high_value_discount_index(reserve_pool)
            incoming_index = self._best_deferred_diversifier_index(deferred_pool, breakers_only=False)
            if outgoing_index is None or incoming_index is None:
                break
            self._swap_reserve_candidate(reserve_pool, deferred_pool, outgoing_index, incoming_index)

        return reserve_pool, deferred_pool

    def _swap_reserve_candidate(
        self,
        reserve_pool: list[PlannedCandidate],
        deferred_pool: list[PlannedCandidate],
        outgoing_index: int,
        incoming_index: int,
    ) -> None:
        outgoing = reserve_pool[outgoing_index]
        incoming = deferred_pool.pop(incoming_index)
        reserve_pool[outgoing_index] = incoming
        deferred_pool.append(outgoing)

    def _reserve_breaker_count(self, items: list[PlannedCandidate]) -> int:
        return sum(1 for item in items if self._candidate_content_type(item) in {'freebie', 'event'})

    @staticmethod
    def _reserve_high_value_discount_count(items: list[PlannedCandidate]) -> int:
        return sum(1 for item in items if item.decision_json.get('lane') == Lane.HIGH_VALUE_DISCOUNT.value)

    def _lowest_high_value_discount_index(self, items: list[PlannedCandidate]) -> int | None:
        best_index = None
        best_value = None
        for index, item in enumerate(items):
            if item.decision_json.get('lane') != Lane.HIGH_VALUE_DISCOUNT.value:
                continue
            value = self._planning_value(item)
            if best_value is None or value < best_value:
                best_value = value
                best_index = index
        return best_index

    def _best_deferred_diversifier_index(self, items: list[PlannedCandidate], *, breakers_only: bool) -> int | None:
        best_index = None
        best_key = None
        for index, item in enumerate(items):
            priority = self._diversifier_priority(item, breakers_only=breakers_only)
            if priority is None:
                continue
            key = (priority, self._planning_value(item), -index)
            if best_key is None or key > best_key:
                best_key = key
                best_index = index
        return best_index

    def _diversifier_priority(self, item: PlannedCandidate, *, breakers_only: bool) -> int | None:
        content_type = self._candidate_content_type(item)
        lane = str(item.decision_json.get('lane') or '')
        if content_type in {'freebie', 'event'}:
            return 2
        if breakers_only:
            return None
        if lane != Lane.HIGH_VALUE_DISCOUNT.value:
            return 1
        return None

    @staticmethod
    def _candidate_content_type(item: PlannedCandidate) -> str:
        lane = str(item.decision_json.get('lane') or '')
        if item.offer.is_event or lane == Lane.EVENT_FESTIVAL.value:
            return 'event'
        if item.offer.is_freebie or lane == Lane.BREAKING_FREEBIE.value:
            return 'freebie'
        return 'discount'

    def _has_alternative_source(
        self,
        candidates: list[PlannedCandidate],
        blocked_source: str,
        lane_usage: dict[str, int],
        event_slot_limit: int | None,
        event_slots_used: int,
    ) -> bool:
        return any(
            item.offer.source.value != blocked_source
            and not self._quota_blocked(item, lane_usage)
            and not self._event_slot_blocked(item, event_slot_limit, event_slots_used)
            for item in candidates
        )

    def _has_alternative_genre(
        self,
        candidates: list[PlannedCandidate],
        blocked_genre: str,
        lane_usage: dict[str, int],
        event_slot_limit: int | None,
        event_slots_used: int,
    ) -> bool:
        return any(
            self._primary_genre(item.offer) != blocked_genre
            and not self._quota_blocked(item, lane_usage)
            and not self._event_slot_blocked(item, event_slot_limit, event_slots_used)
            for item in candidates
        )

    def _has_alternative_franchise(
        self,
        candidates: list[PlannedCandidate],
        blocked_franchise: str,
        lane_usage: dict[str, int],
        event_slot_limit: int | None,
        event_slots_used: int,
    ) -> bool:
        return any(
            item.offer.franchise_key != blocked_franchise
            and not self._quota_blocked(item, lane_usage)
            and not self._event_slot_blocked(item, event_slot_limit, event_slots_used)
            for item in candidates
        )

    def _build_sale_event_context(self, offers: list[Offer], now_utc: datetime) -> SaleEventContext | None:
        mode = self._sale_event_mode()
        if mode == SALE_EVENT_MODE_OFF:
            return None

        eligible_events = [offer for offer in offers if offer.is_event and (offer.promo_end is None or offer.promo_end >= now_utc)]
        if not eligible_events:
            return None

        active_events = [offer for offer in eligible_events if offer.promo_start is None or offer.promo_start <= now_utc]
        context_events = active_events
        if mode == SALE_EVENT_MODE_FORCE and not context_events:
            context_events = eligible_events
        if not context_events:
            return None

        phrase_tokens: set[str] = set()
        word_tokens: set[str] = set()
        for offer in context_events:
            for value in self._event_match_sources(offer):
                phrase = self._normalize_phrase(value)
                if phrase:
                    phrase_tokens.add(phrase)
                word_tokens.update(self._word_tokens(value))

        return SaleEventContext(
            mode=mode,
            event_offer_ids=frozenset(offer.offer_id for offer in context_events),
            phrase_tokens=frozenset(phrase_tokens),
            word_tokens=frozenset(word_tokens),
        )

    def _is_sale_event_linked(self, offer: Offer, sale_event_context: SaleEventContext | None) -> bool:
        if sale_event_context is None or offer.is_event:
            return False

        phrase_tokens: set[str] = set()
        for value in self._offer_phrase_sources(offer):
            phrase = self._normalize_phrase(value)
            if phrase:
                phrase_tokens.add(phrase)
        if phrase_tokens & sale_event_context.phrase_tokens:
            return True

        word_tokens: set[str] = set()
        for value in self._offer_word_sources(offer):
            word_tokens.update(self._word_tokens(value))
        return len(word_tokens & sale_event_context.word_tokens) >= 2

    @staticmethod
    def _sale_event_context_snapshot(mode: str, sale_event_context: SaleEventContext | None) -> dict:
        if sale_event_context is None:
            return {'sale_event_mode': mode, 'active': False, 'active_event_offer_ids': []}
        return {
            'sale_event_mode': mode,
            'active': True,
            'active_event_offer_ids': sorted(sale_event_context.event_offer_ids),
            'phrase_tokens': sorted(sale_event_context.phrase_tokens),
            'word_tokens': sorted(sale_event_context.word_tokens),
        }

    def _sale_event_mode(self) -> str:
        mode = (self.settings.operational.sale_event_mode or SALE_EVENT_MODE_AUTO).strip().lower()
        if mode in {SALE_EVENT_MODE_AUTO, SALE_EVENT_MODE_FORCE, SALE_EVENT_MODE_OFF}:
            return mode
        return SALE_EVENT_MODE_AUTO

    @staticmethod
    def _event_match_sources(offer: Offer) -> list[str]:
        return [
            offer.title,
            *offer.tags,
            *offer.genres,
            PlanQueueUseCase._store_slug(offer.store_url),
        ]

    @staticmethod
    def _offer_phrase_sources(offer: Offer) -> list[str]:
        return [
            offer.title,
            *offer.tags,
            *offer.genres,
            PlanQueueUseCase._store_slug(offer.store_url),
        ]

    @staticmethod
    def _offer_word_sources(offer: Offer) -> list[str]:
        return [
            offer.title,
            *offer.tags,
            *offer.genres,
            offer.short_description,
        ]

    @staticmethod
    def _store_slug(store_url: str) -> str:
        if not store_url:
            return ''
        return store_url.rstrip('/').split('/')[-1]

    @staticmethod
    def _normalize_phrase(value: str) -> str:
        return re.sub(r'[^a-z0-9]+', '_', (value or '').strip().lower()).strip('_')

    @staticmethod
    def _word_tokens(value: str) -> set[str]:
        return {
            token
            for token in re.findall(r'[a-z0-9]+', (value or '').lower())
            if len(token) > 2 and token not in SALE_EVENT_STOPWORDS
        }

    def _quota_blocked(self, item: PlannedCandidate, lane_usage: dict[str, int]) -> bool:
        return self.content_lanes.quota_blocked(
            item.decision_json['lane'],
            lane_usage,
            manual_force_override=bool(item.decision_json.get('manual_force_override')),
        )

    def _event_slot_blocked(self, item: PlannedCandidate, event_slot_limit: int | None, event_slots_used: int) -> bool:
        return self.content_lanes.event_slot_blocked(item.offer.is_event, event_slot_limit, event_slots_used)

    @staticmethod
    def _primary_genre(offer: Offer) -> str | None:
        if offer.genres:
            return offer.genres[0].strip().lower()
        if offer.tags:
            return offer.tags[0].strip().lower()
        return None



