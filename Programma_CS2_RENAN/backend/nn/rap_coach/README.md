> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Português](README_PT.md)**

# RAP Coach — 7-Layer Recurrent Architecture

RAP (Recurrent Architecture for Pedagogy) Coach implements a 7-layer neural architecture with LTC-Hopfield memory for tactical coaching.

## Architecture Layers

### Layer 1: Perception
- **perception.py** — `RAPPerception`, `ResNetBlock` — CNN-based perception layer for visual feature extraction from 5-channel tensors (view cone, map context, motion, danger zones, teammate positions)

### Layer 2: Memory
- **memory.py** — `RAPMemory` — LTC (Liquid Time-Constant) neural network with Hopfield associative memory (512 slots). Stores tactical patterns with content-addressable retrieval. Uses `ncps.LTC` + `hflayers.Hopfield`.

### Layer 3: Strategy
- **strategy.py** — `RAPStrategy`, `ContextualAttention` — Decision optimization layer with contextual attention mechanism for tactical planning

### Layer 4: Pedagogy
- **pedagogy.py** — `RAPPedagogy`, `CausalAttributor` — Value estimation and causal attribution for coaching feedback generation

### Layer 5: Communication
- **communication.py** — `RAPCommunication` — Output layer producing coaching recommendations with confidence scores

### Layer 6: Temporal Analysis
- **chronovisor_scanner.py** — `ChronovisorScanner`, `CriticalMoment` — Multi-scale critical moment detection (micro/standard/macro timescales) for momentum-aware coaching

### Layer 7: Role Classification
- **NeuralRoleHead** (in `model.py`) — 5-class role classifier (Entry/Lurk/Support/AWP/IGL) with consensus mechanism

## Supporting Modules

- **model.py** — `RAPCoachModel` — Full RAP Coach orchestration integrating all 7 layers
- **trainer.py** — `RAPTrainer` — Training orchestration with callback support for TensorBoard/Observatory
- **skill_model.py** — `SkillLatentModel`, `SkillAxes` — Player skill axes representation (VAE-style latent space)

## Dependencies
PyTorch, ncps (LTC), hflayers (Hopfield), NumPy.
