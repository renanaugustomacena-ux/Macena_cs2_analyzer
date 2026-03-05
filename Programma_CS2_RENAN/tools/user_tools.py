#!/usr/bin/env python3
"""
User Tools — Consolidated interactive utilities for Macena CS2 Analyzer.

Merges: Manual_Data_v2, Personalize_v2, GUI_Master_Customizer,
        ML_Coach_Control_Panel, manage_sync, Seed_Pro_Data, Heartbeat_Monitor

Usage:
  python user_tools.py personalize
  python user_tools.py customize
  python user_tools.py manual-entry
  python user_tools.py weights
  python user_tools.py heartbeat
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from _infra import PROJECT_ROOT, SOURCE_ROOT, path_stabilize

path_stabilize()

from Programma_CS2_RENAN.core.config import get_setting, refresh_settings, save_user_setting
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.user_tools")


# =============================================================================
# personalize — First-time user setup
# =============================================================================


def cmd_personalize(args):
    """Collect player name, Steam ID, and API keys."""
    print("\n=== MACENA CS2 ANALYZER — PERSONALIZATION ===\n")

    name = input("Your CS2 player name: ").strip()
    if name:
        save_user_setting("PLAYER_NAME", name)
        print(f"  Saved PLAYER_NAME = {name}")

    steam_id = input("Your Steam ID (leave blank to skip): ").strip()
    if steam_id:
        save_user_setting("STEAM_ID", steam_id)
        print(f"  Saved STEAM_ID = {steam_id}")

    steam_key = input("Steam Web API Key (leave blank to skip): ").strip()
    if steam_key:
        save_user_setting("STEAM_API_KEY", steam_key)
        print(f"  Saved STEAM_API_KEY = ***")  # F8-10: no key fragment — avoids partial credential exposure

    faceit_key = input("FACEIT API Key (leave blank to skip): ").strip()
    if faceit_key:
        save_user_setting("FACEIT_API_KEY", faceit_key)
        print(f"  Saved FACEIT_API_KEY = ***")  # F8-10: no key fragment

    refresh_settings()
    print("\nPersonalization complete.")


# =============================================================================
# customize — GUI preferences
# =============================================================================


def cmd_customize(args):
    """Set language, theme, and font preferences."""
    print("\n=== GUI CUSTOMIZER ===\n")

    lang = input(
        "Language [en/pt/it] (current: {}): ".format(get_setting("LANGUAGE", "en"))
    ).strip()
    if lang in ("en", "pt", "it"):
        save_user_setting("LANGUAGE", lang)
        print(f"  Language set to: {lang}")

    theme = input(
        "Theme [cs2theme/csgotheme/cs16theme] (current: {}): ".format(
            get_setting("ACTIVE_THEME", "cs2theme")
        )
    ).strip()
    if theme:
        save_user_setting("ACTIVE_THEME", theme)
        print(f"  Theme set to: {theme}")

    font = input(
        "Font type [default/monospace/condensed] (current: {}): ".format(
            get_setting("FONT_TYPE", "default")
        )
    ).strip()
    if font:
        save_user_setting("FONT_TYPE", font)
        print(f"  Font set to: {font}")

    refresh_settings()
    print("\nCustomization saved.")


# =============================================================================
# manual-entry — Manual HLTV pro player stats
# =============================================================================


def cmd_manual_entry(args):
    """Manually enter pro player baseline data."""
    print("\n=== MANUAL DATA ENTRY (HLTV Baselines) ===\n")

    from Programma_CS2_RENAN.backend.storage.database import get_db_manager
    from Programma_CS2_RENAN.backend.storage.db_models import PlayerMatchStats

    db = get_db_manager()

    while True:
        name = input("\nPlayer name (or 'q' to quit): ").strip()
        if name.lower() == "q":
            break

        try:
            rating = float(input("  HLTV Rating 2.0: "))
            adr = float(input("  ADR: "))
            kast = float(input("  KAST %: "))
            hs = float(input("  Headshot %: "))
            kd = float(input("  K/D Ratio: "))
            impact = float(input("  Impact: "))
            accuracy = float(input("  Accuracy: "))
            econ = float(input("  Economic Rating: "))
        except ValueError:
            print("  Invalid number. Entry skipped.")
            continue

        entry = PlayerMatchStats(
            player_name=name,
            demo_name=f"manual_entry_{datetime.now().strftime('%Y%m%d')}",
            avg_kills=0.0,
            avg_deaths=0.0,
            avg_adr=adr,
            avg_hs=hs,
            avg_kast=kast,
            kill_std=0.0,
            adr_std=0.0,
            kd_ratio=kd,
            impact_rounds=impact,
            accuracy=accuracy,
            econ_rating=econ,
            rating=rating,
            anomaly_score=0.0,
            sample_weight=1.0,
            is_pro=True,
            processed_at=datetime.now(timezone.utc),  # F8-08: timezone-aware UTC datetime
        )

        with db.get_session() as s:
            s.add(entry)
            s.commit()
        print(f"  Saved: {name} (rating={rating})")


# =============================================================================
# weights — ML feature weight overrides
# =============================================================================


def cmd_weights(args):
    """View and override ML coach feature weights."""
    print("\n=== ML COACH WEIGHT OVERRIDES ===\n")

    overrides = get_setting("COACH_WEIGHT_OVERRIDES", {})
    print(f"Current overrides: {overrides if overrides else '(none)'}")

    action = input("\n[v]iew / [s]et / [r]eset / [q]uit: ").strip().lower()

    if action == "s":
        feature = input("  Feature name: ").strip()
        try:
            weight = float(input("  Weight value: "))
            overrides[feature] = weight
            save_user_setting("COACH_WEIGHT_OVERRIDES", overrides)
            print(f"  Set {feature} = {weight}")
        except ValueError:
            print("  Invalid weight.")

    elif action == "r":
        save_user_setting("COACH_WEIGHT_OVERRIDES", {})
        print("  All overrides reset.")

    elif action == "v":
        from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM

        print(f"  Feature vector dimension: {METADATA_DIM}")
        print(f"  Active overrides: {get_setting('COACH_WEIGHT_OVERRIDES', {})}")

    refresh_settings()


# =============================================================================
# heartbeat — System health telemetry
# =============================================================================


def cmd_heartbeat(args):
    """Display system health: daemon status, queue, matches, resources."""
    print("\n=== HEARTBEAT MONITOR ===\n")

    from sqlmodel import func, select

    from Programma_CS2_RENAN.backend.storage.database import get_db_manager
    from Programma_CS2_RENAN.backend.storage.db_models import (
        CoachState,
        IngestionTask,
        PlayerMatchStats,
    )

    db = get_db_manager()

    with db.get_session() as s:
        # Queue status
        queued = s.exec(
            select(func.count(IngestionTask.id)).where(IngestionTask.status == "queued")
        ).one()
        processing = s.exec(
            select(func.count(IngestionTask.id)).where(IngestionTask.status == "processing")
        ).one()
        completed = s.exec(
            select(func.count(IngestionTask.id)).where(IngestionTask.status == "completed")
        ).one()
        failed = s.exec(
            select(func.count(IngestionTask.id)).where(IngestionTask.status == "failed")
        ).one()

        print(f"  Ingestion Queue:")
        print(f"    Queued:     {queued}")
        print(f"    Processing: {processing}")
        print(f"    Completed:  {completed}")
        print(f"    Failed:     {failed}")

        # Match stats
        total_matches = s.exec(select(func.count(PlayerMatchStats.id))).one()
        print(f"\n  Total Match Stats: {total_matches}")

        # Coach state
        state = s.exec(select(CoachState)).first()
        if state:
            print(f"\n  Coach State:")
            print(f"    HLTV:    {state.hltv_status}")
            print(f"    Ingest:  {state.ingest_status}")
            print(f"    ML:      {state.ml_status}")
            print(f"    Matches: {state.total_matches_processed}")

    # System resources
    try:
        import psutil

        print(f"\n  System Resources:")
        print(f"    CPU:    {psutil.cpu_percent(interval=0.5)}%")
        print(f"    Memory: {psutil.virtual_memory().percent}%")
        print(f"    Disk:   {psutil.disk_usage('/').percent}%")
    except ImportError:
        print("\n  System Resources: (psutil not installed)")

    # PID check
    pid_f = SOURCE_ROOT / "hltv_sync.pid"
    if pid_f.exists():
        try:
            import psutil

            pid = int(pid_f.read_text().strip())
            print(f"\n  HLTV Daemon: PID {pid} ({'alive' if psutil.pid_exists(pid) else 'stale'})")
        except (psutil.NoSuchProcess, ProcessLookupError):
            print(f"\n  HLTV Daemon: PID file exists but process is dead (stale lock)")  # F8-35
        except Exception as e:
            print(f"\n  HLTV Daemon: could not read PID — {e}")
    else:
        print(f"\n  HLTV Daemon: not running")


# =============================================================================
# CLI
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="User Tools — Consolidated interactive utilities",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Tool to run")

    subparsers.add_parser("personalize", help="Set player name, Steam ID, API keys")
    subparsers.add_parser("customize", help="Set language, theme, font preferences")
    subparsers.add_parser("manual-entry", help="Manually enter pro player stats")
    subparsers.add_parser("weights", help="View/set ML feature weight overrides")
    subparsers.add_parser("heartbeat", help="System health telemetry")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    commands = {
        "personalize": cmd_personalize,
        "customize": cmd_customize,
        "manual-entry": cmd_manual_entry,
        "weights": cmd_weights,
        "heartbeat": cmd_heartbeat,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
