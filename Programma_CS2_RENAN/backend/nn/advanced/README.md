> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Português](README_PT.md)**

# Advanced — Experimental Module Stub

Namespace reserved for advanced neural architecture experiments.

## Current Status

The original experimental modules (`brain_bridge.py`, `superposition_net.py`, `feature_engineering.py`) were removed during remediation phase G-06 as dead code with zero callers across the entire codebase.

## Canonical Locations

The surviving functionality now lives in its canonical locations:

- **SuperpositionLayer** — `backend/nn/layers/superposition.py`
- **BrainBridge orchestration** — Absorbed into `backend/nn/rap_coach/model.py` (RAPCoachModel)
- **Feature engineering** — `backend/processing/feature_engineering/vectorizer.py` (FeatureExtractor)

## Package Contents

- `__init__.py` — Package stub with removal history comment
