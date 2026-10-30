# 📈 VN-Advisor | Hệ Thống Phân Tích, Dự Báo & Cố Vấn Đầu Tư Chứng Khoán Việt Nam

[![Python Version](https://img.shields.io/badge/Python-3.13%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![TradingView](https://img.shields.io/badge/Charts-Lightweight%20Charts-2962FF.svg)](https://www.tradingview.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Regulatory](https://img.shields.io/badge/Compliance-TT120%2F2020%2FTT--BTC-purple.svg)](https://thuvienphapluat.vn/)

Hệ thống web tài chính phân tích kỹ thuật, dự báo xu hướng định lượng và tư vấn chiến thuật phân bổ danh mục cổ phiếu Việt Nam (HOSE, HNX, UPCoM) tuân thủ quy chuẩn giao dịch lô 100 cổ phiếu.

---

## 🌟 Tính Năng Nổi Bật

### 1. 📊 Tầng Dữ Liệu Thị Trường Trực Tiếp (Market Data Layer)
- **Đa sàn giao dịch:** Cập nhật liên tục chỉ số VN-Index, VN30-Index, HNX-Index, UPCOM-Index và 20 cổ phiếu Blue-chip thanh khoản cao.
- **Dual-Source Engine:** Tích hợp nguồn dữ liệu CafeF và Yahoo Finance với cơ chế tự động phục hồi lỗi và snapshot hạt giống dự phòng.
- **Cache 3 Tầng:** Bộ nhớ RAM TTL + Disk Cache JSON + Fallback Seed đảm bảo độ trễ sub-millisecond (< 1ms).
- **Quy chế biên độ sàn Việt Nam:** Tự động áp dụng trần/sàn theo quy định HOSE (±7%), HNX (±10%), UPCoM (±15%).

### 2. 📉 Phân Tích Kỹ Thuật & Dự Báo Định Lượng (Analytics & Forecasting)
- **7 Chỉ báo kỹ thuật thuần Python:** SMA (20, 50, 200), EMA (12, 26), Wilder RSI-14, MACD (12, 26, 9), Bollinger Bands (20, 2), ATR-14, Volume Surge Factor.
- **Chấm điểm hợp lưu (Confluence Scoring):** Tổng hợp 5 trụ cột kỹ thuật ra thang điểm từ -100 đến +100 để xác định tín hiệu: `MUA MẠNH`, `MUA`, `TÍCH LŨY`, `TRUNG TÍNH`, `BÁN`.
- **Mô hình dự báo Damped Holt Exponential Smoothing:** Dự phóng quỹ đạo giá tương lai qua 3 mốc thời gian 7 ngày, 14 ngày, 30 ngày.
- **Dải nón biến động (Volatility Cones):** Dải xác suất tin cậy 80% ($1.28\sigma$) và 95% ($1.96\sigma$).
- **Điểm xoay Pivot & Kế hoạch giao dịch:** Xác định ngưỡng cản R1, R2, hỗ trợ S1, S2 và thiết lập điểm Entry, Stop Loss, Take Profit với tỷ lệ $RRR \ge 1.5$.

### 3. 🎯 Động Cơ Tư Vấn Danh Mục Knapsack (Portfolio Advisory)
- **Quy hoạch động Knapsack lô 100:** Phân bổ tối ưu từng lô nguyên 100 cổ phiếu theo **Thông tư 120/2020/TT-BTC** của Bộ Tài chính, triệt tiêu hoàn toàn rủi ro mua dính lô lẻ.
- **Bảo toàn ngân sách tuyệt đối:** $\text{Tổng tiền mua CP} + \text{Tiền mặt khả dụng} == \text{Vốn ban đầu}$ trên mọi dải ngân sách từ 1 triệu VNĐ đến 10 tỷ VNĐ.
- **3 Hồ sơ khẩu vị rủi ro:**
  - *Thận trọng (Conservative):* Giữ $\ge 15\%$ tiền mặt dự phòng, ưu tiên cổ phiếu phòng thủ và cổ tức cao.
  - *Cân bằng (Moderate):* Triển khai $> 70\%$ vốn, đa dạng hóa đa ngành (giới hạn trần ngành $\le 35\%$).
  - *Tăng trưởng (Aggressive):* Tỷ lệ giải ngân cao $\ge 85\%$, đón đầu các nhóm ngành biến động lớn.

### 4. 💻 Giao Diện FinTech Dark OLED (ui-ux-pro-max)
- Bảng màu Dark OLED chuyên nghiệp, độ tương phản cao, chống mỏi mắt.
- Chuẩn hóa 5 màu quy ước thị trường chứng khoán Việt Nam: **Tím (Trần)** - **Xanh lơ (Sàn)** - **Xanh lá (Tăng)** - **Đỏ (Giảm)** - **Vàng (Tham chiếu)**.
- Biểu đồ nến tương tác chuẩn TradingView Lightweight Charts và biểu đồ phân bổ ApexCharts.
- Phông chữ tài chính ép định dạng số `font-variant-numeric: tabular-nums` chống giật số khi cập nhật.

---

## 🛠️ Công Nghệ Sử Dụng

- **Backend:** Python 3.13, FastAPI, Uvicorn, Pydantic v2
- **Frontend:** Single-Page Application (HTML5, Vanilla CSS3 với CSS Variables, JavaScript ES6+)
- **Charting Engine:** TradingView Lightweight Charts v4.x, ApexCharts
- **Testing:** Pytest (205 bài kiểm thử tự động, độ bao phủ E2E Tiers 1-4)

---

## 🚀 Hướng Dẫn Cài Đặt & Chạy Cục Bộ

### 1. Yêu cầu hệ thống
- Python 3.10 trở lên (khuyên dùng Python 3.13)
- Git

### 2. Khởi chạy
```bash
# Clone repository
git clone <URL_REPO_CUA_BAN>
cd vn_stock_advisor

# Cài đặt thư viện phụ thuộc
pip install -r requirements.txt

# Khởi chạy máy chủ
python run.py
```

Mở trình duyệt tại:
- **Ứng dụng Web:** [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Swagger UI REST API:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 🧪 Chạy Kiểm Thử Tự Động (Test Suite)

```bash
# Chạy toàn bộ 205 bài kiểm thử đơn vị, stress test và E2E
pytest

# Hoặc chạy trình kiểm thử tổng quan
python tests/run_tests.py
```

---

## 📜 Giấy Phép & Tuyên Bố Miễn Trừ Trách Nhiệm (Disclaimer)
- Dự án được phát triển dưới giấy phép **MIT License**.
- **Miễn trừ trách nhiệm:** Thông tin, mô hình dự báo và khuyến nghị danh mục do hệ thống đưa ra chỉ mang tính chất tham khảo học thuật và phân tích dữ liệu, không phải là lời mời chào mua bán chứng khoán hay tư vấn tài chính ủy thác. Nhà đầu tư tự chịu trách nhiệm về quyết định của mình trên thị trường.
