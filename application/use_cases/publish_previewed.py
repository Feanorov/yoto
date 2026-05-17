from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from domain.entities.analytics_artifact import AnalyticsArtifact
from domain.entities.offer import Offer
from domain.entities.post_artifact import PostArtifact
from infrastructure.analytics.artifact_writer import AnalyticsArtifactWriter
from infrastructure.db.repositories import OutboxPayloadConflictError, Repositories
from infrastructure.telegram.publisher import TelegramPublisher

from .operator_truth_report import PINNED_PUBLISH_CONTRACT_VERSION
from .replay_outbox import deliver_outbox_record


@dataclass(slots=True)
class PublishPreviewedResult:
    status: str
    reason: str
    published: bool
    message_id: int | None = None
    outbox_status: str | None = None
    source_report_path: Path | None = None
    source_report_run_key: str | None = None
    selected: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None
    caption_hash: str | None = None
    image_hash: str | None = None
    image_path: Path | None = None
    publish_outcome_path: Path | None = None


@dataclass(slots=True)
class PinnedPreviewContext:
    report_path: Path
    report_payload: dict[str, Any]
    run_key: str
    candidate: dict[str, Any]
    offer_snapshot: dict[str, Any]
    decision_snapshot: dict[str, Any]
    offer: Offer
    artifact: PostArtifact
    image_path: Path
    source_report_path: str

    @property
    def lane(self) -> str:
        return str(self.decision_snapshot.get('lane') or '').strip()

    @property
    def offer_id(self) -> str:
        return self.artifact.offer_id

    @property
    def title(self) -> str:
        return str(self.candidate.get('title') or self.offer.title or '').strip()


class PublishPreviewedUseCase:
    SUPPORTED_CONTRACT_VERSION = PINNED_PUBLISH_CONTRACT_VERSION

    def __init__(
        self,
        repositories: Repositories,
        publisher: TelegramPublisher,
        writer: AnalyticsArtifactWriter,
    ) -> None:
        self.repositories = repositories
        self.publisher = publisher
        self.writer = writer
        self.logger = logging.getLogger(__name__)

    async def execute(
        self,
        *,
        report_path: Path,
        now_utc: datetime | None = None,
        now_local: datetime | None = None,
    ) -> PublishPreviewedResult:
        current_utc = now_utc or datetime.utcnow()
        current_local = now_local or datetime.utcnow()
        context, early_result = self._load_context(Path(report_path))
        if early_result is not None:
            return early_result
        assert context is not None

        staged_outbox_status: str | None = None
        staged_message_id: int | None = None
        final_reason = 'db_stage_failed'
        final_published = False
        final_outbox_status: str | None = None
        final_message_id: int | None = None
        try:
            staged = self.repositories.stage_pinned_outbox_delivery(
                artifact=context.artifact,
                image_path=context.image_path,
                offer_snapshot=context.offer_snapshot,
                decision_json=context.decision_snapshot,
                meta={
                    'source_report_path': context.source_report_path,
                    'source_report_run_key': context.run_key,
                    'contract_version': self.SUPPORTED_CONTRACT_VERSION,
                },
            )
            staged_outbox_status = staged.status
            staged_message_id = staged.telegram_message_id
        except OutboxPayloadConflictError:
            final_reason = 'idempotency_conflict'
            final_outbox_status = self._load_outbox_status(context.artifact.idempotency_key)
        except Exception as exc:
            self.logger.warning('Pinned outbox staging failed for %s: %s', context.offer_id, exc)
            final_reason = 'db_stage_failed'
            final_outbox_status = self._load_outbox_status(context.artifact.idempotency_key)
        else:
            try:
                delivery = await deliver_outbox_record(
                    record=staged,
                    repositories=self.repositories,
                    publisher=self.publisher,
                    now_utc=current_utc,
                    now_local=current_local,
                    logger=self.logger,
                    retry_backoff_minutes=15,
                    metrics=None,
                )
            except Exception as exc:
                self.logger.warning('Pinned publish delivery failed unexpectedly for %s: %s', context.offer_id, exc)
                final_reason = 'publish_failed'
                final_outbox_status = self._load_outbox_status(context.artifact.idempotency_key)
            else:
                final_reason = delivery.reason
                final_published = delivery.published
                final_outbox_status = delivery.outbox_status
                final_message_id = delivery.message_id

        if final_outbox_status is None:
            final_outbox_status = staged_outbox_status
        if final_message_id is None:
            final_message_id = staged_message_id

        result = self._result_from_context(
            context,
            reason=final_reason,
            published=final_published,
            outbox_status=final_outbox_status,
            message_id=final_message_id,
        )
        result.publish_outcome_path = self._write_publish_outcome(context, result, now_utc=current_utc)
        result.status = 'ok' if result.published else 'failed'
        return result

    def _load_context(self, report_path: Path) -> tuple[PinnedPreviewContext | None, PublishPreviewedResult | None]:
        resolved_report = report_path.resolve()
        if not resolved_report.exists():
            return None, self._result(reason='report_not_found', status='failed', source_report_path=resolved_report)

        try:
            payload = json.loads(resolved_report.read_text(encoding='utf-8'))
        except OSError:
            return None, self._result(reason='report_not_found', status='failed', source_report_path=resolved_report)
        except json.JSONDecodeError:
            return None, self._result(reason='report_invalid_json', status='failed', source_report_path=resolved_report)

        if str(payload.get('mode') or '').strip() != 'preview':
            return None, self._result(reason='invalid_report_mode', status='failed', source_report_path=resolved_report)
        if str(payload.get('scope') or '').strip() != 'live':
            return None, self._result(reason='invalid_report_scope', status='failed', source_report_path=resolved_report)
        if self._is_stale_report(resolved_report):
            return None, self._result(reason='stale_preview_report', status='failed', source_report_path=resolved_report)

        verdict = dict(payload.get('verdict') or {})
        if not bool(verdict.get('truth_ready')):
            return None, self._result(reason='truth_not_ready', status='failed', source_report_path=resolved_report)

        target = dict(payload.get('send_test_target') or {})
        if not bool(target.get('would_send')):
            return None, self._result(reason='would_send_false', status='failed', source_report_path=resolved_report)

        pinned_publish = dict(payload.get('pinned_publish') or {})
        if not pinned_publish:
            return None, self._result(reason='pinned_publish_missing', status='failed', source_report_path=resolved_report)
        if int(pinned_publish.get('contract_version') or 0) != self.SUPPORTED_CONTRACT_VERSION:
            return None, self._result(reason='unsupported_contract_version', status='failed', source_report_path=resolved_report)
        if str(pinned_publish.get('source') or '').strip() != 'preview':
            return None, self._result(reason='pinned_payload_incomplete', status='failed', source_report_path=resolved_report)

        report_run_key = str(payload.get('run_key') or '').strip()
        if not report_run_key or str(pinned_publish.get('report_run_key') or '').strip() != report_run_key:
            return None, self._result(reason='report_payload_mismatch', status='failed', source_report_path=resolved_report)

        candidate = dict(pinned_publish.get('candidate') or {})
        offer_snapshot = dict(pinned_publish.get('offer_snapshot') or {})
        decision_snapshot = dict(pinned_publish.get('decision_snapshot') or {})
        pinned_artifact = dict(pinned_publish.get('artifact') or {})
        if not candidate or not offer_snapshot or not decision_snapshot or not pinned_artifact:
            return None, self._result(reason='pinned_payload_incomplete', status='failed', source_report_path=resolved_report)

        target_candidate = dict(target.get('candidate') or {})
        target_artifact = dict(target.get('artifact') or {})
        if not self._matches_target(candidate, offer_snapshot, target_candidate, pinned_artifact, target_artifact):
            return None, self._result(
                reason='report_payload_mismatch',
                status='failed',
                source_report_path=resolved_report,
                selected={'offer_id': str(candidate.get('offer_id') or '')},
            )

        caption_html = str(pinned_artifact.get('caption_html') or '')
        caption_hash = str(pinned_artifact.get('caption_hash') or '')
        image_path_raw = str(pinned_artifact.get('image_path') or '').strip()
        image_hash = str(pinned_artifact.get('image_hash') or '')
        idempotency_key = str(pinned_artifact.get('idempotency_key') or '').strip()
        template_id = str(pinned_artifact.get('template_id') or '').strip()
        if not caption_html or not caption_hash or not image_path_raw or not image_hash or not idempotency_key or not template_id:
            return None, self._result(reason='pinned_payload_incomplete', status='failed', source_report_path=resolved_report)

        if self._sha256_text(caption_html) != caption_hash:
            return None, self._result(
                reason='caption_hash_mismatch',
                status='failed',
                source_report_path=resolved_report,
                selected={'offer_id': str(candidate.get('offer_id') or '')},
                idempotency_key=idempotency_key,
                caption_hash=caption_hash,
                image_hash=image_hash,
                image_path=Path(image_path_raw),
            )

        image_path = Path(image_path_raw)
        if not image_path.exists():
            return None, self._result(
                reason='image_missing',
                status='failed',
                source_report_path=resolved_report,
                selected={'offer_id': str(candidate.get('offer_id') or '')},
                idempotency_key=idempotency_key,
                caption_hash=caption_hash,
                image_hash=image_hash,
                image_path=image_path,
            )
        if self._sha256_file(image_path) != image_hash:
            return None, self._result(
                reason='image_hash_mismatch',
                status='failed',
                source_report_path=resolved_report,
                selected={'offer_id': str(candidate.get('offer_id') or '')},
                idempotency_key=idempotency_key,
                caption_hash=caption_hash,
                image_hash=image_hash,
                image_path=image_path,
            )

        lane = str(decision_snapshot.get('lane') or '').strip()
        if not lane:
            return None, self._result(
                reason='pinned_payload_incomplete',
                status='failed',
                source_report_path=resolved_report,
                selected={'offer_id': str(candidate.get('offer_id') or '')},
                idempotency_key=idempotency_key,
                caption_hash=caption_hash,
                image_hash=image_hash,
                image_path=image_path,
            )

        artifact = PostArtifact(
            offer_id=str(pinned_artifact.get('offer_id') or offer_snapshot.get('offer_id') or ''),
            caption_html=caption_html,
            hashtags=[],
            template_id=template_id,
            render_inputs={'offer': offer_snapshot, 'decision': decision_snapshot},
            assets_used=list(pinned_artifact.get('assets_used') or []),
            idempotency_key=idempotency_key,
            caption_hash=caption_hash,
            image_hash=image_hash,
            render_diagnostics=dict(pinned_artifact.get('render_diagnostics') or {}),
            decision_debug={'caption': dict(pinned_artifact.get('caption_debug') or {})},
        )
        try:
            offer = Offer.from_snapshot(offer_snapshot)
        except Exception:
            return None, self._result(
                reason='pinned_payload_incomplete',
                status='failed',
                source_report_path=resolved_report,
                selected={'offer_id': str(candidate.get('offer_id') or '')},
                idempotency_key=idempotency_key,
                caption_hash=caption_hash,
                image_hash=image_hash,
                image_path=image_path,
            )

        return (
            PinnedPreviewContext(
                report_path=resolved_report,
                report_payload=payload,
                run_key=report_run_key,
                candidate=candidate,
                offer_snapshot=offer_snapshot,
                decision_snapshot=decision_snapshot,
                offer=offer,
                artifact=artifact,
                image_path=image_path,
                source_report_path=str(resolved_report),
            ),
            None,
        )

    def _write_publish_outcome(
        self,
        context: PinnedPreviewContext,
        result: PublishPreviewedResult,
        *,
        now_utc: datetime,
    ) -> Path | None:
        payload = self._publish_outcome_payload(context, result, now_utc=now_utc)
        artifact = AnalyticsArtifact(
            artifact_type='publish_outcome',
            subject_id=context.offer_id,
            run_key=now_utc.strftime('%Y%m%dT%H%M%SZ'),
            created_at=now_utc,
            payload_json=payload,
            summary_rows=[
                {
                    'artifact_type': 'publish_outcome',
                    'offer_id': context.offer_id,
                    'title': context.title,
                    'lane': context.lane,
                    'published': result.published,
                    'reason': result.reason,
                    'message_id': result.message_id,
                    'idempotency_key': context.artifact.idempotency_key,
                    'caption_hash': context.artifact.caption_hash,
                    'image_hash': context.artifact.image_hash,
                    'source_report_run_key': context.run_key,
                }
            ],
        )
        try:
            artifact.json_path, artifact.csv_path = self.writer.write(artifact)
            self.repositories.save_analytics_artifact(artifact)
        except Exception as exc:
            self.logger.warning('Pinned publish outcome write failed for %s: %s', context.offer_id, exc)
            return None
        return artifact.json_path

    def _publish_outcome_payload(
        self,
        context: PinnedPreviewContext,
        result: PublishPreviewedResult,
        *,
        now_utc: datetime,
    ) -> dict[str, Any]:
        return {
            'run_key': now_utc.strftime('%Y%m%dT%H%M%SZ'),
            'created_at': now_utc.isoformat(),
            'offer_id': context.offer_id,
            'title': context.title,
            'lane': context.lane,
            'published': result.published,
            'reason': result.reason,
            'message_id': result.message_id,
            'image_path': str(context.image_path),
            'selection': {
                'offer_id': context.offer_id,
                'title': context.title,
                'source': context.candidate.get('source'),
                'lane': context.candidate.get('lane'),
                'bucket': context.candidate.get('bucket'),
                'row_id': context.candidate.get('row_id'),
                'source_report_path': context.source_report_path,
                'source_report_run_key': context.run_key,
            },
            'render': {
                'image_path': str(context.image_path),
                'template_id': context.artifact.template_id,
                'assets_used': list(context.artifact.assets_used),
                'caption_hash': context.artifact.caption_hash,
                'image_hash': context.artifact.image_hash,
                'idempotency_key': context.artifact.idempotency_key,
                'render_diagnostics': dict(context.artifact.render_diagnostics or {}),
                'caption_debug': dict((context.artifact.decision_debug or {}).get('caption') or {}),
            },
            'publish_outcome': {
                'published': result.published,
                'reason': result.reason,
                'message_id': result.message_id,
                'outbox_status': result.outbox_status,
                'failure_detail': None if result.published else result.reason,
                'idempotency_key': context.artifact.idempotency_key,
                'caption_hash': context.artifact.caption_hash,
                'image_hash': context.artifact.image_hash,
                'source_report_path': context.source_report_path,
                'source_report_run_key': context.run_key,
            },
        }

    @staticmethod
    def _matches_target(
        candidate: dict[str, Any],
        offer_snapshot: dict[str, Any],
        target_candidate: dict[str, Any],
        pinned_artifact: dict[str, Any],
        target_artifact: dict[str, Any],
    ) -> bool:
        expected_offer_id = str(candidate.get('offer_id') or offer_snapshot.get('offer_id') or '').strip()
        if not expected_offer_id or expected_offer_id != str(target_candidate.get('offer_id') or '').strip():
            return False
        comparisons = (
            ('caption_hash', pinned_artifact, target_artifact),
            ('image_path', pinned_artifact, target_artifact),
            ('image_hash', pinned_artifact, target_artifact),
            ('idempotency_key', pinned_artifact, target_artifact),
        )
        for key, left_source, right_source in comparisons:
            if str(left_source.get(key) or '').strip() != str(right_source.get(key) or '').strip():
                return False
        return True

    @staticmethod
    def _sha256_text(value: str) -> str:
        return hashlib.sha256(str(value or '').encode('utf-8')).hexdigest()

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open('rb') as handle:
            for chunk in iter(lambda: handle.read(8192), b''):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _sort_key(path: Path) -> tuple[float, str]:
        return (path.stat().st_mtime, str(path))

    def _is_stale_report(self, report_path: Path) -> bool:
        analytics_dir = report_path.parent
        if not analytics_dir.exists():
            return False
        candidates = [path for path in analytics_dir.rglob('*_operator_truth_report_preview.json') if path.is_file()]
        if not candidates:
            return False
        latest = max(candidates, key=self._sort_key)
        return latest.resolve() != report_path.resolve() and self._sort_key(latest) > self._sort_key(report_path)

    def _load_outbox_status(self, idempotency_key: str) -> str | None:
        record = self.repositories.get_outbox_record(idempotency_key)
        return record.status if record is not None else None

    def _result_from_context(
        self,
        context: PinnedPreviewContext,
        *,
        reason: str,
        published: bool,
        outbox_status: str | None,
        message_id: int | None,
    ) -> PublishPreviewedResult:
        return PublishPreviewedResult(
            status='ok' if published else 'failed',
            reason=reason,
            published=published,
            message_id=message_id,
            outbox_status=outbox_status,
            source_report_path=context.report_path,
            source_report_run_key=context.run_key,
            selected={
                'offer_id': context.offer_id,
                'title': context.title,
                'source': context.candidate.get('source'),
                'lane': context.candidate.get('lane'),
                'bucket': context.candidate.get('bucket'),
                'row_id': context.candidate.get('row_id'),
            },
            idempotency_key=context.artifact.idempotency_key,
            caption_hash=context.artifact.caption_hash,
            image_hash=context.artifact.image_hash,
            image_path=context.image_path,
        )

    @staticmethod
    def _result(
        *,
        reason: str,
        status: str,
        source_report_path: Path | None = None,
        selected: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        caption_hash: str | None = None,
        image_hash: str | None = None,
        image_path: Path | None = None,
    ) -> PublishPreviewedResult:
        return PublishPreviewedResult(
            status=status,
            reason=reason,
            published=False,
            source_report_path=source_report_path,
            selected=dict(selected or {}),
            idempotency_key=idempotency_key,
            caption_hash=caption_hash,
            image_hash=image_hash,
            image_path=image_path,
        )
