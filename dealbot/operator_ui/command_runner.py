from __future__ import annotations

import locale
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Signal


class PreviewCommandRunner(QObject):
    output_ready = Signal(str)
    running_changed = Signal(bool)
    finished = Signal(str, int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process = QProcess(self)
        self._current_command = ""
        self._output_buffer: list[str] = []
        self._process.setProcessChannelMode(QProcess.SeparateChannels)
        self._process.readyReadStandardOutput.connect(self._read_stdout)
        self._process.readyReadStandardError.connect(self._read_stderr)
        self._process.started.connect(self._on_started)
        self._process.finished.connect(self._on_finished)
        self._process.errorOccurred.connect(self._on_error)

    @property
    def is_running(self) -> bool:
        return self._process.state() != QProcess.ProcessState.NotRunning

    def run_preview(self, project_root: Path, post_mode: str = "any") -> bool:
        normalized_post_mode = str(post_mode or "any").strip() or "any"
        return self._start_command(project_root, "preview", ["preview", "--post-mode", normalized_post_mode])

    def run_preview_selected(self, project_root: Path, report_path: Path, candidate_id: str) -> bool:
        return self._start_command(
            project_root,
            "preview-selected",
            ["preview-selected", "--from-report", str(report_path), "--candidate-id", str(candidate_id)],
        )

    def run_publish_previewed(self, project_root: Path, report_path: Path) -> bool:
        return self._start_command(
            project_root,
            "publish-previewed",
            ["publish-previewed", "--from-report", str(report_path)],
        )

    @property
    def last_output(self) -> str:
        return "".join(self._output_buffer)

    @property
    def current_command(self) -> str:
        return self._current_command

    def _start_command(self, project_root: Path, command_name: str, arguments: list[str]) -> bool:
        if self.is_running:
            return False
        batch_path = Path(project_root) / "yoto.bat"
        if not batch_path.exists():
            return False
        self._current_command = command_name
        self._output_buffer = []
        self._process.setWorkingDirectory(str(project_root))
        self._process.start("cmd.exe", ["/c", str(batch_path), *arguments])
        return True

    def _on_started(self) -> None:
        self.running_changed.emit(True)
        command_name = self._current_command or "command"
        self.output_ready.emit(f"[runner] Started yoto.bat {command_name}")

    def _on_finished(self, exit_code: int, _exit_status: QProcess.ExitStatus) -> None:
        self.running_changed.emit(False)
        command_name = self._current_command or "command"
        self.output_ready.emit(f"[runner] {command_name} process finished with exit code {exit_code}")
        self.finished.emit(command_name, int(exit_code))
        self._current_command = ""

    def _on_error(self, _error: QProcess.ProcessError) -> None:
        if self._process.errorString():
            self.output_ready.emit(f"[runner] {self._process.errorString()}")
        if self._process.state() == QProcess.ProcessState.NotRunning and self._current_command:
            command_name = self._current_command
            self.running_changed.emit(False)
            self.finished.emit(command_name, -1)
            self._current_command = ""

    def _read_stdout(self) -> None:
        payload = bytes(self._process.readAllStandardOutput())
        if payload:
            decoded = self._decode(payload)
            self._output_buffer.append(decoded)
            self.output_ready.emit(decoded)

    def _read_stderr(self) -> None:
        payload = bytes(self._process.readAllStandardError())
        if payload:
            decoded = self._decode(payload)
            self._output_buffer.append(decoded)
            self.output_ready.emit(decoded)

    @staticmethod
    def _decode(payload: bytes) -> str:
        encodings = [
            "utf-8",
            locale.getpreferredencoding(False) or "utf-8",
            "cp1251",
            "cp866",
        ]
        for encoding in encodings:
            try:
                return payload.decode(encoding)
            except UnicodeDecodeError:
                continue
        return payload.decode("utf-8", errors="replace")
