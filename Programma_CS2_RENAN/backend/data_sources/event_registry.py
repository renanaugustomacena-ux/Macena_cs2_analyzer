"""
Game Event Schema Registry — Canonical specification of CS2 game events.

Derived from SteamDatabase Game Events dumps (awesome-cs2-master reference).
This registry tracks every CS2 event, its fields, whether Macena handles it,
and the handler file path if implemented.

Purpose:
  - Systematic tracking of parser coverage vs CS2 event vocabulary
  - Priority-driven expansion planning
  - Documentation: every field type and expected range in one place

Usage:
  from Programma_CS2_RENAN.backend.data_sources.event_registry import (
      EVENT_REGISTRY, get_implemented_events, get_coverage_report
  )
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class GameEventSpec:
    """Specification for a single CS2 game event."""

    name: str
    category: str  # "round", "combat", "utility", "economy", "movement", "meta"
    fields: Dict[str, str]  # field_name -> type description
    priority: str  # "critical", "standard", "optional"
    implemented: bool  # Whether Macena currently handles this event
    # F6-33: handler_path references are not validated at registration time. If handler
    # modules are relocated, references silently become stale. Add runtime validation
    # (hasattr/callable check) at event dispatch if reliability is critical.
    handler_path: Optional[str] = None  # File path to handler if implemented
    notes: str = ""  # Implementation notes or caveats


# ---------------------------------------------------------------------------
# CANONICAL EVENT REGISTRY
# Organized by category, ordered by priority within each category.
# ---------------------------------------------------------------------------

EVENT_REGISTRY: Dict[str, GameEventSpec] = {
    # ===== ROUND LIFECYCLE =====
    "round_end": GameEventSpec(
        name="round_end",
        category="round",
        fields={"winner": "int (team)", "reason": "int (round end reason)", "message": "str"},
        priority="critical",
        implemented=True,
        handler_path="backend/data_sources/demo_parser.py",
        notes="Used to count total rounds for per-round stat calculation.",
    ),
    "round_start": GameEventSpec(
        name="round_start",
        category="round",
        fields={"timelimit": "int (seconds)", "fraglimit": "int", "objective": "str"},
        priority="standard",
        implemented=False,
        notes="Useful for round phase timing — freeze time boundary detection.",
    ),
    "round_freeze_end": GameEventSpec(
        name="round_freeze_end",
        category="round",
        fields={},
        priority="standard",
        implemented=True,
        handler_path="backend/data_sources/round_context.py",
        notes="Extracted via round_context.extract_round_context(). Marks round action start for time_in_round computation.",
    ),
    "round_mvp": GameEventSpec(
        name="round_mvp",
        category="round",
        fields={"userid": "int", "reason": "int (mvp reason)"},
        priority="optional",
        implemented=False,
        notes="MVP tracking — could feed into impact scoring.",
    ),
    "begin_new_match": GameEventSpec(
        name="begin_new_match",
        category="round",
        fields={},
        priority="standard",
        implemented=False,
        notes="Match boundary detection in multi-match demos.",
    ),
    # ===== COMBAT =====
    "player_death": GameEventSpec(
        name="player_death",
        category="combat",
        fields={
            "userid": "int (victim)",
            "attacker": "int (killer)",
            "assister": "int",
            "weapon": "str",
            "headshot": "bool",
            "penetrated": "int (wallbang penetration count)",
            "noscope": "bool",
            "thrusmoke": "bool",
            "attackerblind": "bool",
            "dominated": "int",
            "revenge": "int",
            "assistedflash": "bool",
        },
        priority="critical",
        implemented=True,
        handler_path="backend/data_sources/demo_parser.py",
        notes="Fully implemented — headshot, penetrated, thrusmoke, attackerblind, noscope all extracted. Trade kill detection via trade_kill_detector.py.",
    ),
    "player_hurt": GameEventSpec(
        name="player_hurt",
        category="combat",
        fields={
            "userid": "int (victim)",
            "attacker": "int",
            "health": "int (remaining)",
            "armor": "int (remaining)",
            "weapon": "str",
            "dmg_health": "int",
            "dmg_armor": "int",
            "hitgroup": "int (body part)",
        },
        priority="critical",
        implemented=True,
        handler_path="backend/data_sources/demo_parser.py",
        notes="Used for accuracy calculation. Weapon field enables per-grenade damage breakdown (Proposal 2).",
    ),
    "weapon_fire": GameEventSpec(
        name="weapon_fire",
        category="combat",
        fields={"userid": "int", "weapon": "str", "silenced": "bool"},
        priority="critical",
        implemented=True,
        handler_path="backend/data_sources/demo_parser.py",
        notes="Used for shot count in accuracy calculation. Also used for flash/smoke throw counting in round_stats_builder.",
    ),
    # ===== BOMB =====
    "bomb_planted": GameEventSpec(
        name="bomb_planted",
        category="round",
        fields={"userid": "int (planter)", "site": "int (A=0, B=1)"},
        priority="critical",
        implemented=True,
        handler_path="backend/data_sources/round_context.py",
        notes="Extracted via round_context.extract_bomb_events(). Used for post-plant analysis and game tree transitions.",
    ),
    "bomb_defused": GameEventSpec(
        name="bomb_defused",
        category="round",
        fields={"userid": "int (defuser)", "site": "int"},
        priority="critical",
        implemented=True,
        handler_path="backend/data_sources/round_context.py",
        notes="Extracted via round_context.extract_bomb_events(). Complements bomb_planted for round outcome classification.",
    ),
    "bomb_pickup": GameEventSpec(
        name="bomb_pickup",
        category="round",
        fields={"userid": "int"},
        priority="optional",
        implemented=False,
        notes="Bomb carrier tracking — useful for T-side role identification.",
    ),
    "bomb_dropped": GameEventSpec(
        name="bomb_dropped",
        category="round",
        fields={"userid": "int", "entindex": "int"},
        priority="optional",
        implemented=False,
        notes="Bomb drop events — potential coaching signal for careless bomb handling.",
    ),
    # ===== UTILITY =====
    "flashbang_detonate": GameEventSpec(
        name="flashbang_detonate",
        category="utility",
        fields={
            "userid": "int (thrower)",
            "entityid": "int",
            "x": "float",
            "y": "float",
            "z": "float",
        },
        priority="standard",
        implemented=False,
        notes="Flash detonation position — enables lineup analysis.",
    ),
    "hegrenade_detonate": GameEventSpec(
        name="hegrenade_detonate",
        category="utility",
        fields={
            "userid": "int (thrower)",
            "entityid": "int",
            "x": "float",
            "y": "float",
            "z": "float",
        },
        priority="standard",
        implemented=False,
        notes="HE detonation position — enables damage area analysis.",
    ),
    "smokegrenade_detonate": GameEventSpec(
        name="smokegrenade_detonate",
        category="utility",
        fields={
            "userid": "int (thrower)",
            "entityid": "int",
            "x": "float",
            "y": "float",
            "z": "float",
        },
        priority="standard",
        implemented=False,
        notes="Smoke position — critical for entropy analysis and line-of-sight blocking.",
    ),
    "inferno_startburn": GameEventSpec(
        name="inferno_startburn",
        category="utility",
        fields={"entityid": "int", "x": "float", "y": "float", "z": "float"},
        priority="standard",
        implemented=False,
        notes="Molotov/incendiary ignition — area denial analysis.",
    ),
    "inferno_expire": GameEventSpec(
        name="inferno_expire",
        category="utility",
        fields={"entityid": "int", "x": "float", "y": "float", "z": "float"},
        priority="optional",
        implemented=False,
        notes="Molotov expiration — duration analysis.",
    ),
    "decoy_started": GameEventSpec(
        name="decoy_started",
        category="utility",
        fields={"userid": "int", "entityid": "int", "x": "float", "y": "float", "z": "float"},
        priority="optional",
        implemented=False,
        notes="Decoy deception — low-priority but feeds deception index.",
    ),
    "player_blind": GameEventSpec(
        name="player_blind",
        category="utility",
        fields={
            "userid": "int (blinded player)",
            "attacker": "int (flasher)",
            "blind_duration": "float",
        },
        priority="critical",
        implemented=True,
        handler_path="backend/processing/round_stats_builder.py",
        notes="Flash effectiveness — used for flash assist detection (128-tick window cross-ref with kills).",
    ),
    # ===== ECONOMY =====
    "item_purchase": GameEventSpec(
        name="item_purchase",
        category="economy",
        fields={"userid": "int", "weapon": "str"},
        priority="optional",
        implemented=False,
        notes="Economy tracking — per-item purchase analysis.",
    ),
    "item_pickup": GameEventSpec(
        name="item_pickup",
        category="economy",
        fields={"userid": "int", "item": "str"},
        priority="optional",
        implemented=False,
        notes="Weapon pickup tracking (scavenging from dead players).",
    ),
    # ===== PLAYER STATE =====
    "player_connect": GameEventSpec(
        name="player_connect",
        category="meta",
        fields={"name": "str", "userid": "int", "networkid": "str"},
        priority="optional",
        implemented=False,
        notes="Player join detection — useful for disconnect tracking.",
    ),
    "player_disconnect": GameEventSpec(
        name="player_disconnect",
        category="meta",
        fields={"userid": "int", "reason": "str", "name": "str", "networkid": "str"},
        priority="optional",
        implemented=False,
        notes="Player leave — could flag abandoned matches.",
    ),
    "player_team": GameEventSpec(
        name="player_team",
        category="meta",
        fields={"userid": "int", "team": "int", "oldteam": "int", "disconnect": "bool"},
        priority="standard",
        implemented=False,
        notes="Team assignment — important for side tracking across half-switch.",
    ),
}


# ---------------------------------------------------------------------------
# REGISTRY QUERY FUNCTIONS
# ---------------------------------------------------------------------------


def get_implemented_events() -> List[str]:
    """Return names of all events Macena currently handles."""
    return [name for name, spec in EVENT_REGISTRY.items() if spec.implemented]


def get_unimplemented_events(priority: Optional[str] = None) -> List[str]:
    """Return names of unimplemented events, optionally filtered by priority."""
    events = [name for name, spec in EVENT_REGISTRY.items() if not spec.implemented]
    if priority:
        events = [name for name in events if EVENT_REGISTRY[name].priority == priority]
    return events


def get_events_by_category(category: str) -> List[GameEventSpec]:
    """Return all events in a given category."""
    return [spec for spec in EVENT_REGISTRY.values() if spec.category == category]


def get_coverage_report() -> Dict[str, Any]:
    """
    Generate a coverage report showing implementation status.

    Returns:
        Dict with total, implemented, unimplemented counts and percentages.
    """
    total = len(EVENT_REGISTRY)
    implemented = sum(1 for spec in EVENT_REGISTRY.values() if spec.implemented)

    by_priority = {}
    for priority in ("critical", "standard", "optional"):
        p_total = sum(1 for s in EVENT_REGISTRY.values() if s.priority == priority)
        p_impl = sum(1 for s in EVENT_REGISTRY.values() if s.priority == priority and s.implemented)
        by_priority[priority] = {
            "total": p_total,
            "implemented": p_impl,
            "coverage_pct": round(p_impl / max(1, p_total) * 100, 1),
        }

    by_category = {}
    for category in ("round", "combat", "utility", "economy", "meta"):
        c_total = sum(1 for s in EVENT_REGISTRY.values() if s.category == category)
        c_impl = sum(1 for s in EVENT_REGISTRY.values() if s.category == category and s.implemented)
        by_category[category] = {
            "total": c_total,
            "implemented": c_impl,
            "coverage_pct": round(c_impl / max(1, c_total) * 100, 1),
        }

    return {
        "total_events": total,
        "implemented": implemented,
        "unimplemented": total - implemented,
        "overall_coverage_pct": round(implemented / max(1, total) * 100, 1),
        "by_priority": by_priority,
        "by_category": by_category,
    }
