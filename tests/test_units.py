"""Tests for unit conversion utilities."""

import pytest
from printforge.utils.units import (
    mm_to_pt, pt_to_mm, mm_to_in, in_to_mm,
    pt_to_in, in_to_pt, px_to_mm, mm_to_px,
    px_to_pt, pt_to_px, POINTS_PER_INCH, MM_PER_INCH,
)


class TestMmPt:
    def test_mm_to_pt(self):
        # 25.4mm = 1 inch = 72 points
        assert mm_to_pt(25.4) == pytest.approx(72.0, rel=0.001)

    def test_pt_to_mm(self):
        assert pt_to_mm(72.0) == pytest.approx(25.4, rel=0.001)

    def test_roundtrip(self):
        assert pt_to_mm(mm_to_pt(100.0)) == pytest.approx(100.0, rel=0.001)


class TestMmIn:
    def test_mm_to_in(self):
        assert mm_to_in(25.4) == pytest.approx(1.0, rel=0.001)

    def test_in_to_mm(self):
        assert in_to_mm(1.0) == pytest.approx(25.4, rel=0.001)

    def test_roundtrip(self):
        assert in_to_mm(mm_to_in(210.0)) == pytest.approx(210.0, rel=0.001)


class TestPtIn:
    def test_pt_to_in(self):
        assert pt_to_in(72.0) == pytest.approx(1.0, rel=0.001)

    def test_in_to_pt(self):
        assert in_to_pt(1.0) == pytest.approx(72.0, rel=0.001)


class TestPixels:
    def test_px_to_mm_at_96dpi(self):
        # At 96 DPI, 96 pixels = 1 inch = 25.4mm
        assert px_to_mm(96, 96) == pytest.approx(25.4, rel=0.01)

    def test_mm_to_px_at_96dpi(self):
        assert mm_to_px(25.4, 96) == pytest.approx(96.0, rel=0.01)

    def test_px_to_mm_zero_dpi(self):
        assert px_to_mm(100, 0) == 0.0

    def test_px_to_pt(self):
        # At 72 DPI, 72 pixels = 72 points
        assert px_to_pt(72, 72) == pytest.approx(72.0, rel=0.001)

    def test_pt_to_px(self):
        assert pt_to_px(72, 72) == pytest.approx(72.0, rel=0.001)

    def test_px_to_pt_zero_dpi(self):
        assert px_to_pt(100, 0) == 0.0
