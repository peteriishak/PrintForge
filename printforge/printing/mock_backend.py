"""Mock printing backend for development and testing without a real printer."""

from __future__ import annotations

import logging
import time
from typing import Optional

from printforge.printing import maintenance
from printforge.printing.pjl import resolve_user_id
from printforge.printing.ppd import PpdChoice, PpdInfo, PpdOption
from printforge.printing.printer import (
    PrinterInfo, PrinterState, PrinterStatus, Severity, StatusIssue, SupplyLevel,
)
from printforge.printing.capabilities import PrinterCapabilities

log = logging.getLogger(__name__)


class MockBackend:
    """Simulates a CUPS backend with fake printers for testing.

    Implements the same interface as CupsBackend so they're interchangeable.
    """

    def __init__(self, user_id: str = "", send_user_id: bool = True) -> None:
        self._available = True
        self._job_counter = 1000
        self._jobs: dict[int, dict] = {}
        self._user_id = resolve_user_id(user_id)
        self._send_user_id = send_user_id
        # Queue state the Printer Settings dialog can change
        self._paused: set[str] = {"Brother_HL_L2350DW"}
        self._rejecting: set[str] = set()
        self._error_policies: dict[str, str] = {}
        self._option_defaults: dict[tuple[str, str], str] = {}
        self._default_printer = "HP_LaserJet_Pro_400"

    @property
    def user_id(self) -> str:
        return self._user_id

    def set_user_id(self, user_id: str, send_to_printer: bool = True) -> None:
        self._user_id = resolve_user_id(user_id)
        self._send_user_id = send_to_printer

    def sends_user_id(self, printer_name: str) -> bool:
        return self._send_user_id and printer_name != "Print_to_PDF"

    @property
    def is_available(self) -> bool:
        return self._available

    def reconnect(self) -> bool:
        self._available = True
        return True

    # ── Printer Discovery ─────────────────────────────────────────────

    def get_printers(self) -> list[PrinterInfo]:
        return [
            PrinterInfo(
                name="HP_LaserJet_Pro_400",
                uri="ipp://192.168.1.50:631/ipp/print",
                make_model="HP LaserJet Pro 400 M401dn",
                state=PrinterState.IDLE,
                is_default=self._default_printer == "HP_LaserJet_Pro_400",
                is_color=False,
                location="Office",
                info="HP LaserJet Pro 400",
            ),
            PrinterInfo(
                name="Canon_PIXMA_TS8350",
                uri="usb://Canon/PIXMA%20TS8350",
                make_model="Canon PIXMA TS8350",
                state=PrinterState.IDLE,
                is_default=False,
                is_color=True,
                location="Home Office",
                info="Canon PIXMA TS8350",
            ),
            PrinterInfo(
                name="Brother_HL_L2350DW",
                uri="ipp://192.168.1.51:631/ipp/print",
                make_model="Brother HL-L2350DW",
                state=PrinterState.PROCESSING,
                state_message="Printing page 2 of 5",
                is_default=False,
                is_color=False,
                location="Study",
                info="Brother HL-L2350DW",
            ),
            PrinterInfo(
                name="Print_to_PDF",
                uri="cups-pdf:/",
                make_model="Virtual PDF Printer",
                state=PrinterState.IDLE,
                is_default=False,
                is_color=True,
                location="",
                info="Print to PDF",
            ),
        ]

    def get_default_printer(self) -> str:
        return self._default_printer

    def refresh(self) -> list[PrinterInfo]:
        return self.get_printers()

    # ── Capabilities ──────────────────────────────────────────────────

    def get_capabilities(self, printer_name: str) -> Optional[PrinterCapabilities]:
        caps_map = {
            "HP_LaserJet_Pro_400": PrinterCapabilities(
                printer_name=printer_name,
                supported_media=[
                    "iso_a4_210x297mm", "iso_a3_297x420mm", "iso_a5_148x210mm",
                    "na_letter_8.5x11in", "na_legal_8.5x14in",
                    "iso_dl_110x220mm", "na_number-10_4.125x9.5in",
                ],
                default_media="iso_a4_210x297mm",
                supports_color=False,
                supported_color_modes=["monochrome"],
                supports_duplex=True,
                supported_sides=["one-sided", "two-sided-long-edge", "two-sided-short-edge"],
                supported_qualities=["3", "4", "5"],
                supported_resolutions=["300x300dpi", "600x600dpi", "1200x1200dpi"],
                supported_media_types=["stationery", "stationery-heavyweight", "envelope", "labels"],
                max_copies=999,
            ),
            "Canon_PIXMA_TS8350": PrinterCapabilities(
                printer_name=printer_name,
                supported_media=[
                    "iso_a4_210x297mm", "iso_a5_148x210mm",
                    "na_letter_8.5x11in",
                    "na_index-4x6_4x6in", "na_5x7_5x7in", "na_govt-letter_8x10in",
                ],
                default_media="iso_a4_210x297mm",
                supports_color=True,
                supported_color_modes=["color", "monochrome"],
                supports_duplex=False,
                supported_sides=["one-sided"],
                supported_qualities=["3", "4", "5"],
                supported_resolutions=["300x300dpi", "600x600dpi", "1200x1200dpi"],
                supported_media_types=[
                    "stationery", "photographic", "photographic-glossy",
                    "photographic-matte", "cardstock",
                ],
                max_copies=99,
            ),
            "Brother_HL_L2350DW": PrinterCapabilities(
                printer_name=printer_name,
                supported_media=[
                    "iso_a4_210x297mm", "iso_a5_148x210mm",
                    "na_letter_8.5x11in", "na_legal_8.5x14in",
                    "na_executive_7.25x10.5in",
                ],
                default_media="iso_a4_210x297mm",
                supports_color=False,
                supported_color_modes=["monochrome"],
                supports_duplex=True,
                supported_sides=["one-sided", "two-sided-long-edge", "two-sided-short-edge"],
                supported_qualities=["3", "4", "5"],
                supported_resolutions=["300x300dpi", "600x600dpi"],
                supported_media_types=["stationery", "stationery-heavyweight"],
                max_copies=999,
            ),
            "Print_to_PDF": PrinterCapabilities(
                printer_name=printer_name,
                supported_media=[
                    "iso_a4_210x297mm", "iso_a3_297x420mm", "iso_a5_148x210mm",
                    "na_letter_8.5x11in", "na_legal_8.5x14in",
                    "na_ledger_11x17in",
                ],
                default_media="iso_a4_210x297mm",
                supports_color=True,
                supported_color_modes=["color", "monochrome"],
                supports_duplex=False,
                supported_sides=["one-sided"],
                supported_qualities=["4", "5"],
                supported_resolutions=["300x300dpi", "600x600dpi", "1200x1200dpi"],
                supported_media_types=["stationery"],
                max_copies=1,
            ),
        }
        caps = caps_map.get(printer_name)
        if caps:
            caps.ppd = self.get_ppd_info(printer_name)
        return caps

    def get_ppd_info(self, printer_name: str) -> Optional[PpdInfo]:
        if printer_name == "Print_to_PDF":
            return None
        trays = [PpdChoice("Auto", "Auto Select"), PpdChoice("Tray1", "Tray 1"), PpdChoice("Manual", "Manual Feed")]
        if printer_name == "HP_LaserJet_Pro_400":
            trays.insert(2, PpdChoice("Tray2", "Tray 2"))
        sizes = [PpdChoice("A4", "A4"), PpdChoice("Letter", "US Letter"), PpdChoice("A5", "A5")]
        options = [
            PpdOption("PageSize", "Media Size", "A4", sizes, "General"),
            PpdOption("InputSlot", "Media Source", "Auto", trays, "General"),
            PpdOption("Duplex", "2-Sided Printing", "None", [
                PpdChoice("None", "Off"), PpdChoice("DuplexNoTumble", "Long Edge"),
                PpdChoice("DuplexTumble", "Short Edge"),
            ], "General"),
        ]
        for option in options:
            option.default = self._option_defaults.get((printer_name, option.keyword), option.default)
        return PpdInfo(nickname=printer_name.replace("_", " "), options=options, is_postscript=True)

    # ── Printing ──────────────────────────────────────────────────────

    def print_file(
        self,
        printer_name: str,
        filepath: str,
        title: str = "PrintForge Job",
        options: Optional[dict[str, str]] = None,
    ) -> int:
        self._job_counter += 1
        job_id = self._job_counter
        self._jobs[job_id] = {
            "job-id": job_id,
            "job-name": title,
            "job-state": 5,  # processing
            "job-printer-uri": f"ipp://localhost/printers/{printer_name}",
            "document-name-supplied": filepath,
            "time-at-creation": int(time.time()),
        }
        log.info("[MOCK] Submitted job %d to %s: %s", job_id, printer_name, filepath)
        return job_id

    # ── Job Management ────────────────────────────────────────────────

    def get_jobs(self, mine_only: bool = True) -> dict:
        return dict(self._jobs)

    def get_completed_jobs(self) -> dict:
        return {}

    def cancel_job(self, job_id: int) -> bool:
        if job_id in self._jobs:
            del self._jobs[job_id]
            return True
        return False

    def get_job_attributes(self, job_id: int) -> dict:
        return self._jobs.get(job_id, {})

    # ── Status ────────────────────────────────────────────────────────

    def get_printer_status(self, printer_name: str) -> Optional[PrinterStatus]:
        printer = next((p for p in self.get_printers() if p.name == printer_name), None)
        if not printer:
            return None
        paused = printer_name in self._paused
        is_inkjet = printer_name == "Canon_PIXMA_TS8350"
        issues = []
        if paused:
            issues.append(maintenance.describe_reason("paused"))
        if printer_name == "HP_LaserJet_Pro_400":
            issues.append(maintenance.describe_reason("toner-low-warning"))
        supplies = {
            "HP_LaserJet_Pro_400": [SupplyLevel("Black Toner", 12, "#000000")],
            "Canon_PIXMA_TS8350": [
                SupplyLevel("Cyan", 64, "#00FFFF"), SupplyLevel("Magenta", 48, "#FF00FF"),
                SupplyLevel("Yellow", 71, "#FFFF00"), SupplyLevel("Black", 35, "#000000"),
            ],
        }.get(printer_name, [])
        return PrinterStatus(
            name=printer_name,
            state=PrinterState.STOPPED if paused else PrinterState.IDLE,
            is_accepting_jobs=printer_name not in self._rejecting,
            is_default=printer_name == self._default_printer,
            queued_jobs=len(self._jobs),
            make_model=printer.make_model,
            uri=printer.uri,
            location=printer.location,
            issues=issues,
            supplies=supplies,
            commands=["Clean", "PrintAlignmentPage", "PrintSelfTestPage"] if is_inkjet else ["PrintSelfTestPage"],
            error_policy=self._error_policies.get(printer_name, "stop-printer"),
            error_policies=["abort-job", "retry-job", "stop-printer"],
        )

    def diagnose(self, printer_name: str, paper_name: str = "") -> list[StatusIssue]:
        status = self.get_printer_status(printer_name)
        if not status:
            return [StatusIssue(Severity.ERROR, "Printer not found")]
        status.uri = ""  # nothing real to reach
        return maintenance.diagnose(status, self.get_ppd_info(printer_name), paper_name)

    # ── Administration ────────────────────────────────────────────────

    def resume_printer(self, printer_name: str) -> None:
        self._paused.discard(printer_name)

    def pause_printer(self, printer_name: str) -> None:
        self._paused.add(printer_name)

    def set_accepting_jobs(self, printer_name: str, accepting: bool) -> None:
        if accepting:
            self._rejecting.discard(printer_name)
        else:
            self._rejecting.add(printer_name)

    def restart_printer(self, printer_name: str) -> None:
        self.resume_printer(printer_name)

    def cancel_all_jobs(self, printer_name: str) -> int:
        count = len(self._jobs)
        self._jobs.clear()
        return count

    def set_error_policy(self, printer_name: str, policy: str) -> None:
        self._error_policies[printer_name] = policy

    def set_option_default(self, printer_name: str, option: str, value: str) -> None:
        self._option_defaults[(printer_name, option)] = value

    def set_default_printer(self, printer_name: str) -> None:
        self._default_printer = printer_name

    # ── Maintenance ───────────────────────────────────────────────────

    def send_command(self, printer_name: str, command: str) -> int:
        known = maintenance.device_command(command)
        return self.print_file(printer_name, command, known.title if known else command)

    def print_service_page(self, printer_name: str, kind: str, paper_name: str = "") -> int:
        page = maintenance.get_service_page(kind)
        return self.print_file(printer_name, kind, f"PrintForge {page.title}" if page else kind)
