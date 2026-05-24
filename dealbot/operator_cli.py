from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import Any, Callable

import httpx
from application.use_cases.dry_run_render import DryRunRenderUseCase
from application.use_cases.operator_truth_report import OperatorTruthReporter
from application.use_cases.preview_selected import PreviewSelectedResult, PreviewSelectedUseCase
from application.use_cases.publish_next import PublishNextUseCase
from application.use_cases.publish_previewed import PublishPreviewedResult, PublishPreviewedUseCase
from dealbot.settings import AppSettings, load_project_env, render_bootstrap_diagnostics
from domain.entities.analytics_artifact import AnalyticsArtifact
from infrastructure.analytics.artifact_writer import AnalyticsArtifactWriter
from infrastructure.clients.base_http import ResilientHttpClient
from infrastructure.db.repositories import Repositories
from infrastructure.render.cards.renderer_selector import CardRendererRouter
from infrastructure.telegram.caption_builder import TelegramCaptionBuilder
from infrastructure.telegram.publisher import TelegramPublisher
from video_generator.application.use_cases.build_voice_ready_package import BuildVoiceReadyPackageResult
from video_generator.cli import build_voice_ready_use_case


Runner = Callable[[list[str], Path], int]


class _PreviewOnlyPublisher:
    async def publish_photo(self, image_path: Path, caption_html: str):
        raise AssertionError('preview-selected must not publish to Telegram')


@dataclass(frozen=True, slots=True)
class LatestArtifacts:
    operator_truth_report: Path | None = None
    planning_snapshot: Path | None = None
    run_diagnostics: Path | None = None
    publish_outcome: Path | None = None
    latest_publish_previewed_workflow: Path | None = None
    latest_card: Path | None = None
    latest_caption_review: Path | None = None
    latest_video_manifest: Path | None = None
    latest_voice_package_manifest: Path | None = None
    latest_snapshot_manifest: Path | None = None
    golden_snapshot_manifest: Path | None = None
    latest_operator_workflow: Path | None = None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Operator-facing launcher for daily YOTO preview, send-test, status, and voice-package work.',
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    preview_parser = subparsers.add_parser(
        'preview',
        help='Refresh publish truth through the existing preview path and finish with an operator verdict.',
    )
    preview_parser.add_argument(
        '--offline-snapshot',
        nargs='?',
        const='latest',
        default=None,
        help='Read from an offline snapshot instead of live ingest. Omit the value to use the latest snapshot.',
    )

    send_test_parser = subparsers.add_parser(
        'send-test',
        help='Run the existing send-test path, keep logs visible, then print the publish verdict and artifact paths.',
    )
    send_test_parser.add_argument(
        '--offline-snapshot',
        nargs='?',
        const='latest',
        default=None,
        help='Replay send-test from an offline snapshot instead of live ingest.',
    )

    publish_previewed_parser = subparsers.add_parser(
        'publish-previewed',
        help='Publish exactly the pinned preview payload from an explicit preview truth report.',
    )
    publish_previewed_parser.add_argument(
        '--from-report',
        required=True,
        help='Path to the explicit preview truth report that contains pinned_publish.',
    )

    preview_selected_parser = subparsers.add_parser(
        'preview-selected',
        help='Build an exact preview truth report for one explicit candidate row from an existing preview truth report.',
    )
    preview_selected_parser.add_argument(
        '--from-report',
        required=True,
        help='Path to the source preview truth report that contains selection.candidate_rows[].',
    )
    preview_selected_parser.add_argument(
        '--candidate-id',
        required=True,
        type=int,
        help='Exact candidate_id / row_id from selection.candidate_rows[].',
    )

    daily_check_parser = subparsers.add_parser(
        'daily-check',
        help='Safe daily operator entrypoint: runs preview, then prints blockers, artifact pointers, and the next step.',
    )
    daily_check_parser.add_argument(
        '--offline-snapshot',
        nargs='?',
        const='latest',
        default=None,
        help='Run the daily check from an offline snapshot instead of live ingest.',
    )

    doctor_parser = subparsers.add_parser(
        'doctor',
        help='Show the latest known publish truth, blockers, and newest artifacts without running the pipeline.',
    )
    doctor_parser.add_argument(
        '--strict',
        action='store_true',
        help='Exit non-zero when the latest truth report is missing or currently blocked.',
    )

    subparsers.add_parser(
        'latest-artifacts',
        help='Print the newest operator truth, card, caption, video, and snapshot artifact locations.',
    )

    build_voice_parser = subparsers.add_parser(
        'build-voice-package',
        help='Build a voice-ready package from the latest manifest or an explicit manifest path.',
    )
    build_voice_parser.add_argument(
        '--manifest',
        default='latest',
        help='Path to a manifest JSON, or "latest" to use the newest manifest under output/video_manifests.',
    )
    build_voice_parser.add_argument(
        '--skip-preview-video',
        action='store_true',
        help='Skip preview MP4 rendering while still building the voice-ready package.',
    )
    build_voice_parser.add_argument('--ffmpeg-bin', default='ffmpeg', help='ffmpeg binary to use for preview video rendering.')
    build_voice_parser.add_argument('--log-level', default='INFO')

    return parser.parse_args(argv)


def discover_latest_artifacts(root_dir: Path) -> LatestArtifacts:
    analytics_dir = root_dir / 'output' / 'analytics'
    return LatestArtifacts(
        operator_truth_report=_find_newest(analytics_dir, '*_operator_truth_report_*.json'),
        planning_snapshot=_find_newest(analytics_dir, '*_planning_snapshot_*.json'),
        run_diagnostics=_find_newest(analytics_dir, '*_run_diagnostics_pipeline.json'),
        publish_outcome=_find_newest(analytics_dir, '*_publish_outcome_*.json'),
        latest_publish_previewed_workflow=_find_newest(analytics_dir, '*_operator_workflow_publish-previewed.json'),
        latest_card=_find_newest(root_dir / 'output' / 'cards', ('*.png', '*.jpg', '*.jpeg', '*.webp')),
        latest_caption_review=_find_newest(root_dir / 'output' / 'captions', 'review.md'),
        latest_video_manifest=_find_newest(root_dir / 'output' / 'video_manifests', '*.json'),
        latest_voice_package_manifest=_find_newest(root_dir / 'output' / 'video_voice_ready', 'package_manifest.json'),
        latest_snapshot_manifest=_find_newest(
            root_dir / 'output' / 'offline_validation' / 'snapshots',
            'snapshot_manifest.json',
        ),
        golden_snapshot_manifest=_find_existing(
            root_dir / 'output' / 'offline_validation' / 'golden' / 'current' / 'snapshot_manifest.json',
        ),
        latest_operator_workflow=_find_newest(analytics_dir, '*_operator_workflow_*.json'),
    )


def _find_existing(path: Path) -> Path | None:
    return path if path.exists() else None


def _find_newest(
    base_dir: Path,
    patterns: str | tuple[str, ...],
    *,
    since_ts: float | None = None,
) -> Path | None:
    if not base_dir.exists():
        return None
    normalized_patterns = (patterns,) if isinstance(patterns, str) else patterns
    candidates: list[Path] = []
    for pattern in normalized_patterns:
        candidates.extend(path for path in base_dir.rglob(pattern) if path.is_file())
    if since_ts is not None:
        candidates = [path for path in candidates if path.stat().st_mtime >= since_ts]
    if not candidates:
        return None
    return max(candidates, key=lambda path: (path.stat().st_mtime, str(path)))


def load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def _path_payload(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    timestamp = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec='seconds')
    return {
        'path': str(path),
        'modified_at': timestamp,
    }


def _payload_path(payload: dict[str, Any] | None) -> str:
    if not payload:
        return 'none'
    path = payload.get('path')
    modified_at = payload.get('modified_at')
    if path and modified_at:
        return f'{path} ({modified_at})'
    return str(path or 'none')


def build_latest_artifacts_payload(artifacts: LatestArtifacts) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for field_name, value in asdict(artifacts).items():
        payload[field_name] = _path_payload(Path(value) if value is not None else None)
    return payload


def recommend_next_action(
    *,
    command_name: str,
    truth_ready: bool,
    telegram_verified: bool,
    blocker_category: str | None,
    blocker_reason: str | None,
    latest_video_manifest: Path | None,
) -> str:
    if command_name in {'preview', 'daily-check'}:
        if truth_ready:
            return 'If the selected target looks right, run yoto.bat send-test.'
        if blocker_reason == 'quiet_hours_active':
            return 'Wait for quiet hours to end, then rerun yoto.bat preview.'
        if blocker_category == 'ingest':
            return 'Fix the ingest source issue, then rerun yoto.bat preview.'
        if blocker_category == 'asset_localization':
            return 'Inspect the selected render/card asset problem, then rerun yoto.bat preview.'
        return 'Inspect blocked candidate reasons in the report, then rerun yoto.bat preview when the window improves.'

    if command_name == 'send-test':
        if telegram_verified:
            if latest_video_manifest is not None:
                return 'Review the Telegram post, then run yoto.bat build-voice-package for the newest manifest.'
            return 'Review the Telegram post and the publish outcome report.'
        if truth_ready:
            return 'Fix Telegram delivery or outbox issues, then rerun yoto.bat send-test.'
        if blocker_reason == 'quiet_hours_active':
            return 'Wait for quiet hours to end, rerun yoto.bat preview, then send-test again.'
        return 'Use yoto.bat preview to inspect the blocker before trying another send-test.'

    if command_name == 'doctor':
        if telegram_verified:
            return 'You already have Telegram proof; review the latest post and artifacts.'
        if truth_ready:
            return 'The latest truth looks send-test ready. Review the selected target, then run yoto.bat send-test.'
        return 'Run yoto.bat preview to refresh truth before deciding on the next publish action.'

    return 'Inspect the latest report and artifacts before the next operator action.'


def build_truth_summary(
    *,
    command_name: str,
    exit_code: int,
    report_path: Path | None,
    payload: dict[str, Any] | None,
    artifacts: LatestArtifacts,
) -> dict[str, Any]:
    if payload is None:
        next_action = 'Run yoto.bat preview to refresh live publish truth.'
        return {
            'command': command_name,
            'status': 'failed' if exit_code else 'missing_truth_report',
            'exit_code': exit_code,
            'report_path': str(report_path) if report_path is not None else None,
            'verdict': 'missing_truth_report',
            'truth_ready': False,
            'telegram_verified': False,
            'selected': None,
            'would_send': False,
            'published': False,
            'message_id': None,
            'card_path': None,
            'caption_preview': None,
            'blocker_category': 'operator_report',
            'blocker_reason': 'missing_truth_report',
            'next_action': next_action,
            'latest_artifacts': build_latest_artifacts_payload(artifacts),
        }

    verdict = dict(payload.get('verdict') or {})
    target = dict(payload.get('send_test_target') or {})
    candidate = dict(target.get('candidate') or {})
    artifact = dict(target.get('artifact') or {})
    telegram = dict(payload.get('telegram') or {})
    publish_result = dict(telegram.get('publish_result') or {})
    blocker_category = verdict.get('blocker_category')
    blocker_reason = verdict.get('blocker_reason')
    truth_ready = bool(verdict.get('truth_ready'))
    telegram_verified = bool(verdict.get('telegram_verified'))
    selected = None
    if candidate:
        selected = {
            'offer_id': candidate.get('offer_id'),
            'title': candidate.get('title'),
            'bucket': candidate.get('bucket'),
            'lane': candidate.get('lane'),
            'content_family': candidate.get('content_family'),
            'source': candidate.get('source'),
            'row_id': candidate.get('row_id'),
        }
    next_action = recommend_next_action(
        command_name=command_name,
        truth_ready=truth_ready,
        telegram_verified=telegram_verified,
        blocker_category=str(blocker_category or '').strip() or None,
        blocker_reason=str(blocker_reason or '').strip() or None,
        latest_video_manifest=artifacts.latest_video_manifest,
    )
    return {
        'command': command_name,
        'status': 'ok' if exit_code == 0 else 'failed',
        'exit_code': exit_code,
        'report_path': str(report_path) if report_path is not None else None,
        'verdict': verdict.get('verdict'),
        'truth_ready': truth_ready,
        'telegram_verified': telegram_verified,
        'selected': selected,
        'would_send': bool(target.get('would_send')),
        'published': bool(publish_result.get('published')),
        'message_id': publish_result.get('message_id'),
        'card_path': publish_result.get('image_path') or artifact.get('image_path'),
        'caption_preview': artifact.get('caption_preview'),
        'blocker_category': blocker_category,
        'blocker_reason': blocker_reason,
        'next_action': next_action,
        'latest_artifacts': build_latest_artifacts_payload(artifacts),
    }


def render_truth_summary(summary: dict[str, Any]) -> list[str]:
    selected = dict(summary.get('selected') or {})
    latest_artifacts = dict(summary.get('latest_artifacts') or {})
    lines = [
        '',
        '=== YOTO Operator Verdict ===',
        f'command: {summary.get("command")}',
        f'status: {summary.get("status")} (exit={summary.get("exit_code")})',
        f'verdict: {summary.get("verdict") or "unknown"}',
        f'truth_ready: {"yes" if summary.get("truth_ready") else "no"}',
        f'telegram_verified: {"yes" if summary.get("telegram_verified") else "no"}',
    ]
    if selected:
        lines.append(
            'selected: '
            f'[{selected.get("bucket")}] '
            f'[{selected.get("content_family")}/{selected.get("lane")}] '
            f'{selected.get("source")} :: {selected.get("offer_id")} :: {selected.get("title")}'
        )
    else:
        lines.append('selected: none')
    lines.extend(
        [
            f'would_send: {"yes" if summary.get("would_send") else "no"}',
            f'published: {"yes" if summary.get("published") else "no"}',
            f'message_id: {summary.get("message_id") or "none"}',
            f'blocker: {summary.get("blocker_category") or "none"} / {summary.get("blocker_reason") or "none"}',
            f'report: {summary.get("report_path") or "none"}',
            f'card: {summary.get("card_path") or "none"}',
            f'caption: {summary.get("caption_preview") or "none"}',
            f'latest_snapshot: {_payload_path(latest_artifacts.get("latest_snapshot_manifest"))}',
            f'latest_manifest: {_payload_path(latest_artifacts.get("latest_video_manifest"))}',
            f'workflow_artifact: {summary.get("workflow_artifact_path") or "none"}',
            f'next: {summary.get("next_action")}',
        ]
    )
    return lines


def build_doctor_summary(
    *,
    report_path: Path | None,
    payload: dict[str, Any] | None,
    artifacts: LatestArtifacts,
) -> dict[str, Any]:
    summary = build_truth_summary(
        command_name='doctor',
        exit_code=0,
        report_path=report_path,
        payload=payload,
        artifacts=artifacts,
    )
    summary['status'] = 'ok'
    summary['latest_truth_mode'] = payload.get('mode') if payload else None
    summary['latest_truth_created_at'] = payload.get('created_at') if payload else None
    publish_previewed_summary = _build_publish_previewed_doctor_summary(
        workflow_path=artifacts.latest_publish_previewed_workflow,
        latest_report_path=report_path,
    )
    summary['latest_publish_previewed'] = publish_previewed_summary
    if publish_previewed_summary.get('bound_to_latest_report') and publish_previewed_summary.get('success'):
        summary['published'] = True
        summary['telegram_verified'] = True
        summary['message_id'] = publish_previewed_summary.get('message_id')
        summary['next_action'] = 'Review the Telegram post, then run preview for the next post.'
    return summary


def render_doctor_summary(summary: dict[str, Any]) -> list[str]:
    lines = [
        '=== YOTO Doctor ===',
        f'latest_truth_mode: {summary.get("latest_truth_mode") or "none"}',
        f'latest_truth_created_at: {summary.get("latest_truth_created_at") or "none"}',
    ]
    publish_previewed = dict(summary.get('latest_publish_previewed') or {})
    if publish_previewed:
        selected = dict(publish_previewed.get('selected') or {})
        selected_text = 'none'
        if selected:
            selected_text = f'{selected.get("title") or "unknown"} / {selected.get("offer_id") or "none"}'
        lines.extend(
            [
                '=== Publish-Previewed Proof ===',
                f'latest_publish_previewed: {"yes" if publish_previewed.get("exists") else "no"}',
                f'status: {publish_previewed.get("status") or "none"}',
                f'reason: {publish_previewed.get("reason") or "none"}',
                f'published: {"yes" if publish_previewed.get("published") else "no"}',
                f'telegram_verified: {"yes" if publish_previewed.get("telegram_verified") else "no"}',
                f'message_id: {publish_previewed.get("message_id") or "none"}',
                f'selected: {selected_text}',
                f'source_report: {publish_previewed.get("source_report_path") or "none"}',
                f'publish_outcome: {publish_previewed.get("publish_outcome_path") or "none"}',
                f'workflow: {publish_previewed.get("workflow_path") or "none"}',
            ]
        )
    lines.extend(render_truth_summary(summary)[1:])
    return lines


def build_latest_artifacts_summary(artifacts: LatestArtifacts) -> dict[str, Any]:
    next_action = 'Run yoto.bat preview if you need fresh publish truth.'
    if artifacts.operator_truth_report is not None:
        next_action = 'Open the newest operator truth report or run yoto.bat doctor for a verdict.'
    return {
        'command': 'latest-artifacts',
        'status': 'ok',
        'latest_artifacts': build_latest_artifacts_payload(artifacts),
        'next_action': next_action,
    }


def render_latest_artifacts_summary(summary: dict[str, Any]) -> list[str]:
    latest_artifacts = dict(summary.get('latest_artifacts') or {})
    lines = ['=== Latest Artifacts ===']
    for key in (
        'operator_truth_report',
        'planning_snapshot',
        'run_diagnostics',
        'publish_outcome',
        'latest_publish_previewed_workflow',
        'latest_card',
        'latest_caption_review',
        'latest_video_manifest',
        'latest_voice_package_manifest',
        'latest_snapshot_manifest',
        'golden_snapshot_manifest',
        'latest_operator_workflow',
    ):
        lines.append(f'{key}: {_payload_path(latest_artifacts.get(key))}')
    lines.append(f'workflow_artifact: {summary.get("workflow_artifact_path") or "none"}')
    lines.append(f'next: {summary.get("next_action")}')
    return lines


def build_voice_package_summary(
    *,
    manifest_path: Path | None,
    result: BuildVoiceReadyPackageResult | None,
    artifacts: LatestArtifacts,
) -> dict[str, Any]:
    if manifest_path is None:
        return {
            'command': 'build-voice-package',
            'status': 'failed',
            'manifest_path': None,
            'ready_for_reaper': False,
            'blocker_reason': 'missing_video_manifest',
            'next_action': 'Generate or locate a video manifest, then rerun yoto.bat build-voice-package.',
            'latest_artifacts': build_latest_artifacts_payload(artifacts),
        }

    if result is None or result.status != 'packaged':
        return {
            'command': 'build-voice-package',
            'status': 'failed',
            'manifest_path': str(manifest_path),
            'ready_for_reaper': False,
            'blocker_reason': result.error if result is not None else 'voice_package_failed',
            'package_dir': str(result.package_dir) if result is not None and result.package_dir is not None else None,
            'next_action': 'Fix the manifest or preview render issue, then rerun yoto.bat build-voice-package.',
            'latest_artifacts': build_latest_artifacts_payload(artifacts),
        }

    ready_for_reaper = all(
        (
            result.package_manifest_path is not None,
            result.review_path is not None,
            result.scene_plan_path is not None,
            result.voice_script_path is not None,
            result.timed_script_path is not None,
        )
    )
    return {
        'command': 'build-voice-package',
        'status': 'ok',
        'manifest_path': str(manifest_path),
        'ready_for_reaper': ready_for_reaper,
        'warnings': list(result.warnings),
        'package_dir': str(result.package_dir) if result.package_dir is not None else None,
        'package_manifest_path': str(result.package_manifest_path) if result.package_manifest_path is not None else None,
        'review_path': str(result.review_path) if result.review_path is not None else None,
        'scene_plan_path': str(result.scene_plan_path) if result.scene_plan_path is not None else None,
        'voice_script_path': str(result.voice_script_path) if result.voice_script_path is not None else None,
        'timed_script_path': str(result.timed_script_path) if result.timed_script_path is not None else None,
        'preview_video_path': str(result.preview_video_path) if result.preview_video_path is not None else None,
        'next_action': 'Open review.md and voice_script.txt, then hand the package to Reaper dubbing.',
        'latest_artifacts': build_latest_artifacts_payload(artifacts),
    }


def build_publish_previewed_summary(
    *,
    result: PublishPreviewedResult,
    artifacts: LatestArtifacts,
) -> dict[str, Any]:
    next_action = 'Inspect the failure reason and refresh preview truth before retrying.'
    if result.published:
        next_action = 'Review the Telegram post and the publish outcome report.'
    elif result.reason in {'publish_failed', 'db_claim_failed', 'db_mark_sent_failed', 'db_finalize_failed'}:
        next_action = 'Inspect Telegram/outbox state, then retry publish-previewed with the same report if it is still current.'
    return {
        'command': 'publish-previewed',
        'status': 'ok' if result.published else 'failed',
        'source_report_path': str(result.source_report_path) if result.source_report_path is not None else None,
        'source_report_run_key': result.source_report_run_key,
        'selected': dict(result.selected or {}),
        'idempotency_key': result.idempotency_key,
        'caption_hash': result.caption_hash,
        'image_hash': result.image_hash,
        'image_path': str(result.image_path) if result.image_path is not None else None,
        'published': result.published,
        'message_id': result.message_id,
        'outbox_status': result.outbox_status,
        'reason': result.reason,
        'publish_outcome_path': str(result.publish_outcome_path) if result.publish_outcome_path is not None else None,
        'telegram_verified': result.published,
        'next_action': next_action,
        'latest_artifacts': build_latest_artifacts_payload(artifacts),
    }


def build_preview_selected_summary(
    *,
    result: PreviewSelectedResult,
    artifacts: LatestArtifacts,
) -> dict[str, Any]:
    next_action = 'Inspect the failure reason, refresh the base preview if needed, and choose another candidate row.'
    if result.created_report and result.report_path is not None:
        next_action = f'If the selected preview looks right, run yoto.bat publish-previewed --from-report "{result.report_path}".'
    return {
        'command': 'preview-selected',
        'status': result.status,
        'reason': result.reason,
        'source_report_path': str(result.source_report_path) if result.source_report_path is not None else None,
        'source_report_run_key': result.source_report_run_key,
        'report_path': str(result.report_path) if result.report_path is not None else None,
        'candidate_id': result.candidate_id,
        'selected': dict(result.selected or {}),
        'truth_ready': result.truth_ready,
        'would_send': result.would_send,
        'blocker_category': result.blocker_category,
        'blocker_detail': result.blocker_detail,
        'caption_hash': result.caption_hash,
        'image_hash': result.image_hash,
        'image_path': str(result.image_path) if result.image_path is not None else None,
        'next_action': next_action,
        'latest_artifacts': build_latest_artifacts_payload(artifacts),
    }


def render_voice_package_summary(summary: dict[str, Any]) -> list[str]:
    return [
        '',
        '=== Voice Package Verdict ===',
        f'status: {summary.get("status")}',
        f'manifest: {summary.get("manifest_path") or "none"}',
        f'package_dir: {summary.get("package_dir") or "none"}',
        f'preview_video: {summary.get("preview_video_path") or "none"}',
        f'voice_script: {summary.get("voice_script_path") or "none"}',
        f'review: {summary.get("review_path") or "none"}',
        f'ready_for_reaper: {"yes" if summary.get("ready_for_reaper") else "no"}',
        f'warnings: {", ".join(summary.get("warnings") or []) or "none"}',
        f'workflow_artifact: {summary.get("workflow_artifact_path") or "none"}',
        f'next: {summary.get("next_action")}',
    ]


def render_publish_previewed_summary(summary: dict[str, Any]) -> list[str]:
    selected = dict(summary.get('selected') or {})
    return [
        '',
        '=== Publish Previewed Verdict ===',
        f'status: {summary.get("status")}',
        f'reason: {summary.get("reason") or "none"}',
        f'source_report: {summary.get("source_report_path") or "none"}',
        f'source_run_key: {summary.get("source_report_run_key") or "none"}',
        f'selected_offer_id: {selected.get("offer_id") or "none"}',
        f'idempotency_key: {summary.get("idempotency_key") or "none"}',
        f'caption_hash: {summary.get("caption_hash") or "none"}',
        f'image_hash: {summary.get("image_hash") or "none"}',
        f'image_path: {summary.get("image_path") or "none"}',
        f'published: {"yes" if summary.get("published") else "no"}',
        f'message_id: {summary.get("message_id") or "none"}',
        f'outbox_status: {summary.get("outbox_status") or "none"}',
        f'publish_outcome: {summary.get("publish_outcome_path") or "none"}',
        f'workflow_artifact: {summary.get("workflow_artifact_path") or "none"}',
        f'next: {summary.get("next_action")}',
    ]


def render_preview_selected_summary(summary: dict[str, Any]) -> list[str]:
    selected = dict(summary.get('selected') or {})
    return [
        '',
        '=== Preview Selected Verdict ===',
        f'status: {summary.get("status")}',
        f'reason: {summary.get("reason") or "none"}',
        f'source_report: {summary.get("source_report_path") or "none"}',
        f'source_run_key: {summary.get("source_report_run_key") or "none"}',
        f'candidate_id: {summary.get("candidate_id") or "none"}',
        f'selected_offer_id: {selected.get("offer_id") or "none"}',
        f'selected_title: {selected.get("title") or "none"}',
        f'selected_status: {selected.get("status") or "none"}',
        f'generated_report: {summary.get("report_path") or "none"}',
        f'truth_ready: {"yes" if summary.get("truth_ready") else "no"}',
        f'would_send: {"yes" if summary.get("would_send") else "no"}',
        f'blocker: {summary.get("blocker_category") or "none"} / {summary.get("reason") or "none"}',
        f'blocker_detail: {summary.get("blocker_detail") or "none"}',
        f'caption_hash: {summary.get("caption_hash") or "none"}',
        f'image_hash: {summary.get("image_hash") or "none"}',
        f'image_path: {summary.get("image_path") or "none"}',
        f'workflow_artifact: {summary.get("workflow_artifact_path") or "none"}',
        f'next: {summary.get("next_action")}',
    ]


def _default_runner(command: list[str], cwd: Path) -> int:
    completed = subprocess.run(command, cwd=str(cwd), check=False)
    return int(completed.returncode)


def safe_print(line: str) -> None:
    text = f'{line}\n'
    encoding = getattr(sys.stdout, 'encoding', None) or 'utf-8'
    try:
        sys.stdout.write(text)
    except UnicodeEncodeError:
        sys.stdout.write(text.encode(encoding, errors='replace').decode(encoding, errors='replace'))


def emit_workflow_artifact(root_dir: Path, payload: dict[str, Any], *, subject_id: str) -> Path:
    now_utc = datetime.utcnow()
    artifact = AnalyticsArtifact(
        artifact_type='operator_workflow',
        subject_id=subject_id,
        run_key=now_utc.strftime('%Y%m%dT%H%M%SZ'),
        created_at=now_utc,
        payload_json=payload,
        summary_rows=[
            {
                'command': payload.get('command') or subject_id,
                'status': payload.get('status'),
                'verdict': payload.get('verdict'),
                'truth_ready': payload.get('truth_ready'),
                'telegram_verified': payload.get('telegram_verified'),
                'ready_for_reaper': payload.get('ready_for_reaper'),
                'blocker_reason': payload.get('blocker_reason'),
                'next_action': payload.get('next_action'),
            }
        ],
    )
    writer = AnalyticsArtifactWriter(root_dir / 'output' / 'analytics')
    json_path, _ = writer.write(artifact)
    if json_path is None:
        raise RuntimeError('Operator workflow artifact could not be written.')
    return json_path


def resolve_report_path(root_dir: Path, report_value: str) -> Path:
    candidate = Path(str(report_value or '').strip())
    if not candidate.is_absolute():
        candidate = root_dir / candidate
    return candidate


def _normalize_path_str(value: Any) -> str | None:
    raw = str(value or '').strip()
    if not raw:
        return None
    try:
        return str(Path(raw).resolve())
    except OSError:
        return str(Path(raw))


def _build_publish_previewed_doctor_summary(
    *,
    workflow_path: Path | None,
    latest_report_path: Path | None,
) -> dict[str, Any]:
    payload = load_json(workflow_path)
    if payload is None or str(payload.get('command') or '').strip() != 'publish-previewed':
        return {}
    selected = dict(payload.get('selected') or {})
    source_report_path = _normalize_path_str(payload.get('source_report_path'))
    latest_report_path_str = _normalize_path_str(latest_report_path)
    message_id = payload.get('message_id')
    success = bool(
        str(payload.get('status') or '').strip() == 'ok'
        and payload.get('published') is True
        and payload.get('telegram_verified') is True
        and message_id not in (None, '')
    )
    return {
        'exists': True,
        'workflow_path': str(workflow_path) if workflow_path is not None else None,
        'status': payload.get('status'),
        'reason': payload.get('reason'),
        'published': bool(payload.get('published')),
        'telegram_verified': bool(payload.get('telegram_verified')),
        'message_id': message_id,
        'selected': selected,
        'source_report_path': source_report_path,
        'publish_outcome_path': payload.get('publish_outcome_path'),
        'success': success,
        'bound_to_latest_report': bool(
            success
            and source_report_path is not None
            and latest_report_path_str is not None
            and source_report_path == latest_report_path_str
        ),
    }


def _run_dealbot_command(
    *,
    root_dir: Path,
    args: list[str],
    command_name: str,
    runner: Runner,
) -> tuple[int, Path | None, dict[str, Any] | None, LatestArtifacts]:
    started_at = time.time()
    exit_code = runner([sys.executable, '-m', 'dealbot.main', *args], root_dir)
    artifacts = discover_latest_artifacts(root_dir)
    report_path = _find_newest(
        root_dir / 'output' / 'analytics',
        '*_operator_truth_report_*.json',
        since_ts=started_at,
    )
    if report_path is None and exit_code == 0:
        report_path = artifacts.operator_truth_report
    payload = load_json(report_path)
    summary = build_truth_summary(
        command_name=command_name,
        exit_code=exit_code,
        report_path=report_path,
        payload=payload,
        artifacts=artifacts,
    )
    summary['workflow_artifact_path'] = str(emit_workflow_artifact(root_dir, summary, subject_id=command_name))
    for line in render_truth_summary(summary):
        safe_print(line)
    return exit_code, report_path, payload, discover_latest_artifacts(root_dir)


def resolve_manifest_path(root_dir: Path, manifest_value: str) -> Path | None:
    normalized = str(manifest_value or '').strip() or 'latest'
    if normalized.lower() == 'latest':
        return _find_newest(root_dir / 'output' / 'video_manifests', '*.json')
    candidate = Path(normalized)
    if not candidate.is_absolute():
        candidate = root_dir / candidate
    if candidate.exists() and candidate.is_file():
        return candidate
    return None


def build_voice_ready_package(root_dir: Path, args: argparse.Namespace) -> tuple[BuildVoiceReadyPackageResult | None, Path | None]:
    manifest_path = resolve_manifest_path(root_dir, args.manifest)
    if manifest_path is None:
        return None, None
    video_args = SimpleNamespace(
        manifests_dir=root_dir / 'output' / 'video_manifests',
        videos_dir=root_dir / 'output' / 'videos',
        temp_scenes_dir=root_dir / 'temp' / 'video_scenes',
        voice_ready_output_dir=root_dir / 'output' / 'video_voice_ready',
        package_manifest=manifest_path,
        skip_preview_video=args.skip_preview_video,
        ffmpeg_bin=args.ffmpeg_bin,
        sleep_seconds=30,
        log_level=args.log_level,
        loop=False,
    )
    use_case = build_voice_ready_use_case(video_args)
    result = use_case.execute(manifest_path, render_preview_video=not args.skip_preview_video)
    return result, manifest_path


async def _execute_preview_selected(
    *,
    settings: AppSettings,
    report_path: Path,
    candidate_id: int,
) -> PreviewSelectedResult:
    repositories = Repositories(settings.db_path)
    repositories.initialize()
    async with httpx.AsyncClient(
        timeout=settings.static.http_timeout_seconds,
        follow_redirects=True,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept-Language': 'uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7',
        },
    ) as http_client:
        render = DryRunRenderUseCase(
            caption_builder=TelegramCaptionBuilder(settings.static.caption_limit),
            renderer=CardRendererRouter(
                settings.card_output_dir,
                renderer_mode=settings.rendering.card_renderer,
                fallback_to_legacy=settings.rendering.fallback_to_legacy,
            ),
            http=ResilientHttpClient(http_client),
        )
        selector = PublishNextUseCase(
            settings=settings,
            repositories=repositories,
            dry_run_render=render,
            publisher=_PreviewOnlyPublisher(),
        )
        reporter = OperatorTruthReporter(
            repositories=repositories,
            writer=AnalyticsArtifactWriter(settings.analytics_output_dir),
        )
        use_case = PreviewSelectedUseCase(
            settings=settings,
            repositories=repositories,
            selector=selector,
            reporter=reporter,
        )
        return await use_case.execute(
            report_path=report_path,
            candidate_id=candidate_id,
        )


def main(argv: list[str] | None = None, *, runner: Runner | None = None) -> int:
    args = parse_args(argv)
    root_dir = Path(__file__).resolve().parents[1]
    command_runner = runner or _default_runner

    if args.command == 'preview':
        exit_code, _, _, _ = _run_dealbot_command(
            root_dir=root_dir,
            args=['--preview', *(['--offline-snapshot', args.offline_snapshot] if args.offline_snapshot is not None else [])],
            command_name='preview',
            runner=command_runner,
        )
        return exit_code

    if args.command == 'daily-check':
        exit_code, _, payload, artifacts = _run_dealbot_command(
            root_dir=root_dir,
            args=['--preview', *(['--offline-snapshot', args.offline_snapshot] if args.offline_snapshot is not None else [])],
            command_name='daily-check',
            runner=command_runner,
        )
        latest_summary = build_latest_artifacts_summary(artifacts)
        latest_summary['workflow_artifact_path'] = str(
            emit_workflow_artifact(root_dir, latest_summary, subject_id='daily_check_latest_artifacts')
        )
        for line in render_latest_artifacts_summary(latest_summary):
            safe_print(line)
        if payload is None and exit_code == 0:
            return 1
        return exit_code

    if args.command == 'send-test':
        exit_code, _, _, _ = _run_dealbot_command(
            root_dir=root_dir,
            args=['--send-test', *(['--offline-snapshot', args.offline_snapshot] if args.offline_snapshot is not None else [])],
            command_name='send-test',
            runner=command_runner,
        )
        return exit_code

    if args.command == 'doctor':
        for line in render_bootstrap_diagnostics(load_project_env(root_dir)):
            safe_print(line)
        artifacts = discover_latest_artifacts(root_dir)
        payload = load_json(artifacts.operator_truth_report)
        summary = build_doctor_summary(
            report_path=artifacts.operator_truth_report,
            payload=payload,
            artifacts=artifacts,
        )
        summary['workflow_artifact_path'] = str(emit_workflow_artifact(root_dir, summary, subject_id='doctor'))
        for line in render_doctor_summary(summary):
            safe_print(line)
        if args.strict and (payload is None or not summary.get('truth_ready')):
            return 1
        return 0

    if args.command == 'latest-artifacts':
        for line in render_bootstrap_diagnostics(load_project_env(root_dir)):
            safe_print(line)
        artifacts = discover_latest_artifacts(root_dir)
        summary = build_latest_artifacts_summary(artifacts)
        summary['workflow_artifact_path'] = str(emit_workflow_artifact(root_dir, summary, subject_id='latest_artifacts'))
        for line in render_latest_artifacts_summary(summary):
            safe_print(line)
        return 0

    if args.command == 'build-voice-package':
        result, manifest_path = build_voice_ready_package(root_dir, args)
        artifacts = discover_latest_artifacts(root_dir)
        summary = build_voice_package_summary(
            manifest_path=manifest_path,
            result=result,
            artifacts=artifacts,
        )
        summary['workflow_artifact_path'] = str(emit_workflow_artifact(root_dir, summary, subject_id='build_voice_package'))
        for line in render_voice_package_summary(summary):
            safe_print(line)
        return 0 if summary.get('status') == 'ok' else 1

    if args.command == 'preview-selected':
        for line in render_bootstrap_diagnostics(load_project_env(root_dir)):
            safe_print(line)
        settings = AppSettings.from_env(root_dir)
        result = asyncio.run(
            _execute_preview_selected(
                settings=settings,
                report_path=resolve_report_path(root_dir, args.from_report),
                candidate_id=int(args.candidate_id),
            )
        )
        artifacts = discover_latest_artifacts(root_dir)
        summary = build_preview_selected_summary(result=result, artifacts=artifacts)
        summary['workflow_artifact_path'] = str(
            emit_workflow_artifact(root_dir, summary, subject_id='preview-selected')
        )
        for line in render_preview_selected_summary(summary):
            safe_print(line)
        return 0 if result.created_report else 1

    if args.command == 'publish-previewed':
        for line in render_bootstrap_diagnostics(load_project_env(root_dir)):
            safe_print(line)
        settings = AppSettings.from_env(root_dir)
        repositories = Repositories(settings.db_path)
        repositories.initialize()
        use_case = PublishPreviewedUseCase(
            repositories,
            TelegramPublisher(settings),
            AnalyticsArtifactWriter(settings.analytics_output_dir),
        )
        result = asyncio.run(
            use_case.execute(
                report_path=resolve_report_path(root_dir, args.from_report),
            )
        )
        artifacts = discover_latest_artifacts(root_dir)
        summary = build_publish_previewed_summary(result=result, artifacts=artifacts)
        summary['workflow_artifact_path'] = str(
            emit_workflow_artifact(root_dir, summary, subject_id='publish-previewed')
        )
        for line in render_publish_previewed_summary(summary):
            safe_print(line)
        return 0 if result.published else 1

    raise RuntimeError(f'Unknown command: {args.command}')


if __name__ == '__main__':
    raise SystemExit(main())

