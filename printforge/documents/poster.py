"""Poster / tile printing — splits a single page across multiple sheets.

Supports:
- 2x2, 3x3, 4x4, and custom grid dimensions (cols x rows)
- Configurable overlap margin in millimeters
- Calculating tile coordinates for preview and print prep
- Visual cut / alignment guides
"""

from __future__ import annotations

from dataclasses import dataclass

from printforge.documents.layout_engine import LayoutRect


@dataclass
class PosterTile:
    """A single tile (physical sheet) of a poster."""
    col: int
    row: int
    tile_index: int
    total_tiles: int
    # The sub-region of the source document (in source units) to render
    src_rect: LayoutRect
    # Target sheet index
    sheet_index: int


class PosterTiler:
    """Calculates poster tiling layouts."""

    @staticmethod
    def calculate_tiles(
        doc_width: float,
        doc_height: float,
        cols: int = 2,
        rows: int = 2,
        overlap_pt: float = 28.35,  # ~10mm in points
    ) -> list[PosterTile]:
        """Calculate the grid of tiles for a document.

        Args:
            doc_width: Document width in points/pixels.
            doc_height: Document height in points/pixels.
            cols: Number of horizontal columns of sheets.
            rows: Number of vertical rows of sheets.
            overlap_pt: Overlap in coordinate points between adjacent tiles.

        Returns:
            List of PosterTile objects.
        """
        cols = max(1, cols)
        rows = max(1, rows)
        total_tiles = cols * rows

        # Each tile covers a portion of doc_width and doc_height
        # Total effective span: doc_w + (cols - 1) * overlap_pt
        tile_w = (doc_width + (cols - 1) * overlap_pt) / cols if cols > 1 else doc_width
        tile_h = (doc_height + (rows - 1) * overlap_pt) / rows if rows > 1 else doc_height

        tiles: list[PosterTile] = []
        idx = 0

        for r in range(rows):
            for c in range(cols):
                # Calculate source rect in document coordinates
                src_x = max(0.0, c * (tile_w - overlap_pt))
                src_y = max(0.0, r * (tile_h - overlap_pt))
                src_w = min(tile_w, doc_width - src_x)
                src_h = min(tile_h, doc_height - src_y)

                tiles.append(PosterTile(
                    col=c,
                    row=r,
                    tile_index=idx,
                    total_tiles=total_tiles,
                    src_rect=LayoutRect(src_x, src_y, src_w, src_h),
                    sheet_index=idx,
                ))
                idx += 1

        return tiles
