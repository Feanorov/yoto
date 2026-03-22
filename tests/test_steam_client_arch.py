from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from dealbot.settings import SteamAccessConfig
from infrastructure.clients.base_http import ResilientHttpClient
from infrastructure.clients.steam_client import SteamClient


def make_config(tmp_path: Path, degraded_threshold: int = 2, search_page_size: int = 100) -> SteamAccessConfig:
    return SteamAccessConfig(
        cache_root=tmp_path / 'steam_cache',
        appdetails_ttl_hours=24,
        reviews_ttl_hours=12,
        deadlines_ttl_hours=6,
        search_page_size=search_page_size,
        max_concurrent_requests=1,
        pacing_delay_ms=1,
        adaptive_slowdown_step=2.0,
        adaptive_slowdown_max=8.0,
        degraded_threshold=degraded_threshold,
        degraded_cooldown_seconds=60,
    )


def test_steam_client_uses_cache_for_appdetails(tmp_path: Path) -> None:
    calls = {'count': 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls['count'] += 1
        return httpx.Response(200, json={'10': {'success': True, 'data': {'name': 'Test Game', 'type': 'game'}}})

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            steam = SteamClient(ResilientHttpClient(client), make_config(tmp_path))
            first = await steam.get_app_details('10')
            second = await steam.get_app_details('10')
            assert first['name'] == 'Test Game'
            assert second['name'] == 'Test Game'

    asyncio.run(run())
    assert calls['count'] == 1


def test_steam_client_marks_degraded_on_429_and_returns_partial_search_results(tmp_path: Path) -> None:
    html = '''
    <a class="search_result_row" data-ds-appid="10" href="https://store.steampowered.com/app/10/Test_Game/">
      <img src="https://example.com/header.png" />
      <span class="title">Test Game</span>
      <div class="discount_pct">-90%</div>
      <div class="discount_original_price">100в‚ґ</div>
      <div class="discount_final_price">10в‚ґ</div>
    </a>
    '''

    async def handler(request: httpx.Request) -> httpx.Response:
        start = request.url.params.get('start')
        if start == '0':
            return httpx.Response(200, json={'results_html': html})
        return httpx.Response(429, json={'error': 'rate limited'})

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            steam = SteamClient(ResilientHttpClient(client, failure_threshold=1, reset_after_seconds=60), make_config(tmp_path, degraded_threshold=1, search_page_size=1))
            offers = await steam.search_specials(200)
            return offers, steam.source_state

    offers, state = asyncio.run(run())
    assert len(offers) == 1
    assert state['mode'] == 'degraded'