from __future__ import annotations

import hashlib
from typing import Any

from PIL import Image, ImageColor, ImageDraw, ImageFilter

ROLE_DISPLAY_BOLD_FONT_CANDIDATES = (
    'segoeuib.ttf',
    'Inter-Bold.ttf',
    'Inter-SemiBold.ttf',
    'arialbd.ttf',
    'tahomabd.ttf',
    'DejaVuSans-Bold.ttf',
)

from .base import ImageResolutionRequest, ResolvedImage


class PlaceholderImageProvider:
    provider_name = 'placeholder'

    def __init__(self, support: Any) -> None:
        self.support = support

    def resolve(self, request: ImageResolutionRequest) -> ResolvedImage | None:
        image = self._build_placeholder(
            request.image_size,
            title=request.title,
            platform=request.platform,
            slug=request.slug,
            card_type=request.card_type,
            deadline=request.deadline,
            old_price=request.old_price,
            current_price=request.current_price,
            platform_badge=request.platform_badge,
            brand_micro_label=request.brand_micro_label,
        )
        return ResolvedImage(
            image=image,
            metadata={
                'selected_source': 'placeholder',
                'provider_name': self.provider_name,
            },
        )

    def _build_placeholder(
        self,
        size: tuple[int, int],
        *,
        title: str,
        platform: str,
        slug: str,
        card_type: str,
        deadline: str | None,
        old_price: str | None,
        current_price: str | None,
        platform_badge: str | None,
        brand_micro_label: str | None,
    ) -> Image.Image:
        normalized_type = self.support._coerce_card_type(card_type)
        palette = self.support._palette(normalized_type)
        title = self.support._normalize_display_text(title or 'YOTO')
        platform = self.support._normalize_display_text(platform or '')
        badge_text = self.support._normalize_display_text(platform_badge or '')
        brand_label = self.support._normalize_display_text(brand_micro_label or self.support._default_brand_micro_label(normalized_type))
        deadline = self.support._normalize_display_text(deadline or '')
        old_price = self.support._normalize_display_text(old_price or '')
        current_price = self.support._normalize_display_text(current_price or '')
        slug = self.support._normalize_display_text(slug or title.lower())
        seed_source = '|'.join((normalized_type.value, platform, badge_text, slug, title, deadline, old_price, current_price))
        digest = hashlib.sha1(seed_source.encode('utf-8')).digest()
        seed = digest * 4
        cache_key = (digest.hex(), size[0], size[1])
        cached = self.support._placeholder_cache.get(cache_key)
        if cached is not None:
            return cached.copy()

        image = Image.new('RGB', size, palette.panel_top)
        draw = ImageDraw.Draw(image)
        top_rgb = ImageColor.getrgb(palette.panel_top)
        bottom_rgb = ImageColor.getrgb(palette.panel_bottom)
        glow_rgb = ImageColor.getrgb(palette.glow)
        for y in range(size[1]):
            ratio = y / max(size[1] - 1, 1)
            base = tuple(int(top_rgb[idx] + (bottom_rgb[idx] - top_rgb[idx]) * ratio) for idx in range(3))
            lift = int((1.0 - min(ratio, 0.84)) * (glow_rgb[1] / 22))
            color = tuple(min(255, base[idx] + lift) for idx in range(3))
            draw.line((0, y, size[0], y), fill=color)

        overlay = Image.new('RGBA', size, (0, 0, 0, 0))
        accent_orbs = Image.new('RGBA', size, (0, 0, 0, 0))
        orb_draw = ImageDraw.Draw(accent_orbs)
        accent_colors = (palette.accent, palette.accent_secondary, palette.glow)
        for index, color in enumerate(accent_colors):
            x0 = int(size[0] * 0.56) + (seed[index] % 220) - 70 + index * 28
            y0 = -70 + (seed[index + 3] % 180) + index * 52
            width = 260 + seed[index + 6] % 250
            height = 200 + seed[index + 9] % 220
            orb_draw.ellipse((x0, y0, x0 + width, y0 + height), fill=self.support._rgba(color, 58 - index * 10))
        accent_orbs = accent_orbs.filter(ImageFilter.GaussianBlur(radius=34))
        overlay = Image.alpha_composite(overlay, accent_orbs)

        beams = Image.new('RGBA', size, (0, 0, 0, 0))
        beam_draw = ImageDraw.Draw(beams)
        for index, color in enumerate((palette.accent, palette.accent_secondary, palette.glow)):
            shift = (seed[12 + index] % 180) - 90
            top = 52 + index * 92 + (seed[15 + index] % 34)
            width = 320 + seed[18 + index] % 220
            height = 44 + seed[21 + index] % 26
            beam_draw.polygon(
                [
                    (-170 + shift, top),
                    (width + shift, top),
                    (width + 170 + shift, top + height),
                    (30 + shift, top + height),
                ],
                fill=self.support._rgba(color, 34 if index == 0 else 22),
            )
        beams = beams.filter(ImageFilter.GaussianBlur(radius=5))
        overlay = Image.alpha_composite(overlay, beams)

        probable_long_title = len(title) >= 18 or len(title.split()) >= 4
        panel_left = 104
        panel_top = (82 if probable_long_title else 92) + seed[24] % (12 if probable_long_title else 16)
        panel_width = min(size[0] - 470, (582 if probable_long_title else 556) + seed[25] % (42 if probable_long_title else 46))
        panel_height = 184 if probable_long_title else 162
        panel_rect = (panel_left, panel_top, panel_left + panel_width, panel_top + panel_height)

        panel_haze = Image.new('RGBA', size, (0, 0, 0, 0))
        panel_haze_draw = ImageDraw.Draw(panel_haze)
        panel_haze_draw.rounded_rectangle(
            (panel_rect[0] + 6, panel_rect[1] + 10, panel_rect[2] + 6, panel_rect[3] + 18),
            radius=32,
            fill=(0, 0, 0, 42),
        )
        panel_haze = panel_haze.filter(ImageFilter.GaussianBlur(radius=18))
        overlay = Image.alpha_composite(overlay, panel_haze)

        o_draw = ImageDraw.Draw(overlay)
        o_draw.rounded_rectangle(panel_rect, radius=30, fill=(5, 10, 16, 42), outline=self.support._rgba('#ffffff', 18), width=1)
        o_draw.line((panel_left + 26, panel_top + 24, panel_left + 158, panel_top + 24), fill=self.support._rgba(palette.accent, 172), width=4)
        o_draw.line((panel_left + 26, panel_top + 38, panel_rect[2] - 28, panel_top + 38), fill=(255, 255, 255, 18), width=1)

        micro_role = self.support._typography_role('placeholder_micro')
        micro_source = f'YOTO / {brand_label}' if brand_label else 'YOTO'
        micro_font = self.support._load_font_for_text(18, micro_role.candidates, micro_source, layer='placeholder_micro')
        micro_spacing = self.support._letter_spacing_px(micro_font, micro_role.tracking_em)
        micro_text = self.support._ellipsize(o_draw, self.support._role_text(micro_source, 'placeholder_micro'), micro_font, panel_width - 64, letter_spacing=micro_spacing)
        self.support._draw_role_text(o_draw, (panel_left + 30, panel_top + 48), micro_text, micro_font, (236, 245, 255, 198), role='placeholder_micro', shadow_layers=())

        title_layout, title_style = self.support._resolve_placeholder_title_layout(
            o_draw,
            title,
            panel_width=panel_width,
            panel_height=panel_height,
        )
        title_gap = int(title_style['line_gap'])
        title_y = panel_top + int(title_style['title_y_offset']) + 6
        for index, line in enumerate(title_layout.lines):
            y = title_y + index * (title_layout.line_height + title_gap)
            self.support._draw_role_text(
                o_draw,
                (panel_left + 30, y),
                line,
                title_layout.font,
                (248, 251, 255, min(232, int(title_style['text_alpha']))),
                role='placeholder_title',
                shadow_layers=((2, 3, max(54, int(title_style['shadow_alpha']) - 10)),),
            )

        initials = self.support._placeholder_initials(title)
        monogram_font = self.support._load_font_for_text(236 if len(initials) == 1 else 220, ROLE_DISPLAY_BOLD_FONT_CANDIDATES, initials, layer='placeholder_monogram')
        mono_bbox = o_draw.textbbox((0, 0), initials, font=monogram_font)
        mono_width = mono_bbox[2] - mono_bbox[0]
        mono_x = size[0] - mono_width - 132 - (seed[26] % 68)
        mono_y = 92 + (seed[27] % 100)
        self.support._draw_role_text(o_draw, (mono_x + 10, mono_y + 10), initials, monogram_font, self.support._rgba(palette.accent, 20), role='brand_wordmark', shadow_layers=())
        self.support._draw_role_text(o_draw, (mono_x, mono_y), initials, monogram_font, (255, 255, 255, 26), role='brand_wordmark', shadow_layers=())

        rail_left = size[0] - 354
        rail_top = 112 + seed[28] % 38
        for index in range(3):
            tile_width = 184 + seed[29 + index] % 26
            tile_height = 76 + seed[32 + index] % 18
            tile_x = rail_left + (seed[35 + index] % 28) - 10
            tile_y = rail_top + index * 88 + (seed[38 + index] % 16) - 5
            tile_rect = (tile_x, tile_y, tile_x + tile_width, tile_y + tile_height)
            outline = palette.accent if index != 1 else palette.accent_secondary
            o_draw.rounded_rectangle(tile_rect, radius=20, fill=(8, 13, 20, 78 if index == 0 else 52), outline=self.support._rgba(outline, 64 if index == 0 else 46), width=1)
            o_draw.line((tile_x + 16, tile_y + 14, tile_x + tile_width - 18, tile_y + 14), fill=self.support._rgba(outline, 104 if index == 0 else 62), width=2)
            o_draw.line((tile_x + 16, tile_y + tile_height - 16, tile_x + tile_width - 18, tile_y + tile_height - 16), fill=(255, 255, 255, 16), width=1)

        frame = Image.new('RGBA', size, (0, 0, 0, 0))
        frame_draw = ImageDraw.Draw(frame)
        frame_draw.rounded_rectangle((84, 78, size[0] - 84, size[1] - 98), radius=34, outline=self.support._rgba('#ffffff', 20), width=1)
        frame_draw.rounded_rectangle((112, 112, size[0] - 112, size[1] - 130), radius=26, outline=self.support._rgba(palette.accent, 38), width=1)
        frame_draw.arc((size[0] - 404, 36, size[0] - 64, 316), start=196, end=344, fill=self.support._rgba(palette.glow, 72), width=3)
        frame_draw.arc((size[0] - 356, 82, size[0] - 112, 284), start=188, end=338, fill=self.support._rgba('#ffffff', 20), width=1)

        branded = Image.alpha_composite(image.convert('RGBA'), overlay)
        branded = Image.alpha_composite(branded, frame.filter(ImageFilter.GaussianBlur(radius=1)))
        branded = branded.convert('RGB')
        self.support._placeholder_cache[cache_key] = branded
        return branded.copy()
