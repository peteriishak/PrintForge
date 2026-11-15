"""Unit conversion utilities for print measurements."""

from __future__ import annotations

# ── Constants ──────────────────────────────────────────────────────────

MM_PER_INCH = 25.4
POINTS_PER_INCH = 72.0
POINTS_PER_MM = POINTS_PER_INCH / MM_PER_INCH  # ~2.8346


# ── Conversion Functions ──────────────────────────────────────────────

def mm_to_pt(mm: float) -> float:
    """Convert millimeters to points."""
    return mm * POINTS_PER_MM


def pt_to_mm(pt: float) -> float:
    """Convert points to millimeters."""
    return pt / POINTS_PER_MM


def mm_to_in(mm: float) -> float:
    """Convert millimeters to inches."""
    return mm / MM_PER_INCH


def in_to_mm(inches: float) -> float:
    """Convert inches to millimeters."""
    return inches * MM_PER_INCH


def pt_to_in(pt: float) -> float:
    """Convert points to inches."""
    return pt / POINTS_PER_INCH


def in_to_pt(inches: float) -> float:
    """Convert inches to points."""
    return inches * POINTS_PER_INCH


def px_to_mm(px: float, dpi: float) -> float:
    """Convert pixels to millimeters at a given DPI."""
    if dpi <= 0:
        return 0.0
    return (px / dpi) * MM_PER_INCH


def mm_to_px(mm: float, dpi: float) -> float:
    """Convert millimeters to pixels at a given DPI."""
    return (mm / MM_PER_INCH) * dpi


def px_to_pt(px: float, dpi: float) -> float:
    """Convert pixels to points at a given DPI."""
    if dpi <= 0:
        return 0.0
    return (px / dpi) * POINTS_PER_INCH


def pt_to_px(pt: float, dpi: float) -> float:
    """Convert points to pixels at a given DPI."""
    return (pt / POINTS_PER_INCH) * dpi
