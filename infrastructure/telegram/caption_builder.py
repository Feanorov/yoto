from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass
from difflib import SequenceMatcher
from html import escape
import hashlib
import re

from dealbot.utils.ua import build_focus_text, build_offer_copy, clean_html_text, contains_cyrillic, format_compact_review_count, format_deadline, truncate_text
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

EPIC_GENERIC_SUMMARY = 'Не найгучніша роздача тижня, але цілком чесна безкоштовна знахідка, яку варто хоча б мати на радарі.'
EVENT_GENERIC_SUMMARY = 'Фестиваль найкраще проходити точково: кількох хвилин вистачає, щоб перевірити головне й лишити собі кілька знахідок.'

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
SOURCE_SUMMARY_SECTION_MARKERS = ('про гру', 'about this game')
SOURCE_SUMMARY_PREFIX_RE = re.compile(
    r"""^
    (?:
        (?:
            starter
            |standard
            |deluxe
            |ultimate
            |complete
            |definitive
            |gold
            |premium
            |collector(?:'s|’s)?
            |founder(?:'s|’s)?
            |director(?:'s|’s)?
            |game\ of\ the\ year
            |goty
            |anniversary
            |season\ pass(?:\ \d+)?
            |expansion\ pass(?:\ \d+)?
            |battle\ pass(?:\ \d+)?
            |character\ pass(?:\ \d+)?
            |story\ pass(?:\ \d+)?
            |supporter\ pack
            |soundtrack
            |bundle
            |pack
            |collection
        )
        (?:\s+[0-9a-z®™'’:+/&()_.-]+){0,6}
        [\s:—\-|]*
    )+
    """,
    re.IGNORECASE | re.VERBOSE,
)
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
        '🎁 Йото зловив безкоштовну роздачу.',
        '🎁 Йото помітив ще один тайтл за 0 грн.',
        '🎁 Йото приніс безкоштовну гру.',
    ),
    'roundup': (
        '🐱 Йото відсіяв шум і залишив тільки те, що тягне на окремий список.',
        '🐱 Йото зібрав короткий редакторський список без випадкових позицій.',
        '🐱 Йото виніс у добірку тільки ті пропозиції, що тримаються самі по собі.',
        '🐱 Йото склав швидкий список із тих тайтлів, де вибір уже виглядає предметно.',
        '🐱 Йото зібрав верхівку з того, що справді варте окремого відкриття.',
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
        'Ще одна безкоштовна гра, яку легко не проґавити.',
        'Тут якраз той випадок, коли безкоштовність не виглядає випадковою.',
        'Безкоштовний слот, який варто хоча б швидко звірити зі своїми смаками.',
    ),
    'temporary_freebie': (
        'Це коротке безкоштовне вікно, щоб спокійно зрозуміти, чи ваша це гра.',
        'Безкоштовний доступ відкритий саме для того, щоб перевірити гру без покупки.',
        'Тут важливіше спробувати гру, ніж просто побачити нуль у ціннику.',
    ),
    'festival': (
        'У Steam відкрилося тематичне вікно, яке зручніше проходити точково, ніж суцільним скролом.',
        'Цей фестиваль краще читати як коротку добірку по темі, а не як ще одну довгу вітрину.',
        'Тут сенс не в тому, щоб дивитися все підряд, а в тому, щоб швидко знайти кілька точних попадань.',
    ),
    'first_price_move': (
        'Цінник нарешті зрушив з місця.',
        'Для такого релізу це вже перший помітний рух по ціні.',
    ),
}

CTA_POOLS: dict[str, tuple[str, ...]] = {
    'finder': (
        'Якщо давно була в бажаному — це хороший момент.',
        'Якщо чекав(ла) нижчу ціну — ось вона.',
        'Нормальна точка входу, якщо давно хотів(ла) спробувати.',
    ),
    'recommend': (
        'Якщо давно хотів(ла) спробувати — це хороший момент.',
        'Нормальна ціна старту, якщо гра давно була на радарі.',
        'Якщо чекав(ла) нижчу ціну на великий тайтл — ось вона.',
    ),
    'freebie': (
        'Якщо така гра вам підходить, краще забрати її до закриття роздачі без зайвих відкладань.',
        'Тут вистачає одного швидкого кліку зараз, щоб не згадувати про цю роздачу запізно.',
        'Якщо хотіли лишити собі ще один запасний тайтл за 0 грн, вікно вже відкрите.',
    ),
    'temporary_freebie': (
        'Якщо гра була на радарі, це зручне вікно перевірити її без покупки.',
        'Тут логіка проста: не брати про запас, а спробувати зараз.',
        'Якщо хотіли чесний тест-драйв без ризику, це саме той випадок.',
    ),
    'festival': (
        'Почніть із верхівки сторінки та тематичних секцій: цього вже вистачить, щоб швидко відмітити своє.',
        'Найкращий хід тут простий: відкласти кілька точних попадань і не тонути в решті каталогу.',
        'Зайдіть хоча б на основні секції фестивалю: за кілька хвилин стане ясно, чи є тут ваші тайтли.',
    ),
    'first_price_move': (
        'Якщо чекав(ла) першу нормальну просадку — гру вже можна повертати в бажане.',
        'Перший рух ціни вниз уже є, тож гру можна знову тримати на радарі.',
        'Нормальний момент повернутися до гри, якщо чекав(ла) саме першої просадки.',
    ),
    'roundup': (
        'Починайте з верхівки: порядок тут уже працює як короткий маршрут.',
        'Цю добірку краще пройти зверху вниз і зупинитися тільки на своєму.',
        'Якщо часу мало, відкрийте перші позиції, а далі вже відсікайте точково.',
        'Тут не треба довгого скролу: кілька верхніх сторінок уже дають головну користь.',
        'Беріть список як готовий маршрут на кілька швидких відкриттів.',
    ),
}

FIRST_PRICE_MOVE_NOTE = (
    'Це перша помітна знижка по грі: рух уже почався, але для великого релізу нижчі орієнтири ще можуть бути попереду.'
)

FREEBIE_FOCUS_SUMMARY_TEMPLATES: tuple[str, ...] = (
    'Ключовий акцент тут — {focus}.',
    'За відчуттям це гра з акцентом на {focus}.',
    'Тут жанровий центр ваги — {focus}.',
)

FREEBIE_GENERIC_SUMMARY_TEMPLATES: tuple[str, ...] = (
    'Не найгучніша роздача в календарі, але цілком чесна безкоштовна знахідка.',
    'Такий безкоштовний тайтл беруть радше за шанс спокійно відкрити щось нове, ніж за шум навколо.',
    'Це спокійна безкоштовна знахідка з тих, що приємно мати під рукою на свій темп.',
)

TEMPORARY_FREEBIE_FOCUS_SUMMARY_TEMPLATES: tuple[str, ...] = (
    'Ключовий акцент тут — {focus}, тож безкоштовне вікно виглядає доречно.',
    'Тут жанровий центр ваги — {focus}, а безкоштовне вікно дає спокійний тест-драйв.',
    'Безкоштовне вікно тут добре працює там, де вас цікавить саме {focus}.',
)

TEMPORARY_FREEBIE_GENERIC_SUMMARY_TEMPLATES: tuple[str, ...] = (
    'Такі безкоштовні вікна цінні не для колекції, а для чесної короткої проби.',
    'Це не постійне поповнення бібліотеки, а нормальний тест-драйв перед рішенням.',
    'Таке тимчасове відкриття зручне, коли гру давно хотілося перевірити без ризику.',
)

DISCOUNT_FOCUS_SUMMARY_TEMPLATES: tuple[str, ...] = (
    'Тут основа — {focus}.',
    'Найпростіше описати це через {focus}.',
    'Головне тут — {focus}.',
)

DISCOUNT_REVIEW_LED_SUMMARY_TEMPLATES: tuple[str, ...] = (
    'Один із тих тайтлів, де сильна репутація давно важливіша за будь-який шум.',
    'Це гра з уже сформованою репутацією, тож рішення тут частіше впирається саме в момент входу.',
    'Тут головний аргумент давно не пітч, а те, як гра тримається в очах спільноти.',
)

DISCOUNT_GENERIC_SUMMARY_TEMPLATES: tuple[str, ...] = (
    'Це міцна гра без потреби в довгому пітчі: головне тут у самому тайтлі.',
    'Такий реліз зазвичай повертають на радар не через шум, а через момент входу.',
    'Одна з тих пропозицій, де достатньо швидко звірити жанр і цінник зі своїм списком.',
)

EVENT_FOCUS_SUMMARY_TEMPLATES: tuple[str, ...] = (
    'Фокус тут — {focus}. Сторінку зручно пройти як короткий маршрут по ключових секціях фестивалю.',
    'У центрі фестивалю — {focus}. За кілька хвилин тут легко відмітити свої тайтли на потім.',
    'Тема цього вікна — {focus}. Його краще проходити точково: головні секції, кілька знахідок і далі без зайвого шуму.',
)

EVENT_GENERIC_SUMMARY_TEMPLATES: tuple[str, ...] = (
    'Такий фестиваль найкраще проходити точково: кількох хвилин вистачає, щоб відсікти зайве й лишити собі кілька знахідок.',
    'Це коротке тематичне вікно, яке краще читати через ключові секції, а не довгим суцільним скролом.',
    'Кількох хвилин тут уже досить, щоб перевірити головне й відкласти собі кілька тайтлів на потім.',
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

DISCOUNT_EDITORIAL_SUMMARY_MAX_LENGTH = 120
DISCOUNT_MARKETING_OPENING_RE = re.compile(
    r'^(?:відчуйте|пориньте|відкрийте|станьте|досліджуйте|вирушайте|керуйте|будуйте|створіть|очольте|розкрийте|прокладайте|боріться|підкорюйте)\b',
    re.IGNORECASE,
)
DISCOUNT_EDITORIAL_TITLE_OVERRIDES: tuple[tuple[str, str], ...] = (
    ('american truck simulator', 'Симулятор дальнобійника про американські траси, вантажі й довгі поїздки між штатами.'),
    ('euro truck simulator 2', 'Симулятор дальнобійника про європейські маршрути, рейси й довгі поїздки.'),
    ('far cry 5', 'Шутер у відкритому світі про культ у Монтані, перестрілки й кооп.'),
    ('assassin s creed origins', 'Екшен-RPG у Стародавньому Єгипті про витоки Братства асасинів.'),
    ('red dead redemption 2', 'Вестерн з відкритим світом і сильним сюжетним акцентом.'),
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
    CTA_ANTI_REPEAT_WINDOW = 4

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
        if offer.is_event:
            return 'festival'
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
        return style in {'alert', 'freebie', 'temporary_freebie', 'festival', 'first_price_move', 'recommend', 'finder'}

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
        return self._pick_phrase(
            pool,
            self._recent_ctas,
            f'cta|{style}|{key}',
            debug_label='cta',
            anti_repeat_window=self.CTA_ANTI_REPEAT_WINDOW,
        )

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
        if anti_repeat_window > 0 and debug_label in {'opening', 'cta'} and candidate_pool:
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
            if anti_repeat_window > 0 and debug_label in {'opening', 'cta'} and recent_window:
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
        if not offer.is_freebie:
            return self._build_steam_discount_caption_v2(title_line, offer, decision_json, copy, hashtags, voice)
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

    def _build_steam_discount_caption_v2(
        self,
        title_line: str,
        offer: Offer,
        decision_json: dict,
        copy: dict[str, str],
        hashtags: list[str],
        voice: YotoVoiceDecision,
    ) -> str:
        lines: list[str] = [title_line]
        body_lines: list[str] = []

        self._append_body_line(lines, body_lines, copy.get('summary', ''))
        self._append_body_line(lines, body_lines, self._build_steam_discount_value_line_v2(offer))
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
        summary_limit = min(max_length, self._summary_limit_for_offer(offer, voice))
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
            long_summary_limit=summary_limit,
            short_summary_limit=min(summary_limit, 110),
        )

        source_summary = self._pick_source_summary(offer, summary_limit)
        summary_fallback_used = not bool(source_summary)
        if source_summary:
            summary = source_summary
        else:
            summary = self._build_family_fallback_summary(offer, decision_json, voice, max_length=summary_limit)

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

        cleaned_summary = truncate_text(
            self._strip_redundant_title_prefix(summary, offer.title),
            max_length=summary_limit,
        )
        return {
            'summary': escape(cleaned_summary),
            'hook_line': escape(clean_html_text(hook_line)),
            'urgency_line': escape(clean_html_text(urgency_line)),
        }

    def _summary_limit_for_offer(self, offer: Offer, voice: YotoVoiceDecision) -> int:
        if offer.is_event:
            return 190
        if offer.is_freebie and voice.access_type == 'temporary_access':
            return 180
        if offer.is_freebie:
            return 170
        if voice.style in {'finder', 'recommend', 'first_price_move'} or offer.discount_percent >= 50:
            return 185
        return 180

    def _pick_source_summary(self, offer: Offer, max_length: int) -> str:
        for value in (offer.short_description, offer.description):
            summary = self._compact_source_summary(offer, str(value or ''), offer.title, max_length=max_length)
            if summary:
                return summary
        return ''

    def _compact_source_summary(self, offer: Offer, value: str, title: str, *, max_length: int) -> str:
        cleaned = self._sanitize_source_summary(value, title)
        if not cleaned:
            return ''
        if not offer.is_event and not offer.is_freebie:
            return self._compact_discount_source_summary(offer, cleaned, max_length=max_length)
        first_sentence = self._first_sentence(cleaned)
        if first_sentence and first_sentence != cleaned and 55 <= len(first_sentence) <= max_length:
            cleaned = first_sentence
        if not contains_cyrillic(cleaned):
            return ''
        return truncate_text(cleaned, max_length=max_length)

    def _compact_discount_source_summary(self, offer: Offer, cleaned: str, *, max_length: int) -> str:
        override = self._match_discount_editorial_summary(offer.title)
        if override:
            return truncate_text(override, max_length=min(max_length, DISCOUNT_EDITORIAL_SUMMARY_MAX_LENGTH))

        first_sentence = self._first_sentence(cleaned)
        candidate = first_sentence or cleaned
        if not contains_cyrillic(candidate):
            return ''

        if len(candidate) > min(max_length, DISCOUNT_EDITORIAL_SUMMARY_MAX_LENGTH):
            return ''
        if self._looks_like_discount_marketing_summary(candidate):
            return ''
        return candidate

    def _match_discount_editorial_summary(self, title: str) -> str:
        normalized_title = self._normalize_summary_key(title)
        for needle, summary in DISCOUNT_EDITORIAL_TITLE_OVERRIDES:
            if needle in normalized_title:
                return summary
        return ''

    def _looks_like_discount_marketing_summary(self, value: str) -> bool:
        normalized = self._normalize_summary_key(value)
        if not normalized:
            return False
        first_word = normalized.split(' ', 1)[0]
        return bool(
            DISCOUNT_MARKETING_OPENING_RE.match(normalized)
            or first_word.endswith(('йте', 'іть', 'іться', 'ться'))
        )

    def _sanitize_source_summary(self, value: str, title: str) -> str:
        cleaned = clean_html_text(value).strip()
        if not cleaned:
            return ''
        cleaned = self._strip_store_section_prefix(cleaned)
        cleaned = self._strip_store_summary_prefix(cleaned)
        cleaned = self._strip_redundant_title_prefix(cleaned, title)
        if not cleaned:
            return ''
        if any(marker in cleaned.casefold() for marker in SOURCE_SUMMARY_SECTION_MARKERS):
            return ''
        if not contains_cyrillic(cleaned):
            return ''
        return cleaned

    @staticmethod
    def _strip_store_section_prefix(value: str) -> str:
        cleaned = value.strip()
        for _ in range(3):
            lowered = cleaned.casefold()
            marker_match: tuple[int, int] | None = None
            for marker in SOURCE_SUMMARY_SECTION_MARKERS:
                index = lowered.find(marker)
                if index == -1 or index > 140:
                    continue
                candidate = (index, len(marker))
                if marker_match is None or candidate[0] < marker_match[0]:
                    marker_match = candidate
            if marker_match is None:
                break
            start, marker_length = marker_match
            cleaned = cleaned[start + marker_length :].lstrip(' :-—|')
        return cleaned

    @staticmethod
    def _strip_store_summary_prefix(value: str) -> str:
        cleaned = value.strip()
        for _ in range(3):
            updated = SOURCE_SUMMARY_PREFIX_RE.sub('', cleaned, count=1).lstrip(' :-—|')
            if updated == cleaned:
                break
            cleaned = updated
        return cleaned

    @staticmethod
    def _normalize_summary_key(value: str) -> str:
        normalized = re.sub(r'[^0-9a-zа-яіїєґ]+', ' ', str(value or '').casefold())
        return ' '.join(normalized.split())

    @staticmethod
    def _first_sentence(value: str) -> str:
        cleaned = clean_html_text(value).strip()
        if not cleaned:
            return ''
        for token in ('. ', '! ', '? '):
            if token in cleaned:
                return cleaned.split(token, 1)[0] + token.strip()
        return cleaned

    def _build_family_fallback_summary(
        self,
        offer: Offer,
        decision_json: dict,
        voice: YotoVoiceDecision,
        *,
        max_length: int,
    ) -> str:
        if offer.is_event:
            summary = self._build_event_fallback_summary(offer)
        elif offer.is_freebie:
            summary = self._build_freebie_fallback_summary(offer, voice.access_type)
        else:
            summary = self._build_discount_fallback_summary(offer, decision_json, voice)
        return truncate_text(summary, max_length=max_length)

    def _build_freebie_fallback_summary(self, offer: Offer, access_type: str | None) -> str:
        focus = build_focus_text(list(offer.tags), list(offer.genres))
        if access_type == 'temporary_access':
            if focus:
                return self._render_summary_template(
                    TEMPORARY_FREEBIE_FOCUS_SUMMARY_TEMPLATES,
                    f'temporary-freebie-focus|{offer.offer_id}|{focus}',
                    focus=focus,
                )
            return self._stable_variant(
                TEMPORARY_FREEBIE_GENERIC_SUMMARY_TEMPLATES,
                f'temporary-freebie-generic|{offer.offer_id}',
            )
        if focus:
            return self._render_summary_template(
                FREEBIE_FOCUS_SUMMARY_TEMPLATES,
                f'freebie-focus|{offer.offer_id}|{focus}',
                focus=focus,
            )
        return self._stable_variant(FREEBIE_GENERIC_SUMMARY_TEMPLATES, f'freebie-generic|{offer.offer_id}')

    def _build_discount_fallback_summary(
        self,
        offer: Offer,
        decision_json: dict,
        voice: YotoVoiceDecision,
    ) -> str:
        focus = build_focus_text(list(offer.tags), list(offer.genres))
        if focus:
            return self._render_summary_template(
                DISCOUNT_FOCUS_SUMMARY_TEMPLATES,
                f'discount-focus|{offer.offer_id}|{voice.style}|{focus}',
                focus=focus,
            )
        if (offer.review_score or 0) >= 85 and (offer.review_count or 0) >= 1500:
            return self._stable_variant(
                DISCOUNT_REVIEW_LED_SUMMARY_TEMPLATES,
                f'discount-review|{offer.offer_id}|{decision_json.get("lane")}|{voice.style}',
            )
        return self._stable_variant(
            DISCOUNT_GENERIC_SUMMARY_TEMPLATES,
            f'discount-generic|{offer.offer_id}|{decision_json.get("lane")}|{voice.style}',
        )

    def _build_event_fallback_summary(self, offer: Offer) -> str:
        focus = build_focus_text(list(offer.tags), list(offer.genres))
        if focus:
            return self._render_summary_template(
                EVENT_FOCUS_SUMMARY_TEMPLATES,
                f'festival-focus|{offer.offer_id}|{focus}',
                focus=focus,
            )
        return self._stable_variant(EVENT_GENERIC_SUMMARY_TEMPLATES, f'festival-generic|{offer.offer_id}')

    def _render_summary_template(self, templates: tuple[str, ...], key: str, **values: str) -> str:
        template = self._stable_variant(templates, key)
        return template.format(**values)

    def _stable_variant(self, templates: tuple[str, ...], key: str) -> str:
        if not templates:
            return ''
        index = int(self.voice_engine._stable_score(key) * len(templates)) % len(templates)
        return templates[index]

    def _build_caption_hook_line(
        self,
        offer: Offer,
        decision_json: dict,
        raw_hook: str,
        access_type: str | None,
    ) -> str:
        final_push = decision_json.get('lane') == 'final_push' or decision_json.get('is_final_push')
        focus = build_focus_text(list(offer.tags), list(offer.genres))
        if offer.is_event:
            if focus:
                return f'Фокус фестивалю — {focus}. Сторінку краще пройти точково, а не скролити все підряд.'
            return 'Це тематичне вікно, яке зручніше читати як коротку добірку, ніж як довгу вітрину.'
        if final_push:
            return 'Останнє вікно, щоб не проґавити цю пропозицію.'
        if offer.is_freebie:
            if access_type == 'temporary_access':
                return 'Безкоштовне вікно тут працює як короткий тест-драйв, а не як клейм про запас.'
            if offer.source.value == 'epic':
                return 'В Epic відкрили ще одну безкоштовну роздачу без зайвого шуму, але з нормальним приводом придивитися.'
            return 'У Steam відкрили безкоштовну роздачу, яку варто хоча б швидко звірити зі своїми смаками.'
        if offer.discount_percent >= 75:
            return 'Одна з найсильніших просадок ціни по цій грі просто зараз.'
        if offer.discount_percent >= 50:
            return 'Цінник уже просів достатньо, щоб гра повернулася в короткий список.'
        if offer.discount_percent > 0:
            return 'Ціна зрушила вниз настільки, що сторінку вже має сенс відкрити без поспіху.'
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
                return f'Вікно фестивалю — до {deadline}.'
            if offer.is_freebie:
                if access_type == 'temporary_access':
                    return f'Безкоштовний доступ відкритий до {deadline}.'
                return f'Роздача відкрита до {deadline}.'
            return f'Цей цінник тримається до {deadline}.'
        if final_push:
            return 'Фінальний шанс: пропозиція вже на останній прямій.'
        if offer.is_event:
            return 'Фестиваль уже триває, тож сторінку краще пройти одним заходом.'
        if offer.is_freebie:
            if access_type == 'temporary_access':
                return 'Безкоштовний доступ уже відкритий.'
            return 'Роздача вже відкрита.'
        return normalized_raw
    @staticmethod
    def _strip_redundant_title_prefix(summary: str, title: str) -> str:
        normalized_summary = clean_html_text(summary).strip()
        normalized_title = clean_html_text(title).strip()
        if not normalized_summary or not normalized_title:
            return normalized_summary
        for _ in range(3):
            if not normalized_summary.casefold().startswith(normalized_title.casefold()):
                break
            remainder = normalized_summary[len(normalized_title):].lstrip(' —-:,.')
            if not remainder:
                return normalized_summary
            normalized_summary = remainder[0].upper() + remainder[1:]
        return normalized_summary

    @staticmethod
    def _capitalize_fragment(value: str) -> str:
        if not value:
            return value
        return value[0].upper() + value[1:]

    def _build_steam_discount_value_line_v2(self, offer: Offer) -> str:
        now_price = 'Безплатно' if offer.price_after_minor == 0 else self._format_minor(offer.price_after_minor)
        old_price = self._format_minor(offer.price_before_minor)
        if now_price != 'невідомо' and old_price != 'невідомо':
            savings = self._format_minor(max((offer.price_before_minor or 0) - (offer.price_after_minor or 0), 0))
            if offer.discount_percent > 0:
                return f'Зараз {now_price} замість {old_price} (-{offer.discount_percent}%, економія {savings}).'
            return f'Зараз {now_price} замість {old_price}.'
        if now_price != 'невідомо':
            return f'Зараз {now_price}.'
        if old_price != 'невідомо':
            return f'Попередня ціна — {old_price}.'
        return ''

    def _build_steam_value_line(self, offer: Offer, voice: YotoVoiceDecision) -> str:
        if offer.is_freebie:
            before = self._format_minor(offer.price_before_minor)
            if voice.access_type == 'temporary_access':
                if before != 'невідомо':
                    return (
                        f'Замість {before} зараз можна '
                        f'<a href="{self._link(offer.store_url)}"><b>зіграти безкоштовно</b></a>; доступ тимчасовий.'
                    )
                return (
                    f'Зараз у гру можна '
                    f'<a href="{self._link(offer.store_url)}"><b>зіграти безкоштовно</b></a>; доступ тимчасовий.'
                )
            if before != 'невідомо':
                return (
                    f'Зараз <a href="{self._link(offer.store_url)}"><b>0 грн</b></a> '
                    f'замість {before}; після додавання гра лишається в бібліотеці.'
                )
            return (
                f'Зараз <a href="{self._link(offer.store_url)}"><b>0 грн</b></a>; '
                'після додавання гра лишається в бібліотеці.'
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
                return f'Замість {before} гру зараз можна спокійно спробувати без покупки; доступ тимчасовий.'
            return 'Гру зараз можна безкоштовно спробувати; доступ тимчасовий.'
        if before != 'невідомо':
            return f'Зараз у Epic — 0 грн замість {before}; після додавання гра лишається на акаунті.'
        return 'Зараз у Epic — 0 грн; після додавання гра лишається на акаунті.'

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
            return 'Почніть із верхівки сторінки та ключових секцій: цього вистачить, щоб швидко відмітити своє.'
        if offer.is_freebie:
            if voice.access_type == 'temporary_access':
                return 'Якщо гра давно була на радарі, це вікно краще використати як швидкий тест, а не відкладати.'
            return 'Якщо гра вам підходить, одного швидкого кліку до закриття роздачі тут достатньо.'
        if final_push:
            return 'Якщо хотів(ла) взяти саме в цю акцію — краще не тягнути.'
        if decision_json.get('lane') == 'game_of_the_day':
            return 'Нормальна точка входу, якщо давно хотів(ла) спробувати.'
        return 'Якщо давно була в бажаному — це хороший момент.'
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
        reviews_short = format_compact_review_count(offer.review_count)
        if offer.review_score is not None and reviews_short:
            return f'{offer.review_score}% позитивних • {reviews_short} відгуків'
        if offer.review_score is not None:
            return f'{offer.review_score}% позитивних'
        if reviews_short:
            return f'{reviews_short} відгуків'
        return ''

    @staticmethod
    def _build_achievements_bit(count: int | None) -> str:
        if not count or count <= 0:
            return ''
        return f'{count} досягнень'

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
        with_space_after = re.sub(r'(?<=\d)\. (?=\d)', '.', with_space_after)
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
        lane = decision_json.get('lane')
        if offer.source.value == 'steam' and not offer.is_freebie:
            hashtags.extend(['#steam', '#steamsale'])
            if lane == 'game_of_the_day':
                hashtags.append('#gameday')
            if lane == 'final_push' or decision_json.get('is_final_push'):
                hashtags.append('#finalpush')
            return hashtags

        if offer.source.value == 'steam':
            hashtags.extend(['#steam', '#freegame'])
        elif offer.source.value == 'epic':
            hashtags.extend(['#epicgames', '#freegame', '#giveaway'])
        else:
            hashtags.extend(['#steam', '#festival', '#gaming'])

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








