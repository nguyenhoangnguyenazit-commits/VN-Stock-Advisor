"""Comprehensive unit test suite for Milestone 2 (M2_ANALYTICS).

Verifies:
- 7 Technical Indicators (SMA, EMA, RSI, MACD, BB, ATR, Vol SMA)
- Confluence Scoring & Trade Signals
- Damped Holt Exponential Smoothing & Monotonicity
- Monotonic Volatility Cone Expansion (80% & 95%)
- Support & Resistance Matrix Monotonicity (S2 <= S1 <= R1 <= R2)
- Trade Setup Invariant: Risk-Reward Ratio (RRR) >= 1.5 across all 20 universe stocks
- Defensive Edge-Case Handlers: 1-bar history, short series, flatlines, zero volume, price spikes
- Pydantic Model Validation and JSON serialization
"""

import importlib.util
import json
import math
import random
import unittest
from pathlib import Path

from app.config import STOCK_UNIVERSE
from app.data.models import OHLCVRecord
from app.analytics.models import (
    BollingerBands,
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
    calculate_indicators,
    evaluate_confluence,
    TechnicalEngine,
)
from app.analytics.prediction import (
    forecast_trend,
    PredictionEngine,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SEEDS_FILE = PROJECT_ROOT / "data" / "seeds" / "market_snapshot.json"


def make_candle(
    date_str: str,
    open_p: float,
    high_p: float,
    low_p: float,
    close_p: float,
    volume: int = 1000000
) -> OHLCVRecord:
    return OHLCVRecord(time=date_str, open=open_p, high=high_p, low=low_p, close=close_p, volume=volume)


class TestTechnicalIndicatorsSynthetic(unittest.TestCase):
    """Verifies indicator calculations on synthetic mathematical price series."""

    def test_flatline_series_indicators(self):
        """Test 1: 50 bars of constant price 50000 VND -> RSI 50.0, zero ATR, BB width 0."""
        candles = [make_candle(f"2026-06-{i+1:02d}", 50000.0, 50000.0, 50000.0, 50000.0, 1000000) for i in range(50)]
        ind = calculate_indicators(candles, symbol="FLAT")

        self.assertEqual(ind.current_price, 50000.0)
        self.assertEqual(ind.sma20, 50000.0)
        self.assertEqual(ind.sma50, 50000.0)
        self.assertEqual(ind.sma200, 50000.0)
        self.assertEqual(ind.ema12, 50000.0)
        self.assertEqual(ind.ema26, 50000.0)
        self.assertEqual(ind.rsi14, 50.0)
        self.assertEqual(ind.atr14, 0.0)
        self.assertEqual(ind.bollinger.upper, 50000.0)
        self.assertEqual(ind.bollinger.middle, 50000.0)
        self.assertEqual(ind.bollinger.lower, 50000.0)
        self.assertEqual(ind.bollinger.bandwidth, 0.0)
        self.assertEqual(ind.bollinger.pct_b, 0.5)
        self.assertEqual(ind.macd.line, 0.0)
        self.assertEqual(ind.macd.signal, 0.0)
        self.assertEqual(ind.macd.histogram, 0.0)
        self.assertEqual(ind.confluence_score, 0.0)
        self.assertEqual(ind.confluence_signal, "NEUTRAL")

    def test_linear_uptrend_series_indicators(self):
        """Test 2: Linear uptrend series -> RSI > 70, MACD positive, bullish confluence."""
        candles = [
            make_candle(
                f"2026-06-{i+1:02d}" if i < 28 else f"2026-07-{i-27:02d}",
                20000.0 + i * 500,
                20300.0 + i * 500,
                19800.0 + i * 500,
                20200.0 + i * 500,
                1500000,
            )
            for i in range(60)
        ]
        ind = calculate_indicators(candles, symbol="UPTREND")

        self.assertGreater(ind.rsi14, 70.0)
        self.assertGreater(ind.current_price, ind.ema12)
        self.assertGreater(ind.ema12, ind.ema26)
        self.assertGreater(ind.current_price, ind.sma20)
        self.assertGreater(ind.sma20, ind.sma50)
        self.assertGreater(ind.macd.line, 0.0)
        self.assertGreater(ind.confluence_score, 30.0)
        self.assertIn(ind.confluence_signal, ["BUY", "STRONG_BUY", "ACCUMULATE"])

    def test_linear_downtrend_series_indicators(self):
        """Test 3: Linear downtrend series -> RSI < 30, MACD negative, bearish confluence."""
        candles = [
            make_candle(
                f"2026-06-{i+1:02d}" if i < 28 else f"2026-07-{i-27:02d}",
                60000.0 - i * 500,
                60200.0 - i * 500,
                59600.0 - i * 500,
                59700.0 - i * 500,
                1200000,
            )
            for i in range(60)
        ]
        ind = calculate_indicators(candles, symbol="DOWNTREND")

        self.assertLess(ind.rsi14, 30.0)
        self.assertLess(ind.current_price, ind.ema12)
        self.assertLess(ind.ema12, ind.ema26)
        self.assertLess(ind.current_price, ind.sma20)
        self.assertLess(ind.sma20, ind.sma50)
        self.assertLess(ind.macd.line, 0.0)
        self.assertLess(ind.confluence_score, -30.0)
        self.assertIn(ind.confluence_signal, ["SELL", "STRONG_SELL"])

    def test_bollinger_bands_ordering_and_pct_b(self):
        """Test 4: Verify Upper >= Middle >= Lower and %B oscillator formula."""
        candles = [
            make_candle(
                f"2026-06-{i+1:02d}",
                30000.0 + math.sin(i / 3.0) * 2000.0,
                30500.0 + math.sin(i / 3.0) * 2000.0,
                29500.0 + math.sin(i / 3.0) * 2000.0,
                30100.0 + math.sin(i / 3.0) * 2000.0,
            )
            for i in range(30)
        ]
        ind = calculate_indicators(candles)
        bb = ind.bollinger

        self.assertGreaterEqual(bb.upper, bb.middle)
        self.assertGreaterEqual(bb.middle, bb.lower)
        self.assertGreater(bb.upper - bb.lower, 0.0)
        self.assertGreaterEqual(bb.bandwidth, 0.0)
        expected_pct_b = (ind.current_price - bb.lower) / (bb.upper - bb.lower)
        self.assertAlmostEqual(bb.pct_b, round(expected_pct_b, 2), places=1)

    def test_rsi_wilder_bounds_and_smoothing(self):
        """Test 5: Verify RSI-14 is strictly within [0.0, 100.0]."""
        candles = [
            make_candle(f"2026-06-{i+1:02d}", 30000.0 + (i % 2) * 500, 30600.0, 29800.0, 30000.0 + (i % 2) * 500)
            for i in range(40)
        ]
        ind = calculate_indicators(candles)
        self.assertGreaterEqual(ind.rsi14, 0.0)
        self.assertLessEqual(ind.rsi14, 100.0)

    def test_atr_wilder_volatility_measurement(self):
        """Test 6: Verify ATR-14 strictly positive and tracks true range."""
        candles = [
            make_candle(f"2026-06-{i+1:02d}", 50000.0, 51000.0, 49000.0, 50200.0)
            for i in range(25)
        ]
        ind = calculate_indicators(candles)
        self.assertGreater(ind.atr14, 0.0)
        # Expected TR is ~2000 VND
        self.assertAlmostEqual(ind.atr14, 2000.0, delta=200.0)


class TestPredictionEngineDampedHolt(unittest.TestCase):
    """Verifies Damped Holt Linear Smoothing, multi-horizon forecasts and volatility cones."""

    def test_damped_holt_uptrend_monotonicity(self):
        """Test 7: Target price monotonicity and positive expected returns on uptrend."""
        candles = [
            make_candle(
                f"2026-06-{i+1:02d}" if i < 28 else f"2026-07-{i-27:02d}",
                30000.0 + i * 200,
                30300.0 + i * 200,
                29800.0 + i * 200,
                30100.0 + i * 200
            )
            for i in range(50)
        ]
        pred = forecast_trend(candles, symbol="TEST_UP", horizons=[7, 14, 30])
        forecasts = {f.horizon_days: f for f in pred.forecasts}

        self.assertGreater(forecasts[14].target_price, forecasts[7].target_price)
        self.assertGreater(forecasts[30].target_price, forecasts[14].target_price)
        self.assertGreater(forecasts[30].expected_return_pct, forecasts[7].expected_return_pct)
        self.assertGreater(forecasts[7].expected_return_pct, 0.0)

    def test_damped_holt_downtrend_monotonicity(self):
        """Test 8: Target price monotonicity and negative expected returns on downtrend."""
        candles = [
            make_candle(
                f"2026-06-{i+1:02d}" if i < 28 else f"2026-07-{i-27:02d}",
                50000.0 - i * 200,
                50300.0 - i * 200,
                49700.0 - i * 200,
                49800.0 - i * 200
            )
            for i in range(50)
        ]
        pred = forecast_trend(candles, symbol="TEST_DOWN", horizons=[7, 14, 30])
        forecasts = {f.horizon_days: f for f in pred.forecasts}

        self.assertLess(forecasts[14].target_price, forecasts[7].target_price)
        self.assertLess(forecasts[30].target_price, forecasts[14].target_price)
        self.assertLess(forecasts[30].expected_return_pct, forecasts[7].expected_return_pct)
        self.assertLess(forecasts[7].expected_return_pct, 0.0)

    def test_damped_holt_damping_effect(self):
        """Test 9: Damped trend growth is strictly less than pure linear extrapolation."""
        candles = [
            make_candle(
                f"2026-06-{i+1:02d}" if i < 28 else f"2026-07-{i-27:02d}",
                30000.0 + i * 300,
                30400.0 + i * 300,
                29800.0 + i * 300,
                30200.0 + i * 300
            )
            for i in range(40)
        ]
        pred = forecast_trend(candles, symbol="TEST_DAMP", horizons=[7, 30])
        f7 = next(f for f in pred.forecasts if f.horizon_days == 7)
        f30 = next(f for f in pred.forecasts if f.horizon_days == 30)

        # Average daily trend increment between 0 and 7 days
        daily_rate_7 = (f7.target_price - pred.current_price) / 7.0
        self.assertLessEqual(f30.target_price, pred.current_price + 30.0 * daily_rate_7)

    def test_volatility_cones_interval_nesting(self):
        """Test 10: Strict interval nesting: lower_95 <= lower_80 <= target <= upper_80 <= upper_95."""
        candles = [
            make_candle(f"2026-06-{i+1:02d}", 30000.0 + (i % 3) * 200, 30500.0, 29500.0, 30100.0)
            for i in range(30)
        ]
        pred = forecast_trend(candles, horizons=[7, 14, 30])
        for f in pred.forecasts:
            self.assertLessEqual(f.lower_95, f.lower_80)
            self.assertLessEqual(f.lower_80, f.target_price)
            self.assertLessEqual(f.target_price, f.upper_80)
            self.assertLessEqual(f.upper_80, f.upper_95)

    def test_volatility_cones_monotonic_expansion(self):
        """Test 11: Cone width expands monotonically with horizon: width(30) >= width(14) >= width(7)."""
        candles = [
            make_candle(f"2026-06-{i+1:02d}", 30000.0 + (i % 3) * 200, 30500.0, 29500.0, 30100.0)
            for i in range(30)
        ]
        pred = forecast_trend(candles, horizons=[7, 14, 30])
        sorted_f = sorted(pred.forecasts, key=lambda x: x.horizon_days)

        prev_w80 = 0.0
        prev_w95 = 0.0
        for f in sorted_f:
            w80 = f.upper_80 - f.lower_80
            w95 = f.upper_95 - f.lower_95
            self.assertGreaterEqual(w95, w80)
            self.assertGreaterEqual(w80, prev_w80)
            self.assertGreaterEqual(w95, prev_w95)
            prev_w80 = w80
            prev_w95 = w95


class TestSupportResistanceAndTradeSetup(unittest.TestCase):
    """Verifies pivot matrix calculations and trade target generation."""

    def test_support_resistance_ordering(self):
        """Test 12: Verify S2 <= S1 <= R1 <= R2 pivot monotonicity."""
        candles = [
            make_candle(f"2026-06-{i+1:02d}", 40000.0 + (i % 5) * 400, 41500.0, 39000.0, 40200.0)
            for i in range(30)
        ]
        pred = forecast_trend(candles)
        sr = pred.support_resistance

        self.assertLessEqual(sr.s2, sr.s1)
        self.assertLessEqual(sr.s1, sr.r1)
        self.assertLessEqual(sr.r1, sr.r2)

    def test_trade_setup_entry_stop_tp_ordering(self):
        """Test 13: Verify entry zone, stop loss, and take profit ordering."""
        candles = [
            make_candle(f"2026-06-{i+1:02d}", 50000.0 + i * 100, 50500.0 + i * 100, 49500.0 + i * 100, 50100.0 + i * 100)
            for i in range(30)
        ]
        pred = forecast_trend(candles)
        setup = pred.trade_setup

        entry_low, entry_high = setup.entry_zone
        self.assertLessEqual(entry_low, entry_high)
        self.assertLess(setup.stop_loss, entry_low)
        self.assertGreater(setup.take_profit_1, entry_high)
        if setup.take_profit_2 > 0:
            self.assertGreaterEqual(setup.take_profit_2, setup.take_profit_1)

    def test_trade_setup_rrr_invariant(self):
        """Test 14: Risk-Reward Ratio (RRR) invariant: RRR >= 1.5."""
        candles = [
            make_candle(f"2026-06-{i+1:02d}", 30000.0, 30500.0, 29500.0, 30000.0)
            for i in range(30)
        ]
        pred = forecast_trend(candles)
        self.assertGreaterEqual(pred.trade_setup.risk_reward_ratio, 1.5)

    def test_trade_setup_rrr_across_all_20_stocks(self):
        """Test 15: Trade setup RRR >= 1.5 across all 20 universe stocks using market snapshot."""
        if not SEEDS_FILE.exists():
            self.skipTest("Market snapshot seed file not found")

        with open(SEEDS_FILE, "r", encoding="utf-8") as f:
            snapshot = json.load(f)

        for sym in STOCK_UNIVERSE.keys():
            self.assertIn(sym, snapshot["history"], f"Missing {sym} in seed snapshot history")
            raw_bars = snapshot["history"][sym]
            candles = [OHLCVRecord(**b) for b in raw_bars]

            pred = forecast_trend(candles, symbol=sym)
            setup = pred.trade_setup

            self.assertGreaterEqual(
                setup.risk_reward_ratio,
                1.5,
                f"{sym}: Trade setup RRR ({setup.risk_reward_ratio}) < 1.5"
            )
            entry_low, entry_high = setup.entry_zone
            self.assertLess(setup.stop_loss, entry_low)
            self.assertGreater(setup.take_profit_1, entry_high)

    def test_support_resistance_inverted_candles_adversarial_regression(self):
        """Test 15b: Adversarial regression - inverted candles (High < Low) strictly enforce S2 <= S1 <= R1 <= R2."""
        # Exact reproduction vector from challenger_m2_1 (High < Low)
        adversarial_candle = make_candle(
            "2026-01-01",
            open_p=36250.0,
            high_p=36232.3,
            low_p=36370.1,
            close_p=36288.1,
            volume=100,
        )

        # 1. Classical method
        piv_c = PredictionEngine.calculate_pivots([adversarial_candle], method="classical")
        self.assertLessEqual(
            piv_c.s2,
            piv_c.s1,
            f"Classical pivot violated S2 <= S1 under inverted candle: s2={piv_c.s2} > s1={piv_c.s1}",
        )
        self.assertLessEqual(piv_c.s1, piv_c.r1)
        self.assertLessEqual(piv_c.r1, piv_c.r2)

        # 2. Fibonacci method
        piv_f = PredictionEngine.calculate_pivots([adversarial_candle], method="fibonacci")
        self.assertLessEqual(
            piv_f.s2,
            piv_f.s1,
            f"Fibonacci pivot violated S2 <= S1 under inverted candle: s2={piv_f.s2} > s1={piv_f.s1}",
        )
        self.assertLessEqual(piv_f.s1, piv_f.r1)
        self.assertLessEqual(piv_f.r1, piv_f.r2)

        # 3. Full forecast_trend integration
        pred = forecast_trend([adversarial_candle])
        sr = pred.support_resistance
        self.assertLessEqual(sr.s2, sr.s1)
        self.assertLessEqual(sr.s1, sr.r1)
        self.assertLessEqual(sr.r1, sr.r2)
        self.assertLess(pred.trade_setup.stop_loss, pred.trade_setup.entry_zone[0])
        self.assertGreater(pred.trade_setup.take_profit_1, pred.trade_setup.entry_zone[1])
        self.assertGreaterEqual(pred.trade_setup.risk_reward_ratio, 1.5)

        # 4. Multi-bar inverted candle series
        multi_inverted = [
            make_candle(f"2026-01-{i+1:02d}", 36000.0, 35000.0 + i * 50, 37000.0 + i * 50, 36100.0)
            for i in range(15)
        ]
        piv_multi_c = PredictionEngine.calculate_pivots(multi_inverted, method="classical")
        self.assertLessEqual(piv_multi_c.s2, piv_multi_c.s1)
        self.assertLessEqual(piv_multi_c.s1, piv_multi_c.r1)
        self.assertLessEqual(piv_multi_c.r1, piv_multi_c.r2)

        piv_multi_f = PredictionEngine.calculate_pivots(multi_inverted, method="fibonacci")
        self.assertLessEqual(piv_multi_f.s2, piv_multi_f.s1)
        self.assertLessEqual(piv_multi_f.s1, piv_multi_f.r1)
        self.assertLessEqual(piv_multi_f.r1, piv_multi_f.r2)

    def test_support_resistance_extreme_noise_random_walk(self):
        """Test 15c: Support/resistance monotonicity under extreme noise, touching, and crossing candles."""
        # 1. Touching candles (High == Low) with varying Close positions
        touch_candles = [
            make_candle("2026-01-01", 50000.0, 50000.0, 50000.0, 50200.0),
            make_candle("2026-01-02", 50000.0, 50000.0, 50000.0, 49800.0),
            make_candle("2026-01-03", 50000.0, 50000.0, 50000.0, 50000.0),
        ]
        for c in touch_candles:
            for m in ["classical", "fibonacci"]:
                sr = PredictionEngine.calculate_pivots([c], method=m)
                self.assertLessEqual(sr.s2, sr.s1)
                self.assertLessEqual(sr.s1, sr.r1)
                self.assertLessEqual(sr.r1, sr.r2)

        # 2. Seeded random walk (500 candles) mixing inverted, touching, and high-noise regimes
        rng = random.Random(1337)
        noise_candles = []
        for i in range(500):
            p1 = rng.uniform(10000, 100000)
            p2 = rng.uniform(10000, 100000)
            regime = rng.random()
            if regime < 0.25:
                # Inverted (corrupted feed simulation)
                h, l = min(p1, p2), max(p1, p2)
            elif regime < 0.50:
                # Touching (zero range simulation)
                h, l = p1, p1
            else:
                # Normal high variance
                h, l = max(p1, p2), min(p1, p2)
            c = rng.uniform(min(h, l), max(h, l)) if h != l else h
            noise_candles.append(make_candle(f"2026-01-{i+1:04d}", (h + l) / 2.0, h, l, c, 10000))

        # Check across rolling windows
        for w in [5, 15, 30]:
            window_slice = noise_candles[-w:]
            for m in ["classical", "fibonacci"]:
                sr = PredictionEngine.calculate_pivots(window_slice, method=m)
                self.assertLessEqual(
                    sr.s2,
                    sr.s1,
                    f"Invariant broken at window={w}, method={m}: s2={sr.s2} > s1={sr.s1}",
                )
                self.assertLessEqual(sr.s1, sr.r1)
                self.assertLessEqual(sr.r1, sr.r2)

    def test_support_resistance_flatline_candles(self):
        """Test 15d: Flatline candles (High == Low == Close) across tiers collapse pivots and maintain invariants."""
        for price in [1000.0, 35000.0, 150000.0]:
            for length in [1, 20, 50]:
                candles = [
                    make_candle(f"2026-01-{i+1:02d}", price, price, price, price)
                    for i in range(length)
                ]
                for m in ["classical", "fibonacci"]:
                    sr = PredictionEngine.calculate_pivots(candles, method=m)
                    self.assertAlmostEqual(sr.s2, price, delta=0.1)
                    self.assertAlmostEqual(sr.s1, price, delta=0.1)
                    self.assertAlmostEqual(sr.r1, price, delta=0.1)
                    self.assertAlmostEqual(sr.r2, price, delta=0.1)
                    self.assertLessEqual(sr.s2, sr.s1)
                    self.assertLessEqual(sr.s1, sr.r1)
                    self.assertLessEqual(sr.r1, sr.r2)

            pred = forecast_trend(candles)
            self.assertLessEqual(pred.support_resistance.s2, pred.support_resistance.s1)
            self.assertLess(pred.trade_setup.stop_loss, pred.trade_setup.entry_zone[0])
            self.assertGreater(pred.trade_setup.take_profit_1, pred.trade_setup.entry_zone[1])
            self.assertGreaterEqual(pred.trade_setup.risk_reward_ratio, 1.5)

    def test_challenger_forecast_stress_harness_integration(self):
        """Test 15e: Challenger stress harness integration verifying 0 failures across all 9 suites."""
        harness_path = PROJECT_ROOT / ".agents" / "teamwork" / "challenger_m2_1" / "test_forecast_stress.py"
        if not harness_path.exists():
            self.skipTest("Challenger stress harness file not found on disk")

        import importlib.util
        spec = importlib.util.spec_from_file_location("test_forecast_stress", harness_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        report = mod.run_all_tests()

        failed_tests = [t["name"] for t in report["tests"] if t["status"] == "FAIL"]
        self.assertEqual(
            report["failed"],
            0,
            f"Challenger stress harness failed {report['failed']} test(s): {failed_tests}",
        )
        self.assertGreaterEqual(report["passed"], 8)


class TestAnalyticsEdgeCasesAndDefensiveness(unittest.TestCase):
    """Verifies robustness and defensive fallback behavior for unusual or boundary inputs."""

    def test_edge_case_single_candle(self):
        """Test 16: History with exactly 1 candle does not crash and returns sensible metrics."""
        candles = [make_candle("2026-06-01", 30000.0, 30500.0, 29800.0, 30200.0, 1000000)]
        ind = calculate_indicators(candles, symbol="SOLO")
        self.assertEqual(ind.sma20, 30200.0)
        self.assertEqual(ind.sma50, 30200.0)
        self.assertEqual(ind.sma200, 30200.0)
        self.assertEqual(ind.rsi14, 50.0)
        self.assertEqual(ind.bollinger.middle, 30200.0)
        self.assertGreaterEqual(ind.bollinger.upper, ind.bollinger.lower)

        pred = forecast_trend(candles, symbol="SOLO")
        self.assertGreaterEqual(pred.trade_setup.risk_reward_ratio, 1.5)

    def test_edge_case_short_history_15_bars(self):
        """Test 17: History with 15 bars (< 20, < 50, < 200) computes valid positive SMAs."""
        candles = [
            make_candle(f"2026-06-{i+1:02d}", 30000.0 + i * 50, 30200.0 + i * 50, 29900.0 + i * 50, 30100.0 + i * 50)
            for i in range(15)
        ]
        ind = calculate_indicators(candles)
        self.assertGreater(ind.sma20, 0.0)
        self.assertGreater(ind.sma50, 0.0)
        self.assertGreater(ind.sma200, 0.0)
        self.assertGreater(ind.atr14, 0.0)

    def test_edge_case_history_30_bars(self):
        """Test 18: History with 30 bars computes proper SMA20 and falls back for SMA50 and SMA200."""
        candles = [
            make_candle(f"2026-06-{i+1:02d}", 30000.0 + i * 50, 30200.0 + i * 50, 29900.0 + i * 50, 30100.0 + i * 50)
            for i in range(30)
        ]
        ind = calculate_indicators(candles)
        self.assertGreater(ind.sma20, 0.0)
        self.assertGreater(ind.sma50, 0.0)
        self.assertGreater(ind.sma200, 0.0)

    def test_edge_case_zero_volume_bars(self):
        """Test 19: All bars with zero volume avoids ZeroDivisionError."""
        candles = [
            make_candle(f"2026-06-{i+1:02d}", 30000.0, 30500.0, 29500.0, 30000.0, volume=0)
            for i in range(25)
        ]
        ind = calculate_indicators(candles)
        self.assertEqual(ind.volume_sma20, 0.0)
        self.assertEqual(ind.volume_surge_factor, 1.0)

    def test_edge_case_extreme_price_spike(self):
        """Test 20: Sudden 100% price spike does not produce NaN or math domain errors."""
        candles = [
            make_candle(f"2026-06-{i+1:02d}", 30000.0, 30500.0, 29500.0, 30000.0)
            for i in range(20)
        ]
        # Append massive gap
        candles.append(make_candle("2026-06-21", 60000.0, 65000.0, 59000.0, 62000.0))
        ind = calculate_indicators(candles)
        self.assertFalse(math.isnan(ind.bollinger.upper))
        self.assertFalse(math.isnan(ind.rsi14))
        self.assertFalse(math.isnan(ind.confluence_score))

    def test_edge_case_empty_candles_raises_value_error(self):
        """Test 21: Empty candle list raises ValueError."""
        with self.assertRaises(ValueError):
            calculate_indicators([])
        with self.assertRaises(ValueError):
            forecast_trend([])

    def test_edge_case_non_chronological_candles_sorted(self):
        """Test 22: Non-chronological (shuffled) candles are sorted ascending automatically."""
        c1 = make_candle("2026-06-01", 30000.0, 30500.0, 29500.0, 30000.0)
        c2 = make_candle("2026-06-02", 31000.0, 31500.0, 30500.0, 31000.0)
        c3 = make_candle("2026-06-03", 32000.0, 32500.0, 31500.0, 32000.0)

        # Feed in reverse order
        ind = calculate_indicators([c3, c2, c1])
        # Current price must be the latest chronological close (c3 close = 32000.0)
        self.assertEqual(ind.current_price, 32000.0)


class TestAnalyticsPydanticSchemas(unittest.TestCase):
    """Verifies schema validation, serialization, and alias interoperability."""

    def test_indicator_summary_pydantic_roundtrip(self):
        """Test 23: IndicatorSummary serialization and deserialization roundtrip."""
        data = {
            "symbol": "FPT",
            "current_price": 135200.0,
            "sma20": 132000.0,
            "sma50": 128000.0,
            "sma200": 115000.0,
            "ema12": 134000.0,
            "ema26": 131000.0,
            "rsi14": 62.5,
            "macd": {"line": 1500.0, "signal": 1200.0, "histogram": 300.0},
            "bollinger": {"upper": 138000.0, "middle": 132000.0, "lower": 126000.0, "bandwidth": 0.09, "pct_b": 0.77},
            "atr14": 2800.0,
            "volume_sma20": 4500000.0,
            "volume_surge_factor": 1.25,
            "confluence_score": 65.0,
            "confluence_signal": "BUY",
        }
        summary = IndicatorSummary.model_validate(data)
        self.assertEqual(summary.symbol, "FPT")
        self.assertEqual(summary.macd.line, 1500.0)

        json_str = summary.model_dump_json()
        restored = IndicatorSummary.model_validate_json(json_str)
        self.assertEqual(restored.confluence_score, 65.0)

    def test_prediction_summary_pydantic_roundtrip(self):
        """Test 24: PredictionSummary and ForecastReport alias interoperability."""
        data = {
            "symbol": "HPG",
            "current_price": 28500.0,
            "signal": "ACCUMULATE",
            "confidence_score": 75.0,
            "forecasts": [
                {
                    "horizon_days": 7,
                    "target_price": 29500.0,
                    "expected_return_pct": 3.51,
                    "upper_80": 30200.0,
                    "lower_80": 28800.0,
                    "upper_95": 30800.0,
                    "lower_95": 28200.0,
                }
            ],
            "support_resistance": {"s2": 26500.0, "s1": 27500.0, "r1": 29500.0, "r2": 30500.0},
            "trade_setup": {
                "entry_zone": [28200.0, 28700.0],
                "stop_loss": 27200.0,
                "take_profit_1": 30500.0,
                "take_profit_2": 31500.0,
                "risk_reward_ratio": 1.8,
            },
        }
        pred = PredictionSummary.model_validate(data)
        self.assertEqual(pred.symbol, "HPG")
        self.assertEqual(pred.trade_setup.risk_reward_ratio, 1.8)

        report = ForecastReport.model_validate(data)
        self.assertEqual(report.trade_setup.stop_loss, 27200.0)

    def test_confluence_result_pydantic_validation(self):
        """Test 25: ConfluenceResult bounds, signals, and component scores."""
        conf = ConfluenceResult(
            score=45.0,
            signal="BUY",
            confidence=80.0,
            components={"rsi": 15.0, "macd": 20.0, "ma": 10.0},
        )
        self.assertEqual(conf.signal, "BUY")
        self.assertEqual(conf.score, 45.0)
        self.assertIn("macd", conf.components)


if __name__ == "__main__":
    unittest.main()
