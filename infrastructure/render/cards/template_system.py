from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
import re
from typing import Iterable

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from domain.entities.offer import Offer
from infrastructure.clients.base_http import ResilientHttpClient
from infrastructure.render.cards.asset_source import resolve_existing_asset_path


TITLE_CLEANERS = [
    '\u2122',
    '\u00ae',
    ' Complete Edition',
    ' Remastered',
    ' Definitive Edition',
]

BOLD_FONT_CANDIDATES = (
    'arialbd.ttf',
    'segoeuib.ttf',
    'tahomabd.ttf',
    'DejaVuSans-Bold.ttf',
    'NotoSans-Bold.ttf',
    'Arial Bold.ttf',
)

REGULAR_FONT_CANDIDATES = (
    'arial.ttf',
    'segoeui.ttf',
    'tahoma.ttf',
    'DejaVuSans.ttf',
    'NotoSans-Regular.ttf',
    'NotoSans.ttf',
    'Arial.ttf',
)

CYRILLIC_FONT_SAMPLE = '\u041f\u0440\u0438\u0432\u0456\u0442 \u0407\u0457 \u0404\u0454 \u0406\u0456 \u0490\u0491'
CARD_SIZE = (1280, 720)
GAME_HERO_RECT = (40, 40, 1240, 384)
GAME_INFO_RECT = (56, 402, 1224, 676)
EVENT_PANEL_RECT = (72, 72, 760, 648)


@dataclass(slots=True)
class RenderDiagnostics:
    template_id: str
    asset_used: str | None
    title_lines: list[str] = field(default_factory=list)
    clipped_fields: list[str] = field(default_factory=list)
    render_warnings: list[str] = field(default_factory=list)
    hero_asset_used: str | None = None
    layout_variant: str | None = None
    hero_mode: str | None = None
    title_font_size: int | None = None
    hero_rect: tuple[int, int, int, int] | None = None
    info_rect: tuple[int, int, int, int] | None = None
    badge_rect: tuple[int, int, int, int] | None = None

    def to_snapshot(self) -> dict[str, object]:
        return {
            'template_id': self.template_id,
            'asset_used': self.asset_used,
            'title_lines': self.title_lines,
            'clipped_fields': self.clipped_fields,
            'render_warnings': self.render_warnings,
            'hero_asset_used': self.hero_asset_used,
            'layout_variant': self.layout_variant,
            'hero_mode': self.hero_mode,
            'title_font_size': self.title_font_size,
            'hero_rect': self.hero_rect,
            'info_rect': self.info_rect,
            'badge_rect': self.badge_rect,
        }


@dataclass(slots=True)
class TemplateRenderResult:
    image_path: Path
    assets_used: list[str]
    diagnostics: RenderDiagnostics


class TemplateSystem:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.repo_font_dir = Path(__file__).resolve().parents[3] / 'video_generator' / 'assets' / 'fonts'
        self._default_font_used = False
        self.title_font = self._load_font(size=68, candidates=BOLD_FONT_CANDIDATES)
        self.body_font = self._load_font(size=30, candidates=REGULAR_FONT_CANDIDATES)
        self.small_font = self._load_font(size=22, candidates=REGULAR_FONT_CANDIDATES)
        self.badge_font = self._load_font(size=30, candidates=BOLD_FONT_CANDIDATES)
        self.kicker_font = self._load_font(size=22, candidates=BOLD_FONT_CANDIDATES)
        self.price_font = self._load_font(size=44, candidates=BOLD_FONT_CANDIDATES)
        self.brand_font = self._load_font(size=20, candidates=BOLD_FONT_CANDIDATES)
        self.badge_font_large = self._load_font(size=54, candidates=BOLD_FONT_CANDIDATES)
        self.badge_font_medium = self._load_font(size=46, candidates=BOLD_FONT_CANDIDATES)
        self.badge_font_small = self._load_font(size=34, candidates=BOLD_FONT_CANDIDATES)

    async def render(self, http: ResilientHttpClient, offer: Offer, template_id: str) -> TemplateRenderResult:
        if template_id == 'festival_event':
            return await self._render_event(http, offer, template_id)
        return await self._render_game(http, offer, template_id)

    async def _render_game(self, http: ResilientHttpClient, offer: Offer, template_id: str) -> TemplateRenderResult:
        diagnostics = RenderDiagnostics(template_id=template_id, asset_used=None)
        if self._default_font_used:
            diagnostics.render_warnings.append('default_font_fallback')

        primary_asset = self._pick_primary_asset(offer)
        hero_asset = self._pick_hero_asset(offer) or primary_asset
        background_asset = self._pick_background_asset(offer) or hero_asset or primary_asset
        theme = self._game_theme(offer, template_id)
        diagnostics.asset_used = primary_asset
        diagnostics.hero_asset_used = hero_asset
        diagnostics.layout_variant = str(theme['layout_variant'])
        diagnostics.hero_rect = GAME_HERO_RECT
        diagnostics.info_rect = GAME_INFO_RECT

        if primary_asset is None and hero_asset is None and background_asset is None:
            diagnostics.render_warnings.append('fallback_layout')

        canvas = Image.new('RGB', CARD_SIZE, '#0f141b')
        background = await self._download(http, background_asset, CARD_SIZE)
        background = self._build_background(background, CARD_SIZE, str(theme['background_tint']), 0.62)
        canvas.paste(background, (0, 0))

        hero_source = await self._download(http, hero_asset, self._rect_size(GAME_HERO_RECT))
        hero_mode = self._pick_hero_mode(hero_source)
        diagnostics.hero_mode = hero_mode
        hero_panel = self._compose_panel_image(
            hero_source,
            self._rect_size(GAME_HERO_RECT),
            hero_mode,
            str(theme['hero_backdrop']),
        )
        self._paste_rounded(canvas, hero_panel, GAME_HERO_RECT, radius=38)

        overlay = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rounded_rectangle(GAME_INFO_RECT, radius=34, fill=theme['slab_fill'])
        overlay_draw.rounded_rectangle(GAME_HERO_RECT, radius=38, outline=(255, 255, 255, 26), width=2)
        overlay_draw.rounded_rectangle(
            (GAME_INFO_RECT[0] + 32, GAME_INFO_RECT[1] + 28, GAME_INFO_RECT[0] + 120, GAME_INFO_RECT[1] + 36),
            radius=4,
            fill=str(theme['accent']),
        )
        canvas = Image.alpha_composite(canvas.convert('RGBA'), overlay)
        draw = ImageDraw.Draw(canvas)

        self._draw_pill(
            draw,
            str(theme['kicker']),
            GAME_HERO_RECT[0] + 26,
            GAME_HERO_RECT[1] + 20,
            fill=str(theme['kicker_fill']),
            font=self.kicker_font,
            padding_x=18,
            padding_y=9,
            radius=20,
            text_fill='#f5f7fb',
        )

        badge_font = theme['badge_font']
        badge_width, badge_height = self._pill_size(draw, str(theme['badge_text']), badge_font, 22, 14)
        badge_x = GAME_HERO_RECT[2] - badge_width - 30
        badge_y = GAME_HERO_RECT[3] - (badge_height // 2)
        diagnostics.badge_rect = self._draw_pill(
            draw,
            str(theme['badge_text']),
            badge_x,
            badge_y,
            fill=str(theme['badge_fill']),
            font=badge_font,
            padding_x=22,
            padding_y=14,
            radius=26,
            text_fill='#ffffff',
        )

        title_lines, title_clipped, title_font = self._fit_title(
            draw,
            self._display_title(offer.title),
            max_width=760,
            max_lines=2,
            size_candidates=theme['title_sizes'],
        )
        diagnostics.title_lines = title_lines
        diagnostics.title_font_size = getattr(title_font, 'size', None)
        if title_clipped:
            diagnostics.clipped_fields.append('title')

        title_x = GAME_INFO_RECT[0] + 34
        title_y = GAME_INFO_RECT[1] + 48
        self._draw_lines(draw, title_lines, title_font, title_x, title_y, '#f8fbff', line_gap=8)
        meta_y = title_y + self._text_block_height(title_lines, title_font, 8) + 20

        if offer.is_freebie:
            deadline_rect = self._draw_pill(
                draw,
                self._format_deadline_chip(offer.promo_end, prefix='CLAIM BY'),
                title_x,
                meta_y,
                fill=str(theme['support_fill']),
                font=self.body_font,
                padding_x=18,
                padding_y=10,
                radius=20,
                text_fill='#edf5f0',
            )
            if offer.price_before_minor:
                draw.text(
                    (title_x, deadline_rect[3] + 18),
                    f'Was {self._format_minor(offer.price_before_minor)}',
                    font=self.body_font,
                    fill='#93a4bb',
                )
        else:
            price_bottom = self._draw_price_line(
                draw,
                title_x,
                meta_y,
                self._format_minor(offer.price_after_minor),
                self._format_minor(offer.price_before_minor),
            )
            self._draw_pill(
                draw,
                self._format_deadline_chip(offer.promo_end, prefix='ENDS'),
                title_x,
                price_bottom + 16,
                fill=str(theme['support_fill']),
                font=self.body_font,
                padding_x=18,
                padding_y=10,
                radius=20,
                text_fill='#edf4fb',
            )

        if offer.has_trading_cards:
            self._draw_pill(
                draw,
                'TRADING CARDS',
                GAME_INFO_RECT[2] - 284,
                GAME_INFO_RECT[3] - 74,
                fill='#a97817',
                font=self.small_font,
                padding_x=16,
                padding_y=9,
                radius=18,
                text_fill='#fff7dd',
            )

        self._draw_brand_lockup(draw, GAME_INFO_RECT, str(theme['brand_fill']))

        filename = self._safe_name(f'{template_id}_{offer.offer_id}_{offer.title}') + '.png'
        path = self.output_dir / filename
        canvas.convert('RGB').save(path, format='PNG', optimize=True)
        assets_used = self._dedupe_assets(primary_asset, hero_asset, background_asset)
        return TemplateRenderResult(image_path=path, assets_used=assets_used, diagnostics=diagnostics)

    async def _render_event(self, http: ResilientHttpClient, offer: Offer, template_id: str) -> TemplateRenderResult:
        diagnostics = RenderDiagnostics(template_id=template_id, asset_used=offer.primary_asset_url)
        if self._default_font_used:
            diagnostics.render_warnings.append('default_font_fallback')
        if diagnostics.asset_used is None:
            diagnostics.render_warnings.append('fallback_layout')
        diagnostics.layout_variant = 'festival_event_feature'
        diagnostics.hero_asset_used = diagnostics.asset_used
        diagnostics.hero_mode = 'cover'
        diagnostics.hero_rect = (0, 0, CARD_SIZE[0], CARD_SIZE[1])
        diagnostics.info_rect = EVENT_PANEL_RECT

        canvas = Image.new('RGB', CARD_SIZE, '#11161f')
        background = await self._download(http, diagnostics.asset_used, CARD_SIZE)
        background = self._build_background(background, CARD_SIZE, '#0b1017', 0.48, blur_radius=8)
        canvas.paste(background, (0, 0))

        overlay = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rounded_rectangle(EVENT_PANEL_RECT, radius=40, fill=(9, 14, 22, 222))
        overlay_draw.rounded_rectangle(
            (EVENT_PANEL_RECT[0] + 34, EVENT_PANEL_RECT[1] + 34, EVENT_PANEL_RECT[0] + 138, EVENT_PANEL_RECT[1] + 42),
            radius=4,
            fill='#f2b545',
        )
        canvas = Image.alpha_composite(canvas.convert('RGBA'), overlay)
        draw = ImageDraw.Draw(canvas)

        self._draw_pill(
            draw,
            self._event_kicker(offer.title),
            EVENT_PANEL_RECT[0] + 36,
            EVENT_PANEL_RECT[1] + 22,
            fill='#1d2430',
            font=self.kicker_font,
            padding_x=18,
            padding_y=9,
            radius=20,
            text_fill='#ffd56d',
        )

        title_lines, title_clipped, title_font = self._fit_title(
            draw,
            self._display_title(offer.title),
            max_width=560,
            max_lines=3,
            size_candidates=(78, 74, 70, 66, 62, 58, 54, 50),
        )
        diagnostics.title_lines = title_lines
        diagnostics.title_font_size = getattr(title_font, 'size', None)
        if title_clipped:
            diagnostics.clipped_fields.append('title')

        title_x = EVENT_PANEL_RECT[0] + 36
        title_y = EVENT_PANEL_RECT[1] + 110
        self._draw_lines(draw, title_lines, title_font, title_x, title_y, '#f9fbff', line_gap=8)
        title_bottom = title_y + self._text_block_height(title_lines, title_font, 8)
        diagnostics.badge_rect = self._draw_pill(
            draw,
            self._format_deadline_chip(offer.promo_end, prefix='LIVE TO'),
            title_x,
            title_bottom + 24,
            fill='#8a6319',
            font=self.body_font,
            padding_x=18,
            padding_y=10,
            radius=20,
            text_fill='#fff5db',
        )

        fallback_body = 'Discounts, demos, and themed picks worth checking before the event wraps.'
        body_copy = self._shorten_copy(offer.short_description or offer.description or fallback_body, 180)
        body_lines, body_clipped = self._wrap_text(draw, body_copy, self.body_font, 560, 3)
        if body_clipped:
            diagnostics.clipped_fields.append('description')
        self._draw_lines(draw, body_lines, self.body_font, title_x, diagnostics.badge_rect[3] + 24, '#d8dfeb', line_gap=6)
        self._draw_brand_lockup(draw, EVENT_PANEL_RECT, '#9facc0')

        filename = self._safe_name(f'{template_id}_{offer.offer_id}_{offer.title}') + '.png'
        path = self.output_dir / filename
        canvas.convert('RGB').save(path, format='PNG', optimize=True)
        assets_used = self._dedupe_assets(diagnostics.asset_used)
        return TemplateRenderResult(image_path=path, assets_used=assets_used, diagnostics=diagnostics)

    async def _download(self, http: ResilientHttpClient, url: str | None, size: tuple[int, int]) -> Image.Image:
        local_path = resolve_existing_asset_path(url)
        if local_path is not None:
            try:
                return Image.open(local_path).convert('RGB')
            except Exception:
                pass
        if url:
            try:
                content = await http.get_bytes(url)
                return Image.open(BytesIO(content)).convert('RGB')
            except Exception:
                pass
        return Image.new('RGB', size, '#1a2130')

    def _pick_primary_asset(self, offer: Offer) -> str | None:
        for asset in (offer.assets.hero, offer.assets.header, offer.assets.screenshot, offer.assets.fallback):
            if asset:
                return asset
        return None

    def _pick_hero_asset(self, offer: Offer) -> str | None:
        for asset in (offer.assets.screenshot, offer.assets.header, offer.assets.hero, offer.assets.fallback):
            if asset:
                return asset
        return None

    def _pick_background_asset(self, offer: Offer) -> str | None:
        for asset in (offer.assets.hero, offer.assets.header, offer.assets.screenshot, offer.assets.fallback):
            if asset:
                return asset
        return None

    def _game_theme(self, offer: Offer, template_id: str) -> dict[str, object]:
        theme: dict[str, object] = {
            'layout_variant': 'steam_discount',
            'kicker': 'STEAM DEAL',
            'kicker_fill': '#161c26',
            'badge_text': f'-{offer.discount_percent}%',
            'badge_fill': '#2477f5',
            'badge_font': self.badge_font_medium,
            'background_tint': '#0c1118',
            'hero_backdrop': '#131c28',
            'slab_fill': (8, 12, 18, 228),
            'support_fill': '#1a2330',
            'accent': '#2e84ff',
            'brand_fill': '#8798b0',
            'title_sizes': (82, 78, 74, 70, 66, 62, 58, 54, 50, 46, 42),
        }
        if template_id == 'epic_free':
            theme.update(
                {
                    'layout_variant': 'epic_free',
                    'kicker': 'EPIC FREEBIE',
                    'badge_text': 'FREE',
                    'badge_fill': '#1fc975',
                    'badge_font': self.badge_font_large,
                    'background_tint': '#0c1316',
                    'hero_backdrop': '#102018',
                    'slab_fill': (7, 13, 17, 226),
                    'support_fill': '#193323',
                    'accent': '#1fc975',
                    'brand_fill': '#8fa89a',
                }
            )
        elif template_id == 'steam_free':
            theme.update(
                {
                    'layout_variant': 'steam_free',
                    'kicker': 'STEAM FREEBIE',
                    'badge_text': 'FREE',
                    'badge_fill': '#22bf76',
                    'badge_font': self.badge_font_large,
                    'background_tint': '#0c1317',
                    'hero_backdrop': '#11211b',
                    'slab_fill': (7, 13, 18, 226),
                    'support_fill': '#183122',
                    'accent': '#22bf76',
                    'brand_fill': '#8fa89a',
                }
            )
        elif template_id == 'final_push':
            theme.update(
                {
                    'layout_variant': 'final_push',
                    'kicker': 'FINAL PUSH',
                    'badge_text': 'LAST CALL',
                    'badge_fill': '#db7421',
                    'badge_font': self.badge_font_small,
                    'background_tint': '#15100d',
                    'hero_backdrop': '#26150f',
                    'slab_fill': (18, 13, 10, 226),
                    'support_fill': '#352013',
                    'accent': '#ff943a',
                    'brand_fill': '#c1a38a',
                    'title_sizes': (80, 76, 72, 68, 64, 60, 56, 52, 48, 44),
                }
            )
        elif template_id == 'game_of_the_day':
            theme.update(
                {
                    'layout_variant': 'game_of_the_day',
                    'kicker': 'GAME OF THE DAY',
                    'badge_text': 'TOP PICK',
                    'badge_fill': '#7a55ff',
                    'badge_font': self.badge_font_small,
                    'background_tint': '#100d17',
                    'hero_backdrop': '#191229',
                    'slab_fill': (11, 10, 21, 226),
                    'support_fill': '#241b3c',
                    'accent': '#9a7bff',
                    'brand_fill': '#a79bc8',
                }
            )
        return theme

    def _build_background(
        self,
        image: Image.Image,
        size: tuple[int, int],
        tint: str,
        blend: float,
        *,
        blur_radius: int = 16,
    ) -> Image.Image:
        background = ImageOps.fit(image.convert('RGB'), size)
        background = background.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        return Image.blend(background, Image.new('RGB', size, tint), blend)

    def _compose_panel_image(
        self,
        image: Image.Image,
        size: tuple[int, int],
        mode: str,
        backdrop_tint: str,
    ) -> Image.Image:
        base = image.convert('RGB')
        if mode == 'contain':
            panel = self._build_background(base, size, backdrop_tint, 0.34, blur_radius=18)
            fitted = ImageOps.contain(base, (int(size[0] * 0.88), int(size[1] * 0.88)))
            offset = ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2)
            panel.paste(fitted, offset)
            return panel
        return ImageOps.fit(base, size)

    def _pick_hero_mode(self, image: Image.Image) -> str:
        aspect = image.width / max(image.height, 1)
        return 'contain' if aspect >= 2.3 else 'cover'

    def _paste_rounded(self, canvas: Image.Image, image: Image.Image, rect: tuple[int, int, int, int], radius: int) -> None:
        mask = Image.new('L', image.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle((0, 0, image.width - 1, image.height - 1), radius=radius, fill=255)
        canvas.paste(image, (rect[0], rect[1]), mask)

    def _draw_pill(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        x: int,
        y: int,
        *,
        fill: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        padding_x: int,
        padding_y: int,
        radius: int,
        text_fill: str,
    ) -> tuple[int, int, int, int]:
        bbox = draw.textbbox((x, y), text, font=font)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        rect = (x - padding_x, y - padding_y, x + width + padding_x, y + height + padding_y)
        draw.rounded_rectangle(rect, radius=radius, fill=fill)
        draw.text((x, y), text, font=font, fill=text_fill)
        return rect

    def _pill_size(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        padding_x: int,
        padding_y: int,
    ) -> tuple[int, int]:
        bbox = draw.textbbox((0, 0), text, font=font)
        return (bbox[2] - bbox[0]) + padding_x * 2, (bbox[3] - bbox[1]) + padding_y * 2

    def _fit_title(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        *,
        max_width: int,
        max_lines: int,
        size_candidates: Iterable[int],
    ) -> tuple[list[str], bool, ImageFont.FreeTypeFont | ImageFont.ImageFont]:
        chosen_font: ImageFont.FreeTypeFont | ImageFont.ImageFont = self.title_font
        chosen_lines: list[str] = [text]
        chosen_clipped = False
        for size in size_candidates:
            font = self._load_font(size=size, candidates=BOLD_FONT_CANDIDATES)
            lines, clipped = self._wrap_text(draw, text, font, max_width, max_lines)
            chosen_font = font
            chosen_lines = lines
            chosen_clipped = clipped
            if not clipped:
                break
        return chosen_lines, chosen_clipped, chosen_font

    def _wrap_text(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        max_width: int,
        max_lines: int,
    ) -> tuple[list[str], bool]:
        words = text.split()
        lines: list[str] = []
        current = ''
        clipped = False
        for word in words:
            candidate = word if not current else f'{current} {word}'
            if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
            current = word
            if len(lines) >= max_lines - 1:
                clipped = True
                break
        if current:
            lines.append(current)
        lines = lines[:max_lines]
        if clipped and lines:
            lines[-1] = lines[-1].rstrip(' ,.;:-') + '...'
        return lines, clipped

    def _draw_lines(
        self,
        draw: ImageDraw.ImageDraw,
        lines: Iterable[str],
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        x: int,
        y: int,
        fill: str,
        *,
        line_gap: int = 10,
    ) -> None:
        line_height = getattr(font, 'size', 24) + line_gap
        for index, line in enumerate(lines):
            draw.text((x, y + index * line_height), line, font=font, fill=fill)

    def _text_block_height(
        self,
        lines: Iterable[str],
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        line_gap: int,
    ) -> int:
        count = len(list(lines))
        if count <= 0:
            return 0
        return count * getattr(font, 'size', 24) + max(0, count - 1) * line_gap

    def _draw_price_line(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        after: str,
        before: str,
    ) -> int:
        draw.text((x, y), after, font=self.price_font, fill='#f7fbff')
        after_bbox = draw.textbbox((x, y), after, font=self.price_font)
        if before != '?':
            before_x = after_bbox[2] + 18
            before_y = y + 10
            draw.text((before_x, before_y), before, font=self.body_font, fill='#93a4bb')
            before_bbox = draw.textbbox((before_x, before_y), before, font=self.body_font)
            strike_y = (before_bbox[1] + before_bbox[3]) // 2
            draw.line((before_bbox[0], strike_y, before_bbox[2], strike_y), fill='#6f8096', width=2)
            return max(after_bbox[3], before_bbox[3])
        return after_bbox[3]

    def _draw_brand_lockup(
        self,
        draw: ImageDraw.ImageDraw,
        rect: tuple[int, int, int, int],
        fill: str,
    ) -> None:
        label = 'YOTO'
        bbox = draw.textbbox((0, 0), label, font=self.brand_font)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        draw.text((rect[2] - width - 30, rect[3] - height - 24), label, font=self.brand_font, fill=fill)

    @staticmethod
    def _rect_size(rect: tuple[int, int, int, int]) -> tuple[int, int]:
        return rect[2] - rect[0], rect[3] - rect[1]

    @staticmethod
    def _shorten_copy(text: str, limit: int) -> str:
        cleaned = re.sub(r'\s+', ' ', (text or '').strip())
        if len(cleaned) <= limit:
            return cleaned
        chunk = cleaned[: limit + 1].rsplit(' ', 1)[0].strip()
        return (chunk or cleaned[:limit].strip()).rstrip(' ,.;:-') + '...'

    @staticmethod
    def _clean_title(title: str) -> str:
        cleaned = title
        for token in TITLE_CLEANERS:
            cleaned = cleaned.replace(token, '')
        return re.sub(r'\s+', ' ', cleaned).strip()

    @staticmethod
    def _display_title(title: str) -> str:
        cleaned = TemplateSystem._clean_title(title)
        if len(cleaned) <= 42:
            return cleaned
        for marker in (' - ', ': ', ' | ', ' \u2014 ', ' \u2013 '):
            if marker not in cleaned:
                continue
            lead = cleaned.split(marker, 1)[0].strip()
            if len(lead) >= 10:
                return lead
        return cleaned

    @staticmethod
    def _safe_name(value: str) -> str:
        return re.sub(r'[^a-zA-Z0-9\u0430-\u044f\u0410-\u042f\u0456\u0457\u0454\u0491\u0406\u0407\u0404\u0490_-]+', '_', value)[:120].strip('_') or 'card'

    @staticmethod
    def _format_minor(value: int | None) -> str:
        if value is None:
            return '?'
        amount = value / 100
        if int(amount) == amount:
            return f'{int(amount)} \u0433\u0440\u043d'
        return f'{amount:.2f} \u0433\u0440\u043d'

    @staticmethod
    def _format_deadline_chip(value, *, prefix: str) -> str:
        if value is None:
            return prefix
        if value.hour or value.minute:
            return f'{prefix} {value.day:02d}.{value.month:02d}, {value.hour:02d}:{value.minute:02d}'
        return f'{prefix} {value.day:02d}.{value.month:02d}'

    @staticmethod
    def _event_kicker(title: str) -> str:
        lowered = (title or '').lower()
        if 'fest' in lowered or 'festival' in lowered:
            return 'STEAM FESTIVAL'
        if 'sale' in lowered:
            return 'STEAM SALE EVENT'
        return 'STEAM EVENT'

    @staticmethod
    def _dedupe_assets(*values: str | None) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            if not value or value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    def _load_font(self, *, size: int, candidates: tuple[str, ...]) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        for path in self._font_paths(candidates):
            try:
                font = self._load_truetype(path, size)
                if font.getbbox(CYRILLIC_FONT_SAMPLE):
                    return font
            except Exception:
                continue
        self._default_font_used = True
        return ImageFont.load_default()

    def _font_paths(self, candidates: tuple[str, ...]) -> Iterable[Path]:
        seen: set[Path] = set()
        for name in candidates:
            for path in (
                self.repo_font_dir / name,
                Path('C:/Windows/Fonts') / name,
                Path('/usr/share/fonts/truetype/dejavu') / name,
                Path('/usr/share/fonts/truetype/noto') / name,
                Path('/Library/Fonts') / name,
            ):
                if path in seen or not path.exists():
                    continue
                seen.add(path)
                yield path

    @staticmethod
    def _load_truetype(path: Path, size: int) -> ImageFont.FreeTypeFont:
        layout = TemplateSystem._layout_engine()
        if layout is None:
            return ImageFont.truetype(str(path), size=size)
        return ImageFont.truetype(str(path), size=size, layout_engine=layout)

    @staticmethod
    def _layout_engine():
        layout = getattr(ImageFont, 'Layout', None)
        if layout is None:
            return None
        return getattr(layout, 'BASIC', None)




