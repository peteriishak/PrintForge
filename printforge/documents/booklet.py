"""Booklet imposition — arranges pages into folded booklet signatures.

Supports:
- Left binding (standard Western: pages turn from right to left)
- Right binding (Manga / RTL: pages turn from left to right)
- Padding to multiple of 4 pages with blank pages
- Generating booklet imposition sequences for preview and print prep
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from printforge.config.print_settings import BookletMode


@dataclass
class BookletFace:
    """A single side (front or back) of a physical sheet in a booklet.
    
    Contains two page indices: left page and right page.
    Indices are 0-based into the document pages, or None for a blank page.
    """
    sheet_index: int  # 0-indexed physical sheet
    is_back: bool     # False = front side, True = back side
    left_page: Optional[int]   # 0-indexed document page, or None
    right_page: Optional[int]  # 0-indexed document page, or None


class BookletImposer:
    """Calculates booklet page imposition."""

    @staticmethod
    def calculate_imposition(
        page_count: int,
        mode: BookletMode = BookletMode.LEFT_BINDING,
    ) -> list[BookletFace]:
        """Calculate the booklet imposition layout.

        Args:
            page_count: Total number of pages in the original document.
            mode: BookletMode.LEFT_BINDING or BookletMode.RIGHT_BINDING.

        Returns:
            List of BookletFace objects, each representing one side of a sheet.
            Total faces = ceil(page_count / 4) * 2.
        """
        if page_count <= 0 or mode == BookletMode.OFF:
            return []

        # Number of sheets needed (each sheet holds 4 pages: 2 front, 2 back)
        total_sheets = math.ceil(page_count / 4)
        total_booklet_pages = total_sheets * 4

        faces: list[BookletFace] = []

        for s in range(total_sheets):
            # 1-based page numbers for standard Western (Left binding):
            # Sheet s (0-indexed):
            # Front side: left = total_pages - 2*s, right = 1 + 2*s
            # Back side:  left = 2 + 2*s, right = total_pages - 1 - 2*s
            if mode == BookletMode.LEFT_BINDING:
                front_left_1 = total_booklet_pages - 2 * s
                front_right_1 = 1 + 2 * s
                back_left_1 = 2 + 2 * s
                back_right_1 = total_booklet_pages - 1 - 2 * s
            else:
                # Right binding (RTL / Manga):
                front_left_1 = 1 + 2 * s
                front_right_1 = total_booklet_pages - 2 * s
                back_left_1 = total_booklet_pages - 1 - 2 * s
                back_right_1 = 2 + 2 * s

            # Convert 1-based to 0-based, map > page_count to None (blank)
            def to_0based(p_1: int) -> Optional[int]:
                idx = p_1 - 1
                return idx if idx < page_count else None

            # Front face
            faces.append(BookletFace(
                sheet_index=s,
                is_back=False,
                left_page=to_0based(front_left_1),
                right_page=to_0based(front_right_1),
            ))

            # Back face
            faces.append(BookletFace(
                sheet_index=s,
                is_back=True,
                left_page=to_0based(back_left_1),
                right_page=to_0based(back_right_1),
            ))

        return faces

    @staticmethod
    def estimate_sheets(page_count: int, mode: BookletMode) -> int:
        """Calculate number of physical sheets needed for booklet."""
        if page_count <= 0 or mode == BookletMode.OFF:
            return page_count
        return math.ceil(page_count / 4)
