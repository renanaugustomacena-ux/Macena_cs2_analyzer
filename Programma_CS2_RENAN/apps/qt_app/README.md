# Qt Desktop Application (Primary)

> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Portugues](README_PT.md)**

PySide6/Qt desktop application implementing MVVM architecture with Signal/Slot for CS2 tactical analysis and AI coaching. This is the primary frontend, replacing the legacy Kivy/KivyMD app at [desktop_app/](../desktop_app/).

## Entry Point

```bash
python -m Programma_CS2_RENAN.apps.qt_app.app
```

## Architecture

**Pattern:** Model-View-ViewModel (MVVM) with Qt Signal/Slot

- **Views:** Screen classes (QWidget) with sidebar navigation
- **ViewModels:** QObject subclasses emitting Signals for reactive data binding
- **Models:** Backend data layer (SQLModel) accessed via Worker threads
- **Data flow:** Screen <-> ViewModel (QObject + Signals) <-> Database (SQLModel) with Worker threads

## Core Components

| File | Purpose |
|------|---------|
| `app.py` | Entry point, creates QApplication, registers 13 screens |
| `main_window.py` | QMainWindow with sidebar navigation + QStackedWidget |
| `core/app_state.py` | AppState singleton polling CoachState every 10s |
| `core/theme_engine.py` | ThemeEngine with QSS + palette + wallpaper management |
| `core/worker.py` | Background task Worker pattern using QThreadPool |

## Screens (13)

1. **HomeScreen** -- Dashboard and overview
2. **CoachScreen** -- AI coaching interface
3. **MatchHistoryScreen** -- Match listing with color-coded HLTV 2.0 ratings
4. **MatchDetailScreen** -- Multi-section match analysis (overview, rounds, economy, momentum)
5. **PerformanceScreen** -- Performance analytics (trends, per-map stats, Z-score comparisons)
6. **TacticalViewerScreen** -- 2D map replay with pixel-accurate rendering and timeline
7. **UserProfileScreen** -- User profile display
8. **ProfileScreen** -- Profile management
9. **SettingsScreen** -- Application settings
10. **WizardScreen** -- First-time setup wizard for Steam integration
11. **HelpScreen** -- User documentation and guides
12. **SteamConfigScreen** -- Steam integration configuration
13. **FaceitConfigScreen** -- Faceit integration configuration

## ViewModels (7)

| ViewModel | Purpose |
|-----------|---------|
| `match_history_vm` | Match list data, filtering, and sorting |
| `match_detail_vm` | Per-match analysis data (rounds, economy, highlights) |
| `performance_vm` | Performance trends, per-map stats, strengths/weaknesses |
| `tactical_vm` | Tactical viewer playback, ghost rendering, chronovisor |
| `coach_vm` | Coaching session state and AI interaction |
| `coaching_chat_vm` | AI coaching dialogue management |
| `user_profile_vm` | User profile data and statistics |

## Widgets

### Charts (`widgets/charts/`)

- `RadarChartWidget` -- Multi-dimensional performance radar
- `MomentumGraphWidget` -- Team momentum evolution
- `EconomyGraphWidget` -- Round-by-round economy timeline
- `RatingSparklineWidget` -- Compact rating history sparkline
- `TrendGraphWidget` -- Time-series trend visualization
- `UtilityBarWidget` -- Utility usage comparison bars (user vs pro baseline)

### Tactical (`widgets/tactical/`)

- `MapWidget` -- Pixel-accurate 2D tactical map rendering
- `PlayerSidebar` -- Real-time player state display
- `TimelineWidget` -- Demo playback navigation and scrubbing

## Theming

The `ThemeEngine` (`core/theme_engine.py`) manages:

- **QSS stylesheets** for consistent widget styling
- **Color palettes** with light/dark mode support
- **Wallpaper management** for background customization
