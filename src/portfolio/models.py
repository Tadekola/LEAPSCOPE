"""
Portfolio Models for LEAPSCOPE Phase 8.

Defines Position, Signal, and related enums for portfolio tracking.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Optional, List, Dict, Any


class PositionStatus(str, Enum):
    """Position lifecycle status."""
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    ROLLED = "ROLLED"


class OptionType(str, Enum):
    """Option contract type."""
    CALL = "CALL"
    PUT = "PUT"


class SignalType(str, Enum):
    """Management signal types."""
    HOLD = "HOLD"
    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LOSS = "STOP_LOSS"
    TECH_INVALIDATED = "TECH_INVALIDATED"
    EXPIRY_REVIEW = "EXPIRY_REVIEW"
    EARNINGS_RISK = "EARNINGS_RISK"


class Severity(str, Enum):
    """Signal severity levels."""
    INFO = "INFO"
    WARN = "WARN"
    CRITICAL = "CRITICAL"


@dataclass
class Signal:
    """
    Management signal for a position.
    
    Represents an actionable insight or alert for portfolio management.
    """
    signal_type: SignalType
    severity: Severity
    reasons: List[str]
    recommended_action: str
    triggered_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_type": self.signal_type.value,
            "severity": self.severity.value,
            "reasons": self.reasons,
            "recommended_action": self.recommended_action,
            "triggered_at": self.triggered_at.isoformat()
        }
    
    @classmethod
    def hold(cls) -> "Signal":
        """Create a default HOLD signal."""
        return cls(
            signal_type=SignalType.HOLD,
            severity=Severity.INFO,
            reasons=["Position within normal parameters"],
            recommended_action="Continue holding. No action required."
        )


@dataclass
class Position:
    """
    LEAPS Option Position.
    
    Represents a single options position in the portfolio.
    """
    # Core identifiers
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str = ""
    asset_type: str = "STOCK"  # STOCK / ETF
    
    # Contract details
    option_type: OptionType = OptionType.CALL
    expiry: str = ""  # YYYY-MM-DD
    strike: float = 0.0
    contracts: int = 1
    
    # Entry details
    entry_date: str = ""  # YYYY-MM-DD
    entry_price: float = 0.0  # Premium per contract
    underlying_entry_price: Optional[float] = None
    
    # Status
    status: PositionStatus = PositionStatus.OPEN
    
    # Optional metadata
    notes: str = ""
    tags: List[str] = field(default_factory=list)
    
    # Computed fields (populated during mark-to-market)
    underlying_last: Optional[float] = None
    option_last: Optional[float] = None
    option_bid: Optional[float] = None
    option_ask: Optional[float] = None
    days_to_expiry: Optional[int] = None
    market_value: Optional[float] = None
    cost_basis: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    iv: Optional[float] = None
    last_updated: Optional[datetime] = None
    pricing_source: str = ""  # tradier / yfinance / computed
    pricing_confidence: str = "HIGH"  # HIGH / MEDIUM / LOW
    
    # Signal (populated by manager)
    signal: Optional[Signal] = None
    
    def __post_init__(self):
        """Validate and normalize fields."""
        if isinstance(self.option_type, str):
            self.option_type = OptionType(self.option_type.upper())
        if isinstance(self.status, str):
            self.status = PositionStatus(self.status.upper())
    
    @property
    def contract_symbol(self) -> str:
        """Generate OCC-style contract symbol."""
        if not self.expiry or not self.symbol:
            return ""
        
        exp_date = datetime.strptime(self.expiry, "%Y-%m-%d")
        exp_str = exp_date.strftime("%y%m%d")
        opt_char = "C" if self.option_type == OptionType.CALL else "P"
        strike_str = f"{int(self.strike * 1000):08d}"
        
        return f"{self.symbol}{exp_str}{opt_char}{strike_str}"
    
    @property
    def expiry_date(self) -> Optional[date]:
        """Parse expiry as date object."""
        if not self.expiry:
            return None
        try:
            return datetime.strptime(self.expiry, "%Y-%m-%d").date()
        except ValueError:
            return None
    
    @property
    def entry_date_obj(self) -> Optional[date]:
        """Parse entry_date as date object."""
        if not self.entry_date:
            return None
        try:
            return datetime.strptime(self.entry_date, "%Y-%m-%d").date()
        except ValueError:
            return None
    
    def calculate_cost_basis(self) -> float:
        """Calculate total cost basis."""
        return self.entry_price * self.contracts * 100
    
    def calculate_market_value(self) -> Optional[float]:
        """Calculate current market value."""
        if self.option_last is None:
            return None
        return self.option_last * self.contracts * 100
    
    def calculate_pnl(self) -> tuple[Optional[float], Optional[float]]:
        """Calculate unrealized P&L in dollars and percentage."""
        cost = self.calculate_cost_basis()
        if cost == 0:
            return None, None
        
        market = self.calculate_market_value()
        if market is None:
            return None, None
        
        pnl_dollars = market - cost
        pnl_pct = (pnl_dollars / cost) * 100
        
        return pnl_dollars, pnl_pct
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert position to dictionary for serialization."""
        return {
            "id": self.id,
            "symbol": self.symbol,
            "asset_type": self.asset_type,
            "option_type": self.option_type.value if isinstance(self.option_type, OptionType) else self.option_type,
            "expiry": self.expiry,
            "strike": self.strike,
            "contracts": self.contracts,
            "entry_date": self.entry_date,
            "entry_price": self.entry_price,
            "underlying_entry_price": self.underlying_entry_price,
            "status": self.status.value if isinstance(self.status, PositionStatus) else self.status,
            "notes": self.notes,
            "tags": self.tags,
            # Mark-to-market fields
            "underlying_last": self.underlying_last,
            "option_last": self.option_last,
            "option_bid": self.option_bid,
            "option_ask": self.option_ask,
            "days_to_expiry": self.days_to_expiry,
            "market_value": self.market_value,
            "cost_basis": self.cost_basis,
            "unrealized_pnl": self.unrealized_pnl,
            "unrealized_pnl_pct": self.unrealized_pnl_pct,
            "delta": self.delta,
            "gamma": self.gamma,
            "theta": self.theta,
            "vega": self.vega,
            "iv": self.iv,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
            "pricing_source": self.pricing_source,
            "pricing_confidence": self.pricing_confidence,
            "signal": self.signal.to_dict() if self.signal else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Position":
        """Create position from dictionary."""
        # Handle signal separately
        signal_data = data.pop("signal", None)
        
        # Handle enums
        if "option_type" in data and isinstance(data["option_type"], str):
            data["option_type"] = OptionType(data["option_type"].upper())
        if "status" in data and isinstance(data["status"], str):
            data["status"] = PositionStatus(data["status"].upper())
        
        # Handle datetime
        if "last_updated" in data and data["last_updated"]:
            if isinstance(data["last_updated"], str):
                data["last_updated"] = datetime.fromisoformat(data["last_updated"])
        
        # Filter valid fields
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        
        position = cls(**filtered_data)
        
        # Restore signal
        if signal_data:
            position.signal = Signal(
                signal_type=SignalType(signal_data["signal_type"]),
                severity=Severity(signal_data["severity"]),
                reasons=signal_data["reasons"],
                recommended_action=signal_data["recommended_action"],
                triggered_at=datetime.fromisoformat(signal_data["triggered_at"])
            )
        
        return position
