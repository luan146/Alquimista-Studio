#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"
PYTHON_CMD="${PYTHON_CMD:-$ROOT_DIR/.venv/bin/python}"
if [[ ! -x "$PYTHON_CMD" ]]; then
  PYTHON_CMD="python3"
fi
VERSION="${1:-0.9.5}"
BUILD_ID="$(date +%Y%m%d-%H%M%S-%N)"
BUILD_ROOT="$ROOT_DIR/.tmp/pyinstaller-linux-$BUILD_ID"
BUILD_DIST="$BUILD_ROOT/dist"
BUILD_WORK="$BUILD_ROOT/work"
RELEASE_DIR="$ROOT_DIR/dist/releases"
PACKAGE_NAME="ALQuimista-Studio-linux-portable"
STAGING_ROOT="$ROOT_DIR/.tmp/$PACKAGE_NAME-$BUILD_ID"
PACKAGE_DIR="$STAGING_ROOT/$PACKAGE_NAME"
ARCHIVE="$RELEASE_DIR/ALQuimista-Studio-linux-portable-$VERSION.tar.gz"

"$PYTHON_CMD" -m PyInstaller --noconfirm --clean \
  --workpath "$BUILD_WORK" --distpath "$BUILD_DIST" \
  "$ROOT_DIR/packaging/ALQuimista Studio.spec"
BUILD_EXIT=$?
if [[ "$BUILD_EXIT" -ne 0 ]]; then
  exit "$BUILD_EXIT"
fi
BUILT_EXECUTABLE="$BUILD_DIST/ALQuimista Studio"
if [[ ! -f "$BUILT_EXECUTABLE" ]]; then
  echo "PyInstaller terminou sem gerar um executável Linux novo." >&2
  exit 1
fi

mkdir -p "$PACKAGE_DIR/data"
touch "$PACKAGE_DIR/data/.keep"
cp "$BUILT_EXECUTABLE" "$PACKAGE_DIR/ALQuimista Studio"
cp "$ROOT_DIR/distribuicao/LEIA-ME-PORTATIL.txt" "$PACKAGE_DIR/LEIA-ME-PORTATIL.txt"
touch "$PACKAGE_DIR/portable.flag"
chmod +x "$PACKAGE_DIR/ALQuimista Studio"
mkdir -p "$RELEASE_DIR"
rm -f "$ARCHIVE"
tar -czf "$ARCHIVE" -C "$STAGING_ROOT" "$PACKAGE_NAME"
rm -rf -- "$BUILD_ROOT" "$STAGING_ROOT"
echo "Portable Linux: $ARCHIVE"
