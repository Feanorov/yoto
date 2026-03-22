from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

import httpx


class CurrencyConverter:
    def __init__(self, cache_path: Path) -> None:
        self.cache_path = cache_path
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)

    async def convert_to_uah(self, client: httpx.AsyncClient, amount: float | None, currency: str | None) -> float | None:
        if amount is None:
            return None
        if not currency:
            return amount
        normalized = currency.upper()
        if normalized in {"UAH", "₴"}:
            return amount
        rates = await self._load_rates(client)
        rate = rates.get(normalized)
        if rate is None:
            return amount
        return round(amount * rate, 2)

    async def _load_rates(self, client: httpx.AsyncClient) -> dict[str, float]:
        today = datetime.utcnow().date().isoformat()
        if self.cache_path.exists():
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
            if payload.get("date") == today:
                return payload.get("rates", {})

        response = await client.get("https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json")
        response.raise_for_status()
        data = response.json()
        rates = {"UAH": 1.0}
        for item in data:
            code = item.get("cc")
            value = item.get("rate")
            if code and value:
                rates[code.upper()] = float(value)
        self.cache_path.write_text(json.dumps({"date": today, "rates": rates}, ensure_ascii=False, indent=2), encoding="utf-8")
        return rates
