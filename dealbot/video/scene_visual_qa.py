from __future__ import annotations

from pathlib import Path
from typing import Any


EXPECTED_SCENE_COUNT = 5
EXPECTED_SOURCE_ASPECT = (1080, 1920)
MIN_SOURCE_IMAGE_WIDTH = 720
MIN_SOURCE_IMAGE_HEIGHT = 720
MAX_TEXT_BLOCKS_PER_SCENE = 4
SUPPORTED_LOCAL_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp"})


class SceneVisualQAError(ValueError):
    pass


def build_scene_visual_qa_report(renderer_input: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(renderer_input, dict):
        raise SceneVisualQAError("Scene visual QA failed: renderer_input must be a dict.")

    raw_scenes = renderer_input.get("scenes")
    scenes = raw_scenes if isinstance(raw_scenes, list) else []
    findings: list[dict[str, Any]] = []
    scene_reports: list[dict[str, Any]] = []
    scene_index_by_visual_key: dict[str, list[dict[str, Any]]] = {}

    if not isinstance(raw_scenes, list):
        findings.append(
            _finding(
                severity="error",
                code="scene_list_missing",
                message="renderer_input.scenes must be a list.",
            )
        )

    if len(scenes) != EXPECTED_SCENE_COUNT:
        findings.append(
            _finding(
                severity="error",
                code="scene_count_mismatch",
                message=(
                    f"renderer_input contains {len(scenes)} scenes; expected exactly {EXPECTED_SCENE_COUNT}."
                ),
                scene_count=len(scenes),
                expected_scene_count=EXPECTED_SCENE_COUNT,
            )
        )

    for index, scene_payload in enumerate(scenes):
        scene_reports.append(
            _inspect_scene(
                scene_payload=scene_payload,
                index=index,
                findings=findings,
                scene_index_by_visual_key=scene_index_by_visual_key,
            )
        )

    duplicate_groups = _duplicate_visual_groups(scene_index_by_visual_key)
    for group in duplicate_groups:
        findings.append(
            _finding(
                severity="warning",
                code="duplicate_visual_reuse",
                message=(
                    f"Visual is reused across scenes: {', '.join(group['scene_ids'])}."
                ),
                asset_ref=group["asset_ref"],
                scene_ids=group["scene_ids"],
                orders=group["orders"],
            )
        )

    error_count = sum(1 for finding in findings if finding["severity"] == "error")
    warning_count = sum(1 for finding in findings if finding["severity"] == "warning")
    status = "fail" if error_count else "warn" if warning_count else "pass"

    return {
        "schema_version": 1,
        "offer_id": _pick_text(renderer_input.get("offer_id")),
        "template": _pick_text(renderer_input.get("template")),
        "expected_scene_count": EXPECTED_SCENE_COUNT,
        "scene_count": len(scenes),
        "total_duration_sec": _float_or_none(renderer_input.get("total_duration_sec")),
        "status": status,
        "error_count": error_count,
        "warning_count": warning_count,
        "findings": findings,
        "duplicate_visual_groups": duplicate_groups,
        "scenes": scene_reports,
    }


def _inspect_scene(
    *,
    scene_payload: Any,
    index: int,
    findings: list[dict[str, Any]],
    scene_index_by_visual_key: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    if not isinstance(scene_payload, dict):
        scene_id = f"scene_{index + 1}"
        scene_finding = _finding(
            severity="error",
            code="scene_payload_invalid",
            message=f"renderer_input.scenes[{index}] must be a dict.",
            scene_id=scene_id,
            order=index + 1,
        )
        findings.append(scene_finding)
        return {
            "scene_id": scene_id,
            "order": index + 1,
            "scene_type": None,
            "visual": {},
            "visual_ref_kind": "missing",
            "text_block_count": 0,
            "empty_text_block_count": 0,
            "has_cta_text": None,
            "source_image": {
                "path": None,
                "exists": False,
                "extension": None,
                "supported_extension": False,
                "width": None,
                "height": None,
                "aspect_ratio": None,
                "aspect_ratio_risk": None,
                "very_small_risk": None,
            },
            "findings": [scene_finding],
        }

    scene_id = _pick_text(scene_payload.get("scene_id")) or f"scene_{index + 1}"
    order = _int_or_none(scene_payload.get("order")) or (index + 1)
    visual = scene_payload.get("visual")
    scene_findings: list[dict[str, Any]] = []
    visual_report = _inspect_visual(
        scene_id=scene_id,
        order=order,
        raw_visual=visual,
        scene_findings=scene_findings,
        scene_index_by_visual_key=scene_index_by_visual_key,
    )
    text_report = _inspect_text_blocks(
        scene_id=scene_id,
        order=order,
        raw_text_blocks=scene_payload.get("text_blocks"),
        scene_findings=scene_findings,
    )
    if scene_id == "telegram_cta" and not text_report["has_cta_text"]:
        scene_findings.append(
            _finding(
                severity="error",
                code="cta_text_missing",
                message="CTA scene is missing a non-empty primary CTA text block.",
                scene_id=scene_id,
                order=order,
            )
        )

    findings.extend(scene_findings)
    return {
        "scene_id": scene_id,
        "order": order,
        "scene_type": _pick_text(scene_payload.get("scene_type")),
        "visual": dict(visual) if isinstance(visual, dict) else {},
        "visual_ref_kind": visual_report["visual_ref_kind"],
        "text_block_count": text_report["text_block_count"],
        "empty_text_block_count": text_report["empty_text_block_count"],
        "has_cta_text": text_report["has_cta_text"] if scene_id == "telegram_cta" else None,
        "source_image": visual_report["source_image"],
        "findings": scene_findings,
    }


def _inspect_visual(
    *,
    scene_id: str,
    order: int,
    raw_visual: Any,
    scene_findings: list[dict[str, Any]],
    scene_index_by_visual_key: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    source_image = {
        "path": None,
        "exists": False,
        "extension": None,
        "supported_extension": False,
        "width": None,
        "height": None,
        "aspect_ratio": None,
        "aspect_ratio_risk": None,
        "very_small_risk": None,
    }
    if not isinstance(raw_visual, dict):
        scene_findings.append(
            _finding(
                severity="error",
                code="visual_payload_invalid",
                message="visual must be a dict.",
                scene_id=scene_id,
                order=order,
            )
        )
        return {
            "visual_ref_kind": "missing",
            "source_image": source_image,
        }

    asset_type = _pick_text(raw_visual.get("asset_type"))
    asset_ref = _pick_text(raw_visual.get("asset_ref"))
    source_image["path"] = asset_ref
    if not asset_ref:
        scene_findings.append(
            _finding(
                severity="error",
                code="visual_ref_missing",
                message="visual.asset_ref is missing.",
                scene_id=scene_id,
                order=order,
            )
        )
        return {
            "visual_ref_kind": "missing",
            "source_image": source_image,
        }

    asset_ref_kind = _classify_asset_ref(asset_ref)
    if asset_type == "fallback":
        scene_findings.append(
            _finding(
                severity="warning",
                code="fallback_visual_used",
                message="Scene is using a fallback visual.",
                scene_id=scene_id,
                order=order,
                asset_ref=asset_ref,
            )
        )
    elif asset_type == "card_image":
        scene_findings.append(
            _finding(
                severity="warning",
                code="card_image_visual_used",
                message="Scene is using the card image as its visual source.",
                scene_id=scene_id,
                order=order,
                asset_ref=asset_ref,
            )
        )

    normalized_visual_key = _normalized_visual_key(asset_ref, kind=asset_ref_kind)
    if normalized_visual_key:
        scene_index_by_visual_key.setdefault(normalized_visual_key, []).append(
            {"scene_id": scene_id, "order": order, "asset_ref": asset_ref},
        )

    if asset_ref_kind == "remote":
        scene_findings.append(
            _finding(
                severity="error",
                code="remote_visual_url",
                message="Scene visual is still a remote URL.",
                scene_id=scene_id,
                order=order,
                asset_ref=asset_ref,
            )
        )
        remote_suffix = Path(asset_ref.split("?", 1)[0]).suffix.lower()
        if remote_suffix and remote_suffix not in SUPPORTED_LOCAL_IMAGE_SUFFIXES:
            scene_findings.append(
                _finding(
                    severity="error",
                    code="unsupported_visual_extension",
                    message=f"Scene visual uses unsupported extension {remote_suffix!r}.",
                    scene_id=scene_id,
                    order=order,
                    asset_ref=asset_ref,
                    extension=remote_suffix,
                )
            )
        return {
            "visual_ref_kind": "remote",
            "source_image": source_image,
        }

    if asset_ref_kind == "unsupported_scheme":
        scene_findings.append(
            _finding(
                severity="error",
                code="unsupported_visual_scheme",
                message="Scene visual uses an unsupported URL scheme.",
                scene_id=scene_id,
                order=order,
                asset_ref=asset_ref,
            )
        )
        return {
            "visual_ref_kind": "unsupported_scheme",
            "source_image": source_image,
        }

    raw_path = Path(asset_ref)
    resolved_path = raw_path if raw_path.is_absolute() else (Path.cwd() / raw_path)
    resolved_path = resolved_path.resolve()
    suffix = resolved_path.suffix.lower()
    source_image["path"] = str(resolved_path)
    source_image["extension"] = suffix or None
    source_image["exists"] = resolved_path.exists() and resolved_path.is_file()
    source_image["supported_extension"] = suffix in SUPPORTED_LOCAL_IMAGE_SUFFIXES

    if not source_image["exists"]:
        scene_findings.append(
            _finding(
                severity="error",
                code="missing_visual_file",
                message=f"Local visual file does not exist: {resolved_path}",
                scene_id=scene_id,
                order=order,
                asset_ref=str(resolved_path),
            )
        )
        return {
            "visual_ref_kind": "local",
            "source_image": source_image,
        }

    if suffix not in SUPPORTED_LOCAL_IMAGE_SUFFIXES:
        scene_findings.append(
            _finding(
                severity="error",
                code="unsupported_visual_extension",
                message=f"Scene visual uses unsupported extension {suffix!r}.",
                scene_id=scene_id,
                order=order,
                asset_ref=str(resolved_path),
                extension=suffix,
            )
        )
        return {
            "visual_ref_kind": "local",
            "source_image": source_image,
        }

    width, height = _read_local_image_dimensions(resolved_path)
    source_image["width"] = width
    source_image["height"] = height
    if width is None or height is None:
        scene_findings.append(
            _finding(
                severity="error",
                code="unreadable_visual_image",
                message=f"Local visual is not a readable image: {resolved_path}",
                scene_id=scene_id,
                order=order,
                asset_ref=str(resolved_path),
            )
        )
        return {
            "visual_ref_kind": "local",
            "source_image": source_image,
        }

    source_image["aspect_ratio"] = round(width / height, 6) if height else None
    aspect_ratio_risk = (width * EXPECTED_SOURCE_ASPECT[1]) != (height * EXPECTED_SOURCE_ASPECT[0])
    source_image["aspect_ratio_risk"] = aspect_ratio_risk
    very_small_risk = width < MIN_SOURCE_IMAGE_WIDTH or height < MIN_SOURCE_IMAGE_HEIGHT
    source_image["very_small_risk"] = very_small_risk

    if aspect_ratio_risk:
        scene_findings.append(
            _finding(
                severity="warning",
                code="source_image_aspect_ratio_risk",
                message=(
                    f"Source image aspect ratio {width}x{height} differs from the target "
                    f"{EXPECTED_SOURCE_ASPECT[0]}x{EXPECTED_SOURCE_ASPECT[1]} ratio."
                ),
                scene_id=scene_id,
                order=order,
                asset_ref=str(resolved_path),
                width=width,
                height=height,
            )
        )
    if very_small_risk:
        scene_findings.append(
            _finding(
                severity="warning",
                code="source_image_very_small",
                message=(
                    f"Source image is small for vertical video use: {width}x{height}."
                ),
                scene_id=scene_id,
                order=order,
                asset_ref=str(resolved_path),
                width=width,
                height=height,
            )
        )

    return {
        "visual_ref_kind": "local",
        "source_image": source_image,
    }


def _inspect_text_blocks(
    *,
    scene_id: str,
    order: int,
    raw_text_blocks: Any,
    scene_findings: list[dict[str, Any]],
) -> dict[str, Any]:
    text_blocks = raw_text_blocks if isinstance(raw_text_blocks, list) else []
    if not isinstance(raw_text_blocks, list):
        scene_findings.append(
            _finding(
                severity="warning",
                code="empty_text_blocks",
                message="Scene text_blocks is missing or not a list.",
                scene_id=scene_id,
                order=order,
            )
        )
        return {
            "text_block_count": 0,
            "empty_text_block_count": 0,
            "has_cta_text": False,
        }

    text_block_count = len(text_blocks)
    empty_text_block_count = 0
    has_cta_text = False
    if text_block_count == 0:
        scene_findings.append(
            _finding(
                severity="warning",
                code="empty_text_blocks",
                message="Scene has no text blocks.",
                scene_id=scene_id,
                order=order,
            )
        )

    if text_block_count > MAX_TEXT_BLOCKS_PER_SCENE:
        scene_findings.append(
            _finding(
                severity="warning",
                code="too_many_text_blocks",
                message=(
                    f"Scene has {text_block_count} text blocks; recommended maximum is {MAX_TEXT_BLOCKS_PER_SCENE}."
                ),
                scene_id=scene_id,
                order=order,
                text_block_count=text_block_count,
            )
        )

    for block_index, raw_block in enumerate(text_blocks):
        if not isinstance(raw_block, dict):
            empty_text_block_count += 1
            scene_findings.append(
                _finding(
                    severity="warning",
                    code="empty_text_block_value",
                    message=f"text_blocks[{block_index}] is not a dict.",
                    scene_id=scene_id,
                    order=order,
                )
            )
            continue

        role = _pick_text(raw_block.get("role"))
        text = _pick_text(raw_block.get("text"))
        if role == "cta" and text:
            has_cta_text = True
        if text:
            continue
        empty_text_block_count += 1
        scene_findings.append(
            _finding(
                severity="warning",
                code="empty_text_block_value",
                message=f"text_blocks[{block_index}] has empty text.",
                scene_id=scene_id,
                order=order,
                role=role,
            )
        )

    return {
        "text_block_count": text_block_count,
        "empty_text_block_count": empty_text_block_count,
        "has_cta_text": has_cta_text,
    }


def _duplicate_visual_groups(scene_index_by_visual_key: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for entries in scene_index_by_visual_key.values():
        if len(entries) <= 1:
            continue
        groups.append(
            {
                "asset_ref": entries[0]["asset_ref"],
                "scene_ids": [entry["scene_id"] for entry in entries],
                "orders": [entry["order"] for entry in entries],
            }
        )
    return groups


def _normalized_visual_key(asset_ref: str, *, kind: str) -> str | None:
    if kind == "local":
        resolved = Path(asset_ref) if Path(asset_ref).is_absolute() else (Path.cwd() / asset_ref)
        return str(resolved.resolve())
    if kind in {"remote", "unsupported_scheme"}:
        return asset_ref
    return None


def _classify_asset_ref(asset_ref: str) -> str:
    lowered = asset_ref.lower()
    if lowered.startswith("http://") or lowered.startswith("https://"):
        return "remote"
    if "://" in asset_ref:
        return "unsupported_scheme"
    return "local"


def _read_local_image_dimensions(path: Path) -> tuple[int | None, int | None]:
    try:
        from PIL import Image

        with Image.open(path) as image:
            return int(image.width), int(image.height)
    except (FileNotFoundError, OSError, SyntaxError, ValueError):
        return None, None


def _finding(*, severity: str, code: str, message: str, **extra: Any) -> dict[str, Any]:
    finding = {
        "severity": severity,
        "code": code,
        "message": message,
    }
    finding.update(extra)
    return finding


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
    "SceneVisualQAError",
    "build_scene_visual_qa_report",
]
