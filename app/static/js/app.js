/**
 * VN-Advisor | Single-Page Application Client Controller
 * Milestone 5 (M5_UI)
 */

// Global Application State
const state = {
  currentView: "market",
  selectedStock: "FPT",
  historyDays: 90,
  theme: "dark",
  marketIndices: [],
  universeStocks: [],
  chartInstance: null,
  candleSeries: null,
  volumeSeries: null,
  donutChartInstance: null,
};

// ==============================================================================
// Utility Formatters
// ==============================================================================

function formatVND(value) {
  if (value === null || value === undefined || isNaN(value)) return "-- ₫";
  return new Intl.NumberFormat("vi-VN", {
    style: "currency",
    currency: "VND",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatRawVND(value) {
  if (value === null || value === undefined || isNaN(value)) return "--";
  return new Intl.NumberFormat("vi-VN", {
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPct(value) {
  if (value === null || value === undefined || isNaN(value)) return "--%";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function getStateBadgeClass(st) {
  const s = (st || "REF").toUpperCase();
  switch (s) {
    case "CEILING":
      return "badge-ceil-bg";
    case "FLOOR":
      return "badge-floor-bg";
    case "UP":
      return "badge-up-bg";
    case "DOWN":
      return "badge-down-bg";
    default:
      return "badge-ref-bg";
  }
}

function getStateTextClass(st) {
  const s = (st || "REF").toUpperCase();
  switch (s) {
    case "CEILING":
      return "state-ceil";
    case "FLOOR":
      return "state-floor";
    case "UP":
      return "state-up";
    case "DOWN":
      return "state-down";
    default:
      return "state-ref";
  }
}

// ==============================================================================
// View Navigation Router
// ==============================================================================

function switchView(viewName) {
  state.currentView = viewName;
  const views = ["market", "stock", "advisory"];

  views.forEach((v) => {
    const section = document.getElementById(`view-${v}`);
    const tabBtn = document.getElementById(`tab-${v}`);

    if (v === viewName) {
      if (section) {
        section.classList.remove("hidden");
        section.classList.add("active");
      }
      if (tabBtn) {
        tabBtn.classList.add("active");
        tabBtn.setAttribute("aria-selected", "true");
      }
    } else {
      if (section) {
        section.classList.remove("active");
        section.classList.add("hidden");
      }
      if (tabBtn) {
        tabBtn.classList.remove("active");
        tabBtn.setAttribute("aria-selected", "false");
      }
    }
  });

  // Handle specific view hooks
  if (viewName === "stock") {
    setTimeout(() => {
      loadStockDetails(state.selectedStock);
    }, 50);
  } else if (viewName === "advisory") {
    if (!state.donutChartInstance) {
      initAdvisoryDonut();
    }
  }
}

function toggleTheme() {
  state.theme = state.theme === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", state.theme);
  const btn = document.getElementById("theme-toggle");
  if (btn) {
    btn.textContent = state.theme === "dark" ? "🌙 Dark OLED" : "☀️ Light Mode";
  }
}

// ==============================================================================
// View 1: Market Overview Feeds
// ==============================================================================

async function loadMarketOverview() {
  try {
    // 1. Fetch Major Indices
    const indicesRes = await fetch("/api/market/indices");
    if (indicesRes.ok) {
      const indices = await indicesRes.json();
      state.marketIndices = indices;
      renderIndices(indices);
      renderTickerRibbon(indices);
    }

    // 2. Fetch Market Breadth
    const breadthRes = await fetch("/api/market/breadth");
    if (breadthRes.ok) {
      const breadth = await breadthRes.json();
      renderMarketBreadth(breadth);
    }

    // 3. Fetch Foreign Net Flow
    const foreignRes = await fetch("/api/market/foreign-flow");
    if (foreignRes.ok) {
      const foreign = await foreignRes.json();
      renderForeignFlow(foreign);
    }

    // 4. Fetch 20 Universe Stock Quotes
    const stocksRes = await fetch("/api/market/stocks");
    if (stocksRes.ok) {
      const stocks = await stocksRes.json();
      state.universeStocks = stocks;
      renderWatchlistTable(stocks);
    }
  } catch (err) {
    console.error("Failed to load market overview feeds:", err);
  }
}

function renderTickerRibbon(indices) {
  const ribbon = document.getElementById("ticker-ribbon");
  if (!ribbon || !indices.length) return;

  ribbon.innerHTML = indices
    .map((idx) => {
      const textCls = getStateTextClass(idx.state);
      const sign = idx.change > 0 ? "+" : "";
      return `
        <span class="ticker-item" onclick="selectStock('${idx.symbol}')">
          <strong>${idx.symbol}:</strong>
          <span class="tabular-nums ${textCls}">${idx.value.toFixed(2)} (${sign}${idx.change.toFixed(2)} / ${formatPct(idx.pct_change)})</span>
        </span>
      `;
    })
    .join("");
}

function renderIndices(indices) {
  indices.forEach((idx) => {
    let prefix = "vnindex";
    if (idx.symbol === "VN30INDEX") prefix = "vn30";
    else if (idx.symbol === "HNX-INDEX") prefix = "hnx";
    else if (idx.symbol === "UPCOM-INDEX") prefix = "upcom";

    const valEl = document.getElementById(`idx-${prefix}-val`);
    const chgEl = document.getElementById(`idx-${prefix}-chg`);

    if (valEl) {
      valEl.textContent = idx.value.toFixed(2);
      valEl.className = `index-value tabular-nums ${getStateTextClass(idx.state)}`;
    }
    if (chgEl) {
      const sign = idx.change > 0 ? "+" : "";
      chgEl.textContent = `${sign}${idx.change.toFixed(2)} (${formatPct(idx.pct_change)})`;
      chgEl.className = `index-change-row tabular-nums ${getStateTextClass(idx.state)}`;
    }
  });
}

function renderMarketBreadth(b) {
  const total = b.total || 20;
  const ceilPct = ((b.ceiling || 0) / total) * 100;
  const upPct = ((b.up || 0) / total) * 100;
  const refPct = ((b.ref || 0) / total) * 100;
  const downPct = ((b.down || 0) / total) * 100;
  const floorPct = ((b.floor || 0) / total) * 100;

  const bar = document.getElementById("breadth-bar");
  if (bar) {
    bar.innerHTML = `
      <div class="breadth-segment seg-ceil" style="width: ${ceilPct}%;" title="Trần: ${b.ceiling}"></div>
      <div class="breadth-segment seg-up" style="width: ${upPct}%;" title="Tăng: ${b.up}"></div>
      <div class="breadth-segment seg-ref" style="width: ${refPct}%;" title="Tham chiếu: ${b.ref}"></div>
      <div class="breadth-segment seg-down" style="width: ${downPct}%;" title="Giảm: ${b.down}"></div>
      <div class="breadth-segment seg-floor" style="width: ${floorPct}%;" title="Sàn: ${b.floor}"></div>
    `;
  }

  const sumEl = document.getElementById("breadth-summary");
  if (sumEl) {
    if ((b.up || 0) >= (b.down || 0)) {
      sumEl.textContent = `Thị trường Tích cực (${b.up} Mã Tăng / ${total})`;
      sumEl.className = "badge badge-up-bg";
    } else {
      sumEl.textContent = `Áp lực Điều chỉnh (${b.down} Mã Giảm / ${total})`;
      sumEl.className = "badge badge-down-bg";
    }
  }

  document.getElementById("cnt-ceil").textContent = `🟣 Trần: ${b.ceiling || 0}`;
  document.getElementById("cnt-up").textContent = `🟢 Tăng: ${b.up || 0}`;
  document.getElementById("cnt-ref").textContent = `🟡 TC: ${b.ref || 0}`;
  document.getElementById("cnt-down").textContent = `🔴 Giảm: ${b.down || 0}`;
  document.getElementById("cnt-floor").textContent = `🔵 Sàn: ${b.floor || 0}`;
}

function renderForeignFlow(data) {
  const net = data.net_value_vnd || 0;
  const badge = document.getElementById("foreign-net-badge");
  const valEl = document.getElementById("foreign-total-net");

  if (valEl) {
    valEl.textContent = formatVND(net);
    valEl.className = `stat-number tabular-nums ${net >= 0 ? "state-up" : "state-down"}`;
  }

  if (badge) {
    badge.textContent = net >= 0 ? "MUA RÒNG" : "BÁN RÒNG";
    badge.className = `badge ${net >= 0 ? "badge-up-bg" : "badge-down-bg"}`;
  }
}

function renderWatchlistTable(stocks) {
  const tbody = document.getElementById("market-watchlist-tbody");
  if (!tbody) return;

  if (!stocks || !stocks.length) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;">Không có dữ liệu cổ phiếu</td></tr>`;
    return;
  }

  tbody.innerHTML = stocks
    .map((s) => {
      const stateCls = getStateTextClass(s.state);
      const badgeCls = getStateBadgeClass(s.state);
      const sign = s.change > 0 ? "+" : "";

      return `
        <tr onclick="selectStock('${s.symbol}')">
          <td><strong style="color: var(--accent-blue);">${s.symbol}</strong></td>
          <td style="max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${s.company_name || s.symbol}</td>
          <td><span style="font-size:0.75rem; color:var(--text-muted);">${s.exchange || "HOSE"}</span></td>
          <td><span style="font-size:0.8rem; color:var(--text-secondary);">${s.sector || "--"}</span></td>
          <td style="text-align: right;" class="tabular-nums ${stateCls}"><strong>${formatRawVND(s.price)}</strong></td>
          <td style="text-align: right;" class="tabular-nums ${stateCls}">${sign}${formatRawVND(s.change)}</td>
          <td style="text-align: right;" class="tabular-nums ${stateCls}">${formatPct(s.pct_change)}</td>
          <td style="text-align: right;" class="tabular-nums">${formatRawVND(s.volume)}</td>
          <td style="text-align: center;"><span class="badge ${badgeCls}">${s.state}</span></td>
        </tr>
      `;
    })
    .join("");
}

// ==============================================================================
// View 2: Stock Deep-Dive, Charting & Prediction
// ==============================================================================

function selectStock(symbol) {
  state.selectedStock = symbol;
  const select = document.getElementById("stock-ticker-select");
  if (select) {
    select.value = symbol;
  }
  switchView("stock");
  loadStockDetails(symbol);
}

function onStockSelectChange(symbol) {
  state.selectedStock = symbol;
  loadStockDetails(symbol);
}

function setTimeframe(days, btn) {
  state.historyDays = days;
  document.querySelectorAll(".timeframe-btn").forEach((b) => b.classList.remove("active"));
  if (btn) btn.classList.add("active");
  loadStockDetails(state.selectedStock);
}

async function loadStockDetails(symbol) {
  try {
    // 1. Fetch Quote
    const quoteRes = await fetch(`/api/stock/quote/${symbol}`);
    if (quoteRes.ok) {
      const quote = await quoteRes.json();
      renderStockHeader(quote);
    }

    // 2. Fetch Candlestick History
    const histRes = await fetch(`/api/stock/history/${symbol}?days=${state.historyDays}`);
    if (histRes.ok) {
      const bars = await histRes.json();
      renderStockChart(bars);
    }

    // 3. Fetch Technical Indicators
    const indRes = await fetch(`/api/stock/indicators/${symbol}`);
    if (indRes.ok) {
      const ind = await indRes.json();
      renderIndicators(ind);
    }

    // 4. Fetch Trend Prediction & Volatility Cones
    const predRes = await fetch(`/api/stock/prediction/${symbol}`);
    if (predRes.ok) {
      const pred = await predRes.json();
      renderPredictionAndSetup(pred);
    }
  } catch (err) {
    console.error(`Failed to load details for ${symbol}:`, err);
  }
}

function renderStockHeader(q) {
  const badgeBox = document.getElementById("stock-live-badge-box");
  if (badgeBox) {
    const badgeCls = getStateBadgeClass(q.state);
    const sign = q.change > 0 ? "+" : "";
    badgeBox.innerHTML = `
      <span class="badge ${badgeCls}">${q.exchange || "HOSE"} · ${q.state}</span>
      <span class="tabular-nums" style="font-weight:700; margin-left: 8px;">${formatVND(q.price)}</span>
      <span class="tabular-nums ${getStateTextClass(q.state)}" style="font-size:0.85rem; margin-left: 4px;">
        ${sign}${formatRawVND(q.change)} (${formatPct(q.pct_change)})
      </span>
    `;
  }
}

function renderStockChart(bars) {
  const container = document.getElementById("tradingview-chart-box");
  if (!container || !window.LightweightCharts) return;

  // Initialize or re-render chart instance
  if (!state.chartInstance) {
    state.chartInstance = window.LightweightCharts.createChart(container, {
      layout: {
        background: { color: "#111827" },
        textColor: "#94A3B8",
      },
      grid: {
        vertLines: { color: "#1F2937" },
        horzLines: { color: "#1F2937" },
      },
    });

    state.candleSeries = state.chartInstance.addCandlestickSeries({
      upColor: "#10B981",
      downColor: "#EF4444",
      borderUpColor: "#10B981",
      borderDownColor: "#EF4444",
      wickUpColor: "#10B981",
      wickDownColor: "#EF4444",
    });

    state.volumeSeries = state.chartInstance.addHistogramSeries({
      color: "rgba(59, 130, 246, 0.4)",
      priceFormat: { type: "volume" },
    });
  }

  // Map candles to Lightweight Charts format
  const candleData = bars.map((b) => ({
    time: b.time,
    open: b.open,
    high: b.high,
    low: b.low,
    close: b.close,
  }));

  const volumeData = bars.map((b) => ({
    time: b.time,
    value: b.volume,
    color: b.close >= b.open ? "rgba(16, 185, 129, 0.4)" : "rgba(239, 68, 68, 0.4)",
  }));

  if (state.candleSeries) {
    state.candleSeries.setData(candleData);
  }
  if (state.volumeSeries) {
    state.volumeSeries.setData(volumeData);
  }
  if (state.chartInstance && state.chartInstance.timeScale) {
    state.chartInstance.timeScale().fitContent();
  }
}

function renderIndicators(ind) {
  // RSI
  const rsiEl = document.getElementById("stat-rsi");
  if (rsiEl) {
    rsiEl.textContent = ind.rsi14 ? ind.rsi14.toFixed(1) : "--";
    if (ind.rsi14 >= 70) {
      rsiEl.className = "stat-number tabular-nums state-down";
      document.getElementById("stat-rsi-desc").textContent = "Quá Mua (Overbought > 70)";
    } else if (ind.rsi14 <= 30) {
      rsiEl.className = "stat-number tabular-nums state-up";
      document.getElementById("stat-rsi-desc").textContent = "Quá Bán (Oversold < 30)";
    } else {
      rsiEl.className = "stat-number tabular-nums state-ref";
      document.getElementById("stat-rsi-desc").textContent = "Trung Tính (30 - 70)";
    }
  }

  // MACD
  const macdEl = document.getElementById("stat-macd");
  if (macdEl && ind.macd) {
    macdEl.textContent = `${ind.macd.histogram > 0 ? "+" : ""}${ind.macd.histogram.toFixed(1)}`;
    macdEl.className = `stat-number tabular-nums ${ind.macd.histogram >= 0 ? "state-up" : "state-down"}`;
    document.getElementById("stat-macd-desc").textContent = `Hist: ${ind.macd.histogram.toFixed(1)} · Line: ${ind.macd.line.toFixed(1)}`;
  }

  // Bollinger Bands
  const bbEl = document.getElementById("stat-bb");
  if (bbEl && ind.bollinger) {
    bbEl.textContent = `${formatRawVND(ind.bollinger.upper)} / ${formatRawVND(ind.bollinger.lower)}`;
    document.getElementById("stat-bb-desc").textContent = `Giữa: ${formatRawVND(ind.bollinger.middle)} VND`;
  }

  // Confluence Score & Signal
  const confEl = document.getElementById("stat-confluence");
  const confSigEl = document.getElementById("stat-confluence-signal");
  if (confEl && confSigEl) {
    const score = ind.confluence_score || 0;
    confEl.textContent = `${score > 0 ? "+" : ""}${score.toFixed(1)} / 100`;
    confSigEl.textContent = ind.confluence_signal || "NEUTRAL";

    if (score >= 20) {
      confEl.className = "stat-number tabular-nums state-up";
      confSigEl.className = "state-up";
    } else if (score <= -20) {
      confEl.className = "stat-number tabular-nums state-down";
      confSigEl.className = "state-down";
    } else {
      confEl.className = "stat-number tabular-nums state-ref";
      confSigEl.className = "state-ref";
    }
  }
}

function renderPredictionAndSetup(pred) {
  // Confidence Badge
  const badge = document.getElementById("pred-confidence-badge");
  if (badge) {
    badge.textContent = `Độ Tin Cậy: ${pred.confidence_score.toFixed(1)}% · Tín Hiệu: ${pred.signal}`;
  }

  // Forecast Targets
  if (pred.forecasts && pred.forecasts.length >= 3) {
    const f7 = pred.forecasts.find((f) => f.horizon_days === 7);
    const f14 = pred.forecasts.find((f) => f.horizon_days === 14);
    const f30 = pred.forecasts.find((f) => f.horizon_days === 30);

    if (f7) {
      document.getElementById("f7-target").textContent = formatVND(f7.target_price);
      document.getElementById("f7-return").textContent = formatPct(f7.expected_return_pct);
      document.getElementById("f7-return").className = `forecast-return tabular-nums ${f7.expected_return_pct >= 0 ? "state-up" : "state-down"}`;
      document.getElementById("f7-cone").textContent = `80%: [${formatRawVND(f7.lower_80)} - ${formatRawVND(f7.upper_80)}]`;
    }
    if (f14) {
      document.getElementById("f14-target").textContent = formatVND(f14.target_price);
      document.getElementById("f14-return").textContent = formatPct(f14.expected_return_pct);
      document.getElementById("f14-return").className = `forecast-return tabular-nums ${f14.expected_return_pct >= 0 ? "state-up" : "state-down"}`;
      document.getElementById("f14-cone").textContent = `80%: [${formatRawVND(f14.lower_80)} - ${formatRawVND(f14.upper_80)}]`;
    }
    if (f30) {
      document.getElementById("f30-target").textContent = formatVND(f30.target_price);
      document.getElementById("f30-return").textContent = formatPct(f30.expected_return_pct);
      document.getElementById("f30-return").className = `forecast-return tabular-nums ${f30.expected_return_pct >= 0 ? "state-up" : "state-down"}`;
      document.getElementById("f30-cone").textContent = `80%: [${formatRawVND(f30.lower_80)} - ${formatRawVND(f30.upper_80)}]`;
    }
  }

  // Pivots
  if (pred.support_resistance) {
    const sr = pred.support_resistance;
    document.getElementById("pivot-r2").textContent = formatVND(sr.r2);
    document.getElementById("pivot-r1").textContent = formatVND(sr.r1);
    document.getElementById("pivot-p").textContent = formatVND(sr.p || sr.pivot);
    document.getElementById("pivot-s1").textContent = formatVND(sr.s1);
    document.getElementById("pivot-s2").textContent = formatVND(sr.s2);
  }

  // Trade Setup
  if (pred.trade_setup) {
    const ts = pred.trade_setup;
    document.getElementById("trade-rrr-badge").textContent = `RRR: ${ts.risk_reward_ratio ? ts.risk_reward_ratio.toFixed(2) : "1.80"}`;
    if (ts.entry_zone && ts.entry_zone.length >= 2) {
      document.getElementById("trade-entry").textContent = `${formatRawVND(ts.entry_zone[0])} - ${formatRawVND(ts.entry_zone[1])}`;
    }
    document.getElementById("trade-sl").textContent = formatRawVND(ts.stop_loss);
    document.getElementById("trade-tp1").textContent = formatRawVND(ts.take_profit_1);
    document.getElementById("trade-tp2").textContent = formatRawVND(ts.take_profit_2);
  }
}

// ==============================================================================
// View 3: Personalized Knapsack Advisory Console
// ==============================================================================

function initAdvisoryDonut(series = [75, 25], labels = ["Cổ Phiếu Đã Mua", "Tiền Mặt Dự Phòng"]) {
  const container = document.getElementById("apex-donut-box");
  if (!container || !window.ApexCharts) return;

  if (state.donutChartInstance) {
    state.donutChartInstance.destroy();
  }

  state.donutChartInstance = new window.ApexCharts(container, {
    series: series,
    labels: labels,
    colors: ["#3B82F6", "#10B981", "#F59E0B", "#A855F7", "#EF4444", "#06B6D4"],
  });

  state.donutChartInstance.render();
}

async function handleAdvisorySubmit(e) {
  e.preventDefault();
  const btn = document.getElementById("btn-run-advisory");
  if (btn) btn.textContent = "Đang Tối Ưu Hóa Knapsack...";

  const budget = parseFloat(document.getElementById("input-budget").value) || 50000000;
  const risk = document.querySelector('input[name="risk_level"]:checked')?.value || "MODERATE";
  const horizon = document.querySelector('input[name="horizon"]:checked')?.value || "MEDIUM_TERM";

  const selectedSectors = [];
  document.querySelectorAll('input[name="sector"]:checked').forEach((cb) => {
    selectedSectors.push(cb.value);
  });

  const payload = {
    budget: budget,
    risk_level: risk,
    horizon: horizon,
    sectors: selectedSectors.length ? selectedSectors : undefined,
  };

  try {
    const res = await fetch("/api/advisory/recommend", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (res.ok) {
      const data = await res.json();
      renderAdvisoryResults(data);
    } else {
      const err = await res.json();
      alert(`Lỗi phân bổ: ${err.detail || "Không thể tối ưu danh mục"}`);
    }
  } catch (err) {
    console.error("Advisory error:", err);
    alert("Không thể kết nối đến máy chủ cố vấn.");
  } finally {
    if (btn) btn.textContent = "Tối Ưu Hóa Danh Mục Knapsack (Lô 100)";
  }
}

function renderAdvisoryResults(data) {
  // 1. Balance Indicators
  document.getElementById("adv-budget-display").textContent = formatVND(data.budget_vnd);
  document.getElementById("adv-invested-display").textContent = formatVND(data.total_invested_vnd);
  document.getElementById("adv-cash-display").textContent = `${formatVND(data.cash_remainder_vnd)} (${data.cash_pct.toFixed(1)}%)`;

  const badge = document.getElementById("adv-conservation-badge");
  const isConserved = Math.abs((data.total_invested_vnd + data.cash_remainder_vnd) - data.budget_vnd) < 1.0;
  badge.textContent = isConserved ? "100% Khớp Lô & Bảo Toàn" : "Đã Kiểm Tra";
  badge.className = `badge ${isConserved ? "badge-up-bg" : "badge-ref-bg"}`;

  // 2. Metrics Summary
  if (data.summary_metrics) {
    const sm = data.summary_metrics;
    document.getElementById("adv-metrics-summary").textContent =
      `Lợi Nhuận Kỳ Vọng: ${formatPct(sm.expected_return_pct)} · Sharpe: ${sm.sharpe_ratio.toFixed(2)} · Cổ Tức: ${formatPct(sm.dividend_yield_est_pct)}`;
  }

  // 3. Asset Allocation Donut
  if (data.stock_allocations && data.stock_allocations.length > 0) {
    const series = data.stock_allocations.map((s) => s.weight_pct);
    const labels = data.stock_allocations.map((s) => s.symbol);

    if (data.cash_pct > 0.05) {
      series.push(data.cash_pct);
      labels.push("Tiền Mặt Dự Phòng");
    }

    initAdvisoryDonut(series, labels);
  } else {
    initAdvisoryDonut([100], ["100% Tiền Mặt Dự Phòng (Vốn Nhỏ)"]);
  }

  // 4. Stock Table
  const tbody = document.getElementById("advisory-stocks-tbody");
  if (tbody) {
    if (!data.stock_allocations || !data.stock_allocations.length) {
      tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding: 20px;">Vốn khả dụng dưới mức tối thiểu cho 1 lô 100 cổ phiếu. Bảo toàn 100% tiền mặt.</td></tr>`;
    } else {
      tbody.innerHTML = data.stock_allocations
        .map((s) => {
          return `
            <tr>
              <td><strong style="color:var(--accent-blue);">${s.symbol}</strong></td>
              <td>${s.company_name}</td>
              <td><span style="font-size:0.8rem; color:var(--text-secondary);">${s.sector}</span></td>
              <td style="text-align: right;" class="tabular-nums">${formatRawVND(s.current_price_vnd)}</td>
              <td style="text-align: right;" class="tabular-nums"><strong>${s.allocated_lots} lô</strong></td>
              <td style="text-align: right;" class="tabular-nums">${formatRawVND(s.allocated_shares)} cp</td>
              <td style="text-align: right;" class="tabular-nums state-up"><strong>${formatVND(s.total_cost_vnd)}</strong></td>
              <td style="text-align: right;" class="tabular-nums">${s.weight_pct.toFixed(1)}%</td>
              <td style="text-align: center;"><span class="badge badge-up-bg">${s.signal || "BUY"}</span></td>
            </tr>
          `;
        })
        .join("");
    }
  }

  // 5. Strategic Notes
  const notesList = document.getElementById("adv-notes-list");
  if (notesList && data.strategic_notes) {
    notesList.innerHTML = data.strategic_notes
      .map((n) => `<li>${n}</li>`)
      .join("");
  }
}

// ==============================================================================
// Initialization on DOMContentLoaded
// ==============================================================================

document.addEventListener("DOMContentLoaded", () => {
  // Default to market overview
  loadMarketOverview();
  // Auto-run initial advisory recommendation for 50M
  setTimeout(() => {
    const form = document.getElementById("advisory-form");
    if (form) {
      handleAdvisorySubmit(new Event("submit"));
    }
  }, 300);
});
