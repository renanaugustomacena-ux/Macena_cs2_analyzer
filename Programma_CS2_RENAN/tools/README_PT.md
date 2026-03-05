> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Português](README_PT.md)**

# Ferramentas de Validação e Diagnóstico

Ferramentas de validação e diagnóstico formando uma hierarquia de 4 níveis para verificações abrangentes de saúde do sistema.

## Hierarquia de Validação

1. **Headless Validator** — Gate rápido (245+ verificacoes em 23 fases, <20s, deve passar antes da conclusão da tarefa)
2. **Pytest** — Validação de lógica (mais de 390 testes)
3. **Backend Validator** — Verificações de build e saúde (40 verificações)
4. **Goliath Hospital** — Suíte de diagnóstico abrangente

## Ferramentas Principais

- `headless_validator.py` — Gate de validação rápido com 245+ verificacoes em 23 fases
- `Goliath_Hospital.py` — Diagnóstico estilo hospitalar com departamentos:
  - NEUROLOGY (modelos), CARDIOLOGY (dados), ICU (serviços)
  - SECURITY (secrets, injection), IMAGING (arquitetura)
- `backend_validator.py` — Verificações de saúde do backend (40 verificações)
- `ui_diagnostic.py` — Diagnóstico de completude de telas UI

## Ferramentas Especializadas

- `Ultimate_ML_Coach_Debugger.py` — Ferramenta de debug do coach ML
- `db_inspector.py` — CLI de inspeção de banco de dados
- `dead_code_detector.py` — Detecção de código morto
- `dev_health.py` — Verificações de saúde de desenvolvimento
- `sync_integrity_manifest.py` — Geração de manifesto de integridade RASP

## Uso

```bash
# Validação headless (obrigatória pré-commit)
python tools/headless_validator.py

# Suíte de diagnóstico completa
python Programma_CS2_RENAN/tools/Goliath_Hospital.py
```
