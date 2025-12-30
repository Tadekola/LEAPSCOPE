"""
Signal Tracker for LEAPSCOPE.

Tracks GO/WATCH signals and their subsequent outcomes for validation.
This is CRITICAL for building evidence of system effectiveness.

Without tracking, users have no way to know if following signals would be profitable.
"""

import sqlite3
import json
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from pathlib import Path
import uuid


@dataclass
class TrackedSignal:
    """A signal tracked for validation."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str = ""
    signal_type: str = ""  # GO, WATCH, NO_GO
    conviction_score: float = 0.0
    conviction_band: str = ""
    
    # Prices at signal time
    underlying_price_at_signal: float = 0.0
    signal_timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Option details (if GO signal)
    recommended_strike: Optional[float] = None
    recommended_expiry: Optional[str] = None
    option_price_at_signal: Optional[float] = None
    
    # Outcome tracking (filled in later)
    underlying_price_30d: Optional[float] = None
    underlying_price_60d: Optional[float] = None
    underlying_price_90d: Optional[float] = None
    
    underlying_change_30d_pct: Optional[float] = None
    underlying_change_60d_pct: Optional[float] = None
    underlying_change_90d_pct: Optional[float] = None
    
    outcome_updated_at: Optional[datetime] = None
    
    # Validation status
    is_validated: bool = False
    validation_notes: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "signal_type": self.signal_type,
            "conviction_score": self.conviction_score,
            "conviction_band": self.conviction_band,
            "underlying_price_at_signal": self.underlying_price_at_signal,
            "signal_timestamp": self.signal_timestamp.isoformat(),
            "recommended_strike": self.recommended_strike,
            "recommended_expiry": self.recommended_expiry,
            "option_price_at_signal": self.option_price_at_signal,
            "underlying_price_30d": self.underlying_price_30d,
            "underlying_price_60d": self.underlying_price_60d,
            "underlying_price_90d": self.underlying_price_90d,
            "underlying_change_30d_pct": self.underlying_change_30d_pct,
            "underlying_change_60d_pct": self.underlying_change_60d_pct,
            "underlying_change_90d_pct": self.underlying_change_90d_pct,
            "outcome_updated_at": self.outcome_updated_at.isoformat() if self.outcome_updated_at else None,
            "is_validated": self.is_validated,
            "validation_notes": self.validation_notes
        }


class SignalTracker:
    """
    Tracks signals and their outcomes for historical validation.
    
    This is essential for understanding whether the system's signals
    have predictive value. Without this data, users are trading blind.
    """
    
    def __init__(self, db_path: str = "data/signal_tracking.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("LEAPSCOPE.SignalTracker")
        self._init_db()
    
    def _init_db(self):
        """Initialize the signal tracking database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tracked_signals (
                id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                conviction_score REAL,
                conviction_band TEXT,
                underlying_price_at_signal REAL,
                signal_timestamp TEXT,
                recommended_strike REAL,
                recommended_expiry TEXT,
                option_price_at_signal REAL,
                underlying_price_30d REAL,
                underlying_price_60d REAL,
                underlying_price_90d REAL,
                underlying_change_30d_pct REAL,
                underlying_change_60d_pct REAL,
                underlying_change_90d_pct REAL,
                outcome_updated_at TEXT,
                is_validated INTEGER DEFAULT 0,
                validation_notes TEXT
            )
        """)
        
        # Index for efficient queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_signal_type ON tracked_signals(signal_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_symbol ON tracked_signals(symbol)
        """)
        
        conn.commit()
        conn.close()
        self.logger.info("Signal tracking database initialized")
    
    def track_signal(self, scan_result: Dict[str, Any]) -> TrackedSignal:
        """
        Record a signal for future validation.
        
        Call this for every GO and WATCH signal to build a track record.
        """
        conviction = scan_result.get("conviction", {})
        candidates = scan_result.get("details", {}).get("options", {}).get("candidates", [])
        
        # Get top candidate details if available
        top_candidate = candidates[0] if candidates else {}
        
        signal = TrackedSignal(
            symbol=scan_result.get("symbol", ""),
            signal_type=scan_result.get("decision", ""),
            conviction_score=conviction.get("score", 0),
            conviction_band=conviction.get("band", ""),
            underlying_price_at_signal=scan_result.get("current_price", 0),
            signal_timestamp=datetime.utcnow(),
            recommended_strike=top_candidate.get("strike"),
            recommended_expiry=top_candidate.get("expiration"),
            option_price_at_signal=top_candidate.get("mid") or top_candidate.get("ask")
        )
        
        self._save_signal(signal)
        self.logger.info(f"Tracking {signal.signal_type} signal for {signal.symbol}")
        
        return signal
    
    def _save_signal(self, signal: TrackedSignal):
        """Save signal to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO tracked_signals 
            (id, symbol, signal_type, conviction_score, conviction_band,
             underlying_price_at_signal, signal_timestamp, recommended_strike,
             recommended_expiry, option_price_at_signal, underlying_price_30d,
             underlying_price_60d, underlying_price_90d, underlying_change_30d_pct,
             underlying_change_60d_pct, underlying_change_90d_pct, outcome_updated_at,
             is_validated, validation_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            signal.id, signal.symbol, signal.signal_type, signal.conviction_score,
            signal.conviction_band, signal.underlying_price_at_signal,
            signal.signal_timestamp.isoformat(), signal.recommended_strike,
            signal.recommended_expiry, signal.option_price_at_signal,
            signal.underlying_price_30d, signal.underlying_price_60d,
            signal.underlying_price_90d, signal.underlying_change_30d_pct,
            signal.underlying_change_60d_pct, signal.underlying_change_90d_pct,
            signal.outcome_updated_at.isoformat() if signal.outcome_updated_at else None,
            1 if signal.is_validated else 0, signal.validation_notes
        ))
        
        conn.commit()
        conn.close()
    
    def update_outcomes(self, provider_manager) -> int:
        """
        Update outcomes for signals that are old enough.
        
        Should be called periodically to backfill price data.
        Returns number of signals updated.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get signals needing 30-day update
        thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).isoformat()
        sixty_days_ago = (datetime.utcnow() - timedelta(days=60)).isoformat()
        ninety_days_ago = (datetime.utcnow() - timedelta(days=90)).isoformat()
        
        updated_count = 0
        
        # Update 30-day outcomes
        cursor.execute("""
            SELECT * FROM tracked_signals 
            WHERE signal_timestamp <= ? AND underlying_price_30d IS NULL
        """, (thirty_days_ago,))
        
        for row in cursor.fetchall():
            try:
                price, _ = provider_manager.fetch_live_price(row["symbol"])
                if price:
                    change_pct = ((price - row["underlying_price_at_signal"]) / 
                                  row["underlying_price_at_signal"]) * 100
                    
                    cursor.execute("""
                        UPDATE tracked_signals 
                        SET underlying_price_30d = ?, underlying_change_30d_pct = ?,
                            outcome_updated_at = ?
                        WHERE id = ?
                    """, (price, change_pct, datetime.utcnow().isoformat(), row["id"]))
                    updated_count += 1
            except Exception as e:
                self.logger.warning(f"Error updating 30d outcome for {row['symbol']}: {e}")
        
        conn.commit()
        conn.close()
        
        self.logger.info(f"Updated {updated_count} signal outcomes")
        return updated_count
    
    def get_validation_stats(self) -> Dict[str, Any]:
        """
        Get statistics on signal effectiveness.
        
        CRITICAL: These stats should be prominently displayed to users
        so they understand the system's historical performance.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        stats = {
            "total_go_signals": 0,
            "total_watch_signals": 0,
            "go_signals_validated": 0,
            "watch_signals_validated": 0,
            "go_avg_30d_change": None,
            "go_positive_30d_pct": None,
            "watch_avg_30d_change": None,
            "disclaimer": (
                "IMPORTANT: These statistics are based on limited historical data. "
                "Past performance does NOT guarantee future results. "
                "Sample sizes may be too small for statistical significance."
            )
        }
        
        # Count totals
        cursor.execute("SELECT COUNT(*) FROM tracked_signals WHERE signal_type = 'GO'")
        stats["total_go_signals"] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM tracked_signals WHERE signal_type = 'WATCH'")
        stats["total_watch_signals"] = cursor.fetchone()[0]
        
        # Count validated (have 30d data)
        cursor.execute("""
            SELECT COUNT(*) FROM tracked_signals 
            WHERE signal_type = 'GO' AND underlying_price_30d IS NOT NULL
        """)
        stats["go_signals_validated"] = cursor.fetchone()[0]
        
        # Calculate GO signal stats
        if stats["go_signals_validated"] > 0:
            cursor.execute("""
                SELECT AVG(underlying_change_30d_pct) FROM tracked_signals 
                WHERE signal_type = 'GO' AND underlying_change_30d_pct IS NOT NULL
            """)
            result = cursor.fetchone()[0]
            stats["go_avg_30d_change"] = round(result, 2) if result else None
            
            cursor.execute("""
                SELECT COUNT(*) FROM tracked_signals 
                WHERE signal_type = 'GO' AND underlying_change_30d_pct > 0
            """)
            positive_count = cursor.fetchone()[0]
            stats["go_positive_30d_pct"] = round(
                (positive_count / stats["go_signals_validated"]) * 100, 1
            )
        
        conn.close()
        
        # Add validation status
        if stats["go_signals_validated"] < 30:
            stats["validation_status"] = "INSUFFICIENT_DATA"
            stats["validation_message"] = (
                f"Only {stats['go_signals_validated']} GO signals have been validated. "
                "At least 30 are recommended for meaningful statistics."
            )
        else:
            stats["validation_status"] = "PRELIMINARY"
            stats["validation_message"] = (
                "Statistics are preliminary. Continue tracking for more reliable results."
            )
        
        return stats
    
    def get_recent_signals(self, signal_type: str = None, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent tracked signals."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if signal_type:
            cursor.execute("""
                SELECT * FROM tracked_signals 
                WHERE signal_type = ?
                ORDER BY signal_timestamp DESC LIMIT ?
            """, (signal_type, limit))
        else:
            cursor.execute("""
                SELECT * FROM tracked_signals 
                ORDER BY signal_timestamp DESC LIMIT ?
            """, (limit,))
        
        signals = []
        for row in cursor.fetchall():
            signals.append(dict(row))
        
        conn.close()
        return signals
