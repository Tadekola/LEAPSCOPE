"""
Tests for LEAPSCOPE Phase 9 Features.

Tests for:
1. Conviction score calculation
2. Alert triggering logic  
3. Scan comparison logic
"""

import pytest
import sys
import os
from datetime import datetime
from unittest.mock import Mock, patch

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.scoring.conviction import ConvictionScorer, ConvictionBand, ConvictionResult
from src.alerts.manager import AlertManager, Alert, AlertType, AlertSeverity
from src.history.scan_history import ScanHistory, ScanComparison


class TestConvictionScoring:
    """Test conviction score calculation."""
    
    def test_conviction_score_strong(self):
        """Test STRONG conviction band for high-quality result."""
        scorer = ConvictionScorer({
            "conviction_scoring": {
                "weight_technical": 0.30,
                "weight_fundamental": 0.25,
                "weight_volatility": 0.25,
                "weight_liquidity": 0.20,
                "strong_threshold": 75,
                "moderate_threshold": 50
            }
        })
        
        # High-quality scan result
        result = {
            "symbol": "AAPL",
            "asset_type": "STOCK",
            "decision": "GO",
            "details": {
                "technical": {
                    "trend": "BULLISH",
                    "indicators": {"rsi": 55},
                    "signals": {"golden_cross": True, "death_cross": False}
                },
                "fundamentals": {
                    "overall_score": 85,
                    "confidence": "HIGH"
                },
                "options": {
                    "candidates": [
                        {"iv": 0.25, "oi": 5000, "bid": 10.0, "ask": 10.20}
                    ]
                }
            }
        }
        
        conviction = scorer.score(result)
        
        assert conviction.score >= 75
        assert conviction.band == ConvictionBand.STRONG
        assert "technical" in conviction.components
        assert "fundamental" in conviction.components
    
    def test_conviction_score_weak(self):
        """Test WEAK conviction band for poor result."""
        scorer = ConvictionScorer({})
        
        # Poor scan result
        result = {
            "symbol": "XYZ",
            "asset_type": "STOCK",
            "decision": "WATCH",
            "details": {
                "technical": {
                    "trend": "BEARISH",
                    "indicators": {"rsi": 75},
                    "signals": {"golden_cross": False, "death_cross": True}
                },
                "fundamentals": {
                    "overall_score": 40,
                    "confidence": "LOW"
                },
                "options": {
                    "candidates": []
                }
            }
        }
        
        conviction = scorer.score(result)
        
        assert conviction.score < 50
        assert conviction.band == ConvictionBand.WEAK
    
    def test_conviction_score_etf_handling(self):
        """Test ETF gets proxy fundamental score (no penalty)."""
        scorer = ConvictionScorer({
            "conviction_scoring": {
                "etf_fundamental_score": 70
            }
        })
        
        result = {
            "symbol": "SPY",
            "asset_type": "ETF",
            "decision": "GO",
            "details": {
                "technical": {
                    "trend": "BULLISH",
                    "indicators": {"rsi": 50},
                    "signals": {}
                },
                "fundamentals": {
                    "overall_score": 70,  # ETF bypass score
                    "confidence": "MEDIUM"
                },
                "options": {
                    "candidates": [
                        {"iv": 0.15, "oi": 10000, "bid": 5.0, "ask": 5.10}
                    ]
                }
            }
        }
        
        conviction = scorer.score(result)
        
        # ETF should get proxy score of 70
        assert conviction.components["fundamental"] == 70
        assert "ETF" in " ".join(conviction.notes)
    
    def test_conviction_batch_sorting(self):
        """Test batch scoring sorts by conviction descending."""
        scorer = ConvictionScorer({})
        
        results = [
            {
                "symbol": "LOW",
                "asset_type": "STOCK",
                "decision": "WATCH",
                "details": {
                    "technical": {"trend": "BEARISH", "indicators": {}, "signals": {}},
                    "fundamentals": {"overall_score": 30, "confidence": "LOW"},
                    "options": {"candidates": []}
                }
            },
            {
                "symbol": "HIGH",
                "asset_type": "STOCK", 
                "decision": "GO",
                "details": {
                    "technical": {"trend": "BULLISH", "indicators": {"rsi": 50}, "signals": {}},
                    "fundamentals": {"overall_score": 90, "confidence": "HIGH"},
                    "options": {"candidates": [{"iv": 0.2, "oi": 5000, "bid": 10, "ask": 10.1}]}
                }
            }
        ]
        
        scored = scorer.score_batch(results)
        
        # HIGH should be first (higher conviction)
        assert scored[0]["symbol"] == "HIGH"
        assert scored[1]["symbol"] == "LOW"
        assert scored[0]["conviction"]["score"] > scored[1]["conviction"]["score"]


class TestAlertTriggering:
    """Test alert triggering logic."""
    
    def setup_method(self):
        """Setup test alert manager with temp db."""
        import tempfile
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.alert_mgr = AlertManager(db_path=self.temp_db.name, config={"alerts": {"console_output": False}})
    
    def teardown_method(self):
        """Cleanup temp db."""
        import os
        try:
            os.unlink(self.temp_db.name)
        except:
            pass
    
    def test_alert_new_go_signal(self):
        """Test alert creation for new GO signal."""
        alert = self.alert_mgr.alert_new_go_signal(
            symbol="AAPL",
            conviction_score=82.5,
            reasons=["Strong fundamentals", "Bullish trend"]
        )
        
        assert alert.alert_type == AlertType.NEW_GO_SIGNAL
        assert alert.symbol == "AAPL"
        assert alert.severity == AlertSeverity.INFO
        assert "82" in alert.message
    
    def test_alert_portfolio_stop_loss(self):
        """Test STOP_LOSS alert creation."""
        alert = self.alert_mgr.alert_portfolio_signal(
            symbol="MSFT",
            signal_type="STOP_LOSS",
            severity=AlertSeverity.CRITICAL,
            message="Position down 35%",
            data={"pnl_pct": -35}
        )
        
        assert alert.alert_type == AlertType.STOP_LOSS
        assert alert.severity == AlertSeverity.CRITICAL
        assert alert.symbol == "MSFT"
    
    def test_alert_persistence(self):
        """Test alerts are persisted to database."""
        # Create an alert
        self.alert_mgr.alert_new_go_signal("TEST", 75, ["reason1"])
        
        # Retrieve alerts
        alerts = self.alert_mgr.get_alerts(limit=10)
        
        assert len(alerts) >= 1
        assert any(a.symbol == "TEST" for a in alerts)
    
    def test_alert_acknowledge(self):
        """Test alert acknowledgment."""
        alert = self.alert_mgr.alert_new_go_signal("ACK_TEST", 80, [])
        
        assert not alert.acknowledged
        
        # Acknowledge
        result = self.alert_mgr.acknowledge_alert(alert.id)
        
        assert result is True
        
        # Verify acknowledged
        alerts = self.alert_mgr.get_alerts(unacknowledged_only=True)
        assert not any(a.id == alert.id for a in alerts)
    
    def test_unacknowledged_count(self):
        """Test unacknowledged alert counting."""
        # Create alerts of different severities
        self.alert_mgr.create_alert(Alert(
            alert_type=AlertType.NEW_GO_SIGNAL,
            severity=AlertSeverity.INFO,
            symbol="INFO_TEST",
            title="Test",
            message="Test"
        ))
        self.alert_mgr.create_alert(Alert(
            alert_type=AlertType.STOP_LOSS,
            severity=AlertSeverity.CRITICAL,
            symbol="CRIT_TEST",
            title="Test",
            message="Test"
        ))
        
        counts = self.alert_mgr.get_unacknowledged_count()
        
        assert counts["INFO"] >= 1
        assert counts["CRITICAL"] >= 1


class TestScanComparison:
    """Test scan comparison logic."""
    
    def setup_method(self):
        """Setup test scan history with temp db."""
        import tempfile
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.history = ScanHistory(db_path=self.temp_db.name)
    
    def teardown_method(self):
        """Cleanup temp db."""
        import os
        try:
            os.unlink(self.temp_db.name)
        except:
            pass
    
    def test_save_and_retrieve_scan(self):
        """Test saving and retrieving a scan."""
        results = [
            {"symbol": "AAPL", "decision": "GO"},
            {"symbol": "MSFT", "decision": "WATCH"}
        ]
        
        scan_id = self.history.save_scan(results)
        
        assert scan_id is not None
        
        # Retrieve
        scan = self.history.get_scan(scan_id)
        
        assert scan is not None
        assert scan.symbol_count == 2
        assert scan.go_count == 1
        assert scan.watch_count == 1
    
    def test_scan_comparison_new_go(self):
        """Test comparison identifies new GO signals."""
        # First scan - no GO
        results1 = [
            {"symbol": "AAPL", "decision": "WATCH"},
            {"symbol": "MSFT", "decision": "WATCH"}
        ]
        scan1_id = self.history.save_scan(results1)
        
        # Second scan - AAPL upgrades to GO
        results2 = [
            {"symbol": "AAPL", "decision": "GO"},
            {"symbol": "MSFT", "decision": "WATCH"}
        ]
        scan2_id = self.history.save_scan(results2)
        
        # Compare
        comparison = self.history.compare_scans(scan2_id, scan1_id)
        
        assert comparison is not None
        assert "AAPL" in comparison.new_go_signals
        assert len(comparison.upgraded_signals) >= 1
    
    def test_scan_comparison_downgrade(self):
        """Test comparison identifies downgraded signals."""
        # First scan - GO signal
        results1 = [
            {"symbol": "TSLA", "decision": "GO"}
        ]
        scan1_id = self.history.save_scan(results1)
        
        # Second scan - downgraded to WATCH
        results2 = [
            {"symbol": "TSLA", "decision": "WATCH"}
        ]
        scan2_id = self.history.save_scan(results2)
        
        # Compare
        comparison = self.history.compare_scans(scan2_id, scan1_id)
        
        assert comparison is not None
        assert len(comparison.downgraded_signals) >= 1
        assert comparison.downgraded_signals[0]["symbol"] == "TSLA"
        assert comparison.downgraded_signals[0]["from"] == "GO"
        assert comparison.downgraded_signals[0]["to"] == "WATCH"
    
    def test_scan_comparison_dropped_symbol(self):
        """Test comparison identifies dropped symbols."""
        # First scan
        results1 = [
            {"symbol": "AAPL", "decision": "GO"},
            {"symbol": "NVDA", "decision": "WATCH"}
        ]
        scan1_id = self.history.save_scan(results1)
        
        # Second scan - NVDA dropped
        results2 = [
            {"symbol": "AAPL", "decision": "GO"}
        ]
        scan2_id = self.history.save_scan(results2)
        
        # Compare
        comparison = self.history.compare_scans(scan2_id, scan1_id)
        
        assert "NVDA" in comparison.dropped_symbols
    
    def test_recent_scans(self):
        """Test getting recent scans."""
        # Save multiple scans
        for i in range(5):
            self.history.save_scan([{"symbol": f"TEST{i}", "decision": "GO"}])
        
        recent = self.history.get_recent_scans(limit=3)
        
        assert len(recent) == 3


class TestDraftOrderTicket:
    """Test DraftOrderTicket model (no execution)."""
    
    def test_ticket_creation(self):
        """Test draft ticket creation from scan result."""
        from src.orders.ticket import DraftOrderTicket, OrderSide
        
        scan_result = {
            "symbol": "AAPL",
            "asset_type": "STOCK",
            "decision": "GO",
            "conviction": {"score": 82, "band": "STRONG"},
            "reasons": ["Strong fundamentals", "Bullish trend"],
            "details": {
                "options": {
                    "candidates": [
                        {
                            "contract_symbol": "AAPL251219C00200000",
                            "expiration": "2025-12-19",
                            "strike": 200,
                            "type": "CALL",
                            "bid": 25.0,
                            "ask": 25.50,
                            "last": 25.25
                        }
                    ]
                }
            }
        }
        
        ticket = DraftOrderTicket.from_scan_result(scan_result)
        
        assert ticket is not None
        assert ticket.symbol == "AAPL"
        assert ticket.strike == 200
        assert ticket.option_type == "CALL"
        assert ticket.side == OrderSide.BUY_TO_OPEN
        assert ticket.status == "DRAFT"
        assert ticket._execution_blocked is True
    
    def test_ticket_no_execution(self):
        """Verify ticket cannot execute (safety check)."""
        from src.orders.ticket import DraftOrderTicket
        
        ticket = DraftOrderTicket(
            symbol="TEST",
            strike=100,
            quantity=1
        )
        
        # Verify execution is blocked
        assert ticket._execution_blocked is True
        assert ticket.status == "DRAFT"
        
        # Verify no execute method exists
        assert not hasattr(ticket, 'execute')
        assert not hasattr(ticket, 'submit')
    
    def test_ticket_display_string(self):
        """Test ticket display formatting."""
        from src.orders.ticket import DraftOrderTicket
        
        ticket = DraftOrderTicket(
            symbol="MSFT",
            option_symbol="MSFT251219C00400000",
            strike=400,
            option_type="CALL",
            expiry="2025-12-19",
            quantity=2,
            limit_price=15.50,
            rationale="GO signal with STRONG conviction"
        )
        
        display = ticket.to_display_string()
        
        assert "DRAFT" in display
        assert "MSFT" in display
        assert "400" in display
        assert "NO EXECUTION" in display


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
