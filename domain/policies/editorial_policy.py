from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
import re

from domain.entities.decision import Decision, Lane
from domain.entities.offer import Offer
from domain.policies.dedup_policy import DedupDecision


FREEBIE_TEMPLATES = {
    'epic': 'epic_free',
    'steam': 'steam_free',
}
STANDOUT_TITLE_MARKERS = (
    'dead cells',
    'slay the spire',
    'grand theft auto',
    'gta v',
    'red dead redemption',
    'hades',
    'hollow knight',
    'baldur s gate',
    'elden ring',
    'stardew valley',
    'terraria',
    'crusader kings iii',
    'hearts of iron iv',
    'disco elysium',
)
MAJOR_FRANCHISE_MARKERS = (
    'assassin s creed',
    'tom clancy',
    'far cry',
    'dead space',
    'resident evil',
    'monster hunter',
    'persona',
    'final fantasy',
    'nba 2k',
    'warhammer 40 000',
)


@dataclass(slots=True)
class EditorialPolicy:
    game_of_the_day_quota: int = 1
    final_push_quota: int = 1
    discounts_quota_min: int = 2
    discounts_quota_max: int = 4
    quiet_hours_start: time = time(0, 0)
    quiet_hours_end: time = time(8, 30)
    min_game_of_the_day_score: int = 65

    def classify_lane(self, offer: Offer, dedup: DedupDecision, now_local: datetime, game_of_day_used: bool) -> Decision:
        importance_score, importance_reasons = self._editorial_importance(offer)
        if offer.is_event:
            return Decision(
                Lane.EVENT_FESTIVAL,
                120.0 + importance_score * 0.25,
                True,
                ('event_festival', *importance_reasons),
                template_id='festival_event',
            )
        if offer.is_freebie:
            return self._classify_freebie(offer, importance_score, importance_reasons, game_of_day_used)
        if dedup.is_final_push:
            return Decision(
                Lane.FINAL_PUSH,
                102.0 + self._discount_momentum(offer, dedup) + importance_score * 0.35,
                True,
                ('final_push', *importance_reasons),
                template_id='final_push',
            )
        return self._classify_discount(offer, dedup, importance_score, importance_reasons)

    def allow_during_quiet_hours(self, decision: Decision, now_local: datetime) -> bool:
        is_quiet = self.quiet_hours_start <= now_local.time() <= self.quiet_hours_end
        if not is_quiet:
            return True
        return decision.must_ship or decision.lane in {Lane.BREAKING_FREEBIE, Lane.EVENT_FESTIVAL, Lane.FINAL_PUSH}

    def _classify_freebie(
        self,
        offer: Offer,
        importance_score: float,
        importance_reasons: tuple[str, ...],
        game_of_day_used: bool,
    ) -> Decision:
        template_id = FREEBIE_TEMPLATES.get(offer.source.value, 'steam_free')
        signal, signal_reasons = self._freebie_signal(offer, importance_score)
        reasons = tuple(dict.fromkeys((*signal_reasons, *importance_reasons)))
        breaking_threshold = 18.0 if offer.source.value == 'epic' else 22.0
        if signal >= breaking_threshold:
            return Decision(
                Lane.BREAKING_FREEBIE,
                104.0 + signal + importance_score * 0.4,
                True,
                ('breaking_freebie', 'freebie_high_signal', *reasons),
                template_id=template_id,
            )
        if not game_of_day_used and signal >= 16.0 and importance_score >= 16.0:
            return Decision(
                Lane.GAME_OF_THE_DAY,
                98.0 + signal + importance_score * 0.35,
                False,
                ('game_of_the_day_candidate', 'freebie_editorial_pick', *reasons),
                template_id='game_of_the_day',
            )
        if signal >= 12.0:
            return Decision(
                Lane.BACKLOG_FILLER,
                78.0 + signal + importance_score * 0.25,
                False,
                ('freebie_roundup_candidate', *reasons),
                queue_bucket='reserve',
                template_id=template_id,
            )
        return Decision(
            Lane.BACKLOG_FILLER,
            58.0 + signal + importance_score * 0.2,
            False,
            ('freebie_low_signal', *reasons),
            queue_bucket='reserve',
            template_id=template_id,
        )

    def _classify_discount(
        self,
        offer: Offer,
        dedup: DedupDecision,
        importance_score: float,
        importance_reasons: tuple[str, ...],
    ) -> Decision:
        momentum = self._discount_momentum(offer, dedup)
        reasons = importance_reasons
        if self._is_hero_discount(offer, importance_score):
            return Decision(
                Lane.HIGH_VALUE_DISCOUNT,
                112.0 + momentum + importance_score,
                False,
                ('high_value_discount', 'hero_discount', *reasons),
                queue_bucket='planned',
                template_id='steam_discount',
            )
        if self._is_strong_discount(offer, importance_score, dedup):
            return Decision(
                Lane.HIGH_VALUE_DISCOUNT,
                92.0 + momentum + importance_score * 0.75,
                False,
                ('high_value_discount', 'strong_discount', *reasons),
                queue_bucket='planned',
                template_id='steam_discount',
            )
        if self._is_roundup_discount(offer, importance_score):
            return Decision(
                Lane.HIGH_VALUE_DISCOUNT,
                72.0 + momentum + importance_score * 0.55,
                False,
                ('high_value_discount', 'roundup_discount', *reasons),
                queue_bucket='reserve',
                template_id='steam_discount',
            )
        return Decision(
            Lane.BACKLOG_FILLER,
            58.0 + momentum + importance_score * 0.35,
            False,
            ('backlog_filler', 'mid_discount', *reasons),
            queue_bucket='reserve',
            template_id='steam_discount',
        )

    @staticmethod
    def _discount_momentum(offer: Offer, dedup: DedupDecision) -> float:
        score = 0.0
        if offer.discount_percent >= 90:
            score += 18.0
        elif offer.discount_percent >= 80:
            score += 14.0
        elif offer.discount_percent >= 70:
            score += 10.0
        elif offer.discount_percent >= 60:
            score += 6.0
        elif offer.discount_percent >= 50:
            score += 3.0
        if dedup.is_historical_best:
            score += 6.0
        if dedup.price_improved_minor >= 3000:
            score += 5.0
        elif dedup.price_improved_minor >= 1000:
            score += 3.0
        if offer.price_after_minor is not None and offer.price_after_minor <= 49900:
            score += 4.0
        elif offer.price_after_minor is not None and offer.price_after_minor <= 99900:
            score += 2.0
        return score

    def _freebie_signal(self, offer: Offer, importance_score: float) -> tuple[float, tuple[str, ...]]:
        signal = 0.0
        reasons: list[str] = []
        if offer.source.value == 'epic':
            signal += 10.0
            reasons.append('freebie_source:epic')
        if self._ends_soon(offer):
            signal += 6.0
            reasons.append('freebie_ends_soon')
        review_count = offer.review_count or 0
        review_score = offer.review_score or 0
        if review_count >= 20000:
            signal += 10.0
            reasons.append('freebie_popular')
        elif review_count >= 5000:
            signal += 7.0
            reasons.append('freebie_known')
        elif review_count >= 1000:
            signal += 4.0
            reasons.append('freebie_some_audience')
        if review_score >= 90:
            signal += 8.0
            reasons.append('freebie_well_reviewed')
        elif review_score >= 80:
            signal += 5.0
            reasons.append('freebie_positive_reviews')
        elif review_score >= 70:
            signal += 2.0
            reasons.append('freebie_mixed_positive')
        if (offer.price_before_minor or 0) >= 69900:
            signal += 5.0
            reasons.append('freebie_high_list_price')
        elif (offer.price_before_minor or 0) >= 29900:
            signal += 3.0
            reasons.append('freebie_meaningful_value')
        if offer.primary_asset_url and offer.confidence_levels.asset_confidence >= 0.6:
            signal += 3.0
            reasons.append('freebie_card_ready')
        if importance_score >= 28.0:
            signal += 6.0
            reasons.append('freebie_editorial_importance_high')
        elif importance_score >= 14.0:
            signal += 3.0
            reasons.append('freebie_editorial_importance')
        return signal, tuple(dict.fromkeys(reasons))

    def _editorial_importance(self, offer: Offer) -> tuple[float, tuple[str, ...]]:
        score = 0.0
        reasons: list[str] = []
        review_count = offer.review_count or 0
        review_score = offer.review_score or 0
        if review_count >= 100000:
            score += 28.0
            reasons.append('editorial_importance:mega_popular')
        elif review_count >= 50000:
            score += 20.0
            reasons.append('editorial_importance:very_popular')
        elif review_count >= 20000:
            score += 12.0
            reasons.append('editorial_importance:popular')
        elif review_count >= 5000 and review_score >= 85:
            score += 6.0
            reasons.append('editorial_importance:trusted_hit')
        if review_score >= 95 and review_count >= 5000:
            score += 12.0
            reasons.append('editorial_importance:critical_favorite')
        elif review_score >= 90 and review_count >= 2000:
            score += 6.0
            reasons.append('editorial_importance:highly_rated')

        normalized_sources = {
            self._normalize_text(offer.title),
            self._normalize_text(offer.franchise_key.replace('-', ' ')),
            self._normalize_text(offer.short_description),
        }
        flattened = ' '.join(part for part in normalized_sources if part)
        if any(marker in flattened for marker in STANDOUT_TITLE_MARKERS):
            score += 18.0
            reasons.append('editorial_importance:standout_title')
        elif any(marker in flattened for marker in MAJOR_FRANCHISE_MARKERS):
            score += 10.0
            reasons.append('editorial_importance:major_franchise')

        if offer.primary_asset_url and offer.confidence_levels.asset_confidence >= 0.6:
            score += 3.0
            reasons.append('editorial_importance:card_ready')
        return score, tuple(dict.fromkeys(reasons))

    @staticmethod
    def _is_hero_discount(offer: Offer, importance_score: float) -> bool:
        review_count = offer.review_count or 0
        review_score = offer.review_score or 0
        return bool(
            (offer.discount_percent >= 85 and importance_score >= 12.0)
            or importance_score >= 28.0
            or (review_score >= 90 and review_count >= 10000 and offer.discount_percent >= 50)
        )

    @staticmethod
    def _is_strong_discount(offer: Offer, importance_score: float, dedup: DedupDecision) -> bool:
        review_count = offer.review_count or 0
        review_score = offer.review_score or 0
        return bool(
            offer.discount_percent >= 75
            or (importance_score >= 18.0 and offer.discount_percent >= 50)
            or (review_score >= 85 and review_count >= 5000 and offer.discount_percent >= 45)
            or (dedup.is_historical_best and importance_score >= 12.0 and offer.discount_percent >= 45)
        )

    @staticmethod
    def _is_roundup_discount(offer: Offer, importance_score: float) -> bool:
        review_count = offer.review_count or 0
        review_score = offer.review_score or 0
        return bool(
            offer.discount_percent >= 60
            or (importance_score >= 12.0 and offer.discount_percent >= 40)
            or (review_score >= 80 and review_count >= 1500 and offer.discount_percent >= 40)
        )

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r'[^a-z0-9]+', ' ', (value or '').lower()).strip()

    @staticmethod
    def _ends_soon(offer: Offer) -> bool:
        return bool(offer.promo_end and timedelta() <= (offer.promo_end - datetime.utcnow()) <= timedelta(days=2))
