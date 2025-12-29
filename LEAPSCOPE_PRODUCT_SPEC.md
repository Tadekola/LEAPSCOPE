# LEAPSCOPE: Product Specification (Phase 0)

## 1. Executive Summary
**LEAPSCOPE** is a professional-grade options analytics system designed to identify high-conviction Long-Term Equity Anticipation Securities (LEAPS) opportunities. It automates the analysis of market conditions, fundamental health, and technical trends to generate "GO/NO-GO" signals and specific contract recommendations. The system prioritizes capital preservation, systematic decision-making, and full explainability.

**Core Philosophy:**
- **Capital Preservation First:** Do not lose money.
- **Systematic Process:** Remove emotion from the equation.
- **Explainability:** No black boxes. Every decision is logged with reasons.
- **Data Integrity:** "UNKNOWN" is a valid state; guessing is not.

---

## 2. Functional Requirements

### 2.1. Market Universe Construction
The system must define a "Universe" of tradable assets.
- **Inputs:** List of Tickers (Stocks, ETFs).
- **Filtering:**
  - Minimum Average Volume (e.g., > 1M daily).
  - Minimum Market Cap (e.g., > $2B).
  - Optionable status (must have liquid options).
  - Sector/Industry classification.
- **Outputs:** A validated list of symbols eligible for scanning.

### 2.2. Technical Analysis (TA) Engine
The system must assess the trend and volatility of assets.
- **Indicators:**
  - Moving Averages (SMA/EMA 50, 200) for trend alignment.
  - RSI / Stochastic for overbought/oversold conditions.
  - Bollinger Bands / ATR for volatility measurement.
  - MACD for momentum.
- **Signal Logic:**
  - Determine "Bullish", "Bearish", or "Neutral" primary trend.
  - Identify support/resistance zones (algorithmic or fixed).

### 2.3. Fundamental Analysis (FA) Engine
The system must assess the quality of the underlying asset.
- **Metrics:**
  - Earnings Growth (Quarterly/Annual).
  - Revenue Growth.
  - Profit Margins.
  - Debt-to-Equity / Current Ratio.
  - Analyst Ratings (if available).
- **Scoring:** Calculate a "Quality Score" (0-100).
- **Earnings Date Check:** Avoid entry immediately prior to binary events unless specified.

### 2.4. Options Chain Analysis & LEAPS Selection
The system must parse option chains to find suitable contracts.
- **LEAPS Definition:** Expiration > 12 months (configurable, e.g., > 300 days).
- **Liquidity Filters:**
  - Open Interest (OI) thresholds.
  - Bid-Ask Spread width (e.g., < 10% of mid-price).
  - Volume (if applicable).
- **Contract Selection Logic:**
  - **Delta:** Target specific delta ranges (e.g., 0.70 - 0.80 for deep ITM substitutions, or specific targets).
  - **Theta:** Minimize theta decay exposure.
  - **Implied Volatility (IV):** Compare IV to Historical Volatility (IV Rank / IV Percentile). Avoid buying when IV is historically high.

### 2.5. Decision Engine (The Brain)
Combines TA, FA, and Options data to make a "GO / NO-GO" decision.
- **Input:** Asset state (TA trend, FA score, IV rank).
- **Logic:** Configuration-driven rulesets (e.g., "Trend=Bullish AND FA_Score>80 AND IV_Rank<50 => GO").
- **Output:**
  - Decision: GO / NO-GO / WATCH.
  - Rationale: Human-readable explanation (e.g., "Rejected: IV Rank too high (85%)").

### 2.6. Portfolio Tracking & Management
Monitors open positions (simulated or manual entry).
- **Tracking:** Entry Date, Cost Basis, Current Value, P&L.
- **Management Signals:**
  - **Take Profit:** Target ROI reached (e.g., +50%).
  - **Stop Loss:** Invalidating technical breakdown or max loss reached.
  - **Roll:** Decision to roll out/up based on time decay or trend continuation.
- **No Auto-Execution:** Generates "Draft Order Tickets" only.

### 2.7. Alerting & Notifications
- Channels: Console logs (MVP), file output, potential future webhook (Discord/Slack/Email).
- Content: New "GO" signals, "Exit" warnings, Weekly summaries.

---

## 3. Non-Functional Requirements

### 3.1. Performance & Scalability
- **Scan Duration:** Full universe scan (< 500 symbols) should complete within a reasonable time (e.g., < 15 mins) on standard hardware.
- **Concurrency:** utilize async/await or threading for data fetching, respecting rate limits.

### 3.2. Data Handling
- **Caching:** Cache heavy queries (e.g., historical data) to disk/database to minimize API calls.
- **Rate Limiting:** Strict adherence to data provider API limits (leaky bucket or token bucket algorithm).
- **Reproducibility:** Scans run at time T must be reproducible (logs/snapshots).

### 3.3. Reliability & Error Handling
- **Fail-Safe:** A failure in analyzing one symbol must NOT crash the entire batch.
- **Logging:** Structured logging (JSON) for all critical events (INFO, WARN, ERROR).
- **Validation:** Strict schema validation for all incoming data.

### 3.4. Configuration
- All thresholds (Delta, IV Rank, MA lengths) must be in a config file (YAML/JSON/TOML), NOT hardcoded.

---

## 4. Data Integrity & Safety Rules

### 4.1. The "UNKNOWN" Rule
- If a datapoint (e.g., "PE Ratio") is missing, it is labeled `UNKNOWN`.
- The Decision Engine must explicitly handle `UNKNOWN` (usually treated as a fail or neutral, never a pass).
- **NEVER** infer missing values (e.g., do not assume 0 for missing debt).

### 4.2. Risk & Compliance Guardrails
- **READ-ONLY Market Access:** The application should not require "Trade" permissions on broker APIs if possible.
- **Draft Orders Only:** Output is text/JSON instructions, never API execution orders.
- **Disclaimers:** Every report must append a standard financial disclaimer.

---

## 5. Technology Stack Recommendation

### 5.1. Core Application
- **Language:** **Python 3.10+** (Dominant in quantitative finance, rich ecosystem).
- **Data Analysis:** `pandas`, `numpy`, `ta-lib` (or `pandas-ta`).

### 5.2. Data Providers (Low Cost / Free)
- **Primary:** `yfinance` (Free/Scraping wrapper) for MVP.
- **Secondary (Future/Robust):** `Polygon.io` (Starter tier) or `Alpaca` (Free data with account).
- **Fallback:** `AlphaVantage`.

### 5.3. Database & Storage
- **MVP:** `SQLite` (File-based, zero config, relational) + JSON files for config/results.
- **Future:** `PostgreSQL` (TimescaleDB for tick data if needed).

### 5.4. Interface
- **CLI (Command Line Interface):** Primary interaction mode for MVP (e.g., `python main.py scan --symbol AAPL`).
- **Dashboard (Phase 7+):** `Streamlit` or `Dash` (Python-native web apps) for visualizing results.

### 5.5. Infrastructure
- **Containerization:** `Docker` + `Docker Compose` for reproducible environments.
- **Scheduling:** System `cron` or simple Python loop with `schedule` library for MVP.

---

## 6. High-Level System Architecture

```mermaid
graph TD
    User[User] --> CLI[CLI / Interface]
    CLI --> Controller[Main Controller]
    
    subgraph Core Engines
        Controller --> Universe[Universe Builder]
        Controller --> Fetcher[Data Fetcher]
        Controller --> TA[Technical Analysis Engine]
        Controller --> FA[Fundamental Analysis Engine]
        Controller --> Options[Options Chain Analyzer]
        Controller --> Decision[Decision Engine]
    end
    
    subgraph Data & State
        Fetcher <--> Cache[Local Cache / SQLite]
        Fetcher <--> API[External APIs (YFinance/Alpaca)]
        Decision --> Results[Result Store (JSON/DB)]
        Decision --> Logger[Logger]
    end
    
    subgraph Output
        Results --> Report[Report Generator]
        Report --> User
    end
```

**Module Responsibilities:**
1.  **Universe Builder:** Loads symbols, filters by liquidity.
2.  **Data Fetcher:** Handles API requests, rate limiting, and caching.
3.  **TA Engine:** Calculates indicators on OHLCV data.
4.  **FA Engine:** Extracts valuation and health metrics.
5.  **Options Analyzer:** Filters chains for LEAPS, calculates Greeks (if missing), filters liquidity.
6.  **Decision Engine:** Applies `Config` rules to `Analysis` objects to produce `Signals`.

---

## 7. Phased Roadmap

### Phase 1: Repo Scaffold + Bootable System
- Initialize Git repo.
- Set up Docker environment.
- Create basic project structure (modular).
- Implement logging and configuration loading.
- **Goal:** `hello_world` runs via Docker.

### Phase 2: Universe Builder & Data Fetching
- Implement Data Fetcher with `yfinance`.
- Implement caching/rate-limiting wrappers.
- Define S&P 500 / Nasdaq 100 universe loaders.
- **Goal:** Can download and save OHLCV data for a list of tickers.

### Phase 3: Technical Analysis Engine
- Implement `pandas-ta` or custom calculations.
- Compute Trend, RSI, Bollinger Bands, ATR.
- **Goal:** Output a "Technical Report" for a given symbol.

### Phase 4: Fundamentals Scoring
- Fetch key stats (PE, EPS growth).
- Implement scoring logic.
- Handle missing data (UNKNOWN).
- **Goal:** Output a "Fundamental Score" for a given symbol.

### Phase 5: Options Chain + LEAPS Selection
- Fetch option chains.
- Filter for expirations > X days.
- Filter by Delta and Liquidity.
- **Goal:** List specific contract candidates (e.g., "AAPL 2025-06-20 150C").

### Phase 6: Decision Engine (MVP Completion)
- Combine Phases 3, 4, 5.
- Apply Ruleset.
- **Goal:** End-to-end "Should I buy LEAPS on AAPL?" answer.

### Phase 7: Scanner + Ranking Dashboard
- Run loop over entire universe.
- Rank results by conviction.
- Basic Streamlit dashboard.

### Phase 8: Portfolio Monitoring
- Ingest simulated positions.
- Track P&L and technical invalidation levels.

### Phase 9: Alerts & Polish
- Email/Discord notifications.
- Documentation and clean up.
