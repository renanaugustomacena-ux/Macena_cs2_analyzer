"""
Engagement Range Analytics — Kill distance analysis and named position registry.

Fusion Plan Proposal 7: Spatial Intelligence Expansion.

This module is ADDITIVE — it does not modify spatial_data.py. It provides:
1. NamedPosition registry for human-readable callout positions
2. Engagement range classification from kill-event positions
3. Role-specific range profile comparison against baselines

Usage:
    from Programma_CS2_RENAN.backend.analysis.engagement_range import (
        EngagementRangeAnalyzer, NamedPositionRegistry
    )
"""

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.analysis.engagement_range")


# ---------------------------------------------------------------------------
# Named Position Registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NamedPosition:
    """A known map callout position with spatial and tactical metadata."""

    name: str  # "Triple Box", "Ticket Booth", "Window"
    map_name: str  # "de_mirage"
    center_x: float  # World X coordinate
    center_y: float  # World Y coordinate
    center_z: float  # World Z coordinate
    radius: float  # Engagement area radius (world units)
    level: str = "default"  # "default", "upper", "lower"


# Core callout positions for competitive maps.
# Populated from community callout maps and spatial analysis.
# Expandable via JSON config without code changes.
_NAMED_POSITIONS: List[NamedPosition] = [
    # --- de_mirage ---
    NamedPosition("A Site", "de_mirage", -290, -2080, 0, 400),
    NamedPosition("B Site", "de_mirage", -2180, 540, 0, 350),
    NamedPosition("Mid", "de_mirage", -460, -530, 0, 350),
    NamedPosition("A Ramp", "de_mirage", 240, -1600, 0, 250),
    NamedPosition("B Apartments", "de_mirage", -1350, 520, 0, 300),
    NamedPosition("Window", "de_mirage", -1250, -545, 0, 150),
    NamedPosition("Connector", "de_mirage", -1100, -1200, 0, 250),
    NamedPosition("Jungle", "de_mirage", -1350, -1690, 0, 200),
    NamedPosition("Palace", "de_mirage", -600, -2550, 0, 250),
    NamedPosition("T Spawn", "de_mirage", 1400, -230, 0, 300),
    # --- de_inferno ---
    NamedPosition("A Site", "de_inferno", 2160, 300, 0, 400),
    NamedPosition("B Site", "de_inferno", 125, 2900, 0, 350),
    NamedPosition("Banana", "de_inferno", 370, 1270, 0, 300),
    NamedPosition("Mid", "de_inferno", 1450, 640, 0, 300),
    NamedPosition("Apartments", "de_inferno", 730, -150, 0, 300),
    NamedPosition("Pit", "de_inferno", 2340, -260, 0, 200),
    NamedPosition("Library", "de_inferno", 1920, 720, 0, 200),
    # --- de_dust2 ---
    NamedPosition("A Site", "de_dust2", 1230, 2500, 0, 350),
    NamedPosition("B Site", "de_dust2", -1375, 2560, 0, 350),
    NamedPosition("Mid Doors", "de_dust2", -470, 1050, 0, 200),
    NamedPosition("Long A", "de_dust2", 1560, 620, 0, 400),
    NamedPosition("Short A (Catwalk)", "de_dust2", 380, 1800, 0, 300),
    NamedPosition("B Tunnels", "de_dust2", -975, 1050, 0, 300),
    NamedPosition("CT Spawn", "de_dust2", 420, 2870, 0, 250),
    NamedPosition("T Spawn", "de_dust2", -650, -430, 0, 300),
    # --- de_anubis ---
    NamedPosition("A Site", "de_anubis", -640, -680, 0, 350),
    NamedPosition("B Site", "de_anubis", 690, 1390, 0, 350),
    NamedPosition("Mid", "de_anubis", -200, 360, 0, 350),
    NamedPosition("Canal", "de_anubis", 560, -100, 0, 300),
    # --- de_nuke ---
    NamedPosition("A Site (Upper)", "de_nuke", -370, -720, -400, 400, "upper"),
    NamedPosition("B Site (Lower)", "de_nuke", 475, -750, -750, 400, "lower"),
    NamedPosition("Ramp", "de_nuke", 410, -1170, -400, 300),
    NamedPosition("Outside", "de_nuke", -1900, -760, -400, 500),
    NamedPosition("Secret", "de_nuke", 510, -400, -750, 250, "lower"),
    # --- de_ancient ---
    NamedPosition("A Site", "de_ancient", -340, -200, 0, 350),
    NamedPosition("B Site", "de_ancient", 1090, 1460, 0, 350),
    NamedPosition("Mid", "de_ancient", 270, 560, 0, 350),
    NamedPosition("Donut", "de_ancient", -350, 400, 0, 200),
    # --- de_overpass ---
    NamedPosition("A Site", "de_overpass", -2100, 200, 0, 400),
    NamedPosition("B Site", "de_overpass", -1900, -600, 0, 350),
    NamedPosition("Connector", "de_overpass", -2600, -300, 0, 300),
    NamedPosition("Bathrooms", "de_overpass", -1400, -350, 0, 250),
    NamedPosition("Monster", "de_overpass", -2200, -1100, 0, 300),
    NamedPosition("Playground", "de_overpass", -2700, 400, 0, 250),
    NamedPosition("Bank", "de_overpass", -1600, 400, 0, 200),
    NamedPosition("Fountain", "de_overpass", -2200, 700, 0, 250),
    # --- de_vertigo ---
    NamedPosition("A Site", "de_vertigo", -700, -500, 11900, 350, "upper"),
    NamedPosition("B Site", "de_vertigo", -1700, -450, 11900, 350, "upper"),
    NamedPosition("Mid", "de_vertigo", -1200, -100, 11900, 300, "upper"),
    NamedPosition("Ramp", "de_vertigo", -1500, -700, 11900, 250, "upper"),
    NamedPosition("Scaffolding", "de_vertigo", -1100, 100, 11500, 300, "lower"),
    NamedPosition("Lower B", "de_vertigo", -1700, -200, 11500, 300, "lower"),
    # --- de_train ---
    NamedPosition("A Site", "de_train", -400, 1100, 0, 400),
    NamedPosition("B Site", "de_train", -200, -100, 0, 350),
    NamedPosition("Ivy", "de_train", -800, 400, 0, 300),
    NamedPosition("Connector", "de_train", 100, 500, 0, 250),
    NamedPosition("Upper B Hall", "de_train", 200, -350, 0, 250),
    NamedPosition("T Main", "de_train", -1100, -100, 0, 300),
    NamedPosition("Old Bomb", "de_train", -650, 850, 0, 250),
]


class NamedPositionRegistry:
    """
    Registry of known map callout positions.

    Supports lookup by proximity: given a world position, finds the nearest
    named position within a configurable radius.
    """

    def __init__(self):
        self._positions: List[NamedPosition] = list(_NAMED_POSITIONS)
        self._by_map: Dict[str, List[NamedPosition]] = {}
        self._rebuild_index()

    def _rebuild_index(self):
        self._by_map.clear()
        for pos in self._positions:
            self._by_map.setdefault(pos.map_name, []).append(pos)

    def get_positions(self, map_name: str) -> List[NamedPosition]:
        """Get all named positions for a map."""
        return self._by_map.get(map_name, [])

    def find_nearest(
        self,
        map_name: str,
        x: float,
        y: float,
        z: float = 0.0,
        max_distance: float = 600.0,
    ) -> Optional[NamedPosition]:
        """
        Find the nearest named position to a world coordinate.

        Args:
            map_name: Map identifier (e.g., "de_mirage").
            x, y, z: World coordinates.
            max_distance: Maximum search radius in world units.

        Returns:
            Nearest NamedPosition within max_distance, or None.
        """
        candidates = self._by_map.get(map_name, [])
        if not candidates:
            return None

        best = None
        best_dist = max_distance

        for pos in candidates:
            dist = math.sqrt(
                (x - pos.center_x) ** 2 + (y - pos.center_y) ** 2 + (z - pos.center_z) ** 2
            )
            if dist < best_dist:
                best_dist = dist
                best = pos

        return best

    def add_position(self, position: NamedPosition):
        """Add a new named position to the registry."""
        self._positions.append(position)
        self._rebuild_index()

    def load_from_json(self, json_path: Path) -> int:
        """
        Load additional named positions from a JSON file.

        Returns:
            Number of positions loaded.
        """
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            count = 0
            for entry in data:
                pos = NamedPosition(
                    name=entry["name"],
                    map_name=entry["map_name"],
                    center_x=entry["center_x"],
                    center_y=entry["center_y"],
                    center_z=entry.get("center_z", 0.0),
                    radius=entry.get("radius", 300.0),
                    level=entry.get("level", "default"),
                )
                self._positions.append(pos)
                count += 1
            self._rebuild_index()
            logger.info("Loaded %s named positions from %s", count, json_path)
            return count
        except Exception as e:
            logger.warning("Failed to load named positions from %s: %s", json_path, e)
            return 0


# ---------------------------------------------------------------------------
# Engagement Range Analyzer
# ---------------------------------------------------------------------------

# Range classification thresholds (world units)
RANGE_CLOSE = 500
RANGE_MEDIUM = 1500
RANGE_LONG = 3000


@dataclass
class EngagementProfile:
    """Distribution of kill distances by range category."""

    close_pct: float = 0.0  # < 500 units
    medium_pct: float = 0.0  # 500-1500 units
    long_pct: float = 0.0  # 1500-3000 units
    extreme_pct: float = 0.0  # > 3000 units
    avg_distance: float = 0.0
    total_kills: int = 0


# Expected engagement profiles by role (pro baselines)
_ROLE_RANGE_BASELINES: Dict[str, EngagementProfile] = {
    "awper": EngagementProfile(close_pct=0.10, medium_pct=0.30, long_pct=0.45, extreme_pct=0.15),
    "entry_fragger": EngagementProfile(
        close_pct=0.40, medium_pct=0.40, long_pct=0.15, extreme_pct=0.05
    ),
    "support": EngagementProfile(close_pct=0.25, medium_pct=0.45, long_pct=0.25, extreme_pct=0.05),
    "lurker": EngagementProfile(close_pct=0.35, medium_pct=0.35, long_pct=0.20, extreme_pct=0.10),
    "igl": EngagementProfile(close_pct=0.25, medium_pct=0.40, long_pct=0.25, extreme_pct=0.10),
    "flex": EngagementProfile(close_pct=0.25, medium_pct=0.40, long_pct=0.25, extreme_pct=0.10),
}


class EngagementRangeAnalyzer:
    """
    Analyzes kill distances to build engagement range profiles.

    Uses kill event positions (from demo_parser enrichment) or
    tick-level positions at the time of kills.
    """

    def __init__(self):
        self.position_registry = NamedPositionRegistry()

    @staticmethod
    def compute_kill_distance(
        killer_x: float,
        killer_y: float,
        killer_z: float,
        victim_x: float,
        victim_y: float,
        victim_z: float,
    ) -> float:
        """Euclidean distance between killer and victim in world units."""
        return math.sqrt(
            (killer_x - victim_x) ** 2 + (killer_y - victim_y) ** 2 + (killer_z - victim_z) ** 2
        )

    @staticmethod
    def classify_range(distance: float) -> str:
        """Classify engagement distance into categories."""
        if distance < RANGE_CLOSE:
            return "close"
        elif distance < RANGE_MEDIUM:
            return "medium"
        elif distance < RANGE_LONG:
            return "long"
        return "extreme"

    def compute_profile(self, kill_distances: List[float]) -> EngagementProfile:
        """
        Build an engagement range profile from a list of kill distances.

        Args:
            kill_distances: List of Euclidean distances for each kill.

        Returns:
            EngagementProfile with distribution and statistics.
        """
        if not kill_distances:
            return EngagementProfile()

        total = len(kill_distances)
        close = sum(1 for d in kill_distances if d < RANGE_CLOSE)
        medium = sum(1 for d in kill_distances if RANGE_CLOSE <= d < RANGE_MEDIUM)
        long_ = sum(1 for d in kill_distances if RANGE_MEDIUM <= d < RANGE_LONG)
        extreme = sum(1 for d in kill_distances if d >= RANGE_LONG)

        return EngagementProfile(
            close_pct=close / total,
            medium_pct=medium / total,
            long_pct=long_ / total,
            extreme_pct=extreme / total,
            avg_distance=sum(kill_distances) / total,
            total_kills=total,
        )

    def compare_to_role(self, profile: EngagementProfile, role: str) -> List[str]:
        """
        Compare a player's engagement profile to role-specific baseline.

        Args:
            profile: Player's computed engagement profile.
            role: Player's classified role (e.g., "awper", "entry_fragger").

        Returns:
            List of coaching observations (strings).
        """
        baseline = _ROLE_RANGE_BASELINES.get(role.lower().replace(" ", "_"))
        if not baseline or profile.total_kills < 5:
            return []

        observations = []
        threshold = 0.15  # 15% deviation triggers observation

        if profile.close_pct - baseline.close_pct > threshold:
            observations.append(
                f"Taking more close-range fights than typical {role}s "
                f"({profile.close_pct:.0%} vs {baseline.close_pct:.0%}). "
                f"Consider holding longer angles."
            )
        elif baseline.close_pct - profile.close_pct > threshold:
            observations.append(
                f"Fewer close-range engagements than typical {role}s. "
                f"You may be playing too passively for your role."
            )

        if profile.long_pct - baseline.long_pct > threshold:
            observations.append(
                f"More long-range kills than expected for {role} "
                f"({profile.long_pct:.0%} vs {baseline.long_pct:.0%})."
            )
        elif baseline.long_pct - profile.long_pct > threshold:
            observations.append(
                f"Fewer long-range kills than expected for {role}. "
                f"Consider utilizing sightlines better."
            )

        return observations

    def annotate_kill_position(self, map_name: str, x: float, y: float, z: float = 0.0) -> str:
        """
        Annotate a kill position with the nearest named callout.

        Returns:
            Position name (e.g., "A Site") or "Unknown Position".
        """
        pos = self.position_registry.find_nearest(map_name, x, y, z)
        return pos.name if pos else "Unknown Position"

    def analyze_match_engagements(
        self,
        kill_events: List[Dict],
        map_name: str,
        player_role: str = "flex",
    ) -> Dict:
        """
        Full engagement analysis for a player's kills in a match.

        Args:
            kill_events: List of dicts with keys:
                killer_x, killer_y, killer_z, victim_x, victim_y, victim_z
            map_name: CS2 map name.
            player_role: Player's classified role for baseline comparison.

        Returns:
            Dict with profile, observations, and annotated kills.
        """
        # O-03: Validate map_name before processing — missing metadata silently
        # produces "Unknown Position" for all kills, making analysis worthless.
        if not map_name:
            logger.warning("O-03: analyze_match_engagements called without map_name")

        distances = []
        annotated = []

        for ev in kill_events:
            required = ("killer_x", "killer_y", "victim_x", "victim_y")
            if not all(k in ev for k in required):
                logger.warning("Skipping kill event missing coordinates: %s", list(ev.keys()))
                continue
            dist = self.compute_kill_distance(
                ev.get("killer_x", 0),
                ev.get("killer_y", 0),
                ev.get("killer_z", 0),
                ev.get("victim_x", 0),
                ev.get("victim_y", 0),
                ev.get("victim_z", 0),
            )
            distances.append(dist)

            killer_pos = self.annotate_kill_position(
                map_name,
                ev.get("killer_x", 0),
                ev.get("killer_y", 0),
                ev.get("killer_z", 0),
            )
            victim_pos = self.annotate_kill_position(
                map_name,
                ev.get("victim_x", 0),
                ev.get("victim_y", 0),
                ev.get("victim_z", 0),
            )
            annotated.append(
                {
                    "distance": dist,
                    "range": self.classify_range(dist),
                    "killer_position": killer_pos,
                    "victim_position": victim_pos,
                }
            )

        profile = self.compute_profile(distances)
        observations = self.compare_to_role(profile, player_role)

        return {
            "profile": profile,
            "observations": observations,
            "annotated_kills": annotated,
        }


def get_engagement_range_analyzer() -> EngagementRangeAnalyzer:
    """Factory function for EngagementRangeAnalyzer (consistent with other analysis modules)."""
    return EngagementRangeAnalyzer()
