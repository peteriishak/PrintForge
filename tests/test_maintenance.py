"""Tests for printer status, diagnostics and service pages."""

import os
from unittest.mock import MagicMock, patch

import pytest

from printforge.printing import maintenance
from printforge.printing.cups_backend import CupsBackend, CupsError
from printforge.printing.mock_backend import MockBackend
from printforge.printing.ppd import PpdChoice, PpdInfo, PpdOption
from printforge.printing.printer import PrinterState, PrinterStatus, Severity
from printforge.utils.paper import PAPER_SIZES


class TestDescribeReason:
    def test_known_reason(self):
        issue = maintenance.describe_reason("media-jam-error")
        assert issue.severity == Severity.ERROR
        assert issue.title == "Paper jam"
        assert issue.advice

    def test_warning_suffix_lowers_severity(self):
        assert maintenance.describe_reason("media-empty-warning").severity == Severity.WARNING

    def test_paused_offers_resume(self):
        assert maintenance.describe_reason("paused").fix == "resume"

    @pytest.mark.parametrize("reason", ["none", "", "cups-waiting-for-job-completed"])
    def test_quiet_reasons(self, reason):
        assert maintenance.describe_reason(reason) is None

    def test_unknown_reason_is_still_shown(self):
        issue = maintenance.describe_reason("vendor-flux-capacitor-error")
        assert issue.title == "Vendor flux capacitor"


class TestSupplies:
    def test_parses_levels(self):
        supplies = maintenance.parse_supplies({
            "marker-names": ["Black Toner", "Cyan Toner"],
            "marker-levels": [80, -1],
            "marker-colors": ["#000000", "none"],
        })
        assert [(s.name, s.level, s.color) for s in supplies] == [
            ("Black Toner", 80, "#000000"), ("Cyan Toner", -1, ""),
        ]

    def test_single_supply_is_not_a_list(self):
        supplies = maintenance.parse_supplies({"marker-names": "Black", "marker-levels": 40})
        assert supplies[0].level == 40

    def test_no_supplies(self):
        assert maintenance.parse_supplies({}) == []


def _ppd(default_paper: str = "Letter", generic: bool = True) -> PpdInfo:
    return PpdInfo(
        nickname="Generic PostScript Printer" if generic else "Ricoh SP C352DN PS",
        is_postscript=True,
        options=[PpdOption("PageSize", "Media Size", default_paper, [
            PpdChoice("Letter", "US Letter"), PpdChoice("A4", "A4"),
        ])],
    )


class TestDiagnose:
    def _titles(self, checks, severity):
        return [check.title for check in checks if check.severity == severity]

    def test_healthy_printer(self):
        checks = maintenance.diagnose(PrinterStatus(name="P"), _ppd("A4", generic=False), "A4")
        assert all(check.severity == Severity.OK for check in checks)

    def test_paused_printer(self):
        status = PrinterStatus(name="P", state=PrinterState.STOPPED, state_message="Filter failed")
        paused = next(c for c in maintenance.diagnose(status) if c.title == "Printer is paused")
        assert paused.fix == "resume"
        assert paused.advice == "Filter failed"

    def test_rejecting_jobs(self):
        checks = maintenance.diagnose(PrinterStatus(name="P", is_accepting_jobs=False))
        assert any(check.fix == "accept" for check in checks)

    def test_stuck_job(self):
        checks = maintenance.diagnose(PrinterStatus(name="P", queued_jobs=1))
        stuck = next(c for c in checks if c.fix == "clear-jobs")
        assert stuck.title == "1 job is waiting but nothing is printing"

    def test_jobs_while_printing_are_not_stuck(self):
        status = PrinterStatus(name="P", queued_jobs=2, state=PrinterState.PROCESSING)
        assert not any(c.fix == "clear-jobs" for c in maintenance.diagnose(status))

    def test_default_paper_differs_from_the_users(self):
        checks = maintenance.diagnose(PrinterStatus(name="P"), _ppd("Letter"), "A4")
        assert any(check.fix == "default-paper" for check in checks)

    def test_default_paper_the_driver_cannot_offer(self):
        checks = maintenance.diagnose(PrinterStatus(name="P"), _ppd("Letter"), "A3")
        assert not any(check.fix == "default-paper" for check in checks)

    def test_generic_driver_is_noted(self):
        checks = maintenance.diagnose(PrinterStatus(name="P"), _ppd("A4"), "A4")
        assert self._titles(checks, Severity.INFO) == ["A generic driver is in use"]

    def test_unreachable_network_printer(self):
        with patch.object(maintenance, "check_connection", return_value=False):
            checks = maintenance.diagnose(PrinterStatus(name="P", uri="ipp://10.0.0.5/ipp/print"))
        assert "Printer is not connected" in self._titles(checks, Severity.ERROR)


class TestCommands:
    def test_postscript_queue_cannot_clean(self):
        """CUPS advertises Clean for every queue, but a PostScript driver fails the job."""
        reported = ["AutoConfigure", "Clean", "PrintSelfTestPage"]
        assert maintenance.supported_commands(reported, _ppd()) == ["AutoConfigure", "PrintSelfTestPage"]

    def test_raster_queue_keeps_clean(self):
        ppd = PpdInfo(is_postscript=False)
        assert maintenance.supported_commands(["Clean", "PrintSelfTestPage"], ppd) == ["Clean", "PrintSelfTestPage"]

    def test_unknown_commands_are_dropped(self):
        assert maintenance.supported_commands(["Levitate"], None) == []

    def test_command_file(self):
        assert maintenance.build_command_file("Clean all") == b"#CUPS-COMMAND\nClean all\n"


class TestServicePages:
    @pytest.mark.parametrize("page", maintenance.SERVICE_PAGES, ids=lambda page: page.kind)
    @pytest.mark.parametrize("paper", ["A4", "Letter", "A5"])
    def test_page_builds_with_the_stated_sheets(self, page, paper, tmp_dir):
        from printforge.documents.pdf_doc import PdfDocument

        path = os.path.join(tmp_dir, f"{page.kind}.pdf")
        assert maintenance.build_service_page(page.kind, path, PAPER_SIZES[paper], "Test")
        doc = PdfDocument(path)
        assert doc.load()
        assert doc.page_count == page.sheets
        width, height = doc.dimensions
        assert abs(width - PAPER_SIZES[paper].width_pt) < 1 and abs(height - PAPER_SIZES[paper].height_pt) < 1

    def test_unknown_page(self, tmp_dir):
        assert not maintenance.build_service_page("confetti", os.path.join(tmp_dir, "x.pdf"))


class TestMockBackendMaintenance:
    def test_resume_paused_printer(self):
        backend = MockBackend()
        assert backend.get_printer_status("Brother_HL_L2350DW").state == PrinterState.STOPPED
        backend.resume_printer("Brother_HL_L2350DW")
        assert backend.get_printer_status("Brother_HL_L2350DW").state == PrinterState.IDLE

    def test_clear_jobs(self):
        backend = MockBackend()
        backend.print_file("HP_LaserJet_Pro_400", "/tmp/a.pdf")
        assert backend.cancel_all_jobs("HP_LaserJet_Pro_400") == 1
        assert backend.get_printer_status("HP_LaserJet_Pro_400").queued_jobs == 0

    def test_option_default_is_remembered(self):
        backend = MockBackend()
        backend.set_option_default("HP_LaserJet_Pro_400", "PageSize", "Letter")
        assert backend.get_ppd_info("HP_LaserJet_Pro_400").option("PageSize").default == "Letter"

    def test_service_page_and_command_queue_jobs(self):
        backend = MockBackend()
        backend.print_service_page("Canon_PIXMA_TS8350", "color")
        backend.send_command("Canon_PIXMA_TS8350", "Clean")
        assert len(backend.get_jobs()) == 2

    def test_diagnose_reports_paused(self):
        checks = MockBackend().diagnose("Brother_HL_L2350DW")
        assert any(check.fix == "resume" for check in checks)

    def test_unknown_printer(self):
        assert MockBackend().get_printer_status("Nope") is None


def _cups_backend() -> CupsBackend:
    backend = CupsBackend()
    if backend._cups is None:
        pytest.skip("pycups not available")
    backend._conn = MagicMock()
    backend._available = True
    return backend


class TestCupsBackendAdmin:
    def test_direct_call_is_enough_for_administrators(self):
        backend = _cups_backend()
        with patch("printforge.printing.cups_backend._call_pk_helper") as helper:
            backend.resume_printer("P")
        backend._conn.enablePrinter.assert_called_once_with("P")
        helper.assert_not_called()

    def test_denied_call_goes_through_polkit(self):
        backend = _cups_backend()
        cups = backend._cups
        backend._conn.enablePrinter.side_effect = cups.IPPError(cups.IPP_NOT_AUTHORIZED, "Unauthorized")
        with patch("printforge.printing.cups_backend._call_pk_helper", return_value="") as helper:
            backend.resume_printer("P")
        helper.assert_called_once_with("PrinterSetEnabled", "(sb)", "P", True)

    def test_polkit_refusal_is_reported(self):
        backend = _cups_backend()
        cups = backend._cups
        backend._conn.enablePrinter.side_effect = cups.IPPError(cups.IPP_FORBIDDEN, "Forbidden")
        with patch("printforge.printing.cups_backend._call_pk_helper", return_value="not allowed"):
            with pytest.raises(CupsError, match="not allowed"):
                backend.resume_printer("P")

    def test_other_errors_are_not_retried(self):
        backend = _cups_backend()
        cups = backend._cups
        backend._conn.enablePrinter.side_effect = cups.IPPError(cups.IPP_NOT_FOUND, "No such printer")
        with patch("printforge.printing.cups_backend._call_pk_helper") as helper:
            with pytest.raises(CupsError, match="No such printer"):
                backend.resume_printer("P")
        helper.assert_not_called()

    def test_cancel_all_jobs_only_touches_this_printer(self):
        backend = _cups_backend()
        backend._conn.getJobs.return_value = {
            2: {"job-printer-uri": "ipp://localhost/printers/P"},
            5: {"job-printer-uri": "ipp://localhost/printers/Other"},
        }
        assert backend.cancel_all_jobs("P") == 1
        backend._conn.cancelJob.assert_called_once_with(2, purge_job=True)

    def test_status_translates_reasons_and_filters_commands(self):
        backend = _cups_backend()
        backend._ppd_cache["P"] = PpdInfo(nickname="Generic PostScript Printer", is_postscript=True)
        backend._conn.getDefault.return_value = "P"
        backend._conn.getPrinterAttributes.return_value = {
            "printer-state": 5,
            "printer-state-message": "Unplugged or turned off",
            "printer-state-reasons": ["paused", "toner-low-warning"],
            "printer-is-accepting-jobs": True,
            "queued-job-count": 1,
            "printer-make-and-model": "Generic PostScript Printer",
            "device-uri": "usb://RICOH/SP%20C352DN?serial=X1",
            "printer-commands": ["AutoConfigure", "Clean", "PrintSelfTestPage"],
            "printer-error-policy": "stop-printer",
            "printer-error-policy-supported": ["abort-job", "retry-job", "stop-printer"],
        }

        status = backend.get_printer_status("P")

        assert status.state == PrinterState.STOPPED
        assert status.summary == "Paused"
        assert status.is_default
        assert [issue.title for issue in status.issues] == ["Printer is paused", "Toner is low"]
        assert status.commands == ["AutoConfigure", "PrintSelfTestPage"]

    def test_unknown_command_is_refused(self):
        with pytest.raises(CupsError):
            _cups_backend().send_command("P", "Levitate")
