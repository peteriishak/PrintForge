"""PrintForge GTK4/Libadwaita Application class."""

from __future__ import annotations

import logging
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Gdk, Gio, Adw

from printforge import __app_id__

log = logging.getLogger(__name__)


class PrintForgeApp(Adw.Application):
    """Main PrintForge application.

    Manages the application lifecycle, CSS loading, and window creation.
    """

    def __init__(self, use_mock: bool = False, files: list[str] | None = None) -> None:
        super().__init__(
            application_id=__app_id__,
            flags=Gio.ApplicationFlags.HANDLES_OPEN,
        )
        self._use_mock = use_mock
        self._initial_files = files or []

    def do_startup(self) -> None:
        """Called when the application starts."""
        Adw.Application.do_startup(self)

        # Load custom CSS
        self._load_css()

        # Set up app-level actions
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda a, p: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Control>q"])

    def do_activate(self) -> None:
        """Called when the application is activated (window shown)."""
        win = self.props.active_window
        if not win:
            from printforge.ui.main_window import PrintForgeWindow
            win = PrintForgeWindow(
                application=self,
                use_mock=self._use_mock,
            )

        # Load any files passed on command line
        if self._initial_files:
            win.add_files(self._initial_files)
            self._initial_files = []

        win.present()

    def do_open(self, files, n_files, hint) -> None:
        """Handle files opened via the command line or file manager."""
        self.do_activate()
        win = self.props.active_window
        if win:
            paths = [f.get_path() for f in files if f.get_path()]
            win.add_files(paths)

    def _load_css(self) -> None:
        """Load the application's custom CSS."""
        css_provider = Gtk.CssProvider()

        # Try to load CSS from the package directory
        css_path = Path(__file__).parent / "ui" / "styles.css"
        if css_path.exists():
            css_provider.load_from_path(str(css_path))
        else:
            log.warning("CSS file not found: %s", css_path)
            return

        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display,
                css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
            log.debug("Loaded custom CSS from %s", css_path)
