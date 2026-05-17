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


@dataclass(slots=True)
class OutboxDeliveryResult:
    idempotency_key: str
    status_before: str
    reason: str
    published: bool
    message_id: int | None = None
    outbox_status: str | None = None


def load_outbox_payload(record: OutboxRecord) -> tuple[PostArtifact, Offer, str]:
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


async def finalize_outbox_sent_record(
    *,
    record: OutboxRecord,
    offer: Offer,
    lane: str,
    repositories: Repositories,
    now_local: datetime,
    logger: logging.Logger,
    metrics: Metrics | None = None,
) -> bool:
    try:
        repositories.finalize_publication(
            record.idempotency_key,
            offer,
            lane,
            now_local.date().isoformat(),
        )
    except sqlite3.Error as exc:
        logger.warning('Replay finalize failed for %s: %s', record.idempotency_key, exc)
        return False
    if metrics is not None:
        metrics.inc('outbox.replay.success')
    return True


async def deliver_outbox_record(
    *,
    record: OutboxRecord,
    repositories: Repositories,
    publisher: TelegramPublisher,
    now_utc: datetime,
    now_local: datetime,
    logger: logging.Logger,
    retry_backoff_minutes: int,
    metrics: Metrics | None = None,
) -> OutboxDeliveryResult:
    status_before = record.status

    if status_before == 'published':
        return OutboxDeliveryResult(
            idempotency_key=record.idempotency_key,
            status_before=status_before,
            reason='already_published',
            published=True,
            message_id=record.telegram_message_id,
            outbox_status='published',
        )

    try:
        artifact, offer, lane = load_outbox_payload(record)
    except (ValueError, KeyError, TypeError) as exc:
        repositories.mark_outbox_failed(
            record.idempotency_key,
            f'invalid_payload:{exc}',
            now_utc + timedelta(minutes=retry_backoff_minutes),
        )
        return OutboxDeliveryResult(
            idempotency_key=record.idempotency_key,
            status_before=status_before,
            reason='invalid_payload',
            published=False,
            outbox_status='failed',
        )

    if status_before == 'sent':
        finalized = await finalize_outbox_sent_record(
            record=record,
            offer=offer,
            lane=lane,
            repositories=repositories,
            now_local=now_local,
            logger=logger,
            metrics=metrics,
        )
        return OutboxDeliveryResult(
            idempotency_key=record.idempotency_key,
            status_before=status_before,
            reason='finalized_sent' if finalized else 'db_finalize_failed',
            published=finalized,
            message_id=record.telegram_message_id,
            outbox_status='published' if finalized else 'sent',
        )

    if status_before not in {'pending', 'failed', 'sending'}:
        return OutboxDeliveryResult(
            idempotency_key=record.idempotency_key,
            status_before=status_before,
            reason='unsupported_status',
            published=False,
            message_id=record.telegram_message_id,
            outbox_status=status_before,
        )

    image_path = record.image_path
    if image_path is None or not Path(image_path).exists():
        repositories.mark_outbox_failed(
            record.idempotency_key,
            'image_missing',
            now_utc + timedelta(minutes=retry_backoff_minutes),
        )
        return OutboxDeliveryResult(
            idempotency_key=record.idempotency_key,
            status_before=status_before,
            reason='image_missing',
            published=False,
            outbox_status='failed',
        )

    try:
        repositories.mark_outbox_sending(record.idempotency_key)
    except sqlite3.Error as exc:
        logger.warning('Replay could not claim outbox send for %s: %s', record.idempotency_key, exc)
        return OutboxDeliveryResult(
            idempotency_key=record.idempotency_key,
            status_before=status_before,
            reason='db_claim_failed',
            published=False,
            message_id=record.telegram_message_id,
            outbox_status=status_before,
        )

    try:
        message = await publisher.publish_photo(image_path, artifact.caption_html)
    except Exception as exc:
        try:
            repositories.mark_outbox_failed(
                record.idempotency_key,
                str(exc),
                now_utc + timedelta(minutes=retry_backoff_minutes),
            )
        except sqlite3.Error as db_exc:
            logger.warning('Replay could not persist failed state for %s: %s', record.idempotency_key, db_exc)
        logger.warning('Replay delivery failed for %s: %s', record.idempotency_key, exc)
        return OutboxDeliveryResult(
            idempotency_key=record.idempotency_key,
            status_before=status_before,
            reason='publish_failed',
            published=False,
            outbox_status='failed',
        )

    try:
        repositories.mark_outbox_sent(record.idempotency_key, message.message_id)
    except sqlite3.Error as exc:
        logger.warning('Replay could not persist sent state for %s: %s', record.idempotency_key, exc)
        return OutboxDeliveryResult(
            idempotency_key=record.idempotency_key,
            status_before=status_before,
            reason='db_mark_sent_failed',
            published=False,
            message_id=message.message_id,
            outbox_status='sending',
        )

    finalized = await finalize_outbox_sent_record(
        record=record,
        offer=offer,
        lane=lane,
        repositories=repositories,
        now_local=now_local,
        logger=logger,
        metrics=metrics,
    )
    return OutboxDeliveryResult(
        idempotency_key=record.idempotency_key,
        status_before=status_before,
        reason='published' if finalized else 'db_finalize_failed',
        published=finalized,
        message_id=message.message_id,
        outbox_status='published' if finalized else 'sent',
    )


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
            delivery = await deliver_outbox_record(
                record=record,
                repositories=self.repositories,
                publisher=self.publisher,
                now_utc=now_utc,
                now_local=now_local,
                logger=self.logger,
                retry_backoff_minutes=self.RETRY_BACKOFF_MINUTES,
                metrics=self.metrics,
            )
            if delivery.reason in {'already_published', 'unsupported_status'}:
                skipped += 1
            elif delivery.published:
                published += 1
            else:
                failed += 1
            results.append(
                ReplayAttemptResult(
                    delivery.idempotency_key,
                    delivery.status_before,
                    delivery.reason,
                    delivery.published,
                    delivery.message_id,
                )
            )

        return ReplaySummary(
            attempted=len(candidates),
            published=published,
            failed=failed,
            skipped=skipped,
            results=results,
        )
