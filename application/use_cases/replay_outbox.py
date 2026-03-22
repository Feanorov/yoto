from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from pathlib import Path
import sqlite3

from domain.entities.offer import Offer
from domain.entities.post_artifact import PostArtifact
from infrastructure.db.repositories import OutboxRecord, Repositories
from infrastructure.observability.metrics import Metrics
from infrastructure.telegram.publisher import TelegramPublisher


@dataclass(slots=True)
class ReplayAttemptResult:
    idempotency_key: str
    status_before: str
    reason: str
    published: bool
    message_id: int | None = None


@dataclass(slots=True)
class ReplaySummary:
    attempted: int
    published: int
    failed: int
    skipped: int
    results: list[ReplayAttemptResult] = field(default_factory=list)


class ReplayOutboxUseCase:
    RETRY_BACKOFF_MINUTES = 15
    STALE_SENDING_SECONDS = 30 * 60

    def __init__(
        self,
        repositories: Repositories,
        publisher: TelegramPublisher,
        metrics: Metrics | None = None,
    ) -> None:
        self.repositories = repositories
        self.publisher = publisher
        self.metrics = metrics or Metrics()
        self.logger = logging.getLogger(__name__)

    async def execute(self, now_utc: datetime, now_local: datetime, limit: int = 10) -> ReplaySummary:
        candidates = self.repositories.list_outbox_replay_ready(
            now_utc=now_utc,
            limit=limit,
            stale_after_seconds=self.STALE_SENDING_SECONDS,
        )
        results: list[ReplayAttemptResult] = []
        published = 0
        failed = 0
        skipped = 0

        for record in candidates:
            status_before = record.status

            if status_before == 'published':
                skipped += 1
                results.append(ReplayAttemptResult(record.idempotency_key, status_before, 'already_published', False, record.telegram_message_id))
                continue

            try:
                artifact, offer, lane = self._load_replay_payload(record)
            except (ValueError, KeyError, TypeError) as exc:
                failed += 1
                self.repositories.mark_outbox_failed(
                    record.idempotency_key,
                    f'invalid_payload:{exc}',
                    now_utc + timedelta(minutes=self.RETRY_BACKOFF_MINUTES),
                )
                results.append(ReplayAttemptResult(record.idempotency_key, status_before, 'invalid_payload', False))
                continue

            if status_before == 'sent':
                finalized = await self._finalize_sent(record, offer, lane, now_local)
                if finalized:
                    published += 1
                    results.append(
                        ReplayAttemptResult(record.idempotency_key, status_before, 'finalized_sent', True, record.telegram_message_id)
                    )
                else:
                    failed += 1
                    results.append(
                        ReplayAttemptResult(record.idempotency_key, status_before, 'db_finalize_failed', False, record.telegram_message_id)
                    )
                continue

            if status_before not in {'pending', 'failed', 'sending'}:
                skipped += 1
                results.append(ReplayAttemptResult(record.idempotency_key, status_before, 'unsupported_status', False, record.telegram_message_id))
                continue

            image_path = record.image_path
            if image_path is None or not Path(image_path).exists():
                failed += 1
                self.repositories.mark_outbox_failed(
                    record.idempotency_key,
                    'image_missing',
                    now_utc + timedelta(minutes=self.RETRY_BACKOFF_MINUTES),
                )
                results.append(ReplayAttemptResult(record.idempotency_key, status_before, 'image_missing', False))
                continue

            try:
                self.repositories.mark_outbox_sending(record.idempotency_key)
                message = await self.publisher.publish_photo(image_path, artifact.caption_html)
            except Exception as exc:
                failed += 1
                self.repositories.mark_outbox_failed(
                    record.idempotency_key,
                    str(exc),
                    now_utc + timedelta(minutes=self.RETRY_BACKOFF_MINUTES),
                )
                self.logger.warning('Replay delivery failed for %s: %s', record.idempotency_key, exc)
                results.append(ReplayAttemptResult(record.idempotency_key, status_before, 'publish_failed', False))
                continue

            try:
                self.repositories.mark_outbox_sent(record.idempotency_key, message.message_id)
            except sqlite3.Error as exc:
                failed += 1
                self.logger.warning('Replay could not persist sent state for %s: %s', record.idempotency_key, exc)
                results.append(ReplayAttemptResult(record.idempotency_key, status_before, 'db_mark_sent_failed', False, message.message_id))
                continue

            finalized = await self._finalize_sent(record, offer, lane, now_local)
            if finalized:
                published += 1
                results.append(ReplayAttemptResult(record.idempotency_key, status_before, 'published', True, message.message_id))
            else:
                failed += 1
                results.append(ReplayAttemptResult(record.idempotency_key, status_before, 'db_finalize_failed', False, message.message_id))

        return ReplaySummary(
            attempted=len(candidates),
            published=published,
            failed=failed,
            skipped=skipped,
            results=results,
        )

    async def _finalize_sent(self, record: OutboxRecord, offer: Offer, lane: str, now_local: datetime) -> bool:
        try:
            self.repositories.finalize_publication(
                record.idempotency_key,
                offer,
                lane,
                now_local.date().isoformat(),
            )
        except sqlite3.Error as exc:
            self.logger.warning('Replay finalize failed for %s: %s', record.idempotency_key, exc)
            return False
        self.metrics.inc('outbox.replay.success')
        return True

    def _load_replay_payload(self, record: OutboxRecord) -> tuple[PostArtifact, Offer, str]:
        payload = record.payload_json or {}
        artifact_snapshot = payload.get('artifact')
        offer_snapshot = payload.get('offer')
        decision_json = payload.get('decision')

        if not isinstance(artifact_snapshot, dict):
            raise ValueError('artifact snapshot missing')
        if not isinstance(offer_snapshot, dict):
            raise ValueError('offer snapshot missing')
        if not isinstance(decision_json, dict):
            raise ValueError('decision snapshot missing')

        lane = str(decision_json.get('lane') or '').strip()
        if not lane:
            raise ValueError('decision lane missing')

        artifact = PostArtifact(**artifact_snapshot)
        offer = Offer.from_snapshot(offer_snapshot)
        return artifact, offer, lane