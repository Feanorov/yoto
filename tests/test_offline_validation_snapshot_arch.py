from __future__ import annotations

import asyncio
from datetime import datetime
from io import BytesIO
import json
from pathlib import Path

from PIL import Image
import pytest

from application.use_cases.offline_validation_snapshot import OfflineValidationSnapshotManager
from application.use_cases.plan_queue import PlannedCandidate, QueuePlan
from domain.entities.analytics_artifact import AnalyticsArtifact
from infrastructure.db.repositories import Repositories
from infrastructure.render.cards.renderer_selector import CardRendererRouter
from infrastructure.render.cards.template_system import TemplateSystem

from .support import make_test_settings
from .test_caption_builder_arch import make_offer


class StaticHttp:
    def __init__(self, payloads: dict[str, bytes]) -> None:
        self.payloads = payloads

    async def get_bytes(self, url: str) -> bytes:
        if url not in self.payloads:
            raise RuntimeError(f'missing payload for {url}')
        return self.payloads[url]


class ExplodingHttp:
    async def get_bytes(self, url: str) -> bytes:
        raise AssertionError(f'network should not be used for local asset {url}')


def make_png_bytes(color: str = '#334455') -> bytes:
    buffer = BytesIO()
    Image.new('RGB', (1280, 720), color).save(buffer, format='PNG')
    return buffer.getvalue()


def make_decision_json(*, lane: str = 'high_value_discount', template_id: str = 'steam_discount') -> dict:
    return {
        'lane': lane,
        'template_id': template_id,
        'must_ship': False,
        'queue_bucket': 'planned',
        'decision_reasons': [lane],
        'quality_reasons': ['review_threshold'],
        'dedup_reason': 'new_offer',
        'score': 123.4,
        'manual_force_override': False,
        'selection_outcome': 'planned',
        'recommended_post_mode': 'solo_post',
        'debug': {},
    }


def make_plan(now: datetime, offer, decision_json: dict) -> QueuePlan:
    candidate = PlannedCandidate(score=123.4, offer=offer, decision_json=decision_json)
    return QueuePlan(
        planned=[candidate],
        reserve=[],
        metrics={'queue.depth.planned': 1},
        context={
            'source': 'current_queue',
            'queue_snapshot_at': now.replace(microsecond=0).isoformat(),
        },
    )


def test_offline_snapshot_capture_copies_db_localizes_assets_and_marks_quality(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path)
    repo = Repositories(settings.db_path)
    repo.initialize()
    now = datetime(2026, 3, 18, 18, 2, 2)

    offer = make_offer()
    offer.offer_id = 'steam:123'
    offer.source_ref = '123'
    offer.game_id = '123'
    offer.franchise_key = 'snapshot-target'
    offer.title = 'Snapshot Target'
    offer.assets = type(offer.assets)(hero='https://example.com/hero.png', header=None, screenshot=None, fallback=None)
    decision_json = make_decision_json()
    repo.replace_queue('planned', [(123.4, offer, decision_json)], created_at=now)

    manager = OfflineValidationSnapshotManager(tmp_path / 'output' / 'offline_validation')
    bundle = asyncio.run(
        manager.capture(
            live_db_path=settings.db_path,
            run_key='20260318T180202Z',
            created_at=now,
            plan=make_plan(now, offer, decision_json),
            http=StaticHttp({'https://example.com/hero.png': make_png_bytes()}),
        )
    )

    live_offer = repo.list_queue('planned')[0].offer
    snapshot_repo = Repositories(bundle.base_db_path)
    snapshot_offer = snapshot_repo.list_queue('planned')[0].offer

    assert live_offer.assets.hero == 'https://example.com/hero.png'
    assert snapshot_offer.assets.hero is not None
    assert snapshot_offer.assets.hero != live_offer.assets.hero
    assert Path(snapshot_offer.assets.hero).exists()
    assert bundle.asset_localization['downloaded_remote'] == 1
    assert bundle.snapshot_role == 'candidate'
    assert bundle.quality['send_test_offline_ready'] is True
    assert bundle.quality['usable_for_send_test_offline'] is True
    assert bundle.quality['golden_eligible'] is True
    assert bundle.quality['planned_rows_with_local_assets'] == 1
    manifest = json.loads(bundle.manifest_path.read_text(encoding='utf-8'))
    assert manifest['planned_count'] == 1
    assert manifest['context']['queue_snapshot_at'] == '2026-03-18T18:02:02'
    assert manifest['quality']['golden_eligible'] is True


def test_offline_snapshot_golden_promotion_copies_snapshot_and_resolves_alias(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path)
    repo = Repositories(settings.db_path)
    repo.initialize()
    now = datetime(2026, 3, 18, 18, 2, 2)

    offer = make_offer()
    offer.offer_id = 'steam:golden'
    offer.source_ref = 'golden'
    offer.game_id = 'golden'
    offer.franchise_key = 'golden-target'
    offer.title = 'Golden Snapshot Target'
    offer.assets = type(offer.assets)(hero='https://example.com/golden.png', header=None, screenshot=None, fallback=None)
    decision_json = make_decision_json()
    repo.replace_queue('planned', [(123.4, offer, decision_json)], created_at=now)

    manager = OfflineValidationSnapshotManager(tmp_path / 'output' / 'offline_validation')
    bundle = asyncio.run(
        manager.capture(
            live_db_path=settings.db_path,
            run_key='20260318T180202Z',
            created_at=now,
            plan=make_plan(now, offer, decision_json),
            http=StaticHttp({'https://example.com/golden.png': make_png_bytes('#556677')}),
        )
    )

    golden_bundle = manager.promote_golden(bundle)
    resolved_golden = manager.resolve('golden')

    assert golden_bundle.snapshot_role == 'golden'
    assert golden_bundle.golden_source_run_key == bundle.run_key
    assert golden_bundle.base_db_path.exists()
    assert golden_bundle.base_db_path.parent.parent.name == 'golden'
    assert resolved_golden.base_db_path == golden_bundle.base_db_path
    assert resolved_golden.run_key == bundle.run_key
    manifest = json.loads(golden_bundle.manifest_path.read_text(encoding='utf-8'))
    assert manifest['snapshot_role'] == 'golden'
    assert manifest['golden_source_run_key'] == bundle.run_key
    assert Path(manifest['base_db_path']) == golden_bundle.base_db_path


def test_offline_snapshot_golden_promotion_rejects_non_publishable_candidate(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path)
    repo = Repositories(settings.db_path)
    repo.initialize()
    now = datetime(2026, 3, 18, 18, 2, 2)

    manager = OfflineValidationSnapshotManager(tmp_path / 'output' / 'offline_validation')
    bundle = asyncio.run(
        manager.capture(
            live_db_path=settings.db_path,
            run_key='20260318T180202Z',
            created_at=now,
            plan=QueuePlan(
                planned=[],
                reserve=[],
                metrics={},
                context={'source': 'current_queue', 'queue_snapshot_at': now.replace(microsecond=0).isoformat()},
            ),
            http=StaticHttp({}),
        )
    )

    assert bundle.quality['golden_eligible'] is False
    assert 'planned_queue_empty' in bundle.quality['blocking_reasons']
    with pytest.raises(ValueError, match='planned_queue_empty'):
        manager.promote_golden(bundle)


def test_offline_snapshot_capture_localizes_roundup_card_asset(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path)
    repo = Repositories(settings.db_path)
    repo.initialize()
    now = datetime(2026, 3, 18, 18, 2, 2)

    card_path = tmp_path / 'cards' / 'roundup.png'
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(make_png_bytes('#556677'))
    payload = {
        'run_key': '20260318T180202Z',
        'created_at': now.isoformat(),
        'context': {'source': 'current_queue', 'queue_snapshot_at': now.replace(microsecond=0).isoformat()},
        'roundups': [
            {
                'roundup_id': 'roundup_01',
                'title': 'Roundup',
                'telegram_draft': {'caption_html': '<b>Roundup</b>'},
                'card_asset_path': str(card_path),
                'items': [],
            }
        ],
    }
    repo.save_analytics_artifact(
        AnalyticsArtifact(
            artifact_type='roundup_snapshot',
            subject_id='roundups',
            run_key='20260318T180202Z',
            created_at=now,
            payload_json=payload,
            json_path=tmp_path / 'analytics' / '20260318T180202Z_roundup_snapshot_roundups.json',
            csv_path=None,
        )
    )

    manager = OfflineValidationSnapshotManager(tmp_path / 'output' / 'offline_validation')
    bundle = asyncio.run(
        manager.capture(
            live_db_path=settings.db_path,
            run_key='20260318T180202Z',
            created_at=now,
            plan=QueuePlan(planned=[], reserve=[], metrics={}, context={'source': 'current_queue', 'queue_snapshot_at': now.replace(microsecond=0).isoformat()}),
            http=StaticHttp({}),
        )
    )

    with Repositories(bundle.base_db_path).connect() as connection:
        row = connection.execute(
            "SELECT payload_json, json_path FROM analytics_artifacts WHERE artifact_type = 'roundup_snapshot'"
        ).fetchone()

    assert row is not None
    stored_payload = json.loads(row['payload_json'])
    stored_card_path = Path(stored_payload['roundups'][0]['card_asset_path'])
    assert stored_card_path.exists()
    assert stored_card_path != card_path
    assert stored_card_path.is_file()
    assert Path(row['json_path']).exists()
    assert bundle.quality['roundup_snapshots_with_local_cards'] == 1


def test_template_system_uses_local_asset_path_without_network(tmp_path: Path) -> None:
    local_asset = tmp_path / 'hero.png'
    local_asset.write_bytes(make_png_bytes())
    offer = make_offer()
    offer.assets = type(offer.assets)(hero=str(local_asset), header=None, screenshot=None, fallback=None)
    renderer = TemplateSystem(tmp_path / 'cards')

    result = asyncio.run(renderer.render(ExplodingHttp(), offer, 'steam_discount'))

    assert result.image_path.exists()
    assert result.assets_used == [str(local_asset)]


def test_yoto_renderer_uses_local_asset_path_without_network(tmp_path: Path) -> None:
    local_asset = tmp_path / 'hero.png'
    local_asset.write_bytes(make_png_bytes('#778899'))
    offer = make_offer()
    offer.assets = type(offer.assets)(hero=str(local_asset), header=None, screenshot=None, fallback=None)
    renderer = CardRendererRouter(tmp_path / 'cards', renderer_mode='yoto_v4', fallback_to_legacy=False, cache_dir=tmp_path / 'cache')

    result = asyncio.run(renderer.render(ExplodingHttp(), offer, 'steam_discount'))

    assert result.image_path.exists()
    assert result.assets_used == [str(local_asset)]
    assert result.diagnostics.renderer_selected == 'yoto_v4'
