from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import (
    ArtifactBundle,
    PreviewFingerprint,
    PreviewPaths,
    PreviewState,
    SelectedTarget,
    SourceHealth,
)


def build_preview_state(bundle: ArtifactBundle) -> PreviewState:
    workflow = _as_dict(bundle.workflow_payload)
    truth = _as_dict(bundle.truth_payload)
    verdict = _as_dict(truth.get("verdict"))
    selection = _as_dict(truth.get("selection"))
    target = _as_dict(truth.get("send_test_target"))
    artifact = _as_dict(target.get("artifact"))
    candidate = _select_candidate(workflow, selection, target)
    card_path = _path_or_none(artifact.get("image_path") or workflow.get("card_path"))
    caption_html = _text(artifact.get("caption_html"))
    caption_preview = _text(artifact.get("caption_preview") or workflow.get("caption_preview"))
    card_family = _text(artifact.get("card_family")).upper()
    template_id = _text(artifact.get("template_id"))
    post_type_key, post_type_label = _derive_post_type(candidate, card_family, template_id)
    warnings = list(bundle.warnings)
    if card_path is None:
        warnings.append("Preview card path is missing.")
    elif not card_path.exists():
        warnings.append("Preview card file is missing on disk.")
    if not caption_html and not caption_preview:
        warnings.append("Preview caption is missing.")
    if post_type_key == "unknown":
        warnings.append("Selected post type is Unknown/Unsupported.")

    status_text = _derive_status_text(
        verdict_name=_text(verdict.get("verdict") or workflow.get("verdict")),
        truth_ready=bool(verdict.get("truth_ready", workflow.get("truth_ready"))),
        telegram_verified=bool(verdict.get("telegram_verified", workflow.get("telegram_verified"))),
        command_status=_text(workflow.get("status")),
    )
    selected_target = _build_selected_target(candidate)
    report_path = bundle.truth_report_path or bundle.workflow_path
    state = PreviewState(
        project_root=bundle.project_root,
        status_text=status_text,
        verdict=_text(verdict.get("verdict") or workflow.get("verdict")),
        truth_ready=bool(verdict.get("truth_ready", workflow.get("truth_ready"))),
        telegram_verified=bool(verdict.get("telegram_verified", workflow.get("telegram_verified"))),
        post_type_key=post_type_key,
        post_type_label=post_type_label,
        selected_target=selected_target,
        caption_html=caption_html,
        caption_preview=caption_preview,
        caption_hash=_text(artifact.get("caption_hash")) or None,
        card_path=card_path,
        card_exists=bool(card_path and card_path.exists()),
        blocker_category=_text(verdict.get("blocker_category")) or None,
        blocker_reason=_text(verdict.get("blocker_reason")) or None,
        blocker_detail=_text(verdict.get("blocker_detail")) or None,
        ingest_sources=_build_ingest_sources(truth),
        paths=PreviewPaths(
            workflow_path=bundle.workflow_path,
            truth_report_path=report_path,
            image_path=card_path,
            latest_snapshot_manifest_path=bundle.latest_snapshot_manifest_path,
            latest_publish_outcome_path=bundle.latest_publish_outcome_path,
            output_dir=bundle.output_dir,
        ),
        ambiguous=bundle.ambiguous,
        stale=bundle.stale,
        warnings=_dedupe(warnings),
        run_key=_text(truth.get("run_key")) or None,
        created_at=_text(truth.get("created_at")) or None,
        command_status=_text(workflow.get("status")),
        report_exists=bool(report_path and report_path.exists()),
    )
    state.fingerprint = PreviewFingerprint(
        workflow_path=bundle.workflow_path,
        truth_report_path=state.paths.truth_report_path,
        run_key=state.run_key,
        selected_offer_id=state.selected_target.offer_id if state.selected_target else None,
        caption_hash=state.caption_hash,
        image_path=state.card_path,
    )
    return state


def _select_candidate(
    workflow: dict[str, Any],
    selection: dict[str, Any],
    target: dict[str, Any],
) -> dict[str, Any]:
    candidate = _as_dict(target.get("candidate"))
    if candidate:
        return candidate
    candidate = _as_dict(selection.get("selected_candidate"))
    if candidate:
        return candidate
    return _as_dict(workflow.get("selected"))


def _build_selected_target(candidate: dict[str, Any]) -> SelectedTarget | None:
    if not candidate:
        return None
    title = _text(candidate.get("title"))
    offer_id = _text(candidate.get("offer_id"))
    if not title and not offer_id:
        return None
    return SelectedTarget(
        title=title,
        offer_id=offer_id,
        source=_text(candidate.get("source")),
        lane=_text(candidate.get("lane")),
        bucket=_text(candidate.get("bucket")),
        content_family=_text(candidate.get("content_family")),
        recommended_post_mode=_text(candidate.get("recommended_post_mode")),
        store_url=_text(candidate.get("store_url")),
    )


def _build_ingest_sources(truth: dict[str, Any]) -> list[SourceHealth]:
    ingest_sources = _as_dict(truth.get("ingest_sources"))
    if not ingest_sources:
        diagnostics = _as_dict(truth.get("diagnostics"))
        context = _as_dict(diagnostics.get("context"))
        ingest_sources = _as_dict(context.get("ingest_sources"))
    ordered_names = ["steam", "epic", "events_auto", "events_calendar", "events_deduped"]
    names = [name for name in ordered_names if name in ingest_sources]
    names.extend(sorted(name for name in ingest_sources if name not in ordered_names))
    result: list[SourceHealth] = []
    for name in names:
        payload = _as_dict(ingest_sources.get(name))
        if not payload:
            continue
        result.append(
            SourceHealth(
                name=name,
                status=_text(payload.get("status")) or "unknown",
                reason=_text(payload.get("reason")) or "unknown",
                offers=_int_or_none(payload.get("offers")),
                details=_as_dict(payload.get("details")),
            )
        )
    return result


def _derive_post_type(candidate: dict[str, Any], card_family: str, template_id: str) -> tuple[str, str]:
    content_family = _text(candidate.get("content_family")).lower()
    normalized_template = template_id.lower()
    if card_family == "TOP_LIST" and content_family == "roundup":
        return "roundup_toplist", "Roundup / Toplist"
    if card_family == "TOP_LIST":
        return "toplist", "Toplist"
    if content_family == "roundup" or normalized_template == "roundup_digest":
        return "roundup", "Roundup"
    if card_family == "FREE_GAME" or content_family == "freebie" or normalized_template in {"steam_free", "epic_free"}:
        return "freebie", "Freebie"
    if card_family == "DISCOUNT" and content_family == "discount":
        return "single_discount", "Single Discount"
    return "unknown", "Unknown/Unsupported"


def _derive_status_text(
    *,
    verdict_name: str,
    truth_ready: bool,
    telegram_verified: bool,
    command_status: str,
) -> str:
    if telegram_verified or verdict_name == "telegram_proof_verified":
        return "Telegram Proof Verified"
    if truth_ready or verdict_name == "truthful_send_test_ready":
        return "Preview Ready"
    if command_status == "failed":
        return "Preview Failed"
    if verdict_name == "truthful_send_test_blocked":
        return "Preview Blocked"
    if verdict_name:
        return verdict_name.replace("_", " ").title()
    return "No Preview Loaded"


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _path_or_none(value: Any) -> Path | None:
    text = _text(value)
    return Path(text) if text else None


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _dedupe(values: list[str]) -> list[str]:
    ordered: list[str] = []
    for value in values:
        text = _text(value)
        if text and text not in ordered:
            ordered.append(text)
    return ordered
