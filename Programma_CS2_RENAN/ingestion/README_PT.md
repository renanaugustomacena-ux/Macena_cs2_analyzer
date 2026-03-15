# Pipelines de Ingestão de Demos

> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Português](README_PT.md)**

Infraestrutura de ingestão de demos para demos CS2 profissionais e de usuário com integração Steam e enriquecimento estatístico em nível de round.

## Componentes Principais

### Orquestradores Principais

**`demo_loader.py`** — Orquestrador principal de carregamento de demos
- Coordena parsing de arquivo demo com demoparser2
- Validação de integridade via `integrity.py`
- Delega para user_ingest.py ou pro_ingest.py com base na fonte da demo
- Rastreamento de progresso e recuperação de erros

**`steam_locator.py`** — Descoberta de instalação Steam
- Detecção de instalação CS2 multiplataforma (Windows, Linux, macOS)
- Parsing de registro (Windows) e varredura de sistema de arquivos
- Auto-detecção de pasta de demos

**`hltv_orchestrator.py`** — Orquestrador de sincronização de estatísticas de jogadores profissionais HLTV
- Coordena scraping de estatísticas de jogadores profissionais do hltv.org (Rating 2.0, K/D, ADR, etc.)
- Aplicação de rate limiting
- Gerenciamento de cache
- Ciclo de vida de automação de navegador
- **NOTA:** Isto NÃO lida com arquivos de demo ou metadados de demo — apenas estatísticas de jogadores profissionais

**`downloader.py`** — Downloader de arquivo demo
- Download HTTP/HTTPS com lógica de retry
- Verificação de integridade (checksum)
- Gerenciamento de download concorrente

**`integrity.py`** — Validação de integridade de arquivo demo
- Verificação de formato de arquivo
- Parsing de cabeçalho
- Detecção de corrupção

## Sub-Pacotes

### `pipelines/`

**`user_ingest.py`** — Pipeline de ingestão de demo de usuário
- Parsing de demos de usuário via demoparser2
- Extração de estatísticas de round com `round_stats_builder.py`
- Enriquecimento com `enrich_from_demo()` (kills noscope/blind, flash assists, uso de utilitários)
- Persistência em tabelas RoundStats + PlayerMatchStats

**`pro_ingest.py`** — Pipeline de ingestão de demo profissional
- Parsing de demos profissionais com enriquecimento estatístico em nível de round
- Enriquecimento estatístico em nível de round
- Geração de registros de conhecimento para sistema RAG
- Atualização de baseline estatística profissional

**`json_tournament_ingestor.py`** — Ingestão em lote de JSON de torneio
- Importação em massa de exportações de dados de torneio
- Validação de schema
- Resolução de conflitos

### `hltv/`

Infraestrutura de scraping HLTV com rate limiting e caching.

**`hltv_api_service.py`** — Cliente de API HLTV
- Interface RESTful para dados HLTV
- Tratamento de autenticação
- Parsing e normalização de respostas

**`rate_limit.py`** — Rate limiter
- Algoritmo de token bucket
- Rate limits por endpoint
- Backoff exponencial em respostas 429

**`selectors.py`** — Seletores CSS e construtores de URL
- Definições de seletores Playwright
- Construção de URL para partidas, jogadores, times, eventos

**`browser/`** — Automação Playwright
- Gerenciamento de navegador headless
- Padrões de interação de página
- Persistência de cookies

**`collectors/`** — Coletores de dados
- Coletor de metadados de partidas
- Coletor de estatísticas de jogadores
- Coletor de elenco de times
- Coletor de eventos/torneios

**`cache/`** — Cache de respostas
- Cache baseado em arquivo com TTL
- Estratégias de invalidação de cache
- Geração de chave de cache

### `hltv_api/`

Wrapper de API HLTV de terceiros (serviço externo baseado em Go).

### `registry/`

Registro de arquivo demo e gerenciamento de ciclo de vida
- Rastreamento de arquivo demo (processados, pendentes, falhados)
- Detecção de duplicatas
- Políticas de retenção
- Automação de limpeza
