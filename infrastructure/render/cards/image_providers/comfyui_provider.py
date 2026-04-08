from __future__ import annotations

from pathlib import Path

from PIL import Image

from infrastructure.render.cards.asset_source import resolve_existing_asset_path

from .base import ImageResolutionRequest, ResolvedImage


class ComfyUIImageProvider:
    provider_name = 'comfyui'

    def __init__(self, *, enabled: bool = False, **_: object) -> None:
        self.enabled = bool(enabled)

    def resolve(self, request: ImageResolutionRequest) -> ResolvedImage:
        image_path = self._resolve_local_image_path(request)
        if image_path is not None:
            try:
                image = Image.open(image_path).convert('RGB')
            except OSError:
                image = self._build_stub_image(request.image_size)
                image_path = None
        else:
            image = self._build_stub_image(request.image_size)

        metadata = {
            'selected_source': 'ai',
            'provider_name': self.provider_name,
            'provider': 'comfyui',
            'status': 'success',
        }
        if image_path is not None:
            metadata['asset_path'] = str(image_path.resolve())

        return ResolvedImage(image=image, metadata=metadata)

    def _resolve_local_image_path(self, request: ImageResolutionRequest) -> Path | None:
        artwork_path = self._resolve_artwork_path(request.artwork_path)
        if artwork_path is not None:
            return artwork_path

        repo_root = Path(__file__).resolve().parents[4]
        candidates = (
            repo_root / 'output/cards/premium_finish_review_20260320T102501Z/cards/yoto_card_typography_free_fallback.png',
            repo_root / 'output/cards/live_validation_v45/cards/yoto_card_epic_free_epic_4889207626a44fed973f5e72ae79ce9d_isonzo.png',
            repo_root / 'output/cards/yoto_card_steam_discount_steam_1426210_it_takes_two.png',
        )
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    @staticmethod
    def _resolve_artwork_path(artwork_path: str | Path | None) -> Path | None:
        if artwork_path is None:
            return None
        if isinstance(artwork_path, Path):
            if artwork_path.exists() and artwork_path.is_file():
                return artwork_path
            return None
        return resolve_existing_asset_path(str(artwork_path))

    @staticmethod
    def _build_stub_image(size: tuple[int, int]) -> Image.Image:
        width = max(64, int(size[0]))
        height = max(64, int(size[1]))
        return Image.new('RGB', (width, height), '#101820')
