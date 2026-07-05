from __future__ import annotations

import copy
import hashlib
import socket
from pathlib import Path
from typing import Any
import urllib.error
import urllib.parse
import urllib.request


SUPPORTED_REMOTE_IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp"})
SUPPORTED_CONTENT_TYPE_SUFFIXES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
DOWNLOAD_TIMEOUT_SECONDS = 15
DOWNLOAD_MAX_BYTES = 16 * 1024 * 1024
DOWNLOAD_CHUNK_SIZE = 64 * 1024


class VisualStagingError(ValueError):
    pass


def stage_renderer_visuals(
    renderer_input: dict[str, Any],
    output_dir: str | Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(renderer_input, dict):
        raise VisualStagingError("Visual staging failed: renderer_input must be a dict.")

    raw_scenes = renderer_input.get("scenes")
    if not isinstance(raw_scenes, list):
        raise VisualStagingError("Visual staging failed: renderer_input.scenes must be a list.")

    resolved_output_dir = _resolve_output_dir(output_dir)
    staged_visuals_dir = (resolved_output_dir / "staged_visuals").resolve()
    staged_visuals_dir.mkdir(parents=True, exist_ok=True)

    staged_renderer_input = copy.deepcopy(renderer_input)
    staged_scenes = staged_renderer_input.get("scenes")
    if not isinstance(staged_scenes, list):
        raise VisualStagingError("Visual staging failed: staged renderer_input.scenes must be a list.")

    remote_cache: dict[str, Path] = {}
    staged_visual_paths: list[Path] = []
    staged_scene_ids: list[str] = []
    preserved_local_visual_count = 0
    downloaded_visual_count = 0
    cached_visual_count = 0

    for index, scene_payload in enumerate(staged_scenes):
        if not isinstance(scene_payload, dict):
            raise VisualStagingError(
                f"Visual staging failed: renderer_input.scenes[{index}] must be a dict.",
            )

        scene_id = _pick_text(scene_payload.get("scene_id")) or f"scene_{index + 1}"
        visual = scene_payload.get("visual")
        if not isinstance(visual, dict):
            raise VisualStagingError(
                f"Visual staging failed: visual must be a dict for scene_id={scene_id!r}.",
            )

        asset_ref = _required_text(
            visual.get("asset_ref"),
            error_message=f"Visual staging failed: visual.asset_ref is missing for scene_id={scene_id!r}.",
        )
        classification = _classify_asset_ref(asset_ref)
        if classification == "unsupported_scheme":
            raise VisualStagingError(
                f"Visual staging failed: unsupported visual URL scheme for scene_id={scene_id!r}: {asset_ref}",
            )
        if classification == "local":
            _validate_local_visual(asset_ref, scene_id=scene_id)
            preserved_local_visual_count += 1
            continue

        staged_scene_ids.append(scene_id)
        cached_path = remote_cache.get(asset_ref)
        if cached_path is not None:
            visual["asset_ref"] = str(cached_path)
            continue

        staged_path, download_status = _stage_remote_visual(
            remote_url=asset_ref,
            scene_id=scene_id,
            scene_order=_int_or_none(scene_payload.get("order")) or (index + 1),
            staged_visuals_dir=staged_visuals_dir,
        )
        remote_cache[asset_ref] = staged_path
        visual["asset_ref"] = str(staged_path)
        staged_visual_paths.append(staged_path)
        if download_status == "downloaded":
            downloaded_visual_count += 1
        elif download_status == "cached":
            cached_visual_count += 1

    metadata = {
        "staged_visuals_dir_path": staged_visuals_dir,
        "staged_visual_paths": tuple(staged_visual_paths),
        "staged_visual_count": len(staged_visual_paths),
        "staged_scene_ids": tuple(staged_scene_ids),
        "staged_scene_count": len(staged_scene_ids),
        "downloaded_visual_count": downloaded_visual_count,
        "cached_visual_count": cached_visual_count,
        "preserved_local_visual_count": preserved_local_visual_count,
        "remote_visual_sources": tuple(remote_cache.keys()),
    }
    return staged_renderer_input, metadata


def _stage_remote_visual(
    *,
    remote_url: str,
    scene_id: str,
    scene_order: int,
    staged_visuals_dir: Path,
) -> tuple[Path, str]:
    suffix_from_url = _remote_image_suffix_from_url(remote_url, scene_id=scene_id)
    url_digest = hashlib.sha256(remote_url.encode("utf-8")).hexdigest()[:16]

    if suffix_from_url:
        cached_target = (staged_visuals_dir / f"{scene_order:02d}_{scene_id}_{url_digest}{suffix_from_url}").resolve()
        if _is_readable_image(cached_target):
            return cached_target, "cached"
    else:
        cached_target = _find_cached_target(url_digest=url_digest, staged_visuals_dir=staged_visuals_dir)
        if cached_target is not None and _is_readable_image(cached_target):
            return cached_target, "cached"

    request = urllib.request.Request(
        remote_url,
        headers={
            "Accept": "image/*",
            "User-Agent": "YOTOVideoVisualStaging/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            content_type = _response_content_type(response.headers)
            if content_type and content_type not in SUPPORTED_CONTENT_TYPE_SUFFIXES:
                raise VisualStagingError(
                    f"Visual staging failed: unsupported remote image content-type for scene_id={scene_id!r}: "
                    f"{content_type}",
                )

            target_suffix = suffix_from_url or SUPPORTED_CONTENT_TYPE_SUFFIXES.get(content_type or "")
            if not target_suffix:
                raise VisualStagingError(
                    f"Visual staging failed: remote visual URL is missing a supported image extension and did not "
                    f"return a safe image content-type for scene_id={scene_id!r}: {remote_url}",
                )

            target_path = (staged_visuals_dir / f"{scene_order:02d}_{scene_id}_{url_digest}{target_suffix}").resolve()
            if _is_readable_image(target_path):
                return target_path, "cached"

            temp_path = target_path.with_suffix(f"{target_path.suffix}.part")
            _cleanup_temp_file(temp_path)

            content_length = response.headers.get("Content-Length")
            if content_length:
                try:
                    if int(content_length) > DOWNLOAD_MAX_BYTES:
                        raise VisualStagingError(
                            f"Visual staging failed: remote visual exceeds byte limit for scene_id={scene_id!r}: "
                            f"{remote_url}",
                        )
                except (TypeError, ValueError):
                    pass

            bytes_written = 0
            with temp_path.open("wb") as handle:
                while True:
                    chunk = response.read(DOWNLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    bytes_written += len(chunk)
                    if bytes_written > DOWNLOAD_MAX_BYTES:
                        raise VisualStagingError(
                            f"Visual staging failed: remote visual exceeds byte limit for scene_id={scene_id!r}: "
                            f"{remote_url}",
                        )
                    handle.write(chunk)

            if not _is_readable_image(temp_path):
                raise VisualStagingError(
                    f"Visual staging failed: downloaded remote visual is not a readable image for "
                    f"scene_id={scene_id!r}: {remote_url}",
                )

            temp_path.replace(target_path)
            return target_path, "downloaded"
    except urllib.error.HTTPError as exc:
        raise VisualStagingError(
            f"Visual staging failed: remote visual download returned HTTP {exc.code} for "
            f"scene_id={scene_id!r}: {remote_url}",
        ) from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        reason_text = reason.__class__.__name__ if reason is not None else exc.__class__.__name__
        raise VisualStagingError(
            f"Visual staging failed: remote visual download failed for scene_id={scene_id!r}: "
            f"{remote_url} ({reason_text})",
        ) from exc
    except socket.timeout as exc:
        raise VisualStagingError(
            f"Visual staging failed: remote visual download timed out for scene_id={scene_id!r}: {remote_url}",
        ) from exc
    except TimeoutError as exc:
        raise VisualStagingError(
            f"Visual staging failed: remote visual download timed out for scene_id={scene_id!r}: {remote_url}",
        ) from exc
    except OSError as exc:
        raise VisualStagingError(
            f"Visual staging failed: could not write staged visual for scene_id={scene_id!r}: {exc}",
        ) from exc
    finally:
        if "temp_path" in locals():
            _cleanup_temp_file(temp_path)


def _resolve_output_dir(output_dir: str | Path) -> Path:
    raw_output = Path(output_dir)
    resolved = raw_output if raw_output.is_absolute() else (Path.cwd() / raw_output)
    return resolved.resolve()


def _classify_asset_ref(asset_ref: str) -> str:
    lowered = asset_ref.lower()
    if lowered.startswith("http://") or lowered.startswith("https://"):
        return "remote"
    if "://" in asset_ref:
        return "unsupported_scheme"
    return "local"


def _validate_local_visual(asset_ref: str, *, scene_id: str) -> None:
    raw_path = Path(asset_ref)
    resolved = raw_path if raw_path.is_absolute() else (Path.cwd() / raw_path)
    resolved = resolved.resolve()
    if not resolved.exists() or not resolved.is_file():
        raise VisualStagingError(
            f"Visual staging failed: no usable local visual exists for scene_id={scene_id!r}: {resolved}",
        )


def _remote_image_suffix_from_url(remote_url: str, *, scene_id: str) -> str | None:
    parsed = urllib.parse.urlsplit(remote_url)
    suffix = Path(parsed.path).suffix.lower()
    if suffix in SUPPORTED_REMOTE_IMAGE_SUFFIXES:
        return suffix
    if suffix:
        raise VisualStagingError(
            f"Visual staging failed: unsupported remote visual URL for scene_id={scene_id!r}: {remote_url}",
        )
    return None


def _find_cached_target(*, url_digest: str, staged_visuals_dir: Path) -> Path | None:
    for suffix in sorted(SUPPORTED_REMOTE_IMAGE_SUFFIXES):
        matches = list(staged_visuals_dir.glob(f"*_{url_digest}{suffix}"))
        for match in matches:
            if match.exists() and match.is_file():
                return match.resolve()
    return None


def _response_content_type(headers: Any) -> str | None:
    content_type = ""
    get_content_type = getattr(headers, "get_content_type", None)
    if callable(get_content_type):
        content_type = str(get_content_type() or "").strip().lower()
    if not content_type:
        raw_header = str(getattr(headers, "get", lambda *_args, **_kwargs: "")("Content-Type") or "")
        content_type = raw_header.split(";", 1)[0].strip().lower()
    return content_type or None


def _cleanup_temp_file(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        return


def _is_readable_image(path: Path) -> bool:
    try:
        from PIL import Image

        with Image.open(path) as image:
            image.verify()
    except (FileNotFoundError, OSError, SyntaxError, ValueError):
        return False
    return True


def _required_text(value: Any, *, error_message: str) -> str:
    cleaned = _pick_text(value)
    if not cleaned:
        raise VisualStagingError(error_message)
    return cleaned


def _pick_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        cleaned = str(value).strip()
        if cleaned:
            return cleaned
    return None


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "VisualStagingError",
    "stage_renderer_visuals",
]
