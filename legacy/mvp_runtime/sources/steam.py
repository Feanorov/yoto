from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any

from bs4 import BeautifulSoup
import httpx

from ..models import Offer, OfferSource, PostKind
from ..utils.currency import CurrencyConverter


STEAM_STORE_BASE = "https://store.steampowered.com"
SEARCH_URL = f"{STEAM_STORE_BASE}/search/results/"
APP_DETAILS_URL = f"{STEAM_STORE_BASE}/api/appdetails"
APP_REVIEWS_URL = f"{STEAM_STORE_BASE}/appreviews"


class SteamSource:
    def __init__(self, converter: CurrencyConverter) -> None:
        self.converter = converter

    async def fetch_discount_catalog(self, client: httpx.AsyncClient, limit: int) -> list[Offer]:
        offers: list[Offer] = []
        page_size = 50
        for start in range(0, limit, page_size):
            params = {
                "query": "",
                "start": start,
                "count": page_size,
                "dynamic_data": "",
                "sort_by": "_ASC",
                "force_infinite": 1,
                "specials": 1,
                "maxprice": "",
                "category1": 998,
                "cc": "ua",
                "l": "ukrainian",
                "infinite": 1,
                "ndl": 1,
            }
            response = await client.get(SEARCH_URL, params=params)
            response.raise_for_status()
            payload = response.json()
            page = self._parse_search_results(payload.get("results_html", ""))
            if not page:
                break
            offers.extend(page)
            if len(page) < page_size:
                break
        return offers[:limit]

    def _parse_search_results(self, html: str) -> list[Offer]:
        soup = BeautifulSoup(html or "", "html.parser")
        offers: list[Offer] = []
        for row in soup.select("a.search_result_row"):
            app_id = self._extract_app_id(row.get("data-ds-appid", ""))
            if not app_id:
                continue
            title_node = row.select_one("span.title")
            if title_node is None:
                continue
            title = title_node.get_text(" ", strip=True)
            discount_text = (row.select_one("div.discount_pct") or row.select_one("span.discount_pct"))
            original_node = row.select_one("div.discount_original_price")
            final_node = row.select_one("div.discount_final_price")
            image_node = row.select_one("img")
            discount_pct = self._parse_discount(discount_text.get_text(" ", strip=True) if discount_text else "")
            original_price = self._parse_price(original_node.get_text(" ", strip=True) if original_node else "")
            final_price = self._parse_price(final_node.get_text(" ", strip=True) if final_node else "")
            if final_price is None and original_price is None:
                continue
            is_free_to_keep = final_price == 0 and (original_price or 0) > 0
            if discount_pct <= 0 and not is_free_to_keep:
                continue
            offers.append(
                Offer(
                    source=OfferSource.STEAM,
                    post_kind=PostKind.STEAM_FREE if is_free_to_keep else PostKind.STEAM_DISCOUNT,
                    offer_id=str(app_id),
                    store_item_id=str(app_id),
                    title=title,
                    url=(row.get("href") or f"{STEAM_STORE_BASE}/app/{app_id}/").split("?")[0],
                    image_url=image_node.get("src", "") if image_node else "",
                    discount_pct=discount_pct,
                    original_price_uah=original_price,
                    final_price_uah=final_price,
                    currency="UAH",
                    is_free_to_keep=is_free_to_keep,
                )
            )
        return offers

    @staticmethod
    def _extract_app_id(raw_value: str) -> str | None:
        match = re.search(r"(\d+)", raw_value or "")
        return match.group(1) if match else None

    @staticmethod
    def _parse_discount(value: str) -> int:
        match = re.search(r"-?(\d+)", value or "")
        return int(match.group(1)) if match else 0

    @staticmethod
    def _parse_price(value: str) -> float | None:
        text = (value or "").strip().lower().replace("₴", "").replace("uah", "")
        if not text:
            return None
        if "безкоштов" in text or "free" in text:
            return 0.0
        digits = re.findall(r"\d+", text)
        if not digits:
            return None
        if "," in text and len(digits[-1]) == 2:
            integer = "".join(digits[:-1]) or "0"
            decimal = digits[-1]
            return float(f"{integer}.{decimal}")
        return float("".join(digits))

    @staticmethod
    def _minor_to_price(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return round(float(value) / 100.0, 2)
        except (TypeError, ValueError):
            return None

    async def enrich_offers(self, client: httpx.AsyncClient, raw_offers: list[Offer]) -> list[Offer]:
        enriched: list[Offer] = []
        for offer in raw_offers:
            details = await self._fetch_app_details(client, offer.offer_id)
            if details is None:
                continue
            offer_type = (details.get("type") or "").lower()
            if offer_type not in {"game", "dlc", "video", "demo"}:
                continue
            categories = details.get("categories") or []
            genres = [entry.get("description", "") for entry in details.get("genres") or [] if entry.get("description")]
            screenshots = details.get("screenshots") or []
            screenshot_url = None
            if screenshots:
                screenshot_url = screenshots[0].get("path_full") or screenshots[0].get("path_thumbnail")
            price_overview = details.get("price_overview") or {}
            currency = price_overview.get("currency") or offer.currency
            original_price = self._minor_to_price(price_overview.get("initial"))
            final_price = self._minor_to_price(price_overview.get("final"))
            if final_price is None:
                final_price = offer.final_price_uah
            if original_price is None:
                original_price = offer.original_price_uah
            original_price = await self.converter.convert_to_uah(client, original_price, currency)
            final_price = await self.converter.convert_to_uah(client, final_price, currency)
            sale_end = await self._fetch_sale_end(client, offer.offer_id)
            review_percent, review_summary = await self._fetch_reviews(client, offer.offer_id)
            achievements_count = None
            achievements = details.get("achievements") or {}
            if isinstance(achievements, dict):
                achievements_count = achievements.get("total")
            has_trading_cards = any(
                entry.get("id") == 29 or "card" in (entry.get("description", "").lower()) or "карт" in (entry.get("description", "").lower())
                for entry in categories
            )
            enriched_offer = replace(
                offer,
                title=details.get("name") or offer.title,
                description=details.get("detailed_description") or "",
                short_description=details.get("short_description") or "",
                hero_image_url=details.get("header_image") or details.get("capsule_imagev5") or offer.image_url,
                image_url=details.get("header_image") or offer.image_url,
                screenshot_url=screenshot_url,
                discount_pct=int(price_overview.get("discount_percent", offer.discount_pct) or offer.discount_pct),
                original_price_uah=original_price,
                final_price_uah=final_price,
                currency="UAH",
                sale_end=sale_end,
                review_percent=review_percent,
                review_summary=review_summary,
                achievements_count=achievements_count,
                has_trading_cards=has_trading_cards,
                genres=genres,
                tags=genres[:],
                is_free_to_keep=(final_price == 0 and (original_price or 0) > 0),
                is_dlc=offer_type == "dlc",
                is_app=offer_type == "game",
            )
            enriched.append(enriched_offer)
        return enriched

    async def _fetch_app_details(self, client: httpx.AsyncClient, app_id: str) -> dict[str, Any] | None:
        response = await client.get(APP_DETAILS_URL, params={"appids": app_id, "cc": "ua", "l": "ukrainian"})
        response.raise_for_status()
        payload = response.json()
        wrapper = payload.get(str(app_id)) or {}
        if not wrapper.get("success"):
            return None
        return wrapper.get("data") or None

    async def _fetch_reviews(self, client: httpx.AsyncClient, app_id: str) -> tuple[int | None, str | None]:
        response = await client.get(
            f"{APP_REVIEWS_URL}/{app_id}",
            params={"json": 1, "language": "all", "purchase_type": "all", "num_per_page": 0, "filter": "all"},
        )
        response.raise_for_status()
        payload = response.json()
        summary = payload.get("query_summary") or {}
        total_positive = int(summary.get("total_positive") or 0)
        total_negative = int(summary.get("total_negative") or 0)
        total = total_positive + total_negative
        if total <= 0:
            return None, None
        percent = round((total_positive / total) * 100)
        return percent, self._review_summary_ua(percent)

    def _review_summary_ua(self, percent: int) -> str:
        if percent >= 95:
            return f"Надзвичайно позитивні ({percent}%)"
        if percent >= 80:
            return f"Дуже позитивні ({percent}%)"
        if percent >= 70:
            return f"Позитивні ({percent}%)"
        if percent >= 40:
            return f"Змішані ({percent}%)"
        if percent >= 20:
            return f"Переважно негативні ({percent}%)"
        return f"Негативні ({percent}%)"

    async def _fetch_sale_end(self, client: httpx.AsyncClient, app_id: str) -> datetime | None:
        response = await client.get(f"{STEAM_STORE_BASE}/app/{app_id}/", params={"cc": "ua", "l": "ukrainian"})
        response.raise_for_status()
        html = response.text
        patterns = [
            r'"discount_expiration"\s*:\s*(\d+)',
            r'InitDailyDealTimer\([^,]+,\s*(\d+)\s*\)',
            r'"rtDiscountCountdown"\s*:\s*(\d+)',
            r'data-discount-end="(\d+)"',
        ]
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                timestamp = int(match.group(1))
                if timestamp > 10_000_000_000:
                    timestamp //= 1000
                return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        return None
