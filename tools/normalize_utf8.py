from __future__ import annotations

import argparse
import os
from pathlib import Path

SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", ".pytest-local", "docs"}
TEXT_EXTENSIONS = {".py", ".md", ".txt", ".json"}

# Characters produced when UTF-8 was decoded as CP1252/Latin-1.
CP1252_REVERSE = {
    "€": 0x80, "‚": 0x82, "ƒ": 0x83, "„": 0x84, "…": 0x85,
    "†": 0x86, "‡": 0x87, "ˆ": 0x88, "‰": 0x89, "Š": 0x8A,
    "‹": 0x8B, "Œ": 0x8C, "Ž": 0x8E, "‘": 0x91, "’": 0x92,
    "“": 0x93, "”": 0x94, "•": 0x95, "–": 0x96, "—": 0x97,
    "˜": 0x98, "™": 0x99, "š": 0x9A, "›": 0x9B, "œ": 0x9C,
    "ž": 0x9E, "Ÿ": 0x9F,
}


def cp1252_bytes(value: str) -> bytes:
    result = bytearray()
    for char in value:
        code = ord(char)
        if code <= 0xFF:
            result.append(code)
        elif char in CP1252_REVERSE:
            result.append(CP1252_REVERSE[char])
        else:
            raise UnicodeEncodeError("cp1252", value, 0, 1, "not a legacy byte")
    return bytes(result)


def mojibake_score(value: str) -> int:
    markers = ("Ã", "Â", "â", "ð", "ï¿½", "�")
    return sum(value.count(marker) for marker in markers)


def repair_mojibake(value: str) -> str:
    current = value
    for _ in range(3):
        if mojibake_score(current) == 0:
            break
        try:
            candidate = cp1252_bytes(current).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if candidate == current or mojibake_score(candidate) >= mojibake_score(current):
            break
        current = candidate
    return current


def iter_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize project text files as UTF-8.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check", action="store_true", help="Only report files that need changes.")
    args = parser.parse_args()
    root = args.root.resolve()
    changed = 0
    pending = 0
    for path in iter_files(root):
        try:
            original = path.read_text(encoding="utf-8-sig", newline="")
        except (UnicodeDecodeError, OSError) as exc:
            print(f"ERROR {path}: {exc}")
            continue
        fixed = repair_mojibake(original)
        if fixed == original and not original.startswith("\ufeff"):
            continue
        changed += 1
        if args.check:
            print(f"NEEDS_FIX {path}")
            continue
        try:
            path.write_text(fixed, encoding="utf-8", newline="")
            print(f"FIXED {path}")
        except PermissionError:
            temp_path = Path(os.environ.get("TEMP", ".")) / f"normalize_{path.name}"
            temp_path.write_text(fixed, encoding="utf-8", newline="")
            pending += 1
            print(f"PENDING {path} :: {temp_path}")
    print(f"changed={changed} pending={pending}")
    return 0 if pending == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
