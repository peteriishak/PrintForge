"""Layout renderer — produces preview surfaces using the unified LayoutEngine.

All layout calculations are delegated to LayoutEngine so that
preview and print output are guaranteed to match.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

import cairo

from printforge.config.print_settings import (
    PrintSettings, ScalingMode, Position, Orientation, ImageFit, CropMode,
)
from printforge.documents.base import Document
from printforge.documents.layout_engine import LayoutEngine, LayoutResult, NupLayout, PageCount
from printforge.utils.paper import get_paper_by_name, DEFAULT_PAPER, PaperSize

log = logging.getLogger(__name__)

# Paper shadow/decoration constants
PAPER_SHADOW_OFFSET = 3
PAPER_BORDER_COLOR = (0.75, 0.75, 0.75)
PAPER_BG_COLOR = (1.0, 1.0, 1.0)
DESK_BG_COLOR = (0.92, 0.92, 0.92)
MARGIN_GUIDE_COLOR = (0.85, 0.85, 0.95, 0.6)


class LayoutRenderer:
    """Renders a document preview showing how it will appear on the selected paper.

    Uses LayoutEngine for all position/scaling calculations, ensuring
    the preview matches the actual print output exactly.
    """

    def __init__(self) -> None:
        self._engine = LayoutEngine()
        self._cache: dict[str, cairo.ImageSurface] = {}

    def invalidate_cache(self) -> None:
        """Clear all cached surfaces."""
        self._cache.clear()

    def get_paper_size(self, settings: PrintSettings) -> PaperSize:
        """Resolve the effective paper size from settings."""
        return self._engine.get_paper_size(settings)

    def render_preview(
        self,
        document: Optional[Document],
        settings: PrintSettings,
        page_num: int,
        available_width: float,
        available_height: float,
    ) -> Optional[cairo.ImageSurface]:
        """Render a preview of the given page.

        Args:
            document: The document to preview (can be None for empty preview).
            settings: Current print settings.
            page_num: 0-indexed page number.
            available_width: Available widget width in pixels.
            available_height: Available widget height in pixels.

        Returns:
            Cairo ImageSurface showing the paper with content.
        """
        paper = self._engine.get_paper_size(settings)
        padding = 24  # Pixels of padding around the paper

        # Calculate paper dimensions in pixels to fit the available space
        paper_aspect = paper.width_mm / paper.height_mm if paper.height_mm > 0 else 1.0
        avail_w = available_width - padding * 2
        avail_h = available_height - padding * 2

        if avail_w <= 0 or avail_h <= 0:
            return None

        if avail_w / avail_h > paper_aspect:
            # Height-constrained
            paper_h_px = avail_h
            paper_w_px = paper_h_px * paper_aspect
        else:
            # Width-constrained
            paper_w_px = avail_w
            paper_h_px = paper_w_px / paper_aspect

        paper_w_px = max(1, int(paper_w_px))
        paper_h_px = max(1, int(paper_h_px))

        total_w = int(available_width)
        total_h = int(available_height)

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, total_w, total_h)
        ctx = cairo.Context(surface)

        # ── Background (desk) ─────────────────────────────────────────
        ctx.set_source_rgb(*DESK_BG_COLOR)
        ctx.rectangle(0, 0, total_w, total_h)
        ctx.fill()

        # Paper position (centered)
        paper_x = (total_w - paper_w_px) / 2
        paper_y = (total_h - paper_h_px) / 2

        # ── Paper shadow ──────────────────────────────────────────────
        ctx.set_source_rgba(0.0, 0.0, 0.0, 0.15)
        ctx.rectangle(
            paper_x + PAPER_SHADOW_OFFSET,
            paper_y + PAPER_SHADOW_OFFSET,
            paper_w_px, paper_h_px,
        )
        ctx.fill()

        # ── Paper ─────────────────────────────────────────────────────
        ctx.set_source_rgb(*PAPER_BG_COLOR)
        ctx.rectangle(paper_x, paper_y, paper_w_px, paper_h_px)
        ctx.fill()

        # ── Paper border ──────────────────────────────────────────────
        ctx.set_source_rgb(*PAPER_BORDER_COLOR)
        ctx.set_line_width(0.5)
        ctx.rectangle(paper_x, paper_y, paper_w_px, paper_h_px)
        ctx.stroke()

        # ── Use LayoutEngine for content positioning ──────────────────
        if document and document.is_valid:
            self._engine.sync_document(document, settings)

            doc_w, doc_h = document.dimensions

            if doc_w > 0 and doc_h > 0:
                layout = self._engine.calculate(
                    doc_w, doc_h, settings,
                    paper_w_px, paper_h_px,
                    is_image=document.is_image,
                )

                # ── Margin guides ─────────────────────────────────────
                pa = layout.printable_area
                self._draw_margin_guides(
                    ctx, paper_x, paper_y,
                    paper_w_px, paper_h_px,
                    pa.x, pa.y,
                    pa.x + pa.width, pa.y + pa.height,
                )

                # ── Content rendering ─────────────────────────────────
                content = layout.content
                if content.width > 0 and content.height > 0:
                    # Clip to printable area
                    ctx.save()
                    ctx.rectangle(
                        paper_x + pa.x, paper_y + pa.y,
                        pa.width, pa.height,
                    )
                    ctx.clip()

                    # N-up rendering
                    if settings.pages_per_sheet > 1 and document.page_count > 1:
                        nup = self._engine.calculate_nup(
                            settings, page_num, document.page_count,
                            pa.x, pa.y, pa.width, pa.height,
                        )
                        self._render_nup(
                            ctx, document, nup,
                            paper_x, paper_y,
                        )
                    else:
                        # Single page
                        render_w = max(1, int(content.width))
                        render_h = max(1, int(content.height))
                        page_surface = document.render_page(page_num, render_w, render_h)
                        if page_surface:
                            ctx.set_source_surface(
                                page_surface,
                                paper_x + content.x,
                                paper_y + content.y,
                            )
                            ctx.paint()

                    ctx.restore()
        else:
            # Draw margin guides even without content
            layout = self._engine.calculate(
                100, 100, settings,
                paper_w_px, paper_h_px,
                is_image=False,
            )
            pa = layout.printable_area
            self._draw_margin_guides(
                ctx, paper_x, paper_y,
                paper_w_px, paper_h_px,
                pa.x, pa.y,
                pa.x + pa.width, pa.y + pa.height,
            )

        return surface

    def _draw_margin_guides(
        self,
        ctx: cairo.Context,
        paper_x: float, paper_y: float,
        paper_w: float, paper_h: float,
        left: float, top: float,
        right: float, bottom: float,
    ) -> None:
        """Draw dashed margin guide lines on the paper."""
        ctx.save()
        ctx.set_source_rgba(*MARGIN_GUIDE_COLOR)
        ctx.set_line_width(0.5)
        ctx.set_dash([4, 4])

        # Top margin
        ctx.move_to(paper_x, paper_y + top)
        ctx.line_to(paper_x + paper_w, paper_y + top)
        ctx.stroke()
        # Bottom margin
        ctx.move_to(paper_x, paper_y + bottom)
        ctx.line_to(paper_x + paper_w, paper_y + bottom)
        ctx.stroke()
        # Left margin
        ctx.move_to(paper_x + left, paper_y)
        ctx.line_to(paper_x + left, paper_y + paper_h)
        ctx.stroke()
        # Right margin
        ctx.move_to(paper_x + right, paper_y)
        ctx.line_to(paper_x + right, paper_y + paper_h)
        ctx.stroke()

        ctx.restore()

    def _render_nup(
        self,
        ctx: cairo.Context,
        document: Document,
        nup: NupLayout,
        paper_x: float,
        paper_y: float,
    ) -> None:
        """Render N-up pages using the layout engine's cell positions."""
        for cell in nup.cells:
            rect = cell.rect
            cx = paper_x + rect.x
            cy = paper_y + rect.y
            cw = rect.width
            ch = rect.height

            if cw <= 0 or ch <= 0:
                continue

            # Light border for each sub-page
            ctx.set_source_rgba(0.8, 0.8, 0.8, 0.5)
            ctx.set_line_width(0.5)
            ctx.rectangle(cx, cy, cw, ch)
            ctx.stroke()

            page_surface = document.render_page(cell.page_index, int(cw), int(ch))
            if page_surface:
                ctx.set_source_surface(page_surface, cx, cy)
                ctx.paint()

    def render_thumbnail(
        self,
        document: Document,
        page_num: int,
        width: int,
        height: int,
    ) -> Optional[cairo.ImageSurface]:
        """Render a small thumbnail of a page for the thumbnail strip."""
        if not document or not document.is_valid:
            return None
        if page_num < 0 or page_num >= document.page_count:
            return None

        return document.render_page(page_num, width, height)

    def estimate_pages(
        self, document: Optional[Document], settings: PrintSettings
    ) -> int:
        """Estimate the number of physical sheets needed."""
        if not document or not document.is_valid:
            return 0
        return self._engine.estimate_sheets(document.page_count, settings)

    def count_document(
        self, document: Optional[Document], settings: PrintSettings
    ) -> PageCount:
        """Pages, printed sides and sheets this document prints as."""
        return self._engine.count_document(document, settings)

    def preview_sheet_count(
        self, document: Optional[Document], settings: PrintSettings
    ) -> int:
        """Number of sheets the preview can page through."""
        if not document or not document.is_valid:
            return 0
        self._engine.sync_document(document, settings)
        if settings.pages_per_sheet > 1 and document.page_count > 1:
            return math.ceil(document.page_count / settings.pages_per_sheet)
        return document.page_count
