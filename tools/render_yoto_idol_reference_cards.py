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
class Direction:
    slug: str
    name: str
    summary: str


COPY = CardCopy(
    category="EPIC FREEBIE",
    badge="\u0411\u0415\u0417\u041a\u041e\u0428\u0422\u041e\u0412\u041d\u041e",
    title="Turnip Boy Robs a Bank",
    deadline="\u0437\u0430\u0431\u0440\u0430\u0442\u0438 \u0434\u043e 12 \u0431\u0435\u0440\u0435\u0437\u043d\u044f, 18:00",
    previous_price="699 \u0433\u0440\u043d",
    brand="YOTO",
)

DIRECTIONS = (
    Direction(
        slug="yoto_turnip_boy_idol_1_titan_broadcast",
        name="Titan Broadcast",
        summary="Hero-dominant lower-third with a loud green badge and cinematic energy.",
    ),
    Direction(
        slug="yoto_turnip_boy_idol_2_night_raid_editorial",
        name="Night Raid Editorial",
        summary="Premium editorial slab with a high-contrast stamp badge and polished contrast.",
    ),
    Direction(
        slug="yoto_turnip_boy_idol_3_arena_pulse",
        name="Arena Pulse",
        summary="Esports-style broadcast graphic with layered bands and a neon impact badge.",
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


def blend_background(hero: Image.Image, tint: str, blend: float) -> Image.Image:
    background = ImageOps.fit(hero, CARD_SIZE, centering=(0.5, 0.5)).filter(ImageFilter.GaussianBlur(radius=26))
    return Image.blend(background, Image.new("RGB", CARD_SIZE, tint), blend)


def crop_hero(hero: Image.Image, *, height: int, focus: tuple[float, float]) -> Image.Image:
    return ImageOps.fit(hero, (CANVAS_W, height), centering=focus)


def composite(base: Image.Image, overlay: Image.Image) -> Image.Image:
    return Image.alpha_composite(base.convert("RGBA"), overlay)


def add_vertical_gradient(
    canvas: Image.Image,
    rect: tuple[int, int, int, int],
    top: tuple[int, int, int, int],
    bottom: tuple[int, int, int, int],
) -> Image.Image:
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    x0, y0, x1, y1 = rect
    height = max(y1 - y0, 1)
    for offset in range(height):
        ratio = offset / max(height - 1, 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(4))
        draw.line((x0, y0 + offset, x1, y0 + offset), fill=color)
    return composite(canvas, overlay)


def add_glow(canvas: Image.Image, center: tuple[int, int], radius: int, color: str, alpha: int) -> Image.Image:
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    cx, cy = center
    for index in range(6, 0, -1):
        current_radius = int(radius * index / 6)
        current_alpha = max(4, int(alpha * (index / 6) ** 2))
        draw.ellipse(
            (cx - current_radius, cy - current_radius, cx + current_radius, cy + current_radius),
            fill=rgba(color, current_alpha),
        )
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=max(12, radius // 5)))
    return composite(canvas, overlay)


def add_beam(canvas: Image.Image, points: list[tuple[int, int]], color: str, alpha: int, blur: int) -> Image.Image:
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.polygon(points, fill=rgba(color, alpha))
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=blur))
    return composite(canvas, overlay)


def add_scanlines(canvas: Image.Image, height: int, alpha: int = 18, step: int = 6) -> Image.Image:
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(0, height, step):
        draw.line((0, y, CANVAS_W, y), fill=(255, 255, 255, alpha), width=1)
    return composite(canvas, overlay)


def panel_shadow(canvas: Image.Image, points: list[tuple[int, int]], *, offset: tuple[int, int], blur: int, alpha: int) -> Image.Image:
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    shifted = [(x + offset[0], y + offset[1]) for x, y in points]
    draw.polygon(shifted, fill=(0, 0, 0, alpha))
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=blur))
    return composite(canvas, overlay)


def draw_panel(
    canvas: Image.Image,
    points: list[tuple[int, int]],
    *,
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int] | None = None,
    outline_width: int = 2,
) -> Image.Image:
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.polygon(points, fill=fill)
    if outline is not None and outline[3] > 0:
        draw.line(points + [points[0]], fill=outline, width=outline_width)
    return composite(canvas, overlay)


def text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> float:
    return draw.textlength(text, font=font)


def ellipsize(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont, max_width: int) -> str:
    trimmed = text.rstrip()
    while trimmed and text_width(draw, trimmed + "...", font) > max_width:
        trimmed = trimmed[:-1].rstrip()
    return trimmed + "..." if trimmed else "..."


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
        candidate = f"{current} {word}"
        if text_width(draw, candidate, font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    if len(lines) <= max_lines:
        return lines, False
    clipped = lines[: max_lines - 1]
    clipped.append(ellipsize(draw, " ".join(lines[max_lines - 1 :]), font, max_width))
    return clipped, True


def fit_title(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    max_width: int,
    max_lines: int,
    candidates: tuple[int, ...],
) -> tuple[list[str], ImageFont.FreeTypeFont | ImageFont.ImageFont]:
    fallback_font = load_font(candidates[-1], bold=True)
    fallback_lines = [text]
    for size in candidates:
        font = load_font(size, bold=True)
        lines, clipped = wrap_text(draw, text, font, max_width, max_lines=max_lines)
        fallback_font = font
        fallback_lines = lines
        if not clipped:
            return lines, font
    return fallback_lines, fallback_font


def draw_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    x: int,
    y: int,
    *,
    fill: str,
    gap: int,
    shadow: tuple[int, int, int, int] | None = None,
    shadow_offset: tuple[int, int] = (0, 4),
) -> int:
    cursor = y
    for line in lines:
        if shadow is not None:
            draw.text((x + shadow_offset[0], cursor + shadow_offset[1]), line, font=font, fill=shadow)
        draw.text((x, cursor), line, font=font, fill=fill)
        bbox = draw.textbbox((0, 0), line, font=font)
        cursor += (bbox[3] - bbox[1]) + gap
    return cursor


def draw_label(draw: ImageDraw.ImageDraw, text: str, *, x: int, y: int, font_size: int = 22) -> tuple[int, int, int, int]:
    font = load_font(font_size, bold=True)
    bbox = draw.textbbox((0, 0), text, font=font)
    rect = (x, y, x + (bbox[2] - bbox[0]) + 28, y + (bbox[3] - bbox[1]) + 18)
    draw.rounded_rectangle(rect, radius=20, fill=(7, 10, 15, 220))
    draw.text((x + 14, y + 8), text, font=font, fill=WHITE)
    return rect


def draw_deadline_chip(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    x: int,
    y: int,
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int],
    text_fill: str,
) -> tuple[int, int, int, int]:
    font = load_font(28, bold=False)
    bbox = draw.textbbox((0, 0), text, font=font)
    rect = (x, y, x + (bbox[2] - bbox[0]) + 34, y + (bbox[3] - bbox[1]) + 22)
    draw.rounded_rectangle(rect, radius=18, fill=fill, outline=outline, width=1)
    draw.text((x + 17, y + 10), text, font=font, fill=text_fill)
    return rect


def draw_brand_lockup(
    draw: ImageDraw.ImageDraw,
    *,
    right: int,
    baseline: int,
    accent: str,
    body: str,
    micro: str,
) -> None:
    body_font = load_font(28, bold=True)
    micro_font = load_font(15, bold=False)
    body_box = draw.textbbox((0, 0), body, font=body_font)
    body_width = body_box[2] - body_box[0]
    micro_box = draw.textbbox((0, 0), micro, font=micro_font)
    micro_width = micro_box[2] - micro_box[0]
    x = right - body_width
    draw.line((x - 64, baseline - 2, x - 18, baseline - 2), fill=accent, width=3)
    draw.text((right - max(body_width, micro_width), baseline - 24), micro, font=micro_font, fill="#aab5c6")
    draw.text((x, baseline), body, font=body_font, fill=WHITE)


def draw_badge_capsule(canvas: Image.Image, *, x: int, y: int, fill: str, text_fill: str, glow: str) -> Image.Image:
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = load_font(34, bold=True)
    bbox = draw.textbbox((0, 0), COPY.badge, font=font)
    rect = (x, y, x + (bbox[2] - bbox[0]) + 48, y + (bbox[3] - bbox[1]) + 24)
    glow_rect = (rect[0] - 14, rect[1] - 10, rect[2] + 14, rect[3] + 10)
    draw.rounded_rectangle(glow_rect, radius=34, fill=rgba(glow, 82))
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=18))
    canvas = composite(canvas, overlay)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(rect, radius=28, fill=fill)
    draw.text((x + 24, y + 12), COPY.badge, font=font, fill=text_fill)
    return canvas


def draw_badge_stamp(canvas: Image.Image, *, x: int, y: int) -> Image.Image:
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    points = [(x, y + 10), (x + 24, y), (x + 292, y), (x + 316, y + 18), (x + 300, y + 76), (x + 16, y + 76), (x, y + 58)]
    draw.polygon(points, fill=(255, 255, 255, 245))
    draw.polygon([(x + 8, y + 8), (x + 272, y + 8), (x + 292, y + 24), (x + 26, y + 24)], fill=rgba("#32d986", 255))
    canvas = panel_shadow(canvas, points, offset=(0, 12), blur=18, alpha=88)
    canvas = composite(canvas, overlay)
    draw = ImageDraw.Draw(canvas)
    title_font = load_font(17, bold=True)
    badge_font = load_font(32, bold=True)
    draw.text((x + 22, y + 7), "FREE CLAIM", font=title_font, fill="#072112")
    draw.text((x + 26, y + 30), COPY.badge, font=badge_font, fill="#0e141d")
    return canvas


def draw_badge_tag(canvas: Image.Image, *, x: int, y: int, fill: str, glow: str) -> Image.Image:
    points = [(x + 16, y), (x + 246, y), (x + 282, y + 28), (x + 246, y + 78), (x + 16, y + 78), (x, y + 39)]
    canvas = add_glow(canvas, (x + 160, y + 38), 180, glow, 86)
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.polygon(points, fill=rgba(fill, 255))
    draw.line(points + [points[0]], fill=(255, 255, 255, 68), width=2)
    canvas = composite(canvas, overlay)
    draw = ImageDraw.Draw(canvas)
    font = load_font(33, bold=True)
    draw.text((x + 28, y + 19), COPY.badge, font=font, fill=WHITE)
    return canvas


def render_titan_broadcast(hero: Image.Image) -> Path:
    hero_height = 472
    canvas = blend_background(hero, "#090d14", 0.46).convert("RGBA")
    canvas.paste(crop_hero(hero, height=hero_height, focus=(0.52, 0.76)), (0, 0))
    canvas = add_glow(canvas, (640, -18), 340, "#05070d", 190)
    canvas = add_beam(canvas, [(430, 0), (850, 0), (782, 94), (498, 94)], "#04060c", 150, 30)
    canvas = add_glow(canvas, (140, 80), 260, "#ff8f3a", 95)
    canvas = add_glow(canvas, (930, 130), 320, "#5a4bff", 70)
    canvas = add_glow(canvas, (1060, 360), 260, "#18d3d4", 54)
    canvas = add_beam(canvas, [(0, 0), (122, 0), (320, hero_height), (178, hero_height)], "#ff8b2b", 86, 54)
    canvas = add_vertical_gradient(canvas, (0, 0, CANVAS_W, hero_height), (0, 0, 0, 24), (0, 0, 0, 122))
    canvas = add_beam(canvas, [(470, 0), (810, 0), (760, 56), (520, 56)], "#030409", 220, 18)

    back_points = [(0, 468), (148, 468), (244, 424), (1280, 424), (1280, 720), (0, 720)]
    front_points = [(0, 486), (210, 486), (296, 440), (1162, 440), (1280, 474), (1280, 720), (0, 720)]
    accent_points = [(0, 486), (156, 486), (250, 440), (322, 440), (244, 720), (0, 720)]
    canvas = panel_shadow(canvas, back_points, offset=(0, 22), blur=34, alpha=114)
    canvas = draw_panel(canvas, back_points, fill=(4, 7, 12, 214))
    canvas = draw_panel(canvas, front_points, fill=(4, 8, 14, 242))
    canvas = draw_panel(canvas, accent_points, fill=(17, 108, 88, 74))
    canvas = add_vertical_gradient(canvas, (0, 440, CANVAS_W, CANVAS_H), (255, 255, 255, 10), (0, 0, 0, 0))

    draw = ImageDraw.Draw(canvas)
    draw_label(draw, COPY.category, x=38, y=34, font_size=24)
    canvas = draw_badge_capsule(canvas, x=963, y=32, fill="#1fcb78", text_fill=WHITE, glow="#23d7a7")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((58, 464, 126, 472), radius=4, fill="#39d98a")

    title_lines, title_font = fit_title(draw, COPY.title, max_width=1080, max_lines=2, candidates=(92, 88, 84, 80, 76, 72))
    last_y = draw_lines(draw, title_lines, title_font, 64, 492, fill=WHITE, gap=8, shadow=(0, 0, 0, 140))
    deadline_rect = draw_deadline_chip(
        draw,
        COPY.deadline,
        x=72,
        y=last_y + 10,
        fill=(14, 64, 48, 226),
        outline=(71, 209, 154, 92),
        text_fill="#d8efe6",
    )
    price_font = load_font(30, bold=False)
    draw.text((72, deadline_rect[3] + 18), f"\u0411\u0443\u043b\u043e {COPY.previous_price}", font=price_font, fill="#a5b1c2")
    draw_brand_lockup(draw, right=1210, baseline=642, accent="#39d98a", body=COPY.brand, micro="gaming freebies")

    path = OUTPUT_DIR / f"{DIRECTIONS[0].slug}.png"
    canvas.convert("RGB").save(path, format="PNG", optimize=True)
    return path


def render_night_raid_editorial(hero: Image.Image) -> Path:
    hero_height = 468
    canvas = blend_background(hero, "#0b0e15", 0.52).convert("RGBA")
    canvas.paste(crop_hero(hero, height=hero_height, focus=(0.52, 0.75)), (0, 0))
    canvas = add_glow(canvas, (640, -18), 340, "#05070d", 190)
    canvas = add_beam(canvas, [(430, 0), (850, 0), (782, 94), (498, 94)], "#04060c", 150, 30)
    canvas = add_glow(canvas, (250, 126), 300, "#7e59ff", 72)
    canvas = add_glow(canvas, (1100, 204), 260, "#ffbb58", 56)
    canvas = add_beam(canvas, [(860, 0), (1110, 0), (1280, hero_height), (990, hero_height)], "#ffb34f", 58, 48)
    canvas = add_vertical_gradient(canvas, (0, 0, CANVAS_W, hero_height), (0, 0, 0, 12), (0, 0, 0, 108))
    canvas = add_beam(canvas, [(470, 0), (810, 0), (760, 56), (520, 56)], "#030409", 220, 18)

    rear_points = [(34, 486), (280, 486), (348, 438), (1240, 438), (1240, 688), (34, 688)]
    front_points = [(46, 500), (266, 500), (334, 452), (1228, 452), (1228, 680), (46, 680)]
    sheen_points = [(46, 500), (266, 500), (334, 452), (1228, 452), (1182, 488), (46, 488)]
    canvas = panel_shadow(canvas, rear_points, offset=(0, 18), blur=28, alpha=120)
    canvas = draw_panel(canvas, rear_points, fill=(10, 12, 18, 184), outline=(255, 255, 255, 18), outline_width=1)
    canvas = draw_panel(canvas, front_points, fill=(11, 13, 20, 228), outline=(255, 255, 255, 18), outline_width=1)
    canvas = draw_panel(canvas, sheen_points, fill=(255, 255, 255, 10))

    draw = ImageDraw.Draw(canvas)
    draw_label(draw, COPY.category, x=38, y=30, font_size=23)
    canvas = draw_badge_stamp(canvas, x=934, y=28)
    draw = ImageDraw.Draw(canvas)
    draw.line((92, 494, 1186, 494), fill="#d7b575", width=3)

    title_lines, title_font = fit_title(draw, COPY.title, max_width=1030, max_lines=2, candidates=(88, 84, 80, 76, 72, 68))
    last_y = draw_lines(draw, title_lines, title_font, 96, 512, fill=WHITE, gap=8, shadow=(0, 0, 0, 120))
    deadline_rect = draw_deadline_chip(
        draw,
        COPY.deadline,
        x=96,
        y=last_y + 8,
        fill=(17, 23, 32, 220),
        outline=(215, 181, 117, 120),
        text_fill="#d8dde5",
    )
    price_font = load_font(30, bold=False)
    draw.text((deadline_rect[2] + 24, deadline_rect[1] + 10), f"\u0411\u0443\u043b\u043e {COPY.previous_price}", font=price_font, fill="#c0c8d5")
    draw_brand_lockup(draw, right=1186, baseline=620, accent="#d7b575", body=COPY.brand, micro="curated game drops")

    path = OUTPUT_DIR / f"{DIRECTIONS[1].slug}.png"
    canvas.convert("RGB").save(path, format="PNG", optimize=True)
    return path


def render_arena_pulse(hero: Image.Image) -> Path:
    hero_height = 462
    canvas = blend_background(hero, "#070b12", 0.50).convert("RGBA")
    canvas.paste(crop_hero(hero, height=hero_height, focus=(0.51, 0.76)), (0, 0))
    canvas = add_glow(canvas, (640, -18), 340, "#05070d", 190)
    canvas = add_beam(canvas, [(430, 0), (850, 0), (782, 94), (498, 94)], "#04060c", 150, 30)
    canvas = add_glow(canvas, (176, 162), 260, "#26d8ff", 64)
    canvas = add_glow(canvas, (1080, 172), 280, "#ff4fa0", 52)
    canvas = add_glow(canvas, (1110, 366), 260, "#25d17b", 42)
    canvas = add_beam(canvas, [(0, 34), (210, 34), (530, hero_height), (280, hero_height)], "#23d7ff", 34, 58)
    canvas = add_scanlines(canvas, hero_height, alpha=12, step=7)
    canvas = add_vertical_gradient(canvas, (0, 0, CANVAS_W, hero_height), (0, 0, 0, 12), (0, 0, 0, 118))
    canvas = add_beam(canvas, [(470, 0), (810, 0), (760, 56), (520, 56)], "#030409", 220, 18)

    top_band = [(0, 492), (168, 492), (244, 450), (1280, 450), (1280, 604), (0, 604)]
    bottom_band = [(0, 604), (1280, 604), (1280, 720), (0, 720)]
    left_bracket = [(40, 488), (128, 488), (128, 500), (52, 500), (52, 574), (40, 574)]
    canvas = panel_shadow(canvas, top_band, offset=(0, 20), blur=30, alpha=104)
    canvas = draw_panel(canvas, top_band, fill=(4, 8, 14, 240))
    canvas = draw_panel(canvas, bottom_band, fill=(6, 11, 17, 248))
    canvas = draw_panel(canvas, left_bracket, fill=(99, 235, 206, 255))
    canvas = add_vertical_gradient(canvas, (0, 450, CANVAS_W, 720), (255, 255, 255, 8), (0, 0, 0, 0))

    draw = ImageDraw.Draw(canvas)
    draw_label(draw, COPY.category, x=40, y=34, font_size=24)
    canvas = draw_badge_tag(canvas, x=952, y=28, fill="#18c878", glow="#22deaa")
    draw = ImageDraw.Draw(canvas)

    title_lines, title_font = fit_title(draw, COPY.title, max_width=1080, max_lines=2, candidates=(82, 78, 74, 70, 66, 62))
    last_y = draw_lines(draw, title_lines, title_font, 58, 500, fill=WHITE, gap=6, shadow=(0, 0, 0, 132))
    deadline_y = max(last_y + 2, 580)
    deadline_rect = draw_deadline_chip(
        draw,
        COPY.deadline,
        x=58,
        y=deadline_y,
        fill=(10, 64, 54, 220),
        outline=(93, 226, 196, 92),
        text_fill="#d6f2ea",
    )
    price_font = load_font(28, bold=False)
    divider_y = 648
    draw.line((58, divider_y, 1228, divider_y), fill=(255, 255, 255, 34), width=2)
    draw.text((58, 658), f"\u0411\u0443\u043b\u043e {COPY.previous_price}", font=price_font, fill="#a8b3c4")
    draw_brand_lockup(draw, right=1222, baseline=650, accent="#63ebce", body=COPY.brand, micro="signal // free claim")

    path = OUTPUT_DIR / f"{DIRECTIONS[2].slug}.png"
    canvas.convert("RGB").save(path, format="PNG", optimize=True)
    return path


def build_contact_sheet(entries: list[tuple[Direction, Path]]) -> Path:
    sheet = Image.new("RGB", (1460, 760), "#080c13")
    draw = ImageDraw.Draw(sheet)
    title_font = load_font(40, bold=True)
    body_font = load_font(22, bold=False)
    label_font = load_font(24, bold=True)
    summary_font = load_font(17, bold=False)

    draw.text((46, 32), "YOTO Idol Reference Directions", font=title_font, fill=WHITE)
    draw.text((46, 84), "Telegram post card explorations | hero-led premium gaming media treatments", font=body_font, fill="#97a4b7")

    thumb_size = (438, 246)
    x_positions = (46, 510, 974)
    for (direction, path), x in zip(entries, x_positions):
        thumb = Image.open(path).convert("RGB")
        thumb = ImageOps.fit(thumb, thumb_size)
        shadow = Image.new("RGBA", sheet.size, (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(shadow)
        frame = (x, 146, x + thumb_size[0], 146 + thumb_size[1])
        sdraw.rounded_rectangle((frame[0], frame[1] + 10, frame[2], frame[3] + 10), radius=24, fill=(0, 0, 0, 110))
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=18))
        sheet = Image.alpha_composite(sheet.convert("RGBA"), shadow).convert("RGB")
        mask = Image.new("L", thumb_size, 0)
        mdraw = ImageDraw.Draw(mask)
        mdraw.rounded_rectangle((0, 0, thumb_size[0] - 1, thumb_size[1] - 1), radius=24, fill=255)
        sheet.paste(thumb, (x, 146), mask)
        draw = ImageDraw.Draw(sheet)
        draw.text((x, 412), direction.name, font=label_font, fill=WHITE)
        summary_lines, _ = wrap_text(draw, direction.summary, summary_font, 410, max_lines=3)
        text_y = 446
        for line in summary_lines:
            draw.text((x, text_y), line, font=summary_font, fill="#9aabbe")
            box = draw.textbbox((0, 0), line, font=summary_font)
            text_y += (box[3] - box[1]) + 5

    out_path = OUTPUT_DIR / "yoto_turnip_boy_idol_contact_sheet.png"
    sheet.save(out_path, format="PNG", optimize=True)
    return out_path


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not HERO_PATH.exists():
        raise FileNotFoundError(f"Hero artwork not found: {HERO_PATH}")

    hero = Image.open(HERO_PATH).convert("RGB")
    rendered = [
        (DIRECTIONS[0], render_titan_broadcast(hero)),
        (DIRECTIONS[1], render_night_raid_editorial(hero)),
        (DIRECTIONS[2], render_arena_pulse(hero)),
    ]
    contact_sheet = build_contact_sheet(rendered)

    for _, path in rendered:
        print(path)
    print(contact_sheet)


if __name__ == "__main__":
    main()