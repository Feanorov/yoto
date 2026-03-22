from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from video_generator.application.use_cases.build_voice_ready_package import BuildVoiceReadyPackageUseCase
from video_generator.domain.scene_planner import ScenePlanner
from video_generator.domain.template_selector import TemplateSelector
from video_generator.infrastructure.asset_resolver import AssetResolver
from video_generator.infrastructure.ffmpeg_renderer import FFmpegRenderError
from video_generator.infrastructure.font_loader import FontLoader
from video_generator.infrastructure.manifest_loader import ManifestLoader
from video_generator.infrastructure.scene_image_renderer import SceneImageRenderer
from video_generator.infrastructure.structured_logger import StructuredLogger


class StubFFmpegRenderer:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def render(self, request) -> None:
        self.calls += 1
        if self.fail:
            raise FFmpegRenderError('ffmpeg unavailable for test')
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        request.output_path.write_bytes(b'mp4')


def write_manifest(
    tmp_path: Path,
    *,
    file_name: str,
    payload: dict,
) -> Path:
    asset = tmp_path / f'{file_name}_asset.png'
    Image.new('RGB', (900, 900), (64, 88, 120)).save(asset)
    payload.setdefault(
        'asset_refs',
        {
            'game_image': str(asset),
            'background': str(asset),
            'card_image': str(asset),
        },
    )
    manifest_path = tmp_path / f'{file_name}.json'
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    return manifest_path


def build_use_case(tmp_path: Path, ffmpeg_renderer: StubFFmpegRenderer) -> BuildVoiceReadyPackageUseCase:
    logger = StructuredLogger('voice_ready_package_test')
    asset_resolver = AssetResolver(assets_dir=tmp_path / 'assets', logger=logger)
    scene_renderer = SceneImageRenderer(
        asset_resolver=asset_resolver,
        font_loader=FontLoader(logger=logger),
        logger=logger,
    )
    return BuildVoiceReadyPackageUseCase(
        manifest_loader=ManifestLoader(),
        asset_resolver=asset_resolver,
        template_selector=TemplateSelector(),
        scene_planner=ScenePlanner(),
        scene_renderer=scene_renderer,
        ffmpeg_renderer=ffmpeg_renderer,
        output_dir=tmp_path / 'voice_ready',
        logger=logger,
    )


def make_discount_payload() -> dict:
    return {
        'manifest_version': 2,
        'run_key': '20260320T120000Z',
        'created_at': '2026-03-20T12:00:00',
        'offer_id': 'steam:1237970',
        'short_title': 'Titanfall 2',
        'hook_line': '\u0417\u043d\u0438\u0436\u043a\u0430 90% \u0432\u0436\u0435 \u0430\u043a\u0442\u0438\u0432\u043d\u0430.',
        'summary_line': '\u0422\u0430\u043a\u0442\u0438\u0447\u043d\u0438\u0439 \u0448\u0443\u0442\u0435\u0440 \u0437 \u0434\u0443\u0436\u0435 \u0441\u0438\u043b\u044c\u043d\u043e\u044e \u0446\u0456\u043d\u043e\u044e \u043d\u0430 \u0437\u0430\u0440\u0430\u0437.',
        'urgency_line': '\u0426\u0456\u043d\u0430 \u0430\u043a\u0442\u0443\u0430\u043b\u044c\u043d\u0430 \u0434\u043e 21 \u0431\u0435\u0440\u0435\u0437\u043d\u044f 2026, 17:00.',
        'cta_line': '\u041f\u0435\u0440\u0435\u0432\u0456\u0440 \u043f\u0440\u043e\u043f\u043e\u0437\u0438\u0446\u0456\u044e \u0437\u0430\u0440\u0430\u0437.',
        'caption_html': '<b>Titanfall 2</b>\n\n\u0417\u0430\u0440\u0430\u0437 79 \u0433\u0440\u043d \u0437\u0430\u043c\u0456\u0441\u0442\u044c 799 \u0433\u0440\u043d.\n\n\u0426\u0456\u043d\u0430 \u0430\u043a\u0442\u0443\u0430\u043b\u044c\u043d\u0430 \u0434\u043e 21 \u0431\u0435\u0440\u0435\u0437\u043d\u044f 2026, 17:00.\n\n#steam',
        'content_type': 'discount',
        'template_hint': 'deal-spotlight',
        'context': {
            'store': 'Steam',
            'offer_kind': 'discount',
            'lane': 'high_value_discount',
            'content_type': 'discount',
        },
        'voice_facts': {
            'title': 'Titanfall 2',
            'price_before_minor': 79900,
            'price_after_minor': 7900,
            'currency': 'UAH',
            'discount_percent': 90,
            'promo_end': '2026-03-21T17:00:00',
        },
        'source_artifact': {
            'image_path': None,
        },
    }


def make_free_game_payload(*, access_type: str) -> dict:
    return {
        'manifest_version': 2,
        'run_key': '20260320T120500Z',
        'created_at': '2026-03-20T12:05:00',
        'offer_id': 'epic:cozy-grove',
        'short_title': 'Cozy Grove',
        'hook_line': '\u0411\u0435\u0437\u043a\u043e\u0448\u0442\u043e\u0432\u043d\u0430 \u0440\u043e\u0437\u0434\u0430\u0447\u0430 \u0432 Epic \u0432\u0436\u0435 \u0430\u043a\u0442\u0438\u0432\u043d\u0430.',
        'summary_line': '\u0413\u0440\u0443 \u043c\u043e\u0436\u043d\u0430 \u0434\u043e\u0434\u0430\u0442\u0438 \u043d\u0430 \u0430\u043a\u0430\u0443\u043d\u0442 \u0431\u0435\u0437 \u043e\u043f\u043b\u0430\u0442\u0438.',
        'urgency_line': '\u0417\u0430\u0431\u0440\u0430\u0442\u0438 \u043c\u043e\u0436\u043d\u0430 \u0434\u043e 21 \u0431\u0435\u0440\u0435\u0437\u043d\u044f 2026, 15:00.',
        'cta_line': '\u0417\u0430\u0431\u0438\u0440\u0430\u0439 \u0437\u0430\u0440\u0430\u0437, \u043f\u043e\u043a\u0438 \u0440\u043e\u0437\u0434\u0430\u0447\u0430 \u0430\u043a\u0442\u0438\u0432\u043d\u0430.',
        'caption_html': '<b>Cozy Grove</b>\n\n\u0417\u0430\u0431\u0440\u0430\u0442\u0438 \u043c\u043e\u0436\u043d\u0430 \u0434\u043e 21 \u0431\u0435\u0440\u0435\u0437\u043d\u044f 2026, 15:00.\n\n#freegame',
        'content_type': 'freebie',
        'template_hint': 'freebie-flash',
        'context': {
            'store': 'Epic Games Store',
            'offer_kind': 'freebie',
            'lane': 'breaking_freebie',
            'content_type': 'freebie',
        },
        'voice_facts': {
            'title': 'Cozy Grove',
            'free_access_type': access_type,
            'promo_end': '2026-03-21T15:00:00',
        },
    }


def make_roundup_payload() -> dict:
    return {
        'manifest_version': 2,
        'run_key': '20260320T121000Z',
        'created_at': '2026-03-20T12:10:00',
        'offer_id': 'roundup:discounts',
        'short_title': 'Roundup: Big Discount Highlights',
        'hook_line': 'Roundup: Big Discount Highlights',
        'summary_line': 'Battlefield V \u00b7 A Way Out \u00b7 Battlefield 2042',
        'urgency_line': '\u041f\u0435\u0440\u0435\u0433\u043b\u044f\u043d\u044c \u0434\u043e\u0431\u0456\u0440\u043a\u0443, \u043f\u043e\u043a\u0438 \u0446\u0456 \u043f\u0440\u043e\u043f\u043e\u0437\u0438\u0446\u0456\u0457 \u0449\u0435 \u0430\u043a\u0442\u0438\u0432\u043d\u0456.',
        'cta_line': '\u041f\u0435\u0440\u0435\u0433\u043b\u044f\u043d\u044c \u0434\u043e\u0431\u0456\u0440\u043a\u0443 \u0437\u0430\u0440\u0430\u0437.',
        'caption_html': '<b>Roundup</b>',
        'content_type': 'roundup',
        'template_hint': 'deal-spotlight',
        'context': {
            'store': 'Steam',
            'offer_kind': 'discount',
            'lane': 'roundup_digest',
            'template_id': 'roundup_digest',
            'content_type': 'roundup',
            'video_template_intent': 'roundup_digest',
        },
        'roundup_items': [
            {'title': 'Battlefield V Definitive Edition', 'discount_percent': 95, 'offer_kind': 'discount'},
            {'title': 'A Way Out', 'discount_percent': 90, 'offer_kind': 'discount'},
            {'title': 'Battlefield 2042', 'discount_percent': 95, 'offer_kind': 'discount'},
            {'title': 'STAR WARS Jedi: Survivor Deluxe', 'discount_percent': 90, 'offer_kind': 'discount'},
            {'title': 'Grand Theft Auto V Enhanced', 'discount_percent': 56, 'offer_kind': 'discount'},
        ],
        'voice_facts': {
            'roundup_title': 'Roundup: Big Discount Highlights',
            'item_count': 5,
        },
    }


def make_sparse_discount_payload() -> dict:
    return {
        'manifest_version': 2,
        'run_key': '20260320T122000Z',
        'created_at': '2026-03-20T12:20:00',
        'offer_id': 'steam:sparse',
        'short_title': 'Sparse Deal',
        'hook_line': 'Deal live now.',
        'summary_line': 'No trusted details survived into the manifest.',
        'urgency_line': 'Offer still live.',
        'cta_line': 'Check the post.',
        'caption_html': '',
        'content_type': 'discount',
        'template_hint': 'deal-spotlight',
        'context': {
            'store': 'Steam',
            'offer_kind': 'discount',
            'lane': 'planned',
            'content_type': 'discount',
        },
    }


def test_build_voice_ready_package_emits_expected_files_and_preview(tmp_path: Path) -> None:
    manifest_path = write_manifest(tmp_path, file_name='discount', payload=make_discount_payload())
    ffmpeg_renderer = StubFFmpegRenderer()
    use_case = build_use_case(tmp_path, ffmpeg_renderer)

    result = use_case.execute(manifest_path)

    assert result.status == 'packaged'
    assert result.package_dir is not None and result.package_dir.exists()
    assert result.package_manifest_path is not None and result.package_manifest_path.exists()
    assert result.review_path is not None and result.review_path.exists()
    assert result.scene_plan_path is not None and result.scene_plan_path.exists()
    assert result.voice_script_path is not None and result.voice_script_path.exists()
    assert result.timed_script_path is not None and result.timed_script_path.exists()
    assert result.preview_video_path is not None and result.preview_video_path.exists()
    assert ffmpeg_renderer.calls == 1

    scene_plan = json.loads(result.scene_plan_path.read_text(encoding='utf-8'))
    assert scene_plan['family'] == 'DISCOUNT'
    assert scene_plan['scene_count'] == 3

    voice_script = result.voice_script_path.read_text(encoding='utf-8')
    assert 'Titanfall 2' in voice_script
    assert 'пості' in voice_script


def test_voice_ready_package_is_deterministic_for_same_manifest(tmp_path: Path) -> None:
    manifest_path = write_manifest(tmp_path, file_name='discount_deterministic', payload=make_discount_payload())
    use_case = build_use_case(tmp_path, StubFFmpegRenderer())

    first = use_case.execute(manifest_path)
    first_manifest = first.package_manifest_path.read_text(encoding='utf-8')
    first_script = first.voice_script_path.read_text(encoding='utf-8')

    second = use_case.execute(manifest_path)
    second_manifest = second.package_manifest_path.read_text(encoding='utf-8')
    second_script = second.voice_script_path.read_text(encoding='utf-8')

    assert first.status == 'packaged'
    assert second.status == 'packaged'
    assert first.package_dir == second.package_dir
    assert first_manifest == second_manifest
    assert first_script == second_script


def test_free_game_keep_forever_script_mentions_nazavzhdy(tmp_path: Path) -> None:
    manifest_path = write_manifest(tmp_path, file_name='free_keep', payload=make_free_game_payload(access_type='keep_forever'))
    use_case = build_use_case(tmp_path, StubFFmpegRenderer())

    result = use_case.execute(manifest_path)
    script = result.voice_script_path.read_text(encoding='utf-8')

    assert 'назавжди' in script
    assert 'тимчасов' not in script


def test_free_game_temporary_access_script_mentions_temporary_not_keep_forever(tmp_path: Path) -> None:
    manifest_path = write_manifest(tmp_path, file_name='free_temp', payload=make_free_game_payload(access_type='temporary_access'))
    use_case = build_use_case(tmp_path, StubFFmpegRenderer())

    result = use_case.execute(manifest_path)
    script = result.voice_script_path.read_text(encoding='utf-8')

    assert 'тимчасов' in script
    assert 'назавжди' not in script


def test_roundup_top_list_package_has_four_scenes(tmp_path: Path) -> None:
    manifest_path = write_manifest(tmp_path, file_name='roundup', payload=make_roundup_payload())
    use_case = build_use_case(tmp_path, StubFFmpegRenderer())

    result = use_case.execute(manifest_path)
    scene_plan = json.loads(result.scene_plan_path.read_text(encoding='utf-8'))
    timed_script = result.timed_script_path.read_text(encoding='utf-8')

    assert result.status == 'packaged'
    assert scene_plan['family'] == 'TOP_LIST'
    assert scene_plan['scene_count'] == 4
    assert 'SCENE 04' in timed_script


def test_package_succeeds_without_preview_video_when_ffmpeg_fails(tmp_path: Path) -> None:
    manifest_path = write_manifest(tmp_path, file_name='discount_no_ffmpeg', payload=make_discount_payload())
    use_case = build_use_case(tmp_path, StubFFmpegRenderer(fail=True))

    result = use_case.execute(manifest_path)

    assert result.status == 'packaged'
    assert result.preview_video_path is None
    assert any(warning.startswith('preview_video_skipped:') for warning in result.warnings)


def test_sparse_discount_inputs_fall_back_gracefully(tmp_path: Path) -> None:
    manifest_path = write_manifest(tmp_path, file_name='discount_sparse', payload=make_sparse_discount_payload())
    use_case = build_use_case(tmp_path, StubFFmpegRenderer())

    result = use_case.execute(manifest_path)
    script = result.voice_script_path.read_text(encoding='utf-8')

    assert result.status == 'packaged'
    assert script.strip() != ''
    assert 'voice_facts_missing_used_manifest_fallbacks' in result.warnings
