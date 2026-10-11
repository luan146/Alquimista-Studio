#!/usr/bin/env bash
# CI check: the Linux packages work on clean Ubuntu systems with neither Python nor Tesseract.
set -euo pipefail
cd "$(dirname "$0")/../.."
work="$(mktemp -d)"
tar -xzf dist/releases/ALQuimista-Studio-linux-portable-*.tar.gz -C "$work"
cp dist/releases/ALQuimista-Studio-linux-installer-*.deb "$work/instalador.deb"
python -c "
from PIL import Image, ImageDraw, ImageFont
image = Image.new('RGB', (900, 160), 'white')
ImageDraw.Draw(image).text((20, 40), 'ALQUIMISTA 2026', fill='black', font=ImageFont.load_default(size=64))
image.save('$work/texto.png')"

check() {  # name, docker image, script
  echo "== $1 ($2)"
  if ! docker run --rm -e DEBIAN_FRONTEND=noninteractive -v "$work:/w" "$2" bash -c "$3" > "$work/saida.txt" 2>&1; then
    # Logs need a GitHub login; annotations are public, so the failure is readable there.
    echo "::error title=$1 ($2)::$(tail -n 40 "$work/saida.txt" | sed ':a;N;$!ba;s/%/%25/g;s/\r//g;s/\n/%0A/g')"
    exit 1
  fi
  tail -n 3 "$work/saida.txt"
}
# Exit code 124 = still running when timeout closed it, so the window opened and stayed open.
opens='status=0; xvfb-run -a timeout 20 "$0" || status=$?; test "$status" -eq 124'

for system in ubuntu:22.04 ubuntu:24.04; do
  check "Tesseract do portátil" "$system" \
    'cd /w/ALQuimista-Studio-linux-portable/tesseract && LD_LIBRARY_PATH=lib TESSDATA_PREFIX=tessdata ./tesseract /w/texto.png stdout -l por | grep ALQUIMISTA'
  check "Portátil abre" "$system" \
    "apt-get update -qq && apt-get install -y -qq xvfb xauth libegl1 libgl1 libfontconfig1 libxkbcommon-x11-0 libdbus-1-3 >/dev/null
     bash -c '$opens' '/w/ALQuimista-Studio-linux-portable/ALQuimista Studio'"
  check "Instalador .deb" "$system" \
    "apt-get update -qq && apt-get install -y -qq /w/instalador.deb xvfb xauth >/dev/null
     tesseract --list-langs | grep -x por
     bash -c '$opens' alquimista-studio"
done
