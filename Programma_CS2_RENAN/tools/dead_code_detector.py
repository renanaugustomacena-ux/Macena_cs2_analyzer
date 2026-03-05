#!/usr/bin/env python3
"""
Dead Code & Orphan Detector — Pre-commit hook for Macena CS2 Analyzer.

Scans for:
  1. Python modules not imported by any other module
  2. Test files that reference modules no longer present
  3. Orphaned __init__.py in empty packages

Exit codes: 0 = clean (or warnings only), 1 = critical orphans found
"""

import ast
import sys
from pathlib import Path

from _infra import SOURCE_ROOT, BaseValidator, Severity

# Directories excluded from orphan detection (standalone entry points, tools, tests)
_EXCLUDED_DIRS = {
    "tools", "tests", "__pycache__",
    "apps",   # F8-18: KivyMD screens loaded dynamically by MDScreenManager, not via Python import
}
_EXCLUDED_FILES = {"__init__.py", "conftest.py", "setup.py"}


class DeadCodeDetector(BaseValidator):

    def __init__(self):
        super().__init__("Dead Code & Orphan Detector", version="1.0")

    def define_checks(self):
        self._detect_orphan_modules()
        self._detect_stale_test_imports()

    def _detect_orphan_modules(self):
        self.console.section("Orphan Module Scan", 1, 2)

        # Collect all production .py files
        prod_files = self._get_production_files()
        if not prod_files:
            self.check(
                "Orphans",
                "Production files found",
                False,
                error="No .py files found in SOURCE_ROOT",
            )
            return

        # Build import graph: which modules are imported by others
        imported_modules: set = set()
        for f in prod_files:
            imported_modules.update(self._extract_imports(f))

        # Check each module: is it imported by at least one other?
        orphan_count = 0
        for f in prod_files:
            if f.name in _EXCLUDED_FILES:
                continue
            module_name = self._file_to_module(f)
            if not module_name:
                continue

            # A module is "imported" if an exact match or dot-delimited prefix exists
            is_imported = any(
                imp == module_name or imp.startswith(module_name + ".")  # F8-03: dot-delimited boundary
                for imp in imported_modules
            )

            if not is_imported:
                orphan_count += 1
                self.check(
                    "Orphans",
                    f"Potentially unused: {f.relative_to(SOURCE_ROOT)}",
                    False,
                    severity=Severity.WARNING,
                    error="Not imported by any other production module",
                )

        if orphan_count == 0:
            self.check(
                "Orphans",
                "No orphaned modules detected",
                True,
                detail=f"Scanned {len(prod_files)} files",
            )
        else:
            self.check(
                "Orphans",
                f"{orphan_count} potentially orphaned module(s)",
                True,  # warnings don't block
                detail="Review manually — may be entry points or dynamic imports",
                severity=Severity.WARNING,
            )

    def _detect_stale_test_imports(self):
        self.console.section("Stale Test Import Scan", 2, 2)

        test_dir = SOURCE_ROOT / "tests"
        if not test_dir.exists():
            self.check("Stale Tests", "Test directory exists", False, severity=Severity.WARNING)
            return

        test_files = list(test_dir.rglob("test_*.py"))  # F8-26: capture once to avoid redundant rglob
        stale_count = 0
        for tf in sorted(test_files):
            imports = self._extract_imports(tf)
            for imp in imports:
                if not imp.startswith("Programma_CS2_RENAN"):
                    continue
                # Check if the referenced module file exists
                parts = imp.split(".")
                candidate = SOURCE_ROOT.parent
                for p in parts:
                    candidate = candidate / p
                py_file = candidate.with_suffix(".py")
                pkg_init = candidate / "__init__.py"

                if not py_file.exists() and not pkg_init.exists() and not candidate.is_dir():
                    stale_count += 1
                    self.check(
                        "Stale Tests",
                        f"{tf.name} imports missing: {imp}",
                        False,
                        severity=Severity.WARNING,
                    )

        if stale_count == 0:
            self.check(
                "Stale Tests",
                "No stale test imports found",
                True,
                detail=f"Scanned {len(test_files)} test files",
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_production_files(self) -> list:
        files = []
        for f in SOURCE_ROOT.rglob("*.py"):
            rel = f.relative_to(SOURCE_ROOT)
            parts = rel.parts
            if any(d in parts for d in _EXCLUDED_DIRS):
                continue
            if "__pycache__" in str(f):
                continue
            files.append(f)
        return sorted(files)

    @staticmethod
    def _extract_imports(filepath: Path) -> set:
        imports = set()
        try:
            tree = ast.parse(filepath.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            return imports

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module)
        return imports

    @staticmethod
    def _file_to_module(filepath: Path) -> str:
        try:
            rel = filepath.relative_to(SOURCE_ROOT.parent)
            parts = list(rel.parts)
            if parts[-1] == "__init__.py":
                parts = parts[:-1]
            else:
                parts[-1] = parts[-1].replace(".py", "")
            return ".".join(parts)
        except ValueError:
            return ""


if __name__ == "__main__":
    detector = DeadCodeDetector()
    sys.exit(detector.run())
