"""
Belief-Based Death Assessment (Phase 6: Game Theory)

Implements a Bayesian belief model that estimates the probability of a player's
death given the current game state, factoring in information asymmetry
(what each team knows vs. doesn't know).

Governance: Rule 1 §7.1 (Probabilistic reasoning over deterministic heuristics)
"""

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.analysis.belief")

# Default death-rate priors by HP bracket (from CS2 round statistics)
_DEFAULT_PRIORS: Dict[str, float] = {
    "full": 0.35,  # 80-100 HP
    "damaged": 0.55,  # 40-79 HP
    "critical": 0.80,  # 1-39 HP
}

# Weapon lethality multipliers (relative to baseline)
_WEAPON_LETHALITY: Dict[str, float] = {
    "rifle": 1.0,
    "awp": 1.4,
    "smg": 0.75,
    "pistol": 0.6,
    "shotgun": 0.85,
    "knife": 0.3,
    "unknown": 1.0,
}

# Maximum rows fetched from RoundStats for belief calibration (F4-01).
# Prevents OOM when demo count grows into the thousands. 5 000 rounds
# is sufficient for reliable empirical priors.
MAX_CALIBRATION_SAMPLES: int = 5_000


@dataclass
class BeliefState:
    """Represents the information-asymmetry state for a player."""

    visible_enemies: int = 0
    inferred_enemies: int = 0
    information_age: float = 0.0
    positional_exposure: float = 0.0

    # P8-01: Threat decay rate (lambda). Controls how quickly inferred enemy
    # positions lose credibility as information ages.
    # Source: hand-tuned for CS2 round pacing (~7-tick half-life at 64 Hz).
    # Validation: AdaptiveBeliefCalibrator.calibrate_threat_decay() fits this
    # via least-squares on engagement data. Run auto_calibrate() with 100+
    # parsed demos to obtain empirical value. Bounded to [0.01, 1.0].
    THREAT_DECAY_LAMBDA: float = 0.1

    def threat_level(self) -> float:
        """Combined threat from visible + inferred enemies, decayed by info age."""
        decay = math.exp(-self.THREAT_DECAY_LAMBDA * self.information_age)
        return (self.visible_enemies + self.inferred_enemies * decay * 0.5) / 5.0


@dataclass
class DeathProbabilityEstimator:
    """
    Bayesian estimator for P(death | belief, HP, armor, weapon_class).

    Uses calibrated priors from historical round data when available,
    falling back to domain-default priors.
    """

    priors: Dict[str, float] = field(default_factory=lambda: dict(_DEFAULT_PRIORS))
    _calibrated: bool = False

    def estimate(
        self,
        belief: BeliefState,
        player_hp: int,
        armor: bool,
        weapon_class: str,
    ) -> float:
        """
        Estimate death probability via Bayesian update.

        Args:
            belief: Current information-asymmetry state.
            player_hp: Player health (0-100).
            armor: Whether the player has armor.
            weapon_class: Category of enemy weapon (rifle, awp, smg, pistol, etc.).

        Returns:
            P(death) in [0.0, 1.0].
        """
        # 1. Prior: base death rate for HP bracket
        bracket = self._hp_to_bracket(player_hp)
        prior = self.priors.get(bracket, 0.5)

        # 2. Likelihood adjustments
        # Threat level from belief state
        threat = belief.threat_level()

        # Armor reduces effective damage
        armor_factor = 0.75 if armor else 1.0

        # Weapon lethality of enemies
        weapon_mult = _WEAPON_LETHALITY.get(weapon_class, 1.0)

        # Positional exposure amplifies risk
        exposure_factor = 0.5 + 0.5 * belief.positional_exposure

        # 3. Bayesian-inspired posterior (logistic combination)
        # P8-02: Log-odds weights. Hand-tuned; validate via logistic regression
        # on actual death outcomes with (threat, weapon, armor, exposure) as inputs.
        # Use regression coefficients as empirically validated replacements.
        # AdaptiveBeliefCalibrator.auto_calibrate() calibrates priors and lethality
        # but not these weights directly — future: grid search over weight space.
        log_odds = math.log(prior / max(1e-6, 1.0 - prior))
        log_odds += threat * 2.0        # threat sensitivity
        log_odds += (weapon_mult - 1.0) * 1.5  # weapon lethality amplification
        log_odds += (armor_factor - 1.0) * -1.0  # armor damage reduction
        log_odds += (exposure_factor - 0.5) * 1.0  # positional exposure risk

        posterior = 1.0 / (1.0 + math.exp(-log_odds))
        return max(0.0, min(1.0, posterior))

    def is_high_risk(self, probability: float, threshold: float = 0.6) -> bool:
        """Flag high-risk positions."""
        return probability > threshold

    # AC-05-01: Minimum samples for statistically meaningful calibration
    MIN_CALIBRATION_SAMPLES: int = 30

    def calibrate(self, historical_rounds: pd.DataFrame) -> None:
        """
        Learn priors from labeled historical round data.

        Expects columns: 'health', 'died' (bool), 'round_id'.
        Groups by HP bracket and computes empirical death rate.
        """
        if historical_rounds.empty:
            logger.warning("Empty calibration data, keeping default priors")
            return

        if len(historical_rounds) < self.MIN_CALIBRATION_SAMPLES:
            logger.warning(
                "AC-05-01: Insufficient death events for calibration (%d < %d). "
                "Keeping default priors to avoid overfitting to sparse data.",
                len(historical_rounds), self.MIN_CALIBRATION_SAMPLES,
            )
            return

        required = {"health", "died"}
        if not required.issubset(historical_rounds.columns):
            logger.error(
                "Calibration data missing columns: %s", required - set(historical_rounds.columns)
            )
            return

        df = historical_rounds.copy()
        df["bracket"] = df["health"].apply(self._hp_to_bracket)

        for bracket, group in df.groupby("bracket"):
            if len(group) >= 10:
                rate = group["died"].mean()
                self.priors[bracket] = float(rate)

        self._calibrated = True
        logger.info("Calibrated death priors: %s", self.priors)

    @staticmethod
    def _hp_to_bracket(hp: int) -> str:
        if hp >= 80:
            return "full"
        elif hp >= 40:
            return "damaged"
        return "critical"


# P3-10: Thread-safe lazy singleton with double-checked locking (AR-5).
import threading

_death_estimator: Optional[DeathProbabilityEstimator] = None
_death_estimator_lock = threading.Lock()


def get_death_estimator() -> DeathProbabilityEstimator:
    """Thread-safe lazy singleton factory for DeathProbabilityEstimator."""
    global _death_estimator
    if _death_estimator is None:
        with _death_estimator_lock:
            if _death_estimator is None:
                _death_estimator = DeathProbabilityEstimator()
    return _death_estimator


# ---------------------------------------------------------------------------
# Adaptive Belief Calibration (Fusion Plan Proposal 6)
# ---------------------------------------------------------------------------


class AdaptiveBeliefCalibrator:
    """
    Empirically calibrates belief model parameters from historical match data.

    Extends the existing DeathProbabilityEstimator.calibrate() method with:
    - Per-weapon-class lethality calibration
    - Threat decay rate (lambda) fitting via least squares
    - Calibration snapshotting for observability and rollback
    - Safety bounds to prevent pathological parameter values

    Does NOT replace existing calibration — augments it.

    Usage:
        calibrator = AdaptiveBeliefCalibrator(estimator)
        calibrator.auto_calibrate(death_events_df)
    """

    MIN_SAMPLES: int = 100

    # Safety bounds to prevent pathological calibration
    _PRIOR_BOUNDS = (0.05, 0.95)
    _LETHALITY_BOUNDS = (0.1, 3.0)
    _DECAY_BOUNDS = (0.01, 1.0)

    def __init__(self, estimator: Optional[DeathProbabilityEstimator] = None):
        self.estimator = estimator or DeathProbabilityEstimator()

    def calibrate_hp_brackets(self, death_events: pd.DataFrame) -> Dict[str, float]:
        """
        Calibrate HP bracket priors from labeled death data.

        Delegates to the existing estimator.calibrate() but adds bounds checking.

        Args:
            death_events: DataFrame with 'health' and 'died' columns.

        Returns:
            Calibrated priors dict, or empty dict if insufficient data.
        """
        if len(death_events) < self.MIN_SAMPLES:
            # AC-05-01: Warn (not info) — sparse data leaves posterior dominated by prior
            logger.warning(
                "Insufficient samples for HP calibration: %d < %d",
                len(death_events), self.MIN_SAMPLES,
            )
            return {}

        # Use existing calibrate method
        self.estimator.calibrate(death_events)

        # Apply safety bounds
        for bracket, value in self.estimator.priors.items():
            self.estimator.priors[bracket] = max(
                self._PRIOR_BOUNDS[0], min(self._PRIOR_BOUNDS[1], value)
            )

        logger.info("HP priors calibrated (bounded): %s", self.estimator.priors)
        return dict(self.estimator.priors)

    def calibrate_weapon_lethality(self, death_events: pd.DataFrame) -> Dict[str, float]:
        """
        Calibrate weapon lethality multipliers from kill data.

        For each weapon class: relative_kill_rate = kills_with_weapon / total_kills,
        normalized so that 'rifle' = 1.0.

        Args:
            death_events: DataFrame with 'weapon_class' and 'died' columns.

        Returns:
            Calibrated weapon multipliers, or empty dict if insufficient data.
        """
        if "weapon_class" not in death_events.columns or len(death_events) < self.MIN_SAMPLES:
            return {}

        deaths_only = death_events[death_events["died"]]
        if deaths_only.empty:
            return {}

        # Count kills per weapon class
        weapon_counts = deaths_only["weapon_class"].value_counts()
        rifle_count = weapon_counts.get("rifle", 1)

        calibrated = {}
        for weapon_class, count in weapon_counts.items():
            if count >= 10:  # Minimum per-class samples
                raw_mult = count / max(1, rifle_count)
                # Apply safety bounds
                bounded = max(self._LETHALITY_BOUNDS[0], min(self._LETHALITY_BOUNDS[1], raw_mult))
                calibrated[weapon_class] = bounded

        if calibrated:
            logger.info(
                "Weapon lethality calibrated (returned, not applied globally): %s", calibrated
            )

        return calibrated

    def calibrate_threat_decay(self, engagement_windows: pd.DataFrame) -> Optional[float]:
        """
        Fit the threat decay rate (lambda) from engagement data.

        Optimizes: P(death | info_age) = P0 * exp(-lambda * info_age)
        via least-squares on empirical death rates binned by information age.

        Args:
            engagement_windows: DataFrame with 'information_age' and 'died' columns.

        Returns:
            Calibrated lambda value, or None if insufficient data.
        """
        if (
            "information_age" not in engagement_windows.columns
            or len(engagement_windows) < self.MIN_SAMPLES
        ):
            return None

        df = engagement_windows.copy()

        # Bin information_age into brackets
        df["age_bin"] = pd.cut(df["information_age"], bins=10)
        bin_stats = df.groupby("age_bin", observed=True).agg(
            death_rate=("died", "mean"),
            count=("died", "count"),
            mean_age=("information_age", "mean"),
        )

        # Filter bins with enough samples
        bin_stats = bin_stats[bin_stats["count"] >= 5]
        if len(bin_stats) < 3:
            logger.info("Insufficient age bins for decay calibration")
            return None

        # Fit exponential decay: death_rate = P0 * exp(-lambda * age)
        # Log-linearize: ln(death_rate) = ln(P0) - lambda * age
        valid = bin_stats[bin_stats["death_rate"] > 0]
        if len(valid) < 3:
            return None

        ages = valid["mean_age"].values
        log_rates = np.log(valid["death_rate"].values)

        # Simple least squares: y = a + b*x where b = -lambda
        try:
            coeffs = np.polyfit(ages, log_rates, 1)
            fitted_lambda = -coeffs[0]

            # Apply safety bounds
            fitted_lambda = max(self._DECAY_BOUNDS[0], min(self._DECAY_BOUNDS[1], fitted_lambda))

            logger.info(
                "Threat decay lambda calibrated: %s (was 0.1)", format(fitted_lambda, ".4f")
            )
            return fitted_lambda
        except Exception as e:
            logger.warning("Decay calibration failed: %s", e)
            return None

    def auto_calibrate(self, death_events: pd.DataFrame) -> Dict[str, Any]:
        """
        Full auto-calibration pipeline. Call from Teacher daemon periodically.

        Args:
            death_events: DataFrame with columns:
                health, died, weapon_class, information_age (all optional — calibrates what it can)

        Returns:
            Dict summarizing what was calibrated.
        """
        summary = {"hp_priors": {}, "weapon_lethality": {}, "threat_decay": None}

        if "health" in death_events.columns and "died" in death_events.columns:
            summary["hp_priors"] = self.calibrate_hp_brackets(death_events)

        if "weapon_class" in death_events.columns:
            summary["weapon_lethality"] = self.calibrate_weapon_lethality(death_events)

        if "information_age" in death_events.columns:
            summary["threat_decay"] = self.calibrate_threat_decay(death_events)

        # Persist calibration snapshot with sample count
        self._save_snapshot(summary, sample_count=len(death_events))

        return summary

    def _save_snapshot(self, summary: Dict, sample_count: int = 0) -> None:
        """Persist calibration parameters to DB for observability."""
        try:
            import json

            from Programma_CS2_RENAN.backend.storage.database import get_db_manager
            from Programma_CS2_RENAN.backend.storage.db_models import CalibrationSnapshot

            db = get_db_manager()
            with db.get_session() as session:
                for cal_type, params in summary.items():
                    if params:  # Only save non-empty calibrations
                        snapshot = CalibrationSnapshot(
                            calibration_type=cal_type,
                            parameters_json=json.dumps(
                                params if isinstance(params, dict) else {"value": params}
                            ),
                            sample_count=sample_count,
                            source="auto",
                        )
                        session.add(snapshot)
                session.commit()
                logger.info("Calibration snapshot saved to DB (%d samples)", sample_count)
        except Exception as e:
            logger.warning("Failed to save calibration snapshot: %s", e)


# ---------------------------------------------------------------------------
# Data Extraction for Calibration Pipeline
# ---------------------------------------------------------------------------


def extract_death_events_from_db() -> pd.DataFrame:
    """Extract round-level death data for belief model calibration.

    Builds a DataFrame from RoundStats suitable for
    ``AdaptiveBeliefCalibrator.auto_calibrate()``.

    Columns provided:
        - ``health`` (int): Estimated player health at round start (100 for
          full-buy rounds, heuristic for eco/force).  Calibrates the "full"
          HP bracket prior; finer brackets require per-engagement tick data.
        - ``died`` (bool): Whether the player died that round.

    Future enhancement: integrate MatchTickState for per-engagement health,
    weapon_class, and information_age columns.

    Returns:
        DataFrame with at least ``health`` and ``died`` columns, or an empty
        DataFrame if no RoundStats data exists.
    """
    try:
        from sqlmodel import select

        from Programma_CS2_RENAN.backend.storage.database import get_db_manager
        from Programma_CS2_RENAN.backend.storage.db_models import RoundStats

        db = get_db_manager()
        rows = []

        with db.get_session("default") as session:
            all_rounds = session.exec(select(RoundStats).limit(MAX_CALIBRATION_SAMPLES)).all()

            for rs in all_rounds:
                # HP bracket estimation from equipment value:
                #   Full buy (>4000) → full health start
                #   Force (2000-4000) → likely damaged from previous round
                #   Eco (<2000) → often critical after save
                if rs.equipment_value > 4000:
                    health = 100
                elif rs.equipment_value > 2000:
                    health = 60
                else:
                    health = 30

                rows.append({"health": health, "died": rs.deaths > 0})

        if not rows:
            return pd.DataFrame(columns=["health", "died"])
        return pd.DataFrame(rows)

    except Exception as e:
        logger.warning("Failed to extract death events for calibration: %s", e)
        return pd.DataFrame(columns=["health", "died"])
