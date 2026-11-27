"""Tests for document processing modules."""

import os
import pytest

from printforge.documents.base import (
    Document, DocumentFactory, is_supported, get_file_type,
    SUPPORTED_EXTENSIONS,
)


class TestFileTypeDetection:
    def test_png_supported(self):
        assert is_supported("photo.png") is True
        assert is_supported("PHOTO.PNG") is True

    def test_jpeg_supported(self):
        assert is_supported("photo.jpg") is True
        assert is_supported("photo.jpeg") is True

    def test_pdf_supported(self):
        assert is_supported("doc.pdf") is True

    def test_txt_supported(self):
        assert is_supported("readme.txt") is True

    def test_svg_supported(self):
        assert is_supported("icon.svg") is True

    def test_webp_supported(self):
        assert is_supported("image.webp") is True

    def test_unsupported(self):
        assert is_supported("archive.zip") is False
        assert is_supported("video.mp4") is False
        assert is_supported("music.mp3") is False
        assert is_supported("binary.bin") is False

    def test_office_supported(self):
        for ext in (".odt", ".docx", ".doc", ".rtf", ".ods", ".xlsx", ".xls", ".odp", ".pptx", ".ppt"):
            assert is_supported(f"file{ext}") is True
            assert get_file_type(f"file{ext}") == "office"

    def test_postscript_supported(self):
        for ext in (".ps", ".eps"):
            assert is_supported(f"graphic{ext}") is True
            assert get_file_type(f"graphic{ext}") == "postscript"

    def test_markdown_and_code_supported(self):
        for ext in (".md", ".markdown", ".py", ".sh", ".c", ".cpp", ".rs", ".go", ".js", ".ts", ".json", ".yaml", ".toml"):
            assert is_supported(f"source{ext}") is True
            assert get_file_type(f"source{ext}") == "text"

    def test_extended_images_supported(self):
        for ext in (".bmp", ".tiff", ".tif", ".gif", ".ico", ".tga", ".ppm", ".webp"):
            assert is_supported(f"picture{ext}") is True
            assert get_file_type(f"picture{ext}") == "image"

    def test_get_file_type(self):
        assert get_file_type("photo.png") == "image"
        assert get_file_type("doc.pdf") == "pdf"
        assert get_file_type("note.txt") == "text"
        assert get_file_type("icon.svg") == "svg"
        assert get_file_type("doc.odt") == "office"
        assert get_file_type("drawing.ps") == "postscript"
        assert get_file_type("script.py") == "text"
        assert get_file_type("file.xyz") is None


class TestDocumentFactory:
    def test_create_text(self, sample_text_file):
        doc = DocumentFactory.create(sample_text_file)
        assert doc is not None
        assert doc.is_valid
        assert doc.file_type == "text"
        assert doc.page_count >= 1

    def test_create_markdown(self, sample_markdown_file):
        doc = DocumentFactory.create(sample_markdown_file)
        assert doc is not None
        assert doc.is_valid
        assert doc.file_type == "text"
        assert doc.page_count >= 1

    def test_create_code(self, sample_code_file):
        doc = DocumentFactory.create(sample_code_file)
        assert doc is not None
        assert doc.is_valid
        assert doc.file_type == "text"
        assert doc.page_count >= 1

    def test_create_image(self, sample_image_file):
        doc = DocumentFactory.create(sample_image_file)
        assert doc is not None
        assert doc.is_valid
        assert doc.file_type == "image"
        assert doc.page_count == 1
        w, h = doc.dimensions
        assert w == 1920
        assert h == 1080

    def test_create_pdf(self, sample_pdf_file):
        doc = DocumentFactory.create(sample_pdf_file)
        if doc is None:
            pytest.skip("Poppler not available")
        assert doc.is_valid
        assert doc.file_type == "pdf"
        assert doc.page_count == 3

    def test_create_postscript(self, sample_ps_file):
        doc = DocumentFactory.create(sample_ps_file)
        if doc is None or not doc.is_valid:
            pytest.skip("Ghostscript not available")
        assert doc.is_valid
        assert doc.file_type == "postscript"
        assert doc.page_count >= 1

    def test_create_office(self, sample_rtf_file):
        doc = DocumentFactory.create(sample_rtf_file)
        if doc is None or not doc.is_valid:
            pytest.skip("LibreOffice not available")
        assert doc.is_valid
        assert doc.file_type == "office"
        assert doc.page_count >= 1

    def test_create_unsupported(self, tmp_dir):
        path = os.path.join(tmp_dir, "test.xyz")
        with open(path, "w") as f:
            f.write("data")
        doc = DocumentFactory.create(path)
        assert doc is None

    def test_create_nonexistent(self):
        doc = DocumentFactory.create("/nonexistent/file.png")
        if doc:
            assert not doc.is_valid


class TestImageDocument:
    def test_dimensions(self, sample_image_file):
        doc = DocumentFactory.create(sample_image_file)
        assert doc is not None
        w, h = doc.dimensions
        assert w == 1920
        assert h == 1080

    def test_render(self, sample_image_file):
        doc = DocumentFactory.create(sample_image_file)
        assert doc is not None
        surface = doc.render_page(0, 200, 150)
        assert surface is not None
        assert surface.get_width() == 200
        assert surface.get_height() == 150

    def test_file_info(self, sample_image_file):
        doc = DocumentFactory.create(sample_image_file)
        assert doc is not None
        assert doc.filename == "sample.png"
        assert doc.file_size > 0
        assert doc.is_image is True


class TestExtendedImageFormats:
    def test_bmp_document(self, sample_bmp_file):
        doc = DocumentFactory.create(sample_bmp_file)
        assert doc is not None and doc.is_valid
        assert doc.file_type == "image"
        w, h = doc.dimensions
        assert w == 400
        assert h == 300
        surface = doc.render_page(0, 200, 150)
        assert surface is not None

    def test_tiff_document(self, sample_tiff_file):
        doc = DocumentFactory.create(sample_tiff_file)
        assert doc is not None and doc.is_valid
        assert doc.file_type == "image"
        w, h = doc.dimensions
        assert w == 600
        assert h == 400
        surface = doc.render_page(0, 300, 200)
        assert surface is not None


class TestTextDocument:
    def test_load(self, sample_text_file):
        doc = DocumentFactory.create(sample_text_file)
        assert doc is not None
        assert doc.is_valid
        assert doc.page_count >= 1

    def test_render(self, sample_text_file):
        doc = DocumentFactory.create(sample_text_file)
        assert doc is not None
        surface = doc.render_page(0, 595, 842)
        assert surface is not None

    def test_pagination(self, sample_text_file):
        doc = DocumentFactory.create(sample_text_file)
        assert doc is not None
        assert doc.page_count >= 2

    def test_markdown_document(self, sample_markdown_file):
        doc = DocumentFactory.create(sample_markdown_file)
        assert doc is not None and doc.is_valid
        surface = doc.render_page(0, 595, 842)
        assert surface is not None

    def test_code_document_syntax_highlighting(self, sample_code_file):
        doc = DocumentFactory.create(sample_code_file)
        assert doc is not None and doc.is_valid
        assert doc.show_line_numbers is True
        surface = doc.render_page(0, 595, 842)
        assert surface is not None

    def test_text_document_scaling(self, sample_text_file):
        doc = DocumentFactory.create(sample_text_file)
        assert doc is not None and doc.is_valid
        initial_pages = doc.page_count
        initial_font_size = doc.font_size
        # Scale to 150%
        doc.set_scale(150.0)
        assert doc.font_size > initial_font_size
        # Larger font size should mean fewer lines per page -> more pages
        assert doc.page_count >= initial_pages


class TestPostScriptDocument:
    def test_load_and_render_ps(self, sample_ps_file):
        doc = DocumentFactory.create(sample_ps_file)
        if doc is None or not doc.is_valid:
            pytest.skip("Ghostscript not available")
        assert doc.is_valid
        assert doc.page_count >= 1
        assert doc.file_type == "postscript"
        w, h = doc.dimensions
        assert w > 0 and h > 0
        surface = doc.render_page(0, 595, 842)
        assert surface is not None


class TestOfficeDocument:
    def test_load_and_render_rtf(self, sample_rtf_file):
        doc = DocumentFactory.create(sample_rtf_file)
        if doc is None or not doc.is_valid:
            pytest.skip("LibreOffice not available")
        assert doc.is_valid
        assert doc.page_count >= 1
        assert doc.file_type == "office"
        w, h = doc.dimensions
        assert w > 0 and h > 0
        surface = doc.render_page(0, 595, 842)
        assert surface is not None


class TestPdfDocument:
    def test_load(self, sample_pdf_file):
        doc = DocumentFactory.create(sample_pdf_file)
        if doc is None:
            pytest.skip("Poppler not available")
        assert doc.is_valid
        assert doc.page_count == 3

    def test_render(self, sample_pdf_file):
        doc = DocumentFactory.create(sample_pdf_file)
        if doc is None:
            pytest.skip("Poppler not available")
        surface = doc.render_page(0, 595, 842)
        assert surface is not None

    def test_render_invalid_page(self, sample_pdf_file):
        doc = DocumentFactory.create(sample_pdf_file)
        if doc is None:
            pytest.skip("Poppler not available")
        surface = doc.render_page(99, 595, 842)
        assert surface is None


def _rsvg_available() -> bool:
    try:
        import gi
        gi.require_version("Rsvg", "2.0")
        from gi.repository import Rsvg  # noqa: F401
        return True
    except (ImportError, ValueError):
        return False


@pytest.mark.skipif(not _rsvg_available(), reason="librsvg not available")
class TestSvgDocument:
    @pytest.fixture
    def sample_svg_file(self, tmp_dir):
        path = os.path.join(tmp_dir, "sample.svg")
        with open(path, "w") as f:
            f.write('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">'
                    '<rect width="200" height="100" fill="teal"/></svg>')
        return path

    def test_load_uses_intrinsic_size(self, sample_svg_file):
        doc = DocumentFactory.create(sample_svg_file)
        assert doc is not None and doc.is_valid
        assert doc.page_count == 1
        assert doc.dimensions == (200.0, 100.0)

    def test_render(self, sample_svg_file):
        doc = DocumentFactory.create(sample_svg_file)
        assert doc is not None
        assert doc.render_page(0, 595, 842) is not None
