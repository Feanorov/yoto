from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from domain.entities.offer import Offer


@dataclass(frozen=True, slots=True)
class PublicationRecord:
    game_id: str
    franchise_key: str
    source: str
    posted_at: datetime
    price_after_minor: int | None
    discount_percent: int
    lane: str
    promo_end: datetime | None
    best_price_minor: int | None = None


@dataclass(frozen=True, slots=True)
class DedupDecision:
    accepted: bool
    reason: str
    is_final_push: bool = False
    is_historical_best: bool = False
    price_improved_minor: int = 0


@dataclass(slots=True)
class DedupPolicy:
    cooldown_game_days: int = 30
    franchise_cooldown_hours: int = 36
    min_price_drop_minor: int = 1000
    min_discount_delta: int = 10

    def evaluate(
        self,
        offer: Offer,
        game_history: PublicationRecord | None,
        franchise_history: PublicationRecord | None,
        now: datetime,
    ) -> DedupDecision:
        if franchise_history and franchise_history.franchise_key == offer.franchise_key:
            if now - franchise_history.posted_at < timedelta(hours=self.franchise_cooldown_hours):
                return DedupDecision(False, 'franchise_cooldown')

        if game_history is None:
            return DedupDecision(True, 'new_offer')

        old_price = game_history.price_after_minor or 0
        new_price = offer.price_after_minor or 0
        best_known_price = game_history.best_price_minor if game_history.best_price_minor is not None else game_history.price_after_minor
        price_drop = max(old_price - new_price, 0)
        discount_delta = offer.discount_percent - game_history.discount_percent
        within_game_cooldown = now - game_history.posted_at < timedelta(days=self.cooldown_game_days)
        final_push = bool(
            offer.promo_end
            and offer.discount_percent >= 80
            and timedelta() <= (offer.promo_end - now) <= timedelta(days=1)
        )

        if price_drop >= self.min_price_drop_minor:
            return DedupDecision(True, 'price_improved', price_improved_minor=price_drop)

        if discount_delta >= self.min_discount_delta:
            return DedupDecision(True, 'discount_improved')

        if best_known_price is not None and new_price and new_price < best_known_price:
            return DedupDecision(True, 'historical_best_price', is_historical_best=True, price_improved_minor=max(best_known_price - new_price, 0))

        if final_push:
            return DedupDecision(True, 'final_push', is_final_push=True)

        same_price = old_price == new_price
        same_discount = game_history.discount_percent == offer.discount_percent
        if same_price and same_discount and within_game_cooldown:
            return DedupDecision(False, 'duplicate_within_game_cooldown')

        return DedupDecision(False, 'not_meaningfully_improved')