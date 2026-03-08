# Statistiche Giocatori Professionisti HLTV

> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Português](README_PT.md)**

## Panoramica

Servizio in background che raccoglie **statistiche giocatori professionisti** (solo dati testuali) da HLTV.org tramite FlareSolverr (Docker). I dati vengono salvati in un database isolato `hltv_metadata.db`, separato dalla pipeline principale di ingestione demo.

## Componenti Chiave

### `stat_fetcher.py`
- **`HLTVStatFetcher`** — Servizio scraping principale tramite FlareSolverr + BeautifulSoup
- Recupera statistiche: Rating 2.0, KPR, DPR, ADR, KAST, HS%, Impact
- Crawl approfondito sotto-pagine: Clutch, Multikill, Storico carriera
- Salva in `ProPlayer` + `ProPlayerStatCard` in `hltv_metadata.db`

### `flaresolverr_client.py`
- **`FlareSolverrClient`** — Client REST per container Docker FlareSolverr locale
- Gestisce automaticamente le challenge Cloudflare
- Supporto sessioni persistenti per riuso cookie

### `rate_limit.py`
- **`RateLimiter`** — Rate limiting multi-livello (micro/standard/heavy/backoff)
- Ritardi conservativi: 4-8s standard, 10-20s heavy, 45-90s backoff

### `docker_manager.py`
- Avvio automatico container Docker FlareSolverr
- Polling health-check con timeout configurabile

### `selectors.py`
- **`HLTVURLBuilder`** — Costruzione URL per pagine statistiche HLTV
- **`PlayerStatsSelectors`** — Selettori CSS per estrazione statistiche

## Isolamento Database

Le tabelle HLTV (`ProPlayer`, `ProPlayerStatCard`, `ProTeam`) risiedono in `hltv_metadata.db`, completamente separate dal `database.db` principale usato per ingestione demo e pipeline ML.

## Punto di Ingresso

Il servizio viene avviato tramite `hltv_sync_service.py` come daemon in background, controllato dalla console.
