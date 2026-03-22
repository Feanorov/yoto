from __future__ import annotations

from domain.entities.roundup_post import RoundupItem, RoundupPost
from infrastructure.telegram.caption_builder import DIRECT_OPENING_POOLS
from infrastructure.telegram.roundup_draft_builder import TelegramRoundupDraftBuilder


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


def test_roundup_draft_builder_creates_editorial_hero_discount_caption() -> None:
    builder = TelegramRoundupDraftBuilder()
    roundup = RoundupPost(
        roundup_id='roundup_02_big_discount_highlights',
        title='Roundup: Big Discount Highlights Part 2',
        intro='raw intro',
        group_type='hero_discount',
        theme_label='Big Discount Highlights',
        item_count=3,
        items=[
            make_item(1, 'Grand Theft Auto V Enhanced', store_url='https://store.steampowered.com/app/3240220', discount_percent=56, price_after_minor=87900, review_score=81, reason_tags=['hero_discount', 'editorial_importance:standout_title']),
            make_item(2, 'Teardown', store_url='https://store.steampowered.com/app/1167630', discount_percent=50, price_after_minor=32400, review_score=96, reason_tags=['hero_discount', 'editorial_importance:critical_favorite']),
            make_item(3, 'Valheim', store_url='https://store.steampowered.com/app/892970', discount_percent=50, price_after_minor=26900, review_score=94, reason_tags=['hero_discount', 'editorial_importance:mega_popular']),
        ],
    )

    draft = builder.build(roundup)

    assert draft.title == 'Що взяти зі знижок просто зараз, частина 2'
    assert any(phrase in draft.intro for phrase in DIRECT_OPENING_POOLS['roundup'])
    assert 'найсильніші резервні знижки' in draft.intro
    assert draft.item_lines[0].startswith('1. <a href="https://store.steampowered.com/app/3240220"><b>Grand Theft Auto V Enhanced</b></a> - ')
    assert '56% до 879 грн' in draft.item_lines[0]
    assert 'знаковий хіт' in draft.item_lines[0]
    assert draft.closing_cta
    assert draft.caption_html.startswith('<b>Що взяти зі знижок просто зараз, частина 2</b>')
    assert 'Teardown' in draft.caption_html
    assert 'Valheim' in draft.caption_html


def test_roundup_draft_builder_creates_freebie_caption_lines() -> None:
    builder = TelegramRoundupDraftBuilder()
    roundup = RoundupPost(
        roundup_id='roundup_01_freebies_to_claim',
        title='Roundup: Freebies To Claim',
        intro='raw intro',
        group_type='freebie',
        theme_label='Freebies To Claim',
        item_count=3,
        items=[
            make_item(1, 'Isonzo', store_url='https://store.epicgames.com/uk/p/isonzo', discount_percent=100, price_after_minor=0, review_score=80, reason_tags=['freebie_roundup_candidate'], is_freebie=True, source='epic'),
            make_item(2, 'Cozy Grove', store_url='https://store.epicgames.com/uk/p/cozy-grove', discount_percent=100, price_after_minor=0, review_score=86, reason_tags=['freebie_roundup_candidate'], is_freebie=True, source='epic'),
            make_item(3, 'Deponia', store_url='https://store.steampowered.com/app/214340', discount_percent=100, price_after_minor=0, review_score=78, reason_tags=['freebie_low_signal'], is_freebie=True, source='steam'),
        ],
    )

    draft = builder.build(roundup)

    assert draft.title == 'Безкоштовні роздачі, які ще можна забрати'
    assert any(phrase in draft.intro for phrase in DIRECT_OPENING_POOLS['roundup'])
    assert 'безкоштовних роздач' in draft.intro
    assert 'безкоштовно в Epic' in draft.item_lines[0]
    assert 'варта уваги' in draft.item_lines[0]
    assert 'безкоштовно в Steam' in draft.item_lines[2]
    assert 'не найгучніша, але може зайти' in draft.item_lines[2]
    assert draft.closing_cta
    assert draft.caption_html.startswith('<b>Безкоштовні роздачі, які ще можна забрати</b>')


def test_roundup_opening_pool_stays_compact_and_natural() -> None:
    assert DIRECT_OPENING_POOLS['roundup'] == (
        '🐱 Йото зібрав добірку сильних знижок.',
        '🐱 Йото витягнув ще кілька помітних пропозицій.',
    )

