import json
import os
import time

import httpx

from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.telemetry")

# Configurable via env var; defaults to localhost for dev. Set CS2_TELEMETRY_URL in production.
DEV_SERVER_URL = os.getenv("CS2_TELEMETRY_URL", "http://127.0.0.1:8000")


def send_match_telemetry(player_id: str, match_id: str, stats: dict):
    """
    Sends match statistics to the central ML Coach server.
    """
    payload = {
        "player_id": player_id,
        "match_id": match_id,
        "stats": stats,
        "timestamp": time.time(),
    }

    try:
        logger.info("[*] Sending telemetry to %s...", DEV_SERVER_URL)
        with httpx.Client() as client:
            response = client.post(
                f"{DEV_SERVER_URL}/api/ingest/telemetry", json=payload, timeout=10.0
            )

        if response.status_code == 200:
            logger.info("[+] Data successfully sent to the Coach.")
            return True
        else:
            logger.error("[-] Failed to send data: %s - %s", response.status_code, response.text)
            return False

    except Exception as e:
        logger.error("[!] Connection error: %s", e)
        logger.error("    (Ensure the Developer's Server is running and accessible)")
        return False


if __name__ == "__main__":
    # No synthetic test data here — fabricated stats violate the Anti-Fabrication Rule
    # and mismatched field names (kills/deaths vs avg_kills/avg_deaths) would mislead.
    # Use real match data from the DB for manual testing.
    logger.info("telemetry_client ready; invoke send_match_telemetry() with real match data.")
