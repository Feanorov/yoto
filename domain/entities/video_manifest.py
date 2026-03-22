from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class VideoManifest:
    offer_id: str
    run_key: str
    created_at: datetime
    payload_json: dict[str, Any]
    json_path: Path | None = None
