"""Application settings persistence — stores user preferences to disk."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from printforge.config.print_settings import PrintSettings


def _config_dir() -> Path:
    """Return the XDG-compliant config directory."""
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    if xdg:
        base = Path(xdg)
    else:
        base = Path.home() / ".config"
    d = base / "printforge"
    d.mkdir(parents=True, exist_ok=True)
    return d


class AppSettings:
    """Manages persistent application settings.

    Settings are stored as JSON at ~/.config/printforge/settings.json.
    Thread-safe via atomic file writes.
    """

    _instance: Optional[AppSettings] = None

    def __init__(self) -> None:
        self._path = _config_dir() / "settings.json"
        self._data: dict[str, Any] = {}
        self._load()

    @classmethod
    def get(cls) -> AppSettings:
        """Return the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Core persistence ──────────────────────────────────────────────

    def _load(self) -> None:
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._data = {}
        else:
            self._data = {}

    def save(self) -> None:
        """Write settings to disk atomically."""
        tmp_path = self._path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            tmp_path.replace(self._path)
        except OSError:
            pass  # Non-critical — settings won't persist this time

    # ── Getters/Setters ───────────────────────────────────────────────

    def get_value(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set_value(self, key: str, value: Any) -> None:
        self._data[key] = value
        self.save()

    # ── Convenience Properties ────────────────────────────────────────

    @property
    def last_printer(self) -> str:
        return self.get_value("last_printer", "")

    @last_printer.setter
    def last_printer(self, name: str) -> None:
        self.set_value("last_printer", name)

    @property
    def last_settings(self) -> Optional[PrintSettings]:
        d = self.get_value("last_settings")
        if d and isinstance(d, dict):
            return PrintSettings.from_dict(d)
        return None

    @last_settings.setter
    def last_settings(self, settings: PrintSettings) -> None:
        self.set_value("last_settings", settings.to_dict())

    @property
    def window_width(self) -> int:
        return self.get_value("window_width", 1200)

    @window_width.setter
    def window_width(self, w: int) -> None:
        self.set_value("window_width", w)

    @property
    def window_height(self) -> int:
        return self.get_value("window_height", 800)

    @window_height.setter
    def window_height(self, h: int) -> None:
        self.set_value("window_height", h)

    @property
    def window_maximized(self) -> bool:
        return self.get_value("window_maximized", False)

    @window_maximized.setter
    def window_maximized(self, val: bool) -> None:
        self.set_value("window_maximized", val)

    @property
    def dark_mode(self) -> Optional[bool]:
        """None = follow system, True = dark, False = light."""
        return self.get_value("dark_mode", None)

    @dark_mode.setter
    def dark_mode(self, val: Optional[bool]) -> None:
        self.set_value("dark_mode", val)

    @property
    def appearance_mode(self) -> str:
        """'system', 'light', or 'dark'."""
        return self.get_value("appearance_mode", "system")

    @appearance_mode.setter
    def appearance_mode(self, mode: str) -> None:
        self.set_value("appearance_mode", mode)

    @property
    def simple_mode(self) -> bool:
        return self.get_value("simple_mode", False)

    @simple_mode.setter
    def simple_mode(self, val: bool) -> None:
        self.set_value("simple_mode", val)

    # ── Preferences ───────────────────────────────────────────────────

    @property
    def default_printer(self) -> str:
        return self.get_value("default_printer", "")

    @default_printer.setter
    def default_printer(self, name: str) -> None:
        self.set_value("default_printer", name)

    @property
    def default_paper(self) -> str:
        return self.get_value("default_paper", "A4")

    @default_paper.setter
    def default_paper(self, paper: str) -> None:
        self.set_value("default_paper", paper)

    @property
    def default_color_mode(self) -> str:
        return self.get_value("default_color_mode", "color")

    @default_color_mode.setter
    def default_color_mode(self, mode: str) -> None:
        self.set_value("default_color_mode", mode)

    @property
    def default_copies(self) -> int:
        return self.get_value("default_copies", 1)

    @default_copies.setter
    def default_copies(self, n: int) -> None:
        self.set_value("default_copies", max(1, n))

    @property
    def preview_default_zoom(self) -> float:
        return self.get_value("preview_default_zoom", 1.0)

    @preview_default_zoom.setter
    def preview_default_zoom(self, z: float) -> None:
        self.set_value("preview_default_zoom", z)

    @property
    def show_margins(self) -> bool:
        return self.get_value("show_margins", True)

    @show_margins.setter
    def show_margins(self, val: bool) -> None:
        self.set_value("show_margins", val)

    @property
    def show_printable_area(self) -> bool:
        return self.get_value("show_printable_area", True)

    @show_printable_area.setter
    def show_printable_area(self, val: bool) -> None:
        self.set_value("show_printable_area", val)

    @property
    def show_rulers(self) -> bool:
        return self.get_value("show_rulers", False)

    @show_rulers.setter
    def show_rulers(self, val: bool) -> None:
        self.set_value("show_rulers", val)

    @property
    def confirm_before_printing(self) -> bool:
        return self.get_value("confirm_before_printing", False)

    @confirm_before_printing.setter
    def confirm_before_printing(self, val: bool) -> None:
        self.set_value("confirm_before_printing", val)

    @property
    def save_history(self) -> bool:
        return self.get_value("save_history", True)

    @save_history.setter
    def save_history(self, val: bool) -> None:
        self.set_value("save_history", val)

    @property
    def auto_refresh_printers(self) -> bool:
        return self.get_value("auto_refresh_printers", True)

    @auto_refresh_printers.setter
    def auto_refresh_printers(self, val: bool) -> None:
        self.set_value("auto_refresh_printers", val)

    @property
    def use_mock_backend(self) -> bool:
        return self.get_value("use_mock_backend", False)

    @use_mock_backend.setter
    def use_mock_backend(self, val: bool) -> None:
        self.set_value("use_mock_backend", val)

    @property
    def user_id(self) -> str:
        """User ID shown on the printer for jobs from this computer. '' means the device name."""
        return self.get_value("user_id", "")

    @user_id.setter
    def user_id(self, value: str) -> None:
        self.set_value("user_id", value.strip())

    @property
    def send_user_id(self) -> bool:
        """Whether jobs carry the User ID to printers that can show it."""
        return self.get_value("send_user_id", True)

    @send_user_id.setter
    def send_user_id(self, val: bool) -> None:
        self.set_value("send_user_id", val)
