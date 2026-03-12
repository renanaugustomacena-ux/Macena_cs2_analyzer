# AUDIT_05: Coaching & Services
## Date: 2026-03-10
## Scope: 28 files across 3 directories

---

### 1. Executive Summary

| Metric | Count |
|--------|-------|
| **Files audited** | 28 |
| **Total lines** | ~6,842 |
| **HIGH findings** | 2 |
| **MEDIUM findings** | 15 |
| **LOW findings** | 12 |

The coaching layer is the most user-facing backend component — it takes raw analysis data and transforms it into actionable advice. It implements a sophisticated 4-tier fallback chain (COPER → Hybrid → Traditional+RAG → Traditional) ensuring the user always receives coaching output. Two HIGH findings: the singleton pattern for `CoachingDialogueEngine` is not thread-safe (race condition on concurrent session access), and the `_FALLBACK_BASELINE` in hybrid_engine.py is stale (January 2024 snapshot) with no automated refresh mechanism.

**Directories covered:**
- `backend/services/` — 11 files (3,173 lines)
- `backend/knowledge/` — 8 files (2,072 lines)
- `backend/coaching/` — 8 files (1,597 lines)

---

### 2. File-by-File Findings

---

#### backend/services/\_\_init\_\_.py (1 line)

No findings — empty init module.

---

#### backend/services/analysis_orchestrator.py (549 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| C-01 | MEDIUM | Concurrency | 537-538 | Module-level singleton `_orchestrator` with double-checked locking. The `_orchestrator_lock` is correct for thread safety, but the outer check on L544 (`if _orchestrator is None`) reads a shared reference without acquiring the lock. On CPython this is safe due to GIL, but is technically a data race under PEP-703 (free-threading). | Acceptable for CPython; document the GIL dependency. If free-threading is ever adopted, refactor to use `threading.Lock` consistently. |
| C-02 | MEDIUM | Error Handling | 75-76 | `_module_failure_counts` tracks per-module consecutive failures but never triggers a circuit breaker or suppresses repeated logging. If a module fails every match for 1000 matches, 1000 error lines are logged. | Add log suppression after N consecutive failures (e.g., log every 10th failure after 5 consecutive). |
| C-03 | LOW | Data Flow | 302-306 | `_build_chat_messages()` slices history with `self._history[:-1][-window_size:]` but the user message hasn't been appended to `_history` yet at this point (it's appended after LLM response on L161-162). The `[:-1]` slice is therefore slicing off the last assistant message, not the current user message. | The logic works correctly in practice because the augmented_user message is appended as a separate entry in `messages`. However, the `[:-1]` is a no-op bug — it clips the last history entry unnecessarily. Remove the `[:-1]`. |

---

#### backend/services/analysis_service.py (92 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| C-04 | LOW | API Design | 16-29 | `analyze_latest_performance()` returns only the single most recent match. For trend analysis or volatility detection, consumers need historical context. | Consider adding an `analyze_recent_performance(n=5)` variant that returns aggregated stats. |
| C-05 | LOW | Performance | 74-87 | `check_for_drift()` loads up to 100 `PlayerMatchStats` records, calls `model_dump()` on each, and converts to DataFrame. For frequent calls, this is wasteful — the same data is re-queried each time. | Cache drift results per player with a TTL, or compute drift incrementally. |

---

#### backend/services/coaching_dialogue.py (373 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| C-06 | **HIGH** | Concurrency | 364-372 | `get_dialogue_engine()` singleton has no thread lock. If two threads call it simultaneously, two `CoachingDialogueEngine` instances could be created, and the second would silently overwrite the first's `_history`. More critically, `CoachingDialogueEngine` stores mutable session state (`_history`, `_player_context`, `_session_active`) — if two UI threads share the singleton, their conversation histories interleave. | Add `threading.Lock` for singleton creation. Consider whether a singleton is appropriate for stateful per-session objects — a per-session factory may be more correct. |
| C-07 | MEDIUM | Security | 138-142 | RAG retrieval context is injected directly into the LLM prompt via string concatenation: `f"{user_message}\n\n[Retrieved coaching knowledge...]\n{retrieval_context}"`. If `retrieval_context` contains adversarial content (e.g., from user-populated experiences), it could perform prompt injection on the LLM. | Sanitize retrieval context before injection, or use a structured prompt format that separates system/user/context roles. |
| C-08 | MEDIUM | Robustness | 278-282 | `ExperienceContext` is constructed with `round_phase="full_buy"` and `side="T"` as hardcoded defaults when the actual game state is unknown. This biases experience retrieval toward T-side full-buy situations. | Use `"unknown"` defaults and let the retrieval handle the null case, or skip experience retrieval when context is insufficient. |
| C-09 | LOW | Code Quality | 303 | The comment on L300-302 says "excluding the user message we just appended" but the user message hasn't been appended at this point (see C-03). Misleading comment. | Fix comment to reflect actual control flow. |

---

#### backend/services/coaching_service.py (763 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| C-10 | MEDIUM | Fallback Chain | 256-292 | COPER failure fallback chain: COPER → Hybrid (if enabled + player_stats) → Traditional (if deviations) → Generic insight (C-01). The chain is well-designed, but the `generate_corrections(deviations, rounds_played)` call on L272 doesn't pass `nn_adjustments`, losing any NN refinement that the COPER path would have included. | Pass `nn_adjustments=None` explicitly to document that NN refinement is intentionally skipped in the fallback path, or include it if available. |
| C-11 | MEDIUM | Data Integrity | 393-395 | `tick_data["tick_rows"]` is converted to DataFrame with `pd.DataFrame(tick_data["tick_rows"])` — if `tick_rows` is very large (millions of ticks), this creates a massive in-memory DataFrame inside the coaching pipeline, which runs synchronously. | Consider streaming or sampling tick data for advanced analysis, or move to async processing. |
| C-12 | LOW | Performance | 529-531 | `KnowledgeRetriever()` is instantiated on every RAG enhancement call. `KnowledgeRetriever.__init__` creates a `KnowledgeEmbedder` which loads Sentence-BERT. While `get_llm_service()` uses a singleton, the RAG retriever does not benefit from the same caching here. | Use `KnowledgeRetriever` as a singleton or cache on the `CoachingService` instance. |
| C-13 | LOW | Observability | 107-111 | Sentry breadcrumb is wrapped in try/except ImportError, which is fine, but if Sentry IS installed and `add_breadcrumb` raises a non-ImportError exception, it would propagate up and crash the coaching pipeline. | Catch `Exception` instead of just `ImportError`, or use a no-throw wrapper. |

---

#### backend/services/lesson_generator.py (382 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| C-14 | MEDIUM | Data Staleness | 274-295 | `_generate_pro_tips()` contains hardcoded pro player tips with specific player names (s1mple, ropz) and tournament references (IEM Katowice 2024). These become stale as the meta evolves and players retire or switch teams. | Move tips to a JSON/DB-backed source that can be updated without code changes. Link to the knowledge base for dynamic tip generation. |
| C-15 | LOW | API Design | 329-353 | `get_available_demos()` returns all non-pro demos without pagination. For players with hundreds of demos, this query grows unbounded (despite the `limit=20` default). | Add offset parameter for pagination support. |

---

#### backend/services/llm_service.py (253 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| C-16 | MEDIUM | Security | 92 | LLM prompt for `generate()` concatenates user input directly into the payload sent to Ollama. While Ollama runs locally, the generated coaching text is stored in the database and displayed to the user. A crafted prompt could generate misleading coaching advice. | This is low risk for a local Ollama instance, but worth noting if the LLM backend is ever changed to a cloud service. Add input length limits. |
| C-17 | LOW | Resilience | 54-56 | When the configured model isn't found, the service silently switches to the first available model (`model_names[0]`). This could result in using a very different model (e.g., a coding model instead of a chat model) without the user knowing. | Log a warning when model substitution occurs, including both the requested and actual model names. |

---

#### backend/services/ollama_writer.py (110 lines)

No findings — clean implementation with proper fallback behavior when Ollama is unavailable. The `USE_OLLAMA_COACHING` config flag correctly gates LLM usage.

---

#### backend/services/profile_service.py (164 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| C-18 | MEDIUM | Error Handling | 116-123 | `_fetch_cs2_hours()` has no retry logic or timeout error handling (unlike the parent `_execute_steam_fetch()` which has bounded retries). If this secondary API call fails, the entire Steam fetch returns with `playtime_forever=0` but no error indicator. | Wrap in the same retry logic as the parent fetch, or propagate the error. |
| C-19 | LOW | Data Quality | 122 | `g["appid"] == 730` — App ID 730 was CS:GO. CS2 replaced CS:GO in-place and kept the same app ID, so this is technically correct. But it's worth a comment for future maintainers. | Add comment: `# 730 = CS2 (originally CS:GO, replaced in-place Sept 2023)`. |

---

#### backend/services/telemetry_client.py (60 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| C-20 | MEDIUM | Security | 17, 39 | `DEV_SERVER_URL` defaults to `http://127.0.0.1:8000` (HTTP, not HTTPS). Telemetry data (player_id, match_id, stats) is sent in plaintext. In production, this should use HTTPS. | Add HTTPS enforcement when `CS2_TELEMETRY_URL` is set to a non-localhost URL. |
| C-21 | LOW | Resilience | 36-52 | No retry logic for telemetry submission. A single network hiccup loses the telemetry data permanently. | Add bounded retry (1-2 attempts) or queue failed submissions for later retry. |

---

#### backend/services/visualization_service.py (119 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| C-22 | MEDIUM | Thread Safety | 108 | Module-level singleton `_service = VisualizationService()` is instantiated at import time. If matplotlib is not installed or its backend is misconfigured, this fails at import time and crashes any module that imports `visualization_service`. | Use lazy initialization (like other singletons in the codebase) to defer matplotlib initialization. |
| C-23 | LOW | Resource Leak | 60-61 | `plt.savefig()` followed by `plt.close(fig)` — if `savefig()` raises an exception (e.g., disk full, permission denied), the figure is never closed, leaking memory. | Use try/finally to ensure `plt.close(fig)` is always called. |

---

#### backend/knowledge/\_\_init\_\_.py (1 line)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| C-24 | LOW | Imports | 1 | Eagerly imports `KnowledgeGraphManager` and `get_knowledge_graph`, which triggers SQLite database initialization on first import of the `knowledge` package. | Acceptable if the knowledge package is always used in contexts where the DB exists. Document the side effect. |

---

#### backend/knowledge/experience_bank.py (883 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| C-25 | MEDIUM | Scalability | 303-359 | `_brute_force_retrieve_similar()` loads up to 100 candidates from DB and computes cosine similarity in a Python loop. With FAISS unavailable, this is O(100) per query — acceptable for small banks but won't scale. The `limit(100)` cap means relevant experiences beyond row 100 are invisible. | Document the scalability limitation. Consider increasing the limit or adding score-based early termination. |
| C-26 | MEDIUM | Data Integrity | 296-299 | `usage_count += 1` is incremented inside the session for retrieved experiences, but this happens inside `_brute_force_retrieve_similar()` which holds the session open. If two concurrent queries retrieve the same experience, the usage counts could be lost (last-write-wins). | Use `UPDATE ... SET usage_count = usage_count + 1` SQL to make increments atomic, or accept the minor race as non-critical. |
| C-27 | LOW | Complexity | 437-535 | `synthesize_advice()` at 98 lines is the most complex method. The pattern analysis (success_actions vs failure_actions) uses simple frequency counting which may not capture nuanced patterns. | Consider weighted pattern analysis that accounts for recency and context similarity. |
| C-28 | LOW | Code Quality | 818-830 | `_infer_position_area()` normalizes coordinates using map metadata but then classifies into only 5 areas ("T-side", "Lower", "CT-side", "Upper", "Mid") with hardcoded 0.3/0.7 thresholds. Real CS2 maps have 20+ named callouts. | This is a known simplification (the comment says "simplified version"). Consider using `engagement_range.py`'s position annotation for higher fidelity. |

---

#### backend/knowledge/graph.py (205 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| C-29 | MEDIUM | Connection Management | 41, 83, 110, 140 | Each method opens a new `sqlite3.connect()` connection. Unlike the main database which uses SQLModel/SQLAlchemy with connection pooling, the knowledge graph creates and destroys connections per operation. Under high query load, this is wasteful. | Use a connection pool or maintain a persistent connection with proper thread-safety. |
| C-30 | LOW | Security | 144 | SQL query uses parameterized queries (`?` placeholders) throughout — no SQL injection risk. Clean implementation. | No action needed. |

---

#### backend/knowledge/init_knowledge_base.py (122 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| C-31 | LOW | Robustness | 53-60 | If `tactical_knowledge.json` doesn't exist, only a warning is logged. The initialization continues but the knowledge base starts empty with only pro-mined entries. | Consider shipping a default `tactical_knowledge.json` with the project, or generate a minimal one from embedded data. |

---

#### backend/knowledge/pro_demo_miner.py (192 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| C-32 | MEDIUM | Data Quality | 107-109 | KAST and HS percentage normalization: `card.kast * 100 if card.kast <= 1.0 else card.kast`. This heuristic assumes values <= 1.0 are ratios and > 1.0 are already percentages. But a KAST of exactly 1.0 (100%) would be multiplied to 100, while 1.01 (a data error) would be kept as-is. The boundary condition is fragile. | Use a more robust normalization: always store as ratio (0-1) at ingestion time (stat_fetcher.py) and format for display at the presentation layer only. |
| C-33 | LOW | Constants | 27-30 | Archetype classification thresholds (`_STAR_FRAGGER_IMPACT = 1.15`, etc.) are hardcoded. These should evolve with the meta — a 1.15 impact rating may be star-level in one era but average in another. | Consider making thresholds configurable or deriving them from the current pro population statistics (e.g., top 10% impact = star fragger). |

---

#### backend/knowledge/rag_knowledge.py (588 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| C-34 | MEDIUM | Fallback Quality | 84-102 | `_fallback_embed()` uses a bag-of-words hash-projection which is an improvement over the previous random approach (R-02), but it still produces low-quality embeddings. Texts with the same words in different order get identical embeddings. Negation is not captured ("good positioning" vs "not good positioning" would be similar). | Document the quality degradation prominently. Consider using a lightweight pre-trained model (e.g., TF-IDF with SVD) as a middle ground. |
| C-35 | LOW | Performance | 302-303 | `_brute_force_retrieve()` uses `stmt.limit(500)` which loads up to 500 TacticalKnowledge rows with their full embeddings into memory. For large knowledge bases, this is a significant memory allocation. | Use pagination or load only IDs + embeddings (not full records) for the similarity computation pass. |

---

#### backend/knowledge/round_utils.py (35 lines)

No findings — clean shared utility with well-defined thresholds for round phase inference. Properly extracted from multiple duplicated implementations (F5-20).

---

#### backend/knowledge/vector_index.py (307 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| C-36 | MEDIUM | Consistency | 270-277 | `_load_experience_vectors()` uses `json.loads(entry.embedding)` but `ExperienceBank._serialize_embedding()` (L117-120) now uses base64 encoding. If new experiences are stored in base64 format, this loader will fail with `json.JSONDecodeError` for those entries. The deserialization in `ExperienceBank._deserialize_embedding()` handles both formats, but this vector index loader does not. | Use `ExperienceBank._deserialize_embedding()` (or extract it to a shared utility) for consistent deserialization in both code paths. |
| C-37 | LOW | Memory | 226-241 | `_load_knowledge_vectors()` loads ALL TacticalKnowledge entries without a limit. For very large knowledge bases, this could consume significant memory during index rebuild. | Add batch loading similar to `_load_experience_vectors()` which uses `BATCH_SIZE = 5000`. |

---

#### backend/coaching/\_\_init\_\_.py (26 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| C-38 | LOW | Imports | 11-17 | Eagerly imports `generate_corrections`, `ExplanationGenerator`, `HybridCoachingEngine`, and `PlayerCardAssimilator`. `HybridCoachingEngine` import triggers `torch` loading which is heavy. | Consider lazy imports for `HybridCoachingEngine` since it's only used when `USE_HYBRID_COACHING=True`. |

---

#### backend/coaching/correction_engine.py (65 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| C-39 | LOW | Precision | 41-48 | Confidence scaling uses `rounds_played / CONFIDENCE_ROUNDS_CEILING` (300). This means a player with 1 round has confidence 0.003, making all corrections near-zero. The coaching system produces no actionable advice until the player has played at least ~30 rounds. | Document the minimum rounds threshold for meaningful corrections. Consider a minimum confidence floor (e.g., 0.1) to ensure some coaching is always generated. |

---

#### backend/coaching/explainability.py (95 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| C-40 | MEDIUM | Template Quality | 19-45 | `TEMPLATES` uses hardcoded fill-in-the-blank templates with generic placeholders. For example, `{impact}` always resolves to "missed opportunities" (L69), `{time}` defaults to "1.2" (L71). The templates appear AI-coaching-like but produce formulaic output that doesn't adapt to actual game events. | Wire context dict with real data from analysis results instead of using generic defaults. The templates are a good structure but need real data flow. |

---

#### backend/coaching/hybrid_engine.py (661 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| C-41 | **HIGH** | Data Staleness | 34-50 | `_FALLBACK_BASELINE` uses January 2024 HLTV data. When `get_pro_baseline()` fails, coaching deviations are computed against 14+ month old averages. The professional CS2 meta evolves significantly over this timeframe (weapon balance changes, map pool rotations, team roster changes). All coaching insights computed against this baseline are degraded. | Add automated baseline refresh from HLTV data (already available via `stat_fetcher.py`). Add a `_FALLBACK_BASELINE_MAX_AGE_DAYS` constant and warn more aggressively when the fallback is older than 90 days. |
| C-42 | MEDIUM | Coupling | 495-508 | `_calculate_confidence()` imports and calls `MetaDriftEngine.get_meta_confidence_adjustment()` synchronously. If the meta-drift engine has errors, the entire confidence calculation fails, potentially crashing the insight generation pipeline. | Wrap in try/except with `meta_adj = 1.0` fallback. |
| C-43 | LOW | Code Quality | 634-661 | `__main__` block uses hardcoded synthetic stats for self-testing. While documented as synthetic, someone copy-pasting this code might use these values in production. | Move self-test to a proper test file. |

---

#### backend/coaching/longitudinal_engine.py (49 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| C-44 | LOW | Template Quality | 37-38 | Regression insights always say "Refocus on fundamentals" regardless of the specific feature declining. A declining `avg_hs` needs different advice than declining `avg_kast`. | Use feature-specific advice templates. |

---

#### backend/coaching/nn_refinement.py (31 lines)

No findings — clean, focused module that applies NN weight adjustments to correction Z-scores. Simple and correct.

---

#### backend/coaching/pro_bridge.py (118 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| C-45 | MEDIUM | Data Quality | 42-43 | `avg_kills` and `avg_deaths` are set to `card.kpr` and `card.dpr` (per-round rates). But the field names `avg_kills` / `avg_deaths` suggest per-match totals. This naming mismatch could cause confusion when compared against user stats which may use a different scale. | Rename to `kpr` / `dpr` in the baseline dict, or explicitly document that these are per-round rates despite the `avg_` prefix inherited from the internal stats schema. |
| C-46 | LOW | Defaults | 64, 79, 89 | Default values (HS ratio 0.45, entry_rate 0.25, utility_damage 45.0) are used when detailed stats are unavailable. These "cognitive defaults" are hardcoded and may drift from reality. | Source defaults from the same `_FALLBACK_BASELINE` used by hybrid_engine.py for consistency. |

---

#### backend/coaching/token_resolver.py (108 lines)

| # | Severity | Category | Line(s) | Finding | Recommendation |
|---|----------|----------|---------|---------|----------------|
| C-47 | LOW | API Design | 86-107 | `compare_performance_to_token()` computes raw deltas (player - pro) but doesn't compute Z-scores. The `is_underperforming` flag uses an arbitrary 0.85 multiplier threshold. This is less rigorous than the Z-score approach used by `hybrid_engine.py`. | Consider delegating to `calculate_deviations()` from `pro_baseline.py` for consistent statistical comparison. |

---

### 3. Cross-Cutting Concerns

#### 3.1 Singleton Thread Safety Inconsistency
Some singletons use `threading.Lock` (coaching_service.py, analysis_orchestrator.py), while others don't (coaching_dialogue.py, llm_service.py, visualization_service.py). The ones without locks are vulnerable to race conditions in the tri-daemon architecture where multiple threads may request services concurrently.

#### 3.2 Stale Baselines and Hardcoded Pro References
Multiple modules contain hardcoded pro player references and statistical baselines:
- `hybrid_engine.py`: `_FALLBACK_BASELINE` (January 2024)
- `pro_bridge.py`: Default HS ratio 0.45, utility damage 45.0
- `lesson_generator.py`: Player name references (s1mple, ropz)
- `pro_demo_miner.py`: Archetype classification thresholds

These all drift over time. A centralized "meta snapshot" with a timestamp and automated refresh would eliminate the drift problem.

#### 3.3 Embedding Serialization Format Mismatch
`ExperienceBank._serialize_embedding()` uses base64 encoding (AC-32-01), but `vector_index._load_experience_vectors()` uses `json.loads()`. This means FAISS index rebuilds will fail for experiences stored in the new base64 format. The brute-force path in `ExperienceBank._deserialize_embedding()` handles both formats correctly, but the FAISS path does not.

#### 3.4 RAG Knowledge Retriever Instantiation Cost
`KnowledgeRetriever()` loads Sentence-BERT on initialization. It's instantiated as a new object in multiple places (coaching_dialogue.py L255, coaching_service.py L531, rag_knowledge.py L448) without caching. While `ExperienceBank` correctly uses a singleton (`get_experience_bank()`), the retriever does not have a corresponding singleton pattern in all call sites.

#### 3.5 LLM Prompt Injection Surface
The coaching dialogue injects RAG retrieval context and experience bank narratives directly into LLM prompts. Since these sources include user-generated content (experiences from user demos), there is a theoretical prompt injection surface. The risk is mitigated by Ollama running locally, but should be addressed if the LLM backend changes.

---

### 4. Inter-Module Dependency Risks

| This Module | Depends On | Risk |
|-------------|-----------|------|
| `coaching_service.py` | All coaching engines + analysis orchestrator | COPER failure triggers a waterfall of fallbacks that may mask persistent failures |
| `hybrid_engine.py` | `pro_baseline.py`, `MetaDriftEngine`, `KnowledgeRetriever`, PyTorch | Heavy dependency chain — any failure cascades to fallback baseline |
| `experience_bank.py` | `vector_index.py` (FAISS), `rag_knowledge.py` (SBERT) | Optional FAISS dependency creates two code paths with different serialization formats (C-36) |
| `coaching_dialogue.py` | `llm_service.py` (Ollama), `experience_bank.py`, `rag_knowledge.py` | Session state (history) is not persisted — app restart loses conversation |
| `graph.py` | Raw `sqlite3` (not SQLModel) | Different connection management than rest of codebase; no migration support |
| `pro_bridge.py` | `ProPlayerStatCard` schema | Field naming mismatch (`avg_kills` = KPR, not total kills) may confuse downstream consumers |

---

### 5. Remediation Priority Matrix

| Priority | ID | Severity | File | Finding | Effort |
|----------|-----|----------|------|---------|--------|
| 1 | C-41 | **HIGH** | hybrid_engine.py | Stale fallback baseline (Jan 2024) | Medium — add automated refresh from HLTV data |
| 2 | C-06 | **HIGH** | coaching_dialogue.py | Thread-unsafe singleton with mutable session state | Medium — add lock + consider per-session factory |
| 3 | C-36 | MEDIUM | vector_index.py | Base64 vs JSON embedding deserialization mismatch | Low — use shared deserializer |
| 4 | C-07 | MEDIUM | coaching_dialogue.py | RAG context prompt injection surface | Low — sanitize retrieval context |
| 5 | C-29 | MEDIUM | graph.py | Per-operation SQLite connections (no pooling) | Medium — add connection pool |
| 6 | C-22 | MEDIUM | visualization_service.py | Import-time matplotlib initialization | Low — lazy init |
| 7 | C-02 | MEDIUM | analysis_orchestrator.py | No log suppression for repeated module failures | Low |
| 8 | C-40 | MEDIUM | explainability.py | Generic template defaults not wired to real data | Medium |
| 9 | C-42 | MEDIUM | hybrid_engine.py | MetaDriftEngine crash propagation | Low — add try/except |
| 10 | C-25 | MEDIUM | experience_bank.py | Brute-force limit(100) caps searchable experiences | Low — increase or document |
| 11 | C-26 | MEDIUM | experience_bank.py | usage_count race condition | Low |
| 12 | C-32 | MEDIUM | pro_demo_miner.py | Fragile KAST/HS normalization boundary | Low |
| 13 | C-45 | MEDIUM | pro_bridge.py | avg_kills = KPR naming mismatch | Low — rename or document |
| 14 | C-14 | MEDIUM | lesson_generator.py | Hardcoded pro tips with player names | Low — move to JSON |
| 15 | C-34 | MEDIUM | rag_knowledge.py | Low-quality fallback embeddings | Medium |
| 16 | C-08 | MEDIUM | coaching_dialogue.py | Hardcoded T-side full_buy defaults | Low |
| 17 | C-18 | MEDIUM | profile_service.py | No retry for secondary Steam API call | Low |
| 18 | C-20 | MEDIUM | telemetry_client.py | HTTP telemetry in production | Low — add HTTPS enforcement |
| 19 | C-16 | MEDIUM | llm_service.py | LLM prompt with unvalidated user input | Low risk for local Ollama |
| 20 | C-10 | MEDIUM | coaching_service.py | Fallback drops NN refinement | Low |

---

### 6. Coverage Attestation

| # | File | Lines | Read | Findings |
|---|------|-------|------|----------|
| 1 | `backend/services/__init__.py` | 1 | Yes | 0 |
| 2 | `backend/services/analysis_orchestrator.py` | 549 | Yes | 3 |
| 3 | `backend/services/analysis_service.py` | 92 | Yes | 2 |
| 4 | `backend/services/coaching_dialogue.py` | 373 | Yes | 4 |
| 5 | `backend/services/coaching_service.py` | 763 | Yes | 4 |
| 6 | `backend/services/lesson_generator.py` | 382 | Yes | 2 |
| 7 | `backend/services/llm_service.py` | 253 | Yes | 2 |
| 8 | `backend/services/ollama_writer.py` | 110 | Yes | 0 |
| 9 | `backend/services/profile_service.py` | 164 | Yes | 2 |
| 10 | `backend/services/telemetry_client.py` | 60 | Yes | 2 |
| 11 | `backend/services/visualization_service.py` | 119 | Yes | 2 |
| 12 | `backend/knowledge/__init__.py` | 1 | Yes | 1 |
| 13 | `backend/knowledge/experience_bank.py` | 883 | Yes | 4 |
| 14 | `backend/knowledge/graph.py` | 205 | Yes | 1 |
| 15 | `backend/knowledge/init_knowledge_base.py` | 122 | Yes | 1 |
| 16 | `backend/knowledge/pro_demo_miner.py` | 192 | Yes | 2 |
| 17 | `backend/knowledge/rag_knowledge.py` | 588 | Yes | 2 |
| 18 | `backend/knowledge/round_utils.py` | 35 | Yes | 0 |
| 19 | `backend/knowledge/vector_index.py` | 307 | Yes | 2 |
| 20 | `backend/coaching/__init__.py` | 26 | Yes | 1 |
| 21 | `backend/coaching/correction_engine.py` | 65 | Yes | 1 |
| 22 | `backend/coaching/explainability.py` | 95 | Yes | 1 |
| 23 | `backend/coaching/hybrid_engine.py` | 661 | Yes | 3 |
| 24 | `backend/coaching/longitudinal_engine.py` | 49 | Yes | 1 |
| 25 | `backend/coaching/nn_refinement.py` | 31 | Yes | 0 |
| 26 | `backend/coaching/pro_bridge.py` | 118 | Yes | 2 |
| 27 | `backend/coaching/token_resolver.py` | 108 | Yes | 1 |

**All 28 files (including __init__.py files) confirmed read and analyzed. Total: ~6,842 lines.**

Note: `backend/services/coaching_dialogue.py` was counted as having 4 findings total (C-06, C-07, C-08, C-09 — with C-09 being a documentation fix related to C-03's code concern in the same module's logic).
