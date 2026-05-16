from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


def resolve_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def create_application(argv: Sequence[str] | None = None) -> QApplication:
    app = QApplication(list(argv or sys.argv))
    app.setApplicationName("YOTO Operator Preview")
    app.setOrganizationName("YOTO")
    return app


def run(argv: Sequence[str] | None = None) -> int:
    app = create_application(argv)
    window = MainWindow(resolve_project_root())
    window.show()
    return int(app.exec())
