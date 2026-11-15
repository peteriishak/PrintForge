"""Tests for CUPS printing backend."""

import pytest
from unittest.mock import MagicMock, patch
from printforge.printing.cups_backend import CupsBackend, CupsError
from printforge.printing.printer import PrinterState


class TestCupsBackend:
    def test_backend_initialization(self):
        backend = CupsBackend()
        # On this system CUPS is running, so available is True
        assert isinstance(backend.is_available, bool)

    def test_get_printers(self):
        backend = CupsBackend()
        if not backend.is_available:
            pytest.skip("CUPS not available")
        printers = backend.get_printers()
        assert isinstance(printers, list)
        for p in printers:
            assert p.name
            assert isinstance(p.is_default, bool)

    def test_get_capabilities(self):
        backend = CupsBackend()
        if not backend.is_available:
            pytest.skip("CUPS not available")
        printers = backend.get_printers()
        if not printers:
            pytest.skip("No printers configured in CUPS")
        caps = backend.get_capabilities(printers[0].name)
        assert caps is not None
        assert caps.printer_name == printers[0].name
        paper_sizes = caps.get_paper_sizes()
        assert len(paper_sizes) > 0

    def test_capabilities_unknown_printer(self):
        backend = CupsBackend()
        if not backend.is_available:
            pytest.skip("CUPS not available")
        caps = backend.get_capabilities("NonExistentPrinter12345")
        assert caps is None

    @patch("cups.Connection")
    def test_mocked_cups_printers(self, mock_conn_cls):
        mock_conn = MagicMock()
        mock_conn_cls.return_value = mock_conn
        mock_conn.getPrinters.return_value = {
            "Test_Printer": {
                "device-uri": "ipp://printer.local/ipp/print",
                "printer-make-and-model": "Test Printer Pro",
                "printer-state": 3,
                "printer-is-shared": False,
                "printer-location": "Office",
                "printer-info": "Office printer",
            }
        }
        mock_conn.getDefault.return_value = "Test_Printer"

        backend = CupsBackend()
        backend._conn = mock_conn
        backend._available = True

        printers = backend.get_printers()
        assert len(printers) == 1
        assert printers[0].name == "Test_Printer"
        assert printers[0].is_default is True
        assert printers[0].state == PrinterState.IDLE
