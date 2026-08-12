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
