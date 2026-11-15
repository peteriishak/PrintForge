"""Unified layout engine — single source of truth for all layout calculations.

Both the preview renderer and the print preparer use this engine,
ensuring that what the user sees matches what the printer produces.

Calculates:
- Paper dimensions (mm, pt, px)
- Printable area (after margins)
- Content scaling (fit, fill, actual, custom)
- Content positioning (9-point grid + custom)
- Rotation
- Crop boundaries
- N-up (pages per sheet) grid layout
- Booklet page reordering
- Poster tile splitting
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from printforge.documents.base import Document

from printforge.config.print_settings import (
    PrintSettings, ScalingMode, Position, Orientation,
    ImageFit, CropMode, DuplexMode, PageRangeMode,
)
from printforge.utils.formatting import parse_page_range
from printforge.utils.paper import get_paper_by_name, custom_paper, DEFAULT_PAPER, PaperSize
from printforge.utils.units import mm_to_pt, mm_to_px


@dataclass
class LayoutRect:
    """A rectangle in the layout coordinate space."""
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2


@dataclass(frozen=True)
class PageCount:
    """How much paper a document needs under the current settings."""
    pages: int = 0   # document pages selected for printing
    sides: int = 0   # printed sides per copy, after pages-per-sheet
    sheets: int = 0  # sheets of paper per copy, after two-sided printing
    copies: int = 1

    @property
    def total_sides(self) -> int:
        return self.sides * self.copies

    @property
    def total_sheets(self) -> int:
        # Every copy starts on a fresh sheet, so sheets never get shared between copies
        return self.sheets * self.copies


@dataclass
class LayoutResult:
    """Complete layout calculation result.

    Contains all the coordinates needed to render or print content
    on a page, in the specified coordinate space (pixels or points).
    """
    # Paper dimensions in target units
    paper: LayoutRect = field(default_factory=LayoutRect)

    # Printable area (paper minus margins) in target units
    printable_area: LayoutRect = field(default_factory=LayoutRect)

    # Where the content should be placed, in target units
    content: LayoutRect = field(default_factory=LayoutRect)

    # Scale factor applied to the original content
    scale_x: float = 1.0
    scale_y: float = 1.0

    # Rotation in degrees (0, 90, 180, 270)
    rotation: int = 0

    # Whether content is clipped to printable area
    clip_to_printable: bool = True


@dataclass
class NupCell:
    """A single cell in an N-up grid layout."""
    page_index: int  # The document page to render in this cell
    rect: LayoutRect = field(default_factory=LayoutRect)


@dataclass
class NupLayout:
    """Complete N-up layout for a single physical sheet."""
    cols: int = 1
    rows: int = 1
    cells: list[NupCell] = field(default_factory=list)


class LayoutEngine:
    """Single source of truth for all layout calculations.

    Usage:
        engine = LayoutEngine()

        # For preview (pixel coordinates)
        result = engine.calculate(doc_w, doc_h, settings, paper_w_px, paper_h_px)

        # For print (point coordinates)
        result = engine.calculate_for_print(doc_w, doc_h, settings)

        # For N-up layouts
        nup = engine.calculate_nup(settings, sheet_num, total_pages)
    """

    def get_paper_size(self, settings: PrintSettings) -> PaperSize:
        """Resolve the effective paper size from settings."""
        paper = get_paper_by_name(settings.paper_size_name)
        if not paper and settings.paper_size_name == "Custom":
            paper = custom_paper(settings.custom_paper_width_mm, settings.custom_paper_height_mm)
        paper = paper or DEFAULT_PAPER
        if settings.orientation == Orientation.LANDSCAPE:
            paper = paper.landscape()
        return paper

    def calculate(
        self,
        doc_width: float,
        doc_height: float,
        settings: PrintSettings,
        target_paper_w: float,
        target_paper_h: float,
        is_image: bool = False,
    ) -> LayoutResult:
        """Calculate layout in an arbitrary coordinate space.

        This is the core method used by both preview and print.
        The caller provides the target paper dimensions in their
        coordinate space (pixels for preview, points for print).

        Args:
            doc_width: Original document width in source units.
            doc_height: Original document height in source units.
            settings: Current print settings.
            target_paper_w: Paper width in target coordinate space.
            target_paper_h: Paper height in target coordinate space.
            is_image: Whether the document is an image (uses image_fit settings).

        Returns:
            LayoutResult with all positions in target coordinates.
        """
        paper = self.get_paper_size(settings)

        # Scale factor from mm to target units
        scale_mm = target_paper_w / paper.width_mm if paper.width_mm > 0 else 1.0

        result = LayoutResult()

        # Paper rect
        result.paper = LayoutRect(0, 0, target_paper_w, target_paper_h)

        # Margins in target units
        margins = settings.margins
        m_left = margins.left * scale_mm
        m_right = margins.right * scale_mm
        m_top = margins.top * scale_mm
        m_bottom = margins.bottom * scale_mm

        # Printable area
        pa_x = m_left
        pa_y = m_top
        pa_w = target_paper_w - m_left - m_right
        pa_h = target_paper_h - m_top - m_bottom

        if pa_w <= 0 or pa_h <= 0:
            return result

        result.printable_area = LayoutRect(pa_x, pa_y, pa_w, pa_h)

        # Handle rotation
        rotation = settings.image_rotation if is_image else 0
        render_doc_w = doc_width
        render_doc_h = doc_height
        if rotation in (90, 270):
            render_doc_w, render_doc_h = doc_height, doc_width
        result.rotation = rotation

        if render_doc_w <= 0 or render_doc_h <= 0:
            return result

        # Calculate scaling
        render_w, render_h, sx, sy = self._calc_scaling(
            render_doc_w, render_doc_h, pa_w, pa_h, settings, is_image,
        )
        result.scale_x = sx
        result.scale_y = sy

        # Calculate position
        offset_x, offset_y = self._calc_position(
            render_w, render_h, pa_w, pa_h, settings, scale_mm,
        )

        result.content = LayoutRect(
            pa_x + offset_x,
            pa_y + offset_y,
            render_w,
            render_h,
        )

        result.clip_to_printable = settings.crop_mode == CropMode.CROP_TO_PAPER

        return result

    def calculate_for_print(
        self,
        doc_width: float,
        doc_height: float,
        settings: PrintSettings,
        is_image: bool = False,
    ) -> LayoutResult:
        """Calculate layout in point coordinates for actual printing.

        Convenience wrapper around calculate() that converts paper
        dimensions to points.
        """
        paper = self.get_paper_size(settings)
        return self.calculate(
            doc_width, doc_height, settings,
            paper.width_pt, paper.height_pt, is_image,
        )

    def calculate_nup(
        self,
        settings: PrintSettings,
        sheet_num: int,
        total_pages: int,
        area_x: float,
        area_y: float,
        area_w: float,
        area_h: float,
    ) -> NupLayout:
        """Calculate N-up grid layout for a single physical sheet.

        Args:
            settings: Print settings (uses pages_per_sheet).
            sheet_num: 0-indexed physical sheet number.
            total_pages: Total number of document pages.
            area_x, area_y: Top-left of the content area.
            area_w, area_h: Size of the content area.

        Returns:
            NupLayout with cells positioned within the content area.
        """
        n = max(1, settings.pages_per_sheet)
        cols, rows = self._get_nup_grid(n)
        cell_pad = 2

        cell_w = area_w / cols
        cell_h = area_h / rows

        layout = NupLayout(cols=cols, rows=rows)
        start_page = sheet_num * n

        for i in range(n):
            page_idx = start_page + i
            if page_idx >= total_pages:
                break

            col = i % cols
            row = i // cols

            cell = NupCell(
                page_index=page_idx,
                rect=LayoutRect(
                    x=area_x + col * cell_w + cell_pad,
                    y=area_y + row * cell_h + cell_pad,
                    width=cell_w - cell_pad * 2,
                    height=cell_h - cell_pad * 2,
                ),
            )
            layout.cells.append(cell)

        return layout

    def get_page_indices(
        self, page_count: int, settings: PrintSettings, ranged: bool = True,
    ) -> Optional[list[int]]:
        """0-indexed document pages selected for printing.

        Returns None when a custom page range doesn't fit the document.
        `ranged` is False for documents that ignore the page range (images).
        """
        if page_count <= 0:
            return []
        if not ranged or settings.page_range_mode == PageRangeMode.ALL:
            return list(range(page_count))
        if settings.page_range_mode == PageRangeMode.CURRENT:
            return [max(0, min(settings.current_page - 1, page_count - 1))]
        if settings.page_range_mode == PageRangeMode.CUSTOM:
            pages = parse_page_range(settings.page_range_str, page_count)
            return [p - 1 for p in pages] if pages else None
        return list(range(page_count))

    def count_pages(
        self, page_count: int, settings: PrintSettings, ranged: bool = True,
    ) -> PageCount:
        """Count the pages, printed sides and sheets one document produces."""
        copies = max(1, settings.copies)
        pages = len(self.get_page_indices(page_count, settings, ranged) or [])
        if pages == 0:
            return PageCount(copies=copies)
        sides = math.ceil(pages / max(1, settings.pages_per_sheet))
        sheets = math.ceil(sides / 2) if settings.duplex != DuplexMode.OFF else sides
        return PageCount(pages=pages, sides=sides, sheets=sheets, copies=copies)

    def sync_document(self, document: Document, settings: PrintSettings) -> None:
        """Lay the document out for the selected paper.

        Text documents re-paginate when the paper or scale changes, so their
        page count is only right after this.
        """
        if hasattr(document, "set_scale"):
            document.set_scale(settings.scaling_value)
        if hasattr(document, "set_page_size"):
            paper = self.get_paper_size(settings)
            document.set_page_size(paper.width_pt, paper.height_pt)

    def count_document(self, document: Optional[Document], settings: PrintSettings) -> PageCount:
        """Count what printing `document` produces, exactly as PrintPreparer prints it."""
        if not document or not document.is_valid:
            return PageCount(copies=max(1, settings.copies))
        self.sync_document(document, settings)
        return self.count_pages(document.page_count, settings, ranged=not document.is_image)

    def estimate_sheets(
        self, page_count: int, settings: PrintSettings
    ) -> int:
        """Estimate number of printed sides needed for the whole document."""
        if page_count <= 0:
            return 0
        nup = max(1, settings.pages_per_sheet)
        sheets = math.ceil(page_count / nup)
        return sheets

    # ── Internal calculations ─────────────────────────────────────────

    def _calc_scaling(
        self,
        doc_w: float,
        doc_h: float,
        content_w: float,
        content_h: float,
        settings: PrintSettings,
        is_image: bool,
    ) -> tuple[float, float, float, float]:
        """Calculate content dimensions and scale factors.

        Returns: (render_w, render_h, scale_x, scale_y)
        """
        # Determine which scaling mode to use
        mode = settings.scaling_mode
        if is_image:
            mode_map = {
                ImageFit.FIT_INSIDE: ScalingMode.FIT_TO_PAGE,
                ImageFit.FILL_PAGE: ScalingMode.FILL_PAGE,
                ImageFit.ACTUAL_SIZE: ScalingMode.ACTUAL_SIZE,
                ImageFit.CUSTOM_SCALE: ScalingMode.CUSTOM,
            }
            mode = mode_map.get(settings.image_fit, mode)

        doc_aspect = doc_w / doc_h if doc_h > 0 else 1.0
        content_aspect = content_w / content_h if content_h > 0 else 1.0

        if mode == ScalingMode.FIT_TO_PAGE:
            if doc_aspect > content_aspect:
                scale = content_w / doc_w
            else:
                scale = content_h / doc_h
            return (doc_w * scale, doc_h * scale, scale, scale)

        elif mode == ScalingMode.FILL_PAGE:
            if doc_aspect > content_aspect:
                scale = content_h / doc_h
            else:
                scale = content_w / doc_w
            return (doc_w * scale, doc_h * scale, scale, scale)

        elif mode == ScalingMode.ACTUAL_SIZE:
            return (min(doc_w, content_w), min(doc_h, content_h), 1.0, 1.0)

        elif mode == ScalingMode.CUSTOM:
            pct = settings.scaling_value / 100.0
            base_scale = min(content_w / doc_w, content_h / doc_h) if doc_w > 0 and doc_h > 0 else 1.0
            scale = base_scale * pct
            return (doc_w * scale, doc_h * scale, scale, scale)

        # Default: fit to page
        scale = min(content_w / doc_w, content_h / doc_h) if doc_w > 0 and doc_h > 0 else 1.0
        return (doc_w * scale, doc_h * scale, scale, scale)

    def _calc_position(
        self,
        render_w: float,
        render_h: float,
        content_w: float,
        content_h: float,
        settings: PrintSettings,
        scale_mm: float,
    ) -> tuple[float, float]:
        """Calculate content offset within the printable area.

        Returns: (offset_x, offset_y)
        """
        pos = settings.position

        positions = {
            Position.CENTER:        lambda: ((content_w - render_w) / 2, (content_h - render_h) / 2),
            Position.TOP_LEFT:      lambda: (0, 0),
            Position.TOP_CENTER:    lambda: ((content_w - render_w) / 2, 0),
            Position.TOP_RIGHT:     lambda: (content_w - render_w, 0),
            Position.CENTER_LEFT:   lambda: (0, (content_h - render_h) / 2),
            Position.CENTER_RIGHT:  lambda: (content_w - render_w, (content_h - render_h) / 2),
            Position.BOTTOM_LEFT:   lambda: (0, content_h - render_h),
            Position.BOTTOM_CENTER: lambda: ((content_w - render_w) / 2, content_h - render_h),
            Position.BOTTOM_RIGHT:  lambda: (content_w - render_w, content_h - render_h),
            Position.CUSTOM:        lambda: (settings.custom_x * scale_mm, settings.custom_y * scale_mm),
        }

        calc = positions.get(pos, positions[Position.CENTER])
        return calc()

    @staticmethod
    def _get_nup_grid(n: int) -> tuple[int, int]:
        """Return (cols, rows) for N-up layout."""
        grids = {
            1: (1, 1), 2: (2, 1), 4: (2, 2),
            6: (3, 2), 9: (3, 3), 16: (4, 4),
        }
        return grids.get(n, (1, 1))
