import yfinance as yf
import pandas as pd
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from src.providers.base import DataProvider, DataUnavailableError


class YFinanceProvider(DataProvider):
    """
    Data provider implementation using yfinance.
    Primary source for: OHLCV, Fundamentals, Earnings dates
    Secondary/fallback for: Options chains
    """
    
    def __init__(self, rate_limit_sleep: float = 1.0):
        self.logger = logging.getLogger("LEAPSCOPE.Provider.YFinance")
        self.rate_limit_sleep = rate_limit_sleep
        
        # Known ETF symbols for classification
        self._etf_symbols = {
            "SPY", "QQQ", "IWM", "DIA", "GLD", "SLV", "TLT", "IEF", 
            "VTI", "VOO", "VEA", "VWO", "BND", "LQD", "HYG", "XLF",
            "XLE", "XLK", "XLV", "XLI", "XLP", "XLY", "XLU", "XLB",
            "ARKK", "ARKG", "ARKW", "ARKF", "EEM", "EFA", "AGG",
            "USO", "UNG", "UVXY", "SQQQ", "TQQQ", "SPXU", "SPXL"
        }
    
    @property
    def name(self) -> str:
        return "yfinance"
    
    def fetch_ohlcv(self, symbol: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
        """Fetch OHLCV data from yfinance."""
        self.logger.info(f"[{self.name}] Fetching OHLCV for {symbol}")
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)
            
            if df.empty:
                self.logger.warning(f"[{self.name}] No OHLCV data for {symbol}")
                return pd.DataFrame()
            
            # Normalize columns to lowercase
            df.columns = [c.lower() for c in df.columns]
            if df.index.name == 'Date':
                df.index.name = 'date'
            
            time.sleep(self.rate_limit_sleep)
            return df
            
        except Exception as e:
            self.logger.error(f"[{self.name}] Error fetching OHLCV for {symbol}: {e}")
            return pd.DataFrame()
    
    def fetch_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """Fetch fundamental data from yfinance."""
        self.logger.info(f"[{self.name}] Fetching fundamentals for {symbol}")
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            if not info:
                return {}
            
            # Add asset type detection
            info['_asset_type'] = self._detect_asset_type(symbol, info)
            
            time.sleep(self.rate_limit_sleep)
            return info
            
        except Exception as e:
            self.logger.error(f"[{self.name}] Error fetching fundamentals for {symbol}: {e}")
            return {}
    
    def fetch_options_chain(self, symbol: str, min_days: int = 300) -> pd.DataFrame:
        """Fetch LEAPS options chain from yfinance."""
        self.logger.info(f"[{self.name}] Fetching options chain for {symbol} (min_days={min_days})")
        
        try:
            ticker = yf.Ticker(symbol)
            expirations = list(ticker.options)
            
            if not expirations:
                self.logger.warning(f"[{self.name}] No option expirations for {symbol}")
                return pd.DataFrame()
            
            # Filter for LEAPS expirations
            today = datetime.now()
            leaps_expirations = []
            
            for exp_str in expirations:
                try:
                    exp_date = datetime.strptime(exp_str, "%Y-%m-%d")
                    days_to_exp = (exp_date - today).days
                    if days_to_exp >= min_days:
                        leaps_expirations.append(exp_str)
                except ValueError:
                    continue
            
            if not leaps_expirations:
                self.logger.info(f"[{self.name}] No LEAPS expirations found for {symbol}")
                return pd.DataFrame()
            
            # Fetch chains for each LEAPS expiration
            all_calls = []
            for exp in leaps_expirations:
                try:
                    chain = ticker.option_chain(exp)
                    calls = chain.calls
                    
                    if not calls.empty:
                        calls = calls.copy()
                        calls['expiration'] = exp
                        calls['days_to_expiry'] = (datetime.strptime(exp, "%Y-%m-%d") - today).days
                        all_calls.append(calls)
                    
                    time.sleep(self.rate_limit_sleep)
                    
                except Exception as e:
                    self.logger.warning(f"[{self.name}] Error fetching chain for {exp}: {e}")
                    continue
            
            if not all_calls:
                return pd.DataFrame()
            
            return pd.concat(all_calls, ignore_index=True)
            
        except Exception as e:
            self.logger.error(f"[{self.name}] Error fetching options for {symbol}: {e}")
            return pd.DataFrame()
    
    def fetch_earnings_date(self, symbol: str) -> Optional[datetime]:
        """Fetch next earnings date from yfinance."""
        self.logger.info(f"[{self.name}] Fetching earnings date for {symbol}")
        try:
            ticker = yf.Ticker(symbol)
            
            # Try calendar first
            try:
                calendar = ticker.calendar
                if calendar is not None:
                    # calendar can be a dict or DataFrame depending on yfinance version
                    if isinstance(calendar, dict):
                        earnings_date = calendar.get('Earnings Date')
                        if earnings_date:
                            if isinstance(earnings_date, list) and len(earnings_date) > 0:
                                return pd.to_datetime(earnings_date[0])
                            return pd.to_datetime(earnings_date)
                    elif isinstance(calendar, pd.DataFrame) and not calendar.empty:
                        if 'Earnings Date' in calendar.columns:
                            return pd.to_datetime(calendar['Earnings Date'].iloc[0])
            except Exception:
                pass
            
            # Fallback: try earnings_dates attribute
            try:
                earnings_dates = ticker.earnings_dates
                if earnings_dates is not None and not earnings_dates.empty:
                    # Get future dates only
                    future_dates = earnings_dates[earnings_dates.index > datetime.now()]
                    if not future_dates.empty:
                        return future_dates.index[0].to_pydatetime()
            except Exception:
                pass
            
            self.logger.info(f"[{self.name}] No earnings date found for {symbol}")
            return None
            
        except Exception as e:
            self.logger.warning(f"[{self.name}] Error fetching earnings date for {symbol}: {e}")
            return None
    
    def fetch_asset_type(self, symbol: str) -> str:
        """Determine if symbol is STOCK or ETF."""
        # Check known ETF list first
        if symbol.upper() in self._etf_symbols:
            return "ETF"
        
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            quote_type = info.get('quoteType', '').upper()
            
            if quote_type == 'ETF':
                return "ETF"
            elif quote_type in ('EQUITY', 'STOCK'):
                return "STOCK"
            else:
                return "UNKNOWN"
                
        except Exception:
            return "UNKNOWN"
    
    def _detect_asset_type(self, symbol: str, info: Dict[str, Any]) -> str:
        """Detect asset type from symbol and info dict."""
        # Check known ETF list
        if symbol.upper() in self._etf_symbols:
            return "ETF"
        
        # Check quoteType in info
        quote_type = info.get('quoteType', '').upper()
        if quote_type == 'ETF':
            return "ETF"
        elif quote_type in ('EQUITY', 'STOCK'):
            return "STOCK"
        
        return "UNKNOWN"
    
    def is_available(self) -> bool:
        """yfinance is always available (no API key required)."""
        return True
