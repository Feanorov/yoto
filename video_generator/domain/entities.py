from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True, frozen=True)
class VideoManifest:
    manifest_version: int
    run_key: str
    created_at: datetime
    offer_id: str
    short_title: str
    hook_line: str
    summary_line: str
    urgency_line: str
    asset_refs: dict[str, str]
    template_hint: str
    context: dict[str, Any]
    source_path: Path
    manifest_hash: str


@dataclass(slots=True, frozen=True)
class VideoTemplate:
    name: str
    background_top: tuple[int, int, int]
    background_bottom: tuple[int, int, int]
    accent: tuple[int, int, int]
    panel: tuple[int, int, int, int]
    badge: tuple[int, int, int]
    cta: tuple[int, int, int]


@dataclass(slots=True, frozen=True)
class PlannedScene:
    scene_id: str
    position: int
    duration_seconds: float
    headline: str
    body: str
    cta: str | None
    voiceover_text: str
    visual_role: str


@dataclass(slots=True, frozen=True)
class RenderedScene:
    scene_id: str
    position: int
    duration_seconds: float
    overlay_text: str
    voiceover_text: str
    image_path: Path
    asset_path: Path | None


@dataclass(slots=True, frozen=True)
class VideoRenderRequest:
    manifest: VideoManifest
    template: VideoTemplate
    scenes: tuple[RenderedScene, ...]
    output_path: Path
    artifact_path: Path


@dataclass(slots=True, frozen=True)
class RenderArtifact:
    manifest_path: Path
    manifest_hash: str
    video_path: Path
    artifact_path: Path
    scene_paths: tuple[Path, ...]
    template_name: str
    created_at: datetime
    status: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            'schema_version': 1,
            'manifest_path': str(self.manifest_path),
            'manifest_hash': self.manifest_hash,
            'video_path': str(self.video_path),
            'artifact_path': str(self.artifact_path),
            'scene_paths': [str(path) for path in self.scene_paths],
            'template_name': self.template_name,
            'created_at': self.created_at.isoformat(),
            'status': self.status,
            'details': self.details,
        }
