#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"
INSTALL_MODE=0
if [[ "${1:-}" == "--install" ]]; then
  INSTALL_MODE=1
  shift
fi
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
if [[ "$INSTALL_MODE" == "1" ]]; then
  INSTALL_DIR="${ALQUIMISTA_INSTALL_DIR:-$HOME/.local/opt/alquimista-studio}"
  mkdir -p "$INSTALL_DIR"
  cp -R "$ROOT_DIR/alquimista" "$ROOT_DIR/assets" "$ROOT_DIR/config" "$INSTALL_DIR/"
  cat > "$INSTALL_DIR/alquimista-studio" <<'LAUNCHER'
#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"
exec python3 -m alquimista "$@"
LAUNCHER
  chmod +x "$INSTALL_DIR/alquimista-studio"
  mkdir -p "$HOME/.local/share/applications"
  cat > "$HOME/.local/share/applications/alquimista-studio.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=ALQuimista Studio
Exec=$INSTALL_DIR/alquimista-studio
Terminal=false
Categories=Utility;Development;
DESKTOP
  echo "ALQuimista Studio instalado em $INSTALL_DIR"
  exit 0
fi
echo "Instalação concluída."
