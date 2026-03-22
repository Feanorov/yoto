from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class OfferSource(str, Enum):
    STEAM = "steam"
    EPIC = "epic"
    EVENT = "event"


class PostKind(str, Enum):
    STEAM_DISCOUNT = "steam_discount"
    STEAM_FREE = "steam_free"
    EPIC_FREE = "epic_free"
    GAME_OF_DAY = "game_of_day"
    FESTIVAL = "festival"


@dataclass(slots=True)
class OfferHistory:
    source: OfferSource
    offer_id: str
    last_posted_at: datetime | None = None
    last_discount_pct: int | None = None
    last_final_price_uah: float | None = None
    last_initial_price_uah: float | None = None
    last_sale_end: datetime | None = None
    total_posts: int = 0
    final_day_alert_sent: bool = False


@dataclass(slots=True)
class Offer:
    source: OfferSource
    post_kind: PostKind
    offer_id: str
    store_item_id: str
    title: str
    url: str
    image_url: str
    hero_image_url: str | None = None
    screenshot_url: str | None = None
    description: str = ""
    short_description: str = ""
    discount_pct: int = 0
    original_price_uah: float | None = None
    final_price_uah: float | None = None
    currency: str = "UAH"
    sale_end: datetime | None = None
    review_percent: int | None = None
    review_summary: str | None = None
    achievements_count: int | None = None
    has_trading_cards: bool = False
    genres: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    is_free_to_keep: bool = False
    is_dlc: bool = False
    is_app: bool = True
    priority_flags: list[str] = field(default_factory=list)
    improvement_note: str | None = None
    previous_price_uah: float | None = None
    previous_price_date: datetime | None = None

    def to_json_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("sale_end", "previous_price_date"):
            value = payload[key]
            if value is not None:
                payload[key] = value.isoformat()
        payload["source"] = self.source.value
        payload["post_kind"] = self.post_kind.value
        return payload

    @classmethod
    def from_json_dict(cls, payload: dict[str, Any]) -> "Offer":
        sale_end = payload.get("sale_end")
        previous_price_date = payload.get("previous_price_date")
        return cls(
            source=OfferSource(payload["source"]),
            post_kind=PostKind(payload["post_kind"]),
            offer_id=payload["offer_id"],
            store_item_id=payload.get("store_item_id", payload["offer_id"]),
            title=payload["title"],
            url=payload["url"],
            image_url=payload["image_url"],
            hero_image_url=payload.get("hero_image_url"),
            screenshot_url=payload.get("screenshot_url"),
            description=payload.get("description", ""),
            short_description=payload.get("short_description", ""),
            discount_pct=int(payload.get("discount_pct", 0)),
            original_price_uah=payload.get("original_price_uah"),
            final_price_uah=payload.get("final_price_uah"),
            currency=payload.get("currency", "UAH"),
            sale_end=datetime.fromisoformat(sale_end) if sale_end else None,
            review_percent=payload.get("review_percent"),
            review_summary=payload.get("review_summary"),
            achievements_count=payload.get("achievements_count"),
            has_trading_cards=bool(payload.get("has_trading_cards", False)),
            genres=list(payload.get("genres", [])),
            tags=list(payload.get("tags", [])),
            is_free_to_keep=bool(payload.get("is_free_to_keep", False)),
            is_dlc=bool(payload.get("is_dlc", False)),
            is_app=bool(payload.get("is_app", True)),
            priority_flags=list(payload.get("priority_flags", [])),
            improvement_note=payload.get("improvement_note"),
            previous_price_uah=payload.get("previous_price_uah"),
            previous_price_date=datetime.fromisoformat(previous_price_date) if previous_price_date else None,
        )


@dataclass(slots=True)
class QueueItem:
    queue_id: str
    score: float
    created_at: datetime
    offer: Offer
