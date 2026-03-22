from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

from application.use_cases.operator_truth_report import OperatorTruthReporter
from application.use_cases.plan_queue import PlannedCandidate, QueuePlan
from application.use_cases.publish_next import PublishNextUseCase
from infrastructure.analytics.artifact_writer import AnalyticsArtifactWriter
from infrastructure.db.repositories import Repositories

from .support import make_test_settings
from .test_caption_builder_arch import make_offer
from .test_publish_reliability_arch import RecordingPublisher, StaticRenderUseCase


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
