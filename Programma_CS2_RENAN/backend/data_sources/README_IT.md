> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Português](README_PT.md)**

# Data Sources — Integrazioni Esterne

Integrazioni sorgenti dati esterne per parsing demo, statistiche giocatori professionisti, sincronizzazione profili Steam e dati piattaforma FACEIT.

## Moduli Principali

### Parsing Demo
- **demo_parser.py** — `parse_demo()` — Wrapper demoparser2 con calcolo rating HLTV 2.0, esporta dati per-tick e per-round
- **demo_format_adapter.py** — `DemoFormatAdapter` — Conversione e validazione formato tra output demo parser e schemi interni
- **event_registry.py** — Registrazione e dispatch tipi evento per eventi demo

### Rilevamento e Analisi
- **trade_kill_detector.py** — `TradeKillDetector` — Identifica trade frags da dati tick (kills entro finestre 3 secondi)

### Integrazione Steam
- **steam_api.py** — `SteamAPI` — Integrazione Steam Web API per sincronizzazione profilo, lista amici, statistiche gioco
- **steam_demo_finder.py** — `SteamDemoFinder` — Localizza file demo CS2 in directory userdata Steam

### Integrazione FACEIT
- **faceit_api.py** — `FaceitAPI` — Wrapper API piattaforma FACEIT per cronologia partite e statistiche giocatore
- **faceit_integration.py** — `FaceitIntegration` — Orchestrazione ingestione dati FACEIT di alto livello

### Integrazione HLTV
- **hltv_metadata.py** — `HLTVMetadata` — Modulo legacy (vedi pacchetto hltv/ per implementazione attiva)
- **hltv_scraper.py** — `HLTVScraper` — Raccoglie statistiche giocatori professionisti da hltv.org (Rating 2.0, K/D, ADR, KAST, HS%)

## Flusso Dati
1. Demo ingeriti via `demo_parser.py` → validati da `demo_format_adapter.py`
2. Profili Steam/FACEIT sincronizzati via rispettivi moduli API
3. Statistiche giocatori professionisti HLTV forniscono il baseline di coaching per confrontare le prestazioni dell'utente con i pro
4. Trade kills rilevati post-parse per analisi tattica

## Dipendenze
demoparser2, FlareSolverr/Docker (statistiche pro HLTV), requests (API Steam/FACEIT).
