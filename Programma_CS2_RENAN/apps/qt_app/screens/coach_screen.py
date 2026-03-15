"""Coach screen — AI coaching dashboard with collapsible chat panel."""

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from Programma_CS2_RENAN.apps.qt_app.core.app_state import get_app_state
from Programma_CS2_RENAN.apps.qt_app.core.i18n_bridge import i18n
from Programma_CS2_RENAN.apps.qt_app.viewmodels.coach_vm import CoachViewModel
from Programma_CS2_RENAN.apps.qt_app.viewmodels.coaching_chat_vm import (
    CoachingChatViewModel,
)
from Programma_CS2_RENAN.core.config import get_setting
from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.qt_coach")

_SEVERITY_COLORS = {
    "high": "#ff5555",
    "medium": "#ffcc00",
    "low": "#4caf50",
}

_QUICK_ACTIONS = [
    "How can I improve my positioning?",
    "Analyze my utility usage",
    "What should I focus on?",
]


class CoachScreen(QWidget):
    """AI Coach dashboard with insights and collapsible chat."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._coach_vm = CoachViewModel()
        self._chat_vm = CoachingChatViewModel()
        self._state_connected = False
        self._chat_open = False

        # Connect VM signals
        self._coach_vm.insights_loaded.connect(self._on_insights)
        self._chat_vm.messages_changed.connect(self._render_messages)
        self._chat_vm.is_loading_changed.connect(self._on_chat_loading)
        self._chat_vm.is_available_changed.connect(self._on_chat_availability)

        self._build_ui()

    def on_enter(self):
        if not self._state_connected:
            get_app_state().belief_confidence_changed.connect(self._on_belief)
            self._state_connected = True
        self._coach_vm.load_insights()

    def retranslate(self):
        """Update all translatable text when language changes."""
        self._title_label.setText(i18n.get_text("rap_coach_dashboard"))
        self._belief_card_title.setText(i18n.get_text("belief_state"))
        self._belief_desc_label.setText(i18n.get_text("belief_desc"))
        self._insights_card_title.setText(i18n.get_text("recent_insights"))
        self._analytics_card_title.setText(i18n.get_text("advanced_analytics"))
        self._typing_label.setText(i18n.get_text("coach_thinking"))
        self._chat_input.setPlaceholderText(i18n.get_text("ask_your_coach"))

    # ── UI Construction ──

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Main scrollable content area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(16, 16, 16, 16)
        self._content_layout.setSpacing(16)

        # Title row with chat toggle
        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        self._title_label = QLabel(i18n.get_text("rap_coach_dashboard"))
        self._title_label.setObjectName("section_title")
        self._title_label.setFont(QFont("Roboto", 20, QFont.Bold))
        title_row.addWidget(self._title_label)
        title_row.addStretch()

        self._chat_toggle_btn = QPushButton("Chat")
        self._chat_toggle_btn.setCursor(Qt.PointingHandCursor)
        self._chat_toggle_btn.setFixedWidth(100)
        self._chat_toggle_btn.clicked.connect(self._toggle_chat)
        title_row.addWidget(self._chat_toggle_btn)
        self._content_layout.addLayout(title_row)

        # Belief confidence card
        self._build_belief_card()

        # Insights card
        self._build_insights_card()

        # Analytics placeholder
        self._build_analytics_placeholder()

        self._content_layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        # Collapsible chat panel (bottom)
        self._chat_panel = self._build_chat_panel()
        self._chat_panel.setVisible(False)
        root.addWidget(self._chat_panel)

    # ── Belief Confidence ──

    def _build_belief_card(self):
        card, self._belief_card_title = self._make_card("belief_state")
        layout = card.layout()

        self._belief_desc_label = QLabel(i18n.get_text("belief_desc"))
        self._belief_desc_label.setWordWrap(True)
        self._belief_desc_label.setStyleSheet("color: #a0a0b0; font-size: 13px;")
        layout.addWidget(self._belief_desc_label)

        self._belief_bar = QProgressBar()
        self._belief_bar.setRange(0, 100)
        self._belief_bar.setValue(0)
        self._belief_bar.setFixedHeight(20)
        layout.addWidget(self._belief_bar)

        self._belief_label = QLabel("0%")
        self._belief_label.setStyleSheet("color: #dcdcdc; font-size: 13px;")
        layout.addWidget(self._belief_label)

        self._content_layout.addWidget(card)

    # ── Insights Card ──

    def _build_insights_card(self):
        card, self._insights_card_title = self._make_card("recent_insights")
        self._insights_container = card.layout()

        self._insights_placeholder = QLabel(i18n.get_text("loading_insights"))
        self._insights_placeholder.setStyleSheet("color: #a0a0b0; font-size: 13px;")
        self._insights_placeholder.setAlignment(Qt.AlignCenter)
        self._insights_container.addWidget(self._insights_placeholder)

        self._content_layout.addWidget(card)

    # ── Analytics Placeholder ──

    def _build_analytics_placeholder(self):
        card, self._analytics_card_title = self._make_card("advanced_analytics")
        layout = card.layout()
        lbl = QLabel(
            "Trend graphs and radar charts will appear here after demo analysis.\n"
            "Analyze matches to populate this section."
        )
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #666680; font-size: 13px; padding: 24px;")
        layout.addWidget(lbl)
        self._content_layout.addWidget(card)

    # ── Chat Panel ──

    def _build_chat_panel(self) -> QFrame:
        panel = QFrame()
        panel.setStyleSheet(
            "QFrame { background-color: #0f0f1a; border-top: 1px solid #2a2a3a; }"
        )
        panel.setFixedHeight(420)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        # Header
        header = QHBoxLayout()
        header.setSpacing(8)
        chat_title = QLabel("Chat")
        chat_title.setFont(QFont("Roboto", 14, QFont.Bold))
        chat_title.setStyleSheet("color: #dcdcdc; border: none;")
        header.addWidget(chat_title)

        self._chat_status_dot = QLabel("\u25cf")
        self._chat_status_dot.setStyleSheet("color: #666680; font-size: 12px; border: none;")
        header.addWidget(self._chat_status_dot)

        self._chat_status_label = QLabel("Checking...")
        self._chat_status_label.setStyleSheet("color: #a0a0b0; font-size: 12px; border: none;")
        header.addWidget(self._chat_status_label)

        header.addStretch()

        clear_btn = QPushButton("Clear")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setFixedWidth(60)
        clear_btn.setStyleSheet("border: none;")
        clear_btn.clicked.connect(self._clear_chat)
        header.addWidget(clear_btn)

        collapse_btn = QPushButton("\u25bc")
        collapse_btn.setCursor(Qt.PointingHandCursor)
        collapse_btn.setFixedWidth(30)
        collapse_btn.setStyleSheet("border: none;")
        collapse_btn.clicked.connect(self._toggle_chat)
        header.addWidget(collapse_btn)

        layout.addLayout(header)

        # Messages scroll area
        msg_scroll = QScrollArea()
        msg_scroll.setWidgetResizable(True)
        msg_scroll.setFrameShape(QFrame.NoFrame)
        msg_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._msg_container = QWidget()
        self._msg_container.setStyleSheet("background: transparent;")
        self._msg_layout = QVBoxLayout(self._msg_container)
        self._msg_layout.setContentsMargins(0, 0, 0, 0)
        self._msg_layout.setSpacing(8)
        self._msg_layout.addStretch()
        msg_scroll.setWidget(self._msg_container)
        self._msg_scroll = msg_scroll
        layout.addWidget(msg_scroll, 1)

        # Typing indicator
        self._typing_label = QLabel(i18n.get_text("coach_thinking"))
        self._typing_label.setStyleSheet("color: #a0a0b0; font-size: 12px; border: none;")
        self._typing_label.setVisible(False)
        layout.addWidget(self._typing_label)

        # Quick actions
        qa_row = QHBoxLayout()
        qa_row.setSpacing(8)
        for action_text in _QUICK_ACTIONS:
            btn = QPushButton(action_text)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            btn.setStyleSheet(
                "QPushButton { border: 1px solid #3a3a5a; border-radius: 12px; "
                "padding: 4px 10px; color: #a0a0b0; font-size: 12px; background: transparent; }"
                "QPushButton:hover { border-color: #5a5a8a; color: #dcdcdc; }"
            )
            btn.clicked.connect(lambda checked, t=action_text: self._send_quick(t))
            qa_row.addWidget(btn)
        qa_row.addStretch()
        layout.addLayout(qa_row)

        # Input row
        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self._chat_input = QLineEdit()
        self._chat_input.setPlaceholderText(i18n.get_text("ask_your_coach"))
        self._chat_input.setStyleSheet("border: none;")
        self._chat_input.returnPressed.connect(self._send_message)
        input_row.addWidget(self._chat_input, 1)

        send_btn = QPushButton("Send")
        send_btn.setCursor(Qt.PointingHandCursor)
        send_btn.setFixedWidth(70)
        send_btn.clicked.connect(self._send_message)
        input_row.addWidget(send_btn)
        layout.addLayout(input_row)

        return panel

    # ── Helpers ──

    def _make_card(self, i18n_key: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName("dashboard_card")
        layout = QVBoxLayout(card)
        layout.setSpacing(8)
        lbl = QLabel(i18n.get_text(i18n_key))
        lbl.setFont(QFont("Roboto", 14, QFont.Bold))
        lbl.setStyleSheet("color: #dcdcdc;")
        layout.addWidget(lbl)
        return card, lbl

    def _scroll_chat_bottom(self):
        QTimer.singleShot(50, lambda: self._msg_scroll.verticalScrollBar().setValue(
            self._msg_scroll.verticalScrollBar().maximum()
        ))

    # ── Actions ──

    def _toggle_chat(self):
        self._chat_open = not self._chat_open
        self._chat_panel.setVisible(self._chat_open)

        if self._chat_open:
            player = get_setting("CS2_PLAYER_NAME", "")
            if player:
                self._chat_vm.check_and_start(player)
            else:
                self._chat_vm.check_availability()
            self._chat_input.setFocus()

    def _send_message(self):
        text = self._chat_input.text().strip()
        if text:
            self._chat_vm.send_message(text)
            self._chat_input.clear()

    def _send_quick(self, text: str):
        self._chat_vm.send_message(text)

    def _clear_chat(self):
        self._chat_vm.clear_session()
        self._chat_status_label.setText("")

    # ── Signal Slots ──

    def _on_belief(self, confidence: float):
        pct = int(confidence)
        self._belief_bar.setValue(pct)
        self._belief_label.setText(f"{pct}%")

    def _on_insights(self, insights: list):
        # Remove placeholder
        if self._insights_placeholder is not None:
            self._insights_placeholder.setVisible(False)

        # Remove old insight widgets (keep title label at index 0 and placeholder at 1)
        while self._insights_container.count() > 2:
            item = self._insights_container.takeAt(2)
            w = item.widget()
            if w:
                w.deleteLater()

        if not insights:
            self._insights_placeholder.setText("No insights yet. Analyze demos to generate coaching advice.")
            self._insights_placeholder.setVisible(True)
            return

        for insight in insights:
            item_frame = QFrame()
            item_frame.setStyleSheet(
                "QFrame { background: #181c28; border-radius: 6px; padding: 8px; }"
            )
            item_layout = QVBoxLayout(item_frame)
            item_layout.setContentsMargins(8, 6, 8, 6)
            item_layout.setSpacing(4)

            # Title + severity
            title_row = QHBoxLayout()
            title_lbl = QLabel(insight.get("title", "Insight"))
            title_lbl.setFont(QFont("Roboto", 12, QFont.Bold))
            title_lbl.setStyleSheet("color: #dcdcdc; background: transparent;")
            title_row.addWidget(title_lbl)

            severity = insight.get("severity", "low").lower()
            sev_color = _SEVERITY_COLORS.get(severity, "#808080")
            sev_lbl = QLabel(severity.capitalize())
            sev_lbl.setStyleSheet(
                f"color: {sev_color}; font-size: 11px; font-weight: bold; background: transparent;"
            )
            title_row.addWidget(sev_lbl)
            title_row.addStretch()
            item_layout.addLayout(title_row)

            # Message
            msg_lbl = QLabel(insight.get("message", ""))
            msg_lbl.setWordWrap(True)
            msg_lbl.setStyleSheet("color: #a0a0b0; font-size: 12px; background: transparent;")
            item_layout.addWidget(msg_lbl)

            # Focus area + date
            meta_row = QHBoxLayout()
            focus = insight.get("focus_area", "")
            if focus:
                focus_lbl = QLabel(focus)
                focus_lbl.setStyleSheet(
                    "color: #5a5a8a; font-size: 11px; background: transparent;"
                )
                meta_row.addWidget(focus_lbl)
            meta_row.addStretch()
            date_lbl = QLabel(insight.get("created_at", ""))
            date_lbl.setStyleSheet("color: #5a5a8a; font-size: 11px; background: transparent;")
            meta_row.addWidget(date_lbl)
            item_layout.addLayout(meta_row)

            self._insights_container.addWidget(item_frame)

    def _render_messages(self, messages: list):
        # Clear existing bubbles (keep the stretch at index 0)
        while self._msg_layout.count() > 1:
            item = self._msg_layout.takeAt(1)
            w = item.widget()
            if w:
                w.deleteLater()

        for msg in messages:
            role = msg.get("role", "assistant")
            is_user = role == "user"
            is_system = role == "system"

            if is_system:
                bg_color = "#2a1a1a"
                text_color = "#ff8888"
            elif is_user:
                bg_color = "#1a3366"
                text_color = "#dcdcdc"
            else:
                bg_color = "#181c28"
                text_color = "#dcdcdc"

            bubble = QFrame()
            bubble.setStyleSheet(
                "QFrame { background: %s; border-radius: 10px; padding: 8px; }"
                % bg_color
            )
            bubble.setMaximumWidth(500)
            b_layout = QVBoxLayout(bubble)
            b_layout.setContentsMargins(10, 6, 10, 6)
            lbl = QLabel(msg.get("content", ""))
            lbl.setWordWrap(True)
            lbl.setStyleSheet(
                f"color: {text_color}; font-size: 13px; background: transparent;"
            )
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            b_layout.addWidget(lbl)

            # Alignment wrapper
            wrapper = QHBoxLayout()
            wrapper.setContentsMargins(0, 0, 0, 0)
            if is_user:
                wrapper.addStretch()
                wrapper.addWidget(bubble)
            elif is_system:
                wrapper.addWidget(bubble, 1)  # full width for system messages
            else:
                wrapper.addWidget(bubble)
                wrapper.addStretch()

            container = QWidget()
            container.setStyleSheet("background: transparent;")
            container.setLayout(wrapper)
            self._msg_layout.addWidget(container)

        self._scroll_chat_bottom()

    def _on_chat_loading(self, loading: bool):
        self._typing_label.setVisible(loading)
        if loading:
            self._scroll_chat_bottom()

    def _on_chat_availability(self, available: bool):
        if available:
            self._chat_status_dot.setStyleSheet("color: #4caf50; font-size: 12px; border: none;")
            self._chat_status_label.setText("Online")
        else:
            self._chat_status_dot.setStyleSheet("color: #ff5555; font-size: 12px; border: none;")
            self._chat_status_label.setText("Offline")
