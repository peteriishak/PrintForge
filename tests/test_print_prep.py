"""Tests for print file preparation (PrintPreparer)."""

import os
import pytest

from printforge.config.print_settings import (
    PrintSettings, Orientation, ScalingMode, Position, PageRangeMode,
)
from printforge.documents.base import DocumentFactory
from printforge.documents.print_prep import PrintPreparer


class TestPrintPreparer:
    def test_prepare_image(self, sample_image_file):
        doc = DocumentFactory.create(sample_image_file)
        assert doc is not None and doc.is_valid

        preparer = PrintPreparer()
        settings = PrintSettings()
        pdf_path = preparer.prepare(doc, settings)

        assert pdf_path is not None
        assert os.path.exists(pdf_path)
        assert os.path.getsize(pdf_path) > 0
        assert pdf_path.endswith(".pdf")

        preparer.cleanup()
        assert not os.path.exists(pdf_path)

    def test_prepare_image_landscape(self, sample_image_file):
        doc = DocumentFactory.create(sample_image_file)
        preparer = PrintPreparer()
        settings = PrintSettings(orientation=Orientation.LANDSCAPE)
        pdf_path = preparer.prepare(doc, settings)

        assert pdf_path is not None
        assert os.path.exists(pdf_path)
        preparer.cleanup()

    def test_prepare_text(self, sample_text_file):
        doc = DocumentFactory.create(sample_text_file)
        assert doc is not None and doc.is_valid

        preparer = PrintPreparer()
        settings = PrintSettings()
        pdf_path = preparer.prepare(doc, settings)

        assert pdf_path is not None
        assert os.path.exists(pdf_path)
        assert os.path.getsize(pdf_path) > 0

        preparer.cleanup()
        assert not os.path.exists(pdf_path)

    def test_prepare_pdf_all_pages(self, sample_pdf_file):
        doc = DocumentFactory.create(sample_pdf_file)
        if doc is None or not doc.is_valid:
            pytest.skip("Poppler not available")

        preparer = PrintPreparer()
        settings = PrintSettings()
        pdf_path = preparer.prepare(doc, settings)

        # For all pages, it returns the original file path
        assert pdf_path == sample_pdf_file

    def test_prepare_pdf_page_range(self, sample_pdf_file):
        doc = DocumentFactory.create(sample_pdf_file)
        if doc is None or not doc.is_valid:
            pytest.skip("Poppler not available")

        preparer = PrintPreparer()
        settings = PrintSettings(
            page_range_mode=PageRangeMode.CUSTOM,
            page_range_str="1, 3",
        )
        pdf_path = preparer.prepare(doc, settings)

        assert pdf_path is not None
        assert os.path.exists(pdf_path)
        assert pdf_path != sample_pdf_file

        preparer.cleanup()
        assert not os.path.exists(pdf_path)

    def test_prepare_markdown(self, sample_markdown_file):
        doc = DocumentFactory.create(sample_markdown_file)
        assert doc is not None and doc.is_valid

        preparer = PrintPreparer()
        settings = PrintSettings()
        pdf_path = preparer.prepare(doc, settings)

        assert pdf_path is not None
        assert os.path.exists(pdf_path)
        assert os.path.getsize(pdf_path) > 0
        preparer.cleanup()
        assert not os.path.exists(pdf_path)

    def test_prepare_code(self, sample_code_file):
        doc = DocumentFactory.create(sample_code_file)
        assert doc is not None and doc.is_valid

        preparer = PrintPreparer()
        settings = PrintSettings()
        pdf_path = preparer.prepare(doc, settings)

        assert pdf_path is not None
        assert os.path.exists(pdf_path)
        assert os.path.getsize(pdf_path) > 0
        preparer.cleanup()
        assert not os.path.exists(pdf_path)

    def test_prepare_postscript(self, sample_ps_file):
        doc = DocumentFactory.create(sample_ps_file)
        if doc is None or not doc.is_valid:
            pytest.skip("Ghostscript not available")

        preparer = PrintPreparer()
        settings = PrintSettings()
        pdf_path = preparer.prepare(doc, settings)

        assert pdf_path is not None
        assert os.path.exists(pdf_path)
        assert os.path.getsize(pdf_path) > 0
        preparer.cleanup()
        assert not os.path.exists(pdf_path)

    def test_prepare_office(self, sample_rtf_file):
        doc = DocumentFactory.create(sample_rtf_file)
        if doc is None or not doc.is_valid:
            pytest.skip("LibreOffice not available")

        preparer = PrintPreparer()
        settings = PrintSettings()
        pdf_path = preparer.prepare(doc, settings)

        assert pdf_path is not None
        assert os.path.exists(pdf_path)
        assert os.path.getsize(pdf_path) > 0
        preparer.cleanup()
        assert not os.path.exists(pdf_path)

    def test_export_office_to_file(self, sample_rtf_file, tmp_dir):
        doc = DocumentFactory.create(sample_rtf_file)
        if doc is None or not doc.is_valid:
            pytest.skip("LibreOffice not available")

        preparer = PrintPreparer()
        settings = PrintSettings()
        out_path = os.path.join(tmp_dir, "exported_office.pdf")
        success = preparer.prepare_to_file(doc, settings, out_path)

        assert success is True
        assert os.path.exists(out_path)
        assert os.path.getsize(out_path) > 0

    def test_prepare_invalid_document(self):
        preparer = PrintPreparer()
        settings = PrintSettings()
        assert preparer.prepare(None, settings) is None

    def test_prepare_unsupported_document(self, tmp_dir):
        path = os.path.join(tmp_dir, "unsupported.xyz")
        with open(path, "w") as f:
            f.write("test")

        doc = DocumentFactory.create(path)
        preparer = PrintPreparer()
        settings = PrintSettings()
        assert preparer.prepare(doc, settings) is None

    def test_prepare_resolutions_image(self, sample_image_file, tmp_dir):
        doc = DocumentFactory.create(sample_image_file)
        assert doc is not None and doc.is_valid

        preparer = PrintPreparer()
        for res_val in ("300x300dpi", "600x600dpi", "1200x1200dpi"):
            settings = PrintSettings(resolution=res_val)
            out_file = os.path.join(tmp_dir, f"test_{res_val}.pdf")
            success = preparer.prepare_to_file(doc, settings, out_file)
            assert success is True
            assert os.path.exists(out_file)
            assert os.path.getsize(out_file) > 0

    def test_prepare_resolutions_text(self, sample_text_file, tmp_dir):
        doc = DocumentFactory.create(sample_text_file)
        assert doc is not None and doc.is_valid

        preparer = PrintPreparer()
        for res_val in ("300x300dpi", "600x600dpi", "1200x1200dpi"):
            settings = PrintSettings(resolution=res_val)
            out_file = os.path.join(tmp_dir, f"test_text_{res_val}.pdf")
            success = preparer.prepare_to_file(doc, settings, out_file)
            assert success is True
            assert os.path.exists(out_file)
            assert os.path.getsize(out_file) > 0


