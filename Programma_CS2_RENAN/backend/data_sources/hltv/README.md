# HLTV Professional Data Scraping

> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Português](README_PT.md)**

## Overview

Web scraping infrastructure for professional CS2 player statistics and match results from HLTV.org using Playwright browser automation. Includes rate limiting, response caching, and robust CSS selector management.

## Key Components

### `hltv_api_service.py`
- **`HLTVApiService`** — Main scraping service with Playwright browser automation
- Fetches player stats, match results, team compositions, tournament data
- Error handling with retry logic and timeout protection

### `rate_limit.py`
- **`RateLimiter`** — Request rate limiting to respect HLTV server load
- Configurable requests-per-minute threshold
- Token bucket algorithm implementation

### `selectors.py`
- **`HLTVURLBuilder`** — URL construction for HLTV pages (player stats, match details, team pages)
- **`PlayerStatsSelectors`** — CSS selectors for player statistics extraction
- Centralized selector management for maintainability against site layout changes

### Sub-directories

#### `browser/`
- Playwright browser context management
- Headless Chrome configuration
- Cookie and session handling

#### `collectors/`
- **`PlayerCollector`** — Specialized player data extraction
- Match result parsing
- Team roster aggregation

#### `cache/`
- Response caching layer to minimize redundant requests
- TTL-based cache expiration
- Cache invalidation strategies

## Integration

Used by `pro_ingest.py` pipeline to populate `ProPlayer`, `MatchResult`, and `TeamComposition` tables. HLTV data serves as ground truth for professional baselines and meta-game analysis.

## Rate Limiting

Default: 10 requests/minute. Configurable via `config.HLTV_RATE_LIMIT`. Exceeding limit triggers exponential backoff.

## Error Handling

Network failures, timeouts, and parsing errors are logged with correlation IDs. Failed requests are retried up to 3 times with exponential backoff.
