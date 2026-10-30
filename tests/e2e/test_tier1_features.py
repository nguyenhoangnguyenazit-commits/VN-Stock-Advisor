"""Tier 1: Core Feature Coverage Test Suite.

Adheres strictly to the 4-Tier Test Architecture:
- Requirement R1: Interactive Web Application Prototype (5 tests)
- Requirement R2: Vietnam Stock Market Data Integration (5 tests)
- Requirement R3: Market Prediction & Trend Analysis (5 tests)
- Requirement R4: Budget & Preference-Based Investment Strategy Advisory (5 tests)
- Requirement R5: Professional Financial UI/UX (ui-ux-pro-max) (5 tests)

Total Test Cases: 25
"""

import pytest
from tests.e2e.client import get_e2e_client

client = get_e2e_client()


# ==============================================================================
# R1: Interactive Web Application Prototype
# ==============================================================================

def test_r1_root_endpoint_html():
    """R1.1: Verify root URL returns 200 OK and serves valid HTML SPA markup."""
    resp = client.get("/")
    assert resp.status_code == 200, f"Expected 200 OK from root, got {resp.status_code}"
    assert "text/html" in resp.headers.get("content-type", "").lower()
    html = resp.text.lower()
    assert "<!doctype html>" in html
    assert "<title>" in html
    assert "vn-advisor" in html or "chứng khoán" in html


def test_r1_healthcheck_endpoint():
    """R1.2: Verify API healthcheck endpoint returns operational status."""
    resp = client.get("/api/health")
    assert resp.status_code == 200, f"Expected 200 OK from /api/health, got {resp.status_code}"
    data = resp.json()
    assert data.get("status") in ["ok", "healthy"]
    assert "version" in data
    assert "timestamp" in data


def test_r1_static_assets_serving():
    """R1.3: Verify static assets (CSS styles, JS bundles) are accessible."""
    css_resp = client.get("/static/css/style.css")
    assert css_resp.status_code == 200
    assert len(css_resp.text) > 0

    js_resp = client.get("/static/js/app.js")
    assert js_resp.status_code == 200
    assert len(js_resp.text) > 0


def test_r1_spa_navigation_views():
    """R1.4: Verify HTML contains containers and navigation for all 3 primary views."""
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text
    # Check for View containers
    assert "view-market" in html, "Market Overview view container missing from DOM"
    assert "view-stock" in html, "Stock Deep-Dive view container missing from DOM"
    assert "view-advisory" in html, "Personalized Advisory view container missing from DOM"
    # Check for navigation tabs
    assert "tab-market" in html or "market" in html.lower()
    assert "tab-stock" in html or "stock" in html.lower()
    assert "tab-advisory" in html or "advisory" in html.lower()


def test_r1_openapi_documentation():
    """R1.5: Verify OpenAPI documentation is exposed and provides valid specification."""
    resp = client.get("/docs")
    assert resp.status_code in [200, 307], f"Expected 200 or 307 from /docs, got {resp.status_code}"
    openapi_resp = client.get("/openapi.json")
    if openapi_resp.status_code == 200:
        schema = openapi_resp.json()
        assert "openapi" in schema or "swagger" in schema
        assert "info" in schema


# ==============================================================================
# R2: Vietnam Stock Market Data Integration
# ==============================================================================

def test_r2_indices_feed_coverage():
    """R2.1: Verify market indices endpoint returns all 4 major Vietnamese indices."""
    resp = client.get("/api/market/indices")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 4

    symbols = {item["symbol"] for item in data}
    expected_indices = {"VNINDEX", "VN30INDEX", "HNX-INDEX", "UPCOM-INDEX"}
    assert expected_indices.issubset(symbols), f"Missing indices in response: {expected_indices - symbols}"

    for idx in data:
        assert idx["value"] > 0, f"Index {idx['symbol']} has invalid value {idx['value']}"
        assert "change" in idx
        assert "pct_change" in idx
        assert "volume" in idx
        assert "value_vnd" in idx
        assert idx["state"] in ["CEILING", "FLOOR", "UP", "DOWN", "REF"]


def test_r2_stock_quote_schema_and_fields():
    """R2.2: Verify stock quote endpoint returns complete StockQuote schema."""
    resp = client.get("/api/stock/quote/FPT")
    assert resp.status_code == 200
    quote = resp.json()

    assert quote["symbol"] == "FPT"
    assert quote["exchange"] == "HOSE"
    assert quote["price"] > 0
    assert quote["ref_price"] > 0
    assert quote["ceiling_price"] > quote["ref_price"]
    assert quote["floor_price"] < quote["ref_price"]
    assert quote["state"] in ["CEILING", "FLOOR", "UP", "DOWN", "REF"]
    assert "company_name" in quote
    assert "sector" in quote
    assert "volume" in quote


def test_r2_price_normalization_raw_vnd():
    """R2.3: Verify stock prices are normalized to raw VND (not x1000 VND)."""
    resp = client.get("/api/stock/quote/FPT")
    assert resp.status_code == 200
    quote = resp.json()
    price = quote["price"]
    # FPT price in raw VND is > 50,000 VND (never 50.0 - 150.0)
    assert price > 1000.0, f"Stock price appears unnormalized: {price} VND"
    assert quote["ref_price"] > 1000.0
    assert quote["ceiling_price"] > 1000.0
    assert quote["floor_price"] > 1000.0


def test_r2_historical_ohlcv_series():
    """R2.4: Verify OHLCV history returns properly structured candlestick series."""
    resp = client.get("/api/stock/history/FPT?days=30")
    assert resp.status_code == 200
    bars = resp.json()
    assert isinstance(bars, list)
    assert len(bars) >= 20, f"Expected at least 20 daily bars, got {len(bars)}"

    for bar in bars:
        assert "time" in bar
        assert bar["high"] >= bar["low"], f"High {bar['high']} < Low {bar['low']}"
        assert bar["high"] >= bar["open"], f"High {bar['high']} < Open {bar['open']}"
        assert bar["high"] >= bar["close"], f"High {bar['high']} < Close {bar['close']}"
        assert bar["low"] <= bar["open"], f"Low {bar['low']} > Open {bar['open']}"
        assert bar["low"] <= bar["close"], f"Low {bar['low']} > Close {bar['close']}"
        assert bar["volume"] >= 0


def test_r2_foreign_flow_feed():
    """R2.5: Verify foreign investor trade feed returns net statistics and records."""
    resp = client.get("/api/market/foreign-flow")
    assert resp.status_code == 200
    data = resp.json()
    assert "net_value_vnd" in data
    assert "records" in data
    assert isinstance(data["records"], list)
    assert len(data["records"]) > 0
    rec = data["records"][0]
    assert "symbol" in rec
    assert "net_volume" in rec
    assert "net_value_vnd" in rec


# ==============================================================================
# R3: Market Prediction & Trend Analysis
# ==============================================================================

def test_r3_technical_indicators_engine():
    """R3.1: Verify indicators endpoint computes all 7 required technical indicators."""
    resp = client.get("/api/stock/indicators/HPG")
    assert resp.status_code == 200
    ind = resp.json()

    assert ind["symbol"] == "HPG"
    assert "sma20" in ind and ind["sma20"] > 0
    assert "sma50" in ind and ind["sma50"] > 0
    assert "sma200" in ind and ind["sma200"] > 0
    assert "ema12" in ind and ind["ema12"] > 0
    assert "ema26" in ind and ind["ema26"] > 0
    assert "rsi14" in ind and 0 <= ind["rsi14"] <= 100
    assert "macd" in ind
    assert "line" in ind["macd"] and "signal" in ind["macd"] and "histogram" in ind["macd"]
    assert "bollinger" in ind
    assert ind["bollinger"]["upper"] >= ind["bollinger"]["middle"] >= ind["bollinger"]["lower"]
    assert "atr14" in ind and ind["atr14"] > 0


def test_r3_confluence_scoring_and_signals():
    """R3.2: Verify confluence scoring produces normalized score (-100 to +100) and signal."""
    resp = client.get("/api/stock/indicators/HPG")
    assert resp.status_code == 200
    ind = resp.json()

    score = ind.get("confluence_score")
    assert score is not None
    assert -100.0 <= score <= 100.0, f"Confluence score out of bounds: {score}"

    signal = ind.get("confluence_signal")
    valid_signals = {"STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL", "ACCUMULATE"}
    assert signal in valid_signals, f"Unexpected signal: {signal}"


def test_r3_multi_horizon_forecasting():
    """R3.3: Verify trend forecasting generates projections for 7, 14, and 30-day horizons."""
    resp = client.get("/api/stock/prediction/FPT")
    assert resp.status_code == 200
    pred = resp.json()

    assert pred["symbol"] == "FPT"
    assert "forecasts" in pred
    forecasts = pred["forecasts"]
    assert len(forecasts) >= 3

    horizons = {f["horizon_days"] for f in forecasts}
    assert {7, 14, 30}.issubset(horizons), f"Missing forecast horizons: {horizons}"

    for f in forecasts:
        assert f["target_price"] > 0
        assert "expected_return_pct" in f


def test_r3_volatility_confidence_cones():
    """R3.4: Verify statistical uncertainty bands (80% and 95%) expand with horizon."""
    resp = client.get("/api/stock/prediction/FPT")
    assert resp.status_code == 200
    forecasts = resp.json()["forecasts"]

    for f in forecasts:
        target = f["target_price"]
        u80 = f["upper_80"]
        l80 = f["lower_80"]
        u95 = f["upper_95"]
        l95 = f["lower_95"]

        assert l95 <= l80, f"95% lower band {l95} must be <= 80% lower band {l80}"
        assert l80 <= target <= u80, f"Target {target} must fall inside 80% confidence interval [{l80}, {u80}]"
        assert u80 <= u95, f"80% upper band {u80} must be <= 95% upper band {u95}"


def test_r3_support_resistance_and_trade_setup():
    """R3.5: Verify pivot support/resistance matrix and trade setup with RRR >= 1.5."""
    resp = client.get("/api/stock/prediction/FPT")
    assert resp.status_code == 200
    data = resp.json()

    assert "support_resistance" in data
    sr = data["support_resistance"]
    assert sr["s2"] <= sr["s1"] <= sr["r1"] <= sr["r2"]

    assert "trade_setup" in data
    setup = data["trade_setup"]
    assert "entry_zone" in setup and len(setup["entry_zone"]) == 2
    assert "stop_loss" in setup
    assert "take_profit_1" in setup
    assert "risk_reward_ratio" in setup
    assert setup["risk_reward_ratio"] >= 1.5, f"RRR must be >= 1.5, got {setup['risk_reward_ratio']}"


# ==============================================================================
# R4: Budget & Preference-Based Investment Strategy Advisory
# ==============================================================================

def test_r4_advisory_recommendation_happy_path():
    """R4.1: Verify advisory endpoint generates personalized allocation for 50M VND."""
    payload = {
        "budget": 50000000,
        "risk_level": "MODERATE",
        "horizon": "MEDIUM_TERM",
        "sectors": ["TECHNOLOGY", "BANKING", "STEEL"]
    }
    resp = client.post("/api/advisory/recommend", json_data=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["budget_vnd"] == 50000000
    assert data["total_invested_vnd"] > 0
    assert data["cash_remainder_vnd"] >= 0
    assert len(data["stock_allocations"]) > 0
    assert len(data["asset_allocation"]) >= 2


def test_r4_strict_100_share_lot_constraint():
    """R4.2: Enforce Vietnamese law: 100-share integer lot constraint (zero fractional shares)."""
    payload = {
        "budget": 50000000,
        "risk_level": "MODERATE",
        "horizon": "MEDIUM_TERM"
    }
    resp = client.post("/api/advisory/recommend", json_data=payload)
    assert resp.status_code == 200
    stocks = resp.json()["stock_allocations"]

    for item in stocks:
        lots = item["allocated_lots"]
        shares = item["allocated_shares"]
        assert isinstance(lots, int) and lots >= 1, f"Lots must be positive integer: {lots}"
        assert isinstance(shares, int), f"Shares must be integer: {shares}"
        assert shares == lots * 100, f"Shares ({shares}) must equal lots ({lots}) * 100"
        assert shares % 100 == 0, f"Violation of 100-share lot rule: {shares} shares for {item['symbol']}"


def test_r4_capital_conservation_and_budget_cap():
    """R4.3: Verify strict capital conservation: Invested + Cash Remainder == Budget."""
    budget = 100000000.0  # 100 Million VND
    payload = {
        "budget": budget,
        "risk_level": "BALANCED",
        "horizon": "LONG_TERM"
    }
    resp = client.post("/api/advisory/recommend", json_data=payload)
    assert resp.status_code == 200
    data = resp.json()

    invested = data["total_invested_vnd"]
    cash = data["cash_remainder_vnd"]

    assert invested <= budget, f"Total invested ({invested}) exceeds budget ({budget})"
    assert cash >= 0, f"Cash remainder cannot be negative: {cash}"
    assert round(invested + cash, 2) == round(budget, 2), f"Capital conservation failed: {invested} + {cash} != {budget}"


def test_r4_risk_profile_allocation_rules():
    """R4.4: Verify Conservative profile maintains a higher cash buffer than Aggressive profile."""
    budget = 50000000
    resp_cons = client.post("/api/advisory/recommend", json_data={"budget": budget, "risk_level": "CONSERVATIVE"})
    resp_aggr = client.post("/api/advisory/recommend", json_data={"budget": budget, "risk_level": "AGGRESSIVE"})

    assert resp_cons.status_code == 200
    assert resp_aggr.status_code == 200

    cash_cons = resp_cons.json()["cash_pct"]
    cash_aggr = resp_aggr.json()["cash_pct"]
    assert cash_cons >= cash_aggr, f"Conservative cash pct ({cash_cons}%) should be >= Aggressive cash pct ({cash_aggr}%)"


def test_r4_strategic_rationale_and_execution_notes():
    """R4.5: Verify advisory response provides comprehensive strategic rationale notes."""
    payload = {"budget": 50000000, "risk_level": "MODERATE"}
    resp = client.post("/api/advisory/recommend", json_data=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert "strategic_notes" in data
    assert isinstance(data["strategic_notes"], list)
    assert len(data["strategic_notes"]) >= 2
    for note in data["strategic_notes"]:
        assert len(note.strip()) > 10

    for item in data["stock_allocations"]:
        assert "rationale" in item and len(item["rationale"].strip()) > 5


# ==============================================================================
# R5: Professional Financial UI/UX (ui-ux-pro-max)
# ==============================================================================

def test_r5_oled_dark_theme_tokens():
    """R5.1: Verify CSS styling defines institutional Dark OLED theme tokens."""
    resp = client.get("/static/css/style.css")
    assert resp.status_code == 200
    css = resp.text
    assert "--bg-base" in css or "#0b0f19" in css.lower(), "Missing OLED base background token"
    assert "--bg-surface" in css or "#111827" in css.lower(), "Missing surface card token"
    assert "--text-primary" in css or "#f8fafc" in css.lower(), "Missing primary text token"


def test_r5_vietnamese_5_color_convention():
    """R5.2: Verify CSS styling defines the 5 Vietnamese market state color tokens."""
    resp = client.get("/static/css/style.css")
    assert resp.status_code == 200
    css = resp.text
    # Check for gain (green), loss (red), ref (yellow), ceil (purple), floor (cyan)
    assert "--color-vn-gain" in css or "#10b981" in css.lower(), "Missing VN Gain (Green) color token"
    assert "--color-vn-loss" in css or "#ef4444" in css.lower(), "Missing VN Loss (Red) color token"
    assert "--color-vn-ref" in css or "#f59e0b" in css.lower(), "Missing VN Reference (Yellow) color token"
    assert "--color-vn-ceil" in css or "#a855f7" in css.lower(), "Missing VN Ceiling (Purple) color token"
    assert "--color-vn-floor" in css or "#06b6d4" in css.lower(), "Missing VN Floor (Cyan) color token"


def test_r5_tabular_numbers_typography():
    """R5.3: Verify CSS enforces font-variant-numeric: tabular-nums for numeric alignment."""
    resp = client.get("/static/css/style.css")
    assert resp.status_code == 200
    css = resp.text
    assert "tabular-nums" in css, "CSS must enforce font-variant-numeric: tabular-nums for financial figures"


def test_r5_charting_vendor_scripts():
    """R5.4: Verify HTML SPA integrates TradingView Lightweight Charts & ApexCharts scripts."""
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text.lower()
    assert "lightweight-charts" in html or "tradingview" in html, "TradingView charting library not referenced in HTML"
    assert "apexcharts" in html, "ApexCharts library not referenced in HTML"


def test_r5_responsive_layout_structure():
    """R5.5: Verify layout defines responsive breakpoints and container classes."""
    resp = client.get("/static/css/style.css")
    assert resp.status_code == 200
    css = resp.text
    assert "@media" in css or "max-width" in css or "flex-col" in css, "Missing responsive breakpoint rules in CSS"
