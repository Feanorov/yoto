from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Any


class SteamCache:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)
        for bucket in ('appdetails', 'reviews', 'deadlines'):
            (self.root_dir / bucket).mkdir(parents=True, exist_ok=True)

    def get(self, bucket: str, key: str, allow_stale: bool = False) -> Any | None:
        path = self._path(bucket, key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding='utf-8-sig'))
        except json.JSONDecodeError:
            return None
        expires_at = payload.get('expires_at')
        if expires_at:
            expires = datetime.fromisoformat(expires_at)
            if expires < datetime.utcnow() and not allow_stale:
                return None
        return payload.get('value')

    def set(self, bucket: str, key: str, value: Any, ttl_hours: int) -> None:
        payload = {
            'stored_at': datetime.utcnow().isoformat(),
            'expires_at': (datetime.utcnow() + timedelta(hours=ttl_hours)).isoformat(),
            'value': value,
        }
        self._path(bucket, key).write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')

    def _path(self, bucket: str, key: str) -> Path:
        safe_key = ''.join(ch if ch.isalnum() or ch in {'-', '_'} else '_' for ch in key)
        return self.root_dir / bucket / f'{safe_key}.json'