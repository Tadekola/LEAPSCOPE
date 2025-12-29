"""
Tests for LEAPSCOPE Portfolio Module (Phase 8).

Required tests:
1. Position P/L calculation correctness
2. TAKE_PROFIT triggered
3. STOP_LOSS triggered
4. EXPIRY_REVIEW triggered
5. TECH_INVALIDATED logic for CALL vs PUT
"""

import pytest
import sys
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.portfolio.models import (
    Position, PositionStatus, OptionType,
    Signal, SignalType, Severity
)
from src.portfolio.storage import PortfolioStorage
from src.portfolio.manager import PortfolioManager


class TestPositionPnLCalculation:
    """Test 1: Position P/L calculation correctness."""
    
    def test_pnl_calculation_profit(self):
        """Test P&L calculation for a profitable position."""
        position = Position(
            symbol="AAPL",
            option_type=OptionType.CALL,
            strike=150.0,
            contracts=2,
            entry_price=10.0,  # $10 per contract
            expiry="2025-12-19",
            entry_date="2024-06-01"
        )
        
        # Set current option price
        position.option_last = 15.0  # $15 per contract (50% profit)
        
        # Calculate
        position.cost_basis = position.calculate_cost_basis()
        position.market_value = position.calculate_market_value()
        pnl, pnl_pct = position.calculate_pnl()
        
        # Verify
        assert position.cost_basis == 2000.0  # 2 contracts * $10 * 100
        assert position.market_value == 3000.0  # 2 contracts * $15 * 100
        assert pnl == 1000.0  # $1000 profit
        assert pnl_pct == 50.0  # 50% profit
    
    def test_pnl_calculation_loss(self):
        """Test P&L calculation for a losing position."""
        position = Position(
            symbol="MSFT",
            option_type=OptionType.CALL,
            strike=400.0,
            contracts=1,
            entry_price=20.0,
            expiry="2025-12-19",
            entry_date="2024-06-01"
        )
        
        # Set current option price (40% loss)
        position.option_last = 12.0
        
        # Calculate
        position.cost_basis = position.calculate_cost_basis()
        position.market_value = position.calculate_market_value()
        pnl, pnl_pct = position.calculate_pnl()
        
        # Verify
        assert position.cost_basis == 2000.0
        assert position.market_value == 1200.0
        assert pnl == -800.0
        assert pnl_pct == -40.0
    
    def test_pnl_calculation_missing_price(self):
        """Test P&L calculation when option price is missing."""
        position = Position(
            symbol="GOOGL",
            option_type=OptionType.CALL,
            strike=150.0,
            contracts=1,
            entry_price=10.0,
            expiry="2025-12-19",
            entry_date="2024-06-01"
        )
        
        # option_last is None (not priced)
        pnl, pnl_pct = position.calculate_pnl()
        
        assert pnl is None
        assert pnl_pct is None


class TestTakeProfitSignal:
    """Test 2: TAKE_PROFIT triggered."""
    
    def test_take_profit_triggered(self):
        """Test TAKE_PROFIT signal when profit exceeds threshold."""
        # Create position with 60% profit
        position = Position(
            symbol="AAPL",
            option_type=OptionType.CALL,
            strike=150.0,
            contracts=1,
            entry_price=10.0,
            expiry="2025-12-19",
            entry_date="2024-06-01"
        )
        position.option_last = 16.0  # 60% profit
        position.cost_basis = position.calculate_cost_basis()
        position.market_value = position.calculate_market_value()
        position.unrealized_pnl, position.unrealized_pnl_pct = position.calculate_pnl()
        position.days_to_expiry = 300
        
        # Create mock manager with 50% take profit threshold
        config = {
            "portfolio": {"take_profit_pct": 50, "stop_loss_pct": -30, "expiry_review_days": 120},
            "decision": {"earnings_block_days": 14}
        }
        
        with patch('src.portfolio.manager.ProviderManager'):
            manager = PortfolioManager.__new__(PortfolioManager)
            manager.take_profit_pct = 50
            manager.stop_loss_pct = -30
            manager.expiry_review_days = 120
            manager.roll_guidance_days = 270
            manager.earnings_block_days = 14
            manager.provider = Mock()
            manager.ta_engine = Mock()
            manager.logger = Mock()
            
            # Mock technical check to return non-invalidated
            manager._check_technical_invalidation = Mock(return_value=None)
            manager._check_earnings_risk = Mock(return_value=None)
            
            signal = manager._generate_signal(position)
        
        assert signal.signal_type == SignalType.TAKE_PROFIT
        assert signal.severity == Severity.WARN
        assert "60.0%" in signal.reasons[0]
    
    def test_take_profit_not_triggered(self):
        """Test TAKE_PROFIT signal NOT triggered when below threshold."""
        position = Position(
            symbol="AAPL",
            option_type=OptionType.CALL,
            strike=150.0,
            contracts=1,
            entry_price=10.0,
            expiry="2025-12-19",
            entry_date="2024-06-01"
        )
        position.option_last = 12.0  # Only 20% profit
        position.cost_basis = position.calculate_cost_basis()
        position.market_value = position.calculate_market_value()
        position.unrealized_pnl, position.unrealized_pnl_pct = position.calculate_pnl()
        position.days_to_expiry = 300
        
        with patch('src.portfolio.manager.ProviderManager'):
            manager = PortfolioManager.__new__(PortfolioManager)
            manager.take_profit_pct = 50
            manager.stop_loss_pct = -30
            manager.expiry_review_days = 120
            manager.roll_guidance_days = 270
            manager.earnings_block_days = 14
            manager.provider = Mock()
            manager.ta_engine = Mock()
            manager.logger = Mock()
            
            manager._check_technical_invalidation = Mock(return_value=None)
            manager._check_earnings_risk = Mock(return_value=None)
            
            signal = manager._generate_signal(position)
        
        # Should be HOLD since 20% < 50% threshold
        assert signal.signal_type == SignalType.HOLD


class TestStopLossSignal:
    """Test 3: STOP_LOSS triggered."""
    
    def test_stop_loss_triggered(self):
        """Test STOP_LOSS signal when loss exceeds threshold."""
        position = Position(
            symbol="TSLA",
            option_type=OptionType.CALL,
            strike=250.0,
            contracts=1,
            entry_price=25.0,
            expiry="2025-12-19",
            entry_date="2024-06-01"
        )
        position.option_last = 15.0  # 40% loss
        position.cost_basis = position.calculate_cost_basis()
        position.market_value = position.calculate_market_value()
        position.unrealized_pnl, position.unrealized_pnl_pct = position.calculate_pnl()
        position.days_to_expiry = 300
        
        with patch('src.portfolio.manager.ProviderManager'):
            manager = PortfolioManager.__new__(PortfolioManager)
            manager.take_profit_pct = 50
            manager.stop_loss_pct = -30  # Stop loss at -30%
            manager.expiry_review_days = 120
            manager.roll_guidance_days = 270
            manager.earnings_block_days = 14
            manager.provider = Mock()
            manager.ta_engine = Mock()
            manager.logger = Mock()
            
            signal = manager._generate_signal(position)
        
        assert signal.signal_type == SignalType.STOP_LOSS
        assert signal.severity == Severity.CRITICAL
        assert "-40.0%" in signal.reasons[0]
    
    def test_stop_loss_not_triggered(self):
        """Test STOP_LOSS signal NOT triggered when loss below threshold."""
        position = Position(
            symbol="TSLA",
            option_type=OptionType.CALL,
            strike=250.0,
            contracts=1,
            entry_price=25.0,
            expiry="2025-12-19",
            entry_date="2024-06-01"
        )
        position.option_last = 20.0  # Only 20% loss
        position.cost_basis = position.calculate_cost_basis()
        position.market_value = position.calculate_market_value()
        position.unrealized_pnl, position.unrealized_pnl_pct = position.calculate_pnl()
        position.days_to_expiry = 300
        
        with patch('src.portfolio.manager.ProviderManager'):
            manager = PortfolioManager.__new__(PortfolioManager)
            manager.take_profit_pct = 50
            manager.stop_loss_pct = -30
            manager.expiry_review_days = 120
            manager.roll_guidance_days = 270
            manager.earnings_block_days = 14
            manager.provider = Mock()
            manager.ta_engine = Mock()
            manager.logger = Mock()
            
            manager._check_technical_invalidation = Mock(return_value=None)
            manager._check_earnings_risk = Mock(return_value=None)
            
            signal = manager._generate_signal(position)
        
        # -20% loss is above -30% threshold, so should be HOLD
        assert signal.signal_type == SignalType.HOLD


class TestExpiryReviewSignal:
    """Test 4: EXPIRY_REVIEW triggered."""
    
    def test_expiry_review_triggered(self):
        """Test EXPIRY_REVIEW signal when expiration approaching."""
        position = Position(
            symbol="NVDA",
            option_type=OptionType.CALL,
            strike=500.0,
            contracts=1,
            entry_price=50.0,
            expiry="2025-04-19",  # Close expiry
            entry_date="2024-06-01"
        )
        position.option_last = 55.0  # Small profit
        position.cost_basis = position.calculate_cost_basis()
        position.market_value = position.calculate_market_value()
        position.unrealized_pnl, position.unrealized_pnl_pct = position.calculate_pnl()
        position.days_to_expiry = 90  # < 120 days threshold
        position.theta = -0.15
        
        with patch('src.portfolio.manager.ProviderManager'):
            manager = PortfolioManager.__new__(PortfolioManager)
            manager.take_profit_pct = 50
            manager.stop_loss_pct = -30
            manager.expiry_review_days = 120  # Trigger at 120 days
            manager.roll_guidance_days = 270
            manager.earnings_block_days = 14
            manager.provider = Mock()
            manager.ta_engine = Mock()
            manager.logger = Mock()
            
            manager._check_technical_invalidation = Mock(return_value=None)
            manager._check_earnings_risk = Mock(return_value=None)
            
            signal = manager._generate_signal(position)
        
        assert signal.signal_type == SignalType.EXPIRY_REVIEW
        assert signal.severity == Severity.WARN
        assert "90 days" in signal.reasons[0]
    
    def test_expiry_review_not_triggered(self):
        """Test EXPIRY_REVIEW NOT triggered when expiration far away."""
        position = Position(
            symbol="NVDA",
            option_type=OptionType.CALL,
            strike=500.0,
            contracts=1,
            entry_price=50.0,
            expiry="2026-01-16",
            entry_date="2024-06-01"
        )
        position.option_last = 52.0
        position.cost_basis = position.calculate_cost_basis()
        position.market_value = position.calculate_market_value()
        position.unrealized_pnl, position.unrealized_pnl_pct = position.calculate_pnl()
        position.days_to_expiry = 400  # > 120 days
        
        with patch('src.portfolio.manager.ProviderManager'):
            manager = PortfolioManager.__new__(PortfolioManager)
            manager.take_profit_pct = 50
            manager.stop_loss_pct = -30
            manager.expiry_review_days = 120
            manager.roll_guidance_days = 270
            manager.earnings_block_days = 14
            manager.provider = Mock()
            manager.ta_engine = Mock()
            manager.logger = Mock()
            
            manager._check_technical_invalidation = Mock(return_value=None)
            manager._check_earnings_risk = Mock(return_value=None)
            
            signal = manager._generate_signal(position)
        
        assert signal.signal_type == SignalType.HOLD


class TestTechInvalidatedSignal:
    """Test 5: TECH_INVALIDATED logic for CALL vs PUT."""
    
    def test_call_invalidated_on_bearish_trend(self):
        """Test CALL position invalidated when trend turns BEARISH."""
        position = Position(
            symbol="META",
            option_type=OptionType.CALL,
            strike=400.0,
            contracts=1,
            entry_price=30.0,
            expiry="2025-12-19",
            entry_date="2024-06-01"
        )
        position.option_last = 25.0
        position.cost_basis = position.calculate_cost_basis()
        position.market_value = position.calculate_market_value()
        position.unrealized_pnl, position.unrealized_pnl_pct = position.calculate_pnl()
        position.days_to_expiry = 300
        
        # Mock TA report with BEARISH trend
        mock_ta_report = {
            "trend": "BEARISH",
            "indicators": {"rsi": 35},
            "signals": {"death_cross": True, "golden_cross": False}
        }
        
        with patch('src.portfolio.manager.ProviderManager'):
            manager = PortfolioManager.__new__(PortfolioManager)
            manager.take_profit_pct = 50
            manager.stop_loss_pct = -30
            manager.expiry_review_days = 120
            manager.roll_guidance_days = 270
            manager.earnings_block_days = 14
            manager.logger = Mock()
            
            # Mock provider to return OHLCV data
            manager.provider = Mock()
            mock_df = Mock()
            mock_df.empty = False
            manager.provider.fetch_ohlcv = Mock(return_value=mock_df)
            
            # Mock TA engine
            manager.ta_engine = Mock()
            manager.ta_engine.analyze = Mock(return_value=mock_ta_report)
            
            signal = manager._check_technical_invalidation(position)
        
        assert signal is not None
        assert signal.signal_type == SignalType.TECH_INVALIDATED
        assert signal.severity == Severity.CRITICAL
        assert "BEARISH" in signal.reasons[1]
    
    def test_put_invalidated_on_bullish_trend(self):
        """Test PUT position invalidated when trend turns BULLISH."""
        position = Position(
            symbol="SPY",
            option_type=OptionType.PUT,  # PUT position
            strike=450.0,
            contracts=1,
            entry_price=15.0,
            expiry="2025-12-19",
            entry_date="2024-06-01"
        )
        position.option_last = 10.0
        position.cost_basis = position.calculate_cost_basis()
        position.market_value = position.calculate_market_value()
        position.unrealized_pnl, position.unrealized_pnl_pct = position.calculate_pnl()
        position.days_to_expiry = 300
        
        # Mock TA report with BULLISH trend (invalidates PUT)
        mock_ta_report = {
            "trend": "BULLISH",
            "indicators": {"rsi": 65},
            "signals": {"death_cross": False, "golden_cross": True}
        }
        
        with patch('src.portfolio.manager.ProviderManager'):
            manager = PortfolioManager.__new__(PortfolioManager)
            manager.take_profit_pct = 50
            manager.stop_loss_pct = -30
            manager.expiry_review_days = 120
            manager.roll_guidance_days = 270
            manager.earnings_block_days = 14
            manager.logger = Mock()
            
            manager.provider = Mock()
            mock_df = Mock()
            mock_df.empty = False
            manager.provider.fetch_ohlcv = Mock(return_value=mock_df)
            
            manager.ta_engine = Mock()
            manager.ta_engine.analyze = Mock(return_value=mock_ta_report)
            
            signal = manager._check_technical_invalidation(position)
        
        assert signal is not None
        assert signal.signal_type == SignalType.TECH_INVALIDATED
        assert signal.severity == Severity.CRITICAL
        assert "BULLISH" in signal.reasons[1]
    
    def test_call_not_invalidated_on_bullish_trend(self):
        """Test CALL position NOT invalidated when trend is BULLISH."""
        position = Position(
            symbol="AAPL",
            option_type=OptionType.CALL,
            strike=200.0,
            contracts=1,
            entry_price=20.0,
            expiry="2025-12-19",
            entry_date="2024-06-01"
        )
        
        mock_ta_report = {
            "trend": "BULLISH",
            "indicators": {"rsi": 55},
            "signals": {"death_cross": False, "golden_cross": False}
        }
        
        with patch('src.portfolio.manager.ProviderManager'):
            manager = PortfolioManager.__new__(PortfolioManager)
            manager.logger = Mock()
            
            manager.provider = Mock()
            mock_df = Mock()
            mock_df.empty = False
            manager.provider.fetch_ohlcv = Mock(return_value=mock_df)
            
            manager.ta_engine = Mock()
            manager.ta_engine.analyze = Mock(return_value=mock_ta_report)
            
            signal = manager._check_technical_invalidation(position)
        
        # CALL with BULLISH trend should not be invalidated
        assert signal is None


class TestPositionStorage:
    """Additional tests for position storage."""
    
    def test_position_to_dict_and_back(self):
        """Test position serialization round-trip."""
        position = Position(
            symbol="AMZN",
            asset_type="STOCK",
            option_type=OptionType.CALL,
            strike=180.0,
            contracts=3,
            entry_price=12.50,
            expiry="2025-12-19",
            entry_date="2024-06-15",
            underlying_entry_price=175.0,
            notes="Test position",
            tags=["tech", "megacap"],
            status=PositionStatus.OPEN
        )
        
        # Convert to dict and back
        data = position.to_dict()
        restored = Position.from_dict(data)
        
        assert restored.symbol == position.symbol
        assert restored.strike == position.strike
        assert restored.contracts == position.contracts
        assert restored.option_type == position.option_type
        assert restored.status == position.status
        assert restored.notes == position.notes
        assert restored.tags == position.tags


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
