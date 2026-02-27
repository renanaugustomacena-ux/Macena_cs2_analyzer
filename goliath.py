#!/usr/bin/env python3
"""
MACENA GOLIATH - Master Authority Orchestrator (MTS-IS)
=======================================================
The unified command-line interface for the Macena CS2 Analyzer tool suite.
Integrates Build, Integrity, Database, and Diagnostic operations.

Industrial Standard Version 2.0
"""

import argparse
import logging
import os
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# --- Path Stabilization ---
# F7-12: sys.path bootstrap — acceptable for root-level CLI entry points invoked directly.
# With `pip install -e .` and `python -m` invocation this block is a no-op.
PROJECT_ROOT = Path(__file__).parent.absolute()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# --- Windows Encoding Fix ---
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# --- Rich & Logging Imports ---
try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.table import Table
    from rich.theme import Theme
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print("CRITICAL: 'rich' library not found. Please run 'pip install rich'.")
    sys.exit(1)

# --- Configuration ---
MTS_THEME = Theme(
    {
        "info": "cyan",
        "warning": "bold yellow",
        "error": "bold red",
        "success": "bold green",
        "command": "bold magenta",
        "path": "underline blue",
    }
)

console = Console(theme=MTS_THEME)
install_rich_traceback(console=console)


# --- Logging Setup ---
def setup_logging(log_dir: Path):
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"goliath_master_{datetime.now().strftime('%Y%m%d')}.json"

    # We append to a daily master log
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter(
        '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "module": "%(name)s", "message": "%(message)s"}'
    )
    file_handler.setFormatter(file_formatter)

    logger = logging.getLogger("Goliath")
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    return logger


logger = setup_logging(PROJECT_ROOT / "logs")


class GoliathOrchestrator:
    def __init__(self):
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, sig, frame):
        # F7-29: TODO — terminate any running child processes (e.g. spawned build workers)
        # before exit to prevent orphaned processes.
        console.print("\n[error]>>> Goliath Terminated by User.[/error]")
        logger.warning("Goliath session interrupted by user.")
        sys.exit(0)

    def print_header(self):
        console.print(
            Panel.fit(
                "[bold white]MACENA GOLIATH ORCHESTRATOR[/bold white]\n[dim]Industrial Tool Suite v2.0[/dim]",
                style="bold blue",
                border_style="blue",
            )
        )

    def run_build(self, test_only: bool):
        from tools.build_pipeline import IndustrialBuildPipeline

        console.print("[command]>>> Initiating Build Subsystem[/command]")
        pipeline = IndustrialBuildPipeline(test_only=test_only)
        if pipeline.execute():
            logger.info("Build completed (Test Mode: %s)", test_only)  # F7-07: %s format
        else:
            logger.error("Build failed")
            sys.exit(1)

    def run_sanitize(self, force: bool):
        from tools.Sanitize_Project import IndustrialSanitizer

        console.print("[command]>>> Initiating Sanitization Subsystem[/command]")
        sanitizer = IndustrialSanitizer(force=force)
        if sanitizer.execute():
            logger.info("Sanitization completed")
        else:
            sys.exit(1)

    def run_manifest(self):
        from tools.generate_manifest import ManifestGenerator

        console.print("[command]>>> Initiating Integrity Subsystem[/command]")
        gen = ManifestGenerator()
        if gen.generate():
            logger.info("Manifest generation completed")
        else:
            sys.exit(1)

    def run_audit(self, demo_path: Optional[str]):
        from tools.Feature_Audit import IndustrialFeatureAuditor

        console.print("[command]>>> Initiating Feature Audit Subsystem[/command]")
        auditor = IndustrialFeatureAuditor(demo_path=demo_path)
        if auditor.execute():
            logger.info("Feature audit passed")
        else:
            logger.error("Feature audit failed")
            sys.exit(1)

    def run_db(self, force: bool):
        from tools.migrate_db import IndustrialDatabaseMigrator

        console.print("[command]>>> Initiating Database Subsystem[/command]")
        migrator = IndustrialDatabaseMigrator(force=force)
        if migrator.migrate():
            logger.info("Database migration completed")
        else:
            sys.exit(1)

    def run_baseline(self):
        """Display temporal baseline status (Proposal 11)."""
        console.print("[command]>>> Initiating Baseline Subsystem[/command]")
        try:
            from sqlmodel import func, select

            from Programma_CS2_RENAN.backend.processing.baselines.pro_baseline import (
                TemporalBaselineDecay,
                get_pro_baseline,
            )
            from Programma_CS2_RENAN.backend.storage.database import get_db_manager
            from Programma_CS2_RENAN.backend.storage.db_models import ProPlayerStatCard

            decay = TemporalBaselineDecay()
            db = get_db_manager()

            with db.get_session() as session:
                card_count = session.exec(select(func.count(ProPlayerStatCard.id))).one()

            temporal = decay.get_temporal_baseline()
            legacy = get_pro_baseline()
            shifted = decay.detect_meta_shift(legacy, temporal) if temporal and legacy else []

            console.print(f"  [info]Stat Cards:[/info] {card_count}")
            console.print(f"  [info]Temporal Metrics:[/info] {len(temporal)} keys")
            console.print(f"  [info]Legacy Metrics:[/info] {len(legacy)} keys")
            console.print(f"  [info]Meta Shifts:[/info] {len(shifted)} detected")

            if shifted:
                for m in shifted:
                    console.print(f"    [warning]SHIFT: {m}[/warning]")
            else:
                console.print("    [success]No meta shifts detected[/success]")

            logger.info("Baseline check: %s cards, %s shifts", card_count, len(shifted))  # F7-07

        except Exception as e:
            console.print(f"[error]Baseline check failed:[/error] {e}")
            logger.error("Baseline check failed: %s", e)  # F7-07

    def run_hospital(self, department: Optional[str]):
        # The Hospital is complex and internal, we wrap it simply
        console.print("[command]>>> Paging Dr. Goliath...[/command]")
        try:
            from Programma_CS2_RENAN.tools.Goliath_Hospital import Department, GoliathHospital

            target = PROJECT_ROOT / "Programma_CS2_RENAN"
            hospital = GoliathHospital(target_dir=target, verbose=True)

            if department:
                dept_key = department.upper()
                if dept_key in Department.__members__:
                    dept_enum = Department[dept_key]
                    console.print(f"[info]Examining Department: {dept_enum.value}[/info]")
                    # Map enum members to methods manually if needed, or rely on hospital logic
                    # For now, let's just trigger full diagnostic if specific dept dispatch is complex
                    # or map what we know from the old script:
                    dept_map = {
                        "ER": hospital._run_emergency_room,
                        "RADIOLOGY": hospital._run_radiology,
                        "PATHOLOGY": hospital._run_pathology,
                        "CARDIOLOGY": hospital._run_cardiology,
                        "NEUROLOGY": hospital._run_neurology,
                        "ONCOLOGY": hospital._run_oncology,
                        "PEDIATRICS": hospital._run_pediatrics,
                        "ICU": hospital._run_icu,
                        "PHARMACY": hospital._run_pharmacy,
                        "TOOL_CLINIC": hospital._run_tool_clinic,
                    }
                    # F7-34: dept_map does not include all Department enum values. Unmapped
                    # departments fall through to full diagnostic. Add assertion coverage when
                    # new departments are added: assert set(Department) == set(dept_map.keys())
                    if dept_key in dept_map:
                        dept_map[dept_key]()
                    else:
                        console.print(
                            f"[warning]Department {dept_key} logic not mapped. Running full scan.[/warning]"
                        )
                        hospital.run_full_diagnostic()
                else:
                    console.print(f"[error]Unknown department: {department}[/error]")
            else:
                hospital.run_full_diagnostic()

        except ImportError as e:
            console.print(f"[error]Hospital unavailable:[/error] {e}")


def main():
    parser = argparse.ArgumentParser(prog="goliath", description="Macena Master Authority (MTS-IS)")
    subparsers = parser.add_subparsers(dest="command", help="Operational Subsystem")

    # Build
    build_parser = subparsers.add_parser("build", help="Execute the Industrial Build Pipeline")
    build_parser.add_argument(
        "--test-only", action="store_true", help="Run tests without compilation"
    )

    # Sanitize
    clean_parser = subparsers.add_parser("sanitize", help="Clean project for distribution")
    clean_parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")

    # Integrity
    subparsers.add_parser("integrity", help="Generate source code integrity manifest")

    # Audit
    audit_parser = subparsers.add_parser("audit", help="Verify Data & Features")
    audit_parser.add_argument("--demo", type=str, help="Real .dem file for live audit")

    # Database
    db_parser = subparsers.add_parser("db", help="Manage Database Schema")
    db_parser.add_argument("-y", "--yes", action="store_true", help="Force migration")

    # Hospital
    doctor_parser = subparsers.add_parser("doctor", help="Run Clinical Diagnostics")
    doctor_parser.add_argument(
        "--dept", "-d", type=str, help="Specific department (e.g. ER, NEUROLOGY)"
    )

    # Baseline
    subparsers.add_parser("baseline", help="Show Temporal Baseline Decay status")

    args = parser.parse_args()

    goliath = GoliathOrchestrator()
    goliath.print_header()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    try:
        if args.command == "build":
            goliath.run_build(test_only=args.test_only)
        elif args.command == "sanitize":
            goliath.run_sanitize(force=args.yes)
        elif args.command == "integrity":
            goliath.run_manifest()
        elif args.command == "audit":
            goliath.run_audit(demo_path=args.demo)
        elif args.command == "db":
            goliath.run_db(force=args.yes)
        elif args.command == "doctor":
            goliath.run_hospital(department=args.dept)
        elif args.command == "baseline":
            goliath.run_baseline()

    except Exception as e:
        console.print_exception()
        logger.critical("Unhandled exception in %s: %s", args.command, e)  # F7-07
        sys.exit(1)


if __name__ == "__main__":
    main()
