from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class AnalyticsArtifact:
    artifact_type: str
    subject_id: str
    run_key: str
    created_at: datetime
    payload_json: dict[str, Any]
    summary_rows: list[dict[str, Any]] = field(default_factory=list)
    json_path: Path | None = None
    csv_path: Path | None = None
