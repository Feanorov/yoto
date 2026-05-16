from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path
from typing import Any

from dealbot.settings import AppSettings
from domain.entities.analytics_artifact import AnalyticsArtifact
from infrastructure.analytics.artifact_writer import AnalyticsArtifactWriter
from infrastructure.db.repositories import Repositories

from .ingest_health_controller import RunDiagnostics
from .offline_validation_snapshot import OfflineSnapshotBundle
from .plan_queue import PlannedCandidate, QueuePlan
from .publish_next import PublishResult, SelectionInspection, SendTestTargetPreview


class OperatorTruthReporter:
    def __init__(
        self,
        repositories: Repositories,
        writer: AnalyticsArtifactWriter,
    ) -> None:
        self.repositories = repositories
        self.writer = writer
        self.logger = logging.getLogger(__name__)

    def build_payload(
        self,
        *,
        now_utc: datetime,
        mode: str,
        settings: AppSettings,
        plan: QueuePlan,
        selection: SelectionInspection,
        target: SendTestTargetPreview,
        diagnostics: RunDiagnostics | None = None,
        publish_result: PublishResult | None = None,
        offline_bundle: OfflineSnapshotBundle | None = None,
    ) -> dict[str, Any]:
        queue_summary = self._queue_summary(plan)
        target_snapshot = target.to_snapshot()
        publish_snapshot = self._publish_snapshot(publish_result, target_snapshot)
        outbox_snapshot = self._outbox_snapshot(target_snapshot)
        verdict = self._verdict(
            target_snapshot=target_snapshot,
            diagnostics=diagnostics,
            publish_result=publish_result,
            outbox_snapshot=outbox_snapshot,
        )
        return {
            'run_key': now_utc.strftime('%Y%m%dT%H%M%SZ'),
            'created_at': now_utc.isoformat(),
            'mode': mode,
            'scope': 'offline' if 'offline' in mode else 'live',
            'ingest_sources': dict((plan.context or {}).get('ingest_sources') or {}),
            'queue': queue_summary,
            'selection': selection.to_snapshot(),
            'send_test_target': target_snapshot,
            'telegram': {
                'channel': settings.channel_username,
                'configured': bool(settings.bot_token and settings.channel_username),
                'delivery_attempted': publish_result is not None,
                'delivery_verified': bool(publish_result.published) if publish_result is not None else False,
                'publish_result': publish_snapshot,
                'outbox': outbox_snapshot,
            },
            'offline_snapshot': self._offline_snapshot_summary(offline_bundle),
            'diagnostics': diagnostics.to_payload() if diagnostics is not None else None,
            'verdict': verdict,
        }

    def emit(
        self,
        *,
        now_utc: datetime,
        mode: str,
        settings: AppSettings,
        plan: QueuePlan,
        selection: SelectionInspection,
        target: SendTestTargetPreview,
        diagnostics: RunDiagnostics | None = None,
        publish_result: PublishResult | None = None,
        offline_bundle: OfflineSnapshotBundle | None = None,
    ) -> AnalyticsArtifact:
        payload = self.build_payload(
            now_utc=now_utc,
            mode=mode,
            settings=settings,
            plan=plan,
            selection=selection,
            target=target,
            diagnostics=diagnostics,
            publish_result=publish_result,
            offline_bundle=offline_bundle,
        )
        run_key = str(payload['run_key'])
        verdict = dict(payload.get('verdict') or {})
        queue = dict(payload.get('queue') or {})
        summary_row = {
            'mode': mode,
            'scope': payload.get('scope'),
            'truth_ready': verdict.get('truth_ready'),
            'telegram_verified': verdict.get('telegram_verified'),
            'blocker_category': verdict.get('blocker_category'),
            'blocker_reason': verdict.get('blocker_reason'),
            'planned_total': ((queue.get('buckets') or {}).get('planned') or {}).get('total'),
            'reserve_total': ((queue.get('buckets') or {}).get('reserve') or {}).get('total'),
            'deferred_total': queue.get('deferred_total'),
            'eligible_candidates_total': ((payload.get('selection') or {}).get('eligible_candidates_total')),
            'selected_offer_id': ((payload.get('send_test_target') or {}).get('candidate') or {}).get('offer_id'),
            'selected_title': ((payload.get('send_test_target') or {}).get('candidate') or {}).get('title'),
            'publish_reason': ((payload.get('telegram') or {}).get('publish_result') or {}).get('reason'),
        }
        artifact = AnalyticsArtifact(
            artifact_type='operator_truth_report',
            subject_id=mode,
            run_key=run_key,
            created_at=now_utc,
            payload_json=payload,
            summary_rows=[summary_row],
        )
        try:
            artifact.json_path, artifact.csv_path = self.writer.write(artifact)
        except Exception as exc:
            artifact.json_path = None
            artifact.csv_path = None
            self.logger.warning('Operator truth report write failed: %s', exc)
        if self._should_persist_to_repository(mode=mode, offline_bundle=offline_bundle):
            try:
                self.repositories.save_analytics_artifact(artifact)
            except Exception as exc:
                self.logger.warning('Operator truth report persistence failed: %s', exc)
        return artifact

    @staticmethod
    def _should_persist_to_repository(
        *,
        mode: str,
        offline_bundle: OfflineSnapshotBundle | None,
    ) -> bool:
        if offline_bundle is None:
            return True
        return mode != 'preview_offline'

    def _queue_summary(self, plan: QueuePlan) -> dict[str, Any]:
        selection_summary = dict((plan.context or {}).get('selection_summary') or {})
        planned = list(plan.planned)
        reserve = list(plan.reserve)
        return {
            'deferred_total': int(selection_summary.get('capacity_hold') or 0),
            'buckets': {
                'planned': self._bucket_summary(planned),
                'reserve': self._bucket_summary(reserve),
            },
        }

    def _bucket_summary(self, items: list[PlannedCandidate]) -> dict[str, Any]:
        rows = [self._plan_row(item) for item in items]
        return {
            'total': len(items),
            'by_family': self._count_by(rows, 'content_family'),
            'by_lane': self._count_by(rows, 'lane'),
            'by_source': self._count_by(rows, 'source'),
            'rows': rows,
        }

    def _plan_row(self, item: PlannedCandidate) -> dict[str, Any]:
        return {
            'offer_id': item.offer.offer_id,
            'title': item.offer.title,
            'source': item.offer.source.value,
            'lane': item.decision_json.get('lane'),
            'content_family': self._content_family(item),
            'score': float(item.decision_json.get('score') or item.score or 0.0),
            'template_id': item.decision_json.get('template_id'),
            'recommended_post_mode': item.decision_json.get('recommended_post_mode'),
        }

    def _publish_snapshot(self, publish_result: PublishResult | None, target_snapshot: dict[str, Any]) -> dict[str, Any] | None:
        if publish_result is None:
            return None
        publish_outcome = dict((publish_result.analytics or {}).get('publish_outcome') or {})
        return {
            'offer_id': publish_result.offer_id,
            'title': publish_result.title,
            'lane': publish_result.lane,
            'published': publish_result.published,
            'reason': publish_result.reason,
            'message_id': publish_result.message_id,
            'image_path': str(publish_result.image_path) if publish_result.image_path else None,
            'failure_detail': publish_outcome.get('failure_detail'),
            'target_idempotency_key': ((target_snapshot.get('artifact') or {}).get('idempotency_key')),
        }

    def _outbox_snapshot(self, target_snapshot: dict[str, Any]) -> dict[str, Any] | None:
        artifact = dict(target_snapshot.get('artifact') or {})
        idempotency_key = str(artifact.get('idempotency_key') or '').strip()
        if not idempotency_key:
            return None
        record = self.repositories.get_outbox_record(idempotency_key)
        if record is None:
            return None
        return {
            'idempotency_key': idempotency_key,
            'status': record.status,
            'telegram_message_id': record.telegram_message_id,
            'last_error': record.last_error,
            'updated_at': record.updated_at.isoformat() if record.updated_at else None,
            'image_path': str(record.image_path) if record.image_path else None,
        }

    @staticmethod
    def _offline_snapshot_summary(bundle: OfflineSnapshotBundle | None) -> dict[str, Any] | None:
        if bundle is None:
            return None
        return {
            'run_key': bundle.run_key,
            'manifest_path': str(bundle.manifest_path),
            'base_db_path': str(bundle.base_db_path),
            'snapshot_role': bundle.snapshot_role,
            'planned_count': bundle.planned_count,
            'reserve_count': bundle.reserve_count,
            'quality': dict(bundle.quality or {}),
        }

    def _verdict(
        self,
        *,
        target_snapshot: dict[str, Any],
        diagnostics: RunDiagnostics | None,
        publish_result: PublishResult | None,
        outbox_snapshot: dict[str, Any] | None,
    ) -> dict[str, Any]:
        truth_ready = bool(target_snapshot.get('truth_ready'))
        blocker_category = target_snapshot.get('blocker_category')
        blocker_reason = target_snapshot.get('blocker_reason')
        blocker_detail = target_snapshot.get('blocker_detail')
        telegram_verified = bool(publish_result.published) if publish_result is not None else False

        if diagnostics is not None and diagnostics.fatal_ingest:
            blocker_category = 'ingest'
            blocker_reason = (diagnostics.reasons or ['fatal_ingest'])[0]
            blocker_detail = diagnostics.status
            truth_ready = False
        elif publish_result is not None and not publish_result.published:
            if publish_result.reason == 'publish_failed':
                blocker_category = 'telegram_delivery'
                blocker_reason = outbox_snapshot.get('last_error') if outbox_snapshot is not None else 'publish_failed'
                blocker_detail = publish_result.reason
            elif str(publish_result.reason).startswith('db_'):
                blocker_category = 'other'
                blocker_reason = publish_result.reason
                blocker_detail = 'storage_or_finalize'
            elif publish_result.reason:
                blocker_category = blocker_category or self._fallback_blocker_category(str(publish_result.reason))
                blocker_reason = blocker_reason or publish_result.reason
                blocker_detail = blocker_detail or publish_result.reason
            truth_ready = False

        verdict = 'truthful_send_test_ready' if truth_ready else 'truthful_send_test_blocked'
        if telegram_verified:
            verdict = 'telegram_proof_verified'
        return {
            'verdict': verdict,
            'truth_ready': truth_ready,
            'telegram_verified': telegram_verified,
            'blocker_category': blocker_category,
            'blocker_reason': blocker_reason,
            'blocker_detail': blocker_detail,
            'next_step': self._next_step(blocker_category),
        }

    @staticmethod
    def _next_step(blocker_category: str | None) -> str:
        if blocker_category == 'ingest':
            return 'Inspect ingest source statuses and degraded source reasons.'
        if blocker_category == 'queue_state':
            return 'Inspect queue bucket counts and blocked candidate reasons.'
        if blocker_category == 'asset_localization':
            return 'Inspect the selected asset paths and render diagnostics.'
        if blocker_category == 'telegram_delivery':
            return 'Inspect Telegram credentials/network and the publish_outbox last_error.'
        return 'Inspect the operator truth report JSON and recent analytics artifacts.'

    @staticmethod
    def _fallback_blocker_category(reason: str) -> str:
        normalized = str(reason or '').strip().lower()
        if normalized.startswith('db_'):
            return 'other'
        if normalized in {'render_failed', 'card_asset_missing_on_disk', 'planned_assets_not_localized'}:
            return 'asset_localization'
        if normalized in {'publish_failed'}:
            return 'telegram_delivery'
        if normalized in {'queue_empty', 'planner_window_empty', 'already_published', 'already_sent_finalize_only'}:
            return 'queue_state'
        return 'queue_state'

    @staticmethod
    def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in rows:
            value = str(row.get(key) or '').strip() or 'unknown'
            counts[value] = counts.get(value, 0) + 1
        return counts

    @staticmethod
    def _content_family(item: PlannedCandidate) -> str:
        decision = dict(item.decision_json or {})
        declared = str(decision.get('content_type') or '').strip().lower()
        if declared in {'roundup', 'freebie', 'event', 'discount'}:
            return declared
        lane = str(decision.get('lane') or '').strip().lower()
        if lane == 'roundup_digest' or str(item.offer.offer_id).startswith('roundup:'):
            return 'roundup'
        if getattr(item.offer, 'is_event', False) or lane == 'event_festival':
            return 'event'
        if getattr(item.offer, 'is_freebie', False) or lane == 'breaking_freebie':
            return 'freebie'
        return 'discount'
