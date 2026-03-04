import io
import json
from pathlib import Path

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import gaussian_filter

from Programma_CS2_RENAN.observability.logger_setup import get_logger

_logger = get_logger("cs2analyzer.visualizer")


class MatchVisualizer:
    """
    Generates visual artifacts for CS2 Match Reports.
    Handles Map Heatmaps, Death Locations, and Trajectory plots.
    """

    def __init__(self, output_dir="reports/assets"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Load map config
        _module_dir = Path(__file__).parent
        try:
            config_path = _module_dir / ".." / "data" / "map_tensors.json"
            with open(config_path, "r", encoding="utf-8") as f:
                self.map_config = json.load(f)
        except Exception as e:
            _logger.warning("Could not load map_tensors.json: %s", e)
            self.map_config = {}

        self.assets_dir = _module_dir / ".." / "assets" / "maps"

        # Fallback bounds
        self.map_bounds = {"unknown": (-4000, 4000, -4000, 4000)}

    def generate_heatmap(self, positions, map_name, title="Player Heatmap"):
        """
        Generates a 2D Histogram heatmap of player positions.
        """
        x_vals = [p[0] for p in positions]
        y_vals = [p[1] for p in positions]

        plt.figure(figsize=(10, 10))

        # Plot styling
        plt.title(f"{title} - {map_name}")

        # Create heatmap
        self._setup_map_plot(map_name)

        # Plot using hist2d instead of seaborn
        plt.hist2d(x_vals, y_vals, bins=64, cmap="magma", cmin=1)
        plt.colorbar()

        # Save
        filename = f"{map_name}_{title.lower().replace(' ', '_')}.png"
        path = self.output_dir / filename
        plt.savefig(str(path))
        plt.close()
        return str(path)

    def plot_round_errors(self, round_id, deaths, bad_decisions, map_name):
        """
        Plots specific points where the user died or made bad decisions.
        """
        plt.figure(figsize=(10, 10))
        self._setup_map_plot(map_name)

        # Plot deaths
        dx = [d["x"] for d in deaths]
        dy = [d["y"] for d in deaths]
        plt.scatter(dx, dy, c="red", marker="x", s=100, label="Deaths")

        # Plot Bad Decisions
        bx = [b["x"] for b in bad_decisions]
        by = [b["y"] for b in bad_decisions]
        plt.scatter(bx, by, c="orange", marker="P", s=100, label="Coach Flag")

        plt.legend()
        plt.title(f"Key Events - Round {round_id}")

        filename = f"round_{round_id}_analysis.png"
        path = self.output_dir / filename
        plt.savefig(str(path))
        plt.close()
        return str(path)

    def _setup_map_plot(self, map_name):
        """Helper to set up map bounds and background image."""
        bounds = self._get_bounds(map_name)

        # Try to load background image from config
        map_entry = self.map_config.get(map_name)
        if map_entry and "image_file" in map_entry:
            img_path = self.assets_dir / map_entry["image_file"]
            if img_path.exists():
                try:
                    img = plt.imread(str(img_path))
                    plt.imshow(img, extent=bounds, zorder=0, aspect="equal")
                except Exception as e:
                    _logger.warning("Failed to load map image %s: %s", img_path, e)

        plt.xlim(bounds[0], bounds[1])
        plt.ylim(bounds[2], bounds[3])

    def render_differential_overlay(
        self,
        user_positions,
        pro_positions,
        map_name,
        resolution=128,
        sigma=5.0,
        title="Pro vs User",
    ):
        """
        Generates a diverging heatmap comparing user vs pro positional patterns.

        Blue = user-heavy areas, Red = pro-heavy areas, White = equal density.
        Overlaid on the map background image if available.

        Args:
            user_positions: List of (x, y) world-coordinate tuples for the user.
            pro_positions: List of (x, y) world-coordinate tuples for pro players.
            map_name: CS2 map identifier (e.g. "de_mirage").
            resolution: Grid resolution for KDE.
            sigma: Gaussian blur sigma.
            title: Plot title.

        Returns:
            Path to the saved PNG file, or None if insufficient data.
        """
        if not user_positions or not pro_positions:
            return None

        fig, ax = plt.subplots(figsize=(10, 10))
        self._setup_map_plot(map_name)

        # Get map bounds for grid alignment
        bounds = self._get_bounds(map_name)
        x_min, x_max, y_min, y_max = bounds

        def positions_to_density(positions):
            grid = np.zeros((resolution, resolution), dtype=np.float32)
            for wx, wy in positions:
                gx = int((wx - x_min) / (x_max - x_min) * (resolution - 1))
                gy = int((wy - y_min) / (y_max - y_min) * (resolution - 1))
                if 0 <= gx < resolution and 0 <= gy < resolution:
                    grid[gy, gx] += 1.0
            density = gaussian_filter(grid, sigma=sigma)
            max_val = np.max(density)
            if max_val > 0:
                density /= max_val
            return density

        d_user = positions_to_density(user_positions)
        d_pro = positions_to_density(pro_positions)

        # Difference: positive = pro-heavy, negative = user-heavy
        diff = d_pro - d_user

        # Mask areas with no activity
        activity = (d_user > 0.02) | (d_pro > 0.02)
        masked_diff = np.ma.masked_where(~activity, diff)

        # Diverging colormap: blue (user) ← white → red (pro)
        cmap = plt.cm.RdBu_r
        norm = mcolors.TwoSlopeNorm(vmin=-1.0, vcenter=0.0, vmax=1.0)

        im = ax.imshow(
            masked_diff,
            extent=bounds,
            origin="lower",
            cmap=cmap,
            norm=norm,
            alpha=0.7,
            zorder=5,
            aspect="equal",
        )

        cbar = plt.colorbar(im, ax=ax, shrink=0.7, pad=0.02)
        cbar.set_label("Pro-heavy ← → User-heavy", fontsize=10)

        ax.set_title(f"{title} — {map_name}", fontsize=14)

        filename = f"{map_name}_differential_{title.lower().replace(' ', '_')}.png"
        path = self.output_dir / filename
        plt.savefig(str(path), dpi=150, bbox_inches="tight")
        plt.close(fig)
        return str(path)

    def _get_bounds(self, map_name):
        """Returns (x_min, x_max, y_min, y_max) for a map."""
        bounds_map = {
            "de_mirage": (-3230, 1910, -3200, 1700),
            "de_inferno": (-2000, 3800, -1200, 3800),
            "de_dust2": (-2476, 2000, -1200, 3300),
            "de_nuke": (-3000, 4000, -4000, 4000),
            "de_overpass": (-4800, 2000, -1000, 1700),
            "de_ancient": (-3000, 2000, -2000, 3000),
        }
        return bounds_map.get(map_name, (-4000, 4000, -4000, 4000))

    def render_critical_moments(self, moments, map_name, title="Critical Moments"):
        """
        Render critical moments as labeled markers on a map image.

        Args:
            moments: List of highlight annotation dicts from CriticalMoment.to_highlight_annotation().
                Each dict has: tick, description, severity, type, position (optional).
            map_name: CS2 map identifier (e.g. "de_mirage").
            title: Plot title.

        Returns:
            Path to the saved annotated image, or None if no moments.
        """
        if not moments:
            return None

        severity_colors = {
            "critical": "red",
            "significant": "orange",
            "notable": "gold",
        }
        type_markers = {
            "mistake": "v",  # downward triangle for mistakes
            "play": "^",  # upward triangle for plays
        }
        scale_marker_sizes = {
            "micro": 100,
            "standard": 200,
            "macro": 350,
        }

        fig, ax = plt.subplots(figsize=(12, 10))
        self._setup_map_plot(map_name)

        bounds = self._get_bounds(map_name)
        x_min, x_max, y_min, y_max = bounds
        x_range = x_max - x_min
        y_range = y_max - y_min

        for i, moment in enumerate(moments):
            severity = moment.get("severity", "notable")
            color = severity_colors.get(severity, "gold")
            marker = type_markers.get(moment.get("type", "play"), "o")

            # Use position if available, otherwise distribute markers evenly across map
            pos = moment.get("position")
            if pos and len(pos) == 2:
                mx, my = pos
            else:
                # Place markers along a horizontal line at 80% map height
                spacing = x_range / max(1, len(moments) + 1)
                mx = x_min + spacing * (i + 1)
                my = y_min + y_range * 0.8

            scale = moment.get("scale", "standard")
            marker_size = scale_marker_sizes.get(scale, 200)

            ax.scatter(
                mx,
                my,
                c=color,
                marker=marker,
                s=marker_size,
                zorder=10,
                edgecolors="black",
                linewidth=1.5,
            )

            # Label with description
            desc = moment.get("description", "")
            tick = moment.get("tick", 0)
            label = f"T{tick}: {desc}" if tick else desc
            # Truncate long labels
            if len(label) > 50:
                label = label[:47] + "..."

            ax.annotate(
                label,
                (mx, my),
                textcoords="offset points",
                xytext=(0, 15),
                ha="center",
                fontsize=7,
                bbox=dict(boxstyle="round,pad=0.3", facecolor=color, alpha=0.3),
                zorder=11,
            )

        # Legend (severity + scale)
        from matplotlib.lines import Line2D

        legend_elements = [
            Line2D(
                [0],
                [0],
                marker="^",
                color="w",
                markerfacecolor="red",
                markersize=10,
                label="Critical Play",
            ),
            Line2D(
                [0],
                [0],
                marker="v",
                color="w",
                markerfacecolor="red",
                markersize=10,
                label="Critical Mistake",
            ),
            Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor="orange",
                markersize=10,
                label="Significant",
            ),
            Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor="gold",
                markersize=10,
                label="Notable",
            ),
            Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor="gray",
                markersize=6,
                label="Micro scale",
            ),
            Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor="gray",
                markersize=9,
                label="Standard scale",
            ),
            Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor="gray",
                markersize=12,
                label="Macro scale",
            ),
        ]
        ax.legend(handles=legend_elements, loc="lower right", fontsize=8)

        ax.set_title(f"{title} — {map_name}", fontsize=14)

        filename = f"{map_name}_critical_moments.png"
        path = self.output_dir / filename
        plt.savefig(str(path), dpi=150, bbox_inches="tight")
        plt.close(fig)
        return str(path)


def generate_highlight_report(match_id, map_name="de_mirage"):
    """
    Integration function: scan a match for critical moments and render them.

    Args:
        match_id: Match identifier for the ChronovisorScanner.
        map_name: Map name for visual rendering.

    Returns:
        Path to the generated highlight report image, or None.
    """
    try:
        from Programma_CS2_RENAN.backend.nn.rap_coach.chronovisor_scanner import ChronovisorScanner

        scanner = ChronovisorScanner()
        critical_moments = scanner.scan_match(match_id)

        if not critical_moments:
            return None

        annotations = [cm.to_highlight_annotation() for cm in critical_moments]

        viz = MatchVisualizer()
        return viz.render_critical_moments(annotations, map_name)

    except Exception as e:
        _logger.error("Highlight report generation failed: %s", e)
        return None
