from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from domain.entities.editorial_control import ControlMatcher, EditorialControl, OverrideRule


DEFAULT_MATCHER = {
    'game_ids': [],
    'franchise_keys': [],
    'publishers': [],
    'developers': [],
    'tags': [],
    'offer_kinds': [],
}

DEFAULT_OVERRIDES = {
    'rules': [],
}


class EditorialControlLoader:
    def __init__(self, control_dir: Path, whitelist_priority_boost: float) -> None:
        self.control_dir = control_dir
        self.whitelist_priority_boost = whitelist_priority_boost
        self.control_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_defaults()

    def load(self) -> EditorialControl:
        blacklist = self._load_matcher(self.control_dir / 'blacklist.json')
        whitelist = self._load_matcher(self.control_dir / 'whitelist.json')
        overrides = self._load_overrides(self.control_dir / 'overrides.json')
        return EditorialControl(
            blacklist=blacklist,
            whitelist=whitelist,
            overrides=overrides,
            whitelist_priority_boost=self.whitelist_priority_boost,
        )

    def _load_matcher(self, path: Path) -> ControlMatcher:
        payload = self._load_json(path, DEFAULT_MATCHER)
        return ControlMatcher(
            game_ids=frozenset(str(item).strip() for item in payload.get('game_ids', []) if str(item).strip()),
            franchise_keys=frozenset(str(item).strip().lower() for item in payload.get('franchise_keys', []) if str(item).strip()),
            publishers=frozenset(str(item).strip().lower() for item in payload.get('publishers', []) if str(item).strip()),
            developers=frozenset(str(item).strip().lower() for item in payload.get('developers', []) if str(item).strip()),
            tags=frozenset(str(item).strip().lower() for item in payload.get('tags', []) if str(item).strip()),
            offer_kinds=frozenset(str(item).strip().lower() for item in payload.get('offer_kinds', []) if str(item).strip()),
        )

    def _load_overrides(self, path: Path) -> tuple[OverrideRule, ...]:
        payload = self._load_json(path, DEFAULT_OVERRIDES)
        rules: list[OverrideRule] = []
        for raw in payload.get('rules', []):
            match_block = raw.get('match', {})
            matcher = ControlMatcher(
                game_ids=frozenset(str(item).strip() for item in match_block.get('game_ids', []) if str(item).strip()),
                franchise_keys=frozenset(str(item).strip().lower() for item in match_block.get('franchise_keys', []) if str(item).strip()),
                publishers=frozenset(str(item).strip().lower() for item in match_block.get('publishers', []) if str(item).strip()),
                developers=frozenset(str(item).strip().lower() for item in match_block.get('developers', []) if str(item).strip()),
                tags=frozenset(str(item).strip().lower() for item in match_block.get('tags', []) if str(item).strip()),
                offer_kinds=frozenset(str(item).strip().lower() for item in match_block.get('offer_kinds', []) if str(item).strip()),
            )
            rules.append(
                OverrideRule(
                    name=str(raw.get('name') or 'override').strip(),
                    matcher=matcher,
                    force_lane=(str(raw.get('force_lane')).strip() if raw.get('force_lane') else None),
                    force_priority=float(raw.get('force_priority') or 0.0),
                    force_skip=bool(raw.get('force_skip', False)),
                    force_game_of_day=bool(raw.get('force_game_of_day', False)),
                )
            )
        return tuple(rules)

    def _load_json(self, path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
        if not path.exists():
            path.write_text(json.dumps(fallback, ensure_ascii=False, indent=2), encoding='utf-8')
            return dict(fallback)
        try:
            return json.loads(path.read_text(encoding='utf-8-sig'))
        except json.JSONDecodeError:
            return dict(fallback)

    def _ensure_defaults(self) -> None:
        for filename, payload in {
            'blacklist.json': DEFAULT_MATCHER,
            'whitelist.json': DEFAULT_MATCHER,
            'overrides.json': DEFAULT_OVERRIDES,
        }.items():
            path = self.control_dir / filename
            if not path.exists():
                path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')