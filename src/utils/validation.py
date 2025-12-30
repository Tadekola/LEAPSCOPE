"""
Data Validation Module for LEAPSCOPE.

Provides data freshness validation, market hours checking, and risk warnings.
Critical for ensuring decisions are not made on stale or invalid data.
"""

import logging
from datetime import datetime, time, timedelta
from typing import Optional, Tuple
from enum import Enum
import pandas as pd


class DataFreshnessError(Exception):
    """Raised when data is too stale for decision-making."""
    pass


class MarketStatus(str, Enum):
    """US market status."""
    OPEN = "OPEN"
    PRE_MARKET = "PRE_MARKET"
    AFTER_HOURS = "AFTER_HOURS"
    CLOSED = "CLOSED"
    WEEKEND = "WEEKEND"
    HOLIDAY = "HOLIDAY"


# US Market Hours (Eastern Time)
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)
PRE_MARKET_OPEN = time(4, 0)
AFTER_HOURS_CLOSE = time(20, 0)

# Known US market holidays (2024-2025) - simplified list
US_MARKET_HOLIDAYS = [
    "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27",
    "2024-06-19", "2024-07-04", "2024-09-02", "2024-11-28", "2024-12-25",
    "2025-01-01", "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26",
    "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25",
]


class DataValidator:
    """
    Validates data freshness and market conditions.
    
    Critical safety component to prevent decisions on stale data.
    """
    
    def __init__(self, max_data_age_minutes: int = 15, strict_mode: bool = True):
        """
        Args:
            max_data_age_minutes: Maximum acceptable age for price data
            strict_mode: If True, raise exceptions; if False, return warnings
        """
        self.max_data_age_minutes = max_data_age_minutes
        self.strict_mode = strict_mode
        self.logger = logging.getLogger("LEAPSCOPE.DataValidator")
    
    def validate_price_freshness(
        self, 
        data_timestamp: Optional[datetime], 
        symbol: str = "",
        context: str = "price"
    ) -> Tuple[bool, str]:
        """
        Validate that price data is fresh enough for decision-making.
        
        Args:
            data_timestamp: When the data was generated/fetched
            symbol: Symbol for logging
            context: What type of data (price, options, etc.)
            
        Returns:
            Tuple of (is_valid, warning_message)
            
        Raises:
            DataFreshnessError: If strict_mode and data is stale
        """
        if data_timestamp is None:
            msg = f"[{symbol}] {context} data has no timestamp - freshness UNKNOWN"
            self.logger.warning(msg)
            if self.strict_mode:
                raise DataFreshnessError(msg)
            return False, msg
        
        now = datetime.now()
        age = now - data_timestamp
        age_minutes = age.total_seconds() / 60
        
        if age_minutes > self.max_data_age_minutes:
            msg = (
                f"[{symbol}] {context} data is {age_minutes:.0f} minutes old "
                f"(max allowed: {self.max_data_age_minutes}). "
                f"Data timestamp: {data_timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            self.logger.warning(msg)
            if self.strict_mode:
                raise DataFreshnessError(msg)
            return False, msg
        
        return True, ""
    
    def validate_ohlcv_freshness(self, df: pd.DataFrame, symbol: str = "") -> Tuple[bool, str]:
        """
        Validate that OHLCV data is reasonably current.
        
        For daily data, checks that the last bar is from the most recent trading day.
        """
        if df.empty:
            return False, f"[{symbol}] OHLCV data is empty"
        
        # Get last bar date
        last_date = df.index[-1]
        if isinstance(last_date, pd.Timestamp):
            last_date = last_date.to_pydatetime()
        
        # For daily data, allow up to 3 days (weekends)
        now = datetime.now()
        age_days = (now.date() - last_date.date()).days
        
        if age_days > 4:  # More than 4 days is suspicious
            msg = (
                f"[{symbol}] OHLCV data may be stale - last bar is from "
                f"{last_date.strftime('%Y-%m-%d')} ({age_days} days ago)"
            )
            self.logger.warning(msg)
            return False, msg
        
        return True, ""
    
    def get_market_status(self, check_time: datetime = None) -> MarketStatus:
        """
        Determine current US market status.
        
        Note: This is a simplified check. For production, use a proper
        market calendar library.
        """
        if check_time is None:
            check_time = datetime.now()
        
        # Check weekend
        if check_time.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return MarketStatus.WEEKEND
        
        # Check holidays (simplified)
        date_str = check_time.strftime("%Y-%m-%d")
        if date_str in US_MARKET_HOLIDAYS:
            return MarketStatus.HOLIDAY
        
        # Check time of day (assuming Eastern Time - user should adjust)
        current_time = check_time.time()
        
        if MARKET_OPEN <= current_time < MARKET_CLOSE:
            return MarketStatus.OPEN
        elif PRE_MARKET_OPEN <= current_time < MARKET_OPEN:
            return MarketStatus.PRE_MARKET
        elif MARKET_CLOSE <= current_time < AFTER_HOURS_CLOSE:
            return MarketStatus.AFTER_HOURS
        else:
            return MarketStatus.CLOSED
    
    def is_market_open(self) -> bool:
        """Check if US market is currently in regular trading hours."""
        return self.get_market_status() == MarketStatus.OPEN
    
    def get_market_status_warning(self) -> Optional[str]:
        """
        Get warning message if market is not in regular hours.
        
        Returns None if market is open, warning string otherwise.
        """
        status = self.get_market_status()
        
        warnings = {
            MarketStatus.CLOSED: (
                "US market is CLOSED. Price data may be from previous session. "
                "Decisions made now may not reflect overnight developments."
            ),
            MarketStatus.WEEKEND: (
                "US market is CLOSED (weekend). Price data is from Friday's close. "
                "Weekend news/events may significantly impact Monday's open."
            ),
            MarketStatus.HOLIDAY: (
                "US market is CLOSED (holiday). Price data may be stale."
            ),
            MarketStatus.PRE_MARKET: (
                "US market is in PRE-MARKET hours. Liquidity is limited and "
                "prices may gap significantly at market open."
            ),
            MarketStatus.AFTER_HOURS: (
                "US market is in AFTER-HOURS trading. Liquidity is limited. "
                "Overnight news may cause gaps at next open."
            ),
        }
        
        return warnings.get(status)


# Risk warning constants
RISK_WARNINGS = {
    "gap_risk": (
        "WARNING: LEAPS options can experience significant gaps overnight or around "
        "earnings/news events. A -30% stop loss provides NO protection against gaps. "
        "Positions can lose 50-100% of value on adverse overnight moves."
    ),
    "leaps_total_loss": (
        "WARNING: LEAPS options can lose 100% of their value if the underlying moves "
        "against you significantly or fails to move enough before expiration. "
        "Only risk capital you can afford to lose completely."
    ),
    "signal_not_advice": (
        "DISCLAIMER: GO/WATCH/NO_GO signals are analytical outputs, NOT trade recommendations. "
        "Historical effectiveness is UNVALIDATED. Past signals do not predict future results. "
        "Consult a qualified financial advisor before making investment decisions."
    ),
    "conviction_uncertainty": (
        "NOTE: Conviction scores are composite metrics, not probabilities. A score of 80 "
        "does NOT mean 80% chance of profit. Scores have not been backtested against actual outcomes."
    ),
    "data_limitations": (
        "NOTE: Analysis is based on point-in-time data which may be delayed or incomplete. "
        "Options prices and Greeks can change rapidly. Always verify with live broker data."
    ),
    "earnings_binary": (
        "WARNING: Holding options through earnings is a binary event with unpredictable outcomes. "
        "Even 'good' earnings can result in stock declines. The 14-day earnings buffer helps but "
        "does not eliminate risk."
    ),
    "iv_crush": (
        "WARNING: Implied volatility typically drops sharply after earnings (IV crush). "
        "This can cause losses even if the underlying moves in your favor."
    ),
}


def get_risk_disclaimer_full() -> str:
    """Get full risk disclaimer for prominent display."""
    return """
================================================================================
                           IMPORTANT RISK DISCLOSURE
================================================================================

This software is for EDUCATIONAL and RESEARCH purposes only.

IT IS NOT:
- Investment advice
- A recommendation to buy or sell securities
- A guarantee of any trading outcome
- A substitute for professional financial advice

RISKS OF OPTIONS TRADING:
- Options can lose 100% of their value
- LEAPS are subject to time decay, volatility changes, and underlying price moves
- Gap risk: Positions can lose more than stop-loss levels overnight
- Liquidity risk: Wide spreads can result in poor execution
- Earnings risk: Binary events can cause unpredictable moves

SIGNAL LIMITATIONS:
- GO/WATCH/NO_GO signals have NOT been backtested
- Historical effectiveness is UNKNOWN
- Conviction scores are NOT probabilities
- Past patterns do not predict future results

BY USING THIS SOFTWARE, YOU ACKNOWLEDGE:
- You understand options trading risks
- You will make your own investment decisions
- You will consult qualified professionals as needed
- The developers assume NO liability for your trading outcomes

================================================================================
"""


def get_decision_disclaimer() -> str:
    """Get disclaimer to embed with every decision output."""
    return (
        "[This is analytical output, NOT a trade recommendation. "
        "Historical effectiveness UNVALIDATED. Options can lose 100% of value. "
        "Consult a financial advisor.]"
    )
