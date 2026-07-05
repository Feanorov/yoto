from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageChops

from dealbot.video import (
    ScenePreviewRenderError,
    build_renderer_input,
    build_scene_asset_plan,
    build_scene_layout_payload,
    build_video_manifest_draft,
    build_video_offer_from_preview_report,
    export_video_offer_artifacts,
    render_scene_previews,
)
from tools.export_video_offer_artifacts import main as export_video_offer_artifacts_main


def _find_font_source() -> Path:
    candidates = [
        Path(r"C:\Windows\Fonts\ARIAL_UNICODE_MS.ttf"),
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path(r"C:\Windows\Fonts\calibri.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    raise AssertionError("No test font source is available on this machine.")


def _copy_test_font(tmp_path: Path) -> Path:
    font_path = tmp_path / "fonts" / "scene-preview-test-font.ttf"
    font_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_find_font_source(), font_path)
    return font_path


def _create_local_image(path: Path, *, color: tuple[int, int, int], size: tuple[int, int]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, format="PNG")
    return path


def _build_preview_report_payload(
    *,
    card_path: Path,
    screenshot_path: Path,
    title: str = "Preview Render Test Game",
    current_price: int | None = 14900,
    old_price: int | None = 29900,
    discount: int | None = 50,
    reviews: int | None = 42000,
    positive_pct: int | None = 94,
    promo_end: str | None = "2026-06-25T18:00:00",
) -> dict:
    candidate = {
        "title": title,
        "offer_id": "steam:scene-preview-test",
        "source": "steam",
        "platform": "steam",
        "store_url": "https://store.steampowered.com/app/50",
        "discount": discount,
        "current_price": current_price,
        "old_price": old_price,
        "reviews": reviews,
        "positive_pct": positive_pct,
    }
    artifact = {
        "offer_id": "steam:scene-preview-test",
        "caption_html": "<b>Preview Render Test Game</b>",
        "caption_hash": "scene-preview-caption-hash",
        "image_hash": "scene-preview-image-hash",
        "idempotency_key": "scene-preview-offer-key",
        "image_path": str(card_path),
        "assets_used": [str(screenshot_path)],
        "render_diagnostics": {},
        "card_family": "DISCOUNT",
        "template_id": "steam_discount",
    }
    offer_snapshot = {
        "offer_id": "steam:scene-preview-test",
        "source": "steam",
        "title": title,
        "store_url": "https://store.steampowered.com/app/50",
        "currency": "UAH",
        "price_after_minor": current_price,
        "price_before_minor": old_price,
        "discount_percent": discount,
        "promo_end": promo_end,
        "review_score": positive_pct,
        "review_count": reviews,
        "achievements_count": 55,
        "has_trading_cards": True,
        "assets": {
            "hero": str(screenshot_path),
            "screenshot": str(screenshot_path),
        },
        "metadata": {
            "official_trailers": [],
            "official_screenshots": [str(screenshot_path)],
        },
    }
    return {
        "run_key": "20260625T181500Z",
        "created_at": "2026-06-25T18:15:00",
        "send_test_target": {
            "candidate": dict(candidate),
            "artifact": dict(artifact),
        },
        "pinned_publish": {
            "contract_version": 1,
            "source": "preview",
            "created_at": "2026-06-25T18:15:00",
            "report_run_key": "20260625T181500Z",
            "candidate": dict(candidate),
            "offer_snapshot": dict(offer_snapshot),
            "decision_snapshot": {
                "lane": "high_value_discount",
                "template_id": "steam_discount",
            },
            "artifact": dict(artifact),
            "validation": {
                "image_exists": True,
                "caption_hash_verified": True,
                "image_hash_verified": True,
            },
        },
    }


def _build_renderer_input_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    title: str = "Preview Render Test Game",
    screenshot_color: tuple[int, int, int] = (160, 40, 40),
    card_color: tuple[int, int, int] = (40, 70, 170),
    current_price: int | None = 14900,
    old_price: int | None = 29900,
    discount: int | None = 50,
    reviews: int | None = 42000,
    positive_pct: int | None = 94,
    promo_end: str | None = "2026-06-25T18:00:00",
) -> tuple[dict, Path, Path]:
    font_path = _copy_test_font(tmp_path)
    monkeypatch.setenv("YOTO_SCENE_PREVIEW_FONT_PATH", str(font_path))

    screenshot_path = _create_local_image(
        tmp_path / "visuals" / "local-screenshot.png",
        color=screenshot_color,
        size=(1600, 900),
    )
    card_path = _create_local_image(
        tmp_path / "visuals" / "local-card.png",
        color=card_color,
        size=(1200, 1200),
    )
    report = _build_preview_report_payload(
        card_path=card_path,
        screenshot_path=screenshot_path,
        title=title,
        current_price=current_price,
        old_price=old_price,
        discount=discount,
        reviews=reviews,
        positive_pct=positive_pct,
        promo_end=promo_end,
    )
    video_offer = build_video_offer_from_preview_report(report)
    draft_manifest = build_video_manifest_draft(video_offer)
    scene_asset_plan = build_scene_asset_plan(video_offer, draft_manifest)
    scene_layout_payload = build_scene_layout_payload(video_offer, scene_asset_plan)
    renderer_input = build_renderer_input(video_offer, scene_asset_plan, scene_layout_payload)
    return renderer_input, screenshot_path, card_path


def _write_local_preview_report(tmp_path: Path) -> Path:
    screenshot_path = _create_local_image(
        tmp_path / "visuals" / "local-screenshot.png",
        color=(160, 40, 40),
        size=(1600, 900),
    )
    card_path = _create_local_image(
        tmp_path / "visuals" / "local-card.png",
        color=(40, 70, 170),
        size=(1200, 1200),
    )
    report_path = tmp_path / "output" / "analytics" / "scene-preview-renderer-preview.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            _build_preview_report_payload(card_path=card_path, screenshot_path=screenshot_path),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return report_path


def _scene(payload: dict, scene_id: str) -> dict:
    for scene_payload in payload["scenes"]:
        if scene_payload["scene_id"] == scene_id:
            return scene_payload
    raise AssertionError(f"Missing scene_id={scene_id!r}")


def _bright_bbox(image_path: Path, *, threshold: int = 210) -> tuple[int, int, int, int] | None:
    with Image.open(image_path) as image:
        grayscale = image.convert("L")
        mask = grayscale.point(lambda value: 255 if value >= threshold else 0, mode="1")
        return mask.getbbox()


def test_renders_exactly_five_pngs_with_deterministic_filenames_order_and_size(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer_input, _, _ = _build_renderer_input_fixture(tmp_path, monkeypatch)
    output_dir = tmp_path / "scene_previews"

    rendered_paths = render_scene_previews(renderer_input, output_dir)

    assert [path.name for path in rendered_paths] == [
        "01_hook.png",
        "02_identity.png",
        "03_offer_proof.png",
        "04_trust_or_deadline.png",
        "05_telegram_cta.png",
    ]
    assert len(rendered_paths) == 5
    for path in rendered_paths:
        assert path.exists()
        with Image.open(path) as image:
            assert image.size == (1080, 1920)


def test_background_visuals_are_rendered_and_scene_specific(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer_input, _, _ = _build_renderer_input_fixture(tmp_path, monkeypatch)
    output_dir = tmp_path / "scene_previews"

    rendered_paths = render_scene_previews(renderer_input, output_dir)

    with Image.open(rendered_paths[0]) as hook_image, Image.open(rendered_paths[2]) as offer_image:
        hook_pixel = hook_image.getpixel((40, 40))
        offer_pixel = offer_image.getpixel((40, 40))

    assert hook_pixel[0] > hook_pixel[2]
    assert offer_pixel[2] > offer_pixel[0]


def test_required_text_creates_visible_non_background_pixels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer_input, _, _ = _build_renderer_input_fixture(tmp_path, monkeypatch)
    output_dir = tmp_path / "scene_previews"

    rendered_paths = render_scene_previews(renderer_input, output_dir)
    hook_path = rendered_paths[0]

    with Image.open(hook_path) as image:
        image = image.convert("RGB")
        baseline_color = image.getpixel((10, 10))
        baseline = Image.new("RGB", image.size, baseline_color)
        diff_bbox = ImageChops.difference(image, baseline).getbbox()

    assert diff_bbox is not None


def test_long_text_remains_inside_safe_bounds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer_input, _, _ = _build_renderer_input_fixture(
        tmp_path,
        monkeypatch,
        screenshot_color=(18, 26, 42),
    )
    hook_scene = _scene(renderer_input, "hook")
    hook_scene["text_blocks"][0]["text"] = (
        "Дуже довгий український заголовок для перевірки переносу рядків у безпечній вертикальній зоні"
    )
    output_dir = tmp_path / "scene_previews"

    rendered_paths = render_scene_previews(renderer_input, output_dir)
    bbox = _bright_bbox(rendered_paths[0])

    assert bbox is not None
    assert bbox[0] >= 96
    assert bbox[1] >= 140
    assert bbox[2] <= 984
    assert bbox[3] <= 760


def test_ukrainian_cyrillic_text_renders(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer_input, _, _ = _build_renderer_input_fixture(
        tmp_path,
        monkeypatch,
        title="Безкоштовна українська гра",
        screenshot_color=(20, 24, 36),
    )
    identity_scene = _scene(renderer_input, "identity")
    identity_scene["text_blocks"][0]["text"] = "Найкраща знижка українською"
    output_dir = tmp_path / "scene_previews"

    rendered_paths = render_scene_previews(renderer_input, output_dir)

    assert _bright_bbox(rendered_paths[1]) is not None


def test_missing_local_visual_fails_clearly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer_input, _, _ = _build_renderer_input_fixture(tmp_path, monkeypatch)
    renderer_input["scenes"][0]["visual"]["asset_ref"] = str(tmp_path / "missing-local.png")
    output_dir = tmp_path / "scene_previews"

    with pytest.raises(ScenePreviewRenderError) as excinfo:
        render_scene_previews(renderer_input, output_dir)

    assert "no usable local visual" in str(excinfo.value)
    assert not output_dir.exists()


def test_remote_urls_are_never_downloaded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer_input, _, _ = _build_renderer_input_fixture(tmp_path, monkeypatch)
    renderer_input["scenes"][0]["visual"]["asset_ref"] = "https://example.com/not-local.png"
    before_modules = {
        name
        for name in sys.modules
        if name == "httpx"
        or name.startswith("httpx.")
        or name == "requests"
        or name.startswith("requests.")
        or name == "telegram"
        or name.startswith("telegram.")
        or name == "ffmpeg"
        or name.startswith("ffmpeg.")
    }

    with pytest.raises(ScenePreviewRenderError) as excinfo:
        render_scene_previews(renderer_input, tmp_path / "scene_previews")

    after_modules = {
        name
        for name in sys.modules
        if name == "httpx"
        or name.startswith("httpx.")
        or name == "requests"
        or name.startswith("requests.")
        or name == "telegram"
        or name.startswith("telegram.")
        or name == "ffmpeg"
        or name.startswith("ffmpeg.")
    }

    assert "remote visual URLs are not allowed" in str(excinfo.value)
    assert after_modules == before_modules


def test_rendering_occurs_only_with_new_flag_and_existing_behavior_remains_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("YOTO_SCENE_PREVIEW_FONT_PATH", str(_copy_test_font(tmp_path)))
    report_path = _write_local_preview_report(tmp_path)
    default_dir = tmp_path / "exports" / "default"
    renderer_dir = tmp_path / "exports" / "renderer"
    preview_dir = tmp_path / "exports" / "previews"

    default_result = export_video_offer_artifacts(report_path, output_dir=default_dir)
    renderer_result = export_video_offer_artifacts(report_path, output_dir=renderer_dir, with_renderer_input=True)
    preview_result = export_video_offer_artifacts(
        report_path,
        output_dir=preview_dir,
        render_scene_previews_flag=True,
    )

    assert default_result.scene_asset_plan_json_path is None
    assert default_result.scene_layout_payload_json_path is None
    assert default_result.renderer_input_json_path is None
    assert default_result.scene_previews_dir_path is None
    assert default_result.rendered_scene_count is None
    assert not (default_dir / "scene_previews").exists()

    assert renderer_result.renderer_input_json_path == (renderer_dir / "renderer_input.json").resolve()
    assert renderer_result.scene_previews_dir_path is None
    assert renderer_result.rendered_scene_count is None
    assert not (renderer_dir / "scene_previews").exists()

    assert preview_result.scene_asset_plan_json_path == (preview_dir / "scene_asset_plan.json").resolve()
    assert preview_result.scene_layout_payload_json_path == (preview_dir / "scene_layout_payload.json").resolve()
    assert preview_result.renderer_input_json_path == (preview_dir / "renderer_input.json").resolve()
    assert preview_result.renderer_input_staged_json_path == (preview_dir / "renderer_input_staged.json").resolve()
    assert preview_result.scene_visual_qa_report_json_path == (preview_dir / "scene_visual_qa_report.json").resolve()
    assert preview_result.staged_visuals_dir_path == (preview_dir / "staged_visuals").resolve()
    assert preview_result.scene_previews_dir_path == (preview_dir / "scene_previews").resolve()
    assert preview_result.renderer_input_staged_json_path.exists()
    assert preview_result.scene_visual_qa_report_json_path.exists()
    assert preview_result.staged_visuals_dir_path.exists()
    assert preview_result.scene_previews_dir_path.exists()
    assert preview_result.visual_qa_status in {"warn", "pass"}
    assert preview_result.staged_scene_count == 0
    assert preview_result.staged_visual_count == 0
    assert preview_result.rendered_scene_count == 5
    assert sorted(path.name for path in preview_result.scene_previews_dir_path.glob("*.png")) == [
        "01_hook.png",
        "02_identity.png",
        "03_offer_proof.png",
        "04_trust_or_deadline.png",
        "05_telegram_cta.png",
    ]


def test_cli_render_scene_previews_flag_wires_optional_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    monkeypatch.setenv("YOTO_SCENE_PREVIEW_FONT_PATH", str(_copy_test_font(tmp_path)))
    report_path = _write_local_preview_report(tmp_path)
    default_dir = tmp_path / "cli-exports" / "default"
    preview_dir = tmp_path / "cli-exports" / "previews"

    default_exit = export_video_offer_artifacts_main(
        ["--from-report", str(report_path), "--output-dir", str(default_dir)],
    )
    default_stdout = capsys.readouterr().out
    preview_exit = export_video_offer_artifacts_main(
        ["--from-report", str(report_path), "--output-dir", str(preview_dir), "--render-scene-previews"],
    )
    preview_stdout = capsys.readouterr().out

    assert default_exit == 0
    assert preview_exit == 0
    assert "scene_previews_dir_path:" not in default_stdout
    assert "rendered_scene_count:" not in default_stdout

    assert "scene_asset_plan_json_path:" in preview_stdout
    assert "scene_layout_payload_json_path:" in preview_stdout
    assert "renderer_input_json_path:" in preview_stdout
    assert "renderer_input_staged_json_path:" in preview_stdout
    assert "scene_visual_qa_report_json_path:" in preview_stdout
    assert "staged_visuals_dir_path:" in preview_stdout
    assert "visual_qa_status:" in preview_stdout
    assert "visual_qa_error_count:" in preview_stdout
    assert "visual_qa_warning_count:" in preview_stdout
    assert "staged_scene_count: 0" in preview_stdout
    assert "staged_visual_count: 0" in preview_stdout
    assert "scene_previews_dir_path:" in preview_stdout
    assert "rendered_scene_count: 5" in preview_stdout
    assert (preview_dir / "scene_previews" / "01_hook.png").exists()


def test_scene_preview_renderer_does_not_import_old_video_generator_or_network_ffmpeg_telegram_modules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer_input, _, _ = _build_renderer_input_fixture(tmp_path, monkeypatch)
    before_modules = {
        name
        for name in sys.modules
        if name == "video_generator"
        or name.startswith("video_generator.")
        or name == "httpx"
        or name.startswith("httpx.")
        or name == "requests"
        or name.startswith("requests.")
        or name == "telegram"
        or name.startswith("telegram.")
        or name == "ffmpeg"
        or name.startswith("ffmpeg.")
    }

    render_scene_previews(renderer_input, tmp_path / "scene_previews")

    after_modules = {
        name
        for name in sys.modules
        if name == "video_generator"
        or name.startswith("video_generator.")
        or name == "httpx"
        or name.startswith("httpx.")
        or name == "requests"
        or name.startswith("requests.")
        or name == "telegram"
        or name.startswith("telegram.")
        or name == "ffmpeg"
        or name.startswith("ffmpeg.")
    }
    assert after_modules == before_modules


def test_cta_variants_remain_available_after_preview_rendering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer_input, _, _ = _build_renderer_input_fixture(tmp_path, monkeypatch)
    cta_scene = _scene(renderer_input, "telegram_cta")
    cta_scene["platform_variants"] = {
        "tiktok": "Приєднуйся до Telegram за повним лінком",
        "shorts": "Відкрий Telegram для повного поста",
        "reels": "Знайди повну пропозицію в Telegram",
    }
    cta_scene["text_blocks"] = [
        {
            "role": "cta",
            "text": "Дивись повну пропозицію в Telegram",
            "priority": 1,
            "required": True,
            "max_lines": 2,
            "alignment": "center",
            "anchor": "lower_third",
            "size_class": "lg",
        },
        {
            "role": "cta_tiktok",
            "text": cta_scene["platform_variants"]["tiktok"],
            "priority": 2,
            "required": False,
            "max_lines": 2,
            "alignment": "center",
            "anchor": "lower_third",
            "size_class": "sm",
        },
    ]

    rendered_paths = render_scene_previews(renderer_input, tmp_path / "scene_previews")

    assert rendered_paths[-1].name == "05_telegram_cta.png"
    assert _bright_bbox(rendered_paths[-1]) is not None
