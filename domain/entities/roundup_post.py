from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class RoundupTelegramDraft:
    title: str
    intro: str
    item_lines: list[str] = field(default_factory=list)
    closing_cta: str = ''
    caption_html: str = ''

    def to_snapshot(self) -> dict:
        return {
            'title': self.title,
            'intro': self.intro,
            'item_lines': list(self.item_lines),
            'closing_cta': self.closing_cta,
            'caption_html': self.caption_html,
        }


@dataclass(slots=True)
class RoundupItem:
    rank: int
    offer_id: str
    title: str
    store_url: str
    store: str
    source: str
    lane: str
    score: float
    discount_percent: int
    review_score: int | None
    is_freebie: bool
    price_after_minor: int | None
    price_line: str
    callout: str
    summary_line: str
    reason_tags: list[str] = field(default_factory=list)
    lead_artwork_url: str | None = None

    def to_snapshot(self) -> dict:
        return {
            'rank': self.rank,
            'offer_id': self.offer_id,
            'title': self.title,
            'store_url': self.store_url,
            'store': self.store,
            'source': self.source,
            'lane': self.lane,
            'score': self.score,
            'discount_percent': self.discount_percent,
            'review_score': self.review_score,
            'is_freebie': self.is_freebie,
            'price_after_minor': self.price_after_minor,
            'price_line': self.price_line,
            'callout': self.callout,
            'summary_line': self.summary_line,
            'reason_tags': list(self.reason_tags),
        }


@dataclass(slots=True)
class RoundupPost:
    roundup_id: str
    title: str
    intro: str
    group_type: str
    theme_label: str
    item_count: int
    items: list[RoundupItem] = field(default_factory=list)
    telegram_draft: RoundupTelegramDraft | None = None
    card_asset_path: str | None = None
    card_render_diagnostics: dict | None = None

    def to_snapshot(self) -> dict:
        return {
            'roundup_id': self.roundup_id,
            'title': self.title,
            'intro': self.intro,
            'group_type': self.group_type,
            'theme_label': self.theme_label,
            'item_count': self.item_count,
            'items': [item.to_snapshot() for item in self.items],
            'telegram_draft': self.telegram_draft.to_snapshot() if self.telegram_draft else None,
            'card_asset_path': self.card_asset_path,
            'card_render_diagnostics': dict(self.card_render_diagnostics or {}),
        }
