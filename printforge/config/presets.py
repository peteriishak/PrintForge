"""Preset management — save, load, export, and import named print configurations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from printforge.config.print_settings import PrintSettings
from printforge.config.settings import _config_dir


# Built-in presets available out-of-the-box
BUILTIN_PRESETS: dict[str, dict] = {
    "A4 Document": {
        "paper_size_name": "A4",
        "color_mode": "color",
        "orientation": "portrait",
        "scaling_mode": "fit_to_page",
        "quality": "4",
        "copies": 1,
    },
    "A4 B&W": {
        "paper_size_name": "A4",
        "color_mode": "monochrome",
        "orientation": "portrait",
        "scaling_mode": "fit_to_page",
        "quality": "4",
        "copies": 1,
    },
    "A4 Duplex": {
        "paper_size_name": "A4",
        "color_mode": "color",
        "orientation": "portrait",
        "duplex": "two-sided-long-edge",
        "scaling_mode": "fit_to_page",
        "quality": "4",
        "copies": 1,
    },
    "Photo 4×6": {
        "paper_size_name": "4x6",
        "color_mode": "color",
        "orientation": "portrait",
        "scaling_mode": "fill_page",
        "quality": "5",
        "copies": 1,
    },
    "High Quality": {
        "paper_size_name": "A4",
        "color_mode": "color",
        "quality": "5",
        "copies": 1,
    },
    "Draft": {
        "paper_size_name": "A4",
        "color_mode": "monochrome",
        "quality": "3",
        "copies": 1,
    },
    "Booklet": {
        "paper_size_name": "A4",
        "booklet_mode": "left",
        "orientation": "landscape",
        "pages_per_sheet": 2,
        "copies": 1,
    },
}


class PresetManager:
    """Manages named print configuration presets.

    Presets are stored in ~/.config/printforge/presets.json.
    Each preset stores print settings (excluding temporary state like file list).
    """

    # Fields that should NOT be saved in presets (they're per-session)
    _EXCLUDED_FIELDS = {
        "page_range_str", "page_range_mode", "current_page",
    }

    def __init__(self) -> None:
        self._path = _config_dir() / "presets.json"
        self._presets: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._presets = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._presets = {}

    def _save(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._presets, f, indent=2, ensure_ascii=False)
            tmp.replace(self._path)
        except OSError:
            pass

    # ── Public API ────────────────────────────────────────────────────

    @property
    def names(self) -> list[str]:
        """Return sorted list of user-created preset names."""
        return sorted(self._presets.keys())

    @property
    def builtin_names(self) -> list[str]:
        """Return sorted list of built-in preset names."""
        return list(BUILTIN_PRESETS.keys())

    @property
    def all_names(self) -> list[str]:
        """Return list of all preset names (built-ins first, then user presets)."""
        builtins = [name for name in BUILTIN_PRESETS if name not in self._presets]
        return builtins + sorted(self._presets.keys())

    def is_builtin(self, name: str) -> bool:
        """Return True if this is a built-in (read-only) preset."""
        return name in BUILTIN_PRESETS and name not in self._presets

    def get(self, name: str) -> Optional[PrintSettings]:
        """Load a preset by name, returning PrintSettings or None."""
        if name in self._presets:
            return PrintSettings.from_dict(self._presets[name])
        if name in BUILTIN_PRESETS:
            return PrintSettings.from_dict(BUILTIN_PRESETS[name])
        return None

    def save_preset(self, name: str, settings: PrintSettings) -> None:
        """Save settings as a named preset."""
        d = settings.to_dict()
        # Remove per-session fields
        for key in self._EXCLUDED_FIELDS:
            d.pop(key, None)
        self._presets[name] = d
        self._save()

    def rename(self, old_name: str, new_name: str) -> bool:
        """Rename a preset. Returns True on success."""
        if old_name not in self._presets or new_name in self._presets:
            return False
        self._presets[new_name] = self._presets.pop(old_name)
        self._save()
        return True

    def delete(self, name: str) -> bool:
        """Delete a user preset by name. Returns True if it existed."""
        if name in self._presets:
            del self._presets[name]
            self._save()
            return True
        return False

    def exists(self, name: str) -> bool:
        return name in self._presets or name in BUILTIN_PRESETS

    def export_preset(self, name: str, filepath: Path | str) -> bool:
        """Export a preset to a JSON file."""
        settings = self.get(name)
        if not settings:
            return False
        try:
            d = settings.to_dict()
            for key in self._EXCLUDED_FIELDS:
                d.pop(key, None)
            export_data = {
                "name": name,
                "version": "1.0",
                "settings": d,
            }
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2)
            return True
        except OSError:
            return False

    def import_preset(self, filepath: Path | str) -> Optional[str]:
        """Import a preset from a JSON file. Returns the imported preset name."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            name = data.get("name", "Imported Preset")
            raw_settings = data.get("settings", data)
            settings = PrintSettings.from_dict(raw_settings)
            # Find unique name if exists
            base_name = name
            counter = 1
            while self.exists(name):
                name = f"{base_name} ({counter})"
                counter += 1
            self.save_preset(name, settings)
            return name
        except (json.JSONDecodeError, OSError, KeyError):
            return None
