from __future__ import annotations

from typing import Any

from .base_http import ResilientHttpClient


class EpicClient:
    FREE_GAMES_URL = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"

    def __init__(self, http: ResilientHttpClient) -> None:
        self.http = http

    async def get_free_games(self) -> list[dict[str, Any]]:
        payload = await self.http.get_json(
            self.FREE_GAMES_URL,
            params={"locale": "uk-UA", "country": "UA", "allowCountries": "UA"},
        )
        return ((((payload.get("data") or {}).get("Catalog") or {}).get("searchStore") or {}).get("elements") or [])
