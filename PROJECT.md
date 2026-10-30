# Project: Vietnamese Stock Market Advisor & Prediction System

## Architecture
- **Backend**: Python 3.13 ASGI server using FastAPI, Uvicorn, and standard libraries.
- **Data Layer**: Dual-source pipeline (CafeF primary REST handlers + Yahoo Finance v8 chart fallback) with 3-tier caching (In-Memory TTL + Disk Cache + Offline Seed Snapshot).
- **Quantitative Engine**: Pure Python analytical modules for 7 technical indicators (SMA, EMA, RSI, MACD, BB, Vol SMA, ATR), confluence scoring, Damped Holt Exponential Smoothing with volatility cones, support/resistance pivots, and discrete 100-share integer lot knapsack allocation.
- **Frontend**: High-performance single-page application (SPA) adhering to `ui-ux-pro-max` guidelines: Dark OLED institutional financial terminal, Vietnamese 5-color market state rules, TradingView Lightweight Charts (v4.x) for 60fps candlestick/volume rendering, ApexCharts for portfolio allocation breakdown, Lucide icons, responsive layout.
- **Runnability**: Single-command startup via `python run.py`, binding to `http://127.0.0.1:8000`.

## Code Layout
```
vn_stock_advisor/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI application setup & route wiring
│   ├── config.py                # Environment, constants & ticker universes
│   ├── data/
│   │   ├── __init__.py
│   │   ├── models.py            # Pydantic schemas (MarketIndex, StockQuote, OHLCV, etc.)
│   │   ├── provider.py          # Unified market data provider with fallback & caching
│   │   ├── cafef.py             # CafeF REST API client
│   │   └── yfinance.py          # Yahoo Finance v8 chart API client
│   ├── analytics/
│   │   ├── __init__.py
│   │   ├── indicators.py        # SMA, EMA, RSI, MACD, Bollinger Bands, ATR, Confluence
│   │   └── prediction.py        # Damped Holt forecast, volatility cones, pivots, targets
│   ├── advisory/
│   │   ├── __init__.py
│   │   ├── profiles.py          # Risk tolerance and investment horizon rules
│   │   └── allocator.py         # Discrete 100-share integer lot knapsack optimizer
│   └── static/
│       ├── index.html           # Main SPA HTML structure
│       ├── css/
│       │   └── style.css        # Custom styles, OLED theme tokens, animations
│       ├── js/
│       │   ├── app.js           # SPA router, state manager & view controller
│       │   ├── market_view.js   # View 1: Market Overview & Indices Dashboard
│       │   ├── stock_view.js    # View 2: Stock Analysis & TradingView Charts
│       │   └── advisory_view.js # View 3: Personalized Advisory & Knapsack Table
│       ├── assets/              # Hero banner, brand logos, icons
│       └── vendor/              # Standalone Lightweight Charts, ApexCharts, Lucide
├── data/
│   ├── cache/                   # Runtime cached JSON responses
│   └── seeds/
│       └── market_snapshot.json # Pre-packaged 90-day offline snapshot for 4 indices & 20 stocks
├── tests/
│   ├── e2e/                     # Opaque-box E2E test suite (Tiers 1-4)
│   ├── unit/                    # Unit tests for data, analytics & advisory
│   └── run_tests.py             # Master test runner
├── run.py                       # One-command server runner
├── requirements.txt             # Minimal Python dependencies (fastapi, uvicorn, requests, pydantic)
├── PROJECT.md                   # Project architecture & master milestone registry
└── TEST_INFRA.md                # E2E test methodology & coverage index
```

## Feature Inventory
Every feature identified from ORIGINAL_REQUEST.md and the survey phase is inventoried below and mapped to a specific milestone.

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Vietnam Index Feeds | Live and historical data for VN-Index, VN30, HNX, UPCOM | M1_DATA | R2 |
| 2 | Stock Universe Feeds | Quotes & OHLCV for 20 curated blue-chip stocks across 6 sectors | M1_DATA | R2 |
| 3 | Dual-Source Resilience | CafeF primary + Yahoo Finance fallback + offline seed snapshot | M1_DATA | R2 |
| 4 | Market Caching Engine | In-memory TTL + disk JSON caching for high availability & speed | M1_DATA | R2 |
| 5 | Price Normalization | Normalized CafeF x1000 VND to raw VND and 100-share trading lots | M1_DATA | R2 |
| 6 | Technical Indicators | SMA (20/50/200), EMA (12/26), RSI, MACD, Bollinger Bands, ATR | M2_ANALYTICS | R2, R3 |
| 7 | Confluence Scoring | Composite indicator score (-100 to +100) -> 5 trade signals | M2_ANALYTICS | R3 |
| 8 | Trend Forecasting | Damped Holt Linear Smoothing producing 7, 14, 30-day price trajectories | M2_ANALYTICS | R3 |
| 9 | Volatility Cones | Statistical uncertainty bands (80% and 95%) based on ATR & horizon | M2_ANALYTICS | R3 |
| 10 | Support & Resistance | Classical and Fibonacci pivot price levels (S1, S2, R1, R2) | M2_ANALYTICS | R3 |
| 11 | Trade Target Generator | Suggested Entry Zone, Stop-Loss, Take-Profit 1 & 2, and RRR >= 1.5 | M2_ANALYTICS | R3 |
| 12 | User Profile Assessment | Input budget (VND), risk tolerance (3 tiers), horizon & sectors | M3_ADVISORY | R4 |
| 13 | Discrete Knapsack Allocator | Enforces strict 100-share integer lots (no fractional shares) | M3_ADVISORY | R4 |
| 14 | Asset Allocation Model | Target asset distribution (Cash, Large-Cap, Mid-Cap, Defensive) | M3_ADVISORY | R4 |
| 15 | Tailored Recommendations | Specific stock picks matching constraints with exact share counts & costs | M3_ADVISORY | R4 |
| 16 | Advisory Rationale | Strategic justifications, risk warnings, and rebalancing guidance | M3_ADVISORY | R4 |
| 17 | FastAPI REST Endpoints | Complete REST API for market data, analytics, predictions & advisory | M4_API | R1 |
| 18 | Local Server & Runner | Single-command startup (`python run.py`) binding to localhost:8000 | M4_API | R1 |
| 19 | UI Design System | Dark OLED institutional terminal styling per `ui-ux-pro-max` | M5_UI | R5 |
| 20 | VN 5-State Colors | Green (Gain), Red (Loss), Yellow (Ref), Purple (Ceiling), Cyan (Floor) | M5_UI | R5 |
| 21 | Navigation & Ribbon | Top navigation bar with brand emblem, quick market ticker ribbon, tabs | M5_UI | R1, R5 |
| 22 | Market Dashboard View | 4 index cards, sparklines, 5-state market breadth bar, foreign flow | M5_UI | R1, R5 |
| 23 | Stock Analysis View | Interactive TradingView candlestick + volume chart, timeframe toggles | M5_UI | R1, R5 |
| 24 | Prediction Overlay | Visual forecast trajectory, 80%/95% confidence cones, key target cards | M5_UI | R3, R5 |
| 25 | Advisory Console View | Interactive budget/risk form, live allocation donut, 100-share table | M5_UI | R4, R5 |
| 26 | Hero & Visual Assets | Bespoke hero banner and brand logo integrated into UI layout | M5_UI | R5 |
| 27 | Comprehensive E2E Suite | 4-Tier requirement-driven opaque-box test suite verifying R1-R5 | M6_FINAL / E2E | Criteria |
| 28 | Adversarial Coverage Hardening | Tier 5 white-box stress testing and edge-case validation | M6_FINAL | Criteria |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | M1_DATA | Market Data Layer (CafeF, Yahoo, seed snapshot, cache, models) | none | DONE |
| 2 | M2_ANALYTICS | Technical Indicators & Trend Prediction Engine | M1_DATA | DONE |
| 3 | M3_ADVISORY | Investment Strategy & 100-Share Knapsack Allocator | M1_DATA, M2_ANALYTICS | DONE |
| 4 | M4_API | FastAPI Server, REST API Routing, Static Serving & run.py | M1, M2, M3 | DONE |
| 5 | M5_UI | Financial Dashboard UI/UX Frontend (3 Views, Charts, ui-ux-pro-max) | M4_API | DONE |
| 6 | M6_FINAL | E2E Test Suite Pass (Tiers 1-4) & Phase 2 Adversarial Hardening | M1-M5, TEST_READY | DONE |

## Interface Contracts

### M1_DATA ↔ M2_ANALYTICS / M4_API
- `MarketDataProvider.get_indices() -> list[MarketIndex]`
- `MarketDataProvider.get_quote(symbol: str) -> StockQuote`
- `MarketDataProvider.get_history(symbol: str, days: int = 90) -> list[OHLCVRecord]`
- `MarketDataProvider.get_foreign_flow(symbol: str) -> ForeignTradeRecord`
- Types:
  * `OHLCVRecord`: `{ time: str ("YYYY-MM-DD"), open: float, high: float, low: float, close: float, volume: int }`
  * `StockQuote`: `{ symbol: str, price: float (VND), change: float, pct_change: float, high: float, low: float, volume: int, ref_price: float, ceiling_price: float, floor_price: float, state: str ("CEILING" | "FLOOR" | "UP" | "DOWN" | "REF") }`

### M2_ANALYTICS ↔ M3_ADVISORY / M4_API
- `TechnicalEngine.calculate_indicators(candles: list[OHLCVRecord]) -> IndicatorSummary`
- `TechnicalEngine.evaluate_confluence(indicators: IndicatorSummary) -> ConfluenceResult`
- `PredictionEngine.forecast_trend(candles: list[OHLCVRecord], horizons: list[int] = [7, 14, 30]) -> ForecastReport`
- Types:
  * `ForecastReport`: `{ current_price: float, signal: str, confidence_score: float, forecasts: list[{ horizon_days: int, target_price: float, expected_return_pct: float, upper_80: float, lower_80: float, upper_95: float, lower_95: float }], support_resistance: { s1: float, s2: float, r1: float, r2: float }, trade_setup: { entry_zone: [float, float], stop_loss: float, take_profit_1: float, take_profit_2: float, risk_reward_ratio: float } }`

### M3_ADVISORY ↔ M4_API / M5_UI
- `AdvisoryEngine.recommend_portfolio(budget: float, risk_level: str, horizon: str, sectors: list[str]) -> AdvisoryRecommendation`
- Types:
  * `AdvisoryRecommendation`: `{ budget_vnd: float, total_invested_vnd: float, cash_remainder_vnd: float, cash_pct: float, risk_level: str, horizon: str, asset_allocation: list[{ category: str, weight_pct: float, value_vnd: float }], stock_allocations: list[{ symbol: str, company_name: str, sector: str, current_price_vnd: float, allocated_lots: int, allocated_shares: int, total_cost_vnd: float, weight_pct: float, signal: str, target_price_vnd: float, stop_loss_vnd: float, rationale: str }], summary_metrics: { expected_return_pct: float, estimated_volatility_pct: float, sharpe_ratio: float, dividend_yield_est_pct: float }, strategic_notes: list[str] }`
- Invariant: `allocated_shares == allocated_lots * 100` and `allocated_shares % 100 == 0`. `total_invested_vnd + cash_remainder_vnd == budget_vnd`.
