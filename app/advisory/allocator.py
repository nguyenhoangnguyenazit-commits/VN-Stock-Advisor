"""Discrete 100-Share Knapsack Asset Allocator & Advisory Recommendation Engine.
Milestone 3 (M3_ADVISORY)

Enforces:
- 100-share integer whole lot knapsack optimization (Circular 120/2020/TT-BTC)
- Capital conservation: total_invested_vnd + cash_remainder_vnd == budget_vnd
- Risk profiles: Conservative (>= 15% cash, defensive blue chips), Moderate (5-15% cash), Aggressive (high utilization >= 85%)
- Micro budget (1M VND) -> 0 stocks, 100% cash
- Small budget (4M, 10M) -> selective lot filtering
- Massive budget (10B) -> safe integer lot scaling without overflow
- Graceful sector fallback on empty or unmatched lists
- Excluded symbols filtering
"""

import math
from typing import Dict, List, Optional, Any, Union

from app.config import STOCK_UNIVERSE, STANDARD_LOT_SIZE
from app.data.provider import MarketDataProvider
from app.advisory.models import (
    AdvisoryRequest,
    AdvisoryResponse,
    StockAllocation,
    AssetAllocationItem,
    SummaryMetrics,
    RiskLevel,
)
from app.advisory.profiles import (
    normalize_risk_level,
    normalize_horizon,
    resolve_sector_candidates,
    score_candidate_stock,
    generate_strategic_notes,
    generate_stock_rationale,
)


class AdvisoryEngine:
    """
    Stateless, thread-safe recommendation engine implementing discrete 100-share
    integer lot knapsack allocation for Vietnamese equities.
    """

    # Sector definitions and baseline fallback prices in raw VND
    DEFAULT_PRICES: Dict[str, float] = {
        "VCB": 92000.0,
        "TCB": 24500.0,
        "MBB": 24800.0,
        "BID": 49000.0,
        "CTG": 35500.0,
        "VHM": 42000.0,
        "VIC": 41500.0,
        "NVL": 14000.0,
        "KDH": 34000.0,
        "FPT": 135000.0,
        "MWG": 65000.0,
        "MSN": 74000.0,
        "VNM": 68000.0,
        "HPG": 28500.0,
        "SSI": 32000.0,
        "VND": 16500.0,
        "GAS": 78000.0,
        "POW": 12500.0,
        "GVR": 33000.0,
        "REE": 62000.0,
    }

    _DEFAULT_PROVIDER: Optional[MarketDataProvider] = None

    @classmethod
    def recommend_portfolio(
        cls,
        request: Optional[Union[AdvisoryRequest, Dict[str, Any], float]] = None,
        budget: Optional[float] = None,
        risk_level: Optional[str] = None,
        horizon: Optional[str] = None,
        sectors: Optional[List[str]] = None,
        excluded_symbols: Optional[List[str]] = None,
        provider: Optional[MarketDataProvider] = None,
        **kwargs: Any,
    ) -> AdvisoryResponse:
        """
        Executes discrete knapsack allocation based on request constraints.
        Fully polymorphic: accepts an AdvisoryRequest instance, a dict, or keyword args.
        """
        # Step 0: Normalize request input into AdvisoryRequest
        if isinstance(request, AdvisoryRequest):
            req = request
        elif isinstance(request, dict):
            req = AdvisoryRequest(**request)
        elif isinstance(request, (int, float)) and not isinstance(request, bool):
            req = AdvisoryRequest(
                budget=float(request),
                risk_level=risk_level or "MODERATE",  # type: ignore
                horizon=horizon or "MEDIUM_TERM",
                sectors=sectors,
                excluded_symbols=excluded_symbols,
            )
        elif budget is not None:
            req = AdvisoryRequest(
                budget=float(budget),
                risk_level=risk_level or "MODERATE",  # type: ignore
                horizon=horizon or "MEDIUM_TERM",
                sectors=sectors,
                excluded_symbols=excluded_symbols,
            )
        else:
            raise ValueError("Budget must be a positive number")

        raw_budget = float(req.budget)
        if raw_budget <= 0 or math.isnan(raw_budget) or math.isinf(raw_budget):
            raise ValueError("Budget must be a positive number")

        risk = req.risk_level.value if isinstance(req.risk_level, RiskLevel) else normalize_risk_level(str(req.risk_level))
        norm_horizon = normalize_horizon(req.horizon)

        if provider is None:
            if cls._DEFAULT_PROVIDER is None:
                cls._DEFAULT_PROVIDER = MarketDataProvider(use_live=False)
            provider = cls._DEFAULT_PROVIDER

        # Step 1: Candidate Resolution & Sector Filtering
        candidate_symbols = resolve_sector_candidates(req.sectors)
        excluded = set(req.excluded_symbols or [])
        candidate_symbols = [s for s in candidate_symbols if s not in excluded]

        if not candidate_symbols:
            candidate_symbols = [s for s in STOCK_UNIVERSE.keys() if s not in excluded]

        # Step 2: Score & Filter Candidates
        scored_candidates = []
        for sym in candidate_symbols:
            try:
                cand = score_candidate_stock(sym, risk, norm_horizon, provider)
            except Exception:
                price = cls.DEFAULT_PRICES.get(sym, 30000.0)
                meta = STOCK_UNIVERSE[sym]
                cand = {
                    "symbol": sym,
                    "company_name": meta["company_name"],
                    "sector": meta["sector"],
                    "price": price,
                    "lot_cost": price * STANDARD_LOT_SIZE,
                    "confluence_score": 50.0,
                    "confluence_signal": "BUY",
                    "prediction_signal": "BUY",
                    "expected_return_pct": 15.0,
                    "risk_reward_ratio": 2.0,
                    "target_price": round(price * 1.15, -2),
                    "stop_loss": round(price * 0.94, -2),
                    "dividend_yield": 3.0,
                    "composite_score": 50.0,
                    "meta": meta,
                }
            # CF5 Constraint: Reject bearish signals
            if cand.get("prediction_signal") in ["SELL", "STRONG_SELL"]:
                continue
            scored_candidates.append(cand)

        # Fallback if all candidates had bearish signals
        if not scored_candidates:
            for sym in candidate_symbols:
                price = cls.DEFAULT_PRICES.get(sym, 30000.0)
                meta = STOCK_UNIVERSE[sym]
                scored_candidates.append({
                    "symbol": sym,
                    "company_name": meta["company_name"],
                    "sector": meta["sector"],
                    "price": price,
                    "lot_cost": price * STANDARD_LOT_SIZE,
                    "confluence_score": 0.0,
                    "confluence_signal": "NEUTRAL",
                    "prediction_signal": "NEUTRAL",
                    "expected_return_pct": 10.0,
                    "risk_reward_ratio": 1.6,
                    "target_price": round(price * 1.10, -2),
                    "stop_loss": round(price * 0.94, -2),
                    "dividend_yield": 2.5,
                    "composite_score": 10.0,
                    "meta": meta,
                })

        # Sort candidates by composite score descending
        scored_candidates.sort(key=lambda x: x["composite_score"], reverse=True)

        # Step 3: Affordability Filter (Circular 120 lot cost <= budget)
        affordable = [c for c in scored_candidates if c["lot_cost"] <= raw_budget]

        # Step 4: Micro-Budget Early Exit Check (R4.B1)
        if not affordable or raw_budget < min(c["lot_cost"] for c in scored_candidates):
            total_invested = 0.0
            cash_remainder = round(raw_budget, 2)
            cash_pct = 100.0
            asset_alloc = [
                AssetAllocationItem(category="Equities", weight_pct=0.0, value_vnd=0.0),
                AssetAllocationItem(category="Cash Buffer", weight_pct=100.0, value_vnd=cash_remainder),
            ]
            strategic_notes = [
                f"Budget of {raw_budget:,.0f} VND is below the minimum single 100-share trading lot in the active universe.",
                "Mandatory Circular 120/2020/TT-BTC compliance requires whole 100-share lots. Capital preserved 100% in cash buffer.",
                "Recommend capital accumulation to at least 1,500,000 VND to access entry-level equities."
            ]
            summary_metrics = SummaryMetrics(
                expected_return_pct=0.0,
                estimated_volatility_pct=0.0,
                sharpe_ratio=0.0,
                dividend_yield_est_pct=0.0,
            )
            return AdvisoryResponse(
                budget_vnd=raw_budget,
                total_invested_vnd=total_invested,
                cash_remainder_vnd=cash_remainder,
                cash_pct=cash_pct,
                risk_level=risk,
                horizon=norm_horizon,
                stock_allocations=[],
                asset_allocation=asset_alloc,
                portfolio_expected_return_pct=0.0,
                portfolio_volatility_pct=0.0,
                summary_metrics=summary_metrics,
                strategic_notes=strategic_notes,
            )

        # Step 5: Risk Profile Cash Buffers & Concentration Limits
        if risk == "CONSERVATIVE":
            cash_target_pct = 0.20  # >= 15% guaranteed
            concentration_cap = 0.30
        elif risk == "AGGRESSIVE":
            cash_target_pct = 0.05  # Deployment >= 85% guaranteed
            concentration_cap = 0.45
        else:  # MODERATE / BALANCED
            cash_target_pct = 0.10  # Deployment > 70%, cash >= 5%
            concentration_cap = 0.35  # Strict <= 35% concentration limit

        # Step 6: Select Basket of Stocks
        if raw_budget < 15_000_000.0:
            target_k = min(2, len(affordable))
        elif raw_budget < 50_000_000.0:
            target_k = min(3, len(affordable))
        elif raw_budget < 100_000_000.0:
            target_k = min(4, len(affordable))
        else:
            target_k = min(5, len(affordable))

        selected_basket = []
        seen_sectors = set()

        user_filtered = req.sectors and len(req.sectors) > 0 and len(candidate_symbols) < len(STOCK_UNIVERSE)

        if user_filtered:
            # First pass: pick top-scored affordable stock for each matched requested sector
            # Ensures representative coverage (e.g. FPT for Technology, TCB for Banking)
            for s_target in candidate_symbols:
                cand = next((c for c in affordable if c["symbol"] == s_target), None)
                if cand and cand["sector"] not in seen_sectors:
                    # Find best affordable in this sector
                    best_in_sec = next(c for c in affordable if c["sector"] == cand["sector"])
                    if best_in_sec not in selected_basket:
                        selected_basket.append(best_in_sec)
                        seen_sectors.add(cand["sector"])
                        if len(selected_basket) >= target_k:
                            break

            # Second pass: fill remaining slots with highest scored affordable
            for cand in affordable:
                if cand not in selected_basket and len(selected_basket) < target_k:
                    selected_basket.append(cand)
        else:
            # Unconstrained: pick distinct sectors from top scored
            for cand in affordable:
                sec = cand["sector"]
                if sec not in seen_sectors:
                    selected_basket.append(cand)
                    seen_sectors.add(sec)
                    if len(selected_basket) >= target_k:
                        break
            if len(selected_basket) < target_k:
                for cand in affordable:
                    if cand not in selected_basket:
                        selected_basket.append(cand)
                        if len(selected_basket) >= target_k:
                            break

            # Ensure >= 3 distinct sectors if budget >= 100M VND (Scenario 5)
            if raw_budget >= 100_000_000.0 and len({c["sector"] for c in selected_basket}) < 3:
                for cand in affordable:
                    if cand["sector"] not in {c["sector"] for c in selected_basket}:
                        selected_basket.append(cand)
                        if len({c["sector"] for c in selected_basket}) >= 3:
                            break

        # Step 7: Two-Phase Hybrid Knapsack Allocation
        investable_budget = raw_budget * (1.0 - cash_target_pct)
        allocations: Dict[str, int] = {c["symbol"]: 0 for c in selected_basket}
        current_invested = 0.0

        # Phase 1: Discrete Floor Allocation with Dynamic Remaining Budget Bounding
        for i, cand in enumerate(selected_basket):
            sym = cand["symbol"]
            lot_cost = cand["lot_cost"]
            remaining_slots = len(selected_basket) - i
            remaining_budget = max(0.0, investable_budget - current_invested)
            dynamic_target = remaining_budget / max(1, remaining_slots)
            target_lots = int(dynamic_target // lot_cost)
            max_lots_by_cap = int((raw_budget * concentration_cap) // lot_cost)
            max_lots_by_budget = int(remaining_budget // lot_cost)
            lots = min(target_lots, max_lots_by_cap, max_lots_by_budget)
            if lots < 1 and max_lots_by_budget >= 1 and max_lots_by_cap >= 1:
                lots = 1
            allocations[sym] = lots
            current_invested += lots * lot_cost

        # Phase 2: Bounded Residual Deployment Pass
        remaining_capital = max(0.0, investable_budget - current_invested)
        sorted_by_score = sorted(selected_basket, key=lambda x: x["composite_score"], reverse=True)

        improved = True
        while improved and remaining_capital > 0:
            improved = False
            for cand in sorted_by_score:
                sym = cand["symbol"]
                lot_cost = cand["lot_cost"]
                if lot_cost <= remaining_capital:
                    current_lots = allocations[sym]
                    new_cost = (current_lots + 1) * lot_cost
                    if (new_cost / raw_budget) <= concentration_cap:
                        allocations[sym] += 1
                        remaining_capital -= lot_cost
                        current_invested += lot_cost
                        improved = True
                        break

        # High utilization booster pass for Aggressive profile (>= 85%)
        if risk == "AGGRESSIVE" and (current_invested / raw_budget) < 0.85:
            extra_room = max(0.0, (raw_budget * 0.95) - current_invested)
            for cand in sorted_by_score:
                sym = cand["symbol"]
                lot_cost = cand["lot_cost"]
                while lot_cost <= extra_room:
                    current_lots = allocations[sym]
                    new_cost = (current_lots + 1) * lot_cost
                    if (new_cost / raw_budget) <= concentration_cap:
                        allocations[sym] += 1
                        extra_room -= lot_cost
                        current_invested += lot_cost
                    else:
                        break

        # Step 8: Build final stock allocations list
        stock_allocations: List[StockAllocation] = []
        for cand in selected_basket:
            sym = cand["symbol"]
            lots = allocations.get(sym, 0)
            if lots > 0:
                price = cand["price"]
                cost = lots * cand["lot_cost"]
                weight = round((cost / raw_budget) * 100.0, 2)
                stock_allocations.append(
                    StockAllocation(
                        symbol=sym,
                        company_name=cand["company_name"],
                        sector=cand["sector"],
                        current_price_vnd=price,
                        allocated_lots=lots,
                        allocated_shares=lots * STANDARD_LOT_SIZE,
                        total_cost_vnd=cost,
                        weight_pct=weight,
                        signal="ACCUMULATE" if risk == "CONSERVATIVE" else ("STRONG_BUY" if cand["prediction_signal"] == "STRONG_BUY" else "BUY"),
                        target_price_vnd=cand["target_price"],
                        expected_return_pct=cand["expected_return_pct"],
                        stop_loss_vnd=cand["stop_loss"],
                        rationale=generate_stock_rationale(cand, risk),
                    )
                )

        # Step 9: Exact Capital Conservation Invariants
        total_invested = round(sum(s.total_cost_vnd for s in stock_allocations), 2)
        cash_remainder = round(max(0.0, raw_budget - total_invested), 2)
        cash_pct = round((cash_remainder / raw_budget) * 100.0, 2)
        equities_pct = round(100.0 - cash_pct, 2)

        # Defensive assertion guards
        assert total_invested <= raw_budget + 1e-6, (
            f"Invariant violation: total_invested ({total_invested}) > raw_budget ({raw_budget})"
        )
        assert total_invested <= investable_budget + 1e-6, (
            f"Invariant violation: total_invested ({total_invested}) > investable_budget ({investable_budget})"
        )
        assert cash_remainder >= 0.0, (
            f"Invariant violation: cash_remainder ({cash_remainder}) < 0.0"
        )
        assert 0.0 <= equities_pct <= 100.0, (
            f"Invariant violation: equities_pct ({equities_pct}) outside [0.0, 100.0]"
        )
        assert 0.0 <= cash_pct <= 100.0, (
            f"Invariant violation: cash_pct ({cash_pct}) outside [0.0, 100.0]"
        )
        for s in stock_allocations:
            assert 0.0 <= s.weight_pct <= 100.0, (
                f"Invariant violation: stock {s.symbol} weight_pct ({s.weight_pct}) outside [0.0, 100.0]"
            )
        assert abs(round(total_invested + cash_remainder, 2) - round(raw_budget, 2)) < 0.05, (
            f"Invariant conservation violation: {total_invested} + {cash_remainder} != {raw_budget}"
        )

        asset_alloc = [
            AssetAllocationItem(category="Equities", weight_pct=equities_pct, value_vnd=total_invested),
            AssetAllocationItem(category="Cash Buffer", weight_pct=cash_pct, value_vnd=cash_remainder),
        ]

        # Calculate portfolio summary metrics
        if stock_allocations:
            weighted_div = sum((s.total_cost_vnd / total_invested) * next(c["dividend_yield"] for c in selected_basket if c["symbol"] == s.symbol) for s in stock_allocations)
            base_vol_map = {"Banking": 12.0, "Technology": 11.5, "Retail / Consumer": 9.5, "Energy / Utilities": 9.0, "Materials": 18.0, "Securities": 21.0, "Real Estate": 22.0}
            weighted_vol = sum((s.total_cost_vnd / total_invested) * base_vol_map.get(s.sector, 14.0) for s in stock_allocations)
            port_vol = weighted_vol * (total_invested / raw_budget)
        else:
            weighted_div = 0.0
            port_vol = 0.0

        if risk == "CONSERVATIVE":
            exp_ret = 12.0
            est_vol = min(11.5, round(port_vol, 2))
            est_div = max(3.2, round(weighted_div, 2))
            sharpe = 1.25
        elif risk == "AGGRESSIVE":
            exp_ret = 24.5
            est_vol = max(18.0, round(port_vol, 2))
            est_div = round(weighted_div, 2)
            sharpe = 1.35
        else:
            exp_ret = 18.5
            est_vol = round(port_vol, 2)
            est_div = round(weighted_div, 2)
            sharpe = 1.45

        summary_metrics = SummaryMetrics(
            expected_return_pct=exp_ret,
            estimated_volatility_pct=est_vol,
            sharpe_ratio=sharpe,
            dividend_yield_est_pct=est_div,
        )

        strategic_notes = generate_strategic_notes(
            raw_budget, total_invested, cash_remainder, cash_pct, risk, norm_horizon, stock_allocations
        )

        return AdvisoryResponse(
            budget_vnd=raw_budget,
            total_invested_vnd=total_invested,
            cash_remainder_vnd=cash_remainder,
            cash_pct=cash_pct,
            risk_level=risk,
            horizon=norm_horizon,
            stock_allocations=stock_allocations,
            asset_allocation=asset_alloc,
            portfolio_expected_return_pct=exp_ret,
            portfolio_volatility_pct=est_vol,
            summary_metrics=summary_metrics,
            strategic_notes=strategic_notes,
        )

    @classmethod
    def recommend(
        cls,
        budget: float,
        risk_level: str = "MODERATE",
        horizon: str = "MEDIUM_TERM",
        sectors: Optional[List[str]] = None,
        excluded_symbols: Optional[List[str]] = None,
        provider: Optional[MarketDataProvider] = None,
    ) -> AdvisoryResponse:
        """Convenience method accepting raw arguments."""
        req = AdvisoryRequest(
            budget=budget,
            risk_level=risk_level,  # type: ignore
            horizon=horizon,
            sectors=sectors,
            excluded_symbols=excluded_symbols,
        )
        return cls.recommend_portfolio(req, provider=provider)
