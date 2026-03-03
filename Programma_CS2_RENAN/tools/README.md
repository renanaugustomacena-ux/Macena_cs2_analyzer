> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Português](README_PT.md)**

# Validation and Diagnostic Tools

Validation and diagnostic tools forming a 4-level hierarchy for comprehensive system health checks.

## Validation Hierarchy

1. **Headless Validator** — Fast gate (245+ checks across 23 phases, <20s, must pass before task completion)
2. **Pytest** — Logic validation (390+ tests)
3. **Backend Validator** — Build and health checks (40 checks)
4. **Goliath Hospital** — Comprehensive diagnostic suite

## Core Tools

- `headless_validator.py` — Fast validation gate with 245+ checks across 23 phases
- `Goliath_Hospital.py` — Hospital-style diagnostics with departments:
  - NEUROLOGY (models), CARDIOLOGY (data), ICU (services)
  - SECURITY (secrets, injection), IMAGING (architecture)
- `backend_validator.py` — Backend health checks (40 checks)
- `brain_verify.py` — Brain model verification (13 learning rules)
- `ui_diagnostic.py` — UI screen completeness diagnostic

## Specialized Tools

- `Ultimate_ML_Coach_Debugger.py` — ML coach debugging tool
- `db_inspector.py` — Database inspection CLI
- `dead_code_detector.py` — Dead code detection
- `dev_health.py` — Development health checks
- `sync_integrity_manifest.py` — RASP integrity manifest generation
- `brain_verification/` — Model verification scripts

## Usage

```bash
# Headless validation (mandatory pre-commit)
python tools/headless_validator.py

# Full diagnostic suite
python Programma_CS2_RENAN/tools/Goliath_Hospital.py
```
