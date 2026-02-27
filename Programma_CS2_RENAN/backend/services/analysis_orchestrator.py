"""
Analysis Orchestrator — Phase 6 Integration Layer

Coordinates all Phase 6 game-theory analysis modules and produces
structured coaching insights for storage in the database.

This is the bridge between the analysis engines (backend/analysis/)
and the coaching pipeline (CoachingService).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from Programma_CS2_RENAN.backend.storage.db_models import CoachingInsight
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.analysis_orchestrator")


@dataclass
class RoundAnalysis:
    """Analysis results for a single round."""

    round_number: int
    insights: List[CoachingInsight] = field(default_factory=list)


@dataclass
class MatchAnalysis:
    """Aggregated analysis results for an entire match."""

    player_name: str
    demo_name: str
    round_analyses: List[RoundAnalysis] = field(default_factory=list)
    match_insights: List[CoachingInsight] = field(default_factory=list)

    @property
    def all_insights(self) -> List[CoachingInsight]:
        result = list(self.match_insights)
        for ra in self.round_analyses:
            result.extend(ra.insights)
        return result


class AnalysisOrchestrator:
    """
    Coordinates Phase 6 analysis modules for a match/round.

    Consumes parsed demo data and produces CoachingInsight objects
    that can be stored directly in the database.
    """

    def __init__(self):
        from Programma_CS2_RENAN.backend.analysis import (
            get_blind_spot_detector,
            get_death_estimator,
            get_deception_analyzer,
            get_engagement_range_analyzer,
            get_entropy_analyzer,
            get_game_tree_search,
            get_momentum_tracker,
        )

        self.belief_estimator = get_death_estimator()
        self.deception_analyzer = get_deception_analyzer()
        self.momentum_tracker = get_momentum_tracker()
        self.entropy_analyzer = get_entropy_analyzer()
        self.game_tree = get_game_tree_search()
        self.blind_spot_detector = get_blind_spot_detector()
        self.engagement_analyzer = get_engagement_range_analyzer()

        # F5-14: per-module failure counter for observability of persistent silent failures.
        self._module_failure_counts: Dict[str, int] = {}

    def analyze_match(
        self,
        player_name: str,
        demo_name: str,
        round_outcomes: List[Dict],
        tick_data: Optional[pd.DataFrame] = None,
        game_states: Optional[List[Dict]] = None,
    ) -> MatchAnalysis:
        """
        Run full Phase 6 analysis suite on match data.

        Args:
            player_name: Player identifier.
            demo_name: Demo file name.
            round_outcomes: List of dicts with 'round_number' and 'round_won' keys.
            tick_data: Optional DataFrame with tick-level data for deception/entropy.
            game_states: Optional list of game state dicts for game tree / blind spots.

        Returns:
            MatchAnalysis with all generated insights.
        """
        analysis = MatchAnalysis(player_name=player_name, demo_name=demo_name)

        # 1. Momentum analysis (always available from round outcomes)
        momentum_insights = self._analyze_momentum(player_name, demo_name, round_outcomes)
        analysis.match_insights.extend(momentum_insights)

        # 2. Deception analysis (requires tick data)
        if tick_data is not None and not tick_data.empty:
            deception_insights = self._analyze_deception(player_name, demo_name, tick_data)
            analysis.match_insights.extend(deception_insights)

        # 3. Entropy analysis (requires tick data with utility events)
        if tick_data is not None and not tick_data.empty:
            entropy_insights = self._analyze_utility_entropy(player_name, demo_name, tick_data)
            analysis.match_insights.extend(entropy_insights)

        # 4. Game tree + blind spots (requires game states)
        if game_states:
            strategy_insights = self._analyze_strategy(player_name, demo_name, game_states)
            analysis.match_insights.extend(strategy_insights)

        # 5. Engagement range analysis (requires tick data with kill positions)
        if tick_data is not None and not tick_data.empty:
            range_insights = self._analyze_engagement_range(
                player_name,
                demo_name,
                tick_data,
            )
            analysis.match_insights.extend(range_insights)

        logger.info(
            "Analysis complete for %s on %s: %d insights generated",
            player_name,
            demo_name,
            len(analysis.all_insights),
        )
        return analysis

    def _analyze_momentum(
        self,
        player_name: str,
        demo_name: str,
        round_outcomes: List[Dict],
    ) -> List[CoachingInsight]:
        """Track momentum through round outcomes, flag tilt/hot states."""
        insights: List[CoachingInsight] = []

        if not round_outcomes:
            return insights

        try:
            from Programma_CS2_RENAN.backend.analysis.momentum import (
                get_momentum_tracker,
                predict_performance_adjustment,
            )

            tracker = get_momentum_tracker()
            tilt_rounds = []
            hot_rounds = []

            for rd in round_outcomes:
                rnum = rd.get("round_number", 0)
                won = rd.get("round_won", False)
                state = tracker.update(round_won=won, round_number=rnum)

                if state.is_tilted:
                    tilt_rounds.append(rnum)
                elif state.is_hot:
                    hot_rounds.append(rnum)

            if tilt_rounds:
                insights.append(
                    CoachingInsight(
                        player_name=player_name,
                        demo_name=demo_name,
                        title="Momentum: Tilt Risk Detected",
                        severity="High",
                        message=(
                            f"Your momentum dropped into the tilt zone (below 0.85) "
                            f"during rounds {', '.join(str(r) for r in tilt_rounds[:5])}. "
                            f"Consider calling a timeout or changing your approach after "
                            f"consecutive losses to reset your mental state."
                        ),
                        focus_area="momentum",
                    )
                )

            if hot_rounds:
                insights.append(
                    CoachingInsight(
                        player_name=player_name,
                        demo_name=demo_name,
                        title="Momentum: Hot Streak",
                        severity="Info",
                        message=(
                            f"You entered a hot streak (multiplier > 1.2) during "
                            f"rounds {', '.join(str(r) for r in hot_rounds[:5])}. "
                            f"Great momentum management — capitalize on these phases "
                            f"with confident plays."
                        ),
                        focus_area="momentum",
                    )
                )

        except Exception as e:
            n = self._module_failure_counts.get("momentum", 0) + 1
            self._module_failure_counts["momentum"] = n
            logger.error("Momentum analysis failed (consecutive=%s): %s", n, e)

        return insights

    def _analyze_deception(
        self,
        player_name: str,
        demo_name: str,
        tick_data: pd.DataFrame,
    ) -> List[CoachingInsight]:
        """Analyze deception sophistication from tick data."""
        insights: List[CoachingInsight] = []

        try:
            metrics = self.deception_analyzer.analyze_round(tick_data)

            if metrics.composite_index > 0.6:
                insights.append(
                    CoachingInsight(
                        player_name=player_name,
                        demo_name=demo_name,
                        title="Deception: Advanced Tactics",
                        severity="Info",
                        message=(
                            f"Your deception index is {metrics.composite_index:.2f} — "
                            f"strong use of fakes and misdirection. "
                            f"Flash bait rate: {metrics.fake_flash_rate:.0%}, "
                            f"Rotation feints: {metrics.rotation_feint_rate:.0%}."
                        ),
                        focus_area="deception",
                    )
                )
            elif metrics.composite_index < 0.2 and metrics.composite_index > 0:
                insights.append(
                    CoachingInsight(
                        player_name=player_name,
                        demo_name=demo_name,
                        title="Deception: Predictable Play",
                        severity="Medium",
                        message=(
                            f"Your deception index is {metrics.composite_index:.2f} — "
                            f"your play may be predictable. Consider adding fake executes, "
                            f"utility baits, or rotation feints to keep opponents guessing."
                        ),
                        focus_area="deception",
                    )
                )

        except Exception as e:
            n = self._module_failure_counts.get("deception", 0) + 1
            self._module_failure_counts["deception"] = n
            logger.error("Deception analysis failed (consecutive=%s): %s", n, e)

        return insights

    def _analyze_utility_entropy(
        self,
        player_name: str,
        demo_name: str,
        tick_data: pd.DataFrame,
    ) -> List[CoachingInsight]:
        """Analyze utility usage effectiveness via entropy reduction."""
        insights: List[CoachingInsight] = []

        try:
            if "event_type" not in tick_data.columns:
                return insights

            utility_events = tick_data[
                tick_data["event_type"].isin(
                    [
                        "smokegrenade_throw",
                        "flashbang_throw",
                        "molotov_throw",
                        "hegrenade_throw",
                    ]
                )
            ]

            if utility_events.empty:
                return insights

            if "team" not in tick_data.columns:
                return insights

            # Compute enemy position entropy before/after each utility
            utility_type_map = {
                "smokegrenade_throw": "smoke",
                "flashbang_throw": "flash",
                "molotov_throw": "molotov",
                "hegrenade_throw": "he_grenade",
            }

            impacts = []
            for _, event in utility_events.iterrows():
                tick = event["tick"]
                utype = utility_type_map.get(event["event_type"], "smoke")

                # Pre: enemy positions at this tick
                event_team = event.get("team", "")
                pre_mask = (tick_data["tick"] == tick) & (tick_data["team"] != event_team)
                post_mask = (tick_data["tick"] == tick + 128) & (tick_data["team"] != event_team)

                if "pos_x" in tick_data.columns and "pos_y" in tick_data.columns:
                    pre_pos = list(
                        zip(
                            tick_data.loc[pre_mask, "pos_x"],
                            tick_data.loc[pre_mask, "pos_y"],
                        )
                    )
                    post_pos = list(
                        zip(
                            tick_data.loc[post_mask, "pos_x"],
                            tick_data.loc[post_mask, "pos_y"],
                        )
                    )

                    if pre_pos:
                        impact = self.entropy_analyzer.analyze_utility_throw(
                            pre_pos,
                            post_pos if post_pos else pre_pos,
                            utype,
                        )
                        impacts.append(impact)

            if impacts:
                ranked = self.entropy_analyzer.rank_utility_usage(impacts)
                best = ranked[0]
                avg_eff = sum(i.effectiveness_rating for i in impacts) / len(impacts)

                insights.append(
                    CoachingInsight(
                        player_name=player_name,
                        demo_name=demo_name,
                        title="Utility: Entropy Impact Analysis",
                        severity="Info",
                        message=(
                            f"Analyzed {len(impacts)} utility throws. "
                            f"Average effectiveness: {avg_eff:.0%}. "
                            f"Best throw ({best.utility_type}): reduced uncertainty "
                            f"by {best.entropy_delta:.2f} bits ({best.effectiveness_rating:.0%} effective)."
                        ),
                        focus_area="utility_entropy",
                    )
                )

        except Exception as e:
            n = self._module_failure_counts.get("utility_entropy", 0) + 1
            self._module_failure_counts["utility_entropy"] = n
            logger.error("Utility entropy analysis failed (consecutive=%s): %s", n, e)

        return insights

    def _analyze_strategy(
        self,
        player_name: str,
        demo_name: str,
        game_states: List[Dict],
    ) -> List[CoachingInsight]:
        """Run game tree + blind spot analysis on decision points."""
        insights: List[CoachingInsight] = []

        try:
            # Run blind spot detection
            spots = self.blind_spot_detector.detect(game_states)

            if spots:
                # Generate training plan from top blind spots
                plan = self.blind_spot_detector.generate_training_plan(spots, top_n=3)
                top_spot = spots[0]

                insights.append(
                    CoachingInsight(
                        player_name=player_name,
                        demo_name=demo_name,
                        title=f"Blind Spot: {top_spot.situation_type.title()}",
                        severity="High" if top_spot.impact_rating > 0.15 else "Medium",
                        message=(
                            f"Detected {len(spots)} strategic blind spot(s). "
                            f"Most impactful: In '{top_spot.situation_type}' situations, "
                            f"you tend to '{top_spot.actual_action}' when the optimal play "
                            f"is '{top_spot.optimal_action}' "
                            f"(seen {top_spot.frequency}x, impact: {top_spot.impact_rating:.0%}).\n\n"
                            f"{plan}"
                        ),
                        focus_area="blind_spots",
                    )
                )

            # Also generate a strategy recommendation from the latest state
            if game_states:
                latest = game_states[-1].get("game_state", game_states[-1])
                strategy = self.game_tree.suggest_strategy(latest)
                insights.append(
                    CoachingInsight(
                        player_name=player_name,
                        demo_name=demo_name,
                        title="Strategy: Game Tree Recommendation",
                        severity="Info",
                        message=strategy,
                        focus_area="game_theory",
                    )
                )

        except Exception as e:
            n = self._module_failure_counts.get("strategy", 0) + 1
            self._module_failure_counts["strategy"] = n
            logger.error("Strategy analysis failed (consecutive=%s): %s", n, e)

        return insights

    def _analyze_engagement_range(
        self,
        player_name: str,
        demo_name: str,
        tick_data: pd.DataFrame,
    ) -> List[CoachingInsight]:
        """Analyze kill distances and provide spatial coaching insights."""
        insights: List[CoachingInsight] = []

        try:
            # Need kill events with position data
            required_cols = {"event_type", "pos_x", "pos_y"}
            if not required_cols.issubset(tick_data.columns):
                return insights

            kill_rows = tick_data[tick_data["event_type"] == "player_death"]
            if kill_rows.empty or len(kill_rows) < 3:
                return insights

            # Build kill event dicts from available columns
            kill_events = []
            for _, row in kill_rows.iterrows():
                ev = {
                    "killer_x": row.get("attacker_pos_x", row.get("pos_x", 0)),
                    "killer_y": row.get("attacker_pos_y", row.get("pos_y", 0)),
                    "killer_z": row.get("attacker_pos_z", row.get("pos_z", 0)),
                    "victim_x": row.get("pos_x", 0),
                    "victim_y": row.get("pos_y", 0),
                    "victim_z": row.get("pos_z", 0),
                }
                kill_events.append(ev)

            if not kill_events:
                return insights

            # Determine map name from tick_data if available
            map_name = "unknown"
            if "map_name" in tick_data.columns:
                map_vals = tick_data["map_name"].dropna().unique()
                if len(map_vals) > 0:
                    map_name = str(map_vals[0])

            # Get player role if available
            player_role = "flex"
            if "role" in tick_data.columns:
                role_vals = tick_data["role"].dropna().unique()
                if len(role_vals) > 0:
                    player_role = str(role_vals[0])

            result = self.engagement_analyzer.analyze_match_engagements(
                kill_events,
                map_name,
                player_role,
            )

            profile = result["profile"]
            observations = result["observations"]

            # Build summary message
            parts = [
                f"Engagement range analysis across {profile.total_kills} kills:",
                f"  Close (<500u): {profile.close_pct:.0%}",
                f"  Medium (500-1500u): {profile.medium_pct:.0%}",
                f"  Long (1500-3000u): {profile.long_pct:.0%}",
                f"  Extreme (>3000u): {profile.extreme_pct:.0%}",
                f"  Average distance: {profile.avg_distance:.0f} units",
            ]

            if observations:
                parts.append("")
                for obs in observations:
                    parts.append(f"  - {obs}")

            # Annotate top kill positions
            annotated = result.get("annotated_kills", [])
            if annotated and map_name != "unknown":
                position_counts: Dict[str, int] = {}
                for ak in annotated:
                    pos = ak.get("killer_position", "Unknown Position")
                    if pos != "Unknown Position":
                        position_counts[pos] = position_counts.get(pos, 0) + 1
                if position_counts:
                    top_positions = sorted(
                        position_counts.items(),
                        key=lambda x: x[1],
                        reverse=True,
                    )[:3]
                    parts.append("")
                    parts.append("Most frequent kill positions:")
                    for pos_name, count in top_positions:
                        parts.append(f"  - {pos_name}: {count} kills")

            severity = "Medium" if observations else "Info"
            insights.append(
                CoachingInsight(
                    player_name=player_name,
                    demo_name=demo_name,
                    title="Engagement Range Profile",
                    severity=severity,
                    message="\n".join(parts),
                    focus_area="positioning",
                )
            )

        except Exception as e:
            n = self._module_failure_counts.get("engagement_range", 0) + 1
            self._module_failure_counts["engagement_range"] = n
            logger.error("Engagement range analysis failed (consecutive=%s): %s", n, e)

        return insights


_orchestrator: AnalysisOrchestrator = None  # type: ignore[assignment]


def get_analysis_orchestrator() -> AnalysisOrchestrator:
    """Singleton factory — avoids re-instantiating 7 analysis modules per call (F5-37)."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AnalysisOrchestrator()
    return _orchestrator
