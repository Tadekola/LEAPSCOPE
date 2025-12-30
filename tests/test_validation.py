"""
Tests for Data Validation Module.

Critical tests for data freshness, market hours, and risk warnings.
"""

import pytest
import sys
import os
from datetime import datetime, time, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.validation import (
    DataValidator,
    DataFreshnessError,
    MarketStatus,
    RISK_WARNINGS,
    get_decision_disclaimer,
    get_risk_disclaimer_full
)


class TestDataFreshnessValidation:
    """Test data freshness validation."""
    
    def test_fresh_data_passes(self):
        """Test that recent data passes validation."""
        validator = DataValidator(max_data_age_minutes=15, strict_mode=True)
        
        # Data from 5 minutes ago should pass
        recent_timestamp = datetime.now() - timedelta(minutes=5)
        is_valid, msg = validator.validate_price_freshness(recent_timestamp, "AAPL")
        
        assert is_valid is True
        assert msg == ""
    
    def test_stale_data_fails_strict(self):
        """Test that stale data fails in strict mode."""
        validator = DataValidator(max_data_age_minutes=15, strict_mode=True)
        
        # Data from 30 minutes ago should fail
        old_timestamp = datetime.now() - timedelta(minutes=30)
        
        with pytest.raises(DataFreshnessError):
            validator.validate_price_freshness(old_timestamp, "AAPL")
    
    def test_stale_data_warns_nonstrict(self):
        """Test that stale data returns warning in non-strict mode."""
        validator = DataValidator(max_data_age_minutes=15, strict_mode=False)
        
        old_timestamp = datetime.now() - timedelta(minutes=30)
        is_valid, msg = validator.validate_price_freshness(old_timestamp, "AAPL")
        
        assert is_valid is False
        assert "30" in msg  # Should mention the age
        assert "minutes" in msg.lower()
    
    def test_none_timestamp_fails(self):
        """Test that None timestamp fails."""
        validator = DataValidator(max_data_age_minutes=15, strict_mode=False)
        
        is_valid, msg = validator.validate_price_freshness(None, "TEST")
        
        assert is_valid is False
        assert "UNKNOWN" in msg


class TestMarketHoursValidation:
    """Test market hours detection."""
    
    def test_market_open_weekday(self):
        """Test market is detected as open during trading hours."""
        validator = DataValidator()
        
        # Wednesday at 10:30 AM
        trading_time = datetime(2024, 12, 18, 10, 30)  # Wednesday
        status = validator.get_market_status(trading_time)
        
        assert status == MarketStatus.OPEN
    
    def test_market_closed_weekend(self):
        """Test market is detected as closed on weekend."""
        validator = DataValidator()
        
        # Saturday
        weekend_time = datetime(2024, 12, 21, 12, 0)  # Saturday
        status = validator.get_market_status(weekend_time)
        
        assert status == MarketStatus.WEEKEND
    
    def test_market_closed_after_hours(self):
        """Test market is detected as after hours."""
        validator = DataValidator()
        
        # Wednesday at 6 PM
        after_hours = datetime(2024, 12, 18, 18, 0)
        status = validator.get_market_status(after_hours)
        
        assert status == MarketStatus.AFTER_HOURS
    
    def test_market_pre_market(self):
        """Test pre-market detection."""
        validator = DataValidator()
        
        # Wednesday at 7 AM
        pre_market = datetime(2024, 12, 18, 7, 0)
        status = validator.get_market_status(pre_market)
        
        assert status == MarketStatus.PRE_MARKET
    
    def test_market_warning_when_closed(self):
        """Test that warning is generated when market is closed."""
        validator = DataValidator()
        
        # Manually test with weekend time
        with patch.object(validator, 'get_market_status', return_value=MarketStatus.WEEKEND):
            warning = validator.get_market_status_warning()
        
        assert warning is not None
        assert "CLOSED" in warning
        assert "weekend" in warning.lower()
    
    def test_no_warning_when_open(self):
        """Test that no warning when market is open."""
        validator = DataValidator()
        
        with patch.object(validator, 'get_market_status', return_value=MarketStatus.OPEN):
            warning = validator.get_market_status_warning()
        
        assert warning is None


class TestRiskWarnings:
    """Test risk warning content."""
    
    def test_gap_risk_warning_exists(self):
        """Test that gap risk warning is defined and meaningful."""
        assert "gap_risk" in RISK_WARNINGS
        warning = RISK_WARNINGS["gap_risk"]
        
        assert "gap" in warning.lower()
        assert "stop loss" in warning.lower() or "stop-loss" in warning.lower()
        assert "100%" in warning or "overnight" in warning.lower()
    
    def test_leaps_total_loss_warning(self):
        """Test LEAPS total loss warning."""
        assert "leaps_total_loss" in RISK_WARNINGS
        warning = RISK_WARNINGS["leaps_total_loss"]
        
        assert "100%" in warning
        assert "lose" in warning.lower()
    
    def test_signal_not_advice_warning(self):
        """Test signal disclaimer warning."""
        assert "signal_not_advice" in RISK_WARNINGS
        warning = RISK_WARNINGS["signal_not_advice"]
        
        assert "NOT" in warning
        assert "recommendation" in warning.lower()
        assert "UNVALIDATED" in warning or "unvalidated" in warning.lower()
    
    def test_decision_disclaimer_content(self):
        """Test decision disclaimer has required content."""
        disclaimer = get_decision_disclaimer()
        
        assert "NOT" in disclaimer
        assert "recommendation" in disclaimer.lower()
        assert "100%" in disclaimer
        assert "advisor" in disclaimer.lower()
    
    def test_full_disclaimer_comprehensive(self):
        """Test full disclaimer covers all key points."""
        disclaimer = get_risk_disclaimer_full()
        
        # Should cover key risk points
        assert "EDUCATIONAL" in disclaimer or "educational" in disclaimer
        assert "NOT" in disclaimer
        assert "100%" in disclaimer
        assert "gap" in disclaimer.lower()
        assert "backtest" in disclaimer.lower()
        assert "liability" in disclaimer.lower()


class TestEdgeCases:
    """Test edge cases in validation."""
    
    def test_exactly_at_threshold(self):
        """Test data exactly at freshness threshold."""
        validator = DataValidator(max_data_age_minutes=15, strict_mode=False)
        
        # Data from exactly 15 minutes ago
        threshold_timestamp = datetime.now() - timedelta(minutes=15)
        is_valid, msg = validator.validate_price_freshness(threshold_timestamp, "TEST")
        
        # At exactly threshold should fail (> not >=)
        assert is_valid is False
    
    def test_future_timestamp(self):
        """Test handling of future timestamp (data corruption scenario)."""
        validator = DataValidator(max_data_age_minutes=15, strict_mode=False)
        
        # Timestamp in the future (shouldn't happen but should handle)
        future_timestamp = datetime.now() + timedelta(hours=1)
        is_valid, msg = validator.validate_price_freshness(future_timestamp, "TEST")
        
        # Future timestamp should pass (age is negative)
        assert is_valid is True
    
    def test_very_old_data(self):
        """Test handling of very old data."""
        validator = DataValidator(max_data_age_minutes=15, strict_mode=False)
        
        # Data from a week ago
        old_timestamp = datetime.now() - timedelta(days=7)
        is_valid, msg = validator.validate_price_freshness(old_timestamp, "TEST")
        
        assert is_valid is False
        assert "10080" in msg or "day" in msg.lower()  # Should show large age


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
