from __future__ import annotations

from .entities import VideoManifest, VideoTemplate


class TemplateSelector:
    def select(self, manifest: VideoManifest) -> VideoTemplate:
        if self._is_roundup_digest(manifest):
            return VideoTemplate(
                name='roundup_digest',
                background_top=(56, 44, 20),
                background_bottom=(20, 14, 8),
                accent=(255, 208, 122),
                panel=(38, 27, 15, 224),
                badge=(255, 208, 122),
                cta=(255, 232, 184),
            )
        if manifest.template_hint == 'freebie-flash' or self._content_type(manifest) == 'freebie':
            return VideoTemplate(
                name='freebie_flash',
                background_top=(22, 54, 64),
                background_bottom=(5, 18, 28),
                accent=(114, 232, 180),
                panel=(9, 33, 39, 220),
                badge=(114, 232, 180),
                cta=(255, 214, 10),
            )
        if manifest.template_hint == 'event-countdown' or self._content_type(manifest) == 'event':
            return VideoTemplate(
                name='event_countdown',
                background_top=(74, 40, 99),
                background_bottom=(24, 10, 38),
                accent=(246, 161, 80),
                panel=(36, 18, 52, 220),
                badge=(246, 161, 80),
                cta=(255, 222, 160),
            )
        if manifest.template_hint in {'deadline-push', 'final-push'} or str(manifest.context.get('lane') or '').strip().lower() == 'final_push':
            return VideoTemplate(
                name='deadline_push',
                background_top=(97, 22, 30),
                background_bottom=(24, 5, 9),
                accent=(255, 102, 102),
                panel=(44, 8, 12, 220),
                badge=(255, 178, 102),
                cta=(255, 230, 153),
            )
        return VideoTemplate(
            name='deal_spotlight',
            background_top=(18, 52, 88),
            background_bottom=(6, 18, 34),
            accent=(115, 181, 255),
            panel=(8, 23, 44, 220),
            badge=(115, 181, 255),
            cta=(255, 217, 102),
        )

    @staticmethod
    def _content_type(manifest: VideoManifest) -> str:
        return str(manifest.context.get('content_type') or '').strip().lower()

    @classmethod
    def _is_roundup_digest(cls, manifest: VideoManifest) -> bool:
        template_hint = str(manifest.template_hint or '').strip().lower().replace('-', '_')
        template_id = str(manifest.context.get('template_id') or '').strip().lower()
        intent = str(manifest.context.get('video_template_intent') or '').strip().lower()
        lane = str(manifest.context.get('lane') or '').strip().lower()
        return (
            template_hint == 'roundup_digest'
            or template_id == 'roundup_digest'
            or intent == 'roundup_digest'
            or lane == 'roundup_digest'
        )
