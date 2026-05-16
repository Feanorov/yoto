from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime
from types import SimpleNamespace

from application.use_cases.dry_run_render import DryRunRenderUseCase
from dealbot.utils.ua import clean_html_text, format_compact_review_count
from domain.entities.offer import AssetBundle, ConfidenceLevels, Offer, OfferKind, OfferSource
from infrastructure.telegram.caption_builder import (
    CTA_POOLS,
    DIRECT_OPENING_POOLS,
    EVENT_FOCUS_SUMMARY_TEMPLATES,
    EVENT_GENERIC_SUMMARY_TEMPLATES,
    INDIRECT_HOOK_POOLS,
    TelegramCaptionBuilder,
)


def make_offer() -> Offer:
    return Offer(
        offer_id='steam:10',
        source=OfferSource.STEAM,
        source_ref='10',
        offer_kind=OfferKind.DISCOUNT,
        game_id='10',
        franchise_key='test-game',
        title='Test Game',
        store_url='https://store.steampowered.com/app/10',
        price_before_minor=22500,
        price_after_minor=11200,
        currency='UAH',
        discount_percent=50,
        promo_start=None,
        promo_end=datetime(2026, 3, 12, 18, 0),
        review_score=89,
        review_count=1200,
        achievements_count=42,
        has_trading_cards=True,
        tags=['Action', 'Co-op'],
        genres=['Action', 'Adventure'],
        assets=AssetBundle(hero='https://example.com/header.png', header='https://example.com/header.png', screenshot='https://example.com/shot.png'),
        confidence_levels=ConfidenceLevels(),
        description='Український опис гри для тесту без обрізків.',
        short_description='Український опис гри для тесту без обрізків.',
        publisher_name='Test Publisher',
    )


def make_decision(
    *,
    lane: str = 'high_value_discount',
    template_id: str = 'steam_discount',
    is_final_push: bool = False,
    decision_reasons: list[str] | None = None,
    is_historical_best: bool = False,
    price_improved_minor: int = 0,
    previous_price_minor: int | None = None,
    previous_posted_at: str | None = None,
    best_price_minor: int | None = None,
) -> dict:
    return {
        'lane': lane,
        'template_id': template_id,
        'queue_bucket': 'planned',
        'is_final_push': is_final_push,
        'decision_reasons': list(decision_reasons or []),
        'is_historical_best': is_historical_best,
        'price_improved_minor': price_improved_minor,
        'previous_price_minor': previous_price_minor,
        'previous_posted_at': previous_posted_at,
        'best_price_minor': best_price_minor,
    }


def make_festival_offer(
    *,
    title: str = 'Steam Next Fest',
    store_url: str = 'https://store.steampowered.com/sale/nextfest',
    short_description: str = '',
    description: str = '',
    tags: list[str] | None = None,
    genres: list[str] | None = None,
    promo_end: datetime | None = datetime(2026, 3, 12, 18, 0),
) -> Offer:
    offer = make_offer()
    offer.source = OfferSource.EVENT
    offer.offer_kind = OfferKind.FESTIVAL
    offer.title = title
    offer.store_url = store_url
    offer.short_description = short_description
    offer.description = description
    offer.tags = list(tags or [])
    offer.genres = list(genres or [])
    offer.price_before_minor = None
    offer.price_after_minor = None
    offer.discount_percent = 0
    offer.has_trading_cards = False
    offer.achievements_count = None
    offer.review_score = None
    offer.review_count = None
    offer.promo_end = promo_end
    return offer


def test_steam_caption_has_clickable_title_and_price() -> None:
    builder = TelegramCaptionBuilder(1024)
    caption, hashtags = builder.build(make_offer(), make_decision())

    assert '<a href="https://store.steampowered.com/app/10"><b>Test Game</b></a>' in caption
    assert 'Зараз 112 грн замість 225 грн (-50%, економія 113 грн).' in caption
    assert '89% позитивних • 1.2к+ відгуків • 42 досягнень • є картки' in caption
    assert 'Спецпропозиція у Steam' not in caption
    assert len(caption) <= 1024
    assert hashtags == ['#steam', '#steamsale']


def test_compact_review_count_formatter_floors_without_rounding_up() -> None:
    assert format_compact_review_count(999) == '999'
    assert format_compact_review_count(4800) == '4.8к+'
    assert format_compact_review_count(86444) == '86к+'
    assert format_compact_review_count(185333) == '185к+'
    assert format_compact_review_count(1_200_000) == '1.2м+'
    assert format_compact_review_count(4899) == '4.8к+'
    assert format_compact_review_count(1_299_999) == '1.2м+'


def test_epic_caption_uses_existing_description_when_available() -> None:
    offer = make_offer()
    offer.source = OfferSource.EPIC
    offer.offer_kind = OfferKind.FREEBIE
    offer.store_url = 'https://store.epicgames.com/uk/p/test-game'
    offer.price_before_minor = 69900
    offer.price_after_minor = 0
    offer.discount_percent = 100
    offer.short_description = 'Кооперативний roguelite про хаотичні пограбування та втечі.'
    offer.description = offer.short_description
    offer.achievements_count = None
    offer.has_trading_cards = False

    builder = TelegramCaptionBuilder(1024)
    caption, _ = builder.build(offer, make_decision(lane='breaking_freebie', template_id='epic_free'))

    assert 'Кооперативний roguelite про хаотичні пограбування та втечі.' in caption
    assert '#epicgames' in caption
    assert 'лишається на акаунті' in caption
    assert caption.count('назавжди') <= 1


def test_epic_caption_ignores_non_cyrillic_store_description() -> None:
    offer = make_offer()
    offer.source = OfferSource.EPIC
    offer.offer_kind = OfferKind.FREEBIE
    offer.title = 'Turnip Boy Robs a Bank'
    offer.store_url = 'https://store.epicgames.com/uk/p/test-game'
    offer.price_before_minor = 69900
    offer.price_after_minor = 0
    offer.discount_percent = 100
    offer.short_description = 'Build your crew and rob absurd banks in a chaotic co-op roguelite.'
    offer.description = offer.short_description
    offer.tags = ['Co-op', 'Roguelite']
    offer.genres = ['Action']
    offer.achievements_count = None
    offer.has_trading_cards = False

    builder = TelegramCaptionBuilder(1024)
    caption, _ = builder.build(offer, make_decision(lane='breaking_freebie', template_id='epic_free'))

    assert 'Build your crew and rob absurd banks' not in caption
    assert 'Turnip Boy Robs a Bank' in caption
    assert '#epicgames' in caption


def test_epic_caption_falls_back_to_non_redundant_summary_without_description() -> None:
    offer = make_offer()
    offer.source = OfferSource.EPIC
    offer.offer_kind = OfferKind.FREEBIE
    offer.store_url = 'https://store.epicgames.com/uk/p/test-game'
    offer.price_before_minor = 69900
    offer.price_after_minor = 0
    offer.discount_percent = 100
    offer.short_description = ''
    offer.description = ''
    offer.title = 'Turnip Boy Robs a Bank'
    offer.tags = ['Co-op', 'Roguelite']
    offer.genres = ['Action']

    builder = TelegramCaptionBuilder(1024)
    caption, _ = builder.build(offer, make_decision(lane='breaking_freebie', template_id='epic_free'))
    blocks = [block for block in caption.split('\n\n') if block]

    assert len(blocks) >= 4
    assert 'Turnip Boy Robs a Bank' in blocks[0]
    assert not blocks[1].startswith('Turnip Boy Robs a Bank')
    assert '#epicgames' in caption


def test_steam_discount_caption_prefers_short_description() -> None:
    offer = make_offer()
    offer.short_description = 'Тактична RPG про складні вибори, експедиції та темне фентезі.'
    offer.description = 'Повний опис, який не має з’явитися замість короткого.'

    builder = TelegramCaptionBuilder(1024)
    caption, _ = builder.build(offer, make_decision())

    assert 'Тактична RPG про складні вибори' in caption
    assert 'Повний опис, який не має з’явитися' not in caption


def test_steam_discount_caption_rewrites_marketing_store_copy_to_compact_editorial_line() -> None:
    offer = make_offer()
    offer.title = 'American Truck Simulator'
    offer.short_description = (
        'Відчуйте силу легендарних американських вантажівок та доставляйте різноманітні вантажі '
        'по сонячній Каліфорнії, піщаній Неваді та величному Великому Каньйону штату Аризона.'
    )
    offer.description = offer.short_description
    offer.tags = ['Simulation', 'Driving']
    offer.genres = ['Simulation']

    builder = TelegramCaptionBuilder(1024)
    caption, _ = builder.build(offer, make_decision())
    blocks = [clean_html_text(block).strip() for block in caption.split('\n\n') if block.strip()]

    assert len(blocks) >= 2
    assert blocks[1] == 'Симулятор дальнобійника про американські траси, вантажі й довгі поїздки між штатами.'
    assert len(blocks[1]) <= 120
    assert 'Відчуйте силу легендарних американських вантажівок' not in caption


def test_discount_caption_v2_uses_compact_social_proof_and_removes_banned_filler() -> None:
    offer = make_offer()
    offer.review_score = 81
    offer.review_count = 185333
    offer.achievements_count = 72
    offer.has_trading_cards = True

    builder = TelegramCaptionBuilder(1024)
    caption, _ = builder.build(offer, make_decision())

    assert '185333' not in caption
    assert '81% позитивних • 185к+ відгуків • 72 досягнень • є картки' in caption
    assert 'Йото радить звернути увагу' not in caption
    assert 'Йото радить не проходити повз' not in caption
    assert 'жанровий акцент чіткий' not in caption
    assert 'пропозиція активна просто зараз' not in caption
    assert 'цінник уже дає привід повернутися' not in caption


def test_discount_caption_v2_omits_missing_optional_meta_cleanly() -> None:
    offer = make_offer()
    offer.review_score = 86
    offer.review_count = 126116
    offer.achievements_count = None
    offer.has_trading_cards = False

    builder = TelegramCaptionBuilder(1024)
    caption, _ = builder.build(offer, make_decision())

    assert '86% позитивних • 126к+ відгуків' in caption
    assert 'досягнень' not in caption
    assert 'є картки' not in caption
    assert '• •' not in caption


def test_indirect_recommend_caption_rejects_store_fragments_and_english_dump() -> None:
    offer = make_offer()
    offer.title = 'Hearts of Iron IV'
    offer.review_score = 90
    offer.review_count = 358990
    offer.short_description = (
        'Expansion Pass 2 Про гру Take charge of history’s greatest war machines in Hearts of Iron IV, '
        'a grand strategy wargame that challenges your strategic abilities and political insight.'
    )
    offer.description = offer.short_description

    builder = TelegramCaptionBuilder(1024)
    caption, _ = builder.build(offer, make_decision())

    assert 'Expansion Pass 2' not in caption
    assert 'Про гру' not in caption
    assert 'Take charge of history' not in caption
    assert '358990' not in caption
    assert '358к+ відгуків' in caption
    assert 'Йото радить звернути увагу' not in caption
    assert 'жанровий акцент чіткий' not in caption


def test_source_summary_keeps_valid_ukrainian_text_after_store_header_cleanup() -> None:
    offer = make_offer()
    offer.title = 'Crusader Kings III'
    offer.review_score = 91
    offer.review_count = 137027
    offer.short_description = ''
    offer.description = 'Starter Edition Про гру Династична стратегія про союзи, інтриги та довгу гру на століття вперед.'

    builder = TelegramCaptionBuilder(1024)
    caption, _ = builder.build(offer, make_decision())

    assert 'Starter Edition' not in caption
    assert 'Про гру' not in caption
    assert 'Династична стратегія про союзи, інтриги та довгу гру на століття вперед.' in caption


def test_final_push_caption_uses_alert_signal_urgency_and_finalpush_tag() -> None:
    builder = TelegramCaptionBuilder(1024)

    lane_caption, lane_hashtags = builder.build(
        make_offer(),
        make_decision(lane='final_push', template_id='final_push', is_final_push=False),
    )
    flag_caption, flag_hashtags = builder.build(
        make_offer(),
        make_decision(lane='high_value_discount', template_id='steam_discount', is_final_push=True),
    )

    assert 'Якщо хотів(ла) взяти саме в цю акцію — краще не тягнути.' in lane_caption
    assert 'Якщо хотів(ла) взяти саме в цю акцію — краще не тягнути.' in flag_caption
    assert 'Йото' not in lane_caption
    assert 'Йото' not in flag_caption
    assert '#finalpush' in lane_hashtags
    assert '#finalpush' in flag_hashtags


def test_event_caption_falls_back_to_safe_summary_without_explicit_yoto() -> None:
    offer = make_festival_offer(title='Steam Strategy Fest', tags=['freegames', 'strategy', 'event'])

    builder = TelegramCaptionBuilder(1024)
    caption, hashtags = builder.build(offer, make_decision(lane='event_festival', template_id='festival_event'))

    assert any(phrase in caption for phrase in INDIRECT_HOOK_POOLS['festival'])
    assert 'freegames' not in caption.lower()
    assert ' event' not in caption.lower()
    expected_summaries = set(EVENT_GENERIC_SUMMARY_TEMPLATES) | {template.format(focus='стратегія') for template in EVENT_FOCUS_SUMMARY_TEMPLATES}
    assert any(summary in caption for summary in expected_summaries)
    assert 'Подія триватиме' not in caption
    assert 'Йото' not in caption
    assert '#festival' in hashtags


def test_fallback_summary_filters_junk_taxonomy_tokens() -> None:
    offer = make_offer()
    offer.title = 'Tiny Rogues'
    offer.short_description = ''
    offer.description = ''
    offer.discount_percent = 40
    offer.price_before_minor = 27900
    offer.price_after_minor = 16700
    offer.tags = ['freegames', 'games', 'edition', 'roguelite', 'top_down_shooter']
    offer.genres = ['Action']

    builder = TelegramCaptionBuilder(1024)
    caption, _ = builder.build(offer, make_decision())

    assert 'freegames' not in caption.lower()
    assert 'edition' not in caption.lower()
    assert 'top_down_shooter' not in caption.lower()
    assert '_' not in caption



def test_freebie_fallback_summary_hides_internal_taxonomy_fragments() -> None:
    offer = make_offer()
    offer.source = OfferSource.EPIC
    offer.offer_kind = OfferKind.FREEBIE
    offer.title = 'Archive Freebie'
    offer.store_url = 'https://store.epicgames.com/uk/p/archive-freebie'
    offer.price_before_minor = 27500
    offer.price_after_minor = 0
    offer.discount_percent = 100
    offer.short_description = ''
    offer.description = ''
    offer.tags = ['freegames', 'games', 'edition']
    offer.genres = ['freegames', 'games', 'edition']
    offer.achievements_count = None
    offer.has_trading_cards = False

    builder = TelegramCaptionBuilder(1024)
    caption, _ = builder.build(offer, make_decision(lane='breaking_freebie', template_id='epic_free'))

    assert 'freegames' not in caption.lower()
    assert 'edition' not in caption.lower()
    assert '0 грн' in caption
    assert 'лишається на акаунті' in caption
    assert caption.count('назавжди') <= 1



def test_discount_fallback_summary_reads_naturally_for_genre_only_offer() -> None:
    offer = make_offer()
    offer.title = 'Strategy Test'
    offer.short_description = ''
    offer.description = ''
    offer.tags = []
    offer.genres = ['Strategy']
    offer.discount_percent = 40
    offer.price_before_minor = 39900
    offer.price_after_minor = 23900

    builder = TelegramCaptionBuilder(1024)
    caption, _ = builder.build(offer, make_decision(lane='backlog_filler'))

    assert any(
        fragment in caption
        for fragment in (
            'Тут основа — стратегія.',
            'Найпростіше описати це через стратегія.',
            'Головне тут — стратегія.',
        )
    )
    assert 'любить стратегія' not in caption



def test_freebie_caption_uses_direct_yoto_signal_and_forever_language() -> None:
    offer = make_offer()
    offer.title = 'Intravenous'
    offer.offer_kind = OfferKind.FREEBIE
    offer.price_before_minor = 24900
    offer.price_after_minor = 0
    offer.discount_percent = 100
    offer.short_description = 'Тактичний стелс-шутер, де важливі шум, світло і вибір маршруту.'
    offer.description = offer.short_description
    offer.tags = ['Stealth', 'Action']
    offer.genres = ['Action']

    builder = TelegramCaptionBuilder(1024)
    caption, _ = builder.build(offer, make_decision(lane='breaking_freebie', template_id='steam_free'))

    assert 'Йото' in caption
    assert '0 грн' in caption
    assert 'лишається в бібліотеці' in caption
    assert 'Роздача відкрита до 12 березня 2026, 18:00.' in caption
    assert caption.count('назавжди') <= 1


def test_high_value_discount_uses_indirect_voice_without_explicit_yoto() -> None:
    builder = TelegramCaptionBuilder(1024)
    caption, _ = builder.build(make_offer(), make_decision())

    assert 'Йото' not in caption
    assert not any(phrase in caption for phrase in INDIRECT_HOOK_POOLS['finder'])
    assert 'Зараз 112 грн замість 225 грн (-50%, економія 113 грн).' in caption
    assert '89% позитивних • 1.2к+ відгуків' in caption


def test_backlog_discount_stays_neutral_without_voice_signal() -> None:
    offer = make_offer()
    offer.discount_percent = 30
    offer.price_before_minor = 29900
    offer.price_after_minor = 20900

    builder = TelegramCaptionBuilder(1024)
    caption, _ = builder.build(offer, make_decision(lane='backlog_filler'))

    assert 'Йото' not in caption
    assert not any(phrase in caption for phrase in INDIRECT_HOOK_POOLS['finder'])
    assert 'Зараз 209 грн замість 299 грн (-30%, економія 90 грн).' in caption
    assert 'Якщо давно була в бажаному — це хороший момент.' in caption


def test_temporary_free_access_avoids_free_claim_language() -> None:
    offer = make_offer()
    offer.offer_kind = OfferKind.FREEBIE
    offer.title = 'Space Raiders Free Weekend'
    offer.price_before_minor = 39900
    offer.price_after_minor = 0
    offer.discount_percent = 100
    offer.short_description = 'У шутер можна пограти безкоштовно на вихідних.'
    offer.description = offer.short_description
    offer.metadata['free_access_type'] = 'temporary'

    builder = TelegramCaptionBuilder(1024)
    caption, _ = builder.build(offer, make_decision(lane='breaking_freebie', template_id='steam_free'))

    assert 'Йото вихопив роздачу' not in caption
    assert 'назавжди' not in caption
    assert 'пограти безкоштовно' in caption
    assert 'доступ тимчасовий' in caption


def test_first_price_move_uses_special_yoto_mode() -> None:
    offer = make_offer()
    offer.title = 'Grand Theft Auto VI'
    offer.franchise_key = 'grand-theft-auto-vi'
    offer.discount_percent = 10
    offer.price_before_minor = 239900
    offer.price_after_minor = 215900
    offer.review_score = 91
    offer.review_count = 24000

    builder = TelegramCaptionBuilder(1024)
    caption, _ = builder.build(
        offer,
        make_decision(
            lane='high_value_discount',
            decision_reasons=['high_value_discount', 'editorial_importance:standout_title'],
        ),
    )

    debug = builder.last_debug_snapshot()

    assert debug['style'] == 'first_price_move'
    assert any(cta in caption for cta in CTA_POOLS['first_price_move'])
    assert not any(phrase in caption for phrase in DIRECT_OPENING_POOLS['first_price_move'])


def test_direct_openings_rotate_across_nearby_posts() -> None:
    builder = TelegramCaptionBuilder(1024)

    first_offer = make_offer()
    first_offer.offer_id = 'steam:100'
    first_offer.title = 'First Freebie'
    first_offer.offer_kind = OfferKind.FREEBIE
    first_offer.price_before_minor = 19900
    first_offer.price_after_minor = 0
    first_offer.discount_percent = 100

    second_offer = make_offer()
    second_offer.offer_id = 'steam:101'
    second_offer.title = 'Second Freebie'
    second_offer.offer_kind = OfferKind.FREEBIE
    second_offer.price_before_minor = 24900
    second_offer.price_after_minor = 0
    second_offer.discount_percent = 100

    first_caption, _ = builder.build(first_offer, make_decision(lane='breaking_freebie', template_id='steam_free'))
    second_caption, _ = builder.build(second_offer, make_decision(lane='breaking_freebie', template_id='steam_free'))

    first_opening = next(phrase for phrase in DIRECT_OPENING_POOLS['freebie'] if phrase in first_caption)
    second_opening = next(phrase for phrase in DIRECT_OPENING_POOLS['freebie'] if phrase in second_caption)

    assert first_opening != second_opening


def test_caption_builder_handles_empty_fields_with_safe_fallback() -> None:
    offer = make_offer()
    offer.short_description = ''
    offer.description = ''
    offer.tags = []
    offer.genres = []
    offer.price_before_minor = None
    offer.price_after_minor = None
    offer.review_score = None
    offer.review_count = None
    offer.achievements_count = None
    offer.has_trading_cards = False

    builder = TelegramCaptionBuilder(1024)
    caption, hashtags = builder.build(offer, make_decision())

    assert caption
    assert 'Test Game' in caption
    assert hashtags







def test_indirect_openings_avoid_recent_repetition_when_alternatives_exist() -> None:
    builder = TelegramCaptionBuilder(1024)
    openings: list[str] = []

    for offset in range(4):
        offer = make_offer()
        offer.offer_id = f'steam:{200 + offset}'
        offer.title = f'Finder Deal {offset}'
        builder.build(offer, make_decision())
        openings.append(builder.last_debug_snapshot()['opening']['selected'])

    assert len(set(openings[:3])) == 3
    assert openings[3] != openings[2]


def test_opening_near_repeat_guard_prefers_less_similar_option() -> None:
    engine = TelegramCaptionBuilder(1024).voice_engine
    history = deque(['Йото радить звернути увагу.'], maxlen=8)
    pool = (
        'Йото радить звернути увагу.',
        'Йото радить не проходити повз.',
        'Йото помітив цікаву просадку.',
    )

    picked = engine._pick_phrase(pool, history, 'near-repeat-test', debug_label='opening', anti_repeat_window=4)

    assert picked == 'Йото помітив цікаву просадку.'
    assert engine._last_phrase_debug['opening']['repeat_risk'] is False


def test_opening_fallback_stays_safe_when_pool_is_exhausted() -> None:
    engine = TelegramCaptionBuilder(1024).voice_engine
    history = deque(DIRECT_OPENING_POOLS['freebie'], maxlen=8)

    picked = engine._pick_phrase(DIRECT_OPENING_POOLS['freebie'], history, 'exhausted-freebie', debug_label='opening', anti_repeat_window=4)
    debug = engine._last_phrase_debug['opening']

    assert picked in DIRECT_OPENING_POOLS['freebie']
    assert debug['fallback_used'] is True
    assert debug['anti_repeat_relaxed'] is True


def test_caption_normalization_cleans_weird_symbols_without_breaking_time_format() -> None:
    offer = make_offer()
    offer.short_description = 'Тактична пригода з дивними​ символами , тестом � і ноткою â€“ ритму.'
    offer.description = offer.short_description

    builder = TelegramCaptionBuilder(1024)
    caption, _ = builder.build(offer, make_decision())
    debug = builder.last_debug_snapshot()

    assert '�' not in caption
    assert '​' not in caption
    assert ' ,' not in caption
    assert '18: 00' not in caption
    assert debug['weird_symbol_detected'] is True
    assert debug['normalization_applied']['removed_replacement_chars'] is True


def test_caption_normalization_preserves_html_safety() -> None:
    offer = make_offer()
    offer.title = 'AT&T <Rise>'
    offer.short_description = 'Сюжетна пригода â€“ з гострим темпом.'
    offer.description = offer.short_description

    builder = TelegramCaptionBuilder(1024)
    caption, _ = builder.build(offer, make_decision())

    assert '<a href="https://store.steampowered.com/app/10"><b>AT&amp;T &lt;Rise&gt;</b></a>' in caption
    assert '<b>' in caption and '</b>' in caption


def test_caption_builder_exposes_opening_debug_snapshot() -> None:
    builder = TelegramCaptionBuilder(1024)

    caption, _ = builder.build(make_offer(), make_decision())
    debug = builder.last_debug_snapshot()

    assert caption
    assert debug['presence'] == 'indirect'
    assert debug['style'] == 'finder'
    assert debug['opening']['selected'] in INDIRECT_HOOK_POOLS['finder']
    assert debug['opening']['line'] not in caption
    assert debug['opening']['anti_repeat_window'] == 4
    assert debug['selected_opener'] == debug['opening']['line']
    assert 'normalization_applied' in debug
    assert 'weird_symbol_detected' in debug
    assert 'repeat_risk' in debug
    assert 'fallback_used' in debug


def test_caption_debug_is_attached_to_render_artifact(tmp_path) -> None:
    class StubDiagnostics:
        def to_snapshot(self) -> dict:
            return {'warnings': []}

    class StubRenderer:
        def __init__(self, image_path):
            self.image_path = image_path

        async def render(self, http, offer, template_id):
            self.image_path.write_bytes(b'card')
            return SimpleNamespace(
                image_path=self.image_path,
                assets_used=[offer.assets.header],
                diagnostics=StubDiagnostics(),
            )

    builder = TelegramCaptionBuilder(1024)
    use_case = DryRunRenderUseCase(builder, StubRenderer(tmp_path / 'card.png'), object())

    result = asyncio.run(use_case.execute(make_offer(), make_decision()))

    assert result.artifact.decision_debug['caption']['opening']['selected'] in INDIRECT_HOOK_POOLS['finder']
    assert result.artifact.decision_debug['caption']['opening']['anti_repeat_window'] == 4
    assert 'selected_opener' in result.artifact.decision_debug['caption']
    assert 'normalization_applied' in result.artifact.decision_debug['caption']
    assert 'weird_symbol_detected' in result.artifact.decision_debug['caption']



def test_freebie_caption_avoids_repeating_keep_forever_semantics() -> None:
    offer = make_offer()
    offer.title = 'Freeze Freebie'
    offer.offer_kind = OfferKind.FREEBIE
    offer.price_before_minor = 31900
    offer.price_after_minor = 0
    offer.discount_percent = 100
    offer.short_description = ''
    offer.description = ''
    offer.tags = ['Stealth']
    offer.genres = ['Action']

    builder = TelegramCaptionBuilder(1024)
    caption, _ = builder.build(offer, make_decision(lane='breaking_freebie', template_id='steam_free'))

    assert '0 грн' in caption
    assert 'лишається в бібліотеці' in caption
    assert caption.count('назавжди') <= 1
    assert caption.count('забрати') <= 2



def test_discount_cta_does_not_echo_numeric_value_line() -> None:
    builder = TelegramCaptionBuilder(1024)
    caption, _ = builder.build(make_offer(), make_decision())
    cta = builder.last_debug_snapshot()['cta']['selected']

    assert cta in caption
    assert 'грн' not in cta
    assert '%' not in cta
    assert not any(char.isdigit() for char in cta)



def test_deadline_wording_is_family_specific() -> None:
    builder = TelegramCaptionBuilder(1024)

    freebie = make_offer()
    freebie.offer_kind = OfferKind.FREEBIE
    freebie.price_before_minor = 19900
    freebie.price_after_minor = 0
    freebie.discount_percent = 100
    freebie.short_description = ''
    freebie.description = ''
    freebie_caption, _ = builder.build(freebie, make_decision(lane='breaking_freebie', template_id='steam_free'))

    event = make_offer()
    event.source = OfferSource.EVENT
    event.offer_kind = OfferKind.FESTIVAL
    event.title = 'Steam Next Fest'
    event.short_description = ''
    event.description = ''
    event.tags = ['event']
    event.genres = []
    event.price_before_minor = None
    event.price_after_minor = None
    event.discount_percent = 0
    event.has_trading_cards = False
    event.achievements_count = None
    event.review_score = None
    event.review_count = None
    event_caption, _ = builder.build(event, make_decision(lane='event_festival', template_id='festival_event'))

    assert 'Роздача відкрита до 12 березня 2026, 18:00.' in freebie_caption
    assert 'Вікно фестивалю — до 12 березня 2026, 18:00.' in event_caption



def test_ctas_avoid_recent_repetition_when_alternatives_exist() -> None:
    builder = TelegramCaptionBuilder(1024)
    ctas: list[str] = []

    for offset in range(4):
        offer = make_offer()
        offer.offer_id = f'steam:cta:{offset}'
        offer.title = f'CTA Deal {offset}'
        builder.build(offer, make_decision())
        ctas.append(builder.last_debug_snapshot()['cta']['selected'])

    assert len(set(ctas[:3])) == 3
    assert ctas[3] != ctas[2]
    assert all(cta in CTA_POOLS['finder'] for cta in ctas)



def test_same_input_stays_deterministic_across_fresh_builders() -> None:
    offer = make_offer()
    decision = make_decision()

    first_caption, first_hashtags = TelegramCaptionBuilder(1024).build(offer, decision)
    second_caption, second_hashtags = TelegramCaptionBuilder(1024).build(offer, decision)

    assert first_caption == second_caption
    assert first_hashtags == second_hashtags



def test_festival_caption_uses_source_led_summary_for_strong_event_case() -> None:
    offer = make_festival_offer(
        title='Steam Tower Defense Fest',
        store_url='https://store.steampowered.com/category/tower_defense',
        short_description='Тематичний тиждень для тих, хто стежить за tower defense, базобудовою та щільними хвилями ворогів.',
        description='Тематичний тиждень для тих, хто стежить за tower defense, базобудовою та щільними хвилями ворогів.',
        tags=['tower defense', 'strategy'],
    )

    builder = TelegramCaptionBuilder(1024)
    caption, _ = builder.build(offer, make_decision(lane='event_festival', template_id='festival_event'))

    assert 'Тематичний тиждень для тих, хто стежить за tower defense' in caption
    assert any(phrase in caption for phrase in INDIRECT_HOOK_POOLS['festival'])
    assert any(phrase in caption for phrase in CTA_POOLS['festival'])
    assert 'Вікно фестивалю — до 12 березня 2026, 18:00.' in caption
    assert caption.lower().count('короткий список') <= 1



def test_festival_caption_without_deadline_uses_clean_editorial_window_line() -> None:
    offer = make_festival_offer(
        title='Steam Automation Fest',
        store_url='https://store.steampowered.com/category/automation',
        short_description='A themed event full of builder demos and discount experiments.',
        description='A themed event full of builder demos and discount experiments.',
        tags=['automation', 'simulation', 'event', 'freegames'],
        promo_end=None,
    )

    builder = TelegramCaptionBuilder(1024)
    caption, _ = builder.build(offer, make_decision(lane='event_festival', template_id='festival_event'))
    expected_focus_summaries = {template.format(focus='симулятор') for template in EVENT_FOCUS_SUMMARY_TEMPLATES}

    assert 'Фестиваль уже триває, тож сторінку краще пройти одним заходом.' in caption
    assert any(summary in caption for summary in expected_focus_summaries)
    assert 'freegames' not in caption.lower()



def test_festival_openings_and_ctas_avoid_recent_repetition_when_alternatives_exist() -> None:
    builder = TelegramCaptionBuilder(1024)
    openings: list[str] = []
    ctas: list[str] = []

    for offset in range(4):
        offer = make_festival_offer(title=f'Steam Strategy Fest {offset}', store_url=f'https://store.steampowered.com/sale/strategyfest/{offset}', tags=['strategy'])
        offer.offer_id = f'event:festival:{offset}'
        offer.source_ref = offer.offer_id
        offer.game_id = offer.offer_id
        offer.franchise_key = f'festival-{offset}'
        builder.build(offer, make_decision(lane='event_festival', template_id='festival_event'))
        debug = builder.last_debug_snapshot()
        openings.append(debug['opening']['selected'])
        ctas.append(debug['cta']['selected'])

    assert len(set(openings[:3])) == 3
    assert openings[3] != openings[2]
    assert len(set(ctas[:3])) == 3
    assert ctas[3] != ctas[2]
    assert all(opening in INDIRECT_HOOK_POOLS['festival'] for opening in openings)
    assert all(cta in CTA_POOLS['festival'] for cta in ctas)



def test_same_festival_input_stays_deterministic_across_fresh_builders() -> None:
    offer = make_festival_offer(title='Steam Strategy Fest', tags=['strategy', 'event'])
    decision = make_decision(lane='event_festival', template_id='festival_event')

    first_caption, first_hashtags = TelegramCaptionBuilder(1024).build(offer, decision)
    second_caption, second_hashtags = TelegramCaptionBuilder(1024).build(offer, decision)

    assert first_caption == second_caption
    assert first_hashtags == second_hashtags



def test_festival_caption_normalization_keeps_ukrainian_punctuation_clean() -> None:
    offer = make_festival_offer(
        title='Steam Builder Fest',
        store_url='https://store.steampowered.com/category/builder',
        short_description='Фокус тут  —  симулятор , демо й знижки.',
        description='Фокус тут  —  симулятор , демо й знижки.',
        tags=['simulation'],
    )

    builder = TelegramCaptionBuilder(1024)
    caption, _ = builder.build(offer, make_decision(lane='event_festival', template_id='festival_event'))

    assert 'Фокус тут — симулятор, демо й знижки.' in caption
    assert ' , ' not in caption
    assert '  ' not in caption


