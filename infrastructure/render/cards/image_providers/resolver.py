from __future__ import annotations

from dataclasses import replace

from infrastructure.render.cards.visual_decision_engine import AI_SOURCE_TYPE, resolve_cover_decision_asset_bridge

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

    @staticmethod
    def _new_trace(*, requested_mode: str | None, normalized_mode: str, has_artwork: bool) -> dict[str, object]:
        return {
            'requested_mode': str(requested_mode or ''),
            'normalized_mode': normalized_mode,
            'has_artwork': has_artwork,
            'steps': [],
            'final_selected_provider': None,
            'final_selected_source': None,
            'final_decision_reason': None,
        }

    @staticmethod
    def _append_trace(
        trace: dict[str, object],
        *,
        candidate_provider: str,
        check_name: str,
        check_result: bool,
        fail_reason: str | None = None,
    ) -> None:
        steps = trace.setdefault('steps', [])
        if isinstance(steps, list):
            steps.append(
                {
                    'candidate_provider': candidate_provider,
                    'check_name': check_name,
                    'check_result': bool(check_result),
                    'fail_reason': fail_reason,
                }
            )

    @staticmethod
    def _finalize_trace(
        trace: dict[str, object],
        *,
        result: ResolvedImage,
        decision_reason: str,
    ) -> dict[str, object]:
        finalized = dict(trace)
        finalized['steps'] = [dict(step) for step in trace.get('steps', []) if isinstance(step, dict)]
        finalized['final_selected_provider'] = str(
            result.metadata.get('provider_name')
            or result.metadata.get('provider')
            or result.metadata.get('selected_source')
            or 'unknown'
        )
        finalized['final_selected_source'] = str(result.metadata.get('selected_source') or 'unknown')
        finalized['final_decision_reason'] = decision_reason
        return finalized

    @staticmethod
    def _evaluate_ai_quality(request: ImageResolutionRequest, result: ResolvedImage) -> dict[str, object]:
        width, height = result.image.size
        required_width, required_height = request.image_size
        asset_path_present = bool(str(result.metadata.get('asset_path') or '').strip())
        reject_reason: str | None = None
        if width < required_width or height < required_height:
            reject_reason = 'image_below_required_size'
        elif not asset_path_present:
            reject_reason = 'ai_asset_path_missing'
        return {
            'quality_checked': True,
            'quality_passed': reject_reason is None,
            'quality_reject_reason': reject_reason,
            'quality_metrics': {
                'width': width,
                'height': height,
                'required_width': required_width,
                'required_height': required_height,
                'asset_path_present': asset_path_present,
            },
        }

    @staticmethod
    def _provider_metadata(provider: object | None) -> dict[str, object]:
        payload = getattr(provider, 'latest_diagnostics', None)
        if not isinstance(payload, dict):
            return {}
        return {str(key): value for key, value in payload.items()}

    @staticmethod
    def _normalized_path_identity(value: object | None) -> str | None:
        text = str(value or '').strip()
        return text.lower() or None

    def _decision_asset_used(self, *, result: ResolvedImage, bridge) -> bool:
        if not bool(getattr(bridge, 'candidate_valid', False)):
            return False
        if str(result.metadata.get('selected_source') or '') != 'artwork':
            return False
        actual_path = self._normalized_path_identity(result.metadata.get('asset_path'))
        decision_path = self._normalized_path_identity(getattr(bridge, 'resolved_local_path', None))
        return actual_path is not None and actual_path == decision_path

    def _actual_image_source_type(self, *, result: ResolvedImage, bridge) -> str:
        selected_source = str(result.metadata.get('selected_source') or 'unknown')
        if self._decision_asset_used(result=result, bridge=bridge):
            return str(getattr(bridge, 'selected_asset_source_type', '') or 'artwork')
        if selected_source == 'artwork':
            return str(result.metadata.get('artwork_source_type') or 'artwork')
        if selected_source == 'ai':
            return AI_SOURCE_TYPE
        if selected_source == 'placeholder':
            return 'placeholder'
        return selected_source

    @staticmethod
    def _actual_image_path_or_url(result: ResolvedImage) -> str | None:
        asset_path = str(result.metadata.get('asset_path') or '').strip()
        if asset_path:
            return asset_path
        output_path = str(result.metadata.get('output_path') or '').strip()
        if output_path:
            return output_path
        return None

    def _decision_metadata(self, *, request: ImageResolutionRequest, result: ResolvedImage, bridge) -> dict[str, object]:
        decision_asset_used = self._decision_asset_used(result=result, bridge=bridge)
        actual_image_source_type = self._actual_image_source_type(result=result, bridge=bridge)
        actual_image_path_or_url = self._actual_image_path_or_url(result)
        decision_selected_asset = (
            dict(getattr(bridge, 'selected_asset', {}))
            if isinstance(getattr(bridge, 'selected_asset', None), dict)
            else None
        )
        decision_asset_reject_reason = None
        if not decision_asset_used:
            decision_asset_reject_reason = str(getattr(bridge, 'decision_asset_reject_reason', '') or '').strip() or None
        cover_decision = request.cover_decision if isinstance(request.cover_decision, dict) else None
        return {
            'cover_decision_selected_asset': decision_selected_asset,
            'cover_decision_use_ai': bool(cover_decision.get('use_ai', False)) if cover_decision is not None else None,
            'cover_decision_image_source_type': (
                str(cover_decision.get('image_source_type') or '').strip() if cover_decision is not None else None
            ) or None,
            'actual_image_source_type': actual_image_source_type,
            'actual_image_path_or_url': actual_image_path_or_url,
            'decision_asset_used': decision_asset_used,
            'decision_asset_use_reason': (
                str(getattr(bridge, 'decision_asset_use_reason', '') or '').strip()
                if decision_asset_used
                else None
            ) or None,
            'decision_asset_reject_reason': (
                decision_asset_reject_reason
                or (
                    'decision_asset_not_used'
                    if bool(getattr(bridge, 'candidate_valid', False)) and not decision_asset_used
                    else None
                )
            ),
            'decision_asset_matches_actual_source': bool(
                decision_asset_used
                and str(actual_image_source_type or '') == str(getattr(bridge, 'selected_asset_source_type', '') or '')
            ),
        }

    def resolve(self, request: ImageResolutionRequest) -> ResolvedImage:
        decision_asset_bridge = resolve_cover_decision_asset_bridge(request.cover_decision)
        effective_request = (
            replace(request, artwork_path=getattr(decision_asset_bridge, 'resolved_local_path', None))
            if bool(getattr(decision_asset_bridge, 'candidate_valid', False))
            else request
        )
        has_artwork = effective_request.artwork_path is not None
        priority = request.priority or self.derive_priority(request.lane)
        mode = self._normalize_mode(request.mode)
        resolver_trace = self._new_trace(requested_mode=request.mode, normalized_mode=mode, has_artwork=has_artwork)
        resolver_trace['cover_decision_present'] = isinstance(request.cover_decision, dict)
        resolver_trace['cover_decision_selected_asset'] = (
            dict(getattr(decision_asset_bridge, 'selected_asset', {}))
            if isinstance(getattr(decision_asset_bridge, 'selected_asset', None), dict)
            else None
        )
        resolver_trace['decision_asset_candidate_valid'] = bool(getattr(decision_asset_bridge, 'candidate_valid', False))
        resolver_trace['decision_asset_use_reason'] = getattr(decision_asset_bridge, 'decision_asset_use_reason', None)
        resolver_trace['decision_asset_reject_reason'] = getattr(decision_asset_bridge, 'decision_asset_reject_reason', None)
        self._append_trace(
            resolver_trace,
            candidate_provider='artwork',
            check_name='decision_asset_bridge_candidate_valid',
            check_result=bool(getattr(decision_asset_bridge, 'candidate_valid', False)),
            fail_reason=(
                str(getattr(decision_asset_bridge, 'decision_asset_reject_reason', '') or '').strip() or None
            ),
        )

        self._append_trace(
            resolver_trace,
            candidate_provider='artwork',
            check_name='artwork_input_present',
            check_result=has_artwork,
            fail_reason=None if has_artwork else 'request_artwork_path_missing',
        )

        artwork = self.artwork_provider.resolve(effective_request)
        self._append_trace(
            resolver_trace,
            candidate_provider='artwork',
            check_name='artwork_provider_resolved',
            check_result=artwork is not None,
            fail_reason=None if artwork is not None else 'artwork_provider_returned_none',
        )
        if artwork is not None:
            decision_asset_used = self._decision_asset_used(result=artwork, bridge=decision_asset_bridge)
            reason = (
                'decision_selected_official_asset'
                if decision_asset_used
                else ('artwork_available_mode_artwork_only' if mode == 'artwork_only' else 'artwork_available')
            )
            self._append_trace(
                resolver_trace,
                candidate_provider='ai',
                check_name='artwork_missing_for_ai_branch',
                check_result=False,
                fail_reason='artwork_available_short_circuit',
            )
            return self._with_metadata(
                artwork,
                mode=mode,
                priority=priority,
                decision_reason=reason,
                has_artwork=has_artwork,
                ai_attempted=False,
                ai_succeeded=False,
                extra_metadata=self._decision_metadata(
                    request=request,
                    result=artwork,
                    bridge=decision_asset_bridge,
                ),
                resolver_trace=self._finalize_trace(resolver_trace, result=artwork, decision_reason=reason),
            )

        self._append_trace(
            resolver_trace,
            candidate_provider='ai',
            check_name='artwork_missing_for_ai_branch',
            check_result=True,
            fail_reason=None,
        )
        self._append_trace(
            resolver_trace,
            candidate_provider='ai',
            check_name='mode_allows_ai',
            check_result=mode != 'artwork_only',
            fail_reason=None if mode != 'artwork_only' else 'mode_artwork_only',
        )
        if mode == 'artwork_only':
            self._append_trace(
                resolver_trace,
                candidate_provider='placeholder',
                check_name='placeholder_fallback_selected',
                check_result=True,
                fail_reason=None,
            )
            return self._placeholder(
                request,
                mode=mode,
                priority=priority,
                decision_reason='placeholder_missing_artwork',
                has_artwork=has_artwork,
                ai_attempted=False,
                ai_succeeded=False,
                resolver_trace=resolver_trace,
                bridge=decision_asset_bridge,
            )

        ai_provider_present = self.ai_provider is not None
        self._append_trace(
            resolver_trace,
            candidate_provider='ai',
            check_name='ai_provider_present',
            check_result=ai_provider_present,
            fail_reason=None if ai_provider_present else 'ai_provider_missing',
        )
        ai_attempted = ai_provider_present and getattr(self.ai_provider, 'enabled', False)
        self._append_trace(
            resolver_trace,
            candidate_provider='ai',
            check_name='ai_provider_enabled',
            check_result=ai_attempted,
            fail_reason=None if ai_attempted else ('ai_provider_disabled' if ai_provider_present else 'ai_provider_missing'),
        )
        if ai_attempted:
            ai_result = self.ai_provider.resolve(request)
            ai_provider_metadata = self._provider_metadata(self.ai_provider)
            self._append_trace(
                resolver_trace,
                candidate_provider='ai',
                check_name='ai_provider_resolved',
                check_result=ai_result is not None,
                fail_reason=None if ai_result is not None else 'ai_provider_returned_none',
            )
            if ai_result is not None:
                quality_metadata = self._evaluate_ai_quality(request, ai_result)
                self._append_trace(
                    resolver_trace,
                    candidate_provider='ai',
                    check_name='ai_quality_checked',
                    check_result=bool(quality_metadata.get('quality_checked', False)),
                    fail_reason=None,
                )
                self._append_trace(
                    resolver_trace,
                    candidate_provider='ai',
                    check_name='ai_quality_passed',
                    check_result=bool(quality_metadata.get('quality_passed', False)),
                    fail_reason=str(quality_metadata.get('quality_reject_reason') or '') or None,
                )
                if not bool(quality_metadata.get('quality_passed', False)):
                    self._append_trace(
                        resolver_trace,
                        candidate_provider='placeholder',
                        check_name='placeholder_fallback_selected',
                        check_result=True,
                        fail_reason=None,
                    )
                    return self._placeholder(
                        request,
                        mode=mode,
                        priority=priority,
                        decision_reason='placeholder_ai_quality_reject',
                        has_artwork=has_artwork,
                        ai_attempted=True,
                        ai_succeeded=False,
                        resolver_trace=resolver_trace,
                        quality_metadata=quality_metadata,
                        bridge=decision_asset_bridge,
                    )
                ai_resolution_metadata = self._decision_metadata(
                    request=request,
                    result=ai_result,
                    bridge=decision_asset_bridge,
                )
                ai_resolution_metadata.update(ai_provider_metadata)
                return self._with_metadata(
                    ai_result,
                    mode=mode,
                    priority=priority,
                    decision_reason='ai_generated_missing_artwork',
                    has_artwork=has_artwork,
                    ai_attempted=True,
                    ai_succeeded=True,
                    quality_metadata=quality_metadata,
                    extra_metadata=ai_resolution_metadata,
                    resolver_trace=self._finalize_trace(
                        resolver_trace,
                        result=ai_result,
                        decision_reason='ai_generated_missing_artwork',
                    ),
                )
            self._append_trace(
                resolver_trace,
                candidate_provider='placeholder',
                check_name='placeholder_fallback_selected',
                check_result=True,
                fail_reason=None,
            )
            return self._placeholder(
                request,
                mode=mode,
                priority=priority,
                decision_reason='placeholder_ai_failed',
                has_artwork=has_artwork,
                ai_attempted=True,
                ai_succeeded=False,
                resolver_trace=resolver_trace,
                quality_metadata=None,
                bridge=decision_asset_bridge,
                extra_metadata=ai_provider_metadata,
            )

        self._append_trace(
            resolver_trace,
            candidate_provider='placeholder',
            check_name='placeholder_fallback_selected',
            check_result=True,
            fail_reason=None,
        )
        return self._placeholder(
            request,
            mode=mode,
            priority=priority,
            decision_reason='placeholder_ai_disabled_or_unavailable',
            has_artwork=has_artwork,
            ai_attempted=False,
            ai_succeeded=False,
            resolver_trace=resolver_trace,
            quality_metadata=None,
            bridge=decision_asset_bridge,
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
        resolver_trace: dict[str, object],
        bridge,
        quality_metadata: dict[str, object] | None = None,
        extra_metadata: dict[str, object] | None = None,
    ) -> ResolvedImage:
        placeholder = self.placeholder_provider.resolve(request)
        combined_extra_metadata = self._decision_metadata(
            request=request,
            result=placeholder,
            bridge=bridge,
        )
        if extra_metadata is not None:
            combined_extra_metadata.update(extra_metadata)
        return self._with_metadata(
            placeholder,
            mode=mode,
            priority=priority,
            decision_reason=decision_reason,
            has_artwork=has_artwork,
            ai_attempted=ai_attempted,
            ai_succeeded=ai_succeeded,
            quality_metadata=quality_metadata,
            extra_metadata=combined_extra_metadata,
            resolver_trace=self._finalize_trace(resolver_trace, result=placeholder, decision_reason=decision_reason),
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
        quality_metadata: dict[str, object] | None = None,
        extra_metadata: dict[str, object] | None = None,
        resolver_trace: dict[str, object] | None = None,
    ) -> ResolvedImage:
        metadata = dict(result.metadata)
        quality_payload = {
            'quality_checked': False,
            'quality_passed': False,
            'quality_reject_reason': None,
            'quality_metrics': None,
        }
        if quality_metadata is not None:
            quality_payload.update(quality_metadata)
        metadata.update(quality_payload)
        if extra_metadata is not None:
            metadata.update(extra_metadata)
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
        if resolver_trace is not None:
            metadata['resolver_trace'] = resolver_trace
        return ResolvedImage(image=result.image, metadata=metadata)
