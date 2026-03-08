# HLTV Professional Player Statistics

> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Português](README_PT.md)**

## Overview

Background service that scrapes **pro player statistics** (text data only) from HLTV.org via FlareSolverr (Docker). Data is stored in an isolated `hltv_metadata.db` database, separate from the main demo ingestion pipeline.

## Key Components

### `stat_fetcher.py`
- **`HLTVStatFetcher`** — Main scraping service using FlareSolverr + BeautifulSoup
- Fetches player stats: Rating 2.0, KPR, DPR, ADR, KAST, HS%, Impact
- Deep-crawls sub-pages: Clutches, Multikills, Career history
- Saves to `ProPlayer` + `ProPlayerStatCard` in `hltv_metadata.db`

### `flaresolverr_client.py`
- **`FlareSolverrClient`** — REST client for the local FlareSolverr Docker container
- Handles Cloudflare challenge resolution automatically
- Persistent session support for cookie reuse across requests

### `rate_limit.py`
- **`RateLimiter`** — Multi-tier rate limiting (micro/standard/heavy/backoff)
- Conservative delays: 4-8s standard, 10-20s heavy, 45-90s backoff
- Random jitter to avoid detectable request patterns

### `docker_manager.py`
- Auto-starts FlareSolverr Docker container if not running
- Health-check polling with configurable timeout
- Graceful shutdown support

### `selectors.py`
- **`HLTVURLBuilder`** — URL construction for HLTV stats pages
- **`PlayerStatsSelectors`** — CSS selectors for player stats extraction

## Database Isolation

HLTV tables (`ProPlayer`, `ProPlayerStatCard`, `ProTeam`) live in `hltv_metadata.db`, completely separate from the main `database.db` used by demo ingestion and ML pipelines.

- **Write path**: `stat_fetcher.py` -> `get_hltv_db_manager()` -> `hltv_metadata.db`
- **Read path** (coach): `token_resolver.py`, `pro_baseline.py`, `nickname_resolver.py` -> `get_hltv_db_manager()` (read-only)

## Entry Point

The service is started via `hltv_sync_service.py` which runs as a background daemon, controlled by the console (`console.py` -> `supervisor`).

## Rate Limiting

Default delays are intentionally conservative to avoid Cloudflare blocks. The service prioritizes reliability over speed.
