"""
Scan History Module for LEAPSCOPE Phase 9.

Persists scan results for historical comparison and audit trail.
"""

import sqlite3
import json
import hashlib
import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from pathlib import Path


@dataclass
class ScanRecord:
    """A historical scan record."""
    id: str
    timestamp: datetime
    config_hash: str
    symbol_count: int
    go_count: int
    watch_count: int
    results: List[Dict[str, Any]]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "config_hash": self.config_hash,
            "symbol_count": self.symbol_count,
            "go_count": self.go_count,
            "watch_count": self.watch_count,
            "results": self.results
        }


@dataclass
class ScanComparison:
    """Comparison between two scans."""
    current_scan_id: str
    previous_scan_id: str
    new_go_signals: List[str]  # Symbols with new GO
    upgraded_signals: List[Dict[str, str]]  # {symbol, from, to}
    downgraded_signals: List[Dict[str, str]]  # {symbol, from, to}
    dropped_symbols: List[str]  # Symbols no longer in scan
    new_symbols: List[str]  # New symbols in scan
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_scan_id": self.current_scan_id,
            "previous_scan_id": self.previous_scan_id,
            "new_go_signals": self.new_go_signals,
            "upgraded_signals": self.upgraded_signals,
            "downgraded_signals": self.downgraded_signals,
            "dropped_symbols": self.dropped_symbols,
            "new_symbols": self.new_symbols,
            "summary": {
                "new_go": len(self.new_go_signals),
                "upgrades": len(self.upgraded_signals),
                "downgrades": len(self.downgraded_signals),
                "dropped": len(self.dropped_symbols),
                "new": len(self.new_symbols)
            }
        }


class ScanHistory:
    """
    Manages scan history for comparison and auditability.
    
    Features:
    - Persist scans with config hash
    - Compare current vs previous
    - Track signal changes over time
    """
    
    def __init__(self, db_path: str = "data/scan_history.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("LEAPSCOPE.ScanHistory")
        self._init_db()
    
    def _init_db(self):
        """Initialize scan history database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scans (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                config_hash TEXT,
                symbol_count INTEGER,
                go_count INTEGER,
                watch_count INTEGER,
                results TEXT
            )
        """)
        
        # Index for efficient timestamp queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_scans_timestamp 
            ON scans(timestamp DESC)
        """)
        
        conn.commit()
        conn.close()
        self.logger.info("Scan history database initialized")
    
    def save_scan(self, results: List[Dict[str, Any]], config: Dict[str, Any] = None) -> str:
        """
        Save a scan to history.
        
        Args:
            results: List of scan results
            config: Optional config dict for hashing
            
        Returns:
            Scan ID
        """
        import uuid
        timestamp = datetime.utcnow()
        scan_id = f"{timestamp.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        config_hash = self._hash_config(config) if config else ""
        
        go_count = len([r for r in results if r.get("decision") == "GO"])
        watch_count = len([r for r in results if r.get("decision") == "WATCH"])
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO scans (id, timestamp, config_hash, symbol_count, go_count, watch_count, results)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            scan_id,
            timestamp.isoformat(),
            config_hash,
            len(results),
            go_count,
            watch_count,
            json.dumps(results, default=str)
        ))
        
        conn.commit()
        conn.close()
        
        self.logger.info(f"Saved scan {scan_id}: {len(results)} results, {go_count} GO, {watch_count} WATCH")
        return scan_id
    
    def get_scan(self, scan_id: str) -> Optional[ScanRecord]:
        """Get a specific scan by ID."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM scans WHERE id = ?", (scan_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return self._row_to_record(row)
    
    def get_recent_scans(self, limit: int = 10) -> List[ScanRecord]:
        """Get recent scans (without full results for efficiency)."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, timestamp, config_hash, symbol_count, go_count, watch_count
            FROM scans
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        records = []
        for row in rows:
            records.append(ScanRecord(
                id=row["id"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                config_hash=row["config_hash"],
                symbol_count=row["symbol_count"],
                go_count=row["go_count"],
                watch_count=row["watch_count"],
                results=[]  # Not loaded for efficiency
            ))
        
        return records
    
    def get_latest_scan(self) -> Optional[ScanRecord]:
        """Get the most recent scan."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM scans
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return self._row_to_record(row)
    
    def get_previous_scan(self, before_id: str = None) -> Optional[ScanRecord]:
        """Get the scan before a given scan (or second most recent)."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if before_id:
            cursor.execute("""
                SELECT * FROM scans
                WHERE timestamp < (SELECT timestamp FROM scans WHERE id = ?)
                ORDER BY timestamp DESC
                LIMIT 1
            """, (before_id,))
        else:
            cursor.execute("""
                SELECT * FROM scans
                ORDER BY timestamp DESC
                LIMIT 1 OFFSET 1
            """)
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return self._row_to_record(row)
    
    def compare_scans(self, current_id: str, previous_id: str = None) -> Optional[ScanComparison]:
        """
        Compare two scans to identify changes.
        
        Args:
            current_id: ID of current scan
            previous_id: ID of previous scan (auto-detect if None)
            
        Returns:
            ScanComparison with changes identified
        """
        current = self.get_scan(current_id)
        if not current:
            return None
        
        if previous_id:
            previous = self.get_scan(previous_id)
        else:
            previous = self.get_previous_scan(current_id)
        
        if not previous:
            # No previous scan to compare
            return ScanComparison(
                current_scan_id=current_id,
                previous_scan_id="",
                new_go_signals=[r["symbol"] for r in current.results if r.get("decision") == "GO"],
                upgraded_signals=[],
                downgraded_signals=[],
                dropped_symbols=[],
                new_symbols=[r["symbol"] for r in current.results]
            )
        
        # Build lookup maps
        current_map = {r["symbol"]: r for r in current.results}
        previous_map = {r["symbol"]: r for r in previous.results}
        
        new_go = []
        upgraded = []
        downgraded = []
        dropped = []
        new_symbols = []
        
        # Check current results
        for symbol, result in current_map.items():
            current_decision = result.get("decision")
            
            if symbol not in previous_map:
                new_symbols.append(symbol)
                if current_decision == "GO":
                    new_go.append(symbol)
            else:
                previous_decision = previous_map[symbol].get("decision")
                
                if current_decision == "GO" and previous_decision != "GO":
                    new_go.append(symbol)
                    upgraded.append({"symbol": symbol, "from": previous_decision, "to": current_decision})
                elif current_decision == "WATCH" and previous_decision == "NO_GO":
                    upgraded.append({"symbol": symbol, "from": previous_decision, "to": current_decision})
                elif current_decision == "NO_GO" and previous_decision in ["GO", "WATCH"]:
                    downgraded.append({"symbol": symbol, "from": previous_decision, "to": current_decision})
                elif current_decision == "WATCH" and previous_decision == "GO":
                    downgraded.append({"symbol": symbol, "from": previous_decision, "to": current_decision})
        
        # Check for dropped symbols
        for symbol in previous_map:
            if symbol not in current_map:
                dropped.append(symbol)
        
        return ScanComparison(
            current_scan_id=current_id,
            previous_scan_id=previous.id,
            new_go_signals=new_go,
            upgraded_signals=upgraded,
            downgraded_signals=downgraded,
            dropped_symbols=dropped,
            new_symbols=new_symbols
        )
    
    def _row_to_record(self, row) -> ScanRecord:
        """Convert database row to ScanRecord."""
        return ScanRecord(
            id=row["id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            config_hash=row["config_hash"],
            symbol_count=row["symbol_count"],
            go_count=row["go_count"],
            watch_count=row["watch_count"],
            results=json.loads(row["results"]) if row["results"] else []
        )
    
    def _hash_config(self, config: Dict[str, Any]) -> str:
        """Create hash of config for comparison."""
        # Only hash relevant config sections
        relevant = {
            "decision": config.get("decision", {}),
            "options": config.get("options", {}),
            "fundamentals": config.get("fundamentals", {}),
            "technical_analysis": config.get("technical_analysis", {})
        }
        config_str = json.dumps(relevant, sort_keys=True)
        return hashlib.md5(config_str.encode()).hexdigest()[:8]
    
    def cleanup_old_scans(self, keep_days: int = 30) -> int:
        """Remove scans older than specified days."""
        from datetime import timedelta
        cutoff = (datetime.utcnow() - timedelta(days=keep_days)).isoformat()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM scans WHERE timestamp < ?", (cutoff,))
        deleted = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        self.logger.info(f"Cleaned up {deleted} old scans")
        return deleted
