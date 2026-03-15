# Demo Ingestion Pipelines

> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Português](README_PT.md)**

Demo ingestion infrastructure for professional and user CS2 demos with Steam integration and round-level statistical enrichment.

## Core Components

### Main Orchestrators

**`demo_loader.py`** — Main demo loading orchestrator
- Coordinates demo file parsing with demoparser2
- Integrity validation via `integrity.py`
- Delegates to user_ingest.py or pro_ingest.py based on demo source
- Progress tracking and error recovery

**`steam_locator.py`** — Steam installation discovery
- Multi-platform CS2 installation detection (Windows, Linux, macOS)
- Registry parsing (Windows) and filesystem scanning
- Demo folder auto-detection

**`hltv_orchestrator.py`** — HLTV pro player statistics synchronization orchestrator
- Coordinates scraping of professional player statistics from hltv.org (Rating 2.0, K/D, ADR, etc.)
- Rate limiting enforcement
- Cache management
- Browser automation lifecycle
- **NOTE:** This does NOT handle demo files or demo metadata — only pro player stats

**`downloader.py`** — Demo file downloader
- HTTP/HTTPS download with retry logic
- Integrity verification (checksum)
- Concurrent download management

**`integrity.py`** — Demo file integrity validation
- File format verification
- Header parsing
- Corruption detection

## Sub-Packages

### `pipelines/`

**`user_ingest.py`** — User demo ingestion pipeline
- Parses user demos via demoparser2
- Extracts round statistics with `round_stats_builder.py`
- Enriches with `enrich_from_demo()` (noscope/blind kills, flash assists, utility usage)
- Persists to RoundStats + PlayerMatchStats tables

**`pro_ingest.py`** — Professional demo ingestion pipeline
- Professional demo parsing with round-level statistical enrichment
- Round-level statistical enrichment
- Knowledge record generation for RAG system
- Pro baseline statistical updates

**`json_tournament_ingestor.py`** — Tournament JSON batch ingestion
- Bulk import from tournament data exports
- Schema validation
- Conflict resolution

### `hltv/`

HLTV scraping infrastructure with rate limiting and caching.

**`hltv_api_service.py`** — HLTV API client
- RESTful interface to HLTV data
- Authentication handling
- Response parsing and normalization

**`rate_limit.py`** — Rate limiter
- Token bucket algorithm
- Per-endpoint rate limits
- Exponential backoff on 429 responses

**`selectors.py`** — CSS selectors and URL builders
- Playwright selector definitions
- URL construction for matches, players, teams, events

**`browser/`** — Playwright automation
- Headless browser management
- Page interaction patterns
- Cookie persistence

**`collectors/`** — Data collectors
- Match metadata collector
- Player statistics collector
- Team roster collector
- Event/tournament collector

**`cache/`** — Response caching
- File-based cache with TTL
- Cache invalidation strategies
- Cache key generation

### `hltv_api/`

Third-party HLTV API wrapper (Go-based external service).

### `registry/`

Demo file registry and lifecycle management
- Demo file tracking (processed, pending, failed)
- Duplicate detection
- Retention policies
- Cleanup automation
