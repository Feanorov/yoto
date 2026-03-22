from __future__ import annotations

import asyncio
from dataclasses import replace
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

from infrastructure.clients.base_http import ResilientHttpClient
from infrastructure.render.cards.template_system import TemplateSystem

from .test_caption_builder_arch import make_offer


async def image_handler(request: httpx.Request) -> httpx.Response:
    image = Image.new('RGB', (1280, 720), '#334455')
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    return httpx.Response(200, content=buffer.getvalue())


def test_template_system_returns_render_diagnostics(tmp_path: Path) -> None:
    renderer = TemplateSystem(tmp_path)
    offer = make_offer()
    offer.title = 'Very Long Test Game Remastered Complete Edition With Extra Words For Clipping'
    offer.assets = replace(offer.assets, hero='https://example.com/hero.png')
    transport = httpx.MockTransport(image_handler)

    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            return await renderer.render(ResilientHttpClient(client), offer, 'steam_discount')

    result = asyncio.run(run())
    snapshot = result.diagnostics.to_snapshot()

    assert result.image_path.exists()
    assert result.diagnostics.template_id == 'steam_discount'
    assert result.diagnostics.asset_used == 'https://example.com/hero.png'
    assert len(result.diagnostics.title_lines) <= 2
    assert 'default_font_fallback' not in result.diagnostics.render_warnings
    assert result.assets_used
    assert {'template_id', 'asset_used', 'title_lines', 'clipped_fields', 'render_warnings'} <= set(snapshot)
    assert snapshot['layout_variant'] == 'steam_discount'
    assert snapshot['hero_rect'] == (40, 40, 1240, 384)
    assert snapshot['info_rect'] == (56, 402, 1224, 676)
    assert result.diagnostics.title_font_size is not None
