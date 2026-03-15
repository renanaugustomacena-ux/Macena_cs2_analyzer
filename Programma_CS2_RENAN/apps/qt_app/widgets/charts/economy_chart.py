"""Economy bar chart — equipment value per round, CT/T color-coded."""

from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QValueAxis,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter


class EconomyChart(QChartView):
    """Bar chart: equipment value per round, blue=CT, gold=T."""

    def __init__(self, parent=None):
        chart = QChart()
        chart.setBackgroundBrush(QColor("#1a1a1a"))
        chart.setBackgroundRoundness(8)
        chart.setTitle("Economy per Round")
        chart.setTitleBrush(QColor("#ffffff"))
        chart.legend().setVisible(True)
        chart.legend().setLabelColor(QColor("#dcdcdc"))
        chart.legend().setAlignment(Qt.AlignBottom)
        super().__init__(chart, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setMinimumHeight(200)

    def plot(self, rounds: list):
        """Plot from list of dicts with equipment_value and side keys."""
        chart = self.chart()
        chart.removeAllSeries()
        for axis in chart.axes():
            chart.removeAxis(axis)

        if not rounds:
            return

        ct_set = QBarSet("CT")
        ct_set.setColor(QColor("#5C9EE8"))
        t_set = QBarSet("T")
        t_set.setColor(QColor("#E8C95C"))

        categories = []
        for r in rounds:
            rnum = str(r.get("round_number", "?"))
            categories.append(rnum)
            val = r.get("equipment_value", 0)
            if r.get("side") == "CT":
                ct_set.append(val)
                t_set.append(0)
            else:
                ct_set.append(0)
                t_set.append(val)

        series = QBarSeries()
        series.append(ct_set)
        series.append(t_set)
        chart.addSeries(series)

        # X axis
        ax_x = QBarCategoryAxis()
        # Show only every Nth label to avoid clutter
        step = max(1, len(categories) // 15)
        display_cats = [c if i % step == 0 else "" for i, c in enumerate(categories)]
        ax_x.append(display_cats)
        ax_x.setLabelsColor(QColor("#aaaaaa"))
        chart.addAxis(ax_x, Qt.AlignBottom)
        series.attachAxis(ax_x)

        # Y axis
        max_val = max(r.get("equipment_value", 0) for r in rounds)
        ax_y = QValueAxis()
        ax_y.setRange(0, max_val * 1.1)
        ax_y.setTitleText("Equipment ($)")
        ax_y.setTitleBrush(QColor("#aaaaaa"))
        ax_y.setLabelsColor(QColor("#aaaaaa"))
        ax_y.setGridLineColor(QColor(255, 255, 255, 20))
        chart.addAxis(ax_y, Qt.AlignLeft)
        series.attachAxis(ax_y)
