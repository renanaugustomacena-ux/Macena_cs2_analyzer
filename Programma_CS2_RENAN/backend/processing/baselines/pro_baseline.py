import os
from typing import Optional

import numpy as np
import pandas as pd
from sqlmodel import select

from Programma_CS2_RENAN.backend.storage.database import get_db_manager
from Programma_CS2_RENAN.backend.storage.db_models import ProPlayerStatCard
from Programma_CS2_RENAN.core.config import BASE_DIR
from Programma_CS2_RENAN.observability.logger_setup import get_logger

_logger = get_logger("cs2analyzer.pro_baseline")

EXTERNAL_DATA_DIR = os.path.join(BASE_DIR, "data", "external")

# Hard-coded Professional Standards (Used if DB is empty)
HARD_DEFAULT_BASELINE = {
    "rating": {"mean": 1.15, "std": 0.15},
    "kd_ratio": {"mean": 1.20, "std": 0.20},
    "avg_kills": {"mean": 0.78, "std": 0.12},
    "avg_deaths": {"mean": 0.62, "std": 0.08},
    "avg_adr": {"mean": 82.0, "std": 12.0},
    "avg_hs": {"mean": 0.52, "std": 0.10},
    "avg_kast": {"mean": 0.74, "std": 0.05},
    "accuracy": {"mean": 0.22, "std": 0.05},
    "positional_aggression_score": {"mean": 0.65, "std": 0.15},
    "utility_blind_time": {"mean": 12.0, "std": 4.0},
    "utility_enemies_blinded": {"mean": 2.2, "std": 0.8},
    "opening_duel_win_pct": {"mean": 0.55, "std": 0.10},
    "clutch_win_pct": {"mean": 0.35, "std": 0.12},
    # HLTV 2.0 Explicit Components
    "rating_impact": {"mean": 1.10, "std": 0.20},
    "rating_survival": {"mean": 0.38, "std": 0.08},
    "rating_kast": {"mean": 0.74, "std": 0.05},
}


def get_pro_baseline(map_name: Optional[str] = None):
    """
    Returns the pro baseline statistics.

    Task 2.18.1: Now supports map-specific baselines for more accurate
    per-map coaching comparisons (e.g., AWP stats differ Dust2 vs Inferno).

    Args:
        map_name: Optional CS2 map name (e.g., 'de_mirage', 'de_nuke').
                  If provided, only stats from that map are aggregated.
                  If None, returns global baseline across all maps.

    Returns:
        dict: Baseline statistics with 'mean' and 'std' for each metric.
    """
    db_baseline = _load_pro_from_db(map_name=map_name)
    if db_baseline:
        return db_baseline

    csv_path = os.path.join(EXTERNAL_DATA_DIR, "all_Time_best_Players_Stats.csv")
    if os.path.exists(csv_path):
        _logger.info("DB baseline empty — falling back to CSV: %s", csv_path)
        return _load_pro_from_csv(csv_path)
    _logger.warning(
        "No DB or CSV pro data found (path checked: %s). "
        "Falling back to HARD_DEFAULT_BASELINE — coaching quality is degraded.",
        csv_path,
    )
    return _get_default_pro_baseline()


def _load_pro_from_db(map_name: Optional[str] = None):
    """
    Aggregates ProPlayerStatCards into a single Gaussian baseline.

    Task 2.18.1: Now supports map-specific filtering.

    Args:
        map_name: Optional map filter (e.g., 'de_mirage').
    """
    db = get_db_manager()
    try:
        with db.get_session() as s:
            query = select(ProPlayerStatCard).limit(5000)
            if map_name:
                # Filter by map name for map-specific baseline
                query = query.where(ProPlayerStatCard.map_name == map_name)
            cards = s.exec(query).all()
            if not cards:
                return None

            # Map DB cards to standard baseline structure, grouping by player_id first
            player_stats = {}
            for c in cards:
                pid = c.player_id if c.player_id else c.name
                if pid not in player_stats:
                    player_stats[pid] = {
                        "rating": [],
                        "kd_ratio": [],
                        "avg_kills": [],
                        "avg_deaths": [],
                        "avg_adr": [],
                        "avg_kast": [],
                        "rating_impact": [],
                        "rating_survival": [],
                        "rating_kast": [],
                    }

                stats = player_stats[pid]
                stats["rating"].append(c.rating_2_0)
                stats["kd_ratio"].append(c.kpr / max(0.1, c.dpr))
                stats["avg_kills"].append(c.kpr)
                stats["avg_deaths"].append(c.dpr)
                stats["avg_adr"].append(c.adr)
                stats["avg_kast"].append(c.kast)
                stats["rating_impact"].append(c.impact)
                stats["rating_survival"].append(1.0 - c.dpr)
                stats["rating_kast"].append(c.kast)

            # Average per player, then flatten for global baseline
            data = {k: [] for k in player_stats[next(iter(player_stats))].keys()}
            for pid, metrics in player_stats.items():
                for key, values in metrics.items():
                    data[key].append(np.mean(values))

            baseline = {}
            for feat, vals in data.items():
                std_val = float(np.std(vals))
                if std_val == 0.0:
                    _logger.warning(
                        "Pro baseline std=0 for '%s' (%d samples) — Z-scores for this metric will be skipped",
                        feat,
                        len(vals),
                    )
                # std=0.0 is safe — downstream calculate_deviations() handles div-by-zero
                baseline[feat] = {"mean": float(np.mean(vals)), "std": std_val}
            return baseline
    except Exception as e:
        _logger.error("Failed to load pro baseline from DB: %s", e)
        return None


def _load_pro_from_csv(path):
    try:
        df = pd.read_csv(path)
        baseline = {
            "rating": {"mean": df["Rating1.0"].mean(), "std": df["Rating1.0"].std()},
            "kd_ratio": {"mean": df["K/D"].mean(), "std": df["K/D"].std()},
            "avg_adr": {"mean": 80.0, "std": 15.0},  # Fallbacks for common missing columns
        }

        # Merge with HARD defaults for any missing keys
        defaults = _get_default_pro_baseline()
        for k, v in defaults.items():
            if k not in baseline:
                baseline[k] = v

        # Override specific known CSV columns if present
        # (This logic can be expanded as CSV format evolves)

        return baseline
    except Exception as e:
        _logger.error("Failed to load pro baseline from CSV '%s': %s", path, e)
        return _get_default_pro_baseline()


def _get_default_pro_baseline():
    _logger.warning(
        "Using HARD_DEFAULT_BASELINE (no DB or CSV pro data). "
        "Coaching quality is DEGRADED — Z-scores are based on hardcoded values, not empirical data."
    )
    result = dict(HARD_DEFAULT_BASELINE)
    result["_provenance"] = "hard_default"
    return result


def get_pro_positions(map_name: str, max_positions: int = 10000) -> list[tuple[float, float]]:
    """
    Retrieves aggregated (x, y) world-coordinate positions from pro match databases.

    Scans all per-match SQLite files for matches flagged as ``is_pro_match=True``
    on the requested map, then samples alive-player ticks for their positions.

    Args:
        map_name: CS2 map identifier (e.g. "de_mirage").
        max_positions: Cap on returned positions to bound memory/computation.

    Returns:
        List of (x, y) world-coordinate tuples, or empty list if no pro data.
    """
    try:
        from sqlmodel import select as sel

        from Programma_CS2_RENAN.backend.storage.match_data_manager import (
            MatchMetadata,
            MatchTickState,
            get_match_data_manager,
        )

        mdm = get_match_data_manager()
        all_positions: list[tuple[float, float]] = []

        for match_id in mdm.list_available_matches():
            with mdm.get_match_session(match_id) as session:
                meta = session.exec(
                    sel(MatchMetadata).where(MatchMetadata.match_id == match_id)
                ).first()
                if not meta or not meta.is_pro_match:
                    continue
                if meta.map_name != map_name:
                    continue

                # Fetch alive-player positions (sample every 64th tick for density)
                ticks = session.exec(
                    sel(MatchTickState.pos_x, MatchTickState.pos_y)
                    .where(MatchTickState.is_alive == True)  # noqa: E712
                    .where(MatchTickState.tick % 64 == 0)
                ).all()

                for row in ticks:
                    all_positions.append((row[0], row[1]))

            if len(all_positions) >= max_positions:
                break

        # Cap to max_positions via uniform sampling
        if len(all_positions) > max_positions:
            step = len(all_positions) / max_positions
            all_positions = [all_positions[int(i * step)] for i in range(max_positions)]

        return all_positions

    except Exception as e:
        _logger.warning("Failed to retrieve pro positions for %s: %s", map_name, e)
        return []


def calculate_deviations(player_stats, baseline):
    """
    Calculates Z-scores for player stats compared to baseline.
    Robust against division-by-zero.
    """
    deviations = {}
    for feature, values in baseline.items():
        if feature in player_stats:
            if isinstance(values, dict):
                mean = values["mean"]
                std = values.get("std", 0.0)
            else:
                mean = float(values)
                std = 0.0

            raw_dev = player_stats[feature] - mean

            if std <= 0.0:
                # Cannot compute valid Z-score without variance — skip metric
                _logger.debug(
                    "Skipping Z-score for '%s': std=%.4f (insufficient variance)", feature, std
                )
                deviations[feature] = (0.0, raw_dev)
            else:
                z_score = raw_dev / std
                deviations[feature] = (z_score, raw_dev)

    return deviations


# ---------------------------------------------------------------------------
# Temporal Baseline Decay (Fusion Plan Proposal 11)
# ---------------------------------------------------------------------------

import math
from datetime import datetime, timezone
from typing import List

from Programma_CS2_RENAN.observability.logger_setup import get_logger

_baseline_logger = get_logger("cs2analyzer.baseline.temporal")


class TemporalBaselineDecay:
    """
    Time-weighted pro baselines so that recent pro stats carry more influence
    than historical data, adapting to CS2's evolving meta.

    This class WRAPS (not replaces) the existing get_pro_baseline() function.
    Call get_temporal_baseline() instead when recency matters.

    Usage:
        decay = TemporalBaselineDecay()
        baseline = decay.get_temporal_baseline(map_name="de_mirage")
    """

    HALF_LIFE_DAYS: float = 90.0  # Weight halves every 90 days
    MIN_WEIGHT: float = 0.1  # Floor weight for very old data
    META_SHIFT_THRESHOLD: float = 0.05  # 5% change flags a meta shift

    # Metrics to track for baseline computation
    BASELINE_METRICS = [
        "rating_2_0",
        "kpr",
        "dpr",
        "kast",
        "impact",
        "adr",
        "headshot_pct",
        "opening_kill_ratio",
        "opening_duel_win_pct",
    ]

    def compute_weight(
        self, stat_date: datetime, reference_date: Optional[datetime] = None
    ) -> float:
        """
        Exponential decay weight based on data age.

        Args:
            stat_date: When the stat was recorded.
            reference_date: Reference point (default: now).

        Returns:
            Weight in [MIN_WEIGHT, 1.0].
        """
        if reference_date is None:
            reference_date = datetime.now(timezone.utc)

        age_days = (reference_date - stat_date).total_seconds() / 86400.0
        if age_days <= 0:
            return 1.0

        weight = math.exp(-0.693 * age_days / self.HALF_LIFE_DAYS)  # ln(2) ~ 0.693
        return max(self.MIN_WEIGHT, weight)

    def compute_weighted_baseline(
        self,
        stat_cards: list,
    ) -> dict:
        """
        Weighted average of pro stats with temporal decay.

        Args:
            stat_cards: List of ProPlayerStatCard objects (must have last_updated field).

        Returns:
            Baseline dict with {metric: {"mean": ..., "std": ...}} structure,
            compatible with the existing baseline format.
        """
        if not stat_cards:
            return {}

        weights = []
        metric_values: dict = {m: [] for m in self.BASELINE_METRICS}

        for card in stat_cards:
            card_date = getattr(card, "last_updated", None)
            if card_date is None:
                w = 0.5  # Unknown date gets middle weight
            else:
                w = self.compute_weight(card_date)
            weights.append(w)

            for metric in self.BASELINE_METRICS:
                val = getattr(card, metric, None)
                if val is not None:
                    metric_values[metric].append((float(val), w))

        baseline = {}
        for metric, weighted_pairs in metric_values.items():
            if not weighted_pairs:
                continue

            values, ws = zip(*weighted_pairs)
            total_w = sum(ws)
            if total_w < 1e-6:
                continue

            w_mean = sum(v * w for v, w in zip(values, ws)) / total_w

            # Weighted standard deviation
            w_var = sum(w * (v - w_mean) ** 2 for v, w in zip(values, ws)) / total_w
            w_std = max(math.sqrt(w_var), 0.01)

            # Map to the standard baseline key names
            baseline_key = self._metric_to_baseline_key(metric)
            baseline[baseline_key] = {"mean": w_mean, "std": w_std}

        return baseline

    def get_temporal_baseline(self, map_name: Optional[str] = None) -> dict:
        """
        Get a time-weighted pro baseline. Falls back to legacy if insufficient data.

        This WRAPS the existing get_pro_baseline() — does not replace it.

        Args:
            map_name: Optional map filter.

        Returns:
            Baseline dict compatible with existing code.
        """
        try:
            db = get_db_manager()
            with db.get_session() as session:
                query = select(ProPlayerStatCard)
                cards = session.exec(query).all()

            if len(cards) >= 10:
                temporal = self.compute_weighted_baseline(cards)
                if temporal:
                    # Merge with legacy defaults for any missing keys
                    legacy = get_pro_baseline(map_name)
                    merged = dict(legacy)
                    merged.update(temporal)
                    _baseline_logger.info(
                        f"Temporal baseline computed from {len(cards)} stat cards"
                    )
                    return merged

        except Exception as e:
            _baseline_logger.warning("Temporal baseline fallback: %s", e)

        # Fallback to existing non-temporal baseline
        return get_pro_baseline(map_name)

    def detect_meta_shift(self, old_baseline: dict, new_baseline: dict) -> List[str]:
        """
        Detect significant meta shifts by comparing baseline epochs.

        Args:
            old_baseline: Previous baseline dict.
            new_baseline: Current baseline dict.

        Returns:
            List of metric names that shifted significantly.
        """
        shifted = []
        for metric in old_baseline:
            if metric.startswith("_"):
                continue
            if metric not in new_baseline:
                continue
            old_val = old_baseline[metric]
            new_val = new_baseline[metric]
            # Skip non-numeric entries (e.g. _provenance="hard_default")
            if not isinstance(old_val, (int, float, dict)):
                continue
            if not isinstance(new_val, (int, float, dict)):
                continue
            old_mean = (
                old_val.get("mean", 0)
                if isinstance(old_val, dict)
                else old_val
            )
            new_mean = (
                new_val.get("mean", 0)
                if isinstance(new_val, dict)
                else new_val
            )

            if old_mean == 0:
                continue

            ratio = new_mean / old_mean
            if abs(1.0 - ratio) > self.META_SHIFT_THRESHOLD:
                shifted.append(metric)
                _baseline_logger.info(
                    f"Meta shift detected: {metric} changed by {(ratio - 1.0) * 100:.1f}%"
                )

        return shifted

    @staticmethod
    def _metric_to_baseline_key(metric: str) -> str:
        """Map ProPlayerStatCard field names to baseline dict key names."""
        mapping = {
            "rating_2_0": "rating",
            "kpr": "avg_kills",
            "dpr": "avg_deaths",
            "kast": "avg_kast",
            "impact": "rating_impact",
            "adr": "avg_adr",
            "headshot_pct": "avg_hs",
            "opening_kill_ratio": "opening_duel_win_pct",
            "opening_duel_win_pct": "opening_duel_win_pct",
        }
        return mapping.get(metric, metric)
