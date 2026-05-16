from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from infrastructure.render.cards.yoto_card_engine_v4 import (
    CARD_SIZE,
    UA_DISCOUNT,
    YotoCardEngineV4,
    YotoCardType,
)


def _make_scene_art(path: Path, *, size: tuple[int, int] = (1600, 900)) -> None:
    image = Image.new('RGB', size, '#253550')
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, size[0], int(size[1] * 0.34)), fill='#f25d50')
    draw.rectangle((0, int(size[1] * 0.72), size[0], size[1]), fill='#0a0f16')
    draw.ellipse((80, 60, int(size[0] * 0.46), int(size[1] * 0.92)), fill='#38c7d4')
    draw.polygon(
        (
            (int(size[0] * 0.44), int(size[1] * 0.92)),
            (int(size[0] * 0.66), int(size[1] * 0.12)),
            (int(size[0] * 0.88), int(size[1] * 0.92)),
        ),
        fill='#ffb14d',
    )
    draw.rounded_rectangle(
        (int(size[0] * 0.62), int(size[1] * 0.24), int(size[0] * 0.92), int(size[1] * 0.84)),
        radius=52,
        fill='#7a4dff',
    )
    image.save(path)


def test_yoto_card_engine_v4_renders_deterministically(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'discount.png'
    _make_scene_art(artwork_path)
    engine = YotoCardEngineV4(tmp_path)
    payload = {
        'title': 'Slay the Spire',
        'platform': 'STEAM',
        'type': YotoCardType.DISCOUNT,
        'deadline': 'until Mar 18, 20:00',
        'old_price': '379 UAH',
        'current_price': '-75%',
        'artwork_path': artwork_path,
        'slug': 'slay_the_spire',
    }

    first = engine.render_card(payload)
    second = engine.render_card(payload)

    assert first.image_path.name == 'yoto_card_slay_the_spire.png'
    assert first.image_path.read_bytes() == second.image_path.read_bytes()
    assert first.diagnostics.text_payload['composition_mode'].startswith('clean_mvp_discount_')
    assert first.diagnostics.text_payload['platform_badge_rendered'] is False
    assert first.diagnostics.text_payload['primary_signal'] == '-75%'
    assert first.diagnostics.text_payload['title_shelf'] == 'suppressed'

    with Image.open(first.image_path) as image:
        assert image.size == CARD_SIZE


def test_yoto_card_engine_v4_scales_discount_signal_by_percent(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'scale.png'
    _make_scene_art(artwork_path)
    engine = YotoCardEngineV4(tmp_path)

    low = engine.render_card(
        {
            'title': 'Low Discount',
            'platform': 'STEAM',
            'type': YotoCardType.DISCOUNT,
            'current_price': '-20%',
            'artwork_path': artwork_path,
            'slug': 'low_discount',
        }
    )
    mid = engine.render_card(
        {
            'title': 'Mid Discount',
            'platform': 'STEAM',
            'type': YotoCardType.DISCOUNT,
            'current_price': '-50%',
            'artwork_path': artwork_path,
            'slug': 'mid_discount',
        }
    )
    high = engine.render_card(
        {
            'title': 'High Discount',
            'platform': 'STEAM',
            'type': YotoCardType.DISCOUNT,
            'current_price': '-80%',
            'artwork_path': artwork_path,
            'slug': 'high_discount',
        }
    )

    assert low.diagnostics.text_payload['discount_percent'] == 20
    assert mid.diagnostics.text_payload['discount_percent'] == 50
    assert high.diagnostics.text_payload['discount_percent'] == 80
    assert low.diagnostics.text_payload['discount_scale_multiplier'] == 1.0
    assert mid.diagnostics.text_payload['discount_scale_multiplier'] == 1.05
    assert high.diagnostics.text_payload['discount_scale_multiplier'] == 1.25
    assert low.diagnostics.text_payload['primary_signal_font_size'] < mid.diagnostics.text_payload['primary_signal_font_size']
    assert mid.diagnostics.text_payload['primary_signal_font_size'] < high.diagnostics.text_payload['primary_signal_font_size']


def test_yoto_card_engine_v4_cover_crop_preserves_aspect_ratio_without_stretch(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'portraitish.png'
    _make_scene_art(artwork_path, size=(900, 1400))
    engine = YotoCardEngineV4(tmp_path)
    result = engine.render_card(
        {
            'title': 'Portrait Crop Probe',
            'platform': 'STEAM',
            'type': YotoCardType.DISCOUNT,
            'current_price': '-70%',
            'artwork_path': artwork_path,
            'slug': 'portrait_crop_probe',
        }
    )

    crop_left, crop_top, crop_right, crop_bottom = result.diagnostics.text_payload['background_crop_box']
    crop_width = crop_right - crop_left
    crop_height = crop_bottom - crop_top
    crop_aspect = crop_width / crop_height
    target_aspect = CARD_SIZE[0] / CARD_SIZE[1]

    assert abs(crop_aspect - target_aspect) < 0.01
    assert tuple(result.diagnostics.text_payload['background_bias']) == (0.5, 0.45)

    with Image.open(result.image_path) as image:
        assert image.size == CARD_SIZE


def test_yoto_card_engine_v4_keeps_discount_and_title_inside_safe_zone(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'safe_zone.png'
    _make_scene_art(artwork_path)
    engine = YotoCardEngineV4(tmp_path)
    result = engine.render_card(
        {
            'title': 'Need for Speed Heat',
            'platform': 'STEAM',
            'type': YotoCardType.DISCOUNT,
            'deadline': 'until Mar 18, 20:00',
            'old_price': '1999 UAH',
            'current_price': '-95%',
            'artwork_path': artwork_path,
            'slug': 'safe_zone_probe',
        }
    )

    safe_left, safe_top, safe_right, safe_bottom = result.diagnostics.text_payload['safe_zone']
    signal_left, signal_top, signal_right, signal_bottom = result.diagnostics.text_payload['primary_signal_bounds']
    title_left, title_top, title_right, title_bottom = result.diagnostics.text_payload['title_bounds']

    assert safe_left <= signal_left <= signal_right <= safe_right
    assert safe_top <= signal_top <= signal_bottom <= safe_bottom
    assert safe_left <= title_left <= title_right <= safe_right
    assert safe_top <= title_top <= title_bottom <= safe_bottom


def test_yoto_card_engine_v4_handles_small_images_and_missing_optional_meta(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'small.png'
    _make_scene_art(artwork_path, size=(320, 180))
    engine = YotoCardEngineV4(tmp_path)
    result = engine.render_card(
        {
            'title': 'Small Image Probe',
            'platform': 'STEAM',
            'type': YotoCardType.DISCOUNT,
            'artwork_path': artwork_path,
            'slug': 'small_image_probe',
        }
    )

    assert result.diagnostics.used_placeholder_artwork is False
    assert result.diagnostics.meta_alignment == 'hidden'
    assert result.diagnostics.text_payload['primary_signal'] == UA_DISCOUNT
    assert tuple(result.diagnostics.text_payload['background_zoom_levels']) == (1.0,)

    with Image.open(result.image_path) as image:
        assert image.size == CARD_SIZE


def test_yoto_card_engine_v4_renders_explicit_platform_label_only_when_requested(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'festival.png'
    _make_scene_art(artwork_path)
    engine = YotoCardEngineV4(tmp_path)
    result = engine.render_card(
        {
            'title': 'Steam Strategy Fest',
            'platform': 'STEAM',
            'type': YotoCardType.FESTIVAL,
            'deadline': 'until Mar 18, 20:00',
            'artwork_path': artwork_path,
            'slug': 'steam_strategy_fest',
            'platform_badge': 'LIVE EVENT',
            'editorial_phrase': 'Season spotlight',
        }
    )

    assert result.diagnostics.text_payload['platform_badge_rendered'] is True
    assert result.diagnostics.platform_badge_text == 'LIVE EVENT'

    with Image.open(result.image_path) as image:
        assert image.size == CARD_SIZE


def test_yoto_card_engine_v4_suppresses_generic_explicit_platform_label(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'generic_label.png'
    _make_scene_art(artwork_path)
    engine = YotoCardEngineV4(tmp_path)
    result = engine.render_card(
        {
            'title': 'Dave the Diver',
            'platform': 'STEAM',
            'type': YotoCardType.DISCOUNT,
            'current_price': '-30%',
            'artwork_path': artwork_path,
            'slug': 'dave_generic_label',
            'platform_badge': 'STEAM DISCOUNT',
        }
    )

    assert result.diagnostics.text_payload['platform_badge_rendered'] is False


def test_yoto_card_engine_v4_renders_discount_price_block_v2_with_crossed_old_price(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'price_block_v2.png'
    _make_scene_art(artwork_path)
    engine = YotoCardEngineV4(tmp_path)
    result = engine.render_card(
        {
            'title': 'Far Cry 5',
            'platform': 'STEAM',
            'type': YotoCardType.DISCOUNT,
            'sticker_text': '-85%',
            'current_price': '137 грн',
            'old_price': '915 грн',
            'artwork_path': artwork_path,
            'slug': 'far_cry_5',
        }
    )

    assert result.diagnostics.text_payload['primary_signal'] == '-85%'
    assert result.diagnostics.text_payload['meta_current_price'] == '137 грн'
    assert result.diagnostics.text_payload['meta_old_price'] == '915 грн'
    assert result.diagnostics.text_payload['meta_old_price_struck'] is True
    old_bounds = result.diagnostics.text_payload['meta_old_price_bounds']
    strike_y = result.diagnostics.text_payload['meta_old_price_strike_y']
    assert result.diagnostics.text_payload['meta_old_price_strike_formula'] == 'glyph_bbox_vertical_center'
    assert strike_y == round((old_bounds[1] + old_bounds[3]) / 2)
    assert old_bounds[1] < strike_y < old_bounds[3]
    assert result.diagnostics.text_payload['meta_price_block_mode'] == 'current_old_strike'
    assert result.diagnostics.text_payload['meta_line'] == '137 грн ~~915 грн~~'
    assert result.diagnostics.meta_alignment == 'price_block_v2'


def test_yoto_card_engine_v4_handles_discount_price_block_without_old_price(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'price_block_current_only.png'
    _make_scene_art(artwork_path)
    engine = YotoCardEngineV4(tmp_path)
    result = engine.render_card(
        {
            'title': 'Solo Price Probe',
            'platform': 'STEAM',
            'type': YotoCardType.DISCOUNT,
            'sticker_text': '-40%',
            'current_price': 'Безплатно',
            'artwork_path': artwork_path,
            'slug': 'solo_price_probe',
        }
    )

    assert result.diagnostics.text_payload['primary_signal'] == '-40%'
    assert result.diagnostics.text_payload['meta_current_price'] == 'Безплатно'
    assert result.diagnostics.text_payload['meta_price_block_mode'] == 'current_only'
    assert result.diagnostics.text_payload['meta_old_price_struck'] is False
    assert result.diagnostics.meta_alignment == 'price_block_v2'
