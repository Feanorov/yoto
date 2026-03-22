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
        base_intro = self._intro(roundup)
        voice = self.voice_engine.select_roundup_voice(roundup)
        intro = f'{voice.opening_line} {base_intro}'.strip()
        item_lines = [self._item_line(item) for item in roundup.items]
        closing_cta = self._closing_cta(roundup)
        parts = [f'<b>{escape(title)}</b>', escape(intro), '\n'.join(item_lines)]
        if closing_cta:
            parts.append(escape(closing_cta))
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
            return self._with_part('Що взяти зі знижок просто зараз', part_suffix)
        if roundup.group_type == 'strong_discount':
            return self._with_part('Сильні знижки, які варто перевірити', part_suffix)
        if roundup.group_type == 'freebie':
            return self._with_part('Безкоштовні роздачі, які ще можна забрати', part_suffix)
        if roundup.group_type == 'genre':
            return self._with_part(f'{roundup.theme_label}: добірка знижок', part_suffix)
        if roundup.group_type == 'tag':
            return self._with_part(f'{roundup.theme_label}: що варте уваги', part_suffix)
        return self._with_part('Що ще варте уваги в резерві', part_suffix)

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
            return 'Зібрали найсильніші резервні знижки цього вікна: тут є і великі імена, і справді сильні пропозиції, які не хочеться втрачати у резерві.'
        if roundup.group_type == 'strong_discount':
            return 'Ці пропозиції трохи спокійніші за головні герої-пости, але разом складаються у дуже міцну добірку.'
        if roundup.group_type == 'freebie':
            return 'Кілька безкоштовних роздач, які краще забрати одним списком, поки вони ще активні.'
        if roundup.group_type == 'genre':
            return f'У цьому наборі {roundup.item_count} близьких за темою пропозицій, які зручно переглянути одним постом.'
        if roundup.group_type == 'tag':
            return f'Зібрали пропозиції навколо теми {roundup.theme_label}, щоб швидко пройтися по найцікавішому без зайвого шуму.'
        return 'Зібрали найкращі резервні пропозиції поточного вікна в один компактний roundup.'

    def _item_line(self, item: RoundupItem) -> str:
        title_html = self._title_html(item)
        value_signal = escape(self._value_signal(item))
        return f'{item.rank}. {title_html} - {value_signal}'

    @staticmethod
    def _title_html(item: RoundupItem) -> str:
        title = escape(item.title)
        if not item.store_url:
            return f'<b>{title}</b>'
        return f'<a href="{escape(item.store_url, quote=True)}"><b>{title}</b></a>'

    def _value_signal(self, item: RoundupItem) -> str:
        if item.is_freebie:
            store_label = 'Epic' if item.source == 'epic' else 'Steam'
            qualifier = self._editorial_signal(item)
            if qualifier:
                return f'безкоштовно в {store_label}, {qualifier}'
            return f'безкоштовно в {store_label}'

        core = self._discount_signal(item)
        qualifier = self._editorial_signal(item)
        if core and qualifier:
            return f'{core}, {qualifier}'
        if core:
            return core
        if qualifier:
            return qualifier
        return 'деталі ціни вже на сторінці'

    def _discount_signal(self, item: RoundupItem) -> str:
        discount = f'{item.discount_percent}%' if item.discount_percent > 0 else ''
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

    def _editorial_signal(self, item: RoundupItem) -> str:
        reasons = set(item.reason_tags)
        if 'editorial_importance:standout_title' in reasons:
            return 'знаковий хіт'
        if 'editorial_importance:major_franchise' in reasons:
            return 'сильний франчайз'
        if 'editorial_importance:critical_favorite' in reasons:
            return 'критичний фаворит'
        if 'editorial_importance:mega_popular' in reasons:
            return 'дуже популярна гра'
        if 'editorial_importance:very_popular' in reasons:
            return 'помітний хіт'
        if 'editorial_importance:trusted_hit' in reasons:
            return 'перевірений хіт'
        if 'editorial_importance:highly_rated' in reasons:
            return 'високий рейтинг'
        if 'freebie_roundup_candidate' in reasons:
            return 'варта уваги'
        if 'freebie_low_signal' in reasons:
            return 'не найгучніша, але може зайти'
        if item.review_score is not None and item.review_score >= 90:
            return f'рейтинг {item.review_score}%'
        if item.review_score is not None and item.review_score >= 80:
            return f'рейтинг {item.review_score}%'
        if 'hero_discount' in reasons:
            return 'топ резерву'
        if 'strong_discount' in reasons:
            return 'сильна другорядна знижка'
        if 'roundup_discount' in reasons:
            return 'добрий кандидат для добірки'
        return ''

    @staticmethod
    def _format_minor(value: int) -> str:
        amount = value / 100
        if amount.is_integer():
            return f'{int(amount)} грн'
        return f'{amount:.2f} грн'

    def _closing_cta(self, roundup: RoundupPost) -> str:
        if roundup.group_type == 'freebie':
            return 'Забирайте, поки роздачі активні, і пишіть, що з цього вже летить у вашу бібліотеку.'
        if roundup.group_type == 'hero_discount':
            return 'Якщо з цієї добірки брати щось першим, пишіть у коментарях, що забрали б одразу.'
        if roundup.group_type == 'strong_discount':
            return 'Пишіть, яка з цих знижок для вас недооцінена найбільше.'
        if roundup.group_type in {'genre', 'tag'}:
            return 'Якщо хочете ще добірки в такому форматі, можна розгорнути окремо ще один тематичний список.'
        return 'Якщо треба, з цього резерву можна окремо розібрати ще одну добірку під інший настрій.'
