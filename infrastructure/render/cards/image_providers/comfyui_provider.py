from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image

from infrastructure.render.cards.asset_source import resolve_existing_asset_path

from .base import ImageResolutionRequest, ResolvedImage


DEFAULT_PROMPT_VARIANT = 'shot_focused_cinematic_grounded'
PROMPT_INTENT = DEFAULT_PROMPT_VARIANT
HERO_ACTION_PROMPT_INTENT = 'hero_action_focus'
VALID_PROMPT_VARIANTS = frozenset({DEFAULT_PROMPT_VARIANT, HERO_ACTION_PROMPT_INTENT})
DEFAULT_KSAMPLER_SEED = 42424242
VISUAL_INTENT_HERO_ACTION = 'HERO_ACTION'
VISUAL_INTENT_VEHICLE_MOTION = 'VEHICLE_MOTION'
VISUAL_INTENT_WORLD_SCALE = 'WORLD_SCALE'
VISUAL_INTENT_ACTIVITY_FOCUS = 'ACTIVITY_FOCUS'
VISUAL_INTENT_THREAT_ATMOSPHERE = 'THREAT_ATMOSPHERE'
PROMPT_NEGATIVE_SUMMARY = (
    'no ui, interface, hud, overlay, text, subtitle, logo, watermark, '
    'price tags, buttons, promo badge, banner, poster, ad creative, card frame, telegram post layout'
)
VISUAL_INTENT_PROMPT_BLOCKS = {
    VISUAL_INTENT_HERO_ACTION: 'one main character, clear action, medium or close shot, strong foreground focus, dynamic pose',
    VISUAL_INTENT_VEHICLE_MOTION: 'vehicle as main subject, speed, motion, dynamic camera angle, road or track, movement emphasis',
    VISUAL_INTENT_WORLD_SCALE: 'wide strategic view, map, empire, city, units, large scale composition, no main character focus',
    VISUAL_INTENT_ACTIVITY_FOCUS: 'clear activity, visible action, interaction with environment, readable task or loop',
    VISUAL_INTENT_THREAT_ATMOSPHERE: 'visible threat, tension, atmosphere, strong lighting contrast, readable danger source',
}
VISUAL_INTENT_NEGATIVE_BLOCKS = {
    VISUAL_INTENT_HERO_ACTION: 'no empty landscape, no distant tiny character',
    VISUAL_INTENT_VEHICLE_MOTION: 'no static parked vehicle, no human hero focus',
    VISUAL_INTENT_WORLD_SCALE: 'no single character close-up, no foreground hero, no portrait shot',
    VISUAL_INTENT_ACTIVITY_FOCUS: 'no empty environment, no unclear action',
    VISUAL_INTENT_THREAT_ATMOSPHERE: 'no pure darkness, no empty fog',
}
VARIATION_CAMERAS = ('close-up', 'low-angle', 'over-the-shoulder', 'wide action frame')
VARIATION_MOMENTS = ('impact moment', 'discovery moment', 'chase/escape moment', 'confrontation moment')
VARIATION_FOCUS = ('main character/object', 'vehicle/tool', 'enemy/threat', 'environment hazard')
VARIATION_COMPOSITIONS = ('foreground subject', 'diagonal movement', 'strong silhouette', 'high contrast focal point')
SCENE_REFERENCE_PATHS = (
    'output/offline_validation/snapshots/20260320T085508Z/assets/queue/0c880d72d11640b6e5a4897f87c6cfed2fd76740c74161f501b241f271e30278.jpg',
    'output/offline_validation/snapshots/20260320T085508Z/assets/queue/1243014462b80f06b506e9b926d84a3dfb6056d69750a3f34d7774f087da816e.jpg',
    'output/offline_validation/snapshots/20260320T085508Z/assets/queue/208a997d760533e4dd4c7775799a09955fa5a6185afafa30e11af1e02a03dee6.jpg',
    'output/offline_validation/snapshots/20260320T085508Z/assets/queue/6738d8a09addd271c147a1f8f08c2020a6c9565eb3616cc20bb90b5f2f7bb813.jpg',
    'output/offline_validation/golden/current/assets/queue/0d83143744ee71ad3afd99212a692ddcbf7d5827476e87e48de63b13c7f2e45b.jpg',
)
UI_STYLE_PATH_TOKENS = (
    'yoto_card',
    'card',
    'banner',
    'poster',
    'telegram',
    'caption',
    'promo',
    'outbox',
)


def select_visual_intent(game: dict[str, Any]) -> tuple[str, str]:
    title = str(game.get('title') or '').strip().lower()
    genre = str(game.get('genre') or '').strip().lower()
    tags_value = game.get('tags')
    if isinstance(tags_value, (list, tuple, set)):
        tags = ' '.join(str(item).strip().lower() for item in tags_value if str(item).strip())
    else:
        tags = str(tags_value or '').strip().lower()
    short_description = str(game.get('short_description') or '').strip().lower()
    fields = {
        'title': title,
        'genre': genre,
        'tags': tags,
        'short_description': short_description,
    }

    def first_match(keywords: tuple[str, ...]) -> tuple[str, str] | None:
        for keyword in keywords:
            for field_name, field_value in fields.items():
                if keyword in field_value:
                    return keyword, field_name
        return None

    strategy_match = first_match(('strategy', '4x', 'city', 'empire', 'civilization', 'builder'))
    if strategy_match is not None:
        keyword, field_name = strategy_match
        return VISUAL_INTENT_WORLD_SCALE, f'matched "{keyword}" in {field_name}'

    vehicle_match = first_match(('racing', 'car', 'vehicle', 'driving'))
    if vehicle_match is not None:
        keyword, field_name = vehicle_match
        return VISUAL_INTENT_VEHICLE_MOTION, f'matched "{keyword}" in {field_name}'

    activity_match = first_match(('survival', 'crafting', 'diving', 'diver', 'farming', 'sandbox'))
    if activity_match is not None:
        keyword, field_name = activity_match
        return VISUAL_INTENT_ACTIVITY_FOCUS, f'matched "{keyword}" in {field_name}'

    threat_match = first_match(('horror', 'dark', 'monster', 'stealth'))
    if threat_match is not None:
        keyword, field_name = threat_match
        return VISUAL_INTENT_THREAT_ATMOSPHERE, f'matched "{keyword}" in {field_name}'

    return VISUAL_INTENT_HERO_ACTION, 'fallback HERO_ACTION: no visual intent rule matched'


class ComfyUIImageProvider:
    provider_name = 'comfyui'

    def __init__(
        self,
        *,
        enabled: bool = False,
        base_url: str = 'http://127.0.0.1:8188',
        reference_assets_enabled: bool = True,
        checkpoint_name: str | None = None,
        prompt_variant: str = DEFAULT_PROMPT_VARIANT,
        poll_interval_seconds: float = 0.5,
        timeout_seconds: float = 20.0,
        **_: object,
    ) -> None:
        self.enabled = bool(enabled)
        self.base_url = str(base_url or 'http://127.0.0.1:8188').rstrip('/')
        self.reference_assets_enabled = bool(reference_assets_enabled)
        configured_checkpoint = checkpoint_name if checkpoint_name is not None else os.getenv('COMFYUI_CHECKPOINT', 'auto')
        self.checkpoint_name = str(configured_checkpoint or 'auto').strip() or 'auto'
        self.prompt_variant = self._normalize_prompt_variant(prompt_variant)
        self.poll_interval_seconds = max(0.1, float(poll_interval_seconds))
        self.timeout_seconds = max(0.5, float(timeout_seconds))
        self.latest_diagnostics = self._new_runtime_diagnostics()

    @property
    def ai_source_mode(self) -> str:
        return 'reference_assisted' if self.reference_assets_enabled else 'pure_generation'

    @property
    def workflow_mode(self) -> str:
        return 'scene_content_reference_assisted' if self.reference_assets_enabled else 'scene_content_pure'

    def resolve(self, request: ImageResolutionRequest) -> ResolvedImage | None:
        self.latest_diagnostics = self._new_runtime_diagnostics()
        if not self.enabled:
            return None

        generation_contract = self._build_generation_contract(request)
        if self.reference_assets_enabled:
            reference_result = self._resolve_reference_assisted(request, generation_contract)
            if reference_result is not None:
                return reference_result

        return self._resolve_pure_generation(request, generation_contract)

    def _resolve_reference_assisted(
        self,
        request: ImageResolutionRequest,
        generation_contract: dict[str, Any],
    ) -> ResolvedImage | None:
        image_path = self._resolve_local_image_path(request)
        if image_path is None:
            return None
        try:
            image = Image.open(image_path).convert('RGB')
        except OSError:
            return None

        metadata: dict[str, Any] = {
            'selected_source': 'ai',
            'provider_name': self.provider_name,
            'provider': self.provider_name,
            'status': 'success',
            'asset_path': str(image_path.resolve()),
            'reference_asset_path': str(image_path.resolve()),
            'reference_asset_count': 1,
            'reference_assets_used': True,
            'ai_source_mode': 'reference_assisted',
            'generated_image_origin': 'local_reference_asset',
            'workflow_mode': 'scene_content_reference_assisted',
        }
        metadata.update(generation_contract)
        metadata.update(self.latest_diagnostics)
        return ResolvedImage(image=image, metadata=metadata)

    def _resolve_pure_generation(
        self,
        request: ImageResolutionRequest,
        generation_contract: dict[str, Any],
    ) -> ResolvedImage | None:
        diagnostics = self._new_runtime_diagnostics()
        self.latest_diagnostics = diagnostics

        checkpoint_name = self._select_checkpoint(diagnostics)
        if not checkpoint_name:
            self._set_stage(diagnostics, 'submit_prompt', success=False)
            self._mark_stage_failure(
                diagnostics,
                'submit_prompt',
                self._checkpoint_failure_reason(diagnostics),
            )
            return None

        payload = {'prompt': self._workflow(request, generation_contract, checkpoint_name=checkpoint_name)}
        self._capture_submit_request_diagnostics(
            diagnostics,
            path='/prompt',
            payload=payload,
            generation_contract=generation_contract,
        )
        self._set_stage(diagnostics, 'submit_prompt', success=False)
        try:
            prompt_response = self._post_json('/prompt', payload)
        except (OSError, ValueError, urllib.error.URLError, TimeoutError) as exc:
            self._mark_stage_failure(diagnostics, 'submit_prompt', exc)
            return None

        self._set_stage(diagnostics, 'submit_prompt', success=True)
        prompt_id = str(prompt_response.get('prompt_id') or '').strip()
        diagnostics['comfyui_prompt_id'] = prompt_id or None
        if not prompt_id:
            self._mark_stage_failure(diagnostics, 'submit_prompt', 'missing_prompt_id')
            return None

        self._set_stage(diagnostics, 'poll_history', success=False)
        try:
            history = self._poll_history(prompt_id)
        except (OSError, ValueError, urllib.error.URLError, TimeoutError) as exc:
            self._mark_stage_failure(diagnostics, 'poll_history', exc)
            return None
        diagnostics['comfyui_history_found'] = bool(history)
        if not history:
            self._mark_stage_failure(diagnostics, 'poll_history', 'history_not_found')
            return None
        self._set_stage(diagnostics, 'poll_history', success=True)

        self._set_stage(diagnostics, 'extract_image_ref', success=False)
        try:
            image_ref = self._extract_image_reference(history)
        except (OSError, ValueError, urllib.error.URLError, TimeoutError) as exc:
            self._mark_stage_failure(diagnostics, 'extract_image_ref', exc)
            return None
        diagnostics['comfyui_image_ref_found'] = image_ref is not None
        if not image_ref:
            self._mark_stage_failure(diagnostics, 'extract_image_ref', 'image_ref_not_found')
            return None
        self._set_stage(diagnostics, 'extract_image_ref', success=True)

        self._set_stage(diagnostics, 'fetch_image', success=False)
        try:
            image_bytes = self._fetch_image_bytes(image_ref)
            diagnostics['comfyui_image_fetch_ok'] = bool(image_bytes)
            if not image_bytes:
                self._mark_stage_failure(diagnostics, 'fetch_image', 'image_fetch_empty')
                return None
            image = Image.open(io.BytesIO(image_bytes)).convert('RGB')
            asset_path = self._persist_generated_image(request, image)
        except (OSError, ValueError, urllib.error.URLError, TimeoutError) as exc:
            self._mark_stage_failure(diagnostics, 'fetch_image', exc)
            return None
        self._set_stage(diagnostics, 'fetch_image', success=True)

        metadata: dict[str, Any] = {
            'selected_source': 'ai',
            'provider_name': self.provider_name,
            'provider': self.provider_name,
            'status': 'success',
            'asset_path': str(asset_path.resolve()),
            'reference_asset_count': 0,
            'reference_assets_used': False,
            'ai_source_mode': 'pure_generation',
            'generated_image_origin': 'comfyui_runtime',
            'workflow_mode': 'scene_content_pure',
            'prompt_id': prompt_id,
            'comfyui_output': dict(image_ref),
        }
        metadata.update(generation_contract)
        metadata.update(diagnostics)
        return ResolvedImage(image=image, metadata=metadata)

    def _workflow(
        self,
        request: ImageResolutionRequest,
        generation_contract: dict[str, Any],
        *,
        checkpoint_name: str,
    ) -> dict[str, Any]:
        width = max(64, int(request.image_size[0]))
        height = max(64, int(request.image_size[1]))
        positive_prompt = str(generation_contract.get('prompt_summary') or 'scene content image')
        negative_prompt = str(generation_contract.get('negative_prompt_summary') or PROMPT_NEGATIVE_SUMMARY)
        ksampler_seed = int(generation_contract.get('ksampler_seed') or DEFAULT_KSAMPLER_SEED)
        return {
            '3': {
                'class_type': 'KSampler',
                'inputs': {
                    'seed': ksampler_seed,
                    'steps': 20,
                    'cfg': 7,
                    'sampler_name': 'euler',
                    'scheduler': 'normal',
                    'denoise': 1,
                    'model': ['4', 0],
                    'positive': ['6', 0],
                    'negative': ['7', 0],
                    'latent_image': ['5', 0],
                },
            },
            '4': {
                'class_type': 'CheckpointLoaderSimple',
                'inputs': {'ckpt_name': checkpoint_name},
            },
            '5': {
                'class_type': 'EmptyLatentImage',
                'inputs': {'width': width, 'height': height, 'batch_size': 1},
            },
            '6': {
                'class_type': 'CLIPTextEncode',
                'inputs': {
                    'text': positive_prompt,
                    'clip': ['4', 1],
                },
            },
            '7': {
                'class_type': 'CLIPTextEncode',
                'inputs': {
                    'text': negative_prompt,
                    'clip': ['4', 1],
                },
            },
            '8': {
                'class_type': 'VAEDecode',
                'inputs': {'samples': ['3', 0], 'vae': ['4', 2]},
            },
            '9': {
                'class_type': 'SaveImage',
                'inputs': {'images': ['8', 0], 'filename_prefix': 'yoto_ai_scene_content'},
            },
        }

    def _poll_history(self, prompt_id: str) -> dict[str, Any] | None:
        deadline = time.monotonic() + self.timeout_seconds
        path = f'/history/{urllib.parse.quote(prompt_id, safe="")}'
        while time.monotonic() < deadline:
            payload = self._get_json(path)
            if isinstance(payload, dict):
                item = payload.get(prompt_id)
                if isinstance(item, dict) and item.get('outputs'):
                    return item
            time.sleep(self.poll_interval_seconds)
        return None

    def _extract_image_reference(self, history_payload: dict[str, Any]) -> dict[str, str] | None:
        outputs = history_payload.get('outputs')
        if not isinstance(outputs, dict):
            return None
        for node_output in outputs.values():
            if not isinstance(node_output, dict):
                continue
            images = node_output.get('images')
            if not isinstance(images, list):
                continue
            for image_ref in images:
                if not isinstance(image_ref, dict):
                    continue
                filename = str(image_ref.get('filename') or '').strip()
                if not filename:
                    continue
                return {
                    'filename': filename,
                    'subfolder': str(image_ref.get('subfolder') or ''),
                    'type': str(image_ref.get('type') or 'output'),
                }
        return None

    def _fetch_image_bytes(self, image_ref: dict[str, str]) -> bytes | None:
        query = urllib.parse.urlencode(
            {
                'filename': image_ref.get('filename', ''),
                'subfolder': image_ref.get('subfolder', ''),
                'type': image_ref.get('type', 'output'),
            }
        )
        request = urllib.request.Request(f'{self.base_url}/view?{query}', method='GET')
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            data = response.read()
        return data or None

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f'{self.base_url}{path}',
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode('utf-8')
        except urllib.error.HTTPError as exc:
            response_body = exc.read().decode('utf-8', errors='replace')
            setattr(exc, 'comfyui_submit_url', f'{self.base_url}{path}')
            setattr(exc, 'comfyui_http_reason', str(exc.reason or ''))
            setattr(exc, 'comfyui_response_body', response_body)
            setattr(exc, 'comfyui_response_body_excerpt', self._excerpt(response_body))
            raise
        data = json.loads(body or '{}')
        if not isinstance(data, dict):
            raise ValueError('ComfyUI response is not a JSON object.')
        return data

    def _get_json(self, path: str) -> dict[str, Any]:
        request = urllib.request.Request(f'{self.base_url}{path}', method='GET')
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            body = response.read().decode('utf-8')
        data = json.loads(body or '{}')
        if not isinstance(data, dict):
            raise ValueError('ComfyUI response is not a JSON object.')
        return data

    def _persist_generated_image(self, request: ImageResolutionRequest, image: Image.Image) -> Path:
        repo_root = Path(__file__).resolve().parents[4]
        output_dir = repo_root / 'output' / 'cards' / 'comfyui_generated'
        output_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha1(f'{request.slug}|{request.title}|{time.time_ns()}'.encode('utf-8')).hexdigest()[:16]
        filename = f'{request.slug or "scene"}_{digest}.png'
        output_path = output_dir / filename
        image.save(output_path, format='PNG')
        return output_path

    def _resolve_local_image_path(self, request: ImageResolutionRequest) -> Path | None:
        artwork_path = self._resolve_artwork_path(request.artwork_path)
        if artwork_path is not None and not self._path_implies_ui_layout(artwork_path):
            return artwork_path

        repo_root = Path(__file__).resolve().parents[4]
        candidates = [repo_root / relative_path for relative_path in SCENE_REFERENCE_PATHS]
        available = [candidate for candidate in candidates if candidate.exists() and candidate.is_file()]
        if available:
            selector = int(
                hashlib.sha256(str(request.slug or request.title or 'scene').encode('utf-8')).hexdigest(),
                16,
            ) % len(available)
            return available[selector]
        return None

    def _build_generation_contract(self, request: ImageResolutionRequest) -> dict[str, Any]:
        title = str(request.title or 'game world').strip() or 'game world'
        card_type = str(request.card_type or 'scene').strip().lower().replace('_', ' ')
        lane = str(request.lane or '').strip().lower().replace('_', ' ')
        platform = str(request.platform or '').strip().upper()
        lane_clause = f', {lane} mood' if lane else ''
        platform_clause = f', {platform} world context' if platform else ''
        grounding = self._build_grounding_payload(request)
        prompt_variant = self.prompt_variant
        variation = self._build_variation_payload(request)
        seed_contract = self._build_seed_contract(request)
        visual_intent, visual_intent_reason = select_visual_intent(
            {
                'title': request.title,
                'genre': request.genre,
                'tags': request.tags,
                'short_description': request.short_description,
            }
        )
        visual_intent_block = VISUAL_INTENT_PROMPT_BLOCKS[visual_intent]
        visual_intent_negative_block = VISUAL_INTENT_NEGATIVE_BLOCKS[visual_intent]
        visual_intent_clause = f'visual intent {visual_intent.lower()}: {visual_intent_block}; '
        negative_prompt_summary = f'{PROMPT_NEGATIVE_SUMMARY}, {visual_intent_negative_block}'
        variation_clause = f'{variation["prompt_variation"]}; ' if variation['variation_enabled'] else ''
        if prompt_variant == HERO_ACTION_PROMPT_INTENT:
            prompt_intent = HERO_ACTION_PROMPT_INTENT
            prompt_summary = (
                f'{visual_intent_clause}hero action frame for {title}: one dominant foreground subject, clear readable action, '
                f'close or medium-close framing, clear focal hierarchy, strong silhouette, high contrast lighting, '
                f'face-forward or three-quarter character view when a character is present, less fog, less empty background; '
                f'{variation_clause}{grounding["prompt_grounding"]}{lane_clause}{platform_clause}, {card_type} game-world action moment, '
                f'no logos, not UI, no text, no banner, no card layout'
            )
        else:
            prompt_intent = PROMPT_INTENT
            prompt_summary = (
                f'{visual_intent_clause}cinematic keyframe shot for {title}: one dominant subject, one readable action, visible action beat, '
                f'clear main subject, strong foreground focus, foreground/midground/background separation, '
                f'dynamic camera angle, dramatic composition, dramatic lighting, high CTR visual hook; '
                f'{variation_clause}{grounding["prompt_grounding"]}{lane_clause}{platform_clause}, {card_type} game-world moment, '
                f'no logos, not UI, no text, no poster layout'
            )
        return {
            'prompt_variant': prompt_variant,
            'prompt_intent': prompt_intent,
            'prompt_summary': prompt_summary,
            'negative_prompt_summary': negative_prompt_summary,
            'grounding_used': grounding['grounding_used'],
            'grounding_fields_used': grounding['grounding_fields_used'],
            'grounding_summary': grounding['grounding_summary'],
            'visual_intent': visual_intent,
            'visual_intent_reason': visual_intent_reason,
            'variation_enabled': variation['variation_enabled'],
            'variation_id': variation['variation_id'],
            'variation_slots': variation['variation_slots'],
            'variation_camera': variation['variation_camera'],
            'variation_moment': variation['variation_moment'],
            'variation_focus': variation['variation_focus'],
            'variation_composition': variation['variation_composition'],
            'external_seed': seed_contract['external_seed'],
            'ksampler_seed': seed_contract['ksampler_seed'],
            'seed_propagated': seed_contract['seed_propagated'],
        }

    @staticmethod
    def _normalize_prompt_variant(value: object) -> str:
        normalized = str(value or DEFAULT_PROMPT_VARIANT).strip().lower()
        if normalized in VALID_PROMPT_VARIANTS:
            return normalized
        return DEFAULT_PROMPT_VARIANT

    def _build_variation_payload(self, request: ImageResolutionRequest) -> dict[str, Any]:
        game_slug, seed = self._extract_variation_seed_context(getattr(request, 'slug', None))
        if not game_slug or seed is None:
            return {
                'variation_enabled': False,
                'variation_id': None,
                'variation_slots': None,
                'variation_camera': None,
                'variation_moment': None,
                'variation_focus': None,
                'variation_composition': None,
                'prompt_variation': '',
            }

        digest = hashlib.sha1(f'{game_slug}|{self.prompt_variant}|{seed}'.encode('utf-8')).hexdigest()
        indices = [int(digest[offset : offset + 8], 16) for offset in (0, 8, 16, 24)]
        camera = VARIATION_CAMERAS[indices[0] % len(VARIATION_CAMERAS)]
        moment = VARIATION_MOMENTS[indices[1] % len(VARIATION_MOMENTS)]
        focus = VARIATION_FOCUS[indices[2] % len(VARIATION_FOCUS)]
        composition = VARIATION_COMPOSITIONS[indices[3] % len(VARIATION_COMPOSITIONS)]
        variation_slots = {
            'camera': camera,
            'moment': moment,
            'focus': focus,
            'composition': composition,
        }
        return {
            'variation_enabled': True,
            'variation_id': digest[:12],
            'variation_slots': variation_slots,
            'variation_camera': camera,
            'variation_moment': moment,
            'variation_focus': focus,
            'variation_composition': composition,
            'prompt_variation': (
                f'controlled scene variation: {camera} camera, {moment}, focus on {focus}, {composition}'
            ),
        }

    def _build_seed_contract(self, request: ImageResolutionRequest) -> dict[str, Any]:
        _, external_seed = self._extract_variation_seed_context(getattr(request, 'slug', None))
        ksampler_seed = int(external_seed) if external_seed is not None else DEFAULT_KSAMPLER_SEED
        return {
            'external_seed': external_seed,
            'ksampler_seed': ksampler_seed,
            'seed_propagated': external_seed is not None,
        }

    @staticmethod
    def _extract_variation_seed_context(value: object) -> tuple[str | None, int | None]:
        slug = str(value or '').strip().lower()
        if '_seed_' not in slug:
            return None, None
        game_slug, _, seed_text = slug.rpartition('_seed_')
        if not game_slug or not seed_text:
            return None, None
        try:
            seed = int(seed_text)
        except ValueError:
            return None, None
        normalized_game_slug = ''.join(char for char in game_slug if char.isalnum() or char in {'_', '-'})
        return (normalized_game_slug or None), seed

    @classmethod
    def _build_grounding_payload(cls, request: ImageResolutionRequest) -> dict[str, Any]:
        fields_used: list[str] = []
        summary_parts: list[str] = []
        prompt_clauses: list[str] = []

        title = cls._compact_grounding_text(request.title, max_words=10, max_chars=80)
        if title:
            fields_used.append('title')
            summary_parts.append(f'title={title}')
            prompt_clauses.append(f'game-specific title grounding: {title}')

        genre = cls._compact_grounding_text(getattr(request, 'genre', None), max_words=6, max_chars=48)
        if genre:
            fields_used.append('genre')
            summary_parts.append(f'genre={genre}')
            prompt_clauses.append(f'genre and visual style: {genre}')

        tags = cls._compact_grounding_tags(getattr(request, 'tags', None))
        if tags:
            tags_summary = ', '.join(tags)
            fields_used.append('tags')
            summary_parts.append(f'tags={tags_summary}')
            prompt_clauses.append(f'signature tags, action cues, and characteristic objects: {tags_summary}')

        short_description = cls._compact_grounding_text(
            getattr(request, 'short_description', None),
            max_words=20,
            max_chars=180,
        )
        if short_description:
            fields_used.append('short_description')
            summary_parts.append(f'short_description={short_description}')
            prompt_clauses.append(f'key setting, atmosphere, and action framing: {short_description}')

        artwork_cues = cls._extract_artwork_metadata_cues(getattr(request, 'artwork_metadata', None))
        if artwork_cues:
            artwork_summary = ', '.join(artwork_cues)
            fields_used.append('artwork_metadata')
            summary_parts.append(f'artwork_metadata={artwork_summary}')
            prompt_clauses.append(f'artwork metadata cues: {artwork_summary}')

        return {
            'grounding_used': bool(fields_used),
            'grounding_fields_used': fields_used,
            'grounding_summary': ' | '.join(summary_parts) if summary_parts else 'none',
            'prompt_grounding': '; '.join(prompt_clauses) if prompt_clauses else 'game-specific visual grounding',
        }

    @staticmethod
    def _compact_grounding_text(value: object, *, max_words: int, max_chars: int) -> str | None:
        text = ' '.join(str(value or '').replace('\n', ' ').split()).strip()
        if not text:
            return None
        words = text.split()
        if len(words) > max_words:
            text = ' '.join(words[:max_words])
        if len(text) > max_chars:
            text = text[: max_chars - 3].rstrip(' ,;:.') + '...'
        return text or None

    @classmethod
    def _compact_grounding_tags(cls, values: list[str] | None, *, limit: int = 4) -> list[str]:
        if not values:
            return []
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in values:
            text = cls._compact_grounding_text(raw, max_words=4, max_chars=32)
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(text)
            if len(normalized) >= limit:
                break
        return normalized

    @classmethod
    def _extract_artwork_metadata_cues(cls, payload: object, *, limit: int = 5) -> list[str]:
        cues: list[str] = []
        cls._collect_artwork_metadata_cues(payload, cues, limit=limit)
        return cues[:limit]

    @classmethod
    def _collect_artwork_metadata_cues(cls, payload: object, cues: list[str], *, limit: int) -> None:
        if len(cues) >= limit or payload is None:
            return
        if isinstance(payload, dict):
            preferred_keys = (
                'subject',
                'action',
                'setting',
                'environment',
                'mood',
                'atmosphere',
                'visual_style',
                'style',
                'objects',
                'lighting',
                'camera',
                'composition',
            )
            for key in preferred_keys:
                if key in payload:
                    cls._collect_artwork_metadata_cues(payload.get(key), cues, limit=limit)
                    if len(cues) >= limit:
                        return
            for key, value in payload.items():
                if key in preferred_keys:
                    continue
                cls._collect_artwork_metadata_cues(value, cues, limit=limit)
                if len(cues) >= limit:
                    return
            return
        if isinstance(payload, (list, tuple, set)):
            for item in payload:
                cls._collect_artwork_metadata_cues(item, cues, limit=limit)
                if len(cues) >= limit:
                    return
            return
        text = cls._compact_grounding_text(payload, max_words=8, max_chars=72)
        if not text:
            return
        lowered = text.lower()
        if lowered in {item.lower() for item in cues}:
            return
        cues.append(text)

    @staticmethod
    def _path_implies_ui_layout(path: Path) -> bool:
        normalized = str(path).replace('\\', '/').lower()
        return any(token in normalized for token in UI_STYLE_PATH_TOKENS)

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
    def _new_runtime_diagnostics() -> dict[str, Any]:
        return {
            'comfyui_stage': None,
            'comfyui_stage_success': False,
            'comfyui_failure_stage': None,
            'comfyui_failure_reason': None,
            'comfyui_http_status': None,
            'comfyui_http_reason': None,
            'comfyui_prompt_id': None,
            'comfyui_history_found': False,
            'comfyui_image_ref_found': False,
            'comfyui_image_fetch_ok': False,
            'comfyui_response_body': None,
            'comfyui_response_body_excerpt': None,
            'comfyui_submit_url': None,
            'comfyui_request_payload': None,
            'comfyui_request_payload_excerpt': None,
            'comfyui_request_top_level_keys': None,
            'comfyui_request_node_count': None,
            'comfyui_checkpoint_name': None,
            'comfyui_checkpoint_requested': None,
            'comfyui_checkpoint_used': None,
            'comfyui_checkpoint_available': None,
            'comfyui_positive_prompt_summary': None,
            'comfyui_negative_prompt_summary': None,
        }

    @staticmethod
    def _set_stage(diagnostics: dict[str, Any], stage: str, *, success: bool) -> None:
        diagnostics['comfyui_stage'] = stage
        diagnostics['comfyui_stage_success'] = bool(success)
        if success:
            diagnostics['comfyui_failure_stage'] = None
            diagnostics['comfyui_failure_reason'] = None
            diagnostics['comfyui_http_status'] = None
            diagnostics['comfyui_http_reason'] = None
            diagnostics['comfyui_response_body'] = None
            diagnostics['comfyui_response_body_excerpt'] = None

    @classmethod
    def _mark_stage_failure(cls, diagnostics: dict[str, Any], stage: str, error: Exception | str) -> None:
        diagnostics['comfyui_stage'] = stage
        diagnostics['comfyui_stage_success'] = False
        diagnostics['comfyui_failure_stage'] = stage
        diagnostics['comfyui_failure_reason'] = cls._failure_reason(error)
        diagnostics['comfyui_http_status'] = cls._http_status(error)
        diagnostics['comfyui_http_reason'] = cls._http_reason(error)
        diagnostics['comfyui_response_body'] = cls._response_body(error)
        diagnostics['comfyui_response_body_excerpt'] = cls._response_body_excerpt(error)
        submit_url = cls._submit_url(error)
        if submit_url is not None:
            diagnostics['comfyui_submit_url'] = submit_url

    @staticmethod
    def _failure_reason(error: Exception | str) -> str:
        if isinstance(error, str):
            return error
        if isinstance(error, urllib.error.HTTPError):
            excerpt = getattr(error, 'comfyui_response_body_excerpt', None)
            if excerpt:
                return f'http_error:{error.code}:{excerpt}'
            return f'http_error:{error.code}:{error.reason or error.code}'
        if isinstance(error, urllib.error.URLError):
            return f'url_error:{error.reason}'
        if isinstance(error, TimeoutError):
            return f'timeout_error:{error}'
        if isinstance(error, ValueError):
            return f'value_error:{error}'
        if isinstance(error, OSError):
            return f'os_error:{error}'
        return error.__class__.__name__.lower()

    @staticmethod
    def _http_status(error: Exception | str) -> int | None:
        if isinstance(error, urllib.error.HTTPError):
            return int(error.code)
        return None

    @staticmethod
    def _http_reason(error: Exception | str) -> str | None:
        if isinstance(error, str):
            return None
        value = getattr(error, 'comfyui_http_reason', None)
        if value is not None:
            return str(value)
        if isinstance(error, urllib.error.HTTPError):
            return str(error.reason or '') or None
        return None

    @staticmethod
    def _response_body(error: Exception | str) -> str | None:
        if isinstance(error, str):
            return None
        value = getattr(error, 'comfyui_response_body', None)
        if value is None:
            return None
        return str(value)

    @staticmethod
    def _response_body_excerpt(error: Exception | str) -> str | None:
        if isinstance(error, str):
            return None
        value = getattr(error, 'comfyui_response_body_excerpt', None)
        if value is not None:
            return str(value)
        body = ComfyUIImageProvider._response_body(error)
        if body is None:
            return None
        return ComfyUIImageProvider._excerpt(body)

    @staticmethod
    def _submit_url(error: Exception | str) -> str | None:
        if isinstance(error, str):
            return None
        value = getattr(error, 'comfyui_submit_url', None)
        if value is None:
            return None
        return str(value)

    def _capture_submit_request_diagnostics(
        self,
        diagnostics: dict[str, Any],
        *,
        path: str,
        payload: dict[str, Any],
        generation_contract: dict[str, Any],
    ) -> None:
        diagnostics['comfyui_submit_url'] = f'{self.base_url}{path}'
        diagnostics['comfyui_request_payload'] = payload
        diagnostics['comfyui_request_payload_excerpt'] = self._excerpt(
            json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
        )
        diagnostics['comfyui_request_top_level_keys'] = sorted(str(key) for key in payload.keys())
        prompt_payload = payload.get('prompt')
        diagnostics['comfyui_request_node_count'] = len(prompt_payload) if isinstance(prompt_payload, dict) else None
        diagnostics['comfyui_checkpoint_name'] = self._extract_checkpoint_name(prompt_payload)
        diagnostics['comfyui_positive_prompt_summary'] = str(generation_contract.get('prompt_summary') or '') or None
        diagnostics['comfyui_negative_prompt_summary'] = str(generation_contract.get('negative_prompt_summary') or '') or None
        diagnostics['external_seed'] = generation_contract.get('external_seed')
        diagnostics['ksampler_seed'] = self._extract_ksampler_seed(prompt_payload)
        diagnostics['seed_propagated'] = bool(generation_contract.get('seed_propagated', False))

    def _select_checkpoint(self, diagnostics: dict[str, Any]) -> str | None:
        requested = self.checkpoint_name
        diagnostics['comfyui_checkpoint_requested'] = requested
        if requested.lower() == 'auto':
            available = self._available_checkpoints()
            if available is None:
                diagnostics['comfyui_checkpoint_available'] = None
                diagnostics['comfyui_checkpoint_used'] = None
                return None
            if not available:
                diagnostics['comfyui_checkpoint_available'] = False
                diagnostics['comfyui_checkpoint_used'] = None
                return None
            diagnostics['comfyui_checkpoint_available'] = True
            diagnostics['comfyui_checkpoint_used'] = available[0]
            return available[0]

        available = self._available_checkpoints()
        diagnostics['comfyui_checkpoint_used'] = requested
        if available is None:
            diagnostics['comfyui_checkpoint_available'] = None
            return requested
        is_available = requested in available
        diagnostics['comfyui_checkpoint_available'] = is_available
        if is_available:
            return requested
        return None

    def _available_checkpoints(self) -> list[str] | None:
        try:
            payload = self._get_json('/object_info/CheckpointLoaderSimple')
        except (OSError, ValueError, urllib.error.URLError, TimeoutError):
            return None
        if not isinstance(payload, dict):
            return None
        root = payload.get('CheckpointLoaderSimple')
        if not isinstance(root, dict):
            return None
        input_payload = root.get('input')
        if not isinstance(input_payload, dict):
            return None
        required_payload = input_payload.get('required')
        if not isinstance(required_payload, dict):
            return None
        ckpt_payload = required_payload.get('ckpt_name')
        if not isinstance(ckpt_payload, list) or not ckpt_payload:
            return None
        options = ckpt_payload[0]
        if not isinstance(options, list):
            return None
        return [str(item).strip() for item in options if str(item).strip()]

    @staticmethod
    def _checkpoint_failure_reason(diagnostics: dict[str, Any]) -> str:
        requested = str(diagnostics.get('comfyui_checkpoint_requested') or 'auto')
        available = diagnostics.get('comfyui_checkpoint_available')
        if requested.lower() == 'auto':
            if available is False:
                return 'no_runtime_checkpoints_available'
            return 'checkpoint_discovery_failed'
        if available is False:
            return f'configured_checkpoint_missing_in_runtime:{requested}'
        return f'checkpoint_unavailable:{requested}'

    @staticmethod
    def _extract_checkpoint_name(prompt_payload: object) -> str | None:
        if not isinstance(prompt_payload, dict):
            return None
        for node_payload in prompt_payload.values():
            if not isinstance(node_payload, dict):
                continue
            inputs = node_payload.get('inputs')
            if not isinstance(inputs, dict):
                continue
            value = inputs.get('ckpt_name')
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None

    @staticmethod
    def _extract_ksampler_seed(prompt_payload: object) -> int | None:
        if not isinstance(prompt_payload, dict):
            return None
        sampler_payload = prompt_payload.get('3')
        if not isinstance(sampler_payload, dict):
            return None
        inputs = sampler_payload.get('inputs')
        if not isinstance(inputs, dict):
            return None
        value = inputs.get('seed')
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _excerpt(value: str, *, limit: int = 1200) -> str:
        if len(value) <= limit:
            return value
        return value[:limit] + '...<truncated>'
