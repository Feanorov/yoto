from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

from application.use_cases.generate_roundup_artifacts import GenerateRoundupArtifactsUseCase
from application.use_cases.plan_queue import PlannedCandidate, QueuePlan
from domain.entities.analytics_artifact import AnalyticsArtifact
from domain.entities.offer import OfferKind, OfferSource
from infrastructure.analytics.artifact_writer import AnalyticsArtifactWriter
from infrastructure.db.repositories import Repositories

from .test_caption_builder_arch import make_offer


def make_reserve_candidate(
    offer_id: str,
    title: str,
    *,
    lane: str = 'high_value_discount',
    score: float = 100.0,
    genre: str = 'Action',
    tags: list[str] | None = None,
    reasons: list[str] | None = None,
    freebie: bool = False,
) -> PlannedCandidate:
    offer = make_offer()
    offer.offer_id = offer_id
    offer.source_ref = offer_id.split(':', 1)[-1]
    offer.game_id = offer.source_ref
    offer.franchise_key = offer.source_ref.replace(':', '-')
    offer.title = title
    offer.genres = [genre] if genre else []
    offer.tags = list(tags or ([genre] if genre else []))
    if freebie:
        offer.source = OfferSource.EPIC
        offer.offer_kind = OfferKind.FREEBIE
        offer.store_url = f'https://store.epicgames.com/uk/p/{offer.source_ref}'
        offer.price_before_minor = 69900
        offer.price_after_minor = 0
        offer.discount_percent = 100
        lane = 'backlog_filler'
    decision_reasons = list(reasons or ([lane] if lane else []))
    return PlannedCandidate(
        score=score,
        offer=offer,
        decision_json={
            'lane': lane,
            'template_id': 'steam_discount',
            'must_ship': False,
            'queue_bucket': 'reserve',
            'decision_reasons': decision_reasons,
            'quality_reasons': ['review_threshold'],
            'dedup_reason': 'new_offer',
            'is_final_push': False,
            'is_historical_best': False,
            'price_improved_minor': 0,
            'score': score,
            'previous_price_minor': None,
            'previous_posted_at': None,
            'best_price_minor': None,
            'manual_force_override': False,
            'recommended_post_mode': 'roundup_candidate',
            'debug': {},
        },
    )



def seed_roundup_history(
    repo: Repositories,
    tmp_path: Path,
    *,
    run_key: str,
    created_at: datetime,
    items: list[tuple[str, str]],
    context_source: str = 'current_queue',
    json_path: Path | None = None,
    payload_override: dict | None = None,
) -> None:
    output_root = tmp_path / 'output' / 'analytics'
    payload = payload_override if payload_override is not None else {
        'roundup_version': 1,
        'run_key': run_key,
        'created_at': created_at.isoformat(),
        'roundup_count': 1,
        'context': {'source': context_source},
        'roundups': [
            {
                'roundup_id': f'history_{run_key}',
                'title': 'Roundup: History',
                'intro': 'History seed',
                'group_type': 'mixed',
                'theme_label': 'History',
                'item_count': len(items),
                'items': [
                    {'offer_id': offer_id, 'title': title}
                    for offer_id, title in items
                ],
                'telegram_draft': None,
            }
        ],
    }
    repo.save_analytics_artifact(
        AnalyticsArtifact(
            artifact_type='roundup_snapshot',
            subject_id='roundups',
            run_key=run_key,
            created_at=created_at,
            payload_json=payload,
            json_path=json_path or (output_root / f'{run_key}_roundup_snapshot_roundups.json'),
            csv_path=output_root / f'{run_key}_roundup_snapshot_roundups.csv',
        )
    )


def emitted_roundup_count(repo: Repositories, now: datetime) -> int:
    with repo.connect() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM analytics_artifacts WHERE artifact_type = 'roundup_snapshot' AND created_at = ?",
            (now.isoformat(),),
        ).fetchone()
    return int(row['count'])


def load_emitted_roundup_payload(repo: Repositories, now: datetime) -> dict:
    with repo.connect() as connection:
        row = connection.execute(
            "SELECT json_path FROM analytics_artifacts WHERE artifact_type = 'roundup_snapshot' AND created_at = ?",
            (now.isoformat(),),
        ).fetchone()
    assert row is not None
    return json.loads(Path(row['json_path']).read_text(encoding='utf-8'))


class RecordingRoundupCardAdapter:
    def __init__(self, output_path: Path) -> None:
        self.output_path = output_path
        self.rendered_titles: list[str] = []

    def render(self, roundup) -> Path:
        self.rendered_titles.append(roundup.title)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_bytes(b'roundup-card')
        return self.output_path


class FailingRoundupCardAdapter:
    def render(self, roundup) -> Path:
        raise RuntimeError('render boom')


class DiagnosticRoundupCardAdapter:
    def __init__(self, output_path: Path) -> None:
        self.output_path = output_path

    def render(self, roundup):
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_bytes(b'roundup-card')
        return type(
            'RoundupRenderResult',
            (),
            {
                'image_path': self.output_path,
                'diagnostics': {
                    'renderer_selected': 'yoto_v4',
                    'renderer_fallback_used': False,
                    'hero_fallback_used': False,
                    'lead_artwork_selected_offer_id': roundup.items[0].offer_id,
                    'lead_artwork_selection_reason': 'highest_weighted_roundup_item_artwork',
                    'selected_asset_path': str(self.output_path),
                    'render_warnings': [],
                },
            },
        )()


def test_generate_roundup_artifacts_groups_related_candidates_by_genre(tmp_path: Path) -> None:
    repo = Repositories(tmp_path / 'repo.sqlite3')
    repo.initialize()
    writer = AnalyticsArtifactWriter(tmp_path / 'analytics')
    use_case = GenerateRoundupArtifactsUseCase(repo, writer)
    now = datetime(2026, 3, 10, 12, 0)

    plan = QueuePlan(
        planned=[],
        reserve=[
            make_reserve_candidate('steam:301', 'Strategy One', score=120.0, genre='Strategy', tags=['Strategy']),
            make_reserve_candidate('steam:302', 'Strategy Two', score=118.0, genre='Strategy', tags=['Strategy']),
            make_reserve_candidate('steam:303', 'Strategy Three', score=115.0, genre='Strategy', tags=['Strategy']),
            make_reserve_candidate('steam:304', 'Action Side Deal', score=90.0, genre='Action', tags=['Action']),
            make_reserve_candidate('steam:305', 'Racing Side Deal', score=88.0, genre='Racing', tags=['Racing']),
        ],
        metrics={},
        context={'sale_event_mode': 'auto', 'source': 'current_queue', 'queue_snapshot_at': '2026-03-10T12:00:00'},
    )

    use_case.execute(now, plan)

    with repo.connect() as connection:
        row = connection.execute("SELECT artifact_type, json_path, csv_path FROM analytics_artifacts WHERE artifact_type = 'roundup_snapshot'").fetchone()

    assert row is not None
    json_path = Path(row['json_path'])
    csv_path = Path(row['csv_path'])
    payload = json.loads(json_path.read_text(encoding='utf-8'))
    assert json_path.exists()
    assert csv_path.exists()
    assert payload['roundup_count'] == 1
    assert payload['context']['source'] == 'current_queue'
    assert payload['context']['queue_snapshot_at'] == '2026-03-10T12:00:00'
    roundup = payload['roundups'][0]
    assert roundup['title'] == 'Roundup: Strategy Picks'
    assert roundup['group_type'] == 'genre'
    assert roundup['theme_label'] == 'Strategy'
    assert roundup['item_count'] == 3
    assert [item['title'] for item in roundup['items']] == ['Strategy One', 'Strategy Two', 'Strategy Three']
    assert roundup['telegram_draft']['title'].startswith('🔥 Strategy: коротка добірка')
    assert roundup['telegram_draft']['item_lines'][0].startswith('1. <a href="https://store.steampowered.com/app/10"><b>Strategy One</b></a> — ')
    assert 'коментар' not in roundup['telegram_draft']['closing_cta'].lower()
    assert any(fragment in roundup['telegram_draft']['closing_cta'] for fragment in ('тема ваша', 'перших позицій', 'перших пунктів', 'головне', 'верхніх позицій'))
    assert roundup['telegram_draft']['caption_html'].startswith('<b>🔥 Strategy: коротка добірка</b>')
    assert use_case.metrics.snapshot() == {
        'roundup.files.success': 1,
        'roundup.db.success': 1,
        'roundup.generated': 1,
    }

    with csv_path.open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 3
    assert rows[0]['roundup_title'] == 'Roundup: Strategy Picks'
    assert rows[0]['telegram_title'].startswith('🔥 Strategy: коротка добірка')
    assert rows[0]['telegram_item_line'].startswith('1. <a href="https://store.steampowered.com/app/10"><b>Strategy One</b></a> — ')
    assert '<b>🔥 Strategy: коротка добірка</b>' in rows[0]['telegram_caption_html']



def test_generate_roundup_artifacts_falls_back_to_freebie_bundle(tmp_path: Path) -> None:
    repo = Repositories(tmp_path / 'repo.sqlite3')
    repo.initialize()
    writer = AnalyticsArtifactWriter(tmp_path / 'analytics')
    use_case = GenerateRoundupArtifactsUseCase(repo, writer)
    now = datetime(2026, 3, 10, 12, 0)

    plan = QueuePlan(
        planned=[],
        reserve=[
            make_reserve_candidate('epic:401', 'Isonzo', score=140.0, genre='Shooter', tags=['Historical'], reasons=['freebie_roundup_candidate'], freebie=True),
            make_reserve_candidate('epic:402', 'Cozy Grove', score=138.0, genre='Adventure', tags=['Relaxing'], reasons=['freebie_roundup_candidate'], freebie=True),
            make_reserve_candidate('epic:403', 'Deponia', score=130.0, genre='Adventure', tags=['Comedy'], reasons=['freebie_roundup_candidate'], freebie=True),
        ],
        metrics={},
        context={},
    )

    use_case.execute(now, plan)

    with repo.connect() as connection:
        row = connection.execute("SELECT json_path FROM analytics_artifacts WHERE artifact_type = 'roundup_snapshot'").fetchone()

    assert row is not None
    payload = json.loads(Path(row['json_path']).read_text(encoding='utf-8'))
    roundup = payload['roundups'][0]
    assert roundup['title'] == 'Roundup: Freebies To Claim'
    assert roundup['group_type'] == 'freebie'
    assert roundup['item_count'] == 3
    assert roundup['items'][0]['callout'] == 'Freebie roundup candidate'
    assert roundup['items'][0]['price_line'] == 'Free claim'
    assert roundup['telegram_draft']['title'] == '🎁 Безкоштовні ігри: коротка добірка'
    assert 'безплатно в Epic' in roundup['telegram_draft']['item_lines'][0]
    assert 'коментар' not in roundup['telegram_draft']['closing_cta'].lower()
    assert any(fragment in roundup['telegram_draft']['closing_cta'] for fragment in ('забрати одразу', 'перших позицій', 'перших пунктів', 'головне', 'верхніх позицій'))



def test_generate_roundup_artifacts_skips_when_not_enough_candidates(tmp_path: Path) -> None:
    repo = Repositories(tmp_path / 'repo.sqlite3')
    repo.initialize()
    writer = AnalyticsArtifactWriter(tmp_path / 'analytics')
    use_case = GenerateRoundupArtifactsUseCase(repo, writer)
    now = datetime(2026, 3, 10, 12, 0)

    plan = QueuePlan(
        planned=[],
        reserve=[
            make_reserve_candidate('steam:501', 'Only One', score=91.0),
            make_reserve_candidate('steam:502', 'Only Two', score=89.0),
        ],
        metrics={},
        context={},
    )

    use_case.execute(now, plan)

    with repo.connect() as connection:
        row = connection.execute("SELECT COUNT(*) AS count FROM analytics_artifacts WHERE artifact_type = 'roundup_snapshot'").fetchone()

    assert int(row['count']) == 0
    assert use_case.metrics.snapshot() == {'roundup.skipped.empty': 1}


def test_generate_roundup_artifacts_suppresses_exact_recurrence_match(tmp_path: Path) -> None:
    repo = Repositories(tmp_path / 'repo.sqlite3')
    repo.initialize()
    writer = AnalyticsArtifactWriter(tmp_path / 'analytics')
    use_case = GenerateRoundupArtifactsUseCase(repo, writer)
    now = datetime(2026, 3, 10, 12, 0)

    reserve = [
        make_reserve_candidate('steam:801', 'Strategy One', score=120.0, genre='Strategy', tags=['Strategy']),
        make_reserve_candidate('steam:802', 'Strategy Two', score=118.0, genre='Strategy', tags=['Strategy']),
        make_reserve_candidate('steam:803', 'Strategy Three', score=116.0, genre='Strategy', tags=['Strategy']),
        make_reserve_candidate('steam:804', 'Strategy Four', score=114.0, genre='Strategy', tags=['Strategy']),
        make_reserve_candidate('steam:805', 'Strategy Five', score=112.0, genre='Strategy', tags=['Strategy']),
    ]
    seed_roundup_history(
        repo,
        tmp_path,
        run_key='20260310T115500Z',
        created_at=now - timedelta(minutes=5),
        items=[(item.offer.offer_id, item.offer.title) for item in reserve],
    )

    plan = QueuePlan(planned=[], reserve=reserve, metrics={}, context={})
    use_case.execute(now, plan)

    assert emitted_roundup_count(repo, now) == 0
    assert use_case.metrics.snapshot() == {
        'roundup.recurrence.checked': 1,
        'roundup.recurrence.suppressed': 1,
        'roundup.skipped.recurrence': 1,
    }


def test_generate_roundup_artifacts_suppresses_high_overlap_recurrence(tmp_path: Path) -> None:
    repo = Repositories(tmp_path / 'repo.sqlite3')
    repo.initialize()
    writer = AnalyticsArtifactWriter(tmp_path / 'analytics')
    use_case = GenerateRoundupArtifactsUseCase(repo, writer)
    now = datetime(2026, 3, 10, 12, 0)

    reserve = [
        make_reserve_candidate('steam:901', 'Strategy One', score=120.0, genre='Strategy', tags=['Strategy']),
        make_reserve_candidate('steam:902', 'Strategy Two', score=118.0, genre='Strategy', tags=['Strategy']),
        make_reserve_candidate('steam:903', 'Strategy Three', score=116.0, genre='Strategy', tags=['Strategy']),
        make_reserve_candidate('steam:904', 'Strategy Four', score=114.0, genre='Strategy', tags=['Strategy']),
        make_reserve_candidate('steam:905', 'Strategy Five', score=112.0, genre='Strategy', tags=['Strategy']),
    ]
    seed_roundup_history(
        repo,
        tmp_path,
        run_key='20260310T115500Z',
        created_at=now - timedelta(minutes=5),
        items=[
            ('steam:901', 'Strategy One'),
            ('steam:902', 'Strategy Two'),
            ('steam:903', 'Strategy Three'),
            ('steam:990', 'History Other One'),
            ('steam:991', 'History Other Two'),
        ],
    )

    plan = QueuePlan(planned=[], reserve=reserve, metrics={}, context={})
    use_case.execute(now, plan)

    assert emitted_roundup_count(repo, now) == 0
    assert use_case.metrics.snapshot() == {
        'roundup.recurrence.checked': 1,
        'roundup.recurrence.suppressed': 1,
        'roundup.skipped.recurrence': 1,
    }


def test_generate_roundup_artifacts_allows_low_overlap_recurrence(tmp_path: Path) -> None:
    repo = Repositories(tmp_path / 'repo.sqlite3')
    repo.initialize()
    writer = AnalyticsArtifactWriter(tmp_path / 'analytics')
    use_case = GenerateRoundupArtifactsUseCase(repo, writer)
    now = datetime(2026, 3, 10, 12, 0)

    reserve = [
        make_reserve_candidate('steam:1001', 'Strategy One', score=120.0, genre='Strategy', tags=['Strategy']),
        make_reserve_candidate('steam:1002', 'Strategy Two', score=118.0, genre='Strategy', tags=['Strategy']),
        make_reserve_candidate('steam:1003', 'Strategy Three', score=116.0, genre='Strategy', tags=['Strategy']),
        make_reserve_candidate('steam:1004', 'Strategy Four', score=114.0, genre='Strategy', tags=['Strategy']),
        make_reserve_candidate('steam:1005', 'Strategy Five', score=112.0, genre='Strategy', tags=['Strategy']),
    ]
    seed_roundup_history(
        repo,
        tmp_path,
        run_key='20260310T115500Z',
        created_at=now - timedelta(minutes=5),
        items=[
            ('steam:1001', 'Strategy One'),
            ('steam:1002', 'Strategy Two'),
            ('steam:1090', 'History Other One'),
            ('steam:1091', 'History Other Two'),
            ('steam:1092', 'History Other Three'),
        ],
    )

    plan = QueuePlan(planned=[], reserve=reserve, metrics={}, context={})
    use_case.execute(now, plan)

    assert emitted_roundup_count(repo, now) == 1
    payload = load_emitted_roundup_payload(repo, now)
    assert payload['roundup_count'] == 1
    assert payload['roundups'][0]['title'] == 'Roundup: Strategy Picks'
    assert [item['title'] for item in payload['roundups'][0]['items']] == [
        'Strategy One',
        'Strategy Two',
        'Strategy Three',
        'Strategy Four',
        'Strategy Five',
    ]
    assert use_case.metrics.snapshot() == {
        'roundup.recurrence.checked': 1,
        'roundup.files.success': 1,
        'roundup.db.success': 1,
        'roundup.generated': 1,
    }


def test_generate_roundup_artifacts_applies_recurrence_before_window_cap(tmp_path: Path) -> None:
    repo = Repositories(tmp_path / 'repo.sqlite3')
    repo.initialize()
    writer = AnalyticsArtifactWriter(tmp_path / 'analytics')
    use_case = GenerateRoundupArtifactsUseCase(repo, writer)
    now = datetime(2026, 3, 10, 12, 0)

    reserve = [
        make_reserve_candidate('steam:1101', 'Hero One', score=160.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
        make_reserve_candidate('steam:1102', 'Hero Two', score=159.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
        make_reserve_candidate('steam:1103', 'Hero Three', score=158.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
        make_reserve_candidate('steam:1104', 'Hero Four', score=157.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
        make_reserve_candidate('steam:1105', 'Hero Five', score=156.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
        make_reserve_candidate('steam:1111', 'Strong One', score=150.0, genre='', tags=[], reasons=['high_value_discount', 'strong_discount']),
        make_reserve_candidate('steam:1112', 'Strong Two', score=149.0, genre='', tags=[], reasons=['high_value_discount', 'strong_discount']),
        make_reserve_candidate('steam:1113', 'Strong Three', score=148.0, genre='', tags=[], reasons=['high_value_discount', 'strong_discount']),
        make_reserve_candidate('steam:1114', 'Strong Four', score=147.0, genre='', tags=[], reasons=['high_value_discount', 'strong_discount']),
        make_reserve_candidate('steam:1115', 'Strong Five', score=146.0, genre='', tags=[], reasons=['high_value_discount', 'strong_discount']),
    ]
    seed_roundup_history(
        repo,
        tmp_path,
        run_key='20260310T115500Z',
        created_at=now - timedelta(minutes=5),
        items=[
            ('steam:1101', 'Hero One'),
            ('steam:1102', 'Hero Two'),
            ('steam:1103', 'Hero Three'),
            ('steam:1104', 'Hero Four'),
            ('steam:1105', 'Hero Five'),
        ],
    )

    plan = QueuePlan(planned=[], reserve=reserve, metrics={}, context={})
    use_case.execute(now, plan)

    assert emitted_roundup_count(repo, now) == 1
    payload = load_emitted_roundup_payload(repo, now)
    assert payload['roundup_count'] == 1
    assert payload['roundups'][0]['title'] == 'Roundup: Strong Discount Picks'
    assert [item['title'] for item in payload['roundups'][0]['items']] == [
        'Strong One',
        'Strong Two',
        'Strong Three',
        'Strong Four',
        'Strong Five',
    ]
    assert use_case.metrics.snapshot() == {
        'roundup.recurrence.checked': 2,
        'roundup.recurrence.suppressed': 1,
        'roundup.files.success': 1,
        'roundup.db.success': 1,
        'roundup.generated': 1,
    }


def test_generate_roundup_artifacts_ignores_non_editorial_or_malformed_recurrence_history(tmp_path: Path) -> None:
    repo = Repositories(tmp_path / 'repo.sqlite3')
    repo.initialize()
    writer = AnalyticsArtifactWriter(tmp_path / 'analytics')
    use_case = GenerateRoundupArtifactsUseCase(repo, writer)
    now = datetime(2026, 3, 10, 12, 0)

    reserve = [
        make_reserve_candidate('steam:1201', 'Strategy One', score=120.0, genre='Strategy', tags=['Strategy']),
        make_reserve_candidate('steam:1202', 'Strategy Two', score=118.0, genre='Strategy', tags=['Strategy']),
        make_reserve_candidate('steam:1203', 'Strategy Three', score=116.0, genre='Strategy', tags=['Strategy']),
        make_reserve_candidate('steam:1204', 'Strategy Four', score=114.0, genre='Strategy', tags=['Strategy']),
        make_reserve_candidate('steam:1205', 'Strategy Five', score=112.0, genre='Strategy', tags=['Strategy']),
    ]
    seed_roundup_history(
        repo,
        tmp_path,
        run_key='20260310T115500Z',
        created_at=now - timedelta(minutes=5),
        items=[(item.offer.offer_id, item.offer.title) for item in reserve],
        context_source='live_db_queue_snapshot',
        json_path=tmp_path / 'temp' / 'analytics' / '20260310T115500Z_roundup_snapshot_roundups.json',
    )
    seed_roundup_history(
        repo,
        tmp_path,
        run_key='20260310T115600Z',
        created_at=now - timedelta(minutes=4),
        items=[],
        payload_override={'context': {'source': 'current_queue'}},
    )

    plan = QueuePlan(planned=[], reserve=reserve, metrics={}, context={})
    use_case.execute(now, plan)

    assert emitted_roundup_count(repo, now) == 1
    payload = load_emitted_roundup_payload(repo, now)
    assert payload['roundup_count'] == 1
    assert payload['roundups'][0]['title'] == 'Roundup: Strategy Picks'
    assert use_case.metrics.snapshot() == {
        'roundup.recurrence.checked': 1,
        'roundup.files.success': 1,
        'roundup.db.success': 1,
        'roundup.generated': 1,
    }


def test_generate_roundup_artifacts_strips_orphaned_part_2_suffix_when_recurrence_leaves_one_roundup(tmp_path: Path) -> None:
    repo = Repositories(tmp_path / 'repo.sqlite3')
    repo.initialize()
    writer = AnalyticsArtifactWriter(tmp_path / 'analytics')
    use_case = GenerateRoundupArtifactsUseCase(repo, writer)
    now = datetime(2026, 3, 10, 12, 0)

    reserve = [
        make_reserve_candidate('steam:1301', 'Hero One', score=150.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
        make_reserve_candidate('steam:1302', 'Hero Two', score=149.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
        make_reserve_candidate('steam:1303', 'Hero Three', score=148.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
        make_reserve_candidate('steam:1304', 'Hero Four', score=147.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
        make_reserve_candidate('steam:1305', 'Hero Five', score=146.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
        make_reserve_candidate('steam:1306', 'Hero Six', score=145.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
        make_reserve_candidate('steam:1307', 'Hero Seven', score=144.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
        make_reserve_candidate('steam:1308', 'Hero Eight', score=143.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
    ]
    seed_roundup_history(
        repo,
        tmp_path,
        run_key='20260310T115500Z',
        created_at=now - timedelta(minutes=5),
        items=[
            ('steam:1301', 'Hero One'),
            ('steam:1302', 'Hero Two'),
            ('steam:1303', 'Hero Three'),
            ('steam:1304', 'Hero Four'),
            ('steam:1305', 'Hero Five'),
        ],
    )

    plan = QueuePlan(planned=[], reserve=reserve, metrics={}, context={})
    use_case.execute(now, plan)

    assert emitted_roundup_count(repo, now) == 1
    payload = load_emitted_roundup_payload(repo, now)
    roundup = payload['roundups'][0]
    assert roundup['title'] == 'Roundup: Big Discount Highlights'
    assert 'Part 2' not in roundup['title']
    assert [item['title'] for item in roundup['items']] == [
        'Hero Six',
        'Hero Seven',
        'Hero Eight',
    ]
    assert ',' not in roundup['telegram_draft']['title']
    assert use_case.metrics.snapshot() == {
        'roundup.recurrence.checked': 2,
        'roundup.recurrence.suppressed': 1,
        'roundup.files.success': 1,
        'roundup.db.success': 1,
        'roundup.generated': 1,
    }


def test_generate_roundup_artifacts_caps_to_one_roundup_per_window(tmp_path: Path) -> None:
    repo = Repositories(tmp_path / 'repo.sqlite3')
    repo.initialize()
    writer = AnalyticsArtifactWriter(tmp_path / 'analytics')
    use_case = GenerateRoundupArtifactsUseCase(repo, writer)
    now = datetime(2026, 3, 10, 12, 0)

    plan = QueuePlan(
        planned=[],
        reserve=[
            make_reserve_candidate('steam:601', 'Hero One', score=150.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
            make_reserve_candidate('steam:602', 'Hero Two', score=149.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
            make_reserve_candidate('steam:603', 'Hero Three', score=148.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
            make_reserve_candidate('steam:604', 'Hero Four', score=147.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
            make_reserve_candidate('steam:605', 'Hero Five', score=146.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
            make_reserve_candidate('steam:606', 'Hero Six', score=145.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
            make_reserve_candidate('steam:607', 'Hero Seven', score=144.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
            make_reserve_candidate('steam:608', 'Hero Eight', score=143.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
        ],
        metrics={},
        context={},
    )

    use_case.execute(now, plan)

    with repo.connect() as connection:
        row = connection.execute("SELECT json_path FROM analytics_artifacts WHERE artifact_type = 'roundup_snapshot'").fetchone()

    assert row is not None
    payload = json.loads(Path(row['json_path']).read_text(encoding='utf-8'))
    assert payload['roundup_count'] == 1
    assert [item['title'] for item in payload['roundups'][0]['items']] == [
        'Hero One',
        'Hero Two',
        'Hero Three',
        'Hero Four',
        'Hero Five',
    ]
    assert use_case.metrics.snapshot() == {
        'roundup.window_cap_applied': 1,
        'roundup.window_cap_suppressed': 1,
        'roundup.files.success': 1,
        'roundup.db.success': 1,
        'roundup.generated': 1,
    }



def test_generate_roundup_artifacts_strips_orphaned_part_suffix_when_capped_to_one(tmp_path: Path) -> None:
    repo = Repositories(tmp_path / 'repo.sqlite3')
    repo.initialize()
    writer = AnalyticsArtifactWriter(tmp_path / 'analytics')
    use_case = GenerateRoundupArtifactsUseCase(repo, writer)
    now = datetime(2026, 3, 10, 12, 0)

    plan = QueuePlan(
        planned=[],
        reserve=[
            make_reserve_candidate('steam:701', 'Hero One', score=150.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
            make_reserve_candidate('steam:702', 'Hero Two', score=149.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
            make_reserve_candidate('steam:703', 'Hero Three', score=148.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
            make_reserve_candidate('steam:704', 'Hero Four', score=147.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
            make_reserve_candidate('steam:705', 'Hero Five', score=146.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
            make_reserve_candidate('steam:706', 'Hero Six', score=145.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
            make_reserve_candidate('steam:707', 'Hero Seven', score=144.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
            make_reserve_candidate('steam:708', 'Hero Eight', score=143.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
        ],
        metrics={},
        context={},
    )

    use_case.execute(now, plan)

    with repo.connect() as connection:
        row = connection.execute("SELECT json_path FROM analytics_artifacts WHERE artifact_type = 'roundup_snapshot'").fetchone()

    assert row is not None
    payload = json.loads(Path(row['json_path']).read_text(encoding='utf-8'))
    roundup = payload['roundups'][0]
    assert roundup['title'] == 'Roundup: Big Discount Highlights'
    assert 'Part 1' not in roundup['title']
    assert ',' not in roundup['telegram_draft']['title']




def test_generate_roundup_artifacts_attaches_card_asset_path_when_adapter_succeeds(tmp_path: Path) -> None:
    repo = Repositories(tmp_path / 'repo.sqlite3')
    repo.initialize()
    writer = AnalyticsArtifactWriter(tmp_path / 'analytics')
    adapter = RecordingRoundupCardAdapter(tmp_path / 'cards' / 'roundup_card.png')
    use_case = GenerateRoundupArtifactsUseCase(repo, writer, roundup_card_adapter=adapter)
    now = datetime(2026, 3, 10, 12, 0)

    plan = QueuePlan(
        planned=[],
        reserve=[
            make_reserve_candidate('steam:1401', 'Hero One', score=150.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
            make_reserve_candidate('steam:1402', 'Hero Two', score=149.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
            make_reserve_candidate('steam:1403', 'Hero Three', score=148.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
            make_reserve_candidate('steam:1404', 'Hero Four', score=147.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
            make_reserve_candidate('steam:1405', 'Hero Five', score=146.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
            make_reserve_candidate('steam:1406', 'Hero Six', score=145.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
            make_reserve_candidate('steam:1407', 'Hero Seven', score=144.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
            make_reserve_candidate('steam:1408', 'Hero Eight', score=143.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
        ],
        metrics={},
        context={},
    )

    use_case.execute(now, plan)

    payload = load_emitted_roundup_payload(repo, now)
    roundup = payload['roundups'][0]
    assert adapter.rendered_titles == ['Roundup: Big Discount Highlights']
    assert roundup['card_asset_path'] == str(adapter.output_path)
    assert 'lead_artwork_url' not in roundup['items'][0]
    assert use_case.metrics.snapshot() == {
        'roundup.window_cap_applied': 1,
        'roundup.window_cap_suppressed': 1,
        'roundup.card.generated': 1,
        'roundup.files.success': 1,
        'roundup.db.success': 1,
        'roundup.generated': 1,
    }


def test_generate_roundup_artifacts_persists_roundup_card_render_diagnostics(tmp_path: Path) -> None:
    repo = Repositories(tmp_path / 'repo.sqlite3')
    repo.initialize()
    writer = AnalyticsArtifactWriter(tmp_path / 'analytics')
    adapter = DiagnosticRoundupCardAdapter(tmp_path / 'cards' / 'roundup_card.png')
    use_case = GenerateRoundupArtifactsUseCase(repo, writer, roundup_card_adapter=adapter)
    now = datetime(2026, 3, 10, 12, 0)

    plan = QueuePlan(
        planned=[],
        reserve=[
            make_reserve_candidate('steam:1451', 'Hero One', score=150.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
            make_reserve_candidate('steam:1452', 'Hero Two', score=149.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
            make_reserve_candidate('steam:1453', 'Hero Three', score=148.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
            make_reserve_candidate('steam:1454', 'Hero Four', score=147.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
            make_reserve_candidate('steam:1455', 'Hero Five', score=146.0, genre='', tags=[], reasons=['high_value_discount', 'hero_discount']),
        ],
        metrics={},
        context={},
    )

    use_case.execute(now, plan)

    payload = load_emitted_roundup_payload(repo, now)
    diagnostics = payload['roundups'][0]['card_render_diagnostics']
    assert diagnostics['renderer_selected'] == 'yoto_v4'
    assert diagnostics['lead_artwork_selected_offer_id'] == 'steam:1451'
    assert diagnostics['lead_artwork_selection_reason'] == 'highest_weighted_roundup_item_artwork'
    assert diagnostics['selected_asset_path'] == str(adapter.output_path)


def test_generate_roundup_artifacts_fails_open_when_roundup_card_render_errors(tmp_path: Path) -> None:
    repo = Repositories(tmp_path / 'repo.sqlite3')
    repo.initialize()
    writer = AnalyticsArtifactWriter(tmp_path / 'analytics')
    use_case = GenerateRoundupArtifactsUseCase(repo, writer, roundup_card_adapter=FailingRoundupCardAdapter())
    now = datetime(2026, 3, 10, 12, 0)

    plan = QueuePlan(
        planned=[],
        reserve=[
            make_reserve_candidate('steam:1501', 'Strategy One', score=120.0, genre='Strategy', tags=['Strategy']),
            make_reserve_candidate('steam:1502', 'Strategy Two', score=118.0, genre='Strategy', tags=['Strategy']),
            make_reserve_candidate('steam:1503', 'Strategy Three', score=115.0, genre='Strategy', tags=['Strategy']),
            make_reserve_candidate('steam:1504', 'Action Side Deal', score=90.0, genre='Action', tags=['Action']),
            make_reserve_candidate('steam:1505', 'Racing Side Deal', score=88.0, genre='Racing', tags=['Racing']),
        ],
        metrics={},
        context={},
    )

    use_case.execute(now, plan)

    payload = load_emitted_roundup_payload(repo, now)
    roundup = payload['roundups'][0]
    assert roundup['card_asset_path'] is None
    assert use_case.metrics.snapshot() == {
        'roundup.card.failed': 1,
        'roundup.files.success': 1,
        'roundup.db.success': 1,
        'roundup.generated': 1,
    }


