"""Adversarial resilience and stress test suite for Milestone 1 (M1_DATA).

Empirically challenges:
1. Cache Corruption Resilience:
   - Truncated JSON
   - Corrupt/invalid binary garbage
   - Empty 0-byte cache files
   - Malformed syntax JSON
   - Disk cache auto-recovery after corruption
2. Extreme Input Tests:
   - Empty symbol ("")
   - Unicode symbols ("VCB📊", "VNINDEX🇻🇳")
   - Whitespace padded ("  VCB  ") vs whitespace embedded ("VC B") vs all-whitespace ("   ")
   - Extreme history days (days=0, days=-10, days=1000)
3. Simulated Total Network Disconnection:
   - urllib.request.urlopen mocking URLError("Network unreachable")
   - 100% data access verification from seed snapshot for:
     * All 4 indices (VNINDEX, VN30INDEX, HNX-INDEX, UPCOM-INDEX)
     * All 20 curated stock quotes
     * All 20 stock foreign flow records & aggregate foreign flow
     * All 4 indices & 20 stocks OHLCV histories (90 days, chronological order)
     * Market breadth consistency
"""

import json
import shutil
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
import unittest
from unittest.mock import patch

from app.config import SUPPORTED_INDICES, STOCK_UNIVERSE
from app.data.models import MarketIndex, StockQuote, OHLCVRecord, ForeignTradeRecord
from app.data.provider import MarketDataProvider


class TestCacheCorruptionResilience(unittest.TestCase):
    """Stress tests resilience of 3-tier caching against disk corruption."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.cache_dir = Path(self.test_dir) / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.provider = MarketDataProvider(use_live=False, cache_dir=self.cache_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_corrupt_quote_truncated_json(self):
        """Disk cache contains truncated JSON bytes; provider must fall back gracefully."""
        corrupt_file = self.cache_dir / "quote_VCB.json"
        with open(corrupt_file, "w", encoding="utf-8") as f:
            f.write('{"symbol": "VCB", "price": 92000.0, "change":')

        quote = self.provider.get_quote("VCB")
        self.assertIsInstance(quote, StockQuote)
        self.assertEqual(quote.symbol, "VCB")
        self.assertGreater(quote.price, 0)

    def test_corrupt_indices_binary_garbage(self):
        """Disk cache contains binary null/FF garbage; indices provider must fall back gracefully."""
        corrupt_file = self.cache_dir / "market_indices.json"
        with open(corrupt_file, "wb") as f:
            f.write(b"\x00\xff\xfe\x00\x01\x02\x03\x04\xff\xff\xee")

        indices = self.provider.get_indices()
        self.assertIsInstance(indices, list)
        self.assertEqual(len(indices), 4)
        for idx in indices:
            self.assertIsInstance(idx, MarketIndex)
            self.assertGreater(idx.value, 0)

    def test_corrupt_history_empty_file(self):
        """Disk cache contains a 0-byte file; history provider must fall back gracefully."""
        corrupt_file = self.cache_dir / "history_VCB_90.json"
        corrupt_file.touch()

        candles = self.provider.get_history("VCB", days=90)
        self.assertIsInstance(candles, list)
        self.assertEqual(len(candles), 90)
        for c in candles:
            self.assertIsInstance(c, OHLCVRecord)

    def test_corrupt_foreign_flow_malformed_syntax(self):
        """Disk cache contains malformed JSON syntax; foreign flow provider must fall back gracefully."""
        corrupt_file = self.cache_dir / "foreign_VCB.json"
        with open(corrupt_file, "w", encoding="utf-8") as f:
            f.write('{"symbol": "VCB", "net_volume": 120000,, "net_value_vnd":}')

        record = self.provider.get_foreign_flow("VCB")
        self.assertIsInstance(record, ForeignTradeRecord)
        self.assertEqual(record.symbol, "VCB")
        self.assertGreater(record.room_left, 0)

    def test_corrupt_market_foreign_flow_truncated(self):
        """Disk cache contains truncated market foreign flow; aggregate provider must fall back."""
        corrupt_file = self.cache_dir / "market_foreign_flow.json"
        with open(corrupt_file, "w", encoding="utf-8") as f:
            f.write('[{"symbol": "VCB", "net_volume": 1000')

        records = self.provider.get_market_foreign_flow()
        self.assertIsInstance(records, list)
        self.assertEqual(len(records), len(STOCK_UNIVERSE))

    def test_cache_auto_recovery_and_rewrite(self):
        """After corrupted disk read and fallback, subsequent calls write clean valid cache."""
        corrupt_file = self.cache_dir / "quote_FPT.json"
        with open(corrupt_file, "w", encoding="utf-8") as f:
            f.write("INVALID_SYNTAX_CORRUPT")

        # 1st call: recovers from seed snapshot and overwrites cache
        q1 = self.provider.get_quote("FPT")
        self.assertEqual(q1.symbol, "FPT")

        # Verify disk file is now valid JSON
        with open(corrupt_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["symbol"], "FPT")

        # 2nd call: new provider with cold memory cache reads cleanly from disk cache
        new_provider = MarketDataProvider(use_live=False, cache_dir=self.cache_dir)
        q2 = new_provider.get_quote("FPT")
        self.assertEqual(q2.symbol, "FPT")
        self.assertEqual(q2.price, q1.price)


class TestExtremeInputHandling(unittest.TestCase):
    """Stress tests extreme inputs, malformed symbols, and boundary days values."""

    def setUp(self):
        self.provider = MarketDataProvider(use_live=False)

    def test_empty_symbol_rejected(self):
        """Empty string symbol must raise KeyError across all data methods."""
        with self.assertRaises(KeyError):
            self.provider.get_quote("")
        with self.assertRaises(KeyError):
            self.provider.get_history("", days=90)
        with self.assertRaises(KeyError):
            self.provider.get_foreign_flow("")

    def test_unicode_symbol_with_emojis_rejected(self):
        """Unicode characters and emojis must raise KeyError without crashing."""
        with self.assertRaises(KeyError):
            self.provider.get_quote("VCB📊")
        with self.assertRaises(KeyError):
            self.provider.get_history("VCB📊", days=90)
        with self.assertRaises(KeyError):
            self.provider.get_foreign_flow("VCB📊")
        with self.assertRaises(KeyError):
            self.provider.get_quote("VNINDEX🇻🇳")

    def test_whitespace_padded_symbols_handled(self):
        """Whitespace-padded symbols (e.g. '  VCB  ') should be trimmed and resolved correctly."""
        quote = self.provider.get_quote("  VCB  ")
        self.assertEqual(quote.symbol, "VCB")

        candles = self.provider.get_history("  VCB  ", days=30)
        self.assertEqual(len(candles), 30)

        foreign = self.provider.get_foreign_flow("  VCB  ")
        self.assertEqual(foreign.symbol, "VCB")

    def test_invalid_embedded_whitespace_and_blank_symbols_rejected(self):
        """Embedded spaces or whitespace-only symbols must raise KeyError."""
        with self.assertRaises(KeyError):
            self.provider.get_quote("VC B")
        with self.assertRaises(KeyError):
            self.provider.get_quote("   ")
        with self.assertRaises(KeyError):
            self.provider.get_history("   ", days=10)
        with self.assertRaises(KeyError):
            self.provider.get_history("\t\n", days=10)
        with self.assertRaises(KeyError):
            self.provider.get_foreign_flow("   ")

    def test_history_days_zero_and_negative(self):
        """days=0 and days < 0 must return an empty list [] immediately."""
        self.assertEqual(self.provider.get_history("VCB", days=0), [])
        self.assertEqual(self.provider.get_history("VCB", days=-1), [])
        self.assertEqual(self.provider.get_history("VCB", days=-10), [])
        self.assertEqual(self.provider.get_history("VNINDEX", days=0), [])
        self.assertEqual(self.provider.get_history("VNINDEX", days=-99), [])

    def test_history_days_extreme_large(self):
        """days=1000 should return all available historical candles up to available length without crashing."""
        candles = self.provider.get_history("VCB", days=1000)
        self.assertGreaterEqual(len(candles), 10)
        self.assertLessEqual(len(candles), 1000)
        # Verify chronological order
        for i in range(len(candles) - 1):
            self.assertLessEqual(candles[i].time, candles[i + 1].time)

        # Also for index
        idx_candles = self.provider.get_history("VNINDEX", days=1000)
        self.assertGreaterEqual(len(idx_candles), 10)
        for i in range(len(idx_candles) - 1):
            self.assertLessEqual(idx_candles[i].time, idx_candles[i + 1].time)

    def test_history_days_single_day(self):
        """days=1 should return exactly 1 candle."""
        candles = self.provider.get_history("VCB", days=1)
        self.assertEqual(len(candles), 1)
        self.assertIsInstance(candles[0], OHLCVRecord)


class TestSimulatedTotalNetworkDisconnection(unittest.TestCase):
    """
    Stress tests 100% offline fallback when network is completely severed.
    Simulated by patching urllib.request.urlopen to always raise URLError.
    """

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.cache_dir = Path(self.test_dir) / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # use_live=True forces provider to attempt CafeF/Yahoo first
        self.provider = MarketDataProvider(use_live=True, cache_dir=self.cache_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    @patch("urllib.request.urlopen")
    def test_all_four_indices_under_network_blackout(self, mock_urlopen):
        """All 4 indices must be fully retrievable from seed snapshot during network blackout."""
        mock_urlopen.side_effect = urllib.error.URLError("Network is unreachable (simulated blackout)")

        indices = self.provider.get_indices()
        self.assertEqual(len(indices), 4)

        symbols = [idx.symbol for idx in indices]
        for expected in ["VNINDEX", "VN30INDEX", "HNX-INDEX", "UPCOM-INDEX"]:
            self.assertIn(expected, symbols)

        for idx in indices:
            self.assertIsInstance(idx, MarketIndex)
            self.assertGreater(idx.value, 0)
            self.assertIn(idx.exchange, ["HOSE", "HNX", "UPCOM"])
            self.assertIn(idx.state, ["CEILING", "FLOOR", "UP", "DOWN", "REF"])
            self.assertGreaterEqual(len(idx.sparkline), 3)

    @patch("urllib.request.urlopen")
    def test_all_twenty_quotes_under_network_blackout(self, mock_urlopen):
        """All 20 universe quotes must be 100% retrievable from seed snapshot during network blackout."""
        mock_urlopen.side_effect = urllib.error.URLError("Network is unreachable (simulated blackout)")

        quotes = self.provider.get_all_quotes()
        self.assertEqual(len(quotes), 20)

        for q in quotes:
            self.assertIsInstance(q, StockQuote)
            self.assertIn(q.symbol, STOCK_UNIVERSE)
            self.assertGreater(q.price, 0)
            self.assertGreater(q.ref_price, 0)
            self.assertGreater(q.ceiling_price, q.floor_price)
            self.assertIn(q.state, ["CEILING", "FLOOR", "UP", "DOWN", "REF"])
            # Fundamental ratios populated from seed
            self.assertGreater(q.pe, 0)
            self.assertGreater(q.pb, 0)
            self.assertGreater(q.roe, 0)

    @patch("urllib.request.urlopen")
    def test_all_twenty_foreign_flows_under_network_blackout(self, mock_urlopen):
        """Foreign flow records for all 20 stocks must resolve from seed snapshot during blackout."""
        mock_urlopen.side_effect = urllib.error.URLError("Network is unreachable (simulated blackout)")

        records = self.provider.get_market_foreign_flow()
        self.assertEqual(len(records), 20)

        for r in records:
            self.assertIsInstance(r, ForeignTradeRecord)
            self.assertIn(r.symbol, STOCK_UNIVERSE)
            self.assertIsInstance(r.room_left, int)
            self.assertNotEqual(r.room_left, 0)
            self.assertIsInstance(r.net_value_vnd, float)

    @patch("urllib.request.urlopen")
    def test_all_histories_under_network_blackout(self, mock_urlopen):
        """All 4 indices and 20 stocks must return 90-day OHLCV history in chronological order."""
        mock_urlopen.side_effect = urllib.error.URLError("Network is unreachable (simulated blackout)")

        all_symbols = list(SUPPORTED_INDICES.keys()) + list(STOCK_UNIVERSE.keys())
        self.assertEqual(len(all_symbols), 24)

        for sym in all_symbols:
            candles = self.provider.get_history(sym, days=90)
            # HOSE stocks and VNINDEX/VN30 have 90 days; HNX and UPCOM have 89 days in seed snapshot
            expected_min = 89 if sym in ("HNX-INDEX", "UPCOM-INDEX") else 90
            self.assertEqual(len(candles), expected_min, f"History length mismatch for {sym}")
            # Verify chronological sort: oldest to newest
            for i in range(len(candles) - 1):
                self.assertLess(
                    candles[i].time,
                    candles[i + 1].time,
                    f"Non-chronological candles for {sym} at index {i}",
                )
                self.assertGreater(candles[i].open, 0)
                self.assertGreater(candles[i].high, 0)
                self.assertGreater(candles[i].low, 0)
                self.assertGreater(candles[i].close, 0)
                self.assertGreaterEqual(candles[i].volume, 0)

    @patch("urllib.request.urlopen")
    def test_market_breadth_under_network_blackout(self, mock_urlopen):
        """Market breadth must compute correctly and consistently during total blackout."""
        mock_urlopen.side_effect = urllib.error.URLError("Network is unreachable (simulated blackout)")

        breadth = self.provider.get_market_breadth()
        self.assertEqual(breadth["total"], 20)
        state_sum = (
            breadth["ceiling"]
            + breadth["up"]
            + breadth["ref"]
            + breadth["down"]
            + breadth["floor"]
        )
        self.assertEqual(state_sum, 20)
        # Verify dual casing support
        self.assertEqual(breadth["ceiling"], breadth["CEILING"])
        self.assertEqual(breadth["up"], breadth["UP"])


if __name__ == "__main__":
    unittest.main()
