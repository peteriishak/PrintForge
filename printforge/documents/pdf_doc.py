"""PDF document handler using Poppler-GLib."""

from __future__ import annotations

import logging
from typing import Optional
from pathlib import Path

import cairo

from printforge.documents.base import Document

log = logging.getLogger(__name__)


class PdfDocument(Document):
    """Handles PDF files using Poppler-GLib (gi.repository.Poppler)."""

    def __init__(self, filepath: str) -> None:
        super().__init__(filepath)
        self._doc = None
        self._page_count: int = 0
        self._page_sizes: list[tuple[float, float]] = []

    @property
    def page_count(self) -> int:
        return self._page_count

    @property
    def dimensions(self) -> tuple[float, float]:
        """Dimensions of the first page in points."""
        if self._page_sizes:
            return self._page_sizes[0]
        return (595.0, 842.0)  # A4 default

    def get_page_size(self, page_num: int) -> tuple[float, float]:
        """Get the size of a specific page in points."""
        if 0 <= page_num < len(self._page_sizes):
            return self._page_sizes[page_num]
        return self.dimensions

    def load(self) -> bool:
        try:
            import gi
            gi.require_version("Poppler", "0.18")
            from gi.repository import Poppler

            uri = Path(self._filepath).as_uri()
            self._doc = Poppler.Document.new_from_file(uri, None)
            self._page_count = self._doc.get_n_pages()

            # Cache page sizes
            self._page_sizes = []
            for i in range(self._page_count):
                page = self._doc.get_page(i)
                w, h = page.get_size()
                self._page_sizes.append((w, h))

            self._valid = True
            return True

        except ImportError:
            self._error = (
                "Poppler GI bindings not available. "
                "Install poppler-glib and gir1.2-poppler-0.18."
            )
            log.error(self._error)
            return False
        except Exception as e:
            self._error = f"Failed to load PDF: {e}"
            log.error("%s: %s", self._error, self._filepath)
            return False

    def render_page(
        self, page_num: int, width: float, height: float
    ) -> Optional[cairo.ImageSurface]:
        if not self._valid or self._doc is None:
            return None

        if page_num < 0 or page_num >= self._page_count:
            return None

        try:
            page = self._doc.get_page(page_num)
            page_w, page_h = page.get_size()

            target_w = max(1, int(width))
            target_h = max(1, int(height))

            # Create surface
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, target_w, target_h)
            ctx = cairo.Context(surface)

            # White background
            ctx.set_source_rgb(1.0, 1.0, 1.0)
            ctx.rectangle(0, 0, target_w, target_h)
            ctx.fill()

            # Scale to fit
            scale_x = target_w / page_w
            scale_y = target_h / page_h
            scale = min(scale_x, scale_y)

            # Center the page
            offset_x = (target_w - page_w * scale) / 2
            offset_y = (target_h - page_h * scale) / 2

            ctx.translate(offset_x, offset_y)
            ctx.scale(scale, scale)

            # Render
            page.render(ctx)

            return surface

        except Exception as e:
            log.error("Failed to render PDF page %d: %s", page_num, e)
            return None

    def close(self) -> None:
        """Release the Poppler document."""
        self._doc = None
