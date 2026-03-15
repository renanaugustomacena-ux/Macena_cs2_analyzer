# Mission Rules — Audit Remediation Checklist

> Keep this file open in a tab during all remediation work.
> Consult it at the start of every session and before every fix.

---

## Before Touching Any File

- [ ] Run `python tools/headless_validator.py` — confirm baseline is green
- [ ] Read the target file in full — understand it before changing it
- [ ] Search all callers: `grep -rn "function_name" Programma_CS2_RENAN/` — know the blast radius
- [ ] Check if this fix is blocked by a dependency (see Dependency Map below)
- [ ] If fix touches >2 files, write the complete file list BEFORE starting

## While Writing the Fix

- [ ] No magic numbers — extract to named constants at file top
- [ ] One logical change per commit — never bundle unrelated fixes
- [ ] New `import`? Trace the chain to verify no circular imports
- [ ] New `threading.Lock`? Must be module-level with double-checked locking
- [ ] New sentinel value? Add a comment explaining what it means and where it's consumed
- [ ] Changed a function signature? Update EVERY caller (grep first)

## After Each Fix

- [ ] Run `python tools/headless_validator.py` — must exit 0
- [ ] Run specific tests: `pytest tests/ -k "relevant_keyword" -v`
- [ ] Read the diff (`git diff`) — verify it's exactly what you intended
- [ ] Commit with finding ID: `fix(T10-C1): add hltv_player_cache to _ALLOWED_TABLES`
- [ ] Update finding status in the relevant `docs/AUDIT_*.md` report

## Before Moving to Next Phase

- [ ] Every finding in current phase marked FIXED
- [ ] `python tools/headless_validator.py` exits 0
- [ ] Phase-specific gate passes (see Phase Gates below)
- [ ] No new `TODO`/`FIXME` left in files you touched without a tracking issue

---

## Dependency Map — NEVER Violate This Ordering

```
INF-C2  ──blocks──►  S-52
S-49    ──must precede──►  S-48
T10-C1  ──blocks──►  any clean-slate reset
C-49    ──blocks (concurrency)──►  Phase 1 testing
NN-M-03 ──blocks (NaN)──►  NN-H-03
NN-H-03 ──blocks (batch size)──►  NN-M-10
```

Each arrow = "left must be fixed and validated before starting right."

---

## The 8 Traps Specific to This Codebase

1. **Don't fix S-52 before INF-C2** — you'll point at yet another wrong database
2. **Don't run reset_pro_data before T10-C1** — crashes mid-reset, leaves DB partially cleared (worse than dirty)
3. **Don't fix S-48 before S-49** — imported rows get IDs that conflict after sequence reset
4. **`model_dump().get(f, 0.0)` does NOT protect against NULL** — key exists with value `None`, `.get()` returns `None` not `0.0`. Use `is not None` guard
5. **Scheduler `T_max=100` is hardcoded** — if you test with 10 epochs, LR barely moves. Always match `T_max` to `max_epochs`
6. **Gradient clipping must cover ALL parameters** — use `model.parameters()`, not subset
7. **Validation and training encode negatives via different code paths** — changes to `target_encoder` must be verified in BOTH
8. **Cross-match negative pool starts empty** — first ~50 batches are skipped during warm-up. This is expected, not a bug

---

## Phase Gates

| Phase | Gate Condition |
|-------|---------------|
| 0 | validator green + `reset_pro_data` runs end-to-end without crash |
| 1 | validator green + 2-epoch dry-run: finite loss, LR decreasing |
| 2 | validator green + CI pipeline passes |
| 3 | validator green + manual smoke test of all 13 Qt screens |
| 4 | validator green + service integration paths tested |
| 5 | validator green + `pytest tests/` coverage increased |
| 6 | validator green + dead code count lower than baseline |

---

## Phase 0 Execution Order

| Step | ID | Fix | Blocks |
|------|----|-----|--------|
| 0.1 | INF-C2 | Resolve knowledge DB identity crisis | S-52 |
| 0.2 | T10-C1 | Add `hltv_player_cache` to `_ALLOWED_TABLES` | All resets |
| 0.3 | S-52 | Fix `run_fix("knowledge")` wrong DB target | — |
| 0.4 | S-49 | Add backup before sequence DELETE | S-48 |
| 0.5 | S-48 | Add INSERT logic to `_transfer_table()` | — |
| 0.6 | C-50 | Fix `visualization_service` uninitialized singleton | — |
| 0.7 | C-48 | Fix `profile_service` KeyError | — |
| 0.8 | C-49 | Fix `experience_bank` thread-safe singleton | Phase 1 |

## Phase 1 Execution Order

| Step | ID | Fix | Blocks |
|------|----|-----|--------|
| 1.1 | NN-M-03 | Fix NaN in `_get_user_baseline_vector` | NN-H-03 |
| 1.2 | NN-M-12 | Sentinel for missing target values (not 0.5) | — |
| 1.3 | NN-H-03 | Cross-match negative sampling | NN-M-10 |
| 1.4 | NN-M-10 | Step scheduler + parameterize T_max | — |
| 1.5 | NN-H-01 | Gradient clipping in finetune loop | — |
| 1.6 | NN-H-02 | Unify negative encoding paths | — |
