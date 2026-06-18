from __future__ import annotations

import sys
from pathlib import Path

import pytest

from dealbot.video import (
    VideoOfferValidationError,
    build_video_manifest_draft,
    build_video_offer_from_preview_report,
)


def _build_preview_report(
    tmp_path: Path,
    *,
    title: str = "Test Game",
    source: str = "steam",
    current_price: int | str | None = 11200,
    old_price: int | str | None = 22500,
    discount: int | None = 50,
    include_title: bool = True,
    include_image_path: bool = True,
    include_source_fields: bool = True,
) -> dict:
    card_path = tmp_path / "cards" / "video-offer-card.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"card-image")

    offer_id = f"{source}:10"
    store_url = (
        "https://store.steampowered.com/app/10"
        if source == "steam"
        else "https://store.epicgames.com/p/test-game"
    )

    candidate = {
        "title": title if include_title else "",
        "offer_id": offer_id,
        "source": source if include_source_fields else "",
        "platform": source if include_source_fields else "",
        "store_url": store_url if include_source_fields else "",
        "discount": discount,
        "current_price": current_price,
        "old_price": old_price,
        "reviews": 1200,
        "positive_pct": 89,
    }
    artifact = {
        "offer_id": offer_id,
        "caption_html": "<b>Test Game</b>",
        "caption_hash": "caption-hash",
        "image_hash": "image-hash",
        "idempotency_key": "video-offer-key",
        "image_path": str(card_path) if include_image_path else "",
        "assets_used": [
            "https://cdn.example.com/screenshot-1.jpg",
            "https://cdn.example.com/screenshot-2.jpg",
        ],
        "render_diagnostics": {
            "hero_asset_used": "https://cdn.example.com/hero.jpg",
        },
        "card_family": "DISCOUNT",
        "template_id": "steam_discount",
    }
    offer_snapshot = {
        "offer_id": offer_id,
        "source": source if include_source_fields else "",
        "title": title if include_title else "",
        "store_url": store_url if include_source_fields else "",
        "currency": "UAH",
        "price_after_minor": current_price if isinstance(current_price, int) else None,
        "price_before_minor": old_price if isinstance(old_price, int) else None,
        "discount_percent": discount,
        "promo_end": "2026-05-30T18:00:00",
        "review_score": 89,
        "review_count": 1200,
        "achievements_count": 42,
        "has_trading_cards": True,
        "assets": {
            "hero": "https://cdn.example.com/hero.jpg",
            "header": "https://cdn.example.com/header.jpg",
            "screenshot": "https://cdn.example.com/screenshot-1.jpg",
            "fallback": "https://cdn.example.com/fallback.jpg",
        },
        "metadata": {
            "official_trailers": ["https://cdn.example.com/trailer.mp4"],
            "official_screenshots": ["https://cdn.example.com/screenshot-1.jpg"],
        },
    }
    return {
        "run_key": "20260525T101500Z",
        "created_at": "2026-05-25T10:15:00",
        "send_test_target": {
            "candidate": dict(candidate),
            "artifact": dict(artifact),
        },
        "pinned_publish": {
            "contract_version": 1,
            "source": "preview",
            "created_at": "2026-05-25T10:15:00",
            "report_run_key": "20260525T101500Z",
            "candidate": dict(candidate),
            "offer_snapshot": dict(offer_snapshot),
            "decision_snapshot": {
                "lane": "high_value_discount",
                "template_id": "steam_discount",
            },
            "artifact": dict(artifact),
            "validation": {
                "image_exists": True,
                "caption_hash_verified": True,
                "image_hash_verified": True,
            },
        },
    }


def test_builds_video_offer_from_minimal_pinned_publish_like_report(tmp_path: Path) -> None:
    report = _build_preview_report(tmp_path)

    video_offer = build_video_offer_from_preview_report(
        report,
        source_report_path=str(tmp_path / "analytics" / "preview_report.json"),
    )

    assert video_offer.offer_id == "steam:10"
    assert video_offer.source_kind == "preview_report"
    assert video_offer.source_report_path == str(tmp_path / "analytics" / "preview_report.json")
    assert video_offer.title == "Test Game"
    assert video_offer.store == "Steam"
    assert video_offer.platform == "steam"
    assert video_offer.store_url == "https://store.steampowered.com/app/10"
    assert video_offer.card_image_path.endswith("video-offer-card.png")
    assert video_offer.visual_assets.card_image == video_offer.card_image_path
    assert video_offer.visual_assets.official_screenshots
    assert video_offer.visual_assets.official_trailers == ["https://cdn.example.com/trailer.mp4"]


def test_detects_discount_offer(tmp_path: Path) -> None:
    report = _build_preview_report(tmp_path, discount=None)

    video_offer = build_video_offer_from_preview_report(report)

    assert video_offer.offer_type == "discount"
    assert video_offer.current_price_text == "112 UAH"
    assert video_offer.old_price_text == "225 UAH"
    assert video_offer.savings_text == "113 UAH"
    assert video_offer.template_hint == "single_discount"


def test_detects_freebie_offer(tmp_path: Path) -> None:
    report = _build_preview_report(
        tmp_path,
        source="epic",
        current_price=0,
        old_price=69900,
        discount=None,
    )

    video_offer = build_video_offer_from_preview_report(report)

    assert video_offer.offer_type == "freebie"
    assert video_offer.store == "Epic Games Store"
    assert video_offer.template_hint == "freebie"


def test_preserves_caption_hash_image_hash_and_idempotency_key(tmp_path: Path) -> None:
    report = _build_preview_report(tmp_path)

    video_offer = build_video_offer_from_preview_report(report)

    assert video_offer.caption_hash == "caption-hash"
    assert video_offer.image_hash == "image-hash"
    assert video_offer.idempotency_key == "video-offer-key"


def test_voice_mode_defaults_to_none(tmp_path: Path) -> None:
    report = _build_preview_report(tmp_path)

    video_offer = build_video_offer_from_preview_report(report)

    assert video_offer.voice_mode == "none"


def test_build_video_manifest_draft_creates_five_scenes(tmp_path: Path) -> None:
    report = _build_preview_report(tmp_path)
    video_offer = build_video_offer_from_preview_report(report)

    manifest = build_video_manifest_draft(video_offer)

    assert manifest["format"] == "vertical_1080x1920"
    assert manifest["duration_target_sec"] == {"min": 14, "max": 18}
    assert manifest["template"] == "single_offer_gameplay_first"
    assert manifest["voice_mode"] == "none"
    assert len(manifest["scenes"]) == 5
    assert [scene["scene_id"] for scene in manifest["scenes"]] == [
        "hook",
        "identity",
        "offer_proof",
        "trust_or_deadline",
        "telegram_cta",
    ]


def test_platform_cta_variants_exist(tmp_path: Path) -> None:
    report = _build_preview_report(tmp_path)
    video_offer = build_video_offer_from_preview_report(report)

    manifest = build_video_manifest_draft(video_offer)

    assert set(manifest["platform_endcards"]) == {"tiktok", "shorts", "reels"}
    assert manifest["platform_endcards"]["tiktok"]
    assert manifest["platform_endcards"]["shorts"]
    assert manifest["platform_endcards"]["reels"]


@pytest.mark.parametrize(
    ("include_title", "include_image_path", "include_source_fields", "expected_field"),
    [
        (False, True, True, "title"),
        (True, False, True, "card_image_path"),
        (True, True, False, "store"),
    ],
)
def test_missing_required_fields_raise_clear_validation_error(
    tmp_path: Path,
    include_title: bool,
    include_image_path: bool,
    include_source_fields: bool,
    expected_field: str,
) -> None:
    report = _build_preview_report(
        tmp_path,
        include_title=include_title,
        include_image_path=include_image_path,
        include_source_fields=include_source_fields,
    )

    with pytest.raises(VideoOfferValidationError) as excinfo:
        build_video_offer_from_preview_report(report)

    assert expected_field in str(excinfo.value)


def test_video_offer_contract_does_not_import_old_video_generator(tmp_path: Path) -> None:
    before_modules = {
        name for name in sys.modules if name == "video_generator" or name.startswith("video_generator.")
    }
    report = _build_preview_report(tmp_path)

    build_video_offer_from_preview_report(report)

    after_modules = {
        name for name in sys.modules if name == "video_generator" or name.startswith("video_generator.")
    }
    assert after_modules == before_modules


def test_action_log_file_exists_and_mentions_video_01_contract() -> None:
    action_log_path = Path("docs") / "YOTO_VIDEO_GROWTH_ACTION_LOG.md"

    assert action_log_path.exists()
    assert "VIDEO-01-NORMALIZED-VIDEO-OFFER-CONTRACT" in action_log_path.read_text(encoding="utf-8")


def test_video_offer_contract_doc_exists() -> None:
    doc_path = Path("docs") / "YOTO_VIDEO_OFFER_CONTRACT.md"

    assert doc_path.exists()
    assert "VideoOffer" in doc_path.read_text(encoding="utf-8")
