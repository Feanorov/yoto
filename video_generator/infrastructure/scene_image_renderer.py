from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from ..domain.entities import PlannedScene, RenderedScene, VideoManifest, VideoTemplate
from ..domain.scene_planner import ScenePlanner
from .asset_resolver import AssetResolver, ResolvedAssets
from .font_loader import FontLoader
from .structured_logger import StructuredLogger


class SceneImageRenderer:
    WIDTH = 1080
    HEIGHT = 1920
    OFFER_KIND_LABELS = {
        'discount': '??????',
        'freebie': '??????????? ???????',
        'festival': '?????',
        'event': '?????',
    }

    def __init__(
        self,
        asset_resolver: AssetResolver,
        font_loader: FontLoader,
        logger: StructuredLogger | None = None,
    ) -> None:
        self.asset_resolver = asset_resolver
        self.font_loader = font_loader
        self.logger = logger or StructuredLogger()

    def render(
        self,
        manifest: VideoManifest,
        template: VideoTemplate,
        assets: ResolvedAssets,
        temp_dir: Path,
        planned_scenes: tuple[PlannedScene, ...],
    ) -> tuple[RenderedScene, ...]:
        temp_dir.mkdir(parents=True, exist_ok=True)
        scenes: list[RenderedScene] = []
        for planned_scene in planned_scenes:
            scene_path = temp_dir / f'scene_{planned_scene.position:03d}.png'
            self._render_scene_image(
                path=scene_path,
                scene_id=planned_scene.scene_id,
                manifest=manifest,
                template=template,
                assets=assets,
                headline=planned_scene.headline,
                body=planned_scene.body,
                cta=planned_scene.cta,
            )
            scenes.append(
                RenderedScene(
                    scene_id=planned_scene.scene_id,
                    position=planned_scene.position,
                    duration_seconds=planned_scene.duration_seconds,
                    overlay_text=' '.join(
                        value for value in (planned_scene.headline, planned_scene.body, planned_scene.cta) if value
                    ),
                    voiceover_text=planned_scene.voiceover_text,
                    image_path=scene_path,
                    asset_path=assets.game_image.path,
                )
            )
        return tuple(scenes)

    def _render_scene_image(
        self,
        *,
        path: Path,
        scene_id: str,
        manifest: VideoManifest,
        template: VideoTemplate,
        assets: ResolvedAssets,
        headline: str,
        body: str,
        cta: str | None,
    ) -> None:
        canvas = self._build_canvas(template, assets)
        overlay = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        layout = self._scene_layout(template.name, scene_id)

        self._draw_store_badge(overlay, assets)
        self._draw_panel(draw, template, layout['panel_rect'])

        y = layout['headline_y']
        y = self._draw_text_block(
            draw=draw,
            text=headline,
            role='headline',
            fill=template.accent,
            x=layout['headline_x'],
            y=y,
            attempts=layout['headline_attempts'],
            scene_id=scene_id,
            field='headline',
        )
        y = self._draw_text_block(
            draw=draw,
            text=body,
            role='subtitle',
            fill=(255, 255, 255),
            x=layout['body_x'],
            y=y + layout['body_gap'],
            attempts=layout['body_attempts'],
            scene_id=scene_id,
            field='body',
        )
        if cta:
            self._draw_cta(draw, cta, template, scene_id, layout['cta_rect'], layout['cta_attempts'])

        composed = Image.alpha_composite(canvas, overlay)
        composed.convert('RGB').save(path)

    def _build_canvas(self, template: VideoTemplate, assets: ResolvedAssets) -> Image.Image:
        canvas = self._vertical_gradient(template.background_top, template.background_bottom)
        background = self.asset_resolver.load_prepared_image(assets.background.path)
        background = ImageOps.fit(background, (self.WIDTH, self.HEIGHT), Image.Resampling.LANCZOS)
        background = background.filter(ImageFilter.GaussianBlur(radius=16))
        background.putalpha(110)
        canvas.alpha_composite(background)

        hero = self.asset_resolver.load_prepared_image(assets.game_image.path)
        shadow = Image.new('RGBA', (hero.width + 40, hero.height + 40), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rounded_rectangle((16, 16, shadow.width - 16, shadow.height - 16), radius=44, fill=(0, 0, 0, 160))
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=18))

        hero_frame = Image.new('RGBA', (hero.width + 36, hero.height + 36), (255, 255, 255, 0))
        hero_draw = ImageDraw.Draw(hero_frame)
        hero_draw.rounded_rectangle((0, 0, hero_frame.width - 1, hero_frame.height - 1), radius=48, fill=(255, 255, 255, 12))
        hero_frame.alpha_composite(hero, dest=(18, 18))

        x = (self.WIDTH - hero_frame.width) // 2
        y = 220
        canvas.alpha_composite(shadow, dest=(x - 2, y + 10))
        canvas.alpha_composite(hero_frame, dest=(x, y))
        return canvas

    def _draw_store_badge(self, overlay: Image.Image, assets: ResolvedAssets) -> None:
        if assets.store_badge is None:
            return
        badge = self.asset_resolver.load_prepared_image(assets.store_badge)
        badge.thumbnail((300, 120), Image.Resampling.LANCZOS)
        overlay.alpha_composite(badge, dest=(92, 86))

    @staticmethod
    def _draw_panel(draw: ImageDraw.ImageDraw, template: VideoTemplate, rect: tuple[int, int, int, int]) -> None:
        draw.rounded_rectangle(rect, radius=52, fill=template.panel)

    def _draw_cta(
        self,
        draw: ImageDraw.ImageDraw,
        cta: str,
        template: VideoTemplate,
        scene_id: str,
        rect: tuple[int, int, int, int],
        attempts: tuple[tuple[int, int, int, int], ...],
    ) -> None:
        font, lines, truncated, _, _, line_gap = self._fit_text(draw, cta, 'cta', attempts)
        if truncated:
            self.logger.warning('text truncated', scene_id=scene_id, field='cta')
        line_height = self._line_height(font)
        block_height = len(lines) * line_height + max(len(lines) - 1, 0) * line_gap
        left, top, right, bottom = rect
        y = top + max((bottom - top - block_height) // 2, 0)
        draw.rounded_rectangle(rect, radius=36, fill=template.cta)
        for line in lines:
            box = draw.textbbox((0, 0), line, font=font)
            width = box[2] - box[0]
            draw.text(((left + right - width) / 2, y), line, font=font, fill=(24, 24, 24))
            y += line_height + line_gap

    def _draw_text_block(
        self,
        *,
        draw: ImageDraw.ImageDraw,
        text: str,
        role: str,
        fill: tuple[int, int, int],
        x: int,
        y: int,
        attempts: tuple[tuple[int, int, int, int], ...],
        scene_id: str,
        field: str,
    ) -> int:
        font, lines, truncated, _, _, line_gap = self._fit_text(draw, text, role, attempts)
        if truncated:
            self.logger.warning('text truncated', scene_id=scene_id, field=field)
        line_height = self._line_height(font)
        for line in lines:
            draw.text((x, y), line, font=font, fill=fill)
            y += line_height + line_gap
        return y

    def _fit_text(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        role: str,
        attempts: tuple[tuple[int, int, int, int], ...],
    ) -> tuple[object, list[str], bool, int, int, int]:
        base_font = self.font_loader.load(role)
        result = None
        for size_delta, max_width, max_lines, line_gap in attempts:
            font = self._font_with_delta(base_font, size_delta)
            lines, truncated = self._wrap_text(draw, text, font, max_width=max_width, max_lines=max_lines)
            result = (font, lines, truncated, max_width, max_lines, line_gap)
            if not truncated:
                return result
        assert result is not None
        return result

    @staticmethod
    def _font_with_delta(font, size_delta: int):
        if size_delta == 0 or not hasattr(font, 'font_variant'):
            return font
        size = getattr(font, 'size', None)
        if not isinstance(size, int):
            return font
        try:
            return font.font_variant(size=max(size + size_delta, 24))
        except Exception:
            return font

    def _wrap_text(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font,
        *,
        max_width: int,
        max_lines: int,
    ) -> tuple[list[str], bool]:
        paragraphs = [paragraph.strip() for paragraph in str(text or '').splitlines() if paragraph.strip()]
        if not paragraphs:
            paragraphs = [' '.join(str(text or '').split())]
        if not any(paragraphs):
            return [''], False

        lines: list[str] = []
        truncated = False
        for paragraph in paragraphs:
            paragraph_lines, paragraph_truncated = self._wrap_single_paragraph(
                draw,
                paragraph,
                font,
                max_width=max_width,
                max_lines=max_lines - len(lines),
            )
            truncated = truncated or paragraph_truncated
            if not paragraph_lines:
                continue
            lines.extend(paragraph_lines)
            if len(lines) >= max_lines:
                return lines[:max_lines], True if paragraph_truncated or len(lines) > max_lines else truncated

        return lines or [''], truncated

    def _wrap_single_paragraph(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font,
        *,
        max_width: int,
        max_lines: int,
    ) -> tuple[list[str], bool]:
        words = text.split()
        if not words or max_lines <= 0:
            return [], bool(words)

        lines: list[str] = []
        current = ''
        truncated = False
        index = 0
        while index < len(words):
            word = words[index]
            trial = word if not current else f'{current} {word}'
            if self._text_width(draw, trial, font) <= max_width:
                current = trial
                index += 1
                continue

            if current:
                lines.append(current)
                current = ''
            else:
                lines.append(self._truncate_to_width(draw, word, font, max_width))
                truncated = True
                index += 1

            if len(lines) == max_lines:
                remaining = ' '.join(words[index:]).strip()
                if remaining:
                    lines[-1] = self._truncate_to_width(draw, f'{lines[-1]} {remaining}'.strip(), font, max_width)
                    truncated = True
                return lines, truncated

        if current:
            if len(lines) < max_lines:
                lines.append(current)
            else:
                lines[-1] = self._truncate_to_width(draw, f'{lines[-1]} {current}'.strip(), font, max_width)
                truncated = True
        return lines, truncated

    def _truncate_to_width(self, draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
        if self._text_width(draw, text, font) <= max_width:
            return text
        ellipsis = '...'
        stripped = text.strip()
        while stripped and self._text_width(draw, stripped + ellipsis, font) > max_width:
            stripped = stripped[:-1].rstrip()
        return (stripped or text[:1]) + ellipsis

    @staticmethod
    def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
        box = draw.textbbox((0, 0), text, font=font)
        return box[2] - box[0]

    @staticmethod
    def _line_height(font) -> int:
        box = font.getbbox('Ay')
        return box[3] - box[1]

    @classmethod
    def _scene_layout(cls, template_name: str, scene_id: str) -> dict[str, object]:
        if scene_id == 'hook':
            layout: dict[str, object] = {
                'panel_rect': (48, 1004, 1032, 1848),
                'headline_x': 84,
                'headline_y': 1044,
                'headline_attempts': (
                    (0, 900, 2, 10),
                    (-10, 924, 3, 8),
                    (-18, 948, 3, 6),
                    (-26, 964, 4, 4),
                    (-34, 980, 4, 2),
                ),
                'body_x': 84,
                'body_gap': 24,
                'body_attempts': (
                    (0, 900, 3, 8),
                    (-4, 924, 3, 6),
                ),
                'cta_rect': (84, 1548, 996, 1798),
                'cta_attempts': (
                    (0, 796, 2, 8),
                    (-8, 836, 3, 6),
                    (-14, 860, 3, 4),
                ),
            }
        elif scene_id in {'summary', 'roundup_page_one', 'roundup_page_two'}:
            layout = {
                'panel_rect': (48, 1000, 1032, 1848),
                'headline_x': 84,
                'headline_y': 1042,
                'headline_attempts': (
                    (0, 900, 2, 10),
                    (-8, 924, 3, 8),
                    (-14, 948, 3, 6),
                    (-24, 964, 4, 4),
                    (-34, 980, 4, 2),
                ),
                'body_x': 84,
                'body_gap': 22,
                'body_attempts': (
                    (0, 904, 2, 8),
                    (-4, 924, 2, 6),
                ),
                'cta_rect': (84, 1548, 996, 1798),
                'cta_attempts': (
                    (0, 796, 2, 8),
                    (-8, 836, 3, 6),
                    (-14, 860, 3, 4),
                ),
            }
        else:
            layout = {
                'panel_rect': (40, 980, 1040, 1864),
                'headline_x': 80,
                'headline_y': 1028,
                'headline_attempts': (
                    (0, 900, 2, 10),
                    (-10, 924, 3, 8),
                    (-18, 948, 3, 6),
                    (-28, 980, 4, 4),
                    (-36, 992, 4, 2),
                ),
                'body_x': 80,
                'body_gap': 18,
                'body_attempts': (
                    (0, 900, 1, 8),
                    (-4, 920, 2, 6),
                ),
                'cta_rect': (72, 1512, 1008, 1812),
                'cta_attempts': (
                    (0, 804, 2, 8),
                    (-8, 840, 3, 6),
                    (-14, 864, 3, 4),
                ),
            }

        if template_name == 'freebie_flash':
            layout['headline_attempts'] = cls._adjust_attempts(layout['headline_attempts'], width_delta=16)
            layout['body_attempts'] = cls._adjust_attempts(layout['body_attempts'], width_delta=16)
            layout['cta_attempts'] = cls._adjust_attempts(layout['cta_attempts'], width_delta=20)
        elif template_name == 'event_countdown':
            line_delta = 1 if scene_id != 'hook' else 0
            layout['headline_attempts'] = cls._adjust_attempts(layout['headline_attempts'], width_delta=18)
            layout['body_attempts'] = cls._adjust_attempts(layout['body_attempts'], width_delta=12, line_delta=line_delta)
            if scene_id == 'urgency':
                layout['panel_rect'] = (40, 970, 1040, 1868)
                layout['headline_y'] = 1020
                layout['cta_rect'] = (66, 1502, 1014, 1816)
                layout['cta_attempts'] = cls._adjust_attempts(layout['cta_attempts'], width_delta=28)
        elif template_name == 'deadline_push' and scene_id == 'urgency':
            layout['headline_y'] = 1018
            layout['headline_attempts'] = cls._adjust_attempts(layout['headline_attempts'], width_delta=20)
            layout['cta_rect'] = (66, 1498, 1014, 1818)
            layout['cta_attempts'] = cls._adjust_attempts(layout['cta_attempts'], width_delta=32)

        return layout

    @staticmethod
    def _adjust_attempts(
        attempts: tuple[tuple[int, int, int, int], ...],
        *,
        width_delta: int = 0,
        line_delta: int = 0,
    ) -> tuple[tuple[int, int, int, int], ...]:
        return tuple(
            (size_delta, max_width + width_delta, max(max_lines + line_delta, 1), line_gap)
            for size_delta, max_width, max_lines, line_gap in attempts
        )

    @classmethod
    def _vertical_gradient(cls, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
        image = Image.new('RGBA', (cls.WIDTH, cls.HEIGHT), top + (255,))
        draw = ImageDraw.Draw(image)
        for y in range(cls.HEIGHT):
            ratio = y / (cls.HEIGHT - 1)
            color = tuple(int(start + (end - start) * ratio) for start, end in zip(top, bottom))
            draw.line((0, y, cls.WIDTH, y), fill=color + (255,))
        return image

    @staticmethod
    def _call_to_action(manifest: VideoManifest) -> str:
        return ScenePlanner._call_to_action(manifest)

    @classmethod
    def _supporting_line(cls, manifest: VideoManifest) -> str:
        return ScenePlanner._supporting_line(manifest)
