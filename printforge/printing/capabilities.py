"""Printer capability detection — queries CUPS/IPP attributes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Any

from printforge.printing.ppd import PpdInfo, pwg_source_keyword
from printforge.utils.paper import PaperSize, PAPER_SIZES, get_paper_by_cups_name


# (label, value) pairs shared by the settings panel and capability parsing.
QUALITY_LEVELS: list[tuple[str, str]] = [
    ("Draft", "3"),
    ("Normal", "4"),
    ("High", "5"),
    ("Best", "6"),
]

MEDIA_TYPES: list[tuple[str, str]] = [
    ("Plain Paper", "stationery"),
    ("Labels & Stickers", "labels"),
    ("Glossy Photo", "photographic-glossy"),
    ("High Gloss Photo", "photographic-high-gloss"),
    ("Matte Photo", "photographic-matte"),
    ("Heavyweight Paper", "stationery-heavyweight"),
    ("Cardstock", "cardstock"),
    ("Lightweight Paper", "stationery-lightweight"),
    ("Envelope", "envelope"),
    ("Transparency", "transparency"),
]

_EXTRA_MEDIA_TYPE_LABELS = {
    "photographic": "Photo Paper",
    "stationery-letterhead": "Letterhead",
    "stationery-preprinted": "Preprinted Paper",
    "stationery-recycled": "Recycled Paper",
    "stationery-coated": "Coated Paper",
    "envelope-plain": "Envelope",
}

_TRAY_LABELS = {
    "auto": "Automatic",
    "main": "Main Tray",
    "manual": "Manual Feed",
    "by-pass-tray": "Bypass Tray",
    "bypass-tray": "Bypass Tray",
    "envelope": "Envelope Feeder",
    "alternate": "Alternate Tray",
    "large-capacity": "Large Capacity Tray",
    "rear": "Rear Tray",
    "top": "Top Tray",
    "middle": "Middle Tray",
    "bottom": "Bottom Tray",
    "photo": "Photo Tray",
}

STANDARD_RESOLUTIONS: list[int] = [300, 600, 1200]


def _humanize(value: str) -> str:
    """Turn an IPP keyword like 'tray-1' into 'Tray 1'."""
    return value.replace("-", " ").replace("_", " ").strip().title()


def media_type_label(value: str) -> str:
    """Readable label for an IPP media-type keyword."""
    for label, known in MEDIA_TYPES:
        if known == value:
            return label
    return _EXTRA_MEDIA_TYPE_LABELS.get(value, _humanize(value))


def tray_label(value: str) -> str:
    """Readable label for an IPP media-source keyword (e.g. 'tray-1' → 'Tray 1')."""
    return _TRAY_LABELS.get(value, _humanize(value))


def resolution_label(x_dpi: int, y_dpi: int) -> str:
    """'600 DPI' for square resolutions, '600 × 1200 DPI' otherwise."""
    if x_dpi == y_dpi:
        return f"{x_dpi} DPI"
    return f"{x_dpi} × {y_dpi} DPI"


def _resolution(x_dpi: int, y_dpi: int, units: int = 3) -> Optional[tuple[str, str, int, int]]:
    """Build a parsed resolution, converting dots-per-cm (units=4) to DPI."""
    if units == 4:
        x_dpi = round(x_dpi * 2.54)
        y_dpi = round(y_dpi * 2.54)
    if x_dpi <= 0 or y_dpi <= 0:
        return None
    return (resolution_label(x_dpi, y_dpi), f"{x_dpi}x{y_dpi}dpi", x_dpi, y_dpi)


def parse_resolution_item(raw: Any) -> Optional[tuple[str, str, int, int]]:
    """Parse a raw resolution into (display_label, cups_value, x_dpi, y_dpi).

    Handles:
    - IPP tuple: (300, 300, 3) where 3=DPI, 4=DPCM
    - String repr of tuple: "(300, 300, 3)"
    - Standard strings: "300x300dpi", "600x600", "1200 × 1200 DPI", "600dpi"
    - Pure integer or digit string: 300, "600"
    Returns None if malformed, internal, or invalid.
    """
    if raw is None:
        return None

    # Tuple / list from IPP: (xres, yres, units)
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        try:
            units = int(raw[2]) if len(raw) > 2 else 3
            return _resolution(int(raw[0]), int(raw[1]), units)
        except (ValueError, TypeError):
            return None

    s = str(raw).strip()
    if not s:
        return None

    # String repr of tuple: "(300, 300, 3)" or "(600, 600)"
    m = re.match(r"^\(\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*(\d+))?\s*\)$", s)
    if m:
        units = int(m.group(3)) if m.group(3) else 3
        return _resolution(int(m.group(1)), int(m.group(2)), units)

    # Dimension string: "300x300dpi", "300 × 300 DPI", "600x600"
    m = re.search(r"(\d+)\s*(?:x|X|×)\s*(\d+)", s)
    if m:
        return _resolution(int(m.group(1)), int(m.group(2)))

    # Single DPI string ("300dpi", "600 dpi") or pure integer ("300")
    m = re.search(r"(\d+)\s*dpi", s, re.IGNORECASE)
    if m or s.isdigit():
        dpi = int(m.group(1)) if m else int(s)
        return _resolution(dpi, dpi)

    return None


@dataclass
class PrinterCapabilities:
    """Parsed capabilities of a specific printer.

    Populated from CUPS getPrinterAttributes() IPP response.
    """

    printer_name: str = ""

    # Paper sizes the printer supports
    supported_media: list[str] = field(default_factory=list)
    default_media: str = ""

    # Color
    supports_color: bool = True
    supported_color_modes: list[str] = field(default_factory=list)

    # Duplex
    supports_duplex: bool = False
    supported_sides: list[str] = field(default_factory=list)

    # Borderless
    supports_borderless: bool = False

    # Quality
    supported_qualities: list[str] = field(default_factory=list)

    # Media type
    supported_media_types: list[str] = field(default_factory=list)

    # Resolution
    supported_resolutions: list[str] = field(default_factory=list)

    # Trays
    supported_sources: list[str] = field(default_factory=list)

    # Copies
    max_copies: int = 999

    # Raw attributes dict for anything else
    raw_attributes: dict = field(default_factory=dict)

    # The queue's driver, when it has one. Its choices are what a job can really select.
    ppd: Optional[PpdInfo] = None

    @property
    def trays(self) -> list[str]:
        """Alias for supported_sources."""
        return self.supported_sources

    def get_paper_sizes(self) -> list[PaperSize]:
        """Return PaperSize objects for each supported media, with known sizes first."""
        known = []
        for media_name in self.supported_media:
            ps = get_paper_by_cups_name(media_name)
            if ps:
                known.append(ps)

        # If no known sizes matched, return common defaults
        if not known:
            return [PAPER_SIZES[n] for n in ["A4", "A3", "A5", "Letter", "Legal"]
                    if n in PAPER_SIZES]
        return known

    def has_color(self) -> bool:
        if self.supported_color_modes:
            return "color" in self.supported_color_modes
        return self.supports_color

    def get_duplex_modes(self) -> list[str]:
        """Return human-readable duplex mode names."""
        modes = []
        for side in self.supported_sides:
            if side == "one-sided":
                modes.append("Off")
            elif side == "two-sided-long-edge":
                modes.append("Long Edge")
            elif side == "two-sided-short-edge":
                modes.append("Short Edge")
        return modes if modes else ["Off"]

    def get_quality_labels(self) -> list[tuple[str, str]]:
        """Return (label, value) pairs for supported print qualities.

        Always offers Draft, Normal, High, and Best when the printer
        doesn't report its own choices.
        """
        if len(self.supported_qualities) > 1:
            names = dict((value, label) for label, value in QUALITY_LEVELS)
            return [(names.get(q, f"Quality {q}"), q) for q in self.supported_qualities]
        return list(QUALITY_LEVELS)

    def get_media_type_labels(self) -> list[tuple[str, str]]:
        """Return (label, cups_value) pairs for media types.

        Printer-reported types come first, followed by the standard types
        (plain, labels, glossy, cardstock, …) that aren't already listed.
        """
        reported = self.supported_media_types if len(self.supported_media_types) > 1 else []
        values = list(dict.fromkeys(reported + [value for _, value in MEDIA_TYPES]))
        return [(media_type_label(value), value) for value in values]

    def get_tray_labels(self) -> list[tuple[str, str]]:
        """Return (label, value) pairs for the trays that can be picked by hand.

        Values are the driver's own choices when the queue has one, because a
        job can only select those; otherwise IPP media-source keywords.
        Automatic selection is not listed: it is the absence of a choice.
        """
        if self.ppd and self.ppd.trays:
            return [
                (choice.label, choice.value) for choice in self.ppd.trays
                if pwg_source_keyword(choice.value) != "auto"
            ]
        return [(tray_label(tray), tray) for tray in self.supported_sources if tray != "auto"]

    def tray_job_options(self, tray: str) -> dict[str, str]:
        """CUPS job options that feed paper from `tray` ('' lets the printer choose)."""
        if self.ppd and self.ppd.trays:
            slot = self.ppd.option("InputSlot")
            if tray and not slot.has_choice(tray):
                # Saved as an IPP keyword ('top'): find the driver choice it stands for
                tray = next((c.value for c in slot.choices if pwg_source_keyword(c.value) == tray), "")
            # Name the automatic choice outright, so a queue defaulting to
            # manual feed can't override it
            choice = tray or self.ppd.auto_tray
            return {"InputSlot": choice} if choice else {}
        if tray and tray != "auto":
            return {"media-source": tray}
        return {}

    def get_resolution_labels(self) -> list[tuple[str, str]]:
        """Return (label, cups_value) pairs for valid supported resolutions.

        Sorted in ascending order of DPI.
        Removes duplicates, ignores invalid or malformed items, and ensures
        standard resolutions (300, 600, 1200 DPI) are available.
        """
        parsed = [parse_resolution_item(r) for r in self.supported_resolutions]
        parsed += [_resolution(dpi, dpi) for dpi in STANDARD_RESOLUTIONS]

        by_value: dict[str, tuple[str, int]] = {}
        for item in parsed:
            if item and item[1] not in by_value:
                label, cups_val, x_dpi, _ = item
                by_value[cups_val] = (label, x_dpi)

        ordered = sorted(by_value.items(), key=lambda entry: entry[1][1])
        return [(label, cups_val) for cups_val, (label, _) in ordered]


def parse_capabilities(printer_name: str, attrs: dict) -> PrinterCapabilities:
    """Parse CUPS printer attributes into a PrinterCapabilities object.

    Args:
        printer_name: The CUPS queue name.
        attrs: Dictionary from cups.Connection.getPrinterAttributes().
    """
    caps = PrinterCapabilities(printer_name=printer_name, raw_attributes=attrs)

    # Media / paper sizes
    media = attrs.get("media-supported", [])
    if isinstance(media, str):
        media = [media]
    caps.supported_media = list(media)
    caps.default_media = attrs.get("media-default", "")

    # Color modes
    color_modes = attrs.get("print-color-mode-supported", [])
    if isinstance(color_modes, str):
        color_modes = [color_modes]
    caps.supported_color_modes = list(color_modes)
    caps.supports_color = "color" in caps.supported_color_modes

    # Duplex / sides
    sides = attrs.get("sides-supported", [])
    if isinstance(sides, str):
        sides = [sides]
    caps.supported_sides = list(sides)
    caps.supports_duplex = any(
        s in sides for s in ["two-sided-long-edge", "two-sided-short-edge"]
    )

    # Quality
    qualities = attrs.get("print-quality-supported", [])
    if isinstance(qualities, (int, str)):
        qualities = [str(qualities)]
    else:
        qualities = [str(q) for q in qualities]
    caps.supported_qualities = qualities

    # Media types
    media_types = attrs.get("media-type-supported", [])
    if isinstance(media_types, str):
        media_types = [media_types]
    caps.supported_media_types = list(media_types)

    # Resolutions: Parse IPP resolution structures or strings cleanly
    raw_res = attrs.get("printer-resolution-supported", [])
    if not raw_res:
        raw_res = attrs.get("resolution-supported", [])
    if isinstance(raw_res, (str, tuple)):
        raw_res = [raw_res]

    clean_res: list[str] = []
    seen_res: set[str] = set()
    for item in raw_res:
        parsed = parse_resolution_item(item)
        if parsed:
            label, cups_val, _, _ = parsed
            if cups_val not in seen_res:
                seen_res.add(cups_val)
                clean_res.append(cups_val)

    caps.supported_resolutions = clean_res

    # Sources / trays
    sources = attrs.get("media-source-supported", [])
    if isinstance(sources, str):
        sources = [sources]
    caps.supported_sources = list(sources)

    # Max copies
    copies_sup = attrs.get("copies-supported", None)
    if copies_sup:
        if isinstance(copies_sup, (list, tuple)) and len(copies_sup) == 2:
            caps.max_copies = int(copies_sup[1])
        elif isinstance(copies_sup, int):
            caps.max_copies = copies_sup

    return caps
