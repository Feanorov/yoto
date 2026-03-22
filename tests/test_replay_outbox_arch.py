from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from application.use_cases.replay_outbox import ReplayOutboxUseCase
from domain.entities.post_artifact import PostArtifact
from infrastructure.db.repositories import Repositories

from .test_caption_builder_arch import make_offer
from .test_publish_reliability_arch import make_decision_json


class RecordingPublisher:
    def __init__(self, failures_before_success: int = 0) -> None:
        self.calls = 0
        self.failures_before_success = failures_before_success

    async def publish_photo(self, image_path: Path, caption_html: str):
        self.calls += 1
        if self.calls <= self.failures_before_success:
            raise RuntimeError('telegram timeout')
        return SimpleNamespace(message_id=700 + self.calls)


def make_artifact(idempotency_key: str) -> PostArtifact:
    offer = make_offer()
    decision_json = make_decision_json()
    return PostArtifact(
        offer_id=offer.offer_id,
        caption_html='<b>caption</b>',
        hashtags=['#steam'],
        template_id='steam_discount',
        render_inputs={'offer': offer.to_snapshot(), 'decision': decision_json},
        assets_used=[],
        idempotency_key=idempotency_key,
        caption_hash='caption-hash',
        image_hash='image-hash',
    )


def seed_outbox(repo: Repositories, tmp_path: Path, idempotency_key: str, status: str):
    offer = make_offer()
    decision_json = make_decision_json()
    artifact = make_artifact(idempotency_key)
    image_path = tmp_path / f'{idempotency_key}.png'
    image_path.write_bytes(b'card')
    repo.upsert_outbox(artifact, image_path=image_path, offer=offer, decision_json=decision_json)

    if status == 'pending':
        return offer, decision_json, image_path
    if status == 'failed':
        repo.mark_outbox_failed(idempotency_key, 'temporary', datetime(2026, 3, 10, 11, 0))
        return offer, decision_json, image_path
    if status == 'sending':
        repo.mark_outbox_sending(idempotency_key)
        with repo.connect() as connection:
            connection.execute(
                "UPDATE publish_outbox SET claimed_at = ? WHERE idempotency_key = ?",
                ((datetime(2026, 3, 10, 10, 0)).isoformat(), idempotency_key),
            )
        return offer, decision_json, image_path
    if status == 'sent':
        repo.mark_outbox_sent(idempotency_key, 777)
        return offer, decision_json, image_path
    if status == 'published':
        repo.mark_outbox_sent(idempotency_key, 778)
        repo.finalize_publication(idempotency_key, offer, decision_json['lane'], '2026-03-10')
        return offer, decision_json, image_path
    raise ValueError(status)


def test_replay_published_rows_are_skipped_without_resend(tmp_path: Path, monkeypatch) -> None:
    repo = Repositories(tmp_path / 'repo.sqlite3')
    repo.initialize()
    seed_outbox(repo, tmp_path, 'published-key', 'published')
    published_record = repo.get_outbox_record('published-key')
    publisher = RecordingPublisher()
    replay = ReplayOutboxUseCase(repo, publisher)

    monkeypatch.setattr(repo, 'list_outbox_replay_ready', lambda **kwargs: [published_record])

    summary = asyncio.run(replay.execute(datetime(2026, 3, 10, 12, 0), datetime(2026, 3, 10, 12, 0), limit=10))

    assert summary.skipped == 1
    assert summary.results[0].reason == 'already_published'
    assert publisher.calls == 0


def test_replay_sent_rows_finalize_without_resend(tmp_path: Path) -> None:
    repo = Repositories(tmp_path / 'repo.sqlite3')
    repo.initialize()
    seed_outbox(repo, tmp_path, 'sent-key', 'sent')
    publisher = RecordingPublisher()
    replay = ReplayOutboxUseCase(repo, publisher)

    summary = asyncio.run(replay.execute(datetime(2026, 3, 10, 12, 0), datetime(2026, 3, 10, 12, 0), limit=10))
    stored = repo.get_outbox_record('sent-key')

    assert summary.published == 1
    assert summary.results[0].reason == 'finalized_sent'
    assert stored is not None
    assert stored.status == 'published'
    assert publisher.calls == 0


@pytest.mark.parametrize('status', ['pending', 'failed', 'sending'])
def test_replay_retries_retryable_statuses(tmp_path: Path, status: str) -> None:
    repo = Repositories(tmp_path / f'{status}.sqlite3')
    repo.initialize()
    seed_outbox(repo, tmp_path, f'{status}-key', status)
    publisher = RecordingPublisher()
    replay = ReplayOutboxUseCase(repo, publisher)

    summary = asyncio.run(replay.execute(datetime(2026, 3, 10, 12, 0), datetime(2026, 3, 10, 12, 0), limit=10))
    stored = repo.get_outbox_record(f'{status}-key')

    assert summary.published == 1
    assert stored is not None
    assert stored.status == 'published'
    assert publisher.calls == 1


@pytest.mark.parametrize(
    'payload',
    [
        {'schema_version': 1, 'artifact': {}, 'offer': make_offer().to_snapshot()},
        {'schema_version': 1, 'artifact': 'bad', 'offer': make_offer().to_snapshot(), 'decision': make_decision_json()},
    ],
)
def test_replay_fails_closed_on_invalid_payload(tmp_path: Path, payload: dict) -> None:
    repo = Repositories(tmp_path / 'repo.sqlite3')
    repo.initialize()
    image_path = tmp_path / 'bad.png'
    image_path.write_bytes(b'card')
    publisher = RecordingPublisher()

    with repo.connect() as connection:
        connection.execute(
            """
            INSERT INTO publish_outbox(
                idempotency_key, caption_hash, image_hash, image_path, telegram_message_id, published_at,
                payload_json, status, attempt_count, last_error, next_attempt_at, claimed_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                'bad-payload',
                'caption',
                'image',
                str(image_path),
                None,
                None,
                json.dumps(payload),
                'pending',
                0,
                None,
                None,
                None,
                '2026-03-10T11:00:00',
                '2026-03-10T11:00:00',
            ),
        )

    replay = ReplayOutboxUseCase(repo, publisher)
    summary = asyncio.run(replay.execute(datetime(2026, 3, 10, 12, 0), datetime(2026, 3, 10, 12, 0), limit=10))
    stored = repo.get_outbox_record('bad-payload')

    assert summary.failed == 1
    assert summary.results[0].reason == 'invalid_payload'
    assert stored is not None
    assert stored.status == 'failed'
    assert publisher.calls == 0