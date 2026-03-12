import os

import numpy as np
import pandas as pd

from Programma_CS2_RENAN.core.config import get_resource_path
from Programma_CS2_RENAN.observability.logger_setup import get_logger

_logger = get_logger("cs2analyzer.external_analytics")


class EliteAnalytics:
    def __init__(self):
        self._load_datasets()
        self._prepare_data()

    def _load_datasets(self):
        self.players_df = self._read_safe("top_100_players.csv").dropna(subset=["Name"])
        self.match_players_df = self._read_safe("match_players.csv")
        self.maps_df = self._read_safe("maps_statistics.csv").fillna(0)
        self.weapons_df = self._read_safe("weapons_statistics.csv").fillna(0)
        self.roles_df = self._read_safe("cs2_playstyle_roles_2024.csv")
        self.best_players_df = self._read_safe("all_Time_best_Players_Stats.csv")
        self.tournament_df = self._read_safe("tournament_advanced_stats.csv")
        # Count successfully loaded datasets so is_healthy() can report degraded state.
        self._loaded_dataset_count = sum(
            1
            for df in [
                self.players_df, self.match_players_df, self.maps_df,
                self.weapons_df, self.roles_df, self.best_players_df, self.tournament_df,
            ]
            if not df.empty
        )

    def is_healthy(self) -> bool:
        """Return True if at least one reference CSV dataset was loaded with expected columns.

        R4-12-01: Verifies column presence, not just non-empty DataFrames.
        Callers should check this before relying on `analyze_user_vs_elite()` results.
        When False, all z-score outputs are empty dicts (degraded signal).
        """
        if self._loaded_dataset_count == 0:
            return False
        # R4-12-01: Verify key columns exist in primary datasets
        if not self.players_df.empty and "CS Rating" not in self.players_df.columns:
            return False
        return True

    def _read_safe(self, filename):
        rel_path = os.path.join("data", "external", filename)
        path = get_resource_path(rel_path)
        if os.path.exists(path):
            return pd.read_csv(path)
        return pd.DataFrame()

    def _prepare_data(self):
        self._prepare_players()
        self._prepare_historical()
        self._prepare_tournament()

    def _prepare_players(self):
        if "CS Rating" in self.players_df.columns:
            _clean_cs_rating_col(self.players_df)

        if all(col in self.players_df.columns for col in ["Wins", "Total_Matches"]):
            self.players_df["Win_Rate"] = self.players_df["Wins"] / self.players_df[
                "Total_Matches"
            ].replace(0, 1)

    def _prepare_historical(self):
        cols = ["adr", "deaths", "kills", "rating", "hs"]
        avail = [c for c in cols if c in self.match_players_df.columns]
        if avail:
            _process_historical_columns(self.match_players_df, avail)
            self.historical_stats = self.match_players_df[avail].mean()
            self.historical_std = self.match_players_df[avail].std()

    def _prepare_tournament(self):
        if not self.tournament_df.empty:
            adv = ["accuracy", "econ_rating", "utility_value"]
            avail = [c for c in adv if c in self.tournament_df.columns]
            if avail:
                self.tournament_baselines = self.tournament_df[avail].mean().to_dict()
                self.tournament_stds = self.tournament_df[avail].std().to_dict()

    def analyze_user_vs_elite(self, user_stats):
        """Compares user metrics against Top 100 and Historical data."""
        # P3-03: Guard against missing data or columns before accessing DataFrame
        if not self.is_healthy():
            return {"elite_rating_avg": 0, "z_scores": {}, "tournament_z_scores": {}}
        required_cols = {"CS Rating", "Win_Rate"}
        if not required_cols.issubset(self.players_df.columns):
            # P-EA-02: Log missing columns so callers can distinguish degradation from cold start
            _logger.warning(
                "P-EA-02: Missing required columns for elite analysis: %s",
                required_cols - set(self.players_df.columns),
            )
            return {"elite_rating_avg": 0, "z_scores": {}, "tournament_z_scores": {}}

        elite_avg = self.players_df[["CS Rating", "Win_Rate"]].mean()
        z_scores = self._calc_z_scores(user_stats)
        t_z_scores = self._calc_tournament_z(user_stats)

        return {
            "elite_rating_avg": elite_avg.get("CS Rating", 0),
            "z_scores": z_scores,
            "tournament_z_scores": t_z_scores,
        }

    def _calc_z_scores(self, user_stats):
        if not hasattr(self, "historical_stats"):
            return {}
        return _compute_z_scores(user_stats, self.historical_stats, self.historical_std)

    def _calc_tournament_z(self, user_stats):
        if not hasattr(self, "tournament_baselines"):
            return {}
        return _compute_t_z_scores(user_stats, self.tournament_baselines, self.tournament_stds)

    def get_player_role(self, player_name):
        match = self.roles_df[self.roles_df["player_name"].str.lower() == player_name.lower()]
        return match.iloc[0]["role_overall"] if not match.empty else "Unknown"

    def get_tournament_baseline(self):
        if not hasattr(self, "tournament_baselines"):
            return {}
        # P3-18: Only include keys that were actually available in the CSV
        result = {}
        for key in ("accuracy", "econ_rating"):
            if key in self.tournament_baselines and key in self.tournament_stds:
                result[key] = {
                    "mean": self.tournament_baselines[key],
                    "std": self.tournament_stds[key],
                }
        return result

    def get_available_extra_datasets(self):
        """Lists all successfully loaded clinical datasets."""
        datasets = []
        if not self.players_df.empty:
            datasets.append("top_100_players")
        if not self.match_players_df.empty:
            datasets.append("match_players")
        if not self.roles_df.empty:
            datasets.append("playstyle_roles")
        if not self.tournament_df.empty:
            datasets.append("tournament_stats")
        return datasets


# --- Top-Level Clinical Helpers ---


def _clean_cs_rating_col(df):
    df["CS Rating"] = pd.to_numeric(
        df["CS Rating"].astype(str).str.replace(",", ""), errors="coerce"
    ).fillna(0)


def _process_historical_columns(df, avail):
    for col in avail:
        # P-EA-03: Regex handles scientific notation (e.g. 1.5e-3, 2E+10)
        df[col] = pd.to_numeric(
            df[col].astype(str).str.extract(r"([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)")[0],
            errors="coerce",
        ).fillna(0)


def _compute_z_scores(u_stats, h_stats, h_std):
    z_scores = {}
    _MIN_STD = 1e-8  # P-EA-01: epsilon guard for floating-point near-zero std
    for key in ["adr", "rating"]:
        if key in u_stats and h_std.get(key, 0) > _MIN_STD:
            # R4-12-02: Guard against NaN/Inf in user stats
            val = u_stats[key]
            if not np.isfinite(val):
                continue
            z_scores[key] = (val - h_stats[key]) / h_std[key]
    return z_scores


def _compute_t_z_scores(u_stats, t_base, t_std):
    t_z = {}
    _MIN_STD = 1e-8  # P-EA-01: epsilon guard for floating-point near-zero std
    for key in ["accuracy", "econ_rating"]:
        if key in u_stats and t_std.get(key, 0) > _MIN_STD:
            # R4-12-02: Guard against NaN/Inf in user stats
            val = u_stats[key]
            if not np.isfinite(val):
                continue
            t_z[key] = (val - t_base[key]) / t_std[key]
    return t_z
