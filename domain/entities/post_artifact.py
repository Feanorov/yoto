from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PostArtifact:
    offer_id: str
    caption_html: str
    hashtags: list[str]
    template_id: str
    render_inputs: dict[str, Any]
    assets_used: list[str]
    idempotency_key: str
    caption_hash: str
    image_hash: str
    render_diagnostics: dict[str, Any] = field(default_factory=dict)
    decision_debug: dict[str, Any] = field(default_factory=dict)
    telegram_message_id: int | None = None