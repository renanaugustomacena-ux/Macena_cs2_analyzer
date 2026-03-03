> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Portugues](README_PT.md)**

# Subsistema de Redes Neurais

Infraestrutura ML completa com 6 arquiteturas de modelos e pipeline de treinamento integrado.

## Arquiteturas dos Modelos

### RAP Coach (`rap_coach/`)
Arquitetura pedagógica de 7 camadas:
- **Perception Layer** — Extração de features baseada em ResNet de situações táticas
- **Memory Layer** — Híbrido LTC-Hopfield com 512 slots associativos para retenção de padrões
- **Strategy Layer** — Mecanismo de atenção contextual para síntese de decisões táticas
- **Pedagogy Layer** — Atribuição causal para explicar erros táticos
- **Communication Layer** — Geração de insights em linguagem natural
- **ChronovisorScanner** — Análise temporal multi-escala (momentum micro/padrão/macro)

### JEPA (`jepa_model.py`)
Encoder auto-supervisionado com rede alvo EMA, loss contrastivo InfoNCE, dicionário de conceitos para alinhamento semântico.

### VL-JEPA (`jepa_model.py`)
Extensão Vision-Language do JEPA para compreensão tática visual-linguística.

### LSTM+MoE (`model.py`)
AdvancedCoachNN legado com roteamento Mixture of Experts para coaching multi-domínio.

### Neural Role Head (`role_head.py`)
Entrada de meta-features de 70 dimensões para consenso suave de 4 papéis (Entry Fragger / Lurker / Support / AWPer).

### Win Probability Model (`win_probability.py`)
Previsão de probabilidade de vitória do round baseada em economia, posicionamento e estado do momentum.

## Infraestrutura de Treinamento

- `training_orchestrator.py` — TrainingOrchestrator com sistema de callback plugin
- `coach_manager.py` — CoachTrainingManager com portão de maturidade de 3 estágios (dúvida/aprendizado/convicção)
- `factory.py` — ModelFactory para instanciação unificada de todos os tipos de modelo
- `maturity_observatory.py` — MaturityObservatory rastreando 5 sinais de maturidade e índice de convicção
- `tensorboard_callback.py` — TensorBoardCallback registrando 9+ sinais escalares, histogramas de parâmetros/gradientes
- `embedding_projector.py` — EmbeddingProjector com redução dimensional UMAP para visualização de belief/conceito
- `ema.py` — Exponential Moving Average para rede alvo JEPA
- `early_stopping.py` — EarlyStopping com limiares de paciência e delta mínimo
- `persistence.py` — Gerenciamento de checkpoint com serialização de estado do modelo
- `dataset.py` — Implementações personalizadas de DemoDataset e DataLoader

## Subpacotes

- `rap_coach/` — Implementação do modelo RAP (model.py, memory.py, trainer.py)
- `advanced/` — Stub de modulos experimentais (modulos originais removidos em G-06)
- `inference/` — GhostEngine para previsão em tempo real
- `layers/` — Camadas personalizadas (SuperpositionLayer, mecanismos de atenção)

## Uso

```python
from backend.nn.factory import ModelFactory
from backend.nn.training_orchestrator import TrainingOrchestrator

model = ModelFactory.create_model("rap_coach")
orchestrator = TrainingOrchestrator(model, train_loader, val_loader)
orchestrator.train(epochs=50)
```
