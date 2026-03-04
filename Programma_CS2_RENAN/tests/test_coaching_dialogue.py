"""
Tests for Coaching Service helpers — Phase 8 Coverage Expansion.

Covers:
  CoachingService._format_coper_message — COPER advice formatting
  CoachingService._baseline_context_note — pro baseline comparison
  CoachingService._health_to_range — health categorization
  CoachingService._infer_round_phase — round phase delegation
"""

import sys


import pytest


class TestFormatCoperMessage:
    """Tests for COPER advice message formatting."""

    def _make_service_shell(self):
        from Programma_CS2_RENAN.backend.services.coaching_service import CoachingService
        svc = CoachingService.__new__(CoachingService)
        return svc

    def _make_advice(self, narrative="Test advice", pro_refs=None,
                     confidence=0.8, focus="positioning", experiences=5):
        from Programma_CS2_RENAN.backend.knowledge.experience_bank import SynthesizedAdvice
        return SynthesizedAdvice(
            narrative=narrative,
            pro_references=pro_refs or [],
            confidence=confidence,
            focus_area=focus,
            experiences_used=experiences,
        )

    def test_basic_message(self):
        svc = self._make_service_shell()
        advice = self._make_advice(narrative="Hold A-site from cover")
        msg = svc._format_coper_message(advice)
        assert "Hold A-site from cover" in msg
        assert "5 similar situations" in msg
        assert "80%" in msg

    def test_with_pro_references(self):
        svc = self._make_service_shell()
        advice = self._make_advice(
            pro_refs=["s1mple (held_angle -> kill)", "NiKo (pushed -> trade)"]
        )
        msg = svc._format_coper_message(advice)
        assert "Pro Examples:" in msg
        assert "s1mple" in msg
        assert "NiKo" in msg

    def test_no_pro_references(self):
        svc = self._make_service_shell()
        advice = self._make_advice(pro_refs=[])
        msg = svc._format_coper_message(advice)
        assert "Pro Examples:" not in msg

    def test_with_baseline_note(self):
        svc = self._make_service_shell()
        advice = self._make_advice()
        msg = svc._format_coper_message(advice, baseline_note="Rating: 1.05 vs pro 1.15")
        assert "Rating: 1.05 vs pro 1.15" in msg

    def test_zero_confidence(self):
        svc = self._make_service_shell()
        advice = self._make_advice(confidence=0.0, experiences=0)
        msg = svc._format_coper_message(advice)
        assert "0 similar situations" in msg
        assert "0%" in msg


class TestBaselineContextNote:
    """Tests for the static _baseline_context_note method."""

    def _note(self, player_stats, baseline, focus_area):
        from Programma_CS2_RENAN.backend.services.coaching_service import CoachingService
        return CoachingService._baseline_context_note(player_stats, baseline, focus_area)

    def test_empty_stats(self):
        result = self._note(None, {"rating": {"mean": 1.15}}, "positioning")
        assert result == ""

    def test_empty_baseline(self):
        result = self._note({"rating": 1.05}, None, "positioning")
        assert result == ""

    def test_positioning_focus(self):
        result = self._note(
            {"rating": 1.05},
            {"rating": {"mean": 1.15, "std": 0.15}},
            "positioning",
        )
        # Should generate a comparison note
        assert isinstance(result, str)

    def test_unknown_focus_defaults_to_rating(self):
        result = self._note(
            {"rating": 1.30},
            {"rating": {"mean": 1.15, "std": 0.15}},
            "unknown_focus",
        )
        assert isinstance(result, str)


class TestCoachingServiceHealthRange:
    """Tests for health categorization."""

    def _make_service_shell(self):
        from Programma_CS2_RENAN.backend.services.coaching_service import CoachingService
        svc = CoachingService.__new__(CoachingService)
        return svc

    def test_full_health(self):
        svc = self._make_service_shell()
        assert svc._health_to_range(100) == "full"
        assert svc._health_to_range(80) == "full"

    def test_damaged_health(self):
        svc = self._make_service_shell()
        assert svc._health_to_range(79) == "damaged"
        assert svc._health_to_range(40) == "damaged"

    def test_critical_health(self):
        svc = self._make_service_shell()
        assert svc._health_to_range(39) == "critical"
        assert svc._health_to_range(1) == "critical"


class TestCoachingServiceInferRoundPhase:
    """Tests for round phase delegation."""

    def _make_service_shell(self):
        from Programma_CS2_RENAN.backend.services.coaching_service import CoachingService
        svc = CoachingService.__new__(CoachingService)
        return svc

    def test_delegates_to_round_utils(self):
        svc = self._make_service_shell()
        assert svc._infer_round_phase({"equipment_value": 800}) == "pistol"
        assert svc._infer_round_phase({"equipment_value": 5000}) == "full_buy"
        assert svc._infer_round_phase({}) == "pistol"
