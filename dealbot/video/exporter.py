from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .models import VideoOfferValidationError
from .offer_adapter import build_video_manifest_draft, build_video_offer_from_preview_report
from .layout_builder import SceneLayoutPayloadError, build_scene_layout_payload
from .mp4_assembler import MP4AssemblerError, assemble_scene_previews_mp4
from .renderer_input_adapter import RendererInputAdapterError, build_renderer_input
from .scene_preview_renderer import ScenePreviewRenderError, render_scene_previews
from .scene_planner import SceneAssetPlanError, build_scene_asset_plan
from .scene_visual_qa import SceneVisualQAError, build_scene_visual_qa_report
from .visual_staging import VisualStagingError, stage_renderer_visuals


@dataclass(frozen=True, slots=True)
class VideoOfferExportResult:
    source_report_path: Path
    output_dir: Path
    video_offer_json_path: Path
    draft_manifest_json_path: Path
    scene_asset_plan_json_path: Path | None
    scene_layout_payload_json_path: Path | None
    renderer_input_json_path: Path | None
    renderer_input_staged_json_path: Path | None
    scene_visual_qa_report_json_path: Path | None
    video_preview_mp4_path: Path | None
    video_assembly_manifest_json_path: Path | None
    staged_visuals_dir_path: Path | None
    scene_previews_dir_path: Path | None
    offer_id: str
    template: str
    scene_count: int
    renderer_scene_count: int | None = None
    renderer_total_duration_sec: float | None = None
    visual_qa_status: str | None = None
    visual_qa_error_count: int | None = None
    visual_qa_warning_count: int | None = None
    video_preview_duration_sec: float | None = None
    staged_scene_count: int | None = None
    staged_visual_count: int | None = None
    rendered_scene_count: int | None = None
    status: str = "exported"


class VideoOfferExportError(ValueError):
    pass


def export_video_offer_artifacts(
    source_report_path: str | Path,
    output_dir: str | Path | None = None,
    *,
    with_scene_plan: bool = False,
    with_layout_payload: bool = False,
    with_renderer_input: bool = False,
    with_visual_qa_report: bool = False,
    stage_visuals_flag: bool = False,
    render_scene_previews_flag: bool = False,
    assemble_mp4_preview_flag: bool = False,
) -> VideoOfferExportResult:
    input_path = _resolve_input_path(source_report_path)
    report_path, report_payload = _load_export_source(input_path)

    video_offer = build_video_offer_from_preview_report(
        report_payload,
        source_report_path=str(report_path),
    )
    draft_manifest = build_video_manifest_draft(video_offer)
    should_render_scene_previews = render_scene_previews_flag or assemble_mp4_preview_flag
    should_export_visual_qa_report = with_visual_qa_report or should_render_scene_previews
    should_export_renderer_input = (
        with_renderer_input or should_export_visual_qa_report or stage_visuals_flag or should_render_scene_previews
    )
    should_export_layout_payload = with_layout_payload or should_export_renderer_input
    should_export_scene_plan = with_scene_plan or should_export_layout_payload
    scene_asset_plan = build_scene_asset_plan(video_offer, draft_manifest) if should_export_scene_plan else None
    scene_layout_payload = (
        build_scene_layout_payload(video_offer, scene_asset_plan)
        if should_export_layout_payload and scene_asset_plan is not None
        else None
    )
    renderer_input = (
        build_renderer_input(video_offer, scene_asset_plan, scene_layout_payload)
        if should_export_renderer_input and scene_asset_plan is not None and scene_layout_payload is not None
        else None
    )

    resolved_output_dir = _resolve_output_dir(report_path=report_path, output_dir=output_dir)
    video_offer_json_path = resolved_output_dir / "video_offer.json"
    draft_manifest_json_path = resolved_output_dir / "draft_video_manifest.json"
    scene_asset_plan_json_path = resolved_output_dir / "scene_asset_plan.json" if should_export_scene_plan else None
    scene_layout_payload_json_path = (
        resolved_output_dir / "scene_layout_payload.json" if should_export_layout_payload else None
    )
    renderer_input_json_path = resolved_output_dir / "renderer_input.json" if should_export_renderer_input else None
    should_stage_visuals = stage_visuals_flag or should_render_scene_previews
    renderer_input_staged_json_path = (
        resolved_output_dir / "renderer_input_staged.json" if should_stage_visuals else None
    )
    scene_visual_qa_report_json_path = (
        resolved_output_dir / "scene_visual_qa_report.json" if should_export_visual_qa_report else None
    )
    video_preview_mp4_path = resolved_output_dir / "video_preview.mp4" if assemble_mp4_preview_flag else None
    video_assembly_manifest_json_path = (
        resolved_output_dir / "video_assembly_manifest.json" if assemble_mp4_preview_flag else None
    )
    staged_visuals_dir_path = resolved_output_dir / "staged_visuals" if should_stage_visuals else None
    scene_previews_dir_path = resolved_output_dir / "scene_previews" if should_render_scene_previews else None

    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(video_offer_json_path, video_offer.to_dict())
    _write_json(draft_manifest_json_path, draft_manifest)
    if scene_asset_plan_json_path is not None and scene_asset_plan is not None:
        _write_json(scene_asset_plan_json_path, scene_asset_plan)
    if scene_layout_payload_json_path is not None and scene_layout_payload is not None:
        _write_json(scene_layout_payload_json_path, scene_layout_payload)
    if renderer_input_json_path is not None and renderer_input is not None:
        _write_json(renderer_input_json_path, renderer_input)
    staged_renderer_input = renderer_input
    staging_metadata: dict[str, Any] | None = None
    if should_stage_visuals and renderer_input is not None and renderer_input_staged_json_path is not None:
        staged_renderer_input, staging_metadata = stage_renderer_visuals(renderer_input, resolved_output_dir)
        _write_json(renderer_input_staged_json_path, staged_renderer_input)
    visual_qa_report: dict[str, Any] | None = None
    if should_export_visual_qa_report and scene_visual_qa_report_json_path is not None:
        qa_renderer_input = staged_renderer_input if staged_renderer_input is not None else renderer_input
        if qa_renderer_input is not None:
            visual_qa_report = build_scene_visual_qa_report(qa_renderer_input)
            _write_json(scene_visual_qa_report_json_path, visual_qa_report)
    rendered_scene_paths = (
        render_scene_previews(staged_renderer_input, scene_previews_dir_path)
        if should_render_scene_previews and staged_renderer_input is not None and scene_previews_dir_path is not None
        else []
    )
    assembly_manifest: dict[str, Any] | None = None
    if assemble_mp4_preview_flag and staged_renderer_input is not None and scene_previews_dir_path is not None:
        assembly_manifest = assemble_scene_previews_mp4(staged_renderer_input, scene_previews_dir_path, resolved_output_dir)

    return VideoOfferExportResult(
        source_report_path=report_path,
        output_dir=resolved_output_dir,
        video_offer_json_path=video_offer_json_path,
        draft_manifest_json_path=draft_manifest_json_path,
        scene_asset_plan_json_path=scene_asset_plan_json_path,
        scene_layout_payload_json_path=scene_layout_payload_json_path,
        renderer_input_json_path=renderer_input_json_path,
        renderer_input_staged_json_path=(
            renderer_input_staged_json_path.resolve() if renderer_input_staged_json_path is not None else None
        ),
        scene_visual_qa_report_json_path=(
            scene_visual_qa_report_json_path.resolve() if scene_visual_qa_report_json_path is not None else None
        ),
        video_preview_mp4_path=video_preview_mp4_path.resolve() if video_preview_mp4_path is not None else None,
        video_assembly_manifest_json_path=(
            video_assembly_manifest_json_path.resolve() if video_assembly_manifest_json_path is not None else None
        ),
        staged_visuals_dir_path=staged_visuals_dir_path.resolve() if staged_visuals_dir_path is not None else None,
        scene_previews_dir_path=scene_previews_dir_path.resolve() if scene_previews_dir_path is not None else None,
        offer_id=video_offer.offer_id,
        template=str(draft_manifest.get("template") or ""),
        scene_count=len(list(draft_manifest.get("scenes") or [])),
        renderer_scene_count=len(list(renderer_input.get("scenes") or [])) if renderer_input is not None else None,
        renderer_total_duration_sec=(
            float(renderer_input.get("total_duration_sec")) if renderer_input is not None else None
        ),
        visual_qa_status=(
            str(visual_qa_report.get("status")) if visual_qa_report is not None and visual_qa_report.get("status") else None
        ),
        visual_qa_error_count=(
            int(visual_qa_report.get("error_count")) if visual_qa_report is not None else None
        ),
        visual_qa_warning_count=(
            int(visual_qa_report.get("warning_count")) if visual_qa_report is not None else None
        ),
        video_preview_duration_sec=(
            float(assembly_manifest.get("total_duration_sec")) if assembly_manifest is not None else None
        ),
        staged_scene_count=(
            int(staging_metadata.get("staged_scene_count")) if staging_metadata is not None else None
        ),
        staged_visual_count=(
            int(staging_metadata.get("staged_visual_count")) if staging_metadata is not None else None
        ),
        rendered_scene_count=len(rendered_scene_paths) or None,
    )


def _resolve_input_path(source_report_path: str | Path) -> Path:
    raw_path = Path(source_report_path)
    resolved = raw_path if raw_path.is_absolute() else (Path.cwd() / raw_path)
    resolved = resolved.resolve()
    if not resolved.exists() or not resolved.is_file():
        raise FileNotFoundError(f"VideoOffer export failed: source report does not exist: {resolved}")
    return resolved


def _load_export_source(input_path: Path) -> tuple[Path, dict[str, Any]]:
    payload = _read_json(input_path)
    if _looks_like_preview_report(payload):
        return input_path, payload

    report_path = _resolve_report_reference(input_path, payload)
    if report_path is None:
        raise VideoOfferExportError(
            "VideoOffer export failed: input file is not a preview report and does not point to one via report_path.",
        )
    report_payload = _read_json(report_path)
    if not _looks_like_preview_report(report_payload):
        raise VideoOfferExportError(
            f"VideoOffer export failed: resolved report does not contain pinned_publish: {report_path}",
        )
    return report_path, report_payload


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw_text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise VideoOfferExportError(f"VideoOffer export failed: could not read {path}: {exc}") from exc
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise VideoOfferExportError(f"VideoOffer export failed: invalid JSON in {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise VideoOfferExportError(f"VideoOffer export failed: JSON root must be an object: {path}")
    return payload


def _looks_like_preview_report(payload: dict[str, Any]) -> bool:
    return isinstance(payload.get("pinned_publish"), dict)


def _resolve_report_reference(input_path: Path, payload: dict[str, Any]) -> Path | None:
    referenced = str(payload.get("report_path") or "").strip()
    if not referenced:
        return None

    candidate = Path(referenced)
    if candidate.is_absolute() and candidate.exists() and candidate.is_file():
        return candidate.resolve()

    candidates = [
        (input_path.parent / candidate),
        (Path.cwd() / candidate),
    ]
    for option in candidates:
        resolved = option.resolve()
        if resolved.exists() and resolved.is_file():
            return resolved
    return None


def _resolve_output_dir(report_path: Path, output_dir: str | Path | None) -> Path:
    if output_dir is not None:
        raw_output = Path(output_dir)
        resolved = raw_output if raw_output.is_absolute() else (Path.cwd() / raw_output)
        return resolved.resolve()
    return (Path.cwd() / "output" / "video_offer_exports" / report_path.stem).resolve()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
