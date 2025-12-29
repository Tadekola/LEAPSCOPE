from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime
import pandas as pd


class DataProvider(ABC):
    """
    Abstract base class for all data providers.
    Defines the interface that all providers must implement.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the provider name for logging purposes."""
        pass
    
    @abstractmethod
    def fetch_ohlcv(self, symbol: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
        """
        Fetch OHLCV (Open, High, Low, Close, Volume) data.
        
        Args:
            symbol: Ticker symbol
            period: Time period (e.g., "2y", "1y", "6mo")
            interval: Data interval (e.g., "1d", "1h")
            
        Returns:
            DataFrame with columns: open, high, low, close, volume (lowercase)
            Index should be datetime
        """
        pass
    
    @abstractmethod
    def fetch_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch fundamental data for a symbol.
        
        Args:
            symbol: Ticker symbol
            
        Returns:
            Dictionary containing fundamental metrics:
            - revenueGrowth, earningsGrowth
            - profitMargins, returnOnEquity
            - debtToEquity, currentRatio
            - operatingCashflow, beta
            - quoteType (for ETF detection)
        """
        pass
    
    @abstractmethod
    def fetch_options_chain(self, symbol: str, min_days: int = 300) -> pd.DataFrame:
        """
        Fetch options chain data for LEAPS (long-dated options).
        
        Args:
            symbol: Ticker symbol
            min_days: Minimum days to expiration for LEAPS
            
        Returns:
            DataFrame with columns:
            - contractSymbol, strike, expiration
            - bid, ask, openInterest, volume
            - impliedVolatility
            - days_to_expiry
        """
        pass
    
    @abstractmethod
    def fetch_earnings_date(self, symbol: str) -> Optional[datetime]:
        """
        Fetch the next earnings date for a symbol.
        
        Args:
            symbol: Ticker symbol
            
        Returns:
            Next earnings date as datetime, or None if unavailable
        """
        pass
    
    def fetch_asset_type(self, symbol: str) -> str:
        """
        Determine if the symbol is a STOCK or ETF.
        Default implementation returns UNKNOWN.
        
        Args:
            symbol: Ticker symbol
            
        Returns:
            One of: "STOCK", "ETF", "UNKNOWN"
        """
        return "UNKNOWN"
    
    def is_available(self) -> bool:
        """
        Check if the provider is available and configured.
        
        Returns:
            True if the provider can be used, False otherwise
        """
        return True


class ProviderError(Exception):
    """Exception raised when a provider encounters an error."""
    pass


class DataUnavailableError(ProviderError):
    """Exception raised when requested data is not available."""
    pass
