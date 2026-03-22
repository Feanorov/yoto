from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

from application.use_cases.ingest_health_controller import IngestHealthController
from application.use_cases.plan_queue import PlannedCandidate, QueuePlan
from application.use_cases.publish_next import PublishResult
from dealbot.main import BotRuntime
from infrastructure.analytics.artifact_writer import AnalyticsArtifactWriter
from infrastructure.db.repositories import Repositories

from .support import make_test_settings
from .test_caption_builder_arch import make_offer


class StubPlanner:
    def __init__(self, plan: QueuePlan) -> None:
        self.plan = plan

    async def execute(self, now_utc: datetime, now_local: datetime) -> QueuePlan:
        return self.plan


class StubPublisher:
    def __init__(self, result: PublishResult | None) -> None:
        self.result = result
        self.calls = 0

    async def execute(self, now_utc: datetime, now_local: datetime, force_publish: bool = False):
        self.calls += 1
        return self.result


class RecordingSideOutput:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, *args, **kwargs) -> None:
        self.calls += 1


def make_candidate(lane: str = 'high_value_discount') -> PlannedCandidate:
    offer = make_offer()
    return PlannedCandidate(
        score=123.45,
        offer=offer,
        decision_json={
            'lane': lane,
            'template_id': 'steam_discount',
            'must_ship': False,
            'queue_bucket': 'planned',
            'decision_reasons': [lane],
            'quality_reasons': ['review_threshold'],
            'dedup_reason': 'new_offer',
            'is_final_push': False,
            'is_historical_best': False,
            'price_improved_minor': 0,
            'score': 123.45,
            'previous_price_minor': None,
            'previous_posted_at': None,
            'best_price_minor': None,
            'manual_force_override': False,
            'selection_outcome': 'planned',
            'recommended_post_mode': 'solo_post',
            'debug': {},
        },
    )


def make_publish_result(tmp_path: Path) -> PublishResult:
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')
    return PublishResult(
        offer_id='steam:42',
        title='Mystery of the Lantern',
        lane='high_value_discount',
        image_path=image_path,
        message_id=777,
        published=True,
        reason='published',
        analytics={},
    )


def test_ingest_health_controller_emits_fatal_ingest_diagnostics(tmp_path: Path) -> None:
    repo = Repositories(tmp_path / 'repo.sqlite3')
    repo.initialize()
    controller = IngestHealthController(repo, AnalyticsArtifactWriter(tmp_path / 'analytics'))
    now = datetime(2026, 3, 13, 20, 0)
    plan = QueuePlan(
        planned=[],
        reserve=[],
        metrics={'offers.ingested_total': 0, 'offers.enriched_total': 0},
        context={'selection_summary': {'solo_post': 0, 'roundup_candidate': 0}},
    )

    diagnostics = controller.evaluate(now, plan)
    diagnostics = controller.finalize(diagnostics, pipeline_action='stopped_fatal_ingest')
    artifact = controller.emit(diagnostics)

    assert diagnostics.status == 'fatal_ingest'
    assert diagnostics.should_stop_pipeline is True
    assert artifact.json_path is not None and artifact.json_path.exists()
    payload = json.loads(artifact.json_path.read_text(encoding='utf-8'))
    assert payload['status'] == 'fatal_ingest'
    assert payload['pipeline_action'] == 'stopped_fatal_ingest'
    assert payload['ingest']['ingested_total'] == 0


def test_bot_runtime_stops_before_publish_on_fatal_ingest(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path)
    runtime = BotRuntime(settings)
    now = datetime(2026, 3, 13, 20, 5)
    plan = QueuePlan(
        planned=[],
        reserve=[],
        metrics={'offers.ingested_total': 0, 'offers.enriched_total': 0},
        context={},
    )
    publisher = StubPublisher(make_publish_result(tmp_path))
    analytics = RecordingSideOutput()
    roundups = RecordingSideOutput()
    video_manifests = RecordingSideOutput()
    runtime.planner = StubPlanner(plan)
    runtime.publisher = publisher
    runtime.analytics = analytics
    runtime.roundups = roundups
    runtime.video_manifests = video_manifests
    runtime.now = lambda: (now, now)

    result = asyncio.run(runtime.plan_and_publish_once())

    assert result is None
    assert publisher.calls == 0
    assert analytics.calls == 0
    assert roundups.calls == 0
    assert video_manifests.calls == 0
    assert runtime.last_run_diagnostics is not None
    assert runtime.last_run_diagnostics.should_stop_pipeline is True
    with runtime.repositories.connect() as connection:
        row = connection.execute(
            "SELECT artifact_type, payload_json FROM analytics_artifacts WHERE artifact_type = 'run_diagnostics'"
        ).fetchone()
    assert row is not None
    payload = json.loads(row['payload_json'])
    assert payload['status'] == 'fatal_ingest'


def test_bot_runtime_skips_publish_on_empty_planner_window(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path)
    runtime = BotRuntime(settings)
    now = datetime(2026, 3, 13, 20, 10)
    plan = QueuePlan(
        planned=[],
        reserve=[],
        metrics={'offers.ingested_total': 5, 'offers.enriched_total': 5},
        context={},
    )
    publisher = StubPublisher(make_publish_result(tmp_path))
    runtime.planner = StubPlanner(plan)
    runtime.publisher = publisher
    runtime.analytics = RecordingSideOutput()
    runtime.roundups = RecordingSideOutput()
    runtime.video_manifests = RecordingSideOutput()
    runtime.now = lambda: (now, now)

    result = asyncio.run(runtime.plan_and_publish_once())

    assert result is None
    assert publisher.calls == 0
    assert runtime.last_run_diagnostics is not None
    assert runtime.last_run_diagnostics.empty_window is True
    assert runtime.last_run_diagnostics.should_stop_pipeline is False
    with runtime.repositories.connect() as connection:
        row = connection.execute(
            "SELECT payload_json FROM analytics_artifacts WHERE artifact_type = 'run_diagnostics'"
        ).fetchone()
    payload = json.loads(row['payload_json'])
    assert payload['status'] == 'empty_planner_window'
    assert payload['pipeline_action'] == 'skipped_empty_window'


def test_bot_runtime_emits_run_diagnostics_for_healthy_publish_attempt(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path)
    runtime = BotRuntime(settings)
    now = datetime(2026, 3, 13, 20, 15)
    plan = QueuePlan(
        planned=[make_candidate()],
        reserve=[],
        metrics={'offers.ingested_total': 6, 'offers.enriched_total': 6},
        context={'selection_summary': {'solo_post': 1, 'roundup_candidate': 0}},
    )
    publish_result = make_publish_result(tmp_path)
    publisher = StubPublisher(publish_result)
    analytics = RecordingSideOutput()
    roundups = RecordingSideOutput()
    video_manifests = RecordingSideOutput()
    runtime.planner = StubPlanner(plan)
    runtime.publisher = publisher
    runtime.analytics = analytics
    runtime.roundups = roundups
    runtime.video_manifests = video_manifests
    runtime.now = lambda: (now, now)

    result = asyncio.run(runtime.plan_and_publish_once())

    assert result is publish_result
    assert publisher.calls == 1
    assert analytics.calls == 1
    assert roundups.calls == 1
    assert video_manifests.calls == 0
    with runtime.repositories.connect() as connection:
        row = connection.execute(
            "SELECT payload_json FROM analytics_artifacts WHERE artifact_type = 'run_diagnostics'"
        ).fetchone()
    payload = json.loads(row['payload_json'])
    assert payload['status'] == 'healthy'
    assert payload['pipeline_action'] == 'publish_attempted'
    assert payload['publish']['attempted'] is True
    assert payload['publish']['reason'] == 'published'


def test_bot_runtime_runs_roundups_before_publish_on_healthy_cycle(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path)
    runtime = BotRuntime(settings)
    now = datetime(2026, 3, 13, 20, 20)
    plan = QueuePlan(
        planned=[make_candidate()],
        reserve=[make_candidate(lane='backlog_filler')],
        metrics={'offers.ingested_total': 6, 'offers.enriched_total': 6},
        context={'selection_summary': {'solo_post': 1, 'roundup_candidate': 1}},
    )
    publish_result = make_publish_result(tmp_path)
    order: list[str] = []

    class OrderedPublisher(StubPublisher):
        async def execute(self, now_utc: datetime, now_local: datetime, force_publish: bool = False):
            order.append('publisher')
            return await super().execute(now_utc, now_local, force_publish=force_publish)

    class OrderedSideOutput(RecordingSideOutput):
        def __init__(self, label: str) -> None:
            super().__init__()
            self.label = label

        def execute(self, *args, **kwargs) -> None:
            order.append(self.label)
            super().execute(*args, **kwargs)

    runtime.planner = StubPlanner(plan)
    runtime.publisher = OrderedPublisher(publish_result)
    runtime.roundups = OrderedSideOutput('roundups')
    runtime.analytics = OrderedSideOutput('analytics')
    runtime.video_manifests = OrderedSideOutput('video_manifests')
    runtime.now = lambda: (now, now)

    result = asyncio.run(runtime.plan_and_publish_once())

    assert result is publish_result
    assert order == ['roundups', 'publisher', 'analytics']


class LocalOnlyHttp:
    async def get_bytes(self, url: str) -> bytes:
        raise AssertionError(f'network should not be used for local asset {url}')


def _make_eligible_snapshot_bundle(
    tmp_path: Path,
    *,
    run_key: str,
    title: str,
    manager=None,
) -> tuple[object, object, datetime]:
    from application.use_cases.offline_validation_snapshot import OfflineValidationSnapshotManager

    settings = make_test_settings(tmp_path / run_key)
    repo = Repositories(settings.db_path)
    repo.initialize()
    now = datetime(2026, 3, 18, 21, 0)
    asset_path = tmp_path / f'{run_key}_hero.png'
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_bytes(b'local-hero')

    candidate = make_candidate()
    offer = candidate.offer
    offer.offer_id = f'steam:{run_key}'
    offer.source_ref = run_key
    offer.game_id = run_key
    offer.franchise_key = f'franchise:{run_key}'
    offer.title = title
    offer.assets = type(offer.assets)(hero=str(asset_path), header=None, screenshot=None, fallback=None)
    decision_json = dict(candidate.decision_json)
    repo.replace_queue('planned', [(candidate.score, offer, decision_json)], created_at=now)

    snapshot_manager = manager or OfflineValidationSnapshotManager(tmp_path / 'offline_validation')
    plan = QueuePlan(
        planned=[PlannedCandidate(score=candidate.score, offer=offer, decision_json=decision_json)],
        reserve=[],
        metrics={'offers.ingested_total': 6, 'offers.enriched_total': 6},
        context={
            'source': 'current_queue',
            'queue_snapshot_at': now.replace(microsecond=0).isoformat(),
            'selection_summary': {'solo_post': 1, 'roundup_candidate': 0},
        },
    )
    bundle = asyncio.run(
        snapshot_manager.capture(
            live_db_path=settings.db_path,
            run_key=run_key,
            created_at=now,
            plan=plan,
            http=LocalOnlyHttp(),
        )
    )
    return snapshot_manager, bundle, now


def test_bot_runtime_auto_promotes_first_golden_snapshot_from_healthy_cycle(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path / 'runtime')
    runtime = BotRuntime(settings)
    manager, bundle, now = _make_eligible_snapshot_bundle(
        tmp_path / 'snapshots',
        run_key='20260318T210000Z',
        title='First Healthy Golden Candidate',
    )
    plan = QueuePlan(
        planned=[make_candidate()],
        reserve=[],
        metrics={'offers.ingested_total': 6, 'offers.enriched_total': 6},
        context={'selection_summary': {'solo_post': 1, 'roundup_candidate': 0}},
    )
    publish_result = make_publish_result(tmp_path)
    runtime.snapshot_manager = manager
    runtime.planner = StubPlanner(plan)
    runtime.publisher = StubPublisher(publish_result)
    runtime.analytics = RecordingSideOutput()
    runtime.roundups = RecordingSideOutput()
    runtime.video_manifests = RecordingSideOutput()
    runtime.now = lambda: (now, now)

    async def fake_capture(now_utc: datetime, captured_plan: QueuePlan):
        return bundle

    runtime._capture_offline_snapshot = fake_capture

    result = asyncio.run(runtime.plan_and_publish_once(capture_offline_snapshot=True))

    assert result is publish_result
    assert runtime.last_auto_golden_bundle is not None
    assert runtime.last_auto_golden_source == 'run_once'
    assert manager.resolve('golden').run_key == bundle.run_key


def test_bot_runtime_keeps_existing_golden_when_later_live_cycle_is_eligible(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path / 'runtime')
    runtime = BotRuntime(settings)
    manager, first_bundle, now = _make_eligible_snapshot_bundle(
        tmp_path / 'snapshots',
        run_key='20260318T210000Z',
        title='First Healthy Golden Candidate',
    )
    manager.promote_golden(first_bundle)
    _, second_bundle, _ = _make_eligible_snapshot_bundle(
        tmp_path / 'snapshots',
        run_key='20260318T211500Z',
        title='Second Healthy Candidate',
        manager=manager,
    )
    plan = QueuePlan(
        planned=[make_candidate()],
        reserve=[],
        metrics={'offers.ingested_total': 6, 'offers.enriched_total': 6},
        context={'selection_summary': {'solo_post': 1, 'roundup_candidate': 0}},
    )
    publish_result = make_publish_result(tmp_path)
    runtime.snapshot_manager = manager
    runtime.planner = StubPlanner(plan)
    runtime.publisher = StubPublisher(publish_result)
    runtime.analytics = RecordingSideOutput()
    runtime.roundups = RecordingSideOutput()
    runtime.video_manifests = RecordingSideOutput()
    runtime.now = lambda: (now, now)

    async def fake_capture(now_utc: datetime, captured_plan: QueuePlan):
        return second_bundle

    runtime._capture_offline_snapshot = fake_capture

    result = asyncio.run(runtime.plan_and_publish_once(capture_offline_snapshot=True))

    assert result is publish_result
    assert runtime.last_auto_golden_bundle is None
    assert manager.resolve('golden').run_key == first_bundle.run_key
