"""
Alert Manager for LEAPSCOPE Phase 9.

Non-executing alert system for scanner and portfolio events.
Supports persistence and optional webhook abstraction.
"""

import sqlite3
import json
import logging
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable
from pathlib import Path
import uuid


class AlertType(str, Enum):
    """Types of alerts."""
    # Scanner alerts
    NEW_GO_SIGNAL = "NEW_GO_SIGNAL"
    CONVICTION_THRESHOLD = "CONVICTION_THRESHOLD"
    SIGNAL_UPGRADE = "SIGNAL_UPGRADE"
    
    # Portfolio alerts
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    TECH_INVALIDATED = "TECH_INVALIDATED"
    EXPIRY_REVIEW = "EXPIRY_REVIEW"
    EARNINGS_RISK = "EARNINGS_RISK"


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "INFO"
    WARN = "WARN"
    CRITICAL = "CRITICAL"


@dataclass
class Alert:
    """An alert record."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    alert_type: AlertType = AlertType.NEW_GO_SIGNAL
    severity: AlertSeverity = AlertSeverity.INFO
    symbol: str = ""
    title: str = ""
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    acknowledged: bool = False
    acknowledged_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "symbol": self.symbol,
            "title": self.title,
            "message": self.message,
            "data": self.data,
            "created_at": self.created_at.isoformat(),
            "acknowledged": self.acknowledged,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Alert":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            alert_type=AlertType(data["alert_type"]),
            severity=AlertSeverity(data["severity"]),
            symbol=data.get("symbol", ""),
            title=data.get("title", ""),
            message=data.get("message", ""),
            data=data.get("data", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.utcnow(),
            acknowledged=data.get("acknowledged", False),
            acknowledged_at=datetime.fromisoformat(data["acknowledged_at"]) if data.get("acknowledged_at") else None
        )


class AlertManager:
    """
    Manages alerts for scanner and portfolio events.
    
    Features:
    - SQLite persistence
    - Console output
    - Optional webhook abstraction (for future extensions)
    - Alert acknowledgment
    """
    
    def __init__(self, db_path: str = "data/alerts.db", config: Dict[str, Any] = None):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.config = config or {}
        self.logger = logging.getLogger("LEAPSCOPE.AlertManager")
        
        # Webhook handlers (for future extension)
        self._webhook_handlers: List[Callable[[Alert], None]] = []
        
        # Config
        alert_config = self.config.get("alerts", {})
        self.console_output = alert_config.get("console_output", True)
        self.conviction_threshold = alert_config.get("conviction_threshold", 75)
        
        self._init_db()
        self.logger.info("AlertManager initialized")
    
    def _init_db(self):
        """Initialize alerts database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id TEXT PRIMARY KEY,
                alert_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                symbol TEXT,
                title TEXT,
                message TEXT,
                data TEXT,
                created_at TEXT,
                acknowledged INTEGER DEFAULT 0,
                acknowledged_at TEXT
            )
        """)
        
        conn.commit()
        conn.close()
    
    def create_alert(self, alert: Alert) -> Alert:
        """Create and persist a new alert."""
        # Save to database
        self._save_alert(alert)
        
        # Console output
        if self.console_output:
            self._print_alert(alert)
        
        # Call webhook handlers
        for handler in self._webhook_handlers:
            try:
                handler(alert)
            except Exception as e:
                self.logger.error(f"Webhook handler error: {e}")
        
        return alert
    
    def _save_alert(self, alert: Alert):
        """Save alert to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO alerts (id, alert_type, severity, symbol, title, message, data, created_at, acknowledged, acknowledged_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            alert.id,
            alert.alert_type.value,
            alert.severity.value,
            alert.symbol,
            alert.title,
            alert.message,
            json.dumps(alert.data),
            alert.created_at.isoformat(),
            1 if alert.acknowledged else 0,
            alert.acknowledged_at.isoformat() if alert.acknowledged_at else None
        ))
        
        conn.commit()
        conn.close()
    
    def _print_alert(self, alert: Alert):
        """Print alert to console."""
        severity_emoji = {
            AlertSeverity.INFO: "ℹ️",
            AlertSeverity.WARN: "⚠️",
            AlertSeverity.CRITICAL: "🚨"
        }
        
        emoji = severity_emoji.get(alert.severity, "📢")
        print(f"\n{emoji} [{alert.severity.value}] {alert.title}")
        print(f"   Symbol: {alert.symbol}")
        print(f"   {alert.message}")
        print(f"   Time: {alert.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    
    def get_alerts(self, 
                   limit: int = 50, 
                   unacknowledged_only: bool = False,
                   alert_type: Optional[AlertType] = None,
                   severity: Optional[AlertSeverity] = None) -> List[Alert]:
        """Get alerts with optional filtering."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = "SELECT * FROM alerts WHERE 1=1"
        params = []
        
        if unacknowledged_only:
            query += " AND acknowledged = 0"
        
        if alert_type:
            query += " AND alert_type = ?"
            params.append(alert_type.value)
        
        if severity:
            query += " AND severity = ?"
            params.append(severity.value)
        
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        alerts = []
        for row in rows:
            alerts.append(Alert(
                id=row["id"],
                alert_type=AlertType(row["alert_type"]),
                severity=AlertSeverity(row["severity"]),
                symbol=row["symbol"],
                title=row["title"],
                message=row["message"],
                data=json.loads(row["data"]) if row["data"] else {},
                created_at=datetime.fromisoformat(row["created_at"]),
                acknowledged=bool(row["acknowledged"]),
                acknowledged_at=datetime.fromisoformat(row["acknowledged_at"]) if row["acknowledged_at"] else None
            ))
        
        return alerts
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """Mark an alert as acknowledged."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE alerts 
            SET acknowledged = 1, acknowledged_at = ?
            WHERE id = ?
        """, (datetime.utcnow().isoformat(), alert_id))
        
        conn.commit()
        updated = cursor.rowcount > 0
        conn.close()
        
        return updated
    
    def acknowledge_all(self) -> int:
        """Acknowledge all unacknowledged alerts."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE alerts 
            SET acknowledged = 1, acknowledged_at = ?
            WHERE acknowledged = 0
        """, (datetime.utcnow().isoformat(),))
        
        count = cursor.rowcount
        conn.commit()
        conn.close()
        
        return count
    
    def get_unacknowledged_count(self) -> Dict[str, int]:
        """Get count of unacknowledged alerts by severity."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT severity, COUNT(*) as count
            FROM alerts
            WHERE acknowledged = 0
            GROUP BY severity
        """)
        
        results = {s.value: 0 for s in AlertSeverity}
        for row in cursor.fetchall():
            results[row[0]] = row[1]
        
        conn.close()
        return results
    
    def register_webhook(self, handler: Callable[[Alert], None]):
        """Register a webhook handler for alerts."""
        self._webhook_handlers.append(handler)
    
    # Alert creation helpers
    
    def alert_new_go_signal(self, symbol: str, conviction_score: float, reasons: List[str]):
        """Create alert for new GO signal."""
        return self.create_alert(Alert(
            alert_type=AlertType.NEW_GO_SIGNAL,
            severity=AlertSeverity.INFO,
            symbol=symbol,
            title=f"New GO Signal: {symbol}",
            message=f"Scanner detected GO signal with conviction {conviction_score:.0f}",
            data={"conviction_score": conviction_score, "reasons": reasons}
        ))
    
    def alert_conviction_threshold(self, symbol: str, score: float, previous_score: float):
        """Create alert for conviction score crossing threshold."""
        direction = "above" if score >= self.conviction_threshold else "below"
        return self.create_alert(Alert(
            alert_type=AlertType.CONVICTION_THRESHOLD,
            severity=AlertSeverity.INFO,
            symbol=symbol,
            title=f"Conviction Threshold: {symbol}",
            message=f"Conviction score moved {direction} threshold ({previous_score:.0f} → {score:.0f})",
            data={"current_score": score, "previous_score": previous_score, "threshold": self.conviction_threshold}
        ))
    
    def alert_signal_upgrade(self, symbol: str, old_signal: str, new_signal: str):
        """Create alert for signal upgrade (e.g., WATCH → GO)."""
        return self.create_alert(Alert(
            alert_type=AlertType.SIGNAL_UPGRADE,
            severity=AlertSeverity.INFO,
            symbol=symbol,
            title=f"Signal Upgrade: {symbol}",
            message=f"Signal upgraded from {old_signal} to {new_signal}",
            data={"old_signal": old_signal, "new_signal": new_signal}
        ))
    
    def alert_portfolio_signal(self, symbol: str, signal_type: str, severity: AlertSeverity, 
                                message: str, data: Dict[str, Any] = None):
        """Create alert for portfolio management signal."""
        alert_type_map = {
            "STOP_LOSS": AlertType.STOP_LOSS,
            "TAKE_PROFIT": AlertType.TAKE_PROFIT,
            "TECH_INVALIDATED": AlertType.TECH_INVALIDATED,
            "EXPIRY_REVIEW": AlertType.EXPIRY_REVIEW,
            "EARNINGS_RISK": AlertType.EARNINGS_RISK
        }
        
        alert_type = alert_type_map.get(signal_type, AlertType.EXPIRY_REVIEW)
        
        return self.create_alert(Alert(
            alert_type=alert_type,
            severity=severity,
            symbol=symbol,
            title=f"Portfolio Alert: {symbol} - {signal_type}",
            message=message,
            data=data or {}
        ))
    
    def get_summary(self) -> Dict[str, Any]:
        """Get alert summary statistics."""
        unack = self.get_unacknowledged_count()
        recent = self.get_alerts(limit=5)
        
        return {
            "unacknowledged": unack,
            "total_unacknowledged": sum(unack.values()),
            "recent_alerts": [a.to_dict() for a in recent]
        }
