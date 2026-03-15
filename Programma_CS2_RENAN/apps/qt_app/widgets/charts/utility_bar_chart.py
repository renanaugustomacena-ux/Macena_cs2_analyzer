"""Utility comparison bar chart — You vs Pro average, horizontal grouped bars."""

from PySide6.QtCharts import (
    QBarCategoryAxis,
    QChart,
    QChartView,
    QHorizontalBarSeries,
    QBarSet,
    QValueAxis,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter


class UtilityBarChart(QChartView):
    """Horizontal grouped bars: user metrics vs pro average."""

    def __init__(self, parent=None):
        chart = QChart()
        chart.setBackgroundBrush(QColor("#1a1a1a"))
        chart.setBackgroundRoundness(8)
        chart.setTitle("Utility: You vs Pro")
        chart.setTitleBrush(QColor("#ffffff"))
        chart.legend().setVisible(True)
        chart.legend().setLabelColor(QColor("#dcdcdc"))
        chart.legend().setAlignment(Qt.AlignBottom)
        super().__init__(chart, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setMinimumHeight(250)

    def plot(self, utility: dict):
        """Plot from dict with 'user' and optional 'pro' sub-dicts."""
        chart = self.chart()
        chart.removeAllSeries()
        for axis in chart.axes():
            chart.removeAxis(axis)

        user_data = utility.get("user", {})
        pro_data = utility.get("pro", {})
        if not user_data:
            return

        metrics = list(user_data.keys())

        user_set = QBarSet("You")
        user_set.setColor(QColor("#00ccff"))
        pro_set = QBarSet("Pro Avg")
        pro_set.setColor(QColor("#ffaa00"))

        for m in metrics:
            user_set.append(user_data.get(m, 0))
            pro_set.append(pro_data.get(m, 0))

        series = QHorizontalBarSeries()
        series.append(user_set)
        series.append(pro_set)
        chart.addSeries(series)

        # Y axis (categories — metric names)
        ax_cat = QBarCategoryAxis()
        ax_cat.append([m.replace("_", " ").title() for m in metrics])
        ax_cat.setLabelsColor(QColor("#dcdcdc"))
        chart.addAxis(ax_cat, Qt.AlignLeft)
        series.attachAxis(ax_cat)

        # X axis (values)
        all_vals = list(user_data.values()) + list(pro_data.values())
        ax_val = QValueAxis()
        ax_val.setRange(0, max(all_vals) * 1.15 if all_vals else 10)
        ax_val.setTitleText("Value")
        ax_val.setTitleBrush(QColor("#aaaaaa"))
        ax_val.setLabelsColor(QColor("#aaaaaa"))
        ax_val.setGridLineColor(QColor(255, 255, 255, 20))
        chart.addAxis(ax_val, Qt.AlignBottom)
        series.attachAxis(ax_val)
