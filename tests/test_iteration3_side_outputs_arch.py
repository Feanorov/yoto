from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from application.use_cases.generate_analytics_artifacts import GenerateAnalyticsArtifactsUseCase
from application.use_cases.generate_video_manifests import GenerateVideoManifestsUseCase
from application.use_cases.plan_queue import PlannedCandidate, QueuePlan
from application.use_cases.publish_next import PublishResult
from infrastructure.analytics.artifact_writer import AnalyticsArtifactWriter
from infrastructure.db.repositories import Repositories
from infrastructure.video.manifest_writer import VideoManifestWriter
from domain.entities.offer import OfferKind, OfferSource

from .test_caption_builder_arch import make_offer


def make_candidate(
    offer_id: str,
    title: str,
    *,
    lane: str = 'high_value_discount',
    queue_bucket: str = 'planned',
    score: float = 123.45,
    manual_force_override: bool = False,
    sale_event: dict | None = None,
    diversity_constraints: list[str] | None = None,
) -> PlannedCandidate:
    offer = make_offer()
    offer.offer_id = offer_id
    offer.source_ref = offer_id.split(':', 1)[-1]
    offer.game_id = offer.source_ref
    offer.franchise_key = offer.source_ref.replace(':', '-')
    offer.title = title
    debug = {
        'sale_event': sale_event or {},
        'diversity_constraints': diversity_constraints or [],
        'manual_control_reasons': ['whitelist'] if manual_force_override else [],
    }
    return PlannedCandidate(
        score=score,
        offer=offer,
        decision_json={
            'lane': lane,
            'template_id': 'steam_discount',
            'must_ship': False,
            'queue_bucket': queue_bucket,
            'decision_reasons': [lane],
            'quality_reasons': ['review_threshold'],
            'dedup_reason': 'new_offer',
            'is_final_push': lane == 'final_push',
            'is_historical_best': False,
            'price_improved_minor': 0,
            'score': score,
            'previous_price_minor': None,
            'previous_posted_at': None,
            'best_price_minor': None,
            'manual_force_override': manual_force_override,
            'debug': debug,
        },
    )


def test_generate_analytics_artifacts_writes_files_and_db_rows(tmp_path: Path) -> None:
    repo = Repositories(tmp_path / 'repo.sqlite3')
    repo.initialize()
    writer = AnalyticsArtifactWriter(tmp_path / 'analytics')
    use_case = GenerateAnalyticsArtifactsUseCase(repo, writer)
    now = datetime(2026, 3, 10, 12, 0)
    planned = make_candidate(
        'steam:42',
        'Mystery of the Lantern',
        sale_event={'mode': 'auto', 'active': False, 'linked': True},
        diversity_constraints=['source_alternation'],
    )
    reserve = make_candidate(
        'steam:43',
        'Action Blast',
        queue_bucket='reserve',
        score=98.0,
        manual_force_override=True,
    )
    plan = QueuePlan(
        planned=[planned],
        reserve=[reserve],
        metrics={'sale_event.context_active': 1},
        context={
            'sale_event_mode': 'auto',
            'active': True,
            'active_event_offer_ids': ['event:visual-fest'],
            'phrase_tokens': ['steam_visual_novel_fest'],
            'word_tokens': ['visual', 'novel', 'fest'],
        },
    )
    publish_result = PublishResult(
        offer_id='steam:42',
        title='Mystery of the Lantern',
        lane='high_value_discount',
        image_path=tmp_path / 'card.png',
        message_id=777,
        published=True,
        reason='published',
        analytics={
            'selection': {
                'lane': 'high_value_discount',
                'queue_bucket': 'planned',
                'template_id': 'steam_discount',
                'score': 123.45,
                'decision_reasons': ['high_value_discount'],
                'quality_reasons': ['review_threshold'],
                'dedup_reason': 'new_offer',
                'event_sale_influence': {'mode': 'auto', 'active': False, 'linked': True},
                'diversity_constraints': ['source_alternation'],
                'manual_override': {'forced': False, 'reasons': []},
            },
            'render': {
                'image_path': str(tmp_path / 'card.png'),
                'template_id': 'steam_discount',
                'assets_used': ['https://example.com/header.png'],
                'caption_hash': 'caption-hash',
                'image_hash': 'image-hash',
                'render_diagnostics': {'warnings': []},
            },
            'publish_outcome': {
                'published': True,
                'reason': 'published',
                'message_id': 777,
                'outbox_status': 'published',
            },
        },
    )

    use_case.execute(now, plan, publish_result)

    with repo.connect() as connection:
        rows = connection.execute(
            'SELECT artifact_type, json_path, csv_path FROM analytics_artifacts ORDER BY artifact_type ASC'
        ).fetchall()

    assert len(rows) == 2
    planning_row = next(row for row in rows if row['artifact_type'] == 'planning_snapshot')
    publish_row = next(row for row in rows if row['artifact_type'] == 'publish_outcome')
    planning_json_path = Path(planning_row['json_path'])
    planning_csv_path = Path(planning_row['csv_path'])
    publish_json_path = Path(publish_row['json_path'])
    publish_csv_path = Path(publish_row['csv_path'])
    assert planning_json_path.exists()
    assert planning_csv_path.exists()
    assert publish_json_path.exists()
    assert publish_csv_path.exists()
    assert use_case.metrics.snapshot() == {
        'analytics.files.success': 2,
        'analytics.db.success': 2,
    }

    planning_payload = json.loads(planning_json_path.read_text(encoding='utf-8'))
    publish_payload = json.loads(publish_json_path.read_text(encoding='utf-8'))
    assert planning_payload['context']['active_event_offer_ids'] == ['event:visual-fest']
    assert planning_payload['planned'][0]['event_sale_influence']['linked'] is True
    assert publish_payload['publish_outcome']['message_id'] == 777
    assert publish_payload['selection']['event_sale_influence']['mode'] == 'auto'

    with planning_csv_path.open(encoding='utf-8', newline='') as handle:
        planning_rows = list(csv.DictReader(handle))
    with publish_csv_path.open(encoding='utf-8', newline='') as handle:
        publish_rows = list(csv.DictReader(handle))

    assert len(planning_rows) == 2
    assert any(row['bucket'] == 'planned' and '"linked": true' in row['event_sale_influence'] for row in planning_rows)
    assert publish_rows[0]['offer_id'] == 'steam:42'
    assert '"linked": true' in publish_rows[0]['event_sale_influence']


def _generate_manifest_payload(
    tmp_path: Path,
    candidate: PlannedCandidate,
    *,
    context: dict | None = None,
) -> tuple[dict, dict[str, int]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    repo = Repositories(tmp_path / 'repo.sqlite3')
    repo.initialize()
    writer = VideoManifestWriter(tmp_path / 'video_manifests')
    use_case = GenerateVideoManifestsUseCase(repo, writer)
    now = datetime(2026, 3, 10, 12, 0)
    plan = QueuePlan(
        planned=[candidate],
        reserve=[],
        metrics={'sale_event.context_active': 1},
        context=context or {},
    )

    use_case.execute(now, plan)

    with repo.connect() as connection:
        row = connection.execute('SELECT json_path FROM video_manifests').fetchone()

    assert row is not None
    manifest_path = Path(row['json_path'])
    assert manifest_path.exists()
    return json.loads(manifest_path.read_text(encoding='utf-8')), use_case.metrics.snapshot()


def test_generate_video_manifests_writes_sidecar_with_plan_context(tmp_path: Path) -> None:
    candidate = make_candidate(
        'steam:99',
        'A Very Long Deal Title That Needs To Be Shortened For Vertical Video Scripts',
        lane='final_push',
        score=140.0,
        sale_event={'mode': 'auto', 'active': False, 'linked': True},
    )

    payload, metrics = _generate_manifest_payload(
        tmp_path / 'base',
        candidate,
        context={
            'sale_event_mode': 'auto',
            'active': True,
            'active_event_offer_ids': ['event:visual-fest'],
        },
    )

    assert metrics == {
        'video_manifest.files.success': 1,
        'video_manifest.db.success': 1,
        'video_manifest.generated': 1,
    }
    assert payload['short_title'].endswith('...')
    assert len(payload['short_title']) <= 56
    assert payload['hook_line'] == '\u0424\u0456\u043d\u0430\u043b\u044c\u043d\u0438\u0439 \u0448\u0430\u043d\u0441 \u0437\u0432\u0435\u0440\u043d\u0443\u0442\u0438 \u0443\u0432\u0430\u0433\u0443 \u043d\u0430 \u0446\u044e \u043f\u0440\u043e\u043f\u043e\u0437\u0438\u0446\u0456\u044e.'
    assert payload['urgency_line'] == '\u0424\u0456\u043d\u0430\u043b\u044c\u043d\u0438\u0439 \u0448\u0430\u043d\u0441: \u0434\u043e 12 \u0431\u0435\u0440\u0435\u0437\u043d\u044f 2026, 18:00.'
    assert payload['template_hint'] == 'deadline-push'
    assert payload['asset_refs'] == {'game_image': 'https://example.com/header.png', 'background': 'https://example.com/shot.png'}
    assert payload['context']['store'] == 'Steam'
    assert payload['context']['sale_event']['linked'] is True
    assert payload['context']['plan_sale_context']['active_event_offer_ids'] == ['event:visual-fest']


def test_generate_video_manifests_prefers_cyrillic_epic_description(tmp_path: Path) -> None:
    candidate = make_candidate('epic:1', 'Turnip Boy Robs a Bank', lane='breaking_freebie')
    candidate.offer.source = OfferSource.EPIC
    candidate.offer.offer_kind = OfferKind.FREEBIE
    candidate.offer.store_url = 'https://store.epicgames.com/uk/p/test-game'
    candidate.offer.price_before_minor = 69900
    candidate.offer.price_after_minor = 0
    candidate.offer.discount_percent = 100
    candidate.offer.short_description = '\u041a\u043e\u043e\u043f\u0435\u0440\u0430\u0442\u0438\u0432\u043d\u0438\u0439 roguelite \u043f\u0440\u043e \u0445\u0430\u043e\u0442\u0438\u0447\u043d\u0456 \u043f\u043e\u0433\u0440\u0430\u0431\u0443\u0432\u0430\u043d\u043d\u044f \u0442\u0430 \u0432\u0442\u0435\u0447\u0456.'
    candidate.offer.description = candidate.offer.short_description

    payload, _ = _generate_manifest_payload(tmp_path / 'epic-with-desc', candidate)

    assert payload['summary_line'] == '\u041a\u043e\u043e\u043f\u0435\u0440\u0430\u0442\u0438\u0432\u043d\u0438\u0439 roguelite \u043f\u0440\u043e \u0445\u0430\u043e\u0442\u0438\u0447\u043d\u0456 \u043f\u043e\u0433\u0440\u0430\u0431\u0443\u0432\u0430\u043d\u043d\u044f \u0442\u0430 \u0432\u0442\u0435\u0447\u0456.'
    assert payload['hook_line'] == '\u0411\u0435\u0437\u043a\u043e\u0448\u0442\u043e\u0432\u043d\u0430 \u0440\u043e\u0437\u0434\u0430\u0447\u0430 \u0432 Epic \u0432\u0436\u0435 \u0430\u043a\u0442\u0438\u0432\u043d\u0430.'
    assert payload['template_hint'] == 'freebie-flash'


def test_generate_video_manifests_falls_back_for_epic_without_description(tmp_path: Path) -> None:
    candidate = make_candidate('epic:2', 'Turnip Boy Robs a Bank', lane='breaking_freebie')
    candidate.offer.source = OfferSource.EPIC
    candidate.offer.offer_kind = OfferKind.FREEBIE
    candidate.offer.store_url = 'https://store.epicgames.com/uk/p/test-game'
    candidate.offer.price_before_minor = 69900
    candidate.offer.price_after_minor = 0
    candidate.offer.discount_percent = 100
    candidate.offer.short_description = ''
    candidate.offer.description = ''
    candidate.offer.tags = ['Co-op', 'Roguelite']
    candidate.offer.genres = ['Action']

    payload, _ = _generate_manifest_payload(tmp_path / 'epic-no-desc', candidate)

    assert 'Turnip Boy Robs a Bank' in payload['summary_line']
    assert 'Epic Games Store' in payload['summary_line']
    assert payload['hook_line'] == '\u0411\u0435\u0437\u043a\u043e\u0448\u0442\u043e\u0432\u043d\u0430 \u0440\u043e\u0437\u0434\u0430\u0447\u0430 \u0432 Epic \u0432\u0436\u0435 \u0430\u043a\u0442\u0438\u0432\u043d\u0430.'


def test_generate_video_manifests_prefers_short_description_for_steam_discount(tmp_path: Path) -> None:
    candidate = make_candidate('steam:77', 'Darkest Ledger')
    candidate.offer.short_description = '\u0422\u0430\u043a\u0442\u0438\u0447\u043d\u0430 RPG \u043f\u0440\u043e \u0441\u043a\u043b\u0430\u0434\u043d\u0456 \u0432\u0438\u0431\u043e\u0440\u0438, \u0435\u043a\u0441\u043f\u0435\u0434\u0438\u0446\u0456\u0457 \u0442\u0430 \u0442\u0435\u043c\u043d\u0435 \u0444\u0435\u043d\u0442\u0435\u0437\u0456.'
    candidate.offer.description = '\u041f\u043e\u0432\u043d\u0438\u0439 \u043e\u043f\u0438\u0441, \u044f\u043a\u0438\u0439 \u043d\u0435 \u043c\u0430\u0454 \u0437\u2019\u044f\u0432\u0438\u0442\u0438\u0441\u044f \u0437\u0430\u043c\u0456\u0441\u0442\u044c \u043a\u043e\u0440\u043e\u0442\u043a\u043e\u0433\u043e.'

    payload, _ = _generate_manifest_payload(tmp_path / 'steam-short-desc', candidate)

    assert payload['summary_line'] == '\u0422\u0430\u043a\u0442\u0438\u0447\u043d\u0430 RPG \u043f\u0440\u043e \u0441\u043a\u043b\u0430\u0434\u043d\u0456 \u0432\u0438\u0431\u043e\u0440\u0438, \u0435\u043a\u0441\u043f\u0435\u0434\u0438\u0446\u0456\u0457 \u0442\u0430 \u0442\u0435\u043c\u043d\u0435 \u0444\u0435\u043d\u0442\u0435\u0437\u0456.'
    assert '\u041f\u043e\u0432\u043d\u0438\u0439 \u043e\u043f\u0438\u0441, \u044f\u043a\u0438\u0439 \u043d\u0435 \u043c\u0430\u0454 \u0437\u2019\u044f\u0432\u0438\u0442\u0438\u0441\u044f' not in payload['summary_line']


def test_generate_video_manifests_adds_final_push_copy_for_lane_and_flag(tmp_path: Path) -> None:
    lane_candidate = make_candidate('steam:88', 'Final Push Lane', lane='final_push')
    flag_candidate = make_candidate('steam:89', 'Final Push Flag', lane='high_value_discount')
    flag_candidate.decision_json['is_final_push'] = True

    lane_payload, _ = _generate_manifest_payload(tmp_path / 'final-push-lane', lane_candidate)
    flag_payload, _ = _generate_manifest_payload(tmp_path / 'final-push-flag', flag_candidate)

    assert lane_payload['hook_line'] == '\u0424\u0456\u043d\u0430\u043b\u044c\u043d\u0438\u0439 \u0448\u0430\u043d\u0441 \u0437\u0432\u0435\u0440\u043d\u0443\u0442\u0438 \u0443\u0432\u0430\u0433\u0443 \u043d\u0430 \u0446\u044e \u043f\u0440\u043e\u043f\u043e\u0437\u0438\u0446\u0456\u044e.'
    assert lane_payload['urgency_line'] == '\u0424\u0456\u043d\u0430\u043b\u044c\u043d\u0438\u0439 \u0448\u0430\u043d\u0441: \u0434\u043e 12 \u0431\u0435\u0440\u0435\u0437\u043d\u044f 2026, 18:00.'
    assert flag_payload['hook_line'] == '\u0424\u0456\u043d\u0430\u043b\u044c\u043d\u0438\u0439 \u0448\u0430\u043d\u0441 \u0437\u0432\u0435\u0440\u043d\u0443\u0442\u0438 \u0443\u0432\u0430\u0433\u0443 \u043d\u0430 \u0446\u044e \u043f\u0440\u043e\u043f\u043e\u0437\u0438\u0446\u0456\u044e.'
    assert flag_payload['urgency_line'] == '\u0424\u0456\u043d\u0430\u043b\u044c\u043d\u0438\u0439 \u0448\u0430\u043d\u0441: \u0434\u043e 12 \u0431\u0435\u0440\u0435\u0437\u043d\u044f 2026, 18:00.'


def test_generate_video_manifests_event_uses_safe_fallback(tmp_path: Path) -> None:
    candidate = make_candidate('event:fest', 'Steam Strategy Fest', lane='event_festival')
    candidate.offer.source = OfferSource.EVENT
    candidate.offer.offer_kind = OfferKind.FESTIVAL
    candidate.offer.short_description = ''
    candidate.offer.description = ''
    candidate.offer.tags = []
    candidate.offer.genres = []
    candidate.offer.price_before_minor = None
    candidate.offer.price_after_minor = None
    candidate.offer.discount_percent = 0

    payload, _ = _generate_manifest_payload(tmp_path / 'event-fallback', candidate)

    assert 'Steam Strategy Fest' in payload['summary_line']
    assert '\u0442\u0435\u043c\u0430\u0442\u0438\u0447\u043d\u0430 \u043f\u043e\u0434\u0456\u044f \u0432 Steam' in payload['summary_line']
    assert payload['template_hint'] == 'event-countdown'


def test_generate_video_manifests_handles_empty_data_without_shape_changes(tmp_path: Path) -> None:
    candidate = make_candidate('steam:111', 'Sparse Offer')
    candidate.offer.short_description = ''
    candidate.offer.description = ''
    candidate.offer.tags = []
    candidate.offer.genres = []
    candidate.offer.price_before_minor = None
    candidate.offer.price_after_minor = None
    candidate.offer.review_score = None
    candidate.offer.review_count = None
    candidate.offer.achievements_count = None
    candidate.offer.has_trading_cards = False

    payload, _ = _generate_manifest_payload(tmp_path / 'empty-data', candidate)

    assert payload['summary_line']
    assert payload['short_title'] == 'Sparse Offer'
    assert isinstance(payload['asset_refs'], dict)
    assert payload['context']['source'] == 'steam'
    assert payload['context']['store'] == 'Steam'
    assert set(payload) == {
        'manifest_version',
        'run_key',
        'created_at',
        'offer_id',
        'short_title',
        'hook_line',
        'summary_line',
        'urgency_line',
        'asset_refs',
        'template_hint',
        'context',
    }


def _build_side_output_inputs(tmp_path: Path) -> tuple[QueuePlan, PublishResult]:
    planned = make_candidate(
        'steam:42',
        'Mystery of the Lantern',
        sale_event={'mode': 'auto', 'active': False, 'linked': True},
        diversity_constraints=['source_alternation'],
    )
    reserve = make_candidate(
        'steam:43',
        'Action Blast',
        queue_bucket='reserve',
        score=98.0,
        manual_force_override=True,
    )
    plan = QueuePlan(
        planned=[planned],
        reserve=[reserve],
        metrics={'sale_event.context_active': 1},
        context={
            'sale_event_mode': 'auto',
            'active': True,
            'active_event_offer_ids': ['event:visual-fest'],
            'phrase_tokens': ['steam_visual_novel_fest'],
            'word_tokens': ['visual', 'novel', 'fest'],
        },
    )
    publish_result = PublishResult(
        offer_id='steam:42',
        title='Mystery of the Lantern',
        lane='high_value_discount',
        image_path=tmp_path / 'card.png',
        message_id=777,
        published=True,
        reason='published',
        analytics={
            'selection': {
                'lane': 'high_value_discount',
                'queue_bucket': 'planned',
                'template_id': 'steam_discount',
                'score': 123.45,
                'decision_reasons': ['high_value_discount'],
                'quality_reasons': ['review_threshold'],
                'dedup_reason': 'new_offer',
                'event_sale_influence': {'mode': 'auto', 'active': False, 'linked': True},
                'diversity_constraints': ['source_alternation'],
                'manual_override': {'forced': False, 'reasons': []},
            },
            'render': {
                'image_path': str(tmp_path / 'card.png'),
                'template_id': 'steam_discount',
                'assets_used': ['https://example.com/header.png'],
                'caption_hash': 'caption-hash',
                'image_hash': 'image-hash',
                'render_diagnostics': {'warnings': []},
            },
            'publish_outcome': {
                'published': True,
                'reason': 'published',
                'message_id': 777,
                'outbox_status': 'published',
            },
        },
    )
    return plan, publish_result


def test_generate_analytics_artifacts_output_is_deterministic(tmp_path: Path) -> None:
    repo = Repositories(tmp_path / 'repo.sqlite3')
    repo.initialize()
    writer = AnalyticsArtifactWriter(tmp_path / 'analytics')
    use_case = GenerateAnalyticsArtifactsUseCase(repo, writer)
    now = datetime(2026, 3, 10, 12, 0)
    plan, publish_result = _build_side_output_inputs(tmp_path)

    use_case.execute(now, plan, publish_result)
    first_snapshot = {
        path.name: path.read_text(encoding='utf-8')
        for path in sorted((tmp_path / 'analytics').glob('*'))
    }

    use_case.execute(now, plan, publish_result)
    second_snapshot = {
        path.name: path.read_text(encoding='utf-8')
        for path in sorted((tmp_path / 'analytics').glob('*'))
    }

    assert first_snapshot == second_snapshot
    assert set(first_snapshot) == {
        '20260310T120000Z_planning_snapshot_20260310T120000Z.csv',
        '20260310T120000Z_planning_snapshot_20260310T120000Z.json',
        '20260310T120000Z_publish_outcome_steam_42.csv',
        '20260310T120000Z_publish_outcome_steam_42.json',
    }


def test_video_manifest_payload_is_telegram_independent_and_separate_from_operational_tables(tmp_path: Path) -> None:
    repo = Repositories(tmp_path / 'repo.sqlite3')
    repo.initialize()
    writer = VideoManifestWriter(tmp_path / 'video_manifests')
    use_case = GenerateVideoManifestsUseCase(repo, writer)
    now = datetime(2026, 3, 10, 12, 0)
    candidate = make_candidate(
        'steam:99',
        'Mystery of the Lantern',
        lane='final_push',
        score=140.0,
        sale_event={'mode': 'auto', 'active': False, 'linked': True},
    )
    plan = QueuePlan(
        planned=[candidate],
        reserve=[],
        metrics={'sale_event.context_active': 1},
        context={'sale_event_mode': 'auto', 'active': True, 'active_event_offer_ids': ['event:visual-fest']},
    )

    use_case.execute(now, plan)

    with repo.connect() as connection:
        manifest_row = connection.execute('SELECT json_path, payload_json FROM video_manifests').fetchone()
        outbox_count = connection.execute('SELECT COUNT(*) AS count FROM publish_outbox').fetchone()['count']
        artifact_count = connection.execute('SELECT COUNT(*) AS count FROM post_artifacts').fetchone()['count']

    assert manifest_row is not None
    assert outbox_count == 0
    assert artifact_count == 0

    manifest_path = Path(manifest_row['json_path'])
    assert manifest_path.exists()
    payload = json.loads(manifest_row['payload_json'])
    assert set(payload) == {
        'manifest_version',
        'run_key',
        'created_at',
        'offer_id',
        'short_title',
        'hook_line',
        'summary_line',
        'urgency_line',
        'asset_refs',
        'template_hint',
        'context',
    }
    assert 'caption_html' not in payload
    assert 'hashtags' not in payload
    assert 'idempotency_key' not in payload
    assert 'caption_hash' not in payload
    assert 'image_hash' not in payload
    assert 'telegram_message_id' not in payload


def test_generate_video_manifests_writer_failure_isolated_from_persistence(tmp_path: Path) -> None:
    class BrokenWriter:
        def write(self, manifest):
            raise RuntimeError('boom')

    repo = Repositories(tmp_path / 'repo.sqlite3')
    repo.initialize()
    use_case = GenerateVideoManifestsUseCase(repo, BrokenWriter())
    now = datetime(2026, 3, 10, 12, 0)
    candidate = make_candidate('steam:77', 'Darkest Ledger')
    plan = QueuePlan(
        planned=[candidate],
        reserve=[],
        metrics={},
        context={'sale_event_mode': 'auto', 'active': False, 'active_event_offer_ids': []},
    )

    use_case.execute(now, plan)

    with repo.connect() as connection:
        row = connection.execute('SELECT json_path FROM video_manifests').fetchone()
        outbox_count = connection.execute('SELECT COUNT(*) AS count FROM publish_outbox').fetchone()['count']
        artifact_count = connection.execute('SELECT COUNT(*) AS count FROM post_artifacts').fetchone()['count']

    assert row is not None
    assert row['json_path'] is None
    assert outbox_count == 0
    assert artifact_count == 0
    assert use_case.metrics.snapshot() == {
        'video_manifest.files.failed': 1,
        'video_manifest.db.success': 1,
        'video_manifest.generated': 1,
    }


def test_bot_runtime_keeps_publish_pipeline_alive_when_side_outputs_raise(tmp_path: Path) -> None:
    import asyncio

    from dealbot.main import BotRuntime
    from .support import make_test_settings

    class StubPlanner:
        def __init__(self, plan: QueuePlan) -> None:
            self.plan = plan

        async def execute(self, now_utc: datetime, now_local: datetime) -> QueuePlan:
            return self.plan

    class StubPublisher:
        def __init__(self, result: PublishResult) -> None:
            self.result = result

        async def execute(self, now_utc: datetime, now_local: datetime, force_publish: bool = False) -> PublishResult:
            return self.result

    class RaisingSideOutput:
        def execute(self, *args, **kwargs) -> None:
            raise RuntimeError('side output boom')

    settings = make_test_settings(tmp_path / 'runtime')
    runtime = BotRuntime(settings)
    now = datetime(2026, 3, 10, 12, 0)
    plan, publish_result = _build_side_output_inputs(tmp_path / 'runtime-artifacts')
    runtime.planner = StubPlanner(plan)
    runtime.publisher = StubPublisher(publish_result)
    runtime.analytics = RaisingSideOutput()
    runtime.roundups = RaisingSideOutput()
    runtime.video_manifests = RaisingSideOutput()
    runtime.now = lambda: (now, now)

    result = asyncio.run(runtime.plan_and_publish_once())

    assert result is publish_result
    assert result.reason == 'published'

