"""Yahoo Finance v8 chart API client fallback for Vietnamese stock market data."""

import json
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from app.config import (
    SUPPORTED_INDICES,
    STOCK_UNIVERSE,
)
from app.data.models import (
    MarketIndex,
    StockQuote,
    OHLCVRecord,
)
from app.data.cafef import _calculate_limits, _determine_state

logger = logging.getLogger(__name__)

YFINANCE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "*/*",
}

DEFAULT_TIMEOUT = 7.0


def map_to_yahoo_symbol(symbol: str) -> str:
    """Maps internal symbol to Yahoo Finance ticker format."""
    clean = symbol.strip().upper()
    if clean == "VNINDEX":
        return "^VNINDEX.VN"
    if clean.startswith("^"):
        return clean
    if not clean.endswith(".VN"):
        return f"{clean}.VN"
    return clean


class YahooFinanceClient:
    """Fallback client querying Yahoo Finance v8 unauthenticated chart endpoint."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        self.timeout = timeout

    def _get_chart(self, yahoo_sym: str, range_str: str = "3mo") -> Optional[Dict[str, Any]]:
        """Queries Yahoo Finance v8 chart API."""
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_sym}?range={range_str}&interval=1d"
        req = urllib.request.Request(url, headers=YFINANCE_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = resp.read().decode("utf-8")
                parsed = json.loads(data)
                result = parsed.get("chart", {}).get("result")
                if result and len(result) > 0:
                    return result[0]
                return None
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as e:
            logger.warning(f"Yahoo Finance request failed for {yahoo_sym}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Unexpected Yahoo Finance error for {yahoo_sym}: {e}")
            return None

    def fetch_ohlcv(self, symbol: str, range_str: str = "3mo") -> Optional[List[OHLCVRecord]]:
        """
        Fetches daily OHLCV series from Yahoo Finance.
        Yahoo Finance already returns raw VND for stocks and raw points for indices.
        Returns records sorted in chronological ascending order.
        """
        clean_sym = symbol.strip().upper()
        is_index = clean_sym in SUPPORTED_INDICES
        # Yahoo Finance only supports VNINDEX; return None gracefully for other indices
        if is_index and clean_sym != "VNINDEX":
            return None

        yahoo_sym = map_to_yahoo_symbol(symbol)
        chart = self._get_chart(yahoo_sym, range_str=range_str)
        if not chart:
            return None

        timestamps = chart.get("timestamp", [])
        indicators = chart.get("indicators", {})
        quotes_list = indicators.get("quote", [])
        if not timestamps or not quotes_list:
            return None

        quote = quotes_list[0]
        opens = quote.get("open", [])
        highs = quote.get("high", [])
        lows = quote.get("low", [])
        closes = quote.get("close", [])
        volumes = quote.get("volume", [])

        records: List[OHLCVRecord] = []
        for i, ts in enumerate(timestamps):
            if i >= len(closes):
                break
            c = closes[i]
            if c is None or c <= 0:
                continue

            o = opens[i] if i < len(opens) and opens[i] is not None else c
            h = highs[i] if i < len(highs) and highs[i] is not None else max(o, c)
            l = lows[i] if i < len(lows) and lows[i] is not None else min(o, c)
            v = int(volumes[i]) if i < len(volumes) and volumes[i] is not None else 0

            date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            records.append(
                OHLCVRecord(
                    time=date_str,
                    open=round(float(o), 2 if is_index else 0),
                    high=round(float(h), 2 if is_index else 0),
                    low=round(float(l), 2 if is_index else 0),
                    close=round(float(c), 2 if is_index else 0),
                    volume=v,
                )
            )

        if not records:
            return None

        records.sort(key=lambda r: r.time)
        return records

    def fetch_stock_quote(self, symbol: str) -> Optional[StockQuote]:
        """Fetches stock quote snapshot from Yahoo Finance."""
        clean_sym = symbol.strip().upper()
        meta_info = STOCK_UNIVERSE.get(clean_sym)
        if not meta_info:
            meta_info = {
                "symbol": clean_sym,
                "company_name": clean_sym,
                "sector": "Other",
                "exchange": "HOSE",
            }

        yahoo_sym = map_to_yahoo_symbol(clean_sym)
        chart = self._get_chart(yahoo_sym, range_str="5d")
        if not chart:
            return None

        meta = chart.get("meta", {})
        price = float(meta.get("regularMarketPrice") or 0.0)
        daily_chg = meta.get("fulldayChange") or meta.get("regularMarketChange")
        if daily_chg is not None:
            ref_price = price - float(daily_chg)
        else:
            ref_price = float(meta.get("chartPreviousClose") or price)
        if ref_price <= 0:
            ref_price = price
        high = float(meta.get("regularMarketDayHigh") or price)
        low = float(meta.get("regularMarketDayLow") or price)
        vol = int(meta.get("regularMarketVolume") or 0)
        chg = price - ref_price
        pct_chg = round((chg / ref_price * 100.0), 2) if ref_price > 0 else 0.0

        ts = meta.get("regularMarketTime")
        date_str = (
            datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            if ts else ""
        )

        exchange = meta_info.get("exchange", "HOSE")
        ceiling, floor = _calculate_limits(ref_price, exchange)
        state = _determine_state(price, ref_price, ceiling, floor)

        return StockQuote(
            symbol=clean_sym,
            company_name=meta_info["company_name"],
            sector=meta_info["sector"],
            exchange=exchange,
            price=round(price, 0),
            change=round(chg, 0),
            pct_change=pct_chg,
            high=round(high, 0),
            low=round(low, 0),
            volume=vol,
            ref_price=round(ref_price, 0),
            ceiling_price=round(ceiling, 0),
            floor_price=round(floor, 0),
            state=state,
            date=date_str,
        )

    def fetch_index_quote(self, symbol: str) -> Optional[MarketIndex]:
        """Fetches market index snapshot from Yahoo Finance (primarily ^VNINDEX.VN)."""
        clean_sym = symbol.strip().upper()
        if clean_sym not in SUPPORTED_INDICES:
            return None
        # Yahoo Finance only supports VNINDEX; return None gracefully for other indices
        if clean_sym != "VNINDEX":
            return None

        index_def = SUPPORTED_INDICES[clean_sym]
        yahoo_sym = map_to_yahoo_symbol(clean_sym)
        chart = self._get_chart(yahoo_sym, range_str="5d")
        if not chart:
            return None

        meta = chart.get("meta", {})
        val = float(meta.get("regularMarketPrice") or 0.0)
        ref_val = float(meta.get("chartPreviousClose") or val)
        chg = val - ref_val
        pct_chg = round((chg / ref_val * 100.0), 2) if ref_val > 0 else 0.0
        vol = int(meta.get("regularMarketVolume") or 0)

        ts = meta.get("regularMarketTime")
        date_str = (
            datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            if ts else ""
        )

        state = "UP" if chg > 0 else ("DOWN" if chg < 0 else "REF")

        # Extract sparkline from recent closes
        indicators = chart.get("indicators", {})
        quotes_list = indicators.get("quote", [])
        sparkline = []
        if quotes_list:
            raw_c = quotes_list[0].get("close", [])
            sparkline = [round(float(c), 2) for c in raw_c if c is not None]

        return MarketIndex(
            symbol=clean_sym,
            name=index_def["name"],
            value=round(val, 2),
            change=round(chg, 2),
            pct_change=pct_chg,
            volume=vol,
            value_vnd=round(val * vol * 0.1, 0),  # approximation if turnover unavailable
            date=date_str,
            exchange=index_def["exchange"],
            sparkline=sparkline,
            state=state,
        )
