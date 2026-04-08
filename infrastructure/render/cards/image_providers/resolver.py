from __future__ import annotations

from .base import IMAGE_PIPELINE_VERSION, VALID_IMAGE_PROVIDER_MODES, ImageResolutionRequest, ResolvedImage


class YotoImageResolver:
    def __init__(self, *, artwork_provider, placeholder_provider, ai_provider=None, mode: str = 'artwork_only') -> None:
        self.artwork_provider = artwork_provider
        self.placeholder_provider = placeholder_provider
        self.ai_provider = ai_provider
        self.mode = self._normalize_mode(mode)

    @staticmethod
    def _normalize_mode(value: str | None) -> str:
        normalized = str(value or 'artwork_only').strip().lower() or 'artwork_only'
        if normalized not in VALID_IMAGE_PROVIDER_MODES:
            return 'artwork_only'
        return normalized

    @staticmethod
    def derive_priority(lane: str | None) -> str:
        normalized = str(lane or '').strip().lower()
        if normalized in {'breaking_freebie', 'high_value_discount'}:
            return 'HIGH'
        if normalized in {'backlog_filler'}:
            return 'LOW'
        return 'NORMAL'

    def resolve(self, request: ImageResolutionRequest) -> ResolvedImage:
        has_artwork = request.artwork_path is not None
        priority = request.priority or self.derive_priority(request.lane)
        mode = self._normalize_mode(request.mode)

        artwork = self.artwork_provider.resolve(request)
        if artwork is not None:
            reason = 'artwork_available_mode_artwork_only' if mode == 'artwork_only' else 'artwork_available'
            return self._with_metadata(
                artwork,
                mode=mode,
                priority=priority,
                decision_reason=reason,
                has_artwork=has_artwork,
                ai_attempted=False,
                ai_succeeded=False,
            )

        if mode == 'artwork_only':
            return self._placeholder(
                request,
                mode=mode,
                priority=priority,
                decision_reason='placeholder_missing_artwork',
                has_artwork=has_artwork,
                ai_attempted=False,
                ai_succeeded=False,
            )

        ai_attempted = self.ai_provider is not None and getattr(self.ai_provider, 'enabled', False)
        if ai_attempted:
            ai_result = self.ai_provider.resolve(request)
            if ai_result is not None:
                return self._with_metadata(
                    ai_result,
                    mode=mode,
                    priority=priority,
                    decision_reason='ai_generated_missing_artwork',
                    has_artwork=has_artwork,
                    ai_attempted=True,
                    ai_succeeded=True,
                )
            return self._placeholder(
                request,
                mode=mode,
                priority=priority,
                decision_reason='placeholder_ai_failed',
                has_artwork=has_artwork,
                ai_attempted=True,
                ai_succeeded=False,
            )

        return self._placeholder(
            request,
            mode=mode,
            priority=priority,
            decision_reason='placeholder_ai_disabled_or_unavailable',
            has_artwork=has_artwork,
            ai_attempted=False,
            ai_succeeded=False,
        )

    def _placeholder(
        self,
        request: ImageResolutionRequest,
        *,
        mode: str,
        priority: str,
        decision_reason: str,
        has_artwork: bool,
        ai_attempted: bool,
        ai_succeeded: bool,
    ) -> ResolvedImage:
        placeholder = self.placeholder_provider.resolve(request)
        return self._with_metadata(
            placeholder,
            mode=mode,
            priority=priority,
            decision_reason=decision_reason,
            has_artwork=has_artwork,
            ai_attempted=ai_attempted,
            ai_succeeded=ai_succeeded,
        )

    @staticmethod
    def _with_metadata(
        result: ResolvedImage,
        *,
        mode: str,
        priority: str,
        decision_reason: str,
        has_artwork: bool,
        ai_attempted: bool,
        ai_succeeded: bool,
    ) -> ResolvedImage:
        metadata = dict(result.metadata)
        metadata.update(
            {
                'mode': mode,
                'priority': priority,
                'decision_reason': decision_reason,
                'pipeline_version': IMAGE_PIPELINE_VERSION,
                'has_artwork': has_artwork,
                'ai_attempted': ai_attempted,
                'ai_succeeded': ai_succeeded,
            }
        )
        return ResolvedImage(image=result.image, metadata=metadata)
