from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from domain.entities.offer import Offer
from domain.entities.post_artifact import PostArtifact
from infrastructure.clients.base_http import ResilientHttpClient
from infrastructure.telegram.caption_builder import TelegramCaptionBuilder


@dataclass(slots=True)
class RenderResult:
    artifact: PostArtifact
    image_path: Path


class SupportsCardRender(Protocol):
    async def render(self, http: ResilientHttpClient, offer: Offer, template_id: str): ...


class DryRunRenderUseCase:
    def __init__(
        self,
        caption_builder: TelegramCaptionBuilder,
        renderer: SupportsCardRender,
        http: ResilientHttpClient,
    ) -> None:
        self.caption_builder = caption_builder
        self.renderer = renderer
        self.http = http

    async def execute(self, offer: Offer, decision_json: dict) -> RenderResult:
        caption_html, hashtags = self.caption_builder.build(offer, decision_json)
        template_id = decision_json['template_id']
        render_result = await self.renderer.render(self.http, offer, template_id)
        image_path = render_result.image_path
        caption_hash = hashlib.sha256(caption_html.encode('utf-8')).hexdigest()
        image_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()
        identity_basis = '|'.join(
            [
                offer.offer_id,
                decision_json['lane'],
                str(offer.price_after_minor),
                str(offer.discount_percent),
                offer.promo_end.isoformat() if offer.promo_end else 'no_end',
            ]
        )
        idempotency_key = hashlib.sha256(identity_basis.encode('utf-8')).hexdigest()
        decision_debug = dict(decision_json.get('debug') or {})
        caption_debug = self.caption_builder.last_debug_snapshot()
        if caption_debug:
            decision_debug['caption'] = caption_debug
        artifact = PostArtifact(
            offer_id=offer.offer_id,
            caption_html=caption_html,
            hashtags=hashtags,
            template_id=template_id,
            render_inputs={
                'offer': offer.to_snapshot(),
                'decision': decision_json,
            },
            assets_used=render_result.assets_used,
            idempotency_key=idempotency_key,
            caption_hash=caption_hash,
            image_hash=image_hash,
            render_diagnostics=render_result.diagnostics.to_snapshot(),
            decision_debug=decision_debug,
        )
        return RenderResult(artifact=artifact, image_path=image_path)
