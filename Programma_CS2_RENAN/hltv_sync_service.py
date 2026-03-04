import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# Use the automated discovery fetcher we just refined
from Programma_CS2_RENAN.fetch_hltv_stats import HLTVStatFetcher
from Programma_CS2_RENAN.ingestion.hltv.flaresolverr_client import FlareSolverrClient
from Programma_CS2_RENAN.ingestion.hltv_orchestrator import HLTVOrchestrator
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
    Coordinates match discovery (Orchestrator) and player card scraping (Fetcher).
    Uses FlareSolverr (Docker) to bypass Cloudflare protection on HLTV.
    """
    logger.info("HLTV Sync Service Loop started.")

    # Import state_manager early for status updates
    from Programma_CS2_RENAN.backend.storage.state_manager import state_manager

    # --- Pre-flight: Auto-start FlareSolverr Docker container ---
    from Programma_CS2_RENAN.ingestion.hltv.docker_manager import ensure_flaresolverr

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

    orchestrator = HLTVOrchestrator()
    fetcher = HLTVStatFetcher()

    if STOP_SIGNAL.exists():
        os.remove(STOP_SIGNAL)

    while not STOP_SIGNAL.exists():
        try:
            state_manager.update_status(
                "hunter", "Running", f"Discovery cycle active at {time.ctime()}"
            )

            # 1. Sync Matches (Recent pro demos)
            logger.info("Starting match discovery cycle...")
            orchestrator.run_sync_cycle(limit=10)

            # 2. Sync Player Cards (Top 50 automatically)
            logger.info("Starting player card synchronization (Top 50)...")
            fetcher.fetch_top_players()

            # 3. Wait (Polite long-tail delay between full cycles)
            logger.info("Cycle complete. Sleeping for 1 hour...")
            _dormant_sleep(3600)

        except Exception as e:
            logger.error("Sync Loop Error: %s", e)
            time.sleep(60)  # Wait a minute before retry on crash

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

    # Launch main.py with --hltv-service flag to trigger run_sync_loop
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
            # On Windows, we might need a harder kill if it doesn't stop politely
            # but for now we rely on the loop checking the STOP_SIGNAL.
            logger.info("Background process %s will stop at next cycle check.", pid)
        except Exception as e:
            logger.warning("Failed to read PID file during stop: %s", e)


if __name__ == "__main__":
    # If run directly without flags, just run in-process (debug mode)
    run_sync_loop()
