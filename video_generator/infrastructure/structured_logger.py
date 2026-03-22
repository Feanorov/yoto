from __future__ import annotations

from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any


class StructuredLogger:
    def __init__(self, name: str = 'video_generator') -> None:
        self.logger = logging.getLogger(name)

    def info(self, event: str, **fields: Any) -> None:
        self._log(logging.INFO, event, **fields)

    def warning(self, event: str, **fields: Any) -> None:
        self._log(logging.WARNING, event, **fields)

    def error(self, event: str, **fields: Any) -> None:
        self._log(logging.ERROR, event, **fields)

    def _log(self, level: int, event: str, **fields: Any) -> None:
        payload = {'event': event, **fields}
        self.logger.log(level, json.dumps(payload, ensure_ascii=False, default=self._default))

    @staticmethod
    def _default(value: Any) -> Any:
        if isinstance(value, (datetime, Path)):
            return str(value)
        return value


def configure_logging(level: str = 'INFO') -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format='%(message)s')
