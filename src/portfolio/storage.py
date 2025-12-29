"""
Portfolio Storage for LEAPSCOPE Phase 8.

SQLite-based persistence for positions with JSON import/export support.
"""

import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any

from src.portfolio.models import Position, PositionStatus, OptionType


class PortfolioStorage:
    """
    SQLite storage for portfolio positions.
    
    Features:
    - Automatic table creation
    - CRUD operations for positions
    - JSON import/export for portability
    """
    
    def __init__(self, db_path: str = "data/portfolio.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("LEAPSCOPE.Portfolio.Storage")
        self._init_db()
    
    def _init_db(self):
        """Initialize database with positions table."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                asset_type TEXT DEFAULT 'STOCK',
                option_type TEXT NOT NULL,
                expiry TEXT NOT NULL,
                strike REAL NOT NULL,
                contracts INTEGER NOT NULL,
                entry_date TEXT NOT NULL,
                entry_price REAL NOT NULL,
                underlying_entry_price REAL,
                status TEXT DEFAULT 'OPEN',
                notes TEXT,
                tags TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        
        conn.commit()
        conn.close()
        self.logger.info(f"Portfolio database initialized at {self.db_path}")
    
    def add_position(self, position: Position) -> bool:
        """Add a new position to the database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            now = datetime.utcnow().isoformat()
            tags_json = json.dumps(position.tags) if position.tags else "[]"
            
            cursor.execute("""
                INSERT INTO positions 
                (id, symbol, asset_type, option_type, expiry, strike, contracts,
                 entry_date, entry_price, underlying_entry_price, status, notes, tags,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                position.id,
                position.symbol,
                position.asset_type,
                position.option_type.value if isinstance(position.option_type, OptionType) else position.option_type,
                position.expiry,
                position.strike,
                position.contracts,
                position.entry_date,
                position.entry_price,
                position.underlying_entry_price,
                position.status.value if isinstance(position.status, PositionStatus) else position.status,
                position.notes,
                tags_json,
                now,
                now
            ))
            
            conn.commit()
            conn.close()
            self.logger.info(f"Added position {position.id} for {position.symbol}")
            return True
            
        except sqlite3.IntegrityError as e:
            self.logger.error(f"Position {position.id} already exists: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Error adding position: {e}")
            return False
    
    def update_position(self, position: Position) -> bool:
        """Update an existing position."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            now = datetime.utcnow().isoformat()
            tags_json = json.dumps(position.tags) if position.tags else "[]"
            
            cursor.execute("""
                UPDATE positions SET
                    symbol = ?,
                    asset_type = ?,
                    option_type = ?,
                    expiry = ?,
                    strike = ?,
                    contracts = ?,
                    entry_date = ?,
                    entry_price = ?,
                    underlying_entry_price = ?,
                    status = ?,
                    notes = ?,
                    tags = ?,
                    updated_at = ?
                WHERE id = ?
            """, (
                position.symbol,
                position.asset_type,
                position.option_type.value if isinstance(position.option_type, OptionType) else position.option_type,
                position.expiry,
                position.strike,
                position.contracts,
                position.entry_date,
                position.entry_price,
                position.underlying_entry_price,
                position.status.value if isinstance(position.status, PositionStatus) else position.status,
                position.notes,
                tags_json,
                now,
                position.id
            ))
            
            conn.commit()
            conn.close()
            self.logger.info(f"Updated position {position.id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error updating position: {e}")
            return False
    
    def get_position(self, position_id: str) -> Optional[Position]:
        """Get a single position by ID."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM positions WHERE id = ?", (position_id,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return self._row_to_position(dict(row))
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting position: {e}")
            return None
    
    def get_all_positions(self, status: Optional[PositionStatus] = None) -> List[Position]:
        """Get all positions, optionally filtered by status."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if status:
                cursor.execute(
                    "SELECT * FROM positions WHERE status = ? ORDER BY entry_date DESC",
                    (status.value,)
                )
            else:
                cursor.execute("SELECT * FROM positions ORDER BY entry_date DESC")
            
            rows = cursor.fetchall()
            conn.close()
            
            return [self._row_to_position(dict(row)) for row in rows]
            
        except Exception as e:
            self.logger.error(f"Error getting positions: {e}")
            return []
    
    def get_open_positions(self) -> List[Position]:
        """Get all OPEN positions."""
        return self.get_all_positions(status=PositionStatus.OPEN)
    
    def close_position(self, position_id: str, notes: str = "") -> bool:
        """Mark a position as CLOSED."""
        position = self.get_position(position_id)
        if position:
            position.status = PositionStatus.CLOSED
            if notes:
                position.notes = f"{position.notes}\n[CLOSED] {notes}".strip()
            return self.update_position(position)
        return False
    
    def delete_position(self, position_id: str) -> bool:
        """Delete a position from the database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM positions WHERE id = ?", (position_id,))
            conn.commit()
            deleted = cursor.rowcount > 0
            conn.close()
            
            if deleted:
                self.logger.info(f"Deleted position {position_id}")
            return deleted
            
        except Exception as e:
            self.logger.error(f"Error deleting position: {e}")
            return False
    
    def _row_to_position(self, row: Dict[str, Any]) -> Position:
        """Convert database row to Position object."""
        tags = json.loads(row.get("tags", "[]")) if row.get("tags") else []
        
        return Position(
            id=row["id"],
            symbol=row["symbol"],
            asset_type=row.get("asset_type", "STOCK"),
            option_type=OptionType(row["option_type"]),
            expiry=row["expiry"],
            strike=row["strike"],
            contracts=row["contracts"],
            entry_date=row["entry_date"],
            entry_price=row["entry_price"],
            underlying_entry_price=row.get("underlying_entry_price"),
            status=PositionStatus(row.get("status", "OPEN")),
            notes=row.get("notes", ""),
            tags=tags
        )
    
    # JSON Import/Export
    
    def export_to_json(self, filepath: str = "data/portfolio.json") -> bool:
        """Export all positions to JSON file."""
        try:
            positions = self.get_all_positions()
            data = {
                "exported_at": datetime.utcnow().isoformat(),
                "count": len(positions),
                "positions": [p.to_dict() for p in positions]
            }
            
            path = Path(filepath)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(path, "w") as f:
                json.dump(data, f, indent=2, default=str)
            
            self.logger.info(f"Exported {len(positions)} positions to {filepath}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error exporting to JSON: {e}")
            return False
    
    def import_from_json(self, filepath: str = "data/portfolio.json", overwrite: bool = False) -> int:
        """
        Import positions from JSON file.
        
        Args:
            filepath: Path to JSON file
            overwrite: If True, update existing positions. If False, skip duplicates.
            
        Returns:
            Number of positions imported
        """
        try:
            path = Path(filepath)
            if not path.exists():
                self.logger.warning(f"Import file not found: {filepath}")
                return 0
            
            with open(path, "r") as f:
                data = json.load(f)
            
            positions_data = data.get("positions", [])
            imported = 0
            
            for pos_data in positions_data:
                # Remove computed fields that shouldn't be stored
                for field in ["market_value", "cost_basis", "unrealized_pnl", 
                              "unrealized_pnl_pct", "last_updated", "signal",
                              "underlying_last", "option_last", "option_bid", 
                              "option_ask", "days_to_expiry", "delta", "gamma",
                              "theta", "vega", "iv", "pricing_source", "pricing_confidence"]:
                    pos_data.pop(field, None)
                
                position = Position.from_dict(pos_data)
                
                existing = self.get_position(position.id)
                if existing:
                    if overwrite:
                        self.update_position(position)
                        imported += 1
                else:
                    if self.add_position(position):
                        imported += 1
            
            self.logger.info(f"Imported {imported} positions from {filepath}")
            return imported
            
        except Exception as e:
            self.logger.error(f"Error importing from JSON: {e}")
            return 0
    
    def get_summary(self) -> Dict[str, Any]:
        """Get portfolio summary statistics."""
        all_positions = self.get_all_positions()
        open_positions = [p for p in all_positions if p.status == PositionStatus.OPEN]
        
        return {
            "total_positions": len(all_positions),
            "open_positions": len(open_positions),
            "closed_positions": len([p for p in all_positions if p.status == PositionStatus.CLOSED]),
            "rolled_positions": len([p for p in all_positions if p.status == PositionStatus.ROLLED]),
            "symbols": list(set(p.symbol for p in open_positions)),
            "calls": len([p for p in open_positions if p.option_type == OptionType.CALL]),
            "puts": len([p for p in open_positions if p.option_type == OptionType.PUT])
        }
