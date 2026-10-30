"""Empirical challenger test suite for Milestone 1 (M1_DATA) Iteration 2.

Author: challenger_m1_it2_2
Purpose: Adversarially challenge and empirically verify across all 20 universe stocks:
1. Seed Snapshot Invariants:
   - Every quote in seed snapshot strictly satisfies floor <= price <= ceiling and abs(pct_change) <= limit_pct * 100.
2. Disk Cache Integrity & Sanitization Defense:
   - Clean disk cache read adheres strictly to bounds.
   - Adversarially poisoned disk cache (price > ceiling, price < floor, extreme pct_change, corporate action split divergence) is defensively sanitized by MarketDataProvider.
3. Memory Cache Integrity & Sanitization Defense:
   - Clean memory cache read adheres strictly to bounds.
   - Adversarially poisoned memory cache is defensively sanitized by MarketDataProvider.
4. Comprehensive 20-Stock Invariant Sweep across all 3 tiers (Memory, Disk, Seed).
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from app.config import STOCK_UNIVERSE, EXCHANGE_LIMITS, SEEDS_DIR
from app.data.models import StockQuote
from app.data.provider import MarketDataProvider
from app.data.cafef import _calculate_limits, _determine_state


class TestTwentyStocksCacheAndSnapshotIntegrity(unittest.TestCase):
    """Verifies all 20 universe stocks across Seed, Disk Cache, and Memory Cache."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.cache_dir = Path(self.test_dir) / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.provider = MarketDataProvider(use_live=False, cache_dir=self.cache_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_seed_snapshot_all_twenty_stocks_strict_bounds(self):
        """Every single quote in seed snapshot directly satisfies floor <= price <= ceiling and abs(pct_change) <= limit_pct * 100."""
        violations = []
        for symbol, meta in STOCK_UNIVERSE.items():
            quote = self.provider._get_seed_quote(symbol)
            exchange = meta.get("exchange", "HOSE")
            limit_pct = EXCHANGE_LIMITS.get(exchange, 0.07) * 100.0

            # Regulatory band check
            if not (quote.floor_price <= quote.price <= quote.ceiling_price):
                violations.append({
                    "symbol": symbol,
                    "tier": "seed",
                    "price": quote.price,
                    "floor": quote.floor_price,
                    "ceiling": quote.ceiling_price,
                    "error": "price outside [floor, ceiling]"
                })

            # Percentage change limit check
            if abs(quote.pct_change) > (limit_pct + 1e-4):
                violations.append({
                    "symbol": symbol,
                    "tier": "seed",
                    "pct_change": quote.pct_change,
                    "limit_pct": limit_pct,
                    "error": "pct_change exceeds exchange limit"
                })

            # Exact math consistency
            expected_change = round(quote.price - quote.ref_price, 0)
            self.assertEqual(quote.change, expected_change, f"Change mismatch for {symbol}")

            # 5-color state verification
            expected_state = _determine_state(quote.price, quote.ref_price, quote.ceiling_price, quote.floor_price)
            self.assertEqual(quote.state, expected_state, f"State mismatch for {symbol}")

        self.assertEqual(len(violations), 0, f"Seed snapshot violations: {violations}")

    def test_disk_cache_clean_and_retrieval_all_twenty_stocks(self):
        """Clean disk cache retrieval across all 20 universe stocks satisfies all invariants."""
        # Warm the disk cache
        for symbol in STOCK_UNIVERSE.keys():
            self.provider.get_quote(symbol)

        # Create fresh provider instance with cold memory cache to force reading from disk
        cold_provider = MarketDataProvider(use_live=False, cache_dir=self.cache_dir)
        self.assertEqual(len(cold_provider.memory_cache), 0)

        violations = []
        for symbol, meta in STOCK_UNIVERSE.items():
            quote = cold_provider.get_quote(symbol)
            exchange = meta.get("exchange", "HOSE")
            limit_pct = EXCHANGE_LIMITS.get(exchange, 0.07) * 100.0

            if not (quote.floor_price <= quote.price <= quote.ceiling_price):
                violations.append({
                    "symbol": symbol,
                    "tier": "disk_clean",
                    "price": quote.price,
                    "floor": quote.floor_price,
                    "ceiling": quote.ceiling_price,
                })

            if abs(quote.pct_change) > (limit_pct + 1e-4):
                violations.append({
                    "symbol": symbol,
                    "tier": "disk_clean",
                    "pct_change": quote.pct_change,
                    "limit_pct": limit_pct,
                })

        self.assertEqual(len(violations), 0, f"Clean disk cache violations: {violations}")

    def test_memory_cache_clean_retrieval_all_twenty_stocks(self):
        """Clean memory cache retrieval across all 20 universe stocks satisfies all invariants."""
        # Warm memory cache
        for symbol in STOCK_UNIVERSE.keys():
            self.provider.get_quote(symbol)

        self.assertGreaterEqual(len(self.provider.memory_cache), 20)

        # Corrupt disk files to prove we are reading directly from memory cache
        for f in self.cache_dir.glob("quote_*.json"):
            with open(f, "w", encoding="utf-8") as fp:
                fp.write("DISASTER_CORRUPT_NOT_JSON")

        violations = []
        for symbol, meta in STOCK_UNIVERSE.items():
            quote = self.provider.get_quote(symbol)
            exchange = meta.get("exchange", "HOSE")
            limit_pct = EXCHANGE_LIMITS.get(exchange, 0.07) * 100.0

            if not (quote.floor_price <= quote.price <= quote.ceiling_price):
                violations.append({
                    "symbol": symbol,
                    "tier": "memory_clean",
                    "price": quote.price,
                    "floor": quote.floor_price,
                    "ceiling": quote.ceiling_price,
                })

            if abs(quote.pct_change) > (limit_pct + 1e-4):
                violations.append({
                    "symbol": symbol,
                    "tier": "memory_clean",
                    "pct_change": quote.pct_change,
                    "limit_pct": limit_pct,
                })

        self.assertEqual(len(violations), 0, f"Clean memory cache violations: {violations}")

    def test_adversarially_poisoned_disk_cache_sanitization(self):
        """
        Adversarially poisons disk cache for universe stocks with:
        1. TCB historical split anomaly (price=22350, ref=33500, floor=31200, ceiling=35800, pct_change=-33.28%)
        2. FPT price blown way above ceiling (price=200000, ref=135000, ceiling=144400)
        3. HPG price breached below floor (price=15000, ref=26000, floor=24200)
        4. POW price blown above ceiling (price=25000, ref=11500, ceiling=12300)
        5. VCB inverted high/low & extreme pct_change (price=92000, ref=92000, pct_change=50.0%)
        Provider must sanitize on read and strictly enforce floor <= price <= ceiling and abs(pct_change) <= limit_pct * 100.
        """
        test_attacks = [
            # TCB split anomaly: price=22350, ref=33500, floor=31200, ceiling=35800, pct_change=-33.28%
            ("TCB", {
                "symbol": "TCB", "price": 22350.0, "ref_price": 33500.0,
                "ceiling_price": 35800.0, "floor_price": 31200.0,
                "change": -11150.0, "pct_change": -33.28, "high": 22800.0, "low": 22200.0,
                "volume": 1000000, "exchange": "HOSE", "company_name": "Techcombank",
                "sector": "Banking", "state": "FLOOR", "date": "2026-10-29"
            }),
            # FPT price blown way above ceiling: price=200000, ref=135000, ceiling=144400
            ("FPT", {
                "symbol": "FPT", "price": 200000.0, "ref_price": 135000.0,
                "ceiling_price": 144400.0, "floor_price": 125600.0,
                "change": 65000.0, "pct_change": 48.15, "high": 205000.0, "low": 135000.0,
                "volume": 2000000, "exchange": "HOSE", "company_name": "FPT Corp",
                "sector": "Technology", "state": "CEILING", "date": "2026-10-29"
            }),
            # HPG price breached below floor: price=15000, ref=26000, floor=24200
            ("HPG", {
                "symbol": "HPG", "price": 15000.0, "ref_price": 26000.0,
                "ceiling_price": 27800.0, "floor_price": 24200.0,
                "change": -11000.0, "pct_change": -42.31, "high": 26000.0, "low": 15000.0,
                "volume": 15000000, "exchange": "HOSE", "company_name": "Hoa Phat Group",
                "sector": "Materials", "state": "FLOOR", "date": "2026-10-29"
            }),
            # POW price blown above ceiling: price=25000, ref=11500, ceiling=12300
            ("POW", {
                "symbol": "POW", "price": 25000.0, "ref_price": 11500.0,
                "ceiling_price": 12300.0, "floor_price": 10700.0,
                "change": 13500.0, "pct_change": 117.39, "high": 25000.0, "low": 11500.0,
                "volume": 3000000, "exchange": "HOSE", "company_name": "PV Power",
                "sector": "Energy / Utilities", "state": "CEILING", "date": "2026-10-29"
            }),
            # VCB inverted high/low & extreme pct_change
            ("VCB", {
                "symbol": "VCB", "price": 92000.0, "ref_price": 92000.0,
                "ceiling_price": 98400.0, "floor_price": 85600.0,
                "change": 0.0, "pct_change": 50.0, "high": 80000.0, "low": 100000.0,
                "volume": 1000000, "exchange": "HOSE", "company_name": "Vietcombank",
                "sector": "Banking", "state": "REF", "date": "2026-10-29"
            }),
        ]

        for symbol, poisoned_data in test_attacks:
            disk_file = self.cache_dir / f"quote_{symbol}.json"
            with open(disk_file, "w", encoding="utf-8") as f:
                json.dump(poisoned_data, f)

            # Cold provider reads poisoned disk cache
            cold_provider = MarketDataProvider(use_live=False, cache_dir=self.cache_dir)
            sanitized_quote = cold_provider.get_quote(symbol)

            exchange = poisoned_data.get("exchange", "HOSE")
            limit_pct = EXCHANGE_LIMITS.get(exchange, 0.07) * 100.0

            # Must satisfy regulatory bounds!
            self.assertGreaterEqual(
                sanitized_quote.price,
                sanitized_quote.floor_price,
                f"Poisoned disk quote for {symbol} failed floor bound: {sanitized_quote.price} < {sanitized_quote.floor_price}"
            )
            self.assertLessEqual(
                sanitized_quote.price,
                sanitized_quote.ceiling_price,
                f"Poisoned disk quote for {symbol} failed ceiling bound: {sanitized_quote.price} > {sanitized_quote.ceiling_price}"
            )
            self.assertLessEqual(
                abs(sanitized_quote.pct_change),
                limit_pct + 1e-4,
                f"Poisoned disk quote for {symbol} failed pct_change limit: {sanitized_quote.pct_change} > {limit_pct}"
            )
            self.assertGreaterEqual(sanitized_quote.high, sanitized_quote.low)
            self.assertIn(sanitized_quote.state, ["CEILING", "FLOOR", "UP", "DOWN", "REF"])

    def test_all_twenty_stocks_simultaneously_poisoned_disk_cache(self):
        """Poison ALL 20 stocks on disk simultaneously: verify sanitization strictly guarantees floor <= price <= ceiling and abs(pct_change) <= limit_pct across all 20."""
        cold_provider = MarketDataProvider(use_live=False, cache_dir=self.cache_dir)
        
        # Test Case 1: Blown prices (+40% corporate action anomaly)
        for symbol, meta in STOCK_UNIVERSE.items():
            seed_q = cold_provider._get_seed_quote(symbol)
            blown_price = seed_q.ref_price * 1.40
            poisoned_dict = {
                "symbol": symbol,
                "price": blown_price,
                "ref_price": seed_q.ref_price,
                "ceiling_price": seed_q.ceiling_price,
                "floor_price": seed_q.floor_price,
                "change": blown_price - seed_q.ref_price,
                "pct_change": 40.0,
                "high": blown_price,
                "low": seed_q.ref_price,
                "volume": 1000000,
                "exchange": meta["exchange"],
                "company_name": meta["company_name"],
                "sector": meta["sector"],
                "state": "CEILING",
                "date": "2026-10-29",
            }
            disk_file = self.cache_dir / f"quote_{symbol}.json"
            with open(disk_file, "w", encoding="utf-8") as f:
                json.dump(poisoned_dict, f)

        # Clear memory and read all 20 back
        cold_provider.memory_cache.clear()
        quotes = cold_provider.get_all_quotes()
        self.assertEqual(len(quotes), 20)

        for q in quotes:
            limit_pct = 7.0  # All 20 are HOSE
            self.assertGreaterEqual(q.price, q.floor_price, f"{q.symbol} price below floor")
            self.assertLessEqual(q.price, q.ceiling_price, f"{q.symbol} price above ceiling")
            self.assertLessEqual(abs(q.pct_change), limit_pct + 1e-4, f"{q.symbol} pct_change exceeds limit")
            self.assertIn(q.state, ["CEILING", "FLOOR", "UP", "DOWN", "REF"])

        # Test Case 2: Regulatory ceiling clamp (+8.5% price breach, below 10.5% split threshold)
        for symbol, meta in STOCK_UNIVERSE.items():
            seed_q = cold_provider._get_seed_quote(symbol)
            clamped_price = round(seed_q.ref_price * 1.085, 0)
            poisoned_dict = {
                "symbol": symbol,
                "price": clamped_price,
                "ref_price": seed_q.ref_price,
                "ceiling_price": seed_q.ceiling_price,
                "floor_price": seed_q.floor_price,
                "change": clamped_price - seed_q.ref_price,
                "pct_change": 8.5,
                "high": clamped_price,
                "low": seed_q.ref_price,
                "volume": 1000000,
                "exchange": meta["exchange"],
                "company_name": meta["company_name"],
                "sector": meta["sector"],
                "state": "CEILING",
                "date": "2026-10-29",
            }
            disk_file = self.cache_dir / f"quote_{symbol}.json"
            with open(disk_file, "w", encoding="utf-8") as f:
                json.dump(poisoned_dict, f)

        cold_provider.memory_cache.clear()
        quotes2 = cold_provider.get_all_quotes()
        self.assertEqual(len(quotes2), 20)

        for q in quotes2:
            limit_pct = 7.0
            self.assertEqual(q.price, q.ceiling_price, f"{q.symbol} not clamped to ceiling")
            self.assertGreaterEqual(q.price, q.floor_price)
            self.assertLessEqual(abs(q.pct_change), limit_pct + 1e-4)
            self.assertEqual(q.state, "CEILING")

    def test_adversarially_poisoned_memory_cache_sanitization(self):
        """
        Adversarially poisons memory cache with out-of-band corrupted quotes.
        Provider must sanitize on read.
        """
        # Inject poisoned quote directly into memory cache
        poisoned_dict = {
            "symbol": "MBB", "price": 50000.0, "ref_price": 25000.0,
            "ceiling_price": 26750.0, "floor_price": 23250.0,
            "change": 25000.0, "pct_change": 100.0, "high": 50000.0, "low": 25000.0,
            "volume": 5000000, "exchange": "HOSE", "company_name": "MBBank",
            "sector": "Banking", "state": "CEILING", "date": "2026-10-29"
        }
        self.provider._set_memory("quote_MBB", poisoned_dict)

        quote = self.provider.get_quote("MBB")
        limit_pct = 7.0

        self.assertGreaterEqual(quote.price, quote.floor_price)
        self.assertLessEqual(quote.price, quote.ceiling_price)
        self.assertLessEqual(abs(quote.pct_change), limit_pct + 1e-4)


if __name__ == "__main__":
    unittest.main()
