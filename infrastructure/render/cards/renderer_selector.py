from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import logging
import math
import os
from pathlib import Path
import re
import subprocess
from typing import Any
from urllib.parse import unquote, urlparse

from PIL import Image, ImageFilter, ImageStat

from application.editorial import select_editorial_phrase
from domain.entities.offer import Offer, OfferKind, OfferSource
from infrastructure.clients.base_http import ResilientHttpClient
from infrastructure.render.cards.asset_source import resolve_existing_asset_path
from infrastructure.render.cards.template_system import TemplateSystem
from infrastructure.render.cards.yoto_card_engine_v4 import YotoCardData, YotoCardEngineV4, YotoCardType


PRIMARY_RENDERER_MODE = 'yoto_v4'
RENDERER_MODE_ALIASES = {'legacy': 'legacy', 'yoto_v4': PRIMARY_RENDERER_MODE, 'yoto_v42': PRIMARY_RENDERER_MODE}
VALID_RENDERER_MODES = set(RENDERER_MODE_ALIASES)
DEBUG_TRUE_VALUES = {'1', 'true', 'yes', 'on'}
LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class RoutedRenderDiagnostics:
    template_id: str
    asset_used: str | None
    title_lines: list[str] = field(default_factory=list)
    clipped_fields: list[str] = field(default_factory=list)
    render_warnings: list[str] = field(default_factory=list)
    hero_asset_used: str | None = None
    layout_variant: str | None = None
    hero_mode: str | None = None
    title_font_size: int | None = None
    hero_rect: tuple[int, int, int, int] | None = None
    info_rect: tuple[int, int, int, int] | None = None
    badge_rect: tuple[int, int, int, int] | None = None
    renderer_family: str = 'legacy'
    renderer_requested: str = 'legacy'
    renderer_selected: str = 'legacy'
    renderer_fallback_used: bool = False
    gameplay_count: int = 0
    has_gameplay_strip: bool = False
    gameplay_candidates_count: int = 0
    gameplay_selected_count: int = 0
    gameplay_selection_reason: str = 'no_candidates_available'
    gameplay_rejected_ui_like: int = 0
    gameplay_score_summary: list[dict[str, Any]] = field(default_factory=list)
    gameplay_selection: dict[str, Any] = field(default_factory=dict)
    editorial_phrase: str | None = None
    hero_source_type: str = 'placeholder'
    hero_selection_reason: str = 'intentional_fallback'
    hero_candidates_count: int = 0
    hero_rejected_capsules: list[dict[str, Any]] = field(default_factory=list)
    hero_score_summary: list[dict[str, Any]] = field(default_factory=list)
    hero_capsule_rejected: bool = False
    hero_fallback_used: bool = False
    hero_selection: dict[str, Any] = field(default_factory=dict)

    def to_snapshot(self) -> dict[str, object]:
        return {
            'template_id': self.template_id,
            'asset_used': self.asset_used,
            'title_lines': self.title_lines,
            'clipped_fields': self.clipped_fields,
            'render_warnings': self.render_warnings,
            'hero_asset_used': self.hero_asset_used,
            'layout_variant': self.layout_variant,
            'hero_mode': self.hero_mode,
            'title_font_size': self.title_font_size,
            'hero_rect': self.hero_rect,
            'info_rect': self.info_rect,
            'badge_rect': self.badge_rect,
            'renderer_family': self.renderer_family,
            'renderer_requested': self.renderer_requested,
            'renderer_selected': self.renderer_selected,
            'renderer_fallback_used': self.renderer_fallback_used,
            'gameplay_count': self.gameplay_count,
            'has_gameplay_strip': self.has_gameplay_strip,
            'gameplay_candidates_count': self.gameplay_candidates_count,
            'gameplay_selected_count': self.gameplay_selected_count,
            'gameplay_selection_reason': self.gameplay_selection_reason,
            'gameplay_rejected_ui_like': self.gameplay_rejected_ui_like,
            'gameplay_score_summary': self.gameplay_score_summary,
            'gameplay_selection': self.gameplay_selection,
            'editorial_phrase': self.editorial_phrase,
            'hero_source_type': self.hero_source_type,
            'hero_selection_reason': self.hero_selection_reason,
            'hero_candidates_count': self.hero_candidates_count,
            'hero_rejected_capsules': self.hero_rejected_capsules,
            'hero_score_summary': self.hero_score_summary,
            'hero_capsule_rejected': self.hero_capsule_rejected,
            'hero_fallback_used': self.hero_fallback_used,
            'hero_selection': self.hero_selection,
        }


@dataclass(slots=True)
class RoutedRenderResult:
    image_path: Path
    assets_used: list[str]
    diagnostics: RoutedRenderDiagnostics


class YotoCardRendererV42Adapter:
    def __init__(self, output_dir: Path, cache_dir: Path | None = None) -> None:
        self.output_dir = output_dir
        self.cache_dir = cache_dir or (output_dir / '.yoto_v42_asset_cache')
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.engine = YotoCardEngineV4(output_dir)
        self.debug_hero_selection = os.getenv('CARD_RENDERER_DEBUG_HERO_SELECTION', '').strip().lower() in DEBUG_TRUE_VALUES
        self.debug_gameplay_selection = os.getenv('CARD_RENDERER_DEBUG_GAMEPLAY_SELECTION', '').strip().lower() in DEBUG_TRUE_VALUES
        self._visual_score_cache: dict[tuple[str, str, str], dict[str, Any]] = {}

    async def render(self, http: ResilientHttpClient, offer: Offer, template_id: str) -> RoutedRenderResult:
        card_type = self._card_type_for_offer(offer, template_id)
        hero_candidates = self._asset_candidates(offer)
        gameplay_candidates = self._gameplay_candidates(offer)
        hero_asset_urls = [url for url, _ in hero_candidates]
        gameplay_asset_urls = [url for url, _ in gameplay_candidates]
        asset_urls = self._merge_asset_urls(hero_candidates, gameplay_candidates)
        downloaded_assets: dict[str, Path] = {}
        for asset_url in asset_urls:
            path = await self._download_asset(http, asset_url)
            if path is not None:
                downloaded_assets[asset_url] = path

        hero_evaluations = self._evaluate_hero_candidates(card_type, hero_candidates, downloaded_assets)
        hero_url, hero_selection = self._select_hero_candidate(card_type, hero_evaluations)
        hero_path = downloaded_assets.get(hero_url) if hero_url else None
        gameplay_context = self._gameplay_context(offer)
        gameplay_evaluations = self._evaluate_gameplay_candidates(card_type, gameplay_candidates, downloaded_assets, gameplay_context)
        gameplay_urls, gameplay_selection = self._select_gameplay_frames(card_type, gameplay_evaluations, hero_url)
        gameplay_paths = [downloaded_assets[url] for url in gameplay_urls if url in downloaded_assets]
        editorial_phrase = select_editorial_phrase(offer)

        data = YotoCardData(
            title=offer.title,
            platform=self._platform_name(offer),
            type=card_type,
            deadline=self._deadline_text(offer, card_type),
            old_price=self._old_price_text(offer),
            current_price=self._current_price_text(offer, card_type),
            artwork_path=hero_path,
            slug=f'{template_id}_{offer.offer_id}_{offer.title}',
            platform_badge=self._platform_badge_text(offer, template_id, card_type),
            brand_micro_label=self._brand_micro_label(card_type),
            editorial_phrase=editorial_phrase,
            gameplay_images=gameplay_paths or None,
            gameplay_selection=gameplay_selection,
            hero_selection=hero_selection,
            lane=str((offer.metadata or {}).get('lane') or '') or None,
        )
        result = self.engine.render_card(data)
        if self.debug_hero_selection:
            self._log_hero_selection(offer, template_id, result.diagnostics.hero_selection)
        if self.debug_gameplay_selection:
            self._log_gameplay_selection(offer, template_id, result.diagnostics.gameplay_selection)

        render_warnings: list[str] = []
        available_hero_assets = [url for url in hero_asset_urls if url in downloaded_assets]
        available_gameplay_assets = [url for url in gameplay_asset_urls if url in downloaded_assets]
        if result.diagnostics.used_placeholder_artwork:
            render_warnings.append('fallback_artwork')
        if hero_asset_urls and not available_hero_assets:
            render_warnings.append('primary_asset_download_failed')
        elif hero_asset_urls and hero_url is None:
            render_warnings.append('hero_selection_fallback')
        if any(url not in downloaded_assets for url in hero_asset_urls) and hero_url is None and not available_hero_assets:
            render_warnings.append('asset_downloads_unavailable')
        if gameplay_asset_urls and not available_gameplay_assets:
            render_warnings.append('gameplay_assets_unavailable')

        title_clipped = any(line.endswith('...') for line in result.diagnostics.title_lines)
        diagnostics = RoutedRenderDiagnostics(
            template_id=template_id,
            asset_used=hero_url,
            title_lines=list(result.diagnostics.title_lines),
            clipped_fields=['title'] if title_clipped else [],
            render_warnings=render_warnings,
            hero_asset_used=hero_url,
            layout_variant=f'{PRIMARY_RENDERER_MODE}_{card_type.value.lower()}',
            hero_mode='hero_with_gameplay_strip' if result.diagnostics.has_gameplay_strip else 'hero_only',
            title_font_size=None,
            hero_rect=result.diagnostics.hero_rect,
            info_rect=result.diagnostics.lower_third_rect,
            badge_rect=None,
            renderer_family=PRIMARY_RENDERER_MODE,
            renderer_requested=PRIMARY_RENDERER_MODE,
            renderer_selected=PRIMARY_RENDERER_MODE,
            renderer_fallback_used=False,
            gameplay_count=result.diagnostics.gameplay_count,
            has_gameplay_strip=result.diagnostics.has_gameplay_strip,
            gameplay_candidates_count=result.diagnostics.gameplay_candidates_count,
            gameplay_selected_count=result.diagnostics.gameplay_selected_count,
            gameplay_selection_reason=result.diagnostics.gameplay_selection_reason,
            gameplay_rejected_ui_like=result.diagnostics.gameplay_rejected_ui_like,
            gameplay_score_summary=[dict(item) for item in result.diagnostics.gameplay_score_summary],
            gameplay_selection=dict(result.diagnostics.gameplay_selection),
            editorial_phrase=result.diagnostics.editorial_phrase,
            hero_source_type=result.diagnostics.hero_source_type,
            hero_selection_reason=result.diagnostics.hero_selection_reason,
            hero_candidates_count=result.diagnostics.hero_candidates_count,
            hero_rejected_capsules=[dict(item) for item in result.diagnostics.hero_rejected_capsules],
            hero_score_summary=[dict(item) for item in result.diagnostics.hero_score_summary],
            hero_capsule_rejected=bool(result.diagnostics.hero_rejected_capsules),
            hero_fallback_used=result.diagnostics.hero_fallback_used,
            hero_selection=dict(result.diagnostics.hero_selection),
        )
        assets_used = [url for url in asset_urls if url in downloaded_assets]
        return RoutedRenderResult(image_path=result.image_path, assets_used=assets_used, diagnostics=diagnostics)

    def _card_type_for_offer(self, offer: Offer, template_id: str) -> YotoCardType:
        template = (template_id or '').strip().lower()
        if offer.source == OfferSource.EVENT or offer.offer_kind in {OfferKind.EVENT, OfferKind.FESTIVAL} or template == 'festival_event':
            return YotoCardType.FESTIVAL
        if offer.is_freebie or template in {'epic_free', 'steam_free'}:
            return YotoCardType.FREE_GAME
        if 'top' in template:
            return YotoCardType.TOP_LIST
        return YotoCardType.DISCOUNT

    def _platform_name(self, offer: Offer) -> str:
        if offer.source == OfferSource.EPIC:
            return 'EPIC'
        if offer.source == OfferSource.STEAM:
            return 'STEAM'
        return 'LIVE'

    def _platform_badge_text(self, offer: Offer, template_id: str, card_type: YotoCardType) -> str:
        platform = self._platform_name(offer)
        if card_type == YotoCardType.FESTIVAL:
            if offer.source == OfferSource.EVENT:
                return 'ПОДІЯ'
            return f'ПОДІЯ {platform}' if platform else 'ПОДІЯ'
        if card_type == YotoCardType.FREE_GAME:
            return f'{platform} РОЗДАЧА' if platform else 'РОЗДАЧА'
        if card_type == YotoCardType.TOP_LIST:
            return f'{platform} ТОП' if platform else 'ТОП'
        return f'{platform} ЗНИЖКА' if platform else 'ЗНИЖКА'

    def _brand_micro_label(self, card_type: YotoCardType) -> str:
        if card_type == YotoCardType.FREE_GAME:
            return 'ігрові роздачі'
        if card_type == YotoCardType.FESTIVAL:
            return 'радар подій'
        if card_type == YotoCardType.TOP_LIST:
            return 'вибір редакції'
        return 'сигнал знижок'

    def _asset_candidates(self, offer: Offer) -> list[tuple[str, tuple[str, ...]]]:
        url_to_kinds: dict[str, list[str]] = {}
        for kind, asset in (
            ('hero', offer.assets.hero),
            ('header', offer.assets.header),
            ('screenshot', offer.assets.screenshot),
            ('fallback', offer.assets.fallback),
        ):
            if not asset:
                continue
            kinds = url_to_kinds.setdefault(asset, [])
            if kind not in kinds:
                kinds.append(kind)
        return [(url, tuple(kinds)) for url, kinds in url_to_kinds.items()]

    def _evaluate_hero_candidates(
        self,
        card_type: YotoCardType,
        candidates: list[tuple[str, tuple[str, ...]]],
        downloaded_assets: dict[str, Path],
    ) -> list[dict[str, Any]]:
        evaluations: list[dict[str, Any]] = []
        hero_floor = self._hero_quality_floor(card_type)
        for index, (url, kinds) in enumerate(candidates):
            path = downloaded_assets.get(url)
            source_type = self._primary_source_type(kinds)
            if path is None:
                evaluations.append(
                    {
                        'url': url,
                        'source_type': source_type,
                        'source_types': list(kinds),
                        'score': None,
                        'available': False,
                        'meets_hero_floor': False,
                        'capsule_like': False,
                        'capsule_named': 'capsule' in url.lower(),
                        'text_heavy': False,
                        'logo_dominant': False,
                        'brightness_score': 0.0,
                        'entropy_score': 0.0,
                        'subject_detection_score': 0.0,
                        'ui_heavy': False,
                        'text_coverage_ratio': 0.0,
                        'banner_like': False,
                        'horizontal_text_block': False,
                        'promotional_layout': False,
                        'index': index,
                    }
                )
                continue
            score, analysis = self._inspect_visual_candidate(card_type, url, path, kinds)
            evaluations.append(
                {
                    'url': url,
                    'source_type': source_type,
                    'source_types': list(kinds),
                    'score': score,
                    'available': True,
                    'meets_hero_floor': score >= hero_floor,
                    'capsule_like': analysis['capsule_like'],
                    'capsule_named': analysis['capsule_named'],
                    'text_heavy': analysis['text_heavy'],
                    'logo_dominant': analysis['logo_dominant'],
                    'brightness_score': analysis['brightness_score'],
                    'entropy_score': analysis['entropy_score'],
                    'subject_detection_score': analysis['subject_detection_score'],
                    'ui_heavy': analysis['ui_heavy'],
                    'text_coverage_ratio': analysis['text_coverage_ratio'],
                    'banner_like': analysis['banner_like'],
                    'horizontal_text_block': analysis['horizontal_text_block'],
                    'promotional_layout': analysis['promotional_layout'],
                    'index': index,
                }
            )
        return evaluations

    def _select_hero_candidate(
        self,
        card_type: YotoCardType,
        evaluations: list[dict[str, Any]],
    ) -> tuple[str | None, dict[str, Any]]:
        hero_floor = self._hero_quality_floor(card_type)
        scored = [item for item in evaluations if item['available'] and item['score'] is not None]
        best = max(scored, key=lambda item: (float(item['score']), -int(item['index']))) if scored else None
        selected = best if best is not None and float(best['score']) >= hero_floor else None
        selected_url = str(selected['url']) if selected is not None else None
        rejected_capsules: list[dict[str, Any]] = []
        score_summary: list[dict[str, Any]] = []

        for item in evaluations:
            available = bool(item['available'])
            score = float(item['score']) if item['score'] is not None else None
            selected_flag = selected_url == item['url']
            rejection_reason = None
            if not available:
                rejection_reason = 'asset_unavailable'
            elif not selected_flag:
                if bool(item['capsule_like']) or bool(item['capsule_named']) or bool(item['text_heavy']):
                    rejection_reason = 'capsule_rejected_text_heavy'
                elif bool(item['logo_dominant']):
                    rejection_reason = 'capsule_rejected_logo_dominant'
                elif selected is None and score is not None and score < hero_floor:
                    rejection_reason = 'weak_asset_fallback'
            score_summary.append(
                {
                    'asset_url': item['url'],
                    'source_type': item['source_type'],
                    'source_types': list(item['source_types']),
                    'available': available,
                    'score': round(score, 2) if score is not None else None,
                    'selected': selected_flag,
                    'rejection_reason': rejection_reason,
                    'meets_hero_floor': bool(available and score is not None and score >= hero_floor),
                    'brightness_score': round(float(item.get('brightness_score') or 0.0), 3),
                    'entropy_score': round(float(item.get('entropy_score') or 0.0), 3),
                    'subject_detection_score': round(float(item.get('subject_detection_score') or 0.0), 3),
                    'ui_heavy': bool(item.get('ui_heavy')),
                    'text_coverage_ratio': round(float(item.get('text_coverage_ratio') or 0.0), 3),
                    'banner_like': bool(item.get('banner_like')),
                    'horizontal_text_block': bool(item.get('horizontal_text_block')),
                    'promotional_layout': bool(item.get('promotional_layout')),
                }
            )
            if rejection_reason in {'capsule_rejected_text_heavy', 'capsule_rejected_logo_dominant'}:
                rejected_capsules.append(
                    {
                        'asset_url': item['url'],
                        'source_type': item['source_type'],
                        'score': round(score, 2) if score is not None else None,
                        'reason': rejection_reason,
                    }
                )

        reason = self._hero_selection_reason(selected, rejected_capsules, scored)
        return selected_url, {
            'selected_source': str(selected['source_type']) if selected is not None else 'placeholder',
            'reason': reason,
            'candidates_evaluated': len(evaluations),
            'rejected_capsules': rejected_capsules,
            'score_summary': score_summary,
            'fallback_used': selected is None,
        }

    def _gameplay_candidates(self, offer: Offer) -> list[tuple[str, tuple[str, ...]]]:
        url_to_kinds: dict[str, list[str]] = {}
        if offer.assets.screenshot:
            url_to_kinds[str(offer.assets.screenshot)] = ['primary_screenshot']
        for url in self._extract_gameplay_media_urls(offer):
            kinds = url_to_kinds.setdefault(url, [])
            if 'media_still' not in kinds:
                kinds.append('media_still')
        return [(url, tuple(kinds)) for url, kinds in url_to_kinds.items()]

    def _gameplay_context(self, offer: Offer) -> dict[str, bool]:
        tokens = f" { ' '.join(part for part in [offer.title, *offer.tags, *offer.genres] if part).lower() } "
        ui_relaxed_genre = any(
            keyword in tokens
            for keyword in (
                ' strategy ',
                ' simulation ',
                ' simulator ',
                ' builder ',
                ' building ',
                ' management ',
                ' tycoon ',
                ' tower defense ',
                ' city builder ',
                ' factory ',
                ' automation ',
                ' colony ',
                ' park builder ',
                ' СЃС‚СЂР°С‚РµРі',
                ' СЃРёРјСѓР»СЏС‚РѕСЂ',
                ' РјРµРЅРµРґР¶',
                ' Р±СѓРґС–РІ',
                ' РєРѕР»РѕРЅ',
                ' Р·Р°С…РёСЃС‚ РІРµР¶ ',
                ' td ',
            )
        )
        return {'ui_relaxed_genre': ui_relaxed_genre}

    def _merge_asset_urls(self, *candidate_groups: list[tuple[str, tuple[str, ...]]]) -> list[str]:
        seen: set[str] = set()
        merged: list[str] = []
        for group in candidate_groups:
            for url, _ in group:
                if url in seen:
                    continue
                seen.add(url)
                merged.append(url)
        return merged

    def _evaluate_gameplay_candidates(
        self,
        card_type: YotoCardType,
        candidates: list[tuple[str, tuple[str, ...]]],
        downloaded_assets: dict[str, Path],
        context: dict[str, bool] | None = None,
    ) -> list[dict[str, Any]]:
        evaluations: list[dict[str, Any]] = []
        gameplay_floor = self._gameplay_quality_floor(card_type)
        gameplay_context = context or {}
        for index, (url, kinds) in enumerate(candidates):
            path = downloaded_assets.get(url)
            source_type = self._primary_gameplay_source_type(kinds)
            if path is None:
                evaluations.append(
                    {
                        'url': url,
                        'source_type': source_type,
                        'source_types': list(kinds),
                        'score': None,
                        'available': False,
                        'ui_like': False,
                        'text_heavy': False,
                        'low_info': False,
                        'logo_dominant': False,
                        'steam_ui_like': False,
                        'banner_like': False,
                        'horizontal_text_block': False,
                        'promotional_layout': False,
                        'aspect_mismatched': False,
                        'text_coverage_ratio': 0.0,
                        'ui_relaxed_candidate': False,
                        'scene_richness_score': 0.0,
                        'luminance': 0.0,
                        'edge_mean': 0.0,
                        'dark_ratio': 1.0,
                        'meets_gameplay_floor': False,
                        'group_key': self._gameplay_media_key(url),
                        'scene_vector': (),
                        'color_histogram_signature': (),
                        'composition_signature': (),
                        'index': index,
                    }
                )
                continue
            score, analysis = self._inspect_gameplay_candidate(card_type, url, path, kinds, gameplay_context)
            evaluations.append(
                {
                    'url': url,
                    'source_type': source_type,
                    'source_types': list(kinds),
                    'score': score,
                    'available': True,
                    'ui_like': analysis['ui_like'],
                    'text_heavy': analysis['text_heavy'],
                    'low_info': analysis['low_info'],
                    'logo_dominant': analysis['logo_dominant'],
                    'steam_ui_like': analysis['steam_ui_like'],
                    'banner_like': analysis['banner_like'],
                    'horizontal_text_block': analysis['horizontal_text_block'],
                    'promotional_layout': analysis['promotional_layout'],
                    'aspect_mismatched': analysis['aspect_mismatched'],
                    'text_coverage_ratio': analysis['text_coverage_ratio'],
                    'ui_relaxed_candidate': analysis['ui_relaxed_candidate'],
                    'scene_richness_score': analysis['scene_richness_score'],
                    'luminance': analysis['luminance'],
                    'edge_mean': analysis['edge_mean'],
                    'dark_ratio': analysis['dark_ratio'],
                    'meets_gameplay_floor': score >= gameplay_floor,
                    'group_key': analysis['group_key'],
                    'scene_vector': analysis['scene_vector'],
                    'color_histogram_signature': analysis['color_histogram_signature'],
                    'composition_signature': analysis['composition_signature'],
                    'index': index,
                }
            )
        return evaluations

    def _select_gameplay_frames(
        self,
        card_type: YotoCardType,
        evaluations: list[dict[str, Any]],
        primary_url: str | None,
    ) -> tuple[list[str], dict[str, Any]]:
        gameplay_floor = self._gameplay_quality_floor(card_type)
        available = [item for item in evaluations if item['available']]
        primary_item = next((item for item in available if primary_url and item['url'] == primary_url), None)
        preferred_available = [item for item in available if item is not primary_item]
        ranked = sorted(
            preferred_available,
            key=lambda item: (
                -float(item['score']),
                int(bool(item['ui_like']) or bool(item['text_heavy']) or bool(item.get('promotional_layout'))),
                int(bool(item['low_info'])),
                int(item['index']),
            ),
        )

        strong_candidates = [item for item in ranked if self._is_strong_gameplay_candidate(item, gameplay_floor)]
        primary_is_strong = primary_item is not None and self._is_strong_gameplay_candidate(primary_item, gameplay_floor)
        promo_heavy_set = self._is_promo_heavy_gameplay_set(preferred_available)
        selected_items: list[dict[str, Any]] = []
        seen_groups: set[str] = set()
        similar_rejections: set[str] = set()
        residual_reason: str | None = None
        for item in strong_candidates:
            group_key = str(item.get('group_key') or item['url'])
            if group_key in seen_groups:
                continue
            if selected_items and not self._passes_gameplay_diversity(item, selected_items):
                similar_rejections.add(str(item['url']))
                continue
            selected_items.append(item)
            seen_groups.add(group_key)
            if len(selected_items) >= 3:
                break

        if not selected_items:
            for item in ranked:
                fallback_reason = self._borderline_gameplay_reason(item, gameplay_floor, promo_heavy_set=promo_heavy_set)
                if fallback_reason is None:
                    continue
                selected_items.append(item)
                seen_groups.add(str(item.get('group_key') or item['url']))
                residual_reason = fallback_reason
                break

        selected_primary_fallback = False
        if primary_is_strong and residual_reason is None and len(selected_items) < 2:
            primary_group_key = str(primary_item.get('group_key') or primary_item['url'])
            if primary_group_key not in seen_groups and (
                not selected_items or self._passes_gameplay_diversity(primary_item, selected_items)
            ):
                selected_items.append(primary_item)
                seen_groups.add(primary_group_key)
                selected_primary_fallback = True
        elif not selected_items and primary_item is not None:
            primary_fallback_reason = self._borderline_gameplay_reason(
                primary_item,
                gameplay_floor,
                promo_heavy_set=promo_heavy_set,
                allow_primary=True,
            )
            if primary_fallback_reason is not None:
                selected_items.append(primary_item)
                seen_groups.add(str(primary_item.get('group_key') or primary_item['url']))
                residual_reason = primary_fallback_reason
                selected_primary_fallback = True

        selected_urls = [str(item['url']) for item in sorted(selected_items, key=lambda entry: int(entry['index']))]
        selected_url_set = set(selected_urls)
        ui_like_rejected = sum(
            1
            for item in available
            if item['url'] not in selected_url_set
            and (
                bool(item['ui_like'])
                or bool(item['text_heavy'])
                or bool(item.get('promotional_layout'))
            )
        )

        score_summary: list[dict[str, Any]] = []
        for item in evaluations:
            available_flag = bool(item['available'])
            score = float(item['score']) if item['score'] is not None else None
            selected_flag = str(item['url']) in selected_url_set
            rejection_reason = None
            if not available_flag:
                rejection_reason = 'asset_unavailable'
            elif primary_url and str(item['url']) == primary_url and not selected_flag:
                rejection_reason = 'primary_hero_excluded'
            elif not selected_flag:
                if bool(item.get('promotional_layout')) or bool(item.get('horizontal_text_block')):
                    rejection_reason = 'marketing_frame'
                elif bool(item['ui_like']) or bool(item['text_heavy']):
                    rejection_reason = 'ui_like_frame'
                elif bool(item['logo_dominant']):
                    rejection_reason = 'logo_or_title_frame'
                elif str(item['url']) in similar_rejections:
                    rejection_reason = 'similar_scene_rejected'
                elif bool(item['low_info']) or (score is not None and score < gameplay_floor):
                    rejection_reason = 'low_information_frame'
            score_summary.append(
                {
                    'asset_url': item['url'],
                    'source_type': item['source_type'],
                    'source_types': list(item['source_types']),
                    'available': available_flag,
                    'score': round(score, 2) if score is not None else None,
                    'selected': selected_flag,
                    'rejection_reason': rejection_reason,
                    'ui_like': bool(item['ui_like']),
                    'ui_relaxed_candidate': bool(item.get('ui_relaxed_candidate')),
                    'text_heavy': bool(item.get('text_heavy')),
                    'low_info': bool(item['low_info']),
                    'steam_ui_like': bool(item.get('steam_ui_like')),
                    'banner_like': bool(item.get('banner_like')),
                    'horizontal_text_block': bool(item.get('horizontal_text_block')),
                    'promotional_layout': bool(item.get('promotional_layout')),
                    'aspect_mismatched': bool(item.get('aspect_mismatched')),
                    'similar_scene': str(item['url']) in similar_rejections,
                    'text_coverage_ratio': round(float(item.get('text_coverage_ratio') or 0.0), 3),
                    'scene_richness_score': round(float(item.get('scene_richness_score') or 0.0), 3),
                    'meets_gameplay_floor': bool(available_flag and score is not None and score >= gameplay_floor),
                    'index': int(item['index']),
                }
            )

        if len(selected_urls) >= 3:
            reason = 'selected_top_scored_frames'
        elif len(selected_urls) == 2:
            reason = 'selected_partial_strong_frames'
        elif len(selected_urls) == 1 and residual_reason is not None:
            reason = residual_reason
        elif len(selected_urls) == 1 and selected_primary_fallback:
            reason = 'selected_primary_frame_fallback'
        elif len(selected_urls) == 1:
            reason = 'selected_single_strong_frame'
        elif evaluations and any(item['available'] and item['url'] == primary_url for item in evaluations):
            reason = 'hero_only_frame_available'
        elif evaluations:
            reason = 'no_usable_frames'
        else:
            reason = 'no_candidates_available'

        return selected_urls, {
            'reason': reason,
            'candidates_evaluated': len(evaluations),
            'selected_count': len(selected_urls),
            'selected_urls': selected_urls,
            'ui_like_rejected': ui_like_rejected,
            'score_summary': score_summary,
        }

    def _extract_gameplay_media_urls(self, offer: Offer, *, limit: int = 8) -> list[str]:
        html = ' '.join(part for part in (offer.description, offer.short_description) if part)
        if not html:
            return []

        seen_groups: set[str] = set()
        urls: list[str] = []
        for match in re.finditer(r"https://[^\s>'\"]+", html):
            url = match.group(0)
            path_value = unquote(urlparse(url).path).lower()
            if '/extras/' not in path_value:
                continue
            if not path_value.endswith(('.png', '.jpg', '.jpeg', '.webp', '.avif')):
                continue
            group_key = self._gameplay_media_key(path_value)
            if group_key in seen_groups:
                continue
            seen_groups.add(group_key)
            urls.append(url)
            if len(urls) >= limit:
                break
        return urls

    def _gameplay_media_key(self, value: str) -> str:
        parsed = urlparse(value)
        path_value = unquote(parsed.path or value).lower()
        name = Path(path_value).name
        name = re.sub(r'\.poster(?=\.(avif|webp|png|jpe?g)$)', '', name)
        name = re.sub(r'\.(avif|webp|png|jpe?g)$', '', name)
        return name or path_value

    def _inspect_gameplay_candidate(
        self,
        card_type: YotoCardType,
        url: str,
        path: Path,
        kinds: tuple[str, ...],
        context: dict[str, bool] | None = None,
    ) -> tuple[float, dict[str, Any]]:
        score = 68.0
        lower = url.lower()
        group_key = self._gameplay_media_key(url)
        gameplay_context = context or {}
        ui_relaxed_genre = bool(gameplay_context.get('ui_relaxed_genre'))
        logo_dominant = any(token in lower for token in ('logo', 'title', 'wordmark', 'capsule'))

        if 'primary_screenshot' in kinds:
            score += 10
        if 'media_still' in kinds:
            score += 16
        if '/ss_' in lower or 'screenshot' in lower:
            score += 18
        if '/extras/' in lower:
            score += 12
        if logo_dominant:
            score -= 26

        with Image.open(path) as raw_image:
            image = raw_image.convert('RGB')
            width, height = image.size
            ratio = width / max(height, 1)
            area = width * height
            aspect_mismatched = False

            if 1.55 <= ratio <= 1.95:
                score += 12
            elif 1.30 <= ratio < 1.55 or 1.95 < ratio <= 2.20:
                score += 4
            else:
                aspect_mismatched = True
                score -= 22

            if area < 180_000:
                score -= 18
            elif area < 320_000:
                score -= 10
            elif area > 700_000:
                score += 8

            preview_w = 320
            preview_h = max(1, int(round(preview_w * height / max(width, 1))))
            preview = image.resize((preview_w, preview_h), Image.Resampling.BILINEAR)
            gray = preview.convert('L')
            sat = preview.convert('HSV').getchannel('S')
            edges = gray.filter(ImageFilter.FIND_EDGES)

            variance = ImageStat.Stat(gray).var[0]
            luminance = ImageStat.Stat(gray).mean[0]
            saturation = ImageStat.Stat(sat).mean[0]
            edge_mean = ImageStat.Stat(edges).mean[0]
            dark_ratio = self._dark_pixel_ratio(gray)
            text_coverage_ratio = self._estimated_text_coverage(edges)
            horizontal_text_block = self._has_large_horizontal_text_block(edges)
            text_heavy = self._looks_text_heavy(edges, variance, text_coverage_ratio, horizontal_text_block=horizontal_text_block)
            steam_ui_like = self._looks_steam_ui_like(gray, edges)
            banner_like = self._looks_banner_like(gray, edges, text_coverage_ratio)
            promotional_layout = self._looks_promotional_layout(
                gray,
                edges,
                text_coverage_ratio=text_coverage_ratio,
                horizontal_text_block=horizontal_text_block,
                banner_like=banner_like,
                dark_ratio=dark_ratio,
            )
            ui_like_raw = steam_ui_like or banner_like or promotional_layout or self._looks_ui_like(gray, edges, variance, edge_mean, text_heavy)
            low_info = variance < 170 or edge_mean < 9 or dark_ratio > 0.84
            rich_scene_score = self._scene_richness_score(gray, sat, edges)
            meaningful_gameplay_state = (
                rich_scene_score >= 0.44
                and variance >= 220
                and edge_mean >= 10
                and 34 <= luminance <= 196
                and dark_ratio < 0.80
            )
            ui_relaxed_candidate = (
                ui_relaxed_genre
                and ui_like_raw
                and not promotional_layout
                and not banner_like
                and not text_heavy
                and not horizontal_text_block
                and meaningful_gameplay_state
            )
            ui_like = ui_like_raw and not ui_relaxed_candidate
            scene_vector = self._scene_vector(preview)
            color_histogram_signature = self._color_histogram_signature(preview)
            composition_signature = self._composition_signature(gray, edges)

            if variance < 220:
                score -= 18
            elif variance < 420:
                score -= 8
            elif variance > 900:
                score += 10
            elif variance > 650:
                score += 6

            if saturation < 18:
                score -= 8
            elif saturation > 54:
                score += 6

            if edge_mean < 12:
                score -= 18
            elif edge_mean < 18:
                score -= 8
            elif 18 <= edge_mean <= 60:
                score += 12
            elif edge_mean > 72:
                score += 2

            if 42 <= luminance <= 180:
                score += 6
            elif luminance < 28:
                score -= 14

            if dark_ratio > 0.66:
                score -= 14
            elif dark_ratio < 0.48:
                score += 4

            if rich_scene_score >= 0.72:
                score += 12
            elif rich_scene_score >= 0.56:
                score += 6
            elif rich_scene_score < 0.34:
                score -= 10

            if text_coverage_ratio > 0.38:
                if ui_relaxed_genre and not horizontal_text_block and not promotional_layout and not banner_like:
                    score -= 12
                else:
                    score -= 32
            elif text_coverage_ratio > 0.28 and horizontal_text_block:
                score -= 18

            if horizontal_text_block:
                score -= 24
            if promotional_layout:
                score -= 28
            if text_heavy:
                score -= 18
            if ui_like_raw:
                score -= 10 if ui_relaxed_candidate else 24
            if ui_relaxed_candidate:
                score += 8
            if logo_dominant:
                score -= 18
            if banner_like:
                score -= 14
            if low_info:
                score -= 18

        return score, {
            'score': score,
            'ui_like': ui_like,
            'ui_relaxed_candidate': ui_relaxed_candidate,
            'text_heavy': text_heavy,
            'low_info': low_info,
            'logo_dominant': logo_dominant,
            'steam_ui_like': steam_ui_like,
            'banner_like': banner_like,
            'horizontal_text_block': horizontal_text_block,
            'promotional_layout': promotional_layout,
            'aspect_mismatched': aspect_mismatched,
            'text_coverage_ratio': text_coverage_ratio,
            'scene_richness_score': rich_scene_score,
            'luminance': luminance,
            'edge_mean': edge_mean,
            'dark_ratio': dark_ratio,
            'group_key': group_key,
            'scene_vector': scene_vector,
            'color_histogram_signature': color_histogram_signature,
            'composition_signature': composition_signature,
        }

    def _looks_ui_like(
        self,
        gray: Image.Image,
        edges: Image.Image,
        variance: float,
        edge_mean: float,
        text_heavy: bool,
    ) -> bool:
        width, height = gray.size
        if width < 24 or height < 24:
            return True
        band_h = max(1, height // 6)
        band_w = max(1, width // 8)
        top = gray.crop((0, 0, width, band_h))
        bottom = gray.crop((0, height - band_h, width, height))
        center = gray.crop((band_w, band_h, width - band_w, height - band_h))
        top_edges = edges.crop((0, 0, width, band_h))
        bottom_edges = edges.crop((0, height - band_h, width, height))
        center_edges = edges.crop((band_w, band_h, width - band_w, height - band_h))

        top_var = ImageStat.Stat(top).var[0]
        bottom_var = ImageStat.Stat(bottom).var[0]
        center_var = ImageStat.Stat(center).var[0]
        top_edge_mean = ImageStat.Stat(top_edges).mean[0]
        bottom_edge_mean = ImageStat.Stat(bottom_edges).mean[0]
        center_edge_mean = ImageStat.Stat(center_edges).mean[0]

        if text_heavy and center_var < max(240.0, variance * 0.70):
            return True
        if max(top_edge_mean, bottom_edge_mean) > max(center_edge_mean * 1.45, 14.0) and center_var < 520:
            return True
        if edge_mean < 16 and center_var < 260 and max(top_var, bottom_var) < 160:
            return True
        return False

    def _looks_steam_ui_like(self, gray: Image.Image, edges: Image.Image) -> bool:
        width, height = gray.size
        if width < 32 or height < 32:
            return False
        top_h = max(1, int(height * 0.12))
        side_w = max(1, int(width * 0.16))
        top = gray.crop((0, 0, width, top_h))
        left = gray.crop((0, 0, side_w, height))
        right = gray.crop((width - side_w, 0, width, height))
        center = gray.crop((side_w, top_h, width - side_w, height - top_h))
        top_edges = edges.crop((0, 0, width, top_h))
        left_edges = edges.crop((0, 0, side_w, height))
        right_edges = edges.crop((width - side_w, 0, width, height))

        top_mean = ImageStat.Stat(top).mean[0]
        top_var = ImageStat.Stat(top).var[0]
        side_mean = (ImageStat.Stat(left).mean[0] + ImageStat.Stat(right).mean[0]) / 2
        center_mean = ImageStat.Stat(center).mean[0]
        center_var = ImageStat.Stat(center).var[0]
        top_edge_mean = ImageStat.Stat(top_edges).mean[0]
        side_edge_mean = (ImageStat.Stat(left_edges).mean[0] + ImageStat.Stat(right_edges).mean[0]) / 2

        if top_mean < 54 and top_var < 110 and top_edge_mean > 16 and center_var > 240:
            return True
        if side_mean < center_mean - 14 and side_edge_mean > 18 and center_var > 220:
            return True
        return False

    def _looks_banner_like(self, gray: Image.Image, edges: Image.Image, text_coverage_ratio: float) -> bool:
        width, height = gray.size
        band_h = max(1, int(height * 0.18))
        top_gray = gray.crop((0, 0, width, band_h))
        bottom_gray = gray.crop((0, height - band_h, width, height))
        center_gray = gray.crop((0, band_h, width, height - band_h))
        top_edges = edges.crop((0, 0, width, band_h))
        bottom_edges = edges.crop((0, height - band_h, width, height))
        center_edges = edges.crop((0, band_h, width, height - band_h))

        top_coverage = self._estimated_text_coverage(top_edges)
        bottom_coverage = self._estimated_text_coverage(bottom_edges)
        center_coverage = self._estimated_text_coverage(center_edges)
        top_var = ImageStat.Stat(top_gray).var[0]
        bottom_var = ImageStat.Stat(bottom_gray).var[0]
        center_var = ImageStat.Stat(center_gray).var[0]
        top_edge_mean = ImageStat.Stat(top_edges).mean[0]
        bottom_edge_mean = ImageStat.Stat(bottom_edges).mean[0]
        center_edge_mean = ImageStat.Stat(center_edges).mean[0]

        if top_coverage > max(0.28, center_coverage * 2.4) and top_edge_mean > max(18.0, center_edge_mean * 1.70):
            return True
        if bottom_coverage > max(0.28, center_coverage * 2.4) and bottom_edge_mean > max(18.0, center_edge_mean * 1.70):
            return True
        if top_coverage > max(0.20, center_coverage * 2.1) and top_edge_mean > max(16.0, center_edge_mean * 1.22) and top_var < max(180.0, center_var * 0.60):
            return True
        if bottom_coverage > max(0.20, center_coverage * 2.1) and bottom_edge_mean > max(16.0, center_edge_mean * 1.22) and bottom_var < max(180.0, center_var * 0.60):
            return True
        return False

    def _has_large_horizontal_text_block(self, edges: Image.Image) -> bool:
        row_means: list[float] = []
        for y in range(0, edges.height, 2):
            row = edges.crop((0, y, edges.width, min(y + 2, edges.height)))
            row_means.append(ImageStat.Stat(row).mean[0])
        if not row_means:
            return False
        streak = 0
        streaks: list[int] = []
        for value in row_means:
            if value >= 26:
                streak += 1
            else:
                if streak:
                    streaks.append(streak)
                streak = 0
        if streak:
            streaks.append(streak)
        return max(streaks or [0]) >= max(4, int(len(row_means) * 0.08))

    def _looks_promotional_layout(
        self,
        gray: Image.Image,
        edges: Image.Image,
        *,
        text_coverage_ratio: float,
        horizontal_text_block: bool,
        banner_like: bool,
        dark_ratio: float,
    ) -> bool:
        width, height = gray.size
        top_h = max(1, int(height * 0.18))
        bottom_h = max(1, int(height * 0.18))
        top_gray = gray.crop((0, 0, width, top_h))
        bottom_gray = gray.crop((0, height - bottom_h, width, height))
        center_gray = gray.crop((0, top_h, width, height - bottom_h))
        top_edges = edges.crop((0, 0, width, top_h))
        bottom_edges = edges.crop((0, height - bottom_h, width, height))
        center_edges = edges.crop((0, top_h, width, height - bottom_h))

        top_var = ImageStat.Stat(top_gray).var[0]
        bottom_var = ImageStat.Stat(bottom_gray).var[0]
        center_var = ImageStat.Stat(center_gray).var[0]
        top_edge_mean = ImageStat.Stat(top_edges).mean[0]
        bottom_edge_mean = ImageStat.Stat(bottom_edges).mean[0]
        center_edge_mean = ImageStat.Stat(center_edges).mean[0]

        if banner_like:
            return True
        if text_coverage_ratio > 0.34 and horizontal_text_block:
            return True
        if horizontal_text_block and max(top_var, bottom_var) < max(180.0, center_var * 0.58):
            return True
        if horizontal_text_block and max(top_edge_mean, bottom_edge_mean) > max(18.0, center_edge_mean * 1.16):
            return True
        if dark_ratio > 0.58 and horizontal_text_block and center_var < 360:
            return True
        return False

    def _dark_pixel_ratio(self, gray: Image.Image) -> float:
        histogram = gray.histogram()
        total = float(sum(histogram) or 1.0)
        return sum(histogram[:32]) / total

    def _inspect_visual_candidate(
        self,
        card_type: YotoCardType,
        url: str,
        path: Path,
        kinds: tuple[str, ...],
    ) -> tuple[float, dict[str, Any]]:
        cache_key = (str(path.resolve()), card_type.value, '|'.join(kinds))
        cached = self._visual_score_cache.get(cache_key)
        if cached is not None:
            return float(cached['score']), dict(cached)

        score = float(self._base_visual_score(card_type, kinds))
        lower = url.lower()
        capsule_like = self._looks_capsule_like(lower)
        capsule_named = 'capsule' in lower
        logo_dominant = 'logo' in lower or 'wordmark' in lower

        if 'screenshot' in kinds and card_type != YotoCardType.FESTIVAL:
            score += 6
        if 'hero' in kinds and card_type == YotoCardType.FREE_GAME:
            score += 4
        if 'hero' in kinds and card_type == YotoCardType.FESTIVAL:
            score += 6

        if capsule_like:
            score -= 54
        elif capsule_named:
            score -= 42

        if '/header.' in lower or lower.endswith('header.jpg') or lower.endswith('header.png'):
            score -= 14 if card_type != YotoCardType.FESTIVAL else 6
        if '/ss_' in lower or 'screenshot' in lower:
            score += 18
        if 'library_hero' in lower or 'libraryhero' in lower:
            score += 12
        if 'promo' in lower or 'banner' in lower:
            score += 8 if card_type == YotoCardType.FESTIVAL else 2
        if logo_dominant:
            score -= 18

        text_heavy = False
        ui_heavy = False
        brightness_score = 0.0
        entropy_score = 0.0
        subject_detection_score = 0.0
        text_coverage_ratio = 0.0
        banner_like = False
        horizontal_text_block = False
        promotional_layout = False
        with Image.open(path) as raw_image:
            image = raw_image.convert('RGB')
            width, height = image.size
            ratio = width / max(height, 1)
            area = width * height
            if 1.45 <= ratio <= 2.4:
                score += 10
            elif 1.20 <= ratio < 1.45 or 2.4 < ratio <= 2.8:
                score += 2
            else:
                score -= 10

            if area < 140_000:
                score -= 20
            elif area < 280_000:
                score -= 12
            elif area > 1_000_000:
                score += 6

            preview_w = 320
            preview_h = max(1, int(round(preview_w * height / max(width, 1))))
            preview = image.resize((preview_w, preview_h), Image.Resampling.BILINEAR)
            gray = preview.convert('L')
            sat = preview.convert('HSV').getchannel('S')
            edges = gray.filter(ImageFilter.FIND_EDGES)
            variance = ImageStat.Stat(gray).var[0]
            luminance = ImageStat.Stat(gray).mean[0]
            saturation = ImageStat.Stat(sat).mean[0]
            edge_mean = ImageStat.Stat(edges).mean[0]
            dark_ratio = self._dark_pixel_ratio(gray)
            text_coverage_ratio = self._estimated_text_coverage(edges)
            horizontal_text_block = self._has_large_horizontal_text_block(edges)
            banner_like = self._looks_banner_like(gray, edges, text_coverage_ratio)
            promotional_layout = self._looks_promotional_layout(
                gray,
                edges,
                text_coverage_ratio=text_coverage_ratio,
                horizontal_text_block=horizontal_text_block,
                banner_like=banner_like,
                dark_ratio=dark_ratio,
            )

            if variance < 280:
                score -= 14
            elif variance > 1200:
                score += 7
            if saturation < 22:
                score -= 5
            elif saturation > 64:
                score += 4
            if edge_mean < 14:
                score -= 10
            elif 20 <= edge_mean <= 56:
                score += 5
            text_heavy = self._looks_text_heavy(edges, variance, text_coverage_ratio)
            ui_heavy = self._looks_ui_like(gray, edges, variance, edge_mean, text_heavy) or banner_like or promotional_layout
            brightness_score = self._brightness_score(luminance, dark_ratio)
            entropy_score = self._entropy_score(gray)
            subject_detection_score = self._subject_detection_score(gray, sat, edges)
            if text_heavy:
                score -= 18
            if ui_heavy:
                score -= 26
            if promotional_layout:
                score -= 18
            if text_coverage_ratio > 0.20:
                score -= 22
            if horizontal_text_block:
                score -= 18
            score += brightness_score * 20
            score += entropy_score * 10
            score += subject_detection_score * 30
            if 0.46 <= brightness_score <= 0.72:
                score += 6
            if brightness_score < 0.32:
                score -= 22
            elif brightness_score >= 0.78:
                score -= 4
            if subject_detection_score >= 0.62:
                score += 6
            if dark_ratio > 0.70:
                score -= 18

        analysis = {
            'score': score,
            'capsule_like': capsule_like,
            'capsule_named': capsule_named,
            'text_heavy': text_heavy,
            'logo_dominant': logo_dominant,
            'brightness_score': brightness_score,
            'entropy_score': entropy_score,
            'subject_detection_score': subject_detection_score,
            'ui_heavy': ui_heavy,
            'text_coverage_ratio': text_coverage_ratio,
            'banner_like': banner_like,
            'horizontal_text_block': horizontal_text_block,
            'promotional_layout': promotional_layout,
        }
        self._visual_score_cache[cache_key] = dict(analysis)
        return score, dict(analysis)

    def _hero_selection_reason(
        self,
        selected: dict[str, Any] | None,
        rejected_capsules: list[dict[str, Any]],
        scored: list[dict[str, Any]],
    ) -> str:
        if selected is None:
            if scored:
                return 'weak_asset_fallback'
            return 'intentional_fallback'
        if rejected_capsules:
            return str(rejected_capsules[0]['reason'])
        return self._selected_reason_tag(tuple(str(kind) for kind in selected['source_types']))

    def _selected_reason_tag(self, kinds: tuple[str, ...]) -> str:
        if 'screenshot' in kinds:
            return 'selected_gameplay_screenshot'
        if 'hero' in kinds:
            return 'selected_primary_hero'
        if 'header' in kinds:
            return 'selected_store_header'
        if 'fallback' in kinds:
            return 'selected_fallback_scene'
        return 'selected_primary_hero'

    def _primary_source_type(self, kinds: tuple[str, ...]) -> str:
        for source_type in ('screenshot', 'hero', 'header', 'fallback'):
            if source_type in kinds:
                return source_type
        return kinds[0] if kinds else 'unknown'

    def _primary_gameplay_source_type(self, kinds: tuple[str, ...]) -> str:
        if 'media_still' in kinds:
            return 'gameplay_media'
        if 'primary_screenshot' in kinds:
            return 'screenshot'
        return kinds[0] if kinds else 'unknown'

    def _log_hero_selection(self, offer: Offer, template_id: str, selection: dict[str, Any]) -> None:
        LOGGER.info(
            'hero_selection offer=%s template=%s source=%s reason=%s fallback=%s candidates=%s summary=%s',
            offer.offer_id,
            template_id,
            selection.get('selected_source'),
            selection.get('reason'),
            selection.get('fallback_used'),
            selection.get('candidates_evaluated'),
            selection.get('score_summary'),
        )

    def _log_gameplay_selection(self, offer: Offer, template_id: str, selection: dict[str, Any]) -> None:
        LOGGER.info(
            'gameplay_selection offer=%s template=%s reason=%s selected=%s candidates=%s ui_like_rejected=%s summary=%s',
            offer.offer_id,
            template_id,
            selection.get('reason'),
            selection.get('selected_count'),
            selection.get('candidates_evaluated'),
            selection.get('ui_like_rejected'),
            selection.get('score_summary'),
        )

    def _base_visual_score(self, card_type: YotoCardType, kinds: tuple[str, ...]) -> int:
        score_table = {
            YotoCardType.DISCOUNT: {'screenshot': 86, 'hero': 64, 'header': 36, 'fallback': 8},
            YotoCardType.FREE_GAME: {'hero': 82, 'screenshot': 74, 'header': 34, 'fallback': 8},
            YotoCardType.FESTIVAL: {'hero': 78, 'header': 58, 'screenshot': 42, 'fallback': 12},
            YotoCardType.TOP_LIST: {'hero': 70, 'screenshot': 60, 'header': 40, 'fallback': 12},
        }
        lookup = score_table[card_type]
        return max(lookup.get(kind, 0) for kind in kinds)

    def _hero_quality_floor(self, card_type: YotoCardType) -> float:
        if card_type == YotoCardType.FESTIVAL:
            return 28.0
        if card_type == YotoCardType.TOP_LIST:
            return 30.0
        return 36.0

    def _gameplay_quality_floor(self, card_type: YotoCardType) -> float:
        if card_type == YotoCardType.FESTIVAL:
            return 34.0
        return 46.0

    def _looks_capsule_like(self, value: str) -> bool:
        lower = value.lower()
        return any(token in lower for token in ('capsule_231x87', 'capsule_184x69', 'capsule_467x181', 'capsule_616x353', 'smallcapsule', 'maincapsule'))

    def _looks_text_heavy(
        self,
        edges: Image.Image,
        variance: float,
        text_coverage_ratio: float | None = None,
        *,
        horizontal_text_block: bool = False,
    ) -> bool:
        if text_coverage_ratio is not None and text_coverage_ratio > 0.82 and horizontal_text_block:
            return True
        row_means: list[float] = []
        for y in range(0, edges.height, 2):
            row = edges.crop((0, y, edges.width, min(y + 2, edges.height)))
            row_means.append(ImageStat.Stat(row).mean[0])
        if not row_means:
            return False
        high_rows = sum(value > 36 for value in row_means)
        spike_rows = sum(value > 54 for value in row_means)
        threshold = max(6, int(len(row_means) * 0.34))
        if text_coverage_ratio is not None and text_coverage_ratio > 0.42 and horizontal_text_block:
            threshold = max(4, int(len(row_means) * 0.24))
        if spike_rows >= max(3, int(len(row_means) * 0.08)) and max(row_means) > 66 and horizontal_text_block:
            return True
        if variance > 2000 and spike_rows < 2 and high_rows < max(4, int(len(row_means) * 0.18)):
            return False
        return horizontal_text_block and high_rows >= threshold

    def _estimated_text_coverage(self, edges: Image.Image) -> float:
        if edges.width <= 0 or edges.height <= 0:
            return 0.0
        sample_w = 96
        sample_h = max(12, int(round(sample_w * edges.height / max(edges.width, 1))))
        preview = edges.resize((sample_w, sample_h), Image.Resampling.BILINEAR)
        mask = preview.point(lambda value: 255 if value >= 34 else 0)
        dilated = mask.filter(ImageFilter.MaxFilter(7))
        histogram = dilated.histogram()
        if len(histogram) < 256:
            return 0.0
        return histogram[255] / float(sample_w * sample_h or 1)

    def _brightness_score(self, luminance: float, dark_ratio: float) -> float:
        target = 112.0
        spread = 78.0
        centered = max(0.0, 1.0 - abs(luminance - target) / spread)
        shadow_penalty = max(0.0, 1.0 - dark_ratio * 1.25)
        return max(0.0, min(1.0, centered * 0.72 + shadow_penalty * 0.28))

    def _entropy_score(self, gray: Image.Image) -> float:
        histogram = gray.histogram()
        total = float(sum(histogram) or 1.0)
        entropy = 0.0
        for value in histogram:
            if value <= 0:
                continue
            probability = value / total
            entropy -= probability * math.log2(probability)
        return max(0.0, min(1.0, entropy / 7.4))

    def _subject_detection_score(self, gray: Image.Image, sat: Image.Image, edges: Image.Image) -> float:
        width, height = gray.size
        left = max(0, int(width * 0.18))
        top = max(0, int(height * 0.14))
        right = min(width, int(width * 0.82))
        bottom = min(height, int(height * 0.86))
        center_gray = gray.crop((left, top, right, bottom))
        center_edges = edges.crop((left, top, right, bottom))
        center_sat = sat.crop((left, top, right, bottom))
        side_band = max(1, int(width * 0.14))
        top_band = max(1, int(height * 0.12))
        outer_edges = [
            edges.crop((0, 0, side_band, height)),
            edges.crop((width - side_band, 0, width, height)),
            edges.crop((0, 0, width, top_band)),
            edges.crop((0, height - top_band, width, height)),
        ]
        outer_edge_mean = sum(ImageStat.Stat(region).mean[0] for region in outer_edges) / len(outer_edges)

        center_var = ImageStat.Stat(center_gray).var[0]
        center_edge_mean = ImageStat.Stat(center_edges).mean[0]
        center_sat_mean = ImageStat.Stat(center_sat).mean[0]
        subject = 0.0
        subject += min(center_var / 900.0, 1.0) * 0.38
        subject += min(center_edge_mean / 42.0, 1.0) * 0.42
        subject += min(center_sat_mean / 52.0, 1.0) * 0.20
        if outer_edge_mean > center_edge_mean * 0.98:
            subject *= 0.82
        return max(0.0, min(1.0, subject))

    def _scene_richness_score(self, gray: Image.Image, sat: Image.Image, edges: Image.Image) -> float:
        variance = ImageStat.Stat(gray).var[0]
        saturation = ImageStat.Stat(sat).mean[0]
        edge_mean = ImageStat.Stat(edges).mean[0]
        dark_ratio = self._dark_pixel_ratio(gray)
        richness = 0.0
        richness += min(variance / 900.0, 1.0) * 0.40
        richness += min(edge_mean / 42.0, 1.0) * 0.36
        richness += min(saturation / 58.0, 1.0) * 0.24
        richness *= max(0.35, 1.0 - dark_ratio * 0.45)
        return max(0.0, min(1.0, richness))

    def _scene_vector(self, image: Image.Image) -> tuple[float, ...]:
        gray = image.convert('L')
        sat = image.convert('HSV').getchannel('S')
        grid_x = 4
        grid_y = 3
        vector: list[float] = []
        for channel in (gray, sat):
            for y in range(grid_y):
                top = int(channel.height * y / grid_y)
                bottom = max(top + 1, int(channel.height * (y + 1) / grid_y))
                for x in range(grid_x):
                    left = int(channel.width * x / grid_x)
                    right = max(left + 1, int(channel.width * (x + 1) / grid_x))
                    vector.append(round(ImageStat.Stat(channel.crop((left, top, right, bottom))).mean[0], 2))
        return tuple(vector)

    def _color_histogram_signature(self, image: Image.Image) -> tuple[float, ...]:
        hsv = image.convert('HSV')
        signature: list[float] = []
        for channel, bins in ((hsv.getchannel('H'), 8), (hsv.getchannel('S'), 6), (hsv.getchannel('V'), 6)):
            histogram = channel.histogram()
            bucket = 256 // bins
            total = float(sum(histogram) or 1.0)
            for index in range(bins):
                start = index * bucket
                end = 256 if index == bins - 1 else (index + 1) * bucket
                signature.append(round(sum(histogram[start:end]) / total, 4))
        return tuple(signature)

    def _composition_signature(self, gray: Image.Image, edges: Image.Image) -> tuple[float, ...]:
        signature: list[float] = []
        for source in (gray, edges):
            for row in range(3):
                top = int(source.height * row / 3)
                bottom = max(top + 1, int(source.height * (row + 1) / 3))
                for col in range(3):
                    left = int(source.width * col / 3)
                    right = max(left + 1, int(source.width * (col + 1) / 3))
                    crop = source.crop((left, top, right, bottom))
                    stat = ImageStat.Stat(crop)
                    signature.append(round(stat.mean[0], 2))
        return tuple(signature)

    def _scene_distance(self, left: tuple[float, ...], right: tuple[float, ...]) -> float:
        if not left or not right or len(left) != len(right):
            return float('inf')
        return sum(abs(a - b) for a, b in zip(left, right)) / len(left)

    def _color_histogram_difference(self, left: tuple[float, ...], right: tuple[float, ...]) -> float:
        if not left or not right or len(left) != len(right):
            return float('inf')
        return sum(abs(a - b) for a, b in zip(left, right))

    def _composition_difference(self, left: tuple[float, ...], right: tuple[float, ...]) -> float:
        if not left or not right or len(left) != len(right):
            return float('inf')
        return sum(abs(a - b) for a, b in zip(left, right)) / len(left)

    def _is_strong_gameplay_candidate(self, item: dict[str, Any], gameplay_floor: float) -> bool:
        return (
            bool(item.get('available'))
            and item.get('score') is not None
            and float(item['score']) >= gameplay_floor
            and (not bool(item.get('ui_like')) or bool(item.get('ui_relaxed_candidate')))
            and not bool(item.get('text_heavy'))
            and not bool(item.get('logo_dominant'))
            and not bool(item.get('promotional_layout'))
            and not bool(item.get('horizontal_text_block'))
            and not bool(item.get('banner_like'))
        )

    def _is_promo_heavy_gameplay_set(self, items: list[dict[str, Any]]) -> bool:
        if not items:
            return False
        flagged = sum(
            1
            for item in items
            if bool(item.get('promotional_layout'))
            or bool(item.get('banner_like'))
            or bool(item.get('horizontal_text_block'))
            or bool(item.get('text_heavy'))
            or bool(item.get('logo_dominant'))
        )
        return flagged >= max(2, math.ceil(len(items) * 0.6))

    def _borderline_gameplay_reason(
        self,
        item: dict[str, Any],
        gameplay_floor: float,
        *,
        promo_heavy_set: bool,
        allow_primary: bool = False,
    ) -> str | None:
        if not bool(item.get('available')) or item.get('score') is None:
            return None
        if bool(item.get('promotional_layout')) or bool(item.get('text_heavy')):
            return None
        if bool(item.get('horizontal_text_block')) or bool(item.get('banner_like')) or bool(item.get('logo_dominant')):
            return None
        score = float(item['score'])
        scene_richness_score = float(item.get('scene_richness_score') or 0.0)
        luminance = float(item.get('luminance') or 0.0)
        edge_mean = float(item.get('edge_mean') or 0.0)
        dark_ratio = float(item.get('dark_ratio') or 1.0)
        readable_scene = scene_richness_score >= 0.32 and edge_mean >= 10.0 and 34 <= luminance <= 196 and dark_ratio < 0.82
        if not readable_scene:
            return None
        if bool(item.get('ui_relaxed_candidate')) and score >= gameplay_floor - 16:
            return 'selected_ui_relaxed_fallback_frame'
        if promo_heavy_set and not bool(item.get('ui_like')) and score >= gameplay_floor - 12:
            return 'selected_promo_rescue_frame'
        if not bool(item.get('ui_like')) and score >= gameplay_floor - 8:
            if allow_primary:
                return 'selected_primary_frame_fallback'
            return 'selected_borderline_fallback_frame'
        return None

    def _passes_gameplay_diversity(self, candidate: dict[str, Any], selected_items: list[dict[str, Any]]) -> bool:
        for item in selected_items:
            scene_embedding_distance = self._scene_distance(
                tuple(candidate.get('scene_vector') or ()),
                tuple(item.get('scene_vector') or ()),
            )
            color_histogram_difference = self._color_histogram_difference(
                tuple(candidate.get('color_histogram_signature') or ()),
                tuple(item.get('color_histogram_signature') or ()),
            )
            composition_difference = self._composition_difference(
                tuple(candidate.get('composition_signature') or ()),
                tuple(item.get('composition_signature') or ()),
            )
            if (
                scene_embedding_distance < 8.5
                and color_histogram_difference < 0.9
                and composition_difference < 6.0
            ):
                return False
            if (
                scene_embedding_distance < 12.5
                and color_histogram_difference < 0.42
                and composition_difference < 16.0
            ):
                return False
        return True

    async def _download_asset(self, http: ResilientHttpClient, asset_url: str) -> Path | None:
        local_path = resolve_existing_asset_path(asset_url)
        if local_path is not None:
            return self._materialize_downloaded_asset(local_path)

        parsed = urlparse(asset_url)
        suffix = Path(unquote(parsed.path)).suffix.lower()
        if suffix not in {'.png', '.jpg', '.jpeg', '.webp', '.avif'}:
            suffix = '.img'
        digest = hashlib.sha256(asset_url.encode('utf-8')).hexdigest()
        path = self.cache_dir / f'{digest}{suffix}'
        if path.exists() and path.stat().st_size > 0:
            return self._materialize_downloaded_asset(path)
        try:
            content = await http.get_bytes(asset_url)
        except Exception:
            return None
        path.write_bytes(content)
        return self._materialize_downloaded_asset(path)

    def _materialize_downloaded_asset(self, path: Path) -> Path | None:
        suffix = path.suffix.lower()
        if suffix != '.avif':
            return path if path.exists() and path.stat().st_size > 0 else None

        raster_path = path.with_suffix('.png')
        if raster_path.exists() and raster_path.stat().st_size > 0:
            return raster_path

        try:
            subprocess.run(
                ['ffmpeg', '-y', '-loglevel', 'error', '-i', str(path), str(raster_path)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
            )
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return None
        return raster_path if raster_path.exists() and raster_path.stat().st_size > 0 else None

    def _deadline_text(self, offer: Offer, card_type: YotoCardType) -> str | None:
        if offer.promo_end is None:
            return None
        months = {
            1: 'січня',
            2: 'лютого',
            3: 'березня',
            4: 'квітня',
            5: 'травня',
            6: 'червня',
            7: 'липня',
            8: 'серпня',
            9: 'вересня',
            10: 'жовтня',
            11: 'листопада',
            12: 'грудня',
        }
        prefix = 'забрати до' if card_type == YotoCardType.FREE_GAME else 'до'
        return f"{prefix} {offer.promo_end.day} {months.get(offer.promo_end.month, str(offer.promo_end.month))}, {offer.promo_end:%H:%M}"

    def _old_price_text(self, offer: Offer) -> str | None:
        if offer.price_before_minor is None or offer.price_before_minor <= 0:
            return None
        return self._format_minor(offer.price_before_minor, offer.currency)

    def _current_price_text(self, offer: Offer, card_type: YotoCardType) -> str | None:
        if card_type == YotoCardType.DISCOUNT:
            if offer.discount_percent > 0:
                return f'-{offer.discount_percent}%'
            if offer.price_after_minor is not None and offer.price_after_minor > 0:
                return self._format_minor(offer.price_after_minor, offer.currency)
        return None

    def _format_minor(self, minor: int, currency: str) -> str:
        amount = minor / 100
        currency_code = (currency or 'UAH').upper()
        if currency_code == 'UAH':
            if minor % 100 == 0:
                return f'{int(amount)} грн'
            return f'{amount:.2f} грн'
        if minor % 100 == 0:
            return f'{int(amount)} {currency_code}'
        return f'{amount:.2f} {currency_code}'


class CardRendererRouter:
    def __init__(
        self,
        output_dir: Path,
        *,
        renderer_mode: str = PRIMARY_RENDERER_MODE,
        fallback_to_legacy: bool = True,
        cache_dir: Path | None = None,
    ) -> None:
        requested_mode = (renderer_mode or PRIMARY_RENDERER_MODE).strip().lower()
        if requested_mode not in VALID_RENDERER_MODES:
            raise ValueError(f'Unsupported card renderer mode: {renderer_mode}')
        self.renderer_mode = RENDERER_MODE_ALIASES[requested_mode]
        self.fallback_to_legacy = fallback_to_legacy
        self.output_dir = output_dir
        self.legacy = TemplateSystem(output_dir)
        self.yoto_v42 = YotoCardRendererV42Adapter(output_dir, cache_dir=cache_dir)

    async def render(self, http: ResilientHttpClient, offer: Offer, template_id: str) -> RoutedRenderResult:
        if self.renderer_mode == 'legacy':
            legacy_result = await self.legacy.render(http, offer, template_id)
            return self._wrap_legacy_result(legacy_result, requested='legacy', selected='legacy', fallback_used=False)

        try:
            return await self.yoto_v42.render(http, offer, template_id)
        except Exception as exc:
            if not self.fallback_to_legacy:
                raise
            legacy_result = await self.legacy.render(http, offer, template_id)
            wrapped = self._wrap_legacy_result(legacy_result, requested=self.renderer_mode, selected='legacy', fallback_used=True)
            wrapped.diagnostics.render_warnings.append(f'renderer_fallback_from_{self.renderer_mode}:{exc.__class__.__name__}')
            wrapped.diagnostics.layout_variant = f'legacy_fallback::{template_id}'
            return wrapped

    def _wrap_legacy_result(self, result, *, requested: str, selected: str, fallback_used: bool) -> RoutedRenderResult:
        source = result.diagnostics
        diagnostics = RoutedRenderDiagnostics(
            template_id=source.template_id,
            asset_used=source.asset_used,
            title_lines=list(source.title_lines),
            clipped_fields=list(source.clipped_fields),
            render_warnings=list(source.render_warnings),
            hero_asset_used=source.hero_asset_used,
            layout_variant=source.layout_variant,
            hero_mode=source.hero_mode,
            title_font_size=source.title_font_size,
            hero_rect=source.hero_rect,
            info_rect=source.info_rect,
            badge_rect=source.badge_rect,
            renderer_family='legacy',
            renderer_requested=requested,
            renderer_selected=selected,
            renderer_fallback_used=fallback_used,
            gameplay_count=0,
            has_gameplay_strip=False,
            editorial_phrase=getattr(source, 'editorial_phrase', None),
            hero_source_type=getattr(source, 'hero_source_type', 'placeholder'),
            hero_selection_reason=getattr(source, 'hero_selection_reason', 'intentional_fallback'),
            hero_candidates_count=getattr(source, 'hero_candidates_count', 0),
            hero_rejected_capsules=[dict(item) for item in getattr(source, 'hero_rejected_capsules', [])],
            hero_score_summary=[dict(item) for item in getattr(source, 'hero_score_summary', [])],
            hero_capsule_rejected=bool(getattr(source, 'hero_rejected_capsules', [])),
            hero_fallback_used=getattr(source, 'hero_fallback_used', False),
            hero_selection=dict(getattr(source, 'hero_selection', {})),
        )
        return RoutedRenderResult(image_path=result.image_path, assets_used=list(result.assets_used), diagnostics=diagnostics)



