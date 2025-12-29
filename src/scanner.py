import logging
import json
from datetime import datetime
from typing import List, Dict, Any, Optional, Set
from pathlib import Path

from src.providers.manager import ProviderManager
from src.analysis.technical import TechnicalAnalyzer
from src.analysis.fundamentals import FundamentalsAnalyzer
from src.analysis.options import OptionsAnalyzer
from src.decision.engine import DecisionEngine
from src.scoring.conviction import ConvictionScorer
from src.history.scan_history import ScanHistory
from src.alerts.manager import AlertManager, AlertSeverity


class Scanner:
    """
    Scanner with provider abstraction, conviction scoring, and history tracking.
    
    Phase 9 Enhancements:
    - Conviction scoring for result ranking
    - Scan history persistence and comparison
    - Alert generation for significant signals
    """
    
    def __init__(self, 
                 provider_manager: ProviderManager,
                 ta_engine: TechnicalAnalyzer,
                 fund_engine: FundamentalsAnalyzer,
                 opt_engine: OptionsAnalyzer,
                 decision_engine: DecisionEngine,
                 config: Dict[str, Any] = None):
        self.provider = provider_manager
        self.ta_engine = ta_engine
        self.fund_engine = fund_engine
        self.opt_engine = opt_engine
        self.decision_engine = decision_engine
        self.config = config or {}
        self.logger = logging.getLogger("LEAPSCOPE.Scanner")
        
        # Results path from config or default
        self.results_path = Path(self.config.get("results_path", "data/scan_results.json"))
        
        # Load known ETF symbols from config
        etf_config = self.config.get("etf", {})
        self._known_etfs: Set[str] = set(etf_config.get("known_symbols", []))
        
        # Phase 9: Initialize conviction scorer, history, and alerts
        self.conviction_scorer = ConvictionScorer(config)
        self.scan_history = ScanHistory()
        self.alert_manager = AlertManager(config=config)
        
        self.logger.info(f"Scanner initialized with {len(self._known_etfs)} known ETF symbols")

    def scan(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """
        Run the full analysis pipeline on a list of symbols.
        
        Pipeline:
        1. Fetch OHLCV data
        2. Run Technical Analysis
        3. Determine asset type (STOCK/ETF)
        4. Fetch fundamentals (if STOCK)
        5. Fetch earnings date (for risk gate)
        6. Fetch options chain (Tradier preferred)
        7. Run Decision Engine
        """
        self.logger.info(f"Starting scan for {len(symbols)} symbols...")
        self.logger.info(f"Available providers: {self.provider.get_available_providers()}")
        
        results = []
        
        for i, symbol in enumerate(symbols):
            self.logger.info(f"[{i+1}/{len(symbols)}] Scanning {symbol}...")
            try:
                result = self._scan_symbol(symbol)
                if result:
                    results.append(result)
                    
                    # Log GO signals prominently
                    if result["decision"] == "GO":
                        self.logger.info(f"*** GO SIGNAL DETECTED FOR {symbol} ***")
                
            except Exception as e:
                self.logger.error(f"Error scanning {symbol}: {e}", exc_info=True)
                continue

        self.logger.info(f"Scan complete. Processed {len(symbols)} symbols. Found {len(results)} valid results.")
        
        # Phase 9: Apply conviction scoring and sort by score
        results = self.conviction_scorer.score_batch(results)
        
        # Save results
        self._save_results(results)
        
        # Phase 9: Save to history and generate alerts
        scan_id = self.scan_history.save_scan(results, self.config)
        self._generate_scan_alerts(results, scan_id)
        
        return results

    def _scan_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Scan a single symbol through the full pipeline."""
        
        # 1. Fetch OHLCV data
        df = self.provider.fetch_ohlcv(symbol)
        if df.empty:
            self.logger.warning(f"Skipping {symbol}: No historical data.")
            return None
        
        current_price = float(df['close'].iloc[-1])
        
        # 2. Technical Analysis
        ta_report = self.ta_engine.analyze(symbol, df)
        if ta_report.get("status") == "INSUFFICIENT_DATA":
            self.logger.warning(f"Skipping {symbol}: Insufficient TA data.")
            return None

        # 3. Determine Asset Type (STOCK/ETF)
        asset_type = self._classify_asset(symbol)
        self.logger.info(f"[{symbol}] Asset type: {asset_type}")
        
        # 4. Fundamental Analysis
        fund_data = self.provider.fetch_fundamentals(symbol)
        fund_report = self.fund_engine.analyze(symbol, fund_data, asset_type=asset_type)
        
        # 5. Fetch Earnings Date (for risk gate)
        earnings_date = None
        if asset_type != "ETF":  # ETFs don't have earnings
            earnings_date = self.provider.fetch_earnings_date(symbol)
            if earnings_date:
                self.logger.info(f"[{symbol}] Next earnings: {earnings_date.strftime('%Y-%m-%d')}")
        
        # 6. Options Analysis (Tradier preferred)
        chain = self.provider.fetch_options_chain(symbol)
        opt_report = self.opt_engine.analyze_chain(symbol, current_price, chain)
        
        # 7. Decision Engine (with earnings date and asset type)
        decision_result = self.decision_engine.evaluate(
            symbol=symbol,
            ta_report=ta_report,
            fund_report=fund_report,
            opt_report=opt_report,
            earnings_date=earnings_date,
            asset_type=asset_type
        )
        
        # Compile Result
        return {
            "symbol": symbol,
            "timestamp": datetime.utcnow().isoformat(),
            "current_price": current_price,
            "asset_type": asset_type,
            "decision": decision_result["decision"],
            "reasons": decision_result["reasons"],
            "earnings_risk": decision_result.get("earnings_risk", False),
            "summary": decision_result["summary"],
            "scores": {
                "fundamental": fund_report["overall_score"],
                "technical_trend": ta_report["trend"],
                "options_candidates": opt_report.get("count", 0)
            },
            "details": {
                "fundamentals": fund_report,
                "technical": ta_report,
                "options": opt_report
            }
        }

    def _classify_asset(self, symbol: str) -> str:
        """
        Classify asset as STOCK or ETF.
        Uses known ETF list first, then provider detection.
        """
        # Check known ETF list first (fast path)
        if symbol.upper() in self._known_etfs:
            return "ETF"
        
        # Fall back to provider detection
        return self.provider.fetch_asset_type(symbol)

    def _save_results(self, results: List[Dict[str, Any]]):
        """Save results to JSON file."""
        try:
            self.results_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.results_path, "w") as f:
                json.dump(results, f, indent=2, default=str)
            self.logger.info(f"Results saved to {self.results_path}")
        except Exception as e:
            self.logger.error(f"Failed to save results: {e}")
    
    def _generate_scan_alerts(self, results: List[Dict[str, Any]], scan_id: str):
        """Generate alerts for significant scan results (Phase 9)."""
        try:
            # Get comparison with previous scan
            comparison = self.scan_history.compare_scans(scan_id)
            
            if not comparison:
                return
            
            # Alert on new GO signals
            for symbol in comparison.new_go_signals:
                result = next((r for r in results if r["symbol"] == symbol), None)
                if result:
                    conviction = result.get("conviction", {})
                    self.alert_manager.alert_new_go_signal(
                        symbol=symbol,
                        conviction_score=conviction.get("score", 0),
                        reasons=result.get("reasons", [])[:3]
                    )
            
            # Alert on signal upgrades (WATCH → GO)
            for upgrade in comparison.upgraded_signals:
                if upgrade["to"] == "GO":
                    self.alert_manager.alert_signal_upgrade(
                        symbol=upgrade["symbol"],
                        old_signal=upgrade["from"],
                        new_signal=upgrade["to"]
                    )
            
            self.logger.info(f"Generated alerts: {len(comparison.new_go_signals)} new GO, {len(comparison.upgraded_signals)} upgrades")
            
        except Exception as e:
            self.logger.warning(f"Error generating scan alerts: {e}")
    
    def get_scan_comparison(self, current_id: str = None) -> Optional[Dict[str, Any]]:
        """Get comparison between current and previous scan."""
        if current_id:
            comparison = self.scan_history.compare_scans(current_id)
        else:
            latest = self.scan_history.get_latest_scan()
            if latest:
                comparison = self.scan_history.compare_scans(latest.id)
            else:
                return None
        
        return comparison.to_dict() if comparison else None
    
    def get_scan_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent scan history."""
        records = self.scan_history.get_recent_scans(limit)
        return [r.to_dict() for r in records]
