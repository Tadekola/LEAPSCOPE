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

## Live Data & Providers (Hybrid Multi-Source)

LEAPSCOPE uses a **hybrid multi-source approach** for maximum data reliability:

| Data Type | Primary Source | Fallback |
| :--- | :--- | :--- |
| **Live prices** | Tradier API | Yahoo Finance Quote API |
| **Options chains & Greeks** | Tradier | yfinance |
| **Implied volatility** | Tradier | Calculated from chain |
| **Fundamentals** | Yahoo Finance | - |
| **Earnings dates** | Yahoo Finance | - |
| **Historical OHLCV** | yfinance (split-adjusted) | Tradier |

**Price Fetching Priority:**
1. Tradier live API (if configured)
2. Yahoo Finance direct quote API (`regularMarketPrice`)
3. yfinance OHLCV fallback

🔒 **Security**: Tradier credentials are loaded securely from a `.env` file. **No secrets are hard-coded.**

---

## Safety & Design Principles

### What LEAPSCOPE Does NOT Do:
*   **No auto-trading** - Cannot execute trades
*   **No order submission** - Cannot send orders to brokers
*   **No execution paths** - Code explicitly blocks execution
*   **No trade recommendations** - GO signals are analytical outputs only

### What LEAPSCOPE Does:
*   **Draft order tickets blocked** - `_execution_blocked = True` enforced
*   **UNKNOWN data fails gates** - Missing data never passes as valid
*   **Earnings risk enforced** - 14-day buffer around earnings
*   **Human review required** - All decisions require manual action
*   **Risk warnings embedded** - Disclaimers at point of decision
*   **Signal tracking** - Records signals for future validation
*   **Market hours warnings** - Alerts when market is closed

LEAPSCOPE is a **decision-support system**, not a trading bot.

### Signal Validation Status

Signals are tracked for future validation but **historical effectiveness is currently UNKNOWN**.
The system will build a track record over time, but users should not assume signals are profitable.

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

### Scan specific symbols
```bash
poetry run python src/main.py scan --symbols NVDA,AAPL,GOOGL
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

## Understanding the Decision Framework

### GO / WATCH / NO_GO Signals

The decision engine requires **ALL THREE** conditions to pass for a **GO** signal:

| Condition | What It Checks | Required for GO |
|-----------|----------------|------------------|
| **Technical** | Trend = BULLISH (price > SMA50 > SMA200) | Must pass |
| **Fundamental** | Score >= 60 (ETFs get bypass score of 70) | Must pass |
| **Options/Volatility** | IV/HV ratio <= 1.5x AND valid LEAPS candidates | Must pass |

### Common Reasons for WATCH Instead of GO

| Scenario | Explanation |
|----------|-------------|
| High IV/HV ratio | Options are "expensive" relative to historical volatility - wait for better pricing |
| No LEAPS candidates | Insufficient liquidity or no strikes in target delta range (0.65-0.85) |
| Earnings within 14 days | Downgraded from GO to WATCH due to binary event risk |

### How to Interpret Results

| Decision | Meaning | Suggested Action |
|----------|---------|------------------|
| **GO** | All conditions met, options fairly priced | Worth deeper research for potential entry |
| **WATCH** | Fundamentals/technicals OK, but options expensive or volatility concern | Monitor, wait for better entry point |
| **NO_GO** | Technical trend not bullish OR fundamentals weak | Not a LEAPS candidate at this time |

### Conviction Score (0-100)

The conviction score is a **composite quality metric**, NOT a probability:

| Component | Weight | What It Measures |
|-----------|--------|------------------|
| Technical | 30% | Trend strength, momentum, crossovers |
| Fundamental | 25% | Growth, profitability, balance sheet |
| Volatility | 25% | IV/HV attractiveness |
| Liquidity | 20% | Options market depth, spreads |

**Conviction Bands:**
- **STRONG** (75+): High quality across all factors
- **MODERATE** (50-74): Acceptable quality, some weaknesses
- **WEAK** (<50): Significant concerns in one or more areas

> **Important**: A score of 80 does NOT mean 80% chance of profit. Scores have not been backtested.

---

## Target Audience

*   **Who This Is For**: LEAPS traders, Long-term options investors, PMCC / diagonal spread users, Quant-curious discretionary traders, Engineers building safe trading tools.
*   **Who This Is NOT For**: High-frequency traders, Fully automated trading systems, Execution-only bots, "YOLO" options strategies.

---

## CRITICAL RISK DISCLOSURE

**READ THIS BEFORE USING LEAPSCOPE**

### This Software is for EDUCATIONAL and RESEARCH Purposes ONLY

**IT IS NOT:**
- Investment advice or trade recommendations
- A guarantee of any trading outcome
- A substitute for professional financial advice
- A validated or backtested trading system

### RISKS YOU MUST UNDERSTAND:

| Risk | Description |
|------|-------------|
| **Total Loss** | LEAPS options can lose 100% of their value |
| **Gap Risk** | Stop losses provide NO protection against overnight gaps. Positions can lose 50-100% on adverse overnight moves |
| **Unvalidated Signals** | GO signals have NOT been backtested for effectiveness. Historical win rates are UNKNOWN |
| **False Precision** | Conviction scores are NOT probabilities. A score of 80 does NOT mean 80% chance of profit |
| **Data Limitations** | Analysis is based on point-in-time data which may be delayed or incomplete |
| **Earnings Risk** | Binary events can cause unpredictable moves regardless of technical/fundamental setup |
| **IV Crush** | Implied volatility typically drops after earnings, causing losses even on correct directional bets |

### BY USING THIS SOFTWARE, YOU ACKNOWLEDGE:
- You understand options trading risks including total loss of investment
- You will make your own investment decisions
- You will consult qualified financial professionals as needed
- The developers assume NO LIABILITY for your trading outcomes
- Past patterns do NOT predict future results

---

## License

No license selected yet. Please choose an appropriate open-source license (e.g., MIT or Apache 2.0) before public redistribution.

---

## Status

**LEAPSCOPE v1.0 — Complete & Live (Signals Only)**
Production-ready decision-support system with live market data integration.

### Version History

| Version | Features |
|---------|----------|
| v0.3.0 | Hybrid multi-source data, signal tracking, market hours validation |
| v0.2.0 | Portfolio management, alerts, scan history |
| v0.1.0 | Core scanner, decision engine, conviction scoring |
