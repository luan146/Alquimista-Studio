"""Unattended sync: remembered tokens, the --sync command and the Windows task."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from alquimista import scheduler, session_store
from alquimista.connectors.local_files import LocalFilesConnector
from alquimista.errors import AlquimistaError
from alquimista.headless import EXIT_ERROR, EXIT_OK, sync_project
from alquimista.models import ExtractionOptions, KnowledgeSelection, ProjectConfig, SourceConfig
from alquimista.scheduler import notify as real_notify
from alquimista.storage import load_project, save_project
from alquimista.ui.controllers import RuntimeSecrets


@pytest.fixture
def fake_dpapi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(session_store, "_crypt_protect", lambda data: b"protected:" + data)
    monkeypatch.setattr(session_store, "_crypt_unprotect", lambda data: data.removeprefix(b"protected:"))


def test_remembered_token_is_encrypted_and_reloaded_only_when_opted_in(fake_dpapi: None) -> None:
    path = session_store.save_secret("notion_1", "secret_abc")
    assert "secret_abc" not in path.read_text(encoding="utf-8")

    sources = [
        SourceConfig(id="notion_1", name="Notion", source_type="notion_api", remember_secret=True),
        SourceConfig(id="other", name="Outra", source_type="notion_api", remember_secret=False),
    ]
    session_store.save_secret("other", "nao-deve-carregar")
    secrets = RuntimeSecrets()
    secrets.load_remembered(sources, lambda _message: None)

    assert secrets.get("notion_1") == "secret_abc"
    assert secrets.get("other") == ""
    session_store.delete_secret("notion_1")
    assert session_store.load_secret("notion_1") == ""


def _local_project(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guia.md").write_text("# Guia\n\nPrimeira versão.", encoding="utf-8")
    source = SourceConfig(
        id="local", name="Pasta", source_type="local_files", base_url=str(docs), connector_options={"path": str(docs)}
    )
    document = LocalFilesConnector(source, ExtractionOptions()).list_documents("root")[0]
    project = ProjectConfig(
        output_dir="base",
        sources=[source],
        selections=[KnowledgeSelection(source_id="local", container_id="root", document_id=document.id)],
    )
    project_path = tmp_path / "projeto agendado.json"
    save_project(project_path, project)
    return project_path


def test_sync_command_extracts_and_picks_up_changes_without_the_window(tmp_path: Path, fake_dpapi: None) -> None:
    project_path = _local_project(tmp_path)
    log: list[str] = []

    assert sync_project(project_path, log.append) == EXIT_OK
    written = list((tmp_path / "base").rglob("guia*.md"))
    assert written and "Primeira versão." in written[0].read_text(encoding="utf-8")

    (tmp_path / "docs" / "guia.md").write_text("# Guia\n\nSegunda versão.", encoding="utf-8")
    assert sync_project(project_path, log.append) == EXIT_OK
    assert "Segunda versão." in written[0].read_text(encoding="utf-8")
    assert any("Concluída" in line for line in log)


def test_sync_command_keeps_files_of_removed_documents_unless_the_project_says_so(
    tmp_path: Path, fake_dpapi: None
) -> None:
    # The project's "apagar arquivos removidos" is off by default; --sync used to ignore it.
    project_path = _local_project(tmp_path)
    assert sync_project(project_path, lambda _message: None) == EXIT_OK
    written = list((tmp_path / "base").rglob("guia*.md"))

    (tmp_path / "docs" / "guia.md").unlink()
    assert sync_project(project_path, lambda _message: None) == EXIT_OK
    assert written[0].exists()


def test_sync_command_reports_unusable_project(tmp_path: Path) -> None:
    log: list[str] = []
    assert sync_project(tmp_path / "nao-existe.json", log.append) == EXIT_ERROR
    assert "não executada" in log[-1]


def test_schedule_passes_paths_through_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append({"command": command, "env": kwargs["env"]})
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(scheduler.subprocess, "run", fake_run)
    project = tmp_path / "Pasta com espaço" / "meu projeto.json"

    scheduler.schedule_daily(project, "02:30")

    env = calls[0]["env"]
    assert env["ALQ_TIME"] == "02:30"
    assert str(project.resolve()) in env["ALQ_ARGS"] and '--sync "' in env["ALQ_ARGS"]
    assert '"' not in env["ALQ_NAME"] and env["ALQ_NAME"].startswith("ALQuimista Studio - ")
    # The project path is never interpolated into the PowerShell script itself.
    assert "espaço" not in " ".join(calls[0]["command"])


def test_scheduler_failure_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        scheduler.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, 1, stdout="", stderr="Acesso negado."),
    )
    with pytest.raises(AlquimistaError, match="Acesso negado"):
        scheduler.remove_schedule(tmp_path / "p.json")


def test_remember_checkbox_saves_and_forgets_the_token(qtbot: Any, fake_dpapi: None) -> None:
    from alquimista.models import AuthMode
    from alquimista.ui.main_window import MainWindow

    window = MainWindow("complete")
    qtbot.addWidget(window)
    window.auth_mode.setCurrentIndex(window.auth_mode.findData(AuthMode.BEARER.value))
    window.auth_secret.setText("token-123")
    window.remember_secret.setChecked(True)

    source = window._store_runtime_secret()

    assert source is not None and source.remember_secret
    assert session_store.load_secret(source.id) == "token-123"
    window.remember_secret.setChecked(False)
    window._store_runtime_secret()
    assert session_store.load_secret(source.id) == ""
    window.dirty = False


def test_sync_command_selects_new_files_of_a_whole_folder(tmp_path: Path, fake_dpapi: None) -> None:
    project_path = _local_project(tmp_path)
    project = load_project(project_path)
    project.whole_containers = ["local:root"]
    save_project(project_path, project)
    (tmp_path / "docs" / "novo.md").write_text("# Novo\n\nChegou depois.", encoding="utf-8")

    assert sync_project(project_path, lambda _message: None) == EXIT_OK

    assert list((tmp_path / "base").rglob("novo*.md"))
    assert len(load_project(project_path).selected_keys_for("local")) == 2


def test_sync_command_notifies_changes_and_stays_quiet_otherwise(
    tmp_path: Path, fake_dpapi: None, silence_windows_notifications: list[tuple[str, str]]
) -> None:
    project_path = _local_project(tmp_path)

    assert sync_project(project_path, lambda _message: None) == EXIT_OK
    assert len(silence_windows_notifications) == 1
    assert "1 novo" in silence_windows_notifications[0][1]

    assert sync_project(project_path, lambda _message: None) == EXIT_OK
    assert len(silence_windows_notifications) == 1


def test_sync_command_notifies_when_it_cannot_run(
    tmp_path: Path, silence_windows_notifications: list[tuple[str, str]]
) -> None:
    assert sync_project(tmp_path / "nao-existe.json", lambda _message: None) == EXIT_ERROR
    assert "não foi feita" in silence_windows_notifications[0][1]


def test_notify_hands_title_and_text_to_powershell(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, str]] = []
    monkeypatch.setattr(scheduler, "_powershell", lambda _script, env: calls.append(env) or "")
    real_notify("Título", "Texto")

    assert calls == [{"ALQ_TITLE": "Título", "ALQ_TEXT": "Texto"}]


def test_notify_never_breaks_the_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(_script: str, _env: dict[str, str]) -> str:
        raise AlquimistaError("sem notificações")

    monkeypatch.setattr(scheduler, "_powershell", refuse)
    real_notify("Título", "Texto")
