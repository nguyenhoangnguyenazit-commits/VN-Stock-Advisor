"""Analytics package: technical indicators, confluence scoring, and trend predictions.

Milestone: M2_ANALYTICS
"""

from app.analytics.models import (
    BollingerBands,
    BollingerBandsResult,
    ConfluenceResult,
    ForecastPoint,
    ForecastReport,
    IndicatorSummary,
    MACDResult,
    PredictionSummary,
    SupportResistance,
    TradeSetup,
)
from app.analytics.indicators import (
    TechnicalEngine,
    calculate_indicators,
    evaluate_confluence,
)
from app.analytics.prediction import (
    PredictionEngine,
    forecast_trend,
)

__all__ = [
    # Models
    "MACDResult",
    "BollingerBands",
    "BollingerBandsResult",
    "ConfluenceResult",
    "IndicatorSummary",
    "ForecastPoint",
    "SupportResistance",
    "TradeSetup",
    "PredictionSummary",
    "ForecastReport",
    # Engines & Functions
    "TechnicalEngine",
    "calculate_indicators",
    "evaluate_confluence",
    "PredictionEngine",
    "forecast_trend",
]
