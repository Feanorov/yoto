from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from typing import Any

from ...domain.entities import VideoRenderRequest
from ...domain.voice_script_builder import VoiceReadyDraft, VoiceScriptBuilder
from ...infrastructure.ffmpeg_renderer import FFmpegRenderError, FFmpegRenderer
from ...infrastructure.manifest_loader import ManifestLoader
from ...infrastructure.structured_logger import StructuredLogger
from ...domain.scene_planner import ScenePlanner
from ...domain.template_selector import TemplateSelector
from ...infrastructure.asset_resolver import AssetResolver
from ...infrastructure.scene_image_renderer import SceneImageRenderer


@dataclass(slots=True, frozen=True)
class BuildVoiceReadyPackageResult:
    manifest_path: Path
    status: str
    package_dir: Path | None = None
    package_manifest_path: Path | None = None
    review_path: Path | None = None
    scene_plan_path: Path | None = None
    voice_script_path: Path | None = None
    timed_script_path: Path | None = None
    preview_video_path: Path | None = None
    warnings: tuple[str, ...] = ()
    error: str | None = None


class BuildVoiceReadyPackageUseCase:
    PACKAGE_SCHEMA_VERSION = 1

    def __init__(
        self,
        manifest_loader: ManifestLoader,
        asset_resolver: AssetResolver,
        template_selector: TemplateSelector,
        scene_planner: ScenePlanner,
        scene_renderer: SceneImageRenderer,
        ffmpeg_renderer: FFmpegRenderer,
        output_dir: Path,
        logger: StructuredLogger | None = None,
        script_builder: VoiceScriptBuilder | None = None,
    ) -> None:
        self.manifest_loader = manifest_loader
        self.asset_resolver = asset_resolver
        self.template_selector = template_selector
        self.scene_planner = scene_planner
        self.scene_renderer = scene_renderer
        self.ffmpeg_renderer = ffmpeg_renderer
        self.output_dir = output_dir
        self.logger = logger or StructuredLogger('video_voice_ready')
        self.script_builder = script_builder or VoiceScriptBuilder()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def execute(self, manifest_path: Path, *, render_preview_video: bool = True) -> BuildVoiceReadyPackageResult:
        try:
            payload = json.loads(manifest_path.read_text(encoding='utf-8'))
            manifest = self.manifest_loader.load(manifest_path)
            preview_manifest = self._preview_manifest(manifest, payload)
            template = self.template_selector.select(preview_manifest)
            assets = self.asset_resolver.resolve(preview_manifest)
            planned_scenes = self.scene_planner.plan(preview_manifest, template)

            package_dir = self.output_dir / self._package_key(manifest, payload)
            scenes_dir = package_dir / 'scenes'
            preview_dir = package_dir / 'preview'
            scenes_dir.mkdir(parents=True, exist_ok=True)
            preview_dir.mkdir(parents=True, exist_ok=True)

            rendered_scenes = self.scene_renderer.render(
                preview_manifest,
                template,
                assets,
                scenes_dir,
                planned_scenes,
            )
            voice_draft = self.script_builder.build(preview_manifest, payload, planned_scenes, rendered_scenes)

            preview_video_path = preview_dir / 'final_preview.mp4'
            preview_rendered = False
            warning_list = list(assets.warnings) + list(voice_draft.warnings)
            if render_preview_video:
                try:
                    self.ffmpeg_renderer.render(
                        VideoRenderRequest(
                            manifest=preview_manifest,
                            template=template,
                            scenes=rendered_scenes,
                            output_path=preview_video_path,
                            artifact_path=preview_dir / 'preview_render.json',
                        )
                    )
                    preview_rendered = True
                except FFmpegRenderError as exc:
                    preview_video_path.unlink(missing_ok=True)
                    warning_list.append(f'preview_video_skipped:{exc}')
            else:
                preview_video_path.unlink(missing_ok=True)
                warning_list.append('preview_video_skipped:disabled_by_operator')

            scene_plan_payload = {
                'schema_version': self.PACKAGE_SCHEMA_VERSION,
                'family': voice_draft.family,
                'title': voice_draft.title,
                'manifest_path': str(manifest_path),
                'manifest_hash': manifest.manifest_hash,
                'template_name': template.name,
                'scene_count': len(voice_draft.scenes),
                'total_duration_seconds': round(sum(scene.duration_seconds for scene in voice_draft.scenes), 2),
                'scenes': [scene.to_dict() for scene in voice_draft.scenes],
            }
            scene_plan_path = package_dir / 'scene_plan.json'
            self._write_json(scene_plan_path, scene_plan_payload)

            voice_script_path = package_dir / 'voice_script.txt'
            self._write_text(voice_script_path, voice_draft.clean_script)

            timed_script_path = package_dir / 'voice_script_timed.txt'
            self._write_text(timed_script_path, voice_draft.timed_script)

            package_manifest_payload = {
                'schema_version': self.PACKAGE_SCHEMA_VERSION,
                'package_kind': 'voice_ready_video_package',
                'package_id': package_dir.name,
                'family': voice_draft.family,
                'title': voice_draft.title,
                'hook': voice_draft.hook,
                'manifest_path': str(manifest_path),
                'manifest_hash': manifest.manifest_hash,
                'run_key': manifest.run_key,
                'content_type': payload.get('content_type'),
                'template_name': template.name,
                'preview_video_rendered': preview_rendered,
                'warnings': list(dict.fromkeys(warning_list)),
                'files': {
                    'scene_plan': str(scene_plan_path),
                    'voice_script': str(voice_script_path),
                    'voice_script_timed': str(timed_script_path),
                    'review_markdown': str(package_dir / 'review.md'),
                    'scenes_dir': str(scenes_dir),
                    'preview_video': str(preview_video_path) if preview_rendered else None,
                },
            }
            package_manifest_path = package_dir / 'package_manifest.json'
            self._write_json(package_manifest_path, package_manifest_payload)

            review_path = package_dir / 'review.md'
            self._write_text(
                review_path,
                self._review_markdown(
                    manifest_path=manifest_path,
                    template_name=template.name,
                    voice_draft=voice_draft,
                    warning_list=tuple(dict.fromkeys(warning_list)),
                    preview_video_path=preview_video_path if preview_rendered else None,
                ),
            )

            return BuildVoiceReadyPackageResult(
                manifest_path=manifest_path,
                status='packaged',
                package_dir=package_dir,
                package_manifest_path=package_manifest_path,
                review_path=review_path,
                scene_plan_path=scene_plan_path,
                voice_script_path=voice_script_path,
                timed_script_path=timed_script_path,
                preview_video_path=preview_video_path if preview_rendered else None,
                warnings=tuple(dict.fromkeys(warning_list)),
            )
        except Exception as exc:
            self.logger.error('voice_ready_package_failed', manifest_path=manifest_path, error=str(exc))
            return BuildVoiceReadyPackageResult(
                manifest_path=manifest_path,
                status='failed',
                error=str(exc),
            )

    def _preview_manifest(self, manifest, payload: dict[str, Any]):
        local_fallback = self._first_existing_local_path(
            self._payload_path(payload, 'source_artifact', 'image_path'),
            self._payload_path(payload, 'asset_refs', 'card_image'),
        )
        if local_fallback is None:
            return manifest

        asset_refs = dict(manifest.asset_refs)
        changed = False
        for key in ('game_image', 'background'):
            current = asset_refs.get(key)
            if self._is_unusable_local_ref(current):
                asset_refs[key] = str(local_fallback)
                changed = True
        if not changed:
            return manifest
        return replace(manifest, asset_refs=asset_refs)

    @staticmethod
    def _first_existing_local_path(*values: str | None) -> Path | None:
        for value in values:
            if not value:
                continue
            candidate = Path(value)
            if candidate.is_absolute() and candidate.exists() and candidate.is_file():
                return candidate
        return None

    @staticmethod
    def _is_unusable_local_ref(value: str | None) -> bool:
        if not value:
            return True
        lowered = value.lower().strip()
        if lowered.startswith('http://') or lowered.startswith('https://'):
            return True
        candidate = Path(value)
        return not (candidate.is_absolute() and candidate.exists() and candidate.is_file())

    @staticmethod
    def _payload_path(payload: dict[str, Any], section: str, key: str) -> str | None:
        block = payload.get(section) or {}
        if not isinstance(block, dict):
            return None
        value = block.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def _package_key(self, manifest, payload: dict[str, Any]) -> str:
        title = str(payload.get('short_title') or manifest.short_title or manifest.offer_id)
        return f"{manifest.run_key}_{self._slugify(title)}_{manifest.manifest_hash[:10]}"

    @staticmethod
    def _slugify(value: str) -> str:
        slug = re.sub(r'[^a-z0-9]+', '_', value.lower()).strip('_')
        return slug or 'voice_ready'

    def _review_markdown(
        self,
        *,
        manifest_path: Path,
        template_name: str,
        voice_draft: VoiceReadyDraft,
        warning_list: tuple[str, ...],
        preview_video_path: Path | None,
    ) -> str:
        lines = [
            '# Voice-Ready Review',
            '',
            f'- Manifest: `{manifest_path}`',
            f'- Family: `{voice_draft.family}`',
            f'- Title: `{voice_draft.title}`',
            f'- Template: `{template_name}`',
            f'- Hook: {voice_draft.hook}',
            f'- Preview Video: `{preview_video_path}`' if preview_video_path is not None else '- Preview Video: not rendered',
            '',
            '## Warnings',
        ]
        if warning_list:
            lines.extend(f'- {warning}' for warning in warning_list)
        else:
            lines.append('- none')
        lines.extend(
            [
                '',
                '## Scenes',
            ]
        )
        for scene in voice_draft.scenes:
            lines.extend(
                [
                    f"### Scene {scene.position:02d} / {scene.start_seconds:.1f}-{scene.end_seconds:.1f}",
                    f"- Scene ID: `{scene.scene_id}`",
                    f"- Visual Purpose: `{scene.visual_role}`",
                    f"- Visual Source: `{scene.visual_source_role}` -> `{scene.visual_source_path}`",
                    f"- On-Screen: {scene.headline} | {scene.body}" + (f" | {scene.cta}" if scene.cta else ''),
                    f"- Narration: {scene.narration_text}",
                    f"- Transition: {scene.transition_note}",
                ]
            )
        lines.extend(
            [
                '',
                '## Clean Script',
                '',
                voice_draft.clean_script,
                '',
                '## Timed Script',
                '',
                '```text',
                voice_draft.timed_script,
                '```',
                '',
            ]
        )
        return '\n'.join(lines)

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        with NamedTemporaryFile('w', encoding='utf-8', newline='', dir=path.parent, delete=False) as handle:
            temp_path = Path(handle.name)
            handle.write(serialized)
            handle.write('\n')
        temp_path.replace(path)

    @staticmethod
    def _write_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        normalized = content.rstrip() + '\n'
        with NamedTemporaryFile('w', encoding='utf-8', newline='', dir=path.parent, delete=False) as handle:
            temp_path = Path(handle.name)
            handle.write(normalized)
        temp_path.replace(path)
