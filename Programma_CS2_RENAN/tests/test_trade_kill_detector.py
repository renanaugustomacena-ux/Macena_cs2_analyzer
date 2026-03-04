"""
Tests for Trade Kill Detector — Phase 15 Coverage Expansion.

Covers:
  TradeKillResult — dataclass, trade_kill_ratio, was_traded_ratio
  assign_round_numbers — np.searchsorted based round assignment
  detect_trade_kills — trade detection algorithm with team roster
  get_player_trade_stats — per-player aggregation
"""

import sys


import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# TradeKillResult
# ---------------------------------------------------------------------------
class TestTradeKillResult:
    """Tests for the TradeKillResult dataclass."""

    def _make(self, **kwargs):
        from Programma_CS2_RENAN.backend.data_sources.trade_kill_detector import TradeKillResult
        return TradeKillResult(**kwargs)

    def test_defaults(self):
        r = self._make()
        assert r.total_kills == 0
        assert r.trade_kills == 0
        assert r.players_traded == 0
        assert r.trade_details == []

    def test_trade_kill_ratio_no_kills(self):
        r = self._make(total_kills=0, trade_kills=0)
        assert r.trade_kill_ratio == 0.0

    def test_trade_kill_ratio(self):
        r = self._make(total_kills=10, trade_kills=3)
        assert abs(r.trade_kill_ratio - 0.3) < 1e-6

    def test_was_traded_ratio_no_kills(self):
        r = self._make(total_kills=0, players_traded=0)
        assert r.was_traded_ratio == 0.0

    def test_was_traded_ratio(self):
        r = self._make(total_kills=20, players_traded=5)
        assert abs(r.was_traded_ratio - 0.25) < 1e-6

    def test_trade_details_mutable(self):
        r = self._make()
        r.trade_details.append({"tick": 100})
        assert len(r.trade_details) == 1


# ---------------------------------------------------------------------------
# assign_round_numbers
# ---------------------------------------------------------------------------
class TestAssignRoundNumbers:
    """Tests for round number assignment from tick boundaries."""

    def _assign(self, ticks, boundaries):
        from Programma_CS2_RENAN.backend.data_sources.trade_kill_detector import assign_round_numbers
        return assign_round_numbers(pd.Series(ticks), boundaries)

    def test_single_round(self):
        rounds = self._assign([100, 200, 300], [0])
        assert list(rounds) == [1, 1, 1]

    def test_multiple_rounds(self):
        # Boundaries: round 1 = [0, 1000), round 2 = [1000, 2000), round 3 = [2000, ...)
        rounds = self._assign([500, 1500, 2500], [0, 1000, 2000])
        assert list(rounds) == [1, 2, 3]

    def test_tick_at_boundary(self):
        rounds = self._assign([1000], [0, 1000, 2000])
        # searchsorted side="right" → 1000 falls in round 2
        assert list(rounds) == [2]

    def test_empty_ticks(self):
        rounds = self._assign([], [0, 1000])
        assert len(rounds) == 0

    def test_preserves_index(self):
        ticks = pd.Series([500, 1500], index=[10, 20])
        from Programma_CS2_RENAN.backend.data_sources.trade_kill_detector import assign_round_numbers
        rounds = assign_round_numbers(ticks, [0, 1000])
        assert list(rounds.index) == [10, 20]


# ---------------------------------------------------------------------------
# detect_trade_kills
# ---------------------------------------------------------------------------
class TestDetectTradeKills:
    """Tests for the core trade kill detection algorithm."""

    def _detect(self, deaths_data, roster, trade_window=192):
        from Programma_CS2_RENAN.backend.data_sources.trade_kill_detector import detect_trade_kills
        df = pd.DataFrame(deaths_data)
        return detect_trade_kills(df, roster, trade_window)

    def test_empty_dataframe(self):
        from Programma_CS2_RENAN.backend.data_sources.trade_kill_detector import detect_trade_kills
        result = detect_trade_kills(pd.DataFrame(), {"alice": 2})
        assert result.total_kills == 0
        assert result.trade_kills == 0

    def test_empty_roster(self):
        deaths = [{"tick": 100, "attacker_name": "alice", "user_name": "bob", "round_num": 1}]
        result = self._detect(deaths, {})
        assert result.total_kills == 0

    def test_missing_columns(self):
        from Programma_CS2_RENAN.backend.data_sources.trade_kill_detector import detect_trade_kills
        df = pd.DataFrame({"tick": [100], "some_col": ["x"]})
        result = detect_trade_kills(df, {"alice": 2})
        assert result.total_kills == 0

    def test_simple_trade_kill(self):
        """B kills A's teammate, then A kills B = trade."""
        roster = {"alice": 2, "bob": 3, "charlie": 2}
        deaths = [
            # Bob kills Charlie (Alice's teammate)
            {"tick": 1000, "attacker_name": "Bob", "user_name": "Charlie", "round_num": 1},
            # Alice kills Bob within trade window (avenging Charlie)
            {"tick": 1100, "attacker_name": "Alice", "user_name": "Bob", "round_num": 1},
        ]
        result = self._detect(deaths, roster)
        assert result.total_kills == 2
        assert result.trade_kills == 1
        assert result.players_traded == 1
        assert len(result.trade_details) == 1
        assert result.trade_details[0]["trade_killer"] == "alice"
        assert result.trade_details[0]["original_victim"] == "charlie"

    def test_no_trade_outside_window(self):
        """Kill outside trade window should NOT be detected as trade."""
        roster = {"alice": 2, "bob": 3, "charlie": 2}
        deaths = [
            {"tick": 1000, "attacker_name": "Bob", "user_name": "Charlie", "round_num": 1},
            {"tick": 1300, "attacker_name": "Alice", "user_name": "Bob", "round_num": 1},
        ]
        # Window = 192 ticks, gap = 300 ticks → no trade
        result = self._detect(deaths, roster)
        assert result.trade_kills == 0

    def test_no_trade_different_rounds(self):
        """Kills in different rounds should NOT be linked as trades."""
        roster = {"alice": 2, "bob": 3, "charlie": 2}
        deaths = [
            {"tick": 1000, "attacker_name": "Bob", "user_name": "Charlie", "round_num": 1},
            {"tick": 1050, "attacker_name": "Alice", "user_name": "Bob", "round_num": 2},
        ]
        result = self._detect(deaths, roster)
        assert result.trade_kills == 0

    def test_team_kill_ignored(self):
        """Team kills should not count as trades."""
        roster = {"alice": 2, "bob": 2, "charlie": 3}
        deaths = [
            {"tick": 1000, "attacker_name": "Charlie", "user_name": "Alice", "round_num": 1},
            # Bob kills Charlie, but Bob and Alice are same team
            {"tick": 1050, "attacker_name": "Bob", "user_name": "Charlie", "round_num": 1},
        ]
        # This IS a trade (Charlie killed Alice, Bob avenges Alice)
        result = self._detect(deaths, roster)
        assert result.trade_kills == 1

    def test_unknown_player_ignored(self):
        """Players not in roster should be skipped."""
        roster = {"alice": 2, "bob": 3}
        deaths = [
            {"tick": 1000, "attacker_name": "Unknown", "user_name": "Alice", "round_num": 1},
            {"tick": 1050, "attacker_name": "Bob", "user_name": "Unknown", "round_num": 1},
        ]
        result = self._detect(deaths, roster)
        assert result.trade_kills == 0

    def test_multiple_trades_in_round(self):
        """Multiple trades can occur in the same round."""
        roster = {"a1": 2, "a2": 2, "b1": 3, "b2": 3}
        deaths = [
            # B1 kills A1, then A2 trades
            {"tick": 1000, "attacker_name": "B1", "user_name": "A1", "round_num": 1},
            {"tick": 1100, "attacker_name": "A2", "user_name": "B1", "round_num": 1},
            # B2 kills A2, then... no trade (no one left)
            {"tick": 1200, "attacker_name": "B2", "user_name": "A2", "round_num": 1},
        ]
        result = self._detect(deaths, roster)
        assert result.trade_kills >= 1

    def test_custom_trade_window(self):
        """Trade window parameter affects detection."""
        roster = {"alice": 2, "bob": 3, "charlie": 2}
        deaths = [
            {"tick": 1000, "attacker_name": "Bob", "user_name": "Charlie", "round_num": 1},
            {"tick": 1150, "attacker_name": "Alice", "user_name": "Bob", "round_num": 1},
        ]
        # With default window (192) → trade detected
        result_wide = self._detect(deaths, roster, trade_window=192)
        assert result_wide.trade_kills == 1

        # With narrow window (100) → no trade
        result_narrow = self._detect(deaths, roster, trade_window=100)
        assert result_narrow.trade_kills == 0

    def test_trade_detail_fields(self):
        """Trade details should contain expected fields."""
        roster = {"alice": 2, "bob": 3, "charlie": 2}
        deaths = [
            {"tick": 1000, "attacker_name": "Bob", "user_name": "Charlie", "round_num": 1},
            {"tick": 1100, "attacker_name": "Alice", "user_name": "Bob", "round_num": 1},
        ]
        result = self._detect(deaths, roster)
        detail = result.trade_details[0]
        assert "trade_tick" in detail
        assert "trade_killer" in detail
        assert "original_killer" in detail
        assert "original_victim" in detail
        assert "original_tick" in detail
        assert "response_ticks" in detail
        assert "round" in detail
        assert detail["response_ticks"] == 100


# ---------------------------------------------------------------------------
# get_player_trade_stats
# ---------------------------------------------------------------------------
class TestGetPlayerTradeStats:
    """Tests for per-player trade stat aggregation."""

    def _make_result(self, details):
        from Programma_CS2_RENAN.backend.data_sources.trade_kill_detector import TradeKillResult
        return TradeKillResult(
            total_kills=len(details) * 2,
            trade_kills=len(details),
            players_traded=len(details),
            trade_details=details,
        )

    def _get_stats(self, result, roster):
        from Programma_CS2_RENAN.backend.data_sources.trade_kill_detector import get_player_trade_stats
        return get_player_trade_stats(result, roster)

    def test_empty_details(self):
        from Programma_CS2_RENAN.backend.data_sources.trade_kill_detector import (
            TradeKillResult,
            get_player_trade_stats,
        )
        result = TradeKillResult()
        roster = {"alice": 2, "bob": 3}
        stats = get_player_trade_stats(result, roster)
        assert "alice" in stats
        assert stats["alice"]["trade_kills"] == 0
        assert stats["alice"]["times_traded"] == 0

    def test_single_trade(self):
        details = [{
            "trade_tick": 1100,
            "trade_killer": "alice",
            "original_killer": "bob",
            "original_victim": "charlie",
            "original_tick": 1000,
            "response_ticks": 100,
            "round": 1,
        }]
        result = self._make_result(details)
        roster = {"alice": 2, "bob": 3, "charlie": 2}
        stats = self._get_stats(result, roster)

        assert stats["alice"]["trade_kills"] == 1
        assert stats["alice"]["avg_response_ticks"] == 100.0
        assert stats["charlie"]["times_traded"] == 1

    def test_multiple_trades_same_player(self):
        details = [
            {
                "trade_tick": 1100, "trade_killer": "alice", "original_killer": "bob",
                "original_victim": "charlie", "original_tick": 1000, "response_ticks": 100, "round": 1,
            },
            {
                "trade_tick": 2100, "trade_killer": "alice", "original_killer": "dave",
                "original_victim": "charlie", "original_tick": 2000, "response_ticks": 50, "round": 2,
            },
        ]
        result = self._make_result(details)
        roster = {"alice": 2, "bob": 3, "charlie": 2, "dave": 3}
        stats = self._get_stats(result, roster)

        assert stats["alice"]["trade_kills"] == 2
        assert stats["alice"]["avg_response_ticks"] == 75.0  # (100 + 50) / 2
        assert stats["charlie"]["times_traded"] == 2

    def test_unknown_trader_ignored(self):
        """If trade_killer is not in roster, stats remain zero."""
        details = [{
            "trade_tick": 1100, "trade_killer": "unknown",
            "original_killer": "bob", "original_victim": "charlie",
            "original_tick": 1000, "response_ticks": 100, "round": 1,
        }]
        result = self._make_result(details)
        roster = {"alice": 2, "bob": 3, "charlie": 2}
        stats = self._get_stats(result, roster)
        # unknown is not in roster, so alice/bob/charlie stats unaffected for trade_kills
        assert stats["alice"]["trade_kills"] == 0

    def test_all_players_initialized(self):
        from Programma_CS2_RENAN.backend.data_sources.trade_kill_detector import (
            TradeKillResult,
            get_player_trade_stats,
        )
        result = TradeKillResult()
        roster = {"p1": 2, "p2": 2, "p3": 3, "p4": 3, "p5": 3}
        stats = get_player_trade_stats(result, roster)
        assert len(stats) == 5
        for name in roster:
            assert name in stats
            assert "trade_kills" in stats[name]
            assert "times_traded" in stats[name]
            assert "avg_response_ticks" in stats[name]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
class TestTradeKillConstants:
    """Tests for module-level constants."""

    def test_trade_window_ticks(self):
        from Programma_CS2_RENAN.backend.data_sources.trade_kill_detector import TRADE_WINDOW_TICKS
        assert TRADE_WINDOW_TICKS == 192  # 3 seconds at 64 tick
