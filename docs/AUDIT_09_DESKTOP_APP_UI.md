# AUDIT_09: Desktop App & UI
## Date: 2026-03-10
## Scope: 20 files (~5,958 lines)

---

### 1. Executive Summary

| Metric | Count |
|--------|-------|
| Files audited | 20 |
| Total lines | ~5,958 |
| HIGH findings | 1 |
| MEDIUM findings | 15 |
| LOW findings | 9 |

The desktop app follows a well-structured MVVM pattern with EventDispatcher-based ViewModels, daemon threads for background data loading, and `Clock.schedule_once` for UI-thread marshaling. The architecture is sound and mostly consistent.

The single HIGH finding concerns ~20+ hardcoded English strings in `layout.kv` that bypass the i18n system, causing mixed-language UI for non-English users. Medium findings cluster around code duplication between screens, inconsistent ORM API usage within ViewModels, and missing safeguards (cancellation support, `is_loading` reset guarantees).

**Cross-references:** Report 5 (coaching_service.py — CoachingDialogue is the backend for coaching_chat_vm.py), Report 6 (database.py — get_db_manager used by data_viewmodels.py), Report 8 (session_engine.py — PlaybackEngine used by tactical_viewmodels.py).

---

### 2. File-by-File Findings

#### `Programma_CS2_RENAN/apps/desktop_app/__init__.py` (1 line)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| — | — | — | — | No findings — empty module init | — |

---

#### `Programma_CS2_RENAN/apps/desktop_app/coaching_chat_vm.py` (138 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| — | — | — | — | No findings — clean MVVM with `threading.Lock` for messages (F7-24), daemon threads, lazy engine import, `Clock.schedule_once` marshaling | — |

---

#### `Programma_CS2_RENAN/apps/desktop_app/data_viewmodels.py` (305 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| U-01 | MEDIUM | Correctness | 128-244 | `MatchDetailViewModel` has no cancellation support (no `_cancel` Event) unlike `MatchHistoryViewModel` (DV-01). If user navigates away during load and returns, stale results could overwrite fresh data on the UI thread. | Add `_cancel = Event()` and check it before `Clock.schedule_once` in `_bg_load`, matching the MatchHistoryViewModel pattern. |
| U-02 | MEDIUM | Code Quality | 152-176 vs 69-78 | Inconsistent ORM API within the same file: `MatchDetailViewModel._bg_load` uses `session.query()` (SQLAlchemy 1.x), while `MatchHistoryViewModel._bg_load` uses `session.exec(select())` (SQLModel). | Standardize on `session.exec(select())` across all ViewModels. |
| U-03 | MEDIUM | Error Handling | 270-293 | `PerformanceViewModel._bg_load` lacks a `finally` block to guarantee `is_loading` reset, unlike `MatchHistoryViewModel` (DV-02). If `analytics.get_rating_history()` raises and the `except` `Clock.schedule_once` itself fails, `is_loading` stays `True` permanently. | Add `finally: Clock.schedule_once(lambda dt: setattr(self, 'is_loading', False), 0)` guard. |

---

#### `Programma_CS2_RENAN/apps/desktop_app/ghost_pixel.py` (140 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| — | — | — | — | No findings — clean debug overlay with P4-09 zero-dimension guard, InstructionGroup separation, SpatialEngine integration | — |

---

#### `Programma_CS2_RENAN/apps/desktop_app/help_screen.py` (79 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| U-04 | LOW | Completeness | 1-79 | F7-09 flag: `help_system` module is not implemented — screen is a placeholder. Topic list and search functionality are wired but non-functional. | Implement or remove from navigation. Low priority — non-blocking for core functionality. |

---

#### `Programma_CS2_RENAN/apps/desktop_app/match_detail_screen.py` (454 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| U-05 | MEDIUM | Code Quality | 32-33, 41-43 | `_MAP_PATTERN` and `_extract_map_name` are duplicated verbatim from `match_history_screen.py`. | Extract to a shared utility (e.g., `theme.py` or a new `ui_utils.py`). |
| U-06 | MEDIUM | Code Quality | 428-453 | `_section_card` helper is duplicated in `performance_screen.py:295-318` with identical logic. | Extract to shared base class or utility module. |

---

#### `Programma_CS2_RENAN/apps/desktop_app/match_history_screen.py` (164 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| — | — | — | — | No unique findings — see U-05 for code duplication with match_detail_screen.py. Clean MVVM pattern with P4-07 color-blind accessible rating labels. | — |

---

#### `Programma_CS2_RENAN/apps/desktop_app/performance_screen.py` (319 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| U-07 | MEDIUM | UX | 116-127 | Horizontal `MDBoxLayout` for map cards (`_build_map_section`) has no `ScrollView` wrapper. If the player has many maps, cards will overflow or be clipped. | Wrap `scroll_row` in a horizontal `ScrollView`. |

---

#### `Programma_CS2_RENAN/apps/desktop_app/player_sidebar.py` (362 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| U-08 | LOW | Code Quality | 48-50 | `radius = [12,]` trailing comma creates a single-element list — works in KivyMD (applies uniform radius) but is unconventional vs `radius = [12]`. | Minor style — no action required. |
| U-09 | LOW | Code Quality | 75, 101, 161 | Commented-out code: `kda_box MDIcon` (line 75), header label (line 101), `weapon_lbl` update (line 161). | Remove if permanently dead, or restore if planned. |
| U-10 | LOW | Robustness | 256 | Team detection uses `"CT" in str(p.team).upper()` — fragile string match when `Team` enum is available and already used in `tactical_viewer_screen.py`. | Use `p.team == Team.CT` for consistency. |

---

#### `Programma_CS2_RENAN/apps/desktop_app/tactical_map.py` (575 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| U-11 | MEDIUM | Correctness | 389 | `time.time()` used for molotov pulsing animation (`math.sin(time.time() * 8)`). This uses wall-clock time which can jump (NTP sync, suspend/resume). | Use `Clock.get_boottime()` or a frame-relative counter for animation consistency. |
| U-12 | LOW | Code Quality | 479 | Redundant `from Programma_CS2_RENAN.core.demo_frame import NadeType` inside `_draw_trajectory` — `NadeType` is already imported at module level (line 25). | Remove the local re-import. |
| U-13 | MEDIUM | Concurrency | 155-160 | `_heatmap_generation_id` is written from the main thread and read from the background thread without synchronization. The race is benign under CPython's GIL (simple attribute read/write), but is not formally thread-safe. | Document GIL reliance or use `threading.Event` for cancellation (matching TM-03 pattern already in use). |

---

#### `Programma_CS2_RENAN/apps/desktop_app/tactical_viewer_screen.py` (293 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| U-14 | LOW | Code Quality | 285-292 | Legacy backward-compatibility properties (`critical_moments`, `_scan_for_cms`) add minor tech debt. | Remove if no external consumers rely on these names. |

---

#### `Programma_CS2_RENAN/apps/desktop_app/tactical_viewmodels.py` (347 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| U-15 | MEDIUM | Code Quality | 29-37 | Non-PEP8 import ordering: `CM_NAVIGATION_BUFFER_TICKS` constant defined at line 29, then `from kivy.clock import Clock` and other imports at lines 30-37, after function-level code. | Move all imports to top of file after docstring. |
| U-16 | LOW | Robustness | 165-168 | `GhostVM.predict_ghosts` catches all exceptions per-player and logs a warning. While good for resilience, systematic failures (e.g., model file missing) would produce N warnings per frame (~10/frame × 64fps). | Add a circuit breaker or failure counter to suppress after N consecutive failures. |

---

#### `Programma_CS2_RENAN/apps/desktop_app/theme.py` (32 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| — | — | — | — | No findings — clean module with WCAG-compliant text labels (P4-07), standard HLTV thresholds. | — |

---

#### `Programma_CS2_RENAN/apps/desktop_app/timeline.py` (113 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| U-17 | MEDIUM | Performance | 91-112 | No event density throttling — every game event draws a Rectangle every frame. Matches with hundreds of kills will draw hundreds of rects each `_redraw` call (triggered by `current_tick` property changes at 10Hz). | Batch events into a cached InstructionGroup; only rebuild when `set_events` is called. |

---

#### `Programma_CS2_RENAN/apps/desktop_app/widgets.py` (272 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| U-18 | MEDIUM | Performance | all `plot()` methods | All `plot()` methods create matplotlib figures and call `fig.savefig()` → PNG → texture on the main thread (via `Clock.schedule_once` with 0.1s delay from callers). For complex data, `savefig()` can block 100-500ms, causing UI jank. | Move `fig.savefig()` to a background thread (only texture creation must be on main thread — already handled by `_set_texture`). |

---

#### `Programma_CS2_RENAN/apps/desktop_app/wizard_screen.py` (417 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| U-19 | MEDIUM | Code Quality | 401-402 | Dead imports: `import subprocess` and `import sys` inside `finish_setup()` are never used — the daemon launch code was removed but imports remained. | Remove both unused imports. |
| U-20 | LOW | Code Quality | 410-416 | Overly broad `try/except Exception` around a single `self.manager.current = "home"` assignment. | Narrow to specific exceptions or remove if `Screen.manager` assignment can't fail. |

---

#### `Programma_CS2_RENAN/apps/desktop_app/layout.kv` (1584 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| U-21 | HIGH | i18n / UX | Throughout | ~20+ hardcoded English strings bypass the i18n system: "Loss (T/V)" (101), "ETA" (120), "Quota: 0/10…" (251), "Set Folder" (266), "Eco (6h)" (334), "Standard (1h)" (338), "Turbo" (346), "Steam" (390), "Tactical Overlay" (588), "Positioning" (754), "Utility" (762), "What to improve?" (770), "Ask your coach…" (785), Steam API description (974), "Ingestion Mode:" (1207), "Manual" (1221), "Auto" (1228), "Scan Interval (min):" (1231), "Set" (1251), "Start Ingestion Now" (1264), "Stop Ingestion" (1271), "Match Detail" (1551), "Performance Dashboard" (1572), "GHOST" (1457), "Tick: 0" (1435). Users selecting PT or IT see mixed English/translated UI. | Add i18n keys for all hardcoded strings. Quick actions (lines 754/762/770) already pass i18n keys to `send_quick_action` but display hardcoded English button text. |
| U-22 | MEDIUM | UX | 362, 400 | Hardcoded `height: "140dp"` on API & Profile card (line 362) and Tactical Analysis card (line 400). Content could overflow or leave excessive whitespace depending on i18n text lengths. | Use `adaptive_height: True` with `size_hint_y: None` like other cards. |
| U-23 | MEDIUM | Accessibility | 1438-1464 | Debug and Ghost toggle switches use only labels ("Debug", "GHOST") with no WCAG-compliant hint or tooltip. The Switch widget itself has no accessible description. | Add `hint_text` or use `MDSwitch` with built-in accessibility support. |

---

#### `Programma_CS2_RENAN/assets/i18n/en.json` (113 lines, 112 keys)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| — | — | — | — | No findings — complete key set, well-organized. | — |

---

#### `Programma_CS2_RENAN/assets/i18n/pt.json` (113 lines, 112 keys)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| — | — | — | — | No findings — complete, all 112 keys match en.json. | — |

---

#### `Programma_CS2_RENAN/assets/i18n/it.json` (113 lines, 112 keys)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| U-24 | LOW | i18n | 60 | Typo: `"usa una cartella como"` — "como" is Portuguese/Spanish. Correct Italian is "come" → `"usa una cartella come"`. | Fix typo: `como` → `come`. |

---

### 3. Cross-Cutting Concerns

**3.1 MVVM Consistency**
The MVVM pattern is well-established across 6 ViewModels (coaching_chat_vm, 3× data_viewmodels, 3× tactical_viewmodels). However, the safety guarantees are inconsistent:
- `MatchHistoryViewModel` has cancellation (DV-01) + `finally` guard (DV-02)
- `MatchDetailViewModel` has neither cancellation nor `finally` guard
- `PerformanceViewModel` has neither

**3.2 Code Duplication**
Three patterns are duplicated across screen files:
1. `_extract_map_name` + `_MAP_PATTERN` (match_history + match_detail)
2. `_section_card` helper (match_detail + performance)
3. `_show_placeholder` pattern (all screens — same implementation but not shared)

**3.3 i18n Coverage Gap**
The i18n infrastructure (`i18n.get_text()`) works well for most UI text. However, `layout.kv` has ~20+ hardcoded English strings (U-21), and 3 quick action buttons display English text while passing i18n keys to the handler. This creates a jarring mixed-language experience for PT/IT users.

**3.4 Matplotlib on Main Thread**
All 6 chart widgets call `fig.savefig()` on the Kivy main thread. While deferred by 0.1s via `Clock.schedule_once`, the actual PNG rendering is CPU-intensive and blocks the UI. The existing `MatplotlibWidget.update_plot` architecture already separates texture creation (`_set_texture`) from rendering — the rendering step should be moved to a daemon thread.

---

### 4. Inter-Module Dependency Risks

| This Module | Depends On | Risk |
|-------------|-----------|------|
| `data_viewmodels.py` | `backend/storage/database.py`, `backend/reporting/analytics.py` | DB session lifetime — sessions are correctly scoped with `with get_db_manager().get_session()` |
| `tactical_map.py` | `core/spatial_engine.py`, `core/map_manager.py` | Map metadata changes would break coordinate transforms |
| `tactical_viewmodels.py` | `backend/nn/inference/ghost_engine.py`, `backend/nn/rap_coach/chronovisor_scanner.py` | Lazy imports protect startup, but model loading failures in ghost engine would spam warnings (U-16) |
| `wizard_screen.py` | `core/config.py`, `core/platform_utils.py` | `get_available_drives()` is Windows-only; Linux path defaults to `~` |
| `layout.kv` | All screen classes, `core/localization.py` | KV references Python classes by name — renaming classes breaks layout |

---

### 5. Remediation Priority Matrix

| Priority | ID | Severity | Effort | Description |
|----------|----|----------|--------|-------------|
| 1 | U-21 | HIGH | Medium | Add i18n keys for ~20+ hardcoded English strings in layout.kv |
| 2 | U-01 | MEDIUM | Low | Add cancellation support to MatchDetailViewModel |
| 3 | U-03 | MEDIUM | Low | Add `finally` guard to PerformanceViewModel._bg_load |
| 4 | U-18 | MEDIUM | Medium | Move matplotlib savefig to background thread |
| 5 | U-17 | MEDIUM | Low | Cache timeline event markers in InstructionGroup |
| 6 | U-05/U-06 | MEDIUM | Low | Extract duplicated helpers to shared module |
| 7 | U-02 | MEDIUM | Low | Standardize on session.exec(select()) |
| 8 | U-07 | MEDIUM | Low | Wrap map cards in horizontal ScrollView |
| 9 | U-19 | MEDIUM | Trivial | Remove dead subprocess/sys imports |
| 10 | U-11 | MEDIUM | Low | Use Kivy clock time for animations |
| 11 | U-13 | MEDIUM | Low | Document GIL reliance or use Event for heatmap gen |
| 12 | U-15 | MEDIUM | Trivial | Fix import ordering in tactical_viewmodels.py |
| 13 | U-22 | MEDIUM | Low | Use adaptive_height on hardcoded-height cards |
| 14 | U-23 | MEDIUM | Low | Add accessible descriptions to toggle switches |
| 15 | U-24 | LOW | Trivial | Fix Italian typo "como" → "come" |

---

### 6. Coverage Attestation

All 20 files in the Desktop App & UI domain were read in full and analyzed:

- [x] `apps/desktop_app/__init__.py` (1 line)
- [x] `apps/desktop_app/coaching_chat_vm.py` (138 lines)
- [x] `apps/desktop_app/data_viewmodels.py` (305 lines)
- [x] `apps/desktop_app/ghost_pixel.py` (140 lines)
- [x] `apps/desktop_app/help_screen.py` (79 lines)
- [x] `apps/desktop_app/match_detail_screen.py` (454 lines)
- [x] `apps/desktop_app/match_history_screen.py` (164 lines)
- [x] `apps/desktop_app/performance_screen.py` (319 lines)
- [x] `apps/desktop_app/player_sidebar.py` (362 lines)
- [x] `apps/desktop_app/tactical_map.py` (575 lines)
- [x] `apps/desktop_app/tactical_viewer_screen.py` (293 lines)
- [x] `apps/desktop_app/tactical_viewmodels.py` (347 lines)
- [x] `apps/desktop_app/theme.py` (32 lines)
- [x] `apps/desktop_app/timeline.py` (113 lines)
- [x] `apps/desktop_app/widgets.py` (272 lines)
- [x] `apps/desktop_app/wizard_screen.py` (417 lines)
- [x] `apps/desktop_app/layout.kv` (1584 lines)
- [x] `assets/i18n/en.json` (113 lines)
- [x] `assets/i18n/pt.json` (113 lines)
- [x] `assets/i18n/it.json` (113 lines)

**Total: 20 files, ~5,958 lines audited.**
