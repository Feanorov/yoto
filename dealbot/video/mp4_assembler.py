from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from typing import Any


CANVAS = {"width": 1080, "height": 1920}
FPS = 30
EXPECTED_SCENES = (
    {"order": 1, "scene_id": "hook"},
    {"order": 2, "scene_id": "identity"},
    {"order": 3, "scene_id": "offer_proof"},
    {"order": 4, "scene_id": "trust_or_deadline"},
    {"order": 5, "scene_id": "telegram_cta"},
)


class MP4AssemblerError(ValueError):
    pass


def assemble_scene_previews_mp4(
    renderer_input: dict[str, Any],
    scene_previews_dir: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    if not isinstance(renderer_input, dict):
        raise MP4AssemblerError("MP4 assembly failed: renderer_input must be a dict.")

    scenes = _validated_scene_sequence(renderer_input)
    previews_dir_path = _resolve_dir(scene_previews_dir)
    output_dir_path = _resolve_dir(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    preview_entries = _validated_preview_entries(scenes, previews_dir_path)
    ffmpeg_path = _resolve_ffmpeg_binary()
    output_path = (output_dir_path / "video_preview.mp4").resolve()
    manifest_path = (output_dir_path / "video_assembly_manifest.json").resolve()
    command = _build_ffmpeg_command(ffmpeg_path, preview_entries, output_path)

    _run_ffmpeg(command)
    if not output_path.exists() or not output_path.is_file():
        raise MP4AssemblerError(
            f"MP4 assembly failed: FFmpeg did not create output video: {output_path}",
        )

    manifest = {
        "schema_version": 1,
        "status": "assembled",
        "offer_id": _pick_text(renderer_input.get("offer_id")),
        "template": _pick_text(renderer_input.get("template")),
        "canvas": dict(CANVAS),
        "fps": FPS,
        "scene_count": len(preview_entries),
        "total_duration_sec": round(sum(entry["duration_sec"] for entry in preview_entries), 3),
        "scene_previews_dir_path": str(previews_dir_path),
        "video_preview_mp4_path": str(output_path),
        "ffmpeg_bin": str(ffmpeg_path),
        "ffmpeg_command": command,
        "scenes": preview_entries,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _validated_scene_sequence(renderer_input: dict[str, Any]) -> list[dict[str, Any]]:
    raw_scenes = renderer_input.get("scenes")
    if not isinstance(raw_scenes, list):
        raise MP4AssemblerError("MP4 assembly failed: renderer_input.scenes must be a list.")
    if len(raw_scenes) != len(EXPECTED_SCENES):
        raise MP4AssemblerError(
            f"MP4 assembly failed: renderer_input must contain exactly {len(EXPECTED_SCENES)} scenes.",
        )

    scenes: list[dict[str, Any]] = []
    for expected, scene_payload in zip(EXPECTED_SCENES, raw_scenes, strict=True):
        if not isinstance(scene_payload, dict):
            raise MP4AssemblerError("MP4 assembly failed: renderer_input scenes must be dicts.")
        scene_id = _pick_text(scene_payload.get("scene_id"))
        order = _int_or_none(scene_payload.get("order"))
        if scene_id != expected["scene_id"]:
            raise MP4AssemblerError(
                f"MP4 assembly failed: expected scene_id={expected['scene_id']!r}, got {scene_id!r}.",
            )
        if order != expected["order"]:
            raise MP4AssemblerError(
                f"MP4 assembly failed: expected order={expected['order']} for scene_id={scene_id!r}.",
            )
        duration_sec = _float_or_none(scene_payload.get("duration_sec"))
        if duration_sec is None or duration_sec <= 0:
            raise MP4AssemblerError(
                f"MP4 assembly failed: duration_sec must be positive for scene_id={scene_id!r}.",
            )
        scenes.append(dict(scene_payload))
    return scenes


def _validated_preview_entries(
    scenes: list[dict[str, Any]],
    previews_dir_path: Path,
) -> list[dict[str, Any]]:
    if not previews_dir_path.exists() or not previews_dir_path.is_dir():
        raise MP4AssemblerError(
            f"MP4 assembly failed: scene previews directory does not exist: {previews_dir_path}",
        )

    preview_entries: list[dict[str, Any]] = []
    for scene_payload in scenes:
        scene_id = str(scene_payload["scene_id"])
        order = int(scene_payload["order"])
        preview_path = (previews_dir_path / f"{order:02d}_{scene_id}.png").resolve()
        if not preview_path.exists() or not preview_path.is_file():
            raise MP4AssemblerError(
                f"MP4 assembly failed: expected scene preview PNG is missing for scene_id={scene_id!r}: {preview_path}",
            )

        width, height = _read_png_dimensions(preview_path)
        if width is None or height is None:
            raise MP4AssemblerError(
                f"MP4 assembly failed: scene preview PNG is unreadable for scene_id={scene_id!r}: {preview_path}",
            )
        if width != CANVAS["width"] or height != CANVAS["height"]:
            raise MP4AssemblerError(
                f"MP4 assembly failed: scene preview PNG must be {CANVAS['width']}x{CANVAS['height']} "
                f"for scene_id={scene_id!r}, got {width}x{height}: {preview_path}",
            )

        preview_entries.append(
            {
                "scene_id": scene_id,
                "order": order,
                "duration_sec": round(float(scene_payload["duration_sec"]), 3),
                "preview_png_path": str(preview_path),
                "width": width,
                "height": height,
            }
        )
    return preview_entries


def _resolve_ffmpeg_binary() -> Path:
    resolved = shutil.which("ffmpeg")
    if not resolved:
        raise MP4AssemblerError(
            "MP4 assembly failed: FFmpeg is not available on PATH. Install ffmpeg or add it to PATH.",
        )
    return Path(resolved).resolve()


def _build_ffmpeg_command(
    ffmpeg_path: Path,
    preview_entries: list[dict[str, Any]],
    output_path: Path,
) -> list[str]:
    command = [str(ffmpeg_path), "-y"]
    for entry in preview_entries:
        command.extend(
            [
                "-loop",
                "1",
                "-framerate",
                str(FPS),
                "-t",
                _format_duration(entry["duration_sec"]),
                "-i",
                entry["preview_png_path"],
            ]
        )

    concat_inputs = "".join(f"[{index}:v]" for index in range(len(preview_entries)))
    command.extend(
        [
            "-filter_complex",
            f"{concat_inputs}concat=n={len(preview_entries)}:v=1:a=0,format=yuv420p[vout]",
            "-map",
            "[vout]",
            "-r",
            str(FPS),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-an",
            str(output_path),
        ]
    )
    return command


def _run_ffmpeg(command: list[str]) -> None:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise MP4AssemblerError(
            "MP4 assembly failed: FFmpeg executable could not be launched.",
        ) from exc
    except OSError as exc:
        raise MP4AssemblerError(
            f"MP4 assembly failed: could not launch FFmpeg: {exc}",
        ) from exc

    if completed.returncode == 0:
        return

    error_text = (completed.stderr or completed.stdout or "").strip()
    if error_text:
        raise MP4AssemblerError(f"MP4 assembly failed: FFmpeg exited with code {completed.returncode}: {error_text}")
    raise MP4AssemblerError(f"MP4 assembly failed: FFmpeg exited with code {completed.returncode}.")


def _read_png_dimensions(path: Path) -> tuple[int | None, int | None]:
    try:
        from PIL import Image

        with Image.open(path) as image:
            return int(image.width), int(image.height)
    except (FileNotFoundError, OSError, SyntaxError, ValueError):
        return None, None


def _resolve_dir(raw_path: str | Path) -> Path:
    path = Path(raw_path)
    resolved = path if path.is_absolute() else (Path.cwd() / path)
    return resolved.resolve()


def _format_duration(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _pick_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "MP4AssemblerError",
    "assemble_scene_previews_mp4",
]
