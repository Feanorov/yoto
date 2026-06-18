from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


SUPPORTED_OFFER_TYPES = frozenset({"discount", "freebie", "unknown"})
SUPPORTED_TEMPLATE_HINTS = frozenset({"single_discount", "freebie", "top3", "unknown"})


class VideoOfferValidationError(ValueError):
    def __init__(self, message: str, *, missing_fields: list[str] | None = None) -> None:
        super().__init__(message)
        self.missing_fields = tuple(missing_fields or [])


def _dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value or "").strip()
        if not cleaned or cleaned in seen:
            continue
        deduped.append(cleaned)
        seen.add(cleaned)
    return deduped


@dataclass(slots=True)
class VideoVisualAssets:
    card_image: str = ""
    official_screenshots: list[str] = field(default_factory=list)
    official_trailers: list[str] = field(default_factory=list)
    fallback_image: str | None = None

    def __post_init__(self) -> None:
        self.card_image = str(self.card_image or "").strip()
        self.official_screenshots = _dedupe_strings(list(self.official_screenshots or []))
        self.official_trailers = _dedupe_strings(list(self.official_trailers or []))
        fallback = str(self.fallback_image or "").strip()
        self.fallback_image = fallback or None


@dataclass(slots=True)
class VideoCTA:
    default: str = "See full deal in Telegram"
    tiktok: str = "Join Telegram for the full deal link"
    shorts: str = "Open Telegram for the full post"
    reels: str = "Find the full deal in Telegram"

    def __post_init__(self) -> None:
        self.default = str(self.default or "").strip()
        self.tiktok = str(self.tiktok or "").strip()
        self.shorts = str(self.shorts or "").strip()
        self.reels = str(self.reels or "").strip()


@dataclass(slots=True)
class VideoOffer:
    offer_id: str
    source_report_path: str | None
    source_kind: str
    title: str
    store: str
    platform: str
    store_url: str
    offer_type: str
    discount_percent: int | None = None
    current_price_text: str | None = None
    old_price_text: str | None = None
    savings_text: str | None = None
    deadline_text: str | None = None
    reviews_text: str | None = None
    positive_percent_text: str | None = None
    achievements_text: str | None = None
    cards_text: str | None = None
    caption_html: str = ""
    card_image_path: str = ""
    image_hash: str = ""
    caption_hash: str = ""
    idempotency_key: str = ""
    visual_assets: VideoVisualAssets = field(default_factory=VideoVisualAssets)
    cta: VideoCTA = field(default_factory=VideoCTA)
    voice_mode: str = "none"
    template_hint: str = "unknown"
    source_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.offer_id = str(self.offer_id or "").strip()
        source_report_path = str(self.source_report_path or "").strip()
        self.source_report_path = source_report_path or None
        self.source_kind = str(self.source_kind or "").strip()
        self.title = str(self.title or "").strip()
        self.store = str(self.store or "").strip()
        self.platform = str(self.platform or "").strip()
        self.store_url = str(self.store_url or "").strip()
        self.offer_type = str(self.offer_type or "").strip().lower()
        self.current_price_text = _optional_text(self.current_price_text)
        self.old_price_text = _optional_text(self.old_price_text)
        self.savings_text = _optional_text(self.savings_text)
        self.deadline_text = _optional_text(self.deadline_text)
        self.reviews_text = _optional_text(self.reviews_text)
        self.positive_percent_text = _optional_text(self.positive_percent_text)
        self.achievements_text = _optional_text(self.achievements_text)
        self.cards_text = _optional_text(self.cards_text)
        self.caption_html = str(self.caption_html or "").strip()
        self.card_image_path = str(self.card_image_path or "").strip()
        self.image_hash = str(self.image_hash or "").strip()
        self.caption_hash = str(self.caption_hash or "").strip()
        self.idempotency_key = str(self.idempotency_key or "").strip()
        self.voice_mode = str(self.voice_mode or "none").strip().lower() or "none"
        self.template_hint = str(self.template_hint or "unknown").strip().lower() or "unknown"
        self.source_metadata = dict(self.source_metadata or {})

        if not self.visual_assets.card_image and self.card_image_path:
            self.visual_assets.card_image = self.card_image_path

        missing_fields: list[str] = []
        for field_name, value in (
            ("offer_id", self.offer_id),
            ("source_kind", self.source_kind),
            ("title", self.title),
            ("store", self.store),
            ("platform", self.platform),
            ("store_url", self.store_url),
            ("caption_html", self.caption_html),
            ("card_image_path", self.card_image_path),
            ("image_hash", self.image_hash),
            ("caption_hash", self.caption_hash),
            ("idempotency_key", self.idempotency_key),
            ("visual_assets.card_image", self.visual_assets.card_image),
        ):
            if not value:
                missing_fields.append(field_name)

        if self.offer_type not in SUPPORTED_OFFER_TYPES:
            raise VideoOfferValidationError(
                f"VideoOffer validation failed: unsupported offer_type={self.offer_type!r}.",
            )
        if self.template_hint not in SUPPORTED_TEMPLATE_HINTS:
            raise VideoOfferValidationError(
                f"VideoOffer validation failed: unsupported template_hint={self.template_hint!r}.",
            )
        if not self.cta.default or not self.cta.tiktok or not self.cta.shorts or not self.cta.reels:
            missing_fields.append("cta")
        if missing_fields:
            field_list = ", ".join(missing_fields)
            raise VideoOfferValidationError(
                f"VideoOffer validation failed: missing required fields: {field_list}.",
                missing_fields=missing_fields,
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _optional_text(value: str | None) -> str | None:
    cleaned = str(value or "").strip()
    return cleaned or None
