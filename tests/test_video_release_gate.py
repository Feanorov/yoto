from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from dealbot.video import (
    build_video_release_gate_report,
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
SCENE_DURATIONS = [2.0, 2.5, 3.0, 3.0, 4.0]
SCENE_STARTS = [0.0, 2.0, 4.5, 7.5, 10.5]


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
    font_path = tmp_path / "fonts" / "video-release-gate-test-font.ttf"
    font_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_find_font_source(), font_path)
    return font_path


def _create_local_image(path: Path, *, color: tuple[int, int, int], size: tuple[int, int]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, format="PNG")
    return path


def _write_video_file(path: Path, *, size_bytes: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"v" * size_bytes)
    return path


def _scene_text_blocks(scene_id: str, *, cta_text: str = "See full deal in Telegram") -> list[dict]:
    if scene_id == "hook":
        return [{"role": "headline", "text": "Big Steam Deal", "priority": 1}]
    if scene_id == "identity":
        return [{"role": "title", "text": "Release Gate Test Game", "priority": 1}]
    if scene_id == "offer_proof":
        return [{"role": "offer_badge", "text": "-50%", "priority": 1}]
    if scene_id == "trust_or_deadline":
        return [{"role": "deadline", "text": "Ends soon", "priority": 1}]
    return [{"role": "cta", "text": cta_text, "priority": 1}]


def _build_renderer_input(
    tmp_path: Path,
    *,
    canvas: tuple[int, int] = (1080, 1920),
    fps: int = 30,
    cta_text: str = "See full deal in Telegram",
) -> tuple[dict, Path]:
    colors = [
        (210, 60, 70),
        (60, 110, 210),
        (90, 150, 80),
        (140, 100, 210),
        (240, 180, 70),
    ]
    scene_previews_dir = tmp_path / "scene_previews"
    scenes: list[dict] = []

    for index, scene_id in enumerate(SCENE_IDS, start=1):
        visual_path = _create_local_image(
            tmp_path / "visuals" / f"{scene_id}.png",
            color=colors[index - 1],
            size=canvas,
        )
        _create_local_image(
            scene_previews_dir / f"{index:02d}_{scene_id}.png",
            color=colors[index - 1],
            size=(1080, 1920),
        )
        start_sec = SCENE_STARTS[index - 1]
        duration_sec = SCENE_DURATIONS[index - 1]
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
                    "asset_ref": str(visual_path),
                },
                "text_blocks": _scene_text_blocks(scene_id, cta_text=cta_text),
                "safe_zone_profile": "upper_middle_center",
                "motion": {"hint": "hold"},
                "warnings": [],
            }
        )

    return (
        {
            "schema_version": 1,
            "offer_id": "steam:video-release-gate",
            "template": "single_offer_gameplay_first",
            "format": "vertical_1080x1920",
            "canvas": {"width": canvas[0], "height": canvas[1]},
            "total_duration_sec": 14.5,
            "fps": fps,
            "voice_mode": "none",
            "music_required": True,
            "scenes": scenes,
            "warnings": [],
        },
        scene_previews_dir,
    )


def _build_scene_visual_qa_report(
    *,
    status: str = "pass",
    findings: list[dict] | None = None,
    duplicate_visual_groups: list[dict] | None = None,
    error_count: int | None = None,
    warning_count: int | None = None,
) -> dict:
    findings = findings or []
    computed_error_count = sum(1 for finding in findings if finding.get("severity") == "error")
    computed_warning_count = sum(1 for finding in findings if finding.get("severity") == "warning")
    return {
        "schema_version": 1,
        "offer_id": "steam:video-release-gate",
        "status": status,
        "error_count": computed_error_count if error_count is None else error_count,
        "warning_count": computed_warning_count if warning_count is None else warning_count,
        "findings": findings,
        "duplicate_visual_groups": duplicate_visual_groups or [],
        "scenes": [],
    }


def _build_assembly_manifest(
    scene_previews_dir: Path,
    *,
    total_duration_sec: float = 14.5,
    scene_count: int = 5,
    audio_present: bool = True,
) -> dict:
    scenes: list[dict] = []
    for index, scene_id in enumerate(SCENE_IDS[:scene_count], start=1):
        scenes.append(
            {
                "scene_id": scene_id,
                "order": index,
                "duration_sec": SCENE_DURATIONS[index - 1],
                "preview_png_path": str((scene_previews_dir / f"{index:02d}_{scene_id}.png").resolve()),
                "width": 1080,
                "height": 1920,
            }
        )

    return {
        "schema_version": 1,
        "status": "assembled",
        "offer_id": "steam:video-release-gate",
        "template": "single_offer_gameplay_first",
        "canvas": {"width": 1080, "height": 1920},
        "fps": 30,
        "scene_count": scene_count,
        "total_duration_sec": total_duration_sec,
        "scene_previews_dir_path": str(scene_previews_dir.resolve()),
        "video_preview_mp4_path": str((scene_previews_dir.parent / "video_preview.mp4").resolve()),
        "ffmpeg_bin": r"C:\ffmpeg\bin\ffmpeg.exe",
        "ffmpeg_command": [r"C:\ffmpeg\bin\ffmpeg.exe", "-y", str((scene_previews_dir.parent / "video_preview.mp4").resolve())],
        "audio_present": audio_present,
        "scenes": scenes,
    }


def _build_preview_report_payload(*, card_path: Path, screenshot_path: Path) -> dict:
    candidate = {
        "title": "Release Gate Preview Game",
        "offer_id": "steam:video-release-gate-preview",
        "source": "steam",
        "platform": "steam",
        "store_url": "https://store.steampowered.com/app/90",
        "discount": 50,
        "current_price": 14900,
        "old_price": 29900,
        "reviews": 42000,
        "positive_pct": 94,
    }
    artifact = {
        "offer_id": "steam:video-release-gate-preview",
        "caption_html": "<b>Release Gate Preview Game</b>",
        "caption_hash": "release-gate-caption-hash",
        "image_hash": "release-gate-image-hash",
        "idempotency_key": "release-gate-key",
        "image_path": str(card_path),
        "assets_used": [str(screenshot_path)],
        "render_diagnostics": {},
        "card_family": "DISCOUNT",
        "template_id": "steam_discount",
    }
    offer_snapshot = {
        "offer_id": "steam:video-release-gate-preview",
        "source": "steam",
        "title": "Release Gate Preview Game",
        "store_url": "https://store.steampowered.com/app/90",
        "currency": "UAH",
        "price_after_minor": 14900,
        "price_before_minor": 29900,
        "discount_percent": 50,
        "promo_end": "2026-07-05T20:00:00",
        "review_score": 94,
        "review_count": 42000,
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
        "run_key": "20260705T210000Z",
        "created_at": "2026-07-05T21:00:00",
        "send_test_target": {
            "candidate": dict(candidate),
            "artifact": dict(artifact),
        },
        "pinned_publish": {
            "contract_version": 1,
            "source": "preview",
            "created_at": "2026-07-05T21:00:00",
            "report_run_key": "20260705T210000Z",
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


def _write_preview_report(tmp_path: Path) -> Path:
    screenshot_path = _create_local_image(
        tmp_path / "visuals" / "local-screenshot.png",
        color=(160, 40, 40),
        size=(1080, 1920),
    )
    card_path = _create_local_image(
        tmp_path / "visuals" / "local-card.png",
        color=(40, 70, 170),
        size=(1080, 1920),
    )
    report_path = tmp_path / "output" / "analytics" / "video-release-gate-preview.json"
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


def test_pass_verdict_for_clean_valid_input(tmp_path: Path) -> None:
    renderer_input, scene_previews_dir = _build_renderer_input(tmp_path)
    qa_report = _build_scene_visual_qa_report()
    assembly_manifest = _build_assembly_manifest(scene_previews_dir)
    video_path = _write_video_file(tmp_path / "video_preview.mp4", size_bytes=200_000)

    report = build_video_release_gate_report(renderer_input, qa_report, assembly_manifest, video_path)

    assert report["verdict"] == "pass"
    assert report["block_reasons"] == []
    assert report["warnings"] == []
    assert report["scene_count"] == 5
    assert report["total_duration_sec"] == 14.5
    assert report["video_file_size_bytes"] == 200_000
    assert report["production_ready"] is False
    assert len(report["checked_files"]) == 6


def test_warn_verdict_for_visual_qa_warnings(tmp_path: Path) -> None:
    renderer_input, scene_previews_dir = _build_renderer_input(tmp_path)
    qa_report = _build_scene_visual_qa_report(
        status="warn",
        findings=[
            {
                "severity": "warning",
                "code": "duplicate_visual_reuse",
                "message": "Visual is reused across scenes.",
            },
            {
                "severity": "warning",
                "code": "source_image_aspect_ratio_risk",
                "message": "Source image aspect ratio differs from target.",
            },
        ],
        duplicate_visual_groups=[{"asset_ref": "shared.png", "scene_ids": ["hook", "identity"], "orders": [1, 2]}],
    )
    assembly_manifest = _build_assembly_manifest(scene_previews_dir)
    video_path = _write_video_file(tmp_path / "video_preview.mp4", size_bytes=200_000)

    report = build_video_release_gate_report(renderer_input, qa_report, assembly_manifest, video_path)

    assert report["verdict"] == "warn"
    assert report["block_reasons"] == []
    assert "Visual QA report verdict is warn." in report["warnings"]
    assert "Visual QA reported duplicate visual reuse across scenes." in report["warnings"]
    assert "Visual QA reported source image aspect ratio risk." in report["warnings"]


def test_block_verdict_for_missing_mp4(tmp_path: Path) -> None:
    renderer_input, scene_previews_dir = _build_renderer_input(tmp_path)
    qa_report = _build_scene_visual_qa_report()
    assembly_manifest = _build_assembly_manifest(scene_previews_dir)

    report = build_video_release_gate_report(
        renderer_input,
        qa_report,
        assembly_manifest,
        tmp_path / "missing-video_preview.mp4",
    )

    assert report["verdict"] == "block"
    assert any("Missing video preview MP4" in reason for reason in report["block_reasons"])


def test_block_verdict_for_zero_byte_mp4(tmp_path: Path) -> None:
    renderer_input, scene_previews_dir = _build_renderer_input(tmp_path)
    qa_report = _build_scene_visual_qa_report()
    assembly_manifest = _build_assembly_manifest(scene_previews_dir)
    video_path = _write_video_file(tmp_path / "video_preview.mp4", size_bytes=0)

    report = build_video_release_gate_report(renderer_input, qa_report, assembly_manifest, video_path)

    assert report["verdict"] == "block"
    assert any("Video preview MP4 is empty" in reason for reason in report["block_reasons"])


def test_block_verdict_for_visual_qa_errors(tmp_path: Path) -> None:
    renderer_input, scene_previews_dir = _build_renderer_input(tmp_path)
    qa_report = _build_scene_visual_qa_report(
        status="fail",
        findings=[
            {
                "severity": "error",
                "code": "missing_visual_file",
                "message": "Local visual file does not exist.",
            }
        ],
    )
    assembly_manifest = _build_assembly_manifest(scene_previews_dir)
    video_path = _write_video_file(tmp_path / "video_preview.mp4", size_bytes=200_000)

    report = build_video_release_gate_report(renderer_input, qa_report, assembly_manifest, video_path)

    assert report["verdict"] == "block"
    assert "Visual QA reported 1 error(s)." in report["block_reasons"]


def test_block_verdict_for_duration_mismatch(tmp_path: Path) -> None:
    renderer_input, scene_previews_dir = _build_renderer_input(tmp_path)
    qa_report = _build_scene_visual_qa_report()
    assembly_manifest = _build_assembly_manifest(scene_previews_dir, total_duration_sec=12.0)
    video_path = _write_video_file(tmp_path / "video_preview.mp4", size_bytes=200_000)

    report = build_video_release_gate_report(renderer_input, qa_report, assembly_manifest, video_path)

    assert report["verdict"] == "block"
    assert "Assembly manifest total duration does not match renderer input total duration." in report["block_reasons"]


def test_block_verdict_for_wrong_scene_count(tmp_path: Path) -> None:
    renderer_input, scene_previews_dir = _build_renderer_input(tmp_path)
    qa_report = _build_scene_visual_qa_report()
    assembly_manifest = _build_assembly_manifest(scene_previews_dir, scene_count=4)
    video_path = _write_video_file(tmp_path / "video_preview.mp4", size_bytes=200_000)

    report = build_video_release_gate_report(renderer_input, qa_report, assembly_manifest, video_path)

    assert report["verdict"] == "block"
    assert any("Assembly manifest references 4 scene previews" in reason for reason in report["block_reasons"])


def test_block_verdict_for_wrong_canvas_and_fps(tmp_path: Path) -> None:
    renderer_input, scene_previews_dir = _build_renderer_input(tmp_path, canvas=(720, 1280), fps=24)
    qa_report = _build_scene_visual_qa_report()
    assembly_manifest = _build_assembly_manifest(scene_previews_dir)
    video_path = _write_video_file(tmp_path / "video_preview.mp4", size_bytes=200_000)

    report = build_video_release_gate_report(renderer_input, qa_report, assembly_manifest, video_path)

    assert report["verdict"] == "block"
    assert "Renderer input canvas must be 1080x1920." in report["block_reasons"]
    assert "Renderer input fps must be 30." in report["block_reasons"]


def test_cta_missing_text_blocks(tmp_path: Path) -> None:
    renderer_input, scene_previews_dir = _build_renderer_input(tmp_path, cta_text="   ")
    qa_report = _build_scene_visual_qa_report()
    assembly_manifest = _build_assembly_manifest(scene_previews_dir)
    video_path = _write_video_file(tmp_path / "video_preview.mp4", size_bytes=200_000)

    report = build_video_release_gate_report(renderer_input, qa_report, assembly_manifest, video_path)

    assert report["verdict"] == "block"
    assert "CTA scene is missing CTA text." in report["block_reasons"]


def test_exporter_writes_release_gate_report_only_with_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_path = _write_preview_report(tmp_path)
    monkeypatch.setenv("YOTO_SCENE_PREVIEW_FONT_PATH", str(_copy_test_font(tmp_path)))
    ffmpeg_path = Path(r"C:\ffmpeg\bin\ffmpeg.exe")

    def fake_run(command, check, capture_output, text):
        output_path = Path(command[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"m" * 200_000)
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    import dealbot.video.mp4_assembler as mp4_assembler

    monkeypatch.setattr(mp4_assembler, "_resolve_ffmpeg_binary", lambda: ffmpeg_path)
    monkeypatch.setattr(mp4_assembler.subprocess, "run", fake_run)

    default_result = export_video_offer_artifacts(report_path, output_dir=tmp_path / "exports" / "default")
    gate_result = export_video_offer_artifacts(
        report_path,
        output_dir=tmp_path / "exports" / "release-gated",
        with_release_gate=True,
    )
    gate_report = json.loads(gate_result.video_release_gate_report_json_path.read_text(encoding="utf-8"))

    assert default_result.video_release_gate_report_json_path is None
    assert default_result.release_gate_verdict is None
    assert default_result.release_gate_block_reason_count is None
    assert default_result.release_gate_warning_count is None
    assert not (tmp_path / "exports" / "default" / "video_release_gate_report.json").exists()

    assert gate_result.renderer_input_json_path is not None
    assert gate_result.renderer_input_staged_json_path is not None
    assert gate_result.scene_visual_qa_report_json_path is not None
    assert gate_result.scene_previews_dir_path is not None
    assert gate_result.video_preview_mp4_path is not None
    assert gate_result.video_assembly_manifest_json_path is not None
    assert gate_result.video_release_gate_report_json_path is not None
    assert gate_result.video_release_gate_report_json_path.exists()
    assert gate_result.release_gate_verdict == "warn"
    assert gate_report["verdict"] == "warn"
    assert gate_report["production_ready"] is False


def test_cli_with_release_gate_flag_wires_optional_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    report_path = _write_preview_report(tmp_path)
    monkeypatch.setenv("YOTO_SCENE_PREVIEW_FONT_PATH", str(_copy_test_font(tmp_path)))
    ffmpeg_path = Path(r"C:\ffmpeg\bin\ffmpeg.exe")

    def fake_run(command, check, capture_output, text):
        output_path = Path(command[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"m" * 200_000)
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    import dealbot.video.mp4_assembler as mp4_assembler

    monkeypatch.setattr(mp4_assembler, "_resolve_ffmpeg_binary", lambda: ffmpeg_path)
    monkeypatch.setattr(mp4_assembler.subprocess, "run", fake_run)

    exit_code = export_video_offer_artifacts_main(
        ["--from-report", str(report_path), "--output-dir", str(tmp_path / "cli-release-gate"), "--with-release-gate"],
    )
    stdout = capsys.readouterr().out

    assert exit_code == 0
    assert "video_preview_mp4_path:" in stdout
    assert "video_assembly_manifest_json_path:" in stdout
    assert "video_release_gate_report_json_path:" in stdout
    assert "release_gate_verdict: warn" in stdout
    assert (tmp_path / "cli-release-gate" / "video_release_gate_report.json").exists()


def test_release_gate_does_not_import_old_video_generator_network_telegram_or_ui_modules(
    tmp_path: Path,
) -> None:
    renderer_input, scene_previews_dir = _build_renderer_input(tmp_path)
    qa_report = _build_scene_visual_qa_report()
    assembly_manifest = _build_assembly_manifest(scene_previews_dir)
    video_path = _write_video_file(tmp_path / "video_preview.mp4", size_bytes=200_000)
    before_modules = {
        name
        for name in sys.modules
        if name == "video_generator"
        or name.startswith("video_generator.")
        or name == "httpx"
        or name.startswith("httpx.")
        or name == "telegram"
        or name.startswith("telegram.")
        or name == "PySide6"
        or name.startswith("PySide6.")
        or name == "infrastructure.clients.steam_client"
        or name.startswith("infrastructure.clients.steam_client.")
    }

    build_video_release_gate_report(renderer_input, qa_report, assembly_manifest, video_path)

    after_modules = {
        name
        for name in sys.modules
        if name == "video_generator"
        or name.startswith("video_generator.")
        or name == "httpx"
        or name.startswith("httpx.")
        or name == "telegram"
        or name.startswith("telegram.")
        or name == "PySide6"
        or name.startswith("PySide6.")
        or name == "infrastructure.clients.steam_client"
        or name.startswith("infrastructure.clients.steam_client.")
    }
    assert after_modules == before_modules
