from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path
import re
from typing import Any

from dealbot.utils.ua import build_offer_copy
from domain.entities.offer import Offer
from domain.entities.post_artifact import PostArtifact
from domain.entities.video_manifest import VideoManifest
from infrastructure.db.repositories import QueueRecord, Repositories
from infrastructure.observability.metrics import Metrics
from infrastructure.video.manifest_writer import VideoManifestWriter


class GenerateVideoManifestsUseCase:
    def __init__(
        self,
        repositories: Repositories,
        writer: VideoManifestWriter,
        metrics: Metrics | None = None,
    ) -> None:
        self.repositories = repositories
        self.writer = writer
        self.metrics = metrics or Metrics()
        self.logger = logging.getLogger(__name__)

    def emit_offer_post(
        self,
        now_utc: datetime,
        record: QueueRecord,
        artifact: PostArtifact,
        image_path: Path | None,
    ) -> VideoManifest | None:
        run_key = now_utc.strftime('%Y%m%dT%H%M%SZ')
        try:
            manifest = self._build_offer_manifest_v2(run_key, now_utc, record, artifact, image_path)
            self._emit_manifest(manifest)
            self.metrics.inc('video_manifest.generated')
            self.metrics.inc('video_manifest.generated.offer')
            return manifest
        except Exception as exc:
            self.metrics.inc('video_manifest.generate.failed')
            self.metrics.inc('video_manifest.generate.failed.offer')
            self.logger.warning('Video manifest generation failed for %s: %s', record.offer.offer_id, exc)
            return None

    def emit_roundup_post(
        self,
        now_utc: datetime,
        record: QueueRecord,
        artifact: PostArtifact,
        image_path: Path | None,
    ) -> VideoManifest | None:
        run_key = now_utc.strftime('%Y%m%dT%H%M%SZ')
        try:
            manifest = self._build_roundup_manifest_v2(run_key, now_utc, record, artifact, image_path)
            self._emit_manifest(manifest)
            self.metrics.inc('video_manifest.generated')
            self.metrics.inc('video_manifest.generated.roundup')
            return manifest
        except Exception as exc:
            self.metrics.inc('video_manifest.generate.failed')
            self.metrics.inc('video_manifest.generate.failed.roundup')
            self.logger.warning('Roundup video manifest generation failed for %s: %s', record.offer.offer_id, exc)
            return None

    def _emit_manifest(self, manifest: VideoManifest) -> None:
        self._write_file(manifest)
        self._save_record(manifest)

    def _write_file(self, manifest: VideoManifest) -> None:
        try:
            manifest.json_path = self.writer.write(manifest)
            self.metrics.inc('video_manifest.files.success')
        except Exception as exc:
            self.metrics.inc('video_manifest.files.failed')
            self.logger.warning('Video manifest write failed for %s: %s', manifest.offer_id, exc)
            manifest.json_path = None

    def _save_record(self, manifest: VideoManifest) -> None:
        try:
            self.repositories.save_video_manifest(manifest)
            self.metrics.inc('video_manifest.db.success')
        except Exception as exc:
            self.metrics.inc('video_manifest.db.failed')
            self.logger.warning('Video manifest persistence failed for %s: %s', manifest.offer_id, exc)

    def _build_offer_manifest_v2(
        self,
        run_key: str,
        now_utc: datetime,
        record: QueueRecord,
        artifact: PostArtifact,
        image_path: Path | None,
    ) -> VideoManifest:
        offer = record.offer
        lane = record.decision_json.get('lane')
        debug = dict(record.decision_json.get('debug') or {})
        caption_debug = dict((artifact.decision_debug or {}).get('caption') or {})
        content_type = self._content_type(record.decision_json, offer)
        copy = build_offer_copy(
            offer.title,
            offer.short_description,
            offer.description,
            offer.genres,
            offer.tags,
            source=offer.source.value,
            is_free=offer.is_freebie,
            is_event=offer.is_event,
            discount_percent=offer.discount_percent,
            lane=lane,
            is_final_push=bool(record.decision_json.get('is_final_push')),
            promo_start=offer.promo_start,
            promo_end=offer.promo_end,
            now_utc=now_utc,
            long_summary_limit=240,
            short_summary_limit=110,
        )
        source_image_path = self._offer_card_image_ref(offer, artifact, image_path)
        payload = {
            'manifest_version': 2,
            'run_key': run_key,
            'created_at': now_utc.isoformat(),
            'content_id': artifact.idempotency_key,
            'content_type': content_type,
            'offer_id': offer.offer_id,
            'short_title': self._short_title(offer.title),
            'hook_line': copy['hook_line'],
            'summary_line': copy['short_summary'],
            'urgency_line': copy['urgency_line'],
            'cta_line': copy['urgency_line'],
            'caption_html': artifact.caption_html,
            'hashtags': list(artifact.hashtags),
            'asset_refs': self._offer_asset_refs(offer, artifact, source_image_path),
            'template_hint': self._template_hint(offer, lane),
            'context': {
                'lane': lane,
                'content_type': content_type,
                'offer_kind': offer.offer_kind.value,
                'source': offer.source.value,
                'store': self._store_name(offer),
                'queue_bucket': record.decision_json.get('queue_bucket'),
                'sale_event': debug.get('sale_event') or {},
                'voice_mode': caption_debug.get('voice_mode'),
                'template_id': artifact.template_id,
                'idempotency_key': artifact.idempotency_key,
                'published': True,
            },
            'render_diagnostics': dict(artifact.render_diagnostics or {}),
            'caption_debug': caption_debug,
            'source_artifact': {
                'image_path': source_image_path,
                'assets_used': list(artifact.assets_used),
            },
            'voice_facts': self._offer_voice_facts(offer),
        }
        return VideoManifest(
            offer_id=offer.offer_id,
            run_key=run_key,
            created_at=now_utc,
            payload_json=payload,
        )

    def _build_roundup_manifest_v2(
        self,
        run_key: str,
        now_utc: datetime,
        record: QueueRecord,
        artifact: PostArtifact,
        image_path: Path | None,
    ) -> VideoManifest:
        decision = dict(record.decision_json or {})
        caption_html = str(decision.get('roundup_caption_html') or artifact.caption_html or '').strip()
        roundup_items = self._roundup_items(decision)
        render_diagnostics = dict(artifact.render_diagnostics or {})
        title = str(record.offer.title or '').strip() or 'Roundup'
        hook_line = self._roundup_hook_line(decision, title)
        summary_line = self._roundup_summary_line(roundup_items, title)
        urgency_line = self._roundup_urgency_line(decision)
        payload = {
            'manifest_version': 2,
            'run_key': run_key,
            'created_at': now_utc.isoformat(),
            'content_id': artifact.idempotency_key,
            'content_type': 'roundup',
            'offer_id': record.offer.offer_id,
            'short_title': self._short_title(title),
            'hook_line': hook_line,
            'summary_line': summary_line,
            'urgency_line': urgency_line,
            'cta_line': urgency_line,
            'caption_html': caption_html,
            'hashtags': list(artifact.hashtags),
            'asset_refs': self._roundup_asset_refs(record, render_diagnostics, image_path),
            'template_hint': 'deal-spotlight',
            'context': {
                'lane': decision.get('lane'),
                'content_type': 'roundup',
                'offer_kind': getattr(record.offer.offer_kind, 'value', record.offer.offer_kind),
                'source': getattr(record.offer.source, 'value', record.offer.source),
                'store': self._store_name(record.offer),
                'queue_bucket': decision.get('queue_bucket'),
                'voice_mode': 'direct',
                'template_id': artifact.template_id,
                'idempotency_key': artifact.idempotency_key,
                'published': True,
                'roundup_id': decision.get('roundup_id'),
                'roundup_run_key': decision.get('roundup_run_key'),
                'video_template_intent': 'roundup_digest',
            },
            'render_diagnostics': render_diagnostics,
            'caption_debug': {
                'voice_mode': 'direct',
                'source': 'roundup_publish_artifact',
            },
            'source_artifact': {
                'image_path': str(image_path) if image_path else None,
                'assets_used': list(artifact.assets_used),
            },
            'roundup_items': roundup_items,
            'voice_facts': self._roundup_voice_facts(title, roundup_items, decision),
        }
        return VideoManifest(
            offer_id=record.offer.offer_id,
            run_key=run_key,
            created_at=now_utc,
            payload_json=payload,
        )

    @staticmethod
    def _short_title(title: str, limit: int = 56) -> str:
        cleaned = re.sub(r'\s+', ' ', (title or '').strip())
        if len(cleaned) <= limit:
            return cleaned
        truncated = cleaned[: limit - 3].rstrip(' ,.;:-')
        return f'{truncated}...'

    def _offer_asset_refs(self, offer: Offer, artifact: PostArtifact, card_image: str | None) -> dict[str, str]:
        lead_artwork = self._string_or_none(
            artifact.render_diagnostics.get('selected_asset_path')
            or artifact.render_diagnostics.get('hero_asset_used')
            or artifact.render_diagnostics.get('asset_used')
            or offer.primary_asset_url
        )
        game_image = offer.primary_asset_url or card_image
        background = offer.assets.screenshot or offer.assets.hero or offer.assets.header or offer.assets.fallback or card_image
        refs: dict[str, str] = {}
        if card_image:
            refs['card_image'] = card_image
        if game_image:
            refs['game_image'] = game_image
        if background:
            refs['background'] = background
        if lead_artwork:
            refs['lead_artwork'] = lead_artwork
        return refs

    def _roundup_asset_refs(
        self,
        record: QueueRecord,
        render_diagnostics: dict[str, Any],
        image_path: Path | None,
    ) -> dict[str, str]:
        lead_artwork = self._string_or_none(
            render_diagnostics.get('selected_asset_path')
            or render_diagnostics.get('hero_asset_used')
            or render_diagnostics.get('asset_used')
        )
        card_image = str(image_path) if image_path else None
        fallback_visual = lead_artwork or card_image or record.offer.primary_asset_url
        refs: dict[str, str] = {}
        if card_image:
            refs['card_image'] = card_image
        if fallback_visual:
            refs['game_image'] = fallback_visual
            refs['background'] = fallback_visual
        if lead_artwork:
            refs['lead_artwork'] = lead_artwork
        return refs


    def _offer_card_image_ref(self, offer: Offer, artifact: PostArtifact, image_path: Path | None) -> str | None:
        if image_path is not None:
            return str(image_path)
        if not offer.is_event:
            return None
        return self._artifact_local_image_ref(artifact)

    def _artifact_local_image_ref(self, artifact: PostArtifact) -> str | None:
        diagnostics = artifact.render_diagnostics or {}
        candidates: list[Any] = [
            diagnostics.get('card_image_path'),
            diagnostics.get('image_path'),
            diagnostics.get('rendered_card_path'),
            *list(artifact.assets_used or []),
        ]
        for candidate in candidates:
            value = self._string_or_none(candidate)
            if value is None:
                continue
            path = Path(value)
            if not path.is_absolute() or not path.exists() or not path.is_file():
                continue
            if path.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}:
                continue
            return str(path)
        return None

    @staticmethod
    def _template_hint(offer: Offer, lane: str | None) -> str:
        if offer.is_event:
            return 'event-countdown'
        if offer.is_freebie:
            return 'freebie-flash'
        if lane == 'final_push':
            return 'deadline-push'
        if lane == 'game_of_the_day':
            return 'daily-spotlight'
        return 'deal-spotlight'

    @staticmethod
    def _store_name(offer: Offer) -> str:
        if offer.source.value == 'epic':
            return 'Epic Games Store'
        return 'Steam'

    @staticmethod
    def _content_type(decision_json: dict[str, Any], offer: Offer) -> str:
        declared = str(decision_json.get('content_type') or '').strip().lower()
        if declared in {'discount', 'freebie', 'event', 'roundup'}:
            return declared
        if offer.is_event:
            return 'event'
        if offer.is_freebie:
            return 'freebie'
        return 'discount'

    @staticmethod
    def _roundup_hook_line(decision: dict[str, Any], title: str) -> str:
        intro = str(decision.get('roundup_intro') or '').strip()
        if intro:
            return intro
        return title

    @classmethod
    def _roundup_summary_line(cls, roundup_items: list[dict[str, Any]], title: str) -> str:
        titles = [str(item.get('title') or '').strip() for item in roundup_items if str(item.get('title') or '').strip()]
        if titles:
            return cls._short_title(' · '.join(titles[:3]), limit=110)
        return cls._short_title(title, limit=110)

    @staticmethod
    def _roundup_urgency_line(decision: dict[str, Any]) -> str:
        closing = str(decision.get('roundup_closing_cta') or '').strip()
        if closing:
            return closing
        return 'Переглянь добірку, поки ці пропозиції ще активні.'

    @staticmethod
    def _roundup_items(decision: dict[str, Any]) -> list[dict[str, Any]]:
        snapshots = decision.get('roundup_item_offers') or []
        if not isinstance(snapshots, list):
            return []
        items: list[dict[str, Any]] = []
        for snapshot in snapshots:
            if not isinstance(snapshot, dict):
                continue
            items.append(
                {
                    'offer_id': snapshot.get('offer_id'),
                    'title': snapshot.get('title'),
                    'source': snapshot.get('source'),
                    'offer_kind': snapshot.get('offer_kind'),
                    'store_url': snapshot.get('store_url'),
                    'discount_percent': snapshot.get('discount_percent'),
                    'price_after_minor': snapshot.get('price_after_minor'),
                }
            )
        return items

    @staticmethod
    def _offer_voice_facts(offer: Offer) -> dict[str, Any]:
        return {
            'title': offer.title,
            'store_url': offer.store_url,
            'price_before_minor': offer.price_before_minor,
            'price_after_minor': offer.price_after_minor,
            'currency': offer.currency,
            'discount_percent': offer.discount_percent,
            'promo_start': offer.promo_start.isoformat() if offer.promo_start else None,
            'promo_end': offer.promo_end.isoformat() if offer.promo_end else None,
            'review_score': offer.review_score,
            'review_count': offer.review_count,
            'achievements_count': offer.achievements_count,
            'has_trading_cards': offer.has_trading_cards,
            'tags': list(offer.tags),
            'genres': list(offer.genres),
            'description': offer.description,
            'short_description': offer.short_description,
            'free_access_type': GenerateVideoManifestsUseCase._freebie_access_type(offer),
        }

    @staticmethod
    def _roundup_voice_facts(
        title: str,
        roundup_items: list[dict[str, Any]],
        decision: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            'roundup_title': title,
            'roundup_id': decision.get('roundup_id'),
            'roundup_run_key': decision.get('roundup_run_key'),
            'item_count': len(roundup_items),
            'group_type': decision.get('group_type'),
            'theme_label': decision.get('theme_label'),
        }

    @staticmethod
    def _freebie_access_type(offer: Offer) -> str | None:
        if not offer.is_freebie:
            return None
        if offer.source.value == 'epic':
            return 'keep_forever'

        explicit = str(offer.metadata.get('free_access_type') or '').strip().lower()
        if explicit in {'temporary', 'free_weekend', 'free_play', 'trial'}:
            return 'temporary_access'

        normalized_text = ' '.join(
            str(value or '').strip().lower()
            for value in (
                offer.title,
                offer.short_description,
                offer.description,
            )
        )
        if any(token in normalized_text for token in ('free weekend', 'free play', '????????', 'trial')):
            return 'temporary_access'
        return 'keep_forever'

    @staticmethod
    def _string_or_none(value: Any) -> str | None:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None
