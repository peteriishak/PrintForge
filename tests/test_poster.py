"""Tests for poster tiling logic."""

import pytest
from printforge.documents.poster import PosterTiler, PosterTile


class TestPosterTiler:
    def test_single_tile(self):
        tiles = PosterTiler.calculate_tiles(100, 100, cols=1, rows=1, overlap_pt=0)
        assert len(tiles) == 1
        assert tiles[0].src_rect.x == 0
        assert tiles[0].src_rect.y == 0
        assert tiles[0].src_rect.width == 100
        assert tiles[0].src_rect.height == 100

    def test_2x2_tiles(self):
        tiles = PosterTiler.calculate_tiles(200, 200, cols=2, rows=2, overlap_pt=10)
        assert len(tiles) == 4
        assert tiles[0].col == 0 and tiles[0].row == 0
        assert tiles[1].col == 1 and tiles[1].row == 0
        assert tiles[2].col == 0 and tiles[2].row == 1
        assert tiles[3].col == 1 and tiles[3].row == 1

        for t in tiles:
            assert t.total_tiles == 4
            assert t.src_rect.width > 0
            assert t.src_rect.height > 0

    def test_custom_dimensions(self):
        tiles = PosterTiler.calculate_tiles(300, 400, cols=3, rows=4, overlap_pt=5)
        assert len(tiles) == 12
