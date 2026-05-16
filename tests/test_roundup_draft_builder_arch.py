from __future__ import annotations

from infrastructure.telegram.caption_builder import CTA_POOLS, DIRECT_OPENING_POOLS
from infrastructure.telegram.roundup_draft_builder import TelegramRoundupDraftBuilder
from domain.entities.roundup_post import RoundupItem, RoundupPost


def make_item(
    rank: int,
    title: str,
    *,
    store_url: str,
    discount_percent: int = 50,
    price_after_minor: int | None = 44900,
    review_score: int | None = 95,
    reason_tags: list[str] | None = None,
    is_freebie: bool = False,
    source: str = 'steam',
) -> RoundupItem:
    return RoundupItem(
        rank=rank,
        offer_id=f'offer:{rank}',
        title=title,
        store_url=store_url,
        store='Epic Games Store' if source == 'epic' else 'Steam',
        source=source,
        lane='backlog_filler' if is_freebie else 'high_value_discount',
        score=200.0 - rank,
        discount_percent=discount_percent,
        review_score=review_score,
        is_freebie=is_freebie,
        price_after_minor=price_after_minor,
        price_line='Free claim' if is_freebie else '50% off to UAH 449',
        callout='Freebie roundup candidate' if is_freebie else 'Hero discount',
        summary_line='summary',
        reason_tags=list(reason_tags or []),
    )


def make_roundup(
    roundup_id: str,
    *,
    title: str = 'Roundup: Big Discount Highlights Part 2',
    group_type: str = 'hero_discount',
    theme_label: str = 'Big Discount Highlights',
    items: list[RoundupItem] | None = None,
) -> RoundupPost:
    return RoundupPost(
        roundup_id=roundup_id,
        title=title,
        intro='raw intro',
        group_type=group_type,
        theme_label=theme_label,
        item_count=len(items or []),
        items=list(items or []),
    )


def test_roundup_draft_builder_creates_compact_hero_discount_caption() -> None:
    builder = TelegramRoundupDraftBuilder()
    draft = builder.build(
        make_roundup(
            'roundup_02_big_discount_highlights',
            items=[
                make_item(1, 'Grand Theft Auto V Enhanced', store_url='https://store.steampowered.com/app/3240220', discount_percent=56, price_after_minor=87900, review_score=81, reason_tags=['hero_discount', 'editorial_importance:standout_title']),
                make_item(2, 'Teardown', store_url='https://store.steampowered.com/app/1167630', discount_percent=50, price_after_minor=32400, review_score=96, reason_tags=['hero_discount', 'editorial_importance:critical_favorite']),
                make_item(3, 'Valheim', store_url='https://store.steampowered.com/app/892970', discount_percent=50, price_after_minor=26900, review_score=94, reason_tags=['hero_discount', 'editorial_importance:mega_popular']),
            ],
        )
    )

    assert draft.title == '🔥 Що взяти зі знижок: коротка добірка, частина 2'
    assert draft.intro == 'Кілька великих знижок, з яких зручно почати прямо зараз.'
    assert 'Йото' not in draft.intro
    assert 'резерв' not in draft.intro.lower()
    assert draft.item_lines[0].startswith('1. <a href="https://store.steampowered.com/app/3240220"><b>Grand Theft Auto V Enhanced</b></a> — ')
    assert '-56% до 879 грн, 81% позитивних' in draft.item_lines[0]
    assert '96% позитивних' in draft.item_lines[1]
    assert '94% позитивних' in draft.item_lines[2]
    assert 'коментар' not in draft.closing_cta.lower()
    assert any(fragment in draft.closing_cta for fragment in ('перших позицій', 'перших пунктів', 'верхніх позицій', 'головне'))
    assert draft.caption_html.startswith('<b>🔥 Що взяти зі знижок: коротка добірка, частина 2</b>')
    assert '#toplist #steamsale #steam' in draft.caption_html


def test_roundup_draft_builder_creates_freebie_caption_lines() -> None:
    builder = TelegramRoundupDraftBuilder()
    draft = builder.build(
        make_roundup(
            'roundup_01_freebies_to_claim',
            title='Roundup: Freebies To Claim',
            group_type='freebie',
            theme_label='Freebies To Claim',
            items=[
                make_item(1, 'Isonzo', store_url='https://store.epicgames.com/uk/p/isonzo', discount_percent=100, price_after_minor=0, review_score=80, reason_tags=['freebie_roundup_candidate'], is_freebie=True, source='epic'),
                make_item(2, 'Cozy Grove', store_url='https://store.epicgames.com/uk/p/cozy-grove', discount_percent=100, price_after_minor=0, review_score=86, reason_tags=['freebie_roundup_candidate'], is_freebie=True, source='epic'),
                make_item(3, 'Deponia', store_url='https://store.steampowered.com/app/214340', discount_percent=100, price_after_minor=0, review_score=78, reason_tags=['freebie_low_signal'], is_freebie=True, source='steam'),
            ],
        )
    )

    assert draft.title == '🎁 Безкоштовні ігри: коротка добірка'
    assert draft.intro == 'Зараз можна забрати 3 безплатні ігри в Epic і Steam.'
    assert 'резерв' not in draft.intro.lower()
    assert ' — ' in draft.item_lines[0]
    assert 'безплатно в Epic' in draft.item_lines[0]
    assert 'варте швидкої звірки' not in draft.item_lines[0]
    assert 'безплатно в Steam' in draft.item_lines[2]
    assert 'нішевий, але робочий слот' not in draft.item_lines[2]
    assert 'коментар' not in draft.closing_cta.lower()
    assert any(fragment in draft.closing_cta for fragment in ('забрати одразу', 'перших позицій', 'перших пунктів', 'верхніх позицій', 'головне'))
    assert '#toplist #freegames' in draft.caption_html
    assert '#steam' not in draft.caption_html
    assert '#epicgames' not in draft.caption_html


def test_roundup_opening_pool_stays_compact_and_has_room_for_anti_repeat() -> None:
    assert len(DIRECT_OPENING_POOLS['roundup']) >= 5
    assert all('Йото' not in phrase for phrase in DIRECT_OPENING_POOLS['roundup'])
    assert all('редактор' not in phrase for phrase in DIRECT_OPENING_POOLS['roundup'])
    assert all('відсіяв шум' not in phrase for phrase in DIRECT_OPENING_POOLS['roundup'])


def test_roundup_openings_and_ctas_avoid_recent_repetition_when_alternatives_exist() -> None:
    builder = TelegramRoundupDraftBuilder()
    openings: list[str] = []
    ctas: list[str] = []

    for offset in range(4):
        builder.build(
            make_roundup(
                f'roundup_repeat_{offset}',
                items=[
                    make_item(1, f'Lead {offset}', store_url=f'https://store.steampowered.com/app/{1000 + offset}', discount_percent=70, price_after_minor=19900, review_score=90, reason_tags=['hero_discount', 'editorial_importance:mega_popular']),
                    make_item(2, f'Second {offset}', store_url=f'https://store.steampowered.com/app/{2000 + offset}', discount_percent=60, price_after_minor=24900, review_score=88, reason_tags=['hero_discount', 'editorial_importance:critical_favorite']),
                    make_item(3, f'Third {offset}', store_url=f'https://store.steampowered.com/app/{3000 + offset}', discount_percent=50, price_after_minor=29900, review_score=84, reason_tags=['hero_discount']),
                ],
            )
        )
        debug = builder.voice_engine.last_debug_snapshot()
        openings.append(str(debug['opening']['selected']))
        ctas.append(str(debug['cta']['selected']))

    assert len(set(openings)) == 4
    assert len(set(ctas)) == 4
    assert all(opening in DIRECT_OPENING_POOLS['roundup'] for opening in openings)
    assert all(cta in CTA_POOLS['roundup'] for cta in ctas)


def test_same_roundup_input_stays_deterministic_across_fresh_builders() -> None:
    roundup = make_roundup(
        'roundup_deterministic_case',
        items=[
            make_item(1, 'Helldivers 2', store_url='https://store.steampowered.com/app/553850', discount_percent=20, price_after_minor=95900, review_score=83, reason_tags=['roundup_discount', 'editorial_importance:very_popular']),
            make_item(2, 'Deep Rock Galactic', store_url='https://store.steampowered.com/app/548430', discount_percent=67, price_after_minor=14900, review_score=97, reason_tags=['strong_discount', 'editorial_importance:trusted_hit']),
            make_item(3, 'Ready or Not', store_url='https://store.steampowered.com/app/1144200', discount_percent=35, price_after_minor=58400, review_score=88, reason_tags=['roundup_discount', 'editorial_importance:highly_rated']),
        ],
        title='Roundup: Co-op Precision Picks',
        group_type='tag',
        theme_label='Co-op',
    )

    first_draft = TelegramRoundupDraftBuilder().build(roundup)
    second_draft = TelegramRoundupDraftBuilder().build(roundup)

    assert first_draft.to_snapshot() == second_draft.to_snapshot()


def test_mixed_roundup_keeps_punctuation_clean_and_drops_dump_language() -> None:
    draft = TelegramRoundupDraftBuilder().build(
        make_roundup(
            'roundup_04_reserve_deals_watch',
            title='Roundup: Reserve Deals Watch Part 2',
            group_type='mixed',
            theme_label='Digest',
            items=[
                make_item(1, 'Cities: Skylines II', store_url='https://store.steampowered.com/app/949230', discount_percent=30, price_after_minor=94400, review_score=74, reason_tags=['roundup_discount']),
                make_item(2, 'Retro Rewind - Video Store Simulator', store_url='https://store.steampowered.com/app/3552140', discount_percent=20, price_after_minor=31200, review_score=97, reason_tags=['editorial_importance:highly_rated']),
                make_item(3, 'Everwind', store_url='https://store.steampowered.com/app/2253100', discount_percent=10, price_after_minor=53500, review_score=86, reason_tags=[]),
            ],
        )
    )

    assert draft.title == '🔥 Що ще подивитися: коротка добірка, частина 2'
    assert 'резерв' not in draft.title.lower()
    assert 'резерв' not in draft.intro.lower()
    assert draft.intro == 'Кілька позицій, які ще варто швидко перевірити.'
    assert '  ' not in draft.caption_html
    assert ' , ' not in draft.caption_html
    assert 'коментар' not in draft.closing_cta.lower()
    assert any(fragment in draft.closing_cta for fragment in ('кілька перших позицій', 'перших пунктів', 'верхніх позицій', 'головне'))


def test_tag_roundup_reads_like_editorial_selection_not_plain_list() -> None:
    draft = TelegramRoundupDraftBuilder().build(
        make_roundup(
            'roundup_99_tag_shortlist',
            title='Roundup: Co-op Picks',
            group_type='tag',
            theme_label='Co-op',
            items=[
                make_item(1, 'Helldivers 2', store_url='https://store.steampowered.com/app/553850', discount_percent=20, price_after_minor=95900, review_score=83, reason_tags=['roundup_discount', 'editorial_importance:very_popular']),
                make_item(2, 'Deep Rock Galactic', store_url='https://store.steampowered.com/app/548430', discount_percent=67, price_after_minor=14900, review_score=97, reason_tags=['strong_discount', 'editorial_importance:trusted_hit']),
            ],
        )
    )

    assert draft.title == '🔥 Co-op: коротка добірка'
    assert draft.intro == 'Кілька ігор у темі Co-op, які зараз виглядають найцікавіше.'
    assert '97% позитивних' in draft.item_lines[1]
    assert 'коментар' not in draft.closing_cta.lower()
    assert draft.caption_html.endswith('#toplist #steamsale #steam')

