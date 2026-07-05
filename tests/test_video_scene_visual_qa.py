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
    build_scene_visual_qa_report,
    export_video_offer_artifacts,
)
from tools.export_video_offer_artifacts import main as export_video_offer_artifacts_main


SCENE_IDS = [
    "hook",
    "identity",
    "offer_proof",
    "trust_or_deadline",
    "telegram_cta",
]


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
    font_path = tmp_path / "fonts" / "scene-visual-qa-test-font.ttf"
    font_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_find_font_source(), font_path)
    return font_path


def _create_local_image(path: Path, *, color: tuple[int, int, int], size: tuple[int, int]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, format="PNG")
    return path


def _png_bytes(*, color: tuple[int, int, int] = (210, 60, 70), size: tuple[int, int] = (1080, 1920)) -> bytes:
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


def _scene_text_blocks(scene_id: str) -> list[dict]:
    if scene_id == "hook":
        return [{"role": "headline", "text": "Big Steam Deal", "priority": 1}]
    if scene_id == "identity":
        return [{"role": "title", "text": "QA Test Game", "priority": 1}]
    if scene_id == "offer_proof":
        return [{"role": "offer_badge", "text": "-50%", "priority": 1}]
    if scene_id == "trust_or_deadline":
        return [{"role": "deadline", "text": "Ends soon", "priority": 1}]
    return [{"role": "cta", "text": "See full deal in Telegram", "priority": 1}]


def _build_renderer_input(tmp_path: Path) -> tuple[dict, dict[str, Path]]:
    image_specs = {
        "hook": ((210, 60, 70), (1080, 1920)),
        "identity": ((60, 110, 210), (1080, 1920)),
        "offer_proof": ((90, 150, 80), (1080, 1920)),
        "trust_or_deadline": ((140, 100, 210), (1080, 1920)),
        "telegram_cta": ((240, 180, 70), (1080, 1920)),
    }
    visuals: dict[str, Path] = {}
    scenes: list[dict] = []
    start_points = [0.0, 2.0, 4.5, 7.5, 10.5]
    durations = [2.0, 2.5, 3.0, 3.0, 4.0]

    for index, scene_id in enumerate(SCENE_IDS, start=1):
        color, size = image_specs[scene_id]
        image_path = _create_local_image(
            tmp_path / "visuals" / f"{scene_id}.png",
            color=color,
            size=size,
        )
        visuals[scene_id] = image_path
        start_sec = start_points[index - 1]
        duration_sec = durations[index - 1]
        scenes.append(
            {
                "scene_id": scene_id,
                "order": index,
                "scene_type": f"{scene_id}_type",
                "start_sec": start_sec,
                "end_sec": round(start_sec + duration_sec, 3),
                "duration_sec": duration_sec,
                "visual": {
                    "asset_type": "screenshot",
                    "asset_ref": str(image_path),
                },
                "text_blocks": _scene_text_blocks(scene_id),
                "safe_zone_profile": "upper_middle_center",
                "motion": {"hint": "hold"},
                "warnings": [],
            }
        )

    return (
        {
            "schema_version": 1,
            "offer_id": "steam:scene-visual-qa",
            "template": "single_offer_gameplay_first",
            "format": "vertical_1080x1920",
            "canvas": {"width": 1080, "height": 1920},
            "total_duration_sec": 14.5,
            "fps": 30,
            "voice_mode": "none",
            "music_required": True,
            "scenes": scenes,
            "warnings": [],
        },
        visuals,
    )


def _build_preview_report_payload(*, card_path: Path, screenshot_ref: str) -> dict:
    candidate = {
        "title": "Scene Visual QA Preview Game",
        "offer_id": "steam:scene-visual-qa-preview",
        "source": "steam",
        "platform": "steam",
        "store_url": "https://store.steampowered.com/app/70",
        "discount": 50,
        "current_price": 14900,
        "old_price": 29900,
        "reviews": 42000,
        "positive_pct": 94,
    }
    artifact = {
        "offer_id": "steam:scene-visual-qa-preview",
        "caption_html": "<b>Scene Visual QA Preview Game</b>",
        "caption_hash": "scene-visual-qa-caption-hash",
        "image_hash": "scene-visual-qa-image-hash",
        "idempotency_key": "scene-visual-qa-key",
        "image_path": str(card_path),
        "assets_used": [screenshot_ref],
        "render_diagnostics": {},
        "card_family": "DISCOUNT",
        "template_id": "steam_discount",
    }
    offer_snapshot = {
        "offer_id": "steam:scene-visual-qa-preview",
        "source": "steam",
        "title": "Scene Visual QA Preview Game",
        "store_url": "https://store.steampowered.com/app/70",
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
            "official_trailers": [],
            "official_screenshots": [screenshot_ref],
        },
    }
    return {
        "run_key": "20260705T190000Z",
        "created_at": "2026-07-05T19:00:00",
        "send_test_target": {
            "candidate": dict(candidate),
            "artifact": dict(artifact),
        },
        "pinned_publish": {
            "contract_version": 1,
            "source": "preview",
            "created_at": "2026-07-05T19:00:00",
            "report_run_key": "20260705T190000Z",
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


def _write_preview_report(tmp_path: Path, *, screenshot_ref: str) -> Path:
    card_path = _create_local_image(
        tmp_path / "visuals" / "local-card.png",
        color=(40, 70, 170),
        size=(1200, 1200),
    )
    report_path = tmp_path / "output" / "analytics" / "scene-visual-qa-preview.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            _build_preview_report_payload(card_path=card_path, screenshot_ref=screenshot_ref),
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


def _has_finding(report: dict, code: str) -> bool:
    return any(finding["code"] == code for finding in report["findings"])


def test_clean_staged_input_produces_report(tmp_path: Path) -> None:
    renderer_input, _ = _build_renderer_input(tmp_path)

    report = build_scene_visual_qa_report(renderer_input)

    assert report["status"] == "pass"
    assert report["scene_count"] == 5
    assert report["error_count"] == 0
    assert report["warning_count"] == 0
    assert len(report["scenes"]) == 5


def test_duplicate_visual_reuse_is_reported(tmp_path: Path) -> None:
    renderer_input, visuals = _build_renderer_input(tmp_path)
    shared_path = str(visuals["hook"])
    _scene(renderer_input, "identity")["visual"]["asset_ref"] = shared_path

    report = build_scene_visual_qa_report(renderer_input)

    assert _has_finding(report, "duplicate_visual_reuse")


def test_remote_url_is_reported(tmp_path: Path) -> None:
    renderer_input, _ = _build_renderer_input(tmp_path)
    _scene(renderer_input, "hook")["visual"]["asset_ref"] = "https://cdn.example.com/remote-scene.png"

    report = build_scene_visual_qa_report(renderer_input)

    assert _has_finding(report, "remote_visual_url")


def test_missing_local_file_is_reported(tmp_path: Path) -> None:
    renderer_input, _ = _build_renderer_input(tmp_path)
    _scene(renderer_input, "hook")["visual"]["asset_ref"] = str(tmp_path / "missing-scene.png")

    report = build_scene_visual_qa_report(renderer_input)

    assert _has_finding(report, "missing_visual_file")


def test_small_image_is_reported(tmp_path: Path) -> None:
    renderer_input, _ = _build_renderer_input(tmp_path)
    small_path = _create_local_image(
        tmp_path / "visuals" / "small-scene.png",
        color=(20, 40, 60),
        size=(640, 640),
    )
    _scene(renderer_input, "hook")["visual"]["asset_ref"] = str(small_path)

    report = build_scene_visual_qa_report(renderer_input)

    assert _has_finding(report, "source_image_very_small")


def test_aspect_ratio_risk_is_reported(tmp_path: Path) -> None:
    renderer_input, _ = _build_renderer_input(tmp_path)
    wide_path = _create_local_image(
        tmp_path / "visuals" / "wide-scene.png",
        color=(20, 40, 60),
        size=(1600, 900),
    )
    _scene(renderer_input, "hook")["visual"]["asset_ref"] = str(wide_path)

    report = build_scene_visual_qa_report(renderer_input)

    assert _has_finding(report, "source_image_aspect_ratio_risk")


def test_cta_missing_text_is_reported(tmp_path: Path) -> None:
    renderer_input, _ = _build_renderer_input(tmp_path)
    _scene(renderer_input, "telegram_cta")["text_blocks"] = [{"role": "cta", "text": "   ", "priority": 1}]

    report = build_scene_visual_qa_report(renderer_input)

    assert _has_finding(report, "cta_text_missing")


def test_preview_export_writes_qa_report_using_staged_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote_url = "https://cdn.example.com/scene-visual-qa-stage.png"
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
    qa_report = json.loads(result.scene_visual_qa_report_json_path.read_text(encoding="utf-8"))
    raw_renderer_input = json.loads(result.renderer_input_json_path.read_text(encoding="utf-8"))

    assert result.scene_visual_qa_report_json_path == (
        tmp_path / "exports" / "previews" / "scene_visual_qa_report.json"
    ).resolve()
    assert result.scene_visual_qa_report_json_path.exists()
    assert result.visual_qa_status in {"warn", "pass"}
    assert _scene(raw_renderer_input, "hook")["visual"]["asset_ref"] == remote_url
    assert not _has_finding(qa_report, "remote_visual_url")


def test_default_exporter_behavior_remains_unchanged_without_visual_qa_flag(tmp_path: Path) -> None:
    screenshot_path = _create_local_image(
        tmp_path / "visuals" / "local-screenshot.png",
        color=(160, 40, 40),
        size=(1080, 1920),
    )
    report_path = _write_preview_report(tmp_path, screenshot_ref=str(screenshot_path))

    result = export_video_offer_artifacts(report_path, output_dir=tmp_path / "exports" / "default")

    assert result.scene_visual_qa_report_json_path is None
    assert result.visual_qa_status is None
    assert result.visual_qa_error_count is None
    assert result.visual_qa_warning_count is None
    assert not (tmp_path / "exports" / "default" / "scene_visual_qa_report.json").exists()


def test_visual_qa_does_not_import_old_video_generator_network_or_steam_clients(tmp_path: Path) -> None:
    renderer_input, _ = _build_renderer_input(tmp_path)
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

    build_scene_visual_qa_report(renderer_input)

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


def test_cli_with_visual_qa_report_flag_wires_optional_export(
    tmp_path: Path,
    capsys,
) -> None:
    screenshot_path = _create_local_image(
        tmp_path / "visuals" / "local-screenshot.png",
        color=(160, 40, 40),
        size=(1080, 1920),
    )
    report_path = _write_preview_report(tmp_path, screenshot_ref=str(screenshot_path))

    exit_code = export_video_offer_artifacts_main(
        ["--from-report", str(report_path), "--output-dir", str(tmp_path / "cli-exports"), "--with-visual-qa-report"],
    )
    stdout = capsys.readouterr().out

    assert exit_code == 0
    assert "renderer_input_json_path:" in stdout
    assert "scene_visual_qa_report_json_path:" in stdout
    assert "visual_qa_status: warn" not in stdout or "visual_qa_status:" in stdout
    assert "visual_qa_error_count:" in stdout
    assert "visual_qa_warning_count:" in stdout
    assert (tmp_path / "cli-exports" / "scene_visual_qa_report.json").exists()
