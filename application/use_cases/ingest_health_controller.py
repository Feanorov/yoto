from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
import logging
from typing import Any

from domain.entities.analytics_artifact import AnalyticsArtifact
from infrastructure.analytics.artifact_writer import AnalyticsArtifactWriter
from infrastructure.db.repositories import Repositories
from infrastructure.observability.metrics import Metrics

from .plan_queue import QueuePlan
from .publish_next import PublishResult


@dataclass(slots=True)
class RunDiagnostics:
    run_key: str
    created_at: datetime
    status: str
    pipeline_action: str
    fatal_ingest: bool
    empty_window: bool
    should_stop_pipeline: bool
    ingest_metrics_available: bool
    ingested_total: int | None
    enriched_total: int | None
    planned_count: int
    reserve_count: int
    publish_attempted: bool
    publish_result: dict[str, Any] = field(default_factory=dict)
    plan_context: dict[str, Any] = field(default_factory=dict)
    plan_metrics: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            'run_key': self.run_key,
            'created_at': self.created_at.isoformat(),
            'status': self.status,
            'pipeline_action': self.pipeline_action,
            'fatal_ingest': self.fatal_ingest,
            'empty_window': self.empty_window,
            'should_stop_pipeline': self.should_stop_pipeline,
            'reasons': list(self.reasons),
            'ingest': {
                'metrics_available': self.ingest_metrics_available,
                'ingested_total': self.ingested_total,
                'enriched_total': self.enriched_total,
            },
            'planner_window': {
                'planned_count': self.planned_count,
                'reserve_count': self.reserve_count,
                'empty': self.empty_window,
            },
            'publish': dict(self.publish_result),
            'context': dict(self.plan_context),
            'metrics': dict(self.plan_metrics),
        }

    def to_summary_row(self) -> dict[str, Any]:
        return {
            'run_key': self.run_key,
            'status': self.status,
            'pipeline_action': self.pipeline_action,
            'fatal_ingest': self.fatal_ingest,
            'empty_window': self.empty_window,
            'should_stop_pipeline': self.should_stop_pipeline,
            'ingested_total': self.ingested_total,
            'enriched_total': self.enriched_total,
            'planned_count': self.planned_count,
            'reserve_count': self.reserve_count,
            'publish_attempted': self.publish_attempted,
            'publish_reason': self.publish_result.get('reason'),
            'published': self.publish_result.get('published'),
            'reasons': list(self.reasons),
        }


class IngestHealthController:
    HEALTHY = 'healthy'
    EMPTY_WINDOW = 'empty_planner_window'
    FATAL_INGEST = 'fatal_ingest'

    def __init__(
        self,
        repositories: Repositories,
        writer: AnalyticsArtifactWriter,
        metrics: Metrics | None = None,
    ) -> None:
        self.repositories = repositories
        self.writer = writer
        self.metrics = metrics or Metrics()
        self.logger = logging.getLogger(__name__)

    def evaluate(self, now_utc: datetime, plan: QueuePlan) -> RunDiagnostics:
        run_key = now_utc.strftime('%Y%m%dT%H%M%SZ')
        plan_metrics = dict(plan.metrics or {})
        ingest_metrics_available = (
            'offers.ingested_total' in plan_metrics
            or 'offers.enriched_total' in plan_metrics
        )
        ingested_total = int(plan_metrics.get('offers.ingested_total', 0)) if ingest_metrics_available else None
        enriched_total = int(plan_metrics.get('offers.enriched_total', 0)) if ingest_metrics_available else None
        planned_count = len(plan.planned)
        reserve_count = len(plan.reserve)
        fatal_ingest = bool(
            ingest_metrics_available
            and (ingested_total or 0) <= 0
            and (enriched_total or 0) <= 0
        )
        empty_window = planned_count == 0 and reserve_count == 0 and not fatal_ingest

        reasons: list[str] = []
        status = self.HEALTHY
        if fatal_ingest:
            status = self.FATAL_INGEST
            reasons.append('no_offers_ingested')
            self.metrics.inc('launch_reliability.ingest.fatal')
        elif empty_window:
            status = self.EMPTY_WINDOW
            reasons.append('planner_window_empty')
            self.metrics.inc('launch_reliability.window.empty')
        else:
            self.metrics.inc('launch_reliability.window.healthy')

        return RunDiagnostics(
            run_key=run_key,
            created_at=now_utc,
            status=status,
            pipeline_action='evaluation_only',
            fatal_ingest=fatal_ingest,
            empty_window=empty_window,
            should_stop_pipeline=fatal_ingest,
            ingest_metrics_available=ingest_metrics_available,
            ingested_total=ingested_total,
            enriched_total=enriched_total,
            planned_count=planned_count,
            reserve_count=reserve_count,
            publish_attempted=False,
            plan_context=dict(plan.context or {}),
            plan_metrics=plan_metrics,
            reasons=reasons,
        )

    def finalize(
        self,
        diagnostics: RunDiagnostics,
        *,
        pipeline_action: str,
        publish_result: PublishResult | None = None,
    ) -> RunDiagnostics:
        publish_snapshot = self._publish_snapshot(publish_result, attempted=pipeline_action == 'publish_attempted')
        return replace(
            diagnostics,
            pipeline_action=pipeline_action,
            publish_attempted=pipeline_action == 'publish_attempted',
            publish_result=publish_snapshot,
        )

    def emit(self, diagnostics: RunDiagnostics) -> AnalyticsArtifact:
        artifact = AnalyticsArtifact(
            artifact_type='run_diagnostics',
            subject_id='pipeline',
            run_key=diagnostics.run_key,
            created_at=diagnostics.created_at,
            payload_json=diagnostics.to_payload(),
            summary_rows=[diagnostics.to_summary_row()],
        )
        try:
            artifact.json_path, artifact.csv_path = self.writer.write(artifact)
            self.metrics.inc('launch_reliability.files.success')
        except Exception as exc:
            self.metrics.inc('launch_reliability.files.failed')
            artifact.json_path = None
            artifact.csv_path = None
            self.logger.warning('Run diagnostics write failed: %s', exc)
        try:
            self.repositories.save_analytics_artifact(artifact)
            self.metrics.inc('launch_reliability.db.success')
        except Exception as exc:
            self.metrics.inc('launch_reliability.db.failed')
            self.logger.warning('Run diagnostics persistence failed: %s', exc)
        return artifact

    @staticmethod
    def _publish_snapshot(result: PublishResult | None, *, attempted: bool) -> dict[str, Any]:
        if result is None:
            return {
                'attempted': attempted,
                'published': False,
                'reason': None,
                'message_id': None,
                'offer_id': None,
                'title': None,
                'lane': None,
                'image_path': None,
            }
        return {
            'attempted': attempted,
            'published': result.published,
            'reason': result.reason,
            'message_id': result.message_id,
            'offer_id': result.offer_id,
            'title': result.title,
            'lane': result.lane,
            'image_path': str(result.image_path) if result.image_path else None,
        }
