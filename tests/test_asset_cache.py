from __future__ import annotations

from email.message import Message
import io
from pathlib import Path

from PIL import Image

from infrastructure.render.cards.asset_sources import asset_cache


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new('RGBA', (1, 1), (255, 0, 0, 255)).save(buffer, format='PNG')
    return buffer.getvalue()


class FakeResponse:
    def __init__(self, data: bytes, *, content_type: str, content_length: int | None = None) -> None:
        self._stream = io.BytesIO(data)
        headers = Message()
        headers.add_header('Content-Type', content_type)
        if content_length is not None:
            headers.add_header('Content-Length', str(content_length))
        self.headers = headers

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def __enter__(self) -> 'FakeResponse':
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_download_remote_asset_writes_local_cache(monkeypatch, tmp_path: Path) -> None:
    png_bytes = _png_bytes()

    def fake_urlopen(request, timeout: int) -> FakeResponse:
        return FakeResponse(
            png_bytes,
            content_type='image/png',
            content_length=len(png_bytes),
        )

    monkeypatch.setattr(asset_cache.urllib.request, 'urlopen', fake_urlopen)
    target = tmp_path / 'steam' / 'capsule.png'

    result = asset_cache.download_remote_asset(
        remote_url='https://example.com/capsule.png',
        cache_path=target,
    )

    assert result.cache_status == 'downloaded'
    assert result.download_attempted is True
    assert target.exists()
    assert asset_cache.is_readable_image(target) is True


def test_download_remote_asset_rejects_invalid_content_type(monkeypatch, tmp_path: Path) -> None:
    def fake_urlopen(request, timeout: int) -> FakeResponse:
        return FakeResponse(
            b'not-an-image',
            content_type='text/plain',
            content_length=len(b'not-an-image'),
        )

    monkeypatch.setattr(asset_cache.urllib.request, 'urlopen', fake_urlopen)
    target = tmp_path / 'steam' / 'bad.png'

    result = asset_cache.download_remote_asset(
        remote_url='https://example.com/bad.png',
        cache_path=target,
    )

    assert result.cache_status == 'invalid_content_type'
    assert result.download_attempted is True
    assert not target.exists()
