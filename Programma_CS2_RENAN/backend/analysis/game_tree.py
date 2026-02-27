"""
Recursive Expectiminimax Trees (Phase 6: Game Theory)

Implements a game tree search that models CS2 round-level strategy as a
sequential decision process with chance nodes (opponent unknown actions).

Governance: Rule 1 §8.1 (Game-theoretic foundations), Rule 2 §9.1 (Bounded computation)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.analysis.game_tree")

# Available tactical actions per node type
_MAX_ACTIONS = ["push", "hold", "rotate", "use_utility"]
_MIN_ACTIONS = ["push", "hold", "rotate", "use_utility"]

# Cold-start defaults only. OpponentModel learns adaptive priors via
# EMA blending once >= 10 rounds of data are available per profile.
_DEFAULT_OPPONENT_PROBS: Dict[str, float] = {
    "push": 0.30,
    "hold": 0.40,
    "rotate": 0.20,
    "use_utility": 0.10,
}

# Computation budget
DEFAULT_NODE_BUDGET = 1000


class OpponentModel:
    """
    Adaptive opponent modeling for game tree search.

    Learns opponent action distributions from context:
    - Economy-based priors (eco rounds are aggressive, full-buys are balanced)
    - Side adjustments (T-side opponents push more, CT-side hold more)
    - Player advantage adjustments
    - Time pressure adjustments

    Falls back to _DEFAULT_OPPONENT_PROBS when no context is available.
    """

    _ECONOMY_PRIORS: Dict[str, Dict[str, float]] = {
        "eco": {"push": 0.50, "hold": 0.15, "rotate": 0.10, "use_utility": 0.25},
        "force": {"push": 0.40, "hold": 0.25, "rotate": 0.15, "use_utility": 0.20},
        "full_buy": {"push": 0.25, "hold": 0.35, "rotate": 0.25, "use_utility": 0.15},
    }

    _SIDE_ADJUSTMENTS: Dict[str, Dict[str, float]] = {
        "T": {"push": 0.05, "hold": -0.05, "rotate": 0.0, "use_utility": 0.0},
        "CT": {"push": -0.05, "hold": 0.05, "rotate": 0.0, "use_utility": 0.0},
    }

    def __init__(self):
        self._learned_profiles: Dict[str, Dict[str, float]] = {}
        self._learned_counts: Dict[str, int] = {}

    def get_opponent_probs(
        self,
        game_state: Dict,
        map_name: Optional[str] = None,
    ) -> Dict[str, float]:
        """Get context-adapted opponent probabilities."""
        # Start with economy-based priors
        economy_tier = self._classify_economy(game_state)
        base_probs = dict(self._ECONOMY_PRIORS.get(economy_tier, _DEFAULT_OPPONENT_PROBS))

        # Apply side adjustments (opponent is on the OTHER side)
        is_ct = game_state.get("is_ct", True)
        opponent_side = "T" if is_ct else "CT"
        for action, adj in self._SIDE_ADJUSTMENTS.get(opponent_side, {}).items():
            base_probs[action] = max(0.01, base_probs.get(action, 0) + adj)

        # Player advantage adjustments
        alive = game_state.get("alive_players", 5)
        enemy = game_state.get("enemy_alive", 5)
        if enemy < alive:
            base_probs["hold"] += 0.10
            base_probs["push"] -= 0.05
            base_probs["rotate"] += 0.05
            base_probs["use_utility"] -= 0.10
        elif enemy > alive:
            base_probs["push"] += 0.10
            base_probs["hold"] -= 0.05

        # Time pressure
        time_remaining = game_state.get("time_remaining", 115)
        if time_remaining < 30:
            base_probs["push"] += 0.15
            base_probs["hold"] -= 0.10
            base_probs["use_utility"] += 0.05

        # Blend with learned profile if available
        if map_name:
            profile_key = f"{map_name}:{economy_tier}"
            learned = self._learned_profiles.get(profile_key)
            count = self._learned_counts.get(profile_key, 0)
            if learned and count >= 10:
                blend_weight = min(count / 100, 0.7)
                for action in base_probs:
                    learned_val = learned.get(action, 0.25)
                    base_probs[action] = (
                        base_probs[action] * (1 - blend_weight) + learned_val * blend_weight
                    )

        # Normalize
        total = sum(max(0.01, v) for v in base_probs.values())
        return {k: max(0.01, v) / total for k, v in base_probs.items()}

    def learn_from_match(self, match_events: List[Dict], map_name: str) -> None:
        """Update opponent model from observed match events."""
        action_counts: Dict[str, Dict[str, int]] = {}

        for event in match_events:
            economy_tier = self._classify_economy(event)
            if economy_tier not in action_counts:
                action_counts[economy_tier] = {a: 0 for a in _MAX_ACTIONS}

            action = self._infer_action_from_event(event)
            if action in action_counts[economy_tier]:
                action_counts[economy_tier][action] += 1

        for econ_tier, counts in action_counts.items():
            total = sum(counts.values())
            if total < 5:
                continue

            probs = {a: c / total for a, c in counts.items()}
            profile_key = f"{map_name}:{econ_tier}"

            if profile_key in self._learned_profiles:
                existing = self._learned_profiles[profile_key]
                old_count = self._learned_counts.get(profile_key, 0)
                alpha = min(total / (total + old_count), 0.5)
                for a in probs:
                    existing[a] = existing.get(a, 0.25) * (1 - alpha) + probs[a] * alpha
                self._learned_counts[profile_key] = old_count + total
            else:
                self._learned_profiles[profile_key] = probs
                self._learned_counts[profile_key] = total

        logger.info(
            "Opponent model updated from %s: %s economy tiers", map_name, len(action_counts)
        )

    def _classify_economy(self, state: Dict) -> str:
        enemy_econ = state.get("enemy_economy", 4000)
        if enemy_econ < 2000:
            return "eco"
        elif enemy_econ < 4000:
            return "force"
        return "full_buy"

    def _infer_action_from_event(self, event: Dict) -> str:
        event_type = event.get("event_type", "")
        if event_type in ("first_kill", "entry_frag"):
            return "push"
        elif event_type in ("flash_thrown", "smoke_thrown", "molotov_thrown"):
            return "use_utility"
        elif event_type == "rotation_detected":
            return "rotate"
        return "hold"


@dataclass
class GameNode:
    """A node in the expectiminimax game tree."""

    node_type: str  # "max" (our team), "min" (opponent), "chance" (stochastic)
    state: Dict  # Game state snapshot
    children: List[GameNode] = field(default_factory=list)
    value: Optional[float] = None
    action: Optional[str] = None  # Action that led to this node

    @property
    def is_leaf(self) -> bool:
        return len(self.children) == 0


class ExpectiminimaxSearch:
    """
    Game tree search engine with expectiminimax evaluation.

    Models CS2 round strategy as alternating max (our team) and min (opponent)
    layers with chance nodes for stochastic outcomes. Uses the existing
    WinProbabilityPredictor for leaf evaluation.
    """

    def __init__(
        self,
        node_budget: int = DEFAULT_NODE_BUDGET,
        opponent_probs: Optional[Dict[str, float]] = None,
        opponent_model: Optional[OpponentModel] = None,
        map_name: Optional[str] = None,
    ):
        self.node_budget = node_budget
        self._static_opponent_probs = opponent_probs or dict(_DEFAULT_OPPONENT_PROBS)
        self._opponent_model = opponent_model
        self._map_name = map_name
        self._nodes_created = 0
        self._predictor = None

    @property
    def opponent_probs(self) -> Dict[str, float]:
        """Backward-compatible property returning static probs."""
        return self._static_opponent_probs

    def _get_predictor(self):
        """Lazy-load WinProbabilityPredictor to avoid circular imports."""
        if self._predictor is None:
            from Programma_CS2_RENAN.backend.analysis.win_probability import get_win_predictor

            self._predictor = get_win_predictor()
        return self._predictor

    def build_tree(self, initial_state: Dict, depth: int = 3) -> GameNode:
        """
        Build a game tree from the initial state to the given depth.

        Args:
            initial_state: Game state dict with keys matching GameState fields
                (team_economy, enemy_economy, alive_players, enemy_alive, etc.).
            depth: Maximum tree depth (alternating max/min/chance layers).

        Returns:
            Root GameNode with children populated.
        """
        self._nodes_created = 0
        root = GameNode(node_type="max", state=initial_state)
        self._expand(root, depth, is_max=True)
        return root

    def _expand(self, node: GameNode, depth: int, is_max: bool) -> None:
        """Recursively expand the tree."""
        if depth <= 0 or self._nodes_created >= self.node_budget:
            return

        actions = _MAX_ACTIONS if is_max else _MIN_ACTIONS

        for action in actions:
            if self._nodes_created >= self.node_budget:
                break

            child_state = self._apply_action(node.state, action, is_max)
            self._nodes_created += 1

            if is_max:
                # Our action leads to a chance node (opponent response uncertain)
                chance = GameNode(node_type="chance", state=child_state, action=action)
                node.children.append(chance)
                self._expand_chance(chance, depth - 1)
            else:
                # Opponent action leads back to our turn (max node)
                child = GameNode(
                    node_type="max",
                    state=child_state,
                    action=action,
                )
                node.children.append(child)
                self._expand(child, depth - 1, is_max=True)

    def _expand_chance(self, node: GameNode, depth: int) -> None:
        """Expand a chance node with probabilistic opponent responses."""
        if depth <= 0 or self._nodes_created >= self.node_budget:
            return

        # Use adaptive opponent model if available, else static probs
        if self._opponent_model:
            probs = self._opponent_model.get_opponent_probs(node.state, map_name=self._map_name)
        else:
            probs = self._static_opponent_probs

        for action, prob in probs.items():
            if self._nodes_created >= self.node_budget:
                break

            child_state = self._apply_action(node.state, action, is_max=False)
            child = GameNode(node_type="max", state=child_state, action=action)
            # NOTE: value temporarily holds opponent probability here; overwritten by minimax evaluation
            child.value = prob
            node.children.append(child)
            self._nodes_created += 1
            self._expand(child, depth - 1, is_max=True)

    def _apply_action(self, state: Dict, action: str, is_max: bool) -> Dict:
        """
        Apply an action to produce a new game state.

        Simplified state transitions that model the general effect of each action.
        """
        new_state = dict(state)

        # DESIGN: push is modeled as symmetric (both sides lose 1 player + map shift).
        # CS2 reality has aggressor advantage (peekers) vs crosshair advantage (defenders).
        # This simplification is acceptable — WinProbabilityPredictor at leaf nodes
        # provides the fine-grained asymmetric correction.
        if action == "push":
            # Aggressive: may gain map control but risks players
            if is_max:
                new_state["alive_players"] = max(0, new_state.get("alive_players", 5) - 1)
                new_state["enemy_alive"] = max(0, new_state.get("enemy_alive", 5) - 1)
                new_state["map_control_pct"] = min(
                    1.0, new_state.get("map_control_pct", 0.5) + 0.15
                )
            else:
                new_state["enemy_alive"] = max(0, new_state.get("enemy_alive", 5) - 1)
                new_state["alive_players"] = max(0, new_state.get("alive_players", 5) - 1)
                new_state["map_control_pct"] = max(
                    0.0, new_state.get("map_control_pct", 0.5) - 0.15
                )

        elif action == "hold":
            # Passive: use time, maintain position
            new_state["time_remaining"] = max(0, new_state.get("time_remaining", 115) - 15)

        elif action == "rotate":
            # Reposition: costs time, changes map control
            new_state["time_remaining"] = max(0, new_state.get("time_remaining", 115) - 10)
            shift = 0.1 if is_max else -0.1
            new_state["map_control_pct"] = max(
                0.0, min(1.0, new_state.get("map_control_pct", 0.5) + shift)
            )

        elif action == "use_utility":
            # Utility: reduces enemy utility, gains temporary advantage
            new_state["utility_remaining"] = max(0, new_state.get("utility_remaining", 4) - 1)
            new_state["map_control_pct"] = min(1.0, new_state.get("map_control_pct", 0.5) + 0.05)

        return new_state

    def evaluate(self, node: GameNode) -> float:
        """
        Recursively evaluate the tree using expectiminimax.

        Returns:
            Utility value in [0, 1] representing estimated win probability.
        """
        if node.is_leaf:
            return self._evaluate_leaf(node.state)

        if node.node_type == "max":
            return max(self.evaluate(c) for c in node.children)
        elif node.node_type == "min":
            return min(self.evaluate(c) for c in node.children)
        elif node.node_type == "chance":
            # Weighted expectation using opponent probabilities
            if self._opponent_model:
                probs = self._opponent_model.get_opponent_probs(node.state, map_name=self._map_name)
            else:
                probs = self._static_opponent_probs

            total = 0.0
            prob_sum = 0.0
            for child in node.children:
                action = child.action
                prob = probs.get(action, 0.25)
                total += prob * self.evaluate(child)
                prob_sum += prob
            return total / max(prob_sum, 1e-6)

        return 0.5

    def _evaluate_leaf(self, state: Dict) -> float:
        """Evaluate a leaf node using WinProbabilityPredictor."""
        try:
            predictor = self._get_predictor()
            prob, _ = predictor.predict_from_dict(state)
            return prob
        except Exception:
            # Fallback heuristic
            alive = state.get("alive_players", 5)
            enemy = state.get("enemy_alive", 5)
            if alive == 0:
                return 0.0
            if enemy == 0:
                return 1.0
            return alive / (alive + enemy)

    def evaluate_single_action(self, state: Dict, action: str) -> float:
        """
        Public API: evaluate a single action from the given game state.

        Replaces direct calls to the private _apply_action / _evaluate_leaf
        methods from external modules (F4-03). Using the public wrapper means
        external callers are insulated from internal refactors of those private
        methods.

        Args:
            state: Current game state dict.
            action: One of "push", "hold", "rotate", "use_utility".

        Returns:
            Estimated win probability [0, 1] for this action.
        """
        new_state = self._apply_action(state, action, is_max=True)
        return self._evaluate_leaf(new_state)

    def get_best_action(self, root: GameNode) -> Tuple[str, float]:
        """
        Return the action with the highest evaluated utility from root.

        Args:
            root: Root GameNode (must be evaluated or will be evaluated here).

        Returns:
            (best_action_name, utility_value)
        """
        if not root.children:
            return ("hold", 0.5)

        best_value = -1.0
        best_action = "hold"

        for child in root.children:
            val = self.evaluate(child)
            action_name = child.action or "hold"
            if val > best_value:
                best_value = val
                best_action = action_name

        return (best_action, best_value)

    def suggest_strategy(self, game_state: Dict, map_name: Optional[str] = None) -> str:
        """
        Build tree, evaluate, and return natural-language recommendation.

        Args:
            game_state: Dict with keys matching GameState fields.
            map_name: Optional map name for context-aware opponent modeling.

        Returns:
            Strategy recommendation string.
        """
        if map_name:
            self._map_name = map_name

        root = self.build_tree(game_state, depth=3)
        action, value = self.get_best_action(root)

        confidence = abs(value - 0.5) * 2  # 0 at 50/50, 1 at extremes

        action_descriptions = {
            "push": "Push aggressively to take map control",
            "hold": "Hold your current position and play for time",
            "rotate": "Rotate to a different angle or site",
            "use_utility": "Deploy utility to gain information or deny area",
        }

        desc = action_descriptions.get(action, action)
        conf_label = "high" if confidence > 0.6 else "moderate" if confidence > 0.3 else "marginal"
        model_label = "adaptive" if self._opponent_model else "static"

        return (
            f"Recommended: {desc} "
            f"(win probability: {value:.0%}, confidence: {conf_label}, "
            f"opponent model: {model_label}). "
            f"Tree explored {self._nodes_created} game states."
        )


def get_game_tree_search(
    map_name: Optional[str] = None,
    use_adaptive: bool = True,
) -> ExpectiminimaxSearch:
    """Factory function with optional adaptive opponent model."""
    opponent_model = OpponentModel() if use_adaptive else None
    return ExpectiminimaxSearch(
        opponent_model=opponent_model,
        map_name=map_name,
    )
