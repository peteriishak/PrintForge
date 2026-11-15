"""Settings panel — all print configuration controls."""

from __future__ import annotations

import copy
import logging
from contextlib import contextmanager
from typing import Any, Callable, Optional, Sequence

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GObject, Adw, Pango

from printforge.config.print_settings import (
    PrintSettings, ColorMode, Orientation, ScalingMode, MarginPreset,
    Position, DuplexMode, PrintQuality, ImageFit, CropMode,
    PageRangeMode, Collation, Margins, BookletMode,
)
from printforge.config.presets import PresetManager
from printforge.printing.printer import PrinterInfo
from printforge.printing.capabilities import PrinterCapabilities
from printforge.utils.paper import get_paper_by_name

log = logging.getLogger(__name__)

Option = tuple[str, Any]  # (label shown to the user, value stored in PrintSettings)

COLOR_OPTIONS: list[Option] = [
    ("Color", ColorMode.COLOR),
    ("Grayscale", ColorMode.GRAYSCALE),
    ("Black & White", ColorMode.BLACK_AND_WHITE),
]
DUPLEX_OPTIONS: list[Option] = [
    ("Off", DuplexMode.OFF),
    ("Flip on Long Edge", DuplexMode.LONG_EDGE),
    ("Flip on Short Edge", DuplexMode.SHORT_EDGE),
]
ORIENTATION_OPTIONS: list[Option] = [
    ("Portrait", Orientation.PORTRAIT),
    ("Landscape", Orientation.LANDSCAPE),
    ("Automatic", Orientation.AUTO),
]
SCALING_OPTIONS: list[Option] = [
    ("Fit to Page", ScalingMode.FIT_TO_PAGE),
    ("Fill Page", ScalingMode.FILL_PAGE),
    ("Actual Size", ScalingMode.ACTUAL_SIZE),
    ("Fit Width", ScalingMode.FIT_WIDTH),
    ("Fit Height", ScalingMode.FIT_HEIGHT),
    ("Custom", ScalingMode.CUSTOM),
]
MARGIN_OPTIONS: list[Option] = [
    ("Normal", MarginPreset.DEFAULT),
    ("Narrow", MarginPreset.MINIMUM),
    ("Custom", MarginPreset.CUSTOM),
]
PAGES_PER_SHEET_OPTIONS: list[Option] = [(str(n), n) for n in (1, 2, 4, 6, 9, 16)]
BOOKLET_OPTIONS: list[Option] = [
    ("Off", BookletMode.OFF),
    ("Left Binding", BookletMode.LEFT_BINDING),
    ("Right Binding", BookletMode.RIGHT_BINDING),
]
POSTER_OPTIONS: list[Option] = [("Off", 0)] + [(f"{n} × {n} Sheets", n) for n in (2, 3, 4)]
IMAGE_FIT_OPTIONS: list[Option] = [
    ("Fit to Page", ImageFit.FIT_INSIDE),
    ("Fill Page", ImageFit.FILL_PAGE),
    ("Actual Size", ImageFit.ACTUAL_SIZE),
    ("Custom Scale", ImageFit.CUSTOM_SCALE),
]
ROTATION_OPTIONS: list[Option] = [(f"{degrees}°", degrees) for degrees in (0, 90, 180, 270)]
CROP_OPTIONS: list[Option] = [
    ("None", CropMode.NONE),
    ("Crop to Paper", CropMode.CROP_TO_PAPER),
]
PAGE_RANGE_OPTIONS: list[Option] = [
    ("All Pages", PageRangeMode.ALL),
    ("Current Page", PageRangeMode.CURRENT),
    ("Custom Range", PageRangeMode.CUSTOM),
]
IMAGE_ADJUSTMENTS: list[tuple[str, str]] = [
    ("image_brightness", "Brightness"),
    ("image_contrast", "Contrast"),
    ("image_saturation", "Saturation"),
    ("image_sharpness", "Sharpness"),
]
POSITION_GRID: list[list[tuple[Position, str]]] = [
    [(Position.TOP_LEFT, "↖"), (Position.TOP_CENTER, "↑"), (Position.TOP_RIGHT, "↗")],
    [(Position.CENTER_LEFT, "←"), (Position.CENTER, "•"), (Position.CENTER_RIGHT, "→")],
    [(Position.BOTTOM_LEFT, "↙"), (Position.BOTTOM_CENTER, "↓"), (Position.BOTTOM_RIGHT, "↘")],
]
CUSTOM_PAPER = "Custom"


def _value_label_factory() -> Gtk.ListItemFactory:
    """Factory for the value shown in the row: ellipsizes only when space runs out."""
    factory = Gtk.SignalListItemFactory()

    def setup(_factory, item: Gtk.ListItem) -> None:
        item.set_child(Gtk.Label(xalign=1, ellipsize=Pango.EllipsizeMode.END))

    def bind(_factory, item: Gtk.ListItem) -> None:
        item.get_child().set_label(item.get_item().get_string())

    factory.connect("setup", setup)
    factory.connect("bind", bind)
    return factory


def _popup_label_factory() -> Gtk.ListItemFactory:
    """Factory for the popup list: full labels with a checkmark on the selected entry."""
    factory = Gtk.SignalListItemFactory()

    def setup(_factory, item: Gtk.ListItem) -> None:
        box = Gtk.Box(spacing=12)
        box.append(Gtk.Label(xalign=0, hexpand=True))
        check = Gtk.Image.new_from_icon_name("object-select-symbolic")
        item.bind_property("selected", check, "opacity", GObject.BindingFlags.SYNC_CREATE,
                           lambda _binding, selected: 1.0 if selected else 0.0)
        box.append(check)
        item.set_child(box)

    def bind(_factory, item: Gtk.ListItem) -> None:
        item.get_child().get_first_child().set_label(item.get_item().get_string())

    factory.connect("setup", setup)
    factory.connect("bind", bind)
    return factory


class OptionRow(Adw.ComboRow):
    """Combo row whose entries are (label, value) pairs, shown without truncation."""

    __gtype_name__ = "PrintForgeOptionRow"

    def __init__(self, title: str, options: Sequence[Option] = (), subtitle: str = "") -> None:
        super().__init__(title=title, subtitle=subtitle)
        self._values: list[Any] = []
        self.set_factory(_value_label_factory())
        self.set_list_factory(_popup_label_factory())
        self.set_options(options)

    @property
    def labels(self) -> list[str]:
        model = self.get_model()
        return [model.get_string(i) for i in range(model.get_n_items())]

    @property
    def value(self) -> Any:
        index = self.get_selected()
        return self._values[index] if 0 <= index < len(self._values) else None

    def select_value(self, value: Any) -> bool:
        """Select the entry holding `value`. Returns False if it isn't offered."""
        if value not in self._values:
            return False
        self.set_selected(self._values.index(value))
        return True

    def set_options(self, options: Sequence[Option]) -> None:
        """Replace the entries, keeping the current value selected if it's still offered."""
        previous = self.value
        self._values = [value for _, value in options]
        self.set_model(Gtk.StringList.new([label for label, _ in options]))
        if not self.select_value(previous):
            self.set_selected(0)
        # Always notify so listeners sync with the (possibly unchanged) index
        self.notify("selected")


def _icon_button(icon_name: str, tooltip: str, on_click: Callable) -> Gtk.Button:
    button = Gtk.Button.new_from_icon_name(icon_name)
    button.set_tooltip_text(tooltip)
    button.set_valign(Gtk.Align.CENTER)
    button.add_css_class("flat")
    button.connect("clicked", on_click)
    return button


def _mm_spin(lower: float, upper: float, value: float, tooltip: str = "") -> Gtk.SpinButton:
    spin = Gtk.SpinButton.new_with_range(lower, upper, 1)
    spin.set_value(value)
    spin.set_valign(Gtk.Align.CENTER)
    if tooltip:
        spin.set_tooltip_text(tooltip)
    return spin


class SettingsPanel(Gtk.Box):
    """Sidebar containing all print settings, organized as preference groups:

    - Printer (printer, preset)
    - Page Setup (copies, color, two-sided, paper, orientation, scale)
    - Pages (page range, multi-page documents only)
    - Image (fit, rotation, crop, adjustments — images only)
    - Layout and Paper & Quality (advanced mode only)
    """

    __gtype_name__ = "PrintForgeSettingsPanel"

    __gsignals__ = {
        "settings-changed": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "printer-changed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "printer-refresh-requested": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "printer-settings-requested": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)

        self._settings = PrintSettings()
        self._capabilities: Optional[PrinterCapabilities] = None
        self._printers: list[PrinterInfo] = []
        self._preset_manager = PresetManager()
        self._suppress_signals = False
        self._is_advanced = True
        self._position_buttons: dict[Position, Gtk.Button] = {}
        self._margin_spins: dict[str, Gtk.SpinButton] = {}
        self._adjustment_scales: dict[str, Gtk.Scale] = {}

        page = Adw.PreferencesPage()
        page.set_vexpand(True)
        page.add(self._build_printer_group())
        page.add(self._build_page_setup_group())

        self._page_range_group = self._build_page_range_group()
        self._image_group = self._build_image_group()
        self._layout_group = self._build_layout_group()
        self._quality_group = self._build_quality_group()
        for group in (self._page_range_group, self._image_group, self._layout_group, self._quality_group):
            page.add(group)
        self._page_range_group.set_visible(False)
        self._image_group.set_visible(False)
        self.append(page)

        self._refresh_presets()
        self.set_capabilities(None)
        self.apply_settings(self._settings)

    @contextmanager
    def _quietly(self):
        """Update controls without emitting settings-changed."""
        previous = self._suppress_signals
        self._suppress_signals = True
        try:
            yield
        finally:
            self._suppress_signals = previous

    def _bind_option(self, row: OptionRow, attr: str, on_change: Optional[Callable[[Any], None]] = None) -> None:
        """Keep `settings.<attr>` in sync with the row's selected value."""
        def on_selected(row: OptionRow, _pspec) -> None:
            if row.value is None:
                return
            setattr(self._settings, attr, row.value)
            if on_change:
                on_change(row.value)
            self._emit_settings_changed()
        row.connect("notify::selected", on_selected)

    # ── Mode ──────────────────────────────────────────────────────────

    def set_professional_mode(self, is_advanced: bool) -> None:
        """Show every control (advanced) or only the everyday ones (simple)."""
        self._is_advanced = is_advanced
        self._preset_row.set_visible(is_advanced)
        self._layout_group.set_visible(is_advanced)
        self._quality_group.set_visible(is_advanced)
        self._adjustments_row.set_visible(is_advanced)

    def get_professional_mode(self) -> bool:
        return self._is_advanced

    # ── Groups ────────────────────────────────────────────────────────

    def _build_printer_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title="Printer")

        self._printer_row = OptionRow("Printer", subtitle="No printers found")
        self._printer_row.add_suffix(_icon_button(
            "view-refresh-symbolic", "Refresh Printers",
            lambda _button: self.emit("printer-refresh-requested"),
        ))
        self._printer_settings_button = _icon_button(
            "emblem-system-symbolic", "Printer Settings & Maintenance",
            lambda _button: self.emit("printer-settings-requested"),
        )
        self._printer_settings_button.set_sensitive(False)
        self._printer_row.add_suffix(self._printer_settings_button)
        self._printer_row.connect("notify::selected", self._on_printer_changed)
        group.add(self._printer_row)

        self._preset_row = OptionRow("Preset")
        self._preset_row.add_suffix(_icon_button(
            "document-save-symbolic", "Save Settings as Preset", self._on_save_preset,
        ))
        self._delete_preset_button = _icon_button(
            "user-trash-symbolic", "Delete Preset", self._on_delete_preset,
        )
        self._preset_row.add_suffix(self._delete_preset_button)
        self._preset_row.connect("notify::selected", self._on_preset_selected)
        group.add(self._preset_row)

        return group

    def _build_page_setup_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title="Page Setup")

        self._copies_row = Adw.SpinRow.new_with_range(1, 999, 1)
        self._copies_row.set_title("Copies")
        self._copies_row.connect("notify::value", self._on_copies_changed)
        group.add(self._copies_row)

        self._collate_row = Adw.SwitchRow(title="Collate", subtitle="Print each copy in page order")
        self._collate_row.set_visible(False)
        self._collate_row.connect("notify::active", self._on_collate_changed)
        group.add(self._collate_row)

        self._color_row = OptionRow("Color", COLOR_OPTIONS)
        self._bind_option(self._color_row, "color_mode")
        group.add(self._color_row)

        self._duplex_row = OptionRow("Two-Sided", DUPLEX_OPTIONS)
        self._bind_option(self._duplex_row, "duplex")
        group.add(self._duplex_row)

        self._paper_row = OptionRow("Paper Size")
        self._bind_option(self._paper_row, "paper_size_name", self._on_paper_changed)
        group.add(self._paper_row)

        self._custom_paper_row = Adw.ActionRow(title="Custom Size", subtitle="Width × height in mm")
        self._custom_paper_row.set_visible(False)
        self._custom_width_spin = _mm_spin(50, 1000, 210, "Paper width in mm")
        self._custom_height_spin = _mm_spin(50, 1500, 297, "Paper height in mm")
        for spin in (self._custom_width_spin, self._custom_height_spin):
            spin.connect("value-changed", self._on_custom_paper_changed)
        self._custom_paper_row.add_suffix(self._custom_width_spin)
        self._custom_paper_row.add_suffix(Gtk.Label(label="×"))
        self._custom_paper_row.add_suffix(self._custom_height_spin)
        group.add(self._custom_paper_row)

        self._orientation_row = OptionRow("Orientation", ORIENTATION_OPTIONS)
        self._bind_option(self._orientation_row, "orientation")
        group.add(self._orientation_row)

        self._scale_row = Adw.SpinRow.new_with_range(25, 400, 5)
        self._scale_row.set_title("Scale")
        self._scale_row.set_subtitle("Percent of original size")
        self._scale_row.set_value(100)
        self._scale_row.connect("notify::value", self._on_scale_changed)
        self._scale_reset_button = _icon_button(
            "edit-undo-symbolic", "Reset to 100%", lambda _button: self._scale_row.set_value(100),
        )
        self._scale_reset_button.set_visible(False)
        self._scale_row.add_suffix(self._scale_reset_button)
        group.add(self._scale_row)

        return group

    def _build_layout_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title="Layout")

        self._scaling_row = OptionRow("Scaling", SCALING_OPTIONS)
        self._bind_option(self._scaling_row, "scaling_mode")
        group.add(self._scaling_row)

        self._margin_row = OptionRow("Margins", MARGIN_OPTIONS)
        self._bind_option(self._margin_row, "margin_preset", self._on_margin_preset_changed)
        group.add(self._margin_row)

        self._custom_margins_row = Adw.ActionRow(title="Custom Margins", subtitle="In millimeters")
        self._custom_margins_row.set_visible(False)
        margins_grid = Gtk.Grid(column_spacing=8, row_spacing=4, valign=Gtk.Align.CENTER)
        for i, side in enumerate(("Top", "Bottom", "Left", "Right")):
            label = Gtk.Label(label=side, halign=Gtk.Align.END)
            label.add_css_class("dim-label")
            margins_grid.attach(label, (i % 2) * 2, i // 2, 1, 1)
            spin = _mm_spin(0, 100, 10)
            spin.connect("value-changed", self._on_custom_margin_changed)
            margins_grid.attach(spin, (i % 2) * 2 + 1, i // 2, 1, 1)
            self._margin_spins[side.lower()] = spin
        self._custom_margins_row.add_suffix(margins_grid)
        group.add(self._custom_margins_row)

        position_row = Adw.ActionRow(title="Position", subtitle="Where content sits on the page")
        position_grid = Gtk.Grid(row_spacing=3, column_spacing=3, valign=Gtk.Align.CENTER)
        position_grid.set_margin_top(6)
        position_grid.set_margin_bottom(6)
        for row_index, grid_row in enumerate(POSITION_GRID):
            for col_index, (position, arrow) in enumerate(grid_row):
                button = Gtk.Button(label=arrow)
                button.add_css_class("position-button")
                button.set_tooltip_text(position.value.replace("_", " ").title())
                button.connect("clicked", self._on_position_clicked, position)
                position_grid.attach(button, col_index, row_index, 1, 1)
                self._position_buttons[position] = button
        position_row.add_suffix(position_grid)
        group.add(position_row)

        self._pages_per_sheet_row = OptionRow("Pages per Sheet", PAGES_PER_SHEET_OPTIONS)
        self._bind_option(self._pages_per_sheet_row, "pages_per_sheet")
        group.add(self._pages_per_sheet_row)

        self._booklet_row = OptionRow("Booklet", BOOKLET_OPTIONS)
        self._bind_option(self._booklet_row, "booklet_mode")
        group.add(self._booklet_row)

        self._poster_row = OptionRow("Poster", POSTER_OPTIONS)
        self._poster_row.connect("notify::selected", self._on_poster_changed)
        group.add(self._poster_row)

        self._poster_overlap_row = Adw.SpinRow.new_with_range(0, 50, 1)
        self._poster_overlap_row.set_title("Sheet Overlap")
        self._poster_overlap_row.set_subtitle("In millimeters")
        self._poster_overlap_row.set_visible(False)
        self._poster_overlap_row.connect("notify::value", self._on_poster_overlap_changed)
        group.add(self._poster_overlap_row)

        return group

    def _build_quality_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title="Paper &amp; Quality")

        self._media_type_row = OptionRow("Paper Type")
        self._bind_option(self._media_type_row, "media_type")
        group.add(self._media_type_row)

        self._tray_row = OptionRow("Paper Tray", [("Automatic", "")])
        self._tray_row.set_visible(False)
        self._bind_option(self._tray_row, "tray", lambda tray: self._tray_row.set_subtitle(
            "" if tray else "The printer picks the tray holding this paper size"
        ))
        group.add(self._tray_row)

        self._quality_row = OptionRow("Print Quality")
        self._bind_option(self._quality_row, "quality")
        group.add(self._quality_row)

        self._resolution_row = OptionRow("Resolution")
        self._bind_option(self._resolution_row, "resolution")
        group.add(self._resolution_row)

        return group

    def _build_image_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title="Image")

        self._image_fit_row = OptionRow("Fit", IMAGE_FIT_OPTIONS)
        self._bind_option(self._image_fit_row, "image_fit")
        group.add(self._image_fit_row)

        self._rotation_row = OptionRow("Rotation", ROTATION_OPTIONS)
        self._bind_option(self._rotation_row, "image_rotation")
        group.add(self._rotation_row)

        self._crop_row = OptionRow("Crop", CROP_OPTIONS)
        self._bind_option(self._crop_row, "crop_mode")
        group.add(self._crop_row)

        self._adjustments_row = Adw.ExpanderRow(title="Adjustments", subtitle="Brightness, contrast and sharpness")
        self._adjustments_row.add_suffix(_icon_button(
            "edit-undo-symbolic", "Reset Adjustments", self._on_reset_adjustments,
        ))
        for attr, title in IMAGE_ADJUSTMENTS:
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -100, 100, 1)
            scale.set_size_request(140, -1)
            scale.connect("value-changed", self._on_adjustment_changed, attr)
            row = Adw.ActionRow(title=title)
            row.add_suffix(scale)
            self._adjustments_row.add_row(row)
            self._adjustment_scales[attr] = scale
        group.add(self._adjustments_row)

        return group

    def _build_page_range_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title="Pages")

        self._page_range_row = OptionRow("Print", PAGE_RANGE_OPTIONS)
        self._bind_option(
            self._page_range_row, "page_range_mode",
            lambda mode: self._range_entry_row.set_visible(mode == PageRangeMode.CUSTOM),
        )
        group.add(self._page_range_row)

        self._range_entry_row = Adw.EntryRow(title="Pages, e.g. 1-3, 5, 8-10")
        self._range_entry_row.set_visible(False)
        self._range_entry_row.connect("changed", self._on_range_entry_changed)
        group.add(self._range_entry_row)

        return group

    # ── Public API ────────────────────────────────────────────────────

    @property
    def settings(self) -> PrintSettings:
        return self._settings

    def set_printers(self, printers: list[PrinterInfo]) -> None:
        """Update the printer list, keeping the current printer selected if still present."""
        self._printers = printers
        with self._quietly():
            self._printer_row.set_options([(p.display_name, p.name) for p in printers])
            current = self._settings.printer_name
            if not any(p.name == current for p in printers):
                default = next((p for p in printers if p.is_default), None)
                if default:
                    self._printer_row.select_value(default.name)

        self._printer_settings_button.set_sensitive(bool(printers))
        if printers:
            self._on_printer_changed(self._printer_row, None)
        else:
            self._printer_row.set_subtitle("No printers found")

    def set_capabilities(self, caps: Optional[PrinterCapabilities]) -> None:
        """Offer only the options the selected printer supports.

        Without capabilities, generic defaults are shown.
        """
        self._capabilities = caps
        known = caps or PrinterCapabilities()

        with self._quietly():
            self._paper_row.set_options(
                [(p.display_name or p.name, p.name) for p in known.get_paper_sizes()]
                + [("Custom Size", CUSTOM_PAPER)]
            )
            self._color_row.set_options(COLOR_OPTIONS if known.has_color() else COLOR_OPTIONS[1:])

            self._duplex_row.set_sensitive(known.supports_duplex)
            self._duplex_row.set_subtitle("" if known.supports_duplex else "Not supported by this printer")
            if not known.supports_duplex:
                self._duplex_row.select_value(DuplexMode.OFF)

            qualities = {quality.value: quality for quality in PrintQuality}
            self._quality_row.set_options([
                (label, qualities[value]) for label, value in known.get_quality_labels() if value in qualities
            ])
            self._media_type_row.set_options(known.get_media_type_labels())

            # "" lets the printer pick the tray that holds the selected paper size
            trays = known.get_tray_labels()
            self._tray_row.set_options([("Automatic", "")] + trays)
            self._tray_row.set_visible(bool(trays))

            self._resolution_row.set_options([("Automatic", "")] + known.get_resolution_labels())

        self._emit_settings_changed()

    def set_document_type(self, doc_type: str) -> None:
        """Show the settings sections that apply to this kind of document."""
        self._image_group.set_visible(doc_type in ("image", "svg"))
        self._page_range_group.set_visible(doc_type == "pdf")

    def set_total_pages(self, total: int) -> None:
        """Offer page-range selection for multi-page documents."""
        if total > 1:
            self._page_range_group.set_visible(True)
            self._range_entry_row.set_title(f"Pages, e.g. 1-{total} or 1, 3, 5")

    def apply_settings(self, settings: PrintSettings) -> None:
        """Show `settings` in every control. The panel edits this object from now on."""
        # Handlers write into self._settings while controls change, so read from a copy
        target = copy.deepcopy(settings)
        self._settings = settings

        with self._quietly():
            self._copies_row.set_value(target.copies)
            self._collate_row.set_active(target.collation == Collation.COLLATED)
            self._scale_row.set_value(target.scaling_value)
            self._custom_width_spin.set_value(target.custom_paper_width_mm)
            self._custom_height_spin.set_value(target.custom_paper_height_mm)
            for side, spin in self._margin_spins.items():
                spin.set_value(getattr(target.margins, side))
            self._poster_overlap_row.set_value(target.poster_overlap_mm)
            self._range_entry_row.set_text(target.page_range_str)
            for attr, scale in self._adjustment_scales.items():
                scale.set_value(getattr(target, attr))

            selections = [
                (self._color_row, target.color_mode),
                (self._duplex_row, target.duplex),
                (self._paper_row, target.paper_size_name),
                (self._orientation_row, target.orientation),
                (self._scaling_row, target.scaling_mode),
                (self._margin_row, target.margin_preset),
                (self._pages_per_sheet_row, target.pages_per_sheet),
                (self._booklet_row, target.booklet_mode),
                (self._poster_row, target.poster_cols if target.poster_enabled else 0),
                (self._media_type_row, target.media_type),
                (self._tray_row, target.tray),
                (self._quality_row, target.quality),
                (self._resolution_row, target.resolution),
                (self._image_fit_row, target.image_fit),
                (self._rotation_row, target.image_rotation),
                (self._crop_row, target.crop_mode),
                (self._page_range_row, target.page_range_mode),
            ]
            for row, value in selections:
                row.select_value(value)
                row.notify("selected")  # sync settings and subtitles even if the index didn't move

            settings.margins = target.margins
            settings.position = target.position
            self._highlight_position(target.position)

        if target.printer_name:
            self.select_printer(target.printer_name)
        else:
            printer = self.get_selected_printer()
            settings.printer_name = printer.name if printer else ""

        self._emit_settings_changed()

    def get_selected_printer(self) -> Optional[PrinterInfo]:
        """Return the currently selected printer info."""
        index = self._printer_row.get_selected()
        if 0 <= index < len(self._printers):
            return self._printers[index]
        return None

    def select_printer(self, name: str) -> None:
        """Select a printer by its exact name."""
        self._printer_row.select_value(name)

    # ── Handlers ──────────────────────────────────────────────────────

    def _emit_settings_changed(self) -> None:
        if not self._suppress_signals:
            self.emit("settings-changed", self._settings)

    def _on_printer_changed(self, _row, _pspec) -> None:
        if self._suppress_signals:
            return  # set_printers() reports the final selection once it's done
        printer = self.get_selected_printer()
        if printer:
            self._settings.printer_name = printer.name
            status = printer.state.display_name
            self._printer_row.set_subtitle(f"{status} · Default" if printer.is_default else status)
            self.emit("printer-changed", printer.name)
        self._emit_settings_changed()

    def _on_copies_changed(self, row: Adw.SpinRow, _pspec) -> None:
        self._settings.copies = int(row.get_value())
        self._collate_row.set_visible(self._settings.copies > 1)
        self._emit_settings_changed()

    def _on_collate_changed(self, row: Adw.SwitchRow, _pspec) -> None:
        self._settings.collation = Collation.COLLATED if row.get_active() else Collation.UNCOLLATED
        self._emit_settings_changed()

    def _on_paper_changed(self, paper_name: str) -> None:
        is_custom = paper_name == CUSTOM_PAPER
        self._custom_paper_row.set_visible(is_custom)
        paper = get_paper_by_name(paper_name)
        self._paper_row.set_subtitle(paper.dimensions_label if paper and not is_custom else "")

    def _on_custom_paper_changed(self, _spin) -> None:
        self._settings.custom_paper_width_mm = self._custom_width_spin.get_value()
        self._settings.custom_paper_height_mm = self._custom_height_spin.get_value()
        self._emit_settings_changed()

    def _on_scale_changed(self, row: Adw.SpinRow, _pspec) -> None:
        self._settings.scaling_value = row.get_value()
        is_default = self._settings.scaling_value == 100
        self._scale_reset_button.set_visible(not is_default)
        if not is_default:
            self._scaling_row.select_value(ScalingMode.CUSTOM)
            self._settings.scaling_mode = ScalingMode.CUSTOM
        self._emit_settings_changed()

    def _on_margin_preset_changed(self, preset: MarginPreset) -> None:
        self._custom_margins_row.set_visible(preset == MarginPreset.CUSTOM)
        if preset == MarginPreset.DEFAULT:
            self._settings.margins = Margins.default()
        elif preset == MarginPreset.MINIMUM:
            self._settings.margins = Margins.minimum()
        if preset == MarginPreset.CUSTOM:
            self._margin_row.set_subtitle("")
        else:
            self._margin_row.set_subtitle(f"{self._settings.margins.top:g} mm on each side")

    def _on_custom_margin_changed(self, _spin) -> None:
        self._settings.margins = Margins(**{side: spin.get_value() for side, spin in self._margin_spins.items()})
        self._emit_settings_changed()

    def _highlight_position(self, selected: Position) -> None:
        for position, button in self._position_buttons.items():
            if position == selected:
                button.add_css_class("suggested-action")
                button.remove_css_class("flat")
            else:
                button.remove_css_class("suggested-action")
                button.add_css_class("flat")

    def _on_position_clicked(self, _button, position: Position) -> None:
        self._settings.position = position
        self._highlight_position(position)
        self._emit_settings_changed()

    def _on_poster_changed(self, row: OptionRow, _pspec) -> None:
        grid_size = row.value or 0
        self._settings.poster_enabled = grid_size > 0
        if grid_size:
            self._settings.poster_cols = self._settings.poster_rows = grid_size
        self._poster_overlap_row.set_visible(grid_size > 0)
        self._emit_settings_changed()

    def _on_poster_overlap_changed(self, row: Adw.SpinRow, _pspec) -> None:
        self._settings.poster_overlap_mm = row.get_value()
        self._emit_settings_changed()

    def _on_adjustment_changed(self, scale: Gtk.Scale, attr: str) -> None:
        setattr(self._settings, attr, scale.get_value())
        self._emit_settings_changed()

    def _on_reset_adjustments(self, _button) -> None:
        for scale in self._adjustment_scales.values():
            scale.set_value(0)

    def _on_range_entry_changed(self, entry: Adw.EntryRow) -> None:
        self._settings.page_range_str = entry.get_text()
        self._emit_settings_changed()

    # ── Presets ───────────────────────────────────────────────────────

    def _refresh_presets(self, select: str = "") -> None:
        names = self._preset_manager.all_names
        with self._quietly():
            self._preset_row.set_options([("None", "")] + [(name, name) for name in names])
            self._preset_row.select_value(select)
        self._update_delete_preset_button()

    def _update_delete_preset_button(self) -> None:
        name = self._preset_row.value
        self._delete_preset_button.set_sensitive(bool(name) and not self._preset_manager.is_builtin(name))

    def _on_preset_selected(self, row: OptionRow, _pspec) -> None:
        self._update_delete_preset_button()
        if self._suppress_signals or not row.value:
            return
        preset = self._preset_manager.get(row.value)
        if preset:
            preset.printer_name = self._settings.printer_name
            self.apply_settings(preset)

    def _on_save_preset(self, _button) -> None:
        dialog = Adw.AlertDialog(heading="Save Preset", body="Save the current settings under a name.")
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("save", "Save")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")
        dialog.set_close_response("cancel")

        entry = Gtk.Entry(placeholder_text="Preset name", activates_default=True)
        dialog.set_extra_child(entry)
        dialog.connect("response", self._on_save_preset_response, entry)
        dialog.present(self.get_root())

    def _on_save_preset_response(self, _dialog, response: str, entry: Gtk.Entry) -> None:
        name = entry.get_text().strip()
        if response == "save" and name:
            self._preset_manager.save_preset(name, self._settings)
            self._refresh_presets(select=name)

    def _on_delete_preset(self, _button) -> None:
        name = self._preset_row.value
        if name and not self._preset_manager.is_builtin(name):
            self._preset_manager.delete(name)
            self._refresh_presets()
