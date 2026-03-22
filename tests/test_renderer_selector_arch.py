from __future__ import annotations

import asyncio
from datetime import datetime
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

from domain.entities.offer import AssetBundle, OfferKind, OfferSource
from infrastructure.clients.base_http import ResilientHttpClient
from infrastructure.render.cards.renderer_selector import CardRendererRouter, YotoCardRendererV42Adapter
from infrastructure.render.cards.yoto_card_engine_v4 import YotoCardType

from .test_caption_builder_arch import make_offer


def _gameplay_eval(url: str, **overrides):
    item = {
        'url': url,
        'source_type': 'gameplay_media',
        'source_types': ['media_still'],
        'score': 0.0,
        'available': True,
        'ui_like': False,
        'ui_relaxed_candidate': False,
        'text_heavy': False,
        'low_info': False,
        'logo_dominant': False,
        'steam_ui_like': False,
        'banner_like': False,
        'horizontal_text_block': False,
        'promotional_layout': False,
        'aspect_mismatched': False,
        'text_coverage_ratio': 0.0,
        'scene_richness_score': 0.5,
        'luminance': 96.0,
        'edge_mean': 18.0,
        'dark_ratio': 0.35,
        'meets_gameplay_floor': False,
        'group_key': url.rsplit('/', 1)[-1],
        'scene_vector': (10.0, 20.0, 30.0),
        'color_histogram_signature': (0.2, 0.4, 0.4),
        'composition_signature': (20.0, 22.0, 24.0),
        'index': 0,
    }
    item.update(overrides)
    return item


async def image_handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url).lower()
    if 'capsule' in url:
        image = Image.new('RGB', (231, 87), '#24324d')
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 231, 28), fill='#101722')
        draw.text((34, 34), 'CAPSULE', fill='#f2f5fa')
    elif 'text_banner' in url or 'banner_text' in url:
        image = Image.new('RGB', (1600, 900), '#223047')
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 1600, 240), fill='#0f1724')
        draw.rectangle((0, 680, 1600, 900), fill='#131c2b')
        draw.rectangle((180, 250, 1420, 640), fill='#39506f')
        for index in range(8):
            left = 72 + index * 182
            draw.rectangle((left, 58, left + 128, 112), fill='#f5f8fc')
            draw.rectangle((left, 132, left + 148, 182), fill='#f0c56c')
        for index in range(6):
            left = 180 + index * 212
            draw.rectangle((left, 734, left + 156, 782), outline='#eef4fb', width=3)
    elif 'menu' in url or 'inventory' in url or 'ui_like' in url:
        image = Image.new('RGB', (1600, 900), '#161c28')
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 1600, 120), fill='#0d1118')
        draw.rectangle((0, 120, 320, 900), fill='#111825')
        draw.rectangle((1280, 140, 1570, 860), fill='#0f1622')
        for index in range(8):
            top = 168 + index * 74
            draw.rectangle((56, top, 270, top + 42), outline='#7086a5', width=2)
            draw.text((72, top + 8), f'MENU {index + 1}', fill='#dbe7f6')
        for index in range(6):
            top = 188 + index * 96
            draw.rectangle((1340, top, 1516, top + 54), outline='#54647f', width=2)
            draw.text((1356, top + 14), 'UI', fill='#eef3fb')
        draw.rectangle((420, 200, 1170, 720), fill='#1f2a39')
        draw.text((650, 430), 'LOADOUT', fill='#ffffff')
    elif 'loading' in url or 'title_screen' in url:
        image = Image.new('RGB', (1600, 900), '#0c1017')
        draw = ImageDraw.Draw(image)
        draw.ellipse((470, 110, 1130, 770), fill='#17202e')
        draw.text((600, 360), 'PRESS START', fill='#f6fbff')
        draw.text((670, 430), 'LOADING', fill='#b8c6da')
    elif 'dark_shot' in url:
        image = Image.new('RGB', (1600, 900), '#090c12')
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 680, 1600, 900), fill='#121722')
        draw.ellipse((640, 220, 860, 520), fill='#1d2433')
        draw.rectangle((920, 300, 1120, 640), fill='#161d2c')
    elif 'bright_hero' in url or 'library_hero' in url:
        image = Image.new('RGB', (1600, 900), '#31455b')
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 560, 1600, 900), fill='#182230')
        draw.ellipse((500, 110, 1080, 820), fill='#ffd38a')
        draw.rectangle((900, 210, 1360, 760), fill='#ff8d4a')
        draw.ellipse((220, 220, 520, 620), fill='#72d4ff')
    elif 'combat_alt' in url:
        image = Image.new('RGB', (1600, 900), '#24384f')
        draw = ImageDraw.Draw(image)
        draw.polygon(((140, 780), (430, 150), (710, 800)), fill='#db8b45')
        draw.polygon(((820, 160), (1160, 760), (1450, 190)), fill='#2ea88d')
        draw.ellipse((520, 200, 930, 760), fill='#102036')
        draw.rectangle((1010, 250, 1450, 790), fill='#5d38c8')
    elif 'action' in url or 'battle' in url:
        image = Image.new('RGB', (1600, 900), '#20364a')
        draw = ImageDraw.Draw(image)
        draw.polygon(((120, 760), (420, 120), (720, 780)), fill='#f28f3b')
        draw.polygon(((760, 120), (1120, 760), (1440, 150)), fill='#34c3a0')
        draw.ellipse((540, 180, 980, 760), fill='#0f1b2f')
        draw.rectangle((1020, 230, 1490, 780), fill='#6d3fd9')
    elif 'explore' in url:
        image = Image.new('RGB', (1600, 900), '#7eb6d2')
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 620, 1600, 900), fill='#315238')
        draw.polygon(((160, 620), (520, 170), (860, 620)), fill='#7f8da0')
        draw.polygon(((760, 620), (1100, 220), (1420, 620)), fill='#90a1b4')
        draw.ellipse((690, 430, 860, 760), fill='#e2a35d')
        draw.rectangle((950, 420, 1260, 700), fill='#c27840')
    elif 'builder_ui' in url:
        image = Image.new('RGB', (1600, 900), '#4a8fb8')
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 620, 1600, 900), fill='#34582f')
        draw.polygon(((120, 640), (440, 240), (760, 640)), fill='#8190a2')
        draw.polygon(((700, 640), (980, 210), (1320, 640)), fill='#72819a')
        draw.rectangle((860, 420, 1280, 760), fill='#c78a4d')
        draw.rectangle((40, 40, 1540, 112), fill='#152433')
        draw.rectangle((1240, 170, 1540, 760), fill='#1c2e40')
        for index in range(5):
            top = 210 + index * 96
            draw.rectangle((1276, top, 1500, top + 54), outline='#89b4d1', width=2)
        draw.rectangle((88, 780, 720, 854), fill='#1b3045')
    elif 'borderline_scene' in url:
        image = Image.new('RGB', (1360, 900), '#47637b')
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 650, 1360, 900), fill='#31452e')
        draw.polygon(((120, 650), (410, 280), (690, 650)), fill='#6c7886')
        draw.rectangle((760, 430, 1020, 760), fill='#9e7440')
        draw.ellipse((930, 360, 1120, 660), fill='#d4a261')
    elif 'promo_rescue' in url:
        image = Image.new('RGB', (1360, 900), '#36495f')
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 640, 1360, 900), fill='#26382c')
        draw.polygon(((140, 640), (460, 240), (720, 640)), fill='#6f7d8b')
        draw.rectangle((820, 420, 1120, 760), fill='#a67944')
        draw.ellipse((980, 320, 1160, 620), fill='#d08b57')
    elif 'world' in url or 'builder' in url:
        image = Image.new('RGB', (1600, 900), '#5aa3d7')
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 600, 1600, 900), fill='#355b2d')
        draw.polygon(((120, 620), (460, 220), (760, 620)), fill='#6d7b8f')
        draw.polygon(((620, 620), (980, 180), (1320, 620)), fill='#7c889c')
        draw.rectangle((900, 420, 1260, 700), fill='#d6a24f')
        draw.rectangle((1040, 310, 1110, 700), fill='#8e5a2a')
    elif 'shot' in url or '/ss_' in url:
        image = Image.new('RGB', (1600, 900), '#2fb87d')
        draw = ImageDraw.Draw(image)
        draw.ellipse((120, 120, 620, 760), fill='#0f412d')
        draw.rectangle((760, 160, 1480, 780), fill='#153a58')
    else:
        image = Image.new('RGB', (1200, 460), '#445a91')
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 1200, 96), fill='#1a2133')
        draw.text((440, 170), 'HEADER', fill='#ffffff')
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    return httpx.Response(200, content=buffer.getvalue())

def test_card_renderer_router_defaults_to_legacy_renderer(tmp_path: Path) -> None:
    router = CardRendererRouter(tmp_path, renderer_mode='legacy', fallback_to_legacy=True)
    offer = make_offer()
    transport = httpx.MockTransport(image_handler)

    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            return await router.render(ResilientHttpClient(client), offer, 'steam_discount')

    result = asyncio.run(run())
    snapshot = result.diagnostics.to_snapshot()

    assert result.image_path.exists()
    assert snapshot['renderer_requested'] == 'legacy'
    assert snapshot['renderer_selected'] == 'legacy'
    assert snapshot['renderer_family'] == 'legacy'
    assert snapshot['renderer_fallback_used'] is False


def test_card_renderer_router_can_use_yoto_v4_renderer(tmp_path: Path) -> None:
    router = CardRendererRouter(tmp_path, renderer_mode='yoto_v4', fallback_to_legacy=False)
    offer = make_offer()
    transport = httpx.MockTransport(image_handler)

    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            return await router.render(ResilientHttpClient(client), offer, 'steam_discount')

    result = asyncio.run(run())
    snapshot = result.diagnostics.to_snapshot()

    assert result.image_path.exists()
    assert snapshot['renderer_requested'] == 'yoto_v4'
    assert snapshot['renderer_selected'] == 'yoto_v4'
    assert snapshot['renderer_family'] == 'yoto_v4'
    assert snapshot['layout_variant'] == 'yoto_v4_discount'
    assert snapshot['editorial_phrase'] == 'Co-op favorite'
    assert snapshot['asset_used'] == offer.assets.screenshot
    assert snapshot['hero_asset_used'] == offer.assets.screenshot
    assert snapshot['hero_source_type'] == 'screenshot'
    assert snapshot['hero_selection_reason'] == 'selected_gameplay_screenshot'
    assert snapshot['hero_candidates_count'] == 2
    assert snapshot['hero_capsule_rejected'] is False
    assert snapshot['hero_fallback_used'] is False
    assert snapshot['hero_selection']['selected_source'] == 'screenshot'
    assert snapshot['hero_selection']['reason'] == 'selected_gameplay_screenshot'
    assert result.assets_used


def test_card_renderer_router_accepts_yoto_v42_alias(tmp_path: Path) -> None:
    router = CardRendererRouter(tmp_path, renderer_mode='yoto_v42', fallback_to_legacy=False)
    offer = make_offer()
    transport = httpx.MockTransport(image_handler)

    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            return await router.render(ResilientHttpClient(client), offer, 'steam_discount')

    result = asyncio.run(run())
    snapshot = result.diagnostics.to_snapshot()

    assert result.image_path.exists()
    assert snapshot['renderer_requested'] == 'yoto_v4'
    assert snapshot['renderer_selected'] == 'yoto_v4'
    assert snapshot['renderer_family'] == 'yoto_v4'


def test_card_renderer_router_reports_capsule_rejection_reason_tags(tmp_path: Path) -> None:
    router = CardRendererRouter(tmp_path, renderer_mode='yoto_v4', fallback_to_legacy=False)
    offer = make_offer()
    offer.assets = AssetBundle(
        hero='https://example.com/capsule_231x87.jpg',
        header='https://example.com/capsule_231x87.jpg',
        screenshot='https://example.com/shot.png',
        fallback='https://example.com/capsule_231x87.jpg',
    )
    transport = httpx.MockTransport(image_handler)

    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            return await router.render(ResilientHttpClient(client), offer, 'steam_discount')

    result = asyncio.run(run())
    snapshot = result.diagnostics.to_snapshot()

    assert result.image_path.exists()
    assert snapshot['hero_source_type'] == 'screenshot'
    assert snapshot['hero_selection_reason'] == 'capsule_rejected_text_heavy'
    assert snapshot['hero_capsule_rejected'] is True
    assert snapshot['hero_fallback_used'] is False
    assert snapshot['hero_rejected_capsules']
    assert snapshot['hero_selection']['selected_source'] == 'screenshot'
    assert snapshot['hero_selection']['reason'] == 'capsule_rejected_text_heavy'



def test_yoto_card_renderer_adapter_emits_clean_ukrainian_copy(tmp_path: Path) -> None:
    adapter = YotoCardRendererV42Adapter(tmp_path)
    offer = make_offer()
    offer.source = OfferSource.EPIC
    offer.offer_kind = OfferKind.FREEBIE
    offer.promo_end = datetime(2026, 3, 19, 15, 0)
    offer.price_before_minor = 27500

    assert adapter._platform_badge_text(offer, 'epic_free', YotoCardType.FREE_GAME) == 'EPIC РОЗДАЧА'
    assert adapter._brand_micro_label(YotoCardType.FREE_GAME) == 'ігрові роздачі'
    assert adapter._deadline_text(offer, YotoCardType.FREE_GAME) == 'забрати до 19 березня, 15:00'
    assert adapter._old_price_text(offer) == '275 грн'

def test_card_renderer_router_rejects_capsule_like_assets_and_uses_branded_fallback(tmp_path: Path) -> None:
    router = CardRendererRouter(tmp_path, renderer_mode='yoto_v4', fallback_to_legacy=False)
    offer = make_offer()
    offer.offer_kind = OfferKind.FREEBIE
    offer.assets = AssetBundle(
        hero='https://example.com/capsule_231x87.jpg',
        header='https://example.com/capsule_231x87.jpg',
        screenshot=None,
        fallback='https://example.com/capsule_231x87.jpg',
    )
    transport = httpx.MockTransport(image_handler)

    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            return await router.render(ResilientHttpClient(client), offer, 'steam_free')

    result = asyncio.run(run())
    snapshot = result.diagnostics.to_snapshot()

    assert result.image_path.exists()
    assert snapshot['renderer_selected'] == 'yoto_v4'
    assert snapshot['asset_used'] is None
    assert snapshot['hero_source_type'] == 'placeholder'
    assert snapshot['hero_selection_reason'] == 'weak_asset_fallback'
    assert snapshot['hero_capsule_rejected'] is True
    assert snapshot['hero_fallback_used'] is True
    assert snapshot['hero_selection']['fallback_used'] is True
    assert 'hero_selection_fallback' in snapshot['render_warnings']
    assert 'fallback_artwork' in snapshot['render_warnings']
    assert result.assets_used


def test_card_renderer_router_falls_back_to_legacy_when_yoto_raises(tmp_path: Path, monkeypatch) -> None:
    router = CardRendererRouter(tmp_path, renderer_mode='yoto_v4', fallback_to_legacy=True)
    offer = make_offer()
    transport = httpx.MockTransport(image_handler)

    async def boom(http, offer, template_id):
        raise RuntimeError('yoto failed')

    monkeypatch.setattr(router.yoto_v42, 'render', boom)

    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            return await router.render(ResilientHttpClient(client), offer, 'steam_discount')

    result = asyncio.run(run())
    snapshot = result.diagnostics.to_snapshot()

    assert result.image_path.exists()
    assert snapshot['renderer_requested'] == 'yoto_v4'
    assert snapshot['renderer_selected'] == 'legacy'
    assert snapshot['renderer_fallback_used'] is True
    assert any('renderer_fallback_from_yoto_v4' in warning for warning in snapshot['render_warnings'])



def test_card_renderer_router_selects_top_gameplay_frames_deterministically(tmp_path: Path) -> None:
    router = CardRendererRouter(tmp_path, renderer_mode='yoto_v4', fallback_to_legacy=False)
    offer = make_offer()
    offer.description = ' '.join(
        (
            'https://example.com/extras/menu.png',
            'https://example.com/extras/action.png',
            'https://example.com/extras/world.png',
            'https://example.com/extras/loading.png',
            'https://example.com/extras/battle.png',
        )
    )
    transport = httpx.MockTransport(image_handler)

    async def run_once():
        async with httpx.AsyncClient(transport=transport) as client:
            return await router.render(ResilientHttpClient(client), offer, 'steam_discount')

    first = asyncio.run(run_once())
    second = asyncio.run(run_once())
    first_snapshot = first.diagnostics.to_snapshot()
    second_snapshot = second.diagnostics.to_snapshot()
    expected_urls = [
        'https://example.com/extras/action.png',
        'https://example.com/extras/world.png',
    ]

    assert first_snapshot['gameplay_selection_reason'] == 'selected_partial_strong_frames'
    assert first_snapshot['gameplay_selected_count'] == 2
    assert first_snapshot['gameplay_selection']['selected_urls'] == expected_urls
    assert second_snapshot['gameplay_selection']['selected_urls'] == expected_urls


def test_card_renderer_router_reports_ui_like_gameplay_rejections(tmp_path: Path) -> None:
    router = CardRendererRouter(tmp_path, renderer_mode='yoto_v4', fallback_to_legacy=False)
    offer = make_offer()
    offer.description = ' '.join(
        (
            'https://example.com/extras/menu.png',
            'https://example.com/extras/action.png',
            'https://example.com/extras/loading.png',
            'https://example.com/extras/world.png',
        )
    )
    transport = httpx.MockTransport(image_handler)

    async def run_once():
        async with httpx.AsyncClient(transport=transport) as client:
            return await router.render(ResilientHttpClient(client), offer, 'steam_discount')

    result = asyncio.run(run_once())
    snapshot = result.diagnostics.to_snapshot()
    score_summary = snapshot['gameplay_score_summary']

    assert snapshot['gameplay_candidates_count'] == 5
    assert snapshot['gameplay_selected_count'] == 2
    assert snapshot['gameplay_rejected_ui_like'] >= 1
    assert snapshot['gameplay_selection']['selected_urls'] == [
        'https://example.com/extras/action.png',
        'https://example.com/extras/world.png',
    ]
    assert snapshot['gameplay_selection_reason'] == 'selected_partial_strong_frames'
    assert any(item['rejection_reason'] == 'ui_like_frame' for item in score_summary)
    assert any(item['asset_url'] == 'https://example.com/extras/loading.png' and item['rejection_reason'] == 'ui_like_frame' for item in score_summary)


def test_card_renderer_router_prefers_bright_subject_hero_over_dark_screenshot(tmp_path: Path) -> None:
    router = CardRendererRouter(tmp_path, renderer_mode='yoto_v4', fallback_to_legacy=False)
    offer = make_offer()
    offer.assets = AssetBundle(
        hero='https://example.com/library_hero_bright_hero.png',
        header='https://example.com/header.png',
        screenshot='https://example.com/dark_shot.png',
        fallback=None,
    )
    transport = httpx.MockTransport(image_handler)

    async def run_once():
        async with httpx.AsyncClient(transport=transport) as client:
            return await router.render(ResilientHttpClient(client), offer, 'steam_discount')

    result = asyncio.run(run_once())
    snapshot = result.diagnostics.to_snapshot()
    score_summary = snapshot['hero_score_summary']
    hero_entry = next(item for item in score_summary if item['asset_url'] == 'https://example.com/library_hero_bright_hero.png')
    dark_entry = next(item for item in score_summary if item['asset_url'] == 'https://example.com/dark_shot.png')

    assert snapshot['hero_source_type'] == 'hero'
    assert snapshot['hero_selection_reason'] == 'selected_primary_hero'
    assert hero_entry['selected'] is True
    assert hero_entry['brightness_score'] > dark_entry['brightness_score']
    assert hero_entry['subject_detection_score'] > dark_entry['subject_detection_score']



def test_card_renderer_router_prefers_diverse_gameplay_scenes_and_rejects_text_banners(tmp_path: Path) -> None:
    router = CardRendererRouter(tmp_path, renderer_mode='yoto_v4', fallback_to_legacy=False)
    offer = make_offer()
    offer.description = ' '.join(
        (
            'https://example.com/extras/action.png',
            'https://example.com/extras/combat_alt.png',
            'https://example.com/extras/explore.png',
            'https://example.com/extras/world.png',
            'https://example.com/extras/text_banner.png',
        )
    )
    transport = httpx.MockTransport(image_handler)

    async def run_once():
        async with httpx.AsyncClient(transport=transport) as client:
            return await router.render(ResilientHttpClient(client), offer, 'steam_discount')

    result = asyncio.run(run_once())
    snapshot = result.diagnostics.to_snapshot()
    selected_urls = snapshot['gameplay_selection']['selected_urls']
    score_summary = snapshot['gameplay_score_summary']
    banner_entry = next(item for item in score_summary if item['asset_url'] == 'https://example.com/extras/text_banner.png')

    assert 'https://example.com/extras/explore.png' in selected_urls
    assert 'https://example.com/extras/world.png' in selected_urls
    assert sum(url in selected_urls for url in ('https://example.com/extras/action.png', 'https://example.com/extras/combat_alt.png')) == 1
    assert banner_entry['selected'] is False
    assert banner_entry['rejection_reason'] in {'marketing_frame', 'ui_like_frame', 'low_information_frame', 'logo_or_title_frame'}
    assert banner_entry['score'] < max(item['score'] for item in score_summary if item['selected'])




def test_card_renderer_router_keeps_single_strong_gameplay_frame_when_it_is_the_only_valid_option(tmp_path: Path) -> None:
    router = CardRendererRouter(tmp_path, renderer_mode='yoto_v4', fallback_to_legacy=False)
    offer = make_offer()
    offer.description = ' '.join(
        (
            'https://example.com/extras/menu.png',
            'https://example.com/extras/loading.png',
            'https://example.com/extras/text_banner.png',
            'https://example.com/extras/world.png',
        )
    )
    transport = httpx.MockTransport(image_handler)

    async def run_once():
        async with httpx.AsyncClient(transport=transport) as client:
            return await router.render(ResilientHttpClient(client), offer, 'steam_discount')

    result = asyncio.run(run_once())
    snapshot = result.diagnostics.to_snapshot()

    assert snapshot['gameplay_selected_count'] == 2
    assert snapshot['gameplay_selection_reason'] == 'selected_partial_strong_frames'
    assert snapshot['gameplay_selection']['selected_urls'] == [offer.assets.screenshot, 'https://example.com/extras/world.png']


def test_card_renderer_router_can_fallback_to_primary_screenshot_for_single_gameplay_frame(tmp_path: Path) -> None:
    router = CardRendererRouter(tmp_path, renderer_mode='yoto_v4', fallback_to_legacy=False)
    offer = make_offer()
    offer.description = ''
    transport = httpx.MockTransport(image_handler)

    async def run_once():
        async with httpx.AsyncClient(transport=transport) as client:
            return await router.render(ResilientHttpClient(client), offer, 'steam_discount')

    result = asyncio.run(run_once())
    snapshot = result.diagnostics.to_snapshot()

    assert snapshot['gameplay_selected_count'] == 1
    assert snapshot['gameplay_selection_reason'] == 'selected_primary_frame_fallback'
    assert snapshot['gameplay_selection']['selected_urls'] == [offer.assets.screenshot]


def test_card_renderer_router_keeps_borderline_frame_when_other_extras_are_rejected(tmp_path: Path) -> None:
    router = CardRendererRouter(tmp_path, renderer_mode='yoto_v4', fallback_to_legacy=False)
    selected_urls, selection = router.yoto_v42._select_gameplay_frames(
        router.yoto_v42._card_type_for_offer(make_offer(), 'steam_discount'),
        [
            _gameplay_eval('https://example.com/extras/menu.png', score=18.0, ui_like=True, low_info=True, index=0),
            _gameplay_eval('https://example.com/extras/loading.png', score=8.0, ui_like=True, low_info=True, index=1),
            _gameplay_eval('https://example.com/extras/borderline_scene.png', score=42.0, low_info=True, index=2),
        ],
        None,
    )

    assert selected_urls == ['https://example.com/extras/borderline_scene.png']
    assert selection['selected_count'] == 1
    assert selection['reason'] == 'selected_borderline_fallback_frame'


def test_card_renderer_router_relaxes_ui_penalty_for_strategy_builder_frames(tmp_path: Path) -> None:
    router = CardRendererRouter(tmp_path, renderer_mode='yoto_v4', fallback_to_legacy=False)
    selected_urls, selection = router.yoto_v42._select_gameplay_frames(
        router.yoto_v42._card_type_for_offer(make_offer(), 'steam_discount'),
        [
            _gameplay_eval('https://example.com/extras/menu.png', score=20.0, ui_like=True, low_info=True, index=0),
            _gameplay_eval(
                'https://example.com/extras/builder_ui.png',
                score=34.0,
                ui_like=False,
                ui_relaxed_candidate=True,
                scene_richness_score=0.54,
                edge_mean=14.0,
                text_coverage_ratio=0.62,
                index=1,
            ),
        ],
        None,
    )

    assert selected_urls == ['https://example.com/extras/builder_ui.png']
    assert selection['selected_count'] == 1
    assert selection['reason'] == 'selected_ui_relaxed_fallback_frame'


def test_card_renderer_router_rescues_semi_clean_frame_from_promo_heavy_set(tmp_path: Path) -> None:
    router = CardRendererRouter(tmp_path, renderer_mode='yoto_v4', fallback_to_legacy=False)
    selected_urls, selection = router.yoto_v42._select_gameplay_frames(
        router.yoto_v42._card_type_for_offer(make_offer(), 'steam_discount'),
        [
            _gameplay_eval('https://example.com/extras/text_banner.png', score=-20.0, promotional_layout=True, banner_like=True, horizontal_text_block=True, index=0),
            _gameplay_eval('https://example.com/extras/title_screen.png', score=6.0, ui_like=True, low_info=True, promotional_layout=True, horizontal_text_block=True, index=1),
            _gameplay_eval('https://example.com/extras/promo_rescue.png', score=38.0, scene_richness_score=0.38, edge_mean=12.0, index=2),
        ],
        None,
    )

    assert selected_urls == ['https://example.com/extras/promo_rescue.png']
    assert selection['selected_count'] == 1
    assert selection['reason'] == 'selected_promo_rescue_frame'
