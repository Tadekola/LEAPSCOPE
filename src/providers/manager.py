import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import pandas as pd
import requests

from src.providers.base import DataProvider
from src.providers.yfinance_provider import YFinanceProvider
from src.providers.tradier_provider import TradierProvider


class ProviderManager:
    """
    Manages multiple data providers and handles provider selection.
    Implements fallback logic when primary provider fails.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger("LEAPSCOPE.ProviderManager")
        
        # Provider configuration
        provider_config = config.get("providers", {})
        self.priority_order = provider_config.get("priority", ["tradier", "yfinance"])
        
        # Initialize providers
        self._providers: Dict[str, DataProvider] = {}
        self._init_providers(provider_config)
        
        # Log provider status
        self._log_provider_status()
    
    def _init_providers(self, config: Dict[str, Any]):
        """Initialize all configured providers."""
        
        # Always initialize yfinance (no config needed)
        yfinance_config = config.get("yfinance", {})
        self._providers["yfinance"] = YFinanceProvider(
            rate_limit_sleep=yfinance_config.get("rate_limit_sleep", 1.0)
        )
        
        # Initialize Tradier if token provided (from .env via config)
        tradier_config = config.get("tradier", {})
        tradier_token = tradier_config.get("api_token", "")
        tradier_base_url = tradier_config.get("base_url", "")
        
        if tradier_token:
            self._providers["tradier"] = TradierProvider(
                api_token=tradier_token,
                base_url=tradier_base_url,
                use_sandbox=tradier_config.get("use_sandbox", False),
                rate_limit_sleep=tradier_config.get("rate_limit_sleep", 0.5)
            )
            self._tradier_live = True
        else:
            self.logger.warning("Tradier API token not configured - Tradier provider disabled")
            self._tradier_live = False
    
    def _log_provider_status(self):
        """Log the status of all providers."""
        for name, provider in self._providers.items():
            available = provider.is_available()
            status = "AVAILABLE" if available else "UNAVAILABLE"
            self.logger.info(f"Provider [{name}]: {status}")
    
    def _get_provider(self, provider_name: str) -> Optional[DataProvider]:
        """Get a specific provider by name."""
        return self._providers.get(provider_name)
    
    def _get_providers_by_priority(self, preferred_providers: List[str] = None) -> List[DataProvider]:
        """Get providers in priority order, optionally filtered."""
        priority = preferred_providers or self.priority_order
        providers = []
        
        for name in priority:
            provider = self._providers.get(name)
            if provider and provider.is_available():
                providers.append(provider)
        
        return providers
    
    def fetch_ohlcv(self, symbol: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
        """
        Fetch OHLCV data with fallback.
        Prefers yfinance for historical data (more complete).
        """
        # For OHLCV, yfinance is typically better
        preferred = ["yfinance", "tradier"]
        
        for provider in self._get_providers_by_priority(preferred):
            try:
                df = provider.fetch_ohlcv(symbol, period, interval)
                if not df.empty:
                    self.logger.debug(f"OHLCV for {symbol} fetched via [{provider.name}]")
                    return df
            except Exception as e:
                self.logger.warning(f"Provider [{provider.name}] failed for OHLCV: {e}")
                continue
        
        self.logger.error(f"All providers failed to fetch OHLCV for {symbol}")
        return pd.DataFrame()
    
    def fetch_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch fundamentals with fallback.
        Prefers yfinance for fundamentals (more complete).
        """
        # yfinance has better fundamentals data
        preferred = ["yfinance", "tradier"]
        
        for provider in self._get_providers_by_priority(preferred):
            try:
                data = provider.fetch_fundamentals(symbol)
                if data:
                    self.logger.debug(f"Fundamentals for {symbol} fetched via [{provider.name}]")
                    return data
            except Exception as e:
                self.logger.warning(f"Provider [{provider.name}] failed for fundamentals: {e}")
                continue
        
        self.logger.warning(f"All providers failed to fetch fundamentals for {symbol}")
        return {}
    
    def fetch_options_chain(self, symbol: str, min_days: int = 300) -> pd.DataFrame:
        """
        Fetch options chain with fallback.
        Prefers Tradier for options (better Greeks, IV data).
        """
        # Tradier is PRIMARY for options
        preferred = ["tradier", "yfinance"]
        
        for provider in self._get_providers_by_priority(preferred):
            try:
                df = provider.fetch_options_chain(symbol, min_days)
                if not df.empty:
                    self.logger.info(f"Options chain for {symbol} fetched via [{provider.name}]")
                    return df
            except Exception as e:
                self.logger.warning(f"Provider [{provider.name}] failed for options: {e}")
                continue
        
        self.logger.warning(f"All providers failed to fetch options for {symbol}")
        return pd.DataFrame()
    
    def fetch_earnings_date(self, symbol: str) -> Optional[datetime]:
        """
        Fetch earnings date with fallback.
        Prefers yfinance for earnings (more reliable).
        """
        preferred = ["yfinance", "tradier"]
        
        for provider in self._get_providers_by_priority(preferred):
            try:
                date = provider.fetch_earnings_date(symbol)
                if date:
                    self.logger.debug(f"Earnings date for {symbol} fetched via [{provider.name}]")
                    return date
            except Exception as e:
                self.logger.warning(f"Provider [{provider.name}] failed for earnings date: {e}")
                continue
        
        self.logger.info(f"No earnings date found for {symbol} (may be ETF or unavailable)")
        return None
    
    def fetch_asset_type(self, symbol: str) -> str:
        """
        Determine if symbol is STOCK or ETF.
        Uses first available provider.
        """
        for provider in self._get_providers_by_priority():
            try:
                asset_type = provider.fetch_asset_type(symbol)
                if asset_type != "UNKNOWN":
                    return asset_type
            except Exception:
                continue
        
        return "UNKNOWN"
    
    def get_available_providers(self) -> List[str]:
        """Return list of available provider names."""
        return [name for name, p in self._providers.items() if p.is_available()]
    
    def fetch_live_price(self, symbol: str) -> tuple:
        """
        Fetch LIVE underlying price using hybrid multi-source approach.
        Returns (price, source) tuple.
        
        Priority:
        1. Tradier (live API)
        2. Yahoo Finance direct quote API
        3. yfinance OHLCV fallback
        """
        prices_found = []
        
        # 1. Try Tradier first for live data
        tradier = self._providers.get("tradier")
        if tradier and tradier.is_available():
            try:
                price = tradier.fetch_underlying_price(symbol)
                if price is not None and price > 0:
                    self.logger.info(f"LIVE price for {symbol}: ${price:.2f} [tradier]")
                    prices_found.append((price, "tradier_live"))
            except Exception as e:
                self.logger.warning(f"Tradier price fetch failed: {e}")
        
        # 2. Try Yahoo Finance direct quote API (faster than OHLCV)
        try:
            yf_price = self._fetch_yahoo_quote_direct(symbol)
            if yf_price is not None and yf_price > 0:
                self.logger.info(f"Yahoo quote for {symbol}: ${yf_price:.2f}")
                prices_found.append((yf_price, "yahoo_quote"))
        except Exception as e:
            self.logger.warning(f"Yahoo direct quote failed: {e}")
        
        # 3. Fallback to yfinance OHLCV
        if not prices_found:
            yf_provider = self._providers.get("yfinance")
            if yf_provider:
                try:
                    df = yf_provider.fetch_ohlcv(symbol, period="5d", interval="1d")
                    if not df.empty:
                        price = float(df["close"].iloc[-1])
                        self.logger.info(f"OHLCV fallback price for {symbol}: ${price:.2f}")
                        prices_found.append((price, "yfinance_ohlcv"))
                except Exception as e:
                    self.logger.warning(f"yfinance OHLCV fallback failed: {e}")
        
        # Return best price found
        if prices_found:
            # If we have multiple sources, log them for comparison
            if len(prices_found) > 1:
                self.logger.info(f"Price sources for {symbol}: {prices_found}")
            return prices_found[0]  # Return first (highest priority)
        
        return (None, "unavailable")
    
    def _fetch_yahoo_quote_direct(self, symbol: str) -> Optional[float]:
        """
        Fetch real-time quote directly from Yahoo Finance API.
        This is faster and more current than OHLCV data.
        """
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            params = {
                "interval": "1d",
                "range": "1d"
            }
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                result = data.get("chart", {}).get("result", [])
                if result:
                    meta = result[0].get("meta", {})
                    # regularMarketPrice is the most current price
                    price = meta.get("regularMarketPrice")
                    if price:
                        return float(price)
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Yahoo direct quote error: {e}")
            return None
    
    def fetch_live_option_quote(self, option_symbol: str) -> Dict[str, Any]:
        """
        Fetch LIVE option quote with Greeks.
        
        Args:
            option_symbol: OCC-format option symbol
            
        Returns:
            Dict with bid, ask, last, greeks, iv, source
        """
        # Try Tradier first (primary for options)
        tradier = self._providers.get("tradier")
        if tradier and tradier.is_available():
            quote = tradier.fetch_option_quote(option_symbol)
            if quote and quote.get("bid") is not None:
                quote["source"] = "tradier_live"
                self.logger.info(f"LIVE option quote for {option_symbol} [tradier]")
                return quote
        
        # No fallback for live option quotes - must use Tradier
        self.logger.warning(f"No live option quote available for {option_symbol}")
        return {"source": "unavailable"}
    
    def is_live_data_available(self) -> bool:
        """Check if live Tradier data is available."""
        tradier = self._providers.get("tradier")
        return tradier is not None and tradier.is_available()
    
    def get_data_source_status(self) -> Dict[str, Any]:
        """Get status of all data sources for dashboard display."""
        tradier = self._providers.get("tradier")
        yfinance = self._providers.get("yfinance")
        
        tradier_live = False
        tradier_available = False
        if tradier:
            tradier_available = tradier.is_available()
            tradier_live = tradier_available and getattr(tradier, '_is_live', False)
        
        return {
            "tradier": {
                "available": tradier_available,
                "live": tradier_live,
                "mode": "LIVE" if tradier_live else "SANDBOX" if tradier_available else "DISABLED"
            },
            "yfinance": {
                "available": yfinance.is_available() if yfinance else False,
                "mode": "FALLBACK"
            },
            "primary_source": "tradier" if tradier_live else "yfinance",
            "live_data": tradier_live
        }
