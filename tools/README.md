> **[English](README.md)** | **[Italiano](README_IT.md)** | **[Português](README_PT.md)**

# Root-Level Project Tools

Root-level project tools for validation, diagnostics, and maintenance.

## Validation Tools

- `headless_validator.py` — Headless validation gate (245+ checks across 23 phases, mandatory pre-commit)
- `verify_all_safe.py` — Safety verification across all modules
- `portability_test.py` — Cross-platform portability checks
- `run_console_boot.py`, `verify_main_boot.py` — Boot verification tools

## Build and Deployment

- `build_pipeline.py` — Build pipeline orchestration
- `generate_manifest.py` — Generate integrity manifest for RASP

## Database Tools

- `db_health_diagnostic.py` — Database health diagnostic
- `migrate_db.py` — Database migration tool
- `reset_pro_data.py` — Reset professional player data

## Project Maintenance

- `Feature_Audit.py` — Feature completeness audit
- `Sanitize_Project.py` — Project sanitization (removes orphaned files, phantom directories)

## Usage

```bash
# Headless validation (run before every commit)
python tools/headless_validator.py

# Database health check
python tools/db_health_diagnostic.py

# Generate integrity manifest
python tools/generate_manifest.py

# Portability check
python tools/portability_test.py
```

## Notes

All tools must be run from the project root directory.
