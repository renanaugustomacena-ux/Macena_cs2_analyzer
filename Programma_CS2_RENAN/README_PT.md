> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Portugues](README_PT.md)**

# Programma_CS2_RENAN

Pacote principal da aplicacao Macena CS2 Analyzer — coach tatico com IA para Counter-Strike 2.

## Visao Geral

Este pacote contem todo o codigo da aplicacao organizado em uma arquitetura em camadas seguindo o pipeline **OBSERVA > APRENDE > PENSA > FALA**:

```
OBSERVA (Ingestao) →  APRENDE (Treinamento) →  PENSA (Inferencia) →  FALA (Dialogo)
    Daemon Hunter        Daemon Teacher            Pipeline COPER       Template + Ollama
    Parsing de demos     Maturidade em 3 estagios  Conhecimento RAG     Atribuicao causal
    Extracao de features Treinamento multi-modelo   Teoria dos jogos     Comparacoes com pros
```

## Estrutura

```
Programma_CS2_RENAN/
├── apps/qt_app/            UI Desktop PySide6/Qt (primaria, padrao MVVM)
├── apps/desktop_app/       UI Desktop Kivy/KivyMD (legacy fallback, padrao MVVM)
├── backend/                Camada de logica de negocios
│   ├── analysis/           Teoria dos jogos, modelos de crenca, momentum
│   ├── coaching/           Pipeline de coaching (COPER, Hibrido, RAG)
│   ├── data_sources/       Parser de demos, estatísticas pro HLTV, Steam, APIs Faceit
│   ├── knowledge/          Base de conhecimento RAG, banco de experiencias COPER
│   ├── nn/                 Redes neurais (6 tipos de modelo)
│   ├── processing/         Feature engineering, baselines, validacao
│   ├── services/           Camada de servicos (Coaching, Analise, Ollama)
│   └── storage/            Banco de dados SQLite, modelos, backup
├── core/                   Motor de sessao, gerenciamento de assets, dados espaciais
├── ingestion/              Pipelines de ingestao de demos (Steam)
├── observability/          Integridade RASP, telemetria, Sentry
├── reporting/              Visualizacao, geracao de PDF
├── tests/                  Suite de testes (390+ testes)
└── tools/                  Ferramentas de validacao e diagnostico
```

## Pontos de Entrada Principais

| Arquivo | Proposito |
|---------|-----------|
| `apps/qt_app/app.py` | Aplicacao desktop (GUI PySide6/Qt — primaria) |
| `apps/desktop_app/main.py` | Aplicacao desktop (GUI Kivy — legacy fallback) |
| `run_ingestion.py` | Pipeline de ingestao de demos |
| `fetch_hltv_stats.py` | Scraping de estatísticas de jogadores profissionais HLTV |
| `hltv_sync_service.py` | Daemon de sincronizacao HLTV |

## Stack Tecnologico

- **UI**: PySide6/Qt (primaria) + Kivy/KivyMD (legacy fallback)
- **ML**: PyTorch, ncps (LTC), redes Hopfield
- **Banco de Dados**: SQLite (modo WAL) via SQLModel
- **Scraping**: Playwright (sync)
- **Observabilidade**: TensorBoard, Sentry
