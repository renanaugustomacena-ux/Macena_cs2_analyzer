> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Portugues](README_PT.md)**

# Backend

Camada de logica de negocios do Macena CS2 Analyzer, organizada em 14 sub-pacotes seguindo principios de design orientado ao dominio.

## Visao Geral

O backend implementa todo o pipeline de coaching com IA — desde o parsing bruto de demos ate a inferencia de redes neurais e saida de coaching em linguagem natural. Cada sub-pacote e dono do seu dominio, invariantes de dados e modos de falha.

## Estrutura

```
backend/
├── analysis/           Motores de teoria dos jogos (11 modulos)
├── coaching/           Pipeline de coaching (COPER, Hibrido, RAG, NN)
├── control/            Logica de controle de treinamento
├── data_sources/       Integracao de dados externos (Demo, HLTV, Steam, Faceit)
├── ingestion/          Helpers de ingestao do backend
├── knowledge/          Base de conhecimento RAG + banco de experiencias COPER
├── knowledge_base/     Armazenamento de grafo de conhecimento
├── nn/                 Redes neurais (6 tipos de modelo, 40+ arquivos)
├── onboarding/         Fluxo de onboarding de novos usuarios
├── processing/         Feature engineering, baselines, validacao
├── progress/           Rastreamento de progresso de treinamento
├── reporting/          Consultas analiticas para telas da UI
├── services/           Camada de servicos (Coaching, Analise, Dialogo, Ollama)
└── storage/            Banco de dados SQLite, SQLModel, backup, dados de partidas
```

## Padroes Arquiteturais Chave

- **Fallback de Coaching em 4 Niveis**: COPER > Hibrido > RAG > NN Base
- **Gating de Maturidade em 3 Estagios**: CALIBRACAO > APRENDIZADO > MADURO
- **Decaimento Temporal de Baseline**: Ponderacao exponencial da evolucao de habilidades
- **Vetor de Features Unificado**: 25 dimensoes via `FeatureExtractor`
- **SQLite Modo WAL**: Leitura/escrita concorrente em todos os bancos de dados

## Dependencias entre Sub-Pacotes

```
data_sources → processing → analysis → coaching → services
                   ↓            ↓
               knowledge ←── nn (treinamento + inferencia)
                   ↓
               storage (camada de persistencia)
```
