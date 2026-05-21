from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
import hashlib
import logging
from pathlib import Path
import sqlite3
from typing import Any

from dealbot.settings import AppSettings
from domain.entities.analytics_artifact import AnalyticsArtifact
from domain.entities.offer import AssetBundle, Offer, OfferKind, OfferSource
from domain.entities.post_artifact import PostArtifact
from domain.policies.content_lane_policy import ContentLanePolicy
from domain.policies.dedup_policy import DedupPolicy
from domain.policies.publish_priority_engine import PublishPriority, PublishPriorityEngine
from infrastructure.analytics.artifact_writer import AnalyticsArtifactWriter
from infrastructure.db.repositories import QueueRecord, Repositories
from infrastructure.observability.metrics import Metrics
from infrastructure.telegram.publisher import TelegramPublisher

from .controlled_reserve_release import ControlledReserveRelease
from .dry_run_render import DryRunRenderUseCase, RenderResult
from .editorial_stream_controller import EditorialAdjustment, EditorialStreamController
from .generate_video_manifests import GenerateVideoManifestsUseCase


@dataclass(slots=True)
class PublishResult:
    offer_id: str
    title: str
    lane: str
    image_path: Path | None
    message_id: int | None
    published: bool
    reason: str
    analytics: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SelectionCandidateSnapshot:
    row_id: int
    bucket: str
    lane: str
    content_family: str
    source: str
    offer_id: str
    title: str
    template_id: str | None
    score: float
    total_priority: float | None
    selected: bool = False
    eligible: bool = False
    blocker_reason: str | None = None
    blocker_detail: str | None = None
    recommended_post_mode: str | None = None
    publish_priority: dict[str, Any] = field(default_factory=dict)
    editorial_adjustment: dict[str, Any] = field(default_factory=dict)
    decision_reasons: list[str] = field(default_factory=list)
    quality_reasons: list[str] = field(default_factory=list)
    store_url: str = ''
    created_at: str | None = None

    def to_snapshot(self) -> dict[str, Any]:
        return {
            'row_id': self.row_id,
            'bucket': self.bucket,
            'lane': self.lane,
            'content_family': self.content_family,
            'source': self.source,
            'offer_id': self.offer_id,
            'title': self.title,
            'template_id': self.template_id,
            'score': self.score,
            'total_priority': self.total_priority,
            'selected': self.selected,
            'eligible': self.eligible,
            'blocker_reason': self.blocker_reason,
            'blocker_detail': self.blocker_detail,
            'recommended_post_mode': self.recommended_post_mode,
            'publish_priority': dict(self.publish_priority),
            'editorial_adjustment': dict(self.editorial_adjustment),
            'decision_reasons': list(self.decision_reasons),
            'quality_reasons': list(self.quality_reasons),
            'store_url': self.store_url,
            'created_at': self.created_at,
        }


@dataclass(slots=True)
class SelectionInspection:
    quiet_hours: bool
    allow_reserve: bool
    planned_total: int
    reserve_total: int
    visible_reserve_total: int
    eligible_candidates: list[SelectionCandidateSnapshot] = field(default_factory=list)
    blocked_candidates: list[SelectionCandidateSnapshot] = field(default_factory=list)
    selected_candidate: SelectionCandidateSnapshot | None = None
    roundup_injection: dict[str, Any] = field(default_factory=dict)
    reserve_release_reason: str | None = None
    blocker_reason: str | None = None
    blocker_detail: str | None = None

    def to_snapshot(self) -> dict[str, Any]:
        return {
            'quiet_hours': self.quiet_hours,
            'allow_reserve': self.allow_reserve,
            'planned_total': self.planned_total,
            'reserve_total': self.reserve_total,
            'visible_reserve_total': self.visible_reserve_total,
            'eligible_candidates_total': len(self.eligible_candidates),
            'blocked_candidates_total': len(self.blocked_candidates),
            'selected_candidate': self.selected_candidate.to_snapshot() if self.selected_candidate else None,
            'eligible_candidates': [candidate.to_snapshot() for candidate in self.eligible_candidates],
            'blocked_candidates': [candidate.to_snapshot() for candidate in self.blocked_candidates],
            'roundup_injection': dict(self.roundup_injection),
            'reserve_release_reason': self.reserve_release_reason,
            'blocker_reason': self.blocker_reason,
            'blocker_detail': self.blocker_detail,
        }


@dataclass(slots=True)
class SendTestTargetPreview:
    truth_ready: bool
    would_send: bool
    blocker_category: str | None
    blocker_reason: str | None
    blocker_detail: str | None
    candidate: dict[str, Any] | None = None
    offer_snapshot: dict[str, Any] = field(default_factory=dict)
    decision_snapshot: dict[str, Any] = field(default_factory=dict)
    artifact: dict[str, Any] = field(default_factory=dict)
    outbox_status: str | None = None
    outbox_message_id: int | None = None

    def to_snapshot(self) -> dict[str, Any]:
        return {
            'truth_ready': self.truth_ready,
            'would_send': self.would_send,
            'blocker_category': self.blocker_category,
            'blocker_reason': self.blocker_reason,
            'blocker_detail': self.blocker_detail,
            'candidate': dict(self.candidate or {}),
            'artifact': dict(self.artifact or {}),
            'outbox_status': self.outbox_status,
            'outbox_message_id': self.outbox_message_id,
        }


class PublishNextUseCase:
    QUIET_START = time(0, 0)
    QUIET_END = time(8, 30)
    RETRY_BACKOFF_MINUTES = 15
    ROUNDUP_LANE = 'roundup_digest'
    ROUNDUP_SPACING_POSTS = 4

    def __init__(
        self,
        settings: AppSettings,
        repositories: Repositories,
        dry_run_render: DryRunRenderUseCase,
        publisher: TelegramPublisher,
        content_lanes: ContentLanePolicy | None = None,
        dedup_policy: DedupPolicy | None = None,
        publish_priority_engine: PublishPriorityEngine | None = None,
        editorial_stream_controller: EditorialStreamController | None = None,
        controlled_reserve_release: ControlledReserveRelease | None = None,
        metrics: Metrics | None = None,
        video_manifests: GenerateVideoManifestsUseCase | None = None,
    ) -> None:
        self.settings = settings
        self.repositories = repositories
        self.dry_run_render = dry_run_render
        self.publisher = publisher
        self.content_lanes = content_lanes or ContentLanePolicy()
        self.dedup_policy = dedup_policy or DedupPolicy()
        self.publish_priority_engine = publish_priority_engine or PublishPriorityEngine(self.content_lanes)
        self.editorial_stream_controller = editorial_stream_controller or EditorialStreamController()
        self.controlled_reserve_release = controlled_reserve_release or ControlledReserveRelease()
        self.metrics = metrics or Metrics()
        self.video_manifests = video_manifests
        self.card_qa_writer = AnalyticsArtifactWriter(self.settings.analytics_output_dir)
        self.logger = logging.getLogger(__name__)

    def inspect_selection(self, now_utc: datetime, now_local: datetime) -> SelectionInspection:
        quiet_hours = self._is_quiet_hours(now_local)
        allow_reserve = not quiet_hours
        planned_candidates = list(self.repositories.list_queue('planned'))
        reserve_all = list(self.repositories.list_queue('reserve'))
        blocked_candidates: list[SelectionCandidateSnapshot] = []
        reserve_candidates = list(reserve_all) if allow_reserve else []
        roundup_injection: dict[str, Any]
        roundup_candidate: QueueRecord | None = None
        visible_roundup_candidate: QueueRecord | None = None
        visible_reserve = list(reserve_candidates)
        release_reason: str | None = None

        if not allow_reserve and reserve_all:
            roundup_injection = {
                'attempted': True,
                'status': 'held',
                'reason': 'quiet_hours_reserve_hidden',
                'release_status': 'quiet_hours_hidden',
                'queue_snapshot_at': self._queue_window_key(reserve_all),
            }
            for record in reserve_all:
                blocked_candidates.append(
                    self._candidate_snapshot(
                        record,
                        blocker_reason='quiet_hours_reserve_hidden',
                        blocker_detail='Reserve rows are hidden during quiet hours.',
                    )
                )
        else:
            recent_stream = self.repositories.list_recent_published_stream(limit=self.editorial_stream_controller.RECENT_WINDOW)
            roundup_candidate, roundup_injection = self._build_roundup_candidate(reserve_candidates, recent_stream)
            visible_roundup_candidate = roundup_candidate
            try:
                release_decision = self.controlled_reserve_release.release(
                    planned_candidates=planned_candidates,
                    reserve_candidates=reserve_candidates,
                    roundup_candidate=roundup_candidate,
                    recent_stream=recent_stream,
                )
                visible_reserve = list(release_decision.visible_reserve_candidates)
                release_reason = release_decision.reason
                original_roundup_candidate = roundup_candidate
                visible_roundup_candidate = release_decision.visible_roundup_candidate
                if roundup_injection and roundup_injection.get('status') == 'candidate_ready':
                    if original_roundup_candidate is not None and visible_roundup_candidate is None:
                        roundup_injection['status'] = 'held'
                        roundup_injection['reason'] = 'controlled_reserve_release_held'
                        roundup_injection['release_status'] = 'held'
                    elif visible_roundup_candidate is not None:
                        roundup_injection['release_status'] = 'visible'

                visible_reserve_ids = {record.row_id for record in visible_reserve}
                for record in reserve_candidates:
                    if record.row_id not in visible_reserve_ids:
                        blocked_candidates.append(
                            self._candidate_snapshot(
                                record,
                                blocker_reason='controlled_reserve_release_held',
                                blocker_detail=release_decision.reason,
                            )
                        )
                if original_roundup_candidate is not None and visible_roundup_candidate is None:
                    blocked_candidates.append(
                        self._candidate_snapshot(
                            original_roundup_candidate,
                            blocker_reason='controlled_reserve_release_held',
                            blocker_detail=release_decision.reason,
                        )
                    )
            except Exception as exc:
                self.metrics.inc('publish.controlled_reserve_release.failed')
                self.logger.warning('Controlled reserve release failed: %s', exc)
                release_reason = 'release_failed'
                roundup_injection = dict(roundup_injection or {})
                roundup_injection['release_status'] = 'failed'
                roundup_injection['reason'] = 'controlled_reserve_release_failed'

        candidates = list(planned_candidates)
        candidates.extend(visible_reserve)
        if visible_roundup_candidate is not None:
            candidates.append(visible_roundup_candidate)

        lane_usage_cache: dict[str, int] = {}
        rankable: list[tuple[QueueRecord, PublishPriority]] = []
        for record in candidates:
            blocker_reason, blocker_detail = self._published_candidate_blocker(record, now_utc)
            if blocker_reason is not None:
                blocked_candidates.append(
                    self._candidate_snapshot(
                        record,
                        blocker_reason=blocker_reason,
                        blocker_detail=blocker_detail,
                    )
                )
                continue
            lane = str(record.decision_json.get('lane') or record.lane)
            lane_usage = lane_usage_cache.setdefault(lane, self.repositories.get_daily_lane_count(now_local.date().isoformat(), lane))
            manual_force_override = bool(record.decision_json.get('manual_force_override'))
            if self.content_lanes.quota_blocked(lane, {lane: lane_usage}, manual_force_override=manual_force_override):
                blocked_candidates.append(
                    self._candidate_snapshot(
                        record,
                        blocker_reason='daily_lane_cap_reached',
                        blocker_detail=f'lane={lane} published_today={lane_usage}',
                    )
                )
                continue
            priority = self.publish_priority_engine.evaluate(
                offer=record.offer,
                lane=lane,
                bucket=record.bucket,
                decision_score=float(record.decision_json.get('score') or record.score or 0.0),
                must_ship=bool(record.decision_json.get('must_ship')),
                manual_force_override=manual_force_override,
                lane_published_today=lane_usage,
                now_utc=now_utc,
            )
            rankable.append((record, priority))

        eligible_candidates: list[SelectionCandidateSnapshot] = []
        selected_candidate: SelectionCandidateSnapshot | None = None
        if rankable:
            recent_stream = self.repositories.list_recent_published_stream(limit=self.editorial_stream_controller.RECENT_WINDOW)
            eligible_records = [record for record, _ in rankable]
            ranked: list[tuple[tuple[float, int, float, int], SelectionCandidateSnapshot]] = []
            for record, priority in rankable:
                editorial_adjustment = self.editorial_stream_controller.score_candidate(record, eligible_records, recent_stream)
                total_priority = float(priority.total) + float(editorial_adjustment.total_delta if editorial_adjustment else 0.0)
                snapshot = self._candidate_snapshot(
                    record,
                    total_priority=round(total_priority, 2),
                    eligible=True,
                    publish_priority=priority.to_snapshot(),
                    editorial_adjustment=editorial_adjustment.to_snapshot(base_total=priority.total),
                )
                ranked.append((self._priority_sort_key(record, priority, editorial_adjustment), snapshot))
            ranked.sort(key=lambda item: item[0], reverse=True)
            eligible_candidates = [snapshot for _, snapshot in ranked]
            if eligible_candidates:
                eligible_candidates[0].selected = True
                selected_candidate = eligible_candidates[0]

        blocker_reason, blocker_detail = self._selection_blocker(
            planned_total=len(planned_candidates),
            reserve_total=len(reserve_all),
            allow_reserve=allow_reserve,
            blocked_candidates=blocked_candidates,
            roundup_injection=roundup_injection,
        )
        if selected_candidate is not None:
            blocker_reason = None
            blocker_detail = None

        return SelectionInspection(
            quiet_hours=quiet_hours,
            allow_reserve=allow_reserve,
            planned_total=len(planned_candidates),
            reserve_total=len(reserve_all),
            visible_reserve_total=len(visible_reserve),
            eligible_candidates=eligible_candidates,
            blocked_candidates=blocked_candidates,
            selected_candidate=selected_candidate,
            roundup_injection=dict(roundup_injection or {}),
            reserve_release_reason=release_reason,
            blocker_reason=blocker_reason,
            blocker_detail=blocker_detail,
        )

    async def preview_send_test_target(self, now_utc: datetime, now_local: datetime) -> SendTestTargetPreview:
        inspection = self.inspect_selection(now_utc, now_local)
        if inspection.selected_candidate is None:
            return SendTestTargetPreview(
                truth_ready=False,
                would_send=False,
                blocker_category=self._blocker_category(inspection.blocker_reason),
                blocker_reason=inspection.blocker_reason,
                blocker_detail=inspection.blocker_detail,
            )

        record, _, _, _ = self._select_record(now_utc, now_local)
        if record is None:
            return SendTestTargetPreview(
                truth_ready=False,
                would_send=False,
                blocker_category=self._blocker_category(inspection.blocker_reason),
                blocker_reason=inspection.blocker_reason,
                blocker_detail=inspection.blocker_detail,
                candidate=inspection.selected_candidate.to_snapshot(),
            )

        if self._is_roundup_candidate(record):
            image_path = Path(str(record.decision_json.get('roundup_card_asset_path') or '').strip())
            artifact = self._roundup_post_artifact(record, image_path)
            outbox = self.repositories.get_outbox_record(artifact.idempotency_key)
            blocker_reason = None
            blocker_detail = None
            would_send = True
            if outbox is not None and outbox.status in {'published', 'sent'}:
                would_send = False
                blocker_reason = 'already_published' if outbox.status == 'published' else 'already_sent_finalize_only'
                blocker_detail = f'outbox_status={outbox.status}'
            return SendTestTargetPreview(
                truth_ready=would_send,
                would_send=would_send,
                blocker_category=self._blocker_category(blocker_reason),
                blocker_reason=blocker_reason,
                blocker_detail=blocker_detail,
                candidate=inspection.selected_candidate.to_snapshot(),
                offer_snapshot=record.offer.to_snapshot(),
                decision_snapshot=dict(record.decision_json),
                artifact=self._artifact_preview(artifact, image_path),
                outbox_status=outbox.status if outbox is not None else None,
                outbox_message_id=outbox.telegram_message_id if outbox is not None else None,
            )

        try:
            render_result = await self.dry_run_render.execute(record.offer, record.decision_json)
        except Exception as exc:
            return SendTestTargetPreview(
                truth_ready=False,
                would_send=False,
                blocker_category='asset_localization',
                blocker_reason='render_failed',
                blocker_detail=self._failure_detail(exc),
                candidate=inspection.selected_candidate.to_snapshot(),
                offer_snapshot=record.offer.to_snapshot(),
                decision_snapshot=dict(record.decision_json),
            )

        artifact = render_result.artifact
        outbox = self.repositories.get_outbox_record(artifact.idempotency_key)
        blocker_reason = None
        blocker_detail = None
        would_send = True
        if outbox is not None and outbox.status in {'published', 'sent'}:
            would_send = False
            blocker_reason = 'already_published' if outbox.status == 'published' else 'already_sent_finalize_only'
            blocker_detail = f'outbox_status={outbox.status}'
        return SendTestTargetPreview(
            truth_ready=would_send,
            would_send=would_send,
            blocker_category=self._blocker_category(blocker_reason),
            blocker_reason=blocker_reason,
            blocker_detail=blocker_detail,
            candidate=inspection.selected_candidate.to_snapshot(),
            offer_snapshot=record.offer.to_snapshot(),
            decision_snapshot=dict(record.decision_json),
            artifact=self._artifact_preview(artifact, render_result.image_path),
            outbox_status=outbox.status if outbox is not None else None,
            outbox_message_id=outbox.telegram_message_id if outbox is not None else None,
        )

    async def execute(self, now_utc: datetime, now_local: datetime, force_publish: bool = False) -> PublishResult | None:
        record, publish_priority, editorial_adjustment, roundup_injection = self._select_record(now_utc, now_local)
        if record is None:
            blocked_result = self._blocked_selection_result(now_utc, now_local)
            if blocked_result is not None:
                self.metrics.inc('publish.idempotent_skip')
                return blocked_result
            self.metrics.inc('publish.queue_empty')
            return None
        self.metrics.inc(f'publish.selected.bucket.{record.bucket}')
        self.metrics.inc(f'publish.selected.lane.{record.decision_json["lane"]}')

        if self._is_roundup_candidate(record):
            return await self._publish_roundup_candidate(
                record,
                now_utc,
                now_local,
                force_publish=force_publish,
                publish_priority=publish_priority,
                editorial_adjustment=editorial_adjustment,
                roundup_injection=roundup_injection,
            )
        return await self._publish_offer_candidate(
            record,
            now_utc,
            now_local,
            force_publish=force_publish,
            publish_priority=publish_priority,
            editorial_adjustment=editorial_adjustment,
            roundup_injection=roundup_injection,
        )

    async def _publish_offer_candidate(
        self,
        record: QueueRecord,
        now_utc: datetime,
        now_local: datetime,
        *,
        force_publish: bool,
        publish_priority: dict[str, Any] | None,
        editorial_adjustment: dict[str, Any] | None,
        roundup_injection: dict[str, Any] | None,
    ) -> PublishResult:
        try:
            render_result = await self.dry_run_render.execute(record.offer, record.decision_json)
        except Exception as exc:
            self.metrics.inc('publish.failed.render')
            self.logger.warning('Render failed for %s: %s', record.offer.offer_id, exc)
            return self._result(
                record,
                'render_failed',
                False,
                publish_priority=publish_priority,
                editorial_adjustment=editorial_adjustment,
                roundup_injection=roundup_injection,
            )

        artifact = render_result.artifact
        existing = self.repositories.get_outbox_record(artifact.idempotency_key)
        if existing and existing.status == 'published':
            self.repositories.delete_queue_item(record.row_id)
            self.metrics.inc('publish.idempotent_skip')
            return self._result(
                record,
                'already_published',
                False,
                image_path=render_result.image_path,
                message_id=existing.telegram_message_id,
                render_result=render_result,
                outbox_status=existing.status,
                publish_priority=publish_priority,
                editorial_adjustment=editorial_adjustment,
                roundup_injection=roundup_injection,
            )

        if (self.settings.operational.dry_run or self.settings.operational.freeze_publish) and not force_publish:
            reason = 'dry_run' if self.settings.operational.dry_run else 'freeze_publish'
            self.metrics.inc(f'publish.skipped.{reason}')
            return self._result(
                record,
                reason,
                False,
                image_path=render_result.image_path,
                render_result=render_result,
                publish_priority=publish_priority,
                editorial_adjustment=editorial_adjustment,
                roundup_injection=roundup_injection,
            )

        try:
            staged = self.repositories.stage_outbox_delivery(
                queue_row_id=record.row_id,
                offer=record.offer,
                decision_json=record.decision_json,
                artifact=artifact,
                image_path=render_result.image_path,
            )
        except sqlite3.Error as exc:
            self.metrics.inc('publish.failed.db_stage')
            self.logger.warning('Failed to stage outbox for %s: %s', record.offer.offer_id, exc)
            return self._result(
                record,
                'db_stage_failed',
                False,
                image_path=render_result.image_path,
                render_result=render_result,
                publish_priority=publish_priority,
                editorial_adjustment=editorial_adjustment,
                roundup_injection=roundup_injection,
            )

        if staged.status == 'published':
            self.metrics.inc('publish.idempotent_skip')
            return self._result(
                record,
                'already_published',
                False,
                image_path=render_result.image_path,
                message_id=staged.telegram_message_id,
                render_result=render_result,
                outbox_status=staged.status,
                publish_priority=publish_priority,
                editorial_adjustment=editorial_adjustment,
                roundup_injection=roundup_injection,
            )

        if staged.status == 'sent' and staged.telegram_message_id is not None:
            try:
                self.repositories.finalize_publication(
                    artifact.idempotency_key,
                    record.offer,
                    record.decision_json['lane'],
                    now_local.date().isoformat(),
                )
            except sqlite3.Error as exc:
                self.metrics.inc('publish.failed.db_finalize')
                self.logger.warning('Failed to finalize prior sent publish for %s: %s', record.offer.offer_id, exc)
                return self._result(
                    record,
                    'db_finalize_failed',
                    False,
                    image_path=render_result.image_path,
                    message_id=staged.telegram_message_id,
                    render_result=render_result,
                    outbox_status=staged.status,
                    publish_priority=publish_priority,
                    editorial_adjustment=editorial_adjustment,
                    roundup_injection=roundup_injection,
                )
            self.metrics.inc('publish.recovered.sent_finalize')
            self._emit_roundup_video_manifest(now_utc, record, artifact, image_path)
            return self._result(
                record,
                'published',
                True,
                image_path=render_result.image_path,
                message_id=staged.telegram_message_id,
                render_result=render_result,
                outbox_status='published',
                publish_priority=publish_priority,
                editorial_adjustment=editorial_adjustment,
                roundup_injection=roundup_injection,
            )

        try:
            self.repositories.mark_outbox_sending(artifact.idempotency_key)
        except sqlite3.Error as exc:
            self.metrics.inc('publish.failed.db_claim')
            self.logger.warning('Failed to claim outbox send for %s: %s', record.offer.offer_id, exc)
            return self._result(
                record,
                'db_claim_failed',
                False,
                image_path=render_result.image_path,
                render_result=render_result,
                outbox_status=staged.status,
                publish_priority=publish_priority,
                editorial_adjustment=editorial_adjustment,
                roundup_injection=roundup_injection,
            )

        try:
            message = await self.publisher.publish_photo(render_result.image_path, artifact.caption_html)
        except Exception as exc:
            try:
                self.repositories.mark_outbox_failed(
                    artifact.idempotency_key,
                    str(exc),
                    now_utc + timedelta(minutes=self.RETRY_BACKOFF_MINUTES),
                )
            except sqlite3.Error as db_exc:
                self.logger.warning('Failed to mark outbox failed for %s: %s', record.offer.offer_id, db_exc)
            self.metrics.inc('publish.failed.delivery')
            self.logger.warning('Publish delivery failed for %s: %s', record.offer.offer_id, exc)
            return self._result(
                record,
                'publish_failed',
                False,
                image_path=render_result.image_path,
                render_result=render_result,
                outbox_status='failed',
                publish_priority=publish_priority,
                editorial_adjustment=editorial_adjustment,
                roundup_injection=roundup_injection,
            )

        try:
            self.repositories.mark_outbox_sent(artifact.idempotency_key, message.message_id)
        except sqlite3.Error as exc:
            self.metrics.inc('publish.failed.db_mark_sent')
            self.logger.warning('Failed to persist sent state for %s: %s', record.offer.offer_id, exc)
            return self._result(
                record,
                'db_mark_sent_failed',
                False,
                image_path=render_result.image_path,
                message_id=message.message_id,
                render_result=render_result,
                outbox_status='sending',
                publish_priority=publish_priority,
                editorial_adjustment=editorial_adjustment,
                roundup_injection=roundup_injection,
            )

        try:
            self.repositories.finalize_publication(
                artifact.idempotency_key,
                record.offer,
                record.decision_json['lane'],
                now_local.date().isoformat(),
            )
        except sqlite3.Error as exc:
            self.metrics.inc('publish.failed.db_finalize')
            self.logger.warning('Failed to finalize publish for %s: %s', record.offer.offer_id, exc)
            return self._result(
                record,
                'db_finalize_failed',
                False,
                image_path=render_result.image_path,
                message_id=message.message_id,
                render_result=render_result,
                outbox_status='sent',
                publish_priority=publish_priority,
                editorial_adjustment=editorial_adjustment,
                roundup_injection=roundup_injection,
            )

        self.metrics.inc('publish.success')
        self.logger.info('Published %s lane=%s message_id=%s', record.offer.title, record.decision_json['lane'], message.message_id)
        self._emit_offer_video_manifest(now_utc, record, artifact, render_result.image_path)
        return self._result(
            record,
            'published',
            True,
            image_path=render_result.image_path,
            message_id=message.message_id,
            render_result=render_result,
            outbox_status='published',
            publish_priority=publish_priority,
            editorial_adjustment=editorial_adjustment,
            roundup_injection=roundup_injection,
        )

    async def _publish_roundup_candidate(
        self,
        record: QueueRecord,
        now_utc: datetime,
        now_local: datetime,
        *,
        force_publish: bool,
        publish_priority: dict[str, Any] | None,
        editorial_adjustment: dict[str, Any] | None,
        roundup_injection: dict[str, Any] | None,
    ) -> PublishResult:
        decision = record.decision_json
        caption_html = str(decision.get('roundup_caption_html') or '').strip()
        image_path_raw = str(decision.get('roundup_card_asset_path') or '').strip()
        image_path = Path(image_path_raw) if image_path_raw else None
        if not caption_html or image_path is None or not image_path.exists():
            self.metrics.inc('publish.failed.roundup_payload')
            self.logger.warning('Roundup payload invalid for %s', record.offer.offer_id)
            return self._result(
                record,
                'roundup_payload_invalid',
                False,
                image_path=image_path,
                publish_priority=publish_priority,
                editorial_adjustment=editorial_adjustment,
                roundup_injection=roundup_injection,
            )

        artifact = self._roundup_post_artifact(record, image_path)
        existing = self.repositories.get_outbox_record(artifact.idempotency_key)
        if existing and existing.status == 'published':
            self.metrics.inc('publish.idempotent_skip')
            return self._result(
                record,
                'already_published',
                False,
                image_path=image_path,
                message_id=existing.telegram_message_id,
                artifact=artifact,
                outbox_status=existing.status,
                publish_priority=publish_priority,
                editorial_adjustment=editorial_adjustment,
                roundup_injection=roundup_injection,
            )

        if (self.settings.operational.dry_run or self.settings.operational.freeze_publish) and not force_publish:
            reason = 'dry_run' if self.settings.operational.dry_run else 'freeze_publish'
            self.metrics.inc(f'publish.skipped.{reason}')
            return self._result(
                record,
                reason,
                False,
                image_path=image_path,
                artifact=artifact,
                publish_priority=publish_priority,
                editorial_adjustment=editorial_adjustment,
                roundup_injection=roundup_injection,
            )

        queue_row_ids = [int(row_id) for row_id in decision.get('roundup_queue_row_ids') or [] if int(row_id) > 0]
        try:
            staged = self.repositories.stage_roundup_outbox_delivery(
                queue_row_ids=queue_row_ids,
                offer=record.offer,
                decision_json=decision,
                artifact=artifact,
                image_path=image_path,
            )
        except sqlite3.Error as exc:
            self.metrics.inc('publish.failed.db_stage')
            self.logger.warning('Failed to stage roundup outbox for %s: %s', record.offer.offer_id, exc)
            return self._result(
                record,
                'db_stage_failed',
                False,
                image_path=image_path,
                artifact=artifact,
                publish_priority=publish_priority,
                editorial_adjustment=editorial_adjustment,
                roundup_injection=roundup_injection,
            )

        if staged.status == 'published':
            self.metrics.inc('publish.idempotent_skip')
            return self._result(
                record,
                'already_published',
                False,
                image_path=image_path,
                message_id=staged.telegram_message_id,
                artifact=artifact,
                outbox_status=staged.status,
                publish_priority=publish_priority,
                editorial_adjustment=editorial_adjustment,
                roundup_injection=roundup_injection,
            )

        if staged.status == 'sent' and staged.telegram_message_id is not None:
            try:
                self.repositories.finalize_publication(
                    artifact.idempotency_key,
                    record.offer,
                    record.decision_json['lane'],
                    now_local.date().isoformat(),
                )
            except sqlite3.Error as exc:
                self.metrics.inc('publish.failed.db_finalize')
                self.logger.warning('Failed to finalize prior roundup publish for %s: %s', record.offer.offer_id, exc)
                return self._result(
                    record,
                    'db_finalize_failed',
                    False,
                    image_path=image_path,
                    message_id=staged.telegram_message_id,
                    artifact=artifact,
                    outbox_status=staged.status,
                    publish_priority=publish_priority,
                    editorial_adjustment=editorial_adjustment,
                    roundup_injection=roundup_injection,
                )
            self.metrics.inc('publish.recovered.sent_finalize')
            self._emit_roundup_video_manifest(now_utc, record, artifact, image_path)
            return self._result(
                record,
                'published',
                True,
                image_path=image_path,
                message_id=staged.telegram_message_id,
                artifact=artifact,
                outbox_status='published',
                publish_priority=publish_priority,
                editorial_adjustment=editorial_adjustment,
                roundup_injection=roundup_injection,
            )

        try:
            self.repositories.mark_outbox_sending(artifact.idempotency_key)
        except sqlite3.Error as exc:
            self.metrics.inc('publish.failed.db_claim')
            self.logger.warning('Failed to claim roundup outbox send for %s: %s', record.offer.offer_id, exc)
            return self._result(
                record,
                'db_claim_failed',
                False,
                image_path=image_path,
                artifact=artifact,
                outbox_status=staged.status,
                publish_priority=publish_priority,
                editorial_adjustment=editorial_adjustment,
                roundup_injection=roundup_injection,
            )

        try:
            message = await self.publisher.publish_photo(image_path, artifact.caption_html)
        except Exception as exc:
            try:
                self.repositories.mark_outbox_failed(
                    artifact.idempotency_key,
                    str(exc),
                    now_utc + timedelta(minutes=self.RETRY_BACKOFF_MINUTES),
                )
            except sqlite3.Error as db_exc:
                self.logger.warning('Failed to mark roundup outbox failed for %s: %s', record.offer.offer_id, db_exc)
            self.metrics.inc('publish.failed.delivery')
            self.logger.warning('Roundup delivery failed for %s: %s', record.offer.offer_id, exc)
            return self._result(
                record,
                'publish_failed',
                False,
                image_path=image_path,
                artifact=artifact,
                outbox_status='failed',
                publish_priority=publish_priority,
                editorial_adjustment=editorial_adjustment,
                roundup_injection=roundup_injection,
            )

        try:
            self.repositories.mark_outbox_sent(artifact.idempotency_key, message.message_id)
        except sqlite3.Error as exc:
            self.metrics.inc('publish.failed.db_mark_sent')
            self.logger.warning('Failed to persist roundup sent state for %s: %s', record.offer.offer_id, exc)
            return self._result(
                record,
                'db_mark_sent_failed',
                False,
                image_path=image_path,
                message_id=message.message_id,
                artifact=artifact,
                outbox_status='sending',
                publish_priority=publish_priority,
                editorial_adjustment=editorial_adjustment,
                roundup_injection=roundup_injection,
            )

        try:
            self.repositories.finalize_publication(
                artifact.idempotency_key,
                record.offer,
                record.decision_json['lane'],
                now_local.date().isoformat(),
            )
        except sqlite3.Error as exc:
            self.metrics.inc('publish.failed.db_finalize')
            self.logger.warning('Failed to finalize roundup publish for %s: %s', record.offer.offer_id, exc)
            return self._result(
                record,
                'db_finalize_failed',
                False,
                image_path=image_path,
                message_id=message.message_id,
                artifact=artifact,
                outbox_status='sent',
                publish_priority=publish_priority,
                editorial_adjustment=editorial_adjustment,
                roundup_injection=roundup_injection,
            )

        self.metrics.inc('publish.success')
        self.logger.info('Published roundup %s lane=%s message_id=%s', record.offer.title, record.decision_json['lane'], message.message_id)
        self._emit_roundup_video_manifest(now_utc, record, artifact, image_path)
        return self._result(
            record,
            'published',
            True,
            image_path=image_path,
            message_id=message.message_id,
            artifact=artifact,
            outbox_status='published',
            publish_priority=publish_priority,
            editorial_adjustment=editorial_adjustment,
            roundup_injection=roundup_injection,
        )

    def _emit_offer_video_manifest(
        self,
        now_utc: datetime,
        record: QueueRecord,
        artifact: PostArtifact,
        image_path: Path | None,
    ) -> None:
        if self.video_manifests is None:
            return
        self.video_manifests.emit_offer_post(now_utc, record, artifact, image_path)

    def _emit_roundup_video_manifest(
        self,
        now_utc: datetime,
        record: QueueRecord,
        artifact: PostArtifact,
        image_path: Path | None,
    ) -> None:
        if self.video_manifests is None:
            return
        self.video_manifests.emit_roundup_post(now_utc, record, artifact, image_path)


    def _result(
        self,
        record: QueueRecord,
        reason: str,
        published: bool,
        image_path: Path | None = None,
        message_id: int | None = None,
        render_result: RenderResult | None = None,
        artifact: PostArtifact | None = None,
        outbox_status: str | None = None,
        publish_priority: dict[str, Any] | None = None,
        editorial_adjustment: dict[str, Any] | None = None,
        roundup_injection: dict[str, Any] | None = None,
        failure_detail: str | None = None,
    ) -> PublishResult:
        analytics = self._analytics_snapshot(
            record,
            reason,
            published,
            image_path,
            message_id,
            render_result,
            artifact,
            outbox_status,
            publish_priority,
            editorial_adjustment,
            roundup_injection,
            failure_detail,
        )
        qa_summary = self._emit_card_qa_summary(
            record,
            reason,
            published,
            image_path,
            render_result,
            artifact,
        )
        if qa_summary:
            analytics['render']['card_qa_summary'] = qa_summary
        return PublishResult(
            offer_id=record.offer.offer_id,
            title=record.offer.title,
            lane=record.decision_json['lane'],
            image_path=image_path,
            message_id=message_id,
            published=published,
            reason=reason,
            analytics=analytics,
        )

    def _analytics_snapshot(
        self,
        record: QueueRecord,
        reason: str,
        published: bool,
        image_path: Path | None,
        message_id: int | None,
        render_result: RenderResult | None,
        artifact: PostArtifact | None,
        outbox_status: str | None,
        publish_priority: dict[str, Any] | None,
        editorial_adjustment: dict[str, Any] | None,
        roundup_injection: dict[str, Any] | None,
        failure_detail: str | None,
    ) -> dict[str, Any]:
        debug = dict(record.decision_json.get('debug') or {})
        selection = {
            'row_id': record.row_id,
            'lane': record.decision_json.get('lane'),
            'content_family': self._content_family(record),
            'store_url': record.offer.store_url,
            'queue_bucket': record.decision_json.get('queue_bucket'),
            'template_id': record.decision_json.get('template_id'),
            'score': record.decision_json.get('score'),
            'decision_reasons': list(record.decision_json.get('decision_reasons') or []),
            'quality_reasons': list(record.decision_json.get('quality_reasons') or []),
            'dedup_reason': record.decision_json.get('dedup_reason'),
            'event_sale_influence': debug.get('sale_event') or {},
            'diversity_constraints': list(debug.get('diversity_constraints') or []),
            'manual_override': {
                'forced': bool(record.decision_json.get('manual_force_override')),
                'reasons': list(debug.get('manual_control_reasons') or []),
            },
            'selection_outcome': record.decision_json.get('selection_outcome'),
            'recommended_post_mode': record.decision_json.get('recommended_post_mode'),
            'publish_priority': publish_priority or {},
            'editorial_adjustment': editorial_adjustment or {},
            'roundup_injection': roundup_injection or {},
        }
        render = {}
        effective_artifact = render_result.artifact if render_result is not None else artifact
        if effective_artifact is not None:
            render = {
                'image_path': str(image_path) if image_path else None,
                'template_id': effective_artifact.template_id,
                'assets_used': list(effective_artifact.assets_used),
                'caption_hash': effective_artifact.caption_hash,
                'image_hash': effective_artifact.image_hash,
                'render_diagnostics': dict(effective_artifact.render_diagnostics or {}),
                'caption_debug': dict((effective_artifact.decision_debug or {}).get('caption') or {}),
            }
        return {
            'selection': selection,
            'render': render,
            'publish_outcome': {
                'published': published,
                'reason': reason,
                'message_id': message_id,
                'outbox_status': outbox_status,
                'failure_detail': failure_detail,
            },
        }

    def _emit_card_qa_summary(
        self,
        record: QueueRecord,
        reason: str,
        published: bool,
        image_path: Path | None,
        render_result: RenderResult | None,
        artifact: PostArtifact | None,
    ) -> dict[str, Any] | None:
        effective_artifact = render_result.artifact if render_result is not None else artifact
        if effective_artifact is None:
            return None

        try:
            recent_cards = [
                self._normalize_published_card_snapshot(card)
                for card in self.repositories.list_recent_published_card_snapshots(limit=8)
            ]
            if not published:
                current_card = self._card_qa_snapshot_from_artifact(
                    record,
                    effective_artifact,
                    image_path,
                    published_at=None,
                    selected=True,
                )
                window_cards = [current_card]
                window_cards.extend(recent_cards[:7])
            else:
                window_cards = recent_cards[:8]
                if not window_cards:
                    window_cards = [
                        self._card_qa_snapshot_from_artifact(
                            record,
                            effective_artifact,
                            image_path,
                            published_at=None,
                            selected=True,
                        )
                    ]

            if not window_cards:
                return None

            summary = self._card_qa_summary_payload(record, effective_artifact, reason, published, window_cards)
            now_utc = datetime.utcnow()
            artifact_record = AnalyticsArtifact(
                artifact_type='card_qa_summary',
                subject_id=record.offer.offer_id,
                run_key=now_utc.strftime('%Y%m%dT%H%M%SZ'),
                created_at=now_utc,
                payload_json=summary,
                summary_rows=window_cards,
            )
            artifact_record.json_path, artifact_record.csv_path = self.card_qa_writer.write(artifact_record)
            self.repositories.save_analytics_artifact(artifact_record)
            self.metrics.inc('card.qa_summary.generated')
            return {
                'artifact_type': artifact_record.artifact_type,
                'json_path': str(artifact_record.json_path) if artifact_record.json_path else None,
                'csv_path': str(artifact_record.csv_path) if artifact_record.csv_path else None,
                'card_type_mix': dict(summary.get('card_type_mix') or {}),
                'renderer_fallback_count': int(summary.get('renderer_fallback_count') or 0),
                'hero_fallback_count': int(summary.get('hero_fallback_count') or 0),
                'placeholder_artwork_count': int(summary.get('placeholder_artwork_count') or 0),
                'leading_card_family_streak': dict(summary.get('leading_card_family_streak') or {}),
            }
        except Exception as exc:
            self.metrics.inc('card.qa_summary.failed')
            self.logger.warning('Card QA summary emission failed for %s: %s', record.offer.offer_id, exc)
            return None

    def _card_qa_summary_payload(
        self,
        record: QueueRecord,
        artifact: PostArtifact,
        reason: str,
        published: bool,
        window_cards: list[dict[str, Any]],
    ) -> dict[str, Any]:
        card_type_mix = Counter(str(card.get('card_family') or 'UNKNOWN') for card in window_cards)
        template_mix = Counter(str(card.get('template_id') or 'unknown') for card in window_cards)
        renderer_fallback_count = sum(1 for card in window_cards if card.get('renderer_fallback_used'))
        hero_fallback_count = sum(1 for card in window_cards if card.get('hero_fallback_used'))
        placeholder_artwork_count = sum(1 for card in window_cards if card.get('placeholder_artwork_used'))
        leading_card_family_streak = self._leading_streak(window_cards, 'card_family')
        leading_template_streak = self._leading_streak(window_cards, 'template_id')
        return {
            'qa_version': 1,
            'created_at': datetime.utcnow().isoformat(),
            'selected_offer_id': record.offer.offer_id,
            'selected_title': record.offer.title,
            'selected_template_id': artifact.template_id,
            'selected_lane': str(record.decision_json.get('lane') or ''),
            'published': published,
            'publish_reason': reason,
            'window_size': len(window_cards),
            'card_type_mix': dict(card_type_mix),
            'template_mix': dict(template_mix),
            'renderer_fallback_count': renderer_fallback_count,
            'hero_fallback_count': hero_fallback_count,
            'placeholder_artwork_count': placeholder_artwork_count,
            'leading_card_family_streak': leading_card_family_streak,
            'leading_template_streak': leading_template_streak,
        }

    def _card_qa_snapshot_from_artifact(
        self,
        record: QueueRecord,
        artifact: PostArtifact,
        image_path: Path | None,
        *,
        published_at: str | None,
        selected: bool,
    ) -> dict[str, Any]:
        diagnostics = dict(artifact.render_diagnostics or {})
        template_id = str(artifact.template_id or record.decision_json.get('template_id') or '')
        return {
            'position': 1,
            'offer_id': record.offer.offer_id,
            'title': record.offer.title,
            'template_id': template_id,
            'card_family': self._card_family(template_id, diagnostics),
            'published_at': published_at,
            'selected': selected,
            'image_path': str(image_path) if image_path else None,
            'renderer_fallback_used': bool(diagnostics.get('renderer_fallback_used')),
            'hero_fallback_used': bool(diagnostics.get('hero_fallback_used')),
            'placeholder_artwork_used': bool(diagnostics.get('used_placeholder_artwork'))
            or 'fallback_artwork' in list(diagnostics.get('render_warnings') or []),
            'render_warnings': list(diagnostics.get('render_warnings') or []),
        }

    def _normalize_published_card_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        diagnostics = dict(payload.get('render_diagnostics') or {})
        template_id = str(payload.get('template_id') or '')
        return {
            'position': 1,
            'offer_id': str(payload.get('offer_id') or ''),
            'title': str(payload.get('title') or ''),
            'template_id': template_id,
            'card_family': self._card_family(template_id, diagnostics),
            'published_at': payload.get('published_at'),
            'selected': False,
            'image_path': None,
            'renderer_fallback_used': bool(diagnostics.get('renderer_fallback_used')),
            'hero_fallback_used': bool(diagnostics.get('hero_fallback_used')),
            'placeholder_artwork_used': bool(diagnostics.get('used_placeholder_artwork'))
            or 'fallback_artwork' in list(diagnostics.get('render_warnings') or []),
            'render_warnings': list(diagnostics.get('render_warnings') or []),
        }

    @staticmethod
    def _leading_streak(window_cards: list[dict[str, Any]], field_name: str) -> dict[str, Any]:
        if not window_cards:
            return {}
        first_value = str(window_cards[0].get(field_name) or '')
        streak = 0
        for card in window_cards:
            if str(card.get(field_name) or '') != first_value:
                break
            streak += 1
        return {
            field_name: first_value,
            'length': streak,
            'flagged': streak >= 3,
        }

    @staticmethod
    def _card_family(template_id: str, diagnostics: dict[str, Any]) -> str:
        card_type = str(diagnostics.get('card_type') or '').strip().upper()
        if card_type in {'DISCOUNT', 'FREE_GAME', 'FESTIVAL', 'TOP_LIST'}:
            return card_type
        normalized_template = str(template_id or '').strip().lower()
        if normalized_template == 'roundup_digest' or 'top' in normalized_template:
            return 'TOP_LIST'
        if normalized_template == 'festival_event':
            return 'FESTIVAL'
        if normalized_template in {'steam_free', 'epic_free'}:
            return 'FREE_GAME'
        return 'DISCOUNT'

    def _candidate_snapshot(
        self,
        record: QueueRecord,
        *,
        total_priority: float | None = None,
        eligible: bool = False,
        selected: bool = False,
        blocker_reason: str | None = None,
        blocker_detail: str | None = None,
        publish_priority: dict[str, Any] | None = None,
        editorial_adjustment: dict[str, Any] | None = None,
    ) -> SelectionCandidateSnapshot:
        return SelectionCandidateSnapshot(
            row_id=int(record.row_id),
            bucket=str(record.bucket),
            lane=str(record.decision_json.get('lane') or record.lane),
            content_family=self._content_family(record),
            source=str(record.offer.source.value),
            offer_id=str(record.offer.offer_id),
            title=str(record.offer.title),
            template_id=str(record.decision_json.get('template_id') or '') or None,
            score=float(record.decision_json.get('score') or record.score or 0.0),
            total_priority=total_priority,
            selected=selected,
            eligible=eligible,
            blocker_reason=blocker_reason,
            blocker_detail=blocker_detail,
            recommended_post_mode=record.decision_json.get('recommended_post_mode'),
            publish_priority=publish_priority or {},
            editorial_adjustment=editorial_adjustment or {},
            decision_reasons=list(record.decision_json.get('decision_reasons') or []),
            quality_reasons=list(record.decision_json.get('quality_reasons') or []),
            store_url=str(record.offer.store_url or ''),
            created_at=record.created_at.isoformat() if isinstance(record.created_at, datetime) else None,
        )

    def _published_candidate_blocker(self, record: QueueRecord, now_utc: datetime) -> tuple[str | None, str | None]:
        if self._is_roundup_candidate(record):
            return None, None
        game_id = str(record.offer.game_id or '').strip()
        if not game_id:
            return None, None
        game_history = self.repositories.get_game_history(game_id)
        if game_history is None:
            return None, None
        dedup = self.dedup_policy.evaluate(record.offer, game_history, None, now_utc)
        if dedup.accepted:
            return None, None
        detail = (
            f'game_id={game_id} posted_at={game_history.posted_at.isoformat()} '
            f'lane={game_history.lane or "unknown"} dedup_reason={dedup.reason}'
        )
        return 'already_published', detail

    def _blocked_selection_result(self, now_utc: datetime, now_local: datetime) -> PublishResult | None:
        inspection = self.inspect_selection(now_utc, now_local)
        blocker_reason = str(inspection.blocker_reason or '').strip()
        if blocker_reason not in {'already_published', 'already_sent_finalize_only'}:
            return None
        blocked_candidate = next(
            (candidate for candidate in inspection.blocked_candidates if candidate.blocker_reason == blocker_reason),
            None,
        )
        if blocked_candidate is None:
            return None
        record = self._queue_record_by_row_id(blocked_candidate.row_id)
        if record is None:
            return None
        return self._result(
            record,
            blocker_reason,
            False,
            failure_detail=blocked_candidate.blocker_detail,
        )

    def _queue_record_by_row_id(self, row_id: int) -> QueueRecord | None:
        for bucket in ('planned', 'reserve'):
            for record in self.repositories.list_queue(bucket):
                if int(record.row_id) == int(row_id):
                    return record
        return None

    def _selection_blocker(
        self,
        *,
        planned_total: int,
        reserve_total: int,
        allow_reserve: bool,
        blocked_candidates: list[SelectionCandidateSnapshot],
        roundup_injection: dict[str, Any] | None,
    ) -> tuple[str | None, str | None]:
        if planned_total <= 0 and reserve_total <= 0:
            return 'queue_empty', 'No planned or reserve rows exist.'
        if planned_total <= 0 and reserve_total > 0 and not allow_reserve:
            return 'quiet_hours_reserve_hidden', 'Only reserve rows exist, and reserve is hidden during quiet hours.'
        if blocked_candidates:
            priority = ['already_published', 'already_sent_finalize_only', 'daily_lane_cap_reached', 'controlled_reserve_release_held', 'quiet_hours_reserve_hidden']
            blocked_candidates.sort(key=lambda item: priority.index(item.blocker_reason) if item.blocker_reason in priority else len(priority))
            winner = blocked_candidates[0]
            return winner.blocker_reason, winner.blocker_detail
        if roundup_injection:
            reason = str(roundup_injection.get('reason') or '').strip() or None
            if reason:
                return reason, str(roundup_injection.get('release_status') or '').strip() or None
        return 'no_publishable_candidate', 'No selector-eligible candidate was found.'

    def _artifact_preview(self, artifact: PostArtifact, image_path: Path | None) -> dict[str, Any]:
        diagnostics = dict(artifact.render_diagnostics or {})
        caption_html = str(artifact.caption_html or '')
        return {
            'offer_id': artifact.offer_id,
            'template_id': artifact.template_id,
            'card_family': self._card_family(artifact.template_id, diagnostics),
            'caption_html': caption_html,
            'caption_preview': self._caption_preview(caption_html),
            'caption_length': len(caption_html),
            'caption_hash': artifact.caption_hash,
            'image_hash': artifact.image_hash,
            'idempotency_key': artifact.idempotency_key,
            'image_path': str(image_path) if image_path else None,
            'assets_used': list(artifact.assets_used),
            'render_diagnostics': diagnostics,
            'caption_debug': dict((artifact.decision_debug or {}).get('caption') or {}),
        }

    @staticmethod
    def _caption_preview(caption_html: str, limit: int = 220) -> str:
        text = ' '.join(str(caption_html or '').split())
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + '...'

    @staticmethod
    def _content_family(record: QueueRecord) -> str:
        declared = str(record.decision_json.get('content_type') or '').strip().lower()
        if declared in {'roundup', 'freebie', 'event', 'discount'}:
            return declared
        lane = str(record.decision_json.get('lane') or record.lane).strip().lower()
        if lane == 'roundup_digest' or str(record.offer.offer_id).startswith('roundup:'):
            return 'roundup'
        if getattr(record.offer, 'is_event', False) or lane == 'event_festival':
            return 'event'
        if getattr(record.offer, 'is_freebie', False) or lane == 'breaking_freebie':
            return 'freebie'
        return 'discount'

    @staticmethod
    def _blocker_category(reason: str | None) -> str | None:
        normalized = str(reason or '').strip().lower()
        if not normalized:
            return None
        if normalized in {
            'render_failed',
            'card_asset_missing_on_disk',
            'missing_card_asset_path',
            'planned_assets_not_localized',
        }:
            return 'asset_localization'
        if normalized in {'publish_failed'}:
            return 'telegram_delivery'
        if normalized.startswith('db_'):
            return 'other'
        return 'queue_state'

    @staticmethod
    def _failure_detail(exc: Exception) -> str:
        text = str(exc).strip()
        return text or exc.__class__.__name__

    def _select_record(
        self,
        now_utc: datetime,
        now_local: datetime,
    ) -> tuple[QueueRecord | None, dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
        allow_reserve = not self._is_quiet_hours(now_local)
        planned_candidates = list(self.repositories.list_queue('planned'))
        reserve_candidates = list(self.repositories.list_queue('reserve')) if allow_reserve else []
        recent_stream = self.repositories.list_recent_published_stream(limit=self.editorial_stream_controller.RECENT_WINDOW)
        roundup_candidate, roundup_injection = self._build_roundup_candidate(reserve_candidates, recent_stream)

        try:
            release_decision = self.controlled_reserve_release.release(
                planned_candidates=planned_candidates,
                reserve_candidates=reserve_candidates,
                roundup_candidate=roundup_candidate,
                recent_stream=recent_stream,
            )
            reserve_candidates = list(release_decision.visible_reserve_candidates)
            original_roundup_candidate = roundup_candidate
            roundup_candidate = release_decision.visible_roundup_candidate
            if roundup_injection and roundup_injection.get('status') == 'candidate_ready':
                if original_roundup_candidate is not None and roundup_candidate is None:
                    roundup_injection['status'] = 'held'
                    roundup_injection['reason'] = 'controlled_reserve_release_held'
                    roundup_injection['release_status'] = 'held'
                elif roundup_candidate is not None:
                    roundup_injection['release_status'] = 'visible'
        except Exception as exc:
            self.metrics.inc('publish.controlled_reserve_release.failed')
            self.logger.warning('Controlled reserve release failed: %s', exc)

        candidates = list(planned_candidates)
        candidates.extend(reserve_candidates)
        if roundup_candidate is not None:
            candidates.append(roundup_candidate)
        if not candidates:
            return None, None, None, roundup_injection

        day_key = now_local.date().isoformat()
        lane_usage_cache: dict[str, int] = {}
        rankable: list[tuple[QueueRecord, PublishPriority]] = []
        for record in candidates:
            blocker_reason, _ = self._published_candidate_blocker(record, now_utc)
            if blocker_reason is not None:
                continue
            lane = str(record.decision_json.get('lane') or record.lane)
            lane_usage = lane_usage_cache.setdefault(lane, self.repositories.get_daily_lane_count(day_key, lane))
            manual_force_override = bool(record.decision_json.get('manual_force_override'))
            if self.content_lanes.quota_blocked(lane, {lane: lane_usage}, manual_force_override=manual_force_override):
                self.metrics.inc(f'publish.skipped.daily_cap.{lane}')
                continue

            priority = self.publish_priority_engine.evaluate(
                offer=record.offer,
                lane=lane,
                bucket=record.bucket,
                decision_score=float(record.decision_json.get('score') or record.score or 0.0),
                must_ship=bool(record.decision_json.get('must_ship')),
                manual_force_override=manual_force_override,
                lane_published_today=lane_usage,
                now_utc=now_utc,
            )
            rankable.append((record, priority))

        if not rankable:
            return None, None, None, roundup_injection

        eligible_records = [record for record, _ in rankable]
        ranked: list[tuple[tuple[float, int, float, int], QueueRecord, PublishPriority, EditorialAdjustment]] = []
        for record, priority in rankable:
            editorial_adjustment = self.editorial_stream_controller.score_candidate(record, eligible_records, recent_stream)
            ranked.append((self._priority_sort_key(record, priority, editorial_adjustment), record, priority, editorial_adjustment))

        _, selected_record, selected_priority, selected_adjustment = max(ranked, key=lambda item: item[0])
        return (
            selected_record,
            selected_priority.to_snapshot(),
            selected_adjustment.to_snapshot(base_total=selected_priority.total),
            roundup_injection,
        )

    def _build_roundup_candidate(
        self,
        reserve_candidates: list[QueueRecord],
        recent_stream: list[dict[str, Any]],
    ) -> tuple[QueueRecord | None, dict[str, Any]]:
        diagnostics = {
            'attempted': bool(reserve_candidates),
            'status': 'rejected',
            'reason': 'no_reserve_candidates' if not reserve_candidates else 'candidate_unavailable',
            'lookup_mode': None,
            'strict_rejection_reason': None,
            'queue_snapshot_at': None,
            'roundup_run_key': None,
            'roundup_id': None,
            'json_path': None,
            'release_status': 'not_applicable',
        }
        if not reserve_candidates:
            return None, diagnostics
        if any(
            self.editorial_stream_controller._content_type_from_stream_entry(item) == 'roundup'
            for item in recent_stream[: self.ROUNDUP_SPACING_POSTS]
        ):
            diagnostics['reason'] = 'recent_roundup_spacing_blocked'
            return None, diagnostics

        queue_snapshot_at = self._queue_window_key(reserve_candidates)
        diagnostics['lookup_mode'] = 'strict'
        diagnostics['queue_snapshot_at'] = queue_snapshot_at
        if queue_snapshot_at is None:
            diagnostics['reason'] = 'queue_snapshot_missing'
            return None, diagnostics

        roundup_snapshot = self.repositories.get_latest_publishable_roundup_snapshot(queue_snapshot_at)
        if roundup_snapshot is None:
            latest_canonical = self.repositories.get_latest_canonical_roundup_snapshot()
            if latest_canonical is None:
                diagnostics['reason'] = 'snapshot_not_found'
                return None, diagnostics
            diagnostics['roundup_run_key'] = str(latest_canonical.get('run_key') or '').strip() or None
            diagnostics['json_path'] = latest_canonical.get('json_path')
            strict_rejection_reason = self._strict_roundup_lookup_rejection_reason(latest_canonical, queue_snapshot_at)
            diagnostics['strict_rejection_reason'] = strict_rejection_reason
            if not self._can_use_roundup_fallback(latest_canonical, queue_snapshot_at):
                diagnostics['reason'] = strict_rejection_reason
                return None, diagnostics
            roundup_snapshot = latest_canonical
            diagnostics['lookup_mode'] = 'fallback'

        diagnostics['roundup_run_key'] = str(roundup_snapshot.get('run_key') or '').strip() or diagnostics['roundup_run_key']
        diagnostics['json_path'] = roundup_snapshot.get('json_path') or diagnostics['json_path']

        roundups = roundup_snapshot.get('roundups') or []
        if not isinstance(roundups, list) or len(roundups) != 1:
            diagnostics['reason'] = 'invalid_roundup_count'
            return None, diagnostics
        roundup = roundups[0]
        if not isinstance(roundup, dict):
            diagnostics['reason'] = 'invalid_roundup_payload'
            return None, diagnostics

        roundup_id = str(roundup.get('roundup_id') or '').strip()
        diagnostics['roundup_id'] = roundup_id or None
        run_key = str(roundup_snapshot.get('run_key') or '').strip()
        if not roundup_id:
            diagnostics['reason'] = 'missing_roundup_id'
            return None, diagnostics
        if not run_key:
            diagnostics['reason'] = 'missing_roundup_run_key'
            return None, diagnostics

        telegram_draft = roundup.get('telegram_draft') or {}
        if not isinstance(telegram_draft, dict):
            diagnostics['reason'] = 'missing_telegram_draft'
            return None, diagnostics
        caption_html = str(telegram_draft.get('caption_html') or '').strip()
        if not caption_html:
            diagnostics['reason'] = 'missing_caption_html'
            return None, diagnostics

        card_asset_path = str(roundup.get('card_asset_path') or '').strip()
        if not card_asset_path:
            diagnostics['reason'] = 'missing_card_asset_path'
            return None, diagnostics
        card_path = Path(card_asset_path)
        if not card_path.exists():
            diagnostics['reason'] = 'card_asset_missing_on_disk'
            return None, diagnostics

        reserve_by_offer_id = {record.offer.offer_id: record for record in reserve_candidates}
        item_records: list[QueueRecord] = []
        item_offer_ids: list[str] = []
        for item in roundup.get('items') or []:
            if not isinstance(item, dict):
                diagnostics['reason'] = 'invalid_roundup_item_payload'
                return None, diagnostics
            offer_id = str(item.get('offer_id') or '').strip()
            if not offer_id:
                diagnostics['reason'] = 'missing_roundup_item_offer_id'
                return None, diagnostics
            reserve_record = reserve_by_offer_id.get(offer_id)
            if reserve_record is None:
                diagnostics['reason'] = 'roundup_item_not_in_reserve'
                return None, diagnostics
            if self.repositories.get_game_history(reserve_record.offer.game_id) is not None:
                diagnostics['reason'] = 'roundup_item_already_published'
                return None, diagnostics
            item_offer_ids.append(offer_id)
            item_records.append(reserve_record)

        if not item_records:
            diagnostics['reason'] = 'roundup_items_empty'
            return None, diagnostics

        idempotency_key = f'roundup:{roundup_id}:{run_key}'
        if self.repositories.get_outbox_record(idempotency_key) is not None:
            diagnostics['reason'] = 'roundup_already_in_outbox'
            return None, diagnostics

        item_offer_snapshots = [record.offer.to_snapshot() for record in item_records]
        queue_row_ids = [record.row_id for record in item_records]
        decision_score = self._roundup_score_from_snapshot(roundup.get('items') or [], reserve_by_offer_id)
        offer = self._roundup_offer(roundup_snapshot, roundup, item_records, item_offer_ids)
        row_id = max(record.row_id for record in reserve_candidates) + 1
        created_at = item_records[0].created_at
        decision_json = {
            'lane': self.ROUNDUP_LANE,
            'template_id': self.ROUNDUP_LANE,
            'must_ship': False,
            'queue_bucket': 'reserve',
            'decision_reasons': ['roundup_digest', 'roundup_publish_candidate'],
            'quality_reasons': ['roundup_artifact_ready'],
            'dedup_reason': 'roundup_snapshot',
            'score': decision_score,
            'manual_force_override': False,
            'content_type': 'roundup',
            'selection_outcome': 'roundup_publish_candidate',
            'recommended_post_mode': 'roundup',
            'roundup_id': roundup_id,
            'roundup_run_key': run_key,
            'roundup_item_offer_ids': item_offer_ids,
            'roundup_item_offers': item_offer_snapshots,
            'roundup_queue_row_ids': queue_row_ids,
            'roundup_caption_html': caption_html,
            'roundup_card_asset_path': card_asset_path,
            'roundup_card_render_diagnostics': dict(roundup.get('card_render_diagnostics') or {}),
            'roundup_queue_snapshot_at': queue_snapshot_at,
            'idempotency_key': idempotency_key,
            'debug': {
                'roundup_source': 'analytics_artifact',
                'roundup_item_count': len(item_offer_ids),
                'roundup_json_path': roundup_snapshot.get('json_path'),
                'roundup_source_mix': self._roundup_source_mix(roundup.get('items') or []),
            },
        }
        diagnostics['status'] = 'candidate_ready'
        diagnostics['reason'] = 'candidate_ready'
        return QueueRecord(
            row_id=row_id,
            bucket='reserve',
            lane=self.ROUNDUP_LANE,
            score=decision_score,
            offer=offer,
            decision_json=decision_json,
            created_at=created_at,
        ), diagnostics

    def _strict_roundup_lookup_rejection_reason(self, roundup_snapshot: dict[str, Any], queue_snapshot_at: str | None) -> str:
        normalized_window = self._normalize_roundup_window_key(queue_snapshot_at)
        if normalized_window is None:
            return 'queue_snapshot_missing'
        context = roundup_snapshot.get('context')
        if not isinstance(context, dict):
            return 'snapshot_context_missing_source'
        source = str(context.get('source') or '').strip()
        if not source:
            return 'snapshot_context_missing_source'
        if source != 'current_queue':
            return 'snapshot_filtered_non_editorial_scope'
        snapshot_window = self._normalize_roundup_window_key(context.get('queue_snapshot_at'))
        if snapshot_window is None:
            return 'snapshot_context_missing_queue_snapshot'
        if snapshot_window != normalized_window:
            return 'snapshot_queue_window_mismatch'
        return 'snapshot_not_found'

    def _can_use_roundup_fallback(self, roundup_snapshot: dict[str, Any], queue_snapshot_at: str | None) -> bool:
        normalized_window = self._normalize_roundup_window_key(queue_snapshot_at)
        if normalized_window is None:
            return False
        context = roundup_snapshot.get('context')
        if context is None:
            context = {}
        if not isinstance(context, dict):
            context = {}
        source = str(context.get('source') or '').strip()
        if source and source != 'current_queue':
            return False
        snapshot_window = self._normalize_roundup_window_key(context.get('queue_snapshot_at'))
        if snapshot_window and snapshot_window != normalized_window:
            return False
        return True

    def _roundup_post_artifact(self, record: QueueRecord, image_path: Path) -> PostArtifact:
        decision = record.decision_json
        caption_html = str(decision.get('roundup_caption_html') or '')
        image_bytes = image_path.read_bytes()
        stored_diagnostics = decision.get('roundup_card_render_diagnostics') or {}
        render_diagnostics = dict(stored_diagnostics) if isinstance(stored_diagnostics, dict) else {}
        render_diagnostics.setdefault('source', 'stored_roundup_artifact')
        render_diagnostics.setdefault('template_id', str(decision.get('template_id') or self.ROUNDUP_LANE))
        render_diagnostics.setdefault('renderer_requested', 'yoto_v4')
        render_diagnostics.setdefault('renderer_selected', 'yoto_v4')
        render_diagnostics.setdefault('renderer_family', 'yoto_v4')
        render_diagnostics.setdefault('renderer_fallback_used', False)
        render_diagnostics.setdefault('render_warnings', [])
        render_diagnostics.setdefault('selected_asset_path', str(image_path))
        render_diagnostics['roundup_id'] = decision.get('roundup_id')
        render_diagnostics['roundup_run_key'] = decision.get('roundup_run_key')
        return PostArtifact(
            offer_id=record.offer.offer_id,
            caption_html=caption_html,
            hashtags=[],
            template_id=str(decision.get('template_id') or self.ROUNDUP_LANE),
            render_inputs={'offer': record.offer.to_snapshot(), 'decision': decision},
            assets_used=[str(image_path)],
            idempotency_key=str(decision.get('idempotency_key') or ''),
            caption_hash=hashlib.sha256(caption_html.encode('utf-8')).hexdigest(),
            image_hash=hashlib.sha256(image_bytes).hexdigest(),
            render_diagnostics=render_diagnostics,
        )

    def _roundup_offer(
        self,
        roundup_snapshot: dict[str, Any],
        roundup: dict[str, Any],
        item_records: list[QueueRecord],
        item_offer_ids: list[str],
    ) -> Offer:
        roundup_id = str(roundup.get('roundup_id') or 'roundup')
        title = str(roundup.get('title') or 'Roundup').strip() or 'Roundup'
        source = self._roundup_offer_source(roundup.get('items') or [])
        promo_candidates = [record.offer.promo_end for record in item_records if record.offer.promo_end is not None]
        store_url = ''
        for item in roundup.get('items') or []:
            if isinstance(item, dict) and item.get('store_url'):
                store_url = str(item.get('store_url'))
                break
        if not store_url:
            store_url = 'https://store.steampowered.com/'
        return Offer(
            offer_id=f'roundup:{roundup_id}',
            source=source,
            source_ref=roundup_id,
            offer_kind=OfferKind.DISCOUNT,
            game_id=f'roundup:{roundup_id}',
            franchise_key=f'roundup:{roundup_id}',
            title=title,
            store_url=store_url,
            price_before_minor=None,
            price_after_minor=None,
            currency='UAH',
            discount_percent=0,
            promo_start=None,
            promo_end=min(promo_candidates) if promo_candidates else None,
            review_score=None,
            review_count=None,
            achievements_count=None,
            has_trading_cards=False,
            assets=AssetBundle(fallback=str(roundup.get('card_asset_path') or '')),
            metadata={
                'content_type': 'roundup',
                'roundup_id': roundup_id,
                'roundup_run_key': roundup_snapshot.get('run_key'),
                'roundup_item_offer_ids': list(item_offer_ids),
            },
        )

    @staticmethod
    def _roundup_offer_source(items: list[dict[str, Any]]) -> OfferSource:
        sources = {str(item.get('source') or '').strip().lower() for item in items if isinstance(item, dict)}
        sources.discard('')
        if sources == {'steam'}:
            return OfferSource.STEAM
        if sources == {'epic'}:
            return OfferSource.EPIC
        return OfferSource.EVENT

    @staticmethod
    def _roundup_source_mix(items: list[dict[str, Any]]) -> str:
        sources = sorted({str(item.get('source') or '').strip().lower() for item in items if isinstance(item, dict) and item.get('source')})
        if not sources:
            return 'unknown'
        if len(sources) == 1:
            return sources[0]
        return 'mixed'

    @staticmethod
    def _roundup_score_from_snapshot(items: list[dict[str, Any]], reserve_by_offer_id: dict[str, QueueRecord]) -> float:
        scores: list[float] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            offer_id = str(item.get('offer_id') or '').strip()
            reserve_record = reserve_by_offer_id.get(offer_id)
            if reserve_record is not None:
                scores.append(float(reserve_record.decision_json.get('score') or reserve_record.score or 0.0))
                continue
            scores.append(float(item.get('score') or 0.0))
        return max(scores) if scores else 0.0

    @staticmethod
    def _queue_window_key(records: list[QueueRecord]) -> str | None:
        timestamps = [record.created_at for record in records if isinstance(record.created_at, datetime)]
        if not timestamps:
            return None
        return min(timestamps).replace(microsecond=0).isoformat()

    @staticmethod
    def _normalize_roundup_window_key(value: str | None) -> str | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value)).replace(microsecond=0).isoformat()
        except ValueError:
            return None

    @staticmethod
    def _is_roundup_candidate(record: QueueRecord) -> bool:
        return str(record.decision_json.get('content_type') or '').strip().lower() == 'roundup'

    @staticmethod
    def _priority_sort_key(
        record: QueueRecord,
        priority: PublishPriority,
        editorial_adjustment: EditorialAdjustment | None = None,
    ) -> tuple[float, int, float, int]:
        planned_bias = 1 if record.bucket == 'planned' else 0
        raw_score = float(record.decision_json.get('score') or record.score or 0.0)
        total = float(priority.total) + float(editorial_adjustment.total_delta if editorial_adjustment else 0.0)
        return (round(total, 2), planned_bias, raw_score, -record.row_id)

    def _is_quiet_hours(self, now_local: datetime) -> bool:
        return self.QUIET_START <= now_local.time() <= self.QUIET_END







