# E2E Test Infrastructure & Verification Specification

**Project**: Vietnamese Stock Market Advisor & Prediction System (VN-Advisor)  
**Track**: Opaque-Box E2E Testing Track  
**Document**: `TEST_INFRA.md`  
**Status**: APPROVED & ACTIVE  

---

## 1. Test Philosophy & Principles

### 1.1 Opaque-Box & Requirement-Driven
The testing strategy for the Vietnamese Stock Advisor is strictly **opaque-box** and **requirement-driven**. Tests evaluate the system purely against observable external behaviors, REST API contracts, DOM/asset structures, and domain business rules defined in `ORIGINAL_REQUEST.md` and `PROJECT.md`.
- **Zero Coupling to Internal Implementation Details**: Tests do not inspect private methods, monkey-patch internal helper variables, or assert on ephemeral transient states.
- **Contract-Based Validation**: Endpoints are treated as black boxes accepting standard HTTP requests and returning validated JSON payloads conforming to published Pydantic schemas.
- **Progressive Testability**: The test suite can run in self-contained simulation mode against reference contract fixtures, directly against the ASGI application via `starlette.testclient.TestClient`, or against a live running server (`http://127.0.0.1:8000`).

### 1.2 Vietnamese Market Regulatory Compliance
The test suite explicitly codifies and enforces Vietnamese exchange laws and State Securities Commission (SSC) regulations:
1. **Discrete 100-Share Integer Lots**: Under Circular 120/2020/TT-BTC, standard board trading on HOSE, HNX, and UPCOM requires whole multiples of 100 shares ($N \pmod{100} == 0$). Zero fractional shares are permitted.
2. **5-State Price Color Rules**: Standardized color tokens for Gain (Green), Loss (Red), Reference (Yellow), Ceiling (Purple, $+7\%$ HOSE, $+10\%$ HNX, $+15\%$ UPCOM), and Floor (Cyan, $-7\%$ HOSE, $-10\%$ HNX, $-15\%$ UPCOM).
3. **Cash & Fee Conservation**: Portfolios must satisfy $\text{Invested} + \text{Cash Remainder} = \text{Budget}$, with cash remainder strictly non-negative and covering transaction friction ($\approx 0.3\% - 0.5\%$).

---

## 2. Feature Inventory & Requirements Traceability

The test suite maps directly to the 5 primary system requirements ($N = 5$):

| Req ID | Requirement Description | Mapped Tests & Scope | Target Files |
| :--- | :--- | :--- | :--- |
| **R1** | **Interactive Web Application Prototype** | ASGI server runnability, root HTML serving, SPA view containers (Market, Stock, Advisory), OpenAPI documentation, static assets mounting. | `test_tier1_features.py` (R1.1–R1.5)<br>`test_tier2_boundaries.py` (R1.B1–R1.B5) |
| **R2** | **Vietnam Stock Market Data Integration** | 4 indices (VN-Index, VN30, HNX, UPCOM), 20 target blue chips, raw VND normalization, OHLCV history, foreign investor trading net flow. | `test_tier1_features.py` (R2.1–R2.5)<br>`test_tier2_boundaries.py` (R2.B1–R2.B5) |
| **R3** | **Market Prediction & Trend Analysis** | 7 technical indicators (SMA, EMA, RSI, MACD, BB, Vol SMA, ATR), Confluence scoring ($-100$ to $+100$), Damped Holt 7/14/30-day forecast, 80%/95% confidence cones, S/R pivots, Trade targets (Entry, Stop Loss, TP1, TP2, RRR $\ge 1.5$). | `test_tier1_features.py` (R3.1–R3.5)<br>`test_tier2_boundaries.py` (R3.B1–R3.B5) |
| **R4** | **Budget & Preference-Based Investment Strategy Advisory** | Discrete 100-share knapsack allocation, risk profiles (Conservative, Moderate, Aggressive), horizons, sector filtering, capital conservation, strategic rationale. | `test_tier1_features.py` (R4.1–R4.5)<br>`test_tier2_boundaries.py` (R4.B1–R4.B5) |
| **R5** | **Professional Financial UI/UX (`ui-ux-pro-max`)** | Dark OLED palette, Vietnamese 5-color tokens, `font-variant-numeric: tabular-nums`, TradingView canvas containers, ApexCharts donut, Lucide SVGs, responsive layout. | `test_tier1_features.py` (R5.1–R5.5)<br>`test_tier2_boundaries.py` (R5.B1–R5.B5) |

---

## 3. 4-Tier Test Architecture

The test suite is organized into 4 hierarchical testing tiers located under `tests/e2e/`:

```
tests/
├── e2e/
│   ├── __init__.py
│   ├── client.py                    # Unified opaque-box test client (Live HTTP / TestClient / Contract Simulator)
│   ├── test_tier1_features.py       # Tier 1: Core Feature Coverage (>=25 tests)
│   ├── test_tier2_boundaries.py     # Tier 2: Boundary & Corner Cases (>=25 tests)
│   ├── test_tier3_cross_feature.py  # Tier 3: Cross-Feature Interactions (>=10 tests)
│   └── test_tier4_scenarios.py      # Tier 4: Real-World Persona Scenarios (>=5 scenarios)
└── run_tests.py                     # Master CLI test runner
```

### Tier 1: Feature Coverage (Baseline & Happy Paths)
- Minimum 5 tests per requirement ($5 \times 5 = 25$ tests minimum).
- Exercises standard successful operations, schema validations, mandatory field completeness, and basic UI/DOM components.

### Tier 2: Boundary & Corner Cases
- Minimum 5 tests per requirement ($5 \times 5 = 25$ tests minimum).
- Evaluates extreme boundary conditions:
  - Budget extremes: Small budgets (3M–5M VND) where individual lots exceed budget; Large budgets (10B VND) preventing overflow.
  - Invalid inputs: Unknown tickers (`INVALID99`), malformed HTTP verbs, zero/negative inputs, empty sector lists.
  - Volatility boundaries: Maximum ceiling ($+7\%$) and floor ($-7\%$) limits, flatline price series, division by zero prevention.
  - Security & resilience: Static path traversal resistance, CORS headers, missing DOM containers.

### Tier 3: Cross-Feature Interactions
- Minimum 10 pairwise and multi-stage workflow tests.
- Verifies data flowing across module boundaries:
  - Market Data OHLCV $\rightarrow$ Technical Indicators calculation.
  - Technical Indicators $\rightarrow$ Confluence Scoring $\rightarrow$ Signal generation.
  - Indicator Volatility (ATR) $\rightarrow$ Prediction Uncertainty Cones (80%/95%).
  - Market Quote $\rightarrow$ Trade Target generation (RRR $\ge 1.5$).
  - Prediction Signals $\rightarrow$ Advisory Candidate Universe filtering.
  - Budget Input $\times$ Stock Price $\rightarrow$ Integer Lot Knapsack optimization.
  - Knapsack Allocation $\rightarrow$ Asset Allocation Donut distribution.
  - User Sector Selection $\rightarrow$ Final Portfolio Sector Composition.
  - Stock State (Ceiling/Floor/Up/Down/Ref) $\rightarrow$ UI Badge Color Mapping.
  - Full End-to-End Pipeline: Feed $\rightarrow$ Analysis $\rightarrow$ Prediction $\rightarrow$ Recommendation.

### Tier 4: Real-World Application Scenarios
Simulates 5 distinct, realistic investor personas with tailored constraints:
1. **Scenario 1: Young Tech Professional**
   - Profile: 50,000,000 VND, Moderate risk, 6-month horizon, Technology & Banking sectors.
   - Verification: Selects tech/banking leaders (FPT, MBB, TCB), all 100-share whole lots, $>70\%$ capital deployment, cash buffer preserved.
2. **Scenario 2: Conservative Retiree**
   - Profile: 200,000,000 VND, Conservative risk, 2-year horizon, Dividend & Large-Cap focus.
   - Verification: High cash/defensive allocation ($\ge 15\%$), stable dividend blue-chips (VNM, VCB, FPT), low portfolio volatility, strict capital preservation.
3. **Scenario 3: Aggressive Swing Trader**
   - Profile: 30,000,000 VND, Aggressive risk, 1-month horizon, High Beta Materials & Securities focus (HPG, SSI).
   - Verification: High capital utilization ($\ge 85\%$), tight stop-loss targets, Take-Profit targets yielding RRR $\ge 1.5$.
4. **Scenario 4: Starter Retail Investor**
   - Profile: 10,000,000 VND, Moderate risk, 3-month horizon, small budget constraints.
   - Verification: Automatically excludes expensive stocks whose 100-share lot exceeds budget (e.g. FPT @ 135k = 13.5M > 10M), selects accessible shares (MBB, HPG, POW), exact integer lots.
5. **Scenario 5: High Net Worth Wealth Building**
   - Profile: 500,000,000 VND, Balanced Growth, 1-year horizon, multi-sector diversification.
   - Verification: Balanced distribution across $\ge 3$ sectors, no single stock exceeding $35\%$ concentration, comprehensive strategic notes and risk warnings.

---

## 4. Test Execution & Pass/Fail Semantics

### 4.1 Master Test Runner (`tests/run_tests.py`)
The master test runner provides an integrated CLI interface:
```bash
# Run complete test suite (all 4 tiers)
python tests/run_tests.py

# Run specific tiers
python tests/run_tests.py --tier 1
python tests/run_tests.py --tier 2
python tests/run_tests.py --tier 3
python tests/run_tests.py --tier 4

# Run with verbose test logs
python tests/run_tests.py --verbose

# Run via standard pytest
pytest tests/e2e/ -v
```

### 4.2 Exit Codes & Reporting
- **Exit Code 0**: 100% of discovered tests across targeted tiers pass without error.
- **Non-Zero Exit Code (1)**: Any test failure or unhandled exception occurs.
- **Summary Table**: Emits a formatted ASCII summary detailing tests executed, passed, failed, duration, and percentage passing per tier.

---

## 5. Coverage & Quality Thresholds

| Metric | Target Threshold | Minimum Acceptable |
| :--- | :--- | :--- |
| **Tier 1 Tests** | $\ge 25$ tests ($5$ per feature R1-R5) | 25 |
| **Tier 2 Tests** | $\ge 25$ tests ($5$ per feature R1-R5) | 25 |
| **Tier 3 Tests** | $\ge 10$ tests | 10 |
| **Tier 4 Scenarios**| $\ge 5$ personas | 5 |
| **Total Test Count**| $\ge 65$ test cases | 65 |
| **Pass Rate** | $100\%$ | 100% |
| **Execution Latency** | $< 15$ seconds total | $< 30$ seconds |
| **Whole-Lot Invariant** | $100\%$ ($N \pmod{100} == 0$) | Strict Zero Fractional Shares |
