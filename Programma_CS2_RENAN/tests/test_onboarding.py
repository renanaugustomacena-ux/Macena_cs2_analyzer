"""
Tests for UserOnboardingManager state machine.

Tests the stage determination logic directly with controlled scalar inputs
(protocol-compliant pure-formula tests) and the real DB integration path.
"""

import sys


import pytest

from Programma_CS2_RENAN.backend.onboarding.new_user_flow import (
    OnboardingStage,
    UserOnboardingManager,
    get_onboarding_manager,
)


class TestOnboardingStageDetermination:
    """Pure-function tests for _determine_stage() with scalar inputs."""

    def test_zero_demos_awaiting(self):
        manager = UserOnboardingManager()
        assert manager._determine_stage(0) == OnboardingStage.AWAITING_FIRST_DEMO

    def test_one_demo_building_baseline(self):
        manager = UserOnboardingManager()
        assert manager._determine_stage(1) == OnboardingStage.BUILDING_BASELINE

    def test_two_demos_building_baseline(self):
        manager = UserOnboardingManager()
        assert manager._determine_stage(2) == OnboardingStage.BUILDING_BASELINE

    def test_three_demos_coach_ready(self):
        manager = UserOnboardingManager()
        assert manager._determine_stage(3) == OnboardingStage.COACH_READY

    def test_many_demos_coach_ready(self):
        manager = UserOnboardingManager()
        assert manager._determine_stage(100) == OnboardingStage.COACH_READY


class TestOnboardingStatusFields:
    """Verify OnboardingStatus field computation from real DB state."""

    def test_status_fields_coherent(self):
        """get_status() fields must be internally consistent with the stage."""
        manager = get_onboarding_manager()
        status = manager.get_status("test_user")

        # Fields must be populated
        assert status.stage in (
            OnboardingStage.AWAITING_FIRST_DEMO,
            OnboardingStage.BUILDING_BASELINE,
            OnboardingStage.COACH_READY,
        )
        assert status.demos_uploaded >= 0
        assert status.demos_required == 1
        assert status.demos_recommended == 3
        assert isinstance(status.message, str)
        assert len(status.message) > 0

        # coach_ready and baseline_stable must be consistent with demos_uploaded
        assert status.coach_ready == (status.demos_uploaded >= 1)
        assert status.baseline_stable == (status.demos_uploaded >= 3)


class TestOnboardingCacheInvalidation:
    """Verify cache invalidation doesn't crash."""

    def test_invalidate_specific_user(self):
        manager = get_onboarding_manager()
        manager.get_status("cache_test_user")
        manager.invalidate_cache("cache_test_user")
        # Second call should re-query DB without error
        status = manager.get_status("cache_test_user")
        assert status.stage is not None

    def test_invalidate_all(self):
        manager = get_onboarding_manager()
        manager.get_status("user_a")
        manager.get_status("user_b")
        manager.invalidate_cache()  # clear all
        status = manager.get_status("user_a")
        assert status.stage is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
