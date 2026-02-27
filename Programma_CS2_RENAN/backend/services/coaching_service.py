from typing import Any, Dict, List, Optional

from Programma_CS2_RENAN.backend.coaching.correction_engine import generate_corrections
from Programma_CS2_RENAN.backend.coaching.longitudinal_engine import generate_longitudinal_coaching
from Programma_CS2_RENAN.backend.knowledge.round_utils import infer_round_phase  # F5-20: shared utility
from Programma_CS2_RENAN.backend.services.ollama_writer import get_ollama_writer
from Programma_CS2_RENAN.backend.storage.database import get_db_manager
from Programma_CS2_RENAN.backend.storage.db_models import CoachingInsight, PlayerMatchStats
from Programma_CS2_RENAN.core.config import get_setting
from Programma_CS2_RENAN.observability.logger_setup import get_logger

_coaching_logger = get_logger("cs2analyzer.coaching.temporal")


class CoachingService:
    def __init__(self):
        self.db_manager = get_db_manager()
        self.use_rag = get_setting("USE_RAG_COACHING", default=False)
        self.use_hybrid = get_setting("USE_HYBRID_COACHING", default=False)
        self.use_coper = get_setting("USE_COPER_COACHING", default=True)  # COPER enabled by default

    def _get_temporal_baseline(self, map_name: str = None) -> dict:
        """Get temporal-weighted pro baseline, with graceful fallback to legacy.

        Returns baseline dict compatible with all existing consumers.
        """
        try:
            from Programma_CS2_RENAN.backend.processing.baselines.pro_baseline import (
                TemporalBaselineDecay,
            )

            decay = TemporalBaselineDecay()
            baseline = decay.get_temporal_baseline(map_name=map_name)
            _coaching_logger.debug("Temporal baseline retrieved for map=%s", map_name or "global")
            return baseline
        except Exception as e:
            _coaching_logger.warning("Temporal baseline unavailable, using legacy: %s", e)
            from Programma_CS2_RENAN.backend.processing.baselines.pro_baseline import (
                get_pro_baseline,
            )

            return get_pro_baseline(map_name)

    def generate_new_insights(
        self,
        player_name: str,
        demo_name: str,
        deviations: Dict[str, float],
        rounds_played: int,
        map_name: str = None,
        player_stats: Dict[str, float] = None,
        tick_data: Dict = None,
    ):
        """
        Generates corrections and longitudinal insights and saves them to the database.

        Supports four modes (priority order):
        - COPER: Context-aware with experience retrieval and pro references (recommended)
        - Hybrid: Full ML + RAG synthesis
        - RAG: Enhanced with knowledge retrieval
        - Basic: Traditional correction engine

        After main coaching, runs Phase 6 advanced analysis if data is available.
        """
        try:
            from Programma_CS2_RENAN.observability.sentry_setup import add_breadcrumb

            add_breadcrumb("coaching", f"Coaching generation: {player_name} on {map_name}")
        except ImportError:
            pass

        # COPER mode takes highest precedence
        if self.use_coper and map_name and tick_data:
            _coaching_logger.info(
                "Coaching mode selected: COPER for player=%s demo=%s", player_name, demo_name
            )
            self._generate_coper_insights(
                player_name, demo_name, player_stats or {}, map_name, tick_data
            )
        elif self.use_hybrid and player_stats:
            _coaching_logger.info(
                "Coaching mode selected: Hybrid for player=%s demo=%s", player_name, demo_name
            )
            self._generate_hybrid_insights(player_name, demo_name, player_stats, map_name)
        else:
            _coaching_logger.info(
                "Coaching mode selected: Traditional%s for player=%s demo=%s",
                "+RAG" if self.use_rag else "",
                player_name,
                demo_name,
            )
            # Traditional + optional RAG
            corrections = generate_corrections(deviations, rounds_played)
            if self.use_rag and map_name:
                corrections = self._enhance_with_rag(corrections, deviations, map_name)
            _save_corrections_as_insights(self.db_manager, player_name, demo_name, corrections)

        # Phase 6 Advanced Analysis (runs after main coaching, non-blocking)
        self._generate_advanced_insights(player_name, demo_name, tick_data)

    def _generate_coper_insights(
        self,
        player_name: str,
        demo_name: str,
        player_stats: Dict[str, float],
        map_name: str,
        tick_data: Dict,
    ):
        """
        Generate insights using COPER Framework (Context, Experience, Prompt, Replay).

        Combines:
        - Experience Bank: Similar past situations from user + pro demos
        - RAG Knowledge: Tactical knowledge retrieval
        - Pro References: Links to professional player examples
        """
        try:
            from Programma_CS2_RENAN.backend.knowledge.experience_bank import (
                ExperienceContext,
                get_experience_bank,
            )
            from Programma_CS2_RENAN.observability.logger_setup import get_logger

            logger = get_logger("cs2analyzer.coaching.coper")

            bank = get_experience_bank()  # Singleton — avoids re-loading SBERT model (F5-04)

            # Build context from tick data
            context = ExperienceContext(
                map_name=map_name,
                round_phase=self._infer_round_phase(tick_data),
                side=tick_data.get("team", "T"),
                position_area=tick_data.get("position_area"),
                health_range=self._health_to_range(tick_data.get("health", 100)),
                teammates_alive=tick_data.get("teammates_alive", 5),
                enemies_alive=tick_data.get("enemies_alive", 5),
            )

            # Get COPER synthesis
            advice = bank.synthesize_advice(
                context=context,
                user_action=tick_data.get("action"),
                user_outcome=tick_data.get("outcome"),
            )

            # Enrich with temporal baseline context (Proposal 11)
            temporal_baseline = self._get_temporal_baseline(map_name)
            advice_baseline_note = self._baseline_context_note(
                player_stats,
                temporal_baseline,
                advice.focus_area,
            )

            # Create insight from COPER advice
            raw_message = self._format_coper_message(advice, advice_baseline_note)
            polished = get_ollama_writer().polish(
                title=f"COPER: {advice.focus_area.title()} Insight",
                message=raw_message,
                focus_area=advice.focus_area,
                severity="Info" if advice.confidence > 0.5 else "Medium",
                map_name=map_name,
            )
            insight = CoachingInsight(
                player_name=player_name,
                demo_name=demo_name,
                title=f"COPER: {advice.focus_area.title()} Insight",
                severity="Info" if advice.confidence > 0.5 else "Medium",
                message=polished,
                focus_area=advice.focus_area,
            )

            with self.db_manager.get_session() as session:
                session.add(insight)
                session.commit()

            logger.info("COPER insight generated for %s on %s", player_name, map_name)

            # Collect feedback from this match for previous coaching experiences
            try:
                events = tick_data.get("events", []) if isinstance(tick_data, dict) else []
                if events and map_name:
                    bank.collect_feedback_from_match(
                        player_name=player_name,
                        match_id=tick_data.get("match_id", 0) if isinstance(tick_data, dict) else 0,
                        events=events,
                        map_name=map_name,
                    )
            except Exception as fb_err:
                logger.debug("Feedback collection non-fatal: %s", fb_err)

        except Exception as e:
            from Programma_CS2_RENAN.observability.logger_setup import get_logger

            logger = get_logger("cs2analyzer.coaching")
            logger.error("COPER coaching failed: %s", e)
            # Fallback to hybrid or traditional
            if self.use_hybrid and player_stats:
                self._generate_hybrid_insights(player_name, demo_name, player_stats, map_name)
            else:
                # G-08: fallback to traditional coaching instead of zero output
                logger.warning(
                    "COPER fallback: using traditional coaching for %s on %s",
                    player_name,
                    demo_name,
                )
                corrections = generate_corrections(deviations, rounds_played)
                _save_corrections_as_insights(self.db_manager, player_name, demo_name, corrections)

    def _format_coper_message(self, advice, baseline_note: str = "") -> str:
        """Format COPER advice into readable message."""
        parts = [advice.narrative]

        if advice.pro_references:
            parts.append("\n\nPro Examples:")
            for ref in advice.pro_references:
                parts.append(f"  - {ref}")

        if baseline_note:
            parts.append(f"\n\n{baseline_note}")

        parts.append(
            f"\n\n(Based on {advice.experiences_used} similar situations, confidence: {advice.confidence:.0%})"
        )

        return "".join(parts)

    @staticmethod
    def _baseline_context_note(
        player_stats: Dict[str, float],
        baseline: dict,
        focus_area: str,
    ) -> str:
        """Build a short pro-baseline comparison note for the focus area."""
        if not player_stats or not baseline:
            return ""

        # Map focus areas to relevant baseline keys
        focus_metrics = {
            "positioning": ["rating"],
            "utility": ["avg_adr"],
            "economy": ["avg_adr", "rating"],
            "aim": ["avg_hs", "avg_kills"],
            "trading": ["avg_kills"],
        }
        keys = focus_metrics.get(focus_area, ["rating"])

        notes = []
        for key in keys:
            b = baseline.get(key)
            if b is None:
                continue
            pro_mean = b.get("mean", 0) if isinstance(b, dict) else b
            if pro_mean == 0:
                continue

            # Try to find a matching player stat
            player_val = player_stats.get(key) or player_stats.get(f"avg_{key}")
            if player_val is not None:
                delta_pct = ((player_val - pro_mean) / pro_mean) * 100
                direction = "above" if delta_pct > 0 else "below"
                notes.append(
                    f"Your {key} is {abs(delta_pct):.0f}% {direction} the current pro average."
                )

        return " ".join(notes)

    def _infer_round_phase(self, tick_data: Dict) -> str:
        """Delegate to shared utility (F5-20: DRY)."""
        return infer_round_phase(tick_data)

    def _health_to_range(self, health: int) -> str:
        """Convert health to categorical range."""
        if health >= 80:
            return "full"
        elif health >= 40:
            return "damaged"
        return "critical"

    def _generate_advanced_insights(
        self, player_name: str, demo_name: str, tick_data: Optional[Dict] = None
    ):
        """
        Run Phase 6 advanced analysis modules (momentum, deception, entropy, game theory).

        Non-blocking: failures are logged but do not affect main coaching pipeline.
        """
        try:
            from Programma_CS2_RENAN.backend.services.analysis_orchestrator import (
                get_analysis_orchestrator,
            )
            from Programma_CS2_RENAN.observability.logger_setup import get_logger

            logger = get_logger("cs2analyzer.coaching.advanced")

            orchestrator = get_analysis_orchestrator()

            # Extract round outcomes from tick_data if available
            round_outcomes = []
            game_states = []
            tick_df = None

            if tick_data and isinstance(tick_data, dict):
                round_outcomes = tick_data.get("round_outcomes", [])
                game_states = tick_data.get("game_states", [])

                # Convert tick-level data to DataFrame if provided
                if "tick_rows" in tick_data:
                    import pandas as pd

                    tick_df = pd.DataFrame(tick_data["tick_rows"])

            if not round_outcomes and not tick_df and not game_states:
                return

            analysis = orchestrator.analyze_match(
                player_name=player_name,
                demo_name=demo_name,
                round_outcomes=round_outcomes,
                tick_data=tick_df,
                game_states=game_states,
            )

            # Save all generated insights to database
            if analysis.all_insights:
                with self.db_manager.get_session() as session:
                    for insight in analysis.all_insights:
                        session.add(insight)
                    session.commit()
                logger.info(
                    "Phase 6 analysis: %d insights saved for %s",
                    len(analysis.all_insights),
                    player_name,
                )

        except Exception as e:
            from Programma_CS2_RENAN.observability.logger_setup import get_logger

            logger = get_logger("cs2analyzer.coaching")
            logger.warning("Phase 6 advanced analysis failed (non-fatal): %s", e)

    def _generate_hybrid_insights(
        self, player_name: str, demo_name: str, player_stats: Dict[str, float], map_name: str = None
    ):
        """
        Generate insights using Hybrid Coaching Engine.

        Combines ML predictions with RAG knowledge for unified insights.
        """
        try:
            from Programma_CS2_RENAN.backend.coaching.hybrid_engine import HybridCoachingEngine

            engine = HybridCoachingEngine()
            insights = engine.generate_insights(player_stats, map_name=map_name)

            # Save to database
            engine.save_insights_to_db(insights, player_name, demo_name)

        except Exception as e:
            from Programma_CS2_RENAN.observability.logger_setup import get_logger

            logger = get_logger("cs2analyzer.coaching")
            logger.error("Hybrid coaching failed: %s", e)

            # Fallback to traditional — but only if we have deviations
            logger.warning(
                f"Hybrid coaching fallback: no deviations data — "
                f"no coaching generated for {player_name} on {demo_name}"
            )

    def _enhance_with_rag(
        self, corrections: List[Dict], deviations: Dict[str, float], map_name: str
    ) -> List[Dict]:
        """
        Enhance corrections with RAG-retrieved tactical knowledge.
        """
        try:
            from Programma_CS2_RENAN.backend.knowledge.rag_knowledge import KnowledgeRetriever

            retriever = KnowledgeRetriever()

            # Build query from deviations
            query_parts = []
            if deviations.get("avg_adr", 0) < -10:
                query_parts.append("low ADR")
            if deviations.get("avg_kills", 0) < -5:
                query_parts.append("low kills")

            query = " ".join(query_parts) if query_parts else "general improvement"

            # Retrieve knowledge
            knowledge = retriever.retrieve(query, top_k=2, map_name=map_name)

            # Add knowledge to corrections
            for k in knowledge:
                corrections.append(
                    {
                        "feature": k.category,
                        "weighted_z": 0,  # Not a deviation, just knowledge
                        "rag_title": k.title,
                        "rag_description": k.description,
                        "rag_pro_example": k.pro_example,
                    }
                )

        except Exception as e:
            from Programma_CS2_RENAN.observability.logger_setup import get_logger

            logger = get_logger("cs2analyzer.coaching")
            logger.error("RAG enhancement failed: %s", e)

        return corrections

    def generate_differential_insights(
        self,
        player_name: str,
        demo_name: str,
        user_positions: List[tuple],
        map_name: str,
    ) -> Optional[str]:
        """
        Generate coaching insights from differential heatmap hotspots.

        Compares user positional patterns against pro baselines on the same map,
        identifies the top divergence areas, and produces a natural-language
        coaching narrative.

        Args:
            player_name: Player identifier.
            demo_name: Demo file name for attribution.
            user_positions: List of (x, y) world-coordinate tuples.
            map_name: CS2 map name (e.g. "de_mirage").

        Returns:
            Path to the saved differential overlay image, or None on failure.
        """
        try:
            from Programma_CS2_RENAN.backend.processing.baselines.pro_baseline import (
                get_pro_positions,
            )
            from Programma_CS2_RENAN.backend.processing.heatmap_engine import HeatmapEngine
            from Programma_CS2_RENAN.observability.logger_setup import get_logger

            logger = get_logger("cs2analyzer.coaching.differential")

            pro_positions = get_pro_positions(map_name)
            if not pro_positions:
                logger.info("No pro positions available for %s, skipping differential", map_name)
                return None

            diff_data = HeatmapEngine.generate_differential_heatmap_data(
                map_name=map_name,
                user_positions=user_positions,
                pro_positions=pro_positions,
            )
            if diff_data is None or not diff_data.hotspots:
                return None

            # Use named positions for human-readable coaching narratives
            try:
                from Programma_CS2_RENAN.backend.analysis.engagement_range import (
                    get_engagement_range_analyzer,
                )

                range_analyzer = get_engagement_range_analyzer()
            except Exception:
                range_analyzer = None

            # Build coaching narrative from hotspots
            narrative_parts = []
            for hs in diff_data.hotspots[:3]:
                # Resolve callout name if analyzer available
                callout = None
                if range_analyzer:
                    callout = range_analyzer.annotate_kill_position(
                        map_name,
                        hs["world_x"],
                        hs["world_y"],
                    )
                    if callout == "Unknown Position":
                        callout = None

                pos_label = callout or f"({hs['world_x']:.0f}, {hs['world_y']:.0f})"

                if hs["label"] == "pro-heavy":
                    narrative_parts.append(
                        f"Pro players occupy {pos_label} "
                        f"significantly more than you (gap: {hs['magnitude']:.0%}). "
                        "Consider incorporating this position into your repertoire."
                    )
                else:
                    narrative_parts.append(
                        f"You spend disproportionate time at {pos_label} "
                        f"compared to pros (gap: {hs['magnitude']:.0%}). "
                        "Evaluate whether this position offers sufficient value."
                    )

            if narrative_parts:
                message = "Positional Comparison:\n" + "\n\n".join(narrative_parts)
                insight = CoachingInsight(
                    player_name=player_name,
                    demo_name=demo_name,
                    title=f"Positioning Gap: {map_name}",
                    severity="Medium",
                    message=message,
                    focus_area="positioning",
                )
                with self.db_manager.get_session() as session:
                    session.add(insight)
                    session.commit()

                logger.info("Differential insight saved for %s on %s", player_name, map_name)

            # Also generate static report overlay via MatchVisualizer
            try:
                from Programma_CS2_RENAN.reporting.visualizer import MatchVisualizer

                viz = MatchVisualizer()
                return viz.render_differential_overlay(user_positions, pro_positions, map_name)
            except Exception as viz_err:
                logger.warning("Differential overlay rendering failed: %s", viz_err)
                return None

        except Exception as e:
            from Programma_CS2_RENAN.observability.logger_setup import get_logger

            logger = get_logger("cs2analyzer.coaching")
            logger.error("Differential heatmap coaching failed: %s", e)
            return None

    def get_latest_insights(self, player_name: str, limit: int = 5) -> List[CoachingInsight]:
        """
        Retrieves the latest coaching insights for a player.
        """
        from sqlmodel import select

        with self.db_manager.get_session() as session:
            statement = (
                select(CoachingInsight)
                .where(CoachingInsight.player_name == player_name)
                .order_by(CoachingInsight.created_at.desc())
                .limit(limit)
            )
            return session.exec(statement).all()


def _save_corrections_as_insights(db_manager, p_name, d_name, corrections):
    with db_manager.get_session() as session:
        for c in corrections:
            session.add(_create_insight_obj(p_name, d_name, c))
        session.commit()


def _create_insight_obj(p_name, d_name, c):
    # Check if RAG-enhanced
    if "rag_title" in c:
        title = c["rag_title"]
        message = f"{c['rag_description']}\n\nPro example: {c.get('rag_pro_example', 'N/A')}"
        severity = "Info"
    else:
        title = f"Improve your {c['feature']}"
        message = f"Your {c['feature']} deviates from pro baseline. Z: {c['weighted_z']:.2f}"
        severity = "Medium" if abs(c["weighted_z"]) < 2 else "High"

    polished = get_ollama_writer().polish(
        title=title,
        message=message,
        focus_area=c["feature"],
        severity=severity,
    )

    return CoachingInsight(
        player_name=p_name,
        demo_name=d_name,
        title=title,
        severity=severity,
        message=polished,
        focus_area=c["feature"],
    )


_coaching_service: CoachingService = None  # type: ignore[assignment]


def get_coaching_service() -> CoachingService:
    """Singleton factory — consistent with other service accessors (F5-38)."""
    global _coaching_service
    if _coaching_service is None:
        _coaching_service = CoachingService()
    return _coaching_service
