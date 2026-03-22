from __future__ import annotations

from html import escape

from .models import Offer, PostKind
from .utils.ua import build_fallback_summary, clean_html_text, contains_cyrillic, format_deadline, format_price_uah, truncate_text


TAG_MAP = {
    "action": "#action",
    "екшен": "#action",
    "adventure": "#adventure",
    "пригод": "#adventure",
    "rpg": "#rpg",
    "рольова": "#rpg",
    "strategy": "#strategy",
    "стратег": "#strategy",
    "simulation": "#simulation",
    "симулятор": "#simulation",
    "indie": "#indie",
    "horror": "#horror",
    "survival": "#survival",
    "гонки": "#racing",
    "racing": "#racing",
    "sports": "#sports",
    "кооп": "#coop",
    "coop": "#coop",
    "multiplayer": "#multiplayer",
    "open world": "#openworld",
    "roguelike": "#roguelike",
}

EPIC_GENERIC_SUMMARY = "Роздача в Epic Games Store. Гру можна додати до бібліотеки безкоштовно, поки акція активна."


def build_caption(offer: Offer) -> str:
    if offer.source.value == "epic":
        return build_epic_caption(offer)
    if offer.source.value == "event":
        return build_event_caption(offer)
    return build_steam_caption(offer)


def build_steam_caption(offer: Offer) -> str:
    prefix = "🎮" if offer.post_kind == PostKind.GAME_OF_DAY else ("🎁" if offer.is_free_to_keep else "🔥")
    headline = f"{prefix} <b>{escape(offer.title)}</b>"
    summary = pick_summary(offer)
    body: list[str] = [headline, summary]

    if offer.post_kind == PostKind.GAME_OF_DAY:
        body.append("Гра дня у Steam: сильна безкоштовна роздача, яку варто забрати зараз.")
    elif offer.is_free_to_keep:
        body.append("Роздача у Steam: гру можна додати до бібліотеки безкоштовно, поки акція активна.")
    else:
        price_line = f"Зараз <b>{format_price_uah(offer.final_price_uah)}</b> замість {format_price_uah(offer.original_price_uah)}."
        body.append(f"Спеціальна акція у Steam: знижка <b>-{offer.discount_pct}%</b>. {price_line}")

    if offer.improvement_note:
        body.append(offer.improvement_note)

    deadline = format_deadline(offer.sale_end)
    if deadline:
        body.append(f"Акція діє до <b>{deadline}</b>.")

    if offer.has_trading_cards:
        body.append("Дає колекційний значок 🏅")

    if offer.achievements_count and offer.achievements_count > 0:
        body.append(f"Досягнення: {offer.achievements_count} шт.")
    else:
        body.append("Досягнення у Steam не знайдені.")

    if offer.review_summary:
        body.append(f"Відгуки: {escape(offer.review_summary)}")

    body.append(f'<a href="{escape(offer.url)}">Відкрити у Steam</a>')
    body.append(" ".join(build_hashtags(offer)))
    return "\n\n".join(line for line in body if line)


def build_epic_caption(offer: Offer) -> str:
    summary = pick_summary(offer)
    body = [f"🎁 <b>{escape(offer.title)}</b>"]
    if summary and summary != EPIC_GENERIC_SUMMARY:
        body.append(summary)
    body.append("Роздача в Epic Games Store. Гру можна забрати безкоштовно до завершення акції.")
    deadline = format_deadline(offer.sale_end)
    if deadline:
        body.append(f"Акція триває до <b>{deadline}</b>.")
    body.append(f'<a href="{escape(offer.url)}">Забрати в Epic Games Store</a>')
    body.append(" ".join(build_hashtags(offer)))
    return "\n\n".join(line for line in body if line)


def build_event_caption(offer: Offer) -> str:
    summary = pick_summary(offer)
    body = [f"🔥 <b>{escape(offer.title)}</b>", summary]
    deadline = format_deadline(offer.sale_end)
    if deadline:
        body.append(f"Подія активна до <b>{deadline}</b>.")
    body.append(f'<a href="{escape(offer.url)}">Переглянути сторінку події</a>')
    body.append(" ".join(build_hashtags(offer)))
    return "\n\n".join(line for line in body if line)


def pick_summary(offer: Offer) -> str:
    text = clean_html_text(offer.short_description or offer.description)
    if not text or not contains_cyrillic(text):
        if offer.source.value == "epic":
            text = EPIC_GENERIC_SUMMARY
        else:
            text = build_fallback_summary(offer.title, offer.genres, offer.tags, offer.is_free_to_keep)
    return escape(truncate_text(text))


def build_hashtags(offer: Offer) -> list[str]:
    hashtags: list[str] = []
    if offer.source.value == "steam":
        hashtags.extend(["#steam", "#freegame" if offer.is_free_to_keep else "#steamsale"])
    elif offer.source.value == "epic":
        hashtags.extend(["#epicgames", "#freegame", "#giveaway"])
    else:
        hashtags.extend(["#steam", "#festival", "#gaming"])

    if offer.post_kind == PostKind.GAME_OF_DAY:
        hashtags.append("#gameday")

    for raw in offer.tags + offer.genres:
        normalized = raw.strip().lower()
        for key, tag in TAG_MAP.items():
            if key in normalized and tag not in hashtags:
                hashtags.append(tag)
                break
        if len(hashtags) >= 7:
            break
    return hashtags[:7]
