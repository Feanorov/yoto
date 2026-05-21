from __future__ import annotations

import html
import re
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
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
from .models import (
    LastPublishState,
    OperatorPostTypeMode,
    OPERATOR_POST_TYPE_MODES,
    PreviewState,
    SafetyState,
    default_operator_post_type_mode,
    get_operator_post_type_mode,
)
from .report_parser import build_preview_state
from .safety import (
    SEND_DISABLED_ALREADY_PUBLISHED_RU,
    SEND_DISABLED_NO_NEW_PREVIEW_RU,
    SEND_DISABLED_POST_TYPE_MODE_RU,
    SEND_DISABLED_REASON_RU,
    build_operator_status,
    build_preview_action_copy,
    evaluate_preview_safety,
    is_post_type_mode_mismatch,
    is_preview_already_published,
    localize_ui_message,
)


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


def _path_from_item_data(item: QListWidgetItem | None, offset: int) -> Path | None:
    if item is None:
        return None
    raw = _text(item.data(Qt.ItemDataRole.UserRole + offset))
    return Path(raw) if raw else None


class ScaledImageLabel(QLabel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._original_pixmap: QPixmap | None = None
        self.setObjectName("previewCanvas")
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
        self.current_safety: SafetyState = evaluate_preview_safety(None, default_operator_post_type_mode())
        self._preview_started_at: float | None = None
        self._publish_started_at: float | None = None

        self.setWindowTitle("Пульт YOTO: превью поста")
        self.resize(1560, 920)
        self._build_ui()
        self._apply_theme()
        self._connect_signals()
        self.refresh_local_state(initial=True)

    def _build_ui(self) -> None:
        root = QWidget(self)
        root.setObjectName("appRoot")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(14)

        splitter = QSplitter(Qt.Orientation.Horizontal, root)
        splitter.setObjectName("mainSplitter")
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
        panel.setObjectName("leftPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Пульт YOTO")
        title.setObjectName("appTitle")
        layout.addWidget(title)

        subtitle = QLabel(str(self.project_root))
        subtitle.setObjectName("appSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        self.operator_status_group = QGroupBox("Операторский статус")
        operator_status_layout = QVBoxLayout(self.operator_status_group)
        self.operator_status_summary_label = QLabel("Статус: готов к работе\nСледующее действие: соберите новое превью.")
        self.operator_status_summary_label.setObjectName("operatorStatusSummary")
        self.operator_status_summary_label.setWordWrap(True)
        self.operator_status_facts_label = QLabel("")
        self.operator_status_facts_label.setObjectName("operatorStatusFacts")
        self.operator_status_facts_label.setWordWrap(True)
        operator_status_layout.addWidget(self.operator_status_summary_label)
        operator_status_layout.addWidget(self.operator_status_facts_label)
        layout.addWidget(self.operator_status_group)

        status_group = QGroupBox("Статус")
        status_layout = QVBoxLayout(status_group)
        self.status_label = QLabel("Нужно собрать превью")
        self.status_label.setObjectName("statusHeadline")
        self.status_label.setWordWrap(True)
        self.post_type_mode_label = QLabel("Тип поста")
        self.post_type_mode_label.setObjectName("postTypeModeLabel")
        self.post_type_mode_combo = QComboBox(status_group)
        self.post_type_mode_combo.setObjectName("postTypeModeCombo")
        for mode in OPERATOR_POST_TYPE_MODES:
            self.post_type_mode_combo.addItem(mode.label, mode.key)
        self.post_type_mode_combo.setCurrentIndex(0)
        self.post_type_badge = QLabel("Неизвестный тип")
        self.post_type_badge.setObjectName("postTypeBadge")
        self.post_type_badge.setWordWrap(True)
        self.post_type_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.post_type_badge.setStyleSheet(self._badge_style("unknown"))
        self.send_reason_label = QLabel(SEND_DISABLED_REASON_RU)
        self.send_reason_label.setObjectName("sendReasonLabel")
        self.send_reason_label.setWordWrap(True)
        self.safety_label = QLabel("")
        self.safety_label.setObjectName("safetySummaryLabel")
        self.safety_label.setWordWrap(True)
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.post_type_mode_label)
        status_layout.addWidget(self.post_type_mode_combo)
        status_layout.addWidget(self.post_type_badge)
        status_layout.addWidget(self.send_reason_label)
        status_layout.addWidget(self.safety_label)
        layout.addWidget(status_group)

        actions_group = QGroupBox("Действия")
        actions_layout = QVBoxLayout(actions_group)
        self.run_preview_button = QPushButton("Собрать превью")
        self._set_button_role(self.run_preview_button, "primary")
        self.refresh_button = QPushButton("Обновить состояние")
        self._set_button_role(self.refresh_button, "secondary")
        self.open_report_button = QPushButton("Открыть отчёт")
        self._set_button_role(self.open_report_button, "utility")
        self.open_card_button = QPushButton("Открыть карточку")
        self._set_button_role(self.open_card_button, "utility")
        self.open_output_button = QPushButton("Открыть папку output")
        self._set_button_role(self.open_output_button, "utility")
        self.send_button = QPushButton("Отправить в Telegram")
        self._set_button_role(self.send_button, "danger")
        self.send_button.setToolTip(SEND_DISABLED_REASON_RU)
        self._apply_send_button_state(False)
        self._sync_preview_action_button()
        actions_layout.addWidget(self.run_preview_button)
        actions_layout.addWidget(self.refresh_button)
        actions_layout.addWidget(self.open_report_button)
        actions_layout.addWidget(self.open_card_button)
        actions_layout.addWidget(self.open_output_button)
        actions_layout.addWidget(self.send_button)
        layout.addWidget(actions_group)
        layout.addStretch(1)
        return panel

    def _build_center_panel(self) -> QWidget:
        panel = QWidget(self)
        panel.setObjectName("centerPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        preview_group = QGroupBox("Текущее превью")
        preview_layout = QVBoxLayout(preview_group)
        self.current_preview_title_label = QLabel("Активное превью не загружено.")
        self.current_preview_title_label.setObjectName("currentPreviewTitle")
        self.current_preview_title_label.setWordWrap(True)
        self.current_preview_meta_label = QLabel("Соберите превью, чтобы увидеть карточку, тип поста и offer_id.")
        self.current_preview_meta_label.setObjectName("currentPreviewMeta")
        self.current_preview_meta_label.setWordWrap(True)
        preview_layout.addWidget(self.current_preview_title_label)
        preview_layout.addWidget(self.current_preview_meta_label)
        layout.addWidget(preview_group)

        image_group = QGroupBox("Превью")
        image_layout = QVBoxLayout(image_group)
        self.image_label = ScaledImageLabel(image_group)
        image_layout.addWidget(self.image_label)
        layout.addWidget(image_group, stretch=3)

        caption_group = QGroupBox("Описание")
        caption_layout = QVBoxLayout(caption_group)
        self.caption_tabs = QTabWidget(caption_group)
        self.caption_tabs.setObjectName("captionTabs")
        self.caption_html_browser = QTextBrowser()
        self.caption_html_browser.setObjectName("captionHtmlBrowser")
        self.caption_html_browser.setOpenExternalLinks(True)
        self.caption_preview_text = QPlainTextEdit()
        self.caption_preview_text.setObjectName("captionPreviewText")
        self.caption_preview_text.setReadOnly(True)
        self.caption_tabs.addTab(self.caption_preview_text, "Превью описания")
        self.caption_tabs.addTab(self.caption_html_browser, "HTML описания")
        self.caption_tabs.setCurrentWidget(self.caption_preview_text)
        caption_layout.addWidget(self.caption_tabs)
        layout.addWidget(caption_group, stretch=2)
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget(self)
        panel.setObjectName("rightPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.side_tabs = QTabWidget(panel)
        self.side_tabs.setObjectName("sideTabs")

        publish_tab = QWidget(self.side_tabs)
        publish_layout = QVBoxLayout(publish_tab)
        publish_layout.setContentsMargins(0, 0, 0, 0)
        publish_layout.setSpacing(12)

        publish_group = QGroupBox("Последняя публикация")
        publish_group_layout = QVBoxLayout(publish_group)
        self.last_publish_label = QLabel("Публикаций через UI пока нет.")
        self.last_publish_label.setObjectName("lastPublishLabel")
        self.last_publish_label.setWordWrap(True)
        self.open_publish_proof_button = QPushButton("Открыть proof")
        self._set_button_role(self.open_publish_proof_button, "utility")
        self.open_publish_outcome_button = QPushButton("Открыть publish outcome")
        self._set_button_role(self.open_publish_outcome_button, "utility")
        self.open_analytics_button = QPushButton("Открыть папку analytics")
        self._set_button_role(self.open_analytics_button, "utility")
        publish_group_layout.addWidget(self.last_publish_label)
        publish_group_layout.addWidget(self.open_publish_proof_button)
        publish_group_layout.addWidget(self.open_publish_outcome_button)
        publish_group_layout.addWidget(self.open_analytics_button)
        publish_layout.addWidget(publish_group)

        history_group = QGroupBox("История публикаций")
        history_layout = QVBoxLayout(history_group)
        self.publish_history_list = QListWidget()
        self.publish_history_list.setObjectName("publishHistoryList")
        self.publish_history_list.setMinimumHeight(220)
        self.open_history_workflow_button = QPushButton("Открыть workflow")
        self._set_button_role(self.open_history_workflow_button, "utility")
        self.open_history_outcome_button = QPushButton("Открыть publish outcome")
        self._set_button_role(self.open_history_outcome_button, "utility")
        history_layout.addWidget(self.publish_history_list)
        history_layout.addWidget(self.open_history_workflow_button)
        history_layout.addWidget(self.open_history_outcome_button)
        publish_layout.addWidget(history_group, stretch=1)

        technical_tab = QWidget(self.side_tabs)
        technical_layout = QVBoxLayout(technical_tab)
        technical_layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Vertical, technical_tab)
        splitter.setObjectName("sideSplitter")

        details_group = QGroupBox("Технические детали")
        details_layout = QVBoxLayout(details_group)
        self.details_text = QPlainTextEdit()
        self.details_text.setObjectName("detailsText")
        self.details_text.setReadOnly(True)
        details_layout.addWidget(self.details_text)

        log_group = QGroupBox("Лог процесса")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QPlainTextEdit()
        self.log_text.setObjectName("logText")
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(2000)
        log_layout.addWidget(self.log_text)

        splitter.addWidget(details_group)
        splitter.addWidget(log_group)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([420, 260])

        technical_layout.addWidget(splitter)

        self.side_tabs.addTab(publish_tab, "Публикации")
        self.side_tabs.addTab(technical_tab, "Техническое")
        layout.addWidget(self.side_tabs)
        return panel

    @staticmethod
    def _set_button_role(button: QPushButton, role: str) -> None:
        if button.property("buttonRole") == role:
            return
        button.setProperty("buttonRole", role)
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget#appRoot {
                background-color: #070b16;
                color: #edf0ff;
            }
            QWidget#leftPanel {
                background-color: #0d1224;
                border: 1px solid #242d50;
                border-radius: 18px;
            }
            QWidget#centerPanel {
                background-color: #091022;
                border: 1px solid #27315d;
                border-radius: 18px;
            }
            QWidget#rightPanel {
                background-color: #0b1126;
                border: 1px solid #242d50;
                border-radius: 18px;
            }
            QSplitter#mainSplitter::handle, QSplitter#sideSplitter::handle {
                background-color: #151c38;
                border-radius: 4px;
            }
            QGroupBox {
                background-color: #141a33;
                border: 1px solid #2a3561;
                border-radius: 14px;
                margin-top: 12px;
                padding: 14px 14px 12px 14px;
                color: #e7ebff;
                font-weight: 600;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px 0 6px;
                color: #bfaeff;
            }
            QLabel {
                color: #e8ecff;
            }
            QLabel#appTitle {
                font-size: 24px;
                font-weight: 700;
                color: #f7f8ff;
            }
            QLabel#appSubtitle {
                color: #8893c8;
            }
            QLabel#statusHeadline {
                font-size: 18px;
                font-weight: 700;
                color: #ffffff;
            }
            QLabel#operatorStatusSummary {
                font-size: 15px;
                font-weight: 700;
                color: #f8f9ff;
            }
            QLabel#currentPreviewTitle {
                font-size: 18px;
                font-weight: 700;
                color: #ffffff;
            }
            QLabel#currentPreviewMeta {
                color: #b8c2f4;
            }
            QLabel#operatorStatusFacts, QLabel#safetySummaryLabel, QLabel#sendReasonLabel, QLabel#lastPublishLabel {
                color: #c8d1ff;
            }
            QLabel#postTypeBadge {
                border: 1px solid #404b83;
            }
            QPushButton {
                background-color: #182043;
                border: 1px solid #33407b;
                border-radius: 10px;
                padding: 10px 12px;
                color: #eef2ff;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #232e5e;
                border-color: #7b75ff;
            }
            QPushButton:pressed {
                background-color: #131b39;
            }
            QPushButton:disabled {
                background-color: #0f1430;
                border-color: #252d52;
                color: #67719d;
            }
            QPushButton[buttonRole="primary"] {
                background-color: #5a49f6;
                border-color: #9184ff;
                color: #ffffff;
            }
            QPushButton[buttonRole="primary"]:hover {
                background-color: #6a59ff;
                border-color: #b1a8ff;
            }
            QPushButton[buttonRole="danger"] {
                background-color: #8d2553;
                border-color: #ff7aa4;
                color: #fff8fb;
            }
            QPushButton[buttonRole="danger"]:disabled,
            QPushButton[buttonRole="disabled"],
            QPushButton[buttonRole="disabled"]:hover,
            QPushButton[buttonRole="disabled"]:pressed {
                background-color: #0f1430;
                border-color: #252d52;
                color: #67719d;
            }
            QPushButton[buttonRole="danger"]:hover {
                background-color: #a72d62;
                border-color: #ff9ab8;
            }
            QPushButton[buttonRole="secondary"] {
                background-color: #20305e;
                border-color: #5064b8;
            }
            QPushButton[buttonRole="utility"] {
                background-color: #151b37;
                border-color: #2d3768;
                color: #d6ddff;
            }
            QPlainTextEdit, QTextBrowser, QListWidget {
                background-color: #0b1025;
                border: 1px solid #2d3768;
                border-radius: 12px;
                color: #edf1ff;
                selection-background-color: #5c55ff;
                selection-color: #ffffff;
                padding: 8px;
            }
            QTextBrowser a {
                color: #8ea0ff;
            }
            QTabWidget::pane {
                border: 1px solid #2d3768;
                border-radius: 12px;
                top: -1px;
                background-color: #0b1025;
            }
            QTabBar::tab {
                background-color: #121938;
                color: #aeb9ee;
                padding: 9px 14px;
                margin-right: 4px;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }
            QTabBar::tab:selected {
                background-color: #1c2550;
                color: #ffffff;
            }
            QLabel#previewCanvas {
                background-color: #080d1d;
                border: 1px solid #324078;
                border-radius: 16px;
                color: #7e88b9;
                padding: 12px;
            }
            QListWidget#publishHistoryList::item {
                border: 1px solid #202850;
                border-radius: 10px;
                margin: 4px 2px;
                padding: 10px;
                background-color: #101734;
            }
            QListWidget#publishHistoryList::item:selected {
                background-color: #232d60;
                border-color: #7a74ff;
            }
            QScrollBar:vertical {
                background: #0d1228;
                width: 12px;
                margin: 2px;
            }
            QScrollBar::handle:vertical {
                background: #2d396e;
                min-height: 24px;
                border-radius: 6px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical,
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
                border: none;
            }
            """
        )

    def _connect_signals(self) -> None:
        self.run_preview_button.clicked.connect(self.run_preview)
        self.refresh_button.clicked.connect(self.refresh_local_state)
        self.open_report_button.clicked.connect(self.open_report)
        self.open_card_button.clicked.connect(self.open_card)
        self.open_output_button.clicked.connect(self.open_output_folder)
        self.open_publish_proof_button.clicked.connect(self.open_publish_proof)
        self.open_publish_outcome_button.clicked.connect(self.open_publish_outcome)
        self.open_analytics_button.clicked.connect(self.open_analytics_folder)
        self.open_history_workflow_button.clicked.connect(self.open_selected_history_workflow)
        self.open_history_outcome_button.clicked.connect(self.open_selected_history_outcome)
        self.publish_history_list.itemSelectionChanged.connect(self._sync_publish_history_buttons)
        self.publish_history_list.itemDoubleClicked.connect(self._open_history_workflow_item)
        self.send_button.clicked.connect(self.handle_send_clicked)
        self.post_type_mode_combo.currentIndexChanged.connect(self._handle_post_type_mode_changed)
        self.runner.output_ready.connect(self.append_log)
        self.runner.running_changed.connect(self._set_running)
        self.runner.finished.connect(self._handle_command_finished)

    def _current_post_type_mode(self) -> OperatorPostTypeMode:
        return get_operator_post_type_mode(self.post_type_mode_combo.currentData())

    def _handle_post_type_mode_changed(self, _index: int) -> None:
        if self.current_state is not None:
            self._apply_state(self.current_state)

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
        answer = self._confirm_publish(state, report_path)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._publish_started_at = time.time()
        self.append_log(f"[ui] Запуск publish-previewed: {report_path}")
        started = self.runner.run_publish_previewed(self.project_root, report_path)
        if not started:
            self.append_log("[ui] Не удалось запустить yoto.bat publish-previewed")
            self._show_message_box(
                QMessageBox.Icon.Warning,
                "Публикация не выполнена",
                "Публикация не выполнена: process_start_failed",
            )

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
        state = (
            build_preview_state(bundle)
            if bundle.workflow_path or bundle.truth_report_path or bundle.latest_publish_workflow_path
            else PreviewState.empty(self.project_root)
        )
        if bundle.current_run_missing_artifact:
            state.current_run_missing_artifact = True
            state.current_run_backend_reason = self._extract_preview_backend_reason(self.runner.last_output)
            if exit_code != 0:
                self.append_log("[ui] Команда превью завершилась без новых workflow/truth артефактов")
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
            self._show_message_box(
                QMessageBox.Icon.Information,
                "Публикация завершена",
                f"Опубликовано в Telegram. message_id: {message_id}",
            )
            self.refresh_local_state()
            return
        if reason == "identity_mismatch":
            self._show_message_box(
                QMessageBox.Icon.Critical,
                "Ошибка публикации",
                _PUBLISH_IDENTITY_MISMATCH_FULL_TEXT,
            )
            self.refresh_local_state()
            return
        if workflow_payload is not None and exit_code != 0:
            failure_reason = _text(workflow_payload.get("reason")) or reason or "publish_failed"
        else:
            failure_reason = reason or _extract_publish_reason(self.runner.last_output) or f"exit_code_{exit_code}"
        self._show_message_box(
            QMessageBox.Icon.Warning,
            "Публикация не выполнена",
            f"Публикация не выполнена: {failure_reason}",
        )
        self.refresh_local_state()

    def _apply_state(self, state: PreviewState) -> None:
        self.current_state = state
        self.current_safety = evaluate_preview_safety(state, self._current_post_type_mode())
        self.status_label.setText(self._build_status_headline(state, self.current_safety))
        self.post_type_badge.setText(_translate_post_type_label(state.post_type_label))
        self.post_type_badge.setStyleSheet(self._badge_style(state.post_type_key))
        self.send_reason_label.setText(self.current_safety.send_disabled_reason)
        self.send_reason_label.setStyleSheet("color: #166534;" if self.current_safety.send_enabled else "color: #7c2d12;")
        self.send_button.setToolTip(self.current_safety.send_disabled_reason)
        self.safety_label.setText(self._format_safety_summary(self.current_safety))
        self._update_operator_status_banner(state, self.current_safety)
        self._update_last_publish_panel(state.last_publish)
        self._update_publish_history_panel(state.publish_history)
        self._update_preview_content(state)
        self.details_text.setPlainText(self._format_details(state, self.current_safety))
        self._sync_buttons()

    def _has_active_preview(self, state: PreviewState) -> bool:
        return bool(
            state.truth_ready
            and not state.current_run_missing_artifact
            and not state.stale
            and not is_preview_already_published(state)
        )

    def _build_status_headline(self, state: PreviewState, safety: SafetyState) -> str:
        mode = self._current_post_type_mode()
        if state.current_run_missing_artifact:
            return SEND_DISABLED_NO_NEW_PREVIEW_RU
        if is_post_type_mode_mismatch(state, mode):
            return self._mode_mismatch_status_text(state, mode)
        if not self._has_active_preview(state):
            return self._inactive_preview_status_text(state, safety)
        return _translate_status_text(state.status_text)

    @staticmethod
    def _mode_mismatch_status_text(state: PreviewState, mode: OperatorPostTypeMode) -> str:
        if mode.key == "single_discount" and state.post_type_key in {"roundup", "roundup_toplist", "toplist"}:
            return "Доступна подборка, но текущий режим ожидает одиночную скидку."
        return SEND_DISABLED_POST_TYPE_MODE_RU

    @staticmethod
    def _inactive_preview_status_text(state: PreviewState, safety: SafetyState) -> str:
        if is_preview_already_published(state) or safety.send_disabled_reason == SEND_DISABLED_ALREADY_PUBLISHED_RU:
            return "Этот оффер уже опубликован."
        if state.blocker_reason and state.selected_target is None:
            return "Нет готового поста для публикации."
        if state.stale:
            return "Новый preview не создан."
        return _translate_status_text(state.status_text)

    @staticmethod
    def _extract_preview_backend_reason(output_text: str) -> str | None:
        text = str(output_text or "")
        detail_matches = re.findall(r"blocked-row :: .*?:: detail=([^\r\n]+)", text)
        for detail in reversed(detail_matches):
            normalized = str(detail).strip()
            if normalized and normalized != "none":
                return normalized
        reason_matches = re.findall(r"operator-verdict :: .*?:: reason=([^\s]+)", text)
        for reason in reversed(reason_matches):
            normalized = str(reason).strip()
            if normalized and normalized != "none":
                return normalized
        blocker_matches = re.findall(r"target :: .*?:: blocker_reason=([^\s]+)", text)
        for reason in reversed(blocker_matches):
            normalized = str(reason).strip()
            if normalized and normalized != "none":
                return normalized
        return None

    def _update_preview_content(self, state: PreviewState) -> None:
        self._update_current_preview_summary(state)
        if self._has_active_preview(state) and state.card_path and state.card_exists:
            self.image_label.set_preview_pixmap(QPixmap(str(state.card_path)))
        else:
            self.image_label.set_preview_pixmap(None)
        if not self._has_active_preview(state):
            self.caption_html_browser.setPlainText("Описание не загружено.")
            self.caption_preview_text.setPlainText("Превью описания не загружено.")
            return
        if state.caption_html:
            self.caption_html_browser.setHtml(state.caption_html)
        elif state.caption_preview:
            self.caption_html_browser.setPlainText(state.caption_preview)
        else:
            self.caption_html_browser.setPlainText("Описание не загружено.")
        self.caption_preview_text.setPlainText(state.caption_preview or "Превью описания не загружено.")

    def _update_current_preview_summary(self, state: PreviewState) -> None:
        target = state.selected_target
        if self._has_active_preview(state) and target is not None and (_text(target.title) or _text(target.offer_id)):
            self.current_preview_title_label.setText(_text(target.title) or "Без названия")
            meta_parts = [
                f"Тип: {_translate_post_type_label(state.post_type_label)}",
                f"offer_id: {_text(target.offer_id) or 'нет'}",
            ]
            if _text(target.source):
                meta_parts.append(f"Источник: {_text(target.source)}")
            self.current_preview_meta_label.setText(" · ".join(meta_parts))
            return

        self.current_preview_title_label.setText("Активное превью не загружено.")
        meta_parts = [f"Статус: {self._build_status_headline(state, self.current_safety)}"]
        translated_post_type = _translate_post_type_label(state.post_type_label)
        if translated_post_type:
            meta_parts.append(f"Тип: {translated_post_type}")
        meta_parts.append(f"Режим: {self._current_post_type_mode().label}")
        self.current_preview_meta_label.setText(" · ".join(meta_parts))

    def _sync_buttons(self) -> None:
        self._sync_preview_action_button()
        report_path = self._report_path()
        card_path = (
            self.current_state.card_path
            if self.current_state is not None and self._has_active_preview(self.current_state)
            else None
        )
        last_publish = self.current_state.last_publish if self.current_state else LastPublishState()
        self.open_report_button.setEnabled(bool(report_path and report_path.exists()))
        self.open_card_button.setEnabled(bool(card_path and card_path.exists()))
        self.open_output_button.setEnabled(True)
        self.open_publish_proof_button.setEnabled(bool(last_publish.workflow_path and last_publish.workflow_path.exists()))
        self.open_publish_outcome_button.setEnabled(
            bool(last_publish.publish_outcome_path and last_publish.publish_outcome_path.exists())
        )
        self.open_analytics_button.setEnabled(True)
        self._sync_publish_history_buttons()
        self._apply_send_button_state(bool(self.current_safety.send_enabled and not self.runner.is_running))

    def _sync_preview_action_button(self) -> None:
        label, tooltip = build_preview_action_copy(self.current_state)
        self.run_preview_button.setText(label)
        self.run_preview_button.setToolTip(tooltip)

    def _set_running(self, running: bool) -> None:
        self.run_preview_button.setEnabled(not running)
        self.refresh_button.setEnabled(not running)
        self.open_report_button.setEnabled(not running and bool(self._report_path() and self._report_path().exists()))
        self.open_card_button.setEnabled(
            not running and bool(self.current_state and self._has_active_preview(self.current_state) and self.current_state.card_exists)
        )
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
        self._sync_publish_history_buttons()
        self._apply_send_button_state(not running and self.current_safety.send_enabled)

    def _apply_send_button_state(self, enabled: bool) -> None:
        self.send_button.setEnabled(enabled)
        self._set_button_role(self.send_button, "danger" if enabled else "disabled")
        self.send_button.setCursor(
            Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ArrowCursor
        )

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

    def open_selected_history_workflow(self) -> None:
        item = self.publish_history_list.currentItem()
        if item is not None:
            self._open_history_workflow_item(item)

    def open_selected_history_outcome(self) -> None:
        item = self.publish_history_list.currentItem()
        if item is None:
            return
        publish_outcome_path = _path_from_item_data(item, 1)
        if publish_outcome_path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(publish_outcome_path)))

    def show_send_disabled_dialog(self) -> None:
        self._show_message_box(
            QMessageBox.Icon.Information,
            "Отправка отключена",
            self.current_safety.send_disabled_reason,
        )

    def append_log(self, text: str) -> None:
        stripped = text.rstrip()
        if not stripped:
            return
        self.log_text.appendPlainText(stripped)

    def _confirm_publish(self, state: PreviewState, report_path: Path) -> QMessageBox.StandardButton:
        dialog = self._build_publish_confirmation_dialog(state, report_path)
        return QMessageBox.StandardButton(dialog.exec())

    def _build_publish_confirmation_dialog(self, state: PreviewState, report_path: Path) -> QMessageBox:
        pinned = state.pinned_publish
        details = "\n".join(
            [
                f"Тип поста: {_translate_post_type_label(state.post_type_label)}",
                f"Title: {_or_none(state.selected_target.title if state.selected_target is not None else '')}",
                f"offer_id: {_or_none(state.selected_target.offer_id if state.selected_target is not None else '')}",
                f"idempotency_key: {_or_none(pinned.idempotency_key)}",
                f"caption_hash: {_or_none(pinned.caption_hash)}",
                f"image_hash: {_or_none(pinned.image_hash)}",
                f"report_path: {report_path}",
            ]
        )
        return self._build_message_box(
            QMessageBox.Icon.Question,
            "Подтвердить публикацию",
            _PUBLISH_CONFIRMATION_WARNING,
            informative_text=details,
            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            default_button=QMessageBox.StandardButton.No,
        )

    def _show_message_box(
        self,
        icon: QMessageBox.Icon,
        title: str,
        text: str,
        *,
        informative_text: str = "",
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
        default_button: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
    ) -> QMessageBox.StandardButton:
        dialog = self._build_message_box(
            icon,
            title,
            text,
            informative_text=informative_text,
            buttons=buttons,
            default_button=default_button,
        )
        return QMessageBox.StandardButton(dialog.exec())

    def _build_message_box(
        self,
        icon: QMessageBox.Icon,
        title: str,
        text: str,
        *,
        informative_text: str = "",
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
        default_button: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
    ) -> QMessageBox:
        dialog = QMessageBox(self)
        dialog.setIcon(icon)
        dialog.setWindowTitle(title)
        dialog.setText(text)
        dialog.setInformativeText(informative_text)
        dialog.setStandardButtons(buttons)
        dialog.setDefaultButton(default_button)
        dialog.setStyleSheet(self._dialog_style())
        return dialog

    @staticmethod
    def _dialog_style() -> str:
        return (
            "QMessageBox {"
            " background-color: #0b1126;"
            "}"
            "QMessageBox QLabel {"
            " color: #edf1ff;"
            " min-width: 520px;"
            "}"
            "QMessageBox QPushButton {"
            " background-color: #182043;"
            " border: 1px solid #33407b;"
            " border-radius: 10px;"
            " padding: 8px 12px;"
            " color: #eef2ff;"
            " font-weight: 600;"
            " min-width: 96px;"
            "}"
            "QMessageBox QPushButton:hover {"
            " background-color: #232e5e;"
            " border-color: #7b75ff;"
            "}"
            "QMessageBox QPushButton:pressed {"
            " background-color: #131b39;"
            "}"
        )

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
            self.last_publish_label.setStyleSheet("color: #c5cdee;")
        elif last_publish.success:
            self.last_publish_label.setStyleSheet("color: #7ef2a8;")
        elif last_publish.workflow_status == "failed" or not last_publish.published:
            self.last_publish_label.setStyleSheet("color: #ff9aa8;")
        else:
            self.last_publish_label.setStyleSheet("color: #d6ddff;")

    def _update_publish_history_panel(self, publish_history: list[LastPublishState]) -> None:
        self.publish_history_list.clear()
        if not publish_history:
            placeholder = QListWidgetItem("Публикаций через UI пока нет.")
            placeholder.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.publish_history_list.addItem(placeholder)
            self._sync_publish_history_buttons()
            return
        for entry in publish_history:
            item = QListWidgetItem(self._format_publish_history_entry(entry))
            item.setData(Qt.ItemDataRole.UserRole, str(entry.workflow_path) if entry.workflow_path is not None else "")
            item.setData(
                Qt.ItemDataRole.UserRole + 1,
                str(entry.publish_outcome_path) if entry.publish_outcome_path is not None else "",
            )
            if entry.success:
                item.setForeground(QColor("#dbffe7"))
                item.setBackground(QColor("#132b24"))
            elif entry.workflow_status == "failed" or not entry.published:
                item.setForeground(QColor("#ffe1e7"))
                item.setBackground(QColor("#32141e"))
            self.publish_history_list.addItem(item)
        self.publish_history_list.setCurrentRow(0)
        self._sync_publish_history_buttons()

    def _sync_publish_history_buttons(self) -> None:
        running = self.runner.is_running
        item = self.publish_history_list.currentItem()
        workflow_path = _path_from_item_data(item, 0) if item is not None else None
        publish_outcome_path = _path_from_item_data(item, 1) if item is not None else None
        self.open_history_workflow_button.setEnabled(not running and workflow_path is not None and workflow_path.exists())
        self.open_history_outcome_button.setEnabled(
            not running and publish_outcome_path is not None and publish_outcome_path.exists()
        )

    def _open_history_workflow_item(self, item: QListWidgetItem) -> None:
        workflow_path = _path_from_item_data(item, 0)
        if workflow_path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(workflow_path)))

    def _update_operator_status_banner(self, state: PreviewState, safety: SafetyState) -> None:
        operator_status = build_operator_status(state, safety)
        self.operator_status_summary_label.setText(
            f"Статус: {operator_status.status_text}\n"
            f"Следующее действие: {operator_status.next_action}"
        )
        fact_lines: list[str] = []
        if operator_status.last_publish_title or operator_status.last_publish_offer_id:
            fact_lines.append(
                f"Последняя публикация: {_text(operator_status.last_publish_title) or 'unknown'} / "
                f"{_text(operator_status.last_publish_offer_id) or 'none'}"
            )
        if operator_status.last_publish_message_id is not None:
            fact_lines.append(f"message_id: {operator_status.last_publish_message_id}")
        if operator_status.last_publish_telegram_verified is not None:
            fact_lines.append(f"telegram_verified: {_yes_no_en(operator_status.last_publish_telegram_verified)}")
        if operator_status.current_preview_title or operator_status.current_preview_offer_id:
            fact_lines.append(
                f"Текущий preview: {_text(operator_status.current_preview_title) or 'unknown'} / "
                f"{_text(operator_status.current_preview_offer_id) or 'none'}"
            )
        if operator_status.current_post_type_label:
            fact_lines.append(f"Тип: {_translate_post_type_label(operator_status.current_post_type_label)}")
        self.operator_status_facts_label.setText("\n".join(fact_lines))
        palette = {
            "ready": ("#dbe3ff", "#111833", "#324071"),
            "preview_ready": ("#eafff3", "#112c21", "#31c36b"),
            "preview_blocked": ("#fff4d8", "#352510", "#e3a33c"),
            "published": ("#edf3ff", "#122044", "#5f8dff"),
            "failed": ("#ffe8ed", "#351420", "#ff5f82"),
        }
        foreground, background, border = palette.get(operator_status.kind, palette["ready"])
        self.operator_status_group.setStyleSheet(
            "QGroupBox {"
            f" color: {foreground};"
            " font-weight: 600;"
            f" border: 1px solid {border};"
            " border-radius: 8px;"
            f" background-color: {background};"
            " margin-top: 8px;"
            " padding-top: 10px;"
            "}"
            "QGroupBox::title {"
            " subcontrol-origin: margin;"
            " left: 10px;"
            " padding: 0 4px 0 4px;"
            f" color: {foreground};"
            "}"
            "QLabel {"
            f" color: {foreground};"
            "}"
        )

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
        lines.append(f"  ui_status_headline: {self._build_status_headline(state, safety)}")
        lines.append(f"  operator_mode: {self._current_post_type_mode().label}")
        lines.append(f"  active_preview_visible: {_yes_no(self._has_active_preview(state))}")
        lines.append(f"  verdict: {_or_none(state.verdict)}")
        lines.append(f"  truth_ready: {_yes_no(state.truth_ready)}")
        lines.append(f"  telegram_verified: {_yes_no(state.telegram_verified)}")
        lines.append(f"  blocker_category: {_or_none(state.blocker_category)}")
        lines.append(f"  blocker_reason: {_or_none(state.blocker_reason)}")
        lines.append(f"  blocker_detail: {_or_none(state.blocker_detail)}")
        lines.append(f"  ambiguous: {_yes_no(state.ambiguous)}")
        lines.append(f"  stale: {_yes_no(state.stale)}")
        lines.append(f"  current_run_missing_artifact: {_yes_no(state.current_run_missing_artifact)}")
        lines.append(f"  current_run_backend_reason: {_or_none(state.current_run_backend_reason)}")
        lines.append("")
        lines.append("Выбор кандидата")
        if not state.selection_diagnostics:
            lines.append("  нет")
        else:
            for diagnostic in state.selection_diagnostics:
                lines.append(f"  {diagnostic}")
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
            lines.append(f"  idempotency_key: {_or_none(state.last_publish.idempotency_key)}")
            lines.append(f"  caption_hash: {_or_none(state.last_publish.caption_hash)}")
            lines.append(f"  image_hash: {_or_none(state.last_publish.image_hash)}")
            lines.append(f"  image_path: {_or_none(state.last_publish.image_path)}")
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
    def _format_publish_history_entry(entry: LastPublishState) -> str:
        title = _text(entry.title) or "unknown"
        offer_id = _text(entry.offer_id) or "none"
        parts = [f"{title} / {offer_id}"]
        if entry.success:
            parts.append(
                f"message_id: {_text(entry.message_id) or 'none'} · "
                f"published: {_yes_no_en(entry.published)} · "
                f"telegram_verified: {_yes_no_en(entry.telegram_verified)}"
            )
        else:
            parts.append(f"failed · reason: {_text(entry.reason) or 'unknown'}")
        timestamp = _text(entry.created_at or entry.workflow_modified_at)
        if timestamp:
            parts.append(timestamp)
        return "\n".join(parts)

    @staticmethod
    def _badge_style(post_type_key: str) -> str:
        palette = {
            "single_discount": ("#94ffd0", "#123426", "#2a8c64"),
            "freebie": ("#cfe3ff", "#12284b", "#4380ff"),
            "roundup": ("#edd9ff", "#2a1647", "#8a5cff"),
            "roundup_toplist": ("#edd9ff", "#2a1647", "#8a5cff"),
            "toplist": ("#edd9ff", "#2a1647", "#8a5cff"),
            "unknown": ("#d7def7", "#1b223f", "#525d87"),
        }
        foreground, background, border = palette.get(post_type_key, palette["unknown"])
        return (
            "padding: 9px 10px; "
            "border-radius: 10px; "
            f"border: 1px solid {border}; "
            f"color: {foreground}; "
            f"background-color: {background}; "
            "font-weight: 600;"
        )
