"""Print file preparation — converts documents to print-ready format for CUPS.

Uses LayoutEngine for all layout calculations, ensuring the print output
matches the preview exactly.
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Optional

import cairo

from printforge.config.print_settings import (
    PrintSettings,
)
from printforge.documents.base import Document
from printforge.documents.layout_engine import LayoutEngine

log = logging.getLogger(__name__)


class PrintPreparer:
    """Converts documents into print-ready PDF files for CUPS submission.

    Uses the same LayoutEngine as the preview renderer, so the
    printed output matches what the user sees in the preview.
    """

    def __init__(self) -> None:
        self._temp_files: list[str] = []
        self._engine = LayoutEngine()

    def prepare(
        self, document: Document, settings: PrintSettings
    ) -> Optional[str]:
        """Prepare a document for printing.

        Returns the path to a temporary PDF file ready for CUPS,
        or None on failure.
        """
        if not document or not document.is_valid:
            return None

        try:
            if document.file_type in ("pdf", "office", "postscript"):
                return self._prepare_pdf(document, settings)
            elif document.file_type in ("image", "svg"):
                return self._prepare_image(document, settings)
            elif document.file_type == "text":
                return self._prepare_text(document, settings)
            else:
                log.warning("Unsupported document type: %s", document.file_type)
                return None
        except Exception as e:
            log.error("Failed to prepare document: %s", e)
            return None

    def prepare_to_file(
        self, document: Document, settings: PrintSettings, output_path: str,
    ) -> bool:
        """Prepare a document and save to a specific file path (for export/test).

        Uses exactly the same layout engine as actual printing.
        """
        if not document or not document.is_valid:
            return False

        try:
            if document.file_type in ("image", "svg"):
                return self._prepare_image_to_path(document, settings, output_path)
            elif document.file_type in ("pdf", "office", "postscript"):
                return self._prepare_pdf_to_path(document, settings, output_path)
            elif document.file_type == "text":
                return self._prepare_text_to_path(document, settings, output_path)
            return False
        except Exception as e:
            log.error("Failed to export document: %s", e)
            return False

    def _prepare_pdf(self, document: Document, settings: PrintSettings) -> Optional[str]:
        """Prepare a PDF, Office, or PostScript document for printing."""
        pages = self._get_page_list(document, settings)
        if pages is None:
            return None

        # If printing all pages, use the ready-to-print PDF file
        if len(pages) == document.page_count and pages == list(range(document.page_count)):
            if document.file_type == "pdf":
                return document.filepath
            elif hasattr(document, "pdf_path") and document.pdf_path:
                import shutil
                tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, prefix="printforge_")
                tmp.close()
                self._temp_files.append(tmp.name)
                shutil.copy2(document.pdf_path, tmp.name)
                return tmp.name

        # Create a new PDF with only selected pages
        paper = self._engine.get_paper_size(settings)
        page_w_pt = paper.width_pt
        page_h_pt = paper.height_pt

        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, prefix="printforge_")
        tmp.close()
        self._temp_files.append(tmp.name)

        surface = cairo.PDFSurface(tmp.name, page_w_pt, page_h_pt)
        ctx = cairo.Context(surface)

        dpi = settings.get_dpi()
        render_scale = max(2.0, min(8.0, dpi / 72.0))

        for page_idx in pages:
            page_surface = document.render_page(
                page_idx, int(page_w_pt * render_scale), int(page_h_pt * render_scale)
            )
            if page_surface:
                sw = page_surface.get_width()
                sh = page_surface.get_height()
                if sw > 0 and sh > 0:
                    ctx.save()
                    ctx.scale(page_w_pt / sw, page_h_pt / sh)
                    ctx.set_source_surface(page_surface, 0, 0)
                    ctx.paint()
                    ctx.restore()
            surface.show_page()

        surface.finish()
        return tmp.name

    def _prepare_image(self, document: Document, settings: PrintSettings) -> Optional[str]:
        """Prepare an image for printing using LayoutEngine."""
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, prefix="printforge_")
        tmp.close()
        self._temp_files.append(tmp.name)

        if self._prepare_image_to_path(document, settings, tmp.name):
            return tmp.name
        return None

    def _prepare_image_to_path(
        self, document: Document, settings: PrintSettings, output_path: str,
    ) -> bool:
        """Render image to PDF at the given path using LayoutEngine."""
        paper = self._engine.get_paper_size(settings)
        page_w_pt = paper.width_pt
        page_h_pt = paper.height_pt

        doc_w, doc_h = document.dimensions
        if doc_w <= 0 or doc_h <= 0:
            return False

        # Use the SAME layout engine as preview
        layout = self._engine.calculate_for_print(
            doc_w, doc_h, settings, is_image=document.is_image,
        )

        pa = layout.printable_area
        content = layout.content

        if content.width <= 0 or content.height <= 0:
            return False

        surface = cairo.PDFSurface(output_path, page_w_pt, page_h_pt)
        ctx = cairo.Context(surface)

        # Render image at requested DPI resolution for printing (300, 600, 1200 DPI)
        dpi = settings.get_dpi()
        render_scale = max(1.0, dpi / 72.0)
        # Cap to Cairo image surface memory limit (16384 px)
        max_dim = 16384.0
        if content.width * render_scale > max_dim or content.height * render_scale > max_dim:
            render_scale = min(max_dim / content.width, max_dim / content.height)

        img_surface = document.render_page(
            0, int(content.width * render_scale), int(content.height * render_scale)
        )

        if img_surface:
            ctx.save()
            ctx.translate(content.x, content.y)
            ctx.scale(1.0 / render_scale, 1.0 / render_scale)
            ctx.set_source_surface(img_surface, 0, 0)
            ctx.paint()
            ctx.restore()

        surface.show_page()
        surface.finish()
        return True

    def _prepare_text(self, document: Document, settings: PrintSettings) -> Optional[str]:
        """Prepare a text document — render all pages to PDF."""
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, prefix="printforge_")
        tmp.close()
        self._temp_files.append(tmp.name)

        if self._prepare_text_to_path(document, settings, tmp.name):
            return tmp.name
        return None

    def _prepare_text_to_path(
        self, document: Document, settings: PrintSettings, output_path: str,
    ) -> bool:
        """Render text to PDF at the given path with resolution matching settings."""
        paper = self._engine.get_paper_size(settings)
        page_w_pt = paper.width_pt
        page_h_pt = paper.height_pt

        # Paginate for the selected paper and scale
        self._engine.sync_document(document, settings)

        pages = self._get_page_list(document, settings)
        if pages is None:
            return False

        surface = cairo.PDFSurface(output_path, page_w_pt, page_h_pt)
        ctx = cairo.Context(surface)

        dpi = settings.get_dpi()
        render_scale = max(2.0, min(8.0, dpi / 72.0))

        for page_idx in pages:
            page_surface = document.render_page(
                page_idx, int(page_w_pt * render_scale), int(page_h_pt * render_scale)
            )
            if page_surface:
                ctx.save()
                ctx.scale(1.0 / render_scale, 1.0 / render_scale)
                ctx.set_source_surface(page_surface, 0, 0)
                ctx.paint()
                ctx.restore()
            surface.show_page()

        surface.finish()
        return True

    def _prepare_pdf_to_path(
        self, document: Document, settings: PrintSettings, output_path: str,
    ) -> bool:
        """Export a PDF to the given path with resolution matching settings."""
        pages = self._get_page_list(document, settings)
        if pages is None:
            return False

        paper = self._engine.get_paper_size(settings)
        page_w_pt = paper.width_pt
        page_h_pt = paper.height_pt

        surface = cairo.PDFSurface(output_path, page_w_pt, page_h_pt)
        ctx = cairo.Context(surface)

        dpi = settings.get_dpi()
        render_scale = max(2.0, min(8.0, dpi / 72.0))

        for page_idx in pages:
            page_surface = document.render_page(
                page_idx, int(page_w_pt * render_scale), int(page_h_pt * render_scale)
            )
            if page_surface:
                sw = page_surface.get_width()
                sh = page_surface.get_height()
                if sw > 0 and sh > 0:
                    ctx.save()
                    ctx.scale(page_w_pt / sw, page_h_pt / sh)
                    ctx.set_source_surface(page_surface, 0, 0)
                    ctx.paint()
                    ctx.restore()
            surface.show_page()

        surface.finish()
        return True

    def _get_page_list(self, document: Document, settings: PrintSettings) -> Optional[list[int]]:
        """Get the list of 0-indexed page numbers to print."""
        return self._engine.get_page_indices(document.page_count, settings)

    def cleanup(self) -> None:
        """Remove all temporary files created during preparation."""
        for path in self._temp_files:
            try:
                if os.path.exists(path):
                    os.unlink(path)
            except OSError:
                pass
        self._temp_files.clear()
