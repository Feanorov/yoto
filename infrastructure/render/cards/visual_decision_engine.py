from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any

from PIL import Image

from infrastructure.render.cards.asset_source import resolve_existing_asset_path


MIN_READABILITY_SCORE = 0.55
MIN_FOCUS_SCORE = 0.50
CLOSE_SCORE_OFFICIAL_TIEBREAK_THRESHOLD = 0.03

AI_SOURCE_TYPE = 'ai_generated'
LOCAL_FALLBACK_SOURCE_ORIGINS = frozenset({'local_manifest', 'fixture_fallback'})
SAFE_LOCAL_ASSET_CACHE_STATUSES = frozenset({'cached', 'downloaded'})

BUNDLE_KEYWORDS = (
    'anthology',
    'bundle',
    'collection',
    'complete edition',
    'compilation',
    'franchise',
    'multi item',
    'multi-item',
    'pack',
    'trilogy',
)
GAMEPLAY_KEYWORDS = (
    '4x',
    'automation',
    'builder',
    'city builder',
    'colony',
    'factory',
    'management',
    'sim',
    'simulation',
    'strategy',
    'tycoon',
)
MOTION_KEYWORDS = (
    'car',
    'drift',
    'driving',
    'flight',
    'motorsport',
    'racing',
    'sports',
    'supercar',
    'vehicle',
)
ATMOSPHERIC_KEYWORDS = (
    'atmospheric',
    'dark',
    'fog',
    'gothic',
    'haunted',
    'horror',
    'nightmare',
    'noir',
    'spooky',
    'survival horror',
)
COZY_KEYWORDS = (
    'cozy',
    'cute',
    'farming',
    'life sim',
    'puzzle',
    'relaxing',
    'wholesome',
)
CHARACTER_KEYWORDS = (
    'action',
    'action rpg',
    'character action',
    'fighter',
    'hack and slash',
    'hero shooter',
    'roguelike',
    'rogue-lite',
    'roguelite',
    'role playing',
    'rpg',
    'soulslike',
)

KNOWN_SOURCE_TYPES = frozenset(
    {
        'steam_library_capsule',
        'steam_main_capsule',
        'steam_header_capsule',
        'steam_library_hero',
        'steam_screenshot',
        'epic_offer_image',
        'epic_library_landscape',
        'official_press_key_art',
        'official_trailer_frame',
        AI_SOURCE_TYPE,
    }
)
OFFICIAL_LIKE_SOURCE_TYPES = frozenset(
    source_type for source_type in KNOWN_SOURCE_TYPES if source_type != AI_SOURCE_TYPE
)

VISUAL_SOURCE_PREFERENCE: dict[str, dict[str, float]] = {
    'character': {
        'steam_library_capsule': 1.0,
        'steam_main_capsule': 0.98,
        'official_press_key_art': 0.96,
        'steam_library_hero': 0.88,
        'steam_header_capsule': 0.84,
        'epic_offer_image': 0.82,
        'epic_library_landscape': 0.74,
        'steam_screenshot': 0.58,
        'official_trailer_frame': 0.55,
        AI_SOURCE_TYPE: 0.78,
    },
    'scene': {
        'steam_library_hero': 1.0,
        'epic_library_landscape': 0.96,
        'steam_header_capsule': 0.93,
        'official_press_key_art': 0.92,
        'official_trailer_frame': 0.89,
        'steam_screenshot': 0.86,
        'epic_offer_image': 0.8,
        'steam_main_capsule': 0.72,
        'steam_library_capsule': 0.68,
        AI_SOURCE_TYPE: 0.8,
    },
    'gameplay': {
        'steam_screenshot': 1.0,
        'official_trailer_frame': 0.94,
        'steam_library_hero': 0.82,
        'epic_library_landscape': 0.78,
        'steam_header_capsule': 0.7,
        'official_press_key_art': 0.64,
        'epic_offer_image': 0.6,
        'steam_main_capsule': 0.56,
        'steam_library_capsule': 0.52,
        AI_SOURCE_TYPE: 0.76,
    },
    'collage': {
        'steam_library_capsule': 0.96,
        'steam_main_capsule': 0.94,
        'official_press_key_art': 0.9,
        'epic_offer_image': 0.88,
        'steam_header_capsule': 0.84,
        'steam_library_hero': 0.82,
        'steam_screenshot': 0.76,
        'epic_library_landscape': 0.76,
        'official_trailer_frame': 0.72,
        AI_SOURCE_TYPE: 0.72,
    },
    'poster_art': {
        'official_press_key_art': 1.0,
        'steam_main_capsule': 0.95,
        'steam_library_capsule': 0.94,
        'epic_offer_image': 0.9,
        'steam_library_hero': 0.78,
        'steam_header_capsule': 0.76,
        'epic_library_landscape': 0.74,
        'steam_screenshot': 0.54,
        'official_trailer_frame': 0.52,
        AI_SOURCE_TYPE: 0.8,
    },
}

SOURCE_STRENGTH_MAP: dict[str, float] = {
    'official_press_key_art': 1.0,
    'steam_library_capsule': 0.96,
    'steam_main_capsule': 0.92,
    'epic_offer_image': 0.9,
    'steam_screenshot': 0.76,
    'official_trailer_frame': 0.72,
    'steam_library_hero': 0.64,
    'epic_library_landscape': 0.62,
    'steam_header_capsule': 0.56,
    AI_SOURCE_TYPE: 0.46,
}

HERO_HINT_KEYWORDS = (
    'character',
    'close-up',
    'closeup',
    'cover',
    'face',
    'foreground',
    'hero',
    'key art',
    'key_art',
    'leader',
    'logo_safe',
    'poster',
    'poster_layout',
    'portrait',
    'readable_subject',
    'subject',
    'subject focus',
    'subject_focus',
    'vehicle_focus',
)
GAMEPLAY_HINT_KEYWORDS = (
    'builder',
    'city',
    'combat',
    'factory',
    'gameplay',
    'harpoon',
    'hud',
    'map',
    'strategy',
    'trailer',
    'world map',
)
SCENE_HINT_KEYWORDS = (
    'atmosphere',
    'atmospheric',
    'background',
    'environment',
    'horizon',
    'landscape',
    'landmark',
    'landmarks',
    'panorama',
    'scene',
    'scene_focus',
    'vista',
    'wide shot',
)
BANNER_HINT_KEYWORDS = (
    'banner',
    'header',
    'lineup',
    'masthead',
    'panoramic',
    'panorama',
)
GROUP_HINT_KEYWORDS = (
    'cast',
    'collection',
    'crowd',
    'ensemble',
    'franchise',
    'group',
    'lineup',
    'multi item',
    'multi-item',
    'multi_character',
    'multi_item',
    'multiple characters',
    'series',
    'team',
)
LARGE_SUBJECT_HINT_KEYWORDS = (
    'close-up',
    'closeup',
    'foreground',
    'hero',
    'leader',
    'portrait',
    'subject',
    'subject_focus',
    'vehicle_focus',
)
SMALL_SUBJECT_HINT_KEYWORDS = (
    'background',
    'crowd',
    'distant',
    'environment',
    'group',
    'horizon',
    'landscape',
    'lineup',
    'map',
    'panorama',
    'scene_focus',
    'skyline',
    'wide shot',
    'world map',
)
SIMPLE_DENSITY_HINT_KEYWORDS = (
    'clean',
    'close-up',
    'closeup',
    'foreground',
    'hero',
    'logo_safe',
    'minimal',
    'poster_layout',
    'portrait',
    'subject_focus',
)
CLUTTER_DENSITY_HINT_KEYWORDS = (
    'army',
    'busy',
    'city',
    'collection',
    'crowd',
    'effects',
    'factory',
    'franchise',
    'group',
    'hud',
    'interface',
    'map',
    'multi item',
    'multi-item',
    'multi_item',
    'multiple characters',
    'team',
    'world map',
)

READABILITY_ENRICHMENT_HEADROOM_WEIGHT = 0.65
READABILITY_ENRICHMENT_MAX_POSITIVE_DELTA = 0.12
READABILITY_ENRICHMENT_MAX_NEGATIVE_DELTA = 0.18
FOCUS_ENRICHMENT_HEADROOM_WEIGHT = 0.75
FOCUS_ENRICHMENT_MAX_POSITIVE_DELTA = 0.18
FOCUS_ENRICHMENT_MAX_NEGATIVE_DELTA = 0.22
VISUAL_ANCHOR_READABILITY_BOOST = 0.015
VISUAL_ANCHOR_FOCUS_BOOST = 0.020


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _clamp_range(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _safe_text(value: Any) -> str:
    return str(value or '').strip()


def _normalize_text(value: Any) -> str:
    return _safe_text(value).lower()


def _safe_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _contains_any(text: str, keywords: Sequence[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _matched_keywords(text: str, keywords: Sequence[str]) -> list[str]:
    return [keyword for keyword in keywords if keyword in text]


def _normalized_keyword_text(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', _normalize_text(text)).strip()


def _contains_keyword(text: str, keyword: str) -> bool:
    normalized_text = _normalized_keyword_text(text)
    normalized_keyword = _normalized_keyword_text(keyword)
    if not normalized_text or not normalized_keyword:
        return False
    return f' {normalized_keyword} ' in f' {normalized_text} '


def _contains_any_keyword(text: str, keywords: Sequence[str]) -> bool:
    return any(_contains_keyword(text, keyword) for keyword in keywords)


def _dedupe_reasons(reasons: Sequence[str]) -> list[str]:
    return [reason for reason in dict.fromkeys(_safe_text(item) for item in reasons) if reason]


def _primary_rejection_reason(reasons: Sequence[str]) -> str | None:
    normalized = _dedupe_reasons(reasons)
    return normalized[0] if normalized else None


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _metadata_text(metadata: Mapping[str, Any]) -> str:
    values: list[str] = []
    for key, value in metadata.items():
        normalized_key = _safe_text(key)
        if normalized_key:
            values.append(normalized_key.lower())
        if isinstance(value, str):
            cleaned = _normalize_text(value)
            if cleaned:
                values.append(cleaned)
        elif isinstance(value, bool):
            if value:
                values.append(normalized_key.lower())
        elif isinstance(value, (int, float)):
            values.append(str(value))
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for item in value:
                cleaned_item = _normalize_text(item)
                if cleaned_item:
                    values.append(cleaned_item)
    return ' '.join(values)


@dataclass(slots=True)
class AssetCandidate:
    index: int
    source_type: str
    width: int | None
    height: int | None
    kind: str
    path_or_url: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any], *, index: int) -> 'AssetCandidate':
        metadata = payload.get('metadata')
        merged_metadata = dict(metadata) if isinstance(metadata, Mapping) else {}
        for key, value in payload.items():
            normalized_key = str(key)
            if normalized_key not in {'source_type', 'width', 'height', 'kind', 'path_or_url', 'metadata'}:
                merged_metadata.setdefault(normalized_key, value)
        return cls(
            index=index,
            source_type=_normalize_text(payload.get('source_type')) or 'unknown',
            width=_safe_int(payload.get('width')),
            height=_safe_int(payload.get('height')),
            kind=_normalize_text(payload.get('kind')) or 'unknown',
            path_or_url=_safe_text(payload.get('path_or_url')),
            metadata={str(key): _json_ready(value) for key, value in merged_metadata.items()},
        )

    @property
    def is_official(self) -> bool:
        return self.source_type != AI_SOURCE_TYPE

    @property
    def aspect_ratio(self) -> float | None:
        if self.width is None or self.height is None or self.height == 0:
            return None
        return float(self.width) / float(self.height)

    @property
    def area(self) -> int:
        if self.width is None or self.height is None:
            return 0
        return self.width * self.height

    @property
    def signal_text(self) -> str:
        return ' '.join(
            part
            for part in (
                self.source_type,
                self.kind,
                _metadata_text(self.metadata),
            )
            if part
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            'source_type': self.source_type,
            'width': self.width,
            'height': self.height,
            'kind': self.kind,
            'path_or_url': self.path_or_url,
            'metadata': dict(self.metadata),
        }


@dataclass(slots=True, frozen=True)
class AssetEnrichment:
    asset_metadata_enriched: bool
    orientation: str
    aspect_ratio: float | None
    is_vertical: bool
    is_wide_banner: bool
    is_squareish: bool
    source_strength: float
    estimated_focus: str
    estimated_subject_scale: str
    estimated_visual_density: str
    composition_bias: str
    official_asset_score_boost: float
    signals: tuple[str, ...] = ()
    local_image_readable: bool | None = None
    local_image_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            'asset_metadata_enriched': self.asset_metadata_enriched,
            'orientation': self.orientation,
            'aspect_ratio': round(self.aspect_ratio, 3) if self.aspect_ratio is not None else None,
            'is_vertical': self.is_vertical,
            'is_wide_banner': self.is_wide_banner,
            'is_squareish': self.is_squareish,
            'source_strength': round(self.source_strength, 3),
            'estimated_focus': self.estimated_focus,
            'estimated_subject_scale': self.estimated_subject_scale,
            'estimated_visual_density': self.estimated_visual_density,
            'composition_bias': self.composition_bias,
            'official_asset_score_boost': round(self.official_asset_score_boost, 3),
            'enrichment_signals': list(self.signals),
        }


@dataclass(slots=True)
class ScoredAsset:
    candidate: AssetCandidate
    enrichment: AssetEnrichment
    readability_score: float
    focus_score: float
    total_score: float
    accepted: bool
    visual_anchor_boost_applied: bool = False
    rejection_reasons: list[str] = field(default_factory=list)
    score_breakdown: dict[str, Any] = field(default_factory=dict)
    scoring_reason: str = ''

    def to_dict(self) -> dict[str, Any]:
        payload = self.candidate.to_dict()
        payload.update(self.enrichment.to_dict())
        payload.update(
            {
                'is_official': self.candidate.is_official,
                'readability_score': round(self.readability_score, 3),
                'focus_score': round(self.focus_score, 3),
                'total_score': round(self.total_score, 3),
                'accepted': self.accepted,
                'visual_anchor_boost_applied': self.visual_anchor_boost_applied,
                'rejection_reasons': _dedupe_reasons(self.rejection_reasons),
                'rejection_reason': _primary_rejection_reason(self.rejection_reasons),
                'score_breakdown': _json_ready(self.score_breakdown),
                'scoring_reason': self.scoring_reason,
            }
        )
        return payload


@dataclass(slots=True)
class CoverDecision:
    genre_cluster: str
    visual_type: str
    image_source_type: str
    layout_type: str
    use_ai: bool
    selected_asset: dict[str, Any] | None
    asset_scores: list[dict[str, Any]]
    rejected_assets: list[dict[str, Any]]
    decision_reason: str
    decision_trace: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            'genre_cluster': self.genre_cluster,
            'visual_type': self.visual_type,
            'image_source_type': self.image_source_type,
            'layout_type': self.layout_type,
            'use_ai': self.use_ai,
            'selected_asset': _json_ready(self.selected_asset),
            'asset_scores': _json_ready(self.asset_scores),
            'rejected_assets': _json_ready(self.rejected_assets),
            'decision_reason': self.decision_reason,
            'decision_trace': _json_ready(self.decision_trace),
        }


@dataclass(slots=True, frozen=True)
class DecisionAssetBridge:
    selected_asset: dict[str, Any] | None
    selected_asset_source_type: str | None
    resolved_local_path: str | None
    candidate_valid: bool
    decision_asset_use_reason: str | None
    decision_asset_reject_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            'selected_asset': _json_ready(self.selected_asset),
            'selected_asset_source_type': self.selected_asset_source_type,
            'resolved_local_path': self.resolved_local_path,
            'candidate_valid': self.candidate_valid,
            'decision_asset_use_reason': self.decision_asset_use_reason,
            'decision_asset_reject_reason': self.decision_asset_reject_reason,
        }


class VisualDecisionEngine:
    def decide(
        self,
        *,
        game_title: str,
        genre: str | None,
        tags: Sequence[str] | None,
        short_description: str | None,
        offer_type: str | None,
        asset_candidates: Sequence[Mapping[str, Any]] | None,
    ) -> CoverDecision:
        title_text = _safe_text(game_title)
        genre_text = _safe_text(genre)
        tag_values = [_safe_text(item) for item in tags or [] if _safe_text(item)]
        description_text = _safe_text(short_description)
        offer_type_text = _safe_text(offer_type)
        candidates = self._normalize_candidates(asset_candidates)

        combined_text = ' '.join(
            part
            for part in (
                _normalize_text(title_text),
                _normalize_text(genre_text),
                ' '.join(_normalize_text(item) for item in tag_values),
                _normalize_text(description_text),
                _normalize_text(offer_type_text),
            )
            if part
        )

        genre_cluster, genre_trace = self._infer_genre_cluster(
            combined_text=combined_text,
            offer_type=offer_type_text,
            candidates=candidates,
        )
        visual_type, visual_trace = self._infer_visual_type(
            genre_cluster=genre_cluster,
            combined_text=combined_text,
            candidates=candidates,
        )

        scored_assets = [
            self._score_asset(
                candidate,
                visual_type=visual_type,
                genre_cluster=genre_cluster,
            )
            for candidate in candidates
        ]

        official_assets = [item for item in scored_assets if item.candidate.is_official]
        ai_assets = [item for item in scored_assets if not item.candidate.is_official]
        usable_official_assets = [item for item in official_assets if item.accepted]

        use_ai = False
        ai_fallback_reason: str | None = None
        selected_assets: list[ScoredAsset] = []
        selection_reason = 'official_first_selected_best_scoring_asset'
        selection_trace: dict[str, Any] = {
            'close_score_official_tiebreak': False,
            'tiebreak_reason': 'not_evaluated',
            'tiebreak_displaced_candidate_index': None,
            'tiebreak_selected_candidate_index': None,
        }

        if usable_official_assets:
            selected_assets, selection_trace = self._select_assets(
                genre_cluster=genre_cluster,
                candidates=usable_official_assets,
            )
            if selection_trace.get('close_score_official_tiebreak'):
                selection_reason = 'official_first_selected_safe_official_close_score_tiebreak'
            elif genre_cluster == 'bundle_multi_item' and len(selected_assets) > 1:
                selection_reason = 'official_first_selected_best_scoring_collage'
        else:
            use_ai = True
            ai_fallback_reason = (
                'no_official_assets'
                if not official_assets
                else 'all_official_assets_failed_thresholds'
            )
            selected_assets, _ = self._select_assets(
                genre_cluster=genre_cluster,
                candidates=ai_assets,
            )
            selection_trace = {
                'close_score_official_tiebreak': False,
                'tiebreak_reason': 'not_applicable_ai_selection',
                'tiebreak_displaced_candidate_index': None,
                'tiebreak_selected_candidate_index': None,
            }
            if not selected_assets:
                selected_assets = [self._synthetic_ai_asset(genre_cluster=genre_cluster, visual_type=visual_type)]
                selection_reason = 'ai_fallback_without_existing_ai_candidate'
            else:
                selection_reason = 'ai_fallback_selected_best_ai_candidate'

        layout_type, layout_trace = self._infer_layout_type(
            genre_cluster=genre_cluster,
            visual_type=visual_type,
            selected_assets=selected_assets,
        )
        selected_asset = self._serialize_selected_assets(
            selected_assets=selected_assets,
            layout_type=layout_type,
        )
        image_source_type = str(selected_asset.get('source_type') or AI_SOURCE_TYPE) if selected_asset else AI_SOURCE_TYPE

        selected_indexes = {item.candidate.index for item in selected_assets}
        ordered_scores = self._ordered_asset_scores(scored_assets)
        rejected_assets = self._collect_rejected_assets(
            scored_assets=ordered_scores,
            selected_indexes=selected_indexes,
            use_ai=use_ai,
            genre_cluster=genre_cluster,
            selection_trace=selection_trace,
        )
        decision_reason = selection_reason if not use_ai else f'{selection_reason}:{ai_fallback_reason}'
        rejection_reasons = sorted(
            {
                reason
                for item in rejected_assets
                for reason in item.get('rejection_reasons', [])
                if _safe_text(reason)
            }
        )

        decision_trace = {
            'policy': 'official_first',
            'inputs': {
                'game_title': title_text,
                'genre': genre_text,
                'tags': list(tag_values),
                'short_description': description_text,
                'offer_type': offer_type_text,
            },
            'matched_rules': {
                'genre_cluster': genre_trace,
                'visual_type': visual_trace,
                'layout_type': layout_trace,
            },
            'thresholds': {
                'min_readability_score': MIN_READABILITY_SCORE,
                'min_focus_score': MIN_FOCUS_SCORE,
            },
            'asset_summary': {
                'total_candidates': len(scored_assets),
                'official_assets_available': bool(official_assets),
                'official_asset_count': len(official_assets),
                'ai_asset_count': len(ai_assets),
                'official_assets_rejected_count': len(
                    [
                        item
                        for item in rejected_assets
                        if str(item.get('source_type') or '') != AI_SOURCE_TYPE
                    ]
                ),
                'usable_official_assets': len(usable_official_assets),
            },
            'selected_strategy': {
                'use_ai': use_ai,
                'selected_asset_count': len(selected_assets),
                'selected_source_types': [item.candidate.source_type for item in selected_assets],
                'selected_scoring_reasons': [item.scoring_reason for item in selected_assets],
                'ai_fallback_reason': ai_fallback_reason,
                'selection_reason': selection_reason,
                'rejection_reasons': rejection_reasons,
            },
            'close_score_official_tiebreak': bool(selection_trace.get('close_score_official_tiebreak', False)),
            'tiebreak_reason': selection_trace.get('tiebreak_reason'),
            'selection_ranking': [
                {
                    'candidate_index': item.candidate.index,
                    'source_type': item.candidate.source_type,
                    'path_or_url': item.candidate.path_or_url,
                    'source_origin': self._candidate_source_origin(item.candidate),
                    'cache_status': self._candidate_cache_status(item.candidate),
                    'is_local_fallback_candidate': self._is_local_fallback_candidate(item),
                    'safe_close_score_official_candidate': self._is_safe_close_score_official_candidate(item),
                    'visual_anchor_boost_applied': item.visual_anchor_boost_applied,
                    'accepted': item.accepted,
                    'total_score': round(item.total_score, 3),
                    'readability_score': round(item.readability_score, 3),
                    'focus_score': round(item.focus_score, 3),
                    'scoring_reason': item.scoring_reason,
                    'rejection_reason': _primary_rejection_reason(item.rejection_reasons),
                }
                for item in ordered_scores
            ],
        }

        return CoverDecision(
            genre_cluster=genre_cluster,
            visual_type=visual_type,
            image_source_type=image_source_type,
            layout_type=layout_type,
            use_ai=use_ai,
            selected_asset=selected_asset,
            asset_scores=[item.to_dict() for item in ordered_scores],
            rejected_assets=rejected_assets,
            decision_reason=decision_reason,
            decision_trace=decision_trace,
        )

    @staticmethod
    def _normalize_candidates(asset_candidates: Sequence[Mapping[str, Any]] | None) -> list[AssetCandidate]:
        normalized: list[AssetCandidate] = []
        for index, payload in enumerate(asset_candidates or []):
            if isinstance(payload, Mapping):
                normalized.append(AssetCandidate.from_mapping(payload, index=index))
        return normalized

    def _infer_genre_cluster(
        self,
        *,
        combined_text: str,
        offer_type: str,
        candidates: Sequence[AssetCandidate],
    ) -> tuple[str, dict[str, Any]]:
        rules = (
            ('bundle_multi_item', BUNDLE_KEYWORDS),
            ('gameplay_first', GAMEPLAY_KEYWORDS),
            ('motion_vehicle', MOTION_KEYWORDS),
            ('atmospheric_scene', ATMOSPHERIC_KEYWORDS),
            ('cute_cozy_symbolic', COZY_KEYWORDS),
            ('character_driven', CHARACTER_KEYWORDS),
        )
        for cluster, keywords in rules:
            matched = _matched_keywords(combined_text, keywords)
            if matched:
                return cluster, {'rule': 'keyword_match', 'matched_signals': matched}

        screenshot_like = sum(
            1
            for candidate in candidates
            if candidate.is_official
            and (
                candidate.source_type in {'steam_screenshot', 'official_trailer_frame'}
                or 'screenshot' in candidate.kind
                or 'gameplay' in candidate.kind
            )
        )
        poster_like = sum(
            1
            for candidate in candidates
            if candidate.is_official
            and (
                candidate.source_type in {
                    'steam_library_capsule',
                    'steam_main_capsule',
                    'steam_header_capsule',
                    'official_press_key_art',
                    'epic_offer_image',
                }
                or 'capsule' in candidate.kind
                or 'key_art' in candidate.kind
                or 'poster' in candidate.kind
            )
        )
        if 'bundle' in _normalize_text(offer_type) or 'franchise' in _normalize_text(offer_type):
            return 'bundle_multi_item', {'rule': 'offer_type_fallback', 'matched_signals': [_normalize_text(offer_type)]}
        if screenshot_like > poster_like:
            return 'gameplay_first', {'rule': 'candidate_mix_fallback', 'matched_signals': ['screenshot_heavy_assets']}
        if poster_like > 0:
            return 'character_driven', {'rule': 'candidate_mix_fallback', 'matched_signals': ['poster_heavy_assets']}
        return 'atmospheric_scene', {'rule': 'safe_default', 'matched_signals': ['default_scene_bias']}

    def _infer_visual_type(
        self,
        *,
        genre_cluster: str,
        combined_text: str,
        candidates: Sequence[AssetCandidate],
    ) -> tuple[str, dict[str, Any]]:
        if genre_cluster == 'character_driven':
            return 'character', {'rule': 'cluster_default', 'matched_signals': ['character_driven']}
        if genre_cluster == 'atmospheric_scene':
            return 'scene', {'rule': 'cluster_default', 'matched_signals': ['atmospheric_scene']}
        if genre_cluster == 'gameplay_first':
            return 'gameplay', {'rule': 'cluster_default', 'matched_signals': ['gameplay_first']}
        if genre_cluster == 'motion_vehicle':
            return 'scene', {'rule': 'cluster_default', 'matched_signals': ['motion_vehicle']}
        if genre_cluster == 'bundle_multi_item':
            return 'collage', {'rule': 'cluster_default', 'matched_signals': ['bundle_multi_item']}

        candidate_text = ' '.join(candidate.signal_text for candidate in candidates)
        character_hints = _matched_keywords(
            ' '.join((combined_text, candidate_text)),
            ('character', 'hero', 'portrait', 'mascot', 'subject focus', 'subject_focus'),
        )
        if character_hints:
            return 'character', {'rule': 'cozy_character_hint', 'matched_signals': character_hints}
        return 'poster_art', {'rule': 'cozy_safe_default', 'matched_signals': ['poster_art_bias']}

    def _score_asset(
        self,
        candidate: AssetCandidate,
        *,
        visual_type: str,
        genre_cluster: str,
    ) -> ScoredAsset:
        enrichment = self._enrich_asset(candidate)
        size_score = self._size_score(candidate)
        aspect_fit = self._aspect_fit(candidate, visual_type=visual_type)
        metadata_confidence = self._metadata_confidence(candidate)
        weak_metadata_penalty = 0.08 if metadata_confidence < 0.55 else 0.0
        small_asset_penalty = self._small_asset_penalty(candidate)
        base_readability_score = _clamp(
            0.10
            + (0.45 * size_score)
            + (0.20 * aspect_fit)
            + (0.25 * metadata_confidence)
            - small_asset_penalty
            - weak_metadata_penalty
        )
        (
            visual_anchor_boost_applied,
            visual_anchor_readability_boost,
            visual_anchor_focus_boost,
            visual_anchor_boost_reason,
        ) = self._visual_anchor_boost(
            enrichment,
            visual_type=visual_type,
        )
        readability_enrichment_delta, readability_reasons = self._readability_enrichment_delta(
            enrichment,
            base_score=base_readability_score,
            visual_type=visual_type,
            visual_anchor_readability_boost=visual_anchor_readability_boost,
        )
        readability_score = _clamp(base_readability_score + readability_enrichment_delta)

        source_preference = self._source_preference(candidate, visual_type=visual_type)
        kind_preference = self._kind_preference(candidate, visual_type=visual_type)
        metadata_focus = self._metadata_focus(candidate, visual_type=visual_type, genre_cluster=genre_cluster)
        cluster_bonus = self._cluster_bonus(candidate, genre_cluster=genre_cluster)
        base_focus_score = _clamp(
            0.10
            + (0.35 * source_preference)
            + (0.15 * kind_preference)
            + (0.20 * metadata_focus)
            + (0.10 * metadata_confidence)
            + cluster_bonus
            - small_asset_penalty
            - weak_metadata_penalty
        )
        focus_enrichment_delta, focus_reasons = self._focus_enrichment_delta(
            enrichment,
            base_score=base_focus_score,
            visual_type=visual_type,
            visual_anchor_focus_boost=visual_anchor_focus_boost,
        )
        focus_score = _clamp(base_focus_score + focus_enrichment_delta)

        hard_reject_reasons = self._hard_reject_reasons(
            candidate,
            enrichment=enrichment,
            visual_type=visual_type,
            small_asset_penalty=small_asset_penalty,
        )
        accepted = (
            not hard_reject_reasons
            and readability_score >= MIN_READABILITY_SCORE
            and focus_score >= MIN_FOCUS_SCORE
        )
        total_score = _clamp((readability_score * 0.45) + (focus_score * 0.55))
        rejection_reasons: list[str] = list(hard_reject_reasons)
        if not candidate.path_or_url:
            rejection_reasons.append('asset_path_or_url_missing')
        if readability_score < MIN_READABILITY_SCORE:
            rejection_reasons.append('readability_below_threshold')
        if focus_score < MIN_FOCUS_SCORE:
            rejection_reasons.append('focus_below_threshold')
        if small_asset_penalty >= 0.20:
            rejection_reasons.append('asset_too_small')
        if metadata_confidence < 0.55:
            rejection_reasons.append('weak_metadata')
        if candidate.source_type not in KNOWN_SOURCE_TYPES:
            rejection_reasons.append('unknown_source_type')
        rejection_reasons = _dedupe_reasons(rejection_reasons)

        scoring_reasons = list(enrichment.signals)
        if visual_anchor_boost_reason:
            scoring_reasons.append(visual_anchor_boost_reason)
        scoring_reasons.extend(readability_reasons)
        scoring_reasons.extend(focus_reasons)
        if hard_reject_reasons:
            scoring_reasons.extend(f'hard_reject:{reason}' for reason in hard_reject_reasons)
        scoring_reason = '; '.join(dict.fromkeys(item for item in scoring_reasons if _safe_text(item))) or 'base_scoring_only'

        return ScoredAsset(
            candidate=candidate,
            enrichment=enrichment,
            readability_score=readability_score,
            focus_score=focus_score,
            total_score=total_score,
            accepted=accepted,
            visual_anchor_boost_applied=visual_anchor_boost_applied,
            rejection_reasons=rejection_reasons,
            score_breakdown={
                'base_readability_score': round(base_readability_score, 3),
                'base_focus_score': round(base_focus_score, 3),
                'size_score': round(size_score, 3),
                'aspect_fit': round(aspect_fit, 3),
                'metadata_confidence': round(metadata_confidence, 3),
                'source_preference': round(source_preference, 3),
                'kind_preference': round(kind_preference, 3),
                'metadata_focus': round(metadata_focus, 3),
                'cluster_bonus': round(cluster_bonus, 3),
                'readability_enrichment_delta': round(readability_enrichment_delta, 3),
                'focus_enrichment_delta': round(focus_enrichment_delta, 3),
                'visual_anchor_boost_applied': visual_anchor_boost_applied,
                'visual_anchor_readability_boost': round(visual_anchor_readability_boost, 3),
                'visual_anchor_focus_boost': round(visual_anchor_focus_boost, 3),
                'small_asset_penalty': round(small_asset_penalty, 3),
                'weak_metadata_penalty': round(weak_metadata_penalty, 3),
                'scoring_reason_parts': scoring_reasons,
            },
            scoring_reason=scoring_reason,
        )

    def _enrich_asset(self, candidate: AssetCandidate) -> AssetEnrichment:
        local_image_path, local_image_readable, local_width, local_height = self._inspect_local_image(candidate)
        if candidate.width is None and local_width is not None:
            candidate.width = local_width
        if candidate.height is None and local_height is not None:
            candidate.height = local_height

        aspect_ratio = candidate.aspect_ratio
        orientation = self._orientation_from_ratio(aspect_ratio)
        is_vertical = orientation == 'vertical'
        is_squareish = orientation == 'square'
        is_wide_banner = bool(aspect_ratio is not None and aspect_ratio >= 2.1)
        hint_text = self._hint_text(candidate)
        group_hint = _contains_any_keyword(hint_text, GROUP_HINT_KEYWORDS)
        composition_bias = self._composition_bias(candidate, hint_text=hint_text, is_wide_banner=is_wide_banner)
        estimated_subject_scale = self._estimated_subject_scale(
            candidate,
            hint_text=hint_text,
            composition_bias=composition_bias,
            is_vertical=is_vertical,
            group_hint=group_hint,
        )
        estimated_visual_density = self._estimated_visual_density(
            candidate,
            hint_text=hint_text,
            composition_bias=composition_bias,
            group_hint=group_hint,
        )
        estimated_focus = self._estimated_focus(
            hint_text=hint_text,
            composition_bias=composition_bias,
            estimated_subject_scale=estimated_subject_scale,
            estimated_visual_density=estimated_visual_density,
            is_vertical=is_vertical,
            is_wide_banner=is_wide_banner,
        )
        source_strength = self._source_strength(
            candidate,
            composition_bias=composition_bias,
            group_hint=group_hint,
        )
        official_asset_score_boost = self._official_asset_score_boost(
            candidate,
            source_strength=source_strength,
            composition_bias=composition_bias,
            estimated_focus=estimated_focus,
            estimated_subject_scale=estimated_subject_scale,
            estimated_visual_density=estimated_visual_density,
            is_vertical=is_vertical,
            is_wide_banner=is_wide_banner,
            group_hint=group_hint,
        )

        signals: list[str] = [
            f'orientation={orientation}',
            f'composition_bias={composition_bias}',
            f'estimated_focus={estimated_focus}',
            f'estimated_subject_scale={estimated_subject_scale}',
            f'estimated_visual_density={estimated_visual_density}',
            f'source_strength={source_strength:.3f}',
            f'official_asset_score_boost={official_asset_score_boost:+.3f}',
        ]
        if aspect_ratio is not None:
            signals.append(f'aspect_ratio={aspect_ratio:.3f}')
        if local_width is not None and local_height is not None and (
            candidate.width == local_width and candidate.height == local_height
        ):
            signals.append('local_image_dimensions_verified')
        if group_hint:
            signals.append('group_or_multi_subject_hint')
        if local_image_readable is False:
            signals.append('local_image_unreadable')

        return AssetEnrichment(
            asset_metadata_enriched=True,
            orientation=orientation,
            aspect_ratio=aspect_ratio,
            is_vertical=is_vertical,
            is_wide_banner=is_wide_banner,
            is_squareish=is_squareish,
            source_strength=source_strength,
            estimated_focus=estimated_focus,
            estimated_subject_scale=estimated_subject_scale,
            estimated_visual_density=estimated_visual_density,
            composition_bias=composition_bias,
            official_asset_score_boost=official_asset_score_boost,
            signals=tuple(signals),
            local_image_readable=local_image_readable,
            local_image_path=local_image_path,
        )

    @staticmethod
    def _inspect_local_image(candidate: AssetCandidate) -> tuple[str | None, bool | None, int | None, int | None]:
        resolved_path = resolve_existing_asset_path(candidate.path_or_url)
        if resolved_path is None:
            return None, None, None, None
        try:
            with Image.open(resolved_path) as image:
                width, height = image.size
                image.load()
        except (FileNotFoundError, OSError, ValueError):
            return str(resolved_path), False, None, None
        return str(resolved_path), True, _safe_int(width), _safe_int(height)

    @staticmethod
    def _orientation_from_ratio(ratio: float | None) -> str:
        if ratio is None:
            return 'unknown'
        if 0.88 <= ratio <= 1.14:
            return 'square'
        if ratio < 0.88:
            return 'vertical'
        return 'horizontal'

    @staticmethod
    def _hint_text(candidate: AssetCandidate) -> str:
        return ' '.join(
            part
            for part in (
                candidate.signal_text,
                _normalize_text(candidate.path_or_url),
            )
            if part
        )

    @staticmethod
    def _composition_bias(candidate: AssetCandidate, *, hint_text: str, is_wide_banner: bool) -> str:
        if candidate.source_type in {'steam_screenshot', 'official_trailer_frame'}:
            return 'gameplay'
        if candidate.source_type in {
            'official_press_key_art',
            'steam_library_capsule',
            'steam_main_capsule',
            'epic_offer_image',
        }:
            return 'hero'
        if (
            candidate.source_type in {'steam_header_capsule'}
            or is_wide_banner
            or _contains_any_keyword(hint_text, BANNER_HINT_KEYWORDS)
        ):
            return 'banner'
        if candidate.source_type in {'steam_library_hero', 'epic_library_landscape'}:
            return 'scene'
        if _contains_any_keyword(hint_text, GAMEPLAY_HINT_KEYWORDS):
            return 'gameplay'
        if _contains_any_keyword(hint_text, SCENE_HINT_KEYWORDS):
            return 'scene'
        if _contains_any_keyword(hint_text, HERO_HINT_KEYWORDS):
            return 'hero'
        return 'unknown'

    @staticmethod
    def _estimated_subject_scale(
        candidate: AssetCandidate,
        *,
        hint_text: str,
        composition_bias: str,
        is_vertical: bool,
        group_hint: bool,
    ) -> str:
        if _contains_any_keyword(hint_text, LARGE_SUBJECT_HINT_KEYWORDS) and not group_hint:
            return 'large'
        if _contains_any_keyword(hint_text, SMALL_SUBJECT_HINT_KEYWORDS) or group_hint:
            return 'small'
        if is_vertical and candidate.source_type in {
            'official_press_key_art',
            'steam_library_capsule',
            'epic_offer_image',
        }:
            return 'large'
        if composition_bias in {'hero', 'gameplay', 'scene'}:
            return 'medium'
        return 'unknown'

    @staticmethod
    def _estimated_visual_density(
        candidate: AssetCandidate,
        *,
        hint_text: str,
        composition_bias: str,
        group_hint: bool,
    ) -> str:
        if group_hint or _contains_any_keyword(hint_text, CLUTTER_DENSITY_HINT_KEYWORDS):
            return 'cluttered'
        if _contains_any_keyword(hint_text, SIMPLE_DENSITY_HINT_KEYWORDS):
            return 'simple'
        if composition_bias == 'hero' and candidate.source_type in {
            'official_press_key_art',
            'steam_library_capsule',
            'steam_main_capsule',
            'epic_offer_image',
        }:
            return 'simple'
        if composition_bias in {'hero', 'gameplay', 'scene', 'banner'} or candidate.source_type in KNOWN_SOURCE_TYPES:
            return 'medium'
        return 'unknown'

    @staticmethod
    def _estimated_focus(
        *,
        hint_text: str,
        composition_bias: str,
        estimated_subject_scale: str,
        estimated_visual_density: str,
        is_vertical: bool,
        is_wide_banner: bool,
    ) -> str:
        has_focus_hint = _contains_any_keyword(hint_text, HERO_HINT_KEYWORDS)
        if composition_bias == 'banner' or is_wide_banner:
            return 'weak'
        if composition_bias == 'hero':
            if has_focus_hint or (is_vertical and estimated_subject_scale != 'small'):
                return 'strong'
            return 'medium'
        if composition_bias == 'gameplay':
            if has_focus_hint and estimated_visual_density != 'cluttered':
                return 'strong'
            return 'medium'
        if composition_bias == 'scene':
            if estimated_subject_scale == 'small' or estimated_visual_density == 'cluttered':
                return 'weak'
            return 'medium'
        return 'unknown'

    @staticmethod
    def _source_strength(candidate: AssetCandidate, *, composition_bias: str, group_hint: bool) -> float:
        base = SOURCE_STRENGTH_MAP.get(candidate.source_type, 0.52 if candidate.is_official else 0.42)
        if composition_bias == 'hero':
            base += 0.03
        elif composition_bias == 'banner':
            base -= 0.05
        if group_hint:
            base -= 0.04
        return _clamp(base)

    @staticmethod
    def _official_asset_score_boost(
        candidate: AssetCandidate,
        *,
        source_strength: float,
        composition_bias: str,
        estimated_focus: str,
        estimated_subject_scale: str,
        estimated_visual_density: str,
        is_vertical: bool,
        is_wide_banner: bool,
        group_hint: bool,
    ) -> float:
        if not candidate.is_official:
            return 0.0
        boost = 0.0
        if source_strength >= 0.9:
            boost += 0.05
        elif source_strength >= 0.75:
            boost += 0.03
        if composition_bias == 'hero':
            boost += 0.05
        elif composition_bias == 'gameplay':
            boost += 0.02
        elif composition_bias == 'banner':
            boost -= 0.08
        if is_vertical:
            boost += 0.05
        if is_wide_banner:
            boost -= 0.10
        if estimated_focus == 'strong':
            boost += 0.05
        elif estimated_focus == 'medium':
            boost += 0.02
        elif estimated_focus == 'weak':
            boost -= 0.06
        if estimated_subject_scale == 'large':
            boost += 0.04
        elif estimated_subject_scale == 'medium':
            boost += 0.02
        elif estimated_subject_scale == 'small':
            boost -= 0.05
        if estimated_visual_density == 'simple':
            boost += 0.04
        elif estimated_visual_density == 'medium':
            boost += 0.01
        elif estimated_visual_density == 'cluttered':
            boost -= 0.08
        if group_hint:
            boost -= 0.04
        return _clamp_range(boost, -0.25, 0.25)

    @staticmethod
    def _visual_anchor_boost(
        enrichment: AssetEnrichment,
        *,
        visual_type: str,
    ) -> tuple[bool, float, float, str | None]:
        if not (
            enrichment.estimated_subject_scale == 'large'
            and enrichment.estimated_focus == 'strong'
            and enrichment.estimated_visual_density == 'simple'
        ):
            return False, 0.0, 0.0, None
        if enrichment.composition_bias == 'gameplay':
            return False, 0.0, 0.0, 'visual_anchor_boost_skipped:gameplay_bias'
        if visual_type == 'gameplay':
            return False, 0.0, 0.0, 'visual_anchor_boost_skipped:gameplay_visual_type'
        return (
            True,
            VISUAL_ANCHOR_READABILITY_BOOST,
            VISUAL_ANCHOR_FOCUS_BOOST,
            'visual_anchor_boost_applied:strong_large_simple',
        )

    @staticmethod
    def _readability_enrichment_delta(
        enrichment: AssetEnrichment,
        *,
        base_score: float,
        visual_type: str,
        visual_anchor_readability_boost: float = 0.0,
    ) -> tuple[float, list[str]]:
        delta_raw = 0.0
        reasons: list[str] = []

        if visual_type in {'character', 'poster_art'}:
            if enrichment.is_vertical:
                delta_raw += 0.08
                reasons.append('portrait_safe_vertical:+0.080')
            elif enrichment.is_squareish:
                delta_raw += 0.03
                reasons.append('squareish_character_crop:+0.030')
            elif enrichment.is_wide_banner:
                delta_raw -= 0.12
                reasons.append('wide_banner_character_penalty:-0.120')
            else:
                delta_raw -= 0.02
                reasons.append('horizontal_character_crop_penalty:-0.020')
        elif visual_type == 'gameplay':
            if enrichment.composition_bias == 'gameplay':
                delta_raw += 0.05
                reasons.append('gameplay_readability_match:+0.050')
            if enrichment.is_vertical:
                delta_raw -= 0.04
                reasons.append('vertical_gameplay_penalty:-0.040')
            if enrichment.is_wide_banner:
                delta_raw -= 0.04
                reasons.append('wide_banner_penalty:-0.040')
        elif visual_type == 'scene':
            if enrichment.composition_bias in {'scene', 'hero'} and not enrichment.is_vertical:
                delta_raw += 0.03
                reasons.append('scene_crop_fit:+0.030')
            if enrichment.is_wide_banner:
                delta_raw -= 0.05
                reasons.append('wide_banner_penalty:-0.050')
        elif visual_type == 'collage':
            if enrichment.is_squareish or enrichment.is_vertical:
                delta_raw += 0.03
                reasons.append('collage_safe_shape:+0.030')
            if enrichment.is_wide_banner:
                delta_raw -= 0.04
                reasons.append('wide_banner_collage_penalty:-0.040')

        if enrichment.estimated_visual_density == 'simple':
            delta_raw += 0.05
            reasons.append('simple_density_bonus:+0.050')
        elif enrichment.estimated_visual_density == 'medium':
            delta_raw += 0.02
            reasons.append('medium_density_bonus:+0.020')
        elif enrichment.estimated_visual_density == 'cluttered':
            delta_raw -= 0.08
            reasons.append('clutter_penalty:-0.080')

        if enrichment.estimated_subject_scale == 'large':
            delta_raw += 0.03
            reasons.append('large_subject_bonus:+0.030')
        elif enrichment.estimated_subject_scale == 'medium':
            delta_raw += 0.01
            reasons.append('medium_subject_bonus:+0.010')
        elif enrichment.estimated_subject_scale == 'small':
            delta_raw -= 0.05
            reasons.append('small_subject_penalty:-0.050')

        official_boost_share = enrichment.official_asset_score_boost * 0.30
        if official_boost_share:
            delta_raw += official_boost_share
            reasons.append(f'official_boost_share:{official_boost_share:+.3f}')

        if visual_anchor_readability_boost > 0.0:
            delta_raw += visual_anchor_readability_boost
            reasons.append(f'visual_anchor_readability_bonus:{visual_anchor_readability_boost:+.3f}')

        return VisualDecisionEngine._cap_enrichment_delta(
            base_score=base_score,
            raw_delta=delta_raw,
            positive_weight=READABILITY_ENRICHMENT_HEADROOM_WEIGHT,
            max_positive_delta=READABILITY_ENRICHMENT_MAX_POSITIVE_DELTA,
            max_negative_delta=READABILITY_ENRICHMENT_MAX_NEGATIVE_DELTA,
            reasons=reasons,
            score_name='readability',
        )

    @staticmethod
    def _focus_enrichment_delta(
        enrichment: AssetEnrichment,
        *,
        base_score: float,
        visual_type: str,
        visual_anchor_focus_boost: float = 0.0,
    ) -> tuple[float, list[str]]:
        delta_raw = 0.0
        reasons: list[str] = []

        if enrichment.estimated_focus == 'strong':
            delta_raw += 0.10
            reasons.append('strong_focus_bonus:+0.100')
        elif enrichment.estimated_focus == 'medium':
            delta_raw += 0.04
            reasons.append('medium_focus_bonus:+0.040')
        elif enrichment.estimated_focus == 'weak':
            delta_raw -= 0.10
            reasons.append('weak_focus_penalty:-0.100')

        if enrichment.estimated_subject_scale == 'large':
            delta_raw += 0.05
            reasons.append('large_subject_focus_bonus:+0.050')
        elif enrichment.estimated_subject_scale == 'medium':
            delta_raw += 0.02
            reasons.append('medium_subject_focus_bonus:+0.020')
        elif enrichment.estimated_subject_scale == 'small':
            delta_raw -= 0.06
            reasons.append('small_subject_focus_penalty:-0.060')

        if visual_type in {'character', 'poster_art'}:
            if enrichment.composition_bias == 'hero':
                delta_raw += 0.08
                reasons.append('hero_match_bonus:+0.080')
            elif enrichment.composition_bias == 'scene':
                delta_raw -= 0.06
                reasons.append('scene_without_hero_penalty:-0.060')
            elif enrichment.composition_bias == 'gameplay':
                delta_raw -= 0.03
                reasons.append('gameplay_character_penalty:-0.030')
            elif enrichment.composition_bias == 'banner':
                delta_raw -= 0.12
                reasons.append('banner_focus_penalty:-0.120')
        elif visual_type == 'gameplay':
            if enrichment.composition_bias == 'gameplay':
                delta_raw += 0.09
                reasons.append('gameplay_focus_match:+0.090')
            elif enrichment.composition_bias == 'scene':
                delta_raw -= 0.04
                reasons.append('scene_over_gameplay_penalty:-0.040')
            elif enrichment.composition_bias == 'banner':
                delta_raw -= 0.08
                reasons.append('banner_focus_penalty:-0.080')
        elif visual_type == 'scene':
            if enrichment.composition_bias == 'scene':
                delta_raw += 0.07
                reasons.append('scene_focus_match:+0.070')
            elif enrichment.composition_bias == 'hero':
                delta_raw += 0.04
                reasons.append('hero_scene_bonus:+0.040')
            elif enrichment.composition_bias == 'banner':
                delta_raw -= 0.08
                reasons.append('banner_focus_penalty:-0.080')
        elif visual_type == 'collage':
            if enrichment.composition_bias == 'hero':
                delta_raw += 0.04
                reasons.append('hero_collage_bonus:+0.040')
            elif enrichment.composition_bias == 'banner':
                delta_raw -= 0.05
                reasons.append('banner_collage_penalty:-0.050')

        official_boost_share = enrichment.official_asset_score_boost * 0.35
        if official_boost_share:
            delta_raw += official_boost_share
            reasons.append(f'official_boost_share:{official_boost_share:+.3f}')

        if visual_anchor_focus_boost > 0.0:
            delta_raw += visual_anchor_focus_boost
            reasons.append(f'visual_anchor_focus_bonus:{visual_anchor_focus_boost:+.3f}')

        return VisualDecisionEngine._cap_enrichment_delta(
            base_score=base_score,
            raw_delta=delta_raw,
            positive_weight=FOCUS_ENRICHMENT_HEADROOM_WEIGHT,
            max_positive_delta=FOCUS_ENRICHMENT_MAX_POSITIVE_DELTA,
            max_negative_delta=FOCUS_ENRICHMENT_MAX_NEGATIVE_DELTA,
            reasons=reasons,
            score_name='focus',
        )

    @staticmethod
    def _cap_enrichment_delta(
        *,
        base_score: float,
        raw_delta: float,
        positive_weight: float,
        max_positive_delta: float,
        max_negative_delta: float,
        reasons: list[str],
        score_name: str,
    ) -> tuple[float, list[str]]:
        if raw_delta >= 0.0:
            positive_headroom_cap = max(0.0, (1.0 - _clamp(base_score)) * positive_weight)
            applied_positive_cap = min(max_positive_delta, positive_headroom_cap)
            capped_delta = min(raw_delta, applied_positive_cap)
            reasons.append(f'{score_name}_delta_raw:{raw_delta:+.3f}')
            reasons.append(f'{score_name}_delta_cap:{applied_positive_cap:+.3f}')
        else:
            capped_delta = max(raw_delta, -max_negative_delta)
            reasons.append(f'{score_name}_delta_raw:{raw_delta:+.3f}')
            reasons.append(f'{score_name}_delta_cap:{(-max_negative_delta):+.3f}')
        if abs(capped_delta - raw_delta) >= 0.001:
            reasons.append(f'{score_name}_delta_capped:{raw_delta:+.3f}->{capped_delta:+.3f}')
        return capped_delta, reasons

    @staticmethod
    def _hard_reject_reasons(
        candidate: AssetCandidate,
        *,
        enrichment: AssetEnrichment,
        visual_type: str,
        small_asset_penalty: float,
    ) -> list[str]:
        reasons: list[str] = []
        if candidate.width is None or candidate.height is None:
            reasons.append('missing_dimensions')
        if small_asset_penalty >= 0.35:
            reasons.append('asset_too_small')
        if enrichment.local_image_readable is False:
            reasons.append('invalid_or_unreadable_file')
        if visual_type in {'character', 'poster_art'}:
            if enrichment.composition_bias == 'banner' or enrichment.is_wide_banner:
                reasons.append('banner_only_for_portrait_intent')
            if (
                enrichment.composition_bias in {'scene', 'banner'}
                and enrichment.estimated_subject_scale in {'small', 'unknown'}
                and enrichment.estimated_focus in {'weak', 'unknown'}
            ):
                reasons.append('environment_only_for_character_intent')
        return _dedupe_reasons(reasons)

    @staticmethod
    def _size_score(candidate: AssetCandidate) -> float:
        if candidate.width is None or candidate.height is None:
            return 0.45
        width_score = min(float(candidate.width) / 1280.0, 1.0)
        height_score = min(float(candidate.height) / 720.0, 1.0)
        return _clamp((0.55 * width_score) + (0.45 * height_score))

    @staticmethod
    def _small_asset_penalty(candidate: AssetCandidate) -> float:
        if candidate.width is None or candidate.height is None:
            return 0.10
        if candidate.width < 320 or candidate.height < 180:
            return 0.35
        if candidate.width < 640 or candidate.height < 360:
            return 0.22
        if candidate.width < 960 or candidate.height < 540:
            return 0.08
        return 0.0

    @staticmethod
    def _aspect_fit(candidate: AssetCandidate, *, visual_type: str) -> float:
        ratio = candidate.aspect_ratio
        if ratio is None:
            return 0.55
        targets = {
            'character': (0.66, 0.75, 1.0, 2.14),
            'poster_art': (0.66, 0.75, 1.0, 2.14),
            'scene': (1.78, 2.14, 2.66, 1.33),
            'gameplay': (1.78, 2.14, 2.66, 1.33),
            'collage': (0.66, 1.0, 1.78, 2.14),
        }.get(visual_type, (1.0, 1.78))
        best = max(
            _clamp(1.0 - (abs(ratio - target) / max(target, ratio, 0.25)))
            for target in targets
        )
        if 0.5 <= ratio <= 3.0:
            best = max(best, 0.45)
        return _clamp(best)

    @staticmethod
    def _metadata_confidence(candidate: AssetCandidate) -> float:
        filled_fields = sum(
            1
            for value in candidate.metadata.values()
            if value not in (None, '', [], {}, ())
        )
        confidence = 0.30 + (0.10 * min(filled_fields, 4))
        if candidate.path_or_url:
            confidence += 0.05
        if candidate.source_type in KNOWN_SOURCE_TYPES:
            confidence += 0.10
        return _clamp(confidence)

    @staticmethod
    def _source_preference(candidate: AssetCandidate, *, visual_type: str) -> float:
        preferences = VISUAL_SOURCE_PREFERENCE.get(visual_type, {})
        if candidate.source_type in preferences:
            return preferences[candidate.source_type]
        return 0.48 if candidate.is_official else 0.7

    @staticmethod
    def _kind_preference(candidate: AssetCandidate, *, visual_type: str) -> float:
        normalized_kind = candidate.kind
        if visual_type == 'gameplay':
            if 'screenshot' in normalized_kind or 'gameplay' in normalized_kind or 'trailer' in normalized_kind:
                return 1.0
            if 'hero' in normalized_kind or 'landscape' in normalized_kind:
                return 0.75
            if 'capsule' in normalized_kind or 'poster' in normalized_kind or 'key_art' in normalized_kind:
                return 0.42
            return 0.55
        if visual_type == 'scene':
            if 'hero' in normalized_kind or 'landscape' in normalized_kind or 'trailer' in normalized_kind:
                return 1.0
            if 'key_art' in normalized_kind or 'poster' in normalized_kind:
                return 0.86
            if 'screenshot' in normalized_kind:
                return 0.84
            return 0.6
        if visual_type == 'collage':
            if 'capsule' in normalized_kind or 'key_art' in normalized_kind or 'poster' in normalized_kind:
                return 0.96
            if 'screenshot' in normalized_kind or 'hero' in normalized_kind:
                return 0.8
            return 0.62
        if visual_type in {'character', 'poster_art'}:
            if 'key_art' in normalized_kind or 'poster' in normalized_kind or 'capsule' in normalized_kind:
                return 1.0
            if 'hero' in normalized_kind:
                return 0.82
            if 'screenshot' in normalized_kind:
                return 0.5
            return 0.64
        return 0.6

    @staticmethod
    def _metadata_focus(candidate: AssetCandidate, *, visual_type: str, genre_cluster: str) -> float:
        signal_text = candidate.signal_text
        score = 0.0
        if visual_type == 'character' and _contains_any(
            signal_text,
            ('character', 'hero', 'portrait', 'subject', 'subject_focus', 'foreground'),
        ):
            score += 0.35
        if visual_type == 'scene' and _contains_any(signal_text, ('scene', 'landscape', 'environment', 'atmosphere', 'wide')):
            score += 0.32
        if visual_type == 'gameplay' and _contains_any(signal_text, ('gameplay', 'hud', 'combat', 'map', 'city', 'factory', 'builder')):
            score += 0.38
        if visual_type == 'poster_art' and _contains_any(signal_text, ('poster', 'cover', 'key art', 'key_art', 'logo_safe')):
            score += 0.34
        if visual_type == 'collage' and _contains_any(signal_text, ('franchise', 'collection', 'multi', 'series')):
            score += 0.30
        if genre_cluster == 'motion_vehicle' and _contains_any(signal_text, ('vehicle', 'car', 'racing', 'drift', 'speed')):
            score += 0.15
        if genre_cluster == 'atmospheric_scene' and _contains_any(signal_text, ('fog', 'dark', 'night', 'horror', 'moody')):
            score += 0.12
        return _clamp(score)

    @staticmethod
    def _cluster_bonus(candidate: AssetCandidate, *, genre_cluster: str) -> float:
        signal_text = candidate.signal_text
        if genre_cluster == 'gameplay_first' and candidate.source_type in {'steam_screenshot', 'official_trailer_frame'}:
            return 0.10
        if genre_cluster == 'motion_vehicle' and candidate.source_type in {'steam_screenshot', 'official_trailer_frame', 'official_press_key_art'}:
            return 0.10 if _contains_any(signal_text, ('vehicle', 'car', 'racing', 'speed')) else 0.05
        if genre_cluster == 'character_driven' and candidate.source_type in {'steam_library_capsule', 'steam_main_capsule', 'official_press_key_art'}:
            return 0.08
        if genre_cluster == 'atmospheric_scene' and candidate.source_type in {'steam_library_hero', 'epic_library_landscape', 'official_press_key_art'}:
            return 0.08
        if genre_cluster == 'bundle_multi_item':
            return 0.06
        if genre_cluster == 'cute_cozy_symbolic' and candidate.source_type in {'official_press_key_art', 'steam_main_capsule', 'steam_library_capsule'}:
            return 0.06
        return 0.0

    @staticmethod
    def _candidate_source_origin(candidate: AssetCandidate) -> str:
        return _normalize_text(candidate.metadata.get('source_origin')) or 'unknown'

    @staticmethod
    def _candidate_cache_status(candidate: AssetCandidate) -> str:
        return _normalize_text(candidate.metadata.get('cache_status')) or 'unknown'

    @staticmethod
    def _candidate_remote_url(candidate: AssetCandidate) -> str | None:
        return _safe_text(candidate.metadata.get('remote_url')) or None

    @staticmethod
    def _candidate_has_local_asset_file(candidate: AssetCandidate) -> bool:
        cache_path = _safe_text(candidate.metadata.get('cache_path')) or None
        return (
            _resolve_local_readable_image_path(cache_path) is not None
            or _resolve_local_readable_image_path(candidate.path_or_url) is not None
        )

    @classmethod
    def _is_local_fallback_candidate(cls, item: ScoredAsset) -> bool:
        return (
            cls._candidate_source_origin(item.candidate) in LOCAL_FALLBACK_SOURCE_ORIGINS
            and not cls._candidate_remote_url(item.candidate)
        )

    @classmethod
    def _is_safe_close_score_official_candidate(cls, item: ScoredAsset) -> bool:
        if not item.candidate.is_official or not item.accepted:
            return False
        if cls._is_local_fallback_candidate(item):
            return False
        if item.enrichment.estimated_focus == 'weak':
            return False
        if item.enrichment.estimated_subject_scale == 'small':
            return False
        if item.enrichment.estimated_visual_density == 'cluttered':
            return False
        if _primary_rejection_reason(item.rejection_reasons) is not None:
            return False
        return (
            cls._candidate_cache_status(item.candidate) in SAFE_LOCAL_ASSET_CACHE_STATUSES
            or cls._candidate_has_local_asset_file(item.candidate)
        )

    def _select_primary_asset_with_tiebreak(
        self,
        *,
        ranked: Sequence[ScoredAsset],
    ) -> tuple[ScoredAsset, dict[str, Any]]:
        top_candidate = ranked[0]
        trace = {
            'close_score_official_tiebreak': False,
            'tiebreak_reason': 'top_ranked_candidate_not_local_fallback',
            'tiebreak_displaced_candidate_index': None,
            'tiebreak_selected_candidate_index': top_candidate.candidate.index,
        }
        if len(ranked) == 1:
            trace['tiebreak_reason'] = 'single_candidate_only'
            return top_candidate, trace
        if not self._is_local_fallback_candidate(top_candidate):
            return top_candidate, trace

        for candidate in ranked[1:]:
            score_diff = max(0.0, top_candidate.total_score - candidate.total_score)
            if score_diff > CLOSE_SCORE_OFFICIAL_TIEBREAK_THRESHOLD:
                break
            if not self._is_safe_close_score_official_candidate(candidate):
                continue
            trace.update(
                {
                    'close_score_official_tiebreak': True,
                    'tiebreak_reason': (
                        'selected_safe_official_candidate_over_local_fallback:'
                        f'{top_candidate.candidate.source_type}->{candidate.candidate.source_type};'
                        f'top_origin={self._candidate_source_origin(top_candidate.candidate)};'
                        f'selected_origin={self._candidate_source_origin(candidate.candidate)};'
                        f'selected_cache_status={self._candidate_cache_status(candidate.candidate)};'
                        f'score_diff={score_diff:.3f}'
                    ),
                    'tiebreak_displaced_candidate_index': top_candidate.candidate.index,
                    'tiebreak_selected_candidate_index': candidate.candidate.index,
                }
            )
            return candidate, trace

        trace['tiebreak_reason'] = (
            f'no_safe_official_candidate_within_{CLOSE_SCORE_OFFICIAL_TIEBREAK_THRESHOLD:.2f}'
        )
        return top_candidate, trace

    def _select_assets(
        self,
        *,
        genre_cluster: str,
        candidates: Sequence[ScoredAsset],
    ) -> tuple[list[ScoredAsset], dict[str, Any]]:
        ranked = self._ordered_asset_scores(candidates)
        if not ranked:
            return [], {
                'close_score_official_tiebreak': False,
                'tiebreak_reason': 'no_candidates',
                'tiebreak_displaced_candidate_index': None,
                'tiebreak_selected_candidate_index': None,
            }
        if genre_cluster != 'bundle_multi_item':
            selected, trace = self._select_primary_asset_with_tiebreak(ranked=ranked)
            return [selected], trace
        bundle_trace = {
            'close_score_official_tiebreak': False,
            'tiebreak_reason': 'not_applicable_bundle_selection',
            'tiebreak_displaced_candidate_index': None,
            'tiebreak_selected_candidate_index': ranked[0].candidate.index,
        }
        if len(ranked) >= 4:
            return ranked[:4], bundle_trace
        if len(ranked) >= 3:
            return ranked[:3], bundle_trace
        if len(ranked) >= 2:
            return ranked[:2], bundle_trace
        return ranked[:1], bundle_trace

    def _ordered_asset_scores(self, scored_assets: Sequence[ScoredAsset]) -> list[ScoredAsset]:
        return sorted(
            list(scored_assets),
            key=lambda item: (
                0 if item.candidate.is_official else 1,
                -item.total_score,
                -item.focus_score,
                -item.readability_score,
                -item.candidate.area,
                item.candidate.source_type,
                item.candidate.path_or_url,
            ),
        )

    def _infer_layout_type(
        self,
        *,
        genre_cluster: str,
        visual_type: str,
        selected_assets: Sequence[ScoredAsset],
    ) -> tuple[str, dict[str, Any]]:
        asset_count = len(selected_assets)
        primary = selected_assets[0] if selected_assets else None
        primary_source_type = primary.candidate.source_type if primary is not None else AI_SOURCE_TYPE

        if genre_cluster == 'bundle_multi_item':
            if asset_count >= 4:
                return 'four_tile_franchise', {'rule': 'bundle_collage', 'matched_signals': ['four_assets']}
            if asset_count == 3:
                return 'three_tile_collage', {'rule': 'bundle_collage', 'matched_signals': ['three_assets']}
            if asset_count == 2:
                return 'two_tile_split', {'rule': 'bundle_collage', 'matched_signals': ['two_assets']}
            return 'landscape_scene_crop', {'rule': 'bundle_safe_fallback', 'matched_signals': ['single_asset_only']}

        if visual_type == 'gameplay':
            if primary_source_type in {'steam_screenshot', 'official_trailer_frame'}:
                return 'gameplay_frame', {'rule': 'gameplay_primary', 'matched_signals': [primary_source_type]}
            return 'landscape_scene_crop', {'rule': 'gameplay_landscape_fallback', 'matched_signals': [primary_source_type]}

        if visual_type == 'scene':
            return 'landscape_scene_crop', {'rule': 'scene_primary', 'matched_signals': [primary_source_type]}

        if visual_type in {'character', 'poster_art'}:
            if primary_source_type in {
                'steam_library_capsule',
                'steam_main_capsule',
                'steam_header_capsule',
                'official_press_key_art',
                'epic_offer_image',
            }:
                return 'portrait_single_logo_safe', {'rule': 'poster_safe_primary', 'matched_signals': [primary_source_type]}
            return 'portrait_single', {'rule': 'character_primary', 'matched_signals': [primary_source_type]}

        return 'landscape_scene_crop', {'rule': 'safe_default', 'matched_signals': [primary_source_type]}

    @staticmethod
    def _serialize_selected_assets(
        *,
        selected_assets: Sequence[ScoredAsset],
        layout_type: str,
    ) -> dict[str, Any] | None:
        if not selected_assets:
            return None
        if len(selected_assets) == 1:
            payload = selected_assets[0].to_dict()
            payload['selection_mode'] = 'single'
            payload['layout_type'] = layout_type
            return payload

        serialized_assets = [item.to_dict() for item in selected_assets]
        primary = serialized_assets[0]
        return {
            'selection_mode': 'collage',
            'layout_type': layout_type,
            'source_type': primary.get('source_type'),
            'kind': 'collage',
            'path_or_url': None,
            'width': None,
            'height': None,
            'metadata': {
                'asset_count': len(serialized_assets),
                'source_types': [item.get('source_type') for item in serialized_assets],
            },
            'readability_score': round(
                sum(float(item.get('readability_score') or 0.0) for item in serialized_assets) / len(serialized_assets),
                3,
            ),
            'focus_score': round(
                sum(float(item.get('focus_score') or 0.0) for item in serialized_assets) / len(serialized_assets),
                3,
            ),
            'total_score': round(
                sum(float(item.get('total_score') or 0.0) for item in serialized_assets) / len(serialized_assets),
                3,
            ),
            'accepted': all(bool(item.get('accepted')) for item in serialized_assets),
            'assets': serialized_assets,
        }

    @staticmethod
    def _collect_rejected_assets(
        *,
        scored_assets: Sequence[ScoredAsset],
        selected_indexes: set[int],
        use_ai: bool,
        genre_cluster: str,
        selection_trace: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        rejected_assets: list[dict[str, Any]] = []
        tiebreak_displaced_candidate_index = _safe_int(
            None if selection_trace is None else selection_trace.get('tiebreak_displaced_candidate_index')
        )
        close_score_official_tiebreak = bool(
            False if selection_trace is None else selection_trace.get('close_score_official_tiebreak', False)
        )
        for item in scored_assets:
            if item.candidate.index in selected_indexes:
                continue
            payload = item.to_dict()
            reasons = list(payload.get('rejection_reasons') or [])
            if item.candidate.is_official and item.accepted:
                if genre_cluster == 'bundle_multi_item' and not use_ai:
                    reasons.append('not_needed_for_selected_collage_layout')
                elif close_score_official_tiebreak and item.candidate.index == tiebreak_displaced_candidate_index:
                    reasons.append('close_score_official_tiebreak_over_local_fallback')
                else:
                    reasons.append('lower_rank_than_selected_asset')
            elif not item.candidate.is_official:
                reasons.append('lower_rank_than_selected_ai_asset' if use_ai else 'ai_not_primary_under_official_first_policy')
            elif not reasons:
                reasons.append('official_asset_failed_thresholds')
            payload['rejection_reasons'] = _dedupe_reasons(reasons)
            payload['rejection_reason'] = _primary_rejection_reason(payload['rejection_reasons'])
            rejected_assets.append(payload)
        return rejected_assets

    def _synthetic_ai_asset(self, *, genre_cluster: str, visual_type: str) -> ScoredAsset:
        candidate = AssetCandidate(
            index=-1,
            source_type=AI_SOURCE_TYPE,
            width=None,
            height=None,
            kind=f'synthetic_{visual_type}',
            path_or_url=f'ai://generated/{genre_cluster}/{visual_type}',
            metadata={
                'synthetic_candidate': True,
                'genre_cluster': genre_cluster,
                'visual_type': visual_type,
            },
        )
        enrichment = AssetEnrichment(
            asset_metadata_enriched=True,
            orientation='unknown',
            aspect_ratio=None,
            is_vertical=False,
            is_wide_banner=False,
            is_squareish=False,
            source_strength=0.0,
            estimated_focus='unknown',
            estimated_subject_scale='unknown',
            estimated_visual_density='unknown',
            composition_bias='unknown',
            official_asset_score_boost=0.0,
            signals=('synthetic_ai_placeholder',),
        )
        return ScoredAsset(
            candidate=candidate,
            enrichment=enrichment,
            readability_score=0.0,
            focus_score=0.0,
            total_score=0.0,
            accepted=False,
            rejection_reasons=[],
            score_breakdown={
                'synthetic_candidate': True,
            },
            scoring_reason='synthetic_ai_placeholder',
        )


DEFAULT_VISUAL_DECISION_ENGINE = VisualDecisionEngine()


def build_cover_decision(
    *,
    game_title: str,
    genre: str | None,
    tags: Sequence[str] | None,
    short_description: str | None,
    offer_type: str | None,
    asset_candidates: Sequence[Mapping[str, Any]] | None,
) -> CoverDecision:
    return DEFAULT_VISUAL_DECISION_ENGINE.decide(
        game_title=game_title,
        genre=genre,
        tags=tags,
        short_description=short_description,
        offer_type=offer_type,
        asset_candidates=asset_candidates,
    )


def is_official_like_source_type(source_type: str | None) -> bool:
    return _normalize_text(source_type) in OFFICIAL_LIKE_SOURCE_TYPES


def resolve_cover_decision_asset_bridge(cover_decision: Mapping[str, Any] | None) -> DecisionAssetBridge:
    if not isinstance(cover_decision, Mapping):
        return DecisionAssetBridge(
            selected_asset=None,
            selected_asset_source_type=None,
            resolved_local_path=None,
            candidate_valid=False,
            decision_asset_use_reason=None,
            decision_asset_reject_reason='cover_decision_missing',
        )

    if bool(cover_decision.get('use_ai', False)):
        selected_asset = cover_decision.get('selected_asset')
        payload = dict(selected_asset) if isinstance(selected_asset, Mapping) else None
        return DecisionAssetBridge(
            selected_asset=payload,
            selected_asset_source_type=_normalize_text(None if payload is None else payload.get('source_type')) or None,
            resolved_local_path=None,
            candidate_valid=False,
            decision_asset_use_reason=None,
            decision_asset_reject_reason='decision_prefers_ai',
        )

    selected_asset = cover_decision.get('selected_asset')
    if not isinstance(selected_asset, Mapping):
        return DecisionAssetBridge(
            selected_asset=None,
            selected_asset_source_type=None,
            resolved_local_path=None,
            candidate_valid=False,
            decision_asset_use_reason=None,
            decision_asset_reject_reason='invalid_or_nonlocal_asset_path',
        )

    payload = {str(key): _json_ready(value) for key, value in selected_asset.items()}
    source_type = _normalize_text(payload.get('source_type')) or None
    resolved_path = _resolve_local_readable_image_path(payload.get('path_or_url'))
    if resolved_path is None:
        return DecisionAssetBridge(
            selected_asset=payload,
            selected_asset_source_type=source_type,
            resolved_local_path=None,
            candidate_valid=False,
            decision_asset_use_reason=None,
            decision_asset_reject_reason='invalid_or_nonlocal_asset_path',
        )

    if not is_official_like_source_type(source_type):
        return DecisionAssetBridge(
            selected_asset=payload,
            selected_asset_source_type=source_type,
            resolved_local_path=None,
            candidate_valid=False,
            decision_asset_use_reason=None,
            decision_asset_reject_reason='non_official_source_type',
        )

    return DecisionAssetBridge(
        selected_asset=payload,
        selected_asset_source_type=source_type,
        resolved_local_path=str(resolved_path),
        candidate_valid=True,
        decision_asset_use_reason='cover_decision_selected_official_asset',
        decision_asset_reject_reason=None,
    )


def _resolve_local_readable_image_path(value: Any) -> str | None:
    candidate_path = resolve_existing_asset_path(_safe_text(value) or None)
    if candidate_path is None:
        return None
    resolved_path = _safe_resolve_path(candidate_path)
    if resolved_path is None:
        return None
    try:
        with Image.open(resolved_path) as image:
            image.verify()
    except (FileNotFoundError, OSError, ValueError):
        return None
    return str(resolved_path)


def _safe_resolve_path(path: Path) -> Path | None:
    try:
        resolved = path.resolve()
    except OSError:
        return None
    if not resolved.exists() or not resolved.is_file():
        return None
    return resolved


__all__ = [
    'AI_SOURCE_TYPE',
    'CoverDecision',
    'DecisionAssetBridge',
    'DEFAULT_VISUAL_DECISION_ENGINE',
    'OFFICIAL_LIKE_SOURCE_TYPES',
    'MIN_FOCUS_SCORE',
    'MIN_READABILITY_SCORE',
    'VisualDecisionEngine',
    'build_cover_decision',
    'is_official_like_source_type',
    'resolve_cover_decision_asset_bridge',
]
