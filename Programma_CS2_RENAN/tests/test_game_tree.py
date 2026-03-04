"""
Tests for Game Tree Search — Phase 15 Coverage Expansion.

Covers:
  OpponentModel — economy priors, side adjustments, player advantage, time pressure, learning
  GameNode — dataclass, is_leaf property
  ExpectiminimaxSearch — build_tree, evaluate, get_best_action, suggest_strategy, apply_action
  get_game_tree_search — factory function
"""

import sys




# ---------------------------------------------------------------------------
# OpponentModel
# ---------------------------------------------------------------------------
class TestOpponentModelEconomy:
    """Tests for economy-based priors in OpponentModel."""

    def _make(self):
        from Programma_CS2_RENAN.backend.analysis.game_tree import OpponentModel
        return OpponentModel()

    def test_eco_round_favors_push(self):
        om = self._make()
        probs = om.get_opponent_probs({"enemy_economy": 1000})
        assert probs["push"] > probs["hold"]

    def test_full_buy_favors_hold(self):
        om = self._make()
        probs = om.get_opponent_probs({"enemy_economy": 5000})
        assert probs["hold"] > probs["use_utility"]

    def test_force_buy_intermediate(self):
        om = self._make()
        probs = om.get_opponent_probs({"enemy_economy": 3000})
        # Force buy should have push > hold (aggressive but not as much as eco)
        assert probs["push"] > probs["use_utility"]

    def test_classify_economy_eco(self):
        om = self._make()
        assert om._classify_economy({"enemy_economy": 500}) == "eco"
        assert om._classify_economy({"enemy_economy": 1999}) == "eco"

    def test_classify_economy_force(self):
        om = self._make()
        assert om._classify_economy({"enemy_economy": 2000}) == "force"
        assert om._classify_economy({"enemy_economy": 3999}) == "force"

    def test_classify_economy_full_buy(self):
        om = self._make()
        assert om._classify_economy({"enemy_economy": 4000}) == "full_buy"
        assert om._classify_economy({"enemy_economy": 10000}) == "full_buy"

    def test_classify_economy_default(self):
        om = self._make()
        # Missing key defaults to 4000 → full_buy
        assert om._classify_economy({}) == "full_buy"


class TestOpponentModelSideAdjustments:
    """Tests for side-based adjustments."""

    def _make(self):
        from Programma_CS2_RENAN.backend.analysis.game_tree import OpponentModel
        return OpponentModel()

    def test_ct_side_opponent_is_t(self):
        """When player is CT, opponent is T → push boost."""
        om = self._make()
        ct_probs = om.get_opponent_probs({"enemy_economy": 5000, "is_ct": True})
        t_probs = om.get_opponent_probs({"enemy_economy": 5000, "is_ct": False})
        # T-side opponent pushes more than CT-side opponent
        assert ct_probs["push"] > t_probs["push"]

    def test_t_side_opponent_is_ct(self):
        """When player is T, opponent is CT → hold boost."""
        om = self._make()
        probs = om.get_opponent_probs({"enemy_economy": 5000, "is_ct": False})
        # CT opponent holds more
        assert probs["hold"] > 0


class TestOpponentModelPlayerAdvantage:
    """Tests for player count adjustments."""

    def _make(self):
        from Programma_CS2_RENAN.backend.analysis.game_tree import OpponentModel
        return OpponentModel()

    def test_enemy_disadvantage_holds_more(self):
        """Outnumbered enemy holds more."""
        om = self._make()
        base = om.get_opponent_probs({"enemy_economy": 5000, "alive_players": 5, "enemy_alive": 5})
        outnumbered = om.get_opponent_probs({"enemy_economy": 5000, "alive_players": 5, "enemy_alive": 3})
        assert outnumbered["hold"] > base["hold"]

    def test_enemy_advantage_pushes_more(self):
        """Enemy with more players pushes more."""
        om = self._make()
        base = om.get_opponent_probs({"enemy_economy": 5000, "alive_players": 5, "enemy_alive": 5})
        advantage = om.get_opponent_probs({"enemy_economy": 5000, "alive_players": 3, "enemy_alive": 5})
        assert advantage["push"] > base["push"]


class TestOpponentModelTimePressure:
    """Tests for time pressure adjustments."""

    def _make(self):
        from Programma_CS2_RENAN.backend.analysis.game_tree import OpponentModel
        return OpponentModel()

    def test_low_time_pushes_more(self):
        om = self._make()
        normal = om.get_opponent_probs({"enemy_economy": 5000, "time_remaining": 90})
        low_time = om.get_opponent_probs({"enemy_economy": 5000, "time_remaining": 15})
        assert low_time["push"] > normal["push"]

    def test_low_time_holds_less(self):
        om = self._make()
        normal = om.get_opponent_probs({"enemy_economy": 5000, "time_remaining": 90})
        low_time = om.get_opponent_probs({"enemy_economy": 5000, "time_remaining": 15})
        assert low_time["hold"] < normal["hold"]


class TestOpponentModelNormalization:
    """Tests for probability normalization."""

    def _make(self):
        from Programma_CS2_RENAN.backend.analysis.game_tree import OpponentModel
        return OpponentModel()

    def test_probs_sum_to_one(self):
        om = self._make()
        for state in [
            {"enemy_economy": 1000},
            {"enemy_economy": 5000, "is_ct": True, "time_remaining": 10},
            {"enemy_economy": 3000, "alive_players": 2, "enemy_alive": 5},
        ]:
            probs = om.get_opponent_probs(state)
            assert abs(sum(probs.values()) - 1.0) < 1e-6

    def test_all_probs_positive(self):
        om = self._make()
        probs = om.get_opponent_probs({"enemy_economy": 5000, "alive_players": 1, "enemy_alive": 5})
        for v in probs.values():
            assert v > 0

    def test_four_actions(self):
        om = self._make()
        probs = om.get_opponent_probs({})
        assert set(probs.keys()) == {"push", "hold", "rotate", "use_utility"}


class TestOpponentModelLearning:
    """Tests for learn_from_match and learned profile blending."""

    def _make(self):
        from Programma_CS2_RENAN.backend.analysis.game_tree import OpponentModel
        return OpponentModel()

    def test_learn_from_match_stores_profiles(self):
        om = self._make()
        events = [
            {"enemy_economy": 5000, "event_type": "first_kill"},
            {"enemy_economy": 5000, "event_type": "first_kill"},
            {"enemy_economy": 5000, "event_type": "smoke_thrown"},
            {"enemy_economy": 5000, "event_type": "rotation_detected"},
            {"enemy_economy": 5000, "event_type": "round_end"},
            {"enemy_economy": 5000, "event_type": "round_end"},
        ]
        om.learn_from_match(events, "de_dust2")
        assert "de_dust2:full_buy" in om._learned_profiles

    def test_learn_from_match_ignores_small_samples(self):
        om = self._make()
        events = [
            {"enemy_economy": 5000, "event_type": "first_kill"},
            {"enemy_economy": 5000, "event_type": "smoke_thrown"},
        ]
        om.learn_from_match(events, "de_mirage")
        # Only 2 events < 5 threshold → no profile stored
        assert "de_mirage:full_buy" not in om._learned_profiles

    def test_learned_profile_blends_after_threshold(self):
        om = self._make()
        # Feed enough events to reach blend threshold (count >= 10)
        events = [{"enemy_economy": 5000, "event_type": "first_kill"} for _ in range(15)]
        om.learn_from_match(events, "de_inferno")
        assert om._learned_counts.get("de_inferno:full_buy", 0) >= 10

        # Now query with map_name → should blend
        probs_with_map = om.get_opponent_probs({"enemy_economy": 5000}, map_name="de_inferno")
        probs_without = om.get_opponent_probs({"enemy_economy": 5000})
        # With learned profile (all pushes), push should be higher
        assert probs_with_map["push"] > probs_without["push"]

    def test_learn_updates_existing_profile(self):
        om = self._make()
        events1 = [{"enemy_economy": 5000, "event_type": "first_kill"} for _ in range(10)]
        om.learn_from_match(events1, "de_dust2")
        count1 = om._learned_counts["de_dust2:full_buy"]

        events2 = [{"enemy_economy": 5000, "event_type": "smoke_thrown"} for _ in range(10)]
        om.learn_from_match(events2, "de_dust2")
        count2 = om._learned_counts["de_dust2:full_buy"]
        assert count2 > count1

    def test_infer_action_from_event_push(self):
        om = self._make()
        assert om._infer_action_from_event({"event_type": "first_kill"}) == "push"
        assert om._infer_action_from_event({"event_type": "entry_frag"}) == "push"

    def test_infer_action_from_event_utility(self):
        om = self._make()
        assert om._infer_action_from_event({"event_type": "flash_thrown"}) == "use_utility"
        assert om._infer_action_from_event({"event_type": "smoke_thrown"}) == "use_utility"
        assert om._infer_action_from_event({"event_type": "molotov_thrown"}) == "use_utility"

    def test_infer_action_from_event_rotate(self):
        om = self._make()
        assert om._infer_action_from_event({"event_type": "rotation_detected"}) == "rotate"

    def test_infer_action_from_event_default(self):
        om = self._make()
        assert om._infer_action_from_event({"event_type": "round_end"}) == "hold"
        assert om._infer_action_from_event({}) == "hold"


# ---------------------------------------------------------------------------
# GameNode
# ---------------------------------------------------------------------------
class TestGameNode:
    """Tests for the GameNode dataclass."""

    def test_creation(self):
        from Programma_CS2_RENAN.backend.analysis.game_tree import GameNode
        node = GameNode(node_type="max", state={"alive_players": 5})
        assert node.node_type == "max"
        assert node.state["alive_players"] == 5
        assert node.children == []
        assert node.value is None
        assert node.action is None

    def test_is_leaf_no_children(self):
        from Programma_CS2_RENAN.backend.analysis.game_tree import GameNode
        node = GameNode(node_type="max", state={})
        assert node.is_leaf is True

    def test_is_leaf_with_children(self):
        from Programma_CS2_RENAN.backend.analysis.game_tree import GameNode
        child = GameNode(node_type="chance", state={})
        parent = GameNode(node_type="max", state={}, children=[child])
        assert parent.is_leaf is False


# ---------------------------------------------------------------------------
# ExpectiminimaxSearch — Tree Building
# ---------------------------------------------------------------------------
class TestExpectiminimaxBuildTree:
    """Tests for tree construction."""

    def _make_search(self, **kwargs):
        from Programma_CS2_RENAN.backend.analysis.game_tree import ExpectiminimaxSearch
        return ExpectiminimaxSearch(**kwargs)

    def test_build_tree_returns_root(self):
        search = self._make_search(node_budget=500)
        state = {"alive_players": 5, "enemy_alive": 5, "enemy_economy": 4000}
        root = search.build_tree(state, depth=2)
        assert root.node_type == "max"
        assert not root.is_leaf

    def test_build_tree_depth_zero(self):
        search = self._make_search(node_budget=500)
        root = search.build_tree({}, depth=0)
        assert root.is_leaf

    def test_build_tree_respects_budget(self):
        search = self._make_search(node_budget=10)
        root = search.build_tree({"enemy_economy": 4000}, depth=5)
        assert search._nodes_created <= 10

    def test_build_tree_root_has_children(self):
        search = self._make_search(node_budget=500)
        root = search.build_tree({"enemy_economy": 4000}, depth=2)
        # Root is max → children are chance nodes
        assert len(root.children) > 0
        for child in root.children:
            assert child.node_type == "chance"
            assert child.action is not None


# ---------------------------------------------------------------------------
# ExpectiminimaxSearch — Action Application
# ---------------------------------------------------------------------------
class TestApplyAction:
    """Tests for _apply_action state transitions."""

    def _make_search(self):
        from Programma_CS2_RENAN.backend.analysis.game_tree import ExpectiminimaxSearch
        return ExpectiminimaxSearch()

    def test_push_reduces_players(self):
        s = self._make_search()
        state = {"alive_players": 5, "enemy_alive": 5, "map_control_pct": 0.5}
        new = s._apply_action(state, "push", is_max=True)
        assert new["alive_players"] == 4
        assert new["enemy_alive"] == 4
        assert new["map_control_pct"] > 0.5

    def test_push_opponent_reduces_map_control(self):
        s = self._make_search()
        state = {"alive_players": 5, "enemy_alive": 5, "map_control_pct": 0.5}
        new = s._apply_action(state, "push", is_max=False)
        assert new["map_control_pct"] < 0.5

    def test_hold_reduces_time(self):
        s = self._make_search()
        state = {"time_remaining": 100}
        new = s._apply_action(state, "hold", is_max=True)
        assert new["time_remaining"] == 85

    def test_hold_time_clamped_at_zero(self):
        s = self._make_search()
        state = {"time_remaining": 5}
        new = s._apply_action(state, "hold", is_max=True)
        assert new["time_remaining"] == 0

    def test_rotate_changes_map_control(self):
        s = self._make_search()
        state = {"time_remaining": 100, "map_control_pct": 0.5}
        new_max = s._apply_action(state, "rotate", is_max=True)
        new_min = s._apply_action(state, "rotate", is_max=False)
        assert new_max["map_control_pct"] > 0.5
        assert new_min["map_control_pct"] < 0.5

    def test_use_utility_reduces_utility(self):
        s = self._make_search()
        state = {"utility_remaining": 4, "map_control_pct": 0.5}
        new = s._apply_action(state, "use_utility", is_max=True)
        assert new["utility_remaining"] == 3
        assert new["map_control_pct"] > 0.5

    def test_push_clamps_alive_at_zero(self):
        s = self._make_search()
        state = {"alive_players": 0, "enemy_alive": 0, "map_control_pct": 0.5}
        new = s._apply_action(state, "push", is_max=True)
        assert new["alive_players"] == 0
        assert new["enemy_alive"] == 0

    def test_does_not_mutate_original(self):
        s = self._make_search()
        state = {"alive_players": 5, "enemy_alive": 5, "map_control_pct": 0.5}
        s._apply_action(state, "push", is_max=True)
        assert state["alive_players"] == 5  # Original unchanged

    def test_map_control_clamped_0_1(self):
        s = self._make_search()
        state = {"map_control_pct": 0.98}
        new = s._apply_action(state, "use_utility", is_max=True)
        assert new["map_control_pct"] <= 1.0

        state2 = {"map_control_pct": 0.05, "time_remaining": 100}
        new2 = s._apply_action(state2, "rotate", is_max=False)
        assert new2["map_control_pct"] >= 0.0


# ---------------------------------------------------------------------------
# ExpectiminimaxSearch — Evaluation
# ---------------------------------------------------------------------------
class TestEvaluate:
    """Tests for tree evaluation with fallback heuristic."""

    def _make_search(self):
        from Programma_CS2_RENAN.backend.analysis.game_tree import ExpectiminimaxSearch
        return ExpectiminimaxSearch(node_budget=200)

    def test_evaluate_leaf_all_enemy_dead(self):
        s = self._make_search()
        val = s._evaluate_leaf({"alive_players": 3, "enemy_alive": 0})
        assert val == 1.0

    def test_evaluate_leaf_all_team_dead(self):
        s = self._make_search()
        val = s._evaluate_leaf({"alive_players": 0, "enemy_alive": 3})
        assert val == 0.0

    def test_evaluate_leaf_bounded(self):
        s = self._make_search()
        val = s._evaluate_leaf({"alive_players": 5, "enemy_alive": 5})
        assert 0.0 <= val <= 1.0

    def test_evaluate_leaf_advantage_higher(self):
        """More alive players should yield higher win probability."""
        s = self._make_search()
        val_even = s._evaluate_leaf({"alive_players": 3, "enemy_alive": 3})
        val_advantage = s._evaluate_leaf({"alive_players": 5, "enemy_alive": 1})
        assert val_advantage > val_even

    def test_evaluate_returns_float(self):
        s = self._make_search()
        root = s.build_tree({"alive_players": 5, "enemy_alive": 5, "enemy_economy": 4000}, depth=2)
        val = s.evaluate(root)
        assert isinstance(val, float)
        assert 0.0 <= val <= 1.0

    def test_evaluate_single_action(self):
        s = self._make_search()
        state = {"alive_players": 5, "enemy_alive": 5, "map_control_pct": 0.5}
        val = s.evaluate_single_action(state, "push")
        assert isinstance(val, float)
        assert 0.0 <= val <= 1.0

    def test_evaluate_single_action_hold(self):
        s = self._make_search()
        state = {"alive_players": 5, "enemy_alive": 5, "time_remaining": 100}
        val = s.evaluate_single_action(state, "hold")
        assert isinstance(val, float)


# ---------------------------------------------------------------------------
# ExpectiminimaxSearch — Best Action & Strategy
# ---------------------------------------------------------------------------
class TestBestActionAndStrategy:
    """Tests for get_best_action and suggest_strategy."""

    def _make_search(self):
        from Programma_CS2_RENAN.backend.analysis.game_tree import ExpectiminimaxSearch
        return ExpectiminimaxSearch(node_budget=200)

    def test_get_best_action_returns_tuple(self):
        s = self._make_search()
        root = s.build_tree({"alive_players": 5, "enemy_alive": 5, "enemy_economy": 4000}, depth=2)
        action, value = s.get_best_action(root)
        assert isinstance(action, str)
        assert action in {"push", "hold", "rotate", "use_utility"}
        assert isinstance(value, float)

    def test_get_best_action_empty_root(self):
        from Programma_CS2_RENAN.backend.analysis.game_tree import GameNode
        s = self._make_search()
        empty_root = GameNode(node_type="max", state={})
        action, value = s.get_best_action(empty_root)
        assert action == "hold"
        assert value == 0.5

    def test_suggest_strategy_returns_string(self):
        s = self._make_search()
        state = {"alive_players": 5, "enemy_alive": 5, "enemy_economy": 4000}
        result = s.suggest_strategy(state)
        assert isinstance(result, str)
        assert "Recommended:" in result
        assert "win probability:" in result
        assert "opponent model: static" in result

    def test_suggest_strategy_with_map_name(self):
        s = self._make_search()
        state = {"alive_players": 5, "enemy_alive": 5, "enemy_economy": 4000}
        _result = s.suggest_strategy(state, map_name="de_dust2")
        assert isinstance(_result, str)
        assert s._map_name == "de_dust2"

    def test_suggest_strategy_with_adaptive_model(self):
        from Programma_CS2_RENAN.backend.analysis.game_tree import (
            ExpectiminimaxSearch,
            OpponentModel,
        )
        om = OpponentModel()
        s = ExpectiminimaxSearch(node_budget=200, opponent_model=om)
        state = {"alive_players": 5, "enemy_alive": 5, "enemy_economy": 4000}
        result = s.suggest_strategy(state)
        assert "opponent model: adaptive" in result

    def test_suggest_strategy_nodes_explored(self):
        s = self._make_search()
        state = {"alive_players": 5, "enemy_alive": 5, "enemy_economy": 4000}
        result = s.suggest_strategy(state)
        assert "game states" in result

    def test_suggest_strategy_confidence_labels(self):
        """Confidence label extraction from result string."""
        s = self._make_search()
        state = {"alive_players": 5, "enemy_alive": 5, "enemy_economy": 4000}
        result = s.suggest_strategy(state)
        # Should contain one of the confidence labels
        assert any(label in result for label in ["high", "moderate", "marginal"])


# ---------------------------------------------------------------------------
# ExpectiminimaxSearch — Opponent Probs Property
# ---------------------------------------------------------------------------
class TestOpponentProbsProperty:
    """Tests for the backward-compatible opponent_probs property."""

    def test_default_probs(self):
        from Programma_CS2_RENAN.backend.analysis.game_tree import (
            ExpectiminimaxSearch,
            _DEFAULT_OPPONENT_PROBS,
        )
        s = ExpectiminimaxSearch()
        assert s.opponent_probs == _DEFAULT_OPPONENT_PROBS

    def test_custom_probs(self):
        from Programma_CS2_RENAN.backend.analysis.game_tree import ExpectiminimaxSearch
        custom = {"push": 0.5, "hold": 0.2, "rotate": 0.2, "use_utility": 0.1}
        s = ExpectiminimaxSearch(opponent_probs=custom)
        assert s.opponent_probs == custom


# ---------------------------------------------------------------------------
# Factory Function
# ---------------------------------------------------------------------------
class TestGameTreeFactory:
    """Tests for get_game_tree_search factory."""

    def test_factory_default_adaptive(self):
        from Programma_CS2_RENAN.backend.analysis.game_tree import get_game_tree_search
        s = get_game_tree_search()
        assert s._opponent_model is not None

    def test_factory_static(self):
        from Programma_CS2_RENAN.backend.analysis.game_tree import get_game_tree_search
        s = get_game_tree_search(use_adaptive=False)
        assert s._opponent_model is None

    def test_factory_with_map(self):
        from Programma_CS2_RENAN.backend.analysis.game_tree import get_game_tree_search
        s = get_game_tree_search(map_name="de_mirage")
        assert s._map_name == "de_mirage"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
class TestGameTreeConstants:
    """Tests for module-level constants."""

    def test_default_node_budget(self):
        from Programma_CS2_RENAN.backend.analysis.game_tree import DEFAULT_NODE_BUDGET
        assert DEFAULT_NODE_BUDGET == 1000

    def test_max_actions(self):
        from Programma_CS2_RENAN.backend.analysis.game_tree import _MAX_ACTIONS
        assert set(_MAX_ACTIONS) == {"push", "hold", "rotate", "use_utility"}

    def test_default_opponent_probs_sum_to_one(self):
        from Programma_CS2_RENAN.backend.analysis.game_tree import _DEFAULT_OPPONENT_PROBS
        assert abs(sum(_DEFAULT_OPPONENT_PROBS.values()) - 1.0) < 1e-6
