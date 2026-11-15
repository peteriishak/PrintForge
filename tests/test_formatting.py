"""Tests for formatting and parsing utilities."""

import pytest
from printforge.utils.formatting import (
    format_file_size, format_dimensions,
    parse_page_range, format_page_range, validate_copies,
)


class TestFormatFileSize:
    def test_bytes(self):
        assert format_file_size(512) == "512 B"

    def test_zero(self):
        assert format_file_size(0) == "0 B"

    def test_negative(self):
        assert format_file_size(-1) == "0 B"

    def test_kilobytes(self):
        result = format_file_size(1536)
        assert "KB" in result

    def test_megabytes(self):
        result = format_file_size(2621440)
        assert "MB" in result

    def test_gigabytes(self):
        result = format_file_size(5 * 1024**3)
        assert "GB" in result

    def test_exact_kb(self):
        assert "1.00 KB" == format_file_size(1024)


class TestFormatDimensions:
    def test_pixels(self):
        assert format_dimensions(1920, 1080) == "1920 × 1080 px"

    def test_mm(self):
        assert format_dimensions(210, 297, "mm") == "210 × 297 mm"


class TestParsePageRange:
    def test_single_page(self):
        assert parse_page_range("1", 10) == [1]

    def test_range(self):
        assert parse_page_range("1-3", 10) == [1, 2, 3]

    def test_complex(self):
        assert parse_page_range("1-3, 5, 8-10", 10) == [1, 2, 3, 5, 8, 9, 10]

    def test_single_pages(self):
        assert parse_page_range("1,3,5", 10) == [1, 3, 5]

    def test_with_spaces(self):
        assert parse_page_range("1 - 3, 5, 8 - 10", 10) == [1, 2, 3, 5, 8, 9, 10]

    def test_empty(self):
        assert parse_page_range("", 10) is None

    def test_invalid_text(self):
        assert parse_page_range("abc", 10) is None

    def test_out_of_range(self):
        assert parse_page_range("11", 10) is None

    def test_zero_page(self):
        assert parse_page_range("0", 10) is None

    def test_reversed_range(self):
        assert parse_page_range("5-3", 10) is None

    def test_exceeds_max(self):
        assert parse_page_range("1-20", 10) is None

    def test_duplicates_removed(self):
        result = parse_page_range("1,1,2,2,3", 10)
        assert result == [1, 2, 3]

    def test_negative_page(self):
        assert parse_page_range("-1", 10) is None


class TestFormatPageRange:
    def test_single(self):
        assert format_page_range([1]) == "1"

    def test_range(self):
        assert format_page_range([1, 2, 3]) == "1-3"

    def test_complex(self):
        assert format_page_range([1, 2, 3, 5, 8, 9, 10]) == "1-3, 5, 8-10"

    def test_empty(self):
        assert format_page_range([]) == ""

    def test_non_contiguous(self):
        assert format_page_range([1, 3, 5, 7]) == "1, 3, 5, 7"


class TestValidateCopies:
    def test_valid(self):
        assert validate_copies("1") == 1
        assert validate_copies("10") == 10
        assert validate_copies("999") == 999

    def test_invalid(self):
        assert validate_copies("0") is None
        assert validate_copies("-1") is None
        assert validate_copies("1000") is None
        assert validate_copies("abc") is None
        assert validate_copies("") is None
