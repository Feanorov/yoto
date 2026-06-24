from __future__ import annotations

from typing import Any

from .models import VideoOffer
from .offer_adapter import build_video_manifest_draft

ALL_ASSET_TYPES = ("trailer", "screenshot", "card_image", "fallback")
SCENE_SPECS = (
    {
        "order": 1,
        "scene_id": "hook",
        "duration_sec": 2.0,
        "asset_priority": ("trailer", "screenshot", "card_image", "fallback"),
    },
    {
        "order": 2,
        "scene_id": "identity",
        "duration_sec": 2.5,
        "asset_priority": ("screenshot", "trailer", "card_image", "fallback"),
    },
    {
        "order": 3,
        "scene_id": "offer_proof",
        "duration_sec": 3.0,
        "asset_priority": ("card_image", "screenshot", "fallback"),
    },
    {
        "order": 4,
        "scene_id": "trust_or_deadline",
        "duration_sec": 3.0,
        "asset_priority": ("screenshot", "card_image", "fallback"),
    },
    {
        "order": 5,
        "scene_id": "telegram_cta",
        "duration_sec": 4.0,
        "asset_priority": ("card_image", "fallback"),
    },
)


class SceneAssetPlanError(ValueError):
    pass


def build_scene_asset_plan(video_offer: VideoOffer, draft_manifest: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(draft_manifest, dict):
        raise SceneAssetPlanError("Scene asset plan failed: draft_manifest must be a dict.")

    base_manifest = build_video_manifest_draft(video_offer)
    merged_manifest = _merge_manifest(base_manifest, draft_manifest)
    assets_by_type = _collect_assets(video_offer)
    available_asset_types = [asset_type for asset_type in ALL_ASSET_TYPES if assets_by_type[asset_type]]
    if not available_asset_types:
        raise SceneAssetPlanError(
            f"Scene asset plan failed: no visual asset exists for offer_id={video_offer.offer_id!r}.",
        )

    warnings: list[str] = []
    if available_asset_types == ["card_image"]:
        _append_warning(
            warnings,
            "Only the card image is available; the planner reused it across all scenes.",
        )

    scene_map = _scene_map(merged_manifest.get("scenes"))
    platform_endcards = _merge_string_dict(
        _as_string_dict(base_manifest.get("platform_endcards")),
        _as_string_dict(merged_manifest.get("platform_endcards")),
    )

    scenes: list[dict[str, Any]] = []
    for spec in SCENE_SPECS:
        scene_id = str(spec["scene_id"])
        selected_asset_type, selected_asset_ref, asset_candidates, scene_warnings = _select_scene_asset(
            scene_id=scene_id,
            preferred_types=tuple(spec["asset_priority"]),
            assets_by_type=assets_by_type,
        )
        payload = {
            "order": int(spec["order"]),
            "scene_id": scene_id,
            "duration_sec": float(spec["duration_sec"]),
            "asset_priority": list(spec["asset_priority"]),
            "asset_candidates": asset_candidates,
            "selected_asset_type": selected_asset_type,
            "selected_asset_ref": selected_asset_ref,
        }
        payload.update(_scene_text_payload(scene_id, scene_map.get(scene_id, {}), platform_endcards))
        if scene_warnings:
            payload["warnings"] = scene_warnings
            for warning in scene_warnings:
                _append_warning(warnings, warning)
        scenes.append(payload)

    return {
        "offer_id": video_offer.offer_id,
        "template": _pick_text(merged_manifest.get("template")) or "single_offer_gameplay_first",
        "format": _pick_text(merged_manifest.get("format")) or "vertical_1080x1920",
        "total_duration_sec": round(sum(float(spec["duration_sec"]) for spec in SCENE_SPECS), 1),
        "voice_mode": _pick_text(merged_manifest.get("voice_mode")) or video_offer.voice_mode or "none",
        "music_required": bool(merged_manifest.get("music_required", True)),
        "scenes": scenes,
        "platform_endcards": platform_endcards,
        "warnings": warnings,
    }


def _merge_manifest(base_manifest: dict[str, Any], override_manifest: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base_manifest)
    for key in ("offer_id", "template", "format", "voice_mode"):
        value = _pick_text(override_manifest.get(key))
        if value:
            merged[key] = value

    if "music_required" in override_manifest:
        merged["music_required"] = bool(override_manifest.get("music_required"))

    merged["platform_endcards"] = _merge_string_dict(
        _as_string_dict(base_manifest.get("platform_endcards")),
        _as_string_dict(override_manifest.get("platform_endcards")),
    )
    merged["scenes"] = _merge_scenes(base_manifest.get("scenes"), override_manifest.get("scenes"))
    return merged


def _merge_scenes(base_scenes: Any, override_scenes: Any) -> list[dict[str, Any]]:
    base_map = _scene_map(base_scenes)
    override_map = _scene_map(override_scenes)
    merged_scenes: list[dict[str, Any]] = []
    for spec in SCENE_SPECS:
        scene_id = str(spec["scene_id"])
        merged_scene = dict(base_map.get(scene_id, {}))
        override_scene = override_map.get(scene_id, {})
        for key, value in override_scene.items():
            if key in {"order", "scene_id"}:
                continue
            if _is_present(value):
                merged_scene[key] = value
        merged_scene["order"] = int(spec["order"])
        merged_scene["scene_id"] = scene_id
        merged_scenes.append(merged_scene)
    return merged_scenes


def _scene_map(raw_scenes: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw_scenes, list):
        return {}
    mapped: dict[str, dict[str, Any]] = {}
    for raw_scene in raw_scenes:
        if not isinstance(raw_scene, dict):
            continue
        scene_id = _pick_text(raw_scene.get("scene_id"))
        if not scene_id:
            continue
        cleaned = dict(raw_scene)
        cleaned["scene_id"] = scene_id
        mapped[scene_id] = cleaned
    return mapped


def _scene_text_payload(
    scene_id: str,
    scene_payload: dict[str, Any],
    platform_endcards: dict[str, str],
) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    for key in ("intent", "primary_text", "secondary_text"):
        value = _pick_text(scene_payload.get(key))
        if value:
            resolved[key] = value

    facts = _as_string_list(scene_payload.get("facts"))
    if facts:
        resolved["facts"] = facts

    if scene_id == "telegram_cta":
        platform_variants = _merge_string_dict(
            platform_endcards,
            _as_string_dict(scene_payload.get("platform_variants")),
        )
        if platform_variants:
            resolved["platform_variants"] = platform_variants
    return resolved


def _collect_assets(video_offer: VideoOffer) -> dict[str, list[str]]:
    card_image = _pick_text(video_offer.visual_assets.card_image, video_offer.card_image_path)
    return {
        "trailer": _dedupe_strings(list(video_offer.visual_assets.official_trailers)),
        "screenshot": _dedupe_strings(list(video_offer.visual_assets.official_screenshots)),
        "card_image": [card_image] if card_image else [],
        "fallback": _dedupe_strings([video_offer.visual_assets.fallback_image]),
    }


def _select_scene_asset(
    *,
    scene_id: str,
    preferred_types: tuple[str, ...],
    assets_by_type: dict[str, list[str]],
) -> tuple[str, str, list[str], list[str]]:
    effective_type_order = tuple(preferred_types) + tuple(
        asset_type for asset_type in ALL_ASSET_TYPES if asset_type not in preferred_types
    )
    asset_candidates = _dedupe_strings(
        [
            asset_ref
            for asset_type in effective_type_order
            for asset_ref in assets_by_type.get(asset_type, [])
        ]
    )
    for asset_type in effective_type_order:
        candidates = assets_by_type.get(asset_type, [])
        if not candidates:
            continue
        warnings: list[str] = []
        if asset_type != preferred_types[0]:
            if asset_type in preferred_types:
                warnings.append(
                    f"Scene '{scene_id}' used {asset_type} because higher-priority asset types were unavailable.",
                )
            else:
                warnings.append(
                    f"Scene '{scene_id}' used non-preferred asset type {asset_type} because its preferred asset types were unavailable.",
                )
        return asset_type, candidates[0], asset_candidates, warnings

    raise SceneAssetPlanError(
        f"Scene asset plan failed: no visual asset exists for scene_id={scene_id!r}.",
    )


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


def _merge_string_dict(base: dict[str, str], override: dict[str, str]) -> dict[str, str]:
    merged = dict(base)
    merged.update(override)
    return merged


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return _dedupe_strings(value)


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


def _append_warning(warnings: list[str], warning: str) -> None:
    cleaned = _pick_text(warning)
    if cleaned and cleaned not in warnings:
        warnings.append(cleaned)


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _pick_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        cleaned = str(value).strip()
        if cleaned:
            return cleaned
    return None
