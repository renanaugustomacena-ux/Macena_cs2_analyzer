"""
Tests for ExperienceBank — DB operations, retrieval, feedback, synthesis.

Complements test_experience_bank_logic.py (which covers data structures only).
Uses in-memory SQLite with monkeypatched get_db_manager for CI portability.
"""

import sys


import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from Programma_CS2_RENAN.backend.knowledge.experience_bank import (
    ExperienceBank,
    ExperienceContext,
    SynthesizedAdvice,
)
from Programma_CS2_RENAN.backend.storage.db_models import CoachingExperience


# ============ Fixtures ============


class _InMemoryDBManager:
    """Lightweight DB manager for tests, mimics DatabaseManager.get_session()."""

    def __init__(self, engine):
        self._engine = engine

    @contextmanager
    def get_session(self, engine_key: str = "default"):
        with Session(self._engine, expire_on_commit=False) as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise


@pytest.fixture
def experience_bank(monkeypatch):
    """Create an ExperienceBank backed by an in-memory DB."""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    mock_db = _InMemoryDBManager(engine)

    # Monkeypatch get_db_manager to return our in-memory manager
    monkeypatch.setattr(
        "Programma_CS2_RENAN.backend.knowledge.experience_bank.get_db_manager",
        lambda: mock_db,
    )

    bank = ExperienceBank.__new__(ExperienceBank)
    from Programma_CS2_RENAN.backend.knowledge.rag_knowledge import KnowledgeEmbedder

    bank.db = mock_db
    bank.embedder = KnowledgeEmbedder()
    return bank


@pytest.fixture
def sample_context():
    """A reusable ExperienceContext for tests."""
    return ExperienceContext(
        map_name="de_mirage",
        round_phase="full_buy",
        side="CT",
        position_area="A-site",
        health_range="full",
        teammates_alive=4,
        enemies_alive=3,
    )


# ============ add_experience ============


class TestAddExperience:
    """Test experience storage."""

    def test_add_returns_record(self, experience_bank, sample_context):
        """add_experience returns a CoachingExperience with correct fields."""
        exp = experience_bank.add_experience(
            context=sample_context,
            action_taken="held_angle",
            outcome="kill",
            delta_win_prob=0.05,
            confidence=0.8,
        )
        assert isinstance(exp, CoachingExperience)
        assert exp.id is not None
        assert exp.map_name == "de_mirage"
        assert exp.action_taken == "held_angle"
        assert exp.outcome == "kill"
        assert exp.confidence == 0.8

    def test_add_generates_embedding(self, experience_bank, sample_context):
        """add_experience stores a JSON-encoded embedding."""
        exp = experience_bank.add_experience(
            context=sample_context,
            action_taken="pushed",
            outcome="death",
        )
        assert exp.embedding is not None
        vec = json.loads(exp.embedding)
        assert isinstance(vec, list)
        assert len(vec) > 0

    def test_add_with_game_state(self, experience_bank, sample_context):
        """game_state dict is serialized to JSON."""
        state = {"health": 85, "weapon": "ak47", "pos_x": -1500}
        exp = experience_bank.add_experience(
            context=sample_context,
            action_taken="pushed",
            outcome="kill",
            game_state=state,
        )
        parsed = json.loads(exp.game_state_json)
        assert parsed["health"] == 85
        assert parsed["weapon"] == "ak47"

    def test_add_pro_experience(self, experience_bank, sample_context):
        """Pro player metadata is stored."""
        exp = experience_bank.add_experience(
            context=sample_context,
            action_taken="held_angle",
            outcome="kill",
            pro_player_name="s1mple",
            source_demo="navi_vs_faze.dem",
            confidence=0.9,
        )
        assert exp.pro_player_name == "s1mple"
        assert exp.source_demo == "navi_vs_faze.dem"

    def test_add_context_hash_stored(self, experience_bank, sample_context):
        """Context hash is computed and stored."""
        exp = experience_bank.add_experience(
            context=sample_context,
            action_taken="pushed",
            outcome="death",
        )
        expected_hash = sample_context.compute_hash()
        assert exp.context_hash == expected_hash

    def test_multiple_adds_create_distinct_records(self, experience_bank, sample_context):
        """Multiple calls create distinct records with unique IDs."""
        exp1 = experience_bank.add_experience(
            context=sample_context, action_taken="pushed", outcome="kill"
        )
        exp2 = experience_bank.add_experience(
            context=sample_context, action_taken="rotated", outcome="survived"
        )
        assert exp1.id != exp2.id


# ============ retrieve_similar ============


class TestRetrieveSimilar:
    """Test experience retrieval."""

    def test_empty_db_returns_empty(self, experience_bank, sample_context):
        """No experiences → empty list."""
        results = experience_bank.retrieve_similar(sample_context)
        assert results == []

    def test_retrieves_matching_map(self, experience_bank):
        """Only experiences from the same map are returned."""
        ctx_mirage = ExperienceContext(map_name="de_mirage", round_phase="full_buy", side="CT")
        ctx_dust2 = ExperienceContext(map_name="de_dust2", round_phase="full_buy", side="CT")

        experience_bank.add_experience(ctx_mirage, "held_angle", "kill", confidence=0.8)
        experience_bank.add_experience(ctx_dust2, "pushed", "death", confidence=0.8)

        results = experience_bank.retrieve_similar(ctx_mirage, top_k=5)
        assert len(results) == 1
        assert results[0].map_name == "de_mirage"

    def test_respects_min_confidence(self, experience_bank, sample_context):
        """Experiences below min_confidence are excluded."""
        experience_bank.add_experience(
            context=sample_context, action_taken="pushed", outcome="death", confidence=0.2
        )
        results = experience_bank.retrieve_similar(sample_context, min_confidence=0.5)
        assert len(results) == 0

    def test_top_k_limits_results(self, experience_bank, sample_context):
        """top_k limits the number of returned experiences."""
        for i in range(10):
            experience_bank.add_experience(
                context=sample_context,
                action_taken=f"action_{i}",
                outcome="kill",
                confidence=0.8,
            )
        results = experience_bank.retrieve_similar(sample_context, top_k=3)
        assert len(results) == 3

    def test_outcome_filter(self, experience_bank, sample_context):
        """outcome_filter restricts to specific outcomes."""
        experience_bank.add_experience(
            context=sample_context, action_taken="pushed", outcome="kill", confidence=0.8
        )
        experience_bank.add_experience(
            context=sample_context, action_taken="held_angle", outcome="death", confidence=0.8
        )

        results = experience_bank.retrieve_similar(
            sample_context, outcome_filter="kill"
        )
        assert len(results) == 1
        assert results[0].outcome == "kill"

    def test_increments_usage_count(self, experience_bank, sample_context):
        """Retrieving an experience increments its usage_count."""
        exp = experience_bank.add_experience(
            context=sample_context, action_taken="pushed", outcome="kill", confidence=0.8
        )
        assert exp.usage_count == 0

        results = experience_bank.retrieve_similar(sample_context, top_k=1)
        assert len(results) == 1

        # Check usage_count was incremented in DB
        with experience_bank.db.get_session() as session:
            refreshed = session.get(CoachingExperience, exp.id)
            assert refreshed.usage_count == 1

    def test_hash_match_bonus(self, experience_bank):
        """Exact context hash match gets a scoring bonus."""
        ctx = ExperienceContext(
            map_name="de_mirage", round_phase="full_buy", side="CT", position_area="A-site"
        )
        ctx_diff = ExperienceContext(
            map_name="de_mirage", round_phase="eco", side="CT", position_area="Mid"
        )

        # Same hash as query context
        experience_bank.add_experience(ctx, "held_angle", "kill", confidence=0.8)
        # Different hash but same map
        experience_bank.add_experience(ctx_diff, "pushed", "kill", confidence=0.8)

        results = experience_bank.retrieve_similar(ctx, top_k=2)
        assert len(results) == 2
        # Hash-matched experience should rank first
        assert results[0].context_hash == ctx.compute_hash()


# ============ retrieve_pro_examples ============


class TestRetrieveProExamples:
    """Test pro player experience retrieval."""

    def test_empty_returns_empty(self, experience_bank, sample_context):
        """No pro experiences → empty list."""
        results = experience_bank.retrieve_pro_examples(sample_context)
        assert results == []

    def test_only_returns_pro(self, experience_bank, sample_context):
        """Only experiences with pro_player_name are returned."""
        experience_bank.add_experience(
            context=sample_context, action_taken="pushed", outcome="kill", confidence=0.8
        )
        experience_bank.add_experience(
            context=sample_context,
            action_taken="held_angle",
            outcome="kill",
            pro_player_name="NiKo",
            confidence=0.9,
        )

        results = experience_bank.retrieve_pro_examples(sample_context, top_k=5)
        assert len(results) == 1
        assert results[0].pro_player_name == "NiKo"


# ============ synthesize_advice ============


class TestSynthesizeAdvice:
    """Test COPER narrative synthesis."""

    def test_empty_db_generic_advice(self, experience_bank, sample_context):
        """No data → generic advice with zero confidence."""
        advice = experience_bank.synthesize_advice(sample_context)
        assert isinstance(advice, SynthesizedAdvice)
        assert advice.confidence == 0.0
        assert advice.experiences_used == 0
        assert len(advice.narrative) > 0

    def test_advice_with_experiences(self, experience_bank, sample_context):
        """With experiences, produces structured advice."""
        for _ in range(3):
            experience_bank.add_experience(
                context=sample_context, action_taken="held_angle", outcome="kill", confidence=0.8
            )

        advice = experience_bank.synthesize_advice(sample_context)
        assert advice.experiences_used > 0
        assert advice.confidence > 0

    def test_advice_with_user_failure(self, experience_bank, sample_context):
        """When user dies, advice suggests successful alternatives."""
        experience_bank.add_experience(
            context=sample_context, action_taken="held_angle", outcome="kill", confidence=0.8
        )

        advice = experience_bank.synthesize_advice(
            sample_context, user_action="pushed", user_outcome="death"
        )
        assert "held_angle" in advice.narrative
        assert advice.experiences_used > 0

    def test_advice_with_pro_references(self, experience_bank, sample_context):
        """Pro examples are included in advice narrative."""
        experience_bank.add_experience(
            context=sample_context,
            action_taken="held_angle",
            outcome="kill",
            pro_player_name="s1mple",
            confidence=0.9,
        )

        advice = experience_bank.synthesize_advice(sample_context)
        assert len(advice.pro_references) > 0
        assert any("s1mple" in ref for ref in advice.pro_references)


# ============ record_feedback ============


class TestRecordFeedback:
    """Test the COPER feedback loop."""

    def test_feedback_not_found(self, experience_bank):
        """Feedback for nonexistent experience returns False."""
        result = experience_bank.record_feedback(
            experience_id=9999,
            follow_up_match_id=1,
            player_outcome="kill",
            player_action="held_angle",
        )
        assert result is False

    def test_positive_feedback(self, experience_bank, sample_context):
        """Positive feedback (action matched, good outcome) increases effectiveness."""
        exp = experience_bank.add_experience(
            context=sample_context, action_taken="held_angle", outcome="kill", confidence=0.5
        )

        result = experience_bank.record_feedback(
            experience_id=exp.id,
            follow_up_match_id=42,
            player_outcome="kill",
            player_action="held_angle",
        )
        assert result is True

        with experience_bank.db.get_session() as session:
            updated = session.get(CoachingExperience, exp.id)
            assert updated.outcome_validated is True
            assert updated.effectiveness_score > 0
            assert updated.follow_up_match_id == 42
            assert updated.times_advice_given == 1
            assert updated.times_advice_followed == 1

    def test_negative_feedback(self, experience_bank, sample_context):
        """Negative feedback (action matched, bad outcome) decreases effectiveness."""
        exp = experience_bank.add_experience(
            context=sample_context, action_taken="pushed", outcome="kill", confidence=0.7
        )

        experience_bank.record_feedback(
            experience_id=exp.id,
            follow_up_match_id=42,
            player_outcome="death",
            player_action="pushed",
        )

        with experience_bank.db.get_session() as session:
            updated = session.get(CoachingExperience, exp.id)
            assert updated.effectiveness_score < 0

    def test_neutral_feedback(self, experience_bank, sample_context):
        """Player didn't follow advice but succeeded → neutral."""
        exp = experience_bank.add_experience(
            context=sample_context, action_taken="held_angle", outcome="kill", confidence=0.5
        )

        experience_bank.record_feedback(
            experience_id=exp.id,
            follow_up_match_id=42,
            player_outcome="kill",
            player_action="pushed",  # Different action
        )

        with experience_bank.db.get_session() as session:
            updated = session.get(CoachingExperience, exp.id)
            # Neutral = 0.0 effectiveness
            assert updated.effectiveness_score == pytest.approx(0.0, abs=0.01)
            assert updated.times_advice_followed == 0

    def test_confidence_adjustment(self, experience_bank, sample_context):
        """Feedback adjusts confidence within [0.1, 1.0] bounds."""
        exp = experience_bank.add_experience(
            context=sample_context, action_taken="held_angle", outcome="kill", confidence=0.5
        )

        experience_bank.record_feedback(
            experience_id=exp.id,
            follow_up_match_id=1,
            player_outcome="kill",
            player_action="held_angle",
        )

        with experience_bank.db.get_session() as session:
            updated = session.get(CoachingExperience, exp.id)
            assert 0.1 <= updated.confidence <= 1.0


# ============ decay_stale_experiences ============


class TestDecayStale:
    """Test stale experience confidence decay."""

    def test_no_stale_no_decay(self, experience_bank, sample_context):
        """Fresh experiences are not decayed."""
        experience_bank.add_experience(
            context=sample_context, action_taken="pushed", outcome="kill", confidence=0.8
        )
        count = experience_bank.decay_stale_experiences(max_age_days=90)
        assert count == 0

    def test_old_unvalidated_decayed(self, experience_bank, sample_context):
        """Old, unvalidated, used experiences get confidence decay."""
        exp = experience_bank.add_experience(
            context=sample_context, action_taken="pushed", outcome="kill", confidence=0.8
        )

        # Manually age the record and mark as used
        with experience_bank.db.get_session() as session:
            record = session.get(CoachingExperience, exp.id)
            record.created_at = datetime.now(timezone.utc) - timedelta(days=120)
            record.usage_count = 5
            session.add(record)

        count = experience_bank.decay_stale_experiences(max_age_days=90)
        assert count == 1

        with experience_bank.db.get_session() as session:
            decayed = session.get(CoachingExperience, exp.id)
            assert decayed.confidence < 0.8  # 0.8 * 0.9 = 0.72
            assert decayed.confidence == pytest.approx(0.72, abs=0.01)

    def test_validated_not_decayed(self, experience_bank, sample_context):
        """Validated experiences are not decayed even if old."""
        exp = experience_bank.add_experience(
            context=sample_context, action_taken="pushed", outcome="kill", confidence=0.8
        )

        with experience_bank.db.get_session() as session:
            record = session.get(CoachingExperience, exp.id)
            record.created_at = datetime.now(timezone.utc) - timedelta(days=120)
            record.usage_count = 5
            record.outcome_validated = True
            session.add(record)

        count = experience_bank.decay_stale_experiences(max_age_days=90)
        assert count == 0


# ============ get_experience_count ============


class TestExperienceCount:
    """Test experience counting."""

    def test_empty_db(self, experience_bank):
        """Empty DB returns all zeros."""
        counts = experience_bank.get_experience_count()
        assert counts == {"total": 0, "pro": 0, "user": 0}

    def test_counts_with_mixed_data(self, experience_bank, sample_context):
        """Correctly counts user vs pro experiences."""
        experience_bank.add_experience(
            context=sample_context, action_taken="pushed", outcome="kill"
        )
        experience_bank.add_experience(
            context=sample_context, action_taken="held_angle", outcome="kill"
        )
        experience_bank.add_experience(
            context=sample_context,
            action_taken="held_angle",
            outcome="kill",
            pro_player_name="NiKo",
        )

        counts = experience_bank.get_experience_count()
        assert counts["total"] == 3
        assert counts["pro"] == 1
        assert counts["user"] == 2


# ============ Private Helpers ============


class TestPrivateHelpers:
    """Test private helper methods."""

    def test_cosine_similarity_identical(self, experience_bank):
        """Identical vectors → similarity = 1.0."""
        v = np.array([1.0, 2.0, 3.0])
        assert experience_bank._cosine_similarity(v, v) == pytest.approx(1.0)

    def test_cosine_similarity_orthogonal(self, experience_bank):
        """Orthogonal vectors → similarity = 0.0."""
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        assert experience_bank._cosine_similarity(a, b) == pytest.approx(0.0)

    def test_cosine_similarity_zero_vector(self, experience_bank):
        """Zero vector → similarity = 0.0 (no division by zero)."""
        a = np.array([1.0, 2.0])
        z = np.array([0.0, 0.0])
        assert experience_bank._cosine_similarity(a, z) == 0.0
        assert experience_bank._cosine_similarity(z, a) == 0.0

    def test_health_to_range_full(self, experience_bank):
        assert experience_bank._health_to_range(100) == "full"
        assert experience_bank._health_to_range(80) == "full"

    def test_health_to_range_damaged(self, experience_bank):
        assert experience_bank._health_to_range(79) == "damaged"
        assert experience_bank._health_to_range(40) == "damaged"

    def test_health_to_range_critical(self, experience_bank):
        assert experience_bank._health_to_range(39) == "critical"
        assert experience_bank._health_to_range(1) == "critical"

    def test_infer_action_scoped(self, experience_bank):
        """Scoped player → 'scoped_hold'."""
        tick = {"is_scoped": True, "is_crouching": False}
        assert experience_bank._infer_action(tick, is_victim=False) == "scoped_hold"

    def test_infer_action_crouching(self, experience_bank):
        """Crouching (not scoped) → 'crouch_peek'."""
        tick = {"is_scoped": False, "is_crouching": True}
        assert experience_bank._infer_action(tick, is_victim=False) == "crouch_peek"

    def test_infer_action_default_attacker(self, experience_bank):
        """No special state, attacker → 'pushed'."""
        tick = {}
        assert experience_bank._infer_action(tick, is_victim=False) == "pushed"

    def test_infer_action_default_victim(self, experience_bank):
        """No special state, victim → 'held_angle'."""
        tick = {}
        assert experience_bank._infer_action(tick, is_victim=True) == "held_angle"

    def test_action_to_focus_mapping(self, experience_bank):
        """Known actions map to correct focus areas."""
        assert experience_bank._action_to_focus("pushed") == "aggression"
        assert experience_bank._action_to_focus("held_angle") == "positioning"
        assert experience_bank._action_to_focus("scoped_hold") == "aim"
        assert experience_bank._action_to_focus("used_utility") == "utility"
        assert experience_bank._action_to_focus("unknown_action") == "positioning"

    def test_infer_position_area(self, experience_bank):
        """Position inference produces a string result."""
        area = experience_bank._infer_position_area(-2000, 800, "de_mirage")
        assert isinstance(area, str)
        assert len(area) > 0

    def test_infer_position_area_unknown_map(self, experience_bank):
        """Unknown map → 'unknown'."""
        area = experience_bank._infer_position_area(0, 0, "de_nonexistent_xyz")
        assert area == "unknown"


# ============ extract_experiences_from_demo ============


class TestExtractFromDemo:
    """Test experience extraction from demo data."""

    def test_no_events_no_experiences(self, experience_bank):
        """Empty events produce zero experiences."""
        count = experience_bank.extract_experiences_from_demo(
            demo_name="test.dem",
            player_name="TestPlayer",
            tick_data=[],
            events=[],
        )
        assert count == 0

    def test_kill_event_creates_experience(self, experience_bank):
        """player_death event where player is attacker → experience with 'kill' outcome."""
        tick_data = [
            {
                "tick": 100,
                "pos_x": -2000,
                "pos_y": 800,
                "map_name": "de_mirage",
                "team": "CT",
                "health": 100,
                "equipment_value": 5000,
                "teammates_alive": 4,
                "enemies_alive": 3,
            }
        ]
        events = [
            {
                "event_type": "player_death",
                "tick": 100,
                "user_name": "Enemy1",
                "attacker_name": "TestPlayer",
            }
        ]

        count = experience_bank.extract_experiences_from_demo(
            demo_name="test.dem",
            player_name="TestPlayer",
            tick_data=tick_data,
            events=events,
        )
        assert count == 1

    def test_death_event_creates_experience(self, experience_bank):
        """player_death event where player is victim → experience with 'death' outcome."""
        tick_data = [{"tick": 200, "pos_x": -1500, "pos_y": 600, "map_name": "de_dust2", "team": "T", "health": 50}]
        events = [
            {
                "event_type": "player_death",
                "tick": 200,
                "user_name": "TestPlayer",
                "attacker_name": "Enemy1",
            }
        ]

        count = experience_bank.extract_experiences_from_demo(
            demo_name="test.dem",
            player_name="TestPlayer",
            tick_data=tick_data,
            events=events,
        )
        assert count == 1

    def test_unrelated_event_ignored(self, experience_bank):
        """Events not involving the player are ignored."""
        tick_data = [{"tick": 100, "map_name": "de_mirage", "team": "CT"}]
        events = [
            {
                "event_type": "player_death",
                "tick": 100,
                "user_name": "Enemy1",
                "attacker_name": "Enemy2",
            }
        ]

        count = experience_bank.extract_experiences_from_demo(
            demo_name="test.dem",
            player_name="TestPlayer",
            tick_data=tick_data,
            events=events,
        )
        assert count == 0

    def test_pro_demo_higher_confidence(self, experience_bank):
        """Pro demo experiences have confidence=0.7 (vs 0.5 for user)."""
        tick_data = [{"tick": 100, "map_name": "de_mirage", "team": "CT", "health": 100}]
        events = [{"event_type": "player_death", "tick": 100, "user_name": "Enemy1", "attacker_name": "ProPlayer"}]

        experience_bank.extract_experiences_from_demo(
            demo_name="pro.dem",
            player_name="ProPlayer",
            tick_data=tick_data,
            events=events,
            is_pro=True,
            pro_player_name="s1mple",
        )

        with experience_bank.db.get_session() as session:
            exp = session.exec(select(CoachingExperience).limit(1)).first()
            assert exp.confidence == 0.7
            assert exp.pro_player_name == "s1mple"
