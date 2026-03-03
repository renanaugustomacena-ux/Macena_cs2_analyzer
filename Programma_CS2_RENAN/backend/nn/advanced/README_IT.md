> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Português](README_PT.md)**

# Advanced — Stub Moduli Sperimentali

Namespace riservato per esperimenti di architetture neurali avanzate.

## Stato Attuale

I moduli sperimentali originali (`brain_bridge.py`, `superposition_net.py`, `feature_engineering.py`) sono stati rimossi durante la fase di remediation G-06 in quanto codice morto senza alcun chiamante nell'intero codebase.

## Posizioni Canoniche

Le funzionalita sopravvissute risiedono ora nelle posizioni canoniche:

- **SuperpositionLayer** — `backend/nn/layers/superposition.py`
- **Orchestrazione BrainBridge** — Assorbita in `backend/nn/rap_coach/model.py` (RAPCoachModel)
- **Feature engineering** — `backend/processing/feature_engineering/vectorizer.py` (FeatureExtractor)

## Contenuto Pacchetto

- `__init__.py` — Stub pacchetto con commento storico della rimozione
