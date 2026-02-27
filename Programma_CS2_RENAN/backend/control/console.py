import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from Programma_CS2_RENAN.backend.storage.state_manager import state_manager
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.console")


class SystemState(Enum):
    IDLE = "idle"
    BUSY = "busy"
    MAINTENANCE = "maintenance"
    ERROR = "error"


class ServiceStatus(Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    CRASHED = "crashed"
    STARTING = "starting"


class ServiceSupervisor:
    """
    Authoritative supervisor for background daemons.
    Manages PIDs, liveness, and restarts.
    """

    # F5-25: Named constants — no magic numbers in restart logic.
    _MAX_RETRIES: int = 3           # Max auto-restarts before giving up
    _RETRY_RESET_WINDOW_S: float = 3600.0  # 1 h — retry counter resets after this
    _RESTART_DELAY_S: float = 5.0   # Seconds to wait before each restart attempt

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.services: Dict[str, Dict] = {
            "hunter": {
                "script": "Programma_CS2_RENAN/hltv_sync_service.py",
                "process": None,
                "status": ServiceStatus.STOPPED,
                "last_start": None,
                "retries": 0,
            }
        }
        self._lock = threading.Lock()

    def start_service(self, name: str):
        with self._lock:
            if name not in self.services:
                raise ValueError(f"Unknown service: {name}")

            svc = self.services[name]
            if svc["status"] == ServiceStatus.RUNNING:
                return

            logger.info("Supervisor: Starting service '%s'...", name)
            svc["status"] = ServiceStatus.STARTING

            try:
                # Use sys.executable to ensure we use the same venv
                script_path = self.project_root / svc["script"]

                # Setup environment with PYTHONPATH
                env = os.environ.copy()
                env["PYTHONPATH"] = str(self.project_root) + (
                    os.pathsep + env.get("PYTHONPATH", "") if env.get("PYTHONPATH") else ""
                )

                # Launch as a subprocess. We'll monitor it in a thread.
                process = subprocess.Popen(
                    [sys.executable, str(script_path)],
                    cwd=str(self.project_root),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    # On Windows, use creationflags to prevent console windows from popping up
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )

                svc["process"] = process
                svc["status"] = ServiceStatus.RUNNING
                svc["last_start"] = datetime.now(timezone.utc)
                logger.info("Supervisor: Service '%s' started with PID %s", name, process.pid)

                # Start monitoring thread
                threading.Thread(
                    target=self._monitor_process, args=(name, process), daemon=True
                ).start()

            except Exception as e:
                svc["status"] = ServiceStatus.CRASHED
                logger.error("Supervisor: Failed to start service '%s': %s", name, e)

    def stop_service(self, name: str):
        with self._lock:
            svc = self.services.get(name)
            if not svc or not svc["process"]:
                return

            logger.info("Supervisor: Stopping service '%s'...", name)
            process = svc["process"]
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

            svc["status"] = ServiceStatus.STOPPED
            svc["process"] = None
            logger.info("Supervisor: Service '%s' stopped.", name)

    def _monitor_process(self, name: str, process: subprocess.Popen):
        """Threaded monitor for a service process."""
        stdout, stderr = process.communicate()
        exit_code = process.returncode

        with self._lock:
            svc = self.services[name]
            if svc["status"] == ServiceStatus.STOPPED:
                return  # Manual stop

            svc["status"] = ServiceStatus.CRASHED
            svc["process"] = None
            logger.error("Supervisor: Service '%s' exited with code %s", name, exit_code)
            if stderr:
                logger.error("Supervisor: Service '%s' error output: %s", name, stderr)

            # Auto-restart logic (max 3 retries in 1 hour, resets after 1 hour).
            # Lock ordering: Timer fires after _lock is released here; start_service
            # re-acquires _lock independently — no deadlock since 5s delay >> lock hold time.
            last_start = svc.get("last_start")
            if last_start and (datetime.now(timezone.utc) - last_start).total_seconds() > self._RETRY_RESET_WINDOW_S:
                svc["retries"] = 0
            if svc["retries"] < self._MAX_RETRIES:
                svc["retries"] += 1
                logger.warning(
                    "Supervisor: Auto-restarting '%s' (Attempt %s)...", name, svc["retries"]
                )
                threading.Timer(self._RESTART_DELAY_S, self.start_service, args=(name,)).start()
            else:
                logger.error(
                    "Supervisor: Service '%s' exceeded max retries (%s). Manual restart required.",
                    name,
                    self._MAX_RETRIES,
                )

    def get_status(self) -> Dict:
        with self._lock:
            return {
                name: {
                    "status": svc["status"].value,
                    "last_start": svc["last_start"].isoformat() if svc["last_start"] else None,
                    "pid": svc["process"].pid if svc["process"] else None,
                }
                for name, svc in self.services.items()
            }


class Console:
    """
    The Unified Control Console (Singleton).
    Authority for ML, Ingestion, and System State.
    """

    # F5-25: Named TTL constants — avoids magic numbers in cache logic.
    _BASELINE_CACHE_TTL_S: float = 60.0       # Baseline status cache lifetime (seconds)
    _TRAINING_DATA_CACHE_TTL_S: float = 120.0  # Training data cache lifetime (seconds)

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(Console, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # Robustly determine project root relative to this file
        # console.py is in Programma_CS2_RENAN/backend/control/
        # We need to go up 3 levels to reach the repo root (Macena_cs2_analyzer)
        current_file = Path(__file__).resolve()
        self.project_root = current_file.parent.parent.parent.parent

        self.state = SystemState.IDLE
        try:
            self.supervisor = ServiceSupervisor(self.project_root)

            # Phase 2: Domain Managers
            from Programma_CS2_RENAN.backend.control.db_governor import DatabaseGovernor
            from Programma_CS2_RENAN.backend.control.ingest_manager import IngestionManager
            from Programma_CS2_RENAN.backend.control.ml_controller import MLController

            self.ingest_manager = IngestionManager()
            self.db_governor = DatabaseGovernor()
            self.ml_controller = MLController()
        except Exception as e:
            logger.error("Console init failed during subsystem creation: %s", e)
            # Clean up partially created components
            if hasattr(self, "supervisor"):
                del self.supervisor
            raise

        # Baseline cache: avoid querying DB + computing decay every 1s poll
        self._baseline_cache = None
        self._baseline_cache_ts = 0.0
        self._baseline_ttl = self._BASELINE_CACHE_TTL_S

        # Training data cache: avoid rglob on large demo directories every poll
        self._training_data_cache = None
        self._training_data_cache_ts = 0.0
        self._training_data_ttl = self._TRAINING_DATA_CACHE_TTL_S

        self._initialized = True
        logger.info("Unified Control Console Initialized.")

    def boot(self):
        """System-wide startup sequence."""
        logger.info("Console: Booting system subsystems...")

        # 1. Start background services
        self.supervisor.start_service("hunter")
        time.sleep(1)
        svcs = self.supervisor.get_status()
        hunter_status = svcs.get("hunter", {}).get("status", "unknown")
        if hunter_status != "running":
            logger.warning("Console: Hunter service status after boot: %s", hunter_status)

        # 2. Start unified ingestion scan (Low Priority)
        # DISABLE AUTO-START: User requested manual control only (Task 3)
        # self.ingest_manager.scan_all(high_priority=False)

        # 3. Check DB Integrity
        self._audit_databases()

        logger.info("Console: System boot complete.")

    def shutdown(self):
        """Graceful shutdown of all subsystems."""
        logger.info("Console: Initiating graceful shutdown...")
        self.supervisor.stop_service("hunter")
        self.ingest_manager.stop()
        self.ml_controller.stop_training()
        # Brief wait for async stops to propagate
        _shutdown_clean = False
        for _ in range(10):
            ml_status = self.ml_controller.get_status()
            ingest_status = self.ingest_manager.get_status()
            if not ml_status.get("is_running") and not ingest_status.get("is_running"):
                _shutdown_clean = True
                break
            time.sleep(0.5)
        # F5-34: Log warning if timeout hit without clean shutdown.
        if not _shutdown_clean:
            logger.warning(
                "Console: Shutdown timeout — subsystems may still be running "
                "(ML=%s, Ingest=%s). Process exit will force termination.",
                self.ml_controller.get_status().get("is_running"),
                self.ingest_manager.get_status().get("is_running"),
            )
        logger.info("Console: Shutdown complete.")

    def _audit_databases(self):
        """Verifies presence of Tier 1 & 2 databases."""
        try:
            audit = self.db_governor.audit_storage()
            logger.info(
                "Console: Storage Audit - T1/2: %.2fMB, T3: %s matches",
                audit["tier1_2_size"] / (1024 * 1024),
                audit["tier3_count"],
            )

            integrity = self.db_governor.verify_integrity()
            if not integrity.get("monolith"):
                logger.error("Console: MONOLITH INTEGRITY FAILURE!")
                self.state = SystemState.ERROR
            else:
                logger.info("Console: Database Tier 1/2 connection verified.")
        except Exception as e:
            logger.error("Console: Database audit failed: %s", e)
            self.state = SystemState.ERROR

    def get_system_status(self) -> Dict:
        """Aggregate health report with per-subsystem error isolation."""

        def _safe_call(label, fn):
            try:
                return fn()
            except Exception as e:
                logger.warning("Console: Status fetch failed for '%s': %s", label, e)
                return {"error": str(e)}

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "state": self._compute_state(),
            "services": _safe_call("services", self.supervisor.get_status),
            "teacher": _safe_call("teacher", lambda: state_manager.get_status("teacher")),
            "ml_controller": _safe_call("ml_controller", self.ml_controller.get_status),
            "ingestion": _safe_call("ingestion", self.ingest_manager.get_status),
            "storage": _safe_call("storage", self.db_governor.audit_storage),
            "baseline": self._get_baseline_status(),
            "training_data": _safe_call("training_data", self._get_training_data_progress),
        }

    def _compute_state(self) -> str:
        """Compute live system state from subsystem health."""
        if self.state == SystemState.ERROR:
            return SystemState.ERROR.value
        try:
            svcs = self.supervisor.get_status()
            any_crashed = any(s.get("status") == "crashed" for s in svcs.values())
            if any_crashed:
                return SystemState.ERROR.value
        except Exception as e:
            logger.debug("Failed to get supervisor status: %s", e)
        return self.state.value

    def _get_baseline_status(self) -> Dict:
        """Get temporal baseline health status (Proposal 11). Cached for 60s."""
        now = time.monotonic()
        if (
            self._baseline_cache is not None
            and (now - self._baseline_cache_ts) < self._baseline_ttl
        ):
            return self._baseline_cache

        try:
            from sqlmodel import func, select

            from Programma_CS2_RENAN.backend.processing.baselines.pro_baseline import (
                TemporalBaselineDecay,
            )
            from Programma_CS2_RENAN.backend.storage.database import get_db_manager
            from Programma_CS2_RENAN.backend.storage.db_models import ProPlayerStatCard

            db = get_db_manager()
            with db.get_session() as session:
                card_count = session.exec(select(func.count(ProPlayerStatCard.id))).one()

            decay = TemporalBaselineDecay()
            temporal = decay.get_temporal_baseline()

            result = {
                "stat_cards": card_count,
                "temporal_metrics": len(temporal),
                "mode": "temporal" if card_count >= 10 else "legacy",
            }
        except Exception as e:
            logger.warning("Console: Baseline status fetch failed: %s", e)
            result = {"stat_cards": 0, "temporal_metrics": 0, "mode": "unavailable"}

        self._baseline_cache = result
        self._baseline_cache_ts = now
        return result

    def _get_training_data_progress(self) -> Dict:
        """Report how many .dem files have been processed vs available. Cached for 120s."""
        now = time.monotonic()
        if (
            self._training_data_cache is not None
            and (now - self._training_data_cache_ts) < self._training_data_ttl
        ):
            return self._training_data_cache

        from pathlib import Path

        from sqlmodel import func, select

        from Programma_CS2_RENAN.backend.storage.database import get_db_manager
        from Programma_CS2_RENAN.backend.storage.db_models import PlayerMatchStats
        from Programma_CS2_RENAN.core.config import get_setting

        db = get_db_manager()

        # Count processed demos in DB
        with db.get_session() as session:
            pro_processed = session.exec(
                select(func.count(PlayerMatchStats.id)).where(PlayerMatchStats.is_pro == True)
            ).one()
            user_processed = session.exec(
                select(func.count(PlayerMatchStats.id)).where(PlayerMatchStats.is_pro == False)
            ).one()
            # Split distribution
            trained_on = session.exec(
                select(func.count(PlayerMatchStats.id)).where(
                    PlayerMatchStats.dataset_split == "train"
                )
            ).one()

        # Count available .dem files on disk
        pro_dem_available = 0
        user_dem_available = 0

        # F5-07: rglob on network/large drives can hang; cap at 10 000 and catch errors.
        _DEMO_COUNT_CAP = 10_000

        def _count_demos(directory: Path) -> int:
            try:
                count = 0
                for _ in directory.rglob("*.dem"):
                    count += 1
                    if count >= _DEMO_COUNT_CAP:
                        logger.warning("Demo count capped at %s in %s", _DEMO_COUNT_CAP, directory)
                        return count
                return count
            except Exception as exc:
                logger.warning("Failed to count demos in %s: %s", directory, exc)
                return 0

        pro_path = get_setting("PRO_DEMO_PATH", "")
        if pro_path:
            pro_dir = Path(pro_path)
            if pro_dir.exists():
                pro_dem_available = _count_demos(pro_dir)

        user_path = get_setting("USER_DEMO_PATH", "")
        if user_path:
            user_dir = Path(user_path)
            if user_dir.exists():
                user_dem_available = _count_demos(user_dir)

        total_processed = pro_processed + user_processed
        total_available = pro_dem_available + user_dem_available

        result = {
            "pro_demos_processed": pro_processed,
            "user_demos_processed": user_processed,
            "total_processed": total_processed,
            "pro_dem_on_disk": pro_dem_available,
            "user_dem_on_disk": user_dem_available,
            "total_on_disk": total_available,
            "trained_on": trained_on,
            "ready_for_training": total_processed >= 10,
        }

        self._training_data_cache = result
        self._training_data_cache_ts = now
        return result

    # --- ML Control Wrappers ---
    def start_training(self):
        self.ml_controller.start_training()
        return self.ml_controller.get_status()

    def stop_training(self):
        self.ml_controller.stop_training()
        return self.ml_controller.get_status()

    def pause_training(self):
        self.ml_controller.pause_training()
        return self.ml_controller.get_status()

    def resume_training(self):
        self.ml_controller.resume_training()
        return self.ml_controller.get_status()


# Global entry point
def get_console() -> Console:
    return Console()
