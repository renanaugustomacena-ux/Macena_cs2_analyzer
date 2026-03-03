> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Portugues](README_PT.md)**

# Neural Network Subsystem

Complete ML infrastructure with 6 model architectures and integrated training pipeline.

## Model Architectures

### RAP Coach (`rap_coach/`)
7-layer pedagogical architecture:
- **Perception Layer** — ResNet-based feature extraction from tactical situations
- **Memory Layer** — LTC-Hopfield hybrid with 512 associative slots for pattern retention
- **Strategy Layer** — Contextual attention mechanism for tactical decision synthesis
- **Pedagogy Layer** — Causal attribution for explaining tactical mistakes
- **Communication Layer** — Natural language insight generation
- **ChronovisorScanner** — Multi-scale temporal analysis (micro/standard/macro momentum)

### JEPA (`jepa_model.py`)
Self-supervised encoder with EMA target network, InfoNCE contrastive loss, concept dictionary for semantic alignment.

### VL-JEPA (`jepa_model.py`)
Vision-Language extension of JEPA for visual-linguistic tactical understanding.

### LSTM+MoE (`model.py`)
Legacy AdvancedCoachNN with Mixture of Experts routing for multi-domain coaching.

### Neural Role Head (`role_head.py`)
70-dimensional meta-feature input to 4-role soft consensus (Entry Fragger / Lurker / Support / AWPer).

### Win Probability Model (`win_probability.py`)
Round win probability prediction based on economy, positioning, and momentum state.

## Training Infrastructure

- `training_orchestrator.py` — TrainingOrchestrator with callback plugin system
- `coach_manager.py` — CoachTrainingManager with 3-stage maturity gate (doubt/learning/conviction)
- `factory.py` — ModelFactory for unified instantiation across all model types
- `maturity_observatory.py` — MaturityObservatory tracking 5 maturity signals and conviction index
- `tensorboard_callback.py` — TensorBoardCallback logging 9+ scalar signals, parameter/gradient histograms
- `embedding_projector.py` — EmbeddingProjector with UMAP dimensionality reduction for belief/concept visualization
- `ema.py` — Exponential Moving Average for JEPA target network
- `early_stopping.py` — EarlyStopping with patience and min-delta thresholds
- `persistence.py` — Checkpoint management with model state serialization
- `dataset.py` — DemoDataset and custom DataLoader implementations

## Sub-packages

- `rap_coach/` — RAP model implementation (model.py, memory.py, trainer.py)
- `advanced/` — Experimental module stub (original modules removed in G-06)
- `inference/` — GhostEngine for real-time prediction
- `layers/` — Custom layers (SuperpositionLayer, attention mechanisms)

## Usage

```python
from backend.nn.factory import ModelFactory
from backend.nn.training_orchestrator import TrainingOrchestrator

model = ModelFactory.create_model("rap_coach")
orchestrator = TrainingOrchestrator(model, train_loader, val_loader)
orchestrator.train(epochs=50)
```
