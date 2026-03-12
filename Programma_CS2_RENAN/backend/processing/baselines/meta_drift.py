"""
Meta-Drift Surveillance Engine

Tracks shifts in professional playstyles over time.
If pros start playing differently, the Coach adjusts its certainty.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
from sqlmodel import func, select

from Programma_CS2_RENAN.backend.storage.database import get_db_manager, get_hltv_db_manager
from Programma_CS2_RENAN.backend.storage.db_models import (
    PlayerMatchStats,
    PlayerTickState,
    ProPlayerStatCard,
)


class MetaDriftEngine:
    """
    Analyzes the 'Knowledge Freshness' of the Pro Baseline.
    """

    @staticmethod
    def calculate_spatial_drift(map_name: str) -> float:
        """
        Implementation of Pillar 2 - Phase 3 (100%): Meta-Drift Surveillance.
        Compares pro positions in the last 30 days vs historical pro positions.
        """
        db = get_db_manager()
        limit_date = datetime.now(timezone.utc) - timedelta(days=30)

        with db.get_session() as s:
            # P3-30: Use COUNT instead of fetching all IDs (avoids unbounded result set)
            pro_count = s.exec(
                select(func.count()).select_from(PlayerMatchStats).where(
                    PlayerMatchStats.is_pro == True
                )
            ).one()
            if not pro_count:
                return 0.0

            # Refined query with date-aware join
            recent_stmt = (
                select(PlayerTickState.pos_x, PlayerTickState.pos_y)
                .join(PlayerMatchStats, PlayerTickState.match_id == PlayerMatchStats.id)
                .where(PlayerMatchStats.is_pro == True)
                .where(PlayerMatchStats.processed_at >= limit_date)
                .where(PlayerTickState.tick % 128 == 0)
                .limit(50_000)
            )
            recent_pts = s.exec(recent_stmt).all()

            hist_stmt = (
                select(PlayerTickState.pos_x, PlayerTickState.pos_y)
                .join(PlayerMatchStats, PlayerTickState.match_id == PlayerMatchStats.id)
                .where(PlayerMatchStats.is_pro == True)
                .where(PlayerMatchStats.processed_at < limit_date)
                .where(PlayerTickState.tick % 128 == 0)
                .limit(50_000)
            )
            hist_pts = s.exec(hist_stmt).all()

            if not recent_pts or not hist_pts:
                return 0.0

            # 3. Compare Distributions (Simplified Centroid Drift)
            # Guard: filter incomplete/None tuples and ensure uniform shape (F2-44)
            recent_clean = [p for p in recent_pts if p is not None and len(p) == 2 and all(v is not None for v in p)]
            hist_clean = [p for p in hist_pts if p is not None and len(p) == 2 and all(v is not None for v in p)]
            if not recent_clean or not hist_clean:
                return 0.0

            r_centroid = np.mean(recent_clean, axis=0)
            h_centroid = np.mean(hist_clean, axis=0)

            dist = float(np.linalg.norm(r_centroid - h_centroid))

            # P-MD-01: Use actual map dimensions from spatial_data when available.
            # Falls back to observed data spread only if map metadata is missing.
            from Programma_CS2_RENAN.core.spatial_data import get_map_metadata

            meta = get_map_metadata(map_name)
            if meta:
                # Map extent = scale * radar_resolution (1024 pixels)
                map_extent = meta.scale * 1024.0
            else:
                all_pts = np.array(recent_clean + hist_clean)
                map_extent = max(float(np.ptp(all_pts[:, 0])), float(np.ptp(all_pts[:, 1])), 1.0)
            # Normalize: 10% of map extent drift = 1.0 coefficient
            drift_threshold = max(map_extent * 0.10, 500.0)
            return min(dist / drift_threshold, 1.0)

    @staticmethod
    def calculate_drift_coefficient(map_name: str = None) -> float:
        """
        Returns a value between 0.0 (Stable) and 1.0 (Meta Chaos).
        Combines Statistical Drift (Rating) and Spatial Drift (Positioning).
        """
        stat_drift = 0.0

        # ProPlayerStatCard lives in hltv_metadata.db
        hltv_db = get_hltv_db_manager()
        with hltv_db.get_session() as s:
            # 1. Statistical Drift
            hist_avg = s.exec(select(func.avg(ProPlayerStatCard.rating_2_0))).one() or 0.0
            # P-MD-02: If historical avg is near-zero, data is degenerate — no drift to measure.
            if abs(hist_avg) < 0.1:
                stat_drift = 0.0
            else:
                limit_date = datetime.now(timezone.utc) - timedelta(days=30)
                recent_avg = (
                    s.exec(
                        select(func.avg(ProPlayerStatCard.rating_2_0)).where(
                            ProPlayerStatCard.last_updated >= limit_date
                        )
                    ).one()
                    or hist_avg
                )
                stat_drift = min((abs(recent_avg - hist_avg) / hist_avg) / 0.20, 1.0)

        # 2. Spatial Drift (if map provided)
        spatial_drift = 0.0
        if map_name:
            spatial_drift = MetaDriftEngine.calculate_spatial_drift(map_name)

        # P-MD-03: Named weights for drift combination.
        # Spatial drift weighted higher because positioning changes reflect
        # meta shifts faster than rating averages.
        _WEIGHT_STAT_DRIFT = 0.4
        _WEIGHT_SPATIAL_DRIFT = 0.6
        if map_name:
            return (stat_drift * _WEIGHT_STAT_DRIFT) + (spatial_drift * _WEIGHT_SPATIAL_DRIFT)
        return stat_drift

    @staticmethod
    def get_meta_confidence_adjustment(map_name: str = None) -> float:
        """
        Returns a multiplier for Coach Confidence.
        """
        drift = MetaDriftEngine.calculate_drift_coefficient(map_name)
        return 1.0 - (drift * 0.5)
