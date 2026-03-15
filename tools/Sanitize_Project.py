import argparse
import logging
import os
import shutil
import signal
import sys
from datetime import datetime
from pathlib import Path

# --- Venv Guard ---
if sys.prefix == sys.base_prefix and not os.environ.get("CI"):
    print("ERROR: Not in venv. Run: source ~/.venvs/cs2analyzer/bin/activate", file=sys.stderr)
    sys.exit(2)

# --- Path Stabilization ---
script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# --- Windows Encoding Fix ---
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# --- Rich & Logging Imports ---
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Confirm
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
        "action": "bold blue",
        "path": "underline blue",
    }
)

console = Console(theme=MTS_THEME)
install_rich_traceback(console=console)


# --- Logging Setup ---
def setup_logging(log_dir: Path):
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"sanitize_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}'
    )
    file_handler.setFormatter(file_formatter)

    logger = logging.getLogger("Sanitizer")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)
    return logger, log_file


class IndustrialSanitizer:
    def __init__(self, force: bool = False):
        self.project_root = project_root
        self.force = force
        self.logger, self.log_file = setup_logging(self.project_root / "logs")

        # Targets to sanitize
        self.app_dir = self.project_root / "Programma_CS2_RENAN"
        self.targets = [
            {
                "path": self.app_dir / "backend" / "storage" / "database.db",
                "action": "DELETE",
                "desc": "Main local database (user profile, coaching history, stats).",
            },
            {
                "path": self.app_dir / "backend" / "storage" / "hltv_metadata.db",
                "action": "DELETE",
                "desc": "HLTV pro player statistics database.",
            },
            {
                "path": self.app_dir / "backend" / "storage" / "match_data",
                "action": "CLEAR",
                "desc": "Per-match SQLite databases from demo ingestion.",
            },
            {
                "path": self.project_root / "models",
                "action": "CLEAR",
                "desc": "ML model checkpoints (jepa_brain.pt, etc.).",
            },
            {
                "path": self.project_root / "logs",
                "action": "CLEAR",
                "desc": "Wipes all execution and debug logs.",
            },
            {
                "path": self.app_dir / "hltv_sync.pid",
                "action": "DELETE",
                "desc": "Stale process ID file.",
            },
        ]

        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, sig, frame):
        console.print("\n[error]>>> Operation cancelled by user.[/error]")
        self.logger.warning("Sanitization cancelled by user SIGINT.")
        sys.exit(1)

    def display_plan(self):
        table = Table(title="Sanitization Action Plan", border_style="blue")
        table.add_column("Target Path", style="path")
        table.add_column("Action", style="action")
        table.add_column("Description", style="dim")
        table.add_column("Status", style="info")

        for t in self.targets:
            exists = t["path"].exists()
            status = "[success]Present[/success]" if exists else "[dim]Not Found[/dim]"
            rel_path = (
                t["path"].relative_to(self.project_root)
                if t["path"].is_relative_to(self.project_root)
                else t["path"]
            )
            table.add_row(str(rel_path), t["action"], t["desc"], status)

        console.print(table)

    def execute(self):
        console.print(
            Panel.fit(
                "[bold cyan]MACENA PROJECT SANITIZER[/bold cyan]\n[dim]Industrial Grade Cleaning & Privacy Prep[/dim]",
                border_style="blue",
            )
        )

        self.display_plan()

        if not self.force:
            if not Confirm.ask(
                "\n[warning]Are you sure you want to execute these destructive actions?[/warning]"
            ):
                console.print("[info]Sanitization aborted.[/info]")
                return False

        self.logger.info("Starting execution phase.")
        with console.status("[bold red]Sanitizing project files...[/bold red]"):
            for t in self.targets:
                path = t["path"]
                action = t["action"]

                if not path.exists():
                    self.logger.debug(f"Skip: {path} (Not found)")
                    continue

                try:
                    if action == "DELETE":
                        if path.is_file():
                            path.unlink()
                        elif path.is_dir():
                            shutil.rmtree(path)
                        console.print(f"✅ [success]Deleted:[/success] [path]{path.name}[/path]")
                        self.logger.info(f"Deleted: {path}")

                    elif action == "CLEAR":
                        if path.is_dir():
                            # We don't delete the logs dir itself to avoid breaking logger
                            for item in path.iterdir():
                                if item == self.log_file:
                                    continue  # Keep current log
                                if item.is_file():
                                    item.unlink()
                                elif item.is_dir():
                                    shutil.rmtree(item)
                            console.print(
                                f"✅ [success]Cleared:[/success] [path]{path.name}/[/path]"
                            )
                            self.logger.info(f"Cleared directory: {path}")

                except Exception as e:
                    console.print(f"❌ [error]Failed to process {path.name}:[/error] {e}")
                    self.logger.error(f"Error processing {path}: {e}")

        console.print(
            Panel(
                "[bold green]PROJECT SANITIZED SUCCESSFULLY[/bold green]\nReady for distribution or clean restart.",
                border_style="green",
            )
        )
        return True


def main():
    parser = argparse.ArgumentParser(description="Macena Project Sanitizer (MTS-IS)")
    parser.add_argument(
        "-y", "--yes", action="store_true", help="Force execution without confirmation."
    )
    args = parser.parse_args()

    sanitizer = IndustrialSanitizer(force=args.yes)
    success = sanitizer.execute()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
