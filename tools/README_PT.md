> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Português](README_PT.md)**

# Ferramentas de Projeto no Nível Raiz

Ferramentas de projeto no nível raiz para validação, diagnóstico e manutenção.

## Ferramentas de Validação

- `headless_validator.py` — Gate de validação headless (245+ verificacoes em 23 fases, obrigatorio pre-commit)
- `verify_all_safe.py` — Verificação de segurança em todos os módulos
- `portability_test.py` — Verificações de portabilidade multiplataforma
- `run_console_boot.py`, `verify_main_boot.py` — Ferramentas de verificação de boot

## Build e Deployment

- `build_pipeline.py` — Orquestração do pipeline de build
- `generate_manifest.py` — Gera manifesto de integridade para RASP

## Ferramentas de Banco de Dados

- `db_health_diagnostic.py` — Diagnóstico de saúde do banco de dados
- `migrate_db.py` — Ferramenta de migração de banco de dados
- `reset_pro_data.py` — Reset de dados de jogadores profissionais

## Manutenção do Projeto

- `Feature_Audit.py` — Auditoria de completude de funcionalidades
- `Sanitize_Project.py` — Sanitização do projeto (remove arquivos órfãos, diretórios fantasma)

## Uso

```bash
# Validação headless (executar antes de cada commit)
python tools/headless_validator.py

# Verificação de saúde do banco de dados
python tools/db_health_diagnostic.py

# Gera manifesto de integridade
python tools/generate_manifest.py

# Verificação de portabilidade
python tools/portability_test.py
```

## Notas

Todas as ferramentas devem ser executadas a partir do diretório raiz do projeto.
