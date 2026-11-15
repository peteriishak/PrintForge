"""Formatting and parsing utilities."""

from __future__ import annotations

import math
from typing import Optional


def format_file_size(size_bytes: int) -> str:
    """Format a file size in bytes to a human-readable string.

    Examples:
        512 -> '512 B'
        1536 -> '1.5 KB'
        2621440 -> '2.5 MB'
    """
    if size_bytes < 0:
        return "0 B"
    if size_bytes == 0:
        return "0 B"

    units = ["B", "KB", "MB", "GB"]
    magnitude = int(math.floor(math.log(size_bytes, 1024))) if size_bytes > 0 else 0
    magnitude = min(magnitude, len(units) - 1)
    value = size_bytes / (1024 ** magnitude)

    if magnitude == 0:
        return f"{int(value)} B"
    if value >= 100:
        return f"{value:.0f} {units[magnitude]}"
    if value >= 10:
        return f"{value:.1f} {units[magnitude]}"
    return f"{value:.2f} {units[magnitude]}"


def format_dimensions(width: int, height: int, unit: str = "px") -> str:
    """Format image dimensions.

    Examples:
        (1920, 1080) -> '1920 × 1080 px'
        (210, 297, 'mm') -> '210 × 297 mm'
    """
    return f"{width} × {height} {unit}"


def parse_page_range(range_str: str, max_pages: int) -> Optional[list[int]]:
    """Parse a page range string into a sorted list of 1-indexed page numbers.

    Supports formats like: '1', '1-3', '1-3, 5, 8-10', '1,2,3'

    Args:
        range_str: The range string to parse.
        max_pages: Maximum valid page number.

    Returns:
        Sorted list of page numbers, or None if the input is invalid.
    """
    if not range_str or not range_str.strip():
        return None

    pages: set[int] = set()

    parts = range_str.replace(" ", "").split(",")
    for part in parts:
        if not part:
            continue

        if "-" in part:
            bounds = part.split("-", 1)
            if len(bounds) != 2:
                return None
            try:
                start = int(bounds[0])
                end = int(bounds[1])
            except ValueError:
                return None

            if start < 1 or end < 1 or start > max_pages or end > max_pages:
                return None
            if start > end:
                return None

            pages.update(range(start, end + 1))
        else:
            try:
                page = int(part)
            except ValueError:
                return None
            if page < 1 or page > max_pages:
                return None
            pages.add(page)

    if not pages:
        return None

    return sorted(pages)


def format_page_range(pages: list[int]) -> str:
    """Format a list of page numbers into a compact range string.

    Examples:
        [1, 2, 3, 5, 8, 9, 10] -> '1-3, 5, 8-10'
    """
    if not pages:
        return ""

    sorted_pages = sorted(set(pages))
    ranges: list[str] = []
    start = sorted_pages[0]
    prev = start

    for page in sorted_pages[1:]:
        if page == prev + 1:
            prev = page
        else:
            if start == prev:
                ranges.append(str(start))
            else:
                ranges.append(f"{start}-{prev}")
            start = page
            prev = page

    # Append the last range
    if start == prev:
        ranges.append(str(start))
    else:
        ranges.append(f"{start}-{prev}")

    return ", ".join(ranges)


def validate_copies(value: str) -> Optional[int]:
    """Validate a copies input string. Returns the int value or None if invalid."""
    try:
        n = int(value)
        if 1 <= n <= 999:
            return n
        return None
    except (ValueError, TypeError):
        return None
