from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class OfferSource(str, Enum):
    STEAM = 'steam'
    EPIC = 'epic'
    EVENT = 'event'


class OfferKind(str, Enum):
    DISCOUNT = 'discount'
    FREEBIE = 'freebie'
    FESTIVAL = 'festival'
    EVENT = 'event'


@dataclass(frozen=True, slots=True)
class AssetBundle:
    hero: str | None = None
    header: str | None = None
    screenshot: str | None = None
    fallback: str | None = None


@dataclass(frozen=True, slots=True)
class ConfidenceLevels:
    price_confidence: float = 1.0
    deadline_confidence: float = 0.5
    asset_confidence: float = 0.8


@dataclass(slots=True)
class Offer:
    offer_id: str
    source: OfferSource
    source_ref: str
    offer_kind: OfferKind
    game_id: str
    franchise_key: str
    title: str
    store_url: str
    price_before_minor: int | None
    price_after_minor: int | None
    currency: str
    discount_percent: int
    promo_start: datetime | None
    promo_end: datetime | None
    review_score: int | None
    review_count: int | None
    achievements_count: int | None
    has_trading_cards: bool
    tags: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    assets: AssetBundle = field(default_factory=AssetBundle)
    confidence_levels: ConfidenceLevels = field(default_factory=ConfidenceLevels)
    description: str = ''
    short_description: str = ''
    publisher_name: str | None = None
    developer_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    adult_flag: bool = False
    is_dlc: bool = False
    is_soundtrack: bool = False
    is_demo: bool = False

    @property
    def is_freebie(self) -> bool:
        return self.offer_kind == OfferKind.FREEBIE or ((self.price_after_minor or 0) == 0 and (self.price_before_minor or 0) > 0)

    @property
    def is_event(self) -> bool:
        return self.offer_kind in {OfferKind.FESTIVAL, OfferKind.EVENT}

    @property
    def primary_asset_url(self) -> str | None:
        return self.assets.hero or self.assets.header or self.assets.screenshot or self.assets.fallback

    def to_snapshot(self) -> dict[str, Any]:
        return {
            'offer_id': self.offer_id,
            'source': self.source.value,
            'source_ref': self.source_ref,
            'offer_kind': self.offer_kind.value,
            'game_id': self.game_id,
            'franchise_key': self.franchise_key,
            'title': self.title,
            'store_url': self.store_url,
            'price_before_minor': self.price_before_minor,
            'price_after_minor': self.price_after_minor,
            'currency': self.currency,
            'discount_percent': self.discount_percent,
            'promo_start': self.promo_start.isoformat() if self.promo_start else None,
            'promo_end': self.promo_end.isoformat() if self.promo_end else None,
            'review_score': self.review_score,
            'review_count': self.review_count,
            'achievements_count': self.achievements_count,
            'has_trading_cards': self.has_trading_cards,
            'tags': self.tags,
            'genres': self.genres,
            'assets': {
                'hero': self.assets.hero,
                'header': self.assets.header,
                'screenshot': self.assets.screenshot,
                'fallback': self.assets.fallback,
            },
            'confidence_levels': {
                'price_confidence': self.confidence_levels.price_confidence,
                'deadline_confidence': self.confidence_levels.deadline_confidence,
                'asset_confidence': self.confidence_levels.asset_confidence,
            },
            'description': self.description,
            'short_description': self.short_description,
            'publisher_name': self.publisher_name,
            'developer_name': self.developer_name,
            'metadata': self.metadata,
            'adult_flag': self.adult_flag,
            'is_dlc': self.is_dlc,
            'is_soundtrack': self.is_soundtrack,
            'is_demo': self.is_demo,
        }

    @classmethod
    def from_snapshot(cls, payload: dict[str, Any]) -> 'Offer':
        promo_start = payload.get('promo_start')
        promo_end = payload.get('promo_end')
        assets = payload.get('assets') or {}
        confidence = payload.get('confidence_levels') or {}
        return cls(
            offer_id=payload['offer_id'],
            source=OfferSource(payload['source']),
            source_ref=payload['source_ref'],
            offer_kind=OfferKind(payload['offer_kind']),
            game_id=payload['game_id'],
            franchise_key=payload['franchise_key'],
            title=payload['title'],
            store_url=payload['store_url'],
            price_before_minor=payload.get('price_before_minor'),
            price_after_minor=payload.get('price_after_minor'),
            currency=payload.get('currency') or 'UAH',
            discount_percent=int(payload.get('discount_percent') or 0),
            promo_start=datetime.fromisoformat(promo_start) if promo_start else None,
            promo_end=datetime.fromisoformat(promo_end) if promo_end else None,
            review_score=payload.get('review_score'),
            review_count=payload.get('review_count'),
            achievements_count=payload.get('achievements_count'),
            has_trading_cards=bool(payload.get('has_trading_cards', False)),
            tags=list(payload.get('tags') or []),
            genres=list(payload.get('genres') or []),
            assets=AssetBundle(
                hero=assets.get('hero'),
                header=assets.get('header'),
                screenshot=assets.get('screenshot'),
                fallback=assets.get('fallback'),
            ),
            confidence_levels=ConfidenceLevels(
                price_confidence=float(confidence.get('price_confidence', 1.0)),
                deadline_confidence=float(confidence.get('deadline_confidence', 0.5)),
                asset_confidence=float(confidence.get('asset_confidence', 0.8)),
            ),
            description=payload.get('description') or '',
            short_description=payload.get('short_description') or '',
            publisher_name=payload.get('publisher_name'),
            developer_name=payload.get('developer_name'),
            metadata=dict(payload.get('metadata') or {}),
            adult_flag=bool(payload.get('adult_flag', False)),
            is_dlc=bool(payload.get('is_dlc', False)),
            is_soundtrack=bool(payload.get('is_soundtrack', False)),
            is_demo=bool(payload.get('is_demo', False)),
        )