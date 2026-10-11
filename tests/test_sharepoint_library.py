"""SharePoint: every convertible file of a library, in subfolders and across pages,
is extracted to Markdown and consolidated."""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest

from alquimista.connectors.sharepoint import SharePointConnector
from alquimista.models import ExtractionOptions, ProjectConfig, SourceConfig
from alquimista.services import ConsolidationService, ExtractionService, SourceRuntime

docx = pytest.importorskip("docx")
openpyxl = pytest.importorskip("openpyxl")
pptx = pytest.importorskip("pptx")

GRAPH = "https://graph.microsoft.com/v1.0"
DRIVE = "/sites/site-1/drive"


def _docx(text: str) -> bytes:
    document = docx.Document()
    document.add_heading("Guia de instalação", level=1)
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _xlsx() -> bytes:
    workbook = openpyxl.Workbook()
    workbook.active.append(["Produto", "Preço"])
    workbook.active.append(["Licença anual", 1200])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _pptx() -> bytes:
    presentation = pptx.Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[1])
    slide.shapes.title.text = "Roadmap"
    slide.placeholders[1].text = "Entrega do trimestre"
    buffer = io.BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()


def _file(item_id: str, name: str, folder: str = "") -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "file": {"mimeType": "application/octet-stream"},
        "cTag": f"ctag-{item_id}",
        "lastModifiedDateTime": "2026-09-01T10:00:00Z",
        "webUrl": f"https://contoso.sharepoint.com/{folder}{name}",
        "parentReference": {"path": f"/drives/d1/root:/{folder}".rstrip("/")},
    }


class FakeGraph:
    """Library: root (2 pages) → Manuais/ → Antigos/, plus an unsupported video."""

    def __init__(self) -> None:
        self.items = {
            "f-manuais": {"id": "f-manuais", "name": "Manuais", "folder": {"childCount": 2}},
            "f-antigos": {"id": "f-antigos", "name": "Antigos", "folder": {"childCount": 1}},
            "planilha": _file("planilha", "Preços.xlsx"),
            "video": _file("video", "demo.mp4"),
            "guia": _file("guia", "Guia.docx", "Manuais/"),
            "deck": _file("deck", "Roadmap 2025.pptx", "Manuais/Antigos/"),
        }
        self.content = {"planilha": _xlsx(), "guia": _docx("Passo a passo detalhado."), "deck": _pptx()}
        self.requests: list[str] = []

    def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        self.requests.append(path)
        pages = {
            f"{DRIVE}/root/children": (["f-manuais", "planilha"], f"{GRAPH}{DRIVE}/root/children?$skiptoken=2"),
            f"{GRAPH}{DRIVE}/root/children?$skiptoken=2": (["video"], None),
            f"{DRIVE}/items/f-manuais/children": (["guia", "f-antigos"], None),
            f"{DRIVE}/items/f-antigos/children": (["deck"], None),
        }
        if path in pages:
            ids, next_link = pages[path]
            payload: dict[str, Any] = {"value": [self.items[i] for i in ids]}
            if next_link:
                payload["@odata.nextLink"] = next_link
            return payload
        if path.startswith(f"{DRIVE}/items/"):
            return self.items[path.rsplit("/", 1)[-1]]
        raise AssertionError(f"endpoint inesperado: {path}")

    def download(self, path: str, **_kwargs: Any) -> bytes:
        return self.content[path.split("/items/")[1].split("/")[0]]

    def close(self) -> None:
        pass


def _connector(graph: FakeGraph) -> tuple[SharePointConnector, SourceConfig]:
    source = SourceConfig(
        id="sp", name="Intranet", source_type="sharepoint_graph", base_url=GRAPH, space_key="site-1"
    )
    connector = SharePointConnector(source, ExtractionOptions(), secret="token", client=graph)  # type: ignore[arg-type]
    return connector, source


def test_listing_walks_subfolders_and_pages_and_skips_unsupported_files() -> None:
    connector, _ = _connector(FakeGraph())

    documents = {doc.id: doc for doc in connector.list_documents("site-1")}

    assert set(documents) == {"planilha", "guia", "deck"}  # demo.mp4 and folders are not documents
    assert documents["deck"].path == ["Manuais", "Antigos", "Roadmap 2025.pptx"]
    assert documents["guia"].etag == "ctag-guia"


def test_office_files_are_converted_and_consolidated(tmp_path: Path) -> None:
    graph = FakeGraph()
    connector, source = _connector(graph)
    metadata = connector.list_documents("site-1")
    project = ProjectConfig(output_dir="base", sources=[source])
    runtime = SourceRuntime(
        source=source,
        root={},
        pages_by_id={},
        selected_page_ids=[f"sp:site-1:{doc.id}" for doc in metadata],
        connector=connector,
        documents_by_container={"site-1": {doc.id: doc for doc in metadata}},
    )

    result = ExtractionService(project, [runtime], tmp_path).run()
    ConsolidationService(project, tmp_path).run()

    assert result["counters"]["new"] == 3
    loose = "\n".join(path.read_text(encoding="utf-8") for path in (tmp_path / "base").rglob("*.md"))
    for expected in ("Passo a passo detalhado.", "Licença anual", "Entrega do trimestre"):
        assert expected in loose
    packages = list((tmp_path / "base" / project.consolidation.output_subdir).glob("*.md"))
    assert packages
    consolidated = "\n".join(path.read_text(encoding="utf-8") for path in packages)
    assert "Passo a passo detalhado." in consolidated and "Entrega do trimestre" in consolidated
