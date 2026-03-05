# Scraping de Dados Profissionais HLTV

> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Português](README_PT.md)**

## Visão Geral

Infraestrutura de web scraping para estatísticas de jogadores profissionais CS2 e resultados de partidas de HLTV.org usando automação de navegador Playwright. Inclui rate limiting, cache de respostas e gerenciamento robusto de seletores CSS.

## Componentes Principais

### `hltv_api_service.py`
- **`HLTVApiService`** — Serviço de scraping principal com automação de navegador Playwright
- Busca estatísticas de jogadores, resultados de partidas, composições de times, dados de torneios
- Tratamento de erros com lógica de retry e proteção de timeout

### `rate_limit.py`
- **`RateLimiter`** — Rate limiting de requisições para respeitar carga do servidor HLTV
- Limiar configurável de requisições-por-minuto
- Implementação de algoritmo token bucket

### `selectors.py`
- **`HLTVURLBuilder`** — Construção de URL para páginas HLTV (estatísticas de jogadores, detalhes de partida, páginas de times)
- **`PlayerStatsSelectors`** — Seletores CSS para extração de estatísticas de jogadores
- Gerenciamento centralizado de seletores para manutenibilidade contra mudanças de layout do site

### Subdiretórios

#### `browser/`
- Gerenciamento de contexto de navegador Playwright
- Configuração Chrome headless
- Tratamento de cookies e sessões

#### `collectors/`
- **`PlayerCollector`** — Extração especializada de dados de jogadores
- Parsing de resultados de partidas
- Agregação de roster de times

#### `cache/`
- Camada de cache de respostas para minimizar requisições redundantes
- Expiração de cache baseada em TTL
- Estratégias de invalidação de cache

## Integração

Usado pela pipeline `pro_ingest.py` para popular tabelas `ProPlayer`, `MatchResult` e `TeamComposition`. Dados HLTV servem como ground truth para baselines profissionais e análise de meta-jogo.

## Rate Limiting

Padrão: 10 requisições/minuto. Configurável via `config.HLTV_RATE_LIMIT`. Exceder o limite aciona backoff exponencial.

## Tratamento de Erros

Falhas de rede, timeouts e erros de parsing são logados com IDs de correlação. Requisições falhadas são retentadas até 3 vezes com backoff exponencial.
