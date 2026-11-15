"""Tests for page, side and sheet counting — the numbers shown before printing."""

from printforge.config.print_settings import PrintSettings, DuplexMode, PageRangeMode
from printforge.documents.base import DocumentFactory
from printforge.documents.layout_engine import LayoutEngine, PageCount
from printforge.documents.print_prep import PrintPreparer


class TestPageIndices:
    def test_all_pages(self):
        assert LayoutEngine().get_page_indices(3, PrintSettings()) == [0, 1, 2]

    def test_current_page(self):
        settings = PrintSettings(page_range_mode=PageRangeMode.CURRENT, current_page=2)
        assert LayoutEngine().get_page_indices(5, settings) == [1]

    def test_current_page_clamped_to_document(self):
        settings = PrintSettings(page_range_mode=PageRangeMode.CURRENT, current_page=9)
        assert LayoutEngine().get_page_indices(3, settings) == [2]

    def test_custom_range(self):
        settings = PrintSettings(page_range_mode=PageRangeMode.CUSTOM, page_range_str="1-2, 5")
        assert LayoutEngine().get_page_indices(6, settings) == [0, 1, 4]

    def test_custom_range_outside_document(self):
        settings = PrintSettings(page_range_mode=PageRangeMode.CUSTOM, page_range_str="4-6")
        assert LayoutEngine().get_page_indices(3, settings) is None

    def test_images_ignore_the_range(self):
        settings = PrintSettings(page_range_mode=PageRangeMode.CUSTOM, page_range_str="4-6")
        assert LayoutEngine().get_page_indices(1, settings, ranged=False) == [0]


class TestCountPages:
    def test_plain(self):
        assert LayoutEngine().count_pages(5, PrintSettings()) == PageCount(pages=5, sides=5, sheets=5, copies=1)

    def test_two_sided_rounds_up(self):
        count = LayoutEngine().count_pages(5, PrintSettings(duplex=DuplexMode.LONG_EDGE))
        assert (count.pages, count.sides, count.sheets) == (5, 5, 3)

    def test_copies_each_start_on_a_new_sheet(self):
        count = LayoutEngine().count_pages(3, PrintSettings(duplex=DuplexMode.LONG_EDGE, copies=2))
        assert count.sheets == 2
        assert count.total_sheets == 4
        assert count.total_sides == 6

    def test_pages_per_sheet(self):
        count = LayoutEngine().count_pages(9, PrintSettings(pages_per_sheet=4))
        assert (count.pages, count.sides, count.sheets) == (9, 3, 3)

    def test_pages_per_sheet_and_two_sided(self):
        count = LayoutEngine().count_pages(9, PrintSettings(pages_per_sheet=2, duplex=DuplexMode.SHORT_EDGE))
        assert (count.sides, count.sheets) == (5, 3)

    def test_range_limits_the_count(self):
        settings = PrintSettings(page_range_mode=PageRangeMode.CUSTOM, page_range_str="2-3", copies=3)
        count = LayoutEngine().count_pages(10, settings)
        assert count.pages == 2
        assert count.total_sheets == 6

    def test_invalid_range_counts_nothing(self):
        settings = PrintSettings(page_range_mode=PageRangeMode.CUSTOM, page_range_str="8-9")
        assert LayoutEngine().count_pages(3, settings).pages == 0

    def test_empty_document(self):
        assert LayoutEngine().count_pages(0, PrintSettings()).total_sheets == 0


class TestCountDocument:
    def test_missing_document(self):
        assert LayoutEngine().count_document(None, PrintSettings(copies=2)) == PageCount(copies=2)

    def test_pdf(self, sample_pdf_file):
        doc = DocumentFactory.create(sample_pdf_file)
        count = LayoutEngine().count_document(doc, PrintSettings(duplex=DuplexMode.LONG_EDGE))
        assert (count.pages, count.sheets) == (3, 2)

    def test_image_prints_whole_despite_range(self, sample_image_file):
        doc = DocumentFactory.create(sample_image_file)
        settings = PrintSettings(page_range_mode=PageRangeMode.CUSTOM, page_range_str="2-3")
        assert LayoutEngine().count_document(doc, settings).pages == 1

    def test_text_repaginates_for_the_paper(self, sample_text_file):
        doc = DocumentFactory.create(sample_text_file)
        engine = LayoutEngine()
        on_a4 = engine.count_document(doc, PrintSettings(paper_size_name="A4")).pages
        on_a5 = engine.count_document(doc, PrintSettings(paper_size_name="A5")).pages
        assert on_a5 > on_a4

    def test_count_matches_what_gets_printed(self, sample_text_file, tmp_dir):
        """The count shown must be the number of pages in the file sent to the printer."""
        import os
        from printforge.documents.pdf_doc import PdfDocument

        doc = DocumentFactory.create(sample_text_file)
        for paper in ("A4", "A5", "Legal"):
            settings = PrintSettings(paper_size_name=paper)
            expected = LayoutEngine().count_document(doc, settings).pages
            output = os.path.join(tmp_dir, f"{paper}.pdf")
            assert PrintPreparer().prepare_to_file(doc, settings, output)
            printed = PdfDocument(output)
            printed.load()
            assert printed.page_count == expected

    def test_custom_paper_size_is_used(self):
        settings = PrintSettings(paper_size_name="Custom", custom_paper_width_mm=100, custom_paper_height_mm=150)
        paper = LayoutEngine().get_paper_size(settings)
        assert (paper.width_mm, paper.height_mm) == (100, 150)
