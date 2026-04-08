from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from infrastructure.render.cards.image_providers.base import ImageResolutionRequest, ResolvedImage
from infrastructure.render.cards.image_providers.resolver import YotoImageResolver
from infrastructure.render.cards.yoto_card_engine_v4 import BOLD_FONT_CANDIDATES, YotoCardData, YotoCardDiagnostics, YotoCardEngineV4, YotoCardType


CARD_SIZE = (1280, 720)
UA_FREE = "БЕЗКОШТОВНО"
UA_EVENT = "ПОДІЯ"
UA_DISCOUNT = "ЗНИЖКА"


def _mojibake(value: str) -> str:
    return value.encode('utf-8').decode('latin1')

def _make_art(path: Path) -> None:
    image = Image.new('RGB', (1600, 900), '#5947b5')
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 540, 1600, 900), fill='#20192f')
    draw.ellipse((90, 120, 650, 760), fill='#2db2d2')
    draw.ellipse((720, 80, 1500, 860), fill='#ef8f47')
    draw.rounded_rectangle((300, 260, 1210, 700), radius=48, outline='#ffffff', width=8)
    draw.text((520, 390), 'TEST HERO', fill='#ffffff')
    image.save(path)


def test_yoto_card_engine_v4_renders_deterministically(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'art.png'
    _make_art(artwork_path)
    engine = YotoCardEngineV4(tmp_path)
    game_data = {
        'title': 'Turnip Boy Robs a Bank',
        'platform': 'EPIC',
        'type': YotoCardType.FREE_GAME,
        'deadline': 'забрати до 12 березня, 18:00',
        'old_price': '699 грн',
        'artwork_path': artwork_path,
        'slug': 'turnip_boy_robs_a_bank',
    }

    first = engine.render_card(game_data)
    first_bytes = first.image_path.read_bytes()
    second = engine.render_card(game_data)

    assert first.image_path.name == 'yoto_card_turnip_boy_robs_a_bank.png'
    assert first_bytes == second.image_path.read_bytes()
    assert first.diagnostics.platform_badge_text == 'EPIC РОЗДАЧА'
    assert first.diagnostics.sticker_header == 'РОЗДАЧА'
    assert first.diagnostics.text_payload['platform_badge'] == 'EPIC РОЗДАЧА'
    assert first.diagnostics.sticker_text == UA_FREE
    assert first.diagnostics.title_mode == 'single_line'
    assert len(first.diagnostics.title_lines) == 1

    with Image.open(first.image_path) as image:
        assert image.size == CARD_SIZE


def test_yoto_card_engine_v4_supports_festival_variant_metadata(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'festival.png'
    _make_art(artwork_path)
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

    assert result.diagnostics.platform_badge_text == 'LIVE EVENT'
    assert result.diagnostics.sticker_header == 'ПОДІЯ'
    assert result.diagnostics.sticker_text == UA_EVENT
    assert result.diagnostics.text_payload['typography_system'] == 'role_based_segoe_v2'
    assert result.diagnostics.text_payload['finish_system'] == 'premium_finish_v2'
    assert result.diagnostics.text_payload['composition_mode'].startswith('festival_system_')
    assert result.diagnostics.text_payload['title_shelf'] == 'suppressed'
    assert result.diagnostics.text_payload['meta_secondary_label'] == 'LIVE EVENT'
    assert result.diagnostics.meta_alignment == 'editorial_row'
    assert result.diagnostics.font_selection['title']['font_family'] == 'segoeuib.ttf'
    assert result.diagnostics.font_selection['deadline']['font_family'] == 'segoeuib.ttf'
    with Image.open(result.image_path) as image:
        assert image.size == CARD_SIZE


def test_yoto_card_engine_v4_supports_top_list_typography_metadata(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'top_list.png'
    _make_art(artwork_path)
    engine = YotoCardEngineV4(tmp_path)
    result = engine.render_card(
        {
            'title': 'Big Discount Highlights',
            'platform': 'STEAM',
            'type': YotoCardType.TOP_LIST,
            'artwork_path': artwork_path,
            'slug': 'big_discount_highlights',
            'platform_badge': 'STEAM TOP',
            'sticker_header': 'TOP LIST',
            'sticker_text': 'Top 5',
            'brand_micro_label': 'вибір редакції',
            'list_label': 'Big discounts',
            'editorial_phrase': 'Editorial picks',
        }
    )

    assert result.diagnostics.platform_badge_text == 'STEAM TOP'
    assert result.diagnostics.text_payload['typography_system'] == 'role_based_segoe_v2'
    assert result.diagnostics.text_payload['finish_system'] == 'premium_finish_v2'
    assert result.diagnostics.text_payload['composition_mode'].startswith('top_list_system_')
    assert result.diagnostics.text_payload['panel_kicker'] == 'BIG DISCOUNTS'
    assert result.diagnostics.text_payload['title_shelf'] == 'suppressed'
    assert result.diagnostics.text_payload['meta_primary_label'] == 'TOP 5'
    assert result.diagnostics.text_payload['meta_secondary_label'] == 'Editorial picks'
    assert result.diagnostics.meta_alignment == 'editorial_row'
    assert result.diagnostics.font_selection['title']['font_family'] == 'segoeuib.ttf'
    assert result.diagnostics.font_selection['brand_micro']['font_family'] == 'segoeui.ttf'
    assert result.diagnostics.font_selection['meta_primary']['font_family'] == 'segoeuib.ttf'
    with Image.open(result.image_path) as image:
        assert image.size == CARD_SIZE


def test_yoto_card_engine_v4_keeps_short_top_list_badge_signal_on_one_line(tmp_path: Path) -> None:
    engine = YotoCardEngineV4(tmp_path)
    diagnostics = YotoCardDiagnostics(
        slug='top_list_badge_single_line',
        card_type=YotoCardType.TOP_LIST.value,
        platform_badge_text='STEAM TOP',
        sticker_header='TOP LIST',
        sticker_text='Top 3',
    )
    diagnostics.text_payload = {'badge_main': 'Top 3'}
    profile = engine._badge_visual_profile(
        YotoCardData.from_mapping(
            {
                'title': 'Roundup Highlights',
                'platform': 'STEAM',
                'type': YotoCardType.TOP_LIST,
                'sticker_text': 'Top 3',
            }
        ),
        diagnostics,
        YotoCardType.TOP_LIST,
    )
    draw = ImageDraw.Draw(Image.new('RGB', (1, 1), '#000000'))
    role = engine._typography_role('badge_main')
    layout = engine._fit_text_block(
        draw,
        'Top 3',
        candidates=role.candidates,
        font_sizes=profile['main_font_sizes'],
        max_width=profile['badge_width'] - 60,
        max_lines=1,
        prefer_multiline=False,
    )

    assert profile['badge_width'] >= 180
    assert layout.lines == ['Top 3']

def test_yoto_card_engine_v4_supports_discount_variant_metadata(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'discount.png'
    _make_art(artwork_path)
    engine = YotoCardEngineV4(tmp_path)
    result = engine.render_card(
        {
            'title': 'Slay the Spire',
            'platform': 'STEAM',
            'type': YotoCardType.DISCOUNT,
            'deadline': 'до 18 березня, 20:00',
            'old_price': '525 грн',
            'current_price': '-75%',
            'artwork_path': artwork_path,
            'slug': 'slay_the_spire',
        }
    )

    assert result.diagnostics.platform_badge_text == 'STEAM'
    assert result.diagnostics.sticker_header == 'STEAM SALE'
    assert result.diagnostics.sticker_text == UA_DISCOUNT
    badge_main, badge_footer = engine._badge_copy(
        YotoCardData.from_mapping(
            {
                'title': 'Slay the Spire',
                'platform': 'STEAM',
                'type': YotoCardType.DISCOUNT,
                'deadline': 'до 18 березня, 20:00',
                'current_price': '-75%',
                'artwork_path': artwork_path,
            }
        ),
        result.diagnostics,
        YotoCardType.DISCOUNT,
    )
    assert badge_main == UA_DISCOUNT
    assert badge_footer == 'до 18 березня, 20:00'
    assert result.diagnostics.meta_alignment == 'pill_row'
    assert result.diagnostics.text_payload['meta_current_signal'] == '-75%'
    assert result.diagnostics.text_payload['badge_main'] == UA_DISCOUNT
    assert result.diagnostics.text_payload['badge_main'] != result.diagnostics.text_payload['meta_current_signal']
    assert 'meta_deadline' in result.diagnostics.text_payload
    assert 'meta_old_price' in result.diagnostics.text_payload
    with Image.open(result.image_path) as image:
        assert image.size == CARD_SIZE


def test_yoto_card_engine_v4_uses_two_line_layout_for_long_titles(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'long.png'
    _make_art(artwork_path)
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

    assert result.diagnostics.title_mode == 'two_line'
    assert len(result.diagnostics.title_lines) == 2
    with Image.open(result.image_path) as image:
        assert image.size == CARD_SIZE


def test_yoto_card_engine_v4_discount_badge_falls_back_to_limited_sale_without_deadline(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'limited_sale.png'
    _make_art(artwork_path)
    engine = YotoCardEngineV4(tmp_path)
    data = YotoCardData.from_mapping(
        {
            'title': 'Dead Space',
            'platform': 'STEAM',
            'type': YotoCardType.DISCOUNT,
            'current_price': '-70%',
            'artwork_path': artwork_path,
            'slug': 'dead_space_limited_sale',
        }
    )
    result = engine.render_card(data)

    badge_main, badge_footer = engine._badge_copy(data, result.diagnostics, YotoCardType.DISCOUNT)

    assert result.diagnostics.sticker_header == 'STEAM SALE'
    assert badge_main == UA_DISCOUNT
    assert badge_footer == 'SALE ENDS SOON'


def test_yoto_card_engine_v4_compacts_discount_top_zone_for_logo_heavy_sale_art(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'discount_logo.png'
    _make_art(artwork_path)
    engine = YotoCardEngineV4(tmp_path)
    result = engine.render_card(
        {
            'title': 'Deep Rock Galactic',
            'platform': 'STEAM',
            'type': YotoCardType.DISCOUNT,
            'deadline': '\u0434\u043e 18 \u0431\u0435\u0440\u0435\u0437\u043d\u044f, 20:00',
            'old_price': '379 \u0433\u0440\u043d',
            'current_price': '-70%',
            'artwork_path': artwork_path,
            'slug': 'deep_rock_galactic_discount_compact',
            'hero_selection': {
                'selected_source': 'screenshot',
                'reason': 'selected_gameplay_screenshot',
                'candidates_evaluated': 1,
                'rejected_capsules': [],
                'score_summary': [
                    {
                        'asset_url': 'https://example.com/deep_rock_galactic_logo.png',
                        'source_type': 'screenshot',
                        'source_types': ['hero', 'screenshot'],
                        'selected': True,
                        'text_coverage_ratio': 0.44,
                        'horizontal_text_block': False,
                        'promotional_layout': False,
                    }
                ],
                'fallback_used': False,
            },
        }
    )

    assert result.diagnostics.platform_badge_text == 'STEAM'
    assert result.diagnostics.text_payload['platform_badge_compact_source'].startswith('STEAM')
    assert result.diagnostics.text_payload['top_zone_layout_mode'].startswith('discount_signal_compact_')
    assert result.diagnostics.text_payload['composition_mode'].startswith('discount_system_logo_')
    assert result.diagnostics.meta_alignment == 'pill_row'
    assert result.diagnostics.text_payload['badge_main'] == UA_DISCOUNT
    assert result.diagnostics.text_payload['badge_main'] != result.diagnostics.text_payload['meta_current_signal']


def test_yoto_card_engine_v4_moves_discount_badge_to_shoulder_when_top_right_is_busy(tmp_path: Path) -> None:
    engine = YotoCardEngineV4(tmp_path)
    hero = Image.new('RGB', (1280, 468), '#14171c')
    draw = ImageDraw.Draw(hero)
    draw.rectangle((736, 0, 1280, 214), fill='#fbf2e4')
    draw.rectangle((700, 30, 1260, 184), fill='#fff2da')
    draw.rectangle((0, 0, 280, 220), fill='#0c1117')

    data = YotoCardData.from_mapping(
        {
            'title': 'Need for Speed Heat',
            'platform': 'STEAM',
            'type': YotoCardType.DISCOUNT,
            'deadline': '\u0434\u043e 18 \u0431\u0435\u0440\u0435\u0437\u043d\u044f, 20:00',
            'old_price': '1999 \u0433\u0440\u043d',
            'current_price': '-95%',
            'artwork_path': tmp_path / 'discount_policy.png',
            'slug': 'discount_top_zone_policy',
        }
    )
    diagnostics = YotoCardDiagnostics(
        slug='discount_top_zone_policy',
        card_type=YotoCardType.DISCOUNT.value,
        platform_badge_text='STEAM \u0417\u041d\u0418\u0416\u041a\u0410',
        sticker_header='STEAM SALE',
        sticker_text=UA_DISCOUNT,
    )
    diagnostics.text_payload = {
        'platform_badge': 'STEAM \u0417\u041d\u0418\u0416\u041a\u0410',
        'sticker_header': 'STEAM SALE',
        'sticker_text': UA_DISCOUNT,
    }
    diagnostics.hero_score_summary = [
        {
            'asset_url': 'https://example.com/discount_logo.png',
            'selected': True,
            'text_coverage_ratio': 0.45,
            'horizontal_text_block': False,
            'promotional_layout': False,
        }
    ]

    layout = engine._top_zone_layout_profile(hero, data, diagnostics, YotoCardType.DISCOUNT)

    assert layout['layout_mode'].startswith('discount_signal_compact_')
    assert layout['badge_anchor'] in {'top_right', 'top_inset', 'right_shoulder'}
    assert layout['platform_badge_overrides']['display_text'] == 'STEAM'
    assert int(layout['badge_overrides']['badge_width']) < 232
    assert int(layout['badge_overrides']['badge_y']) <= 100


def test_yoto_card_engine_v4_applies_cohesive_discount_composition_modes(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'discount_composition.png'
    _make_art(artwork_path)
    engine = YotoCardEngineV4(tmp_path)

    logo_result = engine.render_card(
        {
            'title': 'Need for Speed Heat',
            'platform': 'STEAM',
            'type': YotoCardType.DISCOUNT,
            'deadline': '\u0434\u043e 18 \u0431\u0435\u0440\u0435\u0437\u043d\u044f, 20:00',
            'old_price': '1999 \u0433\u0440\u043d',
            'current_price': '-95%',
            'artwork_path': artwork_path,
            'slug': 'need_for_speed_heat_composition_mode',
            'hero_selection': {
                'selected_source': 'screenshot',
                'reason': 'selected_gameplay_screenshot',
                'candidates_evaluated': 1,
                'rejected_capsules': [],
                'score_summary': [
                    {
                        'asset_url': 'https://example.com/nfs_heat_logo.png',
                        'source_type': 'screenshot',
                        'source_types': ['hero', 'screenshot'],
                        'selected': True,
                        'text_coverage_ratio': 0.43,
                        'horizontal_text_block': False,
                        'promotional_layout': False,
                    }
                ],
                'fallback_used': False,
            },
        }
    )
    fallback_result = engine.render_card(
        {
            'title': 'Retro Rewind Video Store Simulator Definitive Weekend Build Collection',
            'platform': 'STEAM',
            'type': YotoCardType.DISCOUNT,
            'deadline': '\u0434\u043e 22 \u0431\u0435\u0440\u0435\u0437\u043d\u044f, 19:00',
            'old_price': '390 \u0433\u0440\u043d',
            'current_price': '-20%',
            'artwork_path': tmp_path / 'missing_discount_composition.png',
            'slug': 'discount_fallback_composition_mode',
        }
    )

    assert logo_result.diagnostics.text_payload['composition_mode'].startswith('discount_system_logo_')
    assert logo_result.diagnostics.meta_alignment == 'pill_row'
    assert logo_result.diagnostics.text_payload['meta_current_signal'] == '-95%'
    assert logo_result.diagnostics.text_payload['badge_main'] == UA_DISCOUNT
    assert logo_result.diagnostics.text_payload['badge_main'] != logo_result.diagnostics.text_payload['meta_current_signal']
    assert logo_result.diagnostics.text_payload['platform_badge'] == 'STEAM'
    assert 'meta_deadline' in logo_result.diagnostics.text_payload
    assert 'meta_old_price' in logo_result.diagnostics.text_payload
    logo_profile = engine._composition_profile(
        engine._compose_hero_artwork(Image.open(artwork_path).convert('RGB')),
        YotoCardData.from_mapping(
            {
                'title': 'Need for Speed Heat',
                'platform': 'STEAM',
                'type': YotoCardType.DISCOUNT,
                'deadline': '\u0434\u043e 18 \u0431\u0435\u0440\u0435\u0437\u043d\u044f, 20:00',
                'old_price': '1999 \u0433\u0440\u043d',
                'current_price': '-95%',
                'artwork_path': artwork_path,
                'slug': 'need_for_speed_heat_composition_mode',
            }
        ),
        logo_result.diagnostics,
        YotoCardType.DISCOUNT,
    )
    assert tuple(logo_profile['panel']['row_rect'])[1] >= 658
    assert int(logo_profile['meta']['chip_height']) == 36
    assert logo_profile['brand']['style'] == 'grid_chip'
    assert int(logo_profile['title']['halo_alpha']) > 0
    assert fallback_result.diagnostics.text_payload['composition_mode'].startswith('discount_system_fallback_')
    assert fallback_result.diagnostics.used_placeholder_artwork is True
    assert fallback_result.diagnostics.meta_alignment == 'pill_row'
    assert fallback_result.diagnostics.title_mode == 'two_line'
    assert logo_result.diagnostics.text_payload['title_shelf'] == 'suppressed'
    assert fallback_result.diagnostics.text_payload['title_shelf'] == 'fallback_soft'
    assert fallback_result.diagnostics.text_payload['placeholder_caption_mode'] == 'headline_only'


def test_yoto_card_engine_v4_handles_missing_artwork_and_centers_partial_price(tmp_path: Path) -> None:
    engine = YotoCardEngineV4(tmp_path)
    result = engine.render_card(
        {
            'title': 'Mystery Weekly Free Drop',
            'platform': 'EPIC',
            'type': YotoCardType.FREE_GAME,
            'deadline': 'забрати до 12 березня, 18:00',
            'current_price': 'ціна уточнюється',
            'artwork_path': tmp_path / 'missing.png',
            'slug': 'missing_artwork_partial_price',
        }
    )

    assert result.diagnostics.used_placeholder_artwork is True
    assert result.diagnostics.meta_alignment == 'centered'
    assert result.diagnostics.hero_source_type == 'placeholder'
    assert result.diagnostics.text_payload['placeholder_caption_mode'] == 'headline_only'
    assert result.diagnostics.hero_selection_reason == 'intentional_fallback'
    assert result.diagnostics.hero_fallback_used is True
    assert result.diagnostics.hero_selection['fallback_used'] is True
    with Image.open(result.image_path) as image:
        assert image.size == CARD_SIZE



def test_yoto_card_engine_v4_compacts_free_placeholder_platform_badge(tmp_path: Path) -> None:
    engine = YotoCardEngineV4(tmp_path)
    result = engine.render_card(
        {
            'title': 'Fallback Freebie Case',
            'platform': 'EPIC',
            'type': YotoCardType.FREE_GAME,
            'deadline': '?????????????? ???? 19 ??????????????, 15:00',
            'old_price': '229 ??????',
            'artwork_path': tmp_path / 'missing_free_platform_badge.png',
            'slug': 'fallback_free_platform_badge',
        }
    )

    assert result.diagnostics.used_placeholder_artwork is True
    assert result.diagnostics.platform_badge_text == 'EPIC'
    assert result.diagnostics.text_payload['platform_badge_compact_source'].startswith('EPIC')
    assert result.diagnostics.text_payload['platform_badge_compact_source'] != result.diagnostics.platform_badge_text
    assert result.diagnostics.text_payload['placeholder_caption_mode'] == 'headline_only'
    assert result.diagnostics.text_payload['title_shelf'] == 'fallback_soft'

def test_yoto_card_engine_v4_placeholder_long_titles_use_compact_hierarchy(tmp_path: Path) -> None:
    engine = YotoCardEngineV4(tmp_path)
    probe = ImageDraw.Draw(Image.new('RGB', CARD_SIZE, '#000000'))

    short_layout, short_style = engine._resolve_placeholder_title_layout(
        probe,
        'Isonzo',
        panel_width=640,
        panel_height=254,
    )
    long_layout, long_style = engine._resolve_placeholder_title_layout(
        probe,
        'Turnip Boy Robs a Bank',
        panel_width=680,
        panel_height=286,
    )

    assert short_style['mode'] == 'standard'
    assert long_style['mode'] == 'compact'
    assert len(long_layout.lines) >= 2
    assert long_style['text_alpha'] < short_style['text_alpha']
    assert long_style['line_gap'] < short_style['line_gap']
    assert long_layout.line_height <= short_layout.line_height

def test_yoto_card_engine_v4_placeholder_artwork_varies_by_metadata(tmp_path: Path) -> None:
    engine = YotoCardEngineV4(tmp_path)
    first = engine.render_card(
        {
            'title': 'Isonzo',
            'platform': 'EPIC',
            'type': YotoCardType.FREE_GAME,
            'deadline': 'забрати до 19 березня, 18:00',
            'old_price': '699 грн',
            'artwork_path': tmp_path / 'missing_isonzo.png',
            'slug': 'isonzo',
        }
    )
    second = engine.render_card(
        {
            'title': 'Idle Champions of the Forgotten Realms',
            'platform': 'EPIC',
            'type': YotoCardType.FREE_GAME,
            'deadline': 'забрати до 20 березня, 18:00',
            'old_price': '519 грн',
            'artwork_path': tmp_path / 'missing_turnip.png',
            'slug': 'turnip_boy_robs_a_bank',
        }
    )

    with Image.open(first.image_path) as first_image, Image.open(second.image_path) as second_image:
        first_hero = first_image.crop((72, 64, 1208, 412))
        second_hero = second_image.crop((72, 64, 1208, 412))

    assert first.diagnostics.used_placeholder_artwork is True
    assert second.diagnostics.used_placeholder_artwork is True
    assert first_hero.tobytes() != second_hero.tobytes()

def test_yoto_card_engine_v4_preserves_hero_selection_diagnostics_payload(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'diagnostic_hero.png'
    _make_art(artwork_path)
    engine = YotoCardEngineV4(tmp_path)
    result = engine.render_card(
        {
            'title': 'Diagnostic Hero Case',
            'platform': 'STEAM',
            'type': YotoCardType.DISCOUNT,
            'deadline': 'до 20 березня, 20:00',
            'artwork_path': artwork_path,
            'slug': 'diagnostic_hero_case',
            'hero_selection': {
                'selected_source': 'screenshot',
                'reason': 'capsule_rejected_text_heavy',
                'candidates_evaluated': 4,
                'rejected_capsules': [
                    {
                        'asset_url': 'https://example.com/capsule_231x87.jpg',
                        'source_type': 'hero',
                        'score': -12.5,
                        'reason': 'capsule_rejected_text_heavy',
                    }
                ],
                'score_summary': [
                    {
                        'asset_url': 'https://example.com/shot.png',
                        'source_type': 'screenshot',
                        'available': True,
                        'score': 118.0,
                        'selected': True,
                        'rejection_reason': None,
                        'meets_hero_floor': True,
                    }
                ],
                'fallback_used': False,
            },
        }
    )

    assert result.diagnostics.hero_source_type == 'screenshot'
    assert result.diagnostics.hero_selection_reason == 'capsule_rejected_text_heavy'
    assert result.diagnostics.hero_candidates_count == 4
    assert result.diagnostics.hero_fallback_used is False
    assert result.diagnostics.hero_rejected_capsules
    assert result.diagnostics.hero_selection['selected_source'] == 'screenshot'
    assert result.diagnostics.hero_selection['reason'] == 'capsule_rejected_text_heavy'


def test_yoto_card_engine_v4_repairs_mojibake_badge_payloads(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'mojibake.png'
    _make_art(artwork_path)
    engine = YotoCardEngineV4(tmp_path)
    result = engine.render_card(
        {
            'title': 'Repair Payload Case',
            'platform': 'STEAM',
            'type': YotoCardType.DISCOUNT,
            'platform_badge': f"STEAM {_mojibake('ЗНИЖКА')}",
            'sticker_header': _mojibake('ЗНИЖКА'),
            'sticker_text': _mojibake('ЗНИЖКА'),
            'deadline': _mojibake('до 18 березня, 20:00'),
            'old_price': '525 грн',
            'current_price': '-75%',
            'artwork_path': artwork_path,
            'slug': 'repair_payload_case',
        }
    )

    assert result.diagnostics.platform_badge_text == 'STEAM'
    assert result.diagnostics.sticker_header == '\u0417\u041d\u0418\u0416\u041a\u0410'
    assert '????' not in result.diagnostics.platform_badge_text


def test_yoto_card_engine_v4_uses_font_fallback_for_cyrillic_when_primary_font_lacks_glyphs(tmp_path: Path) -> None:
    engine = YotoCardEngineV4(tmp_path)
    diagnostics = YotoCardDiagnostics(
        slug='font_fallback_case',
        card_type=YotoCardType.DISCOUNT.value,
        platform_badge_text='STEAM \u0417\u041d\u0418\u0416\u041a\u0410',
        sticker_header='\u0417\u041d\u0418\u0416\u041a\u0410',
        sticker_text=UA_DISCOUNT,
    )

    primary = engine._load_named_font('arialbd.ttf', 24)
    fallback = engine._load_named_font('segoeuib.ttf', 24)
    assert primary is not None and fallback is not None

    original_load_named_font = engine._load_named_font

    def fake_load_named_font(name: str, size: int):
        if size != 24:
            return original_load_named_font(name, size)
        if name == 'Inter-Bold.ttf':
            return primary
        if name == 'arialbd.ttf':
            return fallback
        return None

    def fake_font_supports_text(font, text: str) -> bool:
        return font is not primary

    engine._load_named_font = fake_load_named_font  # type: ignore[method-assign]
    engine._font_supports_text = fake_font_supports_text  # type: ignore[method-assign]

    chosen = engine._load_font_for_text(24, ('Inter-Bold.ttf', 'arialbd.ttf'), '\u041f\u041e\u0414\u0406\u042f', diagnostics=diagnostics, layer='badge_header')

    assert chosen is fallback
    assert diagnostics.glyph_fallback_used is True
    assert diagnostics.font_selection['badge_header']['fallback_used'] is True

def test_yoto_card_engine_v4_fits_long_sticker_copy_into_available_space(tmp_path: Path) -> None:
    engine = YotoCardEngineV4(tmp_path)
    draw = ImageDraw.Draw(Image.new('RGB', (1, 1), '#000000'))

    english_layout = engine._fit_text_block(
        draw,
        'LIMITED FREE CLAIM',
        candidates=BOLD_FONT_CANDIDATES,
        font_sizes=range(48, 23, -2),
        max_width=304,
        max_lines=2,
        prefer_multiline=True,
    )
    cyrillic_layout = engine._fit_text_block(
        draw,
        UA_FREE,
        candidates=BOLD_FONT_CANDIDATES,
        font_sizes=range(42, 23, -2),
        max_width=316,
        max_lines=2,
        prefer_multiline=False,
    )

    assert len(english_layout.lines) == 2
    assert ' '.join(english_layout.lines) == 'LIMITED FREE CLAIM'
    assert all(draw.textlength(line, font=english_layout.font) <= 304 for line in english_layout.lines)
    assert ''.join(cyrillic_layout.lines) == UA_FREE
    assert all(draw.textlength(line, font=cyrillic_layout.font) <= 316 for line in cyrillic_layout.lines)




def test_yoto_card_engine_v4_softens_epic_free_badge_when_hero_logo_is_prominent(tmp_path: Path) -> None:
    engine = YotoCardEngineV4(tmp_path)
    data = YotoCardData.from_mapping(
        {
            'title': 'Cozy Grove',
            'platform': 'EPIC',
            'type': YotoCardType.FREE_GAME,
            'deadline': '??????? ?? 19 ???????, 15:00',
            'old_price': '229 ???',
            'artwork_path': tmp_path / 'cozy_logo.png',
            'slug': 'cozy_grove_badge_profile',
        }
    )
    diagnostics = YotoCardDiagnostics(
        slug='cozy_grove_badge_profile',
        card_type=YotoCardType.FREE_GAME.value,
        platform_badge_text='EPIC ???????',
        sticker_header='???????',
        sticker_text='???????????',
    )
    diagnostics.text_payload = {'badge_main': '???????????'}
    diagnostics.hero_score_summary = [
        {
            'asset_url': 'https://example.com/cozy_grove_logo.png',
            'selected': True,
            'text_coverage_ratio': 0.51,
            'horizontal_text_block': False,
            'promotional_layout': False,
        }
    ]

    profile = engine._badge_visual_profile(data, diagnostics, YotoCardType.FREE_GAME)

    assert profile['cache_tag'] == 'epic_logo_soft'
    assert profile['badge_width'] < 356
    assert profile['glow_alpha'] < 38
    assert profile['main_shadow_alpha'] < 96


def test_yoto_card_engine_v4_moves_epic_free_badge_to_shoulder_when_top_right_logo_zone_is_busy(tmp_path: Path) -> None:
    engine = YotoCardEngineV4(tmp_path)
    hero = Image.new('RGB', (1280, 468), '#10161f')
    draw = ImageDraw.Draw(hero)
    draw.rectangle((760, 0, 1280, 210), fill='#f8fbff')
    draw.rectangle((720, 34, 1260, 168), fill='#ffffff')
    draw.rectangle((0, 0, 280, 220), fill='#0a1118')

    data = YotoCardData.from_mapping(
        {
            'title': 'Cozy Grove',
            'platform': 'EPIC',
            'type': YotoCardType.FREE_GAME,
            'deadline': '??????? ?? 19 ???????, 15:00',
            'old_price': '229 ???',
            'artwork_path': tmp_path / 'cozy_grove_policy.png',
            'slug': 'cozy_grove_top_zone_policy',
        }
    )
    diagnostics = YotoCardDiagnostics(
        slug='cozy_grove_top_zone_policy',
        card_type=YotoCardType.FREE_GAME.value,
        platform_badge_text='EPIC ???????',
        sticker_header='???????',
        sticker_text='???????????',
    )
    diagnostics.text_payload = {
        'platform_badge': 'EPIC ???????',
        'sticker_header': '???????',
        'sticker_text': '???????????',
    }
    diagnostics.hero_score_summary = [
        {
            'asset_url': 'https://example.com/cozy_grove_logo.png',
            'selected': True,
            'text_coverage_ratio': 0.51,
            'horizontal_text_block': False,
            'promotional_layout': False,
        }
    ]

    layout = engine._top_zone_layout_profile(hero, data, diagnostics, YotoCardType.FREE_GAME)

    assert layout['layout_mode'].startswith('epic_logo_balanced_')
    assert layout['badge_anchor'] == 'right_shoulder'
    assert layout['badge_overrides']['badge_y'] > 100


def test_yoto_card_engine_v4_compacts_platform_badge_for_logo_heavy_epic_free(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'cozy_logo_platform_badge.png'
    _make_art(artwork_path)
    engine = YotoCardEngineV4(tmp_path)
    result = engine.render_card(
        {
            'title': 'Cozy Grove',
            'platform': 'EPIC',
            'type': YotoCardType.FREE_GAME,
            'deadline': '??????? ?? 19 ???????, 15:00',
            'old_price': '229 ???',
            'artwork_path': artwork_path,
            'slug': 'cozy_grove_platform_badge_compact',
            'hero_selection': {
                'selected_source': 'screenshot',
                'reason': 'selected_gameplay_screenshot',
                'candidates_evaluated': 1,
                'rejected_capsules': [],
                'score_summary': [
                    {
                        'asset_url': 'https://example.com/cozy_grove_logo.png',
                        'source_type': 'screenshot',
                        'source_types': ['hero', 'screenshot'],
                        'selected': True,
                        'text_coverage_ratio': 0.51,
                        'horizontal_text_block': False,
                        'promotional_layout': False,
                    }
                ],
                'fallback_used': False,
            },
        }
    )

    assert result.diagnostics.platform_badge_text == 'EPIC'
    assert result.diagnostics.text_payload['platform_badge'] == 'EPIC'
    assert result.diagnostics.text_payload['platform_badge_compact_source'].startswith('EPIC')




def test_yoto_card_engine_v4_applies_cohesive_epic_free_composition_modes(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'cozy_logo_composition.png'
    _make_art(artwork_path)
    engine = YotoCardEngineV4(tmp_path)

    logo_result = engine.render_card(
        {
            'title': 'Cozy Grove',
            'platform': 'EPIC',
            'type': YotoCardType.FREE_GAME,
            'deadline': 'забрати до 19 березня, 15:00',
            'old_price': '229 грн',
            'artwork_path': artwork_path,
            'slug': 'cozy_grove_composition_mode',
            'hero_selection': {
                'selected_source': 'screenshot',
                'reason': 'selected_gameplay_screenshot',
                'candidates_evaluated': 1,
                'rejected_capsules': [],
                'score_summary': [
                    {
                        'asset_url': 'https://example.com/cozy_grove_logo.png',
                        'source_type': 'screenshot',
                        'source_types': ['hero', 'screenshot'],
                        'selected': True,
                        'text_coverage_ratio': 0.51,
                        'horizontal_text_block': False,
                        'promotional_layout': False,
                    }
                ],
                'fallback_used': False,
            },
        }
    )
    fallback_result = engine.render_card(
        {
            'title': 'Turnip Boy Robs a Bank',
            'platform': 'EPIC',
            'type': YotoCardType.FREE_GAME,
            'deadline': 'забрати до 20 березня, 18:00',
            'old_price': '519 грн',
            'artwork_path': tmp_path / 'missing_idle_composition.png',
            'slug': 'idle_champions_composition_mode',
        }
    )

    assert logo_result.diagnostics.text_payload['composition_mode'].startswith('epic_free_system_logo_')
    assert logo_result.diagnostics.text_payload['top_zone_layout_mode'].startswith('epic_logo_balanced_')
    assert logo_result.diagnostics.meta_alignment == 'pill_row'
    assert fallback_result.diagnostics.text_payload['composition_mode'].startswith('epic_free_system_fallback_')
    assert fallback_result.diagnostics.meta_alignment == 'pill_row'
    assert fallback_result.diagnostics.title_lines

def test_yoto_card_engine_v4_suppresses_logo_redundant_gameplay_strip_for_epic_free(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'cozy_logo.png'
    _make_art(artwork_path)
    engine = YotoCardEngineV4(tmp_path)
    result = engine.render_card(
        {
            'title': 'Cozy Grove',
            'platform': 'EPIC',
            'type': YotoCardType.FREE_GAME,
            'deadline': '??????? ?? 19 ???????, 15:00',
            'old_price': '229 ???',
            'artwork_path': artwork_path,
            'slug': 'cozy_grove_logo_redundancy',
            'gameplay_images': [artwork_path],
            'hero_selection': {
                'selected_source': 'screenshot',
                'reason': 'selected_gameplay_screenshot',
                'candidates_evaluated': 1,
                'rejected_capsules': [],
                'score_summary': [
                    {
                        'asset_url': 'https://example.com/cozy_grove_logo.png',
                        'source_type': 'screenshot',
                        'source_types': ['hero', 'screenshot'],
                        'selected': True,
                        'text_coverage_ratio': 0.51,
                        'horizontal_text_block': False,
                        'promotional_layout': False,
                    }
                ],
                'fallback_used': False,
            },
            'gameplay_selection': {
                'reason': 'selected_primary_frame_fallback',
                'candidates_evaluated': 1,
                'selected_count': 1,
                'selected_urls': ['https://example.com/cozy_grove_logo.png'],
                'ui_like_rejected': 0,
                'score_summary': [
                    {
                        'asset_url': 'https://example.com/cozy_grove_logo.png',
                        'source_type': 'screenshot',
                        'source_types': ['primary_screenshot'],
                        'selected': True,
                        'ui_like': False,
                        'ui_relaxed_candidate': False,
                        'text_heavy': False,
                        'low_info': False,
                        'steam_ui_like': False,
                        'banner_like': False,
                        'horizontal_text_block': False,
                        'promotional_layout': False,
                        'aspect_mismatched': False,
                        'similar_scene': False,
                        'text_coverage_ratio': 0.51,
                        'scene_richness_score': 0.62,
                        'meets_gameplay_floor': True,
                        'index': 0,
                    }
                ],
            },
        }
    )

    assert result.diagnostics.has_gameplay_strip is False
    assert result.diagnostics.gameplay_count == 0
    assert result.diagnostics.gameplay_selected_count == 1
    assert result.diagnostics.gameplay_selection_reason == 'suppressed_logo_redundancy'
    assert result.diagnostics.gameplay_selection['suppressed'] is True


def test_yoto_card_engine_v4_renders_gameplay_strip_when_frames_are_supplied(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'hero.png'
    _make_art(artwork_path)
    gameplay_paths = []
    for index in range(3):
        frame_path = tmp_path / f'frame_{index}.png'
        _make_art(frame_path)
        gameplay_paths.append(frame_path)

    engine = YotoCardEngineV4(tmp_path)
    result = engine.render_card(
        {
            'title': 'Turnip Boy Robs a Bank',
            'platform': 'EPIC',
            'type': YotoCardType.FREE_GAME,
            'deadline': 'забрати до 12 березня, 18:00',
            'old_price': '699 грн',
            'artwork_path': artwork_path,
            'slug': 'turnip_boy_with_gameplay_strip',
            'gameplay_images': gameplay_paths,
        }
    )

    assert result.diagnostics.has_gameplay_strip is True
    assert result.diagnostics.gameplay_count == 3
    assert result.diagnostics.gameplay_candidates_count == 3
    assert result.diagnostics.gameplay_selected_count == 3
    assert result.diagnostics.gameplay_selection_reason == 'selected_supplied_frames'
    assert result.diagnostics.gameplay_selection['selected_urls'] == [str(item) for item in gameplay_paths]
    with Image.open(result.image_path) as image:
        assert image.size == CARD_SIZE



def test_yoto_card_engine_v4_preserves_editorial_phrase_metadata(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'editorial.png'
    _make_art(artwork_path)
    engine = YotoCardEngineV4(tmp_path)
    result = engine.render_card(
        {
            'title': 'Helldivers 2',
            'platform': 'STEAM',
            'type': YotoCardType.DISCOUNT,
            'deadline': 'до 18 березня, 20:00',
            'old_price': '999 грн',
            'current_price': '-20%',
            'artwork_path': artwork_path,
            'slug': 'helldivers_2_editorial',
            'editorial_phrase': 'Co-op favorite',
        }
    )

    assert result.diagnostics.editorial_phrase == 'Co-op favorite'
    with Image.open(result.image_path) as image:
        assert image.size == CARD_SIZE


def test_yoto_card_engine_v4_ignores_invalid_editorial_phrase(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'editorial_invalid.png'
    _make_art(artwork_path)
    engine = YotoCardEngineV4(tmp_path)
    result = engine.render_card(
        {
            'title': 'Editorial Guardrail Case',
            'platform': 'STEAM',
            'type': YotoCardType.DISCOUNT,
            'deadline': 'до 18 березня, 20:00',
            'old_price': '999 грн',
            'current_price': '-20%',
            'artwork_path': artwork_path,
            'slug': 'editorial_guardrail_case',
            'editorial_phrase': 'this phrase is far too long',
        }
    )

    assert result.diagnostics.editorial_phrase is None



def test_yoto_card_engine_v4_compacts_festival_top_zone_for_logo_heavy_event_art(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'festival_compact.png'
    _make_art(artwork_path)
    engine = YotoCardEngineV4(tmp_path)
    result = engine.render_card(
        {
            'title': 'Steam Next Fest',
            'platform': 'STEAM',
            'type': YotoCardType.FESTIVAL,
            'deadline': '?? 18 ???????, 20:00',
            'artwork_path': artwork_path,
            'slug': 'festival_compact_top_zone',
            'platform_badge': 'STEAM EVENT',
            'editorial_phrase': 'Live event radar',
            'hero_selection': {
                'selected_source': 'header',
                'reason': 'selected_store_header',
                'candidates_evaluated': 1,
                'rejected_capsules': [],
                'score_summary': [
                    {
                        'asset_url': 'https://example.com/steam_next_fest_logo.png',
                        'selected': True,
                        'text_coverage_ratio': 0.48,
                        'horizontal_text_block': False,
                        'promotional_layout': False,
                    }
                ],
                'fallback_used': False,
            },
        }
    )

    assert result.diagnostics.text_payload['top_zone_layout_mode'].startswith('festival_editorial_compact_')
    assert result.diagnostics.text_payload['platform_badge'] == 'STEAM EVENT'
    assert result.diagnostics.text_payload['top_zone_scaffold_mode'].startswith('festival_')


def test_yoto_card_engine_v4_compacts_top_list_top_zone_for_logo_heavy_roundup_art(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'top_list_compact.png'
    _make_art(artwork_path)
    engine = YotoCardEngineV4(tmp_path)
    result = engine.render_card(
        {
            'title': 'Big Discount Highlights',
            'platform': 'STEAM',
            'type': YotoCardType.TOP_LIST,
            'artwork_path': artwork_path,
            'slug': 'top_list_compact_top_zone',
            'platform_badge': 'STEAM TOP',
            'sticker_header': 'TOP LIST',
            'sticker_text': 'Top 5',
            'brand_micro_label': '????? ????????',
            'list_label': 'Big discounts',
            'editorial_phrase': 'Editorial picks',
            'hero_selection': {
                'selected_source': 'header',
                'reason': 'selected_store_header',
                'candidates_evaluated': 1,
                'rejected_capsules': [],
                'score_summary': [
                    {
                        'asset_url': 'https://example.com/top_list_logo_art.png',
                        'selected': True,
                        'text_coverage_ratio': 0.46,
                        'horizontal_text_block': False,
                        'promotional_layout': False,
                    }
                ],
                'fallback_used': False,
            },
        }
    )

    assert result.diagnostics.text_payload['top_zone_layout_mode'].startswith('top_list_editorial_compact_')
    assert result.diagnostics.text_payload['platform_badge'] == 'STEAM TOP'
    assert result.diagnostics.text_payload['top_zone_scaffold_mode'].startswith('top_list_')


def test_yoto_card_engine_v4_preserves_gameplay_selection_diagnostics_payload(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'gameplay_payload_hero.png'
    _make_art(artwork_path)
    gameplay_paths = []
    for index in range(3):
        frame_path = tmp_path / f'payload_frame_{index}.png'
        _make_art(frame_path)
        gameplay_paths.append(frame_path)

    engine = YotoCardEngineV4(tmp_path)
    result = engine.render_card(
        {
            'title': 'Gameplay Diagnostics Case',
            'platform': 'STEAM',
            'type': YotoCardType.DISCOUNT,
            'deadline': 'до 20 березня, 20:00',
            'artwork_path': artwork_path,
            'slug': 'gameplay_diagnostics_case',
            'gameplay_images': gameplay_paths,
            'gameplay_selection': {
                'reason': 'selected_top_scored_frames',
                'candidates_evaluated': 5,
                'selected_count': 3,
                'selected_urls': [str(item) for item in gameplay_paths],
                'ui_like_rejected': 2,
                'score_summary': [
                    {
                        'asset_url': 'https://example.com/extras/menu.png',
                        'source_type': 'gameplay_media',
                        'available': True,
                        'score': 18.0,
                        'selected': False,
                        'rejection_reason': 'ui_like_frame',
                        'ui_like': True,
                        'low_info': False,
                        'meets_gameplay_floor': False,
                        'index': 0,
                    }
                ],
            },
        }
    )

    assert result.diagnostics.gameplay_candidates_count == 5
    assert result.diagnostics.gameplay_selected_count == 3
    assert result.diagnostics.gameplay_selection_reason == 'selected_top_scored_frames'
    assert result.diagnostics.gameplay_rejected_ui_like == 2
    assert result.diagnostics.gameplay_selection['selected_urls'] == [str(item) for item in gameplay_paths]
    assert result.diagnostics.gameplay_score_summary[0]['rejection_reason'] == 'ui_like_frame'


def test_yoto_card_engine_v4_resolver_metadata_prefers_artwork_when_available(tmp_path: Path) -> None:
    artwork_path = tmp_path / 'resolver_artwork.png'
    _make_art(artwork_path)
    engine = YotoCardEngineV4(tmp_path)

    result = engine.render_card(
        {
            'title': 'Resolver Artwork Path',
            'platform': 'STEAM',
            'type': YotoCardType.DISCOUNT,
            'artwork_path': artwork_path,
            'slug': 'resolver_artwork_path',
            'lane': 'high_value_discount',
        }
    )

    assert result.diagnostics.selected_source == 'artwork'
    assert result.diagnostics.used_placeholder_artwork is False
    assert result.diagnostics.decision_reason == 'artwork_available_mode_artwork_only'
    assert result.diagnostics.image_provider_mode == 'artwork_only'
    assert result.diagnostics.image_priority == 'HIGH'
    assert result.diagnostics.image_pipeline_version == 'v1'
    assert result.diagnostics.text_payload['selected_source'] == 'artwork'



def test_yoto_card_engine_v4_resolver_metadata_falls_back_to_placeholder(tmp_path: Path) -> None:
    engine = YotoCardEngineV4(tmp_path)

    result = engine.render_card(
        {
            'title': 'Resolver Placeholder Path',
            'platform': 'EPIC',
            'type': YotoCardType.FREE_GAME,
            'artwork_path': tmp_path / 'missing_resolver_artwork.png',
            'slug': 'resolver_placeholder_path',
            'lane': 'backlog_filler',
        }
    )

    assert result.diagnostics.selected_source == 'placeholder'
    assert result.diagnostics.used_placeholder_artwork is True
    assert result.diagnostics.decision_reason == 'placeholder_missing_artwork'
    assert result.diagnostics.image_priority == 'LOW'
    assert result.diagnostics.image_pipeline_version == 'v1'
    assert result.diagnostics.text_payload['placeholder_caption_mode'] == 'headline_only'


class _FakeProvider:
    def __init__(self, result: ResolvedImage | None, *, enabled: bool = True) -> None:
        self.result = result
        self.enabled = enabled
        self.calls = 0

    def resolve(self, request: ImageResolutionRequest) -> ResolvedImage | None:
        self.calls += 1
        return self.result


def _request(*, artwork_path: Path | None, mode: str = 'artwork_then_ai', lane: str | None = None) -> ImageResolutionRequest:
    return ImageResolutionRequest(
        artwork_path=artwork_path,
        title='AI Resolver Test',
        platform='STEAM',
        slug='ai_resolver_test',
        card_type=YotoCardType.DISCOUNT.value,
        lane=lane,
        mode=mode,
        priority='',
        image_size=CARD_SIZE,
    )


def test_yoto_image_resolver_uses_ai_when_artwork_missing_and_ai_enabled() -> None:
    ai_image = Image.new('RGB', CARD_SIZE, '#33aa55')
    resolver = YotoImageResolver(
        artwork_provider=_FakeProvider(None),
        ai_provider=_FakeProvider(ResolvedImage(image=ai_image, metadata={'selected_source': 'ai', 'provider_name': 'ai'})),
        placeholder_provider=_FakeProvider(ResolvedImage(image=Image.new('RGB', CARD_SIZE, '#111111'), metadata={'selected_source': 'placeholder'})),
        mode='artwork_then_ai',
    )

    result = resolver.resolve(_request(artwork_path=None, lane='breaking_freebie'))

    assert result.metadata['selected_source'] == 'ai'
    assert result.metadata['decision_reason'] == 'ai_generated_missing_artwork'
    assert result.metadata['priority'] == 'HIGH'
    assert result.metadata['ai_attempted'] is True
    assert result.metadata['ai_succeeded'] is True


def test_yoto_image_resolver_falls_back_to_placeholder_when_ai_fails() -> None:
    placeholder = Image.new('RGB', CARD_SIZE, '#111111')
    resolver = YotoImageResolver(
        artwork_provider=_FakeProvider(None),
        ai_provider=_FakeProvider(None),
        placeholder_provider=_FakeProvider(ResolvedImage(image=placeholder, metadata={'selected_source': 'placeholder'})),
        mode='ai_first',
    )

    result = resolver.resolve(_request(artwork_path=None, mode='ai_first', lane='backlog_filler'))

    assert result.metadata['selected_source'] == 'placeholder'
    assert result.metadata['decision_reason'] == 'placeholder_ai_failed'
    assert result.metadata['priority'] == 'LOW'
    assert result.metadata['ai_attempted'] is True
    assert result.metadata['ai_succeeded'] is False


def test_yoto_image_resolver_skips_ai_in_artwork_only_mode() -> None:
    ai_provider = _FakeProvider(ResolvedImage(image=Image.new('RGB', CARD_SIZE, '#22aa22'), metadata={'selected_source': 'ai'}))
    resolver = YotoImageResolver(
        artwork_provider=_FakeProvider(None),
        ai_provider=ai_provider,
        placeholder_provider=_FakeProvider(ResolvedImage(image=Image.new('RGB', CARD_SIZE, '#111111'), metadata={'selected_source': 'placeholder'})),
        mode='artwork_only',
    )

    result = resolver.resolve(_request(artwork_path=None, mode='artwork_only'))

    assert result.metadata['selected_source'] == 'placeholder'
    assert result.metadata['decision_reason'] == 'placeholder_missing_artwork'
    assert result.metadata['ai_attempted'] is False
    assert result.metadata['ai_succeeded'] is False
    assert ai_provider.calls == 0
