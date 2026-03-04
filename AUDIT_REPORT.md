# Audit Sistematico Completo — Macena CS2 Analyzer
# Data: 2026-03-04
# Totale file: 391 Python files, ~88.600 LOC
# Metodo: Lettura batch per batch, ogni file ispezionato

## Legenda Severità
- **CRITICAL** — Bug che impedisce il funzionamento, data corruption, security hole
- **HIGH** — Bug logico, race condition, comportamento scorretto
- **MEDIUM** — Code smell, pattern fragile, manutenzione problematica
- **LOW** — Style, naming, minor improvement
- **OK** — File ispezionato, nessun problema trovato

---

# BATCH 1: `core/` (17 file, 2765 LOC)

| File | Lines | Verdict | Crit | High | Med | Low |
|------|-------|---------|------|------|-----|-----|
| `__init__.py` | 1 | OK | 0 | 0 | 0 | 0 |
| `app_types.py` | 47 | OK | 0 | 0 | 0 | 0 |
| `demo_frame.py` | 151 | ISSUES | 0 | 0 | 1 | 0 |
| `frozen_hook.py` | 17 | ISSUES | 0 | 0 | 2 | 0 |
| `map_manager.py` | 88 | OK | 0 | 0 | 0 | 0 |
| `playback_engine.py` | 247 | ISSUES | 0 | 0 | 1 | 2 |
| `registry.py` | 43 | ISSUES | 0 | 0 | 1 | 1 |
| `spatial_data.py` | 388 | ISSUES | 0 | 0 | 2 | 1 |
| `playback.py` | 116 | ISSUES | 0 | 0 | 2 | 1 |
| `spatial_engine.py` | 93 | OK | 0 | 0 | 0 | 0 |
| `constants.py` | 2 | OK | 0 | 0 | 0 | 0 |
| `logger.py` | 13 | OK | 0 | 0 | 0 | 0 |
| `lifecycle.py` | 146 | ISSUES | 0 | 0 | 2 | 1 |
| `asset_manager.py` | 255 | ISSUES | 0 | 0 | 1 | 1 |
| `config.py` | 359 | ISSUES | 0 | 1 | 3 | 1 |
| `localization.py` | 334 | ISSUES | 0 | 0 | 0 | 2 |
| `session_engine.py` | 465 | ISSUES | 0 | 1 | 1 | 3 |

### Top Issues core/:
1. **HIGH session_engine.py:233** — Scanner daemon legge `ingest_status` (campo Digester) invece di `hltv_status` (campo Hunter). Lo scanner non si attiva mai se il Digester non imposta il suo stato a "Scanning". Bug cross-wired dei daemon.
2. **HIGH config.py:201** — `load_user_settings()` chiamato all'import time. Se keyring fallisce, `RuntimeError` crasha l'intera app prima che qualsiasi codice parta.
3. **MEDIUM spatial_data.py:153-156** — `__init__` e `reload()` non thread-safe nonostante `__new__` abbia il lock.
4. **MEDIUM demo_frame.py:87** — `NadeState(frozen=True)` contiene `trajectory: List[tuple]` mutabile. Rompe il contratto di immutabilità.
5. **MEDIUM playback_engine.py** — `InterpolatedPlayerState` manca il campo `has_defuser`, perso durante l'interpolazione.

---

# BATCH 2: `backend/analysis/` (11 file, 3474 LOC)

| File | Lines | Verdict | Crit | High | Med | Low |
|------|-------|---------|------|------|-----|-----|
| `__init__.py` | 95 | OK | 0 | 0 | 0 | 0 |
| `belief_model.py` | 440 | ISSUES | 0 | 0 | 2 | 2 |
| `blind_spots.py` | 213 | ISSUES | 0 | 1 | 1 | 1 |
| `deception_index.py` | 221 | ISSUES | 0 | 0 | 2 | 1 |
| `engagement_range.py` | 437 | OK | 0 | 0 | 0 | 0 |
| `entropy_analysis.py` | 150 | ISSUES | 0 | 0 | 1 | 1 |
| `game_tree.py` | 478 | ISSUES | 0 | 1 | 1 | 2 |
| `momentum.py` | 206 | ISSUES | 0 | 0 | 1 | 1 |
| `role_classifier.py` | 556 | ISSUES | 0 | 0 | 1 | 2 |
| `utility_economy.py` | 388 | ISSUES | 0 | 0 | 2 | 2 |
| `win_probability.py` | 290 | ISSUES | 0 | 0 | 1 | 2 |

### Top Issues backend/analysis/:
1. **HIGH game_tree.py:348-350** — Il nodo "min" è dead code. L'albero non produce mai nodi min nonostante la classe si chiami "Expectiminimax". L'algoritmo è in realtà un Expectimax.
2. **HIGH blind_spots.py:49** — `game_tree: Optional[object]` è inutile come type hint. Causerà `AttributeError` a runtime se passato un oggetto sbagliato.
3. **MEDIUM utility_economy.py:249** — Round 13 (pistol del secondo half MR12) trattato come "overtime" invece di pistol round. Bug logico concreto che produce raccomandazioni economiche sbagliate.
4. **MEDIUM deception_index.py:107,178** — Flash bait rate e sound deception conflano gioco scadente con deception intenzionale. Metriche sistematicamente fuorvianti.

---

# BATCH 3: `backend/storage/` (14 file, ~3300 LOC)

| File | Lines | Verdict | Crit | High | Med | Low |
|------|-------|---------|------|------|-----|-----|
| `__init__.py` | 0 | OK | 0 | 0 | 0 | 0 |
| `backup_manager.py` | 218 | ISSUES | 1 | 0 | 2 | 2 |
| `database.py` | 175 | ISSUES | 0 | 0 | 2 | 2 |
| `db_backup.py` | 204 | ISSUES | 0 | 0 | 2 | 2 |
| `db_migrate.py` | 113 | ISSUES | 0 | 0 | 2 | 1 |
| `db_models.py` | 584 | ISSUES | 0 | 0 | 2 | 3 |
| `maintenance.py` | 53 | ISSUES | 0 | 1 | 1 | 1 |
| `match_data_manager.py` | 722 | ISSUES | 0 | 2 | 2 | 1 |
| `remote_file_server.py` | 107 | ISSUES | 0 | 1 | 1 | 2 |
| `stat_aggregator.py` | 100 | ISSUES | 0 | 0 | 1 | 1 |
| `state_manager.py` | 165 | ISSUES | 0 | 1 | 3 | 1 |
| `storage_manager.py` | 250 | ISSUES | 0 | 0 | 1 | 3 |
| `datasets/__init__.py` | 0 | OK | 0 | 0 | 0 | 0 |
| `models/__init__.py` | 0 | OK | 0 | 0 | 0 | 0 |

### Top Issues backend/storage/:
1. **CRITICAL backup_manager.py:65** — SQL via f-string formatting (`VACUUM INTO '{target_path_safe}'`). Manca `text()` wrapper per SQLAlchemy 2.x.
2. **HIGH match_data_manager.py:222-262** — Race condition nella cache engine (nessun lock). I thread del Tri-Daemon possono creare engine duplicati o rimuovere engine in uso.
3. **HIGH match_data_manager.py:597-633** — Singleton `get_match_data_manager()` senza thread safety (a differenza di `get_db_manager()` che ha il lock).
4. **SISTEMICO** — `session.commit()` espliciti dentro il context manager auto-committing (`get_session()`). Trovato in `state_manager.py`, `stat_aggregator.py`, `maintenance.py`. Rompe l'atomicità della transazione.
5. **SISTEMICO** — Raw `sqlite3.connect()` in `db_backup.py` e `db_migrate.py` bypassa le pragma hooks di `DatabaseManager` (WAL, busy_timeout, synchronous).

# BATCH 5: `backend/services/` + `backend/coaching/` (19 file)

### CRITICAL + HIGH:
1. **CRITICAL profile_service.py:39-48** — `PlayerProfile` costruito con campi (`steam_id`, `steam_level`, `faceit_id`, ecc.) che NON ESISTONO sul modello SQLModel. `sync_all_external_data()` completamente rotto a runtime.
2. **HIGH coaching_dialogue.py:297-307** — `_build_chat_messages` fa `self._history[:-1]` che DROPPA sempre l'ultimo messaggio. L'LLM non vede mai la sua ultima risposta.
3. **HIGH hybrid_engine.py:477-488** — `_calculate_confidence` non passa `map_name` disponibile. Usa drift globale.

### Other MEDIUM:
- `analysis_orchestrator.py:66` — `belief_estimator` mai usato (dead code)
- `analysis_orchestrator.py:149-154` — `_analyze_momentum` shadowa il tracker di `__init__`
- `coaching_service.py:443-447` — Fallback dopo hybrid failure produce ZERO output
- `visualization_service.py:22-24` — Radar chart confronta valori disallineati se dict hanno ordine diverso
- `correction_engine.py:48` — `weighted_z` non incorpora `importance`

# BATCH 6: `backend/nn/` (41 file, ~8000+ LOC)

### CRITICAL:
1. **CRITICAL persistence.py:81-82** — Silent failure: ritorna modello con pesi RANDOM su eccezioni non-RuntimeError.
2. **CRITICAL train_pipeline.py:6,26** — `OUTPUT_DIM` mai importato. `NameError` a runtime. `run_training()` completamente rotta.

### HIGH:
3. **HIGH rap_coach/memory.py:73-76** — Shape mismatch Hopfield/LTC per addizione residuale.
4. **HIGH coach_manager.py:820-821** — Scale factor 1000 vs canonico 500. Ghost overlay 2x sbagliato.
5. **HIGH factory.py:81** — `hidden_dim=64` vs config default 128. Incompatibilità checkpoint.
6. **HIGH training_orchestrator.py:288-300** — JEPA validation collassa 5 negativi a 1. Contrastive loss degenera.

### MEDIUM:
- `chronovisor_scanner.py:219-221` — Value estimate shape (1,1) ma itera sulla finestra
- `layers/superposition.py:22` — Pesi `randn(std=1.0)` invece di Kaiming (11x troppo grandi)
- `skill_model.py:40-41` — `val=0.0` trattato come "unavailable"

# BATCH 7: `ingestion/` + `data_sources/` + `knowledge/` (50 file)

### CRITICAL:
1. **CRITICAL downloader.py:27-45** — `BrowserManager.__exit__` mancante. Playwright browser LEAKS su ogni uso.
2. **CRITICAL demo_parser.py:175-176** — `_find_player_column` non definita. `NameError` → `kill_std`/`adr_std` sempre 0.0.
3. **CRITICAL rag_knowledge.py:450** — `_infer_round_phase` non definita dopo estrazione. `NameError` a runtime.
4. **CRITICAL backend/ingestion/hltv_orchestrator.py:1** — Import da modulo legacy `fetch_hltv_stats`. Duplicato stale.

### HIGH:
5. **HIGH demo_loader.py:124-125** — Pass 1 failure swallowed silently. Dati degradati cached come autoritativi.
6. **HIGH demo_loader.py:230,262** — Range esplosion dei tick nade. Milioni di entries, memory pressure.
7. **HIGH pro_ingest.py:42** — `player_name="ProPlayer"` hardcoded. Tutti gli stat pro mergiati in un record.
8. **HIGH pro_demo_miner.py:98-120** — Knowledge "mining" è interamente FABBRICATA da metadata. Nessuna analisi demo reale.
9. **HIGH backend/ingestion/hltv_orchestrator.py:57** — `data.pop()` muta dict potenzialmente condiviso.
10. **HIGH watcher.py:6** — `sqlalchemy.select` usato con `sqlmodel.session.exec()`. Mix fragile.

### MEDIUM:
- `csv_migrator.py:185-191` — Riferisce colonne CSV inesistenti. Tutte le righe falliscono.
- `hltv_api_service.py:278` — Regex HS% richiede punto decimale, fallisce su interi come "50%"
- `collectors/players.py:62` — `_is_profile_valid` non checka `resp is None`

# BATCH 8: `apps/desktop_app/` (16 file, ~4000 LOC)

### HIGH:
1. **HIGH tactical_viewmodels.py:247** — `NameError` a runtime: lambda cattura `e` che Python 3 cancella dopo except block. Crash quando `Clock.schedule_once` la esegue.
2. **HIGH help_screen.py:39,43** — `self.ids.content_label` senza null guard. Crash se KV ids mancanti.

### MEDIUM:
- `tactical_viewer_screen.py:93` — Event binding accumulato: `bind()` chiamato ogni `on_enter()` senza `unbind` in `on_leave()`. Callback N volte dopo N entrate.
- `spatial_debugger.py:86-87` — Division by zero: `width`/`height` può essere 0 durante init.
- `ghost_pixel.py:106-107` — Stessa divisione per zero.
- `tactical_map.py:331` — Tickrate 64 hardcoded per finestra visibilità nade.
- `tactical_map.py:477-478` — No check che trajectory points abbiano 3 elementi.
- `wizard_screen.py:152-157` — `build_demo_path()` è stub che salta a "finish".
- `wizard_screen.py:347-349` — Error dialog senza bottone dismiss.

# BATCH 9: `main.py` + top-level scripts (9 file, 3793 LOC)

### CRITICAL:
1. **CRITICAL main.py:310** — `PlayerProfile` usato dopo chiusura sessione → `DetachedInstanceError`. Profile loading fallisce silenziosamente.
2. **CRITICAL main.py:446** — Mutable class-level default `_last_completed_tasks = []` condiviso.

### HIGH:
3. **HIGH main.py:1320-1332** — `select_path` rifiuta file, ma `open_file_manager_direct` configura il file manager per file selection. **Upload demo utente completamente rotto.**
4. **HIGH main.py:1548/1587/1600** — `parsing_dialog` mai resettato a `None` dopo dismiss. Dopo il primo parse, tutti i successivi falliscono silenziosamente.
5. **HIGH main.py:810** — `"Section 2 omitted for brevity"` È NEL CODICE PRODUZIONE. `knowledge_ticks` e `active_tasks` sempre 0/vuoti.
6. **HIGH main.py:495** — `selection_button=False` non è proprietà documentata di MDFileManager 2.x.
7. **HIGH run_ingestion.py:311** — `limit` accettato ma MAI usato. Throttling ingestion non funzionale.
8. **HIGH run_ingestion.py:925** — MD5 ridotto a 10^9 per match_id. Alta probabilità collisione con ~31k demo.
9. **HIGH run_worker.py:11-12** — `PROJECT_ROOT` sbagliato (package dir, non project root).
10. **HIGH fetch_hltv_stats.py:214-224** — `_parse_clutches` è stub che ritorna dati FABBRICATI.

### MEDIUM:
- `main.py:788-791` — Precedenza operatori ambigua nel ternary
- `main.py:1652` — `atexit.register` accumulato ad ogni chiamata `show_skill_radar()`
- `hltv_sync_service.py:89` — Dopo dormant sleep, esce completamente senza retry
- `hltv_sync_service.py:123` — `time.sleep(60)` ignora stop signal
- `run_ingestion.py:567-575` — State lookup eviction cancella prima metà, non LRU

# BATCH 10: root `tools/`, `tests/`, `alembic/`, root scripts

### HIGH — Migrazioni Alembic:
1. **HIGH** 4 migrazioni (`19fcff36ea0a`, `609fed4b4dce`, `8c443d3d9523`, `c8a2308770e5`) aggiungono colonne NOT NULL SENZA `server_default`. Su SQLite con righe esistenti, la migrazione FALLISCE.
2. **HIGH** `5d5764ef9f26` — 3 blocchi `except Exception: pass` che ingoiano tutti gli errori. `downgrade()` è vuota → migrazione non reversibile.
3. **HIGH** `b609a11e13cc` — `drop_table("ingestiontask_archive")` senza check esistenza.

### MEDIUM:
- `headless_validator.py:2260-2261` — Doppio path prefix causa integrity hash check a fallire sempre.
- `check_db_status.py:40` — Status `"completed"` dovrebbe essere `"complete"`. Count sempre 0.
- `7a30a0ea024e` — `if_not_exists=True` non supportato da Alembic standard.
- `schema.py:67,111,155` — SQL via f-string. Mitigato da fonti trusted ma pattern pericoloso.
- `schema.py:169-170` — `_transfer_table()` non trasferisce mai dati realmente (stub).
- `schema.py:216-217` — Bare `except:` senza tipo eccezione.
- `hflayers.py:59` — `memory_slots=512` hardcoded, non configurabile.

# BATCH 11: Test files (19 file della prima metà)

### SISTEMICO — `sys.exit(2)` Venv Guard (HIGH, 13 file):
I seguenti file contengono un `sys.exit(2)` a livello modulo che UCCIDE pytest collection su ambienti senza venv:
`conftest.py`, `test_analysis_engines.py`, `test_analysis_engines_extended.py`, `test_analysis_gaps.py`, `test_analysis_orchestrator.py`, `test_auto_enqueue.py`, `test_baselines.py`, `test_chronovisor_highlights.py`, `test_chronovisor_scanner.py`, `test_coach_manager_flows.py`, `test_coaching_dialogue.py`, `test_coaching_engines.py`

**Impatto:** Su CI pipeline con system Python, Docker, o conda, l'intera test suite esce silenziosamente con code 2. Fix: `pytest.skip("Not in venv")`.

### Test che passano SEMPRE (never-fail):
- `test_analysis_engines_extended.py:313` — `or True` rende l'assertion vacua
- `test_coach_manager_tensors.py:138-149` — try/except + pass = test mai fallisce
- `test_system_regression.py:8-31` — `hasattr` su oggetto Python sempre True per campi dichiarati

### Test che operano su dati PRODUZIONE:
- `test_auto_enqueue.py` — R/W su `database.db` reale
- `test_system_regression.py` — Query su DB reale all'import
- `test_e2e.py` — `init_database()` su DB reale, muta config reale
- `test_functional.py` — Muta config file su disco

### Other:
- `test_e2e.py:57-60` / `test_functional.py:28-31` — Cleanup mancante: se `original_name` è None, il valore test resta permanente nella config
- `test_coach_manager_flows.py:575-595` — Assertion overly-permissive che maschera un bug reale (campi inesistenti su PlayerProfile)

---

# BATCH 12: `tools/`, `observability/`, `reporting/`, `backend/control|onboarding|progress|reporting|server.py` (49 file)

### HIGH:
1. **HIGH tools/project_snapshot.py:151** — SQL injection via f-string senza bracket-escaping. Table names da lista hardcoded, ma pattern viola la disciplina parameterized.

### MEDIUM:
2. **MEDIUM backend/onboarding/new_user_flow.py:91** — `_count_user_demos()` conta TUTTI i demo nel DB senza filtrare per `user_id`. Count inflato → onboarding status sbagliato.
3. **MEDIUM backend/reporting/analytics.py:136,171,237,298** — `logger.error(..., error=str(e))` — `error=` non è un kwarg valido di stdlib logging. Le eccezioni non vengono loggate.
4. **MEDIUM backend/reporting/analytics.py:22,351** — `AnalyticsEngine()` istanziato a module-level → connessione DB all'import time. Crash se DB non inizializzato.
5. **MEDIUM reporting/report_generator.py:79-80** — Dati di morte raccolti ma MAI analizzati. Il report contiene testo placeholder hardcoded.
6. **MEDIUM backend/control/console.py:211-216** — Singleton `Console` può restare in stato parzialmente inizializzato se `__init__` fallisce. Chiamate successive vedono istanza rotta.
7. **MEDIUM backend/progress/trend_analysis.py:5-8** — `compute_trend()` senza validazione input: crash su lista vuota o singolo elemento.
8. **MEDIUM tools/db_inspector.py:89** — SQL con f-string: `f"SELECT COUNT(*) FROM [{t}]"`. Sorgente trusted ma pattern pericoloso.
9. **MEDIUM tools/Goliath_Hospital.py:2164** — Flag `--department` definito in argparse ma mai wired a esecuzione selettiva.
10. **MEDIUM tools/Ultimate_ML_Coach_Debugger.py:39** — `get_db_manager()` chiamato senza `init_database()` preventivo. Crash standalone.
11. **MEDIUM tools/user_tools.py:267-269** — Accesso a `state.hltv_status`, `state.ingest_status`, `state.ml_status` fragile se schema migra.
12. **MEDIUM tools/user_tools.py:279** — `psutil.disk_usage('/')` su Windows tecnicamente scorretto.
13. **MEDIUM tools/brain_verification/_common.py:253-264** — `get_db_session_or_none()` ritorna sessione fuori da context manager. Resource leak potenziale.
14. **MEDIUM reporting/visualizer.py:21** — Path relativo hardcoded `output_dir="reports/assets"`.
15. **MEDIUM backend/server.py:37-38** — Mock fallback: se import fallisce, endpoints accettano dati ma senza DB. Degradazione silente.

### LOW (27 totali): Vari pattern minori — logging f-string, broad `except Exception`, naive datetime senza timezone, `shell=True` in build tools (locale).

### File OK (25 su 49): `__init__.py` files, `brain_verify.py`, `context_gatherer.py`, `dead_code_detector.py`, `demo_inspector.py`, `dev_health.py`, `headless_validator.py`, `sync_integrity_manifest.py`, `ui_diagnostic.py`, `logger_setup.py`, `sentry_setup.py`, `observability/__init__.py`, `reporting/__init__.py`, `sec01-sec16` (15 sezioni brain_verification, tranne sec07).

---

# BATCH 4: `backend/processing/` (26 file, 5186 LOC)

| File | Lines | Verdict | Crit | High | Med | Low |
|------|-------|---------|------|------|-----|-----|
| `__init__.py` | 1 | OK | 0 | 0 | 0 | 0 |
| `connect_map_context.py` | 116 | ISSUES | 0 | 0 | 1 | 1 |
| `cv_framebuffer.py` | 183 | OK | 0 | 0 | 0 | 0 |
| `data_pipeline.py` | 236 | ISSUES | 0 | 1 | 2 | 0 |
| `external_analytics.py` | 159 | ISSUES | 0 | 1 | 2 | 0 |
| `heatmap_engine.py` | 296 | OK | 0 | 0 | 1 | 0 |
| `player_knowledge.py` | 527 | ISSUES | 0 | 0 | 1 | 1 |
| `round_stats_builder.py` | 519 | ISSUES | 0 | 0 | 2 | 0 |
| `state_reconstructor.py` | 92 | OK | 0 | 0 | 0 | 0 |
| `tensor_factory.py` | 697 | ISSUES | 0 | 0 | 1 | 2 |
| `baselines/meta_drift.py` | 125 | ISSUES | 0 | 0 | 1 | 1 |
| `baselines/nickname_resolver.py` | 129 | ISSUES | 0 | 1 | 1 | 0 |
| `baselines/pro_baseline.py` | 485 | ISSUES | 0 | 0 | 1 | 3 |
| `baselines/role_thresholds.py` | 268 | ISSUES | 0 | 0 | 1 | 3 |
| `feature_engineering/__init__.py` | 30 | OK | 0 | 0 | 0 | 0 |
| `feature_engineering/base_features.py` | 189 | ISSUES | 0 | 0 | 1 | 1 |
| `feature_engineering/kast.py` | 162 | OK | 0 | 0 | 0 | 0 |
| `feature_engineering/rating.py` | 178 | ISSUES | 0 | 0 | 1 | 1 |
| `feature_engineering/role_features.py` | 228 | OK | 0 | 0 | 0 | 0 |
| `feature_engineering/vectorizer.py` | 347 | OK | 0 | 0 | 0 | 2 |
| `validation/dem_validator.py` | 200 | ISSUES | 0 | 0 | 1 | 1 |
| `validation/drift.py` | 176 | OK | 0 | 0 | 0 | 0 |
| `validation/sanity.py` | 116 | ISSUES | 0 | 0 | 1 | 1 |
| `validation/schema.py` | 95 | OK | 0 | 0 | 0 | 0 |

### Top Issues backend/processing/:
1. **HIGH nickname_resolver.py:55** — Exact match DB broken: `_clean()` lowercases tutto ma `ProPlayer.nickname` nel DB ha case originale. L'exact match fallisce sempre, fallback al substring ogni volta.
2. **HIGH data_pipeline.py:67** — Filtro `avg_kills < 3.0` sospetto: se è KPR non filtra nulla; se è total kills, è troppo aggressivo.
3. **HIGH external_analytics.py:77** — Accesso a colonne `["CS Rating", "Win_Rate"]` senza verificare che esistano. KeyError a runtime.
4. **MEDIUM round_stats_builder.py:68** — Off-by-one: `start_tick = ticks[i - 1]` può causare double-count di eventi al confine dei round.
5. **MEDIUM sanity.py:26** — KAST limit 0-100 ma il codebase usa 0-1 ratio. Il sanity check non cattura mai valori anomali per KAST.

---

# BATCH 13: Test files parte 2A (19 file)

### CRITICAL — `sys.exit(2)` venv guard (14 file aggiuntivi):
`test_coaching_service_flows.py`, `test_config_extended.py`, `test_database_layer.py`, `test_db_backup.py`, `test_db_governor_integration.py`, `test_debug_ingestion.py`, `test_dem_validator.py`, `test_demo_format_adapter.py`, `test_demo_parser.py`, `test_detonation_overlays.py`, `test_drift_and_heuristics.py`, `test_experience_bank_db.py`, `test_feature_kast_roles.py`, `test_features.py`

### HIGH:
1. **HIGH test_coaching_service_contracts.py:208-224** — try/except swallows TUTTE le eccezioni tranne `AttributeError`. Test passa sempre se il codice crasha con qualsiasi altro errore.
2. **HIGH test_coaching_service_contracts.py:167** — `assert not ({})` testa un costante Python, non il codice di produzione. Vacuo.
3. **HIGH test_demo_parser.py:64-155** — Intera classe `TestRatingFormulas` (6 test) calcola formule inline senza importare codice di produzione. Test vacui.
4. **HIGH test_coaching_service_flows.py:63-79** — Fixture `coaching_service` esce dal `with patch(...)` prima di ritornare `svc`. Le patch sono già rimosse quando i test usano il servizio.
5. **HIGH test_coaching_service_contracts.py:276-289** — Cleanup singleton senza try/finally.

### MEDIUM:
- `test_drift_and_heuristics.py:247-250` — `assert X is not None` dopo import riuscito è sempre True.
- `test_detonation_overlays.py:71-122` — 3 test leggono source file come stringhe e cercano substring. Fragili.
- `test_dimension_chain_integration.py:63-68` — TypeError nel forward pass silenziosamente accettato → `assert hasattr(model, "forward")` sempre True.
- `test_config_extended.py:49,170` — Test dipendono dall'esistenza di directory su filesystem reale.

---

# BATCH 14: Test files parte 2B (19 file)

### CRITICAL — `sys.exit(2)` venv guard (16 file aggiuntivi):
`test_game_theory.py`, `test_game_tree.py`, `test_hybrid_engine.py`, `test_integration.py`, `test_jepa_model.py`, `test_knowledge_graph.py`, `test_lifecycle.py`, `test_map_manager.py`, `test_nn_extensions.py`, `test_nn_infrastructure.py`, `test_nn_training.py`, `test_onboarding.py`, `test_onboarding_training.py`, `test_playback_engine.py`, `test_pro_demo_miner.py`, `test_profile_service.py`

### CRITICAL — Test su database di PRODUZIONE:
- `test_hybrid_engine.py:166-203` — Scrive/legge da `database.db` reale.
- `test_onboarding.py:51-66,76-90` — Query su DB reale.
- `test_onboarding_training.py:128-142,148-153` — `init_database()` su DB produzione.
- `test_pro_demo_miner.py:31-49` — Scrive/cancella record in DB reale. Cleanup parziale.
- `test_game_theory.py:198-206` — Query `extract_death_events_from_db()` su DB reale.

### HIGH:
1. **HIGH test_nn_infrastructure.py:155-176** — 6 test assertano solo `model is not None`. Non verificano tipo o parametri.
2. **HIGH test_pro_demo_miner.py:156-172** — `auto_populate_from_pro_demos(limit=3)` processa download REALI, non solo i test-created.
3. **HIGH test_nn_infrastructure.py:170-171** — `ModelFactory.get_model("rap")` senza guard `pytest.importorskip("ncps")`. Crash se ncps non installato.

### MEDIUM:
- `test_model_factory_contracts.py:93-145` — 5 test "expected to FAIL" senza marker `@pytest.mark.xfail`. Indistinguibili da regressioni reali.
- `test_knowledge_graph.py:28-35` — `__new__()` bypassa `__init__`, fragile.
- `test_lifecycle.py:46-49` — Crea mutex OS reale su Windows.

### OK (best practice): `test_persistence_stale_checkpoint.py` — Uso esemplare di `tmp_path`, `monkeypatch`, `patch`.

---

# BATCH 15: Test files parte 2C (18 file + conftest.py)

### CRITICAL — `sys.exit(2)` venv guard (17 file + conftest.py):
`conftest.py` (PEGGIORE — blocca TUTTA la suite), `test_rag_knowledge.py`, `test_rap_coach.py`, `test_round_stats_enrichment.py`, `test_round_utils.py`, `test_security.py`, `test_services.py`, `test_session_engine.py`, `test_skill_model.py`, `test_spatial_and_baseline.py`, `test_spatial_engine.py`, `test_state_reconstructor.py`, `test_tactical_features.py`, `test_temporal_baseline.py`, `test_tensor_factory.py`, `test_trade_kill_detector.py`, `test_training_orchestrator_flows.py`, `test_z_penalty.py`

**Unico file SENZA venv guard:** `test_training_orchestrator_logic.py`

### CRITICAL — Test su database di PRODUZIONE:
- `test_rag_knowledge.py:68,130,228` — `init_database()` e `get_db_manager()` su DB reale. 3 fixture diverse.

### HIGH:
1. **HIGH test_skill_model.py:43-111** — 6 test con assertion dentro `if key in vec:`. Se la chiave è assente, test passa vacuamente.
2. **HIGH test_training_orchestrator_logic.py:76-122** — 3 test ri-implementano la logica di early stopping invece di testare il codice di produzione. Zero copertura reale.
3. **HIGH test_tensor_factory.py:735-752** — 3 test mutano `_factory_instance = None` senza teardown. Singleton corrotto per test successivi.
4. **HIGH test_session_engine.py:399-451** — `_work_available_event` e `_shutdown_event` mutati direttamente senza try/finally.

### MEDIUM:
- `test_state_reconstructor.py:99-112` — Test setta attributi manualmente e li ri-asserta. Tautologico.
- `test_training_orchestrator_logic.py:174` — Virgola dopo `assert_array_equal()` crea una tupla, il messaggio di errore è perso.
- `test_services.py:37-38` — `assert result is None or isinstance(result, list)` troppo permissivo.

---

# BATCH 16: Root `console.py` (1610 righe)

### CRITICAL:
1. **CRITICAL console.py:823** — Double `session.commit()` dentro context manager auto-committing. Rompe atomicità.
2. **CRITICAL console.py:766-776** — File handle leak: `open(spawn_log)` mai chiuso nel processo padre dopo `Popen`.

### HIGH:
3. **HIGH console.py:617** — `DATABASE_URL.replace("sqlite:///", "")` è fragile. Si rompe con query params, `sqlite+pysqlite:///`, ecc.
4. **HIGH console.py:652-668** — API keys visibili come argomenti di processo (`ps aux`).
5. **HIGH console.py:671-677** — `_cmd_set_config` accetta QUALSIASI chiave senza validazione. Injection config arbitraria.
6. **HIGH console.py:816-824** — Race condition tra COUNT e DELETE in `_cmd_maint_clear_queue`.
7. **HIGH console.py:1018-1400** — `TUIRenderer._dirty` non thread-safe.
8. **HIGH console.py:232-255** — `proc.stdout` pipe mai chiusa. Leak su Windows.

### MEDIUM (10):
- `console.py:570-578` — `legacy.keys()` crash se `legacy` è None.
- `console.py:800-806` — `os.walk(PROJECT_ROOT)` traversa `node_modules/`, `.git/`, `.venv/`.
- `console.py:437` — Variabile `flag` assegnata ma mai usata.
- `console.py:909-911` — `f.readlines()` carica intero log in memoria.
- `console.py:621-622` — `sqlite3.connect` con `with` non chiude la connessione.
- `console.py:1339-1344` — Hash XOR dirty detection inaffidabile.
- `console.py:102-104` — JSON log invalido se messaggio contiene virgolette.

### LOW (8): Accesso a attributi privati, exit code fragile, `psutil` senza fallback, sleep bloccanti nel TUI, ecc.

---

# BATCH 17: Root tools/ + tests/forensics/ + root scripts (34 file)

### CRITICAL:
1. **CRITICAL migrate_db.py:189** — SQL via f-string: `ALTER TABLE ... ADD COLUMN {col_name} {col_def}`. Nessuna validazione.
2. **CRITICAL reset_pro_data.py:74,77** — SQL via f-string: `SELECT COUNT(*) FROM [{table}]`, `DELETE FROM [{table}]`. Bracket-quoting non previene injection se nome contiene `]`.
3. **CRITICAL migrate_db.py:118** — SQL via f-string: `PRAGMA table_info({table_name})`. Nessuna validazione.
4. **CRITICAL docs/generate_zh_pdfs.py:16-19,24-28** — Path assoluti hardcoded (`/home/renan/...`, `/media/renan/...`). Script funziona solo sulla macchina dello sviluppatore.

### HIGH:
5. **HIGH reset_pro_data.py:93-164** — 5 connessioni SQLite aperte senza try/finally. Leak se eccezione durante DELETE.
6. **HIGH migrate_db.py:148** — Connessione SQLite aperta fuori da try/finally.
7. **HIGH migrate_db.py:182** — `backup_path.name` crash con `AttributeError` se `create_backup()` ritorna None (race condition).
8. **HIGH dead_code_detector.py:173** — Variabile `r` non definita nel except block se `os.walk` fallisce prima del primo yield.
9. **HIGH verify_csv_ingestion.py:58-59** — Exit code 1 per condizione "skip" (nessun dato). Falso negativo in CI.
10. **HIGH check_db_status.py:23-52** — Query DB a livello modulo (import time). Se importato da test runner, connette a DB produzione.

### MEDIUM (14):
- Import non usati (5 file)
- `verify_chronovisor_real.py:105` — Test che solo controlla `isinstance(x, list)`. Vacuo.
- `verify_reporting.py:60-71` — `MatchReportGenerator(db_manager=None)` testato con nulla.
- `forensic_parser_test.py:17` — Path demo hardcoded relativo.
- `run_full_training_cycle.py:63` — f-string in logging call.
- `db_health_diagnostic.py:49` — `run_query()` accetta SQL raw.

### LOW (9): Guard mancanti, convention breaks, department map incompleta in `goliath.py`.

### OK (11): `audit_binaries.py`, `generate_manifest.py`, `dev_health.py`, `check_failed_tasks.py`, `debug_nade_cols.py`, `debug_parser_fields.py`, `probe_missing_tables.py`, `verify_map_dimensions.py`, `verify_chronovisor_logic.py`, `verify_map_integration.py`, `verify_superposition.py`

---

---

# RIEPILOGO CONSOLIDATO FINALE

## Copertura
- **391 file Python** nel progetto (~88.600 LOC)
- **391/391 file auditati** (100% copertura)
- **17 batch** completati

## Conteggi per Severità (tutti i batch)

| Severità | Conteggio | Note |
|----------|-----------|------|
| **CRITICAL** | ~25 | NameError, SQL injection, data corruption, file leaks, sys.exit(2) in 44+ test file |
| **HIGH** | ~55 | Race conditions, wrong logic, broken features, vacuous tests, resource leaks |
| **MEDIUM** | ~85 | Code smells, fragile patterns, ineffective tests, dead code |
| **LOW** | ~70 | Style, naming, minor improvements |

## Top 30 Bug Più Critici — Ordinati per Impatto

### Tier 1: Bloccanti / Data Corruption / Security (fix IMMEDIATAMENTE)

| # | File:Line | Severità | Descrizione |
|---|-----------|----------|-------------|
| 1 | `conftest.py:22-24` + 44+ test file | CRITICAL | `sys.exit(2)` a import-time uccide l'INTERA pytest suite. Nessun test runnabile in CI/Docker/conda. |
| 2 | `train_pipeline.py:6,26` | CRITICAL | `OUTPUT_DIM` mai importato → `NameError`. `run_training()` completamente rotta. |
| 3 | `persistence.py:81-82` | CRITICAL | Ritorna modello con pesi RANDOM su eccezioni non-RuntimeError. Modello corrotto usato come se fosse valido. |
| 4 | `backup_manager.py:65` | CRITICAL | SQL via f-string (`VACUUM INTO`). Potenziale injection + crash su SQLAlchemy 2.x senza `text()`. |
| 5 | `demo_parser.py:175-176` | CRITICAL | `_find_player_column` non definita → `NameError` → `kill_std`/`adr_std` sempre 0.0. |
| 6 | `rag_knowledge.py:450` | CRITICAL | `_infer_round_phase` non definita dopo estrazione. `NameError` a runtime. |
| 7 | `profile_service.py:39-48` | CRITICAL | `PlayerProfile` costruito con 6+ campi inesistenti. Feature completamente rotta. |
| 8 | `downloader.py:27-45` | CRITICAL | `BrowserManager.__exit__` mancante. Playwright browser LEAKS ogni uso. |
| 9 | `main.py:310` | CRITICAL | `PlayerProfile` usato dopo sessione chiusa → `DetachedInstanceError`. |
| 10 | `console.py:823` | CRITICAL | Double commit in context manager auto-committing. Rompe atomicità. |

### Tier 2: Funzionalità Rotte / Bug Logici Gravi

| # | File:Line | Severità | Descrizione |
|---|-----------|----------|-------------|
| 11 | `session_engine.py:233` | HIGH | Scanner legge campo sbagliato (`ingest_status` vs `hltv_status`). Scanner MAI attivato. |
| 12 | `main.py:1320-1332` | HIGH | Upload demo utente COMPLETAMENTE rotto. `select_path` rifiuta file. |
| 13 | `main.py:1548` | HIGH | `parsing_dialog` mai resettato → tutti i parse dopo il primo falliscono. |
| 14 | `main.py:810` | HIGH | `"Section 2 omitted for brevity"` letteralmente nel codice produzione. |
| 15 | `coaching_dialogue.py:297-307` | HIGH | `_build_chat_messages` droppa l'ultimo messaggio via `[:-1]`. |
| 16 | `pro_ingest.py:42` | HIGH | `player_name="ProPlayer"` hardcoded. TUTTI gli stat pro mergiati in un singolo record. |
| 17 | `pro_demo_miner.py:98-120` | HIGH | Knowledge "mining" interamente FABBRICATA da metadata. Zero analisi demo. |
| 18 | `fetch_hltv_stats.py:214-224` | HIGH | `_parse_clutches` è stub che ritorna dati FABBRICATI/dummy. |
| 19 | `config.py:201` | HIGH | `load_user_settings()` a import-time. Se keyring fallisce → crash intera app. |
| 20 | `console.py:671-677` | HIGH | `_cmd_set_config` accetta qualsiasi chiave senza validazione. Config injection. |

### Tier 3: Race Conditions / Resource Leaks / Test Integrity

| # | File:Line | Severità | Descrizione |
|---|-----------|----------|-------------|
| 21 | `match_data_manager.py:222-262` | HIGH | Race condition nella cache engine. Nessun thread lock. |
| 22 | `console.py:766-776` | CRITICAL | File handle leak in `_cmd_svc_spawn`. Mai chiuso nel parent process. |
| 23 | `factory.py:81` | HIGH | `hidden_dim=64` vs config default 128. Incompatibilità checkpoint. |
| 24 | `rap_coach/memory.py:73-76` | HIGH | Shape mismatch Hopfield/LTC per addizione residuale. |
| 25 | `training_orchestrator.py:288-300` | HIGH | JEPA validation collassa 5 negativi a 1. Contrastive loss degenera. |
| 26 | `hltv_orchestrator.py:1` | CRITICAL | Import da modulo legacy `fetch_hltv_stats`. Duplicato stale. |
| 27 | `test_rag_knowledge.py + 8 altri test` | CRITICAL | Test operano su database di PRODUZIONE (`init_database()`, `get_db_manager()`). |
| 28 | `reset_pro_data.py:74,93-164` | CRITICAL+HIGH | SQL injection via f-string + 5 connessioni SQLite senza try/finally. |
| 29 | `4 migrazioni Alembic` | HIGH | NOT NULL senza `server_default`. Migrazione fallisce con righe esistenti. |
| 30 | `tactical_viewmodels.py:247` | HIGH | `NameError` a runtime: lambda cattura `e` cancellato da Python 3 dopo except. |

## Piano Fix Raccomandato (Ordine Priorità)

### Fase 1 — Emergenza (sbloccanti)
1. **Rimuovere TUTTI i `sys.exit(2)`** dai 44+ test file. Sostituire con `pytest.skip()` in conftest.
2. **Fix `train_pipeline.py`**: importare `OUTPUT_DIM` correttamente.
3. **Fix `demo_parser.py`**: definire o importare `_find_player_column`.
4. **Fix `rag_knowledge.py`**: importare `_infer_round_phase` da `round_utils`.
5. **Fix `profile_service.py`**: allineare campi `PlayerProfile` al modello SQLModel reale.

### Fase 2 — Data Integrity
6. **Fix `backup_manager.py`**: usare `text()` wrapper per SQL.
7. **Fix `persistence.py`**: non ritornare modello con pesi random. Raise esplicito.
8. **Fix `main.py:310`**: eager-load profile o mantenere sessione aperta.
9. **Fix `console.py:823`**: rimuovere `session.commit()` esplicito.
10. **Fix tutte le SQL injection** in `reset_pro_data.py`, `migrate_db.py`, `schema.py`.

### Fase 3 — Funzionalità UI/UX
11. **Fix `main.py:1320-1332`**: upload demo utente rotto.
12. **Fix `main.py:1548`**: reset `parsing_dialog` dopo dismiss.
13. **Fix `session_engine.py:233`**: leggere `hltv_status` non `ingest_status`.
14. **Fix `coaching_dialogue.py`**: non droppare ultimo messaggio.
15. **Fix `main.py:810`**: rimuovere "Section 2 omitted for brevity" dal codice produzione.

### Fase 4 — ML Pipeline
16. **Fix `factory.py:81`**: allineare `hidden_dim` al config.
17. **Fix `rap_coach/memory.py`**: risolvere shape mismatch.
18. **Fix `training_orchestrator.py`**: non collassare negativi JEPA.
19. **Fix `pro_ingest.py`**: usare nome giocatore reale, non "ProPlayer".
20. **Fix `pro_demo_miner.py` e `fetch_hltv_stats.py`**: rimuovere dati fabbricati.

### Fase 5 — Resource Leaks / Race Conditions
21. **Fix `downloader.py`**: implementare `__exit__` per BrowserManager.
22. **Fix `console.py:766`**: chiudere file handle dopo Popen.
23. **Fix `match_data_manager.py`**: aggiungere thread lock a cache engine.
24. **Fix migrazioni Alembic**: aggiungere `server_default` alle colonne NOT NULL.

### Fase 6 — Test Quality
25. **Isolare test da DB produzione**: usare `in_memory_db` fixture per tutti.
26. **Fix test vacui**: rimuovere try/except che swallowano, `if key in dict:` guard.
27. **Riscrivere test che testano math Python** invece di codice produzione.

---

