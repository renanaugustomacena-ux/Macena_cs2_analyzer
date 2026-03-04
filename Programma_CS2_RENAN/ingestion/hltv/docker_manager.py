"""
FlareSolverr Docker lifecycle manager.

Ensures the FlareSolverr container is running before HLTV sync starts.
Provides auto-start via `docker start` or `docker-compose up -d`,
and graceful shutdown via `docker stop`.
"""

import subprocess
import time
from pathlib import Path

import requests

from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.docker_manager")

_HEALTH_URL = "http://localhost:8191/"
_HEALTH_TIMEOUT_S = 5
_MAX_WAIT_S = 45
_POLL_INTERVAL_S = 3


def _is_docker_available() -> bool:
    """Check if Docker CLI is reachable."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _is_flaresolverr_healthy() -> bool:
    """Check if FlareSolverr is responding on port 8191."""
    try:
        resp = requests.get(_HEALTH_URL, timeout=_HEALTH_TIMEOUT_S)
        return resp.status_code == 200
    except Exception:
        return False


def _wait_for_healthy(timeout_s: int = _MAX_WAIT_S) -> bool:
    """Poll health endpoint until ready or timeout."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _is_flaresolverr_healthy():
            return True
        time.sleep(_POLL_INTERVAL_S)
    return False


def ensure_flaresolverr(project_root: str | None = None) -> bool:
    """
    Ensure FlareSolverr Docker container is running.

    Returns True if container is healthy, False otherwise.

    Strategy:
    1. Already healthy? Return True immediately.
    2. Docker available? Try ``docker start flaresolverr``.
    3. Container doesn't exist? Try ``docker-compose up -d``.
    4. Wait for health check.
    """
    # Fast path: already running
    if _is_flaresolverr_healthy():
        logger.info("FlareSolverr already healthy.")
        return True

    if not _is_docker_available():
        logger.error(
            "Docker non disponibile. Installa Docker Desktop o avvia il daemon Docker."
        )
        return False

    # Try starting existing container
    logger.info("Avvio container FlareSolverr...")
    try:
        result = subprocess.run(
            ["docker", "start", "flaresolverr"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            logger.info("Container FlareSolverr avviato. Attendo health-check...")
            if _wait_for_healthy():
                logger.info("FlareSolverr pronto.")
                return True
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.debug("docker start failed: %s", exc)

    # Container doesn't exist — try docker-compose
    if project_root:
        compose_file = Path(project_root) / "docker-compose.yml"
        if compose_file.exists():
            logger.info("Container non trovato. Provo docker-compose up -d...")
            try:
                result = subprocess.run(
                    ["docker-compose", "-f", str(compose_file), "up", "-d"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    cwd=project_root,
                )
                if result.returncode == 0:
                    logger.info(
                        "docker-compose up riuscito. Attendo health-check..."
                    )
                    if _wait_for_healthy():
                        logger.info("FlareSolverr pronto via docker-compose.")
                        return True
            except (subprocess.TimeoutExpired, OSError) as exc:
                logger.debug("docker-compose failed: %s", exc)

    logger.error(
        "FlareSolverr non raggiungibile dopo tutti i tentativi. "
        "Verifica che Docker Desktop sia in esecuzione."
    )
    return False


def stop_flaresolverr() -> None:
    """Gracefully stop the FlareSolverr container."""
    try:
        subprocess.run(
            ["docker", "stop", "flaresolverr"],
            capture_output=True,
            timeout=15,
        )
        logger.info("FlareSolverr container fermato.")
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        logger.debug("FlareSolverr stop failed (non-critical): %s", exc)
