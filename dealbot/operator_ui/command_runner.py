from __future__ import annotations

import locale
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Signal


class PreviewCommandRunner(QObject):
    output_ready = Signal(str)
    running_changed = Signal(bool)
    finished = Signal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.SeparateChannels)
        self._process.readyReadStandardOutput.connect(self._read_stdout)
        self._process.readyReadStandardError.connect(self._read_stderr)
        self._process.started.connect(self._on_started)
        self._process.finished.connect(self._on_finished)
        self._process.errorOccurred.connect(self._on_error)

    @property
    def is_running(self) -> bool:
        return self._process.state() != QProcess.ProcessState.NotRunning

    def run_preview(self, project_root: Path) -> bool:
        if self.is_running:
            return False
        batch_path = Path(project_root) / "yoto.bat"
        self._process.setWorkingDirectory(str(project_root))
        self._process.start("cmd.exe", ["/c", str(batch_path), "preview"])
        return self._process.waitForStarted(3000)

    def _on_started(self) -> None:
        self.running_changed.emit(True)
        self.output_ready.emit("[runner] Started yoto.bat preview")

    def _on_finished(self, exit_code: int, _exit_status: QProcess.ExitStatus) -> None:
        self.running_changed.emit(False)
        self.output_ready.emit(f"[runner] Preview process finished with exit code {exit_code}")
        self.finished.emit(int(exit_code))

    def _on_error(self, _error: QProcess.ProcessError) -> None:
        if self._process.errorString():
            self.output_ready.emit(f"[runner] {self._process.errorString()}")

    def _read_stdout(self) -> None:
        payload = bytes(self._process.readAllStandardOutput())
        if payload:
            self.output_ready.emit(self._decode(payload))

    def _read_stderr(self) -> None:
        payload = bytes(self._process.readAllStandardError())
        if payload:
            self.output_ready.emit(self._decode(payload))

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
