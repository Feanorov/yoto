from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import shutil

from ...domain.entities import RenderArtifact, VideoRenderRequest
from ...domain.scene_planner import ScenePlanner
from ...domain.template_selector import TemplateSelector
from ...infrastructure.artifact_writer import ArtifactWriter
from ...infrastructure.asset_resolver import AssetResolver
from ...infrastructure.ffmpeg_renderer import FFmpegRenderer
from ...infrastructure.manifest_loader import ManifestLoader
from ...infrastructure.scene_image_renderer import SceneImageRenderer
from ...infrastructure.structured_logger import StructuredLogger


@dataclass(slots=True, frozen=True)
class RenderManifestResult:
    manifest_path: Path
    status: str
    video_path: Path | None = None
    artifact_path: Path | None = None
    error: str | None = None


class RenderManifestUseCase:
    def __init__(
        self,
        manifest_loader: ManifestLoader,
        asset_resolver: AssetResolver,
        template_selector: TemplateSelector,
        scene_renderer: SceneImageRenderer,
        ffmpeg_renderer: FFmpegRenderer,
        artifact_writer: ArtifactWriter,
        videos_dir: Path,
        temp_scenes_dir: Path,
        logger: StructuredLogger | None = None,
        scene_planner: ScenePlanner | None = None,
    ) -> None:
        self.manifest_loader = manifest_loader
        self.asset_resolver = asset_resolver
        self.template_selector = template_selector
        self.scene_planner = scene_planner or ScenePlanner()
        self.scene_renderer = scene_renderer
        self.ffmpeg_renderer = ffmpeg_renderer
        self.artifact_writer = artifact_writer
        self.videos_dir = videos_dir
        self.temp_scenes_dir = temp_scenes_dir
        self.logger = logger or StructuredLogger()
        self.videos_dir.mkdir(parents=True, exist_ok=True)
        self.temp_scenes_dir.mkdir(parents=True, exist_ok=True)

    def execute(self, manifest_path: Path) -> RenderManifestResult:
        temp_dir: Path | None = None
        try:
            manifest = self.manifest_loader.load(manifest_path)
            self.logger.info('manifest loaded', manifest_path=manifest_path, manifest_hash=manifest.manifest_hash)
            self.logger.info('manifest validated', manifest_path=manifest_path, manifest_hash=manifest.manifest_hash)

            video_path = self.videos_dir / f'video_{manifest.manifest_hash}.mp4'
            artifact_path = self.videos_dir / f'video_{manifest.manifest_hash}.json'
            if video_path.exists():
                self.logger.info('already rendered', manifest_path=manifest_path, video_path=video_path)
                return RenderManifestResult(
                    manifest_path=manifest_path,
                    status='already_rendered',
                    video_path=video_path,
                    artifact_path=artifact_path if artifact_path.exists() else None,
                )

            assets = self.asset_resolver.resolve(manifest)
            self.logger.info('assets resolved', manifest_path=manifest_path, warnings=list(assets.warnings))

            template = self.template_selector.select(manifest)
            self.logger.info('template selected', manifest_path=manifest_path, template=template.name)

            planned_scenes = self.scene_planner.plan(manifest, template)
            self.logger.info(
                'scenes planned',
                manifest_path=manifest_path,
                scene_count=len(planned_scenes),
                scene_ids=[scene.scene_id for scene in planned_scenes],
            )

            temp_dir = self.temp_scenes_dir / manifest.manifest_hash
            scenes = self.scene_renderer.render(manifest, template, assets, temp_dir, planned_scenes)
            self.logger.info('scenes generated', manifest_path=manifest_path, scene_count=len(scenes), temp_dir=temp_dir)

            request = VideoRenderRequest(
                manifest=manifest,
                template=template,
                scenes=scenes,
                output_path=video_path,
                artifact_path=artifact_path,
            )
            self.ffmpeg_renderer.render(request)

            artifact = RenderArtifact(
                manifest_path=manifest_path,
                manifest_hash=manifest.manifest_hash,
                video_path=video_path,
                artifact_path=artifact_path,
                scene_paths=tuple(scene.image_path for scene in scenes),
                template_name=template.name,
                created_at=datetime.utcnow(),
                status='rendered',
                details={
                    'scene_count': len(scenes),
                    'scene_ids': [scene.scene_id for scene in scenes],
                    'durations_seconds': [scene.duration_seconds for scene in scenes],
                    'warnings': list(assets.warnings),
                    'output_filename': video_path.name,
                },
            )
            self.artifact_writer.write(artifact)
            return RenderManifestResult(
                manifest_path=manifest_path,
                status='rendered',
                video_path=video_path,
                artifact_path=artifact_path,
            )
        except Exception as exc:
            self.logger.error('render failed', manifest_path=manifest_path, error=str(exc))
            return RenderManifestResult(
                manifest_path=manifest_path,
                status='failed',
                error=str(exc),
            )
        finally:
            if temp_dir is not None and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
