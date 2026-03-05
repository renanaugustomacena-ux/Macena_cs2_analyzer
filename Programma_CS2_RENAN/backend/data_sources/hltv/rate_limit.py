import random
import time

from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.hltv.rate_limit")


class RateLimiter:
    def __init__(self):
        # Different "gears" for different actions
        self.delays = {
            "micro": (2.0, 3.5),  # Increased to meet 2s minimum
            "standard": (4.0, 8.0),  # Page navigation
            "heavy": (10.0, 20.0),  # Transition between sections
            "backoff": (45.0, 90.0),  # After a suspected block or failure
        }

    def wait(self, tier="standard"):
        min_d, max_d = self.delays.get(tier, self.delays["standard"])
        # F6-25: Randomness intentionally unseeded — deterministic jitter would create
        # detectable request patterns. Anti-scraping detection relies on apparent human randomness.
        jitter = random.uniform(-0.5, 0.5)
        # Ensure the final delay is never below 2.0 seconds
        delay = max(2.0, random.uniform(min_d, max_d) + jitter)
        logger.debug("[Limiter] Sleeping for %.2fs (Tier: %s)", delay, tier)  # F6-05
        time.sleep(delay)

    def random_combination(self):
        """Randomizes sequence of small waits to mimic human reading."""
        for _ in range(random.randint(1, 3)):
            self.wait("micro")
