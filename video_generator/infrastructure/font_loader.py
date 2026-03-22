from __future__ import annotations

from pathlib import Path
import shutil

from PIL import ImageFont

from .structured_logger import StructuredLogger


class FontLoader:
    ROLE_SIZES = {
        'headline': 120,
        'title': 80,
        'subtitle': 60,
        'cta': 70,
    }

    CYRILLIC_SAMPLE = 'Привіт Її Єє Іі Ґґ'

    BOLD_CANDIDATES = (
        'arialbd.ttf',
        'segoeuib.ttf',
        'tahomabd.ttf',
        'DejaVuSans-Bold.ttf',
        'NotoSans-Bold.ttf',
        'Arial Bold.ttf',
    )

    REGULAR_CANDIDATES = (
        'arial.ttf',
        'segoeui.ttf',
        'tahoma.ttf',
        'DejaVuSans.ttf',
        'NotoSans-Regular.ttf',
        'NotoSans.ttf',
        'Arial.ttf',
    )

    def __init__(self, font_dir: Path | None = None, logger: StructuredLogger | None = None) -> None:
        self.font_dir = font_dir or Path(__file__).resolve().parents[1] / 'assets' / 'fonts'
        self.font_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logger or StructuredLogger()
        self._cache: dict[tuple[str, int], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}
        self._bootstrap_fonts()

    def load(self, role: str) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        if role not in self.ROLE_SIZES:
            raise KeyError(f'Unknown font role: {role}')

        size = self.ROLE_SIZES[role]
        font_path = self.resolve_font_path(role)
        if font_path is None:
            cache_key = (f'default:{role}', size)
            if cache_key not in self._cache:
                self.logger.warning('font fallback used', role=role, reason='no_cyrillic_font_found')
                self._cache[cache_key] = ImageFont.load_default()
            return self._cache[cache_key]

        cache_key = (str(font_path), size)
        if cache_key not in self._cache:
            self._cache[cache_key] = self._load_truetype(font_path, size)
        return self._cache[cache_key]

    def resolve_font_path(self, role: str) -> Path | None:
        if role not in self.ROLE_SIZES:
            raise KeyError(f'Unknown font role: {role}')
        weight = 'bold' if role in {'headline', 'title', 'cta'} else 'regular'
        return self._resolve_font_path(weight)

    def _resolve_font_path(self, weight: str) -> Path | None:
        candidates = self.BOLD_CANDIDATES if weight == 'bold' else self.REGULAR_CANDIDATES
        for name in candidates:
            path = self.font_dir / name
            if self._is_usable_font(path):
                return path
        return None

    def _is_usable_font(self, path: Path) -> bool:
        if not path.exists():
            return False
        try:
            font = self._load_truetype(path, 32)
            return bool(font.getbbox(self.CYRILLIC_SAMPLE))
        except Exception as exc:
            self.logger.warning('font candidate skipped', font_path=path, error=str(exc))
            return False

    @staticmethod
    def _load_truetype(path: Path, size: int) -> ImageFont.FreeTypeFont:
        layout = FontLoader._layout_engine()
        if layout is None:
            return ImageFont.truetype(str(path), size=size)
        return ImageFont.truetype(str(path), size=size, layout_engine=layout)

    def _bootstrap_fonts(self) -> None:
        if any(self.font_dir.glob('*.ttf')) or any(self.font_dir.glob('*.otf')):
            return

        copied = 0
        for candidate in self._system_font_candidates():
            if not candidate.exists():
                continue
            target = self.font_dir / candidate.name
            if target.exists():
                continue
            shutil.copy2(candidate, target)
            copied += 1

        if copied:
            self.logger.info('fonts bootstrapped', font_dir=self.font_dir, copied=copied)

    @staticmethod
    def _layout_engine():
        layout = getattr(ImageFont, 'Layout', None)
        if layout is None:
            return None
        return getattr(layout, 'BASIC', None)

    @staticmethod
    def _system_font_candidates() -> tuple[Path, ...]:
        return (
            Path('C:/Windows/Fonts/arialbd.ttf'),
            Path('C:/Windows/Fonts/arial.ttf'),
            Path('C:/Windows/Fonts/segoeuib.ttf'),
            Path('C:/Windows/Fonts/segoeui.ttf'),
            Path('C:/Windows/Fonts/tahomabd.ttf'),
            Path('C:/Windows/Fonts/tahoma.ttf'),
            Path('C:/Windows/Fonts/DejaVuSans-Bold.ttf'),
            Path('C:/Windows/Fonts/DejaVuSans.ttf'),
            Path('C:/Windows/Fonts/NotoSans-Bold.ttf'),
            Path('C:/Windows/Fonts/NotoSans-Regular.ttf'),
            Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
            Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
            Path('/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf'),
            Path('/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf'),
            Path('/Library/Fonts/Arial Bold.ttf'),
            Path('/Library/Fonts/Arial.ttf'),
        )
