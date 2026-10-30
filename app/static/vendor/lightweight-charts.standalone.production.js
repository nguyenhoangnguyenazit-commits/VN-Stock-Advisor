/**
 * TradingView Lightweight Charts - Standalone Bundle / Fallback Engine
 * Provides window.LightweightCharts API
 */
(function(root, factory) {
  if (typeof exports === 'object' && typeof module !== 'undefined') {
    module.exports = factory();
  } else if (typeof define === 'function' && define.amd) {
    define(factory);
  } else {
    root.LightweightCharts = factory();
  }
})(typeof self !== 'undefined' ? self : this, function() {
  return {
    version: function() { return "4.2.0"; },
    createChart: function(container, options) {
      if (typeof container === 'string') {
        container = document.getElementById(container);
      }
      if (!container) return null;
      container.innerHTML = "";
      var canvas = document.createElement("canvas");
      canvas.width = container.clientWidth || 800;
      canvas.height = container.clientHeight || 400;
      canvas.style.width = "100%";
      canvas.style.height = "100%";
      container.appendChild(canvas);
      var ctx = canvas.getContext("2d");

      var seriesList = [];

      var chartInstance = {
        addCandlestickSeries: function(seriesOptions) {
          var series = {
            type: "candlestick",
            options: seriesOptions || {},
            data: [],
            setData: function(data) {
              this.data = data || [];
              chartInstance._render();
            },
            update: function(bar) {
              this.data.push(bar);
              chartInstance._render();
            }
          };
          seriesList.push(series);
          return series;
        },
        addHistogramSeries: function(seriesOptions) {
          var series = {
            type: "histogram",
            options: seriesOptions || {},
            data: [],
            setData: function(data) {
              this.data = data || [];
              chartInstance._render();
            }
          };
          seriesList.push(series);
          return series;
        },
        addLineSeries: function(seriesOptions) {
          var series = {
            type: "line",
            options: seriesOptions || {},
            data: [],
            setData: function(data) {
              this.data = data || [];
              chartInstance._render();
            }
          };
          seriesList.push(series);
          return series;
        },
        timeScale: function() {
          return {
            fitContent: function() { chartInstance._render(); },
            scrollToPosition: function() {}
          };
        },
        applyOptions: function(newOptions) {},
        resize: function(width, height) {
          canvas.width = width;
          canvas.height = height;
          chartInstance._render();
        },
        remove: function() {
          if (container.contains(canvas)) container.removeChild(canvas);
        },
        _render: function() {
          if (!ctx) return;
          var w = canvas.width;
          var h = canvas.height;
          ctx.clearRect(0, 0, w, h);
          // Background
          ctx.fillStyle = options && options.layout && options.layout.background && options.layout.background.color ? options.layout.background.color : "#111827";
          ctx.fillRect(0, 0, w, h);

          // Find candlestick series
          var candleSeries = seriesList.find(function(s) { return s.type === "candlestick"; });
          if (!candleSeries || !candleSeries.data || candleSeries.data.length === 0) return;

          var data = candleSeries.data;
          var minPrice = Infinity, maxPrice = -Infinity;
          for (var i = 0; i < data.length; i++) {
            if (data[i].low < minPrice) minPrice = data[i].low;
            if (data[i].high > maxPrice) maxPrice = data[i].high;
          }
          if (minPrice === maxPrice) { minPrice *= 0.95; maxPrice *= 1.05; }
          var padding = (maxPrice - minPrice) * 0.08;
          minPrice -= padding; maxPrice += padding;

          var chartH = h * 0.8;
          var barW = Math.max(3, (w - 80) / data.length);
          var spacing = barW * 0.2;
          var bodyW = Math.max(2, barW - spacing);

          // Grid lines
          ctx.strokeStyle = "#1F2937";
          ctx.lineWidth = 1;
          for (var g = 1; g < 5; g++) {
            var yGrid = (chartH / 5) * g;
            ctx.beginPath();
            ctx.moveTo(0, yGrid);
            ctx.lineTo(w - 60, yGrid);
            ctx.stroke();
          }

          // Render candles
          for (var j = 0; j < data.length; j++) {
            var d = data[j];
            var x = j * barW + spacing / 2;
            var isUp = d.close >= d.open;
            var color = isUp ? "#10B981" : "#EF4444";

            var yHigh = chartH - ((d.high - minPrice) / (maxPrice - minPrice)) * chartH;
            var yLow = chartH - ((d.low - minPrice) / (maxPrice - minPrice)) * chartH;
            var yOpen = chartH - ((d.open - minPrice) / (maxPrice - minPrice)) * chartH;
            var yClose = chartH - ((d.close - minPrice) / (maxPrice - minPrice)) * chartH;

            // Wick
            ctx.strokeStyle = color;
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.moveTo(x + bodyW / 2, yHigh);
            ctx.lineTo(x + bodyW / 2, yLow);
            ctx.stroke();

            // Candle Body
            ctx.fillStyle = color;
            var bodyTop = Math.min(yOpen, yClose);
            var bodyHeight = Math.max(2, Math.abs(yClose - yOpen));
            ctx.fillRect(x, bodyTop, bodyW, bodyHeight);
          }

          // Volume series if present
          var volSeries = seriesList.find(function(s) { return s.type === "histogram"; });
          if (volSeries && volSeries.data && volSeries.data.length > 0) {
            var maxVol = 0;
            for (var v = 0; v < volSeries.data.length; v++) {
              if (volSeries.data[v].value > maxVol) maxVol = volSeries.data[v].value;
            }
            if (maxVol > 0) {
              var volH = h * 0.18;
              for (var k = 0; k < volSeries.data.length; k++) {
                var vd = volSeries.data[k];
                var vx = k * barW + spacing / 2;
                var vHeight = (vd.value / maxVol) * volH;
                ctx.fillStyle = vd.color || "rgba(59, 130, 246, 0.4)";
                ctx.fillRect(vx, h - vHeight, bodyW, vHeight);
              }
            }
          }
        }
      };

      window.addEventListener("resize", function() {
        if (container.clientWidth > 0 && container.clientHeight > 0) {
          chartInstance.resize(container.clientWidth, container.clientHeight);
        }
      });

      return chartInstance;
    }
  };
});
