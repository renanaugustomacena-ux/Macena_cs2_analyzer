# Aplicacao Desktop Qt (Primaria)

> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Portugues](README_PT.md)**

Aplicacao desktop PySide6/Qt implementando arquitetura MVVM com Signal/Slot para analise tatica CS2 e coaching de IA. Este e o frontend primario, substituindo o app legacy Kivy/KivyMD em [desktop_app/](../desktop_app/).

## Ponto de Entrada

```bash
python -m Programma_CS2_RENAN.apps.qt_app.app
```

## Arquitetura

**Padrao:** Model-View-ViewModel (MVVM) com Qt Signal/Slot

- **Views:** Classes Screen (QWidget) com navegacao sidebar
- **ViewModels:** Subclasses QObject emitindo Signals para binding reativo de dados
- **Models:** Camada de dados backend (SQLModel) acessada via Worker threads
- **Fluxo de dados:** Screen <-> ViewModel (QObject + Signals) <-> Database (SQLModel) com Worker threads

## Componentes Core

| Arquivo | Proposito |
|---------|-----------|
| `app.py` | Ponto de entrada, cria QApplication, registra 13 telas |
| `main_window.py` | QMainWindow com navegacao sidebar + QStackedWidget |
| `core/app_state.py` | Singleton AppState consultando CoachState a cada 10s |
| `core/theme_engine.py` | ThemeEngine com QSS + paleta + gerenciamento de wallpaper |
| `core/worker.py` | Padrao Worker para tarefas em background usando QThreadPool |

## Telas (13)

1. **HomeScreen** -- Dashboard e visao geral
2. **CoachScreen** -- Interface de coaching IA
3. **MatchHistoryScreen** -- Lista de partidas com rating HLTV 2.0 codificado por cor
4. **MatchDetailScreen** -- Analise de partida multi-secao (visao geral, rounds, economia, momentum)
5. **PerformanceScreen** -- Analise de desempenho (tendencias, stats por mapa, comparacoes Z-score)
6. **TacticalViewerScreen** -- Replay de mapa 2D com renderizacao pixel-accurate e timeline
7. **UserProfileScreen** -- Exibicao de perfil do usuario
8. **ProfileScreen** -- Gerenciamento de perfil
9. **SettingsScreen** -- Configuracoes da aplicacao
10. **WizardScreen** -- Assistente de configuracao inicial para integracao Steam
11. **HelpScreen** -- Documentacao e guias do usuario
12. **SteamConfigScreen** -- Configuracao de integracao Steam
13. **FaceitConfigScreen** -- Configuracao de integracao Faceit

## ViewModels (7)

| ViewModel | Proposito |
|-----------|-----------|
| `match_history_vm` | Dados da lista de partidas, filtragem e ordenacao |
| `match_detail_vm` | Dados de analise por partida (rounds, economia, highlights) |
| `performance_vm` | Tendencias de desempenho, stats por mapa, forcas/fraquezas |
| `tactical_vm` | Playback do tactical viewer, renderizacao ghost, chronovisor |
| `coach_vm` | Estado da sessao de coaching e interacao IA |
| `coaching_chat_vm` | Gerenciamento de dialogo de coaching IA |
| `user_profile_vm` | Dados de perfil do usuario e estatisticas |

## Widgets

### Graficos (`widgets/charts/`)

- `RadarChartWidget` -- Radar de desempenho multidimensional
- `MomentumGraphWidget` -- Evolucao do momentum da equipe
- `EconomyGraphWidget` -- Linha do tempo de economia round-by-round
- `RatingSparklineWidget` -- Sparkline compacto de historico de rating
- `TrendGraphWidget` -- Visualizacao de tendencia de series temporais
- `UtilityBarWidget` -- Barras de comparacao de uso de utilitarios (usuario vs baseline pro)

### Taticos (`widgets/tactical/`)

- `MapWidget` -- Renderizacao de mapa tatico 2D pixel-accurate
- `PlayerSidebar` -- Exibicao de estado do jogador em tempo real
- `TimelineWidget` -- Navegacao e scrubbing de playback de demo

## Temas

O `ThemeEngine` (`core/theme_engine.py`) gerencia:

- **Folhas de estilo QSS** para estilizacao consistente dos widgets
- **Paletas de cores** com suporte a modo claro/escuro
- **Gerenciamento de wallpaper** para personalizacao de fundo
