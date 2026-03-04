"""
Tests for Round Utilities and ExperienceContext — Phase 5 Coverage Expansion.

Covers:
  infer_round_phase (round_utils.py) — equipment threshold classification
  ExperienceContext (experience_bank.py) — query string, hash, dataclass
  SynthesizedAdvice (experience_bank.py) — output dataclass
  ExperienceBank private helpers — _health_to_range, _action_to_focus, _cosine_similarity
"""

import sys


import hashlib

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# infer_round_phase
# ---------------------------------------------------------------------------
class TestInferRoundPhase:
    """Tests for the shared round-phase utility."""

    def _infer(self, tick_data):
        from Programma_CS2_RENAN.backend.knowledge.round_utils import infer_round_phase
        return infer_round_phase(tick_data)

    def test_pistol_round(self):
        assert self._infer({"equipment_value": 800}) == "pistol"

    def test_pistol_boundary(self):
        assert self._infer({"equipment_value": 1499}) == "pistol"

    def test_eco_round(self):
        assert self._infer({"equipment_value": 2000}) == "eco"

    def test_eco_boundary(self):
        assert self._infer({"equipment_value": 2999}) == "eco"

    def test_force_round(self):
        assert self._infer({"equipment_value": 3500}) == "force"

    def test_force_boundary(self):
        assert self._infer({"equipment_value": 3999}) == "force"

    def test_full_buy(self):
        assert self._infer({"equipment_value": 5000}) == "full_buy"

    def test_full_buy_at_threshold(self):
        assert self._infer({"equipment_value": 4000}) == "full_buy"

    def test_zero_equipment(self):
        assert self._infer({"equipment_value": 0}) == "pistol"

    def test_missing_equipment_key(self):
        """Missing equipment_value defaults to 0 → pistol."""
        assert self._infer({}) == "pistol"

    def test_non_dict_input(self):
        """Non-dict input → full_buy fallback."""
        assert self._infer("invalid") == "full_buy"
        assert self._infer(None) == "full_buy"
        assert self._infer(42) == "full_buy"

    def test_empty_dict(self):
        assert self._infer({}) == "pistol"

    def test_exact_thresholds(self):
        """Test exact boundary values (1500, 3000, 4000)."""
        assert self._infer({"equipment_value": 1500}) == "eco"
        assert self._infer({"equipment_value": 3000}) == "force"
        assert self._infer({"equipment_value": 4000}) == "full_buy"


# ---------------------------------------------------------------------------
# ExperienceContext
# ---------------------------------------------------------------------------
class TestExperienceContext:
    """Tests for ExperienceContext dataclass."""

    def _make_ctx(self, **kwargs):
        from Programma_CS2_RENAN.backend.knowledge.experience_bank import ExperienceContext
        defaults = {
            "map_name": "de_mirage",
            "round_phase": "full_buy",
            "side": "CT",
        }
        defaults.update(kwargs)
        return ExperienceContext(**defaults)

    def test_to_query_string_basic(self):
        ctx = self._make_ctx()
        qs = ctx.to_query_string()
        assert "de_mirage" in qs
        assert "CT-side" in qs
        assert "full_buy" in qs
        assert "5v5" in qs

    def test_to_query_string_with_position(self):
        ctx = self._make_ctx(position_area="A-site")
        qs = ctx.to_query_string()
        assert "A-site" in qs

    def test_to_query_string_no_position(self):
        ctx = self._make_ctx(position_area=None)
        qs = ctx.to_query_string()
        # Should not contain None or empty area
        assert "None" not in qs

    def test_to_query_string_damaged_health(self):
        ctx = self._make_ctx(health_range="damaged")
        qs = ctx.to_query_string()
        assert "damaged health" in qs

    def test_to_query_string_full_health_omitted(self):
        ctx = self._make_ctx(health_range="full")
        qs = ctx.to_query_string()
        assert "health" not in qs

    def test_to_query_string_custom_alive_counts(self):
        ctx = self._make_ctx(teammates_alive=2, enemies_alive=3)
        qs = ctx.to_query_string()
        assert "2v3" in qs

    def test_compute_hash_deterministic(self):
        ctx1 = self._make_ctx()
        ctx2 = self._make_ctx()
        assert ctx1.compute_hash() == ctx2.compute_hash()

    def test_compute_hash_length(self):
        ctx = self._make_ctx()
        h = ctx.compute_hash()
        assert len(h) == 16

    def test_compute_hash_hex_string(self):
        ctx = self._make_ctx()
        h = ctx.compute_hash()
        # Must be valid hex
        int(h, 16)

    def test_compute_hash_differs_by_map(self):
        ctx1 = self._make_ctx(map_name="de_mirage")
        ctx2 = self._make_ctx(map_name="de_dust2")
        assert ctx1.compute_hash() != ctx2.compute_hash()

    def test_compute_hash_differs_by_side(self):
        ctx1 = self._make_ctx(side="CT")
        ctx2 = self._make_ctx(side="T")
        assert ctx1.compute_hash() != ctx2.compute_hash()

    def test_compute_hash_differs_by_phase(self):
        ctx1 = self._make_ctx(round_phase="pistol")
        ctx2 = self._make_ctx(round_phase="eco")
        assert ctx1.compute_hash() != ctx2.compute_hash()

    def test_compute_hash_includes_position(self):
        ctx1 = self._make_ctx(position_area="A-site")
        ctx2 = self._make_ctx(position_area="B-site")
        assert ctx1.compute_hash() != ctx2.compute_hash()

    def test_compute_hash_none_position(self):
        ctx = self._make_ctx(position_area=None)
        h = ctx.compute_hash()
        # Hash key uses "unknown" for None position
        expected_key = "de_mirage:CT:full_buy:unknown"
        expected_hash = hashlib.sha256(expected_key.encode()).hexdigest()[:16]
        assert h == expected_hash

    def test_defaults(self):
        from Programma_CS2_RENAN.backend.knowledge.experience_bank import ExperienceContext
        ctx = ExperienceContext(map_name="de_inferno", round_phase="eco", side="T")
        assert ctx.position_area is None
        assert ctx.health_range == "full"
        assert ctx.equipment_tier == "full"
        assert ctx.teammates_alive == 5
        assert ctx.enemies_alive == 5


# ---------------------------------------------------------------------------
# SynthesizedAdvice
# ---------------------------------------------------------------------------
class TestSynthesizedAdvice:
    """Tests for the SynthesizedAdvice output dataclass."""

    def test_creation(self):
        from Programma_CS2_RENAN.backend.knowledge.experience_bank import SynthesizedAdvice
        advice = SynthesizedAdvice(
            narrative="Test narrative",
            pro_references=["s1mple (held_angle -> kill)"],
            confidence=0.85,
            focus_area="positioning",
            experiences_used=5,
        )
        assert advice.narrative == "Test narrative"
        assert len(advice.pro_references) == 1
        assert advice.confidence == 0.85
        assert advice.focus_area == "positioning"
        assert advice.experiences_used == 5

    def test_empty_references(self):
        from Programma_CS2_RENAN.backend.knowledge.experience_bank import SynthesizedAdvice
        advice = SynthesizedAdvice(
            narrative="No refs",
            pro_references=[],
            confidence=0.0,
            focus_area="general",
            experiences_used=0,
        )
        assert advice.pro_references == []
        assert advice.experiences_used == 0


# ---------------------------------------------------------------------------
# ExperienceBank private helpers (tested via isolated instances)
# ---------------------------------------------------------------------------
class TestExperienceBankHelpers:
    """Tests for ExperienceBank private helper methods without DB/embedder deps."""

    def _make_bank_shell(self):
        """Create a minimal ExperienceBank without real DB or embedder init."""
        from Programma_CS2_RENAN.backend.knowledge.experience_bank import ExperienceBank
        bank = ExperienceBank.__new__(ExperienceBank)
        return bank

    def test_health_to_range_full(self):
        bank = self._make_bank_shell()
        assert bank._health_to_range(100) == "full"
        assert bank._health_to_range(80) == "full"

    def test_health_to_range_damaged(self):
        bank = self._make_bank_shell()
        assert bank._health_to_range(79) == "damaged"
        assert bank._health_to_range(40) == "damaged"

    def test_health_to_range_critical(self):
        bank = self._make_bank_shell()
        assert bank._health_to_range(39) == "critical"
        assert bank._health_to_range(1) == "critical"
        assert bank._health_to_range(0) == "critical"

    def test_action_to_focus_mapping(self):
        bank = self._make_bank_shell()
        assert bank._action_to_focus("pushed") == "aggression"
        assert bank._action_to_focus("held_angle") == "positioning"
        assert bank._action_to_focus("scoped_hold") == "aim"
        assert bank._action_to_focus("crouch_peek") == "movement"
        assert bank._action_to_focus("used_utility") == "utility"
        assert bank._action_to_focus("rotated") == "game_sense"

    def test_action_to_focus_unknown(self):
        bank = self._make_bank_shell()
        assert bank._action_to_focus("unknown_action") == "positioning"

    def test_infer_action_scoped(self):
        bank = self._make_bank_shell()
        tick = {"is_scoped": True}
        assert bank._infer_action(tick, is_victim=False) == "scoped_hold"

    def test_infer_action_crouching(self):
        bank = self._make_bank_shell()
        tick = {"is_crouching": True}
        assert bank._infer_action(tick, is_victim=False) == "crouch_peek"

    def test_infer_action_default_attacker(self):
        bank = self._make_bank_shell()
        tick = {}
        assert bank._infer_action(tick, is_victim=False) == "pushed"

    def test_infer_action_default_victim(self):
        bank = self._make_bank_shell()
        tick = {}
        assert bank._infer_action(tick, is_victim=True) == "held_angle"

    def test_cosine_similarity_identical(self):
        bank = self._make_bank_shell()
        v = np.array([1.0, 2.0, 3.0])
        sim = bank._cosine_similarity(v, v)
        assert abs(sim - 1.0) < 1e-6

    def test_cosine_similarity_orthogonal(self):
        bank = self._make_bank_shell()
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        sim = bank._cosine_similarity(a, b)
        assert abs(sim) < 1e-6

    def test_cosine_similarity_opposite(self):
        bank = self._make_bank_shell()
        a = np.array([1.0, 0.0])
        b = np.array([-1.0, 0.0])
        sim = bank._cosine_similarity(a, b)
        assert abs(sim - (-1.0)) < 1e-6

    def test_cosine_similarity_zero_vector(self):
        bank = self._make_bank_shell()
        a = np.array([1.0, 2.0])
        b = np.array([0.0, 0.0])
        sim = bank._cosine_similarity(a, b)
        assert sim == 0.0

    def test_infer_round_phase_delegate(self):
        """_infer_round_phase should delegate to round_utils."""
        bank = self._make_bank_shell()
        assert bank._infer_round_phase({"equipment_value": 800}) == "pistol"
        assert bank._infer_round_phase({"equipment_value": 5000}) == "full_buy"
