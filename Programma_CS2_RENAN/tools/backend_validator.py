#!/usr/bin/env python3
"""
Backend Validator — Unified backend validation for Macena CS2 Analyzer.

Merges and supersedes:
  - Clinical_Integration_Validator.py (MCIV v2.0)
  - system_audit_suite.py (Deep Audit v4.0)

7 sections: Environment, Database, Model Zoo, Analysis, Coaching,
            Resource Integrity, Service Health.

Exit codes: 0 = PASS, 1 = FAIL
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# --- Use shared infrastructure ---
from _infra import PROJECT_ROOT, SOURCE_ROOT, BaseValidator, Severity, path_stabilize

PROJECT_ROOT, SOURCE_ROOT = path_stabilize()

import torch

from Programma_CS2_RENAN.core.config import DATABASE_URL, MODELS_DIR, SETTINGS_PATH
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.backend_validator")


class BackendValidator(BaseValidator):
    """
    Unified backend validation — the single authoritative backend gate.
    Replaces Clinical_Integration_Validator + system_audit_suite.
    """

    def __init__(self):
        super().__init__("Macena Backend Validator", version="3.0")

    def define_checks(self):
        self._check_environment()
        self._check_database()
        self._check_model_zoo()
        self._check_analysis_modules()
        self._check_coaching_pipeline()
        self._check_resource_integrity()
        self._check_service_health()

    # -----------------------------------------------------------------
    # Section 1: Environment
    # -----------------------------------------------------------------
    def _check_environment(self):
        self.console.section("Environment", 1, 7)

        self.check(
            "Environment",
            "PyTorch available",
            hasattr(torch, "__version__"),
            detail=f"v{torch.__version__}",
        )

        cuda = torch.cuda.is_available()
        self.check(
            "Environment",
            "CUDA status",
            cuda,
            detail=f"available={cuda}" + (f" ({torch.cuda.get_device_name(0)})" if cuda else ""),
            severity=Severity.INFO,
        )

        # Critical dependencies
        deps_ok = True
        missing = []
        for mod in ["psutil", "kivymd", "sklearn", "demoparser2", "sqlmodel"]:
            try:
                __import__(mod)
            except ImportError:
                deps_ok = False
                missing.append(mod)

        self.check(
            "Environment",
            "Critical dependencies",
            deps_ok,
            error=f"Missing: {', '.join(missing)}" if missing else "",
            detail=f"5/5 loaded" if deps_ok else f"{5 - len(missing)}/5",
        )

        # METADATA_DIM
        from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM

        self.check("Environment", "METADATA_DIM", METADATA_DIM > 0, detail=f"dim={METADATA_DIM}")

        # Torch version bound
        major, minor = (int(x) for x in torch.__version__.split(".")[:2])
        self.check(
            "Environment",
            "PyTorch >= 2.0",
            major >= 2,
            detail=f"v{torch.__version__}",
            severity=Severity.WARNING,
        )

    # -----------------------------------------------------------------
    # Section 2: Database
    # -----------------------------------------------------------------
    def _check_database(self):
        self.console.section("Database", 2, 7)

        from sqlalchemy import inspect as sa_inspect
        from sqlalchemy import text

        from Programma_CS2_RENAN.backend.storage.database import get_db_manager, init_database

        init_database()
        db = get_db_manager()

        # Connectivity
        with db.get_session() as session:
            res = session.exec(text("SELECT 1")).first()
            val = res[0] if res is not None else None
            self.check("Database", "Connectivity (SELECT 1)", val == 1)

            # WAL mode (NEW check)
            journal = session.exec(text("PRAGMA journal_mode")).first()
            mode = journal[0] if journal else "unknown"
            self.check(
                "Database",
                "WAL mode active",
                mode == "wal",
                detail=f"mode={mode}",
                error=f"Expected WAL, got {mode}",
            )

        # Schema tables
        insp = sa_inspect(db.engine)
        tables = insp.get_table_names()
        required = [
            "playerprofile",
            "coachinginsight",
            "playermatchstats",
            "playertickstate",
            "coachstate",
            "roundstats",
        ]
        for t in required:
            self.check("Database", f"Table: {t}", t in tables)

        # CRUD smoke — verify the query actually executes
        from sqlmodel import select

        from Programma_CS2_RENAN.backend.storage.db_models import CoachState

        try:
            with db.get_session() as session:
                state = session.exec(select(CoachState)).first()
                self.check(
                    "Database",
                    "CoachState CRUD smoke",
                    True,
                    detail="row exists" if state else "table empty (queryable)",
                )
        except Exception as e:
            self.check("Database", "CoachState CRUD smoke", False, error=str(e))

        # Backup recency (NEW check)
        backup_dir = SOURCE_ROOT / "backend" / "storage" / "backups"
        if backup_dir.exists():
            backups = sorted(backup_dir.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
            if backups:
                age_days = (
                    datetime.now() - datetime.fromtimestamp(backups[0].stat().st_mtime)
                ).days
                self.check(
                    "Database",
                    "Backup recency (< 7 days)",
                    age_days < 7,
                    detail=f"latest={backups[0].name}, age={age_days}d",
                    severity=Severity.WARNING,
                )
            else:
                self.check(
                    "Database",
                    "Backup recency",
                    False,
                    error="No backup files found",
                    severity=Severity.WARNING,
                )
        else:
            self.check(
                "Database",
                "Backup directory exists",
                False,
                error="backups/ directory missing",
                severity=Severity.WARNING,
            )

    # -----------------------------------------------------------------
    # Section 3: Model Zoo
    # -----------------------------------------------------------------
    def _check_model_zoo(self):
        self.console.section("Model Zoo", 3, 7)

        from Programma_CS2_RENAN.backend.nn.factory import ModelFactory
        from Programma_CS2_RENAN.backend.processing.feature_engineering import METADATA_DIM

        # Default (TeacherRefinementNN)
        model = ModelFactory.get_model("default", input_dim=METADATA_DIM, output_dim=4)
        self.check(
            "Model Zoo", "ModelFactory 'default'", model is not None, detail="TeacherRefinementNN"
        )

        # F8-16: Model Zoo uses torch.randn() inputs — smoke tests (does model load/run?),
        # not correctness tests. See tests/test_deployment_readiness.py for deeper checks.
        if model is not None:
            x = torch.randn(1, 1, METADATA_DIM)
            with torch.no_grad():
                out = model(x)
            self.check(
                "Model Zoo",
                "Default inference shape",
                out.shape == (1, 4),
                detail=f"{METADATA_DIM}->4 dim",
            )

        # JEPA
        jepa = ModelFactory.get_model(
            "jepa", input_dim=METADATA_DIM, output_dim=METADATA_DIM, latent_dim=128
        )
        self.check("Model Zoo", "ModelFactory 'jepa'", jepa is not None, detail="JEPACoachingModel")

        # VL-JEPA + forward_vl
        vl_jepa = ModelFactory.get_model(
            "vl-jepa", input_dim=METADATA_DIM, output_dim=METADATA_DIM, latent_dim=128
        )
        self.check(
            "Model Zoo", "ModelFactory 'vl-jepa'", vl_jepa is not None, detail="VLJEPACoachingModel"
        )

        if vl_jepa is not None:
            x = torch.randn(2, 5, METADATA_DIM)
            with torch.no_grad():
                result = vl_jepa.forward_vl(x)
            ok = (
                "concept_probs" in result
                and "coaching_output" in result
                and result["concept_probs"].shape[1] == 16
            )
            self.check(
                "Model Zoo",
                "VL-JEPA forward_vl",
                ok,
                detail=f"16 concepts, output={result['coaching_output'].shape}",
            )

        # NeuralRoleHead
        role_head = ModelFactory.get_model("role_head")
        self.check(
            "Model Zoo", "ModelFactory 'role_head'", role_head is not None, detail="NeuralRoleHead"
        )

        if role_head is not None:
            x = torch.randn(4, 5)
            with torch.no_grad():
                probs = role_head(x)
            ok = probs.shape == (4, 5) and torch.allclose(
                probs.sum(dim=1), torch.ones(4), atol=0.01
            )
            self.check(
                "Model Zoo", "RoleHead softmax sums to 1.0", ok, detail=f"shape={probs.shape}"
            )

    # -----------------------------------------------------------------
    # Section 4: Analysis Modules
    # -----------------------------------------------------------------
    def _check_analysis_modules(self):
        self.console.section("Analysis Modules", 4, 7)

        # Demo Format Adapter (Prop 12)
        try:
            from Programma_CS2_RENAN.backend.data_sources.demo_format_adapter import (
                DemoFormatAdapter,
            )

            adapter = DemoFormatAdapter()
            changelog = adapter.get_changelog()
            self.check(
                "Analysis",
                "DemoFormatAdapter",
                len(changelog) > 0,
                detail=f"{len(changelog)} changelog entries",
            )
        except Exception as e:
            self.check("Analysis", "DemoFormatAdapter", False, error=str(e))

        # Temporal Baseline Decay (Prop 11)
        try:
            from Programma_CS2_RENAN.backend.processing.baselines.pro_baseline import (
                TemporalBaselineDecay,
            )

            decay = TemporalBaselineDecay()
            ref = datetime.now()
            w = decay.compute_weight(ref - timedelta(days=45), ref)
            self.check(
                "Analysis", "TemporalBaselineDecay", 0.1 <= w <= 1.0, detail=f"weight={w:.3f}"
            )
        except Exception as e:
            self.check("Analysis", "TemporalBaselineDecay", False, error=str(e))

        # Engagement Range Analyzer (Prop 7)
        try:
            from Programma_CS2_RENAN.backend.analysis.engagement_range import (
                EngagementRangeAnalyzer,
            )

            era = EngagementRangeAnalyzer()
            profile = era.compute_profile([300.0, 800.0, 1200.0, 2500.0])
            self.check(
                "Analysis",
                "EngagementRangeAnalyzer",
                profile.total_kills == 4,
                detail=f"{profile.total_kills} kills profiled",
            )
        except Exception as e:
            self.check("Analysis", "EngagementRangeAnalyzer", False, error=str(e))

        # Adaptive Belief Calibrator (Prop 6)
        try:
            from Programma_CS2_RENAN.backend.analysis.belief_model import (
                AdaptiveBeliefCalibrator,
                DeathProbabilityEstimator,
            )

            estimator = DeathProbabilityEstimator()
            cal = AdaptiveBeliefCalibrator(estimator)
            has_calibrate = callable(getattr(cal, "auto_calibrate", None))
            has_bounds = hasattr(cal, "MIN_SAMPLES")
            self.check(
                "Analysis",
                "AdaptiveBeliefCalibrator",
                has_calibrate and has_bounds,
                detail=f"auto_calibrate={has_calibrate}, bounds={has_bounds}",
            )
        except Exception as e:
            self.check("Analysis", "AdaptiveBeliefCalibrator", False, error=str(e))

        # Coaching Dialogue Engine (Prop 9)
        try:
            from Programma_CS2_RENAN.backend.services.coaching_dialogue import (
                CoachingDialogueEngine,
            )

            cde = CoachingDialogueEngine()
            has_api = isinstance(cde.is_available, bool)
            has_methods = callable(getattr(cde, "start_session", None)) and callable(
                getattr(cde, "respond", None)
            )
            self.check(
                "Analysis",
                "CoachingDialogueEngine",
                has_api and has_methods,
                detail=f"available={cde.is_available}, methods={has_methods}",
            )
        except Exception as e:
            self.check("Analysis", "CoachingDialogueEngine", False, error=str(e))

        # Chronovisor Scanner (Prop 5)
        try:
            from Programma_CS2_RENAN.backend.nn.rap_coach.chronovisor_scanner import (
                CriticalMoment,
                ScanResult,
            )

            cm = CriticalMoment(
                match_id=0,
                start_tick=0,
                peak_tick=10,
                end_tick=20,
                severity=0.5,
                type="test",
                description="probe",
                scale="micro",
            )
            self.check(
                "Analysis",
                "Chronovisor CriticalMoment",
                hasattr(cm, "context_ticks") and hasattr(cm, "suggested_review"),
                detail="context_ticks + suggested_review",
            )
        except Exception as e:
            self.check("Analysis", "Chronovisor CriticalMoment", False, error=str(e))

    # -----------------------------------------------------------------
    # Section 5: Coaching Pipeline
    # -----------------------------------------------------------------
    def _check_coaching_pipeline(self):
        self.console.section("Coaching Pipeline", 5, 7)

        # CoachingService (COPER mode)
        try:
            from Programma_CS2_RENAN.backend.services.coaching_service import CoachingService

            cs = CoachingService()
            has_generate = callable(getattr(cs, "generate_new_insights", None))
            has_coper = callable(getattr(cs, "_generate_coper_insights", None))
            self.check(
                "Coaching",
                "CoachingService (COPER)",
                has_generate and has_coper,
                detail=f"generate={has_generate}, coper={has_coper}",
            )
        except Exception as e:
            self.check("Coaching", "CoachingService", False, error=str(e))

        # Experience Bank
        try:
            from Programma_CS2_RENAN.backend.knowledge.experience_bank import ExperienceBank

            eb = ExperienceBank()
            has_add = callable(getattr(eb, "add_experience", None))
            has_retrieve = callable(getattr(eb, "retrieve_similar", None))
            self.check(
                "Coaching",
                "ExperienceBank",
                has_add and has_retrieve,
                detail=f"add={has_add}, retrieve={has_retrieve}",
            )
        except Exception as e:
            self.check("Coaching", "ExperienceBank", False, error=str(e))

        # RAG Knowledge
        try:
            from Programma_CS2_RENAN.backend.knowledge.rag_knowledge import KnowledgeRetriever

            kr = KnowledgeRetriever()
            has_retrieve = callable(getattr(kr, "retrieve", None))
            self.check(
                "Coaching", "KnowledgeRetriever", has_retrieve, detail=f"retrieve={has_retrieve}"
            )
        except Exception as e:
            self.check("Coaching", "KnowledgeRetriever", False, error=str(e))

    # -----------------------------------------------------------------
    # Section 6: Resource Integrity
    # -----------------------------------------------------------------
    def _check_resource_integrity(self):
        self.console.section("Resource Integrity", 6, 7)

        # KV layout
        kv = SOURCE_ROOT / "apps" / "desktop_app" / "layout.kv"
        self.check("Resources", "layout.kv exists", kv.exists())

        # PHOTO_GUI
        gui = SOURCE_ROOT / "PHOTO_GUI"
        self.check(
            "Resources",
            "PHOTO_GUI directory",
            gui.exists() and len(list(gui.iterdir())) > 5,
            detail=f"{len(list(gui.iterdir()))} assets" if gui.exists() else "missing",
        )

        # Models directory
        models_dir = Path(MODELS_DIR)
        self.check("Resources", "Models directory", models_dir.exists())

        # Settings file
        self.check("Resources", "Settings file", Path(SETTINGS_PATH).exists())

        # map_config.json
        map_cfg = SOURCE_ROOT / "data" / "map_config.json"
        if map_cfg.exists():
            try:
                data = json.loads(map_cfg.read_text(encoding="utf-8"))
                self.check(
                    "Resources",
                    "map_config.json valid",
                    isinstance(data, dict) and len(data) > 0,
                    detail=f"{len(data)} maps",
                )
            except Exception as e:
                self.check("Resources", "map_config.json", False, error=str(e))
        else:
            self.check("Resources", "map_config.json exists", False)

        # Integrity manifest staleness (NEW check)
        manifest = SOURCE_ROOT / "core" / "integrity_manifest.json"
        if manifest.exists():
            age_h = (
                datetime.now() - datetime.fromtimestamp(manifest.stat().st_mtime)
            ).total_seconds() / 3600
            self.check(
                "Resources",
                "Integrity manifest freshness",
                age_h < 168,  # 7 days
                detail=f"age={age_h:.0f}h",
                severity=Severity.WARNING,
            )
        else:
            self.check("Resources", "Integrity manifest exists", False, severity=Severity.WARNING)

        # Model checkpoint staleness (NEW check)
        ckpt_dir = SOURCE_ROOT / "models"
        if ckpt_dir.exists():
            ckpts = list(ckpt_dir.glob("*.pt")) + list(ckpt_dir.glob("*.pth"))
            if ckpts:
                newest = max(ckpts, key=lambda p: p.stat().st_mtime)
                age_days = (datetime.now() - datetime.fromtimestamp(newest.stat().st_mtime)).days
                self.check(
                    "Resources",
                    "Model checkpoint freshness",
                    age_days < 30,
                    detail=f"newest={newest.name}, age={age_days}d",
                    severity=Severity.WARNING,
                )
            else:
                self.check(
                    "Resources",
                    "Model checkpoint freshness",
                    False,
                    error="No .pt/.pth checkpoint files found in models directory",
                    severity=Severity.WARNING,
                )

    # -----------------------------------------------------------------
    # Section 7: Service Health
    # -----------------------------------------------------------------
    def _check_service_health(self):
        self.console.section("Service Health", 7, 7)

        # PID file check (informational — daemon not running is not a failure)
        pid_f = SOURCE_ROOT / "hltv_sync.pid"
        if pid_f.exists():
            try:
                import psutil

                pid = int(pid_f.read_text().strip())
                alive = psutil.pid_exists(pid)
                self.check(
                    "Services",
                    "HLTV sync daemon",
                    alive,
                    detail=f"PID {pid}, alive={alive}",
                    severity=Severity.INFO,
                )
            except Exception as e:
                self.check(
                    "Services",
                    "HLTV sync daemon",
                    False,
                    detail=f"PID file exists, verify failed: {e}",
                    severity=Severity.INFO,
                )
        else:
            self.check(
                "Services",
                "HLTV sync daemon",
                False,
                detail="not running (no PID file)",
                severity=Severity.INFO,
            )

        # Windows registry check
        if sys.platform == "win32":
            try:
                import winreg

                key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
                val, _ = winreg.QueryValueEx(key, "MacenaCS2Analyzer_HLTV")
                winreg.CloseKey(key)
                registered = "--loop" in val or "--hltv-service" in val
                self.check(
                    "Services",
                    "Windows registry entry",
                    registered,
                    detail=(
                        "auto-start registered" if registered else "key exists but missing flags"
                    ),
                )
            except Exception:
                self.check(
                    "Services",
                    "Windows registry entry",
                    False,
                    detail="not registered",
                    severity=Severity.INFO,
                )

        # Dependency version bounds
        try:
            import sqlmodel

            sm_ver = getattr(sqlmodel, "__version__", "0.0.0")
            parts = [int(x) for x in sm_ver.split(".")[:3]]
            ver_ok = tuple(parts) >= (0, 0, 14)
            self.check(
                "Services",
                "SQLModel version >= 0.0.14",
                ver_ok,
                detail=f"v{sm_ver}",
                severity=Severity.WARNING if not ver_ok else Severity.INFO,
            )
        except Exception:
            self.check("Services", "SQLModel version", False, error="SQLModel not installed")


if __name__ == "__main__":
    validator = BackendValidator()
    sys.exit(validator.run())
