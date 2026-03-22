from __future__ import annotations

from domain.entities.offer import OfferKind, OfferSource

from application.editorial import select_editorial_phrase
from application.editorial.editorial_classifier import ALLOWED_EDITORIAL_PHRASES, IDENTITY_PHRASES, POPULARITY_PHRASES, QUALITY_PHRASES

from .test_caption_builder_arch import make_offer


def test_identity_phrase_prefers_city_builder_identity() -> None:
    offer = make_offer()
    offer.tags = ['Simulation', 'Strategy']
    offer.genres = ['Simulation', 'Strategy']
    offer.short_description = 'Cities: Skylines is a modern take on the classic city simulation and city building experience.'
    offer.description = ''
    offer.review_score = 93
    offer.review_count = 285347

    assert select_editorial_phrase(offer) == IDENTITY_PHRASES['city builder']


def test_identity_phrase_detects_coop_from_description() -> None:
    offer = make_offer()
    offer.tags = ['Action']
    offer.genres = ['Action']
    offer.short_description = 'Deep Rock Galactic is a cooperative shooter for 1-4 players.'
    offer.description = ''
    offer.review_score = 97
    offer.review_count = 371115

    assert select_editorial_phrase(offer) == IDENTITY_PHRASES['co-op']


def test_identity_phrase_detects_roguelike_hits() -> None:
    offer = make_offer()
    offer.tags = ['Action', 'Adventure', 'Indie']
    offer.genres = ['Action', 'Adventure', 'Indie']
    offer.short_description = 'Dead Cells is an action platformer with roguelike elements and metroidvania exploration.'
    offer.description = ''
    offer.review_score = 97
    offer.review_count = 178016

    assert select_editorial_phrase(offer) == IDENTITY_PHRASES['roguelike']


def test_identity_phrase_detects_deckbuilder_before_popularity() -> None:
    offer = make_offer()
    offer.tags = ['Indie', 'Strategy']
    offer.genres = ['Indie', 'Strategy']
    offer.short_description = 'Build your deck in this singleplayer deckbuilder.'
    offer.description = ''
    offer.review_score = 98
    offer.review_count = 207483

    assert select_editorial_phrase(offer) == IDENTITY_PHRASES['deckbuilder']


def test_identity_phrase_supports_localized_strategy_tags() -> None:
    offer = make_offer()
    offer.tags = ['\u0421\u0438\u043c\u0443\u043b\u044f\u0442\u043e\u0440\u0438', '\u0421\u0442\u0440\u0430\u0442\u0435\u0433\u0456\u0457']
    offer.genres = ['\u0421\u0438\u043c\u0443\u043b\u044f\u0442\u043e\u0440\u0438', '\u0421\u0442\u0440\u0430\u0442\u0435\u0433\u0456\u0457']
    offer.short_description = ''
    offer.description = ''
    offer.review_score = 90
    offer.review_count = 358192

    assert select_editorial_phrase(offer) == IDENTITY_PHRASES['strategy']


def test_quality_phrase_uses_controlled_dictionary_values() -> None:
    offer = make_offer()
    offer.tags = ['Indie']
    offer.genres = ['Indie']
    offer.short_description = ''
    offer.description = ''
    offer.review_score = 94
    offer.review_count = 2500

    phrase = select_editorial_phrase(offer)
    assert phrase == 'Hidden indie gem'
    assert phrase in QUALITY_PHRASES


def test_quality_phrase_precedes_popularity_for_generic_hits() -> None:
    offer = make_offer()
    offer.tags = []
    offer.genres = []
    offer.short_description = ''
    offer.description = ''
    offer.review_score = 92
    offer.review_count = 250000

    phrase = select_editorial_phrase(offer)
    assert phrase == 'Community favorite'
    assert phrase in QUALITY_PHRASES


def test_popularity_phrase_uses_last_fallback_from_dictionary() -> None:
    offer = make_offer()
    offer.tags = []
    offer.genres = []
    offer.short_description = ''
    offer.description = ''
    offer.review_score = 78
    offer.review_count = 60000

    phrase = select_editorial_phrase(offer)
    assert phrase == 'Trending hit'
    assert phrase in POPULARITY_PHRASES


def test_editorial_phrase_never_returns_uncontrolled_value() -> None:
    offer = make_offer()
    offer.tags = ['Sports']
    offer.genres = ['Sports']
    offer.short_description = ''
    offer.description = ''
    offer.review_score = 80
    offer.review_count = 22000

    phrase = select_editorial_phrase(offer)
    assert phrase in ALLOWED_EDITORIAL_PHRASES


def test_select_editorial_phrase_detects_survival_sandbox_from_metadata() -> None:
    offer = make_offer()
    offer.tags = ['Survival']
    offer.genres = ['Adventure']
    offer.short_description = ''
    offer.description = ''
    offer.review_score = 72
    offer.review_count = 140
    offer.metadata = {'genres': ['Sandbox', 'Open World']}

    assert select_editorial_phrase(offer) == IDENTITY_PHRASES['survival']


def test_select_editorial_phrase_skips_events() -> None:
    offer = make_offer()
    offer.source = OfferSource.EVENT
    offer.offer_kind = OfferKind.FESTIVAL
    offer.tags = ['Strategy']
    offer.review_score = 95
    offer.review_count = 50000

    assert select_editorial_phrase(offer) is None
