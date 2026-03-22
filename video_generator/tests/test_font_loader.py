from __future__ import annotations

import shutil
from pathlib import Path

from PIL import ImageFont

from video_generator.infrastructure.font_loader import FontLoader


REPO_FONT_DIR = Path(__file__).resolve().parents[1] / 'assets' / 'fonts'


class NoBootstrapFontLoader(FontLoader):
    def _bootstrap_fonts(self) -> None:
        return


def copy_font(tmp_path: Path, filename: str) -> Path:
    source = REPO_FONT_DIR / filename
    target = tmp_path / filename
    shutil.copy2(source, target)
    return target


def test_preferred_font_path_loads_cyrillic_capable_font_when_available(tmp_path: Path) -> None:
    copy_font(tmp_path, 'arialbd.ttf')
    copy_font(tmp_path, 'tahomabd.ttf')
    copy_font(tmp_path, 'arial.ttf')

    loader = NoBootstrapFontLoader(font_dir=tmp_path)

    resolved = loader.resolve_font_path('headline')
    loaded = loader.load('headline')

    assert resolved is not None
    assert resolved.name == 'arialbd.ttf'
    assert isinstance(loaded, ImageFont.FreeTypeFont)


def test_fallback_chain_works_deterministically(tmp_path: Path) -> None:
    copy_font(tmp_path, 'tahomabd.ttf')
    copy_font(tmp_path, 'arial.ttf')

    loader = NoBootstrapFontLoader(font_dir=tmp_path)

    resolved = loader.resolve_font_path('headline')

    assert resolved is not None
    assert resolved.name == 'tahomabd.ttf'



def test_missing_preferred_font_still_degrades_safely(tmp_path: Path) -> None:
    loader = NoBootstrapFontLoader(font_dir=tmp_path)

    resolved = loader.resolve_font_path('headline')
    loaded = loader.load('headline')

    assert resolved is None
    assert loaded is not None
