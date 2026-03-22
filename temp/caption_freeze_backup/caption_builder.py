from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass
from difflib import SequenceMatcher
from html import escape
import hashlib
import re

from dealbot.utils.ua import build_offer_copy, clean_html_text, contains_cyrillic, format_deadline
from domain.entities.offer import Offer
from domain.entities.roundup_post import RoundupPost


TAG_MAP = {
    'action': '#action',
    'adventure': '#adventure',
    'rpg': '#rpg',
    'strategy': '#strategy',
    'simulation': '#simulation',
    'indie': '#indie',
    'horror': '#horror',
    'survival': '#survival',
    'racing': '#racing',
    'sports': '#sports',
    'coop': '#coop',
    'co-op': '#coop',
    'multiplayer': '#multiplayer',
    'open world': '#openworld',
    'roguelike': '#roguelike',
    'roguelite': '#roguelike',
    'shooter': '#shooter',
    'puzzle': '#puzzle',
}

EPIC_GENERIC_SUMMARY = 'Навіть якщо гру легко було пропустити на релізі, це зручний шанс додати її на акаунт без витрат.'
EVENT_GENERIC_SUMMARY = 'Тематична подія зі знижками, демоверсіями та тематичними добірками, тож це хороший момент пройтися по фестивалю.'

GENERIC_COPY_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (
        'Це гра, яку можна спокійно додати до бібліотеки й повернутися до неї пізніше.',
        'Такий клейм зручно забрати зараз і лишити в бібліотеці на потім.',
    ),
    (
        'Це гра, яку варто забрати, поки роздача відкрита, якщо вам заходять ',
        'Такий клейм особливо доречний, якщо вам заходять ',
    ),
    (
        'Це хороша можливість повернутися до цієї гри зі знижкою.',
        'Гру вже можна спокійно повернути на радар без переплати.',
    ),
    (
        'Ціна вже виглядає достатньо привабливою, щоб придивитися.',
        'Цінник уже вартий швидкої перевірки.',
    ),
    (
        'Ціна вже виглядає достатньо привабливою, щоб придивитися, якщо вам заходять ',
        'Цінник уже вартий перевірки, якщо вам заходять ',
    ),
    (
        'Гарний варіант для тих, хто любить ',
        'Влучний варіант для тих, хто любить ',
    ),
)

COMMON_MOJIBAKE_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ('â€™', '’'),
    ('â€˜', '‘'),
    ('â€œ', '"'),
    ('â€', '"'),
    ('â€“', '—'),
    ('â€”', '—'),
    ('â€¦', '…'),
    ('Â«', '«'),
    ('Â»', '»'),
    ('Â·', '·'),
    ('Â', ''),
)

ZERO_WIDTH_CHARS_RE = re.compile(r'[­​-‏‪-‮⁠﻿]')
BROKEN_REPLACEMENT_RE = re.compile(r'[�]')
HTML_TAG_SPLIT_RE = re.compile(r'(<[^>]+>)')
HTML_ENTITY_RE = re.compile(r'&(?:#[0-9]+|#x[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]+);')
MULTI_SPACE_RE = re.compile(r'[ \t]{2,}')
SPACE_BEFORE_PUNCT_RE = re.compile(r'\s+([,.;:!?%])')
SPACE_AFTER_OPEN_RE = re.compile(r'([([«“„])\s+')
SPACE_BEFORE_CLOSE_RE = re.compile(r'\s+([)\]»”])')
MISSING_SPACE_AFTER_PUNCT_RE = re.compile(r'([,.;:!?])(?=[^\s\n<])')
EM_DASH_SPACING_RE = re.compile(r'\s*[–—−]\s*')
OPENING_NEAR_REPEAT_STOPWORDS = frozenset(
    {
        'йото',
        'ця',
        'це',
        'цей',
        'цю',
        'тут',
        'вже',
        'уже',
        'зараз',
        'ще',
        'справді',
        'просто',
        'варто',
        'часу',
        'гра',
        'гру',
        'грі',
    }
)

DIRECT_OPENING_POOLS: dict[str, tuple[str, ...]] = {
    'finder': (
        'Йото знайшов хорошу знижку.',
        'Йото помітив цікаву просадку.',
        'Йото не пройшов повз цю знижку.',
    ),
    'recommend': (
        'Йото радить звернути увагу.',
        'Йото радить не проходити повз.',
        'Йото радить придивитися.',
    ),
    'alert': (
        '⚠️ Йото попереджає.',
        '⚠️ Йото не радить тягнути.',
        '⚠️ Йото нагадує: часу мало.',
    ),
    'freebie': (
        '🎁 Йото вихопив роздачу.',
        '🎁 Йото спіймав гру за 0 грн.',
        '🎁 Йото витягнув безкоштовну гру.',
    ),
    'roundup': (
        '🐱 Йото зібрав добірку сильних знижок.',
        '🐱 Йото витягнув ще кілька помітних пропозицій.',
    ),
    'first_price_move': (
        '🐱 Йото фіксує перший рух ціни вниз.',
        '🐱 Йото помітив, що цінник нарешті рушив.',
        '🐱 Йото зафіксував першу знижку.',
    ),
}

INDIRECT_HOOK_POOLS: dict[str, tuple[str, ...]] = {
    'finder': (
        'Ця знижка вже виглядає справді цікаво.',
        'Ціна просіла достатньо, щоб гра повернулася на радар.',
        'Тут уже є нормальний привід придивитися ближче.',
    ),
    'recommend': (
        'Для цієї гри цінник уже виглядає значно цікавіше.',
        'Якщо гра давно у списку, це вже знижка правильного масштабу.',
        'Для такого тайтлу пропозиція вже виглядає дуже робочою.',
    ),
    'alert': (
        'Часу тут залишилося справді небагато.',
        'Вікно вже коротке, тож відкладати перевірку не варто.',
    ),
    'freebie': (
        'Таку роздачу спокійно можна забирати в бібліотеку.',
        'Безкоштовне поповнення бібліотеки з тих, що не хочеться пропускати.',
        'Таку гру зручно забрати зараз і лишити на потім.',
    ),
    'temporary_freebie': (
        'Це коротке безкоштовне вікно, щоб спокійно зрозуміти, чи ваша це гра.',
        'Зараз є зручний шанс зайти без покупки й подивитися, чи чіпляє.',
        'Тут варто думати не про клейм, а про нормальну пробу перед покупкою.',
    ),
    'first_price_move': (
        'Цінник нарешті зрушив з місця.',
        'Для такого релізу це вже перший помітний рух по ціні.',
    ),
}

CTA_POOLS: dict[str, tuple[str, ...]] = {
    'finder': (
        'Це той випадок, коли знижку варто хоча б швидко перевірити.',
        'Якщо гра давно маячила на радарі, цю ціну вже варто звірити зі своїм списком.',
    ),
    'recommend': (
        'Якщо давно чекали приводу повернути цю гру на радар, він уже є.',
        'Для такого тайтлу це вже ціна, яку варто перевірити без зайвого шуму.',
    ),
    'first_price_move': (
        'Рух по ціні вже почався, тож гру варто повернути на радар.',
        'Знижка вже є, але для великого релізу за нею ще цікаво спостерігати.',
    ),
    'roundup': (
        'Можна швидко пройтися по списку й забрати точково найсильніше.',
        'У цій добірці зручно одним поглядом знайти те, що давно чекало свого цінника.',
    ),
}

FIRST_PRICE_MOVE_NOTE = (
    'Це перша помітна знижка по грі: рух уже почався, але для великого релізу нижчі орієнтири ще можуть бути попереду.'
)

TEMPORARY_ACCESS_HINTS = (
    'free weekend',
    'free play',
    'play for free',
    'trial',
    'weekend',
    'timed access',
    'limited time access',
    'тимчасов',
    'безкоштовні вихідні',
    'безкоштовний доступ',
    'грати безкоштовно',
    'можна пограти',
    'доступ тимчасовий',
)

RECOMMEND_REASONS = frozenset(
    {
        'editorial_importance:standout_title',
        'editorial_importance:major_franchise',
        'editorial_importance:critical_favorite',
        'editorial_importance:mega_popular',
        'editorial_importance:very_popular',
        'hero_discount',
    }
)

FINDER_REASONS = frozenset({'strong_discount', 'roundup_discount'})
FREEBIE_DIRECT_REASONS = frozenset(
    {
        'freebie_high_signal',
        'freebie_editorial_pick',
        'freebie_popular',
        'freebie_known',
        'freebie_well_reviewed',
        'freebie_ends_soon',
        'freebie_editorial_importance_high',
    }
)
FIRST_MOVE_REASONS = frozenset(
    {
        'editorial_importance:standout_title',
        'editorial_importance:major_franchise',
        'editorial_importance:mega_popular',
        'editorial_importance:very_popular',
        'editorial_importance:critical_favorite',
    }
)


@dataclass(frozen=True, slots=True)
class YotoVoiceDecision:
    presence: str
    style: str
    hook_line: str | None = None
    cta_line: str | None = None
    note_line: str | None = None
    access_type: str | None = None
    direct_mode: str | None = None


@dataclass(frozen=True, slots=True)
class YotoRoundupVoiceDecision:
    opening_line: str
    closing_cta: str


class YotoVoiceEngine:
    OPENING_ANTI_REPEAT_WINDOW = 4

    def __init__(self, history_window: int = 8) -> None:
        self._recent_openings: deque[str] = deque(maxlen=history_window)
        self._recent_ctas: deque[str] = deque(maxlen=history_window)
        self._presence_history: deque[str] = deque(maxlen=max(12, history_window + 4))
        self._last_phrase_debug: dict[str, dict[str, object]] = {}
        self._last_voice_debug: dict[str, object] = {}

    def select_offer_voice(self, offer: Offer, decision_json: dict) -> YotoVoiceDecision:
        reasons = set(decision_json.get('decision_reasons') or [])
        access_type = self.freebie_access_type(offer)
        style = self._style_for_offer(offer, decision_json, reasons, access_type)
        direct_mode = self._direct_mode_for_style(style, offer, decision_json, reasons, access_type)

        if direct_mode and not self._should_downgrade_direct(direct_mode):
            decision = YotoVoiceDecision(
                presence='direct',
                style=style,
                hook_line=self._pick_opening(direct_mode, offer.offer_id),
                cta_line=self._pick_cta(style, offer.offer_id),
                note_line=self._note_for_style(style),
                access_type=access_type,
                direct_mode=direct_mode,
            )
        elif self._should_use_indirect(style):
            decision = YotoVoiceDecision(
                presence='indirect',
                style=style,
                hook_line=self._pick_indirect_hook(style, offer.offer_id),
                cta_line=self._pick_cta(style, offer.offer_id),
                note_line=self._note_for_style(style),
                access_type=access_type,
                direct_mode=None,
            )
        else:
            decision = YotoVoiceDecision(
                presence='neutral',
                style='neutral',
                hook_line=None,
                cta_line=None,
                note_line=self._note_for_style(style),
                access_type=access_type,
                direct_mode=None,
            )

        self._presence_history.append(decision.presence)
        self._remember_voice_debug(decision.presence, decision.style, decision.hook_line, decision.cta_line)
        return decision

    def select_roundup_voice(self, roundup: RoundupPost) -> YotoRoundupVoiceDecision:
        self._presence_history.append('direct')
        decision = YotoRoundupVoiceDecision(
            opening_line=self._pick_opening('roundup', roundup.roundup_id),
            closing_cta=self._pick_cta('roundup', roundup.roundup_id) or CTA_POOLS['roundup'][0],
        )
        self._remember_voice_debug('direct', 'roundup', decision.opening_line, decision.closing_cta)
        return decision

    def last_debug_snapshot(self) -> dict[str, object]:
        return deepcopy(self._last_voice_debug)

    def _remember_voice_debug(
        self,
        presence: str,
        style: str,
        hook_line: str | None,
        cta_line: str | None,
    ) -> None:
        self._last_voice_debug = {
            'presence': presence,
            'style': style,
            'opening': dict(self._last_phrase_debug.get('opening') or {}) if hook_line else {},
            'cta': dict(self._last_phrase_debug.get('cta') or {}) if cta_line else {},
        }

    def freebie_access_type(self, offer: Offer) -> str | None:
        if not offer.is_freebie:
            return None
        if offer.source.value == 'epic':
            return 'keep_forever'

        normalized = self._normalize_offer_text(offer)
        if any(token in normalized for token in TEMPORARY_ACCESS_HINTS):
            return 'temporary_access'

        explicit = str(offer.metadata.get('free_access_type') or '').strip().lower()
        if explicit in {'temporary', 'free_weekend', 'free_play', 'trial'}:
            return 'temporary_access'
        return 'keep_forever'

    def _style_for_offer(self, offer: Offer, decision_json: dict, reasons: set[str], access_type: str | None) -> str:
        final_push = decision_json.get('lane') == 'final_push' or decision_json.get('is_final_push')
        if final_push:
            return 'alert'
        if offer.is_freebie and access_type == 'temporary_access':
            return 'temporary_freebie'
        if offer.is_freebie and access_type == 'keep_forever':
            return 'freebie'
        if self._is_first_price_move(offer, decision_json, reasons):
            return 'first_price_move'
        if self._is_recommend_candidate(offer, decision_json, reasons):
            return 'recommend'
        if self._is_finder_candidate(offer, decision_json, reasons):
            return 'finder'
        return 'neutral'

    def _direct_mode_for_style(
        self,
        style: str,
        offer: Offer,
        decision_json: dict,
        reasons: set[str],
        access_type: str | None,
    ) -> str | None:
        if style == 'alert':
            return 'alert'
        if style == 'freebie' and access_type == 'keep_forever':
            if decision_json.get('lane') in {'breaking_freebie', 'game_of_the_day'} or reasons & FREEBIE_DIRECT_REASONS:
                return 'freebie'
            return None
        if style == 'first_price_move':
            return 'first_price_move'
        if style == 'recommend':
            if decision_json.get('lane') == 'game_of_the_day':
                return 'recommend'
            if reasons & RECOMMEND_REASONS and (
                offer.discount_percent >= 45
                or decision_json.get('is_historical_best')
                or (decision_json.get('price_improved_minor') or 0) >= 1000
            ):
                return 'recommend'
            return None
        if style == 'finder':
            if offer.discount_percent >= 80:
                return 'finder'
            if (decision_json.get('price_improved_minor') or 0) >= 3000 or decision_json.get('is_historical_best'):
                return 'finder'
            if reasons & FINDER_REASONS and offer.discount_percent >= 60:
                return 'finder'
        return None

    @staticmethod
    def _should_use_indirect(style: str) -> bool:
        return style in {'alert', 'freebie', 'temporary_freebie', 'first_price_move', 'recommend', 'finder'}

    def _should_downgrade_direct(self, mode: str) -> bool:
        recent = list(self._presence_history)
        direct_last_six = recent[-6:].count('direct')
        direct_last_ten = recent[-10:].count('direct')
        if mode == 'alert':
            return direct_last_six >= 2 and direct_last_ten >= 3
        if mode == 'finder':
            return direct_last_six >= 1 or direct_last_ten >= 2
        return direct_last_six >= 2 or direct_last_ten >= 3

    def _pick_opening(self, mode: str, key: str) -> str:
        pool = DIRECT_OPENING_POOLS.get(mode) or ()
        if not pool:
            return ''
        return self._pick_phrase(
            pool,
            self._recent_openings,
            f'{mode}|{key}',
            debug_label='opening',
            anti_repeat_window=self.OPENING_ANTI_REPEAT_WINDOW,
        )

    def _pick_indirect_hook(self, style: str, key: str) -> str | None:
        pool = INDIRECT_HOOK_POOLS.get(style) or ()
        if not pool:
            return None
        return self._pick_phrase(
            pool,
            self._recent_openings,
            f'{style}|{key}',
            debug_label='opening',
            anti_repeat_window=self.OPENING_ANTI_REPEAT_WINDOW,
        )

    def _pick_cta(self, style: str, key: str) -> str | None:
        pool = CTA_POOLS.get(style) or ()
        if not pool:
            return None
        return self._pick_phrase(pool, self._recent_ctas, f'cta|{style}|{key}', debug_label='cta')

    def _pick_phrase(
        self,
        pool: tuple[str, ...],
        history: deque[str],
        key: str,
        *,
        debug_label: str,
        anti_repeat_window: int = 0,
    ) -> str:
        recent = list(history)
        recent_window = recent[-anti_repeat_window:] if anti_repeat_window > 0 else []
        candidate_pool = tuple(phrase for phrase in pool if phrase not in recent_window)
        anti_repeat_relaxed = anti_repeat_window > 0 and not candidate_pool and bool(recent_window)
        near_repeat_relaxed = False
        near_repeat_window_hits = 0
        near_repeat_pool = candidate_pool
        if anti_repeat_window > 0 and debug_label == 'opening' and candidate_pool:
            filtered_pool = tuple(
                phrase
                for phrase in candidate_pool
                if not any(self._is_near_repeat(phrase, prior) for prior in recent_window)
            )
            near_repeat_window_hits = sum(
                1
                for prior in recent_window
                if any(self._is_near_repeat(phrase, prior) for phrase in candidate_pool)
            )
            if filtered_pool:
                near_repeat_pool = filtered_pool
            else:
                near_repeat_relaxed = bool(recent_window)
        candidate_pool = near_repeat_pool
        if not candidate_pool:
            candidate_pool = pool

        best_phrase = candidate_pool[0]
        best_rank: tuple[float, float] | None = None
        for phrase in candidate_pool:
            penalty = 0.0
            for index, prior in enumerate(reversed(recent), start=1):
                if prior == phrase:
                    penalty += 2.5 / index
            repeat_similarity = 0.0
            if anti_repeat_window > 0 and debug_label == 'opening' and recent_window:
                repeat_similarity = max((self._near_repeat_score(phrase, prior) for prior in recent_window), default=0.0)
            stability_score = self._stable_score(f'{key}|{phrase}') - penalty
            rank = (repeat_similarity, -stability_score)
            if best_rank is None or rank < best_rank:
                best_phrase = phrase
                best_rank = rank

        self._last_phrase_debug[debug_label] = {
            'selected': best_phrase,
            'pool_size': len(pool),
            'anti_repeat_window': anti_repeat_window,
            'recent_repeat_count': sum(1 for prior in recent if prior == best_phrase),
            'recent_window_repeat_count': sum(1 for prior in recent_window if prior == best_phrase),
            'anti_repeat_relaxed': anti_repeat_relaxed,
            'near_repeat_relaxed': near_repeat_relaxed,
            'near_repeat_window_hits': near_repeat_window_hits,
            'repeat_risk': bool(
                anti_repeat_relaxed
                or near_repeat_relaxed
                or any(self._is_near_repeat(best_phrase, prior) for prior in recent_window)
            ),
            'fallback_used': bool(anti_repeat_relaxed or near_repeat_relaxed),
        }
        history.append(best_phrase)
        return best_phrase

    def _near_repeat_score(self, candidate: str, prior: str) -> float:
        left = self._phrase_signature(candidate)
        right = self._phrase_signature(prior)
        if not left or not right:
            return 0.0
        if left == right:
            return 1.0

        left_parts = left.split()
        right_parts = right.split()
        shared = 0.0
        leading_overlap = 0.0
        if left_parts and right_parts:
            left_tokens = set(left_parts)
            right_tokens = set(right_parts)
            shared = len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens)))
            if left_parts[0] == right_parts[0]:
                leading_overlap = 0.78 if min(len(left_parts), len(right_parts)) >= 2 else 0.62
            if len(left_parts) >= 2 and len(right_parts) >= 2 and left_parts[:2] == right_parts[:2]:
                leading_overlap = 0.92

        sequence = SequenceMatcher(None, left, right).ratio()
        return max(shared, leading_overlap, sequence)

    def _is_near_repeat(self, candidate: str, prior: str) -> bool:
        return self._near_repeat_score(candidate, prior) >= 0.72

    def _phrase_signature(self, value: str) -> str:
        normalized = re.sub(r'[^0-9a-zа-яіїєґ ]+', ' ', str(value or '').casefold())
        tokens = [token for token in normalized.split() if token and token not in OPENING_NEAR_REPEAT_STOPWORDS]
        if tokens:
            return ' '.join(tokens)
        return ' '.join(normalized.split())

    @staticmethod
    def _stable_score(key: str) -> float:
        digest = hashlib.sha256(key.encode('utf-8')).digest()
        return int.from_bytes(digest[:8], 'big') / float(2**64)

    @staticmethod
    def _note_for_style(style: str) -> str | None:
        if style == 'first_price_move':
            return FIRST_PRICE_MOVE_NOTE
        return None

    @staticmethod
    def _is_recommend_candidate(offer: Offer, decision_json: dict, reasons: set[str]) -> bool:
        return bool(
            decision_json.get('lane') == 'game_of_the_day'
            or reasons & RECOMMEND_REASONS
            or ((offer.review_score or 0) >= 90 and (offer.review_count or 0) >= 2000 and offer.discount_percent >= 45)
        )

    @staticmethod
    def _is_finder_candidate(offer: Offer, decision_json: dict, reasons: set[str]) -> bool:
        if decision_json.get('lane') == 'backlog_filler':
            return False
        if decision_json.get('lane') == 'high_value_discount' and offer.discount_percent >= 50:
            return True
        return bool(reasons & FINDER_REASONS and offer.discount_percent >= 50)

    @staticmethod
    def _is_first_price_move(offer: Offer, decision_json: dict, reasons: set[str]) -> bool:
        if offer.is_freebie or offer.is_event or offer.is_dlc or offer.is_soundtrack:
            return False
        if decision_json.get('lane') == 'backlog_filler':
            return False
        if not reasons & FIRST_MOVE_REASONS:
            return False
        if decision_json.get('previous_price_minor') is not None or decision_json.get('best_price_minor') is not None:
            return False
        if not (0 < offer.discount_percent <= 20):
            return False
        if offer.price_before_minor is None or offer.price_after_minor is None:
            return False
        return offer.price_after_minor < offer.price_before_minor

    def _normalize_offer_text(self, offer: Offer) -> str:
        parts: list[str] = [offer.title, offer.store_url, offer.short_description, offer.description]
        parts.extend(self._flatten_values(offer.metadata))
        normalized_parts = []
        for value in parts:
            token = re.sub(r'[^0-9a-zа-яіїєґ]+', ' ', str(value or '').lower()).strip()
            if token:
                normalized_parts.append(token)
        return ' | '.join(normalized_parts)

    def _flatten_values(self, value: object) -> Iterable[str]:
        if value is None:
            return ()
        if isinstance(value, str):
            return (value,)
        if isinstance(value, dict):
            flattened: list[str] = []
            for item in value.values():
                flattened.extend(self._flatten_values(item))
            return tuple(flattened)
        if isinstance(value, Iterable):
            flattened = []
            for item in value:
                flattened.extend(self._flatten_values(item))
            return tuple(flattened)
        return (str(value),)


class TelegramCaptionBuilder:
    def __init__(self, caption_limit: int = 1024, voice_engine: YotoVoiceEngine | None = None) -> None:
        self.caption_limit = caption_limit
        self.voice_engine = voice_engine or YotoVoiceEngine()
        self._last_debug: dict[str, object] = {}
        self._last_copy_debug: dict[str, object] = {}


    def build(self, offer: Offer, decision_json: dict) -> tuple[str, list[str]]:
        hashtags = self._build_hashtags(offer, decision_json)
        voice = self.voice_engine.select_offer_voice(offer, decision_json)
        copy = self._pick_copy(offer, decision_json, voice)
        caption, normalization_debug = self._compose_for_publish(offer, decision_json, copy, hashtags, voice)
        final_hashtags = hashtags
        limit_fallback_used = False
        if len(caption) <= self.caption_limit:
            self._remember_caption_debug(
                offer,
                decision_json,
                voice,
                copy,
                normalization_debug,
                fallback_used=limit_fallback_used,
            )
            return caption, hashtags

        for limit in (240, 200, 160, 120, 90):
            copy = self._pick_copy(offer, decision_json, voice, max_length=limit)
            caption, normalization_debug = self._compose_for_publish(offer, decision_json, copy, hashtags, voice)
            if len(caption) <= self.caption_limit:
                limit_fallback_used = True
                self._remember_caption_debug(
                    offer,
                    decision_json,
                    voice,
                    copy,
                    normalization_debug,
                    fallback_used=limit_fallback_used,
                )
                return caption, hashtags

        trimmed_tags = hashtags[:]
        while len(trimmed_tags) > 3:
            trimmed_tags.pop()
            caption, normalization_debug = self._compose_for_publish(offer, decision_json, copy, trimmed_tags, voice)
            if len(caption) <= self.caption_limit:
                limit_fallback_used = True
                final_hashtags = trimmed_tags
                self._remember_caption_debug(
                    offer,
                    decision_json,
                    voice,
                    copy,
                    normalization_debug,
                    fallback_used=limit_fallback_used,
                )
                return caption, trimmed_tags

        trimmed_copy = {**copy, 'summary': ''}
        caption, normalization_debug = self._compose_for_publish(offer, decision_json, trimmed_copy, trimmed_tags, voice)
        if len(caption) <= self.caption_limit:
            limit_fallback_used = True
            final_hashtags = trimmed_tags
            self._remember_caption_debug(
                offer,
                decision_json,
                voice,
                trimmed_copy,
                normalization_debug,
                fallback_used=limit_fallback_used,
            )
            return caption, trimmed_tags
        caption = caption[: self.caption_limit - 1].rstrip() + '…'
        limit_fallback_used = True
        final_hashtags = trimmed_tags
        self._remember_caption_debug(
            offer,
            decision_json,
            voice,
            trimmed_copy,
            normalization_debug,
            fallback_used=limit_fallback_used,
        )
        return caption, final_hashtags


    def last_debug_snapshot(self) -> dict[str, object]:
        return deepcopy(self._last_debug)

    def _remember_caption_debug(
        self,
        offer: Offer,
        decision_json: dict,
        voice: YotoVoiceDecision,
        copy: dict[str, str],
        normalization_debug: dict[str, object],
        *,
        fallback_used: bool,
    ) -> None:
        voice_debug = self.voice_engine.last_debug_snapshot()
        opening_debug = dict(voice_debug.get('opening') or {})
        if voice.hook_line:
            opening_debug.setdefault('line', voice.hook_line)
        selected_opener = clean_html_text(voice.hook_line or copy.get('hook_line', ''))
        copy_debug = dict(self._last_copy_debug)
        self._last_debug = {
            'offer_id': offer.offer_id,
            'lane': decision_json.get('lane'),
            'presence': voice.presence,
            'style': voice.style,
            'opening': opening_debug,
            'cta': dict(voice_debug.get('cta') or {}),
            'selected_opener': selected_opener,
            'normalization_applied': dict(normalization_debug.get('flags') or {}),
            'weird_symbol_detected': bool(normalization_debug.get('weird_symbol_detected', False)),
            'repeat_risk': bool(opening_debug.get('repeat_risk', False)),
            'fallback_used': bool(
                fallback_used
                or opening_debug.get('fallback_used')
                or copy_debug.get('summary_fallback_used')
                or copy_debug.get('hook_fallback_used')
                or copy_debug.get('urgency_fallback_used')
            ),
        }

    def _compose_for_publish(
        self,
        offer: Offer,
        decision_json: dict,
        copy: dict[str, str],
        hashtags: list[str],
        voice: YotoVoiceDecision,
    ) -> tuple[str, dict[str, object]]:
        raw_caption = self._compose(offer, decision_json, copy, hashtags, voice)
        return self._normalize_caption_html(raw_caption)


    def _compose(
        self,
        offer: Offer,
        decision_json: dict,
        copy: dict[str, str],
        hashtags: list[str],
        voice: YotoVoiceDecision,
    ) -> str:
        if offer.source.value == 'epic':
            return self._build_epic_caption(offer, decision_json, copy, hashtags, voice)
        if offer.is_event:
            return self._build_event_caption(offer, decision_json, copy, hashtags, voice)
        return self._build_steam_caption(offer, decision_json, copy, hashtags, voice)

    def _build_steam_caption(
        self,
        offer: Offer,
        decision_json: dict,
        copy: dict[str, str],
        hashtags: list[str],
        voice: YotoVoiceDecision,
    ) -> str:
        prefix = '🎁' if offer.is_freebie else '🔥'
        if decision_json.get('lane') == 'game_of_the_day':
            prefix = '⭐'
        title_line = f'{prefix} <a href="{self._link(offer.store_url)}"><b>{escape(offer.title)}</b></a>'
        lines: list[str] = [title_line]
        body_lines: list[str] = []

        self._append_body_line(lines, body_lines, copy.get('hook_line', ''))
        self._append_body_line(lines, body_lines, copy.get('summary', ''))

        if decision_json.get('lane') == 'game_of_the_day':
            self._append_body_line(lines, body_lines, 'Гра дня: одна з найпомітніших знахідок у Steam просто зараз.')

        self._append_body_line(lines, body_lines, self._build_steam_value_line(offer, voice))
        self._append_body_line(lines, body_lines, self._build_improvement_note(offer, decision_json, voice))
        self._append_body_line(lines, body_lines, self._select_urgency_line(offer, decision_json, copy))
        self._append_body_line(lines, body_lines, self._build_supporting_line(offer))
        self._append_body_line(lines, body_lines, self._build_cta(offer, decision_json, voice))

        lines.append(' '.join(hashtags))
        return '\n\n'.join(line for line in lines if line)

    def _build_epic_caption(
        self,
        offer: Offer,
        decision_json: dict,
        copy: dict[str, str],
        hashtags: list[str],
        voice: YotoVoiceDecision,
    ) -> str:
        title_line = f'🎁 <a href="{self._link(offer.store_url)}"><b>{escape(offer.title)}</b></a>'
        lines: list[str] = [title_line]
        body_lines: list[str] = []

        self._append_body_line(lines, body_lines, copy.get('hook_line', ''))
        self._append_body_line(lines, body_lines, copy.get('summary', '') or escape(EPIC_GENERIC_SUMMARY))
        self._append_body_line(lines, body_lines, self._build_epic_claim_line(offer, voice))
        self._append_body_line(lines, body_lines, self._select_urgency_line(offer, decision_json, copy))
        self._append_body_line(lines, body_lines, self._build_supporting_line(offer))
        self._append_body_line(lines, body_lines, self._build_cta(offer, decision_json, voice))

        lines.append(' '.join(hashtags))
        return '\n\n'.join(line for line in lines if line)

    def _build_event_caption(
        self,
        offer: Offer,
        decision_json: dict,
        copy: dict[str, str],
        hashtags: list[str],
        voice: YotoVoiceDecision,
    ) -> str:
        title_line = f'🎉 <a href="{self._link(offer.store_url)}"><b>{escape(offer.title)}</b></a>'
        lines: list[str] = [title_line]
        body_lines: list[str] = []

        self._append_body_line(lines, body_lines, copy.get('hook_line', ''))
        self._append_body_line(lines, body_lines, copy.get('summary', '') or escape(EVENT_GENERIC_SUMMARY))
        self._append_body_line(lines, body_lines, self._select_urgency_line(offer, decision_json, copy))
        self._append_body_line(lines, body_lines, self._build_cta(offer, decision_json, voice))

        lines.append(' '.join(hashtags))
        return '\n\n'.join(line for line in lines if line)

    def _pick_copy(
        self,
        offer: Offer,
        decision_json: dict,
        voice: YotoVoiceDecision,
        max_length: int = 320,
    ) -> dict[str, str]:
        raw_copy = build_offer_copy(
            offer.title,
            offer.short_description,
            offer.description,
            offer.genres,
            offer.tags,
            source=offer.source.value,
            is_free=offer.is_freebie,
            is_event=offer.is_event,
            discount_percent=offer.discount_percent,
            lane=decision_json.get('lane'),
            is_final_push=bool(decision_json.get('is_final_push')),
            promo_start=offer.promo_start,
            promo_end=offer.promo_end,
            long_summary_limit=max_length,
            short_summary_limit=min(max_length, 110),
        )

        source_summary = self._pick_source_summary(offer)
        summary_fallback_used = False
        if source_summary:
            summary = source_summary
        elif offer.is_event:
            summary = EVENT_GENERIC_SUMMARY
            summary_fallback_used = True
        else:
            summary = self._refine_fallback_summary(raw_copy.get('summary', ''), offer)
            summary_fallback_used = not bool(clean_html_text(source_summary))
        if not summary and offer.source.value == 'epic':
            summary = EPIC_GENERIC_SUMMARY
            summary_fallback_used = True
        elif not summary and offer.is_event:
            summary = EVENT_GENERIC_SUMMARY
            summary_fallback_used = True

        hook_line = voice.hook_line or self._build_caption_hook_line(
            offer,
            decision_json,
            raw_copy.get('hook_line', ''),
            voice.access_type,
        )
        urgency_line = self._build_caption_urgency_line(
            offer,
            decision_json,
            raw_copy.get('urgency_line', ''),
            voice.access_type,
        )
        self._last_copy_debug = {
            'summary_fallback_used': summary_fallback_used,
            'hook_fallback_used': not bool(voice.hook_line),
            'urgency_fallback_used': not bool(clean_html_text(raw_copy.get('urgency_line', ''))),
        }

        return {
            'summary': escape(self._strip_redundant_title_prefix(summary, offer.title)),
            'hook_line': escape(clean_html_text(hook_line)),
            'urgency_line': escape(clean_html_text(urgency_line)),
        }


    @staticmethod
    def _pick_source_summary(offer: Offer) -> str:
        for value in (offer.short_description, offer.description):
            cleaned = clean_html_text(value)
            if cleaned and contains_cyrillic(cleaned):
                return cleaned
        return ''

    def _refine_fallback_summary(self, summary: str, offer: Offer) -> str:
        cleaned = self._strip_redundant_title_prefix(summary, offer.title)
        if not cleaned or offer.is_event:
            return cleaned

        first_sentence, separator, remainder = cleaned.partition('. ')
        lowered = first_sentence.casefold()
        if separator and remainder and any(
            token in lowered
            for token in (
                'зараз можна',
                'зараз доступна',
                'вигідно взяти',
                'безкоштовно забрати',
            )
        ):
            cleaned = self._capitalize_fragment(remainder)

        for original, replacement in GENERIC_COPY_REPLACEMENTS:
            if original in cleaned:
                cleaned = cleaned.replace(original, replacement)
        return cleaned

    def _build_caption_hook_line(
        self,
        offer: Offer,
        decision_json: dict,
        raw_hook: str,
        access_type: str | None,
    ) -> str:
        safe_title = clean_html_text(offer.title) or 'Гра'
        final_push = decision_json.get('lane') == 'final_push' or decision_json.get('is_final_push')
        if offer.is_event:
            return f'{safe_title} збирає знижки, демо та жанрові знахідки в одному місці.'
        if final_push:
            return 'Останнє вікно, щоб не проґавити цю пропозицію.'
        if offer.is_freebie:
            if access_type == 'temporary_access':
                return 'У гру зараз можна зайти безкоштовно протягом обмеженого часу.'
            if offer.source.value == 'epic':
                return 'Чергове безкоштовне поповнення бібліотеки в Epic, яке можна забрати назавжди.'
            return 'Гру можна безкоштовно додати в бібліотеку просто зараз.'
        if offer.discount_percent >= 75:
            return 'Одна з найпомітніших знижок на гру просто зараз.'
        if offer.discount_percent >= 50:
            return 'Хороший момент взяти гру суттєво дешевше, ніж зазвичай.'
        if offer.discount_percent > 0:
            return 'Гра відчутно подешевшала й повернулася на радар.'
        return clean_html_text(raw_hook)

    def _build_caption_urgency_line(
        self,
        offer: Offer,
        decision_json: dict,
        raw_urgency: str,
        access_type: str | None,
    ) -> str:
        normalized_raw = clean_html_text(raw_urgency)
        if normalized_raw.startswith('Стартує'):
            return normalized_raw

        final_push = decision_json.get('lane') == 'final_push' or decision_json.get('is_final_push')
        deadline = format_deadline(offer.promo_end)
        if deadline:
            if final_push:
                return f'Фінальний шанс: до {deadline}.'
            if offer.is_event:
                return f'Фестиваль триває до {deadline}.'
            if offer.is_freebie:
                if access_type == 'temporary_access':
                    return f'Безкоштовний доступ відкритий до {deadline}.'
                return f'Забрати назавжди варто до {deadline}.'
            return f'Актуально до {deadline}.'
        if final_push:
            return 'Фінальний шанс: пропозиція вже на останній прямій.'
        if offer.is_event:
            return 'Подія вже триває, тож добірку краще переглянути без відкладань.'
        if offer.is_freebie:
            if access_type == 'temporary_access':
                return 'Безкоштовний доступ уже активний.'
            if offer.source.value == 'epic':
                return 'Роздача в Epic Games Store уже активна.'
            return 'Роздача в Steam уже активна.'
        return normalized_raw

    @staticmethod
    def _strip_redundant_title_prefix(summary: str, title: str) -> str:
        normalized_summary = clean_html_text(summary).strip()
        normalized_title = clean_html_text(title).strip()
        if not normalized_summary or not normalized_title:
            return normalized_summary
        if not normalized_summary.casefold().startswith(normalized_title.casefold()):
            return normalized_summary

        remainder = normalized_summary[len(normalized_title):].lstrip(' —-:,.')
        if not remainder:
            return normalized_summary
        return remainder[0].upper() + remainder[1:]

    @staticmethod
    def _capitalize_fragment(value: str) -> str:
        if not value:
            return value
        return value[0].upper() + value[1:]

    def _build_steam_value_line(self, offer: Offer, voice: YotoVoiceDecision) -> str:
        if offer.is_freebie:
            before = self._format_minor(offer.price_before_minor)
            if voice.access_type == 'temporary_access':
                if before != 'невідомо':
                    return (
                        f'Замість {before} у гру зараз можна '
                        f'<a href="{self._link(offer.store_url)}"><b>пограти безкоштовно</b></a>; доступ тимчасовий.'
                    )
                return (
                    f'Зараз у гру можна '
                    f'<a href="{self._link(offer.store_url)}"><b>пограти безкоштовно</b></a>; доступ тимчасовий.'
                )
            if before != 'невідомо':
                return (
                    f'Замість {before} її зараз можна '
                    f'<a href="{self._link(offer.store_url)}"><b>додати безкоштовно</b></a> до бібліотеки назавжди.'
                )
            return (
                f'Зараз її можна '
                f'<a href="{self._link(offer.store_url)}"><b>додати безкоштовно</b></a> до бібліотеки назавжди.'
            )

        now_price = self._format_minor(offer.price_after_minor)
        old_price = self._format_minor(offer.price_before_minor)
        if now_price != 'невідомо' and old_price != 'невідомо':
            savings = self._format_minor(max((offer.price_before_minor or 0) - (offer.price_after_minor or 0), 0))
            return (
                f'Зараз <a href="{self._link(offer.store_url)}"><b>{now_price}</b></a> '
                f'замість {old_price}; економія {savings}.'
            )
        if now_price != 'невідомо':
            return f'Зараз <a href="{self._link(offer.store_url)}"><b>{now_price}</b></a>.'
        return ''

    def _build_epic_claim_line(self, offer: Offer, voice: YotoVoiceDecision) -> str:
        before = self._format_minor(offer.price_before_minor)
        if voice.access_type == 'temporary_access':
            if before != 'невідомо':
                return f'Замість {before} гру можна спокійно спробувати без оплати; доступ тимчасовий.'
            return 'Гру можна безкоштовно спробувати; доступ тимчасовий.'
        if before != 'невідомо':
            return f'Замість {before} гру можна спокійно додати на акаунт без оплати й залишити назавжди.'
        return 'Гру можна швидко забрати на акаунт і залишити в бібліотеці назавжди.'

    def _select_urgency_line(self, offer: Offer, decision_json: dict, copy: dict[str, str]) -> str:
        if not self._should_use_urgency_line(offer, decision_json):
            return ''
        return copy.get('urgency_line', '')

    @staticmethod
    def _should_use_urgency_line(offer: Offer, decision_json: dict) -> bool:
        if offer.is_freebie or offer.is_event:
            return True
        if decision_json.get('lane') == 'game_of_the_day':
            return True
        if decision_json.get('lane') == 'final_push' or decision_json.get('is_final_push'):
            return True
        return offer.discount_percent >= 75

    def _build_cta(self, offer: Offer, decision_json: dict, voice: YotoVoiceDecision) -> str:
        if voice.cta_line:
            return voice.cta_line

        final_push = decision_json.get('lane') == 'final_push' or decision_json.get('is_final_push')
        if offer.is_event:
            return 'Перегляньте фестиваль зараз, поки він у розпалі.'
        if offer.is_freebie:
            if voice.access_type == 'temporary_access':
                return 'Якщо хотіли спробувати гру, зараз якраз зручне вікно зайти безкоштовно.'
            if offer.source.value == 'epic':
                return 'Забирайте на акаунт зараз, поки роздача відкрита й додається назавжди.'
            return 'Додайте в бібліотеку зараз, поки роздача відкрита й гра лишається назавжди.'
        if final_push:
            return 'Якщо гра давно у списку бажаного, час брати.'
        if decision_json.get('lane') == 'game_of_the_day':
            return 'Перевірте пропозицію зараз, поки вона тримає слот дня.'
        return 'Якщо давно чекали зручний цінник, саме час перевірити пропозицію.'

    def _build_improvement_note(self, offer: Offer, decision_json: dict, voice: YotoVoiceDecision) -> str:
        if voice.note_line:
            return voice.note_line

        previous_price = decision_json.get('previous_price_minor')
        previous_posted_at = decision_json.get('previous_posted_at')
        if previous_price is None:
            return 'За нашою історією це найкращий зафіксований цінник.' if decision_json.get('is_historical_best') else ''

        old_price = self._format_minor(previous_price)
        new_price = self._format_minor(offer.price_after_minor)
        if decision_json.get('price_improved_minor'):
            if previous_posted_at:
                try:
                    stamp = format_deadline(__import__('datetime').datetime.fromisoformat(previous_posted_at))
                except ValueError:
                    stamp = None
                if stamp:
                    return f'Стало ще краще: {stamp} було {old_price}, зараз {new_price}.'
            return f'Стало ще краще: було {old_price}, зараз {new_price}.'
        if decision_json.get('is_historical_best'):
            return f'За нашою історією це найкращий цінник: зараз {new_price} замість попередніх {old_price}.'
        return ''

    def _build_supporting_line(self, offer: Offer) -> str:
        bits: list[str] = []
        review_bit = self._build_review_bit(offer)
        if review_bit:
            bits.append(review_bit)
        achievements_bit = self._build_achievements_bit(offer.achievements_count)
        if achievements_bit:
            bits.append(achievements_bit)
        if offer.has_trading_cards:
            bits.append('є картки')
        return ' • '.join(bits[:3])

    @staticmethod
    def _build_review_bit(offer: Offer) -> str:
        if offer.review_score is not None and offer.review_count:
            return f'{offer.review_score}% позитивних із {offer.review_count} оцінок'
        if offer.review_score is not None:
            return f'{offer.review_score}% позитивних'
        if offer.review_count:
            return f'{offer.review_count} оцінок'
        return ''

    @staticmethod
    def _build_achievements_bit(count: int | None) -> str:
        if not count or count <= 0:
            return ''
        remainder_100 = count % 100
        remainder_10 = count % 10
        if 11 <= remainder_100 <= 14:
            suffix = 'досягнень'
        elif remainder_10 == 1:
            suffix = 'досягнення'
        elif remainder_10 in (2, 3, 4):
            suffix = 'досягнення'
        else:
            suffix = 'досягнень'
        return f'{count} {suffix}'

    def _append_body_line(self, lines: list[str], body_lines: list[str], candidate: str) -> None:
        normalized = self._normalize_line(candidate)
        if not normalized:
            return
        for existing in body_lines:
            shorter, longer = sorted((normalized, existing), key=len)
            if shorter == longer:
                return
            if len(shorter) >= 32 and shorter in longer:
                return
        lines.append(candidate)
        body_lines.append(normalized)

    @staticmethod
    def _normalize_line(value: str) -> str:
        return clean_html_text(value).casefold().strip()

    def _normalize_caption_html(self, caption: str) -> tuple[str, dict[str, object]]:
        flags = {
            'removed_replacement_chars': False,
            'removed_garbage_unicode': False,
            'normalized_dashes': False,
            'normalized_whitespace': False,
            'normalized_punctuation_spacing': False,
        }
        weird_symbol_detected = False
        parts: list[str] = []
        for chunk in HTML_TAG_SPLIT_RE.split(caption):
            if not chunk:
                continue
            if chunk.startswith('<') and chunk.endswith('>'):
                parts.append(chunk)
                continue
            normalized_chunk, chunk_flags, chunk_weird = self._normalize_caption_text(chunk)
            weird_symbol_detected = weird_symbol_detected or chunk_weird
            for key, value in chunk_flags.items():
                flags[key] = flags[key] or value
            parts.append(normalized_chunk)

        normalized = ''.join(parts)
        compacted = re.sub(r'[ \t]+\n', '\n', normalized)
        compacted = re.sub(r'\n[ \t]+', '\n', compacted)
        compacted = re.sub(r'\n{3,}', '\n\n', compacted).strip()
        if compacted != normalized:
            flags['normalized_whitespace'] = True
        return compacted, {'flags': flags, 'weird_symbol_detected': weird_symbol_detected}

    def _normalize_caption_text(self, value: str) -> tuple[str, dict[str, bool], bool]:
        text = value
        flags = {
            'removed_replacement_chars': False,
            'removed_garbage_unicode': False,
            'normalized_dashes': False,
            'normalized_whitespace': False,
            'normalized_punctuation_spacing': False,
        }
        weird_symbol_detected = False

        if BROKEN_REPLACEMENT_RE.search(text):
            weird_symbol_detected = True
            flags['removed_replacement_chars'] = True
            text = BROKEN_REPLACEMENT_RE.sub('', text)

        if ZERO_WIDTH_CHARS_RE.search(text):
            weird_symbol_detected = True
            flags['removed_garbage_unicode'] = True
            text = ZERO_WIDTH_CHARS_RE.sub('', text)

        for broken, fixed in COMMON_MOJIBAKE_REPLACEMENTS:
            if broken in text:
                weird_symbol_detected = True
                flags['removed_garbage_unicode'] = True
                text = text.replace(broken, fixed)

        replaced_nbsp = text.replace('\u00a0', ' ')
        if replaced_nbsp != text:
            flags['normalized_whitespace'] = True
            text = replaced_nbsp

        normalized_dashes = EM_DASH_SPACING_RE.sub(' — ', text)
        if normalized_dashes != text:
            flags['normalized_dashes'] = True
            text = normalized_dashes

        entity_placeholders: dict[str, str] = {}
        protected_text = text
        if '&' in text and ';' in text:
            def _stash_entity(match: re.Match[str]) -> str:
                placeholder = f'__HTML_ENTITY_{len(entity_placeholders)}__'
                entity_placeholders[placeholder] = match.group(0)
                return placeholder

            protected_text = HTML_ENTITY_RE.sub(_stash_entity, text)

        without_space_before = SPACE_BEFORE_PUNCT_RE.sub(r'\1', protected_text)
        without_space_before = SPACE_AFTER_OPEN_RE.sub(r'\1', without_space_before)
        without_space_before = SPACE_BEFORE_CLOSE_RE.sub(r'\1', without_space_before)
        with_space_after = MISSING_SPACE_AFTER_PUNCT_RE.sub(r'\1 ', without_space_before)
        with_space_after = re.sub(r'(?<=\d): (?=\d)', ':', with_space_after)
        for placeholder, original in entity_placeholders.items():
            with_space_after = with_space_after.replace(placeholder, original)
        if with_space_after != text:
            flags['normalized_punctuation_spacing'] = True
            text = with_space_after

        compacted = MULTI_SPACE_RE.sub(' ', text)
        if compacted != text:
            flags['normalized_whitespace'] = True
            text = compacted
        return text, flags, weird_symbol_detected

    def _build_hashtags(self, offer: Offer, decision_json: dict) -> list[str]:
        hashtags: list[str] = []
        if offer.source.value == 'steam':
            hashtags.extend(['#steam', '#freegame' if offer.is_freebie else '#steamsale'])
        elif offer.source.value == 'epic':
            hashtags.extend(['#epicgames', '#freegame', '#giveaway'])
        else:
            hashtags.extend(['#steam', '#festival', '#gaming'])

        lane = decision_json.get('lane')
        if lane == 'game_of_the_day':
            hashtags.append('#gameday')
        if lane == 'final_push' or decision_json.get('is_final_push'):
            hashtags.append('#finalpush')

        seen = set(hashtags)
        for raw in list(offer.tags) + list(offer.genres):
            normalized = raw.strip().lower()
            if not normalized:
                continue
            tag = None
            if normalized.startswith('#'):
                tag = normalized
            else:
                for key, mapped in TAG_MAP.items():
                    if key in normalized:
                        tag = mapped
                        break
            if tag and tag not in seen:
                hashtags.append(tag)
                seen.add(tag)
            if len(hashtags) >= 7:
                break
        return hashtags[:7]

    @staticmethod
    def _link(url: str) -> str:
        return escape(url, quote=True)

    @staticmethod
    def _format_minor(value: int | None) -> str:
        if value is None:
            return 'невідомо'
        amount = value / 100
        if int(amount) == amount:
            return f'{int(amount)} грн'
        return f'{amount:.2f} грн'




