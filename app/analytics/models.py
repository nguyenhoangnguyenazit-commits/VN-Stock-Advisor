"""Pydantic data models for technical indicators, confluence scoring, and predictive analytics."""

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


class MACDResult(BaseModel):
    """Schema representing Moving Average Convergence Divergence (MACD) metrics."""
    model_config = ConfigDict(populate_by_name=True)

    line: float = Field(description="MACD fast line (EMA12 - EMA26)")
    signal: float = Field(description="MACD signal line (9-period EMA of MACD line)")
    histogram: float = Field(description="MACD histogram bar (line - signal)")


class BollingerBands(BaseModel):
    """Schema representing Bollinger Bands volatility envelope."""
    model_config = ConfigDict(populate_by_name=True)

    upper: float = Field(description="Upper band: Middle + 2.0 * standard deviation")
    middle: float = Field(description="Middle band: 20-period Simple Moving Average")
    lower: float = Field(description="Lower band: Middle - 2.0 * standard deviation")
    bandwidth: float = Field(default=0.0, description="Normalized bandwidth: (upper - lower) / middle")
    pct_b: float = Field(default=0.5, description="%B oscillator: (current_price - lower) / (upper - lower)")


# Alias for compatibility with indicator calculation schemas
BollingerBandsResult = BollingerBands


class ConfluenceResult(BaseModel):
    """Schema representing composite indicator confluence evaluation."""
    model_config = ConfigDict(populate_by_name=True)

    score: float = Field(
        ge=-100.0,
        le=100.0,
        description="Normalized composite score from -100.0 (bearish) to +100.0 (bullish)"
    )
    signal: Literal["STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL", "ACCUMULATE"] = Field(
        default="NEUTRAL",
        description="Discrete technical trade bias"
    )
    confidence: float = Field(default=50.0, description="Heuristic confidence percentage [0.0, 100.0]")
    components: Dict[str, float] = Field(
        default_factory=dict,
        description="Sub-component indicator score contributions"
    )
    breakdown: Dict[str, float] = Field(
        default_factory=dict,
        description="Pillar breakdown matching components dictionary"
    )
    trend_score: float = Field(default=0.0, description="Trend Pillar contribution [-30, +30]")
    momentum_score: float = Field(default=0.0, description="Momentum Pillar contribution [-25, +25]")
    macd_score: float = Field(default=0.0, description="MACD Pillar contribution [-25, +25]")
    volatility_score: float = Field(default=0.0, description="Volatility Pillar contribution [-10, +10]")
    volume_score: float = Field(default=0.0, description="Volume Pillar contribution [-10, +10]")
    rationale: List[str] = Field(default_factory=list, description="Descriptive rationale statements")


class IndicatorSummary(BaseModel):
    """Schema representing the complete technical indicator profile for a ticker."""
    model_config = ConfigDict(populate_by_name=True)

    symbol: str = Field(default="", description="Ticker symbol, e.g. FPT, HPG, VNINDEX")
    current_price: float = Field(default=0.0, description="Latest matching/closing price in raw VND")
    sma20: float = Field(description="20-period Simple Moving Average")
    sma50: float = Field(description="50-period Simple Moving Average")
    sma200: float = Field(description="200-period Simple Moving Average (or fallback to longest available SMA)")
    ema12: float = Field(description="12-period Exponential Moving Average")
    ema26: float = Field(description="26-period Exponential Moving Average")
    rsi14: float = Field(ge=0.0, le=100.0, description="14-period Relative Strength Index [0.0, 100.0]")
    macd: MACDResult = Field(description="MACD oscillator structure")
    bollinger: BollingerBands = Field(description="Bollinger Bands structure")
    atr14: float = Field(ge=0.0, description="14-period Average True Range volatility measure in VND")
    volume_sma20: float = Field(default=0.0, description="20-period Volume Simple Moving Average")
    volume_surge_factor: float = Field(default=1.0, description="Ratio of latest volume to 20-period Volume SMA")
    confluence_score: float = Field(
        ge=-100.0,
        le=100.0,
        description="Aggregated technical score [-100.0, 100.0]"
    )
    confluence_signal: Literal["STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL", "ACCUMULATE"] = Field(
        default="NEUTRAL",
        description="Discrete technical signal"
    )
    confluence: Optional[ConfluenceResult] = Field(default=None, description="Detailed confluence breakdown")


class ForecastPoint(BaseModel):
    """Schema representing a projected price forecast at a designated horizon."""
    model_config = ConfigDict(populate_by_name=True)

    horizon_days: int = Field(description="Forecast horizon in calendar/trading days (7, 14, 30)")
    target_price: float = Field(description="Projected target price from Damped Holt smoothing in VND")
    expected_return_pct: float = Field(description="Expected percentage price change relative to current price")
    upper_80: float = Field(description="Upper boundary of 80% confidence cone (z=1.28)")
    lower_80: float = Field(description="Lower boundary of 80% confidence cone")
    upper_95: float = Field(description="Upper boundary of 95% confidence cone (z=1.96)")
    lower_95: float = Field(description="Lower boundary of 95% confidence cone")


class SupportResistance(BaseModel):
    """Schema representing key price pivot levels."""
    model_config = ConfigDict(populate_by_name=True)

    s1: float = Field(description="Primary support level")
    s2: float = Field(description="Secondary major support level (s2 <= s1)")
    r1: float = Field(description="Primary resistance level (s1 <= r1)")
    r2: float = Field(description="Secondary major resistance level (r1 <= r2)")


class TradeSetup(BaseModel):
    """Schema representing an actionable trade setup with risk management rules."""
    model_config = ConfigDict(populate_by_name=True)

    entry_zone: List[float] = Field(description="Entry price interval [entry_low, entry_high] where entry_low <= entry_high")
    stop_loss: float = Field(description="Protective stop-loss price strictly below entry_low")
    take_profit_1: float = Field(description="Conservative target 1 strictly above entry_high")
    take_profit_2: float = Field(default=0.0, description="Extended runner target 2 (>= take_profit_1)")
    risk_reward_ratio: float = Field(
        description="Risk-Reward Ratio: (take_profit_1 - entry_high) / (entry_low - stop_loss) >= 1.5"
    )


class PredictionSummary(BaseModel):
    """Schema representing complete trend prediction and trade targets for a ticker."""
    model_config = ConfigDict(populate_by_name=True)

    symbol: str = Field(default="", description="Ticker symbol, e.g. FPT, HPG")
    current_price: float = Field(description="Current matching price in raw VND")
    signal: Literal["STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL", "ACCUMULATE"] = Field(
        default="NEUTRAL",
        description="Overall predictive directional signal"
    )
    confidence_score: float = Field(description="Predictive model confidence score [0.0, 100.0]")
    forecasts: List[ForecastPoint] = Field(description="List of multi-horizon forecast points")
    support_resistance: SupportResistance = Field(description="Pivot support and resistance matrix")
    trade_setup: TradeSetup = Field(description="Suggested trade target setup")


# Alias for backward compatibility with PROJECT.md Interface Contract § 116
ForecastReport = PredictionSummary
