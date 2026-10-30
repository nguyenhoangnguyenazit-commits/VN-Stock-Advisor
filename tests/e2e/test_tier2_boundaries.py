"""Tier 2: Boundary & Corner Cases Test Suite.

Adheres strictly to the 4-Tier Test Architecture (TEST_INFRA.md):
- Requirement R1: Web Application & API Boundaries (R1.B1 - R1.B5)
- Requirement R2: Market Data & Exchange Price Band Boundaries (R2.B1 - R2.B5)
- Requirement R3: Technical Engine & Statistical Forecast Boundaries (R3.B1 - R3.B5)
- Requirement R4: Knapsack Optimizer & Budget Boundary Extremes (R4.B1 - R4.B5)
- Requirement R5: UI/UX & Formatting Boundary Invariants (R5.B1 - R5.B5)

Total Test Cases: >= 25
"""

import math
import re
import pytest
from tests.e2e.client import get_e2e_client
from app.config import STOCK_UNIVERSE

client = get_e2e_client()


# ==============================================================================
# R1 Boundaries: Interactive Web Application & API Infrastructure
# ==============================================================================

def test_r1_b1_path_traversal_prevention():
    """R1.B1: Verify security resistance against directory traversal attacks."""
    traversal_paths = [
        "/static/../app/config.py",
        "/static/../../PROJECT.md",
        "/static/../..//data/seeds/market_snapshot.json",
        "/static/..%2f..%2fapp/main.py",
    ]
    for path in traversal_paths:
        resp = client.get(path)
        assert resp.status_code in [403, 404], (
            f"Directory traversal path '{path}' should return 403 or 404, got {resp.status_code}"
        )
        assert "password" not in resp.text.lower()
        assert "api_key" not in resp.text.lower()


def test_r1_b2_nonexistent_endpoint_404():
    """R1.B2: Verify non-existent API endpoints return structured 404 Not Found."""
    nonexistent_paths = [
        "/api/nonexistent_endpoint",
        "/api/market/invalid_subroute_xyz",
        "/api/stock/unknown_category/FPT",
    ]
    for path in nonexistent_paths:
        resp = client.get(path)
        assert resp.status_code == 404, f"Expected 404 for '{path}', got {resp.status_code}"
        data = resp.json()
        assert "detail" in data, f"404 response for '{path}' should contain detail message"


def test_r1_b3_unsupported_http_methods_405():
    """R1.B3: Verify read-only endpoints reject write/mutation verbs with 405 Method Not Allowed."""
    # POST to read-only market index
    post_resp = client.post("/api/market/indices", json_data={"data": 123})
    assert post_resp.status_code == 405, f"POST /api/market/indices should return 405, got {post_resp.status_code}"

    # DELETE to stock quote
    del_resp = client.delete("/api/stock/quote/FPT")
    assert del_resp.status_code == 405, f"DELETE /api/stock/quote/FPT should return 405, got {del_resp.status_code}"

    # GET to advisory POST endpoint
    get_adv_resp = client.get("/api/advisory/recommend")
    assert get_adv_resp.status_code == 405, f"GET /api/advisory/recommend should return 405, got {get_adv_resp.status_code}"


def test_r1_b4_malformed_payload_and_empty_body_422():
    """R1.B4: Verify advisory endpoint rejects malformed JSON or empty body with 422 Unprocessable Entity."""
    # None / Empty body
    resp_empty = client.post("/api/advisory/recommend", json_data=None)
    assert resp_empty.status_code == 422, f"Expected 422 for empty body, got {resp_empty.status_code}"

    # Empty dictionary
    resp_dict = client.post("/api/advisory/recommend", json_data={})
    assert resp_dict.status_code == 422, f"Expected 422 for empty json dict, got {resp_dict.status_code}"

    # Wrong data types
    resp_type = client.post("/api/advisory/recommend", json_data={"budget": "not_a_number"})
    assert resp_type.status_code == 422, f"Expected 422 for string budget, got {resp_type.status_code}"


def test_r1_b5_nonexistent_static_asset_404():
    """R1.B5: Verify non-existent static assets return 404 without crashing."""
    resp = client.get("/static/vendor/non_existent_library_99.js")
    assert resp.status_code == 404, f"Expected 404 for missing static file, got {resp.status_code}"


# ==============================================================================
# R2 Boundaries: Market Data & Exchange Price Band Boundaries
# ==============================================================================

def test_r2_b1_unknown_stock_symbol_404():
    """R2.B1: Verify unknown or unlisted stock symbols return 404 Not Found across all endpoints."""
    invalid_symbols = ["INVALID99", "UNKNOWN123", "NONEXISTENT"]
    for sym in invalid_symbols:
        quote_resp = client.get(f"/api/stock/quote/{sym}")
        assert quote_resp.status_code == 404, f"Quote for '{sym}' should return 404, got {quote_resp.status_code}"

        ind_resp = client.get(f"/api/stock/indicators/{sym}")
        assert ind_resp.status_code == 404, f"Indicators for '{sym}' should return 404, got {ind_resp.status_code}"

        pred_resp = client.get(f"/api/stock/prediction/{sym}")
        assert pred_resp.status_code == 404, f"Prediction for '{sym}' should return 404, got {pred_resp.status_code}"


def test_r2_b2_extreme_history_days_parameter():
    """R2.B2: Verify history days parameter boundaries (zero, negative, extreme high)."""
    # Zero days -> 422
    resp_zero = client.get("/api/stock/history/FPT?days=0")
    assert resp_zero.status_code == 422, f"Expected 422 for days=0, got {resp_zero.status_code}"

    # Negative days -> 422
    resp_neg = client.get("/api/stock/history/FPT?days=-15")
    assert resp_neg.status_code == 422, f"Expected 422 for negative days, got {resp_neg.status_code}"

    # Non-integer days -> 422
    resp_str = client.get("/api/stock/history/FPT?days=abc")
    assert resp_str.status_code == 422, f"Expected 422 for non-integer days, got {resp_str.status_code}"

    # Extreme high days -> safely capped (<= 365) without memory exhaustion
    resp_large = client.get("/api/stock/history/FPT?days=9999")
    assert resp_large.status_code == 200, f"Expected 200 for days=9999, got {resp_large.status_code}"
    bars = resp_large.json()
    assert len(bars) <= 365, f"History should be safely capped at 365 days, got {len(bars)}"


def test_r2_b3_price_band_ceiling_floor_boundary_limits():
    """R2.B3: Verify Vietnamese daily price band constraints: Floor < Ref < Ceiling."""
    symbols = list(STOCK_UNIVERSE.keys())
    for sym in symbols:
        resp = client.get(f"/api/stock/quote/{sym}")
        assert resp.status_code == 200
        quote = resp.json()

        ref = quote["ref_price"]
        ceil = quote["ceiling_price"]
        floor = quote["floor_price"]
        price = quote["price"]

        # Circular 120/2020/TT-BTC HOSE (+/- 7%)
        assert ceil > ref, f"{sym}: Ceiling price {ceil} must be strictly greater than ref {ref}"
        assert floor < ref, f"{sym}: Floor price {floor} must be strictly less than ref {ref}"
        assert ceil > floor, f"{sym}: Ceiling {ceil} must be strictly greater than floor {floor}"
        assert floor <= price <= ceil, f"{sym}: Current price {price} must be within [{floor}, {ceil}]"

        # Validate discrete state token
        assert quote["state"] in ["CEILING", "FLOOR", "UP", "DOWN", "REF"]


def test_r2_b4_symbol_case_insensitivity_normalization():
    """R2.B4: Verify ticker endpoints accept lower-case and mixed-case symbols gracefully."""
    test_cases = ["fpt", "Fpt", "hpg", "Hpg", "mbb"]
    for sym in test_cases:
        resp = client.get(f"/api/stock/quote/{sym}")
        assert resp.status_code == 200, f"Expected 200 for '{sym}', got {resp.status_code}"
        quote = resp.json()
        assert quote["symbol"] == sym.upper(), f"Symbol '{sym}' should be normalized to uppercase '{quote['symbol']}'"


def test_r2_b5_foreign_flow_extreme_bounds():
    """R2.B5: Verify foreign flow feed records are bounded and adhere to foreign ownership rules."""
    resp = client.get("/api/market/foreign-flow")
    assert resp.status_code == 200
    data = resp.json()

    assert not math.isnan(data["net_value_vnd"])
    assert not math.isinf(data["net_value_vnd"])

    for record in data["records"]:
        assert 0.0 <= record.get("foreign_ratio", 0.0) <= 100.0, f"Foreign ratio out of bounds: {record}"
        assert record.get("room_left", 0) >= 0, f"Room left cannot be negative: {record}"
        assert not math.isnan(record["net_value_vnd"])


# ==============================================================================
# R3 Boundaries: Technical Indicators & Trend Prediction Engine
# ==============================================================================

def test_r3_b1_rsi_oscillator_strict_bounds():
    """R3.B1: Verify RSI-14 oscillator is strictly confined between 0.0 and 100.0."""
    tickers = ["FPT", "HPG", "SSI", "VCB", "MWG"]
    for sym in tickers:
        resp = client.get(f"/api/stock/indicators/{sym}")
        assert resp.status_code == 200
        ind = resp.json()
        rsi = ind.get("rsi14")
        assert rsi is not None, f"{sym}: Missing rsi14"
        assert not math.isnan(rsi) and not math.isinf(rsi), f"{sym}: RSI must be a valid float"
        assert 0.0 <= rsi <= 100.0, f"{sym}: RSI {rsi} must be strictly between 0 and 100"


def test_r3_b2_bollinger_bands_ordering_and_non_negative_width():
    """R3.B2: Verify Bollinger Bands invariant: Upper Band >= Middle Band >= Lower Band."""
    tickers = ["FPT", "HPG", "VNM", "TCB"]
    for sym in tickers:
        resp = client.get(f"/api/stock/indicators/{sym}")
        assert resp.status_code == 200
        bb = resp.json()["bollinger"]

        upper = bb["upper"]
        middle = bb["middle"]
        lower = bb["lower"]

        assert upper >= middle, f"{sym}: Upper BB ({upper}) must be >= Middle BB ({middle})"
        assert middle >= lower, f"{sym}: Middle BB ({middle}) must be >= Lower BB ({lower})"
        assert upper - lower >= 0, f"{sym}: Bollinger bandwidth must be non-negative"


def test_r3_b3_confluence_score_normalization_limits():
    """R3.B3: Verify confluence score is clamped to [-100.0, +100.0] and confidence to [0, 100]."""
    tickers = ["FPT", "HPG", "SSI", "MBB"]
    valid_signals = {"STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL", "ACCUMULATE"}

    for sym in tickers:
        resp_ind = client.get(f"/api/stock/indicators/{sym}")
        assert resp_ind.status_code == 200
        ind = resp_ind.json()
        conf_score = ind["confluence_score"]
        assert -100.0 <= conf_score <= 100.0, f"{sym}: Confluence score {conf_score} outside [-100, 100]"
        assert ind["confluence_signal"] in valid_signals

        resp_pred = client.get(f"/api/stock/prediction/{sym}")
        assert resp_pred.status_code == 200
        pred = resp_pred.json()
        conf = pred["confidence_score"]
        assert 0.0 <= conf <= 100.0, f"{sym}: Confidence score {conf} outside [0, 100]"


def test_r3_b4_forecast_confidence_cones_monotonic_expansion():
    """R3.B4: Verify prediction confidence cones expand monotonically with forecast horizon."""
    resp = client.get("/api/stock/prediction/FPT")
    assert resp.status_code == 200
    forecasts = resp.json()["forecasts"]

    sorted_forecasts = sorted(forecasts, key=lambda x: x["horizon_days"])
    prev_width_80 = 0.0
    prev_width_95 = 0.0

    for f in sorted_forecasts:
        u80, l80 = f["upper_80"], f["lower_80"]
        u95, l95 = f["upper_95"], f["lower_95"]
        target = f["target_price"]

        # Strict band nesting: Lower 95 <= Lower 80 <= Target <= Upper 80 <= Upper 95
        assert l95 <= l80 <= target <= u80 <= u95, (
            f"Interval nesting violation at {f['horizon_days']}d: [{l95}, {l80}, {target}, {u80}, {u95}]"
        )

        width_80 = u80 - l80
        width_95 = u95 - l95
        assert width_95 >= width_80, f"95% cone width ({width_95}) must be >= 80% cone width ({width_80})"

        # Uncertainty expands or remains stable over time
        assert width_80 >= prev_width_80, f"80% cone should expand over horizon: {width_80} < {prev_width_80}"
        assert width_95 >= prev_width_95, f"95% cone should expand over horizon: {width_95} < {prev_width_95}"

        prev_width_80 = width_80
        prev_width_95 = width_95


def test_r3_b5_support_resistance_pivots_and_trade_setup_rrr():
    """R3.B5: Verify pivot level monotonicity (S2 <= S1 <= R1 <= R2) and trade setup RRR >= 1.5."""
    tickers = ["FPT", "HPG", "MWG", "TCB"]
    for sym in tickers:
        resp = client.get(f"/api/stock/prediction/{sym}")
        assert resp.status_code == 200
        data = resp.json()

        sr = data["support_resistance"]
        assert sr["s2"] <= sr["s1"], f"{sym}: S2 ({sr['s2']}) > S1 ({sr['s1']})"
        assert sr["s1"] <= sr["r1"], f"{sym}: S1 ({sr['s1']}) > R1 ({sr['r1']})"
        assert sr["r1"] <= sr["r2"], f"{sym}: R1 ({sr['r1']}) > R2 ({sr['r2']})"

        setup = data["trade_setup"]
        entry_low, entry_high = setup["entry_zone"]
        assert entry_low <= entry_high, f"{sym}: Entry zone low ({entry_low}) > high ({entry_high})"
        assert setup["stop_loss"] < entry_low, f"{sym}: Stop loss ({setup['stop_loss']}) must be < entry low ({entry_low})"
        assert setup["take_profit_1"] > entry_high, f"{sym}: TP1 ({setup['take_profit_1']}) must be > entry high ({entry_high})"
        assert setup["risk_reward_ratio"] >= 1.5, f"{sym}: RRR {setup['risk_reward_ratio']} must be >= 1.5"


# ==============================================================================
# R4 Boundaries: Knapsack Optimizer & Budget Boundary Extremes
# ==============================================================================

def test_r4_b1_micro_budget_below_single_lot_cost():
    """R4.B1: Verify micro-budget (1M VND) where no 100-share whole lot can be purchased."""
    micro_budget = 1000000.0  # 1 Million VND
    payload = {"budget": micro_budget, "risk_level": "MODERATE"}
    resp = client.post("/api/advisory/recommend", json_data=payload)

    assert resp.status_code == 200, f"Expected 200 OK for micro budget, got {resp.status_code}"
    data = resp.json()

    assert data["budget_vnd"] == micro_budget
    assert data["total_invested_vnd"] == 0.0, "Invested capital must be 0 when no lot can be bought"
    assert data["cash_remainder_vnd"] == micro_budget, "Cash remainder must equal budget"
    assert data["cash_pct"] == 100.0, "Cash percentage must be 100%"
    assert len(data["stock_allocations"]) == 0, "No stock allocations should be generated"


def test_r4_b2_small_budget_selective_lot_filtering():
    """R4.B2: Verify small budget (4M VND) automatically filters out unaffordable high-price stocks."""
    small_budget = 4000000.0  # 4 Million VND
    payload = {"budget": small_budget, "risk_level": "MODERATE"}
    resp = client.post("/api/advisory/recommend", json_data=payload)

    assert resp.status_code == 200
    data = resp.json()

    assert data["total_invested_vnd"] <= small_budget
    assert data["cash_remainder_vnd"] >= 0
    assert round(data["total_invested_vnd"] + data["cash_remainder_vnd"], 2) == round(small_budget, 2)

    # Expensive stocks (like FPT @ 135k = 13.5M/lot, VCB @ 92k = 9.2M/lot) must NEVER be allocated
    for stock in data["stock_allocations"]:
        lot_cost = stock["current_price_vnd"] * 100
        assert lot_cost <= small_budget, f"Stock {stock['symbol']} lot cost ({lot_cost}) exceeds budget ({small_budget})"
        assert stock["allocated_shares"] % 100 == 0


def test_r4_b3_massive_institutional_budget_no_overflow():
    """R4.B3: Verify massive institutional budget (10 Billion VND) executes without numeric overflow."""
    huge_budget = 10000000000.0  # 10 Billion VND
    payload = {
        "budget": huge_budget,
        "risk_level": "AGGRESSIVE",
        "horizon": "LONG_TERM"
    }
    resp = client.post("/api/advisory/recommend", json_data=payload)

    assert resp.status_code == 200
    data = resp.json()

    assert data["budget_vnd"] == huge_budget
    assert data["total_invested_vnd"] > 0
    assert data["cash_remainder_vnd"] >= 0
    assert round(data["total_invested_vnd"] + data["cash_remainder_vnd"], 2) == round(huge_budget, 2)

    for stock in data["stock_allocations"]:
        assert stock["allocated_lots"] > 0
        assert stock["allocated_shares"] == stock["allocated_lots"] * 100
        assert not math.isnan(stock["total_cost_vnd"])
        assert not math.isinf(stock["total_cost_vnd"])


def test_r4_b4_invalid_zero_and_negative_budgets_rejected():
    """R4.B4: Verify non-positive, zero, and malformed budgets are rejected with 422."""
    invalid_budgets = [0, -100000, -1, "zero", None]
    for b in invalid_budgets:
        payload = {"budget": b, "risk_level": "MODERATE"}
        resp = client.post("/api/advisory/recommend", json_data=payload)
        assert resp.status_code == 422, f"Expected 422 for budget={b}, got {resp.status_code}"


def test_r4_b5_unknown_risk_level_and_empty_sector_filtering():
    """R4.B5: Verify invalid risk profile returns 422, while empty or unmatched sector gracefully falls back."""
    # Invalid risk profile -> 422
    resp_invalid_risk = client.post("/api/advisory/recommend", json_data={"budget": 50000000, "risk_level": "YOLO_TRADING"})
    assert resp_invalid_risk.status_code == 422, f"Expected 422 for invalid risk, got {resp_invalid_risk.status_code}"

    # Empty sector list -> graceful fallback to full universe
    resp_empty_sec = client.post("/api/advisory/recommend", json_data={"budget": 50000000, "sectors": []})
    assert resp_empty_sec.status_code == 200, f"Empty sector list should return 200, got {resp_empty_sec.status_code}"
    assert len(resp_empty_sec.json()["stock_allocations"]) > 0

    # Non-matching sector list -> graceful fallback to universe without 500
    resp_unmatched_sec = client.post("/api/advisory/recommend", json_data={"budget": 50000000, "sectors": ["CRYPTO_GAMING"]})
    assert resp_unmatched_sec.status_code == 200, f"Unmatched sector should gracefully fallback, got {resp_unmatched_sec.status_code}"


# ==============================================================================
# R5 Boundaries: UI/UX & Formatting Boundary Invariants
# ==============================================================================

def test_r5_b1_zero_division_resilience():
    """R5.B1: Verify financial calculation percentages are finite numbers without NaN or Inf."""
    indices_resp = client.get("/api/market/indices")
    assert indices_resp.status_code == 200
    for idx in indices_resp.json():
        assert not math.isnan(idx["pct_change"]), f"NaN in index pct_change: {idx}"
        assert not math.isinf(idx["pct_change"]), f"Inf in index pct_change: {idx}"

    adv_resp = client.post("/api/advisory/recommend", json_data={"budget": 50000000})
    assert adv_resp.status_code == 200
    data = adv_resp.json()
    assert not math.isnan(data["cash_pct"])
    for stock in data["stock_allocations"]:
        assert not math.isnan(stock["weight_pct"])
        assert 0.0 <= stock["weight_pct"] <= 100.0


def test_r5_b2_css_color_hex_codes_validity():
    """R5.2: Verify CSS definitions for Vietnamese 5-color convention are syntactically valid color tokens."""
    resp = client.get("/static/css/style.css")
    assert resp.status_code == 200
    css = resp.text

    # Extract color tokens
    hex_pattern = r"(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3})"
    matches = re.findall(hex_pattern, css)
    assert len(matches) >= 5, f"Expected at least 5 hex color tokens in CSS, found {len(matches)}"


def test_r5_b3_tabular_nums_enforcement():
    """R5.B3: Verify CSS enforces tabular-nums to prevent visual jitter on streaming financial figures."""
    resp = client.get("/static/css/style.css")
    assert resp.status_code == 200
    css = resp.text
    assert "tabular-nums" in css, "font-variant-numeric: tabular-nums must be declared in CSS"


def test_r5_b4_spa_view_containers_state_classes():
    """R5.B4: Verify HTML SPA and CSS define view transitions using active/hidden container classes."""
    html_resp = client.get("/")
    assert html_resp.status_code == 200
    html = html_resp.text

    assert "view-container" in html, "View container class must be present in HTML markup"
    assert "active" in html, "Initial active view class must be present in HTML markup"


def test_r5_b5_chart_dom_container_elements():
    """R5.B5: Verify script references or DOM mounting containers for charts are present."""
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text.lower()

    # Verify presence of charting assets
    assert "lightweight-charts" in html or "tradingview" in html
    assert "apexcharts" in html
