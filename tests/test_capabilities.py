"""Tests for printer capability parsing."""

import pytest
from printforge.printing.capabilities import parse_capabilities, PrinterCapabilities


class TestParseCapabilities:
    def test_basic_parsing(self):
        attrs = {
            "media-supported": ["iso_a4_210x297mm", "na_letter_8.5x11in"],
            "media-default": "iso_a4_210x297mm",
            "print-color-mode-supported": ["color", "monochrome"],
            "sides-supported": ["one-sided", "two-sided-long-edge"],
            "print-quality-supported": [3, 4, 5],
            "media-type-supported": ["stationery", "photographic"],
        }
        caps = parse_capabilities("TestPrinter", attrs)

        assert caps.printer_name == "TestPrinter"
        assert len(caps.supported_media) == 2
        assert caps.supports_color is True
        assert caps.supports_duplex is True
        assert len(caps.supported_qualities) == 3

    def test_monochrome_only(self):
        attrs = {
            "print-color-mode-supported": "monochrome",
        }
        caps = parse_capabilities("Mono", attrs)
        assert caps.supports_color is False
        assert caps.has_color() is False

    def test_no_duplex(self):
        attrs = {
            "sides-supported": "one-sided",
        }
        caps = parse_capabilities("NoDuplex", attrs)
        assert caps.supports_duplex is False

    def test_string_values(self):
        """Test that single string values (not lists) are handled."""
        attrs = {
            "media-supported": "iso_a4_210x297mm",
            "print-color-mode-supported": "color",
            "sides-supported": "one-sided",
        }
        caps = parse_capabilities("Test", attrs)
        assert len(caps.supported_media) == 1
        assert caps.supported_color_modes == ["color"]

    def test_empty_attrs(self):
        caps = parse_capabilities("Empty", {})
        assert caps.supported_media == []
        assert caps.supported_color_modes == []

    def test_get_paper_sizes(self):
        attrs = {
            "media-supported": ["iso_a4_210x297mm", "na_letter_8.5x11in"],
        }
        caps = parse_capabilities("Test", attrs)
        papers = caps.get_paper_sizes()
        assert len(papers) == 2
        assert papers[0].name == "A4"

    def test_get_paper_sizes_unknown(self):
        attrs = {
            "media-supported": ["some_unknown_media"],
        }
        caps = parse_capabilities("Test", attrs)
        papers = caps.get_paper_sizes()
        # Should return defaults when nothing matches
        assert len(papers) > 0

    def test_get_duplex_modes(self):
        attrs = {
            "sides-supported": ["one-sided", "two-sided-long-edge", "two-sided-short-edge"],
        }
        caps = parse_capabilities("Test", attrs)
        modes = caps.get_duplex_modes()
        assert "Off" in modes
        assert "Long Edge" in modes
        assert "Short Edge" in modes

    def test_get_quality_labels(self):
        attrs = {
            "print-quality-supported": [3, 4, 5],
        }
        caps = parse_capabilities("Test", attrs)
        labels = caps.get_quality_labels()
        names = [l for l, v in labels]
        assert "Draft" in names
        assert "Normal" in names
        assert "High" in names

    def test_get_media_type_labels(self):
        attrs = {
            "media-type-supported": ["stationery", "photographic-glossy"],
        }
        caps = parse_capabilities("Test", attrs)
        labels = caps.get_media_type_labels()
        vals = [v for _, v in labels]
        assert "stationery" in vals
        assert "photographic-glossy" in vals
        assert "labels" in vals  # Labels & Stickers
        assert labels[0][1] == "stationery"
        assert labels[1][1] == "photographic-glossy"


class TestResolutionParsing:
    """Test resolution parsing from IPP attributes, PPD choices, and tuples."""

    def test_parse_ipp_tuple(self):
        from printforge.printing.capabilities import parse_resolution_item
        res = parse_resolution_item((300, 300, 3))
        assert res == ("300 DPI", "300x300dpi", 300, 300)

        res600 = parse_resolution_item((600, 600, 3))
        assert res600 == ("600 DPI", "600x600dpi", 600, 600)

        res1200 = parse_resolution_item((1200, 1200, 3))
        assert res1200 == ("1200 DPI", "1200x1200dpi", 1200, 1200)

    def test_parse_dpcm_tuple(self):
        """118 dots/cm * 2.54 = ~300 DPI."""
        from printforge.printing.capabilities import parse_resolution_item
        res = parse_resolution_item((118, 118, 4))
        assert res == ("300 DPI", "300x300dpi", 300, 300)

    def test_parse_stringified_tuple(self):
        from printforge.printing.capabilities import parse_resolution_item
        res = parse_resolution_item("(300, 300, 3)")
        assert res == ("300 DPI", "300x300dpi", 300, 300)

        res2 = parse_resolution_item("(600, 600)")
        assert res2 == ("600 DPI", "600x600dpi", 600, 600)

    def test_parse_dimension_strings(self):
        from printforge.printing.capabilities import parse_resolution_item
        assert parse_resolution_item("300x300dpi") == ("300 DPI", "300x300dpi", 300, 300)
        assert parse_resolution_item("600 × 600 DPI") == ("600 DPI", "600x600dpi", 600, 600)
        assert parse_resolution_item("1200x1200") == ("1200 DPI", "1200x1200dpi", 1200, 1200)
        assert parse_resolution_item("300dpi") == ("300 DPI", "300x300dpi", 300, 300)

    def test_parse_integer(self):
        from printforge.printing.capabilities import parse_resolution_item
        assert parse_resolution_item(600) == ("600 DPI", "600x600dpi", 600, 600)
        assert parse_resolution_item("1200") == ("1200 DPI", "1200x1200dpi", 1200, 1200)

    def test_parse_malformed_returns_none(self):
        from printforge.printing.capabilities import parse_resolution_item
        assert parse_resolution_item(None) is None
        assert parse_resolution_item("") is None
        assert parse_resolution_item("invalid_text") is None
        assert parse_resolution_item((0, 0, 3)) is None
        assert parse_resolution_item((-300, 300, 3)) is None
        assert parse_resolution_item("(0, 0, 3)") is None

    def test_capabilities_resolution_deduplication_and_sorting(self):
        caps = PrinterCapabilities(
            supported_resolutions=[
                "1200x1200dpi",
                "(300, 300, 3)",
                "300x300dpi",
                (600, 600, 3),
                "invalid",
                "600x600dpi",
            ]
        )
        labels = caps.get_resolution_labels()
        assert labels == [
            ("300 DPI", "300x300dpi"),
            ("600 DPI", "600x600dpi"),
            ("1200 DPI", "1200x1200dpi"),
        ]

    def test_parse_real_world_cups_attributes(self):
        """Simulate real CUPS attributes as returned by Ricoh SP-C352DN: [(300, 300, 3)]."""
        attrs = {
            "printer-resolution-supported": [(300, 300, 3)],
            "media-supported": ["iso_a4_210x297mm"],
        }
        caps = parse_capabilities("SP-C352DN", attrs)
        assert caps.supported_resolutions == ["300x300dpi"]
        labels = caps.get_resolution_labels()
        vals = [v for _, v in labels]
        assert "300x300dpi" in vals
        # Ensure no raw (300, 300, 3) string is present in labels or values
        for label, val in labels:
            assert "(" not in label
            assert "," not in label

    def test_settings_panel_dynamic_resolutions(self):
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw
        Adw.init()
        from printforge.ui.settings_panel import SettingsPanel
        from printforge.printing.capabilities import PrinterCapabilities

        panel = SettingsPanel()
        caps_300 = PrinterCapabilities(printer_name="Ricoh", supported_resolutions=["300x300dpi"])
        panel.set_capabilities(caps_300)
        labels = panel._resolution_row.labels
        assert "Automatic" in labels
        assert "300 DPI" in labels

        for l in labels:
            assert "(300, 300, 3)" not in l

        panel.set_capabilities(None)
        assert "Automatic" in panel._resolution_row.labels



