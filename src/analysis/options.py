import pandas as pd
import logging
from typing import Dict, Any, List
from datetime import datetime
from src.analysis.greeks import GreeksCalculator

class OptionsAnalyzer:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger("LEAPSCOPE.Options")
        
        # Load Config
        self.min_days = config.get("min_days_to_expiration", 300)
        self.min_oi = config.get("min_open_interest", 50)
        self.min_vol = config.get("min_volume", 5)
        self.max_spread_pct = config.get("max_bid_ask_spread_pct", 0.10)
        self.target_delta_min = config.get("target_delta_min", 0.65)
        self.target_delta_max = config.get("target_delta_max", 0.85)
        
        # Risk free rate (could come from config, defaulting to 4.5% for now)
        self.risk_free_rate = 0.045

    def analyze_chain(self, symbol: str, current_price: float, chain: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyze the provided LEAPS chain and return filtered candidates.
        Expects chain to have columns: contractSymbol, strike, expiration, bid, ask, openInterest, volume, impliedVolatility
        """
        if chain.empty:
            return {"symbol": symbol, "candidates": [], "count": 0, "status": "NO_DATA"}

        candidates = []
        
        # Ensure we work on a copy
        df = chain.copy()
        
        # 1. Basic Filtering (Liquidity & Spread)
        # Calculate Spread Pct
        df['mid_price'] = (df['bid'] + df['ask']) / 2
        df['spread_pct'] = (df['ask'] - df['bid']) / df['mid_price']
        
        # Filter
        df = df[
            (df['openInterest'] >= self.min_oi) &
            (df['volume'] >= self.min_vol) & 
            (df['spread_pct'] <= self.max_spread_pct)
        ].copy()
        
        if df.empty:
            self.logger.info(f"No options passed liquidity/spread filters for {symbol}")
            return {"symbol": symbol, "candidates": [], "count": 0, "status": "NO_LIQUIDITY"}

        # 2. Greeks Calculation & Delta Filtering
        # We need T (time to expiry in years)
        today = datetime.now()
        
        for _, row in df.iterrows():
            try:
                exp_date = datetime.strptime(str(row['expiration']), "%Y-%m-%d")
                days_to_exp = (exp_date - today).days
                T = days_to_exp / 365.0
                
                # Check Min Days again just in case
                if days_to_exp < self.min_days:
                    continue

                # Calculate Greeks
                iv = row['impliedVolatility']
                strike = row['strike']
                
                greeks = GreeksCalculator.calculate_call_greeks(
                    S=current_price,
                    K=strike,
                    T=T,
                    r=self.risk_free_rate,
                    sigma=iv
                )
                
                delta = greeks.get('delta')
                
                # Check Delta Filter
                if delta and self.target_delta_min <= delta <= self.target_delta_max:
                    candidate = {
                        "contract_symbol": row['contractSymbol'],
                        "expiration": row['expiration'],
                        "strike": strike,
                        "type": "CALL",
                        "bid": row['bid'],
                        "ask": row['ask'],
                        "mid": row['mid_price'],
                        "iv": iv,
                        "oi": row['openInterest'],
                        "volume": row['volume'],
                        "greeks": greeks,
                        "days_to_expiry": days_to_exp,
                        "spread_pct": row['spread_pct']
                    }
                    candidates.append(candidate)
                    
            except Exception as e:
                self.logger.warning(f"Error processing option {row.get('contractSymbol', 'unknown')}: {e}")
                continue

        # Sort by Delta (highest first) or OI? Let's sort by OI for liquidity
        candidates.sort(key=lambda x: x['oi'], reverse=True)
        
        return {
            "symbol": symbol,
            "current_price": current_price,
            "count": len(candidates),
            "candidates": candidates,
            "status": "OK"
        }
