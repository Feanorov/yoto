from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from ..models import Offer, PostKind
from ..utils.ua import format_deadline, format_price_uah


class CardRenderer:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.title_font = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 62)
        self.body_font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 30)
        self.small_font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 24)
        self.badge_font = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 28)

    async def render(self, client: httpx.AsyncClient, offer: Offer) -> Path:
        if offer.source.value == "event":
            return await self._render_event(client, offer)
        return await self._render_game(client, offer)

    async def _render_game(self, client: httpx.AsyncClient, offer: Offer) -> Path:
        canvas = Image.new("RGB", (1280, 720), "#10131b")
        bg = await self._download_image(client, offer.screenshot_url or offer.hero_image_url or offer.image_url, (1280, 720))
        bg = bg.filter(ImageFilter.GaussianBlur(radius=10)).convert("RGB")
        bg = Image.blend(bg, Image.new("RGB", bg.size, "#0c1018"), 0.45)
        canvas.paste(bg, (0, 0))

        cover = await self._download_image(client, offer.hero_image_url or offer.image_url, (400, 560))
        cover = ImageOps.fit(cover.convert("RGB"), (400, 560))
        screenshot = await self._download_image(client, offer.screenshot_url or offer.hero_image_url or offer.image_url, (700, 300))
        screenshot = ImageOps.fit(screenshot.convert("RGB"), (700, 300))

        canvas.paste(cover, (48, 80))
        canvas.paste(screenshot, (532, 72))

        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        draw.rounded_rectangle((520, 390, 1230, 675), radius=36, fill=(12, 16, 24, 220))
        draw.rounded_rectangle((36, 36, 240, 92), radius=28, fill=(18, 22, 34, 220))
        canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay)
        draw = ImageDraw.Draw(canvas)

        store_label = "STEAM" if offer.source.value == "steam" else "EPIC GAMES"
        draw.text((64, 49), store_label, font=self.badge_font, fill="#f4f7fb")

        self._draw_multiline(draw, offer.title, self.title_font, 550, 420, 620, 2, "#f9fbff")

        badge_text = "БЕЗКОШТОВНО" if offer.is_free_to_keep else f"-{offer.discount_pct}%"
        self._draw_badge(draw, badge_text, 550, 560, "#18b66b" if offer.is_free_to_keep else "#1678ff")

        price_text = "Steam Роздача" if offer.is_free_to_keep else f"{format_price_uah(offer.final_price_uah)} / {format_price_uah(offer.original_price_uah)}"
        draw.text((550, 622), price_text, font=self.body_font, fill="#f9fbff")

        if offer.improvement_note:
            self._draw_multiline(draw, offer.improvement_note, self.small_font, 830, 560, 380, 3, "#b8d7ff")

        deadline = format_deadline(offer.sale_end)
        if deadline:
            draw.text((550, 664), f"До {deadline}", font=self.small_font, fill="#d8dfeb")

        if offer.has_trading_cards:
            self._draw_badge(draw, "ЗНАЧОК", 1000, 622, "#c48715")

        filename = self._safe_name(f"{offer.source.value}_{offer.offer_id}_{offer.title}") + ".png"
        path = self.output_dir / filename
        canvas.convert("RGB").save(path, format="PNG", optimize=True)
        return path

    async def _render_event(self, client: httpx.AsyncClient, offer: Offer) -> Path:
        canvas = Image.new("RGB", (1280, 720), "#11161f")
        bg = await self._download_image(client, offer.image_url or offer.hero_image_url or offer.screenshot_url, (1280, 720))
        bg = bg.filter(ImageFilter.GaussianBlur(radius=12)).convert("RGB")
        bg = Image.blend(bg, Image.new("RGB", bg.size, "#0b0f16"), 0.55)
        canvas.paste(bg, (0, 0))

        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        draw.rounded_rectangle((72, 78, 1208, 648), radius=42, fill=(11, 15, 23, 210))
        canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay)
        draw = ImageDraw.Draw(canvas)

        draw.text((108, 126), "STEAM FESTIVAL", font=self.badge_font, fill="#ffd56d")
        self._draw_multiline(draw, offer.title, self.title_font, 108, 196, 1000, 3, "#f9fbff")
        self._draw_multiline(draw, offer.description or "Велика подія у Steam з акціями, демоверсіями та тематичними добірками.", self.body_font, 108, 372, 1020, 5, "#d8dfeb")
        deadline = format_deadline(offer.sale_end)
        if deadline:
            draw.text((108, 594), f"Триває до {deadline}", font=self.body_font, fill="#f9fbff")

        filename = self._safe_name(f"event_{offer.offer_id}_{offer.title}") + ".png"
        path = self.output_dir / filename
        canvas.convert("RGB").save(path, format="PNG", optimize=True)
        return path

    async def _download_image(self, client: httpx.AsyncClient, url: str | None, size: tuple[int, int]) -> Image.Image:
        if url:
            try:
                response = await client.get(url)
                response.raise_for_status()
                return Image.open(BytesIO(response.content)).convert("RGB")
            except Exception:
                pass
        return Image.new("RGB", size, "#1b2333")

    def _draw_badge(self, draw: ImageDraw.ImageDraw, text: str, x: int, y: int, color: str) -> None:
        bbox = draw.textbbox((x, y), text, font=self.badge_font)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        draw.rounded_rectangle((x - 18, y - 10, x + width + 18, y + height + 10), radius=22, fill=color)
        draw.text((x, y), text, font=self.badge_font, fill="#ffffff")

    def _draw_multiline(self, draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, x: int, y: int, max_width: int, max_lines: int, fill: str) -> None:
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
                current = candidate
                continue
            lines.append(current)
            current = word
            if len(lines) == max_lines - 1:
                break
        if current:
            lines.append(current)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
        if len(lines) == max_lines and words:
            last = lines[-1]
            if not last.endswith("..."):
                lines[-1] = last.rstrip(" ,.;:-") + "..."
        line_height = font.size + 12
        for index, line in enumerate(lines[:max_lines]):
            draw.text((x, y + index * line_height), line, font=font, fill=fill)

    @staticmethod
    def _safe_name(value: str) -> str:
        value = re.sub(r"[^a-zA-Z0-9а-яА-ЯіїєґІЇЄҐ_-]+", "_", value)
        return value[:120].strip("_") or "card"
