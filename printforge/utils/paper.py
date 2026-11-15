"""Paper size definitions and CUPS media name mappings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PaperSize:
    """Represents a paper size with dimensions in millimeters."""

    name: str
    width_mm: float
    height_mm: float
    cups_name: str
    display_name: Optional[str] = None

    @property
    def label(self) -> str:
        """Human-readable label like 'A4 (210 × 297 mm)'."""
        return f"{self.display_name or self.name} ({self.dimensions_label})"

    @property
    def dimensions_label(self) -> str:
        """Size in millimeters, like '210 × 297 mm'."""
        return f"{self.width_mm:.0f} × {self.height_mm:.0f} mm"

    @property
    def width_pt(self) -> float:
        """Width in points (1 mm = 2.834645669 pt)."""
        return self.width_mm * 72.0 / 25.4

    @property
    def height_pt(self) -> float:
        """Height in points."""
        return self.height_mm * 72.0 / 25.4

    @property
    def width_in(self) -> float:
        """Width in inches."""
        return self.width_mm / 25.4

    @property
    def height_in(self) -> float:
        """Height in inches."""
        return self.height_mm / 25.4

    def landscape(self) -> PaperSize:
        """Return this paper size in landscape orientation."""
        return PaperSize(
            name=self.name,
            width_mm=self.height_mm,
            height_mm=self.width_mm,
            cups_name=self.cups_name,
            display_name=self.display_name,
        )


# ── Standard Paper Sizes ──────────────────────────────────────────────

PAPER_SIZES: dict[str, PaperSize] = {}

_PAPER_DEFS = [
    # ISO A series
    ("A3", 297.0, 420.0, "iso_a3_297x420mm", "A3"),
    ("A4", 210.0, 297.0, "iso_a4_210x297mm", "A4"),
    ("A5", 148.0, 210.0, "iso_a5_148x210mm", "A5"),
    ("A6", 105.0, 148.0, "iso_a6_105x148mm", "A6"),
    # ISO B series
    ("B4", 250.0, 353.0, "iso_b4_250x353mm", "B4"),
    ("B5", 176.0, 250.0, "iso_b5_176x250mm", "B5"),
    # North American
    ("Letter", 215.9, 279.4, "na_letter_8.5x11in", "US Letter"),
    ("Legal", 215.9, 355.6, "na_legal_8.5x14in", "US Legal"),
    ("Executive", 184.15, 266.7, "na_executive_7.25x10.5in", "Executive"),
    ("Tabloid", 279.4, 431.8, "na_ledger_11x17in", "Tabloid"),
    # Photo sizes
    ("4x6", 101.6, 152.4, "na_index-4x6_4x6in", "Photo 4 × 6 in"),
    ("5x7", 127.0, 177.8, "na_5x7_5x7in", "Photo 5 × 7 in"),
    ("8x10", 203.2, 254.0, "na_govt-letter_8x10in", "Photo 8 × 10 in"),
    # Envelopes
    ("DL Envelope", 110.0, 220.0, "iso_dl_110x220mm", "DL Envelope"),
    ("C5 Envelope", 162.0, 229.0, "iso_c5_162x229mm", "C5 Envelope"),
    ("#10 Envelope", 104.78, 241.3, "na_number-10_4.125x9.5in", "#10 Envelope"),
]

for _name, _w, _h, _cups, _display in _PAPER_DEFS:
    PAPER_SIZES[_name] = PaperSize(
        name=_name, width_mm=_w, height_mm=_h,
        cups_name=_cups, display_name=_display,
    )

# Default paper size
DEFAULT_PAPER = PAPER_SIZES["A4"]

# Common paper sizes shown first in dropdowns
COMMON_PAPER_NAMES = ["A4", "A3", "A5", "Letter", "Legal", "Executive"]


def get_paper_by_cups_name(cups_name: str) -> Optional[PaperSize]:
    """Look up a paper size by its CUPS/IPP media name."""
    for ps in PAPER_SIZES.values():
        if ps.cups_name == cups_name:
            return ps
    return None


def get_paper_by_name(name: str) -> Optional[PaperSize]:
    """Look up a paper size by its short name."""
    return PAPER_SIZES.get(name)


def custom_paper(width_mm: float, height_mm: float, name: str = "Custom") -> PaperSize:
    """Create a custom paper size."""
    cups_name = f"custom_{width_mm:.1f}x{height_mm:.1f}mm"
    return PaperSize(
        name=name,
        width_mm=width_mm,
        height_mm=height_mm,
        cups_name=cups_name,
        display_name="Custom Size",
    )
