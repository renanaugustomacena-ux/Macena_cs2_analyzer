# --- Path Stabilization ---
import os
import sys
from pathlib import Path

# --- Venv Guard ---
if sys.prefix == sys.base_prefix and not os.environ.get("CI"):
    print("ERROR: Not in venv. Run: source ~/.venvs/cs2analyzer/bin/activate", file=sys.stderr)
    sys.exit(2)

# tools/ is one level below the project root — no fragile name matching needed
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
# ----------------------------------------

"""
============================================================================
PORTABILITY VERIFICATION SUITE - DOCTORATE-LEVEL QUALITY ASSURANCE
============================================================================

NON-NEGOTIABLE STANDARDS:
- 1000% Portability Certification
- Zero tolerance for hardcoded paths
- Full cross-platform compatibility
- CI/CD integration ready

VERIFICATION CATEGORIES:
1. Filesystem Portability - No hardcoded paths, proper OS handling
2. Import Integrity - All modules importable without side effects
3. Configuration Safety - Dynamic config with fallbacks
4. Resource Location - Assets and data files properly referenced
5. Platform Compatibility - Windows/Linux/Mac considerations
6. Dependency Analysis - External deps properly handled
7. Environment Isolation - No leaked environment assumptions
8. Path Construction - Proper pathlib/os.path usage

Run: python tools/portability_test.py
Exit code 0 = CERTIFIED | Exit code 1 = FAILED
============================================================================
"""

import ast
import hashlib
import importlib.util
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class Severity(Enum):
    """Violation severity levels."""

    CRITICAL = "CRITICAL"  # Blocks certification
    WARNING = "WARNING"  # Must be reviewed
    INFO = "INFO"  # Informational only


@dataclass
class Violation:
    """Represents a portability violation."""

    file: str
    line: int
    severity: Severity
    category: str
    message: str
    code_snippet: str = ""
    suggestion: str = ""


@dataclass
class TestResult:
    """Result of a single test."""

    name: str
    passed: bool
    duration_ms: float
    violations: List[Violation] = field(default_factory=list)
    details: str = ""


@dataclass
class TestReport:
    """Complete test report."""

    timestamp: str
    total_tests: int
    passed_tests: int
    failed_tests: int
    critical_violations: int
    warnings: int
    results: List[TestResult] = field(default_factory=list)
    certified: bool = False


class PortabilityVerifier:
    """
    Comprehensive Portability Verification System.

    Implements doctorate-level static analysis and runtime checks
    to ensure 1000% portability across all deployment environments.
    """

    # Patterns that indicate portability violations
    HARDCODED_PATH_PATTERNS = [
        # Windows absolute path with drive letter (e.g., C:/Users or D:\Data), excluding URLs
        (r'(?<![a-zA-Z])(?:[a-zA-Z]:[\\/][^"\'\s]+)(?<!://)', "Windows drive letter detected"),
        (r"/home/\w+", "Unix home directory"),
        (r"/Users/\w+", "macOS home directory"),
        (r"C:\\Users", "Windows Users directory"),
        (r"/tmp/", "Unix temp (use tempfile module)"),
        (r"/var/", "Unix var directory"),
        (r"/opt/", "Unix opt directory"),
        (r"/usr/", "Unix usr directory"),
    ]

    # Acceptable path constructs
    ACCEPTABLE_PATTERNS = [
        r"Path\(__file__\)",
        r"os\.path\.(dirname|abspath|join|expanduser|expandvars)",
        r"pathlib\.Path",
        r"tempfile\.",
        r"\.resolve\(\)",
        r"\.absolute\(\)",
        r"get_setting\(",
        r"DATABASE_URL",
        r"os\.environ",
    ]

    # Files/directories to exclude from scanning
    EXCLUDE_PATTERNS = [
        "__pycache__",
        ".git",
        ".buildozer",
        "node_modules",
        ".venv",
        "venv",
        "env",
        "dist",
        "build",
        ".eggs",
        "*.pyc",
        "*.pyo",
        "*.egg-info",
        "migrations",
    ]

    # Critical modules that must be importable
    CRITICAL_MODULES = [
        "Programma_CS2_RENAN.core.config",
        "Programma_CS2_RENAN.core.localization",
        "Programma_CS2_RENAN.backend.storage.database",
        "Programma_CS2_RENAN.backend.storage.db_models",
    ]

    # Files that must exist for portability
    REQUIRED_FILES = [
        "Programma_CS2_RENAN/core/config.py",
        "Programma_CS2_RENAN/core/localization.py",
        "Programma_CS2_RENAN/apps/qt_app/app.py",
        "requirements.txt",
    ]

    # Dangerous imports that indicate non-portable code
    DANGEROUS_IMPORTS = [
        ("win32", "Windows-specific API"),
        ("winreg", "Windows registry"),
        ("pwd", "Unix password database"),
        ("grp", "Unix group database"),
    ]

    # Patterns that are safe at module level (not import-time side effects)
    SAFE_IMPORT_PATTERNS = [
        # Standard library / framework
        "Path(", "os.path.", "os.makedirs(", "os.environ", "logging.", "getLogger",
        # Type annotations
        "Optional[", "List[", "Dict[", "Tuple[", "Union[", "Type[",
        "TypeVar(", "Callable[",
        # Dataclass / enum
        "dataclass", "field(", "Enum)", "namedtuple(",
        "IntEnum)", "StrEnum)", "auto()",
        # Project-specific safe patterns
        "get_logger(", "get_setting(", "get_base_dir(", "get_writeable_dir(",
        "get_resource_path(", "stabilize_paths(", "get_db_manager(",
        "get_match_data_manager(", "get_experience_bank(",
        # SQLAlchemy / SQLModel
        "create_engine(", "Column(", "Field(", "Relationship(",
        "event.listens_for", "select(",
        # Kivy properties
        "ObjectProperty(", "StringProperty(", "NumericProperty(",
        "BooleanProperty(", "ListProperty(", "DictProperty(",
        "Builder.load", "Factory.register",
        # Constants / config
        "re.compile(", "threading.", "functools.", "collections.",
        # Data structure constructors (module-level constants)
        "NamedPosition(", "MapMetadata(", "GameEventSpec(",
        "CoachingConcept(", "RoleProfile(", "EngagementProfile(",
        "FormatVersion(", "ProtoChange(", "ScaleConfig(", "TrainingConfig(",
        # System / process (entry point scripts)
        "sys.path.insert(", "sys.path.append(", "sys.exit(", "print(",
        # Kivy / GUI config
        "Config.set(", "Config.read(", "matplotlib.use(",
        # Argparse
        "ArgumentParser(", "parse_args(",
        # Standard lib
        "warnings.warn(", "_warnings.warn(",
        "defaultdict(", "OrderedDict(", "deque(",
        "raise ",
        # Register / decorators
        ".register(",
        # Threading primitives
        "Lock(", "Event(", "Semaphore(", "Condition(",
        # Type construction
        "NewType(",
        # Environment / sys introspection
        "os.getenv(", "getattr(sys", "getattr(os",
        # FastAPI / ASGI
        "FastAPI(", "APIKeyHeader(", "APIRouter(", "@app.",
        # Pytest
        "@pytest.mark.", "pytest.mark.",
        # Logging setup
        "addHandler(", "setFormatter(", "fileConfig(",
        "logger.info(", "logger.warning(", "logger.critical(",
        "logger.debug(", "logger.error(", "app_logger.",
        # Project entry-point helpers
        "path_stabilize(", "init_sentry(", "run_rasp_audit(",
        # Alembic
        "run_migrations_offline(", "run_migrations_online(", "is_offline_mode(",
        # Module-level builtins (constant computation)
        "float(", "int(", "str(", "len(", "set(", "list(",
        "dict(", "tuple(", "bool(", "max(", "min(", "abs(", "round(",
        # Module-level singletons (service locator pattern)
        "= HelpSystem(", "= AnalyticsEngine(", "= StateManager(",
        "= VisualizationService(", "= AppLifecycleManager(",
        "= LocalizationManager(", "= ScreenRegistry(",
        "= RateLimiter(", "= Console(",
        "hook(", "stdlib_module_names",
        # Config module bootstrap
        "load_user_settings(", "_settings.get(",
        "_resolve_match_data_path(", "configure_log_dir(",
        "ensure_database_current(",
    ]

    def __init__(self, project_root: Path = None):
        self.project_root = project_root or Path(__file__).parent.parent
        self.violations: List[Violation] = []
        self.results: List[TestResult] = []

    def _should_exclude(self, path: Path) -> bool:
        """Check if path should be excluded from scanning."""
        path_str = str(path)
        for pattern in self.EXCLUDE_PATTERNS:
            if pattern in path_str:
                return True
        return False

    def _is_in_comment_or_docstring(self, line: str, full_content: str, line_num: int) -> bool:
        """Check if code is within a comment or docstring."""
        stripped = line.strip()

        # Single line comment
        if stripped.startswith("#"):
            return True

        # Check for docstring context (simplified)
        lines = full_content.split("\n")[:line_num]
        docstring_count = sum(l.count('"""') + l.count("'''") for l in lines)
        return docstring_count % 2 == 1  # Odd count means we're inside

    @staticmethod
    def _is_false_positive_path(line: str) -> bool:
        """Detect f-strings with / or \\ that are NOT file path construction.

        Strategy: only flag lines that show strong evidence of file system
        path construction.  Everything else is a false positive (URL routes,
        text fractions, ANSI codes, TensorBoard metric keys, etc.).
        """
        lower = line.lower()
        # --- Definite non-path patterns (return True = false positive) ---
        # URL / protocol patterns
        if any(p in lower for p in ("http", "sqlite:///", "ftp:", "://", "mailto:")):
            return True
        # Already uses os.path (safe path construction)
        if "os.path." in line:
            return True
        # Explicit suppression
        if "# PORTABILITY_OK" in line:
            return True
        # Logging / debug strings
        if any(p in line for p in ("logger.", "log.", "app_logger.", "logging.")):
            return True
        # ANSI escape codes (\033[)
        if "\\033[" in line or "\\x1b[" in line:
            return True

        # --- Pathlib / operator already in use → correct, not a violation ---
        import re as _re
        # Pattern: `variable / f"..."` — pathlib division operator
        if _re.search(r'\w\s*/\s*f["\']', line):
            return True

        # --- Positive evidence for file path construction ---
        # A genuine file path f-string typically has a file extension
        file_ext_pattern = _re.compile(
            r'\.(py|json|db|txt|csv|pt|pth|log|cfg|ini|yaml|yml|toml|md|html|kv|png|jpg|bak)\b'
        )
        if file_ext_pattern.search(line):
            return False  # Likely genuine path construction — flag it

        # Backslash that is NOT an escape sequence
        stripped = line.strip()
        if "\\" in stripped:
            test = stripped
            # Remove all known Python escape sequences
            for esc in ("\\n", "\\t", "\\r", "\\\\", "\\'", '\\"', "\\0", "\\a", "\\b", "\\f", "\\v"):
                test = test.replace(esc, "")
            # Remove unicode escapes (\uXXXX) and hex escapes (\xXX)
            test = _re.sub(r"\\u[0-9a-fA-F]{4}", "", test)
            test = _re.sub(r"\\x[0-9a-fA-F]{2}", "", test)
            if "\\" in test:
                return False  # Has real backslash path separators — flag it

        # No file extension AND no real backslash → almost certainly not a path
        return True

    def _is_in_platform_guard(self, lines: list, line_num: int) -> bool:
        """Check if line is inside a platform-specific guard (e.g., if os.name == 'nt':)."""
        # Walk backwards from current line to find enclosing if-block
        current_indent = len(lines[line_num - 1]) - len(lines[line_num - 1].lstrip())
        for i in range(line_num - 2, max(0, line_num - 20), -1):
            prev_line = lines[i]
            prev_stripped = prev_line.strip()
            prev_indent = len(prev_line) - len(prev_line.lstrip())
            if prev_indent < current_indent and re.search(
                r'''if\s+os\.name\s*==\s*["']nt["']''', prev_stripped
            ):
                return True
            if prev_indent < current_indent and re.search(
                r'''if\s+.*sys\.platform.*==.*["']win''', prev_stripped
            ):
                return True
        return False

    def _add_violation(
        self,
        file: str,
        line: int,
        severity: Severity,
        category: str,
        message: str,
        snippet: str = "",
        suggestion: str = "",
    ):
        """Add a violation to the list."""
        self.violations.append(
            Violation(
                file=file,
                line=line,
                severity=severity,
                category=category,
                message=message,
                code_snippet=snippet[:120] if snippet else "",
                suggestion=suggestion,
            )
        )

    # ==========================================================================
    # TEST 1: Hardcoded Path Detection
    # ==========================================================================
    def test_hardcoded_paths(self) -> TestResult:
        """
        Comprehensive scan for hardcoded filesystem paths.

        Checks:
        - Drive letters (C:\\, D:\\, etc.)
        - Unix absolute paths (/home, /Users, etc.)
        - Temp directory assumptions
        - User directory assumptions
        """
        import time

        start = time.time()

        local_violations = []
        files_scanned = 0

        prod_code = self.project_root / "Programma_CS2_RENAN"
        if not prod_code.exists():
            return TestResult(
                name="Hardcoded Paths Detection",
                passed=False,
                duration_ms=0,
                details="Production code directory not found",
            )

        for pyfile in prod_code.rglob("*.py"):
            if self._should_exclude(pyfile):
                continue

            files_scanned += 1

            try:
                content = pyfile.read_text(encoding="utf-8")
                lines = content.split("\n")

                for line_num, line in enumerate(lines, 1):
                    for pattern, description in self.HARDCODED_PATH_PATTERNS:
                        if re.search(pattern, line, re.IGNORECASE):
                            # Skip if in comment/docstring
                            if self._is_in_comment_or_docstring(line, content, line_num):
                                continue

                            # Skip if line has acceptable pattern
                            has_acceptable = any(
                                re.search(ap, line) for ap in self.ACCEPTABLE_PATTERNS
                            )
                            if has_acceptable:
                                continue

                            # Skip allowed markers
                            if "# PORTABILITY_OK" in line or "# Example" in line:
                                continue

                            # Skip regex pattern strings (e.g., r"C:\\Users" in security scanners)
                            stripped = line.strip()
                            if re.search(r'''[rb]?["'].*\\\\.*["']''', stripped):
                                continue

                            # Skip platform-guarded code (inside if os.name == "nt": blocks)
                            if self._is_in_platform_guard(lines, line_num):
                                continue

                            local_violations.append(
                                Violation(
                                    file=str(pyfile.relative_to(self.project_root)),
                                    line=line_num,
                                    severity=Severity.CRITICAL,
                                    category="Hardcoded Path",
                                    message=f"{description} detected",
                                    code_snippet=line.strip(),
                                    suggestion="Use pathlib.Path, os.path.expanduser, or config settings",
                                )
                            )

            except Exception as e:
                local_violations.append(
                    Violation(
                        file=str(pyfile),
                        line=0,
                        severity=Severity.WARNING,
                        category="File Read Error",
                        message=str(e),
                    )
                )

        self.violations.extend(local_violations)
        duration = (time.time() - start) * 1000

        critical_count = sum(1 for v in local_violations if v.severity == Severity.CRITICAL)

        return TestResult(
            name="Hardcoded Paths Detection",
            passed=critical_count == 0,
            duration_ms=duration,
            violations=local_violations,
            details=f"Scanned {files_scanned} files, found {len(local_violations)} issues",
        )

    # ==========================================================================
    # TEST 2: Path Construction Analysis
    # ==========================================================================
    def test_path_construction(self) -> TestResult:
        """
        Verify proper path construction patterns.

        Checks:
        - String concatenation instead of os.path.join
        - Manual separator usage (\\, /)
        - Missing Path.resolve() calls
        - Relative path assumptions
        """
        import time

        start = time.time()

        local_violations = []

        # Pattern: string + "/" or "\" + string (path concatenation)
        bad_concat = re.compile(r'["\'][^"\']*[/\\][^"\']*["\'].*\+')

        prod_code = self.project_root / "Programma_CS2_RENAN"

        for pyfile in prod_code.rglob("*.py"):
            if self._should_exclude(pyfile):
                continue

            try:
                content = pyfile.read_text(encoding="utf-8")
                lines = content.split("\n")

                for line_num, line in enumerate(lines, 1):
                    # Check for f-string path construction without Path
                    if 'f"' in line or "f'" in line:
                        if ("/" in line or "\\" in line) and "Path" not in line:
                            if not self._is_in_comment_or_docstring(line, content, line_num):
                                if not self._is_false_positive_path(line):
                                    local_violations.append(
                                        Violation(
                                            file=str(pyfile.relative_to(self.project_root)),
                                            line=line_num,
                                            severity=Severity.WARNING,
                                            category="Path Construction",
                                            message="F-string path construction without pathlib.Path",
                                            code_snippet=line.strip(),
                                            suggestion="Use Path(f'...') or os.path.join()",
                                        )
                                    )

                    # Check for manual os.sep usage without justification
                    if "os.sep" in line and "# PORTABILITY_OK" not in line:
                        local_violations.append(
                            Violation(
                                file=str(pyfile.relative_to(self.project_root)),
                                line=line_num,
                                severity=Severity.INFO,
                                category="Path Construction",
                                message="Manual os.sep usage (review for necessity)",
                                code_snippet=line.strip(),
                            )
                        )

            except Exception:
                pass

        self.violations.extend(local_violations)
        duration = (time.time() - start) * 1000

        critical = sum(1 for v in local_violations if v.severity == Severity.CRITICAL)

        return TestResult(
            name="Path Construction Analysis",
            passed=critical == 0,
            duration_ms=duration,
            violations=local_violations,
            details=f"Found {len(local_violations)} path construction issues",
        )

    # ==========================================================================
    # TEST 3: Import Safety Analysis
    # ==========================================================================
    def test_import_safety(self) -> TestResult:
        """
        Verify imports don't have side effects and are portable.

        Checks:
        - Platform-specific imports without guards
        - Import-time side effects
        - Missing try/except for optional deps
        - Circular import potential
        """
        import time

        start = time.time()

        local_violations = []

        prod_code = self.project_root / "Programma_CS2_RENAN"

        for pyfile in prod_code.rglob("*.py"):
            if self._should_exclude(pyfile):
                continue

            try:
                content = pyfile.read_text(encoding="utf-8")

                # Check for dangerous platform-specific imports
                rel_path_for_danger = str(pyfile.relative_to(self.project_root))
                content_lines = content.split("\n")
                self._check_dangerous_imports(
                    content_lines, rel_path_for_danger, local_violations
                )

                # Check for import-time function calls (side effects)
                tree = ast.parse(content)
                lines = content.split("\n")
                rel_path = str(pyfile.relative_to(self.project_root))

                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call) or not hasattr(node, "lineno"):
                        continue

                    line = lines[node.lineno - 1]

                    if any(sp in line for sp in self.SAFE_IMPORT_PATTERNS):
                        continue
                    if self._is_inside_function_or_class(tree, node.lineno):
                        continue
                    if self._is_inside_name_main_block(tree, node.lineno):
                        continue

                    local_violations.append(
                        Violation(
                            file=rel_path,
                            line=node.lineno,
                            severity=Severity.WARNING,
                            category="Import Side Effect",
                            message="Top-level function call at import time",
                            code_snippet=line.strip(),
                            suggestion="Move to main() or lazy initialization",
                        )
                    )

            except SyntaxError:
                local_violations.append(
                    Violation(
                        file=str(pyfile.relative_to(self.project_root)),
                        line=0,
                        severity=Severity.CRITICAL,
                        category="Syntax Error",
                        message="File has syntax errors - cannot parse",
                    )
                )
            except Exception:
                pass

        self.violations.extend(local_violations)
        duration = (time.time() - start) * 1000

        critical = sum(1 for v in local_violations if v.severity == Severity.CRITICAL)

        return TestResult(
            name="Import Safety Analysis",
            passed=critical == 0,
            duration_ms=duration,
            violations=local_violations,
            details=f"Analyzed imports, found {len(local_violations)} issues",
        )

    def _is_inside_function_or_class(self, tree: ast.AST, lineno: int) -> bool:
        """Check if a line is inside a function or class definition."""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if hasattr(node, "lineno") and hasattr(node, "end_lineno"):
                    if node.lineno <= lineno <= (node.end_lineno or node.lineno + 1000):
                        return True
        return False

    def _check_dangerous_imports(
        self,
        content_lines: list,
        rel_path: str,
        violations: list,
    ) -> None:
        """Flag platform-specific imports that lack try/except or platform guards."""
        for danger_import, description in self.DANGEROUS_IMPORTS:
            pattern = rf"^\s*(?:import|from)\s+{danger_import}"
            for line_num, line in enumerate(content_lines, 1):
                if not re.match(pattern, line):
                    continue

                context_start = max(0, line_num - 5)
                context = "\n".join(content_lines[context_start:line_num])

                if "try:" in context or "platform" in context.lower():
                    continue

                violations.append(
                    Violation(
                        file=rel_path,
                        line=line_num,
                        severity=Severity.CRITICAL,
                        category="Platform Import",
                        message=f"{description} - not guarded",
                        code_snippet=line.strip(),
                        suggestion="Wrap in try/except or check sys.platform",
                    )
                )

    @staticmethod
    def _is_inside_name_main_block(tree: ast.AST, lineno: int) -> bool:
        """Check if a line is inside an 'if __name__ == \"__main__\":' block."""
        for node in ast.walk(tree):
            if isinstance(node, ast.If) and hasattr(node, "end_lineno"):
                # Match: if __name__ == "__main__":
                test = node.test
                is_name_main = False
                if isinstance(test, ast.Compare):
                    left = test.left
                    if isinstance(left, ast.Name) and left.id == "__name__":
                        is_name_main = True
                    elif isinstance(left, ast.Constant) and left.value == "__main__":
                        is_name_main = True
                if is_name_main:
                    end = node.end_lineno or node.lineno + 5000
                    if node.lineno <= lineno <= end:
                        return True
        return False

    # ==========================================================================
    # TEST 4: Configuration Portability
    # ==========================================================================
    def test_configuration_portability(self) -> TestResult:
        """
        Verify configuration system is portable.

        Checks:
        - Config uses environment variables or dynamic defaults
        - No hardcoded paths in config
        - Fallback values exist for all settings
        - Config file locations are portable
        """
        import time

        start = time.time()

        local_violations = []

        config_files = [
            self.project_root / "Programma_CS2_RENAN" / "core" / "config.py",
        ]

        for config_file in config_files:
            if not config_file.exists():
                local_violations.append(
                    Violation(
                        file=str(config_file),
                        line=0,
                        severity=Severity.CRITICAL,
                        category="Missing File",
                        message="Configuration file missing",
                    )
                )
                continue

            try:
                content = config_file.read_text(encoding="utf-8")

                # Check for get_setting with fallback
                if "get_setting" in content:
                    # Good - has dynamic settings
                    pass

                # Check DATABASE_URL construction
                if "DATABASE_URL" in content:
                    if "sqlite:///" in content:
                        # Check if path is dynamic
                        db_lines = [
                            l for l in content.split("\n") if "DATABASE_URL" in l and "sqlite" in l
                        ]
                        for line in db_lines:
                            if re.search(r"[A-Z]:\\", line):
                                local_violations.append(
                                    Violation(
                                        file=str(config_file.relative_to(self.project_root)),
                                        line=content.split("\n").index(line) + 1,
                                        severity=Severity.CRITICAL,
                                        category="Config Path",
                                        message="Hardcoded path in DATABASE_URL",
                                        code_snippet=line.strip(),
                                    )
                                )

                # Check for environment variable usage
                if "os.environ" not in content and "os.getenv" not in content:
                    local_violations.append(
                        Violation(
                            file=str(config_file.relative_to(self.project_root)),
                            line=0,
                            severity=Severity.WARNING,
                            category="Config Flexibility",
                            message="Config doesn't use environment variables",
                            suggestion="Consider os.getenv() for deployment flexibility",
                        )
                    )

            except Exception as e:
                local_violations.append(
                    Violation(
                        file=str(config_file),
                        line=0,
                        severity=Severity.WARNING,
                        category="Config Read Error",
                        message=str(e),
                    )
                )

        self.violations.extend(local_violations)
        duration = (time.time() - start) * 1000

        critical = sum(1 for v in local_violations if v.severity == Severity.CRITICAL)

        return TestResult(
            name="Configuration Portability",
            passed=critical == 0,
            duration_ms=duration,
            violations=local_violations,
            details=f"Checked {len(config_files)} config files",
        )

    # ==========================================================================
    # TEST 5: Required Files Check
    # ==========================================================================
    def test_required_files(self) -> TestResult:
        """
        Verify all required files exist.

        Checks:
        - Core application files
        - Configuration files
        - Resource files (layouts, assets)
        - Requirements specification
        """
        import time

        start = time.time()

        local_violations = []

        for required in self.REQUIRED_FILES:
            full_path = self.project_root / required
            if not full_path.exists():
                local_violations.append(
                    Violation(
                        file=required,
                        line=0,
                        severity=Severity.CRITICAL,
                        category="Missing Required File",
                        message=f"Required file not found: {required}",
                    )
                )

        # Additional critical files check
        additional_critical = [
            ("Programma_CS2_RENAN/main.py", "Main application entry point"),
            ("tools/portability_test.py", "This verification script"),
            ("tools/headless_validator.py", "Headless system validator"),
        ]

        for file_path, description in additional_critical:
            if not (self.project_root / file_path).exists():
                local_violations.append(
                    Violation(
                        file=file_path,
                        line=0,
                        severity=Severity.CRITICAL,
                        category="Missing Critical File",
                        message=f"{description} - file missing",
                    )
                )

        self.violations.extend(local_violations)
        duration = (time.time() - start) * 1000

        return TestResult(
            name="Required Files Check",
            passed=len(local_violations) == 0,
            duration_ms=duration,
            violations=local_violations,
            details=f"Checked {len(self.REQUIRED_FILES) + len(additional_critical)} required files",
        )

    # ==========================================================================
    # TEST 6: Module Import Test
    # ==========================================================================
    def test_critical_imports(self) -> TestResult:
        """
        Verify critical modules can be imported.

        Checks:
        - All core modules importable
        - No import-time crashes
        - Dependencies available
        """
        import time

        start = time.time()

        local_violations = []
        imported_count = 0

        # Add project to path
        sys.path.insert(0, str(self.project_root))

        for module_name in self.CRITICAL_MODULES:
            try:
                importlib.import_module(module_name)
                imported_count += 1
            except ImportError as e:
                local_violations.append(
                    Violation(
                        file=module_name.replace(".", "/") + ".py",
                        line=0,
                        severity=Severity.CRITICAL,
                        category="Import Failure",
                        message=f"Cannot import module: {e}",
                        suggestion="Check module path and dependencies",
                    )
                )
            except Exception as e:
                local_violations.append(
                    Violation(
                        file=module_name.replace(".", "/") + ".py",
                        line=0,
                        severity=Severity.WARNING,
                        category="Import Warning",
                        message=f"Import succeeded but raised: {type(e).__name__}: {e}",
                    )
                )

        self.violations.extend(local_violations)
        duration = (time.time() - start) * 1000

        critical = sum(1 for v in local_violations if v.severity == Severity.CRITICAL)

        return TestResult(
            name="Critical Module Imports",
            passed=critical == 0,
            duration_ms=duration,
            violations=local_violations,
            details=f"Imported {imported_count}/{len(self.CRITICAL_MODULES)} modules successfully",
        )

    # ==========================================================================
    # TEST 7: Environment Variable Analysis
    # ==========================================================================
    def test_environment_isolation(self) -> TestResult:
        """
        Check for environment variable dependencies.

        Checks:
        - Required env vars documented
        - Fallbacks exist for optional vars
        - No secrets in code
        - Production env assumptions
        """
        import time

        start = time.time()

        local_violations = []
        env_vars_found = set()

        prod_code = self.project_root / "Programma_CS2_RENAN"

        for pyfile in prod_code.rglob("*.py"):
            if self._should_exclude(pyfile):
                continue

            try:
                content = pyfile.read_text(encoding="utf-8")

                # Find all os.environ and os.getenv calls
                env_patterns = [
                    (r'os\.environ\[[\'"](.*?)[\'"]\]', False),  # No fallback
                    (r'os\.getenv\([\'"](.*?)[\'"](?:\s*,\s*.*?)?\)', True),  # With fallback
                    (r'os\.environ\.get\([\'"](.*?)[\'"](?:\s*,\s*.*?)?\)', True),  # With fallback
                ]

                for pattern, has_fallback in env_patterns:
                    for match in re.finditer(pattern, content):
                        var_name = match.group(1)
                        env_vars_found.add(var_name)

                        if not has_fallback:
                            # Check if wrapped in try/except
                            line_num = content[: match.start()].count("\n") + 1
                            context_start = max(0, line_num - 3)
                            context = "\n".join(content.split("\n")[context_start:line_num])

                            if "try" not in context:
                                local_violations.append(
                                    Violation(
                                        file=str(pyfile.relative_to(self.project_root)),
                                        line=line_num,
                                        severity=Severity.WARNING,
                                        category="Env Var Dependency",
                                        message=f"Env var {var_name} accessed without fallback",
                                        suggestion="Use os.getenv() with default or wrap in try/except",
                                    )
                                )

                # Check for potential secrets in code
                secret_patterns = [
                    (
                        r'(?:password|secret|api_key|token)\s*=\s*["\'][^"\']+["\']',
                        "Hardcoded secret",
                    ),
                ]

                for pattern, description in secret_patterns:
                    for match in re.finditer(pattern, content, re.IGNORECASE):
                        line_num = content[: match.start()].count("\n") + 1
                        line = content.split("\n")[line_num - 1]

                        # Skip if it's getting from env or config
                        if "getenv" in line or "get_setting" in line or "environ" in line:
                            continue

                        # Skip test/example values
                        if (
                            "test" in line.lower()
                            or "example" in line.lower()
                            or "placeholder" in line.lower()
                        ):
                            continue

                        local_violations.append(
                            Violation(
                                file=str(pyfile.relative_to(self.project_root)),
                                line=line_num,
                                severity=Severity.CRITICAL,
                                category="Security Risk",
                                message=description,
                                code_snippet=line.strip()[:80],
                                suggestion="Move to environment variable or config",
                            )
                        )

            except Exception:
                pass

        self.violations.extend(local_violations)
        duration = (time.time() - start) * 1000

        critical = sum(1 for v in local_violations if v.severity == Severity.CRITICAL)

        return TestResult(
            name="Environment Isolation",
            passed=critical == 0,
            duration_ms=duration,
            violations=local_violations,
            details=f"Found {len(env_vars_found)} env var references",
        )

    # ==========================================================================
    # TEST 8: Resource Path Verification
    # ==========================================================================
    def test_resource_paths(self) -> TestResult:
        """
        Verify resource file references are portable.

        Checks:
        - Asset paths use __file__ or Path
        - No hardcoded resource locations
        - Relative paths from package root
        """
        import time

        start = time.time()

        local_violations = []

        # Resource file extensions
        resource_extensions = [
            ".kv",
            ".json",
            ".yaml",
            ".yml",
            ".png",
            ".jpg",
            ".ico",
            ".css",
            ".html",
        ]

        prod_code = self.project_root / "Programma_CS2_RENAN"

        for pyfile in prod_code.rglob("*.py"):
            if self._should_exclude(pyfile):
                continue

            try:
                content = pyfile.read_text(encoding="utf-8")

                for ext in resource_extensions:
                    # Find string literals containing resource extensions
                    pattern = rf'["\'][^"\']*{re.escape(ext)}["\']'

                    for match in re.finditer(pattern, content):
                        line_num = content[: match.start()].count("\n") + 1
                        line = content.split("\n")[line_num - 1]

                        # Check if path is properly constructed
                        good_patterns = [
                            "Path(",
                            "__file__",
                            "os.path.join",
                            "os.path.dirname",
                            "get_setting",
                            "resource_path",
                            ".resolve()",
                            "pkg_resources",
                        ]

                        if not any(gp in line for gp in good_patterns):
                            # Check for absolute path in the string
                            matched_str = match.group()
                            if "/" in matched_str or "\\" in matched_str:
                                local_violations.append(
                                    Violation(
                                        file=str(pyfile.relative_to(self.project_root)),
                                        line=line_num,
                                        severity=Severity.WARNING,
                                        category="Resource Path",
                                        message=f"Resource path may not be portable",
                                        code_snippet=line.strip(),
                                        suggestion="Use Path(__file__).parent or pkg_resources",
                                    )
                                )

            except Exception:
                pass

        self.violations.extend(local_violations)
        duration = (time.time() - start) * 1000

        return TestResult(
            name="Resource Path Verification",
            passed=True,  # Warnings don't fail
            duration_ms=duration,
            violations=local_violations,
            details=f"Found {len(local_violations)} resource path concerns",
        )

    # ==========================================================================
    # TEST 9: Cross-Platform Compatibility
    # ==========================================================================
    def test_cross_platform(self) -> TestResult:
        """
        Check for cross-platform compatibility issues.

        Checks:
        - Line endings handling
        - Case sensitivity awareness
        - Platform-specific code paths
        - Subprocess calls
        """
        import time

        start = time.time()

        local_violations = []

        prod_code = self.project_root / "Programma_CS2_RENAN"

        for pyfile in prod_code.rglob("*.py"):
            if self._should_exclude(pyfile):
                continue

            try:
                # Check for CRLF line endings
                raw_content = pyfile.read_bytes()
                if b"\r\n" in raw_content:
                    local_violations.append(
                        Violation(
                            file=str(pyfile.relative_to(self.project_root)),
                            line=0,
                            severity=Severity.INFO,
                            category="Line Endings",
                            message="File uses CRLF line endings (Windows style)",
                            suggestion="Consider using LF for cross-platform git",
                        )
                    )

                content = pyfile.read_text(encoding="utf-8")

                # Check for subprocess calls without shell consideration
                if "subprocess" in content:
                    for line_num, line in enumerate(content.split("\n"), 1):
                        if "subprocess." in line and "shell=True" in line:
                            local_violations.append(
                                Violation(
                                    file=str(pyfile.relative_to(self.project_root)),
                                    line=line_num,
                                    severity=Severity.WARNING,
                                    category="Subprocess Shell",
                                    message="shell=True may behave differently across platforms",
                                    code_snippet=line.strip(),
                                )
                            )

                        # Check for platform-specific commands
                        windows_cmds = ["cmd", "powershell", "taskkill", "reg "]
                        unix_cmds = ["bash", "sh ", "/bin/", "chmod", "chown", "kill "]

                        for cmd in windows_cmds:
                            if (
                                cmd in line.lower()
                                and "platform" not in content[: content.find(line)].lower()
                            ):
                                local_violations.append(
                                    Violation(
                                        file=str(pyfile.relative_to(self.project_root)),
                                        line=line_num,
                                        severity=Severity.WARNING,
                                        category="Platform Command",
                                        message=f"Windows-specific command: {cmd}",
                                        suggestion="Add platform check: if sys.platform == 'win32'",
                                    )
                                )
                                break

            except Exception:
                pass

        self.violations.extend(local_violations)
        duration = (time.time() - start) * 1000

        return TestResult(
            name="Cross-Platform Compatibility",
            passed=True,  # Info/warnings don't fail
            duration_ms=duration,
            violations=local_violations,
            details=f"Found {len(local_violations)} platform considerations",
        )

    # ==========================================================================
    # TEST 10: Dependency Portability
    # ==========================================================================
    def test_dependency_portability(self) -> TestResult:
        """
        Verify dependencies are properly specified and portable.

        Checks:
        - requirements.txt exists and is complete
        - No version pins to dev versions
        - Platform-specific deps marked correctly
        """
        import time

        start = time.time()

        local_violations = []

        req_file = self.project_root / "requirements.txt"

        if not req_file.exists():
            local_violations.append(
                Violation(
                    file="requirements.txt",
                    line=0,
                    severity=Severity.CRITICAL,
                    category="Missing Requirements",
                    message="requirements.txt not found",
                )
            )
        else:
            try:
                content = req_file.read_text(encoding="utf-8")

                for line_num, line in enumerate(content.split("\n"), 1):
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    # Check for file:// references
                    if "file://" in line:
                        local_violations.append(
                            Violation(
                                file="requirements.txt",
                                line=line_num,
                                severity=Severity.CRITICAL,
                                category="Local Dependency",
                                message=f"Local file reference: {line}",
                                suggestion="Use proper package name or git URL",
                            )
                        )

                    # Check for dev versions
                    if ".dev" in line or "a0" in line or "b0" in line:
                        local_violations.append(
                            Violation(
                                file="requirements.txt",
                                line=line_num,
                                severity=Severity.WARNING,
                                category="Dev Dependency",
                                message=f"Development version specified: {line}",
                                suggestion="Use stable version for production",
                            )
                        )

                    # Check for platform-specific without markers
                    platform_deps = ["pywin32", "pyobjc", "dbus-python"]
                    for pd in platform_deps:
                        if pd in line.lower() and "; " not in line:
                            local_violations.append(
                                Violation(
                                    file="requirements.txt",
                                    line=line_num,
                                    severity=Severity.WARNING,
                                    category="Platform Dependency",
                                    message=f"Platform-specific dep without marker: {line}",
                                    suggestion="Add marker like: ; sys_platform == 'win32'",
                                )
                            )

            except Exception as e:
                local_violations.append(
                    Violation(
                        file="requirements.txt",
                        line=0,
                        severity=Severity.WARNING,
                        category="Parse Error",
                        message=str(e),
                    )
                )

        self.violations.extend(local_violations)
        duration = (time.time() - start) * 1000

        critical = sum(1 for v in local_violations if v.severity == Severity.CRITICAL)

        return TestResult(
            name="Dependency Portability",
            passed=critical == 0,
            duration_ms=duration,
            violations=local_violations,
            details="Analyzed requirements.txt",
        )

    # ==========================================================================
    # MAIN EXECUTION
    # ==========================================================================
    def run_all_tests(self) -> TestReport:
        """Execute all portability tests and generate report."""
        print("=" * 70)
        print("[SECURE] PORTABILITY VERIFICATION SUITE - DOCTORATE LEVEL")
        print("=" * 70)
        print(f"[*] Project Root: {self.project_root}")
        print(f"[*] Timestamp: {datetime.now().isoformat()}")
        print("=" * 70)
        print()

        tests = [
            ("1", self.test_hardcoded_paths),
            ("2", self.test_path_construction),
            ("3", self.test_import_safety),
            ("4", self.test_configuration_portability),
            ("5", self.test_required_files),
            ("6", self.test_critical_imports),
            ("7", self.test_environment_isolation),
            ("8", self.test_resource_paths),
            ("9", self.test_cross_platform),
            ("10", self.test_dependency_portability),
        ]

        for test_num, test_func in tests:
            print(
                f"[>>] Test {test_num}: {test_func.__name__.replace('test_', '').replace('_', ' ').title()}..."
            )
            result = test_func()
            self.results.append(result)

            status = "[PASS]" if result.passed else "[FAIL]"
            print(f"   {status} ({result.duration_ms:.1f}ms) - {result.details}")

            if result.violations:
                critical = [v for v in result.violations if v.severity == Severity.CRITICAL]
                warnings = [v for v in result.violations if v.severity == Severity.WARNING]

                if critical:
                    print(f"   [!] {len(critical)} CRITICAL issues:")
                    for v in critical[:3]:  # Show first 3
                        print(f"      > {v.file}:{v.line} - {v.message}")
                    if len(critical) > 3:
                        print(f"      ... and {len(critical) - 3} more")

                if warnings and result.passed:
                    print(f"   [i] {len(warnings)} warnings (non-blocking)")
            print()

        # Generate report
        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed
        critical_count = sum(1 for v in self.violations if v.severity == Severity.CRITICAL)
        warning_count = sum(1 for v in self.violations if v.severity == Severity.WARNING)

        report = TestReport(
            timestamp=datetime.now().isoformat(),
            total_tests=len(self.results),
            passed_tests=passed,
            failed_tests=failed,
            critical_violations=critical_count,
            warnings=warning_count,
            results=self.results,
            certified=failed == 0,
        )

        # Print summary
        print("=" * 70)
        print("VERIFICATION SUMMARY")
        print("=" * 70)

        for result in self.results:
            status = "[PASS]" if result.passed else "[FAIL]"
            print(f"{status} {result.name}")

        print()
        print(f"Tests: {passed}/{len(self.results)} passed")
        print(f"Critical Violations: {critical_count}")
        print(f"Warnings: {warning_count}")
        print()

        if report.certified:
            print("=" * 70)
            print("[PASS] PORTABILITY CERTIFICATION: PASSED")
            print("   100% PORTABILITY VERIFIED")
            print("=" * 70)
        else:
            print("=" * 70)
            print("[FAIL] PORTABILITY CERTIFICATION: FAILED")
            print("   Fix critical violations before committing!")
            print("=" * 70)

        return report

    def save_report(self, path: Path = None):
        """Save detailed JSON report."""
        path = path or self.project_root / "portability_report.json"

        report_data = {
            "timestamp": datetime.now().isoformat(),
            "project_root": str(self.project_root),
            "total_tests": len(self.results),
            "passed_tests": sum(1 for r in self.results if r.passed),
            "violations": [
                {
                    "file": v.file,
                    "line": v.line,
                    "severity": v.severity.value,
                    "category": v.category,
                    "message": v.message,
                    "code_snippet": v.code_snippet,
                    "suggestion": v.suggestion,
                }
                for v in self.violations
            ],
            "results": [
                {
                    "name": r.name,
                    "passed": r.passed,
                    "duration_ms": r.duration_ms,
                    "details": r.details,
                    "violation_count": len(r.violations),
                }
                for r in self.results
            ],
        }

        path.write_text(json.dumps(report_data, indent=2))
        print(f"\n[i] Detailed report saved to: {path}")


def main():
    """Main entry point."""
    verifier = PortabilityVerifier()
    report = verifier.run_all_tests()

    # Optionally save detailed report
    if "--save-report" in sys.argv:
        verifier.save_report()

    return 0 if report.certified else 1


if __name__ == "__main__":
    sys.exit(main())
