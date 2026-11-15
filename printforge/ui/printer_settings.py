"""Printer Settings dialog — status, troubleshooting, maintenance and driver defaults."""

from __future__ import annotations

import logging
from typing import Callable, Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GLib

from printforge.printing import maintenance
from printforge.printing.cups_backend import CupsError
from printforge.printing.pjl import panel_user_id
from printforge.printing.ppd import PpdOption
from printforge.printing.printer import PrinterInfo, PrinterState, PrinterStatus, Severity, StatusIssue
from printforge.ui.settings_panel import OptionRow
from printforge.utils.paper import get_paper_by_name

log = logging.getLogger(__name__)

ERROR_POLICY_LABELS = {
    "stop-printer": "Pause the Printer",
    "retry-job": "Retry the Job Later",
    "retry-current-job": "Retry the Job Immediately",
    "abort-job": "Skip the Job",
}
# Beyond this a driver's option list belongs in System Settings
MAX_DRIVER_OPTIONS = 40

SEVERITY_CSS = {
    Severity.OK: "success",
    Severity.WARNING: "warning",
    Severity.ERROR: "error",
}


def _row(title: str, subtitle: str = "", **properties) -> Adw.ActionRow:
    """An action row showing `title` and `subtitle` literally (rows parse markup)."""
    return Adw.ActionRow(
        title=GLib.markup_escape_text(title), subtitle=GLib.markup_escape_text(subtitle), **properties,
    )


def _action_button(label: str, on_click: Callable[[], None], suggested: bool = False) -> Gtk.Button:
    button = Gtk.Button(label=label, valign=Gtk.Align.CENTER)
    if suggested:
        button.add_css_class("suggested-action")
    button.connect("clicked", lambda _button: on_click())
    return button


def _severity_icon(severity: Severity) -> Gtk.Image:
    icon = Gtk.Image.new_from_icon_name(severity.icon_name)
    if severity in SEVERITY_CSS:
        icon.add_css_class(SEVERITY_CSS[severity])
    return icon


class PrinterSettingsDialog(Adw.PreferencesDialog):
    """Everything for looking after one printer:

    - Status: what the printer reports, supply levels, connection details
    - Repair: diagnostics with one-click fixes, queue repairs
    - Maintenance: test, calibration, alignment and cleaning pages; driver commands
    - Defaults: the driver options every app starts from
    """

    __gtype_name__ = "PrintForgePrinterSettingsDialog"

    FIX_LABELS = {
        "resume": "Resume",
        "accept": "Accept Jobs",
        "clear-jobs": "Clear Jobs",
        "default-paper": "Fix",
        "restart-service": "Restart",
    }

    def __init__(self, backend, printer_name: str, paper_name: str = "") -> None:
        super().__init__()
        self.set_title(f"{printer_name} Settings")
        self.set_content_width(720)
        self.set_content_height(680)

        self._backend = backend
        self._printer_name = printer_name
        self._paper_name = paper_name if get_paper_by_name(paper_name) else ""
        self._status: Optional[PrinterStatus] = None
        self._groups: dict[Adw.PreferencesPage, list[Adw.PreferencesGroup]] = {}
        self._diagnosis: Optional[list[StatusIssue]] = None

        self._status_page = Adw.PreferencesPage(title="Status", icon_name="printer-symbolic")
        self._fix_page = Adw.PreferencesPage(title="Repair", icon_name="dialog-warning-symbolic")
        self._maintenance_page = Adw.PreferencesPage(title="Maintenance", icon_name="applications-utilities-symbolic")
        self._defaults_page = Adw.PreferencesPage(title="Defaults", icon_name="preferences-system-symbolic")
        for page in (self._status_page, self._fix_page, self._maintenance_page, self._defaults_page):
            self._groups[page] = []
            self.add(page)

        self._reload()

    # ── Plumbing ──────────────────────────────────────────────────────

    def _set_groups(self, page: Adw.PreferencesPage, groups: list[Adw.PreferencesGroup]) -> None:
        """Replace everything shown on `page`."""
        for group in self._groups[page]:
            page.remove(group)
        for group in groups:
            page.add(group)
        self._groups[page] = groups

    def _toast(self, message: str) -> None:
        self.add_toast(Adw.Toast(title=message, timeout=4))

    def _run(self, action: Callable[[], object], done: str = "") -> bool:
        """Run a backend action, report the outcome, and refresh what's shown."""
        try:
            result = action()
        except CupsError as e:
            self._toast(str(e))
            return False
        except Exception as e:
            log.exception("Printer action failed")
            self._toast(f"Something went wrong: {e}")
            return False
        if done:
            self._toast(done.format(result=result))
        self._reload_later()
        return True

    def _reload_later(self) -> None:
        """Refresh once the current click or selection has finished being handled.

        Rebuilding the pages destroys the very row that is reporting the change.
        """
        def refresh() -> bool:
            if self._diagnosis is not None:
                self._diagnosis = self._backend.diagnose(self._printer_name, self._paper_name)
            self._reload()
            return GLib.SOURCE_REMOVE
        GLib.idle_add(refresh)

    def _reload(self) -> None:
        self._status = self._backend.get_printer_status(self._printer_name)
        self._build_status_page()
        self._build_fix_page()
        self._build_maintenance_page()
        self._build_defaults_page()

    def _issue_row(self, issue: StatusIssue) -> Adw.ActionRow:
        row = _row(issue.title, issue.advice)
        row.add_prefix(_severity_icon(issue.severity))
        if issue.fix in self.FIX_LABELS:
            row.add_suffix(_action_button(
                self.FIX_LABELS[issue.fix], lambda: self._apply_fix(issue.fix), suggested=True,
            ))
        return row

    # ── Status ────────────────────────────────────────────────────────

    def _build_status_page(self) -> None:
        status = self._status
        if not status:
            unavailable = Adw.PreferencesGroup()
            row = _row(
                "The printer's status can't be read",
                "The print service may be stopped. Try Restart Print Service under Repair.",
            )
            row.add_prefix(_severity_icon(Severity.ERROR))
            unavailable.add(row)
            self._set_groups(self._status_page, [unavailable])
            return

        # ── Condition ──
        condition = Adw.PreferencesGroup(title="Printer")
        refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh.set_tooltip_text("Refresh Status")
        refresh.add_css_class("flat")
        refresh.set_valign(Gtk.Align.CENTER)
        refresh.connect("clicked", lambda _button: self._reload_later())
        condition.set_header_suffix(refresh)

        blocked = status.state == PrinterState.STOPPED or not status.is_accepting_jobs
        has_errors = any(issue.severity == Severity.ERROR for issue in status.issues)
        # Warnings get their own rows below; the headline only says whether it can print
        overall = Severity.ERROR if blocked or has_errors else Severity.OK
        state_row = _row(status.summary, status.state_message)
        state_row.add_prefix(_severity_icon(overall))
        if status.state == PrinterState.STOPPED:
            state_row.add_suffix(_action_button("Resume", lambda: self._apply_fix("resume"), suggested=True))
        elif not status.is_accepting_jobs:
            state_row.add_suffix(_action_button("Accept Jobs", lambda: self._apply_fix("accept"), suggested=True))
        condition.add(state_row)

        for issue in status.issues:
            if issue.fix == "resume" and status.state == PrinterState.STOPPED:
                continue  # already the headline
            condition.add(self._issue_row(issue))

        if status.queued_jobs:
            jobs = "1 job waiting" if status.queued_jobs == 1 else f"{status.queued_jobs} jobs waiting"
            jobs_row = _row(jobs)
            jobs_row.add_prefix(Gtk.Image.new_from_icon_name("view-list-symbolic"))
            condition.add(jobs_row)

        # ── Supplies ──
        supplies = Adw.PreferencesGroup(title="Supplies")
        if status.supplies:
            for supply in status.supplies:
                row = _row(supply.name)
                if supply.level < 0:
                    row.set_subtitle("Level unknown")
                else:
                    row.set_subtitle(f"{supply.level}%")
                    bar = Gtk.LevelBar(min_value=0, max_value=100, value=supply.level)
                    bar.set_size_request(160, -1)
                    bar.set_valign(Gtk.Align.CENTER)
                    row.add_suffix(bar)
                supplies.add(row)
        else:
            supplies.add(_row(
                "Supply levels aren't available",
                "This printer's driver doesn't report toner or ink levels. Check the printer's own display.",
            ))

        # ── Details ──
        details = Adw.PreferencesGroup(title="Details")
        printer = PrinterInfo(name=status.name, uri=status.uri)
        facts = [
            ("Driver", status.make_model or "Unknown"),
            ("Connection", printer.connection_type),
            ("Address", GLib.uri_unescape_string(status.uri, None) or status.uri),
        ]
        if status.location:
            facts.append(("Location", status.location))
        if self._backend.sends_user_id(status.name):
            facts.append(("User ID Shown on Printer", panel_user_id(self._backend.user_id)))
        else:
            facts.append(("User ID Shown on Printer", "Not sent to this printer"))
        for title, value in facts:
            row = _row(title, value, subtitle_selectable=True)
            row.add_css_class("property")
            details.add(row)

        self._set_groups(self._status_page, [condition, supplies, details])

    # ── Repair ────────────────────────────────────────────────────────

    def _build_fix_page(self) -> None:
        status = self._status

        # ── Diagnostics ──
        diagnostics = Adw.PreferencesGroup(
            title="Check Printer",
            description="Tests the print service, the connection, the queue and the driver.",
        )
        diagnostics.set_header_suffix(_action_button("Run Check", self._run_diagnostics, suggested=True))
        if self._diagnosis is None:
            diagnostics.add(_row(
                "Not checked yet", "Run the check to find out why the printer isn't printing.",
            ))
        else:
            problems = [check for check in self._diagnosis if check.severity != Severity.OK]
            for check in problems:
                diagnostics.add(self._issue_row(check))
            passed = [check for check in self._diagnosis if check.severity == Severity.OK]
            if passed:
                expander = Adw.ExpanderRow(
                    title="Everything checks out" if not problems else f"{len(passed)} checks passed",
                )
                expander.add_prefix(_severity_icon(Severity.OK))
                for check in passed:
                    expander.add_row(_row(check.title))
                diagnostics.add(expander)

        # ── Queue repairs ──
        repairs = Adw.PreferencesGroup(title="Quick Fixes")
        paused = bool(status and status.state == PrinterState.STOPPED)
        rejecting = bool(status and not status.is_accepting_jobs)
        waiting = status.queued_jobs if status else 0

        def repair_row(title: str, subtitle: str, label: str, on_click: Callable[[], None], enabled: bool = True) -> None:
            row = _row(title, subtitle)
            button = _action_button(label, on_click)
            button.set_sensitive(enabled)
            row.add_suffix(button)
            repairs.add(row)

        repair_row(
            "Resume Printer",
            "The printer is paused and holding its jobs." if paused else "The printer isn't paused.",
            "Resume", lambda: self._apply_fix("resume"), enabled=paused,
        )
        if rejecting:
            repair_row(
                "Accept Jobs", "The printer is turning new jobs away.",
                "Accept", lambda: self._apply_fix("accept"),
            )
        repair_row(
            "Clear Waiting Jobs",
            "Nothing is waiting." if not waiting else (
                "Removes 1 waiting job, including a stuck one." if waiting == 1
                else f"Removes all {waiting} waiting jobs, including stuck ones."
            ),
            "Clear", self._confirm_clear_jobs, enabled=waiting > 0,
        )
        repair_row(
            "Reconnect to Printer",
            "Restarts the queue's connection. Helps after the printer was switched off or unplugged.",
            "Reconnect",
            lambda: self._run(lambda: self._backend.restart_printer(self._printer_name), "Reconnected to the printer"),
            enabled=status is not None,
        )
        repair_row(
            "Restart Print Service",
            "Restarts CUPS when nothing prints at all. Asks for your password.",
            "Restart", self._restart_print_service,
        )

        groups = [diagnostics, repairs]

        # ── Error policy ──
        if status and status.error_policies:
            policy_group = Adw.PreferencesGroup(title="When a Job Fails")
            policies = [
                (ERROR_POLICY_LABELS.get(policy, policy), policy)
                for policy in ERROR_POLICY_LABELS if policy in status.error_policies
            ]
            policy_row = OptionRow(
                "The Printer Should", policies,
                subtitle="Pausing holds every later job until you resume the printer",
            )
            policy_row.select_value(status.error_policy)
            policy_row.connect("notify::selected", self._on_error_policy_changed)
            policy_group.add(policy_row)
            groups.append(policy_group)

        self._set_groups(self._fix_page, groups)

    def _run_diagnostics(self) -> None:
        self._diagnosis = []  # anything but None: the refresh fills it in
        self._reload_later()

    def _apply_fix(self, fix: str) -> None:
        name = self._printer_name
        if fix == "resume":
            self._run(lambda: self._backend.resume_printer(name), "Printer resumed")
        elif fix == "accept":
            self._run(lambda: self._backend.set_accepting_jobs(name, True), "Printer accepts jobs again")
        elif fix == "clear-jobs":
            self._confirm_clear_jobs()
        elif fix == "default-paper":
            paper = self._paper_name
            self._run(
                lambda: self._backend.set_option_default(name, "PageSize", paper),
                f"Default paper is now {paper}",
            )
        elif fix == "restart-service":
            self._restart_print_service()

    def _confirm_clear_jobs(self) -> None:
        dialog = Adw.AlertDialog(
            heading="Clear Waiting Jobs?",
            body=f"Every job waiting for {self._printer_name} will be cancelled, including jobs from other apps.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("clear", "Clear Jobs")
        dialog.set_response_appearance("clear", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_close_response("cancel")
        dialog.connect("response", self._on_clear_jobs_response)
        dialog.present(self)

    def _on_clear_jobs_response(self, _dialog, response: str) -> None:
        if response == "clear":
            self._run(lambda: self._backend.cancel_all_jobs(self._printer_name), "Cleared {result} waiting job(s)")

    def _on_error_policy_changed(self, row: OptionRow, _pspec) -> None:
        if row.value and self._status and row.value != self._status.error_policy:
            self._run(lambda: self._backend.set_error_policy(self._printer_name, row.value), "Saved")

    def _restart_print_service(self) -> None:
        try:
            process = Gio.Subprocess.new(
                ["pkexec", "systemctl", "restart", "cups.service"], Gio.SubprocessFlags.NONE,
            )
        except GLib.Error as e:
            self._toast(f"Could not restart the print service: {e.message}")
            return
        process.wait_async(None, self._on_print_service_restarted)

    def _on_print_service_restarted(self, process: Gio.Subprocess, result: Gio.AsyncResult) -> None:
        try:
            process.wait_finish(result)
        except GLib.Error as e:
            self._toast(f"Could not restart the print service: {e.message}")
            return
        if not process.get_successful():
            self._toast("The print service was not restarted")
            return
        self._backend.reconnect()
        self._toast("Print service restarted")
        self._reload_later()

    # ── Maintenance ───────────────────────────────────────────────────

    def _build_maintenance_page(self) -> None:
        paper = get_paper_by_name(self._paper_name or maintenance.system_paper_name())
        paper_label = (paper.display_name or paper.name) if paper else "A4"

        pages = Adw.PreferencesGroup(
            title="Test &amp; Calibration Pages",
            description=f"Printed in color on {paper_label} paper from the automatic tray.",
        )
        for page in maintenance.SERVICE_PAGES:
            subtitle = page.description
            if page.sheets > 1:
                subtitle += f" Uses {page.sheets} sheets."
            row = _row(page.title, subtitle)
            row.add_suffix(_action_button("Print", lambda page=page: self._print_service_page(page)))
            pages.add(row)
        groups = [pages]

        commands = self._status.commands if self._status else []
        if commands:
            command_group = Adw.PreferencesGroup(
                title="Printer Commands",
                description="Maintenance routines this printer's driver can start.",
            )
            for name in commands:
                known = maintenance.device_command(name)
                row = _row(known.title, known.description)
                row.add_suffix(_action_button("Run", lambda name=name: self._send_command(name)))
                command_group.add(row)
            groups.append(command_group)

        guide = Adw.PreferencesGroup(
            title="Cleaning &amp; Calibrating",
            description="What to try, in order, when prints look wrong.",
        )
        steps = [
            ("Streaks, spots or repeating marks",
             "Print the Streak & Banding Check to see which color is affected, then print the Cleaning Sheets. "
             "If the mark stays in one color, that toner, drum or ink cartridge needs replacing."),
            ("Colors look wrong or shifted",
             "Start color calibration from the printer's own menu (usually Maintenance → Color Calibration "
             "or Color Registration), then print the Color Calibration Chart to check the result."),
            ("Colors don't line up, or the page is crooked",
             "Print the Alignment Page. Colored fringes on the crosses mean color registration is off: "
             "run Color Registration from the printer's menu. A tilted frame means the paper guides in the tray are loose."),
            ("Faded or uneven print",
             "Check the supply levels on the Status tab. For toner, take the cartridge out and rock it gently side to side."),
        ]
        if "Clean" not in commands:
            steps.append((
                "Why there is no Clean button",
                "This printer's driver has no cleaning command. Laser printers clean themselves; "
                "the Cleaning Sheets and the printer's own menu cover the rest.",
            ))
        for title, advice in steps:
            guide.add(_row(title, advice))
        groups.append(guide)

        self._set_groups(self._maintenance_page, groups)

    def _print_service_page(self, page: maintenance.ServicePage) -> None:
        def send() -> None:
            self._run(
                lambda: self._backend.print_service_page(self._printer_name, page.kind, self._paper_name),
                f"{page.title} sent to the printer",
            )

        if page.sheets <= 1:
            send()
            return
        dialog = Adw.AlertDialog(
            heading=f"Print {page.title}?",
            body=f"This prints {page.sheets} sheets with heavy color coverage, which uses toner or ink.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("print", "Print")
        dialog.set_response_appearance("print", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _dialog, response: response == "print" and send())
        dialog.present(self)

    def _send_command(self, name: str) -> None:
        known = maintenance.device_command(name)
        self._run(lambda: self._backend.send_command(self._printer_name, name), f"{known.title} started")

    # ── Defaults ──────────────────────────────────────────────────────

    def _build_defaults_page(self) -> None:
        ppd = self._backend.get_ppd_info(self._printer_name)
        groups: list[Adw.PreferencesGroup] = []

        options = ppd.options if ppd else []
        shown = options[:MAX_DRIVER_OPTIONS]
        by_group: dict[str, list[PpdOption]] = {}
        for option in shown:
            by_group.setdefault(option.group, []).append(option)

        for index, (group_name, group_options) in enumerate(by_group.items()):
            group = Adw.PreferencesGroup(title=GLib.markup_escape_text(group_name))
            if index == 0:
                group.set_description("What every app starts from when it prints to this printer.")
            for option in group_options:
                if len(option.choices) < 2:
                    continue
                row = OptionRow(
                    GLib.markup_escape_text(option.label),
                    [(choice.label, choice.value) for choice in option.choices],
                )
                row.select_value(option.default)
                row.connect("notify::selected", self._on_default_changed, option)
                group.add(row)
            groups.append(group)

        if not options:
            empty = Adw.PreferencesGroup()
            empty.add(_row("This printer has no driver options", "Its defaults are set on the printer itself."))
            groups.append(empty)
        elif len(options) > len(shown):
            more = Adw.PreferencesGroup()
            more.add(_row(
                f"{len(options) - len(shown)} more options",
                "Open System Printer Settings for the driver's full list.",
            ))
            groups.append(more)

        system = Adw.PreferencesGroup(title="System")
        is_default = bool(self._status and self._status.is_default)
        default_row = _row(
            "Default Printer",
            "Apps print here unless told otherwise." if is_default else "Make this the printer apps use first.",
        )
        default_button = _action_button(
            "Default" if is_default else "Set as Default",
            lambda: self._run(lambda: self._backend.set_default_printer(self._printer_name), "Set as the default printer"),
        )
        default_button.set_sensitive(not is_default)
        default_row.add_suffix(default_button)
        system.add(default_row)

        settings_row = _row(
            "System Printer Settings", "Add or remove printers and change this printer's driver.",
            activatable=True,
        )
        settings_row.add_suffix(Gtk.Image.new_from_icon_name("adw-external-link-symbolic"))
        settings_row.connect("activated", lambda _row: self._open_system_settings())
        system.add(settings_row)
        groups.append(system)

        self._set_groups(self._defaults_page, groups)

    def _on_default_changed(self, row: OptionRow, _pspec, option: PpdOption) -> None:
        value = row.value
        if value is None or value == option.default:
            return
        saved = self._run(
            lambda: self._backend.set_option_default(self._printer_name, option.keyword, value),
            f"{option.label} default saved",
        )
        if not saved:
            self._reload_later()  # put the row back on the real default

    def _open_system_settings(self) -> None:
        try:
            Gio.Subprocess.new(["gnome-control-center", "printers"], Gio.SubprocessFlags.NONE)
        except GLib.Error:
            try:
                Gio.AppInfo.launch_default_for_uri(f"http://localhost:631/printers/{self._printer_name}", None)
            except GLib.Error as e:
                self._toast(f"Could not open the system settings: {e.message}")
