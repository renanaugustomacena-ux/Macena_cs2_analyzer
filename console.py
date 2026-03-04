#!/usr/bin/env python3
"""
MACENA UNIFIED CONSOLE v3.0
============================
The single entry point for the Macena CS2 Analyzer.
Controls all tools, tests, ingestion, training, and diagnostics.

Usage:
  Interactive TUI:  python console.py
  CLI mode:         python console.py <command> [args]

If it's not in this console, the project doesn't need it.
"""

import argparse
import logging
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

if sys.platform == "win32":
    import msvcrt

    _unix_input = False
else:
    msvcrt = None
    _unix_input = True
    import select as _select_mod
    import termios
    import tty

# --- Path Stabilization ---
# F7-12: sys.path bootstrap — acceptable for root-level CLI entry points invoked directly.
# With `pip install -e .` and `python -m` invocation this block is a no-op.
PROJECT_ROOT = Path(__file__).parent.absolute()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["KIVY_NO_ARGS"] = "1"
os.environ["KIVY_NO_CONSOLELOG"] = "1"

# --- Windows Encoding Fix ---
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# --- Rich Imports ---
try:
    from rich import box
    from rich.console import Console as RichConsole
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.progress_bar import ProgressBar
    from rich.table import Table
    from rich.text import Text
    from rich.theme import Theme
    from rich.traceback import install as install_rich_traceback
except ImportError:
    print("CRITICAL: 'rich' library not found. Run: pip install rich")
    sys.exit(1)

# --- Theme ---
THEME = Theme(
    {
        "info": "cyan",
        "warning": "bold yellow",
        "error": "bold red",
        "success": "bold green",
        "brain": "bold magenta",
        "digester": "bold cyan",
        "archive": "bold yellow",
        "path": "underline blue",
        "dim": "dim white",
    }
)

rich_con = RichConsole(theme=THEME)
install_rich_traceback(console=rich_con)

# --- Console Constants ---
TUI_REFRESH_PER_SECOND = 8
TUI_INPUT_POLL_INTERVAL_S = 0.10
OUTPUT_TRIM_MAX_LINES = 80
SUBPROCESS_DEFAULT_TIMEOUT_S = 120
SUBPROCESS_BUILD_TIMEOUT_S = 600
DEAD_CODE_DETECTOR_TIMEOUT_S = 220

# --- Logging ---
_log_dir = PROJECT_ROOT / "logs"
_log_dir.mkdir(parents=True, exist_ok=True)
_log_file = _log_dir / f"console_{datetime.now().strftime('%Y%m%d')}.json"
_fh = logging.FileHandler(_log_file, encoding="utf-8")
_fh.setLevel(logging.INFO)
_fh.setFormatter(
    logging.Formatter(
        '{"ts":"%(asctime)s","lvl":"%(levelname)s","mod":"%(name)s","msg":"%(message)s"}'
    )
)
logger = logging.getLogger("MacenaConsole")
logger.setLevel(logging.INFO)
logger.addHandler(_fh)

# ============================================================================
#  COMMAND REGISTRY
# ============================================================================


class Command:
    __slots__ = ("handler", "help_text", "category")

    def __init__(self, handler: Callable, help_text: str, category: str):
        self.handler = handler
        self.help_text = help_text
        self.category = category


class CommandRegistry:
    def __init__(self):
        self._commands: Dict[str, Dict[str, Command]] = {}

    def register(self, category: str, name: str, handler: Callable, help_text: str):
        if category not in self._commands:
            self._commands[category] = {}
        self._commands[category][name] = Command(handler, help_text, category)

    def dispatch(self, category: str, subcmd: str, args: List[str]) -> str:
        cat = self._commands.get(category)
        if not cat:
            return f"[error]Unknown category: {category}[/error]"
        cmd = cat.get(subcmd)
        if not cmd:
            return f"[error]Unknown command: {category} {subcmd}[/error]\n" + self.get_help(
                category
            )
        try:
            return cmd.handler(args)
        except Exception as e:
            logger.exception(f"Command {category} {subcmd} failed: {e}")
            return f"[error]Error: {e}[/error]"

    def dispatch_interactive(self, cmd_line: str) -> str:
        parts = cmd_line.strip().split()
        if not parts:
            return ""
        category = parts[0].lower()
        subcmd = parts[1].lower() if len(parts) > 1 else ""
        args = parts[2:] if len(parts) > 2 else []

        # Single-word commands (exit, help)
        if category in self._commands and "" in self._commands[category]:
            if not subcmd:
                return self._commands[category][""].handler(args)
            # If subcmd exists as a registered command, dispatch normally
            if subcmd in self._commands.get(category, {}):
                return self.dispatch(category, subcmd, args)
            # Otherwise pass subcmd as first arg to the default handler
            return self._commands[category][""].handler([subcmd] + args)

        if not subcmd:
            return self.get_help(category)
        return self.dispatch(category, subcmd, args)

    def get_help(self, category: str = None) -> str:
        if category and category in self._commands:
            lines = [f"[bold]{category.upper()} Commands:[/bold]"]
            for name, cmd in self._commands[category].items():
                label = f"{category} {name}" if name else category
                lines.append(f"  [info]{label:30s}[/info] {cmd.help_text}")
            return "\n".join(lines)

        lines = [
            "[bold white]MACENA CS2 ANALYZER — UNIFIED CONSOLE v3.0[/bold white]\n",
        ]
        for cat_name, cmds in self._commands.items():
            first = next(iter(cmds.values()))
            summary = first.help_text if len(cmds) == 1 else f"{len(cmds)} sub-commands"
            lines.append(f"  [info]{cat_name:12s}[/info] {summary}")
        lines.append("\n  Type [bold]help <category>[/bold] for details.")
        return "\n".join(lines)


# ============================================================================
#  BACKEND LAZY LOADER (avoid import-time side effects)
# ============================================================================

_sys_console = None


def _get_sys_console():
    global _sys_console
    if _sys_console is None:
        from Programma_CS2_RENAN.backend.control.console import get_console

        _sys_console = get_console()
    return _sys_console


# ============================================================================
#  SUBPROCESS RUNNER
# ============================================================================


def _run_tool(cmd: List[str], timeout: int = 120) -> Tuple[int, str]:
    """Run a subprocess and return (exit_code, output_snippet)."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    try:
        result = subprocess.run(
            cmd, cwd=str(PROJECT_ROOT), env=env, capture_output=True, text=True, timeout=timeout
        )
        output = result.stdout + result.stderr
        # Trim to last N lines for display
        lines = output.strip().splitlines()
        if len(lines) > OUTPUT_TRIM_MAX_LINES:
            output = "\n".join(lines[-OUTPUT_TRIM_MAX_LINES:])
        else:
            output = "\n".join(lines)
        return result.returncode, output
    except subprocess.TimeoutExpired:
        return 1, f"[error]Timeout after {timeout}s[/error]"
    except Exception as e:
        return 1, f"[error]{e}[/error]"


def _run_tool_live(cmd: List[str], timeout: int = 600) -> str:
    """Run a subprocess with live output streaming to console."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in proc.stdout:
            rich_con.print(line.rstrip())
        proc.wait(timeout=timeout)
        status = "[success]PASS[/success]" if proc.returncode == 0 else "[error]FAIL[/error]"
        return f"{status} (exit code {proc.returncode})"
    except subprocess.TimeoutExpired:
        proc.kill()
        return f"[error]Timeout after {timeout}s[/error]"
    except Exception as e:
        return f"[error]{e}[/error]"


# ============================================================================
#  COMMAND HANDLERS
# ============================================================================


# --- ML ---
def _cmd_ml_start(args):
    sc = _get_sys_console()
    sc.start_training()
    status = sc.ml_controller.get_status()
    if status.get("is_running"):
        return "[success]ML training engaged.[/success]"
    return "[warning]ML training start requested but not confirmed running.[/warning]"


def _cmd_ml_stop(args):
    sc = _get_sys_console()
    status = sc.ml_controller.get_status()
    if not status.get("is_running"):
        return "[warning]ML training is not currently running.[/warning]"
    sc.stop_training()
    return "[warning]ML stop requested (will halt at next checkpoint).[/warning]"


def _cmd_ml_pause(args):
    sc = _get_sys_console()
    status = sc.ml_controller.get_status()
    if not status.get("is_running"):
        return "[warning]ML training is not currently running.[/warning]"
    if status.get("paused"):
        return "[warning]ML training is already paused.[/warning]"
    sc.pause_training()
    return "[warning]ML paused.[/warning]"


def _cmd_ml_resume(args):
    sc = _get_sys_console()
    status = sc.ml_controller.get_status()
    if not status.get("paused"):
        return "[warning]ML training is not paused.[/warning]"
    sc.resume_training()
    return "[success]ML resumed.[/success]"


def _cmd_ml_throttle(args):
    if not args:
        return "[error]Usage: ml throttle [0.0-1.0][/error]"
    try:
        val = float(args[0])
        if not 0.0 <= val <= 1.0:
            return "[error]Throttle must be between 0.0 and 1.0[/error]"
        sc = _get_sys_console()
        sc.ml_controller.context.set_throttle(val)
        return f"[success]Throttle set to {val} ({'full speed' if val == 0 else f'{val*100:.0f}% delay'})[/success]"
    except ValueError:
        return "[error]Invalid number. Usage: ml throttle 0.5[/error]"


def _cmd_ml_status(args):
    sc = _get_sys_console()
    ml = sc.ml_controller.get_status()
    from Programma_CS2_RENAN.backend.storage.state_manager import state_manager

    teacher = state_manager.get_status("teacher")
    lines = [
        "[bold]ML Pipeline Status[/bold]",
        f"  Running:    {'[success]Yes[/success]' if ml['is_running'] else '[dim]No[/dim]'}",
        f"  Paused:     {'[warning]Yes[/warning]' if ml['paused'] else '[dim]No[/dim]'}",
        f"  Stop Req:   {'[error]Yes[/error]' if ml['stop_requested'] else '[dim]No[/dim]'}",
        f"  Throttle:   {sc.ml_controller.context._throttle_factor:.1f}",
        f"  Teacher:    {teacher.get('status', 'N/A')}",
        f"  Detail:     {teacher.get('detail', 'N/A')}",
    ]
    return "\n".join(lines)


# --- INGEST ---
def _cmd_ingest_start(args):
    sc = _get_sys_console()
    priority = "--priority" in args or "-p" in args
    sc.ingest_manager.scan_all(high_priority=priority)
    mode = "HIGH PRIORITY" if priority else "normal"
    status = sc.ingest_manager.get_status()
    if status.get("is_running"):
        return f"[success]Ingestion started ({mode}).[/success]"
    return f"[warning]Ingestion start requested ({mode}) but not confirmed running.[/warning]"


def _cmd_ingest_stop(args):
    sc = _get_sys_console()
    status = sc.ingest_manager.get_status()
    if not status.get("is_running"):
        return "[warning]Ingestion is not currently running.[/warning]"
    sc.ingest_manager.stop()
    return "[warning]Ingestion stop requested.[/warning]"


def _cmd_ingest_mode(args):
    if not args:
        return "[error]Usage: ingest mode [single|continuous|timed] [interval_minutes][/error]"
    from Programma_CS2_RENAN.backend.control.ingest_manager import IngestMode

    mode_str = args[0].lower()
    mode_map = {
        "single": IngestMode.SINGLE,
        "continuous": IngestMode.CONTINUOUS,
        "timed": IngestMode.TIMED,
    }
    if mode_str not in mode_map:
        return f"[error]Unknown mode: {mode_str}. Use single/continuous/timed[/error]"
    try:
        interval = int(args[1]) if len(args) > 1 else 30
    except ValueError:
        return f"[error]Interval must be a number, got: '{args[1]}'[/error]"
    sc = _get_sys_console()
    sc.ingest_manager.set_mode(mode_map[mode_str], interval)
    return f"[success]Ingestion mode: {mode_str.upper()}, interval: {interval}m[/success]"


def _cmd_ingest_status(args):
    sc = _get_sys_console()
    st = sc.ingest_manager.get_status()
    lines = [
        "[bold]Ingestion Status[/bold]",
        f"  Running:  {'[success]Yes[/success]' if st['is_running'] else '[dim]No[/dim]'}",
        f"  Phase:    {st.get('phase', 'idle')}",
        f"  Mode:     {st['mode'].upper()}",
        f"  Found:    {st.get('total_found', 0)} demos",
        f"  Queued:   {st['queued']}",
        f"  Active:   {st['processing']}",
        f"  Failed:   {st['failed']}",
        f"  Current:  {st['current_file']}",
        f"  Interval: {st['interval']}m",
    ]
    return "\n".join(lines)


def _cmd_ingest_scan(args):
    """Dry-run: scan for new demos without processing them."""
    sc = _get_sys_console()
    storage = sc.ingest_manager.storage
    lines = [
        "[bold]Scan Configuration:[/bold]",
        f"  User demos: [path]{storage.ingest_dir}[/path]"
        + (
            " [success]\u2713[/]"
            if storage.ingest_dir.exists()
            else " [error]NOT FOUND[/]"
        ),
        f"  Pro demos:  [path]{storage.pro_ingest_dir}[/path]"
        + (
            " [success]\u2713[/]"
            if storage.pro_ingest_dir.exists()
            else " [error]NOT FOUND[/]"
        ),
    ]
    user_demos = storage.list_new_demos(is_pro=False)
    pro_demos = storage.list_new_demos(is_pro=True)
    lines.append(
        f"\n[success]Found {len(user_demos)} user + {len(pro_demos)} pro new demos[/success]"
    )
    if user_demos:
        lines.append(
            f"  [dim]User: {', '.join(d.name for d in user_demos[:5])}{'...' if len(user_demos) > 5 else ''}[/dim]"
        )
    if pro_demos:
        lines.append(
            f"  [dim]Pro:  {', '.join(d.name for d in pro_demos[:5])}{'...' if len(pro_demos) > 5 else ''}[/dim]"
        )
    if not user_demos and not pro_demos:
        lines.append(
            "\n[warning]No new demos found. Use 'set pro-path' or 'set demo-path' to configure paths.[/warning]"
        )
    return "\n".join(lines)


# --- BUILD ---
def _cmd_build_run(args):
    test_only = "--test-only" in args
    flag = " --test-only" if test_only else ""
    rich_con.print(f"[info]>>> Build Pipeline{' (test-only)' if test_only else ''}[/info]")
    return _run_tool_live(
        [sys.executable, "tools/build_pipeline.py"] + (["--test-only"] if test_only else []),
        timeout=600,
    )


def _cmd_build_verify(args):
    rich_con.print("[info]>>> Post-Build Integrity Verification[/info]")
    return _run_tool_live(
        [sys.executable, "Programma_CS2_RENAN/tools/build_tools.py", "verify"], timeout=120
    )


def _cmd_build_manifest(args):
    rich_con.print("[info]>>> Generating Integrity Manifest[/info]")
    return _run_tool_live([sys.executable, "tools/generate_manifest.py"], timeout=120)


# --- TEST ---
def _cmd_test_all(args):
    rich_con.print("[info]>>> Running full pytest suite[/info]")
    return _run_tool_live(
        [sys.executable, "-m", "pytest", "Programma_CS2_RENAN/tests/", "-x", "-q"], timeout=300
    )


def _cmd_test_headless(args):
    rich_con.print("[info]>>> Running headless validator[/info]")
    return _run_tool_live([sys.executable, "tools/headless_validator.py"], timeout=60)


def _cmd_test_backend(args):
    rich_con.print("[info]>>> Running backend validator[/info]")
    return _run_tool_live(
        [sys.executable, "Programma_CS2_RENAN/tools/backend_validator.py"], timeout=120
    )


def _cmd_test_ui(args):
    rich_con.print("[info]>>> Running UI diagnostic[/info]")
    return _run_tool_live(
        [sys.executable, "Programma_CS2_RENAN/tools/ui_diagnostic.py"], timeout=120
    )


def _cmd_test_hospital(args):
    dept_args = []
    if args:
        dept_args = ["--dept", args[0].upper()]
    rich_con.print(
        f"[info]>>> Goliath Hospital{' (' + args[0].upper() + ')' if args else ''}[/info]"
    )
    return _run_tool_live(
        [sys.executable, "Programma_CS2_RENAN/tools/Goliath_Hospital.py"] + dept_args, timeout=120
    )


def _cmd_test_suite(args):
    """Run ALL validation tools sequentially."""
    rich_con.print("[info]>>> Running full validation suite[/info]")
    results = []
    for name, cmd in [
        ("Headless", [sys.executable, "tools/headless_validator.py"]),
        ("Pytest", [sys.executable, "-m", "pytest", "Programma_CS2_RENAN/tests/", "-x", "-q"]),
        ("Backend", [sys.executable, "Programma_CS2_RENAN/tools/backend_validator.py"]),
        ("Hospital", [sys.executable, "Programma_CS2_RENAN/tools/Goliath_Hospital.py"]),
    ]:
        rich_con.print(f"\n[bold]--- {name} ---[/bold]")
        code, output = _run_tool(cmd, timeout=300)
        status = "[success]PASS[/success]" if code == 0 else "[error]FAIL[/error]"
        results.append(f"  {name:12s} {status}")
        if code != 0:
            # Print last few lines on failure
            for line in output.splitlines()[-10:]:
                rich_con.print(f"  {line}")
    return "[bold]Validation Suite Results:[/bold]\n" + "\n".join(results)


# --- SYS ---
def _cmd_sys_status(args):
    sc = _get_sys_console()
    status = sc.get_system_status()
    lines = [
        "[bold]System Status[/bold]",
        f"  State:      {status['state']}",
        f"  Timestamp:  {status['timestamp']}",
    ]
    # Services
    for name, svc in status.get("services", {}).items():
        lines.append(f"  Service [{name}]: {svc['status']} (PID: {svc.get('pid', '-')})")
    # Baseline
    bl = status.get("baseline", {})
    lines.append(f"  Baseline:   {bl.get('mode', '?')} ({bl.get('stat_cards', 0)} cards)")
    return "\n".join(lines)


def _cmd_sys_audit(args):
    rich_con.print("[info]>>> Feature Audit[/info]")
    try:
        from tools.Feature_Audit import IndustrialFeatureAuditor

        auditor = IndustrialFeatureAuditor(demo_path=args[0] if args else None)
        result = auditor.execute()
        if result and hasattr(result, "critical_count") and result.critical_count > 0:
            return f"[warning]Audit complete with {result.critical_count} critical finding(s).[/warning]"
        return "[success]Audit complete — no critical issues.[/success]"
    except Exception as e:
        return f"[error]Audit failed: {e}[/error]"


def _cmd_sys_baseline(args):
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
            min_date = session.exec(select(func.min(ProPlayerStatCard.last_updated))).one()
            max_date = session.exec(select(func.max(ProPlayerStatCard.last_updated))).one()

        temporal = decay.get_temporal_baseline()
        legacy = get_pro_baseline()
        shifted = decay.detect_meta_shift(legacy, temporal) if temporal and legacy else []

        tbl = Table(title="Baseline Status", expand=True, box=box.SIMPLE)
        tbl.add_column("Metric", style="cyan")
        tbl.add_column("Legacy", justify="right")
        tbl.add_column("Temporal", justify="right")
        tbl.add_column("Delta", justify="right")

        for key in sorted(k for k in list(legacy.keys())[:12] if not k.startswith("_"))[:8]:
            l_val = legacy.get(key, {})
            t_val = temporal.get(key, {})
            l_mean = l_val.get("mean", 0) if isinstance(l_val, dict) else l_val
            t_mean = t_val.get("mean", 0) if isinstance(t_val, dict) else t_val
            delta = t_mean - l_mean
            style = "success" if abs(delta) < 0.05 else "warning"
            tbl.add_row(key, f"{l_mean:.3f}", f"{t_mean:.3f}", f"[{style}]{delta:+.3f}[/]")

        rich_con.print(tbl)
        rich_con.print(f"\n  Stat Cards:  {card_count}")
        rich_con.print(f"  Date Range:  {min_date or 'N/A'} -> {max_date or 'N/A'}")
        rich_con.print(f"  Meta Shifts: {len(shifted)} detected")
        if shifted:
            rich_con.print(f"  Shifted:     {', '.join(shifted)}")
        return f"[success]Baseline check complete ({card_count} cards)[/success]"
    except Exception as e:
        logger.error("sys baseline check failed: %s", e, exc_info=True)
        return f"[error]Baseline check failed: {e}[/error]"


def _cmd_sys_db(args):
    force = "-y" in args or "--yes" in args
    rich_con.print("[info]>>> Database Migration[/info]")
    try:
        from tools.migrate_db import IndustrialDatabaseMigrator

        migrator = IndustrialDatabaseMigrator(force=force)
        result = migrator.migrate()
        if result is False:
            return "[warning]Migration reported issues — check output above.[/warning]"
        return "[success]Migration complete.[/success]"
    except Exception as e:
        return f"[error]Migration failed: {e}[/error]"


def _cmd_sys_vacuum(args):
    from Programma_CS2_RENAN.core.config import DATABASE_URL

    db_path = DATABASE_URL.replace("sqlite:///", "")
    if not os.path.exists(db_path):
        return f"[error]Database not found at: {db_path}[/error]"
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute("VACUUM")
        logger.info("sys vacuum: Database vacuumed successfully at %s", db_path)
        return "[success]Database vacuumed.[/success]"
    except sqlite3.OperationalError as e:
        logger.error("sys vacuum failed: %s", e)
        return f"[error]VACUUM failed (DB may be locked): {e}[/error]"


def _cmd_sys_resources(args):
    import psutil

    proc = psutil.Process()
    mem = proc.memory_info()
    cpu_sys = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()
    lines = [
        "[bold]System Resources[/bold]",
        f"  CPU (system):   {cpu_sys:.1f}%",
        f"  RAM (process):  {mem.rss / 1024 / 1024:.1f} MB",
        f"  RAM (system):   {ram.used / 1024 / 1024:.0f} / {ram.total / 1024 / 1024:.0f} MB ({ram.percent}%)",
    ]
    return "\n".join(lines)


# --- SET ---
# SECURITY WARNING (F7-01): API keys are stored in plaintext in settings.json.
# For production use, migrate to the OS credential store via the keyring library:
#   import keyring; keyring.set_password("cs2analyzer", "STEAM_API_KEY", api_key)
# Until keyring integration is implemented, ensure settings.json has filesystem
# permissions restricted to the current user (chmod 600 on Linux/macOS).
def _cmd_set_steam(args):
    if len(args) < 1:
        return "[error]Usage: set steam <KEY>[/error]"
    from Programma_CS2_RENAN.core.config import save_user_setting

    save_user_setting("STEAM_API_KEY", args[0])
    return "[success]Steam API key updated.[/success]"


# SECURITY WARNING (F7-01): same as above — FACEIT_API_KEY stored in plaintext.
def _cmd_set_faceit(args):
    if len(args) < 1:
        return "[error]Usage: set faceit <KEY>[/error]"
    from Programma_CS2_RENAN.core.config import save_user_setting

    save_user_setting("FACEIT_API_KEY", args[0])
    return "[success]Faceit API key updated.[/success]"


_ALLOWED_CONFIG_KEYS = {
    "PLAYER_NAME", "STEAM_ID", "STEAM_API_KEY", "FACEIT_API_KEY",
    "DEFAULT_DEMO_PATH", "PRO_DEMO_PATH", "ACTIVE_THEME", "FONT_SIZE",
    "FONT_TYPE", "LANGUAGE", "BACKGROUND_IMAGE", "ENABLE_SLIDESHOW",
    "BRAIN_DATA_ROOT", "SETUP_COMPLETED", "COACH_WEIGHT_OVERRIDES",
    "CS2_PLAYER_NAME",
}


def _cmd_set_config(args):
    if len(args) < 2:
        return "[error]Usage: set config <key> <value>[/error]"
    if args[0] not in _ALLOWED_CONFIG_KEYS:
        return f"[error]Unknown config key: {args[0]}. Allowed: {', '.join(sorted(_ALLOWED_CONFIG_KEYS))}[/error]"
    from Programma_CS2_RENAN.core.config import save_user_setting

    save_user_setting(args[0], args[1])
    return f"[success]Config {args[0]} = {args[1]}[/success]"


def _cmd_set_view(args):
    from Programma_CS2_RENAN.core.config import get_all_settings

    settings = get_all_settings()
    lines = ["[bold]Current Configuration[/bold]"]
    if isinstance(settings, dict):
        for k, v in settings.items():
            # Mask API keys
            # F7-30: Showing last 4 chars of key is accepted practice. Acceptable until keyring is integrated.
            display = "****" + str(v)[-4:] if "KEY" in k.upper() and v else str(v)
            lines.append(f"  {k:30s} = {display}")
    else:
        lines.append(f"  {settings}")
    return "\n".join(lines)


def _cmd_set_demo_path(args):
    if not args:
        return "[error]Usage: set demo-path <path>[/error]"
    path = " ".join(args)
    if not os.path.isdir(path):
        return f"[error]Path does not exist: {path}[/error]"
    from Programma_CS2_RENAN.core.config import save_user_setting

    save_user_setting("DEFAULT_DEMO_PATH", path)
    return f"[success]User demo path \u2192 {path}[/success]"


def _cmd_set_pro_path(args):
    if not args:
        return "[error]Usage: set pro-path <path>[/error]"
    path = " ".join(args)
    if not os.path.isdir(path):
        return f"[error]Path does not exist: {path}[/error]"
    from Programma_CS2_RENAN.core.config import save_user_setting

    save_user_setting("PRO_DEMO_PATH", path)
    return f"[success]Pro demo path \u2192 {path}[/success]"


# --- SVC ---
def _cmd_svc_restart(args):
    if not args:
        return "[error]Usage: svc restart <service_name>[/error]"
    sc = _get_sys_console()
    name = args[0]
    try:
        sc.supervisor.stop_service(name)
        time.sleep(1)
        sc.supervisor.start_service(name)
        time.sleep(0.5)
        svcs = sc.supervisor.get_status()
        svc_info = svcs.get(name, {})
        if svc_info.get("status") == "running":
            return f"[success]Service '{name}' restarted and confirmed running.[/success]"
        return f"[warning]Service '{name}' restart requested but status is: {svc_info.get('status', 'unknown')}[/warning]"
    except Exception as e:
        return f"[error]Restart failed: {e}[/error]"


def _cmd_svc_kill_all(args):
    sc = _get_sys_console()
    names = list(sc.supervisor.services.keys())
    for name in names:
        sc.supervisor.stop_service(name)
    time.sleep(0.5)
    svcs = sc.supervisor.get_status()
    still_running = [n for n, info in svcs.items() if info.get("status") == "running"]
    if still_running:
        return f"[warning]Kill-all issued but still running: {', '.join(still_running)}[/warning]"
    return f"[success]All {len(names)} managed services terminated.[/success]"


def _cmd_svc_spawn(args):
    if not args:
        return "[error]Usage: svc spawn <script_name>[/error]"
    # Search order: root tools/ first, then Programma_CS2_RENAN/tools/
    tool_path = PROJECT_ROOT / "tools" / args[0]
    if not tool_path.exists():
        tool_path = PROJECT_ROOT / "Programma_CS2_RENAN" / "tools" / args[0]
    if not tool_path.exists():
        return f"[error]Tool not found: {args[0]}[/error]"
    try:
        spawn_log = (
            _log_dir / f"spawn_{args[0].replace('.py', '')}_{datetime.now().strftime('%H%M%S')}.log"
        )
        stderr_file = open(spawn_log, "w", encoding="utf-8")
        # F7-10: stderr_file intentionally not closed here — the spawned subprocess owns the
        # handle and will use it beyond this function's scope. The OS closes it on process exit.
        # Do NOT add finally: stderr_file.close() here.
        subprocess.Popen(
            [sys.executable, str(tool_path)],
            cwd=str(PROJECT_ROOT),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            stdout=subprocess.DEVNULL,
            stderr=stderr_file,
        )
        return f"[success]Spawned '{args[0]}' in background. Errors logged to {spawn_log.name}[/success]"
    except Exception as e:
        return f"[error]Spawn failed: {e}[/error]"


def _cmd_svc_status(args):
    sc = _get_sys_console()
    svcs = sc.supervisor.get_status()
    lines = ["[bold]Service Status[/bold]"]
    for name, info in svcs.items():
        color = (
            "success"
            if info["status"] == "running"
            else ("error" if info["status"] == "crashed" else "dim")
        )
        lines.append(f"  [{color}]{name:15s} {info['status']:10s}[/] PID: {info.get('pid', '-')}")
    return "\n".join(lines)


# --- MAINT ---
def _cmd_maint_clear_cache(args):
    # F7-32: No dry-run flag. Safe operation (caches regenerate), but consider adding
    # --dry-run flag for user confidence before deleting many directories.
    count = 0
    for root, dirs, _ in os.walk(PROJECT_ROOT):
        for d in ("__pycache__", ".pytest_cache"):
            if d in dirs:
                shutil.rmtree(os.path.join(root, d))
                count += 1
    return f"[success]Cache cleared ({count} dirs removed).[/success]"


def _cmd_maint_clear_queue(args):
    from sqlmodel import delete, func, select

    from Programma_CS2_RENAN.backend.storage.database import get_db_manager
    from Programma_CS2_RENAN.backend.storage.db_models import IngestionTask

    db = get_db_manager()
    with db.get_session() as session:
        count = session.exec(
            select(func.count(IngestionTask.id)).where(IngestionTask.status == "queued")
        ).one()
        if count == 0:
            return "[warning]No queued tasks to purge.[/warning]"
        session.exec(delete(IngestionTask).where(IngestionTask.status == "queued"))
    return f"[success]Ingestion queue purged ({count} task(s) removed).[/success]"


def _cmd_maint_sanitize(args):
    force = "-y" in args or "--yes" in args
    rich_con.print("[info]>>> Project Sanitization[/info]")
    try:
        from tools.Sanitize_Project import IndustrialSanitizer

        sanitizer = IndustrialSanitizer(force=force)
        result = sanitizer.execute()
        if result is False:
            return "[warning]Sanitization completed with warnings — check output above.[/warning]"
        return "[success]Sanitization complete.[/success]"
    except Exception as e:
        return f"[error]Sanitization failed: {e}[/error]"


def _cmd_maint_dead_code(args):
    rich_con.print("[info]>>> Dead Code Detection[/info]")
    return _run_tool_live(
        [sys.executable, "tools/dead_code_detector.py"], timeout=DEAD_CODE_DETECTOR_TIMEOUT_S
    )


def _cmd_maint_prune(args):
    if not args:
        return "[error]Usage: maint prune <match_id>[/error]"
    try:
        match_id = int(args[0])
        sc = _get_sys_console()
        ok = sc.db_governor.prune_match_data(match_id)
        return (
            f"[success]Match {match_id} pruned.[/success]"
            if ok
            else f"[error]Prune failed for match {match_id}[/error]"
        )
    except ValueError:
        return "[error]match_id must be an integer[/error]"


# --- TOOL ---
def _cmd_tool_demo(args):
    sub = args[0] if args else "all"
    extra = list(args[1:]) if len(args) > 1 else []
    # If no --demo flag provided, pass PRO_DEMO_PATH as default search directory
    if "--demo" not in extra:
        try:
            from Programma_CS2_RENAN.core.config import PRO_DEMO_PATH

            if PRO_DEMO_PATH and os.path.isdir(PRO_DEMO_PATH):
                extra.extend(["--demo", PRO_DEMO_PATH])
        except ImportError:
            pass
    rich_con.print(f"[info]>>> Demo Inspector ({sub})[/info]")
    return _run_tool_live(
        [sys.executable, "Programma_CS2_RENAN/tools/demo_inspector.py", sub] + extra, timeout=120
    )


def _cmd_tool_user(args):
    """Show user profile info (read-only, no interactive input)."""
    from Programma_CS2_RENAN.core.config import get_all_settings

    settings = get_all_settings()
    lines = [
        "[bold]User Profile[/bold]",
        f"  Player:    {settings.get('CS2_PLAYER_NAME', 'Not set')}",
        f"  Steam ID:  {settings.get('STEAM_ID', 'Not set')}",
        f"  Demo Path: [path]{settings.get('DEFAULT_DEMO_PATH', 'Not set')}[/path]",
        f"  Pro Path:  [path]{settings.get('PRO_DEMO_PATH', 'Not set')}[/path]",
        f"  Brain Root:[path]{settings.get('BRAIN_DATA_ROOT', 'Not set')}[/path]",
        f"  Language:  {settings.get('LANGUAGE', 'en')}",
        f"  Theme:     {settings.get('ACTIVE_THEME', 'CS2')}",
        f"  Setup:     {'[success]Complete[/success]' if settings.get('SETUP_COMPLETED') else '[warning]Incomplete[/warning]'}",
    ]
    return "\n".join(lines)


def _cmd_tool_logs(args):
    log_dir = PROJECT_ROOT / "logs"
    log_files = sorted(log_dir.glob("*.json"), key=os.path.getmtime, reverse=True)
    if not log_files:
        return "[dim]No log files found.[/dim]"
    lines = [f"[bold]Latest log: {log_files[0].name}[/bold]", ""]
    with open(log_files[0], "r", encoding="utf-8") as f:
        for line in f.readlines()[-20:]:
            lines.append(line.strip())
    return "\n".join(lines)


def _cmd_tool_list(args):
    return registry.get_help("tool")


# --- HELP ---
def _cmd_help(args):
    return registry.get_help(args[0] if args else None)


# --- EXIT (only used in TUI mode) ---
def _cmd_exit(args):
    return "__EXIT__"


# ============================================================================
#  REGISTER ALL COMMANDS
# ============================================================================

registry = CommandRegistry()

# ML
registry.register("ml", "start", _cmd_ml_start, "Start full training cycle")
registry.register("ml", "stop", _cmd_ml_stop, "Graceful stop at next checkpoint")
registry.register("ml", "pause", _cmd_ml_pause, "Pause training (resumable)")
registry.register("ml", "resume", _cmd_ml_resume, "Resume from pause")
registry.register("ml", "throttle", _cmd_ml_throttle, "Set training delay [0.0-1.0]")
registry.register("ml", "status", _cmd_ml_status, "Detailed ML pipeline status")

# Ingest
registry.register("ingest", "start", _cmd_ingest_start, "Start ingestion scan [--priority]")
registry.register("ingest", "stop", _cmd_ingest_stop, "Stop ingestion")
registry.register(
    "ingest", "mode", _cmd_ingest_mode, "Set mode [single|continuous|timed] [interval]"
)
registry.register("ingest", "status", _cmd_ingest_status, "Show queue and processing status")
registry.register(
    "ingest", "scan", _cmd_ingest_scan, "Dry-run: scan for new demos without processing"
)

# Build
registry.register("build", "run", _cmd_build_run, "Full build pipeline [--test-only]")
registry.register("build", "verify", _cmd_build_verify, "Post-build integrity verification")
registry.register("build", "manifest", _cmd_build_manifest, "Generate integrity manifest")

# Test
registry.register("test", "all", _cmd_test_all, "Run full pytest suite")
registry.register("test", "headless", _cmd_test_headless, "Run headless validator (79/79 gate)")
registry.register("test", "backend", _cmd_test_backend, "Run backend validator")
registry.register("test", "ui", _cmd_test_ui, "Run UI diagnostic")
registry.register("test", "hospital", _cmd_test_hospital, "Run Goliath Hospital [dept]")
registry.register("test", "suite", _cmd_test_suite, "Run ALL validators sequentially")

# Sys
registry.register("sys", "status", _cmd_sys_status, "Full system status dump")
registry.register("sys", "audit", _cmd_sys_audit, "Feature audit [--demo PATH]")
registry.register("sys", "baseline", _cmd_sys_baseline, "Temporal baseline comparison")
registry.register("sys", "db", _cmd_sys_db, "Database migration [-y]")
registry.register("sys", "vacuum", _cmd_sys_vacuum, "SQLite VACUUM on monolith")
registry.register("sys", "resources", _cmd_sys_resources, "CPU/RAM/disk usage")

# Set
registry.register("set", "steam", _cmd_set_steam, "Set Steam API key")
registry.register("set", "faceit", _cmd_set_faceit, "Set FACEIT API key")
registry.register("set", "config", _cmd_set_config, "Set config <key> <value>")
registry.register("set", "view", _cmd_set_view, "Show all settings")
registry.register("set", "demo-path", _cmd_set_demo_path, "Set user demo folder path")
registry.register("set", "pro-path", _cmd_set_pro_path, "Set pro demo folder path")

# Svc
registry.register("svc", "restart", _cmd_svc_restart, "Restart a supervised service")
registry.register("svc", "kill-all", _cmd_svc_kill_all, "Terminate all managed services")
registry.register("svc", "spawn", _cmd_svc_spawn, "Spawn a tool as background process")
registry.register("svc", "status", _cmd_svc_status, "Show service supervisor status")

# Maint
registry.register("maint", "clear-cache", _cmd_maint_clear_cache, "Delete __pycache__ dirs")
registry.register("maint", "clear-queue", _cmd_maint_clear_queue, "Purge queued ingestion tasks")
registry.register("maint", "sanitize", _cmd_maint_sanitize, "Run project sanitizer [-y]")
registry.register("maint", "dead-code", _cmd_maint_dead_code, "Run dead code detector")
registry.register("maint", "prune", _cmd_maint_prune, "Delete a match database <match_id>")

# Tool
registry.register("tool", "demo", _cmd_tool_demo, "Demo inspector [events|fields|track|all]")
registry.register("tool", "user", _cmd_tool_user, "User utilities [personalize|customize]")
registry.register("tool", "logs", _cmd_tool_logs, "View recent log files")
registry.register("tool", "list", _cmd_tool_list, "List all registered tools")

# Help & Exit (single-word commands)
registry.register("help", "", _cmd_help, "Show command reference")
registry.register("exit", "", _cmd_exit, "Graceful shutdown")


# ============================================================================
#  TUI RENDERER
# ============================================================================


class TUIRenderer:
    """Generates the Rich Layout for the persistent TUI dashboard."""

    def __init__(self):
        self._last_result = "Console v3.0 Ready."
        self._sys_cache: Dict[str, Any] = {"cpu": 0.0, "ram": None, "ts": 0.0}
        self._dirty = True  # Force first render

    def mark_dirty(self):
        self._dirty = True

    def set_result(self, msg: str):
        self._last_result = msg
        self._dirty = True

    def build_layout(self, status: Dict[str, Any]) -> Layout:
        layout = Layout(name="root")
        layout.split(
            Layout(name="header", size=4),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=16),
        )
        layout["body"].split_row(
            Layout(name="left", ratio=1),
            Layout(name="right", ratio=1),
        )
        layout["left"].split(
            Layout(name="ingestion", ratio=1),
            Layout(name="storage", ratio=1),
        )
        layout["right"].split(
            Layout(name="ml_status", ratio=1),
            Layout(name="system", ratio=1),
        )

        layout["header"].update(self._header(status))
        layout["left"]["ingestion"].update(self._ingest_panel(status))
        layout["left"]["storage"].update(self._storage_panel(status))
        layout["right"]["ml_status"].update(self._ml_panel(status))
        layout["right"]["system"].update(self._system_panel(status))
        layout["footer"].update(self._footer())
        return layout

    def update_panels(self, layout: Layout, status: Dict[str, Any], cmd_buffer: str = ""):
        """Update existing layout panels in-place (no Layout rebuild)."""
        layout["header"].update(self._header(status))
        layout["left"]["ingestion"].update(self._ingest_panel(status))
        layout["left"]["storage"].update(self._storage_panel(status))
        layout["right"]["ml_status"].update(self._ml_panel(status))
        layout["right"]["system"].update(self._system_panel(status))
        layout["footer"].update(self._footer(cmd_buffer))

    def _header(self, status: Dict) -> Panel:
        svcs = status.get("services", {})
        hunter = svcs.get("hunter", {})
        ing = status.get("ingestion", {})
        ml = status.get("ml_controller", {})

        # HLTV status
        hltv_st = hunter.get("status", "stopped")
        hltv_color = (
            "green" if hltv_st == "running" else ("red" if hltv_st == "crashed" else "yellow")
        )

        # Ingest status
        ing_running = ing.get("is_running", False)
        ing_queued = ing.get("queued", 0)
        ing_color = "green" if ing_running else "yellow"
        ing_text = f"Scanning {ing_queued} queued" if ing_running else "Idle"

        # ML status
        ml_running = ml.get("is_running", False)
        ml_paused = ml.get("paused", False)
        ml_color = "yellow" if ml_paused else ("green" if ml_running else "dim white")
        ml_text = "Paused" if ml_paused else ("Training" if ml_running else "Idle")

        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=2)
        grid.add_column(justify="right", ratio=1)
        grid.add_row(
            "[bold white]MACENA CS2 ANALYZER[/bold white]  |  [bold]UNIFIED CONSOLE v3.0[/bold]",
            f"[dim]{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]",
        )
        grid.add_row(
            f"[{hltv_color}][HLTV: {hltv_st.upper()}][/]  "
            f"[{ing_color}][Ingest: {ing_text}][/]  "
            f"[{ml_color}][ML: {ml_text}][/]",
            "",
        )
        return Panel(grid, style="white on blue", box=box.ROUNDED)

    def _ingest_panel(self, status: Dict) -> Panel:
        ing = status.get("ingestion", {})
        tbl = Table(expand=True, show_header=False, box=box.SIMPLE)
        tbl.add_column("Key", style="dim", min_width=10)
        tbl.add_column("Value")
        tbl.add_row("Mode", ing.get("mode", "?").upper())

        # Phase-aware status display
        phase = ing.get("phase", "idle")
        if not ing.get("is_running"):
            phase_display = "[dim]STANDBY[/]"
        elif phase.startswith("processing"):
            phase_display = f"[success]{phase}[/]"
        elif phase.startswith("waiting"):
            phase_display = f"[warning]{phase}[/]"
        elif phase == "discovering":
            phase_display = "[info]DISCOVERING...[/]"
        else:
            phase_display = f"[success]{phase}[/]"
        tbl.add_row("Status", phase_display)

        total_found = ing.get("total_found", 0)
        tbl.add_row("Found", f"[bold]{total_found}[/] demos")
        tbl.add_row("Queued", str(ing.get("queued", 0)))
        tbl.add_row("Active", str(ing.get("processing", 0)))
        tbl.add_row("Failed", str(ing.get("failed", 0)))
        tbl.add_row("Current", f"[bold yellow]{ing.get('current_file', 'None')}[/]")

        # Add Progress Bar
        progress = ing.get("progress", 0.0)
        bar = ProgressBar(
            total=100.0,
            completed=progress,
            width=20,
            complete_style="green",
            finished_style="green",
        )
        tbl.add_row("Progress", bar)

        tbl.add_row("Interval", f"{ing.get('interval', 30)}m")
        return Panel(tbl, title="[digester]INGESTION[/digester]", border_style="cyan")

    def _ml_panel(self, status: Dict) -> Panel:
        ml = status.get("ml_controller", {})
        teacher = status.get("teacher", {})
        tbl = Table(expand=True, show_header=False, box=box.SIMPLE)
        tbl.add_column("Key", style="dim", min_width=10)
        tbl.add_column("Value")

        if ml.get("is_running"):
            state = "[warning]PAUSED[/]" if ml.get("paused") else "[success]TRAINING[/]"
        else:
            state = "[dim]IDLE[/]"
        tbl.add_row("State", state)
        tbl.add_row("Teacher", f"[brain]{teacher.get('status', 'N/A')}[/]")
        tbl.add_row("Detail", teacher.get("detail", "Awaiting instruction..."))
        tbl.add_row("Stop Req", "[error]Yes[/]" if ml.get("stop_requested") else "[dim]No[/]")
        return Panel(tbl, title="[brain]ML / BRAIN[/brain]", border_style="magenta")

    def _storage_panel(self, status: Dict) -> Panel:
        st = status.get("storage", {})
        t12_mb = st.get("tier1_2_size", 0) / (1024 * 1024)
        t3_mb = st.get("tier3_total_size", 0) / (1024 * 1024)
        anomalies = st.get("anomalies", [])
        tbl = Table(expand=True, show_header=False, box=box.SIMPLE)
        tbl.add_column("Key", style="dim", min_width=10)
        tbl.add_column("Value")
        tbl.add_row("Monolith", f"{t12_mb:.2f} MB")
        tbl.add_row("Matches", f"{st.get('tier3_count', 0)} files ({t3_mb:.1f} MB)")
        anom_style = "error" if anomalies else "success"
        tbl.add_row("Anomalies", f"[{anom_style}]{len(anomalies)}[/]")
        return Panel(tbl, title="[archive]STORAGE[/archive]", border_style="yellow")

    def _system_panel(self, status: Dict) -> Panel:
        import psutil

        now = time.monotonic()
        if now - self._sys_cache["ts"] > 1.0:
            self._sys_cache["cpu"] = psutil.cpu_percent(interval=0)
            self._sys_cache["ram"] = psutil.virtual_memory()
            self._sys_cache["ts"] = now
        cpu = self._sys_cache["cpu"]
        ram = self._sys_cache["ram"]
        bl = status.get("baseline", {})

        tbl = Table(expand=True, show_header=False, box=box.SIMPLE)
        tbl.add_column("Key", style="dim", min_width=10)
        tbl.add_column("Value")
        tbl.add_row("CPU", f"{cpu:.0f}%")
        if ram is not None:
            tbl.add_row(
                "RAM",
                f"{ram.used / 1024 / 1024:.0f} / {ram.total / 1024 / 1024:.0f} MB ({ram.percent}%)",
            )
        else:
            tbl.add_row("RAM", "[dim]...[/dim]")
        tbl.add_row("Baseline", f"{bl.get('mode', '?')} ({bl.get('stat_cards', 0)} cards)")
        return Panel(tbl, title="[bold]SYSTEM[/bold]", border_style="white")

    def _footer(self, cmd_buffer: str = "") -> Panel:
        grid = Table.grid(expand=True)
        grid.add_row(f"[bold]> Last:[/bold] {self._last_result}")
        cursor = " [blink]_[/]"
        grid.add_row(f"[bold blue]MACENA>[/bold blue] {cmd_buffer}{cursor}")
        grid.add_row("")
        # Command reference — all categories with sub-commands visible
        _D = "[dim]"
        _E = "[/dim]"
        grid.add_row(
            f"  [info]ml[/]     {_D}start | stop | pause | resume | throttle <0-1> | status{_E}"
        )
        grid.add_row(
            f"  [info]ingest[/] {_D}start [-p] | stop | scan | mode <single|continuous|timed> [min] | status{_E}"
        )
        grid.add_row(f"  [info]build[/]  {_D}run [--test-only] | verify | manifest{_E}")
        grid.add_row(
            f"  [info]test[/]   {_D}all | headless | backend | ui | hospital [dept] | suite{_E}"
        )
        grid.add_row(
            f"  [info]sys[/]    {_D}status | audit [--demo PATH] | baseline | db [-y] | vacuum | resources{_E}"
        )
        grid.add_row(
            f"  [info]set[/]    {_D}steam <key> | faceit <key> | config <k> <v> | view | demo-path <path> | pro-path <path>{_E}"
        )
        grid.add_row(
            f"  [info]svc[/]    {_D}restart <name> | kill-all | spawn <script> | status{_E}"
        )
        grid.add_row(
            f"  [info]maint[/]  {_D}clear-cache | clear-queue | sanitize [-y] | dead-code | prune <id>{_E}"
        )
        grid.add_row(
            f"  [info]tool[/]   {_D}demo [events|fields|track|all] | user | logs | list{_E}"
        )
        grid.add_row(f"  [info]help[/]   [error]exit[/]")
        return Panel(grid, title="Command Interface", border_style="white")


# ============================================================================
#  STATUS POLLER (background thread — eliminates blocking in render loop)
# ============================================================================

import threading


class StatusPoller:
    """Background thread that caches system status at a fixed interval.

    The TUI render loop reads the cached dict (fast, non-blocking)
    instead of calling get_system_status() synchronously every frame.
    """

    _STATUS_POLL_INTERVAL_S = 2.0

    def __init__(self, sys_console):
        self._sc = sys_console
        self._status: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._poll, daemon=True, name="StatusPoller")

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=3)

    def get(self) -> Dict[str, Any]:
        with self._lock:
            return self._status.copy()

    def _poll(self):
        while not self._stop.is_set():
            try:
                new_status = self._sc.get_system_status()
            except Exception as e:
                logger.warning("StatusPoller: get_system_status() failed: %s", e)
                new_status = {"_error": str(e), "state": "STATUS UNAVAILABLE"}
            with self._lock:
                self._status = new_status
            self._stop.wait(self._STATUS_POLL_INTERVAL_S)


# ============================================================================
#  TUI MODE
# ============================================================================


def run_tui_mode():
    """Interactive persistent TUI with status dashboard (Non-blocking)."""
    import psutil
    from rich.live import Live

    sc = _get_sys_console()
    sc.boot()
    renderer = TUIRenderer()
    poller = StatusPoller(sc)
    is_running = True
    cmd_buffer = ""

    # Prime psutil CPU measurement so first frame is not 0%
    psutil.cpu_percent(interval=None)

    def _handle_exit(sig, frame):
        nonlocal is_running
        is_running = False

    signal.signal(signal.SIGINT, _handle_exit)

    # Initial layout (built once, then updated in-place)
    status = sc.get_system_status()
    layout = renderer.build_layout(status)

    # Start background status polling
    poller.start()

    # Unix terminal: save state and set cbreak mode for non-blocking input
    _old_term_settings = None
    if _unix_input:
        _old_term_settings = termios.tcgetattr(sys.stdin.fileno())
        tty.setcbreak(sys.stdin.fileno())

    try:
        # Throttle: only refresh at TUI_REFRESH_PER_SECOND to prevent flickering
        _min_refresh_interval = 1.0 / TUI_REFRESH_PER_SECOND
        _last_refresh_time = 0.0
        _prev_status_hash = None

        with Live(layout, console=rich_con, screen=True, auto_refresh=False) as live:
            while is_running:
                now = time.monotonic()

                # 1. Read cached status (non-blocking)
                status = poller.get()

                # Detect status change via lightweight hash
                _status_hash = hash(str(status.get("ingestion", {}))) ^ hash(
                    str(status.get("ml_controller", {}))
                )
                if _status_hash != _prev_status_hash:
                    renderer.mark_dirty()
                    _prev_status_hash = _status_hash

                # 2. Handle Input (platform-aware) — always responsive
                has_input = False
                if msvcrt:
                    has_input = msvcrt.kbhit()
                elif _unix_input:
                    has_input = bool(_select_mod.select([sys.stdin], [], [], 0)[0])

                if has_input:
                    if msvcrt:
                        ch = msvcrt.getwch()
                    else:
                        ch = sys.stdin.read(1)

                    if ch in ("\r", "\n"):  # Enter
                        cmd = cmd_buffer.strip()
                        cmd_buffer = ""
                        renderer.mark_dirty()

                        if not cmd:
                            pass
                        else:
                            result = registry.dispatch_interactive(cmd)

                            if result == "__EXIT__":
                                is_running = False
                                break

                            if result:
                                if ">>>" in result:
                                    renderer.set_result(result)
                                    live.stop()
                                    rich_con.print(result)
                                    rich_con.input("\n[dim]Press Enter to continue...[/dim]")
                                    live.start()
                                    renderer.mark_dirty()
                                else:
                                    renderer.set_result(result)

                    elif ch in ("\b", "\x7f"):  # Backspace (Win=\b, Unix=\x7f)
                        cmd_buffer = cmd_buffer[:-1]
                        renderer.mark_dirty()
                    elif ch == "\x03":  # Ctrl+C
                        is_running = False
                    else:
                        if ch.isprintable():
                            cmd_buffer += ch
                            renderer.mark_dirty()

                # 3. Throttled refresh — ONLY when dirty AND interval elapsed
                # No unconditional periodic refresh — status changes already mark dirty
                elapsed = now - _last_refresh_time
                if renderer._dirty and elapsed >= _min_refresh_interval:
                    renderer.update_panels(layout, status, cmd_buffer)
                    live.refresh()
                    renderer._dirty = False
                    _last_refresh_time = now

                time.sleep(TUI_INPUT_POLL_INTERVAL_S)

    finally:
        # Restore terminal settings on Unix before any other cleanup
        if _old_term_settings is not None:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _old_term_settings)
        poller.stop()
        sc.shutdown()
        rich_con.print("[bold]Console shutdown complete.[/bold]")


# ============================================================================
#  CLI MODE
# ============================================================================


def build_cli_parser() -> argparse.ArgumentParser:
    """Build argparse for non-interactive CLI mode."""
    parser = argparse.ArgumentParser(
        prog="console", description="Macena CS2 Analyzer — Unified Console v3.0"
    )
    sub = parser.add_subparsers(dest="category", help="Command category")

    # ML
    ml_p = sub.add_parser("ml", help="Machine Learning control")
    ml_sub = ml_p.add_subparsers(dest="subcmd")
    ml_sub.add_parser("start", help="Start training cycle")
    ml_sub.add_parser("stop", help="Stop training")
    ml_sub.add_parser("pause", help="Pause training")
    ml_sub.add_parser("resume", help="Resume training")
    t = ml_sub.add_parser("throttle", help="Set throttle [0-1.0]")
    t.add_argument("value", type=float)
    ml_sub.add_parser("status", help="Show ML status")

    # Ingest
    ig_p = sub.add_parser("ingest", help="Ingestion control")
    ig_sub = ig_p.add_subparsers(dest="subcmd")
    s = ig_sub.add_parser("start", help="Start ingestion")
    s.add_argument("--priority", "-p", action="store_true")
    ig_sub.add_parser("stop", help="Stop ingestion")
    m = ig_sub.add_parser("mode", help="Set mode")
    m.add_argument("mode_type", choices=["single", "continuous", "timed"])
    m.add_argument("interval", type=int, nargs="?", default=30)
    ig_sub.add_parser("status", help="Show status")
    ig_sub.add_parser("scan", help="Dry-run: scan for new demos")

    # Build
    bd_p = sub.add_parser("build", help="Build pipeline")
    bd_sub = bd_p.add_subparsers(dest="subcmd")
    r = bd_sub.add_parser("run", help="Full build")
    r.add_argument("--test-only", action="store_true")
    bd_sub.add_parser("verify", help="Post-build verify")
    bd_sub.add_parser("manifest", help="Generate manifest")

    # Test
    ts_p = sub.add_parser("test", help="Test runners")
    ts_sub = ts_p.add_subparsers(dest="subcmd")
    ts_sub.add_parser("all", help="Run pytest suite")
    ts_sub.add_parser("headless", help="Run headless validator")
    ts_sub.add_parser("backend", help="Run backend validator")
    ts_sub.add_parser("ui", help="Run UI diagnostic")
    h = ts_sub.add_parser("hospital", help="Run Goliath Hospital")
    h.add_argument("--dept", "-d", type=str)
    ts_sub.add_parser("suite", help="Run ALL validators")

    # Sys
    sy_p = sub.add_parser("sys", help="System operations")
    sy_sub = sy_p.add_subparsers(dest="subcmd")
    sy_sub.add_parser("status", help="System status")
    a = sy_sub.add_parser("audit", help="Feature audit")
    a.add_argument("--demo", type=str)
    sy_sub.add_parser("baseline", help="Baseline comparison")
    d = sy_sub.add_parser("db", help="Database migration")
    d.add_argument("-y", "--yes", action="store_true")
    sy_sub.add_parser("vacuum", help="VACUUM database")
    sy_sub.add_parser("resources", help="CPU/RAM usage")

    # Maint
    mt_p = sub.add_parser("maint", help="Maintenance operations")
    mt_sub = mt_p.add_subparsers(dest="subcmd")
    mt_sub.add_parser("clear-cache", help="Delete __pycache__")
    mt_sub.add_parser("clear-queue", help="Purge ingestion queue")
    s2 = mt_sub.add_parser("sanitize", help="Sanitize project")
    s2.add_argument("-y", "--yes", action="store_true")
    mt_sub.add_parser("dead-code", help="Dead code detector")
    pr = mt_sub.add_parser("prune", help="Delete match data")
    pr.add_argument("match_id", type=int)

    # Set
    st_p = sub.add_parser("set", help="Configuration settings")
    st_sub = st_p.add_subparsers(dest="subcmd")
    st_steam = st_sub.add_parser("steam", help="Set Steam API key")
    st_steam.add_argument("key", type=str)
    st_faceit = st_sub.add_parser("faceit", help="Set FACEIT API key")
    st_faceit.add_argument("key", type=str)
    st_cfg = st_sub.add_parser("config", help="Set config key/value")
    st_cfg.add_argument("key", type=str)
    st_cfg.add_argument("value", type=str)
    st_sub.add_parser("view", help="View current settings")
    st_demo_path = st_sub.add_parser("demo-path", help="Set user demo folder path")
    st_demo_path.add_argument("path", type=str, nargs="+")
    st_pro_path = st_sub.add_parser("pro-path", help="Set pro demo folder path")
    st_pro_path.add_argument("path", type=str, nargs="+")

    # Svc
    sv_p = sub.add_parser("svc", help="Service management")
    sv_sub = sv_p.add_subparsers(dest="subcmd")
    sv_restart = sv_sub.add_parser("restart", help="Restart a service")
    sv_restart.add_argument("service_name", type=str)
    sv_sub.add_parser("kill-all", help="Terminate all services")
    sv_spawn = sv_sub.add_parser("spawn", help="Spawn background tool")
    sv_spawn.add_argument("script_name", type=str)
    sv_sub.add_parser("status", help="Show service status")

    # Tool
    tl_p = sub.add_parser("tool", help="Tool utilities")
    tl_sub = tl_p.add_subparsers(dest="subcmd")
    tl_demo = tl_sub.add_parser("demo", help="Demo file inspection")
    tl_demo.add_argument("subcommand", type=str, nargs="?", default="all")
    tl_user = tl_sub.add_parser("user", help="User utilities")
    tl_user.add_argument("subcommand", type=str, nargs="?", default="personalize")
    tl_sub.add_parser("logs", help="View recent log files")
    tl_sub.add_parser("list", help="List available tools")

    return parser


def run_cli_mode(argv: List[str]):
    """Non-interactive command dispatch."""
    # Handle 'help' before argparse (not registered as subparser)
    if argv and argv[0] == "help":
        category = argv[1] if len(argv) > 1 else None
        result = registry.get_help(category)
        rich_con.print(result)
        return 0

    parser = build_cli_parser()
    args = parser.parse_args(argv)

    if not args.category:
        parser.print_help()
        return 0

    subcmd = getattr(args, "subcmd", "") or ""

    # Build the args list for the handler
    handler_args = []
    if args.category == "ml" and subcmd == "throttle":
        handler_args = [str(args.value)]
    elif args.category == "ingest" and subcmd == "start" and getattr(args, "priority", False):
        handler_args = ["--priority"]
    elif args.category == "ingest" and subcmd == "mode":
        handler_args = [args.mode_type, str(args.interval)]
    elif args.category == "build" and subcmd == "run" and getattr(args, "test_only", False):
        handler_args = ["--test-only"]
    elif args.category == "test" and subcmd == "hospital" and getattr(args, "dept", None):
        handler_args = [args.dept]
    elif args.category == "sys" and subcmd == "audit" and getattr(args, "demo", None):
        handler_args = [args.demo]
    elif args.category == "sys" and subcmd == "db" and getattr(args, "yes", False):
        handler_args = ["-y"]
    elif args.category == "maint" and subcmd == "sanitize" and getattr(args, "yes", False):
        handler_args = ["-y"]
    elif args.category == "maint" and subcmd == "prune":
        handler_args = [str(args.match_id)]
    elif args.category == "set" and subcmd == "steam":
        handler_args = [args.key]
    elif args.category == "set" and subcmd == "faceit":
        handler_args = [args.key]
    elif args.category == "set" and subcmd == "config":
        handler_args = [args.key, args.value]
    elif args.category == "set" and subcmd in ("demo-path", "pro-path"):
        handler_args = getattr(args, "path", [])
    elif args.category == "svc" and subcmd == "restart":
        handler_args = [args.service_name]
    elif args.category == "svc" and subcmd == "spawn":
        handler_args = [args.script_name]
    elif args.category == "tool" and subcmd == "demo":
        handler_args = [args.subcommand]
    elif args.category == "tool" and subcmd == "user":
        handler_args = [args.subcommand]

    result = registry.dispatch(args.category, subcmd, handler_args)
    if result:
        rich_con.print(result)

    # Return exit code: check if first line starts with [error] tag
    _first_line = (result or "").split("\n", 1)[0].strip()
    if _first_line.startswith("[error]"):
        return 1
    return 0


# ============================================================================
#  ENTRY POINT
# ============================================================================


def main():
    if len(sys.argv) > 1:
        code = run_cli_mode(sys.argv[1:])
        sys.exit(code)
    else:
        run_tui_mode()


if __name__ == "__main__":
    main()
