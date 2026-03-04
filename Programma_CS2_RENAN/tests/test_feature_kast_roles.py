"""
Tests for Feature Engineering — Phase 14 Coverage Expansion.

Covers:
  calculate_kast_for_round, calculate_kast_percentage, estimate_kast_from_stats (kast.py)
  classify_role, extract_role_features, get_role_coaching_focus (role_features.py)
  CoachingDialogueEngine helpers (coaching_dialogue.py) — intent, prompts, fallbacks
"""

import sys


from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# KAST Calculation (kast.py)
# ---------------------------------------------------------------------------
class TestCalculateKastForRound:
    """Tests for calculate_kast_for_round."""

    def test_kill_achieves_kast(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.kast import calculate_kast_for_round
        events = [
            {"type": "player_death", "attacker": "Player1", "victim": "Enemy1", "assister": "", "tick": 100},
        ]
        assert calculate_kast_for_round("Player1", events) is True

    def test_assist_achieves_kast(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.kast import calculate_kast_for_round
        events = [
            {"type": "player_death", "attacker": "Teammate", "victim": "Enemy1", "assister": "Player1", "tick": 100},
        ]
        assert calculate_kast_for_round("Player1", events) is True

    def test_survive_achieves_kast(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.kast import calculate_kast_for_round
        events = [
            {"type": "player_death", "attacker": "Enemy1", "victim": "Teammate", "assister": "", "tick": 100},
        ]
        # Player1 survived (not in any victim field)
        assert calculate_kast_for_round("Player1", events) is True

    def test_traded_achieves_kast(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.kast import calculate_kast_for_round
        events = [
            {"type": "player_death", "attacker": "Enemy1", "victim": "Player1", "assister": "", "tick": 100},
            {"type": "player_death", "attacker": "Teammate", "victim": "Enemy1", "assister": "", "tick": 200},
        ]
        # Player1 died at tick 100, Enemy1 died at tick 200 (within 320-tick window at 64tps)
        assert calculate_kast_for_round("Player1", events) is True

    def test_not_traded_too_late(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.kast import calculate_kast_for_round
        events = [
            {"type": "player_death", "attacker": "Enemy1", "victim": "Player1", "assister": "", "tick": 100},
            {"type": "player_death", "attacker": "Teammate", "victim": "Enemy1", "assister": "", "tick": 500},
        ]
        # 400 ticks gap > 320 tick window
        assert calculate_kast_for_round("Player1", events) is False

    def test_no_events_survives(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.kast import calculate_kast_for_round
        # No deaths → player survived
        assert calculate_kast_for_round("Player1", []) is True

    def test_non_death_events_ignored(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.kast import calculate_kast_for_round
        events = [
            {"type": "weapon_fire", "attacker": "Player1"},
            {"type": "hurt_event", "victim": "Enemy1"},
        ]
        assert calculate_kast_for_round("Player1", events) is True

    def test_self_kill_not_counted(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.kast import calculate_kast_for_round
        events = [
            {"type": "player_death", "attacker": "Player1", "victim": "Player1", "assister": "", "tick": 100},
        ]
        # Self-kill: attacker == victim == player → K not counted (victim == player_name)
        # Player also died, so S not achieved
        assert calculate_kast_for_round("Player1", events) is False

    def test_custom_tick_rate(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.kast import calculate_kast_for_round
        events = [
            {"type": "player_death", "attacker": "Enemy1", "victim": "Player1", "assister": "", "tick": 100},
            {"type": "player_death", "attacker": "Teammate", "victim": "Enemy1", "assister": "", "tick": 500},
        ]
        # At 128 tps: window = 5 * 128 = 640 ticks, so 400 tick gap is within
        assert calculate_kast_for_round("Player1", events, ticks_per_second=128) is True


class TestCalculateKastPercentage:
    """Tests for calculate_kast_percentage."""

    def test_empty_rounds(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.kast import calculate_kast_percentage
        assert calculate_kast_percentage("Player1", []) == 0.0

    def test_all_kast_rounds(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.kast import calculate_kast_percentage
        rounds = [
            [{"type": "player_death", "attacker": "Player1", "victim": "Enemy", "assister": "", "tick": 100}],
            [],  # survived
        ]
        assert calculate_kast_percentage("Player1", rounds) == 1.0

    def test_partial_kast(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.kast import calculate_kast_percentage
        rounds = [
            [{"type": "player_death", "attacker": "Player1", "victim": "Enemy", "assister": "", "tick": 100}],
            [{"type": "player_death", "attacker": "Enemy", "victim": "Player1", "assister": "", "tick": 100}],
        ]
        # Round 1: kill → KAST. Round 2: died, not traded → no KAST
        assert calculate_kast_percentage("Player1", rounds) == 0.5


class TestEstimateKastFromStats:
    """Tests for estimate_kast_from_stats."""

    def test_zero_rounds(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.kast import estimate_kast_from_stats
        assert estimate_kast_from_stats(10, 5, 8, 0) == 0.0

    def test_perfect_stats(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.kast import estimate_kast_from_stats
        # Many kills, few deaths → high KAST
        result = estimate_kast_from_stats(kills=25, assists=5, deaths=5, rounds_played=30)
        assert 0.0 <= result <= 1.0
        assert result > 0.7

    def test_poor_stats(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.kast import estimate_kast_from_stats
        # Few kills, many deaths → lower KAST
        result = estimate_kast_from_stats(kills=3, assists=1, deaths=25, rounds_played=30)
        assert 0.0 <= result <= 1.0

    def test_bounded_output(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.kast import estimate_kast_from_stats
        result = estimate_kast_from_stats(kills=1000, assists=500, deaths=0, rounds_played=10)
        assert result <= 1.0


# ---------------------------------------------------------------------------
# Role Features (role_features.py)
# ---------------------------------------------------------------------------
class TestClassifyRole:
    """Tests for classify_role function."""

    def test_empty_stats_returns_unknown(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.role_features import (
            PlayerRole,
            classify_role,
        )
        role, conf = classify_role({})
        assert role == PlayerRole.UNKNOWN
        assert conf == 0.0

    def test_entry_stats(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.role_features import classify_role
        stats = {
            "opening_attempts_per_round": 0.35,
            "first_kill_pct": 0.18,
            "first_death_pct": 0.22,
            "kpr": 0.78,
            "adr": 85.0,
        }
        role, conf = classify_role(stats)
        assert role.value == "entry"
        assert 0.0 <= conf <= 1.0

    def test_awper_stats(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.role_features import classify_role
        stats = {
            "opening_attempts_per_round": 0.25,
            "first_kill_pct": 0.20,
            "first_death_pct": 0.12,
            "kpr": 0.72,
            "adr": 75.0,
        }
        role, conf = classify_role(stats)
        assert role.value == "awper"

    def test_support_stats(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.role_features import classify_role
        stats = {
            "opening_attempts_per_round": 0.15,
            "first_kill_pct": 0.08,
            "first_death_pct": 0.14,
            "kpr": 0.65,
            "adr": 72.0,
        }
        role, conf = classify_role(stats)
        assert role.value == "support"

    def test_confidence_bounded(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.role_features import classify_role
        stats = {"kpr": 0.5, "adr": 60.0}
        _, conf = classify_role(stats)
        assert 0.0 <= conf <= 1.0


class TestExtractRoleFeatures:
    """Tests for extract_role_features function."""

    def test_auto_detect_role(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.role_features import extract_role_features
        stats = {
            "opening_attempts_per_round": 0.35,
            "first_kill_pct": 0.18,
            "first_death_pct": 0.22,
            "kpr": 0.78,
            "adr": 85.0,
        }
        features = extract_role_features(stats)
        assert "detected_role" in features
        assert len(features) > 1

    def test_with_explicit_role(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.role_features import (
            PlayerRole,
            extract_role_features,
        )
        stats = {"opening_attempts_per_round": 0.2, "kpr": 0.7}
        features = extract_role_features(stats, role=PlayerRole.AWPER)
        assert features["detected_role"] == "awper"

    def test_unknown_role_returns_empty(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.role_features import (
            PlayerRole,
            extract_role_features,
        )
        features = extract_role_features({}, role=PlayerRole.UNKNOWN)
        assert features == {}

    def test_deviation_calculation(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.role_features import (
            PlayerRole,
            extract_role_features,
        )
        stats = {"opening_attempts_per_round": 0.70}  # Double the entry baseline (0.35)
        features = extract_role_features(stats, role=PlayerRole.ENTRY)
        assert features["opening_attempts_per_round_deviation"] == pytest.approx(1.0)
        assert features["opening_attempts_per_round_value"] == 0.70
        assert features["opening_attempts_per_round_baseline"] == 0.35


class TestGetRoleCoachingFocus:
    """Tests for get_role_coaching_focus function."""

    def test_entry_focus(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.role_features import (
            PlayerRole,
            get_role_coaching_focus,
        )
        focus = get_role_coaching_focus(PlayerRole.ENTRY)
        assert "first_kill_pct" in focus

    def test_awper_focus(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.role_features import (
            PlayerRole,
            get_role_coaching_focus,
        )
        focus = get_role_coaching_focus(PlayerRole.AWPER)
        assert "awp_kills_pct" in focus

    def test_unknown_role_default(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.role_features import (
            PlayerRole,
            get_role_coaching_focus,
        )
        focus = get_role_coaching_focus(PlayerRole.UNKNOWN)
        assert "kpr" in focus
        assert "adr" in focus

    def test_all_known_roles_have_focus(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.role_features import (
            PlayerRole,
            get_role_coaching_focus,
        )
        for role in [PlayerRole.ENTRY, PlayerRole.AWPER, PlayerRole.SUPPORT, PlayerRole.LURKER, PlayerRole.IGL]:
            focus = get_role_coaching_focus(role)
            assert len(focus) >= 3

    def test_role_signatures_exist(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering.role_features import (
            PlayerRole,
            ROLE_SIGNATURES,
        )
        assert PlayerRole.ENTRY in ROLE_SIGNATURES
        assert PlayerRole.AWPER in ROLE_SIGNATURES
        assert PlayerRole.SUPPORT in ROLE_SIGNATURES
        assert PlayerRole.LURKER in ROLE_SIGNATURES
        assert PlayerRole.IGL in ROLE_SIGNATURES


# ---------------------------------------------------------------------------
# CoachingDialogueEngine helpers (coaching_dialogue.py)
# ---------------------------------------------------------------------------
class TestCoachingDialogueIntent:
    """Tests for intent classification."""

    def _make_engine_shell(self):
        from Programma_CS2_RENAN.backend.services.coaching_dialogue import CoachingDialogueEngine
        engine = CoachingDialogueEngine.__new__(CoachingDialogueEngine)
        engine._llm = MagicMock()
        engine._player_context = {}
        engine._system_prompt = ""
        engine._history = []
        engine._session_active = False
        return engine

    def test_positioning_intent(self):
        engine = self._make_engine_shell()
        assert engine._classify_intent("Where should I hold on B site?") == "positioning"

    def test_utility_intent(self):
        engine = self._make_engine_shell()
        assert engine._classify_intent("Best smoke lineup for A main") == "utility"

    def test_economy_intent(self):
        engine = self._make_engine_shell()
        assert engine._classify_intent("Should I force buy or save?") == "economy"

    def test_aim_intent(self):
        engine = self._make_engine_shell()
        assert engine._classify_intent("How do I improve my spray control?") == "aim"

    def test_general_intent(self):
        engine = self._make_engine_shell()
        assert engine._classify_intent("How can I get better?") == "general"


class TestCoachingDialogueSystemPrompt:
    """Tests for system prompt building."""

    def _make_engine_shell(self):
        from Programma_CS2_RENAN.backend.services.coaching_dialogue import CoachingDialogueEngine
        engine = CoachingDialogueEngine.__new__(CoachingDialogueEngine)
        engine._llm = MagicMock()
        engine._player_context = {"player_name": "TestPlayer", "demo_name": "match123.dem"}
        engine._system_prompt = ""
        engine._history = []
        engine._session_active = False
        return engine

    def test_system_prompt_contains_player_name(self):
        engine = self._make_engine_shell()
        prompt = engine._build_system_prompt()
        assert "TestPlayer" in prompt

    def test_system_prompt_contains_demo_name(self):
        engine = self._make_engine_shell()
        prompt = engine._build_system_prompt()
        assert "match123.dem" in prompt

    def test_system_prompt_with_focus(self):
        engine = self._make_engine_shell()
        engine._player_context["primary_focus"] = "positioning"
        prompt = engine._build_system_prompt()
        assert "positioning" in prompt

    def test_system_prompt_with_insights(self):
        engine = self._make_engine_shell()
        engine._player_context["recent_insights"] = [
            {"severity": "High", "title": "Poor Aim", "message": "Crosshair placement needs work"}
        ]
        prompt = engine._build_system_prompt()
        assert "Poor Aim" in prompt


class TestCoachingDialogueChatMessages:
    """Tests for chat message building."""

    def _make_engine_shell(self):
        from Programma_CS2_RENAN.backend.services.coaching_dialogue import CoachingDialogueEngine
        engine = CoachingDialogueEngine.__new__(CoachingDialogueEngine)
        engine._llm = MagicMock()
        engine._player_context = {}
        engine._system_prompt = ""
        engine._history = []
        engine._session_active = True
        return engine

    def test_empty_history(self):
        engine = self._make_engine_shell()
        messages = engine._build_chat_messages("Hello coach")
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    def test_with_history(self):
        engine = self._make_engine_shell()
        engine._history = [
            {"role": "assistant", "content": "Hi!"},
            {"role": "user", "content": "How do I play B?"},
            {"role": "assistant", "content": "Hold angles."},
        ]
        messages = engine._build_chat_messages("What about utility?")
        # _history[:-1] = 2 items (drops last), + 1 new user message = 3
        assert len(messages) == 3
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "What about utility?"


class TestCoachingDialogueOffline:
    """Tests for offline/fallback responses."""

    def _make_engine_shell(self):
        from Programma_CS2_RENAN.backend.services.coaching_dialogue import CoachingDialogueEngine
        engine = CoachingDialogueEngine.__new__(CoachingDialogueEngine)
        engine._llm = MagicMock()
        engine._player_context = {"player_name": "TestPlayer"}
        engine._system_prompt = ""
        engine._history = []
        engine._session_active = False
        return engine

    def test_offline_opening(self):
        engine = self._make_engine_shell()
        msg = engine._offline_opening()
        assert "TestPlayer" in msg
        assert "Offline" in msg

    def test_offline_opening_with_focus(self):
        engine = self._make_engine_shell()
        engine._player_context["primary_focus"] = "utility"
        msg = engine._offline_opening()
        assert "utility" in msg

    def test_fallback_response_no_retrieval(self):
        engine = self._make_engine_shell()
        # Mock _retrieve_context to return empty
        engine._retrieve_context = MagicMock(return_value="")
        msg = engine._fallback_response("How do I play?", "general")
        assert "Offline" in msg

    def test_fallback_response_with_retrieval(self):
        engine = self._make_engine_shell()
        engine._retrieve_context = MagicMock(return_value="Tactical knowledge: Hold B site angles")
        msg = engine._fallback_response("How do I play?", "positioning")
        assert "knowledge base" in msg.lower()

    def test_get_history(self):
        engine = self._make_engine_shell()
        engine._history = [{"role": "user", "content": "test"}]
        history = engine.get_history()
        assert len(history) == 1
        # Should return a copy
        history.append({"role": "fake"})
        assert len(engine._history) == 1

    def test_clear_session(self):
        engine = self._make_engine_shell()
        engine._session_active = True
        engine._history = [{"role": "user", "content": "test"}]
        engine.clear_session()
        assert engine._session_active is False
        assert len(engine._history) == 0


class TestCoachingDialogueConstants:
    """Tests for module-level constants."""

    def test_intent_keywords(self):
        from Programma_CS2_RENAN.backend.services.coaching_dialogue import INTENT_KEYWORDS
        assert "positioning" in INTENT_KEYWORDS
        assert "utility" in INTENT_KEYWORDS
        assert "economy" in INTENT_KEYWORDS
        assert "aim" in INTENT_KEYWORDS

    def test_max_context_turns(self):
        from Programma_CS2_RENAN.backend.services.coaching_dialogue import CoachingDialogueEngine
        assert CoachingDialogueEngine.MAX_CONTEXT_TURNS == 6

    def test_retrieval_top_k(self):
        from Programma_CS2_RENAN.backend.services.coaching_dialogue import CoachingDialogueEngine
        assert CoachingDialogueEngine.RETRIEVAL_TOP_K == 3
