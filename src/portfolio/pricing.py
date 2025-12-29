"""
Position Pricing for LEAPSCOPE Phase 8.

Mark-to-market pricing using ProviderManager with fallback to computed Greeks.
"""

import logging
from datetime import datetime, date
from typing import Dict, Any, Optional, Tuple

from src.portfolio.models import Position, OptionType
from src.providers.manager import ProviderManager
from src.analysis.greeks import GreeksCalculator


class PositionPricer:
    """
    Mark-to-market pricer for portfolio positions.
    
    Pricing priority:
    1. Tradier (live options quotes with Greeks)
    2. yfinance (options chain data)
    3. Black-Scholes computed Greeks (fallback)
    """
    
    def __init__(self, provider_manager: ProviderManager, config: Dict[str, Any] = None):
        self.provider = provider_manager
        self.config = config or {}
        self.logger = logging.getLogger("LEAPSCOPE.Portfolio.Pricer")
        
        # Config
        portfolio_config = self.config.get("portfolio", {})
        self.pricing_preference = portfolio_config.get("pricing_preference", "MID")  # MID/BID/ASK
        self.allow_bs_fallback = portfolio_config.get("allow_bs_fallback", True)
        self.risk_free_rate = self.config.get("trading", {}).get("risk_free_rate", 0.04)
    
    def price_position(self, position: Position) -> Position:
        """
        Price a single position with current market data.
        
        Updates position with:
        - underlying_last
        - option_last (mid/bid/ask based on preference)
        - Greeks (delta, gamma, theta, vega)
        - IV
        - days_to_expiry
        - market_value, cost_basis
        - unrealized_pnl, unrealized_pnl_pct
        - pricing_source, pricing_confidence
        - last_updated
        """
        self.logger.info(f"Pricing position {position.symbol} {position.strike}{position.option_type.value[0]} {position.expiry}")
        
        # 1. Get underlying price
        underlying_price = self._get_underlying_price(position.symbol)
        if underlying_price is None:
            position.pricing_confidence = "LOW"
            position.pricing_source = "unavailable"
            self.logger.warning(f"Cannot get underlying price for {position.symbol}")
            return position
        
        position.underlying_last = underlying_price
        
        # 2. Calculate days to expiry
        position.days_to_expiry = self._calculate_days_to_expiry(position.expiry)
        
        # 3. Get option quote
        option_data = self._get_option_quote(position, underlying_price)
        
        if option_data:
            position.option_bid = option_data.get("bid")
            position.option_ask = option_data.get("ask")
            position.option_last = self._select_price(option_data)
            position.iv = option_data.get("iv")
            position.delta = option_data.get("delta")
            position.gamma = option_data.get("gamma")
            position.theta = option_data.get("theta")
            position.vega = option_data.get("vega")
            position.pricing_source = option_data.get("source", "provider")
            position.pricing_confidence = "HIGH" if position.iv else "MEDIUM"
        else:
            # Fallback to Black-Scholes computed values
            if self.allow_bs_fallback:
                position = self._apply_bs_fallback(position, underlying_price)
            else:
                position.pricing_confidence = "LOW"
                position.pricing_source = "unavailable"
        
        # 4. Calculate P&L
        position.cost_basis = position.calculate_cost_basis()
        position.market_value = position.calculate_market_value()
        
        pnl, pnl_pct = position.calculate_pnl()
        position.unrealized_pnl = pnl
        position.unrealized_pnl_pct = pnl_pct
        
        # 5. Update timestamp
        position.last_updated = datetime.utcnow()
        
        return position
    
    def price_all_positions(self, positions: list) -> list:
        """Price all positions in a list."""
        return [self.price_position(p) for p in positions]
    
    def _get_underlying_price(self, symbol: str) -> Optional[float]:
        """
        Get current underlying price using LIVE data when available.
        
        Priority: Tradier (live) > yfinance (fallback)
        """
        try:
            # Use live pricing method from ProviderManager
            price, source = self.provider.fetch_live_price(symbol)
            if price is not None:
                self._last_price_source = source
                return price
        except Exception as e:
            self.logger.error(f"Error fetching live price for {symbol}: {e}")
        
        # Fallback to OHLCV close
        try:
            df = self.provider.fetch_ohlcv(symbol, period="5d", interval="1d")
            if not df.empty:
                self._last_price_source = "ohlcv_fallback"
                return float(df['close'].iloc[-1])
        except Exception as e:
            self.logger.error(f"Error fetching OHLCV price for {symbol}: {e}")
        
        self._last_price_source = "unavailable"
        return None
    
    def _calculate_days_to_expiry(self, expiry_str: str) -> Optional[int]:
        """Calculate days until expiration."""
        try:
            expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
            today = date.today()
            return (expiry_date - today).days
        except ValueError:
            return None
    
    def _get_option_quote(self, position: Position, underlying_price: float) -> Optional[Dict[str, Any]]:
        """
        Get option quote from providers.
        
        Priority:
        1. Tradier LIVE option quote (direct contract lookup)
        2. Options chain search
        3. Return None (trigger BS fallback)
        """
        # Try direct live option quote first (Tradier)
        if hasattr(position, 'contract_symbol') and position.contract_symbol:
            live_quote = self.provider.fetch_live_option_quote(position.contract_symbol)
            if live_quote and live_quote.get("source") != "unavailable":
                self.logger.info(f"LIVE option quote obtained for {position.symbol}")
                live_quote["source"] = "tradier_live"
                return live_quote
        
        # Build OCC symbol and try direct lookup
        occ_symbol = self._build_occ_symbol(position)
        if occ_symbol:
            live_quote = self.provider.fetch_live_option_quote(occ_symbol)
            if live_quote and live_quote.get("source") != "unavailable":
                self.logger.info(f"LIVE option quote for {occ_symbol}")
                live_quote["source"] = "tradier_live"
                return live_quote
        
        # Fallback to options chain search
        try:
            # Fetch options chain (min_days=0 to get all expirations)
            chain = self.provider.fetch_options_chain(position.symbol, min_days=0)
            
            if chain.empty:
                self.logger.warning(f"No options chain data for {position.symbol}")
                return None
            
            # Filter for matching contract
            expiry_matches = chain[chain['expiration'] == position.expiry] if 'expiration' in chain.columns else chain
            
            if expiry_matches.empty:
                self.logger.warning(f"No matching expiration {position.expiry} for {position.symbol}")
                return None
            
            # Filter for strike
            strike_matches = expiry_matches[
                (expiry_matches['strike'] >= position.strike - 0.01) & 
                (expiry_matches['strike'] <= position.strike + 0.01)
            ]
            
            if strike_matches.empty:
                self.logger.warning(f"No matching strike {position.strike} for {position.symbol}")
                return None
            
            # Get the row
            row = strike_matches.iloc[0]
            
            # Extract data
            result = {
                "bid": row.get("bid"),
                "ask": row.get("ask"),
                "last": row.get("lastPrice") or row.get("last"),
                "iv": row.get("impliedVolatility") or row.get("iv"),
                "source": "provider"
            }
            
            # Calculate mid price
            if result["bid"] and result["ask"]:
                result["mid"] = (result["bid"] + result["ask"]) / 2
            
            # Try to get Greeks from chain
            if "delta" in row:
                result["delta"] = row.get("delta")
                result["gamma"] = row.get("gamma")
                result["theta"] = row.get("theta")
                result["vega"] = row.get("vega")
            elif result["iv"] and position.days_to_expiry and position.days_to_expiry > 0:
                # Compute Greeks
                T = position.days_to_expiry / 365.0
                greeks = GreeksCalculator.calculate_call_greeks(
                    S=underlying_price,
                    K=position.strike,
                    T=T,
                    r=self.risk_free_rate,
                    sigma=result["iv"]
                )
                
                if position.option_type == OptionType.PUT:
                    # Put delta = Call delta - 1
                    greeks["delta"] = greeks.get("delta", 0) - 1
                
                result.update(greeks)
                result["source"] = "provider+computed_greeks"
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error getting option quote: {e}")
            return None
    
    def _select_price(self, option_data: Dict[str, Any]) -> Optional[float]:
        """Select price based on preference (MID/BID/ASK)."""
        if self.pricing_preference == "BID":
            return option_data.get("bid")
        elif self.pricing_preference == "ASK":
            return option_data.get("ask")
        else:  # MID
            if option_data.get("mid"):
                return option_data["mid"]
            elif option_data.get("bid") and option_data.get("ask"):
                return (option_data["bid"] + option_data["ask"]) / 2
            return option_data.get("last")
    
    def _apply_bs_fallback(self, position: Position, underlying_price: float) -> Position:
        """
        Apply Black-Scholes fallback pricing.
        
        Uses Historical Volatility as proxy for IV.
        """
        self.logger.info(f"Using Black-Scholes fallback for {position.symbol}")
        
        # Get HV from technical analysis
        hv = self._get_historical_volatility(position.symbol)
        
        if hv is None or hv <= 0:
            position.pricing_confidence = "LOW"
            position.pricing_source = "bs_fallback_no_hv"
            return position
        
        T = position.days_to_expiry / 365.0 if position.days_to_expiry and position.days_to_expiry > 0 else 0.01
        
        greeks = GreeksCalculator.calculate_call_greeks(
            S=underlying_price,
            K=position.strike,
            T=T,
            r=self.risk_free_rate,
            sigma=hv
        )
        
        if position.option_type == OptionType.PUT:
            greeks["delta"] = greeks.get("delta", 0) - 1
        
        # Use theoretical price as option_last
        position.option_last = greeks.get("theoretical_price")
        position.delta = greeks.get("delta")
        position.gamma = greeks.get("gamma")
        position.theta = greeks.get("theta")
        position.vega = greeks.get("vega")
        position.iv = hv  # Using HV as proxy
        position.pricing_source = "bs_fallback_hv_proxy"
        position.pricing_confidence = "MEDIUM"
        
        return position
    
    def _get_historical_volatility(self, symbol: str) -> Optional[float]:
        """Calculate historical volatility for Black-Scholes fallback."""
        try:
            import numpy as np
            
            df = self.provider.fetch_ohlcv(symbol, period="6mo", interval="1d")
            if df.empty or len(df) < 20:
                return None
            
            # Calculate log returns
            log_returns = np.log(df['close'] / df['close'].shift(1))
            
            # Annualized volatility (20-day rolling, take latest)
            hv = log_returns.rolling(window=20).std().iloc[-1] * np.sqrt(252)
            
            return float(hv) if not np.isnan(hv) else None
            
        except Exception as e:
            self.logger.error(f"Error calculating HV: {e}")
            return None
    
    def _build_occ_symbol(self, position: Position) -> Optional[str]:
        """
        Build OCC-format option symbol from position details.
        Format: SYMBOL + YYMMDD + C/P + Strike (8 digits with 3 decimals)
        Example: AAPL251219C00200000
        """
        try:
            # Parse expiry date
            expiry_date = datetime.strptime(position.expiry, "%Y-%m-%d")
            date_part = expiry_date.strftime("%y%m%d")
            
            # Option type
            type_char = "C" if position.option_type == OptionType.CALL else "P"
            
            # Strike price (8 chars: 5 integer + 3 decimal, no decimal point)
            strike_int = int(position.strike * 1000)
            strike_part = f"{strike_int:08d}"
            
            occ_symbol = f"{position.symbol}{date_part}{type_char}{strike_part}"
            return occ_symbol
            
        except Exception as e:
            self.logger.warning(f"Error building OCC symbol: {e}")
            return None
    
    def get_portfolio_value(self, positions: list) -> Dict[str, float]:
        """Calculate total portfolio value metrics."""
        priced = [p for p in positions if p.market_value is not None]
        
        total_market_value = sum(p.market_value or 0 for p in priced)
        total_cost_basis = sum(p.cost_basis or 0 for p in priced)
        total_pnl = sum(p.unrealized_pnl or 0 for p in priced)
        
        pnl_pct = (total_pnl / total_cost_basis * 100) if total_cost_basis > 0 else 0
        
        return {
            "total_market_value": total_market_value,
            "total_cost_basis": total_cost_basis,
            "total_unrealized_pnl": total_pnl,
            "total_unrealized_pnl_pct": pnl_pct,
            "positions_priced": len(priced),
            "positions_unpriced": len(positions) - len(priced)
        }
