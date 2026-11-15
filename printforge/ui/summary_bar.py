"""Print summary bar — fixed bottom bar showing job summary and Print button."""

from __future__ import annotations

import logging
from typing import Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GObject, Pango

from printforge.config.print_settings import (
    PrintSettings, ColorMode, DuplexMode, Orientation,
)
from printforge.utils.paper import get_paper_by_name

log = logging.getLogger(__name__)

COLOR_NAMES = {
    ColorMode.COLOR: "Color",
    ColorMode.GRAYSCALE: "Grayscale",
    ColorMode.BLACK_AND_WHITE: "Black & White",
}


def _plural(count: int, singular: str, plural: str = "") -> str:
    return f"{count} {singular if count == 1 else plural or singular + 's'}"


class PrintSummaryBar(Gtk.Box):
    """Fixed bottom bar showing print job summary and the Print button.

    Displays:  3 files · 16 pages · 2 copies · A4 · Color · Two-Sided    [Print]

    Automatically updates when settings or file state changes.
    """

    __gtype_name__ = "PrintForgeSummaryBar"

    __gsignals__ = {
        "print-requested": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.add_css_class("summary-bar")

        self._file_count: int = 0
        self._page_count: int = 0
        self._settings = PrintSettings()

        self._build_ui()

    def _build_ui(self) -> None:
        self._summary_label = Gtk.Label(label="No files selected")
        self._summary_label.add_css_class("dim-label")
        self._summary_label.set_halign(Gtk.Align.START)
        self._summary_label.set_hexpand(True)
        self._summary_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.append(self._summary_label)

        self._print_btn = Gtk.Button(label="Print")
        self._print_btn.add_css_class("pill")
        self._print_btn.add_css_class("suggested-action")
        self._print_btn.set_sensitive(False)
        self._print_btn.set_tooltip_text("Send to Printer (Ctrl+P)")
        self._print_btn.connect("clicked", lambda _button: self.emit("print-requested"))
        self.append(self._print_btn)

    # ── Public API ────────────────────────────────────────────────────

    def update(
        self,
        file_count: int = 0,
        page_count: int = 0,
        settings: Optional[PrintSettings] = None,
        printer_name: str = "",
        has_valid_files: bool = False,
        has_printer: bool = False,
        sheet_count: int = 0,
    ) -> None:
        """Update the summary bar with current state.

        `page_count` is the number of document pages that will print (one copy);
        `sheet_count` is the sheets of paper needed for every copy.
        """
        self._file_count = file_count
        self._page_count = page_count
        if settings:
            self._settings = settings
        self._print_btn.set_sensitive(has_valid_files and has_printer)

        if file_count == 0:
            self._summary_label.set_text("No files selected")
            return

        copies = self._settings.copies
        parts = [_plural(file_count, "file")]
        if page_count > 0:
            parts.append(_plural(page_count, "page"))
        if copies > 1:
            parts.append(_plural(copies, "copy", "copies"))
        # Sheets of paper for the whole job, when copies, two-sided or N-up make it differ
        if sheet_count > 0 and (copies > 1 or sheet_count != page_count):
            parts.append(_plural(sheet_count, "sheet"))

        paper = get_paper_by_name(self._settings.paper_size_name)
        parts.append(paper.display_name or paper.name if paper else "Custom Size")
        if self._settings.orientation == Orientation.LANDSCAPE:
            parts.append("Landscape")
        parts.append(COLOR_NAMES[self._settings.color_mode])
        if self._settings.duplex != DuplexMode.OFF:
            parts.append("Two-Sided")
        if self._settings.resolution:
            parts.append(f"{self._settings.get_dpi()} DPI")

        self._summary_label.set_text(" · ".join(parts))

    @property
    def print_button(self) -> Gtk.Button:
        """Access the print button directly for external state management."""
        return self._print_btn
