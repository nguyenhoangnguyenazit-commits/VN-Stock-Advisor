"""CafeF REST API client for Vietnamese stock market data."""

import json
import logging
import math
import re
import urllib.request
import urllib.error
from typing import List, Optional, Dict, Any

from app.config import (
    SUPPORTED_INDICES,
    STOCK_UNIVERSE,
    EXCHANGE_LIMITS,
)
from app.data.models import (
    MarketIndex,
    StockQuote,
    OHLCVRecord,
    ForeignTradeRecord,
)

logger = logging.getLogger(__name__)

CAFEF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Referer": "https://cafef.vn/",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}

DEFAULT_TIMEOUT = 7.0


def _parse_cafef_date(date_str: str) -> str:
    """Converts DD/MM/YYYY into ISO YYYY-MM-DD format, stripping any trailing time tokens."""
    if not date_str:
        return ""
    clean = date_str.strip().split()[0] if date_str.strip() else ""
    parts = clean.split("/")
    if len(parts) == 3:
        d, m, y = parts
        return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
    return clean


def _calculate_limits(ref_price: float, exchange: str) -> tuple[float, float]:
    """Calculates ceiling and floor prices based on exchange regulations."""
    limit_pct = EXCHANGE_LIMITS.get(exchange.upper(), 0.07)
    raw_ceiling = round(ref_price * (1.0 + limit_pct), 2)
    raw_floor = round(ref_price * (1.0 - limit_pct), 2)

    # In Vietnam, prices are rounded according to tick sizes:
    # < 10k: 10 VND; 10k-50k: 50 VND; >= 50k: 100 VND
    # For safety across all stocks, round to nearest 50 or 100 VND if price > 10,000
    if ref_price >= 50000:
        ceiling = math.floor(round(raw_ceiling / 100, 4)) * 100
        floor = math.ceil(round(raw_floor / 100, 4)) * 100
    elif ref_price >= 10000:
        ceiling = math.floor(round(raw_ceiling / 50, 4)) * 50
        floor = math.ceil(round(raw_floor / 50, 4)) * 50
    else:
        ceiling = math.floor(round(raw_ceiling / 10, 4)) * 10
        floor = math.ceil(round(raw_floor / 10, 4)) * 10

    return max(0.0, ceiling), max(0.0, floor)


def _determine_state(price: float, ref_price: float, ceiling: float, floor: float) -> str:
    """Classifies price state according to Vietnamese 5-color rules."""
    tolerance = 1.0  # 1 VND tolerance for float rounding
    if price >= (ceiling - tolerance) and ceiling > 0:
        return "CEILING"
    if price <= (floor + tolerance) and floor > 0:
        return "FLOOR"
    if price > (ref_price + tolerance):
        return "UP"
    if price < (ref_price - tolerance):
        return "DOWN"
    return "REF"


class CafeFClient:
    """Client for fetching data from CafeF's public ASP.NET handlers."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        self.timeout = timeout

    def _get_json(self, url: str) -> Optional[Dict[str, Any]]:
        """Performs a GET request and decodes the JSON payload."""
        req = urllib.request.Request(url, headers=CAFEF_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = resp.read().decode("utf-8")
                return json.loads(data)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as e:
            logger.warning(f"CafeF request failed for {url}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Unexpected CafeF error for {url}: {e}")
            return None

    def fetch_raw_price_history(
        self,
        symbol: str,
        page_index: int = 1,
        page_size: int = 30
    ) -> Optional[Dict[str, Any]]:
        """Calls PriceHistory.ashx endpoint for raw session history."""
        clean_sym = symbol.strip().upper()
        url = (
            f"https://cafef.vn/du-lieu/Ajax/PageNew/DataHistory/PriceHistory.ashx"
            f"?Symbol={clean_sym}&StartDate=&EndDate=&PageIndex={page_index}&PageSize={page_size}"
        )
        return self._get_json(url)

    def fetch_ohlcv(self, symbol: str, target_count: int = 90) -> Optional[List[OHLCVRecord]]:
        """
        Fetches historical daily OHLCV candles, paginating as needed.
        Normalizes equity prices by x1000 (CafeF quotes stocks in thousands).
        Indices remain in index points.
        Returns records sorted in chronological ascending order (oldest to newest).
        """
        clean_sym = symbol.strip().upper()
        is_index = clean_sym in SUPPORTED_INDICES
        price_multiplier = 1.0 if is_index else 1000.0

        records: List[OHLCVRecord] = []
        page_size = 30
        pages_needed = max(1, (target_count + page_size - 1) // page_size)

        for page in range(1, pages_needed + 1):
            raw = self.fetch_raw_price_history(clean_sym, page_index=page, page_size=page_size)
            if not raw or not raw.get("Success", True):
                break

            data_list = raw.get("Data", {}).get("Data", [])
            if not data_list:
                break

            for item in data_list:
                date_str = _parse_cafef_date(item.get("Ngay", ""))
                close_p = float(item.get("GiaDongCua") or item.get("GiaDieuChinh") or 0.0) * price_multiplier
                open_p = float(item.get("GiaMoCua") or close_p / price_multiplier) * price_multiplier
                high_p = float(item.get("GiaCaoNhat") or max(open_p, close_p) / price_multiplier) * price_multiplier
                low_p = float(item.get("GiaThapNhat") or min(open_p, close_p) / price_multiplier) * price_multiplier
                vol = int(item.get("KhoiLuongKhopLenh") or 0)

                # Avoid degenerate zero prices
                if close_p <= 0:
                    continue

                records.append(
                    OHLCVRecord(
                        time=date_str,
                        open=round(open_p, 2 if is_index else 0),
                        high=round(high_p, 2 if is_index else 0),
                        low=round(low_p, 2 if is_index else 0),
                        close=round(close_p, 2 if is_index else 0),
                        volume=vol,
                    )
                )

            if len(records) >= target_count:
                break

        if not records:
            return None

        # Sort chronological ascending (oldest first)
        records.sort(key=lambda r: r.time)
        return records[-target_count:]

    def fetch_index_quote(self, symbol: str) -> Optional[MarketIndex]:
        """Fetches and normalizes an index snapshot from PriceHistory.ashx."""
        clean_sym = symbol.strip().upper()
        if clean_sym not in SUPPORTED_INDICES:
            return None

        meta = SUPPORTED_INDICES[clean_sym]
        raw = self.fetch_raw_price_history(clean_sym, page_index=1, page_size=20)
        if not raw or "Data" not in raw:
            return None

        data_list = raw.get("Data", {}).get("Data", [])
        if not data_list:
            return None

        latest = data_list[0]
        current_val = float(latest.get("GiaDongCua") or latest.get("GiaDieuChinh") or 0.0)
        date_str = _parse_cafef_date(latest.get("Ngay", ""))

        if len(data_list) > 1:
            ref_val = float(data_list[1].get("GiaDongCua") or data_list[1].get("GiaDieuChinh") or current_val)
            chg = current_val - ref_val
            pct = round((chg / ref_val * 100.0), 2) if ref_val > 0 else 0.0
        else:
            chg = 0.0
            pct = 0.0
            thay_doi = str(latest.get("ThayDoi") or "")
            match = re.search(r"([+-]?[\d,.]+)\s*\(([+-]?[\d,.]+)", thay_doi)
            if match:
                try:
                    chg = float(match.group(1).replace(",", "."))
                    pct = float(match.group(2).replace(",", "."))
                except (ValueError, TypeError):
                    pass

        vol_raw = latest.get("KhoiLuongKhopLenh")
        try:
            volume = int(float(str(vol_raw).replace(",", "")))
        except (ValueError, TypeError):
            volume = 0

        val_raw = latest.get("GiaTriKhopLenh")
        try:
            # giaTriKhopLenh is in billion VND
            value_vnd = float(str(val_raw).replace(",", "")) * 1e9
        except (ValueError, TypeError):
            value_vnd = 0.0

        # Build sparkline from recent days
        sparkline = [
            float(d.get("GiaDongCua") or 0.0)
            for d in reversed(data_list)
            if d.get("GiaDongCua") is not None
        ]

        # Determine index state
        state = "UP" if chg > 0 else ("DOWN" if chg < 0 else "REF")

        return MarketIndex(
            symbol=clean_sym,
            name=meta["name"],
            value=round(current_val, 2),
            change=round(chg, 2),
            pct_change=round(pct, 2),
            volume=volume,
            value_vnd=round(value_vnd, 0),
            date=date_str,
            exchange=meta["exchange"],
            sparkline=sparkline,
            state=state,
        )

    def fetch_stock_quote(self, symbol: str) -> Optional[StockQuote]:
        """Fetches and normalizes an equity quote snapshot from CafeF."""
        clean_sym = symbol.strip().upper()
        meta = STOCK_UNIVERSE.get(clean_sym)
        if not meta:
            # Dynamic fallback metadata
            meta = {
                "symbol": clean_sym,
                "company_name": clean_sym,
                "sector": "Other",
                "exchange": "HOSE",
            }

        raw = self.fetch_raw_price_history(clean_sym, page_index=1, page_size=5)
        if not raw or "Data" not in raw:
            return None

        data_list = raw["Data"].get("Data", [])
        if not data_list:
            return None

        latest = data_list[0]
        # Multiply equity price by 1000
        price = float(latest.get("GiaDongCua") or latest.get("GiaDieuChinh") or 0.0) * 1000.0
        high = float(latest.get("GiaCaoNhat") or price / 1000.0) * 1000.0
        low = float(latest.get("GiaThapNhat") or price / 1000.0) * 1000.0
        vol = int(latest.get("KhoiLuongKhopLenh") or 0)
        date_str = _parse_cafef_date(latest.get("Ngay", ""))

        # Previous day closing is the reference price
        if len(data_list) > 1:
            ref_price = float(data_list[1].get("GiaDongCua") or data_list[1].get("GiaDieuChinh") or 0.0) * 1000.0
        else:
            ref_price = price

        chg = price - ref_price
        pct_chg = round((chg / ref_price * 100.0), 2) if ref_price > 0 else 0.0

        exchange = meta.get("exchange", "HOSE")
        ceiling, floor = _calculate_limits(ref_price, exchange)
        state = _determine_state(price, ref_price, ceiling, floor)

        return StockQuote(
            symbol=clean_sym,
            company_name=meta["company_name"],
            sector=meta["sector"],
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

    def fetch_foreign_trade(self, symbol: str) -> Optional[ForeignTradeRecord]:
        """Fetches foreign trading flow from GDKhoiNgoai.ashx."""
        clean_sym = symbol.strip().upper()
        url = (
            f"https://cafef.vn/du-lieu/Ajax/PageNew/DataHistory/GDKhoiNgoai.ashx"
            f"?Symbol={clean_sym}&StartDate=&EndDate=&PageIndex=1&PageSize=1"
        )
        data = self._get_json(url)
        if not data or not data.get("Success", True):
            return None

        items = data.get("Data", {}).get("Data", [])
        if not items:
            return None

        latest = items[0]
        net_vol = int(latest.get("KLGDRong") or 0)
        net_val_vnd = float(latest.get("GTDGRong") or 0.0)
        room_left = int(latest.get("RoomConLai") or 0)
        foreign_ratio = float(latest.get("DangSoHuu") or 0.0)
        date_str = _parse_cafef_date(latest.get("Ngay", ""))

        return ForeignTradeRecord(
            symbol=clean_sym,
            net_volume=net_vol,
            net_value_vnd=net_val_vnd,
            room_left=room_left,
            foreign_ratio=foreign_ratio,
            date=date_str,
        )

    def fetch_proprietary_trade(self, symbol: str = "VNINDEX") -> Optional[Dict[str, Any]]:
        """Fetches proprietary trading flow from GDTuDoanh.ashx."""
        clean_sym = symbol.strip().upper()
        url = (
            f"https://cafef.vn/du-lieu/Ajax/PageNew/DataHistory/GDTuDoanh.ashx"
            f"?Symbol={clean_sym}&StartDate=&EndDate=&PageIndex=1&PageSize=5"
        )
        data = self._get_json(url)
        if not data or not data.get("Success", True):
            return None

        report = data.get("Data", {}).get("TradingReport", {})
        return {
            "symbol": clean_sym,
            "buy_val_vnd": float(report.get("TongGtMua") or 0.0),
            "sell_val_vnd": float(report.get("TongGtBan") or 0.0),
            "buy_vol": int(report.get("TongKlMua") or 0),
            "sell_vol": int(report.get("TongKlBan") or 0),
        }
