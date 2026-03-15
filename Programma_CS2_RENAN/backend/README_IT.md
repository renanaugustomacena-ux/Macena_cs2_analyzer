> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Portugues](README_PT.md)**

# Backend

Livello di logica di business del Macena CS2 Analyzer, organizzato in 14 sotto-pacchetti con principi di design domain-driven.

## Panoramica

Il backend implementa l'intera pipeline di coaching IA — dal parsing grezzo delle demo all'inferenza delle reti neurali fino all'output di coaching in linguaggio naturale. Ogni sotto-pacchetto possiede il proprio dominio, invarianti dei dati e modalita di errore.

## Struttura

```
backend/
├── analysis/           Motori di teoria dei giochi (11 moduli)
├── coaching/           Pipeline di coaching (COPER, Ibrido, RAG, NN)
├── control/            Logica di controllo addestramento
├── data_sources/       Integrazione dati esterni (Parser demo, statistiche pro HLTV, Steam, Faceit)
├── ingestion/          Helper di ingestione backend
├── knowledge/          Base di conoscenza RAG + banca esperienze COPER
├── knowledge_base/     Archiviazione grafo di conoscenza
├── nn/                 Reti neurali (6 tipi di modello, 40+ file)
├── onboarding/         Flusso di onboarding nuovi utenti
├── processing/         Feature engineering, baseline, validazione
├── progress/           Tracciamento progresso addestramento
├── reporting/          Query analitiche per schermate UI
├── services/           Livello servizi (Coaching, Analisi, Dialogo, Ollama)
└── storage/            Database SQLite, SQLModel, backup, dati partite
```

## Pattern Architetturali Chiave

- **Fallback Coaching a 4 Livelli**: COPER > Ibrido > RAG > NN Base
- **Gating Maturita a 3 Stadi**: CALIBRAZIONE > APPRENDIMENTO > MATURO
- **Decadimento Temporale Baseline**: Pesatura esponenziale dell'evoluzione delle abilita
- **Vettore Feature Unificato**: 25 dimensioni via `FeatureExtractor`
- **SQLite Modalita WAL**: Lettura/scrittura concorrente su tutti i database

## Dipendenze tra Sotto-Pacchetti

```
data_sources → processing → analysis → coaching → services
                   ↓            ↓
               knowledge ←── nn (addestramento + inferenza)
                   ↓
               storage (livello persistenza)
```
