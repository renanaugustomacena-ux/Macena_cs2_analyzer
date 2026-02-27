import logging

from kivy.metrics import dp
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.list import (
    MDList,
    MDListItem,
    MDListItemHeadlineText,
    MDListItemLeadingIcon,
    MDListItemSupportingText,
    MDListItemTrailingSupportingText,
)
from kivymd.uix.progressindicator.progressindicator import MDLinearProgressIndicator

_logger = logging.getLogger("cs2analyzer.player_sidebar")


class LivePlayerCard(MDCard):
    """
    Real-time Player Statistics Card.
    Refined Layout with Icons.
    """

    player_name = StringProperty("")
    hp = NumericProperty(100)
    armor = NumericProperty(0)
    money = NumericProperty(0)
    weapon = StringProperty("")
    kda = StringProperty("0 / 0 / 0")
    team_color = ListProperty([1, 1, 1, 1])
    is_alive = BooleanProperty(True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.padding = "12dp"
        self.spacing = "4dp"
        self.size_hint_y = None
        self.height = 0  # Hidden by default
        self.opacity = 0
        self.md_bg_color = (0.15, 0.15, 0.15, 1)
        self.radius = [
            12,
        ]
        self.elevation = 4

        # Name Label
        self.name_lbl = MDLabel(
            text=self.player_name,
            font_style="Headline",
            role="small",
            halign="center",
            adaptive_height=True,
            bold=True,
        )
        self.add_widget(self.name_lbl)

        # --- Vitals Row (HP + Armor) ---
        self.add_widget(self._build_icon_row("heart", "Health", "hp_bar", (0, 1, 0, 1)))
        self.add_widget(self._build_icon_row("shield", "Armor", "armor_bar", (0, 0.5, 1, 1)))

        # --- Economy & Weapon ---
        self.add_widget(self._build_info_row("cash", "money_lbl", "$0", (0.5, 1, 0.5, 1)))

        # --- KDA Badge style ---
        kda_box = MDBoxLayout(
            orientation="horizontal", spacing="10dp", adaptive_height=True, padding=[0, "5dp", 0, 0]
        )
        # kda_box.add_widget(MDIcon(icon="crosshairs-gps", theme_text_color="Hint", pos_hint={"center_y": .5}))
        self.kda_lbl = MDLabel(
            text="0 / 0 / 0",
            font_style="Title",
            role="medium",
            halign="center",
            theme_text_color="Primary",
        )
        kda_box.add_widget(self.kda_lbl)
        self.add_widget(kda_box)

    def _build_icon_row(self, icon, label, bar_attr, color):
        """Helper to build Icon + Label + Bar row."""
        box = MDBoxLayout(orientation="vertical", spacing="2dp", adaptive_height=True)

        header = MDBoxLayout(orientation="horizontal", spacing="8dp", adaptive_height=True)
        header.add_widget(
            MDIcon(
                icon=icon,
                theme_text_color="Custom",
                text_color=color,
                font_size="16sp",
                size_hint=(None, None),
                size=("18dp", "18dp"),
            )
        )
        # header.add_widget(MDLabel(text=label, font_style="Label", role="small", theme_text_color="Hint"))
        box.add_widget(header)

        bar = MDLinearProgressIndicator(
            value=100,
            color=color,
            size_hint_y=None,
            height="6dp",
            radius=[
                2,
            ],
        )
        setattr(self, bar_attr, bar)
        box.add_widget(bar)
        return box

    def _build_info_row(self, icon, lbl_attr, default_text, color):
        box = MDBoxLayout(orientation="horizontal", spacing="10dp", adaptive_height=True)
        box.add_widget(
            MDIcon(
                icon=icon, theme_text_color="Custom", text_color=color, pos_hint={"center_y": 0.5}
            )
        )
        lbl = MDLabel(
            text=default_text,
            font_style="Body",
            role="medium",
            theme_text_color="Custom",
            text_color=(1, 1, 1, 1),
        )
        setattr(self, lbl_attr, lbl)
        box.add_widget(lbl)
        return box

    def on_player_name(self, instance, value):
        self.name_lbl.text = value

    def on_team_color(self, instance, value):
        self.name_lbl.text_color = value
        self.name_lbl.theme_text_color = "Custom"

    def update(self, p):
        # [OPTIMIZATION] Reduced height to be less intrusive
        self.height = "210dp"
        self.opacity = 1

        self.player_name = p.name
        self.hp = p.hp
        self.armor = p.armor
        self.money = p.money
        self.weapon = p.weapon
        self.kda = f"{p.kills} / {p.deaths} / {p.assists}"
        self.is_alive = p.is_alive

        self.hp_bar.value = p.hp
        self.hp_bar.color = (0, 1, 0, 1) if p.hp > 50 else (1, 0, 0, 1)
        self.armor_bar.value = p.armor

        self.money_lbl.text = f"${p.money}"
        self.kda_lbl.text = self.kda
        # self.weapon_lbl.text = p.weapon

        if not p.is_alive:
            self.opacity = 0.6
            self.md_bg_color = (0.1, 0.1, 0.1, 1)
            self.name_lbl.text = f"[DEAD] {p.name}"
        else:
            self.opacity = 1
            self.md_bg_color = (0.15, 0.15, 0.15, 1)
            self.name_lbl.text = p.name

    def hide(self):
        self.height = 0
        self.opacity = 0
        self.md_bg_color = (0.15, 0.15, 0.15, 1)


class PlayerSidebar(BoxLayout):
    """Sidebar to display player list and details."""

    team_name = StringProperty("TEAM")
    team_color = ListProperty([1, 1, 1, 1])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.padding = 0
        self.spacing = 0

        # [OPTIMIZATION] Widget Cache for Object Pooling
        self._player_items = {}

        # Header
        self.header = MDLabel(
            text=self.team_name,
            theme_text_color="Custom",
            text_color=self.team_color,
            adaptive_height=True,
            padding=["16dp", "10dp"],
            bold=True,
            font_style="Title",
            role="medium",
        )
        self.add_widget(self.header)

        # Scroll area for players (Using MDList)
        self.scroll = ScrollView()
        self.player_list = MDList()
        self.player_list.padding = "8dp"
        self.player_list.spacing = "4dp"
        self.scroll.add_widget(self.player_list)
        self.add_widget(self.scroll)

        # Live Player Card
        self.card = LivePlayerCard()
        self.add_widget(self.card)

    def on_team_name(self, instance, value):
        if hasattr(self, "header"):
            self.header.text = value

    def on_team_color(self, instance, value):
        if hasattr(self, "header"):
            self.header.text_color = value

    def update_players(self, players, selected_id=None):
        """
        Updates the player list using Widget Pooling.
        Instead of enabling/disabling 10 widgets every frame, we just update data.
        """

        # 1. Identify active players for this frame
        active_ids = {p.player_id for p in players}

        # 2. Evict widgets for players no longer active (e.g. disconnected)
        stale_pids = [pid for pid in self._player_items if pid not in active_ids]
        for pid in stale_pids:
            widget, _ = self._player_items.pop(pid)
            self.player_list.remove_widget(widget)

        sorted_players = sorted(players, key=lambda x: (not x.is_alive, x.player_id))
        target_player = None

        for p in sorted_players:
            is_selected = p.player_id == selected_id
            if is_selected:
                target_player = p

            # Determine colors/icons
            icon_name = "account"
            icon_color = (0.8, 0.8, 0.8, 1)

            if not p.is_alive:
                icon_name = "skull"
                icon_color = (0.5, 0.5, 0.5, 1)
            elif "CT" in str(p.team).upper():
                icon_name = "shield-check"
                icon_color = (0.3, 0.5, 1, 1)
            else:
                icon_name = "target"
                icon_color = (1, 0.6, 0.2, 1)

            # --- POOLING LOGIC ---
            if p.player_id in self._player_items:
                # REUSE existing widget
                item, parts = self._player_items[p.player_id]

                # Check if visible, if not re-add
                if item.parent is None:
                    self.player_list.add_widget(item)

                # Update properties directly
                item.md_bg_color = (0.25, 0.3, 0.4, 1) if is_selected else (0.1, 0.1, 0.1, 0)

                # Update Icon
                parts["icon"].icon = icon_name
                parts["icon"].text_color = icon_color

                # Update Name
                parts["headline"].text = p.name
                parts["headline"].text_color = (
                    (0.5, 0.5, 0.5, 1) if not p.is_alive else (1, 1, 1, 1)
                )

                # Update Money/HP
                info_text = f"${p.money}"
                if p.is_alive:
                    info_text += f" | HP: {p.hp}"
                parts["support"].text = info_text

                # Update Weapon (Trailing)
                parts["trailing"].text = p.weapon

            else:
                # CREATE new widget
                item = MDListItem(
                    radius=[
                        8,
                    ],
                    md_bg_color=(0.25, 0.3, 0.4, 1) if is_selected else (0.1, 0.1, 0.1, 0),
                    on_release=lambda x, pid=p.player_id: self._on_player_clicked(pid),
                )

                # Leading Icon
                icon_widget = MDListItemLeadingIcon(
                    icon=icon_name, theme_text_color="Custom", text_color=icon_color
                )
                item.add_widget(icon_widget)

                # Name
                headline = MDListItemHeadlineText(
                    text=p.name, theme_text_color="Custom", text_color=(1, 1, 1, 1)
                )
                item.add_widget(headline)

                # Stats
                support = MDListItemSupportingText(text=f"${p.money}", theme_text_color="Hint")
                item.add_widget(support)

                # Weapon (Trailing)
                trailing = MDListItemTrailingSupportingText(text=p.weapon, theme_text_color="Hint")
                item.add_widget(trailing)

                self.player_list.add_widget(item)

                # Cache references to parts to avoid .children calls
                self._player_items[p.player_id] = (
                    item,
                    {
                        "icon": icon_widget,
                        "headline": headline,
                        "support": support,
                        "trailing": trailing,
                    },
                )

        # Update Card
        if target_player:
            self.card.team_color = self.team_color
            self.card.update(target_player)
        else:
            self.card.hide()

    def clear_all(self):
        """Clear all player items from the sidebar. Call on match switch."""
        # F7-14: Explicit clear prevents cache growth across matches
        for key in list(self._player_items.keys()):
            widget, parts = self._player_items.pop(key)
            self.player_list.remove_widget(widget)
        self.card.hide()

    def _on_player_clicked(self, pid):
        app = MDApp.get_running_app()
        # Find the tactical_viewer screen
        if app.root and hasattr(app.root, "get_screen"):
            try:
                screen = app.root.get_screen("tactical_viewer")
                if hasattr(screen, "select_player"):
                    screen.select_player(pid)
            except Exception as e:
                _logger.warning("Player navigation failed for pid=%s: %s", pid, e)
