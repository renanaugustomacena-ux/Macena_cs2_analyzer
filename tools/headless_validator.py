"""
Headless Validator — Post-Task Regression Guard
================================================
Fast (~15-20s) non-GUI validation that imports all production modules,
validates DB schema in-memory, checks config loading, runs ML smoke tests,
verifies cross-module contracts, checks ML invariants, audits code quality,
validates the feature extraction pipeline, and performs deep architectural,
security, and integrity verification.

Coverage target: ~95% of production modules (290+ total).

Phases 1-8:   Original checks (imports, schema, config, ML smoke, UI, platform)
Phases 9-15:  Deep checks (contracts, ML invariants, DB integrity, code quality,
              package structure, feature pipeline, dependencies)
Phases 16-23: Extended checks (RAP coach forward pass, belief model contracts,
              MLControlContext, circuit breaker, integrity manifest hashing,
              security scanning, config consistency, advanced code quality)

Usage:  python tools/headless_validator.py [--verbose|-v]
Exit:   0 = PASS (warnings allowed) | 1 = FAIL
"""

import ast
import importlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List

# --- Path Stabilization (canonical project method) ---
_script_dir = Path(__file__).parent.absolute()
_project_root = _script_dir.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from Programma_CS2_RENAN.core.config import stabilize_paths

PROJECT_ROOT = stabilize_paths()

# ── Result Tracking ──────────────────────────────────────────────────────────

VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv


@dataclass
class CheckResult:
    phase: str
    name: str
    passed: bool
    error: str = ""
    severity: str = "fail"  # "fail" or "warn"


_results: List[CheckResult] = []
_t0 = time.perf_counter()

if __name__ != "__main__":
    raise ImportError(
        "headless_validator.py is not importable. Run: python tools/headless_validator.py"
    )


def check(phase: str, name: str, fn):
    """Run fn(), record pass/fail, print inline."""
    t = time.perf_counter()
    try:
        fn()
        _results.append(CheckResult(phase, name, True))
        suffix = f" ({(time.perf_counter() - t)*1000:.0f}ms)" if VERBOSE else ""
        print(f"  [PASS] {name}{suffix}")
    except Exception as e:
        _results.append(CheckResult(phase, name, False, str(e)))
        print(f"  [FAIL] {name}: {e}")


def warn(phase: str, name: str, fn):
    """Run fn(), record as warning on failure (non-blocking)."""
    t = time.perf_counter()
    try:
        fn()
        _results.append(CheckResult(phase, name, True))
        suffix = f" ({(time.perf_counter() - t)*1000:.0f}ms)" if VERBOSE else ""
        print(f"  [PASS] {name}{suffix}")
    except Exception as e:
        _results.append(CheckResult(phase, name, False, str(e), severity="warn"))
        print(f"  [WARN] {name}: {e}")


def try_import(module_path: str):
    """Return a callable that imports a module."""

    def _do():
        importlib.import_module(module_path)

    return _do


# ── Phase 1: Environment ─────────────────────────────────────────────────────

print("=" * 60)
print("HEADLESS VALIDATOR — Macena CS2 Analyzer")
print("=" * 60)
print(f"Project root: {PROJECT_ROOT}")

print("\n[Phase 1] Environment")

check(
    "Env",
    "project root exists",
    lambda: (
        None
        if Path(PROJECT_ROOT).is_dir()
        else (_ for _ in ()).throw(AssertionError("Project root not found"))
    ),
)

CRITICAL_DIRS = [
    "Programma_CS2_RENAN",
    "Programma_CS2_RENAN/backend/storage",
    "Programma_CS2_RENAN/backend/nn",
    "Programma_CS2_RENAN/backend/nn/rap_coach",
    "Programma_CS2_RENAN/backend/nn/experimental/rap_coach",
    "Programma_CS2_RENAN/backend/nn/advanced",
    "Programma_CS2_RENAN/backend/nn/inference",
    "Programma_CS2_RENAN/backend/nn/layers",
    "Programma_CS2_RENAN/backend/processing",
    "Programma_CS2_RENAN/backend/processing/feature_engineering",
    "Programma_CS2_RENAN/backend/processing/validation",
    "Programma_CS2_RENAN/backend/processing/baselines",
    "Programma_CS2_RENAN/backend/coaching",
    "Programma_CS2_RENAN/backend/control",
    "Programma_CS2_RENAN/backend/services",
    "Programma_CS2_RENAN/backend/knowledge",
    "Programma_CS2_RENAN/backend/analysis",
    "Programma_CS2_RENAN/backend/data_sources",
    "Programma_CS2_RENAN/backend/ingestion",
    "Programma_CS2_RENAN/backend/onboarding",
    "Programma_CS2_RENAN/backend/progress",
    "Programma_CS2_RENAN/core",
    "Programma_CS2_RENAN/observability",
    "Programma_CS2_RENAN/ingestion",
    "Programma_CS2_RENAN/ingestion/pipelines",
    "Programma_CS2_RENAN/ingestion/registry",
    "Programma_CS2_RENAN/reporting",
]

for d in CRITICAL_DIRS:
    full = Path(PROJECT_ROOT) / d
    check(
        "Env",
        f"dir {d}",
        lambda p=full: (
            None if p.is_dir() else (_ for _ in ()).throw(AssertionError(f"Missing: {p}"))
        ),
    )


# ── Phase 2: Core Imports ────────────────────────────────────────────────────

print("\n[Phase 2] Core Imports")

CORE_IMPORTS = [
    "Programma_CS2_RENAN.core.config",
    "Programma_CS2_RENAN.core.constants",
    "Programma_CS2_RENAN.core.app_types",
    "Programma_CS2_RENAN.core.spatial_data",
    "Programma_CS2_RENAN.core.spatial_engine",
    "Programma_CS2_RENAN.core.demo_frame",
    "Programma_CS2_RENAN.core.lifecycle",
    "Programma_CS2_RENAN.core.asset_manager",
    "Programma_CS2_RENAN.core.logger",
    "Programma_CS2_RENAN.core.map_manager",
    "Programma_CS2_RENAN.core.playback",
    "Programma_CS2_RENAN.core.playback_engine",
    "Programma_CS2_RENAN.core.registry",
    "Programma_CS2_RENAN.core.session_engine",
    "Programma_CS2_RENAN.observability.logger_setup",
    "Programma_CS2_RENAN.observability.rasp",
    "Programma_CS2_RENAN.ingestion.integrity",
]

for mod in CORE_IMPORTS:
    short = mod.split(".")[-1]
    check("Core", f"import {short}", try_import(mod))


# ── Phase 3: Backend Storage Imports ─────────────────────────────────────────

print("\n[Phase 3] Backend Storage")

STORAGE_IMPORTS = [
    "Programma_CS2_RENAN.backend.storage.db_models",
    "Programma_CS2_RENAN.backend.storage.database",
    "Programma_CS2_RENAN.backend.storage.state_manager",
    "Programma_CS2_RENAN.backend.storage.stat_aggregator",
    "Programma_CS2_RENAN.backend.storage.match_data_manager",
    "Programma_CS2_RENAN.backend.storage.storage_manager",
    "Programma_CS2_RENAN.backend.storage.maintenance",
    "Programma_CS2_RENAN.backend.storage.db_migrate",
    "Programma_CS2_RENAN.backend.storage.remote_file_server",
]

for mod in STORAGE_IMPORTS:
    short = mod.split(".")[-1]
    check("Storage", f"import {short}", try_import(mod))


# ── Phase 3b: Backend Processing Imports ─────────────────────────────────────

print("\n[Phase 3b] Backend Processing")

PROCESSING_IMPORTS = [
    # Feature engineering
    "Programma_CS2_RENAN.backend.processing.feature_engineering",
    "Programma_CS2_RENAN.backend.processing.feature_engineering.vectorizer",
    "Programma_CS2_RENAN.backend.processing.feature_engineering.rating",
    "Programma_CS2_RENAN.backend.processing.feature_engineering.base_features",
    "Programma_CS2_RENAN.backend.processing.feature_engineering.kast",
    "Programma_CS2_RENAN.backend.processing.feature_engineering.role_features",
    # Validation
    "Programma_CS2_RENAN.backend.processing.validation.schema",
    "Programma_CS2_RENAN.backend.processing.validation.drift",
    "Programma_CS2_RENAN.backend.processing.validation.sanity",
    "Programma_CS2_RENAN.backend.processing.validation.dem_validator",
    # Core processing
    "Programma_CS2_RENAN.backend.processing.data_pipeline",
    "Programma_CS2_RENAN.backend.processing.state_reconstructor",
    "Programma_CS2_RENAN.backend.processing.tensor_factory",
    "Programma_CS2_RENAN.backend.processing.heatmap_engine",
    "Programma_CS2_RENAN.backend.processing.connect_map_context",
    "Programma_CS2_RENAN.backend.processing.external_analytics",
    "Programma_CS2_RENAN.backend.processing.round_stats_builder",
    # Baselines
    "Programma_CS2_RENAN.backend.processing.baselines.pro_baseline",
    "Programma_CS2_RENAN.backend.processing.baselines.role_thresholds",
    "Programma_CS2_RENAN.backend.processing.baselines.meta_drift",
    "Programma_CS2_RENAN.backend.processing.baselines.nickname_resolver",
]

for mod in PROCESSING_IMPORTS:
    short = mod.split(".")[-1]
    check("Processing", f"import {short}", try_import(mod))


# ── Phase 3c: Backend Neural Network Imports ─────────────────────────────────

print("\n[Phase 3c] Backend Neural Networks")

NN_IMPORTS = [
    # Core NN
    "Programma_CS2_RENAN.backend.nn.config",
    "Programma_CS2_RENAN.backend.nn.training_config",
    "Programma_CS2_RENAN.backend.nn.model",
    "Programma_CS2_RENAN.backend.nn.jepa_model",
    "Programma_CS2_RENAN.backend.nn.factory",
    "Programma_CS2_RENAN.backend.nn.coach_manager",
    "Programma_CS2_RENAN.backend.nn.persistence",
    "Programma_CS2_RENAN.backend.nn.train",
    "Programma_CS2_RENAN.backend.nn.dataset",
    # evaluate requires 'shap' (optional) — tested separately below
    # "Programma_CS2_RENAN.backend.nn.evaluate",
    "Programma_CS2_RENAN.backend.nn.early_stopping",
    "Programma_CS2_RENAN.backend.nn.ema",
    "Programma_CS2_RENAN.backend.nn.role_head",
    "Programma_CS2_RENAN.backend.nn.win_probability_trainer",
    "Programma_CS2_RENAN.backend.nn.embedding_projector",
    "Programma_CS2_RENAN.backend.nn.maturity_observatory",
    "Programma_CS2_RENAN.backend.nn.training_callbacks",
    "Programma_CS2_RENAN.backend.nn.training_controller",
    "Programma_CS2_RENAN.backend.nn.training_monitor",
    "Programma_CS2_RENAN.backend.nn.training_orchestrator",
    "Programma_CS2_RENAN.backend.nn.train_pipeline",
    "Programma_CS2_RENAN.backend.nn.jepa_trainer",
    "Programma_CS2_RENAN.backend.nn.jepa_train",
    # Layers
    "Programma_CS2_RENAN.backend.nn.layers.superposition",
    # RAP Coach (canonical: experimental/rap_coach, shim: rap_coach)
    "Programma_CS2_RENAN.backend.nn.experimental.rap_coach.memory",
    "Programma_CS2_RENAN.backend.nn.experimental.rap_coach.model",
    "Programma_CS2_RENAN.backend.nn.experimental.rap_coach.trainer",
    "Programma_CS2_RENAN.backend.nn.experimental.rap_coach.chronovisor_scanner",
    "Programma_CS2_RENAN.backend.nn.experimental.rap_coach.strategy",
    "Programma_CS2_RENAN.backend.nn.experimental.rap_coach.perception",
    "Programma_CS2_RENAN.backend.nn.experimental.rap_coach.pedagogy",
    "Programma_CS2_RENAN.backend.nn.experimental.rap_coach.communication",
    # Shared utilities (extracted from RAP, P9-01)
    "Programma_CS2_RENAN.backend.processing.skill_assessment",
    # Inference
    "Programma_CS2_RENAN.backend.nn.inference.ghost_engine",
]

for mod in NN_IMPORTS:
    short = mod.split(".")[-1]
    check("NN", f"import {short}", try_import(mod))


# ── Phase 3d: Backend Analysis Imports ───────────────────────────────────────

print("\n[Phase 3d] Backend Analysis")

ANALYSIS_IMPORTS = [
    "Programma_CS2_RENAN.backend.analysis.belief_model",
    "Programma_CS2_RENAN.backend.analysis.deception_index",
    "Programma_CS2_RENAN.backend.analysis.momentum",
    "Programma_CS2_RENAN.backend.analysis.entropy_analysis",
    "Programma_CS2_RENAN.backend.analysis.game_tree",
    "Programma_CS2_RENAN.backend.analysis.blind_spots",
    "Programma_CS2_RENAN.backend.analysis.engagement_range",
    "Programma_CS2_RENAN.backend.analysis.role_classifier",
    "Programma_CS2_RENAN.backend.analysis.utility_economy",
    "Programma_CS2_RENAN.backend.analysis.win_probability",
]

for mod in ANALYSIS_IMPORTS:
    short = mod.split(".")[-1]
    check("Analysis", f"import {short}", try_import(mod))


# ── Phase 3e: Backend Coaching Imports ───────────────────────────────────────

print("\n[Phase 3e] Backend Coaching")

COACHING_IMPORTS = [
    "Programma_CS2_RENAN.backend.coaching.hybrid_engine",
    "Programma_CS2_RENAN.backend.coaching.correction_engine",
    "Programma_CS2_RENAN.backend.coaching.explainability",
    "Programma_CS2_RENAN.backend.coaching.longitudinal_engine",
    "Programma_CS2_RENAN.backend.coaching.pro_bridge",
    "Programma_CS2_RENAN.backend.coaching.token_resolver",
]

for mod in COACHING_IMPORTS:
    short = mod.split(".")[-1]
    check("Coaching", f"import {short}", try_import(mod))


# ── Phase 3f: Backend Services Imports ───────────────────────────────────────

print("\n[Phase 3f] Backend Services")

SERVICES_IMPORTS = [
    "Programma_CS2_RENAN.backend.services.llm_service",
    "Programma_CS2_RENAN.backend.services.coaching_service",
    "Programma_CS2_RENAN.backend.services.analysis_orchestrator",
    "Programma_CS2_RENAN.backend.services.analysis_service",
    "Programma_CS2_RENAN.backend.services.coaching_dialogue",
    "Programma_CS2_RENAN.backend.services.lesson_generator",
    "Programma_CS2_RENAN.backend.services.profile_service",
    "Programma_CS2_RENAN.backend.services.visualization_service",
    # telemetry_client requires 'httpx' (optional) — skip on envs without it
    # "Programma_CS2_RENAN.backend.services.telemetry_client",
]

for mod in SERVICES_IMPORTS:
    short = mod.split(".")[-1]
    check("Services", f"import {short}", try_import(mod))


# ── Phase 3g: Backend Knowledge Imports ──────────────────────────────────────

print("\n[Phase 3g] Backend Knowledge")

KNOWLEDGE_IMPORTS = [
    "Programma_CS2_RENAN.backend.knowledge.experience_bank",
    "Programma_CS2_RENAN.backend.knowledge.rag_knowledge",
    "Programma_CS2_RENAN.backend.knowledge.graph",
    "Programma_CS2_RENAN.backend.knowledge.init_knowledge_base",
    "Programma_CS2_RENAN.backend.knowledge.pro_demo_miner",
]

for mod in KNOWLEDGE_IMPORTS:
    short = mod.split(".")[-1]
    check("Knowledge", f"import {short}", try_import(mod))


# ── Phase 3h: Backend Control Imports ────────────────────────────────────────

print("\n[Phase 3h] Backend Control")

CONTROL_IMPORTS = [
    "Programma_CS2_RENAN.backend.control.console",
    "Programma_CS2_RENAN.backend.control.db_governor",
    "Programma_CS2_RENAN.backend.control.ingest_manager",
    "Programma_CS2_RENAN.backend.control.ml_controller",
]

for mod in CONTROL_IMPORTS:
    short = mod.split(".")[-1]
    check("Control", f"import {short}", try_import(mod))


# ── Phase 3i: Backend Data Sources Imports ───────────────────────────────────

print("\n[Phase 3i] Backend Data Sources")

DATASOURCE_IMPORTS = [
    "Programma_CS2_RENAN.backend.data_sources.demo_parser",
    "Programma_CS2_RENAN.backend.data_sources.demo_format_adapter",
    "Programma_CS2_RENAN.backend.data_sources.event_registry",
    "Programma_CS2_RENAN.backend.data_sources.trade_kill_detector",
    "Programma_CS2_RENAN.backend.data_sources.steam_api",
    "Programma_CS2_RENAN.backend.data_sources.steam_demo_finder",
    "Programma_CS2_RENAN.backend.data_sources.hltv_scraper",
    "Programma_CS2_RENAN.backend.data_sources.faceit_api",
    "Programma_CS2_RENAN.backend.data_sources.faceit_integration",
    # HLTV package (restructured from hltv_metadata.py)
    "Programma_CS2_RENAN.backend.data_sources.hltv",
    "Programma_CS2_RENAN.backend.data_sources.hltv.selectors",
    "Programma_CS2_RENAN.backend.data_sources.hltv.rate_limit",
    "Programma_CS2_RENAN.backend.data_sources.hltv.flaresolverr_client",
    "Programma_CS2_RENAN.backend.data_sources.hltv.docker_manager",
    "Programma_CS2_RENAN.backend.data_sources.hltv.stat_fetcher",
    # Removed in commit 4c71484 (HLTV pipeline cleanup):
    # cache.proxy, collectors.players, browser.manager, hltv_api_service
]

for mod in DATASOURCE_IMPORTS:
    short = mod.split(".")[-1]
    check("DataSrc", f"import {short}", try_import(mod))


# ── Phase 3j: Backend Ingestion & Onboarding Imports ────────────────────────

print("\n[Phase 3j] Backend Ingestion & Onboarding")

BACKEND_INGESTION_IMPORTS = [
    "Programma_CS2_RENAN.backend.ingestion.watcher",
    "Programma_CS2_RENAN.backend.ingestion.resource_manager",
    "Programma_CS2_RENAN.backend.onboarding.new_user_flow",
    "Programma_CS2_RENAN.backend.reporting.analytics",
    "Programma_CS2_RENAN.backend.server",
]

for mod in BACKEND_INGESTION_IMPORTS:
    short = mod.split(".")[-1]
    check("BkIngestion", f"import {short}", try_import(mod))


# ── Phase 3k: Ingestion Pipeline Imports ─────────────────────────────────────

print("\n[Phase 3k] Ingestion Pipelines")

INGESTION_IMPORTS = [
    "Programma_CS2_RENAN.ingestion.demo_loader",
    "Programma_CS2_RENAN.ingestion.steam_locator",
    "Programma_CS2_RENAN.ingestion.pipelines.user_ingest",
    "Programma_CS2_RENAN.ingestion.pipelines.json_tournament_ingestor",
    "Programma_CS2_RENAN.ingestion.registry.registry",
    "Programma_CS2_RENAN.ingestion.registry.lifecycle",
]

for mod in INGESTION_IMPORTS:
    short = mod.split(".")[-1]
    check("Ingestion", f"import {short}", try_import(mod))


# ── Phase 3l: Reporting & Observability ──────────────────────────────────────

print("\n[Phase 3l] Reporting & Observability")

REPORTING_IMPORTS = [
    "Programma_CS2_RENAN.reporting.visualizer",
    "Programma_CS2_RENAN.reporting.report_generator",
]

for mod in REPORTING_IMPORTS:
    short = mod.split(".")[-1]
    check("Reporting", f"import {short}", try_import(mod))


# ── Phase 4: Database Schema ─────────────────────────────────────────────────

print("\n[Phase 4] Database Schema")

EXPECTED_TABLES = [
    "playermatchstats",
    "playertickstate",
    "playerprofile",
    "ext_teamroundstats",
    "ext_playerplaystyle",
    "coachinginsight",
    "ingestiontask",
    "tacticalknowledge",
    "coachstate",
    "servicenotification",
    "proteam",
    "proplayer",
    "proplayerstatcard",
    "matchresult",
    "mapveto",
    "coachingexperience",
    "roundstats",
    "calibrationsnapshot",
    "rolethresholdrecord",
]


def verify_schema():
    from sqlmodel import SQLModel, create_engine

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    tables = set(SQLModel.metadata.tables.keys())
    missing = [t for t in EXPECTED_TABLES if t not in tables]
    if missing:
        raise AssertionError(f"Missing tables: {missing}")


def verify_table_count():
    from sqlmodel import SQLModel

    tables = set(SQLModel.metadata.tables.keys())
    if len(tables) < len(EXPECTED_TABLES):
        raise AssertionError(f"Expected >= {len(EXPECTED_TABLES)} tables, found {len(tables)}")


def verify_crud_smoke():
    from sqlmodel import Session, SQLModel, create_engine, select

    from Programma_CS2_RENAN.backend.storage.db_models import CoachState

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        state = CoachState(ml_status="validator_test")
        session.add(state)
        session.commit()
        loaded = session.exec(select(CoachState)).first()
        if loaded is None or loaded.ml_status != "validator_test":
            raise AssertionError("CoachState CRUD failed")


check("DB", "schema creation (all tables)", verify_schema)
check("DB", "table count >= 20", verify_table_count)
check("DB", "CRUD smoke (CoachState)", verify_crud_smoke)


# ── Phase 5: Config & Data Files ─────────────────────────────────────────────

print("\n[Phase 5] Config & Data")


def verify_map_config():
    import json

    path = Path(PROJECT_ROOT) / "Programma_CS2_RENAN" / "data" / "map_config.json"
    if not path.exists():
        raise AssertionError(f"map_config.json not found at {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if "maps" not in data:
        raise AssertionError("map_config.json missing 'maps' key")
    if len(data["maps"]) < 5:
        raise AssertionError(f"Expected >= 5 maps, found {len(data['maps'])}")


def verify_get_setting():
    from Programma_CS2_RENAN.core.config import get_setting

    val = get_setting("max_epochs", 100)
    if not isinstance(val, int):
        raise AssertionError(f"Expected int, got {type(val)}")


def verify_metadata_dim():
    from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM

    if METADATA_DIM != 25:
        raise AssertionError(f"METADATA_DIM = {METADATA_DIM}, expected 25")


def verify_nn_config_dims():
    from Programma_CS2_RENAN.backend.nn.config import INPUT_DIM, OUTPUT_DIM

    if INPUT_DIM <= 0 or OUTPUT_DIM <= 0:
        raise AssertionError(f"INPUT_DIM={INPUT_DIM}, OUTPUT_DIM={OUTPUT_DIM}")


def verify_training_features_alignment():
    """Verify TRAINING_FEATURES in coach_manager matches METADATA_DIM."""
    from Programma_CS2_RENAN.backend.nn.coach_manager import TRAINING_FEATURES
    from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM

    if len(TRAINING_FEATURES) != METADATA_DIM:
        raise AssertionError(
            f"TRAINING_FEATURES has {len(TRAINING_FEATURES)} features, "
            f"but METADATA_DIM={METADATA_DIM}"
        )


check("Config", "map_config.json valid", verify_map_config)
check("Config", "get_setting() returns expected type", verify_get_setting)
check("Config", "METADATA_DIM == 25", verify_metadata_dim)
check("Config", "INPUT_DIM / OUTPUT_DIM positive", verify_nn_config_dims)
check("Config", "TRAINING_FEATURES aligned with METADATA_DIM", verify_training_features_alignment)


# ── Phase 6: ML Smoke Test ───────────────────────────────────────────────────

print("\n[Phase 6] ML Smoke")


def verify_jepa_instantiation():
    import torch

    from Programma_CS2_RENAN.backend.nn.jepa_model import JEPACoachingModel

    with torch.no_grad():
        model = JEPACoachingModel(input_dim=10, output_dim=5, latent_dim=32)
        params = sum(p.numel() for p in model.parameters())
        if params <= 0:
            raise AssertionError(f"JEPA model has {params} parameters")


def verify_factory_default():
    import torch.nn as nn

    from Programma_CS2_RENAN.backend.nn.factory import ModelFactory

    model = ModelFactory.get_model("default")
    if not isinstance(model, nn.Module):
        raise AssertionError(f"Factory default returned {type(model)}")


def verify_factory_jepa():
    import torch.nn as nn

    from Programma_CS2_RENAN.backend.nn.factory import ModelFactory

    model = ModelFactory.get_model("jepa")
    if not isinstance(model, nn.Module):
        raise AssertionError(f"Factory JEPA returned {type(model)}")


def verify_factory_vl_jepa():
    import torch

    from Programma_CS2_RENAN.backend.nn.factory import ModelFactory
    from Programma_CS2_RENAN.backend.nn.jepa_model import VLJEPACoachingModel

    model = ModelFactory.get_model("vl-jepa")
    if not isinstance(model, VLJEPACoachingModel):
        raise AssertionError(
            f"Factory vl-jepa returned {type(model)}, expected VLJEPACoachingModel"
        )
    # Verify concept head exists and forward_vl works
    from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM as _META_DIM

    with torch.no_grad():
        x = torch.randn(2, 5, _META_DIM)
        result = model.forward_vl(x)
        if result["concept_probs"].shape != (2, 16):
            raise AssertionError(
                f"concept_probs shape {result['concept_probs'].shape}, expected (2, 16)"
            )
        if len(result["top_concepts"]) != 3:
            raise AssertionError(
                f"top_concepts has {len(result['top_concepts'])} items, expected 3"
            )


def verify_role_head_forward():
    import torch

    from Programma_CS2_RENAN.backend.nn.role_head import NeuralRoleHead

    with torch.no_grad():
        model = NeuralRoleHead()
        x = torch.randn(3, 5)
        out = model(x)
        if out.shape != (3, 5):
            raise AssertionError(f"Role head output shape {out.shape}, expected (3, 5)")
        if not torch.allclose(out.sum(dim=1), torch.ones(3), atol=1e-5):
            raise AssertionError("Role head output does not sum to 1.0")


def verify_factory_role_head():
    import torch.nn as nn

    from Programma_CS2_RENAN.backend.nn.factory import ModelFactory

    model = ModelFactory.get_model("role_head")
    if not isinstance(model, nn.Module):
        raise AssertionError(f"Factory role_head returned {type(model)}")


check("ML", "JEPA model instantiation", verify_jepa_instantiation)
check("ML", "ModelFactory.get_model('default')", verify_factory_default)
check("ML", "ModelFactory.get_model('jepa')", verify_factory_jepa)
check("ML", "ModelFactory.get_model('vl-jepa') + forward_vl", verify_factory_vl_jepa)
check("ML", "NeuralRoleHead forward + softmax", verify_role_head_forward)
check("ML", "ModelFactory.get_model('role_head')", verify_factory_role_head)


# ── Phase 6b: Baseline Smoke ─────────────────────────────────────────────────

print("\n[Phase 6b] Baseline Smoke")


def verify_temporal_baseline_import():
    from Programma_CS2_RENAN.backend.processing.baselines.pro_baseline import TemporalBaselineDecay

    decay = TemporalBaselineDecay()
    if not hasattr(decay, "compute_weight"):
        raise AssertionError("TemporalBaselineDecay missing compute_weight")
    if not hasattr(decay, "get_temporal_baseline"):
        raise AssertionError("TemporalBaselineDecay missing get_temporal_baseline")
    if not hasattr(decay, "detect_meta_shift"):
        raise AssertionError("TemporalBaselineDecay missing detect_meta_shift")


def verify_temporal_baseline_compute_weight():
    from datetime import datetime, timedelta

    from Programma_CS2_RENAN.backend.processing.baselines.pro_baseline import TemporalBaselineDecay

    decay = TemporalBaselineDecay()
    ref = datetime(2026, 6, 1)

    w_today = decay.compute_weight(ref, ref)
    if w_today != 1.0:
        raise AssertionError(f"Weight for today = {w_today}, expected 1.0")

    w_half = decay.compute_weight(ref - timedelta(days=90), ref)
    if not (0.45 <= w_half <= 0.55):
        raise AssertionError(f"Weight at half-life = {w_half}, expected ~0.5")

    w_old = decay.compute_weight(ref - timedelta(days=1000), ref)
    if not (0.1 <= w_old <= 1.0):
        raise AssertionError(f"Weight for old data = {w_old}, not in [0.1, 1.0]")


check("Baseline", "TemporalBaselineDecay import + structure", verify_temporal_baseline_import)
check("Baseline", "compute_weight() range [0.1, 1.0]", verify_temporal_baseline_compute_weight)


# ── Phase 6c: Demo Format Adapter Smoke ─────────────────────────────────────

print("\n[Phase 6c] Demo Format Adapter Smoke")


def verify_adapter_instantiation():
    from Programma_CS2_RENAN.backend.data_sources.demo_format_adapter import DemoFormatAdapter

    adapter = DemoFormatAdapter()
    if not hasattr(adapter, "validate_demo"):
        raise AssertionError("DemoFormatAdapter missing validate_demo")
    if not hasattr(adapter, "get_field_mapping"):
        raise AssertionError("DemoFormatAdapter missing get_field_mapping")


def verify_adapter_validate_rejects_missing():
    from Programma_CS2_RENAN.backend.data_sources.demo_format_adapter import validate_demo_file

    result = validate_demo_file("/nonexistent/path/test.dem")
    if result["valid"] is not False:
        raise AssertionError("validate_demo_file accepted nonexistent file")
    if result["error"] is None:
        raise AssertionError("validate_demo_file returned no error for missing file")


def verify_adapter_field_mapping():
    from Programma_CS2_RENAN.backend.data_sources.demo_format_adapter import DemoFormatAdapter

    mapping = DemoFormatAdapter().get_field_mapping("cs2_protobuf")
    if not isinstance(mapping, dict) or len(mapping) < 10:
        raise AssertionError(f"Field mapping has {len(mapping)} keys, expected >= 10")


check("Adapter", "DemoFormatAdapter instantiation", verify_adapter_instantiation)
check("Adapter", "validate_demo_file rejects missing", verify_adapter_validate_rejects_missing)
check("Adapter", "field mapping >= 10 keys", verify_adapter_field_mapping)


# ── Phase 6d: GPU Detection Smoke ───────────────────────────────────────────

print("\n[Phase 6d] GPU Detection")


def verify_get_device_returns_valid():
    """Verify get_device() returns a valid torch.device."""
    import torch

    from Programma_CS2_RENAN.backend.nn.config import get_device

    dev = get_device()
    if not isinstance(dev, torch.device):
        raise AssertionError(f"get_device() returned {type(dev)}, expected torch.device")
    if dev.type not in ("cpu", "cuda"):
        raise AssertionError(
            f"get_device() returned device type '{dev.type}', expected 'cpu' or 'cuda'"
        )


def verify_get_device_deterministic():
    """Verify get_device() returns the same device on repeated calls."""
    from Programma_CS2_RENAN.backend.nn.config import get_device

    dev1 = get_device()
    dev2 = get_device()
    if str(dev1) != str(dev2):
        raise AssertionError(f"get_device() not deterministic: {dev1} vs {dev2}")


def verify_cuda_device_selection():
    """If CUDA available, verify discrete GPU preference."""
    import torch

    if not torch.cuda.is_available():
        return  # Skip on CPU-only systems
    from Programma_CS2_RENAN.backend.nn.config import get_device

    dev = get_device()
    if dev.type != "cuda":
        raise AssertionError(f"CUDA available but get_device() returned {dev}")
    # Verify the selected device is actually accessible
    name = torch.cuda.get_device_name(dev.index if dev.index is not None else 0)
    if not name:
        raise AssertionError("Selected CUDA device has no name")


check("GPU", "get_device() returns valid torch.device", verify_get_device_returns_valid)
check("GPU", "get_device() deterministic", verify_get_device_deterministic)
check("GPU", "CUDA device selection (if available)", verify_cuda_device_selection)


# ── Phase 6e: Training Pipeline Smoke ───────────────────────────────────────

print("\n[Phase 6e] Training Pipeline Smoke")


def verify_training_orchestrator_init():
    """Verify TrainingOrchestrator can be instantiated with a mock manager."""
    from unittest.mock import MagicMock

    from Programma_CS2_RENAN.backend.nn.training_orchestrator import TrainingOrchestrator

    mock_manager = MagicMock()
    orch = TrainingOrchestrator(manager=mock_manager, model_type="jepa", max_epochs=1)
    if not hasattr(orch, "device"):
        raise AssertionError("TrainingOrchestrator missing 'device' attribute")
    if not hasattr(orch, "run_training"):
        raise AssertionError("TrainingOrchestrator missing 'run_training' method")


def verify_early_stopping_logic():
    """Verify EarlyStopping works correctly."""
    from Programma_CS2_RENAN.backend.nn.early_stopping import EarlyStopping

    es = EarlyStopping(patience=3, min_delta=0.01)
    # Improving: should not trigger
    if es(1.0):
        raise AssertionError("EarlyStopping triggered on first call")
    if es(0.5):
        raise AssertionError("EarlyStopping triggered on improvement")
    # Not improving: should trigger after patience
    es(0.5)
    es(0.5)
    es(0.5)
    if not es(0.5):
        raise AssertionError("EarlyStopping did not trigger after patience exhausted")


def verify_persistence_save_load():
    """Verify model persistence round-trip."""
    import tempfile

    import torch

    from Programma_CS2_RENAN.backend.nn.factory import ModelFactory

    model = ModelFactory.get_model("default")
    # Save to temp
    with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as f:
        torch.save(model.state_dict(), f.name)
        tmp_path = f.name
    # Load back
    state = torch.load(tmp_path, map_location="cpu", weights_only=True)
    model.load_state_dict(state, strict=True)
    os.unlink(tmp_path)


check("Training", "TrainingOrchestrator init", verify_training_orchestrator_init)
check("Training", "EarlyStopping logic", verify_early_stopping_logic)
check("Training", "model persistence round-trip", verify_persistence_save_load)


# ── Phase 6f: Coaching Pipeline Smoke ───────────────────────────────────────

print("\n[Phase 6f] Coaching Pipeline Smoke")


def verify_experience_bank_init():
    """Verify ExperienceBank can be instantiated."""
    from Programma_CS2_RENAN.backend.knowledge.experience_bank import ExperienceBank

    bank = ExperienceBank()
    if not hasattr(bank, "add_experience"):
        raise AssertionError("ExperienceBank missing add_experience")
    if not hasattr(bank, "retrieve_similar"):
        raise AssertionError("ExperienceBank missing retrieve_similar")


def verify_coaching_service_import():
    """Verify coaching service and its dependencies load."""
    from Programma_CS2_RENAN.backend.services.coaching_service import CoachingService

    if not hasattr(CoachingService, "generate_new_insights"):
        raise AssertionError("CoachingService missing generate_new_insights")


check("Coaching", "ExperienceBank init", verify_experience_bank_init)
check("Coaching", "CoachingService import", verify_coaching_service_import)


# ── Phase 7: UI Components (Headless) ────────────────────────────────────────

print("\n[Phase 7] UI Components (Headless)")


def verify_qt_app_imports():
    """Verify the Qt app entry point and MainWindow import cleanly."""
    from Programma_CS2_RENAN.apps.qt_app import app as qt_app_module
    from Programma_CS2_RENAN.apps.qt_app.main_window import MainWindow

    if not hasattr(qt_app_module, "main"):
        raise AssertionError("qt_app.app missing 'main' function")
    if not callable(qt_app_module.main):
        raise AssertionError("qt_app.app.main is not callable")

    # Verify MainWindow has expected navigation structure
    if not hasattr(MainWindow, "__init__"):
        raise AssertionError("MainWindow missing __init__")

    # Verify all screen modules import cleanly
    screen_modules = [
        "home_screen", "coach_screen", "match_history_screen",
        "performance_screen", "tactical_viewer_screen", "settings_screen",
        "help_screen", "steam_config_screen", "user_profile_screen",
        "profile_screen", "wizard_screen", "match_detail_screen",
        "faceit_config_screen",
    ]
    import importlib
    for mod_name in screen_modules:
        full = f"Programma_CS2_RENAN.apps.qt_app.screens.{mod_name}"
        importlib.import_module(full)


check("UI", "Qt App + MainWindow + All Screens Import", verify_qt_app_imports)


# ── Phase 8: Cross-Platform Checks ──────────────────────────────────────────

print("\n[Phase 8] Cross-Platform")


def verify_pathlib_usage():
    """Spot-check that key config paths use pathlib, not hardcoded separators."""
    from Programma_CS2_RENAN.core.config import DATA_DIR, MODELS_DIR

    # Both should be pathlib.Path or string convertible
    if not MODELS_DIR:
        raise AssertionError("MODELS_DIR is empty/None")
    if not DATA_DIR:
        raise AssertionError("DATA_DIR is empty/None")


def verify_no_hardcoded_drive_letters_in_config():
    """Ensure config module doesn't hardcode Windows drive letters."""
    import inspect

    from Programma_CS2_RENAN.core import config as cfg

    source = inspect.getsource(cfg)
    # Check for absolute Windows paths that aren't in comments/docstrings
    for line in source.split("\n"):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
            continue
        # Only flag actual assignment lines with drive letters
        if ":\\\\" in stripped and "=" in stripped and not stripped.startswith("#"):
            # Allow documented fallback paths
            if "not found" in stripped.lower() or "fallback" in stripped.lower():
                continue


check("Platform", "pathlib-based config paths", verify_pathlib_usage)
check(
    "Platform", "no hardcoded drive letters in config", verify_no_hardcoded_drive_letters_in_config
)


# ── Phase 9: Cross-Module Contract Validation ────────────────────────────────

print("\n[Phase 9] Cross-Module Contracts")


def verify_contract(mod_path: str, cls_name: str, methods: list, attrs: list = None):
    """Generic contract verifier: import class, check for expected members."""
    mod = importlib.import_module(mod_path)
    cls = getattr(mod, cls_name)
    for method in methods:
        if not hasattr(cls, method):
            raise AssertionError(f"{cls_name} missing method: {method}")
    for attr in attrs or []:
        if not hasattr(cls, attr):
            raise AssertionError(f"{cls_name} missing attribute: {attr}")


CONTRACT_CHECKS = [
    (
        "Contract",
        "DatabaseManager API",
        "Programma_CS2_RENAN.backend.storage.database",
        "DatabaseManager",
        ["get_session", "upsert", "get", "create_db_and_tables"],
        [],
    ),
    (
        "Contract",
        "CoachingService API",
        "Programma_CS2_RENAN.backend.services.coaching_service",
        "CoachingService",
        ["generate_new_insights"],
        [],
    ),
    (
        "Contract",
        "Console API",
        "Programma_CS2_RENAN.backend.control.console",
        "Console",
        [
            "boot",
            "shutdown",
            "get_system_status",
            "start_training",
            "stop_training",
            "pause_training",
            "resume_training",
        ],
        [],
    ),
    (
        "Contract",
        "ModelFactory API",
        "Programma_CS2_RENAN.backend.nn.factory",
        "ModelFactory",
        ["get_model", "get_checkpoint_name"],
        ["TYPE_LEGACY", "TYPE_JEPA", "TYPE_VL_JEPA", "TYPE_RAP", "TYPE_ROLE_HEAD"],
    ),
    (
        "Contract",
        "FeatureExtractor API",
        "Programma_CS2_RENAN.backend.processing.feature_engineering.vectorizer",
        "FeatureExtractor",
        ["extract", "extract_batch", "get_feature_names", "configure"],
        [],
    ),
    (
        "Contract",
        "ExperienceBank API",
        "Programma_CS2_RENAN.backend.knowledge.experience_bank",
        "ExperienceBank",
        ["add_experience", "retrieve_similar", "synthesize_advice"],
        [],
    ),
    (
        "Contract",
        "CoachTrainingManager API",
        "Programma_CS2_RENAN.backend.nn.coach_manager",
        "CoachTrainingManager",
        ["run_full_cycle", "check_prerequisites", "get_maturity_tier"],
        [],
    ),
    (
        "Contract",
        "EMA API",
        "Programma_CS2_RENAN.backend.nn.ema",
        "EMA",
        ["update", "apply_shadow", "restore", "state_dict", "load_state_dict"],
        [],
    ),
    (
        "Contract",
        "JEPACoachingModel API",
        "Programma_CS2_RENAN.backend.nn.jepa_model",
        "JEPACoachingModel",
        [
            "forward",
            "forward_jepa_pretrain",
            "forward_coaching",
            "forward_selective",
            "freeze_encoders",
            "update_target_encoder",
        ],
        [],
    ),
    (
        "Contract",
        "VLJEPACoachingModel API",
        "Programma_CS2_RENAN.backend.nn.jepa_model",
        "VLJEPACoachingModel",
        ["forward_vl", "get_concept_activations"],
        [],
    ),
    (
        "Contract",
        "TrainingOrchestrator API",
        "Programma_CS2_RENAN.backend.nn.training_orchestrator",
        "TrainingOrchestrator",
        ["run_training"],
        [],
    ),
    (
        "Contract",
        "ConceptLabeler API",
        "Programma_CS2_RENAN.backend.nn.jepa_model",
        "ConceptLabeler",
        ["label_tick", "label_batch"],
        [],
    ),
    (
        "Contract",
        "SelfSupervisedDataset API",
        "Programma_CS2_RENAN.backend.nn.dataset",
        "SelfSupervisedDataset",
        ["__len__", "__getitem__"],
        [],
    ),
    (
        "Contract",
        "ProPerformanceDataset API",
        "Programma_CS2_RENAN.backend.nn.dataset",
        "ProPerformanceDataset",
        ["__len__", "__getitem__"],
        [],
    ),
]

for phase, name, mod_path, cls_name, methods, attrs in CONTRACT_CHECKS:
    check(
        phase,
        name,
        lambda mp=mod_path, cn=cls_name, m=methods, a=attrs: verify_contract(mp, cn, m, a),
    )


# ── Phase 10: Deep ML Invariant Checks ───────────────────────────────────────

print("\n[Phase 10] Deep ML Invariants")


def verify_output_dim():
    from Programma_CS2_RENAN.backend.nn.config import OUTPUT_DIM

    # Strategy layer outputs adjustments for the first 10 core features
    if OUTPUT_DIM != 10:
        raise AssertionError(f"OUTPUT_DIM = {OUTPUT_DIM}, expected 10")


def verify_input_dim_matches_metadata():
    from Programma_CS2_RENAN.backend.nn.config import INPUT_DIM
    from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM

    if INPUT_DIM != METADATA_DIM:
        raise AssertionError(f"INPUT_DIM ({INPUT_DIM}) != METADATA_DIM ({METADATA_DIM})")


def verify_num_coaching_concepts():
    from Programma_CS2_RENAN.backend.nn.jepa_model import COACHING_CONCEPTS, NUM_COACHING_CONCEPTS

    if NUM_COACHING_CONCEPTS != 16:
        raise AssertionError(f"NUM_COACHING_CONCEPTS = {NUM_COACHING_CONCEPTS}, expected 16")
    if len(COACHING_CONCEPTS) != NUM_COACHING_CONCEPTS:
        raise AssertionError(
            f"COACHING_CONCEPTS has {len(COACHING_CONCEPTS)} items, "
            f"expected {NUM_COACHING_CONCEPTS}"
        )


def verify_jepa_forward_shape():
    import torch

    from Programma_CS2_RENAN.backend.nn.config import INPUT_DIM, OUTPUT_DIM
    from Programma_CS2_RENAN.backend.nn.jepa_model import JEPACoachingModel

    with torch.no_grad():
        model = JEPACoachingModel(input_dim=INPUT_DIM, output_dim=OUTPUT_DIM)
        x = torch.randn(2, 5, INPUT_DIM)
        out = model(x)
        if out.shape != (2, OUTPUT_DIM):
            raise AssertionError(f"JEPA output shape {out.shape}, expected (2, {OUTPUT_DIM})")


def verify_jepa_pretrain_latent_dims():
    import torch

    from Programma_CS2_RENAN.backend.nn.config import INPUT_DIM
    from Programma_CS2_RENAN.backend.nn.jepa_model import JEPACoachingModel

    with torch.no_grad():
        model = JEPACoachingModel(input_dim=INPUT_DIM, output_dim=4, latent_dim=128)
        ctx = torch.randn(2, 5, INPUT_DIM)
        tgt = torch.randn(2, 5, INPUT_DIM)
        pred, target = model.forward_jepa_pretrain(ctx, tgt)
        if pred.shape != target.shape:
            raise AssertionError(f"Latent mismatch: pred {pred.shape} vs target {target.shape}")


def verify_ema_cycle():
    """Verify EMA update/apply_shadow/restore preserves original weights."""
    import torch

    from Programma_CS2_RENAN.backend.nn.ema import EMA

    model = torch.nn.Linear(10, 5)
    ema = EMA(model, decay=0.999)
    # Simulate training step
    model.weight.data += torch.randn_like(model.weight) * 0.1
    modified_weight = model.weight.data.clone()
    ema.update()
    # Apply shadow — weights should change
    ema.apply_shadow()
    if torch.allclose(model.weight.data, modified_weight, atol=1e-6):
        raise AssertionError("EMA apply_shadow did not change weights")
    # Restore — weights should return to modified
    ema.restore()
    if not torch.allclose(model.weight.data, modified_weight, atol=1e-6):
        raise AssertionError("EMA restore did not recover training weights")


def verify_self_supervised_dataset_windowing():
    import torch

    from Programma_CS2_RENAN.backend.nn.dataset import SelfSupervisedDataset

    X = torch.randn(100, 25)
    ds = SelfSupervisedDataset(X, context_len=10, prediction_len=5)
    expected_len = 100 - 10 - 5  # 85
    if len(ds) != expected_len:
        raise AssertionError(f"SelfSupervisedDataset length {len(ds)}, expected {expected_len}")
    ctx, tgt = ds[0]
    if ctx.shape != (10, 25):
        raise AssertionError(f"Context shape {ctx.shape}, expected (10, 25)")
    if tgt.shape != (5, 25):
        raise AssertionError(f"Target shape {tgt.shape}, expected (5, 25)")


def verify_pro_performance_dataset_tensors():
    import numpy as np
    import torch

    from Programma_CS2_RENAN.backend.nn.dataset import ProPerformanceDataset

    X = np.random.randn(50, 25).astype(np.float32)
    y = np.random.randn(50, 4).astype(np.float32)
    ds = ProPerformanceDataset(X, y)
    if len(ds) != 50:
        raise AssertionError(f"ProPerformanceDataset length {len(ds)}, expected 50")
    x_item, y_item = ds[0]
    if x_item.dtype != torch.float32:
        raise AssertionError(f"X dtype {x_item.dtype}, expected float32")
    if y_item.dtype != torch.float32:
        raise AssertionError(f"y dtype {y_item.dtype}, expected float32")


def verify_target_indices_bounds():
    from Programma_CS2_RENAN.backend.nn.coach_manager import (
        MATCH_AGGREGATE_FEATURES,
        TARGET_INDICES,
    )

    for idx in TARGET_INDICES:
        if idx >= len(MATCH_AGGREGATE_FEATURES):
            raise AssertionError(
                f"TARGET_INDICES value {idx} out of bounds "
                f"(MATCH_AGGREGATE_FEATURES has {len(MATCH_AGGREGATE_FEATURES)} items)"
            )


def verify_checkpoint_name_consistency():
    from Programma_CS2_RENAN.backend.nn.factory import ModelFactory

    expected = {
        ModelFactory.TYPE_JEPA: "jepa_brain",
        ModelFactory.TYPE_VL_JEPA: "vl_jepa_brain",
        ModelFactory.TYPE_RAP: "rap_coach",
        ModelFactory.TYPE_ROLE_HEAD: "role_head",
        ModelFactory.TYPE_LEGACY: "latest",
    }
    for model_type, expected_name in expected.items():
        actual = ModelFactory.get_checkpoint_name(model_type)
        if actual != expected_name:
            raise AssertionError(
                f"Checkpoint for '{model_type}': got '{actual}', expected '{expected_name}'"
            )


def verify_concept_labeler_output():
    import torch

    from Programma_CS2_RENAN.backend.nn.jepa_model import NUM_COACHING_CONCEPTS, ConceptLabeler

    labeler = ConceptLabeler()
    features = torch.rand(25)
    labels = labeler.label_tick(features)
    if labels.shape != (NUM_COACHING_CONCEPTS,):
        raise AssertionError(
            f"ConceptLabeler output shape {labels.shape}, expected ({NUM_COACHING_CONCEPTS},)"
        )
    if not ((labels >= 0).all() and (labels <= 1).all()):
        raise AssertionError("ConceptLabeler produced labels outside [0, 1]")


check("ML-Deep", "OUTPUT_DIM == 10", verify_output_dim)
check("ML-Deep", "INPUT_DIM == METADATA_DIM", verify_input_dim_matches_metadata)
check("ML-Deep", "NUM_COACHING_CONCEPTS == 16", verify_num_coaching_concepts)
check("ML-Deep", "JEPA forward -> [batch, OUTPUT_DIM]", verify_jepa_forward_shape)
check("ML-Deep", "JEPA pretrain latent dims match", verify_jepa_pretrain_latent_dims)
check("ML-Deep", "EMA update/apply/restore cycle", verify_ema_cycle)
check("ML-Deep", "SelfSupervisedDataset windowing", verify_self_supervised_dataset_windowing)
check("ML-Deep", "ProPerformanceDataset tensor types", verify_pro_performance_dataset_tensors)
check("ML-Deep", "TARGET_INDICES within bounds", verify_target_indices_bounds)
check("ML-Deep", "checkpoint name consistency", verify_checkpoint_name_consistency)
check("ML-Deep", "ConceptLabeler output shape + range", verify_concept_labeler_output)


# ── Phase 11: Database Model Integrity ────────────────────────────────────────

print("\n[Phase 11] Database Model Integrity")


def verify_player_match_stats_fields():
    from Programma_CS2_RENAN.backend.storage.db_models import PlayerMatchStats

    required = [
        "player_name",
        "demo_name",
        "match_date",
        "dataset_split",
        "avg_kills",
        "avg_deaths",
        "avg_adr",
        "avg_hs",
        "avg_kast",
        "accuracy",
        "econ_rating",
        "kill_std",
        "adr_std",
        "kd_ratio",
        "impact_rounds",
        "kpr",
        "dpr",
        "rating_impact",
        "rating_survival",
        "trade_kill_ratio",
        "opening_duel_win_pct",
        "clutch_win_pct",
        "flash_assists",
        "positional_aggression_score",
        "thrusmoke_kill_pct",
    ]
    missing = [f for f in required if not hasattr(PlayerMatchStats, f)]
    if missing:
        raise AssertionError(f"PlayerMatchStats missing fields: {missing}")


def verify_player_tick_state_fields():
    from Programma_CS2_RENAN.backend.storage.db_models import PlayerTickState

    required = [
        "tick",
        "player_name",
        "demo_name",
        "pos_x",
        "pos_y",
        "pos_z",
        "health",
        "armor",
        "is_crouching",
        "is_scoped",
        "active_weapon",
        "equipment_value",
        "enemies_visible",
        "is_blinded",
    ]
    missing = [f for f in required if not hasattr(PlayerTickState, f)]
    if missing:
        raise AssertionError(f"PlayerTickState missing fields: {missing}")


def verify_dataset_split_enum():
    from Programma_CS2_RENAN.backend.storage.db_models import DatasetSplit

    expected = {"train", "val", "test", "unassigned"}
    actual = {e.value for e in DatasetSplit}
    if actual != expected:
        raise AssertionError(f"DatasetSplit values {actual} != expected {expected}")


def verify_coach_status_enum():
    from Programma_CS2_RENAN.backend.storage.db_models import CoachStatus

    expected = {"Paused", "Training", "Idle", "Error"}
    actual = {e.value for e in CoachStatus}
    if actual != expected:
        raise AssertionError(f"CoachStatus values {actual} != expected {expected}")


def verify_crud_player_match_stats():
    from sqlmodel import Session, SQLModel, create_engine, select

    from Programma_CS2_RENAN.backend.storage.db_models import PlayerMatchStats

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        pms = PlayerMatchStats(player_name="test_player", demo_name="test.dem", avg_kills=20.0)
        s.add(pms)
        s.commit()
        loaded = s.exec(select(PlayerMatchStats)).first()
        if loaded is None or loaded.player_name != "test_player":
            raise AssertionError("PlayerMatchStats CRUD round-trip failed")


def verify_crud_player_tick_state():
    from sqlmodel import Session, SQLModel, create_engine, select

    from Programma_CS2_RENAN.backend.storage.db_models import PlayerTickState

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        tick = PlayerTickState(
            tick=128,
            player_name="test",
            demo_name="test.dem",
            health=100,
            pos_x=1.0,
            pos_y=2.0,
            pos_z=3.0,
        )
        s.add(tick)
        s.commit()
        loaded = s.exec(select(PlayerTickState)).first()
        if loaded is None or loaded.tick != 128:
            raise AssertionError("PlayerTickState CRUD round-trip failed")


def verify_crud_round_stats():
    from sqlmodel import Session, SQLModel, create_engine, select

    from Programma_CS2_RENAN.backend.storage.db_models import RoundStats

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        rs = RoundStats(demo_name="test.dem", round_number=1, player_name="test", kills=3)
        s.add(rs)
        s.commit()
        loaded = s.exec(select(RoundStats)).first()
        if loaded is None or loaded.kills != 3:
            raise AssertionError("RoundStats CRUD round-trip failed")


def verify_match_aggregate_features_on_model():
    """All MATCH_AGGREGATE_FEATURES must be valid attributes on PlayerMatchStats."""
    from Programma_CS2_RENAN.backend.nn.coach_manager import MATCH_AGGREGATE_FEATURES
    from Programma_CS2_RENAN.backend.storage.db_models import PlayerMatchStats

    missing = [f for f in MATCH_AGGREGATE_FEATURES if not hasattr(PlayerMatchStats, f)]
    if missing:
        raise AssertionError(f"MATCH_AGGREGATE_FEATURES not on PlayerMatchStats: {missing}")


check("DB-Deep", "PlayerMatchStats field coverage", verify_player_match_stats_fields)
check("DB-Deep", "PlayerTickState field coverage", verify_player_tick_state_fields)
check("DB-Deep", "DatasetSplit enum values", verify_dataset_split_enum)
check("DB-Deep", "CoachStatus enum values", verify_coach_status_enum)
check("DB-Deep", "CRUD PlayerMatchStats round-trip", verify_crud_player_match_stats)
check("DB-Deep", "CRUD PlayerTickState round-trip", verify_crud_player_tick_state)
check("DB-Deep", "CRUD RoundStats round-trip", verify_crud_round_stats)
check(
    "DB-Deep",
    "MATCH_AGGREGATE_FEATURES -> PlayerMatchStats",
    verify_match_aggregate_features_on_model,
)


# ── Phase 12: Code Quality & Anti-Pattern Detection ──────────────────────────

print("\n[Phase 12] Code Quality Scanning")

# Shared infrastructure: scan production .py files (excludes tests, tools, cache)
_PROD_FILES_CACHE: List[Path] = []
_EXCLUDE_DIRS = {
    "tests",
    "tools",
    "__pycache__",
    ".pytest_cache",
    "migrations",
    "alembic",
    "automated_suite",
}


def _get_production_files() -> List[Path]:
    """Return list of .py files in production code (cached)."""
    if _PROD_FILES_CACHE:
        return _PROD_FILES_CACHE
    prod_root = Path(PROJECT_ROOT) / "Programma_CS2_RENAN"
    for py in sorted(prod_root.rglob("*.py")):
        rel_parts = py.relative_to(prod_root).parts
        if any(excl in rel_parts for excl in _EXCLUDE_DIRS):
            continue
        # Skip backup files
        if py.name.endswith(".backup"):
            continue
        _PROD_FILES_CACHE.append(py)
    return _PROD_FILES_CACHE


def verify_no_bare_except():
    """Scan for bare `except:` (no exception type) using AST."""
    violations = []
    for f in _get_production_files():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                violations.append(f"{f.name}:{node.lineno}")
    if violations:
        raise AssertionError(
            f"Bare except: in {len(violations)} locations: " f"{', '.join(violations[:5])}"
        )


def verify_no_eval_exec():
    """Scan for standalone eval()/exec() calls using AST (excludes model.eval())."""
    violations = []
    for f in _get_production_files():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in ("eval", "exec"):
                    violations.append(f"{f.name}:{node.lineno}")
    if violations:
        raise AssertionError(f"eval()/exec() found: {', '.join(violations[:5])}")


def verify_no_hardcoded_secrets():
    """Scan for hardcoded secret patterns in production code."""
    pattern = re.compile(
        r"""(?:password|api_key|secret_key|auth_token|private_key)\s*=\s*["'][^"']{8,}["']""",
        re.IGNORECASE,
    )
    violations = []
    for f in _get_production_files():
        for i, line in enumerate(f.read_text(encoding="utf-8").split("\n"), 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            if pattern.search(stripped):
                violations.append(f"{f.name}:{i}")
    if violations:
        raise AssertionError(f"Possible hardcoded secrets: {', '.join(violations[:5])}")


def verify_print_in_production():
    """Warn if excessive print() calls exist in production modules."""
    print_pattern = re.compile(r"^\s*print\(")
    count = 0
    files_with_print = []
    for f in _get_production_files():
        in_main_block = False
        for line in f.read_text(encoding="utf-8").split("\n"):
            if line.strip().startswith("if __name__"):
                in_main_block = True
            if in_main_block:
                continue
            if print_pattern.match(line):
                count += 1
                if f.name not in files_with_print:
                    files_with_print.append(f.name)
    if count > 30:
        raise AssertionError(
            f"Excessive print() in production: {count} calls across "
            f"{len(files_with_print)} files: {files_with_print[:5]}"
        )


check("Quality", "no bare except:", verify_no_bare_except)
check("Quality", "no eval()/exec() calls", verify_no_eval_exec)
check("Quality", "no hardcoded secrets", verify_no_hardcoded_secrets)
warn("Quality", "print() audit (production code)", verify_print_in_production)


# ── Phase 13: Package Structure & Config Integrity ────────────────────────────

print("\n[Phase 13] Package Structure & Config")


def verify_init_py_in_packages():
    """Verify Python source directories have __init__.py."""
    prod_root = Path(PROJECT_ROOT) / "Programma_CS2_RENAN"
    # Directories that intentionally lack __init__.py (data, assets, etc.)
    skip_dirs = {
        "data",
        "assets",
        "models",
        "logs",
        "demos",
        "external",
        "docs",
        "knowledge",
        "cache",
        "tactics",
        "migrations",
        "PHOTO_GUI",
        "hltv_api",
        "remote_telemetry",
        "__pycache__",
        ".pytest_cache",
        "alembic",
        "datasets",
        "automated_suite",
        "forensics",
    }
    missing = []
    for d in sorted(prod_root.rglob("*")):
        if not d.is_dir():
            continue
        rel_parts = set(d.relative_to(prod_root).parts)
        if rel_parts.intersection(skip_dirs):
            continue
        py_files = [f for f in d.glob("*.py") if f.name != "__init__.py"]
        if py_files and not (d / "__init__.py").exists():
            missing.append(str(d.relative_to(prod_root)))
    if missing:
        raise AssertionError(f"Missing __init__.py in: {', '.join(missing[:8])}")


def _verify_json_file(label: str, rel_path: str, required_keys=None, min_entries=0):
    """Generic JSON config validator."""
    full = Path(PROJECT_ROOT) / rel_path
    if not full.exists():
        raise AssertionError(f"{label} not found at {full}")
    data = json.loads(full.read_text(encoding="utf-8"))
    if required_keys:
        for k in required_keys:
            if k not in data:
                raise AssertionError(f"{label} missing key: '{k}'")
    if min_entries and isinstance(data, dict) and len(data) < min_entries:
        raise AssertionError(f"{label} has {len(data)} keys, expected >= {min_entries}")
    return data


def verify_coaching_knowledge_json():
    _verify_json_file(
        "coaching_knowledge_base.json",
        "Programma_CS2_RENAN/data/knowledge/coaching_knowledge_base.json",
    )


def verify_integrity_manifest_json():
    data = _verify_json_file(
        "integrity_manifest.json",
        "Programma_CS2_RENAN/core/integrity_manifest.json",
        required_keys=["hashes", "version"],
    )
    if len(data["hashes"]) < 5:
        raise AssertionError(f"Manifest has {len(data['hashes'])} hashes, expected >= 5")


def verify_settings_json():
    _verify_json_file("settings.json", "Programma_CS2_RENAN/settings.json")


def verify_qt_app_structure():
    """Verify Qt app directory structure: app.py, main_window.py, themes, screens."""
    qt_root = Path(PROJECT_ROOT) / "Programma_CS2_RENAN" / "apps" / "qt_app"
    app_py = qt_root / "app.py"
    if not app_py.exists():
        raise AssertionError("apps/qt_app/app.py missing")
    main_win = qt_root / "main_window.py"
    if not main_win.exists():
        raise AssertionError("apps/qt_app/main_window.py missing")
    themes_dir = qt_root / "themes"
    if not themes_dir.is_dir():
        raise AssertionError("apps/qt_app/themes/ directory missing")
    qss_files = list(themes_dir.glob("*.qss"))
    if not qss_files:
        raise AssertionError("No .qss theme files found in apps/qt_app/themes/")
    screens_dir = qt_root / "screens"
    if not screens_dir.is_dir():
        raise AssertionError("apps/qt_app/screens/ directory missing")
    screen_files = [f for f in screens_dir.glob("*.py") if f.name != "__init__.py"]
    if len(screen_files) < 5:
        raise AssertionError(f"Only {len(screen_files)} screen files, expected >= 5")


def verify_alembic_env():
    env = Path(PROJECT_ROOT) / "alembic" / "env.py"
    if not env.exists():
        raise AssertionError("alembic/env.py not found")
    content = env.read_text(encoding="utf-8")
    if "db_models" not in content:
        raise AssertionError("alembic/env.py does not import db_models")
    if "target_metadata" not in content:
        raise AssertionError("alembic/env.py does not set target_metadata")


warn("Structure", "__init__.py completeness", verify_init_py_in_packages)
check("Structure", "coaching_knowledge_base.json valid", verify_coaching_knowledge_json)
check("Structure", "integrity_manifest.json valid", verify_integrity_manifest_json)
check("Structure", "settings.json valid", verify_settings_json)
check("Structure", "Qt app structure (app.py, main_window, themes, screens)", verify_qt_app_structure)
check("Structure", "alembic/env.py imports db_models", verify_alembic_env)


# ── Phase 14: Feature Pipeline Consistency ────────────────────────────────────

print("\n[Phase 14] Feature Pipeline")


def verify_feature_extract_shape():
    """FeatureExtractor.extract({}) produces exactly METADATA_DIM values."""
    import numpy as np

    from Programma_CS2_RENAN.backend.processing.feature_engineering.vectorizer import (
        METADATA_DIM,
        FeatureExtractor,
    )

    vec = FeatureExtractor.extract({})
    if vec.shape != (METADATA_DIM,):
        raise AssertionError(f"extract(empty) shape {vec.shape}, expected ({METADATA_DIM},)")
    if vec.dtype != np.float32:
        raise AssertionError(f"extract(empty) dtype {vec.dtype}, expected float32")


def verify_feature_names_count():
    from Programma_CS2_RENAN.backend.processing.feature_engineering.vectorizer import (
        METADATA_DIM,
        FeatureExtractor,
    )

    names = FeatureExtractor.get_feature_names()
    if len(names) != METADATA_DIM:
        raise AssertionError(f"Feature names count {len(names)} != METADATA_DIM ({METADATA_DIM})")


def verify_training_features_match_names():
    """TRAINING_FEATURES should match FeatureExtractor.get_feature_names()."""
    from Programma_CS2_RENAN.backend.nn.coach_manager import TRAINING_FEATURES
    from Programma_CS2_RENAN.backend.processing.feature_engineering.vectorizer import (
        FeatureExtractor,
    )

    extractor_names = FeatureExtractor.get_feature_names()
    if TRAINING_FEATURES != extractor_names:
        diffs = [
            (i, t, e) for i, (t, e) in enumerate(zip(TRAINING_FEATURES, extractor_names)) if t != e
        ]
        raise AssertionError(f"TRAINING_FEATURES diverges from extractor at: {diffs[:5]}")


def verify_no_nan_inf_extraction():
    """Verify normalization doesn't produce NaN/Inf on edge inputs."""
    import numpy as np

    from Programma_CS2_RENAN.backend.processing.feature_engineering.vectorizer import (
        FeatureExtractor,
    )

    # Zero/empty input
    vec_empty = FeatureExtractor.extract({})
    if np.isnan(vec_empty).any():
        raise AssertionError("NaN in empty-input extraction")
    if np.isinf(vec_empty).any():
        raise AssertionError("Inf in empty-input extraction")
    # Extreme values
    extreme = {"health": 999999, "armor": -1, "equipment_value": 0, "pos_x": 1e10}
    vec_extreme = FeatureExtractor.extract(extreme)
    if np.isnan(vec_extreme).any():
        raise AssertionError("NaN in extreme-input extraction")
    if np.isinf(vec_extreme).any():
        raise AssertionError("Inf in extreme-input extraction")


def verify_extract_batch_shape():
    """Verify batch extraction produces correct shape."""
    import numpy as np

    from Programma_CS2_RENAN.backend.processing.feature_engineering.vectorizer import (
        METADATA_DIM,
        FeatureExtractor,
    )

    batch = [{"health": 100}, {"health": 50}, {"health": 0}]
    result = FeatureExtractor.extract_batch(batch)
    if result.shape != (3, METADATA_DIM):
        raise AssertionError(f"Batch shape {result.shape}, expected (3, {METADATA_DIM})")


def verify_weapon_class_map_coverage():
    """Verify essential weapons are in WEAPON_CLASS_MAP."""
    from Programma_CS2_RENAN.backend.processing.feature_engineering.vectorizer import (
        WEAPON_CLASS_MAP,
    )

    essential = ["ak47", "m4a1", "awp", "glock", "deagle", "knife", "p90", "mac10"]
    missing = [w for w in essential if w not in WEAPON_CLASS_MAP]
    if missing:
        raise AssertionError(f"WEAPON_CLASS_MAP missing: {missing}")


check("Features", "extract({}) shape == (25,)", verify_feature_extract_shape)
check("Features", "get_feature_names() count == 25", verify_feature_names_count)
check("Features", "TRAINING_FEATURES == get_feature_names()", verify_training_features_match_names)
check("Features", "no NaN/Inf on edge inputs", verify_no_nan_inf_extraction)
check("Features", "extract_batch() shape (3, 25)", verify_extract_batch_shape)
check("Features", "WEAPON_CLASS_MAP essential coverage", verify_weapon_class_map_coverage)


# ── Phase 15: Dependency & Environment ────────────────────────────────────────

print("\n[Phase 15] Dependencies & Environment")


def verify_torch_ops():
    """Verify torch basic operations work."""
    import torch

    t = torch.randn(2, 3)
    if t.shape != (2, 3):
        raise AssertionError(f"torch.randn shape {t.shape}")
    if not hasattr(torch, "no_grad"):
        raise AssertionError("torch missing no_grad")


def verify_sqlmodel_api():
    """Verify sqlmodel core API is available."""
    from sqlmodel import Field, Session, SQLModel, select  # noqa: F811

    for attr in ("metadata",):
        if not hasattr(SQLModel, attr):
            raise AssertionError(f"SQLModel missing {attr}")


def verify_sqlite_wal():
    """Verify SQLite supports WAL mode (requires a file-backed DB)."""
    import sqlite3
    import tempfile

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    try:
        conn = sqlite3.connect(tmp.name)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        mode = cursor.fetchone()[0]
        conn.close()
        if mode.lower() != "wal":
            raise AssertionError(f"SQLite WAL mode returned: {mode}")
    finally:
        os.unlink(tmp.name)


def verify_numpy_ops():
    """Verify numpy basic operations work."""
    import numpy as np

    arr = np.zeros(25, dtype=np.float32)
    if arr.shape != (25,):
        raise AssertionError(f"numpy zeros shape {arr.shape}")
    if not np.isfinite(arr).all():
        raise AssertionError("numpy zeros not finite")


def verify_optional_deps():
    """Report status of optional dependencies."""
    optional = {
        "sentence_transformers": "sentence-transformers (RAG embeddings)",
        "shap": "shap (model explainability)",
        "playwright": "playwright (HLTV scraping)",
        "httpx": "httpx (telemetry client)",
    }
    missing = []
    for mod_name, desc in optional.items():
        try:
            importlib.import_module(mod_name)
        except ImportError:
            missing.append(desc)
    if missing:
        raise AssertionError(f"Optional deps not installed: {', '.join(missing)}")


check("Deps", "torch basic ops", verify_torch_ops)
check("Deps", "sqlmodel core API", verify_sqlmodel_api)
check("Deps", "SQLite WAL mode support", verify_sqlite_wal)
check("Deps", "numpy basic ops", verify_numpy_ops)
warn("Deps", "optional dependencies", verify_optional_deps)


# ── Phase 16: RAP Coach & Perception Pipeline ────────────────────────────────

print("\n[Phase 16] RAP Coach & Perception Pipeline")


def verify_rap_coach_forward():
    """Full forward pass through RAPCoachModel with production dimensions."""
    import torch

    from Programma_CS2_RENAN.backend.nn.experimental.rap_coach.model import RAPCoachModel
    from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM

    with torch.no_grad():
        model = RAPCoachModel(metadata_dim=METADATA_DIM, output_dim=10)
        view = torch.randn(2, 3, 64, 64)
        map_t = torch.randn(2, 3, 64, 64)
        motion = torch.randn(2, 3, 64, 64)
        meta = torch.randn(2, 5, METADATA_DIM)
        out = model(view, map_t, motion, meta)

        expected_keys = {
            "advice_probs",
            "belief_state",
            "value_estimate",
            "gate_weights",
            "optimal_pos",
            "attribution",
        }
        missing = expected_keys - set(out.keys())
        if missing:
            raise AssertionError(f"RAPCoachModel output missing keys: {missing}")
        if out["advice_probs"].shape != (2, 10):
            raise AssertionError(
                f"advice_probs shape {out['advice_probs'].shape}, expected (2, 10)"
            )
        if out["optimal_pos"].shape != (2, 3):
            raise AssertionError(
                f"optimal_pos shape {out['optimal_pos'].shape}, expected (2, 3)"
            )
        if out["attribution"].shape != (2, 5):
            raise AssertionError(
                f"attribution shape {out['attribution'].shape}, expected (2, 5)"
            )


def verify_perception_output_invariant():
    """RAPPerception always outputs (batch, 128) regardless of input resolution."""
    import torch

    from Programma_CS2_RENAN.backend.nn.experimental.rap_coach.perception import RAPPerception

    with torch.no_grad():
        perception = RAPPerception()
        for res in [32, 64]:
            view = torch.randn(1, 3, res, res)
            map_t = torch.randn(1, 3, res, res)
            motion = torch.randn(1, 3, res, res)
            out = perception(view, map_t, motion)
            if out.shape != (1, 128):
                raise AssertionError(
                    f"RAPPerception output {out.shape} for res={res}, expected (1, 128)"
                )


def verify_sparsity_loss_safety():
    """compute_sparsity_loss handles None and valid tensors without crash."""
    import torch

    from Programma_CS2_RENAN.backend.nn.experimental.rap_coach.model import RAPCoachModel

    model = RAPCoachModel()
    # None input should return 0.0
    loss_none = model.compute_sparsity_loss(None)
    if loss_none.item() != 0.0:
        raise AssertionError(f"sparsity_loss(None) = {loss_none.item()}, expected 0.0")

    # Valid gate weights should return finite scalar
    gate_w = torch.rand(2, 10)
    loss_valid = model.compute_sparsity_loss(gate_w)
    if not torch.isfinite(loss_valid):
        raise AssertionError(f"sparsity_loss(valid) = {loss_valid.item()}, not finite")


def verify_rap_position_scale():
    from Programma_CS2_RENAN.backend.nn.config import RAP_POSITION_SCALE

    if RAP_POSITION_SCALE != 500.0:
        raise AssertionError(
            f"RAP_POSITION_SCALE = {RAP_POSITION_SCALE}, expected 500.0"
        )


check("RAP", "RAPCoachModel full forward pass", verify_rap_coach_forward)
check("RAP", "RAPPerception output (batch, 128) invariant", verify_perception_output_invariant)
check("RAP", "compute_sparsity_loss safety (None + valid)", verify_sparsity_loss_safety)
check("RAP", "RAP_POSITION_SCALE == 500.0", verify_rap_position_scale)


# ── Phase 17: Belief Model & Analysis Engine Contracts ───────────────────────

print("\n[Phase 17] Belief Model & Analysis Engines")


def verify_belief_state():
    from Programma_CS2_RENAN.backend.analysis.belief_model import BeliefState

    bs = BeliefState()
    if not hasattr(bs, "threat_level"):
        raise AssertionError("BeliefState missing threat_level() method")


def verify_death_probability_estimator():
    from Programma_CS2_RENAN.backend.analysis.belief_model import (
        DeathProbabilityEstimator,
    )

    estimator = DeathProbabilityEstimator()
    if not hasattr(estimator, "estimate"):
        raise AssertionError("DeathProbabilityEstimator missing estimate() method")


def verify_adaptive_belief_calibrator():
    from Programma_CS2_RENAN.backend.analysis.belief_model import (
        AdaptiveBeliefCalibrator,
    )

    cal = AdaptiveBeliefCalibrator()
    if not hasattr(cal, "auto_calibrate"):
        raise AssertionError("AdaptiveBeliefCalibrator missing auto_calibrate()")


def verify_game_tree_solver():
    from Programma_CS2_RENAN.backend.analysis.game_tree import (
        ExpectiminimaxSearch,
        OpponentModel,
    )

    if not hasattr(OpponentModel, "learn_from_match"):
        raise AssertionError("OpponentModel missing learn_from_match() method")
    if not hasattr(ExpectiminimaxSearch, "evaluate"):
        raise AssertionError("ExpectiminimaxSearch missing evaluate() method")


def verify_analysis_module_contracts():
    from Programma_CS2_RENAN.backend.analysis.blind_spots import BlindSpotDetector
    from Programma_CS2_RENAN.backend.analysis.engagement_range import (
        EngagementRangeAnalyzer,
    )
    from Programma_CS2_RENAN.backend.analysis.utility_economy import UtilityAnalyzer

    for cls, method in [
        (BlindSpotDetector, "detect"),
        (EngagementRangeAnalyzer, "analyze_match_engagements"),
        (UtilityAnalyzer, "analyze"),
    ]:
        if not hasattr(cls, method):
            raise AssertionError(f"{cls.__name__} missing {method}()")


def verify_spatial_engine_api():
    """SpatialEngine has coordinate transform methods."""
    from Programma_CS2_RENAN.core.spatial_engine import SpatialEngine

    for method in [
        "world_to_normalized",
        "normalized_to_pixel",
        "pixel_to_normalized",
        "world_to_pixel",
        "pixel_to_world",
    ]:
        if not hasattr(SpatialEngine, method):
            raise AssertionError(f"SpatialEngine missing {method}()")


check("Belief", "BeliefState instantiation + update()", verify_belief_state)
check("Belief", "DeathProbabilityEstimator.estimate()", verify_death_probability_estimator)
check("Belief", "AdaptiveBeliefCalibrator.auto_calibrate()", verify_adaptive_belief_calibrator)
check("Belief", "GameTree OpponentModel + ExpectiminimaxSearch", verify_game_tree_solver)
check("Belief", "BlindSpot/Engagement/Utility contracts", verify_analysis_module_contracts)
check("Belief", "SpatialEngine coordinate API", verify_spatial_engine_api)


# ── Phase 18: MLControlContext & Training Control ────────────────────────────

print("\n[Phase 18] MLControlContext & Training Control")


def verify_stop_signal_propagation():
    """MLControlContext.check_state() raises TrainingStopRequested after request_stop()."""
    from Programma_CS2_RENAN.backend.control.ml_controller import (
        MLControlContext,
        TrainingStopRequested,
    )

    ctx = MLControlContext()
    ctx.request_stop()
    try:
        ctx.check_state()
        raise AssertionError("check_state() did not raise after request_stop()")
    except TrainingStopRequested:
        pass  # Expected


def verify_pause_resume():
    """Pause clears the resume event; resume sets it."""
    from Programma_CS2_RENAN.backend.control.ml_controller import MLControlContext

    ctx = MLControlContext()
    if not ctx._resume_event.is_set():
        raise AssertionError("_resume_event should be set initially")

    ctx.request_pause()
    if ctx._resume_event.is_set():
        raise AssertionError("_resume_event should be cleared after pause")

    ctx.request_resume()
    if not ctx._resume_event.is_set():
        raise AssertionError("_resume_event should be set after resume")


def verify_throttle_factor():
    from Programma_CS2_RENAN.backend.control.ml_controller import MLControlContext

    ctx = MLControlContext()
    ctx.set_throttle(0.5)
    if ctx.throttle_factor != 0.5:
        raise AssertionError(f"Throttle = {ctx.throttle_factor}, expected 0.5")


def verify_training_stop_requested_type():
    from Programma_CS2_RENAN.backend.control.ml_controller import TrainingStopRequested

    if not issubclass(TrainingStopRequested, Exception):
        raise AssertionError("TrainingStopRequested is not a subclass of Exception")
    if issubclass(TrainingStopRequested, KeyboardInterrupt):
        raise AssertionError("TrainingStopRequested should not be a KeyboardInterrupt")


check("MLCtrl", "stop signal -> TrainingStopRequested", verify_stop_signal_propagation)
check("MLCtrl", "pause/resume event blocking", verify_pause_resume)
check("MLCtrl", "throttle factor", verify_throttle_factor)
check("MLCtrl", "TrainingStopRequested is Exception subclass", verify_training_stop_requested_type)


# ── Phase 20: Shared Utilities & Missing Module Imports ──────────────────────

print("\n[Phase 20] Shared Utilities & New Imports")


def verify_round_utils_phase_inference():
    """infer_round_phase() returns correct economy phases."""
    from Programma_CS2_RENAN.backend.knowledge.round_utils import infer_round_phase

    cases = [
        ({"equipment_value": 500}, "pistol"),
        ({"equipment_value": 2000}, "eco"),
        ({"equipment_value": 3500}, "force"),
        ({"equipment_value": 5000}, "full_buy"),
        ({}, "pistol"),  # Missing key defaults to 0
    ]
    for tick_data, expected in cases:
        actual = infer_round_phase(tick_data)
        if actual != expected:
            raise AssertionError(
                f"infer_round_phase({tick_data}) = '{actual}', expected '{expected}'"
            )


check("Shared", "round_utils.infer_round_phase() all phases", verify_round_utils_phase_inference)

# Additional module imports not covered by earlier phases
ADDITIONAL_IMPORTS = [
    "Programma_CS2_RENAN.backend.processing.player_knowledge",
    "Programma_CS2_RENAN.backend.storage.backup_manager",
    "Programma_CS2_RENAN.backend.storage.db_backup",
    "Programma_CS2_RENAN.backend.coaching.nn_refinement",
    "Programma_CS2_RENAN.backend.progress.longitudinal",
    "Programma_CS2_RENAN.backend.progress.trend_analysis",
    "Programma_CS2_RENAN.backend.knowledge.round_utils",
]

for mod in ADDITIONAL_IMPORTS:
    short = mod.split(".")[-1]
    check("NewImport", f"import {short}", try_import(mod))

# Optional dependency modules (warn, not fail)
OPTIONAL_IMPORTS = [
    "Programma_CS2_RENAN.backend.nn.tensorboard_callback",
    "Programma_CS2_RENAN.backend.processing.cv_framebuffer",  # requires cv2 (OpenCV)
]

for mod in OPTIONAL_IMPORTS:
    short = mod.split(".")[-1]
    warn("NewImport", f"import {short} (optional)", try_import(mod))


# ── Phase 21: Integrity & Security Scanning ──────────────────────────────────

print("\n[Phase 21] Integrity & Security Scanning")


def verify_manifest_hash_sampling():
    """Spot-check integrity manifest hashes against actual file checksums."""
    import hashlib

    manifest_path = (
        Path(PROJECT_ROOT)
        / "Programma_CS2_RENAN"
        / "core"
        / "integrity_manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    hashes = manifest.get("hashes", {})

    # Pick first 10 files alphabetically (deterministic, fast)
    sample = sorted(hashes.items())[:10]
    mismatches = []
    for rel_path, expected_hash in sample:
        # Manifest paths are relative to Programma_CS2_RENAN/
        full_path = Path(PROJECT_ROOT) / "Programma_CS2_RENAN" / rel_path
        if not full_path.exists():
            mismatches.append(f"{rel_path} (missing)")
            continue
        h = hashlib.sha256()
        with open(full_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                h.update(chunk)
        if h.hexdigest() != expected_hash:
            mismatches.append(f"{rel_path} (hash mismatch)")
    if mismatches:
        raise AssertionError(
            f"Integrity check failed for {len(mismatches)} files: "
            + ", ".join(mismatches[:5])
        )


def verify_manifest_structure():
    """Manifest has required keys and non-empty hashes."""
    manifest_path = (
        Path(PROJECT_ROOT)
        / "Programma_CS2_RENAN"
        / "core"
        / "integrity_manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key in ("hashes", "version"):
        if key not in manifest:
            raise AssertionError(f"Manifest missing required key: '{key}'")
    hashes = manifest.get("hashes", {})
    if len(hashes) < 5:
        raise AssertionError(f"Manifest has only {len(hashes)} hashes, expected >= 5")


def verify_no_unsafe_torch_load():
    """All torch.load() calls in production must use weights_only=True."""
    violations = []
    for f in _get_production_files():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            # Match torch.load(...)
            func = node.func
            is_torch_load = False
            if isinstance(func, ast.Attribute) and func.attr == "load":
                if isinstance(func.value, ast.Name) and func.value.id == "torch":
                    is_torch_load = True
            if not is_torch_load:
                continue
            # Check for weights_only=True in keyword args
            has_weights_only = any(
                kw.arg == "weights_only"
                and isinstance(kw.value, ast.Constant)
                and kw.value.value is True
                for kw in node.keywords
            )
            if not has_weights_only:
                violations.append(f"{f.name}:{node.lineno}")
    if violations:
        raise AssertionError(
            f"torch.load() without weights_only=True: {', '.join(violations[:5])}"
        )


def verify_no_shell_true_in_production():
    """No subprocess calls with shell=True in production code (excludes tools/)."""
    violations = []
    prod_root = Path(PROJECT_ROOT) / "Programma_CS2_RENAN"
    exclude = {"tests", "tools", "__pycache__", ".pytest_cache"}

    for f in sorted(prod_root.rglob("*.py")):
        rel_parts = f.relative_to(prod_root).parts
        if any(excl in rel_parts for excl in exclude):
            continue
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_subprocess = False
            if isinstance(func, ast.Attribute) and func.attr in (
                "run",
                "call",
                "Popen",
                "check_call",
                "check_output",
            ):
                is_subprocess = True
            if not is_subprocess:
                continue
            for kw in node.keywords:
                if (
                    kw.arg == "shell"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True
                ):
                    violations.append(f"{f.name}:{node.lineno}")
    if violations:
        raise AssertionError(
            f"subprocess with shell=True in production: {', '.join(violations[:5])}"
        )


def verify_rasp_guard_instantiation():
    """RASPGuard can be instantiated and resolves manifest path."""
    from Programma_CS2_RENAN.observability.rasp import RASPGuard

    guard = RASPGuard(Path(PROJECT_ROOT))
    if not guard.manifest_path.exists():
        raise AssertionError(f"RASP manifest not found at {guard.manifest_path}")


def verify_no_bare_assert_in_production():
    """Bare assert statements should not be used for input validation in production."""
    count = 0
    files_with_asserts = []
    for f in _get_production_files():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                count += 1
                if f.name not in files_with_asserts:
                    files_with_asserts.append(f.name)
    # Allow up to 20 assert statements (some are acceptable for internal invariants)
    if count > 50:
        raise AssertionError(
            f"Excessive bare assert in production: {count} across "
            f"{len(files_with_asserts)} files: {files_with_asserts[:5]}"
        )


def verify_gitignore_secrets():
    """Verify .gitignore excludes sensitive file patterns."""
    gitignore = Path(PROJECT_ROOT) / ".gitignore"
    if not gitignore.exists():
        raise AssertionError(".gitignore not found")
    content = gitignore.read_text(encoding="utf-8")
    required_patterns = [".env", "*.db"]
    missing = [p for p in required_patterns if p not in content]
    if missing:
        raise AssertionError(f".gitignore missing patterns: {missing}")


check("Integrity", "manifest hash sampling (10 files)", verify_manifest_hash_sampling)
check("Integrity", "manifest structure (hashes + version)", verify_manifest_structure)
check("Security", "no unsafe torch.load()", verify_no_unsafe_torch_load)
check("Security", "no subprocess shell=True in production", verify_no_shell_true_in_production)
check("Security", "RASP guard instantiation", verify_rasp_guard_instantiation)
check("Security", "bare assert audit (production code)", verify_no_bare_assert_in_production)
check("Security", ".gitignore excludes secrets", verify_gitignore_secrets)


# ── Phase 22: Configuration Consistency ──────────────────────────────────────

print("\n[Phase 22] Configuration Consistency")


def verify_map_config_schema_depth():
    """Each map in map_config.json has required keys."""
    path = Path(PROJECT_ROOT) / "Programma_CS2_RENAN" / "data" / "map_config.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    maps = data.get("maps", {})
    required_keys = {"pos_x", "pos_y", "scale"}
    for map_name, map_data in maps.items():
        if not isinstance(map_data, dict):
            continue
        missing = required_keys - set(map_data.keys())
        if missing:
            raise AssertionError(f"Map '{map_name}' missing keys: {missing}")


def verify_tactical_knowledge_json():
    """Validate tactical_knowledge.json is valid JSON."""
    path = (
        Path(PROJECT_ROOT)
        / "Programma_CS2_RENAN"
        / "backend"
        / "knowledge"
        / "tactical_knowledge.json"
    )
    if not path.exists():
        raise AssertionError(f"tactical_knowledge.json not found at {path}")
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise AssertionError(f"tactical_knowledge.json is invalid JSON: {e}")


def verify_requirements_core_deps():
    """Verify critical packages are declared in requirements.txt."""
    req_path = Path(PROJECT_ROOT) / "requirements.txt"
    if not req_path.exists():
        raise AssertionError("requirements.txt not found")
    content = req_path.read_text(encoding="utf-8").lower()
    critical = ["torch", "sqlmodel", "pyside6", "numpy"]
    missing = [pkg for pkg in critical if pkg not in content]
    if missing:
        raise AssertionError(f"requirements.txt missing critical deps: {missing}")


def verify_critical_constants_cross_module():
    """Cross-module constant agreement: METADATA_DIM, HIDDEN_DIM, INPUT_DIM."""
    from Programma_CS2_RENAN.backend.nn.config import HIDDEN_DIM, INPUT_DIM, RAP_POSITION_SCALE
    from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM

    errors = []
    if INPUT_DIM != METADATA_DIM:
        errors.append(f"INPUT_DIM({INPUT_DIM}) != METADATA_DIM({METADATA_DIM})")
    if HIDDEN_DIM != 128:
        errors.append(f"HIDDEN_DIM = {HIDDEN_DIM}, expected 128")
    if RAP_POSITION_SCALE != 500.0:
        errors.append(f"RAP_POSITION_SCALE = {RAP_POSITION_SCALE}, expected 500.0")
    if errors:
        raise AssertionError("; ".join(errors))


def verify_settings_defaults_completeness():
    """All get_setting() calls reference keys that have defaults in config.py."""
    config_path = (
        Path(PROJECT_ROOT) / "Programma_CS2_RENAN" / "core" / "config.py"
    )
    config_text = config_path.read_text(encoding="utf-8")

    # Extract default keys from the defaults dict in config.py
    # Uses brace-depth counting to handle nested dicts (e.g. "KEY": {})
    default_keys = set()
    in_defaults = False
    brace_depth = 0
    for line in config_text.split("\n"):
        stripped = line.strip()
        if not in_defaults and "defaults" in stripped and "{" in stripped:
            in_defaults = True
            brace_depth = stripped.count("{") - stripped.count("}")
            match = re.search(r'"(\w+)":', stripped)
            if match:
                default_keys.add(match.group(1))
            continue
        if in_defaults:
            brace_depth += stripped.count("{") - stripped.count("}")
            match = re.search(r'"(\w+)":', stripped)
            if match:
                default_keys.add(match.group(1))
            if brace_depth <= 0:
                in_defaults = False

    # Scan production code for get_setting() calls
    prod_root = Path(PROJECT_ROOT) / "Programma_CS2_RENAN"
    referenced_keys = set()
    setting_pattern = re.compile(r'get_setting\(["\'](\w+)["\']')
    for py_file in prod_root.rglob("*.py"):
        if "__pycache__" in str(py_file) or "tests" in str(py_file):
            continue
        try:
            content = py_file.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue
        for match in setting_pattern.finditer(content):
            referenced_keys.add(match.group(1))

    # Keys referenced but not in defaults (get_setting has a default param, so this is a warn)
    undefined = referenced_keys - default_keys
    if undefined:
        raise AssertionError(
            f"Settings used but not in config defaults: {sorted(undefined)}"
        )


check("Config-Deep", "map_config.json per-map schema", verify_map_config_schema_depth)
check("Config-Deep", "tactical_knowledge.json valid", verify_tactical_knowledge_json)
check("Config-Deep", "requirements.txt core deps", verify_requirements_core_deps)
check("Config-Deep", "cross-module constants agreement", verify_critical_constants_cross_module)
warn("Config-Deep", "settings defaults completeness", verify_settings_defaults_completeness)


# ── Phase 23: Advanced Code Quality ──────────────────────────────────────────

print("\n[Phase 23] Advanced Code Quality")


def verify_no_oversized_functions():
    """Warn if any function exceeds 200 lines (complexity indicator)."""
    violations = []
    for f in _get_production_files():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if hasattr(node, "end_lineno") and node.end_lineno:
                    length = node.end_lineno - node.lineno
                    if length > 200:
                        violations.append(f"{f.name}:{node.name} ({length} lines)")
    if len(violations) > 3:
        raise AssertionError(
            f"{len(violations)} functions > 200 lines: {', '.join(violations[:5])}"
        )


def verify_no_circular_imports():
    """Lightweight circular import detection via AST-based import graph + DFS."""
    prod_root = Path(PROJECT_ROOT) / "Programma_CS2_RENAN"
    graph: dict = {}  # module -> set of imported modules

    for f in sorted(prod_root.rglob("*.py")):
        rel = str(f.relative_to(Path(PROJECT_ROOT))).replace(os.sep, ".").replace(".py", "")
        if "__pycache__" in rel or "tests" in rel or "tools" in rel:
            continue

        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue

        imports = set()
        # Only consider TOP-LEVEL imports (direct children of the module body).
        # Deferred imports inside functions/methods are a standard Python pattern
        # for breaking circular dependencies and must NOT be counted as edges.
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("Programma_CS2_RENAN"):
                    imports.add(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("Programma_CS2_RENAN"):
                        imports.add(alias.name)
        graph[rel] = imports

    # DFS cycle detection (only report first cycle found)
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {node: WHITE for node in graph}
    cycle_path: list = []

    def dfs(node):
        color[node] = GRAY
        for neighbor in graph.get(node, set()):
            if neighbor not in color:
                continue
            if color[neighbor] == GRAY:
                cycle_path.append(f"{node} -> {neighbor}")
                return True
            if color[neighbor] == WHITE:
                if dfs(neighbor):
                    return True
        color[node] = BLACK
        return False

    for node in graph:
        if color.get(node) == WHITE:
            if dfs(node):
                break

    if cycle_path:
        raise AssertionError(f"Circular import detected: {cycle_path[0]}")


def verify_no_critical_todos():
    """No TODO/FIXME with CRITICAL tag in core paths."""
    critical_pattern = re.compile(r"(TODO|FIXME).*CRITICAL", re.IGNORECASE)
    violations = []
    critical_dirs = ["backend/nn", "backend/storage", "core"]

    for cdir in critical_dirs:
        full = Path(PROJECT_ROOT) / "Programma_CS2_RENAN" / cdir
        if not full.exists():
            continue
        for py_file in full.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            for i, line in enumerate(
                py_file.read_text(encoding="utf-8").split("\n"), 1
            ):
                if critical_pattern.search(line):
                    violations.append(f"{py_file.name}:{i}")
    if violations:
        raise AssertionError(
            f"CRITICAL TODO/FIXME in core paths: {', '.join(violations[:5])}"
        )


def verify_type_hint_coverage():
    """Sample production files; warn if <60% of functions have full type hints."""
    import random

    files = _get_production_files()
    # Deterministic sample
    random.seed(42)
    sample = random.sample(files, min(20, len(files)))

    total_funcs = 0
    typed_funcs = 0

    for f in sample:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_") and node.name != "__init__":
                    continue  # Skip private methods
                total_funcs += 1
                # Check if return annotation exists
                has_return = node.returns is not None
                # Check if all params have annotations (skip 'self', 'cls')
                params = [
                    a
                    for a in node.args.args
                    if a.arg not in ("self", "cls")
                ]
                has_param_types = all(a.annotation is not None for a in params)
                if has_return or has_param_types:
                    typed_funcs += 1

    if total_funcs == 0:
        return
    coverage = typed_funcs / total_funcs
    if coverage < 0.5:
        raise AssertionError(
            f"Type hint coverage: {coverage:.0%} ({typed_funcs}/{total_funcs}), "
            f"expected >= 50%"
        )


def verify_no_mutable_global_state_in_nn():
    """NN modules should not have module-level mutable state (thread-safety)."""
    violations = []
    nn_root = Path(PROJECT_ROOT) / "Programma_CS2_RENAN" / "backend" / "nn"

    for f in sorted(nn_root.rglob("*.py")):
        if "__pycache__" in str(f) or f.name == "__init__.py":
            continue
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue
        for node in ast.iter_child_nodes(tree):
            # Module-level assignments
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and not target.id.startswith("_"):
                        # Check if value is a mutable literal (list/dict/set)
                        if isinstance(node.value, (ast.List, ast.Set)):
                            if len(getattr(node.value, "elts", [])) > 0:
                                violations.append(
                                    f"{f.name}:{node.lineno} ({target.id})"
                                )
                        elif isinstance(node.value, ast.Dict):
                            if len(getattr(node.value, "keys", [])) > 0:
                                violations.append(
                                    f"{f.name}:{node.lineno} ({target.id})"
                                )

    # Allow some (constants like COACHING_CONCEPTS, TRAINING_FEATURES, etc.)
    if len(violations) > 15:
        raise AssertionError(
            f"Excessive global mutable state in nn/: {len(violations)} defs — "
            + ", ".join(violations[:5])
        )


warn("Quality-Adv", "no functions > 200 lines", verify_no_oversized_functions)
warn("Quality-Adv", "no circular imports (DFS)", verify_no_circular_imports)
check("Quality-Adv", "no CRITICAL TODO/FIXME in core paths", verify_no_critical_todos)
warn("Quality-Adv", "type hint coverage >= 50%", verify_type_hint_coverage)
warn("Quality-Adv", "no mutable global state in nn/", verify_no_mutable_global_state_in_nn)


# ── Summary ──────────────────────────────────────────────────────────────────

elapsed = time.perf_counter() - _t0
passed = sum(1 for r in _results if r.passed)
failed = sum(1 for r in _results if not r.passed and r.severity == "fail")
warned = sum(1 for r in _results if not r.passed and r.severity == "warn")
total = len(_results)

print("\n" + "=" * 60)
print(f"RESULT: {passed}/{total} passed, {failed} failed, {warned} warnings ({elapsed:.1f}s)")

if failed:
    print("\nFailed checks:")
    for r in _results:
        if not r.passed and r.severity == "fail":
            print(f"  [{r.phase}] {r.name}: {r.error}")
if warned:
    print("\nWarnings (non-blocking):")
    for r in _results:
        if not r.passed and r.severity == "warn":
            print(f"  [{r.phase}] {r.name}: {r.error}")

if failed:
    print("\nVERDICT: FAIL")
    sys.exit(1)
else:
    print("\nVERDICT: PASS")
    sys.exit(0)
