from __future__ import annotations

import asyncio
from dataclasses import replace
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

from domain.entities.offer import OfferKind, OfferSource
from infrastructure.clients.base_http import ResilientHttpClient
from infrastructure.render.cards.template_system import TemplateSystem

from .test_caption_builder_arch import make_offer


def _make_png(color: str, size: tuple[int, int]) -> bytes:
    image = Image.new('RGB', size, color)
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


async def palette_handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    color = '#445566'
    size = (1600, 900)
    if 'header-red' in url:
        color = '#d34848'
        size = (1600, 400)
    elif 'shot-green' in url:
        color = '#31c96d'
        size = (1600, 900)
    elif 'epic-purple' in url:
        color = '#5f52c7'
        size = (1600, 900)
    elif 'event-blue' in url:
        color = '#4c78d8'
        size = (1600, 900)
    return httpx.Response(200, content=_make_png(color, size))


def _render(tmp_path: Path, offer, template_id: str):
    renderer = TemplateSystem(tmp_path)
    transport = httpx.MockTransport(palette_handler)

    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            return await renderer.render(ResilientHttpClient(client), offer, template_id)

    return asyncio.run(run())


def _sample(path: Path, x: int, y: int) -> tuple[int, int, int]:
    image = Image.open(path).convert('RGB')
    return image.getpixel((x, y))


def test_discount_card_uses_hero_first_banner_layout(tmp_path: Path) -> None:
    offer = make_offer()
    offer.assets = replace(
        offer.assets,
        hero='https://example.com/header-red.png',
        header='https://example.com/header-red.png',
        screenshot='https://example.com/shot-green.png',
    )

    result = _render(tmp_path, offer, 'steam_discount')
    left_hero = _sample(result.image_path, 180, 200)
    right_hero = _sample(result.image_path, 1080, 200)
    slab_center = _sample(result.image_path, 640, 560)

    assert result.diagnostics.layout_variant == 'steam_discount'
    assert result.diagnostics.hero_asset_used == 'https://example.com/shot-green.png'
    assert left_hero[1] > left_hero[0] + 40
    assert right_hero[1] > right_hero[0] + 40
    assert sum(slab_center) < 220


def test_freebie_card_prioritizes_free_badge(tmp_path: Path) -> None:
    offer = make_offer()
    offer.source = OfferSource.EPIC
    offer.offer_kind = OfferKind.FREEBIE
    offer.store_url = 'https://store.epicgames.com/uk/p/test-game'
    offer.price_before_minor = 69900
    offer.price_after_minor = 0
    offer.discount_percent = 100
    offer.has_trading_cards = False
    offer.assets = replace(
        offer.assets,
        hero='https://example.com/epic-purple.png',
        header='https://example.com/epic-purple.png',
        screenshot='https://example.com/epic-purple.png',
    )

    result = _render(tmp_path, offer, 'epic_free')
    badge = result.diagnostics.badge_rect
    assert badge is not None
    badge_sample = _sample(result.image_path, badge[0] + 16, (badge[1] + badge[3]) // 2)

    assert result.diagnostics.layout_variant == 'epic_free'
    assert badge_sample[1] > badge_sample[0] + 40
    assert badge_sample[1] > badge_sample[2] + 40


def test_event_card_uses_editorial_panel_not_generic_deal_slab(tmp_path: Path) -> None:
    offer = make_offer()
    offer.source = OfferSource.EVENT
    offer.offer_kind = OfferKind.FESTIVAL
    offer.title = 'Steam Strategy Fest'
    offer.price_before_minor = None
    offer.price_after_minor = None
    offer.discount_percent = 0
    offer.has_trading_cards = False
    offer.assets = replace(
        offer.assets,
        hero='https://example.com/event-blue.png',
        header='https://example.com/event-blue.png',
        screenshot='https://example.com/event-blue.png',
        fallback='https://example.com/event-blue.png',
    )

    result = _render(tmp_path, offer, 'festival_event')
    panel_shadow = _sample(result.image_path, 180, 280)
    right_side = _sample(result.image_path, 1030, 320)

    assert result.diagnostics.layout_variant == 'festival_event_feature'
    assert len(result.diagnostics.title_lines) <= 3
    assert sum(panel_shadow) < 240
    assert right_side[2] > right_side[0]
    assert sum(right_side) > 180


def test_long_titles_step_down_before_clipping(tmp_path: Path) -> None:
    offer = make_offer()
    offer.title = 'A Very Long Game Name With Extra Words For Testing Font Reduction Mechanics'

    result = _render(tmp_path, offer, 'steam_discount')

    assert len(result.diagnostics.title_lines) <= 2
    assert result.diagnostics.title_font_size is not None
    assert result.diagnostics.title_font_size < 82
    assert 'title' in result.diagnostics.clipped_fields
    assert result.diagnostics.title_lines[-1].endswith('...')


def test_header_only_assets_use_contain_mode_for_logo_safe_crop(tmp_path: Path) -> None:
    offer = make_offer()
    offer.assets = replace(
        offer.assets,
        hero='https://example.com/header-red.png',
        header='https://example.com/header-red.png',
        screenshot=None,
        fallback='https://example.com/header-red.png',
    )

    result = _render(tmp_path, offer, 'steam_discount')

    assert result.diagnostics.hero_mode == 'contain'

