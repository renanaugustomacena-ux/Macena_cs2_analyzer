> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Português](README_PT.md)**

# RAP Coach — Architettura Ricorrente a 7 Livelli

RAP (Recurrent Architecture for Pedagogy) Coach implementa un'architettura neurale a 7 livelli con memoria LTC-Hopfield per coaching tattico.

## Livelli Architettura

### Livello 1: Percezione
- **perception.py** — `RAPPerception`, `ResNetBlock` — Livello percezione basato su CNN per estrazione feature visive da tensori 5 canali (cono vista, contesto mappa, movimento, zone pericolo, posizioni compagni)

### Livello 2: Memoria
- **memory.py** — `RAPMemory` — Rete neurale LTC (Liquid Time-Constant) con memoria associativa Hopfield (512 slot). Memorizza pattern tattici con recupero content-addressable. Usa `ncps.LTC` + `hflayers.Hopfield`.

### Livello 3: Strategia
- **strategy.py** — `RAPStrategy`, `ContextualAttention` — Livello ottimizzazione decisionale con meccanismo attenzione contestuale per pianificazione tattica

### Livello 4: Pedagogia
- **pedagogy.py** — `RAPPedagogy`, `CausalAttributor` — Stima valore e attribuzione causale per generazione feedback coaching

### Livello 5: Comunicazione
- **communication.py** — `RAPCommunication` — Livello output che produce raccomandazioni coaching con punteggi confidenza

### Livello 6: Analisi Temporale
- **chronovisor_scanner.py** — `ChronovisorScanner`, `CriticalMoment` — Rilevamento momenti critici multi-scala (timescale micro/standard/macro) per coaching consapevole del momentum

### Livello 7: Classificazione Ruolo
- **NeuralRoleHead** (in `model.py`) — Classificatore ruoli 5 classi (Entry/Lurk/Support/AWP/IGL) con meccanismo consenso

## Moduli di Supporto

- **model.py** — `RAPCoachModel` — Orchestrazione completa RAP Coach integrando tutti i 7 livelli
- **trainer.py** — `RAPTrainer` — Orchestrazione training con supporto callbacks per TensorBoard/Observatory
- **skill_model.py** — `SkillLatentModel`, `SkillAxes` — Rappresentazione assi abilita giocatore (spazio latente stile VAE)

## Dipendenze
PyTorch, ncps (LTC), hflayers (Hopfield), NumPy.
