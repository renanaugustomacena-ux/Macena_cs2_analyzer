# Scraping Dati Professionali HLTV

> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Português](README_PT.md)**

## Panoramica

Infrastruttura di web scraping per statistiche di giocatori professionisti CS2 e risultati match da HLTV.org usando automazione browser Playwright. Include rate limiting, caching risposte e gestione robusta selettori CSS.

## Componenti Chiave

### `hltv_api_service.py`
- **`HLTVApiService`** — Servizio scraping principale con automazione browser Playwright
- Recupera statistiche giocatori, risultati match, composizioni team, dati tornei
- Gestione errori con logica retry e protezione timeout

### `rate_limit.py`
- **`RateLimiter`** — Rate limiting richieste per rispettare carico server HLTV
- Soglia configurabile richieste-per-minuto
- Implementazione algoritmo token bucket

### `selectors.py`
- **`HLTVURLBuilder`** — Costruzione URL per pagine HLTV (statistiche giocatori, dettagli match, pagine team)
- **`PlayerStatsSelectors`** — Selettori CSS per estrazione statistiche giocatori
- Gestione selettori centralizzata per manutenibilità contro cambi layout sito

### Sotto-directory

#### `browser/`
- Gestione contesto browser Playwright
- Configurazione Chrome headless
- Gestione cookie e sessioni

#### `collectors/`
- **`PlayerCollector`** — Estrazione dati giocatori specializzata
- Parsing risultati match
- Aggregazione roster team

#### `cache/`
- Livello caching risposte per minimizzare richieste ridondanti
- Scadenza cache basata su TTL
- Strategie invalidazione cache

## Integrazione

Usato dalla pipeline `pro_ingest.py` per popolare tabelle `ProPlayer`, `MatchResult` e `TeamComposition`. I dati HLTV servono come ground truth per baseline professionali e analisi meta-gioco.

## Rate Limiting

Default: 10 richieste/minuto. Configurabile tramite `config.HLTV_RATE_LIMIT`. Il superamento del limite attiva backoff esponenziale.

## Gestione Errori

Fallimenti rete, timeout ed errori parsing sono loggati con ID correlazione. Richieste fallite vengono ritentate fino a 3 volte con backoff esponenziale.
