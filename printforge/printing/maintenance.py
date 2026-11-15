"""Printer maintenance — status explanations, diagnostics, and service pages.

Covers what can be done from the computer for any CUPS printer: explaining
what the printer reports, checking the queue end to end, printing test and
calibration charts, and sending the driver's own maintenance commands.
"""

from __future__ import annotations

import math
import socket
import subprocess
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import cairo

from printforge.printing.ppd import PpdInfo
from printforge.printing.printer import (
    PrinterState, PrinterStatus, Severity, StatusIssue, SupplyLevel,
)
from printforge.utils.paper import PaperSize, DEFAULT_PAPER
from printforge.utils.units import mm_to_pt

COMMAND_FORMAT = "application/vnd.cups-command"

# ── What the printer reports ──────────────────────────────────────────

# IPP printer-state-reasons keyword → (severity, title, advice, fix)
_REASONS: dict[str, tuple[Severity, str, str, str]] = {
    "media-empty": (Severity.ERROR, "Out of paper", "Load paper into the tray, then press the printer's OK or Start key.", ""),
    "media-needed": (Severity.ERROR, "Paper needed", "Load the paper size the job asks for, or pick the size that is loaded.", ""),
    "media-low": (Severity.WARNING, "Paper is running low", "Add paper soon.", ""),
    "media-jam": (Severity.ERROR, "Paper jam", "Open the covers, pull the jammed sheet out in the direction of travel, and close them.", ""),
    "toner-empty": (Severity.ERROR, "Toner is empty", "Replace the toner cartridge.", ""),
    "toner-low": (Severity.WARNING, "Toner is low", "Printing still works. Have a replacement cartridge ready.", ""),
    "marker-supply-empty": (Severity.ERROR, "Ink or toner is empty", "Replace the empty cartridge.", ""),
    "marker-supply-low": (Severity.WARNING, "Ink or toner is low", "Printing still works. Have a replacement ready.", ""),
    "marker-waste-full": (Severity.ERROR, "Waste container is full", "Replace the waste toner or maintenance box.", ""),
    "marker-waste-almost-full": (Severity.WARNING, "Waste container is almost full", "Have a replacement waste container ready.", ""),
    "developer-empty": (Severity.ERROR, "Developer is empty", "Replace the developer unit.", ""),
    "developer-low": (Severity.WARNING, "Developer is low", "Have a replacement developer unit ready.", ""),
    "opc-life-over": (Severity.ERROR, "Drum unit has reached end of life", "Replace the drum (photoconductor) unit.", ""),
    "opc-near-eol": (Severity.WARNING, "Drum unit is nearly worn out", "Have a replacement drum unit ready.", ""),
    "door-open": (Severity.ERROR, "A door is open", "Close all doors and covers on the printer.", ""),
    "cover-open": (Severity.ERROR, "A cover is open", "Close all doors and covers on the printer.", ""),
    "interlock-open": (Severity.ERROR, "A cover is open", "Close all doors and covers on the printer.", ""),
    "input-tray-missing": (Severity.ERROR, "Paper tray is missing", "Push the paper tray all the way in.", ""),
    "output-tray-missing": (Severity.ERROR, "Output tray is missing", "Refit the output tray.", ""),
    "output-area-full": (Severity.ERROR, "Output tray is full", "Remove the printed pages from the output tray.", ""),
    "output-area-almost-full": (Severity.WARNING, "Output tray is almost full", "Remove the printed pages from the output tray.", ""),
    "offline": (Severity.ERROR, "Printer is offline", "Check that it is switched on and the cable or network is connected.", ""),
    "shutdown": (Severity.ERROR, "Printer is switched off", "Switch the printer on.", ""),
    "connecting-to-device": (Severity.WARNING, "Connecting to the printer", "If this stays, check the cable or network and that the printer is on.", ""),
    "timed-out": (Severity.ERROR, "Printer is not responding", "Switch it off and on again, then resume the queue.", "resume"),
    "paused": (Severity.ERROR, "Printer is paused", "Resume the printer to continue printing.", "resume"),
    "stopped-partly": (Severity.WARNING, "Part of the printer has stopped", "Check the printer's display for details.", ""),
    "fuser-over-temp": (Severity.ERROR, "Fuser is too hot", "Switch the printer off for a few minutes. Call service if it returns.", ""),
    "fuser-under-temp": (Severity.WARNING, "Fuser is warming up", "Wait for the printer to warm up.", ""),
    "spool-area-full": (Severity.ERROR, "Print spool is full", "Clear waiting jobs to free space.", "clear-jobs"),
    "cups-missing-filter": (Severity.ERROR, "The driver is missing a component", "Reinstall the printer or its driver package from System Settings.", ""),
    "cups-insecure-filter": (Severity.ERROR, "The driver has unsafe file permissions", "Reinstall the printer's driver package.", ""),
}
_QUIET_REASONS = {"none", "cups-waiting-for-job-completed", "moving-to-paused", "stopping", "cups-remote-pending"}
_REASON_SUFFIXES = ("-error", "-warning", "-report")


def describe_reason(reason: str) -> Optional[StatusIssue]:
    """Explain an IPP printer-state-reasons keyword. None for reasons worth no mention."""
    keyword = reason.strip()
    severity_override = None
    for suffix in _REASON_SUFFIXES:
        if keyword.endswith(suffix):
            keyword = keyword[: -len(suffix)]
            if suffix == "-warning":
                severity_override = Severity.WARNING
            elif suffix == "-report":
                severity_override = Severity.INFO
            break
    if not keyword or keyword in _QUIET_REASONS:
        return None

    known = _REASONS.get(keyword)
    if known:
        severity, title, advice, fix = known
        return StatusIssue(severity_override or severity, title, advice, fix)
    title = keyword.replace("-", " ").capitalize()
    return StatusIssue(severity_override or Severity.WARNING, title, "Check the printer's display for details.")


def parse_supplies(attrs: dict) -> list[SupplyLevel]:
    """Toner and ink levels from CUPS marker-* attributes."""
    def as_list(value) -> list:
        if value is None:
            return []
        return list(value) if isinstance(value, (list, tuple)) else [value]

    names = as_list(attrs.get("marker-names"))
    levels = as_list(attrs.get("marker-levels"))
    colors = as_list(attrs.get("marker-colors"))
    supplies = []
    for i, name in enumerate(names):
        try:
            level = int(levels[i])
        except (IndexError, TypeError, ValueError):
            level = -1
        color = str(colors[i]) if i < len(colors) else ""
        supplies.append(SupplyLevel(
            name=str(name),
            level=level if 0 <= level <= 100 else -1,
            color=color if color.startswith("#") else "",
        ))
    return supplies


# ── Diagnostics ───────────────────────────────────────────────────────

_DEFAULT_PORTS = {"ipp": 631, "ipps": 631, "http": 80, "https": 443, "socket": 9100, "lpd": 515}


def system_paper_name() -> str:
    """Paper size this computer's region uses ('A4' or 'Letter')."""
    try:
        output = subprocess.run(
            ["locale", "-k", "LC_PAPER"], capture_output=True, text=True, timeout=5,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return DEFAULT_PAPER.name
    height = next((line.partition("=")[2] for line in output.splitlines() if line.startswith("height=")), "")
    return "Letter" if height.strip() == "279" else DEFAULT_PAPER.name


def check_connection(uri: str) -> Optional[bool]:
    """Whether the device behind `uri` can be reached. None when it can't be told."""
    scheme = urlparse(uri).scheme.lower()
    if scheme == "usb":
        from printforge.printing.pjl import _usb_device_id
        return bool(_usb_device_id(uri))
    if scheme in _DEFAULT_PORTS:
        parsed = urlparse(uri)
        if not parsed.hostname:
            return None
        try:
            with socket.create_connection((parsed.hostname, parsed.port or _DEFAULT_PORTS[scheme]), timeout=3):
                return True
        except OSError:
            return False
    return None


def diagnose(
    status: PrinterStatus, ppd: Optional[PpdInfo] = None, paper_name: str = "",
) -> list[StatusIssue]:
    """Check the queue end to end. Returns every check, passed or failed, in order.

    `paper_name` is the paper the user is printing on, to compare with the
    queue's default.
    """
    checks: list[StatusIssue] = []

    def passed(title: str) -> None:
        checks.append(StatusIssue(Severity.OK, title))

    passed("Print service is running")

    reachable = check_connection(status.uri)
    if reachable is False:
        if status.uri.lower().startswith("usb"):
            advice = "Check the USB cable and that the printer is switched on."
        else:
            advice = "Check that the printer is switched on and on the same network."
        checks.append(StatusIssue(Severity.ERROR, "Printer is not connected", advice))
    elif reachable:
        passed("Printer is connected")

    if status.state == PrinterState.STOPPED:
        if reachable is False:
            advice = "It was paused when it went offline. Once it is back on, resume it if it doesn't resume by itself."
        else:
            advice = status.state_message or "A failed job paused the queue. Resume it to continue printing."
        checks.append(StatusIssue(Severity.ERROR, "Printer is paused", advice, "resume"))
    else:
        passed("Printer is not paused")

    if status.is_accepting_jobs:
        passed("Printer accepts new jobs")
    else:
        checks.append(StatusIssue(
            Severity.ERROR, "Printer is rejecting new jobs", "Let it accept jobs again.", "accept",
        ))

    reported = [issue for issue in status.issues if not (issue.fix == "resume" and status.state == PrinterState.STOPPED)]
    if reported:
        checks.extend(reported)
    else:
        passed("Printer reports no problems")

    if status.queued_jobs and status.state != PrinterState.PROCESSING:
        jobs = "1 job is" if status.queued_jobs == 1 else f"{status.queued_jobs} jobs are"
        checks.append(StatusIssue(
            Severity.WARNING, f"{jobs} waiting but nothing is printing",
            "A stuck job can block the ones behind it. Clear the queue and print again.", "clear-jobs",
        ))
    else:
        passed("No stuck jobs")

    if ppd:
        page_size = ppd.option("PageSize")
        if page_size and paper_name and page_size.default != paper_name and page_size.has_choice(paper_name):
            checks.append(StatusIssue(
                Severity.WARNING, f"Other apps print on {page_size.default} paper by default, not {paper_name}",
                f"A job sent for {page_size.default} makes the printer wait for paper it may not hold. "
                f"Make {paper_name} the default if that is what's in the tray.",
                "default-paper",
            ))
        elif page_size and paper_name:
            passed("Default paper size matches yours")

        if ppd.is_generic:
            checks.append(StatusIssue(
                Severity.INFO, "A generic driver is in use",
                "Printing works, but supply levels and model-specific options aren't available. "
                "Install the manufacturer's driver in System Settings for those.",
            ))
    return checks


# ── Driver maintenance commands ───────────────────────────────────────

@dataclass(frozen=True)
class DeviceCommand:
    command: str  # line sent in the CUPS command file
    title: str
    description: str


_DEVICE_COMMANDS = {
    "Clean": DeviceCommand("Clean all", "Clean Print Heads", "Run the printer's cleaning cycle. Uses a little ink."),
    "PrintAlignmentPage": DeviceCommand("PrintAlignmentPage", "Align Print Heads", "Print the printer's own alignment page."),
    "PrintSelfTestPage": DeviceCommand("PrintSelfTestPage", "Printer Self-Test", "Print the printer's built-in test page."),
    "AutoConfigure": DeviceCommand("AutoConfigure", "Detect Installed Options", "Ask the printer which trays and units are fitted."),
    "ReportLevels": DeviceCommand("ReportLevels", "Refresh Supply Levels", "Ask the printer for its ink or toner levels."),
}
# A PostScript queue's command filter knows nothing about cleaning or alignment
_POSTSCRIPT_COMMANDS = {"PrintSelfTestPage", "AutoConfigure", "ReportLevels"}


def supported_commands(reported: list[str], ppd: Optional[PpdInfo]) -> list[str]:
    """The maintenance commands that will actually do something on this queue."""
    commands = [name for name in reported if name in _DEVICE_COMMANDS]
    if ppd and ppd.is_postscript:
        commands = [name for name in commands if name in _POSTSCRIPT_COMMANDS]
    return commands


def device_command(name: str) -> Optional[DeviceCommand]:
    return _DEVICE_COMMANDS.get(name)


def build_command_file(command: str) -> bytes:
    return f"#CUPS-COMMAND\n{command}\n".encode("ascii")


# ── Service pages ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class ServicePage:
    kind: str
    title: str
    description: str
    sheets: int = 1


SERVICE_PAGES: list[ServicePage] = [
    ServicePage("test", "Test Page", "Text, colors and a border: a quick check that printing works."),
    ServicePage("color", "Color Calibration Chart", "Color and gray steps for checking color balance after calibrating."),
    ServicePage("alignment", "Alignment Page", "Margin frames, rulers and registration marks for checking skew and color alignment."),
    ServicePage("streaks", "Streak & Banding Check", "Solid bands of each color to locate a dirty drum, low toner or clogged nozzles."),
    ServicePage("cleaning", "Cleaning Sheets", "Heavy-coverage sheets that carry stray toner or ink out of the paper path.", sheets=5),
]

_INKS = [
    ("Cyan", (0.0, 1.0, 1.0)),
    ("Magenta", (1.0, 0.0, 1.0)),
    ("Yellow", (1.0, 1.0, 0.0)),
    ("Black", (0.0, 0.0, 0.0)),
]
_CHART_COLORS = _INKS + [
    ("Red", (1.0, 0.0, 0.0)),
    ("Green", (0.0, 1.0, 0.0)),
    ("Blue", (0.0, 0.0, 1.0)),
]
_EDGE = mm_to_pt(12.0)


def get_service_page(kind: str) -> Optional[ServicePage]:
    return next((page for page in SERVICE_PAGES if page.kind == kind), None)


def _tint(color: tuple[float, float, float], amount: float) -> tuple[float, float, float]:
    """`color` at `amount` (0–1) coverage on white paper."""
    return tuple(1.0 - (1.0 - channel) * amount for channel in color)


def _text(ctx: cairo.Context, x: float, y: float, text: str, size: float = 9, bold: bool = False) -> None:
    ctx.select_font_face(
        "Sans", cairo.FONT_SLANT_NORMAL,
        cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL,
    )
    ctx.set_font_size(size)
    ctx.set_source_rgb(0, 0, 0)
    ctx.move_to(x, y)
    ctx.show_text(text)
    ctx.new_path()  # show_text leaves a current point that later arcs would connect to


def _heading(ctx: cairo.Context, title: str, subtitle: str) -> float:
    """Draw the page heading. Returns the y where content can start."""
    _text(ctx, _EDGE, _EDGE + 14, title, 16, bold=True)
    _text(ctx, _EDGE, _EDGE + 28, subtitle, 8.5)
    return _EDGE + 44


def _step_wedge(ctx, x, y, width, height, color, steps: int = 10, labels: bool = True) -> None:
    """A row of patches from light to full coverage."""
    patch = width / steps
    for step in range(steps):
        amount = (step + 1) / steps
        ctx.set_source_rgb(*_tint(color, amount))
        ctx.rectangle(x + step * patch, y, patch, height)
        ctx.fill()
        if labels:
            _text(ctx, x + step * patch + 2, y + height + 9, f"{round(amount * 100)}%", 6.5)
    ctx.set_source_rgb(0.6, 0.6, 0.6)
    ctx.set_line_width(0.4)
    ctx.rectangle(x, y, width, height)
    ctx.stroke()


def _draw_test_page(ctx, width, height, printer_name: str) -> None:
    y = _heading(ctx, "PrintForge Test Page", f"{printer_name}  ·  {time.strftime('%Y-%m-%d %H:%M')}")
    inner = width - 2 * _EDGE

    # Border 5 mm from the paper edge: every side should be visible and parallel
    ctx.set_source_rgb(0, 0, 0)
    ctx.set_line_width(0.5)
    inset = mm_to_pt(5.0)
    ctx.rectangle(inset, inset, width - 2 * inset, height - 2 * inset)
    ctx.stroke()

    bar_width = inner / len(_CHART_COLORS)
    for i, (name, color) in enumerate(_CHART_COLORS):
        ctx.set_source_rgb(*color)
        ctx.rectangle(_EDGE + i * bar_width, y, bar_width, 46)
        ctx.fill()
        _text(ctx, _EDGE + i * bar_width + 2, y + 57, name, 7.5)
    y += 76

    _text(ctx, _EDGE, y, "Gray steps: each patch should look different from its neighbors", 8.5)
    _step_wedge(ctx, _EDGE, y + 6, inner, 30, (0, 0, 0), steps=16, labels=False)
    y += 60

    for size, sample in (
        (6, "The quick brown fox jumps over the lazy dog 0123456789"),
        (8, "The quick brown fox jumps over the lazy dog 0123456789"),
        (10, "The quick brown fox jumps over the lazy dog 0123456789"),
        (12, "The quick brown fox jumps over the lazy dog"),
        (16, "The quick brown fox jumps over"),
        (24, "The quick brown fox"),
    ):
        y += size * 1.5
        _text(ctx, _EDGE, y, f"{size} pt — {sample}", size)
    y += 28

    _text(ctx, _EDGE, y, "Fine lines: should be even, unbroken and sharp", 8.5)
    y += 8
    for i, line_width in enumerate((0.25, 0.5, 1.0, 2.0)):
        ctx.set_source_rgb(0, 0, 0)
        ctx.set_line_width(line_width)
        ctx.move_to(_EDGE, y + i * 9)
        ctx.line_to(_EDGE + inner, y + i * 9)
        ctx.stroke()


def _draw_color_chart(ctx, width, height, printer_name: str) -> None:
    y = _heading(
        ctx, "Color Calibration Chart",
        "Steps should darken evenly, with no color cast in the grays. Run the printer's calibration, then reprint to compare.",
    )
    inner = width - 2 * _EDGE
    row_height = min(44.0, (height - y - _EDGE - 150) / (len(_CHART_COLORS) + 1) - 16)

    for name, color in _CHART_COLORS:
        _text(ctx, _EDGE, y + 8, name, 8.5, bold=True)
        _step_wedge(ctx, _EDGE, y + 12, inner, row_height, color)
        y += row_height + 28

    _text(ctx, _EDGE, y + 8, "Neutral gray (21 steps)", 8.5, bold=True)
    _step_wedge(ctx, _EDGE, y + 12, inner, row_height, (0, 0, 0), steps=21, labels=False)
    y += row_height + 28

    _text(ctx, _EDGE, y + 8, "Smooth blends: look for bands or sudden jumps", 8.5, bold=True)
    y += 12
    blend_height = max(10.0, min(18.0, (height - y - _EDGE) / len(_INKS) - 3))
    for _, color in _INKS:
        gradient = cairo.LinearGradient(_EDGE, 0, _EDGE + inner, 0)
        gradient.add_color_stop_rgb(0, 1, 1, 1)
        gradient.add_color_stop_rgb(1, *color)
        ctx.set_source(gradient)
        ctx.rectangle(_EDGE, y, inner, blend_height)
        ctx.fill()
        y += blend_height + 3


def _draw_alignment_page(ctx, width, height, printer_name: str) -> None:
    # Heading sits inside the innermost frame
    ruler = mm_to_pt(20.0)
    _text(ctx, ruler, ruler + 14, "Alignment Page", 16, bold=True)
    _text(ctx, ruler, ruler + 28, "Frames should be parallel to the paper edges and complete on all four sides.", 8.5)

    # Frames at fixed distances from the paper edge show margins and skew
    for inset_mm, dash in ((5, [1, 2]), (10, []), (15, [4, 2])):
        inset = mm_to_pt(inset_mm)
        ctx.set_source_rgb(0, 0, 0)
        ctx.set_line_width(0.5)
        ctx.set_dash(dash)
        ctx.rectangle(inset, inset, width - 2 * inset, height - 2 * inset)
        ctx.stroke()
        _text(ctx, width / 2 - 12, height - inset - 2, f"{inset_mm} mm", 6.5)
    ctx.set_dash([])

    # Millimeter rulers from the top-left corner
    for mm in range(0, int(width * 25.4 / 72.0) - 39, 1):
        x = ruler + mm_to_pt(mm)
        tick = 9 if mm % 10 == 0 else 5 if mm % 5 == 0 else 3
        ctx.set_line_width(0.3)
        ctx.move_to(x, ruler + 46)
        ctx.line_to(x, ruler + 46 + tick)
        ctx.stroke()
        if mm % 10 == 0:
            _text(ctx, x + 1, ruler + 64, str(mm), 6)
    for mm in range(0, int(height * 25.4 / 72.0) - 110, 1):
        y = ruler + 80 + mm_to_pt(mm)
        tick = 9 if mm % 10 == 0 else 5 if mm % 5 == 0 else 3
        ctx.move_to(ruler, y)
        ctx.line_to(ruler + tick, y)
        ctx.stroke()
        if mm % 10 == 0:
            _text(ctx, ruler + 11, y + 2, str(mm), 6)

    # Each ink draws the same cross: color fringes mean the colors are out of register
    center_x, center_y = width / 2, height / 2
    _text(ctx, center_x - 118, center_y - 74, "Color registration: each cross should be one clean dark line", 8)
    for column, offset in enumerate((-90, 0, 90)):
        cross_x = center_x + offset
        for _, color in _INKS:
            ctx.set_source_rgb(*color)
            ctx.set_line_width(0.6)
            ctx.move_to(cross_x - 30, center_y)
            ctx.line_to(cross_x + 30, center_y)
            ctx.move_to(cross_x, center_y - 30)
            ctx.line_to(cross_x, center_y + 30)
            ctx.stroke()
        ctx.set_source_rgb(0, 0, 0)
        ctx.set_line_width(0.4)
        ctx.arc(cross_x, center_y, 10 + column * 6, 0, 2 * math.pi)
        ctx.stroke()

    _text(ctx, center_x - 132, center_y + 60, "Printed two-sided, the frames on both sides should line up against a light.", 8)

    # Corner marks
    mark = mm_to_pt(10.0)
    for corner_x, corner_y in ((mark, mark), (width - mark, mark), (mark, height - mark), (width - mark, height - mark)):
        ctx.set_line_width(0.5)
        ctx.new_sub_path()
        ctx.arc(corner_x, corner_y, 5, 0, 2 * math.pi)
        ctx.move_to(corner_x - 8, corner_y)
        ctx.line_to(corner_x + 8, corner_y)
        ctx.move_to(corner_x, corner_y - 8)
        ctx.line_to(corner_x, corner_y + 8)
        ctx.stroke()


def _draw_streak_page(ctx, width, height, printer_name: str) -> None:
    y = _heading(
        ctx, "Streak & Banding Check",
        "A line or gap running down the page through one color points to that color's drum, toner or nozzles.",
    )
    inner = width - 2 * _EDGE
    band = (height - y - _EDGE - 70) / (len(_INKS) * 2) - 6

    for name, color in _INKS:
        for amount in (1.0, 0.4):
            ctx.set_source_rgb(*_tint(color, amount))
            ctx.rectangle(_EDGE, y, inner, band)
            ctx.fill()
            _text(ctx, _EDGE, y + band + 8, f"{name} {round(amount * 100)}%", 6.5)
            y += band + 12

    # Fine vertical lines: a clogged nozzle or scratched drum breaks them
    y += 4
    ctx.set_source_rgb(0, 0, 0)
    ctx.set_line_width(0.3)
    x = _EDGE
    while x <= _EDGE + inner:
        ctx.move_to(x, y)
        ctx.line_to(x, y + 40)
        x += 2.0
    ctx.stroke()


def _draw_cleaning_sheets(ctx, surface, width, height, printer_name: str) -> None:
    """One heavy-coverage sheet per ink, then a blank sheet to pick up what was loosened."""
    for name, color in _INKS:
        ctx.set_source_rgb(*_tint(color, 0.6))
        ctx.rectangle(_EDGE, _EDGE + 16, width - 2 * _EDGE, height - 2 * _EDGE - 16)
        ctx.fill()
        _text(ctx, _EDGE, _EDGE + 8, f"PrintForge cleaning sheet — {name}", 8)
        surface.show_page()
    _text(ctx, _EDGE, _EDGE + 8, "PrintForge cleaning sheet — blank pass. Marks on this sheet mean another round is worthwhile.", 8)


def build_service_page(kind: str, output_path: str, paper: Optional[PaperSize] = None, printer_name: str = "") -> bool:
    """Write the service page `kind` as a PDF. Returns False for an unknown kind."""
    if not get_service_page(kind):
        return False
    paper = paper or DEFAULT_PAPER
    width, height = paper.width_pt, paper.height_pt

    surface = cairo.PDFSurface(output_path, width, height)
    ctx = cairo.Context(surface)
    if kind == "test":
        _draw_test_page(ctx, width, height, printer_name)
    elif kind == "color":
        _draw_color_chart(ctx, width, height, printer_name)
    elif kind == "alignment":
        _draw_alignment_page(ctx, width, height, printer_name)
    elif kind == "streaks":
        _draw_streak_page(ctx, width, height, printer_name)
    elif kind == "cleaning":
        _draw_cleaning_sheets(ctx, surface, width, height, printer_name)
    surface.show_page()
    surface.finish()
    return True

