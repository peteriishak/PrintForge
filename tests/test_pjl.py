"""Tests for sending the User ID to the printer."""

import os
import shutil
from unittest.mock import MagicMock, patch

import pytest

from printforge.printing import pjl
from printforge.printing.cups_backend import CupsBackend, CupsError
from printforge.printing.ppd import PpdInfo


class TestUserId:
    def test_configured_id_wins(self):
        assert pjl.resolve_user_id("  peter ") == "peter"

    def test_falls_back_to_device_name(self):
        assert pjl.resolve_user_id("") == pjl.get_device_name()

    @pytest.mark.parametrize("user_id, shown", [
        ("fedora", "fedora"),
        ("Peter's Laptop", "PetersLa"),
        ("accounting-dept", "accounti"),
        ("!!!", "user"),
    ])
    def test_panel_user_id(self, user_id, shown):
        assert pjl.panel_user_id(user_id) == shown


class TestPjlHeader:
    def test_header_identifies_the_job(self):
        header = pjl.build_pjl_header("fedora", "/tmp/Report.pdf", host="office-pc", when=0)
        assert header.startswith(pjl.UEL + b"@PJL JOB NAME=\"Report.pdf\"\n")
        assert b'@PJL SET USERID="fedora"\n' in header
        assert b'@PJL SET USERNAME="fedora"\n' in header
        assert b'@PJL SET HOSTNAME="office-pc"\n' in header
        assert header.endswith(b"@PJL ENTER LANGUAGE=POSTSCRIPT\n")

    def test_quotes_and_non_ascii_cannot_break_the_commands(self):
        header = pjl.build_pjl_header("fedora", 'My "final" résumé.pdf', when=0)
        assert b"@PJL JOB NAME=\"My 'final' r?sum?.pdf\"\n" in header
        header.decode("ascii")  # must be pure ASCII

    def test_footer_ends_the_job(self):
        footer = pjl.build_pjl_footer("Report.pdf")
        assert footer == pjl.UEL + b'@PJL EOJ NAME="Report.pdf"\n' + pjl.UEL

    def test_tag_job_wraps_the_postscript(self, tmp_dir):
        ps_path = os.path.join(tmp_dir, "job.ps")
        out_path = os.path.join(tmp_dir, "job.prn")
        with open(ps_path, "wb") as f:
            f.write(b"%!PS-Adobe-3.0\nshowpage\n")

        pjl.tag_job(ps_path, out_path, "fedora", "Report.pdf")

        with open(out_path, "rb") as f:
            data = f.read()
        assert data.startswith(pjl.UEL + b"@PJL JOB")
        assert b"@PJL ENTER LANGUAGE=POSTSCRIPT\n%!PS-Adobe-3.0\nshowpage\n" in data
        assert data.endswith(pjl.UEL)


class TestDeviceSpeaksPjl:
    def test_device_id_lists_pjl(self):
        assert pjl.device_speaks_pjl("socket://10.0.0.5", "MFG:HP;CMD:PJL,PCL,POSTSCRIPT;MDL:LaserJet;")

    def test_driver_only_device_id_is_not_enough(self):
        assert not pjl.device_speaks_pjl("socket://10.0.0.5", "CMD:PS;", "Generic PostScript Printer")

    def test_ricoh_family_by_name(self):
        assert pjl.device_speaks_pjl("socket://10.0.0.5", "CMD:PS;", "Ricoh SP C352DN PS")
        assert pjl.device_speaks_pjl("lpd://10.0.0.5/lp", "", "Savin MP 3054")

    def test_usb_printer_answers_for_itself(self):
        device_id = "MFG:RICOH;CMD:PJL,RCS,POSTSCRIPT,PCL,PCLXL;MDL:SP C352DN;CLS:PRINTER;"
        with patch.object(pjl, "_usb_device_id", return_value=device_id):
            assert pjl.device_speaks_pjl("usb://RICOH/SP%20C352DN?serial=X1", "CMD:PS;")
        with patch.object(pjl, "_usb_device_id", return_value="MFG:ACME;CMD:GDI;MDL:Cheap;"):
            assert not pjl.device_speaks_pjl("usb://ACME/Cheap?serial=X1", "CMD:PS;")

    def test_unplugged_ricoh_usb_still_counts(self):
        with patch.object(pjl, "_usb_device_id", return_value=""):
            assert pjl.device_speaks_pjl("usb://RICOH/SP%20C352DN?serial=X1", "CMD:PS;")


class TestFilterOptions:
    def test_plain_value(self):
        assert pjl._filter_option("media", "iso_a4_210x297mm") == "media=iso_a4_210x297mm"

    def test_value_with_spaces_is_quoted(self):
        assert pjl._filter_option("job-name", 'a "b" c') == 'job-name="a \\"b\\" c"'

    def test_missing_cupsfilter(self, tmp_dir):
        with patch.object(shutil, "which", return_value=None):
            assert not pjl.render_printer_ready("x.ppd", "x.pdf", os.path.join(tmp_dir, "o.ps"), "u", "t", {})


def _backend(ppd: PpdInfo, send_user_id: bool = True) -> CupsBackend:
    """A CupsBackend wired to a fake CUPS connection for a Ricoh PostScript queue."""
    backend = CupsBackend(user_id="fedora", send_user_id=send_user_id)
    backend._conn = MagicMock()
    backend._available = True
    backend._conn.getPrinterAttributes.return_value = {
        "device-uri": "socket://10.0.0.5",
        "printer-device-id": "CMD:PS;",
        "printer-make-and-model": "Ricoh SP C352DN PS",
    }
    backend._conn.printFile.return_value = 7
    backend._ppd_cache["Ricoh"] = ppd
    return backend


@pytest.fixture
def pdf_job(tmp_dir):
    path = os.path.join(tmp_dir, "job.pdf")
    with open(path, "wb") as f:
        f.write(b"%PDF-1.4\n")
    return path


def _fake_render(_ppd, _pdf, output_path, _user, _title, _options) -> bool:
    with open(output_path, "wb") as f:
        f.write(b"%!PS-Adobe-3.0\n")
    return True


class TestBackendUserId:
    POSTSCRIPT = PpdInfo(nickname="Generic PostScript Printer", is_postscript=True)

    def test_sends_user_id_to_postscript_pjl_printer(self):
        assert _backend(self.POSTSCRIPT).sends_user_id("Ricoh")

    def test_not_when_switched_off(self):
        assert not _backend(self.POSTSCRIPT, send_user_id=False).sends_user_id("Ricoh")

    def test_not_for_raster_drivers(self):
        assert not _backend(PpdInfo(is_postscript=False)).sends_user_id("Ricoh")

    def test_not_when_driver_adds_its_own_job_commands(self):
        assert not _backend(PpdInfo(is_postscript=True, has_jcl=True)).sends_user_id("Ricoh")

    def test_tagged_job_is_sent_printer_ready(self, pdf_job, tmp_dir):
        backend = _backend(self.POSTSCRIPT)
        ppd_copy = os.path.join(tmp_dir, "queue.ppd")
        open(ppd_copy, "w").close()
        backend._conn.getPPD.return_value = ppd_copy
        sent = {}

        def capture(printer, path, title, options):
            with open(path, "rb") as f:
                sent["data"] = f.read()
            sent["options"] = options
            return 7
        backend._conn.printFile.side_effect = capture

        with patch.object(pjl, "render_printer_ready", side_effect=_fake_render):
            job_id = backend.print_file("Ricoh", pdf_job, "Report.pdf", {"copies": "2", "media": "iso_a4_210x297mm"})

        assert job_id == 7
        # Copies were applied during conversion; repeating them would print the job twice over
        assert sent["options"] == {"document-format": "application/vnd.cups-postscript"}
        assert b'@PJL SET USERID="fedora"' in sent["data"]
        assert b"%!PS-Adobe-3.0" in sent["data"]

    def test_conversion_failure_prints_the_ordinary_way(self, pdf_job, tmp_dir):
        backend = _backend(self.POSTSCRIPT)
        ppd_copy = os.path.join(tmp_dir, "queue.ppd")
        open(ppd_copy, "w").close()
        backend._conn.getPPD.return_value = ppd_copy
        options = {"copies": "2"}

        with patch.object(pjl, "render_printer_ready", return_value=False):
            backend.print_file("Ricoh", pdf_job, "Report.pdf", options)

        backend._conn.printFile.assert_called_once_with("Ricoh", pdf_job, "Report.pdf", options)

    def test_refused_tagged_job_is_resent_untagged(self, pdf_job, tmp_dir):
        backend = _backend(self.POSTSCRIPT)
        ppd_copy = os.path.join(tmp_dir, "queue.ppd")
        open(ppd_copy, "w").close()
        backend._conn.getPPD.return_value = ppd_copy
        backend._conn.printFile.side_effect = [RuntimeError("unsupported format"), 9]

        with patch.object(pjl, "render_printer_ready", side_effect=_fake_render):
            assert backend.print_file("Ricoh", pdf_job, "Report.pdf", {"copies": "2"}) == 9

        assert backend._conn.printFile.call_args_list[-1].args == ("Ricoh", pdf_job, "Report.pdf", {"copies": "2"})

    def test_untagged_printer_gets_the_job_options(self, pdf_job):
        backend = _backend(PpdInfo(is_postscript=False))
        backend.print_file("Ricoh", pdf_job, "Report.pdf", {"copies": "2"})
        backend._conn.printFile.assert_called_once_with("Ricoh", pdf_job, "Report.pdf", {"copies": "2"})

    def test_print_failure_is_reported(self, pdf_job):
        backend = _backend(PpdInfo(is_postscript=False))
        backend._conn.printFile.side_effect = RuntimeError("printer gone")
        with pytest.raises(CupsError):
            backend.print_file("Ricoh", pdf_job, "Report.pdf", {})
