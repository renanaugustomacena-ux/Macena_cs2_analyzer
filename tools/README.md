> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Português](README_PT.md)**

# Root-Level Project Tools

Root-level project tools for validation, diagnostics, and maintenance.

## Validation Tools

- `headless_validator.py` — Headless validation gate (245+ checks across 23 phases, mandatory pre-commit)
- `dead_code_detector.py` — Detect orphan modules, duplicate definitions, stale imports
- `verify_all_safe.py` — Safety verification across all modules
- `portability_test.py` — Cross-platform portability checks
- `Feature_Audit.py` — Feature alignment audit (parser vs ML pipeline)
- `run_console_boot.py`, `verify_main_boot.py` — Boot verification tools

## Build and Deployment

- `build_pipeline.py` — Build pipeline orchestration (sanitize, test, manifest, compile, audit)
- `audit_binaries.py` — Post-build binary integrity validation (SHA-256)

## Database Tools

- `db_health_diagnostic.py` — Database health diagnostic (10 sections)
- `migrate_db.py` — Database migration tool (backward compatibility)
- `reset_pro_data.py` — Reset professional player data (multi-phase, idempotent)

## Project Maintenance

- `dev_health.py` — Development health orchestrator (runs multiple tools)
- `Sanitize_Project.py` — Project sanitization (removes user settings, local DB, logs)

## Usage

```bash
# Headless validation (run before every commit)
python tools/headless_validator.py

# Development health check
python tools/dev_health.py

# Database health check
python tools/db_health_diagnostic.py

# Portability check
python tools/portability_test.py

# Dead code detection
python tools/dead_code_detector.py
```

## Notes

All tools must be run from the project root directory.
