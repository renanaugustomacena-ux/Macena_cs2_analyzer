> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Portugues](README_PT.md)**

# Sottosistema di Reti Neurali

Infrastruttura ML completa con 6 architetture di modelli e pipeline di addestramento integrata.

## Architetture dei Modelli

### RAP Coach (`rap_coach/`)
Architettura pedagogica a 7 livelli:
- **Perception Layer** — Estrazione di feature basata su ResNet da situazioni tattiche
- **Memory Layer** — Ibrido LTC-Hopfield con 512 slot associativi per la ritenzione di pattern
- **Strategy Layer** — Meccanismo di attenzione contestuale per la sintesi di decisioni tattiche
- **Pedagogy Layer** — Attribuzione causale per spiegare errori tattici
- **Communication Layer** — Generazione di insight in linguaggio naturale
- **ChronovisorScanner** — Analisi temporale multi-scala (momentum micro/standard/macro)

### JEPA (`jepa_model.py`)
Encoder auto-supervisionato con rete target EMA, loss contrastivo InfoNCE, dizionario di concetti per allineamento semantico.

### VL-JEPA (`jepa_model.py`)
Estensione Vision-Language di JEPA per comprensione tattica visivo-linguistica.

### LSTM+MoE (`model.py`)
AdvancedCoachNN legacy con routing Mixture of Experts per coaching multi-dominio.

### Neural Role Head (`role_head.py`)
Input di meta-feature a 70 dimensioni per consenso soft a 4 ruoli (Entry Fragger / Lurker / Support / AWPer).

### Win Probability Model (`win_probability.py`)
Previsione della probabilità di vincita del round basata su economia, posizionamento e stato del momentum.

## Infrastruttura di Addestramento

- `training_orchestrator.py` — TrainingOrchestrator con sistema di callback plugin
- `coach_manager.py` — CoachTrainingManager con gate di maturità a 3 fasi (doubt/learning/conviction)
- `factory.py` — ModelFactory per istanziazione unificata di tutti i tipi di modello
- `maturity_observatory.py` — MaturityObservatory che traccia 5 segnali di maturità e indice di convinzione
- `tensorboard_callback.py` — TensorBoardCallback che registra 9+ segnali scalari, istogrammi parametri/gradienti
- `embedding_projector.py` — EmbeddingProjector con riduzione dimensionale UMAP per visualizzazione belief/concept
- `ema.py` — Exponential Moving Average per rete target JEPA
- `early_stopping.py` — EarlyStopping con soglie di pazienza e delta minimo
- `persistence.py` — Gestione checkpoint con serializzazione stato modello
- `dataset.py` — Implementazioni DemoDataset e DataLoader personalizzati

## Sotto-pacchetti

- `rap_coach/` — Implementazione modello RAP (model.py, memory.py, trainer.py)
- `advanced/` — Stub moduli sperimentali (moduli originali rimossi in G-06)
- `inference/` — GhostEngine per previsione in tempo reale
- `layers/` — Layer personalizzati (SuperpositionLayer, meccanismi di attenzione)

## Utilizzo

```python
from backend.nn.factory import ModelFactory
from backend.nn.training_orchestrator import TrainingOrchestrator

model = ModelFactory.create_model("rap_coach")
orchestrator = TrainingOrchestrator(model, train_loader, val_loader)
orchestrator.train(epochs=50)
```
