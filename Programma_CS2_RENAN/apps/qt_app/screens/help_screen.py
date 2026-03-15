"""Help screen — two-panel topic browser with search."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from Programma_CS2_RENAN.apps.qt_app.core.i18n_bridge import i18n
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.qt_help")

# help_system is NOT YET IMPLEMENTED — import guard
try:
    from Programma_CS2_RENAN.backend.knowledge_base.help_system import get_help_system

    _HELP_AVAILABLE = True
except ImportError:
    _HELP_AVAILABLE = False

_FALLBACK_TOPICS = [
    {
        "id": "getting_started",
        "title": "Getting Started",
        "content": (
            "Welcome to Macena CS2 Analyzer!\n\n"
            "1. Go to Settings and set your in-game name in Profile\n"
            "2. Set your demo folder path (where CS2 saves .dem files)\n"
            "3. The app will automatically detect and analyze your matches\n"
            "4. View your match history, performance stats, and AI coaching\n\n"
            "Your CS2 demo folder is typically located at:\n"
            "  Steam/steamapps/common/Counter-Strike Global Offensive/game/csgo/replays/"
        ),
    },
    {
        "id": "demo_analysis",
        "title": "Demo Analysis",
        "content": (
            "How Demo Analysis Works\n\n"
            "1. Place your .dem files in the configured demo folder\n"
            "2. The analyzer detects new files and queues them for processing\n"
            "3. Each demo is parsed tick-by-tick to extract player actions\n"
            "4. Features are computed: positioning, utility usage, economy, etc.\n"
            "5. Results appear in Match History and Performance screens\n\n"
            "Pro demos can also be ingested to build a reference baseline\n"
            "that the AI coach uses to compare your play against pro patterns."
        ),
    },
    {
        "id": "ai_coach",
        "title": "AI Coach",
        "content": (
            "The AI Coach Screen\n\n"
            "The coach provides personalized insights based on your analyzed demos.\n\n"
            "Features:\n"
            "- Belief State: shows model confidence based on data volume\n"
            "- Recent Insights: actionable coaching advice ranked by severity\n"
            "- Chat: interactive conversation with the AI coach (requires Ollama)\n\n"
            "To enable chat:\n"
            "1. Install Ollama: curl -fsSL https://ollama.com/install.sh | sh\n"
            "2. Pull the model: ollama pull llama3.2:3b\n"
            "3. Start Ollama: ollama serve\n"
            "4. Open the Chat panel in the Coach screen"
        ),
    },
    {
        "id": "steam_setup",
        "title": "Steam Integration",
        "content": (
            "Connecting Your Steam Account\n\n"
            "Navigate to the Steam Config screen from the Dashboard.\n\n"
            "SteamID64:\n"
            "- Your unique 17-digit Steam identifier\n"
            "- Find it at steamid.io by entering your Steam profile URL\n\n"
            "Steam API Key:\n"
            "- Required for advanced stats retrieval\n"
            "- Register at steamcommunity.com/dev/apikey\n"
            "- Use 'localhost' as the domain name when registering"
        ),
    },
    {
        "id": "keyboard_shortcuts",
        "title": "Navigation",
        "content": (
            "App Navigation\n\n"
            "Use the sidebar on the left to switch between screens:\n\n"
            "- Home: Dashboard overview and quick actions\n"
            "- Coach: AI coaching insights and chat\n"
            "- Match History: Browse analyzed demos\n"
            "- Performance: Advanced analytics and stats\n"
            "- Tactical Viewer: 2D demo replay viewer\n"
            "- Settings: Theme, fonts, paths, language\n"
            "- Help: This screen"
        ),
    },
    {
        "id": "troubleshooting",
        "title": "Troubleshooting",
        "content": (
            "Common Issues\n\n"
            "No matches showing:\n"
            "- Verify your demo folder path in Settings\n"
            "- Ensure .dem files are present in the folder\n"
            "- Check that ingestion has run (Dashboard status)\n\n"
            "Coach chat offline:\n"
            "- Ollama must be installed and running\n"
            "- Run 'ollama serve' in a terminal\n"
            "- Ensure the llama3.2:3b model is downloaded\n\n"
            "Fonts not changing:\n"
            "- Some custom fonts require the font files in PHOTO_GUI/\n"
            "- Restart the app after changing fonts"
        ),
    },
]


class HelpScreen(QWidget):
    """Two-panel help browser with search and topic content."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._topics = []
        self._build_ui()

    def on_enter(self):
        """Load topics when screen becomes visible."""
        self._load_topics()

    def retranslate(self):
        """Update all translatable text when language changes."""
        self._title_label.setText(i18n.get_text("help_center"))
        self._search_input.setPlaceholderText(i18n.get_text("search_placeholder"))
        # Reset content label only if no topic is selected
        if self._topic_list.currentItem() is None:
            self._content_label.setText(i18n.get_text("select_topic"))

    # ── UI ──

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self._title_label = QLabel(i18n.get_text("help_center"))
        self._title_label.setObjectName("section_title")
        self._title_label.setFont(QFont("Roboto", 22, QFont.Bold))
        self._title_label.setStyleSheet("color: #ffffff;")
        layout.addWidget(self._title_label)

        # Two-panel layout
        panels = QHBoxLayout()
        panels.setSpacing(12)

        # ── Left Panel: search + topic list ──
        left = QWidget()
        left.setFixedWidth(240)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(i18n.get_text("search_placeholder"))
        self._search_input.textChanged.connect(self._on_search)
        left_layout.addWidget(self._search_input)

        self._topic_list = QListWidget()
        self._topic_list.setObjectName("help_topic_list")
        self._topic_list.setStyleSheet(
            "QListWidget { font-size: 15px; }"
            "QListWidget::item { padding: 8px 12px; }"
            "QListWidget::item:selected { background: #2a2a3a; color: #ffffff; }"
        )
        self._topic_list.currentItemChanged.connect(self._on_topic_selected)
        left_layout.addWidget(self._topic_list, 1)

        panels.addWidget(left)

        # ── Right Panel: content viewer ──
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.NoFrame)

        self._content_label = QLabel(i18n.get_text("select_topic"))
        self._content_label.setWordWrap(True)
        self._content_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._content_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._content_label.setFont(QFont("Roboto", 14))
        self._content_label.setStyleSheet(
            "color: #e0e0e0; line-height: 1.6; padding: 16px; "
            "background: transparent;"
        )
        right_scroll.setWidget(self._content_label)

        panels.addWidget(right_scroll, 1)
        layout.addLayout(panels, 1)

    # ── Data ──

    def _load_topics(self):
        if _HELP_AVAILABLE:
            try:
                hs = get_help_system()
                self._topics = hs.get_all_topics()
            except Exception:
                logger.warning("help_system failed, using fallback topics")
                self._topics = list(_FALLBACK_TOPICS)
        else:
            self._topics = list(_FALLBACK_TOPICS)

        self._populate_list(self._topics)

    def _populate_list(self, topics: list):
        self._topic_list.clear()
        for topic in topics:
            item = QListWidgetItem(topic.get("title", "Untitled"))
            item.setData(Qt.UserRole, topic)
            self._topic_list.addItem(item)

        if self._topic_list.count() > 0:
            self._topic_list.setCurrentRow(0)

    # ── Actions ──

    def _on_topic_selected(self, current: QListWidgetItem, _previous):
        if current is None:
            return
        topic = current.data(Qt.UserRole)
        self._title_label.setText(topic.get("title", i18n.get_text("help_center")))
        self._content_label.setText(topic.get("content", ""))

    def _on_search(self, text: str):
        query = text.strip().lower()
        if not query:
            self._populate_list(self._topics)
            return

        filtered = [
            t for t in self._topics
            if query in t.get("title", "").lower()
            or query in t.get("content", "").lower()
        ]
        self._populate_list(filtered)
