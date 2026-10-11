#!/usr/bin/env bash
# Builds the Linux portable package (.tar.gz) and installer (.deb), both with no Python needed.
# SEM_TESSERACT=1 builds the portable package without Tesseract (images keep only their description).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"
PYTHON_CMD="${PYTHON_CMD:-$ROOT_DIR/.venv/bin/python}"
if [[ ! -x "$PYTHON_CMD" ]]; then
  PYTHON_CMD="python3"
fi
# Default: __version__ from alquimista/__init__.py (single source of the version).
VERSION="${1:-$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' alquimista/__init__.py)}"
[[ -n "$VERSION" ]] || { echo "__version__ não encontrado em alquimista/__init__.py" >&2; exit 1; }
BUILD_ID="$(date +%Y%m%d-%H%M%S-%N)"
BUILD_ROOT="$ROOT_DIR/.tmp/pyinstaller-linux-$BUILD_ID"
BUILD_DIST="$BUILD_ROOT/dist"
BUILD_WORK="$BUILD_ROOT/work"
RELEASE_DIR="$ROOT_DIR/dist/releases"
PACKAGE_NAME="ALQuimista-Studio-linux-portable"
STAGING_ROOT="$ROOT_DIR/.tmp/$PACKAGE_NAME-$BUILD_ID"
PACKAGE_DIR="$STAGING_ROOT/$PACKAGE_NAME"
ARCHIVE="$RELEASE_DIR/ALQuimista-Studio-linux-portable-$VERSION.tar.gz"
DEB_ROOT="$STAGING_ROOT/deb"
DEB="$RELEASE_DIR/ALQuimista-Studio-linux-installer-$VERSION.deb"

# alquimista/image_text.py looks for <executable folder>/tesseract/tesseract and adds tesseract/lib.
bundle_tesseract() {
  local dest="$1" binary data language
  binary="$(command -v tesseract)" || {
    echo "Tesseract não encontrado. Instale com: sudo apt install tesseract-ocr tesseract-ocr-por tesseract-ocr-spa (ou gere com SEM_TESSERACT=1)." >&2
    exit 1
  }
  data="$(dirname "$(find /usr/share/tesseract-ocr /usr/share/tessdata -name eng.traineddata 2>/dev/null | head -n 1)")"
  mkdir -p "$dest/lib" "$dest/tessdata"
  cp "$binary" "$dest/tesseract"
  # Every library it needs except the C library itself, which must come from the running system.
  ldd "$binary" | awk '/=> \// {print $3}' \
    | grep -vE '/(libc|libm|libdl|libpthread|librt|ld-linux[^/]*)\.so' \
    | xargs -r cp -L -t "$dest/lib"
  for language in eng por spa osd; do
    if [[ -f "$data/$language.traineddata" ]]; then cp "$data/$language.traineddata" "$dest/tessdata/"; fi
  done
  [[ -f "$dest/tessdata/por.traineddata" ]] || { echo "Falta por.traineddata (sudo apt install tesseract-ocr-por)." >&2; exit 1; }
}

"$PYTHON_CMD" -m PyInstaller --noconfirm --clean \
  --workpath "$BUILD_WORK" --distpath "$BUILD_DIST" \
  "$ROOT_DIR/packaging/ALQuimista Studio.spec"
BUILT_EXECUTABLE="$BUILD_DIST/ALQuimista Studio"
if [[ ! -f "$BUILT_EXECUTABLE" ]]; then
  echo "PyInstaller terminou sem gerar um executável Linux novo." >&2
  exit 1
fi
mkdir -p "$RELEASE_DIR"

# Portable: everything inside one folder, settings in data/.
mkdir -p "$PACKAGE_DIR/data"
touch "$PACKAGE_DIR/data/.keep"
cp "$BUILT_EXECUTABLE" "$PACKAGE_DIR/ALQuimista Studio"
cp "$ROOT_DIR/distribuicao/LEIA-ME-PORTATIL.txt" "$PACKAGE_DIR/LEIA-ME-PORTATIL.txt"
touch "$PACKAGE_DIR/portable.flag"
chmod +x "$PACKAGE_DIR/ALQuimista Studio"
if [[ "${SEM_TESSERACT:-0}" != "1" ]]; then
  bundle_tesseract "$PACKAGE_DIR/tesseract"
fi
rm -f "$ARCHIVE"
tar -czf "$ARCHIVE" -C "$STAGING_ROOT" "$PACKAGE_NAME"

# Installer: apt installs Tesseract and the graphics libraries Qt needs as dependencies.
mkdir -p "$DEB_ROOT/DEBIAN" "$DEB_ROOT/opt/alquimista-studio" "$DEB_ROOT/usr/bin" \
  "$DEB_ROOT/usr/share/applications" "$DEB_ROOT/usr/share/icons/hicolor/scalable/apps"
install -m 755 "$BUILT_EXECUTABLE" "$DEB_ROOT/opt/alquimista-studio/alquimista-studio"
ln -s /opt/alquimista-studio/alquimista-studio "$DEB_ROOT/usr/bin/alquimista-studio"
cp "$ROOT_DIR/alquimista/ui/assets/d20.svg" "$DEB_ROOT/usr/share/icons/hicolor/scalable/apps/alquimista-studio.svg"
cat > "$DEB_ROOT/usr/share/applications/alquimista-studio.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=ALQuimista Studio
Comment=Extrai documentação para Markdown
Exec=/opt/alquimista-studio/alquimista-studio
Icon=alquimista-studio
Terminal=false
Categories=Utility;Development;
DESKTOP
cat > "$DEB_ROOT/DEBIAN/control" <<CONTROL
Package: alquimista-studio
Version: $VERSION
Architecture: amd64
Maintainer: luan146 <luan146@users.noreply.github.com>
Depends: tesseract-ocr, tesseract-ocr-por, tesseract-ocr-spa, libegl1, libgl1, libfontconfig1, libxkbcommon-x11-0, libxcb-cursor0, libdbus-1-3
Section: utils
Priority: optional
Homepage: https://github.com/luan146/Alquimista-Studio
Description: ALQuimista Studio
 Extrai documentação de Confluence, Notion, SharePoint, GitBook e outras
 fontes para Markdown e consolida em pacotes para uso em IA.
CONTROL
rm -f "$DEB"
dpkg-deb --root-owner-group --build "$DEB_ROOT" "$DEB"

rm -rf -- "$BUILD_ROOT" "$STAGING_ROOT"
echo "Portable Linux: $ARCHIVE"
echo "Instalador Linux: $DEB"
