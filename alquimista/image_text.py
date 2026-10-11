"""Read the text inside images with Tesseract, shipped next to the Windows and Linux executables."""
from __future__ import annotations

import base64
import functools
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests

from .errors import AlquimistaError, ExtractionCancelledError
from .markdown import ImageReader

MAX_IMAGE_BYTES = 10 * 1024 * 1024
_PREFERRED_LANGUAGES = ("por", "eng", "spa")
_EXECUTABLE_NAME = "tesseract.exe" if sys.platform == "win32" else "tesseract"


def tesseract_path() -> Path | None:
    """Bundled Tesseract first, then ALQUIMISTA_TESSERACT, PATH and the default Windows folder."""
    candidates = [
        Path(sys.executable).parent / "tesseract" / _EXECUTABLE_NAME if getattr(sys, "frozen", False) else None,
        Path(os.environ["ALQUIMISTA_TESSERACT"]) if os.environ.get("ALQUIMISTA_TESSERACT") else None,
        Path(found) if (found := shutil.which("tesseract")) else None,
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR" / "tesseract.exe",
    ]
    return next((path for path in candidates if path is not None and path.is_file()), None)


def _run(executable: Path, arguments: list[str], data: bytes | None = None) -> str:
    env = dict(os.environ)
    if (executable.parent / "tessdata").is_dir():
        env["TESSDATA_PREFIX"] = str(executable.parent / "tessdata")
    if sys.platform != "win32":
        env.update(_library_path(executable, env))
    completed = subprocess.run(
        [str(executable), *arguments],
        input=data,
        capture_output=True,
        timeout=60,
        env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    return completed.stdout.decode("utf-8", errors="replace") if completed.returncode == 0 else ""


def _library_path(executable: Path, env: dict[str, str]) -> dict[str, str]:
    """Linux: the bundled libraries first; never PyInstaller's own, which can clash with the system Tesseract."""
    inherited = env.pop("LD_LIBRARY_PATH_ORIG", "") if getattr(sys, "frozen", False) else env.get("LD_LIBRARY_PATH", "")
    bundled = executable.parent / "lib"
    paths = [str(bundled)] if bundled.is_dir() else []
    return {"LD_LIBRARY_PATH": os.pathsep.join(paths + ([inherited] if inherited else []))}


@functools.cache
def _languages(executable: Path) -> str:
    installed = set(_run(executable, ["--list-langs"]).split())
    return "+".join(language for language in _PREFERRED_LANGUAGES if language in installed) or "eng"


def read_text(executable: Path, data: bytes) -> str:
    """Text Tesseract finds in the image bytes; empty when there is none or it cannot read them."""
    return _run(executable, ["stdin", "stdout", "-l", _languages(executable)], data).strip()


def _public_download(url: str) -> bytes:
    response = requests.get(url, timeout=(10, 30))
    response.raise_for_status()
    return response.content


def _image_bytes(url: str, download: Callable[[str], bytes]) -> bytes | None:
    if url.startswith("data:") and ";base64," in url:
        return base64.b64decode(url.split(";base64,", 1)[1])
    if url.startswith(("http://", "https://")):
        return download(url)
    return None


def image_text_reader(connector: Any) -> ImageReader | None:
    """Reader that downloads an image with the connector's access and returns its text.

    Credentials only go to the source's own origin (the connector clients enforce it);
    connectors without a client download public images anonymously. Results are kept
    per URL, so a logo repeated on every page is read once.
    """
    executable = tesseract_path()
    if executable is None:
        return None
    download = getattr(getattr(connector, "client", None), "download", None)
    fetch: Callable[[str], bytes] = download if callable(download) else _public_download
    cache: dict[str, str] = {}

    def read(url: str) -> str:
        if url not in cache:
            try:
                data = _image_bytes(url, fetch)
                cache[url] = read_text(executable, data) if data and len(data) <= MAX_IMAGE_BYTES else ""
            except ExtractionCancelledError:
                raise
            except (AlquimistaError, requests.RequestException, OSError, ValueError, subprocess.SubprocessError):
                # The description alone still goes into the Markdown.
                cache[url] = ""
        return cache[url]

    return read


__all__ = ["MAX_IMAGE_BYTES", "image_text_reader", "read_text", "tesseract_path"]
