from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import sqlite3

from application.use_cases.dry_run_render import RenderResult
from application.use_cases.publish_next import PublishNextUseCase
from application.use_cases.replay_outbox import ReplayOutboxUseCase
from dealbot.settings import AppSettings, EditorialConfig, EditorialControlConfig, OperationalConfig, StaticConfig, SteamAccessConfig
from domain.entities.post_artifact import PostArtifact
from infrastructure.db.repositories import Repositories

from .support import make_test_settings
from .test_caption_builder_arch import make_offer


class StaticRenderUseCase:
    def __init__(self, image_path: Path, idempotency_key: str = 'reliable-key') -> None:
        self.image_path = image_path
        self.idempotency_key = idempotency_key

    async def execute(self, offer, decision_json):
        artifact = PostArtifact(
            offer_id=offer.offer_id,
            caption_html='<b>caption</b>',
            hashtags=['#steam'],
            template_id='steam_discount',
            render_inputs={'offer': offer.to_snapshot(), 'decision': decision_json},
            assets_used=[],
            idempotency_key=self.idempotency_key,
            caption_hash='caption-hash',
            image_hash='image-hash',
        )
        return RenderResult(artifact=artifact, image_path=self.image_path)


class FailingRenderUseCase:
    async def execute(self, offer, decision_json):
        raise RuntimeError('render boom')


class RecordingPublisher:
    def __init__(self, failures_before_success: int = 0) -> None:
        self.calls = 0
        self.failures_before_success = failures_before_success

    async def publish_photo(self, image_path: Path, caption_html: str):
        self.calls += 1
        if self.calls <= self.failures_before_success:
            raise RuntimeError('telegram timeout')
        return SimpleNamespace(message_id=900 + self.calls)


def make_settings(tmp_path: Path) -> AppSettings:
    return make_test_settings(tmp_path)


def make_decision_json() -> dict:
    return {'lane': 'high_value_discount', 'template_id': 'steam_discount', 'queue_bucket': 'planned', 'debug': {}}


def test_publish_next_keeps_queue_item_when_render_fails(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    repo = Repositories(settings.db_path)
    repo.initialize()
    offer = make_offer()
    repo.replace_queue('planned', [(100.0, offer, make_decision_json())])
    use_case = PublishNextUseCase(settings, repo, FailingRenderUseCase(), RecordingPublisher())

    result = asyncio.run(use_case.execute(datetime(2026, 3, 10, 12, 0), datetime(2026, 3, 10, 12, 0)))

    assert result.reason == 'render_failed'
    assert len(repo.list_queue('planned')) == 1
    assert repo.get_outbox_record('reliable-key') is None


def test_publish_next_keeps_queue_item_when_durable_stage_fails(tmp_path: Path, monkeypatch) -> None:
    settings = make_settings(tmp_path)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')
    offer = make_offer()
    repo.replace_queue('planned', [(100.0, offer, make_decision_json())])
    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())

    def fail_stage(*args, **kwargs):
        raise sqlite3.OperationalError('disk I/O error')

    monkeypatch.setattr(repo, 'stage_outbox_delivery', fail_stage)

    result = asyncio.run(use_case.execute(datetime(2026, 3, 10, 12, 0), datetime(2026, 3, 10, 12, 0)))

    assert result.reason == 'db_stage_failed'
    assert len(repo.list_queue('planned')) == 1
    assert repo.get_outbox_record('reliable-key') is None


def test_publish_next_marks_failed_when_telegram_send_fails(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')
    offer = make_offer()
    repo.replace_queue('planned', [(100.0, offer, make_decision_json())])
    publisher = RecordingPublisher(failures_before_success=1)
    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), publisher)

    result = asyncio.run(use_case.execute(datetime(2026, 3, 10, 12, 0), datetime(2026, 3, 10, 12, 0)))
    outbox = repo.get_outbox_record('reliable-key')

    assert result.reason == 'publish_failed'
    assert outbox is not None
    assert outbox.status == 'failed'
    assert repo.list_queue('planned') == []


def test_publish_next_normal_path_ends_in_published_state(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')
    offer = make_offer()
    repo.replace_queue('planned', [(100.0, offer, make_decision_json())])
    publisher = RecordingPublisher()
    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), publisher)

    result = asyncio.run(use_case.execute(datetime(2026, 3, 10, 12, 0), datetime(2026, 3, 10, 12, 0)))
    outbox = repo.get_outbox_record('reliable-key')

    assert result.reason == 'published'
    assert result.published is True
    assert outbox is not None
    assert outbox.status == 'published'
    assert repo.list_queue('planned') == []
    assert repo.get_daily_lane_count('2026-03-10', 'high_value_discount') == 1
    assert publisher.calls == 1


def test_publish_finalize_failure_leaves_sent_row_for_replay_without_duplicate_send(tmp_path: Path, monkeypatch) -> None:
    settings = make_settings(tmp_path)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')
    offer = make_offer()
    repo.replace_queue('planned', [(100.0, offer, make_decision_json())])
    publisher = RecordingPublisher()
    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), publisher)
    original_finalize = repo.finalize_publication
    calls = {'count': 0}

    def flaky_finalize(*args, **kwargs):
        calls['count'] += 1
        if calls['count'] == 1:
            raise sqlite3.OperationalError('commit failed')
        return original_finalize(*args, **kwargs)

    monkeypatch.setattr(repo, 'finalize_publication', flaky_finalize)

    first = asyncio.run(use_case.execute(datetime(2026, 3, 10, 12, 0), datetime(2026, 3, 10, 12, 0)))
    staged = repo.get_outbox_record('reliable-key')

    assert first.reason == 'db_finalize_failed'
    assert staged is not None
    assert staged.status == 'sent'
    assert publisher.calls == 1

    replay = ReplayOutboxUseCase(repo, publisher)
    second = asyncio.run(replay.execute(datetime(2026, 3, 10, 12, 20), datetime(2026, 3, 10, 12, 20), limit=10))
    finalized = repo.get_outbox_record('reliable-key')

    assert second.published == 1
    assert finalized is not None
    assert finalized.status == 'published'
    assert publisher.calls == 1
    assert repo.get_daily_lane_count('2026-03-10', 'high_value_discount') == 1