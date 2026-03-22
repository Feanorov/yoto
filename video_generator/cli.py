from __future__ import annotations

import argparse
from pathlib import Path

from .application.use_cases.build_voice_ready_package import BuildVoiceReadyPackageUseCase
from .application.use_cases.run_worker import VideoGeneratorWorker
from .application.use_cases.render_manifest import RenderManifestUseCase
from .domain.scene_planner import ScenePlanner
from .domain.template_selector import TemplateSelector
from .infrastructure.artifact_writer import ArtifactWriter
from .infrastructure.asset_resolver import AssetResolver
from .infrastructure.ffmpeg_renderer import FFmpegRenderer
from .infrastructure.font_loader import FontLoader
from .infrastructure.manifest_loader import ManifestLoader
from .infrastructure.scene_image_renderer import SceneImageRenderer
from .infrastructure.structured_logger import StructuredLogger, configure_logging


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    root_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description='Standalone Iteration 4 short-form video generator')
    parser.add_argument('--manifests-dir', type=Path, default=root_dir / 'output' / 'video_manifests')
    parser.add_argument('--videos-dir', type=Path, default=root_dir / 'output' / 'videos')
    parser.add_argument('--temp-scenes-dir', type=Path, default=root_dir / 'temp' / 'video_scenes')
    parser.add_argument('--voice-ready-output-dir', type=Path, default=root_dir / 'output' / 'video_voice_ready')
    parser.add_argument('--package-manifest', type=Path, default=None, help='Build a voice-ready package for one manifest and exit.')
    parser.add_argument('--skip-preview-video', action='store_true', help='Skip MP4 preview rendering for voice-ready packages.')
    parser.add_argument('--ffmpeg-bin', default='ffmpeg')
    parser.add_argument('--sleep-seconds', type=int, default=30)
    parser.add_argument('--log-level', default='INFO')
    parser.add_argument('--loop', action='store_true', help='Run the safe worker loop continuously')
    return parser.parse_args(argv)


def build_render_use_case(args: argparse.Namespace) -> tuple[RenderManifestUseCase, AssetResolver, TemplateSelector, ScenePlanner, SceneImageRenderer, FFmpegRenderer, StructuredLogger]:
    configure_logging(args.log_level)
    logger = StructuredLogger()
    manifest_loader = ManifestLoader()
    asset_resolver = AssetResolver(logger=logger)
    template_selector = TemplateSelector()
    scene_planner = ScenePlanner()
    font_loader = FontLoader(logger=logger)
    scene_renderer = SceneImageRenderer(asset_resolver=asset_resolver, font_loader=font_loader, logger=logger)
    ffmpeg_renderer = FFmpegRenderer(ffmpeg_bin=args.ffmpeg_bin, logger=logger)
    artifact_writer = ArtifactWriter()
    render_manifest = RenderManifestUseCase(
        manifest_loader=manifest_loader,
        asset_resolver=asset_resolver,
        template_selector=template_selector,
        scene_renderer=scene_renderer,
        ffmpeg_renderer=ffmpeg_renderer,
        artifact_writer=artifact_writer,
        videos_dir=args.videos_dir,
        temp_scenes_dir=args.temp_scenes_dir,
        logger=logger,
        scene_planner=scene_planner,
    )
    return render_manifest, asset_resolver, template_selector, scene_planner, scene_renderer, ffmpeg_renderer, logger


def build_worker(args: argparse.Namespace) -> VideoGeneratorWorker:
    render_manifest, _, _, _, _, _, logger = build_render_use_case(args)
    return VideoGeneratorWorker(
        manifests_dir=args.manifests_dir,
        render_manifest=render_manifest,
        sleep_seconds=args.sleep_seconds,
        logger=logger,
    )


def build_voice_ready_use_case(args: argparse.Namespace) -> BuildVoiceReadyPackageUseCase:
    _, asset_resolver, template_selector, scene_planner, scene_renderer, ffmpeg_renderer, logger = build_render_use_case(args)
    return BuildVoiceReadyPackageUseCase(
        manifest_loader=ManifestLoader(),
        asset_resolver=asset_resolver,
        template_selector=template_selector,
        scene_planner=scene_planner,
        scene_renderer=scene_renderer,
        ffmpeg_renderer=ffmpeg_renderer,
        output_dir=args.voice_ready_output_dir,
        logger=logger,
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.package_manifest is not None:
        use_case = build_voice_ready_use_case(args)
        result = use_case.execute(args.package_manifest, render_preview_video=not args.skip_preview_video)
        if result.status != 'packaged':
            print(f'failed {result.manifest_path} :: {result.error}')
            return 1
        print(
            'packaged='
            f'{result.package_dir} '
            f'preview_video={result.preview_video_path or "none"} '
            f'warnings={len(result.warnings)}'
        )
        return 0

    worker = build_worker(args)
    if args.loop:
        worker.run_forever()
        return 0
    summary = worker.process_once()
    for result in summary.results or []:
        if result.status == 'failed':
            print(f'failed {result.manifest_path} :: {result.error}')
    print(f'processed={summary.processed} rendered={summary.rendered} skipped={summary.skipped} failed={summary.failed}')
    return 1 if summary.failed else 0
