"""Pydantic data models for Milestone 3 (M3_ADVISORY).

Enforces:
- 100-share whole lot invariants per Circular 120/2020/TT-BTC
- Strict capital conservation: total_invested_vnd + cash_remainder_vnd == budget_vnd
- Dual-naming support for AssetAllocationItem (category/asset_class, weight_pct/percentage, value_vnd/allocated_vnd)
- Flexible risk profiles (with BALANCED alias for MODERATE) and multi-horizon normalizations
"""

from enum import Enum
from typing import List, Optional, Union, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


class RiskLevel(str, Enum):
    """Investor risk tolerance classification."""
    CONSERVATIVE = "CONSERVATIVE"
    MODERATE = "MODERATE"
    AGGRESSIVE = "AGGRESSIVE"


class InvestmentHorizon(str, Enum):
    """Investment planning timeframe."""
    SHORT_TERM = "SHORT_TERM"       # 1 - 3 months
    MEDIUM_TERM = "MEDIUM_TERM"     # 6 - 12 months
    LONG_TERM = "LONG_TERM"         # 1 - 3 years
    ONE_MONTH = "1_MONTH"
    THREE_MONTHS = "3_MONTHS"
    SIX_MONTHS = "6_MONTHS"
    ONE_YEAR = "1_YEAR"
    TWO_YEARS = "2_YEARS"


class AdvisoryRequest(BaseModel):
    """Client request schema for personalized portfolio allocation."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    budget: float = Field(
        ...,
        gt=0.0,
        description="Total capital in VND. Must be strictly positive (> 0)."
    )
    risk_level: RiskLevel = Field(
        default=RiskLevel.MODERATE,
        description="Risk tolerance tier: CONSERVATIVE, MODERATE, or AGGRESSIVE."
    )
    horizon: Optional[Union[InvestmentHorizon, str]] = Field(
        default="MEDIUM_TERM",
        description="Target investment timeframe."
    )
    sectors: Optional[List[str]] = Field(
        default=None,
        description="Preferred sectors (e.g. ['Technology', 'Banking']). None or empty means full universe."
    )
    excluded_symbols: Optional[List[str]] = Field(
        default=None,
        description="Optional list of ticker symbols to exclude from candidate consideration."
    )

    @field_validator("risk_level", mode="before")
    @classmethod
    def validate_risk_level(cls, v: Any) -> Any:
        if isinstance(v, str):
            clean = v.strip().upper()
            if clean == "BALANCED":
                return RiskLevel.MODERATE
            if clean in ("CONSERVATIVE", "MODERATE", "AGGRESSIVE"):
                return RiskLevel(clean)
            raise ValueError(
                f"Invalid risk_level '{v}'. Must be one of CONSERVATIVE, MODERATE (or BALANCED), AGGRESSIVE"
            )
        return v

    @field_validator("horizon", mode="before")
    @classmethod
    def normalize_horizon(cls, v: Any) -> str:
        if v is None:
            return "MEDIUM_TERM"
        if isinstance(v, InvestmentHorizon):
            return v.value
        return str(v).strip().upper()

    @field_validator("sectors", mode="before")
    @classmethod
    def normalize_sectors(cls, v: Any) -> Optional[List[str]]:
        if v is None:
            return None
        if isinstance(v, list):
            cleaned = [str(s).strip() for s in v if str(s).strip()]
            return cleaned if cleaned else None
        return None

    @field_validator("excluded_symbols", mode="before")
    @classmethod
    def normalize_excluded_symbols(cls, v: Any) -> Optional[List[str]]:
        if v is None:
            return None
        if isinstance(v, list):
            return [str(s).strip().upper() for s in v if str(s).strip()]
        return None


class StockAllocation(BaseModel):
    """Schema representing an individual equity allocation within the recommended portfolio."""
    model_config = ConfigDict(populate_by_name=True)

    symbol: str = Field(description="Ticker symbol, e.g. FPT, VCB, HPG")
    company_name: str = Field(description="Full company name")
    sector: str = Field(description="Industry sector, e.g. Technology, Banking")
    current_price_vnd: float = Field(gt=0.0, description="Current market matching price in raw VND")
    allocated_lots: int = Field(ge=1, description="Number of standard 100-share trading lots")
    allocated_shares: int = Field(ge=100, description="Total shares allocated (must equal lots * 100)")
    total_cost_vnd: float = Field(gt=0.0, description="Total acquisition cost in VND: shares * price")
    weight_pct: float = Field(ge=0.0, le=100.0, description="Percentage weight of total portfolio budget")
    signal: str = Field(default="BUY", description="Directional signal: BUY or ACCUMULATE")
    target_price_vnd: float = Field(gt=0.0, description="Calculated 30-day forecast target price in VND")
    expected_return_pct: float = Field(default=0.0, description="Projected return percentage based on target price")
    stop_loss_vnd: float = Field(gt=0.0, description="Protective stop-loss price in VND")
    rationale: str = Field(description="Investment thesis and strategic selection rationale")

    @model_validator(mode="after")
    def verify_lot_invariants(self) -> "StockAllocation":
        """Strictly enforces Vietnamese Circular 120/2020/TT-BTC whole lot rules."""
        if self.allocated_shares != self.allocated_lots * 100:
            raise ValueError(
                f"allocated_shares ({self.allocated_shares}) must equal allocated_lots ({self.allocated_lots}) * 100"
            )
        if self.allocated_shares % 100 != 0:
            raise ValueError(
                f"allocated_shares ({self.allocated_shares}) violates 100-share whole lot rule (shares % 100 != 0)"
            )
        return self


class AssetAllocationItem(BaseModel):
    """Schema representing an asset class breakdown for portfolio donut visualization."""
    model_config = ConfigDict(populate_by_name=True)

    category: str = Field(description="Asset category, e.g. Equities, Cash Buffer")
    asset_class: str = Field(default="", description="Alias for category")
    weight_pct: float = Field(ge=0.0, le=100.0, description="Allocation weight percentage")
    percentage: float = Field(default=0.0, ge=0.0, le=100.0, description="Alias for weight_pct")
    value_vnd: float = Field(ge=0.0, description="Capital allocated in VND")
    allocated_vnd: float = Field(default=0.0, ge=0.0, description="Alias for value_vnd")

    @model_validator(mode="before")
    @classmethod
    def synchronize_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            cat = data.get("category") or data.get("asset_class") or ""
            data["category"] = cat
            data["asset_class"] = cat

            pct = data.get("weight_pct") if data.get("weight_pct") is not None else data.get("percentage", 0.0)
            data["weight_pct"] = float(pct)
            data["percentage"] = float(pct)

            val = data.get("value_vnd") if data.get("value_vnd") is not None else data.get("allocated_vnd", 0.0)
            data["value_vnd"] = float(val)
            data["allocated_vnd"] = float(val)
        return data


class SummaryMetrics(BaseModel):
    """High-level portfolio financial metrics."""
    model_config = ConfigDict(populate_by_name=True)

    expected_return_pct: float = Field(description="Weighted portfolio expected annual return percentage")
    estimated_volatility_pct: float = Field(description="Weighted portfolio annual volatility percentage")
    sharpe_ratio: float = Field(description="Estimated risk-adjusted Sharpe Ratio")
    dividend_yield_est_pct: float = Field(default=0.0, description="Estimated weighted annual dividend yield")


# Aliases for SummaryMetrics
PortfolioSummaryMetrics = SummaryMetrics
PortfolioMetrics = SummaryMetrics


class AdvisoryResponse(BaseModel):
    """Complete portfolio recommendation output schema."""
    model_config = ConfigDict(populate_by_name=True)

    budget_vnd: float = Field(gt=0.0, description="Total initial investment budget in VND")
    total_invested_vnd: float = Field(ge=0.0, description="Total capital deployed in equities in VND")
    cash_remainder_vnd: float = Field(ge=0.0, description="Undeployed capital held as cash buffer in VND")
    cash_pct: float = Field(ge=0.0, le=100.0, description="Percentage of budget retained as cash")
    risk_level: str = Field(description="Evaluated risk profile (CONSERVATIVE, MODERATE, AGGRESSIVE)")
    horizon: str = Field(description="Evaluated investment horizon")
    stock_allocations: List[StockAllocation] = Field(default_factory=list, description="List of stock picks")
    asset_allocation: List[AssetAllocationItem] = Field(default_factory=list, description="Asset class donut breakdown")
    portfolio_expected_return_pct: float = Field(default=0.0, description="Weighted expected return pct")
    portfolio_volatility_pct: float = Field(default=0.0, description="Estimated portfolio volatility pct")
    summary_metrics: SummaryMetrics = Field(description="Financial summary metrics")
    strategic_notes: List[str] = Field(default_factory=list, description="Actionable execution guidance notes")

    @model_validator(mode="after")
    def verify_conservation_invariants(self) -> "AdvisoryResponse":
        """Verifies capital conservation and consistency invariants."""
        calculated_total = round(self.total_invested_vnd + self.cash_remainder_vnd, 2)
        expected_budget = round(self.budget_vnd, 2)
        if abs(calculated_total - expected_budget) > 0.05:
            raise ValueError(
                f"Capital conservation violated: total_invested ({self.total_invested_vnd}) + "
                f"cash_remainder ({self.cash_remainder_vnd}) = {calculated_total} != budget ({expected_budget})"
            )

        if self.total_invested_vnd == 0.0:
            if len(self.stock_allocations) != 0:
                raise ValueError("stock_allocations must be empty when total_invested_vnd is 0.0")
            if self.cash_pct != 100.0:
                raise ValueError("cash_pct must be 100.0% when total_invested_vnd is 0.0")

        return self


# Backward compatibility alias
AdvisoryRecommendation = AdvisoryResponse
