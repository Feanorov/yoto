from __future__ import annotations

import asyncio

from application.use_cases.enrich_offer import EnrichOfferUseCase
from infrastructure.clients.base_http import CircuitOpenError

from .test_caption_builder_arch import make_offer


class StubSteamClient:
    @property
    def source_state(self):
        return {'mode': 'degraded', 'reason': 'circuit_open'}

    async def get_app_details(self, app_id: str):
        raise CircuitOpenError('Circuit is open for store.steampowered.com')

    async def get_reviews(self, app_id: str):
        return {}

    async def get_deadline(self, app_id: str):
        return None


def test_enrich_offer_returns_partial_offers_when_circuit_opens() -> None:
    first = make_offer()
    second = make_offer()
    second.offer_id = 'steam:11'
    second.game_id = '11'
    use_case = EnrichOfferUseCase(StubSteamClient())
    enriched = asyncio.run(use_case.enrich([first, second], limit=2))
    assert len(enriched) == 2
    assert all(item.metadata.get('steam_partial_enrichment') is True for item in enriched)