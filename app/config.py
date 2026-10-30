"""Application configuration, universe definitions, and market parameters."""

from pathlib import Path
from typing import Dict, Any

# Base Directories
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
SEEDS_DIR = DATA_DIR / "seeds"

# Caching Configuration (in seconds)
QUOTE_CACHE_TTL = 60          # 1 minute during active evaluation
HISTORY_CACHE_TTL = 3600       # 1 hour for historical candles
INDEX_CACHE_TTL = 60          # 1 minute for market indices
FOREIGN_CACHE_TTL = 300       # 5 minutes for foreign trade flow

# Regulatory Trading Constants
STANDARD_LOT_SIZE = 100        # Circular 120/2020/TT-BTC: 100-share whole lots

# Exchange Daily Price Limits
EXCHANGE_LIMITS = {
    "HOSE": 0.07,   # +/- 7.0%
    "HNX": 0.10,    # +/- 10.0%
    "UPCOM": 0.15,  # +/- 15.0%
}

# Supported Market Indices
SUPPORTED_INDICES: Dict[str, Dict[str, Any]] = {
    "VNINDEX": {
        "symbol": "VNINDEX",
        "name": "VN-Index",
        "exchange": "HOSE",
        "description": "Benchmark index of the Ho Chi Minh Stock Exchange",
        "limit_pct": 7.0,
    },
    "VN30INDEX": {
        "symbol": "VN30INDEX",
        "name": "VN30 Index",
        "exchange": "HOSE",
        "description": "Top 30 large-cap, high-liquidity stocks on HOSE",
        "limit_pct": 7.0,
    },
    "HNX-INDEX": {
        "symbol": "HNX-INDEX",
        "name": "HNX-Index",
        "exchange": "HNX",
        "description": "Index of all listed equities on Hanoi Stock Exchange",
        "limit_pct": 10.0,
    },
    "UPCOM-INDEX": {
        "symbol": "UPCOM-INDEX",
        "name": "UPCOM-Index",
        "exchange": "UPCOM",
        "description": "Unlisted Public Company Market Index",
        "limit_pct": 15.0,
    },
}

# Curated Stock Universe: 20 Blue-Chip Equities Across 6 Sectors
STOCK_UNIVERSE: Dict[str, Dict[str, Any]] = {
    # Banking (5)
    "VCB": {
        "symbol": "VCB",
        "company_name": "Ngân hàng TMCP Ngoại thương Việt Nam (Vietcombank)",
        "sector": "Banking",
        "exchange": "HOSE",
        "lot_size": STANDARD_LOT_SIZE,
        "description": "State anchor, highest asset quality and largest bank by market cap",
    },
    "TCB": {
        "symbol": "TCB",
        "company_name": "Ngân hàng TMCP Kỹ thương Việt Nam (Techcombank)",
        "sector": "Banking",
        "exchange": "HOSE",
        "lot_size": STANDARD_LOT_SIZE,
        "description": "High CASA leader, strong retail and corporate banking franchise",
    },
    "MBB": {
        "symbol": "MBB",
        "company_name": "Ngân hàng TMCP Quân đội (MB Bank)",
        "sector": "Banking",
        "exchange": "HOSE",
        "lot_size": STANDARD_LOT_SIZE,
        "description": "Military ecosystem, leading digital banking and robust ROE",
    },
    "BID": {
        "symbol": "BID",
        "company_name": "Ngân hàng TMCP Đầu tư và Phát triển Việt Nam (BIDV)",
        "sector": "Banking",
        "exchange": "HOSE",
        "lot_size": STANDARD_LOT_SIZE,
        "description": "Big-4 commercial bank with massive nationwide asset base",
    },
    "CTG": {
        "symbol": "CTG",
        "company_name": "Ngân hàng TMCP Công thương Việt Nam (VietinBank)",
        "sector": "Banking",
        "exchange": "HOSE",
        "lot_size": STANDARD_LOT_SIZE,
        "description": "Big-4 state bank driving key industrial and corporate credit",
    },

    # Real Estate (4)
    "VHM": {
        "symbol": "VHM",
        "company_name": "Công ty Cổ phần Vinhomes",
        "sector": "Real Estate",
        "exchange": "HOSE",
        "lot_size": STANDARD_LOT_SIZE,
        "description": "Leading residential real estate developer with mega-urban complexes",
    },
    "VIC": {
        "symbol": "VIC",
        "company_name": "Tập đoàn Vingroup - CTCP",
        "sector": "Real Estate",
        "exchange": "HOSE",
        "lot_size": STANDARD_LOT_SIZE,
        "description": "Premier private conglomerate spanning EV, property, and tech",
    },
    "NVL": {
        "symbol": "NVL",
        "company_name": "Công ty Cổ phần Tập đoàn Đầu tư Địa ốc No Va (Novaland)",
        "sector": "Real Estate",
        "exchange": "HOSE",
        "lot_size": STANDARD_LOT_SIZE,
        "description": "Urban and hospitality real estate turnaround player",
    },
    "KDH": {
        "symbol": "KDH",
        "company_name": "Công ty Cổ phần Đầu tư và Kinh doanh Nhà Khang Điền",
        "sector": "Real Estate",
        "exchange": "HOSE",
        "lot_size": STANDARD_LOT_SIZE,
        "description": "Clean land bank and conservative residential property developer",
    },

    # Technology (1)
    "FPT": {
        "symbol": "FPT",
        "company_name": "Công ty Cổ phần FPT",
        "sector": "Technology",
        "exchange": "HOSE",
        "lot_size": STANDARD_LOT_SIZE,
        "description": "Vietnam national technology champion: AI, Cloud, Semiconductor & IT Export",
    },

    # Retail / Consumer (3)
    "MWG": {
        "symbol": "MWG",
        "company_name": "Công ty Cổ phần Đầu tư Thế Giới Di Động",
        "sector": "Retail / Consumer",
        "exchange": "HOSE",
        "lot_size": STANDARD_LOT_SIZE,
        "description": "Top consumer electronics retailer expanding Bach Hoa Xanh grocery chain",
    },
    "MSN": {
        "symbol": "MSN",
        "company_name": "Công ty Cổ phần Tập đoàn Masan",
        "sector": "Retail / Consumer",
        "exchange": "HOSE",
        "lot_size": STANDARD_LOT_SIZE,
        "description": "Consumer goods FMCG, modern retail (WinCommerce) and meat platform",
    },
    "VNM": {
        "symbol": "VNM",
        "company_name": "Công ty Cổ phần Sữa Việt Nam (Vinamilk)",
        "sector": "Retail / Consumer",
        "exchange": "HOSE",
        "lot_size": STANDARD_LOT_SIZE,
        "description": "Dominant dairy producer with strong cash flow and defensive dividend yield",
    },

    # Materials / Industrials (1)
    "HPG": {
        "symbol": "HPG",
        "company_name": "Công ty Cổ phần Tập đoàn Hòa Phát",
        "sector": "Materials",
        "exchange": "HOSE",
        "lot_size": STANDARD_LOT_SIZE,
        "description": "National steel champion (Dung Quat complex) with highest market liquidity",
    },

    # Securities / Financials (2)
    "SSI": {
        "symbol": "SSI",
        "company_name": "Công ty Cổ phần Chứng khoán SSI",
        "sector": "Securities",
        "exchange": "HOSE",
        "lot_size": STANDARD_LOT_SIZE,
        "description": "Pioneering brokerage house, institutional leader benefiting from KRX upgrade",
    },
    "VND": {
        "symbol": "VND",
        "company_name": "Công ty Cổ phần Chứng khoán VNDIRECT",
        "sector": "Securities",
        "exchange": "HOSE",
        "lot_size": STANDARD_LOT_SIZE,
        "description": "Leading retail securities broker with advanced digital trading ecosystem",
    },

    # Energy / Utilities (4)
    "GAS": {
        "symbol": "GAS",
        "company_name": "Tổng Công ty Khí Việt Nam - CTCP (PV GAS)",
        "sector": "Energy / Utilities",
        "exchange": "HOSE",
        "lot_size": STANDARD_LOT_SIZE,
        "description": "PetroVietnam gas transmission monopoly with high dividend yields",
    },
    "POW": {
        "symbol": "POW",
        "company_name": "Tổng Công ty Điện lực Dầu khí Việt Nam (PV Power)",
        "sector": "Energy / Utilities",
        "exchange": "HOSE",
        "lot_size": STANDARD_LOT_SIZE,
        "description": "Second largest power producer, expanding into LNG Nhon Trach 3 & 4",
    },
    "GVR": {
        "symbol": "GVR",
        "company_name": "Tập đoàn Công nghiệp Cao su Việt Nam - CTCP",
        "sector": "Energy / Utilities",
        "exchange": "HOSE",
        "lot_size": STANDARD_LOT_SIZE,
        "description": "Vast land holdings converting from rubber plantations to industrial parks",
    },
    "REE": {
        "symbol": "REE",
        "company_name": "Công ty Cổ phần Cơ Điện Lạnh (REE Corporation)",
        "sector": "Energy / Utilities",
        "exchange": "HOSE",
        "lot_size": STANDARD_LOT_SIZE,
        "description": "Renewable energy infrastructure (hydro, wind, solar) and commercial leasing",
    },
}

SECTORS = sorted(list(set(stock["sector"] for stock in STOCK_UNIVERSE.values())))
