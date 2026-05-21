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


def test_preview_artifact_resolver_marks_reused_latest_preview_when_no_new_artifact_exists(tmp_path: Path) -> None:
    analytics_dir = tmp_path / "output" / "analytics"
    truth_path = analytics_dir / "truth.json"
    _write_json(truth_path, {"verdict": {"truth_ready": True}}, mtime=15)
    _write_json(
        analytics_dir / "20260516T160001Z_operator_workflow_preview.json",
        {"command": "preview", "report_path": str(truth_path)},
        mtime=20,
    )

    resolver = PreviewArtifactResolver(tmp_path)
    bundle = resolver.load_preview_run(started_at=999999)

    assert bundle.workflow_path is not None
    assert bundle.reused_latest_preview is True
    assert any("latest known preview" in warning.lower() for warning in bundle.warnings)


def test_build_preview_state_maps_last_publish_successful_workflow(tmp_path: Path) -> None:
    workflow_path = tmp_path / "output" / "analytics" / "20260517T075955Z_operator_workflow_publish-previewed.json"
    publish_outcome_path = tmp_path / "output" / "analytics" / "20260517T075954Z_publish_outcome_steam_264710.json"
    state = build_preview_state(
        ArtifactBundle(
            project_root=tmp_path,
            output_dir=tmp_path / "output",
            latest_publish_workflow_path=workflow_path,
            latest_publish_outcome_path=publish_outcome_path,
            latest_publish_workflow_payload={
                "command": "publish-previewed",
                "status": "ok",
                "published": True,
                "telegram_verified": True,
                "message_id": 182,
                "outbox_status": "published",
                "reason": "published",
                "idempotency_key": "preview-key",
                "caption_hash": "caption-hash",
                "image_hash": "image-hash",
                "image_path": str(tmp_path / "output" / "cards" / "card.png"),
                "source_report_path": str(tmp_path / "output" / "analytics" / "truth.json"),
                "publish_outcome_path": str(publish_outcome_path),
                "selected": {
                    "title": "Subnautica",
                    "offer_id": "steam:264710",
                },
            },
            latest_publish_outcome_payload={
                "offer_id": "steam:264710",
                "title": "Subnautica",
                "message_id": 182,
                "publish_outcome": {
                    "outbox_status": "published",
                    "reason": "published",
                    "idempotency_key": "preview-key",
                    "caption_hash": "caption-hash",
                    "image_hash": "image-hash",
                },
            },
        )
    )

    assert state.last_publish.present is True
    assert state.last_publish.success is True
    assert state.last_publish.title == "Subnautica"
    assert state.last_publish.offer_id == "steam:264710"
    assert state.last_publish.message_id == 182
    assert state.last_publish.published is True
    assert state.last_publish.telegram_verified is True
    assert state.last_publish.outbox_status == "published"
    assert state.last_publish.reason == "published"
    assert state.last_publish.idempotency_key == "preview-key"
    assert state.last_publish.caption_hash == "caption-hash"
    assert state.last_publish.image_hash == "image-hash"
    assert state.last_publish.image_path == tmp_path / "output" / "cards" / "card.png"
    assert state.last_publish.workflow_path == workflow_path
    assert state.last_publish.publish_outcome_path == publish_outcome_path


def test_build_preview_state_exposes_blocked_selection_diagnostics(tmp_path: Path) -> None:
    state = build_preview_state(
        ArtifactBundle(
            project_root=tmp_path,
            output_dir=tmp_path / "output",
            truth_payload={
                "selection": {
                    "blocked_candidates": [
                        {
                            "offer_id": "steam:413150",
                            "title": "Stardew Valley",
                            "blocker_reason": "already_published",
                            "blocker_detail": (
                                "blocked:already_published_recently "
                                "game_id=413150 dedup_reason=duplicate_within_game_cooldown"
                            ),
                        }
                    ],
                    "blocker_reason": "already_published",
                    "blocker_detail": "blocked:already_published_recently",
                },
                "verdict": {
                    "verdict": "truthful_send_test_blocked",
                    "truth_ready": False,
                    "telegram_verified": False,
                    "blocker_reason": "already_published",
                },
            },
        )
    )

    assert any(
        "blocked:already_published offer_id=steam:413150" in diagnostic
        and "blocked:already_published_recently" in diagnostic
        for diagnostic in state.selection_diagnostics
    )
    assert any(
        diagnostic == "selection_blocker:already_published detail=blocked:already_published_recently"
        for diagnostic in state.selection_diagnostics
    )


def test_build_preview_state_handles_missing_last_publish_workflow(tmp_path: Path) -> None:
    state = build_preview_state(
        ArtifactBundle(
            project_root=tmp_path,
            output_dir=tmp_path / "output",
        )
    )

    assert state.last_publish.present is False
    assert state.last_publish.workflow_path is None
    assert state.last_publish.publish_outcome_path is None


def test_build_preview_state_maps_failed_last_publish_workflow(tmp_path: Path) -> None:
    workflow_path = tmp_path / "output" / "analytics" / "20260517T075955Z_operator_workflow_publish-previewed.json"
    state = build_preview_state(
        ArtifactBundle(
            project_root=tmp_path,
            output_dir=tmp_path / "output",
            latest_publish_workflow_path=workflow_path,
            latest_publish_workflow_payload={
                "command": "publish-previewed",
                "status": "failed",
                "published": False,
                "telegram_verified": False,
                "message_id": None,
                "outbox_status": "failed",
                "reason": "image_missing",
                "selected": {
                    "title": "Subnautica",
                    "offer_id": "steam:264710",
                },
            },
        )
    )

    assert state.last_publish.present is True
    assert state.last_publish.success is False
    assert state.last_publish.workflow_status == "failed"
    assert state.last_publish.published is False
    assert state.last_publish.telegram_verified is False
    assert state.last_publish.reason == "image_missing"
    assert state.last_publish.outbox_status == "failed"


def test_publish_history_is_sorted_newest_first_and_limited_to_five(tmp_path: Path) -> None:
    analytics_dir = tmp_path / "output" / "analytics"
    expected_offer_ids: list[str] = []
    for index in range(6):
        offer_id = f"steam:{200 + index}"
        expected_offer_ids.insert(0, offer_id)
        publish_outcome_path = analytics_dir / f"20260517T0800{index}Z_publish_outcome_{offer_id.replace(':', '_')}.json"
        _write_json(
            publish_outcome_path,
            {
                "offer_id": offer_id,
                "title": f"Title {index}",
                "message_id": 100 + index,
                "publish_outcome": {
                    "outbox_status": "published",
                    "reason": "published",
                },
            },
            mtime=20 + index,
        )
        _write_json(
            analytics_dir / f"20260517T0800{index}Z_operator_workflow_publish-previewed.json",
            {
                "command": "publish-previewed",
                "status": "ok",
                "published": True,
                "telegram_verified": True,
                "message_id": 100 + index,
                "outbox_status": "published",
                "reason": "published",
                "created_at": f"2026-05-17T08:00:0{index}",
                "publish_outcome_path": str(publish_outcome_path),
                "selected": {
                    "title": f"Title {index}",
                    "offer_id": offer_id,
                },
            },
            mtime=30 + index,
        )

    resolver = PreviewArtifactResolver(tmp_path)
    bundle = resolver.load_latest_local_state()
    state = build_preview_state(bundle)

    assert len(state.publish_history) == 5
    assert [entry.offer_id for entry in state.publish_history] == expected_offer_ids[:5]
    assert state.last_publish.offer_id == expected_offer_ids[0]
    assert state.last_publish.message_id == 105


def test_publish_history_normalizes_successful_and_failed_workflows(tmp_path: Path) -> None:
    analytics_dir = tmp_path / "output" / "analytics"
    failed_workflow = analytics_dir / "20260517T090001Z_operator_workflow_publish-previewed.json"
    success_workflow = analytics_dir / "20260517T090000Z_operator_workflow_publish-previewed.json"
    success_outcome = analytics_dir / "20260517T090000Z_publish_outcome_steam_264710.json"
    _write_json(
        success_outcome,
        {
            "offer_id": "steam:264710",
            "title": "Subnautica",
            "message_id": 182,
            "publish_outcome": {
                "outbox_status": "published",
                "reason": "published",
            },
        },
        mtime=40,
    )
    _write_json(
        success_workflow,
        {
            "command": "publish-previewed",
            "status": "ok",
            "published": True,
            "telegram_verified": True,
            "message_id": 182,
            "outbox_status": "published",
            "reason": "published",
            "publish_outcome_path": str(success_outcome),
            "selected": {
                "title": "Subnautica",
                "offer_id": "steam:264710",
            },
        },
        mtime=50,
    )
    _write_json(
        failed_workflow,
        {
            "command": "publish-previewed",
            "status": "failed",
            "published": False,
            "telegram_verified": False,
            "reason": "report_not_found",
            "selected": {},
        },
        mtime=60,
    )

    resolver = PreviewArtifactResolver(tmp_path)
    state = build_preview_state(resolver.load_latest_local_state())

    assert len(state.publish_history) == 2
    failed_entry = state.publish_history[0]
    success_entry = state.publish_history[1]
    assert failed_entry.offer_id == ""
    assert failed_entry.title == ""
    assert failed_entry.reason == "report_not_found"
    assert failed_entry.success is False
    assert success_entry.offer_id == "steam:264710"
    assert success_entry.title == "Subnautica"
    assert success_entry.message_id == 182
    assert success_entry.success is True
