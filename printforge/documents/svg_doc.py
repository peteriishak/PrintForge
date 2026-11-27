"""SVG document handler using librsvg (gi.repository.Rsvg)."""

from __future__ import annotations

import logging
from typing import Optional

import cairo

from printforge.documents.base import Document

log = logging.getLogger(__name__)


class SvgDocument(Document):
    """Handles SVG files using librsvg."""

    def __init__(self, filepath: str) -> None:
        super().__init__(filepath)
        self._handle = None
        self._width: float = 0.0
        self._height: float = 0.0

    @property
    def page_count(self) -> int:
        return 1 if self._valid else 0

    @property
    def dimensions(self) -> tuple[float, float]:
        return (self._width, self._height)

    def load(self) -> bool:
        try:
            import gi
            gi.require_version("Rsvg", "2.0")
            from gi.repository import Rsvg

            self._handle = Rsvg.Handle.new_from_file(self._filepath)

            # Intrinsic size: librsvg >= 2.52 returns (has_size, width, height)
            sized = False
            try:
                has_size, w, h = self._handle.get_intrinsic_size_in_pixels()
                if has_size and w > 0 and h > 0:
                    self._width, self._height = float(w), float(h)
                    sized = True
            except (TypeError, ValueError, AttributeError):
                pass

            # Fallback: the deprecated but widely available get_dimensions
            if not sized:
                try:
                    dim = self._handle.get_dimensions()
                    self._width = float(dim.width) if dim.width > 0 else 100.0
                    self._height = float(dim.height) if dim.height > 0 else 100.0
                except AttributeError:
                    self._width = 100.0
                    self._height = 100.0

            self._valid = True
            return True

        except ImportError:
            self._error = "librsvg GI bindings not available. Install librsvg2."
            log.error(self._error)
            return False
        except Exception as e:
            self._error = f"Failed to load SVG: {e}"
            log.error("%s: %s", self._error, self._filepath)
            return False

    def render_page(
        self, page_num: int, width: float, height: float
    ) -> Optional[cairo.ImageSurface]:
        if not self._valid or self._handle is None:
            return None

        try:
            target_w = max(1, int(width))
            target_h = max(1, int(height))

            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, target_w, target_h)
            ctx = cairo.Context(surface)

            # White background
            ctx.set_source_rgb(1.0, 1.0, 1.0)
            ctx.rectangle(0, 0, target_w, target_h)
            ctx.fill()

            # Scale SVG to fit
            if self._width > 0 and self._height > 0:
                scale_x = target_w / self._width
                scale_y = target_h / self._height
                scale = min(scale_x, scale_y)

                offset_x = (target_w - self._width * scale) / 2
                offset_y = (target_h - self._height * scale) / 2

                ctx.translate(offset_x, offset_y)
                ctx.scale(scale, scale)

            # Render SVG
            try:
                # Try newer API: render_document
                from gi.repository import Rsvg
                viewport = Rsvg.Rectangle()
                viewport.x = 0
                viewport.y = 0
                viewport.width = self._width
                viewport.height = self._height
                self._handle.render_document(ctx, viewport)
            except (TypeError, AttributeError):
                # Fallback to deprecated render_cairo
                self._handle.render_cairo(ctx)

            return surface

        except Exception as e:
            log.error("Failed to render SVG: %s", e)
            return None

    def close(self) -> None:
        self._handle = None
