from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from ..models import Offer, OfferSource, PostKind


@dataclass(slots=True)
class CalendarEventSource:
    path: Path

    def fetch_due_events(self, now: datetime) -> list[Offer]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        events = payload.get("events", [])
        offers: list[Offer] = []
        for event in events:
            start = self._parse_dt(event.get("starts_at"))
            end = self._parse_dt(event.get("ends_at"))
            if start is None or end is None:
                continue
            if end < now.replace(tzinfo=timezone.utc):
                continue
            if start - timedelta(days=2) > now.replace(tzinfo=timezone.utc):
                continue
            offers.append(
                Offer(
                    source=OfferSource.EVENT,
                    post_kind=PostKind.FESTIVAL,
                    offer_id=event.get("id") or event.get("title"),
                    store_item_id=event.get("id") or event.get("title"),
                    title=event.get("title") or "Фестиваль",
                    url=event.get("url") or "https://store.steampowered.com/",
                    image_url=event.get("image_url") or "",
                    hero_image_url=event.get("image_url") or "",
                    screenshot_url=event.get("image_url") or "",
                    description=event.get("description") or "",
                    short_description=event.get("description") or "",
                    sale_end=end,
                    genres=list(event.get("hashtags") or []),
                    tags=list(event.get("hashtags") or []),
                )
            )
        return offers

    @staticmethod
    def _parse_dt(value: str | None) -> datetime | None:
        if not value:
            return None
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
