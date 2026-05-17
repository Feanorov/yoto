from __future__ import annotations

import json
import os
from pathlib import Path

from dealbot.operator_ui.artifact_resolver import PreviewArtifactResolver
from dealbot.operator_ui.models import ArtifactBundle
from dealbot.operator_ui.report_parser import build_preview_state


def _write_json(path: Path, payload: dict, *, mtime: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


def test_build_preview_state_maps_discount_preview_payload(tmp_path: Path) -> None:
    card_path = tmp_path / "output" / "cards" / "card.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"card")

    bundle = ArtifactBundle(
        project_root=tmp_path,
        output_dir=tmp_path / "output",
        workflow_path=tmp_path / "output" / "analytics" / "workflow.json",
        truth_report_path=tmp_path / "output" / "analytics" / "truth.json",
        workflow_payload={
            "status": "ok",
            "verdict": "truthful_send_test_ready",
            "report_path": str(tmp_path / "output" / "analytics" / "truth.json"),
            "card_path": str(card_path),
            "caption_preview": "Caption preview",
        },
        truth_payload={
            "run_key": "20260516T162637Z",
            "created_at": "2026-05-16T16:26:37",
            "ingest_sources": {
                "steam": {"status": "healthy", "reason": "healthy", "offers": 2000},
                "epic": {"status": "healthy", "reason": "healthy", "offers": 7},
            },
            "send_test_target": {
                "candidate": {
                    "title": "Euro Truck Simulator 2",
                    "offer_id": "steam:227300",
                    "source": "steam",
                    "lane": "high_value_discount",
                    "bucket": "planned",
                    "content_family": "discount",
                    "store_url": "https://store.steampowered.com/app/227300/Euro_Truck_Simulator_2/",
                },
                "artifact": {
                    "offer_id": "steam:227300",
                    "image_path": str(card_path),
                    "caption_html": "<b>Euro Truck Simulator 2</b>",
                    "caption_preview": "Euro Truck Simulator 2 preview",
                    "caption_hash": "caption-hash",
                    "image_hash": "image-hash",
                    "idempotency_key": "preview-key",
                    "card_family": "DISCOUNT",
                    "template_id": "steam_discount",
                },
            },
            "pinned_publish": {
                "contract_version": 1,
                "source": "preview",
                "created_at": "2026-05-16T16:26:37",
                "report_run_key": "20260516T162637Z",
                "candidate": {
                    "title": "Euro Truck Simulator 2",
                    "offer_id": "steam:227300",
                },
                "offer_snapshot": {
                    "offer_id": "steam:227300",
                },
                "decision_snapshot": {
                    "lane": "high_value_discount",
                },
                "artifact": {
                    "offer_id": "steam:227300",
                    "image_path": str(card_path),
                    "caption_html": "<b>Euro Truck Simulator 2</b>",
                    "caption_preview": "Euro Truck Simulator 2 preview",
                    "caption_hash": "caption-hash",
                    "image_hash": "image-hash",
                    "idempotency_key": "preview-key",
                    "template_id": "steam_discount",
                    "card_family": "DISCOUNT",
                    "assets_used": ["https://example.com/hero.png"],
                    "render_diagnostics": {"source": "test"},
                    "caption_debug": {"provider": "test"},
                },
                "validation": {
                    "image_exists": True,
                    "caption_hash_verified": True,
                    "image_hash_verified": True,
                },
            },
            "verdict": {
                "verdict": "truthful_send_test_ready",
                "truth_ready": True,
                "telegram_verified": False,
            },
        },
    )

    state = build_preview_state(bundle)

    assert state.status_text == "Preview Ready"
    assert state.post_type_label == "Single Discount"
    assert state.selected_target is not None
    assert state.selected_target.offer_id == "steam:227300"
    assert state.card_exists is True
    assert state.caption_html == "<b>Euro Truck Simulator 2</b>"
    assert [item.name for item in state.ingest_sources] == ["steam", "epic"]
    assert state.pinned_publish.contract_version == 1
    assert state.pinned_publish.idempotency_key == "preview-key"
    assert state.pinned_publish.caption_hash == "caption-hash"
    assert state.pinned_publish.image_hash == "image-hash"
    assert state.pinned_publish.image_exists is True
    assert state.pinned_publish.caption_hash_verified is True
    assert state.pinned_publish.image_hash_verified is True
    assert state.fingerprint is not None
    assert state.fingerprint.report_path == bundle.truth_report_path
    assert state.fingerprint.offer_id == "steam:227300"
    assert state.fingerprint.idempotency_key == "preview-key"
    assert state.fingerprint.caption_hash == "caption-hash"
    assert state.fingerprint.image_hash == "image-hash"
    assert state.fingerprint.image_path == card_path


def test_preview_artifact_resolver_marks_ambiguous_preview_run(tmp_path: Path) -> None:
    analytics_dir = tmp_path / "output" / "analytics"
    truth_path = tmp_path / "output" / "analytics" / "truth.json"
    _write_json(truth_path, {"verdict": {"truth_ready": True}}, mtime=15)
    _write_json(
        analytics_dir / "20260516T160001Z_operator_workflow_preview.json",
        {"command": "preview", "report_path": str(truth_path)},
        mtime=20,
    )
    _write_json(
        analytics_dir / "20260516T160002Z_operator_workflow_preview.json",
        {"command": "preview", "report_path": str(truth_path)},
        mtime=21,
    )

    resolver = PreviewArtifactResolver(tmp_path)
    bundle = resolver.load_preview_run(started_at=10)

    assert bundle.ambiguous is True
    assert bundle.workflow_path is not None
    assert any("ambiguous" in warning.lower() for warning in bundle.warnings)
