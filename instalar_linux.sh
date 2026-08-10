#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3,12) else 1)' || {
  echo "Use Python 3.12." >&2
  exit 1
}
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -c constraints.txt -r requirements.txt
if [[ "${1:-}" == "--with-browser" ]]; then
  python -m pip install -c constraints.txt -r requirements-browser.txt
  python -m playwright install chromium
fi
echo "Instalação concluída."
