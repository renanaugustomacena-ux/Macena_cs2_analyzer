#!/usr/bin/env python3
"""
Demo Inspector — Unified demo file inspection tool.

Merges and supersedes 7 probe scripts:
  probe_demo_data, probe_entity_track, probe_events_advanced,
  probe_inventory, probe_stats_fields, probe_trajectories, probe_inv_direct

Usage:
  python demo_inspector.py events [--demo PATH]
  python demo_inspector.py fields [--demo PATH]
  python demo_inspector.py track  [--demo PATH] [--entity-type smoke|grenade|all]
  python demo_inspector.py all    [--demo PATH]
"""

import argparse
import os
import sys
from pathlib import Path

# --- Path stabilization ---
from _infra import PROJECT_ROOT, SOURCE_ROOT, path_stabilize

path_stabilize()


def find_demo(demo_path=None):
    """Find a demo file to inspect. Uses provided path or discovers first .dem in data/."""
    if demo_path:
        p = Path(demo_path)
        if p.is_file() and p.exists():
            return str(p)
        # If it's a directory, search for .dem files inside
        if p.is_dir():
            demos = list(p.glob("*.dem"))
            if demos:
                print(f"[AUTO] Using: {demos[0].name} (from {p})")
                return str(demos[0])
            print(f"[ERROR] No .dem files found in directory: {demo_path}")
            sys.exit(1)
        print(f"[ERROR] Demo file not found: {demo_path}")
        sys.exit(1)

    # Search order: data/ → ingestion folders → PRO_DEMO_PATH from config
    data_dir = SOURCE_ROOT / "data"
    demos = list(data_dir.rglob("*.dem"))
    if not demos:
        # Try ingestion folders
        for sub in ["demos_to_process", "ingestion/cache"]:
            alt = SOURCE_ROOT / sub
            if alt.exists():
                demos = list(alt.rglob("*.dem"))
                if demos:
                    break

    if not demos:
        # Try PRO_DEMO_PATH from user settings
        try:
            from Programma_CS2_RENAN.core.config import PRO_DEMO_PATH

            pro_dir = Path(PRO_DEMO_PATH)
            if pro_dir.exists():
                demos = list(pro_dir.glob("*.dem"))
        except ImportError:
            pass

    if not demos:
        print(f"[ERROR] No .dem files found under {data_dir}")
        sys.exit(1)

    print(f"[AUTO] Using: {demos[0].name}")
    return str(demos[0])


def get_parser(demo_path):
    """Create a DemoParser instance."""
    try:
        from demoparser2 import DemoParser
    except ImportError:
        print("[ERROR] demoparser2 not installed. Run: pip install demoparser2")
        sys.exit(1)
    return DemoParser(demo_path)


def extract_df(event_result):
    """Extract DataFrame from DemoParser event result tuple."""
    import pandas as pd

    if isinstance(event_result, pd.DataFrame):
        return event_result
    if isinstance(event_result, list) and event_result:
        item = event_result[0]
        if isinstance(item, tuple) and len(item) >= 2:
            return item[1]
        if isinstance(item, dict):
            return pd.DataFrame(event_result)
    return event_result


# =============================================================================
# SUBCOMMAND: events
# =============================================================================


def cmd_events(args):
    """Inspect demo events — list event types and probe critical events."""
    import pandas as pd

    demo = find_demo(args.demo)
    parser = get_parser(demo)

    print(f"\n{'='*60}")
    print(f"  DEMO EVENT INSPECTOR: {Path(demo).name}")
    print(f"{'='*60}")

    # List all event types
    events = parser.list_game_events()
    print(f"\n[Event Types] {len(events)} registered:")
    for e in sorted(events):
        print(f"  - {e}")

    # Probe critical events
    critical = ["player_death", "bomb_planted", "round_end", "weapon_fire", "player_hurt"]
    print(f"\n[Critical Events]")
    for event_name in critical:
        try:
            res = parser.parse_events([event_name])
            df = extract_df(res)
            if df is not None and not df.empty:
                print(f"\n  {event_name}: {len(df)} occurrences")
                print(f"  Columns: {list(df.columns)}")
                print(f"  Sample:\n{df.head(2).to_string(index=False)}")
            else:
                print(f"\n  {event_name}: no data")
        except Exception as e:
            print(f"\n  {event_name}: ERROR — {e}")

    # Coordinate extraction from player_death
    try:
        res = parser.parse_events(["player_death"])
        df = extract_df(res)
        if df is not None and not df.empty:
            coord_cols = [c for c in df.columns if any(k in c.lower() for k in ["x", "y", "pos"])]
            if coord_cols:
                print(f"\n  [Coordinate Columns]: {coord_cols}")
                print(f"  Sample coords:\n{df[coord_cols].head(3).to_string(index=False)}")
    except Exception as e:
        print(f"  Coordinate extraction failed: {e}")


# =============================================================================
# SUBCOMMAND: fields
# =============================================================================


def cmd_fields(args):
    """Inspect available tick fields — stats, inventory, and player data."""
    demo = find_demo(args.demo)
    parser = get_parser(demo)

    print(f"\n{'='*60}")
    print(f"  DEMO FIELD INSPECTOR: {Path(demo).name}")
    print(f"{'='*60}")

    # Player stats fields
    stat_fields = ["health", "kills_total", "deaths_total", "money", "player_name", "team_num"]
    print(f"\n[Player Stats]")
    try:
        df = parser.parse_ticks(stat_fields)
        print(f"  Columns found: {list(df.columns)}")
        print(f"  Rows: {len(df)}")
        if not df.empty:
            print(f"  Sample:\n{df.head(3).to_string(index=False)}")
    except Exception as e:
        print(f"  ERROR: {e}")

    # Weapon inventory fields
    inv_fields = ["tick", "player_name", "active_weapon_name"]
    for i in range(5):
        inv_fields.append(f"weapon_{i}")
    print(f"\n[Weapon Inventory]")
    try:
        df = parser.parse_ticks(inv_fields)
        print(f"  Columns found: {list(df.columns)}")
        if not df.empty:
            print(f"  Sample:\n{df.head(2).to_string(index=False)}")
    except Exception as e:
        print(f"  ERROR: {e}")

    # Direct inventory blob
    print(f"\n[Inventory Blob]")
    try:
        df = parser.parse_ticks(["tick", "steamid", "inventory"])
        print(f"  Columns: {list(df.columns)}")
        if not df.empty:
            print(f"  Sample:\n{df.head(3).to_string(index=False)}")
    except Exception as e:
        print(f"  Not available (schema is per-slot): {e}")


# =============================================================================
# SUBCOMMAND: track
# =============================================================================


def cmd_track(args):
    """Track entity trajectories (grenades, projectiles)."""
    import pandas as pd

    demo = find_demo(args.demo)
    parser = get_parser(demo)

    print(f"\n{'='*60}")
    print(f"  ENTITY TRACKER: {Path(demo).name}")
    print(f"{'='*60}")

    entity_type = getattr(args, "entity_type", "all")

    # Smoke grenade tracking
    if entity_type in ("smoke", "all"):
        print(f"\n[Smoke Grenade Trajectories]")
        try:
            res = parser.parse_events(["smokegrenade_detonate"])
            df = extract_df(res)
            if df is not None and not df.empty:
                print(f"  {len(df)} smoke detonations found")
                # Track first smoke
                if "entityid" in df.columns and "tick" in df.columns:
                    row = df.iloc[0]
                    eid = int(row["entityid"])
                    det_tick = int(row["tick"])
                    start = max(0, det_tick - 300)
                    print(f"  Tracking entity {eid} from tick {start} to {det_tick}")
                    try:
                        ticks = parser.parse_ticks(
                            ["X", "Y", "Z"], ticks=list(range(start, det_tick))
                        )
                        if "entityid" in ticks.columns:
                            trajectory = ticks[ticks["entityid"] == eid]
                            print(f"  Trajectory points: {len(trajectory)}")
                            if not trajectory.empty:
                                print(f"  Start: {trajectory.iloc[0][['X','Y','Z']].to_dict()}")
                                print(f"  End:   {trajectory.iloc[-1][['X','Y','Z']].to_dict()}")
                    except Exception as e:
                        print(f"  Trajectory tracking error: {e}")
            else:
                print("  No smoke detonations found")
        except Exception as e:
            print(f"  ERROR: {e}")

    # Grenade thrown
    if entity_type in ("grenade", "all"):
        print(f"\n[Grenade Throws]")
        try:
            res = parser.parse_events(["grenade_thrown"])
            df = extract_df(res)
            if df is not None and not df.empty:
                print(f"  {len(df)} grenades thrown")
                print(f"  Columns: {list(df.columns)}")
                print(f"  Sample:\n{df.head(3).to_string(index=False)}")
            else:
                print("  No grenade throws found")
        except Exception as e:
            print(f"  ERROR: {e}")

    # Entity listing
    if entity_type == "all":
        print(f"\n[Entity Classes at tick 1000]")
        try:
            entities = parser.list_entities(1000)
            if entities:
                proj = [e for e in entities if "Projectile" in str(e)]
                print(f"  Total entities: {len(entities)}")
                print(f"  Projectile entities: {len(proj)}")
                for p in proj[:5]:
                    print(f"    - {p}")
        except Exception as e:
            print(f"  ERROR: {e}")


# =============================================================================
# SUBCOMMAND: all
# =============================================================================


def cmd_all(args):
    """Run all inspection modes."""
    cmd_events(args)
    cmd_fields(args)
    cmd_track(args)


# =============================================================================
# CLI
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Demo Inspector — Unified demo file inspection tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
        "  python demo_inspector.py events\n"
        "  python demo_inspector.py fields --demo path/to/match.dem\n"
        "  python demo_inspector.py track --entity-type smoke\n"
        "  python demo_inspector.py all\n",
    )

    subparsers = parser.add_subparsers(dest="command", help="Inspection mode")

    # events
    p_events = subparsers.add_parser("events", help="Inspect event types and critical events")
    p_events.add_argument("--demo", type=str, help="Path to .dem file")

    # fields
    p_fields = subparsers.add_parser("fields", help="Inspect tick fields (stats, inventory)")
    p_fields.add_argument("--demo", type=str, help="Path to .dem file")

    # track
    p_track = subparsers.add_parser("track", help="Track entity trajectories")
    p_track.add_argument("--demo", type=str, help="Path to .dem file")
    p_track.add_argument(
        "--entity-type",
        choices=["smoke", "grenade", "all"],
        default="all",
        help="Entity type to track",
    )

    # all
    p_all = subparsers.add_parser("all", help="Run all inspection modes")
    p_all.add_argument("--demo", type=str, help="Path to .dem file")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    commands = {
        "events": cmd_events,
        "fields": cmd_fields,
        "track": cmd_track,
        "all": cmd_all,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
