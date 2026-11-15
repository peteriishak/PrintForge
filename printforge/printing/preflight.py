"""Print preflight — pre-print validation of document, settings, and printer state.

Ensures that invalid, impossible, or poor-quality jobs are identified before
sending them to CUPS. Provides actionable warnings and errors to the user.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from printforge.config.print_settings import PrintSettings, ColorMode, DuplexMode, PageRangeMode
from printforge.documents.base import Document
from printforge.printing.capabilities import PrinterCapabilities
from printforge.printing.printer import PrinterInfo, PrinterState
from printforge.utils.formatting import parse_page_range
from printforge.utils.units import mm_to_in


class Severity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class PreflightIssue:
    """A single issue discovered during preflight check."""
    severity: Severity
    message: str
    field_name: str = ""
    can_auto_fix: bool = False


@dataclass
class PreflightResult:
    """Complete results of preflight validation."""
    issues: list[PreflightIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """True if there are no blocking errors."""
        return not any(i.severity == Severity.ERROR for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == Severity.WARNING for i in self.issues)

    @property
    def errors(self) -> list[PreflightIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[PreflightIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    @property
    def summary_text(self) -> str:
        """Human-readable one-line status summary."""
        if not self.is_valid:
            err_count = len(self.errors)
            return f"{err_count} blocking error{'s' if err_count != 1 else ''} — cannot print"
        elif self.has_warnings:
            warn_count = len(self.warnings)
            return f"{warn_count} warning{'s' if warn_count != 1 else ''}"
        else:
            return "Ready to print"


class PreflightChecker:
    """Validates print jobs before submission."""

    @staticmethod
    def check(
        documents: list[Document],
        settings: PrintSettings,
        printer: Optional[PrinterInfo] = None,
        capabilities: Optional[PrinterCapabilities] = None,
    ) -> PreflightResult:
        """Perform comprehensive preflight checks.

        Args:
            documents: List of loaded documents to print.
            settings: Current print settings.
            printer: Selected printer info (optional).
            capabilities: Selected printer capabilities (optional).

        Returns:
            PreflightResult containing errors, warnings, and informational notes.
        """
        result = PreflightResult()

        # ── 1. Document checks ────────────────────────────────────────
        if not documents:
            result.issues.append(PreflightIssue(
                severity=Severity.ERROR,
                message="No files loaded to print.",
                field_name="documents",
            ))
            return result

        total_pages = sum(doc.page_count for doc in documents)
        if total_pages == 0:
            result.issues.append(PreflightIssue(
                severity=Severity.ERROR,
                message="Loaded documents have no printable pages.",
                field_name="documents",
            ))

        # ── 2. Page Range checks ──────────────────────────────────────
        if settings.page_range_mode == PageRangeMode.CUSTOM:
            range_str = settings.page_range_str.strip()
            if not range_str:
                result.issues.append(PreflightIssue(
                    severity=Severity.ERROR,
                    message="Custom page range is empty.",
                    field_name="page_range",
                ))
            else:
                # The range applies to every document; images print whole regardless
                for doc in documents:
                    if getattr(doc, "is_image", False) is True:
                        continue
                    if not parse_page_range(range_str, doc.page_count):
                        pages = "1 page" if doc.page_count == 1 else f"{doc.page_count} pages"
                        result.issues.append(PreflightIssue(
                            severity=Severity.ERROR,
                            message=f"Page range '{range_str}' doesn't fit \"{doc.filename}\" ({pages}).",
                            field_name="page_range",
                        ))

        # ── 3. Image DPI / Resolution checks ──────────────────────────
        for doc in documents:
            if hasattr(doc, "width_px") and hasattr(doc, "height_px"):
                # Estimate effective DPI on target paper
                # Default A4 printable width is ~200mm (~7.87 inches)
                paper_w_in = 7.87
                if doc.width_px > 0:
                    effective_dpi = doc.width_px / paper_w_in
                    if effective_dpi < 100:
                        result.issues.append(PreflightIssue(
                            severity=Severity.WARNING,
                            message=f'"{doc.filename}" has low resolution ({doc.width_px}×{doc.height_px} px, ~{effective_dpi:.0f} DPI). Output may look pixelated.',
                            field_name="resolution",
                        ))
                    elif effective_dpi < 150:
                        result.issues.append(PreflightIssue(
                            severity=Severity.INFO,
                            message=f'"{doc.filename}" is moderate resolution (~{effective_dpi:.0f} DPI). Recommended is 300 DPI for photos.',
                            field_name="resolution",
                        ))

        # ── 4. Printer checks ─────────────────────────────────────────
        if printer:
            if printer.state == PrinterState.STOPPED:
                result.issues.append(PreflightIssue(
                    severity=Severity.ERROR,
                    message=f'Printer "{printer.name}" is stopped or offline.',
                    field_name="printer",
                ))
            elif not printer.is_accepting_jobs:
                result.issues.append(PreflightIssue(
                    severity=Severity.ERROR,
                    message=f'Printer "{printer.name}" is currently not accepting jobs.',
                    field_name="printer",
                ))

        # ── 5. Capabilities checks ────────────────────────────────────
        if capabilities:
            # Duplex
            if settings.duplex != DuplexMode.OFF and not capabilities.supports_duplex:
                result.issues.append(PreflightIssue(
                    severity=Severity.WARNING,
                    message="Two-sided printing requested, but this printer does not support duplex.",
                    field_name="duplex",
                ))

            # Color
            if settings.color_mode == ColorMode.COLOR and not capabilities.has_color():
                result.issues.append(PreflightIssue(
                    severity=Severity.WARNING,
                    message="Color printing selected, but this printer is monochrome only.",
                    field_name="color_mode",
                ))

            # Borderless
            margins = settings.margins
            if margins.top == 0 and margins.bottom == 0 and margins.left == 0 and margins.right == 0:
                if not capabilities.supports_borderless:
                    result.issues.append(PreflightIssue(
                        severity=Severity.WARNING,
                        message="Zero margins selected, but this printer does not support borderless printing. Edges may be clipped.",
                        field_name="margins",
                    ))

            # Paper size support
            if settings.paper_size_name != "Custom" and capabilities.supported_media:
                supported_names = [p.name for p in capabilities.get_paper_sizes()]
                if settings.paper_size_name not in supported_names:
                    result.issues.append(PreflightIssue(
                        severity=Severity.WARNING,
                        message=f'Paper size "{settings.paper_size_name}" may not be supported by this printer.',
                        field_name="paper_size",
                    ))

        # ── 6. Copies & Settings ──────────────────────────────────────
        if settings.copies < 1:
            result.issues.append(PreflightIssue(
                severity=Severity.ERROR,
                message="Number of copies must be at least 1.",
                field_name="copies",
            ))

        return result
