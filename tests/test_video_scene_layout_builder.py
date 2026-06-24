from __future__ import annotations

import json
import sys
from pathlib import Path

from dealbot.video import (
    VideoCTA,
    build_scene_asset_plan,
    build_scene_layout_payload,
    build_video_manifest_draft,
    build_video_offer_from_preview_report,
    export_video_offer_artifacts,
)
from tools.export_video_offer_artifacts import main as export_video_offer_artifacts_main


def _build_preview_report_payload(
    card_path: Path,
    *,
    title: str = "Scene Layout Test Game",
    current_price: int | None = 14900,
    old_price: int | None = 29900,
    discount: int | None = 50,
    reviews: int | None = 42000,
    positive_pct: int | None = 94,
    promo_end: str | None = "2026-06-25T18:00:00",
    official_trailers: list[str] | None = None,
    official_screenshots: list[str] | None = None,
    fallback_image: str | None = "https://cdn.example.com/layout-fallback.jpg",
) -> dict:
    trailers = list(official_trailers or ["https://cdn.example.com/layout-trailer.mp4"])
    screenshots = list(official_screenshots or ["https://cdn.example.com/layout-screenshot.jpg"])
    assets: dict[str, str] = {}
    if screenshots:
        assets["screenshot"] = screenshots[0]
        assets["hero"] = screenshots[0]
    if fallback_image:
        assets["fallback"] = fallback_image

    candidate = {
        "title": title,
        "offer_id": "steam:scene-layout-test",
        "source": "steam",
        "platform": "steam",
        "store_url": "https://store.steampowered.com/app/30",
        "discount": discount,
        "current_price": current_price,
        "old_price": old_price,
        "reviews": reviews,
        "positive_pct": positive_pct,
    }
    artifact = {
        "offer_id": "steam:scene-layout-test",
        "caption_html": "<b>Scene Layout Test Game</b>",
        "caption_hash": "scene-layout-caption-hash",
        "image_hash": "scene-layout-image-hash",
        "idempotency_key": "scene-layout-offer-key",
        "image_path": str(card_path),
        "assets_used": list(screenshots),
        "render_diagnostics": {},
        "card_family": "DISCOUNT",
        "template_id": "steam_discount",
    }
    offer_snapshot = {
        "offer_id": "steam:scene-layout-test",
        "source": "steam",
        "title": title,
        "store_url": "https://store.steampowered.com/app/30",
        "currency": "UAH",
        "price_after_minor": current_price,
        "price_before_minor": old_price,
        "discount_percent": discount,
        "promo_end": promo_end,
        "review_score": positive_pct,
        "review_count": reviews,
        "achievements_count": 55,
        "has_trading_cards": True,
        "assets": assets,
        "metadata": {
            "official_trailers": trailers,
            "official_screenshots": screenshots,
        },
    }
    return {
        "run_key": "20260625T120000Z",
        "created_at": "2026-06-25T12:00:00",
        "send_test_target": {
            "candidate": dict(candidate),
            "artifact": dict(artifact),
        },
        "pinned_publish": {
            "contract_version": 1,
            "source": "preview",
            "created_at": "2026-06-25T12:00:00",
            "report_run_key": "20260625T120000Z",
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


def _build_video_offer(
    tmp_path: Path,
    **kwargs,
):
    card_path = tmp_path / "cards" / "scene-layout-card.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"scene-layout-card")
    report = _build_preview_report_payload(card_path, **kwargs)
    return build_video_offer_from_preview_report(report)


def _build_scene_layout_payload(
    tmp_path: Path,
    **kwargs,
):
    video_offer = _build_video_offer(tmp_path, **kwargs)
    draft_manifest = build_video_manifest_draft(video_offer)
    scene_asset_plan = build_scene_asset_plan(video_offer, draft_manifest)
    return video_offer, scene_asset_plan, build_scene_layout_payload(video_offer, scene_asset_plan)


def _write_preview_report(tmp_path: Path, **kwargs) -> Path:
    card_path = tmp_path / "cards" / "scene-layout-card.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"scene-layout-card")
    report_path = tmp_path / "output" / "analytics" / "scene-layout-preview.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(_build_preview_report_payload(card_path, **kwargs), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return report_path


def _scene(payload: dict, scene_id: str) -> dict:
    for scene_payload in payload["scenes"]:
        if scene_payload["scene_id"] == scene_id:
            return scene_payload
    raise AssertionError(f"Missing scene_id={scene_id!r}")


def test_layout_payload_has_exactly_five_scenes_with_stable_order_and_canvas(tmp_path: Path) -> None:
    video_offer = _build_video_offer(tmp_path)
    draft_manifest = build_video_manifest_draft(video_offer)
    scene_asset_plan = build_scene_asset_plan(video_offer, draft_manifest)

    first_payload = build_scene_layout_payload(video_offer, scene_asset_plan)
    second_payload = build_scene_layout_payload(video_offer, scene_asset_plan)

    assert first_payload == second_payload
    assert first_payload["scene_count"] == 5
    assert [scene["scene_id"] for scene in first_payload["scenes"]] == [
        "hook",
        "identity",
        "offer_proof",
        "trust_or_deadline",
        "telegram_cta",
    ]
    assert all(scene["canvas"] == {"width": 1080, "height": 1920} for scene in first_payload["scenes"])


def test_required_text_blocks_exist_for_hook_identity_offer_and_cta(tmp_path: Path) -> None:
    _, _, payload = _build_scene_layout_payload(tmp_path)

    hook_scene = _scene(payload, "hook")
    identity_scene = _scene(payload, "identity")
    offer_scene = _scene(payload, "offer_proof")
    cta_scene = _scene(payload, "telegram_cta")

    assert hook_scene["text_blocks"][0]["role"] == "headline"
    assert hook_scene["text_blocks"][0]["max_lines"] == 2
    assert hook_scene["text_blocks"][0]["alignment"] == "center"
    assert hook_scene["text_blocks"][0]["anchor"] == "upper_middle"

    assert [block["role"] for block in identity_scene["text_blocks"]] == ["title", "platform_store"]
    assert sum(block["max_lines"] for block in identity_scene["text_blocks"]) == 3

    assert [block["role"] for block in offer_scene["text_blocks"]] == [
        "offer_badge",
        "current_price",
        "old_price",
        "savings",
    ]
    assert cta_scene["text_blocks"][0]["role"] == "cta"
    assert cta_scene["text_blocks"][0]["required"] is True


def test_trust_scene_uses_deadline_first_when_available(tmp_path: Path) -> None:
    _, _, payload = _build_scene_layout_payload(tmp_path)

    trust_scene = _scene(payload, "trust_or_deadline")

    assert [block["role"] for block in trust_scene["text_blocks"]] == ["deadline"]
    assert trust_scene["text_blocks"][0]["text"] == "2026-06-25T18:00:00"


def test_missing_optional_facts_do_not_crash_and_do_not_fabricate_text(tmp_path: Path) -> None:
    _, _, payload = _build_scene_layout_payload(
        tmp_path,
        current_price=None,
        old_price=None,
        discount=None,
        reviews=None,
        positive_pct=None,
        promo_end=None,
    )

    offer_scene = _scene(payload, "offer_proof")
    trust_scene = _scene(payload, "trust_or_deadline")
    all_text = [block["text"] for scene in payload["scenes"] for block in scene["text_blocks"]]

    assert offer_scene["text_blocks"] == []
    assert trust_scene["text_blocks"] == []
    assert all("Now:" not in text for text in all_text)
    assert all("Was:" not in text for text in all_text)
    assert all("Save:" not in text for text in all_text)
    assert any("has no text blocks" in warning for warning in offer_scene["warnings"])
    assert any("has no text blocks" in warning for warning in trust_scene["warnings"])


def test_cta_variants_are_preserved_without_store_url_leak(tmp_path: Path) -> None:
    video_offer = _build_video_offer(tmp_path)
    video_offer.cta = VideoCTA(
        default="See the full deal in Telegram",
        tiktok="Join Telegram for the full deal",
        shorts="Open Telegram for the full post",
        reels="Find the full deal in Telegram",
    )
    draft_manifest = build_video_manifest_draft(video_offer)
    scene_asset_plan = build_scene_asset_plan(video_offer, draft_manifest)
    payload = build_scene_layout_payload(video_offer, scene_asset_plan)
    cta_scene = _scene(payload, "telegram_cta")

    assert cta_scene["platform_variants"] == {
        "tiktok": "Join Telegram for the full deal",
        "shorts": "Open Telegram for the full post",
        "reels": "Find the full deal in Telegram",
    }
    assert [block["text"] for block in cta_scene["text_blocks"][1:]] == [
        "Join Telegram for the full deal",
        "Open Telegram for the full post",
        "Find the full deal in Telegram",
    ]
    assert video_offer.store_url not in json.dumps(payload)


def test_layout_export_only_occurs_with_new_flag_and_existing_behavior_remains_unchanged(tmp_path: Path) -> None:
    report_path = _write_preview_report(tmp_path)
    default_dir = tmp_path / "exports" / "default"
    scene_plan_dir = tmp_path / "exports" / "scene-plan"
    layout_dir = tmp_path / "exports" / "layout"

    default_result = export_video_offer_artifacts(report_path, output_dir=default_dir)
    scene_plan_result = export_video_offer_artifacts(report_path, output_dir=scene_plan_dir, with_scene_plan=True)
    layout_result = export_video_offer_artifacts(report_path, output_dir=layout_dir, with_layout_payload=True)

    assert default_result.scene_asset_plan_json_path is None
    assert default_result.scene_layout_payload_json_path is None
    assert not (default_dir / "scene_asset_plan.json").exists()
    assert not (default_dir / "scene_layout_payload.json").exists()

    assert scene_plan_result.scene_asset_plan_json_path == (scene_plan_dir / "scene_asset_plan.json").resolve()
    assert scene_plan_result.scene_asset_plan_json_path.exists()
    assert scene_plan_result.scene_layout_payload_json_path is None
    assert not (scene_plan_dir / "scene_layout_payload.json").exists()

    assert layout_result.scene_asset_plan_json_path == (layout_dir / "scene_asset_plan.json").resolve()
    assert layout_result.scene_asset_plan_json_path.exists()
    assert layout_result.scene_layout_payload_json_path == (layout_dir / "scene_layout_payload.json").resolve()
    assert layout_result.scene_layout_payload_json_path.exists()
    exported_layout_payload = json.loads(layout_result.scene_layout_payload_json_path.read_text(encoding="utf-8"))
    assert len(exported_layout_payload["scenes"]) == 5


def test_cli_with_layout_payload_flag_wires_optional_export(tmp_path: Path, capsys) -> None:
    report_path = _write_preview_report(tmp_path)
    default_dir = tmp_path / "cli-exports" / "default"
    layout_dir = tmp_path / "cli-exports" / "layout"

    default_exit = export_video_offer_artifacts_main(
        ["--from-report", str(report_path), "--output-dir", str(default_dir)],
    )
    default_stdout = capsys.readouterr().out
    layout_exit = export_video_offer_artifacts_main(
        ["--from-report", str(report_path), "--output-dir", str(layout_dir), "--with-layout-payload"],
    )
    layout_stdout = capsys.readouterr().out

    assert default_exit == 0
    assert layout_exit == 0
    assert "scene_asset_plan_json_path:" not in default_stdout
    assert "scene_layout_payload_json_path:" not in default_stdout
    assert "scene_asset_plan_json_path:" in layout_stdout
    assert "scene_layout_payload_json_path:" in layout_stdout
    assert not (default_dir / "scene_layout_payload.json").exists()
    assert (layout_dir / "scene_layout_payload.json").exists()


def test_layout_builder_does_not_import_old_video_generator_or_network_ffmpeg_telegram_pillow_modules(
    tmp_path: Path,
) -> None:
    video_offer = _build_video_offer(tmp_path)
    draft_manifest = build_video_manifest_draft(video_offer)
    scene_asset_plan = build_scene_asset_plan(video_offer, draft_manifest)
    before_modules = {
        name
        for name in sys.modules
        if name == "video_generator"
        or name.startswith("video_generator.")
        or name == "httpx"
        or name.startswith("httpx.")
        or name == "telegram"
        or name.startswith("telegram.")
        or name == "ffmpeg"
        or name.startswith("ffmpeg.")
        or name == "PIL"
        or name.startswith("PIL.")
    }

    build_scene_layout_payload(video_offer, scene_asset_plan)

    after_modules = {
        name
        for name in sys.modules
        if name == "video_generator"
        or name.startswith("video_generator.")
        or name == "httpx"
        or name.startswith("httpx.")
        or name == "telegram"
        or name.startswith("telegram.")
        or name == "ffmpeg"
        or name.startswith("ffmpeg.")
        or name == "PIL"
        or name.startswith("PIL.")
    }
    assert after_modules == before_modules
