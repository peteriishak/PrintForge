"""File list widget — manages files queued for printing with proper drag & drop.

Features:
- Full drop zone: clicking ANYWHERE opens the file chooser
- Desktop drag & drop from Nautilus, file managers, browsers
- Multiple simultaneous file drops
- Visual drag-over state
- Compact file list after files are added
- File reordering via drag
- Per-file remove button
- Context menu (right-click)
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Gdk, Gio, GObject, GLib, Pango

from printforge.documents.base import Document, DocumentFactory, is_supported, SUPPORTED_EXTENSIONS
from printforge.utils.formatting import format_file_size, format_dimensions

log = logging.getLogger(__name__)


class FileItem(GObject.Object):
    """Represents a file in the print queue."""

    __gtype_name__ = "PrintForgeFileItem"

    def __init__(self, filepath: str, document: Optional[Document] = None) -> None:
        super().__init__()
        self.filepath = filepath
        self.document = document
        self.filename = os.path.basename(filepath)

    @property
    def type_icon(self) -> str:
        if self.document:
            ft = self.document.file_type
            if ft in ("image", "svg"):
                return "image-x-generic-symbolic"
            elif ft == "pdf":
                return "x-office-document-symbolic"
            elif ft == "office":
                ext = os.path.splitext(self.filepath)[1].lower()
                if ext in (".ods", ".xlsx", ".xls"):
                    return "x-office-spreadsheet-symbolic"
                elif ext in (".odp", ".pptx", ".ppt"):
                    return "x-office-presentation-symbolic"
                return "x-office-document-symbolic"
            elif ft == "postscript":
                return "printer-symbolic"
            elif ft == "text":
                ext = os.path.splitext(self.filepath)[1].lower()
                if ext in (".md", ".markdown", ".txt", ".log"):
                    return "text-x-generic-symbolic"
                return "text-x-script-symbolic"
        return "text-x-generic-symbolic"

    @property
    def format_name(self) -> str:
        """Short format name like 'JPEG', 'PDF', 'ODT', 'Word', 'Markdown'."""
        ext = os.path.splitext(self.filepath)[1].lower()
        names = {
            # Images
            ".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".jpe": "JPEG", ".jfif": "JPEG",
            ".webp": "WebP", ".bmp": "BMP", ".dib": "BMP", ".tiff": "TIFF", ".tif": "TIFF",
            ".gif": "GIF", ".ico": "ICO", ".cur": "CUR", ".icns": "ICNS", ".tga": "TGA",
            ".ppm": "PPM", ".pgm": "PGM", ".pbm": "PBM", ".pnm": "PNM", ".pcx": "PCX",
            ".psd": "PSD", ".xbm": "XBM", ".xpm": "XPM", ".dds": "DDS", ".apng": "APNG",
            ".jp2": "JPEG 2000", ".j2k": "JPEG 2000", ".svg": "SVG", ".svgz": "SVGZ",
            # PDFs & PostScript
            ".pdf": "PDF", ".ps": "PostScript", ".eps": "EPS",
            # Office
            ".odt": "ODT", ".docx": "Word", ".doc": "Word", ".rtf": "RTF",
            ".ods": "Calc", ".xlsx": "Excel", ".xls": "Excel",
            ".odp": "Impress", ".pptx": "PowerPoint", ".ppt": "PowerPoint",
            # Markdown & Text
            ".txt": "Text", ".log": "Log", ".md": "Markdown", ".markdown": "Markdown",
            # Code & Configs
            ".py": "Python", ".sh": "Shell", ".bash": "Bash", ".zsh": "Zsh",
            ".c": "C", ".h": "C Header", ".cpp": "C++", ".hpp": "C++", ".cc": "C++", ".cxx": "C++",
            ".rs": "Rust", ".go": "Go", ".js": "JavaScript", ".ts": "TypeScript",
            ".jsx": "React JSX", ".tsx": "React TSX", ".html": "HTML", ".htm": "HTML",
            ".css": "CSS", ".sql": "SQL", ".json": "JSON", ".yaml": "YAML", ".yml": "YAML",
            ".toml": "TOML", ".xml": "XML", ".ini": "Config", ".conf": "Config", ".cfg": "Config",
            ".csv": "CSV", ".tsv": "TSV", ".diff": "Diff", ".patch": "Patch",
        }
        return names.get(ext, ext.upper().lstrip("."))

    @property
    def details_text(self) -> str:
        parts = [self.format_name]
        if self.document and self.document.is_valid:
            doc = self.document
            if doc.file_type in ("image", "svg"):
                w, h = doc.dimensions
                parts.append(format_dimensions(int(w), int(h)))
            elif doc.file_type in ("pdf", "office", "postscript"):
                parts.append(f"{doc.page_count} page{'s' if doc.page_count != 1 else ''}")
            elif doc.file_type == "text":
                from printforge.documents.text_doc import TextDocument
                if isinstance(doc, TextDocument):
                    parts.append(f"{doc.line_count} lines")
        parts.append(format_file_size(os.path.getsize(self.filepath) if os.path.exists(self.filepath) else 0))
        return "  ·  ".join(parts)


class FileListWidget(Gtk.Box):
    """Widget for displaying and managing files to print.

    When empty: shows a large clickable drop zone
    When populated: shows a compact file list with an Add button
    """

    __gtype_name__ = "PrintForgeFileList"

    __gsignals__ = {
        "file-added": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "file-removed": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "file-selected": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "files-cleared": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("file-list-container")

        self._items: list[FileItem] = []
        self._selected_index: int = -1

        self._build_ui()
        self._setup_drag_drop()
        self._show_empty_state()

    def _build_ui(self) -> None:
        # ── Stack for empty/list states ───────────────────────────────
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(200)
        self._stack.set_vhomogeneous(False)  # a short file list shouldn't take the drop zone's height
        self.append(self._stack)

        # ══════════════════════════════════════════════════════════════
        # EMPTY STATE — Full clickable drop zone
        # ══════════════════════════════════════════════════════════════
        self._empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._empty_box.set_valign(Gtk.Align.CENTER)
        self._empty_box.set_halign(Gtk.Align.FILL)
        self._empty_box.set_vexpand(True)
        self._empty_box.add_css_class("drop-zone")
        self._empty_box.set_cursor_from_name("pointer")

        # Make ENTIRE empty box clickable
        click_gesture = Gtk.GestureClick()
        click_gesture.connect("pressed", self._on_drop_zone_clicked)
        self._empty_box.add_controller(click_gesture)

        # Icon
        empty_icon = Gtk.Image.new_from_icon_name("folder-open-symbolic")
        empty_icon.set_pixel_size(48)
        empty_icon.add_css_class("drop-zone-icon")
        self._empty_box.append(empty_icon)

        # Primary text
        primary = Gtk.Label(label="Drop files here")
        primary.add_css_class("drop-zone-primary")
        self._empty_box.append(primary)

        # Secondary text
        secondary = Gtk.Label(label="or click to browse")
        secondary.add_css_class("drop-zone-secondary")
        self._empty_box.append(secondary)

        # Supported formats
        formats = Gtk.Label(label="Images, PDFs, office documents, PostScript, text and code")
        formats.add_css_class("drop-zone-formats")
        self._empty_box.append(formats)

        self._stack.add_named(self._empty_box, "empty")

        # ══════════════════════════════════════════════════════════════
        # LIST STATE — Compact file list with header
        # ══════════════════════════════════════════════════════════════
        list_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        list_container.add_css_class("file-list-populated")

        # Header row: "Files" title, file count, and Remove All
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.add_css_class("file-list-header")

        title = Gtk.Label(label="Files", halign=Gtk.Align.START)
        title.add_css_class("heading")
        header.append(title)

        self._file_count_label = Gtk.Label(label="", halign=Gtk.Align.START, hexpand=True)
        self._file_count_label.add_css_class("dim-label")
        header.append(self._file_count_label)

        self._clear_btn = Gtk.Button.new_from_icon_name("edit-clear-all-symbolic")
        self._clear_btn.add_css_class("flat")
        self._clear_btn.connect("clicked", self._on_clear_all)
        self._clear_btn.set_sensitive(False)
        self._clear_btn.set_tooltip_text("Remove All Files")
        header.append(self._clear_btn)

        list_container.append(header)

        # Scrollable file list
        self._list_scroll = Gtk.ScrolledWindow()
        self._list_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._list_scroll.set_propagate_natural_height(True)
        self._list_scroll.set_max_content_height(180)

        self._list_box = Gtk.ListBox()
        self._list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._list_box.add_css_class("navigation-sidebar")
        self._list_box.connect("row-selected", self._on_row_selected)
        self._list_scroll.set_child(self._list_box)

        list_container.append(self._list_scroll)

        self._stack.add_named(list_container, "list")

    def _setup_drag_drop(self) -> None:
        """Set up drag-and-drop file acceptance on the ENTIRE widget."""
        drop_target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop_target.connect("drop", self._on_drop)
        drop_target.connect("enter", self._on_drag_enter)
        drop_target.connect("leave", self._on_drag_leave)
        drop_target.connect("motion", self._on_drag_motion)
        # Attach to the ENTIRE widget, not just the empty box
        self.add_controller(drop_target)

    def _on_drag_enter(self, target, x, y):
        """Visual feedback when files are dragged over."""
        self.add_css_class("drag-hover")
        self._empty_box.add_css_class("drag-hover")
        return Gdk.DragAction.COPY

    def _on_drag_motion(self, target, x, y):
        """Continue showing drag feedback during motion."""
        return Gdk.DragAction.COPY

    def _on_drag_leave(self, target):
        """Remove drag feedback."""
        self.remove_css_class("drag-hover")
        self._empty_box.remove_css_class("drag-hover")

    def _on_drop(self, target, value, x, y) -> bool:
        """Handle dropped files."""
        self.remove_css_class("drag-hover")
        self._empty_box.remove_css_class("drag-hover")

        files = value.get_files()
        added = False
        unsupported = []

        for gfile in files:
            path = gfile.get_path()
            if path and os.path.isfile(path):
                if is_supported(path):
                    self.add_file(path)
                    added = True
                else:
                    unsupported.append(os.path.basename(path))
                    log.warning("Unsupported file: %s", path)

        # Show feedback for unsupported files
        if unsupported:
            self._show_unsupported_toast(unsupported)

        return added

    def _show_unsupported_toast(self, filenames: list[str]) -> None:
        """Show a toast for unsupported file types."""
        window = self.get_root()
        if hasattr(window, "show_toast"):
            if len(filenames) == 1:
                window.show_toast(f"Unsupported file type: {filenames[0]}")
            else:
                window.show_toast(f"{len(filenames)} files have unsupported formats")
        elif isinstance(window, Gtk.Window):
            from printforge.ui.dialogs import show_unsupported_format_dialog
            ext = os.path.splitext(filenames[0])[1]
            show_unsupported_format_dialog(window, filenames[0], ext)

    def _on_drop_zone_clicked(self, gesture, n_press, x, y) -> None:
        """Clicking anywhere in the drop zone opens the file chooser."""
        self.open_file_chooser()

    # ── Public API ────────────────────────────────────────────────────

    def open_file_chooser(self) -> None:
        """Open the native file chooser dialog."""
        dialog = Gtk.FileDialog()
        dialog.set_title("Select Files to Print")

        # Build file filters
        filters = Gio.ListStore.new(Gtk.FileFilter)

        all_filter = Gtk.FileFilter()
        all_filter.set_name("All Supported Files")
        for ext in SUPPORTED_EXTENSIONS:
            all_filter.add_pattern(f"*{ext}")
            all_filter.add_pattern(f"*{ext.upper()}")
        filters.append(all_filter)

        doc_filter = Gtk.FileFilter()
        doc_filter.set_name("PDF & Office Documents")
        for ext in (".pdf", ".odt", ".docx", ".doc", ".rtf", ".ods", ".xlsx", ".xls", ".odp", ".pptx", ".ppt", ".ps", ".eps"):
            doc_filter.add_pattern(f"*{ext}")
            doc_filter.add_pattern(f"*{ext.upper()}")
        filters.append(doc_filter)

        img_filter = Gtk.FileFilter()
        img_filter.set_name("Images & Graphics")
        for ext in (".png", ".jpg", ".jpeg", ".jpe", ".jfif", ".webp", ".bmp", ".tiff", ".tif", ".gif", ".ico", ".svg", ".svgz", ".tga", ".ppm"):
            img_filter.add_pattern(f"*{ext}")
            img_filter.add_pattern(f"*{ext.upper()}")
        filters.append(img_filter)

        code_filter = Gtk.FileFilter()
        code_filter.set_name("Markdown & Source Code")
        for ext in (".md", ".markdown", ".py", ".sh", ".bash", ".zsh", ".c", ".h", ".cpp", ".hpp", ".rs", ".go", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".json", ".yaml", ".yml", ".toml", ".xml", ".ini", ".conf"):
            code_filter.add_pattern(f"*{ext}")
            code_filter.add_pattern(f"*{ext.upper()}")
        filters.append(code_filter)

        txt_filter = Gtk.FileFilter()
        txt_filter.set_name("Text Documents (*.txt, *.log)")
        txt_filter.add_pattern("*.txt")
        txt_filter.add_pattern("*.TXT")
        txt_filter.add_pattern("*.log")
        txt_filter.add_pattern("*.LOG")
        filters.append(txt_filter)

        dialog.set_filters(filters)
        dialog.set_default_filter(all_filter)

        window = self.get_root()
        dialog.open_multiple(window, None, self._on_files_selected)

    def add_file(self, filepath: str) -> Optional[FileItem]:
        """Add a file to the list. Returns the FileItem or None if failed."""
        if not os.path.isfile(filepath):
            return None

        if not is_supported(filepath):
            return None

        # Don't add duplicates
        for item in self._items:
            if item.filepath == filepath:
                return item

        # Create document
        doc = DocumentFactory.create(filepath)
        item = FileItem(filepath, doc)
        self._items.append(item)

        # Add to list box
        row = self._create_file_row(item, len(self._items) - 1)
        self._list_box.append(row)

        self._update_state()

        # Auto-select the first file
        if len(self._items) == 1:
            self._list_box.select_row(self._list_box.get_row_at_index(0))

        self.emit("file-added", item)
        return item

    def remove_file(self, index: int) -> None:
        """Remove a file by index."""
        if 0 <= index < len(self._items):
            item = self._items.pop(index)
            row = self._list_box.get_row_at_index(index)
            if row:
                self._list_box.remove(row)
            self.emit("file-removed", item)

            # Re-select if needed
            if self._items:
                new_idx = min(index, len(self._items) - 1)
                row = self._list_box.get_row_at_index(new_idx)
                if row:
                    self._list_box.select_row(row)
            else:
                self._selected_index = -1

            # Rebuild to fix indices
            self._rebuild_list()
            self._update_state()

    def clear_all(self) -> None:
        """Remove all files."""
        self._items.clear()
        self._selected_index = -1

        # Clear list box
        while True:
            row = self._list_box.get_row_at_index(0)
            if row is None:
                break
            self._list_box.remove(row)

        self._update_state()
        self.emit("files-cleared")

    @property
    def items(self) -> list[FileItem]:
        return list(self._items)

    @property
    def selected_item(self) -> Optional[FileItem]:
        if 0 <= self._selected_index < len(self._items):
            return self._items[self._selected_index]
        return None

    @property
    def selected_index(self) -> int:
        return self._selected_index

    # ── Internal ──────────────────────────────────────────────────────

    def _create_file_row(self, item: FileItem, index: int) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.set_activatable(True)

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        hbox.add_css_class("file-item")

        # Icon
        icon = Gtk.Image.new_from_icon_name(item.type_icon)
        icon.set_pixel_size(28)
        icon.add_css_class("file-item-icon")
        hbox.append(icon)

        # Info
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        info_box.set_hexpand(True)
        info_box.set_valign(Gtk.Align.CENTER)

        name_label = Gtk.Label(label=item.filename)
        name_label.add_css_class("file-item-name")
        name_label.set_halign(Gtk.Align.START)
        name_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        name_label.set_max_width_chars(40)
        info_box.append(name_label)

        details_label = Gtk.Label(label=item.details_text)
        details_label.add_css_class("file-item-details")
        details_label.set_halign(Gtk.Align.START)
        info_box.append(details_label)

        # Show error if document failed to load
        if item.document and not item.document.is_valid:
            err_label = Gtk.Label(label=f"⚠ {item.document.error}")
            err_label.add_css_class("error")
            err_label.add_css_class("caption")
            err_label.set_halign(Gtk.Align.START)
            err_label.set_wrap(True)
            info_box.append(err_label)

        hbox.append(info_box)

        # Remove button
        remove_btn = Gtk.Button.new_from_icon_name("window-close-symbolic")
        remove_btn.add_css_class("flat")
        remove_btn.add_css_class("circular")
        remove_btn.add_css_class("file-item-remove")
        remove_btn.set_valign(Gtk.Align.CENTER)
        remove_btn.set_tooltip_text("Remove file")
        remove_btn.connect("clicked", lambda btn, idx=index: self._on_remove_clicked(idx))
        hbox.append(remove_btn)

        # Right-click context menu
        ctx_gesture = Gtk.GestureClick(button=3)  # Right click
        ctx_gesture.connect("pressed", self._on_context_menu, item, index)
        row.add_controller(ctx_gesture)

        row.set_child(hbox)
        return row

    def _on_context_menu(self, gesture, n_press, x, y, item: FileItem, index: int) -> None:
        """Show context menu for a file item."""
        menu = Gio.Menu()
        # For now, basic actions
        menu.append("Remove", f"win.remove-file")

        popover = Gtk.PopoverMenu.new_from_model(menu)
        popover.set_parent(gesture.get_widget())
        popover.set_pointing_to(Gdk.Rectangle())
        popover.popup()

    def _on_remove_clicked(self, index: int) -> None:
        self.remove_file(index)

    def _rebuild_list(self) -> None:
        """Rebuild the list box from the items list."""
        while True:
            row = self._list_box.get_row_at_index(0)
            if row is None:
                break
            self._list_box.remove(row)

        for i, item in enumerate(self._items):
            row = self._create_file_row(item, i)
            self._list_box.append(row)

        # Re-select
        if self._items and self._selected_index >= 0:
            idx = min(self._selected_index, len(self._items) - 1)
            row = self._list_box.get_row_at_index(idx)
            if row:
                self._list_box.select_row(row)

    def _on_row_selected(self, list_box, row) -> None:
        if row is None:
            self._selected_index = -1
        else:
            self._selected_index = row.get_index()

        item = self.selected_item
        if item:
            self.emit("file-selected", item)

    def _on_files_selected(self, dialog, result) -> None:
        try:
            files = dialog.open_multiple_finish(result)
            if files:
                for i in range(files.get_n_items()):
                    gfile = files.get_item(i)
                    path = gfile.get_path()
                    if path:
                        self.add_file(path)
        except GLib.Error:
            pass  # User cancelled

    def _on_clear_all(self, button) -> None:
        self.clear_all()

    def _show_empty_state(self) -> None:
        self._stack.set_visible_child_name("empty")

    def _show_list_state(self) -> None:
        self._stack.set_visible_child_name("list")

    def _update_state(self) -> None:
        count = len(self._items)
        if count == 0:
            self._show_empty_state()
            self._file_count_label.set_text("")
            self._clear_btn.set_sensitive(False)
        else:
            self._show_list_state()
            self._file_count_label.set_text(f"{count} file{'s' if count != 1 else ''}")
            self._clear_btn.set_sensitive(True)
