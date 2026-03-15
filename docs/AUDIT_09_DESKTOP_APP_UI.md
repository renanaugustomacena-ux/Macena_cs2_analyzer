# Audit Report 09 — Desktop App & UI

**Scope:** `apps/desktop_app/` (Kivy, legacy), `apps/qt_app/` (PySide6/Qt, active), `reporting/` — 57 files | **Date:** 2026-03-10 | **Refreshed:** 2026-03-13
**Open findings:** 3 CRITICAL | 5 HIGH | 7 MEDIUM (Kivy legacy) | 8 LOW (Kivy legacy)

> **Qt Migration Status:** The PySide6/Qt frontend (`apps/qt_app/`) was added in commit 08a0572 (2026-03-13), migrating all 13 screens. The Kivy frontend (`apps/desktop_app/`) is being replaced. This refresh audits the Qt app line-by-line.

---

## CRITICAL Findings (Qt App)

| ID | File | Finding |
|---|---|---|
| QT-C-01 | qt_app/screens/home_screen.py:41 | Typo: `PRO_DEMOS_PATH` instead of `PRO_DEMO_PATH` — dashboard permanently shows "Not set" for pro demo folder. One-character fix. |
| QT-C-02 | qt_app/core/qt_playback_engine.py | Qt playback engine inherits from Kivy-dependent `PlaybackEngine` — hard cross-framework dependency that prevents clean Kivy removal. |
| QT-C-03 | qt_app/screens/steam_config_screen.py:146, faceit_config_screen.py:101 | API keys persisted in plaintext via `save_user_setting()` — violates Rule 5 (no hard-coded secrets, encrypt at rest). |

## HIGH Findings (Qt App)

| ID | File | Finding |
|---|---|---|
| QT-H-01 | qt_app/screens/tactical_viewer_screen.py:33 | `_LoadWorkerSignals` inherits from `Signal` directly (PySide6 Signal, not QObject) — QWidget hack that bypasses Qt's signal/slot type safety. |
| QT-H-02 | qt_app/widgets/tactical/map_widget.py | `time.time()` for molotov animation — wall-clock can jump (NTP sync, suspend/resume). Inherited from Kivy code. Use `QElapsedTimer` instead. |
| QT-H-03 | qt_app/ (multiple screens) | `self.window()` calls throughout screens without null checks — returns None before widget is shown, causing `AttributeError` on early access. |
| QT-H-04 | qt_app/ (20 files, 59 occurrences) | Pervasive i18n gaps — ~59 hardcoded English strings and font references ("Roboto") bypass the i18n system. Mixed-language UI for PT/IT users. |
| QT-H-05 | qt_app/screens/tactical_viewer_screen.py | Silent failure on demo load errors — exception caught but no user-visible feedback. User sees nothing happen. |

## MEDIUM Findings (Kivy Legacy — to be resolved by Kivy removal)

| ID | File | Finding |
|---|---|---|
| U-05 | match_detail_screen.py | `_MAP_PATTERN` and `_extract_map_name` duplicated from match_history_screen.py |
| U-06 | match_detail_screen.py | `_section_card` helper duplicated in performance_screen.py |
| U-07 | performance_screen.py | Map cards in horizontal layout with no ScrollView — overflow risk |
| U-11 | tactical_map.py | `time.time()` for molotov animation — wall-clock can jump |
| U-13 | tactical_map.py | `_heatmap_generation_id` read/write without synchronization |
| U-19 | wizard_screen.py | Dead imports: `subprocess` and `sys` |
| U-22 | layout.kv | Hardcoded `height: "140dp"` instead of adaptive_height |

## LOW Findings (Kivy Legacy)

| ID | File | Finding |
|---|---|---|
| U-04 | help_screen.py | Help system placeholder — not implemented |
| U-08 | player_sidebar.py | `radius = [12,]` trailing comma style |
| U-09 | player_sidebar.py | Commented-out dead code |
| U-10 | player_sidebar.py | Fragile `"CT" in str(p.team).upper()` instead of Team enum |
| U-12 | tactical_map.py | Redundant local NadeType re-import |
| U-14 | tactical_viewer_screen.py | Legacy backward-compatibility properties |
| U-16 | tactical_viewmodels.py | No circuit breaker for systematic ghost prediction failures |
| U-24 | it.json | Typo: "como" (Portuguese) should be "come" (Italian) |

## Cross-Cutting

1. **Dual UI Coexistence** — Both Kivy and Qt apps exist. Kivy is legacy; Qt is active. QT-C-02 (cross-framework dependency) blocks clean Kivy removal.
2. **Worker Pattern Duplication** — `_Worker` + `_WorkerSignals` pattern duplicated across `tactical_vm.py`, `tactical_viewer_screen.py`, and `core/worker.py`. Should consolidate to single shared worker class.
3. **i18n Gaps** — 59 hardcoded English strings across 20 Qt app files. The `i18n_bridge.py` system exists but is not consistently used.
4. **Reporting Module** — `reporting/visualizer.py` uses `plt.close(fig)` in `finally` block (correct). `reporting/report_generator.py` generates placeholder markdown reports with hardcoded text.

## Resolved Since 2026-03-10

Removed 4 MEDIUM findings (U-01, 02, 03, 18) and 2 LOW (U-15, 23) from Kivy audit — fixed in commits f480664..45514a2. U-21 (i18n) persists in Qt app as QT-H-04.
