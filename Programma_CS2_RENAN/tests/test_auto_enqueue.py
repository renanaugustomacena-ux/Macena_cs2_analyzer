"""
Unit tests for automated demo parsing triggers.

Tests IngestionTask creation and auto-enqueue functionality.
"""

import sys
import time
from datetime import datetime, timezone


import pytest
from sqlmodel import select

from Programma_CS2_RENAN.backend.storage.database import get_db_manager, init_database
from Programma_CS2_RENAN.backend.storage.db_models import IngestionTask

# Unique prefix so we only clean up OUR test records, never real data
_TEST_PREFIX = "/__test_auto_enqueue__/"


@pytest.mark.integration
class TestAutoEnqueue:
    """Test suite for automatic task creation."""

    @pytest.fixture(autouse=True)
    def setup_database(self):
        """Initialize DB; only clean up tasks created by this test."""
        init_database()
        self._created_ids = []
        yield
        # Teardown: remove only tasks created by this test
        db = get_db_manager()
        with db.get_session() as session:
            for task_id in self._created_ids:
                task = session.get(IngestionTask, task_id)
                if task:
                    session.delete(task)
            session.commit()

    def _create_task(self, session, demo_name="demo.dem", is_pro=False, status="queued"):
        """Helper: create an IngestionTask with test prefix."""
        task = IngestionTask(
            demo_path=f"{_TEST_PREFIX}{demo_name}",
            is_pro=is_pro,
            status=status,
        )
        session.add(task)
        session.commit()
        self._created_ids.append(task.id)
        return task

    def test_create_ingestion_task(self):
        """Test basic IngestionTask creation."""
        db = get_db_manager()

        with db.get_session() as session:
            task = self._create_task(session, "create_test.dem")
            task_id = task.id

        with db.get_session() as session:
            retrieved = session.get(IngestionTask, task_id)
            assert retrieved is not None
            assert retrieved.demo_path == f"{_TEST_PREFIX}create_test.dem"
            assert retrieved.is_pro is False
            assert retrieved.status == "queued"

    def test_task_default_status(self):
        """Test that tasks default to 'queued' status."""
        db = get_db_manager()

        with db.get_session() as session:
            task = self._create_task(session, "default_status.dem")
            assert task.status == "queued"
            assert task.retry_count == 0

    def test_pro_demo_flag(self):
        """Test is_pro flag for pro demos."""
        db = get_db_manager()

        with db.get_session() as session:
            task = self._create_task(session, "pro_demo.dem", is_pro=True)
            pro_id = task.id

        with db.get_session() as session:
            retrieved = session.get(IngestionTask, pro_id)
            assert retrieved.is_pro is True

    def test_multiple_tasks_queued(self):
        """Test multiple tasks can be queued."""
        db = get_db_manager()

        with db.get_session() as session:
            for i in range(3):
                self._create_task(session, f"multi_{i}.dem")

        with db.get_session() as session:
            queued = session.exec(
                select(IngestionTask).where(
                    IngestionTask.status == "queued",
                    IngestionTask.demo_path.startswith(_TEST_PREFIX),
                )
            ).all()
            assert len(queued) >= 3

    def test_task_timestamps(self):
        """Test created_at and updated_at timestamps are populated."""
        db = get_db_manager()

        with db.get_session() as session:
            task = self._create_task(session, "timestamp.dem")
            assert task.created_at is not None
            assert task.updated_at is not None
            assert isinstance(task.created_at, datetime)
            assert isinstance(task.updated_at, datetime)
            # Timestamps should be recent (within last 60 seconds)
            now = datetime.now(timezone.utc)
            delta = (now - task.created_at).total_seconds()
            assert delta < 60, f"created_at is {delta}s old — should be recent"

    def test_task_ordering(self):
        """Test tasks are ordered by created_at."""
        db = get_db_manager()

        task_ids = []
        with db.get_session() as session:
            for i in range(3):
                task = self._create_task(session, f"order_{i}.dem")
                task_ids.append(task.id)
                time.sleep(0.01)

        with db.get_session() as session:
            tasks = session.exec(
                select(IngestionTask)
                .where(IngestionTask.demo_path.startswith(_TEST_PREFIX))
                .order_by(IngestionTask.created_at.asc())
            ).all()

            ordered_ids = [t.id for t in tasks if t.id in task_ids]
            assert ordered_ids == task_ids

