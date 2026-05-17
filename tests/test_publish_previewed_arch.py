from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from application.use_cases.publish_previewed import PublishPreviewedUseCase
from dealbot import operator_cli
from infrastructure.analytics.artifact_writer import AnalyticsArtifactWriter
from infrastructure.db.repositories import Repositories
from infrastructure.telegram import caption_builder
from domain.entities.post_artifact import PostArtifact

from .support import make_test_settings
from .test_caption_builder_arch import make_offer
from .test_publish_reliability_arch import make_decision_json


class RecordingPublisher:
    def __init__(self, *, message_id: int = 901) -> None:
        self.message_id = message_id
        self.calls: list[tuple[Path, str]] = []

    async def publish_photo(self, image_path: Path, caption_html: str):
        self.calls.append((Path(image_path), caption_html))
        return SimpleNamespace(message_id=self.message_id)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_json(path: Path, payload: dict, *, mtime: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
    os.utime(path, (mtime, mtime))
    return path


def _build_preview_report_payload(
    tmp_path: Path,
    *,
    mode: str = 'preview',
    scope: str = 'live',
    truth_ready: bool = True,
    would_send: bool = True,
    include_pinned_publish: bool = True,
    contract_version: int = 1,
    caption_html: str = '<b>Exact preview caption</b>',
    image_bytes: bytes = b'preview-card-image',
    offer_id: str = 'steam:previewed',
    idempotency_key: str = 'previewed-key',
) -> tuple[dict, Path]:
    image_path = tmp_path / 'cards' / 'previewed-card.png'
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(image_bytes)
    caption_hash = _sha256_text(caption_html)
    image_hash = _sha256_bytes(image_bytes)

    offer = make_offer()
    offer.offer_id = offer_id
    offer.game_id = 'previewed'
    offer.franchise_key = 'previewed'
    offer.title = 'Previewed Target'
    offer.store_url = 'https://store.steampowered.com/app/227300/Euro_Truck_Simulator_2/'
    decision_json = make_decision_json()
    decision_json['queue_bucket'] = 'planned'
    decision_json['score'] = 125.0

    candidate = {
        'row_id': 42,
        'bucket': 'planned',
        'lane': decision_json['lane'],
        'content_family': 'discount',
        'source': offer.source.value,
        'offer_id': offer.offer_id,
        'title': offer.title,
        'template_id': decision_json['template_id'],
        'score': decision_json['score'],
        'recommended_post_mode': 'solo_post',
        'store_url': offer.store_url,
    }
    artifact = {
        'offer_id': offer.offer_id,
        'template_id': decision_json['template_id'],
        'card_family': 'DISCOUNT',
        'caption_html': caption_html,
        'caption_preview': caption_html,
        'caption_length': len(caption_html),
        'caption_hash': caption_hash,
        'image_hash': image_hash,
        'idempotency_key': idempotency_key,
        'image_path': str(image_path),
        'assets_used': ['https://example.com/hero.png'],
        'render_diagnostics': {'source': 'previewed-test'},
        'caption_debug': {'provider': 'test'},
    }
    payload = {
        'run_key': '20260517T120000Z',
        'created_at': '2026-05-17T12:00:00',
        'mode': mode,
        'scope': scope,
        'send_test_target': {
            'truth_ready': truth_ready,
            'would_send': would_send,
            'candidate': dict(candidate),
            'artifact': dict(artifact),
        },
        'verdict': {
            'verdict': 'truthful_send_test_ready' if truth_ready else 'truthful_send_test_blocked',
            'truth_ready': truth_ready,
            'telegram_verified': False,
        },
    }
    if include_pinned_publish:
        payload['pinned_publish'] = {
            'contract_version': contract_version,
            'source': 'preview',
            'created_at': payload['created_at'],
            'report_run_key': payload['run_key'],
            'candidate': dict(candidate),
            'offer_snapshot': offer.to_snapshot(),
            'decision_snapshot': dict(decision_json),
            'artifact': {
                'offer_id': offer.offer_id,
                'caption_html': caption_html,
                'caption_preview': caption_html,
                'caption_hash': caption_hash,
                'image_path': str(image_path),
                'image_hash': image_hash,
                'idempotency_key': idempotency_key,
                'template_id': decision_json['template_id'],
                'card_family': 'DISCOUNT',
                'assets_used': ['https://example.com/hero.png'],
                'render_diagnostics': {'source': 'previewed-test'},
                'caption_debug': {'provider': 'test'},
            },
            'validation': {
                'image_exists': True,
                'caption_hash_verified': True,
                'image_hash_verified': True,
            },
        }
    return payload, image_path


def _write_report(tmp_path: Path, payload: dict, *, name: str = '20260517T120000Z_operator_truth_report_preview.json', mtime: int = 10) -> Path:
    return _write_json(tmp_path / 'analytics' / name, payload, mtime=mtime)


def _build_use_case(tmp_path: Path, publisher: RecordingPublisher | None = None) -> tuple[PublishPreviewedUseCase, Repositories, RecordingPublisher]:
    settings = make_test_settings(tmp_path)
    repo = Repositories(settings.db_path)
    repo.initialize()
    recording_publisher = publisher or RecordingPublisher()
    use_case = PublishPreviewedUseCase(
        repo,
        recording_publisher,
        AnalyticsArtifactWriter(settings.analytics_output_dir),
    )
    return use_case, repo, recording_publisher


def _load_context(use_case: PublishPreviewedUseCase, report_path: Path):
    context, error = use_case._load_context(report_path)
    assert error is None
    assert context is not None
    return context


def test_publish_previewed_rejects_missing_report(tmp_path: Path) -> None:
    use_case, _, _ = _build_use_case(tmp_path)

    result = asyncio.run(use_case.execute(report_path=tmp_path / 'analytics' / 'missing.json'))

    assert result.reason == 'report_not_found'
    assert result.published is False


@pytest.mark.parametrize(
    ('mode', 'scope', 'reason'),
    [
        ('preview_offline', 'offline', 'invalid_report_mode'),
        ('preview', 'offline', 'invalid_report_scope'),
    ],
)
def test_publish_previewed_rejects_non_preview_or_offline_reports(
    tmp_path: Path,
    mode: str,
    scope: str,
    reason: str,
) -> None:
    use_case, _, _ = _build_use_case(tmp_path)
    payload, _ = _build_preview_report_payload(tmp_path, mode=mode, scope=scope)
    report_path = _write_report(tmp_path, payload)

    result = asyncio.run(use_case.execute(report_path=report_path))

    assert result.reason == reason
    assert result.published is False


def test_publish_previewed_rejects_missing_pinned_publish(tmp_path: Path) -> None:
    use_case, _, _ = _build_use_case(tmp_path)
    payload, _ = _build_preview_report_payload(tmp_path, include_pinned_publish=False)
    report_path = _write_report(tmp_path, payload)

    result = asyncio.run(use_case.execute(report_path=report_path))

    assert result.reason == 'pinned_publish_missing'


def test_publish_previewed_rejects_unsupported_contract_version(tmp_path: Path) -> None:
    use_case, _, _ = _build_use_case(tmp_path)
    payload, _ = _build_preview_report_payload(tmp_path, contract_version=2)
    report_path = _write_report(tmp_path, payload)

    result = asyncio.run(use_case.execute(report_path=report_path))

    assert result.reason == 'unsupported_contract_version'


def test_publish_previewed_rejects_caption_hash_mismatch(tmp_path: Path) -> None:
    use_case, _, _ = _build_use_case(tmp_path)
    payload, _ = _build_preview_report_payload(tmp_path)
    payload['send_test_target']['artifact']['caption_hash'] = 'bad-hash'
    payload['pinned_publish']['artifact']['caption_hash'] = 'bad-hash'
    report_path = _write_report(tmp_path, payload)

    result = asyncio.run(use_case.execute(report_path=report_path))

    assert result.reason == 'caption_hash_mismatch'


def test_publish_previewed_rejects_missing_image(tmp_path: Path) -> None:
    use_case, _, _ = _build_use_case(tmp_path)
    payload, image_path = _build_preview_report_payload(tmp_path)
    image_path.unlink()
    report_path = _write_report(tmp_path, payload)

    result = asyncio.run(use_case.execute(report_path=report_path))

    assert result.reason == 'image_missing'


def test_publish_previewed_rejects_image_hash_mismatch(tmp_path: Path) -> None:
    use_case, _, _ = _build_use_case(tmp_path)
    payload, image_path = _build_preview_report_payload(tmp_path)
    image_path.write_bytes(b'changed-image')
    report_path = _write_report(tmp_path, payload)

    result = asyncio.run(use_case.execute(report_path=report_path))

    assert result.reason == 'image_hash_mismatch'


def test_publish_previewed_rejects_stale_report(tmp_path: Path) -> None:
    use_case, _, _ = _build_use_case(tmp_path)
    older_payload, _ = _build_preview_report_payload(tmp_path, offer_id='steam:older', idempotency_key='older-key')
    newer_payload, _ = _build_preview_report_payload(tmp_path, offer_id='steam:newer', idempotency_key='newer-key')
    older_report = _write_report(tmp_path, older_payload, name='20260517T120000Z_operator_truth_report_preview.json', mtime=10)
    _write_report(tmp_path, newer_payload, name='20260517T121500Z_operator_truth_report_preview.json', mtime=20)

    result = asyncio.run(use_case.execute(report_path=older_report))

    assert result.reason == 'stale_preview_report'


def test_publish_previewed_rejects_idempotency_conflict_for_same_key_with_different_payload(tmp_path: Path) -> None:
    use_case, repo, publisher = _build_use_case(tmp_path)
    payload, report_image_path = _build_preview_report_payload(tmp_path, idempotency_key='shared-key')
    report_path = _write_report(tmp_path, payload)
    context = _load_context(use_case, report_path)

    conflicting_image_path = tmp_path / 'cards' / 'conflict-card.png'
    conflicting_image_path.parent.mkdir(parents=True, exist_ok=True)
    conflicting_image_path.write_bytes(b'conflicting-image')
    conflicting_artifact = PostArtifact(
        offer_id=context.offer_id,
        caption_html='<b>Different caption</b>',
        hashtags=[],
        template_id=context.artifact.template_id,
        render_inputs={'offer': context.offer_snapshot, 'decision': context.decision_snapshot},
        assets_used=['https://example.com/conflict.png'],
        idempotency_key=context.artifact.idempotency_key,
        caption_hash=_sha256_text('<b>Different caption</b>'),
        image_hash=_sha256_bytes(b'conflicting-image'),
    )
    repo.upsert_outbox(
        conflicting_artifact,
        image_path=conflicting_image_path,
        offer=context.offer,
        decision_json=context.decision_snapshot,
    )

    result = asyncio.run(use_case.execute(report_path=report_path))

    assert result.reason == 'idempotency_conflict'
    assert result.published is False
    assert publisher.calls == []
    assert report_image_path.exists()


@pytest.mark.parametrize(
    ('status', 'reason', 'expected_calls'),
    [
        ('published', 'already_published', 0),
        ('sent', 'finalized_sent', 0),
    ],
)
def test_publish_previewed_is_idempotent_for_exact_matching_published_and_sent_rows(
    tmp_path: Path,
    status: str,
    reason: str,
    expected_calls: int,
) -> None:
    use_case, repo, publisher = _build_use_case(tmp_path)
    payload, _ = _build_preview_report_payload(tmp_path, idempotency_key=f'{status}-key')
    report_path = _write_report(tmp_path, payload)
    context = _load_context(use_case, report_path)
    staged = repo.stage_pinned_outbox_delivery(
        artifact=context.artifact,
        image_path=context.image_path,
        offer_snapshot=context.offer_snapshot,
        decision_json=context.decision_snapshot,
        meta={
            'source_report_path': str(report_path),
            'source_report_run_key': context.run_key,
            'contract_version': 1,
        },
    )
    repo.mark_outbox_sent(staged.idempotency_key, 777)
    if status == 'published':
        repo.finalize_publication(staged.idempotency_key, context.offer, context.lane, '2026-05-17')

    result = asyncio.run(
        use_case.execute(
            report_path=report_path,
            now_utc=datetime(2026, 5, 17, 12, 0),
            now_local=datetime(2026, 5, 17, 15, 0),
        )
    )
    stored = repo.get_outbox_record(staged.idempotency_key)

    assert result.reason == reason
    assert result.published is True
    assert result.message_id == 777
    assert len(publisher.calls) == expected_calls
    assert stored is not None
    assert stored.status == 'published'


def test_publish_previewed_writes_exact_publish_outcome_artifact(tmp_path: Path) -> None:
    use_case, _, publisher = _build_use_case(tmp_path, publisher=RecordingPublisher(message_id=915))
    payload, image_path = _build_preview_report_payload(tmp_path, idempotency_key='artifact-key')
    report_path = _write_report(tmp_path, payload)

    result = asyncio.run(
        use_case.execute(
            report_path=report_path,
            now_utc=datetime(2026, 5, 17, 12, 0),
            now_local=datetime(2026, 5, 17, 15, 0),
        )
    )

    assert result.published is True
    assert result.publish_outcome_path is not None and result.publish_outcome_path.exists()
    publish_payload = json.loads(result.publish_outcome_path.read_text(encoding='utf-8'))
    assert publish_payload['offer_id'] == 'steam:previewed'
    assert publish_payload['image_path'] == str(image_path)
    assert publish_payload['render']['idempotency_key'] == 'artifact-key'
    assert publish_payload['render']['caption_hash'] == payload['pinned_publish']['artifact']['caption_hash']
    assert publish_payload['render']['image_hash'] == payload['pinned_publish']['artifact']['image_hash']
    assert publish_payload['publish_outcome']['source_report_path'] == str(report_path)
    assert publish_payload['publish_outcome']['source_report_run_key'] == payload['run_key']
    assert publish_payload['publish_outcome']['message_id'] == 915
    assert publisher.calls == [(image_path, payload['pinned_publish']['artifact']['caption_html'])]


def test_publish_previewed_cli_uses_direct_backend_path_and_writes_workflow_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload, image_path = _build_preview_report_payload(tmp_path, idempotency_key='cli-key')
    report_path = _write_report(tmp_path, payload)
    settings = make_test_settings(tmp_path)
    publisher = RecordingPublisher(message_id=932)
    captured_workflow: dict[str, Any] = {}

    def fail(*args, **kwargs):
        raise AssertionError('forbidden path called')

    monkeypatch.setattr(operator_cli, '_run_dealbot_command', fail)
    import dealbot.main as main_module
    monkeypatch.setattr(main_module, 'async_main', fail)

    import application.use_cases.publish_next as publish_next_module
    monkeypatch.setattr(publish_next_module.PublishNextUseCase, '__init__', fail)
    monkeypatch.setattr(publish_next_module.PublishNextUseCase, 'preview_send_test_target', fail)
    monkeypatch.setattr(publish_next_module.PublishNextUseCase, '_select_record', fail)

    import application.use_cases.dry_run_render as dry_run_render_module
    monkeypatch.setattr(dry_run_render_module.DryRunRenderUseCase, 'execute', fail)
    monkeypatch.setattr(caption_builder.YotoVoiceEngine, 'select_offer_voice', fail)

    monkeypatch.setattr(operator_cli, 'AppSettings', SimpleNamespace(from_env=lambda root_dir: settings))
    monkeypatch.setattr(operator_cli, 'TelegramPublisher', lambda incoming_settings: publisher)
    monkeypatch.setattr(operator_cli, 'discover_latest_artifacts', lambda root_dir: operator_cli.LatestArtifacts())
    monkeypatch.setattr(operator_cli, 'safe_print', lambda line: None)
    monkeypatch.setattr(operator_cli, 'load_project_env', lambda root_dir: object())
    monkeypatch.setattr(operator_cli, 'render_bootstrap_diagnostics', lambda bootstrap: [])

    def fake_emit(root_dir: Path, payload: dict[str, Any], *, subject_id: str) -> Path:
        captured_workflow.clear()
        captured_workflow.update(payload)
        output_path = tmp_path / 'analytics' / f'{subject_id}.json'
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
        return output_path

    monkeypatch.setattr(operator_cli, 'emit_workflow_artifact', fake_emit)

    exit_code = operator_cli.main(['publish-previewed', '--from-report', str(report_path)])

    assert exit_code == 0
    assert publisher.calls == [(image_path, payload['pinned_publish']['artifact']['caption_html'])]
    assert captured_workflow['command'] == 'publish-previewed'
    assert captured_workflow['status'] == 'ok'
    assert captured_workflow['source_report_path'] == str(report_path)
    assert captured_workflow['source_report_run_key'] == payload['run_key']
    assert captured_workflow['selected']['offer_id'] == 'steam:previewed'
    assert captured_workflow['idempotency_key'] == 'cli-key'
    assert captured_workflow['caption_hash'] == payload['pinned_publish']['artifact']['caption_hash']
    assert captured_workflow['image_hash'] == payload['pinned_publish']['artifact']['image_hash']
    assert captured_workflow['image_path'] == str(image_path)
    assert captured_workflow['published'] is True
    assert captured_workflow['message_id'] == 932
    assert captured_workflow['outbox_status'] == 'published'
    assert captured_workflow['reason'] == 'published'
    assert captured_workflow['publish_outcome_path']
