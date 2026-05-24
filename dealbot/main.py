from __future__ import annotations

import argparse
import asyncio
from dataclasses import replace
from datetime import datetime
import logging
import os
from pathlib import Path
import random
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from application.use_cases.dry_run_render import DryRunRenderUseCase
from application.use_cases.enrich_offer import EnrichOfferUseCase
from application.use_cases.generate_analytics_artifacts import GenerateAnalyticsArtifactsUseCase
from application.use_cases.generate_roundup_artifacts import GenerateRoundupArtifactsUseCase
from application.use_cases.generate_video_manifests import GenerateVideoManifestsUseCase
from application.use_cases.ingest_health_controller import IngestHealthController
from application.use_cases.ingest_source import IngestSourceUseCase
from application.use_cases.offline_validation_snapshot import OfflineSnapshotBundle, OfflineValidationSnapshotManager
from application.use_cases.operator_truth_report import OperatorTruthReporter
from application.use_cases.plan_queue import PlanQueueUseCase, PlannedCandidate, QueuePlan
from application.use_cases.publish_next import PublishNextUseCase
from dealbot.settings import AppSettings, ConfigurationError, load_project_env, render_bootstrap_diagnostics
from domain.policies.content_lane_policy import ContentLanePolicy
from domain.policies.dedup_policy import DedupPolicy
from domain.policies.decision_policy import DecisionPolicy
from domain.policies.editorial_policy import EditorialPolicy
from domain.policies.publish_priority_engine import PublishPriorityEngine
from domain.policies.quality_gate_policy import QualityGatePolicy
from infrastructure.analytics.artifact_writer import AnalyticsArtifactWriter
from infrastructure.clients.base_http import ResilientHttpClient
from infrastructure.clients.epic_client import EpicClient
from infrastructure.clients.steam_events_client import SteamEventsClient
from infrastructure.clients.steam_client import SteamClient
from infrastructure.db.repositories import Repositories
from infrastructure.editorial.control_loader import EditorialControlLoader
from infrastructure.observability.logger import configure_logging
from infrastructure.observability.metrics import Metrics
from infrastructure.render.cards.renderer_selector import CardRendererRouter
from infrastructure.render.cards.roundup_top_list_card_adapter import RoundupTopListCardAdapter
from infrastructure.telegram.caption_builder import TelegramCaptionBuilder
from infrastructure.telegram.publisher import TelegramPublisher
from infrastructure.video.manifest_writer import VideoManifestWriter


LOGGER = logging.getLogger(__name__)


def safe_print(line: str) -> None:
    text = f'{line}\n'
    encoding = getattr(sys.stdout, 'encoding', None) or 'utf-8'
    try:
        sys.stdout.write(text)
    except UnicodeEncodeError:
        sys.stdout.write(text.encode(encoding, errors='replace').decode(encoding, errors='replace'))


def _seed_offline_preview_credentials(args: argparse.Namespace) -> None:
    """Offline preview should not require real Telegram publish credentials."""
    if not (args.preview and args.offline_snapshot is not None):
        return
    if not os.getenv('BOT_TOKEN', '').strip():
        os.environ['BOT_TOKEN'] = 'offline-preview-token'
    if not os.getenv('CHANNEL_USERNAME', '').strip():
        os.environ['CHANNEL_USERNAME'] = '@offline_preview'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Production-grade Telegram deal bot for Steam/Epic promotions')
    parser.add_argument('--once', action='store_true', help='Run one planning + publish cycle and exit')
    parser.add_argument('--send-test', action='store_true', help='Plan queue and force-send one test post to Telegram')
    parser.add_argument('--preview', action='store_true', help='Refresh queue and print planned/reserve items without posting')
    parser.add_argument(
        '--post-mode',
        choices=('single_discount', 'freebie', 'roundup', 'any'),
        default='any',
        help='Optional preview filter for operator mode. Applies only to --preview.',
    )
    parser.add_argument(
        '--offline-snapshot',
        nargs='?',
        const='latest',
        default=None,
        help='Use an offline validation snapshot instead of live ingest. Omit the value to use the latest snapshot.',
    )
    parser.add_argument('--capture-offline-snapshot', action='store_true', help='Capture the current queue/database state into an offline validation snapshot')
    parser.add_argument(
        '--promote-offline-snapshot',
        nargs='?',
        const='latest',
        default=None,
        help='Promote an eligible offline validation snapshot into the preserved golden snapshot. When combined with --capture-offline-snapshot, the newly captured snapshot is promoted.',
    )
    parser.add_argument('--reset-memory', action='store_true', help='Clear publication history, queues and outbox before execution')
    return parser.parse_args()


class BotRuntime:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.repositories = Repositories(settings.db_path)
        self.repositories.initialize()
        self.metrics = Metrics()
        self.timezone = self._load_timezone(settings.operational.timezone)
        self.snapshot_manager = OfflineValidationSnapshotManager(self.settings.analytics_output_dir.parent / 'offline_validation')
        self.last_run_diagnostics = None
        self.active_offline_snapshot: OfflineSnapshotBundle | None = None
        self.last_auto_golden_bundle: OfflineSnapshotBundle | None = None
        self.last_auto_golden_source: str | None = None
        self.ingest_health = IngestHealthController(
            repositories=self.repositories,
            writer=AnalyticsArtifactWriter(self.settings.analytics_output_dir),
            metrics=self.metrics,
        )
        self.operator_truth = OperatorTruthReporter(
            repositories=self.repositories,
            writer=AnalyticsArtifactWriter(self.settings.analytics_output_dir),
        )
        self.last_operator_truth_artifact = None

    async def __aenter__(self) -> 'BotRuntime':
        self.http_client = httpx.AsyncClient(
            timeout=self.settings.static.http_timeout_seconds,
            follow_redirects=True,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'Accept-Language': 'uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7',
            },
        )
        self.http = ResilientHttpClient(self.http_client)
        steam_client = SteamClient(self.http, self.settings.steam_access)
        epic_client = EpicClient(self.http)
        steam_events_client = SteamEventsClient(self.http, self.settings.event_ingestion)
        control_loader = EditorialControlLoader(
            self.settings.editorial_control.control_dir,
            self.settings.editorial_control.whitelist_priority_boost,
        )

        quality_gate = QualityGatePolicy(
            min_review_count=self.settings.editorial.min_review_count,
            publisher_whitelist=set(self.settings.editorial.publisher_whitelist),
        )
        editorial_policy = EditorialPolicy(
            min_game_of_the_day_score=self.settings.editorial.min_game_of_the_day_score,
        )
        decision_policy = DecisionPolicy(
            quality_gate=quality_gate,
            editorial_policy=editorial_policy,
        )
        dedup_policy = DedupPolicy(
            cooldown_game_days=self.settings.editorial.cooldown_game_days,
            franchise_cooldown_hours=self.settings.editorial.franchise_cooldown_hours,
            min_price_drop_minor=self.settings.editorial.min_price_drop_minor,
            min_discount_delta=self.settings.editorial.min_discount_delta,
        )
        content_lanes = ContentLanePolicy()

        ingest = IngestSourceUseCase(self.settings, steam_client, epic_client, steam_events_client)
        enrich = EnrichOfferUseCase(steam_client)
        self.planner = PlanQueueUseCase(
            settings=self.settings,
            repositories=self.repositories,
            ingest_source=ingest,
            enrich_offer=enrich,
            decision_policy=decision_policy,
            dedup_policy=dedup_policy,
            content_lanes=content_lanes,
            control_loader=control_loader,
            metrics=self.metrics,
        )
        render = DryRunRenderUseCase(
            caption_builder=TelegramCaptionBuilder(self.settings.static.caption_limit),
            renderer=CardRendererRouter(
                self.settings.card_output_dir,
                renderer_mode=self.settings.rendering.card_renderer,
                fallback_to_legacy=self.settings.rendering.fallback_to_legacy,
            ),
            http=self.http,
        )
        self.analytics = GenerateAnalyticsArtifactsUseCase(
            repositories=self.repositories,
            writer=AnalyticsArtifactWriter(self.settings.analytics_output_dir),
            metrics=self.metrics,
        )
        self.roundups = GenerateRoundupArtifactsUseCase(
            repositories=self.repositories,
            writer=AnalyticsArtifactWriter(self.settings.analytics_output_dir),
            metrics=self.metrics,
            roundup_card_adapter=RoundupTopListCardAdapter(self.settings.card_output_dir),
        )
        try:
            self.video_manifests = GenerateVideoManifestsUseCase(
                repositories=self.repositories,
                writer=VideoManifestWriter(self.settings.video_manifest_output_dir),
                metrics=self.metrics,
            )
        except Exception as exc:
            LOGGER.warning('Video manifest side output disabled: %s', exc)
            self.video_manifests = None
        self.publisher = PublishNextUseCase(
            settings=self.settings,
            repositories=self.repositories,
            dry_run_render=render,
            publisher=TelegramPublisher(self.settings),
            content_lanes=content_lanes,
            publish_priority_engine=PublishPriorityEngine(content_lanes),
            metrics=self.metrics,
            video_manifests=self.video_manifests,
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.http_client.aclose()

    def reset(self) -> None:
        self.repositories.reset()

    def now(self) -> tuple[datetime, datetime]:
        now_utc = datetime.utcnow()
        now_local = datetime.now(self.timezone).replace(tzinfo=None)
        return now_utc, now_local

    async def preview(self, post_mode: str = 'any') -> None:
        now_utc, now_local = self.now()
        plan = await self.planner.execute(now_utc, now_local)
        diagnostics = self.ingest_health.evaluate(now_utc, plan)
        try:
            self.roundups.execute(now_utc, plan)
        except Exception as exc:
            LOGGER.warning('Roundup side output failed during preview: %s', exc)
        bundle = await self._capture_offline_snapshot(now_utc, plan)
        self._maybe_preserve_first_golden_snapshot(bundle, source='preview')
        selection = self.publisher.inspect_selection(now_utc, now_local, requested_post_mode=post_mode)
        target = await self.publisher.preview_send_test_target(now_utc, now_local, requested_post_mode=post_mode)
        self.last_operator_truth_artifact = await self._emit_operator_truth_report(
            now_utc,
            now_local,
            plan,
            mode='preview',
            diagnostics=diagnostics,
            offline_bundle=bundle,
            selection=selection,
            target=target,
        )

    async def preview_offline(self, bundle: OfflineSnapshotBundle, post_mode: str = 'any') -> None:
        self.active_offline_snapshot = bundle
        now_utc, now_local = self.now()
        plan = self._queue_plan_from_repository(bundle)
        diagnostics = self.ingest_health.evaluate(now_utc, plan)
        selection = self.publisher.inspect_selection(now_utc, now_local, requested_post_mode=post_mode)
        target = await self.publisher.preview_send_test_target(now_utc, now_local, requested_post_mode=post_mode)
        self.last_operator_truth_artifact = await self._emit_operator_truth_report(
            now_utc,
            now_local,
            plan,
            mode='preview_offline',
            diagnostics=diagnostics,
            offline_bundle=bundle,
            selection=selection,
            target=target,
        )

    async def publish_from_existing_queue(
        self,
        bundle: OfflineSnapshotBundle,
        *,
        force_publish: bool,
        operator_mode: str | None = None,
    ):
        self.active_offline_snapshot = bundle
        now_utc, now_local = self.now()
        plan = self._queue_plan_from_repository(bundle)
        diagnostics = self.ingest_health.evaluate(now_utc, plan)
        try:
            self.roundups.execute(now_utc, plan)
        except Exception as exc:
            LOGGER.warning('Roundup side output failed for offline snapshot %s: %s', bundle.run_key, exc)

        selection = None
        target = None
        if operator_mode is not None:
            selection = self.publisher.inspect_selection(now_utc, now_local)
            target = await self.publisher.preview_send_test_target(now_utc, now_local)

        result = await self.publisher.execute(now_utc, now_local, force_publish=force_publish)
        if operator_mode is not None:
            self.last_operator_truth_artifact = await self._emit_operator_truth_report(
                now_utc,
                now_local,
                plan,
                mode=operator_mode,
                diagnostics=diagnostics,
                publish_result=result,
                offline_bundle=bundle,
                selection=selection,
                target=target,
            )
        try:
            self.analytics.execute(now_utc, plan, result)
        except Exception as exc:
            LOGGER.warning('Analytics side output failed for offline snapshot %s: %s', bundle.run_key, exc)
        return result

    async def plan_and_publish_once(
        self,
        force_publish: bool = False,
        *,
        capture_offline_snapshot: bool = False,
        operator_mode: str | None = None,
    ):
        now_utc, now_local = self.now()
        plan = await self.planner.execute(now_utc, now_local)
        diagnostics = self.ingest_health.evaluate(now_utc, plan)

        if diagnostics.fatal_ingest:
            diagnostics = self.ingest_health.finalize(diagnostics, pipeline_action='stopped_fatal_ingest')
            self.ingest_health.emit(diagnostics)
            self.last_run_diagnostics = diagnostics
            if operator_mode is not None:
                self.last_operator_truth_artifact = await self._emit_operator_truth_report(
                    now_utc,
                    now_local,
                    plan,
                    mode=operator_mode,
                    diagnostics=diagnostics,
                )
            LOGGER.error('Fatal ingest detected for run %s; stopping pipeline before publish.', diagnostics.run_key)
            return None

        if diagnostics.empty_window:
            diagnostics = self.ingest_health.finalize(diagnostics, pipeline_action='skipped_empty_window')
            self.ingest_health.emit(diagnostics)
            self.last_run_diagnostics = diagnostics
            if operator_mode is not None:
                self.last_operator_truth_artifact = await self._emit_operator_truth_report(
                    now_utc,
                    now_local,
                    plan,
                    mode=operator_mode,
                    diagnostics=diagnostics,
                )
            LOGGER.warning('Planner window is empty for run %s; skipping publish.', diagnostics.run_key)
            return None

        try:
            self.roundups.execute(now_utc, plan)
        except Exception as exc:
            LOGGER.warning('Roundup side output failed: %s', exc)

        bundle = None
        if capture_offline_snapshot:
            bundle = await self._capture_offline_snapshot(now_utc, plan)
            self._maybe_preserve_first_golden_snapshot(
                bundle,
                source='send_test' if force_publish else 'run_once',
            )

        selection = None
        target = None
        if operator_mode is not None:
            selection = self.publisher.inspect_selection(now_utc, now_local)
            target = await self.publisher.preview_send_test_target(now_utc, now_local)

        result = await self.publisher.execute(now_utc, now_local, force_publish=force_publish)
        diagnostics = self.ingest_health.finalize(
            diagnostics,
            pipeline_action='publish_attempted',
            publish_result=result,
        )
        self.ingest_health.emit(diagnostics)
        self.last_run_diagnostics = diagnostics
        if operator_mode is not None:
            self.last_operator_truth_artifact = await self._emit_operator_truth_report(
                now_utc,
                now_local,
                plan,
                mode=operator_mode,
                diagnostics=diagnostics,
                publish_result=result,
                offline_bundle=bundle,
                selection=selection,
                target=target,
            )
        try:
            self.analytics.execute(now_utc, plan, result)
        except Exception as exc:
            LOGGER.warning('Analytics side output failed: %s', exc)
        return result

    async def run_forever(self) -> None:
        while True:
            result = await self.plan_and_publish_once(force_publish=False)
            if self.last_run_diagnostics is not None and self.last_run_diagnostics.should_stop_pipeline:
                LOGGER.error('Stopping pipeline loop after fatal ingest health for run %s.', self.last_run_diagnostics.run_key)
                break
            if result is None:
                LOGGER.info('No publishable items found. Sleeping 15 minutes before next cycle.')
                await asyncio.sleep(15 * 60)
                continue
            LOGGER.info('Cycle result: %s / %s / %s', result.title, result.reason, result.message_id)
            delay_minutes = random.randint(
                self.settings.operational.min_interval_minutes,
                self.settings.operational.max_interval_minutes,
            )
            await asyncio.sleep(delay_minutes * 60)

    async def capture_current_queue_snapshot(self) -> OfflineSnapshotBundle | None:
        now_utc, _ = self.now()
        plan = self._queue_plan_from_repository(self.active_offline_snapshot)
        try:
            self.roundups.execute(now_utc, plan)
        except Exception as exc:
            LOGGER.warning('Roundup side output failed while capturing current offline snapshot: %s', exc)
        return await self._capture_offline_snapshot(now_utc, plan)

    def promote_offline_snapshot(self, source: OfflineSnapshotBundle | str | None = None) -> OfflineSnapshotBundle:
        bundle = self.snapshot_manager.promote_golden(source)
        LOGGER.info('Offline validation golden snapshot preserved at %s', bundle.base_db_path)
        return bundle

    def _maybe_preserve_first_golden_snapshot(
        self,
        bundle: OfflineSnapshotBundle | None,
        *,
        source: str,
    ) -> OfflineSnapshotBundle | None:
        self.last_auto_golden_bundle = None
        self.last_auto_golden_source = None
        if bundle is None or not bool(bundle.quality.get('golden_eligible')):
            return None
        try:
            existing = self.snapshot_manager.resolve('golden')
        except FileNotFoundError:
            existing = None
        if existing is not None:
            LOGGER.info('Golden snapshot already preserved at %s; leaving live candidate %s as manual refresh only.', existing.base_db_path, bundle.run_key)
            return None
        try:
            golden_bundle = self.snapshot_manager.promote_golden(bundle)
        except ValueError as exc:
            LOGGER.warning('Automatic first golden snapshot promotion skipped for %s: %s', bundle.run_key, exc)
            return None
        self.last_auto_golden_bundle = golden_bundle
        self.last_auto_golden_source = source
        LOGGER.info('Automatically preserved first golden snapshot from live %s at %s', source, golden_bundle.base_db_path)
        return golden_bundle

    async def _capture_offline_snapshot(self, now_utc: datetime, plan: QueuePlan) -> OfflineSnapshotBundle | None:
        try:
            bundle = await self.snapshot_manager.capture(
                live_db_path=self.settings.db_path,
                run_key=now_utc.strftime('%Y%m%dT%H%M%SZ'),
                created_at=now_utc,
                plan=plan,
                http=self.http,
            )
        except Exception as exc:
            LOGGER.warning('Offline validation snapshot capture failed: %s', exc)
            return None
        LOGGER.info('Offline validation snapshot refreshed at %s', bundle.base_db_path)
        return bundle

    def _queue_plan_from_repository(self, bundle: OfflineSnapshotBundle | None = None) -> QueuePlan:
        planned_records = self.repositories.list_queue('planned')
        reserve_records = self.repositories.list_queue('reserve')
        context = dict((bundle.context if bundle is not None else {}) or {})
        context.setdefault('source', 'current_queue')
        if bundle is not None:
            context['offline_snapshot_run_key'] = bundle.run_key
            context['offline_snapshot_created_at'] = bundle.created_at
            context['offline_snapshot_role'] = bundle.snapshot_role
        metrics = dict((bundle.metrics if bundle is not None else {}) or {})
        return QueuePlan(
            planned=[self._record_to_candidate(record) for record in planned_records],
            reserve=[self._record_to_candidate(record) for record in reserve_records],
            metrics=metrics,
            context=context,
        )

    @staticmethod
    def _record_to_candidate(record) -> PlannedCandidate:
        return PlannedCandidate(score=record.score, offer=record.offer, decision_json=record.decision_json)

    async def _emit_operator_truth_report(
        self,
        now_utc: datetime,
        now_local: datetime,
        plan: QueuePlan,
        *,
        mode: str,
        diagnostics=None,
        publish_result=None,
        offline_bundle: OfflineSnapshotBundle | None = None,
        selection=None,
        target=None,
    ):
        selection = selection or self.publisher.inspect_selection(now_utc, now_local)
        target = target or await self.publisher.preview_send_test_target(now_utc, now_local)
        artifact = self.operator_truth.emit(
            now_utc=now_utc,
            mode=mode,
            settings=self.settings,
            plan=plan,
            selection=selection,
            target=target,
            diagnostics=diagnostics,
            publish_result=publish_result,
            offline_bundle=offline_bundle,
        )
        self._print_operator_truth_report(artifact.payload_json, artifact)
        return artifact

    @staticmethod
    def _print_operator_truth_report(payload: dict, artifact) -> None:
        queue = dict(payload.get('queue') or {})
        buckets = dict(queue.get('buckets') or {})
        planned = dict(buckets.get('planned') or {})
        reserve = dict(buckets.get('reserve') or {})
        selection = dict(payload.get('selection') or {})
        target = dict(payload.get('send_test_target') or {})
        target_candidate = dict(target.get('candidate') or {})
        target_artifact = dict(target.get('artifact') or {})
        roundup = dict(selection.get('roundup_injection') or {})
        verdict = dict(payload.get('verdict') or {})
        telegram = dict(payload.get('telegram') or {})
        publish_result = telegram.get('publish_result') or {}
        outbox = telegram.get('outbox') or {}

        safe_print(f'operator-truth[{payload.get("mode")}/{payload.get("scope")}] :: verdict={verdict.get("verdict")} :: truth_ready={"yes" if verdict.get("truth_ready") else "no"}')
        ingest_sources = dict(payload.get('ingest_sources') or {})
        if ingest_sources:
            for source_name, snapshot in ingest_sources.items():
                details = dict(snapshot or {})
                safe_print(
                    f'ingest[{source_name}] :: status={details.get("status") or "unknown"} '
                    f':: offers={int(details.get("offers") or 0)} :: reason={details.get("reason") or "unknown"}'
                )
        else:
            safe_print('ingest :: unavailable')

        safe_print(
            'queue :: '
            f'planned={int(planned.get("total") or 0)} '
            f'reserve={int(reserve.get("total") or 0)} '
            f'deferred={int(queue.get("deferred_total") or 0)} '
            f':: planned_families={BotRuntime._format_counts(planned.get("by_family") or {})} '
            f':: reserve_families={BotRuntime._format_counts(reserve.get("by_family") or {})}'
        )
        safe_print(
            'selector :: '
            f'eligible={int(selection.get("eligible_candidates_total") or 0)} '
            f'blocked={int(selection.get("blocked_candidates_total") or 0)} '
            f'quiet_hours={"yes" if selection.get("quiet_hours") else "no"} '
            f'reserve_visible={int(selection.get("visible_reserve_total") or 0)} '
            f':: roundup_status={roundup.get("status") or "n/a"} '
            f':: roundup_reason={roundup.get("reason") or "n/a"}'
        )

        if target_candidate:
            safe_print(
                'selected :: '
                f'row={target_candidate.get("row_id")} '
                f'[{target_candidate.get("bucket")}] '
                f'[{target_candidate.get("content_family")}/{target_candidate.get("lane")}] '
                f'{target_candidate.get("source")} :: {target_candidate.get("offer_id")} :: {target_candidate.get("title")}'
            )
        else:
            safe_print('selected :: none')

        safe_print(
            'target :: '
            f'would_send={"yes" if target.get("would_send") else "no"} '
            f':: blocker_category={target.get("blocker_category") or "none"} '
            f':: blocker_reason={target.get("blocker_reason") or "none"}'
        )
        if target_artifact:
            safe_print(
                'artifact :: '
                f'template={target_artifact.get("template_id") or "n/a"} '
                f':: card_family={target_artifact.get("card_family") or "n/a"} '
                f':: image={target_artifact.get("image_path") or "n/a"} '
                f':: outbox_status={target.get("outbox_status") or "none"}'
            )
            safe_print(
                'caption :: '
                f'len={int(target_artifact.get("caption_length") or 0)} '
                f':: {target_artifact.get("caption_preview") or "n/a"}'
            )
            safe_print(f'assets :: {BotRuntime._format_assets(target_artifact.get("assets_used") or [])}')

        BotRuntime._print_candidate_rows('publishable-row', selection.get('eligible_candidates') or [])
        BotRuntime._print_candidate_rows('blocked-row', selection.get('blocked_candidates') or [], include_blocker=True)

        offline_snapshot = payload.get('offline_snapshot') or {}
        if offline_snapshot:
            quality = dict(offline_snapshot.get('quality') or {})
            blockers = quality.get('blocking_reasons') or []
            safe_print(
                'offline :: '
                f'role={offline_snapshot.get("snapshot_role")} '
                f':: manifest={offline_snapshot.get("manifest_path")} '
                f':: blockers={", ".join(blockers) if blockers else "none"}'
            )

        if publish_result:
            safe_print(
                'send-test :: '
                f'published={"yes" if publish_result.get("published") else "no"} '
                f':: reason={publish_result.get("reason") or "none"} '
                f':: message_id={publish_result.get("message_id") or "none"} '
                f':: last_error={outbox.get("last_error") or publish_result.get("failure_detail") or "none"}'
            )

        if artifact.json_path is not None:
            safe_print(f'report :: {artifact.json_path}')
        safe_print(
            'operator-verdict :: '
            f'category={verdict.get("blocker_category") or "none"} '
            f':: reason={verdict.get("blocker_reason") or "none"} '
            f':: next={verdict.get("next_step") or "Inspect the report JSON."}'
        )

    @staticmethod
    def _format_counts(values: dict) -> str:
        if not values:
            return 'none'
        return ', '.join(f'{key}={values[key]}' for key in sorted(values))

    @staticmethod
    def _format_assets(values: list) -> str:
        if not values:
            return 'none'
        normalized = [str(value) for value in values[:4]]
        if len(values) > 4:
            normalized.append(f'+{len(values) - 4} more')
        return ', '.join(normalized)

    @staticmethod
    def _print_candidate_rows(label: str, rows: list[dict], *, include_blocker: bool = False, limit: int = 8) -> None:
        for row in list(rows)[:limit]:
            suffix = ''
            if include_blocker:
                suffix = f' :: blocker={row.get("blocker_reason") or "none"} :: detail={row.get("blocker_detail") or "none"}'
            else:
                suffix = f' :: total={row.get("total_priority") if row.get("total_priority") is not None else "n/a"}'
            safe_print(
                f'{label} :: row={row.get("row_id")} :: [{row.get("bucket")}] '
                f'[{row.get("content_family")}/{row.get("lane")}] :: {row.get("offer_id")} :: {row.get("title")}{suffix}'
            )
        if len(rows) > limit:
            safe_print(f'{label} :: +{len(rows) - limit} more')

    @staticmethod
    def _load_timezone(name: str):
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError:
            LOGGER.warning('Timezone %s not found, falling back to UTC', name)
            return ZoneInfo('UTC')


def _print_auto_golden_status(runtime: BotRuntime) -> None:
    bundle = runtime.last_auto_golden_bundle
    if bundle is None:
        return
    source = runtime.last_auto_golden_source or 'live_cycle'
    safe_print(f'golden-auto[{source}] :: {bundle.base_db_path} :: {runtime.snapshot_manager.format_summary(bundle)}')


def _print_bootstrap_diagnostics(root_dir: Path) -> None:
    for line in render_bootstrap_diagnostics(load_project_env(root_dir)):
        safe_print(line)


async def async_main() -> None:
    args = parse_args()
    root_dir = Path(__file__).resolve().parents[1]
    _seed_offline_preview_credentials(args)
    _print_bootstrap_diagnostics(root_dir)
    settings = AppSettings.from_env(root_dir)
    configure_logging()

    offline_bundle = None
    if args.offline_snapshot is not None:
        if not (args.preview or args.send_test or args.once or args.promote_offline_snapshot is not None):
            raise RuntimeError('Offline snapshots are supported only with --preview, --send-test, --once, or --promote-offline-snapshot.')
        offline_manager = OfflineValidationSnapshotManager(settings.analytics_output_dir.parent / 'offline_validation')
        offline_bundle = offline_manager.resolve(args.offline_snapshot)
        runtime_db_path = offline_bundle.base_db_path
        if args.send_test:
            runtime_db_path = offline_manager.create_runtime_db_copy(offline_bundle, purpose='send_test')
        elif args.once:
            runtime_db_path = offline_manager.create_runtime_db_copy(offline_bundle, purpose='run_once')
        settings = replace(settings, db_path=runtime_db_path)

    async with BotRuntime(settings) as runtime:
        if offline_bundle is not None:
            runtime.active_offline_snapshot = offline_bundle
        if args.reset_memory:
            runtime.reset()
        if args.capture_offline_snapshot:
            bundle = await runtime.capture_current_queue_snapshot()
            if bundle is None:
                safe_print('Offline snapshot capture failed.')
                raise SystemExit(1)
            safe_print(f'{bundle.run_key} :: {bundle.base_db_path} :: {runtime.snapshot_manager.format_summary(bundle)}')
            if args.promote_offline_snapshot is not None:
                try:
                    golden_bundle = runtime.promote_offline_snapshot(bundle)
                except ValueError as exc:
                    safe_print(f'Golden snapshot not updated: {exc}')
                    raise SystemExit(1)
                safe_print(f'golden :: {golden_bundle.base_db_path} :: {runtime.snapshot_manager.format_summary(golden_bundle)}')
            return
        if args.promote_offline_snapshot is not None:
            try:
                promote_source = offline_bundle if offline_bundle is not None else args.promote_offline_snapshot
                golden_bundle = runtime.promote_offline_snapshot(promote_source)
            except (FileNotFoundError, ValueError) as exc:
                safe_print(str(exc))
                raise SystemExit(1)
            safe_print(f'golden :: {golden_bundle.base_db_path} :: {runtime.snapshot_manager.format_summary(golden_bundle)}')
            return
        if args.preview:
            if offline_bundle is not None:
                await runtime.preview_offline(offline_bundle, args.post_mode)
            else:
                await runtime.preview(args.post_mode)
                _print_auto_golden_status(runtime)
            return
        if args.send_test:
            if offline_bundle is not None:
                await runtime.publish_from_existing_queue(
                    offline_bundle,
                    force_publish=True,
                    operator_mode='send_test_offline',
                )
                return
            await runtime.plan_and_publish_once(
                force_publish=True,
                capture_offline_snapshot=True,
                operator_mode='send_test',
            )
            _print_auto_golden_status(runtime)
            return
        if args.once:
            if offline_bundle is not None:
                result = await runtime.publish_from_existing_queue(offline_bundle, force_publish=False)
                if result is None:
                    safe_print('No publishable items found.')
                else:
                    safe_print(f'{result.title} :: {result.reason} :: {result.message_id}')
                return
            result = await runtime.plan_and_publish_once(force_publish=False, capture_offline_snapshot=True)
            if result is None:
                if runtime.last_run_diagnostics is not None and runtime.last_run_diagnostics.should_stop_pipeline:
                    safe_print('Fatal ingest detected. Pipeline stopped.')
                elif runtime.last_run_diagnostics is not None and runtime.last_run_diagnostics.empty_window:
                    safe_print('Planner window is empty.')
                else:
                    safe_print('No publishable items found.')
            else:
                safe_print(f'{result.title} :: {result.reason} :: {result.message_id}')
            _print_auto_golden_status(runtime)
            return
        await runtime.run_forever()


def main() -> None:
    try:
        asyncio.run(async_main())
    except ConfigurationError as exc:
        safe_print(f'configuration-error :: {exc}')
        raise SystemExit(1) from exc


if __name__ == '__main__':
    main()
