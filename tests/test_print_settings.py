"""Tests for print settings data model."""

import pytest
from printforge.config.print_settings import (
    PrintSettings, ColorMode, Orientation, ScalingMode, MarginPreset,
    Position, DuplexMode, PrintQuality, ImageFit, CropMode,
    PageRangeMode, Collation, Margins,
)


class TestMargins:
    def test_default(self):
        m = Margins.default()
        assert m.top == 10.0
        assert m.bottom == 10.0

    def test_minimum(self):
        m = Margins.minimum()
        assert m.top == 3.0

    def test_to_dict(self):
        m = Margins(top=5, bottom=10, left=15, right=20)
        d = m.to_dict()
        assert d["top"] == 5
        assert d["right"] == 20

    def test_from_dict(self):
        d = {"top": 5, "bottom": 10, "left": 15, "right": 20}
        m = Margins.from_dict(d)
        assert m.top == 5
        assert m.right == 20


class TestPrintSettings:
    def test_defaults(self):
        s = PrintSettings()
        assert s.copies == 1
        assert s.color_mode == ColorMode.COLOR
        assert s.orientation == Orientation.PORTRAIT
        assert s.paper_size_name == "A4"
        assert s.scaling_mode == ScalingMode.FIT_TO_PAGE

    def test_serialization_roundtrip(self):
        s = PrintSettings(
            printer_name="TestPrinter",
            copies=3,
            color_mode=ColorMode.GRAYSCALE,
            paper_size_name="Letter",
            orientation=Orientation.LANDSCAPE,
            duplex=DuplexMode.LONG_EDGE,
            quality=PrintQuality.HIGH,
            pages_per_sheet=4,
        )
        d = s.to_dict()
        s2 = PrintSettings.from_dict(d)

        assert s2.printer_name == "TestPrinter"
        assert s2.copies == 3
        assert s2.color_mode == ColorMode.GRAYSCALE
        assert s2.paper_size_name == "Letter"
        assert s2.orientation == Orientation.LANDSCAPE
        assert s2.duplex == DuplexMode.LONG_EDGE
        assert s2.quality == PrintQuality.HIGH
        assert s2.pages_per_sheet == 4

    def test_from_dict_with_missing_fields(self):
        s = PrintSettings.from_dict({"copies": 5})
        assert s.copies == 5
        assert s.color_mode == ColorMode.COLOR  # default

    def test_from_dict_with_invalid_enum(self):
        s = PrintSettings.from_dict({"color_mode": "invalid_value"})
        assert s.color_mode == ColorMode.COLOR  # should use default

    def test_margins_serialization(self):
        s = PrintSettings()
        s.margins = Margins(top=5, bottom=15, left=10, right=20)
        d = s.to_dict()
        s2 = PrintSettings.from_dict(d)
        assert s2.margins.top == 5
        assert s2.margins.right == 20

    def test_to_cups_options(self):
        s = PrintSettings(
            copies=3,
            color_mode=ColorMode.GRAYSCALE,
            orientation=Orientation.LANDSCAPE,
            paper_size_name="A4",
            duplex=DuplexMode.LONG_EDGE,
            quality=PrintQuality.HIGH,
            pages_per_sheet=4,
        )
        opts = s.to_cups_options()
        assert opts["copies"] == "3"
        assert opts["print-color-mode"] == "monochrome"
        assert opts["orientation-requested"] == "4"
        assert opts["media"] == "iso_a4_210x297mm"
        assert opts["sides"] == "two-sided-long-edge"
        assert opts["print-quality"] == "5"
        assert opts["number-up"] == "4"

    def test_cups_options_single_copy(self):
        s = PrintSettings(copies=1)
        opts = s.to_cups_options()
        assert "copies" not in opts

    def test_cups_options_collation(self):
        s = PrintSettings(copies=3, collation=Collation.UNCOLLATED)
        opts = s.to_cups_options()
        assert opts["collate"] == "false"

    def test_standard_resolutions_constant(self):
        from printforge.config.print_settings import STANDARD_RESOLUTIONS
        res_values = [v for _, v, _ in STANDARD_RESOLUTIONS]
        assert "" in res_values
        assert "300x300dpi" in res_values
        assert "600x600dpi" in res_values
        assert "1200x1200dpi" in res_values

    def test_resolution_cups_options(self):
        for res_val in ("300x300dpi", "600x600dpi", "1200x1200dpi"):
            s = PrintSettings(resolution=res_val)
            opts = s.to_cups_options()
            assert opts["Resolution"] == res_val
            assert opts["printer-resolution"] == res_val

    def test_get_dpi(self):
        s_300 = PrintSettings(resolution="300x300dpi")
        assert s_300.get_dpi() == 300

        s_600 = PrintSettings(resolution="600x600dpi")
        assert s_600.get_dpi() == 600

        s_1200 = PrintSettings(resolution="1200x1200dpi")
        assert s_1200.get_dpi() == 1200

        # Quality-based fallbacks
        s_auto_normal = PrintSettings(resolution="", quality=PrintQuality.NORMAL)
        assert s_auto_normal.get_dpi() == 300

        s_auto_high = PrintSettings(resolution="", quality=PrintQuality.HIGH)
        assert s_auto_high.get_dpi() == 600

