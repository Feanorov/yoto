from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from domain.entities.post_artifact import PostArtifact
from infrastructure.db.repositories import Repositories

from .test_caption_builder_arch import make_offer


def make_artifact(idempotency_key: str = 'abc123') -> PostArtifact:
    offer = make_offer()
    decision_json = {'lane': 'high_value_discount', 'template_id': 'steam_discount', 'queue_bucket': 'planned', 'debug': {}}
    return PostArtifact(
        offer_id=offer.offer_id,
        caption_html='<b>caption</b>',
        hashtags=['#steam'],
        template_id='steam_discount',
        render_inputs={'offer': offer.to_snapshot(), 'decision': decision_json},
        assets_used=['https://example.com/header.png'],
        idempotency_key=idempotency_key,
        caption_hash='captionhash',
        image_hash='imagehash',
    )


def test_repositories_store_post_artifact_and_outbox(tmp_path: Path) -> None:
    repo = Repositories(tmp_path / 'repo.sqlite3')
    repo.initialize()
    offer = make_offer()
    decision_json = {'lane': 'high_value_discount', 'template_id': 'steam_discount', 'queue_bucket': 'planned', 'debug': {}}
    artifact = make_artifact()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')

    repo.save_post_artifact(artifact, 'high_value_discount')
    stored = repo.upsert_outbox(artifact, image_path=image_path, offer=offer, decision_json=decision_json)

    assert stored.status == 'pending'
    assert stored.image_path == image_path
    assert stored.payload_json['offer']['offer_id'] == offer.offer_id
    assert stored.payload_json['decision']['lane'] == 'high_value_discount'
    assert stored.payload_json['artifact']['idempotency_key'] == artifact.idempotency_key


def test_repositories_initialize_upgrades_publish_outbox_additively(tmp_path: Path) -> None:
    db_path = tmp_path / 'legacy.sqlite3'
    payload = json.dumps({'offer_id': 'steam:10'})

    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE publish_outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                idempotency_key TEXT NOT NULL UNIQUE,
                caption_hash TEXT NOT NULL,
                image_hash TEXT NOT NULL,
                telegram_message_id INTEGER,
                published_at TEXT,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        connection.execute(
            """
            INSERT INTO publish_outbox(
                idempotency_key, caption_hash, image_hash, telegram_message_id, published_at, payload_json, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ('legacy-key', 'captionhash', 'imagehash', None, None, payload, 'pending', '2026-03-10T10:00:00'),
        )

    repo = Repositories(db_path)
    repo.initialize()
    stored = repo.get_outbox_record('legacy-key')

    assert stored is not None
    assert stored.payload_json['offer_id'] == 'steam:10'
    assert stored.created_at == datetime.fromisoformat('2026-03-10T10:00:00')

    with repo.connect() as connection:
        columns = {row['name'] for row in connection.execute('PRAGMA table_info(publish_outbox)').fetchall()}

    assert {'image_path', 'attempt_count', 'last_error', 'next_attempt_at', 'claimed_at', 'updated_at'}.issubset(columns)


def test_stage_outbox_delivery_inserts_outbox_before_queue_delete(tmp_path: Path, monkeypatch) -> None:
    repo = Repositories(tmp_path / 'repo.sqlite3')
    repo.initialize()
    offer = make_offer()
    decision_json = {'lane': 'high_value_discount', 'template_id': 'steam_discount', 'queue_bucket': 'planned', 'debug': {}}
    artifact = make_artifact('stage-key')
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')
    repo.replace_queue('planned', [(100.0, offer, decision_json)])
    queue_record = repo.peek_next_for_publish(allow_reserve=True)
    statements: list[str] = []
    original_connect = repo.connect

    def traced_connect():
        connection = original_connect()
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(repo, 'connect', traced_connect)

    staged = repo.stage_outbox_delivery(
        queue_row_id=queue_record.row_id,
        offer=offer,
        decision_json=decision_json,
        artifact=artifact,
        image_path=image_path,
    )

    assert staged.status == 'pending'
    assert repo.get_outbox_record('stage-key') is not None
    assert repo.list_queue('planned') == []

    insert_index = next(index for index, sql in enumerate(statements) if 'INSERT INTO publish_outbox' in sql)
    delete_index = next(index for index, sql in enumerate(statements) if 'DELETE FROM queue_items WHERE id =' in sql)
    assert insert_index < delete_index