"""Printer information data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PrinterState(Enum):
    """Printer state as reported by CUPS."""
    IDLE = 3
    PROCESSING = 4
    STOPPED = 5

    @classmethod
    def from_cups(cls, value: int) -> PrinterState:
        try:
            return cls(value)
        except ValueError:
            return cls.IDLE

    @property
    def display_name(self) -> str:
        return {
            PrinterState.IDLE: "Ready",
            PrinterState.PROCESSING: "Printing",
            PrinterState.STOPPED: "Stopped",
        }.get(self, "Unknown")

    @property
    def icon_name(self) -> str:
        return {
            PrinterState.IDLE: "emblem-ok-symbolic",
            PrinterState.PROCESSING: "media-playback-start-symbolic",
            PrinterState.STOPPED: "media-playback-pause-symbolic",
        }.get(self, "dialog-question-symbolic")


@dataclass
class PrinterInfo:
    """Information about a discovered printer."""

    name: str
    uri: str = ""
    make_model: str = ""
    state: PrinterState = PrinterState.IDLE
    state_message: str = ""
    is_default: bool = False
    is_color: bool = True
    is_shared: bool = False
    is_accepting_jobs: bool = True
    location: str = ""
    info: str = ""

    @property
    def display_name(self) -> str:
        """Human-friendly display name."""
        return self.info if self.info else self.name

    @property
    def status_text(self) -> str:
        """Human-readable status string."""
        if self.state_message:
            return self.state_message
        return self.state.display_name

    @property
    def connection_type(self) -> str:
        """Infer connection type from URI."""
        uri = self.uri.lower()
        if uri.startswith("ipp://") or uri.startswith("ipps://"):
            return "Network (IPP)"
        elif uri.startswith("http://") or uri.startswith("https://"):
            return "Network (HTTP)"
        elif uri.startswith("usb://"):
            return "USB"
        elif uri.startswith("socket://"):
            return "Network (Socket)"
        elif uri.startswith("lpd://"):
            return "Network (LPD)"
        elif uri.startswith("smb://"):
            return "Network (SMB)"
        elif uri.startswith("dnssd://"):
            return "Network (DNS-SD)"
        elif "pdf" in uri.lower():
            return "Virtual (PDF)"
        else:
            return "Local"


class Severity(Enum):
    """How much a printer condition gets in the way of printing."""
    OK = "ok"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

    @property
    def icon_name(self) -> str:
        return {
            Severity.OK: "object-select-symbolic",
            Severity.INFO: "dialog-information-symbolic",
            Severity.WARNING: "dialog-warning-symbolic",
            Severity.ERROR: "dialog-error-symbolic",
        }[self]


@dataclass
class StatusIssue:
    """Something the printer reports, or a check PrintForge ran, with what to do about it."""
    severity: Severity
    title: str
    advice: str = ""
    # Name of the PrinterSettings fix that resolves it ("resume", "accept", "clear-jobs"), if any
    fix: str = ""


@dataclass
class SupplyLevel:
    """Remaining toner, ink or other consumable."""
    name: str
    level: int  # percent, or -1 when the printer doesn't say
    color: str = ""  # '#RRGGBB', when known


@dataclass
class PrinterStatus:
    """Live condition of a print queue, for the Printer Settings dialog."""

    name: str
    state: PrinterState = PrinterState.IDLE
    state_message: str = ""
    is_accepting_jobs: bool = True
    is_default: bool = False
    queued_jobs: int = 0
    make_model: str = ""
    uri: str = ""
    location: str = ""
    issues: list[StatusIssue] = field(default_factory=list)
    supplies: list[SupplyLevel] = field(default_factory=list)
    # Maintenance commands the driver accepts ('Clean', 'PrintSelfTestPage', …)
    commands: list[str] = field(default_factory=list)
    error_policy: str = ""
    error_policies: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        """One line describing whether the printer can print right now."""
        if self.state == PrinterState.STOPPED:
            return "Paused"
        if not self.is_accepting_jobs:
            return "Not accepting jobs"
        problems = [issue for issue in self.issues if issue.severity == Severity.ERROR]
        if problems:
            return problems[0].title
        return self.state.display_name
