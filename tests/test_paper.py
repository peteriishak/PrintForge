"""Tests for paper size utilities."""

import pytest
from printforge.utils.paper import (
    PaperSize, PAPER_SIZES, DEFAULT_PAPER, COMMON_PAPER_NAMES,
    get_paper_by_cups_name, get_paper_by_name, custom_paper,
)


class TestPaperSize:
    def test_a4_dimensions(self):
        a4 = PAPER_SIZES["A4"]
        assert a4.width_mm == 210.0
        assert a4.height_mm == 297.0

    def test_a4_cups_name(self):
        a4 = PAPER_SIZES["A4"]
        assert a4.cups_name == "iso_a4_210x297mm"

    def test_letter_dimensions(self):
        letter = PAPER_SIZES["Letter"]
        assert letter.width_mm == pytest.approx(215.9)
        assert letter.height_mm == pytest.approx(279.4)

    def test_landscape(self):
        a4 = PAPER_SIZES["A4"]
        landscape = a4.landscape()
        assert landscape.width_mm == 297.0
        assert landscape.height_mm == 210.0

    def test_points_conversion(self):
        a4 = PAPER_SIZES["A4"]
        assert a4.width_pt == pytest.approx(595.276, rel=0.01)
        assert a4.height_pt == pytest.approx(841.89, rel=0.01)

    def test_inches_conversion(self):
        letter = PAPER_SIZES["Letter"]
        assert letter.width_in == pytest.approx(8.5, rel=0.01)
        assert letter.height_in == pytest.approx(11.0, rel=0.01)

    def test_label(self):
        a4 = PAPER_SIZES["A4"]
        label = a4.label
        assert "A4" in label
        assert "210" in label
        assert "297" in label

    def test_default_paper(self):
        assert DEFAULT_PAPER.name == "A4"

    def test_common_papers_exist(self):
        for name in COMMON_PAPER_NAMES:
            assert name in PAPER_SIZES


class TestPaperLookup:
    def test_by_cups_name(self):
        ps = get_paper_by_cups_name("iso_a4_210x297mm")
        assert ps is not None
        assert ps.name == "A4"

    def test_by_cups_name_not_found(self):
        ps = get_paper_by_cups_name("nonexistent_paper")
        assert ps is None

    def test_by_name(self):
        ps = get_paper_by_name("Letter")
        assert ps is not None
        assert ps.name == "Letter"

    def test_by_name_not_found(self):
        ps = get_paper_by_name("FakePaper")
        assert ps is None


class TestCustomPaper:
    def test_custom_paper(self):
        cp = custom_paper(100, 200, "MyPaper")
        assert cp.width_mm == 100
        assert cp.height_mm == 200
        assert cp.name == "MyPaper"
        assert "custom_" in cp.cups_name

    def test_custom_paper_default_name(self):
        cp = custom_paper(150, 250)
        assert cp.name == "Custom"
