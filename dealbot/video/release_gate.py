from __future__ import annotations

from pathlib import Path
from typing import Any


EXPECTED_SCENE_COUNT = 5
EXPECTED_CANVAS = {"width": 1080, "height": 1920}
EXPECTED_FPS = 30
SUSPICIOUSLY_SMALL_VIDEO_BYTES = 128 * 1024
SILENT_WARNING_TOKEN = "-an"


class VideoReleaseGateError(ValueError):
    pass


def build_video_release_gate_report(
    renderer_input: dict[str, Any],
    scene_visual_qa_report: dict[str, Any],
    video_assembly_manifest: dict[str, Any],
    video_path: str | Path,
) -> dict[str, Any]:
    if not isinstance(renderer_input, dict):
        raise VideoReleaseGateError("Video release gate failed: renderer_input must be a dict.")
    if not isinstance(scene_visual_qa_report, dict):
        raise VideoReleaseGateError("Video release gate failed: scene_visual_qa_report must be a dict.")
    if not isinstance(video_assembly_manifest, dict):
        raise VideoReleaseGateError("Video release gate failed: video_assembly_manifest must be a dict.")

    resolved_video_path = _resolve_path(video_path)
    block_reasons: list[str] = []
    warnings: list[str] = []
    checked_files: list[dict[str, Any]] = []

    renderer_scenes = _as_scene_list(renderer_input.get("scenes"))
    renderer_scene_count = len(renderer_scenes)
    renderer_duration = _float_or_none(renderer_input.get("total_duration_sec"))
    renderer_canvas = renderer_input.get("canvas") if isinstance(renderer_input.get("canvas"), dict) else {}
    renderer_fps = _int_or_none(renderer_input.get("fps"))

    assembly_scenes = _as_scene_list(video_assembly_manifest.get("scenes"))
    assembly_scene_count = _int_or_none(video_assembly_manifest.get("scene_count")) or len(assembly_scenes)
    assembly_duration = _float_or_none(video_assembly_manifest.get("total_duration_sec"))
    qa_status = _pick_text(scene_visual_qa_report.get("status")) or "unknown"
    qa_findings = [
        finding
        for finding in list(scene_visual_qa_report.get("findings") or [])
        if isinstance(finding, dict)
    ]
    qa_error_count = _int_or_none(scene_visual_qa_report.get("error_count"))
    if qa_error_count is None:
        qa_error_count = sum(1 for finding in qa_findings if _pick_text(finding.get("severity")) == "error")

    video_exists = resolved_video_path.exists() and resolved_video_path.is_file()
    video_size = resolved_video_path.stat().st_size if video_exists else None
    checked_files.append(
        {
            "label": "video_preview_mp4",
            "path": str(resolved_video_path),
            "exists": video_exists,
            "size_bytes": video_size,
        }
    )

    if not video_exists:
        _append_unique(block_reasons, f"Missing video preview MP4: {resolved_video_path}")
    elif not video_size:
        _append_unique(block_reasons, f"Video preview MP4 is empty: {resolved_video_path}")
    elif video_size < SUSPICIOUSLY_SMALL_VIDEO_BYTES:
        _append_unique(
            warnings,
            f"Video preview MP4 is suspiciously small ({video_size} bytes).",
        )

    if renderer_scene_count != EXPECTED_SCENE_COUNT:
        _append_unique(
            block_reasons,
            f"Renderer input scene count is {renderer_scene_count}; expected {EXPECTED_SCENE_COUNT}.",
        )
    if assembly_scene_count != EXPECTED_SCENE_COUNT or len(assembly_scenes) != EXPECTED_SCENE_COUNT:
        _append_unique(
            block_reasons,
            f"Assembly manifest references {len(assembly_scenes)} scene previews; expected {EXPECTED_SCENE_COUNT}.",
        )

    if qa_error_count > 0:
        _append_unique(block_reasons, f"Visual QA reported {qa_error_count} error(s).")
    elif qa_status == "fail":
        _append_unique(block_reasons, "Visual QA report status is fail.")

    if renderer_duration is None or assembly_duration is None or round(renderer_duration, 3) != round(assembly_duration, 3):
        _append_unique(
            block_reasons,
            "Assembly manifest total duration does not match renderer input total duration.",
        )

    if _int_or_none(renderer_canvas.get("width")) != EXPECTED_CANVAS["width"] or _int_or_none(
        renderer_canvas.get("height")
    ) != EXPECTED_CANVAS["height"]:
        _append_unique(
            block_reasons,
            f"Renderer input canvas must be {EXPECTED_CANVAS['width']}x{EXPECTED_CANVAS['height']}.",
        )

    if renderer_fps != EXPECTED_FPS:
        _append_unique(block_reasons, f"Renderer input fps must be {EXPECTED_FPS}.")

    if not _cta_scene_has_text(renderer_scenes):
        _append_unique(block_reasons, "CTA scene is missing CTA text.")

    preview_paths = []
    for scene in assembly_scenes:
        preview_path = _pick_text(scene.get("preview_png_path"))
        preview_paths.append(preview_path)
        if preview_path:
            resolved_preview = _resolve_path(preview_path)
            checked_files.append(
                {
                    "label": f"scene_preview_{_pick_text(scene.get('scene_id')) or 'unknown'}",
                    "path": str(resolved_preview),
                    "exists": resolved_preview.exists() and resolved_preview.is_file(),
                    "size_bytes": resolved_preview.stat().st_size
                    if resolved_preview.exists() and resolved_preview.is_file()
                    else None,
                }
            )

    if len([path for path in preview_paths if path]) != EXPECTED_SCENE_COUNT:
        _append_unique(
            block_reasons,
            f"Assembly manifest must reference exactly {EXPECTED_SCENE_COUNT} scene preview PNG paths.",
        )

    if qa_status == "warn":
        _append_unique(warnings, "Visual QA report verdict is warn.")

    finding_codes = {
        str(finding.get("code"))
        for finding in qa_findings
        if finding.get("code")
    }
    if "duplicate_visual_reuse" in finding_codes or list(scene_visual_qa_report.get("duplicate_visual_groups") or []):
        _append_unique(warnings, "Visual QA reported duplicate visual reuse across scenes.")
    if "source_image_aspect_ratio_risk" in finding_codes:
        _append_unique(warnings, "Visual QA reported source image aspect ratio risk.")
    if "fallback_visual_used" in finding_codes or "card_image_visual_used" in finding_codes:
        _append_unique(warnings, "Visual QA reported fallback or card-image visual usage.")

    if _manifest_indicates_silent_video(video_assembly_manifest):
        _append_unique(warnings, "Video preview appears to be silent.")

    verdict = "block" if block_reasons else "warn" if warnings else "pass"
    return {
        "schema_version": 1,
        "offer_id": _pick_text(renderer_input.get("offer_id"))
        or _pick_text(video_assembly_manifest.get("offer_id"))
        or _pick_text(scene_visual_qa_report.get("offer_id")),
        "verdict": verdict,
        "block_reasons": block_reasons,
        "warnings": warnings,
        "checked_files": checked_files,
        "scene_count": renderer_scene_count,
        "total_duration_sec": renderer_duration,
        "video_file_size_bytes": video_size,
        "production_ready": False,
    }


def _as_scene_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _cta_scene_has_text(scenes: list[dict[str, Any]]) -> bool:
    for scene in scenes:
        if _pick_text(scene.get("scene_id")) != "telegram_cta":
            continue
        text_blocks = scene.get("text_blocks")
        if not isinstance(text_blocks, list):
            return False
        for block in text_blocks:
            if not isinstance(block, dict):
                continue
            if _pick_text(block.get("role")) == "cta" and _pick_text(block.get("text")):
                return True
        return False
    return False


def _manifest_indicates_silent_video(video_assembly_manifest: dict[str, Any]) -> bool:
    audio_present = video_assembly_manifest.get("audio_present")
    if isinstance(audio_present, bool):
        return not audio_present

    command = video_assembly_manifest.get("ffmpeg_command")
    if isinstance(command, list):
        return SILENT_WARNING_TOKEN in [str(item) for item in command]
    return False


def _resolve_path(raw_path: str | Path) -> Path:
    path = Path(raw_path)
    resolved = path if path.is_absolute() else (Path.cwd() / path)
    return resolved.resolve()


def _append_unique(target: list[str], value: str) -> None:
    if value not in target:
        target.append(value)


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
    "VideoReleaseGateError",
    "build_video_release_gate_report",
]
