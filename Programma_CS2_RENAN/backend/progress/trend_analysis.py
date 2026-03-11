import numpy as np

# Number of samples at which trend confidence reaches 1.0.
TREND_CONFIDENCE_SAMPLE_SIZE = 30


def compute_trend(values):
    # AC-39-01: Guard against insufficient data for polynomial fit
    if len(values) < 2:
        return 0.0, 0.0, 0.0
    x = np.arange(len(values))
    y = np.array(values)

    slope = np.polyfit(x, y, 1)[0]
    volatility = y.std()

    confidence = min(1.0, len(values) / TREND_CONFIDENCE_SAMPLE_SIZE)

    return slope, volatility, confidence
