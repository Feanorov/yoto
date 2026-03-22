from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import logging
import random
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from .config import Settings
from .db import Database
from .models import Offer, OfferHistory, OfferSource, PostKind
from .publisher import TelegramPublisher
from .render.cards import CardRenderer
from .sources.calendar_events import CalendarEventSource
from .sources.epic import EpicSource
from .sources.steam import SteamSource
from .texts import build_caption
from .utils.ua import format_price_uah


LOGGER = logging.getLogger(__name__)


def get_timezone(name: str):
    for candidate in (name, name.replace("Kiev", "Kyiv"), "Europe/Kyiv", "UTC"):
        try:
            return ZoneInfo(candidate)
        except ZoneInfoNotFoundError:
            continue
    return timezone.utc


def normalize_dt(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class DealCoordinator:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        steam_source: SteamSource,
        epic_source: EpicSource,
        event_source: CalendarEventSource,
        renderer: CardRenderer,
        publisher: TelegramPublisher,
        client: httpx.AsyncClient,
    ) -> None:
        self.settings = settings
        self.db = db
        self.steam_source = steam_source
        self.epic_source = epic_source
        self.event_source = event_source
        self.renderer = renderer
        self.publisher = publisher
        self.client = client
        self.tz = get_timezone(settings.timezone)

    async def run_forever(self) -> None:
        while True:
            await self.publish_next()
            sleep_minutes = random.randint(self.settings.min_interval_minutes, self.settings.max_interval_minutes)
            LOGGER.info("Sleeping for %s minutes before the next publication cycle.", sleep_minutes)
            await self._sleep_minutes(sleep_minutes)

    async def _sleep_minutes(self, minutes: int) -> None:
        import asyncio

        await asyncio.sleep(minutes * 60)

    async def publish_next(self) -> Offer | None:
        now = datetime.utcnow()
        await self.refresh_queue(now, force=False)
        queue_item = self.db.pop_next_queue_item()
        if queue_item is None:
            LOGGER.warning("Queue is empty, nothing to publish.")
            return None
        offer = queue_item.offer
        card_path = await self.renderer.render(self.client, offer)
        caption = build_caption(offer)
        message = await self.publisher.send_post(card_path, caption)
        final_day_alert_sent = "final_day_priority" in offer.priority_flags
        self.db.record_post(offer, message.message_id if message else None, note=offer.improvement_note, final_day_alert_sent=final_day_alert_sent)
        if offer.post_kind == PostKind.GAME_OF_DAY:
            self.db.mark_daily_post(self._day_key(now), PostKind.GAME_OF_DAY, offer)
        LOGGER.info("Published %s (%s).", offer.title, offer.post_kind.value)
        return offer

    async def send_test_post(self) -> Offer | None:
        now = datetime.utcnow()
        await self.refresh_queue(now, force=True)
        return await self.publish_next()

    async def refresh_queue(self, now: datetime, force: bool = False) -> list[tuple[float, Offer]]:
        existing = self.db.list_queue()
        if existing and len(existing) >= self.settings.queue_target_size and not force:
            return [(item.score, item.offer) for item in existing]

        events = self.event_source.fetch_due_events(now)
        epic_offers = await self.epic_source.fetch_current_freebies(self.client)
        raw_steam = await self.steam_source.fetch_discount_catalog(self.client, self.settings.steam_scan_limit)
        raw_steam.sort(key=self.seed_score, reverse=True)
        steam_offers = await self.steam_source.enrich_offers(self.client, raw_steam[: self.settings.steam_enrich_limit])

        ranked: list[tuple[float, Offer]] = []
        for offer in events + epic_offers + steam_offers:
            prepared = self.prepare_offer_for_publication(offer, now)
            if prepared is None:
                continue
            ranked.append((self.score_offer(prepared, now), prepared))

        ranked.sort(key=lambda item: item[0], reverse=True)
        selected = self._pick_diverse_queue(ranked, now)
        self.db.save_queue(selected)
        return selected

    def prepare_offer_for_publication(self, offer: Offer, now: datetime) -> Offer | None:
        history = self.db.get_history(offer.source, offer.offer_id)
        if offer.source == OfferSource.STEAM:
            if offer.is_dlc or not offer.is_app:
                return None
            if offer.review_percent is None and not offer.is_free_to_keep:
                return None
            return evaluate_offer_against_history(offer, history, now)
        if offer.source == OfferSource.EPIC:
            if history and normalize_dt(history.last_sale_end) == normalize_dt(offer.sale_end):
                return None
            return offer
        if offer.source == OfferSource.EVENT:
            if history and history.last_posted_at and (now - normalize_dt(history.last_posted_at)) < timedelta(days=7):
                return None
            return offer
        return offer

    def score_offer(self, offer: Offer, now: datetime) -> float:
        score = 0.0
        if offer.source == OfferSource.EVENT:
            score += 110
        if offer.post_kind == PostKind.GAME_OF_DAY:
            score += 105
        if offer.source == OfferSource.EPIC:
            score += 90
        if offer.is_free_to_keep:
            score += 70
        score += min(offer.discount_pct, 100) * 1.4
        if offer.review_percent is not None:
            score += max(offer.review_percent - 50, 0) * 0.7
        if offer.has_trading_cards:
            score += 5
        if offer.achievements_count:
            score += min(offer.achievements_count / 150, 8)
        sale_end = normalize_dt(offer.sale_end)
        if sale_end is not None:
            hours_left = (sale_end - now).total_seconds() / 3600
            if 0 <= hours_left <= 24:
                score += 45
            elif 24 < hours_left <= 48:
                score += 25
            elif 48 < hours_left <= 96:
                score += 10
        if offer.improvement_note:
            score += 22
        if "final_day_priority" in offer.priority_flags:
            score += 30
        return score

    def seed_score(self, offer: Offer) -> float:
        score = offer.discount_pct * 1.2
        if offer.is_free_to_keep:
            score += 70
        if offer.final_price_uah is not None:
            score += max(0, 200 - offer.final_price_uah) / 20
        return score

    def _pick_diverse_queue(self, ranked: list[tuple[float, Offer]], now: datetime) -> list[tuple[float, Offer]]:
        selected: list[tuple[float, Offer]] = []
        used_ids: set[tuple[str, str]] = set()
        source_limits = {OfferSource.EVENT: 1, OfferSource.EPIC: 1, OfferSource.STEAM: self.settings.queue_target_size}
        source_counts = {OfferSource.EVENT: 0, OfferSource.EPIC: 0, OfferSource.STEAM: 0}
        day_key = self._day_key(now)

        if not self.db.was_daily_posted(day_key, PostKind.GAME_OF_DAY):
            freebies = [(score, offer) for score, offer in ranked if offer.source == OfferSource.STEAM and offer.is_free_to_keep and (offer.review_percent or 0) >= self.settings.min_free_review_percent]
            if freebies:
                score, offer = freebies[0]
                game_of_day = replace(offer, post_kind=PostKind.GAME_OF_DAY)
                selected.append((score + 12, game_of_day))
                used_ids.add((game_of_day.source.value, game_of_day.offer_id))
                source_counts[OfferSource.STEAM] += 1

        for source in (OfferSource.EVENT, OfferSource.EPIC):
            for score, offer in ranked:
                key = (offer.source.value, offer.offer_id)
                if key in used_ids or offer.source != source or source_counts[source] >= source_limits[source]:
                    continue
                selected.append((score, offer))
                used_ids.add(key)
                source_counts[source] += 1
                break

        for score, offer in ranked:
            key = (offer.source.value, offer.offer_id)
            if key in used_ids:
                continue
            if source_counts[offer.source] >= source_limits[offer.source]:
                continue
            selected.append((score, offer))
            used_ids.add(key)
            source_counts[offer.source] += 1
            if len(selected) >= self.settings.queue_target_size:
                break

        if len(selected) < self.settings.queue_target_size:
            for score, offer in ranked:
                key = (offer.source.value, offer.offer_id)
                if key in used_ids:
                    continue
                selected.append((score, offer))
                used_ids.add(key)
                if len(selected) >= self.settings.queue_target_size:
                    break

        return selected[: self.settings.queue_target_size]

    def _day_key(self, now: datetime) -> str:
        return now.astimezone(self.tz).date().isoformat()


def evaluate_offer_against_history(offer: Offer, history: OfferHistory | None, now: datetime) -> Offer | None:
    sale_end = normalize_dt(offer.sale_end)
    if history is None:
        if sale_end and sale_end <= now:
            return None
        if sale_end and sale_end <= now + timedelta(days=2):
            offer.priority_flags.append("ending_soon")
        return offer

    last_posted = normalize_dt(history.last_posted_at)
    better_discount = offer.discount_pct > (history.last_discount_pct or 0)
    current_final = offer.final_price_uah if offer.final_price_uah is not None else 10**9
    previous_final = history.last_final_price_uah if history.last_final_price_uah is not None else 10**9
    better_price = current_final < previous_final - 0.009
    same_discount = offer.discount_pct == (history.last_discount_pct or 0)
    same_price = abs(current_final - previous_final) < 0.009

    if same_discount and same_price:
        if sale_end and sale_end <= now + timedelta(days=1) and offer.discount_pct >= 80 and not history.final_day_alert_sent:
            offer.priority_flags.append("final_day_priority")
            return offer
        return None

    if sale_end and sale_end <= now + timedelta(days=2):
        offer.priority_flags.append("ending_soon")

    if better_discount or better_price:
        previous_date = normalize_dt(history.last_posted_at)
        offer.previous_price_uah = history.last_final_price_uah
        offer.previous_price_date = previous_date
        if previous_date and history.last_final_price_uah is not None and offer.final_price_uah is not None:
            offer.improvement_note = (
                f"Ціна стала кращою, ніж {previous_date.day}.{previous_date.month:02d}.{previous_date.year}: "
                f"було {format_price_uah(history.last_final_price_uah)}, зараз {format_price_uah(offer.final_price_uah)}."
            )
        return offer

    if last_posted and now - last_posted < timedelta(days=7):
        return None

    if sale_end and sale_end <= now + timedelta(days=1) and offer.discount_pct >= 80 and not history.final_day_alert_sent:
        offer.priority_flags.append("final_day_priority")
        return offer

    return offer
