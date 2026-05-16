from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import hashlib
import re
import unicodedata
from typing import Any, Mapping, Sequence
import os

from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat

from dealbot.utils.ua import contains_cyrillic, format_deadline
from infrastructure.render.cards.image_providers import (
    ArtworkImageProvider,
    ComfyUIImageProvider,
    IMAGE_PIPELINE_VERSION,
    ImageResolutionRequest,
    PlaceholderImageProvider,
    YotoImageResolver,
)


CARD_SIZE = (1280, 720)
SAFE_TOP = 60
SAFE_BOTTOM = 90
SAFE_LEFT = 40
SAFE_RIGHT = 40
HERO_HEIGHT = 468
LOWER_THIRD_TOP = 462
GAMEPLAY_STRIP_HEIGHT = 118
GAMEPLAY_STRIP_TOP = 322
OUTPUT_PREFIX = 'yoto_card_'

PRIMARY_GREEN = '#27e07d'
ACCENT_GLOW = '#1df2a6'
DISCOUNT_ORANGE = '#ff7a2f'
DISCOUNT_RED = '#ff553d'
DISCOUNT_GLOW = '#ff7d4f'
EVENT_CYAN = '#4fe6ff'
EVENT_PURPLE = '#8d63ff'
EVENT_GLOW = '#72f1ff'
DARK_BG = '#060b10'
PANEL_TOP = '#060b10'
PANEL_BOTTOM = '#0b141c'
NEUTRAL_TEXT = '#9aa6b2'
WHITE = '#ffffff'
UA_FREE = "\u0411\u0415\u0417\u041a\u041e\u0428\u0422\u041e\u0412\u041d\u041e"
UA_DISCOUNT = "\u0417\u041d\u0418\u0416\u041a\u0410"
UA_EVENT = "\u041f\u041e\u0414\u0406\u042f"
UA_TOP = "\u0422\u041e\u041f"
UA_OLD_PRICE_PREFIX = "\u0411\u0443\u043b\u043e"
STEAM_SALE_LABEL = "STEAM SALE"
SALE_ENDS_SOON_LABEL = "SALE ENDS SOON"
GIVEAWAY_LABEL = "\u0420\u041e\u0417\u0414\u0410\u0427\u0410"
SALE_LABEL = "\u0417\u041d\u0418\u0416\u041a\u0410"
EVENT_LABEL = "\u041f\u041e\u0414\u0406\u042f"
GAMEPLAY_LABEL = "\u0413\u0415\u0419\u041c\u041f\u041b\u0415\u0419"
PANEL_KICKERS = {
    'FREE_GAME': "\u0420\u0410\u0414\u0410\u0420 \u0420\u041e\u0417\u0414\u0410\u0427",
    'DISCOUNT': "\u0421\u0418\u0413\u041d\u0410\u041b \u0417\u041d\u0418\u0416\u041e\u041a",
    'FESTIVAL': "\u0420\u0410\u0414\u0410\u0420 \u041f\u041e\u0414\u0406\u0419",
    'TOP_LIST': "\u0422\u041e\u041f \u0414\u041e\u0411\u0406\u0420\u041a\u0410",
}
BRAND_MICRO_LABELS = {
    'FREE_GAME': "\u0456\u0433\u0440\u043e\u0432\u0456 \u0440\u043e\u0437\u0434\u0430\u0447\u0456",
    'DISCOUNT': "\u0441\u0438\u0433\u043d\u0430\u043b \u0437\u043d\u0438\u0436\u043e\u043a",
    'FESTIVAL': "\u0440\u0430\u0434\u0430\u0440 \u043f\u043e\u0434\u0456\u0439",
    'TOP_LIST': "\u0432\u0438\u0431\u0456\u0440 \u0440\u0435\u0434\u0430\u043a\u0446\u0456\u0457",
}
MOJIBAKE_TEXT_RE = re.compile(r'(?:[\u0420\u0421][^\s]){3,}')
BROKEN_TEXT_RE = re.compile(r'^\?+$')

def rgba(color: str, alpha: int) -> tuple[int, int, int, int]:
    red, green, blue = ImageColor.getrgb(color)
    return (red, green, blue, max(0, min(alpha, 255)))

BOLD_FONT_CANDIDATES = (
    'Inter-Bold.ttf',
    'Inter-SemiBold.ttf',
    'arialbd.ttf',
    'segoeuib.ttf',
    'tahomabd.ttf',
    'DejaVuSans-Bold.ttf',
)

SEMIBOLD_FONT_CANDIDATES = (
    'Inter-SemiBold.ttf',
    'Inter-Bold.ttf',
    'arialbd.ttf',
    'segoeuib.ttf',
    'tahomabd.ttf',
    'DejaVuSans-Bold.ttf',
)

MEDIUM_FONT_CANDIDATES = (
    'Inter-Medium.ttf',
    'Inter-Regular.ttf',
    'segoeui.ttf',
    'arial.ttf',
    'tahoma.ttf',
    'DejaVuSans.ttf',
)

REGULAR_FONT_CANDIDATES = (
    'Inter-Regular.ttf',
    'Inter-Medium.ttf',
    'segoeui.ttf',
    'arial.ttf',
    'tahoma.ttf',
    'DejaVuSans.ttf',
)

ROLE_DISPLAY_BOLD_FONT_CANDIDATES = (
    'segoeuib.ttf',
    'Inter-Bold.ttf',
    'Inter-SemiBold.ttf',
    'arialbd.ttf',
    'tahomabd.ttf',
    'DejaVuSans-Bold.ttf',
)

ROLE_DISPLAY_SEMIBOLD_FONT_CANDIDATES = (
    'segoeuib.ttf',
    'Inter-SemiBold.ttf',
    'Inter-Bold.ttf',
    'arialbd.ttf',
    'tahomabd.ttf',
    'DejaVuSans-Bold.ttf',
)

ROLE_UI_SEMIBOLD_FONT_CANDIDATES = (
    'segoeuib.ttf',
    'Inter-SemiBold.ttf',
    'Inter-Bold.ttf',
    'arialbd.ttf',
    'tahomabd.ttf',
    'DejaVuSans-Bold.ttf',
)

ROLE_UI_REGULAR_FONT_CANDIDATES = (
    'segoeui.ttf',
    'Inter-Regular.ttf',
    'Inter-Medium.ttf',
    'arial.ttf',
    'tahoma.ttf',
    'DejaVuSans.ttf',
)


class YotoCardType(str, Enum):
    FREE_GAME = 'FREE_GAME'
    DISCOUNT = 'DISCOUNT'
    FESTIVAL = 'FESTIVAL'
    TOP_LIST = 'TOP_LIST'


@dataclass(slots=True, frozen=True)
class YotoCardPalette:
    accent: str
    accent_secondary: str
    glow: str
    panel_top: str
    panel_bottom: str
    deadline_fill: str
    deadline_border: str
    deadline_text: str
    badge_body: tuple[int, int, int, int]
    badge_header_fill: str
    badge_kicker_fill: str
    badge_text_fill: str
    badge_fold_fill: tuple[int, int, int, int]
    brand_fill: str
    meta_accent: str
    panel_kicker: str


@dataclass(slots=True, frozen=True)
class YotoTitleLayout:
    lines: list[str]
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont
    x: int
    y: int
    line_height: int
    meta_y: int
    mode: str


@dataclass(slots=True, frozen=True)
class YotoPrimarySignalLayout:
    text: str
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont
    x: int
    y: int
    width: int
    height: int


@dataclass(slots=True, frozen=True)
class YotoStickerTextLayout:
    lines: list[str]
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont
    line_height: int


@dataclass(slots=True, frozen=True)
class YotoTypographyRole:
    candidates: tuple[str, ...]
    tracking_em: float = 0.0
    force_uppercase: bool = False
    stroke_width: int = 0
    stroke_fill: str = '#050b10'
    shadow_layers: tuple[tuple[int, int, int], ...] = ()


TYPOGRAPHY_ROLES: dict[str, YotoTypographyRole] = {
    'title': YotoTypographyRole(
        candidates=ROLE_DISPLAY_BOLD_FONT_CANDIDATES,
        tracking_em=-0.022,
        stroke_width=1,
        stroke_fill='#050b11',
        shadow_layers=((2, 3, 82), (1, 1, 34)),
    ),
    'platform_badge': YotoTypographyRole(
        candidates=ROLE_UI_SEMIBOLD_FONT_CANDIDATES,
        tracking_em=0.105,
        force_uppercase=True,
        stroke_width=1,
        stroke_fill='#050d13',
    ),
    'badge_header': YotoTypographyRole(
        candidates=ROLE_UI_SEMIBOLD_FONT_CANDIDATES,
        tracking_em=0.1,
        force_uppercase=True,
        stroke_width=1,
        stroke_fill='#060d12',
    ),
    'badge_main': YotoTypographyRole(
        candidates=ROLE_DISPLAY_BOLD_FONT_CANDIDATES,
        tracking_em=-0.01,
        stroke_width=1,
        stroke_fill='#060c12',
    ),
    'badge_footer': YotoTypographyRole(
        candidates=ROLE_UI_SEMIBOLD_FONT_CANDIDATES,
        tracking_em=0.015,
        stroke_width=1,
        stroke_fill='#050b10',
    ),
    'panel_kicker': YotoTypographyRole(
        candidates=ROLE_UI_SEMIBOLD_FONT_CANDIDATES,
        tracking_em=0.145,
        force_uppercase=True,
        stroke_width=1,
        stroke_fill='#051019',
    ),
    'deadline': YotoTypographyRole(
        candidates=ROLE_UI_SEMIBOLD_FONT_CANDIDATES,
        tracking_em=0.012,
        stroke_width=1,
        stroke_fill='#071018',
    ),
    'meta_primary': YotoTypographyRole(
        candidates=ROLE_UI_SEMIBOLD_FONT_CANDIDATES,
        tracking_em=0.012,
        stroke_width=1,
        stroke_fill='#061018',
    ),
    'meta_secondary': YotoTypographyRole(
        candidates=ROLE_UI_REGULAR_FONT_CANDIDATES,
        tracking_em=0.01,
    ),
    'brand_micro': YotoTypographyRole(
        candidates=ROLE_UI_REGULAR_FONT_CANDIDATES,
        tracking_em=0.12,
        force_uppercase=True,
        stroke_width=1,
        stroke_fill='#050b10',
    ),
    'brand_wordmark': YotoTypographyRole(
        candidates=ROLE_DISPLAY_SEMIBOLD_FONT_CANDIDATES,
        tracking_em=0.06,
        force_uppercase=True,
        stroke_width=1,
        stroke_fill='#050b10',
    ),
    'placeholder_micro': YotoTypographyRole(
        candidates=ROLE_UI_SEMIBOLD_FONT_CANDIDATES,
        tracking_em=0.105,
        force_uppercase=True,
        stroke_width=1,
        stroke_fill='#050b10',
    ),
    'placeholder_title': YotoTypographyRole(
        candidates=ROLE_DISPLAY_BOLD_FONT_CANDIDATES,
        tracking_em=-0.012,
        stroke_width=1,
        stroke_fill='#071018',
    ),
    'placeholder_meta': YotoTypographyRole(
        candidates=ROLE_UI_SEMIBOLD_FONT_CANDIDATES,
        tracking_em=0.015,
        stroke_width=1,
        stroke_fill='#050b10',
    ),
}


@dataclass(slots=True)
class YotoHeroSelectionDiagnostics:
    selected_source: str = 'placeholder'
    reason: str = 'intentional_fallback'
    candidates_evaluated: int = 0
    rejected_capsules: list[dict[str, Any]] = field(default_factory=list)
    score_summary: list[dict[str, Any]] = field(default_factory=list)
    fallback_used: bool = False

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any] | None) -> 'YotoHeroSelectionDiagnostics':
        if payload is None:
            return cls()
        rejected_capsules = [dict(item) for item in payload.get('rejected_capsules', []) if isinstance(item, Mapping)]
        score_summary = [dict(item) for item in payload.get('score_summary', []) if isinstance(item, Mapping)]
        return cls(
            selected_source=str(payload.get('selected_source') or 'placeholder'),
            reason=str(payload.get('reason') or 'intentional_fallback'),
            candidates_evaluated=int(payload.get('candidates_evaluated') or len(score_summary)),
            rejected_capsules=rejected_capsules,
            score_summary=score_summary,
            fallback_used=bool(payload.get('fallback_used', False)),
        )

    def to_snapshot(self) -> dict[str, Any]:
        return {
            'selected_source': self.selected_source,
            'reason': self.reason,
            'candidates_evaluated': self.candidates_evaluated,
            'rejected_capsules': [dict(item) for item in self.rejected_capsules],
            'score_summary': [dict(item) for item in self.score_summary],
            'fallback_used': self.fallback_used,
        }


@dataclass(slots=True)
class YotoGameplaySelectionDiagnostics:
    reason: str = 'no_candidates_available'
    candidates_evaluated: int = 0
    selected_count: int = 0
    selected_urls: list[str] = field(default_factory=list)
    ui_like_rejected: int = 0
    score_summary: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any] | None) -> 'YotoGameplaySelectionDiagnostics':
        if payload is None:
            return cls()
        score_summary = [dict(item) for item in payload.get('score_summary', []) if isinstance(item, Mapping)]
        selected_urls = [str(item) for item in payload.get('selected_urls', []) if item is not None]
        return cls(
            reason=str(payload.get('reason') or 'no_candidates_available'),
            candidates_evaluated=int(payload.get('candidates_evaluated') or len(score_summary)),
            selected_count=int(payload.get('selected_count') or len(selected_urls)),
            selected_urls=selected_urls,
            ui_like_rejected=int(payload.get('ui_like_rejected') or 0),
            score_summary=score_summary,
        )

    def to_snapshot(self) -> dict[str, Any]:
        return {
            'reason': self.reason,
            'candidates_evaluated': self.candidates_evaluated,
            'selected_count': self.selected_count,
            'selected_urls': list(self.selected_urls),
            'ui_like_rejected': self.ui_like_rejected,
            'score_summary': [dict(item) for item in self.score_summary],
        }


@dataclass(slots=True)
class YotoCardData:
    title: str
    platform: str
    type: YotoCardType | str
    deadline: str | None
    old_price: str | None
    artwork_path: str | Path | None
    slug: str | None = None
    current_price: str | None = None
    platform_badge: str | None = None
    sticker_header: str | None = None
    sticker_text: str | None = None
    brand_micro_label: str | None = None
    list_label: str | None = None
    editorial_phrase: str | None = None
    gameplay_images: list[str | Path] | None = None
    gameplay_selection: YotoGameplaySelectionDiagnostics | Mapping[str, Any] | None = None
    badge_rotation: float = -6.0
    hero_selection: YotoHeroSelectionDiagnostics | Mapping[str, Any] | None = None
    lane: str | None = None
    genre: str | None = None
    tags: list[str] | None = None
    short_description: str | None = None
    artwork_metadata: dict[str, Any] | None = None
    cover_decision: dict[str, Any] | None = None

    def normalized_type(self) -> YotoCardType:
        return self.type if isinstance(self.type, YotoCardType) else YotoCardType(str(self.type))

    def normalized_slug(self) -> str:
        source = self.slug or self.title
        slug = re.sub(r'[^a-z0-9]+', '_', source.lower()).strip('_')
        return slug or 'card'

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> 'YotoCardData':
        return cls(
            title=str(payload.get('title') or ''),
            platform=str(payload.get('platform') or ''),
            type=payload.get('type') or YotoCardType.FREE_GAME,
            deadline=str(payload['deadline']) if payload.get('deadline') is not None else None,
            old_price=str(payload['old_price']) if payload.get('old_price') is not None else None,
            artwork_path=payload.get('artwork_path'),
            slug=str(payload['slug']) if payload.get('slug') is not None else None,
            current_price=str(payload['current_price']) if payload.get('current_price') is not None else None,
            platform_badge=str(payload['platform_badge']) if payload.get('platform_badge') is not None else None,
            sticker_header=str(payload['sticker_header']) if payload.get('sticker_header') is not None else None,
            sticker_text=str(payload['sticker_text']) if payload.get('sticker_text') is not None else None,
            brand_micro_label=str(payload['brand_micro_label']) if payload.get('brand_micro_label') is not None else None,
            list_label=str(payload['list_label']) if payload.get('list_label') is not None else None,
            editorial_phrase=str(payload['editorial_phrase']) if payload.get('editorial_phrase') is not None else None,
            gameplay_images=[str(item) for item in payload.get('gameplay_images', [])] if payload.get('gameplay_images') else None,
            gameplay_selection=YotoGameplaySelectionDiagnostics.from_mapping(payload.get('gameplay_selection')) if payload.get('gameplay_selection') else None,
            badge_rotation=float(payload.get('badge_rotation') or -6.0),
            hero_selection=YotoHeroSelectionDiagnostics.from_mapping(payload.get('hero_selection')) if payload.get('hero_selection') else None,
            lane=str(payload['lane']) if payload.get('lane') is not None else None,
            genre=str(payload['genre']) if payload.get('genre') is not None else None,
            tags=[str(item) for item in payload.get('tags', []) if str(item).strip()] if payload.get('tags') else None,
            short_description=str(payload['short_description']) if payload.get('short_description') is not None else None,
            artwork_metadata=dict(payload.get('artwork_metadata')) if isinstance(payload.get('artwork_metadata'), Mapping) else None,
            cover_decision=dict(payload.get('cover_decision')) if isinstance(payload.get('cover_decision'), Mapping) else None,
        )

    @classmethod
    def from_offer(cls, offer: Any, *, artwork_path: str | Path | None = None, slug: str | None = None) -> 'YotoCardData':
        type_value = YotoCardType.DISCOUNT
        offer_kind = str(getattr(getattr(offer, 'offer_kind', None), 'value', getattr(offer, 'offer_kind', '')))
        if offer_kind == 'freebie' or bool(getattr(offer, 'is_freebie', False)):
            type_value = YotoCardType.FREE_GAME
        elif offer_kind in {'festival', 'event'} or bool(getattr(offer, 'is_event', False)):
            type_value = YotoCardType.FESTIVAL
        deadline = None
        promo_end = getattr(offer, 'promo_end', None)
        if promo_end is not None:
            formatted_deadline = format_deadline(promo_end)
            if formatted_deadline:
                deadline = f'забрати до {formatted_deadline}'
        old_price = None
        price_before_minor = getattr(offer, 'price_before_minor', None)
        currency = str(getattr(offer, 'currency', 'UAH') or 'UAH').upper()
        if price_before_minor:
            if currency == 'UAH':
                old_price = f"{int(price_before_minor) // 100} грн"
            else:
                old_price = str(price_before_minor)
        artwork = artwork_path or getattr(getattr(offer, 'assets', None), 'hero', None) or getattr(offer, 'primary_asset_url', None)
        platform = str(getattr(getattr(offer, 'source', None), 'value', getattr(offer, 'source', ''))).upper()
        offer_genres = [str(item).strip() for item in getattr(offer, 'genres', []) or [] if str(item).strip()]
        offer_tags = [str(item).strip() for item in getattr(offer, 'tags', []) or [] if str(item).strip()]
        offer_metadata_raw = getattr(offer, 'metadata', {}) or {}
        offer_metadata = dict(offer_metadata_raw) if isinstance(offer_metadata_raw, Mapping) else None
        return cls(
            title=str(getattr(offer, 'title', '')),
            platform=platform,
            type=type_value,
            deadline=deadline,
            old_price=old_price,
            artwork_path=artwork,
            slug=slug or str(getattr(offer, 'title', '')),
            lane=str(getattr(offer, 'lane', '') or getattr(getattr(offer, 'metadata', {}), 'get', lambda *_: None)('lane') or '') or None,
            genre=offer_genres[0] if offer_genres else None,
            tags=offer_tags or None,
            short_description=str(getattr(offer, 'short_description', '') or '').strip() or None,
            artwork_metadata=offer_metadata,
        )


@dataclass(slots=True)
class YotoCardDiagnostics:
    slug: str
    card_type: str
    platform_badge_text: str
    sticker_header: str | None
    sticker_text: str
    badge_footer_text: str | None = None
    text_payload: dict[str, Any] = field(default_factory=dict)
    font_selection: dict[str, dict[str, Any]] = field(default_factory=dict)
    glyph_fallback_used: bool = False
    title_lines: list[str] = field(default_factory=list)
    title_mode: str = 'single_line'
    meta_alignment: str = 'standard'
    used_placeholder_artwork: bool = False
    has_gameplay_strip: bool = False
    gameplay_count: int = 0
    gameplay_candidates_count: int = 0
    gameplay_selected_count: int = 0
    gameplay_selection_reason: str = 'no_candidates_available'
    gameplay_rejected_ui_like: int = 0
    gameplay_score_summary: list[dict[str, Any]] = field(default_factory=list)
    gameplay_selection: dict[str, Any] = field(default_factory=dict)
    editorial_phrase: str | None = None
    hero_rect: tuple[int, int, int, int] = (0, 0, CARD_SIZE[0], HERO_HEIGHT)
    lower_third_rect: tuple[int, int, int, int] = (0, LOWER_THIRD_TOP, CARD_SIZE[0], CARD_SIZE[1])
    hero_source_type: str = 'placeholder'
    hero_selection_reason: str = 'intentional_fallback'
    hero_candidates_count: int = 0
    hero_rejected_capsules: list[dict[str, Any]] = field(default_factory=list)
    hero_score_summary: list[dict[str, Any]] = field(default_factory=list)
    hero_fallback_used: bool = False
    hero_selection: dict[str, Any] = field(default_factory=dict)
    selected_source: str = 'placeholder'
    decision_reason: str = 'placeholder_missing_artwork'
    image_provider_mode: str = 'artwork_only'
    image_priority: str = 'NORMAL'
    image_pipeline_version: str = IMAGE_PIPELINE_VERSION
    ai_attempted: bool = False
    ai_succeeded: bool = False
    output_path: Path | None = None


@dataclass(slots=True)
class YotoCardRenderResult:
    image_path: Path
    diagnostics: YotoCardDiagnostics


class YotoCardEngineV4:
    def __init__(self, output_dir: Path | None = None, *, image_provider_mode: str | None = None) -> None:
        self.repo_root = Path(__file__).resolve().parents[3]
        self.output_dir = output_dir or self.repo_root / 'output' / 'cards'
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.font_dir = self.repo_root / 'video_generator' / 'assets' / 'fonts'
        self._font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}
        self._font_file_cache: dict[tuple[str, int], ImageFont.FreeTypeFont | None] = {}
        self._grain_cache: dict[tuple[int, int], Image.Image] = {}
        self._scanline_cache: dict[tuple[int, int], Image.Image] = {}
        self._placeholder_cache: dict[tuple[str, int, int], Image.Image] = {}
        self._vignette_cache: dict[tuple[int, int], Image.Image] = {}
        self._hero_depth_cache: dict[tuple[tuple[int, int], str], Image.Image] = {}
        self._panel_cache: dict[str, Image.Image] = {}
        self._sticker_cache: dict[tuple[str, str, str, str, float], Image.Image] = {}
        self._gameplay_strip_cache: dict[tuple[str, ...], Image.Image] = {}
        self._artwork_cache: dict[str, Image.Image] = {}
        self.image_provider_mode = str(image_provider_mode or os.getenv('IMAGE_PROVIDER_MODE', 'artwork_only')).strip().lower() or 'artwork_only'
        self.comfyui_enabled = os.getenv('COMFYUI_ENABLED', '0').strip() == '1'
        self.comfyui_url = str(os.getenv('COMFYUI_URL', 'http://127.0.0.1:8188')).strip() or 'http://127.0.0.1:8188'
        self.image_resolver = YotoImageResolver(
            artwork_provider=ArtworkImageProvider(),
            ai_provider=ComfyUIImageProvider(enabled=self.comfyui_enabled, base_url=self.comfyui_url),
            placeholder_provider=PlaceholderImageProvider(self),
            mode=self.image_provider_mode,
        )

    def render_card(self, game_data: YotoCardData | Mapping[str, Any]) -> YotoCardRenderResult:
        data = game_data if isinstance(game_data, YotoCardData) else YotoCardData.from_mapping(game_data)
        self._normalize_card_text_payload(data)
        card_type = data.normalized_type()
        slug = data.normalized_slug()
        diagnostics = YotoCardDiagnostics(
            slug=slug,
            card_type=card_type.value,
            platform_badge_text=self._platform_badge_text(data, card_type),
            sticker_header=self._sticker_header(data, card_type),
            sticker_text=self._sticker_text(data, card_type),
        )
        diagnostics.text_payload = {
            'platform_badge': diagnostics.platform_badge_text,
            'sticker_header': diagnostics.sticker_header,
            'sticker_text': diagnostics.sticker_text,
            'typography_system': 'role_based_segoe_v2',
            'finish_system': 'clean_mvp_v1',
        }
        diagnostics.editorial_phrase = self._normalize_editorial_phrase(data.editorial_phrase)
        gameplay_selection = self._resolve_gameplay_selection(
            data.gameplay_selection,
            gameplay_images=data.gameplay_images,
        )
        diagnostics.gameplay_candidates_count = gameplay_selection.candidates_evaluated
        diagnostics.gameplay_selected_count = gameplay_selection.selected_count
        diagnostics.gameplay_selection_reason = gameplay_selection.reason
        diagnostics.gameplay_rejected_ui_like = gameplay_selection.ui_like_rejected
        diagnostics.gameplay_score_summary = [dict(item) for item in gameplay_selection.score_summary]
        diagnostics.gameplay_selection = gameplay_selection.to_snapshot()

        resolved_image = self.image_resolver.resolve(
            ImageResolutionRequest(
                artwork_path=data.artwork_path,
                title=data.title,
                platform=data.platform,
                slug=slug,
                card_type=card_type.value,
                lane=data.lane,
                mode=self.image_provider_mode,
                priority=self.image_resolver.derive_priority(data.lane),
                image_size=CARD_SIZE,
                deadline=data.deadline,
                old_price=data.old_price,
                current_price=data.current_price,
                platform_badge=data.platform_badge,
                brand_micro_label=data.brand_micro_label,
                genre=data.genre,
                tags=[str(item) for item in data.tags or []] or None,
                short_description=data.short_description,
                artwork_metadata=dict(data.artwork_metadata) if isinstance(data.artwork_metadata, Mapping) else None,
                cover_decision=dict(data.cover_decision) if isinstance(data.cover_decision, Mapping) else None,
            )
        )
        artwork = resolved_image.image
        diagnostics.selected_source = str(resolved_image.metadata.get('selected_source') or 'placeholder')
        diagnostics.decision_reason = str(resolved_image.metadata.get('decision_reason') or 'placeholder_missing_artwork')
        diagnostics.image_provider_mode = str(resolved_image.metadata.get('mode') or self.image_provider_mode)
        diagnostics.image_priority = str(resolved_image.metadata.get('priority') or 'NORMAL')
        diagnostics.image_pipeline_version = str(resolved_image.metadata.get('pipeline_version') or IMAGE_PIPELINE_VERSION)
        diagnostics.ai_attempted = bool(resolved_image.metadata.get('ai_attempted', False))
        diagnostics.ai_succeeded = bool(resolved_image.metadata.get('ai_succeeded', False))
        diagnostics.used_placeholder_artwork = diagnostics.selected_source == 'placeholder'
        diagnostics.text_payload.update({
            'selected_source': diagnostics.selected_source,
            'decision_reason': diagnostics.decision_reason,
            'image_provider_mode': diagnostics.image_provider_mode,
            'image_priority': diagnostics.image_priority,
            'image_pipeline_version': diagnostics.image_pipeline_version,
            'ai_attempted': diagnostics.ai_attempted,
            'ai_succeeded': diagnostics.ai_succeeded,
        })
        if diagnostics.used_placeholder_artwork:
            diagnostics.text_payload['placeholder_caption_mode'] = 'headline_only'
        hero_selection = self._resolve_hero_selection(
            data.hero_selection,
            artwork_path=data.artwork_path,
            used_placeholder=diagnostics.used_placeholder_artwork,
        )
        diagnostics.hero_source_type = hero_selection.selected_source
        diagnostics.hero_selection_reason = hero_selection.reason
        diagnostics.hero_candidates_count = hero_selection.candidates_evaluated
        diagnostics.hero_rejected_capsules = [dict(item) for item in hero_selection.rejected_capsules]
        diagnostics.hero_score_summary = [dict(item) for item in hero_selection.score_summary]
        diagnostics.hero_fallback_used = hero_selection.fallback_used
        diagnostics.hero_selection = hero_selection.to_snapshot()

        background, background_info = self._compose_clean_background(
            artwork,
            used_placeholder=diagnostics.used_placeholder_artwork,
        )
        canvas = background.convert('RGBA')
        layout_profile = self._clean_layout_profile(data, diagnostics, card_type)
        diagnostics.hero_rect = (0, 0, CARD_SIZE[0], CARD_SIZE[1])
        diagnostics.lower_third_rect = (
            0,
            int(layout_profile['gradient_top']),
            CARD_SIZE[0],
            CARD_SIZE[1],
        )
        diagnostics.text_payload.update(
            {
                'composition_mode': str(layout_profile['mode']),
                'title_shelf': 'suppressed',
                'gradient_height': int(layout_profile['gradient_height']),
                'legacy_chrome_removed': True,
                'safe_zone': tuple(int(value) for value in layout_profile['safe_zone']),
                'background_crop_box': tuple(int(value) for value in background_info['crop_box']),
                'background_source_size': tuple(int(value) for value in background_info['source_size']),
                'background_target_size': tuple(int(value) for value in background_info['target_size']),
                'background_bias': tuple(float(value) for value in background_info['bias']),
                'background_zoom_levels': tuple(float(value) for value in background_info['zoom_levels']),
            }
        )
        canvas = self._apply_clean_bottom_gradient(canvas, layout_profile)
        canvas = self._draw_clean_platform_label(canvas, data, diagnostics, card_type, layout_profile)
        canvas, signal_layout = self._draw_clean_primary_signal(canvas, data, diagnostics, card_type, layout_profile)
        canvas, title_layout = self._draw_clean_title(canvas, data, diagnostics, layout_profile, signal_layout)
        diagnostics.title_lines = title_layout.lines
        diagnostics.title_mode = title_layout.mode
        canvas, diagnostics.meta_alignment = self._draw_clean_meta_line(
            canvas,
            data,
            diagnostics,
            card_type,
            layout_profile,
            title_layout,
            signal_layout.text,
        )
        canvas = self._draw_clean_brand_mark(canvas, card_type, diagnostics, layout_profile)
        diagnostics.has_gameplay_strip = False
        diagnostics.gameplay_count = 0

        path = self.output_dir / f'{OUTPUT_PREFIX}{slug}.png'
        canvas.convert('RGB').save(path, format='PNG', compress_level=1)
        diagnostics.output_path = path
        return YotoCardRenderResult(image_path=path, diagnostics=diagnostics)

    def _compose_clean_background(
        self,
        artwork: Image.Image,
        *,
        used_placeholder: bool = False,
    ) -> tuple[Image.Image, dict[str, Any]]:
        source = artwork.convert('RGB') if artwork.mode != 'RGB' else artwork
        bias_x = 0.50
        bias_y = 0.45
        zoom_levels = self._cover_zoom_levels(source.size, CARD_SIZE, used_placeholder=used_placeholder)
        candidate_rows = self._biased_cover_positions(bias_y, step=0.06, lower=0.28, upper=0.66)
        candidate_cols = self._biased_cover_positions(bias_x, step=0.08, lower=0.34, upper=0.66)
        if used_placeholder:
            background, crop_box = self._smart_cover(
                source,
                CARD_SIZE,
                zoom_levels=zoom_levels,
                candidate_rows=candidate_rows,
                candidate_cols=candidate_cols,
                bias_x=bias_x,
                bias_y=bias_y,
                return_crop_box=True,
            )
            background = Image.blend(background, Image.new('RGB', CARD_SIZE, '#090c11'), 0.22)
            overlay = Image.new('RGBA', CARD_SIZE, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            draw.rectangle((0, 0, CARD_SIZE[0], 236), fill=(7, 9, 13, 248))
            fade_height = int(CARD_SIZE[1] * 0.56)
            for y in range(236, fade_height):
                ratio = (y - 236) / max(fade_height - 236, 1)
                alpha = int(228 * ((1.0 - ratio) ** 1.28))
                draw.line((0, y, CARD_SIZE[0], y), fill=(7, 9, 13, alpha))
            composed = Image.alpha_composite(background.convert('RGBA'), overlay).convert('RGB')
            return composed, {
                'crop_box': crop_box,
                'source_size': source.size,
                'target_size': CARD_SIZE,
                'bias': (bias_x, bias_y),
                'zoom_levels': zoom_levels,
            }
        background, crop_box = self._smart_cover(
            source,
            CARD_SIZE,
            zoom_levels=zoom_levels,
            candidate_rows=candidate_rows,
            candidate_cols=candidate_cols,
            bias_x=bias_x,
            bias_y=bias_y,
            return_crop_box=True,
        )
        return background, {
            'crop_box': crop_box,
            'source_size': source.size,
            'target_size': CARD_SIZE,
            'bias': (bias_x, bias_y),
            'zoom_levels': zoom_levels,
        }

    def _clean_layout_profile(
        self,
        data: YotoCardData,
        diagnostics: YotoCardDiagnostics,
        card_type: YotoCardType,
    ) -> dict[str, Any]:
        used_placeholder = diagnostics.used_placeholder_artwork
        primary_signal = self._clean_primary_signal_text(data, diagnostics, card_type)
        safe_left = int(CARD_SIZE[0] * 0.05)
        safe_right = int(CARD_SIZE[0] * 0.55)
        safe_top = int(CARD_SIZE[1] * 0.55)
        safe_bottom = int(CARD_SIZE[1] * 0.95)
        safe_width = safe_right - safe_left
        gradient_height = int(CARD_SIZE[1] * (0.47 if card_type == YotoCardType.DISCOUNT else 0.45))
        if used_placeholder:
            gradient_height += 16
        discount_percent = self._extract_discount_percent(primary_signal if card_type == YotoCardType.DISCOUNT else data.current_price)
        signal_sizes: tuple[int, ...]
        if card_type == YotoCardType.DISCOUNT:
            signal_sizes = self._discount_signal_font_sizes(discount_percent)
        elif card_type == YotoCardType.FREE_GAME:
            signal_sizes = (120, 112, 104, 96, 88, 80)
        else:
            signal_sizes = (116, 108, 100, 92, 84)
        return {
            'mode': f"clean_mvp_{card_type.value.lower()}_{'placeholder' if used_placeholder else 'hero'}",
            'safe_zone': (safe_left, safe_top, safe_right, safe_bottom),
            'content_left': safe_left,
            'content_right': safe_right,
            'gradient_height': gradient_height,
            'gradient_top': CARD_SIZE[1] - gradient_height,
            'signal_top_offset': 24 if card_type == YotoCardType.DISCOUNT else 30,
            'signal_font_sizes': signal_sizes,
            'signal_max_width': safe_width,
            'signal_fill': '#ffca3a' if card_type == YotoCardType.DISCOUNT else self._palette(card_type).accent,
            'signal_stroke_fill': '#53240a' if card_type == YotoCardType.DISCOUNT else '#061018',
            'signal_stroke_width': 2 if card_type == YotoCardType.DISCOUNT else 1,
            'signal_shadow_layers': ((4, 5, 108), (2, 3, 54)),
            'title_gap': 6,
            'title_max_width': safe_width,
            'title_single_sizes': (80, 76, 72, 68, 64, 60, 56),
            'title_multi_sizes': (58, 54, 50, 46, 42, 38),
            'title_line_gap': 4,
            'title_bottom_padding': 44,
            'meta_font_sizes': (26, 24, 22, 20, 18),
            'meta_gap': 16,
            'meta_max_width': safe_width,
            'meta_bottom': safe_bottom - 4,
            'meta_fill': (255, 255, 255, 194),
            'brand_font_size': 24,
            'brand_right': 42,
            'brand_bottom': 676,
            'platform_label_font_size': 26,
            'platform_label_max_width': 340,
            'platform_label_x': 60,
            'platform_label_y': 42,
        }

    def _apply_clean_bottom_gradient(
        self,
        canvas: Image.Image,
        layout_profile: Mapping[str, Any],
    ) -> Image.Image:
        overlay = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        top = int(layout_profile['gradient_top'])
        for y in range(top, CARD_SIZE[1]):
            ratio = (y - top) / max(CARD_SIZE[1] - top - 1, 1)
            eased = ratio ** 1.45
            alpha = int(12 + 228 * eased)
            draw.line((0, y, CARD_SIZE[0], y), fill=(5, 8, 12, max(0, min(alpha, 236))))
        return Image.alpha_composite(canvas.convert('RGBA'), overlay)

    def _draw_clean_platform_label(
        self,
        canvas: Image.Image,
        data: YotoCardData,
        diagnostics: YotoCardDiagnostics,
        card_type: YotoCardType,
        layout_profile: Mapping[str, Any],
    ) -> Image.Image:
        if not data.platform_badge:
            diagnostics.text_payload['platform_badge_rendered'] = False
            return canvas
        overlay = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        text = self._normalize_display_text(data.platform_badge)
        default_text = self._default_platform_badge_text(str(data.platform or ''), card_type)
        if not text or text == default_text or self._is_generic_platform_label(text, str(data.platform or ''), card_type):
            diagnostics.text_payload['platform_badge_rendered'] = False
            return canvas
        role = self._typography_role('platform_badge')
        font = self._load_font_for_text(
            int(layout_profile['platform_label_font_size']),
            role.candidates,
            text,
            diagnostics=diagnostics,
            layer='platform_badge',
        )
        display_text = self._role_text(text, 'platform_badge')
        max_width = int(layout_profile['platform_label_max_width'])
        letter_spacing = self._letter_spacing_px(font, role.tracking_em)
        if self._textlength(draw, display_text, font, letter_spacing=letter_spacing) > max_width:
            display_text = self._ellipsize(draw, display_text, font, max_width, letter_spacing=letter_spacing)
        self._draw_role_text(
            draw,
            (int(layout_profile['platform_label_x']), int(layout_profile['platform_label_y'])),
            display_text,
            font,
            (255, 255, 255, 188),
            role='platform_badge',
            shadow_layers=((1, 2, 28),),
            stroke_width=0,
        )
        diagnostics.platform_badge_text = display_text
        diagnostics.text_payload['platform_badge'] = display_text
        diagnostics.text_payload['platform_badge_rendered'] = True
        return Image.alpha_composite(canvas.convert('RGBA'), overlay)

    def _default_platform_badge_text(self, platform: str, card_type: YotoCardType) -> str:
        normalized_platform = self._normalize_display_text(str(platform or '').upper().strip())
        if card_type == YotoCardType.FREE_GAME:
            return f'{normalized_platform} {GIVEAWAY_LABEL}'.strip() if normalized_platform else GIVEAWAY_LABEL
        if card_type == YotoCardType.DISCOUNT:
            return f'{normalized_platform} {SALE_LABEL}'.strip() if normalized_platform else SALE_LABEL
        if card_type == YotoCardType.FESTIVAL:
            return f'{EVENT_LABEL} {normalized_platform}'.strip() if normalized_platform else EVENT_LABEL
        return f'{normalized_platform} {UA_TOP}'.strip() if normalized_platform else UA_TOP

    def _is_generic_platform_label(self, text: str, platform: str, card_type: YotoCardType) -> bool:
        normalized = self._normalize_display_text(text)
        if not normalized:
            return True
        normalized_fold = normalized.casefold()
        normalized_platform = self._normalize_display_text(str(platform or '').upper())
        generic_labels = {
            self._default_platform_badge_text(platform, card_type).casefold(),
        }
        if normalized_platform:
            generic_labels.update(
                {
                    f'{normalized_platform} discount'.casefold(),
                    f'{normalized_platform} sale'.casefold(),
                    f'{normalized_platform} free'.casefold(),
                    f'{normalized_platform} giveaway'.casefold(),
                    f'{normalized_platform} event'.casefold(),
                    f'{normalized_platform} top'.casefold(),
                }
            )
        if normalized_fold in generic_labels:
            return True
        if normalized_platform and normalized_fold.startswith(normalized_platform.casefold() + ' '):
            tail = normalized_fold[len(normalized_platform) :].strip()
            if tail in {'discount', 'sale', 'free', 'giveaway', 'event', 'top', 'роздача', 'знижка', 'подія'}:
                return True
        return False

    @staticmethod
    def _biased_cover_positions(center: float, *, step: float, lower: float, upper: float) -> tuple[float, ...]:
        values: list[float] = []
        for offset in (-2, -1, 0, 1, 2):
            value = max(lower, min(upper, center + step * offset))
            if value not in values:
                values.append(value)
        return tuple(values)

    @staticmethod
    def _cover_zoom_levels(
        source_size: tuple[int, int],
        target_size: tuple[int, int],
        *,
        used_placeholder: bool,
    ) -> tuple[float, ...]:
        src_w, src_h = source_size
        target_w, target_h = target_size
        if src_w <= 0 or src_h <= 0 or target_w <= 0 or target_h <= 0:
            return (1.0,)
        resolution_ratio = min(src_w / target_w, src_h / target_h)
        if resolution_ratio <= 1.0:
            return (1.0,)
        if resolution_ratio <= 1.25:
            return (1.0, 0.98)
        if used_placeholder:
            return (1.0, 0.98, 0.95)
        return (1.0, 0.98, 0.95, 0.92)

    @staticmethod
    def _extract_discount_percent(value: str | None) -> int | None:
        if not value:
            return None
        match = re.search(r'(\d{1,3})\s*%', str(value))
        if not match:
            return None
        try:
            return max(0, min(100, int(match.group(1))))
        except ValueError:
            return None

    @classmethod
    def _discount_scale_multiplier(cls, discount_percent: int | None) -> float:
        if discount_percent is None:
            return 1.0
        if discount_percent >= 80:
            return 1.25
        if discount_percent >= 70:
            return 1.15
        if discount_percent >= 50:
            return 1.05
        return 1.0

    @classmethod
    def _discount_signal_font_sizes(cls, discount_percent: int | None) -> tuple[int, ...]:
        base_size = 120
        scaled = int(round(base_size * cls._discount_scale_multiplier(discount_percent)))
        max_size = int(round(base_size * 1.3))
        target = max(base_size, min(scaled, max_size))
        values = [target, max(base_size, target - 10), max(base_size, target - 18), base_size]
        deduped: list[int] = []
        for value in values:
            if value not in deduped:
                deduped.append(value)
        return tuple(deduped)

    def _clean_primary_signal_text(
        self,
        data: YotoCardData,
        diagnostics: YotoCardDiagnostics,
        card_type: YotoCardType,
    ) -> str:
        if card_type == YotoCardType.DISCOUNT:
            badge_text = self._normalize_display_text(diagnostics.sticker_text or data.sticker_text or '')
            if badge_text and badge_text != UA_DISCOUNT:
                return badge_text
            if data.current_price and '%' in str(data.current_price):
                return self._normalize_display_text(data.current_price)
            if data.current_price:
                return self._normalize_display_text(data.current_price)
        if data.current_price and card_type != YotoCardType.DISCOUNT:
            return self._normalize_display_text(data.current_price)
        if diagnostics.sticker_text:
            return self._normalize_display_text(diagnostics.sticker_text)
        if card_type == YotoCardType.FREE_GAME:
            return UA_FREE
        if card_type == YotoCardType.DISCOUNT:
            return UA_DISCOUNT
        if card_type == YotoCardType.FESTIVAL:
            return UA_EVENT
        return UA_TOP

    def _draw_clean_primary_signal(
        self,
        canvas: Image.Image,
        data: YotoCardData,
        diagnostics: YotoCardDiagnostics,
        card_type: YotoCardType,
        layout_profile: Mapping[str, Any],
    ) -> tuple[Image.Image, YotoPrimarySignalLayout]:
        overlay = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        text = self._clean_primary_signal_text(data, diagnostics, card_type)
        role = self._typography_role('badge_main')
        layout = self._fit_text_block(
            draw,
            text,
            candidates=role.candidates,
            font_sizes=tuple(int(size) for size in layout_profile['signal_font_sizes']),
            max_width=int(layout_profile['signal_max_width']),
            max_lines=1,
            prefer_multiline=False,
            diagnostics=diagnostics,
            layer='primary_signal',
            tracking_em=role.tracking_em,
        )
        display_text = self._role_text(layout.lines[0], 'badge_main')
        letter_spacing = self._letter_spacing_px(layout.font, role.tracking_em)
        width = int(self._textlength(draw, display_text, layout.font, letter_spacing=letter_spacing))
        bbox = draw.textbbox((0, 0), 'Ag', font=layout.font)
        height = max(1, bbox[3] - bbox[1])
        x = int(layout_profile['content_left'])
        safe_left, safe_top, safe_right, safe_bottom = tuple(int(value) for value in layout_profile['safe_zone'])
        y = max(int(layout_profile['gradient_top']) + int(layout_profile['signal_top_offset']), safe_top + 4)
        self._draw_role_text(
            draw,
            (x, y),
            display_text,
            layout.font,
            str(layout_profile['signal_fill']),
            role='badge_main',
            shadow_layers=tuple(layout_profile['signal_shadow_layers']),
            stroke_width=int(layout_profile['signal_stroke_width']),
            stroke_fill=str(layout_profile['signal_stroke_fill']),
        )
        diagnostics.text_payload['primary_signal'] = display_text
        diagnostics.text_payload['primary_signal_font_size'] = int(getattr(layout.font, 'size', 0) or height)
        diagnostics.text_payload['primary_signal_bounds'] = (x, y, x + width, y + height)
        diagnostics.text_payload['primary_signal_safe_zone'] = (safe_left, safe_top, safe_right, safe_bottom)
        diagnostics.text_payload['discount_percent'] = self._extract_discount_percent(display_text if card_type == YotoCardType.DISCOUNT else data.current_price)
        diagnostics.text_payload['discount_scale_multiplier'] = self._discount_scale_multiplier(diagnostics.text_payload['discount_percent'])
        if card_type == YotoCardType.DISCOUNT:
            diagnostics.text_payload['meta_current_signal'] = display_text
        signal_layout = YotoPrimarySignalLayout(
            text=display_text,
            font=layout.font,
            x=x,
            y=y,
            width=width,
            height=height,
        )
        return Image.alpha_composite(canvas.convert('RGBA'), overlay), signal_layout

    def _resolve_clean_title_layout(
        self,
        draw: ImageDraw.ImageDraw,
        title: str,
        signal_layout: YotoPrimarySignalLayout,
        diagnostics: YotoCardDiagnostics | None,
        layout_profile: Mapping[str, Any],
        *,
        reserve_meta: bool,
    ) -> YotoTitleLayout:
        role = self._typography_role('title')
        normalized_title = self._normalize_display_text(title)
        safe_left, safe_top, safe_right, safe_bottom = tuple(int(value) for value in layout_profile['safe_zone'])
        x = max(int(layout_profile['content_left']), safe_left)
        y = signal_layout.y + signal_layout.height + int(layout_profile['title_gap'])
        max_width = int(layout_profile['title_max_width'])
        meta_reserve = 42 if reserve_meta else 0
        max_height = max(48, min(int(layout_profile['meta_bottom']), safe_bottom) - y - meta_reserve)
        line_gap = int(layout_profile['title_line_gap'])

        for size in tuple(int(value) for value in layout_profile['title_single_sizes']):
            font = self._load_font_for_text(size, role.candidates, normalized_title, diagnostics=diagnostics, layer='title')
            display_text = self._role_text(normalized_title, 'title')
            width = self._textlength(draw, display_text, font, letter_spacing=self._letter_spacing_px(font, role.tracking_em))
            bbox = draw.textbbox((0, 0), 'Ag', font=font)
            line_height = max(1, bbox[3] - bbox[1])
            if width <= max_width and line_height <= max_height:
                return YotoTitleLayout(
                    lines=[normalized_title],
                    font=font,
                    x=x,
                    y=y,
                    line_height=line_height,
                    meta_y=y + line_height + int(layout_profile['meta_gap']),
                    mode='single_line',
                )

        chosen_lines = [normalized_title]
        chosen_font = self._load_font_for_text(46, role.candidates, normalized_title, diagnostics=diagnostics, layer='title')
        chosen_height = max(1, draw.textbbox((0, 0), 'Ag', font=chosen_font)[3] - draw.textbbox((0, 0), 'Ag', font=chosen_font)[1])
        for size in tuple(int(value) for value in layout_profile['title_multi_sizes']):
            font = self._load_font_for_text(size, role.candidates, normalized_title, diagnostics=diagnostics, layer='title')
            lines, clipped = self._wrap_text(draw, normalized_title, font, max_width=max_width, max_lines=2, tracking_em=role.tracking_em)
            if not lines:
                lines = [normalized_title]
            bbox = draw.textbbox((0, 0), 'Ag', font=font)
            line_height = max(1, bbox[3] - bbox[1])
            total_height = len(lines) * line_height + max(0, len(lines) - 1) * line_gap
            chosen_lines = lines
            chosen_font = font
            chosen_height = line_height
            if not clipped and total_height <= max_height:
                return YotoTitleLayout(
                    lines=lines,
                    font=font,
                    x=x,
                    y=y,
                    line_height=line_height,
                    meta_y=y + total_height + int(layout_profile['meta_gap']),
                    mode='two_line' if len(lines) > 1 else 'single_line',
                )

        fitted_lines, _ = self._wrap_text(draw, normalized_title, chosen_font, max_width=max_width, max_lines=2, tracking_em=role.tracking_em)
        if not fitted_lines:
            fitted_lines = [normalized_title]
        total_height = len(fitted_lines) * chosen_height + max(0, len(fitted_lines) - 1) * line_gap
        return YotoTitleLayout(
            lines=fitted_lines[:2],
            font=chosen_font,
            x=x,
            y=y,
            line_height=chosen_height,
            meta_y=y + total_height + int(layout_profile['meta_gap']),
            mode='two_line' if len(fitted_lines) > 1 else 'single_line',
        )

    def _draw_clean_title(
        self,
        canvas: Image.Image,
        data: YotoCardData,
        diagnostics: YotoCardDiagnostics,
        layout_profile: Mapping[str, Any],
        signal_layout: YotoPrimarySignalLayout,
    ) -> tuple[Image.Image, YotoTitleLayout]:
        overlay = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        reserve_meta = bool(self._clean_meta_parts(data, diagnostics, data.normalized_type(), signal_layout.text))
        layout = self._resolve_clean_title_layout(draw, data.title, signal_layout, diagnostics, layout_profile, reserve_meta=reserve_meta)
        title_role = self._typography_role('title')
        widths: list[int] = []
        line_gap = int(layout_profile['title_line_gap'])
        for index, line in enumerate(layout.lines):
            y = layout.y + index * (layout.line_height + line_gap)
            display_text = self._draw_role_text(
                draw,
                (layout.x, y),
                line,
                layout.font,
                WHITE,
                role='title',
                shadow_layers=((4, 5, 122), (2, 3, 68)),
                stroke_width=1,
                stroke_fill='#04070b',
            )
            widths.append(
                int(
                    self._textlength(
                        draw,
                        display_text,
                        layout.font,
                        letter_spacing=self._letter_spacing_px(layout.font, title_role.tracking_em),
                    )
                )
            )
        total_height = len(layout.lines) * layout.line_height + max(0, len(layout.lines) - 1) * line_gap
        diagnostics.text_payload['title_font_size'] = int(getattr(layout.font, 'size', 0) or layout.line_height)
        diagnostics.text_payload['title_bounds'] = (
            layout.x,
            layout.y,
            layout.x + (max(widths) if widths else 0),
            layout.y + total_height,
        )
        diagnostics.text_payload['title_max_width'] = int(layout_profile['title_max_width'])
        diagnostics.text_payload['title_safe_zone'] = tuple(int(value) for value in layout_profile['safe_zone'])
        return Image.alpha_composite(canvas.convert('RGBA'), overlay), layout

    def _clean_meta_parts(
        self,
        data: YotoCardData,
        diagnostics: YotoCardDiagnostics,
        card_type: YotoCardType,
        primary_signal: str,
    ) -> list[str]:
        parts: list[str] = []

        def add(value: str | None) -> None:
            normalized = self._normalize_display_text(value or '')
            if not normalized:
                return
            if normalized.casefold() == primary_signal.casefold():
                return
            if normalized not in parts:
                parts.append(normalized)

        add(data.deadline)
        if card_type == YotoCardType.DISCOUNT:
            if data.current_price and '%' not in data.current_price:
                add(data.current_price)
            else:
                add(data.old_price)
        else:
            add(data.current_price)
            add(data.old_price)
        if not parts:
            add(data.platform_badge)
        if not parts and diagnostics.editorial_phrase:
            add(diagnostics.editorial_phrase)
        return parts[:2]

    def _resolve_clean_meta_text(
        self,
        draw: ImageDraw.ImageDraw,
        parts: list[str],
        diagnostics: YotoCardDiagnostics | None,
        layout_profile: Mapping[str, Any],
    ) -> tuple[str | None, ImageFont.FreeTypeFont | ImageFont.ImageFont | None]:
        if not parts:
            return None, None
        role = self._typography_role('meta_secondary')
        candidates = role.candidates
        attempts = [' · '.join(parts), parts[0]]
        if len(parts) > 1:
            attempts.append(parts[1])
        for text in attempts:
            for size in tuple(int(value) for value in layout_profile['meta_font_sizes']):
                font = self._load_font_for_text(size, candidates, text, diagnostics=diagnostics, layer='meta_secondary')
                width = self._textlength(draw, text, font, letter_spacing=self._letter_spacing_px(font, role.tracking_em))
                if width <= int(layout_profile['meta_max_width']):
                    return text, font
        fallback_text = attempts[0]
        fallback_font = self._load_font_for_text(
            int(tuple(layout_profile['meta_font_sizes'])[-1]),
            candidates,
            fallback_text,
            diagnostics=diagnostics,
            layer='meta_secondary',
        )
        fallback_text = self._ellipsize(
            draw,
            fallback_text,
            fallback_font,
            int(layout_profile['meta_max_width']),
            letter_spacing=self._letter_spacing_px(fallback_font, role.tracking_em),
        )
        return fallback_text, fallback_font

    def _draw_clean_meta_line(
        self,
        canvas: Image.Image,
        data: YotoCardData,
        diagnostics: YotoCardDiagnostics,
        card_type: YotoCardType,
        layout_profile: Mapping[str, Any],
        title_layout: YotoTitleLayout,
        primary_signal: str,
    ) -> tuple[Image.Image, str]:
        if card_type == YotoCardType.DISCOUNT:
            return self._draw_clean_discount_price_block(canvas, data, diagnostics, layout_profile, title_layout, primary_signal)
        parts = self._clean_meta_parts(data, diagnostics, card_type, primary_signal)
        return self._draw_clean_meta_parts_line(canvas, diagnostics, layout_profile, title_layout, parts, data=data)

    def _draw_clean_meta_parts_line(
        self,
        canvas: Image.Image,
        diagnostics: YotoCardDiagnostics,
        layout_profile: Mapping[str, Any],
        title_layout: YotoTitleLayout,
        parts: list[str],
        *,
        data: YotoCardData | None = None,
    ) -> tuple[Image.Image, str]:
        if not parts or title_layout.meta_y > int(layout_profile['meta_bottom']):
            diagnostics.text_payload['meta_parts'] = parts
            return canvas, 'hidden'
        overlay = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        meta_text, font = self._resolve_clean_meta_text(draw, parts, diagnostics, layout_profile)
        if not meta_text or font is None:
            diagnostics.text_payload['meta_parts'] = parts
            return canvas, 'hidden'
        self._draw_role_text(
            draw,
            (int(layout_profile['content_left']), title_layout.meta_y),
            meta_text,
            font,
            tuple(int(value) for value in layout_profile['meta_fill']),
            role='meta_secondary',
            shadow_layers=((1, 2, 26),),
            stroke_width=0,
        )
        diagnostics.text_payload['meta_parts'] = parts
        diagnostics.text_payload['meta_line'] = meta_text
        if data is not None and data.deadline:
            diagnostics.text_payload['meta_deadline'] = self._normalize_display_text(data.deadline)
        if data is not None and data.old_price:
            diagnostics.text_payload['meta_old_price'] = self._normalize_display_text(data.old_price)
        return Image.alpha_composite(canvas.convert('RGBA'), overlay), 'secondary_line'

    def _draw_clean_discount_price_block(
        self,
        canvas: Image.Image,
        data: YotoCardData,
        diagnostics: YotoCardDiagnostics,
        layout_profile: Mapping[str, Any],
        title_layout: YotoTitleLayout,
        primary_signal: str,
    ) -> tuple[Image.Image, str]:
        current_text = self._normalize_display_text(str(data.current_price or '')) if data.current_price else ''
        old_text = self._normalize_display_text(str(data.old_price or '')) if data.old_price else ''
        if current_text and (current_text.casefold() == primary_signal.casefold() or '%' in current_text):
            current_text = ''
        if current_text == '0 грн':
            current_text = 'Безплатно'

        if not current_text:
            parts = self._clean_meta_parts(data, diagnostics, YotoCardType.DISCOUNT, primary_signal)
            return self._draw_clean_meta_parts_line(canvas, diagnostics, layout_profile, title_layout, parts, data=data)

        overlay = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        current_role = self._typography_role('meta_primary')
        old_role = self._typography_role('meta_secondary')
        x = int(layout_profile['content_left'])
        y = title_layout.meta_y
        max_width = int(layout_profile['meta_max_width'])
        current_fill = (255, 244, 235, 236)
        old_fill = (214, 222, 233, 170)
        gap = 18

        def text_width(text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont, tracking: float) -> int:
            return int(self._textlength(draw, text, font, letter_spacing=self._letter_spacing_px(font, tracking)))

        if old_text:
            font_pairs = (
                (36, 24),
                (34, 22),
                (32, 21),
                (30, 20),
                (28, 19),
                (26, 18),
                (24, 17),
            )
            for current_size, old_size in font_pairs:
                current_font = self._load_font_for_text(current_size, current_role.candidates, current_text, diagnostics=diagnostics, layer='price_current')
                old_font = self._load_font_for_text(old_size, old_role.candidates, old_text, diagnostics=diagnostics, layer='price_old')
                current_width = text_width(current_text, current_font, current_role.tracking_em)
                old_width = text_width(old_text, old_font, old_role.tracking_em)
                if current_width + gap + old_width <= max_width:
                    current_y = y - 2
                    display_current = self._draw_role_text(
                        draw,
                        (x, current_y),
                        current_text,
                        current_font,
                        current_fill,
                        role='meta_primary',
                        shadow_layers=((1, 2, 26),),
                        stroke_width=0,
                    )
                    old_bbox = draw.textbbox((0, 0), old_text, font=old_font)
                    old_height = max(1, old_bbox[3] - old_bbox[1])
                    current_bbox = draw.textbbox((0, 0), current_text, font=current_font)
                    current_height = max(1, current_bbox[3] - current_bbox[1])
                    old_x = x + current_width + gap
                    old_y = current_y + max(0, (current_height - old_height) // 2) + 3
                    old_letter_spacing = self._letter_spacing_px(old_font, old_role.tracking_em)
                    display_old = self._draw_role_text(
                        draw,
                        (old_x, old_y),
                        old_text,
                        old_font,
                        old_fill,
                        role='meta_secondary',
                        shadow_layers=((1, 2, 18),),
                        stroke_width=0,
                    )
                    old_bounds = self._textbbox(
                        draw,
                        (old_x, old_y),
                        display_old,
                        old_font,
                        letter_spacing=old_letter_spacing,
                        stroke_width=0,
                    )
                    strike_y = int(round((old_bounds[1] + old_bounds[3]) / 2))
                    draw.line((old_x, strike_y, old_x + old_width, strike_y), fill=(214, 222, 233, 196), width=2)
                    diagnostics.text_payload['meta_current_price'] = display_current
                    diagnostics.text_payload['meta_old_price'] = display_old
                    diagnostics.text_payload['meta_old_price_struck'] = True
                    diagnostics.text_payload['meta_old_price_bounds'] = old_bounds
                    diagnostics.text_payload['meta_old_price_strike_y'] = strike_y
                    diagnostics.text_payload['meta_old_price_strike_formula'] = 'glyph_bbox_vertical_center'
                    diagnostics.text_payload['meta_parts'] = [display_current, display_old]
                    diagnostics.text_payload['meta_line'] = f'{display_current} ~~{display_old}~~'
                    diagnostics.text_payload['meta_price_block_mode'] = 'current_old_strike'
                    return Image.alpha_composite(canvas.convert('RGBA'), overlay), 'price_block_v2'

            fallback_text = f'{old_text} → {current_text}'
            fallback_text, fallback_font = self._resolve_clean_meta_text(draw, [fallback_text], diagnostics, layout_profile)
            if fallback_text and fallback_font is not None:
                self._draw_role_text(
                    draw,
                    (x, y),
                    fallback_text,
                    fallback_font,
                    tuple(int(value) for value in layout_profile['meta_fill']),
                    role='meta_secondary',
                    shadow_layers=((1, 2, 26),),
                    stroke_width=0,
                )
                diagnostics.text_payload['meta_current_price'] = current_text
                diagnostics.text_payload['meta_old_price'] = old_text
                diagnostics.text_payload['meta_old_price_struck'] = False
                diagnostics.text_payload['meta_parts'] = [old_text, current_text]
                diagnostics.text_payload['meta_line'] = fallback_text
                diagnostics.text_payload['meta_price_block_mode'] = 'arrow_fallback'
                return Image.alpha_composite(canvas.convert('RGBA'), overlay), 'price_block_v2'

        current_font = None
        for current_size in (36, 34, 32, 30, 28, 26, 24):
            probe_font = self._load_font_for_text(current_size, current_role.candidates, current_text, diagnostics=diagnostics, layer='price_current')
            if text_width(current_text, probe_font, current_role.tracking_em) <= max_width:
                current_font = probe_font
                break
        if not current_text or current_font is None:
            diagnostics.text_payload['meta_parts'] = []
            return canvas, 'hidden'
        display_current = self._draw_role_text(
            draw,
            (x, y - 2),
            current_text,
            current_font,
            current_fill,
            role='meta_primary',
            shadow_layers=((1, 2, 26),),
            stroke_width=0,
        )
        diagnostics.text_payload['meta_current_price'] = display_current
        diagnostics.text_payload['meta_old_price_struck'] = False
        diagnostics.text_payload['meta_parts'] = [display_current]
        diagnostics.text_payload['meta_line'] = display_current
        diagnostics.text_payload['meta_price_block_mode'] = 'current_only'
        return Image.alpha_composite(canvas.convert('RGBA'), overlay), 'price_block_v2'

    def _draw_clean_brand_mark(
        self,
        canvas: Image.Image,
        card_type: YotoCardType,
        diagnostics: YotoCardDiagnostics,
        layout_profile: Mapping[str, Any],
    ) -> Image.Image:
        overlay = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        role = self._typography_role('brand_wordmark')
        font = self._load_font_for_text(
            int(layout_profile['brand_font_size']),
            role.candidates,
            'YOTO',
            diagnostics=diagnostics,
            layer='brand_wordmark',
        )
        text = 'YOTO'
        width = int(self._textlength(draw, text, font, letter_spacing=self._letter_spacing_px(font, role.tracking_em)))
        x = CARD_SIZE[0] - int(layout_profile['brand_right']) - width
        y = int(layout_profile['brand_bottom']) - max(1, draw.textbbox((0, 0), 'Ag', font=font)[3] - draw.textbbox((0, 0), 'Ag', font=font)[1])
        self._draw_role_text(
            draw,
            (x, y),
            text,
            font,
            (255, 255, 255, 132),
            role='brand_wordmark',
            shadow_layers=((1, 2, 18),),
            stroke_width=0,
        )
        diagnostics.text_payload['brand_micro'] = 'YOTO'
        diagnostics.text_payload['brand_bounds'] = (x, y, x + width, int(layout_profile['brand_bottom']))
        return Image.alpha_composite(canvas.convert('RGBA'), overlay)

    def _normalize_card_text_payload(self, data: YotoCardData) -> None:
        for field_name in ('platform_badge', 'sticker_header', 'sticker_text', 'brand_micro_label', 'list_label'):
            value = getattr(data, field_name)
            if value is None:
                continue
            normalized = self._normalize_display_text(str(value))
            setattr(data, field_name, None if self._is_broken_display_text(normalized) else normalized)

        for field_name in ('deadline', 'old_price', 'current_price', 'editorial_phrase'):
            value = getattr(data, field_name)
            if value is None:
                continue
            normalized = self._normalize_display_text(str(value))
            setattr(data, field_name, None if self._is_broken_display_text(normalized) else normalized)

    def _normalize_display_text(self, value: str) -> str:
        text = re.sub(r'\s+', ' ', str(value or '').replace(' ', ' ')).strip()
        if not text:
            return ''
        repaired = self._repair_mojibake_text(text)
        return re.sub(r'\s+', ' ', repaired).strip()

    def _repair_mojibake_text(self, value: str) -> str:
        best = value
        for encoding in ('cp1251', 'latin1'):
            try:
                candidate = value.encode(encoding).decode('utf-8')
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
            if self._repair_score(candidate) > self._repair_score(best):
                best = candidate
        return best

    def _repair_score(self, value: str) -> tuple[int, int, int, int, int]:
        letters = sum(char.isalpha() for char in value)
        cyrillic_letters = sum('CYRILLIC' in unicodedata.name(char, '') for char in value if char.isalpha())
        ukrainian_markers = sum(char in '\u0456\u0457\u0454\u0491\u0406\u0407\u0404\u0490' for char in value)
        questions = value.count('?')
        mojibake_hits = len(MOJIBAKE_TEXT_RE.findall(value))
        control_chars = sum(
            unicodedata.category(char).startswith('C') and char not in '\n\r\t'
            for char in value
        )
        return (-control_chars, ukrainian_markers, -mojibake_hits, cyrillic_letters, letters - questions * 5)

    @staticmethod
    def _is_broken_display_text(value: str | None) -> bool:
        stripped = str(value or '').strip()
        if not stripped:
            return True
        compact = stripped.replace(' ', '')
        if BROKEN_TEXT_RE.fullmatch(compact):
            return True
        return compact.count('?') >= max(3, len(compact) // 2)

    def _normalize_editorial_phrase(self, phrase: str | None) -> str | None:
        if phrase is None:
            return None
        normalized_phrase = self._normalize_display_text(str(phrase))
        if self._is_broken_display_text(normalized_phrase):
            return None
        words = [part for part in normalized_phrase.strip().split() if part]
        if not 2 <= len(words) <= 3:
            return None
        normalized = ' '.join(words)
        return normalized if len(normalized) <= 32 else None

    def _panel_kicker_text(
        self,
        data: YotoCardData,
        diagnostics: YotoCardDiagnostics,
        card_type: YotoCardType,
    ) -> str | None:
        if card_type == YotoCardType.TOP_LIST and data.list_label:
            return self._normalize_display_text(str(data.list_label))
        if diagnostics.editorial_phrase:
            return diagnostics.editorial_phrase
        return None


    def _resolve_gameplay_selection(
        self,
        payload: YotoGameplaySelectionDiagnostics | Mapping[str, Any] | None,
        *,
        gameplay_images: list[str | Path] | None,
    ) -> YotoGameplaySelectionDiagnostics:
        if isinstance(payload, YotoGameplaySelectionDiagnostics):
            selection = YotoGameplaySelectionDiagnostics.from_mapping(payload.to_snapshot())
        else:
            selection = YotoGameplaySelectionDiagnostics.from_mapping(payload)

        if selection.candidates_evaluated or selection.selected_count or selection.score_summary:
            return selection
        if gameplay_images:
            selected_urls = [str(item) for item in gameplay_images[:3]]
            count = len(selected_urls)
            return YotoGameplaySelectionDiagnostics(
                reason='selected_supplied_frames',
                candidates_evaluated=count,
                selected_count=count,
                selected_urls=selected_urls,
                ui_like_rejected=0,
                score_summary=[],
            )
        return selection

    def _resolve_hero_selection(
        self,
        payload: YotoHeroSelectionDiagnostics | Mapping[str, Any] | None,
        *,
        artwork_path: str | Path | None,
        used_placeholder: bool,
    ) -> YotoHeroSelectionDiagnostics:
        if isinstance(payload, YotoHeroSelectionDiagnostics):
            selection = YotoHeroSelectionDiagnostics.from_mapping(payload.to_snapshot())
        else:
            selection = YotoHeroSelectionDiagnostics.from_mapping(payload)
        if selection.candidates_evaluated <= 0:
            if selection.score_summary:
                selection.candidates_evaluated = len(selection.score_summary)
            elif artwork_path is not None:
                selection.candidates_evaluated = 1
        if used_placeholder:
            selection.selected_source = 'placeholder'
            selection.fallback_used = True
            if not selection.reason or selection.reason == 'selected_primary_hero':
                selection.reason = 'intentional_fallback'
            return selection
        if not selection.selected_source or selection.selected_source == 'placeholder':
            selection.selected_source = 'hero'
        if not selection.reason or selection.reason == 'intentional_fallback':
            selection.reason = 'selected_primary_hero'
        return selection

    def _coerce_card_type(self, value: YotoCardType | str | None) -> YotoCardType:
        if isinstance(value, YotoCardType):
            return value
        return YotoCardType(str(value or YotoCardType.FREE_GAME.value))

    @staticmethod
    def _rgba(color: str, alpha: int) -> tuple[int, int, int, int]:
        return rgba(color, alpha)

    @staticmethod
    def _default_brand_micro_label(card_type: YotoCardType) -> str:
        return BRAND_MICRO_LABELS.get(card_type.value, 'YOTO')

    def load_artwork(
        self,
        artwork_path: str | Path | None,
        *,
        data: YotoCardData | None = None,
        card_type: YotoCardType | None = None,
        diagnostics: YotoCardDiagnostics | None = None,
    ) -> tuple[Image.Image, bool]:
        normalized_card_type = self._coerce_card_type(card_type or (data.normalized_type() if data is not None else YotoCardType.FREE_GAME))
        slug = data.normalized_slug() if data is not None else 'card'
        resolved = self.image_resolver.resolve(
            ImageResolutionRequest(
                artwork_path=artwork_path,
                title=getattr(data, 'title', '') if data is not None else '',
                platform=getattr(data, 'platform', '') if data is not None else '',
                slug=slug,
                card_type=normalized_card_type.value,
                lane=getattr(data, 'lane', None) if data is not None else None,
                mode=self.image_provider_mode,
                priority=self.image_resolver.derive_priority(getattr(data, 'lane', None) if data is not None else None),
                image_size=CARD_SIZE,
                deadline=data.deadline,
                old_price=data.old_price,
                current_price=data.current_price,
                platform_badge=data.platform_badge,
                brand_micro_label=data.brand_micro_label,
                genre=getattr(data, 'genre', None) if data is not None else None,
                tags=([str(item) for item in (getattr(data, 'tags', None) or [])] or None) if data is not None else None,
                short_description=getattr(data, 'short_description', None) if data is not None else None,
                artwork_metadata=dict(getattr(data, 'artwork_metadata', {})) if data is not None and isinstance(getattr(data, 'artwork_metadata', None), Mapping) else None,
                cover_decision=dict(getattr(data, 'cover_decision', {})) if data is not None and isinstance(getattr(data, 'cover_decision', None), Mapping) else None,
            )
        )
        if diagnostics is not None:
            diagnostics.selected_source = str(resolved.metadata.get('selected_source') or diagnostics.selected_source)
            diagnostics.decision_reason = str(resolved.metadata.get('decision_reason') or diagnostics.decision_reason)
            diagnostics.image_provider_mode = str(resolved.metadata.get('mode') or diagnostics.image_provider_mode)
            diagnostics.image_priority = str(resolved.metadata.get('priority') or diagnostics.image_priority)
            diagnostics.image_pipeline_version = str(resolved.metadata.get('pipeline_version') or diagnostics.image_pipeline_version)
            diagnostics.ai_attempted = bool(resolved.metadata.get('ai_attempted', diagnostics.ai_attempted))
            diagnostics.ai_succeeded = bool(resolved.metadata.get('ai_succeeded', diagnostics.ai_succeeded))
            diagnostics.text_payload['ai_attempted'] = diagnostics.ai_attempted
            diagnostics.text_payload['ai_succeeded'] = diagnostics.ai_succeeded
            if diagnostics.selected_source == 'placeholder':
                diagnostics.text_payload['placeholder_caption_mode'] = 'headline_only'
        return resolved.image, str(resolved.metadata.get('selected_source') or '') == 'placeholder'

    def apply_background_treatment(self, artwork: Image.Image, card_type: YotoCardType) -> Image.Image:
        palette = self._palette(card_type)
        backdrop = self._smart_cover(
            artwork,
            (480, 270),
            zoom_levels=(1.0, 0.94, 0.88),
            candidate_rows=(0.28, 0.42, 0.56, 0.70),
        )
        backdrop = backdrop.filter(ImageFilter.GaussianBlur(radius=8)).resize(CARD_SIZE, Image.Resampling.BILINEAR)
        background = Image.blend(backdrop, Image.new('RGB', CARD_SIZE, palette.panel_top), 0.46)
        canvas = background.convert('RGBA')
        canvas = Image.alpha_composite(canvas, Image.new('RGBA', CARD_SIZE, rgba(palette.accent_secondary, 12)))
        canvas = Image.alpha_composite(canvas, self._grain_overlay())
        canvas = Image.alpha_composite(canvas, self._scanline_overlay())
        canvas = Image.alpha_composite(canvas, self._vignette_overlay())
        return canvas.convert('RGB')


    def _top_zone_scaffold_profile(
        self,
        card_type: YotoCardType,
        *,
        top_zone_layout: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        anchor = str((top_zone_layout or {}).get('badge_anchor') or 'top_right')
        right_post_x = {
            'top_right': 1054,
            'top_inset': 1018,
            'right_shoulder': 1066,
        }.get(anchor, 1054)
        right_post_top = 36 if anchor != 'right_shoulder' else 88
        right_post_bottom = 104 if anchor != 'right_shoulder' else 146
        profile: dict[str, Any] = {
            'mode': f"{card_type.value.lower()}_{anchor}",
            'band_left': 28,
            'band_top': 24 if anchor != 'right_shoulder' else 36,
            'band_right': 1246 if anchor != 'top_inset' else 1216,
            'band_bottom': 62 if anchor != 'right_shoulder' else 76,
            'band_radius': 18,
            'band_alpha': 42,
            'band_outline_alpha': 12,
            'rail_left': 52,
            'rail_right': 1214,
            'rail_y': 48 if anchor != 'right_shoulder' else 60,
            'rail_alpha': 28,
            'rail_secondary_alpha': 10,
            'rail_glow_alpha': 18,
            'rail_glow_blur': 10,
            'shadow_alpha': 36,
            'shadow_blur': 12,
            'left_post_rect': (38, 34, 44, 94),
            'right_post_rect': (right_post_x, right_post_top, right_post_x + 6, right_post_bottom),
            'post_alpha': 172,
            'post_shadow_alpha': 28,
        }
        if card_type == YotoCardType.DISCOUNT:
            profile.update({'band_alpha': 40, 'rail_alpha': 24, 'rail_glow_alpha': 16, 'post_alpha': 160})
        elif card_type == YotoCardType.FESTIVAL:
            profile.update({'band_alpha': 46, 'rail_alpha': 30, 'rail_glow_alpha': 20, 'post_alpha': 176})
        elif card_type == YotoCardType.TOP_LIST:
            profile.update({'band_alpha': 44, 'rail_alpha': 26, 'rail_glow_alpha': 18, 'post_alpha': 166})
        else:
            profile.update({'band_alpha': 44, 'rail_alpha': 30, 'rail_glow_alpha': 20, 'post_alpha': 178})
        return profile

    def draw_top_zone_scaffold(
        self,
        canvas: Image.Image,
        card_type: YotoCardType,
        *,
        top_zone_layout: Mapping[str, Any] | None = None,
        diagnostics: YotoCardDiagnostics | None = None,
    ) -> Image.Image:
        palette = self._palette(card_type)
        profile = self._top_zone_scaffold_profile(card_type, top_zone_layout=top_zone_layout)
        overlay = Image.new('RGBA', canvas.size, (0, 0, 0, 0))

        shadow = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rounded_rectangle(
            (
                int(profile['band_left']),
                int(profile['band_top']) + 4,
                int(profile['band_right']),
                int(profile['band_bottom']) + 4,
            ),
            radius=int(profile['band_radius']),
            fill=(0, 0, 0, int(profile['shadow_alpha'])),
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=int(profile['shadow_blur'])))
        overlay = Image.alpha_composite(overlay, shadow)

        draw = ImageDraw.Draw(overlay)
        draw.rounded_rectangle(
            (
                int(profile['band_left']),
                int(profile['band_top']),
                int(profile['band_right']),
                int(profile['band_bottom']),
            ),
            radius=int(profile['band_radius']),
            fill=(6, 11, 17, int(profile['band_alpha'])),
            outline=(255, 255, 255, int(profile['band_outline_alpha'])),
            width=1,
        )
        draw.line(
            (int(profile['rail_left']), int(profile['rail_y']), int(profile['rail_right']), int(profile['rail_y'])),
            fill=rgba(palette.accent_secondary, int(profile['rail_alpha'])),
            width=1,
        )
        draw.line(
            (int(profile['rail_left']), int(profile['rail_y']) + 1, int(profile['rail_right']), int(profile['rail_y']) + 1),
            fill=(255, 255, 255, int(profile['rail_secondary_alpha'])),
            width=1,
        )
        draw.rounded_rectangle(tuple(int(value) for value in profile['left_post_rect']), radius=3, fill=rgba(palette.accent, int(profile['post_alpha'])))
        draw.rounded_rectangle(tuple(int(value) for value in profile['right_post_rect']), radius=3, fill=rgba(palette.accent_secondary, int(profile['post_alpha'])))

        glow = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        glow_draw.line(
            (int(profile['rail_left']), int(profile['rail_y']), int(profile['rail_right']), int(profile['rail_y'])),
            fill=rgba(palette.glow, int(profile['rail_glow_alpha'])),
            width=2,
        )
        glow_draw.rounded_rectangle(tuple(int(value) for value in profile['left_post_rect']), radius=3, fill=rgba(palette.accent, int(profile['post_shadow_alpha'])))
        glow_draw.rounded_rectangle(tuple(int(value) for value in profile['right_post_rect']), radius=3, fill=rgba(palette.accent_secondary, int(profile['post_shadow_alpha'])))
        glow = glow.filter(ImageFilter.GaussianBlur(radius=int(profile['rail_glow_blur'])))
        overlay = Image.alpha_composite(glow, overlay)

        if diagnostics is not None:
            diagnostics.text_payload['top_zone_scaffold_mode'] = str(profile['mode'])
        return Image.alpha_composite(canvas.convert('RGBA'), overlay)


    def draw_platform_badge(
        self,
        canvas: Image.Image,
        text: str,
        card_type: YotoCardType,
        diagnostics: YotoCardDiagnostics | None = None,
        top_zone_layout: Mapping[str, Any] | None = None,
    ) -> Image.Image:
        palette = self._palette(card_type)
        overlay = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        badge_profile = self._platform_badge_visual_profile(text, card_type, diagnostics=diagnostics, top_zone_layout=top_zone_layout)
        display_text = self._role_text(str(badge_profile['display_text']), 'platform_badge')
        if diagnostics is not None:
            diagnostics.platform_badge_text = display_text
            diagnostics.text_payload['platform_badge'] = display_text
            if display_text != text:
                diagnostics.text_payload['platform_badge_compact_source'] = text
        role_spec = self._typography_role('platform_badge')
        font = self._load_font_for_text(int(badge_profile['font_size']), role_spec.candidates, display_text, diagnostics=diagnostics, layer='platform_badge')
        x = int(badge_profile['x'])
        y = int(badge_profile['y'])
        bbox = draw.textbbox((0, 0), display_text, font=font)
        text_width = int(self._textlength(draw, display_text, font, letter_spacing=self._letter_spacing_px(font, role_spec.tracking_em)))
        rect = (
            x,
            y,
            x + text_width + int(badge_profile['pad_left']) + int(badge_profile['pad_right']),
            y + (bbox[3] - bbox[1]) + int(badge_profile['pad_top']) + int(badge_profile['pad_bottom']),
        )
        draw.rounded_rectangle(
            rect,
            radius=int(badge_profile['radius']),
            fill=tuple(int(value) for value in badge_profile['fill']),
            outline=rgba(palette.accent, int(badge_profile['outline_alpha'])),
            width=1,
        )
        draw.rounded_rectangle(
            (
                x + int(badge_profile['indicator_left']),
                y + int(badge_profile['indicator_top']),
                x + int(badge_profile['indicator_right']),
                rect[3] - int(badge_profile['indicator_bottom']),
            ),
            radius=int(badge_profile['indicator_radius']),
            fill=rgba(palette.accent, int(badge_profile['indicator_alpha'])),
        )
        self._draw_role_text(
            draw,
            (x + int(badge_profile['text_x']), y + int(badge_profile['text_y'])),
            display_text,
            font,
            tuple(int(value) for value in badge_profile['text_fill']),
            role='platform_badge',
        )
        return Image.alpha_composite(canvas.convert('RGBA'), overlay)

    def draw_free_or_discount_badge(
        self,
        canvas: Image.Image,
        data: YotoCardData,
        diagnostics: YotoCardDiagnostics,
        card_type: YotoCardType,
        top_zone_layout: Mapping[str, Any] | None = None,
    ) -> Image.Image:
        palette = self._palette(card_type)
        header_role = self._typography_role('badge_header')
        main_role = self._typography_role('badge_main')
        footer_role = self._typography_role('badge_footer')
        main_text, footer_text = self._badge_copy(data, diagnostics, card_type)
        header_text = diagnostics.sticker_header or ''
        display_main = self._role_text(main_text, 'badge_main')
        display_footer = self._role_text(footer_text or '', 'badge_footer') if footer_text else None
        diagnostics.badge_footer_text = display_footer
        diagnostics.text_payload.update(
            {
                'badge_main': display_main,
                'badge_footer': display_footer,
            }
        )
        badge_profile = self._badge_visual_profile(data, diagnostics, card_type, top_zone_layout=top_zone_layout)
        cache_key = (card_type.value, badge_profile['cache_tag'], header_text, display_main, display_footer or '', 1.0)
        cached = self._sticker_cache.get(cache_key)
        if cached is None:
            badge_width = int(badge_profile['badge_width'])
            badge_min_height = int(badge_profile['badge_min_height'])
            measure_draw = ImageDraw.Draw(Image.new('RGBA', (badge_width, 240), (0, 0, 0, 0)))

            header_layout: YotoStickerTextLayout | None = None
            if header_text:
                header_layout = self._fit_text_block(
                    measure_draw,
                    header_text,
                    candidates=header_role.candidates,
                    font_sizes=badge_profile['header_font_sizes'],
                    max_width=badge_width - 98,
                    max_lines=2,
                    prefer_multiline=(' ' in header_text) or len(header_text) > 14,
                    diagnostics=diagnostics,
                    layer='badge_header',
                    tracking_em=header_role.tracking_em,
                )

            main_force_single_line = (
                (card_type == YotoCardType.DISCOUNT and '%' in display_main)
                or (
                    card_type in {YotoCardType.FESTIVAL, YotoCardType.TOP_LIST}
                    and len(display_main.split()) <= 2
                    and len(display_main) <= 10
                )
            )

            main_layout = self._fit_text_block(
                measure_draw,
                display_main,
                candidates=main_role.candidates,
                font_sizes=badge_profile['main_font_sizes'],
                max_width=badge_width - 60,
                max_lines=1 if main_force_single_line else 2,
                prefer_multiline=(not main_force_single_line) and ((' ' in display_main) or ('\n' in display_main) or len(display_main) > 12),
                diagnostics=diagnostics,
                layer='badge_main',
                tracking_em=main_role.tracking_em,
            )

            footer_layout: YotoStickerTextLayout | None = None
            if display_footer:
                footer_layout = self._fit_text_block(
                    measure_draw,
                    display_footer,
                    candidates=footer_role.candidates,
                    font_sizes=badge_profile['footer_font_sizes'],
                    max_width=badge_width - 108,
                    max_lines=2,
                    prefer_multiline=(' ' in display_footer) or len(display_footer) > 12,
                    diagnostics=diagnostics,
                    layer='badge_footer',
                    tracking_em=footer_role.tracking_em,
                )

            header_height = 0
            if header_layout is not None:
                header_height = len(header_layout.lines) * header_layout.line_height + max(0, len(header_layout.lines) - 1) * 2
            main_height = len(main_layout.lines) * main_layout.line_height + max(0, len(main_layout.lines) - 1) * int(badge_profile['main_gap'])
            footer_height = 0
            if footer_layout is not None:
                footer_height = len(footer_layout.lines) * footer_layout.line_height + max(0, len(footer_layout.lines) - 1) * 2
            badge_height = max(badge_min_height, 22 + header_height + (10 if header_height else 0) + main_height + (12 if footer_height else 0) + footer_height + 22)

            badge = Image.new('RGBA', (badge_width, badge_height), (0, 0, 0, 0))
            shadow = Image.new('RGBA', badge.size, (0, 0, 0, 0))
            shadow_draw = ImageDraw.Draw(shadow)
            shadow_draw.rounded_rectangle((8, 8, badge_width - 4, badge_height - 2), radius=24, fill=(0, 0, 0, int(badge_profile['shadow_alpha'])))
            shadow = shadow.filter(ImageFilter.GaussianBlur(radius=int(badge_profile['shadow_blur'])))
            badge = Image.alpha_composite(badge, shadow)

            plate = Image.new('RGBA', badge.size, (0, 0, 0, 0))
            plate_draw = ImageDraw.Draw(plate)
            body_rect = (0, 0, badge_width - 10, badge_height - 10)
            plate_draw.rounded_rectangle(body_rect, radius=24, fill=badge_profile['body_fill'], outline=rgba(palette.accent, int(badge_profile['outline_alpha'])), width=1)
            plate_draw.rounded_rectangle((1, 1, badge_width - 11, max(32, int((badge_height - 10) * 0.26))), radius=24, fill=(255, 255, 255, int(badge_profile['gloss_alpha'])))
            plate_draw.rounded_rectangle(
                (
                    18,
                    int(badge_profile['accent_bar_top']),
                    int(badge_profile['accent_bar_right']),
                    badge_height - int(badge_profile['accent_bar_bottom']),
                ),
                radius=6,
                fill=rgba(palette.accent, int(badge_profile['accent_bar_alpha'])),
            )
            plate_draw.line((38, 14, badge_width - 24, 14), fill=(255, 255, 255, int(badge_profile['top_line_alpha'])), width=1)
            plate_draw.line((38, badge_height - 28, badge_width - 36, badge_height - 28), fill=rgba(palette.accent_secondary, int(badge_profile['bottom_line_alpha'])), width=2)
            badge = Image.alpha_composite(badge, plate)

            draw = ImageDraw.Draw(badge)
            text_x = int(badge_profile['text_x'])
            content_width = badge_width - text_x - 24
            current_y = 18

            if header_layout is not None:
                header_spacing = self._letter_spacing_px(header_layout.font, header_role.tracking_em)
                header_fill = palette.accent_secondary if card_type == YotoCardType.FESTIVAL else palette.accent
                header_text_fill = WHITE if card_type == YotoCardType.FESTIVAL else '#081019'
                header_lines = [self._ellipsize(draw, self._role_text(line, 'badge_header'), header_layout.font, content_width - 20, letter_spacing=header_spacing) for line in header_layout.lines]
                header_text_width = max(int(self._textlength(draw, line, header_layout.font, letter_spacing=header_spacing)) for line in header_lines)
                pill_width = min(content_width, header_text_width + 24)
                pill_height = len(header_lines) * header_layout.line_height + max(0, len(header_lines) - 1) * 2 + 12
                pill_rect = (text_x, current_y, text_x + pill_width, current_y + pill_height)
                draw.rounded_rectangle(pill_rect, radius=12, fill=rgba(header_fill, int(badge_profile['header_fill_alpha'])))
                for index, line in enumerate(header_lines):
                    line_y = current_y + 6 + index * (header_layout.line_height + 2)
                    self._draw_role_text(draw, (text_x + 12, line_y), line, header_layout.font, header_text_fill, role='badge_header', shadow_layers=())
                current_y = pill_rect[3] + 10

            main_fill = tuple(int(value) for value in badge_profile['main_fill'])
            shadow_alpha = int(badge_profile['main_shadow_alpha'])
            main_gap = int(badge_profile['main_gap'])
            for index, line in enumerate(main_layout.lines):
                line_y = current_y + index * (main_layout.line_height + main_gap)
                self._draw_role_text(
                    draw,
                    (text_x, line_y),
                    line,
                    main_layout.font,
                    main_fill,
                    role='badge_main',
                    shadow_layers=((1, 2, shadow_alpha),),
                )
            current_y += main_height

            if footer_layout is not None:
                current_y += 8
                footer_spacing = self._letter_spacing_px(footer_layout.font, footer_role.tracking_em)
                footer_lines = [self._ellipsize(draw, self._role_text(line, 'badge_footer'), footer_layout.font, content_width - 8, letter_spacing=footer_spacing) for line in footer_layout.lines]
                footer_text_fill = badge_profile.get('footer_text_fill', '#ffcfb5' if card_type == YotoCardType.DISCOUNT else '#dbe3ee')
                for index, line in enumerate(footer_lines):
                    line_y = current_y + index * (footer_layout.line_height + 2)
                    self._draw_role_text(draw, (text_x, line_y), line, footer_layout.font, footer_text_fill, role='badge_footer', shadow_layers=())

            glow = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
            glow_draw = ImageDraw.Draw(glow)
            badge_x = CARD_SIZE[0] - SAFE_RIGHT - badge.width + int(badge_profile['badge_x_adjust'])
            badge_y = int(badge_profile['badge_y'])
            glow_draw.ellipse(
                (
                    badge_x - int(badge_profile['glow_pad_left']),
                    badge_y - int(badge_profile['glow_pad_top']),
                    badge_x + badge.width + int(badge_profile['glow_pad_right']),
                    badge_y + badge.height + int(badge_profile['glow_pad_bottom']),
                ),
                fill=rgba(palette.glow, int(badge_profile['glow_alpha'])),
            )
            if card_type == YotoCardType.DISCOUNT:
                glow_draw.ellipse((badge_x - 10, badge_y - 8, badge_x + badge.width + 16, badge_y + badge.height + 10), fill=rgba(DISCOUNT_RED, 20))
            glow = glow.filter(ImageFilter.GaussianBlur(radius=int(badge_profile['glow_blur'])))

            paste = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
            paste.paste(badge, (badge_x, badge_y), badge)
            cached = Image.alpha_composite(glow, paste)
            self._sticker_cache[cache_key] = cached
        return Image.alpha_composite(canvas.convert('RGBA'), cached.copy())

    @staticmethod
    def _selected_media_score_item(score_summary: Sequence[Mapping[str, Any]] | None) -> dict[str, Any] | None:
        if not score_summary:
            return None
        for item in score_summary:
            if bool(item.get('selected')):
                return dict(item)
        return dict(score_summary[0])

    def _normalized_asset_identity(self, value: str | Path | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, Path):
            try:
                return str(value.resolve()).lower()
            except OSError:
                return str(value).lower()
        text_value = str(value).strip()
        if not text_value:
            return None
        if '://' in text_value:
            return text_value.lower()
        resolved = self._resolve_asset_path(text_value)
        if resolved is not None:
            try:
                return str(resolved.resolve()).lower()
            except OSError:
                return str(resolved).lower()
        return text_value.lower()

    @staticmethod
    def _has_prominent_logo_text(score_item: Mapping[str, Any] | None) -> bool:
        if not score_item:
            return False
        text_coverage_ratio = float(score_item.get('text_coverage_ratio') or 0.0)
        if text_coverage_ratio >= 0.40:
            return True
        if text_coverage_ratio >= 0.32 and bool(score_item.get('horizontal_text_block')):
            return True
        return bool(score_item.get('promotional_layout'))

    def _should_suppress_redundant_gameplay_strip(
        self,
        data: YotoCardData,
        card_type: YotoCardType,
        diagnostics: YotoCardDiagnostics | None = None,
    ) -> bool:
        if card_type != YotoCardType.FREE_GAME:
            return False
        platform = self._normalize_display_text(str(data.platform or '').upper())
        if 'EPIC' not in platform:
            return False
        if diagnostics is None or diagnostics.used_placeholder_artwork:
            return False

        hero_item = self._selected_media_score_item(diagnostics.hero_score_summary)
        if not self._has_prominent_logo_text(hero_item):
            return False

        hero_identities = {
            identity
            for identity in (
                self._normalized_asset_identity(data.artwork_path),
                self._normalized_asset_identity(None if hero_item is None else hero_item.get('asset_url')),
            )
            if identity
        }
        if not hero_identities:
            return False

        gameplay_item = self._selected_media_score_item(diagnostics.gameplay_score_summary)
        gameplay_identities = {
            identity
            for identity in (
                *[self._normalized_asset_identity(item) for item in (data.gameplay_images or [])[:3]],
                *[self._normalized_asset_identity(item) for item in diagnostics.gameplay_selection.get('selected_urls', [])],
                self._normalized_asset_identity(None if gameplay_item is None else gameplay_item.get('asset_url')),
            )
            if identity
        }
        same_asset_selected = any(identity in hero_identities for identity in gameplay_identities)
        single_logo_frame = len(data.gameplay_images or []) <= 1 and self._has_prominent_logo_text(gameplay_item)
        return same_asset_selected or single_logo_frame

    def _top_zone_layout_profile(
        self,
        hero_artwork: Image.Image,
        data: YotoCardData,
        diagnostics: YotoCardDiagnostics,
        card_type: YotoCardType,
    ) -> dict[str, Any]:
        layout: dict[str, Any] = {
            'layout_mode': 'default',
            'badge_anchor': 'top_right',
            'platform_badge_overrides': {},
            'badge_overrides': {},
        }
        if diagnostics.used_placeholder_artwork:
            return layout
        if card_type == YotoCardType.DISCOUNT:
            hero_item = self._selected_media_score_item(diagnostics.hero_score_summary)
            logo_heavy = self._has_prominent_logo_text(hero_item)
            badge_width = 224
            badge_height = 102
            candidates = [
                {
                    'name': 'top_right',
                    'badge_y': 40,
                    'badge_x_adjust': 10,
                    'penalty': 0.0,
                },
                {
                    'name': 'top_inset',
                    'badge_y': 42,
                    'badge_x_adjust': -20,
                    'penalty': 8.0,
                },
                {
                    'name': 'right_shoulder',
                    'badge_y': 98,
                    'badge_x_adjust': -10,
                    'penalty': 16.0,
                },
            ]
            best_candidate: dict[str, Any] | None = None
            candidate_scores: dict[str, float] = {}
            for candidate in candidates:
                badge_x = CARD_SIZE[0] - SAFE_RIGHT - badge_width + int(candidate['badge_x_adjust'])
                rect = (
                    max(0, badge_x - 22),
                    max(0, int(candidate['badge_y']) - 16),
                    min(hero_artwork.width, badge_x + badge_width + 24),
                    min(hero_artwork.height, int(candidate['badge_y']) + badge_height + 26),
                )
                score = self._top_zone_candidate_score(hero_artwork, rect) + float(candidate['penalty'])
                candidate_scores[str(candidate['name'])] = round(score, 3)
                if best_candidate is None or score < float(best_candidate['score']):
                    best_candidate = {**candidate, 'score': score}

            top_right_score = float(candidate_scores.get('top_right') or 0.0)
            best_score = float(best_candidate['score']) if best_candidate is not None else top_right_score
            crowded_top = logo_heavy or top_right_score >= 112.0 or (top_right_score - best_score) >= 16.0
            if not crowded_top or best_candidate is None:
                return layout

            compact_source = self._normalize_display_text(str(data.platform or '').upper()) or self._normalize_display_text(str(diagnostics.platform_badge_text or ''))
            layout['platform_badge_overrides'] = {
                'display_text': compact_source,
                'font_size': 15,
                'x': SAFE_LEFT,
                'y': SAFE_TOP - 10,
                'pad_left': 22,
                'pad_right': 14,
                'pad_top': 7,
                'pad_bottom': 8,
                'radius': 12,
                'fill': (11, 14, 18, 206),
                'outline_alpha': 44,
                'indicator_left': 8,
                'indicator_right': 16,
                'indicator_top': 9,
                'indicator_bottom': 9,
                'indicator_radius': 4,
                'indicator_alpha': 212,
                'text_x': 24,
                'text_y': 7,
                'text_fill': (245, 247, 250, 228),
            }
            badge_overrides: dict[str, Any] = {
                'cache_tag': f"discount_signal_compact_{best_candidate['name']}",
                'badge_width': 216,
                'badge_min_height': 98,
                'header_font_sizes': range(14, 10, -1),
                'main_font_sizes': range(40, 24, -2),
                'footer_font_sizes': range(13, 9, -1),
                'shadow_alpha': 84,
                'shadow_blur': 10,
                'body_fill': (12, 9, 8, 202),
                'outline_alpha': 96,
                'gloss_alpha': 4,
                'accent_bar_alpha': 148,
                'accent_bar_top': 16,
                'accent_bar_right': 28,
                'accent_bar_bottom': 26,
                'top_line_alpha': 8,
                'bottom_line_alpha': 22,
                'text_x': 40,
                'header_fill_alpha': 204,
                'main_shadow_alpha': 62,
                'main_gap': 2,
                'footer_fill_alpha': 168,
                'badge_x_adjust': int(best_candidate['badge_x_adjust']),
                'badge_y': int(best_candidate['badge_y']),
                'glow_alpha': 12,
                'glow_blur': 12,
                'glow_pad_left': 14,
                'glow_pad_top': 10,
                'glow_pad_right': 14,
                'glow_pad_bottom': 12,
            }
            if best_candidate['name'] == 'top_inset':
                badge_overrides.update(
                    {
                        'badge_width': 210,
                        'badge_x_adjust': -26,
                        'glow_alpha': 10,
                    }
                )
            elif best_candidate['name'] == 'right_shoulder':
                badge_overrides.update(
                    {
                        'badge_width': 204,
                        'badge_min_height': 94,
                        'main_font_sizes': range(36, 22, -2),
                        'text_x': 38,
                        'badge_x_adjust': -12,
                        'badge_y': 100,
                        'shadow_alpha': 72,
                        'shadow_blur': 9,
                        'glow_alpha': 8,
                        'glow_blur': 10,
                    }
                )

            layout['layout_mode'] = f"discount_signal_compact_{best_candidate['name']}"
            layout['badge_anchor'] = str(best_candidate['name'])
            layout['badge_overrides'] = badge_overrides
            layout['candidate_scores'] = candidate_scores
            return layout
        if card_type in {YotoCardType.FESTIVAL, YotoCardType.TOP_LIST}:
            hero_item = self._selected_media_score_item(diagnostics.hero_score_summary)
            logo_heavy = self._has_prominent_logo_text(hero_item)
            badge_profile = self._badge_visual_profile(data, diagnostics, card_type, top_zone_layout=None)
            badge_width = int(badge_profile['badge_width'])
            badge_height = int(badge_profile['badge_min_height'])
            candidates = [
                {
                    'name': 'top_right',
                    'badge_y': int(badge_profile['badge_y']),
                    'badge_x_adjust': int(badge_profile['badge_x_adjust']),
                    'penalty': 0.0,
                },
                {
                    'name': 'top_inset',
                    'badge_y': 54,
                    'badge_x_adjust': -20,
                    'penalty': 8.0 if card_type == YotoCardType.FESTIVAL else 10.0,
                },
                {
                    'name': 'right_shoulder',
                    'badge_y': 116 if card_type == YotoCardType.FESTIVAL else 110,
                    'badge_x_adjust': -10,
                    'penalty': 18.0,
                },
            ]
            best_candidate: dict[str, Any] | None = None
            candidate_scores: dict[str, float] = {}
            for candidate in candidates:
                badge_x = CARD_SIZE[0] - SAFE_RIGHT - badge_width + int(candidate['badge_x_adjust'])
                rect = (
                    max(0, badge_x - 22),
                    max(0, int(candidate['badge_y']) - 16),
                    min(hero_artwork.width, badge_x + badge_width + 24),
                    min(hero_artwork.height, int(candidate['badge_y']) + badge_height + 24),
                )
                score = self._top_zone_candidate_score(hero_artwork, rect) + float(candidate['penalty'])
                candidate_scores[str(candidate['name'])] = round(score, 3)
                if best_candidate is None or score < float(best_candidate['score']):
                    best_candidate = {**candidate, 'score': score}

            top_right_score = float(candidate_scores.get('top_right') or 0.0)
            best_score = float(best_candidate['score']) if best_candidate is not None else top_right_score
            crowded_top = logo_heavy or top_right_score >= 106.0 or (top_right_score - best_score) >= 14.0
            if crowded_top and best_candidate is not None:
                compact_source = self._normalize_display_text(str(data.platform_badge or diagnostics.platform_badge_text or data.platform or '').upper())
                if card_type == YotoCardType.FESTIVAL and len(compact_source) > 14:
                    compact_source = compact_source.split()[0] if compact_source else 'EVENT'
                elif card_type == YotoCardType.TOP_LIST and len(compact_source) > 14:
                    words = compact_source.split()
                    compact_source = ' '.join(words[:2]) if words else 'TOP'
                layout['platform_badge_overrides'] = {
                    'display_text': compact_source or str(diagnostics.platform_badge_text or ''),
                    'font_size': 14 if card_type == YotoCardType.TOP_LIST else 15,
                    'x': SAFE_LEFT,
                    'y': SAFE_TOP - 8,
                    'pad_left': 22,
                    'pad_right': 14,
                    'pad_top': 7,
                    'pad_bottom': 8,
                    'radius': 12,
                    'fill': (11, 14, 18, 196),
                    'outline_alpha': 40,
                    'indicator_left': 8,
                    'indicator_right': 16,
                    'indicator_top': 9,
                    'indicator_bottom': 9,
                    'indicator_radius': 4,
                    'indicator_alpha': 208,
                    'text_x': 24,
                    'text_y': 7,
                    'text_fill': (245, 247, 250, 228),
                }
                badge_overrides: dict[str, Any] = {
                    'cache_tag': f"{card_type.value.lower()}_editorial_compact_{best_candidate['name']}",
                    'badge_width': max(172, badge_width - 12),
                    'badge_min_height': max(84, badge_height - 6),
                    'text_x': max(36, int(badge_profile['text_x']) - 2),
                    'badge_x_adjust': int(best_candidate['badge_x_adjust']),
                    'badge_y': int(best_candidate['badge_y']),
                    'shadow_alpha': max(72, int(badge_profile['shadow_alpha']) - 10),
                    'shadow_blur': max(10, int(badge_profile['shadow_blur']) - 1),
                    'glow_alpha': max(8, int(badge_profile['glow_alpha']) - 4),
                    'glow_blur': int(badge_profile['glow_blur']),
                }
                if best_candidate['name'] == 'right_shoulder':
                    badge_overrides.update({'badge_width': max(168, int(badge_overrides['badge_width']) - 8), 'badge_min_height': max(82, int(badge_overrides['badge_min_height']) - 2)})
                layout['layout_mode'] = f"{card_type.value.lower()}_editorial_compact_{best_candidate['name']}"
                layout['badge_anchor'] = str(best_candidate['name'])
                layout['badge_overrides'] = badge_overrides
                layout['candidate_scores'] = candidate_scores
            return layout
        if card_type != YotoCardType.FREE_GAME:
            return layout
        platform = self._normalize_display_text(str(data.platform or '').upper())
        if 'EPIC' not in platform:
            return layout
        hero_item = self._selected_media_score_item(diagnostics.hero_score_summary)
        if not self._has_prominent_logo_text(hero_item):
            return layout

        layout['platform_badge_overrides'] = {
            'display_text': 'EPIC',
            'font_size': 16,
            'x': SAFE_LEFT,
            'y': SAFE_TOP - 8,
            'pad_left': 24,
            'pad_right': 16,
            'pad_top': 8,
            'pad_bottom': 9,
            'radius': 13,
            'fill': (11, 14, 18, 214),
            'outline_alpha': 58,
            'indicator_left': 8,
            'indicator_right': 16,
            'indicator_top': 9,
            'indicator_bottom': 9,
            'indicator_radius': 4,
            'indicator_alpha': 214,
            'text_x': 24,
            'text_y': 8,
            'text_fill': (244, 249, 246, 238),
        }

        badge_profile = self._badge_visual_profile(data, diagnostics, card_type, top_zone_layout=None)
        badge_width = int(badge_profile['badge_width'])
        badge_height = int(badge_profile['badge_min_height'])
        candidates = [
            {
                'name': 'top_right',
                'badge_y': int(badge_profile['badge_y']),
                'badge_x_adjust': int(badge_profile['badge_x_adjust']),
                'penalty': 0.0,
            },
            {
                'name': 'top_inset',
                'badge_y': 56,
                'badge_x_adjust': -44,
                'penalty': 14.0,
            },
            {
                'name': 'right_shoulder',
                'badge_y': 126,
                'badge_x_adjust': -20,
                'penalty': 26.0,
            },
        ]

        best_candidate: dict[str, Any] | None = None
        candidate_scores: dict[str, float] = {}
        for candidate in candidates:
            badge_x = CARD_SIZE[0] - SAFE_RIGHT - badge_width + int(candidate['badge_x_adjust'])
            rect = (
                max(0, badge_x - 22),
                max(0, int(candidate['badge_y']) - 16),
                min(hero_artwork.width, badge_x + badge_width + 24),
                min(hero_artwork.height, int(candidate['badge_y']) + badge_height + 26),
            )
            score = self._top_zone_candidate_score(hero_artwork, rect) + float(candidate['penalty'])
            candidate_scores[str(candidate['name'])] = round(score, 3)
            if best_candidate is None or score < float(best_candidate['score']):
                best_candidate = {**candidate, 'score': score}

        if best_candidate is None:
            layout['layout_mode'] = 'epic_logo_balanced_top_right'
            layout['badge_overrides'] = {'cache_tag': 'epic_logo_balanced_top_right'}
            return layout

        badge_overrides: dict[str, Any] = {
            'cache_tag': f"epic_logo_balanced_{best_candidate['name']}",
            'badge_y': int(best_candidate['badge_y']),
            'badge_x_adjust': int(best_candidate['badge_x_adjust']),
        }
        if best_candidate['name'] == 'top_inset':
            badge_overrides.update(
                {
                    'badge_width': 308,
                    'text_x': 42,
                    'shadow_alpha': 96,
                    'shadow_blur': 11,
                    'glow_alpha': 14,
                    'glow_blur': 13,
                }
            )
        elif best_candidate['name'] == 'right_shoulder':
            badge_overrides.update(
                {
                    'badge_width': 300,
                    'badge_min_height': 114,
                    'header_font_sizes': range(14, 10, -1),
                    'main_font_sizes': range(34, 21, -2),
                    'footer_font_sizes': range(14, 10, -1),
                    'text_x': 40,
                    'shadow_alpha': 82,
                    'shadow_blur': 11,
                    'glow_alpha': 12,
                    'glow_blur': 12,
                    'glow_pad_left': 16,
                    'glow_pad_top': 12,
                    'glow_pad_right': 16,
                    'glow_pad_bottom': 12,
                }
            )

        layout['layout_mode'] = f"epic_logo_balanced_{best_candidate['name']}"
        layout['badge_anchor'] = str(best_candidate['name'])
        layout['badge_overrides'] = badge_overrides
        layout['candidate_scores'] = candidate_scores
        return layout

    def _top_zone_candidate_score(self, hero_artwork: Image.Image, rect: tuple[int, int, int, int]) -> float:
        left, top, right, bottom = rect
        if right <= left or bottom <= top:
            return float('inf')
        crop = hero_artwork.crop((left, top, right, bottom)).convert('L')
        if crop.width <= 0 or crop.height <= 0:
            return float('inf')
        edges = crop.filter(ImageFilter.FIND_EDGES)
        luminance = float(ImageStat.Stat(crop).mean[0])
        edge_mean = float(ImageStat.Stat(edges).mean[0])
        bright_ratio = float(ImageStat.Stat(crop.point(lambda value: 255 if value >= 176 else 0)).mean[0]) / 255.0
        edge_ratio = float(ImageStat.Stat(edges.point(lambda value: 255 if value >= 78 else 0)).mean[0]) / 255.0
        return edge_mean * 0.68 + bright_ratio * 96.0 + edge_ratio * 124.0 + max(luminance - 144.0, 0.0) * 0.42

    def _apply_premium_finish_profile(
        self,
        panel_profile: Mapping[str, Any],
        title_profile: Mapping[str, Any],
        meta_profile: Mapping[str, Any],
        brand_profile: Mapping[str, Any],
        *,
        card_type: YotoCardType,
        mode_kind: str,
        brightness_band: str,
        top_zone_layout: Mapping[str, Any] | None = None,
        signal_kind: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
        panel = dict(panel_profile)
        title = dict(title_profile)
        meta = dict(meta_profile)
        brand = dict(brand_profile)

        row_rect = tuple(panel.get('row_rect', (0, 658, 1280, 720)))
        divider_x = int(panel.get('brand_divider_x', 996) or 996)
        title_lane_y = min(int(row_rect[1]) - 28, int(panel.get('top_line_y', 522)) + 36)
        panel.update(
            {
                'shadow_alpha': max(int(panel.get('shadow_alpha', 0)), 72),
                'shadow_blur': max(int(panel.get('shadow_blur', 0)), 18),
                'top_line_alpha': max(int(panel.get('top_line_alpha', 0)), 10),
                'row_line_alpha': max(int(panel.get('row_line_alpha', 0)), 10),
                'title_lane_y': title_lane_y,
                'title_lane_left': 82,
                'title_lane_right': divider_x - 34,
                'title_lane_alpha': 12,
                'title_lane_secondary_alpha': 7,
                'title_lane_glow_alpha': 14,
                'title_lane_glow_blur': 10,
                'row_glow_alpha': 14,
                'row_glow_blur': 12,
                'kicker_font_size': 13,
                'kicker_rule_gap': 20,
                'kicker_rule_right': divider_x - 34,
                'kicker_rule_alpha': 40,
            }
        )
        title.update(
            {
                'line_gap': max(int(title.get('line_gap', 0)), 2),
                'plate_alpha': int(title.get('plate_alpha', 0) or 0),
                'plate_outline_alpha': int(title.get('plate_outline_alpha', 0) or 0),
                'plate_shadow_alpha': int(title.get('plate_shadow_alpha', 0) or 0),
                'plate_shadow_blur': max(int(title.get('plate_shadow_blur', 0) or 0), 14),
                'plate_radius': int(title.get('plate_radius', 22) or 22),
                'plate_pad_left': int(title.get('plate_pad_left', 18) or 18),
                'plate_pad_right': int(title.get('plate_pad_right', 24) or 24),
                'plate_pad_top': int(title.get('plate_pad_top', 10) or 10),
                'plate_pad_bottom': int(title.get('plate_pad_bottom', 12) or 12),
                'plate_accent_width': int(title.get('plate_accent_width', 4) or 4),
                'plate_gloss_alpha': int(title.get('plate_gloss_alpha', 0) or 0),
                'plate_connector_alpha': int(title.get('plate_connector_alpha', 0) or 0),
                'plate_connector_secondary_alpha': int(title.get('plate_connector_secondary_alpha', 0) or 0),
                'plate_connector_right': max(int(title.get('plate_connector_right', 0) or 0), divider_x - 30),
                'plate_connector_bottom_offset': int(title.get('plate_connector_bottom_offset', 12) or 12),
                'title_shelf_mode': str(title.get('title_shelf_mode', 'suppressed') or 'suppressed'),
            }
        )
        meta.update(
            {
                'chip_height': max(int(meta.get('chip_height', 0) or 0), 36),
                'gap': max(8, int(meta.get('gap', 0) or 0)),
                'y_offset': max(4, int(meta.get('y_offset', 6) or 6) - 1),
            }
        )
        brand.update(
            {
                'height': min(int(brand.get('height', 50) or 50), 48),
                'width': min(int(brand.get('width', 206) or 206), 200),
                'radius': min(int(brand.get('radius', 16) or 16), 16),
                'shadow_alpha': max(int(brand.get('shadow_alpha', 0) or 0), 34),
                'fill_alpha': max(int(brand.get('fill_alpha', 0) or 0), 144),
                'outline_alpha': max(int(brand.get('outline_alpha', 0) or 0), 14),
                'accent_line_alpha': min(int(brand.get('accent_line_alpha', 108) or 108), 88),
                'icon_size': min(int(brand.get('icon_size', 30) or 30), 30),
                'body_font_size': min(int(brand.get('body_font_size', 23) or 23), 23),
                'micro_font_size': min(int(brand.get('micro_font_size', 11) or 11), 11),
            }
        )
        if 'y' in brand:
            brand['y'] = max(596, int(brand.get('y', 614) or 614) - 4)
        panel['brand_divider_top'] = max(0, int(panel.get('brand_divider_top', 616) or 616) - 4)
        panel['brand_divider_bottom'] = max(int(panel['brand_divider_top']) + 32, int(panel.get('brand_divider_bottom', 670) or 670) - 4)
        title['plate_min_width'] = min(int(title.get('plate_min_width', 324) or 324), 304 if card_type in {YotoCardType.FREE_GAME, YotoCardType.DISCOUNT} else 292)

        if brightness_band == 'dark':
            title['halo_alpha'] = max(int(title.get('halo_alpha', 0) or 0), 96)
            panel['row_alpha'] = max(int(panel.get('row_alpha', 0)), 192)
        elif brightness_band == 'bright':
            title['halo_alpha'] = max(int(title.get('halo_alpha', 0) or 0), 90)
            panel['row_alpha'] = max(int(panel.get('row_alpha', 0)), 194)
        else:
            title['halo_alpha'] = max(int(title.get('halo_alpha', 0) or 0), 86)

        if mode_kind == 'logo':
            panel['kicker_alpha'] = max(int(panel.get('kicker_alpha', 0)), 112)
            title['halo_alpha'] = max(int(title.get('halo_alpha', 0) or 0), 92)
        elif mode_kind == 'fallback':
            title.update(
                {
                    'title_shelf_mode': 'fallback_soft',
                    'plate_alpha': max(int(title.get('plate_alpha', 0) or 0), 52),
                    'plate_outline_alpha': max(int(title.get('plate_outline_alpha', 0) or 0), 14),
                    'plate_shadow_alpha': max(int(title.get('plate_shadow_alpha', 0) or 0), 30),
                    'plate_shadow_blur': max(int(title.get('plate_shadow_blur', 0) or 0), 12),
                    'plate_pad_left': min(int(title.get('plate_pad_left', 18) or 18), 18),
                    'plate_pad_right': min(int(title.get('plate_pad_right', 22) or 22), 22),
                    'plate_pad_top': min(int(title.get('plate_pad_top', 10) or 10), 10),
                    'plate_pad_bottom': min(int(title.get('plate_pad_bottom', 12) or 12), 12),
                    'plate_accent_alpha': max(int(title.get('plate_accent_alpha', 0) or 0), 78),
                    'plate_accent_width': min(max(int(title.get('plate_accent_width', 4) or 4), 4), 4),
                    'plate_gloss_alpha': 0,
                    'plate_connector_alpha': 0,
                    'plate_connector_secondary_alpha': 0,
                }
            )
            panel['front_alpha'] = max(int(panel.get('front_alpha', 0)), 182)
            panel['row_alpha'] = max(int(panel.get('row_alpha', 0)), 194)
            panel['title_lane_alpha'] = max(int(panel.get('title_lane_alpha', 0)), 12)
            panel['title_lane_glow_alpha'] = max(int(panel.get('title_lane_glow_alpha', 0)), 16)
            brand['fill_alpha'] = max(int(brand['fill_alpha']), 150)
        else:
            title.update(
                {
                    'plate_alpha': 0,
                    'plate_outline_alpha': 0,
                    'plate_shadow_alpha': 0,
                    'plate_accent_alpha': 0,
                    'plate_gloss_alpha': 0,
                    'plate_connector_alpha': 0,
                    'plate_connector_secondary_alpha': 0,
                }
            )

        if str((top_zone_layout or {}).get('badge_anchor') or '') == 'right_shoulder':
            panel['kicker_rule_right'] = divider_x - 52
            if title.get('plate_alpha', 0):
                title['plate_connector_right'] = max(int(title['plate_connector_right']), divider_x - 46)

        if card_type == YotoCardType.FREE_GAME:
            panel.update({'accent_alpha': max(int(panel.get('accent_alpha', 0)), 18), 'gradient_top': '#11232d', 'gradient_bottom': '#0d171f', 'glow_alpha': max(int(panel.get('glow_alpha', 0)), 14), 'kicker_alpha': max(int(panel.get('kicker_alpha', 0)), 108)})
            title.update({'plate_fill': '#08161d', 'halo_fill': '#07131a', 'halo_alpha': max(int(title.get('halo_alpha', 0) or 0), 88)})
            meta.update({'secondary_fill': (255, 255, 255, 12), 'secondary_outline_alpha': max(int(meta.get('secondary_outline_alpha', 0) or 0), 28), 'secondary_text_fill': (216, 224, 232, 208), 'deadline_fill_alpha': max(int(meta.get('deadline_fill_alpha', 0) or 0), 180), 'deadline_outline_alpha': max(int(meta.get('deadline_outline_alpha', 0) or 0), 88)})
            brand.update({'width': 194, 'fill_alpha': max(int(brand['fill_alpha']), 146)})
        elif card_type == YotoCardType.DISCOUNT:
            panel.update({'accent_alpha': max(int(panel.get('accent_alpha', 0)), 18), 'gradient_top': '#1c2533', 'gradient_bottom': '#17100d', 'glow_alpha': max(int(panel.get('glow_alpha', 0)), 12), 'kicker_alpha': max(int(panel.get('kicker_alpha', 0)), 108)})
            title.update({'plate_fill': '#091018', 'halo_fill': '#081119', 'halo_alpha': max(int(title.get('halo_alpha', 0) or 0), 86)})
            meta.update({'current_fill_alpha': max(int(meta.get('current_fill_alpha', 0) or 0), 220), 'current_outline_alpha': max(int(meta.get('current_outline_alpha', 0) or 0), 186), 'secondary_fill': (255, 255, 255, 12), 'secondary_outline_alpha': max(int(meta.get('secondary_outline_alpha', 0) or 0), 28), 'secondary_text_fill': (220, 226, 234, 210), 'deadline_fill_alpha': max(int(meta.get('deadline_fill_alpha', 0) or 0), 180), 'deadline_outline_alpha': max(int(meta.get('deadline_outline_alpha', 0) or 0), 90)})
            if signal_kind == 'percent':
                meta.update({'current_font_size_single_percent': max(int(meta.get('current_font_size_single_percent', 0) or 0), 25), 'current_font_size_two_percent': max(int(meta.get('current_font_size_two_percent', 0) or 0), 23)})
            brand.update({'width': 198, 'fill_alpha': max(int(brand['fill_alpha']), 144)})
        elif card_type == YotoCardType.FESTIVAL:
            panel.update({'accent_alpha': max(int(panel.get('accent_alpha', 0)), 22), 'gradient_top': '#0e2137', 'gradient_bottom': '#111931', 'glow_alpha': max(int(panel.get('glow_alpha', 0)), 16), 'kicker_alpha': max(int(panel.get('kicker_alpha', 0)), 110), 'top_line_alpha': max(int(panel.get('top_line_alpha', 0)), 12)})
            title.update({'plate_fill': '#081826', 'halo_fill': '#081927', 'halo_alpha': max(int(title.get('halo_alpha', 0) or 0), 90)})
            meta.update({'primary_fill': '#154257', 'primary_fill_alpha': max(int(meta.get('primary_fill_alpha', 0) or 0), 208), 'primary_outline_alpha': max(int(meta.get('primary_outline_alpha', 0) or 0), 182), 'secondary_fill': (118, 97, 180, 16), 'secondary_outline_alpha': max(int(meta.get('secondary_outline_alpha', 0) or 0), 30), 'secondary_text_fill': (226, 232, 243, 210)})
            brand.update({'width': 196, 'fill_alpha': max(int(brand['fill_alpha']), 146)})
        elif card_type == YotoCardType.TOP_LIST:
            panel.update({'accent_alpha': max(int(panel.get('accent_alpha', 0)), 20), 'gradient_top': '#281b0c', 'gradient_bottom': '#111319', 'glow_alpha': max(int(panel.get('glow_alpha', 0)), 14), 'kicker_alpha': max(int(panel.get('kicker_alpha', 0)), 110), 'top_line_alpha': max(int(panel.get('top_line_alpha', 0)), 12)})
            title.update({'plate_fill': '#120f09', 'halo_fill': '#171006', 'halo_alpha': max(int(title.get('halo_alpha', 0) or 0), 88)})
            meta.update({'primary_fill': '#5a4012', 'primary_fill_alpha': max(int(meta.get('primary_fill_alpha', 0) or 0), 204), 'primary_outline_alpha': max(int(meta.get('primary_outline_alpha', 0) or 0), 178), 'secondary_fill': (242, 201, 112, 14), 'secondary_outline_alpha': max(int(meta.get('secondary_outline_alpha', 0) or 0), 28), 'secondary_text_fill': (238, 229, 201, 212)})
            brand.update({'width': 198, 'fill_alpha': max(int(brand['fill_alpha']), 146)})

        panel['accent_alpha'] = min(int(panel.get('accent_alpha', 0)), 22 if card_type in {YotoCardType.FESTIVAL, YotoCardType.TOP_LIST} else 18)
        panel['kicker_alpha'] = min(int(panel.get('kicker_alpha', 0)), 118 if mode_kind == 'fallback' else 112)
        panel['kicker_rule_alpha'] = min(int(panel.get('kicker_rule_alpha', 40) or 40), 46 if mode_kind == 'fallback' else 40)
        panel['title_lane_alpha'] = min(int(panel.get('title_lane_alpha', 12) or 12), 14 if mode_kind == 'fallback' else 12)
        panel['title_lane_secondary_alpha'] = min(int(panel.get('title_lane_secondary_alpha', 7) or 7), 8 if mode_kind == 'fallback' else 7)
        panel['title_lane_glow_alpha'] = min(int(panel.get('title_lane_glow_alpha', 14) or 14), 18 if mode_kind == 'fallback' else 14)
        panel['row_glow_alpha'] = min(int(panel.get('row_glow_alpha', 14) or 14), 14)
        rail_rect = tuple(int(value) for value in panel.get('accent_rail_rect', (68, 518, 124, 522)))
        rail_width = rail_rect[2] - rail_rect[0]
        if rail_width > 40:
            panel['accent_rail_rect'] = (rail_rect[0], rail_rect[1], rail_rect[0] + max(40, rail_width - 12), rail_rect[3])

        return panel, title, meta, brand

    def _composition_profile(
        self,
        hero_artwork: Image.Image,
        data: YotoCardData,
        diagnostics: YotoCardDiagnostics,
        card_type: YotoCardType,
        top_zone_layout: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if card_type == YotoCardType.DISCOUNT:
            hero_luminance = float(ImageStat.Stat(hero_artwork.convert('L')).mean[0]) / 255.0
            if hero_luminance >= 0.56:
                brightness_band = 'bright'
            elif hero_luminance <= 0.36:
                brightness_band = 'dark'
            else:
                brightness_band = 'balanced'

            hero_item = self._selected_media_score_item(diagnostics.hero_score_summary)
            logo_heavy = self._has_prominent_logo_text(hero_item)
            fallback = diagnostics.used_placeholder_artwork
            long_title = len(data.title) > 24 or len(data.title.split()) > 4
            short_title = len(data.title) <= 11
            current_signal = self._normalize_display_text(str(data.current_price or ''))
            signal_kind = 'percent' if '%' in current_signal else ('price' if current_signal else 'fallback')
            mode_kind = 'fallback' if fallback else ('logo' if logo_heavy else 'clean')

            panel_profile: dict[str, Any] = {
                'cache_tag': f'discount_system_{mode_kind}_{brightness_band}_{signal_kind}',
                'back_points': [(0, 524), (232, 524), (350, 484), (1280, 484), (1280, 720), (0, 720)],
                'front_points': [(0, 540), (290, 540), (372, 510), (1214, 510), (1280, 530), (1280, 720), (0, 720)],
                'accent_points': [(0, 540), (138, 540), (246, 510), (312, 510), (226, 720), (0, 720)],
                'row_rect': (0, 658, 1280, 720),
                'shadow_offset': 12,
                'shadow_alpha': 70,
                'shadow_blur': 16,
                'back_alpha': 130,
                'front_alpha': 176,
                'row_alpha': 186,
                'accent_alpha': 20,
                'gradient_top': '#18283a',
                'gradient_bottom': '#17100d',
                'gradient_alpha': 122,
                'top_line_y': 524,
                'top_line_alpha': 8,
                'accent_rail_rect': (68, 518, 126, 522),
                'row_line_alpha': 10,
                'glow_alpha': 16,
                'glow_blur': 7,
                'brand_divider_x': 1000,
                'brand_divider_top': 616,
                'brand_divider_bottom': 670,
                'brand_divider_alpha': 10,
                'kicker_x': 76,
                'kicker_y': 520,
                'kicker_alpha': 108,
            }
            title_profile: dict[str, Any] = {
                'x': 72,
                'single_configs': ((64, 800, 536, 56), (60, 786, 532, 54), (56, 772, 528, 50), (52, 756, 524, 48)),
                'two_line_configs': ((52, 782, 500, 48), (48, 770, 506, 44), (44, 758, 510, 40), (40, 744, 514, 38)),
                'meta_y_single': 616,
                'meta_y_two': 640,
                'prefer_two_lines': long_title,
                'two_line_threshold': 22,
                'shadow_layers': ((3, 4, 110), (1, 2, 76)),
                'halo_fill': '#07131b',
                'halo_alpha': 80,
                'halo_blur': 28,
                'halo_pad_x': 40,
                'halo_pad_y': 24,
                'halo_radius': 26,
            }
            meta_profile: dict[str, Any] = {
                'x': 82,
                'y_offset': 8,
                'gap': 10,
                'chip_height': 36,
                'max_right': 992,
                'current_radius': 14,
                'current_padding_x': 30,
                'current_text_x': 16,
                'current_text_y': 5,
                'current_font_size_single_percent': 24,
                'current_font_size_two_percent': 22,
                'current_font_size_single_price': 21,
                'current_font_size_two_price': 19,
                'current_fill_percent': '#4a1f11',
                'current_fill_price': '#332117',
                'current_fill_alpha': 214,
                'current_outline_percent': DISCOUNT_ORANGE,
                'current_outline_price': '#ffb35a',
                'current_outline_alpha': 186,
                'current_text_fill': '#fff3eb',
                'secondary_fill': (255, 255, 255, 12),
                'secondary_outline_alpha': 28,
                'secondary_radius': 14,
                'secondary_text_fill': (214, 221, 231, 198),
                'old_price_padding_x': 30,
                'old_price_text_x': 16,
                'old_price_text_y': 6,
                'old_price_font_size': 19,
                'deadline_radius': 14,
                'deadline_fill': '#29160f',
                'deadline_fill_alpha': 172,
                'deadline_outline': '#ffb35a',
                'deadline_outline_alpha': 74,
                'deadline_text_fill': '#ffd9c7',
                'deadline_padding_x': 44,
                'deadline_text_x': 16,
                'deadline_text_y': 6,
                'deadline_font_size_single': 19,
                'deadline_font_size_two': 18,
                'deadline_max_width': 232,
            }
            brand_profile: dict[str, Any] = {
                'style': 'grid_chip',
                'x': 1020,
                'y': 614,
                'width': 204,
                'height': 50,
                'radius': 16,
                'shadow_alpha': 40,
                'shadow_blur': 8,
                'fill_alpha': 150,
                'outline_alpha': 12,
                'accent_line_alpha': 108,
                'icon_left': 14,
                'icon_top': 10,
                'icon_size': 30,
                'icon_radius': 10,
                'y_font_size': 20,
                'y_text_x': 9,
                'y_text_y': 4,
                'text_x': 54,
                'micro_font_size': 11,
                'micro_y': 6,
                'body_font_size': 23,
                'body_y': 17,
            }

            if brightness_band == 'bright':
                panel_profile.update({'front_alpha': 184, 'row_alpha': 194, 'gradient_alpha': 132, 'glow_alpha': 18})
                title_profile['shadow_layers'] = ((3, 4, 122), (1, 2, 88))
                title_profile.update({'halo_alpha': 92})
                meta_profile.update({'secondary_fill': (255, 255, 255, 10), 'secondary_text_fill': (220, 227, 236, 208)})
                brand_profile.update({'fill_alpha': 160, 'shadow_alpha': 46})
            elif brightness_band == 'dark':
                panel_profile.update({'front_alpha': 170, 'row_alpha': 180, 'accent_alpha': 24, 'brand_divider_alpha': 12})
                title_profile['shadow_layers'] = ((3, 4, 100), (1, 2, 70))
                meta_profile.update({'secondary_fill': (255, 255, 255, 16), 'secondary_outline_alpha': 34, 'secondary_text_fill': (206, 215, 228, 204)})
                brand_profile.update({'fill_alpha': 144, 'shadow_alpha': 36})

            if fallback:
                panel_profile.update({'accent_alpha': 28, 'front_alpha': 182, 'row_alpha': 194, 'kicker_alpha': 118})
                title_profile.update({
                    'single_configs': ((62, 804, 540, 54), (58, 790, 536, 52), (54, 776, 532, 48)),
                    'two_line_configs': ((50, 776, 504, 46), (46, 764, 508, 42), (42, 752, 512, 38)),
                })
                meta_profile.update({'deadline_max_width': 220, 'gap': 8})
                brand_profile.update({'fill_alpha': 154})
            elif logo_heavy:
                title_profile.update({
                    'single_configs': ((60, 786, 534, 54), (56, 772, 530, 50), (52, 758, 526, 48)),
                    'two_line_configs': ((50, 766, 502, 46), (46, 754, 506, 42), (42, 742, 510, 38)),
                })
                panel_profile.update({'brand_divider_x': 988, 'accent_rail_rect': (68, 518, 118, 522)})
                meta_profile.update({'max_right': 980})

            if long_title:
                title_profile.update({
                    'prefer_two_lines': True,
                    'single_configs': ((58, 780, 532, 52), (54, 766, 528, 48), (50, 752, 524, 46)),
                    'two_line_configs': ((48, 760, 500, 44), (44, 748, 504, 40), (40, 736, 508, 38), (38, 724, 512, 36)),
                    'meta_y_two': 642,
                })
                meta_profile.update({'deadline_max_width': 214, 'gap': 8})
            elif short_title:
                title_profile.update({
                    'single_configs': ((66, 814, 540, 58), (62, 800, 536, 56), (58, 786, 532, 52)),
                })

            if str((top_zone_layout or {}).get('badge_anchor') or '') == 'right_shoulder':
                panel_profile.update({'top_line_y': 526, 'accent_rail_rect': (68, 520, 118, 524)})
                brand_profile.update({'x': 1012})

            panel_profile, title_profile, meta_profile, brand_profile = self._apply_premium_finish_profile(
                panel_profile,
                title_profile,
                meta_profile,
                brand_profile,
                card_type=card_type,
                mode_kind=mode_kind,
                brightness_band=brightness_band,
                top_zone_layout=top_zone_layout,
                signal_kind=signal_kind,
            )
            return {
                'mode': f'discount_system_{mode_kind}_{brightness_band}',
                'panel': panel_profile,
                'title': title_profile,
                'meta': meta_profile,
                'brand': brand_profile,
                'hero_luminance': round(hero_luminance, 3),
                'signal_kind': signal_kind,
            }
        if card_type == YotoCardType.FESTIVAL:
            hero_luminance = float(ImageStat.Stat(hero_artwork.convert('L')).mean[0]) / 255.0
            if hero_luminance >= 0.56:
                brightness_band = 'bright'
            elif hero_luminance <= 0.36:
                brightness_band = 'dark'
            else:
                brightness_band = 'balanced'

            hero_item = self._selected_media_score_item(diagnostics.hero_score_summary)
            logo_heavy = self._has_prominent_logo_text(hero_item)
            fallback = diagnostics.used_placeholder_artwork
            long_title = len(data.title) > 24 or len(data.title.split()) > 4
            short_title = len(data.title) <= 11
            mode_kind = 'fallback' if fallback else ('logo' if logo_heavy else 'clean')

            panel_profile: dict[str, Any] = {
                'cache_tag': f'festival_system_{mode_kind}_{brightness_band}',
                'back_points': [(0, 522), (220, 522), (336, 486), (1280, 486), (1280, 720), (0, 720)],
                'front_points': [(0, 538), (274, 538), (356, 508), (1216, 508), (1280, 530), (1280, 720), (0, 720)],
                'accent_points': [(0, 538), (148, 538), (252, 508), (320, 508), (244, 720), (0, 720)],
                'row_rect': (0, 658, 1280, 720),
                'shadow_offset': 12,
                'shadow_alpha': 72,
                'shadow_blur': 16,
                'back_alpha': 132,
                'front_alpha': 178,
                'row_alpha': 188,
                'accent_alpha': 18,
                'gradient_top': '#102336',
                'gradient_bottom': '#11162b',
                'gradient_alpha': 126,
                'top_line_y': 522,
                'top_line_alpha': 9,
                'accent_rail_rect': (68, 518, 126, 522),
                'row_line_alpha': 10,
                'glow_alpha': 10,
                'glow_blur': 8,
                'brand_divider_x': 1002,
                'brand_divider_top': 616,
                'brand_divider_bottom': 670,
                'brand_divider_alpha': 12,
                'kicker_x': 76,
                'kicker_y': 518,
                'kicker_alpha': 112,
            }
            title_profile: dict[str, Any] = {
                'x': 72,
                'single_configs': ((62, 808, 538, 56), (58, 792, 534, 52), (54, 778, 530, 48)),
                'two_line_configs': ((50, 782, 500, 46), (46, 770, 506, 42), (42, 758, 512, 38), (38, 746, 516, 36)),
                'meta_y_single': 620,
                'meta_y_two': 642,
                'prefer_two_lines': long_title or bool(data.deadline),
                'two_line_threshold': 24,
                'shadow_layers': ((3, 4, 112), (1, 2, 80)),
                'halo_fill': '#081a29',
                'halo_alpha': 86,
                'halo_blur': 28,
                'halo_pad_x': 38,
                'halo_pad_y': 24,
                'halo_radius': 26,
            }
            meta_profile: dict[str, Any] = {
                'x': 82,
                'y_offset': 8,
                'gap': 10,
                'chip_height': 36,
                'primary_radius': 14,
                'primary_fill': '#133649',
                'primary_fill_alpha': 202,
                'primary_border': EVENT_CYAN,
                'primary_outline_alpha': 184,
                'primary_text_fill': '#d7f8ff',
                'primary_dot_fill': EVENT_CYAN,
                'deadline_padding_x': 50,
                'deadline_text_x': 26,
                'deadline_text_y': 6,
                'deadline_dot_left': 12,
                'deadline_dot_top': 14,
                'deadline_dot_right': 20,
                'deadline_dot_bottom': 22,
                'deadline_font_size_single': 20,
                'deadline_font_size_two': 19,
                'secondary_fill': (255, 255, 255, 12),
                'secondary_outline_alpha': 30,
                'secondary_radius': 14,
                'secondary_text_fill': (210, 220, 232, 204),
                'old_price_padding_x': 30,
                'old_price_text_x': 16,
                'old_price_text_y': 6,
                'old_price_font_size': 19,
            }
            brand_profile: dict[str, Any] = {
                'style': 'grid_chip',
                'x': 1018,
                'y': 614,
                'width': 206,
                'height': 50,
                'radius': 16,
                'shadow_alpha': 42,
                'shadow_blur': 8,
                'fill_alpha': 154,
                'outline_alpha': 12,
                'accent_line_alpha': 112,
                'icon_left': 14,
                'icon_top': 10,
                'icon_size': 30,
                'icon_radius': 10,
                'y_font_size': 20,
                'y_text_x': 9,
                'y_text_y': 4,
                'text_x': 54,
                'micro_font_size': 11,
                'micro_y': 6,
                'body_font_size': 23,
                'body_y': 17,
            }

            if brightness_band == 'bright':
                panel_profile.update({'front_alpha': 184, 'row_alpha': 194, 'gradient_alpha': 134, 'glow_alpha': 20})
                title_profile['shadow_layers'] = ((3, 4, 124), (1, 2, 90))
                title_profile.update({'halo_alpha': 92})
                meta_profile.update({'secondary_fill': (255, 255, 255, 10), 'secondary_text_fill': (216, 226, 236, 208)})
                brand_profile.update({'fill_alpha': 162, 'shadow_alpha': 46})
            elif brightness_band == 'dark':
                panel_profile.update({'front_alpha': 170, 'row_alpha': 182, 'accent_alpha': 22, 'brand_divider_alpha': 14})
                title_profile['shadow_layers'] = ((3, 4, 100), (1, 2, 72))
                meta_profile.update({'secondary_fill': (255, 255, 255, 16), 'secondary_outline_alpha': 34, 'secondary_text_fill': (204, 214, 226, 206)})
                brand_profile.update({'fill_alpha': 146, 'shadow_alpha': 36})

            if fallback:
                panel_profile.update({'accent_alpha': 26, 'front_alpha': 182, 'row_alpha': 194, 'kicker_alpha': 118})
                title_profile.update({
                    'single_configs': ((60, 796, 538, 54), (56, 782, 534, 50), (52, 768, 530, 46)),
                    'two_line_configs': ((48, 770, 504, 44), (44, 758, 508, 40), (40, 746, 512, 38)),
                })
            elif logo_heavy:
                title_profile.update({
                    'single_configs': ((60, 792, 536, 54), (56, 778, 532, 50), (52, 764, 528, 46)),
                    'two_line_configs': ((48, 764, 504, 44), (44, 752, 508, 40), (40, 740, 512, 38)),
                })
                panel_profile.update({'brand_divider_x': 992})

            if long_title:
                title_profile.update({
                    'prefer_two_lines': True,
                    'single_configs': ((56, 780, 534, 50), (52, 766, 530, 46), (48, 752, 526, 42)),
                    'two_line_configs': ((46, 756, 502, 42), (42, 744, 506, 38), (38, 732, 510, 36)),
                    'meta_y_two': 644,
                })
            elif short_title:
                title_profile.update({
                    'single_configs': ((64, 820, 540, 58), (60, 804, 536, 54), (56, 788, 532, 50)),
                })

            if str((top_zone_layout or {}).get('badge_anchor') or '') == 'right_shoulder':
                panel_profile.update({'top_line_y': 524, 'accent_rail_rect': (68, 520, 124, 524)})

            panel_profile, title_profile, meta_profile, brand_profile = self._apply_premium_finish_profile(
                panel_profile,
                title_profile,
                meta_profile,
                brand_profile,
                card_type=card_type,
                mode_kind=mode_kind,
                brightness_band=brightness_band,
                top_zone_layout=top_zone_layout,
            )
            return {
                'mode': f'festival_system_{mode_kind}_{brightness_band}',
                'panel': panel_profile,
                'title': title_profile,
                'meta': meta_profile,
                'brand': brand_profile,
                'hero_luminance': round(hero_luminance, 3),
            }
        if card_type == YotoCardType.TOP_LIST:
            hero_luminance = float(ImageStat.Stat(hero_artwork.convert('L')).mean[0]) / 255.0
            if hero_luminance >= 0.56:
                brightness_band = 'bright'
            elif hero_luminance <= 0.36:
                brightness_band = 'dark'
            else:
                brightness_band = 'balanced'

            hero_item = self._selected_media_score_item(diagnostics.hero_score_summary)
            logo_heavy = self._has_prominent_logo_text(hero_item)
            fallback = diagnostics.used_placeholder_artwork
            long_title = len(data.title) > 22 or len(data.title.split()) > 4
            short_title = len(data.title) <= 12
            mode_kind = 'fallback' if fallback else ('logo' if logo_heavy else 'clean')

            panel_profile: dict[str, Any] = {
                'cache_tag': f'top_list_system_{mode_kind}_{brightness_band}',
                'back_points': [(0, 526), (246, 526), (356, 488), (1280, 488), (1280, 720), (0, 720)],
                'front_points': [(0, 542), (304, 542), (382, 512), (1216, 512), (1280, 534), (1280, 720), (0, 720)],
                'accent_points': [(0, 542), (156, 542), (264, 512), (332, 512), (252, 720), (0, 720)],
                'row_rect': (0, 660, 1280, 720),
                'shadow_offset': 12,
                'shadow_alpha': 70,
                'shadow_blur': 16,
                'back_alpha': 130,
                'front_alpha': 176,
                'row_alpha': 188,
                'accent_alpha': 18,
                'gradient_top': '#241b0d',
                'gradient_bottom': '#111317',
                'gradient_alpha': 124,
                'top_line_y': 526,
                'top_line_alpha': 9,
                'accent_rail_rect': (68, 520, 124, 524),
                'row_line_alpha': 10,
                'glow_alpha': 18,
                'glow_blur': 8,
                'brand_divider_x': 996,
                'brand_divider_top': 616,
                'brand_divider_bottom': 670,
                'brand_divider_alpha': 12,
                'kicker_x': 76,
                'kicker_y': 520,
                'kicker_alpha': 116,
            }
            title_profile: dict[str, Any] = {
                'x': 72,
                'single_configs': ((60, 792, 536, 54), (56, 778, 532, 50), (52, 764, 528, 46)),
                'two_line_configs': ((48, 766, 500, 44), (44, 754, 506, 40), (40, 742, 510, 38), (38, 730, 514, 36)),
                'meta_y_single': 620,
                'meta_y_two': 642,
                'prefer_two_lines': long_title or bool(data.list_label),
                'two_line_threshold': 20,
                'shadow_layers': ((3, 4, 112), (1, 2, 78)),
                'halo_fill': '#171005',
                'halo_alpha': 84,
                'halo_blur': 28,
                'halo_pad_x': 38,
                'halo_pad_y': 24,
                'halo_radius': 26,
            }
            meta_profile: dict[str, Any] = {
                'x': 82,
                'y_offset': 8,
                'gap': 10,
                'chip_height': 36,
                'primary_radius': 14,
                'primary_fill': '#4a3712',
                'primary_fill_alpha': 196,
                'primary_border': '#f0c670',
                'primary_outline_alpha': 176,
                'primary_text_fill': '#fff1bf',
                'primary_dot_fill': '#f0c670',
                'deadline_padding_x': 50,
                'deadline_text_x': 26,
                'deadline_text_y': 6,
                'deadline_dot_left': 12,
                'deadline_dot_top': 14,
                'deadline_dot_right': 20,
                'deadline_dot_bottom': 22,
                'deadline_font_size_single': 20,
                'deadline_font_size_two': 19,
                'secondary_fill': (255, 255, 255, 12),
                'secondary_outline_alpha': 28,
                'secondary_radius': 14,
                'secondary_text_fill': (220, 214, 194, 202),
                'old_price_padding_x': 30,
                'old_price_text_x': 16,
                'old_price_text_y': 6,
                'old_price_font_size': 19,
            }
            brand_profile: dict[str, Any] = {
                'style': 'grid_chip',
                'x': 1014,
                'y': 614,
                'width': 210,
                'height': 50,
                'radius': 16,
                'shadow_alpha': 40,
                'shadow_blur': 8,
                'fill_alpha': 154,
                'outline_alpha': 12,
                'accent_line_alpha': 108,
                'icon_left': 14,
                'icon_top': 10,
                'icon_size': 30,
                'icon_radius': 10,
                'y_font_size': 20,
                'y_text_x': 9,
                'y_text_y': 4,
                'text_x': 54,
                'micro_font_size': 11,
                'micro_y': 6,
                'body_font_size': 23,
                'body_y': 17,
            }

            if brightness_band == 'bright':
                panel_profile.update({'front_alpha': 184, 'row_alpha': 194, 'gradient_alpha': 132, 'glow_alpha': 20})
                title_profile['shadow_layers'] = ((3, 4, 124), (1, 2, 88))
                title_profile.update({'halo_alpha': 90})
                meta_profile.update({'secondary_fill': (255, 255, 255, 10), 'secondary_text_fill': (228, 221, 198, 208)})
                brand_profile.update({'fill_alpha': 162, 'shadow_alpha': 44})
            elif brightness_band == 'dark':
                panel_profile.update({'front_alpha': 170, 'row_alpha': 182, 'accent_alpha': 22, 'brand_divider_alpha': 14})
                title_profile['shadow_layers'] = ((3, 4, 102), (1, 2, 72))
                meta_profile.update({'secondary_fill': (255, 255, 255, 16), 'secondary_outline_alpha': 32, 'secondary_text_fill': (214, 206, 184, 206)})
                brand_profile.update({'fill_alpha': 146, 'shadow_alpha': 34})

            if fallback:
                panel_profile.update({'accent_alpha': 24, 'front_alpha': 182, 'row_alpha': 194, 'kicker_alpha': 120})
                title_profile.update({
                    'single_configs': ((58, 780, 536, 52), (54, 766, 532, 48), (50, 752, 528, 44)),
                    'two_line_configs': ((46, 752, 502, 42), (42, 740, 506, 38), (38, 728, 510, 36)),
                })
            elif logo_heavy:
                title_profile.update({
                    'single_configs': ((58, 780, 536, 52), (54, 766, 532, 48), (50, 752, 528, 44)),
                    'two_line_configs': ((46, 756, 502, 42), (42, 744, 506, 38), (38, 732, 510, 36)),
                })
                panel_profile.update({'brand_divider_x': 988})

            if long_title:
                title_profile.update({
                    'prefer_two_lines': True,
                    'single_configs': ((54, 766, 534, 48), (50, 752, 530, 44), (46, 738, 526, 40)),
                    'two_line_configs': ((44, 744, 500, 40), (40, 732, 504, 38), (36, 720, 508, 34)),
                    'meta_y_two': 644,
                })
            elif short_title:
                title_profile.update({
                    'single_configs': ((62, 806, 540, 56), (58, 790, 536, 52), (54, 774, 532, 48)),
                })

            if str((top_zone_layout or {}).get('badge_anchor') or '') == 'right_shoulder':
                panel_profile.update({'top_line_y': 528, 'accent_rail_rect': (68, 522, 124, 526)})

            panel_profile, title_profile, meta_profile, brand_profile = self._apply_premium_finish_profile(
                panel_profile,
                title_profile,
                meta_profile,
                brand_profile,
                card_type=card_type,
                mode_kind=mode_kind,
                brightness_band=brightness_band,
                top_zone_layout=top_zone_layout,
            )
            return {
                'mode': f'top_list_system_{mode_kind}_{brightness_band}',
                'panel': panel_profile,
                'title': title_profile,
                'meta': meta_profile,
                'brand': brand_profile,
                'hero_luminance': round(hero_luminance, 3),
            }
        if card_type != YotoCardType.FREE_GAME:
            return {'mode': 'default'}

        hero_luminance = float(ImageStat.Stat(hero_artwork.convert('L')).mean[0]) / 255.0
        if hero_luminance >= 0.56:
            brightness_band = 'bright'
        elif hero_luminance <= 0.36:
            brightness_band = 'dark'
        else:
            brightness_band = 'balanced'

        hero_item = self._selected_media_score_item(diagnostics.hero_score_summary)
        logo_heavy = self._has_prominent_logo_text(hero_item)
        fallback = diagnostics.used_placeholder_artwork
        long_title = len(data.title) > 22 or len(data.title.split()) > 3
        short_title = len(data.title) <= 10
        mode_kind = 'fallback' if fallback else ('logo' if logo_heavy else 'clean')

        panel_profile: dict[str, Any] = {
            'cache_tag': f'epic_free_system_{mode_kind}_{brightness_band}',
            'back_points': [(0, 522), (228, 522), (320, 486), (1280, 486), (1280, 720), (0, 720)],
            'front_points': [(0, 538), (250, 538), (332, 508), (1208, 508), (1280, 528), (1280, 720), (0, 720)],
            'accent_points': [(0, 538), (126, 538), (218, 508), (282, 508), (210, 720), (0, 720)],
            'row_rect': (0, 658, 1280, 720),
            'shadow_offset': 12,
            'shadow_alpha': 66,
            'shadow_blur': 16,
            'back_alpha': 126,
            'front_alpha': 170,
            'row_alpha': 182,
            'accent_alpha': 18,
            'gradient_top': '#122131',
            'gradient_bottom': '#0f1722',
            'gradient_alpha': 118,
            'top_line_y': 522,
            'top_line_alpha': 8,
            'accent_rail_rect': (68, 518, 124, 522),
            'row_line_alpha': 10,
            'glow_alpha': 16,
            'glow_blur': 7,
            'brand_divider_x': 1002,
            'brand_divider_top': 616,
            'brand_divider_bottom': 670,
            'brand_divider_alpha': 10,
            'kicker_x': 76,
            'kicker_y': 518,
            'kicker_alpha': 110,
        }
        title_profile: dict[str, Any] = {
            'x': 72,
            'single_configs': ((66, 812, 540, 58), (62, 798, 536, 56), (58, 784, 532, 52), (54, 770, 528, 48)),
            'two_line_configs': ((54, 790, 502, 50), (50, 778, 508, 46), (46, 766, 512, 42), (42, 754, 516, 38)),
            'meta_y_single': 620,
            'meta_y_two': 642,
            'prefer_two_lines': long_title,
            'two_line_threshold': 22,
            'shadow_layers': ((3, 4, 112), (1, 2, 78)),
            'halo_fill': '#08141d',
            'halo_alpha': 78,
            'halo_blur': 28,
            'halo_pad_x': 38,
            'halo_pad_y': 24,
            'halo_radius': 26,
        }
        meta_profile: dict[str, Any] = {
            'x': 82,
            'y_offset': 8,
            'gap': 12,
            'chip_height': 36,
            'primary_radius': 14,
            'primary_fill': '#0a3a28',
            'primary_fill_alpha': 196,
            'primary_border': PRIMARY_GREEN,
            'primary_outline_alpha': 172,
            'primary_text_fill': '#d9fff0',
            'primary_dot_fill': PRIMARY_GREEN,
            'deadline_padding_x': 50,
            'deadline_text_x': 26,
            'deadline_text_y': 6,
            'deadline_dot_left': 12,
            'deadline_dot_top': 14,
            'deadline_dot_right': 20,
            'deadline_dot_bottom': 22,
            'deadline_font_size_single': 20,
            'deadline_font_size_two': 19,
            'secondary_fill': (255, 255, 255, 12),
            'secondary_outline_alpha': 30,
            'secondary_radius': 14,
            'secondary_text_fill': (210, 219, 228, 202),
            'old_price_padding_x': 30,
            'old_price_text_x': 16,
            'old_price_text_y': 6,
            'old_price_font_size': 19,
        }
        brand_profile: dict[str, Any] = {
            'style': 'grid_chip',
            'x': 1024,
            'y': 614,
            'width': 200,
            'height': 50,
            'radius': 16,
            'shadow_alpha': 38,
            'shadow_blur': 8,
            'fill_alpha': 150,
            'outline_alpha': 12,
            'accent_line_alpha': 104,
            'icon_left': 14,
            'icon_top': 10,
            'icon_size': 30,
            'icon_radius': 10,
            'y_font_size': 20,
            'y_text_x': 9,
            'y_text_y': 4,
            'text_x': 54,
            'micro_font_size': 11,
            'micro_y': 6,
            'body_font_size': 23,
            'body_y': 17,
        }

        if brightness_band == 'bright':
            panel_profile.update({'front_alpha': 178, 'row_alpha': 188, 'gradient_alpha': 126, 'top_line_alpha': 10, 'glow_alpha': 18})
            title_profile['shadow_layers'] = ((3, 4, 124), (1, 2, 88))
            title_profile.update({'halo_alpha': 88})
            meta_profile.update({'secondary_fill': (255, 255, 255, 10), 'secondary_text_fill': (216, 224, 232, 208)})
            brand_profile.update({'fill_alpha': 160, 'shadow_alpha': 42})
        elif brightness_band == 'dark':
            panel_profile.update({'front_alpha': 164, 'row_alpha': 176, 'accent_alpha': 22, 'brand_divider_alpha': 12})
            title_profile['shadow_layers'] = ((3, 4, 98), (1, 2, 70))
            meta_profile.update({'secondary_fill': (255, 255, 255, 16), 'secondary_outline_alpha': 34, 'secondary_text_fill': (202, 211, 222, 206)})
            brand_profile.update({'fill_alpha': 144, 'shadow_alpha': 34})

        if fallback:
            panel_profile.update({'accent_alpha': 28, 'front_alpha': 178, 'row_alpha': 188, 'kicker_alpha': 118})
            title_profile.update({
                'single_configs': ((64, 820, 540, 56), (60, 804, 536, 54), (56, 788, 532, 50)),
                'two_line_configs': ((52, 786, 504, 48), (48, 772, 508, 44), (44, 760, 512, 40)),
            })
        elif logo_heavy:
            title_profile.update({
                'single_configs': ((62, 796, 538, 56), (58, 782, 534, 52), (54, 768, 530, 48)),
                'two_line_configs': ((52, 772, 504, 48), (48, 760, 508, 44), (44, 748, 512, 40)),
            })

        if long_title:
            title_profile.update({
                'prefer_two_lines': True,
                'single_configs': ((58, 786, 536, 52), (54, 772, 532, 48), (50, 758, 528, 46)),
                'two_line_configs': ((50, 770, 502, 46), (46, 758, 506, 42), (42, 746, 510, 38), (38, 734, 514, 36)),
                'meta_y_two': 644,
            })
        elif short_title:
            title_profile.update({
                'single_configs': ((68, 824, 542, 60), (64, 808, 538, 56), (60, 792, 534, 52)),
            })

        if str((top_zone_layout or {}).get('badge_anchor') or '') == 'right_shoulder':
            panel_profile.update({'top_line_y': 524, 'accent_rail_rect': (68, 520, 124, 524)})

        panel_profile, title_profile, meta_profile, brand_profile = self._apply_premium_finish_profile(
            panel_profile,
            title_profile,
            meta_profile,
            brand_profile,
            card_type=card_type,
            mode_kind=mode_kind,
            brightness_band=brightness_band,
            top_zone_layout=top_zone_layout,
        )
        return {
            'mode': f'epic_free_system_{mode_kind}_{brightness_band}',
            'panel': panel_profile,
            'title': title_profile,
            'meta': meta_profile,
            'brand': brand_profile,
            'hero_luminance': round(hero_luminance, 3),
        }

    def _platform_badge_visual_profile(
        self,
        text: str,
        card_type: YotoCardType,
        diagnostics: YotoCardDiagnostics | None = None,
        top_zone_layout: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        profile: dict[str, Any] = {
            'display_text': text,
            'font_size': 17,
            'x': SAFE_LEFT,
            'y': SAFE_TOP - 2,
            'pad_left': 26,
            'pad_right': 16,
            'pad_top': 7,
            'pad_bottom': 9,
            'radius': 13,
            'fill': (11, 14, 18, 216),
            'outline_alpha': 68,
            'indicator_left': 8,
            'indicator_right': 18,
            'indicator_top': 8,
            'indicator_bottom': 8,
            'indicator_radius': 4,
            'indicator_alpha': 255,
            'text_x': 28,
            'text_y': 8,
            'text_fill': (255, 255, 255, 255),
        }
        overrides = dict((top_zone_layout or {}).get('platform_badge_overrides') or {})
        if overrides:
            profile.update(overrides)
            return profile
        normalized_text = self._normalize_display_text(text.upper())
        if card_type == YotoCardType.DISCOUNT:
            compact_source = normalized_text.split()[0] if normalized_text else ''
            if compact_source:
                profile.update(
                    {
                        'display_text': compact_source,
                        'font_size': 15,
                        'y': SAFE_TOP - 8,
                        'pad_left': 22,
                        'pad_right': 14,
                        'pad_top': 7,
                        'pad_bottom': 8,
                        'radius': 12,
                        'fill': (11, 14, 18, 206),
                        'outline_alpha': 46,
                        'indicator_left': 8,
                        'indicator_right': 16,
                        'indicator_top': 9,
                        'indicator_bottom': 9,
                        'indicator_radius': 4,
                        'indicator_alpha': 214,
                        'text_x': 24,
                        'text_y': 7,
                        'text_fill': (245, 247, 250, 230),
                    }
                )
            return profile
        if card_type == YotoCardType.FESTIVAL:
            profile.update(
                {
                    'font_size': 15,
                    'y': SAFE_TOP - 8,
                    'pad_left': 22,
                    'pad_right': 14,
                    'pad_top': 7,
                    'pad_bottom': 8,
                    'radius': 12,
                    'fill': (10, 14, 20, 196),
                    'outline_alpha': 54,
                    'indicator_left': 8,
                    'indicator_right': 16,
                    'indicator_top': 9,
                    'indicator_bottom': 9,
                    'indicator_radius': 4,
                    'indicator_alpha': 212,
                    'text_x': 24,
                    'text_y': 7,
                    'text_fill': (243, 248, 252, 236),
                }
            )
            return profile
        if card_type == YotoCardType.TOP_LIST:
            profile.update(
                {
                    'font_size': 14,
                    'y': SAFE_TOP - 8,
                    'pad_left': 22,
                    'pad_right': 14,
                    'pad_top': 7,
                    'pad_bottom': 8,
                    'radius': 12,
                    'fill': (12, 13, 16, 198),
                    'outline_alpha': 52,
                    'indicator_left': 8,
                    'indicator_right': 16,
                    'indicator_top': 9,
                    'indicator_bottom': 9,
                    'indicator_radius': 4,
                    'indicator_alpha': 208,
                    'text_x': 24,
                    'text_y': 7,
                    'text_fill': (247, 241, 224, 236),
                }
            )
            return profile
        if card_type != YotoCardType.FREE_GAME or diagnostics is None:
            return profile
        if diagnostics.used_placeholder_artwork:
            compact_source = normalized_text.split()[0] if normalized_text else ''
            if compact_source:
                profile.update(
                    {
                        'display_text': compact_source,
                        'font_size': 16,
                        'y': SAFE_TOP - 8,
                        'pad_left': 24,
                        'pad_right': 16,
                        'pad_top': 8,
                        'pad_bottom': 9,
                        'radius': 13,
                        'fill': (11, 14, 18, 214),
                        'outline_alpha': 54,
                        'indicator_left': 8,
                        'indicator_right': 16,
                        'indicator_top': 9,
                        'indicator_bottom': 9,
                        'indicator_radius': 4,
                        'indicator_alpha': 210,
                        'text_x': 24,
                        'text_y': 8,
                        'text_fill': (244, 249, 246, 236),
                    }
                )
            return profile
        if 'EPIC' not in normalized_text:
            return profile
        hero_item = self._selected_media_score_item(diagnostics.hero_score_summary)
        if not self._has_prominent_logo_text(hero_item):
            return profile
        profile.update(
            {
                'display_text': 'EPIC',
                'font_size': 16,
                'x': SAFE_LEFT,
                'y': SAFE_TOP - 8,
                'pad_left': 24,
                'pad_right': 16,
                'pad_top': 8,
                'pad_bottom': 9,
                'radius': 13,
                'fill': (11, 14, 18, 214),
                'outline_alpha': 58,
                'indicator_left': 8,
                'indicator_right': 16,
                'indicator_top': 9,
                'indicator_bottom': 9,
                'indicator_radius': 4,
                'indicator_alpha': 214,
                'text_x': 24,
                'text_y': 8,
                'text_fill': (244, 249, 246, 238),
            }
        )
        return profile

    def _quiet_badge_profile(self, profile: Mapping[str, Any], card_type: YotoCardType) -> dict[str, Any]:
        quiet = dict(profile)
        min_width = {
            YotoCardType.FREE_GAME: 284,
            YotoCardType.DISCOUNT: 188,
            YotoCardType.FESTIVAL: 176,
            YotoCardType.TOP_LIST: 176,
        }.get(card_type, 188)
        min_height = {
            YotoCardType.FREE_GAME: 104,
            YotoCardType.DISCOUNT: 88,
            YotoCardType.FESTIVAL: 82,
            YotoCardType.TOP_LIST: 82,
        }.get(card_type, 84)
        width_trim = {
            YotoCardType.FREE_GAME: 12,
            YotoCardType.DISCOUNT: 14,
            YotoCardType.FESTIVAL: 10,
            YotoCardType.TOP_LIST: 10,
        }.get(card_type, 10)
        height_trim = {
            YotoCardType.FREE_GAME: 8,
            YotoCardType.DISCOUNT: 10,
            YotoCardType.FESTIVAL: 8,
            YotoCardType.TOP_LIST: 8,
        }.get(card_type, 8)
        quiet['badge_width'] = max(min_width, int(quiet.get('badge_width', min_width)) - width_trim)
        quiet['badge_min_height'] = max(min_height, int(quiet.get('badge_min_height', min_height)) - height_trim)
        quiet['shadow_alpha'] = max(48, int(round(int(quiet.get('shadow_alpha', 0)) * 0.76)))
        quiet['shadow_blur'] = max(8, int(quiet.get('shadow_blur', 10)) - 2)
        quiet['outline_alpha'] = max(42, int(round(int(quiet.get('outline_alpha', 0)) * 0.72)))
        quiet['gloss_alpha'] = max(0, int(quiet.get('gloss_alpha', 0)) - 3)
        quiet['accent_bar_alpha'] = max(82, int(round(int(quiet.get('accent_bar_alpha', 0)) * 0.58)))
        quiet['accent_bar_right'] = max(24, int(quiet.get('accent_bar_right', 28)) - 4)
        quiet['top_line_alpha'] = max(0, int(round(int(quiet.get('top_line_alpha', 0)) * 0.50)))
        quiet['bottom_line_alpha'] = max(10, int(round(int(quiet.get('bottom_line_alpha', 0)) * 0.46)))
        quiet['header_fill_alpha'] = max(128, int(round(int(quiet.get('header_fill_alpha', 0)) * 0.74)))
        quiet['footer_fill_alpha'] = 0
        quiet['glow_alpha'] = max(6, int(round(int(quiet.get('glow_alpha', 0)) * 0.48)))
        quiet['glow_blur'] = max(10, int(quiet.get('glow_blur', 12)) - 1)
        quiet['glow_pad_left'] = max(12, int(quiet.get('glow_pad_left', 16)) - 6)
        quiet['glow_pad_top'] = max(8, int(quiet.get('glow_pad_top', 12)) - 4)
        quiet['glow_pad_right'] = max(12, int(quiet.get('glow_pad_right', 16)) - 6)
        quiet['glow_pad_bottom'] = max(10, int(quiet.get('glow_pad_bottom', 12)) - 4)
        quiet['footer_text_fill'] = quiet.get('footer_text_fill', '#ffcfb5' if card_type == YotoCardType.DISCOUNT else '#dbe3ee')
        return quiet

    def _badge_visual_profile(
        self,
        data: YotoCardData,
        diagnostics: YotoCardDiagnostics,
        card_type: YotoCardType,
        top_zone_layout: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        badge_main = str(diagnostics.text_payload.get('badge_main') or '')
        if card_type == YotoCardType.FREE_GAME:
            profile: dict[str, Any] = {
                'cache_tag': 'default',
                'badge_width': 332,
                'badge_min_height': 126,
                'header_font_sizes': range(17, 11, -1),
                'main_font_sizes': range(42, 21, -2),
                'footer_font_sizes': range(16, 11, -1),
                'shadow_alpha': 110,
                'shadow_blur': 15,
                'body_fill': (7, 11, 17, 230),
                'outline_alpha': 116,
                'gloss_alpha': 8,
                'accent_bar_alpha': 236,
                'accent_bar_top': 16,
                'accent_bar_right': 30,
                'accent_bar_bottom': 26,
                'top_line_alpha': 20,
                'bottom_line_alpha': 68,
                'text_x': 48,
                'header_fill_alpha': 234,
                'main_fill': (255, 255, 255, 255),
                'main_shadow_alpha': 96,
                'main_gap': 4,
                'footer_fill_alpha': 214,
                'badge_x_adjust': 2,
                'badge_y': 52,
                'glow_alpha': 22,
                'glow_blur': 18,
                'glow_pad_left': 28,
                'glow_pad_top': 18,
                'glow_pad_right': 26,
                'glow_pad_bottom': 20,
            }
            hero_item = self._selected_media_score_item(diagnostics.hero_score_summary)
            platform = self._normalize_display_text(str(data.platform or '').upper())
            if 'EPIC' in platform and not diagnostics.used_placeholder_artwork and self._has_prominent_logo_text(hero_item):
                profile.update(
                    {
                        'cache_tag': 'epic_logo_soft',
                        'badge_width': 300,
                        'badge_min_height': 112,
                        'header_font_sizes': range(15, 10, -1),
                        'main_font_sizes': range(36, 21, -2),
                        'footer_font_sizes': range(14, 10, -1),
                        'shadow_alpha': 82,
                        'shadow_blur': 12,
                        'body_fill': (7, 11, 17, 214),
                        'outline_alpha': 84,
                        'gloss_alpha': 5,
                        'accent_bar_alpha': 198,
                        'accent_bar_top': 18,
                        'accent_bar_right': 28,
                        'accent_bar_bottom': 30,
                        'top_line_alpha': 12,
                        'bottom_line_alpha': 44,
                        'text_x': 44,
                        'header_fill_alpha': 214,
                        'main_fill': (245, 250, 247, 238),
                        'main_shadow_alpha': 74,
                        'main_gap': 2,
                        'footer_fill_alpha': 198,
                        'badge_x_adjust': 10,
                        'badge_y': 48,
                        'glow_alpha': 18,
                        'glow_blur': 14,
                        'glow_pad_left': 18,
                        'glow_pad_top': 14,
                        'glow_pad_right': 18,
                        'glow_pad_bottom': 14,
                    }
                )
            overrides = dict((top_zone_layout or {}).get('badge_overrides') or {})
            if overrides:
                profile.update(overrides)
            return self._quiet_badge_profile(profile, card_type)
        if card_type == YotoCardType.DISCOUNT:
            profile = {
                'cache_tag': 'default',
                'badge_width': 216,
                'badge_min_height': 102,
                'header_font_sizes': range(15, 10, -1),
                'main_font_sizes': range(42, 24, -2),
                'footer_font_sizes': range(14, 9, -1),
                'shadow_alpha': 92,
                'shadow_blur': 11,
                'body_fill': (13, 10, 8, 208),
                'outline_alpha': 92,
                'gloss_alpha': 4,
                'accent_bar_alpha': 162,
                'accent_bar_top': 16,
                'accent_bar_right': 28,
                'accent_bar_bottom': 24,
                'top_line_alpha': 10,
                'bottom_line_alpha': 26,
                'text_x': 42,
                'header_fill_alpha': 216,
                'main_fill': (*ImageColor.getrgb(DISCOUNT_ORANGE), 240),
                'main_shadow_alpha': 72,
                'main_gap': 2,
                'footer_fill_alpha': 172,
                'badge_x_adjust': 10,
                'badge_y': 40,
                'glow_alpha': 18,
                'glow_blur': 12,
                'glow_pad_left': 16,
                'glow_pad_top': 12,
                'glow_pad_right': 16,
                'glow_pad_bottom': 12,
            }
            overrides = dict((top_zone_layout or {}).get('badge_overrides') or {})
            if overrides:
                profile.update(overrides)
            return self._quiet_badge_profile(profile, card_type)
        if card_type == YotoCardType.FESTIVAL:
            return self._quiet_badge_profile(
                {
                    'cache_tag': 'festival_editorial_finish',
                    'badge_width': 194,
                    'badge_min_height': 92,
                    'header_font_sizes': range(15, 10, -1),
                    'main_font_sizes': range(32, 20, -2),
                    'footer_font_sizes': range(13, 10, -1),
                    'shadow_alpha': 82,
                    'shadow_blur': 10,
                    'body_fill': (8, 12, 20, 196),
                    'outline_alpha': 90,
                    'gloss_alpha': 3,
                    'accent_bar_alpha': 154,
                    'accent_bar_top': 15,
                    'accent_bar_right': 26,
                    'accent_bar_bottom': 22,
                    'top_line_alpha': 10,
                    'bottom_line_alpha': 26,
                    'text_x': 40,
                    'header_fill_alpha': 184,
                    'main_fill': (244, 249, 255, 238),
                    'main_shadow_alpha': 60,
                    'main_gap': 1,
                    'footer_fill_alpha': 150,
                    'badge_x_adjust': 0,
                    'badge_y': 44,
                    'glow_alpha': 8,
                    'glow_blur': 12,
                    'glow_pad_left': 14,
                    'glow_pad_top': 12,
                    'glow_pad_right': 14,
                    'glow_pad_bottom': 14,
                },
                card_type,
            )
        if card_type == YotoCardType.TOP_LIST:
            return self._quiet_badge_profile(
                {
                    'cache_tag': 'top_list_editorial_finish',
                    'badge_width': 196,
                    'badge_min_height': 92,
                    'header_font_sizes': range(15, 10, -1),
                    'main_font_sizes': range(30, 18, -2),
                    'footer_font_sizes': range(13, 10, -1),
                    'shadow_alpha': 80,
                    'shadow_blur': 10,
                    'body_fill': (9, 11, 16, 198),
                    'outline_alpha': 88,
                    'gloss_alpha': 3,
                    'accent_bar_alpha': 150,
                    'accent_bar_top': 15,
                    'accent_bar_right': 26,
                    'accent_bar_bottom': 22,
                    'top_line_alpha': 10,
                    'bottom_line_alpha': 24,
                    'text_x': 38,
                    'header_fill_alpha': 184,
                    'main_fill': (255, 245, 220, 238),
                    'main_shadow_alpha': 58,
                    'main_gap': 1,
                    'footer_fill_alpha': 146,
                    'badge_x_adjust': 0,
                    'badge_y': 44,
                    'glow_alpha': 8,
                    'glow_blur': 12,
                    'glow_pad_left': 14,
                    'glow_pad_top': 12,
                    'glow_pad_right': 14,
                    'glow_pad_bottom': 14,
                },
                card_type,
            )
        return self._quiet_badge_profile(
            {
                'cache_tag': 'default',
                'badge_width': 228,
                'badge_min_height': 112,
                'header_font_sizes': range(17, 11, -1),
                'main_font_sizes': range(40, 22, -2),
                'footer_font_sizes': range(16, 11, -1),
                'shadow_alpha': 132,
                'shadow_blur': 15,
                'body_fill': (7, 11, 17, 230),
                'outline_alpha': 134,
                'gloss_alpha': 8,
                'accent_bar_alpha': 236,
                'accent_bar_top': 16,
                'accent_bar_right': 30,
                'accent_bar_bottom': 26,
                'top_line_alpha': 20,
                'bottom_line_alpha': 68,
                'text_x': 48,
                'header_fill_alpha': 234,
                'main_fill': (255, 255, 255, 255),
                'main_shadow_alpha': 96,
                'main_gap': 4,
                'footer_fill_alpha': 214,
                'badge_x_adjust': 2,
                'badge_y': 52,
                'glow_alpha': 38,
                'glow_blur': 18,
                'glow_pad_left': 28,
                'glow_pad_top': 18,
                'glow_pad_right': 26,
                'glow_pad_bottom': 20,
            },
            card_type,
        )

    def draw_gameplay_strip(
        self,
        canvas: Image.Image,
        data: YotoCardData,
        card_type: YotoCardType,
        diagnostics: YotoCardDiagnostics | None = None,
    ) -> tuple[Image.Image, bool, int]:
        if not data.gameplay_images:
            return canvas, False, 0
        if self._should_suppress_redundant_gameplay_strip(data, card_type, diagnostics=diagnostics):
            if diagnostics is not None:
                diagnostics.gameplay_selection_reason = 'suppressed_logo_redundancy'
                diagnostics.gameplay_selection['suppressed'] = True
                diagnostics.gameplay_selection['suppression_reason'] = 'logo_redundancy'
            return canvas, False, 0

        palette = self._palette(card_type)
        loaded_images: list[Image.Image] = []
        cache_keys: list[str] = []
        for image_path in data.gameplay_images[:3]:
            image, cache_key = self._load_optional_asset(image_path)
            if image is None or cache_key is None:
                continue
            loaded_images.append(image)
            cache_keys.append(cache_key)

        if not loaded_images:
            return canvas, False, 0

        strip_style = {
            'thumb_widths': {1: 432, 2: 308, 3: 244},
            'gap': 16,
            'y': GAMEPLAY_STRIP_TOP,
            'rail_pad_x': 22,
            'rail_pad_top': 12,
            'rail_pad_bottom': 14,
            'shadow_alpha': 102,
            'shadow_blur': 14,
            'rail_fill_alpha': 148,
            'rail_outline_alpha': 18,
            'gloss_alpha': 8,
            'accent_line_alpha': 72,
            'show_label': True,
            'label_alpha': 132,
            'subline_alpha': 14,
        }
        if card_type == YotoCardType.DISCOUNT:
            strip_style.update(
                {
                    'thumb_widths': {1: 404, 2: 292, 3: 228},
                    'gap': 12,
                    'y': GAMEPLAY_STRIP_TOP + 10,
                    'rail_pad_x': 10,
                    'rail_pad_top': 8,
                    'rail_pad_bottom': 8,
                    'shadow_alpha': 54,
                    'shadow_blur': 10,
                    'rail_fill_alpha': 78,
                    'rail_outline_alpha': 10,
                    'gloss_alpha': 0,
                    'accent_line_alpha': 18,
                    'show_label': False,
                    'label_alpha': 0,
                    'subline_alpha': 0,
                }
            )

        cache_key = (card_type.value, str(strip_style), *cache_keys)
        cached = self._gameplay_strip_cache.get(cache_key)
        if cached is None:
            overlay = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            count = len(loaded_images)
            thumb_width = int(strip_style['thumb_widths'].get(count, 244))
            thumb_size = (thumb_width, GAMEPLAY_STRIP_HEIGHT)
            gap = int(strip_style['gap'])
            total_width = thumb_size[0] * count + gap * max(0, count - 1)
            start_x = int((CARD_SIZE[0] - total_width) / 2)
            y = int(strip_style['y'])
            rail_rect = (
                start_x - int(strip_style['rail_pad_x']),
                y - int(strip_style['rail_pad_top']),
                start_x + total_width + int(strip_style['rail_pad_x']),
                y + thumb_size[1] + int(strip_style['rail_pad_bottom']),
            )

            rail_shadow = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
            rail_shadow_draw = ImageDraw.Draw(rail_shadow)
            rail_shadow_draw.rounded_rectangle(
                (rail_rect[0] + 4, rail_rect[1] + 5, rail_rect[2] + 4, rail_rect[3] + 5),
                radius=28,
                fill=(0, 0, 0, int(strip_style['shadow_alpha'])),
            )
            rail_shadow = rail_shadow.filter(ImageFilter.GaussianBlur(radius=int(strip_style['shadow_blur'])))
            overlay = Image.alpha_composite(overlay, rail_shadow)

            draw.rounded_rectangle(
                rail_rect,
                radius=28,
                fill=(6, 10, 15, int(strip_style['rail_fill_alpha'])),
                outline=(255, 255, 255, int(strip_style['rail_outline_alpha'])),
                width=1,
            )
            gloss_alpha = int(strip_style['gloss_alpha'])
            if gloss_alpha > 0:
                draw.rounded_rectangle((rail_rect[0] + 2, rail_rect[1] + 2, rail_rect[2] - 2, rail_rect[1] + 20), radius=26, fill=(255, 255, 255, gloss_alpha))
            accent_line_alpha = int(strip_style['accent_line_alpha'])
            if accent_line_alpha > 0:
                draw.line((rail_rect[0] + 20, rail_rect[1] + 12, rail_rect[2] - 20, rail_rect[1] + 12), fill=rgba(palette.accent_secondary, accent_line_alpha), width=2)
            if bool(strip_style['show_label']):
                label_font = self._load_font_for_text(12, SEMIBOLD_FONT_CANDIDATES, GAMEPLAY_LABEL, diagnostics=diagnostics, layer='gameplay_label')
                draw.text((rail_rect[0] + 22, rail_rect[1] + 18), GAMEPLAY_LABEL, font=label_font, fill=rgba(WHITE, int(strip_style['label_alpha'])))
                subline_alpha = int(strip_style['subline_alpha'])
                if subline_alpha > 0:
                    draw.line((rail_rect[0] + 92, rail_rect[1] + 26, rail_rect[2] - 22, rail_rect[1] + 26), fill=(255, 255, 255, subline_alpha), width=1)

            angles = {
                1: (0.0,),
                2: (-0.6, 0.6),
                3: (-0.8, 0.0, 0.8),
            }.get(count, (0.0,) * count)

            for index, image in enumerate(loaded_images):
                thumb = self._build_gameplay_thumbnail(image, thumb_size, palette, angles[index], is_primary=index == 0)
                base_x = start_x + index * (thumb_size[0] + gap)
                paste_x = base_x + int((thumb_size[0] - thumb.width) / 2)
                paste_y = y + int((thumb_size[1] - thumb.height) / 2)
                overlay.paste(thumb, (paste_x, paste_y), thumb)

            self._gameplay_strip_cache[cache_key] = overlay
            cached = overlay

        return Image.alpha_composite(canvas.convert('RGBA'), cached.copy()), True, len(loaded_images)


    def draw_lower_third_panel(
        self,
        canvas: Image.Image,
        card_type: YotoCardType,
        editorial_phrase: str | None = None,
        diagnostics: YotoCardDiagnostics | None = None,
        composition_profile: Mapping[str, Any] | None = None,
    ) -> Image.Image:
        palette = self._palette(card_type)
        panel_profile = dict((composition_profile or {}).get('panel') or {})
        if panel_profile:
            cache_key = f"{card_type.value}:{panel_profile.get('cache_tag', 'epic_free_system')}"
            cached = self._panel_cache.get(cache_key)
            if cached is None:
                panel = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
                back_points = [tuple(point) for point in panel_profile['back_points']]
                front_points = [tuple(point) for point in panel_profile['front_points']]
                accent_points = [tuple(point) for point in panel_profile['accent_points']]
                row_rect = tuple(panel_profile['row_rect'])

                shadow = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
                shadow_draw = ImageDraw.Draw(shadow)
                shadow_offset = int(panel_profile.get('shadow_offset', 14))
                shadow_draw.polygon([(x, y + shadow_offset) for x, y in back_points], fill=(0, 0, 0, int(panel_profile.get('shadow_alpha', 92))))
                shadow = shadow.filter(ImageFilter.GaussianBlur(radius=int(panel_profile.get('shadow_blur', 20))))
                panel = Image.alpha_composite(panel, shadow)

                base = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
                base_draw = ImageDraw.Draw(base)
                base_draw.polygon(back_points, fill=(4, 8, 13, int(panel_profile.get('back_alpha', 186))))
                base_draw.polygon(front_points, fill=(5, 10, 16, int(panel_profile.get('front_alpha', 220))))
                base_draw.polygon(accent_points, fill=rgba(palette.accent_secondary, int(panel_profile.get('accent_alpha', 42))))
                base_draw.rectangle(row_rect, fill=(7, 12, 18, int(panel_profile.get('row_alpha', 234))))
                panel = Image.alpha_composite(panel, base)
                panel = self._fill_polygon_with_vertical_gradient(
                    panel,
                    front_points,
                    str(panel_profile.get('gradient_top', palette.panel_top)),
                    str(panel_profile.get('gradient_bottom', palette.panel_bottom)),
                    alpha=int(panel_profile.get('gradient_alpha', 192)),
                )

                overlay_draw = ImageDraw.Draw(panel)
                top_line_y = int(panel_profile.get('top_line_y', 492))
                overlay_draw.line((64, top_line_y, 1212, top_line_y), fill=(255, 255, 255, int(panel_profile.get('top_line_alpha', 12))), width=1)
                overlay_draw.rounded_rectangle(tuple(panel_profile.get('accent_rail_rect', (64, 489, 136, 495))), radius=3, fill=palette.accent)
                overlay_draw.line((0, row_rect[1], 1280, row_rect[1]), fill=(255, 255, 255, int(panel_profile.get('row_line_alpha', 18))), width=1)
                divider_x = int(panel_profile.get('brand_divider_x', 0) or 0)
                if divider_x:
                    overlay_draw.line(
                        (divider_x, int(panel_profile.get('brand_divider_top', 586)), divider_x, int(panel_profile.get('brand_divider_bottom', 666))),
                        fill=(255, 255, 255, int(panel_profile.get('brand_divider_alpha', 14))),
                        width=1,
                    )
                title_lane_y = int(panel_profile.get('title_lane_y', 0) or 0)
                if title_lane_y:
                    title_lane_left = int(panel_profile.get('title_lane_left', 82))
                    title_lane_right = int(panel_profile.get('title_lane_right', divider_x - 32 if divider_x else 980))
                    overlay_draw.line((title_lane_left, title_lane_y, title_lane_right, title_lane_y), fill=rgba(palette.accent_secondary, int(panel_profile.get('title_lane_alpha', 16))), width=1)
                    overlay_draw.line((title_lane_left, title_lane_y + 1, title_lane_right, title_lane_y + 1), fill=(255, 255, 255, int(panel_profile.get('title_lane_secondary_alpha', 10))), width=1)

                glow = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
                glow_draw = ImageDraw.Draw(glow)
                glow_draw.line((40, top_line_y, 1236, top_line_y), fill=rgba(palette.accent, int(panel_profile.get('glow_alpha', 34))), width=2)
                if title_lane_y:
                    glow_draw.line((int(panel_profile.get('title_lane_left', 82)), title_lane_y, int(panel_profile.get('title_lane_right', divider_x - 32 if divider_x else 980)), title_lane_y), fill=rgba(palette.glow, int(panel_profile.get('title_lane_glow_alpha', 20))), width=2)
                row_glow_alpha = int(panel_profile.get('row_glow_alpha', 0) or 0)
                if row_glow_alpha > 0:
                    glow_draw.line((56, row_rect[1], 1224, row_rect[1]), fill=rgba(palette.accent_secondary, row_glow_alpha), width=2)
                glow = glow.filter(ImageFilter.GaussianBlur(radius=int(max(panel_profile.get('glow_blur', 8), panel_profile.get('title_lane_glow_blur', 10), panel_profile.get('row_glow_blur', 12)))))
                panel = Image.alpha_composite(panel, glow)
                panel = Image.alpha_composite(panel, self._grain_overlay())
                self._panel_cache[cache_key] = panel
                cached = panel
            canvas_rgba = Image.alpha_composite(canvas.convert('RGBA'), cached.copy())
            kicker_text = editorial_phrase or palette.panel_kicker
            kicker_overlay = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
            kicker_draw = ImageDraw.Draw(kicker_overlay)
            kicker_role = self._typography_role('panel_kicker')
            kicker_font = self._load_font_for_text(int(panel_profile.get('kicker_font_size', 13)), kicker_role.candidates, kicker_text, diagnostics=diagnostics, layer='panel_kicker')
            kicker_x = int(panel_profile.get('kicker_x', 148))
            kicker_y = int(panel_profile.get('kicker_y', 474))
            display_kicker = self._draw_role_text(
                kicker_draw,
                (kicker_x, kicker_y),
                kicker_text,
                kicker_font,
                rgba(palette.accent_secondary, int(panel_profile.get('kicker_alpha', 152))),
                role='panel_kicker',
            )
            kicker_rule_right = int(panel_profile.get('kicker_rule_right', 0) or 0)
            if kicker_rule_right > 0:
                kicker_width = int(self._textlength(kicker_draw, display_kicker, kicker_font, letter_spacing=self._letter_spacing_px(kicker_font, kicker_role.tracking_em)))
                rule_left = kicker_x + kicker_width + int(panel_profile.get('kicker_rule_gap', 20))
                if rule_left < kicker_rule_right:
                    kicker_draw.line((rule_left, kicker_y + 8, kicker_rule_right, kicker_y + 8), fill=rgba(palette.accent_secondary, int(panel_profile.get('kicker_rule_alpha', 54))), width=1)
            if diagnostics is not None:
                diagnostics.text_payload['panel_kicker'] = display_kicker
            return Image.alpha_composite(canvas_rgba, kicker_overlay)

        cache_key = card_type.value
        cached = self._panel_cache.get(cache_key)
        if cached is None:
            panel = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
            back_points = [(0, 508), (208, 508), (318, 462), (1280, 462), (1280, 720), (0, 720)]
            front_points = [(0, 524), (248, 524), (326, 486), (1186, 486), (1280, 518), (1280, 720), (0, 720)]
            accent_points = [(0, 524), (144, 524), (236, 486), (294, 486), (214, 720), (0, 720)]
            row_points = [(0, 654), (1280, 654), (1280, 720), (0, 720)]

            shadow = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
            shadow_draw = ImageDraw.Draw(shadow)
            shadow_draw.polygon([(x, y + 16) for x, y in back_points], fill=(0, 0, 0, 102))
            shadow = shadow.filter(ImageFilter.GaussianBlur(radius=22))
            panel = Image.alpha_composite(panel, shadow)

            base = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
            base_draw = ImageDraw.Draw(base)
            base_draw.polygon(back_points, fill=(4, 8, 13, 194))
            base_draw.polygon(front_points, fill=(5, 10, 16, 224))
            base_draw.polygon(accent_points, fill=rgba(palette.accent_secondary, 46))
            base_draw.polygon(row_points, fill=(7, 12, 18, 236))
            panel = Image.alpha_composite(panel, base)
            panel = self._fill_polygon_with_vertical_gradient(panel, front_points, palette.panel_top, palette.panel_bottom, alpha=192)

            overlay_draw = ImageDraw.Draw(panel)
            overlay_draw.line((64, 490, 1212, 490), fill=(255, 255, 255, 10), width=1)
            overlay_draw.rounded_rectangle((64, 487, 136, 493), radius=3, fill=palette.accent)
            overlay_draw.line((0, 654, 1280, 654), fill=(255, 255, 255, 18), width=1)
            overlay_draw.line((82, 626, 964, 626), fill=rgba(palette.accent_secondary, 16), width=1)

            glow = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
            glow_draw = ImageDraw.Draw(glow)
            glow_draw.line((40, 490, 1236, 490), fill=rgba(palette.accent, 40), width=2)
            glow_draw.line((82, 626, 964, 626), fill=rgba(palette.glow, 18), width=2)
            glow_draw.line((56, 654, 1224, 654), fill=rgba(palette.accent_secondary, 20), width=2)
            glow = glow.filter(ImageFilter.GaussianBlur(radius=10))
            panel = Image.alpha_composite(panel, glow)
            panel = Image.alpha_composite(panel, self._grain_overlay())
            self._panel_cache[cache_key] = panel
            cached = panel
        canvas_rgba = Image.alpha_composite(canvas.convert('RGBA'), cached.copy())
        kicker_text = editorial_phrase or palette.panel_kicker
        kicker_overlay = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        kicker_draw = ImageDraw.Draw(kicker_overlay)
        kicker_role = self._typography_role('panel_kicker')
        kicker_font = self._load_font_for_text(13, kicker_role.candidates, kicker_text, diagnostics=diagnostics, layer='panel_kicker')
        display_kicker = self._draw_role_text(
            kicker_draw,
            (152, 471),
            kicker_text,
            kicker_font,
            rgba(palette.accent_secondary, 162),
            role='panel_kicker',
        )
        kicker_width = int(self._textlength(kicker_draw, display_kicker, kicker_font, letter_spacing=self._letter_spacing_px(kicker_font, kicker_role.tracking_em)))
        rule_left = 152 + kicker_width + 20
        if rule_left < 962:
            kicker_draw.line((rule_left, 479, 962, 479), fill=rgba(palette.accent_secondary, 54), width=1)
        if diagnostics is not None:
            diagnostics.text_payload['panel_kicker'] = display_kicker
        return Image.alpha_composite(canvas_rgba, kicker_overlay)


    def draw_title(
        self,
        canvas: Image.Image,
        data: YotoCardData,
        card_type: YotoCardType,
        diagnostics: YotoCardDiagnostics | None = None,
        composition_profile: Mapping[str, Any] | None = None,
    ) -> tuple[Image.Image, YotoTitleLayout]:
        layout = self._resolve_title_layout(data.title, card_type, diagnostics=diagnostics, composition_profile=composition_profile)
        canvas_rgba = canvas.convert('RGBA')
        title_profile = dict((composition_profile or {}).get('title') or {})
        title_role = self._typography_role('title')
        palette = self._palette(card_type)
        line_spacing = max(0, int(title_profile.get('line_gap', 0)))
        measure_draw = ImageDraw.Draw(Image.new('RGBA', (8, 8), (0, 0, 0, 0)))
        title_widths = [
            self._textlength(
                measure_draw,
                self._role_text(line, 'title'),
                layout.font,
                letter_spacing=self._letter_spacing_px(layout.font, title_role.tracking_em),
            )
            for line in layout.lines
        ]
        title_block_width = max(int(width) for width in title_widths) if title_widths else 0
        title_block_height = len(layout.lines) * layout.line_height
        title_block_height += max(0, len(layout.lines) - 1) * line_spacing

        default_plate = {
            YotoCardType.FREE_GAME: {
                'plate_fill': '#07121a',
                'plate_alpha': 72,
                'plate_outline_alpha': 18,
                'plate_shadow_alpha': 50,
                'plate_shadow_blur': 14,
                'plate_accent_alpha': 134,
                'plate_gloss_alpha': 12,
                'plate_radius': 24,
                'plate_pad_left': 24,
                'plate_pad_right': 34,
                'plate_pad_top': 14,
                'plate_pad_bottom': 18,
                'plate_min_width': 332,
                'plate_max_right': 958,
            },
            YotoCardType.DISCOUNT: {
                'plate_fill': '#0a1117',
                'plate_alpha': 76,
                'plate_outline_alpha': 18,
                'plate_shadow_alpha': 54,
                'plate_shadow_blur': 14,
                'plate_accent_alpha': 142,
                'plate_gloss_alpha': 12,
                'plate_radius': 24,
                'plate_pad_left': 24,
                'plate_pad_right': 34,
                'plate_pad_top': 14,
                'plate_pad_bottom': 18,
                'plate_min_width': 336,
                'plate_max_right': 952,
            },
            YotoCardType.FESTIVAL: {
                'plate_fill': '#081521',
                'plate_alpha': 82,
                'plate_outline_alpha': 20,
                'plate_shadow_alpha': 56,
                'plate_shadow_blur': 15,
                'plate_accent_alpha': 154,
                'plate_gloss_alpha': 14,
                'plate_radius': 24,
                'plate_pad_left': 24,
                'plate_pad_right': 36,
                'plate_pad_top': 14,
                'plate_pad_bottom': 18,
                'plate_min_width': 328,
                'plate_max_right': 956,
            },
            YotoCardType.TOP_LIST: {
                'plate_fill': '#0c0f13',
                'plate_alpha': 84,
                'plate_outline_alpha': 20,
                'plate_shadow_alpha': 58,
                'plate_shadow_blur': 15,
                'plate_accent_alpha': 156,
                'plate_gloss_alpha': 14,
                'plate_radius': 24,
                'plate_pad_left': 24,
                'plate_pad_right': 38,
                'plate_pad_top': 14,
                'plate_pad_bottom': 18,
                'plate_min_width': 324,
                'plate_max_right': 952,
            },
        }.get(card_type, {
            'plate_fill': '#08131b',
            'plate_alpha': 74,
            'plate_outline_alpha': 18,
            'plate_shadow_alpha': 52,
            'plate_shadow_blur': 14,
            'plate_accent_alpha': 138,
            'plate_gloss_alpha': 12,
            'plate_radius': 24,
            'plate_pad_left': 24,
            'plate_pad_right': 34,
            'plate_pad_top': 14,
            'plate_pad_bottom': 18,
            'plate_min_width': 328,
            'plate_max_right': 956,
        })
        plate_alpha = int(title_profile.get('plate_alpha', default_plate['plate_alpha']) or 0)
        title_shelf_mode = str(title_profile.get('title_shelf_mode', 'enabled' if plate_alpha > 0 else 'suppressed') or 'suppressed')
        if plate_alpha > 0 and title_block_width > 0:
            plate_pad_left = int(title_profile.get('plate_pad_left', default_plate['plate_pad_left']))
            plate_pad_right = int(title_profile.get('plate_pad_right', default_plate['plate_pad_right']))
            plate_pad_top = int(title_profile.get('plate_pad_top', default_plate['plate_pad_top']))
            plate_pad_bottom = int(title_profile.get('plate_pad_bottom', default_plate['plate_pad_bottom']))
            plate_left = layout.x - plate_pad_left
            natural_right = layout.x + title_block_width + plate_pad_right
            min_right = plate_left + int(title_profile.get('plate_min_width', default_plate['plate_min_width']))
            plate_right = max(natural_right, min_right)
            plate_right = min(plate_right, int(title_profile.get('plate_max_right', default_plate['plate_max_right'])))
            plate_right = max(plate_right, natural_right)
            plate_rect = (
                plate_left,
                layout.y - plate_pad_top,
                plate_right,
                layout.y + title_block_height + plate_pad_bottom,
            )

            plate_overlay = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
            if int(title_profile.get('plate_shadow_alpha', default_plate['plate_shadow_alpha'])) > 0:
                plate_shadow = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
                plate_shadow_draw = ImageDraw.Draw(plate_shadow)
                plate_shadow_draw.rounded_rectangle(
                    (plate_rect[0] + 4, plate_rect[1] + 6, plate_rect[2] + 4, plate_rect[3] + 6),
                    radius=int(title_profile.get('plate_radius', default_plate['plate_radius'])),
                    fill=(0, 0, 0, int(title_profile.get('plate_shadow_alpha', default_plate['plate_shadow_alpha']))),
                )
                plate_shadow = plate_shadow.filter(ImageFilter.GaussianBlur(radius=int(title_profile.get('plate_shadow_blur', default_plate['plate_shadow_blur']))))
                plate_overlay = Image.alpha_composite(plate_overlay, plate_shadow)

            plate_draw = ImageDraw.Draw(plate_overlay)
            plate_draw.rounded_rectangle(
                plate_rect,
                radius=int(title_profile.get('plate_radius', default_plate['plate_radius'])),
                fill=rgba(str(title_profile.get('plate_fill', default_plate['plate_fill'])), plate_alpha),
                outline=(255, 255, 255, int(title_profile.get('plate_outline_alpha', default_plate['plate_outline_alpha']))),
                width=1,
            )
            accent_alpha = int(title_profile.get('plate_accent_alpha', default_plate['plate_accent_alpha']) or 0)
            accent_width = max(0, int(title_profile.get('plate_accent_width', 6) or 0))
            if accent_alpha > 0 and accent_width > 0:
                accent_left = plate_rect[0] + 12
                accent_top = plate_rect[1] + 10
                accent_bottom = plate_rect[3] - 10
                plate_draw.rounded_rectangle(
                    (accent_left, accent_top, accent_left + accent_width, accent_bottom),
                    radius=3,
                    fill=rgba(palette.accent, accent_alpha),
                )
            gloss_alpha = int(title_profile.get('plate_gloss_alpha', default_plate['plate_gloss_alpha']) or 0)
            if gloss_alpha > 0:
                plate_draw.line(
                    (plate_rect[0] + 24, plate_rect[1] + 12, plate_rect[2] - 20, plate_rect[1] + 12),
                    fill=(255, 255, 255, gloss_alpha),
                    width=1,
                )
            connector_right = int(title_profile.get('plate_connector_right', 0) or 0)
            connector_alpha = int(title_profile.get('plate_connector_alpha', 0) or 0)
            if connector_right > plate_rect[2] and connector_alpha > 0:
                connector_y = plate_rect[1] + 14
                plate_draw.line((plate_rect[2] - 1, connector_y, connector_right, connector_y), fill=rgba(palette.accent_secondary, connector_alpha), width=1)
                connector_bottom_y = plate_rect[3] - int(title_profile.get('plate_connector_bottom_offset', 12))
                connector_secondary_alpha = int(title_profile.get('plate_connector_secondary_alpha', 10) or 0)
                if connector_secondary_alpha > 0:
                    plate_draw.line((plate_rect[2] - 1, connector_bottom_y, max(plate_rect[2], connector_right - 24), connector_bottom_y), fill=(255, 255, 255, connector_secondary_alpha), width=1)
            canvas_rgba = Image.alpha_composite(canvas_rgba, plate_overlay)

        if diagnostics is not None:
            diagnostics.text_payload['title_shelf'] = title_shelf_mode if plate_alpha > 0 else 'suppressed'

        halo_alpha = int(title_profile.get('halo_alpha', 0) or 0)
        if halo_alpha > 0:
            halo = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
            halo_draw = ImageDraw.Draw(halo)
            halo_rect = (
                layout.x - int(title_profile.get('halo_pad_x', 34)),
                layout.y - int(title_profile.get('halo_pad_y', 20)),
                layout.x + title_block_width + int(title_profile.get('halo_pad_x', 34)),
                layout.y + title_block_height + int(title_profile.get('halo_pad_y', 20)),
            )
            halo_fill = ImageColor.getrgb(str(title_profile.get('halo_fill', '#08131b')))
            halo_draw.rounded_rectangle(
                halo_rect,
                radius=int(title_profile.get('halo_radius', 24)),
                fill=(*halo_fill, halo_alpha),
            )
            halo = halo.filter(ImageFilter.GaussianBlur(radius=int(title_profile.get('halo_blur', 24))))
            canvas_rgba = Image.alpha_composite(canvas_rgba, halo)
        draw = ImageDraw.Draw(canvas_rgba)
        shadow_layers = tuple(title_profile.get('shadow_layers', title_role.shadow_layers or ((4, 5, 132), (2, 3, 94))))
        stroke_width = int(title_profile.get('stroke_width', title_role.stroke_width))
        stroke_fill = title_profile.get('stroke_fill', title_role.stroke_fill)
        for index, line in enumerate(layout.lines):
            y = layout.y + index * (layout.line_height + line_spacing)
            self._draw_role_text(
                draw,
                (layout.x, y),
                line,
                layout.font,
                WHITE,
                role='title',
                shadow_layers=shadow_layers,
                stroke_width=stroke_width,
                stroke_fill=stroke_fill,
            )
        return canvas_rgba, layout

    def draw_deadline_pill(
        self,
        canvas: Image.Image,
        data: YotoCardData,
        title_layout: YotoTitleLayout,
        card_type: YotoCardType,
        diagnostics: YotoCardDiagnostics | None = None,
    ) -> Image.Image:
        if not data.deadline:
            return canvas
        palette = self._palette(card_type)
        overlay = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        deadline_role = self._typography_role('deadline')
        font_size = 21 if title_layout.mode == 'two_line' else 22
        font = self._load_font_for_text(font_size, deadline_role.candidates, data.deadline, diagnostics=diagnostics, layer='deadline')
        x = SAFE_LEFT + 32
        y = title_layout.meta_y + 4
        text_width = int(self._textlength(draw, data.deadline, font, letter_spacing=self._letter_spacing_px(font, deadline_role.tracking_em)))
        rect = (x, y, x + text_width + 54, y + 38)
        draw.rounded_rectangle(rect, radius=15, fill=rgba(palette.deadline_fill, 208), outline=rgba(palette.deadline_border, 214), width=1)
        draw.ellipse((x + 14, y + 14, x + 22, y + 22), fill=palette.accent)
        self._draw_role_text(draw, (x + 30, y + 7), data.deadline, font, palette.deadline_text, role='deadline')
        return Image.alpha_composite(canvas.convert('RGBA'), overlay)


    def draw_free_game_meta_row(
        self,
        canvas: Image.Image,
        data: YotoCardData,
        title_layout: YotoTitleLayout,
        diagnostics: YotoCardDiagnostics | None = None,
        composition_profile: Mapping[str, Any] | None = None,
    ) -> tuple[Image.Image, str]:
        overlay = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        meta_profile = dict((composition_profile or {}).get('meta') or {})
        deadline_role = self._typography_role('deadline')
        secondary_role = self._typography_role('meta_secondary')
        x = int(meta_profile.get('x', SAFE_LEFT + 32))
        y = title_layout.meta_y + int(meta_profile.get('y_offset', 4))
        gap = int(meta_profile.get('gap', 14))
        alignment = 'hidden'

        if data.deadline:
            deadline_font_size = int(meta_profile.get('deadline_font_size_two' if title_layout.mode == 'two_line' else 'deadline_font_size_single', 22))
            deadline_font = self._load_font_for_text(deadline_font_size, deadline_role.candidates, data.deadline, diagnostics=diagnostics, layer='deadline')
            deadline_width = int(self._textlength(draw, data.deadline, deadline_font, letter_spacing=self._letter_spacing_px(deadline_font, deadline_role.tracking_em)))
            deadline_rect = (
                x,
                y,
                x + deadline_width + int(meta_profile.get('deadline_padding_x', 58)),
                y + int(meta_profile.get('chip_height', 40)),
            )
            draw.rounded_rectangle(
                deadline_rect,
                radius=int(meta_profile.get('primary_radius', 15)),
                fill=rgba(str(meta_profile.get('primary_fill', '#0a3a28')), int(meta_profile.get('primary_fill_alpha', 214))),
                outline=rgba(str(meta_profile.get('primary_border', '#27e07d')), int(meta_profile.get('primary_outline_alpha', 214))),
                width=1,
            )
            draw.ellipse(
                (
                    x + int(meta_profile.get('deadline_dot_left', 14)),
                    y + int(meta_profile.get('deadline_dot_top', 15)),
                    x + int(meta_profile.get('deadline_dot_right', 22)),
                    y + int(meta_profile.get('deadline_dot_bottom', 23)),
                ),
                fill=str(meta_profile.get('primary_dot_fill', '#27e07d')),
            )
            display_deadline = self._draw_role_text(
                draw,
                (x + int(meta_profile.get('deadline_text_x', 30)), y + int(meta_profile.get('deadline_text_y', 7))),
                data.deadline,
                deadline_font,
                str(meta_profile.get('primary_text_fill', '#d8fff0')),
                role='deadline',
            )
            if diagnostics is not None:
                diagnostics.text_payload['meta_deadline'] = display_deadline
            x = deadline_rect[2] + gap
            alignment = 'pill_row'

        if data.old_price:
            old_text = f"{UA_OLD_PRICE_PREFIX} {data.old_price}"
            old_font_size = int(meta_profile.get('old_price_font_size', 21))
            old_font = self._load_font_for_text(old_font_size, secondary_role.candidates, old_text, diagnostics=diagnostics, layer='price_old')
            old_width = int(self._textlength(draw, old_text, old_font, letter_spacing=self._letter_spacing_px(old_font, secondary_role.tracking_em)))
            old_rect = (
                x,
                y,
                x + old_width + int(meta_profile.get('old_price_padding_x', 36)),
                y + int(meta_profile.get('chip_height', 40)),
            )
            draw.rounded_rectangle(
                old_rect,
                radius=int(meta_profile.get('secondary_radius', 15)),
                fill=tuple(int(value) for value in meta_profile.get('secondary_fill', (255, 255, 255, 18))),
                outline=(255, 255, 255, int(meta_profile.get('secondary_outline_alpha', 44))),
                width=1,
            )
            display_old = self._draw_role_text(
                draw,
                (x + int(meta_profile.get('old_price_text_x', 18)), y + int(meta_profile.get('old_price_text_y', 7))),
                old_text,
                old_font,
                tuple(int(value) for value in meta_profile.get('secondary_text_fill', (204, 214, 226, 214))),
                role='meta_secondary',
            )
            if diagnostics is not None:
                diagnostics.text_payload['meta_old_price'] = display_old
            alignment = 'pill_row'

        return Image.alpha_composite(canvas.convert('RGBA'), overlay), alignment



    def _editorial_meta_items(
        self,
        data: YotoCardData,
        diagnostics: YotoCardDiagnostics | None,
        card_type: YotoCardType,
    ) -> list[tuple[str, str, str]]:
        panel_kicker = self._normalize_display_text(str((diagnostics.text_payload.get('panel_kicker') if diagnostics is not None else '') or ''))
        seen: set[str] = set()
        items: list[tuple[str, str, str]] = []

        def add(value: str | None, tone: str, kind: str) -> None:
            normalized = self._normalize_display_text(str(value or ''))
            if not normalized:
                return
            if panel_kicker and normalized.casefold() == panel_kicker.casefold() and kind != 'rank':
                return
            key = normalized.casefold()
            if key in seen:
                return
            seen.add(key)
            items.append((normalized, tone, kind))

        if card_type == YotoCardType.FESTIVAL:
            add(data.deadline, 'primary', 'deadline')
            add(data.platform_badge, 'secondary', 'signal')
            add(diagnostics.editorial_phrase if diagnostics is not None else None, 'secondary', 'signal')
        elif card_type == YotoCardType.TOP_LIST:
            top_rank = diagnostics.sticker_text if diagnostics is not None else data.sticker_text
            add(str(top_rank or '').upper(), 'primary', 'rank')
            add(diagnostics.editorial_phrase if diagnostics is not None else None, 'secondary', 'signal')
            add(data.list_label, 'secondary', 'signal')
        return items[:2]

    def draw_editorial_meta_row(
        self,
        canvas: Image.Image,
        data: YotoCardData,
        title_layout: YotoTitleLayout,
        card_type: YotoCardType,
        diagnostics: YotoCardDiagnostics | None = None,
        composition_profile: Mapping[str, Any] | None = None,
    ) -> tuple[Image.Image, str]:
        items = self._editorial_meta_items(data, diagnostics, card_type)
        if not items:
            return canvas, 'hidden'

        overlay = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        meta_profile = dict((composition_profile or {}).get('meta') or {})
        defaults = {
            YotoCardType.FESTIVAL: {
                'x': 82,
                'y_offset': 8,
                'gap': 10,
                'chip_height': 36,
                'max_right': 996,
                'primary_radius': 14,
                'primary_fill': '#143346',
                'primary_fill_alpha': 206,
                'primary_border': EVENT_CYAN,
                'primary_outline_alpha': 180,
                'primary_text_fill': '#d9f8ff',
                'primary_dot_fill': EVENT_CYAN,
                'deadline_padding_x': 50,
                'deadline_text_x': 26,
                'deadline_text_y': 6,
                'deadline_dot_left': 12,
                'deadline_dot_top': 14,
                'deadline_dot_right': 20,
                'deadline_dot_bottom': 22,
                'deadline_font_size_single': 20,
                'deadline_font_size_two': 19,
                'primary_padding_x': 34,
                'primary_text_x': 18,
                'primary_text_y': 6,
                'primary_font_size_single': 20,
                'primary_font_size_two': 19,
                'secondary_fill': (255, 255, 255, 12),
                'secondary_outline_alpha': 30,
                'secondary_radius': 14,
                'secondary_text_fill': (212, 222, 234, 206),
                'secondary_padding_x': 30,
                'secondary_text_x': 16,
                'secondary_text_y': 6,
                'secondary_font_size': 18,
            },
            YotoCardType.TOP_LIST: {
                'x': 82,
                'y_offset': 8,
                'gap': 10,
                'chip_height': 36,
                'max_right': 996,
                'primary_radius': 14,
                'primary_fill': '#4a3712',
                'primary_fill_alpha': 200,
                'primary_border': '#f0c670',
                'primary_outline_alpha': 172,
                'primary_text_fill': '#fff0bf',
                'primary_padding_x': 34,
                'primary_text_x': 18,
                'primary_text_y': 6,
                'primary_font_size_single': 20,
                'primary_font_size_two': 19,
                'secondary_fill': (255, 255, 255, 12),
                'secondary_outline_alpha': 28,
                'secondary_radius': 14,
                'secondary_text_fill': (224, 216, 194, 206),
                'secondary_padding_x': 28,
                'secondary_text_x': 16,
                'secondary_text_y': 6,
                'secondary_font_size': 18,
            },
        }.get(card_type, {})
        meta_profile = {**defaults, **meta_profile}
        palette = self._palette(card_type)
        primary_role = self._typography_role('meta_primary')
        secondary_role = self._typography_role('meta_secondary')
        deadline_role = self._typography_role('deadline')
        x = int(meta_profile.get('x', SAFE_LEFT + 32))
        y = title_layout.meta_y + int(meta_profile.get('y_offset', 8))
        gap = int(meta_profile.get('gap', 10))
        chip_height = int(meta_profile.get('chip_height', 36))
        max_right = int(meta_profile.get('max_right', CARD_SIZE[0] - SAFE_RIGHT - 256))

        for text_value, tone, kind in items:
            remaining_width = max_right - x
            if remaining_width < 132:
                break
            if kind == 'deadline':
                role = deadline_role
                font_size = int(meta_profile.get('deadline_font_size_two' if title_layout.mode == 'two_line' else 'deadline_font_size_single', 20))
                padding_x = int(meta_profile.get('deadline_padding_x', 50))
                text_x = int(meta_profile.get('deadline_text_x', 26))
                text_y = int(meta_profile.get('deadline_text_y', 6))
            elif tone == 'primary':
                role = primary_role
                font_size = int(meta_profile.get('primary_font_size_two' if title_layout.mode == 'two_line' else 'primary_font_size_single', 20))
                padding_x = int(meta_profile.get('primary_padding_x', 34))
                text_x = int(meta_profile.get('primary_text_x', 18))
                text_y = int(meta_profile.get('primary_text_y', 6))
            else:
                role = secondary_role
                font_size = int(meta_profile.get('secondary_font_size', 18))
                padding_x = int(meta_profile.get('secondary_padding_x', 28))
                text_x = int(meta_profile.get('secondary_text_x', 16))
                text_y = int(meta_profile.get('secondary_text_y', 6))

            layer_name = 'deadline' if kind == 'deadline' else 'meta_primary' if tone == 'primary' else 'meta_secondary'
            font = self._load_font_for_text(font_size, role.candidates, text_value, diagnostics=diagnostics, layer=layer_name)
            spacing = self._letter_spacing_px(font, role.tracking_em)
            label = self._ellipsize(draw, text_value, font, max(108, remaining_width - padding_x + 12), letter_spacing=spacing)
            chip_width = min(remaining_width, int(self._textlength(draw, label, font, letter_spacing=spacing)) + padding_x)
            rect = (x, y, x + chip_width, y + chip_height)

            if tone == 'primary':
                draw.rounded_rectangle(
                    rect,
                    radius=int(meta_profile.get('primary_radius', 14)),
                    fill=rgba(str(meta_profile.get('primary_fill', '#173346')), int(meta_profile.get('primary_fill_alpha', 206))),
                    outline=rgba(str(meta_profile.get('primary_border', palette.accent)), int(meta_profile.get('primary_outline_alpha', 180))),
                    width=1,
                )
                if kind == 'deadline':
                    draw.ellipse(
                        (
                            x + int(meta_profile.get('deadline_dot_left', 12)),
                            y + int(meta_profile.get('deadline_dot_top', 14)),
                            x + int(meta_profile.get('deadline_dot_right', 20)),
                            y + int(meta_profile.get('deadline_dot_bottom', 22)),
                        ),
                        fill=str(meta_profile.get('primary_dot_fill', palette.accent)),
                    )
                display_label = self._draw_role_text(
                    draw,
                    (x + text_x, y + text_y),
                    label,
                    font,
                    str(meta_profile.get('primary_text_fill', '#f4f8ff')),
                    role='deadline' if kind == 'deadline' else 'meta_primary',
                )
                if diagnostics is not None:
                    diagnostics.text_payload['meta_primary_label'] = display_label
            else:
                draw.rounded_rectangle(
                    rect,
                    radius=int(meta_profile.get('secondary_radius', 14)),
                    fill=tuple(int(value) for value in meta_profile.get('secondary_fill', (255, 255, 255, 12))),
                    outline=(255, 255, 255, int(meta_profile.get('secondary_outline_alpha', 30))),
                    width=1,
                )
                display_label = self._draw_role_text(
                    draw,
                    (x + text_x, y + text_y),
                    label,
                    font,
                    tuple(int(value) for value in meta_profile.get('secondary_text_fill', (212, 221, 232, 206))),
                    role='meta_secondary',
                )
                if diagnostics is not None:
                    diagnostics.text_payload['meta_secondary_label'] = display_label
            x = rect[2] + gap

        return Image.alpha_composite(canvas.convert('RGBA'), overlay), 'editorial_row'

    def draw_discount_meta_row(
        self,
        canvas: Image.Image,
        data: YotoCardData,
        title_layout: YotoTitleLayout,
        diagnostics: YotoCardDiagnostics | None = None,
        composition_profile: Mapping[str, Any] | None = None,
    ) -> tuple[Image.Image, str]:
        current_text = self._normalize_display_text(str(data.current_price or '')) if data.current_price else None
        old_text = f"{UA_OLD_PRICE_PREFIX} {data.old_price}" if data.old_price else None
        deadline_text = self._normalize_display_text(str(data.deadline or '')) if data.deadline else None
        if not current_text and not old_text and not deadline_text:
            return canvas, 'hidden'

        overlay = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        meta_profile = dict((composition_profile or {}).get('meta') or {})
        primary_role = self._typography_role('meta_primary')
        secondary_role = self._typography_role('meta_secondary')
        deadline_role = self._typography_role('deadline')
        x = int(meta_profile.get('x', SAFE_LEFT + 32))
        y = title_layout.meta_y + int(meta_profile.get('y_offset', 6))
        gap = int(meta_profile.get('gap', 12))
        chip_height = int(meta_profile.get('chip_height', 40))
        max_right = int(meta_profile.get('max_right', CARD_SIZE[0] - SAFE_RIGHT - 256))
        alignment = 'hidden'

        if current_text:
            percent_signal = '%' in current_text
            font_key = 'current_font_size_two_percent' if title_layout.mode == 'two_line' and percent_signal else 'current_font_size_single_percent' if percent_signal else 'current_font_size_two_price' if title_layout.mode == 'two_line' else 'current_font_size_single_price'
            current_font = self._load_font_for_text(int(meta_profile.get(font_key, 26)), primary_role.candidates, current_text, diagnostics=diagnostics, layer='price_current')
            current_width = int(self._textlength(draw, current_text, current_font, letter_spacing=self._letter_spacing_px(current_font, primary_role.tracking_em)))
            current_rect = (
                x,
                y,
                x + current_width + int(meta_profile.get('current_padding_x', 34)),
                y + chip_height,
            )
            fill_key = 'current_fill_percent' if percent_signal else 'current_fill_price'
            outline_key = 'current_outline_percent' if percent_signal else 'current_outline_price'
            draw.rounded_rectangle(
                current_rect,
                radius=int(meta_profile.get('current_radius', 15)),
                fill=rgba(str(meta_profile.get(fill_key, '#4b1e0c')), int(meta_profile.get('current_fill_alpha', 232))),
                outline=rgba(str(meta_profile.get(outline_key, DISCOUNT_ORANGE)), int(meta_profile.get('current_outline_alpha', 214))),
                width=1,
            )
            display_current = self._draw_role_text(
                draw,
                (x + int(meta_profile.get('current_text_x', 18)), y + int(meta_profile.get('current_text_y', 6))),
                current_text,
                current_font,
                str(meta_profile.get('current_text_fill', '#fff2e7')),
                role='meta_primary',
            )
            if diagnostics is not None:
                diagnostics.text_payload['meta_current_signal'] = display_current
            x = current_rect[2] + gap
            alignment = 'pill_row'

        if deadline_text and x < max_right:
            deadline_font_size = int(meta_profile.get('deadline_font_size_two' if title_layout.mode == 'two_line' else 'deadline_font_size_single', 21))
            deadline_font = self._load_font_for_text(deadline_font_size, deadline_role.candidates, deadline_text, diagnostics=diagnostics, layer='deadline')
            remaining_width = max_right - x
            min_deadline_width = 144
            if remaining_width >= min_deadline_width:
                text_width = int(self._textlength(draw, deadline_text, deadline_font, letter_spacing=self._letter_spacing_px(deadline_font, deadline_role.tracking_em)))
                deadline_width = min(text_width + int(meta_profile.get('deadline_padding_x', 52)), int(meta_profile.get('deadline_max_width', 286)), remaining_width)
                deadline_text_width = max(0, deadline_width - int(meta_profile.get('deadline_padding_x', 52)) + 18)
                deadline_label = self._ellipsize(draw, deadline_text, deadline_font, deadline_text_width, letter_spacing=self._letter_spacing_px(deadline_font, deadline_role.tracking_em))
                deadline_rect = (x, y, x + deadline_width, y + chip_height)
                draw.rounded_rectangle(
                    deadline_rect,
                    radius=int(meta_profile.get('deadline_radius', 15)),
                    fill=rgba(str(meta_profile.get('deadline_fill', '#2c1a12')), int(meta_profile.get('deadline_fill_alpha', 198))),
                    outline=rgba(str(meta_profile.get('deadline_outline', '#ffb35a')), int(meta_profile.get('deadline_outline_alpha', 108))),
                    width=1,
                )
                display_deadline = self._draw_role_text(
                    draw,
                    (x + int(meta_profile.get('deadline_text_x', 18)), y + int(meta_profile.get('deadline_text_y', 7))),
                    deadline_label,
                    deadline_font,
                    str(meta_profile.get('deadline_text_fill', '#ffd8c2')),
                    role='deadline',
                )
                if diagnostics is not None:
                    diagnostics.text_payload['meta_deadline'] = display_deadline
                x = deadline_rect[2] + gap
                alignment = 'pill_row'

        if old_text and x < max_right:
            old_font = self._load_font_for_text(int(meta_profile.get('old_price_font_size', 21)), secondary_role.candidates, old_text, diagnostics=diagnostics, layer='price_old')
            remaining_width = max_right - x
            min_old_width = 136
            if remaining_width >= min_old_width:
                text_width = int(self._textlength(draw, old_text, old_font, letter_spacing=self._letter_spacing_px(old_font, secondary_role.tracking_em)))
                old_width = min(text_width + int(meta_profile.get('old_price_padding_x', 34)), remaining_width)
                old_text_width = max(0, old_width - int(meta_profile.get('old_price_padding_x', 34)) + 16)
                old_label = self._ellipsize(draw, old_text, old_font, old_text_width, letter_spacing=self._letter_spacing_px(old_font, secondary_role.tracking_em))
                old_rect = (x, y, x + old_width, y + chip_height)
                draw.rounded_rectangle(
                    old_rect,
                    radius=int(meta_profile.get('secondary_radius', 15)),
                    fill=tuple(int(value) for value in meta_profile.get('secondary_fill', (255, 255, 255, 18))),
                    outline=(255, 255, 255, int(meta_profile.get('secondary_outline_alpha', 44))),
                    width=1,
                )
                display_old = self._draw_role_text(
                    draw,
                    (x + int(meta_profile.get('old_price_text_x', 18)), y + int(meta_profile.get('old_price_text_y', 7))),
                    old_label,
                    old_font,
                    tuple(int(value) for value in meta_profile.get('secondary_text_fill', (212, 221, 232, 216))),
                    role='meta_secondary',
                )
                if diagnostics is not None:
                    diagnostics.text_payload['meta_old_price'] = display_old
                alignment = 'pill_row'

        return Image.alpha_composite(canvas.convert('RGBA'), overlay), alignment


    def draw_price_information(
        self,
        canvas: Image.Image,
        data: YotoCardData,
        title_layout: YotoTitleLayout,
        card_type: YotoCardType,
        diagnostics: YotoCardDiagnostics | None = None,
    ) -> tuple[Image.Image, str]:
        if not data.old_price and not data.current_price:
            return canvas, 'hidden'
        palette = self._palette(card_type)
        overlay = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        primary_role = self._typography_role('meta_primary')
        secondary_role = self._typography_role('meta_secondary')
        y = title_layout.meta_y + 8
        meta_left = 496 if title_layout.mode == 'single_line' else 470
        meta_right = CARD_SIZE[0] - SAFE_RIGHT - 250

        old_text = f"{UA_OLD_PRICE_PREFIX} {data.old_price}" if data.old_price else None
        current_text = str(data.current_price) if data.current_price else None
        regular_font = self._load_font_for_text(22, secondary_role.candidates, old_text or '', diagnostics=diagnostics, layer='price_old')
        accent_font = self._load_font_for_text(30 if card_type == YotoCardType.DISCOUNT else 24, primary_role.candidates, current_text or '', diagnostics=diagnostics, layer='price_current')

        if card_type == YotoCardType.DISCOUNT and current_text and old_text:
            current_fill = palette.accent if '%' in current_text else palette.meta_accent
            display_current = self._draw_role_text(draw, (meta_left, y - 4), current_text, accent_font, current_fill, role='meta_primary')
            current_width = int(self._textlength(draw, display_current, accent_font, letter_spacing=self._letter_spacing_px(accent_font, primary_role.tracking_em)))
            divider_x = meta_left + current_width + 18
            draw.line((divider_x, y + 4, divider_x, y + 26), fill=(255, 255, 255, 24), width=1)
            old_x = divider_x + 16
            display_old = self._draw_role_text(draw, (old_x, y), old_text, regular_font, NEUTRAL_TEXT, role='meta_secondary')
            if diagnostics is not None:
                diagnostics.text_payload['meta_current_signal'] = display_current
                diagnostics.text_payload['meta_old_price'] = display_old
            return Image.alpha_composite(canvas.convert('RGBA'), overlay), 'standard'

        if old_text and current_text:
            current_x = meta_left
            display_current = self._draw_role_text(draw, (current_x, y), current_text, accent_font, palette.meta_accent, role='meta_primary')
            current_x += int(self._textlength(draw, display_current, accent_font, letter_spacing=self._letter_spacing_px(accent_font, primary_role.tracking_em))) + 24
            display_old = self._draw_role_text(draw, (current_x, y + 2), old_text, regular_font, NEUTRAL_TEXT, role='meta_secondary')
            if diagnostics is not None:
                diagnostics.text_payload['meta_current_signal'] = display_current
                diagnostics.text_payload['meta_old_price'] = display_old
            return Image.alpha_composite(canvas.convert('RGBA'), overlay), 'standard'

        if old_text:
            display_old = self._draw_role_text(draw, (meta_left, y), old_text, regular_font, NEUTRAL_TEXT, role='meta_secondary')
            if diagnostics is not None:
                diagnostics.text_payload['meta_old_price'] = display_old
            return Image.alpha_composite(canvas.convert('RGBA'), overlay), 'standard'

        if current_text:
            text_width = int(self._textlength(draw, current_text, accent_font, letter_spacing=self._letter_spacing_px(accent_font, primary_role.tracking_em)))
            x = int((meta_left + meta_right - text_width) / 2)
            fill = palette.accent if card_type == YotoCardType.DISCOUNT and '%' in current_text else palette.meta_accent
            display_current = self._draw_role_text(draw, (x, y - 2), current_text, accent_font, fill, role='meta_primary')
            if diagnostics is not None:
                diagnostics.text_payload['meta_current_signal'] = display_current
            return Image.alpha_composite(canvas.convert('RGBA'), overlay), 'centered'

        return Image.alpha_composite(canvas.convert('RGBA'), overlay), 'hidden'


    def draw_yoto_brand_lockup(
        self,
        canvas: Image.Image,
        data: YotoCardData,
        card_type: YotoCardType,
        diagnostics: YotoCardDiagnostics | None = None,
        composition_profile: Mapping[str, Any] | None = None,
    ) -> Image.Image:
        palette = self._palette(card_type)
        brand_profile = dict((composition_profile or {}).get('brand') or {})
        brand_role = self._typography_role('brand_wordmark')
        micro_role = self._typography_role('brand_micro')
        if brand_profile:
            overlay = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
            x = int(brand_profile.get('x', CARD_SIZE[0] - SAFE_RIGHT - 212))
            y = int(brand_profile.get('y', 596))
            width = int(brand_profile.get('width', 212))
            height = int(brand_profile.get('height', 58))
            radius = int(brand_profile.get('radius', 18))
            shadow_alpha = int(brand_profile.get('shadow_alpha', 78))
            if shadow_alpha > 0:
                shadow = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
                shadow_draw = ImageDraw.Draw(shadow)
                shadow_draw.rounded_rectangle((x + 4, y + 6, x + width + 4, y + height + 6), radius=radius, fill=(0, 0, 0, shadow_alpha))
                shadow = shadow.filter(ImageFilter.GaussianBlur(radius=int(brand_profile.get('shadow_blur', 10))))
                overlay = Image.alpha_composite(overlay, shadow)

            draw = ImageDraw.Draw(overlay)
            rect = (x, y, x + width, y + height)
            draw.rounded_rectangle(
                rect,
                radius=radius,
                fill=(7, 12, 18, int(brand_profile.get('fill_alpha', 204))),
                outline=(255, 255, 255, int(brand_profile.get('outline_alpha', 20))),
                width=1,
            )
            style = str(brand_profile.get('style') or 'default')
            icon_left = x + int(brand_profile.get('icon_left', 14))
            icon_top = y + int(brand_profile.get('icon_top', 16))
            icon_size = int(brand_profile.get('icon_size', 36))
            if style == 'grid_chip':
                draw.rounded_rectangle(
                    (x + 10, y + 10, x + 16, y + height - 10),
                    radius=3,
                    fill=rgba(palette.accent_secondary, int(brand_profile.get('accent_line_alpha', 108))),
                )
                draw.line((x + 20, y + 12, x + width - 14, y + 12), fill=(255, 255, 255, 12), width=1)
            else:
                draw.line((x + 16, y + 14, x + width - 18, y + 14), fill=rgba(palette.accent_secondary, int(brand_profile.get('accent_line_alpha', 108))), width=2)
            draw.rounded_rectangle((icon_left, icon_top, icon_left + icon_size, icon_top + icon_size), radius=int(brand_profile.get('icon_radius', 12)), fill=palette.brand_fill)
            y_font = self._load_font_for_text(int(brand_profile.get('y_font_size', 22)), brand_role.candidates, 'Y', diagnostics=diagnostics, layer='brand_wordmark')
            body_font = self._load_font_for_text(int(brand_profile.get('body_font_size', 26)), brand_role.candidates, 'YOTO', diagnostics=diagnostics, layer='brand_wordmark')
            default_micro = BRAND_MICRO_LABELS.get(card_type.value, BRAND_MICRO_LABELS['DISCOUNT'])
            micro = data.brand_micro_label or default_micro
            micro_font = self._load_font_for_text(int(brand_profile.get('micro_font_size', 12)), micro_role.candidates, micro, diagnostics=diagnostics, layer='brand_micro')
            display_micro = self._role_text(micro, 'brand_micro')
            if diagnostics is not None:
                diagnostics.text_payload['brand_micro'] = display_micro
            self._draw_text_line(draw, (icon_left + int(brand_profile.get('y_text_x', 10)), icon_top + int(brand_profile.get('y_text_y', 5))), 'Y', y_font, '#07120d')
            text_x = x + int(brand_profile.get('text_x', 58))
            self._draw_role_text(draw, (text_x, y + int(brand_profile.get('micro_y', 8))), display_micro, micro_font, '#aab5c6', role='brand_micro')
            self._draw_role_text(draw, (text_x, y + int(brand_profile.get('body_y', 22))), 'YOTO', body_font, WHITE, role='brand_wordmark')
            return Image.alpha_composite(canvas.convert('RGBA'), overlay)

        overlay = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        shadow = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        x = CARD_SIZE[0] - SAFE_RIGHT - 220
        y = 598
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rounded_rectangle((x + 6, y + 8, x + 220 + 6, y + 68 + 8), radius=20, fill=(0, 0, 0, 98))
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=12))
        overlay = Image.alpha_composite(overlay, shadow)

        draw = ImageDraw.Draw(overlay)
        rect = (x, y, x + 220, y + 68)
        draw.rounded_rectangle(rect, radius=20, fill=(7, 12, 18, 220), outline=(255, 255, 255, 22), width=1)
        draw.line((x + 18, y + 14, x + 198, y + 14), fill=rgba(palette.accent_secondary, 120), width=2)
        draw.rounded_rectangle((x + 18, y + 18, x + 56, y + 56), radius=12, fill=palette.brand_fill)
        y_font = self._load_font_for_text(23, brand_role.candidates, 'Y', diagnostics=diagnostics, layer='brand_wordmark')
        body_font = self._load_font_for_text(28, brand_role.candidates, 'YOTO', diagnostics=diagnostics, layer='brand_wordmark')
        default_micro = BRAND_MICRO_LABELS.get(card_type.value, BRAND_MICRO_LABELS['DISCOUNT'])
        micro = data.brand_micro_label or default_micro
        micro_font = self._load_font_for_text(13, micro_role.candidates, micro, diagnostics=diagnostics, layer='brand_micro')
        display_micro = self._role_text(micro, 'brand_micro')
        if diagnostics is not None:
            diagnostics.text_payload['brand_micro'] = display_micro
        self._draw_text_line(draw, (x + 29, y + 22), 'Y', y_font, '#07120d')
        self._draw_role_text(draw, (x + 68, y + 10), display_micro, micro_font, '#aab5c6', role='brand_micro')
        self._draw_role_text(draw, (x + 68, y + 30), 'YOTO', body_font, WHITE, role='brand_wordmark')
        return Image.alpha_composite(canvas.convert('RGBA'), overlay)

    def _compose_hero_artwork(self, artwork: Image.Image) -> Image.Image:
        hero = self._smart_cover(
            artwork,
            (CARD_SIZE[0], HERO_HEIGHT),
            zoom_levels=(1.0, 0.92, 0.84, 0.76),
            candidate_rows=(0.24, 0.38, 0.52, 0.68),
        )
        hero = Image.blend(hero, Image.new('RGB', hero.size, '#091017'), 0.08)
        return hero

    def _apply_hero_depth(self, canvas: Image.Image, card_type: YotoCardType) -> Image.Image:
        palette = self._palette(card_type)
        cache_key = (CARD_SIZE, card_type.value)
        cached = self._hero_depth_cache.get(cache_key)
        if cached is None:
            overlay = Image.new('RGBA', CARD_SIZE, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            draw.ellipse((876, -18, 1246, 202), fill=rgba(palette.glow, 18))
            draw.ellipse((-70, 34, 280, 294), fill=rgba(palette.accent_secondary, 10))
            draw.ellipse((248, 46, 920, 320), fill=(255, 255, 255, 6))
            for x in range(930, CARD_SIZE[0]):
                alpha = int(10 * ((x - 930) / max(CARD_SIZE[0] - 930, 1)))
                draw.line((x, 0, x, 392), fill=(0, 0, 0, alpha))
            overlay = overlay.filter(ImageFilter.GaussianBlur(radius=16))
            overlay = Image.alpha_composite(overlay, self._readability_gradient_overlay(card_type))
            self._hero_depth_cache[cache_key] = overlay
            cached = overlay
        return Image.alpha_composite(canvas.convert('RGBA'), cached.copy())

    def _readability_gradient_overlay(self, card_type: YotoCardType) -> Image.Image:
        palette = self._palette(card_type)
        overlay = Image.new('RGBA', CARD_SIZE, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        if card_type == YotoCardType.DISCOUNT:
            top_alpha, middle_alpha, bottom_alpha = 0, 30, 120
            split = int(HERO_HEIGHT * 0.58)
        elif card_type == YotoCardType.FREE_GAME:
            top_alpha, middle_alpha, bottom_alpha = 0, 28, 112
            split = int(HERO_HEIGHT * 0.57)
        else:
            top_alpha, middle_alpha, bottom_alpha = 0, 34, 132
            split = int(HERO_HEIGHT * 0.54)
        top_rgb = ImageColor.getrgb('#071019')
        bottom_rgb = ImageColor.getrgb(palette.panel_bottom)
        height = CARD_SIZE[1]
        for y in range(height):
            if y < split:
                ratio = y / max(split, 1)
                alpha = int(top_alpha + (middle_alpha - top_alpha) * ratio)
            else:
                ratio = (y - split) / max(height - split, 1)
                alpha = int(middle_alpha + (bottom_alpha - middle_alpha) * ratio)
            color_ratio = y / max(height - 1, 1)
            color = tuple(int(top_rgb[idx] + (bottom_rgb[idx] - top_rgb[idx]) * color_ratio) for idx in range(3))
            draw.line((0, y, CARD_SIZE[0], y), fill=(*color, max(0, min(alpha, 188))))
        glow = Image.new('RGBA', CARD_SIZE, (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        glow_draw.ellipse((-120, 430, 520, 760), fill=rgba(palette.accent_secondary, 12 if card_type == YotoCardType.DISCOUNT else 10))
        glow_draw.ellipse((760, 448, 1360, 760), fill=rgba(palette.glow, 10 if card_type == YotoCardType.DISCOUNT else 8))
        glow = glow.filter(ImageFilter.GaussianBlur(radius=36))
        return Image.alpha_composite(overlay, glow)

    def _platform_badge_text(self, data: YotoCardData, card_type: YotoCardType) -> str:
        if data.platform_badge:
            return self._normalize_display_text(data.platform_badge)
        platform = self._normalize_display_text(str(data.platform or '').upper().strip())
        if card_type == YotoCardType.FREE_GAME:
            return f'{platform} {GIVEAWAY_LABEL}' if platform else GIVEAWAY_LABEL
        if card_type == YotoCardType.DISCOUNT:
            return f'{platform} {SALE_LABEL}' if platform else SALE_LABEL
        if card_type == YotoCardType.FESTIVAL:
            return f'{EVENT_LABEL} {platform}' if platform else EVENT_LABEL
        return f'{platform} {UA_TOP}' if platform else UA_TOP

    def _sticker_header(self, data: YotoCardData, card_type: YotoCardType) -> str | None:
        if data.sticker_header is not None:
            return self._normalize_display_text(data.sticker_header)
        if card_type == YotoCardType.FREE_GAME:
            return GIVEAWAY_LABEL
        if card_type == YotoCardType.DISCOUNT:
            platform = str(data.platform or '').strip().upper()
            if 'STEAM' in platform:
                return STEAM_SALE_LABEL
            return 'SALE'
        if card_type == YotoCardType.FESTIVAL:
            return EVENT_LABEL
        return UA_TOP

    def _sticker_text(self, data: YotoCardData, card_type: YotoCardType) -> str:
        if data.sticker_text:
            return data.sticker_text
        if card_type == YotoCardType.FREE_GAME:
            return UA_FREE
        if card_type == YotoCardType.DISCOUNT:
            return UA_DISCOUNT
        if card_type == YotoCardType.FESTIVAL:
            return UA_EVENT
        return UA_TOP

    def _badge_copy(self, data: YotoCardData, diagnostics: YotoCardDiagnostics, card_type: YotoCardType) -> tuple[str, str | None]:
        if card_type == YotoCardType.DISCOUNT:
            footer_text = (data.deadline or '').strip() or SALE_ENDS_SOON_LABEL
            main_text = diagnostics.sticker_text
            return main_text, footer_text
        if card_type == YotoCardType.FESTIVAL:
            return diagnostics.sticker_text, None
        return diagnostics.sticker_text, None

    def _badge_points(self, card_type: YotoCardType) -> tuple[list[tuple[int, int]], list[tuple[int, int]], list[tuple[int, int]]]:
        if card_type == YotoCardType.DISCOUNT:
            base = [(22, 22), (346, 22), (430, 60), (394, 170), (72, 170), (12, 110)]
            header = [(48, 38), (330, 38), (370, 60), (80, 60)]
            fold = [(354, 22), (430, 60), (394, 76), (326, 30)]
            return base, header, fold
        if card_type == YotoCardType.FESTIVAL:
            base = [(30, 18), (350, 18), (420, 58), (392, 154), (66, 154), (16, 102)]
            header = [(48, 36), (334, 36), (364, 58), (76, 58)]
            fold = [(356, 18), (420, 58), (394, 70), (328, 28)]
            return base, header, fold
        base = [(28, 18), (356, 18), (418, 62), (386, 156), (62, 156), (14, 100)]
        header = [(46, 36), (336, 36), (364, 58), (74, 58)]
        fold = [(360, 18), (418, 62), (388, 72), (332, 28)]
        return base, header, fold

    def _palette(self, card_type: YotoCardType) -> YotoCardPalette:
        if card_type == YotoCardType.DISCOUNT:
            return YotoCardPalette(
                accent=DISCOUNT_ORANGE,
                accent_secondary='#ffb35a',
                glow=DISCOUNT_GLOW,
                panel_top='#130c09',
                panel_bottom='#141018',
                deadline_fill='#4b2616',
                deadline_border=DISCOUNT_ORANGE,
                deadline_text='#ffd7bf',
                badge_body=(251, 247, 244, 255),
                badge_header_fill=DISCOUNT_ORANGE,
                badge_kicker_fill='#34170d',
                badge_text_fill='#171114',
                badge_fold_fill=(255, 210, 196, 144),
                brand_fill='#f2c97a',
                meta_accent='#ffe3d1',
                panel_kicker=PANEL_KICKERS['DISCOUNT'],
            )
        if card_type == YotoCardType.FESTIVAL:
            return YotoCardPalette(
                accent=EVENT_CYAN,
                accent_secondary=EVENT_PURPLE,
                glow=EVENT_GLOW,
                panel_top='#07101b',
                panel_bottom='#101226',
                deadline_fill='#153149',
                deadline_border=EVENT_CYAN,
                deadline_text='#c4f5ff',
                badge_body=(246, 250, 255, 255),
                badge_header_fill=EVENT_CYAN,
                badge_kicker_fill='#071827',
                badge_text_fill='#121824',
                badge_fold_fill=(214, 236, 255, 136),
                brand_fill='#86e8ff',
                meta_accent='#dbe8ff',
                panel_kicker=PANEL_KICKERS['FESTIVAL'],
            )
        if card_type == YotoCardType.TOP_LIST:
            return YotoCardPalette(
                accent='#f0c670',
                accent_secondary='#9f7a24',
                glow='#f6c978',
                panel_top=PANEL_TOP,
                panel_bottom=PANEL_BOTTOM,
                deadline_fill='#4a3a14',
                deadline_border='#f0c670',
                deadline_text='#fff1bf',
                badge_body=(248, 246, 241, 255),
                badge_header_fill='#f0c670',
                badge_kicker_fill='#2f2508',
                badge_text_fill='#121212',
                badge_fold_fill=(255, 242, 190, 128),
                brand_fill='#f0c670',
                meta_accent='#f3dfb0',
                panel_kicker=PANEL_KICKERS['TOP_LIST'],
            )
        return YotoCardPalette(
            accent=PRIMARY_GREEN,
            accent_secondary='#58f4b2',
            glow=ACCENT_GLOW,
            panel_top='#061016',
            panel_bottom='#09141c',
            deadline_fill='#0c3f2c',
            deadline_border=PRIMARY_GREEN,
            deadline_text='#9fffc9',
            badge_body=(250, 252, 250, 255),
            badge_header_fill=PRIMARY_GREEN,
            badge_kicker_fill='#071c11',
            badge_text_fill='#0e141d',
            badge_fold_fill=(255, 255, 255, 120),
            brand_fill=PRIMARY_GREEN,
            meta_accent='#dcefe4',
            panel_kicker=PANEL_KICKERS['FREE_GAME'],
        )

    def _smart_cover(
        self,
        artwork: Image.Image,
        target_size: tuple[int, int],
        *,
        zoom_levels: tuple[float, ...],
        candidate_rows: tuple[float, ...],
        candidate_cols: tuple[float, ...] | None = None,
        bias_x: float = 0.50,
        bias_y: float = 0.45,
        return_crop_box: bool = False,
    ) -> Image.Image | tuple[Image.Image, tuple[int, int, int, int]]:
        crop_box = self._best_crop_box(
            artwork,
            target_size,
            zoom_levels=zoom_levels,
            candidate_rows=candidate_rows,
            candidate_cols=candidate_cols,
            bias_x=bias_x,
            bias_y=bias_y,
        )
        covered = artwork.crop(crop_box).resize(target_size, Image.Resampling.LANCZOS)
        if return_crop_box:
            return covered, crop_box
        return covered

    def _best_crop_box(
        self,
        artwork: Image.Image,
        target_size: tuple[int, int],
        *,
        zoom_levels: tuple[float, ...],
        candidate_rows: tuple[float, ...],
        candidate_cols: tuple[float, ...] | None = None,
        bias_x: float = 0.50,
        bias_y: float = 0.45,
    ) -> tuple[int, int, int, int]:
        img_w, img_h = artwork.size
        target_w, target_h = target_size
        aspect = target_w / target_h
        if img_w / img_h >= aspect:
            max_crop_h = img_h
            max_crop_w = int(max_crop_h * aspect)
        else:
            max_crop_w = img_w
            max_crop_h = int(max_crop_w / aspect)

        preview_w = min(360, img_w)
        preview_h = max(1, int(round(preview_w * img_h / max(img_w, 1))))
        preview = artwork.convert('RGB').resize((preview_w, preview_h), Image.Resampling.BILINEAR)
        preview_gray = preview.convert('L')
        preview_edges = preview_gray.filter(ImageFilter.FIND_EDGES)
        preview_sat = preview.convert('HSV').getchannel('S')
        resolved_cols = candidate_cols or self._biased_cover_positions(bias_x, step=0.08, lower=0.28, upper=0.72)

        best_score = float('-inf')
        best_box = (0, 0, max_crop_w, max_crop_h)
        for zoom in zoom_levels:
            crop_w = max(1, int(max_crop_w * zoom))
            crop_h = max(1, int(max_crop_h * zoom))
            for col in resolved_cols:
                for row in candidate_rows:
                    left = int(round(col * img_w - crop_w / 2))
                    top = int(round(row * img_h - crop_h / 2))
                    left = max(0, min(left, img_w - crop_w))
                    top = max(0, min(top, img_h - crop_h))
                    box = (left, top, left + crop_w, top + crop_h)
                    score = self._crop_interest_score(
                        preview_edges,
                        preview_gray,
                        preview_sat,
                        box,
                        artwork.size,
                        zoom,
                        bias_x=bias_x,
                        bias_y=bias_y,
                    )
                    if score > best_score:
                        best_score = score
                        best_box = box
        return best_box

    def _crop_interest_score(
        self,
        preview_edges: Image.Image,
        preview_gray: Image.Image,
        preview_sat: Image.Image,
        crop_box: tuple[int, int, int, int],
        source_size: tuple[int, int],
        zoom: float,
        *,
        bias_x: float = 0.50,
        bias_y: float = 0.45,
    ) -> float:
        src_w, src_h = source_size
        left, top, right, bottom = crop_box
        scale_x = preview_edges.width / max(src_w, 1)
        scale_y = preview_edges.height / max(src_h, 1)
        preview_box = (
            int(left * scale_x),
            int(top * scale_y),
            max(int(right * scale_x), int(left * scale_x) + 1),
            max(int(bottom * scale_y), int(top * scale_y) + 1),
        )
        edges_crop = preview_edges.crop(preview_box)
        gray_crop = preview_gray.crop(preview_box)
        sat_crop = preview_sat.crop(preview_box)
        edge_mean = ImageStat.Stat(edges_crop).mean[0]
        variance = ImageStat.Stat(gray_crop).var[0]
        saturation = ImageStat.Stat(sat_crop).mean[0]
        upper_crop = edges_crop.crop((0, 0, edges_crop.width, max(1, int(edges_crop.height * 0.62))))
        upper_edge = ImageStat.Stat(upper_crop).mean[0]

        focus_left = int(edges_crop.width * 0.18)
        focus_top = int(edges_crop.height * 0.16)
        focus_right = max(focus_left + 1, int(edges_crop.width * 0.82))
        focus_bottom = max(focus_top + 1, int(edges_crop.height * 0.84))
        focus_crop = edges_crop.crop((focus_left, focus_top, focus_right, focus_bottom))
        focus_edge = ImageStat.Stat(focus_crop).mean[0]

        band_h = max(1, int(edges_crop.height * 0.12))
        band_w = max(1, int(edges_crop.width * 0.12))
        edge_bands = [
            edges_crop.crop((0, 0, edges_crop.width, band_h)),
            edges_crop.crop((0, edges_crop.height - band_h, edges_crop.width, edges_crop.height)),
            edges_crop.crop((0, 0, band_w, edges_crop.height)),
            edges_crop.crop((edges_crop.width - band_w, 0, edges_crop.width, edges_crop.height)),
        ]
        band_edge = sum(ImageStat.Stat(region).mean[0] for region in edge_bands) / len(edge_bands)

        preview_center_x = (preview_box[0] + preview_box[2]) / 2
        preview_center_y = (preview_box[1] + preview_box[3]) / 2
        preferred_x = preview_edges.width * max(0.0, min(1.0, bias_x))
        preferred_y = preview_edges.height * max(0.0, min(1.0, bias_y))
        offset_x = abs(preview_center_x - preferred_x) / max(preview_edges.width / 2, 1)
        offset_y = abs(preview_center_y - preferred_y) / max(preview_edges.height / 2, 1)
        center_bonus = max(0.0, 1.0 - (offset_x * 0.86 + offset_y * 1.12)) * 18
        edge_penalty = max(0.0, band_edge - focus_edge * 0.92)
        zoom_bonus = (1.0 - zoom) * 10
        return edge_mean * 1.82 + upper_edge * 0.74 + focus_edge * 0.64 + variance * 0.34 + saturation * 0.14 + center_bonus - edge_penalty * 0.78 + zoom_bonus

    def _resolve_asset_path(self, asset_path: str | Path | None) -> Path | None:
        if isinstance(asset_path, Path):
            return asset_path if asset_path.is_absolute() else (self.repo_root / asset_path).resolve()
        if isinstance(asset_path, str) and asset_path.strip():
            candidate = Path(asset_path)
            return candidate if candidate.is_absolute() else (self.repo_root / candidate).resolve()
        return None

    def _load_optional_asset(self, asset_path: str | Path | None) -> tuple[Image.Image | None, str | None]:
        path = self._resolve_asset_path(asset_path)
        if path is None or not path.exists():
            return None, None
        cache_key = str(path.resolve())
        cached = self._artwork_cache.get(cache_key)
        if cached is not None:
            return cached.copy(), cache_key
        try:
            image = Image.open(path).convert('RGB')
        except OSError:
            return None, None
        self._artwork_cache[cache_key] = image
        return image.copy(), cache_key

    def _sticker_line_candidates(self, text: str, max_lines: int) -> list[list[str]]:
        if max_lines < 2:
            return []
        explicit_lines = [re.sub(r'\s+', ' ', line).strip() for line in text.splitlines() if line.strip()]
        candidates: list[list[str]] = []
        if len(explicit_lines) > 1:
            candidates.append(explicit_lines[:max_lines])

        normalized = re.sub(r'\s+', ' ', text.replace('\n', ' ')).strip()
        words = normalized.split()
        if len(words) < 2:
            return candidates

        split_candidates: list[list[str]] = []
        for index in range(1, len(words)):
            left = ' '.join(words[:index])
            right = ' '.join(words[index:])
            if left and right:
                split_candidates.append([left, right])
        split_candidates.sort(key=lambda pair: (abs(len(pair[0]) - len(pair[1])), max(len(pair[0]), len(pair[1]))))

        for candidate in split_candidates:
            if candidate not in candidates:
                candidates.append(candidate)
        return candidates


    def _fit_text_block(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        *,
        candidates: tuple[str, ...],
        font_sizes: Sequence[int],
        max_width: int,
        max_lines: int,
        prefer_multiline: bool,
        diagnostics: YotoCardDiagnostics | None = None,
        layer: str | None = None,
        tracking_em: float = 0.0,
    ) -> YotoStickerTextLayout:
        normalized = re.sub(r'\s+', ' ', text.replace('\n', ' ')).strip()
        sizes = [int(size) for size in font_sizes]
        if not sizes:
            sizes = [22]
        if not normalized:
            font = self._load_font_for_text(sizes[-1], candidates, normalized, diagnostics=diagnostics, layer=layer)
            bbox = draw.textbbox((0, 0), 'Ag', font=font)
            return YotoStickerTextLayout(lines=[''], font=font, line_height=max(1, bbox[3] - bbox[1]))

        explicit_candidates = self._sticker_line_candidates(text, max_lines)
        for size in sizes:
            font = self._load_font_for_text(size, candidates, normalized, diagnostics=diagnostics, layer=layer)
            letter_spacing = self._letter_spacing_px(font, tracking_em)
            candidate_sets: list[list[str]] = []
            if max_lines == 1:
                candidate_sets.append([normalized])
            else:
                if prefer_multiline and ' ' in normalized:
                    candidate_sets.extend(explicit_candidates)
                if [normalized] not in candidate_sets:
                    candidate_sets.append([normalized])
                if not prefer_multiline:
                    for candidate in explicit_candidates:
                        if candidate not in candidate_sets:
                            candidate_sets.append(candidate)
                should_wrap = (' ' in normalized) or ('\n' in text)
                if should_wrap:
                    wrapped, clipped = self._wrap_text(draw, normalized, font, max_width=max_width, max_lines=max_lines, tracking_em=tracking_em)
                    if not clipped and wrapped and wrapped not in candidate_sets:
                        candidate_sets.append(wrapped)
                if prefer_multiline and ' ' not in normalized:
                    for candidate in explicit_candidates:
                        if candidate not in candidate_sets:
                            candidate_sets.append(candidate)

            for lines in candidate_sets:
                if not lines or len(lines) > max_lines:
                    continue
                if all(self._textlength(draw, line, font, letter_spacing=letter_spacing) <= max_width for line in lines):
                    bbox = draw.textbbox((0, 0), 'Ag', font=font)
                    return YotoStickerTextLayout(lines=lines, font=font, line_height=max(1, bbox[3] - bbox[1]))

        smallest = self._load_font_for_text(sizes[-1], candidates, normalized, diagnostics=diagnostics, layer=layer)
        letter_spacing = self._letter_spacing_px(smallest, tracking_em)
        if max_lines == 1:
            fitted_lines = [self._ellipsize(draw, normalized, smallest, max_width, letter_spacing=letter_spacing)]
        else:
            fitted_lines, _ = self._wrap_text(draw, normalized, smallest, max_width=max_width, max_lines=max_lines, tracking_em=tracking_em)
            if not fitted_lines:
                fitted_lines = [self._ellipsize(draw, normalized, smallest, max_width, letter_spacing=letter_spacing)]
            fitted_lines = fitted_lines[:max_lines]
            fitted_lines = [
                self._ellipsize(draw, line, smallest, max_width, letter_spacing=letter_spacing)
                if self._textlength(draw, line, smallest, letter_spacing=letter_spacing) > max_width
                else line
                for line in fitted_lines
            ]
        bbox = draw.textbbox((0, 0), 'Ag', font=smallest)
        return YotoStickerTextLayout(lines=fitted_lines, font=smallest, line_height=max(1, bbox[3] - bbox[1]))

    def _build_gameplay_thumbnail(
        self,
        artwork: Image.Image,
        thumb_size: tuple[int, int],
        palette: YotoCardPalette,
        angle: float,
        *,
        is_primary: bool,
    ) -> Image.Image:
        frame_margin = 16
        tile = Image.new('RGBA', (thumb_size[0] + frame_margin * 2, thumb_size[1] + frame_margin * 2), (0, 0, 0, 0))

        shadow = Image.new('RGBA', tile.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_box = (frame_margin + 2, frame_margin + 4, frame_margin + 2 + thumb_size[0], frame_margin + 4 + thumb_size[1])
        shadow_draw.rounded_rectangle(shadow_box, radius=20, fill=(0, 0, 0, 92 if is_primary else 76))
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=7 if is_primary else 6))
        tile = Image.alpha_composite(tile, shadow)

        content = self._smart_cover(
            artwork,
            thumb_size,
            zoom_levels=(1.0, 0.98, 0.94),
            candidate_rows=(0.36, 0.46, 0.54),
        ).convert('RGBA')
        mask = Image.new('L', thumb_size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, thumb_size[0] - 1, thumb_size[1] - 1), radius=16, fill=255)

        frame = Image.new('RGBA', thumb_size, (0, 0, 0, 0))
        frame.paste(content, (0, 0), mask)

        tone = Image.new('RGBA', thumb_size, (0, 0, 0, 0))
        tone_draw = ImageDraw.Draw(tone)
        for row in range(thumb_size[1]):
            alpha = int(34 * (row / max(thumb_size[1] - 1, 1)))
            tone_draw.line((0, row, thumb_size[0], row), fill=(0, 0, 0, alpha))
        frame = Image.alpha_composite(frame, tone)

        frame_overlay = Image.new('RGBA', thumb_size, (0, 0, 0, 0))
        frame_draw = ImageDraw.Draw(frame_overlay)
        outer_color = rgba(palette.accent, 108 if is_primary else 84)
        inner_color = rgba(palette.accent_secondary, 46 if is_primary else 34)
        frame_draw.rounded_rectangle((0, 0, thumb_size[0] - 1, thumb_size[1] - 1), radius=16, outline=outer_color, width=1)
        frame_draw.rounded_rectangle((10, 10, thumb_size[0] - 11, thumb_size[1] - 11), radius=12, outline=inner_color, width=1)
        frame_draw.line((18, 14, thumb_size[0] - 20, 14), fill=rgba(palette.accent, 76 if is_primary else 54), width=1)
        gloss = Image.new('RGBA', thumb_size, (0, 0, 0, 0))
        gloss_draw = ImageDraw.Draw(gloss)
        gloss_height = max(16, int(thumb_size[1] * 0.22))
        for row in range(gloss_height):
            alpha = int((22 if is_primary else 14) * (1.0 - row / max(gloss_height, 1)))
            gloss_draw.line((0, row, thumb_size[0], row), fill=(255, 255, 255, alpha))
        frame_overlay = Image.alpha_composite(frame_overlay, gloss)
        frame = Image.alpha_composite(frame, frame_overlay)
        tile.paste(frame, (frame_margin, frame_margin), frame)

        if is_primary:
            glow = Image.new('RGBA', tile.size, (0, 0, 0, 0))
            glow_draw = ImageDraw.Draw(glow)
            glow_draw.rounded_rectangle((frame_margin, frame_margin, frame_margin + thumb_size[0], frame_margin + thumb_size[1]), radius=20, outline=rgba(palette.accent, 28), width=1)
            glow = glow.filter(ImageFilter.GaussianBlur(radius=4))
            tile = Image.alpha_composite(glow, tile)

        return tile.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)


    def _resolve_title_layout(
        self,
        title: str,
        card_type: YotoCardType,
        diagnostics: YotoCardDiagnostics | None = None,
        composition_profile: Mapping[str, Any] | None = None,
    ) -> YotoTitleLayout:
        probe = ImageDraw.Draw(Image.new('RGB', (1, 1), DARK_BG))
        title_profile = dict((composition_profile or {}).get('title') or {})
        role_spec = self._typography_role('title')
        normalized_title = self._normalize_display_text(title)
        if title_profile:
            single_line_configs = tuple(tuple(config) for config in title_profile.get('single_configs', ((72, 940, 552, 64), (68, 920, 550, 60), (64, 900, 548, 58))))
            two_line_configs = tuple(tuple(config) for config in title_profile.get('two_line_configs', ((60, 920, 504, 56), (56, 920, 510, 52), (52, 920, 516, 48), (48, 910, 520, 44))))
            probe_size = int(single_line_configs[0][0])
            probe_width = int(single_line_configs[0][1])
            probe_font = self._load_font_for_text(probe_size, role_spec.candidates, normalized_title, diagnostics=diagnostics, layer='title')
            prefer_two_lines = bool(title_profile.get('prefer_two_lines')) or len(normalized_title) > int(title_profile.get('two_line_threshold', 34)) or self._textlength(probe, normalized_title, probe_font, letter_spacing=self._letter_spacing_px(probe_font, role_spec.tracking_em)) > probe_width
            chosen_x = int(title_profile.get('x', SAFE_LEFT + 20))
            meta_y_single = int(title_profile.get('meta_y_single', 624))
            meta_y_two = int(title_profile.get('meta_y_two', 648))
        else:
            probe_font = self._load_font_for_text(72, role_spec.candidates, normalized_title, diagnostics=diagnostics, layer='title')
            prefer_two_lines = len(normalized_title) > 34 or self._textlength(probe, normalized_title, probe_font, letter_spacing=self._letter_spacing_px(probe_font, role_spec.tracking_em)) > 920
            single_line_configs = ((72, 940, 552, 64), (68, 920, 550, 60), (64, 900, 548, 58))
            two_line_configs = ((60, 920, 504, 56), (56, 920, 510, 52), (52, 920, 516, 48), (48, 910, 520, 44))
            chosen_x = SAFE_LEFT + 20
            meta_y_single = 624
            meta_y_two = 648

        configs: list[tuple[int, int, int, int, int]] = []
        if prefer_two_lines:
            configs.extend((int(size), int(width), int(y), int(line_height), 2) for size, width, y, line_height in two_line_configs)
        else:
            configs.extend((int(size), int(width), int(y), int(line_height), 1) for size, width, y, line_height in single_line_configs)
            configs.extend((int(size), int(width), int(y), int(line_height), 2) for size, width, y, line_height in two_line_configs)

        chosen_lines = [normalized_title]
        chosen_font = self._load_font_for_text(64, role_spec.candidates, normalized_title, diagnostics=diagnostics, layer='title')
        chosen_mode = 'single_line'
        chosen_y = 548
        chosen_line_height = 58

        for size, width, y, line_height, max_lines in configs:
            font = self._load_font_for_text(size, role_spec.candidates, normalized_title, diagnostics=diagnostics, layer='title')
            lines, clipped = self._wrap_text(probe, normalized_title, font, max_width=width, max_lines=max_lines, tracking_em=role_spec.tracking_em)
            chosen_lines = lines
            chosen_font = font
            chosen_mode = 'two_line' if len(lines) > 1 else 'single_line'
            chosen_y = y
            chosen_line_height = line_height
            if not clipped:
                break

        meta_y = meta_y_two if chosen_mode == 'two_line' else meta_y_single
        return YotoTitleLayout(
            lines=chosen_lines,
            font=chosen_font,
            x=chosen_x,
            y=chosen_y,
            line_height=chosen_line_height,
            meta_y=meta_y,
            mode=chosen_mode,
        )

    def _grain_overlay(self) -> Image.Image:
        cached = self._grain_cache.get(CARD_SIZE)
        if cached is not None:
            return cached.copy()
        tile_w, tile_h = 160, 90
        noise = Image.new('L', (tile_w, tile_h), 128)
        pixels = noise.load()
        for y in range(tile_h):
            for x in range(tile_w):
                value = 124 + (((x * 17) + (y * 29) + ((x * y) % 19)) % 20) - 10
                pixels[x, y] = max(110, min(144, value))
        noise = noise.resize(CARD_SIZE, Image.Resampling.BICUBIC)
        alpha = Image.new('L', CARD_SIZE, 10)
        grain = Image.merge('RGBA', (noise, noise, noise, alpha))
        self._grain_cache[CARD_SIZE] = grain
        return grain.copy()

    def _scanline_overlay(self) -> Image.Image:
        cached = self._scanline_cache.get(CARD_SIZE)
        if cached is not None:
            return cached.copy()
        overlay = Image.new('RGBA', CARD_SIZE, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        for y in range(0, CARD_SIZE[1], 6):
            draw.line((0, y, CARD_SIZE[0], y), fill=(255, 255, 255, 8), width=1)
        self._scanline_cache[CARD_SIZE] = overlay
        return overlay.copy()

    def _vignette_overlay(self) -> Image.Image:
        cached = self._vignette_cache.get(CARD_SIZE)
        if cached is not None:
            return cached.copy()
        overlay = Image.new('RGBA', CARD_SIZE, (0, 0, 0, 0))
        mask = Image.new('L', CARD_SIZE, 164)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((110, 35, CARD_SIZE[0] - 110, CARD_SIZE[1] - 10), fill=0)
        mask = mask.filter(ImageFilter.GaussianBlur(radius=86))
        overlay.putalpha(mask)
        self._vignette_cache[CARD_SIZE] = overlay
        return overlay.copy()

    def _fill_polygon_with_vertical_gradient(
        self,
        canvas: Image.Image,
        points: list[tuple[int, int]],
        top_color: str,
        bottom_color: str,
        *,
        alpha: int,
    ) -> Image.Image:
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        gradient = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(gradient)
        top_rgb = ImageColor.getrgb(top_color)
        bottom_rgb = ImageColor.getrgb(bottom_color)
        height = max(y1 - y0, 1)
        for offset in range(height + 1):
            ratio = offset / max(height, 1)
            color = tuple(int(top_rgb[idx] + (bottom_rgb[idx] - top_rgb[idx]) * ratio) for idx in range(3)) + (alpha,)
            draw.line((x0, y0 + offset, x1, y0 + offset), fill=color)
        mask = Image.new('L', canvas.size, 0)
        ImageDraw.Draw(mask).polygon(points, fill=255)
        gradient.putalpha(ImageChops.multiply(gradient.getchannel('A'), mask))
        return Image.alpha_composite(canvas.convert('RGBA'), gradient)

    @staticmethod
    def _placeholder_initials(title: str) -> str:
        words = [''.join(char for char in part if char.isalnum()) for part in str(title or '').split()]
        initials = ''.join(part[0] for part in words if part)
        if len(initials) >= 2:
            return initials[:2].upper()
        compact = ''.join(char for char in str(title or '') if char.isalnum())
        if len(compact) >= 2:
            return compact[:2].upper()
        if compact:
            return compact[0].upper()
        return 'YT'


    def _resolve_placeholder_title_layout(
        self,
        draw: ImageDraw.ImageDraw,
        title: str,
        *,
        panel_width: int,
        panel_height: int,
    ) -> tuple[YotoStickerTextLayout, dict[str, Any]]:
        normalized_title = self._normalize_display_text(title)
        role_spec = self._typography_role('placeholder_title')
        probable_long_title = len(normalized_title) >= 18 or len(normalized_title.split()) >= 4
        configs: list[dict[str, Any]] = []
        if probable_long_title:
            configs.append(
                {
                    'mode': 'compact',
                    'candidates': role_spec.candidates,
                    'font_sizes': (70, 64, 58, 52, 48, 44, 40),
                    'max_lines': 2,
                    'max_width': panel_width - 112,
                    'line_gap': 4,
                    'title_y_offset': 84,
                    'text_alpha': 194,
                    'shadow_alpha': 72,
                    'badge_gap': 18,
                }
            )
        configs.append(
            {
                'mode': 'standard',
                'candidates': role_spec.candidates,
                'font_sizes': (86, 78, 70, 62, 56, 50),
                'max_lines': 2,
                'max_width': panel_width - 84,
                'line_gap': 6,
                'title_y_offset': 78,
                'text_alpha': 222,
                'shadow_alpha': 94,
                'badge_gap': 14,
            }
        )
        configs.append(
            {
                'mode': 'tight',
                'candidates': ROLE_DISPLAY_SEMIBOLD_FONT_CANDIDATES,
                'font_sizes': (62, 56, 50, 46, 42, 38),
                'max_lines': 3,
                'max_width': panel_width - 124,
                'line_gap': 4,
                'title_y_offset': 86,
                'text_alpha': 186,
                'shadow_alpha': 68,
                'badge_gap': 16,
            }
        )
        title_budget = max(72, panel_height - 162)
        best_layout: YotoStickerTextLayout | None = None
        best_style: dict[str, Any] | None = None

        for config in configs:
            max_width = max(220, int(config['max_width']))
            max_lines = int(config['max_lines'])
            for size in config['font_sizes']:
                font = self._load_font_for_text(int(size), tuple(config['candidates']), normalized_title, layer='placeholder_title')
                lines, clipped = self._wrap_text(draw, normalized_title, font, max_width=max_width, max_lines=max_lines, tracking_em=role_spec.tracking_em)
                if not lines:
                    lines = ['']
                bbox = draw.textbbox((0, 0), 'Ag', font=font)
                line_height = max(1, bbox[3] - bbox[1])
                total_height = len(lines) * line_height + max(0, len(lines) - 1) * int(config['line_gap'])
                layout = YotoStickerTextLayout(lines=lines, font=font, line_height=line_height)
                if best_layout is None:
                    best_layout = layout
                    best_style = dict(config)
                if not clipped and total_height <= title_budget:
                    style = dict(config)
                    style['total_height'] = total_height
                    style['max_width'] = max_width
                    return layout, style

        assert best_layout is not None and best_style is not None
        best_style = dict(best_style)
        best_style['total_height'] = len(best_layout.lines) * best_layout.line_height + max(0, len(best_layout.lines) - 1) * int(best_style['line_gap'])
        best_style['max_width'] = max(220, int(best_style['max_width']))
        return best_layout, best_style

    def _load_named_font(self, name: str, size: int) -> ImageFont.FreeTypeFont | None:
        key = (name, size)
        if key in self._font_file_cache:
            return self._font_file_cache[key]
        path = self.font_dir / name
        if not path.exists():
            self._font_file_cache[key] = None
            return None
        try:
            font = ImageFont.truetype(str(path), size=size)
        except OSError:
            self._font_file_cache[key] = None
            return None
        self._font_file_cache[key] = font
        return font

    def _load_font(self, size: int, candidates: tuple[str, ...]) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        key = ('|'.join(candidates), size)
        cached = self._font_cache.get(key)
        if cached is not None:
            return cached
        for name in candidates:
            font = self._load_named_font(name, size)
            if font is not None:
                self._font_cache[key] = font
                return font
        font = ImageFont.load_default()
        self._font_cache[key] = font
        return font

    def _load_font_for_text(
        self,
        size: int,
        candidates: tuple[str, ...],
        text: str | None,
        *,
        diagnostics: YotoCardDiagnostics | None = None,
        layer: str | None = None,
    ) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        requested = str(text or '')
        needs_cyrillic = contains_cyrillic(requested)
        glyph_blocked = False
        first_available_name: str | None = None
        chosen_font: ImageFont.FreeTypeFont | ImageFont.ImageFont | None = None
        chosen_name = 'PIL-default'

        if needs_cyrillic:
            for name in candidates:
                font = self._load_named_font(name, size)
                if font is None:
                    continue
                if first_available_name is None:
                    first_available_name = name
                if self._font_supports_text(font, requested):
                    chosen_font = font
                    chosen_name = name
                    break
                if first_available_name == name:
                    glyph_blocked = True
        if chosen_font is None:
            chosen_font = self._load_font(size, candidates)
            for name in candidates:
                font = self._load_named_font(name, size)
                if font is chosen_font:
                    chosen_name = name
                    break
        fallback_used = bool(glyph_blocked and first_available_name and chosen_name != first_available_name)

        self._record_font_selection(
            diagnostics,
            layer,
            requested,
            chosen_name,
            fallback_used,
            needs_cyrillic,
        )
        return chosen_font

    @staticmethod
    def _font_supports_text(font: ImageFont.FreeTypeFont | ImageFont.ImageFont, text: str) -> bool:
        if not text:
            return True
        for char in {item for item in text if contains_cyrillic(item)}:
            try:
                bbox = font.getbbox(char)
                mask = font.getmask(char)
            except Exception:
                return False
            if bbox is None or mask.getbbox() is None:
                return False
        return True

    @staticmethod
    def _record_font_selection(
        diagnostics: YotoCardDiagnostics | None,
        layer: str | None,
        text: str,
        font_family: str,
        fallback_used: bool,
        cyrillic_text: bool,
    ) -> None:
        if diagnostics is None or not layer:
            return
        diagnostics.font_selection[layer] = {
            'font_family': font_family,
            'fallback_used': fallback_used,
            'cyrillic_text': cyrillic_text,
        }
        if fallback_used:
            diagnostics.glyph_fallback_used = True

    def _typography_role(self, role: str) -> YotoTypographyRole:
        return TYPOGRAPHY_ROLES.get(role, TYPOGRAPHY_ROLES['meta_secondary'])

    def _role_text(self, text: str | None, role: str) -> str:
        normalized = self._normalize_display_text(str(text or ''))
        role_spec = self._typography_role(role)
        if role_spec.force_uppercase:
            return normalized.upper()
        return normalized

    def _font_pixel_size(self, font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> float:
        size = getattr(font, 'size', None)
        if isinstance(size, (int, float)) and size > 0:
            return float(size)
        try:
            bbox = font.getbbox('Mg')
        except Exception:
            return 16.0
        return float(max(1, bbox[3] - bbox[1]))

    def _letter_spacing_px(
        self,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        tracking_em: float,
    ) -> int:
        if tracking_em == 0.0:
            return 0
        spacing = int(round(self._font_pixel_size(font) * tracking_em))
        return max(-2, min(6, spacing))

    def _textlength(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        *,
        letter_spacing: int = 0,
    ) -> float:
        if not text:
            return 0.0
        if letter_spacing == 0 or len(text) <= 1:
            return float(draw.textlength(text, font=font))
        total = 0.0
        for index, char in enumerate(text):
            total += float(draw.textlength(char, font=font))
            if index < len(text) - 1:
                total += letter_spacing
        return total

    def _draw_text_line(
        self,
        draw: ImageDraw.ImageDraw,
        position: tuple[int, int],
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        fill: str | tuple[int, int, int] | tuple[int, int, int, int],
        *,
        letter_spacing: int = 0,
        stroke_width: int = 0,
        stroke_fill: str | tuple[int, int, int] | tuple[int, int, int, int] | None = None,
    ) -> None:
        x, y = float(position[0]), int(position[1])
        if letter_spacing == 0 or len(text) <= 1:
            draw.text((int(round(x)), y), text, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill)
            return
        for index, char in enumerate(text):
            if char != ' ':
                draw.text((int(round(x)), y), char, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=stroke_fill)
            x += float(draw.textlength(char, font=font))
            if index < len(text) - 1:
                x += letter_spacing

    def _textbbox(
        self,
        draw: ImageDraw.ImageDraw,
        position: tuple[int, int],
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        *,
        letter_spacing: int = 0,
        stroke_width: int = 0,
    ) -> tuple[int, int, int, int]:
        x, y = float(position[0]), int(position[1])
        if not text:
            return (int(round(x)), y, int(round(x)), y)
        if letter_spacing == 0 or len(text) <= 1:
            return tuple(int(value) for value in draw.textbbox((int(round(x)), y), text, font=font, stroke_width=stroke_width))

        left: int | None = None
        top: int | None = None
        right: int | None = None
        bottom: int | None = None
        for index, char in enumerate(text):
            char_x = int(round(x))
            if char != ' ':
                char_bbox = draw.textbbox((char_x, y), char, font=font, stroke_width=stroke_width)
                if left is None:
                    left, top, right, bottom = (int(value) for value in char_bbox)
                else:
                    left = min(left, int(char_bbox[0]))
                    top = min(top, int(char_bbox[1]))
                    right = max(right, int(char_bbox[2]))
                    bottom = max(bottom, int(char_bbox[3]))
            x += float(draw.textlength(char, font=font))
            if index < len(text) - 1:
                x += letter_spacing
        if left is None or top is None or right is None or bottom is None:
            end_x = int(round(position[0] + self._textlength(draw, text, font, letter_spacing=letter_spacing)))
            return (int(round(position[0])), y, end_x, y)
        return (left, top, right, bottom)

    def _draw_role_text(
        self,
        draw: ImageDraw.ImageDraw,
        position: tuple[int, int],
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        fill: str | tuple[int, int, int] | tuple[int, int, int, int],
        *,
        role: str,
        tracking_em: float | None = None,
        shadow_layers: Sequence[tuple[int, int, int]] | None = None,
        stroke_width: int | None = None,
        stroke_fill: str | tuple[int, int, int] | tuple[int, int, int, int] | None = None,
    ) -> str:
        role_spec = self._typography_role(role)
        display_text = self._role_text(text, role)
        letter_spacing = self._letter_spacing_px(font, role_spec.tracking_em if tracking_em is None else tracking_em)
        resolved_shadow_layers = tuple(shadow_layers or role_spec.shadow_layers)
        resolved_stroke_width = role_spec.stroke_width if stroke_width is None else int(stroke_width)
        resolved_stroke_fill = role_spec.stroke_fill if stroke_fill is None else stroke_fill
        for dx, dy, alpha in resolved_shadow_layers:
            self._draw_text_line(
                draw,
                (position[0] + int(dx), position[1] + int(dy)),
                display_text,
                font,
                (0, 0, 0, int(alpha)),
                letter_spacing=letter_spacing,
            )
        self._draw_text_line(
            draw,
            position,
            display_text,
            font,
            fill,
            letter_spacing=letter_spacing,
            stroke_width=resolved_stroke_width,
            stroke_fill=resolved_stroke_fill,
        )
        return display_text


    def _wrap_text(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        *,
        max_width: int,
        max_lines: int,
        tracking_em: float = 0.0,
    ) -> tuple[list[str], bool]:
        words = text.split()
        if not words:
            return [''], False
        letter_spacing = self._letter_spacing_px(font, tracking_em)
        lines: list[str] = []
        current = ''
        for raw_word in words:
            word = raw_word if self._textlength(draw, raw_word, font, letter_spacing=letter_spacing) <= max_width else self._ellipsize(draw, raw_word, font, max_width, letter_spacing=letter_spacing)
            proposal = word if not current else f'{current} {word}'
            if self._textlength(draw, proposal, font, letter_spacing=letter_spacing) <= max_width:
                current = proposal
            else:
                if current:
                    lines.append(current)
                    current = word
                else:
                    lines.append(word)
                    current = ''
        if current:
            lines.append(current)
        if len(lines) <= max_lines:
            return lines, False
        clipped = lines[: max_lines - 1]
        remainder = ' '.join(lines[max_lines - 1 :])
        clipped.append(self._ellipsize(draw, remainder, font, max_width, letter_spacing=letter_spacing))
        return clipped, True


    @staticmethod
    def _ellipsize(
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        max_width: int,
        *,
        letter_spacing: int = 0,
    ) -> str:
        trimmed = text.rstrip()
        if not trimmed:
            return ''
        if letter_spacing == 0 or len(trimmed) <= 1:
            if draw.textlength(trimmed, font=font) <= max_width:
                return trimmed
        else:
            total = 0.0
            for index, char in enumerate(trimmed):
                total += float(draw.textlength(char, font=font))
                if index < len(trimmed) - 1:
                    total += letter_spacing
            if total <= max_width:
                return trimmed
        while trimmed:
            candidate = trimmed + '...'
            if letter_spacing == 0 or len(candidate) <= 1:
                candidate_width = float(draw.textlength(candidate, font=font))
            else:
                candidate_width = 0.0
                for index, char in enumerate(candidate):
                    candidate_width += float(draw.textlength(char, font=font))
                    if index < len(candidate) - 1:
                        candidate_width += letter_spacing
            if candidate_width <= max_width:
                break
            trimmed = trimmed[:-1].rstrip()
        return (trimmed + '...') if trimmed else '...'
