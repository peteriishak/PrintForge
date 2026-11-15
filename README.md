# PrintForge 🖨️

A **native, modern desktop printing application for Fedora Linux** built with GTK4 and Libadwaita. PrintForge makes printing files and images effortless while giving you complete, granular control over print settings, an interactive real-time preview, and full CUPS integration.

![Fedora Linux](https://img.shields.io/badge/Fedora-Linux-blue?logo=fedora)
![GTK4 + Libadwaita](https://img.shields.io/badge/UI-GTK4%20%2B%20Libadwaita-blue)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-green?logo=python)
![CUPS](https://img.shields.io/badge/Backend-CUPS%20%2F%20IPP-orange)
![License](https://img.shields.io/badge/License-GPL--3.0-blue)

---

## Highlights & Features

### 📄 Multi-Format Document Support
* **Images**: PNG, JPEG, WebP, BMP, TIFF with resolution/DPI detection and Pillow-accelerated handling.
* **Vector Graphics**: SVG rendering via `librsvg`.
* **PDFs**: Native rendering, pagination, and multi-page preview via `Poppler-GLib`.
* **Plain Text**: Paginated text documents with formatting.
* **Multi-File Queue**: Add multiple documents via drag-and-drop or file picker; switch between documents or print all at once.

### 🔍 Interactive Real-Time Preview
* Live Cairo-driven paper simulation matching the chosen paper size, orientation, margins, and content layout.
* Zoom in/out, fit-to-page, fit-to-width, and mouse scroll zooming.
* Multi-page navigation (previous / next / page selector).
* Accurate job totals in the summary bar — pages across every queued file, plus sheets of paper once copies, two-sided or N-up change the amount (`2 files · 4 pages · 2 copies · 6 sheets`). Page ranges and the paper size (for text files) are counted exactly as they print.

### ⚙️ Comprehensive Print Controls
* **Printer Selection**: Automatic printer discovery via CUPS, default printer detection, and real-time status indicators (Idle, Processing, Stopped, Offline).
* **Copies & Collation**: 1–999 copies with optional collation switch.
* **Color Mode**: Full Color vs. Grayscale / Black & White.
* **Paper Sizes**: Standard sizes (A4, Letter, Legal, A3, A5, B5, Tabloid, etc.) plus custom dimension support.
* **Orientation**: Portrait, Landscape, and Auto-detect.
* **Scaling & Fit**:
  * Fit to Page (preserving aspect ratio)
  * Fill Page (crop excess)
  * Actual Size (1:1 scaling)
  * Custom Percentage scaling (1% – 500%)
* **Margins**: Default, Minimum (borderless/hardware limit), or Custom margins (mm) for Top, Bottom, Left, Right.
* **Positioning**: 9-point grid alignment (Top-Left, Center, Bottom-Right, etc.) with custom offsets.
* **Pages per Sheet (N-Up)**: 1, 2, 4, 6, 9, or 16 pages per sheet.
* **Duplex Printing**: Off (one-sided), Long-edge duplex, or Short-edge duplex.
* **Print Quality**: Draft, Normal, High quality modes.
* **Media & Paper Type**: Plain, Photo, Glossy, Matte, Cardstock, Transparency, Envelopes.
* **Image Controls**: Specific image rotation (0°, 90°, 180°, 270°) and crop modes.
* **PDF Controls**: Page ranges (e.g. `1-3, 5, 8-10`, `All`, `Current`).

### 🛠️ Printer Settings & Maintenance
Open with the gear button next to the printer, or **Menu → Printer Settings**.
* **Status**: what the printer reports (paper out, jam, toner low, paused, offline…) in plain words, supply levels, driver and connection details.
* **Repair**: a one-click check of the print service, connection, queue and driver, with fixes beside each finding — resume a paused printer, clear stuck jobs, reconnect, restart the print service, and choose what happens when a job fails.
* **Maintenance**: test page, color calibration chart, alignment page, streak & banding check and cleaning sheets, plus the driver's own commands (head cleaning, self-test, detect installed options) where the driver has them.
* **Defaults**: the driver options every app starts from (paper size, tray, two-sided, installed units) and the default printer.

Changes that need administrator rights go through the system's password prompt (polkit).

### 🪪 User ID on the Printer
* Jobs are labelled with a **User ID** (this computer's name unless you set one in **Preferences → Printing**), shown on the printer's display and in its job log.
* For PostScript printers that read PJL job commands (Ricoh, HP and similar) behind a generic driver, PrintForge adds the User ID to the job itself; such drivers otherwise send none.

### 📥 Paper Trays
* Tray choices come from the printer's driver, so the tray you pick is the tray that feeds.
* **Automatic** tells the printer to pick the tray holding the selected paper size, even when the queue's own default is manual feed.

### 💾 Presets & Persistence
* Save frequently used configurations as named presets (e.g., *"Draft Fast"*, *"Photo 4x6 Borderless"*, *"Two-Sided Report"*).
* Recall or delete presets instantly from the UI.
* Remembers window geometry, last selected printer, and last used settings across sessions.

### 🖥️ CUPS & CLI Integration
* Native CUPS integration via `pycups` with automatic fallback to a mock backend for offline testing.
* Built-in **Print Queue Dialog** to inspect active jobs and cancel jobs.
* **Headless CLI Print Mode**: Print directly from scripts and terminal without launching the GUI.

---

## System Requirements & Fedora Packages

PrintForge uses native GNOME/Fedora system libraries for speed and consistency:

```bash
sudo dnf install -y \
    python3 \
    python3-gobject \
    gtk4 \
    libadwaita \
    python3-cups \
    python3-pillow \
    python3-cairo \
    poppler-glib \
    librsvg2 \
    cups
```

Ensure the CUPS daemon is running:
```bash
sudo systemctl enable --now cups
```

---

## Installation & Running

### Running directly
From the project directory:

```bash
# Launch GUI
python3 -m printforge

# Open specific files directly into the print queue
python3 -m printforge document.pdf photo.jpg

# Launch in mock backend mode (for UI testing without CUPS)
python3 -m printforge --mock

# Enable debug logging
python3 -m printforge --debug
```

### Command-Line (CLI) Printing Mode
Print files directly from terminal without a GUI:

```bash
# Print a PDF in grayscale duplex
python3 -m printforge --no-gui --printer "SP-C352DN" --paper A4 --grayscale --duplex long-edge document.pdf

# Print 3 copies of an image in high quality
python3 -m printforge --no-gui --printer "SP-C352DN" --copies 3 --quality high photo.png
```

---

## Keyboard Shortcuts

| Shortcut | Action |
|:---|:---|
| <kbd>Ctrl</kbd> + <kbd>O</kbd> | Add files to print queue |
| <kbd>Ctrl</kbd> + <kbd>P</kbd> | Print selected document |
| <kbd>Ctrl</kbd> + <kbd>Shift</kbd> + <kbd>P</kbd> | Open CUPS Print Queue manager |
| <kbd>Ctrl</kbd> + <kbd>,</kbd> | About PrintForge |
| <kbd>Ctrl</kbd> + <kbd>Q</kbd> | Quit application |
| <kbd>+</kbd> / <kbd>-</kbd> | Zoom In / Out in preview |
| <kbd>Esc</kbd> | Close dialogs |

---

## Architecture & Codebase Overview

```
PrinterZ/
├── data/
│   ├── icons/
│   │   └── hicolor/
│   │       ├── scalable/apps/io.github.printforge.svg
│   │       ├── symbolic/apps/io.github.printforge-symbolic.svg
│   │       └── 128x128/, 64x64/, 48x48/
│   ├── io.github.printforge.desktop
│   └── io.github.printforge.metainfo.xml
├── printforge/
│   ├── application.py         # Adw.Application subclass & lifecycle
│   ├── __main__.py            # CLI parser & GUI launcher
│   ├── config/
│   │   ├── print_settings.py  # PrintSettings dataclass & CUPS options mapper
│   │   ├── presets.py         # PresetManager (JSON persistence)
│   │   └── settings.py        # AppSettings (window state & preferences)
│   ├── documents/
│   │   ├── base.py            # Document ABC & DocumentFactory
│   │   ├── image_doc.py       # Pillow raster handler (PNG, JPEG, WebP, TIFF)
│   │   ├── pdf_doc.py         # Poppler-GLib PDF handler
│   │   ├── svg_doc.py         # librsvg vector handler
│   │   ├── text_doc.py        # Paginated plain text handler
│   │   ├── renderer.py        # Core LayoutRenderer (Cairo layout engine)
│   │   └── print_prep.py      # Print file converter (PDF builder for CUPS)
│   ├── printing/
│   │   ├── cups_backend.py    # CUPS connection & IPP querying via pycups
│   │   ├── capabilities.py    # Printer capabilities parser
│   │   ├── printer.py         # PrinterInfo, PrinterState & PrinterStatus models
│   │   ├── ppd.py             # Driver (PPD) options: trays, defaults
│   │   ├── pjl.py             # User ID job header for PJL printers
│   │   ├── maintenance.py     # Status explanations, diagnostics, service pages
│   │   ├── job.py             # PrintJobManager & job lifecycle
│   │   └── mock_backend.py    # Mock printing backend for testing
│   ├── ui/
│   │   ├── main_window.py     # Main application window & action wiring
│   │   ├── file_list.py       # Drag-and-drop file list widget
│   │   ├── settings_panel.py  # Comprehensive print settings sidebar
│   │   ├── preview.py         # Interactive Cairo print preview widget
│   │   ├── dialogs.py         # Progress, Result, Queue, and About dialogs
│   │   ├── printer_settings.py # Printer status, repair, maintenance & defaults
│   │   └── styles.css         # Adwaita-compliant custom styling
│   └── utils/
│       ├── paper.py           # Standard & custom paper sizes
│       ├── units.py           # mm ↔ pt ↔ in ↔ px conversions
│       └── formatting.py      # Page range parsing & size formatters
├── tests/                     # Comprehensive test suite (320+ tests)
├── printforge.spec            # Fedora RPM packaging spec
├── pyproject.toml             # Python package configuration
└── LICENSE                    # GNU GPL v3.0
```

---

## Running Tests

Run the test suite using `pytest`:

```bash
python3 -m pytest tests/ -v
```

The unit tests cover:
- Paper sizes and CUPS media mapping
- Unit conversions (mm, points, inches, pixels at DPI)
- Page range parsing and validation
- Printer capability detection and mock backends
- Document loading and Cairo rendering (Images, SVG, PDF, Text)
- PrintSettings serialization and CUPS options mapping
- Preset creation, editing, deletion, and file persistence
- PrintPreparer PDF conversion for CUPS
- Page, side and sheet counting against the files actually sent
- Driver tray selection, User ID job headers, diagnostics and service pages

---

## Building Fedora RPM

To build an RPM package for Fedora:

```bash
# Prepare source tarball
tar --exclude-vcs -czf ~/rpmbuild/SOURCES/printforge-1.0.0.tar.gz .

# Build RPM
rpmbuild -ba printforge.spec
```

---

## License

PrintForge is licensed under the **GNU General Public License v3.0** (`GPL-3.0-or-later`). See [LICENSE](LICENSE) for details.
