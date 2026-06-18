from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .models import VideoOfferValidationError
from .offer_adapter import build_video_manifest_draft, build_video_offer_from_preview_report


@dataclass(frozen=True, slots=True)
class VideoOfferExportResult:
    source_report_path: Path
    output_dir: Path
    video_offer_json_path: Path
    draft_manifest_json_path: Path
    offer_id: str
    template: str
    scene_count: int
    status: str = "exported"


class VideoOfferExportError(ValueError):
    pass


def export_video_offer_artifacts(
    source_report_path: str | Path,
    output_dir: str | Path | None = None,
) -> VideoOfferExportResult:
    input_path = _resolve_input_path(source_report_path)
    report_path, report_payload = _load_export_source(input_path)

    video_offer = build_video_offer_from_preview_report(
        report_payload,
        source_report_path=str(report_path),
    )
    draft_manifest = build_video_manifest_draft(video_offer)

    resolved_output_dir = _resolve_output_dir(report_path=report_path, output_dir=output_dir)
    video_offer_json_path = resolved_output_dir / "video_offer.json"
    draft_manifest_json_path = resolved_output_dir / "draft_video_manifest.json"

    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(video_offer_json_path, video_offer.to_dict())
    _write_json(draft_manifest_json_path, draft_manifest)

    return VideoOfferExportResult(
        source_report_path=report_path,
        output_dir=resolved_output_dir,
        video_offer_json_path=video_offer_json_path,
        draft_manifest_json_path=draft_manifest_json_path,
        offer_id=video_offer.offer_id,
        template=str(draft_manifest.get("template") or ""),
        scene_count=len(list(draft_manifest.get("scenes") or [])),
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
