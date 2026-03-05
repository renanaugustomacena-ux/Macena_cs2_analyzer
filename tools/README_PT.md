> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Português](README_PT.md)**

# Ferramentas de Projeto no Nivel Raiz

Ferramentas de projeto no nivel raiz para validacao, diagnostico e manutencao.

## Ferramentas de Validacao

- `headless_validator.py` — Gate de validacao headless (245+ verificacoes em 23 fases, obrigatorio pre-commit)
- `dead_code_detector.py` — Detecta modulos orfaos, definicoes duplicadas, imports obsoletos
- `verify_all_safe.py` — Verificacao de seguranca em todos os modulos
- `portability_test.py` — Verificacoes de portabilidade multiplataforma
- `Feature_Audit.py` — Auditoria de alinhamento de features (parser vs pipeline ML)
- `run_console_boot.py`, `verify_main_boot.py` — Ferramentas de verificacao de boot

## Build e Deployment

- `build_pipeline.py` — Orquestracao do pipeline de build (sanitize, test, manifest, compile, audit)
- `audit_binaries.py` — Validacao de integridade de binarios pos-build (SHA-256)

## Ferramentas de Banco de Dados

- `db_health_diagnostic.py` — Diagnostico de saude do banco de dados (10 secoes)
- `migrate_db.py` — Ferramenta de migracao de banco de dados (backward compatibility)
- `reset_pro_data.py` — Reset de dados de jogadores profissionais (multi-fase, idempotente)

## Manutencao do Projeto

- `dev_health.py` — Orquestrador de saude de desenvolvimento (executa multiplas ferramentas)
- `Sanitize_Project.py` — Sanitizacao do projeto (remove configuracoes do usuario, DB local, logs)

## Uso

```bash
# Validacao headless (executar antes de cada commit)
python tools/headless_validator.py

# Verificacao de saude do desenvolvimento
python tools/dev_health.py

# Verificacao de saude do banco de dados
python tools/db_health_diagnostic.py

# Verificacao de portabilidade
python tools/portability_test.py

# Deteccao de codigo morto
python tools/dead_code_detector.py
```

## Notas

Todas as ferramentas devem ser executadas a partir do diretorio raiz do projeto.
