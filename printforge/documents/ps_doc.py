"""PostScript document handler — PS, EPS.

Converts PostScript files to PDF using Ghostscript (gs),
then renders pages with vector precision via Poppler.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from typing import Optional

import cairo

from printforge.documents.base import Document
from printforge.documents.pdf_doc import PdfDocument

log = logging.getLogger(__name__)


class PostScriptDocument(Document):
    """Handles PostScript (.ps, .eps) documents via Ghostscript."""

    def __init__(self, filepath: str) -> None:
        super().__init__(filepath)
        self._pdf_doc: Optional[PdfDocument] = None
        self._temp_pdf_path: Optional[str] = None

    @property
    def page_count(self) -> int:
        if self._pdf_doc and self._pdf_doc.is_valid:
            return self._pdf_doc.page_count
        return 0

    @property
    def dimensions(self) -> tuple[float, float]:
        if self._pdf_doc and self._pdf_doc.is_valid:
            return self._pdf_doc.dimensions
        return (595.0, 842.0)  # Default A4

    @property
    def pdf_path(self) -> Optional[str]:
        """Path to the converted PDF file."""
        return self._temp_pdf_path

    def load(self) -> bool:
        """Convert PostScript to PDF and load with Poppler."""
        gs_bin = shutil.which("gs")
        if not gs_bin:
            self._error = "Ghostscript (gs) is required to open PostScript files. Please install ghostscript."
            log.error(self._error)
            return False

        if not os.path.isfile(self._filepath):
            self._error = f"File not found: {self._filepath}"
            return False

        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, prefix="printforge_ps_")
            self._temp_pdf_path = tmp.name
            tmp.close()

            cmd = [
                gs_bin,
                "-sDEVICE=pdfwrite",
                "-dSAFER",
                "-dBATCH",
                "-dNOPAUSE",
                f"-sOutputFile={self._temp_pdf_path}",
                self._filepath,
            ]
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=20,
            )

            if result.returncode != 0:
                self._error = f"Ghostscript conversion failed: {result.stderr.decode('utf-8', errors='replace')}"
                log.error("%s: %s", self._error, self._filepath)
                self._cleanup_temp()
                return False

            self._pdf_doc = PdfDocument(self._temp_pdf_path)
            if not self._pdf_doc.load():
                self._error = f"Failed to load converted PostScript PDF: {self._pdf_doc.error}"
                self._cleanup_temp()
                return False

            self._valid = True
            return True

        except subprocess.TimeoutExpired:
            self._error = "PostScript conversion timed out"
            log.error("%s: %s", self._error, self._filepath)
            self._cleanup_temp()
            return False
        except Exception as e:
            self._error = f"Failed to process PostScript file: {e}"
            log.error("%s: %s", self._error, self._filepath)
            self._cleanup_temp()
            return False

    def render_page(
        self, page_num: int, width: float, height: float
    ) -> Optional[cairo.ImageSurface]:
        if self._pdf_doc and self._pdf_doc.is_valid:
            return self._pdf_doc.render_page(page_num, width, height)
        return None

    def _cleanup_temp(self) -> None:
        if self._temp_pdf_path and os.path.exists(self._temp_pdf_path):
            try:
                os.remove(self._temp_pdf_path)
            except OSError:
                pass
            self._temp_pdf_path = None

    def close(self) -> None:
        if self._pdf_doc:
            self._pdf_doc.close()
            self._pdf_doc = None
        self._cleanup_temp()

    def __del__(self) -> None:
        self.close()
