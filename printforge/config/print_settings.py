"""Print settings data model — the canonical representation of all print parameters."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class ColorMode(Enum):
    COLOR = "color"
    GRAYSCALE = "monochrome"
    BLACK_AND_WHITE = "monochrome-1bit"


class Orientation(Enum):
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"
    AUTO = "auto"


class ScalingMode(Enum):
    ACTUAL_SIZE = "actual_size"
    FIT_TO_PAGE = "fit_to_page"
    FILL_PAGE = "fill_page"
    FIT_WIDTH = "fit_width"
    FIT_HEIGHT = "fit_height"
    CUSTOM = "custom"


class BookletMode(Enum):
    OFF = "off"
    LEFT_BINDING = "left"
    RIGHT_BINDING = "right"


class MarginPreset(Enum):
    DEFAULT = "default"
    MINIMUM = "minimum"
    CUSTOM = "custom"


class Position(Enum):
    CENTER = "center"
    TOP_LEFT = "top_left"
    TOP_CENTER = "top_center"
    TOP_RIGHT = "top_right"
    CENTER_LEFT = "center_left"
    CENTER_RIGHT = "center_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_CENTER = "bottom_center"
    BOTTOM_RIGHT = "bottom_right"
    CUSTOM = "custom"


class DuplexMode(Enum):
    OFF = "one-sided"
    LONG_EDGE = "two-sided-long-edge"
    SHORT_EDGE = "two-sided-short-edge"


class PrintQuality(Enum):
    DRAFT = "3"
    NORMAL = "4"
    HIGH = "5"
    BEST = "6"


class ImageFit(Enum):
    FIT_INSIDE = "fit_inside"
    FILL_PAGE = "fill_page"
    ACTUAL_SIZE = "actual_size"
    CUSTOM_SCALE = "custom_scale"


class CropMode(Enum):
    NONE = "none"
    CROP_TO_PAPER = "crop_to_paper"
    CUSTOM = "custom"


class PageRangeMode(Enum):
    ALL = "all"
    CURRENT = "current"
    CUSTOM = "custom"


class Collation(Enum):
    COLLATED = "collated"
    UNCOLLATED = "uncollated"


@dataclass
class Margins:
    """Print margins in millimeters."""

    top: float = 10.0
    bottom: float = 10.0
    left: float = 10.0
    right: float = 10.0

    def to_dict(self) -> dict:
        return {"top": self.top, "bottom": self.bottom,
                "left": self.left, "right": self.right}

    @classmethod
    def from_dict(cls, d: dict) -> Margins:
        return cls(
            top=d.get("top", 10.0),
            bottom=d.get("bottom", 10.0),
            left=d.get("left", 10.0),
            right=d.get("right", 10.0),
        )

    @classmethod
    def default(cls) -> Margins:
        return cls(top=10.0, bottom=10.0, left=10.0, right=10.0)

    @classmethod
    def minimum(cls) -> Margins:
        return cls(top=3.0, bottom=3.0, left=3.0, right=3.0)


# Standard print resolutions (display label, CUPS value, numeric DPI)
STANDARD_RESOLUTIONS: list[tuple[str, str, int]] = [
    ("Automatic", "", 300),
    ("300 DPI", "300x300dpi", 300),
    ("600 DPI", "600x600dpi", 600),
    ("1200 DPI", "1200x1200dpi", 1200),
]


@dataclass
class PrintSettings:
    """Complete set of print parameters.

    This is the single source of truth for what the user wants to print
    and how they want it printed. Passed to the renderer and print preparer.
    """

    # ── Basic Settings ──
    printer_name: str = ""
    copies: int = 1
    color_mode: ColorMode = ColorMode.COLOR
    paper_size_name: str = "A4"
    orientation: Orientation = Orientation.PORTRAIT

    # ── Advanced Settings ──
    scaling_mode: ScalingMode = ScalingMode.FIT_TO_PAGE
    scaling_value: float = 100.0  # percentage, used when scaling_mode == CUSTOM
    margin_preset: MarginPreset = MarginPreset.DEFAULT
    margins: Margins = field(default_factory=Margins.default)
    position: Position = Position.CENTER
    custom_x: float = 0.0  # mm, used when position == CUSTOM
    custom_y: float = 0.0  # mm
    pages_per_sheet: int = 1
    duplex: DuplexMode = DuplexMode.OFF
    quality: PrintQuality = PrintQuality.NORMAL
    media_type: str = ""  # CUPS media-type value
    collation: Collation = Collation.COLLATED
    custom_paper_width_mm: float = 210.0
    custom_paper_height_mm: float = 297.0
    tray: str = ""
    resolution: str = ""
    raw_options: dict[str, str] = field(default_factory=dict)

    # ── Booklet & Poster Modes ──
    booklet_mode: BookletMode = BookletMode.OFF
    poster_enabled: bool = False
    poster_cols: int = 2
    poster_rows: int = 2
    poster_overlap_mm: float = 10.0

    # ── PDF Settings ──
    page_range_mode: PageRangeMode = PageRangeMode.ALL
    page_range_str: str = ""  # e.g. "1-3, 5, 8-10"
    current_page: int = 1

    # ── Image Settings ──
    image_fit: ImageFit = ImageFit.FIT_INSIDE
    image_rotation: int = 0  # degrees: 0, 90, 180, 270
    crop_mode: CropMode = CropMode.NONE
    image_brightness: float = 0.0  # -100.0 to 100.0
    image_contrast: float = 0.0    # -100.0 to 100.0
    image_saturation: float = 0.0  # -100.0 to 100.0
    image_sharpness: float = 0.0   # -100.0 to 100.0

    def to_dict(self) -> dict:
        """Serialize to a JSON-friendly dictionary."""
        d = {}
        for fld in self.__dataclass_fields__:
            val = getattr(self, fld)
            if isinstance(val, Enum):
                d[fld] = val.value
            elif isinstance(val, Margins):
                d[fld] = val.to_dict()
            elif isinstance(val, dict):
                d[fld] = dict(val)
            else:
                d[fld] = val
        return d

    @classmethod
    def from_dict(cls, d: dict) -> PrintSettings:
        """Deserialize from a dictionary."""
        kwargs = {}

        enum_fields = {
            "color_mode": ColorMode,
            "orientation": Orientation,
            "scaling_mode": ScalingMode,
            "booklet_mode": BookletMode,
            "margin_preset": MarginPreset,
            "position": Position,
            "duplex": DuplexMode,
            "quality": PrintQuality,
            "image_fit": ImageFit,
            "crop_mode": CropMode,
            "page_range_mode": PageRangeMode,
            "collation": Collation,
        }

        for fld in cls.__dataclass_fields__:
            if fld not in d:
                continue
            val = d[fld]
            if fld in enum_fields:
                try:
                    kwargs[fld] = enum_fields[fld](val)
                except (ValueError, KeyError):
                    pass  # Use default
            elif fld == "margins":
                kwargs[fld] = Margins.from_dict(val) if isinstance(val, dict) else Margins.default()
            elif fld == "raw_options":
                kwargs[fld] = dict(val) if isinstance(val, dict) else {}
            else:
                kwargs[fld] = val

        return cls(**kwargs)

    def get_dpi(self) -> int:
        """Extract effective numeric DPI (e.g. 300, 600, 1200).

        Parses strings like '300x300dpi', '600dpi', '1200 × 1200 DPI'.
        If resolution is empty or unparseable, falls back to quality-based defaults:
        HIGH/BEST -> 600, NORMAL -> 300, DRAFT -> 150.
        """
        if self.resolution:
            import re
            m = re.search(r"(\d+)", self.resolution)
            if m:
                return max(72, int(m.group(1)))

        if self.quality in (PrintQuality.HIGH, PrintQuality.BEST):
            return 600
        elif self.quality == PrintQuality.DRAFT:
            return 150
        return 300

    def to_cups_options(self, capabilities=None) -> dict[str, str]:
        """Convert these settings to CUPS print option strings.

        Pass the printer's PrinterCapabilities so the paper tray is named the
        way its driver expects.

        Returns a dictionary suitable for passing to cups.Connection.printFile().
        """
        opts: dict[str, str] = {}

        # Copies
        if self.copies > 1:
            opts["copies"] = str(self.copies)

        # Color mode
        opts["print-color-mode"] = self.color_mode.value

        # Orientation (CUPS uses 3=portrait, 4=landscape, 5=reverse-landscape, 6=reverse-portrait)
        if self.orientation == Orientation.LANDSCAPE:
            opts["orientation-requested"] = "4"
        elif self.orientation == Orientation.PORTRAIT:
            opts["orientation-requested"] = "3"
        # AUTO: let CUPS decide

        # Paper / media
        from printforge.utils.paper import get_paper_by_name
        paper = get_paper_by_name(self.paper_size_name)
        if paper:
            opts["media"] = paper.cups_name
        elif self.paper_size_name == "Custom":
            opts["media"] = f"Custom.{self.custom_paper_width_mm:g}x{self.custom_paper_height_mm:g}mm"

        # Duplex
        if self.duplex != DuplexMode.OFF:
            opts["sides"] = self.duplex.value
        else:
            opts["sides"] = "one-sided"

        # Quality
        opts["print-quality"] = self.quality.value

        # Media type
        if self.media_type:
            opts["media-type"] = self.media_type
            opts["MediaType"] = self.media_type

        # Tray
        if capabilities is not None:
            tray_options = capabilities.tray_job_options(self.tray)
        else:
            tray_options = {"InputSlot": self.tray} if self.tray else {}
        # Without a driver, CUPS takes the tray as part of the media option
        source = tray_options.pop("media-source", "")
        if source and "media" in opts:
            opts["media"] = f'{opts["media"]},{source}'
        opts.update(tray_options)

        # Resolution
        if self.resolution:
            opts["Resolution"] = self.resolution
            opts["printer-resolution"] = self.resolution

        # Collation
        if self.copies > 1:
            if self.collation == Collation.COLLATED:
                opts["collate"] = "true"
            else:
                opts["collate"] = "false"

        # Pages per sheet (N-up)
        if self.pages_per_sheet > 1:
            opts["number-up"] = str(self.pages_per_sheet)

        # Raw / printer-specific options
        for k, v in self.raw_options.items():
            opts[str(k)] = str(v)

        return opts
