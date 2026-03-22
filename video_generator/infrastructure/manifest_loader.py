from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from ..domain.entities import VideoManifest


class ManifestValidationError(ValueError):
    pass


class ManifestLoader:
    def load(self, path: Path) -> VideoManifest:
        payload = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(payload, dict):
            raise ManifestValidationError(f'Manifest payload must be an object: {path}')

        asset_refs = self._require_asset_refs(payload, path)
        context = self._require_context(payload, path)
        created_at = self._parse_optional_datetime(payload.get('created_at'), path) or datetime.fromtimestamp(path.stat().st_mtime)

        manifest_hash = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode('utf-8')
        ).hexdigest()

        return VideoManifest(
            manifest_version=self._optional_int(payload.get('manifest_version')) or 1,
            run_key=self._optional_str(payload.get('run_key')) or self._default_run_key(path, created_at),
            created_at=created_at,
            offer_id=self._optional_str(payload.get('offer_id')) or self._default_offer_id(path),
            short_title=self._require_str(payload, 'short_title', path),
            hook_line=self._require_str(payload, 'hook_line', path),
            summary_line=self._require_str(payload, 'summary_line', path),
            urgency_line=self._require_str(payload, 'urgency_line', path),
            asset_refs=asset_refs,
            template_hint=self._optional_str(payload.get('template_hint')) or 'auto',
            context=context,
            source_path=path,
            manifest_hash=manifest_hash,
        )

    @classmethod
    def _require_asset_refs(cls, payload: dict[str, Any], path: Path) -> dict[str, str]:
        asset_refs = payload.get('asset_refs')
        if isinstance(asset_refs, dict):
            return cls._normalize_asset_ref_mapping(asset_refs, path)
        if isinstance(asset_refs, list):
            return cls._normalize_asset_ref_list(asset_refs, path)
        raise ManifestValidationError(f'asset_refs must be an object or list of asset refs: {path}')

    @staticmethod
    def _normalize_asset_ref_mapping(asset_refs: dict[str, Any], path: Path) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for key, value in asset_refs.items():
            if not isinstance(key, str) or not key.strip():
                raise ManifestValidationError(f'asset_refs keys must be non-empty strings: {path}')
            if value is None:
                continue
            if not isinstance(value, str) or not value.strip():
                raise ManifestValidationError(f'asset_refs values must be strings or null: {path}')
            normalized[key.strip()] = value.strip()
        return normalized

    @classmethod
    def _normalize_asset_ref_list(cls, asset_refs: list[Any], path: Path) -> dict[str, str]:
        normalized_items: list[str] = []
        for value in asset_refs:
            if value is None:
                continue
            if not isinstance(value, str) or not value.strip():
                raise ManifestValidationError(f'asset_refs list values must be strings or null: {path}')
            normalized_items.append(value.strip())

        if not normalized_items:
            return {}

        game_image = cls._pick_game_image_ref(normalized_items) or normalized_items[0]
        background = cls._pick_background_ref(normalized_items)
        if background is None:
            background = normalized_items[1] if len(normalized_items) > 1 else game_image

        normalized = {'game_image': game_image}
        if background:
            normalized['background'] = background
        return normalized

    @staticmethod
    def _pick_game_image_ref(asset_refs: list[str]) -> str | None:
        hints = ('header', 'hero', 'capsule', 'thumbnail', 'offerimagewide', 'dieselstorefrontwide', 'cover')
        for value in asset_refs:
            token = value.lower()
            if any(hint in token for hint in hints):
                return value
        return None

    @staticmethod
    def _pick_background_ref(asset_refs: list[str]) -> str | None:
        hints = ('background', 'backdrop', 'screenshot', '/ss_', '_ss', 'library_hero')
        for value in asset_refs:
            token = value.lower()
            if any(hint in token for hint in hints):
                return value
        return None

    @staticmethod
    def _require_context(payload: dict[str, Any], path: Path) -> dict[str, Any]:
        context = payload.get('context')
        if not isinstance(context, dict):
            raise ManifestValidationError(f'context must be an object: {path}')
        return context

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value

    @staticmethod
    def _require_str(payload: dict[str, Any], key: str, path: Path) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ManifestValidationError(f'{key} must be a non-empty string: {path}')
        return value.strip()

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return None
        return value.strip()

    @staticmethod
    def _parse_optional_datetime(value: Any, path: Path) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ManifestValidationError(f'created_at must be an ISO-8601 string when present: {path}')
        normalized = value.strip().replace('Z', '+00:00')
        try:
            return datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ManifestValidationError(f'created_at must be ISO-8601: {path}') from exc

    @staticmethod
    def _default_offer_id(path: Path) -> str:
        stem = path.stem
        if '_video_manifest_' in stem:
            return stem.split('_video_manifest_', 1)[-1] or stem
        return stem

    @staticmethod
    def _default_run_key(path: Path, created_at: datetime) -> str:
        stem = path.stem
        if '_video_manifest_' in stem:
            prefix = stem.split('_video_manifest_', 1)[0].strip('_')
            if prefix:
                return prefix
        return created_at.strftime('%Y%m%dT%H%M%S')
