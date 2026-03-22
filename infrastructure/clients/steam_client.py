from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

from dealbot.settings import SteamAccessConfig

from .base_http import CircuitOpenError, ResilientHttpClient
from .steam_cache import SteamCache


STEAM_STORE_BASE = 'https://store.steampowered.com'
SEARCH_URL = f'{STEAM_STORE_BASE}/search/results/'
APP_DETAILS_URL = f'{STEAM_STORE_BASE}/api/appdetails'
APP_REVIEWS_URL = f'{STEAM_STORE_BASE}/appreviews'


@dataclass(slots=True)
class SteamSourceState:
    mode: str = 'healthy'
    reason: str = 'healthy'
    degraded_until: datetime | None = None
    slowdown_multiplier: float = 1.0
    recent_429_count: int = 0

    def snapshot(self) -> dict[str, Any]:
        return {
            'mode': self.mode,
            'reason': self.reason,
            'degraded_until': self.degraded_until.isoformat() if self.degraded_until else None,
            'slowdown_multiplier': round(self.slowdown_multiplier, 2),
            'recent_429_count': self.recent_429_count,
        }


class SteamClient:
    def __init__(self, http: ResilientHttpClient, config: SteamAccessConfig) -> None:
        self.http = http
        self.config = config
        self.cache = SteamCache(config.cache_root)
        self.logger = logging.getLogger(__name__)
        self.semaphore = asyncio.Semaphore(config.max_concurrent_requests)
        self._pace_lock = asyncio.Lock()
        self._next_request_at = 0.0
        self.state = SteamSourceState()

    async def search_specials(self, limit: int) -> list[dict[str, Any]]:
        offers: list[dict[str, Any]] = []
        page_size = self.config.search_page_size
        effective_limit = min(limit, max(page_size, limit))
        for start in range(0, effective_limit, page_size):
            try:
                payload = await self._steam_get_json(
                    SEARCH_URL,
                    params={
                        'query': '',
                        'start': start,
                        'count': page_size,
                        'dynamic_data': '',
                        'sort_by': '_ASC',
                        'force_infinite': 1,
                        'specials': 1,
                        'maxprice': '',
                        'category1': 998,
                        'cc': 'ua',
                        'l': 'ukrainian',
                        'infinite': 1,
                        'ndl': 1,
                    },
                )
            except Exception as exc:
                if offers:
                    self.logger.warning('Steam specials degraded after %s offers: %s', len(offers), exc)
                    break
                raise
            page = self._parse_search_results(payload.get('results_html', ''))
            if not page:
                break
            offers.extend(page)
            if len(page) < page_size:
                break
        return offers[:limit]

    async def get_app_details(self, app_id: str) -> dict[str, Any] | None:
        cached = self.cache.get('appdetails', app_id)
        if cached is not None:
            return cached
        try:
            payload = await self._steam_get_json(APP_DETAILS_URL, params={'appids': app_id, 'cc': 'ua', 'l': 'ukrainian'})
        except Exception:
            return self.cache.get('appdetails', app_id, allow_stale=True)
        wrapper = payload.get(str(app_id)) or {}
        if not wrapper.get('success'):
            return None
        data = wrapper.get('data') or None
        if data is not None:
            self.cache.set('appdetails', app_id, data, self.config.appdetails_ttl_hours)
        return data

    async def get_reviews(self, app_id: str) -> dict[str, Any]:
        cached = self.cache.get('reviews', app_id)
        if cached is not None:
            return cached
        try:
            payload = await self._steam_get_json(
                f'{APP_REVIEWS_URL}/{app_id}',
                params={'json': 1, 'language': 'all', 'purchase_type': 'all', 'num_per_page': 0, 'filter': 'all'},
            )
        except Exception:
            stale = self.cache.get('reviews', app_id, allow_stale=True)
            return stale or {}
        self.cache.set('reviews', app_id, payload, self.config.reviews_ttl_hours)
        return payload

    async def get_deadline(self, app_id: str) -> datetime | None:
        cached = self.cache.get('deadlines', app_id)
        if cached is not None:
            return datetime.fromisoformat(cached) if cached else None
        try:
            html = await self._steam_get_text(f'{STEAM_STORE_BASE}/app/{app_id}/', params={'cc': 'ua', 'l': 'ukrainian'})
        except Exception:
            stale = self.cache.get('deadlines', app_id, allow_stale=True)
            return datetime.fromisoformat(stale) if stale else None
        deadline = self._extract_deadline(html)
        self.cache.set('deadlines', app_id, deadline.isoformat() if deadline else None, self.config.deadlines_ttl_hours)
        return deadline

    async def _steam_get_json(self, url: str, **kwargs: Any) -> Any:
        async with self.semaphore:
            await self._wait_for_slot()
            try:
                payload = await self.http.get_json(url, **kwargs)
            except Exception as exc:
                self._handle_failure(exc)
                raise
            self._handle_success()
            return payload

    async def _steam_get_text(self, url: str, **kwargs: Any) -> str:
        async with self.semaphore:
            await self._wait_for_slot()
            try:
                payload = await self.http.get_text(url, **kwargs)
            except Exception as exc:
                self._handle_failure(exc)
                raise
            self._handle_success()
            return payload

    async def _wait_for_slot(self) -> None:
        loop = asyncio.get_running_loop()
        async with self._pace_lock:
            now = loop.time()
            wait_seconds = max(0.0, self._next_request_at - now)
            if wait_seconds:
                await asyncio.sleep(wait_seconds)
            delay = (self.config.pacing_delay_ms / 1000.0) * self.state.slowdown_multiplier
            self._next_request_at = loop.time() + delay

    def _handle_success(self) -> None:
        self.state.recent_429_count = max(0, self.state.recent_429_count - 1)
        self.state.slowdown_multiplier = max(1.0, self.state.slowdown_multiplier * 0.92)
        if self.state.degraded_until and self.state.degraded_until <= datetime.utcnow():
            self.state.mode = 'healthy'
            self.state.reason = 'recovered'
            self.state.degraded_until = None

    def _handle_failure(self, exc: Exception) -> None:
        now = datetime.utcnow()
        if isinstance(exc, CircuitOpenError):
            self.state.mode = 'degraded'
            self.state.reason = 'circuit_open'
            self.state.degraded_until = now + timedelta(seconds=self.config.degraded_cooldown_seconds)
            return
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
            self.state.recent_429_count += 1
            self.state.slowdown_multiplier = min(
                self.config.adaptive_slowdown_max,
                self.state.slowdown_multiplier * self.config.adaptive_slowdown_step,
            )
            if self.state.recent_429_count >= self.config.degraded_threshold:
                self.state.mode = 'degraded'
                self.state.reason = 'rate_limited'
                self.state.degraded_until = now + timedelta(seconds=self.config.degraded_cooldown_seconds)
            retry_after = exc.response.headers.get('Retry-After')
            if retry_after and retry_after.isdigit():
                self._next_request_at += float(retry_after)
            return
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500:
            self.state.mode = 'degraded'
            self.state.reason = f'http_{exc.response.status_code}'
            self.state.degraded_until = now + timedelta(seconds=self.config.degraded_cooldown_seconds)
            return
        if isinstance(exc, httpx.TimeoutException):
            self.state.mode = 'degraded'
            self.state.reason = 'timeout'
            self.state.degraded_until = now + timedelta(seconds=self.config.degraded_cooldown_seconds)

    def _extract_deadline(self, html: str) -> datetime | None:
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

    def _parse_search_results(self, html: str) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html or '', 'html.parser')
        offers: list[dict[str, Any]] = []
        for row in soup.select('a.search_result_row'):
            app_id = self._extract_app_id(row.get('data-ds-appid', ''))
            if not app_id:
                continue
            title_node = row.select_one('span.title')
            if title_node is None:
                continue
            discount_text = row.select_one('div.discount_pct') or row.select_one('span.discount_pct')
            original_node = row.select_one('div.discount_original_price')
            final_node = row.select_one('div.discount_final_price')
            image_node = row.select_one('img')
            offers.append(
                {
                    'app_id': app_id,
                    'title': title_node.get_text(' ', strip=True),
                    'discount_percent': self._parse_discount(discount_text.get_text(' ', strip=True) if discount_text else ''),
                    'price_before': self._parse_price(original_node.get_text(' ', strip=True) if original_node else ''),
                    'price_after': self._parse_price(final_node.get_text(' ', strip=True) if final_node else ''),
                    'image_url': image_node.get('src', '') if image_node else '',
                    'store_url': (row.get('href') or f'{STEAM_STORE_BASE}/app/{app_id}/').split('?')[0],
                }
            )
        return offers

    @property
    def source_state(self) -> dict[str, Any]:
        if self.state.degraded_until and self.state.degraded_until <= datetime.utcnow() and self.state.mode == 'degraded':
            self.state.mode = 'healthy'
            self.state.reason = 'recovered'
            self.state.degraded_until = None
        return self.state.snapshot()

    @staticmethod
    def _extract_app_id(raw_value: str) -> str | None:
        match = re.search(r'(\d+)', raw_value or '')
        return match.group(1) if match else None

    @staticmethod
    def _parse_discount(value: str) -> int:
        match = re.search(r'-?(\d+)', value or '')
        return int(match.group(1)) if match else 0

    @staticmethod
    def _parse_price(value: str) -> int | None:
        text = (value or '').strip().lower().replace('₴', '').replace('uah', '')
        if not text:
            return None
        if 'коштов' in text or 'free' in text:
            return 0
        digits = re.findall(r'\d+', text)
        if not digits:
            return None
        if ',' in text and len(digits[-1]) == 2:
            integer = ''.join(digits[:-1]) or '0'
            decimal = digits[-1]
            return int(integer) * 100 + int(decimal)
        return int(''.join(digits)) * 100