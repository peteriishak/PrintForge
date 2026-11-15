"""Tests for booklet imposition logic."""

import pytest
from printforge.config.print_settings import BookletMode
from printforge.documents.booklet import BookletImposer, BookletFace


class TestBookletImposer:
    def test_empty_or_off(self):
        assert BookletImposer.calculate_imposition(0, BookletMode.LEFT_BINDING) == []
        assert BookletImposer.calculate_imposition(4, BookletMode.OFF) == []

    def test_four_page_left_binding(self):
        # 4 pages: exactly 1 sheet (2 faces)
        # Sheet 0 Front: Left = Page 4 (idx 3), Right = Page 1 (idx 0)
        # Sheet 0 Back:  Left = Page 2 (idx 1), Right = Page 3 (idx 2)
        faces = BookletImposer.calculate_imposition(4, BookletMode.LEFT_BINDING)
        assert len(faces) == 2

        front = faces[0]
        assert front.sheet_index == 0
        assert not front.is_back
        assert front.left_page == 3   # Page 4
        assert front.right_page == 0  # Page 1

        back = faces[1]
        assert back.sheet_index == 0
        assert back.is_back
        assert back.left_page == 1   # Page 2
        assert back.right_page == 2  # Page 3

    def test_four_page_right_binding(self):
        # 4 pages Right Binding (Manga / RTL):
        # Front: Left = Page 1 (idx 0), Right = Page 4 (idx 3)
        # Back:  Left = Page 3 (idx 2), Right = Page 2 (idx 1)
        faces = BookletImposer.calculate_imposition(4, BookletMode.RIGHT_BINDING)
        assert len(faces) == 2

        front = faces[0]
        assert front.left_page == 0
        assert front.right_page == 3

        back = faces[1]
        assert back.left_page == 2
        assert back.right_page == 1

    def test_odd_page_padding(self):
        # 3 pages: padded to 4 pages, so page 4 is None (blank)
        faces = BookletImposer.calculate_imposition(3, BookletMode.LEFT_BINDING)
        assert len(faces) == 2
        assert faces[0].left_page is None  # Blank page 4
        assert faces[0].right_page == 0   # Page 1
        assert faces[1].left_page == 1    # Page 2
        assert faces[1].right_page == 2   # Page 3

    def test_eight_pages(self):
        # 8 pages: 2 sheets (4 faces)
        faces = BookletImposer.calculate_imposition(8, BookletMode.LEFT_BINDING)
        assert len(faces) == 4

        # Sheet 0 (Outer sheet): Front [8, 1], Back [2, 7]
        assert faces[0].left_page == 7 and faces[0].right_page == 0
        assert faces[1].left_page == 1 and faces[1].right_page == 6

        # Sheet 1 (Inner sheet): Front [6, 3], Back [4, 5]
        assert faces[2].left_page == 5 and faces[2].right_page == 2
        assert faces[3].left_page == 3 and faces[3].right_page == 4

    def test_estimate_sheets(self):
        assert BookletImposer.estimate_sheets(4, BookletMode.LEFT_BINDING) == 1
        assert BookletImposer.estimate_sheets(5, BookletMode.LEFT_BINDING) == 2
        assert BookletImposer.estimate_sheets(8, BookletMode.LEFT_BINDING) == 2
        assert BookletImposer.estimate_sheets(9, BookletMode.LEFT_BINDING) == 3
        assert BookletImposer.estimate_sheets(8, BookletMode.OFF) == 8
