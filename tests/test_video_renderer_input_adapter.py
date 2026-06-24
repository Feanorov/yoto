from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

from dealbot.video import (
    RendererInputAdapterError,
    VideoCTA,
    build_renderer_input,
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
    title: str = "Renderer Input Test Game",
    current_price: int | None = 14900,
    old_price: int | None = 29900,
    discount: int | None = 50,
    reviews: int | None = 42000,
    positive_pct: int | None = 94,
    promo_end: str | None = "2026-06-25T18:00:00",
    official_trailers: list[str] | None = None,
    official_screenshots: list[str] | None = None,
    fallback_image: str | None = "https://cdn.example.com/renderer-fallback.jpg",
) -> dict:
    trailers = list(official_trailers or ["https://cdn.example.com/renderer-trailer.mp4"])
    screenshots = list(official_screenshots or ["https://cdn.example.com/renderer-screenshot.jpg"])
    assets: dict[str, str] = {}
    if screenshots:
        assets["hero"] = screenshots[0]
        assets["screenshot"] = screenshots[0]
    if fallback_image:
        assets["fallback"] = fallback_image

    candidate = {
        "title": title,
        "offer_id": "steam:renderer-input-test",
        "source": "steam",
        "platform": "steam",
        "store_url": "https://store.steampowered.com/app/40",
        "discount": discount,
        "current_price": current_price,
        "old_price": old_price,
        "reviews": reviews,
        "positive_pct": positive_pct,
    }
    artifact = {
        "offer_id": "steam:renderer-input-test",
        "caption_html": "<b>Renderer Input Test Game</b>",
        "caption_hash": "renderer-caption-hash",
        "image_hash": "renderer-image-hash",
        "idempotency_key": "renderer-offer-key",
        "image_path": str(card_path),
        "assets_used": list(screenshots),
        "render_diagnostics": {},
        "card_family": "DISCOUNT",
        "template_id": "steam_discount",
    }
    offer_snapshot = {
        "offer_id": "steam:renderer-input-test",
        "source": "steam",
        "title": title,
        "store_url": "https://store.steampowered.com/app/40",
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
        "run_key": "20260625T160000Z",
        "created_at": "2026-06-25T16:00:00",
        "send_test_target": {
            "candidate": dict(candidate),
            "artifact": dict(artifact),
        },
        "pinned_publish": {
            "contract_version": 1,
            "source": "preview",
            "created_at": "2026-06-25T16:00:00",
            "report_run_key": "20260625T160000Z",
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


def _build_video_offer(tmp_path: Path, **kwargs):
    card_path = tmp_path / "cards" / "renderer-input-card.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"renderer-input-card")
    report = _build_preview_report_payload(card_path, **kwargs)
    return build_video_offer_from_preview_report(report)


def _build_renderer_contracts(tmp_path: Path, **kwargs):
    video_offer = _build_video_offer(tmp_path, **kwargs)
    draft_manifest = build_video_manifest_draft(video_offer)
    scene_asset_plan = build_scene_asset_plan(video_offer, draft_manifest)
    scene_layout_payload = build_scene_layout_payload(video_offer, scene_asset_plan)
    renderer_input = build_renderer_input(video_offer, scene_asset_plan, scene_layout_payload)
    return video_offer, scene_asset_plan, scene_layout_payload, renderer_input


def _write_preview_report(tmp_path: Path, **kwargs) -> Path:
    card_path = tmp_path / "cards" / "renderer-input-card.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"renderer-input-card")
    report_path = tmp_path / "output" / "analytics" / "renderer-input-preview.json"
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


def test_renderer_input_has_exactly_five_scenes_with_deterministic_order_canvas_and_fps(tmp_path: Path) -> None:
    video_offer = _build_video_offer(tmp_path)
    draft_manifest = build_video_manifest_draft(video_offer)
    scene_asset_plan = build_scene_asset_plan(video_offer, draft_manifest)
    scene_layout_payload = build_scene_layout_payload(video_offer, scene_asset_plan)

    first_renderer_input = build_renderer_input(video_offer, scene_asset_plan, scene_layout_payload)
    second_renderer_input = build_renderer_input(video_offer, scene_asset_plan, scene_layout_payload)

    assert first_renderer_input == second_renderer_input
    assert first_renderer_input["schema_version"] == 1
    assert first_renderer_input["fps"] == 30
    assert first_renderer_input["canvas"] == {"width": 1080, "height": 1920}
    assert [scene["scene_id"] for scene in first_renderer_input["scenes"]] == [
        "hook",
        "identity",
        "offer_proof",
        "trust_or_deadline",
        "telegram_cta",
    ]
    assert [scene["order"] for scene in first_renderer_input["scenes"]] == [1, 2, 3, 4, 5]


def test_renderer_input_calculates_cumulative_timestamps_and_final_end_matches_total_duration(
    tmp_path: Path,
) -> None:
    _, _, _, renderer_input = _build_renderer_contracts(tmp_path)

    assert [scene["start_sec"] for scene in renderer_input["scenes"]] == [0.0, 2.0, 4.5, 7.5, 10.5]
    assert [scene["end_sec"] for scene in renderer_input["scenes"]] == [2.0, 4.5, 7.5, 10.5, 14.5]
    assert [scene["duration_sec"] for scene in renderer_input["scenes"]] == [2.0, 2.5, 3.0, 3.0, 4.0]
    assert renderer_input["scenes"][-1]["end_sec"] == renderer_input["total_duration_sec"] == 14.5


def test_renderer_scene_data_and_cta_variants_are_preserved(tmp_path: Path) -> None:
    video_offer = _build_video_offer(tmp_path)
    video_offer.cta = VideoCTA(
        default="See the full deal in Telegram",
        tiktok="Join Telegram for the full deal",
        shorts="Open Telegram for the full post",
        reels="Find the full deal in Telegram",
    )
    draft_manifest = build_video_manifest_draft(video_offer)
    scene_asset_plan = build_scene_asset_plan(video_offer, draft_manifest)
    scene_layout_payload = build_scene_layout_payload(video_offer, scene_asset_plan)
    renderer_input = build_renderer_input(video_offer, scene_asset_plan, scene_layout_payload)

    hook_layout_scene = _scene(scene_layout_payload, "hook")
    hook_renderer_scene = _scene(renderer_input, "hook")
    cta_layout_scene = _scene(scene_layout_payload, "telegram_cta")
    cta_renderer_scene = _scene(renderer_input, "telegram_cta")

    assert hook_renderer_scene["visual"] == hook_layout_scene["selected_visual"]
    assert hook_renderer_scene["text_blocks"] == hook_layout_scene["text_blocks"]
    assert hook_renderer_scene["safe_zone_profile"] == hook_layout_scene["safe_zone_profile"]
    assert hook_renderer_scene["motion"] == {"hint": hook_layout_scene["motion_hint"]}
    assert cta_renderer_scene["platform_variants"] == cta_layout_scene["platform_variants"]


def test_missing_optional_facts_do_not_crash_and_do_not_fabricate_renderer_text(tmp_path: Path) -> None:
    video_offer, scene_asset_plan, scene_layout_payload, renderer_input = _build_renderer_contracts(
        tmp_path,
        current_price=None,
        old_price=None,
        discount=None,
        reviews=None,
        positive_pct=None,
        promo_end=None,
    )

    offer_scene = _scene(renderer_input, "offer_proof")
    trust_scene = _scene(renderer_input, "trust_or_deadline")
    serialized = json.dumps(renderer_input)

    assert offer_scene["text_blocks"] == []
    assert trust_scene["text_blocks"] == []
    assert "Now:" not in serialized
    assert "Was:" not in serialized
    assert "Save:" not in serialized
    assert video_offer.store_url not in serialized
    assert scene_asset_plan["total_duration_sec"] == scene_layout_payload["total_duration_sec"] == renderer_input["total_duration_sec"]


@pytest.mark.parametrize(
    ("label", "mutator", "expected_text"),
    [
        (
            "scene_id",
            lambda asset_plan, layout_payload: layout_payload["scenes"][0].__setitem__("scene_id", "wrong_scene"),
            "scene_layout_payload scene index 0 must be scene_id='hook'",
        ),
        (
            "order",
            lambda asset_plan, layout_payload: asset_plan["scenes"][0].__setitem__("order", 99),
            "scene_asset_plan order mismatch",
        ),
        (
            "scene_type",
            lambda asset_plan, layout_payload: layout_payload["scenes"][0].__setitem__("scene_type", "wrong_type"),
            "scene_type mismatch",
        ),
        (
            "duration",
            lambda asset_plan, layout_payload: layout_payload["scenes"][0].__setitem__("duration_sec", 9.0),
            "duration mismatch",
        ),
        (
            "selected_visual",
            lambda asset_plan, layout_payload: layout_payload["scenes"][0]["selected_visual"].__setitem__(
                "asset_ref",
                "https://cdn.example.com/other-asset.jpg",
            ),
            "selected visual mismatch",
        ),
    ],
)
def test_mismatched_scene_contracts_fail_clearly(
    tmp_path: Path,
    label: str,
    mutator,
    expected_text: str,
) -> None:
    video_offer = _build_video_offer(tmp_path)
    draft_manifest = build_video_manifest_draft(video_offer)
    scene_asset_plan = build_scene_asset_plan(video_offer, draft_manifest)
    scene_layout_payload = build_scene_layout_payload(video_offer, scene_asset_plan)

    mutated_asset_plan = copy.deepcopy(scene_asset_plan)
    mutated_layout_payload = copy.deepcopy(scene_layout_payload)
    mutator(mutated_asset_plan, mutated_layout_payload)

    with pytest.raises(RendererInputAdapterError) as excinfo:
        build_renderer_input(video_offer, mutated_asset_plan, mutated_layout_payload)

    assert expected_text in str(excinfo.value), label


def test_renderer_file_is_exported_only_with_flag_and_flag_implies_scene_plan_and_layout_payload(
    tmp_path: Path,
) -> None:
    report_path = _write_preview_report(tmp_path)
    default_dir = tmp_path / "exports" / "default"
    layout_dir = tmp_path / "exports" / "layout"
    renderer_dir = tmp_path / "exports" / "renderer"

    default_result = export_video_offer_artifacts(report_path, output_dir=default_dir)
    layout_result = export_video_offer_artifacts(report_path, output_dir=layout_dir, with_layout_payload=True)
    renderer_result = export_video_offer_artifacts(report_path, output_dir=renderer_dir, with_renderer_input=True)

    assert default_result.scene_asset_plan_json_path is None
    assert default_result.scene_layout_payload_json_path is None
    assert default_result.renderer_input_json_path is None
    assert default_result.renderer_scene_count is None
    assert default_result.renderer_total_duration_sec is None
    assert not (default_dir / "renderer_input.json").exists()

    assert layout_result.scene_asset_plan_json_path == (layout_dir / "scene_asset_plan.json").resolve()
    assert layout_result.scene_layout_payload_json_path == (layout_dir / "scene_layout_payload.json").resolve()
    assert layout_result.renderer_input_json_path is None
    assert not (layout_dir / "renderer_input.json").exists()

    assert renderer_result.scene_asset_plan_json_path == (renderer_dir / "scene_asset_plan.json").resolve()
    assert renderer_result.scene_layout_payload_json_path == (renderer_dir / "scene_layout_payload.json").resolve()
    assert renderer_result.renderer_input_json_path == (renderer_dir / "renderer_input.json").resolve()
    assert renderer_result.renderer_input_json_path.exists()
    assert renderer_result.renderer_scene_count == 5
    assert renderer_result.renderer_total_duration_sec == 14.5

    exported_renderer_input = json.loads(renderer_result.renderer_input_json_path.read_text(encoding="utf-8"))
    assert exported_renderer_input["fps"] == 30
    assert exported_renderer_input["canvas"] == {"height": 1920, "width": 1080}
    assert exported_renderer_input["total_duration_sec"] == 14.5


def test_cli_with_renderer_input_flag_wires_optional_export(tmp_path: Path, capsys) -> None:
    report_path = _write_preview_report(tmp_path)
    default_dir = tmp_path / "cli-exports" / "default"
    renderer_dir = tmp_path / "cli-exports" / "renderer"

    default_exit = export_video_offer_artifacts_main(
        ["--from-report", str(report_path), "--output-dir", str(default_dir)],
    )
    default_stdout = capsys.readouterr().out
    renderer_exit = export_video_offer_artifacts_main(
        ["--from-report", str(report_path), "--output-dir", str(renderer_dir), "--with-renderer-input"],
    )
    renderer_stdout = capsys.readouterr().out

    assert default_exit == 0
    assert renderer_exit == 0
    assert "scene_asset_plan_json_path:" not in default_stdout
    assert "scene_layout_payload_json_path:" not in default_stdout
    assert "renderer_input_json_path:" not in default_stdout
    assert "renderer_scene_count:" not in default_stdout
    assert "renderer_total_duration_sec:" not in default_stdout

    assert "scene_asset_plan_json_path:" in renderer_stdout
    assert "scene_layout_payload_json_path:" in renderer_stdout
    assert "renderer_input_json_path:" in renderer_stdout
    assert "renderer_scene_count: 5" in renderer_stdout
    assert "renderer_total_duration_sec: 14.5" in renderer_stdout
    assert (renderer_dir / "renderer_input.json").exists()


def test_renderer_input_adapter_does_not_import_old_video_generator_or_network_ffmpeg_telegram_pillow_modules(
    tmp_path: Path,
) -> None:
    video_offer = _build_video_offer(tmp_path)
    draft_manifest = build_video_manifest_draft(video_offer)
    scene_asset_plan = build_scene_asset_plan(video_offer, draft_manifest)
    scene_layout_payload = build_scene_layout_payload(video_offer, scene_asset_plan)
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

    build_renderer_input(video_offer, scene_asset_plan, scene_layout_payload)

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
