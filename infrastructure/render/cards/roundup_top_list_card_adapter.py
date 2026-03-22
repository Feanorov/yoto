from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from domain.entities.roundup_post import RoundupPost
from infrastructure.render.cards.yoto_card_engine_v4 import YotoCardData, YotoCardEngineV4, YotoCardType


@dataclass(slots=True)
class RoundupCardRenderResult:
    image_path: Path
    diagnostics: dict[str, Any]


class RoundupTopListCardAdapter:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir = self.output_dir / '_roundup_cache'
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.engine = YotoCardEngineV4(self.output_dir)

    def render(self, roundup: RoundupPost) -> RoundupCardRenderResult:
        platform = self._platform_label(roundup)
        lead_artwork = self._resolve_lead_artwork(roundup)
        result = self.engine.render_card(
            YotoCardData(
                title=roundup.title,
                platform=platform,
                type=YotoCardType.TOP_LIST,
                deadline=None,
                old_price=None,
                artwork_path=lead_artwork['artwork_path'],
                slug=f'roundup_{roundup.roundup_id}',
                platform_badge=f'{platform} TOP',
                sticker_header='TOP LIST',
                sticker_text=f'Top {roundup.item_count}',
                brand_micro_label='YOTO PICKS',
                list_label=roundup.theme_label,
                editorial_phrase=self._editorial_phrase(roundup),
                hero_selection=lead_artwork['hero_selection'],
            )
        )
        diagnostics = self._build_diagnostics(result, lead_artwork)
        return RoundupCardRenderResult(image_path=result.image_path, diagnostics=diagnostics)

    def _resolve_lead_artwork(self, roundup: RoundupPost) -> dict[str, Any]:
        evaluations: list[dict[str, Any]] = []
        warnings: list[str] = []
        selected: dict[str, Any] | None = None
        for item in roundup.items:
            selection_score = self._lead_artwork_selection_score(
                roundup,
                item.rank,
                item.score,
                item.discount_percent,
                item.review_score,
                item.is_freebie,
                item.reason_tags,
            )
            materialized = self._materialize_artwork(item.lead_artwork_url, roundup.roundup_id, item.offer_id)
            status = str(materialized['status'])
            if status == 'download_failed':
                warnings.append('lead_artwork_materialization_failed')
            evaluation = {
                'offer_id': item.offer_id,
                'title': item.title,
                'rank': item.rank,
                'source': item.source,
                'artwork_url': item.lead_artwork_url,
                'selection_score': round(selection_score, 2),
                'materialization_status': status,
                'materialized_path': str(materialized['path']) if materialized['path'] else None,
                'discount_percent': item.discount_percent,
                'review_score': item.review_score,
                'reason_tags': list(item.reason_tags),
                'is_freebie': item.is_freebie,
            }
            evaluations.append(evaluation)
            if materialized['path'] is None:
                continue
            if selected is None or selection_score > float(selected['selection_score']):
                selected = {
                    **evaluation,
                    'artwork_path': materialized['path'],
                }

        if selected is None:
            warnings.append('fallback_artwork')
            return {
                'artwork_path': None,
                'selected_offer_id': None,
                'selected_rank': None,
                'selected_url': None,
                'selected_asset_path': None,
                'selection_reason': 'no_usable_roundup_artwork',
                'warnings': self._dedupe(warnings),
                'hero_selection': {
                    'selected_source': 'placeholder',
                    'reason': 'no_usable_roundup_artwork',
                    'candidates_evaluated': len(evaluations),
                    'rejected_capsules': [],
                    'score_summary': evaluations,
                    'fallback_used': True,
                },
            }

        return {
            'artwork_path': selected['artwork_path'],
            'selected_offer_id': selected['offer_id'],
            'selected_rank': selected['rank'],
            'selected_url': selected['artwork_url'],
            'selected_asset_path': selected['materialized_path'],
            'selection_reason': 'highest_weighted_roundup_item_artwork',
            'warnings': self._dedupe(warnings),
            'hero_selection': {
                'selected_source': 'roundup_item_artwork',
                'reason': 'highest_weighted_roundup_item_artwork',
                'candidates_evaluated': len(evaluations),
                'rejected_capsules': [],
                'score_summary': evaluations,
                'fallback_used': False,
            },
        }

    def _build_diagnostics(self, result, lead_artwork: dict[str, Any]) -> dict[str, Any]:
        diagnostics = self._json_ready(asdict(result.diagnostics))
        warnings = list(lead_artwork.get('warnings') or [])
        if diagnostics.get('used_placeholder_artwork'):
            warnings.append('fallback_artwork')
        diagnostics.update(
            {
                'source': 'roundup_top_list_adapter',
                'template_id': 'roundup_digest',
                'renderer_requested': 'yoto_v4',
                'renderer_selected': 'yoto_v4',
                'renderer_family': 'yoto_v4',
                'renderer_fallback_used': False,
                'layout_variant': 'yoto_v4_top_list',
                'asset_used': lead_artwork.get('selected_url'),
                'hero_asset_used': lead_artwork.get('selected_url'),
                'selected_asset_path': lead_artwork.get('selected_asset_path'),
                'lead_artwork_selected_offer_id': lead_artwork.get('selected_offer_id'),
                'lead_artwork_selected_rank': lead_artwork.get('selected_rank'),
                'lead_artwork_selected_url': lead_artwork.get('selected_url'),
                'lead_artwork_selection_reason': lead_artwork.get('selection_reason'),
                'render_warnings': self._dedupe(warnings),
            }
        )
        return diagnostics

    def _materialize_artwork(self, artwork_url: str | None, roundup_id: str, offer_id: str) -> dict[str, Path | str | None]:
        if not artwork_url:
            return {'path': None, 'status': 'missing_artwork_url'}
        try:
            parsed = urlparse(artwork_url)
            if parsed.scheme in {'http', 'https'}:
                suffix = Path(parsed.path).suffix.lower()
                if suffix not in {'.png', '.jpg', '.jpeg', '.webp'}:
                    suffix = '.png'
                cache_name = f'{self._slug(roundup_id)}_{self._slug(offer_id)}_{hashlib.sha1(artwork_url.encode("utf-8")).hexdigest()[:12]}{suffix}'
                cache_path = self.cache_dir / cache_name
                if not cache_path.exists():
                    request = Request(artwork_url, headers={'User-Agent': 'YOTO Roundup Card/1.0'})
                    with urlopen(request, timeout=10) as response:
                        cache_path.write_bytes(response.read())
                return {'path': cache_path, 'status': 'materialized_remote'}
            local_path = Path(artwork_url)
            if local_path.exists():
                return {'path': local_path, 'status': 'existing_local_path'}
        except Exception:
            return {'path': None, 'status': 'download_failed'}
        return {'path': None, 'status': 'unusable_artwork_url'}

    @staticmethod
    def _lead_artwork_selection_score(
        roundup: RoundupPost,
        rank: int,
        item_score: float,
        discount_percent: int,
        review_score: int | None,
        is_freebie: bool,
        reason_tags: list[str],
    ) -> float:
        score = float(item_score or 0.0)
        score += max(0, (roundup.item_count + 1) - rank) * 6.0
        score += max(0, discount_percent) * 0.35
        score += float(review_score or 0) * 0.15
        if is_freebie:
            score += 8.0
        if 'hero_discount' in set(reason_tags or []):
            score += 10.0
        return score

    @staticmethod
    def _platform_label(roundup: RoundupPost) -> str:
        sources = {str(item.source or '').upper() for item in roundup.items if item.source}
        if len(sources) == 1:
            return next(iter(sources))
        return 'MIXED'

    @staticmethod
    def _editorial_phrase(roundup: RoundupPost) -> str:
        if roundup.group_type == 'freebie':
            return 'Free picks'
        if 'discount' in roundup.group_type:
            return 'Big discounts'
        return 'Editorial picks'

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r'[^a-z0-9]+', '_', value.lower()).strip('_')
        return slug or 'roundup'

    @classmethod
    def _json_ready(cls, value: Any) -> Any:
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {str(key): cls._json_ready(item) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._json_ready(item) for item in value]
        if isinstance(value, tuple):
            return [cls._json_ready(item) for item in value]
        return value

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        ordered: list[str] = []
        for value in values:
            if value and value not in ordered:
                ordered.append(value)
        return ordered
