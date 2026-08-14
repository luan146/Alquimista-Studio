from __future__ import annotations

from pathlib import Path

from alquimista.connectors.local_files import LocalFilesConnector
from alquimista.models import ExtractionOptions, SourceConfig


def test_local_files_connector(tmp_path: Path) -> None:
    # Setup sample directory structure
    folder_a = tmp_path / "docs_a"
    folder_a.mkdir()
    doc_1 = folder_a / "introducao.md"
    doc_1.write_text("# Introducao ao Sistema\n\nEste e um documento de teste.", encoding="utf-8")

    doc_2 = folder_a / "tabela.csv"
    doc_2.write_text("Chave,Valor\nTimeout,30\nRetries,3\n", encoding="utf-8")

    source_config = SourceConfig(
        id="local-source-1",
        source_type="local_files",
        name="Docs Locais",
        base_url=str(tmp_path),
        connector_options={"path": str(tmp_path)},
    )
    options = ExtractionOptions()
    connector = LocalFilesConnector(source_config, options)

    # 1. Validation
    val = connector.validate_connection()
    assert val["exists"] is True

    # 2. List containers (folders)
    containers = connector.list_containers()
    container_ids = [c.id for c in containers]
    assert "root" in container_ids
    assert "docs_a" in container_ids

    # 3. List documents
    docs = connector.list_documents("docs_a")
    assert len(docs) == 2
    titles = [d.title for d in docs]
    assert "introducao.md" in titles
    assert "tabela.csv" in titles

    # 4. Get document
    doc_meta = next(d for d in docs if d.title == "introducao.md")
    doc = connector.get_document(doc_meta.id, container_id="docs_a")
    assert doc.title == "Introducao ao Sistema"
    assert "Este e um documento de teste." in doc.content

    connector.close()
