> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Portugues](README_PT.md)**

# Programma_CS2_RENAN

Pacchetto applicativo principale del Macena CS2 Analyzer — coach tattico basato su IA per Counter-Strike 2.

## Panoramica

Questo pacchetto contiene l'intero codice dell'applicazione organizzato in un'architettura a livelli seguendo la pipeline **GUARDA > IMPARA > PENSA > PARLA**:

```
GUARDA (Ingestione) →  IMPARA (Addestramento) →  PENSA (Inferenza) →  PARLA (Dialogo)
    Daemon Hunter         Daemon Teacher             Pipeline COPER       Template + Ollama
    Parsing demo          Maturita a 3 stadi         Conoscenza RAG       Attribuzione causale
    Estrazione feature    Training multi-modello      Teoria dei giochi    Confronti con i pro
```

## Struttura

```
Programma_CS2_RENAN/
├── apps/qt_app/            UI Desktop PySide6/Qt (primaria, pattern MVVM)
├── apps/desktop_app/       UI Desktop Kivy/KivyMD (legacy fallback, pattern MVVM)
├── backend/                Livello logica di business
│   ├── analysis/           Teoria dei giochi, modelli di credenza, momentum
│   ├── coaching/           Pipeline coaching (COPER, Ibrido, RAG)
│   ├── data_sources/       Parser demo, statistiche pro HLTV, Steam, API Faceit
│   ├── knowledge/          Base di conoscenza RAG, banca esperienze COPER
│   ├── nn/                 Reti neurali (6 tipi di modello)
│   ├── processing/         Feature engineering, baseline, validazione
│   ├── services/           Livello servizi (Coaching, Analisi, Ollama)
│   └── storage/            Database SQLite, modelli, backup
├── core/                   Motore sessione, gestione asset, dati spaziali
├── ingestion/              Pipeline ingestione demo (Steam)
├── observability/          Integrita RASP, telemetria, Sentry
├── reporting/              Visualizzazione, generazione PDF
├── tests/                  Suite di test (390+ test)
└── tools/                  Strumenti di validazione e diagnostica
```

## Punti di Ingresso Principali

| File | Scopo |
|------|-------|
| `apps/qt_app/app.py` | Applicazione desktop (GUI PySide6/Qt — primaria) |
| `apps/desktop_app/main.py` | Applicazione desktop (GUI Kivy — legacy fallback) |
| `run_ingestion.py` | Pipeline di ingestione demo |
| `fetch_hltv_stats.py` | Scraping statistiche giocatori professionisti HLTV |
| `hltv_sync_service.py` | Daemon di sincronizzazione HLTV |

## Stack Tecnologico

- **UI**: PySide6/Qt (primaria) + Kivy/KivyMD (legacy fallback)
- **ML**: PyTorch, ncps (LTC), reti Hopfield
- **Database**: SQLite (modalita WAL) via SQLModel
- **Scraping**: Playwright (sync)
- **Osservabilita**: TensorBoard, Sentry
