from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from pathlib import Path
import re
from typing import Iterable, Protocol

from domain.entities.analytics_artifact import AnalyticsArtifact
from domain.entities.offer import Offer
from domain.entities.roundup_post import RoundupItem, RoundupPost
from infrastructure.analytics.artifact_writer import AnalyticsArtifactWriter
from infrastructure.db.repositories import Repositories
from infrastructure.observability.metrics import Metrics
from infrastructure.telegram.roundup_draft_builder import TelegramRoundupDraftBuilder

from .plan_queue import PlannedCandidate, QueuePlan


ROUNDUP_THEME_STOPWORDS = {
    'a',
    'all',
    'bundle',
    'collection',
    'deal',
    'deals',
    'discount',
    'discounts',
    'edition',
    'editions',
    'epic',
    'event',
    'festival',
    'fest',
    'for',
    'freebie',
    'freebies',
    'game',
    'games',
    'offer',
    'offers',
    'pack',
    'sale',
    'steam',
    'store',
    'the',
    'ultimate',
}
ROUNDUP_PART_SUFFIX = re.compile(r' Part [1-9]\d*$')


@dataclass(slots=True)
class RoundupDraft:
    group_type: str
    theme_label: str
    title: str
    intro: str
    items: list[PlannedCandidate]


class SupportsRoundupCardAdapter(Protocol):
    def render(self, roundup: RoundupPost):
        ...


class GenerateRoundupArtifactsUseCase:
    MIN_ITEMS = 3
    MAX_ITEMS = 5
    MAX_ROUNDUPS_PER_WINDOW = 1
    ROUNDUP_RECURRENCE_LOOKBACK_ARTIFACTS = 5
    ROUNDUP_RECURRENCE_MIN_OVERLAP_ITEMS = 3
    ROUNDUP_RECURRENCE_OVERLAP_RATIO = 0.6

    def __init__(
        self,
        repositories: Repositories,
        writer: AnalyticsArtifactWriter,
        metrics: Metrics | None = None,
        draft_builder: TelegramRoundupDraftBuilder | None = None,
        roundup_card_adapter: SupportsRoundupCardAdapter | None = None,
    ) -> None:
        self.repositories = repositories
        self.writer = writer
        self.metrics = metrics or Metrics()
        self.draft_builder = draft_builder or TelegramRoundupDraftBuilder()
        self.roundup_card_adapter = roundup_card_adapter
        self.logger = logging.getLogger(__name__)

    def execute(self, now_utc: datetime, plan: QueuePlan) -> None:
        run_key = now_utc.strftime('%Y%m%dT%H%M%SZ')
        roundups = self._build_roundups(plan.reserve)
        if not roundups:
            self.metrics.inc('roundup.skipped.empty')
            return
        roundups = self._apply_recurrence_cooldown(roundups, run_key)
        if not roundups:
            self.metrics.inc('roundup.skipped.recurrence')
            return
        roundups = self._apply_roundup_window_cap(roundups)
        roundups = self._normalize_orphaned_part_suffix(roundups)
        self._render_roundup_cards(roundups)

        artifact = self._build_artifact(run_key, now_utc, roundups, plan.context)
        self._write_files(artifact)
        self._save_record(artifact)
        self.metrics.inc('roundup.generated', len(roundups))

    def _apply_recurrence_cooldown(self, roundups: list[RoundupPost], run_key: str) -> list[RoundupPost]:
        recent_snapshots = self.repositories.list_recent_roundup_snapshots(self.ROUNDUP_RECURRENCE_LOOKBACK_ARTIFACTS)
        if not recent_snapshots:
            return roundups

        self.metrics.inc('roundup.recurrence.checked', len(roundups))
        filtered: list[RoundupPost] = []
        for roundup in roundups:
            recurrence_match = self._find_recurrence_match(roundup, recent_snapshots, run_key)
            if recurrence_match is None:
                filtered.append(roundup)
                continue

            historical_run_key, historical_roundup_id, overlap_count, overlap_ratio = recurrence_match
            self.metrics.inc('roundup.recurrence.suppressed')
            self.logger.info(
                'Roundup recurrence suppressed current=%s historical=%s run=%s overlap=%s ratio=%.2f',
                roundup.roundup_id,
                historical_roundup_id,
                historical_run_key,
                overlap_count,
                overlap_ratio,
            )
        return filtered

    def _find_recurrence_match(
        self,
        roundup: RoundupPost,
        recent_snapshots: list[dict],
        current_run_key: str,
    ) -> tuple[str, str, int, float] | None:
        current_offer_ids = self._offer_ids_for_roundup(roundup)
        if not current_offer_ids:
            return None

        for snapshot in recent_snapshots:
            historical_run_key = str(snapshot.get('run_key') or '')
            if historical_run_key == current_run_key:
                continue
            historical_roundups = snapshot.get('roundups') or []
            if not isinstance(historical_roundups, list):
                continue
            for historical_roundup in historical_roundups:
                historical_offer_ids = self._offer_ids_for_roundup_snapshot(historical_roundup)
                if not historical_offer_ids:
                    continue

                overlap_count = len(current_offer_ids & historical_offer_ids)
                if overlap_count == 0:
                    continue
                overlap_ratio = overlap_count / len(current_offer_ids)
                if current_offer_ids == historical_offer_ids or (
                    overlap_count >= self.ROUNDUP_RECURRENCE_MIN_OVERLAP_ITEMS
                    and overlap_ratio >= self.ROUNDUP_RECURRENCE_OVERLAP_RATIO
                ):
                    return (
                        historical_run_key,
                        str(historical_roundup.get('roundup_id') or ''),
                        overlap_count,
                        overlap_ratio,
                    )
        return None

    @staticmethod
    def _offer_ids_for_roundup(roundup: RoundupPost) -> frozenset[str]:
        return frozenset(item.offer_id for item in roundup.items if item.offer_id)

    @staticmethod
    def _offer_ids_for_roundup_snapshot(roundup_snapshot: dict) -> frozenset[str]:
        if not isinstance(roundup_snapshot, dict):
            return frozenset()
        items = roundup_snapshot.get('items') or []
        if not isinstance(items, list):
            return frozenset()
        return frozenset(
            str(item.get('offer_id'))
            for item in items
            if isinstance(item, dict) and item.get('offer_id')
        )

    def _apply_roundup_window_cap(self, roundups: list[RoundupPost]) -> list[RoundupPost]:
        if len(roundups) <= self.MAX_ROUNDUPS_PER_WINDOW:
            return roundups

        capped = roundups[: self.MAX_ROUNDUPS_PER_WINDOW]
        suppressed_count = len(roundups) - len(capped)
        self.metrics.inc('roundup.window_cap_applied')
        self.metrics.inc('roundup.window_cap_suppressed', suppressed_count)
        self.logger.info(
            'Roundup window cap applied kept=%s suppressed=%s',
            capped[0].roundup_id if capped else None,
            suppressed_count,
        )
        return capped

    def _normalize_orphaned_part_suffix(self, roundups: list[RoundupPost]) -> list[RoundupPost]:
        if len(roundups) != 1:
            return roundups

        roundup = roundups[0]
        normalized_title = ROUNDUP_PART_SUFFIX.sub('', roundup.title)
        if normalized_title == roundup.title:
            return roundups

        roundup.title = normalized_title
        roundup.telegram_draft = self.draft_builder.build(roundup)
        return roundups

    def _render_roundup_cards(self, roundups: list[RoundupPost]) -> None:
        if self.roundup_card_adapter is None:
            return

        for roundup in roundups:
            try:
                rendered = self.roundup_card_adapter.render(roundup)
            except Exception as exc:
                self.metrics.inc('roundup.card.failed')
                self.logger.warning('Roundup card render failed for %s: %s', roundup.roundup_id, exc)
                continue

            diagnostics = {}
            if isinstance(rendered, Path):
                output_path = rendered
            else:
                output_path = Path(getattr(rendered, 'image_path'))
                diagnostics_payload = getattr(rendered, 'diagnostics', {})
                if isinstance(diagnostics_payload, dict):
                    diagnostics = dict(diagnostics_payload)
            roundup.card_asset_path = str(output_path)
            roundup.card_render_diagnostics = diagnostics
            self.metrics.inc('roundup.card.generated')

    def _write_files(self, artifact: AnalyticsArtifact) -> None:
        try:
            artifact.json_path, artifact.csv_path = self.writer.write(artifact)
            self.metrics.inc('roundup.files.success')
        except Exception as exc:
            self.metrics.inc('roundup.files.failed')
            self.logger.warning('Roundup artifact write failed for %s: %s', artifact.subject_id, exc)
            artifact.json_path = None
            artifact.csv_path = None

    def _save_record(self, artifact: AnalyticsArtifact) -> None:
        try:
            self.repositories.save_analytics_artifact(artifact)
            self.metrics.inc('roundup.db.success')
        except Exception as exc:
            self.metrics.inc('roundup.db.failed')
            self.logger.warning('Roundup artifact persistence failed for %s: %s', artifact.subject_id, exc)

    def _build_artifact(self, run_key: str, now_utc: datetime, roundups: list[RoundupPost], plan_context: dict) -> AnalyticsArtifact:
        context = dict(plan_context or {})
        context.setdefault('source', 'current_queue')
        context.setdefault('queue_snapshot_at', None)
        payload = {
            'roundup_version': 1,
            'run_key': run_key,
            'created_at': now_utc.isoformat(),
            'roundup_count': len(roundups),
            'context': context,
            'roundups': [roundup.to_snapshot() for roundup in roundups],
        }
        summary_rows: list[dict] = []
        for roundup in roundups:
            draft = roundup.telegram_draft
            for item in roundup.items:
                summary_rows.append(
                    {
                        'roundup_id': roundup.roundup_id,
                        'roundup_title': roundup.title,
                        'roundup_intro': roundup.intro,
                        'group_type': roundup.group_type,
                        'theme_label': roundup.theme_label,
                        'telegram_title': draft.title if draft else None,
                        'telegram_intro': draft.intro if draft else None,
                        'telegram_closing_cta': draft.closing_cta if draft else None,
                        'telegram_caption_html': draft.caption_html if draft else None,
                        'telegram_item_line': draft.item_lines[item.rank - 1] if draft and item.rank - 1 < len(draft.item_lines) else None,
                        'rank': item.rank,
                        'offer_id': item.offer_id,
                        'offer_title': item.title,
                        'store': item.store,
                        'lane': item.lane,
                        'score': item.score,
                        'discount_percent': item.discount_percent,
                        'price_line': item.price_line,
                        'callout': item.callout,
                        'summary_line': item.summary_line,
                        'reason_tags': list(item.reason_tags),
                    }
                )
        return AnalyticsArtifact(
            artifact_type='roundup_snapshot',
            subject_id='roundups',
            run_key=run_key,
            created_at=now_utc,
            payload_json=payload,
            summary_rows=summary_rows,
        )

    def _build_roundups(self, reserve: list[PlannedCandidate]) -> list[RoundupPost]:
        remaining = sorted(self._eligible_candidates(reserve), key=lambda item: item.score, reverse=True)
        drafts: list[RoundupDraft] = []
        drafts.extend(self._consume_theme_groups(remaining, self._genre_buckets))
        drafts.extend(self._consume_theme_groups(remaining, self._tag_buckets))
        drafts.extend(self._consume_profile_groups(remaining))
        drafts.extend(self._consume_mixed_groups(remaining))

        drafts.sort(key=lambda draft: max(item.score for item in draft.items), reverse=True)
        title_totals: dict[str, int] = {}
        for draft in drafts:
            title_totals[draft.title] = title_totals.get(draft.title, 0) + 1

        title_seen: dict[str, int] = {}
        roundups: list[RoundupPost] = []
        for index, draft in enumerate(drafts, start=1):
            title_seen[draft.title] = title_seen.get(draft.title, 0) + 1
            title = draft.title
            if title_totals[draft.title] > 1:
                title = f'{draft.title} Part {title_seen[draft.title]}'
            roundup = self._roundup_from_draft(index, draft, title=title)
            roundup.telegram_draft = self.draft_builder.build(roundup)
            roundups.append(roundup)
        return roundups

    @staticmethod
    def _eligible_candidates(reserve: list[PlannedCandidate]) -> list[PlannedCandidate]:
        return [
            item
            for item in reserve
            if item.decision_json.get('recommended_post_mode') in {None, 'roundup_candidate'}
        ]

    def _consume_theme_groups(self, remaining: list[PlannedCandidate], bucket_builder) -> list[RoundupDraft]:
        drafts: list[RoundupDraft] = []
        while True:
            buckets = bucket_builder(remaining)
            eligible = [bucket for bucket in buckets if len(bucket[2]) >= self.MIN_ITEMS]
            if not eligible:
                break
            group_type, theme_label, group_items = max(
                eligible,
                key=lambda bucket: (len(bucket[2]), max(item.score for item in bucket[2])),
            )
            picked = sorted(group_items, key=lambda item: item.score, reverse=True)[: self.MAX_ITEMS]
            self._remove_items(remaining, picked)
            drafts.append(self._draft_for_theme(group_type, theme_label, picked))
        return drafts

    def _consume_profile_groups(self, remaining: list[PlannedCandidate]) -> list[RoundupDraft]:
        drafts: list[RoundupDraft] = []
        profile_specs = [
            (
                'freebie',
                lambda item: item.offer.is_freebie,
                'Freebies To Claim',
                'These claims are worth bundling into one quick post instead of forcing breaking treatment.',
            ),
            (
                'hero_discount',
                lambda item: 'hero_discount' in set(item.decision_json.get('decision_reasons') or []),
                'Big Discount Highlights',
                'Top reserve discounts with enough editorial weight to carry one combined roundup post.',
            ),
            (
                'strong_discount',
                lambda item: 'strong_discount' in set(item.decision_json.get('decision_reasons') or []),
                'Strong Discount Picks',
                'Solid secondary discounts that work better together than as separate solo posts right now.',
            ),
        ]
        for group_type, predicate, theme_label, intro in profile_specs:
            matching = [item for item in remaining if predicate(item)]
            while len(matching) >= self.MIN_ITEMS:
                picked = matching[: self.MAX_ITEMS]
                self._remove_items(remaining, picked)
                drafts.append(
                    RoundupDraft(
                        group_type=group_type,
                        theme_label=theme_label,
                        title=f'Roundup: {theme_label}',
                        intro=intro,
                        items=picked,
                    )
                )
                matching = [item for item in remaining if predicate(item)]
        return drafts

    def _consume_mixed_groups(self, remaining: list[PlannedCandidate]) -> list[RoundupDraft]:
        drafts: list[RoundupDraft] = []
        while len(remaining) >= self.MIN_ITEMS:
            picked = remaining[: self.MAX_ITEMS]
            self._remove_items(remaining, picked)
            drafts.append(
                RoundupDraft(
                    group_type='mixed',
                    theme_label='Reserve Deals Watch',
                    title='Roundup: Reserve Deals Watch',
                    intro='A mixed reserve bundle built from the strongest remaining roundup candidates in this window.',
                    items=picked,
                )
            )
        return drafts

    def _genre_buckets(self, items: list[PlannedCandidate]) -> list[tuple[str, str, list[PlannedCandidate]]]:
        buckets: dict[str, tuple[str, list[PlannedCandidate]]] = {}
        for item in items:
            theme = self._theme_from_values(item.offer.genres[:1])
            if theme is None:
                continue
            normalized, display = theme
            entry = buckets.setdefault(normalized, (display, []))
            entry[1].append(item)
        return [('genre', display, grouped_items) for display, grouped_items in buckets.values()]

    def _tag_buckets(self, items: list[PlannedCandidate]) -> list[tuple[str, str, list[PlannedCandidate]]]:
        buckets: dict[str, tuple[str, list[PlannedCandidate]]] = {}
        for item in items:
            seen: set[str] = set()
            for theme in self._theme_candidates(item.offer.tags[:4]):
                normalized, display = theme
                if normalized in seen:
                    continue
                seen.add(normalized)
                entry = buckets.setdefault(normalized, (display, []))
                entry[1].append(item)
        return [('tag', display, grouped_items) for display, grouped_items in buckets.values()]

    def _draft_for_theme(self, group_type: str, theme_label: str, items: list[PlannedCandidate]) -> RoundupDraft:
        title = f'Roundup: {theme_label} Picks' if group_type == 'genre' else f'Roundup: {theme_label} Highlights'
        intro = 'A themed bundle of related offers that fits better as one post than as separate solos right now.'
        return RoundupDraft(
            group_type=group_type,
            theme_label=theme_label,
            title=title,
            intro=intro,
            items=items,
        )

    def _roundup_from_draft(self, index: int, draft: RoundupDraft, *, title: str | None = None) -> RoundupPost:
        items = [
            self._roundup_item(rank, candidate)
            for rank, candidate in enumerate(sorted(draft.items, key=lambda item: item.score, reverse=True), start=1)
        ]
        roundup_id = f'roundup_{index:02d}_{self._slug(draft.theme_label)}'
        return RoundupPost(
            roundup_id=roundup_id,
            title=title or draft.title,
            intro=draft.intro,
            group_type=draft.group_type,
            theme_label=draft.theme_label,
            item_count=len(items),
            items=items,
        )

    def _roundup_item(self, rank: int, candidate: PlannedCandidate) -> RoundupItem:
        offer = candidate.offer
        reasons = list(candidate.decision_json.get('decision_reasons') or [])
        price_line = self._price_line(offer)
        callout = self._callout(offer, reasons)
        summary_line = self._summary_line(offer, price_line, callout)
        return RoundupItem(
            rank=rank,
            offer_id=offer.offer_id,
            title=offer.title,
            store_url=offer.store_url,
            store=self._store_name(offer),
            source=offer.source.value,
            lane=str(candidate.decision_json.get('lane') or ''),
            score=round(candidate.score, 2),
            discount_percent=offer.discount_percent,
            review_score=offer.review_score,
            is_freebie=offer.is_freebie,
            price_after_minor=offer.price_after_minor,
            price_line=price_line,
            callout=callout,
            summary_line=summary_line,
            reason_tags=reasons,
            lead_artwork_url=offer.primary_asset_url,
        )

    @staticmethod
    def _remove_items(remaining: list[PlannedCandidate], picked: Iterable[PlannedCandidate]) -> None:
        picked_ids = {id(item) for item in picked}
        remaining[:] = [item for item in remaining if id(item) not in picked_ids]

    def _theme_candidates(self, values: list[str]) -> list[tuple[str, str]]:
        themes: list[tuple[str, str]] = []
        seen: set[str] = set()
        for value in values:
            theme = self._theme_from_values([value])
            if theme is None:
                continue
            normalized, display = theme
            if normalized in seen:
                continue
            seen.add(normalized)
            themes.append((normalized, display))
        return themes

    def _theme_from_values(self, values: list[str]) -> tuple[str, str] | None:
        for value in values:
            cleaned = re.sub(r'[^a-z0-9 ]+', ' ', (value or '').lower())
            tokens = [token for token in cleaned.split() if token and token not in ROUNDUP_THEME_STOPWORDS]
            if not tokens:
                continue
            normalized = ' '.join(tokens[:3])
            display = ' '.join(token.title() for token in tokens[:3])
            if len(normalized) < 3:
                continue
            return normalized, display
        return None

    @staticmethod
    def _store_name(offer: Offer) -> str:
        if offer.source.value == 'epic':
            return 'Epic Games Store'
        return 'Steam'

    @staticmethod
    def _price_line(offer: Offer) -> str:
        if offer.is_freebie:
            return 'Free claim'
        if offer.price_after_minor is not None:
            amount = offer.price_after_minor / 100
            amount_label = str(int(amount)) if amount.is_integer() else f'{amount:.2f}'
            if offer.discount_percent > 0:
                return f'{offer.discount_percent}% off to UAH {amount_label}'
            return f'UAH {amount_label}'
        if offer.discount_percent > 0:
            return f'{offer.discount_percent}% off'
        return 'Price live now'

    @staticmethod
    def _callout(offer: Offer, reasons: list[str]) -> str:
        reason_set = set(reasons)
        if offer.is_freebie:
            return 'Freebie roundup candidate'
        if 'hero_discount' in reason_set:
            return 'Hero discount'
        if 'strong_discount' in reason_set:
            return 'Strong secondary discount'
        if 'roundup_discount' in reason_set:
            return 'Roundup-fit discount'
        if 'mid_discount' in reason_set:
            return 'Backlog discount'
        return 'Reserve candidate'

    @staticmethod
    def _summary_line(offer: Offer, price_line: str, callout: str) -> str:
        parts = [price_line, callout]
        if offer.review_score is not None:
            parts.append(f'review {offer.review_score}/100')
        return ' | '.join(parts)

    @staticmethod
    def _slug(value: str) -> str:
        return re.sub(r'[^a-z0-9]+', '_', (value or '').lower()).strip('_') or 'group'


