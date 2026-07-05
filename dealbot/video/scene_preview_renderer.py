from __future__ import annotations

import os
from pathlib import Path
from typing import Any

CANVAS = {"width": 1080, "height": 1920}
CANVAS_SIZE = (CANVAS["width"], CANVAS["height"])
EXPECTED_SCENES = (
    {"order": 1, "scene_id": "hook"},
    {"order": 2, "scene_id": "identity"},
    {"order": 3, "scene_id": "offer_proof"},
    {"order": 4, "scene_id": "trust_or_deadline"},
    {"order": 5, "scene_id": "telegram_cta"},
)
SAFE_ZONE_PROFILES = {
    "upper_middle_center": (96, 140, 984, 760),
    "upper_middle_title_stack": (96, 160, 984, 820),
    "middle_offer_stack": (80, 500, 1000, 1240),
    "lower_middle_fact_stack": (100, 860, 980, 1450),
    "lower_third_cta": (90, 1140, 990, 1730),
}
ANCHOR_RECTS = {
    "upper_middle": (90, 120, 990, 820),
    "middle_center": (80, 460, 1000, 1280),
    "lower_middle": (90, 820, 990, 1500),
    "lower_third": (90, 1120, 990, 1760),
}
SUPPORTED_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp"})
ENV_FONT_KEYS = ("YOTO_SCENE_PREVIEW_FONT_PATH", "YOTO_VIDEO_PREVIEW_FONT_PATH")
FALLBACK_FONT_PATHS = (
    r"C:\Windows\Fonts\ARIAL_UNICODE_MS.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\calibri.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
)
SIZE_CLASS_POINTS = {
    "xl": 120,
    "lg": 88,
    "md": 60,
    "sm": 42,
}
MIN_FONT_SIZE = 22
OVERLAY_RGBA = (8, 10, 14, 104)
ROLE_COLORS = {
    "headline": (255, 255, 255),
    "title": (255, 255, 255),
    "platform_store": (220, 225, 233),
    "offer_badge": (255, 216, 116),
    "current_price": (255, 255, 255),
    "old_price": (216, 216, 216),
    "savings": (180, 247, 169),
    "deadline": (255, 226, 161),
    "positive_score": (191, 244, 181),
    "reviews": (232, 232, 232),
    "cta": (255, 245, 211),
    "cta_tiktok": (240, 240, 240),
    "cta_shorts": (240, 240, 240),
    "cta_reels": (240, 240, 240),
}


class ScenePreviewRenderError(ValueError):
    pass


def render_scene_previews(renderer_input: dict[str, Any], output_dir: str | Path) -> list[Path]:
    if not isinstance(renderer_input, dict):
        raise ScenePreviewRenderError("Scene preview render failed: renderer_input must be a dict.")

    _validate_renderer_input(renderer_input)
    output_path = _resolve_output_dir(output_dir)
    font_path = _resolve_font_path()

    rendered_images: list[tuple[str, Any]] = []
    for expected_scene, scene_payload in zip(EXPECTED_SCENES, renderer_input["scenes"], strict=True):
        order = int(expected_scene["order"])
        scene_id = str(expected_scene["scene_id"])
        filename = f"{order:02d}_{scene_id}.png"
        rendered_images.append((filename, _render_scene_image(scene_payload, font_path=font_path)))

    output_path.mkdir(parents=True, exist_ok=True)
    written_paths: list[Path] = []
    for filename, image in rendered_images:
        target_path = output_path / filename
        image.save(target_path, format="PNG")
        image.close()
        written_paths.append(target_path.resolve())
    return written_paths


def _validate_renderer_input(renderer_input: dict[str, Any]) -> None:
    canvas = renderer_input.get("canvas")
    if not isinstance(canvas, dict):
        raise ScenePreviewRenderError("Scene preview render failed: renderer_input.canvas must be a dict.")
    if int(canvas.get("width", 0)) != CANVAS["width"] or int(canvas.get("height", 0)) != CANVAS["height"]:
        raise ScenePreviewRenderError(
            f"Scene preview render failed: renderer_input.canvas must be {CANVAS['width']}x{CANVAS['height']}.",
        )

    scenes = renderer_input.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != len(EXPECTED_SCENES):
        raise ScenePreviewRenderError(
            f"Scene preview render failed: renderer_input must contain exactly {len(EXPECTED_SCENES)} scenes.",
        )

    for expected, scene_payload in zip(EXPECTED_SCENES, scenes, strict=True):
        if not isinstance(scene_payload, dict):
            raise ScenePreviewRenderError("Scene preview render failed: renderer_input scenes must be dicts.")
        scene_id = str(expected["scene_id"])
        order = int(expected["order"])
        if _pick_text(scene_payload.get("scene_id")) != scene_id:
            raise ScenePreviewRenderError(
                f"Scene preview render failed: expected scene_id={scene_id!r}, got {scene_payload.get('scene_id')!r}.",
            )
        if _int_or_none(scene_payload.get("order")) != order:
            raise ScenePreviewRenderError(
                f"Scene preview render failed: expected order={order} for scene_id={scene_id!r}.",
            )
        if not isinstance(scene_payload.get("visual"), dict):
            raise ScenePreviewRenderError(
                f"Scene preview render failed: visual must be a dict for scene_id={scene_id!r}.",
            )
        if not isinstance(scene_payload.get("text_blocks"), list):
            raise ScenePreviewRenderError(
                f"Scene preview render failed: text_blocks must be a list for scene_id={scene_id!r}.",
            )
        safe_zone_profile = _pick_text(scene_payload.get("safe_zone_profile"))
        if safe_zone_profile not in SAFE_ZONE_PROFILES:
            raise ScenePreviewRenderError(
                f"Scene preview render failed: unsupported safe_zone_profile={safe_zone_profile!r} "
                f"for scene_id={scene_id!r}.",
            )


def _resolve_output_dir(output_dir: str | Path) -> Path:
    raw_output = Path(output_dir)
    resolved = raw_output if raw_output.is_absolute() else (Path.cwd() / raw_output)
    return resolved.resolve()


def _resolve_font_path() -> Path:
    for env_key in ENV_FONT_KEYS:
        raw_value = str(os.environ.get(env_key) or "").strip()
        if not raw_value:
            continue
        return _validate_font_path(Path(raw_value), source=env_key)

    for candidate in FALLBACK_FONT_PATHS:
        path = Path(candidate)
        if path.exists() and path.is_file():
            return _validate_font_path(path, source="fallback")

    raise ScenePreviewRenderError(
        "Scene preview render failed: no usable local Unicode font exists. "
        f"Set one of {ENV_FONT_KEYS!r} to a local .ttf/.otf font path.",
    )


def _validate_font_path(path: Path, *, source: str) -> Path:
    if _looks_like_remote_ref(str(path)):
        raise ScenePreviewRenderError(
            f"Scene preview render failed: font path from {source} must be local, not remote: {path}",
        )

    resolved = path if path.is_absolute() else (Path.cwd() / path)
    resolved = resolved.resolve()
    if not resolved.exists() or not resolved.is_file():
        raise ScenePreviewRenderError(
            f"Scene preview render failed: font file does not exist: {resolved}",
        )
    if resolved.suffix.lower() not in {".ttf", ".otf", ".ttc"}:
        raise ScenePreviewRenderError(
            f"Scene preview render failed: unsupported font format for {resolved}.",
        )
    return resolved


def _render_scene_image(scene_payload: dict[str, Any], *, font_path: Path):
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    scene_id = _pick_text(scene_payload.get("scene_id")) or "unknown_scene"
    background_path = _resolve_local_visual_path(scene_payload.get("visual"), scene_id=scene_id)
    with Image.open(background_path) as source_image:
        background = ImageOps.fit(
            source_image.convert("RGBA"),
            CANVAS_SIZE,
            method=Image.Resampling.LANCZOS,
        )

    overlay = Image.new("RGBA", CANVAS_SIZE, OVERLAY_RGBA)
    composed = Image.alpha_composite(background, overlay)
    draw = ImageDraw.Draw(composed)
    safe_rect = SAFE_ZONE_PROFILES[_pick_text(scene_payload.get("safe_zone_profile")) or ""]
    text_groups = _group_blocks_by_anchor(scene_payload.get("text_blocks"))
    for anchor, blocks in text_groups:
        render_rect = _intersect_rect(safe_rect, ANCHOR_RECTS.get(anchor, safe_rect))
        prepared_blocks = _prepare_blocks_for_rect(
            draw=draw,
            blocks=blocks,
            rect=render_rect,
            font_path=font_path,
            scene_id=scene_id,
        )
        _draw_prepared_blocks(draw=draw, prepared_blocks=prepared_blocks, rect=render_rect)

    return composed.convert("RGB")


def _resolve_local_visual_path(raw_visual: Any, *, scene_id: str) -> Path:
    if not isinstance(raw_visual, dict):
        raise ScenePreviewRenderError(
            f"Scene preview render failed: visual must be a dict for scene_id={scene_id!r}.",
        )

    asset_ref = _pick_text(raw_visual.get("asset_ref"))
    if not asset_ref:
        raise ScenePreviewRenderError(
            f"Scene preview render failed: visual.asset_ref is missing for scene_id={scene_id!r}.",
        )
    if _looks_like_remote_ref(asset_ref):
        raise ScenePreviewRenderError(
            f"Scene preview render failed: remote visual URLs are not allowed for scene_id={scene_id!r}: {asset_ref}",
        )

    raw_path = Path(asset_ref)
    resolved = raw_path if raw_path.is_absolute() else (Path.cwd() / raw_path)
    resolved = resolved.resolve()
    if not resolved.exists() or not resolved.is_file():
        raise ScenePreviewRenderError(
            f"Scene preview render failed: no usable local visual exists for scene_id={scene_id!r}: {resolved}",
        )
    if resolved.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
        raise ScenePreviewRenderError(
            f"Scene preview render failed: visual must be a local still image for scene_id={scene_id!r}: {resolved}",
        )
    return resolved


def _group_blocks_by_anchor(raw_blocks: Any) -> list[tuple[str, list[dict[str, Any]]]]:
    if not isinstance(raw_blocks, list):
        return []

    sorted_blocks = sorted(
        [dict(block) for block in raw_blocks if isinstance(block, dict)],
        key=lambda block: (_int_or_none(block.get("priority")) or 999),
    )
    grouped: list[tuple[str, list[dict[str, Any]]]] = []
    for block in sorted_blocks:
        anchor = _pick_text(block.get("anchor")) or "middle_center"
        if grouped and grouped[-1][0] == anchor:
            grouped[-1][1].append(block)
            continue
        grouped.append((anchor, [block]))
    return grouped


def _prepare_blocks_for_rect(
    *,
    draw,
    blocks: list[dict[str, Any]],
    rect: tuple[int, int, int, int],
    font_path: Path,
    scene_id: str,
) -> list[dict[str, Any]]:
    rect_width = rect[2] - rect[0]
    rect_height = rect[3] - rect[1]
    inner_padding = 26
    max_width = rect_width - (inner_padding * 2)
    max_height = rect_height - (inner_padding * 2)
    if max_width <= 0 or max_height <= 0:
        raise ScenePreviewRenderError(
            f"Scene preview render failed: safe zone is too small for scene_id={scene_id!r}.",
        )

    for step in range(0, 16):
        scale = 1.0 - (step * 0.05)
        prepared: list[dict[str, Any]] = []
        total_height = 0
        failed = False

        for block in blocks:
            size_class = _pick_text(block.get("size_class")) or "md"
            base_size = SIZE_CLASS_POINTS.get(size_class, SIZE_CLASS_POINTS["md"])
            font_size = max(int(round(base_size * scale)), MIN_FONT_SIZE)
            font = _load_font(font_path, font_size)
            lines = _wrap_text_to_width(
                draw=draw,
                text=_pick_text(block.get("text")) or "",
                font=font,
                max_width=max_width,
                max_lines=max(_int_or_none(block.get("max_lines")) or 1, 1),
            )
            if lines is None:
                failed = True
                break

            spacing = max(int(round(font_size * 0.18)), 6)
            text = "\n".join(lines)
            bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=spacing, align=_text_align(block))
            block_height = bbox[3] - bbox[1]
            block_width = bbox[2] - bbox[0]
            prepared.append(
                {
                    "block": block,
                    "font": font,
                    "text": text,
                    "spacing": spacing,
                    "width": block_width,
                    "height": block_height,
                }
            )
            total_height += block_height

        if failed:
            continue

        group_gap = max(int(round((prepared[0]["font"].size if prepared else MIN_FONT_SIZE) * 0.20)), 12)
        total_height += group_gap * max(len(prepared) - 1, 0)
        if total_height <= max_height:
            for item in prepared:
                item["group_gap"] = group_gap
            return prepared

    raise ScenePreviewRenderError(
        f"Scene preview render failed: text does not fit inside safe bounds for scene_id={scene_id!r}.",
    )


def _draw_prepared_blocks(*, draw, prepared_blocks: list[dict[str, Any]], rect: tuple[int, int, int, int]) -> None:
    if not prepared_blocks:
        return

    total_height = sum(item["height"] for item in prepared_blocks)
    total_height += prepared_blocks[0]["group_gap"] * max(len(prepared_blocks) - 1, 0)
    y = rect[1] + max(((rect[3] - rect[1]) - total_height) // 2, 0)

    for item in prepared_blocks:
        block = item["block"]
        font = item["font"]
        text = item["text"]
        spacing = item["spacing"]
        width = item["width"]
        height = item["height"]
        alignment = _text_align(block)
        fill = ROLE_COLORS.get(_pick_text(block.get("role")) or "", (255, 255, 255))
        stroke_width = max(int(round(font.size * 0.06)), 1)

        if alignment == "right":
            x = rect[2] - 26 - width
        elif alignment == "left":
            x = rect[0] + 26
        else:
            x = rect[0] + ((rect[2] - rect[0]) - width) / 2

        draw.multiline_text(
            (x, y),
            text,
            font=font,
            fill=fill,
            spacing=spacing,
            align=alignment,
            stroke_width=stroke_width,
            stroke_fill=(0, 0, 0),
        )
        y += height + item["group_gap"]


def _wrap_text_to_width(*, draw, text: str, font, max_width: int, max_lines: int) -> list[str] | None:
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return []

    lines: list[str] = []
    words = normalized.split(" ")
    current = ""

    for word in words:
        candidate = word if not current else f"{current} {word}"
        if _measure_text_width(draw, candidate, font) <= max_width:
            current = candidate
            continue

        if current:
            lines.append(current)
            current = ""
            if len(lines) >= max_lines:
                return None

        oversized_parts = _split_word_to_width(draw, word, font, max_width)
        for index, part in enumerate(oversized_parts):
            is_last_part = index == len(oversized_parts) - 1
            if is_last_part:
                current = part
                continue
            lines.append(part)
            if len(lines) >= max_lines:
                return None

    if current:
        lines.append(current)

    return lines if len(lines) <= max_lines else None


def _split_word_to_width(draw, word: str, font, max_width: int) -> list[str]:
    parts: list[str] = []
    current = ""
    for character in word:
        candidate = f"{current}{character}"
        if current and _measure_text_width(draw, candidate, font) > max_width:
            parts.append(current)
            current = character
            continue
        current = candidate

    if current:
        parts.append(current)
    return parts


def _measure_text_width(draw, text: str, font) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _load_font(font_path: Path, size: int):
    from PIL import ImageFont

    try:
        return ImageFont.truetype(str(font_path), size=size)
    except OSError as exc:
        raise ScenePreviewRenderError(
            f"Scene preview render failed: could not load font {font_path}: {exc}",
        ) from exc


def _intersect_rect(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    return (
        max(a[0], b[0]),
        max(a[1], b[1]),
        min(a[2], b[2]),
        min(a[3], b[3]),
    )


def _text_align(block: dict[str, Any]) -> str:
    alignment = (_pick_text(block.get("alignment")) or "center").lower()
    return alignment if alignment in {"left", "center", "right"} else "center"


def _looks_like_remote_ref(value: str) -> bool:
    lowered = value.lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def _pick_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        cleaned = str(value).strip()
        if cleaned:
            return cleaned
    return None


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
