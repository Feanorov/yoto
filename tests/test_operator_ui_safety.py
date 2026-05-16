from __future__ import annotations

from pathlib import Path

from dealbot.operator_ui.models import PreviewPaths, PreviewState
from dealbot.operator_ui.safety import evaluate_preview_safety


def test_evaluate_preview_safety_keeps_send_disabled_with_exact_reason(tmp_path: Path) -> None:
    state = PreviewState(
        project_root=tmp_path,
        status_text="Preview Blocked",
        post_type_key="unknown",
        post_type_label="Unknown/Unsupported",
        caption_html="",
        caption_preview="",
        card_path=tmp_path / "missing.png",
        card_exists=False,
        ambiguous=True,
        stale=True,
        blocker_reason="queue_empty",
        paths=PreviewPaths(output_dir=tmp_path / "output"),
    )

    safety = evaluate_preview_safety(state)

    assert safety.send_enabled is False
    assert safety.send_disabled_reason == "Disabled: send-test is not preview-pinned yet; backend may replan before publish."
    assert "Preview artifacts are ambiguous." in safety.blockers
    assert "Preview artifacts are stale." in safety.blockers
    assert "Selected post type is Unknown/Unsupported." in safety.blockers
    assert "Backend blocker: queue_empty" in safety.blockers
