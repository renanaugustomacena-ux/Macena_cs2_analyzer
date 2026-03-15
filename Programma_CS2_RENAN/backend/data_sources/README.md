> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Português](README_PT.md)**

# Data Sources — External Integrations

External data source integrations for demo parsing, professional player statistics, Steam profile synchronization, and FACEIT platform data.

## Core Modules

### Demo Parsing
- **demo_parser.py** — `parse_demo()` — demoparser2 wrapper with HLTV 2.0 rating calculation, exports per-tick and per-round data
- **demo_format_adapter.py** — `DemoFormatAdapter` — Format conversion and validation between demo parser outputs and internal schemas
- **event_registry.py** — Event type registration and dispatch for demo events

### Detection & Analysis
- **trade_kill_detector.py** — `TradeKillDetector` — Identifies trade frags from tick data (kills within 3-second windows)

### Steam Integration
- **steam_api.py** — `SteamAPI` — Steam Web API integration for profile synchronization, friend list, game stats
- **steam_demo_finder.py** — `SteamDemoFinder` — Locates CS2 demo files in Steam userdata directories

### FACEIT Integration
- **faceit_api.py** — `FaceitAPI` — FACEIT platform API wrapper for match history and player stats
- **faceit_integration.py** — `FaceitIntegration` — High-level FACEIT data ingestion orchestration

### HLTV Integration
- **hltv_metadata.py** — `HLTVMetadata` — Legacy module (see hltv/ package for active implementation)
- **hltv_scraper.py** — `HLTVScraper` — Scrapes professional player statistics from hltv.org (Rating 2.0, K/D, ADR, KAST, HS%)

## Data Flow
1. Demos ingested via `demo_parser.py` → validated by `demo_format_adapter.py`
2. Steam/FACEIT profiles synced via respective API modules
3. HLTV pro player statistics provide the coaching baseline for comparing user performance against pros
4. Trade kills detected post-parse for tactical analysis

## Dependencies
demoparser2, FlareSolverr/Docker (HLTV pro stats), requests (Steam/FACEIT APIs).
