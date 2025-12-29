import logging
from typing import Dict, Any, Literal

class FundamentalsAnalyzer:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger("LEAPSCOPE.FA")
        
        # Load Config
        self.weights = config.get("weights", {
            "growth": 0.30,
            "profitability": 0.30,
            "balance_sheet": 0.25,
            "stability": 0.15
        })
        self.thresholds = config.get("thresholds", {})
        
        self.min_score_leaps = config.get("min_score_leaps", 60)

    def analyze(self, symbol: str, info: Dict[str, Any], asset_type: str = "STOCK") -> Dict[str, Any]:
        """
        Analyze fundamental data for a symbol.
        
        Args:
            symbol: Ticker symbol
            info: Fundamental data dictionary
            asset_type: "STOCK", "ETF", or "UNKNOWN"
        """
        # ETF bypass - return neutral score
        if asset_type == "ETF":
            self.logger.info(f"[{symbol}] ETF detected - applying neutral fundamental score")
            return {
                "symbol": symbol,
                "overall_score": 70.0,  # Neutral passing score for ETFs
                "confidence": "MEDIUM",
                "is_eligible": True,
                "asset_type": "ETF",
                "dimensions": {},
                "notes": ["ETF: Fundamental scoring bypassed per policy"]
            }
        
        if not info:
            self.logger.warning(f"No fundamental data provided for {symbol}")
            return {
                "symbol": symbol,
                "overall_score": 0,
                "confidence": "LOW",
                "is_eligible": False,
                "asset_type": asset_type,
                "notes": ["No data available"]
            }

        # 1. Analyze Dimensions
        growth_res = self._analyze_growth(info)
        prof_res = self._analyze_profitability(info)
        bal_res = self._analyze_balance_sheet(info)
        stab_res = self._analyze_stability(info)

        # 2. Calculate Weighted Score
        weighted_score = 0.0
        total_weight = 0.0
        
        dimensions = {
            "growth": growth_res,
            "profitability": prof_res,
            "balance_sheet": bal_res,
            "stability": stab_res
        }

        # Check for Critical Failures or missing data impact
        confidence_scores = []

        for key, res in dimensions.items():
            weight = self.weights.get(key, 0.25)
            score = res.get("score", 0)
            weighted_score += score * weight
            total_weight += weight
            
            # Track confidence
            if res.get("confidence") == "HIGH": confidence_scores.append(1.0)
            elif res.get("confidence") == "MEDIUM": confidence_scores.append(0.5)
            else: confidence_scores.append(0.0)

        final_score = round(weighted_score, 1)
        
        # Determine Overall Confidence
        avg_conf = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0
        overall_confidence = "HIGH" if avg_conf >= 0.8 else ("MEDIUM" if avg_conf >= 0.5 else "LOW")

        # Compile Notes
        all_notes = []
        for d in dimensions.values():
            all_notes.extend(d.get("notes", []))

        # Check for LEAPS suitability
        is_eligible = final_score >= self.min_score_leaps

        result = {
            "symbol": symbol,
            "overall_score": final_score,
            "confidence": overall_confidence,
            "is_eligible": is_eligible,
            "asset_type": asset_type,
            "dimensions": dimensions,
            "notes": all_notes
        }
        
        self.logger.info(f"Fundamentals for {symbol}: Score={final_score} ({overall_confidence})")
        return result

    def _analyze_growth(self, info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze Growth Quality: Revenue Growth, Earnings Growth
        """
        score = 0
        notes = []
        missing = 0
        
        # Thresholds
        rev_thresh = self.thresholds.get("growth_revenue_yoy_good", 0.10)
        earn_thresh = self.thresholds.get("growth_earnings_yoy_good", 0.10)

        # Metrics
        rev_growth = info.get("revenueGrowth")
        earn_growth = info.get("earningsGrowth")

        # Scoring Logic (Simple Rules)
        # Revenue Growth (50 pts)
        if rev_growth is not None:
            if rev_growth >= rev_thresh: score += 50
            elif rev_growth > 0: score += 25
            else: notes.append(f"Negative revenue growth: {rev_growth:.1%}")
        else:
            missing += 1
            notes.append("Missing revenueGrowth")

        # Earnings Growth (50 pts)
        if earn_growth is not None:
            if earn_growth >= earn_thresh: score += 50
            elif earn_growth > 0: score += 25
            else: notes.append(f"Negative earnings growth: {earn_growth:.1%}")
        else:
            missing += 1
            notes.append("Missing earningsGrowth")

        confidence = self._calculate_confidence(missing, 2)
        
        return {
            "score": score,
            "confidence": confidence,
            "metrics": {"revenue_growth": rev_growth, "earnings_growth": earn_growth},
            "notes": notes
        }

    def _analyze_profitability(self, info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze Profitability: Margins, ROE
        """
        score = 0
        notes = []
        missing = 0
        
        # Thresholds
        margin_thresh = self.thresholds.get("profitability_net_margin_good", 0.15)
        roe_thresh = self.thresholds.get("profitability_roe_good", 0.15)

        # Metrics
        margins = info.get("profitMargins")
        roe = info.get("returnOnEquity")
        
        # Scoring
        # Margins (50 pts)
        if margins is not None:
            if margins >= margin_thresh: score += 50
            elif margins > 0: score += 25
            else: notes.append(f"Negative profit margins: {margins:.1%}")
        else:
            missing += 1
            notes.append("Missing profitMargins")

        # ROE (50 pts)
        if roe is not None:
            if roe >= roe_thresh: score += 50
            elif roe > 0: score += 25
            else: notes.append(f"Negative/Low ROE: {roe}")
        else:
            missing += 1
            notes.append("Missing returnOnEquity")
            
        confidence = self._calculate_confidence(missing, 2)

        return {
            "score": score,
            "confidence": confidence,
            "metrics": {"profit_margins": margins, "roe": roe},
            "notes": notes
        }

    def _analyze_balance_sheet(self, info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze Balance Sheet: Debt/Equity, Current Ratio
        """
        score = 0
        notes = []
        missing = 0
        
        # Thresholds
        de_max = self.thresholds.get("debt_to_equity_max_good", 1.5)
        cr_min = self.thresholds.get("current_ratio_min_good", 1.2)

        # Metrics
        # yfinance debtToEquity is usually a percentage (e.g. 150 = 1.5 ratio) or raw ratio? 
        # Checking typical yfinance output: it returns value like 156.43 for AAPL -> 1.56. 
        # It is usually Debt/Equity * 100. Let's assume input is raw scalar if < 10, or percent if > 10? 
        # Actually yfinance documentation says "Total Debt/Equity (mrq)". 
        # Let's handle the scaling cautiously. If > 10, divide by 100.
        
        de = info.get("debtToEquity")
        current_ratio = info.get("currentRatio")

        # Scoring
        # Debt to Equity (50 pts)
        if de is not None:
            # Normalize
            de_ratio = de / 100.0 if de > 10 else de
            
            if de_ratio <= de_max: score += 50
            elif de_ratio <= de_max * 2: score += 25
            else: notes.append(f"High Debt/Equity: {de_ratio:.2f}")
        else:
            # Some companies have no debt/equity field (e.g. ETFs sometimes). 
            missing += 1
            notes.append("Missing debtToEquity")

        # Current Ratio (50 pts)
        if current_ratio is not None:
            if current_ratio >= cr_min: score += 50
            elif current_ratio >= 1.0: score += 25
            else: notes.append(f"Weak Current Ratio: {current_ratio:.2f}")
        else:
            missing += 1
            notes.append("Missing currentRatio")

        confidence = self._calculate_confidence(missing, 2)

        return {
            "score": score,
            "confidence": confidence,
            "metrics": {"debt_to_equity": de, "current_ratio": current_ratio},
            "notes": notes
        }

    def _analyze_stability(self, info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze Stability: Cash Flow, Beta
        """
        score = 0
        notes = []
        missing = 0
        
        # Metrics
        ocf = info.get("operatingCashflow")
        beta = info.get("beta")

        # Scoring
        # Operating Cash Flow (60 pts) - Must be positive
        if ocf is not None:
            if ocf > 0: score += 60
            else: notes.append(f"Negative Operating Cash Flow: {ocf}")
        else:
            missing += 1
            notes.append("Missing operatingCashflow")

        # Beta (40 pts) - Prefer lower volatility for LEAPS stability? 
        # Or just not extreme. Let's penalize Beta > 2.0 or Beta < 0 (weird).
        if beta is not None:
            if 0 < beta < 1.5: score += 40
            elif 1.5 <= beta < 2.5: score += 20
            else: notes.append(f"High/Abnormal Beta: {beta}")
        else:
            missing += 1
            notes.append("Missing beta")

        confidence = self._calculate_confidence(missing, 2)

        return {
            "score": score,
            "confidence": confidence,
            "metrics": {"operating_cashflow": ocf, "beta": beta},
            "notes": notes
        }

    def _calculate_confidence(self, missing_count: int, total_metrics: int) -> Literal["HIGH", "MEDIUM", "LOW"]:
        if missing_count == 0: return "HIGH"
        if missing_count < total_metrics: return "MEDIUM"
        return "LOW"
