from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from dealbot.video import (
    MP4AssemblerError,
    assemble_scene_previews_mp4,
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
    font_path = tmp_path / "fonts" / "video-mp4-assembler-test-font.ttf"
    font_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_find_font_source(), font_path)
    return font_path


def _create_local_image(path: Path, *, color: tuple[int, int, int], size: tuple[int, int]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, format="PNG")
    return path


def _build_renderer_input(tmp_path: Path) -> tuple[dict, Path]:
    scene_previews_dir = tmp_path / "scene_previews"
    colors = [
        (210, 60, 70),
        (60, 110, 210),
        (90, 150, 80),
        (140, 100, 210),
        (240, 180, 70),
    ]
    scenes: list[dict] = []

    for index, scene_id in enumerate(SCENE_IDS, start=1):
        preview_path = _create_local_image(
            scene_previews_dir / f"{index:02d}_{scene_id}.png",
            color=colors[index - 1],
            size=(1080, 1920),
        )
        scenes.append(
            {
                "scene_id": scene_id,
                "order": index,
                "scene_type": f"{scene_id}_type",
                "start_sec": SCENE_STARTS[index - 1],
                "end_sec": round(SCENE_STARTS[index - 1] + SCENE_DURATIONS[index - 1], 3),
                "duration_sec": SCENE_DURATIONS[index - 1],
                "visual": {
                    "asset_type": "screenshot",
                    "asset_ref": str(preview_path),
                },
                "text_blocks": [{"role": "headline", "text": scene_id, "priority": 1}],
                "safe_zone_profile": "upper_middle_center",
                "motion": {"hint": "hold"},
                "warnings": [],
            }
        )

    return (
        {
            "schema_version": 1,
            "offer_id": "steam:mp4-assembler-test",
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
        scene_previews_dir,
    )


def _build_preview_report_payload(*, card_path: Path, screenshot_path: Path) -> dict:
    candidate = {
        "title": "MP4 Assembler Test Game",
        "offer_id": "steam:mp4-assembler-preview",
        "source": "steam",
        "platform": "steam",
        "store_url": "https://store.steampowered.com/app/80",
        "discount": 50,
        "current_price": 14900,
        "old_price": 29900,
        "reviews": 42000,
        "positive_pct": 94,
    }
    artifact = {
        "offer_id": "steam:mp4-assembler-preview",
        "caption_html": "<b>MP4 Assembler Test Game</b>",
        "caption_hash": "mp4-assembler-caption-hash",
        "image_hash": "mp4-assembler-image-hash",
        "idempotency_key": "mp4-assembler-key",
        "image_path": str(card_path),
        "assets_used": [str(screenshot_path)],
        "render_diagnostics": {},
        "card_family": "DISCOUNT",
        "template_id": "steam_discount",
    }
    offer_snapshot = {
        "offer_id": "steam:mp4-assembler-preview",
        "source": "steam",
        "title": "MP4 Assembler Test Game",
        "store_url": "https://store.steampowered.com/app/80",
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
        "run_key": "20260705T200000Z",
        "created_at": "2026-07-05T20:00:00",
        "send_test_target": {
            "candidate": dict(candidate),
            "artifact": dict(artifact),
        },
        "pinned_publish": {
            "contract_version": 1,
            "source": "preview",
            "created_at": "2026-07-05T20:00:00",
            "report_run_key": "20260705T200000Z",
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
        size=(1600, 900),
    )
    card_path = _create_local_image(
        tmp_path / "visuals" / "local-card.png",
        color=(40, 70, 170),
        size=(1200, 1200),
    )
    report_path = tmp_path / "output" / "analytics" / "video-mp4-assembler-preview.json"
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


def test_validates_five_scenes(tmp_path: Path) -> None:
    renderer_input, scene_previews_dir = _build_renderer_input(tmp_path)
    renderer_input["scenes"] = renderer_input["scenes"][:-1]

    with pytest.raises(MP4AssemblerError) as excinfo:
        assemble_scene_previews_mp4(renderer_input, scene_previews_dir, tmp_path / "exports")

    assert "exactly 5 scenes" in str(excinfo.value)


def test_validates_preview_png_existence(tmp_path: Path) -> None:
    renderer_input, scene_previews_dir = _build_renderer_input(tmp_path)
    (scene_previews_dir / "03_offer_proof.png").unlink()

    with pytest.raises(MP4AssemblerError) as excinfo:
        assemble_scene_previews_mp4(renderer_input, scene_previews_dir, tmp_path / "exports")

    assert "expected scene preview PNG is missing" in str(excinfo.value)


def test_validates_preview_png_size(tmp_path: Path) -> None:
    renderer_input, scene_previews_dir = _build_renderer_input(tmp_path)
    _create_local_image(
        scene_previews_dir / "01_hook.png",
        color=(20, 40, 60),
        size=(720, 1280),
    )

    with pytest.raises(MP4AssemblerError) as excinfo:
        assemble_scene_previews_mp4(renderer_input, scene_previews_dir, tmp_path / "exports")

    assert "must be 1080x1920" in str(excinfo.value)


def test_builds_deterministic_ffmpeg_command_and_writes_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer_input, scene_previews_dir = _build_renderer_input(tmp_path)
    ffmpeg_path = Path(r"C:\ffmpeg\bin\ffmpeg.exe")

    def fake_run(command, check, capture_output, text):
        output_path = Path(command[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-mp4-preview")
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    import dealbot.video.mp4_assembler as mp4_assembler

    monkeypatch.setattr(mp4_assembler, "_resolve_ffmpeg_binary", lambda: ffmpeg_path)
    monkeypatch.setattr(mp4_assembler.subprocess, "run", fake_run)

    manifest = assemble_scene_previews_mp4(renderer_input, scene_previews_dir, tmp_path / "exports")
    manifest_path = tmp_path / "exports" / "video_assembly_manifest.json"
    output_path = tmp_path / "exports" / "video_preview.mp4"

    assert output_path.exists()
    assert manifest_path.exists()
    assert manifest["video_preview_mp4_path"] == str(output_path.resolve())
    assert manifest["total_duration_sec"] == 14.5
    assert manifest["scenes"][0]["duration_sec"] == 2.0
    assert manifest["scenes"][-1]["duration_sec"] == 4.0
    assert manifest["ffmpeg_command"] == [
        str(ffmpeg_path),
        "-y",
        "-loop",
        "1",
        "-framerate",
        "30",
        "-t",
        "2",
        "-i",
        str((scene_previews_dir / "01_hook.png").resolve()),
        "-loop",
        "1",
        "-framerate",
        "30",
        "-t",
        "2.5",
        "-i",
        str((scene_previews_dir / "02_identity.png").resolve()),
        "-loop",
        "1",
        "-framerate",
        "30",
        "-t",
        "3",
        "-i",
        str((scene_previews_dir / "03_offer_proof.png").resolve()),
        "-loop",
        "1",
        "-framerate",
        "30",
        "-t",
        "3",
        "-i",
        str((scene_previews_dir / "04_trust_or_deadline.png").resolve()),
        "-loop",
        "1",
        "-framerate",
        "30",
        "-t",
        "4",
        "-i",
        str((scene_previews_dir / "05_telegram_cta.png").resolve()),
        "-filter_complex",
        "[0:v][1:v][2:v][3:v][4:v]concat=n=5:v=1:a=0,format=yuv420p[vout]",
        "-map",
        "[vout]",
        "-r",
        "30",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-an",
        str(output_path.resolve()),
    ]

    persisted_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert persisted_manifest["ffmpeg_command"] == manifest["ffmpeg_command"]


def test_missing_ffmpeg_fails_clearly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    renderer_input, scene_previews_dir = _build_renderer_input(tmp_path)

    import dealbot.video.mp4_assembler as mp4_assembler

    monkeypatch.setattr(mp4_assembler.shutil, "which", lambda _name: None)

    with pytest.raises(MP4AssemblerError) as excinfo:
        assemble_scene_previews_mp4(renderer_input, scene_previews_dir, tmp_path / "exports")

    assert "FFmpeg is not available on PATH" in str(excinfo.value)


def test_exporter_writes_mp4_only_with_assemble_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_path = _write_preview_report(tmp_path)
    monkeypatch.setenv("YOTO_SCENE_PREVIEW_FONT_PATH", str(_copy_test_font(tmp_path)))
    ffmpeg_path = Path(r"C:\ffmpeg\bin\ffmpeg.exe")

    def fake_run(command, check, capture_output, text):
        output_path = Path(command[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-mp4-preview")
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    import dealbot.video.mp4_assembler as mp4_assembler

    monkeypatch.setattr(mp4_assembler, "_resolve_ffmpeg_binary", lambda: ffmpeg_path)
    monkeypatch.setattr(mp4_assembler.subprocess, "run", fake_run)

    default_result = export_video_offer_artifacts(report_path, output_dir=tmp_path / "exports" / "default")
    assembled_result = export_video_offer_artifacts(
        report_path,
        output_dir=tmp_path / "exports" / "assembled",
        assemble_mp4_preview_flag=True,
    )

    assert default_result.video_preview_mp4_path is None
    assert default_result.video_assembly_manifest_json_path is None
    assert default_result.video_preview_duration_sec is None
    assert not (tmp_path / "exports" / "default" / "video_preview.mp4").exists()

    assert assembled_result.video_preview_mp4_path == (tmp_path / "exports" / "assembled" / "video_preview.mp4").resolve()
    assert assembled_result.video_assembly_manifest_json_path == (
        tmp_path / "exports" / "assembled" / "video_assembly_manifest.json"
    ).resolve()
    assert assembled_result.scene_previews_dir_path == (tmp_path / "exports" / "assembled" / "scene_previews").resolve()
    assert assembled_result.scene_visual_qa_report_json_path == (
        tmp_path / "exports" / "assembled" / "scene_visual_qa_report.json"
    ).resolve()
    assert assembled_result.video_preview_mp4_path.exists()
    assert assembled_result.video_assembly_manifest_json_path.exists()
    assert assembled_result.video_preview_duration_sec == 14.5


def test_cli_assemble_mp4_preview_flag_wires_optional_export(
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
        output_path.write_bytes(b"fake-mp4-preview")
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    import dealbot.video.mp4_assembler as mp4_assembler

    monkeypatch.setattr(mp4_assembler, "_resolve_ffmpeg_binary", lambda: ffmpeg_path)
    monkeypatch.setattr(mp4_assembler.subprocess, "run", fake_run)

    exit_code = export_video_offer_artifacts_main(
        ["--from-report", str(report_path), "--output-dir", str(tmp_path / "cli-assembled"), "--assemble-mp4-preview"],
    )
    stdout = capsys.readouterr().out

    assert exit_code == 0
    assert "renderer_input_json_path:" in stdout
    assert "renderer_input_staged_json_path:" in stdout
    assert "scene_visual_qa_report_json_path:" in stdout
    assert "scene_previews_dir_path:" in stdout
    assert "video_preview_mp4_path:" in stdout
    assert "video_assembly_manifest_json_path:" in stdout
    assert "video_preview_duration_sec: 14.5" in stdout
    assert (tmp_path / "cli-assembled" / "video_preview.mp4").exists()


def test_default_exporter_behavior_remains_unchanged_without_assemble_flag(tmp_path: Path) -> None:
    report_path = _write_preview_report(tmp_path)

    result = export_video_offer_artifacts(report_path, output_dir=tmp_path / "exports" / "default")

    assert result.video_preview_mp4_path is None
    assert result.video_assembly_manifest_json_path is None
    assert result.video_preview_duration_sec is None
    assert not (tmp_path / "exports" / "default" / "video_preview.mp4").exists()
    assert not (tmp_path / "exports" / "default" / "video_assembly_manifest.json").exists()


def test_mp4_assembler_does_not_import_old_video_generator_network_telegram_or_ui_modules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer_input, scene_previews_dir = _build_renderer_input(tmp_path)
    ffmpeg_path = Path(r"C:\ffmpeg\bin\ffmpeg.exe")

    def fake_run(command, check, capture_output, text):
        output_path = Path(command[-1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-mp4-preview")
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    import dealbot.video.mp4_assembler as mp4_assembler

    monkeypatch.setattr(mp4_assembler, "_resolve_ffmpeg_binary", lambda: ffmpeg_path)
    monkeypatch.setattr(mp4_assembler.subprocess, "run", fake_run)
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

    assemble_scene_previews_mp4(renderer_input, scene_previews_dir, tmp_path / "exports")

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
