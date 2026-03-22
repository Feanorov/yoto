from __future__ import annotations

import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile

from domain.entities.video_manifest import VideoManifest


class VideoManifestWriter:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write(self, manifest: VideoManifest) -> Path:
        path = self.output_dir / f'{self._base_name(manifest)}.json'
        serialized = json.dumps(manifest.payload_json, ensure_ascii=False, indent=2, sort_keys=True)
        with NamedTemporaryFile('w', encoding='utf-8', newline='', dir=path.parent, delete=False) as handle:
            temp_path = Path(handle.name)
            handle.write(serialized)
        temp_path.replace(path)
        return path

    def _base_name(self, manifest: VideoManifest) -> str:
        offer_id = re.sub(r'[^a-zA-Z0-9._-]+', '_', manifest.offer_id).strip('_') or 'offer'
        return f'{manifest.run_key}_video_manifest_{offer_id}'
