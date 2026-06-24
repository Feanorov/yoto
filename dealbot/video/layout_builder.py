from __future__ import annotations

from typing import Any

from .models import VideoOffer

CANVAS = {"width": 1080, "height": 1920}
CTA_PLATFORM_ORDER = ("tiktok", "shorts", "reels")
SCENE_LAYOUT_SPECS = (
    {
        "scene_id": "hook",
        "scene_type": "headline_hook",
        "safe_zone_profile": "upper_middle_center",
        "motion_hint": "use_native_motion_or_subtle_push",
    },
    {
        "scene_id": "identity",
        "scene_type": "title_identity",
        "safe_zone_profile": "upper_middle_title_stack",
        "motion_hint": "slow_push_in",
    },
    {
        "scene_id": "offer_proof",
        "scene_type": "offer_proof_stack",
        "safe_zone_profile": "middle_offer_stack",
        "motion_hint": "offer_hold_with_emphasis",
    },
    {
        "scene_id": "trust_or_deadline",
        "scene_type": "trust_deadline_stack",
        "safe_zone_profile": "lower_middle_fact_stack",
        "motion_hint": "detail_hold",
    },
    {
        "scene_id": "telegram_cta",
        "scene_type": "telegram_cta_endcard",
        "safe_zone_profile": "lower_third_cta",
        "motion_hint": "cta_hold",
    },
)


class SceneLayoutPayloadError(ValueError):
    pass


def build_scene_layout_payload(video_offer: VideoOffer, scene_asset_plan: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(scene_asset_plan, dict):
        raise SceneLayoutPayloadError("Scene layout payload failed: scene_asset_plan must be a dict.")

    plan_scenes = _scene_map(scene_asset_plan.get("scenes"))
    warnings = _as_string_list(scene_asset_plan.get("warnings"))
    scenes: list[dict[str, Any]] = []

    for spec in SCENE_LAYOUT_SPECS:
        scene_id = str(spec["scene_id"])
        plan_scene = plan_scenes.get(scene_id)
        if not plan_scene:
            raise SceneLayoutPayloadError(
                f"Scene layout payload failed: scene_asset_plan is missing scene_id={scene_id!r}.",
            )

        selected_visual = _selected_visual(plan_scene, scene_id=scene_id)
        scene_warnings = _as_string_list(plan_scene.get("warnings"))
        text_blocks = _build_scene_text_blocks(scene_id, video_offer, plan_scene)
        if not text_blocks:
            scene_warnings = _dedupe_strings(
                scene_warnings
                + [f"Scene '{scene_id}' has no text blocks from available VideoOffer facts."]
            )

        payload = {
            "scene_id": scene_id,
            "scene_type": str(spec["scene_type"]),
            "duration_sec": _float_or_default(plan_scene.get("duration_sec"), 0.0),
            "selected_visual": selected_visual,
            "canvas": dict(CANVAS),
            "safe_zone_profile": str(spec["safe_zone_profile"]),
            "text_blocks": text_blocks,
            "motion_hint": str(spec["motion_hint"]),
            "warnings": scene_warnings,
        }
        if scene_id == "telegram_cta":
            platform_variants = _platform_variants(plan_scene)
            if platform_variants:
                payload["platform_variants"] = platform_variants
        scenes.append(payload)

    return {
        "offer_id": video_offer.offer_id,
        "template": _pick_text(scene_asset_plan.get("template")) or "single_offer_gameplay_first",
        "format": _pick_text(scene_asset_plan.get("format")) or "vertical_1080x1920",
        "scene_count": len(scenes),
        "scenes": scenes,
        "warnings": warnings,
    }


def _build_scene_text_blocks(
    scene_id: str,
    video_offer: VideoOffer,
    plan_scene: dict[str, Any],
) -> list[dict[str, Any]]:
    if scene_id == "hook":
        return _build_hook_blocks(video_offer, plan_scene)
    if scene_id == "identity":
        return _build_identity_blocks(video_offer, plan_scene)
    if scene_id == "offer_proof":
        return _build_offer_proof_blocks(video_offer, plan_scene)
    if scene_id == "trust_or_deadline":
        return _build_trust_or_deadline_blocks(video_offer)
    if scene_id == "telegram_cta":
        return _build_cta_blocks(video_offer, plan_scene)
    raise SceneLayoutPayloadError(f"Scene layout payload failed: unsupported scene_id={scene_id!r}.")


def _build_hook_blocks(video_offer: VideoOffer, plan_scene: dict[str, Any]) -> list[dict[str, Any]]:
    headline = _pick_text(plan_scene.get("primary_text"), video_offer.title)
    title = _pick_text(plan_scene.get("secondary_text"))
    blocks: list[dict[str, Any]] = []
    if headline:
        blocks.append(
            _text_block(
                role="headline",
                text=headline,
                priority=1,
                required=True,
                max_lines=2,
                alignment="center",
                anchor="upper_middle",
                size_class="xl",
            )
        )
    if title and title != headline:
        blocks.append(
            _text_block(
                role="title",
                text=title,
                priority=2,
                required=False,
                max_lines=1,
                alignment="center",
                anchor="upper_middle",
                size_class="md",
            )
        )
    return blocks


def _build_identity_blocks(video_offer: VideoOffer, plan_scene: dict[str, Any]) -> list[dict[str, Any]]:
    title = _pick_text(plan_scene.get("primary_text"), video_offer.title)
    platform_store = _pick_text(plan_scene.get("secondary_text"))
    blocks: list[dict[str, Any]] = []
    if title:
        blocks.append(
            _text_block(
                role="title",
                text=title,
                priority=1,
                required=True,
                max_lines=2,
                alignment="center",
                anchor="upper_middle",
                size_class="lg",
            )
        )
    if platform_store:
        blocks.append(
            _text_block(
                role="platform_store",
                text=platform_store,
                priority=2,
                required=True,
                max_lines=1,
                alignment="center",
                anchor="upper_middle",
                size_class="sm",
            )
        )
    return blocks


def _build_offer_proof_blocks(video_offer: VideoOffer, plan_scene: dict[str, Any]) -> list[dict[str, Any]]:
    facts = _offer_fact_map(_as_string_list(plan_scene.get("facts")))
    badge = facts.get("offer_badge")
    current_price = facts.get("current_price")
    if video_offer.offer_type == "freebie" and not badge:
        badge = _pick_text(current_price, video_offer.current_price_text)
        if badge == current_price:
            current_price = None

    blocks: list[dict[str, Any]] = []
    for role, text, priority, required, size_class in (
        ("offer_badge", badge, 1, bool(badge), "lg"),
        ("current_price", current_price, 2, bool(current_price), "xl"),
        ("old_price", facts.get("old_price"), 3, False, "sm"),
        ("savings", facts.get("savings"), 4, False, "sm"),
    ):
        if not text:
            continue
        blocks.append(
            _text_block(
                role=role,
                text=text,
                priority=priority,
                required=required,
                max_lines=1,
                alignment="center",
                anchor="middle_center",
                size_class=size_class,
            )
        )
    return blocks


def _build_trust_or_deadline_blocks(video_offer: VideoOffer) -> list[dict[str, Any]]:
    deadline = _pick_text(video_offer.deadline_text)
    if deadline:
        return [
            _text_block(
                role="deadline",
                text=deadline,
                priority=1,
                required=True,
                max_lines=2,
                alignment="center",
                anchor="lower_middle",
                size_class="md",
            )
        ]

    blocks: list[dict[str, Any]] = []
    for role, text, priority, required in (
        ("positive_score", _pick_text(video_offer.positive_percent_text), 1, bool(video_offer.positive_percent_text)),
        ("reviews", _pick_text(video_offer.reviews_text), 2, bool(video_offer.reviews_text)),
    ):
        if not text:
            continue
        blocks.append(
            _text_block(
                role=role,
                text=text,
                priority=priority,
                required=required,
                max_lines=1,
                alignment="center",
                anchor="lower_middle",
                size_class="sm" if role == "reviews" else "md",
            )
        )
    return blocks


def _build_cta_blocks(video_offer: VideoOffer, plan_scene: dict[str, Any]) -> list[dict[str, Any]]:
    cta_text = _pick_text(plan_scene.get("primary_text"), video_offer.cta.default)
    blocks: list[dict[str, Any]] = []
    if cta_text:
        blocks.append(
            _text_block(
                role="cta",
                text=cta_text,
                priority=1,
                required=True,
                max_lines=2,
                alignment="center",
                anchor="lower_third",
                size_class="lg",
            )
        )

    variants = _platform_variants(plan_scene)
    for priority, platform in enumerate(CTA_PLATFORM_ORDER, start=2):
        text = _pick_text(variants.get(platform))
        if not text:
            continue
        blocks.append(
            _text_block(
                role=f"cta_{platform}",
                text=text,
                priority=priority,
                required=False,
                max_lines=2,
                alignment="center",
                anchor="lower_third",
                size_class="sm",
            )
        )
    return blocks


def _selected_visual(plan_scene: dict[str, Any], *, scene_id: str) -> dict[str, str]:
    asset_type = _pick_text(plan_scene.get("selected_asset_type"))
    asset_ref = _pick_text(plan_scene.get("selected_asset_ref"))
    if not asset_type or not asset_ref:
        raise SceneLayoutPayloadError(
            f"Scene layout payload failed: selected visual is missing for scene_id={scene_id!r}.",
        )
    return {
        "asset_type": asset_type,
        "asset_ref": asset_ref,
    }


def _platform_variants(plan_scene: dict[str, Any]) -> dict[str, str]:
    raw_variants = plan_scene.get("platform_variants")
    if not isinstance(raw_variants, dict):
        return {}

    cleaned: dict[str, str] = {}
    for platform in CTA_PLATFORM_ORDER:
        text = _pick_text(raw_variants.get(platform))
        if text:
            cleaned[platform] = text
    return cleaned


def _offer_fact_map(facts: list[str]) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for fact in facts:
        normalized = fact.lower()
        if normalized.startswith("now:"):
            mapped["current_price"] = fact
            continue
        if normalized.startswith("was:"):
            mapped["old_price"] = fact
            continue
        if normalized.startswith("save:"):
            mapped["savings"] = fact
            continue
        if "offer_badge" not in mapped:
            mapped["offer_badge"] = fact
    return mapped


def _scene_map(raw_scenes: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw_scenes, list):
        return {}

    mapped: dict[str, dict[str, Any]] = {}
    for raw_scene in raw_scenes:
        if not isinstance(raw_scene, dict):
            continue
        scene_id = _pick_text(raw_scene.get("scene_id"))
        if scene_id:
            mapped[scene_id] = dict(raw_scene)
    return mapped


def _text_block(
    *,
    role: str,
    text: str,
    priority: int,
    required: bool,
    max_lines: int,
    alignment: str,
    anchor: str,
    size_class: str,
) -> dict[str, Any]:
    return {
        "role": role,
        "text": text,
        "priority": priority,
        "required": required,
        "max_lines": max_lines,
        "alignment": alignment,
        "anchor": anchor,
        "size_class": size_class,
    }


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


def _float_or_default(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _pick_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        cleaned = str(value).strip()
        if cleaned:
            return cleaned
    return None
