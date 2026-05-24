from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from dealbot.operator_ui.command_runner import PreviewCommandRunner
from dealbot.operator_ui.main_window import MainWindow
from dealbot.operator_ui.models import (
    ArtifactBundle,
    CandidateRow,
    LastPublishState,
    OPERATOR_POST_TYPE_MODES,
    PinnedPublishState,
    PreviewPaths,
    PreviewState,
    SelectedTarget,
    get_operator_post_type_mode,
)
from dealbot.operator_ui.safety import (
    SEND_DISABLED_SELECTION_MISMATCH_RU,
    build_operator_status,
    build_preview_action_copy,
    enforce_selected_candidate_send_gate,
    evaluate_preview_safety,
    evaluate_selected_preview_eligibility,
)


def test_evaluate_preview_safety_enables_send_for_verified_pinned_preview(tmp_path: Path) -> None:
    report_path = tmp_path / "output" / "analytics" / "truth.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("{}", encoding="utf-8")
    card_path = tmp_path / "output" / "cards" / "card.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"card")

    state = PreviewState(
        project_root=tmp_path,
        status_text="Preview Ready",
        truth_ready=True,
        post_type_key="single_discount",
        post_type_label="Single Discount",
        caption_html="<b>Caption</b>",
        caption_preview="Caption",
        caption_hash="caption-hash",
        card_path=card_path,
        card_exists=True,
        report_exists=True,
        pinned_publish=PinnedPublishState(
            contract_version=1,
            source="preview",
            offer_id="steam:227300",
            idempotency_key="preview-key",
            caption_hash="caption-hash",
            image_path=card_path,
            image_hash="image-hash",
            image_exists=True,
            caption_hash_verified=True,
            image_hash_verified=True,
        ),
        paths=PreviewPaths(
            truth_report_path=report_path,
            image_path=card_path,
            output_dir=tmp_path / "output",
        ),
    )

    safety = evaluate_preview_safety(state)

    assert safety.send_enabled is True
    assert safety.send_disabled_reason == "Превью готово к безопасной публикации."
    assert safety.blockers == []
    assert safety.preview_ready is True


def test_selected_candidate_send_gate_and_selected_preview_eligibility(tmp_path: Path) -> None:
    report_path = tmp_path / "output" / "analytics" / "truth.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("{}", encoding="utf-8")
    card_path = tmp_path / "output" / "cards" / "card.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"card")

    state = PreviewState(
        project_root=tmp_path,
        status_text="Preview Ready",
        truth_ready=True,
        post_type_key="single_discount",
        post_type_label="Single Discount",
        selected_target=SelectedTarget(title="Recommended", offer_id="steam:recommended"),
        preview_candidate_id="2",
        candidate_rows=[
            CandidateRow(candidate_id="2", row_id="2", title="Recommended", offer_id="steam:recommended", status="recommended"),
            CandidateRow(
                candidate_id="4",
                row_id="4",
                title="Blocked",
                offer_id="steam:blocked",
                status="blocked",
                blocker_reason="daily_lane_cap_reached",
            ),
        ],
        caption_html="<b>Caption</b>",
        caption_preview="Caption",
        card_path=card_path,
        card_exists=True,
        report_exists=True,
        pinned_publish=PinnedPublishState(
            contract_version=1,
            source="preview",
            offer_id="steam:recommended",
            idempotency_key="preview-key",
            caption_hash="caption-hash",
            image_path=card_path,
            image_hash="image-hash",
            image_exists=True,
            caption_hash_verified=True,
            image_hash_verified=True,
        ),
        paths=PreviewPaths(truth_report_path=report_path, image_path=card_path, output_dir=tmp_path / "output"),
    )

    base_safety = evaluate_preview_safety(state)
    assert base_safety.send_enabled is True

    no_selection = enforce_selected_candidate_send_gate(base_safety, state, "")
    mismatched_selection = enforce_selected_candidate_send_gate(base_safety, state, "4")
    matched_selection = enforce_selected_candidate_send_gate(base_safety, state, "2")
    ready_allowed, ready_reason = evaluate_selected_preview_eligibility(state, "2")
    blocked_allowed, blocked_reason = evaluate_selected_preview_eligibility(state, "4")

    assert no_selection.send_enabled is False
    assert no_selection.send_disabled_reason == SEND_DISABLED_SELECTION_MISMATCH_RU
    assert mismatched_selection.send_enabled is False
    assert mismatched_selection.send_disabled_reason == SEND_DISABLED_SELECTION_MISMATCH_RU
    assert matched_selection.send_enabled is True
    assert ready_allowed is True
    assert "preview-selected" in ready_reason
    assert blocked_allowed is False
    assert blocked_reason == "blocked: daily_lane_cap_reached"


def test_evaluate_preview_safety_disables_send_for_post_type_mismatch(tmp_path: Path) -> None:
    report_path = tmp_path / "output" / "analytics" / "truth.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("{}", encoding="utf-8")
    card_path = tmp_path / "output" / "cards" / "roundup.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"roundup")

    state = PreviewState(
        project_root=tmp_path,
        status_text="Preview Ready",
        truth_ready=True,
        post_type_key="roundup",
        post_type_label="Roundup",
        selected_target=SelectedTarget(title="Roundup: Weekly Picks", offer_id="roundup:weekly"),
        caption_html="<b>Roundup</b>",
        caption_preview="Roundup",
        card_path=card_path,
        card_exists=True,
        report_exists=True,
        pinned_publish=PinnedPublishState(
            contract_version=1,
            source="preview",
            offer_id="roundup:weekly",
            idempotency_key="roundup-key",
            caption_hash="caption-hash",
            image_path=card_path,
            image_hash="image-hash",
            image_exists=True,
            caption_hash_verified=True,
            image_hash_verified=True,
        ),
        paths=PreviewPaths(
            truth_report_path=report_path,
            image_path=card_path,
            output_dir=tmp_path / "output",
        ),
    )

    safety = evaluate_preview_safety(state)

    assert safety.send_enabled is False
    assert safety.send_disabled_reason == "Отключено: тип поста не выбран в текущем режиме."
    assert "Отключено: тип поста не выбран в текущем режиме." in safety.blockers


def test_evaluate_preview_safety_allows_supported_roundup_in_any_type_mode(tmp_path: Path) -> None:
    report_path = tmp_path / "output" / "analytics" / "truth.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("{}", encoding="utf-8")
    card_path = tmp_path / "output" / "cards" / "roundup.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"roundup")

    state = PreviewState(
        project_root=tmp_path,
        status_text="Preview Ready",
        truth_ready=True,
        post_type_key="roundup_toplist",
        post_type_label="Roundup / Toplist",
        selected_target=SelectedTarget(title="Roundup: Weekly Picks", offer_id="roundup:weekly"),
        caption_html="<b>Roundup</b>",
        caption_preview="Roundup",
        card_path=card_path,
        card_exists=True,
        report_exists=True,
        pinned_publish=PinnedPublishState(
            contract_version=1,
            source="preview",
            offer_id="roundup:weekly",
            idempotency_key="roundup-key",
            caption_hash="caption-hash",
            image_path=card_path,
            image_hash="image-hash",
            image_exists=True,
            caption_hash_verified=True,
            image_hash_verified=True,
        ),
        paths=PreviewPaths(
            truth_report_path=report_path,
            image_path=card_path,
            output_dir=tmp_path / "output",
        ),
    )

    safety = evaluate_preview_safety(state, get_operator_post_type_mode("any"))

    assert safety.send_enabled is True
    assert safety.send_disabled_reason == "Превью готово к безопасной публикации."
    assert safety.blockers == []


def test_evaluate_preview_safety_keeps_send_disabled_when_pinned_publish_missing(tmp_path: Path) -> None:
    report_path = tmp_path / "output" / "analytics" / "truth.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("{}", encoding="utf-8")
    card_path = tmp_path / "output" / "cards" / "card.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"card")

    state = PreviewState(
        project_root=tmp_path,
        status_text="Preview Ready",
        truth_ready=True,
        post_type_key="single_discount",
        post_type_label="Single Discount",
        caption_html="<b>Caption</b>",
        caption_preview="Caption",
        card_path=card_path,
        card_exists=True,
        report_exists=True,
        paths=PreviewPaths(
            truth_report_path=report_path,
            image_path=card_path,
            output_dir=tmp_path / "output",
        ),
    )

    safety = evaluate_preview_safety(state)

    assert safety.send_enabled is False
    assert safety.send_disabled_reason == "Отключено: в preview report нет pinned_publish."
    assert "В preview report нет pinned_publish." in safety.blockers


def test_evaluate_preview_safety_blocks_ambiguous_and_stale_preview(tmp_path: Path) -> None:
    report_path = tmp_path / "output" / "analytics" / "truth.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("{}", encoding="utf-8")
    card_path = tmp_path / "missing.png"

    state = PreviewState(
        project_root=tmp_path,
        status_text="Preview Blocked",
        post_type_key="unknown",
        post_type_label="Unknown/Unsupported",
        caption_html="",
        caption_preview="",
        card_path=card_path,
        card_exists=False,
        ambiguous=True,
        stale=True,
        blocker_reason="queue_empty",
        report_exists=True,
        pinned_publish=PinnedPublishState(contract_version=1),
        paths=PreviewPaths(
            truth_report_path=report_path,
            output_dir=tmp_path / "output",
        ),
    )

    safety = evaluate_preview_safety(state)

    assert safety.send_enabled is False
    assert "Артефакты превью неоднозначны." in safety.blockers
    assert "Артефакты превью устарели." in safety.blockers
    assert "Выбранный тип поста не определён или не поддерживается." in safety.blockers
    assert "Блокировка backend: Нет готового поста для публикации." in safety.blockers


def test_build_operator_status_ready_to_work_without_preview(tmp_path: Path) -> None:
    state = PreviewState.empty(tmp_path)
    safety = evaluate_preview_safety(state)

    operator_status = build_operator_status(state, safety)

    assert operator_status.status_text == "готов к работе"
    assert operator_status.next_action == "Соберите новое превью."


def test_build_preview_action_copy_defaults_to_preview(tmp_path: Path) -> None:
    label, tooltip = build_preview_action_copy(PreviewState.empty(tmp_path))

    assert label == "Собрать превью"
    assert tooltip == "Запускает preview и подбирает следующий кандидат для публикации."


def test_build_operator_status_marks_preview_ready_when_send_enabled(tmp_path: Path) -> None:
    report_path = tmp_path / "output" / "analytics" / "truth.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("{}", encoding="utf-8")
    card_path = tmp_path / "output" / "cards" / "card.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"card")
    state = PreviewState(
        project_root=tmp_path,
        status_text="Preview Ready",
        truth_ready=True,
        post_type_key="single_discount",
        post_type_label="Single Discount",
        selected_target=SelectedTarget(title="Subnautica", offer_id="steam:264710"),
        caption_html="<b>Caption</b>",
        caption_preview="Caption",
        card_path=card_path,
        card_exists=True,
        report_exists=True,
        pinned_publish=PinnedPublishState(
            contract_version=1,
            source="preview",
            offer_id="steam:264710",
            idempotency_key="preview-key",
            caption_hash="caption-hash",
            image_path=card_path,
            image_hash="image-hash",
            image_exists=True,
            caption_hash_verified=True,
            image_hash_verified=True,
        ),
        paths=PreviewPaths(truth_report_path=report_path, image_path=card_path, output_dir=tmp_path / "output"),
    )
    safety = evaluate_preview_safety(state)

    operator_status = build_operator_status(state, safety)

    assert operator_status.status_text == "превью готово к публикации"
    assert operator_status.next_action == "Проверьте карточку и описание, затем отправьте в Telegram."
    assert operator_status.current_preview_title == "Subnautica"
    assert operator_status.current_preview_offer_id == "steam:264710"


def test_build_operator_status_marks_preview_blocked_when_send_disabled(tmp_path: Path) -> None:
    report_path = tmp_path / "output" / "analytics" / "truth.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("{}", encoding="utf-8")
    state = PreviewState(
        project_root=tmp_path,
        status_text="Preview Blocked",
        truth_ready=False,
        post_type_key="single_discount",
        post_type_label="Single Discount",
        selected_target=SelectedTarget(title="Subnautica", offer_id="steam:264710"),
        report_exists=True,
        paths=PreviewPaths(truth_report_path=report_path, output_dir=tmp_path / "output"),
    )
    safety = evaluate_preview_safety(state)

    operator_status = build_operator_status(state, safety)

    assert operator_status.status_text == "превью не готово к публикации"
    assert operator_status.next_action == safety.send_disabled_reason


def test_build_operator_status_marks_preview_as_already_published(tmp_path: Path) -> None:
    report_path = tmp_path / "output" / "analytics" / "truth.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("{}", encoding="utf-8")
    state = PreviewState(
        project_root=tmp_path,
        status_text="Preview Ready",
        truth_ready=True,
        post_type_key="single_discount",
        post_type_label="Single Discount",
        selected_target=SelectedTarget(title="Subnautica", offer_id="steam:264710"),
        report_exists=True,
        last_publish=LastPublishState(
            workflow_path=tmp_path / "output" / "analytics" / "publish.json",
            title="Subnautica",
            offer_id="steam:264710",
            message_id=182,
            published=True,
            telegram_verified=True,
            source_report_path=report_path,
        ),
        paths=PreviewPaths(truth_report_path=report_path, output_dir=tmp_path / "output"),
    )
    safety = evaluate_preview_safety(state)

    operator_status = build_operator_status(state, safety)
    label, tooltip = build_preview_action_copy(state)

    assert operator_status.status_text == "Этот оффер уже опубликован."
    assert operator_status.next_action == "Соберите новое превью для следующего поста."
    assert operator_status.last_publish_message_id == 182
    assert label == "Собрать следующий пост"
    assert tooltip == "Запускает preview и подбирает следующий кандидат для публикации."


def test_evaluate_preview_safety_disables_send_for_already_published_preview_by_identity(tmp_path: Path) -> None:
    report_path = tmp_path / "output" / "analytics" / "truth.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("{}", encoding="utf-8")
    card_path = tmp_path / "output" / "cards" / "card.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"card")

    state = PreviewState(
        project_root=tmp_path,
        status_text="Preview Ready",
        truth_ready=True,
        post_type_key="single_discount",
        post_type_label="Single Discount",
        selected_target=SelectedTarget(title="Stardew Valley", offer_id="steam:413150"),
        caption_html="<b>Caption</b>",
        caption_preview="Caption",
        caption_hash="caption-hash",
        card_path=card_path,
        card_exists=True,
        report_exists=True,
        pinned_publish=PinnedPublishState(
            contract_version=1,
            source="preview",
            offer_id="steam:413150",
            idempotency_key="preview-key",
            caption_hash="caption-hash",
            image_path=card_path,
            image_hash="image-hash",
            image_exists=True,
            caption_hash_verified=True,
            image_hash_verified=True,
        ),
        last_publish=LastPublishState(
            workflow_path=tmp_path / "output" / "analytics" / "publish.json",
            title="Stardew Valley",
            offer_id="steam:413150",
            message_id=183,
            published=True,
            telegram_verified=True,
            idempotency_key="preview-key",
            caption_hash="caption-hash",
            image_hash="image-hash",
        ),
        paths=PreviewPaths(truth_report_path=report_path, image_path=card_path, output_dir=tmp_path / "output"),
    )

    safety = evaluate_preview_safety(state)

    assert safety.send_enabled is False
    assert safety.send_disabled_reason == "Этот оффер уже опубликован."
    assert "Этот оффер уже опубликован." in safety.blockers


def test_build_preview_action_copy_uses_next_post_after_successful_last_publish_without_preview(tmp_path: Path) -> None:
    state = PreviewState.empty(tmp_path)
    state.last_publish = LastPublishState(
        workflow_path=tmp_path / "output" / "analytics" / "publish.json",
        title="Subnautica",
        offer_id="steam:264710",
        message_id=182,
        published=True,
        telegram_verified=True,
    )
    safety = evaluate_preview_safety(state)

    operator_status = build_operator_status(state, safety)
    label, tooltip = build_preview_action_copy(state)

    assert operator_status.status_text == "готов к работе"
    assert operator_status.next_action == "Соберите новое превью для следующего поста."
    assert label == "Собрать следующий пост"
    assert tooltip == "Запускает preview и подбирает следующий кандидат для публикации."


def test_build_operator_status_marks_failed_last_publish(tmp_path: Path) -> None:
    state = PreviewState.empty(tmp_path)
    state.last_publish = LastPublishState(
        workflow_path=tmp_path / "output" / "analytics" / "publish.json",
        title="Subnautica",
        offer_id="steam:264710",
        published=False,
        telegram_verified=False,
        workflow_status="failed",
        reason="image_missing",
    )
    safety = evaluate_preview_safety(state)

    operator_status = build_operator_status(state, safety)

    assert operator_status.status_text == "последняя публикация не выполнена"
    assert operator_status.next_action == "Проверьте причину ошибки и соберите новое превью при необходимости."


def test_main_window_does_not_invoke_send_for_already_published_preview(tmp_path: Path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path)
    report_path = tmp_path / "output" / "analytics" / "truth.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("{}", encoding="utf-8")
    card_path = tmp_path / "output" / "cards" / "card.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"card")

    state = PreviewState(
        project_root=tmp_path,
        status_text="Preview Ready",
        truth_ready=True,
        post_type_key="single_discount",
        post_type_label="Single Discount",
        selected_target=SelectedTarget(title="Stardew Valley", offer_id="steam:413150"),
        caption_html="<b>Caption</b>",
        caption_preview="Caption",
        caption_hash="caption-hash",
        card_path=card_path,
        card_exists=True,
        report_exists=True,
        pinned_publish=PinnedPublishState(
            contract_version=1,
            source="preview",
            offer_id="steam:413150",
            idempotency_key="preview-key",
            caption_hash="caption-hash",
            image_path=card_path,
            image_hash="image-hash",
            image_exists=True,
            caption_hash_verified=True,
            image_hash_verified=True,
        ),
        last_publish=LastPublishState(
            workflow_path=tmp_path / "output" / "analytics" / "publish.json",
            title="Stardew Valley",
            offer_id="steam:413150",
            message_id=183,
            published=True,
            telegram_verified=True,
            idempotency_key="preview-key",
            caption_hash="caption-hash",
            image_hash="image-hash",
        ),
        paths=PreviewPaths(truth_report_path=report_path, image_path=card_path, output_dir=tmp_path / "output"),
    )
    window._apply_state(state)

    flags = {"disabled_dialog": 0}

    monkeypatch.setattr(window, "show_send_disabled_dialog", lambda: flags.__setitem__("disabled_dialog", flags["disabled_dialog"] + 1))
    monkeypatch.setattr(window, "_confirm_publish", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("confirmation must not open")))
    monkeypatch.setattr(
        window.runner,
        "run_publish_previewed",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("publish command must not run")),
    )

    window.handle_send_clicked()

    assert window.current_safety.send_enabled is False
    assert flags["disabled_dialog"] == 1
    assert window.send_button.isEnabled() is False
    assert window.send_button.property("buttonRole") == "disabled"
    assert window.send_button.cursor().shape() == Qt.CursorShape.ArrowCursor
    window.close()
    app.processEvents()


def test_main_window_refresh_local_state_disables_send_for_latest_already_published_preview(tmp_path: Path) -> None:
    analytics_dir = tmp_path / "output" / "analytics"
    cards_dir = tmp_path / "output" / "cards"
    analytics_dir.mkdir(parents=True, exist_ok=True)
    cards_dir.mkdir(parents=True, exist_ok=True)
    card_path = cards_dir / "card.png"
    card_path.write_bytes(b"card")
    truth_path = analytics_dir / "20260517T084940Z_operator_truth_report_preview.json"
    truth_path.write_text(
        """
        {
          "run_key": "20260517T084940Z",
          "created_at": "2026-05-17T08:49:40",
          "send_test_target": {
            "candidate": {
              "title": "Stardew Valley",
              "offer_id": "steam:413150",
              "source": "steam",
              "lane": "high_value_discount",
              "bucket": "planned",
              "content_family": "discount"
            },
            "artifact": {
              "offer_id": "steam:413150",
              "image_path": "%s",
              "caption_html": "<b>Caption</b>",
              "caption_preview": "Caption",
              "caption_hash": "caption-hash",
              "image_hash": "image-hash",
              "idempotency_key": "preview-key",
              "card_family": "DISCOUNT",
              "template_id": "steam_discount"
            }
          },
          "pinned_publish": {
            "contract_version": 1,
            "source": "preview",
            "report_run_key": "20260517T084940Z",
            "candidate": {
              "title": "Stardew Valley",
              "offer_id": "steam:413150"
            },
            "artifact": {
              "offer_id": "steam:413150",
              "image_path": "%s",
              "caption_html": "<b>Caption</b>",
              "caption_preview": "Caption",
              "caption_hash": "caption-hash",
              "image_hash": "image-hash",
              "idempotency_key": "preview-key",
              "card_family": "DISCOUNT",
              "template_id": "steam_discount"
            },
            "validation": {
              "image_exists": true,
              "caption_hash_verified": true,
              "image_hash_verified": true
            }
          },
          "verdict": {
            "verdict": "truthful_send_test_ready",
            "truth_ready": true,
            "telegram_verified": false
          }
        }
        """
        % (str(card_path).replace("\\", "\\\\"), str(card_path).replace("\\", "\\\\")),
        encoding="utf-8",
    )
    workflow_path = analytics_dir / "20260517T085019Z_operator_workflow_preview.json"
    workflow_path.write_text(
        '{"status": "ok", "command": "preview", "report_path": "%s"}'
        % str(truth_path).replace("\\", "\\\\"),
        encoding="utf-8",
    )
    publish_outcome_path = analytics_dir / "20260521T140649Z_publish_outcome_steam_413150.json"
    publish_outcome_path.write_text(
        '{"offer_id": "steam:413150", "title": "Stardew Valley", "message_id": 183, "publish_outcome": {"reason": "already_published", "outbox_status": "published", "idempotency_key": "preview-key", "caption_hash": "caption-hash", "image_hash": "image-hash"}}',
        encoding="utf-8",
    )
    publish_workflow_path = analytics_dir / "20260521T140650Z_operator_workflow_publish-previewed.json"
    publish_workflow_path.write_text(
        '{"command": "publish-previewed", "status": "ok", "published": true, "telegram_verified": true, "message_id": 183, "reason": "already_published", "outbox_status": "published", "source_report_path": "%s", "idempotency_key": "preview-key", "caption_hash": "caption-hash", "image_hash": "image-hash", "image_path": "%s", "publish_outcome_path": "%s", "selected": {"title": "Stardew Valley", "offer_id": "steam:413150"}}'
        % (
            str(truth_path).replace("\\", "\\\\"),
            str(card_path).replace("\\", "\\\\"),
            str(publish_outcome_path).replace("\\", "\\\\"),
        ),
        encoding="utf-8",
    )

    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path)

    assert window.current_state is not None
    assert window.current_safety.send_enabled is False
    assert window.send_button.isEnabled() is False
    assert window.send_button.property("buttonRole") == "disabled"
    assert window.send_button.cursor().shape() == Qt.CursorShape.ArrowCursor
    assert window.status_label.text() == "Этот оффер уже опубликован."
    assert window.send_reason_label.text() == "Этот оффер уже опубликован."
    assert window.current_preview_title_label.text() == "Активное превью не загружено."
    assert window.caption_preview_text.toPlainText() == "Превью описания не загружено."
    assert window.caption_html_browser.toPlainText() == "Описание не загружено."
    assert window.open_card_button.isEnabled() is False

    window.close()
    app.processEvents()


def test_main_window_clears_preview_when_current_run_creates_no_new_artifact(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path)
    report_path = tmp_path / "output" / "analytics" / "truth.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("{}", encoding="utf-8")
    card_path = tmp_path / "output" / "cards" / "card.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"card")

    bundle = ArtifactBundle(
        project_root=tmp_path,
        output_dir=tmp_path / "output",
        workflow_path=tmp_path / "output" / "analytics" / "workflow.json",
        truth_report_path=report_path,
        workflow_payload={
            "status": "ok",
            "command": "preview",
            "report_path": str(report_path),
        },
        truth_payload={
            "send_test_target": {
                "candidate": {
                    "title": "Stardew Valley",
                    "offer_id": "steam:413150",
                    "source": "steam",
                    "lane": "high_value_discount",
                    "bucket": "planned",
                    "content_family": "discount",
                },
                "artifact": {
                    "offer_id": "steam:413150",
                    "image_path": str(card_path),
                    "caption_html": "<b>Caption</b>",
                    "caption_preview": "Caption",
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
                "candidate": {
                    "title": "Stardew Valley",
                    "offer_id": "steam:413150",
                },
                "artifact": {
                    "offer_id": "steam:413150",
                    "image_path": str(card_path),
                    "caption_html": "<b>Caption</b>",
                    "caption_preview": "Caption",
                    "caption_hash": "caption-hash",
                    "image_hash": "image-hash",
                    "idempotency_key": "preview-key",
                    "card_family": "DISCOUNT",
                    "template_id": "steam_discount",
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
        publish_history_records=[
            {
                "workflow_path": tmp_path / "output" / "analytics" / "publish.json",
                "workflow_payload": {
                    "command": "publish-previewed",
                    "status": "ok",
                    "published": True,
                    "telegram_verified": True,
                    "message_id": 183,
                    "reason": "already_published",
                    "outbox_status": "published",
                    "source_report_path": str(report_path),
                    "idempotency_key": "preview-key",
                    "caption_hash": "caption-hash",
                    "image_hash": "image-hash",
                    "image_path": str(card_path),
                    "selected": {
                        "title": "Stardew Valley",
                        "offer_id": "steam:413150",
                    },
                },
                "publish_outcome_path": None,
                "publish_outcome_payload": {},
            }
        ],
        current_run_missing_artifact=True,
        stale=True,
        warnings=["No new preview workflow or truth artifact was created after the current run."],
    )

    window._preview_started_at = 1.0
    window.resolver.load_preview_run = lambda started_at: bundle
    window.runner._output_buffer = [
        "operator-verdict :: category=queue_state :: reason=already_published\n"
        "blocked-row :: row=42 :: [planned] [discount/high_value_discount] :: steam:413150 :: Stardew Valley :: blocker=already_published :: detail=blocked:already_published_recently\n"
    ]
    window._handle_preview_finished(0)

    assert window.current_state is not None
    assert window.current_state.current_run_missing_artifact is True
    assert window.current_state.current_run_backend_reason == "blocked:already_published_recently"
    assert window.send_button.isEnabled() is False
    assert window.send_button.property("buttonRole") == "disabled"
    assert window.send_button.cursor().shape() == Qt.CursorShape.ArrowCursor
    assert window.status_label.text() == "Новый preview не создан."
    assert window.send_reason_label.text() == "Новый preview не создан."
    assert window.current_preview_title_label.text() == "Активное превью не загружено."
    assert window.caption_preview_text.toPlainText() == "Превью описания не загружено."
    assert window.caption_html_browser.toPlainText() == "Описание не загружено."
    assert window.open_card_button.isEnabled() is False

    window.close()
    app.processEvents()


def test_main_window_keeps_send_button_visually_disabled_for_stale_preview(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path)
    report_path = tmp_path / "output" / "analytics" / "truth.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("{}", encoding="utf-8")
    card_path = tmp_path / "output" / "cards" / "card.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"card")

    state = PreviewState(
        project_root=tmp_path,
        status_text="Preview Ready",
        truth_ready=True,
        stale=True,
        post_type_key="single_discount",
        post_type_label="Single Discount",
        selected_target=SelectedTarget(title="Stale Preview", offer_id="steam:stale"),
        caption_html="<b>Caption</b>",
        caption_preview="Caption",
        card_path=card_path,
        card_exists=True,
        report_exists=True,
        pinned_publish=PinnedPublishState(
            contract_version=1,
            source="preview",
            offer_id="steam:stale",
            idempotency_key="stale-key",
            caption_hash="caption-hash",
            image_path=card_path,
            image_hash="image-hash",
            image_exists=True,
            caption_hash_verified=True,
            image_hash_verified=True,
        ),
        paths=PreviewPaths(truth_report_path=report_path, image_path=card_path, output_dir=tmp_path / "output"),
    )

    window._apply_state(state)

    assert window.current_safety.send_enabled is False
    assert window.send_button.isEnabled() is False
    assert window.send_button.property("buttonRole") == "disabled"
    assert window.send_button.cursor().shape() == Qt.CursorShape.ArrowCursor
    assert window.send_reason_label.text() == "Отключено: превью устарело."
    assert window.current_preview_title_label.text() == "Активное превью не загружено."
    assert window.caption_preview_text.toPlainText() == "Превью описания не загружено."
    assert window.caption_html_browser.toPlainText() == "Описание не загружено."
    assert window.open_card_button.isEnabled() is False

    window.close()
    app.processEvents()


def test_main_window_keeps_send_button_visually_disabled_for_unknown_blocked_preview(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path)
    report_path = tmp_path / "output" / "analytics" / "truth.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("{}", encoding="utf-8")

    state = PreviewState(
        project_root=tmp_path,
        status_text="Preview Blocked",
        truth_ready=False,
        post_type_key="unknown",
        post_type_label="Unknown/Unsupported",
        selected_target=SelectedTarget(title="Blocked Preview", offer_id="steam:blocked"),
        report_exists=True,
        paths=PreviewPaths(truth_report_path=report_path, output_dir=tmp_path / "output"),
    )

    window._apply_state(state)

    assert window.current_safety.send_enabled is False
    assert window.send_button.isEnabled() is False
    assert window.send_button.property("buttonRole") == "disabled"
    assert window.send_button.cursor().shape() == Qt.CursorShape.ArrowCursor

    window.close()
    app.processEvents()


def test_main_window_defaults_post_type_mode_to_single_discounts(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path)

    assert window.post_type_mode_combo.currentData() == OPERATOR_POST_TYPE_MODES[0].key
    assert window.post_type_mode_combo.currentText() == OPERATOR_POST_TYPE_MODES[0].label

    window.close()
    app.processEvents()


def test_main_window_disables_roundup_preview_in_single_discount_mode(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path)
    report_path = tmp_path / "output" / "analytics" / "truth.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("{}", encoding="utf-8")
    card_path = tmp_path / "output" / "cards" / "roundup.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"roundup")

    state = PreviewState(
        project_root=tmp_path,
        status_text="Preview Ready",
        truth_ready=True,
        post_type_key="roundup_toplist",
        post_type_label="Roundup / Toplist",
        selected_target=SelectedTarget(title="Roundup: Weekly Picks", offer_id="roundup:weekly"),
        caption_html="<b>Roundup</b>",
        caption_preview="Roundup",
        card_path=card_path,
        card_exists=True,
        report_exists=True,
        pinned_publish=PinnedPublishState(
            contract_version=1,
            source="preview",
            offer_id="roundup:weekly",
            idempotency_key="roundup-key",
            caption_hash="caption-hash",
            image_path=card_path,
            image_hash="image-hash",
            image_exists=True,
            caption_hash_verified=True,
            image_hash_verified=True,
        ),
        paths=PreviewPaths(truth_report_path=report_path, image_path=card_path, output_dir=tmp_path / "output"),
    )

    window._apply_state(state)

    assert window.current_safety.send_enabled is False
    assert window.send_button.isEnabled() is False
    assert window.send_reason_label.text() == "Отключено: тип поста не выбран в текущем режиме."
    assert window.status_label.text() == "Собрано превью типа Подборка, но выбран режим Одиночные скидки."
    assert "Подборки" in window.preview_selection_hint_label.text()
    assert "соберите подходящее превью" in window.preview_selection_hint_label.text().lower()
    assert window.current_preview_title_label.text() == "Roundup: Weekly Picks"
    assert window.open_card_button.isEnabled() is True

    window.close()
    app.processEvents()


def test_main_window_allows_supported_preview_in_any_type_mode(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path)
    report_path = tmp_path / "output" / "analytics" / "truth.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("{}", encoding="utf-8")
    card_path = tmp_path / "output" / "cards" / "roundup.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"roundup")

    state = PreviewState(
        project_root=tmp_path,
        status_text="Preview Ready",
        truth_ready=True,
        post_type_key="roundup",
        post_type_label="Roundup",
        selected_target=SelectedTarget(title="Roundup: Weekly Picks", offer_id="roundup:weekly"),
        caption_html="<b>Roundup</b>",
        caption_preview="Roundup",
        card_path=card_path,
        card_exists=True,
        report_exists=True,
        pinned_publish=PinnedPublishState(
            contract_version=1,
            source="preview",
            offer_id="roundup:weekly",
            idempotency_key="roundup-key",
            caption_hash="caption-hash",
            image_path=card_path,
            image_hash="image-hash",
            image_exists=True,
            caption_hash_verified=True,
            image_hash_verified=True,
        ),
        paths=PreviewPaths(truth_report_path=report_path, image_path=card_path, output_dir=tmp_path / "output"),
    )

    window.post_type_mode_combo.setCurrentIndex(window.post_type_mode_combo.findData("any"))
    window._apply_state(state)

    assert window.current_safety.send_enabled is True
    assert window.send_button.isEnabled() is True
    assert window.send_button.property("buttonRole") == "danger"
    assert window.status_label.text() == "Превью готово"

    window.close()
    app.processEvents()


def test_main_window_does_not_invoke_send_for_post_type_mismatch(tmp_path: Path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path)
    report_path = tmp_path / "output" / "analytics" / "truth.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("{}", encoding="utf-8")
    card_path = tmp_path / "output" / "cards" / "roundup.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"roundup")

    state = PreviewState(
        project_root=tmp_path,
        status_text="Preview Ready",
        truth_ready=True,
        post_type_key="roundup",
        post_type_label="Roundup",
        selected_target=SelectedTarget(title="Roundup: Weekly Picks", offer_id="roundup:weekly"),
        caption_html="<b>Roundup</b>",
        caption_preview="Roundup",
        card_path=card_path,
        card_exists=True,
        report_exists=True,
        pinned_publish=PinnedPublishState(
            contract_version=1,
            source="preview",
            offer_id="roundup:weekly",
            idempotency_key="roundup-key",
            caption_hash="caption-hash",
            image_path=card_path,
            image_hash="image-hash",
            image_exists=True,
            caption_hash_verified=True,
            image_hash_verified=True,
        ),
        paths=PreviewPaths(truth_report_path=report_path, image_path=card_path, output_dir=tmp_path / "output"),
    )
    window._apply_state(state)

    flags = {"disabled_dialog": 0}
    monkeypatch.setattr(window, "show_send_disabled_dialog", lambda: flags.__setitem__("disabled_dialog", flags["disabled_dialog"] + 1))
    monkeypatch.setattr(
        window.runner,
        "run_publish_previewed",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("publish command must not run")),
    )

    window.handle_send_clicked()

    assert window.current_safety.send_enabled is False
    assert flags["disabled_dialog"] == 1
    assert window.send_button.isEnabled() is False

    window.close()
    app.processEvents()


def test_main_window_uses_danger_style_only_for_valid_sendable_preview(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path)
    report_path = tmp_path / "output" / "analytics" / "truth.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("{}", encoding="utf-8")
    card_path = tmp_path / "output" / "cards" / "card.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"card")

    state = PreviewState(
        project_root=tmp_path,
        status_text="Preview Ready",
        truth_ready=True,
        post_type_key="single_discount",
        post_type_label="Single Discount",
        selected_target=SelectedTarget(title="Subnautica", offer_id="steam:264710"),
        caption_html="<b>Caption</b>",
        caption_preview="Caption",
        card_path=card_path,
        card_exists=True,
        report_exists=True,
        pinned_publish=PinnedPublishState(
            contract_version=1,
            source="preview",
            offer_id="steam:264710",
            idempotency_key="preview-key",
            caption_hash="caption-hash",
            image_path=card_path,
            image_hash="image-hash",
            image_exists=True,
            caption_hash_verified=True,
            image_hash_verified=True,
        ),
        paths=PreviewPaths(truth_report_path=report_path, image_path=card_path, output_dir=tmp_path / "output"),
    )

    window._apply_state(state)

    assert window.current_safety.send_enabled is True
    assert window.send_button.isEnabled() is True
    assert window.send_button.property("buttonRole") == "danger"
    assert window.send_button.cursor().shape() == Qt.CursorShape.PointingHandCursor

    window.close()
    app.processEvents()


def test_main_window_builds_readable_publish_confirmation_dialog(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path)
    report_path = tmp_path / "output" / "analytics" / "truth.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("{}", encoding="utf-8")
    card_path = tmp_path / "output" / "cards" / "card.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"card")

    state = PreviewState(
        project_root=tmp_path,
        status_text="Preview Ready",
        truth_ready=True,
        post_type_key="single_discount",
        post_type_label="Single Discount",
        selected_target=SelectedTarget(title="Subnautica", offer_id="steam:264710"),
        caption_html="<b>Caption</b>",
        caption_preview="Caption",
        card_path=card_path,
        card_exists=True,
        report_exists=True,
        pinned_publish=PinnedPublishState(
            contract_version=1,
            source="preview",
            offer_id="steam:264710",
            idempotency_key="preview-key",
            caption_hash="caption-hash",
            image_path=card_path,
            image_hash="image-hash",
            image_exists=True,
            caption_hash_verified=True,
            image_hash_verified=True,
        ),
        paths=PreviewPaths(truth_report_path=report_path, image_path=card_path, output_dir=tmp_path / "output"),
    )

    dialog = window._build_publish_confirmation_dialog(state, report_path)

    assert dialog.icon() == QMessageBox.Icon.Question
    assert dialog.windowTitle() == "Подтвердить публикацию"
    assert dialog.text() == "Будет опубликован именно закреплённый preview payload из текущего отчёта. Проверь карточку и описание перед отправкой."
    assert "offer_id: steam:264710" in dialog.informativeText()
    assert "idempotency_key: preview-key" in dialog.informativeText()
    assert "caption_hash: caption-hash" in dialog.informativeText()
    assert "image_hash: image-hash" in dialog.informativeText()
    assert "report_path:" in dialog.informativeText()
    assert "QMessageBox QLabel" in dialog.styleSheet()
    assert "color: #edf1ff;" in dialog.styleSheet()
    dialog.close()
    window.close()
    app.processEvents()


def test_main_window_candidate_selection_gates_send_until_preview_matches(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path)
    report_path = tmp_path / "output" / "analytics" / "truth.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("{}", encoding="utf-8")
    card_path = tmp_path / "output" / "cards" / "card.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"card")

    state = PreviewState(
        project_root=tmp_path,
        status_text="Preview Ready",
        truth_ready=True,
        post_type_key="single_discount",
        post_type_label="Single Discount",
        selected_target=SelectedTarget(title="Recommended", offer_id="steam:recommended"),
        preview_candidate_id="2",
        candidate_rows=[
            CandidateRow(candidate_id="2", row_id="2", title="Recommended", offer_id="steam:recommended", status="recommended"),
            CandidateRow(candidate_id="4", row_id="4", title="Reserve", offer_id="steam:reserve", status="reserve"),
        ],
        caption_html="<b>Caption</b>",
        caption_preview="Caption",
        card_path=card_path,
        card_exists=True,
        report_exists=True,
        pinned_publish=PinnedPublishState(
            contract_version=1,
            source="preview",
            offer_id="steam:recommended",
            idempotency_key="preview-key",
            caption_hash="caption-hash",
            image_path=card_path,
            image_hash="image-hash",
            image_exists=True,
            caption_hash_verified=True,
            image_hash_verified=True,
        ),
        paths=PreviewPaths(truth_report_path=report_path, image_path=card_path, output_dir=tmp_path / "output"),
    )

    window._apply_state(state)

    assert window.current_safety.send_enabled is False
    assert window.send_button.isEnabled() is False
    assert window.send_reason_label.text() == SEND_DISABLED_SELECTION_MISMATCH_RU
    assert window.candidate_table.rowCount() == 2

    window.candidate_table.selectRow(1)
    app.processEvents()
    assert window.selected_candidate_id == "4"
    assert window.current_safety.send_enabled is False
    assert window.send_reason_label.text() == SEND_DISABLED_SELECTION_MISMATCH_RU

    window.candidate_table.selectRow(0)
    app.processEvents()
    assert window.selected_candidate_id == "2"
    assert window.current_safety.send_enabled is True
    assert window.send_button.isEnabled() is True

    window.close()
    app.processEvents()


def test_main_window_marks_preview_command_running_immediately(tmp_path: Path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path)

    captured: dict[str, object] = {}
    monkeypatch.setattr(
        window.runner,
        "run_preview",
        lambda project_root, post_mode: captured.update(project_root=project_root, post_mode=post_mode) or True,
    )

    window.run_preview()

    assert captured == {
        "project_root": tmp_path.resolve(),
        "post_mode": "single_discount",
    }

    assert window.active_job_label.text().startswith("Выполняется: сбор превью")
    assert window.run_preview_button.isEnabled() is False
    assert window.refresh_button.isEnabled() is False
    assert window.post_type_mode_combo.isEnabled() is False
    assert window.candidate_table.isEnabled() is False

    window.close()
    app.processEvents()


def test_main_window_marks_mode_mismatch_preview_as_failed(tmp_path: Path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path)
    report_path = tmp_path / "output" / "analytics" / "truth.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("{}", encoding="utf-8")
    card_path = tmp_path / "output" / "cards" / "roundup.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"roundup")
    workflow_path = tmp_path / "output" / "analytics" / "workflow.json"
    workflow_path.write_text("{}", encoding="utf-8")

    bundle = ArtifactBundle(
        project_root=tmp_path,
        output_dir=tmp_path / "output",
        workflow_path=workflow_path,
        truth_report_path=report_path,
        workflow_payload={
            "status": "ok",
            "command": "preview",
            "report_path": str(report_path),
        },
        truth_payload={
            "selection": {
                "candidate_rows": [
                    {
                        "candidate_id": 8,
                        "row_id": 8,
                        "title": "Roundup: Big Discount Highlights",
                        "offer_id": "roundup:weekly",
                        "source": "steam",
                        "platform": "steam",
                        "post_type": "roundup",
                        "status": "recommended",
                        "bucket": "planned",
                        "lane": "roundup",
                    },
                    {
                        "candidate_id": 2,
                        "row_id": 2,
                        "title": "Single Discount Candidate",
                        "offer_id": "steam:single",
                        "source": "steam",
                        "platform": "steam",
                        "post_type": "discount",
                        "status": "ready",
                        "bucket": "planned",
                        "lane": "high_value_discount",
                    },
                ]
            },
            "send_test_target": {
                "candidate": {
                    "candidate_id": 8,
                    "row_id": 8,
                    "title": "Roundup: Big Discount Highlights",
                    "offer_id": "roundup:weekly",
                    "source": "steam",
                    "lane": "roundup",
                    "bucket": "planned",
                    "content_family": "roundup",
                    "post_type": "roundup",
                },
                "artifact": {
                    "offer_id": "roundup:weekly",
                    "image_path": str(card_path),
                    "caption_html": "<b>Roundup</b>",
                    "caption_preview": "Roundup preview",
                    "caption_hash": "caption-hash",
                    "image_hash": "image-hash",
                    "idempotency_key": "roundup-key",
                    "card_family": "TOP_LIST",
                    "template_id": "roundup_digest",
                },
            },
            "pinned_publish": {
                "contract_version": 1,
                "source": "preview",
                "candidate": {
                    "candidate_id": 8,
                    "row_id": 8,
                    "title": "Roundup: Big Discount Highlights",
                    "offer_id": "roundup:weekly",
                    "source": "steam",
                    "lane": "roundup",
                    "bucket": "planned",
                    "content_family": "roundup",
                    "post_type": "roundup",
                },
                "artifact": {
                    "offer_id": "roundup:weekly",
                    "image_path": str(card_path),
                    "caption_html": "<b>Roundup</b>",
                    "caption_preview": "Roundup preview",
                    "caption_hash": "caption-hash",
                    "image_hash": "image-hash",
                    "idempotency_key": "roundup-key",
                    "card_family": "TOP_LIST",
                    "template_id": "roundup_digest",
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

    captured_dialog: dict[str, object] = {}
    monkeypatch.setattr(window.resolver, "load_preview_run", lambda started_at: bundle)
    monkeypatch.setattr(window, "_active_job_elapsed_seconds", lambda: 34)
    monkeypatch.setattr(
        window,
        "_show_message_box",
        lambda icon, title, text: captured_dialog.update(icon=icon, title=title, text=text),
    )

    window._preview_started_at = 1.0
    window._start_active_job("preview")
    window._handle_preview_finished(0)

    log_text = window.log_text.toPlainText()

    assert window.active_job_label.text() == "Активных задач нет."
    assert "Сбор превью failed за 34 сек:" in log_text
    assert "Собрано превью типа Подборка, но выбран режим Одиночные скидки." in log_text
    assert window.status_label.text() == "Собрано превью типа Подборка, но выбран режим Одиночные скидки."
    assert "Собрать превью выбранного" in window.preview_selection_hint_label.text()
    assert window.send_button.isEnabled() is False
    assert captured_dialog["icon"] == QMessageBox.Icon.Warning
    assert "Одиночные скидки" in str(captured_dialog["text"])

    window.close()
    app.processEvents()


def test_main_window_marks_mode_filtered_no_candidate_preview_as_failed(tmp_path: Path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path)
    report_path = tmp_path / "output" / "analytics" / "truth.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("{}", encoding="utf-8")
    workflow_path = tmp_path / "output" / "analytics" / "workflow.json"
    workflow_path.write_text("{}", encoding="utf-8")

    bundle = ArtifactBundle(
        project_root=tmp_path,
        output_dir=tmp_path / "output",
        workflow_path=workflow_path,
        truth_report_path=report_path,
        workflow_payload={
            "status": "ok",
            "command": "preview",
            "report_path": str(report_path),
        },
        truth_payload={
            "selection": {
                "candidate_rows": [
                    {
                        "candidate_id": 8,
                        "row_id": 8,
                        "title": "Roundup: Freebies To Claim",
                        "offer_id": "roundup:weekly",
                        "source": "steam",
                        "platform": "steam",
                        "post_type": "roundup",
                        "status": "ready",
                        "bucket": "planned",
                        "lane": "roundup",
                    },
                ]
            },
            "verdict": {
                "verdict": "truthful_send_test_blocked",
                "truth_ready": False,
                "telegram_verified": False,
                "blocker_category": "queue_state",
                "blocker_reason": "no_candidates_for_post_mode",
                "blocker_detail": "Нет кандидатов для выбранного режима: Одиночные скидки",
            },
        },
    )

    captured_dialog: dict[str, object] = {}
    monkeypatch.setattr(window.resolver, "load_preview_run", lambda started_at: bundle)
    monkeypatch.setattr(window, "_active_job_elapsed_seconds", lambda: 12)
    monkeypatch.setattr(
        window,
        "_show_message_box",
        lambda icon, title, text: captured_dialog.update(icon=icon, title=title, text=text),
    )

    window._preview_started_at = 1.0
    window._start_active_job("preview")
    window._handle_preview_finished(0)

    log_text = window.log_text.toPlainText()

    assert "Сбор превью failed за 12 сек" in log_text
    assert "Нет кандидатов для выбранного режима: Одиночные скидки" in log_text
    assert window.status_label.text() == "Нет кандидатов для выбранного режима: Одиночные скидки"
    assert window.send_button.isEnabled() is False
    assert captured_dialog["icon"] == QMessageBox.Icon.Warning
    assert captured_dialog["text"] == "Нет кандидатов для выбранного режима: Одиночные скидки"

    window.close()
    app.processEvents()


def test_main_window_runs_preview_selected_for_selected_candidate(tmp_path: Path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path)
    report_path = tmp_path / "output" / "analytics" / "truth.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("{}", encoding="utf-8")
    card_path = tmp_path / "output" / "cards" / "card.png"
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_bytes(b"card")
    captured: dict[str, object] = {}

    state = PreviewState(
        project_root=tmp_path,
        status_text="Preview Ready",
        truth_ready=True,
        post_type_key="single_discount",
        post_type_label="Single Discount",
        selected_target=SelectedTarget(title="Recommended", offer_id="steam:recommended"),
        preview_candidate_id="2",
        candidate_rows=[
            CandidateRow(candidate_id="2", row_id="2", title="Recommended", offer_id="steam:recommended", status="recommended"),
        ],
        caption_html="<b>Caption</b>",
        caption_preview="Caption",
        card_path=card_path,
        card_exists=True,
        report_exists=True,
        pinned_publish=PinnedPublishState(
            contract_version=1,
            source="preview",
            offer_id="steam:recommended",
            idempotency_key="preview-key",
            caption_hash="caption-hash",
            image_path=card_path,
            image_hash="image-hash",
            image_exists=True,
            caption_hash_verified=True,
            image_hash_verified=True,
        ),
        paths=PreviewPaths(truth_report_path=report_path, image_path=card_path, output_dir=tmp_path / "output"),
    )

    monkeypatch.setattr(
        window.runner,
        "run_preview_selected",
        lambda project_root, selected_report_path, candidate_id: captured.update(
            project_root=project_root,
            report_path=selected_report_path,
            candidate_id=candidate_id,
        )
        or True,
    )

    window._apply_state(state)
    window.candidate_table.selectRow(0)
    app.processEvents()
    window.run_preview_selected()

    assert captured == {
        "project_root": tmp_path.resolve(),
        "report_path": report_path,
        "candidate_id": "2",
    }
    assert window.active_job_label.text().startswith("Выполняется: сбор превью выбранного")
    assert window.build_selected_preview_button.isEnabled() is False
    assert window.post_type_mode_combo.isEnabled() is False
    assert window.candidate_table.isEnabled() is False
    assert "building selected preview for 2" in window.log_text.toPlainText()

    window.close()
    app.processEvents()


def test_main_window_disables_preview_selected_for_blocked_candidate(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path)
    report_path = tmp_path / "output" / "analytics" / "truth.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("{}", encoding="utf-8")

    state = PreviewState(
        project_root=tmp_path,
        status_text="Preview Blocked",
        truth_ready=False,
        post_type_key="single_discount",
        post_type_label="Single Discount",
        preview_candidate_id="4",
        candidate_rows=[
            CandidateRow(
                candidate_id="4",
                row_id="4",
                title="Blocked",
                offer_id="steam:blocked",
                status="blocked",
                blocker_reason="daily_lane_cap_reached",
            ),
        ],
        report_exists=True,
        paths=PreviewPaths(truth_report_path=report_path, output_dir=tmp_path / "output"),
    )

    window._apply_state(state)
    window.candidate_table.selectRow(0)
    app.processEvents()

    assert window.build_selected_preview_button.isEnabled() is False
    assert window.build_selected_preview_reason_label.text() == "blocked: daily_lane_cap_reached"

    window.close()
    app.processEvents()


def test_main_window_disables_preview_selected_for_candidate_mode_mismatch(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path)
    report_path = tmp_path / "output" / "analytics" / "truth.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("{}", encoding="utf-8")

    state = PreviewState(
        project_root=tmp_path,
        status_text="Preview Ready",
        truth_ready=True,
        post_type_key="single_discount",
        post_type_label="Single Discount",
        preview_candidate_id="8",
        candidate_rows=[
            CandidateRow(
                candidate_id="8",
                row_id="8",
                title="Roundup Candidate",
                offer_id="roundup:weekly",
                post_type="roundup",
                status="ready",
            ),
        ],
        report_exists=True,
        paths=PreviewPaths(truth_report_path=report_path, output_dir=tmp_path / "output"),
    )

    window._apply_state(state)
    window.candidate_table.selectRow(0)
    app.processEvents()

    assert window.build_selected_preview_button.isEnabled() is False
    assert "не подходит для режима Одиночные скидки" in window.build_selected_preview_reason_label.text()

    window.close()
    app.processEvents()


def test_preview_command_runner_still_invokes_preview(monkeypatch, tmp_path: Path) -> None:
    runner = PreviewCommandRunner()
    captured: dict[str, object] = {}

    def fake_start_command(project_root: Path, command_name: str, arguments: list[str]) -> bool:
        captured["project_root"] = project_root
        captured["command_name"] = command_name
        captured["arguments"] = arguments
        return True

    monkeypatch.setattr(runner, "_start_command", fake_start_command)

    started = runner.run_preview(tmp_path)

    assert started is True
    assert captured == {
        "project_root": tmp_path,
        "command_name": "preview",
        "arguments": ["preview", "--post-mode", "any"],
    }


def test_preview_command_runner_invokes_preview_with_explicit_post_mode(monkeypatch, tmp_path: Path) -> None:
    runner = PreviewCommandRunner()
    captured: dict[str, object] = {}

    def fake_start_command(project_root: Path, command_name: str, arguments: list[str]) -> bool:
        captured["project_root"] = project_root
        captured["command_name"] = command_name
        captured["arguments"] = arguments
        return True

    monkeypatch.setattr(runner, "_start_command", fake_start_command)

    started = runner.run_preview(tmp_path, "roundup")

    assert started is True
    assert captured == {
        "project_root": tmp_path,
        "command_name": "preview",
        "arguments": ["preview", "--post-mode", "roundup"],
    }


def test_preview_command_runner_invokes_preview_selected(monkeypatch, tmp_path: Path) -> None:
    runner = PreviewCommandRunner()
    captured: dict[str, object] = {}
    report_path = tmp_path / "output" / "analytics" / "truth.json"

    def fake_start_command(project_root: Path, command_name: str, arguments: list[str]) -> bool:
        captured["project_root"] = project_root
        captured["command_name"] = command_name
        captured["arguments"] = arguments
        return True

    monkeypatch.setattr(runner, "_start_command", fake_start_command)

    started = runner.run_preview_selected(tmp_path, report_path, "42")

    assert started is True
    assert captured == {
        "project_root": tmp_path,
        "command_name": "preview-selected",
        "arguments": ["preview-selected", "--from-report", str(report_path), "--candidate-id", "42"],
    }
