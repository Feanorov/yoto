from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse


REPO_ROOT = Path(__file__).resolve().parents[3]
OFFLINE_VALIDATION_ROOT = REPO_ROOT / 'output' / 'offline_validation'


def resolve_existing_asset_path(value: str | None) -> Path | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None

    direct = Path(raw)
    if direct.exists() and direct.is_file():
        return direct
    rebased = _resolve_rebased_path(direct)
    if rebased is not None:
        return rebased

    parsed = urlparse(raw)
    if parsed.scheme != 'file':
        return None

    target = unquote(parsed.path or '')
    if target.startswith('/') and len(target) >= 3 and target[2] == ':':
        target = target[1:]
    file_path = Path(target)
    if file_path.exists() and file_path.is_file():
        return file_path
    return _resolve_rebased_path(file_path)


def _resolve_rebased_path(path: Path) -> Path | None:
    if not path.is_absolute():
        return None
    rebased = _rebase_under_repo_root(path)
    if rebased is not None:
        return rebased
    return _rebase_offline_validation_asset(path)


def _rebase_under_repo_root(path: Path) -> Path | None:
    lower_parts = [part.lower() for part in path.parts]
    for anchor in ('output', 'data'):
        if anchor not in lower_parts:
            continue
        index = lower_parts.index(anchor)
        candidate = REPO_ROOT.joinpath(*path.parts[index:])
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _rebase_offline_validation_asset(path: Path) -> Path | None:
    lower_parts = [part.lower() for part in path.parts]
    if 'offline_validation' not in lower_parts or 'assets' not in lower_parts:
        return None
    assets_index = lower_parts.index('assets')
    asset_parts = path.parts[assets_index:]
    candidate_roots: list[Path] = []
    if 'snapshots' in lower_parts:
        snapshots_index = lower_parts.index('snapshots')
        if snapshots_index + 1 < len(path.parts):
            candidate_roots.append(OFFLINE_VALIDATION_ROOT / 'snapshots' / path.parts[snapshots_index + 1])
    if 'review' in lower_parts:
        review_index = lower_parts.index('review')
        if review_index + 1 < len(path.parts):
            candidate_roots.append(OFFLINE_VALIDATION_ROOT / 'review' / path.parts[review_index + 1])
    candidate_roots.append(OFFLINE_VALIDATION_ROOT / 'golden' / 'current')
    for root in candidate_roots:
        candidate = root.joinpath(*asset_parts)
        if candidate.exists() and candidate.is_file():
            return candidate
    return None

