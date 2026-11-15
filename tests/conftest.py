"""Pytest configuration and shared fixtures."""

import os
import sys
import tempfile
import pytest


@pytest.fixture
def tmp_dir():
    """Provide a temporary directory for test files."""
    with tempfile.TemporaryDirectory(prefix="printforge_test_") as d:
        yield d


@pytest.fixture
def sample_text_file(tmp_dir):
    """Create a sample text file."""
    path = os.path.join(tmp_dir, "sample.txt")
    with open(path, "w") as f:
        for i in range(100):
            f.write(f"Line {i + 1}: This is a test line with some content.\n")
    return path


@pytest.fixture
def sample_image_file(tmp_dir):
    """Create a sample PNG image file using Pillow."""
    try:
        from PIL import Image
        path = os.path.join(tmp_dir, "sample.png")
        img = Image.new("RGB", (1920, 1080), color=(100, 150, 200))
        img.save(path, "PNG")
        return path
    except ImportError:
        pytest.skip("Pillow not available")


@pytest.fixture
def sample_jpeg_file(tmp_dir):
    """Create a sample JPEG image file."""
    try:
        from PIL import Image
        path = os.path.join(tmp_dir, "sample.jpg")
        img = Image.new("RGB", (800, 600), color=(200, 100, 50))
        img.save(path, "JPEG")
        return path
    except ImportError:
        pytest.skip("Pillow not available")


@pytest.fixture
def sample_pdf_file(tmp_dir):
    """Create a sample PDF file using Cairo."""
    try:
        import cairo
        path = os.path.join(tmp_dir, "sample.pdf")
        surface = cairo.PDFSurface(path, 595, 842)  # A4
        ctx = cairo.Context(surface)
        ctx.set_source_rgb(0, 0, 0)
        ctx.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        ctx.set_font_size(24)
        ctx.move_to(50, 100)
        ctx.show_text("PrintForge Test PDF - Page 1")
        surface.show_page()
        ctx.move_to(50, 100)
        ctx.show_text("PrintForge Test PDF - Page 2")
        surface.show_page()
        ctx.move_to(50, 100)
        ctx.show_text("PrintForge Test PDF - Page 3")
        surface.show_page()
        surface.finish()
        return path
    except ImportError:
        pytest.skip("PyCairo not available")


@pytest.fixture
def sample_ps_file(tmp_dir):
    """Create a sample PostScript file."""
    path = os.path.join(tmp_dir, "sample.ps")
    with open(path, "w") as f:
        f.write("%!PS-Adobe-3.0\n"
                "%%BoundingBox: 0 0 595 842\n"
                "/Helvetica findfont 24 scalefont setfont\n"
                "100 700 moveto\n"
                "(PrintForge PostScript Test Document) show\n"
                "showpage\n")
    return path


@pytest.fixture
def sample_markdown_file(tmp_dir):
    """Create a sample Markdown file."""
    path = os.path.join(tmp_dir, "sample.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Heading Level 1\n\n"
                "## Section 2\n\n"
                "This is a paragraph with **formatted** text and details.\n\n"
                "- First item\n"
                "- Second item with details\n"
                "- Third item\n\n"
                "> Blockquote note here\n\n"
                "```python\n"
                "def hello():\n"
                "    print('Hello PrintForge')\n"
                "```\n")
    return path


@pytest.fixture
def sample_code_file(tmp_dir):
    """Create a sample Python code file."""
    path = os.path.join(tmp_dir, "sample.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write("#!/usr/bin/env python3\n"
                '"""Sample script for PrintForge code printing."""\n\n'
                "import os\n"
                "import sys\n\n"
                "def compute_stats(values: list[float]) -> dict:\n"
                "    total = sum(values)\n"
                "    count = len(values)\n"
                "    return {'total': total, 'mean': total / max(1, count)}\n\n"
                'if __name__ == "__main__":\n'
                "    data = [10.5, 20.0, 30.5]\n"
                "    print(compute_stats(data))\n")
    return path


@pytest.fixture
def sample_rtf_file(tmp_dir):
    """Create a sample RTF office document."""
    path = os.path.join(tmp_dir, "sample.rtf")
    with open(path, "w", encoding="utf-8") as f:
        f.write(r"{\rtf1\ansi\deff0{\fonttbl{\f0 Arial;}}\f0\fs24 PrintForge Office Document Test\par Second line with text.}")
    return path


@pytest.fixture
def sample_bmp_file(tmp_dir):
    """Create a sample BMP image file."""
    try:
        from PIL import Image
        path = os.path.join(tmp_dir, "sample.bmp")
        img = Image.new("RGB", (400, 300), color=(80, 160, 240))
        img.save(path, "BMP")
        return path
    except ImportError:
        pytest.skip("Pillow not available")


@pytest.fixture
def sample_tiff_file(tmp_dir):
    """Create a sample TIFF image file."""
    try:
        from PIL import Image
        path = os.path.join(tmp_dir, "sample.tiff")
        img = Image.new("RGB", (600, 400), color=(240, 120, 80))
        img.save(path, "TIFF")
        return path
    except ImportError:
        pytest.skip("Pillow not available")

