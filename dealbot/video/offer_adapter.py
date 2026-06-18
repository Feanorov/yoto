from __future__ import annotations

from typing import Any

from .models import VideoCTA, VideoOffer, VideoOfferValidationError, VideoVisualAssets


STORE_LABELS = {
    "steam": "Steam",
    "epic": "Epic Games Store",
    "event": "Steam",
}

FREE_PRICE_TOKENS = ("free", "0", "0.0", "0.00", "freebie", "free now", "gratis", "free-to-claim")
FREE_LOCALE_TOKENS = (
    "gratis",
    "free",
    "freebie",
    "\u0431\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u043e",
    "\u0431\u0435\u0437\u043a\u043e\u0448\u0442\u043e\u0432\u043d\u043e",
)


def build_video_offer_from_preview_report(
    report: dict[str, Any],
    source_report_path: str | None = None,
) -> VideoOffer:
    if not isinstance(report, dict):
        raise VideoOfferValidationError("VideoOffer source report must be a dict.")

    source_kind, pinned_publish = _resolve_source_payload(report)
    send_test_target = _as_dict(report.get("send_test_target"))
    send_candidate = _as_dict(send_test_target.get("candidate"))
    send_artifact = _as_dict(send_test_target.get("artifact"))
    pinned_candidate = _as_dict(pinned_publish.get("candidate"))
    pinned_artifact = _as_dict(pinned_publish.get("artifact"))
    offer_snapshot = _merged_payload(_as_dict(pinned_publish.get("offer_snapshot")))
    decision_snapshot = _merged_payload(_as_dict(pinned_publish.get("decision_snapshot")))
    artifact = _merged_payload(send_artifact, pinned_artifact)
    candidate = _merged_payload(send_candidate, pinned_candidate)
    render_inputs = _as_dict(artifact.get("render_inputs"))
    offer_snapshot = _merged_payload(_as_dict(render_inputs.get("offer")), offer_snapshot)
    decision_snapshot = _merged_payload(_as_dict(render_inputs.get("decision")), decision_snapshot)
    render_diagnostics = _as_dict(artifact.get("render_diagnostics"))
    assets_used = _string_list(artifact.get("assets_used"))

    source_value = _normalized_token(
        _pick_value(
            candidate.get("source"),
            candidate.get("platform"),
            offer_snapshot.get("source"),
        )
    )
    platform = _normalized_token(_pick_value(candidate.get("platform"), offer_snapshot.get("source"), source_value))
    store = _pick_text(candidate.get("store"), offer_snapshot.get("store")) or STORE_LABELS.get(source_value, "")
    store_url = _pick_text(candidate.get("store_url"), offer_snapshot.get("store_url"))
    offer_id = _pick_text(artifact.get("offer_id"), candidate.get("offer_id"), offer_snapshot.get("offer_id"))
    title = _pick_text(candidate.get("title"), offer_snapshot.get("title"), artifact.get("title"))
    currency = _pick_text(offer_snapshot.get("currency"), candidate.get("currency")) or "UAH"

    current_price_raw = _pick_value(
        candidate.get("current_price_text"),
        candidate.get("current_price"),
        decision_snapshot.get("current_price_text"),
        decision_snapshot.get("current_price"),
        offer_snapshot.get("current_price_text"),
        offer_snapshot.get("price_after_minor"),
    )
    old_price_raw = _pick_value(
        candidate.get("old_price_text"),
        candidate.get("old_price"),
        decision_snapshot.get("old_price_text"),
        decision_snapshot.get("old_price"),
        offer_snapshot.get("old_price_text"),
        offer_snapshot.get("price_before_minor"),
    )
    current_price_text = _coerce_price_text(current_price_raw, currency)
    old_price_text = _coerce_price_text(old_price_raw, currency)
    savings_text = _pick_text(
        candidate.get("savings_text"),
        decision_snapshot.get("savings_text"),
        offer_snapshot.get("savings_text"),
    ) or _build_savings_text(current_price_raw, old_price_raw, currency)
    deadline_text = _coerce_text_fact(
        _pick_value(
            candidate.get("deadline_text"),
            candidate.get("deadline"),
            decision_snapshot.get("deadline_text"),
            decision_snapshot.get("deadline"),
            offer_snapshot.get("deadline_text"),
            offer_snapshot.get("promo_end"),
        )
    )
    reviews_text = _pick_text(candidate.get("reviews_text"), offer_snapshot.get("reviews_text")) or _build_reviews_text(
        _pick_value(candidate.get("reviews"), offer_snapshot.get("review_count"))
    )
    positive_percent_text = _pick_text(
        candidate.get("positive_percent_text"),
        offer_snapshot.get("positive_percent_text"),
    ) or _build_positive_percent_text(_pick_value(candidate.get("positive_pct"), offer_snapshot.get("review_score")))
    achievements_text = _pick_text(
        candidate.get("achievements_text"),
        offer_snapshot.get("achievements_text"),
    ) or _build_achievements_text(_pick_value(offer_snapshot.get("achievements_count"), candidate.get("achievements")))
    cards_text = _pick_text(candidate.get("cards_text"), offer_snapshot.get("cards_text")) or _build_cards_text(
        _pick_value(offer_snapshot.get("has_trading_cards"), candidate.get("has_trading_cards"))
    )
    discount_percent = _int_or_none(
        _pick_value(
            candidate.get("discount_percent"),
            candidate.get("discount"),
            offer_snapshot.get("discount_percent"),
            decision_snapshot.get("discount_percent"),
        )
    )
    offer_type = _detect_offer_type(
        current_price_raw=current_price_raw,
        current_price_text=current_price_text,
        old_price_raw=old_price_raw,
        discount_percent=discount_percent,
    )

    card_image_path = _pick_text(artifact.get("image_path"))
    fallback_image = _pick_text(
        _as_dict(offer_snapshot.get("assets")).get("fallback"),
        render_diagnostics.get("selected_asset_path"),
        render_diagnostics.get("hero_asset_used"),
        _first_non_card_asset(assets_used, card_image_path),
        _as_dict(offer_snapshot.get("assets")).get("hero"),
        _as_dict(offer_snapshot.get("assets")).get("header"),
        _as_dict(offer_snapshot.get("assets")).get("screenshot"),
    )
    visual_assets = VideoVisualAssets(
        card_image=card_image_path or "",
        official_screenshots=_collect_official_screenshots(offer_snapshot, assets_used, card_image_path),
        official_trailers=_collect_official_trailers(offer_snapshot, decision_snapshot),
        fallback_image=fallback_image,
    )

    resolved_source_report_path = _pick_text(
        source_report_path,
        report.get("report_path"),
        report.get("source_report_path"),
        pinned_publish.get("source_report_path"),
    )
    template_hint = _detect_template_hint(offer_type, decision_snapshot, candidate)

    return VideoOffer(
        offer_id=offer_id or "",
        source_report_path=resolved_source_report_path,
        source_kind=source_kind,
        title=title or "",
        store=store,
        platform=platform,
        store_url=store_url or "",
        offer_type=offer_type,
        discount_percent=discount_percent,
        current_price_text=current_price_text,
        old_price_text=old_price_text,
        savings_text=savings_text,
        deadline_text=deadline_text,
        reviews_text=reviews_text,
        positive_percent_text=positive_percent_text,
        achievements_text=achievements_text,
        cards_text=cards_text,
        caption_html=_pick_text(artifact.get("caption_html")) or "",
        card_image_path=card_image_path or "",
        image_hash=_pick_text(artifact.get("image_hash")) or "",
        caption_hash=_pick_text(artifact.get("caption_hash")) or "",
        idempotency_key=_pick_text(artifact.get("idempotency_key")) or "",
        visual_assets=visual_assets,
        cta=VideoCTA(),
        voice_mode=_normalized_token(_pick_value(decision_snapshot.get("voice_mode"), artifact.get("voice_mode"))) or "none",
        template_hint=template_hint,
        source_metadata={
            "report_run_key": _pick_text(report.get("run_key"), pinned_publish.get("report_run_key")),
            "template_id": _pick_text(
                decision_snapshot.get("template_id"),
                artifact.get("template_id"),
            ),
            "card_family": _pick_text(artifact.get("card_family")),
            "pinned_publish_source": _pick_text(pinned_publish.get("source")),
        },
    )


def build_video_manifest_draft(video_offer: VideoOffer) -> dict[str, Any]:
    strongest_offer_text = _build_strongest_offer_text(video_offer)
    identity_line = " / ".join(item for item in (video_offer.platform, video_offer.store) if item)
    offer_proof_facts = [
        value
        for value in (
            _discount_line(video_offer.discount_percent),
            _label_fact("Now", video_offer.current_price_text),
            _label_fact("Was", video_offer.old_price_text),
            _label_fact("Save", video_offer.savings_text),
        )
        if value
    ]
    trust_or_deadline_facts = [
        value
        for value in (
            video_offer.reviews_text,
            video_offer.positive_percent_text,
            video_offer.achievements_text,
            video_offer.cards_text,
            video_offer.deadline_text,
        )
        if value
    ]
    hook_assets = _dedupe_preserve_order(
        list(video_offer.visual_assets.official_trailers)
        + list(video_offer.visual_assets.official_screenshots)
        + [value for value in (video_offer.visual_assets.fallback_image, video_offer.visual_assets.card_image) if value]
    )

    return {
        "format": "vertical_1080x1920",
        "duration_target_sec": {"min": 14, "max": 18},
        "template": "single_offer_gameplay_first",
        "template_hint": video_offer.template_hint,
        "voice_mode": video_offer.voice_mode,
        "music_required": True,
        "offer_id": video_offer.offer_id,
        "source": {
            "source_kind": video_offer.source_kind,
            "source_report_path": video_offer.source_report_path,
            "store_url": video_offer.store_url,
        },
        "platform_endcards": {
            "tiktok": video_offer.cta.tiktok,
            "shorts": video_offer.cta.shorts,
            "reels": video_offer.cta.reels,
        },
        "scenes": [
            {
                "order": 1,
                "scene_id": "hook",
                "intent": "gameplay/trailer/motion screenshot opener candidate + strongest offer text",
                "primary_text": strongest_offer_text,
                "secondary_text": video_offer.title,
                "asset_candidates": hook_assets,
            },
            {
                "order": 2,
                "scene_id": "identity",
                "intent": "title + platform/store",
                "primary_text": video_offer.title,
                "secondary_text": identity_line,
            },
            {
                "order": 3,
                "scene_id": "offer_proof",
                "intent": "discount/free/current price/old price/savings",
                "facts": offer_proof_facts,
            },
            {
                "order": 4,
                "scene_id": "trust_or_deadline",
                "intent": "reviews/positive %/deadline if available",
                "facts": trust_or_deadline_facts,
            },
            {
                "order": 5,
                "scene_id": "telegram_cta",
                "intent": "Telegram CTA variant",
                "primary_text": video_offer.cta.default,
                "platform_variants": {
                    "tiktok": video_offer.cta.tiktok,
                    "shorts": video_offer.cta.shorts,
                    "reels": video_offer.cta.reels,
                },
            },
        ],
    }


def _resolve_source_payload(report: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    pinned_publish = _as_dict(report.get("pinned_publish"))
    if pinned_publish:
        return "preview_report", pinned_publish
    if "artifact" in report and "contract_version" in report:
        return "pinned_publish", dict(report)
    raise VideoOfferValidationError(
        "VideoOffer source payload must include pinned_publish or be a pinned_publish payload.",
    )


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _merged_payload(*payloads: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for key, value in payload.items():
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            merged[key] = value
    return merged


def _pick_value(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _pick_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                return cleaned
        elif value is not None:
            cleaned = str(value).strip()
            if cleaned:
                return cleaned
    return None


def _normalized_token(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _coerce_price_text(value: Any, currency: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    if isinstance(value, (int, float)):
        amount = float(value) / 100
        if amount.is_integer():
            return f"{int(amount)} {currency.upper()}"
        return f"{amount:.2f} {currency.upper()}"
    return None


def _coerce_text_fact(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return str(value).strip() or None


def _build_savings_text(current_price_raw: Any, old_price_raw: Any, currency: str) -> str | None:
    current_minor = _minor_amount_or_none(current_price_raw)
    old_minor = _minor_amount_or_none(old_price_raw)
    if current_minor is None or old_minor is None or old_minor <= current_minor:
        return None
    return _coerce_price_text(old_minor - current_minor, currency)


def _minor_amount_or_none(value: Any) -> int | None:
    if isinstance(value, (int, float)):
        return int(round(float(value)))
    return None


def _build_reviews_text(value: Any) -> str | None:
    count = _int_or_none(value)
    if count is None:
        return None
    return f"{count:,} reviews"


def _build_positive_percent_text(value: Any) -> str | None:
    percent = _int_or_none(value)
    if percent is None:
        return None
    return f"{percent}% positive"


def _build_achievements_text(value: Any) -> str | None:
    count = _int_or_none(value)
    if count is None:
        return None
    return f"{count} achievements"


def _build_cards_text(value: Any) -> str | None:
    if value is True:
        return "Trading cards available"
    return None


def _detect_offer_type(
    *,
    current_price_raw: Any,
    current_price_text: str | None,
    old_price_raw: Any,
    discount_percent: int | None,
) -> str:
    if _looks_like_free(current_price_raw, current_price_text):
        return "freebie"
    if discount_percent not in (None, 0):
        return "discount"
    if current_price_raw is not None or old_price_raw is not None:
        return "discount"
    return "unknown"


def _looks_like_free(current_price_raw: Any, current_price_text: str | None) -> bool:
    if isinstance(current_price_raw, (int, float)) and float(current_price_raw) == 0:
        return True
    normalized_text = _normalized_token(current_price_text)
    if normalized_text in FREE_PRICE_TOKENS:
        return True
    return any(token in normalized_text for token in FREE_LOCALE_TOKENS)


def _collect_official_screenshots(
    offer_snapshot: dict[str, Any],
    assets_used: list[str],
    card_image_path: str | None,
) -> list[str]:
    assets = _as_dict(offer_snapshot.get("assets"))
    metadata = _as_dict(offer_snapshot.get("metadata"))
    screenshots = _dedupe_preserve_order(
        _string_list(metadata.get("official_screenshots"))
        + _string_list(metadata.get("screenshots"))
        + [value for value in (assets.get("screenshot"), assets.get("hero"), assets.get("header")) if _pick_text(value)]
        + [value for value in assets_used if value != card_image_path and _looks_like_visual_ref(value)]
    )
    return screenshots


def _collect_official_trailers(
    offer_snapshot: dict[str, Any],
    decision_snapshot: dict[str, Any],
) -> list[str]:
    metadata = _as_dict(offer_snapshot.get("metadata"))
    return _dedupe_preserve_order(
        _string_list(metadata.get("official_trailers"))
        + _string_list(metadata.get("trailers"))
        + _string_list(decision_snapshot.get("official_trailers"))
        + _string_list(decision_snapshot.get("trailers"))
    )


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        if isinstance(item, str):
            cleaned = item.strip()
            if cleaned:
                items.append(cleaned)
            continue
        if isinstance(item, dict):
            for key in ("url", "mp4", "webm", "video_url", "path", "path_or_url"):
                cleaned = _pick_text(item.get(key))
                if cleaned:
                    items.append(cleaned)
                    break
    return items


def _looks_like_visual_ref(value: str) -> bool:
    lowered = value.lower()
    return lowered.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp"))


def _first_non_card_asset(assets_used: list[str], card_image_path: str | None) -> str | None:
    for value in assets_used:
        if value != card_image_path and _looks_like_visual_ref(value):
            return value
    return None


def _detect_template_hint(
    offer_type: str,
    decision_snapshot: dict[str, Any],
    candidate: dict[str, Any],
) -> str:
    content_type = _normalized_token(_pick_value(decision_snapshot.get("content_type"), candidate.get("post_type")))
    if content_type in {"roundup", "top3", "top_list", "toplist"}:
        return "top3"
    if offer_type == "freebie":
        return "freebie"
    if offer_type == "discount":
        return "single_discount"
    return "unknown"


def _build_strongest_offer_text(video_offer: VideoOffer) -> str:
    if video_offer.offer_type == "freebie":
        if video_offer.current_price_text:
            return f"Free now: {video_offer.current_price_text}"
        return "Free now"
    if video_offer.discount_percent is not None and video_offer.current_price_text:
        return f"-{video_offer.discount_percent}% | {video_offer.current_price_text}"
    if video_offer.current_price_text and video_offer.old_price_text:
        return f"{video_offer.current_price_text} from {video_offer.old_price_text}"
    if video_offer.current_price_text:
        return video_offer.current_price_text
    if video_offer.savings_text:
        return f"Save {video_offer.savings_text}"
    return video_offer.title


def _discount_line(discount_percent: int | None) -> str | None:
    if discount_percent is None:
        return None
    return f"-{discount_percent}%"


def _label_fact(label: str, value: str | None) -> str | None:
    if not value:
        return None
    return f"{label}: {value}"


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value or "").strip()
        if not cleaned or cleaned in seen:
            continue
        deduped.append(cleaned)
        seen.add(cleaned)
    return deduped
