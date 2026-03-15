# Audit Report 03 — Processing Pipeline

**Scope:** `backend/processing/` — 28 files, ~6,679 lines | **Date:** 2026-03-10 | **Refreshed:** 2026-03-13
**Open findings:** 0 HIGH | 2 MEDIUM | 8 LOW

---

## MEDIUM Findings

| ID | File | Finding |
|---|---|---|
| P3-M-05 | momentum_tracker.py | Non-singleton: `MomentumTracker()` is instantiated per-call in some code paths, losing accumulated momentum state between calls. Should use factory singleton. |
| P3-M-06 | heatmap_generator.py | Unconditional `import cv2` at module level — cv2 is heavy (~50MB) and not needed unless heatmaps are generated. Should use lazy import. |

## LOW Findings

| ID | File | Finding |
|---|---|---|
| P3-02 | data_pipeline.py | `_MAX_PIPELINE_ROWS = 50_000` not configurable |
| P3-03 | vectorizer.py | Unknown weapons silently default to "unknown" — no logging |
| P3-08 | player_knowledge.py | Memory decay tau values not empirically validated |
| P3-12 | rating.py | KAST ratio vs percentage contract not enforced at function boundary |
| P3-16 | pro_baseline.py | f-string logger anti-pattern: `logger.info(f"...")` instead of `logger.info("%s", ...)` — bypasses lazy formatting |
| P3-19 | external_analytics.py | NaN skip count not reported |
| P3-20 | connect_map_context.py | Z-penalty factor same for all maps |
| P3-21 | dem_validator.py | 2GB max file size may be tight for 40+ round matches |

## Cross-Cutting

1. **Hardcoded CS2 Constants** — Some constants remain that could be centralized in `cs2_constants.py`.
2. **Overall Quality** — Zero CRITICAL or HIGH findings. The processing pipeline is defensively coded and well-structured. The most impactful improvement is feeding more pro demo data through to calibrate hand-tuned constants.

## Resolved Since 2026-03-10

Removed all 18 MEDIUM findings (P3-01, 04, 06, 07, 09, 10, 11, 13, 14, 15, 16, 17, 22, 28, 31, 32, 33, 35) and 6 LOW findings (P3-05, 23, 24, 25, 29, 34) — fixed in commits dfd2f88..381643d. Key fixes: HMAC integrity check, spatial dimension assertions, configurable FOV, case-insensitive nickname matching, timezone-aware datetime, schema versioning, lazy scipy import.
