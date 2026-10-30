"""Comprehensive unit test suite for Milestone 3 (M3_ADVISORY).

Location: tests/unit/test_advisory.py

Verifies:
1. Pydantic Request & Response Model Validation:
   - Positive budget validation, rejection of <= 0, None, string, etc.
   - Risk level normalization (BALANCED -> MODERATE, lowercase) and rejection of invalid values.
   - 100-share whole lot invariants enforced inside StockAllocation model.
   - AssetAllocationItem dual-naming synchronization (category/asset_class, weight_pct/percentage, value_vnd/allocated_vnd).
   - Capital conservation invariant inside AdvisoryResponse validator.
   - Roundtrip JSON serialization and deserialization.
2. 100-Share Whole Lot Invariants (Circular 120/2020/TT-BTC):
   - allocated_shares == allocated_lots * 100
   - allocated_shares % 100 == 0
   - allocated_lots >= 1
   - Zero fractional shares
   - total_cost_vnd == allocated_shares * current_price_vnd
3. Capital Conservation Invariants:
   - total_invested_vnd + cash_remainder_vnd == budget_vnd across 1M, 5M, 10M, 50M, 100M, 500M, 10B
   - cash_remainder_vnd >= 0
   - total_invested_vnd == sum(stock.total_cost_vnd)
   - Asset allocation donut weights sum to 100% (+/- 0.1%)
4. Budget Boundary Tests:
   - Micro budget (1M VND) -> 0 stocks, 100% cash remainder, invested = 0
   - Sub-single-share budget (10k VND) -> 0 stocks, 100% cash
   - Small budget (4M VND) -> unaffordable stocks (FPT @ 13.5M, VCB @ 9.2M) strictly excluded
   - Small budget (10M VND) -> accessible stocks selected within budget
   - Massive budget (10B VND) -> no float overflow, no NaN, no inf, proper lot scaling
5. Risk Profiles & Hierarchy:
   - Cash buffer hierarchy: Conservative cash_pct >= Moderate cash_pct >= Aggressive cash_pct
   - Conservative defensive focus: volatility <= 12%, dividend yield >= 3%
   - Aggressive high utilization: capital deployment >= 85%
   - BALANCED alias produces identical profile to MODERATE
6. Sector Filtering & Graceful Fallbacks:
   - Single sector filter: e.g. Banking -> only Banking stocks
   - Multi-sector filter: e.g. Technology, Materials -> only FPT / HPG
   - Empty sector list [] gracefully falls back to full universe
   - Unmatched sector ["CRYPTO_GAMING"] gracefully falls back without 500
   - Excluded symbols: ["VCB", "FPT"] guaranteed not allocated
7. Non-Functional Guarantees:
   - Strategic notes completeness: >= 2 notes (> 10 chars), stock rationales (> 5 chars)
   - Zero side-effects and idempotency: identical runs produce identical output
   - Execution latency: < 10 ms
   - Thread safety: concurrent multi-threaded execution without race conditions
"""

import concurrent.futures
import json
import math
import sys
import time
import unittest
from pathlib import Path
from typing import List

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.advisory.models import (
    AdvisoryRequest,
    AdvisoryResponse,
    AdvisoryRecommendation,
    StockAllocation,
    AssetAllocationItem,
    SummaryMetrics,
    PortfolioSummaryMetrics,
    RiskLevel,
    InvestmentHorizon,
)
from app.advisory.allocator import AdvisoryEngine
from app.advisory.profiles import (
    normalize_risk_level,
    normalize_horizon,
    resolve_sector_candidates,
    SECTOR_ALIASES,
)
from app.config import STOCK_UNIVERSE, STANDARD_LOT_SIZE
from app.data.provider import MarketDataProvider
from pydantic import ValidationError


class TestAdvisoryPydanticModels(unittest.TestCase):
    """Verifies Pydantic schema validation, edge cases, and JSON roundtrip."""

    def test_advisory_request_valid_defaults(self):
        """1. Valid request accepts standard budget and defaults risk/horizon."""
        req = AdvisoryRequest(budget=50_000_000.0)
        self.assertEqual(req.budget, 50_000_000.0)
        self.assertEqual(req.risk_level, RiskLevel.MODERATE)
        self.assertEqual(req.horizon, "MEDIUM_TERM")
        self.assertIsNone(req.sectors)
        self.assertIsNone(req.excluded_symbols)

    def test_advisory_request_positive_float_and_int(self):
        """2. Integer budget is automatically cast to float."""
        req = AdvisoryRequest(budget=10000000)
        self.assertEqual(req.budget, 10000000.0)
        self.assertIsInstance(req.budget, float)

    def test_advisory_request_reject_zero_budget(self):
        """3. Zero budget must raise ValidationError."""
        with self.assertRaises(ValidationError):
            AdvisoryRequest(budget=0.0)

    def test_advisory_request_reject_negative_budget(self):
        """4. Negative budget must raise ValidationError."""
        with self.assertRaises(ValidationError):
            AdvisoryRequest(budget=-1000000.0)

    def test_advisory_request_reject_none_budget(self):
        """5. None budget must raise ValidationError."""
        with self.assertRaises(ValidationError):
            AdvisoryRequest(budget=None)  # type: ignore

    def test_advisory_request_reject_string_budget(self):
        """6. Non-numeric string budget must raise ValidationError."""
        with self.assertRaises(ValidationError):
            AdvisoryRequest(budget="one_million")  # type: ignore

    def test_advisory_request_risk_level_normalization(self):
        """7. 'BALANCED' aliases to MODERATE, lowercase strings are normalized."""
        req1 = AdvisoryRequest(budget=50_000_000.0, risk_level="BALANCED")  # type: ignore
        self.assertEqual(req1.risk_level, RiskLevel.MODERATE)

        req2 = AdvisoryRequest(budget=50_000_000.0, risk_level="conservative")  # type: ignore
        self.assertEqual(req2.risk_level, RiskLevel.CONSERVATIVE)

        req3 = AdvisoryRequest(budget=50_000_000.0, risk_level="AGGRESSIVE")  # type: ignore
        self.assertEqual(req3.risk_level, RiskLevel.AGGRESSIVE)

    def test_advisory_request_reject_invalid_risk_level(self):
        """8. Unknown risk level raises ValidationError."""
        with self.assertRaises(ValidationError):
            AdvisoryRequest(budget=50_000_000.0, risk_level="YOLO_TRADING")  # type: ignore

    def test_advisory_request_sectors_empty_and_cleaning(self):
        """9. Sectors list strips whitespace and converts empty list to None."""
        req1 = AdvisoryRequest(budget=50_000_000.0, sectors=["  Banking  ", "Technology "])
        self.assertEqual(req1.sectors, ["Banking", "Technology"])

        req2 = AdvisoryRequest(budget=50_000_000.0, sectors=[])
        self.assertIsNone(req2.sectors)

    def test_advisory_request_excluded_symbols_uppercase(self):
        """10. Excluded symbols are converted to uppercase and whitespace stripped."""
        req = AdvisoryRequest(budget=50_000_000.0, excluded_symbols=[" fpt ", "vcb"])
        self.assertEqual(req.excluded_symbols, ["FPT", "VCB"])

    def test_stock_allocation_invariant_validation(self):
        """11. StockAllocation validates whole lot invariants."""
        # Valid allocation
        valid_alloc = StockAllocation(
            symbol="FPT",
            company_name="Công ty Cổ phần FPT",
            sector="Technology",
            current_price_vnd=135000.0,
            allocated_lots=2,
            allocated_shares=200,
            total_cost_vnd=27000000.0,
            weight_pct=54.0,
            signal="BUY",
            target_price_vnd=150000.0,
            expected_return_pct=11.11,
            stop_loss_vnd=127000.0,
            rationale="Leading technology export player with robust earnings growth.",
        )
        self.assertEqual(valid_alloc.allocated_shares, 200)

        # Invalid: shares != lots * 100
        with self.assertRaises(ValidationError):
            StockAllocation(
                symbol="FPT",
                company_name="Công ty Cổ phần FPT",
                sector="Technology",
                current_price_vnd=135000.0,
                allocated_lots=2,
                allocated_shares=250,  # Invalid
                total_cost_vnd=33750000.0,
                weight_pct=54.0,
                signal="BUY",
                target_price_vnd=150000.0,
                expected_return_pct=11.11,
                stop_loss_vnd=127000.0,
                rationale="Invalid lots test.",
            )

        # Invalid: shares % 100 != 0
        with self.assertRaises(ValidationError):
            StockAllocation(
                symbol="FPT",
                company_name="Công ty Cổ phần FPT",
                sector="Technology",
                current_price_vnd=135000.0,
                allocated_lots=1,
                allocated_shares=99,  # Fractional / odd lot
                total_cost_vnd=13365000.0,
                weight_pct=26.7,
                signal="BUY",
                target_price_vnd=150000.0,
                expected_return_pct=11.11,
                stop_loss_vnd=127000.0,
                rationale="Invalid odd lot test.",
            )

    def test_asset_allocation_item_dual_naming(self):
        """12. AssetAllocationItem synchronizes category/asset_class and weight/percentage."""
        item1 = AssetAllocationItem(category="Equities", weight_pct=85.0, value_vnd=42500000.0)
        self.assertEqual(item1.category, "Equities")
        self.assertEqual(item1.asset_class, "Equities")
        self.assertEqual(item1.weight_pct, 85.0)
        self.assertEqual(item1.percentage, 85.0)
        self.assertEqual(item1.value_vnd, 42500000.0)
        self.assertEqual(item1.allocated_vnd, 42500000.0)

        # Reverse initialization via alias names
        item2 = AssetAllocationItem(asset_class="Cash Buffer", percentage=15.0, allocated_vnd=7500000.0)  # type: ignore
        self.assertEqual(item2.category, "Cash Buffer")
        self.assertEqual(item2.asset_class, "Cash Buffer")
        self.assertEqual(item2.weight_pct, 15.0)
        self.assertEqual(item2.value_vnd, 7500000.0)

    def test_advisory_response_serialization_roundtrip(self):
        """13. AdvisoryResponse round-trip serialization to JSON and model reconstruction."""
        resp = AdvisoryResponse(
            budget_vnd=50_000_000.0,
            total_invested_vnd=45_000_000.0,
            cash_remainder_vnd=5_000_000.0,
            cash_pct=10.0,
            risk_level="MODERATE",
            horizon="MEDIUM_TERM",
            stock_allocations=[
                StockAllocation(
                    symbol="MBB",
                    company_name="Ngân hàng TMCP Quân đội",
                    sector="Banking",
                    current_price_vnd=25000.0,
                    allocated_lots=18,
                    allocated_shares=1800,
                    total_cost_vnd=45_000_000.0,
                    weight_pct=90.0,
                    signal="BUY",
                    target_price_vnd=28500.0,
                    expected_return_pct=14.0,
                    stop_loss_vnd=23500.0,
                    rationale="Military bank with top CASA.",
                )
            ],
            asset_allocation=[
                AssetAllocationItem(category="Equities", weight_pct=90.0, value_vnd=45_000_000.0),
                AssetAllocationItem(category="Cash Buffer", weight_pct=10.0, value_vnd=5_000_000.0),
            ],
            portfolio_expected_return_pct=14.0,
            portfolio_volatility_pct=12.0,
            summary_metrics=SummaryMetrics(
                expected_return_pct=14.0,
                estimated_volatility_pct=12.0,
                sharpe_ratio=1.4,
                dividend_yield_est_pct=3.0,
            ),
            strategic_notes=["Strict 100-share integer lot execution.", "Preserves cash buffer."],
        )

        json_str = resp.model_dump_json()
        restored = AdvisoryResponse.model_validate_json(json_str)
        self.assertEqual(restored.budget_vnd, resp.budget_vnd)
        self.assertEqual(restored.total_invested_vnd, resp.total_invested_vnd)
        self.assertEqual(restored.cash_remainder_vnd, resp.cash_remainder_vnd)
        self.assertEqual(len(restored.stock_allocations), 1)
        self.assertEqual(restored.stock_allocations[0].symbol, "MBB")


class TestAdvisoryEngineWholeLotInvariants(unittest.TestCase):
    """Verifies strict 100-share whole lot execution per Circular 120/2020/TT-BTC."""

    def test_100_share_whole_lot_invariant_standard_budget(self):
        """14. 50M VND budget generates only 100-share whole lots."""
        resp = AdvisoryEngine.recommend(budget=50_000_000.0, risk_level="MODERATE")
        self.assertGreater(len(resp.stock_allocations), 0)
        for alloc in resp.stock_allocations:
            self.assertIsInstance(alloc.allocated_lots, int)
            self.assertIsInstance(alloc.allocated_shares, int)
            self.assertGreaterEqual(alloc.allocated_lots, 1)
            self.assertEqual(alloc.allocated_shares, alloc.allocated_lots * 100)
            self.assertEqual(alloc.allocated_shares % 100, 0)

    def test_100_share_whole_lot_invariant_multi_budgets(self):
        """15. Whole-lot invariant holds across varied budget sizes."""
        test_budgets = [5_000_000.0, 15_000_000.0, 75_000_000.0, 150_000_000.0, 500_000_000.0]
        for b in test_budgets:
            resp = AdvisoryEngine.recommend(budget=b, risk_level="MODERATE")
            for alloc in resp.stock_allocations:
                self.assertEqual(alloc.allocated_shares % 100, 0, f"Odd lots for budget {b}: {alloc.allocated_shares}")
                self.assertEqual(alloc.allocated_shares, alloc.allocated_lots * 100)

    def test_zero_fractional_shares_guarantee(self):
        """16. Verify zero fractional shares under any circumstances."""
        resp = AdvisoryEngine.recommend(budget=33_333_333.0, risk_level="AGGRESSIVE")
        for alloc in resp.stock_allocations:
            self.assertEqual(alloc.allocated_shares, int(alloc.allocated_shares))
            self.assertEqual(alloc.allocated_shares % 100, 0)

    def test_stock_cost_formula_exact(self):
        """17. Total cost equals allocated_shares * current_price_vnd."""
        resp = AdvisoryEngine.recommend(budget=80_000_000.0, risk_level="MODERATE")
        for alloc in resp.stock_allocations:
            expected_cost = round(alloc.allocated_shares * alloc.current_price_vnd, 2)
            self.assertEqual(round(alloc.total_cost_vnd, 2), expected_cost)

    def test_weight_pct_consistency(self):
        """18. Individual stock weight_pct matches (total_cost_vnd / budget) * 100."""
        budget = 50_000_000.0
        resp = AdvisoryEngine.recommend(budget=budget, risk_level="MODERATE")
        for alloc in resp.stock_allocations:
            expected_weight = round((alloc.total_cost_vnd / budget) * 100.0, 2)
            self.assertEqual(alloc.weight_pct, expected_weight)


class TestAdvisoryEngineCapitalConservation(unittest.TestCase):
    """Verifies capital conservation: total_invested + cash_remainder == budget."""

    def test_capital_conservation_multi_budget_spectrum(self):
        """19. Invested + Cash Remainder == Budget across full spectrum and all risk tiers."""
        budgets = [
            1_000_000.0,
            4_000_000.0,
            10_000_000.0,
            25_000_000.0,
            50_000_000.0,
            54_000_000.0,
            55_000_000.0,
            56_000_000.0,
            56_547_167.32,
            60_000_000.0,
            65_000_000.0,
            68_000_000.0,
            70_000_000.0,
            75_432_100.0,
            76_000_000.0,
            100_000_000.0,
            200_000_000.0,
            500_000_000.0,
            10_000_000_000.0,
        ]
        for risk in ["CONSERVATIVE", "MODERATE", "AGGRESSIVE"]:
            for b in budgets:
                resp = AdvisoryEngine.recommend(budget=b, risk_level=risk)
                calculated_sum = round(resp.total_invested_vnd + resp.cash_remainder_vnd, 2)
                self.assertEqual(calculated_sum, round(b, 2), f"Capital conservation failed for {b} under {risk}")
                self.assertLessEqual(resp.total_invested_vnd, b, f"Invested exceeds budget {b} under {risk}")
                self.assertGreaterEqual(resp.cash_remainder_vnd, 0.0, f"Negative cash remainder for {b} under {risk}")
                equities_item = next(a for a in resp.asset_allocation if a.category == "Equities")
                self.assertLessEqual(equities_item.weight_pct, 100.0)
                self.assertGreaterEqual(equities_item.weight_pct, 0.0)

    def test_aggressive_retail_budget_spectrum_no_overflow(self):
        """19b. Explicit regression test: Aggressive profile across retail spectrum has zero over-allocation and non-negative cash."""
        failing_spectrum = [
            54_000_000.0, 55_000_000.0, 56_000_000.0, 56_072_818.73, 56_547_167.32,
            60_000_000.0, 65_000_000.0, 70_000_000.0, 72_000_000.0, 75_432_100.0, 76_000_000.0
        ]
        for b in failing_spectrum:
            resp = AdvisoryEngine.recommend(budget=b, risk_level="AGGRESSIVE")
            self.assertLessEqual(resp.total_invested_vnd, b, f"Over-allocation detected: {resp.total_invested_vnd} > {b}")
            self.assertGreaterEqual(resp.cash_remainder_vnd, 0.0, f"Negative cash remainder: {resp.cash_remainder_vnd}")
            self.assertEqual(round(resp.total_invested_vnd + resp.cash_remainder_vnd, 2), round(b, 2))
            equities_item = next(a for a in resp.asset_allocation if a.category == "Equities")
            self.assertLessEqual(equities_item.weight_pct, 100.0)
            self.assertGreaterEqual(equities_item.weight_pct, 0.0)

    def test_non_negative_cash_remainder(self):
        """20. Cash remainder is strictly non-negative."""
        resp = AdvisoryEngine.recommend(budget=45_000_000.0, risk_level="AGGRESSIVE")
        self.assertGreaterEqual(resp.cash_remainder_vnd, 0.0)
        self.assertLessEqual(resp.total_invested_vnd, 45_000_000.0)

    def test_total_invested_equals_sum_of_stocks(self):
        """21. Total invested equals sum of individual stock total_cost_vnd."""
        resp = AdvisoryEngine.recommend(budget=70_000_000.0, risk_level="CONSERVATIVE")
        sum_costs = sum(alloc.total_cost_vnd for alloc in resp.stock_allocations)
        self.assertEqual(round(resp.total_invested_vnd, 2), round(sum_costs, 2))

    def test_cash_pct_formula_exact(self):
        """22. Cash pct matches round((cash_remainder_vnd / budget) * 100, 2)."""
        budget = 60_000_000.0
        resp = AdvisoryEngine.recommend(budget=budget, risk_level="MODERATE")
        expected_cash_pct = round((resp.cash_remainder_vnd / budget) * 100.0, 2)
        self.assertEqual(resp.cash_pct, expected_cash_pct)

    def test_asset_allocation_donut_sum_matches_budget(self):
        """23. Asset allocation categories sum to 100% and match values."""
        budget = 90_000_000.0
        resp = AdvisoryEngine.recommend(budget=budget, risk_level="MODERATE")
        total_weight = sum(cat.weight_pct for cat in resp.asset_allocation)
        self.assertAlmostEqual(total_weight, 100.0, delta=0.1)

        donut_dict = {cat.category: cat.value_vnd for cat in resp.asset_allocation}
        self.assertEqual(round(donut_dict["Equities"], 2), round(resp.total_invested_vnd, 2))
        self.assertEqual(round(donut_dict["Cash Buffer"], 2), round(resp.cash_remainder_vnd, 2))


class TestAdvisoryEngineBudgetBoundaries(unittest.TestCase):
    """Verifies edge-case budgets: micro, small, and massive institutional."""

    def test_micro_budget_1m_vnd_no_purchase(self):
        """24. Micro budget (1M VND) cannot purchase any 100-share lot -> 100% cash."""
        resp = AdvisoryEngine.recommend(budget=1_000_000.0, risk_level="MODERATE")
        self.assertEqual(resp.budget_vnd, 1_000_000.0)
        self.assertEqual(resp.total_invested_vnd, 0.0)
        self.assertEqual(resp.cash_remainder_vnd, 1_000_000.0)
        self.assertEqual(resp.cash_pct, 100.0)
        self.assertEqual(len(resp.stock_allocations), 0)

    def test_micro_budget_below_lowest_stock_lot(self):
        """25. 500k VND budget is completely retained in cash."""
        resp = AdvisoryEngine.recommend(budget=500_000.0, risk_level="AGGRESSIVE")
        self.assertEqual(resp.total_invested_vnd, 0.0)
        self.assertEqual(resp.cash_pct, 100.0)
        self.assertEqual(len(resp.stock_allocations), 0)

    def test_small_budget_4m_vnd_selective_filtering(self):
        """26. Small budget (4M VND) excludes expensive stocks (FPT @ 13.5M, VCB @ 9.2M)."""
        resp = AdvisoryEngine.recommend(budget=4_000_000.0, risk_level="MODERATE")
        self.assertLessEqual(resp.total_invested_vnd, 4_000_000.0)
        for alloc in resp.stock_allocations:
            lot_cost = alloc.current_price_vnd * 100
            self.assertLessEqual(lot_cost, 4_000_000.0, f"{alloc.symbol} lot exceeds 4M")
            self.assertNotIn(alloc.symbol, ["FPT", "VCB", "GAS", "MWG"])

    def test_small_budget_10m_vnd_filtering(self):
        """27. 10M VND budget excludes FPT (13.5M/lot) and picks accessible stocks."""
        resp = AdvisoryEngine.recommend(budget=10_000_000.0, risk_level="MODERATE")
        self.assertLessEqual(resp.total_invested_vnd, 10_000_000.0)
        allocated_symbols = [a.symbol for a in resp.stock_allocations]
        self.assertNotIn("FPT", allocated_symbols)
        for alloc in resp.stock_allocations:
            self.assertLessEqual(alloc.current_price_vnd * 100, 10_000_000.0)

    def test_massive_budget_10b_vnd_no_overflow(self):
        """28. Massive institutional budget (10B VND) scales without overflow or NaN."""
        resp = AdvisoryEngine.recommend(budget=10_000_000_000.0, risk_level="AGGRESSIVE")
        self.assertEqual(resp.budget_vnd, 10_000_000_000.0)
        self.assertGreater(resp.total_invested_vnd, 0.0)
        self.assertEqual(round(resp.total_invested_vnd + resp.cash_remainder_vnd, 2), 10_000_000_000.0)
        for alloc in resp.stock_allocations:
            self.assertGreater(alloc.allocated_lots, 0)
            self.assertEqual(alloc.allocated_shares, alloc.allocated_lots * 100)
            self.assertFalse(math.isnan(alloc.total_cost_vnd))
            self.assertFalse(math.isinf(alloc.total_cost_vnd))


class TestAdvisoryEngineRiskProfiles(unittest.TestCase):
    """Verifies risk tier differentiation: Conservative vs Moderate vs Aggressive."""

    def test_risk_tier_cash_buffer_hierarchy(self):
        """29. Conservative cash_pct >= Moderate cash_pct >= Aggressive cash_pct."""
        budget = 50_000_000.0
        resp_cons = AdvisoryEngine.recommend(budget=budget, risk_level="CONSERVATIVE")
        resp_mod = AdvisoryEngine.recommend(budget=budget, risk_level="MODERATE")
        resp_aggr = AdvisoryEngine.recommend(budget=budget, risk_level="AGGRESSIVE")

        self.assertGreaterEqual(resp_cons.cash_pct, resp_mod.cash_pct)
        self.assertGreaterEqual(resp_mod.cash_pct, resp_aggr.cash_pct)
        self.assertGreaterEqual(resp_cons.cash_pct, 15.0, "Conservative cash buffer must be >= 15%")

    def test_conservative_defensive_picks(self):
        """30. Conservative portfolio achieves low volatility (<= 12%) and dividend yield >= 3%."""
        resp = AdvisoryEngine.recommend(budget=200_000_000.0, risk_level="CONSERVATIVE", horizon="2_YEARS")
        self.assertLessEqual(resp.summary_metrics.estimated_volatility_pct, 12.0)
        self.assertGreaterEqual(resp.summary_metrics.dividend_yield_est_pct, 3.0)

    def test_aggressive_high_utilization(self):
        """31. Aggressive portfolio achieves >= 85% capital utilization."""
        budget = 30_000_000.0
        resp = AdvisoryEngine.recommend(budget=budget, risk_level="AGGRESSIVE", horizon="1_MONTH")
        utilization = (resp.total_invested_vnd / budget) * 100.0
        self.assertGreaterEqual(utilization, 85.0)

    def test_balanced_profile_alias(self):
        """32. 'BALANCED' generates identical result to 'MODERATE'."""
        budget = 50_000_000.0
        resp_bal = AdvisoryEngine.recommend(budget=budget, risk_level="BALANCED")
        resp_mod = AdvisoryEngine.recommend(budget=budget, risk_level="MODERATE")
        self.assertEqual(resp_bal.total_invested_vnd, resp_mod.total_invested_vnd)
        self.assertEqual(resp_bal.cash_remainder_vnd, resp_mod.cash_remainder_vnd)


class TestAdvisoryEngineSectorAndSymbolFiltering(unittest.TestCase):
    """Verifies sector filtering, empty/unmatched fallback, and symbol exclusion."""

    def test_single_sector_filter(self):
        """33. Requesting Banking sector exclusively selects Banking stocks."""
        resp = AdvisoryEngine.recommend(budget=60_000_000.0, sectors=["Banking"])
        self.assertGreater(len(resp.stock_allocations), 0)
        for alloc in resp.stock_allocations:
            self.assertEqual(alloc.sector, "Banking")

    def test_multi_sector_filter(self):
        """34. Requesting Technology and Banking selects only from those sectors."""
        resp = AdvisoryEngine.recommend(budget=50_000_000.0, sectors=["Technology", "Banking"])
        self.assertGreater(len(resp.stock_allocations), 0)
        for alloc in resp.stock_allocations:
            self.assertIn(alloc.sector, ["Technology", "Banking"])

    def test_empty_sector_list_graceful_fallback(self):
        """35. Empty sector list [] falls back to full universe without error."""
        resp = AdvisoryEngine.recommend(budget=50_000_000.0, sectors=[])
        self.assertGreater(len(resp.stock_allocations), 0)

    def test_unmatched_sector_graceful_fallback(self):
        """36. Non-existent sector ['CRYPTO_GAMING'] falls back gracefully."""
        resp = AdvisoryEngine.recommend(budget=50_000_000.0, sectors=["CRYPTO_GAMING"])
        self.assertGreater(len(resp.stock_allocations), 0)

    def test_excluded_symbols_filtering(self):
        """37. Excluded symbols (e.g. FPT, VCB) are guaranteed not allocated."""
        resp = AdvisoryEngine.recommend(budget=100_000_000.0, excluded_symbols=["FPT", "VCB"])
        symbols = [a.symbol for a in resp.stock_allocations]
        self.assertNotIn("FPT", symbols)
        self.assertNotIn("VCB", symbols)


class TestAdvisoryEngineNonFunctionalGuarantees(unittest.TestCase):
    """Verifies strategic notes, zero side-effects, latency, and thread safety."""

    def test_strategic_notes_and_rationale_completeness(self):
        """38. Comprehensive strategic notes (>= 2) and stock rationales."""
        resp = AdvisoryEngine.recommend(budget=50_000_000.0, risk_level="MODERATE")
        self.assertGreaterEqual(len(resp.strategic_notes), 2)
        for note in resp.strategic_notes:
            self.assertGreater(len(note.strip()), 10)

        for alloc in resp.stock_allocations:
            self.assertGreater(len(alloc.rationale.strip()), 5)

    def test_zero_side_effects_idempotency(self):
        """39. Idempotency: multiple calls with identical input produce identical output."""
        req = AdvisoryRequest(budget=50_000_000.0, risk_level="MODERATE")
        resp1 = AdvisoryEngine.recommend_portfolio(req)
        resp2 = AdvisoryEngine.recommend_portfolio(req)
        self.assertEqual(resp1.model_dump(), resp2.model_dump())

    def test_sub_10ms_latency(self):
        """40. Advisory optimization executes within < 10 ms SLA."""
        req = AdvisoryRequest(budget=50_000_000.0, risk_level="MODERATE")
        # Warmup
        AdvisoryEngine.recommend_portfolio(req)

        start = time.perf_counter()
        AdvisoryEngine.recommend_portfolio(req)
        duration_ms = (time.perf_counter() - start) * 1000.0
        self.assertLess(duration_ms, 10.0, f"Execution took {duration_ms:.2f} ms (expected < 10 ms)")

    def test_thread_safety_concurrent_execution(self):
        """41. Concurrent execution across 10 threads yields valid, identical results."""
        req = AdvisoryRequest(budget=50_000_000.0, risk_level="MODERATE")

        def task():
            return AdvisoryEngine.recommend_portfolio(req)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(task) for _ in range(10)]
            results = [f.result() for f in futures]

        first_dump = results[0].model_dump()
        for res in results[1:]:
            self.assertEqual(res.model_dump(), first_dump)


if __name__ == "__main__":
    unittest.main()
