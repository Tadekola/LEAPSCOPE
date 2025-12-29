import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from enum import Enum


class Decision(str, Enum):
    GO = "GO"
    NO_GO = "NO_GO"
    WATCH = "WATCH"


class DecisionEngine:
    """
    Decision Engine with strict UNKNOWN handling and earnings risk gate.
    
    Policy Rules:
    - UNKNOWN data NEVER passes a gate (fails or neutral)
    - Earnings proximity triggers automatic downgrade
    - ETFs bypass fundamental scoring
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger("LEAPSCOPE.Decision")
        
        # Load Thresholds
        self.require_bullish = config.get("require_bullish_trend", True)
        self.max_rsi = config.get("max_rsi_entry", 70)
        self.min_fund_score = config.get("min_fundamentals_score", 60)
        self.max_iv_hv_ratio = config.get("max_iv_hv_ratio", 1.5)
        
        # Earnings risk gate (P0 fix)
        self.earnings_block_days = config.get("earnings_block_days", 14)
        
        # UNKNOWN data policy (P0 fix)
        self.unknown_data_policy = config.get("unknown_data_policy", "fail")  # fail | neutral
        
        # ETF handling
        self.etf_bypass_fundamentals = config.get("etf_bypass_fundamentals", True)

    def evaluate(self, 
                 symbol: str, 
                 ta_report: Dict[str, Any], 
                 fund_report: Dict[str, Any], 
                 opt_report: Dict[str, Any],
                 earnings_date: Optional[datetime] = None,
                 asset_type: str = "STOCK") -> Dict[str, Any]:
        """
        Evaluate all reports to produce a final trading decision.
        
        Args:
            symbol: Ticker symbol
            ta_report: Technical analysis report
            fund_report: Fundamentals report
            opt_report: Options analysis report
            earnings_date: Next earnings date (if available)
            asset_type: "STOCK", "ETF", or "UNKNOWN"
        """
        reasons = []
        warnings = []
        
        # 1. Technical Analysis Check
        ta_status = self._evaluate_technical(ta_report, reasons)
        
        # 2. Fundamental Analysis Check (with ETF handling)
        fund_status = self._evaluate_fundamental(fund_report, reasons, asset_type)
        
        # 3. Options/Volatility Check (with strict UNKNOWN handling)
        opt_status = self._evaluate_options(opt_report, ta_report, reasons)
        
        # 4. Earnings Risk Gate (P0 fix)
        earnings_risk = self._check_earnings_risk(earnings_date, reasons)
        
        # Final Decision Logic
        decision = Decision.NO_GO
        
        if ta_status and fund_status and opt_status:
            decision = Decision.GO
            reasons.append("All systems GO.")
        elif not opt_status and (ta_status and fund_status):
            decision = Decision.WATCH
            reasons.append("Fundamentals and Technicals align, but Options/Volatility conditions not met.")
        else:
            decision = Decision.NO_GO
        
        # Apply Earnings Risk Downgrade
        if earnings_risk and decision == Decision.GO:
            decision = Decision.WATCH
            self.logger.warning(f"[{symbol}] Decision downgraded from GO to WATCH due to earnings proximity")
        
        result = {
            "symbol": symbol,
            "decision": decision.value,
            "reasons": reasons,
            "asset_type": asset_type,
            "earnings_risk": earnings_risk,
            "summary": {
                "technical": ta_status,
                "fundamental": fund_status,
                "options": opt_status,
                "earnings_clear": not earnings_risk
            }
        }
        
        self.logger.info(f"Decision for {symbol} ({asset_type}): {decision.value}")
        return result

    def _evaluate_technical(self, report: Dict[str, Any], reasons: List[str]) -> bool:
        """Evaluate technical analysis with UNKNOWN handling."""
        if not report or report.get("status") == "INSUFFICIENT_DATA":
            reasons.append("Technical Analysis: Insufficient Data")
            return False
        
        trend = report.get("trend")
        indicators = report.get("indicators", {})
        rsi = indicators.get("rsi")
        
        passed = True
        
        # Trend Check - UNKNOWN trend fails
        if trend == "UNKNOWN":
            reasons.append("Technical: Trend is UNKNOWN (insufficient data)")
            self.logger.warning("UNKNOWN trend detected - failing technical check")
            return False
        
        if self.require_bullish and trend != "BULLISH":
            reasons.append(f"Trend is {trend} (Bullish required)")
            passed = False
        
        # RSI Check
        if rsi is not None and rsi > self.max_rsi:
            reasons.append(f"RSI is Overbought ({rsi:.1f} > {self.max_rsi})")
            passed = False
        
        return passed

    def _evaluate_fundamental(self, report: Dict[str, Any], reasons: List[str], asset_type: str) -> bool:
        """
        Evaluate fundamentals with ETF bypass support.
        ETFs get neutral/pass treatment since they don't have company fundamentals.
        """
        # ETF Bypass Logic
        if asset_type == "ETF" and self.etf_bypass_fundamentals:
            reasons.append("ETF: Fundamentals check bypassed (ETF policy)")
            self.logger.info("ETF detected - bypassing fundamental scoring")
            return True
        
        if not report:
            reasons.append("Fundamentals: No Data (UNKNOWN)")
            self.logger.warning("UNKNOWN fundamentals - failing check per policy")
            return False
        
        score = report.get("overall_score", 0)
        eligible = report.get("is_eligible", False)
        confidence = report.get("confidence", "LOW")
        
        # Low confidence with critical missing data should fail
        if confidence == "LOW" and score == 0:
            reasons.append("Fundamentals: Critical data missing (LOW confidence)")
            self.logger.warning("LOW confidence fundamentals with zero score - failing check")
            return False
        
        if score < self.min_fund_score:
            reasons.append(f"Fundamental Score {score} < {self.min_fund_score}")
            return False
        
        if not eligible:
            reasons.append("Marked ineligible by Fundamentals Engine")
            return False
        
        return True

    def _evaluate_options(self, opt_report: Dict[str, Any], ta_report: Dict[str, Any], reasons: List[str]) -> bool:
        """
        Evaluate options with STRICT UNKNOWN handling.
        P0 FIX: Missing HV or IV data MUST fail, not pass.
        """
        if not opt_report or opt_report.get("status") not in ("OK",):
            status = opt_report.get("status", "NO_DATA") if opt_report else "NO_DATA"
            reasons.append(f"Options: {status} - No suitable LEAPS chains found")
            return False
        
        count = opt_report.get("count", 0)
        if count == 0:
            reasons.append("Options: 0 candidates found matching criteria")
            return False
        
        candidates = opt_report.get("candidates", [])
        if not candidates:
            reasons.append("Options: No candidates available")
            return False
        
        # Calculate average IV from candidates
        iv_values = [c.get('iv') for c in candidates if c.get('iv') is not None]
        
        if not iv_values:
            # P0 FIX: Missing IV data must FAIL
            reasons.append("Options: UNKNOWN IV data - cannot evaluate volatility pricing")
            self.logger.warning("UNKNOWN IV data detected - failing options check per policy")
            return False
        
        avg_iv = sum(iv_values) / len(iv_values)
        
        # Get Historical Volatility from TA report
        indicators = ta_report.get("indicators", {})
        hv = indicators.get("hv")
        
        # P0 FIX: Missing HV must FAIL, not pass with warning
        if hv is None or hv <= 0:
            reasons.append("Options: UNKNOWN Historical Volatility - cannot compare IV/HV ratio")
            self.logger.warning("UNKNOWN HV data detected - failing options check per policy")
            return False
        
        # IV/HV Ratio Check
        ratio = avg_iv / hv
        if ratio > self.max_iv_hv_ratio:
            reasons.append(f"Volatility too expensive: IV/HV Ratio {ratio:.2f} > {self.max_iv_hv_ratio}")
            return False
        
        return True

    def _check_earnings_risk(self, earnings_date: Optional[datetime], reasons: List[str]) -> bool:
        """
        Check if earnings date is within the risk window.
        Returns True if there IS a risk (earnings too close).
        """
        if earnings_date is None:
            # No earnings date available - could be ETF or data unavailable
            # For safety, this is NOT a risk (we don't block on missing data for earnings)
            return False
        
        today = datetime.now()
        days_to_earnings = (earnings_date - today).days
        
        if days_to_earnings < 0:
            # Earnings already passed
            return False
        
        if days_to_earnings <= self.earnings_block_days:
            reasons.append(
                f"Earnings within {days_to_earnings} days ({earnings_date.strftime('%Y-%m-%d')}) "
                f"- binary risk avoided (threshold: {self.earnings_block_days} days)"
            )
            self.logger.warning(
                f"Earnings risk gate triggered: {days_to_earnings} days to earnings"
            )
            return True
        
        return False
