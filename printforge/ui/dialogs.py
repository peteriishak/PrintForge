"""Application dialogs — print progress, results, about, print queue, etc."""

from __future__ import annotations

import logging

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GObject, Adw

from printforge import __version__, __app_name__
from printforge.printing.job import PrintJobInfo, JobState

log = logging.getLogger(__name__)


# ── Print Progress Dialog ─────────────────────────────────────────────

class PrintProgressDialog(Adw.Dialog):
    """Shows progress during print job submission."""

    __gtype_name__ = "PrintForgeProgressDialog"

    def __init__(self, filename: str, printer_name: str, pages: int, sheets: int = 0) -> None:
        super().__init__()
        self.set_title("Printing")
        self.set_content_width(380)
        self.set_content_height(220)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)
        box.set_valign(Gtk.Align.CENTER)

        # Spinner
        spinner = Gtk.Spinner()
        spinner.set_spinning(True)
        spinner.set_size_request(48, 48)
        spinner.set_halign(Gtk.Align.CENTER)
        box.append(spinner)

        # Title
        title = Gtk.Label(label="Sending print job…")
        title.add_css_class("title-3")
        box.append(title)

        # Details
        amount = f"Pages: {pages}"
        if sheets and sheets != pages:
            amount += f"  ·  Sheets of paper: {sheets}"
        details = Gtk.Label(label=f"{filename}\nPrinter: {printer_name}\n{amount}")
        details.set_justify(Gtk.Justification.CENTER)
        details.add_css_class("dim-label")
        box.append(details)

        # Progress bar
        self._progress = Gtk.ProgressBar()
        self._progress.set_fraction(0.0)
        self._progress.pulse()
        box.append(self._progress)

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(False)
        header.set_show_start_title_buttons(False)
        toolbar.add_top_bar(header)
        toolbar.set_content(box)

        self.set_child(toolbar)

    def set_progress(self, fraction: float) -> None:
        self._progress.set_fraction(fraction)

    def pulse(self) -> None:
        self._progress.pulse()


# ── Print Result Dialog ───────────────────────────────────────────────

class PrintResultDialog(Adw.Dialog):
    """Shows the result of a print job (success or failure)."""

    __gtype_name__ = "PrintForgeResultDialog"

    __gsignals__ = {
        "retry-requested": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "done": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, success: bool, message: str = "", details: str = "") -> None:
        super().__init__()
        self.set_title("Print Result")
        self.set_content_width(400)
        self.set_content_height(280)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(32)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)
        box.set_valign(Gtk.Align.CENTER)

        if success:
            icon = Gtk.Label(label="✓")
            icon.add_css_class("print-success-icon")
            box.append(icon)

            title = Gtk.Label(label="Print job sent successfully")
            title.add_css_class("title-3")
            box.append(title)

            if message:
                msg = Gtk.Label(label=message)
                msg.add_css_class("dim-label")
                box.append(msg)

            btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            btn_box.set_halign(Gtk.Align.CENTER)
            btn_box.set_margin_top(8)

            done_btn = Gtk.Button(label="Done")
            done_btn.add_css_class("pill")
            done_btn.add_css_class("suggested-action")
            done_btn.connect("clicked", lambda b: self._on_done())
            btn_box.append(done_btn)

            box.append(btn_box)
        else:
            icon = Gtk.Label(label="⚠")
            icon.add_css_class("print-error-icon")
            box.append(icon)

            title = Gtk.Label(label="Printing failed")
            title.add_css_class("title-3")
            box.append(title)

            if message:
                msg = Gtk.Label(label=message)
                msg.set_wrap(True)
                msg.set_justify(Gtk.Justification.CENTER)
                box.append(msg)

            if details:
                detail_frame = Gtk.Frame()
                detail_label = Gtk.Label(label=details)
                detail_label.add_css_class("error-details")
                detail_label.set_wrap(True)
                detail_label.set_selectable(True)
                detail_frame.set_child(detail_label)
                box.append(detail_frame)

            btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            btn_box.set_halign(Gtk.Align.CENTER)
            btn_box.set_margin_top(8)

            retry_btn = Gtk.Button(label="Retry")
            retry_btn.add_css_class("pill")
            retry_btn.add_css_class("suggested-action")
            retry_btn.connect("clicked", lambda b: self._on_retry())
            btn_box.append(retry_btn)

            cancel_btn = Gtk.Button(label="Close")
            cancel_btn.add_css_class("pill")
            cancel_btn.connect("clicked", lambda b: self._on_done())
            btn_box.append(cancel_btn)

            box.append(btn_box)

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(True)
        toolbar.add_top_bar(header)
        toolbar.set_content(box)

        self.set_child(toolbar)

    def _on_retry(self) -> None:
        self.emit("retry-requested")
        self.close()

    def _on_done(self) -> None:
        self.emit("done")
        self.close()


# ── About Dialog ──────────────────────────────────────────────────────

def show_about_dialog(parent: Gtk.Window) -> None:
    """Show the application About dialog."""
    about = Adw.AboutDialog(
        application_name=__app_name__,
        application_icon="printer-symbolic",
        version=__version__,
        developer_name="Peter Habib",
        license_type=Gtk.License.GPL_3_0,
        comments="A modern, polished printing application for Fedora Linux.\n\n"
                 "Easily print images and documents with full control over "
                 "layout, scaling, margins, and quality.",
        website="https://github.com/peteriishak/PrintForge",
        issue_url="https://github.com/peteriishak/PrintForge/issues",
        developers=["Peter Habib https://github.com/peteriishak"],
        copyright="© 2026 Peter Habib",
    )
    about.present(parent)


# ── Print Queue / Jobs Dialog ─────────────────────────────────────────

class PrintQueueDialog(Adw.Dialog):
    """Shows the CUPS print queue with Printing, Queued, and Completed sections."""

    __gtype_name__ = "PrintForgeQueueDialog"

    def __init__(self, job_manager) -> None:
        super().__init__()
        self.set_title("Print Jobs")
        self.set_content_width(580)
        self.set_content_height(480)

        self._job_manager = job_manager

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()

        refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh_btn.set_tooltip_text("Refresh queue")
        refresh_btn.connect("clicked", lambda b: self._refresh())
        header.pack_end(refresh_btn)

        clear_completed_btn = Gtk.Button(label="Clear Completed")
        clear_completed_btn.add_css_class("flat")
        clear_completed_btn.connect("clicked", lambda b: self._clear_completed())
        header.pack_start(clear_completed_btn)

        toolbar.add_top_bar(header)

        # Content with sections
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self._content_box.set_margin_start(16)
        self._content_box.set_margin_end(16)
        self._content_box.set_margin_top(16)
        self._content_box.set_margin_bottom(16)

        # Printing group
        self._printing_group = Adw.PreferencesGroup(title="Printing")
        self._content_box.append(self._printing_group)

        # Queued group
        self._queued_group = Adw.PreferencesGroup(title="Queued")
        self._content_box.append(self._queued_group)

        # Completed group
        self._completed_group = Adw.PreferencesGroup(title="Completed")
        self._content_box.append(self._completed_group)

        # Empty label
        self._empty_label = Gtk.Label(label="No active or recent print jobs")
        self._empty_label.add_css_class("dim-label")
        self._empty_label.set_margin_top(32)
        self._content_box.append(self._empty_label)

        scroll.set_child(self._content_box)
        toolbar.set_content(scroll)
        self.set_child(toolbar)

        self._refresh()

    def _refresh(self) -> None:
        """Refresh the job list by category."""
        # Clear groups
        for grp in (self._printing_group, self._queued_group, self._completed_group):
            while True:
                child = grp.get_first_child()
                # Find rows inside the group
                break

        # Remove existing rows from preferences groups by creating fresh groups
        self._content_box.remove(self._printing_group)
        self._content_box.remove(self._queued_group)
        self._content_box.remove(self._completed_group)
        self._content_box.remove(self._empty_label)

        self._printing_group = Adw.PreferencesGroup(title="Printing")
        self._queued_group = Adw.PreferencesGroup(title="Queued")
        self._completed_group = Adw.PreferencesGroup(title="Completed")

        jobs = self._job_manager.refresh_all()

        printing_jobs = [j for j in jobs if j.state == JobState.PROCESSING]
        queued_jobs = [j for j in jobs if j.state in (JobState.PENDING, JobState.HELD)]
        completed_jobs = [j for j in jobs if j.state.is_finished]

        has_any = False

        if printing_jobs:
            has_any = True
            for job in printing_jobs:
                row = self._create_job_row(job, is_active=True)
                self._printing_group.add(row)
            self._content_box.append(self._printing_group)

        if queued_jobs:
            has_any = True
            for job in queued_jobs:
                row = self._create_job_row(job, is_active=True)
                self._queued_group.add(row)
            self._content_box.append(self._queued_group)

        if completed_jobs:
            has_any = True
            for job in completed_jobs:
                row = self._create_job_row(job, is_active=False)
                self._completed_group.add(row)
            self._content_box.append(self._completed_group)

        self._empty_label.set_visible(not has_any)
        self._content_box.append(self._empty_label)

    def _create_job_row(self, job: PrintJobInfo, is_active: bool) -> Adw.ActionRow:
        row = Adw.ActionRow(title=job.title or f"Job #{job.job_id}")
        subtitle_parts = [job.printer_name]
        if job.pages > 0:
            subtitle_parts.append("1 page" if job.pages == 1 else f"{job.pages} pages")
        row.set_subtitle(" · ".join(subtitle_parts))

        # Status badge
        status = Gtk.Label(label=job.state.display_name)
        status.add_css_class("queue-job-status")
        if job.state == JobState.PROCESSING:
            status.add_css_class("processing")
            # Add progress bar in suffix
            pbar = Gtk.ProgressBar()
            pbar.set_size_request(80, -1)
            pbar.set_valign(Gtk.Align.CENTER)
            pbar.pulse()
            row.add_suffix(pbar)
        elif job.state == JobState.COMPLETED:
            status.add_css_class("completed")
        elif job.state in (JobState.ABORTED, JobState.CANCELED):
            status.add_css_class("failed")

        status.set_valign(Gtk.Align.CENTER)
        row.add_suffix(status)

        if is_active:
            cancel_btn = Gtk.Button.new_from_icon_name("process-stop-symbolic")
            cancel_btn.add_css_class("flat")
            cancel_btn.set_valign(Gtk.Align.CENTER)
            cancel_btn.set_tooltip_text("Cancel job")
            cancel_btn.connect("clicked", lambda b, jid=job.job_id: self._cancel_job(jid))
            row.add_suffix(cancel_btn)

        return row

    def _cancel_job(self, job_id: int) -> None:
        self._job_manager.cancel_job(job_id)
        self._refresh()

    def _clear_completed(self) -> None:
        self._job_manager.remove_completed()
        self._refresh()


# ── Printer Management Dialog ─────────────────────────────────────────

class PrinterManagementDialog(Adw.Dialog):
    """Lists all detected printers, status, capabilities, and settings."""

    __gtype_name__ = "PrintForgePrinterDialog"

    __gsignals__ = {
        "printer-selected": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "refresh-requested": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, printers: list, default_printer: str = "") -> None:
        super().__init__()
        self.set_title("Printer Management")
        self.set_content_width(560)
        self.set_content_height(480)

        self._printers = printers
        self._default_printer = default_printer

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()

        refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh_btn.set_tooltip_text("Refresh printers")
        refresh_btn.connect("clicked", lambda b: self.emit("refresh-requested"))
        header.pack_end(refresh_btn)

        system_btn = Gtk.Button(label="System Settings")
        system_btn.add_css_class("flat")
        system_btn.set_tooltip_text("Open system printer settings")
        system_btn.connect("clicked", self._on_open_system_settings)
        header.pack_start(system_btn)

        toolbar.add_top_bar(header)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self._group = Adw.PreferencesGroup(title="Available Printers")
        self._group.set_margin_start(16)
        self._group.set_margin_end(16)
        self._group.set_margin_top(16)
        self._group.set_margin_bottom(16)

        for p in self._printers:
            row = Adw.ActionRow(title=p.name)
            status_text = p.state.display_name if hasattr(p, "state") else "Ready"
            location = f" · {p.location}" if hasattr(p, "location") and p.location else ""
            row.set_subtitle(f"{status_text}{location}")

            # Status indicator
            is_default = (p.name == self._default_printer or getattr(p, "is_default", False))
            if is_default:
                badge = Gtk.Label(label="Default")
                badge.add_css_class("queue-job-status")
                badge.add_css_class("completed")
                badge.set_valign(Gtk.Align.CENTER)
                row.add_suffix(badge)

            # Select / Set default button
            btn = Gtk.Button(label="Use" if not is_default else "Selected")
            btn.add_css_class("flat")
            btn.set_sensitive(not is_default)
            btn.set_valign(Gtk.Align.CENTER)
            btn.connect("clicked", lambda b, pname=p.name: self._on_select_printer(pname))
            row.add_suffix(btn)

            self._group.add(row)

        scroll.set_child(self._group)
        toolbar.set_content(scroll)
        self.set_child(toolbar)

    def _on_select_printer(self, name: str) -> None:
        self.emit("printer-selected", name)
        self.close()

    def _on_open_system_settings(self, _btn) -> None:
        import subprocess
        for cmd in (["gnome-control-center", "printers"], ["system-config-printer"]):
            try:
                subprocess.Popen(cmd)
                return
            except FileNotFoundError:
                pass


# ── Print History Dialog ──────────────────────────────────────────────

class PrintHistoryDialog(Adw.Dialog):
    """Shows past print jobs with option to reprint or inspect."""

    __gtype_name__ = "PrintForgeHistoryDialog"

    __gsignals__ = {
        "reprint-requested": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }

    def __init__(self, history_manager) -> None:
        super().__init__()
        self.set_title("Print History")
        self.set_content_width(580)
        self.set_content_height(480)

        self._history_mgr = history_manager

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()

        clear_btn = Gtk.Button(label="Clear History")
        clear_btn.add_css_class("flat")
        clear_btn.connect("clicked", lambda b: self._clear())
        header.pack_end(clear_btn)

        toolbar.add_top_bar(header)

        self._scroll = Gtk.ScrolledWindow()
        self._scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        toolbar.set_content(self._scroll)
        self.set_child(toolbar)

        self._refresh()

    def _refresh(self) -> None:
        entries = self._history_mgr.get_entries()

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.set_margin_start(16)
        content.set_margin_end(16)
        content.set_margin_top(16)
        content.set_margin_bottom(16)

        if not entries:
            empty = Gtk.Label(label="No print history yet")
            empty.add_css_class("dim-label")
            empty.set_margin_top(48)
            content.append(empty)
            self._scroll.set_child(content)
            return

        # Group by relative date
        groups: dict[str, list] = {}
        for entry in entries:
            groups.setdefault(entry.relative_date, []).append(entry)

        for date_label, group_entries in groups.items():
            grp = Adw.PreferencesGroup(title=date_label)
            for entry in group_entries:
                row = Adw.ActionRow(title=entry.filename)
                row.set_subtitle(f"{entry.summary} · {entry.printer_name} · {entry.time_str}")

                # Status icon
                status_icon = "emblem-ok-symbolic" if entry.status == "Completed" else "dialog-warning-symbolic"
                img = Gtk.Image.new_from_icon_name(status_icon)
                img.set_valign(Gtk.Align.CENTER)
                row.add_suffix(img)

                # Delete entry button
                del_btn = Gtk.Button.new_from_icon_name("user-trash-symbolic")
                del_btn.add_css_class("flat")
                del_btn.set_valign(Gtk.Align.CENTER)
                del_btn.set_tooltip_text("Remove entry")
                del_btn.connect("clicked", lambda b, eid=entry.entry_id: self._remove_entry(eid))
                row.add_suffix(del_btn)

                grp.add(row)
            content.append(grp)

        self._scroll.set_child(content)

    def _remove_entry(self, entry_id: str) -> None:
        self._history_mgr.remove_entry(entry_id)
        self._refresh()

    def _clear(self) -> None:
        self._history_mgr.clear_history()
        self._refresh()


# ── Preferences Dialog ────────────────────────────────────────────────

class PreferencesDialog(Adw.PreferencesDialog):
    """Application preferences window with General, Preview, and Printing tabs."""

    __gtype_name__ = "PrintForgePreferencesDialog"

    def __init__(self, parent_window: Gtk.Window, on_identity_changed=None) -> None:
        super().__init__()
        self.set_title("Preferences")

        from printforge.config.settings import AppSettings
        from printforge.printing.pjl import get_device_name, panel_user_id, resolve_user_id
        self._settings = AppSettings.get()

        # ── General Tab ───────────────────────────────────────────────
        general_page = Adw.PreferencesPage(title="General", icon_name="preferences-system-symbolic")
        gen_group = Adw.PreferencesGroup(title="Defaults")

        # Default Copies
        copies_row = Adw.SpinRow.new_with_range(1, 999, 1)
        copies_row.set_title("Default Copies")
        copies_row.set_value(self._settings.default_copies)
        copies_row.connect("notify::value", lambda r, p: setattr(self._settings, "default_copies", int(r.get_value())))
        gen_group.add(copies_row)

        general_page.add(gen_group)
        self.add(general_page)

        # ── Preview Tab ───────────────────────────────────────────────
        preview_page = Adw.PreferencesPage(title="Preview", icon_name="view-preview-symbolic")
        prev_group = Adw.PreferencesGroup(title="Preview Overlays")

        margins_switch = Adw.SwitchRow(title="Show Margins", subtitle="Display page margins on preview")
        margins_switch.set_active(self._settings.show_margins)
        margins_switch.connect("notify::active", lambda r, p: setattr(self._settings, "show_margins", r.get_active()))
        prev_group.add(margins_switch)

        area_switch = Adw.SwitchRow(title="Show Printable Area", subtitle="Highlight printable boundary")
        area_switch.set_active(self._settings.show_printable_area)
        area_switch.connect("notify::active", lambda r, p: setattr(self._settings, "show_printable_area", r.get_active()))
        prev_group.add(area_switch)

        rulers_switch = Adw.SwitchRow(title="Show Rulers", subtitle="Display millimeter rulers along paper edges")
        rulers_switch.set_active(self._settings.show_rulers)
        rulers_switch.connect("notify::active", lambda r, p: setattr(self._settings, "show_rulers", r.get_active()))
        prev_group.add(rulers_switch)

        preview_page.add(prev_group)
        self.add(preview_page)

        # ── Printing Tab ──────────────────────────────────────────────
        print_page = Adw.PreferencesPage(title="Printing", icon_name="printer-symbolic")
        print_group = Adw.PreferencesGroup(title="Behavior")

        confirm_switch = Adw.SwitchRow(title="Confirm Before Printing", subtitle="Show confirmation prompt before sending")
        confirm_switch.set_active(self._settings.confirm_before_printing)
        confirm_switch.connect("notify::active", lambda r, p: setattr(self._settings, "confirm_before_printing", r.get_active()))
        print_group.add(confirm_switch)

        history_switch = Adw.SwitchRow(title="Save Print History", subtitle="Record printed files and metadata")
        history_switch.set_active(self._settings.save_history)
        history_switch.connect("notify::active", lambda r, p: setattr(self._settings, "save_history", r.get_active()))
        print_group.add(history_switch)

        refresh_switch = Adw.SwitchRow(title="Auto-refresh Printers", subtitle="Periodically check printer status")
        refresh_switch.set_active(self._settings.auto_refresh_printers)
        refresh_switch.connect("notify::active", lambda r, p: setattr(self._settings, "auto_refresh_printers", r.get_active()))
        print_group.add(refresh_switch)

        print_page.add(print_group)

        # User ID: how jobs from this computer are labelled on the printer
        identity_group = Adw.PreferencesGroup(
            title="User ID",
            description="Shown on the printer's display and in its job log, so you can tell your jobs apart.",
        )

        def identity_changed() -> None:
            shown = panel_user_id(resolve_user_id(self._settings.user_id))
            user_id_row.set_title(f"User ID — printer shows “{shown}”")
            if on_identity_changed:
                on_identity_changed()

        def on_user_id_applied(row: Adw.EntryRow) -> None:
            self._settings.user_id = row.get_text()
            identity_changed()

        user_id_row = Adw.EntryRow(show_apply_button=True)
        user_id_row.set_text(self._settings.user_id or get_device_name())
        user_id_row.set_tooltip_text(
            "Leave empty to use this computer's name. Printers show up to 8 letters and digits."
        )
        user_id_row.connect("apply", on_user_id_applied)
        identity_group.add(user_id_row)

        def on_send_toggled(row: Adw.SwitchRow, _pspec) -> None:
            self._settings.send_user_id = row.get_active()
            identity_changed()

        send_switch = Adw.SwitchRow(
            title="Send User ID to Printer",
            subtitle="For printers that show who sent a job (Ricoh, HP and similar office printers)",
        )
        send_switch.set_active(self._settings.send_user_id)
        send_switch.connect("notify::active", on_send_toggled)
        identity_group.add(send_switch)

        shown = panel_user_id(resolve_user_id(self._settings.user_id))
        user_id_row.set_title(f"User ID — printer shows “{shown}”")

        print_page.add(identity_group)
        self.add(print_page)


# ── Unsupported Format Dialog ─────────────────────────────────────────

def show_unsupported_format_dialog(parent: Gtk.Window, filename: str, extension: str) -> None:
    """Show a dialog explaining that a file format is unsupported."""
    dialog = Adw.MessageDialog(
        heading="Unsupported File Format",
        body=f'The file "{filename}" has an unsupported format ({extension}).\n\n'
             f"PrintForge currently supports:\n"
             f"• Images: PNG, JPEG, WebP, BMP, TIFF, SVG\n"
             f"• Documents: PDF, TXT",
        transient_for=parent,
    )
    dialog.add_response("ok", "OK")
    dialog.set_default_response("ok")
    dialog.present()

