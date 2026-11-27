"""Text, Code, and Markdown document handler — renders paginated documents with styling."""

from __future__ import annotations

import logging
import os
from typing import Optional

import cairo

from printforge.documents.base import Document

log = logging.getLogger(__name__)

# Default layout parameters (in points)
DEFAULT_FONT_FAMILY = "Monospace"
DEFAULT_FONT_SIZE = 9.5
DEFAULT_LINE_SPACING = 1.35
DEFAULT_MARGIN_PT = 36.0  # 0.5 inch

# Pygments syntax highlighting colors (RGB float tuples)
SYNTAX_COLORS: dict[str, tuple[float, float, float]] = {
    "keyword": (0.0, 0.2, 0.7),       # Deep blue
    "string": (0.65, 0.1, 0.1),       # Burgundy red
    "comment": (0.45, 0.45, 0.45),    # Muted gray
    "number": (0.1, 0.5, 0.1),        # Forest green
    "function": (0.0, 0.4, 0.6),      # Teal
    "operator": (0.3, 0.3, 0.3),      # Charcoal
    "default": (0.1, 0.1, 0.1),       # Near black
    "gutter": (0.55, 0.55, 0.55),     # Line number gray
    "header": (0.4, 0.4, 0.4),        # Header/footer gray
}


class FormattedLine:
    """A single renderable line with tokens or markdown styles."""
    def __init__(
        self,
        text: str,
        line_num: Optional[int] = None,
        is_heading: bool = False,
        heading_level: int = 0,
        is_code_block: bool = False,
        is_bullet: bool = False,
        is_quote: bool = False,
        tokens: Optional[list[tuple[tuple[float, float, float], str]]] = None,
    ) -> None:
        self.text = text
        self.line_num = line_num
        self.is_heading = is_heading
        self.heading_level = heading_level
        self.is_code_block = is_code_block
        self.is_bullet = is_bullet
        self.is_quote = is_quote
        self.tokens = tokens or []


class TextDocument(Document):
    """Handles Plain Text, Markdown, and Source Code files with pagination and styling."""

    def __init__(self, filepath: str) -> None:
        super().__init__(filepath)
        self._raw_text: str = ""
        self._source_lines: list[str] = []
        self._formatted_lines: list[FormattedLine] = []
        self._pages: list[list[FormattedLine]] = []
        self._chars_count: int = 0

        # Layout parameters (in points)
        self.font_family = DEFAULT_FONT_FAMILY
        self.font_size = DEFAULT_FONT_SIZE
        self.line_spacing = DEFAULT_LINE_SPACING
        self.page_width_pt = 595.0  # A4
        self.page_height_pt = 842.0
        self.margin_pt = DEFAULT_MARGIN_PT
        self.show_line_numbers = False

        # Detect format
        ext = os.path.splitext(self._filepath)[1].lower()
        self._is_markdown = ext in (".md", ".markdown")
        self._is_code = ext in (
            ".py", ".sh", ".bash", ".zsh", ".c", ".h", ".cpp", ".hpp",
            ".cc", ".rs", ".go", ".js", ".ts", ".jsx", ".tsx", ".html",
            ".css", ".json", ".yaml", ".yml", ".toml", ".xml", ".sql",
            ".ini", ".conf", ".cfg", ".diff", ".patch",
        )
        if self._is_code:
            self.show_line_numbers = True

    @property
    def page_count(self) -> int:
        return max(1, len(self._pages)) if self._valid else 0

    @property
    def dimensions(self) -> tuple[float, float]:
        return (self.page_width_pt, self.page_height_pt)

    @property
    def char_count(self) -> int:
        return self._chars_count

    @property
    def line_count(self) -> int:
        return len(self._source_lines)

    def load(self) -> bool:
        try:
            with open(self._filepath, "r", encoding="utf-8", errors="replace") as f:
                self._raw_text = f.read()

            self._source_lines = self._raw_text.splitlines()
            self._chars_count = len(self._raw_text)

            self._process_and_paginate()
            self._valid = True
            return True

        except Exception as e:
            self._error = f"Failed to load text file: {e}"
            log.error("%s: %s", self._error, self._filepath)
            return False

    def set_scale(self, scale_pct: float) -> None:
        """Update font size and line spacing based on scale percentage (25% to 400%)."""
        scale = max(0.25, min(4.0, scale_pct / 100.0))
        new_font_size = round(DEFAULT_FONT_SIZE * scale, 1)
        if abs(self.font_size - new_font_size) > 0.1:
            self.font_size = new_font_size
            if self._valid:
                self._process_and_paginate()

    def set_page_size(self, width_pt: float, height_pt: float) -> None:
        """Update page size and re-paginate."""
        if abs(self.page_width_pt - width_pt) < 0.01 and abs(self.page_height_pt - height_pt) < 0.01:
            return
        self.page_width_pt = width_pt
        self.page_height_pt = height_pt
        if self._valid:
            self._process_and_paginate()

    def _process_and_paginate(self) -> None:
        """Format text (with syntax highlighting or markdown parsing) and paginate."""
        self._formatted_lines = []

        if self._is_markdown:
            self._format_markdown()
        elif self._is_code:
            self._format_code()
        else:
            self._format_plain_text()

        # Split formatted lines into pages
        # Reserve 30pt top for header and 25pt bottom for footer
        usable_height = self.page_height_pt - 2 * self.margin_pt - 55.0
        line_h = self.font_size * self.line_spacing

        lines_per_page = max(1, int(usable_height / line_h))
        self._pages = []

        for i in range(0, len(self._formatted_lines), lines_per_page):
            self._pages.append(self._formatted_lines[i:i + lines_per_page])

        if not self._pages:
            self._pages = [[]]

    def _format_plain_text(self) -> None:
        """Format plain text with word-wrapping."""
        max_chars = max(20, int((self.page_width_pt - 2 * self.margin_pt) / (self.font_size * 0.58)))

        for line_idx, line in enumerate(self._source_lines):
            line_num = line_idx + 1 if self.show_line_numbers else None
            if not line:
                self._formatted_lines.append(FormattedLine("", line_num=line_num))
                continue

            # Word-wrap long lines
            wrapped = self._wrap_line(line, max_chars)
            for sub_idx, sub_line in enumerate(wrapped):
                self._formatted_lines.append(
                    FormattedLine(sub_line, line_num=line_num if sub_idx == 0 else None)
                )

    def _format_code(self) -> None:
        """Format code with Pygments syntax highlighting and line numbers."""
        try:
            import pygments
            from pygments.lexers import get_lexer_for_filename, TextLexer

            try:
                lexer = get_lexer_for_filename(self._filepath, self._raw_text)
            except Exception:
                lexer = TextLexer()

            tokens = list(pygments.lex(self._raw_text, lexer))
            gutter_width_chars = len(str(len(self._source_lines))) + 3
            max_chars = max(20, int((self.page_width_pt - 2 * self.margin_pt) / (self.font_size * 0.58)) - gutter_width_chars)

            # Map tokens to lines
            current_line_tokens: list[tuple[tuple[float, float, float], str]] = []
            line_idx = 0

            for tok_type, tok_val in tokens:
                color = self._token_to_color(tok_type)
                parts = tok_val.split("\n")

                for p_i, part in enumerate(parts):
                    if p_i > 0:
                        # End of line
                        line_text = "".join(t[1] for t in current_line_tokens)
                        self._formatted_lines.append(FormattedLine(
                            line_text,
                            line_num=line_idx + 1,
                            tokens=current_line_tokens,
                        ))
                        line_idx += 1
                        current_line_tokens = []

                    if part:
                        # Wrap long token if necessary
                        current_line_tokens.append((color, part))

            if current_line_tokens:
                line_text = "".join(t[1] for t in current_line_tokens)
                self._formatted_lines.append(FormattedLine(
                    line_text,
                    line_num=line_idx + 1,
                    tokens=current_line_tokens,
                ))

        except Exception as e:
            log.warning("Pygments highlighting failed (%s), falling back to plain text", e)
            self._format_plain_text()

    def _format_markdown(self) -> None:
        """Format Markdown text with headings, lists, quotes, and code blocks."""
        in_code_block = False
        max_chars = max(20, int((self.page_width_pt - 2 * self.margin_pt) / (self.font_size * 0.58)))

        for line in self._source_lines:
            stripped = line.strip()

            if stripped.startswith("```"):
                in_code_block = not in_code_block
                continue

            if in_code_block:
                self._formatted_lines.append(FormattedLine(line, is_code_block=True))
                continue

            # Heading 1
            if stripped.startswith("# "):
                self._formatted_lines.append(FormattedLine(stripped[2:], is_heading=True, heading_level=1))
                continue
            # Heading 2
            elif stripped.startswith("## "):
                self._formatted_lines.append(FormattedLine(stripped[3:], is_heading=True, heading_level=2))
                continue
            # Heading 3
            elif stripped.startswith("### "):
                self._formatted_lines.append(FormattedLine(stripped[4:], is_heading=True, heading_level=3))
                continue
            # Bullet list
            elif stripped.startswith(("- ", "* ", "+ ")):
                bullet_text = "• " + stripped[2:]
                for sub_line in self._wrap_line(bullet_text, max_chars):
                    self._formatted_lines.append(FormattedLine(sub_line, is_bullet=True))
                continue
            # Blockquote
            elif stripped.startswith("> "):
                quote_text = stripped[2:]
                for sub_line in self._wrap_line(quote_text, max_chars):
                    self._formatted_lines.append(FormattedLine(sub_line, is_quote=True))
                continue

            # Regular paragraph
            if not line:
                self._formatted_lines.append(FormattedLine(""))
            else:
                for sub_line in self._wrap_line(line, max_chars):
                    self._formatted_lines.append(FormattedLine(sub_line))

    def _wrap_line(self, text: str, max_chars: int) -> list[str]:
        """Wrap a string into multiple lines without breaking words when possible."""
        if len(text) <= max_chars:
            return [text]

        words = text.split(" ")
        lines = []
        cur_line: list[str] = []
        cur_len = 0

        for w in words:
            w_len = len(w)
            if cur_len + w_len + (1 if cur_line else 0) <= max_chars:
                cur_line.append(w)
                cur_len += w_len + (1 if cur_line else 0)
            else:
                if cur_line:
                    lines.append(" ".join(cur_line))
                if w_len > max_chars:
                    # Break long word across lines
                    for i in range(0, w_len, max_chars):
                        lines.append(w[i:i + max_chars])
                    cur_line = []
                    cur_len = 0
                else:
                    cur_line = [w]
                    cur_len = w_len

        if cur_line:
            lines.append(" ".join(cur_line))

        return lines or [text]

    def _token_to_color(self, token) -> tuple[float, float, float]:
        """Map Pygments token type to RGB color."""
        s = str(token)
        if "Keyword" in s:
            return SYNTAX_COLORS["keyword"]
        elif "String" in s:
            return SYNTAX_COLORS["string"]
        elif "Comment" in s:
            return SYNTAX_COLORS["comment"]
        elif "Number" in s:
            return SYNTAX_COLORS["number"]
        elif "Function" in s or "Name.Class" in s:
            return SYNTAX_COLORS["function"]
        elif "Operator" in s or "Punctuation" in s:
            return SYNTAX_COLORS["operator"]
        return SYNTAX_COLORS["default"]

    def render_page(
        self, page_num: int, width: float, height: float
    ) -> Optional[cairo.ImageSurface]:
        if not self._valid or page_num < 0 or page_num >= len(self._pages):
            return None

        try:
            target_w = max(1, int(width))
            target_h = max(1, int(height))

            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, target_w, target_h)
            ctx = cairo.Context(surface)

            # Paper background (crisp white)
            ctx.set_source_rgb(1.0, 1.0, 1.0)
            ctx.rectangle(0, 0, target_w, target_h)
            ctx.fill()

            scale_x = target_w / self.page_width_pt
            scale_y = target_h / self.page_height_pt
            scale = min(scale_x, scale_y)

            ctx.save()
            ctx.scale(scale, scale)

            # Draw Header: Filename & divider
            ctx.set_source_rgb(*SYNTAX_COLORS["header"])
            ctx.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            ctx.set_font_size(8.0)
            ctx.move_to(self.margin_pt, self.margin_pt - 10)
            ctx.show_text(self.filename)

            ctx.set_line_width(0.5)
            ctx.move_to(self.margin_pt, self.margin_pt - 4)
            ctx.line_to(self.page_width_pt - self.margin_pt, self.margin_pt - 4)
            ctx.stroke()

            # Draw Footer: Page X of Y
            footer_text = f"Page {page_num + 1} of {len(self._pages)}"
            ctx.move_to(self.page_width_pt / 2 - 25, self.page_height_pt - self.margin_pt + 16)
            ctx.show_text(footer_text)

            # Line positioning
            x_start = self.margin_pt
            y = self.margin_pt + 18.0
            line_h = self.font_size * self.line_spacing
            gutter_chars = len(str(len(self._source_lines))) + 1
            gutter_w = (gutter_chars * self.font_size * 0.6) if self.show_line_numbers else 0

            page_lines = self._pages[page_num]

            for line_obj in page_lines:
                # 1. Line Number Gutter
                if self.show_line_numbers:
                    ctx.select_font_face(DEFAULT_FONT_FAMILY, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
                    ctx.set_font_size(self.font_size * 0.9)
                    ctx.set_source_rgb(*SYNTAX_COLORS["gutter"])

                    if line_obj.line_num is not None:
                        num_str = f"{line_obj.line_num:>{gutter_chars - 1}} "
                        ctx.move_to(x_start, y)
                        ctx.show_text(num_str)

                text_x = x_start + gutter_w

                # 2. Markdown Headings
                if line_obj.is_heading:
                    ctx.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
                    size = self.font_size * (1.5 if line_obj.heading_level == 1 else 1.25)
                    ctx.set_font_size(size)
                    ctx.set_source_rgb(0.05, 0.05, 0.1)
                    ctx.move_to(text_x, y)
                    ctx.show_text(line_obj.text)

                # 3. Code Blocks
                elif line_obj.is_code_block:
                    # Draw subtle shaded background
                    ctx.set_source_rgb(0.95, 0.95, 0.96)
                    ctx.rectangle(text_x - 4, y - line_h + 3, self.page_width_pt - text_x - self.margin_pt + 4, line_h)
                    ctx.fill()

                    ctx.select_font_face(DEFAULT_FONT_FAMILY, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
                    ctx.set_font_size(self.font_size)
                    ctx.set_source_rgb(*SYNTAX_COLORS["default"])
                    ctx.move_to(text_x, y)
                    ctx.show_text(line_obj.text)

                # 4. Tokenized Syntax Highlighted Code
                elif line_obj.tokens:
                    ctx.select_font_face(DEFAULT_FONT_FAMILY, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
                    ctx.set_font_size(self.font_size)
                    cur_x = text_x
                    for col, tok_text in line_obj.tokens:
                        ctx.set_source_rgb(*col)
                        ctx.move_to(cur_x, y)
                        ctx.show_text(tok_text)
                        # Measure text advance
                        extents = ctx.text_extents(tok_text)
                        cur_x += extents.x_advance

                # 5. Regular text / bullet / quote
                else:
                    ctx.select_font_face(
                        DEFAULT_FONT_FAMILY if not self._is_markdown else "Sans",
                        cairo.FONT_SLANT_ITALIC if line_obj.is_quote else cairo.FONT_SLANT_NORMAL,
                        cairo.FONT_WEIGHT_NORMAL,
                    )
                    ctx.set_font_size(self.font_size)
                    ctx.set_source_rgb(*SYNTAX_COLORS["default"])
                    ctx.move_to(text_x, y)
                    ctx.show_text(line_obj.text)

                y += line_h

            ctx.restore()
            return surface

        except Exception as e:
            log.error("Failed to render text page %d: %s", page_num, e)
            return None
