"""PrintForge entry point — CLI argument parsing and application launch."""

from __future__ import annotations

import argparse
import logging
import sys
import os


def main() -> int:
    """Main entry point for PrintForge."""
    parser = argparse.ArgumentParser(
        prog="printforge",
        description="PrintForge — A modern printing application for Fedora Linux",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Files to open for printing",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock printing backend (for development/testing)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"PrintForge {_get_version()}",
    )

    # CLI-only print mode
    parser.add_argument("--printer", help="Printer name (CLI print mode)")
    parser.add_argument("--paper", default="A4", help="Paper size (default: A4)")
    parser.add_argument("--copies", type=int, default=1, help="Number of copies")
    parser.add_argument("--color", action="store_true", help="Print in color")
    parser.add_argument("--grayscale", action="store_true", help="Print in grayscale")
    parser.add_argument("--landscape", action="store_true", help="Landscape orientation")
    parser.add_argument("--duplex", choices=["off", "long-edge", "short-edge"],
                        default="off", help="Duplex mode")
    parser.add_argument("--quality", choices=["draft", "normal", "high"],
                        default="normal", help="Print quality")
    parser.add_argument("--resolution", "--dpi", dest="resolution",
                        help="Print resolution (e.g. 300, 600, 1200, 300x300dpi, 600x600dpi, 1200x1200dpi)")
    parser.add_argument("--no-gui", action="store_true",
                        help="Print directly without GUI")
    parser.add_argument("--export-pdf", metavar="PATH",
                        help="Export print-ready PDF to file (for verification)")


    args = parser.parse_args()

    # Set up logging
    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Resolve file paths
    files = [os.path.abspath(f) for f in args.files] if args.files else []

    # Export PDF mode (no GUI, no printer needed)
    if args.export_pdf and files:
        return _export_pdf(args, files)

    # CLI-only mode
    if args.no_gui and files and args.printer:
        return _cli_print(args, files)

    # GUI mode
    return _gui_mode(args, files)


def _get_version() -> str:
    try:
        from printforge import __version__
        return __version__
    except ImportError:
        return "unknown"


def _gui_mode(args: argparse.Namespace, files: list[str]) -> int:
    """Launch the GTK4 GUI."""
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")

    from printforge.application import PrintForgeApp

    app = PrintForgeApp(use_mock=args.mock, files=files)
    return app.run(None)


def _cli_print(args: argparse.Namespace, files: list[str]) -> int:
    """Print files directly from the command line without GUI."""
    from printforge.config.print_settings import (
        PrintSettings, ColorMode, Orientation, DuplexMode, PrintQuality,
    )
    from printforge.documents.base import DocumentFactory, is_supported
    from printforge.documents.print_prep import PrintPreparer
    from printforge.printing.cups_backend import CupsBackend, CupsError

    log = logging.getLogger("printforge.cli")

    # Build settings
    settings = PrintSettings()
    settings.printer_name = args.printer
    settings.copies = max(1, args.copies)
    settings.paper_size_name = args.paper

    if args.grayscale:
        settings.color_mode = ColorMode.GRAYSCALE
    elif args.color:
        settings.color_mode = ColorMode.COLOR

    if args.landscape:
        settings.orientation = Orientation.LANDSCAPE

    duplex_map = {
        "off": DuplexMode.OFF,
        "long-edge": DuplexMode.LONG_EDGE,
        "short-edge": DuplexMode.SHORT_EDGE,
    }
    settings.duplex = duplex_map.get(args.duplex, DuplexMode.OFF)

    quality_map = {
        "draft": PrintQuality.DRAFT,
        "normal": PrintQuality.NORMAL,
        "high": PrintQuality.HIGH,
    }
    settings.quality = quality_map.get(args.quality, PrintQuality.NORMAL)

    if getattr(args, 'resolution', None):
        res = str(args.resolution).strip()
        settings.resolution = f"{res}x{res}dpi" if res.isdigit() else res

    # Connect to CUPS
    from printforge.config.settings import AppSettings
    app_settings = AppSettings.get()
    backend = CupsBackend(user_id=app_settings.user_id, send_user_id=app_settings.send_user_id)
    if not backend.is_available:
        print("Error: CUPS is not available. Is the cups service running?", file=sys.stderr)
        return 1

    # Verify printer exists
    printers = backend.get_printers()
    printer_names = [p.name for p in printers]
    if args.printer not in printer_names:
        print(f"Error: Printer '{args.printer}' not found.", file=sys.stderr)
        print(f"Available printers: {', '.join(printer_names)}", file=sys.stderr)
        return 1

    preparer = PrintPreparer()
    capabilities = backend.get_capabilities(args.printer)

    for filepath in files:
        if not os.path.isfile(filepath):
            print(f"Error: File not found: {filepath}", file=sys.stderr)
            continue

        if not is_supported(filepath):
            print(f"Error: Unsupported format: {filepath}", file=sys.stderr)
            continue

        doc = DocumentFactory.create(filepath)
        if not doc or not doc.is_valid:
            print(f"Error: Cannot load file: {filepath}", file=sys.stderr)
            continue

        # Prepare
        prepared_path = preparer.prepare(doc, settings)
        if not prepared_path:
            print(f"Error: Cannot prepare file for printing: {filepath}", file=sys.stderr)
            continue

        # Print
        try:
            options = settings.to_cups_options(capabilities)
            job_id = backend.print_file(
                args.printer,
                prepared_path,
                os.path.basename(filepath),
                options,
            )
            print(f"✓ Sent to {args.printer}: {os.path.basename(filepath)} (Job #{job_id})")
        except CupsError as e:
            print(f"Error: {e}", file=sys.stderr)

    preparer.cleanup()
    return 0


def _export_pdf(args: argparse.Namespace, files: list[str]) -> int:
    """Export files to print-ready PDF for verification."""
    from printforge.config.print_settings import (
        PrintSettings, ColorMode, Orientation,
    )
    from printforge.documents.base import DocumentFactory, is_supported
    from printforge.documents.print_prep import PrintPreparer

    log = logging.getLogger("printforge.export")

    settings = PrintSettings()
    settings.copies = max(1, getattr(args, 'copies', 1))
    settings.paper_size_name = getattr(args, 'paper', 'A4')

    if getattr(args, 'grayscale', False):
        settings.color_mode = ColorMode.GRAYSCALE
    if getattr(args, 'landscape', False):
        settings.orientation = Orientation.LANDSCAPE

    if getattr(args, 'resolution', None):
        res = str(args.resolution).strip()
        settings.resolution = f"{res}x{res}dpi" if res.isdigit() else res

    preparer = PrintPreparer()
    output_path = args.export_pdf

    for filepath in files:
        if not os.path.isfile(filepath):
            print(f"Error: File not found: {filepath}", file=sys.stderr)
            continue

        if not is_supported(filepath):
            print(f"Error: Unsupported format: {filepath}", file=sys.stderr)
            continue

        doc = DocumentFactory.create(filepath)
        if not doc or not doc.is_valid:
            print(f"Error: Cannot load file: {filepath}", file=sys.stderr)
            continue

        if preparer.prepare_to_file(doc, settings, output_path):
            print(f"✓ Exported to {output_path}: {os.path.basename(filepath)}")
        else:
            print(f"Error: Failed to export: {filepath}", file=sys.stderr)

    preparer.cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
