from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from ..domain.entities import RenderArtifact


class ArtifactWriter:
    def write(self, artifact: RenderArtifact) -> Path:
        artifact.artifact_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(artifact.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        with NamedTemporaryFile('w', encoding='utf-8', newline='', dir=artifact.artifact_path.parent, delete=False) as handle:
            temp_path = Path(handle.name)
            handle.write(serialized)
            handle.write('\n')
        temp_path.replace(artifact.artifact_path)
        return artifact.artifact_path
