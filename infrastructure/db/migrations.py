from __future__ import annotations

from datetime import datetime
import sqlite3


LATEST_SCHEMA_SCRIPT = """
    CREATE TABLE IF NOT EXISTS publication_history (
        game_id TEXT PRIMARY KEY,
        franchise_key TEXT NOT NULL,
        source TEXT NOT NULL,
        posted_at TEXT NOT NULL,
        price_after_minor INTEGER,
        discount_percent INTEGER NOT NULL,
        lane TEXT NOT NULL,
        promo_end TEXT,
        best_price_minor INTEGER,
        telegram_message_id INTEGER
    );
    CREATE TABLE IF NOT EXISTS franchise_history (
        franchise_key TEXT PRIMARY KEY,
        posted_at TEXT NOT NULL,
        source TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS queue_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bucket TEXT NOT NULL,
        lane TEXT NOT NULL,
        score REAL NOT NULL,
        offer_json TEXT NOT NULL,
        decision_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS publish_outbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        idempotency_key TEXT NOT NULL UNIQUE,
        caption_hash TEXT NOT NULL,
        image_hash TEXT NOT NULL,
        image_path TEXT,
        telegram_message_id INTEGER,
        published_at TEXT,
        payload_json TEXT NOT NULL,
        status TEXT NOT NULL,
        attempt_count INTEGER NOT NULL DEFAULT 0,
        last_error TEXT,
        next_attempt_at TEXT,
        claimed_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS post_artifacts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        offer_id TEXT NOT NULL,
        lane TEXT NOT NULL,
        artifact_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS daily_lane_usage (
        day_key TEXT NOT NULL,
        lane TEXT NOT NULL,
        count INTEGER NOT NULL,
        PRIMARY KEY(day_key, lane)
    );
    CREATE TABLE IF NOT EXISTS analytics_artifacts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        artifact_type TEXT NOT NULL,
        subject_id TEXT NOT NULL,
        run_key TEXT NOT NULL,
        json_path TEXT,
        csv_path TEXT,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS video_manifests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        offer_id TEXT NOT NULL,
        run_key TEXT NOT NULL,
        json_path TEXT,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
"""


def apply_migrations(connection: sqlite3.Connection) -> None:
    current_version = int(connection.execute('PRAGMA user_version').fetchone()[0])

    if current_version < 1:
        connection.executescript(LATEST_SCHEMA_SCRIPT)
        connection.execute('PRAGMA user_version = 1')
        current_version = 1

    if current_version < 2:
        _add_column_if_missing(connection, 'publish_outbox', 'image_path', 'TEXT')
        _add_column_if_missing(connection, 'publish_outbox', 'attempt_count', 'INTEGER NOT NULL DEFAULT 0')
        _add_column_if_missing(connection, 'publish_outbox', 'last_error', 'TEXT')
        _add_column_if_missing(connection, 'publish_outbox', 'next_attempt_at', 'TEXT')
        _add_column_if_missing(connection, 'publish_outbox', 'claimed_at', 'TEXT')
        _add_column_if_missing(connection, 'publish_outbox', 'updated_at', 'TEXT')
        connection.execute(
            'UPDATE publish_outbox SET updated_at = COALESCE(updated_at, created_at, ?)',
            (datetime.utcnow().isoformat(),),
        )
        connection.execute('CREATE INDEX IF NOT EXISTS idx_queue_items_bucket_id ON queue_items(bucket, id)')
        connection.execute('CREATE INDEX IF NOT EXISTS idx_publish_outbox_replay ON publish_outbox(status, next_attempt_at, claimed_at)')
        connection.execute('PRAGMA user_version = 2')
        current_version = 2

    if current_version < 3:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analytics_artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                artifact_type TEXT NOT NULL,
                subject_id TEXT NOT NULL,
                run_key TEXT NOT NULL,
                json_path TEXT,
                csv_path TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute('CREATE INDEX IF NOT EXISTS idx_analytics_artifacts_type_created ON analytics_artifacts(artifact_type, created_at)')
        connection.execute('PRAGMA user_version = 3')
        current_version = 3

    if current_version < 4:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS video_manifests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                offer_id TEXT NOT NULL,
                run_key TEXT NOT NULL,
                json_path TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute('CREATE INDEX IF NOT EXISTS idx_video_manifests_offer_created ON video_manifests(offer_id, created_at)')
        connection.execute('PRAGMA user_version = 4')


def _add_column_if_missing(connection: sqlite3.Connection, table_name: str, column_name: str, column_sql: str) -> None:
    existing_columns = {
        row['name']
        for row in connection.execute(f'PRAGMA table_info({table_name})').fetchall()
    }
    if column_name in existing_columns:
        return
    connection.execute(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}')
