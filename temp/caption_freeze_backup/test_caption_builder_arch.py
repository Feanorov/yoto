from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime
from types import SimpleNamespace

from application.use_cases.dry_run_render import DryRunRenderUseCase
from domain.entities.offer import AssetBundle, ConfidenceLevels, Offer, OfferKind, OfferSource
from infrastructure.telegram.caption_builder import DIRECT_OPENING_POOLS, INDIRECT_HOOK_POOLS, TelegramCaptionBuilder


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


def test_steam_caption_has_clickable_title_and_price() -> None:
    builder = TelegramCaptionBuilder(1024)
    caption, hashtags = builder.build(make_offer(), make_decision())

    assert '<a href="https://store.steampowered.com/app/10"><b>Test Game</b></a>' in caption
    assert '<a href="https://store.steampowered.com/app/10"><b>112 грн</b></a>' in caption
    assert 'Спецпропозиція у Steam' not in caption
    assert len(caption) <= 1024
    assert '#steam' in hashtags


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
    assert 'назавжди' in caption


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

    assert 'Фінальний шанс' in lane_caption
    assert 'Фінальний шанс' in flag_caption
    assert 'Йото' in lane_caption
    assert 'Йото' in flag_caption
    assert '#finalpush' in lane_hashtags
    assert '#finalpush' in flag_hashtags


def test_event_caption_falls_back_to_safe_summary_without_explicit_yoto() -> None:
    offer = make_offer()
    offer.source = OfferSource.EVENT
    offer.offer_kind = OfferKind.FESTIVAL
    offer.title = 'Steam Strategy Fest'
    offer.short_description = ''
    offer.description = ''
    offer.tags = ['freegames', 'strategy', 'event']
    offer.genres = []
    offer.price_before_minor = None
    offer.price_after_minor = None
    offer.discount_percent = 0
    offer.has_trading_cards = False
    offer.achievements_count = None
    offer.review_score = None
    offer.review_count = None

    builder = TelegramCaptionBuilder(1024)
    caption, hashtags = builder.build(offer, make_decision(lane='event_festival', template_id='festival_event'))

    assert 'тематична подія' in caption.lower()
    assert 'freegames' not in caption.lower()
    assert ' event' not in caption.lower()
    assert 'Перегляньте фестиваль зараз' in caption
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
    assert 'лишити в бібліотеці на потім' in caption
    assert 'спокійно додати на акаунт' in caption



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

    assert 'Влучний варіант для тих, хто любить стратегії.' in caption
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
    assert 'додати безкоштовно' in caption
    assert 'назавжди' in caption
    assert 'Забрати назавжди варто до 12 березня 2026, 18:00.' in caption


def test_high_value_discount_uses_indirect_voice_without_explicit_yoto() -> None:
    builder = TelegramCaptionBuilder(1024)
    caption, _ = builder.build(make_offer(), make_decision())

    assert 'Йото' not in caption
    assert any(phrase in caption for phrase in INDIRECT_HOOK_POOLS['finder'])


def test_backlog_discount_stays_neutral_without_voice_signal() -> None:
    offer = make_offer()
    offer.discount_percent = 30
    offer.price_before_minor = 29900
    offer.price_after_minor = 20900

    builder = TelegramCaptionBuilder(1024)
    caption, _ = builder.build(offer, make_decision(lane='backlog_filler'))

    assert 'Йото' not in caption
    assert not any(phrase in caption for phrase in INDIRECT_HOOK_POOLS['finder'])
    assert 'Гра відчутно подешевшала й повернулася на радар.' in caption


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

    assert any(phrase in caption for phrase in DIRECT_OPENING_POOLS['first_price_move'])
    assert 'перша помітна знижка по грі' in caption


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
        caption, _ = builder.build(offer, make_decision())
        openings.append(next(phrase for phrase in INDIRECT_HOOK_POOLS['finder'] if phrase in caption))

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
    assert debug['opening']['line'] in caption
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
