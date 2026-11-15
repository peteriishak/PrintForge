"""Tests for mock printing backend."""

import pytest
from printforge.printing.mock_backend import MockBackend
from printforge.printing.job import PrintJobManager, JobState


class TestMockBackend:
    def test_get_printers(self):
        backend = MockBackend()
        printers = backend.get_printers()
        assert len(printers) == 4
        assert any(p.is_default for p in printers)

    def test_default_printer(self):
        backend = MockBackend()
        assert backend.get_default_printer() == "HP_LaserJet_Pro_400"

    def test_capabilities(self):
        backend = MockBackend()
        caps = backend.get_capabilities("HP_LaserJet_Pro_400")
        assert caps is not None
        assert caps.supports_color is False
        assert caps.supports_duplex is True

    def test_capabilities_color_printer(self):
        backend = MockBackend()
        caps = backend.get_capabilities("Canon_PIXMA_TS8350")
        assert caps is not None
        assert caps.supports_color is True
        assert caps.supports_duplex is False

    def test_capabilities_unknown(self):
        backend = MockBackend()
        caps = backend.get_capabilities("NonExistent")
        assert caps is None

    def test_print_file(self):
        backend = MockBackend()
        job_id = backend.print_file("HP_LaserJet_Pro_400", "/tmp/test.pdf")
        assert job_id > 0

    def test_cancel_job(self):
        backend = MockBackend()
        job_id = backend.print_file("HP_LaserJet_Pro_400", "/tmp/test.pdf")
        assert backend.cancel_job(job_id) is True
        assert backend.cancel_job(99999) is False

    def test_is_available(self):
        backend = MockBackend()
        assert backend.is_available is True


class TestPrintJobManager:
    def test_submit_job(self):
        backend = MockBackend()
        manager = PrintJobManager(backend)
        info = manager.submit_job(
            "HP_LaserJet_Pro_400", "/tmp/test.pdf",
            "Test Job", {}, page_count=3,
        )
        assert info.job_id > 0
        assert info.state == JobState.PROCESSING
        assert info.pages == 3

    def test_tracked_jobs(self):
        backend = MockBackend()
        manager = PrintJobManager(backend)
        manager.submit_job("HP_LaserJet_Pro_400", "/tmp/a.pdf", "Job A", {})
        manager.submit_job("HP_LaserJet_Pro_400", "/tmp/b.pdf", "Job B", {})
        jobs = manager.get_tracked_jobs()
        assert len(jobs) == 2

    def test_cancel_job(self):
        backend = MockBackend()
        manager = PrintJobManager(backend)
        info = manager.submit_job("HP_LaserJet_Pro_400", "/tmp/test.pdf", "Test", {})
        assert manager.cancel_job(info.job_id) is True
        jobs = manager.get_tracked_jobs()
        assert jobs[0].state == JobState.CANCELED

    def test_remove_completed(self):
        backend = MockBackend()
        manager = PrintJobManager(backend)
        info = manager.submit_job("HP_LaserJet_Pro_400", "/tmp/test.pdf", "Test", {})
        manager.cancel_job(info.job_id)  # Makes it "finished"
        manager.remove_completed()
        assert len(manager.get_tracked_jobs()) == 0
