import streamlit as st
import json
import pandas as pd
import sys
import os
from pathlib import Path
from datetime import datetime

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Set page config
st.set_page_config(
    page_title="LEAPSCOPE Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Constants
RESULTS_PATH = Path("data/scan_results.json")

# Financial Disclaimer (P0 requirement) - ENHANCED
FINANCIAL_DISCLAIMER = """
**CRITICAL RISK DISCLOSURE**

This tool is for **EDUCATIONAL and RESEARCH purposes ONLY**.

**IT IS NOT:**
- Investment advice or trade recommendations
- A guarantee of any trading outcome
- A substitute for professional financial advice
- A validated or backtested trading system

**RISKS YOU MUST UNDERSTAND:**
- LEAPS options can lose 100% of their value
- Gap risk: Stop losses provide NO protection against overnight gaps
- GO signals have NOT been backtested for effectiveness
- Conviction scores are NOT probabilities of success
- Past patterns do NOT predict future results

**BY USING THIS SOFTWARE:**
- You acknowledge these risks
- You will make your own investment decisions
- You accept that developers have NO liability for your outcomes
"""

# Risk warning banner for GO signals
GO_SIGNAL_WARNING = """
**RISK WARNING**: GO signals are analytical outputs, NOT trade recommendations.
Historical effectiveness is UNVALIDATED. LEAPS can lose 100% of value.
Always consult a financial advisor.
"""

def load_scan_data():
    if not RESULTS_PATH.exists():
        return []
    try:
        with open(RESULTS_PATH, "r") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Error loading scan data: {e}")
        return []

def main():
    st.title("📈 LEAPSCOPE: Options Analytics Dashboard")
    
    # Version and last update info in sidebar
    st.sidebar.markdown("### LEAPSCOPE v0.3.0")
    st.sidebar.caption("Phase 9: Final Release")
    
    # Live data status indicator
    render_data_source_status()
    
    # Main navigation tabs
    tab_scanner, tab_portfolio, tab_history, tab_alerts = st.tabs([
        "📊 Scanner Results", 
        "💼 Portfolio",
        "📜 Scan History",
        "🔔 Alerts"
    ])
    
    with tab_scanner:
        render_scanner_tab()
    
    with tab_portfolio:
        render_portfolio_tab()
    
    with tab_history:
        render_history_tab()
    
    with tab_alerts:
        render_alerts_tab()
    
    # Render disclaimer at bottom
    render_disclaimer()


def render_data_source_status():
    """Render live data source status indicator in sidebar."""
    st.sidebar.markdown("---")
    
    try:
        from src.utils.config_loader import load_config
        from src.providers.manager import ProviderManager
        
        config = load_config()
        
        # Check if Tradier token is configured
        tradier_config = config.get("providers", {}).get("tradier", {})
        tradier_token = tradier_config.get("api_token", "")
        
        if tradier_token:
            # Token exists - try to get full status
            try:
                provider = ProviderManager(config)
                status = provider.get_data_source_status()
                
                if status["live_data"]:
                    st.sidebar.success("🟢 **LIVE DATA: TRADIER**")
                else:
                    st.sidebar.warning("🟡 **FALLBACK MODE: yfinance**")
                
                # Provider details in expander
                with st.sidebar.expander("📡 Data Sources", expanded=False):
                    tradier_status = status["tradier"]
                    yf_status = status["yfinance"]
                    
                    # Tradier
                    if tradier_status["available"]:
                        mode = tradier_status["mode"]
                        emoji = "🟢" if mode == "LIVE" else "🟡"
                        st.write(f"{emoji} **Tradier**: {mode}")
                    else:
                        st.write("🔴 **Tradier**: DISABLED")
                    
                    # yfinance
                    if yf_status["available"]:
                        st.write(f"🟢 **yfinance**: {yf_status['mode']}")
                    else:
                        st.write("🔴 **yfinance**: UNAVAILABLE")
                    
                    st.caption(f"Primary: {status['primary_source']}")
            except Exception as inner_e:
                st.sidebar.warning("🟡 **Tradier configured but status check failed**")
                with st.sidebar.expander("📡 Details"):
                    st.caption(f"Error: {str(inner_e)[:100]}")
        else:
            st.sidebar.info("🔵 **yfinance mode** (no Tradier token)")
            
    except Exception as e:
        st.sidebar.warning(f"⚠️ Data status: {str(e)[:50]}")

def render_scanner_tab():
    """Render the scanner results tab with conviction scoring (Phase 9)."""
    
    # Load Data
    data = load_scan_data()
    
    if not data:
        st.warning("No scan results found. Run: `poetry run python src/main.py scan`")
        return
    
    # Get scan timestamp
    scan_time = data[0].get("timestamp", "") if data else ""
    if scan_time:
        st.caption(f"📅 Last scan: {scan_time[:19]}")

    # Sidebar Filters
    st.sidebar.markdown("---")
    st.sidebar.header("🔍 Scanner Filters")
    
    # Filter by Decision
    decisions = sorted(list(set([d["decision"] for d in data])))
    default_decisions = [d for d in ["GO", "WATCH"] if d in decisions] or decisions
    selected_decisions = st.sidebar.multiselect("Decision", decisions, default=default_decisions)
    
    # Filter by Conviction Band (Phase 9)
    conviction_bands = ["STRONG", "MODERATE", "WEAK"]
    available_bands = list(set([d.get("conviction", {}).get("band", "MODERATE") for d in data]))
    selected_bands = st.sidebar.multiselect("Conviction Band", conviction_bands, 
                                            default=[b for b in ["STRONG", "MODERATE"] if b in available_bands] or available_bands)
    
    # Filter by min conviction score
    min_conviction = st.sidebar.slider("Min Conviction Score", 0, 100, 0)
    
    # Filter Data
    filtered_data = [
        d for d in data 
        if d["decision"] in selected_decisions 
        and d.get("conviction", {}).get("band", "MODERATE") in selected_bands
        and d.get("conviction", {}).get("score", 0) >= min_conviction
    ]
    
    st.sidebar.markdown(f"**Showing {len(filtered_data)} / {len(data)} symbols**")

    # Main Display
    if not filtered_data:
        st.info("No symbols match the current filters.")
        return

    # Show warning banner if there are GO signals
    go_count = len([d for d in filtered_data if d["decision"] == "GO"])
    if go_count > 0:
        st.error(GO_SIGNAL_WARNING)
    
    # Summary Metrics
    col1, col2, col3, col4, col5 = st.columns(5)
    watch_count = len([d for d in filtered_data if d["decision"] == "WATCH"])
    strong_count = len([d for d in filtered_data if d.get("conviction", {}).get("band") == "STRONG"])
    
    avg_conviction = sum([d.get("conviction", {}).get("score", 0) for d in filtered_data]) / len(filtered_data) if filtered_data else 0
    
    col1.metric("GO Signals", go_count, help="NOT trade recommendations")
    col2.metric("WATCH", watch_count)
    col3.metric("Strong Band", strong_count, help="High conviction does NOT mean high probability")
    # Show conviction as range instead of false precision
    col4.metric("Avg Conviction", f"~{int(avg_conviction/10)*10}-{int(avg_conviction/10)*10+10}", help="Approximate range, NOT a probability")
    col5.metric("Total", len(filtered_data))

    st.markdown("---")

    # Results Table with conviction scoring
    st.subheader("📋 Scan Results (Sorted by Conviction)")
    
    table_data = []
    for d in filtered_data:
        conviction = d.get("conviction", {})
        conv_score = conviction.get("score", 0)
        conv_band = conviction.get("band", "N/A")
        
        # Reduce false precision - show ranges instead of exact numbers
        # Round to nearest 5 to avoid implying false precision
        conv_score_rounded = int(round(conv_score / 5) * 5)
        
        # Use neutral labels instead of encouraging emojis
        band_label = f"{conv_band}"
        
        # Decision label - neutral wording
        decision_label = d["decision"]
        
        table_data.append({
            "Symbol": d["symbol"],
            "Type": d.get("asset_type", "STOCK"),
            "Price": f"${d['current_price']:.2f}",
            "Decision": decision_label,
            "Score": f"~{conv_score_rounded}",  # Approximate, not exact
            "Band": band_label,
            "Trend": d["scores"]["technical_trend"],
            "Fund": d["scores"]["fundamental"],
            "Options": d["scores"]["options_candidates"],
            "Risk": "⚠️" if d.get("earnings_risk", False) else "✓",
        })
    
    df_table = pd.DataFrame(table_data)
    st.dataframe(df_table, use_container_width=True, height=400)

    # Detail View
    st.markdown("---")
    st.subheader("🔍 Symbol Details")
    
    selected_symbol = st.selectbox("Select Symbol", [d["symbol"] for d in filtered_data])
    
    if selected_symbol:
        details = next((d for d in filtered_data if d["symbol"] == selected_symbol), None)
        
        if details:
            # Layout
            t1, t2, t3 = st.tabs(["Fundamentals", "Technical Analysis", "Options (LEAPS)"])
            
            with t1:
                fund = details["details"]["fundamentals"]
                st.metric("Overall Score", fund["overall_score"], delta_color="normal")
                st.write(f"**Confidence:** {fund['confidence']}")
                st.write(f"**Eligible:** {fund['is_eligible']}")
                
                c1, c2 = st.columns(2)
                with c1:
                    st.write("#### Dimensions")
                    st.json(fund["dimensions"])
                with c2:
                    st.write("#### Notes")
                    for n in fund["notes"]:
                        st.text(f"• {n}")

            with t2:
                ta = details["details"]["technical"]
                st.metric("Trend", ta["trend"])
                
                c1, c2 = st.columns(2)
                with c1:
                    st.write("#### Indicators")
                    st.json(ta["indicators"])
                with c2:
                    st.write("#### Signals")
                    st.json(ta["signals"])

            with t3:
                opt = details["details"]["options"]
                st.metric("Candidates Found", opt["count"])
                st.write(f"**Status:** {opt['status']}")
                
                if opt.get("candidates"):
                    st.write("#### Top Candidates")
                    cand_df = pd.DataFrame(opt["candidates"])
                    
                    # Flatten Greeks for display
                    if not cand_df.empty:
                        # Extract delta/theta from greeks dict if present
                        if "greeks" in cand_df.columns:
                            greeks_df = cand_df["greeks"].apply(pd.Series)
                            cand_df = pd.concat([cand_df.drop(["greeks"], axis=1), greeks_df], axis=1)
                        
                        cols_to_show = ["contract_symbol", "expiration", "strike", "type", "bid", "ask", "oi", "delta", "theta", "iv"]
                        # Filter cols that exist
                        cols_to_show = [c for c in cols_to_show if c in cand_df.columns]
                        
                        st.dataframe(cand_df[cols_to_show], use_container_width=True)

def render_portfolio_tab():
    """Render the portfolio management tab (Phase 8)."""
    st.markdown("---")
    
    try:
        from src.utils.config_loader import load_config
        from src.providers.manager import ProviderManager
        from src.portfolio.manager import PortfolioManager
        from src.portfolio.models import Position, PositionStatus, OptionType, SignalType, Severity
        
        config = load_config()
        provider = ProviderManager(config)
        portfolio_mgr = PortfolioManager(provider, config)
        
    except Exception as e:
        st.error(f"Error initializing portfolio manager: {e}")
        st.info("Make sure all dependencies are installed: `poetry install`")
        return
    
    # Sidebar controls
    st.sidebar.markdown("---")
    st.sidebar.header("Portfolio Controls")
    
    # Filter options
    show_status = st.sidebar.radio("Show Positions", ["OPEN Only", "All"], index=0)
    status_filter = PositionStatus.OPEN if show_status == "OPEN Only" else None
    
    # Refresh button
    if st.sidebar.button("🔄 Refresh Portfolio", use_container_width=True):
        st.rerun()
    
    # Get positions
    if status_filter:
        positions = portfolio_mgr.get_all_positions(status_filter)
    else:
        positions = portfolio_mgr.get_all_positions()
    
    if not positions:
        st.info("No positions found. Add positions using the form below or import from JSON.")
        render_add_position_form(portfolio_mgr)
        return
    
    # Refresh pricing and signals
    with st.spinner("Refreshing portfolio with live data..."):
        priced_positions = portfolio_mgr.refresh_portfolio()
    
    # Portfolio Summary
    st.subheader("📊 Portfolio Summary")
    summary = portfolio_mgr.get_portfolio_summary(priced_positions)
    
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Positions", summary["total_positions"])
    col2.metric("Market Value", f"${summary['total_market_value']:,.0f}")
    col3.metric("Cost Basis", f"${summary['total_cost_basis']:,.0f}")
    
    pnl = summary['total_unrealized_pnl']
    pnl_pct = summary['total_unrealized_pnl_pct']
    col4.metric("Unrealized P&L", f"${pnl:,.0f}", delta=f"{pnl_pct:.1f}%")
    col5.metric("Critical Signals", summary.get("critical_count", 0))
    
    st.caption(f"Last updated: {summary.get('last_updated', 'N/A')}")
    
    # Signals Summary
    if summary.get("signals"):
        st.markdown("**Signal Distribution:**")
        signal_cols = st.columns(len(summary["signals"]))
        for i, (sig_type, count) in enumerate(summary["signals"].items()):
            color = "🔴" if sig_type in ["STOP_LOSS", "TECH_INVALIDATED"] else "🟡" if sig_type != "HOLD" else "🟢"
            signal_cols[i].metric(f"{color} {sig_type}", count)
    
    st.markdown("---")
    
    # Positions Table
    st.subheader("📋 Positions")
    
    # Signal filter
    signal_types = ["All"] + [s.value for s in SignalType]
    signal_filter = st.selectbox("Filter by Signal", signal_types)
    
    # Filter positions
    if signal_filter != "All":
        filtered_positions = [p for p in priced_positions if p.signal and p.signal.signal_type.value == signal_filter]
    else:
        filtered_positions = priced_positions
    
    if not filtered_positions:
        st.info("No positions match the filter.")
    else:
        # Build table data
        table_data = []
        for p in filtered_positions:
            signal_emoji = get_signal_emoji(p.signal) if p.signal else "⚪"
            table_data.append({
                "Symbol": p.symbol,
                "Type": p.asset_type,
                "Option": f"{p.strike}{p.option_type.value[0]}",
                "Expiry": p.expiry,
                "Contracts": p.contracts,
                "Entry": f"${p.entry_price:.2f}",
                "Last": f"${p.option_last:.2f}" if p.option_last else "N/A",
                "P&L %": f"{p.unrealized_pnl_pct:.1f}%" if p.unrealized_pnl_pct else "N/A",
                "DTE": p.days_to_expiry or "N/A",
                "Signal": f"{signal_emoji} {p.signal.signal_type.value}" if p.signal else "N/A",
            })
        
        df = pd.DataFrame(table_data)
        st.dataframe(df, use_container_width=True)
    
    # Position Details
    st.markdown("---")
    st.subheader("🔍 Position Details")
    
    position_options = [f"{p.symbol} {p.strike}{p.option_type.value[0]} {p.expiry}" for p in filtered_positions]
    if position_options:
        selected_pos = st.selectbox("Select Position", position_options)
        selected_idx = position_options.index(selected_pos)
        position = filtered_positions[selected_idx]
        
        render_position_details(position)
    
    # Add Position Form
    st.markdown("---")
    render_add_position_form(portfolio_mgr)
    
    # Import/Export
    st.markdown("---")
    st.subheader("📁 Import / Export")
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📤 Export to JSON", use_container_width=True):
            if portfolio_mgr.export_portfolio():
                st.success("Portfolio exported to data/portfolio.json")
            else:
                st.error("Export failed")
    
    with col2:
        if st.button("📥 Import from JSON", use_container_width=True):
            count = portfolio_mgr.import_portfolio()
            if count > 0:
                st.success(f"Imported {count} positions")
                st.rerun()
            else:
                st.warning("No positions imported (file may not exist or be empty)")

def get_signal_emoji(signal) -> str:
    """Get emoji for signal severity."""
    if not signal:
        return "⚪"
    if signal.severity.value == "CRITICAL":
        return "🔴"
    elif signal.severity.value == "WARN":
        return "🟡"
    return "🟢"

def render_position_details(position):
    """Render detailed view for a single position."""
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("#### Position Info")
        st.write(f"**Symbol:** {position.symbol} ({position.asset_type})")
        st.write(f"**Contract:** {position.strike} {position.option_type.value} exp {position.expiry}")
        st.write(f"**Contracts:** {position.contracts}")
        st.write(f"**Entry Date:** {position.entry_date}")
        st.write(f"**Entry Price:** ${position.entry_price:.2f}")
        st.write(f"**Cost Basis:** ${position.cost_basis:,.2f}" if position.cost_basis else "")
        st.write(f"**Status:** {position.status.value}")
        if position.notes:
            st.write(f"**Notes:** {position.notes}")
    
    with col2:
        st.write("#### Current Pricing")
        st.write(f"**Underlying:** ${position.underlying_last:.2f}" if position.underlying_last else "**Underlying:** N/A")
        st.write(f"**Option Bid/Ask:** ${position.option_bid:.2f} / ${position.option_ask:.2f}" if position.option_bid and position.option_ask else "")
        st.write(f"**Option Last:** ${position.option_last:.2f}" if position.option_last else "**Option Last:** N/A")
        st.write(f"**Market Value:** ${position.market_value:,.2f}" if position.market_value else "")
        st.write(f"**Days to Expiry:** {position.days_to_expiry}")
        st.write(f"**Pricing Source:** {position.pricing_source} ({position.pricing_confidence})")
    
    # Greeks
    if position.delta or position.theta:
        st.write("#### Greeks")
        greek_cols = st.columns(5)
        greek_cols[0].metric("Delta", f"{position.delta:.3f}" if position.delta else "N/A")
        greek_cols[1].metric("Gamma", f"{position.gamma:.4f}" if position.gamma else "N/A")
        greek_cols[2].metric("Theta", f"{position.theta:.4f}" if position.theta else "N/A")
        greek_cols[3].metric("Vega", f"{position.vega:.4f}" if position.vega else "N/A")
        greek_cols[4].metric("IV", f"{position.iv:.1%}" if position.iv else "N/A")
    
    # Signal Details
    if position.signal:
        st.write("#### 📢 Signal")
        signal = position.signal
        severity_color = "red" if signal.severity.value == "CRITICAL" else "orange" if signal.severity.value == "WARN" else "green"
        st.markdown(f"**{signal.signal_type.value}** (:{severity_color}[{signal.severity.value}])")
        
        st.write("**Reasons:**")
        for reason in signal.reasons:
            if reason:
                st.write(f"- {reason}")
        
        st.info(f"**Recommended Action:** {signal.recommended_action}")

def render_add_position_form(portfolio_mgr):
    """Render form to add a new position."""
    st.subheader("➕ Add Position")
    
    with st.expander("Add New Position", expanded=False):
        with st.form("add_position_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                symbol = st.text_input("Symbol", placeholder="AAPL").upper()
                asset_type = st.selectbox("Asset Type", ["STOCK", "ETF"])
                option_type = st.selectbox("Option Type", ["CALL", "PUT"])
                strike = st.number_input("Strike Price", min_value=0.01, step=1.0)
                expiry = st.date_input("Expiration Date")
            
            with col2:
                contracts = st.number_input("Contracts", min_value=1, value=1, step=1)
                entry_price = st.number_input("Entry Price (per contract)", min_value=0.01, step=0.1)
                entry_date = st.date_input("Entry Date")
                underlying_entry = st.number_input("Underlying Price at Entry (optional)", min_value=0.0, step=1.0)
                notes = st.text_area("Notes (optional)")
            
            submitted = st.form_submit_button("Add Position", use_container_width=True)
            
            if submitted:
                if not symbol:
                    st.error("Symbol is required")
                elif strike <= 0:
                    st.error("Strike must be positive")
                elif entry_price <= 0:
                    st.error("Entry price must be positive")
                else:
                    from src.portfolio.models import Position, OptionType as OT, PositionStatus as PS
                    
                    new_position = Position(
                        symbol=symbol,
                        asset_type=asset_type,
                        option_type=OT(option_type),
                        strike=float(strike),
                        expiry=expiry.strftime("%Y-%m-%d"),
                        contracts=int(contracts),
                        entry_price=float(entry_price),
                        entry_date=entry_date.strftime("%Y-%m-%d"),
                        underlying_entry_price=float(underlying_entry) if underlying_entry > 0 else None,
                        notes=notes,
                        status=PS.OPEN
                    )
                    
                    if portfolio_mgr.add_position(new_position):
                        st.success(f"Position added: {symbol} {strike}{option_type[0]} {expiry}")
                        st.rerun()
                    else:
                        st.error("Failed to add position")

def render_history_tab():
    """Render the scan history tab (Phase 9)."""
    st.markdown("---")
    st.subheader("📜 Scan History")
    
    try:
        from src.history.scan_history import ScanHistory
        
        history = ScanHistory()
        recent_scans = history.get_recent_scans(limit=10)
        
        if not recent_scans:
            st.info("No scan history available. Run a scan first: `poetry run python src/main.py scan`")
            return
        
        # Display recent scans
        st.write(f"**{len(recent_scans)} recent scans:**")
        
        history_data = []
        for scan in recent_scans:
            history_data.append({
                "Scan ID": scan.id,
                "Timestamp": scan.timestamp.strftime("%Y-%m-%d %H:%M"),
                "Symbols": scan.symbol_count,
                "🟢 GO": scan.go_count,
                "🟡 WATCH": scan.watch_count,
                "Config": scan.config_hash[:8] if scan.config_hash else "N/A"
            })
        
        df_history = pd.DataFrame(history_data)
        st.dataframe(df_history, use_container_width=True)
        
        # Scan comparison
        st.markdown("---")
        st.subheader("📊 Scan Comparison")
        
        if len(recent_scans) >= 2:
            latest = history.get_latest_scan()
            if latest:
                comparison = history.compare_scans(latest.id)
                
                if comparison:
                    col1, col2, col3 = st.columns(3)
                    col1.metric("🆕 New GO Signals", len(comparison.new_go_signals))
                    col2.metric("⬆️ Upgrades", len(comparison.upgraded_signals))
                    col3.metric("⬇️ Downgrades", len(comparison.downgraded_signals))
                    
                    if comparison.new_go_signals:
                        st.write("**New GO signals:**")
                        for sym in comparison.new_go_signals:
                            st.write(f"  🟢 {sym}")
                    
                    if comparison.upgraded_signals:
                        st.write("**Upgraded signals:**")
                        for upgrade in comparison.upgraded_signals:
                            st.write(f"  ⬆️ {upgrade['symbol']}: {upgrade['from']} → {upgrade['to']}")
                    
                    if comparison.downgraded_signals:
                        st.write("**Downgraded signals:**")
                        for downgrade in comparison.downgraded_signals:
                            st.write(f"  ⬇️ {downgrade['symbol']}: {downgrade['from']} → {downgrade['to']}")
        else:
            st.info("Need at least 2 scans for comparison.")
            
    except Exception as e:
        st.error(f"Error loading scan history: {e}")


def render_alerts_tab():
    """Render the alerts tab (Phase 9)."""
    st.markdown("---")
    st.subheader("🔔 Alerts")
    
    try:
        from src.alerts.manager import AlertManager, AlertSeverity
        
        alert_mgr = AlertManager()
        
        # Alert summary
        unack_counts = alert_mgr.get_unacknowledged_count()
        total_unack = sum(unack_counts.values())
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("🚨 Critical", unack_counts.get("CRITICAL", 0))
        col2.metric("⚠️ Warnings", unack_counts.get("WARN", 0))
        col3.metric("ℹ️ Info", unack_counts.get("INFO", 0))
        col4.metric("📬 Total Unread", total_unack)
        
        # Acknowledge all button
        if total_unack > 0:
            if st.button("✓ Acknowledge All", use_container_width=True):
                count = alert_mgr.acknowledge_all()
                st.success(f"Acknowledged {count} alerts")
                st.rerun()
        
        st.markdown("---")
        
        # Recent alerts
        st.subheader("📋 Recent Alerts")
        
        # Filter
        show_unack_only = st.checkbox("Show unacknowledged only", value=True)
        
        alerts = alert_mgr.get_alerts(limit=20, unacknowledged_only=show_unack_only)
        
        if not alerts:
            st.info("No alerts to display.")
            return
        
        for alert in alerts:
            severity_color = "🚨" if alert.severity == AlertSeverity.CRITICAL else "⚠️" if alert.severity == AlertSeverity.WARN else "ℹ️"
            ack_status = "✓" if alert.acknowledged else "○"
            
            with st.expander(f"{severity_color} {ack_status} {alert.title} ({alert.created_at.strftime('%Y-%m-%d %H:%M')})"):
                st.write(f"**Symbol:** {alert.symbol}")
                st.write(f"**Type:** {alert.alert_type.value}")
                st.write(f"**Message:** {alert.message}")
                
                if alert.data:
                    st.write("**Details:**")
                    st.json(alert.data)
                
                if not alert.acknowledged:
                    if st.button(f"Acknowledge", key=f"ack_{alert.id}"):
                        alert_mgr.acknowledge_alert(alert.id)
                        st.rerun()
                        
    except Exception as e:
        st.error(f"Error loading alerts: {e}")


def render_disclaimer():
    """Render the financial disclaimer footer."""
    st.markdown("---")
    
    # ALWAYS VISIBLE warning box
    st.warning(
        "**IMPORTANT**: This tool is for EDUCATIONAL purposes only. "
        "GO signals are NOT trade recommendations. Historical effectiveness is UNVALIDATED. "
        "LEAPS can lose 100% of value. Consult a financial advisor."
    )
    
    with st.expander("📋 Full Risk Disclosure (MUST READ)", expanded=False):
        st.markdown(FINANCIAL_DISCLAIMER)
    
    # Always visible mini disclaimer
    st.caption(
        "Options trading involves significant risk of loss including total loss of investment. "
        "Past performance does not guarantee future results."
    )

if __name__ == "__main__":
    main()
