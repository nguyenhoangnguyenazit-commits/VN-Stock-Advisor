"""Enhanced unit test suite for Milestone 1 (M1_DATA).

Includes:
- Comprehensive tests covering all 4 indices, all 20 tickers,
  cache TTL expiration, corrupted disk cache recovery, live multi-source
  fallback chain, HNX/UPCOM exchange limits, and mock client parsing.
- Explicit verification of UPCOM ceiling rounding (+15%), MarketBreadth casing,
  aggregate market foreign flow, days <= 0 validation, and unknown ticker KeyError.
"""

import math
import shutil
import tempfile
import time
import unittest
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import (
    SUPPORTED_INDICES,
    STOCK_UNIVERSE,
    STANDARD_LOT_SIZE,
    EXCHANGE_LIMITS,
)
from app.data.models import (
    MarketIndex,
    StockQuote,
    OHLCVRecord,
    ForeignTradeRecord,
    MarketBreadth,
)
from app.data.cafef import (
    _calculate_limits,
    _determine_state,
    _parse_cafef_date,
    CafeFClient,
)
from app.data.yfinance import map_to_yahoo_symbol, YahooFinanceClient
from app.data.provider import MarketDataProvider


class TestDataModels(unittest.TestCase):
    """Verifies Pydantic schemas, validation, and JSON serialization."""

    def test_market_index_model(self):
        index = MarketIndex(
            symbol="VNINDEX",
            name="VN-Index",
            value=1755.61,
            change=-11.04,
            pct_change=-0.625,
            volume=549131300,
            value_vnd=12432870000000.0,
            date="2026-10-29",
            exchange="HOSE",
            sparkline=[1760.0, 1758.0, 1755.61],
            state="DOWN",
        )
        data = index.model_dump()
        self.assertEqual(data["symbol"], "VNINDEX")
        self.assertEqual(data["value"], 1755.61)
        self.assertEqual(data["state"], "DOWN")
        self.assertEqual(len(data["sparkline"]), 3)

        # Roundtrip JSON
        restored = MarketIndex.model_validate_json(index.model_dump_json())
        self.assertEqual(restored.symbol, index.symbol)
        self.assertEqual(restored.value, index.value)

    def test_stock_quote_model(self):
        quote = StockQuote(
            symbol="FPT",
            company_name="Công ty Cổ phần FPT",
            sector="Technology",
            exchange="HOSE",
            price=52700.0,
            change=-1300.0,
            pct_change=-2.41,
            high=54000.0,
            low=52500.0,
            volume=12591100,
            ref_price=54000.0,
            ceiling_price=57700.0,
            floor_price=50300.0,
            state="DOWN",
            date="2026-10-29",
            pe=18.5,
            pb=3.4,
            roe=26.8,
            dividend_yield=3.5,
        )
        self.assertEqual(quote.symbol, "FPT")
        self.assertEqual(quote.price, 52700.0)
        self.assertEqual(quote.state, "DOWN")
        self.assertGreater(quote.ref_price, 0)
        self.assertGreater(quote.ceiling_price, quote.ref_price)
        self.assertLess(quote.floor_price, quote.ref_price)

    def test_ohlcv_model(self):
        candle = OHLCVRecord(
            time="2026-10-29",
            open=54000.0,
            high=54500.0,
            low=52500.0,
            close=52700.0,
            volume=12591100,
        )
        self.assertEqual(candle.time, "2026-10-29")
        self.assertEqual(candle.close, 52700.0)

    def test_foreign_trade_model(self):
        foreign = ForeignTradeRecord(
            symbol="HPG",
            net_volume=2992600,
            net_value_vnd=63338420000.0,
            room_left=2305904571,
            foreign_ratio=21.69,
            date="2026-10-29",
        )
        self.assertEqual(foreign.symbol, "HPG")
        self.assertGreater(foreign.net_value_vnd, 0)
        self.assertEqual(foreign.foreign_ratio, 21.69)


class TestConfigAndRules(unittest.TestCase):
    """Verifies market configuration parameters, universes, and regulatory rules."""

    def test_supported_indices(self):
        self.assertIn("VNINDEX", SUPPORTED_INDICES)
        self.assertIn("VN30INDEX", SUPPORTED_INDICES)
        self.assertIn("HNX-INDEX", SUPPORTED_INDICES)
        self.assertIn("UPCOM-INDEX", SUPPORTED_INDICES)
        self.assertEqual(len(SUPPORTED_INDICES), 4)

    def test_stock_universe(self):
        self.assertEqual(len(STOCK_UNIVERSE), 20)
        sectors = set(s["sector"] for s in STOCK_UNIVERSE.values())
        self.assertIn("Banking", sectors)
        self.assertIn("Real Estate", sectors)
        self.assertIn("Technology", sectors)
        self.assertIn("Retail / Consumer", sectors)
        self.assertIn("Materials", sectors)
        self.assertIn("Securities", sectors)
        self.assertIn("Energy / Utilities", sectors)

        for sym, data in STOCK_UNIVERSE.items():
            self.assertEqual(data["lot_size"], STANDARD_LOT_SIZE)
            self.assertEqual(data["exchange"], "HOSE")

    def test_date_parser(self):
        self.assertEqual(_parse_cafef_date("29/10/2026"), "2026-10-29")
        self.assertEqual(_parse_cafef_date("05/01/2026"), "2026-01-05")
        self.assertEqual(_parse_cafef_date("2026-10-29"), "2026-10-29")
        self.assertEqual(_parse_cafef_date(""), "")
        # Trailing time tokens stripped
        self.assertEqual(_parse_cafef_date("29/10/2026 15:00:00"), "2026-10-29")
        self.assertEqual(_parse_cafef_date("2026-10-29 15:00:00"), "2026-10-29")

    def test_vietnamese_5_color_states_and_limits(self):
        ref_price = 50000.0
        ceil, floor = _calculate_limits(ref_price, "HOSE")
        self.assertEqual(ceil, 53500.0)  # +7%
        self.assertEqual(floor, 46500.0)  # -7%

        self.assertEqual(_determine_state(53500.0, ref_price, ceil, floor), "CEILING")
        self.assertEqual(_determine_state(46500.0, ref_price, ceil, floor), "FLOOR")
        self.assertEqual(_determine_state(51000.0, ref_price, ceil, floor), "UP")
        self.assertEqual(_determine_state(49000.0, ref_price, ceil, floor), "DOWN")
        self.assertEqual(_determine_state(50000.0, ref_price, ceil, floor), "REF")

    def test_hnx_and_upcom_limits(self):
        """Verifies price limits and tick sizes for HNX (+10%) and UPCOM (+15%)."""
        # HNX: +/- 10%
        c_hnx, f_hnx = _calculate_limits(50000.0, "HNX")
        self.assertEqual(c_hnx, 55000.0)
        self.assertEqual(f_hnx, 45000.0)

        # UPCOM: +/- 15% (precision bug fix check at 50,000 VND)
        c_upcom, f_upcom = _calculate_limits(50000.0, "UPCOM")
        self.assertEqual(c_upcom, 57500.0)
        self.assertEqual(f_upcom, 42500.0)

        # Tick sizes: < 10k (10 VND), 10k-50k (50 VND), >= 50k (100 VND)
        c_small, f_small = _calculate_limits(5000.0, "HOSE")
        self.assertEqual(c_small, 5350.0)
        self.assertEqual(f_small, 4650.0)

        c_mid, f_mid = _calculate_limits(25000.0, "HOSE")
        self.assertEqual(c_mid, 26750.0)
        self.assertEqual(f_mid, 23250.0)

    def test_yahoo_symbol_mapping(self):
        self.assertEqual(map_to_yahoo_symbol("VNINDEX"), "^VNINDEX.VN")
        self.assertEqual(map_to_yahoo_symbol("FPT"), "FPT.VN")
        self.assertEqual(map_to_yahoo_symbol("VCB.VN"), "VCB.VN")
        self.assertEqual(map_to_yahoo_symbol("^VNINDEX.VN"), "^VNINDEX.VN")


class TestDataProviderOffline(unittest.TestCase):
    """Verifies MarketDataProvider in offline seed-backed mode."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.cache_dir = Path(self.test_dir) / "cache"
        self.provider = MarketDataProvider(
            use_live=False,
            cache_dir=self.cache_dir,
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_get_indices(self):
        indices = self.provider.get_indices()
        self.assertEqual(len(indices), 4)
        symbols = [idx.symbol for idx in indices]
        self.assertIn("VNINDEX", symbols)
        self.assertIn("VN30INDEX", symbols)
        self.assertIn("HNX-INDEX", symbols)
        self.assertIn("UPCOM-INDEX", symbols)

        vnindex = next(idx for idx in indices if idx.symbol == "VNINDEX")
        self.assertGreater(vnindex.value, 1000.0)
        self.assertGreater(vnindex.volume, 0)
        self.assertIn(vnindex.state, ["UP", "DOWN", "REF"])
        self.assertTrue(len(vnindex.sparkline) > 0)

    def test_all_four_indices_attributes(self):
        """Verifies metadata, values, and sparklines across all 4 indices."""
        indices = self.provider.get_indices()
        lookup = {idx.symbol: idx for idx in indices}

        # Check VN30
        vn30 = lookup["VN30INDEX"]
        self.assertEqual(vn30.exchange, "HOSE")
        self.assertGreater(vn30.value, 1000.0)
        self.assertIn(vn30.state, ["UP", "DOWN", "REF"])
        self.assertTrue(len(vn30.sparkline) >= 5)

        # Check HNX
        hnx = lookup["HNX-INDEX"]
        self.assertEqual(hnx.exchange, "HNX")
        self.assertGreater(hnx.value, 100.0)
        self.assertIn(hnx.state, ["UP", "DOWN", "REF"])
        self.assertTrue(len(hnx.sparkline) >= 5)

        # Check UPCOM
        upcom = lookup["UPCOM-INDEX"]
        self.assertEqual(upcom.exchange, "UPCOM")
        self.assertGreater(upcom.value, 50.0)
        self.assertIn(upcom.state, ["UP", "DOWN", "REF"])
        self.assertTrue(len(upcom.sparkline) >= 5)

    def test_index_history_retrieval(self):
        """Verifies that index history returns raw index points without 1000x multiplication."""
        candles = self.provider.get_history("VNINDEX", days=30)
        self.assertEqual(len(candles), 30)
        self.assertGreater(candles[-1].close, 1000.0)
        self.assertLess(candles[-1].close, 3000.0)  # Indices are ~1700, NOT 1,700,000

    def test_get_quote(self):
        fpt = self.provider.get_quote("FPT")
        self.assertEqual(fpt.symbol, "FPT")
        self.assertEqual(fpt.exchange, "HOSE")
        self.assertEqual(fpt.sector, "Technology")
        self.assertGreater(fpt.price, 10000.0)
        self.assertGreater(fpt.ref_price, 10000.0)
        self.assertGreater(fpt.ceiling_price, fpt.ref_price)
        self.assertLess(fpt.floor_price, fpt.ref_price)
        self.assertIn(fpt.state, ["CEILING", "FLOOR", "UP", "DOWN", "REF"])
        self.assertGreater(fpt.pe, 0.0)
        self.assertGreater(fpt.roe, 0.0)

    def test_get_all_quotes(self):
        quotes = self.provider.get_all_quotes()
        self.assertEqual(len(quotes), 20)
        symbols = set(q.symbol for q in quotes)
        for sym in STOCK_UNIVERSE.keys():
            self.assertIn(sym, symbols)
            q = next(item for item in quotes if item.symbol == sym)
            self.assertGreater(q.price, 0.0)
            self.assertEqual(q.exchange, "HOSE")

    def test_all_20_stocks_comprehensive_metrics(self):
        """Ensures all 20 universe stocks have complete fundamental ratios and valid prices."""
        quotes = self.provider.get_all_quotes()
        for q in quotes:
            self.assertGreater(q.price, 10000.0, f"{q.symbol} price too low (unscaled)")
            self.assertGreater(q.ref_price, 10000.0)
            self.assertGreater(q.ceiling_price, q.ref_price)
            self.assertLess(q.floor_price, q.ref_price)
            self.assertGreater(q.pe, 0.0, f"{q.symbol} missing PE")
            self.assertGreater(q.roe, 0.0, f"{q.symbol} missing ROE")

    def test_all_20_stocks_history_and_foreign_trades(self):
        """Verifies history and foreign ownership across all 20 tickers, allowing signed room."""
        for sym in STOCK_UNIVERSE.keys():
            history = self.provider.get_history(sym, days=30)
            self.assertGreaterEqual(len(history), 10)
            flow = self.provider.get_foreign_flow(sym)
            self.assertEqual(flow.symbol, sym)
            self.assertIsInstance(flow.room_left, int)
            self.assertIsInstance(flow.net_value_vnd, float)

    def test_get_history_sorting_and_length(self):
        candles = self.provider.get_history("FPT", days=30)
        self.assertEqual(len(candles), 30)

        for i in range(len(candles) - 1):
            self.assertLessEqual(candles[i].time, candles[i + 1].time)
            self.assertGreater(candles[i].open, 0)
            self.assertGreater(candles[i].high, 0)
            self.assertGreater(candles[i].low, 0)
            self.assertGreater(candles[i].close, 0)
            self.assertGreaterEqual(candles[i].high, candles[i].low)

    def test_get_foreign_flow(self):
        flow = self.provider.get_foreign_flow("HPG")
        self.assertEqual(flow.symbol, "HPG")
        self.assertIsInstance(flow.net_volume, int)
        self.assertIsInstance(flow.net_value_vnd, float)
        self.assertGreater(flow.room_left, 0)

    def test_get_market_foreign_flow(self):
        """Verifies aggregate foreign flow for all 20 universe stocks."""
        flow_list = self.provider.get_market_foreign_flow()
        self.assertEqual(len(flow_list), 20)
        for flow in flow_list:
            self.assertIn(flow.symbol, STOCK_UNIVERSE)
            self.assertIsInstance(flow.room_left, int)
            self.assertIsInstance(flow.net_value_vnd, float)

    def test_market_breadth(self):
        breadth = self.provider.get_market_breadth()
        self.assertIn("CEILING", breadth)
        self.assertIn("UP", breadth)
        self.assertIn("REF", breadth)
        self.assertIn("DOWN", breadth)
        self.assertIn("FLOOR", breadth)
        self.assertEqual(breadth["total"], 20)

        state_sum = (
            breadth["CEILING"]
            + breadth["UP"]
            + breadth["REF"]
            + breadth["DOWN"]
            + breadth["FLOOR"]
        )
        self.assertEqual(state_sum, breadth["total"])

        # Also verify Pydantic MarketBreadth model compatibility
        mb = MarketBreadth(**breadth)
        self.assertEqual(mb.total, 20)
        mb_sum = mb.ceiling + mb.up + mb.ref + mb.down + mb.floor
        self.assertEqual(mb_sum, 20)

    def test_unknown_symbol_raises_key_error(self):
        """Verifies KeyError is raised for nonexistent symbols."""
        with self.assertRaises(KeyError):
            self.provider.get_quote("INVALID99")
        with self.assertRaises(KeyError):
            self.provider.get_history("INVALID99")
        with self.assertRaises(KeyError):
            self.provider.get_foreign_flow("INVALID99")

    def test_get_history_zero_or_negative_days(self):
        """Verifies days <= 0 validation in get_history."""
        self.assertEqual(self.provider.get_history("FPT", days=0), [])
        self.assertEqual(self.provider.get_history("FPT", days=-5), [])

    def test_caching_tiers(self):
        q1 = self.provider.get_quote("VCB")
        self.assertEqual(q1.symbol, "VCB")

        disk_file = self.cache_dir / "quote_VCB.json"
        self.assertTrue(disk_file.exists())

        q2 = self.provider.get_quote("VCB")
        self.assertEqual(q1.price, q2.price)

        self.provider.memory_cache.clear()
        self.assertEqual(len(self.provider.memory_cache), 0)
        q3 = self.provider.get_quote("VCB")
        self.assertEqual(q1.price, q3.price)
        self.assertIn("quote_VCB", self.provider.memory_cache)

    def test_cache_ttl_expiration(self):
        """Verifies that entries expire after designated TTL."""
        short_provider = MarketDataProvider(
            use_live=False,
            cache_dir=self.cache_dir,
            quote_ttl=1,
        )
        q = short_provider.get_quote("FPT")
        self.assertEqual(q.symbol, "FPT")
        self.assertIsNotNone(short_provider._get_from_memory("quote_FPT", ttl=1))

        # Advance beyond 1s TTL
        time.sleep(1.05)
        self.assertIsNone(short_provider._get_from_memory("quote_FPT", ttl=1))
        self.assertIsNone(short_provider._get_from_disk("quote_FPT", ttl=1))

    def test_corrupted_disk_cache_fallback(self):
        """Verifies graceful recovery when disk cache contains malformed JSON."""
        corrupt_file = self.cache_dir / "quote_SSI.json"
        corrupt_file.write_text("{malformed_json: true", encoding="utf-8")

        q = self.provider.get_quote("SSI")
        self.assertEqual(q.symbol, "SSI")
        self.assertGreater(q.price, 10000.0)

    def test_missing_seed_file_synthetic_fallback(self):
        """Verifies synthetic minimal record generation when seed file is entirely missing."""
        bogus_seed = Path(self.test_dir) / "non_existent_seed.json"
        empty_provider = MarketDataProvider(
            use_live=False,
            cache_dir=self.cache_dir,
            seed_path=bogus_seed,
        )
        indices = empty_provider.get_indices()
        self.assertEqual(len(indices), 4)
        quote = empty_provider.get_quote("FPT")
        self.assertEqual(quote.symbol, "FPT")
        self.assertEqual(quote.price, 30000.0)


class TestDataProviderLiveFallback(unittest.TestCase):
    """Verifies multi-tier live fallback chain using mocked API responses."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.cache_dir = Path(self.test_dir) / "cache"
        self.provider = MarketDataProvider(
            use_live=True,
            cache_dir=self.cache_dir,
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_fallback_cafef_failure_to_yahoo(self):
        """When CafeF fails, provider seamlessly falls back to Yahoo Finance."""
        self.provider.cafef.fetch_stock_quote = MagicMock(return_value=None)
        mock_yahoo_quote = StockQuote(
            symbol="TCB",
            company_name="Techcombank",
            sector="Banking",
            exchange="HOSE",
            price=24500.0,
            change=500.0,
            pct_change=2.08,
            high=24800.0,
            low=24000.0,
            volume=8000000,
            ref_price=24000.0,
            ceiling_price=25650.0,
            floor_price=22350.0,
            state="UP",
        )
        self.provider.yahoo.fetch_stock_quote = MagicMock(return_value=mock_yahoo_quote)

        quote = self.provider.get_quote("TCB")
        self.assertEqual(quote.symbol, "TCB")
        self.assertEqual(quote.price, 24500.0)
        self.provider.cafef.fetch_stock_quote.assert_called_once_with("TCB")
        self.provider.yahoo.fetch_stock_quote.assert_called_once_with("TCB")

    def test_fallback_dual_failure_to_seed(self):
        """When both CafeF and Yahoo Finance fail, provider falls back to Seed snapshot."""
        self.provider.cafef.fetch_stock_quote = MagicMock(return_value=None)
        self.provider.yahoo.fetch_stock_quote = MagicMock(return_value=None)

        quote = self.provider.get_quote("FPT")
        self.assertEqual(quote.symbol, "FPT")
        self.assertEqual(quote.price, 52700.0)


class TestClientParsersWithMocks(unittest.TestCase):
    """Verifies low-level response decoding and normalization logic in CafeF & Yahoo clients."""

    def test_cafef_stock_scaling_x1000(self):
        client = CafeFClient()
        mock_payload = {
            "Success": True,
            "Data": {
                "Data": [
                    {"Ngay": "29/10/2026", "GiaDongCua": 52.7, "GiaMoCua": 54.0, "GiaCaoNhat": 54.5, "GiaThapNhat": 52.5, "KhoiLuongKhopLenh": 12591100},
                    {"Ngay": "28/10/2026", "GiaDongCua": 54.0, "GiaMoCua": 53.5, "GiaCaoNhat": 54.5, "GiaThapNhat": 53.0, "KhoiLuongKhopLenh": 11000000},
                ]
            }
        }
        client.fetch_raw_price_history = MagicMock(return_value=mock_payload)

        quote = client.fetch_stock_quote("FPT")
        self.assertIsNotNone(quote)
        self.assertEqual(quote.price, 52700.0)
        self.assertEqual(quote.ref_price, 54000.0)
        self.assertEqual(quote.change, -1300.0)

        candles = client.fetch_ohlcv("FPT", target_count=2)
        self.assertEqual(len(candles), 2)
        self.assertEqual(candles[0].close, 54000.0)
        self.assertEqual(candles[1].close, 52700.0)

    def test_cafef_index_unscaled_points(self):
        client = CafeFClient()
        mock_payload = {
            "Success": True,
            "Data": {
                "Data": [
                    {"Ngay": "29/10/2026", "GiaDongCua": 1755.61, "GiaMoCua": 1760.0, "GiaCaoNhat": 1765.0, "GiaThapNhat": 1750.0, "KhoiLuongKhopLenh": 549131300},
                ]
            }
        }
        client.fetch_raw_price_history = MagicMock(return_value=mock_payload)

        candles = client.fetch_ohlcv("VNINDEX", target_count=1)
        self.assertEqual(len(candles), 1)
        self.assertEqual(candles[0].close, 1755.61)  # Index points unscaled

    def test_cafef_index_quote_extraction(self):
        """Verifies parsing index quote metrics from raw['Data']['Data'][0] avoiding root overwrite."""
        client = CafeFClient()
        mock_payload = {
            "Success": True,
            "Data": {
                "ClosePriceIndex": 1755.61,  # Root is VNINDEX!
                "ChgIndex": -11.04,
                "Data": [
                    {
                        "Symbol": "HNX-INDEX",
                        "Ngay": "29/10/2026",
                        "GiaDongCua": 256.61,
                        "GiaDieuChinh": 256.61,
                        "ThayDoi": "-3,25 (-1,25%)",
                        "KhoiLuongKhopLenh": 35889804,
                        "GiaTriKhopLenh": 597.09,
                    },
                    {
                        "Symbol": "HNX-INDEX",
                        "Ngay": "28/10/2026",
                        "GiaDongCua": 259.86,
                        "GiaDieuChinh": 259.86,
                    }
                ]
            }
        }
        client.fetch_raw_price_history = MagicMock(return_value=mock_payload)

        idx = client.fetch_index_quote("HNX-INDEX")
        self.assertIsNotNone(idx)
        self.assertEqual(idx.symbol, "HNX-INDEX")
        self.assertEqual(idx.value, 256.61)  # Correct HNX value, NOT 1755.61
        self.assertEqual(idx.change, -3.25)
        self.assertEqual(idx.pct_change, -1.25)
        self.assertEqual(idx.volume, 35889804)
        self.assertEqual(idx.value_vnd, 597090000000.0)
        self.assertEqual(idx.state, "DOWN")

    def test_yahoo_stock_chart_parsing(self):
        client = YahooFinanceClient()
        mock_chart = {
            "meta": {
                "regularMarketPrice": 52700.0,
                "chartPreviousClose": 54000.0,
                "regularMarketDayHigh": 54500.0,
                "regularMarketDayLow": 52500.0,
                "regularMarketVolume": 12591100,
                "regularMarketTime": 1793280000,
            },
            "timestamp": [1793193600, 1793280000],
            "indicators": {
                "quote": [{
                    "open": [53500.0, 54000.0],
                    "high": [54500.0, 54500.0],
                    "low": [53000.0, 52500.0],
                    "close": [54000.0, 52700.0],
                    "volume": [11000000, 12591100],
                }]
            }
        }
        client._get_chart = MagicMock(return_value=mock_chart)

        quote = client.fetch_stock_quote("FPT")
        self.assertIsNotNone(quote)
        self.assertEqual(quote.price, 52700.0)

        candles = client.fetch_ohlcv("FPT")
        self.assertEqual(len(candles), 2)
        self.assertEqual(candles[1].close, 52700.0)

    def test_yahoo_unsupported_indices_graceful(self):
        """Verifies YahooFinanceClient returns None gracefully for unsupported indices."""
        client = YahooFinanceClient()
        self.assertIsNone(client.fetch_index_quote("VN30INDEX"))
        self.assertIsNone(client.fetch_index_quote("HNX-INDEX"))
        self.assertIsNone(client.fetch_index_quote("UPCOM-INDEX"))
        self.assertIsNone(client.fetch_ohlcv("VN30INDEX"))


if __name__ == "__main__":
    unittest.main()
