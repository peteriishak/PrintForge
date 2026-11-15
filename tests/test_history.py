"""Tests for print history manager."""

import os
import pytest
from printforge.config.history import HistoryManager


@pytest.fixture
def history_manager(tmp_dir, monkeypatch):
    monkeypatch.setattr(
        "printforge.config.history._config_dir",
        lambda: type("P", (), {"__truediv__": lambda self, x: os.path.join(tmp_dir, x)})()
    )
    import pathlib
    hm = HistoryManager.__new__(HistoryManager)
    hm._path = pathlib.Path(tmp_dir) / "history.json"
    hm._entries = []
    return hm


class TestHistoryManager:
    def test_empty_history(self, history_manager):
        assert history_manager.get_entries() == []

    def test_add_entry(self, history_manager):
        entry = history_manager.add_entry(
            filename="test.png",
            printer_name="HP LaserJet",
            page_count=1,
            copies=2,
            paper_size="A4",
            color_mode="color",
            duplex="one-sided",
            status="Completed",
        )
        assert entry.filename == "test.png"
        assert entry.copies == 2
        assert len(history_manager.get_entries()) == 1

    def test_summary_formatting(self, history_manager):
        entry = history_manager.add_entry(
            filename="document.pdf",
            printer_name="Brother",
            page_count=5,
            copies=3,
            paper_size="Letter",
            color_mode="monochrome",
            duplex="two-sided-long-edge",
        )
        summary = entry.summary
        assert "Letter" in summary
        assert "monochrome" in summary
        assert "Duplex" in summary
        assert "3 copies" in summary

    def test_remove_entry(self, history_manager):
        e1 = history_manager.add_entry(
            filename="f1.pdf", printer_name="P", page_count=1, copies=1,
            paper_size="A4", color_mode="color", duplex="one-sided",
        )
        e2 = history_manager.add_entry(
            filename="f2.pdf", printer_name="P", page_count=1, copies=1,
            paper_size="A4", color_mode="color", duplex="one-sided",
        )
        assert len(history_manager.get_entries()) == 2
        assert history_manager.remove_entry(e1.entry_id) is True
        assert len(history_manager.get_entries()) == 1
        assert history_manager.get_entries()[0].entry_id == e2.entry_id

    def test_clear_history(self, history_manager):
        history_manager.add_entry(
            filename="f1.pdf", printer_name="P", page_count=1, copies=1,
            paper_size="A4", color_mode="color", duplex="one-sided",
        )
        assert len(history_manager.get_entries()) == 1
        history_manager.clear_history()
        assert len(history_manager.get_entries()) == 0

    def test_max_entries_cap(self, history_manager):
        for i in range(110):
            history_manager.add_entry(
                filename=f"doc_{i}.pdf", printer_name="P", page_count=1, copies=1,
                paper_size="A4", color_mode="color", duplex="one-sided",
            )
        assert len(history_manager.get_entries()) == HistoryManager.MAX_ENTRIES
