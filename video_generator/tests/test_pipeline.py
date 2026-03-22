from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

from PIL import Image

from video_generator.application.use_cases.render_manifest import RenderManifestUseCase
from video_generator.application.use_cases.run_worker import VideoGeneratorWorker
from video_generator.domain.scene_planner import ScenePlanner
from video_generator.domain.template_selector import TemplateSelector
from video_generator.infrastructure.artifact_writer import ArtifactWriter
from video_generator.infrastructure.asset_resolver import AssetResolver
from video_generator.infrastructure.font_loader import FontLoader
from video_generator.infrastructure.manifest_loader import ManifestLoader
from video_generator.infrastructure.scene_image_renderer import SceneImageRenderer
from video_generator.infrastructure.structured_logger import StructuredLogger


class StubFFmpegRenderer:
    def __init__(self) -> None:
        self.calls = 0

    def render(self, request) -> None:
        self.calls += 1
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        request.output_path.write_bytes(b'mp4')


class CapturingLogger(StructuredLogger):
    def __init__(self) -> None:
        self.warning_events: list[tuple[str, dict[str, object]]] = []

    def info(self, event: str, **fields) -> None:
        return

    def warning(self, event: str, **fields) -> None:
        self.warning_events.append((event, fields))

    def error(self, event: str, **fields) -> None:
        self.warning_events.append((f'error:{event}', fields))


def make_manifest(tmp_path: Path) -> Path:
    game_image = tmp_path / 'game.png'
    background = tmp_path / 'background.png'
    Image.new('RGB', (720, 920), (140, 80, 90)).save(game_image)
    Image.new('RGB', (800, 800), (30, 40, 60)).save(background)
    manifest_path = tmp_path / '20260310T120000Z_video_manifest_steam_42.json'
    manifest_path.write_text(
        json.dumps(
            {
                'manifest_version': 1,
                'run_key': '20260310T120000Z',
                'created_at': '2026-03-10T12:00:00',
                'offer_id': 'steam:42',
                'short_title': "Sid Meier's Civilization VI Anthology Edition",
                'hook_line': 'Знижка вже активна.',
                'summary_line': 'Тактична стратегія зі сильним дисконтом.',
                'urgency_line': 'До завершення акції залишилось небагато часу.',
                'asset_refs': {
                    'game_image': str(game_image),
                    'background': str(background),
                },
                'template_hint': 'deadline-push',
                'context': {
                    'store': 'Steam',
                    'offer_kind': 'discount',
                    'lane': 'final_push',
                },
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )
    return manifest_path


def make_roundup_manifest(tmp_path: Path, roundup_items: list[dict] | None = None) -> Path:
    game_image = tmp_path / 'roundup.png'
    Image.new('RGB', (900, 900), (90, 70, 40)).save(game_image)
    manifest_path = tmp_path / '20260310T120500Z_video_manifest_roundup_digest.json'
    manifest_path.write_text(
        json.dumps(
            {
                'manifest_version': 2,
                'run_key': '20260310T120500Z',
                'created_at': '2026-03-10T12:05:00',
                'offer_id': 'roundup:reserve_digest',
                'short_title': 'Roundup: Reserve Digest',
                'hook_line': 'Йото витягнув ще кілька сильних пропозицій.',
                'summary_line': 'Ще кілька пропозицій з резерву поточного вікна.',
                'urgency_line': 'Переглянь добірку, поки ці пропозиції ще активні.',
                'asset_refs': {
                    'game_image': str(game_image),
                    'background': str(game_image),
                    'card_image': str(game_image),
                },
                'template_hint': 'deal-spotlight',
                'context': {
                    'store': 'Steam',
                    'offer_kind': 'discount',
                    'lane': 'roundup_digest',
                    'template_id': 'roundup_digest',
                    'video_template_intent': 'roundup_digest',
                },
                'roundup_items': roundup_items
                or [
                    {'title': 'Roundup One', 'discount_percent': 80},
                    {'title': 'Roundup Two', 'discount_percent': 70},
                    {'title': 'Roundup Three', 'discount_percent': 65},
                    {'title': 'Roundup Four', 'discount_percent': 55},
                ],
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )
    return manifest_path


def build_use_case(tmp_path: Path, ffmpeg_renderer: StubFFmpegRenderer, font_loader: FontLoader | None = None) -> RenderManifestUseCase:
    logger = StructuredLogger('video_generator_test')
    asset_resolver = AssetResolver(logger=logger)
    active_font_loader = font_loader or FontLoader(logger=logger)
    return RenderManifestUseCase(
        manifest_loader=ManifestLoader(),
        asset_resolver=asset_resolver,
        template_selector=TemplateSelector(),
        scene_renderer=SceneImageRenderer(
            asset_resolver=asset_resolver,
            font_loader=active_font_loader,
            logger=logger,
        ),
        ffmpeg_renderer=ffmpeg_renderer,
        artifact_writer=ArtifactWriter(),
        videos_dir=tmp_path / 'videos',
        temp_scenes_dir=tmp_path / 'temp' / 'video_scenes',
        logger=logger,
    )


def render_scenes(tmp_path: Path, manifest):
    logger = CapturingLogger()
    asset_resolver = AssetResolver(assets_dir=tmp_path / 'renderer-assets', logger=logger)
    renderer = SceneImageRenderer(
        asset_resolver=asset_resolver,
        font_loader=FontLoader(logger=logger),
        logger=logger,
    )
    assets = asset_resolver.resolve(manifest)
    template = TemplateSelector().select(manifest)
    planned_scenes = ScenePlanner().plan(manifest, template)
    scenes = renderer.render(
        manifest,
        template,
        assets,
        tmp_path / 'temp' / 'direct-scenes' / manifest.manifest_hash,
        planned_scenes,
    )
    return scenes, logger


def test_render_manifest_creates_video_artifact_and_cleans_temp_scenes(tmp_path: Path) -> None:
    manifest_path = make_manifest(tmp_path)
    ffmpeg_renderer = StubFFmpegRenderer()
    font_loader = FontLoader(logger=StructuredLogger('font_loader_test'))
    assert font_loader.resolve_font_path('headline') is not None
    use_case = build_use_case(tmp_path, ffmpeg_renderer, font_loader=font_loader)
    manifest = ManifestLoader().load(manifest_path)

    result = use_case.execute(manifest_path)

    assert result.status == 'rendered'
    assert result.video_path is not None and result.video_path.exists()
    assert result.artifact_path is not None and result.artifact_path.exists()
    assert ffmpeg_renderer.calls == 1
    assert not (tmp_path / 'temp' / 'video_scenes' / manifest.manifest_hash).exists()

    artifact = json.loads(result.artifact_path.read_text(encoding='utf-8'))
    assert artifact['details']['scene_count'] == 3
    assert artifact['details']['scene_ids'] == ['hook', 'summary', 'urgency']
    assert artifact['template_name'] == 'deadline_push'


def test_long_ukrainian_headlines_fit_without_headline_truncation(tmp_path: Path) -> None:
    manifest = ManifestLoader().load(make_manifest(tmp_path))
    manifest = replace(
        manifest,
        short_title='Дуже довга назва для перевірки переносу у вертикальному відео',
        summary_line='Стислий опис для перевірки переносу без зайвого обрізання.',
        urgency_line='До завершення пропозиції залишилось небагато часу прямо зараз',
    )

    scenes, logger = render_scenes(tmp_path, manifest)
    truncation_fields = {
        (fields.get('scene_id'), fields.get('field'))
        for event, fields in logger.warning_events
        if event == 'text truncated'
    }

    assert len(scenes) == 3
    assert ('hook', 'headline') not in truncation_fields
    assert ('summary', 'headline') not in truncation_fields
    assert ('urgency', 'headline') not in truncation_fields


def test_urgency_cta_truncates_less_aggressively_for_event_scene(tmp_path: Path) -> None:
    manifest = ManifestLoader().load(make_manifest(tmp_path))
    manifest = replace(
        manifest,
        template_hint='event-countdown',
        urgency_line='До завершення пропозиції залишилось небагато часу прямо зараз',
        context={
            **manifest.context,
            'offer_kind': 'event',
            'lane': 'final_push',
        },
    )

    scenes, logger = render_scenes(tmp_path, manifest)
    truncation_fields = {
        (fields.get('scene_id'), fields.get('field'))
        for event, fields in logger.warning_events
        if event == 'text truncated'
    }

    assert len(scenes) == 3
    assert ('urgency', 'cta') not in truncation_fields


def test_scene_planner_support_strings_are_clean_ukrainian(tmp_path: Path) -> None:
    manifest_path = make_manifest(tmp_path)
    manifest = ManifestLoader().load(manifest_path)

    assert ScenePlanner._call_to_action(manifest) == 'Перевір знижку зараз до завершення акції.'
    assert ScenePlanner._supporting_line(manifest) == 'Steam - Знижка'


def test_smoke_manifest_path_remains_compatible(tmp_path: Path) -> None:
    smoke_manifest = Path(__file__).resolve().parents[1] / 'smoke_test' / 'manifests' / '20260311T003000Z_video_manifest_smoke_test.json'
    ffmpeg_renderer = StubFFmpegRenderer()
    use_case = build_use_case(tmp_path, ffmpeg_renderer)

    result = use_case.execute(smoke_manifest)

    assert result.status == 'rendered'
    assert result.video_path is not None and result.video_path.exists()
    assert ffmpeg_renderer.calls == 1


def test_worker_skips_already_rendered_output_on_second_pass(tmp_path: Path) -> None:
    manifest_path = make_manifest(tmp_path)
    ffmpeg_renderer = StubFFmpegRenderer()
    use_case = build_use_case(tmp_path, ffmpeg_renderer)
    worker = VideoGeneratorWorker(
        manifests_dir=manifest_path.parent,
        render_manifest=use_case,
        sleep_seconds=1,
        logger=StructuredLogger('video_generator_worker_test'),
    )

    first = worker.process_once()
    second = worker.process_once()

    assert first.rendered == 1
    assert second.skipped == 1
    assert ffmpeg_renderer.calls == 1


def test_manifest_loader_accepts_v2_payload_without_worker_changes(tmp_path: Path) -> None:
    manifest_path = make_manifest(tmp_path)
    payload = json.loads(manifest_path.read_text(encoding='utf-8'))
    payload.update(
        {
            'manifest_version': 2,
            'content_id': 'offer-video-key',
            'content_type': 'discount',
            'cta_line': 'Перевір пропозицію зараз.',
            'caption_html': '<b>caption</b>',
            'hashtags': ['#steam'],
            'render_diagnostics': {'renderer_selected': 'yoto_v4'},
            'caption_debug': {'voice_mode': 'direct'},
            'source_artifact': {
                'image_path': payload['asset_refs']['game_image'],
                'assets_used': [payload['asset_refs']['game_image']],
            },
        }
    )
    payload['asset_refs']['card_image'] = payload['asset_refs']['game_image']
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')

    manifest = ManifestLoader().load(manifest_path)
    ffmpeg_renderer = StubFFmpegRenderer()
    use_case = build_use_case(tmp_path, ffmpeg_renderer)
    result = use_case.execute(manifest_path)

    assert manifest.manifest_version == 2
    assert result.status == 'rendered'
    assert ffmpeg_renderer.calls == 1


def test_render_manifest_renders_roundup_digest_with_four_scenes(tmp_path: Path) -> None:
    manifest_path = make_roundup_manifest(tmp_path)
    ffmpeg_renderer = StubFFmpegRenderer()
    use_case = build_use_case(tmp_path, ffmpeg_renderer)

    result = use_case.execute(manifest_path)

    assert result.status == 'rendered'
    assert result.artifact_path is not None and result.artifact_path.exists()
    artifact = json.loads(result.artifact_path.read_text(encoding='utf-8'))
    assert artifact['template_name'] == 'roundup_digest'
    assert artifact['details']['scene_count'] == 4
    assert artifact['details']['scene_ids'] == ['hook', 'roundup_page_one', 'roundup_page_two', 'urgency']


def test_roundup_page_two_avoids_body_truncation_for_wide_titles(tmp_path: Path) -> None:
    manifest = ManifestLoader().load(
        make_roundup_manifest(
            tmp_path,
            roundup_items=[
                {'title': 'Battlefield V', 'discount_percent': 95},
                {'title': 'A Way Out', 'discount_percent': 90},
                {'title': 'Battlefield 2042', 'discount_percent': 95},
                {'title': 'STAR WARS Jedi: Survivor', 'discount_percent': 90},
            ],
        )
    )

    scenes, logger = render_scenes(tmp_path, manifest)
    truncation_fields = {
        (fields.get('scene_id'), fields.get('field'))
        for event, fields in logger.warning_events
        if event == 'text truncated'
    }

    assert len(scenes) == 4
    assert ('roundup_page_two', 'body') not in truncation_fields




def make_event_manifest_with_small_assets(tmp_path: Path) -> Path:
    small = tmp_path / 'event-small.png'
    card = tmp_path / 'event-card.png'
    Image.new('RGB', (184, 69), (120, 60, 40)).save(small)
    Image.new('RGB', (900, 1200), (40, 90, 140)).save(card)
    manifest_path = tmp_path / '20260310T121000Z_video_manifest_event_small.json'
    manifest_path.write_text(
        json.dumps(
            {
                'manifest_version': 2,
                'run_key': '20260310T121000Z',
                'created_at': '2026-03-10T12:10:00',
                'offer_id': 'event:small',
                'short_title': 'Steam Tower Defense Fest is on now!',
                'hook_line': '????? ??? ??????.',
                'summary_line': '????????? ??????? ???????? ??????????.',
                'urgency_line': '??? ?????????? ?????.',
                'asset_refs': {
                    'game_image': str(small),
                    'background': str(small),
                    'card_image': str(card),
                },
                'template_hint': 'event-countdown',
                'context': {
                    'store': 'Steam',
                    'offer_kind': 'event',
                    'lane': 'event_festival',
                },
            },
            ensure_ascii=False,
        ),
        encoding='utf-8',
    )
    return manifest_path


def test_render_manifest_event_uses_card_image_when_source_assets_are_too_small(tmp_path: Path) -> None:
    manifest_path = make_event_manifest_with_small_assets(tmp_path)
    manifest = ManifestLoader().load(manifest_path)
    assets = AssetResolver(assets_dir=tmp_path / 'renderer-assets', logger=StructuredLogger('event_asset_resolver_test')).resolve(manifest)
    ffmpeg_renderer = StubFFmpegRenderer()
    use_case = build_use_case(tmp_path, ffmpeg_renderer)

    result = use_case.execute(manifest_path)

    assert assets.game_image.path == tmp_path / 'event-card.png'
    assert assets.game_image.used_fallback is False
    assert assets.background.path == tmp_path / 'event-card.png'
    assert assets.background.used_fallback is False
    assert result.status == 'rendered'
    assert result.artifact_path is not None and result.artifact_path.exists()
    artifact = json.loads(result.artifact_path.read_text(encoding='utf-8'))
    assert artifact['template_name'] == 'event_countdown'
    assert artifact['details']['warnings'] == ['missing badge']
