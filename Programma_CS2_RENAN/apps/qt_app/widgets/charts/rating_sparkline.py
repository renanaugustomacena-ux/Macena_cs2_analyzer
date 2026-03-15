"""Rating sparkline — compact trend with reference lines."""

from PySide6.QtCharts import (
    QAreaSeries,
    QChart,
    QChartView,
    QLineSeries,
    QValueAxis,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen


class RatingSparkline(QChartView):
    """Rating trend with 1.0/1.1/0.9 reference lines and filled area."""

    def __init__(self, parent=None):
        chart = QChart()
        chart.setBackgroundBrush(QColor("#1a1a1a"))
        chart.setBackgroundRoundness(8)
        chart.setTitle("Rating Trend")
        chart.setTitleBrush(QColor("#ffffff"))
        chart.legend().setVisible(False)
        super().__init__(chart, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setMinimumHeight(200)

    def plot(self, history: list):
        chart = self.chart()
        chart.removeAllSeries()
        for axis in chart.axes():
            chart.removeAxis(axis)

        if not history:
            return

        ratings = [
            h.get("rating", 1.0) if h.get("rating") is not None else 1.0
            for h in history
        ]
        n = len(ratings)

        # Rating line
        line = QLineSeries()
        line.setPen(QPen(QColor("#00ccff"), 2))
        for i, r in enumerate(ratings):
            line.append(i, r)

        # Fill below the line
        baseline = QLineSeries()
        floor = min(ratings) - 0.05
        for i in range(n):
            baseline.append(i, floor)
        area = QAreaSeries(line, baseline)
        fill = QColor("#00ccff")
        fill.setAlphaF(0.15)
        area.setBrush(QBrush(fill))
        area.setPen(QPen(Qt.NoPen))

        chart.addSeries(area)
        chart.addSeries(line)

        # Reference lines
        for ref_val, ref_color, style in [
            (1.0, "#ffffff", Qt.DashLine),
            (1.1, "#4CAF50", Qt.DashLine),
            (0.9, "#F44336", Qt.DashLine),
        ]:
            ref = QLineSeries()
            pen = QPen(QColor(ref_color), 1, style)
            pen.setColor(QColor(ref_color))
            ref.setPen(pen)
            ref.setOpacity(0.4)
            ref.append(0, ref_val)
            ref.append(n - 1, ref_val)
            chart.addSeries(ref)

        # Axes
        ax_x = QValueAxis()
        ax_x.setRange(0, max(n - 1, 1))
        ax_x.setLabelsColor(QColor("#aaaaaa"))
        ax_x.setGridLineColor(QColor(255, 255, 255, 20))
        ax_x.setLabelFormat("%d")
        chart.addAxis(ax_x, Qt.AlignBottom)

        ax_y = QValueAxis()
        ax_y.setRange(floor, max(ratings) + 0.05)
        ax_y.setTitleText("Rating")
        ax_y.setTitleBrush(QColor("#aaaaaa"))
        ax_y.setLabelsColor(QColor("#aaaaaa"))
        ax_y.setGridLineColor(QColor(255, 255, 255, 20))
        chart.addAxis(ax_y, Qt.AlignLeft)

        for s in chart.series():
            s.attachAxis(ax_x)
            s.attachAxis(ax_y)
