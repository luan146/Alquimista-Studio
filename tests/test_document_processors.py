from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from alquimista.document_processing import (
    EbookProcessor,
    HtmlProcessor,
    ImageProcessor,
    PdfProcessor,
    SpreadsheetProcessor,
    TextProcessor,
    default_processor_registry,
)
from alquimista.errors import DocumentProcessingError
from alquimista.models import KnowledgeDocument


def test_text_processor_plain_and_markdown() -> None:
    proc = TextProcessor()
    assert proc.can_process(file_path="sample.txt")
    assert proc.can_process(file_path="readme.md")
    assert proc.can_process(mime_type="text/markdown")

    # Plain text
    doc = proc.process_bytes(b"Linha 1\nLinha 2", filename="teste.txt")
    assert doc.title == "teste"
    assert "Linha 1" in doc.content
    assert doc.metadata.get("raw_type") == "text"

    # Markdown with H1
    doc_md = proc.process_bytes(b"# Titulo Principal\n\nTexto descritivo.", filename="doc.md")
    assert doc_md.title == "Titulo Principal"
    assert "Texto descritivo." in doc_md.content


def test_html_processor() -> None:
    proc = HtmlProcessor()
    assert proc.can_process(file_path="index.html")
    assert proc.can_process(mime_type="text/html")

    html = b"""
    <html>
      <head><title>Guia de Instalacao</title></head>
      <body>
        <article>
          <h1>Passo a Passo</h1>
          <p>Execute o comando <code>alquimista run</code>.</p>
          <table><tr><th>Item</th><th>Qtd</th></tr><tr><td>Servidor</td><td>1</td></tr></table>
        </article>
      </body>
    </html>
    """
    doc = proc.process_bytes(html, filename="guia.html")
    assert doc.title == "Guia de Instalacao"
    assert "Passo a Passo" in doc.content
    assert "alquimista run" in doc.content
    assert "Servidor" in doc.content


def test_spreadsheet_processor_csv_tsv() -> None:
    proc = SpreadsheetProcessor()
    assert proc.can_process(file_path="dados.csv")
    assert proc.can_process(file_path="tabela.tsv")
    assert proc.can_process(file_path="planilha.xlsx")

    csv_data = b"ID,Nome,Status\n1,Alquimista,Ativo\n2,Studio,Concluido\n"
    doc = proc.process_bytes(csv_data, filename="relatorio.csv")
    assert doc.title == "relatorio"
    assert "Alquimista" in doc.content
    assert "| ID | Nome | Status |" in doc.content


def test_pdf_processor_with_mock_or_pypdf(tmp_path: Path) -> None:
    proc = PdfProcessor()
    assert proc.can_process(file_path="manual.pdf")
    assert proc.can_process(mime_type="application/pdf")

    # A corrupt PDF must fail instead of producing a "successful" error document.
    with pytest.raises(DocumentProcessingError):
        proc.process_bytes(b"%PDF-1.4 dummy", filename="manual.pdf")


def test_image_processor() -> None:
    proc = ImageProcessor()
    assert proc.can_process(file_path="foto.png")
    assert proc.can_process(file_path="foto.jpg")

    # Generate a small 10x10 PNG bytes
    from PIL import Image
    buf = io.BytesIO()
    img = Image.new("RGB", (10, 10), color="blue")
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    doc = proc.process_bytes(png_bytes, filename="diagrama.png")
    assert doc.title == "diagrama"
    assert "10x10" in doc.content
    assert doc.metadata.get("width") == 10
    assert doc.metadata.get("height") == 10


def test_document_processor_registry() -> None:
    registry = default_processor_registry()
    assert ".pdf" in registry.supported_extensions()
    assert ".xlsx" in registry.supported_extensions()
    assert ".docx" in registry.supported_extensions()
    assert ".pptx" in registry.supported_extensions()
    assert ".epub" in registry.supported_extensions()
    assert ".html" in registry.supported_extensions()
    assert ".md" in registry.supported_extensions()
    assert ".png" in registry.supported_extensions()

    doc = registry.process_bytes(b"# Teste de Integracao", filename="nota.md")
    assert isinstance(doc, KnowledgeDocument)
    assert doc.title == "Teste de Integracao"


def test_office_formats_convert_real_files() -> None:
    docx = pytest.importorskip("docx")
    openpyxl = pytest.importorskip("openpyxl")
    pptx = pytest.importorskip("pptx")
    registry = default_processor_registry()

    document = docx.Document()
    document.add_heading("Guia", level=1)
    document.add_paragraph("Conteúdo do guia")
    buffer = io.BytesIO()
    document.save(buffer)
    doc = registry.process_bytes(buffer.getvalue(), filename="guia.docx")
    assert "# Guia" in doc.content and "Conteúdo do guia" in doc.content

    workbook = openpyxl.Workbook()
    workbook.active.append(["ID", "Nome"])
    workbook.active.append([1, "Alquimista"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    doc = registry.process_bytes(buffer.getvalue(), filename="dados.xlsx")
    assert "| ID | Nome |" in doc.content and "Alquimista" in doc.content

    presentation = pptx.Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[1])
    slide.shapes.title.text = "Abertura"
    slide.placeholders[1].text = "Primeiro tópico"
    buffer = io.BytesIO()
    presentation.save(buffer)
    doc = registry.process_bytes(buffer.getvalue(), filename="deck.pptx")
    assert "Abertura" in doc.content and "Primeiro tópico" in doc.content


def _epub_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
            '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
            "</rootfiles></container>",
        )
        archive.writestr(
            "OEBPS/content.opf",
            '<package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/">'
            "<metadata><dc:title>Livro Teste</dc:title><dc:creator>Autora</dc:creator>"
            "<dc:language>pt</dc:language></metadata>"
            '<manifest><item id="c2" href="text/c2.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="c1" href="text/c1.xhtml" media-type="application/xhtml+xml"/></manifest>'
            '<spine><itemref idref="c1"/><itemref idref="c2"/></spine></package>',
        )
        archive.writestr("OEBPS/text/c1.xhtml", "<html><body><h1>Capítulo 1</h1><p>Início</p></body></html>")
        archive.writestr("OEBPS/text/c2.xhtml", "<html><body><h1>Capítulo 2</h1><p>Fim</p></body></html>")
    return buffer.getvalue()


def test_epub_processor_follows_spine_order() -> None:
    doc = EbookProcessor().process_bytes(_epub_bytes(), filename="livro.epub")
    assert doc.title == "Livro Teste"
    assert doc.metadata["author"] == "Autora"
    assert doc.content.index("Capítulo 1") < doc.content.index("Capítulo 2")

    with pytest.raises(DocumentProcessingError):
        EbookProcessor().process_bytes(b"not a zip", filename="ruim.epub")


def test_unsupported_formats_fail_instead_of_emitting_garbage(tmp_path: Path) -> None:
    registry = default_processor_registry()
    for ext in (".doc", ".odt", ".xls", ".ods", ".ppt", ".odp"):
        assert ext not in registry.supported_extensions()
    with pytest.raises(DocumentProcessingError):
        registry.process_bytes(b"OLE2 binary", filename="antigo.doc")
    legacy = tmp_path / "planilha.xls"
    legacy.write_bytes(b"OLE2 binary")
    with pytest.raises(DocumentProcessingError):
        registry.process_file(legacy)
