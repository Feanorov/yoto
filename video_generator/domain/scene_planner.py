from __future__ import annotations

import json
import re
from typing import Any

from .entities import PlannedScene, VideoManifest, VideoTemplate


class ScenePlanner:
    SUMMARY_HEADLINE_MAX = 48
    SUMMARY_BODY_MAX = 64
    URGENCY_HEADLINE_MAX = 56
    CTA_MAX = 54
    HOOK_BODY_MAX = 88
    ROUNDUP_HOOK_BODY_MAX = 96
    ROUNDUP_CLOSE_BODY_MAX = 72
    ROUNDUP_ITEM_LINE_MAX = 24

    OFFER_KIND_LABELS = {
        'discount': '\u0417\u043d\u0438\u0436\u043a\u0430',
        'freebie': '\u0411\u0435\u0437\u043a\u043e\u0448\u0442\u043e\u0432\u043d\u0430 \u0433\u0440\u0430',
        'festival': '\u041f\u043e\u0434\u0456\u044f',
        'event': '\u041f\u043e\u0434\u0456\u044f',
    }
    CLAUSE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+|(?<=:)\s+|(?<=;)\s+')

    def plan(self, manifest: VideoManifest, template: VideoTemplate) -> tuple[PlannedScene, ...]:
        if template.name == 'roundup_digest':
            return self._plan_roundup_digest(manifest)
        return self._plan_standard_offer(manifest)

    def _plan_standard_offer(self, manifest: VideoManifest) -> tuple[PlannedScene, ...]:
        hook_body = self._budget_text(manifest.hook_line, self.HOOK_BODY_MAX)
        supporting_line = self._budget_text(self._supporting_line(manifest), self.SUMMARY_BODY_MAX)
        summary_headline = self._summary_headline(manifest)
        urgency_headline = self._compress_to_clause(manifest.urgency_line, self.URGENCY_HEADLINE_MAX)
        call_to_action = self._compress_to_clause(self._call_to_action(manifest), self.CTA_MAX)
        return (
            PlannedScene(
                scene_id='hook',
                position=1,
                duration_seconds=2.0,
                headline=manifest.short_title,
                body=hook_body,
                cta=None,
                voiceover_text=hook_body,
                visual_role='hero',
            ),
            PlannedScene(
                scene_id='summary',
                position=2,
                duration_seconds=5.0,
                headline=summary_headline,
                body=supporting_line,
                cta=None,
                voiceover_text=summary_headline,
                visual_role='support',
            ),
            PlannedScene(
                scene_id='urgency',
                position=3,
                duration_seconds=3.0,
                headline=urgency_headline,
                body=supporting_line,
                cta=call_to_action,
                voiceover_text=f'{urgency_headline} {call_to_action}'.strip(),
                visual_role='cta',
            ),
        )

    def _plan_roundup_digest(self, manifest: VideoManifest) -> tuple[PlannedScene, ...]:
        items = self._roundup_items(manifest)
        first_page = self._roundup_page_body(items[:2], start_index=1) or self._budget_text(manifest.summary_line, self.ROUNDUP_CLOSE_BODY_MAX)
        second_page = self._roundup_page_body(items[2:4], start_index=3) or self._budget_text(manifest.summary_line, self.ROUNDUP_CLOSE_BODY_MAX)
        hook_body = self._compress_roundup_intro(manifest.hook_line)
        close_cta = self._compress_to_clause(self._roundup_call_to_action(manifest), self.CTA_MAX)
        close_headline = self._compress_to_clause(manifest.urgency_line, self.URGENCY_HEADLINE_MAX)
        close_body = self._budget_text(manifest.summary_line or self._supporting_line(manifest), self.ROUNDUP_CLOSE_BODY_MAX)
        return (
            PlannedScene(
                scene_id='hook',
                position=1,
                duration_seconds=2.0,
                headline=manifest.short_title,
                body=hook_body,
                cta=None,
                voiceover_text=f'{manifest.short_title}. {hook_body}'.strip(),
                visual_role='hero',
            ),
            PlannedScene(
                scene_id='roundup_page_one',
                position=2,
                duration_seconds=3.0,
                headline='\u0429\u043e \u0432 \u0434\u043e\u0431\u0456\u0440\u0446\u0456',
                body=first_page,
                cta=None,
                voiceover_text=first_page.replace('\n', ' '),
                visual_role='roundup_page',
            ),
            PlannedScene(
                scene_id='roundup_page_two',
                position=3,
                duration_seconds=3.0,
                headline='\u0429\u0435 \u043a\u0456\u043b\u044c\u043a\u0430 \u043f\u043e\u0437\u0438\u0446\u0456\u0439',
                body=second_page,
                cta=None,
                voiceover_text=second_page.replace('\n', ' '),
                visual_role='roundup_page',
            ),
            PlannedScene(
                scene_id='urgency',
                position=4,
                duration_seconds=2.0,
                headline=close_headline,
                body=close_body,
                cta=close_cta,
                voiceover_text=f'{close_headline} {close_cta}'.strip(),
                visual_role='cta',
            ),
        )

    @staticmethod
    def _call_to_action(manifest: VideoManifest) -> str:
        if manifest.template_hint == 'freebie-flash':
            return '\u0414\u043e\u0434\u0430\u0439 \u0433\u0440\u0443 \u0437\u0430\u0440\u0430\u0437, \u043f\u043e\u043a\u0438 \u0440\u043e\u0437\u0434\u0430\u0447\u0430 \u0430\u043a\u0442\u0438\u0432\u043d\u0430.'
        if manifest.template_hint == 'event-countdown':
            return '\u041f\u0435\u0440\u0435\u0433\u043b\u044f\u043d\u044c \u043f\u043e\u0434\u0456\u044e \u0437\u0430\u0440\u0430\u0437 \u0442\u0430 \u0437\u0430\u0431\u0435\u0440\u0438 \u043d\u0430\u0439\u043a\u0440\u0430\u0449\u0456 \u0437\u043d\u0438\u0436\u043a\u0438.'
        if manifest.template_hint in {'deadline-push', 'final-push'} or manifest.context.get('lane') == 'final_push':
            return '\u041f\u0435\u0440\u0435\u0432\u0456\u0440 \u0437\u043d\u0438\u0436\u043a\u0443 \u0437\u0430\u0440\u0430\u0437 \u0434\u043e \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u043d\u044f \u0430\u043a\u0446\u0456\u0457.'
        return '\u041f\u0435\u0440\u0435\u0432\u0456\u0440 \u043f\u0440\u043e\u043f\u043e\u0437\u0438\u0446\u0456\u044e \u0437\u0430\u0440\u0430\u0437.'

    @classmethod
    def _supporting_line(cls, manifest: VideoManifest) -> str:
        store = str(manifest.context.get('store') or '').strip()
        offer_kind = str(manifest.context.get('offer_kind') or '').replace('_', ' ').strip().lower()
        offer_kind_label = cls.OFFER_KIND_LABELS.get(offer_kind, offer_kind)
        if store and offer_kind_label:
            return f'{store} - {offer_kind_label}'
        return store or offer_kind_label or manifest.short_title

    @staticmethod
    def _roundup_call_to_action(manifest: VideoManifest) -> str:
        return '\u041f\u0435\u0440\u0435\u0433\u043b\u044f\u043d\u044c \u0434\u043e\u0431\u0456\u0440\u043a\u0443 \u0437\u0430\u0440\u0430\u0437.'

    def _roundup_items(self, manifest: VideoManifest) -> list[dict[str, Any]]:
        try:
            payload = json.loads(manifest.source_path.read_text(encoding='utf-8'))
        except Exception:
            return []
        raw_items = payload.get('roundup_items') or []
        if not isinstance(raw_items, list):
            return []
        items: list[dict[str, Any]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            title = str(item.get('title') or '').strip()
            if not title:
                continue
            items.append(item)
        return items

    def _roundup_page_body(self, items: list[dict[str, Any]], *, start_index: int) -> str:
        lines: list[str] = []
        for offset, item in enumerate(items, start=start_index):
            line = self._roundup_item_line(item, offset)
            if line:
                lines.append(line)
        return '\n'.join(lines[:2])

    def _roundup_item_line(self, item: dict[str, Any], index: int) -> str:
        title = str(item.get('title') or '').strip()
        if not title:
            return ''
        detail = ''
        discount_percent = item.get('discount_percent')
        if isinstance(discount_percent, int) and discount_percent > 0:
            detail = f'-{discount_percent}%'
        elif item.get('offer_kind') == 'freebie' or item.get('price_after_minor') == 0:
            detail = 'free'
        compact_title = self._budget_text(title, self.ROUNDUP_ITEM_LINE_MAX)
        if detail:
            return f'{index}. {detail} {compact_title}'
        return f'{index}. {compact_title}'

    def _summary_headline(self, manifest: VideoManifest) -> str:
        summary_line = self._clean_text(manifest.summary_line)
        if len(summary_line) <= self.SUMMARY_HEADLINE_MAX:
            return summary_line
        short_title = self._budget_text(manifest.short_title, self.SUMMARY_HEADLINE_MAX)
        if short_title:
            return short_title
        return self._budget_text(summary_line, self.SUMMARY_HEADLINE_MAX)

    def _compress_roundup_intro(self, text: str) -> str:
        return self._compress_to_clause(text, self.ROUNDUP_HOOK_BODY_MAX)

    def _compress_to_clause(self, text: str, max_chars: int) -> str:
        cleaned = self._clean_text(text)
        if len(cleaned) <= max_chars:
            return cleaned
        first_clause = self._first_clause(cleaned)
        if first_clause and len(first_clause) <= max_chars:
            return first_clause
        return self._budget_text(cleaned, max_chars)

    def _budget_text(self, text: str, max_chars: int) -> str:
        cleaned = self._clean_text(text)
        if len(cleaned) <= max_chars:
            return cleaned

        truncated = cleaned[: max_chars + 1]
        boundary = max(
            truncated.rfind('. '),
            truncated.rfind('! '),
            truncated.rfind('? '),
            truncated.rfind('; '),
            truncated.rfind(': '),
            truncated.rfind(', '),
        )
        if boundary >= max_chars // 2:
            candidate = truncated[: boundary + 1].rstrip(' ,;:')
            if candidate:
                return candidate

        clipped = cleaned[:max_chars].rstrip(' ,.;:-')
        if not clipped:
            return cleaned[:max_chars]
        return f'{clipped}...'

    def _first_clause(self, text: str) -> str:
        parts = [part.strip() for part in self.CLAUSE_SPLIT_RE.split(text) if part.strip()]
        return parts[0] if parts else ''

    @staticmethod
    def _clean_text(text: str) -> str:
        return ' '.join(str(text or '').split()).strip()

