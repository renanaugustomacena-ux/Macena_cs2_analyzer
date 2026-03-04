"""
Tests for SkillLatentModel and SkillAxes.

Verifies skill vector calculation, curriculum level mapping, and tensor output
using fields that actually feed into calculate_skill_vector.
"""

import sys


import pytest
import torch

from Programma_CS2_RENAN.backend.nn.rap_coach.skill_model import SkillAxes, SkillLatentModel
from Programma_CS2_RENAN.backend.storage.db_models import PlayerMatchStats


class TestSkillAxes:
    def test_all_returns_five_axes(self):
        axes = SkillAxes.all()
        assert len(axes) == 5
        assert SkillAxes.MECHANICS in axes
        assert SkillAxes.POSITIONING in axes
        assert SkillAxes.UTILITY in axes
        assert SkillAxes.TIMING in axes
        assert SkillAxes.DECISION in axes


class TestSkillVectorLowPerformance:
    def test_low_mechanics(self):
        """Poor accuracy + avg_hs → low MECHANICS score."""
        stats = PlayerMatchStats(
            player_name="LowMech",
            demo_name="test_low_mech.dem",
            accuracy=0.10,
            avg_hs=0.05,
        )
        vec = SkillLatentModel.calculate_skill_vector(stats)
        if SkillAxes.MECHANICS in vec:
            assert (
                vec[SkillAxes.MECHANICS] < 0.4
            ), f"MECHANICS should be low for accuracy=0.10, avg_hs=0.05, got {vec[SkillAxes.MECHANICS]}"

    def test_low_utility(self):
        """Very low utility stats → low UTILITY score or absent axis.

        Note: get_z treats 0.0 as 'unavailable' (not val), so we use small
        non-zero values for a genuine low score, and test 0.0 separately.
        """
        stats = PlayerMatchStats(
            player_name="LowUtil",
            demo_name="test_low_util.dem",
            utility_blind_time=0.5,
            utility_enemies_blinded=0.1,
        )
        vec = SkillLatentModel.calculate_skill_vector(stats)
        if SkillAxes.UTILITY in vec:
            assert vec[SkillAxes.UTILITY] < 0.5

    def test_zero_utility_treated_as_absent(self):
        """Exactly 0.0 utility is treated as unavailable data by get_z."""
        stats = PlayerMatchStats(
            player_name="ZeroUtil",
            demo_name="test_zero_util.dem",
            utility_blind_time=0.0,
            utility_enemies_blinded=0.0,
        )
        vec = SkillLatentModel.calculate_skill_vector(stats)
        # 0.0 values → get_z returns None → axis absent or at fallback 0.5
        if SkillAxes.UTILITY in vec:
            assert vec[SkillAxes.UTILITY] == pytest.approx(0.5, abs=0.01)

    def test_low_timing(self):
        """Very low timing stats → low TIMING score."""
        stats = PlayerMatchStats(
            player_name="LowTime",
            demo_name="test_low_time.dem",
            opening_duel_win_pct=0.01,
            positional_aggression_score=0.01,
        )
        vec = SkillLatentModel.calculate_skill_vector(stats)
        if SkillAxes.TIMING in vec:
            assert vec[SkillAxes.TIMING] < 0.5

    def test_low_decision(self):
        """Very low decision stats → low DECISION score."""
        stats = PlayerMatchStats(
            player_name="LowDec",
            demo_name="test_low_dec.dem",
            clutch_win_pct=0.01,
            rating_impact=0.01,
        )
        vec = SkillLatentModel.calculate_skill_vector(stats)
        if SkillAxes.DECISION in vec:
            assert vec[SkillAxes.DECISION] < 0.5

    def test_low_positioning(self):
        """Very low survival and kast → low POSITIONING score."""
        stats = PlayerMatchStats(
            player_name="LowPos",
            demo_name="test_low_pos.dem",
            rating_survival=0.01,
            rating_kast=0.01,
        )
        vec = SkillLatentModel.calculate_skill_vector(stats)
        if SkillAxes.POSITIONING in vec:
            assert vec[SkillAxes.POSITIONING] < 0.5


class TestSkillVectorProPerformance:
    def test_pro_level_produces_high_skill(self):
        """Very high stats across all axes → high curriculum level."""
        stats = PlayerMatchStats(
            player_name="GoatPlayer",
            demo_name="test_high.dem",
            accuracy=0.45,
            avg_hs=0.75,
            rating_survival=1.5,
            rating_kast=1.3,
            utility_blind_time=30.0,
            utility_enemies_blinded=5.0,
            opening_duel_win_pct=0.75,
            positional_aggression_score=1.5,
            clutch_win_pct=0.60,
            rating_impact=1.5,
        )
        vec = SkillLatentModel.calculate_skill_vector(stats)
        level = SkillLatentModel.get_curriculum_level(vec)
        assert level >= 7, f"Pro-level stats should yield level >=7, got {level}"

    def test_pro_has_all_five_axes(self):
        """Pro stats providing all axis inputs should populate all 5 axes."""
        stats = PlayerMatchStats(
            player_name="FullPro",
            demo_name="test_full.dem",
            accuracy=0.40,
            avg_hs=0.60,
            rating_survival=1.2,
            rating_kast=1.1,
            utility_blind_time=25.0,
            utility_enemies_blinded=4.0,
            opening_duel_win_pct=0.65,
            positional_aggression_score=1.2,
            clutch_win_pct=0.45,
            rating_impact=1.3,
        )
        vec = SkillLatentModel.calculate_skill_vector(stats)
        for ax in SkillAxes.all():
            assert ax in vec, f"Axis {ax} missing from skill vector"
            assert 0.0 <= vec[ax] <= 1.0, f"Axis {ax} out of range: {vec[ax]}"


class TestCurriculumLevel:
    def test_boundaries_clamped(self):
        """Level is always clamped between 1 and 10."""
        vec_max = {ax: 2.0 for ax in SkillAxes.all()}
        assert SkillLatentModel.get_curriculum_level(vec_max) == 10

        vec_min = {ax: -1.0 for ax in SkillAxes.all()}
        assert SkillLatentModel.get_curriculum_level(vec_min) == 1

    def test_empty_vector_returns_one(self):
        """Empty skill vector → level 1."""
        assert SkillLatentModel.get_curriculum_level({}) == 1

    def test_mid_range_level(self):
        """Skill vector around 0.5 → level ~5."""
        vec_mid = {ax: 0.5 for ax in SkillAxes.all()}
        level = SkillLatentModel.get_curriculum_level(vec_mid)
        assert 4 <= level <= 6, f"Mid-range vector should give level 4-6, got {level}"


class TestSkillTensor:
    def test_tensor_shape(self):
        """Skill tensor is [1, 10] one-hot."""
        vec = {ax: 0.5 for ax in SkillAxes.all()}
        tensor = SkillLatentModel.get_skill_tensor(vec)
        assert tensor.shape == (1, 10)
        assert tensor.sum().item() == pytest.approx(1.0)

    def test_tensor_one_hot_position(self):
        """One-hot position corresponds to curriculum level."""
        vec = {ax: 0.5 for ax in SkillAxes.all()}
        level = SkillLatentModel.get_curriculum_level(vec)
        tensor = SkillLatentModel.get_skill_tensor(vec)
        assert tensor[0, level - 1].item() == 1.0
        # All other positions should be 0
        for i in range(10):
            if i != level - 1:
                assert tensor[0, i].item() == 0.0

