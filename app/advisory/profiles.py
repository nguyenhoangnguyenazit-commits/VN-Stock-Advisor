"""Risk tolerance profiles, horizon normalization, scoring, sector aliases, and rationale generator.
Milestone 3 (M3_ADVISORY)
"""

import math
from typing import Dict, List, Any, Optional

from app.config import STOCK_UNIVERSE, STANDARD_LOT_SIZE
from app.data.provider import MarketDataProvider
from app.analytics.indicators import calculate_indicators, evaluate_confluence
from app.analytics.prediction import forecast_trend

# Sector Synonyms and Aliases
SECTOR_ALIASES: Dict[str, str] = {
    "STEEL": "Materials",
    "MATERIALS": "Materials",
    "MATERIAL": "Materials",
    "METALS": "Materials",
    "TECH": "Technology",
    "TECHNOLOGY": "Technology",
    "IT": "Technology",
    "BANK": "Banking",
    "BANKING": "Banking",
    "BANKS": "Banking",
    "FINANCIALS": "Banking",
    "FINANCE": "Banking",
    "SECURITIES": "Securities",
    "BROKERAGE": "Securities",
    "REAL ESTATE": "Real Estate",
    "REALESTATE": "Real Estate",
    "PROPERTY": "Real Estate",
    "RE": "Real Estate",
    "CONSUMER": "Retail / Consumer",
    "RETAIL": "Retail / Consumer",
    "RETAIL / CONSUMER": "Retail / Consumer",
    "FMCG": "Retail / Consumer",
    "ENERGY": "Energy / Utilities",
    "UTILITIES": "Energy / Utilities",
    "UTILITY": "Energy / Utilities",
    "ENERGY / UTILITIES": "Energy / Utilities",
    "POWER": "Energy / Utilities",
    "OIL & GAS": "Energy / Utilities",
    "OIL": "Energy / Utilities",
    "GAS": "Energy / Utilities",
}


def normalize_risk_level(raw_risk: Any) -> str:
    """Validates and normalizes risk tolerance string."""
    if not raw_risk or not isinstance(raw_risk, str):
        raise ValueError("risk_level must be a valid non-empty string")
    clean = raw_risk.strip().upper()
    if clean == "BALANCED":
        clean = "MODERATE"
    if clean not in ["CONSERVATIVE", "MODERATE", "AGGRESSIVE"]:
        raise ValueError(f"Invalid risk_level '{raw_risk}'. Must be CONSERVATIVE, MODERATE, or AGGRESSIVE")
    return clean


def normalize_horizon(raw_horizon: Any) -> str:
    """Normalizes investment horizon input string while preserving valid representations."""
    if not raw_horizon or not isinstance(raw_horizon, str):
        return "MEDIUM_TERM"
    clean = raw_horizon.strip().upper()
    if clean in ["1_MONTH", "3_MONTHS", "SHORT_TERM", "SHORT", "1M", "3M"]:
        return clean
    if clean in ["6_MONTHS", "1_YEAR", "MEDIUM_TERM", "MEDIUM", "6M", "1Y"]:
        return clean
    if clean in ["2_YEARS", "LONG_TERM", "LONG", "2Y", "3Y", "5Y"]:
        return clean
    return "MEDIUM_TERM"


def resolve_sector_candidates(
    requested_sectors: Optional[List[str]],
    universe: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Resolves sector filter with synonyms and graceful fallback on empty/unmatched."""
    active_universe = universe if universe is not None else STOCK_UNIVERSE

    if not requested_sectors:
        return list(active_universe.keys())

    normalized_targets = set()
    for s in requested_sectors:
        if isinstance(s, str) and s.strip():
            clean = s.strip().upper()
            if clean in SECTOR_ALIASES:
                normalized_targets.add(SECTOR_ALIASES[clean].upper())
            else:
                normalized_targets.add(clean)

    if not normalized_targets:
        return list(active_universe.keys())

    matched = []
    for sym, meta in active_universe.items():
        sec_upper = meta["sector"].upper()
        if any(t == sec_upper or t in sec_upper or sec_upper in t for t in normalized_targets):
            matched.append(sym)

    # Graceful fallback: unmatched sectors (e.g. CRYPTO_GAMING) fallback to universe without 500
    if not matched:
        return list(active_universe.keys())

    return matched


_CANDIDATE_SCORE_CACHE: Dict[tuple, Dict[str, Any]] = {}


def score_candidate_stock(
    symbol: str,
    risk: str,
    horizon: str,
    provider: MarketDataProvider,
) -> Dict[str, Any]:
    """Calculates quantitative confluence, forecast, RRR, and profile-aligned score."""
    cache_key = (symbol, risk, horizon)
    if cache_key in _CANDIDATE_SCORE_CACHE:
        return dict(_CANDIDATE_SCORE_CACHE[cache_key])

    quote = provider.get_quote(symbol)

    history = provider.get_history(symbol, days=90)
    meta = STOCK_UNIVERSE[symbol]

    indicators = calculate_indicators(history, symbol=symbol)
    confluence = evaluate_confluence(indicators)
    prediction = forecast_trend(history, symbol=symbol)

    current_price = quote.price
    lot_cost = current_price * STANDARD_LOT_SIZE
    div_yield = quote.dividend_yield or 0.0

    # Extract forecasts
    f14 = next((f for f in prediction.forecasts if f.horizon_days == 14), prediction.forecasts[0])
    f30 = next((f for f in prediction.forecasts if f.horizon_days == 30), prediction.forecasts[-1])
    r14 = f14.expected_return_pct
    r30 = f30.expected_return_pct

    rrr = prediction.trade_setup.risk_reward_ratio
    stop_loss = prediction.trade_setup.stop_loss
    target_price = prediction.trade_setup.take_profit_1

    # Base Technical Score [-100, +100] scaled
    base_tech = confluence.score * 0.35 + (r30 * 2.5) + ((rrr - 1.5) * 10.0)

    # Profile & Horizon Bonuses
    bonus = 0.0
    sec = meta["sector"]

    if risk == "CONSERVATIVE":
        # High dividend yield is paramount (e.g. VNM 6.8%, GAS 5.2%, MBB 4.5%, REE 4.0%)
        bonus += div_yield * 10.0
        # Defensive sector bonus
        if sec in ["Energy / Utilities", "Retail / Consumer"]:
            bonus += 25.0
        if symbol in ["VCB", "MBB", "VNM", "GAS", "REE"]:
            bonus += 20.0
        # Volatility penalty
        if sec in ["Real Estate", "Securities"]:
            bonus -= 20.0

    elif risk == "AGGRESSIVE":
        # High beta / momentum / capital gains
        bonus += r30 * 4.0
        if sec in ["Materials", "Securities", "Real Estate"]:
            bonus += 30.0
        if symbol in ["HPG", "SSI", "VND", "TCB", "NVL", "VIC"]:
            bonus += 20.0
        if r14 > 2.0:
            bonus += 15.0

    else:  # MODERATE / BALANCED
        # Core blue chips across Tech, Banking, Materials, Retail
        bonus += div_yield * 3.0
        bonus += r30 * 2.0
        if sec in ["Technology", "Banking", "Materials", "Retail / Consumer"]:
            bonus += 20.0
        if symbol in ["FPT", "MBB", "TCB", "HPG", "MWG", "VCB"]:
            bonus += 20.0

    total_score = round(base_tech + bonus, 2)

    res = {
        "symbol": symbol,
        "company_name": meta["company_name"],
        "sector": meta["sector"],
        "price": current_price,
        "lot_cost": lot_cost,
        "confluence_score": confluence.score,
        "confluence_signal": confluence.signal,
        "prediction_signal": prediction.signal,
        "expected_return_pct": r30,
        "risk_reward_ratio": rrr,
        "target_price": target_price,
        "stop_loss": stop_loss,
        "dividend_yield": div_yield,
        "composite_score": total_score,
        "quote": quote,
        "meta": meta,
    }
    _CANDIDATE_SCORE_CACHE[cache_key] = dict(res)
    return res


def generate_strategic_notes(
    budget: float,
    total_invested: float,
    cash_remainder: float,
    cash_pct: float,
    risk: str,
    horizon: str,
    stock_allocations: List[Any],
) -> List[str]:
    """Generates comprehensive, institutional-grade strategic notes."""
    notes = [
        f"Portfolio constructed for {risk} profile with {cash_pct:.1f}% cash buffer ({cash_remainder:,.0f} VND) preserving liquidity for fee friction and market pullbacks.",
        f"Execution strictly complies with Circular 120/2020/TT-BTC enforcing standard 100-share integer whole lots (zero fractional shares) on HOSE.",
        "Staged limit orders are strongly recommended near daily support pivots (S1) to avoid chasing opening volatility or exchange ceiling price limits (+7% HOSE).",
        "Quarterly rebalancing recommended, or whenever individual position weights deviate by more than 5.0% from target allocations."
    ]
    if risk == "CONSERVATIVE":
        notes.append("Capital preservation prioritized: overweight high-dividend cash-flow generators and defensive utilities with low portfolio beta.")
    elif risk == "AGGRESSIVE":
        notes.append("High-beta tactical posture: strict stop-loss adherence is mandatory to contain tail-risk drawdowns in cyclical growth leaders.")
    return notes


def generate_stock_rationale(candidate: Dict[str, Any], risk: str) -> str:
    """Generates detailed, contextual narrative rationale for a stock pick."""
    sym = candidate["symbol"]
    sec = candidate["sector"]
    c_score = candidate["confluence_score"]
    c_sig = candidate["confluence_signal"]
    r30 = candidate["expected_return_pct"]
    target = candidate["target_price"]
    sl = candidate["stop_loss"]
    rrr = candidate["risk_reward_ratio"]
    div = candidate["dividend_yield"]

    if risk == "CONSERVATIVE":
        role = f"defensive income anchor with {div:.1f}% dividend yield"
    elif risk == "AGGRESSIVE":
        role = f"high-beta momentum champion targeting {target:,.0f} VND (+{r30:.1f}%)"
    else:
        role = "core sector leader with robust 5-pillar technical confluence"

    return (
        f"{candidate['company_name']} ({sym}) selected as {role}. "
        f"Technical confluence: {c_score:+.1f} ({c_sig}), projected target: {target:,.0f} VND, "
        f"stop-loss: {sl:,.0f} VND (RRR: {rrr:.2f})."
    )
