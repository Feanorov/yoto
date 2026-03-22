from __future__ import annotations

from datetime import datetime
import logging

from domain.entities.analytics_artifact import AnalyticsArtifact
from infrastructure.analytics.artifact_writer import AnalyticsArtifactWriter
from infrastructure.db.repositories import Repositories
from infrastructure.observability.metrics import Metrics

from .plan_queue import PlannedCandidate, QueuePlan
from .publish_next import PublishResult


class GenerateAnalyticsArtifactsUseCase:
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

    def execute(self, now_utc: datetime, plan: QueuePlan, publish_result: PublishResult | None) -> None:
        run_key = now_utc.strftime('%Y%m%dT%H%M%SZ')
        artifacts = [self._build_planning_artifact(run_key, now_utc, plan)]
        if publish_result is not None:
            artifacts.append(self._build_publish_artifact(run_key, now_utc, publish_result))

        for artifact in artifacts:
            self._write_files(artifact)
            self._save_record(artifact)

    def _write_files(self, artifact: AnalyticsArtifact) -> None:
        try:
            artifact.json_path, artifact.csv_path = self.writer.write(artifact)
            self.metrics.inc('analytics.files.success')
        except Exception as exc:
            self.metrics.inc('analytics.files.failed')
            self.logger.warning('Analytics file write failed for %s: %s', artifact.artifact_type, exc)
            artifact.json_path = None
            artifact.csv_path = None

    def _save_record(self, artifact: AnalyticsArtifact) -> None:
        try:
            self.repositories.save_analytics_artifact(artifact)
            self.metrics.inc('analytics.db.success')
        except Exception as exc:
            self.metrics.inc('analytics.db.failed')
            self.logger.warning('Analytics persistence failed for %s: %s', artifact.artifact_type, exc)

    def _build_planning_artifact(self, run_key: str, now_utc: datetime, plan: QueuePlan) -> AnalyticsArtifact:
        planned_rows = [self._candidate_payload('planned', item) for item in plan.planned]
        reserve_rows = [self._candidate_payload('reserve', item) for item in plan.reserve]
        payload = {
            'run_key': run_key,
            'created_at': now_utc.isoformat(),
            'context': plan.context,
            'metrics': plan.metrics,
            'planned_count': len(plan.planned),
            'reserve_count': len(plan.reserve),
            'planned': planned_rows,
            'reserve': reserve_rows,
        }
        return AnalyticsArtifact(
            artifact_type='planning_snapshot',
            subject_id=run_key,
            run_key=run_key,
            created_at=now_utc,
            payload_json=payload,
            summary_rows=planned_rows + reserve_rows,
        )

    def _build_publish_artifact(self, run_key: str, now_utc: datetime, publish_result: PublishResult) -> AnalyticsArtifact:
        analytics = publish_result.analytics or {}
        payload = {
            'run_key': run_key,
            'created_at': now_utc.isoformat(),
            'offer_id': publish_result.offer_id,
            'title': publish_result.title,
            'lane': publish_result.lane,
            'published': publish_result.published,
            'reason': publish_result.reason,
            'message_id': publish_result.message_id,
            'image_path': str(publish_result.image_path) if publish_result.image_path else None,
            'selection': analytics.get('selection') or {},
            'render': analytics.get('render') or {},
            'publish_outcome': analytics.get('publish_outcome') or {},
        }
        summary_row = {
            'artifact_type': 'publish_outcome',
            'offer_id': publish_result.offer_id,
            'title': publish_result.title,
            'lane': publish_result.lane,
            'published': publish_result.published,
            'reason': publish_result.reason,
            'message_id': publish_result.message_id,
            'event_sale_influence': (analytics.get('selection') or {}).get('event_sale_influence'),
            'manual_override': ((analytics.get('selection') or {}).get('manual_override') or {}).get('forced'),
        }
        return AnalyticsArtifact(
            artifact_type='publish_outcome',
            subject_id=publish_result.offer_id,
            run_key=run_key,
            created_at=now_utc,
            payload_json=payload,
            summary_rows=[summary_row],
        )

    def _candidate_payload(self, bucket: str, item: PlannedCandidate) -> dict:
        debug = dict(item.decision_json.get('debug') or {})
        selection = {
            'bucket': bucket,
            'offer_id': item.offer.offer_id,
            'title': item.offer.title,
            'source': item.offer.source.value,
            'lane': item.decision_json.get('lane'),
            'score': item.score,
            'queue_bucket': item.decision_json.get('queue_bucket'),
            'decision_reasons': list(item.decision_json.get('decision_reasons') or []),
            'quality_reasons': list(item.decision_json.get('quality_reasons') or []),
            'dedup_reason': item.decision_json.get('dedup_reason'),
            'must_ship': item.decision_json.get('must_ship'),
            'event_sale_influence': debug.get('sale_event') or {},
            'diversity_constraints': list(debug.get('diversity_constraints') or []),
            'manual_override': {
                'forced': bool(item.decision_json.get('manual_force_override')),
                'reasons': list(debug.get('manual_control_reasons') or []),
            },
            'selection_outcome': item.decision_json.get('selection_outcome'),
            'recommended_post_mode': item.decision_json.get('recommended_post_mode'),
        }
        return selection
