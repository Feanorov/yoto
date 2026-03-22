from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw

from ..domain.entities import VideoManifest
from .structured_logger import StructuredLogger


@dataclass(slots=True, frozen=True)
class ResolvedImageAsset:
    role: str
    path: Path
    used_fallback: bool
    warning: str | None = None


@dataclass(slots=True, frozen=True)
class ResolvedAssets:
    game_image: ResolvedImageAsset
    background: ResolvedImageAsset
    store_badge: Path | None
    warnings: tuple[str, ...]


class AssetResolver:
    def __init__(self, assets_dir: Path | None = None, logger: StructuredLogger | None = None) -> None:
        self.assets_dir = assets_dir or Path(__file__).resolve().parents[1] / 'assets'
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.badges_dir = self.assets_dir / 'badges'
        self.badges_dir.mkdir(parents=True, exist_ok=True)
        self.remote_cache_dir = self.assets_dir / 'cache'
        self.remote_cache_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logger or StructuredLogger()
        self.fallback_game_image = self.assets_dir / 'fallback_game_image.png'
        self.default_background = self.assets_dir / 'default_background.png'
        self._download_cache: dict[str, Path] = {}
        self._ensure_default_assets()

    def resolve(self, manifest: VideoManifest) -> ResolvedAssets:
        game_image_ref = self._preferred_asset_ref(manifest, 'game_image', 'hero', 'header', 'screenshot', 'fallback')
        background_ref = self._preferred_asset_ref(manifest, 'background', 'screenshot', 'hero', 'header', 'game_image', 'fallback')
        rescue_ref = self._event_card_fallback_ref(manifest)
        game_image = self._resolve_image(
            manifest,
            game_image_ref,
            role='game_image',
            fallback=self.fallback_game_image,
            rescue_ref=rescue_ref,
        )
        background = self._resolve_image(
            manifest,
            background_ref or game_image_ref,
            role='background',
            fallback=self.default_background,
            rescue_ref=rescue_ref,
        )
        store_badge = self._resolve_badge(
            manifest,
            manifest.asset_refs.get('store'),
            str(manifest.context.get('store') or '').strip(),
        )
        warnings = tuple(
            warning
            for warning in (
                game_image.warning,
                background.warning,
                None if store_badge is not None else 'missing badge',
            )
            if warning
        )
        return ResolvedAssets(
            game_image=game_image,
            background=background,
            store_badge=store_badge,
            warnings=warnings,
        )

    def load_prepared_image(self, asset_path: Path) -> Image.Image:
        with Image.open(asset_path) as image:
            prepared = image.convert('RGBA')
            prepared.thumbnail((900, 900), Image.Resampling.LANCZOS)
            return prepared.copy()

    def _resolve_image(
        self,
        manifest: VideoManifest,
        asset_ref: str | None,
        *,
        role: str,
        fallback: Path,
        rescue_ref: str | None = None,
    ) -> ResolvedImageAsset:
        min_width, min_height = self._minimum_dimensions(role)
        candidate, reason = self._materialize_asset_path(manifest, asset_ref)
        if reason is None and candidate is None:
            reason = 'missing_asset'
        elif reason is None and not candidate.exists():
            reason = 'file_missing'
        elif reason is None and not self._is_valid_image(candidate, min_width=min_width, min_height=min_height):
            reason = 'image_unreadable_or_too_small'

        rescue_path = self._resolve_rescue_asset(
            manifest,
            rescue_ref,
            asset_ref,
            min_width=min_width,
            min_height=min_height,
        )
        if reason is not None and rescue_path is not None:
            self.logger.info(
                'asset rescue used',
                role=role,
                asset_ref=asset_ref,
                rescue_ref=rescue_ref,
                rescue_path=rescue_path,
                reason=reason,
            )
            return ResolvedImageAsset(role=role, path=rescue_path, used_fallback=False)

        if reason is not None:
            self.logger.warning(
                'asset fallback used',
                role=role,
                asset_ref=asset_ref,
                reason=reason,
                fallback=fallback,
            )
            return ResolvedImageAsset(role=role, path=fallback, used_fallback=True, warning=f'{role}:{reason}')

        return ResolvedImageAsset(role=role, path=candidate, used_fallback=False)

    def _resolve_badge(self, manifest: VideoManifest, asset_ref: str | None, store_name: str) -> Path | None:
        candidate, _ = self._materialize_asset_path(manifest, asset_ref)
        if candidate is not None:
            valid_badge = self._validate_badge(candidate)
            if valid_badge is not None:
                return valid_badge

        if not store_name:
            return None

        badge_name = store_name.lower().replace(' ', '_').replace('-', '_')
        badge_path = self.badges_dir / f'{badge_name}_badge.png'
        valid_badge = self._validate_badge(badge_path)
        if valid_badge is not None:
            return valid_badge

        self.logger.warning('missing badge', store=store_name, reason='badge_file_missing')
        return None

    def _validate_badge(self, path: Path) -> Path | None:
        if not self._is_valid_image(path, min_width=96, min_height=32):
            if path.exists():
                self.logger.warning('missing badge', store=path.name, reason='badge_unreadable_or_too_small')
            return None
        return path

    def _materialize_asset_path(self, manifest: VideoManifest, asset_ref: str | None) -> tuple[Path | None, str | None]:
        if not asset_ref:
            return None, 'missing_asset'
        parsed = urlparse(asset_ref)
        if parsed.scheme in {'http', 'https'}:
            downloaded = self._download_remote_asset(asset_ref)
            if downloaded is None:
                return None, 'remote_download_failed'
            return downloaded, None
        path = Path(asset_ref)
        if path.is_absolute():
            return path, None
        return (manifest.source_path.parent / path).resolve(), None

    def _resolve_rescue_asset(
        self,
        manifest: VideoManifest,
        rescue_ref: str | None,
        original_ref: str | None,
        *,
        min_width: int,
        min_height: int,
    ) -> Path | None:
        if not rescue_ref or rescue_ref == original_ref:
            return None
        candidate, reason = self._materialize_asset_path(manifest, rescue_ref)
        if reason is not None or candidate is None or not candidate.exists():
            return None
        if not self._is_valid_image(candidate, min_width=min_width, min_height=min_height):
            return None
        return candidate

    def _download_remote_asset(self, asset_ref: str) -> Path | None:
        cached = self._download_cache.get(asset_ref)
        if cached is not None and cached.exists():
            return cached

        parsed = urlparse(asset_ref)
        suffix = Path(parsed.path).suffix.lower()
        if suffix not in {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}:
            suffix = '.img'

        target = self.remote_cache_dir / f'{hashlib.sha256(asset_ref.encode("utf-8")).hexdigest()}{suffix}'
        if target.exists():
            self._download_cache[asset_ref] = target
            return target

        temp_path = target.with_suffix(f'{target.suffix}.part')
        try:
            request = Request(asset_ref, headers={'User-Agent': 'TelegramVideoGenerator/1.0'})
            with urlopen(request, timeout=20) as response, temp_path.open('wb') as handle:
                handle.write(response.read())
            temp_path.replace(target)
            self._download_cache[asset_ref] = target
            return target
        except Exception as exc:
            if temp_path.exists():
                temp_path.unlink()
            self.logger.warning('remote asset download failed', asset_ref=asset_ref, error=str(exc))
            return None

    @staticmethod
    def _preferred_asset_ref(manifest: VideoManifest, *keys: str) -> str | None:
        for key in keys:
            value = manifest.asset_refs.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _event_card_fallback_ref(manifest: VideoManifest) -> str | None:
        template_hint = str(manifest.template_hint or '').strip().lower()
        lane = str(manifest.context.get('lane') or '').strip().lower()
        offer_kind = str(manifest.context.get('offer_kind') or '').strip().lower()
        if template_hint == 'event-countdown' or lane == 'event_festival' or offer_kind in {'event', 'festival'}:
            value = manifest.asset_refs.get('card_image')
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _minimum_dimensions(role: str) -> tuple[int, int]:
        if role == 'background':
            return 360, 180
        return 360, 180

    def _ensure_default_assets(self) -> None:
        if not self._is_valid_image(self.fallback_game_image, min_width=400, min_height=400):
            self._write_placeholder(
                self.fallback_game_image,
                top_color=(34, 47, 74),
                bottom_color=(16, 23, 36),
                label='GAME IMAGE',
            )
        if not self._is_valid_image(self.default_background, min_width=400, min_height=400):
            self._write_placeholder(
                self.default_background,
                top_color=(27, 16, 47),
                bottom_color=(5, 8, 20),
                label='BACKGROUND',
            )

    @staticmethod
    def _is_valid_image(path: Path, *, min_width: int, min_height: int) -> bool:
        if not path.exists():
            return False
        try:
            with Image.open(path) as image:
                image.load()
                return image.width >= min_width and image.height >= min_height
        except Exception:
            return False

    @staticmethod
    def _write_placeholder(path: Path, *, top_color: tuple[int, int, int], bottom_color: tuple[int, int, int], label: str) -> None:
        image = Image.new('RGB', (900, 900), top_color)
        draw = ImageDraw.Draw(image)
        for y in range(900):
            ratio = y / 899
            color = tuple(int(top + (bottom - top) * ratio) for top, bottom in zip(top_color, bottom_color))
            draw.line((0, y, 900, y), fill=color)
        draw.rounded_rectangle((90, 90, 810, 810), radius=48, outline=(255, 255, 255), width=6)
        draw.line((180, 720, 720, 180), fill=(255, 255, 255), width=10)
        draw.line((180, 180, 720, 720), fill=(255, 255, 255), width=10)
        draw.text((260, 420), label, fill=(255, 255, 255))
        image.save(path)
