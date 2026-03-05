> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Português](README_PT.md)**

# Strumenti di Progetto a Livello Root

Strumenti di progetto a livello root per validazione, diagnostica e manutenzione.

## Strumenti di Validazione

- `headless_validator.py` — Gate di validazione headless (245+ controlli in 23 fasi, obbligatorio pre-commit)
- `dead_code_detector.py` — Rileva moduli orfani, definizioni duplicate, import obsoleti
- `verify_all_safe.py` — Verifica sicurezza su tutti i moduli
- `portability_test.py` — Controlli portabilita' cross-platform
- `Feature_Audit.py` — Audit allineamento feature (parser vs pipeline ML)
- `run_console_boot.py`, `verify_main_boot.py` — Strumenti verifica boot

## Build e Deployment

- `build_pipeline.py` — Orchestrazione pipeline di build (sanitize, test, manifest, compile, audit)
- `audit_binaries.py` — Validazione integrita' binari post-build (SHA-256)

## Strumenti Database

- `db_health_diagnostic.py` — Diagnostica salute database (10 sezioni)
- `migrate_db.py` — Strumento migrazione database (backward compatibility)
- `reset_pro_data.py` — Reset dati giocatori professionisti (multi-fase, idempotente)

## Manutenzione Progetto

- `dev_health.py` — Orchestratore salute sviluppo (esegue piu' strumenti)
- `Sanitize_Project.py` — Pulizia progetto (rimuove impostazioni utente, DB locale, log)

## Utilizzo

```bash
# Validazione headless (eseguire prima di ogni commit)
python tools/headless_validator.py

# Controllo salute sviluppo
python tools/dev_health.py

# Controllo salute database
python tools/db_health_diagnostic.py

# Controllo portabilita'
python tools/portability_test.py

# Rilevamento codice morto
python tools/dead_code_detector.py
```

## Note

Tutti gli strumenti devono essere eseguiti dalla directory root del progetto.
