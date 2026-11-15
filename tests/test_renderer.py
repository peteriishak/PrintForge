"""Tests for the layout renderer."""

import pytest
from printforge.documents.renderer import LayoutRenderer
from printforge.config.print_settings import (
    PrintSettings, Orientation, ScalingMode, Position, Margins, MarginPreset,
)


class TestLayoutRenderer:
    def test_get_paper_size_portrait(self):
        renderer = LayoutRenderer()
        settings = PrintSettings(paper_size_name="A4", orientation=Orientation.PORTRAIT)
        paper = renderer.get_paper_size(settings)
        assert paper.width_mm == 210
        assert paper.height_mm == 297

    def test_get_paper_size_landscape(self):
        renderer = LayoutRenderer()
        settings = PrintSettings(paper_size_name="A4", orientation=Orientation.LANDSCAPE)
        paper = renderer.get_paper_size(settings)
        assert paper.width_mm == 297
        assert paper.height_mm == 210

    def test_estimate_pages_none(self):
        renderer = LayoutRenderer()
        settings = PrintSettings()
        assert renderer.estimate_pages(None, settings) == 0

    def test_estimate_pages_single(self, sample_image_file):
        from printforge.documents.base import DocumentFactory
        renderer = LayoutRenderer()
        doc = DocumentFactory.create(sample_image_file)
        settings = PrintSettings()
        assert renderer.estimate_pages(doc, settings) == 1

    def test_estimate_pages_nup(self, sample_pdf_file):
        from printforge.documents.base import DocumentFactory
        renderer = LayoutRenderer()
        doc = DocumentFactory.create(sample_pdf_file)
        if doc is None:
            pytest.skip("Poppler not available")
        settings = PrintSettings(pages_per_sheet=2)
        sheets = renderer.estimate_pages(doc, settings)
        assert sheets == 2  # 3 pages / 2 per sheet = 2 sheets

    def test_render_preview_empty(self):
        renderer = LayoutRenderer()
        settings = PrintSettings()
        surface = renderer.render_preview(None, settings, 0, 600, 800)
        assert surface is not None

    def test_render_preview_with_image(self, sample_image_file):
        from printforge.documents.base import DocumentFactory
        renderer = LayoutRenderer()
        doc = DocumentFactory.create(sample_image_file)
        settings = PrintSettings()
        surface = renderer.render_preview(doc, settings, 0, 600, 800)
        assert surface is not None
        assert surface.get_width() == 600
        assert surface.get_height() == 800

    def test_render_preview_zero_size(self):
        renderer = LayoutRenderer()
        settings = PrintSettings()
        surface = renderer.render_preview(None, settings, 0, 0, 0)
        assert surface is None

    def test_nup_grid(self):
        from printforge.documents.layout_engine import LayoutEngine
        assert LayoutEngine._get_nup_grid(1) == (1, 1)
        assert LayoutEngine._get_nup_grid(2) == (2, 1)
        assert LayoutEngine._get_nup_grid(4) == (2, 2)
        assert LayoutEngine._get_nup_grid(6) == (3, 2)
        assert LayoutEngine._get_nup_grid(9) == (3, 3)
        assert LayoutEngine._get_nup_grid(16) == (4, 4)

    def test_invalidate_cache(self):
        renderer = LayoutRenderer()
        renderer._cache["test"] = "value"
        renderer.invalidate_cache()
        assert len(renderer._cache) == 0


class TestPreviewWidget:
    def test_preview_widget_zoom_and_expand(self):
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw
        Adw.init()
        from printforge.ui.preview import PreviewWidget
        from printforge.config.print_settings import PrintSettings

        pw = PreviewWidget()
        assert pw.MAX_ZOOM == 10.0
        assert pw.MIN_ZOOM == 0.25

        # Test zoom in up to 1000%
        pw._zoom_by(5.0)
        assert pw._zoom == 6.0
        pw._zoom_by(10.0)
        assert pw._zoom == 10.0  # Clamped to 10.0 (1000%)
        assert pw._zoom_label.get_text() == "1000%"

        # Test zoom fit
        pw._zoom_fit()
        assert pw._zoom == 1.0
        assert pw._zoom_label.get_text() == "100%"

        # Test touchpad gesture zoom
        pw._on_zoom_gesture_begin(None, None)
        pw._on_zoom_gesture_scale_changed(None, 2.5)
        assert pw._zoom == 2.5
        assert pw._zoom_label.get_text() == "250%"

        # Test expand / collapse toggle
        expanded_states = []
        pw.connect("expand-toggled", lambda w, exp: expanded_states.append(exp))
        pw._on_expand_clicked(None)
        assert pw._is_expanded is True
        assert expanded_states == [True]
        pw._on_expand_clicked(None)
        assert pw._is_expanded is False
        assert expanded_states == [True, False]

        # Test paper label with DPI and Scale
        settings = PrintSettings(paper_size_name="A4", resolution="600x600dpi", scaling_value=150.0)
        pw.set_settings(settings)
        label_text = pw._paper_label.get_text()
        assert "A4" in label_text
        assert "600 DPI" in label_text
        assert "150%" in label_text

