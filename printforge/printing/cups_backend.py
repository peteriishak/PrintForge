"""CUPS printing backend — wraps pycups for printer discovery, job submission, and monitoring."""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Callable, Optional

from printforge.printing import maintenance, pjl
from printforge.printing.pjl import resolve_user_id
from printforge.printing.ppd import PpdInfo, read_ppd
from printforge.printing.printer import PrinterInfo, PrinterState, PrinterStatus, Severity, StatusIssue
from printforge.printing.capabilities import PrinterCapabilities, parse_capabilities, parse_resolution_item
from printforge.utils.paper import get_paper_by_name, DEFAULT_PAPER

log = logging.getLogger(__name__)

_PK_HELPER = "org.opensuse.CupsPkHelper.Mechanism"
_PK_HELPER_TIMEOUT_MS = 5 * 60 * 1000  # leaves time to answer the password prompt


class CupsError(Exception):
    """Raised when a CUPS operation fails."""
    pass


class CupsBackend:
    """Interface to the local CUPS printing system via pycups.

    All methods handle cups import errors gracefully so the app
    can still run (with reduced functionality) if CUPS is unavailable.
    """

    def __init__(self, user_id: str = "", send_user_id: bool = True) -> None:
        self._conn = None
        self._cups = None
        self._available = False
        self._user_id = resolve_user_id(user_id)
        self._send_user_id = send_user_id
        self._ppd_cache: dict[str, Optional[PpdInfo]] = {}
        self._connect()

    def _connect(self) -> None:
        """Attempt to connect to the CUPS daemon."""
        try:
            import cups
            self._cups = cups
            # Jobs show up on the printer under the User ID, not the login user
            cups.setUser(self._user_id)
            # Never prompt on the terminal; denied admin actions go through polkit instead
            cups.setPasswordCB2(lambda *_args: None)
            self._conn = cups.Connection()
            self._available = True
            log.info("Connected to CUPS daemon")
        except ImportError:
            log.warning("pycups not installed — printing will be unavailable")
            self._available = False
        except Exception as e:
            log.warning("Cannot connect to CUPS: %s", e)
            self._available = False

    @property
    def user_id(self) -> str:
        """The User ID jobs are submitted under."""
        return self._user_id

    def set_user_id(self, user_id: str, send_to_printer: bool = True) -> None:
        """Change the User ID for the jobs that follow."""
        self._user_id = resolve_user_id(user_id)
        self._send_user_id = send_to_printer
        if self._cups:
            self._cups.setUser(self._user_id)

    @property
    def is_available(self) -> bool:
        """Whether CUPS is available and connected."""
        return self._available

    def reconnect(self) -> bool:
        """Try to reconnect to CUPS. Returns True on success."""
        self._connect()
        return self._available

    # ── Printer Discovery ─────────────────────────────────────────────

    def get_printers(self) -> list[PrinterInfo]:
        """Return all printers configured in CUPS."""
        if not self._available or not self._conn:
            return []

        try:
            raw = self._conn.getPrinters()
        except Exception as e:
            log.error("Failed to get printers: %s", e)
            return []

        default_name = self.get_default_printer()
        printers = []

        for name, attrs in raw.items():
            info = PrinterInfo(
                name=name,
                uri=attrs.get("device-uri", ""),
                make_model=attrs.get("printer-make-and-model", ""),
                state=PrinterState.from_cups(attrs.get("printer-state", 3)),
                state_message=attrs.get("printer-state-message", ""),
                is_default=(name == default_name),
                is_shared=attrs.get("printer-is-shared", False),
                location=attrs.get("printer-location", ""),
                info=attrs.get("printer-info", ""),
            )
            printers.append(info)

        # Sort: default first, then alphabetical
        printers.sort(key=lambda p: (not p.is_default, p.display_name.lower()))
        return printers

    def get_default_printer(self) -> str:
        """Return the name of the system default printer."""
        if not self._available or not self._conn:
            return ""
        try:
            return self._conn.getDefault() or ""
        except Exception:
            return ""

    def refresh(self) -> list[PrinterInfo]:
        """Re-query CUPS and return updated printer list."""
        self._ppd_cache.clear()
        if not self._available:
            self.reconnect()
        return self.get_printers()

    # ── Capabilities ──────────────────────────────────────────────────

    def _fetch_ppd(self, printer_name: str) -> Optional[str]:
        """Download the queue's PPD to a temporary file the caller removes."""
        try:
            return self._conn.getPPD(printer_name)
        except Exception as e:
            log.debug("No PPD for %s: %s", printer_name, e)
            return None

    def get_ppd_info(self, printer_name: str) -> Optional[PpdInfo]:
        """The queue's driver details, or None for a queue without a PPD."""
        if not self._available or not self._conn:
            return None
        if printer_name not in self._ppd_cache:
            info = None
            ppd_file = self._fetch_ppd(printer_name)
            if ppd_file:
                try:
                    info = read_ppd(ppd_file)
                finally:
                    _remove(ppd_file)
            self._ppd_cache[printer_name] = info
        return self._ppd_cache[printer_name]

    def get_capabilities(self, printer_name: str) -> Optional[PrinterCapabilities]:
        """Query the capabilities of a specific printer."""
        if not self._available or not self._conn:
            return None

        try:
            attrs = self._conn.getPrinterAttributes(printer_name)
        except Exception as e:
            log.error("Failed to get capabilities for %s: %s", printer_name, e)
            return None

        caps = parse_capabilities(printer_name, attrs)
        caps.ppd = self.get_ppd_info(printer_name)

        # If IPP didn't return any resolutions, use the driver's
        resolution = caps.ppd.option("Resolution") if caps.ppd else None
        if not caps.supported_resolutions and resolution:
            parsed = [parse_resolution_item(choice.value) for choice in resolution.choices]
            caps.supported_resolutions = [item[1] for item in parsed if item]
        return caps

    # ── Printing ──────────────────────────────────────────────────────

    def print_file(
        self,
        printer_name: str,
        filepath: str,
        title: str = "PrintForge Job",
        options: Optional[dict[str, str]] = None,
    ) -> int:
        """Submit a file to CUPS for printing.

        Args:
            printer_name: CUPS queue name.
            filepath: Absolute path to the file to print.
            title: Job title shown in the queue.
            options: CUPS options dict (e.g., {'copies': '2', 'media': 'iso_a4_210x297mm'}).

        Returns:
            CUPS job ID.

        Raises:
            CupsError: If printing fails.
        """
        if not self._available or not self._conn:
            raise CupsError("CUPS is not available. Is the CUPS service running?")

        opts = dict(options or {})
        tagged = self._tag_with_user_id(printer_name, filepath, title, opts) if self._send_user_id else None
        try:
            job_id = None
            if tagged:
                try:
                    # Already converted for the printer: sent as is, so no job options apply
                    job_id = self._conn.printFile(
                        printer_name, tagged, title, {"document-format": pjl.PRINTER_READY_FORMAT},
                    )
                except Exception as e:
                    log.warning("Printer-ready job refused (%s); sending without the User ID", e)
            if job_id is None:
                job_id = self._conn.printFile(printer_name, filepath, title, opts)
            log.info("Submitted job %d to %s: %s", job_id, printer_name, filepath)
            return job_id
        except Exception as e:
            raise CupsError(f"Failed to print: {_describe(e)}") from e
        finally:
            if tagged:
                _remove(tagged)

    def sends_user_id(self, printer_name: str) -> bool:
        """Whether jobs to this printer carry the User ID for its panel and job log.

        Needs a printer that reads PJL job commands and a driver that passes
        PostScript through without adding job commands of its own.
        """
        if not self._send_user_id or not self._available or not self._conn:
            return False
        ppd = self.get_ppd_info(printer_name)
        if not ppd or not ppd.is_postscript or ppd.has_jcl:
            return False
        try:
            attrs = self._conn.getPrinterAttributes(
                printer_name,
                requested_attributes=["device-uri", "printer-device-id", "printer-make-and-model"],
            )
        except Exception:
            return False
        return pjl.device_speaks_pjl(
            attrs.get("device-uri", ""),
            attrs.get("printer-device-id", ""),
            attrs.get("printer-make-and-model", ""),
        )

    def _tag_with_user_id(
        self, printer_name: str, filepath: str, title: str, options: dict[str, str],
    ) -> Optional[str]:
        """Convert the job for the printer and add the User ID to it.

        Returns the path of the printer-ready file, or None when the job
        should be submitted the ordinary way.
        """
        if not filepath.lower().endswith(".pdf") or not self.sends_user_id(printer_name):
            return None

        ppd_file = self._fetch_ppd(printer_name)
        if not ppd_file:
            return None
        ps_path = _temp_path(".ps")
        tagged_path = _temp_path(".prn")
        try:
            if not pjl.render_printer_ready(ppd_file, filepath, ps_path, self._user_id, title, options):
                _remove(tagged_path)
                return None
            pjl.tag_job(ps_path, tagged_path, self._user_id, title)
            return tagged_path
        except OSError as e:
            log.warning("Could not add the User ID to the job: %s", e)
            _remove(tagged_path)
            return None
        finally:
            _remove(ppd_file)
            _remove(ps_path)

    # ── Job Management ────────────────────────────────────────────────

    def get_jobs(self, mine_only: bool = True) -> dict:
        """Get active print jobs.

        Returns dict of {job_id: {attributes...}}.
        """
        if not self._available or not self._conn:
            return {}

        try:
            which = "not-completed" 
            return self._conn.getJobs(which_jobs=which, my_jobs=mine_only)
        except Exception as e:
            log.error("Failed to get jobs: %s", e)
            return {}

    def get_completed_jobs(self) -> dict:
        """Get completed print jobs."""
        if not self._available or not self._conn:
            return {}
        try:
            return self._conn.getJobs(which_jobs="completed", my_jobs=True)
        except Exception as e:
            log.error("Failed to get completed jobs: %s", e)
            return {}

    def cancel_job(self, job_id: int) -> bool:
        """Cancel a print job. Returns True on success."""
        if not self._available or not self._conn:
            return False
        try:
            self._conn.cancelJob(job_id)
            log.info("Cancelled job %d", job_id)
            return True
        except Exception as e:
            log.error("Failed to cancel job %d: %s", job_id, e)
            return False

    def get_job_attributes(self, job_id: int) -> dict:
        """Get attributes of a specific job."""
        if not self._available or not self._conn:
            return {}
        try:
            return self._conn.getJobAttributes(job_id)
        except Exception:
            return {}

    # ── Status ────────────────────────────────────────────────────────

    def get_printer_status(self, printer_name: str) -> Optional[PrinterStatus]:
        """Live condition of the queue: state, reported problems, supplies."""
        if not self._available or not self._conn:
            return None
        try:
            attrs = self._conn.getPrinterAttributes(printer_name)
        except Exception as e:
            log.error("Failed to get status for %s: %s", printer_name, e)
            return None

        reasons = attrs.get("printer-state-reasons", [])
        if isinstance(reasons, str):
            reasons = [reasons]
        issues = [issue for issue in (maintenance.describe_reason(r) for r in reasons) if issue]

        policies = attrs.get("printer-error-policy-supported", [])
        commands = attrs.get("printer-commands", [])
        return PrinterStatus(
            name=printer_name,
            state=PrinterState.from_cups(attrs.get("printer-state", 3)),
            state_message=attrs.get("printer-state-message", "") or "",
            is_accepting_jobs=bool(attrs.get("printer-is-accepting-jobs", True)),
            is_default=printer_name == self.get_default_printer(),
            queued_jobs=int(attrs.get("queued-job-count", 0) or 0),
            make_model=attrs.get("printer-make-and-model", "") or "",
            uri=attrs.get("device-uri", "") or "",
            location=attrs.get("printer-location", "") or "",
            issues=issues,
            supplies=maintenance.parse_supplies(attrs),
            commands=maintenance.supported_commands(
                [commands] if isinstance(commands, str) else list(commands),
                self.get_ppd_info(printer_name),
            ),
            error_policy=attrs.get("printer-error-policy", "") or "",
            error_policies=[policies] if isinstance(policies, str) else list(policies),
        )

    def diagnose(self, printer_name: str, paper_name: str = "") -> list[StatusIssue]:
        """Check the queue end to end. Returns every check, passed or failed."""
        status = self.get_printer_status(printer_name)
        if not status:
            return [StatusIssue(
                Severity.ERROR, "Print service is not responding",
                "Restart the print service, then check again.", "restart-service",
            )]
        return maintenance.diagnose(status, self.get_ppd_info(printer_name), paper_name)

    # ── Administration ────────────────────────────────────────────────

    def _is_denied(self, error: Exception) -> bool:
        """Whether CUPS refused the request for lack of administrator rights."""
        cups = self._cups
        code = error.args[0] if error.args else None
        if isinstance(error, cups.IPPError):
            return code in (
                cups.IPP_NOT_AUTHORIZED, cups.IPP_FORBIDDEN,
                cups.IPP_STATUS_ERROR_CUPS_AUTHENTICATION_CANCELED,
            )
        if isinstance(error, cups.HTTPError):
            return code in (401, 403)
        return False

    def _admin(self, what: str, direct: Callable[[], None], helper_method: str, signature: str, *args) -> None:
        """Run an administrative change.

        Tries CUPS directly, which works for administrators; otherwise asks
        through cups-pk-helper, which shows the system's password prompt.
        """
        if not self._available or not self._conn:
            raise CupsError("CUPS is not available. Is the CUPS service running?")
        try:
            direct()
            return
        except CupsError as e:
            raise CupsError(f"Could not {what}: {e}") from e
        except Exception as e:
            if not self._is_denied(e):
                raise CupsError(f"Could not {what}: {_describe(e)}") from e

        error = _call_pk_helper(helper_method, signature, *args)
        if error:
            raise CupsError(f"Could not {what}: {error}")

    def resume_printer(self, printer_name: str) -> None:
        """Un-pause the queue so waiting jobs print."""
        self._admin(
            "resume the printer", lambda: self._conn.enablePrinter(printer_name),
            "PrinterSetEnabled", "(sb)", printer_name, True,
        )

    def pause_printer(self, printer_name: str) -> None:
        self._admin(
            "pause the printer", lambda: self._conn.disablePrinter(printer_name),
            "PrinterSetEnabled", "(sb)", printer_name, False,
        )

    def set_accepting_jobs(self, printer_name: str, accepting: bool) -> None:
        def direct() -> None:
            if accepting:
                self._conn.acceptJobs(printer_name)
            else:
                self._conn.rejectJobs(printer_name)
        self._admin(
            "change whether the printer accepts jobs", direct,
            "PrinterSetAcceptJobs", "(sbs)", printer_name, accepting, "",
        )

    def restart_printer(self, printer_name: str) -> None:
        """Pause and resume the queue, which reopens the connection to the device."""
        self.pause_printer(printer_name)
        self.resume_printer(printer_name)

    def cancel_all_jobs(self, printer_name: str) -> int:
        """Remove every waiting or stuck job from the queue. Returns how many."""
        if not self._available or not self._conn:
            raise CupsError("CUPS is not available. Is the CUPS service running?")
        try:
            jobs = self._conn.getJobs(
                which_jobs="not-completed", my_jobs=False,
                requested_attributes=["job-id", "job-printer-uri"],
            )
        except Exception as e:
            raise CupsError(f"Could not list the waiting jobs: {_describe(e)}") from e

        job_ids = [
            job_id for job_id, attrs in jobs.items()
            if str(attrs.get("job-printer-uri", "")).rsplit("/", 1)[-1] == printer_name
        ]
        for job_id in job_ids:
            # Other users' jobs need administrator rights
            self._admin(
                f"cancel job {job_id}", lambda job_id=job_id: self._conn.cancelJob(job_id, purge_job=True),
                "JobCancelPurge", "(ib)", job_id, True,
            )
        return len(job_ids)

    def set_error_policy(self, printer_name: str, policy: str) -> None:
        """Choose what the queue does when a job fails ('retry-job', 'abort-job', 'stop-printer')."""
        self._admin(
            "change the error policy", lambda: self._conn.setPrinterErrorPolicy(printer_name, policy),
            "PrinterSetErrorPolicy", "(ss)", printer_name, policy,
        )

    def set_option_default(self, printer_name: str, option: str, value: str) -> None:
        """Make `value` the queue's default for a driver option, for every app.

        The default lives in the queue's PPD, so the PPD is re-saved with
        only its Default lines changed.
        """
        def direct() -> None:
            ppd_file = self._fetch_ppd(printer_name)
            if not ppd_file:
                raise CupsError("this printer has no driver options")
            updated = _temp_path(".ppd")
            try:
                ppd = self._cups.PPD(ppd_file)
                ppd.markOption(option, value)
                with open(updated, "wb") as f:
                    ppd.writeFd(f.fileno())
                self._conn.addPrinter(printer_name, filename=updated)
            finally:
                _remove(ppd_file)
                _remove(updated)

        self._admin(
            f"change the default {option}", direct,
            "PrinterAddOption", "(ssas)", printer_name, option, [value],
        )
        self._ppd_cache.pop(printer_name, None)

    def set_default_printer(self, printer_name: str) -> None:
        self._admin(
            "set the default printer", lambda: self._conn.setDefault(printer_name),
            "PrinterSetDefault", "(s)", printer_name,
        )

    # ── Maintenance ───────────────────────────────────────────────────

    def send_command(self, printer_name: str, command: str) -> int:
        """Send one of the driver's maintenance commands (see maintenance.device_command)."""
        if not self._available or not self._conn:
            raise CupsError("CUPS is not available. Is the CUPS service running?")
        known = maintenance.device_command(command)
        if not known:
            raise CupsError(f"Unknown printer command: {command}")
        path = _temp_path(".command")
        try:
            with open(path, "wb") as f:
                f.write(maintenance.build_command_file(known.command))
            return self._conn.printFile(
                printer_name, path, known.title, {"document-format": maintenance.COMMAND_FORMAT},
            )
        except Exception as e:
            raise CupsError(f"Could not send the command: {_describe(e)}") from e
        finally:
            _remove(path)

    def print_service_page(self, printer_name: str, kind: str, paper_name: str = "") -> int:
        """Print a test, calibration, alignment, streak-check or cleaning page."""
        page = maintenance.get_service_page(kind)
        if not page:
            raise CupsError(f"Unknown service page: {kind}")
        paper = get_paper_by_name(paper_name or maintenance.system_paper_name()) or DEFAULT_PAPER
        path = _temp_path(".pdf")
        try:
            maintenance.build_service_page(kind, path, paper, printer_name)
            caps = self.get_capabilities(printer_name)
            options = {"media": paper.cups_name, "sides": "one-sided", "print-color-mode": "color"}
            if caps:
                options.update(caps.tray_job_options(""))
            return self.print_file(printer_name, path, f"PrintForge {page.title}", options)
        finally:
            _remove(path)


def _temp_path(suffix: str) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False, prefix="printforge_")
    tmp.close()
    return tmp.name


def _remove(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _describe(error: Exception) -> str:
    """The readable part of a pycups error, which is (code, message)."""
    if len(error.args) >= 2 and error.args[1]:
        return str(error.args[1])
    return str(error)


def _call_pk_helper(method: str, signature: str, *args) -> str:
    """Call cups-pk-helper, the polkit-guarded CUPS administration service.

    Returns '' on success, otherwise the reason it failed.
    """
    try:
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        reply = bus.call_sync(
            _PK_HELPER, "/", _PK_HELPER, method,
            GLib.Variant(signature, args), GLib.VariantType("(s)"),
            Gio.DBusCallFlags.ALLOW_INTERACTIVE_AUTHORIZATION, _PK_HELPER_TIMEOUT_MS, None,
        )
        return reply.unpack()[0]
    except Exception as e:
        log.warning("cups-pk-helper %s failed: %s", method, e)
        return "administrator rights are needed. Use System Settings → Printers instead."
