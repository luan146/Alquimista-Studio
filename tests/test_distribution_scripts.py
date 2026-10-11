import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_linux_distribution_requires_pyinstaller_and_uses_fresh_paths() -> None:
    requirements = (ROOT / "config" / "requirements-dev.txt").read_text(encoding="utf-8")
    script = (ROOT / "tools" / "build" / "gerar_portable_linux.sh").read_text(
        encoding="utf-8"
    )

    assert "pyinstaller" in requirements.lower()
    assert 'BUILD_ID="$(date ' in script
    assert 'BUILT_EXECUTABLE="$BUILD_DIST/ALQuimista Studio"' in script
    assert "PyInstaller terminou sem gerar" in script
    assert 'tar -czf "$ARCHIVE" -C "$STAGING_ROOT" "$PACKAGE_NAME"' in script


def test_windows_installer_receives_the_new_executable_path() -> None:
    script = (ROOT / "tools" / "build" / "gerar_distribuicoes.ps1").read_text(
        encoding="utf-8"
    )
    installer = (ROOT / "packaging" / "ALQuimista Studio.iss").read_text(
        encoding="utf-8"
    )

    assert '"/DAppExeSource=$builtExe"' in script
    assert 'Source: "{#AppExeSource}"' in installer
    assert 'Remove-Item -LiteralPath $buildRoot, $portableRoot' in script


def test_distribution_defaults_use_current_product_version() -> None:
    package = (ROOT / "alquimista" / "__init__.py").read_text(encoding="utf-8")
    windows = (ROOT / "tools" / "build" / "gerar_distribuicoes.ps1").read_text(
        encoding="utf-8"
    )
    linux = (ROOT / "tools" / "build" / "gerar_portable_linux.sh").read_text(
        encoding="utf-8"
    )
    installer = (ROOT / "packaging" / "ALQuimista Studio.iss").read_text(
        encoding="utf-8"
    )

    # The version lives only in __init__.py; scripts and installer derive it.
    assert re.search(r'^__version__ = "\d+\.\d+\.\d+"$', package, re.MULTILINE)
    assert "alquimista\\__init__.py" in windows and '[string]$Version = ""' in windows
    assert "alquimista/__init__.py" in linux and 'VERSION="${1:-$(sed' in linux
    assert "#error" in installer and not re.search(r'AppVersion "\d', installer)
    assert 'rm -rf -- "$BUILD_ROOT" "$STAGING_ROOT"' in linux


def test_windows_distributions_ship_tesseract_next_to_the_executable() -> None:
    script = (ROOT / "tools" / "build" / "gerar_distribuicoes.ps1").read_text(encoding="utf-8")
    installer = (ROOT / "packaging" / "ALQuimista Studio.iss").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "quality.yml").read_text(encoding="utf-8")

    # alquimista/image_text.py looks for <executable folder>/tesseract/tesseract.exe.
    assert '[switch]$SemTesseract' in script and "$env:ALQ_TESSERACT_DIR" in script
    assert '(Join-Path $portableRoot "tesseract")' in script
    assert '"/DTesseractDir=$tesseractStage"' in script
    assert r'DestDir: "{app}\tesseract"' in installer and "#ifdef TesseractDir" in installer
    assert workflow.index("choco install tesseract") < workflow.index("Run pytest")


def test_linux_distributions_ship_tesseract_and_an_installer() -> None:
    script = (ROOT / "tools" / "build" / "gerar_portable_linux.sh").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "quality.yml").read_text(encoding="utf-8")

    # alquimista/image_text.py looks for <executable folder>/tesseract/tesseract and its lib/ folder.
    assert 'bundle_tesseract "$PACKAGE_DIR/tesseract"' in script and 'mkdir -p "$dest/lib"' in script
    assert "Depends: tesseract-ocr, tesseract-ocr-por, tesseract-ocr-spa" in script
    assert 'dpkg-deb --root-owner-group --build "$DEB_ROOT" "$DEB"' in script
    assert workflow.index("tools/build/gerar_portable_linux.sh") < workflow.index("tools/build/testar_pacotes_linux.sh")
    assert "needs: [test, linux-distribution]" in workflow and "gh release create" in workflow
