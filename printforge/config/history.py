"""Print history manager — records completed/cancelled print jobs.

Stores lightweight metadata in ~/.config/printforge/history.json without copying
the original document files. Capped at 100 entries.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from printforge.config.settings import _config_dir


@dataclass
class HistoryEntry:
    """A record of a print job execution."""
    entry_id: str
    timestamp: float  # Epoch seconds
    filename: str
    filepath: str
    printer_name: str
    page_count: int
    copies: int
    paper_size: str
    color_mode: str
    duplex: str
    status: str  # "Completed", "Cancelled", "Failed"
    settings: dict = field(default_factory=dict)

    @property
    def time_str(self) -> str:
        """Formatted time e.g. '14:35'."""
        dt = datetime.fromtimestamp(self.timestamp)
        return dt.strftime("%H:%M")

    @property
    def date_str(self) -> str:
        """Formatted date e.g. '2025-05-12'."""
        dt = datetime.fromtimestamp(self.timestamp)
        return dt.strftime("%Y-%m-%d")

    @property
    def relative_date(self) -> str:
        """Group label: 'Today', 'Yesterday', or full date."""
        dt = datetime.fromtimestamp(self.timestamp).date()
        today = datetime.now().date()
        days_diff = (today - dt).days

        if days_diff == 0:
            return "Today"
        elif days_diff == 1:
            return "Yesterday"
        elif days_diff < 7:
            return dt.strftime("%A")  # Day of week
        else:
            return dt.strftime("%b %d, %Y")

    @property
    def summary(self) -> str:
        """Summary string e.g. 'A4 · Color · 2 copies'."""
        parts = [self.paper_size, self.color_mode]
        if self.duplex and self.duplex != "one-sided":
            parts.append("Duplex")
        if self.copies > 1:
            parts.append(f"{self.copies} copies")
        else:
            parts.append("1 copy")
        return " · ".join(parts)


class HistoryManager:
    """Manages persistent print history."""

    MAX_ENTRIES = 100

    def __init__(self) -> None:
        self._path = _config_dir() / "history.json"
        self._entries: list[dict] = []
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._entries = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._entries = []

    def _save(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._entries, f, indent=2, ensure_ascii=False)
            tmp.replace(self._path)
        except OSError:
            pass

    def add_entry(
        self,
        filename: str,
        printer_name: str,
        page_count: int,
        copies: int,
        paper_size: str,
        color_mode: str,
        duplex: str,
        status: str = "Completed",
        filepath: str = "",
        settings: Optional[dict] = None,
    ) -> HistoryEntry:
        """Record a new print job in history."""
        entry = HistoryEntry(
            entry_id=str(uuid.uuid4()),
            timestamp=time.time(),
            filename=filename,
            filepath=filepath,
            printer_name=printer_name,
            page_count=page_count,
            copies=copies,
            paper_size=paper_size,
            color_mode=color_mode,
            duplex=duplex,
            status=status,
            settings=settings or {},
        )

        self._entries.insert(0, asdict(entry))
        # Cap at MAX_ENTRIES
        if len(self._entries) > self.MAX_ENTRIES:
            self._entries = self._entries[:self.MAX_ENTRIES]

        self._save()
        return entry

    def get_entries(self) -> list[HistoryEntry]:
        """Return all history entries sorted by most recent first."""
        results = []
        for d in self._entries:
            try:
                results.append(HistoryEntry(**d))
            except TypeError:
                pass
        return results

    def remove_entry(self, entry_id: str) -> bool:
        """Remove an entry by ID."""
        initial_len = len(self._entries)
        self._entries = [e for e in self._entries if e.get("entry_id") != entry_id]
        if len(self._entries) < initial_len:
            self._save()
            return True
        return False

    def clear_history(self) -> None:
        """Remove all history entries."""
        self._entries.clear()
        self._save()
