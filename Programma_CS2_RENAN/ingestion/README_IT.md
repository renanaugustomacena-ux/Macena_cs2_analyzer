# Pipeline di Ingestion Demo

> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Português](README_PT.md)**

Infrastruttura di ingestion demo per demo CS2 professionali e utente con integrazione Steam e arricchimento statistico a livello di round.

## Componenti Principali

### Orchestratori Principali

**`demo_loader.py`** — Orchestratore principale caricamento demo
- Coordina parsing file demo con demoparser2
- Validazione integrità via `integrity.py`
- Delega a user_ingest.py o pro_ingest.py in base alla sorgente demo
- Tracciamento progresso e recupero errori

**`steam_locator.py`** — Rilevamento installazione Steam
- Rilevamento installazione CS2 multi-piattaforma (Windows, Linux, macOS)
- Parsing registry (Windows) e scansione filesystem
- Auto-rilevamento cartella demo

**`hltv_orchestrator.py`** — Orchestratore sincronizzazione statistiche giocatori professionisti HLTV
- Coordina scraping statistiche giocatori professionisti da hltv.org (Rating 2.0, K/D, ADR, ecc.)
- Applicazione rate limiting
- Gestione cache
- Ciclo di vita automazione browser
- **NOTA:** Questo NON gestisce file demo o metadati demo — solo statistiche giocatori professionisti

**`downloader.py`** — Downloader file demo
- Download HTTP/HTTPS con logica retry
- Verifica integrità (checksum)
- Gestione download concorrenti

**`integrity.py`** — Validazione integrità file demo
- Verifica formato file
- Parsing header
- Rilevamento corruzione

## Sub-Package

### `pipelines/`

**`user_ingest.py`** — Pipeline ingestion demo utente
- Parsing demo utente via demoparser2
- Estrazione statistiche round con `round_stats_builder.py`
- Arricchimento con `enrich_from_demo()` (kill noscope/blind, flash assist, utilizzo utility)
- Persistenza su tabelle RoundStats + PlayerMatchStats

**`pro_ingest.py`** — Pipeline ingestion demo professionali
- Parsing demo professionali con arricchimento statistico a livello di round
- Arricchimento statistico a livello di round
- Generazione record conoscenza per sistema RAG
- Aggiornamento baseline statistiche pro

**`json_tournament_ingestor.py`** — Ingestion batch JSON torneo
- Importazione massiva da export dati torneo
- Validazione schema
- Risoluzione conflitti

### `hltv/`

Infrastruttura scraping HLTV con rate limiting e caching.

**`hltv_api_service.py`** — Client API HLTV
- Interfaccia RESTful a dati HLTV
- Gestione autenticazione
- Parsing e normalizzazione risposte

**`rate_limit.py`** — Rate limiter
- Algoritmo token bucket
- Rate limit per endpoint
- Backoff esponenziale su risposte 429

**`selectors.py`** — Selettori CSS e builder URL
- Definizioni selettori Playwright
- Costruzione URL per partite, giocatori, team, eventi

**`browser/`** — Automazione Playwright
- Gestione browser headless
- Pattern interazione pagina
- Persistenza cookie

**`collectors/`** — Collector dati
- Collector metadati partite
- Collector statistiche giocatori
- Collector roster team
- Collector eventi/tornei

**`cache/`** — Caching risposte
- Cache file-based con TTL
- Strategie invalidazione cache
- Generazione chiavi cache

### `hltv_api/`

Wrapper API HLTV di terze parti (servizio esterno basato su Go).

### `registry/`

Registry file demo e gestione ciclo di vita
- Tracciamento file demo (processati, pending, falliti)
- Rilevamento duplicati
- Politiche retention
- Automazione pulizia
