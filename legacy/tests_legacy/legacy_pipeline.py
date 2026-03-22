from datetime import datetime, timedelta

from dealbot.models import OfferHistory, OfferSource
from dealbot.pipeline import evaluate_offer_against_history

from .test_texts import make_offer


def test_skip_same_discount_and_same_price() -> None:
    offer = make_offer()
    history = OfferHistory(
        source=OfferSource.STEAM,
        offer_id=offer.offer_id,
        last_posted_at=datetime.utcnow() - timedelta(days=35),
        last_discount_pct=offer.discount_pct,
        last_final_price_uah=offer.final_price_uah,
        last_initial_price_uah=offer.original_price_uah,
    )
    assert evaluate_offer_against_history(offer, history, datetime.utcnow()) is None


def test_allow_better_price_with_note() -> None:
    offer = make_offer()
    offer.final_price_uah = 99.0
    history = OfferHistory(
        source=OfferSource.STEAM,
        offer_id=offer.offer_id,
        last_posted_at=datetime.utcnow() - timedelta(days=10),
        last_discount_pct=50,
        last_final_price_uah=199.0,
        last_initial_price_uah=offer.original_price_uah,
    )
    prepared = evaluate_offer_against_history(offer, history, datetime.utcnow())
    assert prepared is not None
    assert prepared.improvement_note is not None
