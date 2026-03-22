from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from application.use_cases.dry_run_render import RenderResult
from application.use_cases.publish_next import PublishNextUseCase
from dealbot.settings import AppSettings, EditorialConfig, EditorialControlConfig, OperationalConfig, StaticConfig, SteamAccessConfig
from domain.entities.post_artifact import PostArtifact
from infrastructure.db.repositories import Repositories

from .support import make_test_settings
from .test_caption_builder_arch import make_offer


class FakeRenderUseCase:
    def __init__(self, image_path: Path) -> None:
        self.image_path = image_path

    async def execute(self, offer, decision_json):
        artifact = PostArtifact(
            offer_id=offer.offer_id,
            caption_html='<b>caption</b>',
            hashtags=['#steam'],
            template_id='steam_discount',
            render_inputs={'offer': offer.to_snapshot(), 'decision': decision_json},
            assets_used=[],
            idempotency_key='same-key',
            caption_hash='caption-hash',
            image_hash='image-hash',
        )
        return RenderResult(artifact=artifact, image_path=self.image_path)


class FakePublisher:
    def __init__(self) -> None:
        self.calls = 0

    async def publish_photo(self, image_path: Path, caption_html: str):
        self.calls += 1
        return SimpleNamespace(message_id=777)


def make_settings(tmp_path: Path) -> AppSettings:
    return make_test_settings(tmp_path)


def test_publish_next_is_idempotent(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')
    offer = make_offer()
    decision_json = {'lane': 'high_value_discount', 'template_id': 'steam_discount', 'queue_bucket': 'planned', 'debug': {}}
    repo.replace_queue('planned', [(100.0, offer, decision_json), (100.0, offer, decision_json)])
    publisher = FakePublisher()
    use_case = PublishNextUseCase(settings, repo, FakeRenderUseCase(image_path), publisher)

    first = asyncio.run(use_case.execute(datetime(2026, 3, 10, 12, 0), datetime(2026, 3, 10, 12, 0)))
    second = asyncio.run(use_case.execute(datetime(2026, 3, 10, 12, 1), datetime(2026, 3, 10, 12, 1)))

    assert first.published is True
    assert second.reason == 'already_published'
    assert publisher.calls == 1