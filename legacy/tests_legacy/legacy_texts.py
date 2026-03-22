from datetime import datetime

from dealbot.models import Offer, OfferSource, PostKind
from dealbot.pipeline import evaluate_offer_against_history
from dealbot.texts import build_hashtags


def make_offer() -> Offer:
    return Offer(
        source=OfferSource.STEAM,
        post_kind=PostKind.STEAM_DISCOUNT,
        offer_id="10",
        store_item_id="10",
        title="Test Game",
        url="https://store.steampowered.com/app/10",
        image_url="https://example.com/header.jpg",
        description="Український опис гри для тесту.",
        short_description="Український опис гри для тесту.",
        discount_pct=75,
        original_price_uah=500.0,
        final_price_uah=125.0,
        review_percent=89,
        review_summary="Дуже позитивні (89%)",
        achievements_count=42,
        has_trading_cards=True,
        genres=["Action", "Adventure"],
        tags=["Action", "Coop"],
    )


def test_build_hashtags_contains_store_and_genre_tags() -> None:
    hashtags = build_hashtags(make_offer())
    assert "#steam" in hashtags
    assert "#steamsale" in hashtags
    assert "#action" in hashtags
