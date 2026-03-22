from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any

import httpx

from ..models import Offer, OfferSource, PostKind
from ..utils.currency import CurrencyConverter
from ..utils.ua import contains_cyrillic


EPIC_FREE_GAMES_URL = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"


class EpicSource:
    def __init__(self, converter: CurrencyConverter) -> None:
        self.converter = converter

    async def fetch_current_freebies(self, client: httpx.AsyncClient) -> list[Offer]:
        response = await client.get(
            EPIC_FREE_GAMES_URL,
            params={"locale": "uk-UA", "country": "UA", "allowCountries": "UA"},
        )
        response.raise_for_status()
        payload = response.json()
        elements = (((payload.get("data") or {}).get("Catalog") or {}).get("searchStore") or {}).get("elements") or []
        offers: list[Offer] = []
        now = datetime.utcnow()
        for element in elements:
            current = self._pick_current_promotion(element, now)
            if current is None:
                continue
            original_price, currency = self._extract_original_price(element)
            original_price = await self.converter.convert_to_uah(client, original_price, currency)
            slug = self._resolve_slug(element)
            if not slug:
                continue
            image_url = self._pick_image(element)
            description = element.get("description") or ""
            if not contains_cyrillic(description):
                description = "Роздача в Epic Games Store. Гру можна додати до бібліотеки безкоштовно, поки акція активна."
            offer = Offer(
                source=OfferSource.EPIC,
                post_kind=PostKind.EPIC_FREE,
                offer_id=element.get("id") or slug,
                store_item_id=element.get("id") or slug,
                title=element.get("title") or slug,
                url=f"https://store.epicgames.com/uk/p/{slug}",
                image_url=image_url,
                hero_image_url=image_url,
                screenshot_url=image_url,
                description=description,
                short_description=description,
                discount_pct=100,
                original_price_uah=original_price,
                final_price_uah=0.0,
                currency="UAH",
                sale_end=datetime.fromisoformat(current["endDate"].replace("Z", "+00:00")),
                is_free_to_keep=True,
                genres=self._extract_categories(element),
                tags=self._extract_categories(element),
            )
            offers.append(replace(offer))
        return offers

    def _pick_current_promotion(self, element: dict[str, Any], now: datetime) -> dict[str, Any] | None:
        promotions = (element.get("promotions") or {}).get("promotionalOffers") or []
        for block in promotions:
            for offer in block.get("promotionalOffers") or []:
                start = datetime.fromisoformat(offer["startDate"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(offer["endDate"].replace("Z", "+00:00"))
                if start.replace(tzinfo=None) <= now <= end.replace(tzinfo=None):
                    return offer
        return None

    def _resolve_slug(self, element: dict[str, Any]) -> str | None:
        catalog_ns = element.get("catalogNs") or {}
        mappings = catalog_ns.get("mappings") or []
        if mappings:
            return mappings[0].get("pageSlug")
        slug = element.get("productSlug")
        if slug:
            return slug.strip("/")
        return None

    def _pick_image(self, element: dict[str, Any]) -> str:
        images = element.get("keyImages") or []
        for preferred in ("DieselStoreFrontWide", "OfferImageWide", "Thumbnail"):
            for image in images:
                if image.get("type") == preferred:
                    return image.get("url") or ""
        return images[0].get("url") if images else ""

    def _extract_original_price(self, element: dict[str, Any]) -> tuple[float | None, str | None]:
        total_price = (((element.get("price") or {}).get("totalPrice") or {}))
        original = total_price.get("originalPrice")
        currency = total_price.get("currencyCode")
        if original is None:
            return None, currency
        return round(float(original) / 100.0, 2), currency

    def _extract_categories(self, element: dict[str, Any]) -> list[str]:
        categories = []
        for category in element.get("categories") or []:
            path = category.get("path")
            if path:
                categories.append(path.split("/")[-1])
        return categories[:5]
