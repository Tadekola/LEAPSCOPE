"""
Conviction Scoring Module for LEAPSCOPE Phase 9.

Combines multiple factors into a normalized 0-100 conviction score
for ranking and prioritizing scanner results.
"""

import logging
from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass


class ConvictionBand(str, Enum):
    """Conviction score bands for quick classification."""
    STRONG = "STRONG"      # >= 75
    MODERATE = "MODERATE"  # 50-74
    WEAK = "WEAK"          # < 50


@dataclass
class ConvictionResult:
    """Result of conviction scoring."""
    score: float
    band: ConvictionBand
    components: Dict[str, float]
    notes: list
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 1),
            "band": self.band.value,
            "components": {k: round(v, 1) for k, v in self.components.items()},
            "notes": self.notes
        }


class ConvictionScorer:
    """
    Calculates conviction scores for scanner results.
    
    Components:
    1. Technical Strength (trend, RSI, signals)
    2. Fundamental Quality (or ETF proxy)
    3. Volatility Attractiveness (IV/HV ratio)
    4. Liquidity Quality (OI, spread)
    
    All weights are config-driven for flexibility.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.logger = logging.getLogger("LEAPSCOPE.ConvictionScorer")
        
        # Load weights from config
        scoring_config = self.config.get("conviction_scoring", {})
        
        self.weights = {
            "technical": scoring_config.get("weight_technical", 0.30),
            "fundamental": scoring_config.get("weight_fundamental", 0.25),
            "volatility": scoring_config.get("weight_volatility", 0.25),
            "liquidity": scoring_config.get("weight_liquidity", 0.20),
        }
        
        # Thresholds
        self.strong_threshold = scoring_config.get("strong_threshold", 75)
        self.moderate_threshold = scoring_config.get("moderate_threshold", 50)
        
        # ETF handling
        self.etf_fundamental_score = scoring_config.get("etf_fundamental_score", 70)
        
        self.logger.info(f"ConvictionScorer initialized with weights: {self.weights}")
    
    def score(self, scan_result: Dict[str, Any]) -> ConvictionResult:
        """
        Calculate conviction score for a single scan result.
        
        Args:
            scan_result: Full scan result dict from scanner
            
        Returns:
            ConvictionResult with score, band, components, and notes
        """
        notes = []
        components = {}
        
        # 1. Technical Strength Score (0-100)
        tech_score = self._score_technical(scan_result, notes)
        components["technical"] = tech_score
        
        # 2. Fundamental Score (0-100)
        fund_score = self._score_fundamental(scan_result, notes)
        components["fundamental"] = fund_score
        
        # 3. Volatility Attractiveness (0-100)
        vol_score = self._score_volatility(scan_result, notes)
        components["volatility"] = vol_score
        
        # 4. Liquidity Quality (0-100)
        liq_score = self._score_liquidity(scan_result, notes)
        components["liquidity"] = liq_score
        
        # Calculate weighted score
        total_score = (
            tech_score * self.weights["technical"] +
            fund_score * self.weights["fundamental"] +
            vol_score * self.weights["volatility"] +
            liq_score * self.weights["liquidity"]
        )
        
        # Determine band
        band = self._get_band(total_score)
        
        return ConvictionResult(
            score=total_score,
            band=band,
            components=components,
            notes=notes
        )
    
    def _score_technical(self, result: Dict[str, Any], notes: list) -> float:
        """Score technical analysis strength (0-100)."""
        score = 50.0  # Base neutral score
        
        details = result.get("details", {})
        ta = details.get("technical", {})
        
        if not ta:
            notes.append("Technical data unavailable")
            return 30.0
        
        trend = ta.get("trend", "UNKNOWN")
        indicators = ta.get("indicators", {})
        signals = ta.get("signals", {})
        
        # Trend contribution (up to 40 points)
        if trend == "BULLISH":
            score += 30
        elif trend == "BEARISH":
            score -= 30
        elif trend == "NEUTRAL":
            score += 0
        else:  # UNKNOWN
            score -= 20
            notes.append("Trend unknown - technical score reduced")
        
        # RSI contribution (up to 20 points)
        rsi = indicators.get("rsi")
        if rsi is not None:
            if 40 <= rsi <= 60:  # Neutral zone - good for entry
                score += 15
            elif 30 <= rsi < 40 or 60 < rsi <= 70:
                score += 10
            elif rsi < 30:  # Oversold - could be opportunity
                score += 5
            elif rsi > 70:  # Overbought - risky entry
                score -= 10
        
        # Signal contribution (up to 10 points)
        if signals.get("golden_cross"):
            score += 10
            notes.append("Golden cross detected")
        if signals.get("death_cross"):
            score -= 15
            notes.append("Death cross detected")
        
        return max(0, min(100, score))
    
    def _score_fundamental(self, result: Dict[str, Any], notes: list) -> float:
        """Score fundamental quality (0-100)."""
        asset_type = result.get("asset_type", "STOCK")
        
        # ETF handling - use proxy score
        if asset_type == "ETF":
            notes.append(f"ETF: Using proxy fundamental score ({self.etf_fundamental_score})")
            return self.etf_fundamental_score
        
        details = result.get("details", {})
        fund = details.get("fundamentals", {})
        
        if not fund:
            notes.append("Fundamental data unavailable")
            return 30.0
        
        # Use the overall fundamental score directly
        raw_score = fund.get("overall_score", 0)
        confidence = fund.get("confidence", "LOW")
        
        # Adjust based on confidence
        if confidence == "HIGH":
            adjustment = 1.0
        elif confidence == "MEDIUM":
            adjustment = 0.9
            notes.append("Medium confidence fundamentals")
        else:
            adjustment = 0.7
            notes.append("Low confidence fundamentals - score reduced")
        
        return min(100, raw_score * adjustment)
    
    def _score_volatility(self, result: Dict[str, Any], notes: list) -> float:
        """Score volatility attractiveness (0-100)."""
        score = 50.0
        
        details = result.get("details", {})
        ta = details.get("technical", {})
        opt = details.get("options", {})
        
        indicators = ta.get("indicators", {})
        hv = indicators.get("hv")
        
        candidates = opt.get("candidates", [])
        
        if not candidates:
            notes.append("No options candidates - volatility score neutral")
            return 50.0
        
        # Calculate average IV from candidates
        iv_values = [c.get("iv") for c in candidates if c.get("iv")]
        
        if not iv_values:
            notes.append("IV data unavailable")
            return 40.0
        
        avg_iv = sum(iv_values) / len(iv_values)
        
        if hv and hv > 0:
            iv_hv_ratio = avg_iv / hv
            
            # Ideal: IV slightly below or equal to HV (good value)
            if iv_hv_ratio <= 0.9:
                score = 90  # Excellent - IV below HV
                notes.append(f"IV/HV ratio excellent ({iv_hv_ratio:.2f})")
            elif iv_hv_ratio <= 1.1:
                score = 80  # Good - fair priced
            elif iv_hv_ratio <= 1.3:
                score = 65  # Acceptable
            elif iv_hv_ratio <= 1.5:
                score = 50  # Neutral
            else:
                score = 30  # Expensive premium
                notes.append(f"IV/HV ratio high ({iv_hv_ratio:.2f}) - expensive")
        else:
            # No HV available - use IV percentile heuristic
            if avg_iv < 0.20:
                score = 75
            elif avg_iv < 0.35:
                score = 60
            else:
                score = 45
            notes.append("HV unavailable - using IV heuristic")
        
        return score
    
    def _score_liquidity(self, result: Dict[str, Any], notes: list) -> float:
        """Score liquidity quality (0-100)."""
        details = result.get("details", {})
        opt = details.get("options", {})
        
        candidates = opt.get("candidates", [])
        
        if not candidates:
            notes.append("No options candidates for liquidity scoring")
            return 30.0
        
        # Score based on average OI and spread
        total_oi = 0
        spread_scores = []
        
        for c in candidates:
            oi = c.get("oi", 0) or c.get("openInterest", 0) or 0
            total_oi += oi
            
            bid = c.get("bid", 0)
            ask = c.get("ask", 0)
            
            if bid and ask and ask > 0:
                spread_pct = (ask - bid) / ask
                if spread_pct <= 0.03:
                    spread_scores.append(100)
                elif spread_pct <= 0.05:
                    spread_scores.append(85)
                elif spread_pct <= 0.10:
                    spread_scores.append(65)
                elif spread_pct <= 0.15:
                    spread_scores.append(45)
                else:
                    spread_scores.append(25)
        
        avg_oi = total_oi / len(candidates) if candidates else 0
        
        # OI score
        if avg_oi >= 5000:
            oi_score = 100
        elif avg_oi >= 1000:
            oi_score = 85
        elif avg_oi >= 500:
            oi_score = 70
        elif avg_oi >= 100:
            oi_score = 55
        elif avg_oi >= 50:
            oi_score = 40
        else:
            oi_score = 25
            notes.append("Low open interest - liquidity concern")
        
        # Spread score
        spread_score = sum(spread_scores) / len(spread_scores) if spread_scores else 50
        
        # Combined liquidity score (60% OI, 40% spread)
        return oi_score * 0.6 + spread_score * 0.4
    
    def _get_band(self, score: float) -> ConvictionBand:
        """Determine conviction band from score."""
        if score >= self.strong_threshold:
            return ConvictionBand.STRONG
        elif score >= self.moderate_threshold:
            return ConvictionBand.MODERATE
        else:
            return ConvictionBand.WEAK
    
    def score_batch(self, results: list) -> list:
        """Score a batch of scan results and return sorted by conviction."""
        scored = []
        for result in results:
            conviction = self.score(result)
            result["conviction"] = conviction.to_dict()
            scored.append(result)
        
        # Sort by conviction score descending
        scored.sort(key=lambda x: x["conviction"]["score"], reverse=True)
        return scored
