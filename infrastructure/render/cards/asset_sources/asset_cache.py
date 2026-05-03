from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import socket
import urllib.error
import urllib.request

from PIL import Image


ASSET_DOWNLOAD_TIMEOUT_SECONDS = 10
ASSET_DOWNLOAD_MAX_BYTES = 8 * 1024 * 1024
_DOWNLOAD_CHUNK_SIZE = 64 * 1024


@dataclass(slots=True, frozen=True)
class AssetCacheDownloadResult:
    cache_path: str | None
    cache_status: str
    download_attempted: bool
    error: str | None = None
    bytes_written: int = 0
    content_type: str | None = None


def is_readable_image(path: str | Path | None) -> bool:
    if path is None:
        return False
    target = Path(path)
    try:
        with Image.open(target) as image:
            image.verify()
    except (FileNotFoundError, OSError, ValueError, SyntaxError):
        return False
    return True


def _cleanup_temp_file(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        return


def download_remote_asset(
    *,
    remote_url: str,
    cache_path: str | Path,
    timeout_seconds: int = ASSET_DOWNLOAD_TIMEOUT_SECONDS,
    max_bytes: int = ASSET_DOWNLOAD_MAX_BYTES,
) -> AssetCacheDownloadResult:
    target_path = Path(cache_path)
    normalized_target = str(target_path)
    if not str(remote_url or '').strip():
        return AssetCacheDownloadResult(
            cache_path=normalized_target,
            cache_status='failed',
            download_attempted=False,
            error='remote_url_missing',
        )
    if is_readable_image(target_path):
        return AssetCacheDownloadResult(
            cache_path=normalized_target,
            cache_status='cached',
            download_attempted=False,
        )

    temp_path = target_path.with_suffix(f'{target_path.suffix}.part')
    _cleanup_temp_file(temp_path)
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return AssetCacheDownloadResult(
            cache_path=normalized_target,
            cache_status='failed',
            download_attempted=False,
            error=f'cache_dir_error:{exc.__class__.__name__}',
        )

    request = urllib.request.Request(
        remote_url,
        headers={
            'Accept': 'image/*',
            'User-Agent': 'YOTOAssetCache/1.0',
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=int(timeout_seconds)) as response:
            headers = response.headers
            content_type = str(headers.get_content_type() or '').strip().lower()
            if not content_type.startswith('image/'):
                return AssetCacheDownloadResult(
                    cache_path=normalized_target,
                    cache_status='invalid_content_type',
                    download_attempted=True,
                    error=f'content_type:{content_type or "missing"}',
                    content_type=content_type or None,
                )

            content_length = headers.get('Content-Length')
            if content_length:
                try:
                    if int(content_length) > int(max_bytes):
                        return AssetCacheDownloadResult(
                            cache_path=normalized_target,
                            cache_status='too_large',
                            download_attempted=True,
                            error=f'content_length_exceeds_limit:{content_length}',
                            content_type=content_type or None,
                        )
                except (TypeError, ValueError):
                    pass

            bytes_written = 0
            with temp_path.open('wb') as handle:
                while True:
                    chunk = response.read(_DOWNLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    bytes_written += len(chunk)
                    if bytes_written > int(max_bytes):
                        _cleanup_temp_file(temp_path)
                        return AssetCacheDownloadResult(
                            cache_path=normalized_target,
                            cache_status='too_large',
                            download_attempted=True,
                            error='downloaded_bytes_exceed_limit',
                            bytes_written=bytes_written,
                            content_type=content_type or None,
                        )
                    handle.write(chunk)

        if not is_readable_image(temp_path):
            _cleanup_temp_file(temp_path)
            return AssetCacheDownloadResult(
                cache_path=normalized_target,
                cache_status='failed',
                download_attempted=True,
                error='downloaded_file_not_readable_image',
                bytes_written=bytes_written,
                content_type=content_type or None,
            )

        temp_path.replace(target_path)
        return AssetCacheDownloadResult(
            cache_path=normalized_target,
            cache_status='downloaded',
            download_attempted=True,
            bytes_written=bytes_written,
            content_type=content_type or None,
        )
    except urllib.error.HTTPError as exc:
        _cleanup_temp_file(temp_path)
        return AssetCacheDownloadResult(
            cache_path=normalized_target,
            cache_status='failed',
            download_attempted=True,
            error=f'http_error:{exc.code}',
        )
    except urllib.error.URLError as exc:
        _cleanup_temp_file(temp_path)
        reason = getattr(exc, 'reason', None)
        reason_text = reason.__class__.__name__ if reason is not None else exc.__class__.__name__
        return AssetCacheDownloadResult(
            cache_path=normalized_target,
            cache_status='failed',
            download_attempted=True,
            error=f'url_error:{reason_text}',
        )
    except socket.timeout:
        _cleanup_temp_file(temp_path)
        return AssetCacheDownloadResult(
            cache_path=normalized_target,
            cache_status='failed',
            download_attempted=True,
            error='socket_timeout',
        )
    except TimeoutError:
        _cleanup_temp_file(temp_path)
        return AssetCacheDownloadResult(
            cache_path=normalized_target,
            cache_status='failed',
            download_attempted=True,
            error='timeout',
        )
    except OSError as exc:
        _cleanup_temp_file(temp_path)
        return AssetCacheDownloadResult(
            cache_path=normalized_target,
            cache_status='failed',
            download_attempted=True,
            error=f'os_error:{exc.__class__.__name__}',
        )


__all__ = [
    'ASSET_DOWNLOAD_MAX_BYTES',
    'ASSET_DOWNLOAD_TIMEOUT_SECONDS',
    'AssetCacheDownloadResult',
    'download_remote_asset',
    'is_readable_image',
]
