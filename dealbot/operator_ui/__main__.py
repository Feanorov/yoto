from __future__ import annotations

import sys


def main() -> int:
    try:
        from .app import run
    except ModuleNotFoundError as exc:
        if exc.name == "PySide6":
            print("PySide6 is required to run dealbot.operator_ui.", file=sys.stderr)
            return 1
        raise
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
