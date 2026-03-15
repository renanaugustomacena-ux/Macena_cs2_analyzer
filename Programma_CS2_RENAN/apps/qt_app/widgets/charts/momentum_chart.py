"""Momentum chart — cumulative K-D delta with green/red fill."""

from PySide6.QtCharts import (
    QAreaSeries,
    QChart,
    QChartView,
    QLineSeries,
    QValueAxis,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen


class MomentumChart(QChartView):
    """Cumulative kill-death delta as area chart with positive=green, negative=red."""

    def __init__(self, parent=None):
        chart = QChart()
        chart.setBackgroundBrush(QColor("#1a1a1a"))
        chart.setBackgroundRoundness(8)
        chart.setTitle("Momentum (Kill-Death Delta)")
        chart.setTitleBrush(QColor("#ffffff"))
        chart.legend().setVisible(False)
        super().__init__(chart, parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setMinimumHeight(200)

    def plot(self, rounds: list):
        chart = self.chart()
        chart.removeAllSeries()
        for axis in chart.axes():
            chart.removeAxis(axis)

        if not rounds:
            return

        # Compute cumulative K-D
        momentum = []
        cumulative = 0
        for r in rounds:
            cumulative += r.get("kills", 0) - r.get("deaths", 0)
            momentum.append(cumulative)

        round_nums = [r.get("round_number", i + 1) for i, r in enumerate(rounds)]

        # Main line
        line = QLineSeries()
        line.setPen(QPen(QColor("#00ccff"), 2))
        for i, val in enumerate(momentum):
            line.append(round_nums[i], val)

        # Zero baseline
        zero_line = QLineSeries()
        for rn in round_nums:
            zero_line.append(rn, 0)

        # Positive area (green)
        pos_upper = QLineSeries()
        pos_lower = QLineSeries()
        for i, val in enumerate(momentum):
            pos_upper.append(round_nums[i], max(val, 0))
            pos_lower.append(round_nums[i], 0)
        pos_area = QAreaSeries(pos_upper, pos_lower)
        pos_color = QColor("#4CAF50")
        pos_color.setAlphaF(0.2)
        pos_area.setBrush(QBrush(pos_color))
        pos_area.setPen(QPen(Qt.NoPen))

        # Negative area (red)
        neg_upper = QLineSeries()
        neg_lower = QLineSeries()
        for i, val in enumerate(momentum):
            neg_upper.append(round_nums[i], 0)
            neg_lower.append(round_nums[i], min(val, 0))
        neg_area = QAreaSeries(neg_upper, neg_lower)
        neg_color = QColor("#F44336")
        neg_color.setAlphaF(0.2)
        neg_area.setBrush(QBrush(neg_color))
        neg_area.setPen(QPen(Qt.NoPen))

        chart.addSeries(pos_area)
        chart.addSeries(neg_area)
        chart.addSeries(line)

        # Axes
        ax_x = QValueAxis()
        ax_x.setRange(round_nums[0], round_nums[-1])
        ax_x.setTitleText("Round")
        ax_x.setTitleBrush(QColor("#aaaaaa"))
        ax_x.setLabelsColor(QColor("#aaaaaa"))
        ax_x.setGridLineColor(QColor(255, 255, 255, 20))
        ax_x.setLabelFormat("%d")
        chart.addAxis(ax_x, Qt.AlignBottom)

        ax_y = QValueAxis()
        lo = min(momentum)
        hi = max(momentum)
        ax_y.setRange(lo - 1, hi + 1)
        ax_y.setTitleText("Cumulative K-D")
        ax_y.setTitleBrush(QColor("#aaaaaa"))
        ax_y.setLabelsColor(QColor("#aaaaaa"))
        ax_y.setGridLineColor(QColor(255, 255, 255, 20))
        chart.addAxis(ax_y, Qt.AlignLeft)

        for s in chart.series():
            s.attachAxis(ax_x)
            s.attachAxis(ax_y)
