"""Trend Prediction Engine for Vietnamese Stock Market.

Module: app/analytics/prediction.py
Milestone: M2_ANALYTICS

100% Pure Python implementation with zero external scientific dependencies:
1. Damped Holt Linear Exponential Smoothing (alpha=0.30, beta=0.10, phi=0.90)
2. Volatility Cones: 80% (z=1.28) and 95% (z=1.96) confidence intervals
3. Support & Resistance Pivots: S2 <= S1 <= R1 <= R2 guaranteed
4. Actionable Trade Setup: entry_zone, stop_loss, take_profit_1, take_profit_2, and RRR >= 1.5
5. Directional Signal & Statistical Confidence Scoring
"""

import math
from typing import Any, Dict, List, Optional, Tuple, Union

from app.data.models import OHLCVRecord
from app.analytics.models import (
    ForecastPoint,
    ForecastReport,
    PredictionSummary,
    SupportResistance,
    TradeSetup,
)
from app.analytics.indicators import calculate_atr


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
        raise ValueError("Candle list cannot be empty")

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
# PredictionEngine Service
# ==============================================================================

class PredictionEngine:
    """Quantitative Prediction & Trend Forecasting Engine."""

    @classmethod
    def calculate_atr(
        cls,
        candles: List[Union[OHLCVRecord, Dict[str, Any]]],
        period: int = 14
    ) -> float:
        """Computes 14-period Average True Range using Wilder's smoothing."""
        if not candles:
            return 0.0
        _, highs, lows, closes, _ = _sort_and_extract_candles(candles)
        return calculate_atr(highs, lows, closes, period=period)

    @classmethod
    def calculate_pivots(
        cls,
        candles: List[Union[OHLCVRecord, Dict[str, Any]]],
        window: int = 20,
        method: str = "classical"
    ) -> SupportResistance:
        """
        Computes support & resistance pivot levels from recent candle window.
        Guarantees strict monotonicity: S2 <= S1 <= R1 <= R2.
        """
        if not candles:
            raise ValueError("Cannot calculate pivots on empty candle series")

        _, highs, lows, closes, _ = _sort_and_extract_candles(candles)
        recent_h = highs[-window:] if len(highs) >= window else highs
        recent_l = lows[-window:] if len(lows) >= window else lows
        recent_c = closes[-window:] if len(closes) >= window else closes

        H = max(recent_h)
        L = min(recent_l)
        if H < L:
            H, L = L, H
        C = recent_c[-1]
        if C < L:
            C = L
        elif C > H:
            C = H
        P = (H + L + C) / 3.0

        if method == "fibonacci":
            diff = H - L
            r2 = P + 0.618 * diff
            r1 = P + 0.382 * diff
            s1 = P - 0.382 * diff
            s2 = P - 0.618 * diff
        else:
            # Classical Pivots
            r1 = 2.0 * P - L
            s1 = 2.0 * P - H
            r2 = P + (H - L)
            s2 = P - (H - L)

        s2 = round(s2, 1)
        s1 = round(s1, 1)
        r1 = round(r1, 1)
        r2 = round(r2, 1)

        # Invariant enforcement: S2 <= S1 <= R1 <= R2 guaranteed
        if s1 > r1:
            mid = (s1 + r1) / 2.0
            s1 = mid
            r1 = mid
        if s2 > s1:
            s2 = s1
        if r1 > r2:
            r2 = r1
        s2, s1, r1, r2 = sorted([s2, s1, r1, r2])

        return SupportResistance(s1=s1, s2=s2, r1=r1, r2=r2)

    @classmethod
    def generate_trade_setup(
        cls,
        current_price: float,
        pivots: SupportResistance,
        forecast_target: Optional[float] = None,
        atr_val: Optional[float] = None,
        min_rrr: float = 1.5,
    ) -> TradeSetup:
        """
        Generates actionable trade targets with strict RRR >= 1.5 guarantee.
        Constraints enforced:
        - entry_low <= entry_high
        - stop_loss < entry_low
        - take_profit_1 > entry_high
        - take_profit_2 >= take_profit_1
        - RRR = (take_profit_1 - entry_high) / (entry_low - stop_loss) >= min_rrr
        """
        curr = float(current_price)

        # 1. Entry zone brackets current price
        entry_low = round(curr * 0.99, 1)
        entry_high = round(curr * 1.01, 1)
        if entry_low > entry_high:
            entry_low = entry_high

        # 2. Stop loss placed below entry_low
        if atr_val is not None and atr_val > 0:
            sl_cand = entry_low - 1.5 * atr_val
        elif pivots.s1 < entry_low:
            sl_cand = pivots.s1
        else:
            sl_cand = entry_low * 0.965

        # Guaranteed positive risk denominator
        min_risk = max(curr * 0.02, 50.0)
        if (entry_low - sl_cand) < min_risk:
            stop_loss = round(entry_low - min_risk, 1)
        else:
            stop_loss = round(sl_cand, 1)

        risk_distance = entry_low - stop_loss
        if risk_distance <= 0:
            stop_loss = round(entry_low - min_risk, 1)
            risk_distance = entry_low - stop_loss

        # 3. Take Profit 1 with target RRR multiplier 1.8 >= min_rrr
        target_tp1 = entry_high + (1.8 * risk_distance)
        if forecast_target is not None and (forecast_target - entry_high) >= (min_rrr * risk_distance):
            target_tp1 = max(target_tp1, forecast_target)
        if pivots.r1 > entry_high and (pivots.r1 - entry_high) >= (min_rrr * risk_distance):
            target_tp1 = max(target_tp1, pivots.r1)

        take_profit_1 = round(target_tp1, 1)

        # 4. Take Profit 2
        target_tp2 = entry_high + (2.5 * risk_distance)
        if pivots.r2 > take_profit_1:
            target_tp2 = max(target_tp2, pivots.r2)
        take_profit_2 = round(max(take_profit_1, target_tp2), 1)

        # 5. RRR calculation and strict enforcement
        rrr = round((take_profit_1 - entry_high) / risk_distance, 2)
        if rrr < min_rrr:
            take_profit_1 = round(entry_high + (min_rrr * risk_distance), 1)
            rrr = min_rrr

        return TradeSetup(
            entry_zone=[entry_low, entry_high],
            stop_loss=stop_loss,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2,
            risk_reward_ratio=rrr,
        )

    @classmethod
    def forecast_trend(
        cls,
        candles: List[Union[OHLCVRecord, Dict[str, Any]]],
        horizons: List[int] = [7, 14, 30],
        symbol: str = "UNKNOWN",
        alpha: float = 0.30,
        beta: float = 0.10,
        phi: float = 0.90,
        pivot_window: int = 20,
        min_rrr: float = 1.5,
    ) -> PredictionSummary:
        """
        Executes Damped Holt exponential smoothing, volatility cones, pivots, and trade setup.
        """
        if not candles:
            raise ValueError("Candle list cannot be empty")

        opens, highs, lows, closes, volumes = _sort_and_extract_candles(candles)
        n = len(closes)
        current_price = closes[-1]
        atr_val = calculate_atr(highs, lows, closes, period=14)

        # 1. Damped Holt Initialization
        if n == 1:
            l_t = closes[0]
            b_t = 0.0
        else:
            l_t = closes[0]
            k_init = min(n, 5)
            b_t = (closes[k_init - 1] - closes[0]) / float(k_init - 1) if k_init > 1 else (closes[1] - closes[0])

            # Recurrence equations
            for t in range(1, n):
                y_t = closes[t]
                prev_l = l_t
                prev_b = b_t
                l_t = alpha * y_t + (1.0 - alpha) * (prev_l + phi * prev_b)
                b_t = beta * (l_t - prev_l) + (1.0 - beta) * phi * prev_b

        # 2. Multi-Horizon Forecasts & Volatility Cones
        forecast_points: List[ForecastPoint] = []
        sorted_horizons = sorted(horizons)

        for h in sorted_horizons:
            if abs(1.0 - phi) > 1e-9:
                phi_sum = phi * (1.0 - (phi ** h)) / (1.0 - phi)
            else:
                phi_sum = float(h)

            raw_target = l_t + (phi_sum * b_t)
            target = max(100.0, round(raw_target, 1))

            exp_return = round(((target - current_price) / current_price) * 100.0, 2) if current_price > 0 else 0.0

            sqrt_h = math.sqrt(h)
            delta_80 = 1.28 * atr_val * sqrt_h
            delta_95 = 1.96 * atr_val * sqrt_h

            u80 = round(target + delta_80, 1)
            l80 = round(max(0.0, target - delta_80), 1)
            u95 = round(target + delta_95, 1)
            l95 = round(max(0.0, target - delta_95), 1)

            # Invariant safeguards: lower_95 <= lower_80 <= target <= upper_80 <= upper_95
            if l80 < l95:
                l80 = l95
            if target < l80:
                l80 = target
            if target > u80:
                u80 = target
            if u80 > u95:
                u95 = u80

            forecast_points.append(
                ForecastPoint(
                    horizon_days=h,
                    target_price=target,
                    expected_return_pct=exp_return,
                    upper_80=u80,
                    lower_80=l80,
                    upper_95=u95,
                    lower_95=l95,
                )
            )

        # 3. Pivots
        pivots = cls.calculate_pivots(candles, window=pivot_window, method="classical")

        # 4. Trade Setup
        f14_target = next((f.target_price for f in forecast_points if f.horizon_days == 14), None)
        trade_setup = cls.generate_trade_setup(
            current_price=current_price,
            pivots=pivots,
            forecast_target=f14_target,
            atr_val=atr_val,
            min_rrr=min_rrr,
        )

        # 5. Signal & Confidence Scoring
        r14 = next((f.expected_return_pct for f in forecast_points if f.horizon_days == 14), 0.0)
        r30 = next((f.expected_return_pct for f in forecast_points if f.horizon_days == 30), 0.0)

        if r14 >= 5.0:
            signal = "STRONG_BUY"
        elif r14 >= 2.0:
            signal = "BUY"
        elif r14 >= -1.0 and r30 >= 3.0:
            signal = "ACCUMULATE"
        elif r14 > -2.0:
            signal = "NEUTRAL"
        elif r14 > -5.0:
            signal = "SELL"
        else:
            signal = "STRONG_SELL"

        sample_factor = min(1.0, n / 60.0)
        vol_ratio = (atr_val / current_price) if current_price > 0 else 0.03
        vol_penalty = max(0.0, (vol_ratio - 0.02) * 500.0)
        raw_conf = 80.0 * sample_factor - vol_penalty + (abs(r14) * 0.5)
        conf_score = round(max(10.0, min(95.0, raw_conf)), 1)

        return PredictionSummary(
            symbol=symbol,
            current_price=current_price,
            signal=signal,
            confidence_score=conf_score,
            forecasts=forecast_points,
            support_resistance=pivots,
            trade_setup=trade_setup,
        )


# Module-level convenience wrapper
forecast_trend = PredictionEngine.forecast_trend
