from __future__ import annotations

from datetime import datetime
import json
import re
from pathlib import Path

from domain.entities.offer import AssetBundle, ConfidenceLevels, Offer, OfferKind, OfferSource


def sanitize_title(title: str) -> str:
    cleaned = title or ''
    for token in (' Complete Edition', ' Remastered', ' Definitive Edition'):
        cleaned = cleaned.replace(token, '')
    cleaned = cleaned.replace('\u2122', '').replace('\u00ae', '')
    return re.sub(r'\s+', ' ', cleaned).strip()


def build_franchise_key(title: str) -> str:
    cleaned = sanitize_title(title)
    words = [token.lower() for token in re.findall(r"[\w']+", cleaned, flags=re.UNICODE) if len(token) > 1]
    ignored = {'the', 'edition', 'ultimate', 'complete', 'definitive', 'game', 'of', 'and', 'hd'}
    words = [word for word in words if word not in ignored]
    return '-'.join(words[:2]) or cleaned.lower()


def normalize_steam_search_row(raw: dict) -> Offer:
    title = sanitize_title(raw['title'])
    price_before_minor = raw.get('price_before')
    price_after_minor = raw.get('price_after')
    offer_kind = OfferKind.FREEBIE if (price_after_minor == 0 and (price_before_minor or 0) > 0) else OfferKind.DISCOUNT
    return Offer(
        offer_id=f"steam:{raw['app_id']}",
        source=OfferSource.STEAM,
        source_ref=str(raw['app_id']),
        offer_kind=offer_kind,
        game_id=str(raw['app_id']),
        franchise_key=build_franchise_key(title),
        title=title,
        store_url=raw['store_url'],
        price_before_minor=price_before_minor,
        price_after_minor=price_after_minor,
        currency='UAH',
        discount_percent=int(raw.get('discount_percent') or 0),
        promo_start=None,
        promo_end=None,
        review_score=None,
        review_count=None,
        achievements_count=None,
        has_trading_cards=False,
        tags=[],
        genres=[],
        assets=AssetBundle(hero=raw.get('image_url'), header=raw.get('image_url'), fallback=raw.get('image_url')),
        confidence_levels=ConfidenceLevels(price_confidence=0.85, deadline_confidence=0.3, asset_confidence=0.6),
    )


def normalize_epic_offer(raw: dict, now: datetime) -> Offer | None:
    promotions = ((raw.get('promotions') or {}).get('promotionalOffers') or [])
    active_offer = None
    for block in promotions:
        for promo in block.get('promotionalOffers') or []:
            start = datetime.fromisoformat(promo['startDate'].replace('Z', '+00:00')).replace(tzinfo=None)
            end = datetime.fromisoformat(promo['endDate'].replace('Z', '+00:00')).replace(tzinfo=None)
            if start <= now <= end:
                active_offer = promo
                break
        if active_offer:
            break
    if active_offer is None:
        return None

    mappings = ((raw.get('catalogNs') or {}).get('mappings') or [])
    slug = mappings[0].get('pageSlug') if mappings else (raw.get('productSlug') or '').strip('/')
    if not slug:
        return None
    title = sanitize_title(raw.get('title') or slug)
    images = raw.get('keyImages') or []
    hero = None
    for image in images:
        if image.get('type') in {'DieselStoreFrontWide', 'OfferImageWide', 'Thumbnail'}:
            hero = image.get('url')
            break
    if not hero and images:
        hero = images[0].get('url')

    total_price = ((raw.get('price') or {}).get('totalPrice') or {})
    original_price = total_price.get('originalPrice')
    return Offer(
        offer_id=f"epic:{raw.get('id') or slug}",
        source=OfferSource.EPIC,
        source_ref=raw.get('id') or slug,
        offer_kind=OfferKind.FREEBIE,
        game_id=raw.get('id') or slug,
        franchise_key=build_franchise_key(title),
        title=title,
        store_url=f'https://store.epicgames.com/uk/p/{slug}',
        price_before_minor=original_price,
        price_after_minor=0,
        currency=(total_price.get('currencyCode') or 'UAH').upper(),
        discount_percent=100,
        promo_start=datetime.fromisoformat(active_offer['startDate'].replace('Z', '+00:00')).replace(tzinfo=None),
        promo_end=datetime.fromisoformat(active_offer['endDate'].replace('Z', '+00:00')).replace(tzinfo=None),
        review_score=None,
        review_count=None,
        achievements_count=None,
        has_trading_cards=False,
        tags=[c.get('path', '').split('/')[-1] for c in raw.get('categories') or [] if c.get('path')],
        genres=[c.get('path', '').split('/')[-1] for c in raw.get('categories') or [] if c.get('path')],
        assets=AssetBundle(hero=hero, header=hero, screenshot=hero, fallback=hero),
        confidence_levels=ConfidenceLevels(price_confidence=0.8, deadline_confidence=0.95, asset_confidence=0.8),
        description=raw.get('description') or '',
        short_description=raw.get('description') or '',
        publisher_name=raw.get('seller', {}).get('name') if isinstance(raw.get('seller'), dict) else None,
    )


def normalize_auto_event(raw: dict, now: datetime) -> Offer | None:
    return _normalize_event_record(raw, now)


def normalize_calendar_events(path: Path, now: datetime) -> list[Offer]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding='utf-8-sig'))
    events = payload.get('events') or []
    offers: list[Offer] = []
    for event in events:
        normalized = _normalize_event_record(event, now)
        if normalized is not None:
            offers.append(normalized)
    return offers


def _normalize_event_record(event: dict, now: datetime) -> Offer | None:
    starts_at = event.get('starts_at')
    ends_at = event.get('ends_at')
    if not starts_at or not ends_at:
        return None
    start = datetime.fromisoformat(starts_at.replace('Z', '+00:00')).replace(tzinfo=None)
    end = datetime.fromisoformat(ends_at.replace('Z', '+00:00')).replace(tzinfo=None)
    if end < now:
        return None

    title = sanitize_title(event.get('title') or 'Steam Event')
    event_id = str(event.get('id') or title)
    hashtags = _normalize_event_tags(event.get('hashtags') or [])
    image_url = event.get('image_url')
    description = (event.get('description') or '').strip()

    return Offer(
        offer_id=f'event:{event_id}',
        source=OfferSource.EVENT,
        source_ref=event_id,
        offer_kind=OfferKind.FESTIVAL,
        game_id=event_id,
        franchise_key=build_franchise_key(title),
        title=title,
        store_url=event.get('url') or 'https://store.steampowered.com/',
        price_before_minor=None,
        price_after_minor=None,
        currency='UAH',
        discount_percent=0,
        promo_start=start,
        promo_end=end,
        review_score=None,
        review_count=None,
        achievements_count=None,
        has_trading_cards=False,
        tags=hashtags,
        genres=hashtags,
        assets=AssetBundle(hero=image_url, header=image_url, screenshot=image_url, fallback=image_url),
        confidence_levels=ConfidenceLevels(price_confidence=0.0, deadline_confidence=1.0, asset_confidence=0.7),
        description=description,
        short_description=description,
    )


def _normalize_event_tags(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value).strip().lstrip('#')
        if not cleaned:
            continue
        token = cleaned.lower().replace(' ', '_').replace('-', '_')
        if token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized

