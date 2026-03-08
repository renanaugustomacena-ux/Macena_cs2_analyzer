# Estatisticas de Jogadores Profissionais HLTV

> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Português](README_PT.md)**

## Visao Geral

Servico em background que coleta **estatisticas de jogadores profissionais** (apenas dados textuais) do HLTV.org via FlareSolverr (Docker). Os dados sao armazenados em um banco isolado `hltv_metadata.db`, separado do pipeline principal de ingestao de demos.

## Componentes Principais

### `stat_fetcher.py`
- **`HLTVStatFetcher`** — Servico de scraping principal via FlareSolverr + BeautifulSoup
- Busca estatisticas: Rating 2.0, KPR, DPR, ADR, KAST, HS%, Impact
- Deep-crawl de sub-paginas: Clutches, Multikills, Historico de carreira
- Salva em `ProPlayer` + `ProPlayerStatCard` no `hltv_metadata.db`

### `flaresolverr_client.py`
- **`FlareSolverrClient`** — Cliente REST para container Docker FlareSolverr local
- Resolve challenges Cloudflare automaticamente
- Suporte a sessoes persistentes para reuso de cookies

### `rate_limit.py`
- **`RateLimiter`** — Rate limiting multi-nivel (micro/standard/heavy/backoff)
- Delays conservadores: 4-8s padrao, 10-20s pesado, 45-90s backoff

### `docker_manager.py`
- Auto-inicia container Docker FlareSolverr se nao estiver rodando
- Polling de health-check com timeout configuravel

### `selectors.py`
- **`HLTVURLBuilder`** — Construcao de URL para paginas de estatisticas HLTV
- **`PlayerStatsSelectors`** — Seletores CSS para extracao de estatisticas

## Isolamento do Banco de Dados

Tabelas HLTV (`ProPlayer`, `ProPlayerStatCard`, `ProTeam`) ficam no `hltv_metadata.db`, completamente separadas do `database.db` principal usado para ingestao de demos e pipelines ML.

## Ponto de Entrada

O servico e iniciado via `hltv_sync_service.py` como daemon em background, controlado pelo console.
