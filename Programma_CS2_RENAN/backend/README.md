> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Portugues](README_PT.md)**

# Backend

Core business logic layer for the Macena CS2 Analyzer, organized into 14 sub-packages following domain-driven design principles.

## Overview

The backend implements the full AI coaching pipeline — from raw demo parsing through neural network inference to natural language coaching output. Each sub-package owns its domain, data invariants, and failure modes.

## Structure

```
backend/
├── analysis/           Game theory engines (11 modules)
├── coaching/           Coaching pipeline (COPER, Hybrid, RAG, NN)
├── control/            Training control logic
├── data_sources/       External data integration (Demo, HLTV, Steam, Faceit)
├── ingestion/          Backend ingestion helpers
├── knowledge/          RAG knowledge base + COPER experience bank
├── knowledge_base/     Knowledge graph storage
├── nn/                 Neural networks (6 model types, 40+ files)
├── onboarding/         New user onboarding flow
├── processing/         Feature engineering, baselines, validation
├── progress/           Training progress tracking
├── reporting/          Analytics queries for UI screens
├── services/           Service layer (Coaching, Analysis, Dialogue, Ollama)
└── storage/            SQLite database, SQLModel, backup, match data
```

## Key Architectural Patterns

- **4-Level Coaching Fallback**: COPER > Hybrid > RAG > Base NN
- **3-Stage Maturity Gating**: CALIBRATING > LEARNING > MATURE
- **Temporal Baseline Decay**: Exponential weighting of player skill evolution
- **Unified Feature Vector**: 25-dimensional via `FeatureExtractor`
- **SQLite WAL Mode**: Concurrent read/write across all databases

## Sub-Package Dependencies

```
data_sources → processing → analysis → coaching → services
                   ↓            ↓
               knowledge ←── nn (training + inference)
                   ↓
               storage (persistence layer)
```
