"""Tests for print preflight validation."""

import pytest
from unittest.mock import MagicMock

from printforge.config.print_settings import PrintSettings, ColorMode, DuplexMode, Margins, PageRangeMode
from printforge.printing.preflight import PreflightChecker, Severity
from printforge.printing.printer import PrinterInfo, PrinterState
from printforge.printing.capabilities import PrinterCapabilities


class TestPreflightChecker:
    def test_no_documents(self):
        result = PreflightChecker.check([], PrintSettings())
        assert not result.is_valid
        assert any(i.field_name == "documents" for i in result.errors)

    def test_valid_document(self):
        doc = MagicMock()
        doc.page_count = 5
        doc.is_valid = True
        doc.filename = "doc.pdf"
        del doc.width_px  # Not an image

        result = PreflightChecker.check([doc], PrintSettings())
        assert result.is_valid
        assert not result.has_warnings

    def test_stopped_printer(self):
        doc = MagicMock(page_count=1, is_valid=True, filename="test.pdf")
        del doc.width_px
        printer = PrinterInfo(name="HP", state=PrinterState.STOPPED, is_accepting_jobs=False)

        result = PreflightChecker.check([doc], PrintSettings(), printer=printer)
        assert not result.is_valid
        assert any("stopped" in i.message.lower() for i in result.errors)

    def test_unsupported_duplex_warning(self):
        doc = MagicMock(page_count=2, is_valid=True, filename="test.pdf")
        del doc.width_px
        settings = PrintSettings(duplex=DuplexMode.LONG_EDGE)
        caps = PrinterCapabilities(printer_name="Test", supported_sides=["one-sided"])

        result = PreflightChecker.check([doc], settings, capabilities=caps)
        assert result.is_valid  # Still valid (non-blocking warning)
        assert result.has_warnings
        assert any(i.field_name == "duplex" for i in result.warnings)

    def test_unsupported_color_warning(self):
        doc = MagicMock(page_count=1, is_valid=True, filename="test.pdf")
        del doc.width_px
        settings = PrintSettings(color_mode=ColorMode.COLOR)
        caps = PrinterCapabilities(printer_name="MonoPrinter", supports_color=False)

        result = PreflightChecker.check([doc], settings, capabilities=caps)
        assert result.is_valid
        assert result.has_warnings
        assert any(i.field_name == "color_mode" for i in result.warnings)

    def test_borderless_unsupported_warning(self):
        doc = MagicMock(page_count=1, is_valid=True, filename="test.pdf")
        del doc.width_px
        settings = PrintSettings(margins=Margins(0, 0, 0, 0))
        caps = PrinterCapabilities(printer_name="Printer", supports_borderless=False)

        result = PreflightChecker.check([doc], settings, capabilities=caps)
        assert result.has_warnings
        assert any(i.field_name == "margins" for i in result.warnings)

    def test_zero_copies_error(self):
        doc = MagicMock(page_count=1, is_valid=True, filename="test.pdf")
        del doc.width_px
        settings = PrintSettings(copies=0)

        result = PreflightChecker.check([doc], settings)
        assert not result.is_valid
        assert any(i.field_name == "copies" for i in result.errors)


class TestPageRangeAcrossDocuments:
    def test_range_must_fit_every_document(self):
        from printforge.config.print_settings import PageRangeMode

        long_doc = MagicMock(page_count=10, is_valid=True, filename="long.pdf", is_image=False)
        short_doc = MagicMock(page_count=2, is_valid=True, filename="short.pdf", is_image=False)
        for doc in (long_doc, short_doc):
            del doc.width_px
        settings = PrintSettings(page_range_mode=PageRangeMode.CUSTOM, page_range_str="1-5")

        result = PreflightChecker.check([long_doc, short_doc], settings)

        assert [e.field_name for e in result.errors] == ["page_range"]
        assert "short.pdf" in result.errors[0].message

    def test_images_are_exempt_from_the_range(self):
        from printforge.config.print_settings import PageRangeMode

        pdf = MagicMock(page_count=10, is_valid=True, filename="long.pdf", is_image=False)
        image = MagicMock(page_count=1, is_valid=True, filename="photo.png", is_image=True, width_px=4000, height_px=3000)
        del pdf.width_px
        settings = PrintSettings(page_range_mode=PageRangeMode.CUSTOM, page_range_str="3-5")

        assert PreflightChecker.check([pdf, image], settings).is_valid
