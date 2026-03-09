"""
COPER Experience Bank Module

Implements the Experience component of the COPER (Context Optimized with Prompt,
Experience, and Replay) framework for contextual coaching.

Components:
    - Experience storage and retrieval
    - Semantic similarity search via embeddings
    - Context hashing for fast lookups
    - Pro reference linking
    - Narrative synthesis

Adheres to GEMINI.md principles:
    - Explicit state management
    - High-fidelity data preservation
    - Clear separation of concerns
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sqlmodel import Session, func, select

from Programma_CS2_RENAN.backend.knowledge.round_utils import infer_round_phase  # F5-20: shared utility
from Programma_CS2_RENAN.backend.storage.database import get_db_manager
from Programma_CS2_RENAN.backend.storage.db_models import CoachingExperience, PlayerMatchStats
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.experience_bank")


@dataclass
class ExperienceContext:
    """
    Structured context for experience matching.

    Captures the essential game state elements that define
    a "similar situation" for coaching purposes.
    """

    map_name: str
    round_phase: str  # "pistol", "eco", "full_buy", "force"
    side: str  # "T" or "CT"
    position_area: Optional[str] = None  # "A-site", "Mid", "B-apps", etc.
    health_range: str = "full"  # "full", "damaged", "critical"
    equipment_tier: str = "full"  # "eco", "force", "full"
    teammates_alive: int = 5
    enemies_alive: int = 5

    def to_query_string(self) -> str:
        """Convert context to searchable query string."""
        parts = [
            self.map_name,
            f"{self.side}-side",
            self.round_phase,
        ]
        if self.position_area:
            parts.append(self.position_area)
        if self.health_range != "full":
            parts.append(f"{self.health_range} health")
        parts.append(f"{self.teammates_alive}v{self.enemies_alive}")
        return " ".join(parts)

    def compute_hash(self) -> str:
        """Generate deterministic hash for fast lookups."""
        key = f"{self.map_name}:{self.side}:{self.round_phase}:{self.position_area or 'unknown'}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]


@dataclass
class SynthesizedAdvice:
    """
    Output from COPER synthesis.

    Combines experiences and knowledge into actionable coaching.
    """

    narrative: str
    pro_references: List[str]
    confidence: float
    focus_area: str
    experiences_used: int


class ExperienceBank:
    """
    COPER Experience Bank: Store, retrieve, and synthesize gameplay experiences.

    Provides:
        - Experience storage with vector embeddings
        - Semantic similarity search
        - Context-based fast lookups
        - Pro reference linking
        - Narrative advice generation
    """

    def __init__(self):
        # F5-23: init_database() removed — must be called once at app startup, not per-constructor.
        # Deferred import breaks circular dependency: experience_bank <-> rag_knowledge
        from Programma_CS2_RENAN.backend.knowledge.rag_knowledge import KnowledgeEmbedder

        self.db = get_db_manager()
        self.embedder = KnowledgeEmbedder()
        logger.info("ExperienceBank initialized")

    # AC-32-01: Compact embedding serialization (base64 numpy bytes)
    # ~4x smaller than JSON for float32 vectors.  Reads both formats for
    # backward compatibility with existing JSON-encoded rows.

    @staticmethod
    def _serialize_embedding(vec: np.ndarray) -> str:
        """Serialize embedding to base64-encoded float32 bytes."""
        import base64
        return base64.b64encode(vec.astype(np.float32).tobytes()).decode("ascii")

    @staticmethod
    def _deserialize_embedding(raw: str) -> np.ndarray:
        """Deserialize embedding from base64 or legacy JSON."""
        if raw.startswith("["):
            return np.array(json.loads(raw), dtype=np.float32)
        import base64
        return np.frombuffer(base64.b64decode(raw), dtype=np.float32)

    def add_experience(
        self,
        context: ExperienceContext,
        action_taken: str,
        outcome: str,
        delta_win_prob: float = 0.0,
        game_state: Dict[str, Any] = None,
        pro_player_name: Optional[str] = None,
        pro_match_id: Optional[int] = None,
        source_demo: Optional[str] = None,
        confidence: float = 0.5,
    ) -> CoachingExperience:
        """
        Add a new experience to the bank.

        Args:
            context: Structured context of the situation
            action_taken: What action was performed
            outcome: Result of the action (kill, death, trade, etc.)
            delta_win_prob: Win probability change from this action
            game_state: Full tick data at moment of experience
            pro_player_name: If from pro demo, the player name
            pro_match_id: If from pro demo, the match ID
            source_demo: Demo file this came from
            confidence: How reliable/generalizable (0.0-1.0)

        Returns:
            The created CoachingExperience record
        """
        # Generate embedding for semantic search
        query_text = f"{context.to_query_string()} {action_taken} {outcome}"
        embedding_vec = self.embedder.embed(query_text)
        embedding_json = self._serialize_embedding(embedding_vec)

        # Create experience record
        experience = CoachingExperience(
            context_hash=context.compute_hash(),
            map_name=context.map_name,
            round_phase=context.round_phase,
            side=context.side,
            position_area=context.position_area,
            game_state_json=json.dumps(game_state) if game_state else "{}",
            action_taken=action_taken,
            outcome=outcome,
            delta_win_prob=delta_win_prob,
            confidence=confidence,
            pro_match_id=pro_match_id,
            pro_player_name=pro_player_name,
            embedding=embedding_json,
            source_demo=source_demo,
        )

        with self.db.get_session() as session:
            session.add(experience)
            session.commit()
            session.refresh(experience)

        # AC-36-02: Signal FAISS index rebuild
        from Programma_CS2_RENAN.backend.knowledge.vector_index import get_vector_index_manager

        index_mgr = get_vector_index_manager()
        if index_mgr:
            index_mgr.mark_dirty("experience")

        logger.info("Added experience: %s -> %s on %s", action_taken, outcome, context.map_name)
        return experience

    def retrieve_similar(
        self,
        context: ExperienceContext,
        top_k: int = 3,
        min_confidence: float = 0.3,
        outcome_filter: Optional[str] = None,
    ) -> List[CoachingExperience]:
        """
        Retrieve similar experiences using semantic + hash matching.

        Uses FAISS vector index when available (AC-36-02), falling back
        to brute-force cosine similarity if FAISS is not installed.

        Args:
            context: Current game context to match
            top_k: Number of experiences to retrieve
            min_confidence: Minimum confidence threshold
            outcome_filter: Optional filter for specific outcomes

        Returns:
            List of similar CoachingExperience records
        """
        query_text = context.to_query_string()
        query_embedding = self.embedder.embed(query_text)
        context_hash = context.compute_hash()

        # AC-36-02: FAISS fast-path
        from Programma_CS2_RENAN.backend.knowledge.vector_index import (
            OVERFETCH_EXPERIENCE,
            get_vector_index_manager,
        )

        index_mgr = get_vector_index_manager()
        if index_mgr is not None:
            overfetch_k = top_k * OVERFETCH_EXPERIENCE
            faiss_results = index_mgr.search("experience", query_embedding, overfetch_k)
            if faiss_results:
                result = self._score_and_filter_faiss(
                    faiss_results, context, context_hash,
                    min_confidence, outcome_filter, top_k,
                )
                if result is not None:
                    return result

        # Brute-force fallback
        return self._brute_force_retrieve_similar(
            query_embedding, context_hash, context.map_name,
            min_confidence, outcome_filter, top_k,
        )

    def _score_and_filter_faiss(
        self,
        faiss_results: List,
        context: "ExperienceContext",
        context_hash: str,
        min_confidence: float,
        outcome_filter: Optional[str],
        top_k: int,
    ) -> Optional[List[CoachingExperience]]:
        """Post-filter FAISS results with composite scoring."""
        candidate_ids = [db_id for db_id, _ in faiss_results]
        faiss_scores = {db_id: score for db_id, score in faiss_results}

        with self.db.get_session() as session:
            entries = session.exec(
                select(CoachingExperience).where(CoachingExperience.id.in_(candidate_ids))
            ).all()

            if not entries:
                return None

            # Post-filter by metadata
            filtered = [
                e for e in entries
                if e.map_name == context.map_name
                and e.confidence >= min_confidence
            ]
            if outcome_filter:
                filtered = [e for e in filtered if e.outcome == outcome_filter]

            if not filtered:
                return None

            # Composite scoring: FAISS similarity + hash bonus + effectiveness
            scored = []
            for exp in filtered:
                similarity = faiss_scores.get(exp.id, 0.0)
                hash_bonus = 0.2 if exp.context_hash == context_hash else 0.0
                effectiveness_bonus = 0.0
                if (
                    getattr(exp, "outcome_validated", False)
                    and getattr(exp, "effectiveness_score", 0) > 0
                ):
                    effectiveness_bonus = exp.effectiveness_score * 0.4
                score = (similarity + hash_bonus + effectiveness_bonus) * exp.confidence
                scored.append((exp, score))

            scored.sort(key=lambda x: x[1], reverse=True)
            results = [exp for exp, _ in scored[:top_k]]

            for exp in results:
                exp.usage_count += 1
            session.commit()

            return results

    def _brute_force_retrieve_similar(
        self,
        query_embedding: np.ndarray,
        context_hash: str,
        map_name: str,
        min_confidence: float,
        outcome_filter: Optional[str],
        top_k: int,
    ) -> List[CoachingExperience]:
        """Original brute-force cosine similarity search."""
        with self.db.get_session() as session:
            stmt = select(CoachingExperience).where(
                CoachingExperience.map_name == map_name,
                CoachingExperience.confidence >= min_confidence,
            )

            if outcome_filter:
                stmt = stmt.where(CoachingExperience.outcome == outcome_filter)

            stmt = stmt.limit(100)
            candidates = session.exec(stmt).all()

            if not candidates:
                logger.debug("No experiences found for %s", map_name)
                return []

            scored = []
            for exp in candidates:
                hash_bonus = 0.2 if exp.context_hash == context_hash else 0.0

                if exp.embedding:
                    try:
                        exp_vec = self._deserialize_embedding(exp.embedding)
                        similarity = self._cosine_similarity(query_embedding, exp_vec)
                    except (json.JSONDecodeError, ValueError):
                        similarity = 0.0
                else:
                    similarity = 0.0

                effectiveness_bonus = 0.0
                if (
                    getattr(exp, "outcome_validated", False)
                    and getattr(exp, "effectiveness_score", 0) > 0
                ):
                    effectiveness_bonus = exp.effectiveness_score * 0.4

                score = (similarity + hash_bonus + effectiveness_bonus) * exp.confidence
                scored.append((exp, score))

            scored.sort(key=lambda x: x[1], reverse=True)
            results = [exp for exp, _ in scored[:top_k]]

            for exp in results:
                exp.usage_count += 1
            session.commit()

            return results

    def retrieve_pro_examples(
        self, context: ExperienceContext, top_k: int = 3
    ) -> List[CoachingExperience]:
        """
        Retrieve similar experiences specifically from pro players.

        Uses FAISS vector index when available, falling back to brute-force.

        Args:
            context: Current game context
            top_k: Number of pro examples to retrieve

        Returns:
            List of pro player experiences
        """
        query_text = context.to_query_string()
        query_embedding = self.embedder.embed(query_text)

        # FAISS fast-path
        from Programma_CS2_RENAN.backend.knowledge.vector_index import (
            OVERFETCH_EXPERIENCE,
            get_vector_index_manager,
        )

        index_mgr = get_vector_index_manager()
        if index_mgr is not None:
            overfetch_k = top_k * OVERFETCH_EXPERIENCE
            faiss_results = index_mgr.search("experience", query_embedding, overfetch_k)
            if faiss_results:
                candidate_ids = [db_id for db_id, _ in faiss_results]
                faiss_scores = {db_id: score for db_id, score in faiss_results}

                with self.db.get_session() as session:
                    entries = session.exec(
                        select(CoachingExperience).where(
                            CoachingExperience.id.in_(candidate_ids),
                            CoachingExperience.pro_player_name.isnot(None),
                            CoachingExperience.map_name == context.map_name,
                        )
                    ).all()

                    if entries:
                        entries.sort(
                            key=lambda e: faiss_scores.get(e.id, 0), reverse=True
                        )
                        return entries[:top_k]

        # Brute-force fallback
        with self.db.get_session() as session:
            stmt = (
                select(CoachingExperience)
                .where(
                    CoachingExperience.pro_player_name.isnot(None),
                    CoachingExperience.map_name == context.map_name,
                )
                .limit(50)
            )

            candidates = session.exec(stmt).all()

            if not candidates:
                return []

            scored = []
            for exp in candidates:
                if exp.embedding:
                    try:
                        exp_vec = self._deserialize_embedding(exp.embedding)
                        similarity = self._cosine_similarity(query_embedding, exp_vec)
                        scored.append((exp, similarity))
                    except (json.JSONDecodeError, ValueError):
                        pass

            scored.sort(key=lambda x: x[1], reverse=True)
            return [exp for exp, _ in scored[:top_k]]

    def synthesize_advice(
        self,
        context: ExperienceContext,
        user_action: Optional[str] = None,
        user_outcome: Optional[str] = None,
    ) -> SynthesizedAdvice:
        """
        COPER Synthesis: Generate narrative coaching advice from experiences.

        Combines:
            - Similar past experiences (user + pro)
            - Success/failure patterns
            - Pro player references

        Args:
            context: Current game context
            user_action: What the user did (if known)
            user_outcome: What happened (if known)

        Returns:
            SynthesizedAdvice with narrative and references
        """
        # Retrieve relevant experiences
        similar = self.retrieve_similar(context, top_k=5)
        pro_examples = self.retrieve_pro_examples(context, top_k=3)

        if not similar and not pro_examples:
            return SynthesizedAdvice(
                narrative="Keep practicing! No similar situations found yet.",
                pro_references=[],
                confidence=0.0,
                focus_area="general",
                experiences_used=0,
            )

        # Analyze patterns
        success_actions = []
        failure_actions = []

        for exp in similar:
            if exp.outcome in ("kill", "trade", "objective", "survived"):
                success_actions.append(exp.action_taken)
            else:
                failure_actions.append(exp.action_taken)

        # Build narrative
        narrative_parts = []
        focus_area = "positioning"  # Default

        # Compare user action to successful patterns
        if user_action and user_outcome:
            if user_outcome in ("death",) and success_actions:
                # User failed - suggest what works
                most_common_success = (
                    max(set(success_actions), key=success_actions.count)
                    if success_actions
                    else None
                )
                if most_common_success:
                    narrative_parts.append(
                        f"In similar situations, '{most_common_success}' has been more successful than '{user_action}'."
                    )
                    focus_area = self._action_to_focus(most_common_success)

        # Add pro references
        pro_refs = []
        if pro_examples:
            for exp in pro_examples[:2]:
                if exp.pro_player_name:
                    ref = f"{exp.pro_player_name} ({exp.action_taken} -> {exp.outcome})"
                    pro_refs.append(ref)
                    narrative_parts.append(
                        f"Pro example: {exp.pro_player_name} used '{exp.action_taken}' in this situation."
                    )

        # Calculate confidence
        total_experiences = len(similar) + len(pro_examples)
        avg_confidence = (
            np.mean([e.confidence for e in similar + pro_examples])
            if total_experiences > 0
            else 0.0
        )

        # Finalize narrative
        if not narrative_parts:
            narrative_parts.append(
                f"On {context.map_name} ({context.side}-side {context.round_phase}), "
                f"focus on {context.position_area or 'your positioning'}."
            )

        narrative = " ".join(narrative_parts)

        return SynthesizedAdvice(
            narrative=narrative,
            pro_references=pro_refs,
            confidence=float(avg_confidence),
            focus_area=focus_area,
            experiences_used=total_experiences,
        )

    def extract_experiences_from_demo(
        self,
        demo_name: str,
        player_name: str,
        tick_data: List[Dict[str, Any]],
        events: List[Dict[str, Any]],
        is_pro: bool = False,
        pro_player_name: Optional[str] = None,
    ) -> int:
        """
        Extract and store experiences from a parsed demo.

        Analyzes tick data and events to identify coaching-relevant
        experiences (kills, deaths, utility usage, positioning).

        Args:
            demo_name: Source demo file
            player_name: Player to extract experiences for
            tick_data: List of tick snapshots
            events: List of game events (kills, etc.)
            is_pro: Whether this is from a pro demo
            pro_player_name: Pro player name if applicable

        Returns:
            Number of experiences extracted
        """
        experiences_added = 0

        # Group events by tick for context building
        events_by_tick = {}
        for event in events:
            tick = event.get("tick", 0)
            if tick not in events_by_tick:
                events_by_tick[tick] = []
            events_by_tick[tick].append(event)

        # AC-32-03: Index tick_data by tick for O(1) lookup instead of O(T) linear scan
        tick_data_by_tick = {td.get("tick"): td for td in tick_data}

        # Process kill/death events
        for event in events:
            if event.get("event_type") not in ("player_death",):
                continue

            tick = event.get("tick", 0)

            # Find corresponding tick data (O(1) dict lookup)
            tick_snapshot = tick_data_by_tick.get(tick)

            if not tick_snapshot:
                continue

            # Determine if this player was involved
            victim = event.get("user_name", "")
            attacker = event.get("attacker_name", "")

            if victim != player_name and attacker != player_name:
                continue

            # Build context
            map_name = tick_snapshot.get("map_name", "unknown")
            context = ExperienceContext(
                map_name=map_name,
                round_phase=self._infer_round_phase(tick_snapshot),
                side=tick_snapshot.get("team", "unknown"),
                position_area=self._infer_position_area(
                    tick_snapshot.get("pos_x", 0), tick_snapshot.get("pos_y", 0), map_name
                ),
                health_range=self._health_to_range(tick_snapshot.get("health", 100)),
                teammates_alive=tick_snapshot.get("teammates_alive", 5),
                enemies_alive=tick_snapshot.get("enemies_alive", 5),
            )

            # Determine action and outcome
            if victim == player_name:
                action = self._infer_action(tick_snapshot, is_victim=True)
                outcome = "death"
            else:
                action = self._infer_action(tick_snapshot, is_victim=False)
                outcome = "kill"

            # Add experience
            self.add_experience(
                context=context,
                action_taken=action,
                outcome=outcome,
                delta_win_prob=0.0,  # Would need win probability model
                game_state=tick_snapshot,
                pro_player_name=pro_player_name if is_pro else None,
                source_demo=demo_name,
                confidence=0.7 if is_pro else 0.5,
            )
            experiences_added += 1

        logger.info("Extracted %s experiences from %s", experiences_added, demo_name)
        return experiences_added

    def get_experience_count(self) -> Dict[str, int]:
        """Get counts of experiences by category using server-side aggregation."""
        with self.db.get_session() as session:
            total = session.exec(select(func.count(CoachingExperience.id))).one()
            pro_count = session.exec(
                select(func.count(CoachingExperience.id)).where(
                    CoachingExperience.pro_player_name.isnot(None)
                )
            ).one()
            return {"total": total, "pro": pro_count, "user": total - pro_count}

    # --- Feedback Loop (COPER Intelligence) ---

    def record_feedback(
        self,
        experience_id: int,
        follow_up_match_id: int,
        player_outcome: str,
        player_action: str,
    ) -> bool:
        """
        Record feedback for a previously given coaching experience.

        Links match N's coaching to match N+1's outcome to measure
        whether the advice was effective.

        Returns:
            True if feedback was recorded, False if experience not found.
        """
        with self.db.get_session() as session:
            experience = session.get(CoachingExperience, experience_id)
            if not experience:
                logger.warning("Feedback target experience %s not found", experience_id)
                return False

            # Determine effectiveness
            action_match = player_action.lower() == experience.action_taken.lower()
            positive_outcomes = {"kill", "trade", "objective", "survived"}
            outcome_improved = player_outcome in positive_outcomes

            # Effectiveness heuristic: single-trial outcomes are noisy signals.
            # Use moderate values to avoid overconfidence from one event.
            if action_match and outcome_improved:
                effectiveness = 0.6  # Good signal, but one success != proven
            elif action_match and not outcome_improved:
                effectiveness = -0.3  # Moderate penalty — opponent may have been better
            elif not action_match and outcome_improved:
                effectiveness = 0.0  # Neutral — player found alternative approach
            else:
                effectiveness = -0.15  # Mild negative — didn't follow, didn't succeed

            # Update experience with feedback (EMA)
            experience.outcome_validated = True
            experience.effectiveness_score = (
                experience.effectiveness_score * 0.7 + effectiveness * 0.3
            )
            experience.follow_up_match_id = follow_up_match_id
            experience.times_advice_given = (experience.times_advice_given or 0) + 1
            if action_match:
                experience.times_advice_followed = (experience.times_advice_followed or 0) + 1
            experience.last_feedback_at = datetime.now(timezone.utc)

            # Adjust confidence based on feedback
            confidence_adj = effectiveness * 0.05
            experience.confidence = max(0.1, min(1.0, experience.confidence + confidence_adj))

            session.add(experience)
            session.commit()

        logger.info(
            "Feedback recorded for experience %s: effectiveness=%.2f",
            experience_id,
            effectiveness,
        )
        return True

    def collect_feedback_from_match(
        self,
        player_name: str,
        match_id: int,
        events: List[Dict[str, Any]],
        map_name: str,
    ) -> int:
        """
        After processing a new match, find experiences that were previously
        given as coaching and check if the player's behavior changed.

        Returns:
            Number of feedback records created.
        """
        with self.db.get_session() as session:
            stmt = (
                select(CoachingExperience)
                .where(
                    CoachingExperience.map_name == map_name,
                    CoachingExperience.usage_count > 0,
                    CoachingExperience.outcome_validated == False,  # noqa: E712
                )
                .order_by(CoachingExperience.created_at.desc())
                .limit(20)
            )

            pending_experiences = session.exec(stmt).all()

        feedback_count = 0
        for exp in pending_experiences:
            for event in events:
                if event.get("event_type") != "player_death":
                    continue

                victim = event.get("user_name", "")
                attacker = event.get("attacker_name", "")

                if victim != player_name and attacker != player_name:
                    continue

                if attacker == player_name:
                    action = self._infer_action(event, is_victim=False)
                    outcome = "kill"
                else:
                    action = self._infer_action(event, is_victim=True)
                    outcome = "death"

                if self.record_feedback(
                    experience_id=exp.id,
                    follow_up_match_id=match_id,
                    player_outcome=outcome,
                    player_action=action,
                ):
                    feedback_count += 1
                break

        if feedback_count > 0:
            logger.info("Collected %s feedback records from match %s", feedback_count, match_id)
        return feedback_count

    def decay_stale_experiences(self, max_age_days: int = 90) -> int:
        """
        Reduce confidence of old, unvalidated experiences.

        Experiences older than max_age_days with no feedback get 10% confidence decay.
        Prevents stale, unvalidated experiences from dominating retrieval.

        Returns:
            Number of experiences decayed.
        """
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

        with self.db.get_session() as session:
            stmt = select(CoachingExperience).where(
                CoachingExperience.outcome_validated == False,  # noqa: E712
                CoachingExperience.usage_count > 0,
                CoachingExperience.created_at < cutoff,
            ).limit(1000)  # F5-10: cap to prevent OOM on large experience banks
            stale = session.exec(stmt).all()

            for exp in stale:
                exp.confidence = max(0.1, exp.confidence * 0.9)
                session.add(exp)
            session.commit()

            count = len(stale)

        if count > 0:
            logger.info("Decayed confidence for %s stale experiences", count)
        return count

    # --- Private Helpers ---

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def _infer_round_phase(self, tick_data: Dict) -> str:
        """Delegate to shared utility (F5-20: DRY)."""
        return infer_round_phase(tick_data)

    def _infer_position_area(self, x: float, y: float, map_name: str) -> str:
        """Infer position area from coordinates (simplified)."""
        # This is a simplified version - full implementation would use
        # the spatial_data.py landmarks for precise area detection
        try:
            from Programma_CS2_RENAN.core.spatial_data import get_map_metadata

            meta = get_map_metadata(map_name)
            if meta:
                # Very simplified area detection based on normalized position
                norm_x = (x - meta.pos_x) / (meta.scale * 1024)
                norm_y = (meta.pos_y - y) / (meta.scale * 1024)

                # Rough area classification
                if norm_x < 0.3:
                    return "T-side" if norm_y < 0.5 else "Lower"
                elif norm_x > 0.7:
                    return "CT-side" if norm_y < 0.5 else "Upper"
                else:
                    return "Mid"
        except Exception as e:
            logger.debug("Position inference failed: %s", e)
        return "unknown"

    def _health_to_range(self, health: int) -> str:
        """Convert health value to categorical range."""
        if health >= 80:
            return "full"
        elif health >= 40:
            return "damaged"
        return "critical"

    def _infer_action(self, tick_data: Dict, is_victim: bool) -> str:
        """Infer action from tick data."""
        if tick_data.get("is_scoped", False):
            return "scoped_hold"
        if tick_data.get("is_crouching", False):
            return "crouch_peek"

        # Would need velocity to determine push vs hold
        # Simplified for now
        return "pushed" if not is_victim else "held_angle"

    def _action_to_focus(self, action: str) -> str:
        """Map action to coaching focus area."""
        mapping = {
            "pushed": "aggression",
            "held_angle": "positioning",
            "scoped_hold": "aim",
            "crouch_peek": "movement",
            "used_utility": "utility",
            "rotated": "game_sense",
        }
        return mapping.get(action, "positioning")


_experience_bank_instance: Optional[ExperienceBank] = None


def get_experience_bank() -> ExperienceBank:
    """Factory function for ExperienceBank singleton."""
    global _experience_bank_instance
    if _experience_bank_instance is None:
        _experience_bank_instance = ExperienceBank()
    return _experience_bank_instance
