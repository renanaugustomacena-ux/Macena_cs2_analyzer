> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Português](README_PT.md)**

# Advanced — Stub de Modulos Experimentais

Namespace reservado para experimentos de arquiteturas neurais avancadas.

## Estado Atual

Os modulos experimentais originais (`brain_bridge.py`, `superposition_net.py`, `feature_engineering.py`) foram removidos durante a fase de remediacao G-06 como codigo morto sem nenhum chamador em todo o codebase.

## Localizacoes Canonicas

As funcionalidades sobreviventes agora residem em suas localizacoes canonicas:

- **SuperpositionLayer** — `backend/nn/layers/superposition.py`
- **Orquestracao BrainBridge** — Absorvida em `backend/nn/rap_coach/model.py` (RAPCoachModel)
- **Feature engineering** — `backend/processing/feature_engineering/vectorizer.py` (FeatureExtractor)

## Conteudo do Pacote

- `__init__.py` — Stub de pacote com comentario historico da remocao
