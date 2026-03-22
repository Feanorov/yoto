from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse


def resolve_existing_asset_path(value: str | None) -> Path | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None

    direct = Path(raw)
    if direct.exists() and direct.is_file():
        return direct

    parsed = urlparse(raw)
    if parsed.scheme != 'file':
        return None

    target = unquote(parsed.path or '')
    if target.startswith('/') and len(target) >= 3 and target[2] == ':':
        target = target[1:]
    file_path = Path(target)
    if file_path.exists() and file_path.is_file():
        return file_path
    return None

