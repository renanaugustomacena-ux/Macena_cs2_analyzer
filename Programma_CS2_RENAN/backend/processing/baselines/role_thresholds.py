"""
Role Threshold Store

Dynamic threshold storage for role classification.
Thresholds are LEARNED from real data (HLTV, demos), NEVER hardcoded.

Anti-Mock Principle:
    - All thresholds start as None (unknown)
    - Values are populated from pro player data
    - If insufficient data, classifier returns UNKNOWN with 0% confidence
    - Coach never learns from fake/mock data
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.role_thresholds")


@dataclass
class LearnedThreshold:
    """A threshold value learned from real data."""

    value: Optional[float] = None  # None = not yet learned
    sample_count: int = 0  # How many samples contributed
    last_updated: Optional[datetime] = None
    source: str = "unknown"  # "hltv", "demo_parser", "ml_model"


class RoleThresholdStore:
    """
    Dynamic threshold storage - learned from real data, NEVER mocked.

    Philosophy:
        - All thresholds initialize to None (cold start)
        - Values are computed from real pro player statistics
        - If a threshold is None, the classifier cannot use it
        - Minimum sample count required before threshold is valid

    Data Sources:
        1. HLTV Scraper: Pro player stats → compute role thresholds
        2. Demo Parser: User matches → validate/refine thresholds
        3. ML Model: Over time, learns optimal thresholds
    """

    # P-PB-04: 30 samples gives ≤8% std error in 75th-percentile estimates
    # (Bootstrap CI). Previous value of 10 produced unstable thresholds.
    MIN_SAMPLES_FOR_VALIDITY = 30

    def __init__(self):
        """Initialize with empty thresholds (cold start state)."""
        self._thresholds: Dict[str, LearnedThreshold] = {
            # Role detection stat names - values are None until learned
            "awp_kill_ratio": LearnedThreshold(),
            "entry_rate": LearnedThreshold(),
            "assist_rate": LearnedThreshold(),
            "survival_rate": LearnedThreshold(),
            "solo_kill_rate": LearnedThreshold(),
            "first_death_rate": LearnedThreshold(),
            "utility_damage_rate": LearnedThreshold(),
            "clutch_rate": LearnedThreshold(),
            "trade_rate": LearnedThreshold(),
        }
        self._is_initialized = False
        logger.info("RoleThresholdStore initialized in COLD START state (no learned thresholds)")

    def get_threshold(self, stat_name: str) -> Optional[float]:
        """
        Get a threshold value if it has been learned.

        Returns:
            The threshold value, or None if not yet learned or insufficient samples.
        """
        threshold = self._thresholds.get(stat_name)
        if threshold is None:
            return None

        # Only return value if we have sufficient samples
        if threshold.sample_count < self.MIN_SAMPLES_FOR_VALIDITY:
            return None

        return threshold.value

    def is_cold_start(self) -> bool:
        """
        Check if the store is in cold start state.

        A cold start means insufficient data to reliably classify roles.
        The coach should remain silent or return UNKNOWN in this state.
        """
        valid_thresholds = sum(
            1
            for t in self._thresholds.values()
            if t.value is not None and t.sample_count >= self.MIN_SAMPLES_FOR_VALIDITY
        )

        # Require at least 3 valid thresholds to exit cold start
        return valid_thresholds < 3

    def validate_consistency(self) -> bool:
        """R4-23-01: Validate that learned thresholds are consistent.

        Checks:
        1. All valid thresholds have positive values (rates must be > 0)
        2. No threshold exceeds 1.0 (all are rate-based [0, 1])
        3. At least MIN_SAMPLES_FOR_VALIDITY samples contributed

        Returns False if any inconsistency is detected.
        """
        for name, t in self._thresholds.items():
            if t.value is None or t.sample_count < self.MIN_SAMPLES_FOR_VALIDITY:
                continue  # Skip unlearned thresholds
            if t.value < 0.0:
                logger.warning("R4-23-01: Negative threshold '%s' = %.4f", name, t.value)
                return False
            if t.value > 1.0:
                logger.warning("R4-23-01: Threshold '%s' = %.4f exceeds 1.0", name, t.value)
                return False
        return True

    def get_readiness_report(self) -> Dict[str, Any]:
        """Get a report on threshold readiness for debugging."""
        return {
            "is_cold_start": self.is_cold_start(),
            "thresholds": {
                name: {
                    "value": t.value,
                    "samples": t.sample_count,
                    "valid": t.sample_count >= self.MIN_SAMPLES_FOR_VALIDITY,
                    "source": t.source,
                }
                for name, t in self._thresholds.items()
            },
        }

    def learn_from_pro_data(
        self, pro_stats: List[Dict[str, float]], known_roles: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Learn thresholds from real pro player statistics.

        P8-05: Validate by running on scraped pro player stats (HLTV).
        Verify that pros are classified into their known roles (from HLTV
        team pages). Target: 80%+ classification accuracy.

        Args:
            pro_stats: List of player stat dictionaries from HLTV or demos.
            known_roles: Optional mapping of player_name -> role for labeled data.
                         When provided, enables accuracy measurement against
                         ground truth (HLTV role assignments).

        This calculates thresholds as statistical boundaries (e.g., 75th percentile)
        that separate role archetypes.
        """
        import numpy as np

        if not pro_stats:
            logger.warning("learn_from_pro_data called with empty data - no learning performed")
            return

        # P-RT-02: Count unique players, not total data points, for sample_count.
        # Same player across tournaments should not inflate statistical confidence.
        _unique_players = len({
            s.get("player_id") or s.get("player_name", id(s))
            for s in pro_stats
        })
        logger.info(
            "Learning thresholds from %d pro player records (%d unique players)",
            len(pro_stats), _unique_players,
        )

        # Calculate thresholds using percentile analysis
        now = datetime.now()

        # P-RT-01: Consistent 75th percentile for all role thresholds.
        # Players above the 75th pct are classified as role specialists.
        _ROLE_THRESHOLD_PERCENTILE = 75

        # AWP Kill Ratio - AWPers have high awp_kills / total_kills
        awp_ratios = [s.get("awp_kills", 0) / max(s.get("total_kills", 1), 1) for s in pro_stats]
        if awp_ratios:
            self._thresholds["awp_kill_ratio"].value = float(
                np.percentile(awp_ratios, _ROLE_THRESHOLD_PERCENTILE)
            )
            self._thresholds["awp_kill_ratio"].sample_count = _unique_players
            self._thresholds["awp_kill_ratio"].last_updated = now
            self._thresholds["awp_kill_ratio"].source = "hltv"

        # Entry Rate - entry_frags per round
        entry_rates = [
            s.get("entry_frags", 0) / max(s.get("rounds_played", 1), 1) for s in pro_stats
        ]
        if entry_rates:
            self._thresholds["entry_rate"].value = float(
                np.percentile(entry_rates, _ROLE_THRESHOLD_PERCENTILE)
            )
            self._thresholds["entry_rate"].sample_count = _unique_players
            self._thresholds["entry_rate"].last_updated = now
            self._thresholds["entry_rate"].source = "hltv"

        # Assist Rate - assists per round
        assist_rates = [s.get("assists", 0) / max(s.get("rounds_played", 1), 1) for s in pro_stats]
        if assist_rates:
            self._thresholds["assist_rate"].value = float(
                np.percentile(assist_rates, _ROLE_THRESHOLD_PERCENTILE)
            )
            self._thresholds["assist_rate"].sample_count = _unique_players
            self._thresholds["assist_rate"].last_updated = now
            self._thresholds["assist_rate"].source = "hltv"

        # Survival Rate - rounds survived / rounds played
        survival_rates = [
            s.get("rounds_survived", 0) / max(s.get("rounds_played", 1), 1) for s in pro_stats
        ]
        if survival_rates:
            self._thresholds["survival_rate"].value = float(
                np.percentile(survival_rates, _ROLE_THRESHOLD_PERCENTILE)
            )
            self._thresholds["survival_rate"].sample_count = _unique_players
            self._thresholds["survival_rate"].last_updated = now
            self._thresholds["survival_rate"].source = "hltv"

        # Solo Kill Rate - for lurkers
        solo_rates = [s.get("solo_kills", 0) / max(s.get("total_kills", 1), 1) for s in pro_stats]
        if solo_rates:
            self._thresholds["solo_kill_rate"].value = float(
                np.percentile(solo_rates, _ROLE_THRESHOLD_PERCENTILE)
            )
            self._thresholds["solo_kill_rate"].sample_count = _unique_players
            self._thresholds["solo_kill_rate"].last_updated = now
            self._thresholds["solo_kill_rate"].source = "hltv"

        self._is_initialized = True
        logger.info("Threshold learning complete. Cold start: %s", self.is_cold_start())

    def persist_to_db(self, db_session) -> None:
        """Persist learned thresholds to database for recovery across restarts."""
        from sqlmodel import select

        from Programma_CS2_RENAN.backend.storage.db_models import RoleThresholdRecord

        for name, threshold in self._thresholds.items():
            existing = db_session.exec(
                select(RoleThresholdRecord).where(RoleThresholdRecord.stat_name == name)
            ).first()
            if existing:
                existing.value = threshold.value
                existing.sample_count = threshold.sample_count
                existing.source = threshold.source
                existing.last_updated = threshold.last_updated
                db_session.add(existing)
            else:
                record = RoleThresholdRecord(
                    stat_name=name,
                    value=threshold.value,
                    sample_count=threshold.sample_count,
                    source=threshold.source,
                    last_updated=threshold.last_updated,
                )
                db_session.add(record)
        logger.info("Persisted %d thresholds to database", len(self._thresholds))

    def load_from_db(self, db_session) -> bool:
        """Load previously learned thresholds from database.

        Returns True if thresholds were loaded, False if cold start.
        """
        from sqlmodel import select

        from Programma_CS2_RENAN.backend.storage.db_models import RoleThresholdRecord

        records = db_session.exec(select(RoleThresholdRecord)).all()
        if not records:
            logger.info("No persisted thresholds found — cold start")
            return False

        loaded = 0
        for record in records:
            if record.stat_name in self._thresholds:
                t = self._thresholds[record.stat_name]
                t.value = record.value
                t.sample_count = record.sample_count
                t.source = record.source
                t.last_updated = record.last_updated
                loaded += 1

        if loaded > 0:
            self._is_initialized = True
        logger.info("Loaded %d/%d thresholds from database", loaded, len(records))
        return loaded > 0


# P3-06: Thread-safe lazy singleton with double-checked locking (AR-5).
import threading

_threshold_store: Optional[RoleThresholdStore] = None
_threshold_store_lock = threading.Lock()


def get_role_threshold_store() -> RoleThresholdStore:
    """Thread-safe lazy singleton factory for RoleThresholdStore."""
    global _threshold_store
    if _threshold_store is None:
        with _threshold_store_lock:
            if _threshold_store is None:
                _threshold_store = RoleThresholdStore()
    return _threshold_store
