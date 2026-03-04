"""
Tests for Analysis Gaps — Phase 13 Coverage Expansion.

Covers:
  RoleClassifier (role_classifier.py) — classify, scoring, consensus, team, audit
  DeceptionAnalyzer (deception_index.py) — flash baits, rotation feints, sound, composite
"""

import sys


from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# RoleClassifier
# ---------------------------------------------------------------------------
class TestRoleClassifierColdStart:
    """Tests for cold start behavior of RoleClassifier."""

    def _make_classifier_cold(self):
        from Programma_CS2_RENAN.backend.analysis.role_classifier import RoleClassifier
        store = MagicMock()
        store.is_cold_start.return_value = True
        return RoleClassifier(threshold_store=store)

    def test_cold_start_returns_flex(self):
        from Programma_CS2_RENAN.backend.analysis.role_classifier import PlayerRole
        clf = self._make_classifier_cold()
        role, confidence, profile = clf.classify({"total_kills": 100})
        assert role == PlayerRole.FLEX
        assert confidence == 0.0


class TestRoleClassifierWarm:
    """Tests for RoleClassifier with learned thresholds."""

    def _make_classifier(self):
        from Programma_CS2_RENAN.backend.analysis.role_classifier import RoleClassifier
        store = MagicMock()
        store.is_cold_start.return_value = False
        store.get_threshold.return_value = None  # No specific thresholds → use linear
        return RoleClassifier(threshold_store=store)

    def test_classify_returns_tuple(self):
        clf = self._make_classifier()
        result = clf.classify({"total_kills": 100, "rounds_played": 100})
        assert len(result) == 3

    def test_classify_awper_high_awp_kills(self):
        from Programma_CS2_RENAN.backend.analysis.role_classifier import PlayerRole
        clf = self._make_classifier()
        stats = {"awp_kills": 80, "total_kills": 100, "rounds_played": 100}
        role, conf, _ = clf.classify(stats)
        assert role == PlayerRole.AWPER

    def test_classify_entry_fragger(self):
        from Programma_CS2_RENAN.backend.analysis.role_classifier import PlayerRole
        clf = self._make_classifier()
        stats = {
            "entry_frags": 30,
            "total_kills": 80,
            "rounds_played": 100,
            "first_deaths": 25,
            "awp_kills": 0,
            "assists": 5,
            "rounds_survived": 30,
            "solo_kills": 5,
            "kd_ratio": 1.5,
        }
        role, conf, _ = clf.classify(stats)
        assert role == PlayerRole.ENTRY_FRAGGER

    def test_classify_lurker_high_solo(self):
        from Programma_CS2_RENAN.backend.analysis.role_classifier import PlayerRole
        clf = self._make_classifier()
        stats = {
            "solo_kills": 60,
            "total_kills": 80,
            "rounds_played": 100,
            "awp_kills": 0,
            "entry_frags": 2,
            "assists": 5,
            "rounds_survived": 40,
            "first_deaths": 5,
            "kd_ratio": 1.0,
        }
        role, conf, _ = clf.classify(stats)
        assert role == PlayerRole.LURKER

    def test_calculate_role_scores_dict(self):
        clf = self._make_classifier()
        scores = clf._calculate_role_scores({"total_kills": 100, "rounds_played": 100})
        assert isinstance(scores, dict)
        assert len(scores) == 5  # 5 roles (no FLEX)

    def test_scores_normalized(self):
        clf = self._make_classifier()
        scores = clf._calculate_role_scores({
            "total_kills": 100, "rounds_played": 100,
            "awp_kills": 20, "entry_frags": 15, "assists": 10,
            "rounds_survived": 40, "solo_kills": 10, "first_deaths": 10,
            "kd_ratio": 1.0, "utility_damage_avg": 30,
        })
        total = sum(scores.values())
        assert abs(total - 1.0) < 1e-6


class TestRoleClassifierScoring:
    """Tests for individual role scoring functions."""

    def _make_classifier_with_threshold(self, threshold_val=None):
        from Programma_CS2_RENAN.backend.analysis.role_classifier import RoleClassifier
        store = MagicMock()
        store.is_cold_start.return_value = False
        store.get_threshold.return_value = threshold_val
        return RoleClassifier(threshold_store=store)

    def test_score_awper_no_threshold(self):
        clf = self._make_classifier_with_threshold(None)
        score = clf._score_awper(0.5, {})
        assert score == pytest.approx(0.5 * 1.5)

    def test_score_awper_above_threshold(self):
        clf = self._make_classifier_with_threshold(0.3)
        score = clf._score_awper(0.5, {})
        assert score == pytest.approx(0.8 + (0.5 - 0.3) * 0.5)

    def test_score_entry_no_threshold(self):
        clf = self._make_classifier_with_threshold(None)
        score = clf._score_entry(0.2, {"first_deaths": 10, "rounds_played": 100})
        assert score > 0

    def test_score_support_utility_bonus(self):
        clf = self._make_classifier_with_threshold(None)
        score = clf._score_support(0.3, {"utility_damage_avg": 100})
        # utility_damage_avg / 50 = 2.0, bonus = min(2.0 * 0.2, 0.3) = 0.3
        assert score > 0.3 * 2.0

    def test_score_igl_balanced_kd(self):
        clf = self._make_classifier_with_threshold(None)
        score_balanced = clf._score_igl(0.4, {"kd_ratio": 1.0})
        score_unbalanced = clf._score_igl(0.4, {"kd_ratio": 2.0})
        assert score_balanced > score_unbalanced

    def test_score_lurker_above_threshold(self):
        clf = self._make_classifier_with_threshold(0.2)
        score = clf._score_lurker(0.5, {})
        assert score == pytest.approx(0.7 + (0.5 - 0.2) * 0.8)


class TestConsensus:
    """Tests for the _consensus static method."""

    def test_agree_boosts_confidence(self):
        from Programma_CS2_RENAN.backend.analysis.role_classifier import PlayerRole, RoleClassifier
        role, conf = RoleClassifier._consensus(
            PlayerRole.AWPER, 0.7, PlayerRole.AWPER, 0.8
        )
        assert role == PlayerRole.AWPER
        assert conf == pytest.approx(min((0.7 + 0.8) / 2 + 0.1, 1.0))

    def test_disagree_neural_wins(self):
        from Programma_CS2_RENAN.backend.analysis.role_classifier import PlayerRole, RoleClassifier
        role, conf = RoleClassifier._consensus(
            PlayerRole.SUPPORT, 0.4, PlayerRole.AWPER, 0.6
        )
        # neural (0.6) > heuristic (0.4) + 0.1 → neural wins
        assert role == PlayerRole.AWPER

    def test_disagree_heuristic_wins_tie(self):
        from Programma_CS2_RENAN.backend.analysis.role_classifier import PlayerRole, RoleClassifier
        role, conf = RoleClassifier._consensus(
            PlayerRole.SUPPORT, 0.5, PlayerRole.AWPER, 0.55
        )
        # neural (0.55) NOT > heuristic (0.5) + 0.1 → heuristic wins
        assert role == PlayerRole.SUPPORT


class TestClassifyTeam:
    """Tests for team classification."""

    def _make_classifier(self):
        from Programma_CS2_RENAN.backend.analysis.role_classifier import RoleClassifier
        store = MagicMock()
        store.is_cold_start.return_value = False
        store.get_threshold.return_value = None
        return RoleClassifier(threshold_store=store)

    def test_team_classification_returns_dict(self):
        clf = self._make_classifier()
        team = [
            {"name": "p1", "awp_kills": 60, "total_kills": 80, "rounds_played": 100, "impact_rating": 1.2},
            {"name": "p2", "entry_frags": 25, "total_kills": 70, "rounds_played": 100, "impact_rating": 1.0},
        ]
        results = clf.classify_team(team)
        assert len(results) == 2

    def test_no_duplicate_awper(self):
        from Programma_CS2_RENAN.backend.analysis.role_classifier import PlayerRole
        clf = self._make_classifier()
        # Two players that would both be AWPers
        team = [
            {"name": "p1", "awp_kills": 70, "total_kills": 80, "rounds_played": 100, "impact_rating": 1.3},
            {"name": "p2", "awp_kills": 65, "total_kills": 80, "rounds_played": 100, "impact_rating": 1.1},
        ]
        results = clf.classify_team(team)
        awper_count = sum(1 for _, (r, c) in results.items() if r == PlayerRole.AWPER)
        assert awper_count <= 1


class TestAuditTeamBalance:
    """Tests for team balance auditing."""

    def _make_classifier(self):
        from Programma_CS2_RENAN.backend.analysis.role_classifier import RoleClassifier
        store = MagicMock()
        store.is_cold_start.return_value = False
        store.get_threshold.return_value = None
        return RoleClassifier(threshold_store=store)

    def test_balanced_team_no_issues(self):
        from Programma_CS2_RENAN.backend.analysis.role_classifier import PlayerRole
        clf = self._make_classifier()
        roles = {
            "p1": (PlayerRole.AWPER, 0.8),
            "p2": (PlayerRole.ENTRY_FRAGGER, 0.7),
            "p3": (PlayerRole.SUPPORT, 0.6),
            "p4": (PlayerRole.LURKER, 0.7),
            "p5": (PlayerRole.IGL, 0.5),
        }
        issues = clf.audit_team_balance(roles)
        assert len(issues) == 0

    def test_multiple_awpers_flagged(self):
        from Programma_CS2_RENAN.backend.analysis.role_classifier import PlayerRole
        clf = self._make_classifier()
        roles = {
            "p1": (PlayerRole.AWPER, 0.8),
            "p2": (PlayerRole.AWPER, 0.7),
        }
        issues = clf.audit_team_balance(roles)
        assert any("AWPer" in i["title"] for i in issues)

    def test_no_entry_flagged(self):
        from Programma_CS2_RENAN.backend.analysis.role_classifier import PlayerRole
        clf = self._make_classifier()
        roles = {
            "p1": (PlayerRole.AWPER, 0.8),
            "p2": (PlayerRole.SUPPORT, 0.7),
            "p3": (PlayerRole.LURKER, 0.6),
        }
        issues = clf.audit_team_balance(roles)
        assert any("Entry Fragger" in i["title"] for i in issues)

    def test_no_support_flagged(self):
        from Programma_CS2_RENAN.backend.analysis.role_classifier import PlayerRole
        clf = self._make_classifier()
        roles = {
            "p1": (PlayerRole.AWPER, 0.8),
            "p2": (PlayerRole.ENTRY_FRAGGER, 0.7),
            "p3": (PlayerRole.LURKER, 0.6),
        }
        issues = clf.audit_team_balance(roles)
        assert any("Support" in i["title"] for i in issues)

    def test_all_same_role_critical(self):
        from Programma_CS2_RENAN.backend.analysis.role_classifier import PlayerRole
        clf = self._make_classifier()
        roles = {
            "p1": (PlayerRole.LURKER, 0.5),
            "p2": (PlayerRole.LURKER, 0.5),
            "p3": (PlayerRole.LURKER, 0.5),
        }
        issues = clf.audit_team_balance(roles)
        assert any(i["severity"] == "CRITICAL" for i in issues)

    def test_multiple_lurkers_flagged(self):
        from Programma_CS2_RENAN.backend.analysis.role_classifier import PlayerRole
        clf = self._make_classifier()
        roles = {
            "p1": (PlayerRole.LURKER, 0.7),
            "p2": (PlayerRole.LURKER, 0.6),
            "p3": (PlayerRole.ENTRY_FRAGGER, 0.8),
            "p4": (PlayerRole.SUPPORT, 0.7),
        }
        issues = clf.audit_team_balance(roles)
        assert any("Lurker" in i["title"] for i in issues)


class TestRoleProfiles:
    """Tests for role profile constants and fallback tips."""

    def test_all_roles_have_profiles(self):
        from Programma_CS2_RENAN.backend.analysis.role_classifier import (
            PlayerRole,
            ROLE_PROFILES,
        )
        for role in PlayerRole:
            assert role in ROLE_PROFILES

    def test_fallback_tips_exist(self):
        from Programma_CS2_RENAN.backend.analysis.role_classifier import (
            PlayerRole,
            _FALLBACK_TIPS,
        )
        for role in PlayerRole:
            assert role in _FALLBACK_TIPS
            assert len(_FALLBACK_TIPS[role]) >= 1


# ---------------------------------------------------------------------------
# DeceptionAnalyzer (deception_index.py)
# ---------------------------------------------------------------------------
class TestDeceptionMetrics:
    """Tests for DeceptionMetrics dataclass."""

    def test_defaults(self):
        from Programma_CS2_RENAN.backend.analysis.deception_index import DeceptionMetrics
        m = DeceptionMetrics()
        assert m.fake_flash_rate == 0.0
        assert m.rotation_feint_rate == 0.0
        assert m.sound_deception_score == 0.0
        assert m.composite_index == 0.0

    def test_custom_values(self):
        from Programma_CS2_RENAN.backend.analysis.deception_index import DeceptionMetrics
        m = DeceptionMetrics(fake_flash_rate=0.5, composite_index=0.8)
        assert m.fake_flash_rate == 0.5
        assert m.composite_index == 0.8


class TestDeceptionAnalyzer:
    """Tests for the DeceptionAnalyzer."""

    def _make_analyzer(self):
        from Programma_CS2_RENAN.backend.analysis.deception_index import DeceptionAnalyzer
        return DeceptionAnalyzer()

    def test_empty_round(self):
        analyzer = self._make_analyzer()
        df = pd.DataFrame()
        result = analyzer.analyze_round(df)
        assert result.composite_index == 0.0

    def test_flash_baits_no_event_type(self):
        analyzer = self._make_analyzer()
        df = pd.DataFrame({"tick": [100, 200]})
        result = analyzer._detect_flash_baits(df)
        assert result == 0.0

    def test_flash_baits_no_flashes(self):
        analyzer = self._make_analyzer()
        df = pd.DataFrame({"event_type": ["player_death", "player_death"], "tick": [100, 200]})
        result = analyzer._detect_flash_baits(df)
        assert result == 0.0

    def test_flash_baits_all_ineffective(self):
        analyzer = self._make_analyzer()
        df = pd.DataFrame({
            "event_type": ["flashbang_throw", "flashbang_throw"],
            "tick": [100, 200],
        })
        result = analyzer._detect_flash_baits(df)
        # No blinds → 100% bait rate
        assert result == pytest.approx(1.0)

    def test_flash_baits_all_effective(self):
        analyzer = self._make_analyzer()
        df = pd.DataFrame({
            "event_type": ["flashbang_throw", "player_blind", "flashbang_throw", "player_blind"],
            "tick": [100, 110, 200, 210],
        })
        result = analyzer._detect_flash_baits(df)
        assert result == pytest.approx(0.0)

    def test_rotation_feints_no_positions(self):
        analyzer = self._make_analyzer()
        df = pd.DataFrame({"tick": range(50)})
        result = analyzer._detect_rotation_feints(df)
        assert result == 0.0

    def test_rotation_feints_too_few_samples(self):
        analyzer = self._make_analyzer()
        df = pd.DataFrame({"pos_x": [0, 1], "pos_y": [0, 1]})
        result = analyzer._detect_rotation_feints(df)
        assert result == 0.0

    def test_rotation_feints_straight_line(self):
        analyzer = self._make_analyzer()
        n = 100
        df = pd.DataFrame({
            "pos_x": np.linspace(0, 100, n),
            "pos_y": np.linspace(0, 100, n),
        })
        result = analyzer._detect_rotation_feints(df)
        # Straight line = no direction changes
        assert result < 0.3

    def test_sound_deception_no_crouching_col(self):
        analyzer = self._make_analyzer()
        df = pd.DataFrame({"tick": range(50)})
        result = analyzer._detect_sound_deception(df)
        assert result == 0.0

    def test_sound_deception_all_crouching(self):
        analyzer = self._make_analyzer()
        df = pd.DataFrame({"is_crouching": [True] * 100})
        result = analyzer._detect_sound_deception(df)
        # All crouching → stealthy → score = 1.0 - 1.0*2.0 = -1.0 → clamped to 0.0
        assert result == 0.0

    def test_sound_deception_no_crouching(self):
        analyzer = self._make_analyzer()
        df = pd.DataFrame({"is_crouching": [False] * 100})
        result = analyzer._detect_sound_deception(df)
        # No crouching → fully noisy → score = 1.0 - 0 = 1.0
        assert result == 1.0

    def test_composite_bounded(self):
        analyzer = self._make_analyzer()
        # Create a round with some events
        df = pd.DataFrame({
            "event_type": ["flashbang_throw"] * 10,
            "tick": list(range(100, 200, 10)),
            "pos_x": np.linspace(0, 200, 10),
            "pos_y": np.linspace(0, 200, 10),
            "is_crouching": [False] * 10,
        })
        result = analyzer.analyze_round(df)
        assert 0.0 <= result.composite_index <= 1.0


class TestDeceptionCompareToBaseline:
    """Tests for the compare_to_baseline narrative generator."""

    def _make_analyzer(self):
        from Programma_CS2_RENAN.backend.analysis.deception_index import DeceptionAnalyzer
        return DeceptionAnalyzer()

    def _metrics(self, composite=0.5, rotation=0.3):
        from Programma_CS2_RENAN.backend.analysis.deception_index import DeceptionMetrics
        return DeceptionMetrics(composite_index=composite, rotation_feint_rate=rotation)

    def test_above_baseline(self):
        analyzer = self._make_analyzer()
        result = analyzer.compare_to_baseline(
            self._metrics(composite=0.7), self._metrics(composite=0.4)
        )
        assert "above" in result.lower()

    def test_below_baseline(self):
        analyzer = self._make_analyzer()
        result = analyzer.compare_to_baseline(
            self._metrics(composite=0.2), self._metrics(composite=0.5)
        )
        assert "below" in result.lower()

    def test_aligns_with_baseline(self):
        analyzer = self._make_analyzer()
        result = analyzer.compare_to_baseline(
            self._metrics(composite=0.5), self._metrics(composite=0.5)
        )
        assert "aligns" in result.lower()

    def test_rotation_feint_feedback(self):
        analyzer = self._make_analyzer()
        result = analyzer.compare_to_baseline(
            self._metrics(composite=0.5, rotation=0.1),
            self._metrics(composite=0.5, rotation=0.4),
        )
        assert "rotation" in result.lower()


class TestDeceptionFactory:
    """Tests for factory and constants."""

    def test_get_deception_analyzer(self):
        from Programma_CS2_RENAN.backend.analysis.deception_index import get_deception_analyzer
        analyzer = get_deception_analyzer()
        assert analyzer is not None

    def test_constants(self):
        from Programma_CS2_RENAN.backend.analysis.deception_index import (
            FAKE_EXECUTE_WINDOW,
            FLASH_BLIND_WINDOW_TICKS,
            UTILITY_FOLLOWUP_WINDOW,
            W_FAKE_FLASH,
            W_ROTATION_FEINT,
            W_SOUND_DECEPTION,
        )
        assert FAKE_EXECUTE_WINDOW == 5.0
        assert UTILITY_FOLLOWUP_WINDOW == 3.0
        assert FLASH_BLIND_WINDOW_TICKS == 128
        assert abs(W_FAKE_FLASH + W_ROTATION_FEINT + W_SOUND_DECEPTION - 1.0) < 1e-6
