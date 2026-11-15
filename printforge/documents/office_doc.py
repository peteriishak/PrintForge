"""Office document handler — ODT, DOCX, DOC, RTF, ODS, XLSX, ODP, PPTX.

Converts office documents on the fly to PDF using LibreOffice in headless mode,
then renders pages with vector and typographic fidelity via Poppler.
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


class OfficeDocument(Document):
    """Handles office documents (.odt, .docx, .rtf, .ods, .xlsx, .odp, .pptx)."""

    def __init__(self, filepath: str) -> None:
        super().__init__(filepath)
        self._pdf_doc: Optional[PdfDocument] = None
        self._temp_dir: Optional[str] = None
        self._converted_pdf_path: Optional[str] = None

    @property
    def page_count(self) -> int:
        if self._pdf_doc and self._pdf_doc.is_valid:
            return self._pdf_doc.page_count
        return 0

    @property
    def dimensions(self) -> tuple[float, float]:
        if self._pdf_doc and self._pdf_doc.is_valid:
            return self._pdf_doc.dimensions
        return (595.0, 842.0)  # Default A4 in points

    @property
    def pdf_path(self) -> Optional[str]:
        """Path to the converted PDF file."""
        return self._converted_pdf_path

    def load(self) -> bool:
        """Convert office document to PDF and load with Poppler."""
        lo_bin = shutil.which("libreoffice") or shutil.which("soffice")
        if not lo_bin:
            self._error = "LibreOffice is required to open office documents. Please install libreoffice."
            log.error(self._error)
            return False

        if not os.path.isfile(self._filepath):
            self._error = f"File not found: {self._filepath}"
            return False

        try:
            self._temp_dir = tempfile.mkdtemp(prefix="printforge_office_")
            cmd = [
                lo_bin,
                "--headless",
                "--convert-to", "pdf",
                "--outdir", self._temp_dir,
                self._filepath,
            ]
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )

            if result.returncode != 0:
                self._error = f"LibreOffice conversion failed: {result.stderr.decode('utf-8', errors='replace')}"
                log.error("%s: %s", self._error, self._filepath)
                self._cleanup_temp()
                return False

            # Find generated PDF
            base_name = os.path.splitext(os.path.basename(self._filepath))[0]
            expected_pdf = os.path.join(self._temp_dir, f"{base_name}.pdf")

            if not os.path.exists(expected_pdf):
                # Search temp dir for any .pdf generated
                candidates = [
                    os.path.join(self._temp_dir, f)
                    for f in os.listdir(self._temp_dir)
                    if f.lower().endswith(".pdf")
                ]
                if candidates:
                    expected_pdf = candidates[0]
                else:
                    self._error = "No PDF was generated from office document"
                    self._cleanup_temp()
                    return False

            self._converted_pdf_path = expected_pdf
            self._pdf_doc = PdfDocument(self._converted_pdf_path)
            if not self._pdf_doc.load():
                self._error = f"Failed to load converted PDF: {self._pdf_doc.error}"
                self._cleanup_temp()
                return False

            self._valid = True
            return True

        except subprocess.TimeoutExpired:
            self._error = "Document conversion timed out"
            log.error("%s: %s", self._error, self._filepath)
            self._cleanup_temp()
            return False
        except Exception as e:
            self._error = f"Failed to process office document: {e}"
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
        if self._temp_dir and os.path.exists(self._temp_dir):
            try:
                shutil.rmtree(self._temp_dir)
            except OSError:
                pass
            self._temp_dir = None
            self._converted_pdf_path = None

    def close(self) -> None:
        if self._pdf_doc:
            self._pdf_doc.close()
            self._pdf_doc = None
        self._cleanup_temp()

    def __del__(self) -> None:
        self.close()
