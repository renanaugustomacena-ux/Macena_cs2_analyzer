import matplotlib
from kivy.clock import Clock
from kivy.graphics.texture import Texture
from kivy.uix.image import Image

matplotlib.use("Agg")  # Headless backend for Kivy compatibility
import io

import matplotlib.pyplot as plt
import numpy as np


class MatplotlibWidget(Image):
    """
    Base widget to render Matplotlib figures to Kivy Textures.
    Efficiently handles buffer-to-texture conversion.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.figure = None
        self.allow_stretch = True
        self.keep_ratio = False

    def update_plot(self, fig):
        """Renders the figure and updates the texture."""
        self.figure = fig

        # Render to buffer
        buf = io.BytesIO()
        fig.savefig(buf, format="png", facecolor="#1a1a1a", edgecolor="none")
        buf.seek(0)

        # Load into CoreImage for texture creation
        from kivy.core.image import Image as CoreImage

        img_data = CoreImage(buf, ext="png")
        buf.close()

        # Update widget texture safely on main thread
        Clock.schedule_once(lambda dt: self._set_texture(img_data.texture), 0)

        # Close figure to free memory
        plt.close(fig)

    def _set_texture(self, texture):
        self.texture = texture


class TrendGraphWidget(MatplotlibWidget):
    """Line chart for historical trends."""

    def plot(self, df):
        if df.empty:
            self.texture = None
            return

        fig, ax1 = plt.subplots(figsize=(6, 3))
        fig.patch.set_facecolor("#1a1a1a")
        ax1.set_facecolor("#1a1a1a")

        # Plot Rating (Left Axis)
        idx = range(len(df))
        ax1.plot(idx, df["rating"], color="#00ccff", marker="o", label="Rating")
        ax1.set_ylabel("Rating", color="#00ccff")
        ax1.tick_params(axis="y", labelcolor="#00ccff", colors="white")
        ax1.tick_params(axis="x", colors="white")

        # Plot ADR (Right Axis)
        ax2 = ax1.twinx()
        ax2.plot(idx, df["avg_adr"], color="#ffaa00", linestyle="--", label="ADR")
        ax2.set_ylabel("ADR", color="#ffaa00")
        ax2.tick_params(axis="y", labelcolor="#ffaa00", colors="white")

        ax1.set_title("Performance Trend (Last 20 Matches)", color="white")
        ax1.grid(True, alpha=0.2)

        plt.tight_layout()
        self.update_plot(fig)


class RadarChartWidget(MatplotlibWidget):
    """Spider chart for skill attributes."""

    def plot(self, skill_dict):
        if not skill_dict:
            self.texture = None
            return

        metrics = list(skill_dict.keys())
        values = list(skill_dict.values())

        if len(metrics) < 3:  # F7-36: radar chart needs at least 3 points for a meaningful polygon
            import logging
            logging.getLogger("cs2analyzer.widgets").warning(
                "RadarChartWidget: need at least 3 attributes, got %s", len(metrics)
            )
            self.texture = None
            return

        # Close the loop
        metrics += [metrics[0]]
        values += [values[0]]

        angles = np.linspace(0, 2 * np.pi, len(metrics), endpoint=True)

        fig = plt.figure(figsize=(4, 4))
        fig.patch.set_facecolor("#1a1a1a")

        ax = fig.add_subplot(111, polar=True)
        ax.set_facecolor("#1a1a1a")

        # Style
        ax.plot(angles, values, color="#aa00ff", linewidth=2)
        ax.fill(angles, values, color="#aa00ff", alpha=0.25)

        # Labels
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(metrics[:-1], color="white", size=10)

        # Y-Grid
        ax.set_rlabel_position(0)
        plt.yticks([25, 50, 75, 100], ["25", "50", "75", ""], color="grey", size=8)
        plt.ylim(0, 100)

        # Grid color
        ax.grid(color="grey", alpha=0.3)
        ax.spines["polar"].set_visible(False)

        self.update_plot(fig)


class EconomyGraphWidget(MatplotlibWidget):
    """Bar chart of equipment value per round, color-coded by side (CT/T)."""

    def plot(self, rounds: list):
        if not rounds:
            self.texture = None
            return

        fig, ax = plt.subplots(figsize=(6, 2.5))
        fig.patch.set_facecolor("#1a1a1a")
        ax.set_facecolor("#1a1a1a")

        round_nums = [r.get("round_number", i + 1) for i, r in enumerate(rounds)]
        equip_vals = [r.get("equipment_value", 0) for r in rounds]
        colors = ["#5C9EE8" if r.get("side") == "CT" else "#E8C95C" for r in rounds]

        ax.bar(round_nums, equip_vals, color=colors, width=0.8, alpha=0.85)
        ax.set_xlabel("Round", color="white", fontsize=9)
        ax.set_ylabel("Equipment ($)", color="white", fontsize=9)
        ax.set_title("Economy per Round", color="white", fontsize=10)
        ax.tick_params(colors="white", labelsize=8)
        ax.grid(True, alpha=0.15)

        plt.tight_layout()
        self.update_plot(fig)


class MomentumGraphWidget(MatplotlibWidget):
    """Cumulative kill-death delta as momentum line with green/red fill."""

    def plot(self, rounds: list):
        if not rounds:
            self.texture = None
            return

        fig, ax = plt.subplots(figsize=(6, 2.5))
        fig.patch.set_facecolor("#1a1a1a")
        ax.set_facecolor("#1a1a1a")

        round_nums = []
        momentum = []
        cumulative = 0
        for i, r in enumerate(rounds):
            round_nums.append(r.get("round_number", i + 1))
            cumulative += r.get("kills", 0) - r.get("deaths", 0)
            momentum.append(cumulative)

        ax.plot(round_nums, momentum, color="#00ccff", linewidth=2, marker="o", markersize=3)
        ax.fill_between(
            round_nums, momentum, 0, where=[m >= 0 for m in momentum], color="#4CAF50", alpha=0.2
        )
        ax.fill_between(
            round_nums, momentum, 0, where=[m < 0 for m in momentum], color="#F44336", alpha=0.2
        )
        ax.axhline(y=0, color="white", linewidth=0.5, alpha=0.5)

        ax.set_xlabel("Round", color="white", fontsize=9)
        ax.set_ylabel("Cumulative K-D", color="white", fontsize=9)
        ax.set_title("Momentum (Kill-Death Delta)", color="white", fontsize=10)
        ax.tick_params(colors="white", labelsize=8)
        ax.grid(True, alpha=0.15)

        plt.tight_layout()
        self.update_plot(fig)


class RatingSparklineWidget(MatplotlibWidget):
    """Sparkline showing rating progression with reference lines."""

    def plot(self, history: list):
        if not history:
            self.texture = None
            return

        fig, ax = plt.subplots(figsize=(6, 2.5))
        fig.patch.set_facecolor("#1a1a1a")
        ax.set_facecolor("#1a1a1a")

        ratings = [h.get("rating", 1.0) if h.get("rating") is not None else 1.0 for h in history]
        idx = range(len(ratings))

        ax.plot(idx, ratings, color="#00ccff", linewidth=2, marker="o", markersize=4)
        ax.fill_between(idx, ratings, min(ratings) - 0.05, color="#00ccff", alpha=0.15)

        ax.axhline(y=1.0, color="white", linewidth=0.5, linestyle="--", alpha=0.4)
        ax.axhline(y=1.1, color="#4CAF50", linewidth=0.5, linestyle="--", alpha=0.3)
        ax.axhline(y=0.9, color="#F44336", linewidth=0.5, linestyle="--", alpha=0.3)

        ax.set_ylabel("Rating", color="white", fontsize=9)
        ax.set_title("Rating Trend", color="white", fontsize=10)
        ax.tick_params(colors="white", labelsize=8)
        ax.grid(True, alpha=0.15)

        plt.tight_layout()
        self.update_plot(fig)


class UtilityBarWidget(MatplotlibWidget):
    """Horizontal grouped bar chart comparing user vs pro utility stats."""

    def plot(self, utility: dict):
        user_data = utility.get("user", {})
        pro_data = utility.get("pro", {})
        if not user_data:
            self.texture = None
            return

        fig, ax = plt.subplots(figsize=(6, 3.5))
        fig.patch.set_facecolor("#1a1a1a")
        ax.set_facecolor("#1a1a1a")

        metrics = list(user_data.keys())
        user_vals = [user_data.get(m, 0) for m in metrics]
        pro_vals = [pro_data.get(m, 0) for m in metrics]

        y = np.arange(len(metrics))
        bar_height = 0.35

        ax.barh(y - bar_height / 2, user_vals, bar_height, label="You", color="#00ccff", alpha=0.85)
        ax.barh(
            y + bar_height / 2, pro_vals, bar_height, label="Pro Avg", color="#ffaa00", alpha=0.65
        )

        ax.set_yticks(y)
        ax.set_yticklabels(
            [m.replace("_", " ").title() for m in metrics], color="white", fontsize=9
        )
        ax.set_xlabel("Value", color="white", fontsize=9)
        ax.set_title("Utility: You vs Pro", color="white", fontsize=10)
        ax.tick_params(colors="white", labelsize=8)
        ax.legend(
            loc="lower right", fontsize=8, facecolor="#2a2a2a", edgecolor="#444", labelcolor="white"
        )
        ax.grid(True, axis="x", alpha=0.15)

        plt.tight_layout()
        self.update_plot(fig)
