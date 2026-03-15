# Audit Report 04 — Analysis & Game Theory

**Scope:** `backend/analysis/` — 11 files, ~3,672 lines | **Date:** 2026-03-10 | **Refreshed:** 2026-03-13
**Open findings:** 0 HIGH | 4 MEDIUM | 8 LOW

> **Note:** Most remaining findings involve hand-tuned constants that will be naturally calibrated as more pro demo data is ingested (~200 demos available). The pipeline is ready — feeding data will auto-correct these baselines.
>
> **2026-03-13 refresh:** Zero CRITICAL or HIGH issues found. All existing findings confirmed still open. No new findings — the analysis module is solid.

---

## MEDIUM Findings

| ID | File | Finding |
|---|---|---|
| A-02 | belief_model.py | Hand-tuned log-odds weights — no empirical validation |
| A-07 | game_tree.py | Transposition table uses FIFO eviction, not LRU |
| A-20 | utility_economy.py | Flash cost hardcoded $200 — may be $250 in current CS2 |
| A-23 | deception_index.py | Sound deception uses crouch ratio as sole proxy — conflates stealth with deception |

## LOW Findings

| ID | File | Finding |
|---|---|---|
| A-03 | belief_model.py | HP range assertion missing in `estimate()` |
| A-05 | belief_model.py | Per-bracket calibration minimum (10) vs global (30) |
| A-08 | game_tree.py | Chance node value temporarily holds probability |
| A-14 | win_probability.py | Self-test block not reachable via test framework |
| A-17 | role_classifier.py | `KnowledgeRetriever()` re-instantiated per call |
| A-22 | utility_economy.py | `np.mean` on 4-element dict.values() — unnecessary numpy overhead |
| A-25 | engagement_range.py | 50+ named positions hardcoded as Python literals |
| A-26 | engagement_range.py | Role range baselines hand-estimated |

## Cross-Cutting

1. **Pervasive Hand-Tuned Parameters** — 4 remaining files contain unvalidated constants. A calibration pass using parsed pro demos will improve coaching accuracy.
2. **WinProbabilityPredictor as Shared Dependency** — Game tree, blind spot, and coaching all depend on it. Training the model cascades improvements through the entire stack.

## Resolved Since 2026-03-10

Removed 7 MEDIUM findings (A-06, 13, 15, 16, 18, 21, 24) and 4 LOW findings (A-01, 04, 10, 11) — fixed in commits f1e921f..2fa2cf3. Key fixes: deterministic state hash (tuple-based), win probability documented, role classifier consensus, entropy deltas documented, lazy module imports, named constants for thresholds.
