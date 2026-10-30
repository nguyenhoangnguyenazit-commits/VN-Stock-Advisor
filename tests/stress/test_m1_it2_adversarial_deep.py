"""Adversarial Deep Probe for Milestone 1 Iteration 2 (M1_DATA).

Author: challenger_m1_it2_1 (Data Layer Challenger 1)
Purpose: Aggressively stress-test:
1. Exact regulatory price band invariants for all 20 universe stocks.
2. Exact mathematical consistency of TCB after ex-rights split adjustment.
3. Defense-in-depth sanitization under adversarial inputs (stock splits, surge spikes, corrupted caches).
4. Cache round-trip tamper defense.
"""

import json
import pytest
import unittest
from pathlib import Path

from app.config import STOCK_UNIVERSE, EXCHANGE_LIMITS, CACHE_DIR
from app.data.models import StockQuote
from app.data.cafef import _calculate_limits, _determine_state
from app.data.provider import MarketDataProvider


class TestMilestone1Iteration2DeepAdversarial(unittest.TestCase):
    """Deep adversarial test suite for M1 Iteration 2 data layer fixes."""

    def setUp(self):
        self.provider = MarketDataProvider(use_live=False)

    def test_all_twenty_stocks_individual_band_invariants(self):
        """Verifies strict regulatory invariants on all 20 stocks individually."""
        quotes = self.provider.get_all_quotes()
        self.assertEqual(len(quotes), 20, "Must return exactly 20 universe quotes")

        for q in quotes:
            exchange = q.exchange
            limit_pct = EXCHANGE_LIMITS[exchange]
            max_pct = limit_pct * 100.0

            # 1. Floor < Ref < Ceiling
            self.assertGreater(
                q.ceiling_price, q.ref_price,
                f"{q.symbol}: Ceiling {q.ceiling_price} must be > ref {q.ref_price}"
            )
            self.assertLess(
                q.floor_price, q.ref_price,
                f"{q.symbol}: Floor {q.floor_price} must be < ref {q.ref_price}"
            )
            self.assertGreater(
                q.ceiling_price, q.floor_price,
                f"{q.symbol}: Ceiling {q.ceiling_price} must be > floor {q.floor_price}"
            )

            # 2. Floor <= Price <= Ceiling
            self.assertLessEqual(
                q.price, q.ceiling_price,
                f"{q.symbol}: Price {q.price} exceeds ceiling {q.ceiling_price}"
            )
            self.assertGreaterEqual(
                q.price, q.floor_price,
                f"{q.symbol}: Price {q.price} below floor {q.floor_price}"
            )

            # 3. High / Low bounds
            self.assertLessEqual(
                q.high, q.ceiling_price,
                f"{q.symbol}: High {q.high} exceeds ceiling {q.ceiling_price}"
            )
            self.assertGreaterEqual(
                q.low, q.floor_price,
                f"{q.symbol}: Low {q.low} below floor {q.floor_price}"
            )
            self.assertGreaterEqual(
                q.high, q.low,
                f"{q.symbol}: High {q.high} must be >= low {q.low}"
            )
            self.assertGreaterEqual(
                q.high, q.price,
                f"{q.symbol}: High {q.high} must be >= price {q.price}"
            )
            self.assertLessEqual(
                q.low, q.price,
                f"{q.symbol}: Low {q.low} must be <= price {q.price}"
            )

            # 4. Pct Change limit
            self.assertLessEqual(
                abs(q.pct_change), max_pct + 0.01,
                f"{q.symbol}: pct_change {q.pct_change}% exceeds {max_pct}% limit for {exchange}"
            )

            # 5. Tick size alignment
            if q.ref_price >= 50000:
                tick = 100
            elif q.ref_price >= 10000:
                tick = 50
            else:
                tick = 10
            self.assertEqual(
                q.ceiling_price % tick, 0,
                f"{q.symbol}: Ceiling {q.ceiling_price} not divisible by tick {tick}"
            )
            self.assertEqual(
                q.floor_price % tick, 0,
                f"{q.symbol}: Floor {q.floor_price} not divisible by tick {tick}"
            )

            # 6. 5-Color state consistency
            expected_state = _determine_state(q.price, q.ref_price, q.ceiling_price, q.floor_price)
            self.assertEqual(
                q.state, expected_state,
                f"{q.symbol}: State {q.state} does not match expected {expected_state}"
            )

    def test_tcb_specific_mathematical_consistency(self):
        """Verifies exact post-split mathematical consistency for TCB."""
        quote = self.provider.get_quote("TCB")
        self.assertEqual(quote.symbol, "TCB")
        self.assertEqual(quote.exchange, "HOSE")
        self.assertEqual(quote.price, 22350.0)
        self.assertEqual(quote.ref_price, 22350.0)
        self.assertEqual(quote.change, 0.0)
        self.assertEqual(quote.pct_change, 0.0)
        self.assertEqual(quote.state, "REF")
        self.assertEqual(quote.ceiling_price, 23900.0)
        self.assertEqual(quote.floor_price, 20800.0)
        self.assertEqual(quote.high, 22800.0)
        self.assertEqual(quote.low, 22200.0)
        self.assertGreater(quote.volume, 0)
        self.assertEqual(quote.sector, "Banking")

    def test_sanitizer_catches_unadjusted_stock_splits(self):
        """Tests that _sanitize_quote defensively recovers from unadjusted splits."""
        # Case 1: 50% split drop (ref=50,000, price=25,000, reported change=-25,000)
        corrupted = StockQuote(
            symbol="VCB",
            company_name="Vietcombank",
            sector="Banking",
            exchange="HOSE",
            price=25000.0,
            change=-25000.0,
            pct_change=-50.0,
            high=25500.0,
            low=24500.0,
            volume=1000000,
            ref_price=50000.0,
            ceiling_price=53500.0,
            floor_price=46500.0,
            state="FLOOR",
            date="2026-10-29",
        )
        sanitized = self.provider._sanitize_quote(corrupted)
        self.assertEqual(sanitized.ref_price, 25000.0)
        self.assertEqual(sanitized.price, 25000.0)
        self.assertEqual(sanitized.pct_change, 0.0)
        self.assertEqual(sanitized.state, "REF")
        self.assertEqual(sanitized.ceiling_price, 26750.0)
        self.assertEqual(sanitized.floor_price, 23250.0)

    def test_sanitizer_clamps_out_of_band_prices(self):
        """Tests that prices outside ceiling/floor are clamped to statutory boundaries."""
        # Price above ceiling on HNX (10%)
        out_of_band_high = StockQuote(
            symbol="SHS",
            company_name="SHS Securities",
            sector="Financial Services",
            exchange="HNX",
            price=25000.0,  # Ref is 20000, ceil is 22000
            change=5000.0,
            pct_change=25.0,
            high=25000.0,
            low=20000.0,
            volume=500000,
            ref_price=20000.0,
            ceiling_price=22000.0,
            floor_price=18000.0,
            state="UP",
            date="2026-10-29",
        )
        sanitized = self.provider._sanitize_quote(out_of_band_high)
        # Should detect divergence > 15% on HNX and re-anchor or clamp
        self.assertLessEqual(sanitized.price, sanitized.ceiling_price)
        self.assertGreaterEqual(sanitized.price, sanitized.floor_price)
        self.assertLessEqual(abs(sanitized.pct_change), 10.01)

    def test_sanitizer_defends_against_tampered_cache_file(self):
        """Tests that if a disk cache file is tampered, get_quote sanitizes the output."""
        cache_path = CACHE_DIR / "quote_MBB.json"
        
        # Save tampered quote to disk cache
        tampered_data = {
            "symbol": "MBB",
            "company_name": "MB Bank",
            "sector": "Banking",
            "exchange": "HOSE",
            "price": 99999.0,  # Ridiculously high out of band
            "change": 80299.0,
            "pct_change": 407.6,
            "high": 99999.0,
            "low": 19550.0,
            "volume": 7234600,
            "ref_price": 19700.0,
            "ceiling_price": 21050.0,
            "floor_price": 18350.0,
            "state": "CEILING",
            "date": "2026-10-29",
            "pe": 5.9,
            "pb": 1.0,
            "roe": 22.1,
            "dividend_yield": 4.5,
            "foreign_net_value_vnd": 12073420000.0,
            "market_cap_vnd": 105000000000000.0
        }
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(tampered_data, f)

        # Clear memory cache to force disk cache read
        fresh_provider = MarketDataProvider(use_live=False)
        quote = fresh_provider.get_quote("MBB")

        # Invariant checks: Must NOT return 99999.0 with 407.6% pct_change!
        self.assertLessEqual(quote.price, quote.ceiling_price)
        self.assertGreaterEqual(quote.price, quote.floor_price)
        self.assertLessEqual(abs(quote.pct_change), 7.01)
        self.assertIn(quote.state, ["CEILING", "FLOOR", "UP", "DOWN", "REF"])

        # Clean up tampered cache
        if cache_path.exists():
            cache_path.unlink()


if __name__ == "__main__":
    unittest.main()
