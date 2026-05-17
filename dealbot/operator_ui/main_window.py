from __future__ import annotations

import html
import re
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .artifact_resolver import PreviewArtifactResolver
from .command_runner import PreviewCommandRunner
from .models import LastPublishState, PreviewState, SafetyState
from .report_parser import build_preview_state
from .safety import SEND_DISABLED_REASON_RU, evaluate_preview_safety, localize_ui_message


_STATUS_TEXT_TRANSLATIONS = {
    "No preview loaded.": "Нужно собрать превью",
    "No Preview Loaded": "Нужно собрать превью",
    "Preview Ready": "Превью готово",
    "Preview Required": "Нужно собрать превью",
    "Preview Failed": "Сбой сборки превью",
    "Preview Blocked": "Превью заблокировано",
    "Telegram Proof Verified": "Проверка Telegram подтверждена",
}

_POST_TYPE_TRANSLATIONS = {
    "Single Discount": "Одиночная скидка",
    "Freebie": "Раздача",
    "Roundup": "Подборка",
    "Roundup / Toplist": "Подборка",
    "Toplist": "Топ/подборка",
    "Unknown/Unsupported": "Неизвестный тип",
}

_PUBLISH_CONFIRMATION_WARNING = (
    "Будет опубликован именно закреплённый preview payload из текущего отчёта. "
    "Проверь карточку и описание перед отправкой."
)
_PUBLISH_IDENTITY_MISMATCH_TEXT = "ОШИБКА: опубликованный payload не совпадает с превью."
_PUBLISH_IDENTITY_MISMATCH_FULL_TEXT = (
    "ОШИБКА: опубликованный payload не совпадает с превью. Проверь workflow/report вручную."
)


def _translate_status_text(text: str) -> str:
    normalized = str(text or "").strip()
    return _STATUS_TEXT_TRANSLATIONS.get(normalized, normalized)


def _translate_post_type_label(text: str) -> str:
    normalized = str(text or "").strip()
    return _POST_TYPE_TRANSLATIONS.get(normalized, normalized)


def _yes_no(value: bool) -> str:
    return "да" if value else "нет"


def _yes_no_en(value: bool) -> str:
    return "yes" if value else "no"


def _or_none(value: object) -> str:
    text = str(value or "").strip()
    return text or "нет"


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_path(value: Any) -> str:
    raw = _text(value)
    if not raw:
        return ""
    try:
        return str(Path(raw).resolve())
    except OSError:
        return str(Path(raw))


def _verify_publish_previewed_identity(
    state: PreviewState | None,
    workflow_payload: dict[str, Any] | None,
) -> tuple[bool, str, str | None]:
    if state is None or state.fingerprint is None or workflow_payload is None:
        return False, "workflow_missing", None

    fingerprint = state.fingerprint
    selected = _as_dict(workflow_payload.get("selected"))
    expected_report_path = _normalized_path(fingerprint.report_path)
    actual_report_path = _normalized_path(workflow_payload.get("source_report_path"))
    expected_image_path = _normalized_path(fingerprint.image_path)
    actual_image_path = _normalized_path(workflow_payload.get("image_path"))
    checks = (
        (expected_report_path, actual_report_path),
        (_text(fingerprint.offer_id), _text(selected.get("offer_id"))),
        (_text(fingerprint.idempotency_key), _text(workflow_payload.get("idempotency_key"))),
        (_text(fingerprint.caption_hash), _text(workflow_payload.get("caption_hash"))),
        (_text(fingerprint.image_hash), _text(workflow_payload.get("image_hash"))),
        (expected_image_path, actual_image_path),
    )
    for expected, actual in checks:
        if expected and expected != actual:
            return False, "identity_mismatch", None

    if not bool(workflow_payload.get("published")):
        return False, _text(workflow_payload.get("reason")) or "publish_failed", None

    message_id = _text(workflow_payload.get("message_id"))
    if not message_id:
        return False, "missing_message_id", None
    return True, "", message_id


def _extract_publish_reason(output_text: str) -> str:
    text = str(output_text or "")
    if not text:
        return ""
    json_match = re.findall(r'"reason"\s*:\s*"([^"]+)"', text)
    if json_match:
        return json_match[-1]
    line_match = re.findall(r"\breason:\s*([a-z0-9_]+)", text, flags=re.IGNORECASE)
    if line_match:
        return line_match[-1]
    return ""


def _last_publish_status(last_publish: LastPublishState) -> str:
    return _text(last_publish.outbox_status or last_publish.reason or last_publish.workflow_status) or "none"


class ScaledImageLabel(QLabel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._original_pixmap: QPixmap | None = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(360)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setText("Карточка превью не загружена.")

    def set_preview_pixmap(self, pixmap: QPixmap | None) -> None:
        self._original_pixmap = pixmap
        self._refresh()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        if self._original_pixmap is None or self._original_pixmap.isNull():
            self.setPixmap(QPixmap())
            self.setText("Карточка превью не загружена.")
            return
        scaled = self._original_pixmap.scaled(
            max(320, self.width() - 24),
            max(240, self.height() - 24),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setText("")
        self.setPixmap(scaled)


class MainWindow(QMainWindow):
    def __init__(self, project_root: Path) -> None:
        super().__init__()
        self.project_root = Path(project_root).resolve()
        self.resolver = PreviewArtifactResolver(self.project_root)
        self.runner = PreviewCommandRunner(self)
        self.current_state: PreviewState | None = None
        self.current_safety: SafetyState = evaluate_preview_safety(None)
        self._preview_started_at: float | None = None
        self._publish_started_at: float | None = None

        self.setWindowTitle("Пульт YOTO: превью поста")
        self.resize(1560, 920)
        self._build_ui()
        self._connect_signals()
        self.refresh_local_state(initial=True)

    def _build_ui(self) -> None:
        root = QWidget(self)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        splitter = QSplitter(Qt.Orientation.Horizontal, root)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_center_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([320, 760, 480])

        layout.addWidget(splitter)
        self.setCentralWidget(root)

    def _build_left_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setSpacing(10)

        title = QLabel("Пульт YOTO")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(title)

        subtitle = QLabel(str(self.project_root))
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #4b5563;")
        layout.addWidget(subtitle)

        status_group = QGroupBox("Статус")
        status_layout = QVBoxLayout(status_group)
        self.status_label = QLabel("Нужно собрать превью")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.post_type_badge = QLabel("Неизвестный тип")
        self.post_type_badge.setWordWrap(True)
        self.post_type_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.post_type_badge.setStyleSheet(self._badge_style("unknown"))
        self.send_reason_label = QLabel(SEND_DISABLED_REASON_RU)
        self.send_reason_label.setWordWrap(True)
        self.send_reason_label.setStyleSheet("color: #7c2d12;")
        self.safety_label = QLabel("")
        self.safety_label.setWordWrap(True)
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.post_type_badge)
        status_layout.addWidget(self.send_reason_label)
        status_layout.addWidget(self.safety_label)
        layout.addWidget(status_group)

        actions_group = QGroupBox("Действия")
        actions_layout = QVBoxLayout(actions_group)
        self.run_preview_button = QPushButton("Собрать превью")
        self.refresh_button = QPushButton("Обновить состояние")
        self.open_report_button = QPushButton("Открыть отчёт")
        self.open_card_button = QPushButton("Открыть карточку")
        self.open_output_button = QPushButton("Открыть папку output")
        self.send_button = QPushButton("Отправить в Telegram")
        self.send_button.setEnabled(False)
        self.send_button.setToolTip(SEND_DISABLED_REASON_RU)
        actions_layout.addWidget(self.run_preview_button)
        actions_layout.addWidget(self.refresh_button)
        actions_layout.addWidget(self.open_report_button)
        actions_layout.addWidget(self.open_card_button)
        actions_layout.addWidget(self.open_output_button)
        actions_layout.addWidget(self.send_button)
        layout.addWidget(actions_group)

        publish_group = QGroupBox("Последняя публикация")
        publish_layout = QVBoxLayout(publish_group)
        self.last_publish_label = QLabel("Публикаций через UI пока нет.")
        self.last_publish_label.setWordWrap(True)
        self.last_publish_label.setStyleSheet("color: #374151;")
        self.open_publish_proof_button = QPushButton("Открыть proof")
        self.open_publish_outcome_button = QPushButton("Открыть publish outcome")
        self.open_analytics_button = QPushButton("Открыть папку analytics")
        publish_layout.addWidget(self.last_publish_label)
        publish_layout.addWidget(self.open_publish_proof_button)
        publish_layout.addWidget(self.open_publish_outcome_button)
        publish_layout.addWidget(self.open_analytics_button)
        layout.addWidget(publish_group)
        layout.addStretch(1)
        return panel

    def _build_center_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setSpacing(10)

        image_group = QGroupBox("Превью")
        image_layout = QVBoxLayout(image_group)
        self.image_label = ScaledImageLabel(image_group)
        image_layout.addWidget(self.image_label)
        layout.addWidget(image_group, stretch=3)

        caption_group = QGroupBox("Описание")
        caption_layout = QVBoxLayout(caption_group)
        self.caption_tabs = QTabWidget(caption_group)
        self.caption_html_browser = QTextBrowser()
        self.caption_html_browser.setOpenExternalLinks(True)
        self.caption_preview_text = QPlainTextEdit()
        self.caption_preview_text.setReadOnly(True)
        self.caption_tabs.addTab(self.caption_html_browser, "HTML описания")
        self.caption_tabs.addTab(self.caption_preview_text, "Превью описания")
        caption_layout.addWidget(self.caption_tabs)
        layout.addWidget(caption_group, stretch=2)
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Vertical, panel)

        details_group = QGroupBox("Детали")
        details_layout = QVBoxLayout(details_group)
        self.details_text = QPlainTextEdit()
        self.details_text.setReadOnly(True)
        details_layout.addWidget(self.details_text)

        log_group = QGroupBox("Лог процесса")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(2000)
        log_layout.addWidget(self.log_text)

        splitter.addWidget(details_group)
        splitter.addWidget(log_group)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([420, 260])

        layout.addWidget(splitter)
        return panel

    def _connect_signals(self) -> None:
        self.run_preview_button.clicked.connect(self.run_preview)
        self.refresh_button.clicked.connect(self.refresh_local_state)
        self.open_report_button.clicked.connect(self.open_report)
        self.open_card_button.clicked.connect(self.open_card)
        self.open_output_button.clicked.connect(self.open_output_folder)
        self.open_publish_proof_button.clicked.connect(self.open_publish_proof)
        self.open_publish_outcome_button.clicked.connect(self.open_publish_outcome)
        self.open_analytics_button.clicked.connect(self.open_analytics_folder)
        self.send_button.clicked.connect(self.handle_send_clicked)
        self.runner.output_ready.connect(self.append_log)
        self.runner.running_changed.connect(self._set_running)
        self.runner.finished.connect(self._handle_command_finished)

    def run_preview(self) -> None:
        if self.runner.is_running:
            return
        self._preview_started_at = time.time()
        self.log_text.clear()
        self.append_log(f"[ui] Запуск превью: {self.project_root / 'yoto.bat'}")
        started = self.runner.run_preview(self.project_root)
        if not started:
            self.append_log("[ui] Не удалось запустить yoto.bat для сборки превью")
            self.status_label.setText(_translate_status_text("Preview Failed"))

    def handle_send_clicked(self) -> None:
        if self.runner.is_running:
            return
        if not self.current_safety.send_enabled:
            self.show_send_disabled_dialog()
            return
        state = self.current_state
        report_path = self._bound_report_path_for_publish()
        if state is None or state.selected_target is None or report_path is None:
            self.show_send_disabled_dialog()
            return
        pinned = state.pinned_publish
        details = "\n".join(
            [
                f"Тип поста: {_translate_post_type_label(state.post_type_label)}",
                f"Title: {_or_none(state.selected_target.title)}",
                f"offer_id: {_or_none(state.selected_target.offer_id)}",
                f"idempotency_key: {_or_none(pinned.idempotency_key)}",
                f"caption_hash: {_or_none(pinned.caption_hash)}",
                f"image_hash: {_or_none(pinned.image_hash)}",
                f"report_path: {report_path}",
            ]
        )
        answer = QMessageBox.question(
            self,
            "Подтвердить публикацию",
            f"{_PUBLISH_CONFIRMATION_WARNING}\n\n{details}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._publish_started_at = time.time()
        self.append_log(f"[ui] Запуск publish-previewed: {report_path}")
        started = self.runner.run_publish_previewed(self.project_root, report_path)
        if not started:
            self.append_log("[ui] Не удалось запустить yoto.bat publish-previewed")
            QMessageBox.warning(self, "Публикация не выполнена", "Публикация не выполнена: process_start_failed")

    def refresh_local_state(self, initial: bool = False) -> None:
        if self.current_state and self.current_state.fingerprint:
            bundle = self.resolver.reload_bound_state(self.current_state.fingerprint)
        else:
            bundle = self.resolver.load_latest_local_state()
        state = (
            build_preview_state(bundle)
            if bundle.workflow_path or bundle.truth_report_path or bundle.latest_publish_workflow_path
            else PreviewState.empty(self.project_root)
        )
        self._apply_state(state)
        if not initial:
            self.append_log("[ui] Локальное состояние превью обновлено с диска")

    def _handle_command_finished(self, command_name: str, exit_code: int) -> None:
        if command_name == "publish-previewed":
            self._handle_publish_finished(exit_code)
            return
        self._handle_preview_finished(exit_code)

    def _handle_preview_finished(self, exit_code: int) -> None:
        started_at = self._preview_started_at or 0.0
        bundle = self.resolver.load_preview_run(started_at)
        if exit_code != 0 and bundle.workflow_path is None and bundle.truth_report_path is None:
            self.current_state = PreviewState.empty(self.project_root)
            self.current_safety = evaluate_preview_safety(self.current_state)
            self.status_label.setText(_translate_status_text("Preview Failed"))
            self.safety_label.setText("Последний запуск не создал артефакты превью.")
            self.append_log("[ui] Команда превью завершилась с ошибкой до записи артефактов workflow")
            self._sync_buttons()
            return
        state = build_preview_state(bundle)
        self._apply_state(state)

    def _handle_publish_finished(self, exit_code: int) -> None:
        state = self.current_state
        bound_report_path = self._bound_report_path_for_publish()
        started_at = self._publish_started_at or 0.0
        workflow_path, workflow_payload = self.resolver.load_publish_previewed_workflow(
            started_at=started_at,
            source_report_path=bound_report_path,
        )
        if workflow_path is not None:
            self.append_log(f"[ui] Найден workflow publish-previewed: {workflow_path}")
        success, reason, message_id = _verify_publish_previewed_identity(state, workflow_payload)
        if success and message_id is not None:
            QMessageBox.information(self, "Публикация завершена", f"Опубликовано в Telegram. message_id: {message_id}")
            self.refresh_local_state()
            return
        if reason == "identity_mismatch":
            QMessageBox.critical(self, "Ошибка публикации", _PUBLISH_IDENTITY_MISMATCH_FULL_TEXT)
            self.refresh_local_state()
            return
        if workflow_payload is not None and exit_code != 0:
            failure_reason = _text(workflow_payload.get("reason")) or reason or "publish_failed"
        else:
            failure_reason = reason or _extract_publish_reason(self.runner.last_output) or f"exit_code_{exit_code}"
        QMessageBox.warning(self, "Публикация не выполнена", f"Публикация не выполнена: {failure_reason}")
        self.refresh_local_state()

    def _apply_state(self, state: PreviewState) -> None:
        self.current_state = state
        self.current_safety = evaluate_preview_safety(state)
        self.status_label.setText(_translate_status_text(state.status_text))
        self.post_type_badge.setText(_translate_post_type_label(state.post_type_label))
        self.post_type_badge.setStyleSheet(self._badge_style(state.post_type_key))
        self.send_reason_label.setText(self.current_safety.send_disabled_reason)
        self.send_reason_label.setStyleSheet("color: #166534;" if self.current_safety.send_enabled else "color: #7c2d12;")
        self.send_button.setToolTip(self.current_safety.send_disabled_reason)
        self.safety_label.setText(self._format_safety_summary(self.current_safety))
        self._update_last_publish_panel(state.last_publish)
        self._update_preview_content(state)
        self.details_text.setPlainText(self._format_details(state, self.current_safety))
        self._sync_buttons()

    def _update_preview_content(self, state: PreviewState) -> None:
        if state.card_path and state.card_exists:
            self.image_label.set_preview_pixmap(QPixmap(str(state.card_path)))
        else:
            self.image_label.set_preview_pixmap(None)
        if state.caption_html:
            self.caption_html_browser.setHtml(state.caption_html)
        elif state.caption_preview:
            self.caption_html_browser.setPlainText(state.caption_preview)
        else:
            self.caption_html_browser.setPlainText("Описание не загружено.")
        self.caption_preview_text.setPlainText(state.caption_preview or "Превью описания не загружено.")

    def _sync_buttons(self) -> None:
        report_path = self._report_path()
        card_path = self.current_state.card_path if self.current_state else None
        last_publish = self.current_state.last_publish if self.current_state else LastPublishState()
        self.open_report_button.setEnabled(bool(report_path and report_path.exists()))
        self.open_card_button.setEnabled(bool(card_path and card_path.exists()))
        self.open_output_button.setEnabled(True)
        self.open_publish_proof_button.setEnabled(bool(last_publish.workflow_path and last_publish.workflow_path.exists()))
        self.open_publish_outcome_button.setEnabled(
            bool(last_publish.publish_outcome_path and last_publish.publish_outcome_path.exists())
        )
        self.open_analytics_button.setEnabled(True)
        self.send_button.setEnabled(bool(self.current_safety.send_enabled and not self.runner.is_running))

    def _set_running(self, running: bool) -> None:
        self.run_preview_button.setEnabled(not running)
        self.refresh_button.setEnabled(not running)
        self.open_report_button.setEnabled(not running and bool(self._report_path() and self._report_path().exists()))
        self.open_card_button.setEnabled(not running and bool(self.current_state and self.current_state.card_exists))
        self.open_output_button.setEnabled(not running)
        self.open_publish_proof_button.setEnabled(
            not running
            and bool(
                self.current_state
                and self.current_state.last_publish.workflow_path
                and self.current_state.last_publish.workflow_path.exists()
            )
        )
        self.open_publish_outcome_button.setEnabled(
            not running
            and bool(
                self.current_state
                and self.current_state.last_publish.publish_outcome_path
                and self.current_state.last_publish.publish_outcome_path.exists()
            )
        )
        self.open_analytics_button.setEnabled(not running)
        self.send_button.setEnabled(not running and self.current_safety.send_enabled)

    def open_report(self) -> None:
        report_path = self._report_path()
        if report_path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(report_path)))

    def open_card(self) -> None:
        if self.current_state and self.current_state.card_path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.current_state.card_path)))

    def open_output_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.project_root / "output")))

    def open_publish_proof(self) -> None:
        if self.current_state and self.current_state.last_publish.workflow_path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.current_state.last_publish.workflow_path)))

    def open_publish_outcome(self) -> None:
        if self.current_state and self.current_state.last_publish.publish_outcome_path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.current_state.last_publish.publish_outcome_path)))

    def open_analytics_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.project_root / "output" / "analytics")))

    def show_send_disabled_dialog(self) -> None:
        QMessageBox.information(self, "Отправка отключена", self.current_safety.send_disabled_reason)

    def append_log(self, text: str) -> None:
        stripped = text.rstrip()
        if not stripped:
            return
        self.log_text.appendPlainText(stripped)

    def _report_path(self) -> Path | None:
        if self.current_state is None:
            return None
        return self.current_state.paths.truth_report_path or self.current_state.paths.workflow_path

    def _bound_report_path_for_publish(self) -> Path | None:
        if self.current_state is None or self.current_state.fingerprint is None:
            return None
        report_path = self.current_state.fingerprint.report_path
        if report_path is None or not report_path.exists():
            return None
        return report_path

    def _update_last_publish_panel(self, last_publish: LastPublishState) -> None:
        self.last_publish_label.setText(self._format_last_publish_summary(last_publish))
        if not last_publish.present:
            self.last_publish_label.setStyleSheet("color: #374151;")
        elif last_publish.success:
            self.last_publish_label.setStyleSheet("color: #166534;")
        elif last_publish.workflow_status == "failed" or not last_publish.published:
            self.last_publish_label.setStyleSheet("color: #991b1b;")
        else:
            self.last_publish_label.setStyleSheet("color: #374151;")

    def _format_details(self, state: PreviewState, safety: SafetyState) -> str:
        lines: list[str] = []
        target = state.selected_target
        lines.append("Выбранный пост")
        if target is None:
            lines.append("  нет")
        else:
            lines.append(f"  title: {_or_none(target.title)}")
            lines.append(f"  post_type: {_translate_post_type_label(state.post_type_label)}")
            lines.append(f"  offer_id: {_or_none(target.offer_id)}")
            lines.append(f"  source: {_or_none(target.source)}")
            lines.append(f"  lane: {_or_none(target.lane)}")
            lines.append(f"  bucket: {_or_none(target.bucket)}")
            lines.append(f"  content_family: {_or_none(target.content_family)}")
        lines.append("")
        lines.append("Статус")
        lines.append(f"  status_text: {_translate_status_text(state.status_text)}")
        lines.append(f"  verdict: {_or_none(state.verdict)}")
        lines.append(f"  truth_ready: {_yes_no(state.truth_ready)}")
        lines.append(f"  telegram_verified: {_yes_no(state.telegram_verified)}")
        lines.append(f"  blocker_category: {_or_none(state.blocker_category)}")
        lines.append(f"  blocker_reason: {_or_none(state.blocker_reason)}")
        lines.append(f"  blocker_detail: {_or_none(state.blocker_detail)}")
        lines.append(f"  ambiguous: {_yes_no(state.ambiguous)}")
        lines.append(f"  stale: {_yes_no(state.stale)}")
        lines.append("")
        lines.append("Источники / здоровье данных")
        if not state.ingest_sources:
            lines.append("  нет")
        else:
            for source in state.ingest_sources:
                offers_text = str(source.offers) if source.offers is not None else "n/a"
                lines.append(f"  {source.name}: status={source.status} reason={source.reason} offers={offers_text}")
        lines.append("")
        lines.append("Пути")
        lines.append(f"  report_path: {_or_none(self._report_path())}")
        lines.append(f"  image_path: {_or_none(state.card_path)}")
        lines.append(f"  latest_snapshot_manifest: {_or_none(state.paths.latest_snapshot_manifest_path)}")
        lines.append(f"  latest_publish_outcome: {_or_none(state.paths.latest_publish_outcome_path)}")
        lines.append(f"  latest_publish_workflow: {_or_none(state.paths.latest_publish_workflow_path)}")
        lines.append("")
        lines.append("Закреплённый publish payload")
        lines.append(f"  contract_version: {_or_none(state.pinned_publish.contract_version)}")
        lines.append(f"  source: {_or_none(state.pinned_publish.source)}")
        lines.append(f"  report_run_key: {_or_none(state.pinned_publish.report_run_key)}")
        lines.append(f"  idempotency_key: {_or_none(state.pinned_publish.idempotency_key)}")
        lines.append(f"  caption_hash: {_or_none(state.pinned_publish.caption_hash)}")
        lines.append(f"  image_hash: {_or_none(state.pinned_publish.image_hash)}")
        lines.append(f"  image_path: {_or_none(state.pinned_publish.image_path)}")
        lines.append(f"  image_exists: {_yes_no(state.pinned_publish.image_exists)}")
        lines.append(f"  caption_hash_verified: {_yes_no(state.pinned_publish.caption_hash_verified)}")
        lines.append(f"  image_hash_verified: {_yes_no(state.pinned_publish.image_hash_verified)}")
        lines.append("")
        lines.append("Последняя публикация")
        if not state.last_publish.present:
            lines.append("  нет")
        else:
            lines.append(f"  title: {_or_none(state.last_publish.title)}")
            lines.append(f"  offer_id: {_or_none(state.last_publish.offer_id)}")
            lines.append(f"  message_id: {_or_none(state.last_publish.message_id)}")
            lines.append(f"  published: {_yes_no(state.last_publish.published)}")
            lines.append(f"  telegram_verified: {_yes_no(state.last_publish.telegram_verified)}")
            lines.append(f"  outbox_status: {_or_none(state.last_publish.outbox_status)}")
            lines.append(f"  reason: {_or_none(state.last_publish.reason)}")
            lines.append(f"  source_report_path: {_or_none(state.last_publish.source_report_path)}")
            lines.append(f"  publish_outcome_path: {_or_none(state.last_publish.publish_outcome_path)}")
            lines.append(f"  workflow_path: {_or_none(state.last_publish.workflow_path)}")
            lines.append(f"  workflow_modified_at: {_or_none(state.last_publish.workflow_modified_at)}")
            lines.append(f"  publish_outcome_modified_at: {_or_none(state.last_publish.publish_outcome_modified_at)}")
        lines.append("")
        lines.append("Безопасность")
        lines.append(f"  send_enabled: {_yes_no(safety.send_enabled)}")
        lines.append(f"  send_disabled_reason: {safety.send_disabled_reason}")
        if safety.blockers:
            lines.append("  blockers:")
            for blocker in safety.blockers:
                lines.append(f"    - {blocker}")
        if safety.warnings:
            lines.append("  warnings:")
            for warning in safety.warnings:
                lines.append(f"    - {warning}")
        return "\n".join(lines)

    @staticmethod
    def _format_safety_summary(safety: SafetyState) -> str:
        if safety.send_enabled:
            return "Превью готово к безопасной публикации."
        if safety.blockers:
            return " | ".join(safety.blockers)
        if safety.warnings:
            return " | ".join(localize_ui_message(item) for item in safety.warnings)
        return "Нужно собрать превью"

    @staticmethod
    def _format_last_publish_summary(last_publish: LastPublishState) -> str:
        if not last_publish.present:
            return "Публикаций через UI пока нет."
        lines: list[str] = []
        if last_publish.success:
            lines.append("Последняя публикация:")
        elif last_publish.workflow_status == "failed" or not last_publish.published:
            lines.append(f"Последняя публикация не выполнена: {_text(last_publish.reason) or 'unknown'}")
        else:
            lines.append("Последняя публикация:")
        lines.append(f"{_text(last_publish.title) or 'unknown'} / {_text(last_publish.offer_id) or 'none'}")
        lines.append(f"message_id: {_text(last_publish.message_id) or 'none'}")
        lines.append(f"published: {_yes_no_en(last_publish.published)}")
        lines.append(f"telegram_verified: {_yes_no_en(last_publish.telegram_verified)}")
        lines.append(f"status: {_last_publish_status(last_publish)}")
        lines.append(f"outbox_status: {_text(last_publish.outbox_status) or 'none'}")
        lines.append(f"reason: {_text(last_publish.reason) or 'none'}")
        lines.append(f"source_report: {_text(last_publish.source_report_path) or 'none'}")
        lines.append(f"publish_outcome: {_text(last_publish.publish_outcome_path) or 'none'}")
        lines.append(f"workflow: {_text(last_publish.workflow_path) or 'none'}")
        if last_publish.workflow_modified_at:
            lines.append(f"workflow_time: {last_publish.workflow_modified_at}")
        if last_publish.publish_outcome_modified_at:
            lines.append(f"publish_outcome_time: {last_publish.publish_outcome_modified_at}")
        return "\n".join(lines)

    @staticmethod
    def _badge_style(post_type_key: str) -> str:
        palette = {
            "single_discount": ("#065f46", "#d1fae5"),
            "freebie": ("#1d4ed8", "#dbeafe"),
            "roundup": ("#7c3aed", "#ede9fe"),
            "roundup_toplist": ("#7c3aed", "#ede9fe"),
            "toplist": ("#7c3aed", "#ede9fe"),
            "unknown": ("#374151", "#e5e7eb"),
        }
        foreground, background = palette.get(post_type_key, palette["unknown"])
        return (
            "padding: 8px 10px; "
            "border-radius: 8px; "
            f"color: {foreground}; "
            f"background-color: {background}; "
            "font-weight: 600;"
        )
