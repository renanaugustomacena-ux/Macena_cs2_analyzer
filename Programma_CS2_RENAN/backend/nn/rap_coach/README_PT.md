> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Português](README_PT.md)**

# RAP Coach — Arquitetura Recorrente de 7 Camadas

RAP (Recurrent Architecture for Pedagogy) Coach implementa uma arquitetura neural de 7 camadas com memoria LTC-Hopfield para coaching tatico.

## Camadas da Arquitetura

### Camada 1: Percepcao
- **perception.py** — `RAPPerception`, `ResNetBlock` — Camada de percepcao baseada em CNN para extracao de caracteristicas visuais de tensores de 5 canais (cone de visao, contexto do mapa, movimento, zonas de perigo, posicoes de companheiros)

### Camada 2: Memoria
- **memory.py** — `RAPMemory` — Rede neural LTC (Liquid Time-Constant) com memoria associativa Hopfield (512 slots). Armazena padroes taticos com recuperacao enderecavel por conteudo. Usa `ncps.LTC` + `hflayers.Hopfield`.

### Camada 3: Estrategia
- **strategy.py** — `RAPStrategy`, `ContextualAttention` — Camada de otimizacao de decisao com mecanismo de atencao contextual para planejamento tatico

### Camada 4: Pedagogia
- **pedagogy.py** — `RAPPedagogy`, `CausalAttributor` — Estimativa de valor e atribuicao causal para geracao de feedback de coaching

### Camada 5: Comunicacao
- **communication.py** — `RAPCommunication` — Camada de saida produzindo recomendacoes de coaching com pontuacoes de confianca

### Camada 6: Analise Temporal
- **chronovisor_scanner.py** — `ChronovisorScanner`, `CriticalMoment` — Deteccao de momentos criticos em multiplas escalas (escalas de tempo micro/padrao/macro) para coaching consciente do momentum

### Camada 7: Classificacao de Funcao
- **NeuralRoleHead** (em `model.py`) — Classificador de funcoes de 5 classes (Entry/Lurk/Support/AWP/IGL) com mecanismo de consenso

## Modulos de Suporte

- **model.py** — `RAPCoachModel` — Orquestracao completa do RAP Coach integrando todas as 7 camadas
- **trainer.py** — `RAPTrainer` — Orquestracao de treinamento com suporte a callbacks para TensorBoard/Observatory
- **skill_model.py** — `SkillLatentModel`, `SkillAxes` — Representacao de eixos de habilidade do jogador (espaco latente estilo VAE)

## Dependencias
PyTorch, ncps (LTC), hflayers (Hopfield), NumPy.
