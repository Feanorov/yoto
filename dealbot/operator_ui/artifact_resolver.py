from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import ArtifactBundle, PreviewFingerprint


class PreviewArtifactResolver:
    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root).resolve()
        self.output_dir = self.project_root / "output"
        self.analytics_dir = self.output_dir / "analytics"

    def load_latest_local_state(self) -> ArtifactBundle:
        workflow_path = self._find_newest(
            self.analytics_dir,
            ("*_operator_workflow_preview.json", "*_operator_workflow_preview-selected.json"),
        )
        warnings: list[str] = []
        if workflow_path is None:
            warnings.append("No preview workflow artifact exists yet.")
        return self._build_bundle(workflow_path=workflow_path, warnings=warnings)

    def load_preview_run(self, started_at: float) -> ArtifactBundle:
        workflow_candidates = self._find_since_many(
            self.analytics_dir,
            ("*_operator_workflow_preview.json", "*_operator_workflow_preview-selected.json"),
            started_at,
        )
        truth_candidates = self._find_since(self.analytics_dir, "*_operator_truth_report_preview.json", started_at)
        warnings: list[str] = []
        ambiguous = len(workflow_candidates) > 1 or (not workflow_candidates and len(truth_candidates) > 1)
        if ambiguous:
            warnings.append("Preview artifacts are ambiguous; multiple preview artifacts were created.")
        workflow_path = max(workflow_candidates, key=self._sort_key) if workflow_candidates else None
        truth_report_path = max(truth_candidates, key=self._sort_key) if truth_candidates else None
        current_run_missing_artifact = workflow_path is None and truth_report_path is None
        stale = False
        if current_run_missing_artifact:
            latest_preview_artifact = self._find_newest(
                self.analytics_dir,
                (
                    "*_operator_workflow_preview.json",
                    "*_operator_workflow_preview-selected.json",
                    "*_operator_truth_report_preview.json",
                ),
            )
            stale = latest_preview_artifact is not None and self._sort_key(latest_preview_artifact)[0] < started_at
            warnings.append("No new preview workflow or truth artifact was created after the current run.")
        return self._build_bundle(
            workflow_path=workflow_path,
            truth_report_path=truth_report_path,
            ambiguous=ambiguous,
            stale=stale,
            current_run_missing_artifact=current_run_missing_artifact,
            allow_latest_truth_fallback=not current_run_missing_artifact,
            warnings=warnings,
        )

    def reload_bound_state(self, fingerprint: PreviewFingerprint | None) -> ArtifactBundle:
        if fingerprint is None or fingerprint.workflow_path is None:
            return self.load_latest_local_state()
        workflow_path = fingerprint.workflow_path if fingerprint.workflow_path.exists() else None
        truth_report_path = fingerprint.truth_report_path if fingerprint.truth_report_path and fingerprint.truth_report_path.exists() else None
        warnings: list[str] = []
        if workflow_path is None:
            warnings.append("The bound preview workflow artifact is missing; showing the latest known preview instead.")
            return self.load_latest_local_state()
        stale = self.is_preview_stale(fingerprint)
        if stale:
            warnings.append("Preview artifacts are stale; a newer preview workflow artifact exists on disk.")
        return self._build_bundle(
            workflow_path=workflow_path,
            truth_report_path=truth_report_path,
            stale=stale,
            warnings=warnings,
        )

    def load_publish_previewed_workflow(
        self,
        *,
        started_at: float,
        source_report_path: Path | None = None,
    ) -> tuple[Path | None, dict[str, Any] | None]:
        candidates = self._find_since(self.analytics_dir, "*_operator_workflow_publish-previewed.json", started_at)
        if not candidates:
            return None, None
        if source_report_path is not None:
            expected_report_path = str(source_report_path.resolve())
            matching: list[tuple[Path, dict[str, Any]]] = []
            for path in candidates:
                payload = self._load_json(path)
                if payload is None:
                    continue
                actual_report_path = str(payload.get("source_report_path") or "").strip()
                if actual_report_path == expected_report_path:
                    matching.append((path, payload))
            if matching:
                workflow_path, payload = max(matching, key=lambda item: self._sort_key(item[0]))
                return workflow_path, payload
        workflow_path = max(candidates, key=self._sort_key)
        return workflow_path, self._load_json(workflow_path)

    def is_preview_stale(self, fingerprint: PreviewFingerprint | None) -> bool:
        if fingerprint is None or fingerprint.workflow_path is None:
            return False
        latest_workflow = self._find_newest(
            self.analytics_dir,
            ("*_operator_workflow_preview.json", "*_operator_workflow_preview-selected.json"),
        )
        if latest_workflow is None:
            return False
        if fingerprint.workflow_path.resolve() == latest_workflow.resolve():
            return False
        return self._sort_key(latest_workflow) > self._sort_key(fingerprint.workflow_path)

    def _build_bundle(
        self,
        *,
        workflow_path: Path | None,
        truth_report_path: Path | None = None,
        ambiguous: bool = False,
        stale: bool = False,
        reused_latest_preview: bool = False,
        current_run_missing_artifact: bool = False,
        allow_latest_truth_fallback: bool = True,
        warnings: list[str] | None = None,
    ) -> ArtifactBundle:
        workflow_payload = self._load_json(workflow_path)
        resolved_truth_report = truth_report_path
        if resolved_truth_report is None and workflow_payload:
            resolved_truth_report = self._resolve_truth_report_path(workflow_payload)
        if resolved_truth_report is None and allow_latest_truth_fallback:
            resolved_truth_report = self._find_newest(self.analytics_dir, ("*_operator_truth_report_preview.json",))
        truth_payload = self._load_json(resolved_truth_report)
        publish_history_records = self._load_publish_history(limit=5)
        latest_snapshot_manifest_path = self._find_newest(
            self.output_dir / "offline_validation" / "snapshots",
            ("snapshot_manifest.json",),
        )
        latest_publish_workflow_path = None
        latest_publish_workflow_payload = None
        latest_publish_outcome_path = None
        latest_publish_outcome_payload = None
        if publish_history_records:
            latest_record = publish_history_records[0]
            latest_publish_workflow_path = latest_record.get("workflow_path")
            latest_publish_workflow_payload = latest_record.get("workflow_payload")
            latest_publish_outcome_path = latest_record.get("publish_outcome_path")
            latest_publish_outcome_payload = latest_record.get("publish_outcome_payload")
        return ArtifactBundle(
            project_root=self.project_root,
            output_dir=self.output_dir,
            workflow_path=workflow_path,
            truth_report_path=resolved_truth_report,
            workflow_payload=workflow_payload,
            truth_payload=truth_payload,
            latest_snapshot_manifest_path=latest_snapshot_manifest_path,
            latest_publish_outcome_path=latest_publish_outcome_path,
            latest_publish_workflow_path=latest_publish_workflow_path,
            latest_publish_workflow_payload=latest_publish_workflow_payload,
            latest_publish_outcome_payload=latest_publish_outcome_payload,
            publish_history_records=publish_history_records,
            ambiguous=ambiguous,
            stale=stale,
            reused_latest_preview=reused_latest_preview,
            current_run_missing_artifact=current_run_missing_artifact,
            warnings=list(warnings or ()),
        )

    def _resolve_truth_report_path(self, workflow_payload: dict[str, Any]) -> Path | None:
        report_path_raw = str(workflow_payload.get("report_path") or "").strip()
        if not report_path_raw:
            return None
        report_path = Path(report_path_raw)
        if not report_path.is_absolute():
            report_path = self.project_root / report_path
        return report_path if report_path.exists() else None

    def _resolve_publish_outcome_path(self, workflow_payload: dict[str, Any] | None) -> Path | None:
        payload = dict(workflow_payload or {})
        outcome_path_raw = str(payload.get("publish_outcome_path") or "").strip()
        if not outcome_path_raw:
            return None
        outcome_path = Path(outcome_path_raw)
        if not outcome_path.is_absolute():
            outcome_path = self.project_root / outcome_path
        return outcome_path if outcome_path.exists() else None

    def _load_json(self, path: Path | None) -> dict[str, Any] | None:
        if path is None or not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _load_publish_history(self, *, limit: int) -> list[dict[str, Any]]:
        if not self.analytics_dir.exists():
            return []
        workflow_paths = [
            path
            for path in self.analytics_dir.rglob("*_operator_workflow_publish-previewed.json")
            if path.is_file()
        ]
        workflow_paths.sort(key=self._sort_key, reverse=True)
        records: list[dict[str, Any]] = []
        for workflow_path in workflow_paths[:limit]:
            workflow_payload = self._load_json(workflow_path)
            if workflow_payload is None:
                continue
            publish_outcome_path = self._resolve_publish_outcome_path(workflow_payload)
            records.append(
                {
                    "workflow_path": workflow_path,
                    "workflow_payload": workflow_payload,
                    "publish_outcome_path": publish_outcome_path,
                    "publish_outcome_payload": self._load_json(publish_outcome_path),
                }
            )
        return records

    def _find_since(self, base_dir: Path, pattern: str, started_at: float) -> list[Path]:
        if not base_dir.exists():
            return []
        return [
            path
            for path in base_dir.rglob(pattern)
            if path.is_file() and path.stat().st_mtime >= started_at
        ]

    def _find_since_many(self, base_dir: Path, patterns: tuple[str, ...], started_at: float) -> list[Path]:
        candidates: list[Path] = []
        for pattern in patterns:
            candidates.extend(self._find_since(base_dir, pattern, started_at))
        return candidates

    def _find_newest(self, base_dir: Path, patterns: tuple[str, ...]) -> Path | None:
        if not base_dir.exists():
            return None
        candidates: list[Path] = []
        for pattern in patterns:
            candidates.extend(path for path in base_dir.rglob(pattern) if path.is_file())
        if not candidates:
            return None
        return max(candidates, key=self._sort_key)

    @staticmethod
    def _sort_key(path: Path) -> tuple[float, str]:
        return (path.stat().st_mtime, str(path))
