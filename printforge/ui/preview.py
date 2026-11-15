"""Live print preview widget — first-class document preview.

Features:
- Paper simulation with shadow, margin guides, and content
- Zoom controls (in/out/fit/fit-width/actual-size)
- Page navigation with thumbnails for multi-page documents
- Pan support when zoomed in
- Empty state and loading state
- Real-time updates on settings changes
- Mouse wheel zoom
"""

from __future__ import annotations

import logging
import math
from typing import Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GObject, Pango

import cairo

from printforge.config.print_settings import PrintSettings, Orientation
from printforge.documents.base import Document
from printforge.documents.renderer import LayoutRenderer
from printforge.utils.paper import get_paper_by_name

log = logging.getLogger(__name__)

ORIENTATION_NAMES = {
    Orientation.PORTRAIT: "Portrait",
    Orientation.LANDSCAPE: "Landscape",
    Orientation.AUTO: "Automatic Orientation",
}


class PreviewWidget(Gtk.Box):
    """Live print preview showing how content will appear on paper.

    Occupies the majority of the right column in the two-column layout.
    """

    __gtype_name__ = "PrintForgePreview"

    __gsignals__ = {
        "page-changed": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
        "expand-toggled": (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
    }

    MIN_ZOOM: float = 0.25
    MAX_ZOOM: float = 10.0

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("preview-container")

        self._renderer = LayoutRenderer()
        self._document: Optional[Document] = None
        self._settings = PrintSettings()
        self._current_page: int = 0
        self._total_pages: int = 0
        self._zoom: float = 1.0
        self._gesture_start_zoom: float = 1.0
        self._pan_x: float = 0.0
        self._pan_y: float = 0.0
        self._is_panning: bool = False
        self._pan_start_x: float = 0.0
        self._pan_start_y: float = 0.0
        self._cached_surface: Optional[cairo.ImageSurface] = None
        self._is_expanded: bool = False

        self._build_ui()

    def _build_ui(self) -> None:
        # ── Stack for empty/preview states ────────────────────────────
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(200)
        self._stack.set_vexpand(True)
        self._stack.set_hexpand(True)
        self.append(self._stack)

        # ── Empty state ───────────────────────────────────────────────
        empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        empty_box.set_valign(Gtk.Align.CENTER)
        empty_box.set_halign(Gtk.Align.CENTER)
        empty_box.add_css_class("preview-empty")

        empty_icon = Gtk.Image.new_from_icon_name("document-print-preview-symbolic")
        empty_icon.set_pixel_size(64)
        empty_icon.set_opacity(0.3)
        empty_box.append(empty_icon)

        empty_title = Gtk.Label(label="No document selected")
        empty_title.add_css_class("title-4")
        empty_title.set_opacity(0.5)
        empty_box.append(empty_title)

        empty_subtitle = Gtk.Label(label="Add a file to see the print preview")
        empty_subtitle.add_css_class("dim-label")
        empty_box.append(empty_subtitle)

        self._stack.add_named(empty_box, "empty")

        # ── Loading state ─────────────────────────────────────────────
        loading_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        loading_box.set_valign(Gtk.Align.CENTER)
        loading_box.set_halign(Gtk.Align.CENTER)

        spinner = Gtk.Spinner()
        spinner.set_spinning(True)
        spinner.set_size_request(32, 32)
        loading_box.append(spinner)

        loading_label = Gtk.Label(label="Loading document…")
        loading_label.add_css_class("dim-label")
        loading_box.append(loading_label)

        self._stack.add_named(loading_box, "loading")

        # ── Preview content ───────────────────────────────────────────
        preview_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Paper info bar
        info_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        info_bar.add_css_class("preview-info-bar")

        preview_title = Gtk.Label(label="Preview")
        preview_title.add_css_class("heading")
        preview_title.set_halign(Gtk.Align.START)
        preview_title.set_hexpand(True)
        info_bar.append(preview_title)

        self._paper_label = Gtk.Label(label="A4 · Portrait", ellipsize=Pango.EllipsizeMode.END)
        self._paper_label.add_css_class("preview-paper-label")
        info_bar.append(self._paper_label)

        preview_box.append(info_bar)

        # Drawing area
        self._drawing_area = Gtk.DrawingArea()
        self._drawing_area.set_vexpand(True)
        self._drawing_area.set_hexpand(True)
        self._drawing_area.add_css_class("preview-drawing-area")
        self._drawing_area.set_draw_func(self._on_draw)

        # Scroll to zoom
        scroll_ctrl = Gtk.EventControllerScroll(
            flags=Gtk.EventControllerScrollFlags.VERTICAL
        )
        scroll_ctrl.connect("scroll", self._on_scroll)
        self._drawing_area.add_controller(scroll_ctrl)

        # Pan support (click and drag)
        drag_gesture = Gtk.GestureDrag()
        drag_gesture.connect("drag-begin", self._on_pan_begin)
        drag_gesture.connect("drag-update", self._on_pan_update)
        drag_gesture.connect("drag-end", self._on_pan_end)
        self._drawing_area.add_controller(drag_gesture)

        # 2-finger touchpad pinch-to-zoom
        self._zoom_gesture = Gtk.GestureZoom()
        self._zoom_gesture.connect("begin", self._on_zoom_gesture_begin)
        self._zoom_gesture.connect("scale-changed", self._on_zoom_gesture_scale_changed)
        self._drawing_area.add_controller(self._zoom_gesture)

        preview_box.append(self._drawing_area)

        # Toolbar (zoom + navigation)
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        toolbar.add_css_class("preview-toolbar")

        # Zoom controls
        zoom_out = Gtk.Button.new_from_icon_name("zoom-out-symbolic")
        zoom_out.add_css_class("flat")
        zoom_out.set_tooltip_text("Zoom out")
        zoom_out.connect("clicked", lambda b: self._zoom_by(-0.15))
        toolbar.append(zoom_out)

        self._zoom_label = Gtk.Label(label="100%")
        self._zoom_label.add_css_class("preview-zoom-label")
        toolbar.append(self._zoom_label)

        zoom_in = Gtk.Button.new_from_icon_name("zoom-in-symbolic")
        zoom_in.add_css_class("flat")
        zoom_in.set_tooltip_text("Zoom in")
        zoom_in.connect("clicked", lambda b: self._zoom_by(0.15))
        toolbar.append(zoom_in)

        sep1 = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep1.set_margin_start(4)
        sep1.set_margin_end(4)
        toolbar.append(sep1)

        zoom_fit = Gtk.Button.new_from_icon_name("zoom-fit-best-symbolic")
        zoom_fit.add_css_class("flat")
        zoom_fit.set_tooltip_text("Fit page")
        zoom_fit.connect("clicked", lambda b: self._zoom_fit())
        toolbar.append(zoom_fit)

        zoom_actual = Gtk.Button(label="1:1")
        zoom_actual.add_css_class("flat")
        zoom_actual.set_tooltip_text("Actual size")
        zoom_actual.connect("clicked", lambda b: self._zoom_actual())
        toolbar.append(zoom_actual)

        # Spacer
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        toolbar.append(spacer)

        # Expand / Collapse preview button (to take whole right section)
        self._expand_btn = Gtk.Button.new_from_icon_name("view-fullscreen-symbolic")
        self._expand_btn.add_css_class("flat")
        self._expand_btn.set_tooltip_text("Expand preview (hide file list)")
        self._expand_btn.connect("clicked", self._on_expand_clicked)
        toolbar.append(self._expand_btn)

        sep_exp = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        sep_exp.set_margin_start(4)
        sep_exp.set_margin_end(4)
        toolbar.append(sep_exp)

        # Page navigation
        self._prev_btn = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        self._prev_btn.add_css_class("flat")
        self._prev_btn.set_tooltip_text("Previous page")
        self._prev_btn.connect("clicked", lambda b: self._go_page(-1))
        self._prev_btn.set_sensitive(False)
        toolbar.append(self._prev_btn)

        self._page_label = Gtk.Label(label="Page 1 of 1")
        self._page_label.add_css_class("preview-page-label")
        toolbar.append(self._page_label)

        self._next_btn = Gtk.Button.new_from_icon_name("go-next-symbolic")
        self._next_btn.add_css_class("flat")
        self._next_btn.set_tooltip_text("Next page")
        self._next_btn.connect("clicked", lambda b: self._go_page(1))
        self._next_btn.set_sensitive(False)
        toolbar.append(self._next_btn)

        preview_box.append(toolbar)

        self._stack.add_named(preview_box, "preview")

        # Start in empty state
        self._stack.set_visible_child_name("empty")

    # ── Public API ────────────────────────────────────────────────────

    def set_document(self, document: Optional[Document]) -> None:
        """Set the document to preview."""
        self._document = document
        self._current_page = 0
        self._pan_x = 0.0
        self._pan_y = 0.0

        if document and document.is_valid:
            self._stack.set_visible_child_name("preview")
        else:
            self._stack.set_visible_child_name("empty")

        self._invalidate()
        self._update_nav()
        # A new document always starts on its first page
        self.emit("page-changed", 0)

    def set_settings(self, settings: PrintSettings) -> None:
        """Update preview with new settings."""
        self._settings = settings
        self._invalidate()
        self._update_nav()
        self._update_paper_label()

    def refresh(self) -> None:
        """Force a full preview refresh."""
        self._invalidate()

    @property
    def current_page(self) -> int:
        """0-indexed current page."""
        return self._current_page

    @property
    def estimated_sheets(self) -> int:
        """Estimated number of physical sheets."""
        return self._renderer.estimate_pages(self._document, self._settings)

    @property
    def first_page_shown(self) -> int:
        """0-indexed document page at the start of the sheet on screen."""
        if self._settings.pages_per_sheet > 1 and self._sheet_count() > 0:
            return self._current_page * self._settings.pages_per_sheet
        return self._current_page

    # ── Drawing ───────────────────────────────────────────────────────

    def _on_draw(self, area, ctx, width, height) -> None:
        """GTK4 draw callback."""
        if width <= 0 or height <= 0:
            return

        # Render preview surface
        surface = self._renderer.render_preview(
            self._document,
            self._settings,
            self._current_page,
            width * self._zoom,
            height * self._zoom,
        )

        if surface:
            ctx.save()
            if self._zoom != 1.0:
                ctx.scale(1.0 / self._zoom, 1.0 / self._zoom)
            # Apply pan offset
            ctx.translate(self._pan_x * self._zoom, self._pan_y * self._zoom)
            ctx.set_source_surface(surface, 0, 0)
            ctx.paint()
            ctx.restore()
        else:
            # Draw clean empty state
            ctx.set_source_rgba(0.5, 0.5, 0.5, 0.3)
            ctx.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            ctx.set_font_size(14)
            text = "Select a file to preview"
            extents = ctx.text_extents(text)
            ctx.move_to(
                (width - extents.width) / 2,
                (height + extents.height) / 2,
            )
            ctx.show_text(text)

    def _invalidate(self) -> None:
        """Request a redraw."""
        self._cached_surface = None
        self._drawing_area.queue_draw()

    # ── Zoom ──────────────────────────────────────────────────────────

    def _zoom_by(self, delta: float) -> None:
        self._zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, self._zoom + delta))
        self._update_zoom_label()
        self._invalidate()

    def _zoom_fit(self) -> None:
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._update_zoom_label()
        self._invalidate()

    def _zoom_actual(self) -> None:
        """Zoom to actual size (1:1 pixel mapping)."""
        self._zoom = 2.0  # Approximate actual size at screen DPI
        self._update_zoom_label()
        self._invalidate()

    def _on_scroll(self, ctrl, dx, dy) -> bool:
        if dy < 0:
            self._zoom_by(0.15)
        elif dy > 0:
            self._zoom_by(-0.15)
        return True

    def _on_zoom_gesture_begin(self, gesture, sequence) -> None:
        self._gesture_start_zoom = self._zoom

    def _on_zoom_gesture_scale_changed(self, gesture, scale: float) -> None:
        if scale > 0:
            self._zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, self._gesture_start_zoom * scale))
            self._update_zoom_label()
            self._invalidate()

    def _update_zoom_label(self) -> None:
        self._zoom_label.set_text(f"{int(self._zoom * 100)}%")

    # ── Expand / Collapse ─────────────────────────────────────────────

    def _on_expand_clicked(self, btn) -> None:
        self._is_expanded = not self._is_expanded
        icon = "view-restore-symbolic" if self._is_expanded else "view-fullscreen-symbolic"
        tip = "Collapse preview (show file list)" if self._is_expanded else "Expand preview (hide file list)"
        self._expand_btn.set_icon_name(icon)
        self._expand_btn.set_tooltip_text(tip)
        self.emit("expand-toggled", self._is_expanded)

    def set_expanded(self, expanded: bool) -> None:
        if self._is_expanded != expanded:
            self._is_expanded = expanded
            icon = "view-restore-symbolic" if self._is_expanded else "view-fullscreen-symbolic"
            tip = "Collapse preview (show file list)" if self._is_expanded else "Expand preview (hide file list)"
            self._expand_btn.set_icon_name(icon)
            self._expand_btn.set_tooltip_text(tip)

    # ── Pan ───────────────────────────────────────────────────────────

    def _on_pan_begin(self, gesture, start_x, start_y) -> None:
        self._is_panning = True
        self._pan_start_x = self._pan_x
        self._pan_start_y = self._pan_y

    def _on_pan_update(self, gesture, offset_x, offset_y) -> None:
        if self._is_panning:
            self._pan_x = self._pan_start_x + offset_x
            self._pan_y = self._pan_start_y + offset_y
            self._invalidate()

    def _on_pan_end(self, gesture, offset_x, offset_y) -> None:
        self._is_panning = False

    # ── Navigation ────────────────────────────────────────────────────

    def _sheet_count(self) -> int:
        """Sheets the preview can page through under the current settings."""
        return self._renderer.preview_sheet_count(self._document, self._settings)

    def _go_page(self, delta: int) -> None:
        max_sheet = max(0, self._sheet_count() - 1)
        new_page = max(0, min(max_sheet, self._current_page + delta))
        if new_page != self._current_page:
            self._current_page = new_page
            self._pan_x = 0.0
            self._pan_y = 0.0
            self._invalidate()
            self._update_nav()
            self.emit("page-changed", self.first_page_shown)

    def _update_nav(self) -> None:
        total_sheets = max(1, self._sheet_count())
        self._total_pages = total_sheets

        # Settings can shrink the document (larger paper, more pages per sheet)
        if self._current_page > total_sheets - 1:
            self._current_page = total_sheets - 1
            self.emit("page-changed", self.first_page_shown)

        current_display = self._current_page + 1
        self._page_label.set_text(f"Page {current_display} of {total_sheets}")
        self._prev_btn.set_sensitive(self._current_page > 0)
        self._next_btn.set_sensitive(current_display < total_sheets)

    def _update_paper_label(self) -> None:
        paper = get_paper_by_name(self._settings.paper_size_name)
        parts = [
            (paper.display_name or paper.name) if paper else "Custom Size",
            ORIENTATION_NAMES[self._settings.orientation],
        ]
        if self._settings.resolution:
            parts.append(f"{self._settings.get_dpi()} DPI")
        if self._settings.scaling_value != 100:
            parts.append(f"{int(self._settings.scaling_value)}%")
        self._paper_label.set_text(" · ".join(parts))
