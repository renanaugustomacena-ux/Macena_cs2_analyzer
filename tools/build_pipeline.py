import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# --- Venv Guard ---
if sys.prefix == sys.base_prefix:
    print("ERROR: Not in venv. Run: source ~/.venvs/cs2analyzer/bin/activate", file=sys.stderr)
    sys.exit(2)

# --- Path Stabilization ---
# We use the robust header defined in MTS-IS
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
    from rich.logging import RichHandler
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.text import Text
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
        "stage": "bold magenta reverse",
        "path": "underline blue",
    }
)

console = Console(theme=MTS_THEME, record=True)
install_rich_traceback(console=console)


# --- Logging Setup ---
def setup_logging(log_dir: Path):
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"build_pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    # File Handler - JSON Structured
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}'
    )
    file_handler.setFormatter(file_formatter)

    # Root Logger
    logger = logging.getLogger("MacenaBuild")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)

    return logger, log_file


class IndustrialBuildPipeline:
    def __init__(self, test_only: bool = False):
        self.project_root = project_root
        self.dist_dir = self.project_root / "dist"
        self.build_dir = self.project_root / "build"
        self.log_dir = self.project_root / "logs"
        self.test_only = test_only
        self.logger, self.log_file = setup_logging(self.log_dir)

        # Handle Ctrl+C
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, sig, frame):
        console.print("\n[error]>>> Interrupted by User. Aborting...[/error]")
        self.logger.warning("Build process interrupted by user.")
        sys.exit(1)

    def _run_command(self, command: str, cwd: Path) -> bool:
        """Runs a shell command, streaming output to logs and showing spinner."""
        self.logger.info(f"Executing: {command}")

        try:
            import shlex

            cmd_parts = shlex.split(command)
            process = subprocess.run(
                cmd_parts,
                shell=False,
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            # Log full output
            if process.stdout:
                self.logger.debug(f"STDOUT: {process.stdout.strip()}")
            if process.stderr:
                self.logger.debug(f"STDERR: {process.stderr.strip()}")

            if process.returncode != 0:
                console.print(f"[error]Command Failed with code {process.returncode}[/error]")
                console.print(
                    Panel(
                        process.stderr[-1000:] if process.stderr else "No stderr",
                        title="Error Output",
                        border_style="red",
                    )
                )
                self.logger.error(f"Command failed: {command}")
                return False

            return True
        except Exception as e:
            console.print_exception()
            self.logger.exception(f"Exception during command execution: {command}")
            return False

    def run_stage(self, title: str, command: str) -> bool:
        """Executes a build stage with visual feedback."""
        console.print(f"\n[stage] STAGE: {title} [/stage]")
        self.logger.info(f"Starting Stage: {title}")

        with console.status(f"[bold cyan]Working on {title}...[/bold cyan]", spinner="dots"):
            start_time = time.time()
            success = self._run_command(command, self.project_root)
            duration = time.time() - start_time

        if success:
            console.print(f"✅ [success]{title} completed[/success] in {duration:.2f}s")
            self.logger.info(f"Stage {title} success in {duration:.2f}s")
            return True
        else:
            console.print(f"❌ [error]{title} FAILED[/error] in {duration:.2f}s")
            self.logger.error(f"Stage {title} failed in {duration:.2f}s")
            return False

    def execute(self):
        console.print(
            Panel.fit(
                f"[bold cyan]MACENA CS2 ANALYZER[/bold cyan]\nIndustrial Build Pipeline v2.0\n[dim]Log: {self.log_file}[/dim]",
                title="System Init",
                border_style="blue",
            )
        )

        # 1. Sanitization
        if not self.run_stage(
            "Project Sanitization", f'"{sys.executable}" tools/Sanitize_Project.py --yes'
        ):
            return False

        # 2. Unit Testing
        test_dir = self.project_root / "Programma_CS2_RENAN" / "tests"
        if test_dir.exists():
            if not self.run_stage(
                "Logic Verification (Unit Tests)",
                f'"{sys.executable}" -m pytest "{test_dir}" -x -q',
            ):
                return False
        else:
            self.logger.warning(f"Test directory not found: {test_dir}")
            console.print(f"[warning]Test directory missing: {test_dir}. Skipping tests.[/warning]")

        # 3. Integrity Manifest
        if not self.run_stage(
            "Generate Integrity Manifest",
            f'"{sys.executable}" Programma_CS2_RENAN/tools/sync_integrity_manifest.py',
        ):
            return False

        if self.test_only:
            console.print(
                Panel(
                    "[yellow]Test-Only Mode - Skipping Compilation[/yellow]", border_style="yellow"
                )
            )
            return True

        # 5. Cleanup
        with console.status("[bold red]Cleaning old artifacts...[/bold red]"):
            try:
                if self.dist_dir.exists():
                    shutil.rmtree(self.dist_dir)
                if self.build_dir.exists():
                    shutil.rmtree(self.build_dir)
                self.logger.info("Cleaned dist/ and build/ directories")
            except Exception as e:
                console.print(f"[warning]Cleanup warning: {e}[/warning]")

        # 6. Compilation
        spec_file = self.project_root / "cs2_analyzer_win.spec"
        if not spec_file.exists():
            spec_file = self.project_root / "cs2_analyzer.spec"

        console.print(f"[info]Using Spec File: [path]{spec_file.name}[/path][/info]")

        # Locate PyInstaller
        pyinstaller_exe = self.project_root / "venv_win" / "Scripts" / "pyinstaller.exe"
        if not pyinstaller_exe.exists():
            pyinstaller_exe = "pyinstaller"

        build_cmd = f'"{pyinstaller_exe}" --noconfirm "{spec_file}" --log-level WARN'
        if not self.run_stage("PyInstaller Compilation", build_cmd):
            return False

        # 7. Post-Build Audit
        if not self.run_stage(
            "Binary Integrity Audit", f'"{sys.executable}" tools/audit_binaries.py'
        ):
            console.print("[error]Binary audit FAILED. Build cannot be trusted.[/error]")
            return False

        console.print(
            Panel(
                f"[bold green]BUILD SUCCESSFUL[/bold green]\nTarget: [path]{self.dist_dir}[/path]",
                title="Mission Complete",
                border_style="green",
            )
        )
        return True


if __name__ == "__main__":
    test_mode = "--test-only" in sys.argv
    pipeline = IndustrialBuildPipeline(test_only=test_mode)
    if not pipeline.execute():
        sys.exit(1)
