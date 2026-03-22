from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from render_yoto_idol_reference_cards import (
    COPY,
    HERO_PATH,
    OUTPUT_DIR,
    WHITE,
    add_beam,
    add_glow,
    add_vertical_gradient,
    blend_background,
    composite,
    crop_hero,
    draw_deadline_chip,
    draw_label,
    draw_lines,
    draw_panel,
    fit_title,
    load_font,
    panel_shadow,
    rgba,
    wrap_text,
)


@dataclass(frozen=True)
class Variant:
    slug: str
    name: str
    summary: str


VARIANTS = (
    Variant(
        slug="titan_v3_signal_core",
        name="Titan V3 / Signal Core",
        summary="The most feed-dominant version: strong claim sticker, hero-led energy, and a sharper broadcast lower-third.",
    ),
    Variant(
        slug="titan_v3_prime_broadcast",
        name="Titan V3 / Prime Broadcast",
        summary="The premium finalist: cleaner broadcast geometry, stronger badge authority, and the best YOTO brand finish.",
    ),
)


def draw_claim_sticker(
    canvas: Image.Image,
    *,
    x: int,
    y: int,
    angle: float,
    kicker: str,
    accent: str,
    fill: tuple[int, int, int, int],
    text_fill: str,
    kicker_fill: str,
    glow: str,
) -> Image.Image:
    sticker = Image.new("RGBA", (470, 210), (0, 0, 0, 0))
    shadow = Image.new("RGBA", sticker.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    shadow_points = [(44, 34), (372, 34), (434, 78), (402, 172), (78, 172), (28, 116)]
    sdraw.polygon(shadow_points, fill=(0, 0, 0, 132))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=20))
    sticker = Image.alpha_composite(sticker, shadow)

    overlay = Image.new("RGBA", sticker.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    base_points = [(28, 18), (356, 18), (418, 62), (386, 156), (62, 156), (14, 100)]
    highlight_points = [(46, 36), (336, 36), (364, 58), (74, 58)]
    cut_points = [(360, 18), (418, 62), (388, 72), (332, 28)]
    draw.polygon(base_points, fill=fill)
    draw.polygon(highlight_points, fill=rgba(accent, 255))
    draw.polygon(cut_points, fill=(255, 255, 255, 88))
    draw.line(base_points + [base_points[0]], fill=(255, 255, 255, 72), width=2)
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=0))
    sticker = Image.alpha_composite(sticker, overlay)

    draw = ImageDraw.Draw(sticker)
    kicker_font = load_font(18, bold=True)
    badge_font = load_font(43, bold=True)
    draw.text((54, 34), kicker, font=kicker_font, fill=kicker_fill)
    draw.text((56, 78), COPY.badge, font=badge_font, fill=text_fill)

    glow_overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow_overlay)
    gdraw.ellipse((x - 18, y - 10, x + 340, y + 176), fill=rgba(glow, 86))
    glow_overlay = glow_overlay.filter(ImageFilter.GaussianBlur(radius=22))
    canvas = composite(canvas, glow_overlay)

    rotated = sticker.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
    paste = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    paste.paste(rotated, (x, y), rotated)
    return composite(canvas, paste)


def draw_brand_lockup(
    canvas: Image.Image,
    *,
    right: int,
    y: int,
    accent: str,
    micro: str,
    premium: bool,
) -> Image.Image:
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width = 232 if premium else 214
    height = 78 if premium else 72
    x = right - width
    points = [(x + 24, y), (right, y), (right, y + height), (x, y + height), (x, y + 24)]
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.polygon([(px, py + 10) for px, py in points], fill=(0, 0, 0, 102))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=16))
    canvas = composite(canvas, shadow)

    draw.polygon(points, fill=(8, 12, 18, 234))
    draw.line(points + [points[0]], fill=(255, 255, 255, 26), width=1)
    draw.line((x + 22, y + 14, right - 16, y + 14), fill=accent, width=3)
    draw.rounded_rectangle((x + 18, y + 18, x + 58, y + 58), radius=10, fill=accent)
    y_font = load_font(24, bold=True)
    body_font = load_font(32 if premium else 30, bold=True)
    micro_font = load_font(15, bold=False)
    draw.text((x + 30, y + 23), "Y", font=y_font, fill="#06120d")
    draw.text((x + 72, y + 34), COPY.brand, font=body_font, fill=WHITE)
    draw.text((x + 72, y + 10), micro, font=micro_font, fill="#aab5c6")
    return composite(canvas, overlay)


def draw_signal_core_lower_third(canvas: Image.Image) -> Image.Image:
    back_points = [(0, 494), (196, 494), (328, 438), (1280, 438), (1280, 720), (0, 720)]
    front_points = [(0, 514), (254, 514), (348, 462), (1144, 462), (1280, 500), (1280, 720), (0, 720)]
    accent_points = [(0, 514), (162, 514), (256, 462), (344, 462), (246, 720), (0, 720)]
    band_points = [(0, 514), (146, 514), (238, 462), (1280, 462), (1280, 488), (264, 488), (192, 528), (0, 528)]
    row_points = [(0, 648), (1280, 648), (1280, 720), (0, 720)]
    canvas = panel_shadow(canvas, back_points, offset=(0, 22), blur=34, alpha=118)
    canvas = draw_panel(canvas, back_points, fill=(4, 7, 12, 216))
    canvas = draw_panel(canvas, front_points, fill=(4, 8, 14, 244))
    canvas = draw_panel(canvas, accent_points, fill=(17, 111, 91, 80))
    canvas = draw_panel(canvas, band_points, fill=(255, 255, 255, 8))
    canvas = draw_panel(canvas, row_points, fill=(6, 11, 17, 250))
    canvas = add_vertical_gradient(canvas, (0, 462, 1280, 720), (255, 255, 255, 8), (0, 0, 0, 0))
    return canvas


def draw_prime_broadcast_lower_third(canvas: Image.Image) -> Image.Image:
    rear_points = [(26, 500), (286, 500), (372, 446), (1248, 446), (1248, 700), (26, 700)]
    front_points = [(18, 514), (264, 514), (354, 460), (1230, 460), (1230, 690), (18, 690)]
    cap_points = [(18, 514), (254, 514), (342, 460), (1230, 460), (1182, 490), (18, 490)]
    row_points = [(18, 644), (1230, 644), (1230, 690), (18, 690)]
    canvas = panel_shadow(canvas, rear_points, offset=(0, 20), blur=30, alpha=124)
    canvas = draw_panel(canvas, rear_points, fill=(10, 12, 18, 188), outline=(255, 255, 255, 18), outline_width=1)
    canvas = draw_panel(canvas, front_points, fill=(7, 10, 15, 236), outline=(255, 255, 255, 18), outline_width=1)
    canvas = draw_panel(canvas, cap_points, fill=(255, 255, 255, 10))
    canvas = draw_panel(canvas, row_points, fill=(10, 14, 22, 248))
    canvas = add_vertical_gradient(canvas, (18, 460, 1230, 690), (255, 255, 255, 8), (0, 0, 0, 0))
    return canvas


def render_signal_core(hero: Image.Image) -> Path:
    hero_height = 474
    canvas = blend_background(hero, "#090d14", 0.46).convert("RGBA")
    canvas.paste(crop_hero(hero, height=hero_height, focus=(0.52, 0.80)), (0, 0))
    canvas = add_glow(canvas, (148, 82), 300, "#ff8d38", 88)
    canvas = add_glow(canvas, (1028, 126), 360, "#5d49ff", 84)
    canvas = add_glow(canvas, (980, 360), 280, "#19d5df", 50)
    canvas = add_beam(canvas, [(0, 0), (130, 0), (344, hero_height), (196, hero_height)], "#ff8a29", 74, 56)
    canvas = add_beam(canvas, [(430, 0), (850, 0), (786, 68), (508, 68)], "#030409", 230, 20)
    canvas = add_vertical_gradient(canvas, (0, 0, 1280, hero_height), (0, 0, 0, 0), (0, 0, 0, 138))
    canvas = add_glow(canvas, (1120, 64), 170, "#2fd57d", 38)
    canvas = draw_signal_core_lower_third(canvas)

    draw = ImageDraw.Draw(canvas)
    draw_label(draw, COPY.category, x=36, y=34, font_size=24)
    canvas = draw_claim_sticker(
        canvas,
        x=840,
        y=8,
        angle=-6.0,
        kicker="FREE CLAIM",
        accent="#2fd57d",
        fill=(247, 250, 247, 255),
        text_fill="#0f151d",
        kicker_fill="#071c11",
        glow="#2fd57d",
    )
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((58, 470, 132, 478), radius=4, fill="#39d98a")

    title_lines, title_font = fit_title(draw, COPY.title, max_width=950, max_lines=1, candidates=(88, 84, 80, 76, 72, 68))
    title_bottom = draw_lines(draw, title_lines, title_font, 62, 534, fill=WHITE, gap=8, shadow=(0, 0, 0, 148))
    deadline_rect = draw_deadline_chip(
        draw,
        COPY.deadline,
        x=72,
        y=max(title_bottom + 8, 622),
        fill=(13, 70, 54, 228),
        outline=(88, 226, 170, 104),
        text_fill="#dcf6ea",
    )
    price_font = load_font(29, bold=False)
    draw.text((deadline_rect[2] + 24, deadline_rect[1] + 9), f"\u0431\u0443\u043b\u043e {COPY.previous_price}", font=price_font, fill="#aab5c6")
    canvas = draw_brand_lockup(canvas, right=1218, y=590, accent="#39d98a", micro="gaming freebies", premium=False)

    path = OUTPUT_DIR / f"{VARIANTS[0].slug}.png"
    canvas.convert("RGB").save(path, format="PNG", optimize=True)
    return path


def render_prime_broadcast(hero: Image.Image) -> Path:
    hero_height = 472
    canvas = blend_background(hero, "#090c13", 0.48).convert("RGBA")
    canvas.paste(crop_hero(hero, height=hero_height, focus=(0.52, 0.79)), (0, 0))
    canvas = add_glow(canvas, (222, 92), 300, "#ff9642", 70)
    canvas = add_glow(canvas, (1024, 122), 360, "#5c4bff", 82)
    canvas = add_glow(canvas, (1140, 240), 260, "#ffcb76", 38)
    canvas = add_beam(canvas, [(868, 0), (1112, 0), (1280, hero_height), (988, hero_height)], "#ffc56a", 40, 52)
    canvas = add_beam(canvas, [(432, 0), (852, 0), (786, 68), (506, 68)], "#030409", 228, 20)
    canvas = add_vertical_gradient(canvas, (0, 0, 1280, hero_height), (0, 0, 0, 0), (0, 0, 0, 136))
    canvas = add_glow(canvas, (1104, 64), 160, "#2fd57d", 28)
    canvas = draw_prime_broadcast_lower_third(canvas)

    draw = ImageDraw.Draw(canvas)
    draw_label(draw, COPY.category, x=36, y=34, font_size=24)
    canvas = draw_claim_sticker(
        canvas,
        x=832,
        y=10,
        angle=-4.0,
        kicker="LIMITED FREE CLAIM",
        accent="#32d986",
        fill=(255, 255, 255, 255),
        text_fill="#0e141d",
        kicker_fill="#072012",
        glow="#ffffff",
    )
    draw = ImageDraw.Draw(canvas)
    draw.line((86, 498, 1182, 498), fill="#d7b575", width=3)

    title_lines, title_font = fit_title(draw, COPY.title, max_width=900, max_lines=1, candidates=(86, 82, 78, 74, 70, 66))
    title_bottom = draw_lines(draw, title_lines, title_font, 82, 540, fill=WHITE, gap=8, shadow=(0, 0, 0, 142))
    deadline_rect = draw_deadline_chip(
        draw,
        COPY.deadline,
        x=88,
        y=max(title_bottom + 8, 622),
        fill=(15, 21, 30, 224),
        outline=(215, 181, 117, 116),
        text_fill="#d8e0e9",
    )
    price_font = load_font(29, bold=False)
    draw.text((deadline_rect[2] + 24, deadline_rect[1] + 9), f"\u0431\u0443\u043b\u043e {COPY.previous_price}", font=price_font, fill="#c0c8d6")
    canvas = draw_brand_lockup(canvas, right=1178, y=586, accent="#d7b575", micro="drop signal", premium=True)

    path = OUTPUT_DIR / f"{VARIANTS[1].slug}.png"
    canvas.convert("RGB").save(path, format="PNG", optimize=True)
    return path


def build_contact_sheet(entries: list[tuple[Variant, Path]]) -> Path:
    sheet = Image.new("RGB", (1410, 760), "#070b12")
    draw = ImageDraw.Draw(sheet)
    title_font = load_font(40, bold=True)
    body_font = load_font(22, bold=False)
    label_font = load_font(24, bold=True)
    summary_font = load_font(18, bold=False)

    draw.text((44, 32), "Titan Broadcast V3 Finalists", font=title_font, fill=WHITE)
    draw.text((44, 84), "Telegram hero-led premium gaming card idol references", font=body_font, fill="#97a4b7")

    thumb_size = (610, 343)
    x_positions = (44, 756)
    for (variant, path), x in zip(entries, x_positions):
        thumb = Image.open(path).convert("RGB")
        thumb = ImageOps.fit(thumb, thumb_size)
        shadow = Image.new("RGBA", sheet.size, (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(shadow)
        frame = (x, 150, x + thumb_size[0], 150 + thumb_size[1])
        sdraw.rounded_rectangle((frame[0], frame[1] + 12, frame[2], frame[3] + 12), radius=24, fill=(0, 0, 0, 120))
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=18))
        sheet = Image.alpha_composite(sheet.convert("RGBA"), shadow).convert("RGB")
        mask = Image.new("L", thumb_size, 0)
        mdraw = ImageDraw.Draw(mask)
        mdraw.rounded_rectangle((0, 0, thumb_size[0] - 1, thumb_size[1] - 1), radius=24, fill=255)
        sheet.paste(thumb, (x, 150), mask)
        draw = ImageDraw.Draw(sheet)
        draw.text((x, 524), variant.name, font=label_font, fill=WHITE)
        lines, _ = wrap_text(draw, variant.summary, summary_font, 590, max_lines=3)
        y = 560
        for line in lines:
            draw.text((x, y), line, font=summary_font, fill="#9aabbe")
            box = draw.textbbox((0, 0), line, font=summary_font)
            y += (box[3] - box[1]) + 6

    out_path = OUTPUT_DIR / "titan_v3_contact_sheet.png"
    sheet.save(out_path, format="PNG", optimize=True)
    return out_path


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not HERO_PATH.exists():
        raise FileNotFoundError(f"Hero artwork not found: {HERO_PATH}")

    hero = Image.open(HERO_PATH).convert("RGB")
    rendered = [
        (VARIANTS[0], render_signal_core(hero)),
        (VARIANTS[1], render_prime_broadcast(hero)),
    ]
    contact_sheet = build_contact_sheet(rendered)

    for _, path in rendered:
        print(path)
    print(contact_sheet)


if __name__ == "__main__":
    main()