from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
import random
from typing import Any

import httpx


class CircuitOpenError(RuntimeError):
    pass


class ResilientHttpClient:
    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(self, client: httpx.AsyncClient, failure_threshold: int = 3, reset_after_seconds: int = 180) -> None:
        self.client = client
        self.failure_threshold = failure_threshold
        self.reset_after = timedelta(seconds=reset_after_seconds)
        self.failures: dict[str, int] = defaultdict(int)
        self.open_until: dict[str, datetime] = {}

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        response = await self._request('GET', url, **kwargs)
        return response.json()

    async def get_text(self, url: str, **kwargs: Any) -> str:
        response = await self._request('GET', url, **kwargs)
        return response.text

    async def get_bytes(self, url: str, **kwargs: Any) -> bytes:
        response = await self._request('GET', url, **kwargs)
        return response.content

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        host = httpx.URL(url).host or 'default'
        now = datetime.utcnow()
        if host in self.open_until and now < self.open_until[host]:
            raise CircuitOpenError(f'Circuit is open for {host}')

        attempts = int(kwargs.pop('attempts', 4))
        base_delay = float(kwargs.pop('base_delay', 0.75))
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                response = await self.client.request(method, url, **kwargs)
                response.raise_for_status()
                self.failures[host] = 0
                self.open_until.pop(host, None)
                return response
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in self.RETRYABLE_STATUS_CODES:
                    raise
                last_error = exc
                self._register_retryable_failure(host)
                if attempt == attempts:
                    break
                await self._sleep_with_backoff(base_delay, attempt, exc.response)
            except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                last_error = exc
                self._register_retryable_failure(host)
                if attempt == attempts:
                    break
                await self._sleep_with_backoff(base_delay, attempt, None)
        raise last_error if last_error else RuntimeError('Unknown HTTP error')

    def _register_retryable_failure(self, host: str) -> None:
        self.failures[host] += 1
        if self.failures[host] >= self.failure_threshold:
            self.open_until[host] = datetime.utcnow() + self.reset_after

    async def _sleep_with_backoff(self, base_delay: float, attempt: int, response: httpx.Response | None) -> None:
        import asyncio

        delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.35)
        if response is not None and response.status_code == 429:
            retry_after = response.headers.get('Retry-After')
            if retry_after and retry_after.isdigit():
                delay = max(delay, float(retry_after))
        await asyncio.sleep(delay)