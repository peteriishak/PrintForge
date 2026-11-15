"""Main application window — sidebar + workspace layout.

Layout:
┌────────────────────┬─────────────────────────────────────┐
│ [Simple|Advanced]  │ +        PrintForge             ≡   │
├────────────────────┼─────────────────────────────────────┤
│ Printer            │ Files                               │
│ Page Setup         ├─────────────────────────────────────┤
│ Layout             │ Preview                             │
│ Paper & Quality    │                                     │
│ …                  ├─────────────────────────────────────┤
│                    │ 1 file · 5 pages · A4      [Print]  │
└────────────────────┴─────────────────────────────────────┘
On narrow windows the settings sidebar becomes an overlay.
"""

from __future__ import annotations

import logging
import os

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GObject, Adw, GLib, Gio

from printforge.config.print_settings import PrintSettings
from printforge.config.settings import AppSettings
from printforge.config.history import HistoryManager
from printforge.documents.layout_engine import LayoutEngine
from printforge.documents.print_prep import PrintPreparer
from printforge.printing.cups_backend import CupsBackend, CupsError
from printforge.printing.mock_backend import MockBackend
from printforge.printing.job import PrintJobManager
from printforge.printing.preflight import PreflightChecker
from printforge.ui.file_list import FileListWidget, FileItem
from printforge.ui.settings_panel import SettingsPanel
from printforge.ui.preview import PreviewWidget
from printforge.ui.summary_bar import PrintSummaryBar
from printforge.ui.dialogs import (
    PrintProgressDialog, PrintResultDialog, PrintQueueDialog,
    PrinterManagementDialog, PrintHistoryDialog, PreferencesDialog,
    show_about_dialog,
)
from printforge.ui.printer_settings import PrinterSettingsDialog

log = logging.getLogger(__name__)


class PrintForgeWindow(Adw.ApplicationWindow):
    """Main PrintForge application window.

    - Sidebar: settings panel with a Simple / Advanced switch
    - Content: file list (top), preview, and summary bar with the Print button
    """

    __gtype_name__ = "PrintForgeWindow"

    def __init__(self, use_mock: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)

        self._app_settings = AppSettings.get()
        self._history_mgr = HistoryManager()

        # Initialize backend
        identity = dict(
            user_id=self._app_settings.user_id,
            send_user_id=self._app_settings.send_user_id,
        )
        if use_mock or self._app_settings.use_mock_backend:
            self._backend = MockBackend(**identity)
            log.info("Using mock printing backend")
        else:
            self._backend = CupsBackend(**identity)
            if not self._backend.is_available:
                log.warning("CUPS unavailable, falling back to mock backend")
                self._backend = MockBackend(**identity)

        self._job_manager = PrintJobManager(self._backend)
        self._print_preparer = PrintPreparer()
        self._layout_engine = LayoutEngine()
        self._settings = PrintSettings()
        self._last_printer_name = ""

        # Restore window geometry
        self.set_default_size(
            self._app_settings.window_width,
            self._app_settings.window_height,
        )

        self._build_ui()
        self._setup_actions()
        self._settings_panel.set_printers(self._backend.get_printers())

        # Restore last settings if available
        last = self._app_settings.last_settings
        if last:
            self._settings_panel.apply_settings(last)
        self._settings = self._settings_panel.settings

        # Connect window state for saving geometry
        self.connect("close-request", self._on_close_request)

    def _build_ui(self) -> None:
        is_simple = self._app_settings.simple_mode

        # ── Sidebar: settings ─────────────────────────────────────────
        self._mode_switch = Adw.ToggleGroup()
        self._mode_switch.add(Adw.Toggle(name="simple", label="Simple", tooltip="Everyday settings only"))
        self._mode_switch.add(Adw.Toggle(name="advanced", label="Advanced", tooltip="All print settings"))
        self._mode_switch.set_active_name("simple" if is_simple else "advanced")
        self._mode_switch.connect("notify::active-name", self._on_mode_changed)

        sidebar_header = Adw.HeaderBar()
        sidebar_header.set_title_widget(self._mode_switch)

        self._settings_panel = SettingsPanel()
        self._settings_panel.set_professional_mode(not is_simple)
        self._settings_panel.connect("settings-changed", self._on_settings_changed)
        self._settings_panel.connect("printer-refresh-requested", self._on_refresh_printers)
        self._settings_panel.connect("printer-changed", self._on_printer_selection_changed)
        self._settings_panel.connect("printer-settings-requested", lambda _panel: self._show_printer_settings())

        sidebar = Adw.ToolbarView()
        sidebar.add_top_bar(sidebar_header)
        sidebar.set_content(self._settings_panel)

        # ── Content: files, preview, summary ──────────────────────────
        self._split_view = Adw.OverlaySplitView()
        self._split_view.set_min_sidebar_width(340)
        self._split_view.set_max_sidebar_width(420)
        self._split_view.set_sidebar_width_fraction(0.36)
        self._split_view.set_sidebar(sidebar)

        sidebar_button = Gtk.ToggleButton(icon_name="sidebar-show-symbolic", tooltip_text="Show Settings")
        self._split_view.bind_property(
            "show-sidebar", sidebar_button, "active",
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE,
        )
        self._split_view.bind_property("collapsed", sidebar_button, "visible", GObject.BindingFlags.SYNC_CREATE)

        add_button = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="Add Files (Ctrl+O)")
        add_button.set_action_name("win.add-files")

        menu = Gio.Menu()
        menu.append("Printers", "win.show-printers")
        menu.append("Printer Settings", "win.show-printer-settings")
        menu.append("Print Jobs", "win.show-queue")
        menu.append("Print History", "win.show-history")
        about_section = Gio.Menu()
        about_section.append("Preferences", "win.show-preferences")
        about_section.append("Keyboard Shortcuts", "win.show-shortcuts")
        about_section.append("About PrintForge", "win.about")
        menu.append_section(None, about_section)
        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic", tooltip_text="Main Menu", menu_model=menu)
        menu_button.set_primary(True)

        self._window_title = Adw.WindowTitle(title="PrintForge")
        content_header = Adw.HeaderBar()
        content_header.set_title_widget(self._window_title)
        content_header.pack_start(sidebar_button)
        content_header.pack_start(add_button)
        content_header.pack_end(menu_button)

        self._file_list = FileListWidget()
        self._file_list.set_vexpand(False)
        self._file_list.connect("file-added", self._on_file_added)
        self._file_list.connect("file-removed", self._on_file_removed)
        self._file_list.connect("file-selected", self._on_file_selected)
        self._file_list.connect("files-cleared", self._on_files_cleared)

        self._preview = PreviewWidget()
        self._preview.set_vexpand(True)
        self._preview.connect("page-changed", self._on_preview_page_changed)
        self._preview.connect("expand-toggled", self._on_preview_expand_toggled)

        workspace = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        workspace.append(self._file_list)
        self._files_separator = Gtk.Separator()
        workspace.append(self._files_separator)
        workspace.append(self._preview)

        self._summary_bar = PrintSummaryBar()
        self._summary_bar.connect("print-requested", lambda _bar: self._on_print_clicked(None))

        content = Adw.ToolbarView()
        content.add_top_bar(content_header)
        content.set_content(workspace)
        content.add_bottom_bar(self._summary_bar)
        content.set_bottom_bar_style(Adw.ToolbarStyle.RAISED)
        self._split_view.set_content(content)

        self._toast_overlay = Adw.ToastOverlay(child=self._split_view)
        self.set_content(self._toast_overlay)

        # Narrow windows: the sidebar slides over the content instead of sitting beside it
        narrow = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 720sp"))
        narrow.add_setter(self._split_view, "collapsed", True)
        self.add_breakpoint(narrow)
        self.set_size_request(360, 480)

    def _on_mode_changed(self, toggle_group: Adw.ToggleGroup, _pspec) -> None:
        is_simple = toggle_group.get_active_name() == "simple"
        self._app_settings.simple_mode = is_simple
        self._settings_panel.set_professional_mode(not is_simple)

    def show_toast(self, message: str) -> None:
        self._toast_overlay.add_toast(Adw.Toast(title=message, timeout=3))

    def _setup_actions(self) -> None:
        """Register window actions and keyboard shortcuts."""
        # Add files (Ctrl+O)
        add_action = Gio.SimpleAction.new("add-files", None)
        add_action.connect("activate", lambda a, p: self._file_list.open_file_chooser())
        self.add_action(add_action)

        # Print (Ctrl+P)
        print_action = Gio.SimpleAction.new("print", None)
        print_action.connect("activate", lambda a, p: self._on_print_clicked(None))
        self.add_action(print_action)

        # Refresh printers (Ctrl+R)
        refresh_action = Gio.SimpleAction.new("refresh", None)
        refresh_action.connect("activate", lambda a, p: self._on_refresh_printers(None))
        self.add_action(refresh_action)

        # Remove selected file (Delete)
        remove_action = Gio.SimpleAction.new("remove-file", None)
        remove_action.connect("activate", lambda a, p: self._remove_selected_file())
        self.add_action(remove_action)

        # Printers dialog
        printers_action = Gio.SimpleAction.new("show-printers", None)
        printers_action.connect("activate", lambda a, p: self._show_printers_dialog())
        self.add_action(printers_action)

        # Printer settings & maintenance
        printer_settings_action = Gio.SimpleAction.new("show-printer-settings", None)
        printer_settings_action.connect("activate", lambda a, p: self._show_printer_settings())
        self.add_action(printer_settings_action)

        # Show queue / jobs
        queue_action = Gio.SimpleAction.new("show-queue", None)
        queue_action.connect("activate", lambda a, p: self._show_queue())
        self.add_action(queue_action)

        # Show print history
        history_action = Gio.SimpleAction.new("show-history", None)
        history_action.connect("activate", lambda a, p: self._show_history_dialog())
        self.add_action(history_action)

        # Preferences
        pref_action = Gio.SimpleAction.new("show-preferences", None)
        pref_action.connect("activate", lambda a, p: self._show_preferences_dialog())
        self.add_action(pref_action)

        # About
        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", lambda a, p: show_about_dialog(self))
        self.add_action(about_action)

        # Show shortcuts
        shortcuts_action = Gio.SimpleAction.new("show-shortcuts", None)
        shortcuts_action.connect("activate", lambda a, p: self._show_shortcuts())
        self.add_action(shortcuts_action)

        # Keyboard shortcuts
        app = self.get_application()
        if app:
            app.set_accels_for_action("win.add-files", ["<Control>o"])
            app.set_accels_for_action("win.print", ["<Control>p"])
            app.set_accels_for_action("win.refresh", ["<Control>r"])
            app.set_accels_for_action("win.remove-file", ["Delete"])
            app.set_accels_for_action("win.show-queue", ["<Control><Shift>p"])
            app.set_accels_for_action("win.show-preferences", ["<Control>comma"])

    def _remove_selected_file(self) -> None:
        """Remove the currently selected file."""
        idx = self._file_list.selected_index
        if idx >= 0:
            self._file_list.remove_file(idx)

    # ── Backend Integration ───────────────────────────────────────────

    def _on_refresh_printers(self, _panel) -> None:
        self._last_printer_name = ""  # reload capabilities even if the printer is unchanged
        self._settings_panel.set_printers(self._backend.refresh())

    # ── File Events ───────────────────────────────────────────────────

    def _on_file_added(self, widget, item: FileItem) -> None:
        self._update_summary()

    def _on_file_removed(self, widget, item: FileItem) -> None:
        self._update_summary()
        if not self._file_list.items:
            self._preview.set_document(None)
            self._window_title.set_subtitle("")

    def _on_file_selected(self, widget, item: FileItem) -> None:
        """When a file is selected, show it in the preview."""
        self._window_title.set_subtitle(item.filename if item else "")
        if item and item.document:
            self._preview.set_document(item.document)
            doc_type = item.document.file_type
            self._settings_panel.set_document_type(doc_type)
            if item.document.page_count > 1:
                self._settings_panel.set_total_pages(item.document.page_count)
        else:
            self._preview.set_document(None)

        self._update_summary()

    def _on_files_cleared(self, widget) -> None:
        self._preview.set_document(None)
        self._window_title.set_subtitle("")
        self._update_summary()

    # ── Settings Events ───────────────────────────────────────────────

    def _on_printer_selection_changed(self, panel, printer_name: str) -> None:
        """Handle dynamic printer change to reload capabilities."""
        if printer_name and printer_name != self._last_printer_name:
            self._last_printer_name = printer_name
            panel.set_capabilities(self._backend.get_capabilities(printer_name))
            self._update_summary()

    def _on_settings_changed(self, panel, settings: PrintSettings) -> None:
        self._settings = settings
        self._preview.set_settings(settings)
        self._update_summary()

    def _on_preview_page_changed(self, preview, page: int) -> None:
        self._settings.current_page = page + 1
        self._update_summary()

    def _on_preview_expand_toggled(self, preview, is_expanded: bool) -> None:
        """Expand preview to fill the entire right column by hiding the file list."""
        self._file_list.set_visible(not is_expanded)
        self._files_separator.set_visible(not is_expanded)

    # ── Printing ──────────────────────────────────────────────────────

    def _on_print_clicked(self, button) -> None:
        """Execute the print workflow with preflight checks."""
        items = self._file_list.items
        if not items:
            return

        printer = self._settings_panel.get_selected_printer()
        if not printer:
            return

        docs = [item.document for item in items if item.document and item.document.is_valid]
        caps = self._backend.get_capabilities(printer.name) if printer else None

        # Preflight validation
        preflight = PreflightChecker.check(docs, self._settings, printer, caps)
        if not preflight.is_valid:
            err_msgs = "\n".join(f"• {e.message}" for e in preflight.errors)
            dialog = Adw.AlertDialog(
                heading="Unable to Print",
                body=f"Please resolve the following issues:\n\n{err_msgs}",
            )
            dialog.add_response("ok", "OK")
            if any(e.field_name == "printer" for e in preflight.errors):
                # A paused or rejecting queue is fixed from Printer Settings
                dialog.add_response("fix", "Printer Settings")
                dialog.set_response_appearance("fix", Adw.ResponseAppearance.SUGGESTED)
                dialog.connect("response", lambda _d, response: response == "fix" and self._show_printer_settings())
            dialog.present(self)
            return

        # Print documents
        for item in items:
            if not item.document or not item.document.is_valid:
                continue
            self._print_document(item, printer.name, caps)

    def _print_document(self, item: FileItem, printer_name: str, caps=None) -> None:
        """Print a single document."""
        doc = item.document
        filename = item.filename
        # Counted for this document, not the one in the preview
        count = self._layout_engine.count_document(doc, self._settings)

        progress = PrintProgressDialog(
            filename=filename,
            printer_name=printer_name,
            pages=count.pages,
            sheets=count.total_sheets,
        )
        progress.present(self)

        def retry(_dialog) -> None:
            self._print_document(item, printer_name, caps)

        def save_history(status: str) -> None:
            if not self._app_settings.save_history:
                return
            self._history_mgr.add_entry(
                filename=filename,
                printer_name=printer_name,
                page_count=count.pages,
                copies=self._settings.copies,
                paper_size=self._settings.paper_size_name,
                color_mode=self._settings.color_mode.value,
                duplex=self._settings.duplex.value,
                status=status,
                filepath=item.filepath,
                settings=self._settings.to_dict() if status == "Completed" else None,
            )

        def do_print():
            try:
                prepared_path = self._print_preparer.prepare(doc, self._settings)
                if not prepared_path:
                    progress.close()
                    result = PrintResultDialog(
                        success=False,
                        message="Failed to prepare document for printing.",
                        details="The document could not be converted to a printable format.",
                    )
                    result.connect("retry-requested", retry)
                    result.present(self)
                    return False

                cups_options = self._settings.to_cups_options(caps)

                job_info = self._job_manager.submit_job(
                    printer_name=printer_name,
                    filepath=prepared_path,
                    title=filename,
                    options=cups_options,
                    page_count=count.pages,
                )

                progress.close()
                save_history("Completed")

                self._app_settings.last_settings = self._settings
                self._app_settings.last_printer = printer_name

                message = f"Job #{job_info.job_id} sent to {printer_name}"
                if self._backend.sends_user_id(printer_name):
                    message += f"\nUser ID: {self._backend.user_id}"
                result = PrintResultDialog(success=True, message=message)
                result.present(self)

            except CupsError as e:
                progress.close()
                save_history("Failed")
                result = PrintResultDialog(
                    success=False,
                    message="Unable to send the print job.",
                    details=str(e),
                )
                result.connect("retry-requested", retry)
                result.present(self)

            except Exception as e:
                progress.close()
                log.exception("Print error")
                result = PrintResultDialog(
                    success=False,
                    message="An unexpected error occurred.",
                    details=str(e),
                )
                result.present(self)

            return False

        GLib.idle_add(do_print)

    # ── Dialogs ───────────────────────────────────────────────────────

    def _show_printers_dialog(self) -> None:
        printers = self._backend.get_printers()
        default = self._settings.printer_name
        dialog = PrinterManagementDialog(printers=printers, default_printer=default)
        dialog.connect("printer-selected", lambda d, name: self._settings_panel.select_printer(name))
        dialog.connect("refresh-requested", lambda d: self._on_refresh_printers(None))
        dialog.present(self)

    def _show_queue(self) -> None:
        dialog = PrintQueueDialog(self._job_manager)
        dialog.present(self)

    def _show_history_dialog(self) -> None:
        dialog = PrintHistoryDialog(self._history_mgr)
        dialog.present(self)

    def _show_preferences_dialog(self) -> None:
        dialog = PreferencesDialog(self, on_identity_changed=self._apply_user_id)
        dialog.present(self)

    def _apply_user_id(self) -> None:
        self._backend.set_user_id(self._app_settings.user_id, self._app_settings.send_user_id)

    def _show_printer_settings(self) -> None:
        printer = self._settings_panel.get_selected_printer()
        if not printer:
            self.show_toast("No printer selected")
            return
        dialog = PrinterSettingsDialog(self._backend, printer.name, paper_name=self._settings.paper_size_name)
        # Paused state, default tray and paper may all have changed
        dialog.connect("closed", lambda _dialog: self._on_refresh_printers(None))
        dialog.present(self)

    # ── Shortcuts ─────────────────────────────────────────────────────

    def _show_shortcuts(self) -> None:
        shortcuts = Gtk.ShortcutsWindow(transient_for=self, modal=True)

        section = Gtk.ShortcutsSection(section_name="shortcuts", title="Shortcuts")
        section.set_visible(True)

        group = Gtk.ShortcutsGroup(title="General")
        group.set_visible(True)

        shortcuts_data = [
            ("<Control>o", "Add files"),
            ("<Control>p", "Print"),
            ("<Control>r", "Refresh printers"),
            ("Delete", "Remove selected file"),
            ("<Control><Shift>p", "Print queue / jobs"),
            ("<Control>comma", "Preferences"),
            ("Escape", "Cancel / Close"),
        ]

        for accel, desc in shortcuts_data:
            shortcut = Gtk.ShortcutsShortcut(
                accelerator=accel,
                title=desc,
            )
            shortcut.set_visible(True)
            group.append(shortcut)

        section.append(group)
        shortcuts.add_section(section)
        shortcuts.present()

    # ── UI State ──────────────────────────────────────────────────────

    def _job_totals(self) -> tuple[int, int]:
        """Pages (one copy) and sheets of paper (all copies) across every file."""
        pages = sheets = 0
        for item in self._file_list.items:
            count = self._layout_engine.count_document(item.document, self._settings)
            pages += count.pages
            sheets += count.total_sheets
        return pages, sheets

    def _update_summary(self) -> None:
        """Update the bottom summary bar with current state."""
        items = self._file_list.items
        pages, sheets = self._job_totals()

        has_valid = any(
            item.document and item.document.is_valid
            for item in items
        )
        has_printer = self._settings_panel.get_selected_printer() is not None

        self._summary_bar.update(
            file_count=len(items),
            page_count=pages,
            sheet_count=sheets,
            settings=self._settings,
            printer_name=self._settings.printer_name,
            has_valid_files=has_valid,
            has_printer=has_printer,
        )

    # ── Window State ──────────────────────────────────────────────────

    def _on_close_request(self, window) -> bool:
        w, h = self.get_default_size()
        self._app_settings.window_width = w
        self._app_settings.window_height = h
        self._app_settings.last_settings = self._settings
        self._print_preparer.cleanup()
        return False

    # ── Public API for CLI file loading ───────────────────────────────

    def add_files(self, filepaths: list[str]) -> None:
        """Add files programmatically (e.g., from CLI arguments)."""
        for fp in filepaths:
            if os.path.isfile(fp):
                self._file_list.add_file(fp)
