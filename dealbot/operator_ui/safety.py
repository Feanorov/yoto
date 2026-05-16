from __future__ import annotations

from .models import PreviewState, SafetyState, SEND_DISABLED_REASON


def evaluate_preview_safety(state: PreviewState | None) -> SafetyState:
    blockers: list[str] = []
    warnings: list[str] = []
    preview_ready = False

    if state is None:
        blockers.append("No preview state is loaded.")
    else:
        warnings.extend(state.warnings)
        if state.ambiguous:
            blockers.append("Preview artifacts are ambiguous.")
        if state.stale:
            blockers.append("Preview artifacts are stale.")
        if state.post_type_key == "unknown":
            blockers.append("Selected post type is Unknown/Unsupported.")
        if state.card_path is None:
            blockers.append("Preview card path is missing.")
        elif not state.card_exists:
            blockers.append("Preview card file is missing on disk.")
        if not state.caption_html and not state.caption_preview:
            blockers.append("Preview caption is missing.")
        if state.blocker_reason:
            blockers.append(f"Backend blocker: {state.blocker_reason}")
        preview_ready = bool(state.truth_ready and not blockers)

    return SafetyState(
        send_enabled=False,
        send_disabled_reason=SEND_DISABLED_REASON,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        preview_ready=preview_ready,
    )


def _dedupe(values: list[str]) -> list[str]:
    ordered: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in ordered:
            ordered.append(text)
    return ordered
