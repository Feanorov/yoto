from __future__ import annotations

from collections.abc import Iterable

from domain.entities.offer import Offer, OfferSource


IDENTITY_PHRASES = {
    'roguelike': 'Roguelike hit',
    'deckbuilder': 'Deckbuilder hit',
    'city builder': 'City builder',
    'factory': 'Factory builder',
    'tower defense': 'Tower defense',
    'co-op': 'Co-op favorite',
    'survival': 'Survival sandbox',
    'strategy': 'Strategy classic',
    'metroidvania': 'Metroidvania hit',
    'racing': 'Racing hit',
    'sports': 'Sports sim',
    'colony': 'Colony sim',
    'park': 'Park builder',
}

QUALITY_PHRASES = [
    'Top rated indie',
    'Player favorite',
    'Critically loved',
    'Hidden indie gem',
    'Community favorite',
]

POPULARITY_PHRASES = [
    'Steam bestseller',
    'Trending hit',
    'Fan favorite',
]

ALLOWED_EDITORIAL_PHRASES = frozenset((*IDENTITY_PHRASES.values(), *QUALITY_PHRASES, *POPULARITY_PHRASES))

UA_CITY_BUILD = '\u043c\u0456\u0441\u0442\u043e\u0431\u0443\u0434'
UA_CITY_SIM = '\u043c\u0456\u0441\u044c\u043a\u043e\u0457 \u0441\u0438\u043c\u0443\u043b\u044f\u0446\u0456\u0457'
UA_FACTORY_BUILD = '\u0431\u0443\u0434\u0456\u0432\u043d\u0438\u0446\u0442\u0432\u043e \u0444\u0430\u0431\u0440\u0438\u043a'
UA_BUILD_FACTORIES = '\u0431\u0443\u0434\u0443\u0432\u0430\u0442\u0438 \u0444\u0430\u0431\u0440\u0438\u043a\u0438'
UA_FACTORIES = '\u0444\u0430\u0431\u0440\u0438\u043a\u0438'
UA_CONVEYOR = '\u043a\u043e\u043d\u0432\u0435\u0454\u0440'
UA_DECKBUILDER = '\u0441\u043a\u043b\u0430\u0434\u0430\u043b\u044c\u043d\u0438\u043a \u043a\u043e\u043b\u043e\u0434\u0438'
UA_CARDS = '\u043a\u0430\u0440\u0442\u043a\u043e\u0432\u0456'
UA_DECK = '\u043a\u043e\u043b\u043e\u0434'
UA_ROGUELIKE = '\u0440\u043e\u0433\u0430\u043b\u0438\u043a'
UA_ROGUELIKE_GEN = '\u0440\u043e\u0433\u0430\u043b\u0438\u043a\u0430'
UA_ROGUELIKE_INST = '\u0440\u043e\u0433\u0430\u043b\u0438\u043a\u043e\u043c'
UA_METROIDVANIA = '\u043c\u0435\u0442\u0440\u043e\u0457\u0434\u0432\u0430\u043d\u0456\u044f'
UA_COOP = '\u043a\u043e\u043e\u043f\u0435\u0440\u0430\u0442\u0438\u0432'
UA_SURVIVAL = '\u0432\u0438\u0436\u0438\u0432'
UA_OPEN_WORLD = '\u0432\u0456\u0434\u043a\u0440\u0438\u0442\u043e\u0433\u043e \u0441\u0432\u0456\u0442\u0443'
UA_BUILDING = '\u0431\u0443\u0434\u0456\u0432\u043d\u0438\u0446\u0442\u0432\u043e'
UA_STRATEGY = '\u0441\u0442\u0440\u0430\u0442\u0435\u0433'
UA_INDIE = '\u0456\u043d\u0434\u0456'
UA_RACING = '\u043f\u0435\u0440\u0435\u0433\u043e\u043d\u0438'
UA_SPORT = '\u0441\u043f\u043e\u0440\u0442'
UA_COLONY = '\u043a\u043e\u043b\u043e\u043d'
UA_PARK = '\u043f\u0430\u0440\u043a'


def select_editorial_phrase(offer: Offer) -> str | None:
    if offer.is_event:
        return None

    text = _combined_text(
        offer.title,
        offer.tags,
        offer.genres,
        offer.metadata.get('tags'),
        offer.metadata.get('genres'),
        offer.short_description,
        offer.description,
    )
    review_score = int(offer.review_score or 0)
    review_count = int(offer.review_count or 0)

    identity_phrase = _select_identity_phrase(text)
    if identity_phrase is not None:
        return identity_phrase

    quality_phrase = _select_quality_phrase(text, review_score, review_count)
    if quality_phrase is not None:
        return quality_phrase

    popularity_phrase = _select_popularity_phrase(offer.source, review_score, review_count)
    if popularity_phrase is not None:
        return popularity_phrase

    return None


def _select_identity_phrase(text: str) -> str | None:
    if _contains_any(text, 'city builder', 'city building', 'city simulation', UA_CITY_BUILD, UA_CITY_SIM):
        return IDENTITY_PHRASES['city builder']

    if _contains_any(text, 'factory builder', 'factory building', 'building factories', UA_FACTORY_BUILD, UA_BUILD_FACTORIES, UA_FACTORIES, UA_CONVEYOR):
        return IDENTITY_PHRASES['factory']

    if _contains_any(text, 'tower defense', 'tower defense fest', 'tower defense experience', ' td '):
        return IDENTITY_PHRASES['tower defense']

    if _contains_any(text, 'deckbuilder', 'deck building', 'deckbuilding', UA_DECKBUILDER) or (_contains_any(text, UA_CARDS) and _contains_any(text, UA_DECK, 'deck')):
        return IDENTITY_PHRASES['deckbuilder']

    if _contains_any(text, 'roguelike', 'rogue like', 'roguelite', 'rogue lite', UA_ROGUELIKE, UA_ROGUELIKE_GEN, UA_ROGUELIKE_INST):
        return IDENTITY_PHRASES['roguelike']

    if _contains_any(text, 'metroidvania', UA_METROIDVANIA):
        return IDENTITY_PHRASES['metroidvania']

    if _contains_any(text, 'co op', 'coop', 'cooperative', 'co-op', UA_COOP):
        return IDENTITY_PHRASES['co-op']

    if _contains_any(text, 'survival', UA_SURVIVAL) and _contains_any(text, 'sandbox', 'open world', UA_OPEN_WORLD, 'crafting', 'building', UA_BUILDING):
        return IDENTITY_PHRASES['survival']

    if _contains_any(text, 'colony sim', 'colony builder', 'colony management', 'colony', UA_COLONY):
        return IDENTITY_PHRASES['colony']

    if _contains_any(text, 'park builder', 'theme park', 'park management', UA_PARK):
        return IDENTITY_PHRASES['park']

    if _contains_any(text, 'racing', 'racer', UA_RACING):
        return IDENTITY_PHRASES['racing']

    if _contains_any(text, 'sports', 'sport', UA_SPORT):
        return IDENTITY_PHRASES['sports']

    if _contains_any(text, 'strategy', UA_STRATEGY):
        return IDENTITY_PHRASES['strategy']

    return None


def _select_quality_phrase(text: str, review_score: int, review_count: int) -> str | None:
    if _contains_any(text, 'indie', UA_INDIE) and review_score >= 92 and 500 <= review_count < 10000:
        return 'Hidden indie gem'

    if _contains_any(text, 'indie', UA_INDIE) and review_score >= 88 and review_count >= 500:
        return 'Top rated indie'

    if review_score >= 96 and review_count >= 5000:
        return 'Critically loved'

    if review_score >= 90 and review_count >= 20000:
        return 'Community favorite'

    if review_score >= 85 and review_count >= 5000:
        return 'Player favorite'

    return None


def _select_popularity_phrase(source: OfferSource, review_score: int, review_count: int) -> str | None:
    if source == OfferSource.STEAM and review_score >= 90 and review_count >= 100000:
        return 'Steam bestseller'

    if review_count >= 50000:
        return 'Trending hit'

    if review_count >= 20000:
        return 'Fan favorite'

    return None


def _combined_text(*groups: object) -> str:
    parts: list[str] = []
    for group in groups:
        for value in _flatten_values(group):
            normalized = ' '.join(str(value).strip().lower().replace('_', ' ').replace('-', ' ').split())
            if normalized:
                parts.append(normalized)
    return ' | '.join(parts)


def _flatten_values(value: object) -> Iterable[str]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, dict):
        flattened: list[str] = []
        for item in value.values():
            flattened.extend(_flatten_values(item))
        return tuple(flattened)
    if isinstance(value, Iterable):
        flattened = []
        for item in value:
            flattened.extend(_flatten_values(item))
        return tuple(flattened)
    return (str(value),)


def _contains_any(text: str, *needles: str) -> bool:
    normalized_text = f' {text} '
    for needle in needles:
        token = ' '.join(str(needle).strip().lower().replace('_', ' ').replace('-', ' ').split())
        if token and token in normalized_text:
            return True
    return False
