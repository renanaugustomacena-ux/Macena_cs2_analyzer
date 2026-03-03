# Macena CS2 Analyzer

**Coach Tatico com IA para Counter-Strike 2**

> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Portugues](README_PT.md)**

---

## O Que E Isso?

Macena CS2 Analyzer e uma aplicacao desktop que funciona como um coach pessoal de IA para Counter-Strike 2. Ele analisa arquivos demo profissionais e do usuario, treina multiplos modelos de redes neurais e entrega coaching tatico personalizado comparando sua gameplay com padroes profissionais.

O sistema aprende com as melhores partidas profissionais ja jogadas e adapta seu coaching ao seu estilo de jogo individual — seja voce um AWPer, entry fragger, support ou qualquer outro papel. A pipeline de coaching funde previsoes de machine learning com conhecimento tatico recuperado, analise baseada em teoria dos jogos e modelagem bayesiana de crencas para produzir conselhos acionaveis e context-aware.

Diferente de ferramentas de coaching estaticas com dicas pre-escritas, este sistema constroi sua inteligencia a partir de dados reais de gameplay profissional. Na primeira execucao, as redes neurais tem pesos aleatorios e zero conhecimento tatico. Cada demo que voce fornece torna o coach mais inteligente, mais refinado e mais personalizado.

---

## Indice

- [Funcionalidades Principais](#funcionalidades-principais)
- [Requisitos do Sistema](#requisitos-do-sistema)
- [Inicio Rapido](#inicio-rapido)
- [Panorama Arquitetural](#panorama-arquitetural)
- [Mapas Suportados](#mapas-suportados)
- [Stack Tecnologico](#stack-tecnologico)
- [Estrutura do Projeto](#estrutura-do-projeto)
- [Pontos de Entrada](#pontos-de-entrada)
- [Validacao e Qualidade](#validacao-e-qualidade)
- [Suporte Multi-Idioma](#suporte-multi-idioma)
- [Recursos de Seguranca](#recursos-de-seguranca)
- [Maturidade do Sistema](#maturidade-do-sistema)
- [Documentacao](#documentacao)
- [Alimentando o Coach](#alimentando-o-coach)
- [Solucao de Problemas](#solucao-de-problemas)
- [Licenca](#licenca)
- [Autor](#autor)

---

## Funcionalidades Principais

### Pipeline de Coaching IA

- **Cadeia de Fallback de 4 Niveis** — COPER > Hibrido > RAG > Base, garantindo que o sistema sempre produza conselhos uteis independente da maturidade do modelo
- **Banco de Experiencias COPER** — Armazena e recupera experiencias de coaching passadas ponderadas por recencia, eficacia e similaridade de contexto
- **Base de Conhecimento RAG** — Retrieval-Augmented Generation com padroes de referencia profissionais e conhecimento tatico
- **Integracao Ollama** — LLM local opcional para refinamento em linguagem natural dos insights de coaching
- **Atribuicao Causal** — Cada recomendacao de coaching inclui uma explicacao "por que" rastreavel a decisoes especificas de gameplay

### Subsistemas de Redes Neurais

- **RAP Coach** — Arquitetura de 7 camadas que combina percepcao, memoria (LTC-Hopfield), estrategia (Mixture-of-Experts com superposicao), pedagogia (value function), predicao de posicao, atribuicao causal e agregacao de output
- **Encoder JEPA** — Joint-Embedding Predictive Architecture para pre-treinamento auto-supervisionado com loss contrastiva InfoNCE e target encoder EMA
- **VL-JEPA** — Extensao Vision-Language com alinhamento de 16 conceitos taticos (posicionamento, utility, economia, engajamento, decisao, psicologia)
- **AdvancedCoachNN** — Arquitetura LSTM + Mixture-of-Experts para predicao dos pesos de coaching
- **Neural Role Head** — Classificador MLP de 5 funcoes (entry, support, lurk, AWP, anchor) com KL-divergence e consensus gating
- **Modelos Bayesianos de Crenca** — Rastreamento do estado mental do adversario com calibracao adaptativa a partir dos dados da partida

### Analise de Demos

- **Parsing a Nivel de Tick** — Cada tick dos arquivos `.dem` e analisado via demoparser2, preservando todo o estado do jogo (nenhuma decimacao de tick)
- **Rating HLTV 2.0** — Calculado por partida usando a formula oficial HLTV 2.0 (abates, mortes, ADR, KAST%, sobrevivencia, assist flash)
- **Detalhamento Round por Round** — Timeline da economia, analise de engajamentos, uso de utilitarios, rastreamento de momentum
- **Decaimento Temporal da Baseline** — Rastreia a evolucao das habilidades do jogador ao longo do tempo com pesos de decaimento exponencial

### Analise baseada em Teoria dos Jogos

- **Arvores Expectiminimax** — Avaliacao decisional game-theoretic para cenarios estrategicos
- **Probabilidade de Morte Bayesiana** — Estima a probabilidade de sobrevivencia baseada em posicao, equipamento e estado do inimigo
- **Indice de Engano** — Quantifica a imprevisibilidade posicional em relacao as baselines profissionais
- **Analise do Raio de Engajamento** — Mapeia a selecao de armas contra as distribuicoes de distancia de engajamento
- **Probabilidade de Vitoria** — Calculo da probabilidade de vitoria em tempo real
- **Rastreamento de Momentum** — Trajetoria de confianca e desempenho round por round

### Aplicacao Desktop

- **Interface Kivy + KivyMD** — App desktop cross-platform com arquitetura MVVM
- **Visualizador Tatico 2D** — Replay de demo em tempo real com posicoes dos jogadores, eventos de abate, indicadores de bomba e predicoes AI ghost
- **Historico de Partidas** — Lista rolavel das partidas recentes com ratings codificados por cor
- **Dashboard de Performance** — Tendencias de rating, estatisticas por mapa, analise de pontos fortes/fracos, detalhamento de utilitarios
- **Chat com o Coach** — Conversa AI interativa com botoes de acao rapida e perguntas em texto livre
- **Perfil do Jogador** — Integracao Steam com importacao automatica de partidas
- **3 Temas Visuais** — CS2 (laranja), CS:GO (azul-cinza), CS 1.6 (verde) com wallpapers rotativos

### Treinamento e Automacao

- **Session Engine de 4 Daemons** — Scanner (descoberta de arquivos), Digester (processamento de demos), Teacher (treinamento de modelos), Pulse (monitoramento de saude)
- **Gating de Maturidade em 3 Estagios** — CALIBRATING (0-49 demos, 0.5x confianca) > LEARNING (50-199, 0.8x) > MATURE (200+, total)
- **Conviction Index** — Composto de 5 sinais que rastreia entropia de crencas, especializacao de gates, foco conceitual, precisao de valor e estabilidade de funcao
- **Auto-Retreinamento** — O treinamento e acionado automaticamente com 10% de crescimento na contagem de demos
- **Deteccao de Drift** — Monitoramento de drift de features baseado em Z-score com flag automatico de retreinamento
- **Observatorio de Introspeccao do Coach** — Integracao TensorBoard com maquina de estados de maturidade, projetor de embeddings e rastreamento de conviccao

---

## Requisitos do Sistema

| Componente | Minimo | Recomendado |
|------------|--------|-------------|
| OS | Windows 10 / Ubuntu 22.04 | Windows 10/11 |
| Python | 3.10 | 3.10 ou 3.12 |
| RAM | 8 GB | 16 GB |
| GPU | Nenhuma (modo CPU) | NVIDIA GTX 1650+ (CUDA 12.1) |
| Disco | 3 GB livres | 5 GB livres |
| Display | 1280x720 | 1920x1080 |

---

## Inicio Rapido

### 1. Clone

```bash
git clone https://github.com/renanaugustomacena-ux/Counter-Strike-coach-AI.git
cd Counter-Strike-coach-AI
```

### 2. Setup Automatizado (Windows)

```powershell
.\scripts\Setup_Macena_CS2.ps1
```

Cria um ambiente virtual, instala todas as dependencias, inicializa o banco de dados e configura o Playwright para scraping HLTV.

**Para suporte a GPU NVIDIA**, apos o script completar:

```powershell
.\venv_win\Scripts\pip.exe install --force-reinstall torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### 3. Setup Manual (Windows)

```powershell
python -m venv venv_win
.\venv_win\Scripts\activate

# PyTorch (escolha UM):
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu       # Apenas CPU
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121     # GPU NVIDIA

pip install -r Programma_CS2_RENAN/requirements.txt
python -c "import sys; sys.path.append('.'); from Programma_CS2_RENAN.backend.storage.database import init_database; init_database()"
pip install playwright && python -m playwright install chromium
```

### 4. Setup Manual (Linux)

```bash
sudo apt update
sudo apt install -y python3.10 python3.10-venv python3.10-dev libsdl2-dev libglew-dev build-essential

python3.10 -m venv venv_linux
source venv_linux/bin/activate

# PyTorch (escolha UM):
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu       # Apenas CPU
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121     # GPU NVIDIA

pip install -r Programma_CS2_RENAN/requirements.txt
pip install Kivy==2.3.0 KivyMD==1.2.0
python -c "import sys; sys.path.append('.'); from Programma_CS2_RENAN.backend.storage.database import init_database; init_database()"
pip install playwright && python -m playwright install chromium
```

### 5. Verificar Instalacao

```bash
python -c "import torch; print(f'PyTorch: {torch.__version__}')"
python -c "import kivy; print(f'Kivy: {kivy.__version__}')"
python -c "from Programma_CS2_RENAN.backend.nn.config import get_device; print(f'Device: {get_device()}')"
```

### 6. Executar

```bash
# Aplicacao desktop (GUI Kivy)
python Programma_CS2_RENAN/main.py

# Console interativo (TUI live com paineis em tempo real)
python console.py

# CLI one-shot (build, test, audit, hospital, sanitize)
python goliath.py
```

> Para o guia completo com configuracao de API, walkthroughs das funcionalidades e troubleshooting, consulte o [Guia do Usuario](docs/USER_GUIDE_PT.md).

---

## Panorama Arquitetural

### Pipeline OBSERVA > APRENDE > PENSA > FALA

O sistema e organizado como uma pipeline de 4 estagios que transforma arquivos demo brutos em coaching personalizado:

```
OBSERVA (Ingestao)     APRENDE (Treinamento)   PENSA (Inferencia)      FALA (Dialogo)
  Daemon Scanner         Daemon Teacher          Pipeline COPER          Template + Ollama
  Parsing de demo        Maturidade em 3 est.    Conhecimento RAG        Atribuicao causal
  Extracao de features   Treinamento multi-mod.  Teoria dos jogos        Comparacoes com pros
  Armazenamento de tick  Deteccao de drift       Modelagem de crencas    Scoring de gravidade
```

**OBSERVA** — O daemon Scanner monitora continuamente as pastas de demo configuradas em busca de novos arquivos `.dem`. Quando encontrados, o daemon Digester analisa cada tick usando demoparser2, extrai o vetor canonico de features de 25 dimensoes, calcula os ratings HLTV 2.0 e armazena tudo em bancos de dados SQLite por partida.

**APRENDE** — O daemon Teacher treina automaticamente os modelos neurais quando dados suficientes se acumulam. O treinamento progride atraves de 3 estagios de maturidade (CALIBRATING > LEARNING > MATURE). Multiplas arquiteturas treinam em paralelo: JEPA para aprendizado auto-supervisionado de representacoes, RAP Coach para modelagem de decisoes taticas, NeuralRoleHead para classificacao de funcao dos jogadores.

**PENSA** — No tempo de inferencia, a pipeline COPER combina previsoes neurais com experiencias de coaching recuperadas, conhecimento RAG e analise de teoria dos jogos. Uma cadeia de fallback de 4 niveis (COPER > Hibrido > RAG > Base) garante que conselhos estejam sempre disponiveis independente da maturidade do modelo.

**FALA** — O output final de coaching e formatado com niveis de gravidade, atribuicao causal ("por que este conselho") e opcionalmente refinado atraves de um LLM local Ollama para qualidade de linguagem natural.

### Session Engine de 4 Daemons

| Daemon | Funcao | Trigger |
|--------|--------|---------|
| **Scanner (Hunter)** | Descobre novos arquivos `.dem` nas pastas configuradas | Scan periodico ou file watcher |
| **Digester** | Analisa demos, extrai features, calcula ratings | Novo arquivo detectado pelo Scanner |
| **Teacher** | Treina os modelos neurais com os dados acumulados | Limiar de crescimento de 10% na contagem de demos |
| **Pulse** | Monitoramento de saude, deteccao de drift, status do sistema | Continuo em background |

### Pipeline de Coaching COPER

COPER (Coaching via Organized Pattern Experience Retrieval) e o motor de coaching principal. Opera uma cadeia de fallback de 4 niveis:

1. **Modo COPER** — Pipeline completa: recuperacao do Experience Bank + conhecimento RAG + previsoes do modelo neural + comparacoes profissionais. Requer modelos treinados.
2. **Modo Hibrido** — Combina previsoes neurais com conselhos baseados em templates quando alguns modelos ainda estao em calibracao.
3. **Modo RAG** — Recuperacao pura: busca padroes de coaching relevantes na knowledge base sem inferencia neural. Funciona apenas com demos ingeridas.
4. **Modo Base** — Conselhos baseados em templates a partir de analise estatistica (desvios media/std das baselines profissionais). Funciona imediatamente.

### Arquiteturas de Redes Neurais

**RAP Coach (Arquitetura de 7 Camadas)**

O RAP (Reasoning, Attribution, Prediction) Coach e o modelo neural principal. Suas 7 camadas processam os dados de gameplay atraves de uma pipeline cognitiva:

| Camada | Funcao | Detalhes |
|--------|--------|----------|
| 1. Percepcao | Codificacao visual + espacial | Camadas conv para view frame (64d), estado do mapa (32d), diff de movimento (32d) → 128d |
| 2. Memoria | Rastreamento recorrente de crencas | LSTM + rede Hopfield para memoria associativa. Input: 153d (128 percepcao + 25 metadados) → 256d estado oculto |
| 3. Estrategia | Otimizacao decisional | Mixture-of-Experts com superposicao para decisoes context-dependent. 10 pesos de acao |
| 4. Pedagogia | Estimativa de valor | Avaliacao V-function com integracao de skill vector |
| 5. Posicao | Posicionamento otimo | Prediz (dx, dy, dz) delta para a posicao otima (escala: 500 unidades mundo) |
| 6. Atribuicao | Diagnostico causal | Atribuicao de 5 dimensoes que explica os drivers das decisoes |
| 7. Output | Agregacao | advice_probs, belief_state, value_estimate, gate_weights, optimal_pos, attribution |

**JEPA (Joint-Embedding Predictive Architecture)**

Pre-treinamento auto-supervisionado com:
- Context encoder + predictor → prediz embedding target
- Target encoder atualizado via EMA (momentum 0.996)
- Loss contrastiva InfoNCE com negativos in-batch
- Dimensao latente: 128

**VL-JEPA (Extensao Vision-Language)**

Estende o JEPA com alinhamento de 16 conceitos taticos:
- Conceitos: posicionamento (3), utility (2), economia (2), engajamento (4), decisao (2), psicologia (3)
- Loss de alinhamento conceitual + regularizacao de diversidade
- Etiquetagem baseada em outcome dos RoundStats (abates, mortes, equipamento, resultado do round)

**Outros Modelos:**
- **AdvancedCoachNN** — LSTM (hidden=128) + Mixture-of-Experts (4 especialistas, top-k=2) para predicao dos pesos de coaching
- **NeuralRoleHead** — Classificador MLP de 5 funcoes com KL-divergence gating e consensus voting
- **RoleClassifier** — Deteccao leve de funcoes a partir das features dos ticks

### Vetor de Features de 25 Dimensoes

Cada tick de jogo e representado como um vetor canonico de 25 dimensoes (`METADATA_DIM=25`):

| Indice | Feature | Range | Descricao |
|--------|---------|-------|-----------|
| 0 | health | [0, 1] | HP / 100 |
| 1 | armor | [0, 1] | Armadura / 100 |
| 2 | has_helmet | {0, 1} | Capacete equipado |
| 3 | has_defuser | {0, 1} | Kit de desarme |
| 4 | equipment_value | [0, 1] | Custo do equipamento normalizado |
| 5 | is_crouching | {0, 1} | Posicao agachada |
| 6 | is_scoped | {0, 1} | Arma com scope ativa |
| 7 | is_blinded | {0, 1} | Efeito de flash |
| 8 | enemies_visible | [0, 1] | Contagem de inimigos visiveis (normalizada) |
| 9-11 | pos_x, pos_y, pos_z | [-1, 1] | Coordenadas mundo (normalizadas por mapa) |
| 12-13 | view_yaw_sin, view_yaw_cos | [-1, 1] | Angulo de visao (codificacao ciclica) |
| 14 | view_pitch | [-1, 1] | Angulo de visao vertical |
| 15 | z_penalty | [0, 1] | Distintividade vertical (mapas multi-nivel) |
| 16 | kast_estimate | [0, 1] | Razao Kill/Assist/Survive/Trade |
| 17 | map_id | [0, 1] | Hash deterministico do mapa (baseado em MD5) |
| 18 | round_phase | {0, .33, .66, 1} | Pistol / Eco / Force / Full buy |
| 19 | weapon_class | [0, 1] | Faca=0, Pistola=.2, SMG=.4, Rifle=.6, Sniper=.8, Pesada=1 |
| 20 | time_in_round | [0, 1] | Segundos / 115 |
| 21 | bomb_planted | {0, 1} | Flag bomba plantada |
| 22 | teammates_alive | [0, 1] | Contagem / 4 |
| 23 | enemies_alive | [0, 1] | Contagem / 5 |
| 24 | team_economy | [0, 1] | Dinheiro medio do time / 16000 |

### Gating de Maturidade em 3 Estagios

Os modelos progridem atraves de gates de maturidade baseados na contagem de demos ingeridas:

| Estagio | Contagem de Demos | Confianca | Comportamento |
|---------|-------------------|-----------|---------------|
| **CALIBRATING** | 0-49 | 0.5x | Coaching basico, conselhos marcados como provisorios |
| **LEARNING** | 50-199 | 0.8x | Intermediario, confiabilidade crescente |
| **MATURE** | 200+ | 1.0x | Confianca total, todos os subsistemas contribuem |

Um **Conviction Index** paralelo (0.0-1.0) rastreia 5 sinais neurais: entropia de crencas, especializacao de gates, foco conceitual, precisao de valor e estabilidade de funcao. Estados: DOUBT (<0.30) > LEARNING (0.30-0.60) > CONVICTION (>0.60 estavel por 10+ epocas) > MATURE (>0.75 estavel por 20+ epocas). Uma queda brusca >20% ativa o estado CRISIS.

---

## Mapas Suportados

O sistema suporta todos os 9 mapas competitivos Active Duty com mapeamento de coordenadas com precisao de pixel:

| Mapa | Tipo | Calibracao |
|------|------|------------|
| de_mirage | Nivel unico | pos (-3230, 1713), escala 5.0 |
| de_inferno | Nivel unico | pos (-2087, 3870), escala 4.9 |
| de_dust2 | Nivel unico | pos (-2476, 3239), escala 4.4 |
| de_overpass | Nivel unico | pos (-4831, 1781), escala 5.2 |
| de_ancient | Nivel unico | pos (-2953, 2164), escala 5.0 |
| de_anubis | Nivel unico | pos (-2796, 3328), escala 5.22 |
| de_train | Nivel unico | pos (-2477, 2392), escala 4.7 |
| de_nuke | **Multi-nivel** | pos (-3453, 2887), escala 7.0, Z-cutoff -495 |
| de_vertigo | **Multi-nivel** | pos (-3168, 1762), escala 4.0, Z-cutoff 11700 |

Os mapas multi-nivel (Nuke, Vertigo) usam cutoff no eixo Z para separar nivel superior e inferior para uma renderizacao 2D precisa. A feature z_penalty (indice 15) no vetor de features captura a distintividade vertical para estes mapas.

---

## Stack Tecnologico

### Dependencias Principais

| Categoria | Pacote | Versao | Proposito |
|-----------|--------|--------|-----------|
| **ML Framework** | PyTorch | Latest | Treinamento e inferencia de redes neurais |
| **Redes Recorrentes** | ncps | Latest | Redes Liquid Time-Constant (LTC) |
| **Memoria Associativa** | hopfield-layers | Latest | Camadas de rede Hopfield para memoria |
| **Parsing de Demo** | demoparser2 | 0.40.2 | Parsing a nivel de tick dos arquivos demo CS2 |
| **Utilitarios CS2** | awpy | 1.2.3 | Utilitarios de analise CS2 |
| **Framework UI** | Kivy | 2.3.0 | GUI desktop cross-platform |
| **Componentes UI** | KivyMD | 1.2.0 | Widgets Material Design |
| **ORM Database** | SQLAlchemy + SQLModel | Latest | Modelos e queries de banco de dados |
| **Migracoes** | Alembic | Latest | Migracoes de schema de banco de dados |
| **Web Scraping** | Playwright | 1.57.0 | Navegador headless para HLTV |
| **Cliente HTTP** | HTTPX | 0.28.1 | Requisicoes HTTP async |
| **Data Science** | NumPy, Pandas, SciPy, scikit-learn | Latest | Computacao numerica e analise |
| **Visualizacao** | Matplotlib | Latest | Geracao de graficos |
| **Geometria** | Shapely | 2.1.2 | Analise espacial |
| **Grafos** | NetworkX | Latest | Analise baseada em grafos |
| **Seguranca** | cryptography | 46.0.3 | Criptografia de credenciais |
| **TUI** | Rich | 14.2.0 | UI de terminal para modo console |
| **API** | FastAPI + Uvicorn | 0.40.0 | Servidor de API interno |
| **Validacao** | Pydantic | Latest | Validacao de dados e configuracoes |
| **Testes** | pytest + pytest-cov + pytest-mock | 9.0.2 | Framework de testes e cobertura |
| **Packaging** | PyInstaller | 6.17.0 | Distribuicao binaria |
| **Templating** | Jinja2 | 3.1.6 | Renderizacao de templates para relatorios |
| **Parsing HTML** | BeautifulSoup4 + lxml | 4.12.3 | Extracao de conteudo web |
| **Config** | PyYAML | 6.0.3 | Arquivos de configuracao YAML |
| **Imagens** | Pillow | 12.0.0 | Processamento de imagens |
| **Keyring** | keyring | 25.6.0 | Armazenamento seguro de credenciais |

### Dependencias Apenas Windows

| Pacote | Versao | Proposito |
|--------|--------|-----------|
| kivy-deps.glew | 0.3.1 | OpenGL extension wrangler |
| kivy-deps.sdl2 | 0.7.0 | Biblioteca multimidia SDL2 |
| kivy-deps.angle | 0.4.0 | Backend ANGLE OpenGL ES |

---

## Estrutura do Projeto

```
Counter-Strike-coach-AI/
|
+-- Programma_CS2_RENAN/                Pacote principal da aplicacao
|   +-- apps/desktop_app/               GUI Kivy (padrao MVVM)
|   |   +-- main.py                     Ponto de entrada da app
|   |   +-- layout.kv                   Definicao de layout Kivy
|   |   +-- viewmodels/                 Camada ViewModel (playback, ghost, chronovisor)
|   |   +-- screens/                    Telas UI (tactical viewer, match history, performance,
|   |   |                               match detail, wizard, help, coach, settings, profile)
|   |   +-- widgets/                    Componentes UI reutilizaveis (tactical map, player sidebar,
|   |   |                               timeline scrubber, ghost pixel renderer)
|   |   +-- assets/                     Temas (CS2, CSGO, CS1.6), fontes, imagens de radar dos mapas
|   |   +-- i18n/                       Traducoes (EN, IT, PT)
|   |
|   +-- backend/
|   |   +-- analysis/                   Teoria dos jogos e analise estatistica
|   |   |   +-- belief_model.py         Rastreamento bayesiano do estado mental do adversario
|   |   |   +-- game_tree.py            Arvores decisionais expectiminimax
|   |   |   +-- momentum.py             Momentum dos rounds e tendencias de confianca
|   |   |   +-- role_classifier.py      Deteccao de funcao do jogador (entry, support, lurk, AWP, anchor)
|   |   |   +-- blind_spots.py          Consciencia do mapa e fraquezas posicionais
|   |   |   +-- deception_index.py      Metrica de imprevisibilidade posicional
|   |   |   +-- entropy_analysis.py     Quantificacao da aleatoriedade decisional
|   |   |   +-- engagement_range.py     Analise de distribuicao arma-distancia
|   |   |   +-- utility_economy.py      Eficiencia de gasto de granadas
|   |   |   +-- win_probability.py      Calculo de probabilidade de vitoria em tempo real
|   |   |
|   |   +-- data_sources/              Integracao de dados externos
|   |   |   +-- demo_parser.py          Wrapper demoparser2 (extracao a nivel de tick)
|   |   |   +-- hltv_api_service.py     Scraping de metadados profissionais HLTV
|   |   |   +-- steam_api_service.py    Perfil Steam e dados de partidas
|   |   |   +-- faceit_api_service.py   Integracao de dados de partidas FaceIT
|   |   |
|   |   +-- nn/                         Subsistemas de redes neurais
|   |   |   +-- config.py               Configuracao global NN (dimensoes, lr, batch size, device)
|   |   |   +-- jepa_model.py           Encoder JEPA + VL-JEPA + ConceptLabeler
|   |   |   +-- jepa_trainer.py         Loop de treinamento JEPA com monitoramento de drift
|   |   |   +-- training_orchestrator.py Orquestracao de treinamento multi-modelo
|   |   |   +-- rap_coach/              Modelo RAP Coach
|   |   |   |   +-- model.py            Arquitetura de 7 camadas (Percepcao-Memoria-Estrategia-
|   |   |   |   |                       Pedagogia-Posicao-Atribuicao-Output)
|   |   |   |   +-- trainer.py          Loop de treinamento especifico do RAP
|   |   |   |   +-- memory.py           Modulo de memoria LTC + Hopfield
|   |   |   +-- layers/                 Componentes neurais compartilhados
|   |   |       +-- superposition.py    Camada de superposicao context-dependent
|   |   |       +-- moe.py             Gating Mixture-of-Experts
|   |   |
|   |   +-- processing/                Feature engineering e processamento de dados
|   |   |   +-- feature_engineering/
|   |   |   |   +-- vectorizer.py       Extracao de features canonicas de 25-dim (METADATA_DIM=25)
|   |   |   |   +-- tensor_factory.py   Construcao de tensores view/map para RAP Coach
|   |   |   +-- heatmap/               Geracao de heatmaps espaciais
|   |   |   +-- validation/            Deteccao de drift, verificacoes de qualidade de dados
|   |   |
|   |   +-- knowledge/                 Gestao do conhecimento
|   |   |   +-- rag_knowledge.py        Recuperacao RAG para padroes de coaching
|   |   |   +-- experience_bank.py      Armazenamento e recuperacao de experiencias COPER
|   |   |   +-- round_utils.py          Utilitario de deteccao de fase do round
|   |   |
|   |   +-- services/                  Servicos da aplicacao
|   |   |   +-- coaching_service.py     Pipeline de coaching de 4 niveis (COPER/Hibrido/RAG/Base)
|   |   |   +-- ollama_service.py       Integracao LLM local para refinamento de linguagem
|   |   |
|   |   +-- storage/                   Camada de banco de dados
|   |       +-- database.py            Gestao de conexoes SQLite WAL-mode
|   |       +-- models.py              Definicoes ORM SQLAlchemy/SQLModel
|   |       +-- backup.py              Backup automatizado de banco de dados
|   |       +-- match_data_manager.py  Gestao de banco de dados SQLite por partida
|   |
|   +-- core/                          Servicos core da aplicacao
|   |   +-- session_engine.py           Engine de 4 daemons (Scanner, Digester, Teacher, Pulse)
|   |   +-- map_manager.py             Carregamento de mapas, calibracao de coordenadas, Z-cutoff
|   |   +-- asset_manager.py           Resolucao de temas e assets
|   |   +-- spatial_data.py            Sistemas de coordenadas espaciais
|   |
|   +-- ingestion/                     Pipeline de ingestao de demos
|   |   +-- steam_locator.py           Auto-descoberta dos caminhos de demo do Steam CS2
|   |   +-- integrity_check.py         Validacao de arquivos demo
|   |
|   +-- observability/                 Monitoramento e seguranca
|   |   +-- rasp.py                    Runtime Application Self-Protection
|   |   +-- telemetry.py              Metricas TensorBoard e rastreamento de conviccao
|   |   +-- logger_setup.py           Logging estruturado (namespace cs2analyzer.*)
|   |
|   +-- reporting/                     Geracao de output
|   |   +-- visualizer.py             Renderizacao de graficos e diagramas
|   |   +-- pdf_generator.py          Geracao de relatorios PDF
|   |
|   +-- tests/                         Suite de testes (390+ testes)
|   +-- data/                          Dados estaticos (seed knowledge base, datasets externos)
|
+-- docs/                              Documentacao
|   +-- USER_GUIDE.md                  Guia do usuario completo (EN)
|   +-- USER_GUIDE_IT.md               Guia do usuario (Italiano)
|   +-- USER_GUIDE_PT.md               Guia do usuario (Portugues)
|   +-- AI-cs2-coach-part1.md          Documentacao da arquitetura (Parte 1)
|   +-- AI-cs2-coach-part2.md          Documentacao da arquitetura (Parte 2)
|   +-- AI-cs2-coach-part3.md          Documentacao da arquitetura (Parte 3)
|   +-- cybersecurity.md               Analise de seguranca
|   +-- Studies/                        17 papers de pesquisa sobre:
|       +-- Studio_01                   Fundamentos Epistemicos
|       +-- Studio_02                   Algebra da Ingestao
|       +-- Studio_03                   Redes Recorrentes
|       +-- Studio_04                   Aprendizado por Reforco
|       +-- Studio_05                   Arquitetura Perceptiva
|       +-- Studio_06                   Arquitetura Cognitiva
|       +-- Studio_07                   Arquitetura JEPA
|       +-- Studio_08                   Engenharia Forense
|       +-- Studio_09                   Feature Engineering
|       +-- Studio_10                   Database e Storage
|       +-- Studio_11                   Motor Tri-Daemon
|       +-- Studio_12                   Avaliacao e Falsificacao
|       +-- Studio_13                   Explicabilidade e Interface de Coaching
|       +-- Studio_14                   Etica, Privacidade e Integridade
|       +-- Studio_15                   Otimizacao de Hardware e Scaling
|       +-- Studio_16                   Mapas e GNN
|       +-- Studio_17                   Impacto Sociotecnico e Futuro
|
+-- tools/                             Ferramentas de validacao e diagnostico
|   +-- headless_validator.py          Gate de regressao primario (245+ checks)
|   +-- Feature_Audit.py              Auditoria de feature engineering
|   +-- portability_test.py           Verificacao de portabilidade cross-platform
|   +-- dead_code_detector.py         Deteccao de codigo nao utilizado
|   +-- dev_health.py                 Saude do ambiente de desenvolvimento
|   +-- verify_all_safe.py            Verificacao de seguranca
|   +-- db_health_diagnostic.py       Diagnostico de saude do banco de dados
|   +-- generate_manifest.py          Gerador de manifesto de integridade
|   +-- Sanitize_Project.py           Preparacao para distribuicao
|   +-- build_pipeline.py             Orquestracao da pipeline de build
|
+-- tests/                            Testes de integracao e verificacao
|   +-- forensics/                    Utilitarios de debug e forenses
|
+-- scripts/                          Scripts de setup e deployment
|   +-- Setup_Macena_CS2.ps1          Setup automatizado Windows
|
+-- alembic/                          Scripts de migracao de banco de dados
+-- console.py                        Ponto de entrada da TUI interativa
+-- goliath.py                        Orquestrador CLI de producao
+-- run_full_training_cycle.py        Runner standalone de ciclo de treinamento
```

---

## Pontos de Entrada

A aplicacao fornece 4 pontos de entrada para diferentes casos de uso:

### Aplicacao Desktop (GUI)

```bash
python Programma_CS2_RENAN/main.py
```

Interface grafica completa com visualizador tatico, historico de partidas, dashboard de performance, chat com o coach e configuracoes. Abre em 1280x720. Na primeira execucao, um assistente de 3 passos configura o diretorio Brain Data Root.

### Console Interativo (TUI)

```bash
python console.py
```

UI de terminal com paineis em tempo real para desenvolvimento e controle de runtime. Comandos organizados por subsistema:

| Grupo de Comandos | Exemplos |
|-------------------|----------|
| **Pipeline ML** | `ml start`, `ml stop`, `ml pause`, `ml resume`, `ml throttle 0.5`, `ml status` |
| **Ingestao** | `ingest start`, `ingest stop`, `ingest mode continuous 5`, `ingest scan` |
| **Build & Test** | `build run`, `build verify`, `test all`, `test headless`, `test hospital` |
| **Sistema** | `sys status`, `sys audit`, `sys baseline`, `sys db`, `sys vacuum`, `sys resources` |
| **Config** | `set steam /path`, `set faceit KEY`, `set config key value` |
| **Servicos** | `svc restart coaching` |

### CLI de Producao (Goliath)

```bash
python goliath.py <comando>
```

Orquestrador master para builds de producao, release e diagnostico:

| Comando | Descricao | Flags |
|---------|-----------|-------|
| `build` | Pipeline de build industrial | `--test-only` |
| `sanitize` | Limpar o projeto para distribuicao | `--force` |
| `integrity` | Gerar manifesto de integridade | |
| `audit` | Verificar dados e features | `--demo <path>` |
| `db` | Gestao de schema do banco de dados | `--force` |
| `doctor` | Diagnostico clinico | `--department <name>` |
| `baseline` | Status de decaimento da baseline temporal | |

### Runner de Ciclo de Treinamento

```bash
python run_full_training_cycle.py
```

Script standalone que executa um ciclo de treinamento completo fora do daemon engine. Util para treinamento manual ou debugging.

---

## Validacao e Qualidade

O projeto mantem uma hierarquia de validacao em multiplos niveis:

| Ferramenta | Escopo | Comando | Checks |
|------------|--------|---------|--------|
| Headless Validator | Gate de regressao primario | `python tools/headless_validator.py` | 245+ checks |
| Suite Pytest | Testes logicos e integracao | `python -m pytest Programma_CS2_RENAN/tests/ -x -q` | 390+ testes |
| Feature Audit | Integridade de feature engineering | `python tools/Feature_Audit.py` | Dimensoes do vetor, ranges |
| Portability Test | Compatibilidade cross-platform | `python tools/portability_test.py` | Checks de importacao, caminhos |
| Dev Health | Ambiente de desenvolvimento | `python tools/dev_health.py` | Dependencias, config |
| Dead Code Detector | Scan de codigo nao utilizado | `python tools/dead_code_detector.py` | Analise de importacoes |
| Safety Verifier | Checks de seguranca | `python tools/verify_all_safe.py` | RASP, scan de secrets |
| DB Health | Diagnostico de banco de dados | `python tools/db_health_diagnostic.py` | Schema, modo WAL, integridade |
| Goliath Hospital | Diagnostico completo | `python goliath.py doctor` | Saude completa do sistema |

**Gate CI/CD:** O headless validator deve retornar exit code 0 antes que qualquer commit seja considerado valido. Os pre-commit hooks aplicam padroes de qualidade de codigo.

---

## Suporte Multi-Idioma

A aplicacao suporta 3 idiomas em toda a interface do usuario:

| Idioma | UI | Guia do Usuario | README |
|--------|----|-----------------|--------|
| English | Completa | [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | [README.md](README.md) |
| Italiano | Completa | [docs/USER_GUIDE_IT.md](docs/USER_GUIDE_IT.md) | [README_IT.md](README_IT.md) |
| Portugues | Completa | [docs/USER_GUIDE_PT.md](docs/USER_GUIDE_PT.md) | [README_PT.md](README_PT.md) |

O idioma pode ser alterado em runtime a partir das Configuracoes sem reiniciar a aplicacao.

---

## Recursos de Seguranca

### Runtime Application Self-Protection (RASP)

- **Manifesto de Integridade** — Hashes SHA-256 de todos os arquivos fonte criticos, verificados na inicializacao
- **Deteccao de Adulteracao** — Avisa quando arquivos fonte foram modificados desde a ultima geracao do manifesto
- **Validacao de Binarios Congelados** — Verifica a estrutura do bundle PyInstaller e o ambiente de execucao
- **Deteccao de Localizacao Suspeita** — Avisa quando executado a partir de caminhos inesperados do filesystem

### Seguranca de Credenciais

- **Integracao OS Keyring** — API keys (Steam, FaceIT) armazenadas no Windows Credential Manager / keyring Linux, nunca em texto simples
- **Nenhum Secret Hardcoded** — O arquivo de configuracoes mostra o placeholder `"PROTECTED_BY_WINDOWS_VAULT"`
- **Operacoes Criptograficas** — Usa `cryptography==46.0.3` (biblioteca verificada, nenhuma crypto personalizada)

### Seguranca de Banco de Dados

- **SQLite WAL Mode** — Write-Ahead Logging para acesso concorrente seguro em todos os bancos de dados
- **Validacao de Input** — Modelos Pydantic na fronteira de ingestao, queries SQL parametrizadas
- **Sistema de Backup** — Backups automatizados do banco de dados com verificacao de integridade

### Logging Estruturado

- Todo o logging atraves do namespace `get_logger("cs2analyzer.<modulo>")`
- Nenhum PII no output de logs
- Formato estruturado para integracao de observabilidade

---

## Maturidade do Sistema

Nem todos os subsistemas sao igualmente maduros. O modo de coaching padrao (COPER) e production-ready e **nao** depende dos modelos neurais. O coaching neural melhora conforme mais demos sao processadas.

| Subsistema | Status | Pontuacao | Notas |
|------------|--------|-----------|-------|
| Coaching COPER | OPERACIONAL | 8/10 | Experience bank + RAG + referencias pro. Funciona imediatamente. |
| Motor Analitico | OPERACIONAL | 6/10 | Rating HLTV 2.0, breakdown por round, timeline de economia. |
| JEPA Base (InfoNCE) | OPERACIONAL | 7/10 | Pre-treinamento auto-supervisionado, target encoder EMA. |
| Neural Role Head | OPERACIONAL | 7/10 | MLP de 5 funcoes com KL-divergence, consensus gating. |
| RAP Coach (7 camadas) | LIMITADO | 3/10 | Arquitetura completa (LTC+Hopfield), necessita 200+ demos. |
| VL-JEPA (16 conceitos) | LIMITADO | 2/10 | Alinhamento conceitual implementado, qualidade das etiquetas em melhoria. |

**Niveis de maturidade:**
- **CALIBRATING** (0-49 demos): 0.5x confianca, coaching fortemente integrado por COPER
- **LEARNING** (50-199 demos): 0.8x confianca, features neurais gradualmente ativadas
- **MATURE** (200+ demos): Confianca total, todos os subsistemas contribuem

---

## Documentacao

### Guias do Usuario

| Documento | Descricao |
|-----------|-----------|
| [Guia do Usuario (PT)](docs/USER_GUIDE_PT.md) | Guia completo de instalacao, setup wizard, API keys, todas as telas, aquisicao de demos, troubleshooting |
| [User Guide (EN)](docs/USER_GUIDE.md) | Complete installation, setup wizard, API keys, all screens, demo acquisition, troubleshooting |
| [Guida Utente (IT)](docs/USER_GUIDE_IT.md) | Guida completa installazione e utilizzo |

### Documentacao Arquitetural

| Documento | Descricao |
|-----------|-----------|
| [Arquitetura Parte 1](docs/AI-cs2-coach-part1.md) | Design do sistema e arquitetura core |
| [Arquitetura Parte 2](docs/AI-cs2-coach-part2.md) | Subsistemas de redes neurais |
| [Arquitetura Parte 3](docs/AI-cs2-coach-part3.md) | Pipeline de coaching e gestao do conhecimento |
| [Analise de Cybersecurity](docs/cybersecurity.md) | Postura de seguranca e modelo de ameacas |

### Papers de Pesquisa (17 Estudos)

A pasta `docs/Studies/` contem 17 papers de pesquisa aprofundados que cobrem os fundamentos teoricos e as decisoes de engenharia por tras de cada subsistema:

| # | Estudo | Tema |
|---|--------|------|
| 01 | Fundamentos Epistemicos | Framework de representacao e raciocinio do conhecimento |
| 02 | Algebra da Ingestao | Modelo matematico do processamento de dados de demo |
| 03 | Redes Recorrentes | Teoria das redes LTC e Hopfield |
| 04 | Aprendizado por Reforco | Fundamentos de RL para decisoes de coaching |
| 05 | Arquitetura Perceptiva | Design da pipeline de processamento visual |
| 06 | Arquitetura Cognitiva | Modelagem de crencas e sistemas decisionais |
| 07 | Arquitetura JEPA | Teoria da Joint-Embedding Predictive Architecture |
| 08 | Engenharia Forense | Metodologia de debug e diagnostico |
| 09 | Feature Engineering | Design e validacao do vetor de 25 dimensoes |
| 10 | Database e Storage | SQLite WAL, DB por partida, estrategia de migracao |
| 11 | Motor Tri-Daemon | Arquitetura multi-daemon e ciclo de vida |
| 12 | Avaliacao e Falsificacao | Metodologia de teste e validacao |
| 13 | Explicabilidade e Coaching | Atribuicao causal e design de interface do usuario |
| 14 | Etica, Privacidade e Integridade | Protecao de dados e consideracoes eticas sobre IA |
| 15 | Hardware e Scaling | Otimizacao para varias configuracoes de hardware |
| 16 | Mapas e GNN | Analise espacial e abordagens com redes neurais em grafos |
| 17 | Impacto Sociotecnico | Direcoes futuras e implicacoes sociais |

---

## Alimentando o Coach

O coach de IA vem sem nenhum conhecimento pre-treinado. Ele aprende exclusivamente a partir de arquivos demo profissionais de CS2. A qualidade do coaching e diretamente proporcional a qualidade e quantidade das demos ingeridas.

### Limiares de Contagem de Demos

| Demos Pro | Nivel | Confianca | O que Acontece |
|-----------|-------|-----------|----------------|
| 0-9 | Nao pronto | 0% | Minimo de 10 demos pro necessarias para o primeiro ciclo de treinamento |
| 10-49 | CALIBRATING | 50% | Coaching basico ativo, conselhos marcados como provisorios |
| 50-199 | LEARNING | 80% | Confiabilidade crescente, cada vez mais personalizado |
| 200+ | MATURE | 100% | Confianca total, maxima precisao |

### Onde Encontrar Demos Pro

1. Va ate [hltv.org](https://www.hltv.org) > Results
2. Filtre por eventos top-tier: Major Championship, IEM Katowice/Cologne, BLAST Premier, ESL Pro League, PGL Major
3. Selecione partidas de times no top-20 (Navi, FaZe, Vitality, G2, Spirit, Heroic)
4. Prefira series BO3/BO5 para maximizar os dados de treinamento por download
5. Diversifique em todos os mapas Active Duty — uma distribuicao desbalanceada cria um coach desbalanceado
6. Baixe o link "GOTV Demo" ou "Watch Demo"

### Planejamento de Armazenamento

Os arquivos `.dem` sao tipicamente de 300-850 MB cada. Planeje seu armazenamento de acordo:

| Demos | Arquivos Raw | DBs de Partida | Total |
|-------|-------------|----------------|-------|
| 10 | ~5 GB | ~1 GB | ~6 GB |
| 50 | ~30 GB | ~5 GB | ~35 GB |
| 100 | ~60 GB | ~10 GB | ~70 GB |
| 200 | ~120 GB | ~20 GB | ~140 GB |

Tres locais de armazenamento separados:

| Local | Conteudo | Recomendacao |
|-------|----------|-------------|
| Core Database | Estatisticas do jogador, estado do coaching, metadados HLTV | Permanece na pasta do programa |
| Brain Data Root | Pesos dos modelos de IA, logs, knowledge base | SSD recomendado |
| Pro Demo Folder | Arquivos .dem raw + bancos de dados SQLite por partida | O maior, HDD aceitavel |

### Monitoramento TensorBoard

```bash
tensorboard --logdir runs/coach_training
```

Abra [http://localhost:6006](http://localhost:6006) para monitorar o conviction index, transicoes de estado de maturidade, especializacao de gates e curvas de loss do treinamento.

> Para a checklist completa passo-a-passo do ciclo de coaching e o guia detalhado de armazenamento, consulte o [Guia do Usuario](docs/USER_GUIDE_PT.md).

---

## Solucao de Problemas

### Problemas Comuns

| Problema | Solucao |
|----------|---------|
| `ModuleNotFoundError: No module named 'kivy'` | Instale as dependencias do Kivy: `pip install kivy-deps.glew==0.3.1 kivy-deps.sdl2==0.7.0 kivy-deps.angle==0.4.0 Kivy==2.3.0 KivyMD==1.2.0` (pule kivy-deps no Linux) |
| `CUDA not available` | Verifique o driver com `nvidia-smi`, reinstale o PyTorch com `--index-url https://download.pytorch.org/whl/cu121` |
| `sentence-transformers not installed` | Aviso nao-bloqueante. Instale com `pip install sentence-transformers` para embeddings melhorados, ou ignore (fallback TF-IDF funciona) |
| App crasha com erro GL | Configure `KIVY_GL_BACKEND=angle_sdl2` (Windows) ou `KIVY_GL_BACKEND=sdl2` (Linux) |
| `database is locked` | Feche todos os processos Python e reinicie |
| Tela branca/vazia | Execute a partir da raiz do projeto: `python Programma_CS2_RENAN/main.py`, verifique que `layout.kv` existe |
| Reset para estado de fabrica | Delete `Programma_CS2_RENAN/user_settings.json` e reinicie |

### Localizacoes dos Bancos de Dados

| Banco de Dados | Caminho | Conteudo |
|----------------|---------|----------|
| Principal | `Programma_CS2_RENAN/backend/storage/database.db` | Estatisticas do jogador, estado do coaching, dados de treinamento |
| HLTV | `Programma_CS2_RENAN/backend/storage/hltv_metadata.db` | Metadados de jogadores profissionais |
| Conhecimento | `Programma_CS2_RENAN/data/knowledge_base.db` | Base de conhecimento RAG |
| Por partida | `{PRO_DEMO_PATH}/match_data/match_*.db` | Dados tick-a-tick da partida |

> Para o troubleshooting completo, consulte o [Guia do Usuario](docs/USER_GUIDE_PT.md).

---

## Licenca

Este projeto possui licenca dupla. Copyright (c) 2025-2026 Renan Augusto Macena.

Voce pode escolher entre:
- **Licenca Proprietaria** — Todos os Direitos Reservados (padrao). Visualizacao para fins educacionais e permitida.
- **Apache License 2.0** — Open source permissiva com protecao de patentes.

Consulte [LICENSE](LICENSE) para os termos completos.

---

## Autor

**Renan Augusto Macena**

Construido com paixao por um jogador de Counter-Strike com mais de 10.000 horas desde 2004, combinando profundo conhecimento do jogo com engenharia de IA para criar o sistema de coaching definitivo.

> *"Eu sempre quis um guia profissional — como os que os verdadeiros jogadores profissionais tem — para entender como realmente e quando alguem treina do jeito certo e joga do jeito certo."*

---

# Guia do Usuario

Guia completo para instalar, configurar e usar o Macena CS2 Analyzer no Windows ou Linux.

---

## Sumario

1. [Requisitos do Sistema](#1-requisitos-do-sistema)
2. [Instalacao](#2-instalacao)
3. [Primeiro Inicio e Assistente de Configuracao](#3-primeiro-inicio--assistente-de-configuracao)
4. [Configurando API Keys (Steam e FaceIT)](#4-configurando-api-keys-steam--faceit)
5. [Tela Inicial](#5-tela-inicial)
6. [Pagina de Configuracoes](#6-pagina-de-configuracoes)
7. [Tela do Coach e Chat com IA](#7-tela-do-coach--chat-com-ia)
8. [Historico de Partidas](#8-historico-de-partidas)
9. [Detalhe da Partida](#9-detalhe-da-partida)
10. [Painel de Desempenho](#10-painel-de-desempenho)
11. [Visualizador Tatico (Widget de Mapa 2D)](#11-visualizador-tatico-widget-de-mapa-2d)
12. [Perfil do Jogador](#12-perfil-do-jogador)
13. [Alimentando o Coach: Guia de Aquisicao de Demos e Gerenciamento de Armazenamento](#13-alimentando-o-coach-guia-de-aquisicao-de-demos-e-gerenciamento-de-armazenamento)
14. [Solucao de Problemas](#14-solucao-de-problemas)

---

## 1. Requisitos do Sistema

| Componente | Minimo | Recomendado |
|------------|--------|-------------|
| SO | Windows 10 / Ubuntu 22.04 | Windows 10/11 |
| Python | 3.10 | 3.10 ou 3.12 |
| RAM | 8 GB | 16 GB |
| GPU | Nenhuma (modo CPU) | NVIDIA GTX 1650+ (CUDA 12.1) |
| Disco | 3 GB livres | 5 GB livres |
| Tela | 1280x720 | 1920x1080 |

---

## 2. Instalacao

### 2.1 Clonar o Repositorio

```bash
git clone https://github.com/renanaugustomacena-ux/Counter-Strike-coach-AI.git
cd Counter-Strike-coach-AI
```

### 2.2 Windows (Configuracao Automatizada)

Abra o **PowerShell** na raiz do projeto e execute:

```powershell
.\scripts\Setup_Macena_CS2.ps1
```

Este script ira:
- Verificar se o Python 3.10+ esta instalado
- Criar um ambiente virtual (`venv_win/`)
- Instalar o PyTorch (versao CPU) e todas as dependencias
- Inicializar o banco de dados
- Instalar o Playwright (navegador Chromium para scraping do HLTV)

**Para suporte a GPU** (apenas NVIDIA), apos o script concluir:

```powershell
.\venv_win\Scripts\pip.exe install --force-reinstall torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### 2.3 Windows (Configuracao Manual)

Se o script do PowerShell falhar ou se voce preferir a instalacao manual:

```powershell
# Criar ambiente virtual
python -m venv venv_win
.\venv_win\Scripts\activate

# Instalar PyTorch (escolha UM):
# Apenas CPU:
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
# NVIDIA GPU (CUDA 12.1):
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Instalar todas as outras dependencias
pip install -r Programma_CS2_RENAN/requirements.txt

# Inicializar banco de dados
python -c "import sys; sys.path.append('.'); from Programma_CS2_RENAN.backend.storage.database import init_database; init_database()"

# Instalar navegador do Playwright
pip install playwright
python -m playwright install chromium
```

### 2.4 Linux (Ubuntu/Debian)

```bash
# Dependencias do sistema
sudo apt update
sudo apt install -y python3.10 python3.10-venv python3.10-dev
sudo apt install -y libsdl2-dev libglew-dev build-essential

# Criar ambiente virtual
python3.10 -m venv venv_linux
source venv_linux/bin/activate

# Instalar PyTorch (escolha UM):
# Apenas CPU:
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
# NVIDIA GPU (CUDA 12.1):
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Instalar dependencias (ignore kivy-deps somente para Windows se o pip reclamar)
pip install -r Programma_CS2_RENAN/requirements.txt
pip install Kivy==2.3.0 KivyMD==1.2.0

# Inicializar banco de dados
python -c "import sys; sys.path.append('.'); from Programma_CS2_RENAN.backend.storage.database import init_database; init_database()"

# Instalar navegador do Playwright
pip install playwright
python -m playwright install chromium
```

### 2.5 Verificar a Instalacao

```bash
# Ative seu venv primeiro, depois:
python -c "import torch; print(f'PyTorch: {torch.__version__}')"
python -c "import kivy; print(f'Kivy: {kivy.__version__}')"
python -c "from Programma_CS2_RENAN.backend.nn.config import get_device; print(f'Device: {get_device()}')"
```

Saida esperada (exemplo com GPU):
```
PyTorch: 2.5.1+cu121
Kivy: 2.3.0
Device: cuda:0
```

### 2.6 Iniciar o Aplicativo

```bash
# Windows
.\venv_win\Scripts\python.exe Programma_CS2_RENAN/main.py

# Linux
./venv_linux/bin/python Programma_CS2_RENAN/main.py
```

A janela abre em 1280x720. Na **primeira execucao**, voce vera o Assistente de Configuracao (Setup Wizard).

---

## 3. Primeiro Inicio e Assistente de Configuracao

Quando voce executa o main.py pela primeira vez, o aplicativo mostra um **assistente de configuracao em 3 etapas**.

### Etapa 1: Tela de Boas-Vindas

Voce ve uma mensagem de boas-vindas explicando o aplicativo. Clique em **START** para iniciar a configuracao.

### Etapa 2: Diretorio Raiz dos Dados da IA

O aplicativo pergunta: **"Onde a IA deve armazenar seus dados de treinamento?"**

Esta e a pasta onde os modelos de rede neural, a base de conhecimento e os conjuntos de dados de treinamento serao salvos. Pode estar em qualquer drive.

**Como configurar:**
1. Clique em **Select Folder** — um seletor de arquivos abre
2. Navegue ate o local desejado (ex.: `D:\CS2_Coach_Data` ou `C:\Users\SeuNome\Documents\CS2Coach`)
3. Selecione a pasta e confirme
4. O aplicativo cria tres subdiretorios dentro dela: `knowledge/`, `models/`, `datasets/`

**Ou** cole um caminho manualmente no campo de texto.

> **Dica:** Escolha um local com pelo menos 2 GB de espaco livre. Um SSD e recomendado para treinamento mais rapido.

> **Se voce vir "Permission denied":** Escolha uma pasta dentro do seu diretorio de usuario, como `C:\Users\SeuNome\Documents\MacenaData`.

Clique em **NEXT** quando terminar.

### Etapa 3: Configuracao Concluida

Clique em **LAUNCH** para entrar no aplicativo. O assistente nao aparecera novamente nas proximas execucoes.

> **Para re-executar o assistente:** Delete o arquivo `Programma_CS2_RENAN/user_settings.json` e reinicie o aplicativo.

---

## 4. Configurando API Keys (Steam e FaceIT)

As API keys permitem que o aplicativo busque seu historico de partidas e estatisticas de jogadores. Elas sao **opcionais** — o aplicativo funciona sem elas, mas alguns recursos (importacao automatica de partidas, sincronizacao de perfil do jogador) ficarao indisponiveis.

### 4.1 Steam API Key

1. Na **Tela Inicial (Home Screen)**, encontre o cartao **Personalizacao (Personalization)**
2. Clique no botao **Steam**
3. Voce vera dois campos:

**Steam ID (SteamID64):**
- Este e o seu identificador Steam de 17 digitos (ex.: `76561198012345678`)
- Clique no link **"Find Your Steam ID"** para abrir o [steamid.io](https://steamid.io) no seu navegador
- Insira a URL do seu perfil Steam e copie o numero **SteamID64**

**Steam Web API Key:**
- Clique no link **"Get Steam API Key"** para abrir o [Steam Developer](https://steamcommunity.com/dev/apikey) no seu navegador
- Faca login com sua conta Steam
- Quando perguntado sobre um nome de dominio, digite `localhost`
- Copie a chave gerada

4. Cole ambos os valores e clique em **Save Config**

> **Seguranca:** Sua API key e armazenada no **Cofre de Credenciais do Windows** (Windows Credential Manager) (ou no keyring do sistema no Linux), nao em texto puro. O arquivo de configuracoes mostra `"PROTECTED_BY_WINDOWS_VAULT"` em vez da chave real.

### 4.2 FaceIT API Key

1. Na **Tela Inicial (Home Screen)** > cartao **Personalizacao (Personalization)**, clique em **FaceIT**
2. Clique no link **"Get FaceIT API Key"** para abrir o [FaceIT Developers](https://developers.faceit.com/)
3. Crie uma conta de desenvolvedor e gere uma API key
4. Cole a chave e clique em **Save**

> **Nota:** O aplicativo valida as chaves no momento do uso, nao ao salvar. Se uma chave for invalida, voce vera um erro quando o aplicativo tentar buscar dados.

---

## 5. Tela Inicial

Apos a configuracao, este e o seu painel principal. Possui uma **barra de navegacao superior** e **cartoes rolaveis**.

### Barra de Navegacao Superior

| Icone | Acao |
|-------|------|
| Engrenagem (esquerda) | Abre **Configuracoes (Settings)** |
| Interrogacao (esquerda) | Abre **Ajuda (Help)** — topicos de documentacao pesquisaveis |
| Prancheta (direita) | Abre **Historico de Partidas (Match History)** |
| Grafico (direita) | Abre **Painel de Desempenho (Performance Dashboard)** |
| Capelo (direita) | Abre **Tela do Coach (Coach Screen)** |
| Pessoa (direita) | Abre **Perfil do Jogador (User Profile)** |

### Cartoes do Painel

**1. Progresso do Treinamento (Training Progress)**
Mostra o status do treinamento de ML em tempo real: epoca atual, perda de treino/validacao, tempo restante estimado. Quando o treinamento esta ocioso, exibe as metricas do ultimo treinamento concluido.

**2. Hub de Ingestao Pro (Pro Ingestion Hub)**
- **Set Folder**: Selecione a pasta contendo seus arquivos de demo `.dem` pessoais
- **Pro Folder**: Selecione a pasta contendo arquivos de demo `.dem` de jogadores profissionais
- **Seletor de velocidade**: Eco (lento, baixo CPU), Standard (equilibrado), Turbo (rapido, alto CPU)
- **Botao Play/Stop**: Inicia ou para o processo de ingestao de demos

**3. Personalizacao (Personalization)**
- **Profile**: Defina seu nome de jogador no jogo
- **Steam**: Configure Steam ID e API key ([veja Secao 4.1](#41-steam-api-key))
- **FaceIT**: Configure FaceIT API key ([veja Secao 4.2](#42-faceit-api-key))

**4. Analise Tatica (Tactical Analysis)**
Clique em **Launch Viewer** para abrir o visualizador de mapa tatico 2D ([veja Secao 11](#11-visualizador-tatico-widget-de-mapa-2d)).

**5. Insights Dinamicos (Dynamic Insights)**
Cartoes de coaching gerados automaticamente pela IA. Cada cartao possui:
- Uma **cor de severidade** (azul = informativo, laranja = aviso, vermelho = critico)
- Um **titulo** e **mensagem** explicando o insight
- Uma **area de foco** (ex.: "Posicionamento", "Uso de Utilitarios")

### Barra de Status do ML

No topo do painel, uma barra colorida mostra o status do servico de coaching:
- **Azul**: Servico ativo e em execucao
- **Vermelho**: Servico offline — clique em **RESTART SERVICE** para recuperar

---

## 6. Pagina de Configuracoes

Acesse pelo icone de engrenagem na Tela Inicial (Home Screen). Todas as alteracoes sao salvas imediatamente.

### Tema Visual (Visual Theme)

Tres presets de tema que alteram o esquema de cores e papel de parede do aplicativo:
- **CS2** (tons laranjas)
- **CS:GO** (tons azul-acinzentados)
- **CS 1.6** (tons verdes)

Clique em **Cycle Wallpaper** para alternar entre as imagens de fundo disponiveis para o tema atual.

### Caminhos de Analise (Analysis Paths)

- **Pasta de Demos Padrao (Default Demo Folder)**: Onde seus arquivos `.dem` pessoais estao armazenados. Clique em **Change** para selecionar uma nova pasta.
- **Pasta de Demos Pro (Pro Demo Folder)**: Onde os arquivos `.dem` de jogadores profissionais estao armazenados. Clique em **Change** para selecionar uma nova pasta.

> **Importante:** Quando voce altera a Pasta de Demos Pro, o aplicativo migra automaticamente os arquivos de banco de dados de partidas (`match_data/`) para o novo local.

### Aparencia (Appearance)

- **Tamanho da Fonte**: Pequeno (12pt), Medio (16pt) ou Grande (20pt)
- **Tipo de Fonte**: Escolha entre Roboto, Arial, JetBrains Mono, New Hope, CS Regular ou YUPIX

### Controle de Ingestao de Dados (Data Ingestion Control)

- **Alternador de Modo**: Alterne entre **Manual** (varredura unica) e **Auto** (varredura continua em intervalos)
- **Intervalo de Varredura**: Com que frequencia (em minutos) o modo automatico verifica novos demos. Minimo: 1 minuto.
- **Iniciar/Parar Ingestao**: Acionar ou parar manualmente o processo de ingestao

### Idioma (Language)

Alterne entre English, Italiano e Portugues. Toda a interface atualiza imediatamente.

---

## 7. Tela do Coach e Chat com IA

Acesse pelo icone de capelo na Tela Inicial (Home Screen).

### Painel (Dashboard)

- **Estado de Crenca (Belief State)**: Mostra a confianca de inferencia do coach de IA (0-100%). Verde quando acima de 70%.
- **Grafico de Tendencia (Trend Graph)**: Grafico de linha do seu Rating e ADR nas ultimas 20 partidas.
- **Radar de Habilidades (Skill Radar)**: Grafico aranha mostrando 5 dimensoes de habilidade (Mira, Utilitarios, Posicionamento, Leitura de Mapa, Clutch) comparadas com referencias profissionais.
- **Auditoria Causal (Causal Audit)**: Clique em **Show Advantage Audit** para visualizar a analise causal das suas decisoes.
- **Motor de Conhecimento (Knowledge Engine)**: Mostra quantos ticks de experiencia a IA processou e o progresso atual de parsing.
- **Cartoes de Coaching (Coaching Cards)**: Insights gerados pela IA com niveis de severidade.

### Painel de Chat (Chat Panel)

Clique no botao **chat toggle** (parte inferior da tela) para expandir o painel de chat.

- **Botoes de Acao Rapida (Quick Action Buttons)**: Perguntas pre-definidas — "Posicionamento", "Utilitarios", "O que melhorar?"
- **Campo de Texto (Text Input)**: Digite qualquer pergunta sobre sua gameplay
- **Respostas do Coach (Coach Replies)**: A IA analisa seus dados de partida e fornece conselhos personalizados

> **Nota:** A qualidade do coach melhora com mais demos ingeridos. Minimo de 10 demos recomendado para insights significativos.

---

## 8. Historico de Partidas

Acesse pelo icone de prancheta na Tela Inicial (Home Screen).

Mostra uma lista rolavel das suas **ultimas 50 partidas nao-profissionais**. Cada cartao de partida exibe:

- **Badge de Rating** (lado esquerdo, codificado por cores):
  - Verde: Rating > 1.10 (acima da media)
  - Amarelo: Rating 0.90 - 1.10 (media)
  - Vermelho: Rating < 0.90 (abaixo da media)
- **Nome do mapa** e **data**
- **Estatisticas**: Proporcao K/D, ADR, Abates, Mortes

**Clique em qualquer partida** para abrir a tela de [Detalhe da Partida](#9-detalhe-da-partida).

---

## 9. Detalhe da Partida

Mostra analise detalhada de uma unica partida, organizada em 4 secoes:

### Visao Geral (Overview)
Nome do mapa, data, rating geral (codificado por cores) e uma grade de estatisticas: Abates, Mortes, ADR, KAST%, HS%, Proporcao K:D, KPR (Abates Por Round), DPR (Mortes Por Round).

### Linha do Tempo dos Rounds (Round Timeline)
Uma lista de cada round jogado, mostrando:
- Numero do round e lado (CT/T)
- Abates, Mortes, Dano causado
- Badge de abertura de kill (se aplicavel)
- Resultado do round (Vitoria/Derrota)

### Grafico de Economia (Economy Graph)
Um grafico de barras mostrando o valor do seu equipamento por round. Barras azuis = lado CT, Barras amarelas = lado T. Ajuda a identificar padroes de eco/force-buy.

### Destaques e Momentum (Highlights & Momentum)
- **Grafico de Momentum**: Grafico de linha do seu delta acumulado de Abates-Mortes ao longo dos rounds. Preenchimento verde = momentum positivo, Preenchimento vermelho = negativo.
- **Insights de Coaching**: Analise gerada pela IA especifica para esta partida.

---

## 10. Painel de Desempenho

Acesse pelo icone de grafico na Tela Inicial (Home Screen). Mostra suas tendencias de desempenho a longo prazo.

### Tendencia de Rating (Rating Trend)
Grafico sparkline do seu rating nas ultimas 50 partidas. Linhas de referencia em:
- 1.10 (verde) — desempenho top
- 1.00 (branco) — media
- 0.90 (vermelho) — abaixo da media

### Desempenho por Mapa (Per-Map Performance)
Cartoes rolaveis horizontalmente, um por mapa (de_dust2, de_mirage, etc.). Cada um mostra:
- Rating medio (codificado por cores)
- ADR medio e proporcao K:D
- Numero de partidas jogadas

### Pontos Fortes e Fracos (Strengths & Weaknesses)
Comparacao em duas colunas contra referencias de jogadores profissionais usando Z-scores:
- **Esquerda (Verde)**: Suas metricas mais fortes
- **Direita (Vermelho)**: Areas que precisam de melhoria

### Painel de Utilitarios (Utility Panel)
Grafico de barras comparando seu uso de utilitarios com referencias profissionais em 6 metricas:
- Granadas HE, Molotovs, Granadas de Fumaca
- Tempo de Cegueira por Flash, Assistencias de Flash, Utilitarios Nao Utilizados

---

## 11. Visualizador Tatico (Widget de Mapa 2D)

Acesse pelo **Launch Viewer** na Tela Inicial (Home Screen).

Este e o visualizador de replay 2D em tempo real. Ele renderiza arquivos de demo como uma visualizacao interativa de mapa.

### O que Voce Ve
- **Mapa 2D**: Vista superior do mapa de CS2 com posicoes dos jogadores como circulos coloridos
- **Rotulos dos Jogadores**: Nome, funcao e barras de vida para cada jogador
- **Marcadores de Eventos**: Icones de abate, indicadores de plantio/desarme de bomba
- **Sobreposicao da IA (AI Overlay)**: Predicoes fantasma mostrando posicoes sugeridas pela IA (quando habilitado)

### Controles
- **Play/Pause**: Iniciar ou pausar a reproducao
- **Velocidade (Speed)**: Alternar entre 0.5x, 1x, 2x
- **Barra de Tempo (Timeline Scrubber)**: Clique em qualquer lugar na barra horizontal para pular para um tick especifico
- **Seletor de Mapa (Map Selector)**: Alternar entre mapas (para demos multi-mapa)
- **Seletor de Round (Round Selector)**: Pular para um round especifico ou visualizar a partida completa
- **Alternador Ghost AI (Ghost AI Toggle)**: Habilitar/desabilitar predicoes de posicao da IA

### Carregando um Demo
Na primeira entrada, um seletor de arquivo abre automaticamente. Selecione um arquivo `.dem` para carregar. O visualizador analisa e renderiza os dados do demo.

---

## 12. Perfil do Jogador

Acesse pelo icone de pessoa na Tela Inicial (Home Screen).

Mostra seu avatar de jogador, nome, funcao e biografia. Clique no **icone de lapis** para editar sua biografia e funcao. Clique em **SYNC WITH STEAM** para puxar seus dados de perfil do Steam (requer Steam API key).

---

## 13. Alimentando o Coach: Guia de Aquisicao de Demos e Gerenciamento de Armazenamento

O coach de IA vem **sem nenhum conhecimento pre-treinado**. Ele aprende exclusivamente a partir de arquivos demo de partidas profissionais de CS2 (`.dem`). A qualidade e profundidade do coaching que voce recebe e diretamente proporcional a qualidade e quantidade de demos que voce importa. Sem demos, as telas de coaching exibirao "Calibrating" e a maioria das funcoes de coaching permanecera inativa.

Esta secao explica como adquirir arquivos demo, quantos voce precisa e como planejar seu armazenamento.

### 13.1 Por que o Coach Comeca Vazio

Diferente de ferramentas de coaching tradicionais que vem com dicas estaticas, o Macena CS2 Analyzer constroi sua inteligencia a partir de **gameplay profissional real**. Na primeira execucao:

- As redes neurais (RAP Coach, JEPA, Belief Model) tem pesos aleatorios sem nenhum conhecimento tatico
- O pipeline de coaching nao tem nenhuma referencia profissional para comparar seu gameplay
- O banco de experiencias e o sistema de conhecimento RAG estao vazios

Isso e por design. O coach aprende com dados reais de partidas profissionais, nao com conselhos sinteticos ou pre-fabricados. Quanto mais demos de alta qualidade voce fornecer, mais refinado e preciso o coaching se torna.

### 13.2 Como Baixar Demos Pro do HLTV.org

Siga estes passos para construir sua biblioteca de demos profissionais:

1. Va ate [hltv.org](https://www.hltv.org) e navegue ate **Results** (Resultados)
2. Filtre por **eventos top-tier**: Major Championships, IEM Katowice/Cologne, BLAST Premier, ESL Pro League, PGL Major
3. Selecione partidas envolvendo **times do top-20** (ex. Navi, FaZe, Vitality, G2, Spirit, Heroic)
4. Prefira **series BO3 ou BO5** — mais rounds por download significa mais dados de treinamento por arquivo
5. Na pagina da partida, clique em **"Watch Demo"** (ou "GOTV Demo") para baixar o arquivo `.dem`
6. **Diversifique os mapas** — cubra todos os mapas do Active Duty (Mirage, Inferno, Nuke, Ancient, Anubis, Dust2, Vertigo). Baixar 50 demos do mesmo mapa criara um coach tendencioso
7. **Escolha com cuidado** — selecione as melhores partidas: finais de torneio, partidas eliminatorias de playoff e Grand Finals. Estas contem a maior profundidade tatica

**O que evitar:**
- Showmatches e partidas de exibicao (baixa intensidade tatica)
- Qualificatorias com times desconhecidos/amadores (qualidade inconsistente)
- Eventos beneficentes ou partidas entre criadores de conteudo
- Demos muito antigas (mudancas no meta as tornam menos relevantes)

**Eventos recomendados (maxima qualidade):**
- CS2 Major Championships (qualquer ano)
- IEM Katowice, IEM Cologne
- BLAST World Final, BLAST Premier
- ESL Pro League Finals
- PGL Major series

### 13.3 Quantas Demos Baixar

Quanto mais demos voce importar, melhor seu coach se torna. Aqui estao os niveis de coaching:

| Demos Pro Importadas | Nivel de Coaching | Confianca | Comportamento do Coach |
|---------------------|-------------------|-----------|----------------------|
| **0 - 9** | Nao pronto | 0% | Coach inativo. Minimo de 10 demos pro necessarias para iniciar o primeiro ciclo de treinamento. |
| **10 - 49** | CALIBRATING | 50% | Coaching basico ativo. Conselhos marcados como provisorios. |
| **50 - 199** | LEARNING | 80% | Coaching intermediario. Confianca crescente, cada vez mais confiavel. |
| **200+** | MATURE | 100% | Confianca total. Coaching production-ready com maxima precisao. |

**Limites-chave:**
- **10 demos pro**: O primeiro ciclo de treinamento e acionado automaticamente. Este e o minimo absoluto.
- **Crescimento de 10%**: Apos o primeiro ciclo, o retreinamento e acionado automaticamente cada vez que sua contagem de demos pro cresce 10% (ex. 10 → 11, 50 → 55, 100 → 110).
- **50 demos**: Minimo recomendado para coaching significativo e acionavel.
- **200+ demos**: Meta para coaching maduro e de alta confianca em todos os mapas e cenarios.

**A regra de ouro: mais demos = coach melhor.** Baixe o maximo de demos pro de alta qualidade que puder. Nao ha limite superior — o sistema melhora continuamente com mais dados.

### 13.4 Gates de Maturidade Explicados

Dois sistemas de maturidade operam em paralelo:

**A. Niveis baseados na Contagem de Demos** (principal, visivel no app)

Estes niveis sao baseados no numero bruto de demos pro importadas (veja tabela na secao 13.3). Eles controlam diretamente o multiplicador de confianca aplicado a todos os conselhos de coaching.

**B. Conviction Index** (avancado, visivel via TensorBoard)

Durante o treinamento, a IA rastreia um indice composto de "conviccao" (0.0 a 1.0) calculado a partir de cinco sinais neurais: entropia das crencas (belief entropy), especializacao dos gates, foco conceitual, precisao de valor e estabilidade de funcao.

| Estado | Conviction Index | O que Significa |
|--------|-----------------|-----------------|
| **DOUBT** | < 0.30 | Modelo incerto. Crencas ruidosas, especialistas nao especializados. |
| **LEARNING** | 0.30 - 0.60 | Formacao ativa de crencas. Especialistas comecando a se diferenciar. |
| **CONVICTION** | > 0.60 (estavel por 10+ epocas) | Crencas fortes e consistentes entre os lotes de treinamento. |
| **MATURE** | > 0.75 (estavel por 20+ epocas) | Modelo convergido. Inferencia production-ready. |
| **CRISIS** | Queda brusca > 20% | Anomalia detectada (overfitting ou mudanca na distribuicao dos dados). Investigacao necessaria. |

O conviction index fornece uma compreensao mais profunda do estado interno da IA, alem da simples contagem de demos. Voce pode monitora-lo em tempo real via TensorBoard (veja secao 13.6).

### 13.5 Planejamento de Armazenamento

Arquivos `.dem` sao **pesados** — tipicamente de 300 a 850 MB cada. Conforme voce constroi sua biblioteca de demos, os requisitos de espaco crescem significativamente. Planeje com antecedencia.

**Estimativas de Espaco:**

| Demos Pro | Arquivos .dem Raw | Bancos de Dados Match | Estimativa Total |
|-----------|------------------|----------------------|-----------------|
| 10 | ~5 GB | ~1 GB | **~6 GB** |
| 50 | ~30 GB | ~5 GB | **~35 GB** |
| 100 | ~60 GB | ~10 GB | **~70 GB** |
| 200 | ~120 GB | ~20 GB | **~140 GB** |

**Recomendacoes:**

- **Use um drive separado** com bastante espaco livre para sua Pro Demo Folder. Um HDD serve perfeitamente para armazenamento de demos; SSD e preferivel para o Brain Data Root (modelos de IA e treinamento)
- **Crie uma pasta dedicada** (ex. `D:\CS2_Pro_Demos\`) ANTES de comecar a baixar demos
- Configure este caminho em **Configuracoes (Settings) > Analysis Paths > Pro Demo Folder**
- Se armazenar demos no **mesmo drive** do programa, garanta pelo menos **50 GB de espaco livre** alem das necessidades do sistema operacional e aplicativos
- A pasta `match_data/` (bancos de dados SQLite por partida) e criada automaticamente junto a sua Pro Demo Folder
- O sistema **NAO** exclui demos antigas automaticamente — monitore o espaco do seu drive periodicamente

**Por que tres locais de armazenamento separados?**

| Local | O que Armazena | Onde Colocar |
|-------|---------------|-------------|
| **Core Database** (pasta do programa) | Estatisticas do jogador, estado do coaching, metadados HLTV | Sempre permanece na pasta do programa. Portatil. |
| **Brain Data Root** (Assistente de Configuracao) | Pesos dos modelos de IA, logs, base de conhecimento, cache | SSD recomendado para treinamento mais rapido. |
| **Pro Demo Folder** (Configuracoes) | Arquivos .dem raw + bancos de dados SQLite por partida | Necessita de mais espaco. HDD aceitavel. |

### 13.6 Monitoramento TensorBoard

Voce pode monitorar o progresso de treinamento do coach e a maturidade em tempo real usando TensorBoard.

**Iniciar TensorBoard:**
```bash
tensorboard --logdir runs/coach_training
```

Depois abra [http://localhost:6006](http://localhost:6006) no seu navegador.

**Metricas-chave para monitorar:**
- **`maturity/conviction_index`** (Scalars): Deve tender para cima ao longo das epocas de treinamento
- **`maturity/state`** (Text): Rastreia transicoes atraves de doubt → learning → conviction → mature
- **`maturity/gate_specialization`** (Scalars): Valores mais altos significam que a rede de especialistas esta se especializando mais
- **`loss/train`** e **`loss/val`** (Scalars): Curvas de perda de treinamento e validacao — ambas devem diminuir
- **`gates/mean_activation`** (Scalars): Roteamento de gates na camada mixture-of-experts

TensorBoard e opcional, mas altamente recomendado para usuarios que querem entender como seu coach esta evoluindo.

### 13.7 Primeiro Ciclo de Coaching: Checklist Passo a Passo

Siga esta checklist da instalacao ate seu primeiro conselho de coaching:

1. **Instale** o aplicativo e complete o **Assistente de Configuracao** (configure seu Brain Data Root)
2. Va em **Configuracoes (Settings) > Analysis Paths** e defina sua **Pro Demo Folder** para um drive/pasta dedicada com bastante espaco
3. **Baixe pelo menos 10 demos pro** do HLTV.org (mapas diversificados!)
4. **Coloque os arquivos `.dem`** na Pro Demo Folder configurada
5. **Inicie o app** — o daemon Hunter descobre automaticamente novos arquivos demo
6. **Aguarde a importacao** — cada demo leva aproximadamente 5-10 minutos para processar. Monitore o progresso na Tela Inicial (Home Screen)
7. Apos **10 demos pro serem importadas**, o daemon Teacher inicia automaticamente o **primeiro ciclo de treinamento**
8. *(Opcional)* **Monitore a maturidade** via TensorBoard para ver o conviction index subir
9. **Conecte sua conta Steam** (Home > Personalizacao > Steam ID)
10. **Jogue 10+ partidas competitivas** — suas demos pessoais sao localizadas automaticamente via integracao Steam
11. Uma vez que voce tenha **10+ demos pessoais E 10+ demos pro**, o pipeline de coaching completo se ativa!

### 13.8 Solucao de Problemas: Espaco em Disco

- **Drive cheio?** Mova sua Pro Demo Folder para um drive maior via Configuracoes (Settings). O diretorio `match_data/` migra automaticamente.
- **Banco de dados crescendo muito rapido?** Os arquivos SQLite por partida em `match_data/` podem ser excluidos individualmente para partidas antigas que voce nao precisa mais revisar em detalhe.
- **Quer economizar espaco mantendo o coaching?** Os arquivos `.dem` podem ser excluidos apos a importacao — todos os dados necessarios sao extraidos para os bancos de dados de partida durante o processamento. Porem, manter os arquivos `.dem` originais permite re-importacao futura caso o parser de demos seja atualizado.
- **Cache ocupando espaco?** O cache de importacao em `ingestion/cache/` pode ser limpo com seguranca. As demos serao re-analisadas a partir dos arquivos `.dem` originais no proximo acesso.

---

## 14. Solucao de Problemas

### "ModuleNotFoundError: No module named 'kivy'"

As dependencias do Kivy nao estao instaladas. No Windows:
```bash
pip install kivy-deps.glew==0.3.1 kivy-deps.sdl2==0.7.0 kivy-deps.angle==0.4.0
pip install Kivy==2.3.0 KivyMD==1.2.0
```
No Linux, pule os pacotes `kivy-deps` — eles sao exclusivos do Windows.

### "No module named 'watchdog'"

```bash
pip install watchdog
```
Isso e necessario para a deteccao automatica de arquivos de demo. Sem ele, use a ingestao manual nas Configuracoes (Settings).

### "CUDA not available" / GPU nao detectada

Verifique se o driver NVIDIA esta instalado:
```bash
nvidia-smi
```
Depois reinstale o PyTorch com CUDA:
```bash
pip install --force-reinstall torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```
Verifique:
```bash
python -c "import torch; print(torch.cuda.is_available())"  # Deve imprimir True
```

> **Sem GPU NVIDIA?** O aplicativo funciona em CPU. O treinamento e mais lento, mas tudo funciona.

### Aviso "sentence-transformers not installed"

Isso e **normal** e nao-bloqueante. O aplicativo usa embeddings TF-IDF como alternativa. Para instalar:
```bash
pip install sentence-transformers
```
A primeira execucao baixa um modelo de ~80MB — isso e esperado.

### Aplicativo trava ao iniciar com erro GL do Kivy

No Windows, tente:
```bash
set KIVY_GL_BACKEND=angle_sdl2
python Programma_CS2_RENAN/main.py
```
No Linux:
```bash
export KIVY_GL_BACKEND=sdl2
python Programma_CS2_RENAN/main.py
```

### Erro de bloqueio do banco de dados ("database is locked")

Outro processo esta com o banco de dados aberto. Feche todos os processos Python:
```bash
# Windows
taskkill /F /IM python.exe
# Linux
pkill -f python
```
Depois reinicie o aplicativo.

### Permissao negada ao selecionar pastas

Escolha uma pasta dentro do seu diretorio de usuario:
- Windows: `C:\Users\SeuNome\Documents\MacenaData`
- Linux: `~/MacenaData`

Evite caminhos protegidos pelo sistema como `C:\Program Files\` ou `/usr/`.

### Aviso "Integrity mismatch detected"

Este e um aviso do modo de desenvolvimento da auditoria de seguranca RASP. Significa que os arquivos fonte foram modificados desde a ultima geracao do manifesto de integridade. **Nao bloqueia o aplicativo** — apenas bloqueia builds congelados/de producao.

### Aplicativo abre mas mostra tela em branco/branca

O arquivo de layout KV falhou ao carregar. Verifique:
1. Voce esta executando a partir da raiz do projeto (nao de dentro de `Programma_CS2_RENAN/`)
2. O arquivo `Programma_CS2_RENAN/apps/desktop_app/layout.kv` existe
3. Execute: `python Programma_CS2_RENAN/main.py` (nao `python main.py`)

### Como resetar o aplicativo para o estado de fabrica

Delete `user_settings.json` e reinicie:
```bash
# Windows
del Programma_CS2_RENAN\user_settings.json
# Linux
rm Programma_CS2_RENAN/user_settings.json
```
O assistente de configuracao aparecera novamente na proxima execucao.

### Onde meus bancos de dados estao armazenados?

| Banco de Dados | Localizacao | Conteudo |
|----------------|-------------|----------|
| BD Principal | `Programma_CS2_RENAN/backend/storage/database.db` | Estatisticas de jogadores, estado do coaching, dados de treinamento |
| BD HLTV | `Programma_CS2_RENAN/backend/storage/hltv_metadata.db` | Metadados de jogadores profissionais (separado do treinamento) |
| BD de Conhecimento | `Programma_CS2_RENAN/data/knowledge_base.db` | Base de conhecimento RAG |
| BDs de Partidas | `{PRO_DEMO_PATH}/match_data/match_*.db` | Dados tick-a-tick por partida |

---

## Referencia Rapida

| Acao | Como |
|------|------|
| Iniciar o aplicativo | `python Programma_CS2_RENAN/main.py` |
| Re-executar o assistente | Delete `user_settings.json`, reinicie |
| Alterar pasta de demos | Configuracoes (Settings) > Caminhos de Analise (Analysis Paths) > Change |
| Adicionar chave Steam | Tela Inicial (Home) > Personalizacao (Personalization) > Steam |
| Adicionar chave FaceIT | Tela Inicial (Home) > Personalizacao (Personalization) > FaceIT |
| Iniciar ingestao | Tela Inicial (Home) > Hub de Ingestao Pro (Pro Ingestion Hub) > Botao Play |
| Ver replay de partida | Tela Inicial (Home) > Launch Viewer |
| Perguntar ao coach de IA | Tela do Coach (Coach Screen) > Chat toggle > Digitar pergunta |
| Alterar tema | Configuracoes (Settings) > Tema Visual (Visual Theme) |
| Alterar idioma | Configuracoes (Settings) > Idioma (Language) |
