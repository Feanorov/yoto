from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from PIL import Image


IMAGE_PIPELINE_VERSION = 'v1'
VALID_IMAGE_PROVIDER_MODES = frozenset({'artwork_only', 'artwork_then_ai', 'ai_first'})


@dataclass(slots=True, frozen=True)
class ResolvedImage:
    image: Image.Image
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ImageResolutionRequest:
    artwork_path: str | Path | None
    title: str
    platform: str
    slug: str
    card_type: str
    lane: str | None
    mode: str
    priority: str
    image_size: tuple[int, int]
    deadline: str | None = None
    old_price: str | None = None
    current_price: str | None = None
    platform_badge: str | None = None
    brand_micro_label: str | None = None


class ImageProvider(Protocol):
    provider_name: str

    def resolve(self, request: ImageResolutionRequest) -> ResolvedImage | None:
        ...
