"""
Headless dry-run of the Qt app structure.

Verifies that the Qt entry point, MainWindow, all screens, and theme files
are importable and structurally sound — without requiring a display server.
"""

import os
import sys
from pathlib import Path

# --- Venv Guard ---
if sys.prefix == sys.base_prefix and not os.environ.get("CI"):
    print("ERROR: Not in venv. Run: source ~/.venvs/cs2analyzer/bin/activate", file=sys.stderr)
    sys.exit(2)

# Path setup — anchored to __file__, not CWD
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

errors = []

# --- 1. Qt app entry point ---
try:
    print("[-] Importing Qt app module...")
    from Programma_CS2_RENAN.apps.qt_app import app as qt_app_module

    if not hasattr(qt_app_module, "main") or not callable(qt_app_module.main):
        errors.append("qt_app.app missing callable 'main' function")
    else:
        print("[PASS] qt_app.app.main() exists and is callable.")
except Exception as e:
    errors.append(f"Failed to import qt_app.app: {e}")

# --- 2. MainWindow class ---
try:
    print("[-] Importing MainWindow...")
    from Programma_CS2_RENAN.apps.qt_app.main_window import MainWindow

    print("[PASS] MainWindow class imported successfully.")
except Exception as e:
    errors.append(f"Failed to import MainWindow: {e}")

# --- 3. All screen modules ---
screen_modules = [
    "home_screen", "coach_screen", "match_history_screen",
    "performance_screen", "tactical_viewer_screen", "settings_screen",
    "help_screen", "steam_config_screen", "user_profile_screen",
    "profile_screen", "wizard_screen", "match_detail_screen",
    "faceit_config_screen",
]

print("[-] Importing all screen modules...")
import importlib

for mod_name in screen_modules:
    full = f"Programma_CS2_RENAN.apps.qt_app.screens.{mod_name}"
    try:
        importlib.import_module(full)
    except Exception as e:
        errors.append(f"Screen import failed: {full} — {e}")

if not any("Screen import failed" in e for e in errors):
    print(f"[PASS] All {len(screen_modules)} screen modules imported.")

# --- 4. Theme files ---
print("[-] Checking theme files...")
themes_dir = Path(_PROJECT_ROOT) / "Programma_CS2_RENAN" / "apps" / "qt_app" / "themes"
expected_themes = ["cs2.qss", "csgo.qss", "cs16.qss"]
for theme_file in expected_themes:
    path = themes_dir / theme_file
    if not path.exists():
        errors.append(f"Theme file missing: {theme_file}")
    elif path.stat().st_size < 100:
        errors.append(f"Theme file suspiciously small: {theme_file} ({path.stat().st_size} bytes)")

if not any("Theme file" in e for e in errors):
    print(f"[PASS] All {len(expected_themes)} theme files present.")

# --- Summary ---
if errors:
    print(f"\n[CRITICAL FAILURE] {len(errors)} error(s):")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("\n[SUCCESS] Qt app is structurally sound and importable.")
