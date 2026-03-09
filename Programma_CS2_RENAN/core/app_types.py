"""
Core application type aliases and enums.

R1-02 WARNING: This module defines a NUMERIC Team enum (SPECTATOR=0, T=1, CT=2).
A SEPARATE Team enum exists in demo_frame.py with STRING values ("ct", "t").
Never confuse the two — import the correct one for your context.
"""
from enum import Enum, auto
from typing import Any, Dict, List, NewType, Optional, Tuple, TypedDict

MatchID = NewType("MatchID", int)
Tick = NewType("Tick", int)
PlayerID = NewType("PlayerID", int)


class Team(Enum):
    """Numeric team identifiers for internal processing.

    Note: demo_frame.py defines a separate Team enum with string values
    ("ct", "t", "spectator") for demo-parser compatibility. Import the correct
    enum for your context: use this one for DB/UI, demo_frame.Team for parser data.
    """

    SPECTATOR = 0
    T = 1
    CT = 2

    def __eq__(self, other):
        # AT-01: Fail-fast on cross-enum comparison to prevent silent mismatches.
        if (isinstance(other, Enum)
                and type(other).__name__ == "Team"
                and type(other).__module__ != type(self).__module__):
            raise TypeError(
                f"AT-01: Cannot compare {type(self).__module__}.Team with "
                f"{type(other).__module__}.Team — use team_from_demo_frame() to convert"
            )
        return Enum.__eq__(self, other)

    def __hash__(self):
        return Enum.__hash__(self)


class PlayerRole(str, Enum):
    """Canonical CS2 player role classification (P3-01).

    Single source of truth — imported by role_features.py, role_classifier.py,
    and all downstream consumers.  Values are lowercase identifiers suitable
    for serialisation, DB storage, and cross-module comparison.
    """

    ENTRY = "entry"
    AWPER = "awper"
    SUPPORT = "support"
    LURKER = "lurker"
    IGL = "igl"
    FLEX = "flex"
    UNKNOWN = "unknown"

    @property
    def display_name(self) -> str:
        """Human-readable name for UI display."""
        _DISPLAY = {
            "entry": "Entry Fragger",
            "awper": "AWPer",
            "support": "Support",
            "lurker": "Lurker",
            "igl": "IGL",
            "flex": "Flex",
            "unknown": "Unknown",
        }
        return _DISPLAY.get(self.value, self.value.title())


class IngestionStatus(Enum):
    QUEUED = auto()
    PROCESSING = auto()
    COMPLETED = auto()
    FAILED = auto()


class DemoMetadata(TypedDict):
    demo_name: str
    map_name: str
    tick_rate: float
    total_ticks: int
    processed_at: str
    is_pro: bool
    last_tick_processed: int


class PlayerStats(TypedDict):
    name: str
    kills: int
    deaths: int
    adr: float
    hs_percent: float
    kast: float
    rating: float


def team_from_demo_frame(demo_team) -> Team:
    """Convert demo_frame.Team (string enum) to app_types.Team (int enum).

    R1-02: Safe bridge between the two Team enum definitions.
    Accepts demo_frame.Team or a raw string ("ct", "t", "spectator").
    Raises ValueError for unknown values (fail-fast instead of silent default).
    """
    _MAP = {"ct": Team.CT, "t": Team.T, "spectator": Team.SPECTATOR}
    val = demo_team.value if hasattr(demo_team, "value") else str(demo_team).lower()
    result = _MAP.get(val)
    if result is None:
        raise ValueError(
            f"R1-02: Unknown team value '{val}' — expected 'ct', 't', or 'spectator'"
        )
    return result
