"""Unified MarketDataProvider providing 3-tier retrieval with CafeF, Yahoo Finance, and offline seed."""

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from app.config import (
    SUPPORTED_INDICES,
    STOCK_UNIVERSE,
    EXCHANGE_LIMITS,
    CACHE_DIR,
    SEEDS_DIR,
    QUOTE_CACHE_TTL,
    HISTORY_CACHE_TTL,
    INDEX_CACHE_TTL,
    FOREIGN_CACHE_TTL,
)
from app.data.models import (
    MarketIndex,
    StockQuote,
    OHLCVRecord,
    ForeignTradeRecord,
    MarketBreadth,
)
from app.data.cafef import CafeFClient, _calculate_limits, _determine_state
from app.data.yfinance import YahooFinanceClient

logger = logging.getLogger(__name__)


class MarketDataProvider:
    """
    Unified market data service for Vietnamese equities and indices.
    Implements a resilient 3-tier retrieval architecture:
    1. Tier 1: In-Memory TTL Cache (< 1ms)
    2. Tier 2: Persistent Local JSON Disk Cache (< 5ms)
    3. Tier 3: Live Fetch (CafeF primary -> Yahoo Finance fallback) -> Offline Seed Snapshot guarantee
    """

    def __init__(
        self,
        use_live: bool = True,
        cache_dir: Optional[Path] = None,
        seed_path: Optional[Path] = None,
        quote_ttl: int = QUOTE_CACHE_TTL,
        history_ttl: int = HISTORY_CACHE_TTL,
        index_ttl: int = INDEX_CACHE_TTL,
        foreign_ttl: int = FOREIGN_CACHE_TTL,
    ):
        self.use_live = use_live
        self.cache_dir = cache_dir or CACHE_DIR
        self.seed_path = seed_path or (SEEDS_DIR / "market_snapshot.json")
        self.quote_ttl = quote_ttl
        self.history_ttl = history_ttl
        self.index_ttl = index_ttl
        self.foreign_ttl = foreign_ttl

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.memory_cache: Dict[str, Tuple[float, Any]] = {}

        self.cafef = CafeFClient()
        self.yahoo = YahooFinanceClient()
        self._seed_data: Optional[Dict[str, Any]] = None

    # -------------------------------------------------------------------------
    # Tier 1 & 2: Cache Management Helpers
    # -------------------------------------------------------------------------

    def _get_from_memory(self, key: str, ttl: int) -> Optional[Any]:
        if key in self.memory_cache:
            ts, val = self.memory_cache[key]
            if (time.time() - ts) < ttl:
                return val
        return None

    def _set_memory(self, key: str, value: Any) -> None:
        self.memory_cache[key] = (time.time(), value)

    def _get_disk_cache_path(self, key: str) -> Path:
        sanitized = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in key)
        return self.cache_dir / f"{sanitized}.json"

    def _get_from_disk(self, key: str, ttl: int) -> Optional[Any]:
        path = self._get_disk_cache_path(key)
        if not path.exists():
            return None
        try:
            mtime = path.stat().st_mtime
            if (time.time() - mtime) > ttl:
                return None
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Propagate back to memory cache
            self._set_memory(key, data)
            return data
        except Exception as e:
            logger.warning(f"Failed reading disk cache for {key}: {e}")
            return None

    def _write_to_disk(self, key: str, data: Any) -> None:
        path = self._get_disk_cache_path(key)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed writing disk cache for {key}: {e}")

    # -------------------------------------------------------------------------
    # Tier 3: Seed Snapshot Fallback Loader
    # -------------------------------------------------------------------------

    def _load_seed(self) -> Dict[str, Any]:
        """Loads and caches the offline market snapshot."""
        if self._seed_data is not None:
            return self._seed_data

        if self.seed_path.exists():
            try:
                with open(self.seed_path, "r", encoding="utf-8") as f:
                    self._seed_data = json.load(f)
                    return self._seed_data
            except Exception as e:
                logger.error(f"Error loading seed snapshot {self.seed_path}: {e}")

        # Fallback empty snapshot structure if seed file is missing
        self._seed_data = {
            "indices": {},
            "quotes": {},
            "history": {},
            "foreign_trades": {},
        }
        return self._seed_data

    def _get_seed_index(self, symbol: str) -> MarketIndex:
        clean = symbol.strip().upper()
        seed = self._load_seed()
        raw = seed.get("indices", {}).get(clean)
        meta = SUPPORTED_INDICES.get(clean, {"name": clean, "exchange": "HOSE"})
        if raw:
            return MarketIndex(**raw)
        return MarketIndex(
            symbol=clean,
            name=meta["name"],
            value=1750.0,
            change=0.0,
            pct_change=0.0,
            volume=500_000_000,
            value_vnd=12_000_000_000_000.0,
            date="2026-10-29",
            exchange=meta["exchange"],
            sparkline=[1740.0, 1745.0, 1750.0],
            state="REF",
        )

    def _sanitize_quote(self, quote: StockQuote) -> StockQuote:
        """
        Defensively sanitizes a StockQuote against corporate actions, unadjusted splits,
        and pricing anomalies to strictly enforce Vietnamese market regulatory invariants:
        1. floor_price <= price <= ceiling_price
        2. abs(pct_change) <= limit_pct * 100
        3. state matches _determine_state(price, ref_price, ceiling_price, floor_price)
        """
        exchange = (quote.exchange or "HOSE").upper()
        limit_pct = EXCHANGE_LIMITS.get(exchange, 0.07)
        max_pct = limit_pct * 100.0
        split_threshold = limit_pct * 1.5  # 10.5% on HOSE, 15% on HNX, 22.5% on UPCOM

        price = float(quote.price)
        ref_price = float(quote.ref_price)
        change = float(quote.change)
        pct_change = float(quote.pct_change)
        high = float(quote.high)
        low = float(quote.low)

        # 1. Ensure positive nominal price & ref_price
        if price <= 0.0:
            price = ref_price if ref_price > 0.0 else 10000.0
        if ref_price <= 0.0:
            ref_price = price

        expected_ceiling, expected_floor = _calculate_limits(ref_price, exchange)

        # 2. Detect corporate action / unadjusted split
        rel_divergence = abs(price - ref_price) / ref_price if ref_price > 0 else 0.0

        if rel_divergence > split_threshold or abs(pct_change) > (split_threshold * 100.0):
            # Check if reported change yields a valid candidate reference price
            candidate_ref = round(price - change, 0)
            c_ceil, c_floor = _calculate_limits(candidate_ref, exchange) if candidate_ref > 0 else (0, 0)
            if (
                candidate_ref > 0
                and (c_floor <= price <= c_ceil)
                and (abs(price - candidate_ref) / candidate_ref <= limit_pct + 0.005)
            ):
                ref_price = candidate_ref
                expected_ceiling, expected_floor = c_ceil, c_floor
            else:
                # Re-anchor reference price to current matching execution price
                ref_price = price
                change = 0.0
                pct_change = 0.0
                expected_ceiling, expected_floor = _calculate_limits(ref_price, exchange)

        # 3. Strictly enforce statutory band [expected_floor, expected_ceiling]
        if price > expected_ceiling:
            price = expected_ceiling
        elif price < expected_floor:
            price = expected_floor

        # 4. Enforce exact change & percentage change consistency
        change = round(price - ref_price, 0)
        pct_change = round((change / ref_price * 100.0), 2) if ref_price > 0 else 0.0

        # Safety clamp on pct_change if float rounding slightly exceeds max_pct
        if pct_change > max_pct:
            pct_change = round(max_pct, 2)
        elif pct_change < -max_pct:
            pct_change = round(-max_pct, 2)

        # 5. Enforce high/low consistency
        if high <= 0.0 or high < price:
            high = price
        if low <= 0.0 or low > price:
            low = price
        if high > expected_ceiling:
            high = expected_ceiling
        if low < expected_floor:
            low = expected_floor
        if high < low:
            high, low = max(high, low), min(high, low)

        # 6. Recompute 5-color state
        state = _determine_state(price, ref_price, expected_ceiling, expected_floor)

        return quote.model_copy(update={
            "price": price,
            "ref_price": ref_price,
            "ceiling_price": expected_ceiling,
            "floor_price": expected_floor,
            "change": change,
            "pct_change": pct_change,
            "high": high,
            "low": low,
            "state": state,
        })

    def _get_seed_quote(self, symbol: str) -> StockQuote:
        clean = symbol.strip().upper()
        seed = self._load_seed()
        raw = seed.get("quotes", {}).get(clean)
        if raw:
            return self._sanitize_quote(StockQuote(**raw))

        if clean not in STOCK_UNIVERSE:
            raise KeyError(f"Symbol {symbol} not found")

        meta = STOCK_UNIVERSE.get(clean, {
            "symbol": clean,
            "company_name": clean,
            "sector": "Other",
            "exchange": "HOSE",
        })

        return self._sanitize_quote(StockQuote(
            symbol=clean,
            company_name=meta["company_name"],
            sector=meta["sector"],
            exchange=meta["exchange"],
            price=30000.0,
            change=0.0,
            pct_change=0.0,
            high=30500.0,
            low=29800.0,
            volume=5_000_000,
            ref_price=30000.0,
            ceiling_price=32100.0,
            floor_price=27900.0,
            state="REF",
            date="2026-10-29",
        ))

    def _get_seed_history(self, symbol: str, days: int = 90) -> List[OHLCVRecord]:
        clean = symbol.strip().upper()
        seed = self._load_seed()
        raw_list = seed.get("history", {}).get(clean, [])
        if raw_list:
            records = [OHLCVRecord(**item) for item in raw_list]
            records.sort(key=lambda r: r.time)
            return records[-days:]

        # Synthetic minimal 3-day history if entirely missing from seed
        is_index = clean in SUPPORTED_INDICES
        base = 1750.0 if is_index else 30000.0
        return [
            OHLCVRecord(time="2026-10-27", open=base, high=base * 1.01, low=base * 0.99, close=base, volume=1000000),
            OHLCVRecord(time="2026-10-28", open=base, high=base * 1.02, low=base * 0.98, close=base * 1.01, volume=1200000),
            OHLCVRecord(time="2026-10-29", open=base * 1.01, high=base * 1.03, low=base, close=base * 1.01, volume=1500000),
        ]

    def _get_seed_foreign(self, symbol: str) -> ForeignTradeRecord:
        clean = symbol.strip().upper()
        seed = self._load_seed()
        raw = seed.get("foreign_trades", {}).get(clean)
        if raw:
            return ForeignTradeRecord(**raw)
        return ForeignTradeRecord(
            symbol=clean,
            net_volume=100000,
            net_value_vnd=2_500_000_000.0,
            room_left=10_000_000,
            foreign_ratio=25.0,
            date="2026-10-29",
        )

    # -------------------------------------------------------------------------
    # Public Interface Contracts
    # -------------------------------------------------------------------------

    def get_indices(self) -> List[MarketIndex]:
        """
        Retrieves snapshot data for all 4 supported market indices:
        VNINDEX, VN30INDEX, HNX-INDEX, UPCOM-INDEX.
        """
        cache_key = "market_indices"

        # 1. Tier 1 Memory Cache
        cached_mem = self._get_from_memory(cache_key, self.index_ttl)
        if cached_mem:
            return [MarketIndex(**item) for item in cached_mem]

        # 2. Tier 2 Disk Cache
        cached_disk = self._get_from_disk(cache_key, self.index_ttl)
        if cached_disk:
            return [MarketIndex(**item) for item in cached_disk]

        # 3. Tier 3 Fetch (Live CafeF/Yahoo -> Seed fallback)
        results: List[MarketIndex] = []
        for symbol in SUPPORTED_INDICES.keys():
            idx = None
            if self.use_live:
                # CafeF primary
                idx = self.cafef.fetch_index_quote(symbol)
                # Yahoo Finance secondary fallback
                if idx is None:
                    idx = self.yahoo.fetch_index_quote(symbol)

            # Seed fallback guarantee
            if idx is None:
                idx = self._get_seed_index(symbol)

            results.append(idx)

        # Cache serialized representations
        serialized = [r.model_dump() for r in results]
        self._set_memory(cache_key, serialized)
        self._write_to_disk(cache_key, serialized)

        return results

    def get_quote(self, symbol: str) -> StockQuote:
        """
        Retrieves real-time or cached quote snapshot for a given stock symbol.
        Normalizes prices to VND and determines Vietnamese 5-color market state.
        """
        clean_sym = symbol.strip().upper()
        seed = self._load_seed()
        if clean_sym not in STOCK_UNIVERSE and clean_sym not in SUPPORTED_INDICES and clean_sym not in seed.get("quotes", {}):
            raise KeyError(f"Symbol {symbol} not found")

        cache_key = f"quote_{clean_sym}"

        # 1. Tier 1 Memory Cache
        cached_mem = self._get_from_memory(cache_key, self.quote_ttl)
        if cached_mem:
            return self._sanitize_quote(StockQuote(**cached_mem))

        # 2. Tier 2 Disk Cache
        cached_disk = self._get_from_disk(cache_key, self.quote_ttl)
        if cached_disk:
            return self._sanitize_quote(StockQuote(**cached_disk))

        # 3. Tier 3 Fetch
        quote = None
        if self.use_live:
            # Primary: CafeF
            quote = self.cafef.fetch_stock_quote(clean_sym)
            # Secondary: Yahoo Finance
            if quote is None:
                quote = self.yahoo.fetch_stock_quote(clean_sym)

        # Fallback to seed snapshot
        if quote is None:
            quote = self._get_seed_quote(clean_sym)

        # Attach foreign flow if available
        try:
            foreign = self.get_foreign_flow(clean_sym)
            quote.foreign_net_value_vnd = foreign.net_value_vnd
        except Exception:
            pass

        # Populate fundamental ratios from seed if zero
        seed_quote = self._get_seed_quote(clean_sym)
        if quote.pe == 0.0 and seed_quote.pe > 0:
            quote.pe = seed_quote.pe
            quote.pb = seed_quote.pb
            quote.roe = seed_quote.roe
            quote.dividend_yield = seed_quote.dividend_yield
            quote.market_cap_vnd = seed_quote.market_cap_vnd

        # Apply regulatory defensive guardrail & sanitization
        quote = self._sanitize_quote(quote)

        serialized = quote.model_dump()
        self._set_memory(cache_key, serialized)
        self._write_to_disk(cache_key, serialized)

        return quote

    def get_all_quotes(self) -> List[StockQuote]:
        """Retrieves quotes for all 20 curated blue-chip stocks."""
        quotes = []
        for symbol in STOCK_UNIVERSE.keys():
            quotes.append(self._sanitize_quote(self.get_quote(symbol)))
        return quotes

    def get_history(self, symbol: str, days: int = 90) -> List[OHLCVRecord]:
        """
        Retrieves daily OHLCV candlesticks for an index or stock.
        Guaranteed to be sorted in chronological ascending order (oldest -> newest).
        """
        if days <= 0:
            return []

        clean_sym = symbol.strip().upper()
        seed = self._load_seed()
        if clean_sym not in STOCK_UNIVERSE and clean_sym not in SUPPORTED_INDICES and clean_sym not in seed.get("history", {}):
            raise KeyError(f"Symbol {symbol} not found")

        cache_key = f"history_{clean_sym}_{days}"

        # 1. Tier 1 Memory Cache
        cached_mem = self._get_from_memory(cache_key, self.history_ttl)
        if cached_mem:
            return [OHLCVRecord(**item) for item in cached_mem]

        # 2. Tier 2 Disk Cache
        cached_disk = self._get_from_disk(cache_key, self.history_ttl)
        if cached_disk:
            return [OHLCVRecord(**item) for item in cached_disk]

        # 3. Tier 3 Fetch
        candles: Optional[List[OHLCVRecord]] = None
        if self.use_live:
            # Primary: CafeF
            candles = self.cafef.fetch_ohlcv(clean_sym, target_count=days)
            # Secondary: Yahoo Finance
            if not candles or len(candles) < 20:
                y_candles = self.yahoo.fetch_ohlcv(clean_sym, range_str=f"{days}d")
                if y_candles and len(y_candles) >= 20:
                    candles = y_candles

        # Fallback to seed snapshot
        if not candles or len(candles) < 10:
            candles = self._get_seed_history(clean_sym, days=days)

        # Enforce chronological ascending sort
        candles.sort(key=lambda r: r.time)
        candles = candles[-days:]

        serialized = [c.model_dump() for c in candles]
        self._set_memory(cache_key, serialized)
        self._write_to_disk(cache_key, serialized)

        return candles

    def get_foreign_flow(self, symbol: str) -> ForeignTradeRecord:
        """Retrieves foreign investor net flow and foreign room for a stock."""
        clean_sym = symbol.strip().upper()
        seed = self._load_seed()
        if clean_sym not in STOCK_UNIVERSE and clean_sym not in seed.get("foreign_trades", {}):
            raise KeyError(f"Symbol {symbol} not found")

        cache_key = f"foreign_{clean_sym}"

        # 1. Tier 1 Memory Cache
        cached_mem = self._get_from_memory(cache_key, self.foreign_ttl)
        if cached_mem:
            return ForeignTradeRecord(**cached_mem)

        # 2. Tier 2 Disk Cache
        cached_disk = self._get_from_disk(cache_key, self.foreign_ttl)
        if cached_disk:
            return ForeignTradeRecord(**cached_disk)

        # 3. Tier 3 Fetch
        record = None
        if self.use_live:
            record = self.cafef.fetch_foreign_trade(clean_sym)

        if record is None:
            record = self._get_seed_foreign(clean_sym)

        serialized = record.model_dump()
        self._set_memory(cache_key, serialized)
        self._write_to_disk(cache_key, serialized)

        return record

    def get_market_foreign_flow(self) -> List[ForeignTradeRecord]:
        """
        Retrieves aggregate foreign investor net flow records for all 20 universe stocks.
        """
        cache_key = "market_foreign_flow"

        # 1. Tier 1 Memory Cache
        cached_mem = self._get_from_memory(cache_key, self.foreign_ttl)
        if cached_mem:
            return [ForeignTradeRecord(**item) for item in cached_mem]

        # 2. Tier 2 Disk Cache
        cached_disk = self._get_from_disk(cache_key, self.foreign_ttl)
        if cached_disk:
            return [ForeignTradeRecord(**item) for item in cached_disk]

        # 3. Retrieve for all universe stocks
        records: List[ForeignTradeRecord] = []
        for symbol in STOCK_UNIVERSE.keys():
            records.append(self.get_foreign_flow(symbol))

        serialized = [r.model_dump() for r in records]
        self._set_memory(cache_key, serialized)
        self._write_to_disk(cache_key, serialized)

        return records

    def get_market_breadth(self) -> Dict[str, int]:
        """
        Computes market breadth distribution across the 20-stock universe:
        counts of CEILING (purple), UP (green), REF (yellow), DOWN (red), FLOOR (cyan).
        Includes both lowercase and uppercase keys for seamless Pydantic MarketBreadth serialization.
        """
        quotes = self.get_all_quotes()
        counts = {
            "ceiling": 0,
            "up": 0,
            "ref": 0,
            "down": 0,
            "floor": 0,
            "CEILING": 0,
            "UP": 0,
            "REF": 0,
            "DOWN": 0,
            "FLOOR": 0,
            "total": len(quotes),
        }
        for q in quotes:
            state = q.state.upper()
            lower = state.lower()
            if state in ("CEILING", "UP", "REF", "DOWN", "FLOOR"):
                counts[state] += 1
                counts[lower] += 1
            else:
                counts["REF"] += 1
                counts["ref"] += 1
        return counts
