from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from dealbot.settings import EventIngestionConfig

from .base_http import ResilientHttpClient


ALL_NEWS_URL = 'https://store.steampowered.com/oldnews/'
PACIFIC_TZ = ZoneInfo('America/Los_Angeles')
UTC_TZ = timezone.utc
EVENT_KEYWORDS = (
    ' fest',
    'festival',
    ' sale',
    'showcase',
    'celebration',
    'spotlight',
)
MONTHS = {
    'january': 1,
    'jan': 1,
    'february': 2,
    'feb': 2,
    'march': 3,
    'mar': 3,
    'april': 4,
    'apr': 4,
    'may': 5,
    'june': 6,
    'jun': 6,
    'july': 7,
    'jul': 7,
    'august': 8,
    'aug': 8,
    'september': 9,
    'sep': 9,
    'october': 10,
    'oct': 10,
    'november': 11,
    'nov': 11,
    'december': 12,
    'dec': 12,
}


class SteamEventsClient:
    def __init__(self, http: ResilientHttpClient, config: EventIngestionConfig) -> None:
        self.http = http
        self.config = config

    async def list_events(self, now: datetime) -> list[dict[str, Any]]:
        if not self.config.enabled:
            return []
        html = await self.http.get_text(ALL_NEWS_URL, params={'l': 'english'})
        return self._parse_events(html, now)

    def _parse_events(self, html: str, now: datetime) -> list[dict[str, Any]]:
        soup = BeautifulSoup(html or '', 'html.parser')
        blocks = soup.select('div.newsPostBlock.steam_community_blog')
        lookback_cutoff = now - timedelta(days=self.config.lookback_days)
        events: list[dict[str, Any]] = []

        for block in blocks:
            event = self._parse_event_block(block, now)
            if event is None:
                continue
            start = datetime.fromisoformat(event['starts_at'])
            end = datetime.fromisoformat(event['ends_at'])
            if end < now or end < start or start < lookback_cutoff:
                continue
            events.append(event)
            if len(events) >= self.config.max_posts:
                break
        return events

    def _parse_event_block(self, block, now: datetime) -> dict[str, Any] | None:
        title_node = block.select_one('.posttitle a')
        body_node = block.select_one('.body')
        date_node = block.select_one('.headline .date')
        if title_node is None or body_node is None or date_node is None:
            return None

        title = title_node.get_text(' ', strip=True)
        body_text = body_node.get_text(' ', strip=True)
        if not self._looks_like_event(title, body_text):
            return None

        store_url = self._pick_store_url(body_node)
        if store_url is None:
            return None

        published_at = self._parse_post_date(date_node.get_text(' ', strip=True), now)
        starts_at, ends_at = self._extract_event_window(body_text, published_at)
        if starts_at is None or ends_at is None:
            return None

        image_node = block.select_one('img.capsule')
        return {
            'id': self._build_event_id(store_url, title_node.get('href', '')),
            'title': title,
            'url': store_url,
            'image_url': image_node.get('src') if image_node else None,
            'description': body_text,
            'starts_at': starts_at.isoformat(),
            'ends_at': ends_at.isoformat(),
            'hashtags': self._hashtags_from_url(store_url),
        }

    def _extract_event_window(self, body_text: str, published_at: datetime) -> tuple[datetime | None, datetime | None]:
        normalized = self._normalize_text(body_text)
        explicit_range = re.search(
            r'(?:from|starting|starts)\s+(?P<start_month>[a-z]+)\s+(?P<start_day>\d{1,2})(?:st|nd|rd|th)?'
            r'(?:\s+at\s+(?P<start_hour>\d{1,2})\s*(?P<start_meridiem>a\.m\.|p\.m\.))?'
            r'.{0,120}?through\s+(?P<end_month>[a-z]+)\s+(?P<end_day>\d{1,2})(?:st|nd|rd|th)?'
            r'(?:\s+at\s+(?P<end_hour>\d{1,2})\s*(?P<end_meridiem>a\.m\.|p\.m\.))?',
            normalized,
        )
        if explicit_range:
            start = self._build_pacific_datetime(
                published_at,
                explicit_range.group('start_month'),
                explicit_range.group('start_day'),
                explicit_range.group('start_hour'),
                explicit_range.group('start_meridiem'),
                fallback_hour=10,
            )
            end = self._build_pacific_datetime(
                published_at,
                explicit_range.group('end_month'),
                explicit_range.group('end_day'),
                explicit_range.group('end_hour'),
                explicit_range.group('end_meridiem'),
                fallback_hour=10,
            )
            return start, end

        through_now = re.search(
            r'(?:from now|on now|now)\s+through\s+(?P<end_month>[a-z]+)\s+(?P<end_day>\d{1,2})(?:st|nd|rd|th)?'
            r'(?:\s+at\s+(?P<end_hour>\d{1,2})\s*(?P<end_meridiem>a\.m\.|p\.m\.))?',
            normalized,
        )
        if through_now:
            end = self._build_pacific_datetime(
                published_at,
                through_now.group('end_month'),
                through_now.group('end_day'),
                through_now.group('end_hour'),
                through_now.group('end_meridiem'),
                fallback_hour=10,
            )
            return published_at, end

        ends_only = re.search(
            r'ends?\s+(?P<end_month>[a-z]+)\s+(?P<end_day>\d{1,2})(?:st|nd|rd|th)?'
            r'(?:\s+at\s+(?P<end_hour>\d{1,2})\s*(?P<end_meridiem>a\.m\.|p\.m\.))?',
            normalized,
        )
        if ends_only:
            end = self._build_pacific_datetime(
                published_at,
                ends_only.group('end_month'),
                ends_only.group('end_day'),
                ends_only.group('end_hour'),
                ends_only.group('end_meridiem'),
                fallback_hour=10,
            )
            return published_at, end

        return None, None

    @staticmethod
    def _looks_like_event(title: str, body_text: str) -> bool:
        combined = SteamEventsClient._normalize_text(f'{title} {body_text}')
        return any(keyword in combined for keyword in EVENT_KEYWORDS)

    @staticmethod
    def _pick_store_url(body_node) -> str | None:
        for link in body_node.select('a.bb_link'):
            href = (link.get('href') or '').strip()
            if href.startswith('https://store.steampowered.com/') and ('/sale/' in href or '/category/' in href):
                return href.split('?', 1)[0].rstrip('/')
        return None

    @staticmethod
    def _parse_post_date(raw_value: str, now: datetime) -> datetime:
        match = re.search(
            r'(?:(?P<day_first>\d{1,2})\s+(?P<month_first>[A-Za-z]{3,9})|(?P<month_second>[A-Za-z]{3,9})\s+(?P<day_second>\d{1,2}))',
            raw_value or '',
        )
        if not match:
            return now
        month_name = match.group('month_first') or match.group('month_second')
        day_value = match.group('day_first') or match.group('day_second')
        month = MONTHS.get((month_name or '').lower())
        if month is None or day_value is None:
            return now
        candidate = datetime(now.year, month, int(day_value), 10, 0)
        if candidate > now + timedelta(days=31):
            candidate = candidate.replace(year=now.year - 1)
        return SteamEventsClient._pacific_to_utc(candidate)

    def _build_pacific_datetime(
        self,
        published_at: datetime,
        month_name: str | None,
        day_value: str | None,
        hour_value: str | None,
        meridiem: str | None,
        fallback_hour: int,
    ) -> datetime | None:
        if not month_name or not day_value:
            return None
        month = MONTHS.get(month_name.lower())
        if month is None:
            return None
        year = published_at.year
        day = int(day_value)
        hour = self._parse_hour(hour_value, meridiem, fallback_hour)
        candidate = datetime(year, month, day, hour, 0)
        if candidate + timedelta(days=180) < published_at:
            candidate = candidate.replace(year=year + 1)
        elif candidate - timedelta(days=180) > published_at:
            candidate = candidate.replace(year=year - 1)
        return self._pacific_to_utc(candidate)

    @staticmethod
    def _parse_hour(raw_value: str | None, meridiem: str | None, fallback_hour: int) -> int:
        if not raw_value:
            return fallback_hour
        hour = int(raw_value)
        suffix = (meridiem or '').lower()
        if suffix.startswith('p') and hour < 12:
            return hour + 12
        if suffix.startswith('a') and hour == 12:
            return 0
        return hour

    @staticmethod
    def _build_event_id(store_url: str, fallback_url: str) -> str:
        parsed = urlparse(store_url)
        path = parsed.path.strip('/').replace('/', ':')
        if path:
            return path.lower()
        fallback = urlparse(fallback_url).path.strip('/').replace('/', ':')
        return fallback.lower() or 'steam:event'

    @staticmethod
    def _hashtags_from_url(store_url: str) -> list[str]:
        slug = urlparse(store_url).path.strip('/').split('/')[-1]
        if not slug:
            return []
        return [slug.replace('-', '_')]

    @staticmethod
    def _normalize_text(value: str) -> str:
        text = re.sub(r'[^\x00-\x7F]+', ' ', value or ' ')
        text = re.sub(r'\s+', ' ', text).strip().lower()
        return text.replace("steam's", 'steam s')

    @staticmethod
    def _pacific_to_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=PACIFIC_TZ).astimezone(UTC_TZ).replace(tzinfo=None)
