# Original User Request

## Initial Request — 2026-10-29T18:00:00Z

Build an interactive web prototype for Vietnamese stock market analysis and prediction, featuring personalized investment strategy recommendations based on user budget and preferences, applying `ui-ux-pro-max` design guidelines.

### Core Requirements:
- R1: Interactive Web Application Prototype (FastAPI + TradingView Lightweight Charts v4.x + ApexCharts SPA).
- R2: Vietnam Stock Market Data Integration (VN-Index, VN30, HNX, UPCOM, 20 key blue chips via CafeF / Yahoo Finance fallback, 3-tier cache).
- R3: Market Prediction & Trend Analysis (SMA 20/50/200, EMA 12/26, RSI 14, MACD 12/26/9, Bollinger Bands 20/2, ATR 14, 5-Pillar Confluence scoring [-100, +100], Damped Holt forecast for 7/14/30d, volatility cones 80%/95%, S/R pivots, trade setups with RRR >= 1.5).
- R4: Budget & Preference-Based Investment Strategy Advisory (Discrete Knapsack optimizer enforcing strict 100-share integer whole lots per Circular 120/2020/TT-BTC, risk tiers, sector filtering).
- R5: Professional Financial UI/UX (ui-ux-pro-max Dark OLED institutional terminal, Vietnamese 5-state colors: Purple/Ceiling, Cyan/Floor, Green/Up, Red/Down, Yellow/Ref).
- Windows OS, Python 3.13, Node.js/npm is NOT installed. Pure Python standard library (math, typing, pydantic) + static vendor assets. Single startup command `python run.py`.
