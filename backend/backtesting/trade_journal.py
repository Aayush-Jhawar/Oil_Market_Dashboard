"""
Trade Journal
==============
Persists every trade to SQLite for post-hoc analysis.
Captures entry/exit timestamps, prices, structure type, fly/spread spec,
planned targets, stop losses, indicator triggers, and P&L.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

import logging

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent.parent / "backtest_journal.db"


@dataclass
class Trade:
    """Single trade record."""
    trade_id: str = ""
    backtest_id: str = ""

    # Timestamps
    entry_timestamp: str = ""
    exit_timestamp: str = ""

    # Direction
    direction: str = ""  # LONG or SHORT

    # Instrument info
    instrument: str = ""          # e.g., "CL_N26-CL_Q26"
    product: str = ""             # CL or CO
    structure_type: str = ""      # OUTRIGHT, SPREAD, FLY
    fly_spec: str = ""            # e.g., "M1M2M3", "M1M6M12"
    spread_spec: str = ""         # e.g., "M1M2", "M1M6"
    leg_details: str = ""         # JSON string of individual legs

    # Prices
    entry_price: float = 0.0
    exit_price: float = 0.0
    planned_target: float = 0.0
    stop_loss: float = 0.0

    # P&L
    pnl_points: float = 0.0      # raw price difference
    pnl_dollars: float = 0.0     # pnl_points * contract_multiplier
    slippage_cost: float = 0.0   # 1% slippage applied

    # Exit info
    exit_reason: str = ""         # SIGNAL, STOP_LOSS, TARGET, TIME_EXIT, EOD

    # Indicator that triggered
    entry_indicator: str = ""     # e.g., "BB", "ZSCORE", "COMPOSITE"
    entry_indicator_value: float = 0.0
    entry_metadata: str = ""      # JSON of indicator details

    # Holding duration
    holding_bars: int = 0
    holding_minutes: int = 0

    # Equity tracking
    equity_at_entry: float = 0.0
    equity_at_exit: float = 0.0
    running_drawdown: float = 0.0

    # Strategy info
    strategy_name: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)

    @property
    def is_winner(self) -> bool:
        return self.pnl_points > 0


class TradeJournal:
    """SQLite-backed trade journal."""

    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS trades (
        trade_id TEXT PRIMARY KEY,
        backtest_id TEXT NOT NULL,
        entry_timestamp TEXT,
        exit_timestamp TEXT,
        direction TEXT,
        instrument TEXT,
        product TEXT,
        structure_type TEXT,
        fly_spec TEXT,
        spread_spec TEXT,
        leg_details TEXT,
        entry_price REAL,
        exit_price REAL,
        planned_target REAL,
        stop_loss REAL,
        pnl_points REAL,
        pnl_dollars REAL,
        slippage_cost REAL,
        exit_reason TEXT,
        entry_indicator TEXT,
        entry_indicator_value REAL,
        entry_metadata TEXT,
        holding_bars INTEGER,
        holding_minutes INTEGER,
        equity_at_entry REAL,
        equity_at_exit REAL,
        running_drawdown REAL,
        strategy_name TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """

    CREATE_INDEX_SQL = [
        "CREATE INDEX IF NOT EXISTS idx_trades_backtest ON trades(backtest_id)",
        "CREATE INDEX IF NOT EXISTS idx_trades_instrument ON trades(instrument)",
        "CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy_name)",
        "CREATE INDEX IF NOT EXISTS idx_trades_entry_ts ON trades(entry_timestamp)",
    ]

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(self.CREATE_TABLE_SQL)
        for idx_sql in self.CREATE_INDEX_SQL:
            conn.execute(idx_sql)
        conn.commit()
        conn.close()

    def record_trade(self, trade: Trade):
        """Insert a completed trade into the journal."""
        if not trade.trade_id:
            trade.trade_id = str(uuid.uuid4())[:8]

        conn = sqlite3.connect(str(self.db_path))
        conn.execute(
            """INSERT OR REPLACE INTO trades (
                trade_id, backtest_id, entry_timestamp, exit_timestamp,
                direction, instrument, product, structure_type,
                fly_spec, spread_spec, leg_details,
                entry_price, exit_price, planned_target, stop_loss,
                pnl_points, pnl_dollars, slippage_cost,
                exit_reason, entry_indicator, entry_indicator_value, entry_metadata,
                holding_bars, holding_minutes,
                equity_at_entry, equity_at_exit, running_drawdown,
                strategy_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trade.trade_id, trade.backtest_id,
                trade.entry_timestamp, trade.exit_timestamp,
                trade.direction, trade.instrument, trade.product,
                trade.structure_type, trade.fly_spec, trade.spread_spec,
                trade.leg_details,
                trade.entry_price, trade.exit_price,
                trade.planned_target, trade.stop_loss,
                trade.pnl_points, trade.pnl_dollars, trade.slippage_cost,
                trade.exit_reason, trade.entry_indicator,
                trade.entry_indicator_value, trade.entry_metadata,
                trade.holding_bars, trade.holding_minutes,
                trade.equity_at_entry, trade.equity_at_exit,
                trade.running_drawdown, trade.strategy_name,
            ),
        )
        conn.commit()
        conn.close()

    def get_trades(
        self,
        backtest_id: Optional[str] = None,
        instrument: Optional[str] = None,
        strategy: Optional[str] = None,
        limit: int = 500,
    ) -> List[Dict]:
        """Retrieve trades with optional filters."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        query = "SELECT * FROM trades WHERE 1=1"
        params = []

        if backtest_id:
            query += " AND backtest_id = ?"
            params.append(backtest_id)
        if instrument:
            query += " AND instrument = ?"
            params.append(instrument)
        if strategy:
            query += " AND strategy_name = ?"
            params.append(strategy)

        query += " ORDER BY entry_timestamp DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_backtest_ids(self) -> List[Dict]:
        """List all backtest runs."""
        conn = sqlite3.connect(str(self.db_path))
        rows = conn.execute(
            """SELECT backtest_id, strategy_name,
                      COUNT(*) as trade_count,
                      MIN(entry_timestamp) as first_trade,
                      MAX(exit_timestamp) as last_trade,
                      SUM(pnl_dollars) as total_pnl
               FROM trades
               GROUP BY backtest_id
               ORDER BY first_trade DESC"""
        ).fetchall()
        conn.close()
        return [
            {
                "backtest_id": r[0], "strategy_name": r[1],
                "trade_count": r[2], "first_trade": r[3],
                "last_trade": r[4], "total_pnl": r[5],
            }
            for r in rows
        ]

    def clear_backtest(self, backtest_id: str):
        """Delete all trades for a specific backtest run."""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("DELETE FROM trades WHERE backtest_id = ?", (backtest_id,))
        conn.commit()
        conn.close()
