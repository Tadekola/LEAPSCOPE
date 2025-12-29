import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.logger import setup_logger
from src.utils.config_loader import load_config

def main():
    # Load Config
    try:
        config = load_config()
    except Exception as e:
        print(f"CRITICAL: Failed to load config: {e}")
        sys.exit(1)

    # Setup Logger
    log_level = config.get("app", {}).get("log_level", "INFO")
    logger = setup_logger("LEAPSCOPE", log_level)

    logger.info("System booting up...")
    logger.info(f"App Name: {config['app']['name']}")
    logger.info(f"Version: {config['app']['version']}")
    
    logger.info("System initialization complete. Ready for commands.")

    # Initialize Components
    from src.data.cache import DataCache
    from src.data.fetcher import DataFetcher
    from src.data.universe import UniverseBuilder
    from src.analysis.technical import TechnicalAnalyzer
    from src.analysis.fundamentals import FundamentalsAnalyzer
    from src.analysis.options import OptionsAnalyzer
    from src.decision.engine import DecisionEngine

    try:
        cache = DataCache()
        fetcher = DataFetcher(cache=cache)
        universe = UniverseBuilder()
        
        # Load Configs
        ta_config = config.get("technical_analysis", {})
        ta_engine = TechnicalAnalyzer(config=ta_config)
        
        fund_config = config.get("fundamentals", {})
        fund_engine = FundamentalsAnalyzer(config=fund_config)

        opt_config = config.get("options", {})
        opt_engine = OptionsAnalyzer(config=opt_config)
        
        decision_config = config.get("decision", {})
        decision_engine = DecisionEngine(config=decision_config)

        # Test Universe Loading
        tickers = universe.get_sp500_tickers()
        logger.info(f"Universe loaded with {len(tickers)} symbols.")

        # Test Data Fetching for specific diverse symbols
        # 1. AAPL: Large Cap, Full Data
        # 2. SPY: ETF, Limited Fundamentals
        # 3. INTC: Another stock
        test_symbols = ['AAPL', 'SPY', 'INTC'] 
        logger.info(f"Starting test fetch for: {test_symbols}")

        for symbol in test_symbols:
            # 1. Fetch OHLCV
            df = fetcher.fetch_history(symbol)
            if not df.empty:
                current_price = df['close'].iloc[-1]
                logger.info(f"Successfully fetched {symbol}: {len(df)} rows. Last Close: {current_price:.2f}")
                
                # 2. Run TA
                logger.info(f"Running Technical Analysis on {symbol}...")
                ta_report = ta_engine.analyze(symbol, df)
                
                # 3. Run Fundamentals
                logger.info(f"Running Fundamental Analysis on {symbol}...")
                fund_data = fetcher.fetch_fundamentals(symbol)
                fund_report = fund_engine.analyze(symbol, fund_data)
                
                logger.info(f"Fundamentals Result: Score={fund_report['overall_score']} "
                            f"Confidence={fund_report['confidence']} "
                            f"Eligible={fund_report['is_eligible']}")
                            
                # 4. Run Options Analysis (LEAPS)
                logger.info(f"Running Options Analysis (LEAPS) for {symbol}...")
                # Fetch chains (min 300 days default)
                chain = fetcher.fetch_leaps_chains(symbol)
                
                opt_report = opt_engine.analyze_chain(symbol, current_price, chain)
                if opt_report['count'] > 0:
                     logger.info(f"Options Found: {opt_report['count']} candidates.")
                else:
                    logger.warning(f"No LEAPS chains found for {symbol} or filtered out.")

                # 5. Run Decision Engine
                logger.info(f"Running Decision Engine for {symbol}...")
                decision_result = decision_engine.evaluate(symbol, ta_report, fund_report, opt_report)
                
                logger.info(f"=== FINAL DECISION FOR {symbol}: {decision_result['decision']} ===")
                for reason in decision_result['reasons']:
                    logger.info(f" - {reason}")
                logger.info("========================================")

            else:
                logger.warning(f"Failed to fetch data for {symbol}")

    except Exception as e:
        logger.error(f"Error during execution: {e}", exc_info=True)

def run_scanner():
    """
    Run the scanner using the new ProviderManager abstraction.
    Phase 7.5: Uses Tradier for options (if configured), yfinance for fundamentals.
    """
    from src.utils.logger import setup_logger
    from src.utils.config_loader import load_config
    from src.data.universe import UniverseBuilder
    from src.providers.manager import ProviderManager
    from src.analysis.technical import TechnicalAnalyzer
    from src.analysis.fundamentals import FundamentalsAnalyzer
    from src.analysis.options import OptionsAnalyzer
    from src.decision.engine import DecisionEngine
    from src.scanner import Scanner

    config = load_config()
    logger = setup_logger("LEAPSCOPE", config.get("app", {}).get("log_level", "INFO"))
    
    logger.info("=== LEAPSCOPE Scanner (Phase 7.5) ===")
    logger.info(f"Version: {config.get('app', {}).get('version', 'unknown')}")
    
    # Initialize ProviderManager (handles Tradier + yfinance)
    provider_manager = ProviderManager(config)
    
    universe = UniverseBuilder()
    
    # Initialize analysis engines
    ta_engine = TechnicalAnalyzer(config=config.get("technical_analysis", {}))
    fund_engine = FundamentalsAnalyzer(config=config.get("fundamentals", {}))
    opt_engine = OptionsAnalyzer(config=config.get("options", {}))
    decision_engine = DecisionEngine(config=config.get("decision", {}))
    
    # Initialize scanner with ProviderManager
    scanner = Scanner(
        provider_manager=provider_manager,
        ta_engine=ta_engine,
        fund_engine=fund_engine,
        opt_engine=opt_engine,
        decision_engine=decision_engine,
        config=config  # Pass full config for ETF list etc.
    )
    
    # Scan universe
    symbols = universe.get_sp500_tickers()[:10]  # First 10 for testing
    results = scanner.scan(symbols)
    
    logger.info(f"Scanner complete. {len(results)} results saved.")
    return results

def run_portfolio():
    """
    Display portfolio summary and signals via CLI.
    Phase 8: Portfolio monitoring command.
    """
    from src.utils.logger import setup_logger
    from src.utils.config_loader import load_config
    from src.providers.manager import ProviderManager
    from src.portfolio.manager import PortfolioManager
    from src.portfolio.models import SignalType, Severity
    
    config = load_config()
    logger = setup_logger("LEAPSCOPE", config.get("app", {}).get("log_level", "INFO"))
    
    logger.info("=== LEAPSCOPE Portfolio Monitor (Phase 8) ===")
    
    # Initialize
    provider = ProviderManager(config)
    portfolio_mgr = PortfolioManager(provider, config)
    
    # Get and refresh positions
    positions = portfolio_mgr.refresh_portfolio()
    
    if not positions:
        print("\n📂 Portfolio is empty. No open positions found.")
        print("   Add positions via dashboard or import from JSON.")
        return
    
    # Get summary
    summary = portfolio_mgr.get_portfolio_summary(positions)
    
    # Print Portfolio Summary
    print("\n" + "="*60)
    print("📊 PORTFOLIO SUMMARY")
    print("="*60)
    print(f"  Positions:        {summary['total_positions']}")
    print(f"  Market Value:     ${summary['total_market_value']:,.2f}")
    print(f"  Cost Basis:       ${summary['total_cost_basis']:,.2f}")
    print(f"  Unrealized P&L:   ${summary['total_unrealized_pnl']:,.2f} ({summary['total_unrealized_pnl_pct']:.1f}%)")
    print(f"  Critical Alerts:  {summary.get('critical_count', 0)}")
    print(f"  Last Updated:     {summary.get('last_updated', 'N/A')}")
    
    # Print Signal Breakdown
    if summary.get("signals"):
        print("\n" + "-"*60)
        print("📢 SIGNAL BREAKDOWN")
        print("-"*60)
        for sig_type, count in summary["signals"].items():
            emoji = "🔴" if sig_type in ["STOP_LOSS", "TECH_INVALIDATED"] else "🟡" if sig_type != "HOLD" else "🟢"
            print(f"  {emoji} {sig_type}: {count}")
    
    # Print Positions Table
    print("\n" + "-"*60)
    print("📋 POSITIONS")
    print("-"*60)
    print(f"{'Symbol':<8} {'Strike':<8} {'Type':<6} {'Expiry':<12} {'P&L %':<10} {'Signal':<18}")
    print("-"*60)
    
    for p in positions:
        pnl_str = f"{p.unrealized_pnl_pct:.1f}%" if p.unrealized_pnl_pct else "N/A"
        signal_str = p.signal.signal_type.value if p.signal else "N/A"
        opt_type = p.option_type.value[0]  # C or P
        print(f"{p.symbol:<8} {p.strike:<8.0f} {opt_type:<6} {p.expiry:<12} {pnl_str:<10} {signal_str:<18}")
    
    # Print Critical Signals Details
    critical = [p for p in positions if p.signal and p.signal.severity == Severity.CRITICAL]
    if critical:
        print("\n" + "="*60)
        print("🚨 CRITICAL ALERTS - IMMEDIATE ATTENTION REQUIRED")
        print("="*60)
        for p in critical:
            print(f"\n  {p.symbol} {p.strike}{p.option_type.value[0]} {p.expiry}")
            print(f"  Signal: {p.signal.signal_type.value}")
            print(f"  P&L: {p.unrealized_pnl_pct:.1f}%" if p.unrealized_pnl_pct else "")
            print(f"  Reasons:")
            for reason in p.signal.reasons:
                if reason:
                    print(f"    - {reason}")
            print(f"  Action: {p.signal.recommended_action}")
    
    # Print non-critical alerts
    warnings = [p for p in positions if p.signal and p.signal.severity == Severity.WARN]
    if warnings:
        print("\n" + "-"*60)
        print("⚠️  WARNINGS")
        print("-"*60)
        for p in warnings:
            print(f"  {p.symbol} {p.strike}{p.option_type.value[0]}: {p.signal.signal_type.value}")
    
    print("\n" + "="*60)
    logger.info("Portfolio report complete.")


def add_position_from_json(json_path: str):
    """
    Add a position from a JSON file.
    Phase 8: CLI position import.
    """
    import json
    from pathlib import Path
    from src.utils.logger import setup_logger
    from src.utils.config_loader import load_config
    from src.providers.manager import ProviderManager
    from src.portfolio.manager import PortfolioManager
    from src.portfolio.models import Position
    
    config = load_config()
    logger = setup_logger("LEAPSCOPE", config.get("app", {}).get("log_level", "INFO"))
    
    path = Path(json_path)
    if not path.exists():
        print(f"❌ File not found: {json_path}")
        return
    
    try:
        with open(path, "r") as f:
            data = json.load(f)
        
        # Initialize manager
        provider = ProviderManager(config)
        portfolio_mgr = PortfolioManager(provider, config)
        
        # Handle single position or list
        if isinstance(data, list):
            positions_data = data
        elif "positions" in data:
            positions_data = data["positions"]
        else:
            positions_data = [data]
        
        added = 0
        for pos_data in positions_data:
            position = Position.from_dict(pos_data)
            if portfolio_mgr.add_position(position):
                print(f"✅ Added: {position.symbol} {position.strike}{position.option_type.value[0]} {position.expiry}")
                added += 1
            else:
                print(f"❌ Failed to add: {pos_data.get('symbol', 'unknown')}")
        
        print(f"\n📊 Added {added} position(s) to portfolio.")
        
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")


def print_usage():
    """Print CLI usage information."""
    print("""
LEAPSCOPE - LEAPS Options Analysis System

Usage:
  python src/main.py [command]

Commands:
  (none)      Run system diagnostics and test analysis
  scan        Run scanner on universe symbols
  portfolio   Display portfolio summary and signals
  add-position --json <path>   Add position(s) from JSON file

Examples:
  poetry run python src/main.py scan
  poetry run python src/main.py portfolio
  poetry run python src/main.py add-position --json data/new_position.json

Dashboard:
  poetry run streamlit run src/dashboard/app.py
""")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        main()
    elif sys.argv[1] == "scan":
        run_scanner()
    elif sys.argv[1] == "portfolio":
        run_portfolio()
    elif sys.argv[1] == "add-position":
        if len(sys.argv) >= 4 and sys.argv[2] == "--json":
            add_position_from_json(sys.argv[3])
        else:
            print("Usage: python src/main.py add-position --json <path>")
    elif sys.argv[1] in ["-h", "--help", "help"]:
        print_usage()
    else:
        print(f"Unknown command: {sys.argv[1]}")
        print_usage()
