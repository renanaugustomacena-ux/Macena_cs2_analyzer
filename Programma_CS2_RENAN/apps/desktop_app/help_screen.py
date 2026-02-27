import logging

from kivy.properties import StringProperty
from kivymd.uix.label import MDLabel
from kivymd.uix.list import MDListItem, MDListItemHeadlineText
from kivymd.uix.screen import MDScreen

try:
    from Programma_CS2_RENAN.backend.knowledge_base.help_system import help_system
    _HELP_SYSTEM_AVAILABLE = True
except ImportError:
    # F7-09: help_system module not yet implemented. HelpScreen will display
    # a placeholder until the module is created.
    help_system = None
    _HELP_SYSTEM_AVAILABLE = False

_logger = logging.getLogger("cs2analyzer.help_screen")


class HelpScreen(MDScreen):
    current_topic_title = StringProperty("Help Center")

    def on_enter(self):
        self.load_topics()

    def load_topics(self):
        """Populates the sidebar list."""
        if not _HELP_SYSTEM_AVAILABLE:
            self._populate_list([])
            return
        try:
            topics = help_system.get_all_topics()
        except Exception as e:
            _logger.error("Failed to load help topics: %s", e)
            topics = []
        self._populate_list(topics)

        # Load first topic by default if content is empty
        if not self.ids.content_label.text and topics:
            self.load_content(topics[0]["id"])

    def _populate_list(self, topics):
        container = self.ids.topic_list
        container.clear_widgets()
        for t in topics:
            item = MDListItem(
                MDListItemHeadlineText(text=t["title"]),
                on_release=lambda x, tid=t["id"]: self.load_content(tid),
            )
            container.add_widget(item)

    def load_content(self, topic_id):
        """Displays the MD content."""
        if not _HELP_SYSTEM_AVAILABLE:
            return
        try:
            data = help_system.get_topic(topic_id)
        except Exception as e:
            _logger.error("Failed to load topic %s: %s", topic_id, e)
            return
        if data:
            self.current_topic_title = data["title"]
            self.ids.content_label.text = data["content"]

    def filter_topics(self, query):
        """Search functionality."""
        if not query:
            self.load_topics()
            return
        if not _HELP_SYSTEM_AVAILABLE:
            self._populate_list([])
            return
        try:
            results = help_system.search_topics(query)
        except Exception as e:
            _logger.error("Help search failed for query '%s': %s", query, e)
            results = []
        self._populate_list(results)
