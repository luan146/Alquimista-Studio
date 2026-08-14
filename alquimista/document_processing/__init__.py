"""Universal document processing subsystem for ALQuimista Studio."""

from .base import DocumentProcessor
from .ebook import EbookProcessor
from .html import HtmlProcessor
from .image import ImageProcessor
from .pdf import PdfProcessor
from .presentation import PresentationProcessor
from .registry import (
    DocumentProcessorRegistry,
    default_processor_registry,
    get_global_processor_registry,
)
from .spreadsheet import SpreadsheetProcessor
from .text import TextProcessor
from .word import WordProcessor

__all__ = [
    "DocumentProcessor",
    "DocumentProcessorRegistry",
    "EbookProcessor",
    "HtmlProcessor",
    "ImageProcessor",
    "PdfProcessor",
    "PresentationProcessor",
    "SpreadsheetProcessor",
    "TextProcessor",
    "WordProcessor",
    "default_processor_registry",
    "get_global_processor_registry",
]
