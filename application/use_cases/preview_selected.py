from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from dealbot.settings import AppSettings
from infrastructure.db.repositories import Repositories

from .operator_truth_report import OperatorTruthReporter
from .plan_queue import PlannedCandidate, QueuePlan
from .publish_next import PublishNextUseCase, SelectionCandidateSnapshot


@dataclass(slots=True)
class PreviewSelectedResult:
    status: str
    reason: str
    created_report: bool
    source_report_path: Path | None = None
    source_report_run_key: str | None = None
    report_path: Path | None = None
    report_payload: dict[str, Any] = field(default_factory=dict)
    candidate_id: int | None = None
    selected: dict[str, Any] = field(default_factory=dict)
    truth_ready: bool = False
    would_send: bool = False
    blocker_category: str | None = None
    blocker_detail: str | None = None
    caption_hash: str | None = None
    image_hash: str | None = None
    image_path: Path | None = None


@dataclass(slots=True)
class SelectedPreviewContext:
    report_path: Path
    report_payload: dict[str, Any]
    run_key: str
    candidate_id: int
    candidate_row: dict[str, Any]


class PreviewSelectedUseCase:
    ALLOWED_STATUSES = {'recommended', 'ready', 'reserve'}

    def __init__(
        self,
        *,
        settings: AppSettings,
        repositories: Repositories,
        selector: PublishNextUseCase,
        reporter: OperatorTruthReporter,
    ) -> None:
        self.settings = settings
        self.repositories = repositories
        self.selector = selector
        self.reporter = reporter

    async def execute(
        self,
        *,
        report_path: Path,
        candidate_id: int,
        now_utc: datetime | None = None,
        now_local: datetime | None = None,
    ) -> PreviewSelectedResult:
        current_utc = now_utc or datetime.utcnow()
        current_local = now_local or datetime.utcnow()
        context, early_result = self._load_context(Path(report_path), candidate_id)
        if early_result is not None:
            return early_result
        assert context is not None

        inspection = self.selector.inspect_selection(current_utc, current_local)
        current_candidate = self.selector.find_selection_candidate(inspection, context.candidate_id)
        if current_candidate is None:
            return self._result(
                reason='candidate_not_found',
                status='failed',
                source_report_path=context.report_path,
                source_report_run_key=context.run_key,
                candidate_id=context.candidate_id,
                selected=self._selected_from_row(context.candidate_row),
                blocker_category='queue_state',
                blocker_detail=f'row_id={context.candidate_id} was not found in the current queue snapshot.',
            )

        mismatch_detail = self._snapshot_mismatch_detail(context.candidate_row, current_candidate)
        if mismatch_detail is not None:
            return self._result(
                reason='candidate_snapshot_mismatch',
                status='failed',
                source_report_path=context.report_path,
                source_report_run_key=context.run_key,
                candidate_id=context.candidate_id,
                selected=self._selected_from_snapshot(current_candidate),
                blocker_category='queue_state',
                blocker_detail=mismatch_detail,
            )

        selected_inspection, target = await self.selector.preview_selected_target(
            current_utc,
            current_local,
            context.candidate_id,
        )
        if not (target.truth_ready and target.would_send and target.candidate and target.artifact):
            failure_reason = self._normalize_failure_reason(target.blocker_reason)
            selected_payload = dict(target.candidate or self._selected_from_snapshot(current_candidate))
            image_path_raw = str((target.artifact or {}).get('image_path') or '').strip()
            return self._result(
                reason=failure_reason,
                status='failed',
                source_report_path=context.report_path,
                source_report_run_key=context.run_key,
                candidate_id=context.candidate_id,
                selected=selected_payload,
                truth_ready=bool(target.truth_ready),
                would_send=bool(target.would_send),
                blocker_category=target.blocker_category,
                blocker_detail=target.blocker_detail,
                caption_hash=(target.artifact or {}).get('caption_hash'),
                image_hash=(target.artifact or {}).get('image_hash'),
                image_path=Path(image_path_raw) if image_path_raw else None,
            )

        plan = self._queue_plan_from_repository(context)
        artifact = self.reporter.emit(
            now_utc=current_utc,
            mode='preview',
            settings=self.settings,
            plan=plan,
            selection=selected_inspection,
            target=target,
        )
        if artifact.json_path is None:
            return self._result(
                reason='report_write_failed',
                status='failed',
                source_report_path=context.report_path,
                source_report_run_key=context.run_key,
                candidate_id=context.candidate_id,
                selected=dict(target.candidate or {}),
                truth_ready=bool(target.truth_ready),
                would_send=bool(target.would_send),
                blocker_category='operator_report',
                blocker_detail='Operator truth report JSON could not be written.',
                caption_hash=(target.artifact or {}).get('caption_hash'),
                image_hash=(target.artifact or {}).get('image_hash'),
                image_path=Path(str((target.artifact or {}).get('image_path')))
                if str((target.artifact or {}).get('image_path') or '').strip()
                else None,
            )

        return PreviewSelectedResult(
            status='ok',
            reason='selected_preview_ready',
            created_report=True,
            source_report_path=context.report_path,
            source_report_run_key=context.run_key,
            report_path=artifact.json_path,
            report_payload=dict(artifact.payload_json or {}),
            candidate_id=context.candidate_id,
            selected=dict(target.candidate or {}),
            truth_ready=bool(target.truth_ready),
            would_send=bool(target.would_send),
            caption_hash=(target.artifact or {}).get('caption_hash'),
            image_hash=(target.artifact or {}).get('image_hash'),
            image_path=Path(str((target.artifact or {}).get('image_path')))
            if str((target.artifact or {}).get('image_path') or '').strip()
            else None,
        )

    def _load_context(
        self,
        report_path: Path,
        candidate_id: int,
    ) -> tuple[SelectedPreviewContext | None, PreviewSelectedResult | None]:
        resolved_report = report_path.resolve()
        if not resolved_report.exists():
            return None, self._result(
                reason='report_not_found',
                status='failed',
                source_report_path=resolved_report,
                candidate_id=candidate_id,
            )

        try:
            payload = json.loads(resolved_report.read_text(encoding='utf-8'))
        except OSError:
            return None, self._result(
                reason='report_not_found',
                status='failed',
                source_report_path=resolved_report,
                candidate_id=candidate_id,
            )
        except json.JSONDecodeError:
            return None, self._result(
                reason='report_invalid_json',
                status='failed',
                source_report_path=resolved_report,
                candidate_id=candidate_id,
            )

        if str(payload.get('mode') or '').strip() != 'preview':
            return None, self._result(
                reason='invalid_report_mode',
                status='failed',
                source_report_path=resolved_report,
                candidate_id=candidate_id,
            )
        if str(payload.get('scope') or '').strip() != 'live':
            return None, self._result(
                reason='invalid_report_scope',
                status='failed',
                source_report_path=resolved_report,
                candidate_id=candidate_id,
            )

        selection = dict(payload.get('selection') or {})
        candidate_rows = selection.get('candidate_rows')
        if not isinstance(candidate_rows, list) or not candidate_rows:
            return None, self._result(
                reason='candidate_rows_missing',
                status='failed',
                source_report_path=resolved_report,
                candidate_id=candidate_id,
            )

        report_run_key = str(payload.get('run_key') or '').strip()
        if not report_run_key:
            return None, self._result(
                reason='report_payload_invalid',
                status='failed',
                source_report_path=resolved_report,
                candidate_id=candidate_id,
            )

        candidate_row = self._find_candidate_row(candidate_rows, candidate_id)
        if candidate_row is None:
            return None, self._result(
                reason='candidate_not_found',
                status='failed',
                source_report_path=resolved_report,
                source_report_run_key=report_run_key,
                candidate_id=candidate_id,
            )

        candidate_row = dict(candidate_row)
        source_status = str(candidate_row.get('status') or '').strip().lower()
        if source_status not in self.ALLOWED_STATUSES:
            return None, self._result(
                reason=self._status_reason(source_status),
                status='failed',
                source_report_path=resolved_report,
                source_report_run_key=report_run_key,
                candidate_id=candidate_id,
                selected=self._selected_from_row(candidate_row),
                blocker_category=self._status_category(source_status),
                blocker_detail=self._status_detail(candidate_row),
            )

        return (
            SelectedPreviewContext(
                report_path=resolved_report,
                report_payload=payload,
                run_key=report_run_key,
                candidate_id=int(candidate_id),
                candidate_row=candidate_row,
            ),
            None,
        )

    @staticmethod
    def _find_candidate_row(candidate_rows: list[Any], candidate_id: int) -> dict[str, Any] | None:
        target = int(candidate_id)
        for row in candidate_rows:
            if not isinstance(row, dict):
                continue
            for key in ('candidate_id', 'row_id'):
                raw = row.get(key)
                if raw is None:
                    continue
                try:
                    if int(raw) == target:
                        return dict(row)
                except (TypeError, ValueError):
                    continue
        return None

    @staticmethod
    def _snapshot_mismatch_detail(
        source_row: dict[str, Any],
        current_candidate: SelectionCandidateSnapshot,
    ) -> str | None:
        comparisons: tuple[tuple[str, Any, Any], ...] = (
            ('row_id', source_row.get('row_id') or source_row.get('candidate_id'), current_candidate.row_id),
            ('offer_id', source_row.get('offer_id'), current_candidate.offer_id),
            ('bucket', source_row.get('bucket'), current_candidate.bucket),
            ('lane', source_row.get('lane'), current_candidate.lane),
            ('source', source_row.get('source'), current_candidate.source),
            ('title', source_row.get('title'), current_candidate.title),
            ('store_url', source_row.get('store_url'), current_candidate.store_url),
            ('created_at', source_row.get('created_at'), current_candidate.created_at),
            ('recommended_post_mode', source_row.get('recommended_post_mode'), current_candidate.recommended_post_mode),
        )
        for field_name, expected, actual in comparisons:
            expected_text = str(expected or '').strip()
            actual_text = str(actual or '').strip()
            if expected_text and expected_text != actual_text:
                return f'{field_name} mismatch: report={expected_text} current={actual_text}'
        return None

    def _queue_plan_from_repository(self, context: SelectedPreviewContext) -> QueuePlan:
        planned_records = self.repositories.list_queue('planned')
        reserve_records = self.repositories.list_queue('reserve')
        source_payload = dict(context.report_payload or {})
        queue_payload = dict(source_payload.get('queue') or {})
        selection_context = {
            'source': 'current_queue',
            'ingest_sources': dict(source_payload.get('ingest_sources') or {}),
            'selection_summary': {
                'capacity_hold': int(queue_payload.get('deferred_total') or 0),
            },
            'preview_selected': {
                'source_report_path': str(context.report_path),
                'source_report_run_key': context.run_key,
                'candidate_id': context.candidate_id,
            },
        }
        return QueuePlan(
            planned=[self._record_to_candidate(record) for record in planned_records],
            reserve=[self._record_to_candidate(record) for record in reserve_records],
            metrics={},
            context=selection_context,
        )

    @staticmethod
    def _record_to_candidate(record) -> PlannedCandidate:
        return PlannedCandidate(score=record.score, offer=record.offer, decision_json=record.decision_json)

    @staticmethod
    def _selected_from_row(candidate_row: dict[str, Any]) -> dict[str, Any]:
        return {
            'offer_id': candidate_row.get('offer_id'),
            'title': candidate_row.get('title'),
            'source': candidate_row.get('source'),
            'lane': candidate_row.get('lane'),
            'bucket': candidate_row.get('bucket'),
            'row_id': candidate_row.get('row_id') or candidate_row.get('candidate_id'),
            'status': candidate_row.get('status'),
        }

    @staticmethod
    def _selected_from_snapshot(candidate: SelectionCandidateSnapshot) -> dict[str, Any]:
        payload = candidate.to_snapshot()
        payload['status'] = candidate.operator_status()
        return payload

    @staticmethod
    def _normalize_failure_reason(reason: str | None) -> str:
        normalized = str(reason or '').strip().lower()
        if normalized == 'selected_candidate_blocked':
            return 'candidate_blocked'
        return normalized or 'selected_preview_failed'

    @staticmethod
    def _status_reason(status: str) -> str:
        if status == 'blocked':
            return 'candidate_blocked'
        return status or 'selected_preview_unsupported'

    @staticmethod
    def _status_category(status: str) -> str:
        if status == 'no_visual':
            return 'asset_localization'
        return 'queue_state'

    @staticmethod
    def _status_detail(candidate_row: dict[str, Any]) -> str:
        blocker_reason = str(candidate_row.get('blocker_reason') or '').strip()
        blocker_detail = str(candidate_row.get('blocker_detail') or '').strip()
        if blocker_reason and blocker_detail:
            return f'{blocker_reason}: {blocker_detail}'
        if blocker_detail:
            return blocker_detail
        if blocker_reason:
            return blocker_reason
        status = str(candidate_row.get('status') or '').strip()
        return status or 'unsupported candidate row'

    @staticmethod
    def _result(
        *,
        reason: str,
        status: str,
        source_report_path: Path | None = None,
        source_report_run_key: str | None = None,
        report_path: Path | None = None,
        report_payload: dict[str, Any] | None = None,
        candidate_id: int | None = None,
        selected: dict[str, Any] | None = None,
        truth_ready: bool = False,
        would_send: bool = False,
        blocker_category: str | None = None,
        blocker_detail: str | None = None,
        caption_hash: str | None = None,
        image_hash: str | None = None,
        image_path: Path | None = None,
    ) -> PreviewSelectedResult:
        return PreviewSelectedResult(
            status=status,
            reason=reason,
            created_report=report_path is not None,
            source_report_path=source_report_path,
            source_report_run_key=source_report_run_key,
            report_path=report_path,
            report_payload=dict(report_payload or {}),
            candidate_id=candidate_id,
            selected=dict(selected or {}),
            truth_ready=truth_ready,
            would_send=would_send,
            blocker_category=blocker_category,
            blocker_detail=blocker_detail,
            caption_hash=caption_hash,
            image_hash=image_hash,
            image_path=image_path,
        )
