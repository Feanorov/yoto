from __future__ import annotations

from typing import Any

from .models import VideoOffer

CANVAS = {"width": 1080, "height": 1920}
FPS = 30
SCHEMA_VERSION = 1
SCENE_RENDER_SPECS = (
    {"order": 1, "scene_id": "hook", "scene_type": "headline_hook"},
    {"order": 2, "scene_id": "identity", "scene_type": "title_identity"},
    {"order": 3, "scene_id": "offer_proof", "scene_type": "offer_proof_stack"},
    {"order": 4, "scene_id": "trust_or_deadline", "scene_type": "trust_deadline_stack"},
    {"order": 5, "scene_id": "telegram_cta", "scene_type": "telegram_cta_endcard"},
)
TEXT_BLOCK_FIELDS = (
    "role",
    "text",
    "priority",
    "required",
    "max_lines",
    "alignment",
    "anchor",
    "size_class",
)


class RendererInputAdapterError(ValueError):
    pass


def build_renderer_input(
    video_offer: VideoOffer,
    scene_asset_plan: dict[str, Any],
    scene_layout_payload: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(scene_asset_plan, dict):
        raise RendererInputAdapterError("Renderer input failed: scene_asset_plan must be a dict.")
    if not isinstance(scene_layout_payload, dict):
        raise RendererInputAdapterError("Renderer input failed: scene_layout_payload must be a dict.")

    _validate_offer_id(video_offer, scene_asset_plan, scene_layout_payload)
    template = _validated_text("template", scene_asset_plan.get("template"), scene_layout_payload.get("template"))
    output_format = _validated_text("format", scene_asset_plan.get("format"), scene_layout_payload.get("format"))
    voice_mode = _pick_text(scene_asset_plan.get("voice_mode"), video_offer.voice_mode) or "none"
    music_required = bool(scene_asset_plan.get("music_required", True))

    asset_plan_scenes = _validated_scene_list(
        scene_asset_plan.get("scenes"),
        field_name="scene_asset_plan.scenes",
    )
    layout_scenes = _validated_scene_list(
        scene_layout_payload.get("scenes"),
        field_name="scene_layout_payload.scenes",
    )
    if len(asset_plan_scenes) != len(SCENE_RENDER_SPECS):
        raise RendererInputAdapterError(
            f"Renderer input failed: scene_asset_plan must contain exactly {len(SCENE_RENDER_SPECS)} scenes.",
        )
    if len(layout_scenes) != len(SCENE_RENDER_SPECS):
        raise RendererInputAdapterError(
            f"Renderer input failed: scene_layout_payload must contain exactly {len(SCENE_RENDER_SPECS)} scenes.",
        )

    renderer_scenes: list[dict[str, Any]] = []
    cumulative_start = 0.0
    for index, spec in enumerate(SCENE_RENDER_SPECS):
        asset_scene = asset_plan_scenes[index]
        layout_scene = layout_scenes[index]
        scene_id = str(spec["scene_id"])
        scene_type = str(spec["scene_type"])
        order = int(spec["order"])

        _validate_scene_alignment(
            asset_scene=asset_scene,
            layout_scene=layout_scene,
            expected_scene_id=scene_id,
            expected_order=order,
            expected_scene_type=scene_type,
            index=index,
        )

        duration_sec = _validated_duration(asset_scene, layout_scene, scene_id=scene_id)
        visual = _validated_visual(asset_scene, layout_scene, scene_id=scene_id)
        canvas = _validated_canvas(layout_scene, scene_id=scene_id)
        safe_zone_profile = _required_text(
            layout_scene.get("safe_zone_profile"),
            error_message=f"Renderer input failed: safe_zone_profile is missing for scene_id={scene_id!r}.",
        )
        motion_hint = _required_text(
            layout_scene.get("motion_hint"),
            error_message=f"Renderer input failed: motion_hint is missing for scene_id={scene_id!r}.",
        )
        text_blocks = _validated_text_blocks(layout_scene.get("text_blocks"), scene_id=scene_id)
        scene_warnings = _dedupe_strings(
            _as_string_list(asset_scene.get("warnings")) + _as_string_list(layout_scene.get("warnings"))
        )

        start_sec = round(cumulative_start, 3)
        end_sec = round(cumulative_start + duration_sec, 3)
        renderer_scene = {
            "scene_id": scene_id,
            "order": order,
            "scene_type": scene_type,
            "start_sec": start_sec,
            "end_sec": end_sec,
            "duration_sec": duration_sec,
            "visual": visual,
            "text_blocks": text_blocks,
            "safe_zone_profile": safe_zone_profile,
            "motion": {"hint": motion_hint},
            "warnings": scene_warnings,
        }

        platform_variants = _as_string_dict(layout_scene.get("platform_variants"))
        if scene_id == "telegram_cta" and platform_variants:
            renderer_scene["platform_variants"] = platform_variants

        renderer_scenes.append(renderer_scene)
        cumulative_start = end_sec

    total_duration_sec = round(cumulative_start, 3)
    _validate_total_duration(scene_asset_plan, scene_layout_payload, total_duration_sec=total_duration_sec)

    return {
        "schema_version": SCHEMA_VERSION,
        "offer_id": video_offer.offer_id,
        "template": template,
        "format": output_format,
        "canvas": dict(CANVAS),
        "total_duration_sec": total_duration_sec,
        "fps": FPS,
        "voice_mode": voice_mode,
        "music_required": music_required,
        "scenes": renderer_scenes,
        "warnings": _dedupe_strings(
            _as_string_list(scene_asset_plan.get("warnings")) + _as_string_list(scene_layout_payload.get("warnings"))
        ),
    }


def _validate_offer_id(
    video_offer: VideoOffer,
    scene_asset_plan: dict[str, Any],
    scene_layout_payload: dict[str, Any],
) -> None:
    expected_offer_id = video_offer.offer_id
    for field_name, value in (
        ("scene_asset_plan.offer_id", scene_asset_plan.get("offer_id")),
        ("scene_layout_payload.offer_id", scene_layout_payload.get("offer_id")),
    ):
        cleaned = _pick_text(value)
        if cleaned != expected_offer_id:
            raise RendererInputAdapterError(
                f"Renderer input failed: {field_name}={cleaned!r} does not match video_offer.offer_id={expected_offer_id!r}.",
            )


def _validated_scene_list(value: Any, *, field_name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise RendererInputAdapterError(f"Renderer input failed: {field_name} must be a list.")
    scenes: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise RendererInputAdapterError(f"Renderer input failed: {field_name} must contain only dict scenes.")
        scenes.append(dict(item))
    return scenes


def _validate_scene_alignment(
    *,
    asset_scene: dict[str, Any],
    layout_scene: dict[str, Any],
    expected_scene_id: str,
    expected_order: int,
    expected_scene_type: str,
    index: int,
) -> None:
    asset_scene_id = _pick_text(asset_scene.get("scene_id"))
    if asset_scene_id != expected_scene_id:
        raise RendererInputAdapterError(
            f"Renderer input failed: scene_asset_plan scene index {index} must be scene_id={expected_scene_id!r}, "
            f"got {asset_scene_id!r}.",
        )

    asset_order = _int_or_none(asset_scene.get("order"))
    if asset_order != expected_order:
        raise RendererInputAdapterError(
            f"Renderer input failed: scene_asset_plan order mismatch for scene_id={expected_scene_id!r}: "
            f"expected {expected_order}, got {asset_order!r}.",
        )

    layout_scene_id = _pick_text(layout_scene.get("scene_id"))
    if layout_scene_id != expected_scene_id:
        raise RendererInputAdapterError(
            f"Renderer input failed: scene_layout_payload scene index {index} must be scene_id={expected_scene_id!r}, "
            f"got {layout_scene_id!r}.",
        )

    layout_scene_type = _pick_text(layout_scene.get("scene_type"))
    if layout_scene_type != expected_scene_type:
        raise RendererInputAdapterError(
            f"Renderer input failed: scene_type mismatch for scene_id={expected_scene_id!r}: "
            f"expected {expected_scene_type!r}, got {layout_scene_type!r}.",
        )


def _validated_duration(asset_scene: dict[str, Any], layout_scene: dict[str, Any], *, scene_id: str) -> float:
    asset_duration = _float_or_none(asset_scene.get("duration_sec"))
    layout_duration = _float_or_none(layout_scene.get("duration_sec"))
    if asset_duration is None or layout_duration is None:
        raise RendererInputAdapterError(
            f"Renderer input failed: duration_sec is missing for scene_id={scene_id!r}.",
        )
    if round(asset_duration, 3) != round(layout_duration, 3):
        raise RendererInputAdapterError(
            f"Renderer input failed: duration mismatch for scene_id={scene_id!r}: "
            f"asset plan={asset_duration}, layout payload={layout_duration}.",
        )
    return round(layout_duration, 3)


def _validated_visual(asset_scene: dict[str, Any], layout_scene: dict[str, Any], *, scene_id: str) -> dict[str, str]:
    expected_visual = {
        "asset_type": _required_text(
            asset_scene.get("selected_asset_type"),
            error_message=f"Renderer input failed: selected_asset_type is missing for scene_id={scene_id!r}.",
        ),
        "asset_ref": _required_text(
            asset_scene.get("selected_asset_ref"),
            error_message=f"Renderer input failed: selected_asset_ref is missing for scene_id={scene_id!r}.",
        ),
    }

    raw_layout_visual = layout_scene.get("selected_visual")
    if not isinstance(raw_layout_visual, dict):
        raise RendererInputAdapterError(
            f"Renderer input failed: selected_visual must be a dict for scene_id={scene_id!r}.",
        )

    layout_visual = {
        "asset_type": _required_text(
            raw_layout_visual.get("asset_type"),
            error_message=f"Renderer input failed: selected_visual.asset_type is missing for scene_id={scene_id!r}.",
        ),
        "asset_ref": _required_text(
            raw_layout_visual.get("asset_ref"),
            error_message=f"Renderer input failed: selected_visual.asset_ref is missing for scene_id={scene_id!r}.",
        ),
    }
    if layout_visual != expected_visual:
        raise RendererInputAdapterError(
            f"Renderer input failed: selected visual mismatch for scene_id={scene_id!r}: "
            f"asset plan={expected_visual}, layout payload={layout_visual}.",
        )
    return layout_visual


def _validated_canvas(layout_scene: dict[str, Any], *, scene_id: str) -> dict[str, int]:
    raw_canvas = layout_scene.get("canvas")
    if not isinstance(raw_canvas, dict):
        raise RendererInputAdapterError(
            f"Renderer input failed: canvas must be a dict for scene_id={scene_id!r}.",
        )

    width = _int_or_none(raw_canvas.get("width"))
    height = _int_or_none(raw_canvas.get("height"))
    if width != CANVAS["width"] or height != CANVAS["height"]:
        raise RendererInputAdapterError(
            f"Renderer input failed: canvas mismatch for scene_id={scene_id!r}: expected {CANVAS}, "
            f"got width={width!r}, height={height!r}.",
        )
    return dict(CANVAS)


def _validated_text_blocks(value: Any, *, scene_id: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise RendererInputAdapterError(
            f"Renderer input failed: text_blocks must be a list for scene_id={scene_id!r}.",
        )

    validated: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise RendererInputAdapterError(
                f"Renderer input failed: text_blocks[{index}] must be a dict for scene_id={scene_id!r}.",
            )

        text_block: dict[str, Any] = {}
        for field_name in TEXT_BLOCK_FIELDS:
            if field_name not in item:
                raise RendererInputAdapterError(
                    f"Renderer input failed: text_blocks[{index}].{field_name} is missing for scene_id={scene_id!r}.",
                )
            text_block[field_name] = item[field_name]
        validated.append(text_block)
    return validated


def _validate_total_duration(
    scene_asset_plan: dict[str, Any],
    scene_layout_payload: dict[str, Any],
    *,
    total_duration_sec: float,
) -> None:
    asset_plan_total = _float_or_none(scene_asset_plan.get("total_duration_sec"))
    if asset_plan_total is not None and round(asset_plan_total, 3) != total_duration_sec:
        raise RendererInputAdapterError(
            f"Renderer input failed: scene_asset_plan total_duration_sec={asset_plan_total} "
            f"does not match renderer total_duration_sec={total_duration_sec}.",
        )

    layout_total = _float_or_none(scene_layout_payload.get("total_duration_sec"))
    if layout_total is not None and round(layout_total, 3) != total_duration_sec:
        raise RendererInputAdapterError(
            f"Renderer input failed: scene_layout_payload total_duration_sec={layout_total} "
            f"does not match renderer total_duration_sec={total_duration_sec}.",
        )


def _validated_text(field_name: str, first_value: Any, second_value: Any) -> str:
    first_text = _required_text(
        first_value,
        error_message=f"Renderer input failed: {field_name} is missing from the upstream contracts.",
    )
    second_text = _required_text(
        second_value,
        error_message=f"Renderer input failed: {field_name} is missing from the upstream contracts.",
    )
    if first_text != second_text:
        raise RendererInputAdapterError(
            f"Renderer input failed: {field_name} mismatch between upstream contracts: "
            f"{first_text!r} != {second_text!r}.",
        )
    return first_text


def _required_text(value: Any, *, error_message: str) -> str:
    cleaned = _pick_text(value)
    if not cleaned:
        raise RendererInputAdapterError(error_message)
    return cleaned


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return _dedupe_strings(value)


def _as_string_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    cleaned: dict[str, str] = {}
    for key, raw_value in value.items():
        cleaned_key = _pick_text(key)
        cleaned_value = _pick_text(raw_value)
        if cleaned_key and cleaned_value:
            cleaned[cleaned_key] = cleaned_value
    return cleaned


def _dedupe_strings(values: list[Any]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _pick_text(value)
        if not cleaned or cleaned in seen:
            continue
        deduped.append(cleaned)
        seen.add(cleaned)
    return deduped


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _pick_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        cleaned = str(value).strip()
        if cleaned:
            return cleaned
    return None
