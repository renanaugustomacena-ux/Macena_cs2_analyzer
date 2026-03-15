# Qt Migration — Rules & Checklist

> Tracking document for the Kivy → Qt migration audit and implementation.
> Check off items as each batch is completed.

---

## Non-Negotiable Rules

| # | Rule | Enforced By |
|---|------|-------------|
| R1 | Use `.claude/skills/` for all quality gates | CLAUDE.md |
| R2 | Plan/elaborate/execute in small batches | This document |
| R3 | Run `python tools/headless_validator.py` after every change (exit 0) | Dev Rule 9 |
| R4 | Commits authored solely by **Renan Augusto Macena** — zero AI mention | Global CLAUDE.md |
| R5 | No Co-Authored-By lines in any commit | Global CLAUDE.md |
| R6 | `/scope-guard` before implementing multi-file changes | Skill Rules |
| R7 | `/change-impact` before modifying shared interfaces | Skill Rules |
| R8 | `/pre-commit` before every commit | Dev Rule 10 |
| R9 | Every tick is sacred — no tick decimation | Project invariant |
| R10 | METADATA_DIM = 25 is a hard contract everywhere | Architecture |
| R11 | Read before modify — always read existing code first | Dev Rule 1 |
| R12 | Backward compatibility — new features must not break existing behavior | Dev Rule 2 |

---

## Audit Report Sections — Progress

- [x] **Section 1**: New Qt Frontend — Complete Assessment
- [x] **Section 2**: Old Kivy Frontend — Complete Assessment
- [x] **Section 3**: Industrial-Grade Implementation Plan with CI/CD

---

## Implementation Phases — Progress (Future)

### Phase 1: Core Infrastructure
- [ ] P1.1 — Port Settings screen (theme, paths, language, fonts, ingestion)
- [ ] P1.2 — Port Setup Wizard (first-run flow)
- [ ] P1.3 — Port Player Profile + Edit Profile screens
- [ ] P1.4 — Port background images from Kivy version (themed backgrounds per screen, asset pipeline)

### Phase 2: Dashboard & Coaching
- [ ] P2.1 — Port Home/Dashboard (ML status, coaching card, connectivity, tactical entry)
- [ ] P2.2 — Port AI Coach screen (belief state, analytics containers, insights, chat panel)
- [ ] P2.3 — Port Coaching Chat ViewModel (Ollama integration)
- [ ] P2.4 — TensorBoard monitoring page (embedded view or launcher to track JEPA/RAP training progress — loss curves, metrics, epoch status)

### Phase 3: Integrations
- [ ] P3.1 — Port Steam Config screen (SteamID64, API key)
- [ ] P3.2 — Port FaceIT Config screen (API key)
- [ ] P3.3 — Port Help screen (searchable docs, sidebar + content)

### Phase 4: Tactical Viewer (Complex)
- [ ] P4.1 — Port TacticalMap widget (QPainter, coordinate transforms)
- [ ] P4.2 — Port PlayerSidebar (widget pooling, team lists)
- [ ] P4.3 — Port Timeline scrubber (interactive seek, event markers)
- [ ] P4.4 — Port GhostPixel debug overlay
- [ ] P4.5 — Port Tactical ViewModels (playback, ghost, chronovisor)
- [ ] P4.6 — Port TacticalViewerScreen orchestrator
- [ ] P4.7 — Port Heatmap rendering pipeline

### Phase 5: CI/CD & Quality
- [ ] P5.1 — GitHub Actions CI pipeline
- [ ] P5.2 — Pre-commit hooks for Qt app
- [ ] P5.3 — Headless validator coverage for Qt screens
- [ ] P5.4 — Automated UI smoke tests
- [ ] P5.5 — Release packaging (PyInstaller / cx_Freeze)

---

## Batch Execution Protocol

1. **Before each batch**: Review this checklist, identify next incomplete item
2. **Scope guard**: Run `/scope-guard` on target files
3. **Impact analysis**: Run `/change-impact` if touching shared code
4. **Implement**: Small, focused changes (1-3 files per batch)
5. **Validate**: `python tools/headless_validator.py` → exit 0
6. **Pre-commit**: `/pre-commit` before staging
7. **Commit**: Author = Renan Augusto Macena, no AI attribution
8. **Update this doc**: Check off completed items
