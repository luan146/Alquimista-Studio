from __future__ import annotations

import io
from pathlib import Path

from alquimista.document_processing import (
    HtmlProcessor,
    ImageProcessor,
    PdfProcessor,
    SpreadsheetProcessor,
    TextProcessor,
    default_processor_registry,
)
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

    # Process empty or fallback bytes
    doc = proc.process_bytes(b"%PDF-1.4 dummy", filename="manual.pdf")
    assert doc.title == "manual"
    assert doc.id


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
