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
        intro = f'{voice.opening_line} {self._intro(roundup)}'.strip()
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
            return self._with_part('Що взяти зі знижок просто зараз', part_suffix)
        if roundup.group_type == 'strong_discount':
            return self._with_part('Сильні знижки без зайвого шуму', part_suffix)
        if roundup.group_type == 'freebie':
            return self._with_part('Безкоштовні роздачі, які ще можна забрати', part_suffix)
        if roundup.group_type == 'genre':
            return self._with_part(f'{roundup.theme_label}: тематична добірка зі знижок', part_suffix)
        if roundup.group_type == 'tag':
            return self._with_part(f'{roundup.theme_label}: короткий редакторський список', part_suffix)
        return self._with_part('Що ще варте швидкої перевірки', part_suffix)

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
            pool = (
                'Тут не весь сейл підряд, а кілька позицій, де знижка вже сама тягне на окреме відкриття.',
                'Це короткий зріз по великих тайтлах, у яких цінник уже говорить голосніше за будь-який пітч.',
                'Цю верхівку зібрано як редакторський маршрут по сильних входах у великий сейл.',
                'Список із тих тайтлів, де момент входу вже виглядає достатньо сильним без зайвих пояснень.',
            )
        elif roundup.group_type == 'strong_discount':
            pool = (
                'Це не другий список за інерцією, а щільна добірка позицій, які легко пропустити без окремого проходу.',
                'Тут зібрані не випадкові залишки сейлу, а міцні ціни, що заслуговують на власне коротке вікно.',
                'Після головних хедлайнерів саме тут часто ховається найприємніша робоча серія знижок.',
                'Добірка для тих, хто вже бачив вітрину і хоче ще кілька справді переконливих цін.',
            )
        elif roundup.group_type == 'freebie':
            pool = (
                'Тут не календар нулів підряд, а кілька безкоштовностей, які мають сенс пройти одним заходом.',
                'Це короткий список безкоштовних роздач, де є нормальний привід не відкладати швидку звірку.',
                'Добірка для тих, хто хоче подивитися не все безкоштовне підряд, а тільки робочі слоти.',
                'Зібрали ті роздачі, які краще перевірити зараз, ніж випадково згадати про них запізно.',
            )
        elif roundup.group_type == 'genre':
            pool = (
                f'Тут не вся тема {roundup.theme_label} підряд, а короткий список позицій, які найкраще тримають цей напрям зараз.',
                f'Це тематична добірка по {roundup.theme_label}, зібрана для швидкого проходу без зайвого шуму.',
                f'Список по {roundup.theme_label}, де зручно відразу відсікти своє, а не тонути в масиві схожих сторінок.',
                f'{roundup.item_count} позицій по {roundup.theme_label}, які справді варто звести в один короткий маршрут.',
            )
        elif roundup.group_type == 'tag':
            pool = (
                f'Тема {roundup.theme_label} тут зібрана не для маси, а як короткий редакторський список.',
                f'Це редакторська добірка по {roundup.theme_label}, яку зручно пройти одним заходом і швидко відсікти своє.',
                f'Навколо {roundup.theme_label} тут лишили тільки ті позиції, які тягнуть на окрему перевірку.',
                f'Короткий список по {roundup.theme_label}, де важливі не кількість, а точність відбору.',
            )
        else:
            pool = (
                'Це не технічний хвіст стрічки, а коротка дорізка з того, що ще тримається без статусу хедлайнера.',
                'Після головних слотів лишається ще кілька позицій, яким варто дати окремий короткий прохід.',
                'Тут зібрано не все, що залишилося, а те, що все ще має привід на швидке окреме відкриття.',
                'Це короткий додатковий список поверх основної вітрини: лише те, що ще тримається.',
            )
        return self._stable_variant(pool, f'roundup-intro|{roundup.roundup_id}|{roundup.group_type}')

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
            qualifier = self._editorial_signal(roundup, item)
            if qualifier:
                return f'безкоштовно в {store_label}, {qualifier}'
            return f'безкоштовно в {store_label}'

        core = self._discount_signal(item)
        qualifier = self._editorial_signal(roundup, item)
        if core and qualifier:
            return f'{core}, {qualifier}'
        if core:
            return core
        if qualifier:
            return qualifier
        return 'деталі вже на сторінці'

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
                'Почніть із верхніх позицій і відмітьте своє, поки вікно ще відкрите.',
                'Цей список краще пройти одним заходом: у безкоштовностей тут головна цінність саме в таймінгу.',
                voice_closing,
            )
        elif roundup.group_type == 'hero_discount':
            pool = (
                'Якщо відкривати лише кілька сторінок, починайте з верхівки: порядок тут не випадковий.',
                'Верхні позиції тут уже відсіяні як головний маршрут по цій добірці.',
                voice_closing,
            )
        elif roundup.group_type == 'strong_discount':
            pool = (
                'Силу цього списку краще читати серією: швидко пройдіть усі позиції зверху вниз.',
                'Тут працює саме щільність добірки, тож не зупиняйтеся на одному тайтлі.',
                voice_closing,
            )
        elif roundup.group_type in {'genre', 'tag'}:
            pool = (
                'Якщо тема ваша, йдіть зверху вниз і лишайте тільки ті сторінки, що реально потрапляють у смак.',
                'Цей список найкраще працює як короткий тематичний маршрут без довгого зависання.',
                voice_closing,
            )
        else:
            pool = (
                'Пройдіть список зверху вниз як коротку дорізку до основної вітрини.',
                'Тут сенс у швидких точкових відкриттях, а не в довгому скролі по кожній позиції.',
                voice_closing,
            )
        return self._stable_variant(pool, f'roundup-cta|{roundup.roundup_id}|{roundup.group_type}')

    def _hashtags(self, roundup: RoundupPost) -> list[str]:
        hashtags = ['#toplist']
        if roundup.group_type == 'freebie':
            hashtags.append('#freegame')
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

