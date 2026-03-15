"""UserProfileViewModel — loads and saves PlayerProfile from DB."""

from PySide6.QtCore import QObject, QThreadPool, Signal

from Programma_CS2_RENAN.apps.qt_app.core.worker import Worker
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.qt_user_profile_vm")


class UserProfileViewModel(QObject):
    """Loads/saves PlayerProfile in background. Signals auto-marshal to main thread."""

    profile_loaded = Signal(dict)
    is_loading_changed = Signal(bool)
    error_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_loading = False

    def load_profile(self):
        if self._is_loading:
            return
        self._is_loading = True
        self.is_loading_changed.emit(True)
        self.error_changed.emit("")

        worker = Worker(self._bg_load)
        worker.signals.result.connect(self._on_loaded)
        worker.signals.error.connect(self._on_error)
        QThreadPool.globalInstance().start(worker)

    def save_profile(self, bio: str, role: str):
        """Save bio/role in background, then reload."""
        worker = Worker(self._bg_save, bio, role)
        worker.signals.result.connect(self._on_loaded)
        worker.signals.error.connect(self._on_error)
        QThreadPool.globalInstance().start(worker)

    def _bg_load(self):
        from sqlmodel import select

        from Programma_CS2_RENAN.backend.storage.database import get_db_manager
        from Programma_CS2_RENAN.backend.storage.db_models import PlayerProfile
        from Programma_CS2_RENAN.core.config import get_setting

        player = get_setting("CS2_PLAYER_NAME", "")

        with get_db_manager().get_session() as session:
            profile = session.exec(
                select(PlayerProfile).where(PlayerProfile.player_name == player)
            ).first() if player else None

            if profile:
                return {
                    "name": profile.player_name,
                    "bio": profile.bio or "No description yet.",
                    "role": profile.role or "All-Rounder",
                }

        # No profile found — return defaults
        return {
            "name": player or "Player",
            "bio": "No description yet.",
            "role": "All-Rounder",
        }

    def _bg_save(self, bio: str, role: str):
        from sqlmodel import select

        from Programma_CS2_RENAN.backend.storage.database import get_db_manager
        from Programma_CS2_RENAN.backend.storage.db_models import PlayerProfile
        from Programma_CS2_RENAN.core.config import get_setting

        player = get_setting("CS2_PLAYER_NAME", "")
        if not player:
            raise ValueError("Player name not set.")

        with get_db_manager().get_session() as session:
            profile = session.exec(
                select(PlayerProfile).where(PlayerProfile.player_name == player)
            ).first()
            if not profile:
                profile = PlayerProfile(player_name=player)
                session.add(profile)
            profile.bio = bio.strip() or "No description yet."
            profile.role = role.strip() or "All-Rounder"
            session.commit()

        logger.info("Profile saved: bio=%s, role=%s", bio[:30], role)
        return {"name": player, "bio": profile.bio, "role": profile.role}

    def _on_loaded(self, data):
        self._is_loading = False
        self.is_loading_changed.emit(False)
        if data is not None:
            self.profile_loaded.emit(data)

    def _on_error(self, msg):
        logger.error("user_profile_vm error: %s", msg)
        self._is_loading = False
        self.is_loading_changed.emit(False)
        self.error_changed.emit(str(msg))
