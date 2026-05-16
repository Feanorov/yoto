from __future__ import annotations

from html import escape
import re

from domain.entities.roundup_post import RoundupItem, RoundupPost, RoundupTelegramDraft
from infrastructure.telegram.caption_builder import YotoVoiceEngine


class TelegramRoundupDraftBuilder:
    def __init__(self, voice_engine: YotoVoiceEngine | None = None) -> None:
        self.voice_engine = voice_engine or YotoVoiceEngine()

    def build(self, roundup: RoundupPost) -> RoundupTelegramDraft:
        title = self._title(roundup)
        voice = self.voice_engine.select_roundup_voice(roundup)
        intro = self._intro(roundup)
        item_lines = [self._item_line(roundup, item) for item in roundup.items]
        closing_cta = self._closing_cta(roundup, voice.closing_cta)
        hashtags = self._hashtags(roundup)
        parts = [f'<b>{escape(title)}</b>', escape(intro), '\n'.join(item_lines)]
        if closing_cta:
            parts.append(escape(closing_cta))
        if hashtags:
            parts.append(' '.join(hashtags))
        caption_html = '\n\n'.join(part for part in parts if part)
        return RoundupTelegramDraft(
            title=title,
            intro=intro,
            item_lines=item_lines,
            closing_cta=closing_cta,
            caption_html=caption_html,
        )

    def _title(self, roundup: RoundupPost) -> str:
        part_suffix = self._part_suffix(roundup.title)
        if roundup.group_type == 'hero_discount':
            return self._with_part('🔥 Що взяти зі знижок: коротка добірка', part_suffix)
        if roundup.group_type == 'strong_discount':
            return self._with_part('🔥 Сильні знижки: коротка добірка', part_suffix)
        if roundup.group_type == 'freebie':
            return self._with_part('🎁 Безкоштовні ігри: коротка добірка', part_suffix)
        if roundup.group_type == 'genre':
            return self._with_part(f'🔥 {roundup.theme_label}: коротка добірка', part_suffix)
        if roundup.group_type == 'tag':
            return self._with_part(f'🔥 {roundup.theme_label}: коротка добірка', part_suffix)
        return self._with_part('🔥 Що ще подивитися: коротка добірка', part_suffix)

    @staticmethod
    def _with_part(title: str, part_suffix: str) -> str:
        if not part_suffix:
            return title
        return f'{title}, {part_suffix}'

    @staticmethod
    def _part_suffix(source_title: str) -> str:
        match = re.search(r'Part\s+(\d+)', source_title or '')
        if not match:
            return ''
        return f'частина {match.group(1)}'

    def _intro(self, roundup: RoundupPost) -> str:
        if roundup.group_type == 'hero_discount':
            return 'Кілька великих знижок, з яких зручно почати прямо зараз.'
        if roundup.group_type == 'strong_discount':
            return 'Кілька помітних знижок, які зараз виглядають найцікавіше.'
        if roundup.group_type == 'freebie':
            return f'Зараз можна забрати {roundup.item_count} безплатні ігри{self._freebie_source_suffix(roundup)}.'
        if roundup.group_type in {'genre', 'tag'}:
            return f'Кілька ігор у темі {roundup.theme_label}, які зараз виглядають найцікавіше.'
        return 'Кілька позицій, які ще варто швидко перевірити.'

    @staticmethod
    def _freebie_source_suffix(roundup: RoundupPost) -> str:
        sources = {item.source for item in roundup.items if item.source}
        if sources == {'epic'}:
            return ' в Epic'
        if sources == {'steam'}:
            return ' у Steam'
        if sources == {'epic', 'steam'}:
            return ' в Epic і Steam'
        return ''

    def _item_line(self, roundup: RoundupPost, item: RoundupItem) -> str:
        title_html = self._title_html(item)
        value_signal = escape(self._value_signal(roundup, item))
        if not value_signal:
            return f'{item.rank}. {title_html}'
        return f'{item.rank}. {title_html} — {value_signal}'

    @staticmethod
    def _title_html(item: RoundupItem) -> str:
        title = escape(item.title)
        if not item.store_url:
            return f'<b>{title}</b>'
        return f'<a href="{escape(item.store_url, quote=True)}"><b>{title}</b></a>'

    def _value_signal(self, roundup: RoundupPost, item: RoundupItem) -> str:
        if item.is_freebie:
            store_label = 'Epic' if item.source == 'epic' else 'Steam'
            return f'безплатно в {store_label}'

        core = self._discount_signal(item)
        review_signal = self._review_signal(item.review_score)
        if core and review_signal:
            return f'{core}, {review_signal}'
        if core:
            return core
        if review_signal:
            return review_signal
        return 'деталі вже на сторінці'

    def _discount_signal(self, item: RoundupItem) -> str:
        discount = f'-{item.discount_percent}%' if item.discount_percent > 0 else ''
        price = ''
        if item.price_after_minor is not None:
            price = f'до {self._format_minor(item.price_after_minor)}'
        if discount and price:
            return f'{discount} {price}'
        if discount:
            return discount
        if price:
            return price
        return ''

    @staticmethod
    def _review_signal(review_score: int | None) -> str:
        if review_score is None:
            return ''
        return f'{review_score}% позитивних'

    def _editorial_signal(self, roundup: RoundupPost, item: RoundupItem) -> str:
        reasons = set(item.reason_tags)
        if 'editorial_importance:standout_title' in reasons:
            return 'велике ім’я добірки'
        if 'editorial_importance:major_franchise' in reasons:
            return 'сильний франчайз у цій ціні'
        if 'editorial_importance:critical_favorite' in reasons:
            return 'критичний фаворит'
        if 'editorial_importance:mega_popular' in reasons:
            if item.discount_percent >= 60:
                return 'великий хіт у сильній ціні'
            return 'великий хіт'
        if 'editorial_importance:very_popular' in reasons:
            if item.discount_percent >= 70:
                return 'помітний хіт у сильній ціні'
            return 'помітний хіт'
        if 'editorial_importance:trusted_hit' in reasons:
            return 'перевірений хіт'
        if 'editorial_importance:highly_rated' in reasons and item.review_score is not None:
            return f'рейтинг {item.review_score}%'
        if 'editorial_importance:highly_rated' in reasons:
            return 'сильний рейтинг'
        if 'freebie_roundup_candidate' in reasons:
            return 'варте швидкої звірки'
        if 'freebie_low_signal' in reasons:
            return 'нішевий, але робочий слот'
        if item.rank == 1 and roundup.group_type in {'hero_discount', 'strong_discount'} and not item.is_freebie:
            return 'верхівка добірки'
        if 'hero_discount' in reasons:
            return 'верхівка добірки'
        if 'strong_discount' in reasons:
            return 'щільна знижка другого ряду'
        if 'roundup_discount' in reasons:
            return 'точка для швидкої звірки'
        if item.review_score is not None and item.review_score >= 80:
            return f'рейтинг {item.review_score}%'
        return ''

    @staticmethod
    def _format_minor(value: int) -> str:
        amount = value / 100
        if amount.is_integer():
            return f'{int(amount)} грн'
        return f'{amount:.2f} грн'

    def _closing_cta(self, roundup: RoundupPost, voice_closing: str) -> str:
        if roundup.group_type == 'freebie':
            pool = (
                'Якщо щось цікаве — краще забрати одразу, поки роздача активна.',
                voice_closing,
            )
        elif roundup.group_type == 'hero_discount':
            pool = (
                'Якщо щось цікаве — почніть із перших позицій.',
                voice_closing,
            )
        elif roundup.group_type == 'strong_discount':
            pool = (
                'Якщо щось цікаве — краще відкрити це зараз, поки ціни активні.',
                voice_closing,
            )
        elif roundup.group_type in {'genre', 'tag'}:
            pool = (
                'Якщо тема ваша — відкрийте кілька перших позицій і відсійте своє.',
                voice_closing,
            )
        else:
            pool = (
                'Якщо щось зачепило — кілька перших позицій уже дають головне.',
                voice_closing,
            )
        return self._stable_variant(pool, f'roundup-cta|{roundup.roundup_id}|{roundup.group_type}')

    def _hashtags(self, roundup: RoundupPost) -> list[str]:
        hashtags = ['#toplist']
        if roundup.group_type == 'freebie':
            hashtags.append('#freegames')
        else:
            hashtags.append('#steamsale')

        sources = {item.source for item in roundup.items if item.source}
        if len(sources) == 1:
            source = next(iter(sources))
            if source == 'steam':
                hashtags.append('#steam')
            elif source == 'epic':
                hashtags.append('#epicgames')
        return hashtags

    def _stable_variant(self, values: tuple[str, ...], key: str) -> str:
        filtered = tuple(value for value in values if value)
        if not filtered:
            return ''
        index = int(self.voice_engine._stable_score(key) * len(filtered)) % len(filtered)
        return filtered[index]

