from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_readme_documents_the_integration_status_vocabulary() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    for status in ("Estável", "Disponível", "Experimental", "Parcial", "Em desenvolvimento", "Planejado"):
        assert status in readme


def test_build_script_uses_the_pinned_installer_and_ui_assets() -> None:
    build = (ROOT / "gerar_executavel.bat").read_text(encoding="utf-8")

    assert "pip install -c constraints.txt pyinstaller" in build
    assert '"ALQuimista Studio.spec"' in build
