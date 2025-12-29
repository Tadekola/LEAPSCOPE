"""
Draft Order Ticket Module for LEAPSCOPE Phase 9.

IMPORTANT: This module generates draft tickets ONLY.
NO execution logic exists. This is preparation for future phases.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List
import json
from pathlib import Path


class OrderSide(str, Enum):
    """Order side."""
    BUY_TO_OPEN = "BUY_TO_OPEN"
    SELL_TO_CLOSE = "SELL_TO_CLOSE"
    BUY_TO_CLOSE = "BUY_TO_CLOSE"
    SELL_TO_OPEN = "SELL_TO_OPEN"


class OrderType(str, Enum):
    """Order type."""
    LIMIT = "LIMIT"
    MARKET = "MARKET"  # Not recommended for options


@dataclass
class DraftOrderTicket:
    """
    Draft order ticket for manual review.
    
    IMPORTANT: This is a DRAFT only.
    - NO execution capability
    - NO broker submission
    - For informational/planning purposes only
    
    The user must manually execute any trades through their broker.
    """
    
    # Identification
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    # Underlying
    symbol: str = ""
    asset_type: str = "STOCK"
    
    # Option details
    option_symbol: str = ""  # OCC format
    expiry: str = ""
    strike: float = 0.0
    option_type: str = "CALL"  # CALL or PUT
    
    # Order details
    side: OrderSide = OrderSide.BUY_TO_OPEN
    order_type: OrderType = OrderType.LIMIT
    quantity: int = 1
    limit_price: Optional[float] = None
    
    # Context
    rationale: str = ""
    conviction_score: Optional[float] = None
    decision_reasons: List[str] = field(default_factory=list)
    
    # Status (for tracking, NOT execution)
    status: str = "DRAFT"  # Always DRAFT - no execution
    notes: str = ""
    
    # Safety flag
    _execution_blocked: bool = field(default=True, repr=False)
    
    def __post_init__(self):
        """Ensure execution is always blocked."""
        self._execution_blocked = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "symbol": self.symbol,
            "asset_type": self.asset_type,
            "option_symbol": self.option_symbol,
            "expiry": self.expiry,
            "strike": self.strike,
            "option_type": self.option_type,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "quantity": self.quantity,
            "limit_price": self.limit_price,
            "rationale": self.rationale,
            "conviction_score": self.conviction_score,
            "decision_reasons": self.decision_reasons,
            "status": self.status,
            "notes": self.notes,
            "_disclaimer": "DRAFT ONLY - NO EXECUTION CAPABILITY"
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DraftOrderTicket":
        """Create from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.utcnow(),
            symbol=data.get("symbol", ""),
            asset_type=data.get("asset_type", "STOCK"),
            option_symbol=data.get("option_symbol", ""),
            expiry=data.get("expiry", ""),
            strike=data.get("strike", 0.0),
            option_type=data.get("option_type", "CALL"),
            side=OrderSide(data["side"]) if data.get("side") else OrderSide.BUY_TO_OPEN,
            order_type=OrderType(data["order_type"]) if data.get("order_type") else OrderType.LIMIT,
            quantity=data.get("quantity", 1),
            limit_price=data.get("limit_price"),
            rationale=data.get("rationale", ""),
            conviction_score=data.get("conviction_score"),
            decision_reasons=data.get("decision_reasons", []),
            status="DRAFT",  # Always DRAFT
            notes=data.get("notes", "")
        )
    
    @classmethod
    def from_scan_result(cls, result: Dict[str, Any], 
                          candidate_idx: int = 0,
                          quantity: int = 1) -> Optional["DraftOrderTicket"]:
        """
        Create a draft ticket from a scan result.
        
        Args:
            result: Scan result dict
            candidate_idx: Which options candidate to use
            quantity: Number of contracts
            
        Returns:
            DraftOrderTicket or None if no candidates
        """
        decision = result.get("decision")
        if decision not in ["GO", "WATCH"]:
            return None
        
        candidates = result.get("details", {}).get("options", {}).get("candidates", [])
        if not candidates or candidate_idx >= len(candidates):
            return None
        
        candidate = candidates[candidate_idx]
        
        # Calculate limit price (use bid for conservative entry)
        bid = candidate.get("bid", 0)
        ask = candidate.get("ask", 0)
        
        if bid and ask:
            # Use midpoint slightly below for limit
            limit_price = round((bid + ask) / 2 * 0.98, 2)
        else:
            limit_price = candidate.get("last") or bid or ask
        
        conviction = result.get("conviction", {})
        
        return cls(
            symbol=result.get("symbol", ""),
            asset_type=result.get("asset_type", "STOCK"),
            option_symbol=candidate.get("contract_symbol", ""),
            expiry=candidate.get("expiration", ""),
            strike=candidate.get("strike", 0.0),
            option_type=candidate.get("type", "CALL").upper(),
            side=OrderSide.BUY_TO_OPEN,
            order_type=OrderType.LIMIT,
            quantity=quantity,
            limit_price=limit_price,
            rationale=f"{decision} signal with {conviction.get('band', 'N/A')} conviction",
            conviction_score=conviction.get("score"),
            decision_reasons=result.get("reasons", [])[:5]
        )
    
    def to_display_string(self) -> str:
        """Format ticket for display."""
        lines = [
            "=" * 50,
            "📋 DRAFT ORDER TICKET (NOT FOR EXECUTION)",
            "=" * 50,
            f"Symbol:      {self.symbol} ({self.asset_type})",
            f"Contract:    {self.option_symbol}",
            f"             {self.strike} {self.option_type} exp {self.expiry}",
            f"Action:      {self.side.value}",
            f"Quantity:    {self.quantity} contract(s)",
            f"Limit Price: ${self.limit_price:.2f}" if self.limit_price else "Limit Price: N/A",
            "-" * 50,
            f"Conviction:  {self.conviction_score:.0f}" if self.conviction_score else "Conviction: N/A",
            f"Rationale:   {self.rationale}",
            "-" * 50,
            "⚠️  THIS IS A DRAFT ONLY",
            "⚠️  NO EXECUTION CAPABILITY EXISTS",
            "⚠️  MANUALLY EXECUTE VIA YOUR BROKER",
            "=" * 50
        ]
        return "\n".join(lines)


class DraftTicketStore:
    """Simple JSON storage for draft tickets."""
    
    def __init__(self, filepath: str = "data/draft_tickets.json"):
        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
    
    def save(self, ticket: DraftOrderTicket) -> bool:
        """Save a draft ticket."""
        tickets = self.load_all()
        tickets.append(ticket.to_dict())
        
        try:
            with open(self.filepath, "w") as f:
                json.dump(tickets, f, indent=2, default=str)
            return True
        except Exception:
            return False
    
    def load_all(self) -> List[Dict[str, Any]]:
        """Load all draft tickets."""
        if not self.filepath.exists():
            return []
        
        try:
            with open(self.filepath, "r") as f:
                return json.load(f)
        except Exception:
            return []
    
    def clear(self) -> bool:
        """Clear all draft tickets."""
        try:
            with open(self.filepath, "w") as f:
                json.dump([], f)
            return True
        except Exception:
            return False
