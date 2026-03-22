from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
FONT_DIR = ROOT / "video_generator" / "assets" / "fonts"
HERO_PATH = (
    ROOT
    / "video_generator"
    / "assets"
    / "cache"
    / "8e1d77c0450dd201fecb8df9dc7603bbfc06b5966968d6a2573e7d8c8d48af74.png"
)
OUTPUT_DIR = ROOT / "output" / "reference_cards"
CARD_SIZE = (1280, 720)
CANVAS_W, CANVAS_H = CARD_SIZE
WHITE = "#f5f7fb"


@dataclass(frozen=True)
class CardCopy:
    category: str
    badge: str
    title: str
    deadline: str
    previous_price: str
    brand: str


@dataclass(frozen=True)
class Variation:
    slug: str
    name: str
    hero_height: int
    hero_focus: tuple[float, float]
    slab_rect: tuple[int, int, int, int]
    slab_fill: tuple[int, int, int, int]
    slab_outline: tuple[int, int, int, int]
    label_fill: tuple[int, int, int, int]
    badge_fill: str
    badge_text: str
    accent: str
    accent_style: str
    deadline_fill: tuple[int, int, int, int]
    deadline_outline: tuple[int, int, int, int]
    price_color: str
    title_color: str
    muted_text: str
    hero_tint: tuple[int, int, int, int]
    bg_tint: str
    bg_blend: float
    seam_glow: str
    inner_panel: bool = False
    badge_radius: int = 22


COPY = CardCopy(
    category="EPIC FREEBIE",
    badge="\u0411\u0415\u0417\u041a\u041e\u0428\u0422\u041e\u0412\u041d\u041e",
    title="Turnip Boy Robs a Bank",
    deadline="\u0437\u0430\u0431\u0440\u0430\u0442\u0438 \u0434\u043e 12 \u0431\u0435\u0440\u0435\u0437\u043d\u044f, 18:00",
    previous_price="699 \u0433\u0440\u043d",
    brand="YOTO",
)

VARIATIONS = (
    Variation(
        slug="yoto_turnip_boy_v1_aurora_slab",
        name="Aurora Slab",
        hero_height=392,
        hero_focus=(0.50, 0.68),
        slab_rect=(28, 334, 1252, 684),
        slab_fill=(8, 12, 18, 234),
        slab_outline=(255, 255, 255, 18),
        label_fill=(11, 15, 20, 212),
        badge_fill="#1fcb78",
        badge_text="#ffffff",
        accent="#39d98a",
        accent_style="bar",
        deadline_fill=(22, 54, 40, 230),
        deadline_outline=(72, 196, 130, 66),
        price_color="#9eabbf",
        title_color=WHITE,
        muted_text="#ccd5e1",
        hero_tint=(7, 12, 18, 78),
        bg_tint="#0b1017",
        bg_blend=0.42,
        seam_glow="#23d7a7",
    ),
    Variation(
        slug="yoto_turnip_boy_v2_signal_frame",
        name="Signal Frame",
        hero_height=404,
        hero_focus=(0.55, 0.66),
        slab_rect=(42, 350, 1238, 688),
        slab_fill=(7, 11, 16, 238),
        slab_outline=(43, 209, 137, 56),
        label_fill=(13, 18, 24, 216),
        badge_fill="#17c66d",
        badge_text="#ffffff",
        accent="#1fd68a",
        accent_style="rail",
        deadline_fill=(18, 44, 34, 230),
        deadline_outline=(53, 168, 110, 82),
        price_color="#aeb9c9",
        title_color=WHITE,
        muted_text="#d1dae6",
        hero_tint=(8, 13, 18, 86),
        bg_tint="#0b1016",
        bg_blend=0.46,
        seam_glow="#19c77d",
    ),
    Variation(
        slug="yoto_turnip_boy_v3_obsidian_glass",
        name="Obsidian Glass",
        hero_height=384,
        hero_focus=(0.50, 0.64),
        slab_rect=(34, 328, 1246, 686),
        slab_fill=(10, 12, 18, 214),
        slab_outline=(255, 255, 255, 30),
        label_fill=(11, 16, 22, 206),
        badge_fill="#f5f7fb",
        badge_text="#10151d",
        accent="#d7b575",
        accent_style="line",
        deadline_fill=(21, 28, 36, 226),
        deadline_outline=(215, 181, 115, 88),
        price_color="#bcc5d4",
        title_color=WHITE,
        muted_text="#d5dbe5",
        hero_tint=(8, 12, 19, 90),
        bg_tint="#0a0e15",
        bg_blend=0.50,
        seam_glow="#d7b575",
        inner_panel=True,
        badge_radius=20,
    ),
    Variation(
        slug="yoto_turnip_boy_v4_broadcast_minimal",
        name="Broadcast Minimal",
        hero_height=388,
        hero_focus=(0.48, 0.67),
        slab_rect=(0, 354, 1280, 720),
        slab_fill=(7, 10, 14, 244),
        slab_outline=(255, 255, 255, 0),
        label_fill=(11, 15, 20, 216),
        badge_fill="#1fcb78",
        badge_text="#ffffff",
        accent="#66e0b0",
        accent_style="corner",
        deadline_fill=(18, 48, 36, 238),
        deadline_outline=(84, 216, 160, 60),
        price_color="#9aa7bc",
        title_color="#f9fbff",
        muted_text="#d5dde8",
        hero_tint=(8, 13, 18, 88),
        bg_tint="#090d13",
        bg_blend=0.54,
        seam_glow="#1fcb78",
    ),
)


def load_font(size: int, *, bold: bool) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        ("segoeuib.ttf", "arialbd.ttf", "tahomabd.ttf") if bold else ("segoeui.ttf", "arial.ttf", "tahoma.ttf")
    )
    for name in candidates:
        path = FONT_DIR / name
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def rgba(color: str | tuple[int, int, int, int], alpha: int | None = None) -> tuple[int, int, int, int]:
    if isinstance(color, tuple):
        if len(color) == 4:
            return color
        return (color[0], color[1], color[2], 255 if alpha is None else alpha)
    parsed = ImageColor.getrgb(color)
    return (parsed[0], parsed[1], parsed[2], 255 if alpha is None else alpha)


def build_background(hero: Image.Image, variation: Variation) -> Image.Image:
    background = ImageOps.fit(hero, CARD_SIZE, centering=(0.5, 0.5))
    background = background.filter(ImageFilter.GaussianBlur(radius=24))
    return Image.blend(background, Image.new("RGB", CARD_SIZE, variation.bg_tint), variation.bg_blend)


def build_hero(hero: Image.Image, variation: Variation) -> Image.Image:
    hero_strip = ImageOps.fit(hero, (CANVAS_W, variation.hero_height), centering=variation.hero_focus)
    overlay = Image.new("RGBA", hero_strip.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    top = rgba(variation.hero_tint)
    bottom = rgba(variation.hero_tint, min(variation.hero_tint[3] + 62, 190))
    for y in range(hero_strip.height):
        ratio = y / max(hero_strip.height - 1, 1)
        color = tuple(int(top[idx] + (bottom[idx] - top[idx]) * ratio) for idx in range(4))
        draw.line((0, y, hero_strip.width, y), fill=color)
    return Image.alpha_composite(hero_strip.convert("RGBA"), overlay).convert("RGB")


def draw_shadowed_panel(
    canvas: Image.Image,
    rect: tuple[int, int, int, int],
    *,
    radius: int,
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int] | None,
    outline_width: int = 1,
    shadow_color: tuple[int, int, int, int] = (0, 0, 0, 120),
    shadow_offset: tuple[int, int] = (0, 18),
    shadow_blur: int = 26,
) -> Image.Image:
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    shadow_rect = (
        rect[0] + shadow_offset[0],
        rect[1] + shadow_offset[1],
        rect[2] + shadow_offset[0],
        rect[3] + shadow_offset[1],
    )
    sdraw.rounded_rectangle(shadow_rect, radius=radius, fill=shadow_color)
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=shadow_blur))
    merged = Image.alpha_composite(canvas.convert("RGBA"), shadow)
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rounded_rectangle(rect, radius=radius, fill=fill)
    if outline is not None and outline[3] > 0:
        odraw.rounded_rectangle(rect, radius=radius, outline=outline, width=outline_width)
    return Image.alpha_composite(merged, overlay)


def draw_pill(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    *,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: tuple[int, int, int, int] | str,
    text_fill: str,
    padding_x: int,
    padding_y: int,
    radius: int,
    outline: tuple[int, int, int, int] | None = None,
    outline_width: int = 1,
) -> tuple[int, int, int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    rect = (
        x,
        y,
        x + (bbox[2] - bbox[0]) + padding_x * 2,
        y + (bbox[3] - bbox[1]) + padding_y * 2,
    )
    draw.rounded_rectangle(rect, radius=radius, fill=fill)
    if outline is not None and outline[3] > 0:
        draw.rounded_rectangle(rect, radius=radius, outline=outline, width=outline_width)
    draw.text((x + padding_x, y + padding_y - 1), text, font=font, fill=text_fill)
    return rect


def measure_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> float:
    return draw.textlength(text, font=font)


def ellipsize(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> str:
    trimmed = text.rstrip()
    while trimmed and measure_text(draw, trimmed + "...", font) > max_width:
        trimmed = trimmed[:-1].rstrip()
    return (trimmed + "...") if trimmed else "..."


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
    *,
    max_lines: int,
) -> tuple[list[str], bool]:
    words = text.split()
    if not words:
        return [""], False

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        proposal = f"{current} {word}"
        if measure_text(draw, proposal, font) <= max_width:
            current = proposal
            continue
        lines.append(current)
        current = word

    lines.append(current)
    if len(lines) <= max_lines:
        return lines, False

    clipped = lines[: max_lines - 1]
    remainder = " ".join(lines[max_lines - 1 :])
    clipped.append(ellipsize(draw, remainder, font, max_width))
    return clipped, True


def fit_title(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    max_width: int,
    max_lines: int,
    size_candidates: tuple[int, ...],
) -> tuple[list[str], ImageFont.FreeTypeFont | ImageFont.ImageFont]:
    fallback_font: ImageFont.FreeTypeFont | ImageFont.ImageFont = load_font(size_candidates[-1], bold=True)
    fallback_lines = [text]
    for size in size_candidates:
        font = load_font(size, bold=True)
        lines, clipped = wrap_text(draw, text, font, max_width, max_lines=max_lines)
        fallback_font = font
        fallback_lines = lines
        if not clipped:
            return lines, font
    return fallback_lines, fallback_font


def text_block_height(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    gap: int,
) -> int:
    total = 0
    for index, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        total += bbox[3] - bbox[1]
        if index < len(lines) - 1:
            total += gap
    return total


def draw_text_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    x: int,
    y: int,
    *,
    fill: str,
    gap: int,
) -> None:
    cursor = y
    for line in lines:
        draw.text((x, cursor), line, font=font, fill=fill)
        bbox = draw.textbbox((0, 0), line, font=font)
        cursor += (bbox[3] - bbox[1]) + gap


def draw_lockup(draw: ImageDraw.ImageDraw, variation: Variation, rect: tuple[int, int, int, int]) -> None:
    font = load_font(24, bold=True)
    y = rect[3] - 50
    bbox = draw.textbbox((0, 0), COPY.brand, font=font)
    width = bbox[2] - bbox[0]
    x = rect[2] - width - 42
    draw.line((x - 38, y + 13, x - 12, y + 13), fill=variation.accent, width=3)
    draw.text((x, y), COPY.brand, font=font, fill=variation.muted_text)


def draw_accent(canvas: Image.Image, variation: Variation, slab_rect: tuple[int, int, int, int]) -> Image.Image:
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    if variation.accent_style == "bar":
        draw.rounded_rectangle((slab_rect[0] + 32, slab_rect[1] + 28, slab_rect[0] + 134, slab_rect[1] + 36), radius=4, fill=variation.accent)
    elif variation.accent_style == "rail":
        draw.rounded_rectangle((slab_rect[0] + 18, slab_rect[1] + 38, slab_rect[0] + 24, slab_rect[3] - 34), radius=3, fill=variation.accent)
    elif variation.accent_style == "line":
        draw.rounded_rectangle((slab_rect[0] + 42, slab_rect[1] + 30, slab_rect[2] - 42, slab_rect[1] + 33), radius=2, fill=variation.accent)
    elif variation.accent_style == "corner":
        draw.rounded_rectangle((slab_rect[0] + 40, slab_rect[1] + 34, slab_rect[0] + 124, slab_rect[1] + 40), radius=3, fill=variation.accent)
        draw.rounded_rectangle((slab_rect[0] + 40, slab_rect[1] + 34, slab_rect[0] + 46, slab_rect[1] + 112), radius=3, fill=variation.accent)
    return Image.alpha_composite(canvas.convert("RGBA"), overlay)


def add_seam_glow(canvas: Image.Image, y: int, color: str) -> Image.Image:
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((0, y - 2, CANVAS_W, y + 2), fill=rgba(color, 78))
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=12))
    return Image.alpha_composite(canvas.convert("RGBA"), overlay)


def render_card(hero: Image.Image, variation: Variation) -> Path:
    canvas = build_background(hero, variation).convert("RGBA")
    hero_strip = build_hero(hero, variation)
    canvas.paste(hero_strip, (0, 0))
    canvas = add_seam_glow(canvas, variation.hero_height - 1, variation.seam_glow)

    slab_rect = variation.slab_rect
    radius = 34 if slab_rect[0] > 0 else 0
    canvas = draw_shadowed_panel(
        canvas,
        slab_rect,
        radius=radius,
        fill=variation.slab_fill,
        outline=variation.slab_outline,
        outline_width=1,
        shadow_offset=(0, 16),
        shadow_blur=28,
    )

    if variation.inner_panel:
        inner = (slab_rect[0] + 18, slab_rect[1] + 18, slab_rect[2] - 18, slab_rect[3] - 18)
        canvas = draw_shadowed_panel(
            canvas,
            inner,
            radius=28,
            fill=(255, 255, 255, 14),
            outline=(255, 255, 255, 14),
            outline_width=1,
            shadow_color=(0, 0, 0, 0),
            shadow_offset=(0, 0),
            shadow_blur=0,
        )
        slab_rect = inner

    canvas = draw_accent(canvas, variation, slab_rect)
    draw = ImageDraw.Draw(canvas)

    label_font = load_font(27, bold=True)
    badge_font = load_font(26, bold=True)
    body_font = load_font(29, bold=False)
    price_font = load_font(28, bold=False)

    draw_pill(
        draw,
        COPY.category,
        38,
        26,
        font=label_font,
        fill=variation.label_fill,
        text_fill=WHITE,
        padding_x=22,
        padding_y=14,
        radius=22,
    )

    badge_bbox = draw.textbbox((0, 0), COPY.badge, font=badge_font)
    badge_width = (badge_bbox[2] - badge_bbox[0]) + 42
    badge_x = CANVAS_W - badge_width - 36
    badge_y = 28 if variation.slug != "yoto_turnip_boy_v4_broadcast_minimal" else 30
    draw_pill(
        draw,
        COPY.badge,
        badge_x,
        badge_y,
        font=badge_font,
        fill=variation.badge_fill,
        text_fill=variation.badge_text,
        padding_x=21,
        padding_y=13,
        radius=variation.badge_radius,
    )

    title_x = slab_rect[0] + 46
    title_y = slab_rect[1] + (64 if variation.accent_style != "line" else 56)
    title_lines, title_font = fit_title(
        draw,
        COPY.title,
        max_width=slab_rect[2] - slab_rect[0] - 120,
        max_lines=2,
        size_candidates=(80, 76, 72, 68, 64, 60, 56, 52),
    )
    draw_text_lines(draw, title_lines, title_font, title_x, title_y, fill=variation.title_color, gap=8)
    title_bottom = title_y + text_block_height(draw, title_lines, title_font, 8)

    deadline_rect = draw_pill(
        draw,
        COPY.deadline,
        title_x,
        title_bottom + 24,
        font=body_font,
        fill=variation.deadline_fill,
        text_fill=variation.muted_text,
        padding_x=18,
        padding_y=11,
        radius=19,
        outline=variation.deadline_outline,
    )

    draw.text(
        (title_x, deadline_rect[3] + 18),
        f"\u0411\u0443\u043b\u043e {COPY.previous_price}",
        font=price_font,
        fill=variation.price_color,
    )

    if variation.slug == "yoto_turnip_boy_v2_signal_frame":
        meta_font = load_font(20, bold=True)
        meta_text = "PREMIUM GAMING FREEBIE"
        meta_bbox = draw.textbbox((0, 0), meta_text, font=meta_font)
        draw.text((slab_rect[2] - (meta_bbox[2] - meta_bbox[0]) - 44, slab_rect[1] + 42), meta_text, font=meta_font, fill="#8ea0b7")

    if variation.slug == "yoto_turnip_boy_v4_broadcast_minimal":
        divider_y = deadline_rect[3] + 74
        draw.line((title_x, divider_y, slab_rect[2] - 52, divider_y), fill=(255, 255, 255, 24), width=2)

    draw_lockup(draw, variation, slab_rect)

    out_path = OUTPUT_DIR / f"{variation.slug}.png"
    canvas.convert("RGB").save(out_path, format="PNG", optimize=True)
    return out_path


def build_contact_sheet(paths: list[Path], variations: tuple[Variation, ...]) -> Path:
    sheet = Image.new("RGB", (1360, 980), "#0b0f16")
    draw = ImageDraw.Draw(sheet)
    title_font = load_font(38, bold=True)
    body_font = load_font(22, bold=False)
    label_font = load_font(24, bold=True)

    draw.text((56, 34), "YOTO Telegram Card References", font=title_font, fill=WHITE)
    draw.text((56, 86), "Turnip Boy Robs a Bank | 1280x720 exploration set", font=body_font, fill="#99a8bb")

    thumb_w = 592
    thumb_h = 333
    slots = ((56, 140), (712, 140), (56, 532), (712, 532))

    for index, (path, variation, slot) in enumerate(zip(paths, variations, slots), start=1):
        thumb = Image.open(path).convert("RGB")
        thumb = ImageOps.fit(thumb, (thumb_w, thumb_h))
        frame = (slot[0], slot[1], slot[0] + thumb_w, slot[1] + thumb_h)
        shadow = Image.new("RGBA", sheet.size, (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(shadow)
        sdraw.rounded_rectangle((frame[0], frame[1] + 10, frame[2], frame[3] + 10), radius=26, fill=(0, 0, 0, 110))
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=16))
        sheet = Image.alpha_composite(sheet.convert("RGBA"), shadow).convert("RGB")
        mask = Image.new("L", (thumb_w, thumb_h), 0)
        mdraw = ImageDraw.Draw(mask)
        mdraw.rounded_rectangle((0, 0, thumb_w - 1, thumb_h - 1), radius=26, fill=255)
        sheet.paste(thumb, slot, mask)
        draw = ImageDraw.Draw(sheet)
        draw.text((slot[0], slot[1] + thumb_h + 16), f"{index}. {variation.name}", font=label_font, fill=WHITE)
        draw.text((slot[0], slot[1] + thumb_h + 48), variation.slug.replace("_", " "), font=body_font, fill="#8e9db1")

    out_path = OUTPUT_DIR / "yoto_turnip_boy_contact_sheet.png"
    sheet.save(out_path, format="PNG", optimize=True)
    return out_path


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not HERO_PATH.exists():
        raise FileNotFoundError(f"Hero artwork not found: {HERO_PATH}")

    hero = Image.open(HERO_PATH).convert("RGB")
    rendered_paths = [render_card(hero, variation) for variation in VARIATIONS]
    build_contact_sheet(rendered_paths, VARIATIONS)

    for path in rendered_paths:
        print(path)
    print(OUTPUT_DIR / "yoto_turnip_boy_contact_sheet.png")


if __name__ == "__main__":
    main()