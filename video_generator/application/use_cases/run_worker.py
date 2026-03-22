from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time

from .render_manifest import RenderManifestResult, RenderManifestUseCase
from ...infrastructure.structured_logger import StructuredLogger


@dataclass(slots=True)
class WorkerCycleResult:
    processed: int = 0
    rendered: int = 0
    skipped: int = 0
    failed: int = 0
    results: list[RenderManifestResult] | None = None

    def __post_init__(self) -> None:
        if self.results is None:
            self.results = []


class VideoGeneratorWorker:
    def __init__(
        self,
        manifests_dir: Path,
        render_manifest: RenderManifestUseCase,
        sleep_seconds: int = 30,
        logger: StructuredLogger | None = None,
    ) -> None:
        self.manifests_dir = manifests_dir
        self.manifests_dir.mkdir(parents=True, exist_ok=True)
        self.render_manifest = render_manifest
        self.sleep_seconds = sleep_seconds
        self.logger = logger or StructuredLogger()
        self._failed_signatures: dict[Path, tuple[int, int]] = {}

    def process_once(self) -> WorkerCycleResult:
        summary = WorkerCycleResult()
        for manifest_path in self._discover_manifests():
            signature = self._signature(manifest_path)
            if self._failed_signatures.get(manifest_path) == signature:
                self.logger.warning('corrupted manifest skipped', manifest_path=manifest_path)
                continue

            result = self.render_manifest.execute(manifest_path)
            summary.processed += 1
            summary.results.append(result)
            if result.status == 'rendered':
                summary.rendered += 1
                self._failed_signatures.pop(manifest_path, None)
            elif result.status == 'already_rendered':
                summary.skipped += 1
                self._failed_signatures.pop(manifest_path, None)
            else:
                summary.failed += 1
                self._failed_signatures[manifest_path] = signature
        return summary

    def run_forever(self) -> None:
        while True:
            self.process_once()
            time.sleep(self.sleep_seconds)

    def _discover_manifests(self) -> list[Path]:
        dedicated = sorted(path for path in self.manifests_dir.glob('*_video_manifest_*.json') if path.is_file())
        if dedicated:
            return dedicated
        return sorted(path for path in self.manifests_dir.glob('*.json') if path.is_file())

    @staticmethod
    def _signature(path: Path) -> tuple[int, int]:
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size
