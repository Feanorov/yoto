from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from dealbot.video import VideoOfferExportError, export_video_offer_artifacts


def _build_preview_report_payload(card_path: Path) -> dict:
    return {
        "run_key": "20260525T143000Z",
        "created_at": "2026-05-25T14:30:00",
        "send_test_target": {
            "candidate": {
                "title": "Export Test Game",
                "offer_id": "steam:export-test",
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
                "offer_id": "steam:export-test",
                "caption_html": "<b>Export Test Game</b>",
                "caption_hash": "export-caption-hash",
                "image_hash": "export-image-hash",
                "idempotency_key": "export-offer-key",
                "image_path": str(card_path),
                "assets_used": [
                    "https://cdn.example.com/export-screenshot.jpg",
                    "https://cdn.example.com/export-hero.jpg",
                ],
                "render_diagnostics": {
                    "hero_asset_used": "https://cdn.example.com/export-hero.jpg",
                },
                "card_family": "DISCOUNT",
                "template_id": "steam_discount",
            },
        },
        "pinned_publish": {
            "contract_version": 1,
            "source": "preview",
            "created_at": "2026-05-25T14:30:00",
            "report_run_key": "20260525T143000Z",
            "candidate": {
                "title": "Export Test Game",
                "offer_id": "steam:export-test",
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
                "offer_id": "steam:export-test",
                "source": "steam",
                "title": "Export Test Game",
                "store_url": "https://store.steampowered.com/app/20",
                "currency": "UAH",
                "price_after_minor": 14900,
                "price_before_minor": 29900,
                "discount_percent": 50,
                "promo_end": "2026-05-30T18:00:00",
                "review_score": 94,
                "review_count": 42000,
                "achievements_count": 55,
                "has_trading_cards": True,
                "assets": {
                    "hero": "https://cdn.example.com/export-hero.jpg",
                    "header": "https://cdn.example.com/export-header.jpg",
                    "screenshot": "https://cdn.example.com/export-screenshot.jpg",
                    "fallback": "https://cdn.example.com/export-fallback.jpg",
                },
                "metadata": {
                    "official_trailers": ["https://cdn.example.com/export-trailer.mp4"],
                    "official_screenshots": ["https://cdn.example.com/export-screenshot.jpg"],
                },
            },
            "decision_snapshot": {
                "lane": "high_value_discount",
                "template_id": "steam_discount",
            },
            "artifact": {
                "offer_id": "steam:export-test",
                "caption_html": "<b>Export Test Game</b>",
                "caption_hash": "export-caption-hash",
                "image_hash": "export-image-hash",
                "idempotency_key": "export-offer-key",
                "image_path": str(card_path),
                "assets_used": [
                    "https://cdn.example.com/export-screenshot.jpg",
                    "https://cdn.example.com/export-hero.jpg",
                ],
                "render_diagnostics": {
                    "hero_asset_used": "https://cdn.example.com/export-hero.jpg",
                },
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


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def test_exports_video_offer_and_manifest_json_from_preview_report(tmp_path: Path) -> None:
    card_path = tmp_path / "cards" / "export-card.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"export-card")
    report_path = _write_json(
        tmp_path / "output" / "analytics" / "20260525T143000Z_operator_truth_report_preview.json",
        _build_preview_report_payload(card_path),
    )
    output_dir = tmp_path / "exports" / "manual_run"

    result = export_video_offer_artifacts(report_path, output_dir=output_dir)

    assert result.source_report_path == report_path.resolve()
    assert result.output_dir == output_dir.resolve()
    assert result.video_offer_json_path.exists()
    assert result.draft_manifest_json_path.exists()
    assert result.offer_id == "steam:export-test"
    assert result.template == "single_offer_gameplay_first"
    assert result.scene_count == 5


def test_exported_files_are_valid_json_and_preserve_identity_fields(tmp_path: Path) -> None:
    card_path = tmp_path / "cards" / "export-card.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"export-card")
    report_path = _write_json(
        tmp_path / "output" / "analytics" / "preview.json",
        _build_preview_report_payload(card_path),
    )
    output_dir = tmp_path / "exports"

    result = export_video_offer_artifacts(report_path, output_dir=output_dir)
    video_offer_payload = json.loads(result.video_offer_json_path.read_text(encoding="utf-8"))
    manifest_payload = json.loads(result.draft_manifest_json_path.read_text(encoding="utf-8"))

    assert video_offer_payload["title"] == "Export Test Game"
    assert video_offer_payload["image_hash"] == "export-image-hash"
    assert video_offer_payload["caption_hash"] == "export-caption-hash"
    assert video_offer_payload["idempotency_key"] == "export-offer-key"
    assert len(manifest_payload["scenes"]) == 5


def test_exporter_resolves_preview_report_from_operator_workflow_report(tmp_path: Path) -> None:
    card_path = tmp_path / "cards" / "workflow-card.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"workflow-card")
    report_path = _write_json(
        tmp_path / "output" / "analytics" / "20260525T143000Z_operator_truth_report_preview.json",
        _build_preview_report_payload(card_path),
    )
    workflow_path = _write_json(
        tmp_path / "output" / "analytics" / "20260525T143100Z_operator_workflow_preview-selected.json",
        {
            "command": "preview-selected",
            "status": "ok",
            "report_path": str(report_path),
        },
    )

    result = export_video_offer_artifacts(workflow_path, output_dir=tmp_path / "exports")

    assert result.source_report_path == report_path.resolve()
    assert result.video_offer_json_path.exists()
    assert result.draft_manifest_json_path.exists()


def test_exporter_accepts_utf8_bom_preview_report(tmp_path: Path) -> None:
    card_path = tmp_path / "cards" / "bom-card.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"bom-card")
    report_path = tmp_path / "output" / "analytics" / "bom-preview.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(_build_preview_report_payload(card_path), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8-sig",
    )

    result = export_video_offer_artifacts(report_path, output_dir=tmp_path / "exports")

    assert result.video_offer_json_path.exists()
    assert result.draft_manifest_json_path.exists()


def test_default_output_dir_uses_safe_project_output_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    card_path = tmp_path / "cards" / "default-output-card.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"default-card")
    report_path = _write_json(
        tmp_path / "input" / "preview.json",
        _build_preview_report_payload(card_path),
    )
    monkeypatch.chdir(tmp_path)

    result = export_video_offer_artifacts(report_path)

    assert result.output_dir == (tmp_path / "output" / "video_offer_exports" / "preview").resolve()
    assert result.video_offer_json_path.exists()
    assert result.draft_manifest_json_path.exists()


def test_missing_source_report_fails_clearly(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.json"

    with pytest.raises(FileNotFoundError) as excinfo:
        export_video_offer_artifacts(missing_path, output_dir=tmp_path / "exports")

    assert "source report does not exist" in str(excinfo.value)
    assert not (tmp_path / "exports").exists()


def test_invalid_broken_report_fails_clearly_without_partial_artifacts(tmp_path: Path) -> None:
    broken_report_path = _write_json(
        tmp_path / "output" / "analytics" / "broken.json",
        {"mode": "preview", "created_at": "2026-05-25T15:00:00"},
    )
    output_dir = tmp_path / "exports" / "broken"

    with pytest.raises(VideoOfferExportError) as excinfo:
        export_video_offer_artifacts(broken_report_path, output_dir=output_dir)

    assert "does not point to one via report_path" in str(excinfo.value)
    assert not output_dir.exists()


def test_exporter_does_not_import_old_video_generator_or_network_ffmpeg_telegram_modules(tmp_path: Path) -> None:
    card_path = tmp_path / "cards" / "isolation-card.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"isolation-card")
    report_path = _write_json(
        tmp_path / "output" / "analytics" / "preview.json",
        _build_preview_report_payload(card_path),
    )
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

    export_video_offer_artifacts(report_path, output_dir=tmp_path / "exports")

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
