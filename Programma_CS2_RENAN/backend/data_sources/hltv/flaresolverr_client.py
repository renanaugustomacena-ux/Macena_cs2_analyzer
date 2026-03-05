"""
FlareSolverr client — bypasses Cloudflare via local Docker proxy.

FlareSolverr runs as a Docker container on port 8191 and exposes a REST API
that handles Cloudflare challenges automatically using a headless browser.

Setup:
    docker pull ghcr.io/flaresolverr/flaresolverr:latest
    docker run -d --name flaresolverr -p 8191:8191 \
        -e LOG_LEVEL=info -e TZ=Europe/Rome \
        --restart unless-stopped \
        ghcr.io/flaresolverr/flaresolverr:latest
"""

from __future__ import annotations

import requests

from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.flaresolverr")

_DEFAULT_URL = "http://localhost:8191/v1"
_DEFAULT_TIMEOUT = 60


class FlareSolverrClient:
    """REST client for the local FlareSolverr Docker container."""

    def __init__(
        self,
        base_url: str = _DEFAULT_URL,
        timeout: int = _DEFAULT_TIMEOUT,
    ):
        self._base_url = base_url
        self._timeout = timeout
        self._session_id: str | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return True if the FlareSolverr container is reachable."""
        try:
            # FlareSolverr health check is on root /, not /v1
            health_url = self._base_url.replace("/v1", "")
            resp = requests.get(health_url, timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def create_session(self) -> str | None:
        """Create a persistent browser session for cookie reuse."""
        try:
            resp = requests.post(
                self._base_url,
                json={"cmd": "sessions.create"},
                timeout=15,
            )
            data = resp.json()
            if data.get("status") == "ok":
                self._session_id = data["session"]
                logger.info("FlareSolverr session created: %s", self._session_id)
                return self._session_id
            logger.warning("FlareSolverr session.create returned: %s", data.get("message"))
        except requests.exceptions.ConnectionError:
            logger.error(
                "FlareSolverr non raggiungibile su %s — il container Docker e' attivo?",
                self._base_url,
            )
        except Exception as exc:
            logger.warning("Failed to create FlareSolverr session: %s", exc)
        return None

    def destroy_session(self) -> None:
        """Destroy the current persistent session."""
        if not self._session_id:
            return
        try:
            requests.post(
                self._base_url,
                json={"cmd": "sessions.destroy", "session": self._session_id},
                timeout=10,
            )
            logger.info("FlareSolverr session destroyed: %s", self._session_id)
        except Exception:
            pass
        self._session_id = None

    # ------------------------------------------------------------------
    # HTTP verbs
    # ------------------------------------------------------------------

    def get(self, url: str) -> str | None:
        """Fetch *url* through FlareSolverr, returning the decoded HTML body.

        Returns ``None`` on any error (network, Cloudflare block, timeout).
        """
        payload: dict = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": self._timeout * 1000,
        }
        if self._session_id:
            payload["session"] = self._session_id

        try:
            resp = requests.post(
                self._base_url,
                json=payload,
                timeout=self._timeout + 15,
            )
            data = resp.json()

            if data.get("status") == "ok":
                solution = data.get("solution", {})
                status_code = solution.get("status", 0)
                if status_code == 200:
                    logger.info("FlareSolverr: OK for %s", url)
                    return solution.get("response", "")
                logger.warning(
                    "FlareSolverr: HTTP %s for %s",
                    status_code,
                    url,
                )
            else:
                logger.error("FlareSolverr error: %s", data.get("message"))

        except requests.exceptions.ConnectionError:
            logger.error(
                "FlareSolverr non raggiungibile su %s — il container Docker e' attivo?",
                self._base_url,
            )
        except requests.exceptions.Timeout:
            logger.error(
                "FlareSolverr timeout (%ss) per %s",
                self._timeout,
                url,
            )
        except Exception as exc:
            logger.error("FlareSolverr request failed: %s", exc)

        return None
