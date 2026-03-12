#!/usr/bin/env python3
"""
================================================================================
                    GOLIATH HOSPITAL DIAGNOSTIC SYSTEM
                    ===================================
    The Ultimate Clinical Diagnostic Authority for Macena CS2 Analyzer

    Not just a debugger - an ENTIRE HOSPITAL for project health.

    DEPARTMENTS:
    - Emergency Room (ER):     Critical syntax/import issues
    - Radiology:               Visual asset integrity scans
    - Pathology Lab:           Data quality, mock vs real detection
    - Cardiology:              Core module health (DB, config, models)
    - Neurology:               ML/AI system integrity
    - Oncology:                Dead code, deprecated patterns, tech debt
    - Pediatrics:              New/recently modified files
    - ICU:                     Integration tests, end-to-end flows
    - Pharmacy:                Dependency health and version checks
    - Tool Clinic:             Validates all project tool scripts

    Author: Macena Development Team
    Version: 2.1.0 (Hospital Edition)
================================================================================
"""

import ast
import importlib.util
import json
import os
import re
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import signal
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

# Centralized path stabilization (handles sys.path, encoding, KIVY_NO_ARGS)
from _infra import path_stabilize

PROJECT_ROOT, SOURCE_ROOT = path_stabilize()

# F8-19: Goliath Hospital uses print() for console output rather than structured logging.
# As a diagnostic tool (not production service), this is acceptable — all findings are
# captured in DiagnosticFinding objects with severity levels.

# =============================================================================
# CLINICAL CONSTANTS & CONFIGURATION
# =============================================================================


class Severity(Enum):
    """Medical severity levels for diagnostic findings."""

    CRITICAL = "CRITICAL"  # System cannot run
    ERROR = "ERROR"  # Major issue requiring fix
    WARNING = "WARNING"  # Potential problem
    INFO = "INFO"  # Normal operation
    DEBUG = "DEBUG"  # Detailed diagnostic
    HEALTHY = "HEALTHY"  # All clear


class Department(Enum):
    """Hospital departments for categorizing diagnostics."""

    ER = "Emergency Room"
    RADIOLOGY = "Radiology"
    PATHOLOGY = "Pathology Lab"
    CARDIOLOGY = "Cardiology"
    NEUROLOGY = "Neurology"
    ONCOLOGY = "Oncology"
    PEDIATRICS = "Pediatrics"
    ICU = "ICU"
    PHARMACY = "Pharmacy"
    TOOL_CLINIC = "Tool Clinic"
    ENDOCRINOLOGY = "Endocrinology"


# Configuration
EXCLUDE_DIRS = {
    "venv",
    "venv_win",
    "__pycache__",
    ".git",
    "node_modules",
    "dist",
    "build",
    "android_app",
    ".buildozer",
    "ios_app",
    "research",
    "mobile_app",
    "android",
    ".mypy_cache",
    ".pytest_cache",
    "eggs",
    "*.egg-info",
}

FORBIDDEN_PATTERNS = [
    r"/home/[a-z]+/Desktop",  # Linux desktop paths
    r"C:\\Users\\[A-Za-z]+\\Desktop",  # Windows desktop (non-project)
    r"EA6635E16635AF67",  # Sensitive identifiers
    r'password\s*=\s*["\'][^"\']+["\']',  # Hardcoded passwords
    r'api_key\s*=\s*["\'][^"\']+["\']',  # Hardcoded API keys (outside config)
]

MOCK_DATA_INDICATORS = [
    "mock",
    "fake",
    "dummy",
    "test_",
    "sample_",
    "placeholder",
    "FIXME",
    "TODO",
    "XXX",
    "HACK",
    "lorem ipsum",
    "12345",
    "example.com",
    "test@test",
    "foo",
    "bar",
    "baz",
]

# NOTE: Direct "from backend./from core." imports are already caught by ER's
# _check_critical_imports(). AsyncMapRegistry and asset_loader have been fully
# removed from the codebase. Only genuinely active deprecated patterns here.
DEPRECATED_PATTERNS = [
    (r'print\s*\(\s*f?["\']DEBUG', "Debug print statement in production code"),
    (r"training_orchestrator\.py\.backup", "Backup file should be removed"),
]

CRITICAL_MODULES = [
    "Programma_CS2_RENAN/core/config.py",
    "Programma_CS2_RENAN/core/logger.py",
    "Programma_CS2_RENAN/core/asset_manager.py",
    "Programma_CS2_RENAN/core/map_manager.py",
    "Programma_CS2_RENAN/core/session_engine.py",
    "Programma_CS2_RENAN/core/spatial_data.py",
    "Programma_CS2_RENAN/backend/storage/database.py",
    "Programma_CS2_RENAN/backend/storage/db_models.py",
    "Programma_CS2_RENAN/backend/storage/match_data_manager.py",
    "Programma_CS2_RENAN/backend/nn/model.py",
    "Programma_CS2_RENAN/backend/nn/jepa_model.py",
    "Programma_CS2_RENAN/backend/nn/coach_manager.py",
    "Programma_CS2_RENAN/backend/services/coaching_service.py",
    "Programma_CS2_RENAN/backend/services/analysis_orchestrator.py",
    "Programma_CS2_RENAN/backend/control/console.py",
    "Programma_CS2_RENAN/backend/processing/feature_engineering/vectorizer.py",
    "Programma_CS2_RENAN/backend/processing/tensor_factory.py",
    "Programma_CS2_RENAN/backend/analysis/__init__.py",
    "Programma_CS2_RENAN/backend/knowledge/experience_bank.py",
    "Programma_CS2_RENAN/backend/knowledge/graph.py",
    "Programma_CS2_RENAN/backend/ingestion/resource_manager.py",
    "Programma_CS2_RENAN/observability/logger_setup.py",
]

# =============================================================================
# DATA CLASSES FOR FINDINGS
# =============================================================================


@dataclass
class DiagnosticFinding:
    """A single diagnostic finding from any department."""

    department: str
    severity: str
    category: str
    file_path: str
    line_number: Optional[int]
    message: str
    suggestion: Optional[str] = None
    code_snippet: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class FileHealth:
    """Health status for a single file."""

    path: str
    size_bytes: int
    line_count: int
    function_count: int
    class_count: int
    import_count: int
    complexity_score: float
    last_modified: str
    has_docstring: bool
    findings: List[DiagnosticFinding] = field(default_factory=list)


@dataclass
class DepartmentReport:
    """Summary report for a department."""

    name: str
    status: str  # HEALTHY, WARNING, CRITICAL
    checks_run: int
    issues_found: int
    critical_count: int
    error_count: int
    warning_count: int
    duration_ms: float
    findings: List[DiagnosticFinding] = field(default_factory=list)


@dataclass
class HospitalReport:
    """Complete hospital diagnostic report."""

    timestamp: str
    project_root: str
    total_files: int
    total_lines: int
    total_functions: int
    total_classes: int
    overall_health: str
    departments: Dict[str, DepartmentReport] = field(default_factory=dict)
    file_health: Dict[str, FileHealth] = field(default_factory=dict)
    duration_seconds: float = 0.0


# =============================================================================
# CONSOLE OUTPUT UTILITIES
# =============================================================================


class Console:
    """Clinical console output with severity-based formatting."""

    COLORS = {
        "CRITICAL": "\033[91m\033[1m",  # Bold Red
        "ERROR": "\033[91m",  # Red
        "WARNING": "\033[93m",  # Yellow
        "INFO": "\033[94m",  # Blue
        "DEBUG": "\033[90m",  # Gray
        "HEALTHY": "\033[92m",  # Green
        "RESET": "\033[0m",
        "BOLD": "\033[1m",
        "HEADER": "\033[95m\033[1m",  # Bold Magenta
        "DEPT": "\033[96m\033[1m",  # Bold Cyan
    }

    @staticmethod
    def header(text: str):
        """Print a major section header."""
        width = 80
        print("\n" + Console.COLORS["HEADER"] + "=" * width)
        print(text.center(width))
        print("=" * width + Console.COLORS["RESET"] + "\n")

    @staticmethod
    def department(name: str, status: str):
        """Print a department header."""
        icon = {"HEALTHY": "[+]", "WARNING": "[!]", "CRITICAL": "[X]"}.get(status, "[?]")
        reset = Console.COLORS["RESET"]
        print(f"\n{Console.COLORS['DEPT']}{'='*60}")
        print(f"  {icon} DEPARTMENT: {name}")
        print(f"{'='*60}{reset}")

    @staticmethod
    def finding(f: DiagnosticFinding, verbose: bool = False):
        """Print a single finding."""
        color = Console.COLORS.get(f.severity, Console.COLORS["INFO"])
        reset = Console.COLORS["RESET"]

        # Severity badge
        badge = f"[{f.severity}]"

        # Location
        loc = f.file_path
        if f.line_number:
            loc += f":{f.line_number}"

        print(f"{color}{badge:12}{reset} {loc}")
        print(f"             {f.message}")

        if f.suggestion and verbose:
            print(f"             {Console.COLORS['DEBUG']}Suggestion: {f.suggestion}{reset}")

        if f.code_snippet and verbose:
            print(f"             {Console.COLORS['DEBUG']}>>> {f.code_snippet[:60]}...{reset}")

    @staticmethod
    def stats(label: str, value: Any, status: str = "INFO"):
        """Print a stat line."""
        color = Console.COLORS.get(status, Console.COLORS["INFO"])
        reset = Console.COLORS["RESET"]
        print(f"  {color}{label:<40}{reset}: {value}")

    @staticmethod
    def progress(current: int, total: int, prefix: str = ""):
        """Print a progress indicator."""
        pct = (current / total * 100) if total > 0 else 0
        bar_len = 30
        filled = int(bar_len * current / total) if total > 0 else 0
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"\r  {prefix} [{bar}] {pct:5.1f}% ({current}/{total})", end="", flush=True)


# =============================================================================
# GOLIATH HOSPITAL - MAIN CLASS
# =============================================================================


class GoliathHospital:
    """
    The Goliath Hospital Diagnostic System.

    A comprehensive, multi-department diagnostic authority for the
    Macena CS2 Analyzer project. Each department specializes in
    different aspects of project health.
    """

    def __init__(self, target_dir: Path = None, verbose: bool = True):
        self.target_dir = Path(target_dir) if target_dir else SOURCE_ROOT
        self.project_root = PROJECT_ROOT
        self.verbose = verbose
        self.start_time = None

        # Initialize report
        self.report = HospitalReport(
            timestamp=datetime.now().isoformat(),
            project_root=str(self.project_root),
            total_files=0,
            total_lines=0,
            total_functions=0,
            total_classes=0,
            overall_health="PENDING",
        )

        # File cache for cross-department analysis
        self._file_cache: Dict[str, str] = {}
        self._ast_cache: Dict[str, ast.AST] = {}

    # =========================================================================
    # TIMEOUT GUARD (cross-platform, thread-safe)
    # =========================================================================

    def _timeout_guard(self, func, timeout_sec=15, label="check"):
        """Run func in a worker thread with a hard timeout.

        Uses ThreadPoolExecutor (imported at module level but previously unused).
        Each callable must create its own DB sessions — SQLite connections are
        not shareable across threads.

        Returns:
            (True, result)            on success
            (False, error_string)     on timeout or exception
        """
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func)
            try:
                return True, future.result(timeout=timeout_sec)
            except FuturesTimeoutError:
                return False, f"{label} timed out after {timeout_sec}s"
            except Exception as e:
                return False, str(e)

    # =========================================================================
    # MAIN ENTRY POINT
    # =========================================================================

    def run_full_diagnostic(self) -> HospitalReport:
        """Run complete hospital diagnostic across all departments."""
        self.start_time = time.time()

        # Global watchdog: abort if full diagnostic exceeds 120s
        def _watchdog(max_seconds=120):
            import time as _t

            _t.sleep(max_seconds)
            msg = f"FATAL: Goliath Hospital exceeded {max_seconds}s timeout. Aborting with os._exit(3)."
            print(f"\n{msg}")
            # T10-H2: Log to stderr before hard exit so the abort is diagnosable
            print(msg, file=sys.stderr)
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(3)

        _wd = threading.Thread(target=_watchdog, args=(120,), daemon=True)
        _wd.start()

        Console.header("GOLIATH HOSPITAL DIAGNOSTIC SYSTEM v2.1")

        print(f"  Target Directory: {self.target_dir}")
        print(f"  Project Root:     {self.project_root}")
        print(f"  Scan Started:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Phase 1: File Discovery & Caching
        self._discover_files()

        # Phase 2: Run All Departments
        departments = [
            ("ER", self._run_emergency_room),
            ("RADIOLOGY", self._run_radiology),
            ("PATHOLOGY", self._run_pathology),
            ("CARDIOLOGY", self._run_cardiology),
            ("NEUROLOGY", self._run_neurology),
            ("ONCOLOGY", self._run_oncology),
            ("PEDIATRICS", self._run_pediatrics),
            ("ICU", self._run_icu),
            ("PHARMACY", self._run_pharmacy),
            ("TOOL_CLINIC", self._run_tool_clinic),
            ("ENDOCRINOLOGY", self._run_endocrinology),
        ]

        for dept_key, dept_func in departments:
            try:
                dept_func()
            except Exception as e:
                self._add_department_error(dept_key, str(e))

        # Phase 3: Calculate Overall Health
        self._calculate_overall_health()

        # Phase 4: Generate Final Report
        self.report.duration_seconds = time.time() - self.start_time
        self._print_final_report()

        # Phase 5: Export Reports
        self._export_json_report()

        return self.report

    # =========================================================================
    # SINGLE-DEPARTMENT ENTRY POINT
    # =========================================================================

    _DEPT_MAP_KEYS = None  # populated lazily

    def _get_dept_map(self):
        return {
            "ER": self._run_emergency_room,
            "RADIOLOGY": self._run_radiology,
            "PATHOLOGY": self._run_pathology,
            "CARDIOLOGY": self._run_cardiology,
            "NEUROLOGY": self._run_neurology,
            "ONCOLOGY": self._run_oncology,
            "PEDIATRICS": self._run_pediatrics,
            "ICU": self._run_icu,
            "PHARMACY": self._run_pharmacy,
            "TOOL_CLINIC": self._run_tool_clinic,
            "ENDOCRINOLOGY": self._run_endocrinology,
        }

    def run_single_department(self, dept_key: str) -> HospitalReport:
        """Run a single department diagnostic."""
        self.start_time = time.time()
        Console.header(f"GOLIATH HOSPITAL - DEPARTMENT: {dept_key}")

        print(f"  Target Directory: {self.target_dir}")
        print(f"  Project Root:     {self.project_root}")
        print()

        # File discovery is required for all departments
        self._discover_files()

        dept_map = self._get_dept_map()
        func = dept_map.get(dept_key)
        if func is None:
            print(f"  ERROR: Unknown department '{dept_key}'")
            sys.exit(1)

        try:
            func()
        except Exception as e:
            self._add_department_error(dept_key, str(e))

        self._calculate_overall_health()
        self.report.duration_seconds = time.time() - self.start_time
        self._print_final_report()
        self._export_json_report()
        return self.report

    # =========================================================================
    # FILE DISCOVERY
    # =========================================================================

    def _discover_files(self):
        """Discover and cache all Python files for analysis."""
        Console.header("PHASE 1: FILE DISCOVERY & CACHING")

        py_files = []
        for root, dirs, files in os.walk(self.target_dir):
            # Filter excluded directories
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

            for file in files:
                if file.endswith(".py"):
                    py_files.append(Path(root) / file)

        total = len(py_files)
        print(f"  Found {total} Python files to analyze\n")

        for i, fp in enumerate(py_files):
            if self.verbose:
                Console.progress(i + 1, total, "Caching files")

            try:
                content = fp.read_text(encoding="utf-8")
                rel_path = str(fp.relative_to(self.project_root))
                self._file_cache[rel_path] = content

                # Cache AST
                try:
                    self._ast_cache[rel_path] = ast.parse(content)
                except SyntaxError:
                    pass  # Will be caught by ER

                # Build file health
                self._build_file_health(rel_path, content, fp)

            except Exception as e:
                self._add_finding(
                    Department.ER,
                    Severity.ERROR,
                    "FILE_READ_ERROR",
                    str(fp),
                    None,
                    f"Cannot read file: {e}",
                )

        print("\n")
        self.report.total_files = len(self._file_cache)
        Console.stats("Total Python Files", self.report.total_files, "HEALTHY")
        Console.stats("Total Lines of Code", self.report.total_lines, "INFO")
        Console.stats("Total Functions", self.report.total_functions, "INFO")
        Console.stats("Total Classes", self.report.total_classes, "INFO")

    def _build_file_health(self, rel_path: str, content: str, fp: Path):
        """Build health metrics for a single file."""
        lines = content.splitlines()
        stat = fp.stat()

        # Count structures
        func_count = 0
        class_count = 0
        import_count = 0
        has_docstring = False

        if rel_path in self._ast_cache:
            tree = self._ast_cache[rel_path]
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    func_count += 1
                elif isinstance(node, ast.ClassDef):
                    class_count += 1
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    import_count += 1

            # Check for module docstring
            if (
                tree.body
                and isinstance(tree.body[0], ast.Expr)
                and isinstance(tree.body[0].value, ast.Constant)
                and isinstance(tree.body[0].value.value, str)
            ):
                has_docstring = True

        # Complexity score (simple heuristic)
        complexity = len(lines) * 0.01 + func_count * 0.5 + class_count * 1.0 + import_count * 0.1

        health = FileHealth(
            path=rel_path,
            size_bytes=stat.st_size,
            line_count=len(lines),
            function_count=func_count,
            class_count=class_count,
            import_count=import_count,
            complexity_score=round(complexity, 2),
            last_modified=datetime.fromtimestamp(stat.st_mtime).isoformat(),
            has_docstring=has_docstring,
        )

        self.report.file_health[rel_path] = health
        self.report.total_lines += len(lines)
        self.report.total_functions += func_count
        self.report.total_classes += class_count

    # =========================================================================
    # DEPARTMENT: EMERGENCY ROOM (ER)
    # =========================================================================

    def _run_emergency_room(self):
        """
        Emergency Room: Critical syntax and import issues.
        These are show-stoppers that prevent code from running.
        """
        start = time.time()
        dept = Department.ER
        findings = []

        Console.department("EMERGENCY ROOM", "PENDING")
        print("  Checking for critical syntax errors, broken imports, and fatal issues...")

        for rel_path, content in self._file_cache.items():
            # 1. Syntax Check
            if rel_path not in self._ast_cache:
                try:
                    ast.parse(content)
                except SyntaxError as e:
                    findings.append(
                        self._create_finding(
                            dept,
                            Severity.CRITICAL,
                            "SYNTAX_ERROR",
                            rel_path,
                            e.lineno,
                            f"Syntax error: {e.msg}",
                            "Fix the syntax error to allow code execution",
                        )
                    )

            # 2. Forbidden Path Detection (skip Goliath itself)
            if "Goliath_Hospital.py" not in rel_path:
                for pattern in FORBIDDEN_PATTERNS:
                    for i, line in enumerate(content.splitlines(), 1):
                        if re.search(pattern, line, re.IGNORECASE):
                            findings.append(
                                self._create_finding(
                                    dept,
                                    Severity.ERROR,
                                    "FORBIDDEN_PATTERN",
                                    rel_path,
                                    i,
                                    f"Potentially sensitive pattern detected: {pattern[:30]}...",
                                    "Remove or externalize sensitive data",
                                    line.strip()[:80],
                                )
                            )

            # 3. Critical Import Issues
            self._check_critical_imports(rel_path, content, findings)

        self._finalize_department(dept, findings, time.time() - start)

    def _check_critical_imports(self, rel_path: str, content: str, findings: List):
        """Check for broken or problematic imports."""
        for i, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()

            # Direct imports that should use full path
            if (
                stripped.startswith("from backend")
                or stripped.startswith("from core")
                or stripped.startswith("from ingestion")
            ):
                if "Programma_CS2_RENAN" not in stripped:
                    findings.append(
                        self._create_finding(
                            Department.ER,
                            Severity.ERROR,
                            "NAMESPACE_COLLISION",
                            rel_path,
                            i,
                            f"Direct import without package prefix: {stripped[:50]}",
                            "Use 'from Programma_CS2_RENAN.backend...' instead",
                            stripped,
                        )
                    )

    # =========================================================================
    # DEPARTMENT: RADIOLOGY
    # =========================================================================

    def _run_radiology(self):
        """
        Radiology: Visual asset integrity scans.
        Checks images, themes, maps, and static resources.
        """
        start = time.time()
        dept = Department.RADIOLOGY
        findings = []

        Console.department("RADIOLOGY", "PENDING")
        print("  Scanning visual assets, themes, and static resources...")

        # 1. Check PHOTO_GUI structure
        photo_gui = self.target_dir / "PHOTO_GUI"
        if photo_gui.exists():
            # Theme directories
            themes = ["cs2theme", "csgotheme", "cs16theme"]
            for theme in themes:
                theme_dir = photo_gui / theme
                if not theme_dir.exists():
                    findings.append(
                        self._create_finding(
                            dept,
                            Severity.WARNING,
                            "MISSING_THEME",
                            str(theme_dir.relative_to(self.project_root)),
                            None,
                            f"Theme directory '{theme}' not found",
                        )
                    )
                else:
                    assets = list(theme_dir.glob("*"))
                    if len(assets) < 5:
                        findings.append(
                            self._create_finding(
                                dept,
                                Severity.WARNING,
                                "SPARSE_THEME",
                                str(theme_dir.relative_to(self.project_root)),
                                None,
                                f"Theme '{theme}' has only {len(assets)} assets (expected 5+)",
                            )
                        )
                    else:
                        findings.append(
                            self._create_finding(
                                dept,
                                Severity.HEALTHY,
                                "THEME_OK",
                                str(theme_dir.relative_to(self.project_root)),
                                None,
                                f"Theme '{theme}' has {len(assets)} assets",
                            )
                        )

            # Map radars
            maps_dir = photo_gui / "maps"
            if maps_dir.exists():
                map_files = list(maps_dir.glob("*.png")) + list(maps_dir.glob("*.jpg"))
                required_maps = [
                    "de_dust2",
                    "de_mirage",
                    "de_inferno",
                    "de_nuke",
                    "de_ancient",
                    "de_anubis",
                    "de_vertigo",
                ]
                for map_name in required_maps:
                    found = any(map_name in f.stem for f in map_files)
                    if not found:
                        findings.append(
                            self._create_finding(
                                dept,
                                Severity.WARNING,
                                "MISSING_MAP_RADAR",
                                str(maps_dir.relative_to(self.project_root)),
                                None,
                                f"Map radar for '{map_name}' not found",
                            )
                        )

                findings.append(
                    self._create_finding(
                        dept,
                        Severity.INFO,
                        "MAP_RADAR_COUNT",
                        str(maps_dir.relative_to(self.project_root)),
                        None,
                        f"Found {len(map_files)} map radar images",
                    )
                )
            else:
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.ERROR,
                        "MISSING_MAPS_DIR",
                        "PHOTO_GUI/maps",
                        None,
                        "Maps directory not found - tactical viewer will fail",
                    )
                )
        else:
            findings.append(
                self._create_finding(
                    dept,
                    Severity.CRITICAL,
                    "MISSING_PHOTO_GUI",
                    "PHOTO_GUI",
                    None,
                    "PHOTO_GUI directory not found - UI assets missing",
                )
            )

        # 2. Check models directory
        models_dir = self.target_dir / "models"
        if models_dir.exists():
            pt_files = list(models_dir.rglob("*.pt"))
            onnx_files = list(models_dir.rglob("*.onnx"))
            findings.append(
                self._create_finding(
                    dept,
                    Severity.INFO,
                    "MODEL_ARTIFACTS",
                    str(models_dir.relative_to(self.project_root)),
                    None,
                    f"Found {len(pt_files)} PyTorch models, {len(onnx_files)} ONNX models",
                )
            )

        # 3. Check layout.kv
        layout_kv = self.target_dir / "apps" / "desktop_app" / "layout.kv"
        if layout_kv.exists():
            kv_content = layout_kv.read_text(encoding="utf-8")
            kv_lines = len(kv_content.splitlines())
            findings.append(
                self._create_finding(
                    dept,
                    Severity.HEALTHY,
                    "LAYOUT_KV",
                    str(layout_kv.relative_to(self.project_root)),
                    None,
                    f"KivyMD layout found ({kv_lines} lines)",
                )
            )
        else:
            findings.append(
                self._create_finding(
                    dept,
                    Severity.ERROR,
                    "MISSING_LAYOUT",
                    "apps/desktop_app/layout.kv",
                    None,
                    "KivyMD layout file not found - UI will not render",
                )
            )

        self._finalize_department(dept, findings, time.time() - start)

    # =========================================================================
    # DEPARTMENT: PATHOLOGY LAB
    # =========================================================================

    def _run_pathology(self):
        """
        Pathology Lab: Data quality analysis.
        Detects mock data, placeholders, and validates real-world expectations.
        """
        start = time.time()
        dept = Department.PATHOLOGY
        findings = []

        Console.department("PATHOLOGY LAB", "PENDING")
        print("  Analyzing data quality, detecting mock data and placeholders...")

        mock_locations = defaultdict(list)
        real_data_files = []

        for rel_path, content in self._file_cache.items():
            file_has_mock = False
            content_lower = content.lower()

            for indicator in MOCK_DATA_INDICATORS:
                if indicator.lower() in content_lower:
                    # Find specific lines
                    for i, line in enumerate(content.splitlines(), 1):
                        if indicator.lower() in line.lower():
                            # Skip if it's in a comment about detecting mock data
                            if "MOCK_DATA_INDICATORS" in line:
                                continue
                            mock_locations[rel_path].append((i, indicator, line.strip()[:60]))
                            file_has_mock = True

            if not file_has_mock:
                real_data_files.append(rel_path)

        # Report mock data findings
        for rel_path, locations in mock_locations.items():
            if len(locations) > 5:
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.WARNING,
                        "MOCK_DATA_HEAVY",
                        rel_path,
                        None,
                        f"File contains {len(locations)} mock/placeholder indicators",
                        "Review and replace with real data or mark as test file",
                    )
                )
            else:
                for line_no, indicator, snippet in locations[:3]:
                    findings.append(
                        self._create_finding(
                            dept,
                            Severity.INFO,
                            "MOCK_DATA_DETECTED",
                            rel_path,
                            line_no,
                            f"Mock indicator '{indicator}' found",
                            None,
                            snippet,
                        )
                    )

        # Summary
        findings.append(
            self._create_finding(
                dept,
                Severity.INFO,
                "DATA_QUALITY_SUMMARY",
                "PROJECT",
                None,
                f"Files with mock data: {len(mock_locations)}, Clean files: {len(real_data_files)}",
            )
        )

        # Check database for real vs test data
        self._check_database_data_quality(findings)

        self._finalize_department(dept, findings, time.time() - start)

    def _check_database_data_quality(self, findings: List):
        """Check database tables for real vs test data (timeout-guarded)."""

        def _query_db():
            from sqlmodel import func, select

            from Programma_CS2_RENAN.backend.storage.database import get_db_manager
            from Programma_CS2_RENAN.backend.storage.db_models import (
                PlayerMatchStats,
            )

            db = get_db_manager()
            with db.get_session() as session:
                stats_count = session.exec(select(func.count(PlayerMatchStats.id))).one()
                test_entries = session.exec(
                    select(func.count(PlayerMatchStats.id)).where(
                        PlayerMatchStats.player_name.like("%test%")
                        | PlayerMatchStats.player_name.like("%mock%")
                        | PlayerMatchStats.player_name.like("%MCIV%")
                    )
                ).one()
            return stats_count, test_entries

        ok, result = self._timeout_guard(_query_db, timeout_sec=20, label="DB data quality")
        if ok:
            stats_count, test_entries = result
            if test_entries > 0:
                findings.append(
                    self._create_finding(
                        Department.PATHOLOGY,
                        Severity.WARNING,
                        "TEST_DATA_IN_DB",
                        "DATABASE",
                        None,
                        f"Found {test_entries}/{stats_count} test/mock entries in PlayerMatchStats",
                        "Run cleanup to remove test data before production",
                    )
                )
            else:
                findings.append(
                    self._create_finding(
                        Department.PATHOLOGY,
                        Severity.HEALTHY,
                        "DB_DATA_CLEAN",
                        "DATABASE",
                        None,
                        f"Database has {stats_count} entries, no obvious test data",
                    )
                )
        else:
            findings.append(
                self._create_finding(
                    Department.PATHOLOGY,
                    Severity.INFO,
                    "DB_CHECK_SKIPPED",
                    "DATABASE",
                    None,
                    f"Could not check database: {result}",
                )
            )

    # =========================================================================
    # DEPARTMENT: CARDIOLOGY
    # =========================================================================

    def _run_cardiology(self):
        """
        Cardiology: Core module health.
        Checks database, configuration, and essential services.
        """
        start = time.time()
        dept = Department.CARDIOLOGY
        findings = []

        Console.department("CARDIOLOGY", "PENDING")
        print("  Checking core module health: database, config, essential services...")

        # 1. Check critical modules exist
        for module_path in CRITICAL_MODULES:
            full_path = self.project_root / module_path
            if full_path.exists():
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.HEALTHY,
                        "CRITICAL_MODULE_OK",
                        module_path,
                        None,
                        f"Critical module exists",
                    )
                )
            else:
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.CRITICAL,
                        "MISSING_CRITICAL_MODULE",
                        module_path,
                        None,
                        f"Critical module missing - system will fail",
                    )
                )

        # 2. Check database connection (timeout-guarded)
        def _check_db_conn():
            from sqlalchemy import text

            from Programma_CS2_RENAN.backend.storage.database import get_db_manager

            db = get_db_manager()
            with db.get_session() as s:
                s.execute(text("SELECT 1"))
            return True

        ok, result = self._timeout_guard(_check_db_conn, timeout_sec=10, label="DB connection")
        if ok:
            findings.append(
                self._create_finding(
                    dept,
                    Severity.HEALTHY,
                    "DATABASE_CONNECTION",
                    "backend/storage/database.py",
                    None,
                    "Database connection successful",
                )
            )
        else:
            findings.append(
                self._create_finding(
                    dept,
                    Severity.ERROR,
                    "DATABASE_ERROR",
                    "backend/storage/database.py",
                    None,
                    f"Database connection failed: {result}",
                )
            )

        # 3. Check configuration loading
        try:
            from Programma_CS2_RENAN.core.config import get_setting

            theme = get_setting("THEME", default="cs2theme")
            findings.append(
                self._create_finding(
                    dept,
                    Severity.HEALTHY,
                    "CONFIG_LOAD",
                    "core/config.py",
                    None,
                    f"Configuration loads successfully (THEME={theme})",
                )
            )
        except Exception as e:
            findings.append(
                self._create_finding(
                    dept,
                    Severity.ERROR,
                    "CONFIG_ERROR",
                    "core/config.py",
                    None,
                    f"Configuration failed to load: {e}",
                )
            )

        # 4. Check settings.json
        settings_path = self.target_dir / "settings.json"
        if settings_path.exists():
            try:
                settings = json.loads(settings_path.read_text(encoding="utf-8"))
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.HEALTHY,
                        "SETTINGS_JSON",
                        "settings.json",
                        None,
                        f"Settings file valid with {len(settings)} keys",
                    )
                )
            except json.JSONDecodeError as e:
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.ERROR,
                        "SETTINGS_INVALID",
                        "settings.json",
                        None,
                        f"Settings file has invalid JSON: {e}",
                    )
                )
        else:
            findings.append(
                self._create_finding(
                    dept,
                    Severity.WARNING,
                    "SETTINGS_MISSING",
                    "settings.json",
                    None,
                    "Settings file not found, using defaults",
                )
            )

        # 5. Check Temporal Baseline Decay health (timeout-guarded)
        def _check_baseline():
            from Programma_CS2_RENAN.backend.processing.baselines.pro_baseline import (
                TemporalBaselineDecay,
            )

            decay = TemporalBaselineDecay()
            ref = datetime.now()
            return decay.compute_weight(ref - timedelta(days=45), ref)

        ok, result = self._timeout_guard(_check_baseline, timeout_sec=10, label="TemporalBaseline")
        if ok:
            w = result
            if 0.1 <= w <= 1.0:
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.HEALTHY,
                        "TEMPORAL_BASELINE_OK",
                        "backend/processing/baselines/pro_baseline.py",
                        None,
                        f"TemporalBaselineDecay operational (45-day weight: {w:.3f})",
                    )
                )
            else:
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.ERROR,
                        "TEMPORAL_BASELINE_RANGE",
                        "backend/processing/baselines/pro_baseline.py",
                        None,
                        f"TemporalBaselineDecay compute_weight out of range: {w}",
                    )
                )
        else:
            findings.append(
                self._create_finding(
                    dept,
                    Severity.WARNING,
                    "TEMPORAL_BASELINE_ERROR",
                    "backend/processing/baselines/pro_baseline.py",
                    None,
                    f"TemporalBaselineDecay check failed: {result}",
                )
            )

        # 6. Analysis Engine Factory Smoke Test
        try:
            from Programma_CS2_RENAN.backend.analysis import (
                get_blind_spot_detector,
                get_death_estimator,
                get_deception_analyzer,
                get_economy_optimizer,
                get_engagement_range_analyzer,
                get_entropy_analyzer,
                get_game_tree_search,
                get_momentum_tracker,
                get_role_classifier,
                get_utility_analyzer,
                get_win_predictor,
            )

            factory_funcs = [
                ("get_win_predictor", get_win_predictor),
                ("get_role_classifier", get_role_classifier),
                ("get_death_estimator", get_death_estimator),
                ("get_deception_analyzer", get_deception_analyzer),
                ("get_momentum_tracker", get_momentum_tracker),
                ("get_entropy_analyzer", get_entropy_analyzer),
                ("get_game_tree_search", get_game_tree_search),
                ("get_blind_spot_detector", get_blind_spot_detector),
                ("get_engagement_range_analyzer", get_engagement_range_analyzer),
                ("get_utility_analyzer", get_utility_analyzer),
                ("get_economy_optimizer", get_economy_optimizer),
            ]

            ok_count = 0
            for name, func in factory_funcs:
                try:
                    obj = func()
                    if obj is not None:
                        ok_count += 1
                except Exception:
                    findings.append(
                        self._create_finding(
                            dept,
                            Severity.WARNING,
                            "ANALYSIS_FACTORY_FAIL",
                            "backend/analysis/__init__.py",
                            None,
                            f"Analysis factory {name}() raised an exception",
                        )
                    )

            findings.append(
                self._create_finding(
                    dept,
                    Severity.HEALTHY if ok_count == len(factory_funcs) else Severity.WARNING,
                    "ANALYSIS_FACTORIES",
                    "backend/analysis/__init__.py",
                    None,
                    f"Analysis factories: {ok_count}/{len(factory_funcs)} operational",
                )
            )
        except Exception as e:
            findings.append(
                self._create_finding(
                    dept,
                    Severity.WARNING,
                    "ANALYSIS_IMPORT_FAIL",
                    "backend/analysis/__init__.py",
                    None,
                    f"Analysis package import failed: {e}",
                )
            )

        # 7. ResourceManager health
        try:
            from Programma_CS2_RENAN.backend.ingestion.resource_manager import ResourceManager

            stats = ResourceManager.get_system_stats()
            if isinstance(stats, dict) and "cpu" in stats:
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.HEALTHY,
                        "RESOURCE_MANAGER_OK",
                        "backend/ingestion/resource_manager.py",
                        None,
                        f"ResourceManager operational (CPU: {stats.get('cpu', 'N/A'):.1f}%)",
                    )
                )
            else:
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.WARNING,
                        "RESOURCE_MANAGER_FORMAT",
                        "backend/ingestion/resource_manager.py",
                        None,
                        "ResourceManager.get_system_stats() returned unexpected format",
                    )
                )

            throttle = ResourceManager.should_throttle()
            if isinstance(throttle, bool):
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.HEALTHY,
                        "THROTTLE_CHECK_OK",
                        "backend/ingestion/resource_manager.py",
                        None,
                        f"should_throttle() = {throttle}",
                    )
                )
        except Exception as e:
            findings.append(
                self._create_finding(
                    dept,
                    Severity.INFO,
                    "RESOURCE_MANAGER_SKIP",
                    "backend/ingestion/resource_manager.py",
                    None,
                    f"ResourceManager check failed: {e}",
                )
            )

        # 8. Observability subsystem
        try:
            import logging

            from Programma_CS2_RENAN.observability.logger_setup import get_logger as _get_logger

            test_logger = _get_logger("cs2analyzer.goliath_test")
            if isinstance(test_logger, logging.Logger):
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.HEALTHY,
                        "OBSERVABILITY_OK",
                        "observability/logger_setup.py",
                        None,
                        "get_logger() returns valid Logger instance",
                    )
                )
            else:
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.WARNING,
                        "OBSERVABILITY_TYPE",
                        "observability/logger_setup.py",
                        None,
                        f"get_logger() returned {type(test_logger).__name__}, expected Logger",
                    )
                )
        except Exception as e:
            findings.append(
                self._create_finding(
                    dept,
                    Severity.WARNING,
                    "OBSERVABILITY_FAIL",
                    "observability/logger_setup.py",
                    None,
                    f"Observability check failed: {e}",
                )
            )

        for obs_file in ["logger_setup.py", "rasp.py", "sentry_setup.py"]:
            obs_path = self.target_dir / "observability" / obs_file
            if obs_path.exists():
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.HEALTHY,
                        "OBS_FILE_OK",
                        f"observability/{obs_file}",
                        None,
                        "Observability module exists",
                    )
                )
            else:
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.WARNING,
                        "OBS_FILE_MISSING",
                        f"observability/{obs_file}",
                        None,
                        "Observability module missing",
                    )
                )

        # 9. Control layer existence
        for ctrl_file in ["console.py", "db_governor.py", "ingest_manager.py", "ml_controller.py"]:
            ctrl_path = self.target_dir / "backend" / "control" / ctrl_file
            if ctrl_path.exists():
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.HEALTHY,
                        "CONTROL_MODULE_OK",
                        f"backend/control/{ctrl_file}",
                        None,
                        "Control module exists",
                    )
                )
            else:
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.ERROR,
                        "CONTROL_MODULE_MISSING",
                        f"backend/control/{ctrl_file}",
                        None,
                        "Control module missing",
                    )
                )

        self._finalize_department(dept, findings, time.time() - start)

    # =========================================================================
    # DEPARTMENT: NEUROLOGY
    # =========================================================================

    def _run_neurology(self):
        """
        Neurology: ML/AI system integrity.
        Checks neural network models, training pipelines, and inference.
        """
        start = time.time()
        dept = Department.NEUROLOGY
        findings = []

        Console.department("NEUROLOGY", "PENDING")
        print("  Scanning ML/AI systems: models, training, inference pipelines...")

        # 1. Check model files
        models_dir = self.target_dir / "models"
        if models_dir.exists():
            pt_files = list(models_dir.rglob("*.pt"))
            for pt_file in pt_files:
                size_mb = pt_file.stat().st_size / (1024 * 1024)
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.INFO,
                        "MODEL_FILE",
                        str(pt_file.relative_to(self.project_root)),
                        None,
                        f"Model artifact: {pt_file.name} ({size_mb:.2f} MB)",
                    )
                )

        # 2. Check PyTorch availability (timeout-guarded)
        def _check_pytorch():
            import torch

            cuda = "CUDA available" if torch.cuda.is_available() else "CPU only"
            return torch.__version__, cuda

        ok, result = self._timeout_guard(_check_pytorch, timeout_sec=15, label="PyTorch import")
        if ok:
            version, cuda = result
            findings.append(
                self._create_finding(
                    dept,
                    Severity.HEALTHY,
                    "PYTORCH_OK",
                    "ENVIRONMENT",
                    None,
                    f"PyTorch {version} ({cuda})",
                )
            )
        else:
            findings.append(
                self._create_finding(
                    dept,
                    Severity.CRITICAL,
                    "PYTORCH_MISSING",
                    "ENVIRONMENT",
                    None,
                    f"PyTorch check failed: {result}",
                )
            )

        # 3. Check model instantiation (timeout-guarded)
        def _check_teacher_nn():
            import torch

            from Programma_CS2_RENAN.backend.nn.model import TeacherRefinementNN
            from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM

            model = TeacherRefinementNN(input_dim=METADATA_DIM, output_dim=4)
            dummy = torch.randn(1, 1, METADATA_DIM)
            with torch.no_grad():
                out = model(dummy)
            return str(out.shape)

        ok, result = self._timeout_guard(_check_teacher_nn, timeout_sec=15, label="TeacherRefinementNN")
        if ok:
            findings.append(
                self._create_finding(
                    dept,
                    Severity.HEALTHY,
                    "MODEL_INSTANTIATION",
                    "backend/nn/model.py",
                    None,
                    f"TeacherRefinementNN forward pass OK (output shape: {result})",
                )
            )
        else:
            findings.append(
                self._create_finding(
                    dept,
                    Severity.ERROR,
                    "MODEL_ERROR",
                    "backend/nn/model.py",
                    None,
                    f"Model instantiation failed: {result}",
                )
            )

        # 4. Check JEPA model (timeout-guarded)
        def _check_jepa():
            import torch

            from Programma_CS2_RENAN.backend.nn.jepa_model import JEPACoachingModel
            from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM

            jepa = JEPACoachingModel(input_dim=METADATA_DIM, output_dim=METADATA_DIM, latent_dim=128)
            x = torch.randn(1, 5, METADATA_DIM)
            with torch.no_grad():
                pred = jepa(x)
            return str(pred.shape)

        ok, result = self._timeout_guard(_check_jepa, timeout_sec=15, label="JEPA forward pass")
        if ok:
            findings.append(
                self._create_finding(
                    dept,
                    Severity.HEALTHY,
                    "JEPA_MODEL",
                    "backend/nn/jepa_model.py",
                    None,
                    f"JEPA model forward pass OK (output shape: {result})",
                )
            )
        else:
            findings.append(
                self._create_finding(
                    dept,
                    Severity.WARNING,
                    "JEPA_ERROR",
                    "backend/nn/jepa_model.py",
                    None,
                    f"JEPA model check failed: {result}",
                )
            )

        # 5. Check RAP Coach (LTC-Hopfield) — actual forward pass (timeout-guarded)
        def _check_rap():
            import torch

            from Programma_CS2_RENAN.backend.nn.rap_coach.model import RAPCoachModel
            from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM

            rap = RAPCoachModel()
            rap.eval()
            with torch.no_grad():
                view = torch.randn(1, 3, 64, 64)
                map_t = torch.randn(1, 3, 64, 64)
                motion = torch.randn(1, 3, 64, 64)
                meta = torch.randn(1, 5, METADATA_DIM)
                out = rap(view, map_t, motion, meta)
            keys = list(out.keys()) if isinstance(out, dict) else type(out).__name__
            return keys

        ok, result = self._timeout_guard(_check_rap, timeout_sec=15, label="RAP Coach forward pass")
        if ok:
            findings.append(
                self._create_finding(
                    dept,
                    Severity.HEALTHY,
                    "RAP_COACH",
                    "backend/nn/rap_coach/model.py",
                    None,
                    f"RAP Coach (LTC-Hopfield) forward pass OK (output keys: {result})",
                )
            )
        else:
            findings.append(
                self._create_finding(
                    dept,
                    Severity.WARNING,
                    "RAP_COACH_ERROR",
                    "backend/nn/rap_coach/model.py",
                    None,
                    f"RAP Coach forward pass failed: {result}",
                )
            )

        # 6. ModelFactory integration test (timeout-guarded)
        for model_type in ["default", "jepa"]:

            def _make_model(mt=model_type):
                import torch.nn as nn

                from Programma_CS2_RENAN.backend.nn.factory import ModelFactory

                m = ModelFactory.get_model(mt)
                return type(m).__name__, isinstance(m, nn.Module)

            ok, result = self._timeout_guard(
                _make_model, timeout_sec=15, label=f"ModelFactory({model_type})"
            )
            if ok:
                name, is_module = result
                if is_module:
                    findings.append(
                        self._create_finding(
                            dept,
                            Severity.HEALTHY,
                            "FACTORY_MODEL_OK",
                            "backend/nn/factory.py",
                            None,
                            f"ModelFactory.get_model('{model_type}') -> {name}",
                        )
                    )
                else:
                    findings.append(
                        self._create_finding(
                            dept,
                            Severity.WARNING,
                            "FACTORY_MODEL_TYPE",
                            "backend/nn/factory.py",
                            None,
                            f"ModelFactory('{model_type}') returned {name}, not nn.Module",
                        )
                    )
            else:
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.WARNING,
                        "FACTORY_MODEL_FAIL",
                        "backend/nn/factory.py",
                        None,
                        f"ModelFactory('{model_type}') failed: {result}",
                    )
                )

        # 7. METADATA_DIM cross-validation
        try:
            from Programma_CS2_RENAN.backend.nn.config import INPUT_DIM, OUTPUT_DIM
            from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM

            dim_checks = [
                ("METADATA_DIM (vectorizer)", METADATA_DIM, 25),
                ("INPUT_DIM (nn/config)", INPUT_DIM, METADATA_DIM),
                ("OUTPUT_DIM (nn/config)", OUTPUT_DIM, 10),
            ]
            all_aligned = True
            for name, actual, expected in dim_checks:
                if actual != expected:
                    all_aligned = False
                    findings.append(
                        self._create_finding(
                            dept,
                            Severity.ERROR,
                            "DIM_MISMATCH",
                            "backend/nn/config.py",
                            None,
                            f"{name} = {actual}, expected {expected}",
                        )
                    )

            if all_aligned:
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.HEALTHY,
                        "DIM_ALIGNMENT_OK",
                        "backend/nn/config.py",
                        None,
                        f"All dimensions aligned: METADATA_DIM={METADATA_DIM}, INPUT_DIM={INPUT_DIM}, OUTPUT_DIM={OUTPUT_DIM}",
                    )
                )

            # Also check TRAINING_FEATURES length
            try:
                from Programma_CS2_RENAN.backend.nn.coach_manager import TRAINING_FEATURES

                if len(TRAINING_FEATURES) == METADATA_DIM:
                    findings.append(
                        self._create_finding(
                            dept,
                            Severity.HEALTHY,
                            "TRAINING_FEATURES_OK",
                            "backend/nn/coach_manager.py",
                            None,
                            f"TRAINING_FEATURES length ({len(TRAINING_FEATURES)}) matches METADATA_DIM",
                        )
                    )
                else:
                    findings.append(
                        self._create_finding(
                            dept,
                            Severity.ERROR,
                            "TRAINING_FEATURES_MISMATCH",
                            "backend/nn/coach_manager.py",
                            None,
                            f"TRAINING_FEATURES length ({len(TRAINING_FEATURES)}) != METADATA_DIM ({METADATA_DIM})",
                        )
                    )
            except Exception as e:
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.WARNING,
                        "TRAINING_FEATURES_FAIL",
                        "backend/nn/coach_manager.py",
                        None,
                        f"TRAINING_FEATURES check failed: {e}",
                    )
                )
        except Exception as e:
            findings.append(
                self._create_finding(
                    dept,
                    Severity.WARNING,
                    "DIM_CHECK_FAIL",
                    "backend/nn/config.py",
                    None,
                    f"Dimension cross-validation failed: {e}",
                )
            )

        self._finalize_department(dept, findings, time.time() - start)

    # =========================================================================
    # DEPARTMENT: ONCOLOGY
    # =========================================================================

    def _run_oncology(self):
        """
        Oncology: Dead code, deprecated patterns, technical debt.
        Identifies code that needs to be removed or refactored.
        """
        start = time.time()
        dept = Department.ONCOLOGY
        findings = []

        Console.department("ONCOLOGY", "PENDING")
        print("  Scanning for dead code, deprecated patterns, and technical debt...")

        for rel_path, content in self._file_cache.items():
            lines = content.splitlines()

            # 1. Check for deprecated patterns
            for pattern, description in DEPRECATED_PATTERNS:
                for i, line in enumerate(lines, 1):
                    if re.search(pattern, line):
                        if "DEPRECATED_PATTERNS" not in line:  # Don't flag ourselves
                            findings.append(
                                self._create_finding(
                                    dept,
                                    Severity.WARNING,
                                    "DEPRECATED_PATTERN",
                                    rel_path,
                                    i,
                                    description,
                                    "Update to use the recommended approach",
                                    line.strip()[:60],
                                )
                            )

            # 2. Check for commented-out code blocks
            consecutive_comments = 0
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                # F8-15: Detect both `#def` and `# def` patterns (with or without space)
                if stripped.startswith("#") and re.match(
                    r"#\s*(def |class |import |from |if |for |while |return )", stripped
                ):
                    consecutive_comments += 1
                else:
                    if consecutive_comments >= 5:
                        findings.append(
                            self._create_finding(
                                dept,
                                Severity.INFO,
                                "COMMENTED_CODE_BLOCK",
                                rel_path,
                                i - consecutive_comments,
                                f"Large commented code block ({consecutive_comments} lines)",
                                "Consider removing or documenting why it's kept",
                            )
                        )
                    consecutive_comments = 0

            # 3. Check for unused imports (basic heuristic)
            if rel_path in self._ast_cache:
                self._check_unused_imports(rel_path, content, findings)

            # 4. Check for very long functions
            if rel_path in self._ast_cache:
                self._check_function_lengths(rel_path, findings)

        # 5. Check for orphan files (files not imported anywhere)
        self._check_orphan_files(findings)

        self._finalize_department(dept, findings, time.time() - start)

    def _check_unused_imports(self, rel_path: str, content: str, findings: List):
        """Basic check for potentially unused imports."""
        tree = self._ast_cache[rel_path]
        imports = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname if alias.asname else alias.name.split(".")[0]
                    imports.append((name, node.lineno))
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name != "*":
                        name = alias.asname if alias.asname else alias.name
                        imports.append((name, node.lineno))

        # Check if import is used (very basic)
        for name, lineno in imports:
            # Count occurrences after import
            pattern = r"\b" + re.escape(name) + r"\b"
            matches = re.findall(pattern, content)
            if len(matches) <= 1:  # Only the import itself
                findings.append(
                    self._create_finding(
                        Department.ONCOLOGY,
                        Severity.INFO,
                        "POTENTIALLY_UNUSED_IMPORT",
                        rel_path,
                        lineno,
                        f"Import '{name}' may be unused",
                        "Verify and remove if not needed",
                    )
                )

    # Files where long functions are expected by design (diagnostic departments,
    # tool scripts, test fixtures). Suppresses LONG_FUNCTION warnings for these.
    _ONCOLOGY_LENGTH_EXCLUSIONS = {
        "tools/Goliath_Hospital.py",
        "tools/Sanitize_Project.py",
        "tools/Feature_Audit.py",
        "tools/headless_validator.py",
        "tools/Ultimate_ML_Coach_Debugger.py",
        "tools/backend_validator.py",
        "tools/db_inspector.py",
        "tools/project_snapshot.py",
        "tests/conftest.py",
    }

    def _check_function_lengths(self, rel_path: str, findings: List):
        """Check for overly long functions."""
        if any(rel_path.endswith(exc) for exc in self._ONCOLOGY_LENGTH_EXCLUSIONS):
            return

        tree = self._ast_cache[rel_path]

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if hasattr(node, "end_lineno") and node.end_lineno:
                    length = node.end_lineno - node.lineno
                    if length > 100:
                        findings.append(
                            self._create_finding(
                                Department.ONCOLOGY,
                                Severity.WARNING,
                                "LONG_FUNCTION",
                                rel_path,
                                node.lineno,
                                f"Function '{node.name}' is {length} lines long",
                                "Consider breaking into smaller functions",
                            )
                        )
                    elif length > 50:
                        findings.append(
                            self._create_finding(
                                Department.ONCOLOGY,
                                Severity.INFO,
                                "MODERATELY_LONG_FUNCTION",
                                rel_path,
                                node.lineno,
                                f"Function '{node.name}' is {length} lines",
                            )
                        )

    def _check_orphan_files(self, findings: List):
        """Check for Python files that aren't imported anywhere."""
        # F8-06: Regex-based import scan matches "import" in comments and strings.
        # For accurate orphan detection use dead_code_detector.py (AST-based).
        # This department provides a heuristic estimate only.
        all_imports = set()

        # Collect all imports
        for rel_path, content in self._file_cache.items():
            for line in content.splitlines():
                if "import" in line:
                    # Extract module names
                    match = re.search(r"from\s+(\S+)\s+import|import\s+(\S+)", line)
                    if match:
                        module = match.group(1) or match.group(2)
                        all_imports.add(module.replace(".", "/"))

        # Check each file
        orphans = []
        for rel_path in self._file_cache.keys():
            if rel_path.endswith("__init__.py"):
                continue
            if "test" in rel_path.lower():
                continue
            if "/tools/" in rel_path or rel_path.startswith("tools/"):  # F8-22: match Programma_CS2_RENAN/tools/ and root tools/
                continue  # Tools are standalone

            # Convert path to import format
            module_path = rel_path.replace(".py", "").replace("\\", "/")

            # Check if imported
            is_imported = any(
                module_path.endswith(imp)
                or imp.endswith(module_path.split("/")[-1].replace(".py", ""))
                for imp in all_imports
            )

            if not is_imported:
                orphans.append(rel_path)

        if orphans:
            findings.append(
                self._create_finding(
                    Department.ONCOLOGY,
                    Severity.INFO,
                    "POTENTIAL_ORPHAN_FILES",
                    "PROJECT",
                    None,
                    f"Found {len(orphans)} potentially orphan files (not imported)",
                    "Review if these files are still needed",
                )
            )

    # =========================================================================
    # DEPARTMENT: PEDIATRICS
    # =========================================================================

    def _run_pediatrics(self):
        """
        Pediatrics: New and recently modified files.
        These need extra attention as they may introduce issues.
        """
        start = time.time()
        dept = Department.PEDIATRICS
        findings = []

        Console.department("PEDIATRICS", "PENDING")
        print("  Identifying recently modified files that need attention...")

        now = datetime.now(timezone.utc)  # F8-13/F8-37: timezone-aware UTC datetime
        recent_files = []
        new_files = []

        for rel_path, health in self.report.file_health.items():
            mod_time = datetime.fromisoformat(health.last_modified)
            if mod_time.tzinfo is None:
                mod_time = mod_time.replace(tzinfo=timezone.utc)
            age = now - mod_time

            if age < timedelta(days=1):
                new_files.append((rel_path, "< 1 day old"))
            elif age < timedelta(days=7):
                recent_files.append((rel_path, f"{age.days} days old"))

        # Report new files
        for rel_path, age_str in new_files:
            health = self.report.file_health[rel_path]
            findings.append(
                self._create_finding(
                    dept,
                    Severity.INFO,
                    "NEW_FILE",
                    rel_path,
                    None,
                    f"New file ({age_str}): {health.line_count} lines, {health.function_count} functions",
                    "Review recent changes for potential issues",
                )
            )

        # Report recently modified
        for rel_path, age_str in recent_files[:10]:  # Limit output
            findings.append(
                self._create_finding(
                    dept,
                    Severity.INFO,
                    "RECENT_CHANGE",
                    rel_path,
                    None,
                    f"Recently modified ({age_str})",
                )
            )

        # Summary
        findings.append(
            self._create_finding(
                dept,
                Severity.INFO,
                "PEDIATRICS_SUMMARY",
                "PROJECT",
                None,
                f"New files (< 1 day): {len(new_files)}, Recent (< 7 days): {len(recent_files)}",
            )
        )

        self._finalize_department(dept, findings, time.time() - start)

    # =========================================================================
    # DEPARTMENT: ICU
    # =========================================================================

    def _run_icu(self):
        """
        ICU: Integration tests and end-to-end flows.
        Validates that components work together correctly.
        """
        start = time.time()
        dept = Department.ICU
        findings = []

        Console.department("ICU", "PENDING")
        print("  Running integration checks and end-to-end flow validation...")

        # 1. Test import chain (24 verified chains covering all subsystems)
        import_tests = [
            # Core
            ("Core Config", "Programma_CS2_RENAN.core.config", "get_setting"),
            ("Map Manager", "Programma_CS2_RENAN.core.map_manager", "MapManager"),
            ("Asset Manager", "Programma_CS2_RENAN.core.asset_manager", "AssetAuthority"),
            ("Spatial Data", "Programma_CS2_RENAN.core.spatial_data", "get_map_metadata"),
            # Storage
            ("Database", "Programma_CS2_RENAN.backend.storage.database", "get_db_manager"),
            ("DB Models", "Programma_CS2_RENAN.backend.storage.db_models", "PlayerMatchStats"),
            ("Match Data Mgr", "Programma_CS2_RENAN.backend.storage.match_data_manager", "get_match_data_manager"),
            # Neural Networks
            ("Model Factory", "Programma_CS2_RENAN.backend.nn.factory", "ModelFactory"),
            ("NN Config", "Programma_CS2_RENAN.backend.nn.config", "get_device"),
            # Processing
            ("Feature Extractor", "Programma_CS2_RENAN.backend.processing.feature_engineering.vectorizer", "FeatureExtractor"),
            ("Tensor Factory", "Programma_CS2_RENAN.backend.processing.tensor_factory", "TensorFactory"),
            # Services
            ("Coaching Service", "Programma_CS2_RENAN.backend.services.coaching_service", "CoachingService"),
            ("Analysis Orchestrator", "Programma_CS2_RENAN.backend.services.analysis_orchestrator", "AnalysisOrchestrator"),
            # Coaching
            ("Hybrid Engine", "Programma_CS2_RENAN.backend.coaching.hybrid_engine", "HybridCoachingEngine"),
            # Knowledge
            ("Knowledge Graph", "Programma_CS2_RENAN.backend.knowledge.graph", "KnowledgeGraphManager"),
            ("Knowledge Retriever", "Programma_CS2_RENAN.backend.knowledge.rag_knowledge", "KnowledgeRetriever"),
            ("Experience Bank", "Programma_CS2_RENAN.backend.knowledge.experience_bank", "ExperienceBank"),
            # Analysis
            ("Role Classifier", "Programma_CS2_RENAN.backend.analysis.role_classifier", "RoleClassifier"),
            ("Win Probability", "Programma_CS2_RENAN.backend.analysis.win_probability", "WinProbabilityPredictor"),
            # Control
            ("Console", "Programma_CS2_RENAN.backend.control.console", "Console"),
            ("DB Governor", "Programma_CS2_RENAN.backend.control.db_governor", "DatabaseGovernor"),
            ("ML Controller", "Programma_CS2_RENAN.backend.control.ml_controller", "MLController"),
            ("Ingestion Manager", "Programma_CS2_RENAN.backend.control.ingest_manager", "IngestionManager"),
            # Observability
            ("Logger Setup", "Programma_CS2_RENAN.observability.logger_setup", "get_logger"),
        ]

        for name, module, attr in import_tests:
            try:
                mod = importlib.import_module(module)
                if hasattr(mod, attr):
                    findings.append(
                        self._create_finding(
                            dept,
                            Severity.HEALTHY,
                            "IMPORT_CHAIN_OK",
                            module.replace(".", "/") + ".py",
                            None,
                            f"{name}: {attr} importable",
                        )
                    )
                else:
                    findings.append(
                        self._create_finding(
                            dept,
                            Severity.ERROR,
                            "MISSING_ATTRIBUTE",
                            module.replace(".", "/") + ".py",
                            None,
                            f"{name}: {attr} not found in module",
                        )
                    )
            except Exception as e:
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.ERROR,
                        "IMPORT_CHAIN_FAIL",
                        module.replace(".", "/") + ".py",
                        None,
                        f"{name}: Import failed - {e}",
                    )
                )

        # 2. Test coaching service instantiation (timeout-guarded)
        def _check_coaching():
            from Programma_CS2_RENAN.backend.services.coaching_service import CoachingService

            _ = CoachingService()
            return True

        ok, result = self._timeout_guard(_check_coaching, timeout_sec=15, label="CoachingService")
        if ok:
            findings.append(
                self._create_finding(
                    dept,
                    Severity.HEALTHY,
                    "COACHING_SERVICE",
                    "backend/services/coaching_service.py",
                    None,
                    "CoachingService instantiation successful",
                )
            )
        else:
            findings.append(
                self._create_finding(
                    dept,
                    Severity.ERROR,
                    "COACHING_SERVICE_FAIL",
                    "backend/services/coaching_service.py",
                    None,
                    f"CoachingService failed: {result}",
                )
            )

        # 3. Test feature extraction with real DB data (timeout-guarded)
        def _check_feature_extraction():
            from sqlmodel import select

            from Programma_CS2_RENAN.backend.processing.feature_engineering.vectorizer import (
                FeatureExtractor,
            )
            from Programma_CS2_RENAN.backend.storage.database import get_db_manager
            from Programma_CS2_RENAN.backend.storage.db_models import PlayerMatchStats

            fe = FeatureExtractor()
            db = get_db_manager()
            with db.get_session() as session:
                real_record = session.exec(select(PlayerMatchStats).limit(1)).first()

            if real_record is None:
                return "skip", None

            real_stats = {
                attr: getattr(real_record, attr, 0)
                for attr in vars(real_record)
                if not attr.startswith("_")
                and isinstance(getattr(real_record, attr, None), (int, float))
            }
            vec = fe.extract(real_stats)
            return "ok", len(vec) if hasattr(vec, "__len__") else "N/A"

        ok, result = self._timeout_guard(
            _check_feature_extraction, timeout_sec=20, label="FeatureExtractor+DB"
        )
        if ok:
            status, dim = result
            if status == "skip":
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.WARNING,
                        "FEATURE_EXTRACTION_SKIP",
                        "backend/processing/feature_engineering/vectorizer.py",
                        None,
                        "FeatureExtractor test skipped — no real data in database",
                    )
                )
            else:
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.HEALTHY,
                        "FEATURE_EXTRACTION",
                        "backend/processing/feature_engineering/vectorizer.py",
                        None,
                        f"FeatureExtractor OK (output dim: {dim})",
                    )
                )
        else:
            findings.append(
                self._create_finding(
                    dept,
                    Severity.WARNING,
                    "FEATURE_EXTRACTION_FAIL",
                    "backend/processing/feature_engineering/vectorizer.py",
                    None,
                    f"Feature extraction test failed: {result}",
                )
            )

        self._finalize_department(dept, findings, time.time() - start)

    # =========================================================================
    # DEPARTMENT: PHARMACY
    # =========================================================================

    def _run_pharmacy(self):
        """
        Pharmacy: Dependency health and version checks.
        Validates that all required packages are installed and compatible.
        """
        start = time.time()
        dept = Department.PHARMACY
        findings = []

        Console.department("PHARMACY", "PENDING")
        print("  Checking dependency health and package versions...")

        # Critical dependencies
        # F8-29: hflayers is a root-level custom implementation (hflayers.py), not pip-installed.
        # Cannot check via importlib.import_module — Pharmacy verifies pip-installable deps only.
        critical_deps = [
            ("torch", "PyTorch"),
            ("sqlmodel", "SQLModel"),
            ("kivy", "Kivy"),
            ("kivymd", "KivyMD"),
            ("numpy", "NumPy"),
            ("pandas", "Pandas"),
            ("sklearn", "Scikit-learn"),
        ]

        for package, name in critical_deps:
            try:
                mod = importlib.import_module(package)
                version = getattr(mod, "__version__", "unknown")
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.HEALTHY,
                        "DEPENDENCY_OK",
                        "ENVIRONMENT",
                        None,
                        f"{name}: {version}",
                    )
                )
            except ImportError:
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.ERROR,
                        "MISSING_DEPENDENCY",
                        "ENVIRONMENT",
                        None,
                        f"{name} ({package}) not installed",
                    )
                )

        # Optional but recommended
        optional_deps = [
            ("sentence_transformers", "Sentence-Transformers"),
            ("ncps", "Neural Circuit Policies"),
            ("hflayers", "Hopfield Layers"),
            ("psutil", "PSUtil"),
            ("aiohttp", "AioHTTP"),
        ]

        for package, name in optional_deps:
            try:
                mod = importlib.import_module(package)
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.INFO,
                        "OPTIONAL_DEP_OK",
                        "ENVIRONMENT",
                        None,
                        f"Optional: {name} available",
                    )
                )
            except ImportError:
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.INFO,
                        "OPTIONAL_DEP_MISSING",
                        "ENVIRONMENT",
                        None,
                        f"Optional: {name} not installed (some features may be limited)",
                    )
                )

        # Check requirements.txt
        req_file = self.target_dir / "requirements.txt"
        if req_file.exists():
            reqs = req_file.read_text().splitlines()
            req_count = len([r for r in reqs if r.strip() and not r.startswith("#")])
            findings.append(
                self._create_finding(
                    dept,
                    Severity.INFO,
                    "REQUIREMENTS_FILE",
                    "requirements.txt",
                    None,
                    f"Found {req_count} dependencies in requirements.txt",
                )
            )
        else:
            findings.append(
                self._create_finding(
                    dept,
                    Severity.WARNING,
                    "NO_REQUIREMENTS",
                    "requirements.txt",
                    None,
                    "No requirements.txt found",
                )
            )

        self._finalize_department(dept, findings, time.time() - start)

    # =========================================================================
    # DEPARTMENT: TOOL CLINIC
    # =========================================================================

    def _run_tool_clinic(self):
        """
        Tool Clinic: Validates all project tool scripts.
        Ensures tools are runnable, properly structured, and documented.
        """
        start = time.time()
        dept = Department.TOOL_CLINIC
        findings = []

        Console.department("TOOL CLINIC", "PENDING")
        print("  Validating project tool scripts...")

        # Find all tool directories
        tool_dirs = [
            self.target_dir / "tools",
            self.project_root / "tools",
        ]

        tool_files = []
        for td in tool_dirs:
            if td.exists():
                tool_files.extend(td.rglob("*.py"))

        print(f"  Found {len(tool_files)} tool scripts to validate\n")

        for tool_path in tool_files:
            rel_path = str(tool_path.relative_to(self.project_root))

            try:
                content = tool_path.read_text(encoding="utf-8")
                lines = content.splitlines()

                # 1. Check syntax
                try:
                    ast.parse(content)
                except SyntaxError as e:
                    findings.append(
                        self._create_finding(
                            dept,
                            Severity.ERROR,
                            "TOOL_SYNTAX_ERROR",
                            rel_path,
                            e.lineno,
                            f"Syntax error in tool: {e.msg}",
                        )
                    )
                    continue

                # 2. Check for main guard
                has_main_guard = "__name__" in content and "__main__" in content
                if not has_main_guard:
                    findings.append(
                        self._create_finding(
                            dept,
                            Severity.WARNING,
                            "NO_MAIN_GUARD",
                            rel_path,
                            None,
                            "Tool lacks if __name__ == '__main__' guard",
                        )
                    )

                # 3. Check for docstring
                tree = ast.parse(content)
                has_docstring = (
                    tree.body
                    and isinstance(tree.body[0], ast.Expr)
                    and isinstance(tree.body[0].value, ast.Constant)
                )
                if not has_docstring:
                    findings.append(
                        self._create_finding(
                            dept,
                            Severity.INFO,
                            "NO_DOCSTRING",
                            rel_path,
                            None,
                            "Tool lacks module docstring",
                        )
                    )

                # 4. Check for proper path handling
                if "sys.path" in content and "PROJECT_ROOT" not in content.upper():
                    findings.append(
                        self._create_finding(
                            dept,
                            Severity.INFO,
                            "PATH_HANDLING",
                            rel_path,
                            None,
                            "Tool modifies sys.path without PROJECT_ROOT pattern",
                        )
                    )

                # 5. Tool is OK
                if has_main_guard and has_docstring:
                    findings.append(
                        self._create_finding(
                            dept,
                            Severity.HEALTHY,
                            "TOOL_OK",
                            rel_path,
                            None,
                            f"Tool valid ({len(lines)} lines)",
                        )
                    )

            except Exception as e:
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.ERROR,
                        "TOOL_READ_ERROR",
                        rel_path,
                        None,
                        f"Cannot read tool: {e}",
                    )
                )

        self._finalize_department(dept, findings, time.time() - start)

    # =========================================================================
    # DEPARTMENT: ENDOCRINOLOGY
    # =========================================================================

    def _run_endocrinology(self):
        """
        Endocrinology: System Integration & Configuration Integrity.
        Validates entry points, Alembic migrations, config files,
        and headless validator cross-reference.
        """
        start = time.time()
        dept = Department.ENDOCRINOLOGY
        findings = []

        Console.department("ENDOCRINOLOGY", "PENDING")
        print("  Validating system integration: entry points, migrations, configs...")

        # 1. Entry point validation
        entry_points = ["main.py", "run_build.py", "run_ingestion.py", "run_worker.py"]
        for ep in entry_points:
            ep_path = self.target_dir / ep
            if ep_path.exists():
                try:
                    ast.parse(ep_path.read_text(encoding="utf-8"))
                    findings.append(
                        self._create_finding(
                            dept,
                            Severity.HEALTHY,
                            "ENTRY_POINT_OK",
                            ep,
                            None,
                            "Entry point parseable",
                        )
                    )
                except SyntaxError as e:
                    findings.append(
                        self._create_finding(
                            dept,
                            Severity.ERROR,
                            "ENTRY_POINT_SYNTAX",
                            ep,
                            getattr(e, "lineno", None),
                            f"Entry point has syntax error: {e.msg}",
                        )
                    )
            else:
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.ERROR,
                        "ENTRY_POINT_MISSING",
                        ep,
                        None,
                        "Entry point not found",
                    )
                )

        # 2. Alembic migration chain validation
        migrations_dir = self.project_root / "alembic" / "versions"
        if migrations_dir.exists():
            migration_files = list(migrations_dir.glob("*.py"))
            valid_count = 0
            for mf in migration_files:
                try:
                    ast.parse(mf.read_text(encoding="utf-8"))
                    valid_count += 1
                except SyntaxError:
                    findings.append(
                        self._create_finding(
                            dept,
                            Severity.ERROR,
                            "MIGRATION_SYNTAX",
                            str(mf.relative_to(self.project_root)),
                            None,
                            "Migration has syntax error",
                        )
                    )
            findings.append(
                self._create_finding(
                    dept,
                    Severity.HEALTHY if valid_count == len(migration_files) else Severity.WARNING,
                    "MIGRATIONS",
                    "alembic/versions/",
                    None,
                    f"Alembic migrations: {valid_count}/{len(migration_files)} valid",
                )
            )
        else:
            findings.append(
                self._create_finding(
                    dept,
                    Severity.WARNING,
                    "MIGRATIONS_DIR_MISSING",
                    "alembic/versions/",
                    None,
                    "Alembic versions directory not found",
                )
            )

        # 3. JSON config validation
        json_configs = [
            ("settings.json", self.target_dir / "settings.json"),
            ("data/map_config.json", self.target_dir / "data" / "map_config.json"),
            ("data/map_tensors.json", self.target_dir / "data" / "map_tensors.json"),
        ]
        for name, path in json_configs:
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    detail = (
                        f"Valid JSON ({len(data)} top-level keys)"
                        if isinstance(data, dict)
                        else f"Valid JSON ({type(data).__name__})"
                    )
                    findings.append(
                        self._create_finding(
                            dept,
                            Severity.HEALTHY,
                            "JSON_CONFIG_OK",
                            name,
                            None,
                            detail,
                        )
                    )
                except json.JSONDecodeError as e:
                    findings.append(
                        self._create_finding(
                            dept,
                            Severity.ERROR,
                            "JSON_CONFIG_INVALID",
                            name,
                            None,
                            f"Invalid JSON: {e}",
                        )
                    )
            else:
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.WARNING,
                        "JSON_CONFIG_MISSING",
                        name,
                        None,
                        "Config file not found",
                    )
                )

        # 4. Headless validator cross-reference
        hv_path = self.project_root / "tools" / "headless_validator.py"
        if hv_path.exists():
            try:
                ast.parse(hv_path.read_text(encoding="utf-8"))
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.HEALTHY,
                        "HEADLESS_VALIDATOR_OK",
                        "tools/headless_validator.py",
                        None,
                        "Headless validator parseable",
                    )
                )
            except SyntaxError:
                findings.append(
                    self._create_finding(
                        dept,
                        Severity.ERROR,
                        "HEADLESS_VALIDATOR_SYNTAX",
                        "tools/headless_validator.py",
                        None,
                        "Headless validator has syntax error",
                    )
                )
        else:
            findings.append(
                self._create_finding(
                    dept,
                    Severity.WARNING,
                    "HEADLESS_VALIDATOR_MISSING",
                    "tools/headless_validator.py",
                    None,
                    "Headless validator not found",
                )
            )

        self._finalize_department(dept, findings, time.time() - start)

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def _create_finding(
        self,
        dept: Department,
        severity: Severity,
        category: str,
        file_path: str,
        line_number: Optional[int],
        message: str,
        suggestion: str = None,
        code_snippet: str = None,
    ) -> DiagnosticFinding:
        """Create a diagnostic finding."""
        return DiagnosticFinding(
            department=dept.value,
            severity=severity.value,
            category=category,
            file_path=file_path,
            line_number=line_number,
            message=message,
            suggestion=suggestion,
            code_snippet=code_snippet,
        )

    def _add_finding(
        self,
        dept: Department,
        severity: Severity,
        category: str,
        file_path: str,
        line_number: Optional[int],
        message: str,
    ):
        """Add a finding directly to the report."""
        finding = self._create_finding(dept, severity, category, file_path, line_number, message)
        dept_name = dept.value
        if dept_name not in self.report.departments:
            self.report.departments[dept_name] = DepartmentReport(
                name=dept_name,
                status="PENDING",
                checks_run=0,
                issues_found=0,
                critical_count=0,
                error_count=0,
                warning_count=0,
                duration_ms=0,
            )
        self.report.departments[dept_name].findings.append(finding)

    def _add_department_error(self, dept_key: str, error: str):
        """Add an error for a department that failed to run."""
        dept = Department[dept_key]
        self._add_finding(
            dept,
            Severity.CRITICAL,
            "DEPARTMENT_CRASH",
            "SYSTEM",
            None,
            f"Department failed: {error}",
        )

    def _finalize_department(
        self, dept: Department, findings: List[DiagnosticFinding], duration: float
    ):
        """Finalize a department's report."""
        # Count severities
        critical = sum(1 for f in findings if f.severity == "CRITICAL")
        errors = sum(1 for f in findings if f.severity == "ERROR")
        warnings = sum(1 for f in findings if f.severity == "WARNING")

        # Determine status
        if critical > 0:
            status = "CRITICAL"
        elif errors > 0:
            status = "ERROR"
        elif warnings > 0:
            status = "WARNING"
        else:
            status = "HEALTHY"

        report = DepartmentReport(
            name=dept.value,
            status=status,
            checks_run=len(findings),
            issues_found=critical + errors + warnings,
            critical_count=critical,
            error_count=errors,
            warning_count=warnings,
            duration_ms=duration * 1000,
            findings=findings,
        )

        self.report.departments[dept.value] = report

        # Print department summary
        color = Console.COLORS.get(status, Console.COLORS["INFO"])
        reset = Console.COLORS["RESET"]
        print(f"\n  {color}Status: {status}{reset}")
        print(
            f"  Checks: {len(findings)} | Critical: {critical} | Errors: {errors} | Warnings: {warnings}"
        )
        print(f"  Duration: {duration*1000:.1f}ms")

        # Print findings
        if self.verbose:
            for f in findings:
                if f.severity in ("CRITICAL", "ERROR", "WARNING"):
                    Console.finding(f, verbose=True)

    # F8-05: Health rating thresholds — adjust if project error/warning baseline changes
    _HEALTH_ERROR_THRESHOLD = 3   # >N errors → ERROR rating
    _HEALTH_WARN_THRESHOLD = 10   # >N warnings → WARNING rating (when errors == 0)

    def _calculate_overall_health(self):
        """Calculate overall project health based on all departments."""
        all_critical = sum(d.critical_count for d in self.report.departments.values())
        all_errors = sum(d.error_count for d in self.report.departments.values())
        all_warnings = sum(d.warning_count for d in self.report.departments.values())

        if all_critical > 0:
            self.report.overall_health = "CRITICAL"
        elif all_errors > self._HEALTH_ERROR_THRESHOLD:
            self.report.overall_health = "ERROR"
        elif all_errors > 0 or all_warnings > self._HEALTH_WARN_THRESHOLD:
            self.report.overall_health = "WARNING"
        else:
            self.report.overall_health = "HEALTHY"

    def _print_final_report(self):
        """Print the final hospital report."""
        Console.header("FINAL HOSPITAL DIAGNOSTIC REPORT")

        # Overall status
        status = self.report.overall_health
        color = Console.COLORS.get(status, Console.COLORS["INFO"])
        reset = Console.COLORS["RESET"]

        print(f"  {color}{'='*56}{reset}")
        print(f"  {color}  OVERALL PROJECT HEALTH: {status:^20}  {reset}")
        print(f"  {color}{'='*56}{reset}\n")

        # Summary stats
        Console.stats("Total Files Analyzed", self.report.total_files, "INFO")
        Console.stats("Total Lines of Code", self.report.total_lines, "INFO")
        Console.stats("Total Functions", self.report.total_functions, "INFO")
        Console.stats("Total Classes", self.report.total_classes, "INFO")
        Console.stats("Scan Duration", f"{self.report.duration_seconds:.2f}s", "INFO")

        print("\n  DEPARTMENT SUMMARY:")
        print("  " + "-" * 56)

        for name, dept in sorted(self.report.departments.items()):
            status_color = Console.COLORS.get(dept.status, Console.COLORS["INFO"])
            print(
                f"  {status_color}[{dept.status:^8}]{reset} {name:<25} "
                f"C:{dept.critical_count} E:{dept.error_count} W:{dept.warning_count}"
            )

        # Critical issues summary
        all_critical = []
        for dept in self.report.departments.values():
            all_critical.extend(f for f in dept.findings if f.severity == "CRITICAL")

        if all_critical:
            print(
                f"\n  {Console.COLORS['CRITICAL']}CRITICAL ISSUES REQUIRING IMMEDIATE ATTENTION:{reset}"
            )
            print("  " + "-" * 56)
            for f in all_critical[:10]:
                Console.finding(f, verbose=True)

        print("\n" + "=" * 60)
        print("  GOLIATH HOSPITAL DIAGNOSTIC COMPLETE")
        print("=" * 60 + "\n")

    def _export_json_report(self):
        """Export the full report to JSON."""
        report_dir = self.project_root / "reports"
        report_dir.mkdir(exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")  # F8-38: UTC for unambiguous filenames
        report_path = report_dir / f"goliath_hospital_{timestamp}.json"

        # Convert to dict
        report_dict = {
            "timestamp": self.report.timestamp,
            "version": "2.1.0",
            "timeout_guard_active": True,
            "project_root": self.report.project_root,
            "total_files": self.report.total_files,
            "total_lines": self.report.total_lines,
            "total_functions": self.report.total_functions,
            "total_classes": self.report.total_classes,
            "overall_health": self.report.overall_health,
            "duration_seconds": self.report.duration_seconds,
            "departments": {},
            "file_health": {},
        }

        for name, dept in self.report.departments.items():
            report_dict["departments"][name] = {
                "status": dept.status,
                "checks_run": dept.checks_run,
                "issues_found": dept.issues_found,
                "critical_count": dept.critical_count,
                "error_count": dept.error_count,
                "warning_count": dept.warning_count,
                "duration_ms": dept.duration_ms,
                "findings": [f.to_dict() for f in dept.findings],
            }

        # Only include files with issues
        for path, health in self.report.file_health.items():
            if health.findings:
                report_dict["file_health"][path] = asdict(health)

        report_path.write_text(json.dumps(report_dict, indent=2, default=str), encoding="utf-8")
        print(f"  JSON Report exported to: {report_path}")


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================


def main():
    """Main entry point for Goliath Hospital."""
    # F8-33: argparse imported inside main() as lazy import. Avoids loading when Goliath_Hospital
    # is imported as a module by goliath.py root orchestrator. Acceptable pattern.
    import argparse

    parser = argparse.ArgumentParser(
        description="Goliath Hospital Diagnostic System - Comprehensive project health analysis"
    )
    parser.add_argument(
        "--target",
        "-t",
        type=str,
        default=None,
        help="Target directory to scan (default: Programma_CS2_RENAN)",
    )
    parser.add_argument("--quiet", "-q", action="store_true", help="Reduce output verbosity")
    parser.add_argument(
        "--department",
        "-d",
        type=str,
        choices=[
            "ER",
            "RADIOLOGY",
            "PATHOLOGY",
            "CARDIOLOGY",
            "NEUROLOGY",
            "ONCOLOGY",
            "PEDIATRICS",
            "ICU",
            "PHARMACY",
            "TOOL_CLINIC",
            "ENDOCRINOLOGY",
        ],
        help="Run only a specific department",
    )

    args = parser.parse_args()

    target = Path(args.target) if args.target else SOURCE_ROOT
    hospital = GoliathHospital(target_dir=target, verbose=not args.quiet)

    if args.department:
        report = hospital.run_single_department(args.department)
    else:
        report = hospital.run_full_diagnostic()

    # Exit code based on health
    exit_codes = {"HEALTHY": 0, "WARNING": 0, "ERROR": 1, "CRITICAL": 2}
    sys.exit(exit_codes.get(report.overall_health, 1))


if __name__ == "__main__":
    main()
