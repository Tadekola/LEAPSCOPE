"""
Public.com Data Provider for LEAPSCOPE.

Uses Public.com's free API for real-time stock quotes.
This is a lightweight provider focused on getting fresh price data.
"""

import requests
import pandas as pd
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from src.providers.base import DataProvider


class PublicProvider(DataProvider):
    """
    Data provider using Public.com API.
    
    Primary use: Fresh real-time stock quotes
    Note: Public.com has limited options data, use Tradier for options.
    """
    
    BASE_URL = "https://api.public.com/v1"
    
    def __init__(self, rate_limit_sleep: float = 0.5):
        self.logger = logging.getLogger("LEAPSCOPE.Provider.Public")
        self.rate_limit_sleep = rate_limit_sleep
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/json",
            "User-Agent": "LEAPSCOPE/1.0"
        })
    
    @property
    def name(self) -> str:
        return "public"
    
    def is_available(self) -> bool:
        """Check if Public.com API is reachable."""
        try:
            # Simple connectivity check
            response = self._session.get(
                f"{self.BASE_URL}/market/status",
                timeout=5
            )
            return response.status_code in (200, 401, 403)  # API is reachable
        except Exception:
            return False
    
    def fetch_quote(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch real-time quote from Public.com.
        
        Returns dict with: last, bid, ask, volume, timestamp
        """
        self.logger.info(f"[{self.name}] Fetching quote for {symbol}")
        
        try:
            response = self._session.get(
                f"{self.BASE_URL}/market/quote/{symbol}",
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                time.sleep(self.rate_limit_sleep)
                return data
            else:
                self.logger.warning(f"[{self.name}] Quote request failed: {response.status_code}")
                return {}
                
        except Exception as e:
            self.logger.error(f"[{self.name}] Error fetching quote: {e}")
            return {}
    
    def fetch_ohlcv(self, symbol: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
        """
        Fetch OHLCV data - Public.com has limited historical data.
        Falls back to empty DataFrame if not available.
        """
        self.logger.info(f"[{self.name}] Fetching OHLCV for {symbol}")
        
        try:
            # Public.com historical endpoint
            period_map = {"1d": 1, "5d": 5, "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730}
            days = period_map.get(period, 365)
            
            response = self._session.get(
                f"{self.BASE_URL}/market/history/{symbol}",
                params={"days": min(days, 365)},  # Public may limit historical data
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data and "history" in data:
                    df = pd.DataFrame(data["history"])
                    if not df.empty:
                        df['date'] = pd.to_datetime(df['date'])
                        df.set_index('date', inplace=True)
                        df.columns = [c.lower() for c in df.columns]
                        time.sleep(self.rate_limit_sleep)
                        return df
            
            return pd.DataFrame()
            
        except Exception as e:
            self.logger.error(f"[{self.name}] Error fetching OHLCV: {e}")
            return pd.DataFrame()
    
    def fetch_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """Public.com has limited fundamentals - return empty."""
        return {}
    
    def fetch_options_chain(self, symbol: str, min_days: int = 300) -> pd.DataFrame:
        """Public.com doesn't have options data - return empty."""
        return pd.DataFrame()
    
    def fetch_earnings_date(self, symbol: str) -> Optional[datetime]:
        """Public.com doesn't have earnings data - return None."""
        return None
    
    def fetch_asset_type(self, symbol: str) -> str:
        """Determine asset type."""
        return "UNKNOWN"


class AlphaVantageProvider(DataProvider):
    """
    Alpha Vantage provider as additional backup.
    Free tier: 25 requests/day
    """
    
    BASE_URL = "https://www.alphavantage.co/query"
    
    def __init__(self, api_key: str = "", rate_limit_sleep: float = 1.0):
        self.logger = logging.getLogger("LEAPSCOPE.Provider.AlphaVantage")
        self.api_key = api_key
        self.rate_limit_sleep = rate_limit_sleep
    
    @property
    def name(self) -> str:
        return "alphavantage"
    
    def is_available(self) -> bool:
        return bool(self.api_key)
    
    def fetch_quote(self, symbol: str) -> Dict[str, Any]:
        """Fetch real-time quote from Alpha Vantage."""
        if not self.api_key:
            return {}
        
        self.logger.info(f"[{self.name}] Fetching quote for {symbol}")
        
        try:
            response = requests.get(
                self.BASE_URL,
                params={
                    "function": "GLOBAL_QUOTE",
                    "symbol": symbol,
                    "apikey": self.api_key
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                quote = data.get("Global Quote", {})
                if quote:
                    return {
                        "last": float(quote.get("05. price", 0)),
                        "open": float(quote.get("02. open", 0)),
                        "high": float(quote.get("03. high", 0)),
                        "low": float(quote.get("04. low", 0)),
                        "volume": int(quote.get("06. volume", 0)),
                        "previous_close": float(quote.get("08. previous close", 0)),
                        "change_pct": quote.get("10. change percent", "0%"),
                        "timestamp": quote.get("07. latest trading day")
                    }
            return {}
            
        except Exception as e:
            self.logger.error(f"[{self.name}] Error fetching quote: {e}")
            return {}
    
    def fetch_ohlcv(self, symbol: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
        """Fetch daily OHLCV from Alpha Vantage."""
        if not self.api_key:
            return pd.DataFrame()
        
        self.logger.info(f"[{self.name}] Fetching OHLCV for {symbol}")
        
        try:
            response = requests.get(
                self.BASE_URL,
                params={
                    "function": "TIME_SERIES_DAILY_ADJUSTED",
                    "symbol": symbol,
                    "outputsize": "full" if period in ("1y", "2y", "5y") else "compact",
                    "apikey": self.api_key
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                time_series = data.get("Time Series (Daily)", {})
                
                if time_series:
                    rows = []
                    for date_str, values in time_series.items():
                        rows.append({
                            "date": date_str,
                            "open": float(values["1. open"]),
                            "high": float(values["2. high"]),
                            "low": float(values["3. low"]),
                            "close": float(values["5. adjusted close"]),  # Split-adjusted
                            "volume": int(values["6. volume"])
                        })
                    
                    df = pd.DataFrame(rows)
                    df['date'] = pd.to_datetime(df['date'])
                    df.set_index('date', inplace=True)
                    df.sort_index(inplace=True)
                    
                    time.sleep(self.rate_limit_sleep)
                    return df
            
            return pd.DataFrame()
            
        except Exception as e:
            self.logger.error(f"[{self.name}] Error fetching OHLCV: {e}")
            return pd.DataFrame()
    
    def fetch_fundamentals(self, symbol: str) -> Dict[str, Any]:
        return {}
    
    def fetch_options_chain(self, symbol: str, min_days: int = 300) -> pd.DataFrame:
        return pd.DataFrame()
    
    def fetch_earnings_date(self, symbol: str) -> Optional[datetime]:
        return None
    
    def fetch_asset_type(self, symbol: str) -> str:
        return "UNKNOWN"
