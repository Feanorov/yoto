from __future__ import annotations

import html
import time
from pathlib import Path

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
from .models import PreviewState, SafetyState, SEND_DISABLED_REASON
from .report_parser import build_preview_state
from .safety import evaluate_preview_safety


class ScaledImageLabel(QLabel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._original_pixmap: QPixmap | None = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(360)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setText("No preview card loaded.")

    def set_preview_pixmap(self, pixmap: QPixmap | None) -> None:
        self._original_pixmap = pixmap
        self._refresh()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        if self._original_pixmap is None or self._original_pixmap.isNull():
            self.setPixmap(QPixmap())
            self.setText("No preview card loaded.")
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

        self.setWindowTitle("YOTO Operator Preview")
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

        title = QLabel("YOTO Desktop Operator")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(title)

        subtitle = QLabel(str(self.project_root))
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #4b5563;")
        layout.addWidget(subtitle)

        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout(status_group)
        self.status_label = QLabel("No preview loaded.")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.post_type_badge = QLabel("Unknown/Unsupported")
        self.post_type_badge.setWordWrap(True)
        self.post_type_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.post_type_badge.setStyleSheet(self._badge_style("unknown"))
        self.send_reason_label = QLabel(SEND_DISABLED_REASON)
        self.send_reason_label.setWordWrap(True)
        self.send_reason_label.setStyleSheet("color: #7c2d12;")
        self.safety_label = QLabel("")
        self.safety_label.setWordWrap(True)
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.post_type_badge)
        status_layout.addWidget(self.send_reason_label)
        status_layout.addWidget(self.safety_label)
        layout.addWidget(status_group)

        actions_group = QGroupBox("Actions")
        actions_layout = QVBoxLayout(actions_group)
        self.run_preview_button = QPushButton("Run Preview")
        self.refresh_button = QPushButton("Refresh Local State")
        self.open_report_button = QPushButton("Open Report")
        self.open_card_button = QPushButton("Open Card")
        self.open_output_button = QPushButton("Open Output Folder")
        self.send_button = QPushButton("Send to Telegram")
        self.send_button.setEnabled(False)
        self.send_button.setToolTip(SEND_DISABLED_REASON)
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
        layout = QVBoxLayout(panel)
        layout.setSpacing(10)

        image_group = QGroupBox("Preview")
        image_layout = QVBoxLayout(image_group)
        self.image_label = ScaledImageLabel(image_group)
        image_layout.addWidget(self.image_label)
        layout.addWidget(image_group, stretch=3)

        caption_group = QGroupBox("Caption")
        caption_layout = QVBoxLayout(caption_group)
        self.caption_tabs = QTabWidget(caption_group)
        self.caption_html_browser = QTextBrowser()
        self.caption_html_browser.setOpenExternalLinks(True)
        self.caption_preview_text = QPlainTextEdit()
        self.caption_preview_text.setReadOnly(True)
        self.caption_tabs.addTab(self.caption_html_browser, "Caption HTML")
        self.caption_tabs.addTab(self.caption_preview_text, "Caption Preview")
        caption_layout.addWidget(self.caption_tabs)
        layout.addWidget(caption_group, stretch=2)
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Vertical, panel)

        details_group = QGroupBox("Details")
        details_layout = QVBoxLayout(details_group)
        self.details_text = QPlainTextEdit()
        self.details_text.setReadOnly(True)
        details_layout.addWidget(self.details_text)

        log_group = QGroupBox("Process Log")
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
        self.send_button.clicked.connect(self.show_send_disabled_dialog)
        self.runner.output_ready.connect(self.append_log)
        self.runner.running_changed.connect(self._set_running)
        self.runner.finished.connect(self._handle_preview_finished)

    def run_preview(self) -> None:
        if self.runner.is_running:
            return
        self._preview_started_at = time.time()
        self.log_text.clear()
        self.append_log(f"[ui] Running {self.project_root / 'yoto.bat'} preview")
        started = self.runner.run_preview(self.project_root)
        if not started:
            self.append_log("[ui] Failed to start yoto.bat preview")
            self.status_label.setText("Preview Failed")

    def refresh_local_state(self, initial: bool = False) -> None:
        if self.current_state and self.current_state.fingerprint:
            bundle = self.resolver.reload_bound_state(self.current_state.fingerprint)
        else:
            bundle = self.resolver.load_latest_local_state()
        state = build_preview_state(bundle) if bundle.workflow_path or bundle.truth_report_path else PreviewState.empty(self.project_root)
        self._apply_state(state)
        if not initial:
            self.append_log("[ui] Local preview state refreshed from disk")

    def _handle_preview_finished(self, exit_code: int) -> None:
        started_at = self._preview_started_at or 0.0
        bundle = self.resolver.load_preview_run(started_at)
        if exit_code != 0 and bundle.workflow_path is None and bundle.truth_report_path is None:
            self.current_state = PreviewState.empty(self.project_root)
            self.current_safety = evaluate_preview_safety(self.current_state)
            self.status_label.setText("Preview Failed")
            self.safety_label.setText("No preview artifacts were produced by the latest run.")
            self.append_log("[ui] Preview command failed before a preview workflow artifact was written")
            self._sync_buttons()
            return
        state = build_preview_state(bundle)
        self._apply_state(state)

    def _apply_state(self, state: PreviewState) -> None:
        self.current_state = state
        self.current_safety = evaluate_preview_safety(state)
        self.status_label.setText(state.status_text)
        self.post_type_badge.setText(state.post_type_label)
        self.post_type_badge.setStyleSheet(self._badge_style(state.post_type_key))
        self.safety_label.setText(self._format_safety_summary(self.current_safety))
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
            self.caption_html_browser.setPlainText("No caption loaded.")
        self.caption_preview_text.setPlainText(state.caption_preview or "No caption preview loaded.")

    def _sync_buttons(self) -> None:
        report_path = self._report_path()
        card_path = self.current_state.card_path if self.current_state else None
        self.open_report_button.setEnabled(bool(report_path and report_path.exists()))
        self.open_card_button.setEnabled(bool(card_path and card_path.exists()))
        self.open_output_button.setEnabled(True)
        self.send_button.setEnabled(False)

    def _set_running(self, running: bool) -> None:
        self.run_preview_button.setEnabled(not running)
        self.refresh_button.setEnabled(not running)
        self.open_report_button.setEnabled(not running and bool(self._report_path() and self._report_path().exists()))
        self.open_card_button.setEnabled(not running and bool(self.current_state and self.current_state.card_exists))
        self.open_output_button.setEnabled(not running)
        self.send_button.setEnabled(False)

    def open_report(self) -> None:
        report_path = self._report_path()
        if report_path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(report_path)))

    def open_card(self) -> None:
        if self.current_state and self.current_state.card_path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.current_state.card_path)))

    def open_output_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.project_root / "output")))

    def show_send_disabled_dialog(self) -> None:
        QMessageBox.information(self, "Send Disabled", SEND_DISABLED_REASON)

    def append_log(self, text: str) -> None:
        stripped = text.rstrip()
        if not stripped:
            return
        self.log_text.appendPlainText(stripped)

    def _report_path(self) -> Path | None:
        if self.current_state is None:
            return None
        return self.current_state.paths.truth_report_path or self.current_state.paths.workflow_path

    def _format_details(self, state: PreviewState, safety: SafetyState) -> str:
        lines: list[str] = []
        target = state.selected_target
        lines.append("Selected Target")
        if target is None:
            lines.append("  none")
        else:
            lines.append(f"  title: {target.title or 'none'}")
            lines.append(f"  post_type: {state.post_type_label}")
            lines.append(f"  offer_id: {target.offer_id or 'none'}")
            lines.append(f"  source: {target.source or 'none'}")
            lines.append(f"  lane: {target.lane or 'none'}")
            lines.append(f"  bucket: {target.bucket or 'none'}")
            lines.append(f"  content_family: {target.content_family or 'none'}")
        lines.append("")
        lines.append("Status")
        lines.append(f"  status_text: {state.status_text}")
        lines.append(f"  verdict: {state.verdict or 'none'}")
        lines.append(f"  truth_ready: {'yes' if state.truth_ready else 'no'}")
        lines.append(f"  telegram_verified: {'yes' if state.telegram_verified else 'no'}")
        lines.append(f"  blocker_category: {state.blocker_category or 'none'}")
        lines.append(f"  blocker_reason: {state.blocker_reason or 'none'}")
        lines.append(f"  blocker_detail: {state.blocker_detail or 'none'}")
        lines.append(f"  ambiguous: {'yes' if state.ambiguous else 'no'}")
        lines.append(f"  stale: {'yes' if state.stale else 'no'}")
        lines.append("")
        lines.append("Ingest / Source Health")
        if not state.ingest_sources:
            lines.append("  none")
        else:
            for source in state.ingest_sources:
                offers_text = str(source.offers) if source.offers is not None else "n/a"
                lines.append(f"  {source.name}: status={source.status} reason={source.reason} offers={offers_text}")
        lines.append("")
        lines.append("Paths")
        lines.append(f"  report_path: {self._report_path() or 'none'}")
        lines.append(f"  image_path: {state.card_path or 'none'}")
        lines.append(f"  latest_snapshot_manifest: {state.paths.latest_snapshot_manifest_path or 'none'}")
        lines.append(f"  latest_publish_outcome: {state.paths.latest_publish_outcome_path or 'none'}")
        lines.append("")
        lines.append("Safety")
        lines.append(f"  send_enabled: {'yes' if safety.send_enabled else 'no'}")
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
        if safety.blockers:
            return " | ".join(safety.blockers)
        if safety.preview_ready:
            return "Preview artifacts are loaded. Sending remains disabled in this MVP shell."
        return "Preview is available but not yet ready for a send-capable UI."

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
