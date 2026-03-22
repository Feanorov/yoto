from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import html
import re
from typing import Any

from dealbot.utils.ua import clean_html_text, contains_cyrillic, format_deadline, format_price_uah

from .entities import PlannedScene, RenderedScene, VideoManifest


@dataclass(slots=True, frozen=True)
class VoiceSceneDraft:
    scene_id: str
    position: int
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    visual_role: str
    visual_source_role: str
    visual_source_path: str | None
    headline: str
    body: str
    cta: str | None
    narration_text: str
    transition_note: str
    preview_image_path: str | None
    estimated_read_seconds: float
    timing_warning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            'scene_id': self.scene_id,
            'position': self.position,
            'start_seconds': round(self.start_seconds, 2),
            'end_seconds': round(self.end_seconds, 2),
            'duration_seconds': round(self.duration_seconds, 2),
            'visual_role': self.visual_role,
            'visual_source': {
                'role': self.visual_source_role,
                'path': self.visual_source_path,
            },
            'on_screen_text': {
                'headline': self.headline,
                'body': self.body,
                'cta': self.cta,
            },
            'narration_text': self.narration_text,
            'transition_note': self.transition_note,
            'preview_image_path': self.preview_image_path,
            'estimated_read_seconds': round(self.estimated_read_seconds, 2),
            'timing_warning': self.timing_warning,
        }


@dataclass(slots=True, frozen=True)
class VoiceReadyDraft:
    family: str
    title: str
    hook: str
    clean_script: str
    timed_script: str
    warnings: tuple[str, ...]
    scenes: tuple[VoiceSceneDraft, ...]


class VoiceScriptBuilder:
    WORDS_PER_SECOND = 2.6
    CLAUSE_SPLIT_RE = re.compile(r'(?<=[.!?;:])\s+|,\s+')
    SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+')
    TRADEMARK_RE = re.compile(r'[\u00ae\u2122\u00a9]')
    EDITION_SUFFIX_RE = re.compile(
        r'\b(?:deluxe|ultimate|complete|collection|edition|bundle|pack|founder|celebration)\b',
        re.IGNORECASE,
    )
    HASH_RE = re.compile(r'#\w+')
    PERCENT_RE = re.compile(r'(\d{1,3})%')
    STRIP_SPACING_RE = re.compile(r'\s+')

    def build(
        self,
        manifest: VideoManifest,
        payload: dict[str, Any],
        planned_scenes: tuple[PlannedScene, ...],
        rendered_scenes: tuple[RenderedScene, ...],
    ) -> VoiceReadyDraft:
        facts = self._facts(manifest, payload)
        lines, warnings = self._scene_lines(facts, planned_scenes)
        scene_drafts: list[VoiceSceneDraft] = []
        elapsed = 0.0
        warning_list = list(warnings)
        for index, planned in enumerate(planned_scenes):
            rendered = rendered_scenes[index] if index < len(rendered_scenes) else None
            narration_text = lines[index] if index < len(lines) else self._fallback_scene_line(planned, facts)
            narration_text = self._fit_to_duration(narration_text, planned.duration_seconds)
            estimated = self._estimate_read_seconds(narration_text)
            timing_warning = None
            if estimated > planned.duration_seconds + 0.6:
                timing_warning = 'trim_recommended'
                warning_list.append(f'scene_{planned.position:02d}_voiceover_over_budget')

            visual_source_role, visual_source_path = self._visual_source(payload, planned.scene_id, rendered)
            scene_drafts.append(
                VoiceSceneDraft(
                    scene_id=planned.scene_id,
                    position=planned.position,
                    start_seconds=elapsed,
                    end_seconds=elapsed + planned.duration_seconds,
                    duration_seconds=planned.duration_seconds,
                    visual_role=planned.visual_role,
                    visual_source_role=visual_source_role,
                    visual_source_path=visual_source_path,
                    headline=planned.headline,
                    body=planned.body,
                    cta=planned.cta,
                    narration_text=narration_text,
                    transition_note=self._transition_note(planned.position, len(planned_scenes)),
                    preview_image_path=str(rendered.image_path) if rendered is not None else None,
                    estimated_read_seconds=estimated,
                    timing_warning=timing_warning,
                )
            )
            elapsed += planned.duration_seconds

        clean_script = '\n\n'.join(scene.narration_text for scene in scene_drafts if scene.narration_text)
        timed_script = '\n\n'.join(
            self._timed_scene_block(scene)
            for scene in scene_drafts
        )
        return VoiceReadyDraft(
            family=str(facts['family']),
            title=str(facts['title']),
            hook=scene_drafts[0].narration_text if scene_drafts else '',
            clean_script=clean_script,
            timed_script=timed_script,
            warnings=tuple(dict.fromkeys(warning_list)),
            scenes=tuple(scene_drafts),
        )

    def _facts(self, manifest: VideoManifest, payload: dict[str, Any]) -> dict[str, Any]:
        voice_facts = dict(payload.get('voice_facts') or {})
        caption_paragraphs = self._caption_paragraphs(str(payload.get('caption_html') or ''))
        roundup_items = tuple(
            item
            for item in (payload.get('roundup_items') or [])
            if isinstance(item, dict)
        )
        return {
            'family': self._family(manifest, payload),
            'title': self._sanitize_title(str(voice_facts.get('title') or payload.get('short_title') or manifest.short_title or manifest.offer_id)),
            'short_title': self._sanitize_title(str(payload.get('short_title') or manifest.short_title or voice_facts.get('title') or manifest.offer_id)),
            'store': clean_html_text(str(manifest.context.get('store') or '')),
            'hook_line': clean_html_text(str(payload.get('hook_line') or manifest.hook_line or '')),
            'summary_line': clean_html_text(str(payload.get('summary_line') or manifest.summary_line or '')),
            'urgency_line': clean_html_text(str(payload.get('urgency_line') or manifest.urgency_line or '')),
            'cta_line': clean_html_text(str(payload.get('cta_line') or payload.get('urgency_line') or manifest.urgency_line or '')),
            'caption_paragraphs': caption_paragraphs,
            'price_before_minor': self._int_or_none(voice_facts.get('price_before_minor')),
            'price_after_minor': self._int_or_none(voice_facts.get('price_after_minor')),
            'currency': str(voice_facts.get('currency') or 'UAH'),
            'discount_percent': self._int_or_none(voice_facts.get('discount_percent')),
            'promo_end': self._parse_datetime(voice_facts.get('promo_end')),
            'access_type': self._freebie_access_type(manifest, payload, voice_facts, caption_paragraphs),
            'roundup_items': roundup_items,
            'voice_facts_present': bool(voice_facts),
            'source_artifact_image': self._payload_path(payload, 'source_artifact', 'image_path'),
            'asset_card_image': self._payload_path(payload, 'asset_refs', 'card_image'),
            'asset_game_image': self._payload_path(payload, 'asset_refs', 'game_image'),
            'asset_background': self._payload_path(payload, 'asset_refs', 'background'),
        }

    def _scene_lines(self, facts: dict[str, Any], planned_scenes: tuple[PlannedScene, ...]) -> tuple[list[str], list[str]]:
        warnings: list[str] = []
        if not bool(facts.get('voice_facts_present')):
            warnings.append('voice_facts_missing_used_manifest_fallbacks')

        family = str(facts['family'])
        if family == 'FREE_GAME':
            lines, family_warnings = self._free_game_lines(facts)
        elif family == 'FESTIVAL':
            lines, family_warnings = self._festival_lines(facts)
        elif family == 'TOP_LIST':
            lines, family_warnings = self._top_list_lines(facts)
        else:
            lines, family_warnings = self._discount_lines(facts)
        warnings.extend(family_warnings)

        if len(lines) < len(planned_scenes):
            for planned in planned_scenes[len(lines):]:
                lines.append(self._fallback_scene_line(planned, facts))
        elif len(lines) > len(planned_scenes):
            lines = lines[: len(planned_scenes)]
        return lines, warnings

    def _discount_lines(self, facts: dict[str, Any]) -> tuple[list[str], list[str]]:
        warnings: list[str] = []
        title = str(facts['short_title'] or facts['title'])
        discount_percent = facts.get('discount_percent') or self._percent_from_text(str(facts['hook_line']))
        if discount_percent:
            hook = f"{title}: \u0437\u043d\u0438\u0436\u043a\u0430 {discount_percent}%."
        elif self._is_ukrainian_line(str(facts['hook_line'])):
            hook = self._prepend_title(title, str(facts['hook_line']))
        else:
            hook = f"\u0417\u043d\u0438\u0436\u043a\u0430 \u043d\u0430 {title}."
            warnings.append('discount_hook_used_generic_fallback')

        value = self._discount_value_line(facts)
        if value.startswith('\u0426\u0456\u043d\u0430 \u0432\u0436\u0435'):
            warnings.append('discount_value_used_generic_fallback')
        cta = self._discount_cta_line(facts)
        return [hook, value, cta], warnings

    def _free_game_lines(self, facts: dict[str, Any]) -> tuple[list[str], list[str]]:
        warnings: list[str] = []
        title = str(facts['short_title'] or facts['title'])
        store_short = self._store_short_name(str(facts['store']))
        hook = f"{title} \u0431\u0435\u0437\u043a\u043e\u0448\u0442\u043e\u0432\u043d\u043e \u0432 {store_short}."
        access_type = str(facts.get('access_type') or '')
        if access_type == 'temporary_access':
            value = '\u0426\u0435 \u0442\u0438\u043c\u0447\u0430\u0441\u043e\u0432\u0438\u0439 \u0434\u043e\u0441\u0442\u0443\u043f, \u043d\u0435 \u043f\u043e\u0441\u0442\u0456\u0439\u043d\u0430 \u0440\u043e\u0437\u0434\u0430\u0447\u0430.'
        elif access_type == 'keep_forever':
            value = '\u0414\u043e\u0434\u0430\u0454\u0448 \u043d\u0430 \u0430\u043a\u0430\u0443\u043d\u0442 \u0431\u0435\u0437 \u043e\u043f\u043b\u0430\u0442\u0438, \u0456 \u0433\u0440\u0430 \u043b\u0438\u0448\u0430\u0454\u0442\u044c\u0441\u044f \u043d\u0430\u0437\u0430\u0432\u0436\u0434\u0438.'
        else:
            value = self._supporting_line(facts)
            warnings.append('free_game_access_type_inferred_from_sparse_inputs')
        cta = self._free_game_cta_line(facts)
        return [hook, value, cta], warnings

    def _festival_lines(self, facts: dict[str, Any]) -> tuple[list[str], list[str]]:
        warnings: list[str] = []
        title = self._event_title(str(facts['title']))
        store_short = self._store_short_name(str(facts['store']))
        if store_short and store_short.lower() not in title.lower():
            hook = f"{title} \u0441\u0442\u0430\u0440\u0442\u0443\u0432 \u0443 {store_short}."
        else:
            hook = f"{title} \u0441\u0442\u0430\u0440\u0442\u0443\u0432."
        summary_line = self._supporting_line(facts)
        if summary_line == '\u041f\u0435\u0440\u0435\u0433\u043b\u044f\u043d\u044c \u043f\u043e\u0434\u0456\u044e \u0437\u0430\u0440\u0430\u0437, \u0442\u0443\u0442 \u0454 \u0449\u043e \u0432\u0456\u0434\u043a\u0440\u0438\u0442\u0438.':
            warnings.append('festival_summary_used_generic_fallback')
        cta = self._festival_cta_line(facts)
        return [hook, summary_line, cta], warnings

    def _top_list_lines(self, facts: dict[str, Any]) -> tuple[list[str], list[str]]:
        warnings: list[str] = []
        items = list(facts.get('roundup_items') or [])
        hook = '\u041a\u043e\u0440\u043e\u0442\u043a\u0430 \u0434\u043e\u0431\u0456\u0440\u043a\u0430 \u0441\u0438\u043b\u044c\u043d\u0438\u0445 \u0437\u043d\u0438\u0436\u043e\u043a.'
        page_one = self._roundup_page_line(items[:2])
        page_two = self._roundup_page_line(items[2:4], extra_item=items[4] if len(items) > 4 else None)
        if not page_one:
            page_one = self._supporting_line(facts)
            warnings.append('top_list_page_one_used_summary_fallback')
        if not page_two:
            page_two = self._compress_clause(str(facts['summary_line']) or str(facts['urgency_line']))
            warnings.append('top_list_page_two_used_summary_fallback')
        cta = self._top_list_cta_line(facts)
        return [hook, page_one, page_two, cta], warnings

    def _supporting_line(self, facts: dict[str, Any]) -> str:
        summary = self._clean_for_speech(str(facts['summary_line']))
        if self._is_ukrainian_line(summary):
            return self._compress_clause(self._strip_title_prefix(summary, str(facts['title'])))

        for paragraph in facts.get('caption_paragraphs') or ():
            if self._is_ukrainian_line(paragraph) and '\u0433\u0440\u043d' not in paragraph and paragraph != facts['urgency_line']:
                return self._compress_clause(self._strip_title_prefix(paragraph, str(facts['title'])))

        if str(facts['family']) == 'FESTIVAL':
            return '\u041f\u0435\u0440\u0435\u0433\u043b\u044f\u043d\u044c \u043f\u043e\u0434\u0456\u044e \u0437\u0430\u0440\u0430\u0437, \u0442\u0443\u0442 \u0454 \u0449\u043e \u0432\u0456\u0434\u043a\u0440\u0438\u0442\u0438.'
        return '\u0426\u0456\u043d\u0430 \u0432\u0436\u0435 \u0432\u0438\u0433\u043b\u044f\u0434\u0430\u0454 \u0434\u043e\u0441\u0438\u0442\u044c \u0441\u0438\u043b\u044c\u043d\u043e, \u0449\u043e\u0431 \u043f\u0440\u0438\u0434\u0438\u0432\u0438\u0442\u0438\u0441\u044f.'

    def _discount_value_line(self, facts: dict[str, Any]) -> str:
        price_before_minor = facts.get('price_before_minor')
        price_after_minor = facts.get('price_after_minor')
        if isinstance(price_after_minor, int) and isinstance(price_before_minor, int) and price_before_minor > price_after_minor:
            after_price = format_price_uah(price_after_minor / 100)
            before_price = format_price_uah(price_before_minor / 100)
            return f"\u0417\u0430\u0440\u0430\u0437 {after_price} \u0437\u0430\u043c\u0456\u0441\u0442\u044c {before_price}."

        price_line = self._first_matching_paragraph(
            facts,
            lambda paragraph: '\u0433\u0440\u043d' in paragraph or '%' in paragraph,
        )
        if price_line:
            return self._compress_clause(price_line)
        return self._supporting_line(facts)

    def _discount_cta_line(self, facts: dict[str, Any]) -> str:
        return self._cta_with_post_link(facts, default='\u041f\u043e\u0441\u0438\u043b\u0430\u043d\u043d\u044f \u0432 \u043f\u043e\u0441\u0442\u0456, \u0434\u0438\u0432\u0438\u0441\u044c \u043f\u043e\u043a\u0438 \u0446\u0456\u043d\u0430 \u0430\u043a\u0442\u0438\u0432\u043d\u0430.')

    def _free_game_cta_line(self, facts: dict[str, Any]) -> str:
        deadline = self._deadline_phrase(facts)
        if deadline:
            lowered = deadline.lower()
            if any(token in lowered for token in ('\u0437\u0430\u0431\u0440\u0430\u0442\u0438', '\u0434\u043e\u0434\u0430\u0442\u0438', '\u043c\u043e\u0436\u043d\u0430 \u0434\u043e')):
                line = self._end_sentence(deadline)
                if '\u043f\u043e\u0441\u0442' in line.lower():
                    return line
                return f"{line} \u041f\u043e\u0441\u0438\u043b\u0430\u043d\u043d\u044f \u0432 \u043f\u043e\u0441\u0442\u0456."
            return f"\u0417\u0430\u0431\u0440\u0430\u0442\u0438 \u0432\u0430\u0440\u0442\u043e \u0434\u043e {deadline}. \u041f\u043e\u0441\u0438\u043b\u0430\u043d\u043d\u044f \u0432 \u043f\u043e\u0441\u0442\u0456."
        return self._cta_with_post_link(facts, default='\u041f\u043e\u0441\u0438\u043b\u0430\u043d\u043d\u044f \u0432 \u043f\u043e\u0441\u0442\u0456. \u0417\u0430\u0431\u0438\u0440\u0430\u0439, \u043f\u043e\u043a\u0438 \u0440\u043e\u0437\u0434\u0430\u0447\u0430 \u0430\u043a\u0442\u0438\u0432\u043d\u0430.')

    def _festival_cta_line(self, facts: dict[str, Any]) -> str:
        return self._cta_with_post_link(facts, default='\u041f\u0435\u0440\u0435\u0433\u043b\u044f\u043d\u044c \u043f\u043e\u0434\u0456\u044e \u0437\u0430\u0440\u0430\u0437 \u0456 \u0432\u0456\u0434\u0431\u0435\u0440\u0438, \u0449\u043e \u0437\u0430\u0439\u0448\u043b\u043e.')

    def _top_list_cta_line(self, facts: dict[str, Any]) -> str:
        return self._cta_with_post_link(facts, default='\u041f\u043e\u0432\u043d\u0430 \u0434\u043e\u0431\u0456\u0440\u043a\u0430 \u0432 \u043f\u043e\u0441\u0442\u0456. \u0414\u0438\u0432\u0438\u0441\u044c, \u043f\u043e\u043a\u0438 \u0446\u0456 \u043f\u0440\u043e\u043f\u043e\u0437\u0438\u0446\u0456\u0457 \u0449\u0435 \u0436\u0438\u0432\u0456.')

    def _event_title(self, value: str) -> str:
        cleaned = self._sanitize_title(value)
        cleaned = re.sub(r'\bis on now!?$', '', cleaned, flags=re.IGNORECASE).strip(' !.-')
        return cleaned or self._sanitize_title(value)

    def _roundup_page_line(self, items: list[dict[str, Any]], extra_item: dict[str, Any] | None = None) -> str:
        phrases = [
            self._roundup_item_phrase(item)
            for item in items
            if self._roundup_item_phrase(item)
        ]
        if not phrases:
            return ''
        if len(phrases) == 1:
            line = f"{phrases[0]}."
        else:
            line = f"{phrases[0]}, \u0430 {phrases[1]}."
        if extra_item is not None:
            extra_phrase = self._roundup_item_phrase(extra_item)
            if extra_phrase:
                line = f"{line} \u0406 \u0449\u0435 {extra_phrase}."
        return line

    def _roundup_item_phrase(self, item: dict[str, Any]) -> str:
        title = self._compact_title(str(item.get('title') or ''))
        if not title:
            return ''
        discount_percent = self._int_or_none(item.get('discount_percent'))
        price_after_minor = self._int_or_none(item.get('price_after_minor'))
        offer_kind = str(item.get('offer_kind') or '').strip().lower()
        if discount_percent and discount_percent > 0:
            return f"{title} \u0437 \u043c\u0456\u043d\u0443\u0441 {discount_percent}%"
        if offer_kind == 'freebie' or price_after_minor == 0:
            return f"{title} \u0431\u0435\u0437\u043a\u043e\u0448\u0442\u043e\u0432\u043d\u043e"
        if isinstance(price_after_minor, int) and price_after_minor > 0:
            return f"{title} \u0437\u0430 {format_price_uah(price_after_minor / 100)}"
        return title

    def _freebie_access_type(
        self,
        manifest: VideoManifest,
        payload: dict[str, Any],
        voice_facts: dict[str, Any],
        caption_paragraphs: tuple[str, ...],
    ) -> str | None:
        explicit = str(voice_facts.get('free_access_type') or '').strip().lower()
        if explicit in {'keep_forever', 'temporary_access'}:
            return explicit

        store = str(manifest.context.get('store') or '').strip().lower()
        if store == 'epic games store':
            return 'keep_forever'

        normalized = ' '.join(paragraph.lower() for paragraph in caption_paragraphs)
        if '\u043d\u0430\u0437\u0430\u0432\u0436\u0434\u0438' in normalized:
            return 'keep_forever'
        if any(token in normalized for token in ('free weekend', 'free play', '\u0442\u0438\u043c\u0447\u0430\u0441\u043e\u0432', 'trial')):
            return 'temporary_access'

        content_type = str(payload.get('content_type') or '').strip().lower()
        if content_type == 'freebie':
            return 'keep_forever'
        return None

    @staticmethod
    def _family(manifest: VideoManifest, payload: dict[str, Any]) -> str:
        content_type = str(payload.get('content_type') or manifest.context.get('content_type') or '').strip().lower()
        template_id = str(manifest.context.get('template_id') or '').strip().lower()
        lane = str(manifest.context.get('lane') or '').strip().lower()
        offer_kind = str(manifest.context.get('offer_kind') or '').strip().lower()
        if content_type == 'roundup' or template_id == 'roundup_digest' or lane == 'roundup_digest':
            return 'TOP_LIST'
        if content_type == 'freebie' or offer_kind == 'freebie' or manifest.template_hint == 'freebie-flash':
            return 'FREE_GAME'
        if content_type == 'event' or offer_kind in {'event', 'festival'} or manifest.template_hint == 'event-countdown':
            return 'FESTIVAL'
        return 'DISCOUNT'

    def _caption_paragraphs(self, caption_html: str) -> tuple[str, ...]:
        if not caption_html.strip():
            return tuple()
        text = re.sub(r'<br\s*/?>', '\n', caption_html, flags=re.IGNORECASE)
        text = re.sub(r'</(?:p|div|li)>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<li[^>]*>', '- ', text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '', text)
        text = html.unescape(text)
        paragraphs: list[str] = []
        for raw_paragraph in re.split(r'\n\s*\n|\n', text):
            cleaned = self._clean_for_speech(raw_paragraph)
            if not cleaned:
                continue
            if self._hashtags_only(cleaned):
                continue
            paragraphs.append(cleaned)
        return tuple(paragraphs)

    def _cta_with_post_link(self, facts: dict[str, Any], *, default: str) -> str:
        for candidate in (str(facts['cta_line']), str(facts['urgency_line'])):
            cleaned = self._clean_for_speech(candidate)
            if not self._is_ukrainian_line(cleaned):
                continue
            line = self._compress_clause(cleaned)
            if '\u043f\u043e\u0441\u0442' not in line.lower():
                return f"{line} \u041f\u043e\u0441\u0438\u043b\u0430\u043d\u043d\u044f \u0432 \u043f\u043e\u0441\u0442\u0456."
            return line
        return default

    def _deadline_phrase(self, facts: dict[str, Any]) -> str | None:
        promo_end = facts.get('promo_end')
        if isinstance(promo_end, datetime):
            return format_deadline(promo_end)
        urgency_line = self._clean_for_speech(str(facts['urgency_line']))
        if self._is_ukrainian_line(urgency_line):
            return self._compress_clause(urgency_line).rstrip('.')
        return None

    def _fallback_scene_line(self, planned: PlannedScene, facts: dict[str, Any]) -> str:
        voiceover_text = self._clean_for_speech(planned.voiceover_text)
        if voiceover_text:
            return self._compress_clause(voiceover_text)
        return self._supporting_line(facts)

    def _fit_to_duration(self, text: str, duration_seconds: float) -> str:
        cleaned = self._end_sentence(self._clean_for_speech(text))
        if not cleaned:
            return cleaned
        words = cleaned.split()
        target_words = max(8, int(duration_seconds * self.WORDS_PER_SECOND) + 2)
        if len(words) <= target_words:
            return cleaned

        clauses = [self._clean_for_speech(part) for part in self.CLAUSE_SPLIT_RE.split(cleaned) if self._clean_for_speech(part)]
        selected: list[str] = []
        selected_words = 0
        for clause in clauses:
            clause_words = len(clause.split())
            if selected and selected_words + clause_words > target_words:
                break
            if clause_words > target_words and not selected:
                break
            selected.append(clause)
            selected_words += clause_words
            if selected_words >= target_words:
                break
        if selected:
            return self._end_sentence(' '.join(selected))
        trimmed_words = words[:target_words]
        if len(trimmed_words) < len(words) and trimmed_words[-1].lower() in {'в', 'у', 'на', 'до', 'з', 'і', 'й', 'та'}:
            trimmed_words = trimmed_words[:-1]
        trimmed = ' '.join(trimmed_words).rstrip(' ,.;:-')
        return self._end_sentence(trimmed)

    def _estimate_read_seconds(self, text: str) -> float:
        words = len(self._clean_for_speech(text).split())
        return 0.0 if words == 0 else words / self.WORDS_PER_SECOND

    def _timed_scene_block(self, scene: VoiceSceneDraft) -> str:
        return (
            f"SCENE {scene.position:02d} / {scene.start_seconds:.1f}-{scene.end_seconds:.1f}\n"
            f"\"{scene.narration_text}\""
        )

    def _transition_note(self, position: int, total: int) -> str:
        if position == 1:
            return '\u0411\u0435\u0437 \u043f\u0430\u0443\u0437\u0438 \u0432\u0456\u0434\u043a\u0440\u0438\u0442\u0438 \u0437 \u0445\u0443\u043a\u0430.'
        if position == total:
            return '\u0424\u0456\u043d\u0430\u043b\u044c\u043d\u0438\u0439 CTA, \u0434\u0430\u0442\u0438 \u043a\u043e\u0440\u043e\u0442\u043a\u0443 \u0443\u0442\u0440\u0438\u043c\u043a\u0443 \u043f\u0435\u0440\u0435\u0434 \u0432\u0438\u0445\u043e\u0434\u043e\u043c.'
        return '\u0428\u0432\u0438\u0434\u043a\u0438\u0439 \u0436\u043e\u0440\u0441\u0442\u043a\u0438\u0439 \u043f\u0435\u0440\u0435\u0445\u0456\u0434 \u0432 \u043d\u0430\u0441\u0442\u0443\u043f\u043d\u0438\u0439 \u0431\u0456\u0442.'

    def _visual_source(
        self,
        payload: dict[str, Any],
        scene_id: str,
        rendered_scene: RenderedScene | None,
    ) -> tuple[str, str | None]:
        source_artifact = self._payload_path(payload, 'source_artifact', 'image_path')
        card_image = self._payload_path(payload, 'asset_refs', 'card_image')
        game_image = self._payload_path(payload, 'asset_refs', 'game_image')
        background = self._payload_path(payload, 'asset_refs', 'background')
        if scene_id == 'hook' and source_artifact:
            return 'source_artifact_image', source_artifact
        if scene_id == 'urgency' and card_image:
            return 'card_image', card_image
        if game_image:
            return 'game_image', game_image
        if background:
            return 'background', background
        if rendered_scene is not None and rendered_scene.asset_path is not None:
            return 'rendered_asset', str(rendered_scene.asset_path)
        return 'unknown', None

    @staticmethod
    def _payload_path(payload: dict[str, Any], section: str, key: str) -> str | None:
        block = payload.get(section) or {}
        if not isinstance(block, dict):
            return None
        value = block.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    @staticmethod
    def _int_or_none(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        return None

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None

    @staticmethod
    def _is_ukrainian_line(text: str) -> bool:
        return bool(text) and contains_cyrillic(text)

    def _first_matching_paragraph(self, facts: dict[str, Any], predicate) -> str:
        for paragraph in facts.get('caption_paragraphs') or ():
            if predicate(paragraph):
                return paragraph
        return ''

    def _prepend_title(self, title: str, text: str) -> str:
        cleaned = self._clean_for_speech(text)
        if not cleaned:
            return title
        if title.lower() in cleaned.lower():
            return self._end_sentence(cleaned)
        return self._end_sentence(f"{title}: {cleaned[:1].lower()}{cleaned[1:]}")

    def _compress_clause(self, text: str) -> str:
        cleaned = self._clean_for_speech(text)
        if not cleaned:
            return ''
        parts = [part for part in self.CLAUSE_SPLIT_RE.split(cleaned) if part]
        if not parts:
            return self._end_sentence(cleaned)
        return self._end_sentence(parts[0])

    def _percent_from_text(self, text: str) -> int | None:
        match = self.PERCENT_RE.search(text or '')
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    def _sanitize_title(self, value: str) -> str:
        cleaned = clean_html_text(value)
        cleaned = self.TRADEMARK_RE.sub('', cleaned)
        cleaned = self.STRIP_SPACING_RE.sub(' ', cleaned).strip(' ,.;:-')
        return cleaned or 'YOTO'

    def _compact_title(self, value: str) -> str:
        cleaned = self._sanitize_title(value)
        cleaned = self.EDITION_SUFFIX_RE.sub('', cleaned)
        cleaned = self.STRIP_SPACING_RE.sub(' ', cleaned).strip(' ,.;:-')
        if ':' in cleaned:
            leading = cleaned.split(':', 1)[0].strip()
            if 6 <= len(leading) <= 30:
                cleaned = leading
        if len(cleaned) <= 30:
            return cleaned
        words = cleaned.split()
        if len(words) > 4:
            candidate = ' '.join(words[:4]).rstrip(' ,.;:-')
            if len(candidate) >= 8:
                return candidate
        return cleaned[:30].rstrip(' ,.;:-')

    def _strip_title_prefix(self, text: str, title: str) -> str:
        cleaned = self._clean_for_speech(text)
        safe_title = self._clean_for_speech(title)
        if not safe_title:
            return cleaned
        if cleaned.lower().startswith(safe_title.lower()):
            remainder = cleaned[len(safe_title):].lstrip(' :,-')
            return remainder or cleaned
        return cleaned

    @staticmethod
    def _clean_for_speech(text: str) -> str:
        cleaned = clean_html_text(text)
        cleaned = cleaned.replace('\u2014', '-').replace('\u2013', '-')
        return ' '.join(cleaned.split()).strip()

    @staticmethod
    def _hashtags_only(text: str) -> bool:
        tokens = [token for token in text.split() if token]
        return bool(tokens) and all(token.startswith('#') for token in tokens)

    @staticmethod
    def _store_short_name(store: str) -> str:
        lowered = store.strip().lower()
        if lowered == 'epic games store':
            return 'Epic'
        return store.strip() or 'Steam'

    @staticmethod
    def _end_sentence(text: str) -> str:
        cleaned = text.rstrip(' ,;:-')
        if not cleaned:
            return ''
        if cleaned.endswith(('.', '!', '?')):
            return cleaned
        return f'{cleaned}.'
