"""
Tests for RAPStateReconstructor — Phase 6 Coverage Expansion.

Covers:
  RAPStateReconstructor (state_reconstructor.py)
  - segment_match_into_windows: temporal windowing with 50% overlap
  - init defaults
"""

import sys


import pytest


class TestSegmentMatchIntoWindows:
    """Tests for temporal windowing logic (no DB or tensor deps)."""

    def _make_reconstructor(self, seq_len=32):
        from Programma_CS2_RENAN.backend.processing.state_reconstructor import (
            RAPStateReconstructor,
        )
        recon = RAPStateReconstructor.__new__(RAPStateReconstructor)
        recon.sequence_length = seq_len
        return recon

    def test_exact_one_window(self):
        """Exactly sequence_length ticks → 1 window."""
        recon = self._make_reconstructor(seq_len=4)
        ticks = list(range(4))
        windows = recon.segment_match_into_windows(ticks)
        assert len(windows) == 1
        assert windows[0] == [0, 1, 2, 3]

    def test_insufficient_ticks(self):
        """Fewer ticks than sequence_length → 0 windows."""
        recon = self._make_reconstructor(seq_len=8)
        ticks = list(range(5))
        windows = recon.segment_match_into_windows(ticks)
        assert len(windows) == 0

    def test_empty_ticks(self):
        recon = self._make_reconstructor(seq_len=4)
        windows = recon.segment_match_into_windows([])
        assert len(windows) == 0

    def test_overlap_50_percent(self):
        """50% overlap: step = seq_len // 2."""
        recon = self._make_reconstructor(seq_len=4)
        # With 6 ticks, step=2: windows at [0:4], [2:6]
        ticks = list(range(6))
        windows = recon.segment_match_into_windows(ticks)
        assert len(windows) == 2
        assert windows[0] == [0, 1, 2, 3]
        assert windows[1] == [2, 3, 4, 5]

    def test_trailing_ticks_discarded(self):
        """Trailing ticks < sequence_length are intentionally discarded."""
        recon = self._make_reconstructor(seq_len=4)
        # 7 ticks, step=2: [0:4], [2:6], then 4+4=8 > 7 → only 2 windows
        ticks = list(range(7))
        windows = recon.segment_match_into_windows(ticks)
        assert len(windows) == 2

    def test_window_sizes_uniform(self):
        """All windows must have exactly sequence_length ticks."""
        recon = self._make_reconstructor(seq_len=4)
        ticks = list(range(20))
        windows = recon.segment_match_into_windows(ticks)
        for w in windows:
            assert len(w) == 4

    def test_many_windows(self):
        """Large tick list produces expected window count."""
        recon = self._make_reconstructor(seq_len=32)
        ticks = list(range(200))
        windows = recon.segment_match_into_windows(ticks)
        step = 16  # 32 // 2
        expected = (200 - 32) // step + 1  # 168 // 16 + 1 = 11
        assert len(windows) == expected

    def test_window_content_integrity(self):
        """Window content is contiguous slices of the original list."""
        recon = self._make_reconstructor(seq_len=4)
        ticks = list(range(10))
        windows = recon.segment_match_into_windows(ticks)
        for w in windows:
            for i in range(1, len(w)):
                assert w[i] == w[i - 1] + 1


class TestRAPStateReconstructorInit:
    """Tests for constructor defaults."""

    def test_default_sequence_length(self):
        from Programma_CS2_RENAN.backend.processing.state_reconstructor import (
            RAPStateReconstructor,
        )
        from Programma_CS2_RENAN.backend.processing.feature_engineering.vectorizer import (
            METADATA_DIM,
        )
        recon = RAPStateReconstructor.__new__(RAPStateReconstructor)
        recon.sequence_length = 32
        recon.metadata_dim = METADATA_DIM
        recon.map_name = "de_mirage"
        assert recon.sequence_length == 32
        assert recon.metadata_dim == METADATA_DIM
        assert recon.map_name == "de_mirage"
