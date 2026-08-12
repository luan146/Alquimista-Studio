#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"
python3 -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3,12) else 1)' || {
  echo "Use Python 3.12." >&2
  exit 1
}
python3 -m venv "$ROOT_DIR/.venv"
. "$ROOT_DIR/.venv/bin/activate"
python -m pip install -c "$ROOT_DIR/config/constraints.txt" -r "$ROOT_DIR/config/requirements.txt"
if [[ "${1:-}" == "--with-browser" ]]; then
  python -m pip install -c "$ROOT_DIR/config/constraints.txt" -r "$ROOT_DIR/config/requirements-browser.txt"
  python -m playwright install chromium
fi
echo "Instalação concluída."
