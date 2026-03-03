> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Português](README_PT.md)**

# Strumenti di Validazione e Diagnostica

Strumenti di validazione e diagnostica che formano una gerarchia a 4 livelli per controlli completi della salute del sistema.

## Gerarchia di Validazione

1. **Headless Validator** — Gate veloce (245+ controlli in 23 fasi, <20s, deve passare prima del completamento task)
2. **Pytest** — Validazione logica (oltre 390 test)
3. **Backend Validator** — Controlli di build e salute (40 controlli)
4. **Goliath Hospital** — Suite diagnostica completa

## Strumenti Principali

- `headless_validator.py` — Gate di validazione veloce con 245+ controlli in 23 fasi
- `Goliath_Hospital.py` — Diagnostica in stile ospedaliero con reparti:
  - NEUROLOGY (modelli), CARDIOLOGY (dati), ICU (servizi)
  - SECURITY (secrets, injection), IMAGING (architettura)
- `backend_validator.py` — Controlli salute backend (40 controlli)
- `brain_verify.py` — Verifica modello brain (13 regole di apprendimento)
- `ui_diagnostic.py` — Diagnostica completezza schermate UI

## Strumenti Specializzati

- `Ultimate_ML_Coach_Debugger.py` — Tool debugging coach ML
- `db_inspector.py` — CLI ispezione database
- `dead_code_detector.py` — Rilevazione codice morto
- `dev_health.py` — Controlli salute sviluppo
- `sync_integrity_manifest.py` — Generazione manifest integrità RASP
- `brain_verification/` — Script verifica modelli

## Utilizzo

```bash
# Validazione headless (obbligatoria pre-commit)
python tools/headless_validator.py

# Suite diagnostica completa
python Programma_CS2_RENAN/tools/Goliath_Hospital.py
```
