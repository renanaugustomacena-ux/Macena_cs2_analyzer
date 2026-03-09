"""
Player Knowledge State — Player-POV Perception System

Computes what a player KNOWS at each tick, respecting the same sensorial
limitations as the real player. The AI coach learns with the player's
perspective, NOT with wallhacks.

Sensorial model:
- Own state: full access (position, yaw, health, armor, weapon)
- Teammates: always known (radar/comms)
- Visible enemies: ONLY when enemies_visible > 0 AND within FOV cone
- Last-known enemies: memory with exponential decay (half-life 2.5s)
- Sound inference: weapon_fire events within hearing range → direction + distance
- Utility zones: active smokes, molotovs, recent flashes
- Bomb state: known to all players
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from Programma_CS2_RENAN.core.constants import (
    FOV_DEGREES,
    FLASH_DURATION_TICKS,
    MEMORY_CUTOFF_TICKS,
    MEMORY_DECAY_TAU_TICKS,
    Z_FLOOR_THRESHOLD,
)
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.player_knowledge")

# ============ Constants ============
# H-10: FOV_DEGREES, MEMORY_DECAY_TAU, MEMORY_CUTOFF, FLASH_DURATION
# now imported from core.constants (single source of truth).

HEARING_RANGE_GUNFIRE = 2000.0
"""World units within which gunfire is audible."""

HEARING_RANGE_FOOTSTEP = 1000.0
"""World units within which footsteps are audible."""

# P-PK-02: Hard cap on tracked enemies in memory dict.
# CS2 is 5v5 so max 5 enemies; 10 allows for edge cases in parsed data.
MAX_TRACKED_ENEMIES = 10

# Backward-compatible alias (M-08)
MEMORY_DECAY_TAU = MEMORY_DECAY_TAU_TICKS

SMOKE_RADIUS = 200.0
"""Approximate smoke cloud radius in world units."""

MOLOTOV_RADIUS = 100.0
"""Approximate molotov fire radius in world units."""


# ============ Data Structures ============


@dataclass
class VisibleEntity:
    """An entity visible to the player."""

    pos_x: float
    pos_y: float
    pos_z: float
    distance: float
    is_teammate: bool
    health: int = 100
    weapon: str = ""


@dataclass
class LastKnownEnemy:
    """An enemy position from memory, with temporal decay."""

    pos_x: float
    pos_y: float
    pos_z: float
    decay_factor: float  # 1.0 = just seen, 0.0 = forgotten
    ticks_since_seen: int = 0


@dataclass
class HeardEvent:
    """A sound event the player can hear."""

    pos_x: float
    pos_y: float
    pos_z: float
    distance: float
    direction_rad: float  # angle from player to event source (radians)
    event_type: str = "gunfire"  # gunfire, explosion, etc.


@dataclass
class UtilityZone:
    """An active utility zone (smoke, molotov, flash)."""

    pos_x: float
    pos_y: float
    pos_z: float
    radius: float
    utility_type: str  # "smoke", "molotov", "flash"


@dataclass
class PlayerKnowledge:
    """What a player KNOWS at a specific tick.

    This is the core output of the perception system. It encodes all
    information legitimately available to the player, respecting sensorial
    limitations.
    """

    # Own state (full access)
    own_pos_x: float = 0.0
    own_pos_y: float = 0.0
    own_pos_z: float = 0.0
    own_yaw: float = 0.0
    own_health: int = 100
    own_armor: int = 0
    own_weapon: str = ""
    own_team: str = ""
    is_crouching: bool = False
    is_scoped: bool = False
    is_blinded: bool = False

    # Teammates (always known via radar/comms)
    teammate_positions: List[VisibleEntity] = field(default_factory=list)
    teammates_alive: int = 0

    # Visible enemies (only those in FOV when enemies_visible > 0)
    visible_enemies: List[VisibleEntity] = field(default_factory=list)
    visible_enemy_count: int = 0

    # Last-known enemy positions (memory with temporal decay)
    last_known_enemies: List[LastKnownEnemy] = field(default_factory=list)

    # Sound information (within hearing range)
    heard_events: List[HeardEvent] = field(default_factory=list)

    # Active utility zones
    utility_zones: List[UtilityZone] = field(default_factory=list)

    # Bomb state (known to all)
    bomb_planted: bool = False
    bomb_pos_x: float = 0.0
    bomb_pos_y: float = 0.0
    bomb_pos_z: float = 0.0

    # R4-14-01: True when position is (0,0,0) fallback — likely missing data
    position_is_fallback: bool = False


# ============ Geometry Helpers ============


def _normalize_angle(angle: float) -> float:
    """Normalize angle to [0, 360) range."""
    return angle % 360.0


def _angle_diff(a: float, b: float) -> float:
    """Compute shortest angular difference between two angles in degrees.

    Returns value in [0, 180].
    """
    diff = abs(_normalize_angle(a) - _normalize_angle(b))
    return min(diff, 360.0 - diff)


def _is_in_fov(
    player_x: float,
    player_y: float,
    player_yaw: float,
    target_x: float,
    target_y: float,
    fov_degrees: float = FOV_DEGREES,
    player_z: float = 0.0,
    target_z: float = 0.0,
    z_floor_threshold: float = Z_FLOOR_THRESHOLD,
) -> bool:
    """Check if a target position is within the player's FOV cone.

    Uses atan2 for direction and handles yaw wraparound correctly.
    H-11: Includes Z-distance check for multi-level maps (Nuke, Vertigo).
    """
    # H-11: Z-level guard — players on different floors are not visible
    if abs(player_z - target_z) > z_floor_threshold:
        return False

    dx = target_x - player_x
    dy = target_y - player_y

    if abs(dx) < 0.01 and abs(dy) < 0.01:
        return True  # Same position considered visible

    # atan2 returns angle in radians, convert to degrees
    # CS2 yaw: 0=East, 90=North, 180=West, 270=South (counter-clockwise)
    angle_to_target = math.degrees(math.atan2(dy, dx))
    angle_to_target = _normalize_angle(angle_to_target)

    half_fov = fov_degrees / 2.0
    return _angle_diff(player_yaw, angle_to_target) <= half_fov


def _distance_2d(x1: float, y1: float, x2: float, y2: float) -> float:
    """2D Euclidean distance."""
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def _direction_rad(from_x: float, from_y: float, to_x: float, to_y: float) -> float:
    """Angle in radians from one point to another."""
    return math.atan2(to_y - from_y, to_x - from_x)


# ============ Builder ============


class PlayerKnowledgeBuilder:
    """Constructs PlayerKnowledge from match database records.

    Implements the NO-WALLHACK sensorial model: the coach sees only
    what the player legitimately knows at each tick.
    """

    def __init__(
        self,
        fov_degrees: float = FOV_DEGREES,
        hearing_range_gunfire: float = HEARING_RANGE_GUNFIRE,
        memory_decay_tau: float = MEMORY_DECAY_TAU,
        memory_cutoff_ticks: int = MEMORY_CUTOFF_TICKS,
    ):
        self.fov_degrees = fov_degrees
        self.hearing_range_gunfire = hearing_range_gunfire
        self.memory_decay_tau = memory_decay_tau
        self.memory_cutoff_ticks = memory_cutoff_ticks

    def build_knowledge(
        self,
        player_tick,
        all_players_at_tick: list,
        recent_player_history: Optional[list] = None,
        recent_all_players_history: Optional[dict] = None,
        active_events: Optional[list] = None,
    ) -> PlayerKnowledge:
        """Build what the player SHOULD know at this tick.

        Args:
            player_tick: MatchTickState for the target player at current tick.
            all_players_at_tick: List of MatchTickState for ALL players at current tick.
            recent_player_history: List of MatchTickState for this player over
                recent ticks (for trajectory). Optional.
            recent_all_players_history: Dict mapping tick -> List[MatchTickState]
                for all players over recent ticks (for enemy memory). Optional.
            active_events: List of MatchEventState near this tick (for sound
                inference + utility zones). Optional.

        Returns:
            PlayerKnowledge with all legitimately available information.
        """
        knowledge = PlayerKnowledge()

        # --- Own state (full access) ---
        knowledge.own_pos_x = float(getattr(player_tick, "pos_x", 0))
        knowledge.own_pos_y = float(getattr(player_tick, "pos_y", 0))
        knowledge.own_pos_z = float(getattr(player_tick, "pos_z", 0))
        # R4-14-01: Flag (0,0,0) positions as likely missing data
        if (
            knowledge.own_pos_x == 0.0
            and knowledge.own_pos_y == 0.0
            and knowledge.own_pos_z == 0.0
        ):
            knowledge.position_is_fallback = True
            logger.debug(
                "Zero position for player at tick %d — possible missing data",
                int(getattr(player_tick, "tick", 0)),
            )
        knowledge.own_yaw = float(getattr(player_tick, "yaw", 0))
        knowledge.own_health = int(getattr(player_tick, "health", 100))
        knowledge.own_armor = int(getattr(player_tick, "armor", 0))
        knowledge.own_weapon = str(getattr(player_tick, "active_weapon", ""))
        knowledge.own_team = str(getattr(player_tick, "team", ""))
        knowledge.is_crouching = bool(getattr(player_tick, "is_crouching", False))
        knowledge.is_scoped = bool(getattr(player_tick, "is_scoped", False))
        knowledge.is_blinded = bool(getattr(player_tick, "is_blinded", False))

        player_name = str(getattr(player_tick, "player_name", ""))
        player_team = knowledge.own_team
        current_tick = int(getattr(player_tick, "tick", 0))
        enemies_visible_count = int(getattr(player_tick, "enemies_visible", 0))

        # --- Classify all players at this tick ---
        teammates = []
        enemies = []
        for p in all_players_at_tick:
            p_name = str(getattr(p, "player_name", ""))
            if p_name == player_name:
                continue
            if not getattr(p, "is_alive", True):
                continue

            p_team = str(getattr(p, "team", ""))
            entity = VisibleEntity(
                pos_x=float(getattr(p, "pos_x", 0)),
                pos_y=float(getattr(p, "pos_y", 0)),
                pos_z=float(getattr(p, "pos_z", 0)),
                distance=_distance_2d(
                    knowledge.own_pos_x,
                    knowledge.own_pos_y,
                    float(getattr(p, "pos_x", 0)),
                    float(getattr(p, "pos_y", 0)),
                ),
                is_teammate=(p_team == player_team),
                health=int(getattr(p, "health", 100)),
                weapon=str(getattr(p, "active_weapon", "")),
            )

            if p_team == player_team:
                teammates.append(entity)
            else:
                enemies.append(entity)

        # --- Teammates: always known (radar/comms) ---
        knowledge.teammate_positions = teammates
        knowledge.teammates_alive = len(teammates)

        # --- Visible enemies: only when enemies_visible > 0 AND in FOV ---
        if enemies_visible_count > 0 and not knowledge.is_blinded:
            # Sort enemies by distance, take those in FOV up to the count
            in_fov = [
                e
                for e in enemies
                if _is_in_fov(
                    knowledge.own_pos_x,
                    knowledge.own_pos_y,
                    knowledge.own_yaw,
                    e.pos_x,
                    e.pos_y,
                    self.fov_degrees,
                )
            ]
            in_fov.sort(key=lambda e: e.distance)
            knowledge.visible_enemies = in_fov[:enemies_visible_count]
            knowledge.visible_enemy_count = len(knowledge.visible_enemies)

        # --- Last-known enemy positions (memory with temporal decay) ---
        if recent_all_players_history:
            self._build_enemy_memory(
                knowledge, player_name, player_team, current_tick, recent_all_players_history
            )

        # --- Sound inference from events ---
        if active_events:
            self._build_sound_events(knowledge, active_events, current_tick)

        # --- Active utility zones from events ---
        if active_events:
            self._build_utility_zones(knowledge, active_events, current_tick)

        return knowledge

    def _build_enemy_memory(
        self,
        knowledge: PlayerKnowledge,
        player_name: str,
        player_team: str,
        current_tick: int,
        recent_all_players_history: dict,
    ) -> None:
        """Build last-known enemy positions from recent tick history.

        For each enemy, find the most recent tick where this player
        could see them (enemies_visible > 0 and enemy in FOV), then
        apply exponential decay based on time elapsed.
        """
        # Track: enemy_name -> (pos_x, pos_y, pos_z, last_visible_tick)
        enemy_last_seen: dict = {}

        # Pre-index: tick -> {player_name -> player_obj} for O(1) lookup
        indexed_history: dict = {}
        for hist_tick, players_at_tick in recent_all_players_history.items():
            by_name: dict = {}
            for p in players_at_tick:
                by_name[str(getattr(p, "player_name", ""))] = p
            indexed_history[hist_tick] = by_name

        # Walk history from oldest to newest
        sorted_ticks = sorted(indexed_history.keys())
        for hist_tick in sorted_ticks:
            by_name = indexed_history[hist_tick]

            # O(1) lookup for our player
            our_player = by_name.get(player_name)
            if not our_player:
                continue

            our_vis_count = int(getattr(our_player, "enemies_visible", 0))
            if our_vis_count <= 0:
                continue

            our_x = float(getattr(our_player, "pos_x", 0))
            our_y = float(getattr(our_player, "pos_y", 0))
            our_yaw = float(getattr(our_player, "yaw", 0))

            # Find enemies in FOV at this historical tick
            enemies_in_fov = []
            for p_name, p in by_name.items():
                if p_name == player_name:
                    continue
                if str(getattr(p, "team", "")) == player_team:
                    continue
                if not getattr(p, "is_alive", True):
                    continue

                p_x = float(getattr(p, "pos_x", 0))
                p_y = float(getattr(p, "pos_y", 0))

                if _is_in_fov(our_x, our_y, our_yaw, p_x, p_y, self.fov_degrees):
                    dist = _distance_2d(our_x, our_y, p_x, p_y)
                    enemies_in_fov.append((p_name, p_x, p_y, float(getattr(p, "pos_z", 0)), dist))

            # Take closest N matching the visible count
            enemies_in_fov.sort(key=lambda e: e[4])
            for name, ex, ey, ez, _ in enemies_in_fov[:our_vis_count]:
                enemy_last_seen[name] = (ex, ey, ez, hist_tick)

            # P-PK-02: Evict oldest entry if dict exceeds cap
            if len(enemy_last_seen) > MAX_TRACKED_ENEMIES:
                oldest_key = min(enemy_last_seen, key=lambda k: enemy_last_seen[k][3])
                del enemy_last_seen[oldest_key]

        # Convert to LastKnownEnemy with decay
        for name, (ex, ey, ez, last_tick) in enemy_last_seen.items():
            ticks_elapsed = current_tick - last_tick
            if ticks_elapsed > self.memory_cutoff_ticks:
                continue
            if ticks_elapsed <= 0:
                continue  # Currently visible → already in visible_enemies

            decay = math.exp(-ticks_elapsed / self.memory_decay_tau)
            knowledge.last_known_enemies.append(
                LastKnownEnemy(
                    pos_x=ex,
                    pos_y=ey,
                    pos_z=ez,
                    decay_factor=decay,
                    ticks_since_seen=ticks_elapsed,
                )
            )

    def _build_sound_events(
        self,
        knowledge: PlayerKnowledge,
        events: list,
        current_tick: int,
        tick_rate: int = 64,
    ) -> None:
        """Infer audible events from MatchEventState records.

        The player can hear gunfire within HEARING_RANGE_GUNFIRE and
        explosions within the same range. Direction is computed as the
        angle from the player to the event source.

        Args:
            tick_rate: Server tick rate (64 or 128). Used to compute the
                       1-second audible event window in ticks.
        """
        audible_types = {"weapon_fire", "he_detonate", "flash_detonate", "bomb_planted"}

        for evt in events:
            evt_type = str(getattr(evt, "event_type", ""))
            if evt_type not in audible_types:
                continue

            evt_tick = int(getattr(evt, "tick", 0))
            # P3-05: Use tick_rate to compute 1-second window instead of hardcoded 64.
            if abs(evt_tick - current_tick) > tick_rate:
                continue

            evt_x = float(getattr(evt, "pos_x", 0))
            evt_y = float(getattr(evt, "pos_y", 0))
            evt_z = float(getattr(evt, "pos_z", 0))

            dist = _distance_2d(knowledge.own_pos_x, knowledge.own_pos_y, evt_x, evt_y)

            if dist > self.hearing_range_gunfire:
                continue

            direction = _direction_rad(knowledge.own_pos_x, knowledge.own_pos_y, evt_x, evt_y)

            knowledge.heard_events.append(
                HeardEvent(
                    pos_x=evt_x,
                    pos_y=evt_y,
                    pos_z=evt_z,
                    distance=dist,
                    direction_rad=direction,
                    event_type=evt_type,
                )
            )

    def _build_utility_zones(
        self,
        knowledge: PlayerKnowledge,
        events: list,
        current_tick: int,
    ) -> None:
        """Build active utility zones from MatchEventState records.

        Identifies smokes and molotovs that are currently active
        (between start and end events), and recent flash detonations.
        """
        # Active utility: start events without matching end events
        # C-10: Time-based expiry constants (in ticks at 64 Hz)
        SMOKE_MAX_TICKS = 18 * 64   # 18 seconds
        MOLOTOV_MAX_TICKS = 7 * 64  # 7 seconds

        active_starts = {}  # entity_id -> event
        for evt in events:
            evt_type = str(getattr(evt, "event_type", ""))
            evt_tick = int(getattr(evt, "tick", 0))
            entity_id = int(getattr(evt, "entity_id", -1))

            # R4-06-02 / C-10: For entity_id=-1, use position-based matching
            # with increased radius (100 units) and temporal correlation
            if entity_id == -1:
                if evt_type in ("smoke_end", "molotov_end") and evt_tick <= current_tick:
                    evt_x = float(getattr(evt, "pos_x", 0))
                    evt_y = float(getattr(evt, "pos_y", 0))
                    best_match = None
                    best_dist = float("inf")
                    for eid, start_evt in active_starts.items():
                        start_type = str(getattr(start_evt, "event_type", ""))
                        if ("smoke" in evt_type) != ("smoke" in start_type):
                            continue
                        sx = float(getattr(start_evt, "pos_x", 0))
                        sy = float(getattr(start_evt, "pos_y", 0))
                        dist = math.sqrt((evt_x - sx) ** 2 + (evt_y - sy) ** 2)
                        # R4-06-02: Increased radius from 50→100 for entity_id=-1
                        # plus temporal check (end must be after start)
                        start_tick = int(getattr(start_evt, "tick", 0))
                        if dist < 100.0 and dist < best_dist and evt_tick >= start_tick:
                            best_match = eid
                            best_dist = dist
                    if best_match is not None:
                        del active_starts[best_match]
                continue

            if evt_type in ("smoke_start", "molotov_start"):
                if evt_tick <= current_tick:
                    active_starts[entity_id] = evt
            elif evt_type in ("smoke_end", "molotov_end"):
                if evt_tick <= current_tick and entity_id in active_starts:
                    del active_starts[entity_id]

        # C-10: Expire stale utility zones that exceeded max duration
        expired_ids = []
        for eid, evt in active_starts.items():
            evt_type = str(getattr(evt, "event_type", ""))
            evt_tick = int(getattr(evt, "tick", 0))
            max_dur = SMOKE_MAX_TICKS if "smoke" in evt_type else MOLOTOV_MAX_TICKS
            if current_tick - evt_tick > max_dur:
                expired_ids.append(eid)
        for eid in expired_ids:
            del active_starts[eid]

        for evt in active_starts.values():
            evt_type = str(getattr(evt, "event_type", ""))
            util_type = "smoke" if "smoke" in evt_type else "molotov"
            radius = SMOKE_RADIUS if util_type == "smoke" else MOLOTOV_RADIUS

            knowledge.utility_zones.append(
                UtilityZone(
                    pos_x=float(getattr(evt, "pos_x", 0)),
                    pos_y=float(getattr(evt, "pos_y", 0)),
                    pos_z=float(getattr(evt, "pos_z", 0)),
                    radius=radius,
                    utility_type=util_type,
                )
            )

        # Recent flashes (M-12: tick-rate aware via FLASH_DURATION_TICKS)
        for evt in events:
            if str(getattr(evt, "event_type", "")) != "flash_detonate":
                continue
            evt_tick = int(getattr(evt, "tick", 0))
            if 0 <= (current_tick - evt_tick) <= FLASH_DURATION_TICKS:
                knowledge.utility_zones.append(
                    UtilityZone(
                        pos_x=float(getattr(evt, "pos_x", 0)),
                        pos_y=float(getattr(evt, "pos_y", 0)),
                        pos_z=float(getattr(evt, "pos_z", 0)),
                        # NOTE (F2-08): Using SMOKE_RADIUS (200 units) as a proxy for flash
                        # effective radius. CS2 actual values: smoke ~288 units, flash
                        # effective blind radius ~400 units. Accepted approximation for now.
                        radius=SMOKE_RADIUS,
                        utility_type="flash",
                    )
                )
