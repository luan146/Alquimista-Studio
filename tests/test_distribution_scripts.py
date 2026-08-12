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

    assert '__version__ = "0.9"' in package
    assert '[string]$Version = "0.9"' in windows
    assert 'VERSION="${1:-0.9}"' in linux
    assert '#define AppVersion "0.9"' in installer
    assert 'rm -rf -- "$BUILD_ROOT" "$STAGING_ROOT"' in linux
