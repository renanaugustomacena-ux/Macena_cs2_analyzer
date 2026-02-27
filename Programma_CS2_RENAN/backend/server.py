"""
NOT WIRED — Standalone utility server, not part of the main app lifecycle.

This module defines FastAPI endpoints for telemetry ingestion and Ollama proxy,
but is NOT imported or launched by main.py, session_engine.py, or lifecycle.py.
To use: run directly via ``uvicorn Programma_CS2_RENAN.backend.server:app``
or integrate into session_engine.py when server-side features are needed.
"""

import os

# Adjust path to find core/backend modules
import sys
import time
from collections import defaultdict
from typing import List, Optional

import uvicorn
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from Programma_CS2_RENAN.observability.logger_setup import get_logger

app_logger = get_logger("cs2analyzer.server")

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from Programma_CS2_RENAN.backend.storage.database import get_db_manager, init_database
    from Programma_CS2_RENAN.backend.storage.db_models import CoachingInsight
except ImportError:
    # Fallback/Mock for when running in isolation without DB setup
    app_logger.warning(
        "Could not import Programma_CS2_RENAN.backend modules. Running in mock mode."
    )
    get_db_manager = None
    init_database = lambda: None
    CoachingInsight = None


# ==============================================================================
# TASK 2.5.1: Rate Limiting for Telemetry Endpoint
# Prevents DoS attacks from overwhelming local disk or triggering excessive WAL growth
# ==============================================================================
class RateLimiter:
    """
    Simple in-memory rate limiter using sliding window algorithm.
    Limits requests per IP to prevent abuse of the telemetry endpoint.
    """

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict = defaultdict(list)  # IP -> list of timestamps

    def is_allowed(self, client_ip: str) -> bool:
        """Check if request from client_ip is allowed."""
        current_time = time.time()
        window_start = current_time - self.window_seconds

        # Clean old entries outside the window
        self.requests[client_ip] = [ts for ts in self.requests[client_ip] if ts > window_start]

        # Check if under limit
        if len(self.requests[client_ip]) < self.max_requests:
            self.requests[client_ip].append(current_time)
            return True
        return False

    def get_retry_after(self, client_ip: str) -> int:
        """Return seconds until the client can retry."""
        if not self.requests[client_ip]:
            return 0
        oldest_in_window = min(self.requests[client_ip])
        return max(0, int(self.window_seconds - (time.time() - oldest_in_window)))


# Initialize rate limiter: 10 requests per minute per IP
telemetry_rate_limiter = RateLimiter(max_requests=10, window_seconds=60)

app = FastAPI()


class InsightRead(BaseModel):
    title: str
    severity: str
    message: str
    focus_area: str


class MatchTelemetry(BaseModel):
    """
    Data structure for match telemetry sent from a remote client.
    """

    player_name: str
    match_id: str
    stats: dict
    timestamp: float


@app.on_event("startup")
def on_startup():
    if init_database:
        try:
            init_database()
        except Exception as e:
            app_logger.error("DB Init failed: %s", e)


@app.post("/api/ingest/telemetry", status_code=202)
async def ingest_telemetry(
    request: Request, data: MatchTelemetry, background_tasks: BackgroundTasks
):
    """
    Endpoint for remote clients to upload match data to this central server.

    TASK 6.2: Disk write is decoupled from the response loop via BackgroundTasks
    to prevent I/O blocking during high load.

    Rate limited to 10 requests per minute per IP to prevent DoS attacks.
    """
    # TASK 2.5.1: Apply rate limiting
    client_ip = request.client.host if request.client else "unknown"
    if not telemetry_rate_limiter.is_allowed(client_ip):
        retry_after = telemetry_rate_limiter.get_retry_after(client_ip)
        app_logger.warning("Rate limit exceeded for %s. Retry after %ss", client_ip, retry_after)
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests. Retry after {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )

    app_logger.info("Received telemetry from %s for match %s", data.player_name, data.match_id)

    # TASK 6.2: Schedule disk write as background task (non-blocking)
    background_tasks.add_task(_write_telemetry_to_disk, data)

    return {"status": "accepted", "message": "Telemetry received. Archiving in background."}


def _write_telemetry_to_disk(data: MatchTelemetry) -> None:
    """
    Background task: writes telemetry data to disk.

    TASK 6.2: Separated from the API response loop to prevent I/O blocking.
    Errors are logged but do not affect the client response (fire-and-forget).
    """
    try:
        # Default to project-relative telemetry directory
        telemetry_dir = os.path.join(os.path.dirname(__file__), "storage", "remote_telemetry")

        # Optional: Allow override via environment variable for production environments
        env_telemetry_path = os.getenv("CS2_TELEMETRY_PATH")
        if env_telemetry_path and os.path.exists(os.path.dirname(env_telemetry_path)):
            telemetry_dir = env_telemetry_path

        os.makedirs(telemetry_dir, exist_ok=True)

        safe_match_id = "".join(c for c in str(data.match_id) if c.isalnum() or c in "-_")
        safe_player = "".join(c for c in str(data.player_name) if c.isalnum() or c in "-_")
        file_path = os.path.join(telemetry_dir, f"{safe_match_id}_{safe_player}.json")
        import json

        with open(file_path, "w") as f:
            json.dump(data.model_dump(), f, indent=4)

        app_logger.info("Telemetry archived: %s", file_path)
    except Exception as e:
        app_logger.error("Background telemetry write failed: %s", e)


@app.get("/api/insights", response_model=List[InsightRead])
def get_insights():
    if not get_db_manager:
        # Return empty list when DB is not available instead of fake data
        app_logger.warning("Database not available - returning empty insights")
        return []

    try:
        db_manager = get_db_manager()
        with db_manager.get_session() as session:
            statement = select(CoachingInsight).limit(100)
            insights = session.exec(statement).all()
            return insights
    except Exception as e:
        app_logger.error("Error fetching insights: %s", e)
        return []


@app.get("/api/status")
def get_status():
    return {"status": "operational", "version": "2.0.0-electron"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
