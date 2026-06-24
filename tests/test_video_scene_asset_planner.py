from __future__ import annotations

import json
import sys
from pathlib import Path

from dealbot.video import (
    SceneAssetPlanError,
    VideoCTA,
    build_scene_asset_plan,
    build_video_manifest_draft,
    build_video_offer_from_preview_report,
    export_video_offer_artifacts,
)
from tools.export_video_offer_artifacts import main as export_video_offer_artifacts_main


def _build_preview_report_payload(
    card_path: Path,
    *,
    official_trailers: list[str] | None = None,
    official_screenshots: list[str] | None = None,
    fallback_image: str | None = "https://cdn.example.com/export-fallback.jpg",
) -> dict:
    trailers = list(official_trailers or [])
    screenshots = list(official_screenshots or [])
    assets: dict[str, str] = {}
    if screenshots:
        assets["screenshot"] = screenshots[0]
    if fallback_image:
        assets["fallback"] = fallback_image

    return {
        "run_key": "20260618T120000Z",
        "created_at": "2026-06-18T12:00:00",
        "send_test_target": {
            "candidate": {
                "title": "Scene Planner Test Game",
                "offer_id": "steam:scene-planner-test",
                "source": "steam",
                "platform": "steam",
                "store_url": "https://store.steampowered.com/app/20",
                "discount": 50,
                "current_price": 14900,
                "old_price": 29900,
                "reviews": 42000,
                "positive_pct": 94,
            },
            "artifact": {
                "offer_id": "steam:scene-planner-test",
                "caption_html": "<b>Scene Planner Test Game</b>",
                "caption_hash": "scene-caption-hash",
                "image_hash": "scene-image-hash",
                "idempotency_key": "scene-offer-key",
                "image_path": str(card_path),
                "assets_used": list(screenshots),
                "render_diagnostics": {},
                "card_family": "DISCOUNT",
                "template_id": "steam_discount",
            },
        },
        "pinned_publish": {
            "contract_version": 1,
            "source": "preview",
            "created_at": "2026-06-18T12:00:00",
            "report_run_key": "20260618T120000Z",
            "candidate": {
                "title": "Scene Planner Test Game",
                "offer_id": "steam:scene-planner-test",
                "source": "steam",
                "platform": "steam",
                "store_url": "https://store.steampowered.com/app/20",
                "discount": 50,
                "current_price": 14900,
                "old_price": 29900,
                "reviews": 42000,
                "positive_pct": 94,
            },
            "offer_snapshot": {
                "offer_id": "steam:scene-planner-test",
                "source": "steam",
                "title": "Scene Planner Test Game",
                "store_url": "https://store.steampowered.com/app/20",
                "currency": "UAH",
                "price_after_minor": 14900,
                "price_before_minor": 29900,
                "discount_percent": 50,
                "promo_end": "2026-06-25T18:00:00",
                "review_score": 94,
                "review_count": 42000,
                "achievements_count": 55,
                "has_trading_cards": True,
                "assets": assets,
                "metadata": {
                    "official_trailers": trailers,
                    "official_screenshots": screenshots,
                },
            },
            "decision_snapshot": {
                "lane": "high_value_discount",
                "template_id": "steam_discount",
            },
            "artifact": {
                "offer_id": "steam:scene-planner-test",
                "caption_html": "<b>Scene Planner Test Game</b>",
                "caption_hash": "scene-caption-hash",
                "image_hash": "scene-image-hash",
                "idempotency_key": "scene-offer-key",
                "image_path": str(card_path),
                "assets_used": list(screenshots),
                "render_diagnostics": {},
                "card_family": "DISCOUNT",
                "template_id": "steam_discount",
            },
            "validation": {
                "image_exists": True,
                "caption_hash_verified": True,
                "image_hash_verified": True,
            },
        },
    }


def _build_video_offer(
    tmp_path: Path,
    *,
    official_trailers: list[str] | None = None,
    official_screenshots: list[str] | None = None,
    fallback_image: str | None = "https://cdn.example.com/export-fallback.jpg",
):
    card_path = tmp_path / "cards" / "scene-plan-card.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"scene-plan-card")
    report = _build_preview_report_payload(
        card_path,
        official_trailers=official_trailers,
        official_screenshots=official_screenshots,
        fallback_image=fallback_image,
    )
    return build_video_offer_from_preview_report(report)


def _write_preview_report(
    tmp_path: Path,
    *,
    official_trailers: list[str] | None = None,
    official_screenshots: list[str] | None = None,
    fallback_image: str | None = "https://cdn.example.com/export-fallback.jpg",
) -> Path:
    card_path = tmp_path / "cards" / "scene-plan-card.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"scene-plan-card")
    report_path = tmp_path / "output" / "analytics" / "scene-planner-preview.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            _build_preview_report_payload(
                card_path,
                official_trailers=official_trailers,
                official_screenshots=official_screenshots,
                fallback_image=fallback_image,
            ),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return report_path


def test_scene_asset_plan_has_exactly_five_scenes_with_deterministic_order_and_default_duration(tmp_path: Path) -> None:
    video_offer = _build_video_offer(
        tmp_path,
        official_trailers=["https://cdn.example.com/trailer-1.mp4"],
        official_screenshots=["https://cdn.example.com/screenshot-1.jpg"],
    )
    draft_manifest = build_video_manifest_draft(video_offer)

    first_plan = build_scene_asset_plan(video_offer, draft_manifest)
    second_plan = build_scene_asset_plan(video_offer, draft_manifest)

    assert first_plan == second_plan
    assert first_plan["total_duration_sec"] == 14.5
    assert len(first_plan["scenes"]) == 5
    assert [scene["scene_id"] for scene in first_plan["scenes"]] == [
        "hook",
        "identity",
        "offer_proof",
        "trust_or_deadline",
        "telegram_cta",
    ]


def test_hook_asset_priority_prefers_trailer_and_offer_proof_prefers_card_image(tmp_path: Path) -> None:
    video_offer = _build_video_offer(
        tmp_path,
        official_trailers=["https://cdn.example.com/trailer-1.mp4"],
        official_screenshots=[
            "https://cdn.example.com/screenshot-1.jpg",
            "https://cdn.example.com/screenshot-2.jpg",
        ],
        fallback_image="https://cdn.example.com/fallback-1.jpg",
    )
    draft_manifest = build_video_manifest_draft(video_offer)

    plan = build_scene_asset_plan(video_offer, draft_manifest)

    hook_scene = plan["scenes"][0]
    offer_proof_scene = plan["scenes"][2]
    assert hook_scene["selected_asset_type"] == "trailer"
    assert hook_scene["selected_asset_ref"] == "https://cdn.example.com/trailer-1.mp4"
    assert offer_proof_scene["selected_asset_type"] == "card_image"
    assert offer_proof_scene["selected_asset_ref"] == video_offer.card_image_path


def test_cta_variants_are_preserved(tmp_path: Path) -> None:
    video_offer = _build_video_offer(
        tmp_path,
        official_trailers=["https://cdn.example.com/trailer-1.mp4"],
        official_screenshots=["https://cdn.example.com/screenshot-1.jpg"],
    )
    video_offer.cta = VideoCTA(
        default="See the full deal in Telegram",
        tiktok="Join Telegram for the full deal",
        shorts="Open Telegram for the full post",
        reels="Find the full deal in Telegram",
    )
    draft_manifest = build_video_manifest_draft(video_offer)

    plan = build_scene_asset_plan(video_offer, draft_manifest)

    assert plan["platform_endcards"] == {
        "tiktok": "Join Telegram for the full deal",
        "shorts": "Open Telegram for the full post",
        "reels": "Find the full deal in Telegram",
    }
    assert plan["scenes"][-1]["platform_variants"] == plan["platform_endcards"]


def test_missing_optional_facts_do_not_crash_scene_planning(tmp_path: Path) -> None:
    video_offer = _build_video_offer(
        tmp_path,
        official_screenshots=["https://cdn.example.com/screenshot-1.jpg"],
    )
    video_offer.discount_percent = None
    video_offer.current_price_text = None
    video_offer.old_price_text = None
    video_offer.savings_text = None
    video_offer.deadline_text = None
    video_offer.reviews_text = None
    video_offer.positive_percent_text = None
    video_offer.achievements_text = None
    video_offer.cards_text = None
    draft_manifest = build_video_manifest_draft(video_offer)

    plan = build_scene_asset_plan(video_offer, draft_manifest)

    assert len(plan["scenes"]) == 5
    assert plan["scenes"][3].get("facts", []) == []


def test_card_only_fallback_reuses_card_image_and_adds_warnings(tmp_path: Path) -> None:
    video_offer = _build_video_offer(
        tmp_path,
        official_trailers=[],
        official_screenshots=[],
        fallback_image=None,
    )
    draft_manifest = build_video_manifest_draft(video_offer)

    plan = build_scene_asset_plan(video_offer, draft_manifest)

    assert all(scene["selected_asset_ref"] == video_offer.card_image_path for scene in plan["scenes"])
    assert any("Only the card image is available" in warning for warning in plan["warnings"])


def test_no_visual_asset_fails_clearly(tmp_path: Path) -> None:
    video_offer = _build_video_offer(
        tmp_path,
        official_trailers=[],
        official_screenshots=[],
        fallback_image=None,
    )
    video_offer.card_image_path = ""
    video_offer.visual_assets.card_image = ""
    draft_manifest = build_video_manifest_draft(video_offer)
    video_offer.visual_assets.card_image = ""

    try:
        build_scene_asset_plan(video_offer, draft_manifest)
        raise AssertionError("Expected SceneAssetPlanError")
    except SceneAssetPlanError as exc:
        assert "no visual asset exists" in str(exc)


def test_exporter_writes_scene_plan_only_with_flag(tmp_path: Path) -> None:
    report_path = _write_preview_report(
        tmp_path,
        official_trailers=["https://cdn.example.com/trailer-1.mp4"],
        official_screenshots=["https://cdn.example.com/screenshot-1.jpg"],
    )
    without_flag_dir = tmp_path / "exports" / "without-scene-plan"
    with_flag_dir = tmp_path / "exports" / "with-scene-plan"

    without_flag_result = export_video_offer_artifacts(report_path, output_dir=without_flag_dir)
    with_flag_result = export_video_offer_artifacts(report_path, output_dir=with_flag_dir, with_scene_plan=True)

    assert without_flag_result.scene_asset_plan_json_path is None
    assert not (without_flag_dir / "scene_asset_plan.json").exists()
    assert with_flag_result.scene_asset_plan_json_path == (with_flag_dir / "scene_asset_plan.json").resolve()
    assert with_flag_result.scene_asset_plan_json_path.exists()


def test_cli_with_scene_plan_flag_wires_optional_export(tmp_path: Path, capsys) -> None:
    report_path = _write_preview_report(
        tmp_path,
        official_trailers=["https://cdn.example.com/trailer-1.mp4"],
        official_screenshots=["https://cdn.example.com/screenshot-1.jpg"],
    )
    without_flag_dir = tmp_path / "cli-exports" / "without-scene-plan"
    with_flag_dir = tmp_path / "cli-exports" / "with-scene-plan"

    without_flag_exit = export_video_offer_artifacts_main(
        ["--from-report", str(report_path), "--output-dir", str(without_flag_dir)],
    )
    without_flag_stdout = capsys.readouterr().out
    with_flag_exit = export_video_offer_artifacts_main(
        ["--from-report", str(report_path), "--output-dir", str(with_flag_dir), "--with-scene-plan"],
    )
    with_flag_stdout = capsys.readouterr().out

    assert without_flag_exit == 0
    assert with_flag_exit == 0
    assert "scene_asset_plan_json_path:" not in without_flag_stdout
    assert "scene_asset_plan_json_path:" in with_flag_stdout
    assert not (without_flag_dir / "scene_asset_plan.json").exists()
    assert (with_flag_dir / "scene_asset_plan.json").exists()


def test_scene_planner_does_not_import_old_video_generator_or_network_ffmpeg_telegram_modules(tmp_path: Path) -> None:
    video_offer = _build_video_offer(
        tmp_path,
        official_trailers=["https://cdn.example.com/trailer-1.mp4"],
        official_screenshots=["https://cdn.example.com/screenshot-1.jpg"],
    )
    draft_manifest = build_video_manifest_draft(video_offer)
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
    }

    build_scene_asset_plan(video_offer, draft_manifest)

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
    }
    assert after_modules == before_modules
