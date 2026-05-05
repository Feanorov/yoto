from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from infrastructure.render.cards.yoto_card_engine_v4 import (
    CARD_SIZE,
    UA_DISCOUNT,
    UA_FREE,
    YotoCardEngineV4,
    YotoCardType,
)


def _make_scene_art(path: Path) -> None:
    image = Image.new('RGB', (1600, 900), '#2b3f63')
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1600, 520), fill='#f4475f')
    draw.rectangle((0, 720, 1600, 900), fill='#0b1018')
    draw.ellipse((110, 150, 760, 860), fill='#43c7d8')
    draw.polygon(((720, 810), (1040, 120), (1400, 810)), fill='#ffb14d')
    draw.rounded_rectangle((900, 250, 1450, 770), radius=52, fill='#7f4bff')
    image.save(path)


def test_yoto_card_engine_v4_renders_clean_discount_layout_deterministically(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'discount.png'
    _make_scene_art(artwork_path)
    engine = YotoCardEngineV4(tmp_path)
    payload = {
        'title': 'Slay the Spire',
        'platform': 'STEAM',
        'type': YotoCardType.DISCOUNT,
        'deadline': 'до 18 березня, 20:00',
        'old_price': '379 грн',
        'current_price': '-75%',
        'artwork_path': artwork_path,
        'slug': 'slay_the_spire',
    }

    first = engine.render_card(payload)
    first_bytes = first.image_path.read_bytes()
    second = engine.render_card(payload)

    assert first.image_path.name == 'yoto_card_slay_the_spire.png'
    assert first_bytes == second.image_path.read_bytes()
    assert first.diagnostics.text_payload['composition_mode'].startswith('clean_mvp_discount_')
    assert first.diagnostics.text_payload['legacy_chrome_removed'] is True
    assert first.diagnostics.text_payload['primary_signal'] == '-75%'
    assert first.diagnostics.text_payload['primary_signal_font_size'] > first.diagnostics.text_payload['title_font_size']
    assert first.diagnostics.meta_alignment == 'secondary_line'
    assert first.diagnostics.text_payload['title_shelf'] == 'suppressed'

    with Image.open(first.image_path) as image:
        assert image.size == CARD_SIZE
        top_pixel = image.getpixel((640, 60))
        assert top_pixel[0] > 220
        assert top_pixel[1] < 100
        assert top_pixel[2] < 120


def test_yoto_card_engine_v4_wraps_long_titles_without_overflow(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'long_title.png'
    _make_scene_art(artwork_path)
    engine = YotoCardEngineV4(tmp_path)
    result = engine.render_card(
        {
            'title': 'Black Desert Online: Land of the Morning Light Deluxe Founder Celebration Collection',
            'platform': 'STEAM',
            'type': YotoCardType.DISCOUNT,
            'deadline': 'до 15 березня, 17:00',
            'old_price': '1199 грн',
            'current_price': '-60%',
            'artwork_path': artwork_path,
            'slug': 'long_title_layout',
        }
    )

    bounds = result.diagnostics.text_payload['title_bounds']
    assert result.diagnostics.title_mode == 'two_line'
    assert len(result.diagnostics.title_lines) == 2
    assert bounds[2] - bounds[0] <= result.diagnostics.text_payload['title_max_width']

    with Image.open(result.image_path) as image:
        assert image.size == CARD_SIZE


def test_yoto_card_engine_v4_omits_meta_line_when_price_and_deadline_are_missing(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'missing_meta.png'
    _make_scene_art(artwork_path)
    engine = YotoCardEngineV4(tmp_path)
    result = engine.render_card(
        {
            'title': 'Dead Space',
            'platform': 'STEAM',
            'type': YotoCardType.DISCOUNT,
            'artwork_path': artwork_path,
            'slug': 'dead_space_clean_meta_fallback',
        }
    )

    assert result.diagnostics.meta_alignment == 'hidden'
    assert result.diagnostics.text_payload['primary_signal'] == UA_DISCOUNT
    assert 'meta_line' not in result.diagnostics.text_payload

    with Image.open(result.image_path) as image:
        assert image.size == CARD_SIZE


def test_yoto_card_engine_v4_supports_placeholder_artwork_with_clean_layout(tmp_path: Path) -> None:
    engine = YotoCardEngineV4(tmp_path)
    result = engine.render_card(
        {
            'title': 'Mystery Weekly Free Drop',
            'platform': 'EPIC',
            'type': YotoCardType.FREE_GAME,
            'deadline': 'забрати до 12 березня, 18:00',
            'old_price': '699 грн',
            'artwork_path': tmp_path / 'missing.png',
            'slug': 'missing_artwork_partial_price',
        }
    )

    assert result.diagnostics.used_placeholder_artwork is True
    assert result.diagnostics.text_payload['placeholder_caption_mode'] == 'headline_only'
    assert result.diagnostics.text_payload['primary_signal'] == UA_FREE
    assert result.diagnostics.text_payload['composition_mode'].startswith('clean_mvp_free_game_')

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
            'deadline': 'до 18 березня, 20:00',
            'artwork_path': artwork_path,
            'slug': 'steam_strategy_fest',
            'platform_badge': 'LIVE EVENT',
            'editorial_phrase': 'Season spotlight',
        }
    )

    assert result.diagnostics.text_payload['platform_badge_rendered'] is True
    assert result.diagnostics.platform_badge_text == 'LIVE EVENT'
    assert result.diagnostics.text_payload['composition_mode'].startswith('clean_mvp_festival_')

    with Image.open(result.image_path) as image:
        assert image.size == CARD_SIZE
