"""Output that stands on its own for AI tools (NotebookLM, Claude/ChatGPT projects)."""
from __future__ import annotations

import base64
import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from alquimista import image_text
from alquimista.errors import ExtractionCancelledError, PermissionDeniedError
from alquimista.markdown import KnowledgeDocumentRenderer, images_as_text
from alquimista.models import KnowledgeDocument, MarkdownOptions, ProjectConfig, SourceConfig
from alquimista.services import ExtractionService, SourceRuntime

FIND_TESSERACT = image_text.tesseract_path  # the real lookup; conftest hides it during tests
INSTALLED_TESSERACT = FIND_TESSERACT()


def test_images_become_text_without_authenticated_urls() -> None:
    markdown = (
        "Antes ![Fluxo de aprovação](https://wiki.example.com/download/attachments/1/fluxo.png?api=v2) depois\n"
        "![](https://wiki.example.com/download/attachments/1/tela%20inicial.png)\n"
        '[![logo](https://x.com/a.svg)](https://x.com)\n'
        '<img src="https://x.com/b/diagrama.jpg" alt="">'
    )

    text = images_as_text(markdown)

    assert "Antes [Imagem: Fluxo de aprovação] depois" in text
    assert "[Imagem: tela inicial.png]" in text
    assert "[Imagem: logo]" in text
    assert "[Imagem: diagrama.jpg]" in text
    assert "http" not in text


def test_image_reader_adds_the_text_found_in_the_image() -> None:
    read = {"https://x.com/fluxo.png": "Passo 1\n  Passo   2"}.get

    text = images_as_text("![Fluxo](https://x.com/fluxo.png) ![Outra](https://x.com/vazia.png)", read)

    assert text == "[Imagem: Fluxo — texto na imagem: Passo 1 Passo 2] [Imagem: Outra]"


def test_renderer_applies_the_option_and_new_projects_have_it_on() -> None:
    document = KnowledgeDocument(
        id="1", container_id="C", title="Página", content="![Mapa](https://x.com/mapa.png)", source_type="generic_web"
    )
    source = SourceConfig(id="s1", name="Fonte")

    assert ProjectConfig().markdown.images_as_text is True
    on = KnowledgeDocumentRenderer(MarkdownOptions()).prepare(document, source)
    off = KnowledgeDocumentRenderer(MarkdownOptions(images_as_text=False)).prepare(document, source)

    assert on.content == "[Imagem: Mapa]"
    assert off.content == "![Mapa](https://x.com/mapa.png)"


def test_existing_projects_keep_their_images_and_their_format_signature() -> None:
    old = ProjectConfig.from_dict({"schema_version": 4, "markdown": {"include_images": True}})

    assert old.markdown.images_as_text is False
    # Format hash of the default options before these fields existed (old goldens/hashes.json).
    assert old.markdown.signature() == "f0b69e912bfbbef1f494c0397bdb3661bcc30df03e5157cf02c944955e06ad90"


# --- Text inside images (Tesseract) -------------------------------------------------


class _Client:
    def __init__(self, fail: Exception | None = None) -> None:
        self.calls: list[str] = []
        self.fail = fail

    def download(self, url: str) -> bytes:
        self.calls.append(url)
        if self.fail:
            raise self.fail
        return b"png:" + url.encode()


@pytest.fixture
def fake_tesseract(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[bytes]:
    read: list[bytes] = []
    monkeypatch.setattr(image_text, "tesseract_path", lambda: tmp_path / "tesseract.exe")

    def fake_read(_executable: Path, data: bytes) -> str:
        read.append(data)
        return "texto de " + data.decode(errors="replace")

    monkeypatch.setattr(image_text, "read_text", fake_read)
    return read


def test_reader_downloads_with_the_source_access_and_reads_each_image_once(fake_tesseract: list[bytes]) -> None:
    client = _Client()
    read = image_text.image_text_reader(SimpleNamespace(client=client))
    assert read is not None

    assert read("https://wiki/logo.png") == "texto de png:https://wiki/logo.png"
    read("https://wiki/logo.png")
    assert client.calls == ["https://wiki/logo.png"]
    assert read("data:image/png;base64," + base64.b64encode(b"embutida").decode()) == "texto de embutida"
    assert read("imagens/relativa.png") == ""


def test_unreadable_image_keeps_only_the_description(fake_tesseract: list[bytes]) -> None:
    read = image_text.image_text_reader(SimpleNamespace(client=_Client(PermissionDeniedError("403"))))
    assert read is not None

    assert images_as_text("![Tela](https://wiki/t.png)", read) == "[Imagem: Tela]"


def test_cancelling_while_reading_images_stops_the_extraction(fake_tesseract: list[bytes]) -> None:
    read = image_text.image_text_reader(SimpleNamespace(client=_Client(ExtractionCancelledError("cancelado"))))
    assert read is not None

    with pytest.raises(ExtractionCancelledError):
        read("https://wiki/t.png")


def test_without_tesseract_there_is_no_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(image_text, "tesseract_path", lambda: None)
    assert image_text.image_text_reader(SimpleNamespace()) is None


def test_tesseract_can_be_pointed_to_by_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    executable = tmp_path / "tesseract.exe"
    executable.write_bytes(b"")
    monkeypatch.setenv("ALQUIMISTA_TESSERACT", str(executable))
    assert FIND_TESSERACT() == executable


class _ImageConnector:
    client = _Client()

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        return KnowledgeDocument(
            id=document_id, container_id="C", title="Fluxo", source_type="generic",
            content="Veja ![Fluxo](https://docs.example.com/fluxo.png)",
        )

    def close(self) -> None:
        pass


def _extract(tmp_path: Path, markdown: MarkdownOptions) -> str:
    source = SourceConfig(id="s", name="Fonte", source_type="generic", base_url="https://docs.example.com")
    project = ProjectConfig(output_dir="base", sources=[source], markdown=markdown)
    runtime = SourceRuntime(
        source=source, root={}, pages_by_id={}, selected_page_ids=["s:C:d1"], connector=_ImageConnector()
    )
    ExtractionService(project, [runtime], tmp_path).run()
    return next((tmp_path / "base").rglob("Fluxo*.md")).read_text(encoding="utf-8")


def test_extraction_writes_the_text_read_in_images(fake_tesseract: list[bytes], tmp_path: Path) -> None:
    output = _extract(tmp_path, MarkdownOptions())

    assert "[Imagem: Fluxo — texto na imagem: texto de png:https://docs.example.com/fluxo.png]" in output


def test_reading_image_text_can_be_turned_off(fake_tesseract: list[bytes], tmp_path: Path) -> None:
    output = _extract(tmp_path, MarkdownOptions(read_image_text=False))

    assert "Veja [Imagem: Fluxo]" in output
    assert fake_tesseract == []


@pytest.mark.skipif(INSTALLED_TESSERACT is None, reason="Tesseract não instalado")
def test_real_tesseract_reads_printed_text() -> None:
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (900, 160), "white")
    ImageDraw.Draw(image).text((20, 40), "ALQUIMISTA 2026", fill="black", font=ImageFont.load_default(size=64))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    assert INSTALLED_TESSERACT is not None
    assert "ALQUIMISTA" in image_text.read_text(INSTALLED_TESSERACT, buffer.getvalue())
