from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import alquimista.storage as storage_module
from alquimista.errors import StorageError
from alquimista.models import AuthMode, ManifestDocument, ManifestEntry, ProjectConfig, SourceConfig
from alquimista.storage import (
    FileTransaction,
    ManifestStore,
    atomic_write_text,
    load_project,
    save_project,
)


def test_empty_source_is_valid_default_configuration() -> None:
    source = SourceConfig()
    assert source.base_url == ""
    assert source.space_key == ""
    assert source.root_value == ""


def test_project_v2_migration_and_secret_free_export(tmp_path: Path) -> None:
    path = tmp_path / "legacy.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "project_name": "Legado",
                "output_dir": "base",
                "sources": [
                    {
                        "id": "fonte1",
                        "name": "Fonte",
                        "base_url": "https://example.test",
                        "space_key": "DOC",
                        "root_mode": "title",
                        "root_value": "Manual",
                        "auth_mode": "browser_session",
                        "state_file": "sessions/segredo.json",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    project = load_project(path)
    assert project.schema_version == 3
    assert project.sources[0].state_file == "sessions/segredo.json"
    saved = tmp_path / "novo.json"
    save_project(saved, project)
    raw = json.loads(saved.read_text(encoding="utf-8"))
    assert raw["schema_version"] == 3
    assert "state_file" not in raw["sources"][0]


def test_file_transaction_publishes_writes_and_deletions_together(tmp_path: Path) -> None:
    updated = tmp_path / "updated.txt"
    deleted = tmp_path / "deleted.txt"
    updated.write_text("old", encoding="utf-8")
    deleted.write_text("remove", encoding="utf-8")

    with FileTransaction(tmp_path) as transaction:
        transaction.stage_text(updated, "new")
        transaction.stage_text(tmp_path / "created.txt", "created")
        transaction.stage_delete(deleted)
        assert updated.read_text(encoding="utf-8") == "old"
        assert deleted.exists()
        transaction.commit()

    assert updated.read_text(encoding="utf-8") == "new"
    assert (tmp_path / "created.txt").read_text(encoding="utf-8") == "created"
    assert not deleted.exists()


def test_file_transaction_rolls_back_when_commit_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "a.txt"
    second = tmp_path / "b.txt"
    first.write_text("old-a", encoding="utf-8")
    second.write_text("old-b", encoding="utf-8")
    original_replace = storage_module.os.replace
    failure_injected = False

    def flaky_replace(source: str | Path, destination: str | Path) -> None:
        nonlocal failure_injected
        source_path = Path(source)
        if (
            not failure_injected
            and Path(destination) == second
            and "staged" in source_path.parts
        ):
            failure_injected = True
            raise OSError("falha simulada")
        original_replace(source, destination)

    monkeypatch.setattr(storage_module.os, "replace", flaky_replace)
    with pytest.raises(StorageError), FileTransaction(tmp_path) as transaction:
        transaction.stage_text(first, "new-a")
        transaction.stage_text(second, "new-b")
        transaction.commit()

    assert first.read_text(encoding="utf-8") == "old-a"
    assert second.read_text(encoding="utf-8") == "old-b"
    assert not list(tmp_path.glob(".alquimista-txn-*"))


def test_file_transaction_preserves_backups_when_rollback_restore_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ISSUE-008: when rollback itself fails, the transaction directory and
    any surviving backups must be preserved for manual recovery instead of
    being destroyed by close()."""
    # "alpha.txt" sorts before "other.txt" so alpha is published first and
    # recorded in ``applied`` before the second publish fails.
    target = tmp_path / "alpha.txt"
    other = tmp_path / "other.txt"
    target.write_text("original", encoding="utf-8")
    original_replace = storage_module.os.replace
    restore_blocked = {"done": False}

    def flaky_replace(source: str | Path, destination: str | Path) -> None:
        source_path = Path(source)
        dest_path = Path(destination)
        # Fail the publish of "other.txt" (second operation) to trigger
        # rollback of the first (already-published) target.
        if dest_path == other and "staged" in source_path.parts:
            raise OSError("falha do segundo publicar")
        # Block the rollback restore (backup -> target) so rollback fails.
        if (
            not restore_blocked["done"]
            and dest_path == target
            and source_path.suffix == ".bak"
        ):
            restore_blocked["done"] = True
            raise OSError("rollback simulada falhou")
        original_replace(source, destination)

    monkeypatch.setattr(storage_module.os, "replace", flaky_replace)
    with pytest.raises(StorageError) as exc_info:
        with FileTransaction(tmp_path) as transaction:
            transaction.stage_text(target, "new")
            transaction.stage_text(other, "other")
            transaction.commit()

    message = str(exc_info.value)
    assert "Rollback incompleto" in message
    assert "Backups preservados" in message
    # The transaction directory must survive so backups are recoverable.
    assert transaction.directory.exists()
    backups_dir = transaction.directory / "backups"
    assert backups_dir.exists()
    assert list(backups_dir.glob("*.bak"))
    # Manual cleanup so pytest tmp_path teardown is quiet.
    import shutil as _shutil
    _shutil.rmtree(transaction.directory, ignore_errors=True)


def test_file_transaction_rolls_back_deletion_restore_preserves_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ISSUE-008: if deletion rollback (restore of deleted original) fails,
    the backup file must not be silently deleted.

    The commit publishes any staged writes first, then processes deletions in
    sorted order. We stage one write ("a-trigger.txt") so a publish happens, and
    two deletions ("z-first.bak" style): the first deletion's backup move
    succeeds (it is recorded in ``applied``), and the second deletion's backup
    move fails to trigger rollback. Rollback then tries to restore the first
    deletion's backup, which we block to force an incomplete rollback.
    """
    trigger = tmp_path / "a-trigger.txt"
    first_deleted = tmp_path / "zz-first.txt"
    second_deleted = tmp_path / "zzzz-second.txt"
    trigger.write_text("trigger-old", encoding="utf-8")
    first_deleted.write_text("first-to-delete", encoding="utf-8")
    second_deleted.write_text("second-to-delete", encoding="utf-8")
    original_replace = storage_module.os.replace
    restore_blocked = {"done": False}

    def flaky_replace(source: str | Path, destination: str | Path) -> None:
        source_path = Path(source)
        dest_path = Path(destination)
        # Block the rollback restore of the first deleted file:
        # os.replace(<backups/xxx.bak>, first_deleted).
        if (
            not restore_blocked["done"]
            and dest_path == first_deleted
            and source_path.suffix == ".bak"
        ):
            restore_blocked["done"] = True
            raise OSError("restauro simulado falhou")
        # Fail the backup move of the second deletion so rollback runs:
        # os.replace(second_deleted, <backups/yyy.bak>).
        if source_path == second_deleted and dest_path.suffix == ".bak":
            raise OSError("falha do backup da segunda exclusao")
        original_replace(source, destination)

    monkeypatch.setattr(storage_module.os, "replace", flaky_replace)
    with pytest.raises(StorageError) as exc_info:
        with FileTransaction(tmp_path) as transaction:
            transaction.stage_text(trigger, "trigger-new")
            transaction.stage_delete(first_deleted)
            transaction.stage_delete(second_deleted)
            transaction.commit()

    message = str(exc_info.value)
    assert "Rollback incompleto" in message
    assert transaction.directory.exists()
    backups_dir = transaction.directory / "backups"
    assert list(backups_dir.glob("*.bak"))
    # The trigger publish rolled back, so its original content survives.
    assert trigger.read_text(encoding="utf-8") == "trigger-old"
    import shutil as _shutil
    _shutil.rmtree(transaction.directory, ignore_errors=True)


def test_file_transaction_creates_target_then_fails_unlinks_published_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ISSUE-008: when a transaction creates a target then a later operation
    fails, rollback must remove the just-created file rather than leaving it
    behind (because it did not exist before the transaction)."""
    # "a-created.txt" sorts before "z-trigger.txt" so it is published first.
    created = tmp_path / "a-created.txt"
    trigger = tmp_path / "z-trigger.txt"
    trigger.write_text("old", encoding="utf-8")
    original_replace = storage_module.os.replace

    def flaky_replace(source: str | Path, destination: str | Path) -> None:
        source_path = Path(source)
        dest_path = Path(destination)
        # Fail the publish of the second (already-existing) target to trigger
        # rollback of the first (just-created) target.
        if dest_path == trigger and "staged" in source_path.parts:
            raise OSError("falha do segundo publicar")
        original_replace(source, destination)

    monkeypatch.setattr(storage_module.os, "replace", flaky_replace)
    with pytest.raises(StorageError):
        with FileTransaction(tmp_path) as transaction:
            transaction.stage_text(created, "new")
            transaction.stage_text(trigger, "new")
            transaction.commit()

    assert not created.exists()
    assert trigger.read_text(encoding="utf-8") == "old"


@pytest.mark.build
def test_install_and_build_scripts_use_constraints_and_bundle_assets() -> None:
    root = Path(__file__).resolve().parents[1]
    install_windows = (root / "tools" / "install" / "instalar_windows.bat").read_text()
    install_linux = (root / "tools" / "install" / "instalar_linux.sh").read_text()
    install_browser = (root / "tools" / "install" / "instalar_navegador.bat").read_text()
    assert "config\\constraints.txt" in install_windows
    assert "config/constraints.txt" in install_linux
    assert "config\\constraints.txt" in install_browser
    build = (root / "tools" / "build" / "gerar_executavel.bat").read_text()
    assert "config\\constraints.txt" in build
    assert '"%ROOT_DIR%\\packaging\\ALQuimista Studio.spec"' in build


def test_urls_with_embedded_credentials_are_rejected() -> None:
    with pytest.raises(ValidationError):
        SourceConfig(base_url="https://user:password@example.test")


@pytest.mark.parametrize("source_id", ["../victim", r"..\victim", "C:drive", "a/b"])
def test_unsafe_source_ids_are_rejected(source_id: str) -> None:
    with pytest.raises(ValidationError):
        SourceConfig(id=source_id)


@pytest.mark.parametrize("mode", [AuthMode.BASIC, AuthMode.BEARER, AuthMode.BROWSER])
def test_authenticated_access_requires_https(mode: AuthMode) -> None:
    with pytest.raises(ValidationError, match="HTTPS"):
        SourceConfig(base_url="http://intranet.example", auth_mode=mode)

    source = SourceConfig(base_url="https://intranet.example", auth_mode=mode)
    assert source.auth_mode == mode


def test_atomic_write_creates_backup(tmp_path: Path) -> None:
    path = tmp_path / "data.txt"
    atomic_write_text(path, "anterior")
    atomic_write_text(path, "novo", backup=True)
    assert path.read_text(encoding="utf-8") == "novo"
    assert path.with_suffix(".txt.bak").read_text(encoding="utf-8") == "anterior"


def test_manifest_migrates_legacy_list(tmp_path: Path) -> None:
    project = ProjectConfig(project_name="Teste")
    path = tmp_path / "manifesto_alquimista.json"
    path.write_text(
        json.dumps(
            [
                {
                    "schema_version": 2,
                    "source_id": "s1",
                    "id": "10",
                    "document_key": "s1:10",
                    "title": "Página",
                    "markdown_path": "paginas/10.md",
                    "status": "new",
                }
            ]
        ),
        encoding="utf-8",
    )
    document = ManifestStore(path, project).load()
    assert document.entries[0].page_id == "10"
    assert document.entries[0].document_key == "s1:10"


def test_manifest_store_rebuilds_queryable_sqlite_sidecar(tmp_path: Path) -> None:
    project = ProjectConfig(project_name="Índice")
    path = tmp_path / "manifesto_alquimista.json"
    store = ManifestStore(path, project)
    entry = ManifestEntry(
        source_id="s1",
        source_type="gitbook_api",
        container_id="space-1",
        document_id="doc-1",
        page_id="doc-1",
        document_key="s1:space-1:doc-1",
        title="Documento",
        etag='"v1"',
    )
    store.save(ManifestDocument(project_id=project.project_id, entries=[entry]))

    assert store.index.path.exists()
    indexed = store.index.get("s1:space-1:doc-1")
    assert indexed is not None
    assert indexed["etag"] == '"v1"'
