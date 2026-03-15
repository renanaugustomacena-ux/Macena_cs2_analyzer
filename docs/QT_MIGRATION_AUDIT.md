# Macena CS2 Analyzer — Comprehensive Frontend Migration Audit

> **Author**: Renan Augusto Macena
> **Date**: 2026-03-12
> **Scope**: Full assessment of the new Qt frontend, the old Kivy frontend, and industrial-grade implementation plan.
> **Companion Document**: [QT_MIGRATION_RULES.md](QT_MIGRATION_RULES.md)

---

# ════════════════════════════════════════════════════════════════
# SECTION 1: NEW QT FRONTEND — COMPLETE ASSESSMENT
# ════════════════════════════════════════════════════════════════

## 1.1 Executive Summary

The Qt frontend (`Programma_CS2_RENAN/apps/qt_app/`) is a **Phase 1 skeleton** built on PySide6. It contains **3 fully functional data screens** (Match History, Match Detail, Performance), **6 native chart widgets**, and **10 placeholder screens** that display only a title and description message. The app boots, themes correctly, and connects to the backend database. The reason all pages appear "empty" is that 10 of 13 screens are intentionally stubbed out with `PlaceholderScreen` widgets showing centered text like "Dashboard — Training status, coaching hub, connectivity."

### Maturity Matrix

| Area | Status | Notes |
|------|--------|-------|
| App bootstrap & entry point | **Complete** | High-DPI, theme, window creation |
| Sidebar navigation | **Complete** | 7 nav items, i18n, checked state |
| Theme engine (QSS + QPalette) | **Complete** | 3 themes: CS2, CSGO, CS1.6 |
| Localization bridge | **Complete** | 3 languages, Signal-based, JSON + fallback |
| Asset loading (maps) | **Complete** | QPixmap cache, checkered fallback |
| Background worker pattern | **Complete** | QRunnable + Signal auto-marshaling |
| Match History screen | **Complete** | Scrollable cards, rating badges, click → detail |
| Match Detail screen | **Complete** | 4 tabs: Overview, Rounds, Economy, Highlights |
| Performance screen | **Complete** | Rating trend, per-map stats, S/W, utility |
| 6 chart widgets | **Complete** | Radar, Economy, Momentum, Sparkline, Trend, Utility |
| Dashboard (Home) | **Placeholder** | Only title + description text |
| AI Coach screen | **Placeholder** | Only title + description text |
| Tactical Viewer | **Placeholder** | Only title + description text |
| Settings screen | **Placeholder** | Only title + description text |
| Setup Wizard | **Placeholder** | Only title + description text |
| Player Profile | **Placeholder** | Only title + description text |
| Edit Profile | **Placeholder** | Only title + description text |
| Steam Config | **Placeholder** | Only title + description text |
| FaceIT Config | **Placeholder** | Only title + description text |
| Help screen | **Placeholder** | Only title + description text |

---

## 1.2 File Inventory (Every File)

### Source Files (non-cache)

```
qt_app/
├── __init__.py                          (1 line — package marker)
├── app.py                               (80 lines — entry point)
├── main_window.py                       (145 lines — QMainWindow + sidebar)
├── core/
│   ├── __init__.py                      (1 line)
│   ├── theme_engine.py                  (135 lines — QSS loader, palettes, rating colors)
│   ├── i18n_bridge.py                   (115 lines — Qt localization, 3 languages)
│   ├── asset_bridge.py                  (120 lines — QPixmap map loader)
│   └── worker.py                        (59 lines — QRunnable background worker)
├── screens/
│   ├── __init__.py                      (1 line)
│   ├── placeholder.py                   (78 lines — 13 placeholder screen definitions)
│   ├── match_history_screen.py          (174 lines — FUNCTIONAL match list)
│   ├── match_detail_screen.py           (315 lines — FUNCTIONAL tabbed detail)
│   └── performance_screen.py            (253 lines — FUNCTIONAL analytics dashboard)
├── viewmodels/
│   ├── __init__.py                      (1 line)
│   ├── match_history_vm.py              (97 lines — loads 50 matches from DB)
│   ├── match_detail_vm.py               (143 lines — loads stats/rounds/insights/HLTV)
│   └── performance_vm.py                (72 lines — loads analytics from backend)
├── widgets/
│   ├── __init__.py                      (1 line)
│   ├── charts/
│   │   ├── __init__.py                  (1 line)
│   │   ├── radar_chart.py               (118 lines — QPainter polar spider chart)
│   │   ├── economy_chart.py             (83 lines — QtCharts grouped bar)
│   │   ├── momentum_chart.py            (108 lines — QtCharts area, green/red fill)
│   │   ├── rating_sparkline.py          (97 lines — QtCharts area with ref lines)
│   │   ├── trend_chart.py               (92 lines — QtCharts dual-axis line)
│   │   └── utility_bar_chart.py         (76 lines — QtCharts horizontal bar)
│   └── tactical/
│       └── __init__.py                  (0 lines — empty, not yet implemented)
└── themes/
    ├── cs2.qss                          (307 lines — dark gaming, orange accent)
    ├── csgo.qss                         (CSGO blue palette variant)
    └── cs16.qss                         (CS1.6 green palette variant)
```

**Total**: ~2,200 lines of Python + ~307 lines QSS = ~2,500 lines

---

## 1.3 Entry Point — `app.py` (80 lines)

```python
# Line-by-line flow:
1.  Imports: sys, Qt, QApplication, ThemeEngine, MainWindow, create_placeholder_screens
2.  main():
3.    Enable high-DPI scaling (PassThrough rounding policy)
4.    Create QApplication(sys.argv)
5.    Set app name: "Macena CS2 Analyzer"
6.    Create ThemeEngine instance
7.    Apply "CS2" theme (loads cs2.qss + sets QPalette)
8.    Create MainWindow (sidebar + QStackedWidget content area)
9.    Create 13 placeholder screens via create_placeholder_screens()
10.   Lazy-import 3 real screens (MatchHistory, MatchDetail, Performance)
11.   Create real screen instances
12.   Wire signal: match_history.match_selected → load match_detail + switch screen
13.   Replace 3 placeholders with real screens in the dict
14.   Register all 13 screens with MainWindow
15.   Start on "home" screen (placeholder)
16.   Store ThemeEngine reference on window for future theme switching
17.   Show window + enter event loop (sys.exit(app.exec()))
```

**Observations**:
- Lazy imports at lines 38-46 prevent circular imports and speed up cold start
- The `_on_match_selected` closure at line 53 is the only cross-screen signal wiring
- No session engine connection — the app currently only reads from database
- No background daemon management — the Qt app is pure UI + read-only DB queries

---

## 1.4 MainWindow — `main_window.py` (145 lines)

### Widget Hierarchy
```
QMainWindow
└── QWidget (central)
    └── QHBoxLayout (margins=0, spacing=0)
        ├── QWidget#nav_sidebar (220px fixed width)
        │   └── QVBoxLayout (margins=8,16,8,16, spacing=4)
        │       ├── QLabel#accent_label "MACENA CS2" (centered)
        │       ├── 20px spacing
        │       ├── _NavButton × 7 (checkable, 40px height each)
        │       ├── QSpacerItem (expanding vertical)
        │       └── QLabel#section_subtitle "v1.0.0-qt" (centered)
        └── QStackedWidget (flex, weight=1)
            └── [13 registered screen widgets]
```

### Navigation Items (NAV_ITEMS constant)
| Key | Unicode Icon | i18n Key | Display |
|-----|-------------|----------|---------|
| `home` | ⌂ (\u2302) | `dashboard` | Dashboard |
| `coach` | ⚑ (\u2691) | `rap_coach_dashboard` | AI Coach |
| `match_history` | ☰ (\u2630) | `match_history_title` | Match History |
| `performance` | ☆ (\u2606) | `advanced_analytics` | Your Stats |
| `tactical_viewer` | ⌖ (\u2316) | `tactical_analyzer` | Tactical Analyzer |
| `settings` | ⚙ (\u2699) | `settings` | Settings |
| `help` | ❓ (\u2753) | `help` | Help |

### Navigation Logic
- `_NavButton`: QPushButton subclass, checkable, stores `screen_key`
- `switch_screen(name)`: Sets QStackedWidget index, updates button checked states, calls `on_enter()` on target widget if method exists, emits `screen_changed` signal
- `_on_nav_clicked()`: Gets sender button, calls `switch_screen(btn.screen_key)`
- `_refresh_nav_labels(lang)`: Connected to `i18n.language_changed` signal, updates all button text

### Missing vs Kivy
- No MDTopAppBar (Kivy had one per screen with back button + trailing icons)
- No screen transition animation (Kivy used FadeTransition with 0.2s duration)
- Only 7 nav items visible (Kivy had 13 screens navigable via app bar buttons)
- Screens like `wizard`, `profile`, `user_profile`, `steam_config`, `faceit_config` are registered but not in sidebar nav

---

## 1.5 Theme Engine — `core/theme_engine.py` (135 lines)

### Palette Data
```python
PALETTES = {
    "CS2": {
        "surface": [0.08, 0.08, 0.12, 0.85],         # #14141e @ 85% → dark blue-black
        "surface_alt": [0.06, 0.06, 0.18, 0.9],       # #0f0f2e @ 90% → deeper blue
        "accent_primary": [0.85, 0.4, 0.0, 1],        # #d96600 → CS2 orange
        "chart_bg": "#1a1a1a",
    },
    "CSGO": {
        "surface": [0.10, 0.11, 0.13, 0.85],
        "surface_alt": [0.08, 0.10, 0.14, 0.9],
        "accent_primary": [0.38, 0.49, 0.55, 1],      # Muted blue-gray
        "chart_bg": "#1c1e20",
    },
    "CS1.6": {
        "surface": [0.07, 0.10, 0.07, 0.85],
        "surface_alt": [0.05, 0.14, 0.08, 0.9],
        "accent_primary": [0.30, 0.69, 0.31, 1],      # Classic green
        "chart_bg": "#181e18",
    },
}
```

### Global Color Constants
```python
COLOR_GREEN  = (0.30, 0.69, 0.31, 1)   # Rating > 1.10
COLOR_YELLOW = (1.0, 0.60, 0.0, 1)     # Rating 0.90–1.10
COLOR_RED    = (0.96, 0.26, 0.21, 1)    # Rating < 0.90
COLOR_CARD_BG = (0.12, 0.12, 0.14, 1)  # Card backgrounds
RATING_GOOD = 1.10
RATING_BAD  = 0.90
```

### Functions
- `rgba_to_qcolor(rgba: List[float]) → QColor`: Converts [r,g,b,a] (0-1 floats) to QColor
- `rating_color(rating: float) → QColor`: Maps HLTV rating to green/yellow/red QColor
- `rating_label(rating: float) → str`: WCAG 1.4.1 color-blind accessible text label
  - `>= 1.20` → "Excellent"
  - `> 1.10` → "Good"
  - `>= 0.90` → "Average"
  - `< 0.90` → "Below Avg"

### ThemeEngine Class
- `apply_theme(name, app)`: Loads QSS from `themes/{name}.qss`, sets QPalette with 13 color roles
- `get_color(slot)`: Returns QColor for a palette slot
- `chart_bg` property: Returns chart background hex string
- `active_theme` property: Returns current theme name

### QSS Stylesheet — `themes/cs2.qss` (307 lines)
Comprehensive styling for all Qt widget types:
- `QMainWindow`: `#14141e` background
- `QWidget#nav_sidebar`: `#0f0f2e` background, subtle right border
- `QPushButton#nav_button`: Transparent, orange hover (`rgba(217,102,0,0.15)`), orange checked (`rgba(217,102,0,0.25)`)
- `QFrame#dashboard_card`: `rgba(20,20,30,217)` background, 16px border-radius, hover orange border
- `QPushButton` (default): `#d96600` orange, white text, 8px radius, bold
- `QLabel#placeholder_label`: 24px, `#3a3a5a` (very muted gray — this is why placeholders look empty)
- `QTabBar::tab:selected`: Orange underline (`2px solid #d96600`)
- Scrollbars: 8px wide, dark handles, orange hover
- Inputs: Dark background, orange focus border, orange selection
- Progress bars, tooltips, radio/checkbox, group boxes all styled

---

## 1.6 Localization Bridge — `core/i18n_bridge.py` (115 lines)

### Architecture
- `QtLocalizationManager(QObject)` with `language_changed = Signal(str)`
- Singleton: `i18n = QtLocalizationManager()`
- Language state: `self._lang = "en"` (default)

### Translation Lookup Priority
1. JSON file (`assets/i18n/{lang}.json`)
2. Hardcoded dict from `core.localization.TRANSLATIONS` (full Kivy-era translations)
3. English fallback from hardcoded dict
4. Raw key (if nothing found)

### Template Variables
- `{home_dir}` in JSON values is replaced with `os.path.expanduser("~")`

### Hardcoded Fallback Keys (12 keys)
```python
"app_name", "dashboard", "coaching", "settings", "profile",
"match_history_title", "tactical_analysis", "tactical_analyzer",
"rap_coach_dashboard", "advanced_analytics", "knowledge_engine",
"training_progress", "help"
```

### Import Safety
Attempts `from Programma_CS2_RENAN.core.localization import TRANSLATIONS` but catches `ImportError` if Kivy is not installed, falling back to the minimal 12-key dict.

---

## 1.7 Asset Bridge — `core/asset_bridge.py` (120 lines)

### Map Name Normalization
```python
_MAP_ALIASES = {
    "mirage" → "de_mirage", "dust2" → "de_dust2", "inferno" → "de_inferno",
    "nuke" → "de_nuke", "overpass" → "de_overpass", "ancient" → "de_ancient",
    "vertigo" → "de_vertigo", "anubis" → "de_anubis", "train" → "de_train",
    "cache" → "de_cache"
}
```

### QPixmap Loading
- `get_map_pixmap(map_name, theme="regular")`: Normalizes name → builds path (`PHOTO_GUI/maps/{canonical}.png` or `{canonical}_{theme}.png`) → loads QPixmap → caches in dict → returns checkered fallback if not found
- `_checkered_fallback(256)`: Generates 256×256 magenta/black checkerboard QImage → QPixmap
- Fallback is created once and cached in module-level `_FALLBACK_PIXMAP`
- Singleton: `assets = QtAssetBridge()`

---

## 1.8 Background Worker — `core/worker.py` (59 lines)

### Pattern: QRunnable + WorkerSignals
```python
class WorkerSignals(QObject):
    finished = Signal()
    error = Signal(str)
    result = Signal(object)

class Worker(QRunnable):
    def __init__(self, fn, *args, **kwargs)
    def run(self):
        try:
            result = self.fn(*args, **kwargs)
            self.signals.result.emit(result)    # Auto-marshals to main thread
        except Exception as e:
            self.signals.error.emit(str(e))
        finally:
            self.signals.finished.emit()
```

### Key Design Decisions
- `setAutoDelete(True)`: Worker auto-destroyed after `run()` completes
- Triple `try/except RuntimeError: pass` guards: Handles case where signal receiver is garbage-collected before worker finishes (prevents crashes on rapid screen switches)
- Replaces Kivy pattern: `Thread(target=fn, daemon=True).start()` + `Clock.schedule_once(lambda dt: callback, 0)`
- PySide6 Signal connections auto-marshal across threads — no explicit scheduling needed

---

## 1.9 Match History Screen — `screens/match_history_screen.py` (174 lines)

### Widget Hierarchy
```
MatchHistoryScreen (QWidget)
├── QVBoxLayout (margins=16, spacing=8)
│   ├── QLabel#section_title "Match History" (Roboto 20, bold)
│   ├── QLabel (status — loading/error/empty, centered, gray, initially hidden)
│   └── QScrollArea (frame=NoFrame, widgetResizable=True)
│       └── QWidget (container)
│           └── QVBoxLayout (spacing=6)
│               ├── MatchCard × N
│               └── Stretch (keeps cards top-aligned)
```

### MatchCard (QFrame, 70px fixed height)
```
QFrame#dashboard_card (cursor=PointingHand)
└── QHBoxLayout (margins=12,8,12,8, spacing=12)
    ├── QLabel (rating badge — 60px wide, Roboto 12 bold, color-coded)
    │   "1.23\nExcellent"
    └── QVBoxLayout (info column, spacing=2)
        ├── QLabel "de_mirage  |  2026-03-12 14:30" (Roboto 12, #dcdcdc)
        └── QLabel "K/D: 1.45  |  ADR: 89.3  |  Kills: 22.1  Deaths: 15.3" (Roboto 10, #a0a0b0)
```

### Signal Flow
```
on_enter() → _vm.load_matches()
  → Worker(_bg_load) in QThreadPool
    → DB: SELECT PlayerMatchStats WHERE player_name=? AND is_pro=False ORDER BY match_date DESC LIMIT 50
    → Return list of dicts: {demo_name, match_date, rating, avg_kills, avg_deaths, avg_adr, avg_kast, kd_ratio}
  → _on_loaded(data) via Signal auto-marshal
    → _vm.matches_changed.emit(data)
      → _on_matches_loaded(matches)
        → Clear container → Create MatchCard for each → Connect card.clicked → insert before stretch
MatchCard.mousePressEvent(LeftButton) → clicked.emit(demo_name)
  → _on_match_clicked(demo_name)
    → match_selected.emit(demo_name)
      → [wired in app.py] match_detail.load_demo(demo_name) + window.switch_screen("match_detail")
```

### Map Name Extraction
Regex `(de_\w+|cs_\w+|ar_\w+)` extracts map name from demo filename. Falls back to "Unknown Map".

### ViewModel — `viewmodels/match_history_vm.py` (97 lines)
- `MatchHistoryViewModel(QObject)` with 3 signals: `matches_changed(list)`, `is_loading_changed(bool)`, `error_changed(str)`
- `_cancel = Event()` for cooperative cancellation
- Prevents duplicate loads: `if self._is_loading: return`
- Lazy imports `sqlmodel` and DB models inside `_bg_load()` to avoid import-time overhead
- Error path: raises `ValueError` if `CS2_PLAYER_NAME` not set

---

## 1.10 Match Detail Screen — `screens/match_detail_screen.py` (315 lines)

### Widget Hierarchy
```
MatchDetailScreen (QWidget)
├── QVBoxLayout (margins=16, spacing=8)
│   ├── QLabel#section_title "Match Detail — de_mirage" (Roboto 20, bold)
│   ├── QLabel (status — loading/error, centered, gray, initially hidden)
│   └── QTabWidget (initially hidden, shown when data loads)
│       ├── Tab "Overview" → _build_overview(stats, hltv)
│       ├── Tab "Rounds" → _build_rounds(rounds)
│       ├── Tab "Economy" → _build_economy(rounds)
│       └── Tab "Highlights" → _build_highlights(rounds, insights)
```

### Tab 1: Overview
```
QScrollArea
└── QWidget
    └── QVBoxLayout (spacing=8)
        ├── QHBoxLayout (rating header)
        │   ├── QLabel "1.23 (Excellent)" (Roboto 24, bold, color-coded)
        │   ├── QLabel "de_mirage  |  2026-03-12 14:30" (Roboto 14, #dcdcdc)
        │   └── Stretch
        ├── QLabel "K/D: 1.45   ADR: 89.3   KAST: 78%   HS: 52%   ..." (Roboto 11, #a0a0b0)
        ├── QLabel "HLTV 2.0 Components" (Roboto 14, bold, #dcdcdc)  [if hltv data exists]
        ├── QHBoxLayout × N (per component)
        │   ├── QLabel "Rating Impact" (180px, #a0a0b0)
        │   ├── QLabel "1.15" (bold, color-coded)
        │   └── Stretch
        └── Stretch
```

### Tab 2: Rounds
```
QScrollArea
└── QWidget
    └── QVBoxLayout (spacing=2)
        ├── QLabel "Rnd   W/L   Side   K  D   DMG     $Equip" (JetBrains Mono 10, bold, #a0a0b0)
        ├── QLabel × N (RichText HTML for each round)
        │   "R1   <span color=green>W</span>    <span color=blue>CT</span>    3  1    234   $4750  <span color=gold>FK</span>"
        └── Stretch
```

### Tab 3: Economy
```
EconomyChart (QChartView)
  → QBarSeries with CT (blue #5C9EE8) and T (gold #E8C95C) bar sets
  → X-axis: Round numbers (subsampled if >15 rounds)
  → Y-axis: Equipment value ($)
```

### Tab 4: Highlights
```
QScrollArea
└── QWidget
    └── QVBoxLayout (spacing=8)
        ├── QLabel "Coaching Insights" (Roboto 14, bold)
        ├── QFrame#dashboard_card × N (per insight)
        │   └── QVBoxLayout (spacing=4)
        │       ├── QLabel (title — bold, severity-colored: red/yellow/blue)
        │       ├── QLabel (message — word-wrapped, #dcdcdc)
        │       └── QLabel "Focus: {area}" (italic, #666666)
        ├── QLabel "Momentum" (Roboto 14, bold)
        └── MomentumChart (250px min height)
```

### ViewModel — `viewmodels/match_detail_vm.py` (143 lines)
- Signal: `data_changed(dict, list, list, dict)` → (stats, rounds, insights, hltv_breakdown)
- Queries 3 tables in single session: `PlayerMatchStats`, `RoundStats`, `CoachingInsight`
- Fetches HLTV 2.0 breakdown via `analytics.get_hltv2_breakdown()` (wrapped in try/except)
- Returns tuple of 4 dicts/lists

---

## 1.11 Performance Screen — `screens/performance_screen.py` (253 lines)

### Widget Hierarchy
```
PerformanceScreen (QWidget)
├── QVBoxLayout (margins=16, spacing=8)
│   ├── QLabel#section_title "Your Stats" (Roboto 20, bold)
│   ├── QLabel (status — loading/error, initially hidden)
│   └── QScrollArea
│       └── QWidget
│           └── QVBoxLayout (spacing=16)
│               ├── Section 1: "Rating Trend" card
│               │   └── RatingSparkline chart (250px min height)
│               ├── Section 2: "Per-Map Performance" card
│               │   └── QScrollArea (horizontal, 140px height)
│               │       └── QHBoxLayout of QFrame#dashboard_card × N (170×120 each)
│               │           ├── QLabel "Mirage" (Roboto 12, bold)
│               │           ├── QLabel "Rating: 1.15 (Good)" (color-coded)
│               │           ├── QLabel "ADR: 85  K/D: 1.30" (#a0a0b0)
│               │           └── QLabel "12 matches" (#666666)
│               ├── Section 3: "Strengths & Weaknesses" card
│               │   └── QHBoxLayout
│               │       ├── QVBoxLayout (green column)
│               │       │   ├── QLabel "Strengths" (green, bold)
│               │       │   └── QLabel × N "+1.5 above avg — Adr" (green)
│               │       └── QVBoxLayout (red column)
│               │           ├── QLabel "Weaknesses" (red, bold)
│               │           └── QLabel × N "-0.8 below avg — Flash Assists" (red)
│               ├── Section 4: "Utility Effectiveness" card
│               │   └── UtilityBarChart (280px min height)
│               └── Stretch
```

### ViewModel — `viewmodels/performance_vm.py` (72 lines)
- Signal: `data_changed(list, dict, dict, dict)` → (history, map_stats, sw, utility)
- Calls 4 analytics functions: `get_rating_history()`, `get_per_map_stats()`, `get_strength_weakness()`, `get_utility_breakdown()`
- Returns tuple of 4 results (with empty defaults on None)

---

## 1.12 Chart Widgets — Complete Specifications

### 1.12.1 RadarChart (QPainter, 118 lines)
- **Rendering**: Custom `paintEvent()` with QPainter (no QtCharts — QtCharts lacks polar charts)
- **Background**: `#1a1a1a` fill
- **Grid**: 4 concentric polygon rings at 25/50/75/100% of radius
- **Axes**: White lines from center to each vertex (25% opacity)
- **Data polygon**: Magenta fill (`#aa00ff` at 25% alpha), 2px magenta border
- **Labels**: Metric names at 20px beyond radius, Roboto 10pt
- **Value labels**: White text near each data point, Roboto 8pt
- **Min data**: 3 attributes required, shows "Not enough data" otherwise
- **Scale**: 0-100 per attribute

### 1.12.2 EconomyChart (QtCharts QBarSeries, 83 lines)
- **Type**: Grouped vertical bar chart
- **Series**: CT (blue `#5C9EE8`) vs T (gold `#E8C95C`)
- **X-axis**: QBarCategoryAxis with round numbers (every Nth label if >15 rounds)
- **Y-axis**: QValueAxis, range 0 to max_val×1.1, title "Equipment ($)"
- **Styling**: Dark background, white/gray labels, 8px rounded background

### 1.12.3 MomentumChart (QtCharts QAreaSeries, 108 lines)
- **Type**: Cumulative kill-death delta as area chart
- **Positive area**: Green fill (`#4CAF50` at 20% alpha)
- **Negative area**: Red fill (`#F44336` at 20% alpha)
- **Main line**: Cyan (`#00ccff`, 2px)
- **X-axis**: Round number
- **Y-axis**: Cumulative K-D (range: min-1 to max+1)
- **Legend**: Hidden

### 1.12.4 RatingSparkline (QtCharts QAreaSeries, 97 lines)
- **Type**: Line chart with filled area below
- **Main line**: Cyan (`#00ccff`, 2px)
- **Area fill**: Cyan at 15% alpha
- **Reference lines** (40% opacity):
  - White dashed at 1.0 (average baseline)
  - Green dashed at 1.1 (good threshold)
  - Red dashed at 0.9 (bad threshold)
- **X-axis**: Match index (integer)
- **Y-axis**: Rating (auto-scaled ±0.05 from data range)

### 1.12.5 TrendChart (QtCharts dual-axis, 92 lines)
- **Left axis** (cyan): Rating line (2px solid)
- **Right axis** (orange): ADR line (2px dashed)
- **X-axis**: Match index
- **Legend**: Visible at bottom
- **Title**: "Performance Trend"

### 1.12.6 UtilityBarChart (QtCharts QHorizontalBarSeries, 76 lines)
- **Type**: Horizontal grouped bars
- **Series**: "You" (cyan `#00ccff`) vs "Pro Avg" (orange `#ffaa00`)
- **Y-axis**: QBarCategoryAxis with metric names (title case, underscores replaced)
- **X-axis**: QValueAxis, range 0 to max×1.15
- **Legend**: Visible at bottom

---

## 1.13 Placeholder System — `screens/placeholder.py` (78 lines)

### 13 Placeholder Definitions
| Screen Key | Title | Description |
|-----------|-------|-------------|
| `home` | Dashboard | Training status, coaching hub, connectivity |
| `coach` | AI Coach | Coaching insights and interactive chat |
| `match_history` | Match History | Your analyzed matches with HLTV ratings |
| `match_detail` | Match Detail | Per-match stats, rounds, economy, insights |
| `performance` | Your Stats | Rating trends, skill radar, utility analysis |
| `tactical_viewer` | Tactical Analyzer | 2D map visualization with playback |
| `settings` | Settings | Theme, paths, language, ingestion config |
| `wizard` | Setup Wizard | First-time configuration |
| `profile` | Player Profile | View player stats and role analysis |
| `user_profile` | Edit Profile | Avatar, bio, system specs |
| `steam_config` | Steam Integration | SteamID64 and API key |
| `faceit_config` | FaceIT Integration | FaceIT API key |
| `help` | Help | Searchable documentation and FAQ |

Note: `match_history`, `match_detail`, and `performance` are replaced by real screens in `app.py` at line 60-62. The remaining 10 stay as placeholders.

### PlaceholderScreen Widget
```python
class PlaceholderScreen(QWidget):
    def __init__(self, title, description=""):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        lbl = QLabel(title)         # objectName="placeholder_label" → styled as 24px #3a3a5a
        desc = QLabel(description)  # objectName="section_subtitle" → styled as 12px #a0a0b0
    def on_enter(self):
        pass  # No-op
```

---

## 1.14 MVVM Architecture — Signal Flow Diagram

```
┌─────────────┐    on_enter()    ┌──────────────┐    Worker()     ┌──────────────┐
│   Screen     │ ──────────────► │  ViewModel    │ ─────────────► │  Background   │
│  (View)      │                 │  (QObject)    │                │   Thread      │
│              │  Signal         │               │  result.emit() │   (DB/API)    │
│  _on_data()  │ ◄────────────── │  data_changed │ ◄───────────── │              │
│              │  auto-marshal   │               │                │              │
│  render UI   │                 │  is_loading   │                │              │
└─────────────┘                 └──────────────┘                └──────────────┘
```

All 3 functional screens follow this exact pattern:
1. `on_enter()` → ViewModel.load_*()
2. ViewModel creates Worker → submits to QThreadPool
3. Worker runs DB query on background thread
4. Worker emits `result` signal → auto-marshaled to main thread
5. ViewModel emits `data_changed` signal
6. Screen receives data → clears old content → builds new widgets

---

## 1.15 Backend Integration Points

| Qt Component | Backend Module | Data Flow |
|-------------|---------------|-----------|
| `MatchHistoryViewModel._bg_load()` | `backend.storage.db_models.PlayerMatchStats` | SELECT WHERE is_pro=False LIMIT 50 |
| `MatchDetailViewModel._bg_load()` | `db_models.{PlayerMatchStats, RoundStats, CoachingInsight}` | SELECT by demo_name + player_name |
| `MatchDetailViewModel._bg_load()` | `backend.reporting.analytics.get_hltv2_breakdown()` | HLTV 2.0 component breakdown |
| `PerformanceViewModel._bg_load()` | `backend.reporting.analytics.get_rating_history()` | Last 50 match ratings |
| `PerformanceViewModel._bg_load()` | `backend.reporting.analytics.get_per_map_stats()` | Per-map aggregates |
| `PerformanceViewModel._bg_load()` | `backend.reporting.analytics.get_strength_weakness()` | Z-score deviations |
| `PerformanceViewModel._bg_load()` | `backend.reporting.analytics.get_utility_breakdown()` | User vs pro utility |
| `i18n_bridge` | `core.localization.TRANSLATIONS` | Translation dicts |
| `asset_bridge` | `core.config.get_resource_path()` | Map image paths |
| `theme_engine` | (standalone) | QSS file loading |

### NOT Connected (Missing)
- `core.session_engine` — No daemon management
- `backend.services.coaching_service` — No coaching generation
- `backend.nn.*` — No ML model interaction
- `backend.data_sources.demo_parser` — No demo parsing
- `core.playback_engine` — No tactical playback
- `core.spatial_engine` — No coordinate transforms
- `backend.knowledge.*` — No RAG/experience bank
- `backend.ingestion.*` — No watcher integration
- `observability.rasp` — No RASP protection


---

# ════════════════════════════════════════════════════════════════
# SECTION 2: OLD KIVY FRONTEND — COMPLETE ASSESSMENT
# ════════════════════════════════════════════════════════════════

## 2.1 Executive Summary

The Kivy frontend (`Programma_CS2_RENAN/apps/desktop_app/`) is the **production-grade, feature-complete** version of the UI. Built on Kivy + KivyMD (Material Design 3), it implements **13 fully functional screens** with a declarative layout system (`layout.kv`, 1622 lines), **6 matplotlib chart widgets**, a **2D tactical demo viewer** with real-time player rendering at 60 FPS, **coaching chat integration**, and deep connections to all backend services. Total: ~5,400+ lines of Python + ~1,622 lines of KV.

### Feature Completeness Matrix

| Feature | Kivy Status | Qt Status | Gap |
|---------|------------|-----------|-----|
| Dashboard (Home) with ML status bar | **Complete** | Placeholder | **Full port needed** |
| AI Coach with belief state + insights | **Complete** | Placeholder | **Full port needed** |
| Coaching Chat with Ollama | **Complete** | Placeholder | **Full port needed** |
| Match History | **Complete** | **Complete** | Parity |
| Match Detail | **Complete** | **Complete** | Parity |
| Performance Dashboard | **Complete** | **Complete** | Parity |
| Tactical 2D Viewer (603-line widget) | **Complete** | Placeholder | **Major port needed** |
| Player Sidebar with widget pooling | **Complete** | Not started | **Full port needed** |
| Timeline scrubber with events | **Complete** | Not started | **Full port needed** |
| Ghost AI prediction overlay | **Complete** | Not started | **Full port needed** |
| Setup Wizard (3-step flow) | **Complete** | Placeholder | **Full port needed** |
| Settings (theme/font/lang/paths/ingest) | **Complete** | Placeholder | **Full port needed** |
| Steam Config (ID + API key) | **Complete** | Placeholder | **Full port needed** |
| FaceIT Config (API key) | **Complete** | Placeholder | **Full port needed** |
| Player Profile (avatar, bio, specs) | **Complete** | Placeholder | **Full port needed** |
| Profile (in-game name) | **Complete** | Placeholder | **Full port needed** |
| Help (searchable, sidebar + content) | **Partial** | Placeholder | **Port stub** |
| Background crossfade wallpapers | **Complete** | Not present | **Port or skip** |
| 6 matplotlib chart widgets | **Complete** | **6 QtCharts** | Parity (upgraded) |
| 3 game themes (CS2/CSGO/CS1.6) | **Complete** | **Complete** | Parity |
| 3 languages (en/it/pt) | **Complete** | **Complete** | Parity |
| Fonts (6 selectable types) | **Complete** | Not present | **Port to QSS** |

---

## 2.2 File Inventory (Every File)

```
desktop_app/
├── __init__.py                          (empty — package marker)
├── layout.kv                            (1622 lines — full declarative UI for all 13 screens)
├── theme.py                             (74 lines — palette registry, rating colors)
├── widgets.py                           (277 lines — 6 matplotlib chart widgets)
├── wizard_screen.py                     (417 lines — setup wizard with file pickers)
├── match_history_screen.py              (164 lines — match list view)
├── match_detail_screen.py               (454 lines — match drill-down)
├── performance_screen.py                (331 lines — aggregate analytics)
├── help_screen.py                       (79 lines — help center stub)
├── coaching_chat_vm.py                  (138 lines — coaching dialogue ViewModel)
├── data_viewmodels.py                   (320 lines — 3 data ViewModels)
├── tactical_viewmodels.py               (347 lines — 3 tactical ViewModels)
├── tactical_viewer_screen.py            (295 lines — 2D viewer orchestrator)
├── tactical_map.py                      (603 lines — THE core 2D map widget)
├── player_sidebar.py                    (362 lines — team player lists + detail cards)
├── ghost_pixel.py                       (140 lines — debug coordinate overlay)
├── timeline.py                          (129 lines — interactive timeline scrubber)
├── README.md                            (multilingual docs)
├── README_IT.md
└── README_PT.md
```

**Total**: ~3,800+ lines Python + 1,622 lines KV = ~5,400+ lines

---

## 2.3 Declarative UI — `layout.kv` (1622 lines)

### Root Layout
```
FloatLayout
├── FadingBackground (dual FitImage crossfade for wallpaper transitions)
└── MDScreenManager (FadeTransition, 0.2s)
    ├── WizardScreen (name="wizard")
    ├── HomeScreen (name="home")
    ├── CoachScreen (name="coach")
    ├── UserProfileScreen (name="user_profile")
    ├── SettingsScreen (name="settings")
    ├── ProfileScreen (name="profile")
    ├── SteamConfigScreen (name="steam_config")
    ├── FaceitConfigScreen (name="faceit_config")
    ├── HelpScreen (name="help")
    ├── TacticalViewerScreen (name="tactical_viewer")
    ├── MatchHistoryScreen (name="match_history")
    ├── MatchDetailScreen (name="match_detail")
    └── PerformanceScreen (name="performance")
```

### Custom KV Components (Reusable)
| Component | Purpose | Lines |
|-----------|---------|-------|
| `SectionHeader` | Icon + title horizontal layout | 16-36 |
| `AppSettingItem` | Title + value vertical pair | 38-53 |
| `DashboardCard` | Styled MDCard with theme_surface bg, 16px radius, elevation 2 | 55-64 |
| `TrainingStatusCard` | Training progress with epoch counter + loss display | 66-124 |
| `FadingBackground` | Dual FitImage for crossfade wallpaper transitions | 128-140 |
| `CoachingCard` | Severity-colored insight card with glassmorphism effect + colored left bar | 455-511 |

### Screen-by-Screen KV Analysis

#### HomeScreen (lines 161-453, ~292 lines)
- **MDTopAppBar**: Settings gear, help icon, match history, performance, coach, profile buttons
- **ML Status Bar**: Coach status text (blue if active, red if inactive) + "Restart Service" button
- **ScrollView** with 4 DashboardCards:
  1. **Coaching Card**: Upload status, quota label, demo folder path, "Set Demo Folder" button, parsing progress bar
  2. **Pro Knowledge Hub**: Pro folder path, "Set Pro Folder" button, ingest speed controls (Eco 6h / Standard 1h / Turbo Continuous), Play/Stop toggle
  3. **API & Profile Connectivity**: Profile, Steam, FaceIT buttons
  4. **Tactical Analysis Entry**: "Launch Viewer" button with green theme

#### CoachScreen (lines 513-821, ~308 lines)
- **Active Belief State** card: Confidence progress bar + stability indicator
- **Advanced Analytics** card: Injected matplotlib containers (analytics_container, radar_container) + "Tactical Heatmap (Coming Soon)" button
- **Causal Audit** card: "Audit Path" button (orange)
- **Knowledge Engine** card: Game ticks counter + active tasks list + parsing progress bar
- **Dynamic Insights** section: Container for CoachingCards
- **Coaching Chat Panel** (420dp collapsible):
  - Chat header with "Ask your coach" title + broom (clear) + chevron-down (collapse) buttons
  - Chat messages ScrollView
  - Typing indicator
  - Quick action buttons: "Positioning", "Utility", "What to improve?"
  - Input bar: MDTextField + blue send button

#### UserProfileScreen (lines 822-925, ~103 lines)
- Avatar image (120dp circular FitImage, fallback account icon)
- Role badge (36dp shield-star in corner)
- Player name + role labels
- Bio card
- System specs card
- "Sync with Steam" button

#### ProfileScreen (lines 926-961, ~35 lines)
- In-game name explanation
- MDTextField for nickname
- Save button → `app.save_user_config("CS2_PLAYER_NAME", ...)`

#### SteamConfigScreen (lines 962-1032, ~70 lines)
- Steam integration explanation
- "Find Steam ID" button → opens `steamid.io`
- SteamID64 text field (17-digit)
- Steam Web API Key explanation
- "Get Steam Key" button → opens `steamcommunity.com/dev/apikey`
- API key password field
- Save button → `app.save_multiple_configs({"STEAM_ID": ..., "STEAM_API_KEY": ...})`

#### FaceitConfigScreen (lines 1033-1075, ~42 lines)
- FaceIT stats explanation
- "Get FaceIT Key" button → opens `developers.faceit.com`
- API key password field
- Save button → `app.save_user_config("FACEIT_API_KEY", ...)`

#### HelpScreen (lines 1076-1122, ~46 lines)
- Horizontal split layout:
  - Left (30%): Search text field + scrollable topic list
  - Right (70%): Markdown content display

#### SettingsScreen (lines 1124-1387, ~263 lines)
- **Theme Section**: CS2/CSGO/CS1.6 toggle buttons + cycle wallpaper
- **Analysis Paths**: Demo folder + Pro folder with current values + change buttons
- **Appearance**: Font size (Small/Medium/Large) toggle buttons
- **Data Ingestion**: Manual/Auto toggle, scan interval text field, Start/Stop ingestion buttons
- **Font Type**: 6-button grid (Roboto, Arial, JetBrains Mono, New Hope, CS Regular, YUPIX)
- **Language**: English/Italiano/Português toggle buttons

#### WizardScreen (lines 1388-1421, ~33 lines KV + 417 lines Python)
- Title label + divider + content area (injected by Python) + Next button

#### TacticalViewerScreen (lines 1422-1550, ~128 lines)
- **MDTopAppBar**: Back arrow + "Tactical Analyzer" title + folder open button
- **Horizontal triple-pane**: CT Sidebar (20%) | TacticalMap (60%) | T Sidebar (20%)
- **Controls bar** (120dp):
  - Map spinner + Round spinner + Tick counter
  - Debug toggle switch + Ghost toggle switch
  - Playback: Skip prev/Play/Skip next + Speed (0.5x/0.75x/1x/2x/4x)
  - TimelineScrubber widget (40dp)

#### MatchHistoryScreen (lines 1552-1575, ~23 lines)
- MDTopAppBar with back arrow + "Match History" title + chart-line shortcut to performance
- ScrollView with match_list_container

#### MatchDetailScreen (lines 1577-1596, ~19 lines)
- MDTopAppBar with back arrow + "Match Detail" title
- ScrollView with detail_container

#### PerformanceScreen (lines 1598-1622, ~24 lines)
- MDTopAppBar with back arrow + "Performance Dashboard" title + history shortcut
- ScrollView with performance_container

---

## 2.4 Theme System — `theme.py` (74 lines)

Identical palette data as Qt version:
- 3 themes: CS2 (orange), CSGO (blue-gray), CS1.6 (green)
- Same COLOR_GREEN/YELLOW/RED constants
- `rating_color(rating)` → tuple(r,g,b,a) (not QColor)
- `rating_label(rating)` → WCAG 1.4.1 text labels
- `CHART_BG = "#1a1a1a"` for matplotlib figures

---

## 2.5 Matplotlib Chart Widgets — `widgets.py` (277 lines)

### Base Class: `MatplotlibWidget(Image)`
- Inherits Kivy `Image` widget
- Pattern: Create matplotlib Figure → render to PNG BytesIO → load as Kivy Texture
- **WG-01**: Figure closed immediately after serialization (prevents memory leak)
- **WG-02**: BytesIO context manager ensures cleanup on exception

### 6 Chart Widgets
| Widget | Kivy Class | Qt Equivalent | Rendering |
|--------|-----------|---------------|-----------|
| `TrendGraphWidget` | matplotlib dual-axis line | `TrendChart` | matplotlib → PNG → Texture |
| `RadarChartWidget` | matplotlib polar spider | `RadarChart` | matplotlib → PNG → Texture |
| `EconomyGraphWidget` | matplotlib stacked bar | `EconomyChart` | matplotlib → PNG → Texture |
| `MomentumGraphWidget` | matplotlib area fill | `MomentumChart` | matplotlib → PNG → Texture |
| `RatingSparklineWidget` | matplotlib area + refs | `RatingSparkline` | matplotlib → PNG → Texture |
| `UtilityBarWidget` | matplotlib horizontal bar | `UtilityBarChart` | matplotlib → PNG → Texture |

**Key difference**: Kivy uses matplotlib → PNG → Kivy Texture (CPU-heavy, 50-100ms per chart). Qt uses QtCharts (GPU-accelerated, <5ms per chart). The Qt version is significantly more performant.

---

## 2.6 Wizard Screen — `wizard_screen.py` (417 lines)

### 4-Step Setup Flow
1. **Intro**: Welcome text + "Get started" button
2. **Brain Path**: File picker + manual entry, creates `{path}/knowledge`, `{path}/models`, `{path}/datasets` directories
3. **Demo Path**: Optional demo folder selection
4. **Finish**: Saves `SETUP_COMPLETED=True`, transitions to home screen

### Defensive Coding
- `WZ-01`: Path normalization to prevent directory traversal attacks
- `WZ-02`: Try/except around `MDFileManager.show()` (can fail on non-existent paths)
- `WZ-03`: Only saves settings if directory creation succeeds
- `WZ-04`: Verifies fallback path suggestions are writable before recommending

### Cross-Platform Support
- Windows: Drive selector dialog if multiple drives detected
- Linux/macOS: Defaults to `~` via `os.path.expanduser("~")`
- Creates intermediate directories with `os.makedirs(exist_ok=True)`

---

## 2.7 The Tactical Map — `tactical_map.py` (603 lines)

**This is the crown jewel of the Kivy frontend.** A real-time 2D demo viewer rendering at 60 FPS.

### Architecture: InstructionGroup Layers
```
Canvas
├── map_group (InstructionGroup)      — Static: map texture (drawn once per load/resize)
├── heatmap_group (InstructionGroup)  — Static: heatmap overlay (drawn once per generation)
└── dynamic_group (InstructionGroup)  — Dynamic: players + nades (cleared + redrawn every tick)
```

**Key Optimization**: This layered approach avoids re-uploading the map texture to the GPU ~64 times per second. Only the `dynamic_group` is cleared and redrawn each frame.

### Coordinate System (3-stage transformation)
```
World Coordinates (CS2 engine units, e.g., x=-2400, y=1800)
    ↓ SpatialEngine.world_to_normalized()
Normalized Coordinates (0.0–1.0)
    ↓ scale by min(width, height) + offset
Screen Coordinates (Kivy widget pixels)
```

- `_world_to_screen(x, y)`: Full pipeline world → screen
- `_screen_to_world(sx, sy)`: Reverse for click interaction
- **F7-22**: Uses `min(width, height)` for uniform scaling to handle non-square widgets

### Player Rendering
- **Circle**: 8px radius, CT blue `(0.3, 0.5, 1.0)` or T orange `(1.0, 0.6, 0.2)`, dead = gray
- **Ghost players**: 30% alpha (AI prediction overlay)
- **Selection highlight**: Larger white circle (8+4=12px radius)
- **FoV cone**: 30px cone extending from player position at yaw angle
- **Name label**: 9pt cached in OrderedDict (LRU eviction at 64 entries)
- **Health bar**: 2px bar below player, green if HP>50, red otherwise
- **Hitbox**: 2.5× visual radius for easier mouse clicking

### Grenade Rendering
| Nade Type | Detonation Radius | Color | Animation |
|-----------|------------------|-------|-----------|
| HE | 350 units | Red | Semi-transparent circle overlay |
| Molotov | 180 units | Orange | Pulsing red glow (`sin(time*8)`) |
| Smoke | 144 units | Gray | Expanding ellipse over 3 seconds |
| Flash | 1000 units | Yellow | Inner high-opacity zone (300 units) |

- **Trajectory**: Polyline with height-based width/opacity, apex marker (white dot)
- **Fade**: Trajectory fades 3 seconds after detonation
- **Duration progress**: Circular progress bar around active nades

### Heatmap Pipeline
1. Events → background thread → `HeatmapEngine.generate_heatmap_data()`
2. **TM-03**: Generation ID guards against stale results
3. `Clock.schedule_once()` → main thread → `HeatmapEngine.create_texture_from_data()` (OpenGL)
4. Apply to `heatmap_group` InstructionGroup

### Click Interaction
- `on_touch_down()`: Checks collision, then debug mode children, then player selection
- Player selection: Distance check using `math.hypot()` with hitbox multiplier
- Click toggle: Same player → deselect, different → select

---

## 2.8 Player Sidebar — `player_sidebar.py` (362 lines)

### Two Widget Classes

#### LivePlayerCard
- Displays HP, armor, money, weapon, K/D for selected player
- Progress bars with color-coded values
- Animated height transitions (0 when hidden, 210dp when visible)

#### PlayerSidebar
- Team header (CT blue or T orange)
- Scrollable MDList of team members
- **Widget pooling optimization**: Reuses MDListItem widgets across frames
  - `_player_items` cache stores (widget, {icon, headline, support, trailing})
  - Stale players evicted on disconnect
  - **F7-14**: Explicit `clear_all()` prevents cache growth across match switches
- Sorted: Alive players first, dead at bottom

---

## 2.9 Timeline — `timeline.py` (129 lines)

### Interactive Timeline Scrubber Widget
- **Background bar**: Dark gray
- **Progress bar**: Green, proportional to `current_tick / total_ticks`
- **Event markers** (colored vertical lines):
  - Red (50% height): Kill events
  - Yellow (100% height): Bomb plant
  - Blue (100% height): Bomb defuse
- **Drag interaction**: Touch → seek to tick
- **F7-33**: Position clamped to [0.0, 1.0]

---

## 2.10 Ghost Pixel Debug Overlay — `ghost_pixel.py` (140 lines)

- Renders cyan landmark circles on map at known positions
- Interactive magenta crosshair on touch
- Displays normalized + world coordinates in tooltip
- Toggled via `debug_mode` property on TacticalMap
- **F7-38**: Importable in production, gated by config flag

---

## 2.11 ViewModels — Data Layer

### `data_viewmodels.py` (320 lines) — 3 ViewModels
All use Kivy `EventDispatcher` with `ListProperty`, `BooleanProperty`, `StringProperty`.

#### MatchHistoryViewModel
- `load_matches()` → Background thread → `PlayerMatchStats` query (is_pro=False, LIMIT 50)
- `_cancel` Event for cooperative cancellation
- **DV-01**: Discard results if cancelled during load
- **DV-02**: Guarantee `is_loading` resets even on exception

#### MatchDetailViewModel
- `load_detail(demo_name)` → Background thread → 3 table query + HLTV breakdown
- **DV-03**: Validate demo_name before spawning thread

#### PerformanceViewModel
- `load_performance()` → Background thread → 4 analytics API calls

### `coaching_chat_vm.py` (138 lines)
- `messages` ListProperty: `[{role: "user"|"assistant", content: str}]`
- `check_availability()` → Background thread checks Ollama
- `start_session(player_name, demo_name)` → Initializes coaching session
- `send_message(text)` → Background response fetch
- **F7-24**: Thread lock guards concurrent message list access
- Fallback: Canned response if Ollama offline

### `tactical_viewmodels.py` (347 lines) — 3 ViewModels

#### TacticalPlaybackViewModel
- Binds to `PlaybackEngine` instance
- `toggle_playback()`, `set_speed()`, `seek_to_tick()`

#### TacticalGhostViewModel
- Lazy-loads `GhostEngine` on demand (prevents torch startup overhead)
- `predict_ghosts(players)` → ghost predictions

#### TacticalChronovisorViewModel
- Background scan for critical moments (RAP model)
- `_scan_cancel` Event for cooperative shutdown
- **CM_NAVIGATION_BUFFER_TICKS = 32**: Prevents getting stuck on same critical moment
- Methods: `scan_match()`, `jump_to_next()`, `jump_to_prev()`

---

## 2.12 Screen Implementations (Python)

### `match_history_screen.py` (164 lines)
- MVVM with `MatchHistoryViewModel`
- Card rendering with rating badge, map name, date, K/D, ADR
- `_show_placeholder()` for loading/empty states

### `match_detail_screen.py` (454 lines)
- 4 sections: Overview, Round Timeline, Economy Graph, Highlights + Momentum
- HLTV 2.0 breakdown bars
- Per-round cards: Round#, W/L, K/D, DMG, $Equipment, FK flag
- Economy: `EconomyGraphWidget` (matplotlib)
- Coaching insights with severity-colored cards
- `MomentumGraphWidget` (matplotlib)

### `performance_screen.py` (331 lines)
- 4 sections: Rating Trend, Per-Map Performance, Strengths/Weaknesses, Utility
- All matplotlib chart widgets

### `tactical_viewer_screen.py` (295 lines)
- Orchestrates 3 ViewModels + PlaybackEngine
- Creates engine locally, binds to TacticalPlaybackViewModel
- Lifecycle: `on_enter()` → start tick timer, bind map selection; `on_leave()` → cancel timer, unbind
- **P4-01**: Prevents duplicate bindings on re-enter
- **F7-27**: Guards against stale callbacks when screen is not current

### `help_screen.py` (79 lines)
- Stub with import guard for `help_system` module
- Left sidebar: Searchable topic list
- Right pane: Markdown/HTML content display

---

## 2.13 Backend Integration — Complete Map

| Kivy Component | Backend Dependency | Not in Qt |
|---------------|-------------------|-----------|
| HomeScreen KV | `app.coach_status`, `app.service_active`, `app.parsing_progress` | Yes |
| HomeScreen KV | `app.open_folder_picker()`, `app.toggle_ai_service()` | Yes |
| HomeScreen KV | `app.set_pro_ingest_speed()`, `app.soft_restart_service()` | Yes |
| CoachScreen KV | `app.belief_confidence`, `app.knowledge_reservoir_ticks` | Yes |
| CoachScreen KV | `app.show_brain_dialog()`, `app.show_pro_comparison_dialog()` | Yes |
| CoachingChatVM | `backend.services.coaching_dialogue.get_dialogue_engine()` | Yes |
| TacticalViewerScreen | `core.playback_engine.PlaybackEngine` | Yes |
| TacticalMap | `core.spatial_engine.SpatialEngine` | Yes |
| TacticalMap | `core.map_manager.MapManager` | Yes |
| TacticalMap | `backend.processing.heatmap_engine.HeatmapEngine` | Yes |
| TacticalGhostVM | `backend.nn.inference.ghost_engine.GhostEngine` | Yes |
| TacticalChronovisorVM | `backend.nn.rap_coach.chronovisor_scanner.ChronovisorScanner` | Yes |
| WizardScreen | `core.config.save_user_setting()` | Yes |
| SettingsScreen KV | `app.set_app_theme()`, `app.set_font_size()`, etc. | Yes |
| SteamConfigScreen KV | `app.save_multiple_configs()`, `app.open_url()` | Yes |
| FaceitConfigScreen KV | `app.save_user_config()`, `app.open_url()` | Yes |
| UserProfileScreen KV | `app.sync_profile_with_steam()` | Yes |
| MatchHistoryVM | `backend.storage.db_models.PlayerMatchStats` | No (already in Qt) |
| MatchDetailVM | `backend.storage.db_models.*` | No (already in Qt) |
| PerformanceVM | `backend.reporting.analytics` | No (already in Qt) |

---

## 2.14 Assets Referenced

### Fonts (6 selectable in Settings)
1. **Roboto** (default, bundled with KivyMD)
2. **Arial** (system font)
3. **JetBrains Mono** (monospace, used for round data)
4. **New Hope** (custom gaming font)
5. **CS Regular** (Counter-Strike style font)
6. **YUPIX** (pixel art style font)

### Map Images
- Located in `PHOTO_GUI/maps/` directory
- Naming: `de_mirage.png`, `de_dust2.png`, etc.
- Themes: `de_mirage_dark.png`, `de_mirage_light.png`
- Loaded via `MapManager.load_map_async()` in Kivy
- Loaded via `QtAssetBridge.get_map_pixmap()` in Qt

### Wallpapers
- Managed by `app.background_source` / `app.background_source_next`
- Crossfade via `FadingBackground` widget (dual FitImage)
- Cycleable via "Cycle Wallpaper" button in Settings

### Icons
- Material Design icons via KivyMD `MDIcon` (icon names like "brain", "school", "trophy")
- In Qt: Currently using Unicode characters (\u2302, \u2691, etc.) as icon replacements

### Localization Files
- `assets/i18n/en.json`, `pt.json`, `it.json`
- Template variables: `{home_dir}` replaced at runtime

---

## 2.15 Thread Safety & Concurrency

| Thread Origin | Mechanism | Safety Guard |
|---------------|-----------|--------------|
| MatchHistoryVM | `Thread(daemon=True)` | `_cancel.set()` cooperative cancellation |
| MatchDetailVM | `Thread(daemon=True)` | One-shot, DV-03 validation |
| PerformanceVM | `Thread(daemon=True)` | One-shot |
| CoachingChatVM | `Thread(daemon=True)` | F7-24 thread lock on message list |
| ChronovisorVM | `Thread(daemon=True)` | `_scan_cancel` Event |
| TacticalMap heatmap | `Thread(daemon=True)` | `_heatmap_generation_id` staleness check |
| All UI updates | `Clock.schedule_once(fn, 0)` | Marshals to main thread |


---

# ════════════════════════════════════════════════════════════════
# SECTION 3: INDUSTRIAL-GRADE IMPLEMENTATION PLAN
# ════════════════════════════════════════════════════════════════

## 3.1 Migration Strategy: Incremental, Backward-Compatible

### Guiding Principle
Both frontends coexist. The Kivy app remains the production frontend while Qt screens are ported one by one. Each ported screen must pass the headless validator before being considered complete.

### Migration Order (Risk-Optimized)
```
Phase 1: Core Infrastructure (enables all subsequent phases)
  → Settings, Wizard, Profile screens
  → These are simple forms with no real-time data

Phase 2: Dashboard & Coaching (high user value)
  → Home, Coach, Chat
  → Requires app.* property bridge for ML status

Phase 3: Integrations (simple forms)
  → Steam Config, FaceIT Config, Help
  → Pure form screens with URL actions

Phase 4: Tactical Viewer (highest complexity)
  → TacticalMap QPainter port, PlayerSidebar, Timeline, Ghost, ViewModels
  → Requires coordinate transform, playback engine integration

Phase 5: CI/CD & Quality (ongoing)
  → GitHub Actions, packaging, automated tests
```

---

## 3.2 Phase 1: Core Infrastructure

### P1.1 — Settings Screen

**Files to create**:
- `qt_app/screens/settings_screen.py` (~250 lines)

**Port from Kivy**: `layout.kv` lines 1124-1387 (SettingsScreen definition)

**Sections to implement**:
1. Theme selector (CS2/CSGO/CS1.6) → calls `ThemeEngine.apply_theme()`
2. Wallpaper cycle button
3. Analysis paths (demo + pro folder) with QFileDialog
4. Font size selector (Small/Medium/Large) → updates QSS font-size
5. Data ingestion mode (Manual/Auto) + scan interval
6. Font type selector (6 options) → updates QSS font-family
7. Language selector (en/it/pt) → calls `i18n.set_language()`

**Backend connections needed**:
- `core.config.get_setting()` / `save_user_setting()` for all preferences
- `ThemeEngine.apply_theme()` for live theme switching

**Qt widgets**:
- QScrollArea with QVBoxLayout sections
- QPushButton groups for toggles (checkable, exclusive via manual logic or QButtonGroup)
- QLineEdit for interval
- QFileDialog for folder pickers

### P1.2 — Setup Wizard

**Files to create**:
- `qt_app/screens/wizard_screen.py` (~200 lines)

**Port from Kivy**: `wizard_screen.py` (417 lines)

**Steps to implement**:
1. Intro page → "Get started" button
2. Brain path → QFileDialog + manual path entry + directory creation
3. Demo path → Optional QFileDialog
4. Finish → Save config, switch to home

**Security**: WZ-01 through WZ-04 path validation guards must be preserved.

### P1.3 — Player Profile Screens

**Files to create**:
- `qt_app/screens/user_profile_screen.py` (~120 lines)
- `qt_app/screens/profile_screen.py` (~60 lines)

**Port from Kivy**: `layout.kv` lines 822-961

**Content**:
- Avatar display (QLabel with QPixmap, circular clip)
- Role badge
- Name, role, bio, system specs labels
- In-game name text field + save button
- "Sync with Steam" button

---

## 3.3 Phase 2: Dashboard & Coaching

### P2.1 — Home/Dashboard Screen

**Files to create**:
- `qt_app/screens/home_screen.py` (~300 lines)
- `qt_app/viewmodels/home_vm.py` (~80 lines)

**Port from Kivy**: `layout.kv` lines 161-453

**Critical requirement**: The Dashboard is the nerve center. It needs a bridge to backend state:

**App Property Bridge** (new concept for Qt):
```python
class AppState(QObject):
    """Singleton that polls CoachState from DB and emits signals."""
    coach_status_changed = Signal(str)
    service_active_changed = Signal(bool)
    parsing_progress_changed = Signal(float)
    belief_confidence_changed = Signal(float)
    knowledge_ticks_changed = Signal(int)
    # ... poll every 2 seconds via QTimer
```

**Sections**:
1. ML Status bar with coach_status + restart button
2. Coaching card: Demo quota, folder path, folder picker, parsing progress
3. Pro Knowledge Hub: Pro folder, speed controls, play/stop toggle
4. API & Profile Connectivity: Profile/Steam/FaceIT buttons
5. Tactical Analysis Entry: "Launch Viewer" button

### P2.2 — AI Coach Screen

**Files to create**:
- `qt_app/screens/coach_screen.py` (~350 lines)
- `qt_app/viewmodels/coach_vm.py` (~100 lines)

**Port from Kivy**: `layout.kv` lines 513-821

**Sections**:
1. Belief state card with QProgressBar
2. Analytics containers (inject RadarChart, TrendChart)
3. Causal audit button
4. Knowledge engine card with tick counter
5. Dynamic coaching insights (severity-colored QFrame cards)
6. Collapsible chat panel (QWidget with animated height via QPropertyAnimation)

### P2.3 — Coaching Chat ViewModel

**Files to create**:
- `qt_app/viewmodels/coaching_chat_vm.py` (~120 lines)

**Port from Kivy**: `coaching_chat_vm.py` (138 lines)

**Key adaptations**:
- Replace Kivy `EventDispatcher` + `ListProperty` with `QObject` + `Signal`
- Replace `Clock.schedule_once()` with Signal auto-marshaling
- Preserve Ollama availability check + fallback behavior
- Preserve thread lock for message list (F7-24)

---

## 3.4 Phase 3: Integrations

### P3.1 — Steam Config Screen
- `qt_app/screens/steam_config_screen.py` (~80 lines)
- QLineEdit for SteamID64, QLineEdit (echoMode=Password) for API key
- QPushButton → `QDesktopServices.openUrl()` for external links
- Save → `core.config.save_user_setting()`

### P3.2 — FaceIT Config Screen
- `qt_app/screens/faceit_config_screen.py` (~60 lines)
- Same pattern as Steam, single API key field

### P3.3 — Help Screen
- `qt_app/screens/help_screen.py` (~100 lines)
- QSplitter: left QListWidget (topics) + right QTextBrowser (markdown)
- Search filtering via QLineEdit

---

## 3.5 Phase 4: Tactical Viewer (Major Port)

This is the most complex phase. The Kivy TacticalMap (603 lines) must be rewritten for QPainter.

### P4.1 — TacticalMap Widget (QPainter Port)

**Files to create**:
- `qt_app/widgets/tactical/tactical_map.py` (~600 lines)

**Key translations**:

| Kivy Concept | Qt Equivalent |
|-------------|---------------|
| `InstructionGroup` with `Color`, `Ellipse`, `Rectangle` | QPainter with `setBrush`, `drawEllipse`, `drawRect` |
| `Canvas.add(group)` | Paint layers via `paintEvent()` with explicit order |
| `PushMatrix`/`PopMatrix`/`Rotate` | `QPainter.save()`/`restore()`/`rotate()` |
| `Kivy.core.text.Label` for name textures | QPainter.drawText() or QStaticText cache |
| `Widget.bind(size=, pos=)` | `resizeEvent()` |
| `Widget.on_touch_down()` | `mousePressEvent()` |

**Layer strategy for Qt**:
```python
def paintEvent(self, event):
    painter = QPainter(self)
    painter.setRenderHint(QPainter.Antialiasing)

    # Layer 1: Map background (cached QPixmap)
    self._draw_map(painter)

    # Layer 2: Heatmap overlay (cached QPixmap)
    self._draw_heatmap(painter)

    # Layer 3: Dynamic elements (every frame)
    self._draw_nades(painter)
    self._draw_ghosts(painter)
    self._draw_players(painter)

    painter.end()
```

**Performance optimization**:
- Cache map + heatmap as QPixmap (equivalent to Kivy's static InstructionGroups)
- Only call `update()` when frame data changes
- Use QTimer for tick updates instead of Kivy Clock

**Coordinate system**: Reuse `SpatialEngine.world_to_normalized()` — it's pure math, no Kivy deps.

### P4.2 — PlayerSidebar

**Files to create**:
- `qt_app/widgets/tactical/player_sidebar.py` (~250 lines)

**Port from Kivy**: `player_sidebar.py` (362 lines)

**Key translations**:
- `MDList` → `QListWidget` or custom QVBoxLayout with pooled QFrame items
- Widget pooling: Reuse QFrame instances across frames
- `LivePlayerCard`: QFrame with QProgressBar for HP/armor
- Animated height: `QPropertyAnimation` on `maximumHeight`

### P4.3 — Timeline Scrubber

**Files to create**:
- `qt_app/widgets/tactical/timeline.py` (~120 lines)

**Port from Kivy**: `timeline.py` (129 lines)

**Implementation**: Custom `paintEvent()` with QPainter:
- Gray background bar
- Green progress fill
- Colored event marker lines (red kills, yellow bomb plant, blue defuse)
- `mousePressEvent()` / `mouseMoveEvent()` for drag-to-seek

### P4.4 — Ghost Pixel Debug Overlay

**Files to create**:
- `qt_app/widgets/tactical/ghost_pixel.py` (~100 lines)

**Port from Kivy**: `ghost_pixel.py` (140 lines)

**Implementation**: QPainter overlay rendering landmark circles + coordinate tooltip.

### P4.5 — Tactical ViewModels

**Files to create**:
- `qt_app/viewmodels/tactical_playback_vm.py` (~80 lines)
- `qt_app/viewmodels/tactical_ghost_vm.py` (~60 lines)
- `qt_app/viewmodels/tactical_chronovisor_vm.py` (~100 lines)

**Port from Kivy**: `tactical_viewmodels.py` (347 lines)

**Key adaptations**:
- Replace Kivy `EventDispatcher` + Properties with `QObject` + Signals
- Replace `Clock.schedule_once()` with Signal auto-marshaling
- Preserve cooperative cancellation patterns
- Preserve lazy GhostEngine loading

### P4.6 — TacticalViewerScreen

**Files to create**:
- `qt_app/screens/tactical_viewer_screen.py` (~250 lines)

**Port from Kivy**: `tactical_viewer_screen.py` (295 lines)

**Layout**: QSplitter with CT sidebar | TacticalMap | T sidebar + controls bar below.

### P4.7 — Heatmap Pipeline

**Port**: TacticalMap's `update_heatmap_async()` → use Worker + QPixmap caching.
Backend `HeatmapEngine` is pure numpy — no Kivy deps.

---

## 3.6 Phase 5: CI/CD & Quality

### 3.6.1 GitHub Actions Workflow

**File**: `.github/workflows/ci.yml`

```yaml
name: CI
on: [push, pull_request]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.10" }
      - run: pip install black isort flake8 mypy
      - run: black --check .
      - run: isort --check .
      - run: flake8 --max-line-length=100

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.10" }
      - run: pip install -r requirements.txt
      - run: pip install pytest pytest-cov
      - run: pytest --cov=Programma_CS2_RENAN --cov-fail-under=30

  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.10" }
      - run: pip install -r requirements.txt
      - run: python tools/headless_validator.py

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install bandit safety
      - run: bandit -r Programma_CS2_RENAN/ -ll
      - run: safety check
```

### 3.6.2 Pre-commit Hooks

**File**: `.pre-commit-config.yaml`
```yaml
repos:
  - repo: https://github.com/psf/black
    rev: "24.3.0"
    hooks: [{ id: black, args: [--line-length=100] }]
  - repo: https://github.com/pycqa/isort
    rev: "5.13.2"
    hooks: [{ id: isort, args: [--profile=black] }]
  - repo: https://github.com/pycqa/flake8
    rev: "7.0.0"
    hooks: [{ id: flake8, args: [--max-line-length=100] }]
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: "v4.5.0"
    hooks:
      - { id: trailing-whitespace }
      - { id: end-of-file-fixer }
      - { id: check-yaml }
      - { id: check-added-large-files, args: [--maxkb=500] }
      - { id: detect-private-key }
```

### 3.6.3 Headless Validator Extension

Extend `tools/headless_validator.py` to include Qt-specific checks:
- Import smoke test for all Qt screen modules
- Verify no Kivy imports leak into `qt_app/` package
- Verify QSS files parse correctly
- Verify all 13 placeholder keys are registered

### 3.6.4 Automated UI Smoke Tests

**File**: `tests/test_qt_smoke.py`
```python
# Uses QApplication in headless mode (QT_QPA_PLATFORM=offscreen)
def test_all_screens_register():
    """Verify all 13 screens register without crash."""

def test_match_history_renders_empty():
    """Verify MatchHistoryScreen shows 'No matches' when DB is empty."""

def test_theme_switch():
    """Verify all 3 themes apply without crash."""
```

### 3.6.5 Release Packaging

**Target**: PyInstaller single-directory bundle

```python
# pyinstaller.spec
a = Analysis(
    ['Programma_CS2_RENAN/apps/qt_app/app.py'],
    datas=[
        ('Programma_CS2_RENAN/apps/qt_app/themes/*.qss', 'themes'),
        ('Programma_CS2_RENAN/assets/i18n/*.json', 'assets/i18n'),
        ('Programma_CS2_RENAN/PHOTO_GUI/maps/*.png', 'PHOTO_GUI/maps'),
    ],
    hiddenimports=['PySide6.QtCharts'],
)
```

---

## 3.7 Downstream/Upstream Service Integration Map

### Upstream Services (Data Producers → UI Consumers)

```
┌──────────────────────────────────────────────────────────────────┐
│                    SESSION ENGINE (subprocess)                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ Scanner  │  │ Digester │  │ Teacher  │  │  Pulse   │       │
│  │ (Hunter) │  │          │  │          │  │(Heartbeat)│       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘       │
│       │              │              │              │             │
│       ▼              ▼              ▼              ▼             │
│  IngestionTask   PlayerMatch   CoachState     CoachState       │
│  (queue)         Stats (DB)    (training)    (heartbeat)       │
└──────────────────────────────────────────────────────────────────┘
         │                │              │              │
         ▼                ▼              ▼              ▼
┌──────────────────────────────────────────────────────────────────┐
│                     QT FRONTEND (AppState bridge)                │
│                                                                  │
│  AppState polls CoachState every 2s via QTimer                  │
│  ├── coach_status → Dashboard ML status bar                     │
│  ├── parsing_progress → Dashboard progress bar                  │
│  ├── belief_confidence → Coach belief state card                │
│  ├── knowledge_ticks → Coach knowledge engine card              │
│  ├── current_epoch/total_epochs → Training status card          │
│  └── train_loss/val_loss → Training loss display                │
│                                                                  │
│  Direct DB queries (read-only, via ViewModels):                 │
│  ├── PlayerMatchStats → Match History, Match Detail             │
│  ├── RoundStats → Match Detail Rounds tab                       │
│  ├── CoachingInsight → Match Detail Highlights tab              │
│  └── Analytics service → Performance Dashboard                   │
└──────────────────────────────────────────────────────────────────┘
```

### Downstream Services (UI Actions → Backend Effects)

```
┌─────────────────────────────────────────────────────────────────┐
│                     QT FRONTEND (User Actions)                   │
│                                                                  │
│  Settings Screen                                                 │
│  ├── save_user_setting() → core/config.py → user_settings.json  │
│  ├── set_app_theme() → ThemeEngine → QSS + QPalette reload     │
│  └── set_language() → i18n.set_language() → language_changed    │
│                                                                  │
│  Dashboard Screen                                                │
│  ├── toggle_ai_service() → session_engine start/stop (IPC)     │
│  ├── set_pro_ingest_speed() → config update → Scanner reads    │
│  ├── open_folder_picker() → QFileDialog → save_user_setting()  │
│  └── soft_restart_service() → session_engine restart (IPC)     │
│                                                                  │
│  Coach Screen                                                    │
│  ├── send_message() → CoachingChatVM → Ollama API              │
│  ├── show_brain_dialog() → ML model info display               │
│  └── show_pro_comparison() → AnalysisService.get_pro_comparison│
│                                                                  │
│  Tactical Viewer                                                 │
│  ├── Load demo → DemoLoader.load_demo() → PlaybackEngine       │
│  ├── Toggle playback → PlaybackEngine.play()/pause()           │
│  ├── Ghost predict → GhostEngine.predict_ghosts() (lazy load)  │
│  ├── Scan CMs → ChronovisorScanner.scan_match() (background)  │
│  └── Generate heatmap → HeatmapEngine (background thread)      │
│                                                                  │
│  Steam/FaceIT Config                                             │
│  ├── save_multiple_configs() → keyring (Windows) or config     │
│  └── open_url() → QDesktopServices.openUrl()                   │
└─────────────────────────────────────────────────────────────────┘
```

### Background Daemons — Impact on Qt Frontend

| Daemon | What It Writes | UI Effect |
|--------|---------------|-----------|
| **Scanner (Hunter)** | `IngestionTask` rows, `CoachState.ingest_status` | Dashboard shows scan progress |
| **Digester** | `PlayerMatchStats`, `PlayerTickState`, `RoundStats` | Match History shows new matches |
| **Teacher** | `CoachState.ml_status`, model checkpoints | Dashboard shows training progress |
| **Pulse** | `CoachState.last_heartbeat` | Dashboard shows "Running" vs "Offline" |
| **Watcher** | `IngestionTask` rows on new .dem files | Auto-triggers processing pipeline |

### Database Concurrency Model
```
Session Engine Subprocess (writes)
├── Scanner → INSERT IngestionTask
├── Digester → INSERT/UPDATE PlayerMatchStats, PlayerTickState, RoundStats
├── Teacher → UPDATE CoachState (training progress)
└── Pulse → UPDATE CoachState (heartbeat)

Qt Frontend Process (reads only)
├── ViewModels → SELECT PlayerMatchStats, RoundStats, CoachingInsight
├── AppState → SELECT CoachState (poll every 2s)
└── Analytics → SELECT aggregations via analytics service

SQLite WAL mode enables concurrent readers + single writer.
Pool: pool_size=1, max_overflow=4, timeout=30s.
```

---

## 3.8 Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|-----------|
| QPainter TacticalMap performance vs Kivy Canvas | HIGH | Profile early, use QPixmap caching for static layers |
| PySide6 QtCharts availability on all platforms | MEDIUM | Fall back to matplotlib if QtCharts unavailable |
| Thread safety with QThreadPool vs daemon=True | MEDIUM | Use Worker pattern consistently, test concurrency |
| QSS styling gaps (no equivalent for some KivyMD features) | LOW | Custom QWidget painting where QSS is insufficient |
| Import isolation (prevent Kivy imports in Qt package) | LOW | Headless validator check + import linting |
| Font availability across platforms | LOW | Bundle key fonts as Qt resources |

---

## 3.9 Success Criteria

1. All 13 Qt screens render real content (zero placeholder screens remaining)
2. `python tools/headless_validator.py` passes with Qt-specific checks
3. Zero Kivy imports in `qt_app/` directory tree
4. All 6 chart types render correctly with real data
5. Tactical Viewer plays demo at 30+ FPS via QPainter
6. Theme switching works live for all 3 themes
7. Language switching works live for all 3 languages
8. GitHub Actions CI passes all jobs (lint, test, validate, security)
9. Pre-commit hooks pass for all staged changes
10. Release package builds and runs on clean system

---

## 3.10 Estimated Scope per Phase

| Phase | New Files | Lines (est.) | Backend Connections |
|-------|-----------|-------------|-------------------|
| Phase 1 | 4 | ~530 | config, save_user_setting |
| Phase 2 | 4 | ~830 | AppState bridge, Ollama, analytics |
| Phase 3 | 3 | ~240 | config, QDesktopServices |
| Phase 4 | 8 | ~1,560 | PlaybackEngine, SpatialEngine, GhostEngine, HeatmapEngine, ChronovisorScanner, MapManager |
| Phase 5 | 4 | ~300 | CI config files |
| **Total** | **23** | **~3,460** | |

This brings the Qt frontend from ~2,500 lines to ~6,000 lines — approaching parity with the Kivy frontend's ~5,400 lines, with the added benefit of GPU-accelerated charts and native OS integration.
