import io
from typing import Any, Dict

import matplotlib.pyplot as plt
import numpy as np

from Programma_CS2_RENAN.observability.logger_setup import get_logger

logger = get_logger("cs2analyzer.visualization_service")


class VisualizationService:
    def generate_performance_radar(
        self, user_stats: Dict[str, float], pro_stats: Dict[str, float], output_path: str
    ):
        """
        Generates a professional Radar Chart comparing User vs Pro.
        """
        # F5-19: Wrap matplotlib operations — rendering can fail (empty stats, backend issues).
        try:
            labels = list(user_stats.keys())
            num_vars = len(labels)

            # Split the circle into even parts and complete the loop
            angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
            angles += angles[:1]

            # Values
            user_vals = list(user_stats.values())
            user_vals += user_vals[:1]

            pro_vals = list(pro_stats.values())
            pro_vals += pro_vals[:1]

            fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))

            # Draw one axe per variable + add labels
            plt.xticks(angles[:-1], labels, color="grey", size=8)

            # Plot Pro Data
            ax.plot(
                angles, pro_vals, linewidth=1, linestyle="solid", label="Pro Baseline", color="#1f77b4"
            )
            ax.fill(angles, pro_vals, "#1f77b4", alpha=0.1)

            # Plot User Data
            ax.plot(
                angles,
                user_vals,
                linewidth=2,
                linestyle="solid",
                label="Your Performance",
                color="#ff7f0e",
            )
            ax.fill(angles, user_vals, "#ff7f0e", alpha=0.4)

            plt.legend(loc="upper right", bbox_to_anchor=(0.1, 0.1))

            # Save to file
            plt.savefig(output_path, transparent=True)
            plt.close(fig)
            return output_path
        except Exception as e:
            logger.error("generate_performance_radar failed: %s", e)
            raise

    def plot_comparison_v2(
        self, p1_name: str, p2_name: str, p1_stats: Dict[str, Any], p2_stats: Dict[str, Any]
    ) -> io.BytesIO:
        """
        Comparison plot for two players, returning a BytesIO buffer.
        """
        # F5-19: Wrap matplotlib operations — rendering can fail (empty stats, backend issues).
        try:
            # Filter only numeric values for radar chart
            numeric_feats = ["avg_kills", "avg_adr", "avg_hs", "avg_kast", "accuracy"]
            s1 = {k: float(p1_stats.get(k, 0)) for k in numeric_feats}
            s2 = {k: float(p2_stats.get(k, 0)) for k in numeric_feats}

            labels = list(s1.keys())
            angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
            angles += angles[:1]

            v1 = list(s1.values())
            v1 += v1[:1]
            v2 = list(s2.values())
            v2 += v2[:1]

            fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
            ax.plot(angles, v1, label=p1_name)
            ax.fill(angles, v1, alpha=0.25)
            ax.plot(angles, v2, label=p2_name)
            ax.fill(angles, v2, alpha=0.25)

            plt.xticks(angles[:-1], labels)
            plt.legend()

            buf = io.BytesIO()
            plt.savefig(buf, format="png")
            plt.close(fig)
            buf.seek(0)
            return buf
        except Exception as e:
            logger.error("plot_comparison_v2 failed: %s", e)
            raise


_service = VisualizationService()


def get_visualization_service():
    return _service


def generate_performance_radar(
    user_stats: Dict[str, float], pro_stats: Dict[str, float], output_path: str
):
    return _service.generate_performance_radar(user_stats, pro_stats, output_path)
