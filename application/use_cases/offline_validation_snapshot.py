from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
from typing import Any
from urllib.parse import unquote, urlparse

from application.use_cases.plan_queue import QueuePlan
from domain.entities.offer import Offer
from infrastructure.clients.base_http import ResilientHttpClient
from infrastructure.db.repositories import QueueRecord, Repositories
from infrastructure.render.cards.asset_source import resolve_existing_asset_path


SNAPSHOT_MANIFEST_NAME = 'snapshot_manifest.json'
SNAPSHOT_DB_NAME = 'dealbot.sqlite3'
GOLDEN_DIR_NAME = 'golden'
GOLDEN_CURRENT_DIR_NAME = 'current'


@dataclass(slots=True)
class OfflineSnapshotBundle:
    root_dir: Path
    manifest_path: Path
    base_db_path: Path
    run_key: str
    created_at: str
    context: dict[str, Any]
    metrics: dict[str, int]
    planned_count: int
    reserve_count: int
    asset_localization: dict[str, int]
    quality: dict[str, Any]
    snapshot_role: str
    golden_promoted_at: str | None
    golden_source_run_key: str | None


class OfflineValidationSnapshotManager:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = Path(root_dir)
        self.snapshots_dir = self.root_dir / 'snapshots'
        self.golden_dir = self.root_dir / GOLDEN_DIR_NAME
        self.golden_current_dir = self.golden_dir / GOLDEN_CURRENT_DIR_NAME
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.golden_dir.mkdir(parents=True, exist_ok=True)

    async def capture(
        self,
        *,
        live_db_path: Path,
        run_key: str,
        created_at: datetime,
        plan: QueuePlan,
        http: ResilientHttpClient,
    ) -> OfflineSnapshotBundle:
        snapshot_dir = self.snapshots_dir / run_key
        if snapshot_dir.exists():
            shutil.rmtree(snapshot_dir)
        assets_dir = snapshot_dir / 'assets'
        queue_assets_dir = assets_dir / 'queue'
        roundup_assets_dir = assets_dir / 'roundup'
        analytics_dir = snapshot_dir / 'analytics'
        runtime_dir = snapshot_dir / 'runtime'
        for directory in (queue_assets_dir, roundup_assets_dir, analytics_dir, runtime_dir):
            directory.mkdir(parents=True, exist_ok=True)

        base_db_path = snapshot_dir / SNAPSHOT_DB_NAME
        shutil.copy2(live_db_path, base_db_path)

        stats = {
            'localized_total': 0,
            'copied_local': 0,
            'downloaded_remote': 0,
            'reused_localized': 0,
            'unresolved_remote': 0,
            'unsupported_reference': 0,
            'roundup_assets_copied': 0,
            'roundup_assets_missing': 0,
        }

        await self._localize_queue_assets(base_db_path, queue_assets_dir, http, stats)
        await self._localize_roundup_assets(base_db_path, roundup_assets_dir, analytics_dir, http, stats)

        manifest_path = snapshot_dir / SNAPSHOT_MANIFEST_NAME
        quality = self._build_quality_summary(
            base_db_path,
            planned_count=len(plan.planned),
            reserve_count=len(plan.reserve),
            stats=stats,
        )
        manifest = {
            'manifest_version': 1,
            'run_key': run_key,
            'created_at': created_at.isoformat(),
            'base_db_path': str(base_db_path),
            'live_db_path': str(live_db_path),
            'planned_count': len(plan.planned),
            'reserve_count': len(plan.reserve),
            'context': dict(plan.context or {}),
            'metrics': dict(plan.metrics or {}),
            'asset_localization': dict(stats),
            'quality': quality,
            'snapshot_role': 'candidate',
            'golden_promoted_at': None,
            'golden_source_run_key': None,
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
        return self._bundle_from_manifest_path(manifest_path)

    def resolve(self, spec: str | None = None) -> OfflineSnapshotBundle:
        manifest_path = self._resolve_manifest_path(spec)
        return self._bundle_from_manifest_path(manifest_path)

    def promote_golden(self, source: OfflineSnapshotBundle | str | None = None, *, promoted_at: datetime | None = None) -> OfflineSnapshotBundle:
        bundle = source if isinstance(source, OfflineSnapshotBundle) else self.resolve(source)
        quality = dict(bundle.quality or {})
        if not quality:
            quality = self._build_quality_summary(
                bundle.base_db_path,
                planned_count=bundle.planned_count,
                reserve_count=bundle.reserve_count,
                stats=bundle.asset_localization,
            )
        if not bool(quality.get('golden_eligible')):
            blockers = [str(item) for item in quality.get('blocking_reasons') or [] if str(item).strip()]
            reason_text = ', '.join(blockers) if blockers else 'snapshot_not_golden_eligible'
            raise ValueError(f'Offline validation snapshot is not eligible for golden preservation: {reason_text}')

        if self.golden_current_dir.exists():
            shutil.rmtree(self.golden_current_dir)
        shutil.copytree(bundle.root_dir, self.golden_current_dir, ignore=shutil.ignore_patterns('runtime'))
        (self.golden_current_dir / 'runtime').mkdir(parents=True, exist_ok=True)

        manifest_path = self.golden_current_dir / SNAPSHOT_MANIFEST_NAME
        payload = json.loads(manifest_path.read_text(encoding='utf-8'))
        payload['base_db_path'] = str(self.golden_current_dir / SNAPSHOT_DB_NAME)
        payload['quality'] = quality
        payload['snapshot_role'] = 'golden'
        payload['golden_promoted_at'] = (promoted_at or datetime.utcnow()).isoformat()
        payload['golden_source_run_key'] = bundle.run_key
        manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
        return self._bundle_from_manifest_path(manifest_path)

    def create_runtime_db_copy(self, bundle: OfflineSnapshotBundle, *, purpose: str) -> Path:
        runtime_dir = bundle.root_dir / 'runtime'
        runtime_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.utcnow().strftime('%Y%m%dT%H%M%S%fZ')
        runtime_db_path = runtime_dir / f'{purpose}_{stamp}.sqlite3'
        shutil.copy2(bundle.base_db_path, runtime_db_path)
        return runtime_db_path

    def format_summary(self, bundle: OfflineSnapshotBundle) -> str:
        quality = dict(bundle.quality or {})
        blockers = [str(item) for item in quality.get('blocking_reasons') or [] if str(item).strip()]
        blocker_text = ','.join(blockers) if blockers else 'none'
        return (
            f'role={bundle.snapshot_role} '
            f'planned={bundle.planned_count} '
            f'reserve={bundle.reserve_count} '
            f'planned_local_assets={int(quality.get("planned_rows_with_local_assets") or 0)} '
            f'roundup_local_cards={int(quality.get("roundup_snapshots_with_local_cards") or 0)} '
            f'send_test_ready={"yes" if quality.get("send_test_offline_ready") else "no"} '
            f'golden_eligible={"yes" if quality.get("golden_eligible") else "no"} '
            f'blockers={blocker_text}'
        )

    async def _localize_queue_assets(
        self,
        db_path: Path,
        assets_dir: Path,
        http: ResilientHttpClient,
        stats: dict[str, int],
    ) -> None:
        repositories = Repositories(db_path)
        for bucket in ('planned', 'reserve'):
            records = repositories.list_queue(bucket)
            if not records:
                continue
            localized_rows: list[tuple[float, Offer, dict[str, Any]]] = []
            created_at = records[0].created_at
            for record in records:
                localized_offer = await self._localize_offer_assets(record.offer, assets_dir, http, stats)
                localized_rows.append((record.score, localized_offer, record.decision_json))
            repositories.replace_queue(bucket, localized_rows, created_at=created_at)

    async def _localize_offer_assets(
        self,
        offer: Offer,
        assets_dir: Path,
        http: ResilientHttpClient,
        stats: dict[str, int],
    ) -> Offer:
        snapshot = offer.to_snapshot()
        assets = dict(snapshot.get('assets') or {})
        for key in ('hero', 'header', 'screenshot', 'fallback'):
            assets[key] = await self._localize_asset_reference(assets.get(key), assets_dir, http, stats)
        snapshot['assets'] = assets
        return Offer.from_snapshot(snapshot)

    async def _localize_roundup_assets(
        self,
        db_path: Path,
        assets_dir: Path,
        analytics_dir: Path,
        http: ResilientHttpClient,
        stats: dict[str, int],
    ) -> None:
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                """
                SELECT id, run_key, json_path, payload_json
                FROM analytics_artifacts
                WHERE artifact_type = 'roundup_snapshot'
                ORDER BY created_at DESC, id DESC
                """
            ).fetchall()
            for row in rows:
                try:
                    payload = json.loads(row['payload_json'])
                except (TypeError, json.JSONDecodeError):
                    continue
                if not isinstance(payload, dict):
                    continue
                roundups = payload.get('roundups') or []
                if not isinstance(roundups, list):
                    roundups = []
                for roundup in roundups:
                    if not isinstance(roundup, dict):
                        continue
                    original_path = roundup.get('card_asset_path')
                    localized_path = await self._localize_asset_reference(original_path, assets_dir, http, stats)
                    if localized_path and localized_path != original_path:
                        stats['roundup_assets_copied'] = int(stats.get('roundup_assets_copied', 0)) + 1
                    elif original_path and localized_path == original_path:
                        stats['roundup_assets_missing'] = int(stats.get('roundup_assets_missing', 0)) + 1
                    roundup['card_asset_path'] = localized_path
                output_name = self._roundup_json_name(row['run_key'], row['json_path'])
                output_json_path = analytics_dir / output_name
                output_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
                connection.execute(
                    'UPDATE analytics_artifacts SET payload_json = ?, json_path = ? WHERE id = ?',
                    (json.dumps(payload, ensure_ascii=False, sort_keys=True), str(output_json_path), row['id']),
                )
            connection.commit()
        finally:
            connection.close()

    async def _localize_asset_reference(
        self,
        value: str | None,
        assets_dir: Path,
        http: ResilientHttpClient,
        stats: dict[str, int],
    ) -> str | None:
        if not value:
            return None

        reference = str(value)
        suffix = self._asset_suffix(reference)
        target_path = assets_dir / f'{hashlib.sha256(reference.encode("utf-8")).hexdigest()}{suffix}'
        if target_path.exists() and target_path.stat().st_size > 0:
            stats['reused_localized'] = int(stats.get('reused_localized', 0)) + 1
            return str(target_path)

        local_path = resolve_existing_asset_path(reference)
        if local_path is not None:
            shutil.copy2(local_path, target_path)
            stats['localized_total'] = int(stats.get('localized_total', 0)) + 1
            stats['copied_local'] = int(stats.get('copied_local', 0)) + 1
            return str(target_path)

        parsed = urlparse(reference)
        if parsed.scheme in {'http', 'https'}:
            try:
                content = await http.get_bytes(reference)
            except Exception:
                stats['unresolved_remote'] = int(stats.get('unresolved_remote', 0)) + 1
                return reference
            target_path.write_bytes(content)
            stats['localized_total'] = int(stats.get('localized_total', 0)) + 1
            stats['downloaded_remote'] = int(stats.get('downloaded_remote', 0)) + 1
            return str(target_path)

        stats['unsupported_reference'] = int(stats.get('unsupported_reference', 0)) + 1
        return reference

    def _resolve_manifest_path(self, spec: str | None = None) -> Path:
        normalized = str(spec or 'latest').strip().lower()
        if normalized in {'latest', ''}:
            manifests = sorted(self.snapshots_dir.glob(f'*/{SNAPSHOT_MANIFEST_NAME}'), reverse=True)
            if not manifests:
                raise FileNotFoundError('No offline validation snapshots were found.')
            return manifests[0]

        if normalized in {'golden', 'latest-golden', 'current-golden'}:
            manifest_path = self.golden_current_dir / SNAPSHOT_MANIFEST_NAME
            if manifest_path.exists():
                return manifest_path
            raise FileNotFoundError('No golden offline validation snapshot was found.')

        raw = str(spec).strip()
        named_manifest = self.snapshots_dir / raw / SNAPSHOT_MANIFEST_NAME
        if named_manifest.exists():
            return named_manifest

        candidate = Path(raw)
        if candidate.is_dir():
            manifest_path = candidate / SNAPSHOT_MANIFEST_NAME
            if manifest_path.exists():
                return manifest_path
        elif candidate.is_file():
            if candidate.name == SNAPSHOT_MANIFEST_NAME:
                return candidate
            if candidate.suffix.lower() == '.sqlite3':
                manifest_path = candidate.parent / SNAPSHOT_MANIFEST_NAME
                if manifest_path.exists():
                    return manifest_path

        raise FileNotFoundError(f'Offline validation snapshot not found: {spec}')

    def _bundle_from_manifest_path(self, manifest_path: Path) -> OfflineSnapshotBundle:
        payload = json.loads(manifest_path.read_text(encoding='utf-8'))
        base_db_path = Path(payload.get('base_db_path') or (manifest_path.parent / SNAPSHOT_DB_NAME))
        if not base_db_path.exists():
            fallback_db_path = manifest_path.parent / SNAPSHOT_DB_NAME
            if fallback_db_path.exists():
                base_db_path = fallback_db_path
        quality_payload = payload.get('quality')
        if not isinstance(quality_payload, dict):
            quality_payload = self._build_quality_summary(
                base_db_path,
                planned_count=int(payload.get('planned_count') or 0),
                reserve_count=int(payload.get('reserve_count') or 0),
                stats=dict(payload.get('asset_localization') or {}),
            )
        return OfflineSnapshotBundle(
            root_dir=manifest_path.parent,
            manifest_path=manifest_path,
            base_db_path=base_db_path,
            run_key=str(payload.get('run_key') or manifest_path.parent.name),
            created_at=str(payload.get('created_at') or ''),
            context=dict(payload.get('context') or {}),
            metrics={str(key): int(value) for key, value in dict(payload.get('metrics') or {}).items()},
            planned_count=int(payload.get('planned_count') or 0),
            reserve_count=int(payload.get('reserve_count') or 0),
            asset_localization={str(key): int(value) for key, value in dict(payload.get('asset_localization') or {}).items()},
            quality=dict(quality_payload),
            snapshot_role=str(payload.get('snapshot_role') or 'candidate'),
            golden_promoted_at=str(payload.get('golden_promoted_at') or '') or None,
            golden_source_run_key=str(payload.get('golden_source_run_key') or '') or None,
        )

    def _build_quality_summary(
        self,
        db_path: Path,
        *,
        planned_count: int | None = None,
        reserve_count: int | None = None,
        stats: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        summary: dict[str, Any] = {
            'quality_version': 1,
            'queue_rows_total': 0,
            'publishable_planned_rows_total': 0,
            'planned_rows_total': 0,
            'reserve_rows_total': 0,
            'planned_rows_with_local_assets': 0,
            'planned_rows_without_local_assets': 0,
            'reserve_rows_with_local_assets': 0,
            'reserve_rows_without_local_assets': 0,
            'roundup_snapshots_total': 0,
            'roundup_snapshots_with_local_cards': 0,
            'roundup_snapshots_missing_local_cards': 0,
            'archive_posts_total': 0,
            'asset_localization_localized_total': int((stats or {}).get('localized_total') or 0),
            'asset_localization_unresolved_remote': int((stats or {}).get('unresolved_remote') or 0),
            'send_test_offline_ready': False,
            'captions_offline_ready': False,
            'cards_offline_ready': False,
            'artifact_rich': False,
            'usable_for_send_test_offline': False,
            'golden_eligible': False,
            'blocking_reasons': [],
            'warnings': [],
        }
        if not Path(db_path).exists():
            summary['blocking_reasons'] = ['snapshot_db_missing']
            return summary

        repositories = Repositories(db_path)
        planned_records = repositories.list_queue('planned')
        reserve_records = repositories.list_queue('reserve')
        planned_total = int(planned_count if planned_count is not None else len(planned_records))
        reserve_total = int(reserve_count if reserve_count is not None else len(reserve_records))
        planned_with_local_assets = self._count_rows_with_local_assets(planned_records)
        reserve_with_local_assets = self._count_rows_with_local_assets(reserve_records)
        roundup_total, roundup_with_local_cards, roundup_missing_cards, archive_posts_total = self._inspect_artifact_quality(db_path)

        summary.update(
            {
                'queue_rows_total': planned_total + reserve_total,
                'publishable_planned_rows_total': planned_total,
                'planned_rows_total': planned_total,
                'reserve_rows_total': reserve_total,
                'planned_rows_with_local_assets': planned_with_local_assets,
                'planned_rows_without_local_assets': max(planned_total - planned_with_local_assets, 0),
                'reserve_rows_with_local_assets': reserve_with_local_assets,
                'reserve_rows_without_local_assets': max(reserve_total - reserve_with_local_assets, 0),
                'roundup_snapshots_total': roundup_total,
                'roundup_snapshots_with_local_cards': roundup_with_local_cards,
                'roundup_snapshots_missing_local_cards': roundup_missing_cards,
                'archive_posts_total': archive_posts_total,
            }
        )
        summary['send_test_offline_ready'] = planned_total > 0
        summary['captions_offline_ready'] = (planned_total + reserve_total) > 0 or archive_posts_total > 0
        summary['cards_offline_ready'] = (planned_with_local_assets + reserve_with_local_assets + roundup_with_local_cards) > 0
        summary['artifact_rich'] = bool(summary['cards_offline_ready'])
        summary['usable_for_send_test_offline'] = bool(summary['send_test_offline_ready'] and planned_with_local_assets > 0)

        blockers: list[str] = []
        if planned_total <= 0:
            blockers.append('planned_queue_empty')
        if planned_with_local_assets <= 0:
            blockers.append('planned_assets_not_localized')
        summary['blocking_reasons'] = blockers
        summary['golden_eligible'] = not blockers

        warnings: list[str] = []
        if int((stats or {}).get('unresolved_remote') or 0) > 0:
            warnings.append('queue_assets_unresolved_remote')
        if roundup_missing_cards > 0:
            warnings.append('roundup_card_assets_missing')
        summary['warnings'] = warnings
        return summary

    def _inspect_artifact_quality(self, db_path: Path) -> tuple[int, int, int, int]:
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        roundup_total = 0
        roundup_with_local_cards = 0
        roundup_missing_cards = 0
        archive_posts_total = 0
        try:
            archive_posts_total = int(connection.execute('SELECT COUNT(*) FROM post_artifacts').fetchone()[0] or 0)
            rows = connection.execute(
                """
                SELECT payload_json
                FROM analytics_artifacts
                WHERE artifact_type = 'roundup_snapshot'
                ORDER BY created_at DESC, id DESC
                """
            ).fetchall()
            for row in rows:
                try:
                    payload = json.loads(row['payload_json'])
                except (TypeError, json.JSONDecodeError):
                    continue
                if not isinstance(payload, dict):
                    continue
                roundups = payload.get('roundups') or []
                if not isinstance(roundups, list):
                    continue
                for roundup in roundups:
                    if not isinstance(roundup, dict):
                        continue
                    roundup_total += 1
                    card_asset_path = str(roundup.get('card_asset_path') or '').strip()
                    if card_asset_path and resolve_existing_asset_path(card_asset_path) is not None:
                        roundup_with_local_cards += 1
                    else:
                        roundup_missing_cards += 1
        finally:
            connection.close()
        return roundup_total, roundup_with_local_cards, roundup_missing_cards, archive_posts_total

    def _count_rows_with_local_assets(self, records: list[QueueRecord]) -> int:
        count = 0
        for record in records:
            if self._offer_has_local_asset(record.offer):
                count += 1
        return count

    @staticmethod
    def _offer_has_local_asset(offer: Offer) -> bool:
        references = [offer.assets.hero, offer.assets.header, offer.assets.screenshot, offer.assets.fallback]
        for reference in references:
            if reference and resolve_existing_asset_path(str(reference)) is not None:
                return True
        return False

    @staticmethod
    def _asset_suffix(reference: str) -> str:
        local_path = resolve_existing_asset_path(reference)
        if local_path is not None and local_path.suffix:
            return local_path.suffix.lower()
        parsed = urlparse(reference)
        suffix = Path(unquote(parsed.path)).suffix.lower()
        if suffix in {'.png', '.jpg', '.jpeg', '.webp', '.avif'}:
            return suffix
        return '.img'

    @staticmethod
    def _roundup_json_name(run_key: str | None, json_path: str | None) -> str:
        if json_path:
            return Path(str(json_path)).name
        normalized_run_key = str(run_key or 'snapshot').strip() or 'snapshot'
        return f'{normalized_run_key}_roundup_snapshot_roundups.json'
