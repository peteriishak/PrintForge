"""Image document handler — PNG, JPEG, WebP, BMP, TIFF."""

from __future__ import annotations

import logging
from typing import Optional

import cairo

from printforge.documents.base import Document

log = logging.getLogger(__name__)


class ImageDocument(Document):
    """Handles raster image files using Pillow + Cairo."""

    # Class-level dict to prevent buffer garbage collection while surfaces live
    _buffer_refs: dict[int, bytearray] = {}

    def __init__(self, filepath: str) -> None:
        super().__init__(filepath)
        self._width: int = 0
        self._height: int = 0
        self._dpi: tuple[float, float] = (72.0, 72.0)
        self._mode: str = ""
        self._pil_image = None

    @property
    def page_count(self) -> int:
        return 1 if self._valid else 0

    @property
    def dimensions(self) -> tuple[float, float]:
        return (float(self._width), float(self._height))

    @property
    def dpi(self) -> tuple[float, float]:
        return self._dpi

    @property
    def image_mode(self) -> str:
        return self._mode

    def load(self) -> bool:
        try:
            from PIL import Image

            img = Image.open(self._filepath)
            img.load()  # Force load to detect corrupt files
            self._width, self._height = img.size
            self._mode = img.mode

            # Extract DPI if available
            dpi_info = img.info.get("dpi")
            if dpi_info and isinstance(dpi_info, tuple) and len(dpi_info) == 2:
                if dpi_info[0] > 0 and dpi_info[1] > 0:
                    self._dpi = (float(dpi_info[0]), float(dpi_info[1]))

            self._pil_image = img
            self._valid = True
            return True

        except ImportError:
            self._error = "Pillow library is not installed"
            log.error(self._error)
            return False
        except Exception as e:
            self._error = f"Failed to load image: {e}"
            log.error("%s: %s", self._error, self._filepath)
            return False

    def render_page(
        self, page_num: int, width: float, height: float
    ) -> Optional[cairo.ImageSurface]:
        if not self._valid or self._pil_image is None:
            return None

        try:
            from PIL import Image

            # Convert to RGBA for Cairo compatibility
            img = self._pil_image.copy()
            if img.mode != "RGBA":
                img = img.convert("RGBA")

            # Resize to target dimensions
            target_w = max(1, int(width))
            target_h = max(1, int(height))
            img = img.resize((target_w, target_h), Image.LANCZOS)

            # Convert to Cairo format (BGRA premultiplied)
            # PIL RGBA is R,G,B,A; Cairo ARGB32 is B,G,R,A in native byte order
            raw_data = img.tobytes("raw", "BGRa")

            # The buffer must stay alive as long as the surface exists
            buf = bytearray(raw_data)

            surface = cairo.ImageSurface.create_for_data(
                buf,
                cairo.FORMAT_ARGB32,
                target_w,
                target_h,
                target_w * 4,
            )

            # Store buffer reference at class level to prevent GC
            ImageDocument._buffer_refs[id(surface)] = buf

            return surface

        except Exception as e:
            log.error("Failed to render image: %s", e)
            return None

    def get_rotated_dimensions(self, rotation: int) -> tuple[float, float]:
        """Return dimensions after rotation (0, 90, 180, 270 degrees)."""
        if rotation in (90, 270):
            return (float(self._height), float(self._width))
        return (float(self._width), float(self._height))

    def close(self) -> None:
        """Release the PIL image resources."""
        if self._pil_image:
            try:
                self._pil_image.close()
            except Exception:
                pass
            self._pil_image = None
