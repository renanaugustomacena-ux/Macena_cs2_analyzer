# Applicazione Desktop Qt (Primaria)

> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Portugues](README_PT.md)**

Applicazione desktop PySide6/Qt che implementa l'architettura MVVM con Signal/Slot per l'analisi tattica CS2 e il coaching AI. Questo e il frontend primario, che sostituisce l'app legacy Kivy/KivyMD in [desktop_app/](../desktop_app/).

## Punto di Ingresso

```bash
python -m Programma_CS2_RENAN.apps.qt_app.app
```

## Architettura

**Pattern:** Model-View-ViewModel (MVVM) con Qt Signal/Slot

- **Views:** Classi Screen (QWidget) con navigazione sidebar
- **ViewModels:** Sottoclassi QObject che emettono Signals per binding reattivo dei dati
- **Models:** Livello dati backend (SQLModel) accessibile tramite Worker threads
- **Flusso dati:** Screen <-> ViewModel (QObject + Signals) <-> Database (SQLModel) con Worker threads

## Componenti Core

| File | Scopo |
|------|-------|
| `app.py` | Punto di ingresso, crea QApplication, registra 13 schermate |
| `main_window.py` | QMainWindow con navigazione sidebar + QStackedWidget |
| `core/app_state.py` | Singleton AppState che interroga CoachState ogni 10s |
| `core/theme_engine.py` | ThemeEngine con QSS + palette + gestione wallpaper |
| `core/worker.py` | Pattern Worker per task in background usando QThreadPool |

## Schermate (13)

1. **HomeScreen** -- Dashboard e panoramica
2. **CoachScreen** -- Interfaccia coaching AI
3. **MatchHistoryScreen** -- Elenco partite con rating HLTV 2.0 codificato per colore
4. **MatchDetailScreen** -- Analisi partita multi-sezione (panoramica, round, economia, momentum)
5. **PerformanceScreen** -- Analisi prestazioni (trend, statistiche per mappa, confronti Z-score)
6. **TacticalViewerScreen** -- Replay mappa 2D con rendering pixel-accurate e timeline
7. **UserProfileScreen** -- Visualizzazione profilo utente
8. **ProfileScreen** -- Gestione profilo
9. **SettingsScreen** -- Impostazioni applicazione
10. **WizardScreen** -- Procedura guidata di configurazione iniziale per integrazione Steam
11. **HelpScreen** -- Documentazione e guide utente
12. **SteamConfigScreen** -- Configurazione integrazione Steam
13. **FaceitConfigScreen** -- Configurazione integrazione Faceit

## ViewModels (7)

| ViewModel | Scopo |
|-----------|-------|
| `match_history_vm` | Dati elenco partite, filtraggio e ordinamento |
| `match_detail_vm` | Dati analisi per partita (round, economia, highlights) |
| `performance_vm` | Trend prestazioni, statistiche per mappa, punti di forza/debolezza |
| `tactical_vm` | Playback tactical viewer, rendering ghost, chronovisor |
| `coach_vm` | Stato sessione coaching e interazione AI |
| `coaching_chat_vm` | Gestione dialogo coaching AI |
| `user_profile_vm` | Dati profilo utente e statistiche |

## Widget

### Grafici (`widgets/charts/`)

- `RadarChartWidget` -- Radar prestazioni multidimensionale
- `MomentumGraphWidget` -- Evoluzione momentum squadra
- `EconomyGraphWidget` -- Timeline economia round-by-round
- `RatingSparklineWidget` -- Sparkline compatto storico rating
- `TrendGraphWidget` -- Visualizzazione trend serie temporali
- `UtilityBarWidget` -- Barre confronto utilizzo utility (utente vs baseline pro)

### Tattici (`widgets/tactical/`)

- `MapWidget` -- Rendering mappa tattica 2D pixel-accurate
- `PlayerSidebar` -- Visualizzazione stato giocatore in tempo reale
- `TimelineWidget` -- Navigazione e scrubbing playback demo

## Temi

Il `ThemeEngine` (`core/theme_engine.py`) gestisce:

- **Fogli di stile QSS** per styling consistente dei widget
- **Palette colori** con supporto modalita chiara/scura
- **Gestione wallpaper** per personalizzazione sfondo
