from __future__ import annotations

from email.message import Message
import io
import json
import shutil
import sys
from pathlib import Path

import pytest
from PIL import Image

from dealbot.video import (
    ScenePreviewRenderError,
    VisualStagingError,
    build_renderer_input,
    build_scene_asset_plan,
    build_scene_layout_payload,
    build_video_manifest_draft,
    build_video_offer_from_preview_report,
    export_video_offer_artifacts,
    render_scene_previews,
    stage_renderer_visuals,
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
    font_path = tmp_path / "fonts" / "video-visual-staging-test-font.ttf"
    font_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_find_font_source(), font_path)
    return font_path


def _create_local_image(path: Path, *, color: tuple[int, int, int], size: tuple[int, int]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, format="PNG")
    return path


def _png_bytes(*, color: tuple[int, int, int] = (210, 60, 70), size: tuple[int, int] = (1600, 900)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


class FakeResponse:
    def __init__(self, data: bytes, *, content_type: str, content_length: int | None = None) -> None:
        self._stream = io.BytesIO(data)
        headers = Message()
        headers.add_header("Content-Type", content_type)
        if content_length is not None:
            headers.add_header("Content-Length", str(content_length))
        self.headers = headers

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def _build_preview_report_payload(
    *,
    card_path: Path,
    screenshot_ref: str,
    official_trailers: list[str] | None = None,
) -> dict:
    candidate = {
        "title": "Visual Staging Test Game",
        "offer_id": "steam:visual-staging-test",
        "source": "steam",
        "platform": "steam",
        "store_url": "https://store.steampowered.com/app/60",
        "discount": 50,
        "current_price": 14900,
        "old_price": 29900,
        "reviews": 42000,
        "positive_pct": 94,
    }
    artifact = {
        "offer_id": "steam:visual-staging-test",
        "caption_html": "<b>Visual Staging Test Game</b>",
        "caption_hash": "visual-staging-caption-hash",
        "image_hash": "visual-staging-image-hash",
        "idempotency_key": "visual-staging-offer-key",
        "image_path": str(card_path),
        "assets_used": [screenshot_ref],
        "render_diagnostics": {},
        "card_family": "DISCOUNT",
        "template_id": "steam_discount",
    }
    offer_snapshot = {
        "offer_id": "steam:visual-staging-test",
        "source": "steam",
        "title": "Visual Staging Test Game",
        "store_url": "https://store.steampowered.com/app/60",
        "currency": "UAH",
        "price_after_minor": 14900,
        "price_before_minor": 29900,
        "discount_percent": 50,
        "promo_end": "2026-07-05T18:00:00",
        "review_score": 94,
        "review_count": 42000,
        "achievements_count": 55,
        "has_trading_cards": True,
        "assets": {
            "hero": screenshot_ref,
            "screenshot": screenshot_ref,
        },
        "metadata": {
            "official_trailers": list(official_trailers or []),
            "official_screenshots": [screenshot_ref],
        },
    }
    return {
        "run_key": "20260705T180000Z",
        "created_at": "2026-07-05T18:00:00",
        "send_test_target": {
            "candidate": dict(candidate),
            "artifact": dict(artifact),
        },
        "pinned_publish": {
            "contract_version": 1,
            "source": "preview",
            "created_at": "2026-07-05T18:00:00",
            "report_run_key": "20260705T180000Z",
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


def _write_preview_report(tmp_path: Path, *, screenshot_ref: str, official_trailers: list[str] | None = None) -> Path:
    card_path = _create_local_image(
        tmp_path / "visuals" / "local-card.png",
        color=(40, 70, 170),
        size=(1200, 1200),
    )
    report_path = tmp_path / "output" / "analytics" / "video-visual-staging-preview.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            _build_preview_report_payload(
                card_path=card_path,
                screenshot_ref=screenshot_ref,
                official_trailers=official_trailers,
            ),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return report_path


def _build_renderer_input_fixture(
    tmp_path: Path,
    *,
    screenshot_ref: str,
    official_trailers: list[str] | None = None,
) -> tuple[dict, Path]:
    card_path = _create_local_image(
        tmp_path / "visuals" / "local-card.png",
        color=(40, 70, 170),
        size=(1200, 1200),
    )
    report = _build_preview_report_payload(
        card_path=card_path,
        screenshot_ref=screenshot_ref,
        official_trailers=official_trailers,
    )
    video_offer = build_video_offer_from_preview_report(report)
    draft_manifest = build_video_manifest_draft(video_offer)
    scene_asset_plan = build_scene_asset_plan(video_offer, draft_manifest)
    scene_layout_payload = build_scene_layout_payload(video_offer, scene_asset_plan)
    renderer_input = build_renderer_input(video_offer, scene_asset_plan, scene_layout_payload)
    return renderer_input, card_path


def _scene(payload: dict, scene_id: str) -> dict:
    for scene_payload in payload["scenes"]:
        if scene_payload["scene_id"] == scene_id:
            return scene_payload
    raise AssertionError(f"Missing scene_id={scene_id!r}")


def test_stage_renderer_visuals_stages_remote_image_and_rewrites_visuals(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote_url = "https://cdn.example.com/visual-stage-hero.png"
    renderer_input, _ = _build_renderer_input_fixture(tmp_path, screenshot_ref=remote_url)

    def fake_urlopen(request, timeout: int) -> FakeResponse:
        return FakeResponse(
            _png_bytes(),
            content_type="image/png",
            content_length=len(_png_bytes()),
        )

    import dealbot.video.visual_staging as visual_staging

    monkeypatch.setattr(visual_staging.urllib.request, "urlopen", fake_urlopen)

    staged_renderer_input, metadata = stage_renderer_visuals(renderer_input, tmp_path / "exports")
    hook_visual = _scene(staged_renderer_input, "hook")["visual"]["asset_ref"]
    identity_visual = _scene(staged_renderer_input, "identity")["visual"]["asset_ref"]
    trust_visual = _scene(staged_renderer_input, "trust_or_deadline")["visual"]["asset_ref"]

    assert _scene(renderer_input, "hook")["visual"]["asset_ref"] == remote_url
    assert hook_visual == identity_visual == trust_visual
    assert hook_visual != remote_url
    assert hook_visual.endswith(".png")
    assert Path(hook_visual).exists()
    assert Path(hook_visual).parent == (tmp_path / "exports" / "staged_visuals").resolve()
    assert metadata["staged_scene_ids"] == ("hook", "identity", "trust_or_deadline")
    assert metadata["staged_scene_count"] == 3
    assert metadata["staged_visual_count"] == 1
    assert metadata["downloaded_visual_count"] == 1
    assert metadata["preserved_local_visual_count"] == 2


def test_stage_renderer_visuals_preserves_existing_local_visuals(tmp_path: Path) -> None:
    screenshot_path = _create_local_image(
        tmp_path / "visuals" / "local-screenshot.png",
        color=(160, 40, 40),
        size=(1600, 900),
    )
    renderer_input, _ = _build_renderer_input_fixture(tmp_path, screenshot_ref=str(screenshot_path))

    staged_renderer_input, metadata = stage_renderer_visuals(renderer_input, tmp_path / "exports")

    assert staged_renderer_input == renderer_input
    assert metadata["staged_scene_count"] == 0
    assert metadata["staged_visual_count"] == 0
    assert metadata["downloaded_visual_count"] == 0
    assert metadata["preserved_local_visual_count"] == 5


def test_stage_renderer_visuals_rejects_unsupported_remote_visual(tmp_path: Path) -> None:
    renderer_input, _ = _build_renderer_input_fixture(
        tmp_path,
        screenshot_ref="https://cdn.example.com/visual-stage-hero.png",
    )
    _scene(renderer_input, "hook")["visual"]["asset_ref"] = "https://cdn.example.com/trailer.mp4"

    with pytest.raises(VisualStagingError) as excinfo:
        stage_renderer_visuals(renderer_input, tmp_path / "exports")

    assert "unsupported remote visual URL" in str(excinfo.value)


def test_stage_renderer_visuals_rejects_missing_local_visual(tmp_path: Path) -> None:
    screenshot_path = _create_local_image(
        tmp_path / "visuals" / "local-screenshot.png",
        color=(160, 40, 40),
        size=(1600, 900),
    )
    renderer_input, _ = _build_renderer_input_fixture(tmp_path, screenshot_ref=str(screenshot_path))
    _scene(renderer_input, "hook")["visual"]["asset_ref"] = str(tmp_path / "missing-local.png")

    with pytest.raises(VisualStagingError) as excinfo:
        stage_renderer_visuals(renderer_input, tmp_path / "exports")

    assert "no usable local visual exists" in str(excinfo.value)


def test_stage_renderer_visuals_accepts_missing_extension_when_content_type_is_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote_url = "https://cdn.example.com/visual-stage-hero"
    renderer_input, _ = _build_renderer_input_fixture(tmp_path, screenshot_ref=remote_url)

    def fake_urlopen(request, timeout: int) -> FakeResponse:
        return FakeResponse(
            _png_bytes(),
            content_type="image/png",
            content_length=len(_png_bytes()),
        )

    import dealbot.video.visual_staging as visual_staging

    monkeypatch.setattr(visual_staging.urllib.request, "urlopen", fake_urlopen)

    staged_renderer_input, metadata = stage_renderer_visuals(renderer_input, tmp_path / "exports")
    hook_visual = _scene(staged_renderer_input, "hook")["visual"]["asset_ref"]

    assert hook_visual.endswith(".png")
    assert Path(hook_visual).exists()
    assert metadata["staged_visual_count"] == 1


def test_stage_renderer_visuals_preserves_scene_order_and_timing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote_url = "https://cdn.example.com/visual-stage-hero.png"
    renderer_input, _ = _build_renderer_input_fixture(tmp_path, screenshot_ref=remote_url)

    def fake_urlopen(request, timeout: int) -> FakeResponse:
        return FakeResponse(
            _png_bytes(),
            content_type="image/png",
            content_length=len(_png_bytes()),
        )

    import dealbot.video.visual_staging as visual_staging

    monkeypatch.setattr(visual_staging.urllib.request, "urlopen", fake_urlopen)

    staged_renderer_input, _ = stage_renderer_visuals(renderer_input, tmp_path / "exports")

    assert [scene["scene_id"] for scene in staged_renderer_input["scenes"]] == [
        "hook",
        "identity",
        "offer_proof",
        "trust_or_deadline",
        "telegram_cta",
    ]
    assert [scene["order"] for scene in staged_renderer_input["scenes"]] == [1, 2, 3, 4, 5]
    assert [scene["start_sec"] for scene in staged_renderer_input["scenes"]] == [0.0, 2.0, 4.5, 7.5, 10.5]
    assert [scene["end_sec"] for scene in staged_renderer_input["scenes"]] == [2.0, 4.5, 7.5, 10.5, 14.5]
    assert [scene["duration_sec"] for scene in staged_renderer_input["scenes"]] == [2.0, 2.5, 3.0, 3.0, 4.0]

    for original_scene, staged_scene in zip(renderer_input["scenes"], staged_renderer_input["scenes"], strict=True):
        assert staged_scene["text_blocks"] == original_scene["text_blocks"]
        assert staged_scene["safe_zone_profile"] == original_scene["safe_zone_profile"]
        assert staged_scene["motion"] == original_scene["motion"]
        assert staged_scene["warnings"] == original_scene["warnings"]


def test_stage_visuals_flag_writes_renderer_input_staged_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote_url = "https://cdn.example.com/export-stage-hero.png"
    report_path = _write_preview_report(tmp_path, screenshot_ref=remote_url)

    def fake_urlopen(request, timeout: int) -> FakeResponse:
        return FakeResponse(
            _png_bytes(),
            content_type="image/png",
            content_length=len(_png_bytes()),
        )

    import dealbot.video.visual_staging as visual_staging

    monkeypatch.setattr(visual_staging.urllib.request, "urlopen", fake_urlopen)

    result = export_video_offer_artifacts(
        report_path,
        output_dir=tmp_path / "exports" / "staged",
        stage_visuals_flag=True,
    )

    assert result.renderer_input_json_path == (tmp_path / "exports" / "staged" / "renderer_input.json").resolve()
    assert result.renderer_input_staged_json_path == (
        tmp_path / "exports" / "staged" / "renderer_input_staged.json"
    ).resolve()
    assert result.staged_visuals_dir_path == (tmp_path / "exports" / "staged" / "staged_visuals").resolve()
    assert result.renderer_input_staged_json_path.exists()
    assert result.staged_visuals_dir_path.exists()
    assert result.staged_scene_count == 3
    assert result.staged_visual_count == 1

    raw_renderer_input = json.loads(result.renderer_input_json_path.read_text(encoding="utf-8"))
    staged_renderer_input = json.loads(result.renderer_input_staged_json_path.read_text(encoding="utf-8"))

    assert _scene(raw_renderer_input, "hook")["visual"]["asset_ref"] == remote_url
    assert Path(_scene(staged_renderer_input, "hook")["visual"]["asset_ref"]).exists()


def test_render_scene_previews_uses_staged_visuals_for_remote_images(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote_url = "https://cdn.example.com/render-stage-hero.png"
    report_path = _write_preview_report(tmp_path, screenshot_ref=remote_url)
    monkeypatch.setenv("YOTO_SCENE_PREVIEW_FONT_PATH", str(_copy_test_font(tmp_path)))

    def fake_urlopen(request, timeout: int) -> FakeResponse:
        return FakeResponse(
            _png_bytes(),
            content_type="image/png",
            content_length=len(_png_bytes()),
        )

    import dealbot.video.visual_staging as visual_staging

    monkeypatch.setattr(visual_staging.urllib.request, "urlopen", fake_urlopen)

    result = export_video_offer_artifacts(
        report_path,
        output_dir=tmp_path / "exports" / "previews",
        render_scene_previews_flag=True,
    )
    raw_renderer_input = json.loads(result.renderer_input_json_path.read_text(encoding="utf-8"))
    staged_renderer_input = json.loads(result.renderer_input_staged_json_path.read_text(encoding="utf-8"))

    assert result.scene_previews_dir_path == (tmp_path / "exports" / "previews" / "scene_previews").resolve()
    assert result.scene_previews_dir_path.exists()
    assert result.rendered_scene_count == 5
    assert _scene(raw_renderer_input, "hook")["visual"]["asset_ref"] == remote_url
    assert Path(_scene(staged_renderer_input, "hook")["visual"]["asset_ref"]).exists()
    assert sorted(path.name for path in result.scene_previews_dir_path.glob("*.png")) == [
        "01_hook.png",
        "02_identity.png",
        "03_offer_proof.png",
        "04_trust_or_deadline.png",
        "05_telegram_cta.png",
    ]


def test_default_exporter_behavior_remains_unchanged_without_stage_flags(tmp_path: Path) -> None:
    screenshot_path = _create_local_image(
        tmp_path / "visuals" / "local-screenshot.png",
        color=(160, 40, 40),
        size=(1600, 900),
    )
    report_path = _write_preview_report(tmp_path, screenshot_ref=str(screenshot_path))

    result = export_video_offer_artifacts(report_path, output_dir=tmp_path / "exports" / "default")

    assert result.renderer_input_json_path is None
    assert result.renderer_input_staged_json_path is None
    assert result.staged_visuals_dir_path is None
    assert result.scene_previews_dir_path is None
    assert result.staged_scene_count is None
    assert result.staged_visual_count is None
    assert not (tmp_path / "exports" / "default" / "renderer_input.json").exists()
    assert not (tmp_path / "exports" / "default" / "renderer_input_staged.json").exists()
    assert not (tmp_path / "exports" / "default" / "staged_visuals").exists()


def test_cli_stage_visuals_flag_wires_optional_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    remote_url = "https://cdn.example.com/cli-stage-hero.png"
    report_path = _write_preview_report(tmp_path, screenshot_ref=remote_url)

    def fake_urlopen(request, timeout: int) -> FakeResponse:
        return FakeResponse(
            _png_bytes(),
            content_type="image/png",
            content_length=len(_png_bytes()),
        )

    import dealbot.video.visual_staging as visual_staging

    monkeypatch.setattr(visual_staging.urllib.request, "urlopen", fake_urlopen)

    exit_code = export_video_offer_artifacts_main(
        ["--from-report", str(report_path), "--output-dir", str(tmp_path / "cli-exports"), "--stage-visuals"],
    )
    stdout = capsys.readouterr().out

    assert exit_code == 0
    assert "renderer_input_json_path:" in stdout
    assert "renderer_input_staged_json_path:" in stdout
    assert "staged_visuals_dir_path:" in stdout
    assert "staged_scene_count: 3" in stdout
    assert "staged_visual_count: 1" in stdout
    assert (tmp_path / "cli-exports" / "renderer_input_staged.json").exists()


def test_visual_staging_keeps_preview_renderer_strict_about_raw_remote_urls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote_url = "https://cdn.example.com/raw-remote-hero.png"
    renderer_input, _ = _build_renderer_input_fixture(tmp_path, screenshot_ref=remote_url)
    monkeypatch.setenv("YOTO_SCENE_PREVIEW_FONT_PATH", str(_copy_test_font(tmp_path)))

    with pytest.raises(ScenePreviewRenderError) as excinfo:
        render_scene_previews(renderer_input, tmp_path / "scene_previews")

    assert "remote visual URLs are not allowed" in str(excinfo.value)


def test_visual_staging_does_not_import_old_video_generator_network_or_steam_clients(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote_url = "https://cdn.example.com/no-extra-imports.png"
    renderer_input, _ = _build_renderer_input_fixture(tmp_path, screenshot_ref=remote_url)

    def fake_urlopen(request, timeout: int) -> FakeResponse:
        return FakeResponse(
            _png_bytes(),
            content_type="image/png",
            content_length=len(_png_bytes()),
        )

    import dealbot.video.visual_staging as visual_staging

    monkeypatch.setattr(visual_staging.urllib.request, "urlopen", fake_urlopen)
    before_modules = {
        name
        for name in sys.modules
        if name == "video_generator"
        or name.startswith("video_generator.")
        or name == "httpx"
        or name.startswith("httpx.")
        or name == "telegram"
        or name.startswith("telegram.")
        or name == "ffmpeg"
        or name.startswith("ffmpeg.")
        or name == "infrastructure.clients.steam_client"
        or name.startswith("infrastructure.clients.steam_client.")
    }

    stage_renderer_visuals(renderer_input, tmp_path / "exports")

    after_modules = {
        name
        for name in sys.modules
        if name == "video_generator"
        or name.startswith("video_generator.")
        or name == "httpx"
        or name.startswith("httpx.")
        or name == "telegram"
        or name.startswith("telegram.")
        or name == "ffmpeg"
        or name.startswith("ffmpeg.")
        or name == "infrastructure.clients.steam_client"
        or name.startswith("infrastructure.clients.steam_client.")
    }
    assert after_modules == before_modules
