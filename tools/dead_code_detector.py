import ast
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

# --- Venv Guard ---
if sys.prefix == sys.base_prefix and not os.environ.get("CI"):
    print("ERROR: Not in venv. Run: source ~/.venvs/cs2analyzer/bin/activate", file=sys.stderr)
    sys.exit(2)

# --- Path Stabilization ---
script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# --- Configuration ---
SOURCE_DIR = project_root / "Programma_CS2_RENAN"
TOOLS_DIR = project_root / "tools"
INNER_TOOLS_DIR = SOURCE_DIR / "tools"
ENTRY_POINTS = {
    SOURCE_DIR / "main.py",
    SOURCE_DIR / "apps" / "qt_app" / "app.py",
    project_root / "goliath.py",
    project_root / "console.py",
}
# Add all tools to entry points (project-level and inner)
for tool in TOOLS_DIR.glob("*.py"):
    ENTRY_POINTS.add(tool)
for tool in INNER_TOOLS_DIR.glob("*.py"):
    ENTRY_POINTS.add(tool)
# Standalone entry-point scripts (run directly, never imported)
_STANDALONE_SCRIPTS = [
    SOURCE_DIR / "run_worker.py",
    SOURCE_DIR / "hltv_sync_service.py",
    SOURCE_DIR / "apps" / "spatial_debugger.py",
    SOURCE_DIR / "backend" / "data_sources" / "hltv_scraper.py",
    SOURCE_DIR / "backend" / "ingestion" / "csv_migrator.py",
    SOURCE_DIR / "backend" / "nn" / "rap_coach" / "test_arch.py",
    SOURCE_DIR / "core" / "frozen_hook.py",
    SOURCE_DIR / "Train_ML_Cycle.py",
]
for script in _STANDALONE_SCRIPTS:
    ENTRY_POINTS.add(script)

# Exclusions
EXCLUDE_DIRS = {
    "__pycache__",
    "venv",
    "venv_win",
    ".venv",
    ".git",
    ".idea",
    ".vs",
    ".claude",
    "dist",
    "build",
    "external_libs",
    "external_analysis",
    "docs",
    "reports",
    "packaging",
    "tmp",
    # Test directories (entry points, never imported)
    "tests",
    "forensics",
    # Alembic migration directories (entry points managed by Alembic)
    "versions",
}
EXCLUDE_FILES = {"__init__.py"}
COMMON_NAMES = {
    # Python dunder methods
    "__init__", "__str__", "__repr__", "__call__", "__enter__", "__exit__",
    "__len__", "__getitem__", "__setitem__", "__delitem__", "__iter__",
    "__next__", "__contains__", "__hash__", "__eq__", "__ne__", "__lt__",
    "__gt__", "__le__", "__ge__", "__bool__", "__del__",
    # Test framework
    "setUp", "tearDown", "setUpClass", "tearDownClass",
    # Common entry points
    "run", "main", "execute", "process",
    # PyTorch nn.Module (21+ files override this — standard pattern)
    "forward",
    # Tool-specific patterns (each standalone tool has its own copy)
    "setup_logging", "_signal_handler",
    # Alembic migration patterns (each env.py must define these)
    "run_migrations_offline", "run_migrations_online",
    # Training callbacks (different contexts: CLI vs Console)
    "_build_callbacks",
    # Common interface method names across unrelated modules
    "register", "start", "stop", "get", "set", "close", "reset",
    "connect", "disconnect", "shutdown", "configure", "validate",
    "save", "load", "update", "delete", "create", "build",
    # Alembic migration (every migration file defines these)
    "upgrade", "downgrade",
    # Kivy Screen / Widget lifecycle (overridden per-screen)
    "on_pre_enter", "on_enter", "on_leave", "on_pre_leave",
    "on_start", "on_stop", "on_pause", "on_resume",
    "on_touch_down", "on_touch_move", "on_touch_up",
    "on_press", "on_release", "on_text_validate",
    "select_path", "dismiss",
    # Session management (ViewModel + Service both define these)
    "start_session", "clear_session",
    # Language / localization (main.py delegates to localization module)
    "set_language",
    # Service lifecycle (multiple independent services)
    "stop_service",
    # Debug info (spatial_debugger + ghost_pixel — independent debug views)
    "update_debug_info",
    # File manager / drive selector (main.py + wizard_screen — UI delegation)
    "exit_file_manager", "select_path",
    "_get_available_drives", "_show_drive_selector", "_select_drive",
    # Utility helpers (common private name across unrelated modules)
    "_safe_float", "_safe_int", "_safe_str", "_safe",
    # Training lifecycle callbacks (each trainer defines its own set)
    "on_epoch_end", "on_epoch_start", "on_train_start",
    "on_batch_end", "on_train_end",
    "run_training", "start_training", "stop_training",
    "pause_training", "resume_training", "train_step",
    "_log_epoch", "_finalize_training",
    # Serialization / status (standard patterns across data classes)
    "to_dict", "get_status", "from_dict",
    # Headless validator (each tool defines its own checks)
    "define_checks",
    # Visualization (each widget/chart defines its own plot)
    "plot",
    # Common short method names across unrelated modules
    "add", "check", "evaluate", "generate", "header",
    "is_available", "close_all",
    # NN model patterns (each model defines its own)
    "_create_expert", "_load_model", "get_model",
    "_apply_role_bias", "_extract_features",
    # Kivy UI helpers (each screen builds its own independently)
    "_rating_color", "_show_placeholder", "_section_card",
    "_populate", "_extract_map_name", "_redraw",
    "toggle_playback", "critical_moments",
    "set_on_frame_update", "load_frames",
    "seek_to_tick", "get_current_tick",
    # Common private helpers
    "_cosine_similarity", "_add_extra_args",
    "_init_db", "_save", "_try_import",
    "_health_to_range", "_infer_round_phase",
    # Data source methods (each scraper/syncer has its own)
    "scan_match", "download_demo",
    "run_hltv_sync_cycle", "run_sync_cycle",
    # Common utility functions
    "calculate_sha256", "format_compact",
    "validate_dem_file", "generate_lesson",
    "generate_performance_radar", "set_sqlite_pragma",
    "get_map_asset", "get_map_metadata",
    "_get_production_files",
}

# --- Helpers ---


def get_all_python_files(root: Path) -> List[Path]:
    files = []
    print(f"Scanning root: {root}")
    try:
        for r, d, f in os.walk(root, topdown=True, followlinks=False):
            # Prune hidden dirs and exclusions
            d[:] = [
                dirname
                for dirname in d
                if dirname not in EXCLUDE_DIRS and not dirname.startswith(".")
            ]

            for file in f:
                if file.endswith(".py") and file not in EXCLUDE_FILES:
                    files.append(Path(r) / file)
    except Exception as e:
        print(f"[ERR] Scanning failed at {r}: {e}")
    return files


def get_module_path(file_path: Path, root: Path) -> str:
    """Convert file path to module.path.string"""
    try:
        rel = file_path.relative_to(root)
        return ".".join(rel.with_suffix("").parts)
    except ValueError:
        return ""


def is_file_ignored(content: str) -> bool:
    return "# no-dead-code" in content


# --- Phase A: Orphan Detection ---


def scan_orphans(all_files: List[Path]) -> List[str]:
    print("\n[Phase A] Scanning for Orphan Modules...")

    # 1. Map files to possible import names
    # e.g. defined in Programma_CS2_RENAN/backend/foo.py -> "Programma_CS2_RENAN.backend.foo", "backend.foo"
    file_to_mod: Dict[Path, Set[str]] = {}

    # Files that are entry points are inherently not orphans
    non_orphans = set()

    for f in all_files:
        if f in ENTRY_POINTS:
            non_orphans.add(f)
            continue

        content = f.read_text(encoding="utf-8", errors="ignore")
        if is_file_ignored(content):
            non_orphans.add(f)
            continue

        mods = set()
        # Full project path
        full_mod = get_module_path(f, project_root)
        if full_mod:
            mods.add(full_mod)

        # Inner app path (if inside Programma_CS2_RENAN)
        if SOURCE_DIR in f.parents:
            inner_mod = get_module_path(f, SOURCE_DIR)
            if inner_mod:
                mods.add(inner_mod)

        # Also filename without extension (for local imports in same dir - naive but helpful)
        mods.add(f.stem)

        file_to_mod[f] = mods

    # 2. Scan ALL files for imports of these modules
    # We grep the content because AST import parsing is tricky for all variations
    # and we want to be conservative (if string "backend.foo" appears, assume it's used)

    orphans = []

    # For optimization, build a big text blob of all code? No, memory check.
    # Scan file by file.

    check_files = list(file_to_mod.keys())  # Only check these for orphaned status

    usage_counts = defaultdict(int)

    for scanner_path in all_files:
        content = scanner_path.read_text(encoding="utf-8", errors="ignore")

        for target_file in check_files:
            if target_file == scanner_path:
                continue  # Self-reference doesn't count

            # If any of the target's module paths appear in content
            for mod_name in file_to_mod[target_file]:
                # Simple heuristic: space or start of line + mod_name + space or dot or end
                # Actually, simply checking if the string exists is safer to avoid false positives.
                # If "backend.foo" is in the text, it's likely an import or usage.
                if mod_name in content:
                    usage_counts[target_file] += 1
                    break

    for f in check_files:
        if usage_counts[f] == 0 and f not in non_orphans:
            # Double check: maybe it's imported as "from . import foo"?
            # That would be caught by "foo" check in mods.add(f.stem)
            orphans.append(str(f.relative_to(project_root)))

    return orphans


# --- Phase B: Duplicate Definitions ---


def scan_duplicates(all_files: List[Path]) -> List[str]:
    print("\n[Phase B] Scanning for Duplicate Definitions...")

    definitions = defaultdict(list)  # name -> [files]

    for f in all_files:
        content = f.read_text(encoding="utf-8", errors="ignore")
        if is_file_ignored(content):
            continue

        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    if node.name not in COMMON_NAMES and not node.name.startswith("test_"):
                        definitions[node.name].append(f)
        except SyntaxError:
            pass  # Skip invalid python files

    duplicates = []
    for name, file_list in definitions.items():
        if len(file_list) > 1:
            # Filter out overloads? No, just report.
            # Filter if files are in same directory? Maybe __init__ and impl?
            paths = [str(p.relative_to(project_root)) for p in file_list]
            duplicates.append(f"{name} defined in: {', '.join(paths)}")

    return duplicates


# --- Phase C: Stale Imports ---


def scan_stale_imports(all_files: List[Path]) -> List[str]:
    print("\n[Phase C] Scanning for Stale Imports...")
    stale_reports = []

    for f in all_files:
        content = f.read_text(encoding="utf-8", errors="ignore")
        if is_file_ignored(content):
            continue

        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue

        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    imports.append((n.asname or n.name, n.name))
            elif isinstance(node, ast.ImportFrom):
                for n in node.names:
                    imports.append((n.asname or n.name, f"{node.module}.{n.name}"))

        # Check usage
        # Naive text usage check in the file content (excluding the import lines themselves?)
        # Better: use AST to find Name nodes.

        used_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                used_names.add(node.id)
            elif isinstance(node, ast.Attribute):
                # e.g. module.func - we need to see if 'module' is used
                # This is covered by Name check of the value
                pass

        for alias, original in imports:
            if alias not in used_names:
                # Fallback: Validation via text search (handling comments etc is hard for regex,
                # but valid for "used in string" cases like rigid checks)
                # If it's NOT in AST used_names, it might be unused.
                # BUT: Typings?
                if alias not in content:  # Brutal verify
                    stale_reports.append(f"{f.relative_to(project_root)}: unused import '{alias}'")
                elif f"'{alias}'" in content or f'"{alias}"' in content:
                    # Used in string (e.g. __all__ = ["foo"]) -> Safe
                    pass
                # else:
                #     # It's in content but not in AST load?
                #     # Could be a comment.
                #     # We'll report it as a warning.
                #     pass

    return stale_reports


# --- Main ---


def main():
    print("=" * 60)
    print("DEAD CODE DETECTOR")
    print("=" * 60)

    all_files = get_all_python_files(project_root)
    print(f"Scanned {len(all_files)} Python files.")

    orphans = scan_orphans(all_files)
    duplicates = scan_duplicates(all_files)
    stale = scan_stale_imports(all_files)

    print("\n" + "=" * 30)
    print("SUMMARY")
    print("=" * 30)

    has_issues = False

    if orphans:
        print("\n[WARN] Orphan Modules (0 imports found):")
        for o in orphans:
            print(f"  - {o}")
        has_issues = True  # Orphans are bad
    else:
        print("\n[PASS] No orphan modules found.")

    if duplicates:
        print("\n[INFO] Duplicate Definitions:")
        # Duplicates are often intentional (overrides), so just INFO
        for d in duplicates[:10]:
            print(f"  - {d}")
        if len(duplicates) > 10:
            print(f"  ... and {len(duplicates)-10} more")

    if stale:
        print("\n[WARN] Stale Imports:")
        for s in stale[:20]:
            print(f"  - {s}")
        if len(stale) > 20:
            print(f"  ... and {len(stale)-20} more")
        # Stale imports are warnings

    strict = "--strict" in sys.argv
    if has_issues:
        print("\nVERDICT: Issues found (Review required)")
        sys.exit(1 if strict else 0)
    else:
        print("\nVERDICT: Clean")
        sys.exit(0)


if __name__ == "__main__":
    main()
