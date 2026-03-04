# Build Checklist — Macena CS2 Analyzer

## Prerequisites

- [ ] Python 3.10+ with venv activated
- [ ] `pip install -r requirements.txt` clean (exit 0)
- [ ] `pip install pyinstaller` (not in requirements.txt — build-only dep)
- [ ] `python tools/headless_validator.py` exits 0

## Pre-Build Verification

- [ ] All 13 pre-commit hooks pass: `pre-commit run --all-files`
- [ ] Test suite passes: `pytest --cov=Programma_CS2_RENAN --cov-fail-under=49`
- [ ] No `print()` in production code (headless validator Phase 12 checks this)
- [ ] `integrity_manifest.json` is current (regenerate if files changed)

## Build Command

```bash
python -m PyInstaller --noconfirm packaging/cs2_analyzer_win.spec --log-level WARN
```

Output: `dist/Macena_CS2_Analyzer/`

## PyTorch CPU-Only Variant (Smaller Build)

To reduce build size (~500MB savings), install CPU-only torch before building:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

The code auto-detects CPU via `backend/nn/config.py:get_device()` — no code changes needed.

## Post-Build Verification

- [ ] `dist/Macena_CS2_Analyzer/Macena_CS2_Analyzer.exe` exists
- [ ] Launch exe — verify no crash on startup
- [ ] Verify layout.kv loads (UI renders correctly)
- [ ] Verify map_config.json accessible (map images load)
- [ ] Verify alembic/ directory present in bundle
- [ ] Verify PHOTO_GUI/ assets present (fonts, themes, backgrounds)

## Windows Installer (Optional)

Requires [Inno Setup](https://jrsoftware.org/isinfo.php):

```bash
iscc packaging/windows_installer.iss
```

## Known Constraints

- FlareSolverr requires Docker — not bundled, must be run separately
- Playwright requires browser install — not bundled for frozen builds
- HLTV scraping excluded from frozen build (Playwright dep)
- SentenceTransformer model downloads on first run (~80MB)
