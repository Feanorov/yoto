from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3

from domain.entities.analytics_artifact import AnalyticsArtifact
from domain.entities.offer import Offer
from domain.entities.post_artifact import PostArtifact
from domain.entities.video_manifest import VideoManifest
from domain.policies.dedup_policy import PublicationRecord
from infrastructure.db.migrations import apply_migrations


@dataclass(slots=True)
class QueueRecord:
    row_id: int
    bucket: str
    lane: str
    score: float
    offer: Offer
    decision_json: dict
    created_at: datetime


@dataclass(slots=True)
class OutboxRecord:
    idempotency_key: str
    caption_hash: str
    image_hash: str
    image_path: Path | None
    telegram_message_id: int | None
    published_at: datetime | None
    payload_json: dict
    status: str
    attempt_count: int
    last_error: str | None
    next_attempt_at: datetime | None
    claimed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class OutboxPayloadConflictError(RuntimeError):
    """Raised when an existing outbox row does not match the requested exact payload."""


class Repositories:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            apply_migrations(connection)

    def reset(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                DELETE FROM publication_history;
                DELETE FROM franchise_history;
                DELETE FROM queue_items;
                DELETE FROM publish_outbox;
                DELETE FROM post_artifacts;
                DELETE FROM analytics_artifacts;
                DELETE FROM video_manifests;
                DELETE FROM daily_lane_usage;
                """
            )

    def get_game_history(self, game_id: str) -> PublicationRecord | None:
        with self.connect() as connection:
            row = connection.execute('SELECT * FROM publication_history WHERE game_id = ?', (game_id,)).fetchone()
        if row is None:
            return None
        return PublicationRecord(
            game_id=row['game_id'],
            franchise_key=row['franchise_key'],
            source=row['source'],
            posted_at=datetime.fromisoformat(row['posted_at']),
            price_after_minor=row['price_after_minor'],
            discount_percent=row['discount_percent'],
            lane=row['lane'],
            promo_end=datetime.fromisoformat(row['promo_end']) if row['promo_end'] else None,
            best_price_minor=row['best_price_minor'],
        )

    def get_franchise_history(self, franchise_key: str) -> PublicationRecord | None:
        with self.connect() as connection:
            row = connection.execute(
                'SELECT franchise_key, posted_at, source FROM franchise_history WHERE franchise_key = ?',
                (franchise_key,),
            ).fetchone()
        if row is None:
            return None
        return PublicationRecord(
            game_id='',
            franchise_key=row['franchise_key'],
            source=row['source'],
            posted_at=datetime.fromisoformat(row['posted_at']),
            price_after_minor=None,
            discount_percent=0,
            lane='',
            promo_end=None,
            best_price_minor=None,
        )

    def get_daily_lane_count(self, day_key: str, lane: str) -> int:
        with self.connect() as connection:
            row = connection.execute(
                'SELECT count FROM daily_lane_usage WHERE day_key = ? AND lane = ?',
                (day_key, lane),
            ).fetchone()
        return int(row['count']) if row else 0

    def increment_daily_lane(self, day_key: str, lane: str) -> None:
        with self.connect() as connection:
            self._increment_daily_lane(connection, day_key, lane)

    def replace_queue(
        self,
        bucket: str,
        rows: list[tuple[float, Offer, dict]],
        *,
        created_at: datetime | str | None = None,
    ) -> None:
        if isinstance(created_at, datetime):
            now = created_at.isoformat()
        elif isinstance(created_at, str) and created_at:
            now = created_at
        else:
            now = datetime.utcnow().isoformat()
        with self.connect() as connection:
            connection.execute('DELETE FROM queue_items WHERE bucket = ?', (bucket,))
            for score, offer, decision_json in rows:
                connection.execute(
                    'INSERT INTO queue_items(bucket, lane, score, offer_json, decision_json, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                    (
                        bucket,
                        decision_json['lane'],
                        score,
                        json.dumps(offer.to_snapshot(), ensure_ascii=False),
                        json.dumps(decision_json, ensure_ascii=False),
                        now,
                    ),
                )

    def list_queue(self, bucket: str) -> list[QueueRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                'SELECT * FROM queue_items WHERE bucket = ? ORDER BY id ASC',
                (bucket,),
            ).fetchall()
        return [self._row_to_queue_record(row) for row in rows]

    def peek_next_for_publish(self, allow_reserve: bool) -> QueueRecord | None:
        planned = self.list_queue('planned')
        if planned:
            return planned[0]
        if not allow_reserve:
            return None
        reserve = self.list_queue('reserve')
        return reserve[0] if reserve else None

    def delete_queue_item(self, row_id: int) -> None:
        with self.connect() as connection:
            connection.execute('DELETE FROM queue_items WHERE id = ?', (row_id,))

    def pop_next_for_publish(self, allow_reserve: bool) -> QueueRecord | None:
        record = self.peek_next_for_publish(allow_reserve=allow_reserve)
        if record is None:
            return None
        self.delete_queue_item(record.row_id)
        return record

    def save_post_artifact(self, artifact: PostArtifact, lane: str) -> None:
        with self.connect() as connection:
            self._save_post_artifact(connection, artifact, lane, datetime.utcnow().isoformat())

    def get_outbox_record(self, idempotency_key: str) -> OutboxRecord | None:
        with self.connect() as connection:
            row = connection.execute(
                'SELECT * FROM publish_outbox WHERE idempotency_key = ?',
                (idempotency_key,),
            ).fetchone()
        return self._row_to_outbox_record(row)

    def save_analytics_artifact(self, artifact: AnalyticsArtifact) -> None:
        with self.connect() as connection:
            connection.execute(
                'INSERT INTO analytics_artifacts(artifact_type, subject_id, run_key, json_path, csv_path, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (
                    artifact.artifact_type,
                    artifact.subject_id,
                    artifact.run_key,
                    str(artifact.json_path) if artifact.json_path else None,
                    str(artifact.csv_path) if artifact.csv_path else None,
                    json.dumps(artifact.payload_json, ensure_ascii=False, sort_keys=True),
                    artifact.created_at.isoformat(),
                ),
            )

    def list_recent_roundup_snapshots(self, limit: int = 5) -> list[dict]:
        if limit <= 0:
            return []
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT subject_id, run_key, json_path, payload_json, created_at
                FROM analytics_artifacts
                WHERE artifact_type = 'roundup_snapshot'
                  AND subject_id = 'roundups'
                ORDER BY created_at DESC
                """
            ).fetchall()

        snapshots: list[dict] = []
        for row in rows:
            try:
                payload = json.loads(row['payload_json'])
            except (TypeError, json.JSONDecodeError):
                continue
            if not self._is_editorial_roundup_snapshot(row['json_path'], payload):
                continue

            snapshot = dict(payload)
            snapshot.setdefault('run_key', row['run_key'])
            snapshot.setdefault('created_at', row['created_at'])
            snapshots.append(snapshot)
            if len(snapshots) >= limit:
                break
        return snapshots

    def get_latest_publishable_roundup_snapshot(self, queue_snapshot_at: str | None) -> dict | None:
        normalized_window = self._normalize_roundup_window_key(queue_snapshot_at)
        if normalized_window is None:
            return None
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, subject_id, run_key, json_path, payload_json, created_at
                FROM analytics_artifacts
                WHERE artifact_type = 'roundup_snapshot'
                  AND subject_id = 'roundups'
                ORDER BY created_at DESC, id DESC
                """
            ).fetchall()

        for row in rows:
            try:
                payload = json.loads(row['payload_json'])
            except (TypeError, json.JSONDecodeError):
                continue
            if not self._is_editorial_roundup_snapshot(row['json_path'], payload):
                continue
            context = payload.get('context') or {}
            if not isinstance(context, dict):
                continue
            if self._normalize_roundup_window_key(context.get('queue_snapshot_at')) != normalized_window:
                continue
            snapshot = dict(payload)
            snapshot.setdefault('run_key', row['run_key'])
            snapshot.setdefault('created_at', row['created_at'])
            snapshot.setdefault('json_path', row['json_path'])
            return snapshot
        return None

    def get_latest_canonical_roundup_snapshot(self) -> dict | None:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, subject_id, run_key, json_path, payload_json, created_at
                FROM analytics_artifacts
                WHERE artifact_type = 'roundup_snapshot'
                  AND subject_id = 'roundups'
                ORDER BY created_at DESC, id DESC
                """
            ).fetchall()

        for row in rows:
            try:
                payload = json.loads(row['payload_json'])
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            if not self._is_canonical_roundup_snapshot_path(row['json_path']):
                continue
            snapshot = dict(payload)
            snapshot.setdefault('run_key', row['run_key'])
            snapshot.setdefault('created_at', row['created_at'])
            snapshot.setdefault('json_path', row['json_path'])
            return snapshot
        return None

    def list_recent_published_stream(self, limit: int = 4) -> list[dict]:
        if limit <= 0:
            return []
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT published_at, payload_json
                FROM publish_outbox
                WHERE status = 'published'
                  AND published_at IS NOT NULL
                ORDER BY published_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        stream: list[dict] = []
        for row in rows:
            try:
                payload = json.loads(row['payload_json'])
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            offer = payload.get('offer') or {}
            decision = payload.get('decision') or {}
            if not isinstance(offer, dict) or not isinstance(decision, dict):
                continue
            lane = str(decision.get('lane') or '')
            offer_kind = str(offer.get('offer_kind') or '')
            decision_content_type = str(decision.get('content_type') or '')
            stream.append(
                {
                    'published_at': row['published_at'],
                    'lane': lane,
                    'offer_kind': offer_kind,
                    'source': str(offer.get('source') or ''),
                    'content_type': self._outbox_content_type(lane, offer_kind, decision_content_type),
                }
            )
        return stream

    def list_recent_published_card_snapshots(self, limit: int = 8) -> list[dict]:
        if limit <= 0:
            return []
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT published_at, payload_json
                FROM publish_outbox
                WHERE status = 'published'
                  AND published_at IS NOT NULL
                ORDER BY published_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        snapshots: list[dict] = []
        for row in rows:
            try:
                payload = json.loads(row['payload_json'])
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            artifact = payload.get('artifact') or {}
            offer = payload.get('offer') or {}
            decision = payload.get('decision') or {}
            if not isinstance(artifact, dict) or not isinstance(offer, dict) or not isinstance(decision, dict):
                continue
            render_diagnostics = artifact.get('render_diagnostics') or {}
            if not isinstance(render_diagnostics, dict):
                render_diagnostics = {}
            snapshots.append(
                {
                    'published_at': row['published_at'],
                    'offer_id': str(payload.get('offer_id') or ''),
                    'title': str(offer.get('title') or ''),
                    'template_id': str(artifact.get('template_id') or decision.get('template_id') or ''),
                    'render_diagnostics': render_diagnostics,
                }
            )
        return snapshots

    def save_video_manifest(self, manifest: VideoManifest) -> None:
        with self.connect() as connection:
            connection.execute(
                'INSERT INTO video_manifests(offer_id, run_key, json_path, payload_json, created_at) VALUES (?, ?, ?, ?, ?)',
                (
                    manifest.offer_id,
                    manifest.run_key,
                    str(manifest.json_path) if manifest.json_path else None,
                    json.dumps(manifest.payload_json, ensure_ascii=False, sort_keys=True),
                    manifest.created_at.isoformat(),
                ),
            )

    def upsert_outbox(
        self,
        artifact: PostArtifact,
        image_path: Path | None = None,
        offer: Offer | None = None,
        decision_json: dict | None = None,
    ) -> OutboxRecord:
        now = datetime.utcnow().isoformat()
        with self.connect() as connection:
            self._upsert_outbox(
                connection=connection,
                artifact=artifact,
                image_path=image_path,
                offer_snapshot=offer.to_snapshot() if offer else None,
                decision_json=decision_json,
                updated_at=now,
            )
            row = connection.execute(
                'SELECT * FROM publish_outbox WHERE idempotency_key = ?',
                (artifact.idempotency_key,),
            ).fetchone()
        record = self._row_to_outbox_record(row)
        if record is None:
            raise RuntimeError('Outbox record was not created.')
        return record

    def stage_pinned_outbox_delivery(
        self,
        *,
        artifact: PostArtifact,
        image_path: Path,
        offer_snapshot: dict,
        decision_json: dict,
        meta: dict | None = None,
    ) -> OutboxRecord:
        now = datetime.utcnow().isoformat()
        lane = str(decision_json.get('lane') or '').strip()
        if not lane:
            raise RuntimeError('Pinned decision lane is missing.')
        payload = self._build_outbox_payload(artifact, offer_snapshot, decision_json, meta=meta)
        with self.connect() as connection:
            row = connection.execute(
                'SELECT * FROM publish_outbox WHERE idempotency_key = ?',
                (artifact.idempotency_key,),
            ).fetchone()
            existing = self._row_to_outbox_record(row)
            if existing is not None:
                self._assert_outbox_payload_matches(
                    existing,
                    artifact=artifact,
                    image_path=image_path,
                    payload=payload,
                )
                return existing

            self._save_post_artifact(connection, artifact, lane, now)
            try:
                connection.execute(
                    """
                    INSERT INTO publish_outbox(
                        idempotency_key, caption_hash, image_hash, image_path, telegram_message_id, published_at,
                        payload_json, status, attempt_count, last_error, next_attempt_at, claimed_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        artifact.idempotency_key,
                        artifact.caption_hash,
                        artifact.image_hash,
                        str(image_path),
                        artifact.telegram_message_id,
                        None,
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                        'pending',
                        0,
                        None,
                        None,
                        None,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                row = connection.execute(
                    'SELECT * FROM publish_outbox WHERE idempotency_key = ?',
                    (artifact.idempotency_key,),
                ).fetchone()
                existing = self._row_to_outbox_record(row)
                if existing is None:
                    raise
                self._assert_outbox_payload_matches(
                    existing,
                    artifact=artifact,
                    image_path=image_path,
                    payload=payload,
                )
                return existing
            row = connection.execute(
                'SELECT * FROM publish_outbox WHERE idempotency_key = ?',
                (artifact.idempotency_key,),
            ).fetchone()

        record = self._row_to_outbox_record(row)
        if record is None:
            raise RuntimeError('Pinned outbox record was not staged.')
        return record

    def stage_outbox_delivery(
        self,
        queue_row_id: int,
        offer: Offer,
        decision_json: dict,
        artifact: PostArtifact,
        image_path: Path,
    ) -> OutboxRecord:
        now = datetime.utcnow().isoformat()
        with self.connect() as connection:
            self._save_post_artifact(connection, artifact, decision_json['lane'], now)
            self._upsert_outbox(
                connection=connection,
                artifact=artifact,
                image_path=image_path,
                offer_snapshot=offer.to_snapshot(),
                decision_json=decision_json,
                updated_at=now,
            )
            connection.execute('DELETE FROM queue_items WHERE id = ?', (queue_row_id,))
            row = connection.execute(
                'SELECT * FROM publish_outbox WHERE idempotency_key = ?',
                (artifact.idempotency_key,),
            ).fetchone()
        record = self._row_to_outbox_record(row)
        if record is None:
            raise RuntimeError('Outbox record was not staged.')
        return record

    def stage_roundup_outbox_delivery(
        self,
        queue_row_ids: list[int],
        offer: Offer,
        decision_json: dict,
        artifact: PostArtifact,
        image_path: Path,
    ) -> OutboxRecord:
        now = datetime.utcnow().isoformat()
        with self.connect() as connection:
            self._save_post_artifact(connection, artifact, decision_json['lane'], now)
            self._upsert_outbox(
                connection=connection,
                artifact=artifact,
                image_path=image_path,
                offer_snapshot=offer.to_snapshot(),
                decision_json=decision_json,
                updated_at=now,
            )
            delete_ids = [int(row_id) for row_id in queue_row_ids if int(row_id) > 0]
            if delete_ids:
                placeholders = ', '.join('?' for _ in delete_ids)
                connection.execute(f'DELETE FROM queue_items WHERE id IN ({placeholders})', delete_ids)
            row = connection.execute(
                'SELECT * FROM publish_outbox WHERE idempotency_key = ?',
                (artifact.idempotency_key,),
            ).fetchone()
        record = self._row_to_outbox_record(row)
        if record is None:
            raise RuntimeError('Roundup outbox record was not staged.')
        return record

    def list_outbox_replay_ready(
        self,
        now_utc: datetime,
        limit: int = 20,
        stale_after_seconds: int = 1800,
    ) -> list[OutboxRecord]:
        stale_cutoff = (now_utc - timedelta(seconds=stale_after_seconds)).isoformat()
        due_at = now_utc.isoformat()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM publish_outbox
                WHERE status = 'sent'
                   OR status = 'pending'
                   OR (status = 'failed' AND (next_attempt_at IS NULL OR next_attempt_at <= ?))
                   OR (status = 'sending' AND (claimed_at IS NULL OR claimed_at <= ?))
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (due_at, stale_cutoff, limit),
            ).fetchall()
        return [record for row in rows if (record := self._row_to_outbox_record(row)) is not None]

    def mark_outbox_sending(self, idempotency_key: str) -> OutboxRecord | None:
        now = datetime.utcnow().isoformat()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE publish_outbox
                SET status = 'sending',
                    attempt_count = CASE WHEN status = 'sending' THEN attempt_count ELSE attempt_count + 1 END,
                    claimed_at = ?,
                    next_attempt_at = NULL,
                    last_error = NULL,
                    updated_at = ?
                WHERE idempotency_key = ? AND status IN ('pending', 'failed', 'sending')
                """,
                (now, now, idempotency_key),
            )
            row = connection.execute(
                'SELECT * FROM publish_outbox WHERE idempotency_key = ?',
                (idempotency_key,),
            ).fetchone()
        return self._row_to_outbox_record(row)

    def mark_outbox_sent(self, idempotency_key: str, telegram_message_id: int) -> OutboxRecord | None:
        now = datetime.utcnow().isoformat()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE publish_outbox
                SET status = 'sent',
                    telegram_message_id = ?,
                    claimed_at = NULL,
                    last_error = NULL,
                    next_attempt_at = NULL,
                    updated_at = ?
                WHERE idempotency_key = ? AND status != 'published'
                """,
                (telegram_message_id, now, idempotency_key),
            )
            row = connection.execute(
                'SELECT * FROM publish_outbox WHERE idempotency_key = ?',
                (idempotency_key,),
            ).fetchone()
        return self._row_to_outbox_record(row)

    def mark_outbox_failed(self, idempotency_key: str, error: str, next_attempt_at: datetime | None = None) -> None:
        now = datetime.utcnow().isoformat()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE publish_outbox
                SET status = 'failed',
                    last_error = ?,
                    next_attempt_at = ?,
                    claimed_at = NULL,
                    updated_at = ?
                WHERE idempotency_key = ? AND status IN ('pending', 'failed', 'sending')
                """,
                (error[:1000], next_attempt_at.isoformat() if next_attempt_at else None, now, idempotency_key),
            )

    def finalize_publication(self, idempotency_key: str, offer: Offer, lane: str, day_key: str) -> OutboxRecord:
        now = datetime.utcnow().isoformat()
        with self.connect() as connection:
            row = connection.execute(
                'SELECT * FROM publish_outbox WHERE idempotency_key = ?',
                (idempotency_key,),
            ).fetchone()
            record = self._row_to_outbox_record(row)
            if record is None:
                raise RuntimeError(f'Outbox record not found for {idempotency_key}')
            if record.status == 'published':
                return record
            if record.telegram_message_id is None:
                raise RuntimeError(f'Outbox record {idempotency_key} has no Telegram message id')

            payload = record.payload_json or {}
            decision = payload.get('decision') or {}
            content_type = self._decision_content_type(decision, lane, getattr(offer.offer_kind, 'value', offer.offer_kind))
            if content_type == 'roundup':
                self._record_roundup_publication(connection, decision, record.telegram_message_id, now)
            else:
                self._record_publication(connection, offer, lane, record.telegram_message_id, now)
            self._increment_daily_lane(connection, day_key, lane)
            connection.execute(
                """
                UPDATE publish_outbox
                SET status = 'published',
                    published_at = COALESCE(published_at, ?),
                    claimed_at = NULL,
                    last_error = NULL,
                    next_attempt_at = NULL,
                    updated_at = ?
                WHERE idempotency_key = ?
                """,
                (now, now, idempotency_key),
            )
            row = connection.execute(
                'SELECT * FROM publish_outbox WHERE idempotency_key = ?',
                (idempotency_key,),
            ).fetchone()
        finalized = self._row_to_outbox_record(row)
        if finalized is None:
            raise RuntimeError(f'Outbox record disappeared for {idempotency_key}')
        return finalized

    def mark_outbox_published(self, idempotency_key: str, telegram_message_id: int) -> None:
        now = datetime.utcnow().isoformat()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE publish_outbox
                SET telegram_message_id = ?,
                    published_at = ?,
                    status = 'published',
                    claimed_at = NULL,
                    last_error = NULL,
                    next_attempt_at = NULL,
                    updated_at = ?
                WHERE idempotency_key = ?
                """,
                (telegram_message_id, now, now, idempotency_key),
            )

    def record_publication(self, offer: Offer, lane: str, telegram_message_id: int | None) -> None:
        with self.connect() as connection:
            self._record_publication(connection, offer, lane, telegram_message_id, datetime.utcnow().isoformat())

    def _save_post_artifact(self, connection: sqlite3.Connection, artifact: PostArtifact, lane: str, created_at: str) -> None:
        connection.execute(
            'INSERT INTO post_artifacts(offer_id, lane, artifact_json, created_at) VALUES (?, ?, ?, ?)',
            (artifact.offer_id, lane, json.dumps(asdict(artifact), ensure_ascii=False, sort_keys=True), created_at),
        )

    def _upsert_outbox(
        self,
        connection: sqlite3.Connection,
        artifact: PostArtifact,
        image_path: Path | None,
        offer_snapshot: dict | None,
        decision_json: dict | None,
        updated_at: str,
    ) -> None:
        payload = self._build_outbox_payload(artifact, offer_snapshot, decision_json)
        connection.execute(
            """
            INSERT INTO publish_outbox(
                idempotency_key, caption_hash, image_hash, image_path, telegram_message_id, published_at,
                payload_json, status, attempt_count, last_error, next_attempt_at, claimed_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(idempotency_key) DO UPDATE SET
                caption_hash = excluded.caption_hash,
                image_hash = excluded.image_hash,
                image_path = COALESCE(excluded.image_path, publish_outbox.image_path),
                payload_json = excluded.payload_json,
                updated_at = excluded.updated_at
            """,
            (
                artifact.idempotency_key,
                artifact.caption_hash,
                artifact.image_hash,
                str(image_path) if image_path else None,
                artifact.telegram_message_id,
                None,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                'pending',
                0,
                None,
                None,
                None,
                updated_at,
                updated_at,
            ),
        )

    def _build_outbox_payload(
        self,
        artifact: PostArtifact,
        offer_snapshot: dict | None,
        decision_json: dict | None,
        meta: dict | None = None,
    ) -> dict:
        render_inputs = artifact.render_inputs or {}
        stable_offer = offer_snapshot or render_inputs.get('offer')
        stable_decision = decision_json or render_inputs.get('decision')
        payload = {
            'schema_version': 1,
            'offer_id': artifact.offer_id,
            'artifact': asdict(artifact),
            'offer': stable_offer,
            'decision': stable_decision,
        }
        if isinstance(meta, dict) and meta:
            payload['meta'] = dict(meta)
        return payload

    @staticmethod
    def _normalize_outbox_payload_for_compare(payload: dict | None) -> dict:
        normalized = json.loads(json.dumps(dict(payload or {}), ensure_ascii=False, sort_keys=True))
        normalized.pop('meta', None)
        return normalized

    def _assert_outbox_payload_matches(
        self,
        existing: OutboxRecord,
        *,
        artifact: PostArtifact,
        image_path: Path,
        payload: dict,
    ) -> None:
        existing_image_path = str(existing.image_path) if existing.image_path else None
        requested_image_path = str(image_path)
        if existing.caption_hash != artifact.caption_hash:
            raise OutboxPayloadConflictError('idempotency_conflict')
        if existing.image_hash != artifact.image_hash:
            raise OutboxPayloadConflictError('idempotency_conflict')
        if existing_image_path != requested_image_path:
            raise OutboxPayloadConflictError('idempotency_conflict')
        existing_payload = self._normalize_outbox_payload_for_compare(existing.payload_json)
        requested_payload = self._normalize_outbox_payload_for_compare(payload)
        if existing_payload != requested_payload:
            raise OutboxPayloadConflictError('idempotency_conflict')

    def _record_publication(
        self,
        connection: sqlite3.Connection,
        offer: Offer,
        lane: str,
        telegram_message_id: int | None,
        posted_at: str,
    ) -> None:
        existing = connection.execute(
            'SELECT best_price_minor FROM publication_history WHERE game_id = ?',
            (offer.game_id,),
        ).fetchone()
        best_price_minor = offer.price_after_minor
        if existing and existing['best_price_minor'] is not None and offer.price_after_minor is not None:
            best_price_minor = min(existing['best_price_minor'], offer.price_after_minor)
        elif existing and existing['best_price_minor'] is not None:
            best_price_minor = existing['best_price_minor']

        connection.execute(
            """
            INSERT OR REPLACE INTO publication_history(
                game_id, franchise_key, source, posted_at, price_after_minor, discount_percent, lane, promo_end, best_price_minor, telegram_message_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                offer.game_id,
                offer.franchise_key,
                offer.source.value,
                posted_at,
                offer.price_after_minor,
                offer.discount_percent,
                lane,
                offer.promo_end.isoformat() if offer.promo_end else None,
                best_price_minor,
                telegram_message_id,
            ),
        )
        connection.execute(
            'INSERT OR REPLACE INTO franchise_history(franchise_key, posted_at, source) VALUES (?, ?, ?)',
            (offer.franchise_key, posted_at, offer.source.value),
        )

    def _increment_daily_lane(self, connection: sqlite3.Connection, day_key: str, lane: str) -> None:
        connection.execute(
            """
            INSERT INTO daily_lane_usage(day_key, lane, count)
            VALUES (?, ?, 1)
            ON CONFLICT(day_key, lane) DO UPDATE SET count = count + 1
            """,
            (day_key, lane),
        )

    @staticmethod
    def _row_to_queue_record(row: sqlite3.Row) -> QueueRecord:
        return QueueRecord(
            row_id=row['id'],
            bucket=row['bucket'],
            lane=row['lane'],
            score=row['score'],
            offer=Offer.from_snapshot(json.loads(row['offer_json'])),
            decision_json=json.loads(row['decision_json']),
            created_at=datetime.fromisoformat(row['created_at']),
        )

    @staticmethod
    def _row_to_outbox_record(row: sqlite3.Row | None) -> OutboxRecord | None:
        if row is None:
            return None
        updated_at = row['updated_at'] or row['created_at']
        return OutboxRecord(
            idempotency_key=row['idempotency_key'],
            caption_hash=row['caption_hash'],
            image_hash=row['image_hash'],
            image_path=Path(row['image_path']) if row['image_path'] else None,
            telegram_message_id=row['telegram_message_id'],
            published_at=datetime.fromisoformat(row['published_at']) if row['published_at'] else None,
            payload_json=json.loads(row['payload_json']),
            status=row['status'],
            attempt_count=int(row['attempt_count'] or 0),
            last_error=row['last_error'],
            next_attempt_at=datetime.fromisoformat(row['next_attempt_at']) if row['next_attempt_at'] else None,
            claimed_at=datetime.fromisoformat(row['claimed_at']) if row['claimed_at'] else None,
            created_at=datetime.fromisoformat(row['created_at']),
            updated_at=datetime.fromisoformat(updated_at),
        )

    @staticmethod
    def _outbox_content_type(lane: str, offer_kind: str, decision_content_type: str = '') -> str:
        normalized_decision = str(decision_content_type or '').strip().lower()
        if normalized_decision in {'event', 'freebie', 'discount', 'roundup'}:
            return normalized_decision
        normalized_lane = str(lane or '').strip().lower()
        normalized_kind = str(offer_kind or '').strip().lower()
        if normalized_lane == 'roundup_digest':
            return 'roundup'
        if normalized_kind in {'festival', 'event'} or normalized_lane == 'event_festival':
            return 'event'
        if normalized_kind == 'freebie' or normalized_lane == 'breaking_freebie':
            return 'freebie'
        return 'discount'

    def _record_roundup_publication(
        self,
        connection: sqlite3.Connection,
        decision_json: dict,
        telegram_message_id: int,
        posted_at: str,
    ) -> None:
        item_snapshots = decision_json.get('roundup_item_offers') or []
        if not isinstance(item_snapshots, list):
            return
        for snapshot in item_snapshots:
            if not isinstance(snapshot, dict):
                continue
            try:
                offer = Offer.from_snapshot(snapshot)
            except Exception:
                continue
            self._record_publication(
                connection,
                offer,
                str(decision_json.get('lane') or 'roundup_digest'),
                telegram_message_id,
                posted_at,
            )

    @staticmethod
    def _decision_content_type(decision_json: dict | None, lane: str, offer_kind: str) -> str:
        if isinstance(decision_json, dict):
            declared = str(decision_json.get('content_type') or '').strip().lower()
            if declared in {'event', 'freebie', 'discount', 'roundup'}:
                return declared
        return Repositories._outbox_content_type(lane, offer_kind)

    @staticmethod
    def _normalize_roundup_window_key(value: str | None) -> str | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value)).replace(microsecond=0).isoformat()
        except ValueError:
            return None

    @staticmethod
    def _is_editorial_roundup_snapshot(json_path: str | None, payload: dict) -> bool:
        if not isinstance(payload, dict):
            return False
        context = payload.get('context')
        if not isinstance(context, dict) or context.get('source') != 'current_queue':
            return False
        return Repositories._is_canonical_roundup_snapshot_path(json_path)

    @staticmethod
    def _is_canonical_roundup_snapshot_path(json_path: str | None) -> bool:
        normalized_path = str(json_path or '').replace('/', '\\').lower()
        return '\\output\\analytics\\' in normalized_path

