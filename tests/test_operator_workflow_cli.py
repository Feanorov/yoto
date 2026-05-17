from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path

from dealbot.operator_cli import (
    LatestArtifacts,
    _run_dealbot_command,
    build_doctor_summary,
    build_truth_summary,
    build_voice_package_summary,
    discover_latest_artifacts,
    emit_workflow_artifact,
    load_json,
    render_doctor_summary,
)
from video_generator.application.use_cases.build_voice_ready_package import BuildVoiceReadyPackageResult


def _touch(path: Path, *, mtime: int, content: str = '{}') -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    os.utime(path, (mtime, mtime))
    return path


def _write_json(path: Path, payload: dict, *, mtime: int) -> Path:
    return _touch(path, mtime=mtime, content=json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def test_discover_latest_artifacts_prefers_newest_paths(tmp_path: Path) -> None:
    root = tmp_path
    older_truth = _touch(root / 'output' / 'analytics' / '20260320T010000Z_operator_truth_report_preview.json', mtime=10)
    newer_truth = _touch(root / 'output' / 'analytics' / '20260320T020000Z_operator_truth_report_preview.json', mtime=20)
    publish_previewed_workflow = _touch(
        root / 'output' / 'analytics' / '20260320T020500Z_operator_workflow_publish-previewed.json',
        mtime=25,
    )
    older_card = _touch(root / 'output' / 'cards' / 'older.png', mtime=10)
    newer_card = _touch(root / 'output' / 'cards' / 'nested' / 'newer.png', mtime=30)
    caption_review = _touch(root / 'output' / 'captions' / 'freeze_review_1' / 'review.md', mtime=25)
    video_manifest = _touch(root / 'output' / 'video_manifests' / '20260320T020000Z_video_manifest_steam_952060.json', mtime=40)
    voice_package = _touch(root / 'output' / 'video_voice_ready' / 'pkg' / 'package_manifest.json', mtime=50)
    snapshot_manifest = _touch(root / 'output' / 'offline_validation' / 'snapshots' / '20260320T020000Z' / 'snapshot_manifest.json', mtime=60)
    golden_manifest = _touch(root / 'output' / 'offline_validation' / 'golden' / 'current' / 'snapshot_manifest.json', mtime=5)
    workflow = _touch(root / 'output' / 'analytics' / '20260320T021000Z_operator_workflow_preview.json', mtime=70)

    artifacts = discover_latest_artifacts(root)

    assert artifacts.operator_truth_report == newer_truth
    assert artifacts.latest_publish_previewed_workflow == publish_previewed_workflow
    assert artifacts.latest_card == newer_card
    assert artifacts.latest_caption_review == caption_review
    assert artifacts.latest_video_manifest == video_manifest
    assert artifacts.latest_voice_package_manifest == voice_package
    assert artifacts.latest_snapshot_manifest == snapshot_manifest
    assert artifacts.golden_snapshot_manifest == golden_manifest
    assert artifacts.latest_operator_workflow == workflow
    assert artifacts.operator_truth_report != older_truth
    assert artifacts.latest_card != older_card


def test_build_doctor_summary_still_reports_preview_truth_without_publish_previewed(tmp_path: Path) -> None:
    report_path = _write_json(
        tmp_path / 'output' / 'analytics' / '20260517T075511Z_operator_truth_report_preview.json',
        {
            'mode': 'preview',
            'created_at': '2026-05-17T07:55:11',
            'verdict': {
                'verdict': 'truthful_send_test_ready',
                'truth_ready': True,
                'telegram_verified': False,
            },
            'send_test_target': {
                'would_send': True,
                'candidate': {
                    'offer_id': 'steam:264710',
                    'title': 'Subnautica',
                    'bucket': 'planned',
                    'lane': 'high_value_discount',
                    'content_family': 'discount',
                    'source': 'steam',
                    'row_id': 1307,
                },
                'artifact': {
                    'image_path': 'D:\\Telegram_portable_bundle\\output\\cards\\subnautica.png',
                    'caption_preview': 'Subnautica preview caption',
                },
            },
        },
        mtime=10,
    )
    artifacts = discover_latest_artifacts(tmp_path)
    summary = build_doctor_summary(
        report_path=report_path,
        payload=load_json(report_path),
        artifacts=artifacts,
    )
    lines = render_doctor_summary(summary)

    assert summary['truth_ready'] is True
    assert summary['telegram_verified'] is False
    assert summary['published'] is False
    assert summary['next_action'] == 'The latest truth looks send-test ready. Review the selected target, then run yoto.bat send-test.'
    assert summary['latest_publish_previewed'] == {}
    assert all('latest_publish_previewed:' not in line for line in lines)


def test_build_doctor_summary_detects_successful_bound_publish_previewed(tmp_path: Path) -> None:
    report_path = _write_json(
        tmp_path / 'output' / 'analytics' / '20260517T075511Z_operator_truth_report_preview.json',
        {
            'mode': 'preview',
            'created_at': '2026-05-17T07:55:11',
            'verdict': {
                'verdict': 'truthful_send_test_ready',
                'truth_ready': True,
                'telegram_verified': False,
            },
            'send_test_target': {
                'would_send': True,
                'candidate': {
                    'offer_id': 'steam:264710',
                    'title': 'Subnautica',
                    'bucket': 'planned',
                    'lane': 'high_value_discount',
                    'content_family': 'discount',
                    'source': 'steam',
                    'row_id': 1307,
                },
                'artifact': {
                    'image_path': 'D:\\Telegram_portable_bundle\\output\\cards\\subnautica.png',
                    'caption_preview': 'Subnautica preview caption',
                },
            },
        },
        mtime=10,
    )
    publish_outcome_path = _write_json(
        tmp_path / 'output' / 'analytics' / '20260517T075954Z_publish_outcome_steam_264710.json',
        {
            'offer_id': 'steam:264710',
            'message_id': 182,
            'published': True,
        },
        mtime=20,
    )
    _write_json(
        tmp_path / 'output' / 'analytics' / '20260517T075955Z_operator_workflow_publish-previewed.json',
        {
            'command': 'publish-previewed',
            'status': 'ok',
            'reason': 'published',
            'published': True,
            'telegram_verified': True,
            'message_id': 182,
            'source_report_path': str(report_path.resolve()),
            'publish_outcome_path': str(publish_outcome_path.resolve()),
            'selected': {
                'offer_id': 'steam:264710',
                'title': 'Subnautica',
                'bucket': 'planned',
                'lane': 'high_value_discount',
                'source': 'steam',
                'row_id': 1307,
            },
        },
        mtime=21,
    )

    artifacts = discover_latest_artifacts(tmp_path)
    summary = build_doctor_summary(
        report_path=report_path,
        payload=load_json(report_path),
        artifacts=artifacts,
    )
    lines = render_doctor_summary(summary)
    rendered = '\n'.join(lines)

    assert summary['published'] is True
    assert summary['telegram_verified'] is True
    assert summary['message_id'] == 182
    assert summary['next_action'] == 'Review the Telegram post, then run preview for the next post.'
    assert summary['latest_publish_previewed']['success'] is True
    assert summary['latest_publish_previewed']['bound_to_latest_report'] is True
    assert 'run yoto.bat send-test' not in summary['next_action']
    assert 'latest_publish_previewed: yes' in rendered
    assert 'published: yes' in rendered
    assert 'telegram_verified: yes' in rendered
    assert 'message_id: 182' in rendered
    assert f'source_report: {report_path.resolve()}' in rendered
    assert f'publish_outcome: {publish_outcome_path.resolve()}' in rendered
    assert 'selected: Subnautica / steam:264710' in rendered


def test_build_doctor_summary_reports_failed_publish_previewed_without_hiding_preview_state(tmp_path: Path) -> None:
    report_path = _write_json(
        tmp_path / 'output' / 'analytics' / '20260517T075511Z_operator_truth_report_preview.json',
        {
            'mode': 'preview',
            'created_at': '2026-05-17T07:55:11',
            'verdict': {
                'verdict': 'truthful_send_test_ready',
                'truth_ready': True,
                'telegram_verified': False,
            },
            'send_test_target': {
                'would_send': True,
                'candidate': {
                    'offer_id': 'steam:264710',
                    'title': 'Subnautica',
                    'bucket': 'planned',
                    'lane': 'high_value_discount',
                    'content_family': 'discount',
                    'source': 'steam',
                    'row_id': 1307,
                },
                'artifact': {
                    'image_path': 'D:\\Telegram_portable_bundle\\output\\cards\\subnautica.png',
                    'caption_preview': 'Subnautica preview caption',
                },
            },
        },
        mtime=10,
    )
    _write_json(
        tmp_path / 'output' / 'analytics' / '20260517T075955Z_operator_workflow_publish-previewed.json',
        {
            'command': 'publish-previewed',
            'status': 'failed',
            'reason': 'image_missing',
            'published': False,
            'telegram_verified': False,
            'message_id': None,
            'source_report_path': str(report_path.resolve()),
            'publish_outcome_path': None,
            'selected': {
                'offer_id': 'steam:264710',
                'title': 'Subnautica',
            },
        },
        mtime=21,
    )

    artifacts = discover_latest_artifacts(tmp_path)
    summary = build_doctor_summary(
        report_path=report_path,
        payload=load_json(report_path),
        artifacts=artifacts,
    )
    rendered = '\n'.join(render_doctor_summary(summary))

    assert summary['published'] is False
    assert summary['telegram_verified'] is False
    assert summary['next_action'] == 'The latest truth looks send-test ready. Review the selected target, then run yoto.bat send-test.'
    assert summary['latest_publish_previewed']['success'] is False
    assert 'latest_publish_previewed: yes' in rendered
    assert 'status: failed' in rendered
    assert 'reason: image_missing' in rendered
    assert 'published: no' in rendered
    assert 'telegram_verified: no' in rendered


def test_build_truth_summary_reports_blocked_preview_with_next_step(tmp_path: Path) -> None:
    report_path = tmp_path / 'output' / 'analytics' / 'report.json'
    payload = {
        'verdict': {
            'verdict': 'truthful_send_test_blocked',
            'truth_ready': False,
            'telegram_verified': False,
            'blocker_category': 'queue_state',
            'blocker_reason': 'queue_empty',
        },
        'send_test_target': {
            'would_send': False,
        },
        'telegram': {},
    }

    summary = build_truth_summary(
        command_name='preview',
        exit_code=0,
        report_path=report_path,
        payload=payload,
        artifacts=LatestArtifacts(),
    )

    assert summary['truth_ready'] is False
    assert summary['published'] is False
    assert summary['selected'] is None
    assert summary['blocker_category'] == 'queue_state'
    assert 'rerun yoto.bat preview' in summary['next_action']


def test_build_truth_summary_reports_published_send_test_with_operator_next_step(tmp_path: Path) -> None:
    manifest_path = _touch(
        tmp_path / 'output' / 'video_manifests' / '20260320T063648Z_video_manifest_steam_952060.json',
        mtime=100,
    )
    payload = {
        'verdict': {
            'verdict': 'telegram_proof_verified',
            'truth_ready': True,
            'telegram_verified': True,
        },
        'send_test_target': {
            'would_send': True,
            'candidate': {
                'offer_id': 'steam:952060',
                'title': 'Resident Evil 3',
                'bucket': 'planned',
                'lane': 'high_value_discount',
                'content_family': 'discount',
                'source': 'steam',
                'row_id': 635,
            },
            'artifact': {
                'image_path': 'D:\\Telegram\\output\\cards\\resident_evil_3.png',
                'caption_preview': 'Resident Evil 3 preview caption',
            },
        },
        'telegram': {
            'publish_result': {
                'published': True,
                'message_id': 172,
                'image_path': 'D:\\Telegram\\output\\cards\\resident_evil_3.png',
            }
        },
    }

    summary = build_truth_summary(
        command_name='send-test',
        exit_code=0,
        report_path=tmp_path / 'report.json',
        payload=payload,
        artifacts=LatestArtifacts(latest_video_manifest=manifest_path),
    )

    assert summary['truth_ready'] is True
    assert summary['telegram_verified'] is True
    assert summary['published'] is True
    assert summary['message_id'] == 172
    assert summary['card_path'] == 'D:\\Telegram\\output\\cards\\resident_evil_3.png'
    assert 'build-voice-package' in summary['next_action']


def test_build_voice_package_summary_marks_ready_and_writes_operator_artifact(tmp_path: Path) -> None:
    manifest_path = tmp_path / 'output' / 'video_manifests' / 'manifest.json'
    package_dir = tmp_path / 'output' / 'video_voice_ready' / 'pkg'
    package_dir.mkdir(parents=True, exist_ok=True)
    package_manifest = package_dir / 'package_manifest.json'
    review_path = package_dir / 'review.md'
    scene_plan = package_dir / 'scene_plan.json'
    voice_script = package_dir / 'voice_script.txt'
    timed_script = package_dir / 'voice_script_timed.txt'
    preview_video = package_dir / 'preview' / 'final_preview.mp4'
    preview_video.parent.mkdir(parents=True, exist_ok=True)
    for path in (manifest_path, package_manifest, review_path, scene_plan, voice_script, timed_script, preview_video):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('ok', encoding='utf-8')

    result = BuildVoiceReadyPackageResult(
        manifest_path=manifest_path,
        status='packaged',
        package_dir=package_dir,
        package_manifest_path=package_manifest,
        review_path=review_path,
        scene_plan_path=scene_plan,
        voice_script_path=voice_script,
        timed_script_path=timed_script,
        preview_video_path=preview_video,
        warnings=(),
    )

    summary = build_voice_package_summary(
        manifest_path=manifest_path,
        result=result,
        artifacts=LatestArtifacts(latest_video_manifest=manifest_path),
    )
    artifact_path = emit_workflow_artifact(tmp_path, summary, subject_id='build_voice_package_test')
    artifact_payload = json.loads(artifact_path.read_text(encoding='utf-8'))

    assert summary['ready_for_reaper'] is True
    assert 'Reaper dubbing' in summary['next_action']
    assert artifact_payload['status'] == 'ok'
    assert artifact_payload['ready_for_reaper'] is True


def test_run_dealbot_command_does_not_reuse_stale_truth_report_when_command_fails(tmp_path: Path) -> None:
    stale_report = _touch(
        tmp_path / 'output' / 'analytics' / '20260320T010000Z_operator_truth_report_preview.json',
        mtime=10,
        content=json.dumps(
            {
                'verdict': {
                    'verdict': 'telegram_proof_verified',
                    'truth_ready': True,
                    'telegram_verified': True,
                }
            }
        ),
    )

    exit_code, report_path, payload, artifacts = _run_dealbot_command(
        root_dir=tmp_path,
        args=['--preview'],
        command_name='preview',
        runner=lambda command, cwd: 1,
    )

    assert exit_code == 1
    assert report_path is None
    assert payload is None
    assert artifacts.operator_truth_report == stale_report
