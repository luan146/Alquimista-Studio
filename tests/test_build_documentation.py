from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_readme_documents_the_integration_status_vocabulary() -> None:
    readme = (ROOT / "README.pt-BR.md").read_text(encoding="utf-8")

    for status in (
        "Estável",
        "Disponível",
        "Experimental",
        "Parcial",
        "Em desenvolvimento",
        "Planejado",
    ):
        assert status in readme


def test_readmes_expose_both_language_options() -> None:
    english = (ROOT / "README.md").read_text(encoding="utf-8")
    portuguese = (ROOT / "README.pt-BR.md").read_text(encoding="utf-8")

    assert "README.pt-BR.md" in english
    assert "README.md" in portuguese


def test_build_script_uses_the_pinned_installer_and_ui_assets() -> None:
    build = (ROOT / "gerar_executavel.bat").read_text(encoding="utf-8")

    assert "pip install -c constraints.txt pyinstaller" in build
    assert '"ALQuimista Studio.spec"' in build
