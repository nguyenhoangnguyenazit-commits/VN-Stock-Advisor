"""Pydantic data models for Vietnamese stock market entities."""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


class MarketIndex(BaseModel):
    """Schema representing a Vietnamese market index snapshot."""
    model_config = ConfigDict(populate_by_name=True)

    symbol: str = Field(description="Index symbol, e.g. VNINDEX, VN30INDEX, HNX-INDEX, UPCOM-INDEX")
    name: str = Field(description="Full index name, e.g. VN-Index")
    value: float = Field(description="Current index points, e.g. 1755.61")
    change: float = Field(description="Absolute change in points, e.g. -11.04")
    pct_change: float = Field(description="Percentage change, e.g. -0.625")
    volume: int = Field(description="Total matched trading volume")
    value_vnd: float = Field(description="Total trading value in VND")
    date: str = Field(description="Trading date string, YYYY-MM-DD or DD/MM/YYYY")
    exchange: str = Field(default="HOSE", description="Underlying exchange")
    sparkline: List[float] = Field(default_factory=list, description="Recent 15-30 index closing values")
    state: Literal["CEILING", "FLOOR", "UP", "DOWN", "REF"] = Field(
        default="REF",
        description="Market state based on reference price"
    )


class StockQuote(BaseModel):
    """Schema representing an individual stock quote snapshot."""
    model_config = ConfigDict(populate_by_name=True)

    symbol: str = Field(description="Stock ticker symbol, e.g. FPT, VCB")
    company_name: str = Field(description="Full registered enterprise name")
    sector: str = Field(description="Industry sector, e.g. Technology, Banking")
    exchange: str = Field(description="Exchange board: HOSE, HNX, or UPCOM")
    price: float = Field(description="Current matching price in raw VND, e.g. 52700.0")
    change: float = Field(description="Price change compared to reference in VND, e.g. -1300.0")
    pct_change: float = Field(description="Percentage price change, e.g. -2.407")
    high: float = Field(description="Highest matched price in session in VND")
    low: float = Field(description="Lowest matched price in session in VND")
    volume: int = Field(description="Accumulated matched volume in session")
    ref_price: float = Field(description="Reference price (previous close) in VND")
    ceiling_price: float = Field(description="Ceiling price limit in VND")
    floor_price: float = Field(description="Floor price limit in VND")
    state: Literal["CEILING", "FLOOR", "UP", "DOWN", "REF"] = Field(
        default="REF",
        description="Vietnamese 5-color state classification"
    )
    date: str = Field(default="", description="Trading date string (YYYY-MM-DD)")

    # Key Fundamental & Financial Metrics (Optional with realistic defaults)
    pe: float = Field(default=0.0, description="Trailing Price-to-Earnings ratio")
    pb: float = Field(default=0.0, description="Price-to-Book ratio")
    roe: float = Field(default=0.0, description="Return on Equity percentage")
    dividend_yield: float = Field(default=0.0, description="Dividend yield percentage")
    foreign_net_value_vnd: float = Field(default=0.0, description="Session foreign net buy/sell value in VND")
    market_cap_vnd: float = Field(default=0.0, description="Estimated market capitalization in VND")


class OHLCVRecord(BaseModel):
    """Schema representing a single daily candlestick bar."""
    model_config = ConfigDict(populate_by_name=True)

    time: str = Field(description="Candlestick date in YYYY-MM-DD format (standard for TradingView)")
    open: float = Field(description="Opening price in VND (or index points for indices)")
    high: float = Field(description="Session high price in VND (or index points)")
    low: float = Field(description="Session low price in VND (or index points)")
    close: float = Field(description="Closing price in VND (or index points)")
    volume: int = Field(description="Traded volume (number of shares or index units)")


class ForeignTradeRecord(BaseModel):
    """Schema representing foreign investor trading activity."""
    model_config = ConfigDict(populate_by_name=True)

    symbol: str = Field(description="Stock ticker symbol")
    net_volume: int = Field(description="Foreign net trading volume (buy - sell)")
    net_value_vnd: float = Field(description="Foreign net trading value in VND")
    room_left: int = Field(description="Remaining foreign ownership room shares")
    foreign_ratio: float = Field(default=0.0, description="Current foreign ownership ratio percentage")
    date: str = Field(default="", description="Trading date (YYYY-MM-DD)")


class MarketBreadth(BaseModel):
    """Schema representing market-wide price distribution breadth."""
    ceiling: int = Field(default=0, description="Number of stocks at ceiling price (Purple)")
    up: int = Field(default=0, description="Number of stocks gaining (Green)")
    ref: int = Field(default=0, description="Number of stocks unchanged (Yellow)")
    down: int = Field(default=0, description="Number of stocks declining (Red)")
    floor: int = Field(default=0, description="Number of stocks at floor price (Cyan)")
    total: int = Field(default=0, description="Total number of evaluated stocks")
