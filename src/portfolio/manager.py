"""
Portfolio Manager for LEAPSCOPE Phase 8.

Orchestrates position management, pricing, and signal generation.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from src.portfolio.models import (
    Position, PositionStatus, OptionType,
    Signal, SignalType, Severity
)
from src.portfolio.storage import PortfolioStorage
from src.portfolio.pricing import PositionPricer
from src.providers.manager import ProviderManager
from src.analysis.technical import TechnicalAnalyzer


class PortfolioManager:
    """
    Central manager for portfolio operations.
    
    Responsibilities:
    - Position CRUD via storage
    - Mark-to-market pricing
    - Signal generation based on management rules
    - Technical analysis integration for invalidation signals
    """
    
    def __init__(
        self,
        provider_manager: ProviderManager,
        config: Dict[str, Any],
        storage: Optional[PortfolioStorage] = None
    ):
        self.provider = provider_manager
        self.config = config
        self.storage = storage or PortfolioStorage()
        self.pricer = PositionPricer(provider_manager, config)
        self.ta_engine = TechnicalAnalyzer(config.get("technical_analysis", {}))
        self.logger = logging.getLogger("LEAPSCOPE.Portfolio.Manager")
        
        # Load config
        portfolio_config = config.get("portfolio", {})
        decision_config = config.get("decision", {})
        
        self.take_profit_pct = portfolio_config.get("take_profit_pct", 50)
        self.stop_loss_pct = portfolio_config.get("stop_loss_pct", -30)
        self.expiry_review_days = portfolio_config.get("expiry_review_days", 120)
        self.roll_guidance_days = portfolio_config.get("roll_guidance_days", 270)
        self.earnings_block_days = decision_config.get("earnings_block_days", 14)
        
        self.logger.info(
            f"PortfolioManager initialized: TP={self.take_profit_pct}%, "
            f"SL={self.stop_loss_pct}%, Expiry Review={self.expiry_review_days}d"
        )
    
    # Position CRUD
    
    def add_position(self, position: Position) -> bool:
        """Add a new position to the portfolio."""
        return self.storage.add_position(position)
    
    def get_position(self, position_id: str) -> Optional[Position]:
        """Get a position by ID."""
        return self.storage.get_position(position_id)
    
    def get_all_positions(self, status: Optional[PositionStatus] = None) -> List[Position]:
        """Get all positions, optionally filtered by status."""
        return self.storage.get_all_positions(status)
    
    def get_open_positions(self) -> List[Position]:
        """Get all open positions."""
        return self.storage.get_open_positions()
    
    def close_position(self, position_id: str, notes: str = "") -> bool:
        """Close a position."""
        return self.storage.close_position(position_id, notes)
    
    def update_position(self, position: Position) -> bool:
        """Update a position."""
        return self.storage.update_position(position)
    
    def delete_position(self, position_id: str) -> bool:
        """Delete a position."""
        return self.storage.delete_position(position_id)
    
    # Mark-to-Market & Signals
    
    def refresh_portfolio(self) -> List[Position]:
        """
        Refresh all open positions with current pricing and signals.
        
        Returns list of priced positions with signals attached.
        """
        self.logger.info("Refreshing portfolio...")
        
        positions = self.get_open_positions()
        if not positions:
            self.logger.info("No open positions to refresh")
            return []
        
        self.logger.info(f"Refreshing {len(positions)} open positions")
        
        # Price all positions
        priced_positions = self.pricer.price_all_positions(positions)
        
        # Generate signals for each position
        for position in priced_positions:
            position.signal = self._generate_signal(position)
        
        return priced_positions
    
    def refresh_position(self, position_id: str) -> Optional[Position]:
        """Refresh a single position with current pricing and signal."""
        position = self.get_position(position_id)
        if not position:
            return None
        
        position = self.pricer.price_position(position)
        position.signal = self._generate_signal(position)
        
        return position
    
    def _generate_signal(self, position: Position) -> Signal:
        """
        Generate management signal for a position.
        
        Signal priority (first match wins):
        1. STOP_LOSS (CRITICAL)
        2. TECH_INVALIDATED (CRITICAL)
        3. TAKE_PROFIT (WARN)
        4. EARNINGS_RISK (WARN)
        5. EXPIRY_REVIEW (WARN)
        6. HOLD (INFO)
        """
        reasons = []
        
        # Check P&L-based signals
        pnl_pct = position.unrealized_pnl_pct
        
        # 1. STOP_LOSS check
        if pnl_pct is not None and pnl_pct <= self.stop_loss_pct:
            return Signal(
                signal_type=SignalType.STOP_LOSS,
                severity=Severity.CRITICAL,
                reasons=[
                    f"Position down {pnl_pct:.1f}% (threshold: {self.stop_loss_pct}%)",
                    f"Unrealized loss: ${position.unrealized_pnl:,.2f}" if position.unrealized_pnl else ""
                ],
                recommended_action=(
                    "CRITICAL: Consider closing position to limit further losses. "
                    "Evaluate if the original thesis is still valid. "
                    "If technical breakdown confirmed, exit may be warranted."
                )
            )
        
        # 2. TECH_INVALIDATED check
        tech_signal = self._check_technical_invalidation(position)
        if tech_signal:
            return tech_signal
        
        # 3. TAKE_PROFIT check
        if pnl_pct is not None and pnl_pct >= self.take_profit_pct:
            action = (
                f"Position up {pnl_pct:.1f}% (target: {self.take_profit_pct}%). "
                f"Unrealized gain: ${position.unrealized_pnl:,.2f}. "
            )
            
            # Add roll guidance if within window
            if position.days_to_expiry and position.days_to_expiry <= self.roll_guidance_days:
                action += (
                    "Consider rolling out 6-12 months while maintaining delta band "
                    "to lock in gains and extend exposure."
                )
            else:
                action += (
                    "Consider taking partial profits or setting a trailing stop. "
                    "Thesis may have played out."
                )
            
            return Signal(
                signal_type=SignalType.TAKE_PROFIT,
                severity=Severity.WARN,
                reasons=[
                    f"Profit target reached: {pnl_pct:.1f}% >= {self.take_profit_pct}%",
                    f"Market value: ${position.market_value:,.2f}" if position.market_value else ""
                ],
                recommended_action=action
            )
        
        # 4. EARNINGS_RISK check
        earnings_signal = self._check_earnings_risk(position)
        if earnings_signal:
            return earnings_signal
        
        # 5. EXPIRY_REVIEW check
        if position.days_to_expiry is not None and position.days_to_expiry <= self.expiry_review_days:
            action = (
                f"Position expires in {position.days_to_expiry} days. "
                f"Review theta decay impact. "
            )
            
            if pnl_pct and pnl_pct > 0:
                action += (
                    "Position is profitable - consider rolling out 6-12 months "
                    "to extend exposure while maintaining similar delta."
                )
            else:
                action += (
                    "Position is at/near loss - evaluate if thesis is still valid. "
                    "Rolling may be appropriate if trend intact, otherwise consider closing."
                )
            
            return Signal(
                signal_type=SignalType.EXPIRY_REVIEW,
                severity=Severity.WARN,
                reasons=[
                    f"Expiration approaching: {position.days_to_expiry} days remaining",
                    f"Expiry date: {position.expiry}",
                    f"Current theta: {position.theta:.4f}" if position.theta else "Theta unknown"
                ],
                recommended_action=action
            )
        
        # 6. Default HOLD
        return Signal.hold()
    
    def _check_technical_invalidation(self, position: Position) -> Optional[Signal]:
        """
        Check if technical trend invalidates the position.
        
        - CALL: Invalidated if trend turns BEARISH
        - PUT: Invalidated if trend turns BULLISH
        """
        try:
            # Fetch recent OHLCV
            df = self.provider.fetch_ohlcv(position.symbol, period="1y", interval="1d")
            if df.empty:
                return None
            
            # Run TA
            ta_report = self.ta_engine.analyze(position.symbol, df)
            trend = ta_report.get("trend", "UNKNOWN")
            
            # Check invalidation
            invalidated = False
            if position.option_type == OptionType.CALL and trend == "BEARISH":
                invalidated = True
                reason = "CALL position invalidated: Technical trend turned BEARISH"
            elif position.option_type == OptionType.PUT and trend == "BULLISH":
                invalidated = True
                reason = "PUT position invalidated: Technical trend turned BULLISH"
            
            if invalidated:
                indicators = ta_report.get("indicators", {})
                signals = ta_report.get("signals", {})
                
                return Signal(
                    signal_type=SignalType.TECH_INVALIDATED,
                    severity=Severity.CRITICAL,
                    reasons=[
                        reason,
                        f"Current trend: {trend}",
                        f"RSI: {indicators.get('rsi', 'N/A'):.1f}" if indicators.get('rsi') else "",
                        "Death cross detected" if signals.get('death_cross') else "",
                        "Golden cross detected" if signals.get('golden_cross') else ""
                    ],
                    recommended_action=(
                        "CRITICAL: Technical thesis invalidated. "
                        "Consider exiting position to preserve capital. "
                        "Wait for trend confirmation before re-entry."
                    )
                )
            
        except Exception as e:
            self.logger.warning(f"Error checking technical invalidation: {e}")
        
        return None
    
    def _check_earnings_risk(self, position: Position) -> Optional[Signal]:
        """Check if earnings are approaching within risk window."""
        try:
            earnings_date = self.provider.fetch_earnings_date(position.symbol)
            
            if earnings_date:
                days_to_earnings = (earnings_date.date() - datetime.now().date()).days
                
                if 0 <= days_to_earnings <= self.earnings_block_days:
                    return Signal(
                        signal_type=SignalType.EARNINGS_RISK,
                        severity=Severity.WARN,
                        reasons=[
                            f"Earnings in {days_to_earnings} days ({earnings_date.strftime('%Y-%m-%d')})",
                            f"Risk window: {self.earnings_block_days} days",
                            "Binary event risk - significant price movement possible"
                        ],
                        recommended_action=(
                            f"Earnings report in {days_to_earnings} days. "
                            "Consider reducing position size before earnings to limit binary risk, "
                            "or accept the volatility if thesis is strong. "
                            "IV typically elevated pre-earnings."
                        )
                    )
        except Exception as e:
            self.logger.warning(f"Error checking earnings: {e}")
        
        return None
    
    # Portfolio Analytics
    
    def get_portfolio_summary(self, positions: List[Position] = None) -> Dict[str, Any]:
        """
        Get comprehensive portfolio summary.
        
        If positions not provided, fetches and refreshes open positions.
        """
        if positions is None:
            positions = self.refresh_portfolio()
        
        if not positions:
            return {
                "total_positions": 0,
                "total_market_value": 0,
                "total_cost_basis": 0,
                "total_unrealized_pnl": 0,
                "total_unrealized_pnl_pct": 0,
                "signals": {},
                "by_symbol": {},
                "last_updated": datetime.utcnow().isoformat()
            }
        
        # Value metrics
        value_metrics = self.pricer.get_portfolio_value(positions)
        
        # Signal counts
        signal_counts = {}
        for p in positions:
            if p.signal:
                sig_type = p.signal.signal_type.value
                signal_counts[sig_type] = signal_counts.get(sig_type, 0) + 1
        
        # By symbol breakdown
        by_symbol = {}
        for p in positions:
            if p.symbol not in by_symbol:
                by_symbol[p.symbol] = {
                    "positions": 0,
                    "market_value": 0,
                    "unrealized_pnl": 0
                }
            by_symbol[p.symbol]["positions"] += 1
            by_symbol[p.symbol]["market_value"] += p.market_value or 0
            by_symbol[p.symbol]["unrealized_pnl"] += p.unrealized_pnl or 0
        
        # Critical signals
        critical_positions = [
            p for p in positions 
            if p.signal and p.signal.severity == Severity.CRITICAL
        ]
        
        return {
            **value_metrics,
            "total_positions": len(positions),
            "signals": signal_counts,
            "critical_count": len(critical_positions),
            "critical_positions": [
                {"symbol": p.symbol, "signal": p.signal.signal_type.value}
                for p in critical_positions
            ],
            "by_symbol": by_symbol,
            "last_updated": datetime.utcnow().isoformat()
        }
    
    def get_signals_summary(self, positions: List[Position] = None) -> List[Dict[str, Any]]:
        """Get list of all non-HOLD signals for reporting."""
        if positions is None:
            positions = self.refresh_portfolio()
        
        signals = []
        for p in positions:
            if p.signal and p.signal.signal_type != SignalType.HOLD:
                signals.append({
                    "position_id": p.id,
                    "symbol": p.symbol,
                    "strike": p.strike,
                    "expiry": p.expiry,
                    "option_type": p.option_type.value,
                    "signal": p.signal.to_dict(),
                    "pnl_pct": p.unrealized_pnl_pct,
                    "days_to_expiry": p.days_to_expiry
                })
        
        # Sort by severity (CRITICAL first)
        severity_order = {"CRITICAL": 0, "WARN": 1, "INFO": 2}
        signals.sort(key=lambda x: severity_order.get(x["signal"]["severity"], 3))
        
        return signals
    
    # Import/Export
    
    def export_portfolio(self, filepath: str = "data/portfolio.json") -> bool:
        """Export portfolio to JSON."""
        return self.storage.export_to_json(filepath)
    
    def import_portfolio(self, filepath: str = "data/portfolio.json", overwrite: bool = False) -> int:
        """Import portfolio from JSON."""
        return self.storage.import_from_json(filepath, overwrite)
