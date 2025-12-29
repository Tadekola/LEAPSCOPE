# LEAPSCOPE 🚀

**Professional LEAPS Options Analytics & Decision-Support Platform**

## Overview

**LEAPSCOPE** is a production-grade analytics and decision-support platform for **Long-Term Equity Anticipation Securities (LEAPS)**. It helps traders identify, evaluate, and manage long-dated options on stocks and ETFs using live market data, systematic analysis, and strict risk controls.

LEAPSCOPE is **human-in-the-loop** by design: it provides signals, rankings, and insights — **never auto-executes trades**.

---

## Key Capabilities

### 🔍 Market Scanning
*   **Scans stocks and ETFs** for LEAPS suitability
*   **GO / WATCH / NO_GO** decision framework
*   **Conviction scoring (0–100)** with explainability
*   Rankings by **quality**, not hype

### 📊 Analysis Engine
*   **Technical analysis**: Trend regime, momentum, volatility
*   **Fundamental scoring**: Growth, profitability, balance sheet, stability
*   **Volatility analysis**: IV vs HV, regime awareness
*   **ETF-aware logic**: Customized scoring for ETFs (no inappropriate penalties)

### 🧠 Conviction Scoring
Composite score combining:
1.  Technical strength
2.  Fundamentals (or ETF proxy)
3.  Volatility attractiveness
4.  Liquidity quality

**Conviction Bands:**
*   🟢 **STRONG**
*   🟡 **MODERATE**
*   🔴 **WEAK**

### 🧾 Options (LEAPS) Analysis
*   **Live options chains and Greeks** via Tradier
*   **Liquidity-aware filtering** (Open Interest, spreads)
*   **Delta-appropriate** LEAPS candidates (0.70 - 0.80 delta focus)
*   Multiple expirations and strikes surfaced transparently

### 💼 Portfolio Monitoring
*   Persistent portfolio storage (**SQLite + JSON**)
*   **Live mark-to-market pricing**
*   P&L tracking ($ and %)
*   **Risk-aware management signals**:
    *   `TAKE_PROFIT`
    *   `STOP_LOSS`
    *   `TECH_INVALIDATED`
    *   `EXPIRY_REVIEW`
    *   `EARNINGS_RISK`

### 🚨 Alerts & History
*   Persistent alerts (Scanner + Portfolio)
*   Scan history with comparison:
    *   New **GO** signals
    *   Upgrades / Downgrades
    *   Dropped candidates
*   Fully auditable decision trail

### 🖥️ Interactive Dashboard
*   **Streamlit-based UI**
*   Tabs for: Scanner, Portfolio, Scan History, Alerts
*   **Live data indicator** (Tradier vs Fallback)
*   Explainable drill-downs for every symbol

---

## Live Data & Providers

| Data Type | Source |
| :--- | :--- |
| **Live prices** | Tradier |
| **Options chains & Greeks** | Tradier |
| **Implied volatility** | Tradier |
| **Fundamentals** | Yahoo Finance |
| **Earnings dates** | Yahoo Finance |
| **Historical OHLCV** | Yahoo Finance |

🔒 **Security**: Tradier credentials are loaded securely from a `.env` file. **No secrets are hard-coded.**

---

## Safety & Design Principles

*   ❌ **No auto-trading**
*   ❌ **No order submission**
*   ❌ **No execution paths**
*   ✅ **Draft order tickets are always blocked**
*   ✅ **UNKNOWN data never passes decision gates**
*   ✅ **Earnings risk explicitly enforced**
*   ✅ **Human review required for all actions**

LEAPSCOPE is a **decision-support system**, not a trading bot.

---

## Technology Stack

*   **Language**: Python 3.11
*   **Dependency Management**: Poetry
*   **Data Providers**: Tradier, Yahoo Finance
*   **UI**: Streamlit
*   **Storage**: SQLite + JSON
*   **Testing**: Pytest (30+ tests)
*   **Architecture**: Modular, provider-abstracted, config-driven

---

## Project Structure

```text
LeapScope/
├── src/
│   ├── analysis/        # Technical & fundamental analysis
│   ├── scoring/         # Conviction scoring
│   ├── providers/       # Tradier & Yahoo Finance providers
│   ├── portfolio/       # Position models, pricing, signals
│   ├── alerts/          # Alert manager
│   ├── history/         # Scan history & comparison
│   ├── orders/          # DraftOrderTicket (non-executing)
│   ├── dashboard/       # Streamlit UI
│   └── main.py          # CLI entry point
├── config/
│   └── settings.yaml    # Configuration (thresholds, weights)
├── data/
│   ├── portfolio.db     # Portfolio database
│   ├── alerts.db        # Alerts database
│   └── scan_results.json # Latest scan results
├── tests/               # Comprehensive test suite
├── pyproject.toml       # Dependencies
└── README.md            # Documentation
```

---

## Installation & Setup

### 1. Clone the repository
```bash
git clone https://github.com/Tadekola/LEAPSCOPE.git
cd LEAPSCOPE
```

### 2. Install dependencies
```bash
poetry install
```

### 3. Configure environment variables
Create a `.env` file at the project root:

```ini
TRADIER_TOKEN=your_tradier_api_token
TRADIER_BASE_URL=https://api.tradier.com/v1
```

> **Note**: Ensure `.env` is in your `.gitignore` (already configured in this repo).

---

## Usage

### Run a market scan
```bash
poetry run python src/main.py scan
```

### View portfolio status
```bash
poetry run python src/main.py portfolio
```

### Launch the dashboard
```bash
poetry run streamlit run src/dashboard/app.py
```
The dashboard will display live data status, scanner results, portfolio positions, and alerts.

---

## Target Audience

*   **Who This Is For**: LEAPS traders, Long-term options investors, PMCC / diagonal spread users, Quant-curious discretionary traders, Engineers building safe trading tools.
*   **Who This Is NOT For**: High-frequency traders, Fully automated trading systems, Execution-only bots, "YOLO" options strategies.

---

## Disclaimer ⚠️

**This project is for educational and research purposes only.**
It does not constitute financial advice or a recommendation to buy or sell securities. Options trading involves significant risk. You are responsible for your own decisions.

---

## License

No license selected yet. Please choose an appropriate open-source license (e.g., MIT or Apache 2.0) before public redistribution.

---

## Status

**LEAPSCOPE v1.0 — Complete & Live (Signals Only)**
Production-ready decision-support system with live market data integration.
