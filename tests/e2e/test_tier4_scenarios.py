"""Tier 4: Real-World Application Persona Scenarios Test Suite.

Adheres strictly to the 4-Tier Test Architecture (TEST_INFRA.md § Tier 4):
1. Scenario 1: Young Tech Professional (50M VND, Moderate, 6M, Tech/Banking focus)
2. Scenario 2: Conservative Retiree (200M VND, Conservative, 2Y, Dividend/Defensive focus)
3. Scenario 3: Aggressive Swing Trader (30M VND, Aggressive, 1M, Materials/Securities focus)
4. Scenario 4: Starter Retail Investor (10M VND, Moderate, 3M, Small budget constraint)
5. Scenario 5: High Net Worth Wealth Building (500M VND, Balanced Growth, 1Y, Multi-sector diversification)

Total Test Cases: 5
"""

import pytest
from tests.e2e.client import get_e2e_client

client = get_e2e_client()


def test_scenario1_young_tech_professional():
    """Scenario 1: Young Tech Professional.
    
    Profile:
    - Budget: 50,000,000 VND
    - Risk Profile: Moderate
    - Investment Horizon: 6 months
    - Target Sectors: Technology, Banking
    
    Verifications:
    - Allocates to technology & banking champions (FPT, MBB, TCB)
    - All whole 100-share lots (zero fractional shares)
    - Capital deployment > 70% with safe cash buffer preserved
    - Exact budget conservation: Invested + Cash Remainder == Budget
    """
    budget = 50000000.0
    payload = {
        "budget": budget,
        "risk_level": "MODERATE",
        "horizon": "6_MONTHS",
        "sectors": ["Technology", "Banking"]
    }
    resp = client.post("/api/advisory/recommend", json_data=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["budget_vnd"] == budget
    invested = data["total_invested_vnd"]
    cash = data["cash_remainder_vnd"]

    # Budget conservation
    assert round(invested + cash, 2) == round(budget, 2)
    assert cash >= 0

    # Capital deployment > 70%
    deployment_ratio = invested / budget
    assert deployment_ratio > 0.70, f"Expected >70% capital deployment, got {deployment_ratio * 100:.2f}%"

    # Preserves cash buffer for market friction
    assert data["cash_pct"] >= 5.0, f"Expected >=5% cash buffer, got {data['cash_pct']}%"

    # Strict whole lots & sector validation
    allocations = data["stock_allocations"]
    assert len(allocations) >= 1
    for item in allocations:
        assert item["sector"].upper() in ["TECHNOLOGY", "BANKING"]
        assert item["allocated_shares"] % 100 == 0
        assert item["allocated_shares"] == item["allocated_lots"] * 100
        assert item["allocated_lots"] >= 1


def test_scenario2_conservative_retiree():
    """Scenario 2: Conservative Retiree.
    
    Profile:
    - Budget: 200,000,000 VND
    - Risk Profile: Conservative
    - Investment Horizon: 2 years
    - Target: Capital preservation & defensive dividend blue chips
    
    Verifications:
    - Defensive cash buffer >= 15%
    - Stable large-cap dividend equities (VCB, VNM, FPT, MBB)
    - Low portfolio volatility (< 12%) and solid estimated dividend yield (>= 3.0%)
    - Exact whole 100-share lots and budget conservation
    """
    budget = 200000000.0
    payload = {
        "budget": budget,
        "risk_level": "CONSERVATIVE",
        "horizon": "2_YEARS"
    }
    resp = client.post("/api/advisory/recommend", json_data=payload)
    assert resp.status_code == 200
    data = resp.json()

    invested = data["total_invested_vnd"]
    cash = data["cash_remainder_vnd"]
    cash_pct = data["cash_pct"]

    # Budget conservation
    assert round(invested + cash, 2) == round(budget, 2)

    # Defensive cash allocation >= 15%
    assert cash_pct >= 15.0, f"Conservative portfolio must preserve >= 15% cash, got {cash_pct}%"

    # Metrics verification
    metrics = data["summary_metrics"]
    assert metrics["estimated_volatility_pct"] <= 12.0, (
        f"Conservative volatility must be <= 12%, got {metrics['estimated_volatility_pct']}%"
    )
    assert metrics.get("dividend_yield_est_pct", 0) >= 3.0, (
        f"Conservative dividend yield should be >= 3.0%, got {metrics.get('dividend_yield_est_pct')}%"
    )

    # Equities verification
    allocations = data["stock_allocations"]
    assert len(allocations) >= 2
    for item in allocations:
        assert item["allocated_shares"] % 100 == 0
        assert item["allocated_shares"] == item["allocated_lots"] * 100


def test_scenario3_aggressive_swing_trader():
    """Scenario 3: Aggressive Swing Trader.
    
    Profile:
    - Budget: 30,000,000 VND
    - Risk Profile: Aggressive
    - Investment Horizon: 1 month
    - Target Sectors: High-beta Materials & Securities
    
    Verifications:
    - High capital deployment >= 85%
    - Focus on momentum/beta leaders (HPG, SSI, VND)
    - Take-Profit and Stop-Loss setups ensuring RRR >= 1.5
    - Exact whole 100-share lots
    """
    budget = 30000000.0
    payload = {
        "budget": budget,
        "risk_level": "AGGRESSIVE",
        "horizon": "1_MONTH",
        "sectors": ["Materials", "Securities"]
    }
    resp = client.post("/api/advisory/recommend", json_data=payload)
    assert resp.status_code == 200
    data = resp.json()

    invested = data["total_invested_vnd"]
    cash = data["cash_remainder_vnd"]

    # Budget conservation
    assert round(invested + cash, 2) == round(budget, 2)

    # High capital utilization >= 85%
    utilization_pct = (invested / budget) * 100.0
    assert utilization_pct >= 85.0, f"Aggressive trader utilization must be >= 85%, got {utilization_pct:.2f}%"

    # Validate stock targets & RRR
    allocations = data["stock_allocations"]
    assert len(allocations) >= 1
    for item in allocations:
        assert item["sector"].upper() in ["MATERIALS", "SECURITIES"]
        assert item["allocated_shares"] % 100 == 0

        # Verify trade setup on the stock's prediction endpoint
        sym = item["symbol"]
        pred_resp = client.get(f"/api/stock/prediction/{sym}")
        assert pred_resp.status_code == 200
        pred = pred_resp.json()
        assert pred["trade_setup"]["risk_reward_ratio"] >= 1.5
        assert pred["trade_setup"]["stop_loss"] < item["current_price_vnd"]


def test_scenario4_starter_retail_investor():
    """Scenario 4: Starter Retail Investor.
    
    Profile:
    - Budget: 10,000,000 VND (Small starter capital)
    - Risk Profile: Moderate
    - Investment Horizon: 3 months
    
    Verifications:
    - Excludes expensive stocks where a single 100-share lot exceeds budget (e.g. FPT @ 13.5M/lot)
    - Selects accessible stocks (e.g. MBB, HPG, POW, NVL)
    - Strict 100-share whole lots without exceeding 10M VND budget
    - Invested + Cash Remainder == 10M VND
    """
    budget = 10000000.0
    payload = {
        "budget": budget,
        "risk_level": "MODERATE",
        "horizon": "3_MONTHS"
    }
    resp = client.post("/api/advisory/recommend", json_data=payload)
    assert resp.status_code == 200
    data = resp.json()

    invested = data["total_invested_vnd"]
    cash = data["cash_remainder_vnd"]

    assert round(invested + cash, 2) == round(budget, 2)
    assert invested <= budget
    assert cash >= 0

    allocations = data["stock_allocations"]
    # Check that no stock with lot cost > 10M is selected
    for item in allocations:
        lot_cost = item["current_price_vnd"] * 100
        assert lot_cost <= budget, (
            f"Stock {item['symbol']} lot cost ({lot_cost}) exceeds budget ({budget})"
        )
        assert item["allocated_shares"] % 100 == 0
        assert item["allocated_lots"] >= 1


def test_scenario5_high_net_worth_wealth_building():
    """Scenario 5: High Net Worth Wealth Building.
    
    Profile:
    - Budget: 500,000,000 VND
    - Risk Profile: Balanced Growth (Moderate)
    - Investment Horizon: 1 year
    
    Verifications:
    - Multi-sector diversification across >= 3 distinct sectors
    - Strict concentration cap: no single stock exceeds 35% of total budget
    - Comprehensive strategic execution notes & risk guidance (>= 2 notes)
    - Strict 100-share integer lots and capital conservation
    """
    budget = 500000000.0
    payload = {
        "budget": budget,
        "risk_level": "MODERATE",
        "horizon": "1_YEAR"
    }
    resp = client.post("/api/advisory/recommend", json_data=payload)
    assert resp.status_code == 200
    data = resp.json()

    invested = data["total_invested_vnd"]
    cash = data["cash_remainder_vnd"]
    assert round(invested + cash, 2) == round(budget, 2)

    allocations = data["stock_allocations"]
    assert len(allocations) >= 3, f"High Net Worth portfolio should hold >= 3 stocks, got {len(allocations)}"

    # Multi-sector diversification: >= 3 sectors
    sectors = {item["sector"] for item in allocations}
    assert len(sectors) >= 3, f"Expected >= 3 distinct sectors, got {len(sectors)}: {sectors}"

    # Concentration limit: no single stock > 35% of budget
    for item in allocations:
        weight = item["weight_pct"]
        assert weight <= 35.0, f"Stock {item['symbol']} concentration ({weight}%) exceeds 35% limit"
        assert item["allocated_shares"] % 100 == 0

    # Strategic guidance notes
    notes = data.get("strategic_notes", [])
    assert len(notes) >= 2, f"Expected >= 2 strategic notes, got {len(notes)}"
    for note in notes:
        assert len(note.strip()) >= 15, f"Strategic note too brief: '{note}'"
