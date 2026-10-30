"""Technical Indicators & Confluence Engine for Vietnamese Stock Market.

Module: app/analytics/indicators.py
Milestone: M2_ANALYTICS

100% Pure Python implementation with zero external scientific dependencies (no numpy/pandas):
1. SMA (20, 50, 200) with dynamic history length fallback
2. EMA (12, 26) with standard alpha = 2 / (N + 1)
3. RSI (14, Wilder smoothing, strictly bounded [0.0, 100.0], 50.0 on zero variance)
4. MACD (12, 26, 9) line, signal, and histogram
5. Bollinger Bands (20, 2) upper >= middle >= lower strictly
6. ATR (14, Wilder smoothing, strictly >= 0.0)
7. Volume SMA (20) & Surge Factor
8. 5-Pillar Confluence Scoring (normalized to [-100.0, +100.0])
"""

import math
from typing import Any, Dict, List, Optional, Tuple, Union

from app.data.models import OHLCVRecord
from app.analytics.models import (
    BollingerBands,
    BollingerBandsResult,
    ConfluenceResult,
    IndicatorSummary,
    MACDResult,
)


# ==============================================================================
# Helper Extraction & Sorting
# ==============================================================================

def _sort_and_extract_candles(
    candles: List[Union[OHLCVRecord, Dict[str, Any]]]
) -> Tuple[List[float], List[float], List[float], List[float], List[int]]:
    """
    Sorts candles chronologically ascending and extracts opens, highs, lows, closes, volumes.
    """
    if not candles:
        raise ValueError("Candles list cannot be empty for indicator calculation")

    def _get_time(c: Union[OHLCVRecord, Dict[str, Any]]) -> str:
        if isinstance(c, dict):
            return str(c.get("time", c.get("date", "")))
        return str(getattr(c, "time", getattr(c, "date", "")))

    sorted_candles = sorted(candles, key=_get_time)

    opens: List[float] = []
    highs: List[float] = []
    lows: List[float] = []
    closes: List[float] = []
    volumes: List[int] = []

    for c in sorted_candles:
        if isinstance(c, dict):
            c_close = float(c.get("close", 0.0))
            c_high = float(c.get("high", c_close))
            c_low = float(c.get("low", c_close))
            c_open = float(c.get("open", c_close))
            c_vol = int(c.get("volume", 0))
        else:
            c_close = float(c.close)
            c_high = float(getattr(c, "high", c_close))
            c_low = float(getattr(c, "low", c_close))
            c_open = float(getattr(c, "open", c_close))
            c_vol = int(getattr(c, "volume", 0))

        opens.append(c_open)
        highs.append(c_high)
        lows.append(c_low)
        closes.append(c_close)
        volumes.append(c_vol)

    return opens, highs, lows, closes, volumes


# ==============================================================================
# Pure Python Technical Indicator Functions
# ==============================================================================

def calculate_sma(series: List[float], period: int) -> float:
    """
    Computes Simple Moving Average of the last `period` elements.
    Uses dynamic window fallback: min(len(series), period) if history is shorter than period.
    """
    if not series:
        return 0.0
    effective_p = min(len(series), period)
    if effective_p == 0:
        return 0.0
    return sum(series[-effective_p:]) / float(effective_p)


def calculate_ema_series(series: List[float], period: int) -> List[float]:
    """
    Computes full Exponential Moving Average series using standard alpha = 2 / (N + 1).
    Seeded with SMA of first available bars.
    """
    if not series:
        return []
    if len(series) == 1:
        return [series[0]]

    k = 2.0 / (period + 1.0)
    res: List[float] = []
    for i in range(len(series)):
        if i < period - 1:
            res.append(sum(series[:i + 1]) / float(i + 1))
        elif i == period - 1:
            sma_seed = sum(series[:period]) / float(period)
            res.append(sma_seed)
        else:
            val = series[i] * k + res[-1] * (1.0 - k)
            res.append(val)
    return res


def calculate_rsi(series: List[float], period: int = 14) -> float:
    """
    Computes 14-period Relative Strength Index using Wilder's exponential smoothing.
    Strictly bounded in [0.0, 100.0].
    Returns 50.0 on zero variance (flatline series) or len < 2.
    """
    if len(series) < 2:
        return 50.0

    gains: List[float] = []
    losses: List[float] = []
    for i in range(1, len(series)):
        diff = series[i] - series[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))

    if len(gains) < period:
        avg_g = sum(gains) / float(len(gains)) if gains else 0.0
        avg_l = sum(losses) / float(len(losses)) if losses else 0.0
    else:
        avg_g = sum(gains[:period]) / float(period)
        avg_l = sum(losses[:period]) / float(period)
        for i in range(period, len(gains)):
            avg_g = (avg_g * (period - 1) + gains[i]) / float(period)
            avg_l = (avg_l * (period - 1) + losses[i]) / float(period)

    if avg_l == 0.0:
        if avg_g == 0.0:
            return 50.0  # Flatline price series
        return 100.0     # Strictly positive gains

    rs = avg_g / avg_l
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return max(0.0, min(100.0, round(rsi, 2)))


def calculate_macd(
    closes: List[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9
) -> MACDResult:
    """Computes MACD Line, Signal Line, and Histogram."""
    if not closes:
        return MACDResult(line=0.0, signal=0.0, histogram=0.0)
    if len(closes) == 1:
        return MACDResult(line=0.0, signal=0.0, histogram=0.0)

    ema_fast = calculate_ema_series(closes, fast)
    ema_slow = calculate_ema_series(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = calculate_ema_series(macd_line, signal)

    line_val = round(macd_line[-1], 2)
    sig_val = round(signal_line[-1], 2)
    hist_val = round(line_val - sig_val, 2)

    return MACDResult(line=line_val, signal=sig_val, histogram=hist_val)


def calculate_bollinger_bands(
    closes: List[float],
    period: int = 20,
    num_std: float = 2.0
) -> BollingerBands:
    """
    Computes Bollinger Bands: Middle, Upper, Lower, Bandwidth, and %B.
    Strict invariant: Upper >= Middle >= Lower.
    """
    if not closes:
        return BollingerBands(middle=0.0, upper=0.0, lower=0.0, bandwidth=0.0, pct_b=0.5)

    effective_p = min(len(closes), period)
    sub = closes[-effective_p:]
    mid = sum(sub) / float(effective_p)
    variance = sum((x - mid) ** 2 for x in sub) / float(effective_p)
    std_dev = math.sqrt(max(0.0, variance))

    upper = mid + num_std * std_dev
    lower = mid - num_std * std_dev
    bandwidth = (upper - lower) / mid if mid > 0 else 0.0

    current = closes[-1]
    if upper != lower:
        pct_b = (current - lower) / (upper - lower)
    else:
        pct_b = 0.5

    # Defensive guarantee for ordering
    if upper < mid:
        upper = mid
    if lower > mid:
        lower = mid

    return BollingerBands(
        middle=round(mid, 1),
        upper=round(upper, 1),
        lower=round(lower, 1),
        bandwidth=round(bandwidth, 4),
        pct_b=round(pct_b, 2)
    )


def calculate_atr(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 14
) -> float:
    """
    Computes Average True Range using Wilder's smoothing.
    Strictly >= 0.0.
    """
    n = len(highs)
    if n == 0:
        return 0.0
    if n < 2:
        return max(round(highs[0] - lows[0], 1), 0.0)

    trs: List[float] = [highs[0] - lows[0]]
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1])
        )
        trs.append(tr)

    if len(trs) <= period:
        atr = sum(trs) / float(len(trs))
    else:
        atr = sum(trs[:period]) / float(period)
        for i in range(period, len(trs)):
            atr = (atr * (period - 1) + trs[i]) / float(period)

    return max(0.0, round(atr, 1))


def calculate_volume_metrics(
    volumes: List[int],
    period: int = 20
) -> Tuple[float, float]:
    """
    Computes 20-period Volume SMA and current Volume Surge Factor.
    Handles zero volumes without ZeroDivisionError.
    """
    if not volumes:
        return 0.0, 1.0

    effective_p = min(len(volumes), period)
    vol_sma20 = sum(volumes[-effective_p:]) / float(effective_p)
    latest_vol = volumes[-1]
    surge_factor = round(latest_vol / vol_sma20, 2) if vol_sma20 > 0 else 1.0

    return round(vol_sma20, 1), surge_factor


# ==============================================================================
# TechnicalEngine Service
# ==============================================================================

class TechnicalEngine:
    """
    Quantitative technical analysis engine for Vietnamese stock market.
    Computes 7 essential indicators and composite confluence score.
    """

    @classmethod
    def calculate_indicators(
        cls,
        candles: List[Union[OHLCVRecord, Dict[str, Any]]],
        symbol: str = "UNKNOWN"
    ) -> IndicatorSummary:
        """
        Calculates all 7 essential technical indicators and confluence score
        from a series of OHLCV candles (auto-sorted chronologically).
        """
        if not candles:
            raise ValueError("Candles list cannot be empty for indicator calculation")

        opens, highs, lows, closes, volumes = _sort_and_extract_candles(candles)
        n = len(closes)
        current_price = closes[-1]

        # 1. Moving Averages with dynamic period fallback
        sma20 = round(calculate_sma(closes, 20), 1)
        sma50 = round(calculate_sma(closes, 50), 1)
        sma200 = round(calculate_sma(closes, 200), 1)

        ema12_series = calculate_ema_series(closes, 12)
        ema26_series = calculate_ema_series(closes, 26)
        ema12 = round(ema12_series[-1], 1) if ema12_series else current_price
        ema26 = round(ema26_series[-1], 1) if ema26_series else current_price

        # 2. Oscillators & Volatility
        rsi14 = calculate_rsi(closes, 14)
        macd = calculate_macd(closes, 12, 26, 9)
        bollinger = calculate_bollinger_bands(closes, 20, 2.0)
        atr14 = calculate_atr(highs, lows, closes, 14)

        # 3. Volume Metrics
        vol_sma20, surge_factor = calculate_volume_metrics(volumes, 20)

        # 4. Preliminary summary object for confluence evaluation
        summary = IndicatorSummary(
            symbol=symbol,
            current_price=round(current_price, 2),
            sma20=sma20,
            sma50=sma50,
            sma200=sma200,
            ema12=ema12,
            ema26=ema26,
            rsi14=rsi14,
            macd=macd,
            bollinger=bollinger,
            atr14=atr14,
            volume_sma20=vol_sma20,
            volume_surge_factor=surge_factor,
            confluence_score=0.0,
            confluence_signal="NEUTRAL"
        )

        # 5. Evaluate Confluence
        confluence_res = cls.evaluate_confluence(summary)
        summary.confluence_score = confluence_res.score
        summary.confluence_signal = confluence_res.signal
        summary.confluence = confluence_res

        return summary

    @classmethod
    def evaluate_confluence(
        cls,
        ind: IndicatorSummary
    ) -> ConfluenceResult:
        """
        Evaluates multi-factor composite confluence score (-100 to +100)
        across 5 market pillars:
        - Pillar 1: Trend Alignment & Moving Averages (30%)
        - Pillar 2: Momentum / RSI (25%)
        - Pillar 3: MACD Convergence/Divergence (25%)
        - Pillar 4: Bollinger Bands Volatility & Location (10%)
        - Pillar 5: Volume Confirmation (10%)

        Categorizes into 5 discrete trade signals:
        - STRONG_BUY (+60.0 to +100.0)
        - BUY (+20.0 to +59.9)
        - NEUTRAL (-19.9 to +19.9)
        - SELL (-59.9 to -20.0)
        - STRONG_SELL (-100.0 to -60.0)
        """
        price = ind.current_price
        sma20 = ind.sma20
        sma50 = ind.sma50
        sma200 = ind.sma200
        ema12 = ind.ema12
        ema26 = ind.ema26
        rsi = ind.rsi14
        macd = ind.macd
        bb = ind.bollinger
        surge = ind.volume_surge_factor

        rationale: List[str] = []

        # ---------------------------------------------------------------------
        # Pillar 1: Trend Alignment & Moving Averages (Weight: 30 pts)
        # ---------------------------------------------------------------------
        trend_pts = 0.0

        def _diff_score(val: float, ref: float, thresh_high: float, thresh_low: float) -> float:
            if ref <= 0:
                return 0.0
            pct = (val - ref) / ref
            if pct >= thresh_high:
                return 5.0
            elif pct > thresh_low:
                return 2.5
            elif pct <= -thresh_high:
                return -5.0
            elif pct < -thresh_low:
                return -2.5
            return 0.0

        trend_pts += _diff_score(price, sma20, 0.01, 0.001)
        trend_pts += _diff_score(price, sma50, 0.02, 0.002)
        trend_pts += _diff_score(price, sma200, 0.03, 0.003)

        # Moving Average Stack Hierarchy
        if price > sma20 > sma50 > sma200:
            trend_pts += 7.5
            rationale.append("Bullish moving average alignment: Price > SMA20 > SMA50 > SMA200")
        elif price > sma20 > sma50:
            trend_pts += 4.0
        elif price < sma20 < sma50 < sma200:
            trend_pts -= 7.5
            rationale.append("Bearish moving average breakdown: Price < SMA20 < SMA50 < SMA200")
        elif price < sma20 < sma50:
            trend_pts -= 4.0

        # Fast EMA12 vs Slow EMA26
        if price > 0:
            pct_ema = (ema12 - ema26) / price
            if pct_ema >= 0.01:
                trend_pts += 7.5
            elif pct_ema > 0.001:
                trend_pts += 3.5
            elif pct_ema <= -0.01:
                trend_pts -= 7.5
            elif pct_ema < -0.001:
                trend_pts -= 3.5

        trend_score = max(-30.0, min(30.0, trend_pts))

        # ---------------------------------------------------------------------
        # Pillar 2: Momentum & RSI-14 (Weight: 25 pts)
        # ---------------------------------------------------------------------
        if rsi >= 80.0:
            momentum_score = 15.0
            rationale.append(f"RSI-14 ({rsi:.1f}) in extreme overbought territory (>80)")
        elif rsi >= 70.0:
            momentum_score = 25.0
            rationale.append(f"RSI-14 ({rsi:.1f}) strong bullish momentum (70-80)")
        elif rsi >= 60.0:
            momentum_score = 15.0 + ((rsi - 60.0) / 10.0) * 10.0
        elif rsi > 50.5:
            momentum_score = ((rsi - 50.0) / 10.0) * 15.0
        elif rsi < 49.5:
            if rsi >= 40.0:
                momentum_score = -(((50.0 - rsi) / 10.0) * 15.0)
            elif rsi >= 30.0:
                momentum_score = -15.0 - (((40.0 - rsi) / 10.0) * 10.0)
            elif rsi >= 20.0:
                momentum_score = -25.0
                rationale.append(f"RSI-14 ({rsi:.1f}) deep bearish momentum (20-30)")
            else:
                momentum_score = -15.0
                rationale.append(f"RSI-14 ({rsi:.1f}) in extreme oversold territory (<20)")
        else:
            momentum_score = 0.0

        momentum_score = max(-25.0, min(25.0, momentum_score))

        # ---------------------------------------------------------------------
        # Pillar 3: MACD Trend & Convergence/Divergence (Weight: 25 pts)
        # ---------------------------------------------------------------------
        macd_pts = 0.0
        line = macd.line
        hist = macd.histogram

        # Regime relative to zero
        if line > 0.01:
            macd_pts += 10.0
        elif line < -0.01:
            macd_pts -= 10.0

        # Divergence & Signal cross
        if hist > 0.01:
            if price > 0 and hist >= 0.005 * price:
                macd_pts += 15.0
                rationale.append("MACD histogram showing strong positive expansion")
            else:
                macd_pts += 8.0
        elif hist < -0.01:
            if price > 0 and hist <= -0.005 * price:
                macd_pts -= 15.0
                rationale.append("MACD histogram showing strong negative expansion")
            else:
                macd_pts -= 8.0

        macd_score = max(-25.0, min(25.0, macd_pts))

        # ---------------------------------------------------------------------
        # Pillar 4: Bollinger Bands Volatility & Position (Weight: 10 pts)
        # ---------------------------------------------------------------------
        bb_pts = 0.0
        mid = bb.middle
        pct_b = bb.pct_b

        if mid > 0:
            pct_mid = (price - mid) / mid
            if pct_mid >= 0.005:
                bb_pts += 3.0
            elif pct_mid <= -0.005:
                bb_pts -= 3.0

        if pct_b >= 0.8:
            bb_pts += 7.0
            rationale.append(f"Price trading in upper Bollinger band (PctB={pct_b:.2f})")
        elif pct_b >= 0.6:
            bb_pts += 4.0
        elif pct_b <= 0.2:
            bb_pts -= 7.0
            rationale.append(f"Price trading in lower Bollinger band (PctB={pct_b:.2f})")
        elif pct_b <= 0.4:
            bb_pts -= 4.0

        volatility_score = max(-10.0, min(10.0, bb_pts))

        # ---------------------------------------------------------------------
        # Pillar 5: Volume Confirmation & Surge (Weight: 10 pts)
        # ---------------------------------------------------------------------
        vol_pts = 0.0
        if price > sma20:
            if surge >= 1.5:
                vol_pts += 10.0
                rationale.append(f"Bullish volume breakout: {surge:.2f}x 20-day average volume")
            elif surge >= 1.1:
                vol_pts += 5.0
            elif surge >= 0.9:
                vol_pts += 2.0
            else:
                vol_pts -= 2.0
        elif price < sma20:
            if surge >= 1.5:
                vol_pts -= 10.0
                rationale.append(f"High volume selloff: {surge:.2f}x 20-day average volume")
            elif surge >= 1.1:
                vol_pts -= 5.0
            elif surge >= 0.9:
                vol_pts -= 2.0
            else:
                vol_pts += 2.0

        volume_score = max(-10.0, min(10.0, vol_pts))

        # ---------------------------------------------------------------------
        # Composite Confluence Sum & Clamping [-100.0, +100.0]
        # ---------------------------------------------------------------------
        total = trend_score + momentum_score + macd_score + volatility_score + volume_score
        total = max(-100.0, min(100.0, round(total, 1)))

        # Signal Categorization
        if total >= 60.0:
            signal = "STRONG_BUY"
        elif total >= 20.0:
            signal = "BUY"
        elif total >= -19.0:
            signal = "NEUTRAL"
        elif total >= -59.0:
            signal = "SELL"
        else:
            signal = "STRONG_SELL"

        components_dict = {
            "trend": round(trend_score, 1),
            "momentum": round(momentum_score, 1),
            "macd": round(macd_score, 1),
            "volatility": round(volatility_score, 1),
            "volume": round(volume_score, 1),
        }

        conf_pct = round(min(100.0, max(10.0, 50.0 + abs(total) * 0.5)), 1)

        return ConfluenceResult(
            score=total,
            signal=signal,
            confidence=conf_pct,
            components=components_dict,
            breakdown=components_dict,
            trend_score=round(trend_score, 1),
            momentum_score=round(momentum_score, 1),
            macd_score=round(macd_score, 1),
            volatility_score=round(volatility_score, 1),
            volume_score=round(volume_score, 1),
            rationale=rationale,
        )


# Module-level convenience wrappers
calculate_indicators = TechnicalEngine.calculate_indicators
evaluate_confluence = TechnicalEngine.evaluate_confluence
