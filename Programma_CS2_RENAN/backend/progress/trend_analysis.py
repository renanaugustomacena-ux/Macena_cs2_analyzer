import numpy as np


def compute_trend(values):
    # AC-39-01: Guard against insufficient data for polynomial fit
    if len(values) < 2:
        return 0.0, 0.0, 0.0
    x = np.arange(len(values))
    y = np.array(values)

    slope = np.polyfit(x, y, 1)[0]
    volatility = y.std()

    confidence = min(1.0, len(values) / 30)

    return slope, volatility, confidence
