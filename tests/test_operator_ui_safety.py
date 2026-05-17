from __future__ import annotations

from pathlib import Path

from dealbot.operator_ui.models import LastPublishState, PinnedPublishState, PreviewPaths, PreviewState, SelectedTarget
from dealbot.operator_ui.safety import build_operator_status, evaluate_preview_safety


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
    assert "Блокировка backend: queue_empty" in safety.blockers


def test_build_operator_status_ready_to_work_without_preview(tmp_path: Path) -> None:
    state = PreviewState.empty(tmp_path)
    safety = evaluate_preview_safety(state)

    operator_status = build_operator_status(state, safety)

    assert operator_status.status_text == "готов к работе"
    assert operator_status.next_action == "Соберите новое превью."


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

    assert operator_status.status_text == "последний preview уже опубликован"
    assert operator_status.next_action == "Соберите новое превью для следующего поста."
    assert operator_status.last_publish_message_id == 182


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
