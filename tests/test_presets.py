"""Tests for preset management."""

import json
import os
import pytest

from printforge.config.presets import PresetManager
from printforge.config.print_settings import PrintSettings, ColorMode, Orientation


@pytest.fixture
def preset_manager(tmp_dir, monkeypatch):
    """Create a PresetManager using a temp directory."""
    monkeypatch.setattr(
        "printforge.config.presets._config_dir",
        lambda: type("Path", (), {"__truediv__": lambda self, x: os.path.join(tmp_dir, x),
                                   "exists": lambda self: os.path.exists(str(self)),
                                   "with_suffix": lambda self, s: str(self) + s,
                                   "replace": lambda self, target: os.replace(str(self), str(target)),
                                   "mkdir": lambda self, **kw: None})()
    )
    # Actually use a simpler approach: override the path directly
    pm = PresetManager.__new__(PresetManager)
    pm._path = type("P", (), {
        "exists": lambda self: os.path.exists(os.path.join(tmp_dir, "presets.json")),
        "with_suffix": lambda self, s: os.path.join(tmp_dir, f"presets{s}"),
        "__str__": lambda self: os.path.join(tmp_dir, "presets.json"),
    })()

    # Patch open calls to use string path
    import pathlib
    pm._path = pathlib.Path(tmp_dir) / "presets.json"
    pm._presets = {}
    return pm


class TestPresetManager:
    def test_empty_names(self, preset_manager):
        assert preset_manager.names == []

    def test_save_and_get(self, preset_manager):
        settings = PrintSettings(
            printer_name="TestPrinter",
            copies=2,
            color_mode=ColorMode.GRAYSCALE,
        )
        preset_manager.save_preset("Test Preset", settings)
        assert "Test Preset" in preset_manager.names

        loaded = preset_manager.get("Test Preset")
        assert loaded is not None
        assert loaded.copies == 2
        assert loaded.color_mode == ColorMode.GRAYSCALE

    def test_delete(self, preset_manager):
        settings = PrintSettings()
        preset_manager.save_preset("ToDelete", settings)
        assert preset_manager.exists("ToDelete")

        assert preset_manager.delete("ToDelete") is True
        assert not preset_manager.exists("ToDelete")

    def test_delete_nonexistent(self, preset_manager):
        assert preset_manager.delete("NoSuch") is False

    def test_rename(self, preset_manager):
        settings = PrintSettings()
        preset_manager.save_preset("OldName", settings)

        assert preset_manager.rename("OldName", "NewName") is True
        assert not preset_manager.exists("OldName")
        assert preset_manager.exists("NewName")

    def test_rename_conflict(self, preset_manager):
        preset_manager.save_preset("A", PrintSettings())
        preset_manager.save_preset("B", PrintSettings())

        assert preset_manager.rename("A", "B") is False

    def test_get_nonexistent(self, preset_manager):
        assert preset_manager.get("NoSuch") is None

    def test_excluded_fields(self, preset_manager):
        """Verify that per-session fields are not saved in presets."""
        settings = PrintSettings(page_range_str="1-5")
        preset_manager.save_preset("Test", settings)

        # Read the raw data
        loaded = preset_manager.get("Test")
        # page_range_str should not be preserved
        assert loaded.page_range_str == ""  # default
