from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

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
    fit_title,
    load_font,
    panel_shadow,
    draw_panel,
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
        slug="yoto_turnip_boy_titan_v2_1_signal_sticker",
        name="Titan Broadcast V2 / Signal Sticker",
        summary="Stronger hero dominance, loud sticker badge, and a sweeping broadcast lower-third.",
    ),
    Variant(
        slug="yoto_turnip_boy_titan_v2_2_prime_stamp",
        name="Titan Broadcast V2 / Prime Stamp",
        summary="More premium and structured, with a bold stamp badge and a sharper branded right-end lockup.",
    ),
)


def draw_sticker_badge(
    canvas: Image.Image,
    *,
    x: int,
    y: int,
    angle: float,
    fill: str,
    accent: str,
    text_fill: str,
    kicker: str,
) -> Image.Image:
    sticker = Image.new("RGBA", (430, 180), (0, 0, 0, 0))
    shadow = Image.new("RGBA", sticker.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    shadow_points = [(34, 28), (334, 28), (388, 66), (360, 150), (64, 150), (26, 102)]
    sdraw.polygon(shadow_points, fill=(0, 0, 0, 118))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=18))
    sticker = Image.alpha_composite(sticker, shadow)

    draw = ImageDraw.Draw(sticker)
    base_points = [(24, 18), (326, 18), (380, 56), (352, 140), (54, 140), (16, 92)]
    accent_points = [(42, 34), (304, 34), (330, 54), (70, 54)]
    cut_points = [(328, 18), (380, 56), (356, 64), (306, 28)]
    draw.polygon(base_points, fill=rgba(fill, 255))
    draw.polygon(accent_points, fill=rgba(accent, 255))
    draw.polygon(cut_points, fill=(255, 255, 255, 72))
    draw.line(base_points + [base_points[0]], fill=(255, 255, 255, 78), width=2)

    kicker_font = load_font(18, bold=True)
    badge_font = load_font(38, bold=True)
    draw.text((50, 31), kicker, font=kicker_font, fill="#072112")
    draw.text((50, 72), COPY.badge, font=badge_font, fill=text_fill)

    rotated = sticker.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    overlay.paste(rotated, (x, y), rotated)
    return composite(canvas, overlay)


def draw_brand_signature(
    canvas: Image.Image,
    *,
    right: int,
    baseline: int,
    accent: str,
    micro: str,
    mode: str,
) -> Image.Image:
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    box_w = 208 if mode == "plate" else 174
    box_h = 68 if mode == "plate" else 62
    x0 = right - box_w
    y0 = baseline - 20
    if mode == "plate":
        points = [(x0 + 22, y0), (right, y0), (right, y0 + box_h), (x0, y0 + box_h), (x0, y0 + 22)]
        inner_line = (x0 + 20, y0 + 14, right - 18, y0 + 14)
        y_block = (x0 + 18, y0 + 18, x0 + 56, y0 + 56)
    else:
        points = [(x0 + 18, y0), (right, y0), (right, y0 + box_h), (x0, y0 + box_h), (x0, y0 + 18)]
        inner_line = (x0 + 16, y0 + 12, right - 16, y0 + 12)
        y_block = (x0 + 14, y0 + 14, x0 + 46, y0 + 46)

    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.polygon([(px, py + 10) for px, py in points], fill=(0, 0, 0, 88))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=14))
    canvas = composite(canvas, shadow)

    draw.polygon(points, fill=(7, 12, 18, 230))
    draw.line(points + [points[0]], fill=(255, 255, 255, 34), width=1)
    draw.line(inner_line, fill=accent, width=3)
    draw.rounded_rectangle(y_block, radius=8, fill=accent)

    body_font = load_font(29 if mode == "plate" else 26, bold=True)
    micro_font = load_font(14, bold=False)
    y_font = load_font(22, bold=True)
    draw.text((y_block[0] + 10, y_block[1] + 6), "Y", font=y_font, fill="#07120d")
    draw.text((y_block[2] + 14, y0 + 22), COPY.brand, font=body_font, fill=WHITE)
    draw.text((y_block[2] + 14, y0 + 6), micro, font=micro_font, fill="#aab5c6")
    return composite(canvas, overlay)


def render_signal_sticker(hero: Image.Image) -> Path:
    hero_height = 474
    canvas = blend_background(hero, "#090d14", 0.46).convert("RGBA")
    canvas.paste(crop_hero(hero, height=hero_height, focus=(0.52, 0.80)), (0, 0))
    canvas = add_glow(canvas, (146, 72), 320, "#ff8f39", 92)
    canvas = add_glow(canvas, (1040, 128), 360, "#5d48ff", 86)
    canvas = add_glow(canvas, (990, 350), 280, "#18d2e1", 54)
    canvas = add_beam(canvas, [(0, 0), (128, 0), (346, hero_height), (196, hero_height)], "#ff8a29", 76, 56)
    canvas = add_beam(canvas, [(420, 0), (860, 0), (790, 70), (510, 70)], "#030409", 230, 20)
    canvas = add_vertical_gradient(canvas, (0, 0, 1280, hero_height), (0, 0, 0, 0), (0, 0, 0, 138))

    back_points = [(0, 492), (202, 492), (320, 438), (1280, 438), (1280, 720), (0, 720)]
    front_points = [(0, 514), (256, 514), (350, 462), (1138, 462), (1280, 506), (1280, 720), (0, 720)]
    accent_points = [(0, 514), (160, 514), (256, 462), (350, 462), (244, 720), (0, 720)]
    edge_points = [(0, 514), (142, 514), (238, 462), (312, 462), (252, 486), (1280, 486), (1280, 506), (350, 506), (256, 556), (0, 556)]
    canvas = panel_shadow(canvas, back_points, offset=(0, 24), blur=34, alpha=122)
    canvas = draw_panel(canvas, back_points, fill=(4, 8, 13, 216))
    canvas = draw_panel(canvas, front_points, fill=(4, 8, 14, 244))
    canvas = draw_panel(canvas, accent_points, fill=(19, 119, 95, 82))
    canvas = draw_panel(canvas, edge_points, fill=(255, 255, 255, 9))

    draw = ImageDraw.Draw(canvas)
    draw_label(draw, COPY.category, x=36, y=34, font_size=24)
    canvas = draw_sticker_badge(
        canvas,
        x=860,
        y=8,
        angle=-6,
        fill="#f3f8f4",
        accent="#2fd57d",
        text_fill="#0e141d",
        kicker="FREE CLAIM",
    )
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((58, 468, 132, 476), radius=4, fill="#39d98a")

    title_lines, title_font = fit_title(draw, COPY.title, max_width=940, max_lines=1, candidates=(88, 84, 80, 76, 72, 68))
    last_y = draw_lines(draw, title_lines, title_font, 62, 530, fill=WHITE, gap=8, shadow=(0, 0, 0, 150))
    deadline_rect = draw_deadline_chip(
        draw,
        COPY.deadline,
        x=72,
        y=last_y + 6,
        fill=(12, 70, 53, 228),
        outline=(86, 226, 172, 104),
        text_fill="#ddf5ea",
    )
    price_font = load_font(31, bold=False)
    draw.text((deadline_rect[2] + 24, deadline_rect[1] + 8), f"\u0411\u0443\u043b\u043e {COPY.previous_price}", font=price_font, fill="#a8b4c4")
    canvas = draw_brand_signature(canvas, right=1220, baseline=620, accent="#39d98a", micro="gaming freebies", mode="plate")

    path = OUTPUT_DIR / f"{VARIANTS[0].slug}.png"
    canvas.convert("RGB").save(path, format="PNG", optimize=True)
    return path


def render_prime_stamp(hero: Image.Image) -> Path:
    hero_height = 470
    canvas = blend_background(hero, "#090c13", 0.48).convert("RGBA")
    canvas.paste(crop_hero(hero, height=hero_height, focus=(0.52, 0.79)), (0, 0))
    canvas = add_glow(canvas, (220, 88), 310, "#ff9440", 74)
    canvas = add_glow(canvas, (1030, 118), 360, "#604fff", 80)
    canvas = add_glow(canvas, (1130, 250), 250, "#ffcc72", 40)
    canvas = add_beam(canvas, [(870, 0), (1110, 0), (1280, hero_height), (986, hero_height)], "#ffc56a", 42, 52)
    canvas = add_beam(canvas, [(432, 0), (852, 0), (786, 68), (504, 68)], "#030409", 228, 20)
    canvas = add_vertical_gradient(canvas, (0, 0, 1280, hero_height), (0, 0, 0, 0), (0, 0, 0, 134))

    rear_points = [(34, 500), (286, 500), (370, 448), (1242, 448), (1242, 698), (34, 698)]
    front_points = [(24, 514), (260, 514), (350, 462), (1218, 462), (1218, 688), (24, 688)]
    cap_points = [(24, 514), (248, 514), (336, 462), (1218, 462), (1172, 490), (24, 490)]
    rail_points = [(24, 650), (1218, 650), (1218, 688), (24, 688)]
    canvas = panel_shadow(canvas, rear_points, offset=(0, 20), blur=30, alpha=120)
    canvas = draw_panel(canvas, rear_points, fill=(10, 13, 19, 188), outline=(255, 255, 255, 18), outline_width=1)
    canvas = draw_panel(canvas, front_points, fill=(8, 11, 17, 234), outline=(255, 255, 255, 20), outline_width=1)
    canvas = draw_panel(canvas, cap_points, fill=(255, 255, 255, 10))
    canvas = draw_panel(canvas, rail_points, fill=(13, 16, 24, 250))

    draw = ImageDraw.Draw(canvas)
    draw_label(draw, COPY.category, x=36, y=32, font_size=24)
    canvas = draw_sticker_badge(
        canvas,
        x=852,
        y=14,
        angle=-4,
        fill="#ffffff",
        accent="#32d986",
        text_fill="#0d141d",
        kicker="LIMITED FREE CLAIM",
    )
    draw = ImageDraw.Draw(canvas)
    draw.line((88, 496, 1178, 496), fill="#d7b575", width=3)

    title_lines, title_font = fit_title(draw, COPY.title, max_width=900, max_lines=1, candidates=(86, 82, 78, 74, 70, 66))
    last_y = draw_lines(draw, title_lines, title_font, 84, 534, fill=WHITE, gap=8, shadow=(0, 0, 0, 138))
    deadline_rect = draw_deadline_chip(
        draw,
        COPY.deadline,
        x=90,
        y=last_y + 10,
        fill=(16, 22, 30, 224),
        outline=(215, 181, 117, 116),
        text_fill="#d8dfe8",
    )
    price_font = load_font(31, bold=False)
    draw.text((deadline_rect[2] + 24, deadline_rect[1] + 9), f"\u0411\u0443\u043b\u043e {COPY.previous_price}", font=price_font, fill="#bdc6d4")
    canvas = draw_brand_signature(canvas, right=1178, baseline=612, accent="#d7b575", micro="drop signal", mode="compact")

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

    draw.text((44, 32), "Titan Broadcast V2 Refinements", font=title_font, fill=WHITE)
    draw.text((44, 84), "Telegram hero-led premium gaming card directions", font=body_font, fill="#97a4b7")

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

    out_path = OUTPUT_DIR / "yoto_turnip_boy_titan_v2_contact_sheet.png"
    sheet.save(out_path, format="PNG", optimize=True)
    return out_path


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not HERO_PATH.exists():
        raise FileNotFoundError(f"Hero artwork not found: {HERO_PATH}")

    hero = Image.open(HERO_PATH).convert("RGB")
    rendered = [
        (VARIANTS[0], render_signal_sticker(hero)),
        (VARIANTS[1], render_prime_stamp(hero)),
    ]
    sheet = build_contact_sheet(rendered)
    for _, path in rendered:
        print(path)
    print(sheet)


if __name__ == "__main__":
    main()