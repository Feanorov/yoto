from __future__ import annotations

from csv import DictWriter
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from typing import Any

from domain.entities.analytics_artifact import AnalyticsArtifact


class AnalyticsArtifactWriter:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write(self, artifact: AnalyticsArtifact) -> tuple[Path | None, Path | None]:
        base_name = self._base_name(artifact)
        json_path = self.output_dir / f'{base_name}.json'
        csv_path = self.output_dir / f'{base_name}.csv'
        self._write_json(json_path, artifact.payload_json)
        self._write_csv(csv_path, artifact.summary_rows)
        return json_path, csv_path

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        self._atomic_write(path, serialized)

    def _write_csv(self, path: Path, rows: list[dict[str, Any]]) -> None:
        normalized_rows = [self._normalize_row(row) for row in rows]
        fieldnames = sorted({key for row in normalized_rows for key in row.keys()})
        with NamedTemporaryFile('w', encoding='utf-8', newline='', dir=path.parent, delete=False) as handle:
            temp_path = Path(handle.name)
            writer = DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in normalized_rows:
                writer.writerow({name: row.get(name, '') for name in fieldnames})
        temp_path.replace(path)

    def _atomic_write(self, path: Path, content: str) -> None:
        with NamedTemporaryFile('w', encoding='utf-8', newline='', dir=path.parent, delete=False) as handle:
            temp_path = Path(handle.name)
            handle.write(content)
        temp_path.replace(path)

    def _base_name(self, artifact: AnalyticsArtifact) -> str:
        subject = re.sub(r'[^a-zA-Z0-9._-]+', '_', artifact.subject_id).strip('_') or 'run'
        return f'{artifact.run_key}_{artifact.artifact_type}_{subject}'

    @staticmethod
    def _normalize_row(row: dict[str, Any]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for key, value in row.items():
            if value is None:
                normalized[key] = ''
            elif isinstance(value, (dict, list, tuple)):
                normalized[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)
            else:
                normalized[key] = str(value)
        return normalized
