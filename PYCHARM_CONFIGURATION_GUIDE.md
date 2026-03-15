# PyCharm Configuration Guide — Macena CS2 Analyzer

> Complete IDE setup for development on this project.

## 1. Project Interpreter

**Path:** `/mnt/usb/.venvs/cs2analyzer/bin/python` (Python 3.12.3)

Settings → Project → Python Interpreter → Add Interpreter → Existing:
```
/mnt/usb/.venvs/cs2analyzer/bin/python
```

Install dependencies:
```bash
source /mnt/usb/.venvs/cs2analyzer/bin/activate
pip install -r requirements.txt
```

## 2. Project Structure (Mark Directories)

Settings → Project → Project Structure:

| Directory | Mark As |
|-----------|---------|
| Project root (`.`) | **Content Root** |
| `Programma_CS2_RENAN/` | **Sources Root** — NOT the project root itself. All imports start with `from Programma_CS2_RENAN.…` |
| `tests/` | **Test Sources Root** |
| `Programma_CS2_RENAN/tests/` | **Test Sources Root** |
| `external_analysis/` | **Excluded** |
| `.venv/`, `venv*/` | **Excluded** |
| `dist/`, `build/` | **Excluded** |

**Critical:** The project root is the source root for import resolution. Imports are:
```python
from Programma_CS2_RENAN.backend.storage.database import get_db_manager
from Programma_CS2_RENAN.core.config import get_config
```

## 3. Code Style — Black + isort

### Black Formatter

Settings → Tools → Black:
- **Black path:** `/mnt/usb/.venvs/cs2analyzer/bin/black`
- **Line length:** `100`
- **Target version:** `py310`
- Enable **"On save"** formatting

Or: Settings → Editor → Code Style → Python → Set from → Black (line length: 100)

### isort (Import Sorting)

Settings → Editor → Code Style → Python → Imports:
- Profile: **Black-compatible**
- Line length: **100**
- Or install the isort plugin and configure:
  - `--profile black --line-length 100`

### File Watchers (Alternative)

Settings → Tools → File Watchers → Add:

**Black:**
- File type: Python
- Program: `$PyInterpreterDirectory$/black`
- Arguments: `--line-length 100 $FilePath$`
- Output: `$FilePath$`

**isort:**
- File type: Python
- Program: `$PyInterpreterDirectory$/isort`
- Arguments: `--profile black --line-length 100 $FilePath$`
- Output: `$FilePath$`

## 4. Type Checking — mypy

Settings → Editor → Inspections → Python → Mypy:
- Enable mypy inspection
- **mypy path:** `/mnt/usb/.venvs/cs2analyzer/bin/mypy`
- **Arguments:** `--ignore-missing-imports --allow-untyped-defs`
- **Python version:** 3.10
- **Exclude:** `external_analysis/`, `dist/`, `.venv/`, `tests/`

Or install the Mypy plugin and use `pyproject.toml` (auto-detected).

## 5. Testing — pytest

Settings → Tools → Python Integrated Tools:
- **Default test runner:** pytest
- **Test paths:** `tests/` and `Programma_CS2_RENAN/tests/`

### Run Configuration: Unit Tests

- **Name:** `All Tests`
- **Module:** pytest
- **Working directory:** Project root
- **Additional Arguments:** `--tb=short -q`
- **Environment variables:** `PYTHONPATH=.`

### Run Configuration: Tests with Coverage

- Same as above, with:
- **Additional Arguments:** `--cov=Programma_CS2_RENAN --cov-report=term-missing --cov-fail-under=35`

## 6. Run Configurations

### Console (Unified CLI)

- **Name:** `CS2 Console`
- **Script:** `console.py`
- **Working directory:** Project root
- **Python interpreter:** Venv interpreter
- **Environment variables:** `PYTHONPATH=.`

### Qt Frontend

- **Name:** `Qt App`
- **Module name:** `Programma_CS2_RENAN.apps.qt_app.app`
- **Working directory:** Project root
- **Environment variables:** `PYTHONPATH=.`

### Kivy Frontend (Legacy)

- **Name:** `Kivy App`
- **Script:** `Programma_CS2_RENAN/main.py`
- **Working directory:** Project root
- **Environment variables:** `PYTHONPATH=.;KIVY_NO_ARGS=1`

### Headless Validator (Post-Task Gate)

- **Name:** `Headless Validator`
- **Script:** `tools/headless_validator.py`
- **Working directory:** Project root
- **Environment variables:** `PYTHONPATH=.`
- **Must exit with code 0** — run after every code change

### Database Migration

- **Name:** `Alembic Upgrade`
- **Module name:** `alembic`
- **Arguments:** `upgrade head`
- **Working directory:** Project root

## 7. Pre-Commit Hooks

Install once from terminal:
```bash
source /mnt/usb/.venvs/cs2analyzer/bin/activate
pre-commit install
pre-commit install --hook-type pre-push
```

**13 hooks active:**

| Hook | Stage | Purpose |
|------|-------|---------|
| trailing-whitespace | pre-commit | Strip trailing spaces (markdown-aware) |
| end-of-file-fixer | pre-commit | Ensure newline at EOF |
| check-yaml | pre-commit | YAML syntax validation |
| check-json | pre-commit | JSON syntax validation |
| check-added-large-files | pre-commit | Block files >1MB (excludes images/CSVs) |
| check-merge-conflict | pre-commit | Detect conflict markers |
| detect-private-key | pre-commit | Block accidental key commits |
| black | pre-commit | Code formatting (100 chars) |
| isort | pre-commit | Import sorting (black profile) |
| integrity-manifest-check | pre-commit | Critical file verification |
| dev-health-quick | pre-commit | Fast health checks |
| headless-validator | **pre-push** | Full 23-phase regression gate |
| dead-code-detector | **pre-push** | Orphaned module detection |

## 8. Database Configuration

**SQLite databases** (all use WAL mode):
- **Main DB:** `Programma_CS2_RENAN/backend/storage/database.db` (created on first run)
- **HLTV Metadata:** `Programma_CS2_RENAN/backend/storage/hltv_metadata.db`
- **Per-match DBs:** Created dynamically during ingestion

**Alembic** (migrations):
- Config: `alembic.ini` in project root
- Migrations: `alembic/versions/`
- Run: `alembic upgrade head`

PyCharm Database tool (optional):
- Settings → Database → Add → SQLite
- Path: `Programma_CS2_RENAN/backend/storage/database.db`

## 9. CI/CD Pipeline Awareness

The GitHub Actions pipeline (`.github/workflows/build.yml`) runs:

1. **Lint** — pre-commit hooks (Black, isort, yaml, json, etc.)
2. **Unit Tests** — pytest with coverage (fail-under: 30%)
3. **Integration** — headless validator, portability tests
4. **Security** — Bandit, detect-secrets, pip-audit
5. **Type Check** — mypy (informational, non-blocking)
6. **Build** — PyInstaller (Windows, main branch only)

Reproduce CI locally:
```bash
# Lint
pre-commit run --all-files

# Tests
pytest --cov=Programma_CS2_RENAN --cov-fail-under=30 -q

# Integration
python tools/headless_validator.py
python tools/portability_test.py

# Type check
mypy Programma_CS2_RENAN/ --ignore-missing-imports --allow-untyped-defs

# Security
bandit -r Programma_CS2_RENAN/ -ll
```

## 10. Key Development Tools

| Tool | Path | Purpose |
|------|------|---------|
| `tools/headless_validator.py` | 23-phase regression gate | **MANDATORY** after every change |
| `tools/dead_code_detector.py` | Find orphaned modules | Run periodically |
| `tools/portability_test.py` | Cross-platform validation | Before commits |
| `tools/db_health_diagnostic.py` | Database integrity check | After DB operations |
| `tools/dev_health.py` | Quick health check | Fast sanity check |
| `tools/verify_main_boot.py` | Boot verification | After structural changes |
| `tools/Sanitize_Project.py` | Project cleanup | Before releases |

## 11. Debugging Tips

### Import Resolution Issues
If PyCharm can't resolve `Programma_CS2_RENAN.*` imports:
1. Verify project root is the Content Root (not `Programma_CS2_RENAN/`)
2. Invalidate caches: File → Invalidate Caches
3. Ensure `PYTHONPATH=.` in run configurations

### SQLite Locking
- All databases use WAL mode for concurrent access
- If you get "database is locked": check for orphan processes (`lsof *.db`)

### GPU / PyTorch
- Current setup: **CPU-only** PyTorch 2.10.0
- GPU (AMD RX 9070 XT / gfx1201): Requires PyTorch with ROCm 7.2+ (not yet available in stable)
- `HSA_OVERRIDE_GFX_VERSION=12.0.0` does NOT work (causes bus error)

## 12. File Exclusions

Add to Settings → Editor → File Types → Ignored Files and Folders:
```
*.db; *.db-wal; *.db-shm; *.dem; *.pt; *.log;
__pycache__; .venv; venv*; dist; build; .git_corrupted;
external_analysis; runs; reports
```

## 13. Useful Keyboard Shortcuts (Custom)

| Action | Shortcut | Notes |
|--------|----------|-------|
| Reformat File (Black) | `Ctrl+Alt+L` | Default, uses Black settings |
| Optimize Imports (isort) | `Ctrl+Alt+O` | Auto-sorts on save |
| Run Current File | `Shift+F10` | Default |
| Run with Coverage | — | Configure via toolbar |
| Run pytest at Cursor | `Ctrl+Shift+F10` | On test function/class |
| Navigate to Source | `Ctrl+B` | Follow imports |
| Find Usages | `Alt+F7` | Find all references |
