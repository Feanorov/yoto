from __future__ import annotations

from dataclasses import replace
import logging

from domain.entities.offer import AssetBundle, ConfidenceLevels, Offer
from infrastructure.clients.base_http import CircuitOpenError
from infrastructure.clients.steam_client import SteamClient


class EnrichOfferUseCase:
    def __init__(self, steam_client: SteamClient) -> None:
        self.steam_client = steam_client
        self.logger = logging.getLogger(__name__)

    async def enrich(self, offers: list[Offer], limit: int) -> list[Offer]:
        enriched: list[Offer] = []
        steam_candidates = [offer for offer in offers if offer.source.value == 'steam'][:limit]
        steam_passthrough = [offer for offer in offers if offer.source.value == 'steam'][limit:]
        pass_through = [offer for offer in offers if offer.source.value != 'steam']

        for index, offer in enumerate(steam_candidates):
            try:
                details = await self.steam_client.get_app_details(offer.source_ref)
                if details is None:
                    enriched.append(self._partial_offer(offer, 'missing_appdetails'))
                    continue
                offer_type = (details.get('type') or '').lower()
                categories = details.get('categories') or []
                screenshots = details.get('screenshots') or []
                price_overview = details.get('price_overview') or {}
                reviews = await self.steam_client.get_reviews(offer.source_ref)
                review_summary = reviews.get('query_summary') or {}
                total_positive = int(review_summary.get('total_positive') or 0)
                total_negative = int(review_summary.get('total_negative') or 0)
                review_count = total_positive + total_negative
                review_score = round((total_positive / review_count) * 100) if review_count else None
                promo_end = await self.steam_client.get_deadline(offer.source_ref)
                enriched.append(
                    replace(
                        offer,
                        title=details.get('name') or offer.title,
                        price_before_minor=price_overview.get('initial') or offer.price_before_minor,
                        price_after_minor=price_overview.get('final') or offer.price_after_minor,
                        currency=(price_overview.get('currency') or offer.currency).upper(),
                        discount_percent=int(price_overview.get('discount_percent') or offer.discount_percent),
                        promo_end=promo_end.replace(tzinfo=None) if promo_end else offer.promo_end,
                        review_score=review_score,
                        review_count=review_count,
                        achievements_count=((details.get('achievements') or {}).get('total') if isinstance(details.get('achievements'), dict) else None),
                        has_trading_cards=any(
                            entry.get('id') == 29 or 'card' in (entry.get('description', '').lower())
                            for entry in categories
                        ),
                        tags=[entry.get('description') for entry in details.get('genres') or [] if entry.get('description')],
                        genres=[entry.get('description') for entry in details.get('genres') or [] if entry.get('description')],
                        assets=AssetBundle(
                            hero=details.get('header_image') or offer.assets.hero,
                            header=details.get('capsule_imagev5') or details.get('header_image') or offer.assets.header,
                            screenshot=(screenshots[0].get('path_full') if screenshots else offer.assets.screenshot),
                            fallback=offer.assets.fallback or details.get('header_image'),
                        ),
                        confidence_levels=ConfidenceLevels(
                            price_confidence=0.95 if price_overview else offer.confidence_levels.price_confidence,
                            deadline_confidence=0.75 if promo_end else 0.35,
                            asset_confidence=0.9 if screenshots or details.get('header_image') else offer.confidence_levels.asset_confidence,
                        ),
                        description=details.get('detailed_description') or offer.description,
                        short_description=details.get('short_description') or offer.short_description,
                        publisher_name=((details.get('publishers') or [None])[0]),
                        developer_name=((details.get('developers') or [None])[0]),
                        adult_flag=(int(details.get('required_age') or 0) >= 18),
                        is_dlc=offer_type == 'dlc',
                        is_soundtrack=(offer_type == 'music' or 'soundtrack' in (details.get('name', '').lower())),
                        is_demo=offer_type == 'demo',
                        metadata={
                            **offer.metadata,
                            'offer_type': offer_type,
                            'source_state': self.steam_client.source_state['mode'],
                            'steam_partial_enrichment': False,
                        },
                    )
                )
            except CircuitOpenError as exc:
                self.logger.warning('Steam enrich paused by circuit breaker: %s', exc)
                enriched.extend(self._partial_offer(item, 'circuit_open') for item in steam_candidates[index:])
                break
            except Exception as exc:
                self.logger.warning('Steam enrich degraded for %s: %s', offer.source_ref, exc)
                enriched.append(self._partial_offer(offer, str(exc)))

        enriched.extend(steam_passthrough)
        enriched.extend(pass_through)
        return enriched

    def _partial_offer(self, offer: Offer, reason: str) -> Offer:
        state = self.steam_client.source_state
        return replace(
            offer,
            metadata={
                **offer.metadata,
                'source_state': state['mode'],
                'steam_state_reason': state['reason'],
                'steam_partial_enrichment': True,
                'steam_partial_reason': reason,
            },
        )