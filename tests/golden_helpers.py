from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent / "fixtures" / "goldens"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def read_json(path: Path) -> Any:
    return json.loads(read_text(path))


def assert_golden_text(
    actual: str, expected_path: Path, *, exact: bool = False
) -> None:
    expected = read_text(expected_path)
    normalized = actual.replace("\r\n", "\n")
    if not exact:
        normalized = normalized.rstrip("\n")
        expected = expected.rstrip("\n")
    assert normalized == expected


def assert_golden_json(actual: Any, expected_path: Path) -> None:
    assert actual == read_json(expected_path)
