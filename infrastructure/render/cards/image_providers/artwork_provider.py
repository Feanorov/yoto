from __future__ import annotations

from pathlib import Path

from PIL import Image

from infrastructure.render.cards.asset_source import resolve_existing_asset_path

from .base import ImageResolutionRequest, ResolvedImage


class ArtworkImageProvider:
    provider_name = 'artwork'

    def __init__(self) -> None:
        self._cache: dict[str, Image.Image] = {}

    def resolve(self, request: ImageResolutionRequest) -> ResolvedImage | None:
        path = self._resolve_asset_path(request.artwork_path)
        if path is None or not path.exists():
            return None
        cache_key = str(path.resolve())
        cached = self._cache.get(cache_key)
        if cached is not None:
            return ResolvedImage(
                image=cached.copy(),
                metadata={
                    'selected_source': 'artwork',
                    'provider_name': self.provider_name,
                    'asset_path': cache_key,
                },
            )
        try:
            image = Image.open(path).convert('RGB')
        except OSError:
            return None
        self._cache[cache_key] = image
        return ResolvedImage(
            image=image.copy(),
            metadata={
                'selected_source': 'artwork',
                'provider_name': self.provider_name,
                'asset_path': cache_key,
            },
        )

    @staticmethod
    def _resolve_asset_path(asset_path: str | Path | None) -> Path | None:
        if asset_path is None:
            return None
        if isinstance(asset_path, Path):
            if asset_path.exists() and asset_path.is_file():
                return asset_path
            return None
        return resolve_existing_asset_path(str(asset_path))
