# Ingestion Pipeline Implementations

> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Português](README_PT.md)**

## Overview

Demo file ingestion pipelines for different data sources: user demos, professional demos, and tournament JSON files. All pipelines now include round-level statistical enrichment via `round_stats_builder.py`.

## Key Pipelines

### `user_ingest.py`
- **`ingest_user_demos()`** — User demo file processing pipeline
- Parses `.dem` files from user's Steam CS2 directory
- Extracts tick-level events, player states, round outcomes
- **Round stats enrichment**: Calls `aggregate_round_stats_to_match()` + `enrich_from_demo()`
- Persists to `PlayerMatchStats` (aggregated) and `RoundStats` (per-round) tables
- Creates per-match SQLite database via `MatchDataManager`

### `pro_ingest.py`
- **`ingest_pro_demos()`** — Professional demo processing pipeline
- Sources demos from `PRO_DEMO_PATH` directory
- Pro baseline statistical enrichment via `round_stats_builder` (per-round HLTV 2.0 rating calculation, noscope/blind kills, flash assists)
- **Round stats enrichment**: Same as user pipeline — `enrich_from_demo()` populates `RoundStats`
- Populates `ProPlayer`, `MatchResult`, `TeamComposition` tables
- Generates tactical knowledge records for RAG retrieval

### `json_tournament_ingestor.py`
- **`process_tournament_jsons()`** — Tournament JSON file ingestion
- Processes structured JSON exports from tournament databases
- Validates schema, extracts match metadata, player stats, round timelines
- Batch insert with transaction boundaries
- Used for historical data import and offline tournament analysis

## Common Patterns

All pipelines follow this flow:
1. **Discovery**: Scan source directory for unprocessed files
2. **Validation**: Check file integrity, format, schema
3. **Parsing**: Extract structured data via demo parser
4. **Enrichment**: Round stats, spatial data
5. **Persistence**: Atomic DB writes with rollback on error
6. **Registration**: Mark file as processed in `DemoFileRecord` registry

## Round Stats Integration (2026-02-16)

Phase 1 of Fusion Plan connected aggregation pipeline:
- `round_stats_builder.py` now called by both user and pro ingestion
- Per-round HLTV 2.0 rating, noscope kills, blind kills, flash assists all persisted
- `RoundStats` table extended with new fields
- Momentum timeline construction now uses `RoundStats.compute_round_rating()`

## Error Handling

Ingestion failures are logged with correlation IDs. Partial ingestion is rolled back. Failed files are marked with error state in registry for manual review.
