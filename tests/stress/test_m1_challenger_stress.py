"""Empirical stress-testing harness for Milestone 1 (M1_DATA).

Author: challenger_m1_1 (Data Layer Challenger 1)
Purpose: Adversarially challenge and empirically verify:
1. Exchange limits and tick sizes for 100+ price points across HOSE (7%), HNX (10%), and UPCOM (15%)
   across all 3 tick tiers (<10k, 10k-50k, >=50k), verified against a high-precision Decimal oracle.
2. 5-state price determination (CEILING, FLOOR, UP, DOWN, REF) with strict boundary tolerances
   (exact ceiling, within 1 VND, just outside tolerance, exact floor, etc.).
3. Price ranges, raw VND scaling, and price band invariants for all 20 universe stocks and 4 indices.
"""

import math
import unittest
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING
from typing import List, Tuple

from app.config import SUPPORTED_INDICES, STOCK_UNIVERSE, EXCHANGE_LIMITS
from app.data.cafef import _calculate_limits, _determine_state
from app.data.provider import MarketDataProvider
from app.data.models import MarketIndex, StockQuote


class TestExchangeLimitsAndTickSizesStress(unittest.TestCase):
    """Stress tests exchange limits and tick sizes with 700+ combinations against a Decimal oracle."""

    def test_limits_against_decimal_oracle(self):
        """
        Tests 250+ price points across HOSE (7%), HNX (10%), UPCOM (15%)
        across all 3 tick tiers:
        - Tier 1 (< 10,000 VND): tick size 10 VND
        - Tier 2 (10,000 - 50,000 VND): tick size 50 VND
        - Tier 3 (>= 50,000 VND): tick size 100 VND
        """
        exchanges = [("HOSE", 0.07), ("HNX", 0.10), ("UPCOM", 0.15)]
        
        # Build comprehensive price points spanning all tiers and boundaries
        test_prices = []
        # Tier 1: 500 to 9,900 in steps of 100
        test_prices.extend([float(p) for p in range(500, 10000, 100)])
        test_prices.extend([500.0, 990.0, 1000.0, 4500.0, 7230.0, 9950.0, 9980.0, 9990.0])

        # Tier 2: 10,000 to 49,500 in steps of 500
        test_prices.extend([float(p) for p in range(10000, 50000, 500)])
        test_prices.extend([10000.0, 10050.0, 10100.0, 22350.0, 33500.0, 49900.0, 49950.0])

        # Tier 3: 50,000 to 200,000 in steps of 2,000
        test_prices.extend([float(p) for p in range(50000, 200000, 2000)])
        test_prices.extend([50000.0, 50100.0, 57500.0, 75000.0, 99900.0, 100000.0, 241000.0, 500000.0])

        test_prices = sorted(list(set(test_prices)))
        self.assertGreaterEqual(len(test_prices), 100, "Must test at least 100 price points")

        mismatches = []
        total_evaluations = 0

        for ex, pct in exchanges:
            for p in test_prices:
                total_evaluations += 1
                c, f = _calculate_limits(p, ex)

                # Determine tick size
                if p >= 50000:
                    tick = 100
                elif p >= 10000:
                    tick = 50
                else:
                    tick = 10

                # Strict Decimal Oracle
                p_dec = Decimal(str(p))
                pct_dec = Decimal(str(pct))
                tick_dec = Decimal(str(tick))

                raw_c = p_dec * (Decimal("1") + pct_dec)
                raw_f = p_dec * (Decimal("1") - pct_dec)

                oracle_c = float((raw_c / tick_dec).quantize(Decimal("1"), rounding=ROUND_FLOOR) * tick_dec)
                oracle_f = float((raw_f / tick_dec).quantize(Decimal("1"), rounding=ROUND_CEILING) * tick_dec)

                if c != oracle_c or f != oracle_f:
                    mismatches.append({
                        "exchange": ex,
                        "ref_price": p,
                        "tick": tick,
                        "actual_ceiling": c,
                        "oracle_ceiling": oracle_c,
                        "actual_floor": f,
                        "oracle_floor": oracle_f,
                    })

                # Assert exact tick divisibility
                self.assertEqual(c % tick, 0.0, f"Ceiling {c} not divisible by tick {tick} for ref {p}")
                self.assertEqual(f % tick, 0.0, f"Floor {f} not divisible by tick {tick} for ref {p}")

                # Assert regulatory caps: ceiling <= raw_ceiling, floor >= raw_floor
                self.assertLessEqual(c, float(raw_c) + 1e-6)
                self.assertGreaterEqual(f, float(raw_f) - 1e-6)

        self.assertGreaterEqual(total_evaluations, 300)
        self.assertEqual(len(mismatches), 0, f"Found {len(mismatches)} mismatches against Decimal oracle: {mismatches[:5]}")

    def test_tier_boundary_tick_transitions(self):
        """Verifies exact boundaries between tick tiers: 9,990 vs 10,000 and 49,950 vs 50,000."""
        # 9,990 VND is tier 1 (tick 10)
        c1, f1 = _calculate_limits(9990.0, "HOSE")
        self.assertEqual(c1 % 10, 0)
        self.assertEqual(f1 % 10, 0)

        # 10,000 VND is tier 2 (tick 50)
        c2, f2 = _calculate_limits(10000.0, "HOSE")
        self.assertEqual(c2 % 50, 0)
        self.assertEqual(f2 % 50, 0)
        self.assertEqual(c2, 10700.0)
        self.assertEqual(f2, 9300.0)

        # 49,950 VND is tier 2 (tick 50)
        c3, f3 = _calculate_limits(49950.0, "HOSE")
        self.assertEqual(c3 % 50, 0)
        self.assertEqual(f3 % 50, 0)

        # 50,000 VND is tier 3 (tick 100)
        c4, f4 = _calculate_limits(50000.0, "HOSE")
        self.assertEqual(c4 % 100, 0)
        self.assertEqual(f4 % 100, 0)
        self.assertEqual(c4, 53500.0)
        self.assertEqual(f4, 46500.0)


class TestFiveStatePriceDeterminationBoundaries(unittest.TestCase):
    """Stress tests Vietnamese 5-color state determination across strict price boundaries."""

    def test_five_state_boundaries(self):
        """
        Evaluates boundary conditions:
        - Exactly on ceiling -> CEILING
        - Within 1 VND of ceiling -> CEILING
        - Just outside ceiling tolerance (ceiling - 1.01) -> UP
        - Well above ref -> UP
        - Just above ref tolerance (ref + 1.01) -> UP
        - Boundary on ref (ref + 1.0, ref + 0.5, ref, ref - 0.5, ref - 1.0) -> REF
        - Just below ref tolerance (ref - 1.01) -> DOWN
        - Well below ref -> DOWN
        - Just above floor tolerance (floor + 1.01) -> DOWN
        - Within 1 VND of floor -> FLOOR
        - Exactly on floor -> FLOOR
        - Below floor -> FLOOR
        """
        test_cases = [
            ("HOSE", 50000.0),
            ("HOSE", 25000.0),
            ("HOSE", 8000.0),
            ("HNX", 50000.0),
            ("UPCOM", 50000.0),
        ]

        for ex, ref in test_cases:
            ceil, floor = _calculate_limits(ref, ex)
            checks = [
                (ceil, "CEILING", "exact ceiling"),
                (ceil - 0.5, "CEILING", "ceiling - 0.5 (within 1 VND)"),
                (ceil - 1.0, "CEILING", "ceiling - 1.0 (boundary)"),
                (ceil - 1.01, "UP", "ceiling - 1.01 (just below ceiling tolerance)"),
                (ref + 10.0, "UP", "well above ref"),
                (ref + 1.01, "UP", "ref + 1.01 (just above ref tolerance)"),
                (ref + 1.0, "REF", "ref + 1.0 (boundary)"),
                (ref + 0.5, "REF", "ref + 0.5 (within 1 VND of ref)"),
                (ref, "REF", "exact ref"),
                (ref - 0.5, "REF", "ref - 0.5 (within 1 VND of ref)"),
                (ref - 1.0, "REF", "ref - 1.0 (boundary)"),
                (ref - 1.01, "DOWN", "ref - 1.01 (just below ref tolerance)"),
                (ref - 10.0, "DOWN", "well below ref"),
                (floor + 1.01, "DOWN", "floor + 1.01 (just above floor tolerance)"),
                (floor + 1.0, "FLOOR", "floor + 1.0 (boundary)"),
                (floor + 0.5, "FLOOR", "floor + 0.5 (within 1 VND of floor)"),
                (floor, "FLOOR", "exact floor"),
                (floor - 0.5, "FLOOR", "floor - 0.5 (below floor)"),
            ]

            for price, expected_state, desc in checks:
                state = _determine_state(price, ref, ceil, floor)
                self.assertEqual(
                    state,
                    expected_state,
                    f"Failed {desc} on {ex} ref={ref}: price={price}, expected {expected_state}, got {state}"
                )


class TestUniverseQuotesAndIndicesPriceRanges(unittest.TestCase):
    """Verifies that all 20 stock quotes and 4 indices adhere to price ranges and raw VND scaling."""

    def setUp(self):
        self.provider = MarketDataProvider(use_live=False)

    def test_all_four_indices_adhere_to_point_ranges(self):
        """Verifies all 4 indices have reasonable point values, non-default distinct values, and valid state."""
        indices = self.provider.get_indices()
        self.assertEqual(len(indices), 4)
        
        idx_map = {idx.symbol: idx for idx in indices}
        for expected in ["VNINDEX", "VN30INDEX", "HNX-INDEX", "UPCOM-INDEX"]:
            self.assertIn(expected, idx_map)
            idx = idx_map[expected]
            self.assertIsInstance(idx, MarketIndex)
            # Must be in unscaled index points
            self.assertGreater(idx.value, 50.0, f"{expected} value too low: {idx.value}")
            self.assertLess(idx.value, 5000.0, f"{expected} value too high: {idx.value}")
            self.assertIn(idx.state, ["UP", "DOWN", "REF", "CEILING", "FLOOR"])
            self.assertGreaterEqual(len(idx.sparkline), 3)

        # Ensure all 4 indices do not collapse to identical default placeholder 1750.0
        distinct_values = set(idx.value for idx in indices)
        self.assertGreater(len(distinct_values), 1, "Indices must have distinct point values, not all defaulted to 1750.0")

    def test_all_twenty_stocks_raw_vnd_scaling(self):
        """Verifies all 20 universe stocks are quoted in raw VND (e.g. 10,000 - 500,000 VND), not thousands."""
        quotes = self.provider.get_all_quotes()
        self.assertEqual(len(quotes), 20)

        for q in quotes:
            self.assertIsInstance(q, StockQuote)
            self.assertIn(q.symbol, STOCK_UNIVERSE)
            # In Vietnam, equities trade between 1,000 VND and 500,000 VND
            self.assertGreaterEqual(q.price, 1000.0, f"{q.symbol}: Price {q.price} suggests unnormalized thousands")
            self.assertLessEqual(q.price, 500000.0, f"{q.symbol}: Price {q.price} unreasonably high")
            self.assertGreaterEqual(q.ref_price, 1000.0, f"{q.symbol}: Ref price {q.ref_price} suggests unnormalized thousands")

    def test_all_twenty_stocks_price_band_invariants(self):
        """
        Verifies Circular 120/2020/TT-BTC daily price band constraints for ALL 20 universe stocks:
        Floor <= Current Price <= Ceiling, and Floor < Ref < Ceiling.
        """
        quotes = self.provider.get_all_quotes()
        violations = []

        for q in quotes:
            # Check price band
            if not (q.floor_price <= q.price <= q.ceiling_price):
                violations.append({
                    "symbol": q.symbol,
                    "price": q.price,
                    "floor": q.floor_price,
                    "ceiling": q.ceiling_price,
                    "ref": q.ref_price,
                    "pct_change": q.pct_change,
                    "violation": "price out of regulatory band [floor, ceiling]"
                })

            # Check daily change limits
            limit_pct = EXCHANGE_LIMITS.get(q.exchange, 0.07) * 100
            if abs(q.pct_change) > (limit_pct + 0.5):
                violations.append({
                    "symbol": q.symbol,
                    "pct_change": q.pct_change,
                    "limit_pct": limit_pct,
                    "violation": f"daily pct_change exceeds exchange limit (+/-{limit_pct}%)"
                })

        self.assertEqual(
            len(violations),
            0,
            f"Regulatory price band violations detected in {len(violations)} stock(s): {violations}"
        )


if __name__ == "__main__":
    unittest.main()
