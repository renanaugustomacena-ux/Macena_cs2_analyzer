> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Português](README_PT.md)**

# Strumenti di Progetto a Livello Root

Strumenti di progetto a livello root per validazione, diagnostica e manutenzione.

## Strumenti di Validazione

- `headless_validator.py` — Gate di validazione headless (245+ controlli in 23 fasi, obbligatorio pre-commit)
- `verify_all_safe.py` — Verifica sicurezza su tutti i moduli
- `portability_test.py` — Controlli portabilità cross-platform
- `run_console_boot.py`, `verify_main_boot.py` — Strumenti verifica boot

## Build e Deployment

- `build_pipeline.py` — Orchestrazione pipeline di build
- `generate_manifest.py` — Genera manifest integrità per RASP

## Strumenti Database

- `db_health_diagnostic.py` — Diagnostica salute database
- `migrate_db.py` — Strumento migrazione database
- `reset_pro_data.py` — Reset dati giocatori professionisti

## Manutenzione Progetto

- `Feature_Audit.py` — Audit completezza funzionalità
- `Sanitize_Project.py` — Pulizia progetto (rimuove file orfani, directory fantasma)

## Utilizzo

```bash
# Validazione headless (eseguire prima di ogni commit)
python tools/headless_validator.py

# Controllo salute database
python tools/db_health_diagnostic.py

# Genera manifest integrità
python tools/generate_manifest.py

# Controllo portabilità
python tools/portability_test.py
```

## Note

Tutti gli strumenti devono essere eseguiti dalla directory root del progetto.
