"""
HLTV Sync Service — Background daemon for pro player statistics scraping.

Periodically fetches player statistics (text data) from HLTV.org player pages
and saves to ProPlayer + ProPlayerStatCard in hltv_metadata.db.

This service does NOT download demo files — it only reads web pages
and extracts statistical data (Rating 2.0, K/D, ADR, KAST, HS%, etc.).
"""

import os
import subprocess
import sys
import time
from pathlib import Path

from Programma_CS2_RENAN.backend.data_sources.hltv.flaresolverr_client import FlareSolverrClient
from Programma_CS2_RENAN.backend.data_sources.hltv.stat_fetcher import HLTVStatFetcher
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.hltv_sync_service")

# --- Path Stabilization ---
SCRIPT_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
PID_FILE = SCRIPT_DIR / "hltv_sync.pid"
STOP_SIGNAL = SCRIPT_DIR / "hltv_sync.stop"

# Dormant mode sleep duration (6 hours) when HLTV is unreachable
_DORMANT_SLEEP_S = 21600


def _dormant_sleep(seconds: int) -> None:
    """Sleep in 1-second increments, checking the stop signal."""
    for _ in range(seconds):
        if STOP_SIGNAL.exists():
            break
        time.sleep(1)


def run_sync_loop():
    """
    Main background loop.
    Fetches pro player statistics from HLTV.org player pages.
    Uses FlareSolverr (Docker) to bypass Cloudflare protection.
    """
    logger.info("HLTV Sync Service Loop started.")

    from Programma_CS2_RENAN.backend.storage.state_manager import state_manager

    # --- Pre-flight: Auto-start FlareSolverr Docker container ---
    from Programma_CS2_RENAN.backend.data_sources.hltv.docker_manager import ensure_flaresolverr

    project_root = str(Path(__file__).resolve().parent.parent)
    if not ensure_flaresolverr(project_root):
        logger.error("FlareSolverr non avviabile automaticamente.")
        state_manager.update_status(
            "hunter", "Blocked", "FlareSolverr/Docker non disponibile"
        )
        state_manager.add_notification(
            "hunter",
            "error",
            "HLTV sync bloccato: FlareSolverr non disponibile e auto-start fallito. "
            "Verifica che Docker Desktop sia in esecuzione.",
        )
        return

    # --- Pre-flight: FlareSolverr availability (safety net) ---
    solver = FlareSolverrClient()
    if not solver.is_available():
        logger.error(
            "FlareSolverr non disponibile dopo auto-start! Avvialo con: docker start flaresolverr"
        )
        state_manager.update_status(
            "hunter", "Blocked", "FlareSolverr non raggiungibile"
        )
        state_manager.add_notification(
            "hunter",
            "error",
            "HLTV sync bloccato: FlareSolverr non disponibile. "
            "Esegui: docker start flaresolverr",
        )
        return

    # --- Pre-flight: HLTV connectivity test ---
    logger.info("Testing HLTV connectivity via FlareSolverr...")
    test_html = solver.get("https://www.hltv.org/stats")
    if not test_html:
        logger.error(
            "HLTV non raggiungibile nemmeno via FlareSolverr. Dormant mode (%s ore).",
            _DORMANT_SLEEP_S // 3600,
        )
        state_manager.update_status(
            "hunter", "Blocked", "HLTV non raggiungibile via FlareSolverr"
        )
        _dormant_sleep(_DORMANT_SLEEP_S)
        return

    logger.info("HLTV connectivity test passed. Creating persistent session...")

    # Create persistent session for cookie reuse across requests
    solver.create_session()

    fetcher = HLTVStatFetcher()

    if STOP_SIGNAL.exists():
        os.remove(STOP_SIGNAL)

    while not STOP_SIGNAL.exists():
        try:
            state_manager.update_status(
                "hunter", "Running", f"Stats sync cycle active at {time.ctime()}"
            )

            # 1. Discover Top 50 players
            logger.info("Discovering Top 50 players...")
            player_urls = fetcher.fetch_top_players()

            # 2. Deep crawl each player's stats
            synced = 0
            for url in player_urls:
                if STOP_SIGNAL.exists():
                    break
                if fetcher.fetch_and_save_player(url):
                    synced += 1

            logger.info("Cycle complete: %s players synced. Sleeping for 1 hour...", synced)
            _dormant_sleep(3600)

        except Exception as e:
            logger.error("Sync Loop Error: %s", e)
            time.sleep(60)

    # Cleanup persistent session
    solver.destroy_session()

    logger.info("Sync Loop received stop signal. Exiting.")
    if PID_FILE.exists():
        os.remove(PID_FILE)


def start_detached():
    """Starts the sync service as a detached background process."""
    if PID_FILE.exists():
        logger.warning("Sync service already seems to be running.")
        return

    python_exe = sys.executable
    main_script = SCRIPT_DIR / "main.py"

    process = subprocess.Popen(
        [python_exe, str(main_script), "--hltv-service"],
        creationflags=(
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            if os.name == "nt"
            else 0
        ),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(SCRIPT_DIR.parent),
    )

    PID_FILE.write_text(str(process.pid))
    logger.info("HLTV Sync Service launched in background (PID: %s)", process.pid)


def stop_service():
    """Signals the background service to stop and cleans up."""
    STOP_SIGNAL.touch()
    logger.info("Stop signal sent to HLTV Sync Service.")

    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            logger.info("Background process %s will stop at next cycle check.", pid)
        except Exception as e:
            logger.warning("Failed to read PID file during stop: %s", e)


if __name__ == "__main__":
    run_sync_loop()
