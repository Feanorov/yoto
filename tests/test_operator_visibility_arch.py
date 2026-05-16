from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

from application.use_cases.dry_run_render import RenderResult
from application.use_cases.offline_validation_snapshot import OfflineSnapshotBundle
from application.use_cases.operator_truth_report import OperatorTruthReporter
from application.use_cases.plan_queue import PlannedCandidate, QueuePlan
from application.use_cases.publish_next import PublishNextUseCase
from domain.entities.post_artifact import PostArtifact
from infrastructure.analytics.artifact_writer import AnalyticsArtifactWriter
from infrastructure.db.repositories import Repositories

from .support import make_test_settings
from .test_caption_builder_arch import make_offer
from .test_publish_reliability_arch import FailingRenderUseCase, RecordingPublisher, StaticRenderUseCase


def make_decision_json(
    lane: str,
    *,
    score: float,
    queue_bucket: str = 'planned',
) -> dict:
    return {
        'lane': lane,
        'template_id': 'steam_discount',
        'must_ship': False,
        'queue_bucket': queue_bucket,
        'decision_reasons': [lane],
        'quality_reasons': ['review_threshold'],
        'dedup_reason': 'new_offer',
        'score': score,
        'manual_force_override': False,
        'selection_outcome': 'planned',
        'recommended_post_mode': 'solo_post',
        'debug': {},
    }


def make_candidate(offer, decision_json: dict, score: float) -> PlannedCandidate:
    return PlannedCandidate(score=score, offer=offer, decision_json=decision_json)


class VerifiedRenderUseCase:
    def __init__(self, image_path: Path, *, caption_html: str = '<b>verified caption</b>') -> None:
        self.image_path = image_path
        self.caption_html = caption_html

    async def execute(self, offer, decision_json):
        image_bytes = b'verified-card-image'
        self.image_path.write_bytes(image_bytes)
        artifact = PostArtifact(
            offer_id=offer.offer_id,
            caption_html=self.caption_html,
            hashtags=['#steam'],
            template_id='steam_discount',
            render_inputs={'offer': offer.to_snapshot(), 'decision': decision_json},
            assets_used=['https://example.com/verified.png'],
            idempotency_key='verified-key',
            caption_hash=hashlib.sha256(self.caption_html.encode('utf-8')).hexdigest(),
            image_hash=hashlib.sha256(image_bytes).hexdigest(),
            render_diagnostics={'source': 'verified-render'},
            decision_debug={'caption': {'provider': 'verified-test'}},
        )
        return RenderResult(artifact=artifact, image_path=self.image_path)


def test_publish_next_inspect_selection_exposes_publishable_and_blocked_rows(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path, dry_run=True)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')

    capped = make_offer()
    capped.offer_id = 'steam:cap'
    capped.game_id = 'cap'
    capped.franchise_key = 'cap'
    capped.title = 'Capped Game Of Day'

    fallback = make_offer()
    fallback.offer_id = 'steam:fallback'
    fallback.game_id = 'fallback'
    fallback.franchise_key = 'fallback'
    fallback.title = 'Fallback Discount'

    repo.increment_daily_lane('2026-03-20', 'game_of_the_day')
    repo.replace_queue(
        'planned',
        [
            (140.0, capped, make_decision_json('game_of_the_day', score=140.0)),
            (110.0, fallback, make_decision_json('high_value_discount', score=110.0)),
        ],
    )

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    inspection = use_case.inspect_selection(datetime(2026, 3, 20, 12, 0), datetime(2026, 3, 20, 12, 0))

    assert inspection.selected_candidate is not None
    assert inspection.selected_candidate.offer_id == 'steam:fallback'
    assert len(inspection.eligible_candidates) == 1
    assert any(row.offer_id == 'steam:cap' and row.blocker_reason == 'daily_lane_cap_reached' for row in inspection.blocked_candidates)


def test_publish_next_preview_send_test_target_exposes_selected_artifact_details(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path, dry_run=True)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')

    offer = make_offer()
    offer.offer_id = 'steam:preview'
    offer.game_id = 'preview'
    offer.franchise_key = 'preview'
    offer.title = 'Preview Target'
    repo.replace_queue('planned', [(125.0, offer, make_decision_json('high_value_discount', score=125.0))])

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    target = asyncio.run(use_case.preview_send_test_target(datetime(2026, 3, 20, 12, 0), datetime(2026, 3, 20, 12, 0)))

    assert target.truth_ready is True
    assert target.would_send is True
    assert target.candidate is not None
    assert target.candidate['offer_id'] == 'steam:preview'
    assert target.offer_snapshot['offer_id'] == 'steam:preview'
    assert target.decision_snapshot['lane'] == 'high_value_discount'
    assert target.artifact['template_id'] == 'steam_discount'
    assert target.artifact['image_path'] == str(image_path)
    assert target.artifact['caption_preview']


def test_operator_truth_report_emits_queue_selection_and_target_details(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path, dry_run=True)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')
    now = datetime(2026, 3, 20, 12, 0)

    offer = make_offer()
    offer.offer_id = 'steam:report'
    offer.game_id = 'report'
    offer.franchise_key = 'report'
    offer.title = 'Report Target'
    decision_json = make_decision_json('high_value_discount', score=130.0)
    repo.replace_queue('planned', [(130.0, offer, decision_json)], created_at=now)

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    selection = use_case.inspect_selection(now, now)
    target = asyncio.run(use_case.preview_send_test_target(now, now))
    plan = QueuePlan(
        planned=[make_candidate(offer, decision_json, 130.0)],
        reserve=[],
        metrics={'offers.ingested_total': 1, 'offers.enriched_total': 1},
        context={
            'source': 'current_queue',
            'queue_snapshot_at': now.isoformat(),
            'ingest_sources': {
                'steam': {'status': 'healthy', 'reason': 'healthy', 'offers': 1},
                'epic': {'status': 'healthy', 'reason': 'healthy', 'offers': 0},
            },
            'selection_summary': {'solo_post': 1, 'roundup_candidate': 0, 'capacity_hold': 0},
        },
    )

    reporter = OperatorTruthReporter(repo, AnalyticsArtifactWriter(tmp_path / 'analytics'))
    artifact = reporter.emit(
        now_utc=now,
        mode='preview',
        settings=settings,
        plan=plan,
        selection=selection,
        target=target,
    )

    assert artifact.json_path is not None and artifact.json_path.exists()
    payload = json.loads(artifact.json_path.read_text(encoding='utf-8'))
    assert payload['ingest_sources']['steam']['offers'] == 1
    assert payload['queue']['buckets']['planned']['by_family']['discount'] == 1
    assert payload['selection']['eligible_candidates_total'] == 1
    assert payload['send_test_target']['artifact']['image_path'] == str(image_path)
    assert payload['verdict']['truth_ready'] is True


def test_operator_truth_report_includes_verified_pinned_publish_payload(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path, dry_run=True)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'verified-card.png'
    now = datetime(2026, 3, 20, 12, 0)

    offer = make_offer()
    offer.offer_id = 'steam:pinned'
    offer.game_id = 'pinned'
    offer.franchise_key = 'pinned'
    offer.title = 'Pinned Target'
    decision_json = make_decision_json('high_value_discount', score=135.0)
    repo.replace_queue('planned', [(135.0, offer, decision_json)], created_at=now)

    use_case = PublishNextUseCase(settings, repo, VerifiedRenderUseCase(image_path), RecordingPublisher())
    selection = use_case.inspect_selection(now, now)
    target = asyncio.run(use_case.preview_send_test_target(now, now))
    plan = QueuePlan(
        planned=[make_candidate(offer, decision_json, 135.0)],
        reserve=[],
        metrics={'offers.ingested_total': 1, 'offers.enriched_total': 1},
        context={
            'source': 'current_queue',
            'queue_snapshot_at': now.isoformat(),
            'selection_summary': {'solo_post': 1, 'roundup_candidate': 0, 'capacity_hold': 0},
        },
    )

    reporter = OperatorTruthReporter(repo, AnalyticsArtifactWriter(tmp_path / 'analytics'))
    artifact = reporter.emit(
        now_utc=now,
        mode='preview',
        settings=settings,
        plan=plan,
        selection=selection,
        target=target,
    )

    assert artifact.json_path is not None and artifact.json_path.exists()
    payload = json.loads(artifact.json_path.read_text(encoding='utf-8'))
    pinned_publish = payload['pinned_publish']
    assert pinned_publish['contract_version'] == 1
    assert pinned_publish['source'] == 'preview'
    assert pinned_publish['report_run_key'] == payload['run_key']
    assert pinned_publish['candidate']['offer_id'] == 'steam:pinned'
    assert pinned_publish['offer_snapshot']['offer_id'] == 'steam:pinned'
    assert pinned_publish['decision_snapshot']['lane'] == 'high_value_discount'
    assert pinned_publish['artifact']['caption_html'] == '<b>verified caption</b>'
    assert pinned_publish['artifact']['caption_hash'] == hashlib.sha256(
        pinned_publish['artifact']['caption_html'].encode('utf-8')
    ).hexdigest()
    assert pinned_publish['artifact']['image_path'] == str(image_path)
    assert pinned_publish['artifact']['image_hash'] == hashlib.sha256(image_path.read_bytes()).hexdigest()
    assert pinned_publish['artifact']['idempotency_key'] == 'verified-key'
    assert pinned_publish['validation']['caption_hash_verified'] is True
    assert pinned_publish['validation']['image_exists'] is True
    assert pinned_publish['validation']['image_hash_verified'] is True


def test_operator_truth_report_omits_pinned_publish_when_target_has_no_artifact(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path, dry_run=True)
    repo = Repositories(settings.db_path)
    repo.initialize()
    now = datetime(2026, 3, 20, 12, 0)

    offer = make_offer()
    offer.offer_id = 'steam:no-artifact'
    offer.game_id = 'no-artifact'
    offer.franchise_key = 'no-artifact'
    offer.title = 'No Artifact Target'
    decision_json = make_decision_json('high_value_discount', score=120.0)
    repo.replace_queue('planned', [(120.0, offer, decision_json)], created_at=now)

    use_case = PublishNextUseCase(settings, repo, FailingRenderUseCase(), RecordingPublisher())
    selection = use_case.inspect_selection(now, now)
    target = asyncio.run(use_case.preview_send_test_target(now, now))
    plan = QueuePlan(
        planned=[make_candidate(offer, decision_json, 120.0)],
        reserve=[],
        metrics={'offers.ingested_total': 1, 'offers.enriched_total': 1},
        context={
            'source': 'current_queue',
            'queue_snapshot_at': now.isoformat(),
            'selection_summary': {'solo_post': 1, 'roundup_candidate': 0, 'capacity_hold': 0},
        },
    )

    reporter = OperatorTruthReporter(repo, AnalyticsArtifactWriter(tmp_path / 'analytics'))
    artifact = reporter.emit(
        now_utc=now,
        mode='preview',
        settings=settings,
        plan=plan,
        selection=selection,
        target=target,
    )

    assert artifact.json_path is not None and artifact.json_path.exists()
    payload = json.loads(artifact.json_path.read_text(encoding='utf-8'))
    assert 'pinned_publish' not in payload


def test_operator_truth_report_skips_repository_persistence_for_offline_preview(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path, dry_run=True)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')
    now = datetime(2026, 3, 20, 12, 0)

    offer = make_offer()
    offer.offer_id = 'steam:offline-preview'
    offer.game_id = 'offline-preview'
    offer.franchise_key = 'offline-preview'
    offer.title = 'Offline Preview Target'
    decision_json = make_decision_json('high_value_discount', score=130.0)
    repo.replace_queue('planned', [(130.0, offer, decision_json)], created_at=now)

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    selection = use_case.inspect_selection(now, now)
    target = asyncio.run(use_case.preview_send_test_target(now, now))
    plan = QueuePlan(
        planned=[make_candidate(offer, decision_json, 130.0)],
        reserve=[],
        metrics={'offers.ingested_total': 1, 'offers.enriched_total': 1},
        context={
            'source': 'current_queue',
            'queue_snapshot_at': now.isoformat(),
            'selection_summary': {'solo_post': 1, 'roundup_candidate': 0, 'capacity_hold': 0},
        },
    )
    offline_bundle = OfflineSnapshotBundle(
        root_dir=tmp_path / 'offline_validation' / 'golden' / 'current',
        manifest_path=tmp_path / 'offline_validation' / 'golden' / 'current' / 'snapshot_manifest.json',
        base_db_path=tmp_path / 'offline_validation' / 'golden' / 'current' / 'dealbot.sqlite3',
        run_key='20260320T120000Z',
        created_at=now.isoformat(),
        context={'source': 'current_queue'},
        metrics={'offers.ingested_total': 1},
        planned_count=1,
        reserve_count=0,
        asset_localization={},
        quality={'golden_eligible': True, 'blocking_reasons': []},
        snapshot_role='golden',
        golden_promoted_at=now.isoformat(),
        golden_source_run_key='20260320T110000Z',
    )

    reporter = OperatorTruthReporter(repo, AnalyticsArtifactWriter(tmp_path / 'analytics'))
    artifact = reporter.emit(
        now_utc=now,
        mode='preview_offline',
        settings=settings,
        plan=plan,
        selection=selection,
        target=target,
        offline_bundle=offline_bundle,
    )

    assert artifact.json_path is not None and artifact.json_path.exists()
    with repo.connect() as connection:
        stored = connection.execute(
            "SELECT COUNT(*) FROM analytics_artifacts WHERE artifact_type = 'operator_truth_report'"
        ).fetchone()
    assert stored is not None
    assert int(stored[0]) == 0


def test_async_main_allows_offline_preview_without_publish_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import dealbot.main as main_module

    snapshot_root = tmp_path / 'offline_validation' / 'golden' / 'current'
    snapshot_root.mkdir(parents=True, exist_ok=True)
    db_path = snapshot_root / 'dealbot.sqlite3'
    db_path.write_bytes(b'db')
    bundle = OfflineSnapshotBundle(
        root_dir=snapshot_root,
        manifest_path=snapshot_root / 'snapshot_manifest.json',
        base_db_path=db_path,
        run_key='20260320T120000Z',
        created_at='2026-03-20T12:00:00',
        context={'source': 'current_queue'},
        metrics={},
        planned_count=1,
        reserve_count=0,
        asset_localization={},
        quality={'golden_eligible': True, 'blocking_reasons': []},
        snapshot_role='golden',
        golden_promoted_at='2026-03-20T12:00:00',
        golden_source_run_key='20260320T110000Z',
    )
    settings = make_test_settings(tmp_path, dry_run=True)
    captured: dict[str, object] = {}

    def fake_from_env(root_dir: Path):
        assert main_module.os.environ['BOT_TOKEN'] == 'offline-preview-token'
        assert main_module.os.environ['CHANNEL_USERNAME'] == '@offline_preview'
        return settings

    class FakeSnapshotManager:
        def __init__(self, root_dir: Path) -> None:
            self.root_dir = root_dir

        def resolve(self, spec: str | None = None) -> OfflineSnapshotBundle:
            assert spec == 'golden'
            return bundle

    class FakeRuntime:
        def __init__(self, incoming_settings) -> None:
            self.settings = incoming_settings

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def preview_offline(self, incoming_bundle: OfflineSnapshotBundle) -> None:
            captured['bundle'] = incoming_bundle
            captured['db_path'] = self.settings.db_path

    monkeypatch.setattr(main_module.AppSettings, 'from_env', staticmethod(fake_from_env))
    monkeypatch.setattr(main_module, 'OfflineValidationSnapshotManager', FakeSnapshotManager)
    monkeypatch.setattr(main_module, 'BotRuntime', FakeRuntime)
    monkeypatch.delenv('BOT_TOKEN', raising=False)
    monkeypatch.delenv('CHANNEL_USERNAME', raising=False)
    monkeypatch.setattr(sys, 'argv', ['dealbot.main', '--preview', '--offline-snapshot', 'golden'])

    asyncio.run(main_module.async_main())

    assert captured['bundle'] == bundle
    assert captured['db_path'] == db_path
