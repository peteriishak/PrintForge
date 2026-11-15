"""Base document abstraction for all supported file types."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import cairo


# Supported file extensions mapped to document type
SUPPORTED_EXTENSIONS: dict[str, str] = {
    # ── Standard & Extended Images ──
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".jpe": "image",
    ".jfif": "image",
    ".webp": "image",
    ".bmp": "image",
    ".dib": "image",
    ".tiff": "image",
    ".tif": "image",
    ".gif": "image",
    ".ico": "image",
    ".cur": "image",
    ".icns": "image",
    ".tga": "image",
    ".ppm": "image",
    ".pgm": "image",
    ".pbm": "image",
    ".pnm": "image",
    ".pcx": "image",
    ".psd": "image",
    ".xbm": "image",
    ".xpm": "image",
    ".dds": "image",
    ".apng": "image",
    ".jp2": "image",
    ".j2k": "image",

    # ── Scalable Vector Graphics ──
    ".svg": "svg",
    ".svgz": "svg",

    # ── PDF Documents ──
    ".pdf": "pdf",

    # ── PostScript / EPS ──
    ".ps": "postscript",
    ".eps": "postscript",

    # ── Office & Rich Text Documents ──
    ".odt": "office",
    ".docx": "office",
    ".doc": "office",
    ".rtf": "office",
    ".ods": "office",
    ".xlsx": "office",
    ".xls": "office",
    ".odp": "office",
    ".pptx": "office",
    ".ppt": "office",

    # ── Text, Markdown, Code & Structured Data ──
    ".txt": "text",
    ".log": "text",
    ".md": "text",
    ".markdown": "text",
    ".py": "text",
    ".sh": "text",
    ".bash": "text",
    ".zsh": "text",
    ".c": "text",
    ".h": "text",
    ".cpp": "text",
    ".hpp": "text",
    ".cc": "text",
    ".cxx": "text",
    ".rs": "text",
    ".go": "text",
    ".js": "text",
    ".ts": "text",
    ".jsx": "text",
    ".tsx": "text",
    ".html": "text",
    ".htm": "text",
    ".css": "text",
    ".sql": "text",
    ".json": "text",
    ".yaml": "text",
    ".yml": "text",
    ".toml": "text",
    ".xml": "text",
    ".ini": "text",
    ".conf": "text",
    ".cfg": "text",
    ".csv": "text",
    ".tsv": "text",
    ".diff": "text",
    ".patch": "text",
}

IMAGE_EXTENSIONS = {k for k, v in SUPPORTED_EXTENSIONS.items() if v == "image"}


def is_supported(filepath: str) -> bool:
    """Check if a file extension is supported."""
    ext = Path(filepath).suffix.lower()
    return ext in SUPPORTED_EXTENSIONS


def get_file_type(filepath: str) -> Optional[str]:
    """Return the document type for a file, or None if unsupported."""
    ext = Path(filepath).suffix.lower()
    return SUPPORTED_EXTENSIONS.get(ext)


class Document(ABC):
    """Abstract base class for all document types.

    Subclasses must implement methods for rendering pages to Cairo surfaces.
    """

    def __init__(self, filepath: str) -> None:
        self._filepath = os.path.abspath(filepath)
        self._valid = False
        self._error: str = ""

    @property
    def filepath(self) -> str:
        return self._filepath

    @property
    def filename(self) -> str:
        return os.path.basename(self._filepath)

    @property
    def file_size(self) -> int:
        """File size in bytes."""
        try:
            return os.path.getsize(self._filepath)
        except OSError:
            return 0

    @property
    def file_type(self) -> str:
        """Return the type string (image, pdf, text, svg)."""
        return get_file_type(self._filepath) or "unknown"

    @property
    def is_image(self) -> bool:
        return self.file_type in ("image", "svg")

    @property
    def is_valid(self) -> bool:
        return self._valid

    @property
    def error(self) -> str:
        return self._error

    @property
    @abstractmethod
    def page_count(self) -> int:
        """Total number of pages."""
        ...

    @property
    @abstractmethod
    def dimensions(self) -> tuple[float, float]:
        """Width and height in pixels (for images) or points (for PDFs)."""
        ...

    @abstractmethod
    def render_page(
        self, page_num: int, width: float, height: float
    ) -> Optional[cairo.ImageSurface]:
        """Render a page to a Cairo ImageSurface at the given dimensions.

        Args:
            page_num: 0-indexed page number.
            width: Target width in pixels.
            height: Target height in pixels.

        Returns:
            Cairo ImageSurface, or None on failure.
        """
        ...

    @abstractmethod
    def load(self) -> bool:
        """Load and validate the file.

        Sets self._valid and self._error.
        Returns True on success.
        """
        ...


class DocumentFactory:
    """Creates the appropriate Document subclass for a file."""

    @staticmethod
    def create(filepath: str) -> Optional[Document]:
        """Create a Document for the given file path.

        Returns None if the file type is unsupported.
        """
        file_type = get_file_type(filepath)
        if file_type is None:
            return None

        if file_type == "image":
            from printforge.documents.image_doc import ImageDocument
            doc = ImageDocument(filepath)
        elif file_type == "pdf":
            from printforge.documents.pdf_doc import PdfDocument
            doc = PdfDocument(filepath)
        elif file_type == "office":
            from printforge.documents.office_doc import OfficeDocument
            doc = OfficeDocument(filepath)
        elif file_type == "postscript":
            from printforge.documents.ps_doc import PostScriptDocument
            doc = PostScriptDocument(filepath)
        elif file_type == "text":
            from printforge.documents.text_doc import TextDocument
            doc = TextDocument(filepath)
        elif file_type == "svg":
            from printforge.documents.svg_doc import SvgDocument
            doc = SvgDocument(filepath)
        else:
            return None

        doc.load()
        return doc
