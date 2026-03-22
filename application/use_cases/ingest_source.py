from __future__ import annotations

from datetime import datetime
import logging

from dealbot.settings import AppSettings
from domain.entities.offer import Offer
from infrastructure.clients.epic_client import EpicClient
from infrastructure.clients.steam_events_client import SteamEventsClient
from infrastructure.clients.steam_client import SteamClient

from .normalize_offer import normalize_auto_event, normalize_calendar_events, normalize_epic_offer, normalize_steam_search_row


class IngestSourceUseCase:
    def __init__(
        self,
        settings: AppSettings,
        steam_client: SteamClient,
        epic_client: EpicClient,
        steam_events_client: SteamEventsClient | None = None,
    ) -> None:
        self.settings = settings
        self.steam_client = steam_client
        self.epic_client = epic_client
        self.steam_events_client = steam_events_client
        self.logger = logging.getLogger(__name__)
        self.last_run_sources: dict[str, dict[str, object]] = {}

    async def execute(self, now: datetime) -> list[Offer]:
        offers: list[Offer] = []
        event_offers: list[Offer] = []
        source_status: dict[str, dict[str, object]] = {}

        if 'steam' not in self.settings.operational.degraded_sources:
            try:
                steam_rows = await self.steam_client.search_specials(self.settings.static.steam_scan_limit)
                steam_state = self.steam_client.source_state
                for row in steam_rows:
                    normalized = normalize_steam_search_row(row)
                    normalized.metadata['source_state'] = steam_state['mode']
                    normalized.metadata['steam_state_reason'] = steam_state['reason']
                    offers.append(normalized)
                source_status['steam'] = {
                    'status': str(steam_state.get('mode') or 'healthy'),
                    'reason': str(steam_state.get('reason') or 'healthy'),
                    'offers': len(steam_rows),
                    'details': dict(steam_state),
                }
            except Exception as exc:
                self.logger.warning('Steam ingest degraded: %s', exc)
                source_status['steam'] = {
                    'status': 'degraded',
                    'reason': self._exc_reason(exc),
                    'offers': 0,
                }
        else:
            source_status['steam'] = {
                'status': 'disabled',
                'reason': 'configured_degraded_source',
                'offers': 0,
            }

        if 'epic' not in self.settings.operational.degraded_sources:
            try:
                epic_rows = await self.epic_client.get_free_games()
                epic_count = 0
                for raw in epic_rows:
                    normalized = normalize_epic_offer(raw, now)
                    if normalized is not None:
                        offers.append(normalized)
                        epic_count += 1
                source_status['epic'] = {
                    'status': 'healthy',
                    'reason': 'healthy',
                    'offers': epic_count,
                    'raw_offers': len(epic_rows),
                }
            except Exception as exc:
                self.logger.warning('Epic ingest degraded: %s', exc)
                source_status['epic'] = {
                    'status': 'degraded',
                    'reason': self._exc_reason(exc),
                    'offers': 0,
                }
        else:
            source_status['epic'] = {
                'status': 'disabled',
                'reason': 'configured_degraded_source',
                'offers': 0,
            }

        if self.steam_events_client is not None and 'events' not in self.settings.operational.degraded_sources:
            try:
                auto_event_rows = await self.steam_events_client.list_events(now)
                auto_event_count = 0
                for raw in auto_event_rows:
                    normalized = normalize_auto_event(raw, now)
                    if normalized is not None:
                        event_offers.append(normalized)
                        auto_event_count += 1
                source_status['events_auto'] = {
                    'status': 'healthy',
                    'reason': 'healthy',
                    'offers': auto_event_count,
                    'raw_offers': len(auto_event_rows),
                }
            except Exception as exc:
                self.logger.warning('Automatic event ingest degraded: %s', exc)
                source_status['events_auto'] = {
                    'status': 'degraded',
                    'reason': self._exc_reason(exc),
                    'offers': 0,
                }
        elif self.steam_events_client is None:
            source_status['events_auto'] = {
                'status': 'disabled',
                'reason': 'client_unavailable',
                'offers': 0,
            }
        else:
            source_status['events_auto'] = {
                'status': 'disabled',
                'reason': 'configured_degraded_source',
                'offers': 0,
            }

        try:
            calendar_events = normalize_calendar_events(self.settings.calendar_events_path, now)
            event_offers.extend(calendar_events)
            source_status['events_calendar'] = {
                'status': 'healthy',
                'reason': 'healthy',
                'offers': len(calendar_events),
            }
        except Exception as exc:
            self.logger.warning('Calendar events degraded: %s', exc)
            source_status['events_calendar'] = {
                'status': 'degraded',
                'reason': self._exc_reason(exc),
                'offers': 0,
            }

        deduped_events = self._dedupe_events(event_offers)
        offers.extend(deduped_events)
        source_status['events_deduped'] = {
            'status': 'healthy',
            'reason': 'deduped',
            'offers': len(deduped_events),
            'raw_offers': len(event_offers),
        }
        self.last_run_sources = source_status
        return offers

    @staticmethod
    def _dedupe_events(events: list[Offer]) -> list[Offer]:
        deduped: dict[str, Offer] = {}
        for event in events:
            deduped[IngestSourceUseCase._event_key(event)] = event
        return list(deduped.values())

    @staticmethod
    def _event_key(event: Offer) -> str:
        store_url = (event.store_url or '').strip().lower().rstrip('/')
        if store_url:
            return store_url
        promo_start = event.promo_start.isoformat() if event.promo_start else 'unknown'
        return f'{event.title.strip().lower()}|{promo_start}'

    @staticmethod
    def _exc_reason(exc: Exception) -> str:
        return str(exc).strip() or exc.__class__.__name__
