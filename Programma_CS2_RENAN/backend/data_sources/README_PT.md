> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Português](README_PT.md)**

# Data Sources — Integrações Externas

Integrações de fontes de dados externas para análise de demos, estatísticas de jogadores profissionais, sincronização de perfis Steam e dados da plataforma FACEIT.

## Módulos Principais

### Análise de Demos
- **demo_parser.py** — `parse_demo()` — Wrapper demoparser2 com cálculo de rating HLTV 2.0, exporta dados por tick e por round
- **demo_format_adapter.py** — `DemoFormatAdapter` — Conversão e validação de formato entre saídas do demo parser e esquemas internos
- **event_registry.py** — Registro e despacho de tipos de eventos para eventos de demo

### Detecção e Análise
- **trade_kill_detector.py** — `TradeKillDetector` — Identifica trade frags a partir de dados de tick (kills em janelas de 3 segundos)

### Integração Steam
- **steam_api.py** — `SteamAPI` — Integração com Steam Web API para sincronização de perfil, lista de amigos, estatísticas de jogo
- **steam_demo_finder.py** — `SteamDemoFinder` — Localiza arquivos de demo CS2 em diretórios userdata do Steam

### Integração FACEIT
- **faceit_api.py** — `FaceitAPI` — Wrapper da API da plataforma FACEIT para histórico de partidas e estatísticas de jogador
- **faceit_integration.py** — `FaceitIntegration` — Orquestração de ingestão de dados FACEIT de alto nível

### Integração HLTV
- **hltv_metadata.py** — `HLTVMetadata` — Módulo legado (veja pacote hltv/ para implementação ativa)
- **hltv_scraper.py** — `HLTVScraper` — Coleta estatísticas de jogadores profissionais do hltv.org (Rating 2.0, K/D, ADR, KAST, HS%)

## Fluxo de Dados
1. Demos ingeridas via `demo_parser.py` → validadas por `demo_format_adapter.py`
2. Perfis Steam/FACEIT sincronizados via respectivos módulos de API
3. Estatísticas de jogadores profissionais HLTV fornecem o baseline de coaching para comparar desempenho do usuário contra os pros
4. Trade kills detectados pós-análise para análise tática

## Dependências
demoparser2, FlareSolverr/Docker (estatísticas pro HLTV), requests (APIs Steam/FACEIT).
