"""Radar/spider chart for skill attributes — replaces RadarChartWidget (matplotlib).

QtCharts doesn't have a true polar/radar chart, so we use QPainter directly.
This gives us full control over the gaming aesthetic.
"""

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from Programma_CS2_RENAN.observability.logger_setup import get_logger

_logger = get_logger("cs2analyzer.qt_radar_chart")


class RadarChart(QWidget):
    """Custom-painted polar spider chart for skill attributes (0-100 scale)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: dict = {}
        self.setMinimumSize(250, 250)

    def plot(self, skill_dict: dict):
        """Set data and trigger repaint. skill_dict: {name: value (0-100)}."""
        if len(skill_dict) < 3:
            _logger.warning("RadarChart needs >= 3 attributes, got %d", len(skill_dict))
            self._data = {}
        else:
            self._data = skill_dict
        self.update()

    def paintEvent(self, event):
        if not self._data:
            painter = QPainter(self)
            painter.setPen(QColor("#3a3a5a"))
            painter.drawText(self.rect(), Qt.AlignCenter, "Not enough data")
            painter.end()
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Background
        painter.fillRect(self.rect(), QColor("#1a1a1a"))

        metrics = list(self._data.keys())
        values = list(self._data.values())
        n = len(metrics)

        cx = self.width() / 2
        cy = self.height() / 2
        radius = min(cx, cy) - 40

        angles = [2 * math.pi * i / n - math.pi / 2 for i in range(n)]

        # Grid rings (25, 50, 75, 100)
        grid_pen = QPen(QColor(255, 255, 255, 40), 1)
        painter.setPen(grid_pen)
        for level in (25, 50, 75, 100):
            r = radius * level / 100
            points = QPolygonF()
            for a in angles:
                points.append(QPointF(cx + r * math.cos(a), cy + r * math.sin(a)))
            points.append(points[0])
            painter.drawPolyline(points)

        # Axis lines
        axis_pen = QPen(QColor(255, 255, 255, 25), 1)
        painter.setPen(axis_pen)
        for a in angles:
            painter.drawLine(
                QPointF(cx, cy),
                QPointF(cx + radius * math.cos(a), cy + radius * math.sin(a)),
            )

        # Data polygon
        data_points = QPolygonF()
        for i, a in enumerate(angles):
            v = max(0, min(values[i], 100))
            r = radius * v / 100
            data_points.append(QPointF(cx + r * math.cos(a), cy + r * math.sin(a)))
        data_points.append(data_points[0])

        # Fill
        fill_color = QColor("#aa00ff")
        fill_color.setAlphaF(0.25)
        painter.setBrush(QBrush(fill_color))
        painter.setPen(QPen(QColor("#aa00ff"), 2))
        painter.drawPolygon(data_points)

        # Labels
        label_font = QFont("Roboto", 10)
        painter.setFont(label_font)
        painter.setPen(QColor("#dcdcdc"))
        for i, a in enumerate(angles):
            lx = cx + (radius + 20) * math.cos(a)
            ly = cy + (radius + 20) * math.sin(a)
            text = metrics[i]
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(text)
            th = fm.height()
            painter.drawText(QRectF(lx - tw / 2, ly - th / 2, tw, th), Qt.AlignCenter, text)

        # Value labels on points
        painter.setFont(QFont("Roboto", 8))
        painter.setPen(QColor("#ffffff"))
        for i, a in enumerate(angles):
            v = max(0, min(values[i], 100))
            r = radius * v / 100
            px = cx + r * math.cos(a)
            py = cy + r * math.sin(a)
            painter.drawText(QRectF(px - 12, py - 16, 24, 12), Qt.AlignCenter, f"{v:.0f}")

        painter.end()
