# Audit Report 05 — Coaching & Services

**Scope:** `backend/services/`, `backend/knowledge/`, `backend/coaching/` — 28 files, ~6,842 lines | **Date:** 2026-03-10 | **Refreshed:** 2026-03-13
**Open findings:** 1 CRITICAL | 2 HIGH | 10 MEDIUM | 20 LOW

---

## CRITICAL Finding

| ID | File | Finding |
|---|---|---|
| C-50 | visualization_service.py:118-121 | **[FIXED 2026-03-13]** Module-level function now calls `get_visualization_service()` to ensure initialization. |

## HIGH Findings

| ID | File | Finding |
|---|---|---|
| C-48 | profile_service.py:122 | **[FIXED 2026-03-13]** Changed `g["appid"]` to `g.get("appid")` — safe against missing keys. |
| C-49 | experience_bank.py:892-900 | **[FIXED 2026-03-13]** Added `threading.Lock` with double-checked locking pattern to singleton factory. |

## MEDIUM Findings

| ID | File | Finding |
|---|---|---|
| C-08 | coaching_dialogue.py | Hardcoded T-side full_buy defaults when game state unknown |
| C-14 | lesson_generator.py | Hardcoded pro player tips (s1mple, ropz) — stale over time |
| C-20 | telemetry_client.py | HTTP telemetry in production (no HTTPS enforcement for non-localhost) |
| C-29 | graph.py:83,110,140 | Per-operation SQLite connections (no pooling). WAL only set in `_init_db()` — subsequent connections don't set pragma. |
| C-32 | pro_demo_miner.py | KAST/HS normalization boundary fragile at exactly 1.0 |
| C-40 | explainability.py | Template defaults use fabricated values, not wired to real data |
| C-51 | visualization_service.py:60-65 | `plt.close(fig)` not in `finally` block — matplotlib figure leak on savefig error |
| C-52 | analysis_orchestrator.py:299,311 | Duplicate guard check for `"team" not in tick_data.columns` — second check unreachable |
| C-53 | rag_knowledge.py:448 | `generate_rag_coaching_insight()` creates new `KnowledgeRetriever` per call — loads SBERT model every time |
| C-54 | knowledge_base/help_system.py:71 | Module-level `help_system = HelpSystem()` triggers file I/O on import — violates lazy singleton pattern |

## LOW Findings

| ID | File | Finding |
|---|---|---|
| C-04 | analysis_service.py | `analyze_latest_performance()` returns only single most recent match |
| C-05 | analysis_service.py | `check_for_drift()` re-queries same data each call (no cache) |
| C-19 | profile_service.py | App ID 730 comment missing (CS2 replaced CS:GO in-place) |
| C-23 | visualization_service.py | `plt.close(fig)` not in finally block after `savefig()` |
| C-24 | knowledge/__init__.py | Eager import triggers SQLite DB init on package import |
| C-31 | init_knowledge_base.py | Missing `tactical_knowledge.json` only logged as warning |
| C-33 | pro_demo_miner.py | Archetype classification thresholds hardcoded |
| C-35 | rag_knowledge.py | `_brute_force_retrieve()` loads up to 500 full records into memory |
| C-37 | vector_index.py | `_load_knowledge_vectors()` loads ALL entries without limit |
| C-38 | coaching/__init__.py | Eager HybridCoachingEngine import triggers PyTorch load |
| C-39 | correction_engine.py | No actionable corrections until ~30 rounds played |
| C-43 | hybrid_engine.py | `__main__` block uses hardcoded synthetic stats |
| C-44 | longitudinal_engine.py | Regression insight always "Refocus on fundamentals" |
| C-46 | pro_bridge.py | Default values (HS 0.45, entry_rate 0.25) hardcoded |
| C-47 | token_resolver.py | Uses raw deltas instead of Z-scores for comparison |
| C-55 | coaching_dialogue.py:307 | Comment "History already has the user message appended" is stale/misleading |
| C-56 | pro_bridge.py:108-111 | `_is_awper` — `sum(weapons.values())` can be 0 if all values are 0 → `ZeroDivisionError` |
| C-57 | hybrid_engine.py:37-39 | Fallback baseline version "2024-01" is 2+ years stale. No runtime age check. |
| C-58 | hybrid_engine.py:659-661 | `get_hybrid_engine()` creates new instance every call — not a singleton (inconsistent with other factories) |
| C-59 | graph.py:197-204 | `get_knowledge_graph()` singleton lacks thread safety — no lock |

## Cross-Cutting

1. **Stale Baselines** — Multiple modules contain hardcoded pro player references and statistical baselines that drift over time. No automated staleness detection.
2. **RAG Retriever Instantiation Cost** — `KnowledgeRetriever()` loads Sentence-BERT on init, instantiated without caching in multiple places.
3. **Singleton Pattern Inconsistency** — Some singletons use double-checked locking (correct), others use simple check-and-create (race condition), others use module-level instantiation (import-time side effects).
4. **Session Commit Redundancy** — 20+ explicit `session.commit()` calls inside `get_session()` auto-commit context managers. Harmless but confusing.

## Resolved Since 2026-03-10

Removed 14 MEDIUM findings (C-01, 02, 07, 10, 11, 16, 18, 22, 25, 26, 34, 36, 42, 45) and 5 LOW findings (C-03, 09, 12, 13, 17) — fixed in commits c10f393..dfd2f88. Key fixes: thread-safe singleton with lock, log suppression for repeated failures, RAG context sanitized, retry+timeout on profile fetch, lazy viz singleton, atomic usage_count, base64/JSON deserialization unified, MetaDriftEngine crash guarded.
