from __future__ import annotations

from datetime import datetime
import html
import re


UKRAINIAN_MONTHS = {
    1: "січня",
    2: "лютого",
    3: "березня",
    4: "квітня",
    5: "травня",
    6: "червня",
    7: "липня",
    8: "серпня",
    9: "вересня",
    10: "жовтня",
    11: "листопада",
    12: "грудня",
}


GENRE_FALLBACKS = {
    "Action": "екшени",
    "Adventure": "пригодницькі ігри",
    "RPG": "рольові ігри",
    "Strategy": "стратегії",
    "Simulation": "симулятори",
    "Indie": "інді-ігри",
    "Casual": "казуальні ігри",
    "Racing": "перегони",
    "Sports": "спортивні ігри",
    "Free To Play": "free-to-play проєкти",
}
SOURCE_LABELS = {
    "steam": "Steam",
    "epic": "Epic Games Store",
    "event": "Steam",
}

FOCUS_TRANSLATIONS = (
    ("co op", "кооператив"),
    ("coop", "кооператив"),
    ("co-op", "кооператив"),
    ("кооп", "кооператив"),
    ("кооператив", "кооператив"),
    ("multiplayer", "мультиплеєр"),
    ("open world", "відкритий світ"),
    ("відкрит", "відкритий світ"),
    ("roguelite", "рогалик"),
    ("roguelike", "рогалик"),
    ("рогалик", "рогалик"),
    ("deckbuilder", "карткові бої"),
    ("deck building", "карткові бої"),
    ("shooter", "шутер"),
    ("strategy", "стратегія"),
    ("стратег", "стратегія"),
    ("simulation", "симулятор"),
    ("симулятор", "симулятор"),
    ("adventure", "пригоди"),
    ("пригод", "пригоди"),
    ("action", "екшен"),
    ("екшен", "екшен"),
    ("rpg", "рольова гра"),
    ("role playing", "рольова гра"),
    ("survival", "виживання"),
    ("вижив", "виживання"),
    ("horror", "горор"),
    ("sports", "спорт"),
    ("спорт", "спорт"),
    ("racing", "перегони"),
    ("перегон", "перегони"),
    ("indie", "інді"),
    ("factory", "фабрики"),
    ("city builder", "містобудування"),
    ("tower defense", "тауер-дефенс"),
    ("visual novel", "візуальні новели"),
    ("puzzle", "головоломки"),
    ("stealth", "стелс"),
    ("magic", "магія"),
    ("tactical", "тактика"),
    ("tactics", "тактика"),
    ("story rich", "сюжет"),
    ("narrative", "сюжет"),
    ("turn based", "покрокова тактика"),
    ("soulslike", "соулслайк"),
    ("metroidvania", "метроїдванія"),
    ("sandbox", "пісочниця"),
    ("craft", "крафт"),
)

JUNK_FOCUS_TOKENS = {
    "freegames",
    "free games",
    "game",
    "games",
    "edition",
    "editions",
    "standard edition",
    "deluxe edition",
    "ultimate edition",
    "complete edition",
    "bundle",
    "bundles",
    "pack",
    "packs",
    "collection",
    "collections",
    "event",
    "events",
    "festival",
    "sale",
    "sales",
    "discount",
    "discounts",
    "promo",
    "promotion",
    "offer",
    "offers",
    "steam",
    "epic",
    "store",
    "store page",
    "franchise",
    "catalog",
    "library",
    "dlc",
    "soundtrack",
    "demo",
    "giveaway",
    "freebie",
}


def clean_html_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def contains_cyrillic(value: str) -> bool:
    return bool(re.search(r"[А-Яа-яІіЇїЄєҐґ]", value or ""))


def truncate_text(value: str, max_length: int = 340) -> str:
    text = clean_html_text(value)
    if len(text) <= max_length:
        return text
    sentence_break = max(text.rfind(". ", 0, max_length), text.rfind("! ", 0, max_length), text.rfind("? ", 0, max_length))
    if sentence_break > 120:
        return text[: sentence_break + 1].strip()
    word_break = text.rfind(" ", 0, max_length - 1)
    if word_break < 40:
        word_break = max_length
    return text[:word_break].rstrip(" ,;:-") + "..."


def ua_join(items: list[str]) -> str:
    cleaned = [item.strip() for item in items if item and item.strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} та {cleaned[1]}"
    return f"{', '.join(cleaned[:-1])} та {cleaned[-1]}"


def format_deadline(value: datetime | None) -> str | None:
    if value is None:
        return None
    return f"{value.day} {UKRAINIAN_MONTHS[value.month]} {value.year}, {value:%H:%M}"


def format_price_uah(value: float | None) -> str:
    if value is None:
        return "невідомо"
    rounded = round(value, 2)
    if float(int(rounded)) == rounded:
        return f"{int(rounded)} грн"
    return f"{rounded:.2f} грн"


def format_compact_review_count(value: int | None) -> str:
    if value is None:
        return ""
    count = max(int(value), 0)
    if count < 1000:
        return str(count)
    if count < 10_000:
        return f"{count // 100 / 10:.1f}к+"
    if count < 1_000_000:
        return f"{count // 1000}к+"
    return f"{count // 100_000 / 10:.1f}м+"


def build_fallback_summary(
    title: str,
    genres: list[str],
    tags: list[str],
    is_free: bool,
    *,
    source: str = "steam",
    is_event: bool = False,
    discount_percent: int = 0,
) -> str:
    safe_title = clean_html_text(title) or "Гра"
    source_label = SOURCE_LABELS.get((source or "").strip().lower(), "Steam")
    focus = _build_focus_text(tags, genres)
    genre_bits: list[str] = []
    for genre in genres[:3]:
        cleaned = clean_html_text(genre)
        if not cleaned:
            continue
        mapped = GENRE_FALLBACKS.get(cleaned, "")
        if mapped:
            genre_bits.append(mapped)

    if is_event:
        if focus:
            return (
                f"{safe_title} — тематична подія в Steam для тих, хто стежить за {focus}. "
                "Тут варто чекати на знижки, демоверсії та цікаві добірки."
            )
        return (
            f"{safe_title} — тематична подія в Steam зі знижками, демоверсіями та добірками, "
            "яку варто переглянути, поки вона триває."
        )

    if is_free:
        emphasis = f"безкоштовно забрати в {source_label}"
        if genre_bits:
            return (
                f"{safe_title} зараз можна {emphasis}. Це гарна знахідка для бібліотеки, "
                f"особливо якщо вам заходять {ua_join(genre_bits) or focus}."
            )
        if focus:
            return (
                f"{safe_title} зараз можна {emphasis}. "
                f"Це гра, яку варто забрати, поки роздача відкрита, якщо вам заходять {focus}."
            )
        return (
            f"{safe_title} зараз можна {emphasis}. "
            "Це гра, яку можна спокійно додати до бібліотеки й повернутися до неї пізніше."
        )

    if discount_percent > 0:
        discount_label = f"зі знижкою {discount_percent}%"
        if genre_bits:
            return (
                f"{safe_title} зараз доступна {discount_label}. "
                f"Гарний варіант для тих, хто любить {ua_join(genre_bits) or focus}."
            )
        if focus:
            return (
                f"{safe_title} зараз доступна {discount_label}. "
                f"Ціна вже виглядає достатньо привабливою, щоб придивитися, якщо вам заходять {focus}."
            )
        return (
            f"{safe_title} зараз доступна {discount_label}, "
            "тож це хороша можливість повернутися до цієї гри зі знижкою."
        )

    emphasis = "вигідно взяти просто зараз"
    if genre_bits:
        return (
            f"{safe_title} зараз можна {emphasis}. "
            f"Гарний варіант для тих, хто любить {ua_join(genre_bits) or focus}."
        )
    if tags:
        return (
            f"{safe_title} зараз можна {emphasis}. "
            f"Ціна вже виглядає достатньо привабливою, щоб придивитися, якщо вам заходять {focus or 'ігри з виразним жанровим акцентом'}."
        )
    return (
        f"{safe_title} зараз можна {emphasis}. "
        "Ціна вже виглядає достатньо привабливою, щоб придивитися."
    )

def build_offer_copy(
    title: str,
    short_description: str,
    description: str,
    genres: list[str],
    tags: list[str],
    *,
    source: str,
    is_free: bool,
    is_event: bool,
    discount_percent: int = 0,
    lane: str | None = None,
    is_final_push: bool = False,
    promo_start: datetime | None = None,
    promo_end: datetime | None = None,
    now_utc: datetime | None = None,
    long_summary_limit: int = 320,
    short_summary_limit: int = 110,
) -> dict[str, str]:
    final_push = is_final_push or lane == "final_push"
    summary_source = _pick_preferred_text(short_description, description)
    summary = summary_source or build_fallback_summary(
        title,
        genres,
        tags,
        is_free,
        source=source,
        is_event=is_event,
        discount_percent=discount_percent,
    )
    summary = truncate_text(summary, max_length=long_summary_limit)

    return {
        "summary": summary,
        "short_summary": truncate_text(summary, max_length=min(short_summary_limit, long_summary_limit)),
        "hook_line": truncate_text(
            _build_hook_line(
                title=title,
                source=source,
                is_free=is_free,
                is_event=is_event,
                discount_percent=discount_percent,
                final_push=final_push,
            ),
            max_length=90,
        ),
        "urgency_line": truncate_text(
            _build_urgency_line(
                source=source,
                is_free=is_free,
                is_event=is_event,
                final_push=final_push,
                promo_start=promo_start,
                promo_end=promo_end,
                now_utc=now_utc,
            ),
            max_length=90,
        ),
    }


def build_focus_text(tags: list[str], genres: list[str]) -> str:
    return _build_focus_text(tags, genres)
def _pick_preferred_text(short_description: str, description: str) -> str:
    for value in (short_description, description):
        cleaned = clean_html_text(value)
        if cleaned and contains_cyrillic(cleaned):
            return cleaned
    return ""


def _build_focus_text(tags: list[str], genres: list[str]) -> str:
    values: list[str] = []
    seen: set[str] = set()
    for raw in list(tags) + list(genres):
        cleaned = _localize_focus_value(raw)
        if not cleaned:
            continue
        token = cleaned.lower()
        if token in seen:
            continue
        seen.add(token)
        values.append(token)
        if len(values) >= 3:
            break
    return ua_join(values)


def _localize_focus_value(value: str) -> str:
    cleaned = clean_html_text(value).strip()
    if not cleaned:
        return ""

    normalized = " ".join(cleaned.lower().replace("_", " ").replace("-", " ").split())
    for needle, replacement in FOCUS_TRANSLATIONS:
        if needle in normalized:
            return replacement
    if _is_junk_focus_value(cleaned, normalized):
        return ""

    if contains_cyrillic(cleaned):
        return cleaned.lower()
    return ""


def _is_junk_focus_value(cleaned: str, normalized: str) -> bool:
    if not normalized:
        return True
    if normalized in JUNK_FOCUS_TOKENS:
        return True
    if normalized.endswith(" edition") or normalized.endswith(" bundle"):
        return True
    if not contains_cyrillic(cleaned) and re.fullmatch(r"[a-z0-9]+(?:[_/-][a-z0-9]+)+", cleaned.lower()):
        return True
    return False


def _build_hook_line(
    *,
    title: str,
    source: str,
    is_free: bool,
    is_event: bool,
    discount_percent: int,
    final_push: bool,
) -> str:
    safe_title = truncate_text(clean_html_text(title) or "Гра", max_length=48)
    if is_event:
        return f"{safe_title} вже триває."
    if final_push:
        return "Фінальний шанс звернути увагу на цю пропозицію."
    if is_free:
        store_label = "Epic" if (source or "").strip().lower() == "epic" else "Steam"
        return f"Безкоштовна роздача в {store_label} вже активна."
    if discount_percent > 0:
        return f"Знижка {discount_percent}% уже активна."
    return f"{safe_title} знову привертає увагу."


def _build_urgency_line(
    *,
    source: str,
    is_free: bool,
    is_event: bool,
    final_push: bool,
    promo_start: datetime | None,
    promo_end: datetime | None,
    now_utc: datetime | None,
) -> str:
    if promo_start and now_utc is not None and promo_start > now_utc:
        return f"Стартує {format_deadline(promo_start)}."
    if promo_end:
        deadline = format_deadline(promo_end)
        if final_push:
            return f"Фінальний шанс: до {deadline}."
        if is_event:
            return f"Подія триває до {deadline}."
        if is_free:
            return f"Забрати можна до {deadline}."
        return f"Ціна актуальна до {deadline}."
    if final_push:
        return "Фінальний шанс: пропозиція вже виходить на останню пряму."
    if is_event:
        return "Подія вже активна, тож добірку варто перевірити найближчим часом."
    if is_free:
        store_label = "Epic Games Store" if (source or "").strip().lower() == "epic" else "Steam"
        return f"Роздача в {store_label} активна просто зараз."
    return "Пропозиція активна просто зараз."


