import pandas as pd
import numpy as np
import ta
import logging
from datetime import datetime
from typing import Dict, Any, Literal

class TechnicalAnalyzer:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger("LEAPSCOPE.TA")
        
        # Load config thresholds
        self.sma_fast_len = config.get("sma_fast", 50)
        self.sma_slow_len = config.get("sma_slow", 200)
        self.rsi_period = config.get("rsi_period", 14)
        self.rsi_ob = config.get("rsi_overbought", 70)
        self.rsi_os = config.get("rsi_oversold", 30)
        self.atr_period = config.get("atr_period", 14)
        self.bb_period = config.get("bollinger_period", 20)
        self.bb_std = config.get("bollinger_std", 2.0)
        self.hv_window = config.get("hv_window", 20) # 20 days HV

    def analyze(self, symbol: str, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Perform technical analysis on the dataframe.
        Expects df to have columns: open, high, low, close, volume (lowercase).
        """
        if df.empty or len(df) < self.sma_slow_len:
            self.logger.warning(f"Insufficient data for TA on {symbol}. Rows: {len(df)}")
            return {"status": "INSUFFICIENT_DATA"}

        # Ensure we are working on a copy to avoid SettingWithCopy warnings
        df = df.copy()

        # Calculate Indicators using 'ta' library
        
        # SMA
        df[f'SMA_{self.sma_fast_len}'] = ta.trend.SMAIndicator(close=df['close'], window=self.sma_fast_len).sma_indicator()
        df[f'SMA_{self.sma_slow_len}'] = ta.trend.SMAIndicator(close=df['close'], window=self.sma_slow_len).sma_indicator()
        
        # RSI
        df['RSI'] = ta.momentum.RSIIndicator(close=df['close'], window=self.rsi_period).rsi()
        
        # Bollinger Bands
        bb_indicator = ta.volatility.BollingerBands(close=df['close'], window=self.bb_period, window_dev=self.bb_std)
        df['BB_UPPER'] = bb_indicator.bollinger_hband()
        df['BB_LOWER'] = bb_indicator.bollinger_lband()
        df['BB_MID'] = bb_indicator.bollinger_mavg()

        # ATR
        df['ATR'] = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=self.atr_period).average_true_range()

        # MACD (Default 12, 26, 9)
        macd = ta.trend.MACD(close=df['close'])
        df['MACD'] = macd.macd()
        df['MACD_SIGNAL'] = macd.macd_signal()
        df['MACD_HIST'] = macd.macd_diff()

        # Historical Volatility (Annualized)
        # Log returns
        df['log_ret'] = np.log(df['close'] / df['close'].shift(1))
        # Rolling std dev * sqrt(252)
        df['HV'] = df['log_ret'].rolling(window=self.hv_window).std() * np.sqrt(252)

        # Get latest values
        latest = df.iloc[-1]
        
        # Determine Trend
        trend = self._determine_trend(latest)
        
        # Construct Report
        # Handle NaN values for JSON serialization (convert to None)
        def clean(val):
            return None if pd.isna(val) else float(val)

        report = {
            "symbol": symbol,
            "date": str(latest.name) if hasattr(latest, 'name') else datetime.utcnow().isoformat(),
            "price": clean(latest['close']),
            "trend": trend,
            "indicators": {
                "sma_fast": clean(latest.get(f'SMA_{self.sma_fast_len}')),
                "sma_slow": clean(latest.get(f'SMA_{self.sma_slow_len}')),
                "rsi": clean(latest.get('RSI')),
                "atr": clean(latest.get('ATR')),
                "macd": clean(latest.get('MACD')),
                "macd_signal": clean(latest.get('MACD_SIGNAL')),
                "bb_upper": clean(latest.get('BB_UPPER')),
                "bb_lower": clean(latest.get('BB_LOWER')),
                "hv": clean(latest.get('HV')),
            },
            "signals": {
                "golden_cross": self._check_golden_cross(df),
                "death_cross": self._check_death_cross(df),
                "rsi_state": self._get_rsi_state(latest.get('RSI', 50)),
            }
        }
        
        return report

    def _determine_trend(self, row: pd.Series) -> Literal["BULLISH", "BEARISH", "NEUTRAL"]:
        sma_fast = row.get(f'SMA_{self.sma_fast_len}')
        sma_slow = row.get(f'SMA_{self.sma_slow_len}')
        price = row['close']
        
        if pd.isna(sma_fast) or pd.isna(sma_slow):
            return "UNKNOWN"
            
        # Simple Logic: Price > SMA50 > SMA200 -> Bullish
        if price > sma_fast > sma_slow:
            return "BULLISH"
        # Price < SMA50 < SMA200 -> Bearish
        elif price < sma_fast < sma_slow:
            return "BEARISH"
        # Otherwise Neutral/Choppy
        else:
            return "NEUTRAL"

    def _get_rsi_state(self, rsi: float) -> str:
        if pd.isna(rsi): return "UNKNOWN"
        if rsi > self.rsi_ob: return "OVERBOUGHT"
        if rsi < self.rsi_os: return "OVERSOLD"
        return "NEUTRAL"

    def _check_golden_cross(self, df: pd.DataFrame) -> bool:
        """SMA 50 crosses above SMA 200 recently"""
        if len(df) < 2: return False
        
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        fast_col = f'SMA_{self.sma_fast_len}'
        slow_col = f'SMA_{self.sma_slow_len}'
        
        if pd.isna(curr[fast_col]) or pd.isna(prev[fast_col]): return False
        if pd.isna(curr[slow_col]) or pd.isna(prev[slow_col]): return False

        cross_above = (prev[fast_col] <= prev[slow_col]) and (curr[fast_col] > curr[slow_col])
        return bool(cross_above)

    def _check_death_cross(self, df: pd.DataFrame) -> bool:
        """SMA 50 crosses below SMA 200 recently"""
        if len(df) < 2: return False
        
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        fast_col = f'SMA_{self.sma_fast_len}'
        slow_col = f'SMA_{self.sma_slow_len}'
        
        if pd.isna(curr[fast_col]) or pd.isna(prev[fast_col]): return False
        if pd.isna(curr[slow_col]) or pd.isna(prev[slow_col]): return False
        
        cross_below = (prev[fast_col] >= prev[slow_col]) and (curr[fast_col] < curr[slow_col])
        return bool(cross_below)
