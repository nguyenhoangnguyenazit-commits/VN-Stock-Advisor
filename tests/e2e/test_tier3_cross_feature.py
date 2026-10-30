"""Tier 3: Cross-Feature Interactions Test Suite.

Adheres strictly to the 4-Tier Test Architecture (TEST_INFRA.md § Tier 3):
- CF1: Market Data OHLCV -> Technical Indicators Calculation
- CF2: Technical Indicators -> Confluence Scoring -> Signal Generation
- CF3: Indicator Volatility (ATR) -> Prediction Uncertainty Cones (80%/95%)
- CF4: Market Quote -> Trade Target Generation (RRR >= 1.5)
- CF5: Prediction Signals -> Advisory Candidate Universe Filtering
- CF6: Budget Input * Stock Price -> Integer Lot Knapsack Optimization
- CF7: Knapsack Allocation -> Asset Allocation Donut Distribution
- CF8: User Sector Selection -> Final Portfolio Sector Composition
- CF9: Stock State (Ceiling/Floor/Up/Down/Ref) -> UI Badge Color Mapping
- CF10: Full End-to-End Pipeline: Feed -> Analysis -> Prediction -> Advisory

Total Test Cases: >= 10
"""

import pytest
from tests.e2e.client import get_e2e_client
from app.config import STOCK_UNIVERSE

client = get_e2e_client()


def test_cf1_ohlcv_to_technical_indicators_flow():
    """CF1: Verify data continuity from OHLCV history into Technical Indicators calculation."""
    symbol = "FPT"
    hist_resp = client.get(f"/api/stock/history/{symbol}?days=60")
    assert hist_resp.status_code == 200
    bars = hist_resp.json()
    assert len(bars) >= 30, f"Insufficient historical bars: {len(bars)}"

    # Get indicator output
    ind_resp = client.get(f"/api/stock/indicators/{symbol}")
    assert ind_resp.status_code == 200
    indicators = ind_resp.json()

    # The indicator engine's current price must align closely with latest candle close
    latest_close = bars[-1]["close"]
    ind_price = indicators["current_price"]
    price_diff_pct = abs(latest_close - ind_price) / ind_price
    assert price_diff_pct < 0.10, (
        f"Indicator current price ({ind_price}) diverges significantly from latest candle close ({latest_close})"
    )

    # Moving averages must fall within the range of historical prices
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    min_price, max_price = min(lows), max(highs)
    assert min_price <= indicators["sma20"] <= max_price, "SMA20 outside historical price extremes"
    assert min_price <= indicators["ema12"] <= max_price, "EMA12 outside historical price extremes"


def test_cf2_technical_indicators_to_confluence_signal():
    """CF2: Verify multi-indicator aggregation into Confluence Score (-100 to +100) and discrete signal."""
    symbols = ["FPT", "HPG", "SSI", "VCB"]
    for sym in symbols:
        resp = client.get(f"/api/stock/indicators/{sym}")
        assert resp.status_code == 200
        ind = resp.json()

        score = ind["confluence_score"]
        signal = ind["confluence_signal"]

        # Signal coherence with score sign
        if score >= 30.0:
            assert signal in ["BUY", "STRONG_BUY", "ACCUMULATE"], (
                f"Bullish score {score} produced incompatible signal '{signal}' for {sym}"
            )
        elif score <= -30.0:
            assert signal in ["SELL", "STRONG_SELL"], (
                f"Bearish score {score} produced incompatible signal '{signal}' for {sym}"
            )
        else:
            assert signal in ["NEUTRAL", "BUY", "ACCUMULATE", "SELL"], (
                f"Neutral score {score} produced unexpected signal '{signal}' for {sym}"
            )


def test_cf3_atr_volatility_to_prediction_uncertainty_cones():
    """CF3: Verify ATR volatility metric directly influences prediction confidence cone expansion."""
    symbol = "FPT"
    ind_resp = client.get(f"/api/stock/indicators/{symbol}")
    assert ind_resp.status_code == 200
    atr = ind_resp.json()["atr14"]
    assert atr > 0, "ATR14 must be positive"

    pred_resp = client.get(f"/api/stock/prediction/{symbol}")
    assert pred_resp.status_code == 200
    forecasts = pred_resp.json()["forecasts"]

    # 7-day cone width should be proportional to ATR (at least 1.0x ATR for 80% cone)
    f7 = next(f for f in forecasts if f["horizon_days"] == 7)
    cone_width_80_7d = f7["upper_80"] - f7["lower_80"]
    assert cone_width_80_7d >= atr, (
        f"7-day 80% confidence interval width ({cone_width_80_7d}) is unrealistically smaller than daily ATR ({atr})"
    )


def test_cf4_market_quote_to_trade_target_setup():
    """CF4: Verify Market Quote coordinates with Trade Setup targets and preserves RRR >= 1.5."""
    symbol = "FPT"
    quote_resp = client.get(f"/api/stock/quote/{symbol}")
    assert quote_resp.status_code == 200
    quote = quote_resp.json()
    curr_price = quote["price"]

    pred_resp = client.get(f"/api/stock/prediction/{symbol}")
    assert pred_resp.status_code == 200
    setup = pred_resp.json()["trade_setup"]

    entry_min, entry_max = setup["entry_zone"]
    stop_loss = setup["stop_loss"]
    tp1 = setup["take_profit_1"]
    rrr = setup["risk_reward_ratio"]

    # Current price should be proximal to entry zone
    assert entry_min <= curr_price * 1.05 and entry_max >= curr_price * 0.95, (
        f"Entry zone [{entry_min}, {entry_max}] disconnected from current quote {curr_price}"
    )

    # For a long trade setup: Stop Loss < Entry < Take Profit
    assert stop_loss < entry_min, f"Stop loss ({stop_loss}) must be below entry min ({entry_min})"
    assert tp1 > entry_max, f"Take Profit 1 ({tp1}) must be above entry max ({entry_max})"

    # Risk-Reward Ratio validation
    assert rrr >= 1.5, f"Reported RRR ({rrr}) must be >= 1.5"
    tp2 = setup.get("take_profit_2", tp1)
    assert tp2 >= tp1, f"Take Profit 2 ({tp2}) must be >= Take Profit 1 ({tp1})"


def test_cf5_prediction_signals_to_advisory_candidate_selection():
    """CF5: Verify Advisory module prioritizes stocks with positive predictive confluence signals."""
    payload = {
        "budget": 50000000,
        "risk_level": "MODERATE",
        "horizon": "MEDIUM_TERM"
    }
    adv_resp = client.post("/api/advisory/recommend", json_data=payload)
    assert adv_resp.status_code == 200
    recommendations = adv_resp.json()["stock_allocations"]
    assert len(recommendations) > 0

    for item in recommendations:
        sym = item["symbol"]
        pred_resp = client.get(f"/api/stock/prediction/{sym}")
        assert pred_resp.status_code == 200
        pred = pred_resp.json()

        # Advisory should pick actionable bullish/accumulating stocks
        assert pred["signal"] in ["BUY", "STRONG_BUY", "ACCUMULATE", "NEUTRAL"], (
            f"Advisory recommended {sym} despite bearish prediction signal '{pred['signal']}'"
        )


def test_cf6_budget_and_prices_to_knapsack_integer_lots():
    """CF6: Verify Knapsack Optimizer converts budget and stock prices into exact whole-lot allocations."""
    budget = 75000000.0  # 75 Million VND
    payload = {"budget": budget, "risk_level": "MODERATE"}
    resp = client.post("/api/advisory/recommend", json_data=payload)
    assert resp.status_code == 200
    data = resp.json()

    allocations = data["stock_allocations"]
    running_total = 0.0

    for alloc in allocations:
        sym = alloc["symbol"]
        lots = alloc["allocated_lots"]
        shares = alloc["allocated_shares"]
        cost = alloc["total_cost_vnd"]
        price = alloc["current_price_vnd"]

        # Exact whole-lot invariant
        assert lots >= 1, f"Expected at least 1 lot for {sym}"
        assert shares == lots * 100, f"Shares ({shares}) != Lots ({lots}) * 100 for {sym}"
        assert shares % 100 == 0, f"Fractional share detected: {shares} shares for {sym}"

        # Total cost consistency
        expected_cost = shares * price
        assert round(cost, 2) == round(expected_cost, 2), (
            f"Allocated cost ({cost}) != Shares ({shares}) * Price ({price}) for {sym}"
        )
        running_total += cost

    assert round(data["total_invested_vnd"], 2) == round(running_total, 2)
    assert round(data["total_invested_vnd"] + data["cash_remainder_vnd"], 2) == round(budget, 2)


def test_cf7_knapsack_allocation_to_donut_distribution():
    """CF7: Verify mathematical synchronization between stock-level knapsack outputs and asset allocation donut."""
    payload = {"budget": 100000000.0, "risk_level": "MODERATE"}
    resp = client.post("/api/advisory/recommend", json_data=payload)
    assert resp.status_code == 200
    data = resp.json()

    # Sum of stock allocations
    equities_total = sum(s["total_cost_vnd"] for s in data["stock_allocations"])
    cash_total = data["cash_remainder_vnd"]

    # Donut categories
    categories = {cat["category"]: cat for cat in data["asset_allocation"]}
    assert "Equities" in categories, "Equities category missing from asset allocation donut"
    assert "Cash Buffer" in categories, "Cash Buffer category missing from asset allocation donut"

    # Equities value matches stock sum
    assert round(categories["Equities"]["value_vnd"], 2) == round(equities_total, 2)
    # Cash Buffer value matches cash remainder
    assert round(categories["Cash Buffer"]["value_vnd"], 2) == round(cash_total, 2)

    # Percentage total must sum to 100% (+/- 0.1% rounding)
    total_pct = sum(cat["weight_pct"] for cat in data["asset_allocation"])
    assert 99.9 <= total_pct <= 100.1, f"Asset allocation donut weights do not sum to 100%: {total_pct}%"


def test_cf8_user_sector_selection_to_portfolio_composition():
    """CF8: Verify user sector restrictions strictly filter candidates into final portfolio allocations."""
    restricted_sectors = ["Technology", "Banking"]
    payload = {
        "budget": 60000000.0,
        "risk_level": "MODERATE",
        "sectors": restricted_sectors
    }
    resp = client.post("/api/advisory/recommend", json_data=payload)
    assert resp.status_code == 200
    allocations = resp.json()["stock_allocations"]
    assert len(allocations) > 0, "Expected allocations for Banking & Technology sectors"

    for alloc in allocations:
        sym = alloc["symbol"]
        sector = alloc["sector"]
        meta_sector = STOCK_UNIVERSE[sym]["sector"]
        assert any(s.upper() in meta_sector.upper() for s in restricted_sectors), (
            f"Stock {sym} ({meta_sector}) violates sector filter {restricted_sectors}"
        )


def test_cf9_stock_state_to_ui_color_token_mapping():
    """CF9: Verify stock quote states map 1-to-1 to CSS color tokens under Vietnamese market rules."""
    state_to_token = {
        "CEILING": "--color-vn-ceil",
        "FLOOR": "--color-vn-floor",
        "UP": "--color-vn-gain",
        "DOWN": "--color-vn-loss",
        "REF": "--color-vn-ref",
    }
    # Retrieve CSS tokens
    css_resp = client.get("/static/css/style.css")
    assert css_resp.status_code == 200
    css = css_resp.text

    for state, token in state_to_token.items():
        assert token in css, f"State '{state}' lacks corresponding CSS color token '{token}'"

    # Verify quotes emit valid states
    for sym in ["FPT", "VCB", "HPG", "MBB"]:
        q_resp = client.get(f"/api/stock/quote/{sym}")
        assert q_resp.status_code == 200
        assert q_resp.json()["state"] in state_to_token


def test_cf10_full_end_to_end_decision_pipeline():
    """CF10: Full end-to-end user workflow: Indices -> Breadth -> Flow -> Stock Deep Dive -> Advisory."""
    # Step 1: Scan market indices
    indices_resp = client.get("/api/market/indices")
    assert indices_resp.status_code == 200
    indices = indices_resp.json()
    assert len(indices) >= 4

    # Step 2: Check market breadth & foreign flow
    breadth_resp = client.get("/api/market/breadth")
    assert breadth_resp.status_code == 200
    flow_resp = client.get("/api/market/foreign-flow")
    assert flow_resp.status_code == 200

    # Step 3: Select top stock FPT for deep dive
    target_sym = "FPT"
    quote_resp = client.get(f"/api/stock/quote/{target_sym}")
    assert quote_resp.status_code == 200
    assert quote_resp.json()["price"] > 0

    history_resp = client.get(f"/api/stock/history/{target_sym}?days=30")
    assert history_resp.status_code == 200
    assert len(history_resp.json()) >= 20

    ind_resp = client.get(f"/api/stock/indicators/{target_sym}")
    assert ind_resp.status_code == 200

    # Step 4: Examine forecast & trade targets
    pred_resp = client.get(f"/api/stock/prediction/{target_sym}")
    assert pred_resp.status_code == 200
    pred = pred_resp.json()
    assert len(pred["forecasts"]) >= 3
    assert pred["trade_setup"]["risk_reward_ratio"] >= 1.5

    # Step 5: Execute portfolio recommendation
    budget = 80000000.0  # 80 Million VND
    adv_payload = {
        "budget": budget,
        "risk_level": "MODERATE",
        "horizon": "MEDIUM_TERM",
        "sectors": ["Technology", "Banking"]
    }
    adv_resp = client.post("/api/advisory/recommend", json_data=adv_payload)
    assert adv_resp.status_code == 200
    advisory = adv_resp.json()

    # Step 6: Validate holistic plan consistency
    assert advisory["total_invested_vnd"] + advisory["cash_remainder_vnd"] == budget
    assert len(advisory["stock_allocations"]) >= 1
    assert any(s["symbol"] == target_sym for s in advisory["stock_allocations"])
    for stock in advisory["stock_allocations"]:
        assert stock["allocated_shares"] % 100 == 0
        assert stock["allocated_lots"] >= 1
