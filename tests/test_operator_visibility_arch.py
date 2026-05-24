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
from application.use_cases.preview_selected import PreviewSelectedUseCase
from application.use_cases.publish_next import PublishNextUseCase
from application.use_cases.controlled_reserve_release import ReleaseDecision
from domain.entities.offer import OfferKind
from domain.entities.post_artifact import PostArtifact
from infrastructure.analytics.artifact_writer import AnalyticsArtifactWriter
from infrastructure.db.repositories import QueueRecord, Repositories

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


def make_roundup_record(now: datetime, image_path: Path, *, score: float = 200.0) -> QueueRecord:
    offer = make_offer()
    offer.offer_id = 'roundup:weekly'
    offer.game_id = 'roundup:weekly'
    offer.franchise_key = 'roundup:weekly'
    offer.title = 'Roundup: Freebies To Claim'

    decision_json = {
        'lane': 'roundup_digest',
        'template_id': 'roundup_digest',
        'queue_bucket': 'planned',
        'decision_reasons': ['roundup_digest'],
        'quality_reasons': ['roundup_artifact_ready'],
        'dedup_reason': 'roundup_snapshot',
        'score': score,
        'manual_force_override': False,
        'selection_outcome': 'roundup_publish_candidate',
        'recommended_post_mode': 'roundup',
        'content_type': 'roundup',
        'roundup_caption_html': '<b>Roundup</b>',
        'roundup_card_asset_path': str(image_path),
        'roundup_queue_row_ids': [1],
    }
    return QueueRecord(
        row_id=999,
        bucket='planned',
        lane='roundup_digest',
        score=score,
        offer=offer,
        decision_json=decision_json,
        created_at=now,
    )


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


def test_publish_next_preview_send_test_target_respects_requested_post_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_test_settings(tmp_path, dry_run=True)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')
    now = datetime(2026, 3, 20, 12, 0)

    discount_offer = make_offer()
    discount_offer.offer_id = 'steam:single-mode'
    discount_offer.game_id = 'single-mode'
    discount_offer.franchise_key = 'single-mode'
    discount_offer.title = 'Single Discount Candidate'
    repo.replace_queue('planned', [(120.0, discount_offer, make_decision_json('high_value_discount', score=120.0))], created_at=now)

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    roundup_record = make_roundup_record(now, image_path, score=200.0)
    monkeypatch.setattr(
        use_case,
        '_build_roundup_candidate',
        lambda reserve_candidates, recent_stream: (
            roundup_record,
            {'attempted': True, 'status': 'candidate_ready', 'reason': None, 'release_status': 'visible'},
        ),
    )
    monkeypatch.setattr(
        use_case.controlled_reserve_release,
        'release',
        lambda **kwargs: ReleaseDecision(
            visible_reserve_candidates=[],
            visible_roundup_candidate=kwargs['roundup_candidate'],
            reason='leading_discount_streak',
            released_content_type='roundup',
        ),
    )

    generic_target = asyncio.run(use_case.preview_send_test_target(now, now, requested_post_mode='any'))
    filtered_selection = use_case.inspect_selection(now, now, requested_post_mode='single_discount')
    filtered_target = asyncio.run(use_case.preview_send_test_target(now, now, requested_post_mode='single_discount'))

    assert generic_target.candidate is not None
    assert generic_target.candidate['offer_id'] == 'roundup:weekly'
    assert filtered_selection.selected_candidate is not None
    assert filtered_selection.selected_candidate.offer_id == 'steam:single-mode'
    assert filtered_selection.eligible_candidates[0].offer_id == 'steam:single-mode'
    assert filtered_target.candidate is not None
    assert filtered_target.candidate['offer_id'] == 'steam:single-mode'


def test_publish_next_preview_send_test_target_reports_no_candidates_for_requested_mode(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path, dry_run=True)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')
    now = datetime(2026, 3, 20, 12, 0)

    freebie_offer = make_offer()
    freebie_offer.offer_id = 'steam:freebie-only'
    freebie_offer.game_id = 'freebie-only'
    freebie_offer.franchise_key = 'freebie-only'
    freebie_offer.title = 'Freebie Candidate'
    freebie_offer.offer_kind = OfferKind.FREEBIE
    freebie_offer.price_before_minor = 1200
    freebie_offer.price_after_minor = 0
    freebie_offer.discount_percent = 100
    repo.replace_queue('planned', [(150.0, freebie_offer, make_decision_json('breaking_freebie', score=150.0))], created_at=now)

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    selection = use_case.inspect_selection(now, now, requested_post_mode='single_discount')
    target = asyncio.run(use_case.preview_send_test_target(now, now, requested_post_mode='single_discount'))

    assert selection.selected_candidate is None
    assert selection.blocker_reason == 'no_candidates_for_post_mode'
    assert selection.blocker_detail == 'Нет кандидатов для выбранного режима: Одиночные скидки'
    assert target.truth_ready is False
    assert target.would_send is False
    assert target.blocker_reason == 'no_candidates_for_post_mode'
    assert target.blocker_detail == 'Нет кандидатов для выбранного режима: Одиночные скидки'


def test_publish_next_inspect_selection_skips_already_published_queue_rows(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path, dry_run=True)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')

    published_offer = make_offer()
    published_offer.offer_id = 'steam:413150'
    published_offer.game_id = '413150'
    published_offer.franchise_key = '413150'
    published_offer.title = 'Stardew Valley'

    fallback_offer = make_offer()
    fallback_offer.offer_id = 'steam:264710'
    fallback_offer.game_id = '264710'
    fallback_offer.franchise_key = '264710'
    fallback_offer.title = 'Subnautica'

    repo.replace_queue(
        'planned',
        [
            (150.0, published_offer, make_decision_json('high_value_discount', score=150.0)),
            (120.0, fallback_offer, make_decision_json('high_value_discount', score=120.0)),
        ],
    )
    repo.record_publication(published_offer, 'high_value_discount', 183)

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    inspection = use_case.inspect_selection(datetime(2026, 3, 20, 12, 0), datetime(2026, 3, 20, 12, 0))
    target = asyncio.run(use_case.preview_send_test_target(datetime(2026, 3, 20, 12, 0), datetime(2026, 3, 20, 12, 0)))

    assert inspection.selected_candidate is not None
    assert inspection.selected_candidate.offer_id == 'steam:264710'
    blocked_stardew = next(
        candidate
        for candidate in inspection.blocked_candidates
        if candidate.offer_id == 'steam:413150' and candidate.blocker_reason == 'already_published'
    )
    assert 'blocked:already_published_recently' in str(blocked_stardew.blocker_detail)
    assert target.candidate is not None
    assert target.candidate['offer_id'] == 'steam:264710'


def test_publish_next_allows_repeat_same_game_when_price_improves_meaningfully(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path, dry_run=True)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')

    improved_offer = make_offer()
    improved_offer.offer_id = 'steam:413150'
    improved_offer.game_id = '413150'
    improved_offer.franchise_key = '413150'
    improved_offer.title = 'Stardew Valley'
    improved_offer.price_after_minor = 900
    improved_offer.discount_percent = 80

    previously_published_offer = make_offer()
    previously_published_offer.offer_id = 'steam:413150'
    previously_published_offer.game_id = '413150'
    previously_published_offer.franchise_key = '413150'
    previously_published_offer.title = 'Stardew Valley'
    previously_published_offer.price_after_minor = 1900
    previously_published_offer.discount_percent = 60

    repo.replace_queue(
        'planned',
        [(150.0, improved_offer, make_decision_json('high_value_discount', score=150.0))],
    )
    repo.record_publication(previously_published_offer, 'high_value_discount', 183)

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    inspection = use_case.inspect_selection(datetime(2026, 3, 20, 12, 0), datetime(2026, 3, 20, 12, 0))
    target = asyncio.run(use_case.preview_send_test_target(datetime(2026, 3, 20, 12, 0), datetime(2026, 3, 20, 12, 0)))

    assert inspection.selected_candidate is not None
    assert inspection.selected_candidate.offer_id == 'steam:413150'
    assert all(candidate.offer_id != 'steam:413150' for candidate in inspection.blocked_candidates)
    assert target.candidate is not None
    assert target.candidate['offer_id'] == 'steam:413150'


def test_publish_next_blocks_only_already_published_candidate_when_no_alternative_exists(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path, dry_run=True)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')

    published_offer = make_offer()
    published_offer.offer_id = 'steam:413150'
    published_offer.game_id = '413150'
    published_offer.franchise_key = '413150'
    published_offer.title = 'Stardew Valley'

    repo.replace_queue(
        'planned',
        [(150.0, published_offer, make_decision_json('high_value_discount', score=150.0))],
    )
    repo.record_publication(published_offer, 'high_value_discount', 183)

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    inspection = use_case.inspect_selection(datetime(2026, 3, 20, 12, 0), datetime(2026, 3, 20, 12, 0))
    target = asyncio.run(use_case.preview_send_test_target(datetime(2026, 3, 20, 12, 0), datetime(2026, 3, 20, 12, 0)))

    assert inspection.selected_candidate is None
    assert inspection.blocker_reason == 'already_published'
    assert any(
        candidate.offer_id == 'steam:413150'
        and candidate.blocker_reason == 'already_published'
        and 'blocked:already_published_recently' in str(candidate.blocker_detail)
        for candidate in inspection.blocked_candidates
    )
    assert target.truth_ready is False
    assert target.would_send is False
    assert target.blocker_reason == 'already_published'
    assert target.candidate is None


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


def test_operator_truth_report_emits_selection_candidate_rows_contract(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path, dry_run=True)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')
    now = datetime(2026, 3, 20, 12, 0)

    blocked_offer = make_offer()
    blocked_offer.offer_id = 'steam:blocked-row'
    blocked_offer.game_id = 'blocked-row'
    blocked_offer.franchise_key = 'blocked-row'
    blocked_offer.title = 'Blocked Candidate'

    recommended_offer = make_offer()
    recommended_offer.offer_id = 'steam:recommended-row'
    recommended_offer.game_id = 'recommended-row'
    recommended_offer.franchise_key = 'recommended-row'
    recommended_offer.title = 'Recommended Candidate'
    recommended_offer.price_before_minor = 35000
    recommended_offer.price_after_minor = 17500
    recommended_offer.discount_percent = 50
    recommended_offer.review_score = 94
    recommended_offer.review_count = 42000

    ready_offer = make_offer()
    ready_offer.offer_id = 'steam:ready-row'
    ready_offer.game_id = 'ready-row'
    ready_offer.franchise_key = 'ready-row'
    ready_offer.title = 'Ready Candidate'

    reserve_offer = make_offer()
    reserve_offer.offer_id = 'steam:reserve-row'
    reserve_offer.game_id = 'reserve-row'
    reserve_offer.franchise_key = 'reserve-row'
    reserve_offer.title = 'Reserve Candidate'

    blocked_decision = make_decision_json('game_of_the_day', score=180.0)
    recommended_decision = make_decision_json('high_value_discount', score=130.0)
    ready_decision = make_decision_json('high_value_discount', score=120.0)
    reserve_decision = make_decision_json('high_value_discount', score=90.0, queue_bucket='reserve')
    reserve_decision['selection_outcome'] = 'reserve'
    reserve_decision['recommended_post_mode'] = 'roundup_candidate'

    repo.increment_daily_lane('2026-03-20', 'game_of_the_day')
    repo.replace_queue(
        'planned',
        [
            (180.0, blocked_offer, blocked_decision),
            (130.0, recommended_offer, recommended_decision),
            (120.0, ready_offer, ready_decision),
        ],
        created_at=now,
    )
    repo.replace_queue('reserve', [(90.0, reserve_offer, reserve_decision)], created_at=now)

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    selection = use_case.inspect_selection(now, now)
    target = asyncio.run(use_case.preview_send_test_target(now, now))
    plan = QueuePlan(
        planned=[
            make_candidate(blocked_offer, blocked_decision, 180.0),
            make_candidate(recommended_offer, recommended_decision, 130.0),
            make_candidate(ready_offer, ready_decision, 120.0),
        ],
        reserve=[make_candidate(reserve_offer, reserve_decision, 90.0)],
        metrics={'offers.ingested_total': 4, 'offers.enriched_total': 4},
        context={
            'source': 'current_queue',
            'queue_snapshot_at': now.isoformat(),
            'selection_summary': {'solo_post': 2, 'roundup_candidate': 1, 'capacity_hold': 0},
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
    rows = {row['offer_id']: row for row in payload['selection']['candidate_rows']}

    assert len(payload['selection']['candidate_rows']) == 4
    assert rows['steam:recommended-row']['candidate_id'] == rows['steam:recommended-row']['row_id']
    assert rows['steam:recommended-row']['status'] == 'recommended'
    assert rows['steam:ready-row']['status'] == 'ready'
    assert rows['steam:reserve-row']['status'] == 'reserve'
    assert rows['steam:blocked-row']['status'] == 'blocked'
    assert rows['steam:blocked-row']['blocker_reason'] == 'daily_lane_cap_reached'
    assert rows['steam:blocked-row']['blocker_detail'] == 'lane=game_of_the_day published_today=1'
    assert rows['steam:recommended-row']['source'] == 'steam'
    assert rows['steam:recommended-row']['platform'] == 'steam'
    assert rows['steam:recommended-row']['post_type'] == 'discount'
    assert rows['steam:recommended-row']['current_price'] == 17500
    assert rows['steam:recommended-row']['old_price'] == 35000
    assert rows['steam:recommended-row']['discount'] == 50
    assert rows['steam:recommended-row']['reviews'] == 42000
    assert rows['steam:recommended-row']['positive_pct'] == 94
    assert rows['steam:recommended-row']['already_published'] is False


def test_operator_truth_report_candidate_rows_mark_already_published_status(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path, dry_run=True)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')
    now = datetime(2026, 3, 20, 12, 0)

    published_offer = make_offer()
    published_offer.offer_id = 'steam:413150'
    published_offer.game_id = '413150'
    published_offer.franchise_key = '413150'
    published_offer.title = 'Stardew Valley'

    fallback_offer = make_offer()
    fallback_offer.offer_id = 'steam:264710'
    fallback_offer.game_id = '264710'
    fallback_offer.franchise_key = '264710'
    fallback_offer.title = 'Subnautica'

    published_decision = make_decision_json('high_value_discount', score=150.0)
    fallback_decision = make_decision_json('high_value_discount', score=120.0)
    repo.replace_queue(
        'planned',
        [
            (150.0, published_offer, published_decision),
            (120.0, fallback_offer, fallback_decision),
        ],
        created_at=now,
    )
    repo.record_publication(published_offer, 'high_value_discount', 183)

    use_case = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    selection = use_case.inspect_selection(now, now)
    target = asyncio.run(use_case.preview_send_test_target(now, now))
    plan = QueuePlan(
        planned=[
            make_candidate(published_offer, published_decision, 150.0),
            make_candidate(fallback_offer, fallback_decision, 120.0),
        ],
        reserve=[],
        metrics={'offers.ingested_total': 2, 'offers.enriched_total': 2},
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
    rows = {row['offer_id']: row for row in payload['selection']['candidate_rows']}

    assert rows['steam:413150']['status'] == 'already_published'
    assert rows['steam:413150']['already_published'] is True
    assert rows['steam:413150']['blocker_reason'] == 'already_published'
    assert 'blocked:already_published_recently' in str(rows['steam:413150']['blocker_detail'])
    assert rows['steam:264710']['status'] == 'recommended'


def test_preview_selected_builds_new_preview_report_for_exact_ready_candidate(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path, dry_run=True)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')
    source_now = datetime(2026, 3, 20, 12, 0)
    selected_now = datetime(2026, 3, 20, 12, 1)

    recommended_offer = make_offer()
    recommended_offer.offer_id = 'steam:recommended-preview-selected'
    recommended_offer.game_id = 'recommended-preview-selected'
    recommended_offer.franchise_key = 'recommended-preview-selected'
    recommended_offer.title = 'Recommended Source Candidate'

    ready_offer = make_offer()
    ready_offer.offer_id = 'steam:ready-preview-selected'
    ready_offer.game_id = 'ready-preview-selected'
    ready_offer.franchise_key = 'ready-preview-selected'
    ready_offer.title = 'Ready Source Candidate'

    recommended_decision = make_decision_json('high_value_discount', score=140.0)
    ready_decision = make_decision_json('high_value_discount', score=120.0)
    repo.replace_queue(
        'planned',
        [
            (140.0, recommended_offer, recommended_decision),
            (120.0, ready_offer, ready_decision),
        ],
        created_at=source_now,
    )

    selector = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    selection = selector.inspect_selection(source_now, source_now)
    target = asyncio.run(selector.preview_send_test_target(source_now, source_now))
    plan = QueuePlan(
        planned=[
            make_candidate(recommended_offer, recommended_decision, 140.0),
            make_candidate(ready_offer, ready_decision, 120.0),
        ],
        reserve=[],
        metrics={'offers.ingested_total': 2, 'offers.enriched_total': 2},
        context={
            'source': 'current_queue',
            'queue_snapshot_at': source_now.isoformat(),
            'selection_summary': {'solo_post': 2, 'roundup_candidate': 0, 'capacity_hold': 0},
        },
    )
    reporter = OperatorTruthReporter(repo, AnalyticsArtifactWriter(tmp_path / 'analytics'))
    source_report = reporter.emit(
        now_utc=source_now,
        mode='preview',
        settings=settings,
        plan=plan,
        selection=selection,
        target=target,
    )
    assert source_report.json_path is not None and source_report.json_path.exists()

    source_payload = json.loads(source_report.json_path.read_text(encoding='utf-8'))
    ready_row = next(
        row
        for row in source_payload['selection']['candidate_rows']
        if row['offer_id'] == 'steam:ready-preview-selected'
    )

    use_case = PreviewSelectedUseCase(
        settings=settings,
        repositories=repo,
        selector=selector,
        reporter=reporter,
    )
    result = asyncio.run(
        use_case.execute(
            report_path=source_report.json_path,
            candidate_id=int(ready_row['candidate_id']),
            now_utc=selected_now,
            now_local=selected_now,
        )
    )

    assert result.created_report is True
    assert result.reason == 'selected_preview_ready'
    assert result.report_path is not None and result.report_path.exists()
    generated = json.loads(result.report_path.read_text(encoding='utf-8'))
    assert generated['send_test_target']['candidate']['row_id'] == ready_row['row_id']
    assert generated['send_test_target']['candidate']['offer_id'] == 'steam:ready-preview-selected'
    assert generated['selection']['selected_candidate']['row_id'] == ready_row['row_id']
    assert generated['pinned_publish']['candidate']['row_id'] == ready_row['row_id']
    assert generated['pinned_publish']['candidate']['offer_id'] == 'steam:ready-preview-selected'
    generated_rows = {row['offer_id']: row for row in generated['selection']['candidate_rows']}
    assert generated_rows['steam:ready-preview-selected']['status'] == 'recommended'
    assert generated_rows['steam:recommended-preview-selected']['status'] == 'ready'


def test_preview_selected_rejects_blocked_candidate_from_source_report(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path, dry_run=True)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')
    source_now = datetime(2026, 3, 20, 12, 0)
    selected_now = datetime(2026, 3, 20, 12, 1)

    blocked_offer = make_offer()
    blocked_offer.offer_id = 'steam:blocked-preview-selected'
    blocked_offer.game_id = 'blocked-preview-selected'
    blocked_offer.franchise_key = 'blocked-preview-selected'
    blocked_offer.title = 'Blocked Source Candidate'

    ready_offer = make_offer()
    ready_offer.offer_id = 'steam:ready-other'
    ready_offer.game_id = 'ready-other'
    ready_offer.franchise_key = 'ready-other'
    ready_offer.title = 'Ready Other Candidate'

    repo.increment_daily_lane('2026-03-20', 'game_of_the_day')
    blocked_decision = make_decision_json('game_of_the_day', score=180.0)
    ready_decision = make_decision_json('high_value_discount', score=120.0)
    repo.replace_queue(
        'planned',
        [
            (180.0, blocked_offer, blocked_decision),
            (120.0, ready_offer, ready_decision),
        ],
        created_at=source_now,
    )

    selector = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    selection = selector.inspect_selection(source_now, source_now)
    target = asyncio.run(selector.preview_send_test_target(source_now, source_now))
    reporter = OperatorTruthReporter(repo, AnalyticsArtifactWriter(tmp_path / 'analytics'))
    source_report = reporter.emit(
        now_utc=source_now,
        mode='preview',
        settings=settings,
        plan=QueuePlan(
            planned=[
                make_candidate(blocked_offer, blocked_decision, 180.0),
                make_candidate(ready_offer, ready_decision, 120.0),
            ],
            reserve=[],
            metrics={},
            context={'source': 'current_queue', 'selection_summary': {'capacity_hold': 0}},
        ),
        selection=selection,
        target=target,
    )
    assert source_report.json_path is not None and source_report.json_path.exists()

    source_payload = json.loads(source_report.json_path.read_text(encoding='utf-8'))
    blocked_row = next(
        row
        for row in source_payload['selection']['candidate_rows']
        if row['offer_id'] == 'steam:blocked-preview-selected'
    )

    use_case = PreviewSelectedUseCase(
        settings=settings,
        repositories=repo,
        selector=selector,
        reporter=reporter,
    )
    result = asyncio.run(
        use_case.execute(
            report_path=source_report.json_path,
            candidate_id=int(blocked_row['candidate_id']),
            now_utc=selected_now,
            now_local=selected_now,
        )
    )

    assert result.created_report is False
    assert result.reason == 'candidate_blocked'
    assert result.blocker_category == 'queue_state'
    assert 'daily_lane_cap_reached' in str(result.blocker_detail)


def test_preview_selected_rejects_already_published_candidate_from_source_report(tmp_path: Path) -> None:
    settings = make_test_settings(tmp_path, dry_run=True)
    repo = Repositories(settings.db_path)
    repo.initialize()
    image_path = tmp_path / 'card.png'
    image_path.write_bytes(b'card')
    source_now = datetime(2026, 3, 20, 12, 0)
    selected_now = datetime(2026, 3, 20, 12, 1)

    published_offer = make_offer()
    published_offer.offer_id = 'steam:413150'
    published_offer.game_id = '413150'
    published_offer.franchise_key = '413150'
    published_offer.title = 'Stardew Valley'

    fallback_offer = make_offer()
    fallback_offer.offer_id = 'steam:264710'
    fallback_offer.game_id = '264710'
    fallback_offer.franchise_key = '264710'
    fallback_offer.title = 'Subnautica'

    published_decision = make_decision_json('high_value_discount', score=150.0)
    fallback_decision = make_decision_json('high_value_discount', score=120.0)
    repo.replace_queue(
        'planned',
        [
            (150.0, published_offer, published_decision),
            (120.0, fallback_offer, fallback_decision),
        ],
        created_at=source_now,
    )
    repo.record_publication(published_offer, 'high_value_discount', 183)

    selector = PublishNextUseCase(settings, repo, StaticRenderUseCase(image_path), RecordingPublisher())
    selection = selector.inspect_selection(source_now, source_now)
    target = asyncio.run(selector.preview_send_test_target(source_now, source_now))
    reporter = OperatorTruthReporter(repo, AnalyticsArtifactWriter(tmp_path / 'analytics'))
    source_report = reporter.emit(
        now_utc=source_now,
        mode='preview',
        settings=settings,
        plan=QueuePlan(
            planned=[
                make_candidate(published_offer, published_decision, 150.0),
                make_candidate(fallback_offer, fallback_decision, 120.0),
            ],
            reserve=[],
            metrics={},
            context={'source': 'current_queue', 'selection_summary': {'capacity_hold': 0}},
        ),
        selection=selection,
        target=target,
    )
    assert source_report.json_path is not None and source_report.json_path.exists()

    source_payload = json.loads(source_report.json_path.read_text(encoding='utf-8'))
    published_row = next(
        row
        for row in source_payload['selection']['candidate_rows']
        if row['offer_id'] == 'steam:413150'
    )

    use_case = PreviewSelectedUseCase(
        settings=settings,
        repositories=repo,
        selector=selector,
        reporter=reporter,
    )
    result = asyncio.run(
        use_case.execute(
            report_path=source_report.json_path,
            candidate_id=int(published_row['candidate_id']),
            now_utc=selected_now,
            now_local=selected_now,
        )
    )

    assert result.created_report is False
    assert result.reason == 'already_published'
    assert result.blocker_category == 'queue_state'
    assert 'blocked:already_published_recently' in str(result.blocker_detail)


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
    assert set(pinned_publish['candidate']) == {
        'row_id',
        'bucket',
        'lane',
        'content_family',
        'source',
        'offer_id',
        'title',
        'template_id',
        'score',
        'total_priority',
        'selected',
        'eligible',
        'blocker_reason',
        'blocker_detail',
        'recommended_post_mode',
        'publish_priority',
        'editorial_adjustment',
        'decision_reasons',
        'quality_reasons',
        'store_url',
        'created_at',
    }
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

        async def preview_offline(self, incoming_bundle: OfflineSnapshotBundle, post_mode: str = 'any') -> None:
            captured['bundle'] = incoming_bundle
            captured['db_path'] = self.settings.db_path
            captured['post_mode'] = post_mode

    monkeypatch.setattr(main_module.AppSettings, 'from_env', staticmethod(fake_from_env))
    monkeypatch.setattr(main_module, 'OfflineValidationSnapshotManager', FakeSnapshotManager)
    monkeypatch.setattr(main_module, 'BotRuntime', FakeRuntime)
    monkeypatch.delenv('BOT_TOKEN', raising=False)
    monkeypatch.delenv('CHANNEL_USERNAME', raising=False)
    monkeypatch.setattr(sys, 'argv', ['dealbot.main', '--preview', '--offline-snapshot', 'golden'])

    asyncio.run(main_module.async_main())

    assert captured['bundle'] == bundle
    assert captured['db_path'] == db_path
    assert captured['post_mode'] == 'any'
