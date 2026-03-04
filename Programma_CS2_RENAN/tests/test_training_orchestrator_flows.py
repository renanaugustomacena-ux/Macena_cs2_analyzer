"""
Tests for training_orchestrator.py — Training targets, map resolution,
tactical classification, batch preparation, and training flow edge cases.

Complements test_training_orchestrator_logic.py (init, early stopping,
empty batch handling, deterministic RNG).

CI-portable: uses mocks for external dependencies.
"""

import sys


from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import torch


def _make_orchestrator(model_type="jepa", **kwargs):
    """Create a TrainingOrchestrator with mocked device and manager."""
    with patch(
        "Programma_CS2_RENAN.backend.nn.training_orchestrator.get_device",
        return_value=torch.device("cpu"),
    ):
        from Programma_CS2_RENAN.backend.nn.training_orchestrator import (
            TrainingOrchestrator,
        )

        manager = MagicMock()
        return TrainingOrchestrator(manager, model_type=model_type, **kwargs)


# ===========================================================================
# _resolve_map_name
# ===========================================================================


class TestResolveMapName:
    """Tests for _resolve_map_name — static method for map name resolution."""

    def test_from_metadata(self):
        from Programma_CS2_RENAN.backend.nn.training_orchestrator import (
            TrainingOrchestrator,
        )

        match_mgr = MagicMock()
        meta = SimpleNamespace(map_name="de_inferno")
        match_mgr.get_metadata.return_value = meta
        cache = {}

        result = TrainingOrchestrator._resolve_map_name(1, "demo.dem", match_mgr, cache)
        assert result == "de_inferno"

    def test_from_metadata_adds_de_prefix(self):
        from Programma_CS2_RENAN.backend.nn.training_orchestrator import (
            TrainingOrchestrator,
        )

        match_mgr = MagicMock()
        meta = SimpleNamespace(map_name="mirage")
        match_mgr.get_metadata.return_value = meta
        cache = {}

        result = TrainingOrchestrator._resolve_map_name(1, "demo.dem", match_mgr, cache)
        assert result == "de_mirage"

    def test_from_demo_name_pattern(self):
        from Programma_CS2_RENAN.backend.nn.training_orchestrator import (
            TrainingOrchestrator,
        )

        result = TrainingOrchestrator._resolve_map_name(None, "faze_vs_navi_dust2.dem", None, {})
        assert result == "de_dust2"

    def test_from_demo_name_case_insensitive(self):
        from Programma_CS2_RENAN.backend.nn.training_orchestrator import (
            TrainingOrchestrator,
        )

        result = TrainingOrchestrator._resolve_map_name(None, "MATCH_INFERNO_2024.dem", None, {})
        assert result == "de_inferno"

    def test_fallback_to_mirage(self):
        from Programma_CS2_RENAN.backend.nn.training_orchestrator import (
            TrainingOrchestrator,
        )

        result = TrainingOrchestrator._resolve_map_name(None, "unknown_demo.dem", None, {})
        assert result == "de_mirage"

    def test_metadata_cache_prevents_requery(self):
        from Programma_CS2_RENAN.backend.nn.training_orchestrator import (
            TrainingOrchestrator,
        )

        match_mgr = MagicMock()
        meta = SimpleNamespace(map_name="de_nuke")
        match_mgr.get_metadata.return_value = meta
        cache = {}

        # First call populates cache
        TrainingOrchestrator._resolve_map_name(1, "demo.dem", match_mgr, cache)
        # Second call should use cache (get_metadata NOT called again)
        match_mgr.get_metadata.reset_mock()
        TrainingOrchestrator._resolve_map_name(1, "demo.dem", match_mgr, cache)
        match_mgr.get_metadata.assert_not_called()

    def test_metadata_exception_falls_back_to_demo_name(self):
        from Programma_CS2_RENAN.backend.nn.training_orchestrator import (
            TrainingOrchestrator,
        )

        match_mgr = MagicMock()
        match_mgr.get_metadata.side_effect = RuntimeError("DB error")
        cache = {}

        result = TrainingOrchestrator._resolve_map_name(1, "match_ancient.dem", match_mgr, cache)
        assert result == "de_ancient"

    def test_all_known_maps_detected(self):
        from Programma_CS2_RENAN.backend.nn.training_orchestrator import (
            TrainingOrchestrator,
        )

        known_maps = ["mirage", "inferno", "dust2", "ancient", "nuke", "anubis", "overpass", "vertigo"]
        for m in known_maps:
            result = TrainingOrchestrator._resolve_map_name(None, f"demo_{m}_2024.dem", None, {})
            assert result == f"de_{m}", f"Failed to detect {m}"


# ===========================================================================
# _compute_advantage
# ===========================================================================


class TestComputeAdvantage:
    """Tests for _compute_advantage — continuous advantage [0, 1]."""

    def _make_player(self, team, health=100, equip=4000, is_alive=True):
        return SimpleNamespace(
            team=team, health=health, equipment_value=equip, is_alive=is_alive
        )

    def test_balanced_returns_around_half(self):
        from Programma_CS2_RENAN.backend.nn.training_orchestrator import (
            TrainingOrchestrator,
        )

        players = [
            self._make_player("CT", 100, 4000),
            self._make_player("CT", 100, 4000),
            self._make_player("T", 100, 4000),
            self._make_player("T", 100, 4000),
        ]
        adv = TrainingOrchestrator._compute_advantage(players, "CT", bomb_planted=False)
        assert 0.45 <= adv <= 0.55, f"Balanced game should be ~0.5, got {adv}"

    def test_numerical_advantage_increases_score(self):
        from Programma_CS2_RENAN.backend.nn.training_orchestrator import (
            TrainingOrchestrator,
        )

        players = [
            self._make_player("CT", 100, 4000),
            self._make_player("CT", 100, 4000),
            self._make_player("CT", 100, 4000),
            self._make_player("T", 100, 4000),
        ]
        adv = TrainingOrchestrator._compute_advantage(players, "CT", bomb_planted=False)
        assert adv > 0.55, f"3v1 should be > 0.55, got {adv}"

    def test_numerical_disadvantage_decreases_score(self):
        from Programma_CS2_RENAN.backend.nn.training_orchestrator import (
            TrainingOrchestrator,
        )

        players = [
            self._make_player("CT", 100, 4000),
            self._make_player("T", 100, 4000),
            self._make_player("T", 100, 4000),
            self._make_player("T", 100, 4000),
        ]
        adv = TrainingOrchestrator._compute_advantage(players, "CT", bomb_planted=False)
        assert adv < 0.45, f"1v3 should be < 0.45, got {adv}"

    def test_bomb_planted_advantage_for_t(self):
        from Programma_CS2_RENAN.backend.nn.training_orchestrator import (
            TrainingOrchestrator,
        )

        players = [
            self._make_player("CT", 100, 4000),
            self._make_player("T", 100, 4000),
        ]
        adv_no_bomb = TrainingOrchestrator._compute_advantage(players, "T", bomb_planted=False)
        adv_bomb = TrainingOrchestrator._compute_advantage(players, "T", bomb_planted=True)
        assert adv_bomb > adv_no_bomb, "Bomb planted should increase T advantage"

    def test_bomb_planted_disadvantage_for_ct(self):
        from Programma_CS2_RENAN.backend.nn.training_orchestrator import (
            TrainingOrchestrator,
        )

        players = [
            self._make_player("CT", 100, 4000),
            self._make_player("T", 100, 4000),
        ]
        adv_no_bomb = TrainingOrchestrator._compute_advantage(players, "CT", bomb_planted=False)
        adv_bomb = TrainingOrchestrator._compute_advantage(players, "CT", bomb_planted=True)
        assert adv_bomb < adv_no_bomb, "Bomb planted should decrease CT advantage"

    def test_dead_players_not_counted(self):
        from Programma_CS2_RENAN.backend.nn.training_orchestrator import (
            TrainingOrchestrator,
        )

        players = [
            self._make_player("CT", 100, 4000, is_alive=True),
            self._make_player("T", 100, 4000, is_alive=False),  # Dead
        ]
        adv = TrainingOrchestrator._compute_advantage(players, "CT", bomb_planted=False)
        # CT has 1 alive, T has 0 alive → strong advantage for CT
        assert adv > 0.6, f"1v0 should be strong advantage, got {adv}"

    def test_result_always_in_0_1_range(self):
        from Programma_CS2_RENAN.backend.nn.training_orchestrator import (
            TrainingOrchestrator,
        )

        # Extreme case: 5v0
        players = [self._make_player("CT", 100, 10000) for _ in range(5)]
        adv = TrainingOrchestrator._compute_advantage(players, "CT", bomb_planted=False)
        assert 0.0 <= adv <= 1.0

        # Extreme case: 0v5
        players = [self._make_player("T", 100, 10000) for _ in range(5)]
        adv = TrainingOrchestrator._compute_advantage(players, "CT", bomb_planted=True)
        assert 0.0 <= adv <= 1.0

    def test_no_players_returns_safe_value(self):
        from Programma_CS2_RENAN.backend.nn.training_orchestrator import (
            TrainingOrchestrator,
        )

        adv = TrainingOrchestrator._compute_advantage([], "CT", bomb_planted=False)
        assert 0.0 <= adv <= 1.0


# ===========================================================================
# _classify_tactical_role
# ===========================================================================


class TestClassifyTacticalRole:
    """Tests for _classify_tactical_role — heuristic role classification."""

    def _make_item(self, team="CT", equipment_value=4000, is_crouching=False):
        return SimpleNamespace(
            team=team, equipment_value=equipment_value, is_crouching=is_crouching
        )

    def test_save_on_low_equipment(self):
        orch = _make_orchestrator()
        item = self._make_item(equipment_value=500)
        role = orch._classify_tactical_role(item, knowledge=None, all_players=[])
        assert role == orch.ROLE_SAVE

    def test_ct_default_passive_hold(self):
        orch = _make_orchestrator()
        item = self._make_item(team="CT", equipment_value=4000)
        role = orch._classify_tactical_role(item, knowledge=None, all_players=[])
        assert role == orch.ROLE_PASSIVE_HOLD

    def test_t_default_site_take(self):
        orch = _make_orchestrator()
        item = self._make_item(team="T", equipment_value=4000)
        role = orch._classify_tactical_role(item, knowledge=None, all_players=[])
        assert role == orch.ROLE_SITE_TAKE

    def test_ct_retake_on_bomb_planted(self):
        orch = _make_orchestrator()
        item = self._make_item(team="CT", equipment_value=4000)
        knowledge = SimpleNamespace(
            bomb_planted=True,
            visible_enemy_count=0,
            teammate_positions=[],
            visible_enemies=[],
        )
        role = orch._classify_tactical_role(item, knowledge=knowledge, all_players=[])
        assert role == orch.ROLE_RETAKE

    def test_lurk_when_far_from_team(self):
        orch = _make_orchestrator()
        item = self._make_item(team="T", equipment_value=4000)
        knowledge = SimpleNamespace(
            bomb_planted=False,
            visible_enemy_count=0,
            teammate_positions=[
                SimpleNamespace(distance=2000.0),
                SimpleNamespace(distance=2500.0),
            ],
            visible_enemies=[],
        )
        role = orch._classify_tactical_role(item, knowledge=knowledge, all_players=[])
        assert role == orch.ROLE_LURK

    def test_entry_frag_close_enemy(self):
        orch = _make_orchestrator()
        item = self._make_item(team="T", equipment_value=4000)
        knowledge = SimpleNamespace(
            bomb_planted=False,
            visible_enemy_count=1,
            teammate_positions=[],
            visible_enemies=[SimpleNamespace(distance=500.0)],
        )
        role = orch._classify_tactical_role(item, knowledge=knowledge, all_players=[])
        assert role == orch.ROLE_ENTRY_FRAG

    def test_aggressive_push_distant_enemy(self):
        orch = _make_orchestrator()
        item = self._make_item(team="T", equipment_value=4000)
        knowledge = SimpleNamespace(
            bomb_planted=False,
            visible_enemy_count=1,
            teammate_positions=[],
            visible_enemies=[SimpleNamespace(distance=1500.0)],
        )
        role = orch._classify_tactical_role(item, knowledge=knowledge, all_players=[])
        assert role == orch.ROLE_AGGRESSIVE_PUSH

    def test_ct_anchor_when_crouching(self):
        orch = _make_orchestrator()
        item = self._make_item(team="CT", equipment_value=4000, is_crouching=True)
        knowledge = SimpleNamespace(
            bomb_planted=False,
            visible_enemy_count=0,
            teammate_positions=[],
            visible_enemies=[],
        )
        role = orch._classify_tactical_role(item, knowledge=knowledge, all_players=[])
        assert role == orch.ROLE_ANCHOR

    def test_support_near_teammates(self):
        orch = _make_orchestrator()
        item = self._make_item(team="T", equipment_value=4000)
        knowledge = SimpleNamespace(
            bomb_planted=False,
            visible_enemy_count=0,
            teammate_positions=[
                SimpleNamespace(distance=300.0),
                SimpleNamespace(distance=400.0),
            ],
            visible_enemies=[],
        )
        role = orch._classify_tactical_role(item, knowledge=knowledge, all_players=[])
        assert role == orch.ROLE_SUPPORT

    def test_role_always_in_valid_range(self):
        orch = _make_orchestrator()
        # Test all combinations
        for team in ["CT", "T"]:
            for equip in [500, 4000]:
                for crouch in [True, False]:
                    item = self._make_item(team=team, equipment_value=equip, is_crouching=crouch)
                    role = orch._classify_tactical_role(item, knowledge=None, all_players=[])
                    assert 0 <= role <= 9, f"Role {role} out of range for {team}/{equip}/{crouch}"


# ===========================================================================
# _fetch_batches
# ===========================================================================


class TestFetchBatches:
    """Tests for _fetch_batches — data fetching and batching."""

    def test_returns_correct_number_of_batches(self):
        orch = _make_orchestrator(batch_size=4)
        orch.manager._fetch_jepa_ticks.return_value = list(range(10))
        batches = orch._fetch_batches(is_train=True)
        # 10 items / 4 batch_size = 3 batches (4, 4, 2)
        assert len(batches) == 3
        assert len(batches[0]) == 4
        assert len(batches[-1]) == 2

    def test_uses_train_split_when_is_train(self):
        orch = _make_orchestrator()
        orch.manager._fetch_jepa_ticks.return_value = []
        orch._fetch_batches(is_train=True)
        orch.manager._fetch_jepa_ticks.assert_called_with(is_pro=True, split="train")

    def test_uses_val_split_when_not_train(self):
        orch = _make_orchestrator()
        orch.manager._fetch_jepa_ticks.return_value = []
        orch._fetch_batches(is_train=False)
        orch.manager._fetch_jepa_ticks.assert_called_with(is_pro=True, split="val")


# ===========================================================================
# _prepare_tensor_batch — JEPA path
# ===========================================================================


class TestPrepareTensorBatchJEPA:
    """Tests for _prepare_tensor_batch JEPA path."""

    def _make_tick_items(self, n=10):
        """Create mock PlayerTickState-like items for FeatureExtractor."""
        items = []
        for i in range(n):
            items.append(
                SimpleNamespace(
                    tick=i,
                    player_name="TestPlayer",
                    demo_name="test.dem",
                    pos_x=100.0 + i,
                    pos_y=200.0,
                    pos_z=0.0,
                    view_x=0.0,
                    view_y=0.0,
                    health=100,
                    armor=100,
                    has_helmet=True,
                    has_defuser=False,
                    equipment_value=4750,
                    is_crouching=False,
                    is_scoped=False,
                    is_blinded=False,
                    enemies_visible=0,
                    active_weapon="ak47",
                    team="T",
                    round_time=60.0,
                    round_number=1,
                    bomb_planted=False,
                    teammates_alive=4,
                    enemies_alive=5,
                    team_economy=20000,
                    match_id=None,
                )
            )
        return items

    def test_jepa_batch_returns_correct_keys(self):
        orch = _make_orchestrator(model_type="jepa")
        items = self._make_tick_items(10)
        result = orch._prepare_tensor_batch(items)
        assert result is not None
        assert "context" in result
        assert "target" in result
        assert "negatives" in result

    def test_jepa_batch_context_shape(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM

        orch = _make_orchestrator(model_type="jepa")
        items = self._make_tick_items(10)
        result = orch._prepare_tensor_batch(items)
        assert result["context"].shape == (1, 10, METADATA_DIM)

    def test_jepa_batch_target_shape(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM

        orch = _make_orchestrator(model_type="jepa")
        items = self._make_tick_items(10)
        result = orch._prepare_tensor_batch(items)
        assert result["target"].shape == (1, METADATA_DIM)

    def test_jepa_batch_negatives_shape(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM

        orch = _make_orchestrator(model_type="jepa")
        items = self._make_tick_items(10)
        result = orch._prepare_tensor_batch(items)
        assert result["negatives"].shape == (1, 5, METADATA_DIM)

    def test_jepa_batch_too_small_returns_none(self):
        """Batch with < 5 items can't produce negatives → returns None."""
        orch = _make_orchestrator(model_type="jepa")
        items = self._make_tick_items(3)
        result = orch._prepare_tensor_batch(items)
        assert result is None

    def test_jepa_context_padded_when_small(self):
        from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM

        orch = _make_orchestrator(model_type="jepa")
        items = self._make_tick_items(6)
        result = orch._prepare_tensor_batch(items)
        assert result is not None
        # Context should be padded to 10
        assert result["context"].shape == (1, 10, METADATA_DIM)


# ===========================================================================
# run_training edge cases
# ===========================================================================


class TestRunTrainingEdgeCases:
    """Tests for run_training edge cases."""

    def test_aborts_when_no_training_data(self):
        """run_training should exit gracefully when no data is available."""
        orch = _make_orchestrator(model_type="jepa")
        orch.manager._fetch_jepa_ticks.return_value = []

        # Mock model and trainer to avoid real PyTorch initialization
        mock_model = MagicMock()
        mock_model.to.return_value = mock_model
        mock_trainer = MagicMock()
        orch.TrainerClass = MagicMock(return_value=mock_trainer)

        with patch(
            "Programma_CS2_RENAN.backend.nn.factory.ModelFactory"
        ) as mock_factory:
            mock_factory.get_model.return_value = mock_model
            with patch(
                "Programma_CS2_RENAN.backend.nn.training_orchestrator.load_nn"
            ):
                with patch(
                    "Programma_CS2_RENAN.backend.nn.training_orchestrator.save_nn"
                ):
                    orch.run_training()  # Should not crash

    def test_report_progress_delegates_to_manager(self):
        orch = _make_orchestrator(model_type="jepa", max_epochs=50)
        orch._report_progress(5, 0.1234, 0.0567)
        orch.manager._update_state.assert_called_once()
        call_args = orch.manager._update_state.call_args
        assert call_args[0][0] == "Training"
        assert "5/50" in call_args[0][1]


# ===========================================================================
# Weight constants and role indices
# ===========================================================================


class TestConstants:
    """Verify training orchestrator constants are valid."""

    def test_advantage_weights_sum_to_one(self):
        from Programma_CS2_RENAN.backend.nn.training_orchestrator import (
            TrainingOrchestrator,
        )

        total = (
            TrainingOrchestrator._ADV_W_ALIVE
            + TrainingOrchestrator._ADV_W_HP
            + TrainingOrchestrator._ADV_W_EQUIP
            + TrainingOrchestrator._ADV_W_BOMB
        )
        assert total == pytest.approx(1.0), f"Advantage weights sum to {total}, expected 1.0"

    def test_role_indices_unique_and_contiguous(self):
        from Programma_CS2_RENAN.backend.nn.training_orchestrator import (
            TrainingOrchestrator,
        )

        roles = [
            TrainingOrchestrator.ROLE_SITE_TAKE,
            TrainingOrchestrator.ROLE_ROTATION,
            TrainingOrchestrator.ROLE_ENTRY_FRAG,
            TrainingOrchestrator.ROLE_SUPPORT,
            TrainingOrchestrator.ROLE_ANCHOR,
            TrainingOrchestrator.ROLE_LURK,
            TrainingOrchestrator.ROLE_RETAKE,
            TrainingOrchestrator.ROLE_SAVE,
            TrainingOrchestrator.ROLE_AGGRESSIVE_PUSH,
            TrainingOrchestrator.ROLE_PASSIVE_HOLD,
        ]
        assert sorted(roles) == list(range(10)), "Role indices should be 0-9 contiguous"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
