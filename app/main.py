"""FastAPI Application for Vietnamese Stock Market Advisor & Prediction System.
Milestone 4 (M4_API)

Features:
- REST Endpoints for Market Indices, Stocks, Foreign Flow, Breadth
- Technical Indicators & 5-Pillar Confluence Scoring
- Damped Holt Forecasting & Volatility Cones
- 100-Share Discrete Knapsack Advisory Engine
- Static File Serving with Directory Traversal Protection
- Interactive OpenAPI / Swagger UI Documentation
"""

import datetime
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import (
    STOCK_UNIVERSE,
    SUPPORTED_INDICES,
    EXCHANGE_LIMITS,
    STANDARD_LOT_SIZE,
)
from app.data.models import (
    MarketIndex,
    StockQuote,
    OHLCVRecord,
    ForeignTradeRecord,
    MarketBreadth,
)
from app.data.provider import MarketDataProvider
from app.analytics.indicators import TechnicalEngine
from app.analytics.prediction import PredictionEngine
from app.analytics.models import IndicatorSummary, PredictionSummary
from app.advisory.models import AdvisoryRequest, AdvisoryResponse
from app.advisory.allocator import AdvisoryEngine

# Root directory of the application
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="VN-Advisor | Vietnamese Stock Market Advisor & Prediction API",
    description=(
        "Production REST API for Vietnamese equities: real-time & historical market data, "
        "quantitative technical indicators, Damped Holt trend forecasting with volatility cones, "
        "and discrete 100-share integer lot portfolio optimization complying with Circular 120/2020/TT-BTC."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Enable CORS for local development and testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Unified Provider Instance
provider = MarketDataProvider(use_live=True)


# ==============================================================================
# Security & Static Files
# ==============================================================================

@app.middleware("http")
async def security_and_path_traversal_middleware(request: Request, call_next):
    """
    Blocks path traversal attempts (/static/../, %2e%2e, etc.) with 403 Forbidden.
    """
    raw_path = request.url.path
    if "/../" in raw_path or raw_path.endswith("/..") or "..%2f" in raw_path.lower() or "%2e%2e" in raw_path.lower():
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Access forbidden: Path traversal is not permitted."},
        )
    return await call_next(request)


@app.get("/static/{file_path:path}", include_in_schema=False)
async def serve_static_asset(file_path: str):
    """
    Safely serves static assets from app/static with strict directory bounds.
    """
    if ".." in file_path or file_path.startswith("/") or "\\" in file_path:
        raise HTTPException(status_code=403, detail="Access forbidden")

    target = (STATIC_DIR / file_path).resolve()
    try:
        target.relative_to(STATIC_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access forbidden")

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail=f"Static file '{file_path}' not found")

    media_type = "application/octet-stream"
    if target.suffix == ".css":
        media_type = "text/css"
    elif target.suffix == ".js":
        media_type = "application/javascript"
    elif target.suffix == ".html":
        media_type = "text/html; charset=utf-8"
    elif target.suffix == ".json":
        media_type = "application/json"
    elif target.suffix in [".png", ".jpg", ".jpeg", ".svg"]:
        media_type = f"image/{target.suffix.lstrip('.')}"

    return FileResponse(target, media_type=media_type)


@app.get("/", response_class=FileResponse, include_in_schema=False)
async def serve_root_spa():
    """Serves the primary Single-Page Application (SPA) HTML shell."""
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="SPA index.html not found")
    return FileResponse(index_file, media_type="text/html; charset=utf-8")


# ==============================================================================
# Healthcheck Endpoint
# ==============================================================================

@app.get(
    "/api/health",
    tags=["Health"],
    summary="Application Health & Status Check",
    response_description="Returns operational status and active engine versions",
)
async def get_health():
    """Health check endpoint confirming ASGI service readiness."""
    return {
        "status": "healthy",
        "service": "Vietnamese Stock Advisor API",
        "version": "1.0.0",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "universe_size": len(STOCK_UNIVERSE),
        "supported_indices": len(SUPPORTED_INDICES),
    }


# ==============================================================================
# Market Overview Endpoints
# ==============================================================================

@app.get(
    "/api/market/indices",
    response_model=List[MarketIndex],
    tags=["Market Data"],
    summary="Get All Major Vietnamese Market Indices",
    response_description="Returns real-time and snapshot quotes for VNINDEX, VN30, HNX, UPCOM",
)
async def get_market_indices():
    """Retrieves live or cached quotes for VNINDEX, VN30INDEX, HNX-INDEX, and UPCOM-INDEX."""
    return provider.get_indices()


@app.get(
    "/api/market/stocks",
    response_model=List[StockQuote],
    tags=["Market Data"],
    summary="Get Quotes for Curated Universe (20 Stocks)",
    response_description="Returns quotes with Vietnamese 5-color market state",
)
async def get_all_universe_stocks():
    """Retrieves latest quotes for all 20 blue-chip stocks across 6 Vietnamese sectors."""
    return provider.get_all_quotes()


@app.get(
    "/api/market/foreign-flow",
    tags=["Market Data"],
    summary="Get Market-Wide Foreign Capital Net Flow",
    response_description="Returns net value in VND and individual stock foreign flow records",
)
async def get_foreign_flow():
    """Retrieves foreign investor net buy/sell volumes and aggregate market flow."""
    records = provider.get_market_foreign_flow()
    total_net = sum(r.net_value_vnd for r in records)
    return {
        "net_value_vnd": total_net,
        "records": [r.model_dump() for r in records],
        "total_stocks_tracked": len(records),
    }


@app.get(
    "/api/market/breadth",
    tags=["Market Data"],
    summary="Get Market Breadth Distribution",
    response_description="Counts of Ceiling, Up, Ref, Down, and Floor stocks across universe",
)
async def get_market_breadth():
    """Returns Vietnamese 5-state market breadth distribution."""
    return provider.get_market_breadth()


# ==============================================================================
# Stock Deep-Dive Endpoints
# ==============================================================================

def _normalize_and_validate_symbol(symbol: str) -> str:
    """Normalizes ticker symbol and validates existence in universe or indices."""
    clean = symbol.strip().upper()
    seed = provider._load_seed()
    if clean not in STOCK_UNIVERSE and clean not in SUPPORTED_INDICES and clean not in seed.get("quotes", {}):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stock symbol '{symbol}' not found in active universe",
        )
    return clean


@app.get(
    "/api/stock/quote/{symbol}",
    response_model=StockQuote,
    tags=["Stock Analysis"],
    summary="Get Single Stock Quote with Vietnamese Market State",
)
async def get_stock_quote(symbol: str):
    """Retrieves quote for a specific ticker symbol normalized to raw VND."""
    clean = _normalize_and_validate_symbol(symbol)
    try:
        return provider.get_quote(clean)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stock symbol '{symbol}' not found in active universe",
        )


@app.get(
    "/api/stock/history/{symbol}",
    response_model=List[OHLCVRecord],
    tags=["Stock Analysis"],
    summary="Get Historical Daily OHLCV Candlestick Series",
)
async def get_stock_history(
    symbol: str,
    days: int = Query(90, ge=1, description="Number of daily trading bars (minimum 1)"),
):
    """
    Retrieves chronological daily OHLCV candlesticks for technical analysis and charting.
    Safe bounds: days is capped at 365 days max.
    """
    clean = _normalize_and_validate_symbol(symbol)
    safe_days = min(days, 365)
    try:
        return provider.get_history(clean, days=safe_days)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Historical data for symbol '{symbol}' not found",
        )


@app.get(
    "/api/stock/indicators/{symbol}",
    response_model=IndicatorSummary,
    tags=["Stock Analysis"],
    summary="Calculate 7 Technical Indicators & Confluence Score",
)
async def get_stock_indicators(symbol: str):
    """
    Computes pure Python technical indicators: SMA (20, 50, 200), EMA (12, 26),
    Wilder RSI-14, MACD (12, 26, 9), Bollinger Bands (20, 2), ATR-14, Volume SMA,
    and 5-Pillar Confluence Scoring [-100, +100].
    """
    clean = _normalize_and_validate_symbol(symbol)
    candles = provider.get_history(clean, days=90)
    if not candles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Insufficient candle history for symbol '{symbol}'",
        )
    return TechnicalEngine.calculate_indicators(candles, symbol=clean)


@app.get(
    "/api/stock/prediction/{symbol}",
    response_model=PredictionSummary,
    tags=["Stock Analysis"],
    summary="Generate Trend Forecast, Volatility Cones & Trade Setup",
)
async def get_stock_prediction(symbol: str):
    """
    Forecasts price trajectory via Damped Holt Exponential Smoothing (h=7, 14, 30 days),
    expanding statistical volatility cones (80% and 95%), pivot support/resistance,
    and recommended trade setup with RRR >= 1.5.
    """
    clean = _normalize_and_validate_symbol(symbol)
    candles = provider.get_history(clean, days=90)
    if not candles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Insufficient candle history for symbol '{symbol}'",
        )
    return PredictionEngine.forecast_trend(candles, symbol=clean)


# ==============================================================================
# Investment Strategy Advisory Endpoints
# ==============================================================================

@app.post(
    "/api/advisory/recommend",
    response_model=AdvisoryResponse,
    tags=["Advisory Engine"],
    summary="Generate 100-Share Integer Lot Portfolio Recommendation",
    response_description="Returns asset allocation breakdown, whole 100-share picks, and strategic rationale",
)
async def recommend_portfolio(request: AdvisoryRequest):
    """
    Executes discrete knapsack portfolio optimization complying with Circular 120/2020/TT-BTC:
    - Guaranteed 100-share integer lots (zero odd lots)
    - Strict capital conservation: Total Invested + Cash Remainder == Budget
    - Tailored asset allocation based on risk tolerance (Conservative, Moderate, Aggressive)
    """
    # Enforce positive finite budget
    if request.budget is None or request.budget <= 0.0 or math.isnan(request.budget) or math.isinf(request.budget):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Budget must be a positive finite number in Vietnamese Dong (VND)",
        )

    try:
        return AdvisoryEngine.recommend_portfolio(request=request, provider=provider)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Advisory engine error: {str(e)}",
        )
