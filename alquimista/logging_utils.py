from __future__ import annotations

import json
import logging
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

SENSITIVE = re.compile(
    r"(?i)(authorization|bearer|token|password|senha|cookie|secret)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)


def redact(value: str) -> str:
    return SENSITIVE.sub(r"\1\2***", value)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "time": datetime.now().astimezone().isoformat(timespec="seconds"),
            "level": record.levelname,
            "message": redact(record.getMessage()),
            "logger": record.name,
        }
        if record.exc_info:
            data["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(data, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Human-readable formatter for a live CMD/terminal diagnostic stream."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now().astimezone().strftime("%H:%M:%S")
        return f"[{timestamp}] {record.levelname:<5} {redact(record.getMessage())}"


def configure_logging(log_path: Path) -> logging.Logger:
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        log_path = Path(tempfile.gettempdir()) / "alquimista-studio" / log_path.name
        log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("alquimista")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    try:
        handler = logging.FileHandler(log_path, encoding="utf-8")
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "alquimista-studio" / log_path.name
        fallback.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(fallback, encoding="utf-8")
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    console_stream = getattr(sys, "stdout", None) or getattr(sys, "__stdout__", None)
    if console_stream is not None:
        console_handler = logging.StreamHandler(console_stream)
        console_handler.setFormatter(ConsoleFormatter())
        logger.addHandler(console_handler)
    logger.propagate = False
    return logger


def default_log_path() -> Path:
    import os

    root = os.environ.get("LOCALAPPDATA")
    base = Path(root) / "ALQuimista Studio" if root else Path.home() / ".alquimista-studio"
    return base / "logs" / "alquimista.jsonl"
