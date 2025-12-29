import requests
import pandas as pd
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from src.providers.base import DataProvider, DataUnavailableError


class TradierProvider(DataProvider):
    """
    Data provider implementation using Tradier API.
    PRIMARY source for: Live prices, Options chains (with Greeks, IV, OI)
    Requires API token from environment/.env file.
    
    LIVE DATA PROVIDER - No execution capability.
    """
    
    DEFAULT_BASE_URL = "https://api.tradier.com/v1"
    SANDBOX_URL = "https://sandbox.tradier.com/v1"
    
    def __init__(self, api_token: str, base_url: str = None, use_sandbox: bool = False, rate_limit_sleep: float = 0.5):
        self.logger = logging.getLogger("LEAPSCOPE.Provider.Tradier")
        self.api_token = api_token
        
        # Determine base URL priority: explicit base_url > sandbox flag > default
        if base_url:
            self.base_url = base_url.rstrip("/")
            if not self.base_url.endswith("/v1"):
                self.base_url = f"{self.base_url}/v1"
        elif use_sandbox:
            self.base_url = self.SANDBOX_URL
        else:
            self.base_url = self.DEFAULT_BASE_URL
        
        self.rate_limit_sleep = rate_limit_sleep
        self._is_live = "sandbox" not in self.base_url.lower()
        
        self._headers = {
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json"
        }
        
        # Log provider mode (without exposing token)
        mode = "LIVE" if self._is_live else "SANDBOX"
        self.logger.info(f"[{self.name}] Initialized in {mode} mode")
        
        # Known ETF symbols
        self._etf_symbols = {
            "SPY", "QQQ", "IWM", "DIA", "GLD", "SLV", "TLT", "IEF",
            "VTI", "VOO", "VEA", "VWO", "BND", "LQD", "HYG", "XLF",
            "XLE", "XLK", "XLV", "XLI", "XLP", "XLY", "XLU", "XLB",
            "ARKK", "ARKG", "ARKW", "ARKF", "EEM", "EFA", "AGG",
            "USO", "UNG", "UVXY", "SQQQ", "TQQQ", "SPXU", "SPXL"
        }
    
    @property
    def name(self) -> str:
        return "tradier"
    
    def is_available(self) -> bool:
        """Check if Tradier API is available with valid token."""
        if not self.api_token:
            return False
        
        try:
            response = requests.get(
                f"{self.base_url}/user/profile",
                headers=self._headers,
                timeout=10
            )
            return response.status_code == 200
        except Exception:
            return False
    
    def fetch_ohlcv(self, symbol: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
        """
        Fetch OHLCV data from Tradier.
        Note: Tradier's history endpoint has different period semantics.
        """
        self.logger.info(f"[{self.name}] Fetching OHLCV for {symbol}")
        
        # Convert period to start date
        period_map = {
            "2y": 730, "1y": 365, "6mo": 180, "3mo": 90, "1mo": 30
        }
        days = period_map.get(period, 365)
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        try:
            response = requests.get(
                f"{self.base_url}/markets/history",
                headers=self._headers,
                params={
                    "symbol": symbol,
                    "interval": "daily" if interval == "1d" else interval,
                    "start": start_date
                },
                timeout=30
            )
            
            if response.status_code != 200:
                self.logger.warning(f"[{self.name}] OHLCV request failed: {response.status_code}")
                return pd.DataFrame()
            
            data = response.json()
            history = data.get("history", {})
            
            if not history or not history.get("day"):
                return pd.DataFrame()
            
            days_data = history["day"]
            if isinstance(days_data, dict):
                days_data = [days_data]
            
            df = pd.DataFrame(days_data)
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            df.columns = [c.lower() for c in df.columns]
            
            time.sleep(self.rate_limit_sleep)
            return df
            
        except Exception as e:
            self.logger.error(f"[{self.name}] Error fetching OHLCV for {symbol}: {e}")
            return pd.DataFrame()
    
    def fetch_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch fundamental data from Tradier.
        Note: Tradier has limited fundamentals; prefer yfinance for this.
        """
        self.logger.info(f"[{self.name}] Fetching fundamentals for {symbol}")
        
        try:
            response = requests.get(
                f"{self.base_url}/markets/fundamentals/company",
                headers=self._headers,
                params={"symbols": symbol},
                timeout=30
            )
            
            if response.status_code != 200:
                return {}
            
            data = response.json()
            items = data.get("items", [])
            
            if not items:
                return {}
            
            company_data = items[0] if isinstance(items, list) else items
            
            # Add asset type detection
            company_data['_asset_type'] = self._detect_asset_type(symbol)
            
            time.sleep(self.rate_limit_sleep)
            return company_data
            
        except Exception as e:
            self.logger.error(f"[{self.name}] Error fetching fundamentals for {symbol}: {e}")
            return {}
    
    def fetch_options_chain(self, symbol: str, min_days: int = 300) -> pd.DataFrame:
        """
        Fetch LEAPS options chain from Tradier with full Greeks.
        This is Tradier's PRIMARY strength - complete options data.
        """
        self.logger.info(f"[{self.name}] Fetching options chain for {symbol} (min_days={min_days})")
        
        try:
            # First, get available expirations
            exp_response = requests.get(
                f"{self.base_url}/markets/options/expirations",
                headers=self._headers,
                params={"symbol": symbol, "includeAllRoots": "true"},
                timeout=30
            )
            
            if exp_response.status_code != 200:
                self.logger.warning(f"[{self.name}] Failed to fetch expirations: {exp_response.status_code}")
                return pd.DataFrame()
            
            exp_data = exp_response.json()
            expirations = exp_data.get("expirations", {}).get("date", [])
            
            if not expirations:
                return pd.DataFrame()
            
            if isinstance(expirations, str):
                expirations = [expirations]
            
            # Filter for LEAPS
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
            
            # Fetch chains for each expiration
            all_options = []
            
            for exp in leaps_expirations:
                try:
                    chain_response = requests.get(
                        f"{self.base_url}/markets/options/chains",
                        headers=self._headers,
                        params={
                            "symbol": symbol,
                            "expiration": exp,
                            "greeks": "true"  # Include Greeks!
                        },
                        timeout=30
                    )
                    
                    if chain_response.status_code != 200:
                        continue
                    
                    chain_data = chain_response.json()
                    options = chain_data.get("options", {}).get("option", [])
                    
                    if not options:
                        continue
                    
                    if isinstance(options, dict):
                        options = [options]
                    
                    # Filter for calls only and add days to expiry
                    for opt in options:
                        if opt.get("option_type") == "call":
                            opt["days_to_expiry"] = (datetime.strptime(exp, "%Y-%m-%d") - today).days
                            all_options.append(opt)
                    
                    time.sleep(self.rate_limit_sleep)
                    
                except Exception as e:
                    self.logger.warning(f"[{self.name}] Error fetching chain for {exp}: {e}")
                    continue
            
            if not all_options:
                return pd.DataFrame()
            
            df = pd.DataFrame(all_options)
            
            # Normalize column names to match expected format
            column_mapping = {
                "symbol": "contractSymbol",
                "strike": "strike",
                "expiration_date": "expiration",
                "bid": "bid",
                "ask": "ask",
                "open_interest": "openInterest",
                "volume": "volume",
                "greeks": "greeks"  # Tradier includes greeks as nested object
            }
            
            # Extract IV from greeks if present
            if "greeks" in df.columns:
                df["impliedVolatility"] = df["greeks"].apply(
                    lambda x: x.get("mid_iv") if isinstance(x, dict) else None
                )
                df["delta"] = df["greeks"].apply(
                    lambda x: x.get("delta") if isinstance(x, dict) else None
                )
                df["gamma"] = df["greeks"].apply(
                    lambda x: x.get("gamma") if isinstance(x, dict) else None
                )
                df["theta"] = df["greeks"].apply(
                    lambda x: x.get("theta") if isinstance(x, dict) else None
                )
                df["vega"] = df["greeks"].apply(
                    lambda x: x.get("vega") if isinstance(x, dict) else None
                )
            
            # Rename columns
            rename_map = {
                "symbol": "contractSymbol",
                "expiration_date": "expiration",
                "open_interest": "openInterest"
            }
            df = df.rename(columns=rename_map)
            
            return df
            
        except Exception as e:
            self.logger.error(f"[{self.name}] Error fetching options for {symbol}: {e}")
            return pd.DataFrame()
    
    def fetch_earnings_date(self, symbol: str) -> Optional[datetime]:
        """
        Fetch earnings date from Tradier.
        Note: Tradier may have limited earnings data; yfinance preferred.
        """
        self.logger.info(f"[{self.name}] Fetching earnings date for {symbol}")
        
        try:
            response = requests.get(
                f"{self.base_url}/markets/fundamentals/calendars",
                headers=self._headers,
                params={"symbols": symbol},
                timeout=30
            )
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            items = data.get("items", [])
            
            if not items:
                return None
            
            # Look for earnings events
            for item in items:
                results = item.get("results", [])
                for result in results:
                    tables = result.get("tables", {})
                    corporate_calendars = tables.get("corporate_calendars", [])
                    
                    for event in corporate_calendars:
                        if event.get("event") == "Earnings":
                            event_date = event.get("begin_date_time")
                            if event_date:
                                return pd.to_datetime(event_date)
            
            return None
            
        except Exception as e:
            self.logger.warning(f"[{self.name}] Error fetching earnings date for {symbol}: {e}")
            return None
    
    def fetch_asset_type(self, symbol: str) -> str:
        """Determine if symbol is STOCK or ETF."""
        return self._detect_asset_type(symbol)
    
    def _detect_asset_type(self, symbol: str) -> str:
        """Detect asset type from known ETF list."""
        if symbol.upper() in self._etf_symbols:
            return "ETF"
        
        # Could also check Tradier's securities endpoint
        # but for MVP, use the known list
        return "STOCK"
    
    def fetch_quote(self, symbol: str) -> Dict[str, Any]:
        """Fetch real-time quote from Tradier."""
        self.logger.info(f"[{self.name}] Fetching LIVE quote for {symbol}")
        
        try:
            response = requests.get(
                f"{self.base_url}/markets/quotes",
                headers=self._headers,
                params={"symbols": symbol},
                timeout=10
            )
            
            if response.status_code != 200:
                self.logger.warning(f"[{self.name}] Quote request failed: {response.status_code}")
                return {}
            
            data = response.json()
            quotes = data.get("quotes", {}).get("quote", {})
            
            time.sleep(self.rate_limit_sleep)
            return quotes if isinstance(quotes, dict) else {}
            
        except Exception as e:
            self.logger.error(f"[{self.name}] Error fetching quote for {symbol}: {e}")
            return {}
    
    def fetch_underlying_price(self, symbol: str) -> Optional[float]:
        """
        Fetch LIVE underlying price from Tradier.
        
        Returns:
            float: Last traded price if available
            None: If unavailable (DO NOT guess)
        """
        quote = self.fetch_quote(symbol)
        
        if not quote:
            self.logger.warning(f"[{self.name}] No quote data for {symbol}")
            return None
        
        # Try last price first, then bid/ask midpoint
        last_price = quote.get("last")
        if last_price is not None and last_price > 0:
            self.logger.info(f"[{self.name}] LIVE price for {symbol}: ${last_price:.2f}")
            return float(last_price)
        
        # Fallback to bid/ask midpoint
        bid = quote.get("bid")
        ask = quote.get("ask")
        if bid and ask and bid > 0 and ask > 0:
            mid = (bid + ask) / 2
            self.logger.info(f"[{self.name}] LIVE mid price for {symbol}: ${mid:.2f}")
            return float(mid)
        
        return None
    
    def fetch_option_quote(self, option_symbol: str) -> Dict[str, Any]:
        """
        Fetch LIVE quote for a specific option contract.
        
        Args:
            option_symbol: OCC-format option symbol (e.g., AAPL251219C00200000)
            
        Returns:
            Dict with bid, ask, last, greeks, iv
        """
        self.logger.info(f"[{self.name}] Fetching LIVE option quote for {option_symbol}")
        
        try:
            response = requests.get(
                f"{self.base_url}/markets/quotes",
                headers=self._headers,
                params={"symbols": option_symbol, "greeks": "true"},
                timeout=10
            )
            
            if response.status_code != 200:
                self.logger.warning(f"[{self.name}] Option quote request failed: {response.status_code}")
                return {}
            
            data = response.json()
            quote = data.get("quotes", {}).get("quote", {})
            
            if not quote or isinstance(quote, list):
                return {}
            
            # Extract and structure the data
            result = {
                "bid": quote.get("bid"),
                "ask": quote.get("ask"),
                "last": quote.get("last"),
                "volume": quote.get("volume"),
                "open_interest": quote.get("open_interest"),
                "source": "tradier_live"
            }
            
            # Extract Greeks if present
            greeks = quote.get("greeks", {})
            if greeks:
                result["delta"] = greeks.get("delta")
                result["gamma"] = greeks.get("gamma")
                result["theta"] = greeks.get("theta")
                result["vega"] = greeks.get("vega")
                result["iv"] = greeks.get("mid_iv") or greeks.get("smv_vol")
            
            time.sleep(self.rate_limit_sleep)
            return result
            
        except Exception as e:
            self.logger.error(f"[{self.name}] Error fetching option quote: {e}")
            return {}
    
    @property
    def is_live(self) -> bool:
        """Check if provider is using live (non-sandbox) data."""
        return self._is_live
