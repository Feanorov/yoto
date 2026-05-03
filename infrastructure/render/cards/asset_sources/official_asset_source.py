from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from infrastructure.render.cards.asset_source import resolve_existing_asset_path
from infrastructure.render.cards.asset_sources.asset_cache import (
    ASSET_DOWNLOAD_MAX_BYTES,
    ASSET_DOWNLOAD_TIMEOUT_SECONDS,
    AssetCacheDownloadResult,
    download_remote_asset,
    is_readable_image,
)
from infrastructure.render.cards.visual_decision_engine import build_cover_decision


REPO_ROOT = Path(__file__).resolve().parents[4]
CACHE_ROOT = REPO_ROOT / 'output' / 'cards' / 'official_asset_cache'
DEFAULT_LOCAL_OFFICIAL_ASSET_MANIFEST_PATH = Path(__file__).with_name('official_asset_manifest.local.json')

SOURCE_PRIORITY_ORDER = (
    'steam_library_capsule',
    'steam_main_capsule',
    'steam_header_capsule',
    'steam_library_hero',
    'steam_screenshot',
    'epic_offer_image',
    'epic_library_landscape',
    'official_press_key_art',
    'official_trailer_frame',
    'ai_generated',
)
SOURCE_PRIORITY_MAP = {
    source_type: index
    for index, source_type in enumerate(SOURCE_PRIORITY_ORDER, start=1)
}

STEAM_TEMPLATE_SPECS: dict[str, dict[str, Any]] = {
    'steam_library_capsule': {
        'filename': 'library_600x900_2x.jpg',
        'kind': 'library_capsule',
        'width': 1200,
        'height': 1800,
    },
    'steam_main_capsule': {
        'filename': 'capsule_616x353.jpg',
        'kind': 'main_capsule',
        'width': 616,
        'height': 353,
    },
    'steam_header_capsule': {
        'filename': 'header.jpg',
        'kind': 'header_capsule',
        'width': 460,
        'height': 215,
    },
    'steam_library_hero': {
        'filename': 'library_hero.jpg',
        'kind': 'library_hero',
        'width': 3840,
        'height': 1240,
    },
    'steam_screenshot': {
        'filename': 'ss_template_01.jpg',
        'kind': 'screenshot',
        'width': 1920,
        'height': 1080,
    },
}
STEAM_CDN_TEMPLATE = 'https://shared.cloudflare.steamstatic.com/store_item_assets/steam/apps/{app_id}/{filename}'

EPIC_TEMPLATE_SPECS: dict[str, dict[str, Any]] = {
    'epic_offer_image': {
        'filename': 'offer-image.jpg',
        'kind': 'offer_image',
        'width': 1200,
        'height': 1600,
    },
    'epic_library_landscape': {
        'filename': 'library-landscape.jpg',
        'kind': 'library_landscape',
        'width': 2560,
        'height': 1440,
    },
}
EPIC_CDN_TEMPLATE = 'https://cdn1.epicgames.com/{epic_slug}/{filename}'
MAX_DOWNLOAD_CANDIDATES_PER_GAME = 3
_DOWNLOAD_FAILURE_STATUSES = {'failed', 'invalid_content_type', 'too_large'}


@dataclass(slots=True, frozen=True)
class AssetDownloadSummary:
    enabled: bool
    attempted: bool
    status: str
    error: str | None
    downloaded_count: int
    cached_count: int
    failed_count: int


def _safe_text(value: Any) -> str:
    return str(value or '').strip()


def _normalize_text(value: Any) -> str:
    return _safe_text(value).lower()


def _safe_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _is_http_url(value: str) -> bool:
    normalized = _normalize_text(value)
    return normalized.startswith('http://') or normalized.startswith('https://')


def _has_uri_scheme(value: str) -> bool:
    return bool(re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', value))


def _safe_identifier(value: str | None) -> str:
    normalized = _normalize_text(value)
    if not normalized:
        return 'unknown'
    collapsed = re.sub(r'[^a-z0-9]+', '_', normalized).strip('_')
    return collapsed or 'unknown'


def _normalize_local_path(value: Any) -> str | None:
    raw = _safe_text(value)
    if not raw:
        return None
    if raw.startswith('${REPO_ROOT}/'):
        candidate = REPO_ROOT / Path(raw.removeprefix('${REPO_ROOT}/'))
    elif _has_uri_scheme(raw) and not raw.startswith('file://'):
        return None
    else:
        direct = resolve_existing_asset_path(raw)
        if direct is not None:
            return str(direct.resolve())
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = REPO_ROOT / candidate
    try:
        return str(candidate.resolve()) if candidate.exists() else str(candidate)
    except OSError:
        return str(candidate)


def _evaluate_local_cache(value: str | None) -> tuple[str | None, str]:
    if not value:
        return None, 'not_requested'
    normalized = _normalize_local_path(value)
    if normalized is None:
        return None, 'not_requested'
    path = Path(normalized)
    if not path.exists() or not path.is_file():
        return normalized, 'missing'
    return normalized, ('cached' if is_readable_image(path) else 'error')


def _cache_extension(remote_url: str, fallback: str = '.jpg') -> str:
    name = Path(remote_url).name
    suffix = Path(name).suffix
    return suffix or fallback


def _deterministic_cache_path(
    *,
    namespace: str,
    identifier: str,
    source_type: str,
    remote_url: str,
    index: int,
) -> str:
    extension = _cache_extension(remote_url)
    filename = f'{source_type}_{index + 1}{extension}'
    return str((CACHE_ROOT / namespace / _safe_identifier(identifier) / filename).resolve())


def _candidate_metadata(payload: Mapping[str, Any]) -> dict[str, Any]:
    metadata = payload.get('metadata')
    return dict(metadata) if isinstance(metadata, Mapping) else {}


def _candidate_remote_url(payload: Mapping[str, Any]) -> str | None:
    metadata = _candidate_metadata(payload)
    value = _safe_text(payload.get('remote_url') or metadata.get('remote_url'))
    return value or None


def _candidate_cache_path(payload: Mapping[str, Any]) -> str | None:
    metadata = _candidate_metadata(payload)
    value = _safe_text(payload.get('cache_path') or metadata.get('cache_path'))
    return value or None


def _candidate_cache_status(payload: Mapping[str, Any]) -> str:
    metadata = _candidate_metadata(payload)
    return _normalize_text(payload.get('cache_status') or metadata.get('cache_status')) or 'not_requested'


def _candidate_priority(payload: Mapping[str, Any]) -> int:
    source_type = _normalize_text(payload.get('source_type')) or 'unknown'
    explicit = payload.get('priority')
    try:
        return int(explicit or SOURCE_PRIORITY_MAP.get(source_type, len(SOURCE_PRIORITY_MAP) + 1))
    except (TypeError, ValueError):
        return int(SOURCE_PRIORITY_MAP.get(source_type, len(SOURCE_PRIORITY_MAP) + 1))


def _candidate_identity(payload: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        _normalize_text(payload.get('source_type')),
        _safe_text(_candidate_remote_url(payload)),
        _safe_text(_candidate_cache_path(payload)),
        _safe_text(payload.get('path_or_url')),
    )


def _normalize_candidate_payloads(values: Any, *, source_type: str | None = None) -> list[dict[str, Any]]:
    if isinstance(values, Mapping):
        payload = dict(values)
        if source_type and not payload.get('source_type'):
            payload['source_type'] = source_type
        return [payload]
    if isinstance(values, Sequence) and not isinstance(values, (str, bytes, bytearray)):
        normalized: list[dict[str, Any]] = []
        for item in values:
            if isinstance(item, Mapping):
                payload = dict(item)
                if source_type and not payload.get('source_type'):
                    payload['source_type'] = source_type
                normalized.append(payload)
            elif isinstance(item, str):
                normalized.append(
                    {
                        'source_type': source_type,
                        'path_or_url': item,
                    }
                )
        return normalized
    if isinstance(values, str):
        return [
            {
                'source_type': source_type,
                'path_or_url': values,
            }
        ]
    return []


def _normalize_local_assets(local_assets: Any) -> dict[str, list[dict[str, Any]]]:
    normalized: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if isinstance(local_assets, Mapping):
        for key, value in local_assets.items():
            source_type = _normalize_text(key)
            if not source_type:
                continue
            normalized[source_type].extend(_normalize_candidate_payloads(value, source_type=source_type))
        return dict(normalized)
    for payload in _normalize_candidate_payloads(local_assets):
        source_type = _normalize_text(payload.get('source_type'))
        if source_type:
            normalized[source_type].append(payload)
    return dict(normalized)


def _normalize_asset_urls(asset_urls: Any) -> dict[str, list[dict[str, Any]]]:
    normalized: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if isinstance(asset_urls, Mapping):
        for key, value in asset_urls.items():
            source_type = _normalize_text(key)
            if not source_type:
                continue
            payloads = _normalize_candidate_payloads(value, source_type=source_type)
            for payload in payloads:
                remote_url = _safe_text(payload.get('remote_url') or payload.get('path_or_url'))
                normalized[source_type].append(
                    {
                        **payload,
                        'source_type': source_type,
                        'remote_url': remote_url,
                    }
                )
        return dict(normalized)
    for payload in _normalize_candidate_payloads(asset_urls):
        source_type = _normalize_text(payload.get('source_type'))
        if not source_type:
            continue
        remote_url = _safe_text(payload.get('remote_url') or payload.get('path_or_url'))
        normalized[source_type].append(
            {
                **payload,
                'source_type': source_type,
                'remote_url': remote_url,
            }
        )
    return dict(normalized)


def _load_manifest(manifest_path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    if not manifest_path.exists():
        return None, ['local_manifest_missing']
    try:
        payload = json.loads(manifest_path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        return None, [f'local_manifest_read_error:{exc.__class__.__name__}']
    if not isinstance(payload, Mapping):
        return None, ['local_manifest_invalid']
    return {str(key): value for key, value in payload.items()}, []


def _manifest_entries(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return []
    entries = payload.get('entries')
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes, bytearray)):
        return []
    return [dict(item) for item in entries if isinstance(item, Mapping)]


def _match_score(
    entry: Mapping[str, Any],
    *,
    game_title: str,
    store_id: str | None,
    slug: str | None,
    source_hint: str | None,
) -> int:
    score = 0
    if slug and _normalize_text(entry.get('slug')) == _normalize_text(slug):
        score += 8
    if store_id and _normalize_text(entry.get('store_id')) == _normalize_text(store_id):
        score += 6
    if game_title and _normalize_text(entry.get('game_title')) == _normalize_text(game_title):
        score += 4
    if source_hint and _normalize_text(entry.get('source_hint')) == _normalize_text(source_hint):
        score += 2
    return score


def _select_manifest_entry(
    entries: Sequence[Mapping[str, Any]],
    *,
    game_title: str,
    store_id: str | None,
    slug: str | None,
    source_hint: str | None,
) -> dict[str, Any] | None:
    best_entry: dict[str, Any] | None = None
    best_score = 0
    for entry in entries:
        score = _match_score(
            entry,
            game_title=game_title,
            store_id=store_id,
            slug=slug,
            source_hint=source_hint,
        )
        if score > best_score:
            best_entry = dict(entry)
            best_score = score
    if best_score < 4:
        return None
    return best_entry


def _resolve_candidate_contract(
    *,
    source_type: str,
    explicit_path_or_url: str,
    explicit_remote_url: str,
    explicit_cache_path: str,
    cache_namespace: str,
    cache_identifier: str,
    index: int,
) -> tuple[str, str | None, str | None, str]:
    remote_url = explicit_remote_url if _is_http_url(explicit_remote_url) else ''
    path_or_url = explicit_path_or_url
    if not remote_url and _is_http_url(path_or_url):
        remote_url = path_or_url
    local_candidate = _normalize_local_path(explicit_cache_path or path_or_url)
    if local_candidate is not None:
        cache_path, cache_status = _evaluate_local_cache(local_candidate)
        if cache_status == 'cached':
            return cache_path or local_candidate, remote_url or None, cache_path, cache_status
        return path_or_url or local_candidate, remote_url or None, cache_path, cache_status

    if remote_url:
        deterministic_cache_path = _normalize_local_path(
            explicit_cache_path or _deterministic_cache_path(
                namespace=cache_namespace,
                identifier=cache_identifier,
                source_type=source_type,
                remote_url=remote_url,
                index=index,
            )
        )
        cache_path, cache_status = _evaluate_local_cache(deterministic_cache_path)
        if cache_status == 'cached':
            return cache_path or remote_url, remote_url, cache_path, cache_status
        return remote_url, remote_url, cache_path, 'not_requested'

    if path_or_url:
        return path_or_url, None, None, 'missing'
    return '', None, None, 'missing'


def _build_candidate(
    *,
    source_type: str,
    kind: str,
    width: int | None,
    height: int | None,
    priority: int,
    source_origin: str,
    license_hint: str,
    manifest_entry_id: str | None,
    cache_namespace: str,
    cache_identifier: str,
    index: int,
    base_metadata: Mapping[str, Any] | None = None,
    local_payload: Mapping[str, Any] | None = None,
    remote_payload: Mapping[str, Any] | None = None,
    remote_url: str | None = None,
) -> dict[str, Any]:
    merged_metadata = {
        str(key): _json_ready(value)
        for key, value in (base_metadata or {}).items()
    }
    if isinstance(remote_payload, Mapping) and isinstance(remote_payload.get('metadata'), Mapping):
        merged_metadata.update({str(key): _json_ready(value) for key, value in remote_payload['metadata'].items()})
    if isinstance(local_payload, Mapping) and isinstance(local_payload.get('metadata'), Mapping):
        merged_metadata.update({str(key): _json_ready(value) for key, value in local_payload['metadata'].items()})
    if manifest_entry_id:
        merged_metadata.setdefault('manifest_entry_id', manifest_entry_id)

    local_path_or_url = _safe_text(None if local_payload is None else local_payload.get('path_or_url'))
    remote_path_or_url = _safe_text(None if remote_payload is None else remote_payload.get('path_or_url'))
    explicit_path_or_url = local_path_or_url or remote_path_or_url
    explicit_remote_url = (
        _safe_text(None if remote_payload is None else remote_payload.get('remote_url'))
        or _safe_text(remote_url)
    )
    explicit_cache_path = _safe_text(
        (None if local_payload is None else local_payload.get('cache_path'))
        or (None if remote_payload is None else remote_payload.get('cache_path'))
    )

    resolved_path_or_url, resolved_remote_url, resolved_cache_path, cache_status = _resolve_candidate_contract(
        source_type=source_type,
        explicit_path_or_url=explicit_path_or_url,
        explicit_remote_url=explicit_remote_url,
        explicit_cache_path=explicit_cache_path,
        cache_namespace=cache_namespace,
        cache_identifier=cache_identifier,
        index=index,
    )

    resolved_kind = (
        _normalize_text(None if local_payload is None else local_payload.get('kind'))
        or _normalize_text(None if remote_payload is None else remote_payload.get('kind'))
        or _normalize_text(kind)
        or 'unknown'
    )
    resolved_width = (
        _safe_int(None if local_payload is None else local_payload.get('width'))
        or _safe_int(None if remote_payload is None else remote_payload.get('width'))
        or width
    )
    resolved_height = (
        _safe_int(None if local_payload is None else local_payload.get('height'))
        or _safe_int(None if remote_payload is None else remote_payload.get('height'))
        or height
    )
    merged_metadata['remote_url'] = resolved_remote_url
    merged_metadata['cache_path'] = resolved_cache_path
    merged_metadata['cache_status'] = cache_status

    return {
        'source_type': source_type,
        'path_or_url': resolved_path_or_url,
        'remote_url': resolved_remote_url,
        'cache_path': resolved_cache_path,
        'cache_status': cache_status,
        'width': resolved_width,
        'height': resolved_height,
        'kind': resolved_kind,
        'priority': int(
            (None if local_payload is None else local_payload.get('priority'))
            or (None if remote_payload is None else remote_payload.get('priority'))
            or priority
        ),
        'source_origin': (
            _safe_text(None if local_payload is None else local_payload.get('source_origin'))
            or _safe_text(None if remote_payload is None else remote_payload.get('source_origin'))
            or source_origin
        ),
        'license_hint': (
            _safe_text(None if local_payload is None else local_payload.get('license_hint'))
            or _safe_text(None if remote_payload is None else remote_payload.get('license_hint'))
            or license_hint
        ),
        'metadata': merged_metadata,
    }


def _normalized_explicit_candidates(
    payloads: Sequence[Mapping[str, Any]] | None,
    *,
    source_origin: str,
    license_hint: str,
    manifest_entry_id: str | None,
    cache_namespace: str,
    cache_identifier: str,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, payload in enumerate(payloads or []):
        if not isinstance(payload, Mapping):
            continue
        source_type = _normalize_text(payload.get('source_type')) or 'unknown'
        metadata = dict(payload.get('metadata')) if isinstance(payload.get('metadata'), Mapping) else {}
        normalized.append(
            _build_candidate(
                source_type=source_type,
                kind=_normalize_text(payload.get('kind')) or 'unknown',
                width=_safe_int(payload.get('width')),
                height=_safe_int(payload.get('height')),
                priority=int(payload.get('priority') or SOURCE_PRIORITY_MAP.get(source_type, len(SOURCE_PRIORITY_MAP) + 1)),
                source_origin=_safe_text(payload.get('source_origin')) or source_origin,
                license_hint=_safe_text(payload.get('license_hint')) or license_hint,
                manifest_entry_id=manifest_entry_id,
                cache_namespace=cache_namespace,
                cache_identifier=cache_identifier,
                index=index,
                base_metadata=metadata,
                local_payload=payload,
                remote_payload=payload,
                remote_url=_safe_text(payload.get('remote_url')),
            )
        )
    return normalized


def _expand_steam_candidates(
    *,
    steam_app_id: str,
    local_assets: Mapping[str, list[dict[str, Any]]],
    asset_urls: Mapping[str, list[dict[str, Any]]],
    manifest_entry_id: str | None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for source_type, spec in STEAM_TEMPLATE_SPECS.items():
        local_payloads = list(local_assets.get(source_type, []))
        remote_payloads = list(asset_urls.get(source_type, []))
        iterations = max(len(local_payloads), len(remote_payloads), 1)
        for index in range(iterations):
            remote_payload = remote_payloads[index] if index < len(remote_payloads) else None
            local_payload = local_payloads[index] if index < len(local_payloads) else None
            template_url = STEAM_CDN_TEMPLATE.format(app_id=steam_app_id, filename=spec['filename'])
            metadata = {
                'steam_app_id': steam_app_id,
                'template_filename': spec['filename'],
                'template_index': index + 1,
            }
            if source_type == 'steam_screenshot' and remote_payload is None:
                metadata['template_only'] = True
            candidates.append(
                _build_candidate(
                    source_type=source_type,
                    kind=spec['kind'],
                    width=int(spec['width']),
                    height=int(spec['height']),
                    priority=SOURCE_PRIORITY_MAP[source_type],
                    source_origin='steam_cdn_manifest',
                    license_hint='steam_store_cdn_template',
                    manifest_entry_id=manifest_entry_id,
                    cache_namespace='steam',
                    cache_identifier=steam_app_id,
                    index=index,
                    base_metadata=metadata,
                    local_payload=local_payload,
                    remote_payload=remote_payload,
                    remote_url=template_url,
                )
            )
    return candidates


def _expand_epic_candidates(
    *,
    epic_slug: str,
    local_assets: Mapping[str, list[dict[str, Any]]],
    asset_urls: Mapping[str, list[dict[str, Any]]],
    manifest_entry_id: str | None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for source_type, spec in EPIC_TEMPLATE_SPECS.items():
        local_payloads = list(local_assets.get(source_type, []))
        remote_payloads = list(asset_urls.get(source_type, []))
        iterations = max(len(local_payloads), len(remote_payloads), 1)
        for index in range(iterations):
            remote_payload = remote_payloads[index] if index < len(remote_payloads) else None
            local_payload = local_payloads[index] if index < len(local_payloads) else None
            template_url = EPIC_CDN_TEMPLATE.format(epic_slug=epic_slug, filename=spec['filename'])
            candidates.append(
                _build_candidate(
                    source_type=source_type,
                    kind=spec['kind'],
                    width=int(spec['width']),
                    height=int(spec['height']),
                    priority=SOURCE_PRIORITY_MAP[source_type],
                    source_origin='epic_manifest',
                    license_hint='epic_manifest_template',
                    manifest_entry_id=manifest_entry_id,
                    cache_namespace='epic',
                    cache_identifier=epic_slug,
                    index=index,
                    base_metadata={
                        'epic_slug': epic_slug,
                        'template_filename': spec['filename'],
                        'template_index': index + 1,
                    },
                    local_payload=local_payload,
                    remote_payload=remote_payload,
                    remote_url=template_url,
                )
            )
    return candidates


def _dedupe_candidates(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for payload in candidates:
        if not isinstance(payload, Mapping):
            continue
        key = (
            _normalize_text(payload.get('source_type')),
            _safe_text(payload.get('path_or_url')),
            _safe_text(payload.get('remote_url')),
            _safe_text(payload.get('cache_path')),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append({str(key): _json_ready(value) for key, value in payload.items()})
    deduped.sort(
        key=lambda item: (
            int(item.get('priority') or len(SOURCE_PRIORITY_MAP) + 1),
            str(item.get('source_type') or ''),
            str(item.get('path_or_url') or ''),
            str(item.get('remote_url') or ''),
        )
    )
    return deduped


def _resolve_source_mode(*, has_steam: bool, has_epic: bool) -> str:
    if has_steam and has_epic:
        return 'mixed_manifest'
    if has_steam:
        return 'steam_cdn_manifest'
    if has_epic:
        return 'epic_manifest'
    return 'local_manifest'


def _resolve_asset_ingestion_mode(candidates: Sequence[Mapping[str, Any]]) -> str:
    if not candidates:
        return 'empty'
    statuses = [str(item.get('cache_status') or '') for item in candidates]
    has_cached = any(status in {'cached', 'downloaded'} for status in statuses)
    has_remote = any(_safe_text(item.get('remote_url')) for item in candidates)
    has_local_error = any(status in {'missing', 'error', 'failed', 'invalid_content_type', 'too_large'} for status in statuses)
    if has_remote and has_cached:
        return 'mixed_local_remote'
    if has_remote:
        return 'remote_templates_only'
    if has_local_error:
        return 'local_with_errors'
    return 'local_only'


def _extend_extra_manifest_candidates(
    *,
    candidates: list[dict[str, Any]],
    local_assets_by_source: Mapping[str, list[dict[str, Any]]],
    asset_urls_by_source: Mapping[str, list[dict[str, Any]]],
    handled_source_types: set[str],
    manifest_entry_id: str | None,
    cache_identifier: str,
    license_hint: str,
) -> None:
    for source_type, payloads in local_assets_by_source.items():
        if source_type in handled_source_types:
            continue
        candidates.extend(
            _normalized_explicit_candidates(
                payloads,
                source_origin='local_manifest',
                license_hint=license_hint,
                manifest_entry_id=manifest_entry_id,
                cache_namespace='local_manifest',
                cache_identifier=cache_identifier,
            )
        )
    for source_type, payloads in asset_urls_by_source.items():
        if source_type in handled_source_types:
            continue
        candidates.extend(
            _normalized_explicit_candidates(
                payloads,
                source_origin='local_manifest',
                license_hint=license_hint,
                manifest_entry_id=manifest_entry_id,
                cache_namespace='local_manifest',
                cache_identifier=cache_identifier,
            )
        )


def _decision_ranking_payload(
    *,
    candidates: Sequence[Mapping[str, Any]],
    game_title: str,
    metadata: Mapping[str, Any],
) -> tuple[dict[tuple[str, str, str, str], dict[str, Any]], tuple[str, str, str, str] | None]:
    try:
        decision = build_cover_decision(
            game_title=game_title,
            genre=_safe_text(metadata.get('genre')) or None,
            tags=[
                str(item)
                for item in metadata.get('tags') or []
                if str(item).strip()
            ],
            short_description=_safe_text(metadata.get('short_description')) or None,
            offer_type=_safe_text(metadata.get('offer_type')) or None,
            asset_candidates=candidates,
        )
    except Exception:
        return {}, None

    ranking: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for payload in decision.asset_scores:
        if not isinstance(payload, Mapping):
            continue
        ranking[_candidate_identity(payload)] = {
            'accepted': bool(payload.get('accepted', False)),
            'total_score': float(payload.get('total_score') or 0.0),
        }
    selected_key = (
        _candidate_identity(decision.selected_asset)
        if isinstance(decision.selected_asset, Mapping)
        else None
    )
    return ranking, selected_key


def _select_download_candidate_indexes(
    *,
    candidates: Sequence[Mapping[str, Any]],
    game_title: str,
    metadata: Mapping[str, Any],
    max_download_candidates: int,
) -> list[int]:
    if int(max_download_candidates) < 1:
        return []

    ranking, selected_key = _decision_ranking_payload(
        candidates=candidates,
        game_title=game_title,
        metadata=metadata,
    )
    remote_indexes = [
        index
        for index, payload in enumerate(candidates)
        if _candidate_remote_url(payload)
        and _candidate_cache_path(payload)
        and _candidate_cache_status(payload) not in {'cached', 'downloaded'}
    ]
    if not remote_indexes:
        return []

    chosen: list[int] = []
    if selected_key is not None:
        for index in remote_indexes:
            if _candidate_identity(candidates[index]) == selected_key:
                chosen.append(index)
                break

    accepted_indexes = sorted(
        [
            index
            for index in remote_indexes
            if ranking.get(_candidate_identity(candidates[index]), {}).get('accepted', False)
        ],
        key=lambda index: (
            -float(ranking.get(_candidate_identity(candidates[index]), {}).get('total_score') or 0.0),
            _candidate_priority(candidates[index]),
            index,
        ),
    )
    for index in accepted_indexes:
        if index not in chosen:
            chosen.append(index)
        if len(chosen) >= int(max_download_candidates):
            return chosen[: int(max_download_candidates)]

    ranked_indexes = sorted(
        remote_indexes,
        key=lambda index: (
            _candidate_priority(candidates[index]),
            -float(ranking.get(_candidate_identity(candidates[index]), {}).get('total_score') or 0.0),
            index,
        ),
    )
    for index in ranked_indexes:
        if index not in chosen:
            chosen.append(index)
        if len(chosen) >= int(max_download_candidates):
            break
    return chosen[: int(max_download_candidates)]


def _apply_download_result_to_candidate(
    payload: Mapping[str, Any],
    *,
    result: AssetCacheDownloadResult,
) -> dict[str, Any]:
    updated = {str(key): _json_ready(value) for key, value in payload.items()}
    metadata = _candidate_metadata(updated)
    remote_url = _candidate_remote_url(updated)
    cache_path = result.cache_path or _candidate_cache_path(updated)

    updated['remote_url'] = remote_url
    updated['cache_path'] = cache_path
    updated['cache_status'] = result.cache_status
    updated['asset_download_attempted'] = bool(result.download_attempted)
    updated['asset_download_error'] = result.error
    if result.cache_status in {'cached', 'downloaded'} and cache_path:
        updated['path_or_url'] = cache_path
    elif cache_path:
        updated['path_or_url'] = cache_path

    metadata['remote_url'] = remote_url
    metadata['cache_path'] = cache_path
    metadata['cache_status'] = result.cache_status
    metadata['asset_download_attempted'] = bool(result.download_attempted)
    if result.error:
        metadata['asset_download_error'] = result.error
    else:
        metadata.pop('asset_download_error', None)
    updated['metadata'] = metadata
    return updated


def _download_summary_for_candidates(
    *,
    candidates: Sequence[Mapping[str, Any]],
    game_title: str,
    metadata: Mapping[str, Any],
    download_assets: bool,
    max_download_candidates: int,
    asset_downloader: Callable[..., AssetCacheDownloadResult] | None,
) -> tuple[list[dict[str, Any]], AssetDownloadSummary, list[str]]:
    normalized_candidates = [
        {str(key): _json_ready(value) for key, value in payload.items()}
        for payload in candidates
        if isinstance(payload, Mapping)
    ]
    if not download_assets:
        return normalized_candidates, AssetDownloadSummary(
            enabled=False,
            attempted=False,
            status='disabled',
            error=None,
            downloaded_count=0,
            cached_count=0,
            failed_count=0,
        ), []

    selected_indexes = _select_download_candidate_indexes(
        candidates=normalized_candidates,
        game_title=game_title,
        metadata=metadata,
        max_download_candidates=max_download_candidates,
    )
    if not selected_indexes:
        return normalized_candidates, AssetDownloadSummary(
            enabled=True,
            attempted=False,
            status='not_needed',
            error=None,
            downloaded_count=0,
            cached_count=0,
            failed_count=0,
        ), []

    downloader = asset_downloader or download_remote_asset
    errors: list[str] = []
    error_messages: list[str] = []
    downloaded_count = 0
    cached_count = 0
    failed_count = 0

    for index in selected_indexes:
        payload = normalized_candidates[index]
        remote_url = _candidate_remote_url(payload)
        cache_path = _candidate_cache_path(payload)
        if remote_url is None or cache_path is None:
            continue
        try:
            result = downloader(
                remote_url=remote_url,
                cache_path=cache_path,
                timeout_seconds=ASSET_DOWNLOAD_TIMEOUT_SECONDS,
                max_bytes=ASSET_DOWNLOAD_MAX_BYTES,
            )
        except Exception as exc:
            result = AssetCacheDownloadResult(
                cache_path=cache_path,
                cache_status='failed',
                download_attempted=True,
                error=f'downloader_exception:{exc.__class__.__name__}',
            )

        normalized_candidates[index] = _apply_download_result_to_candidate(
            payload,
            result=result,
        )
        if result.cache_status == 'downloaded':
            downloaded_count += 1
        elif result.cache_status == 'cached':
            cached_count += 1
        elif result.cache_status in _DOWNLOAD_FAILURE_STATUSES:
            failed_count += 1
            source_type = _normalize_text(payload.get('source_type')) or 'unknown'
            errors.append(f'asset_download_failed:{source_type}:{result.cache_status}')
            if result.error:
                error_messages.append(f'{source_type}:{result.error}')

    if failed_count and not downloaded_count and not cached_count:
        status = 'failed'
    elif failed_count:
        status = 'partial_failure'
    elif downloaded_count:
        status = 'downloaded'
    elif cached_count:
        status = 'cached'
    else:
        status = 'not_needed'

    return normalized_candidates, AssetDownloadSummary(
        enabled=True,
        attempted=bool(selected_indexes),
        status=status,
        error=';'.join(sorted(dict.fromkeys(error_messages))) or None,
        downloaded_count=downloaded_count,
        cached_count=cached_count,
        failed_count=failed_count,
    ), errors


@dataclass(slots=True, frozen=True)
class OfficialAssetSourceResult:
    asset_candidates: list[dict[str, Any]]
    asset_source_mode: str
    asset_ingestion_mode: str
    asset_source_errors: list[str]
    manifest_path: str | None
    manifest_entry_id: str | None
    used_fixture_fallback: bool
    asset_download_enabled: bool = False
    asset_download_attempted: bool = False
    asset_download_status: str = 'disabled'
    asset_download_error: str | None = None
    downloaded_asset_count: int = 0
    cached_asset_count: int = 0
    failed_asset_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            'asset_candidates': _json_ready(self.asset_candidates),
            'asset_source_mode': self.asset_source_mode,
            'asset_ingestion_mode': self.asset_ingestion_mode,
            'asset_source_errors': list(self.asset_source_errors),
            'manifest_path': self.manifest_path,
            'manifest_entry_id': self.manifest_entry_id,
            'used_fixture_fallback': self.used_fixture_fallback,
            'asset_download_enabled': self.asset_download_enabled,
            'asset_download_attempted': self.asset_download_attempted,
            'asset_download_status': self.asset_download_status,
            'asset_download_error': self.asset_download_error,
            'downloaded_asset_count': int(self.downloaded_asset_count),
            'cached_asset_count': int(self.cached_asset_count),
            'failed_asset_count': int(self.failed_asset_count),
        }


def resolve_official_asset_candidates(
    *,
    game_title: str,
    steam_app_id: str | None = None,
    epic_slug: str | None = None,
    asset_urls: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
    local_assets: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
    store_id: str | None = None,
    slug: str | None = None,
    source_hint: str | None = None,
    existing_metadata: Mapping[str, Any] | None = None,
    fallback_asset_candidates: Sequence[Mapping[str, Any]] | None = None,
    manifest_path: str | Path | None = None,
    download_assets: bool = False,
    max_download_candidates: int = MAX_DOWNLOAD_CANDIDATES_PER_GAME,
    asset_downloader: Callable[..., AssetCacheDownloadResult] | None = None,
) -> OfficialAssetSourceResult:
    metadata = dict(existing_metadata) if isinstance(existing_metadata, Mapping) else {}
    resolved_game_title = _safe_text(game_title) or _safe_text(metadata.get('game_title'))
    resolved_store_id = _safe_text(store_id) or _safe_text(metadata.get('store_id')) or None
    resolved_slug = _safe_text(slug) or _safe_text(metadata.get('slug')) or None
    resolved_source_hint = _safe_text(source_hint) or _safe_text(metadata.get('source_hint')) or None

    resolved_manifest_path = (
        Path(manifest_path)
        if manifest_path is not None
        else DEFAULT_LOCAL_OFFICIAL_ASSET_MANIFEST_PATH
    )
    manifest_payload, manifest_errors = _load_manifest(resolved_manifest_path)
    entries = _manifest_entries(manifest_payload)
    matched_entry = _select_manifest_entry(
        entries,
        game_title=resolved_game_title,
        store_id=resolved_store_id,
        slug=resolved_slug,
        source_hint=resolved_source_hint,
    )

    source_payload = dict(matched_entry) if isinstance(matched_entry, Mapping) else {}
    manifest_entry_id = (
        _safe_text(source_payload.get('slug'))
        or _safe_text(source_payload.get('game_title'))
        or resolved_slug
        or resolved_game_title
        or None
    )

    resolved_steam_app_id = (
        _safe_text(steam_app_id)
        or _safe_text(source_payload.get('steam_app_id'))
        or _safe_text(metadata.get('steam_app_id'))
        or None
    )
    resolved_epic_slug = (
        _safe_text(epic_slug)
        or _safe_text(source_payload.get('epic_slug'))
        or _safe_text(metadata.get('epic_slug'))
        or None
    )
    resolved_local_assets = (
        local_assets
        if local_assets is not None
        else source_payload.get('local_assets') if source_payload else metadata.get('local_assets')
    )
    resolved_asset_urls = (
        asset_urls
        if asset_urls is not None
        else source_payload.get('asset_urls') if source_payload else metadata.get('asset_urls')
    )

    explicit_manifest_candidates = (
        source_payload.get('asset_candidates')
        if isinstance(source_payload.get('asset_candidates'), Sequence)
        else None
    )

    local_assets_by_source = _normalize_local_assets(resolved_local_assets)
    asset_urls_by_source = _normalize_asset_urls(resolved_asset_urls)

    generated_candidates: list[dict[str, Any]] = []
    has_steam = bool(resolved_steam_app_id)
    has_epic = bool(resolved_epic_slug)
    handled_source_types: set[str] = set()

    if has_steam:
        handled_source_types.update(STEAM_TEMPLATE_SPECS)
        generated_candidates.extend(
            _expand_steam_candidates(
                steam_app_id=resolved_steam_app_id,
                local_assets=local_assets_by_source,
                asset_urls=asset_urls_by_source,
                manifest_entry_id=manifest_entry_id,
            )
        )
    if has_epic:
        handled_source_types.update(EPIC_TEMPLATE_SPECS)
        generated_candidates.extend(
            _expand_epic_candidates(
                epic_slug=resolved_epic_slug,
                local_assets=local_assets_by_source,
                asset_urls=asset_urls_by_source,
                manifest_entry_id=manifest_entry_id,
            )
        )

    if has_steam or has_epic:
        _extend_extra_manifest_candidates(
            candidates=generated_candidates,
            local_assets_by_source=local_assets_by_source,
            asset_urls_by_source=asset_urls_by_source,
            handled_source_types=handled_source_types,
            manifest_entry_id=manifest_entry_id,
            cache_identifier=manifest_entry_id or resolved_game_title or 'unknown',
            license_hint=_safe_text(source_payload.get('license_hint')) or 'local_manifest_fixture',
        )

    if not has_steam and not has_epic and explicit_manifest_candidates:
        generated_candidates.extend(
            _normalized_explicit_candidates(
                explicit_manifest_candidates,
                source_origin='local_manifest',
                license_hint=_safe_text(source_payload.get('license_hint')) or 'local_manifest_fixture',
                manifest_entry_id=manifest_entry_id,
                cache_namespace='local_manifest',
                cache_identifier=manifest_entry_id or resolved_game_title or 'unknown',
            )
        )
    elif not has_steam and not has_epic and local_assets_by_source:
        for source_type, payloads in local_assets_by_source.items():
            generated_candidates.extend(
                _normalized_explicit_candidates(
                    payloads,
                    source_origin='local_manifest',
                    license_hint=_safe_text(source_payload.get('license_hint')) or 'local_manifest_fixture',
                    manifest_entry_id=manifest_entry_id,
                    cache_namespace='local_manifest',
                    cache_identifier=manifest_entry_id or resolved_game_title or 'unknown',
                )
            )

    generated_candidates = _dedupe_candidates(generated_candidates)
    if generated_candidates:
        generated_candidates, download_summary, download_errors = _download_summary_for_candidates(
            candidates=generated_candidates,
            game_title=resolved_game_title,
            metadata=metadata,
            download_assets=download_assets,
            max_download_candidates=max_download_candidates,
            asset_downloader=asset_downloader,
        )
        return OfficialAssetSourceResult(
            asset_candidates=generated_candidates,
            asset_source_mode=_resolve_source_mode(has_steam=has_steam, has_epic=has_epic),
            asset_ingestion_mode=_resolve_asset_ingestion_mode(generated_candidates),
            asset_source_errors=list(download_errors),
            manifest_path=str(resolved_manifest_path),
            manifest_entry_id=manifest_entry_id if matched_entry is not None else None,
            used_fixture_fallback=False,
            asset_download_enabled=download_summary.enabled,
            asset_download_attempted=download_summary.attempted,
            asset_download_status=download_summary.status,
            asset_download_error=download_summary.error,
            downloaded_asset_count=download_summary.downloaded_count,
            cached_asset_count=download_summary.cached_count,
            failed_asset_count=download_summary.failed_count,
        )

    errors = list(manifest_errors)
    if matched_entry is None and (manifest_payload is not None):
        errors.append('manifest_entry_not_found')

    fallback_candidates = _normalized_explicit_candidates(
        fallback_asset_candidates,
        source_origin='fixture_fallback',
        license_hint='smoke_fixture',
        manifest_entry_id=resolved_slug or resolved_game_title or None,
        cache_namespace='fixture_fallback',
        cache_identifier=resolved_slug or resolved_game_title or 'unknown',
    )
    if fallback_candidates:
        fallback_candidates, download_summary, download_errors = _download_summary_for_candidates(
            candidates=fallback_candidates,
            game_title=resolved_game_title,
            metadata=metadata,
            download_assets=download_assets,
            max_download_candidates=max_download_candidates,
            asset_downloader=asset_downloader,
        )
        return OfficialAssetSourceResult(
            asset_candidates=fallback_candidates,
            asset_source_mode='fixture_fallback',
            asset_ingestion_mode=_resolve_asset_ingestion_mode(fallback_candidates),
            asset_source_errors=errors + list(download_errors),
            manifest_path=str(resolved_manifest_path),
            manifest_entry_id=None,
            used_fixture_fallback=True,
            asset_download_enabled=download_summary.enabled,
            asset_download_attempted=download_summary.attempted,
            asset_download_status=download_summary.status,
            asset_download_error=download_summary.error,
            downloaded_asset_count=download_summary.downloaded_count,
            cached_asset_count=download_summary.cached_count,
            failed_asset_count=download_summary.failed_count,
        )

    return OfficialAssetSourceResult(
        asset_candidates=[],
        asset_source_mode='empty',
        asset_ingestion_mode='empty',
        asset_source_errors=errors + ['asset_candidates_unavailable'],
        manifest_path=str(resolved_manifest_path),
        manifest_entry_id=None,
        used_fixture_fallback=False,
        asset_download_enabled=bool(download_assets),
        asset_download_attempted=False,
        asset_download_status='disabled' if not download_assets else 'not_needed',
        asset_download_error=None,
        downloaded_asset_count=0,
        cached_asset_count=0,
        failed_asset_count=0,
    )


__all__ = [
    'DEFAULT_LOCAL_OFFICIAL_ASSET_MANIFEST_PATH',
    'MAX_DOWNLOAD_CANDIDATES_PER_GAME',
    'OfficialAssetSourceResult',
    'SOURCE_PRIORITY_MAP',
    'SOURCE_PRIORITY_ORDER',
    'resolve_official_asset_candidates',
]
