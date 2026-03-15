# Audit Report 02 — RAP Coach & Training

**Scope:** `backend/nn/rap_coach/`, `experimental/rap_coach/`, RAP processing — 25 files, ~3,024 lines | **Date:** 2026-03-10 | **Refreshed:** 2026-03-13
**Open findings:** 0 HIGH | 6 MEDIUM | 11 LOW

> All existing findings confirmed. No new findings in this domain — new RAP-adjacent issues (gradient clipping, batch_size=1, tactical role targets) filed under AUDIT_01 as they originate in shared NN code.

---

## MEDIUM Findings

| ID | File | Finding |
|---|---|---|
| RAP-M-02 | communication.py | Feedback templates use fabricated values from confidence scalar, not real game metrics |
| RAP-M-03 | pedagogy.py | `_detect_utility_need()` uses `sigmoid(hidden.mean())` — proxy may not correlate with utility need |
| RAP-M-07 | test_arch.py | Uses assert instead of test framework — stripped with `-O` flag |
| RAP-M-08 | tensor_factory.py | Channel semantics (legacy vs POV) not tracked on generated tensors |
| RAP-M-09 | tensor_factory.py | Mixed `int()` truncation vs `math.floor()` in world-to-grid conversion |
| RAP-M-12 | skill_assessment.py | Skill vector attribute access without getattr guards |

## LOW Findings

| ID | File | Finding |
|---|---|---|
| RAP-L-01 | rap_coach/ | 11 deprecated shims not cleaned up |
| RAP-L-02 | perception.py | No output dimension assertion on forward() |
| RAP-L-03 | strategy.py | Forward returns bare tuple instead of NamedTuple |
| RAP-L-04 | communication.py | Confidence threshold 0.7 hardcoded |
| RAP-L-05 | pedagogy.py | Coaching concepts hardcoded as list |
| RAP-L-06 | chronovisor_scanner.py | Maturity gate not enforced in backend |
| RAP-L-07 | chronovisor_scanner.py | `if model:` after `RAPCoachModel()` — always truthy |
| RAP-L-08 | test_arch.py | Only tests shapes, not gradient flow or NaN propagation |
| RAP-L-09 | skill_assessment.py | Fallback 0.5 undocumented |
| RAP-L-10 | player_knowledge.py | Unused constant `HEARING_RANGE_FOOTSTEP` |
| RAP-L-11 | perception.py | `num_blocks=[1,2,2,1]` group structure misleading — all blocks use same dimension |

## Cross-Cutting

1. **Training/Inference Skew** — Channel order (legacy vs POV), tensor resolution (64 vs 128/224).
2. **Heuristic Attribution Quality** — 2 of 5 concepts (Aggression, Rotation) derived from same signal with different scaling.
3. **Fabricated Feedback Values** — Player-facing advice uses confidence-derived fake measurements.

## Resolved Since 2026-03-10

Removed 6 MEDIUM findings (RAP-M-01, 04, 05, 06, 10, 11) — fixed in commits 8c347a3..2fa2cf3. Key fixes: position head 2D projection documented, Hopfield trained-flag gate, gradient clipping added, silent skip replaced with debug log, MAX_HISTORY_TICKS=512 hard cap, FLASH_RADIUS corrected to 400.
