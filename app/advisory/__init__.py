"""Milestone 3 Advisory Package (M3_ADVISORY).
100-Share Knapsack Asset Allocator & Risk Profiles.
"""

from app.advisory.models import (
    AdvisoryRequest,
    AdvisoryResponse,
    AdvisoryRecommendation,
    RiskLevel,
    InvestmentHorizon,
    StockAllocation,
    AssetAllocationItem,
    SummaryMetrics,
    PortfolioSummaryMetrics,
    PortfolioMetrics,
)
from app.advisory.allocator import AdvisoryEngine
from app.advisory.profiles import (
    normalize_risk_level,
    normalize_horizon,
    resolve_sector_candidates,
    score_candidate_stock,
    generate_strategic_notes,
    generate_stock_rationale,
    SECTOR_ALIASES,
)

__all__ = [
    "AdvisoryEngine",
    "AdvisoryRequest",
    "AdvisoryResponse",
    "AdvisoryRecommendation",
    "RiskLevel",
    "InvestmentHorizon",
    "StockAllocation",
    "AssetAllocationItem",
    "SummaryMetrics",
    "PortfolioSummaryMetrics",
    "PortfolioMetrics",
    "normalize_risk_level",
    "normalize_horizon",
    "resolve_sector_candidates",
    "score_candidate_stock",
    "generate_strategic_notes",
    "generate_stock_rationale",
    "SECTOR_ALIASES",
]
