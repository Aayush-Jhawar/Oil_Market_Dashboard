"""
Backfill daily PriceHistory from the per-contract OHLCV export
(Data/{CL,HO,LCO,LGO,RBOB}/*c1.csv — Refinitiv hourly bars).

WHY: that export (from I:\\Public\\Summer Interns Energy\\OHLCV, copied into Data/)
is a STATIC one-time dump — no periodic updater — so it is NOT wired as a live
source. But history doesn't need to be live, and it fills genuine gaps the live
feeds don't cover:

  • RBOB  — the dashboard had NO deep RBOB history (only a handful of live
           yfinance rows); this adds 2019-01 → 2026-06 daily bars, so
           fetch_historical() serves RBOB from the DB and stops hitting yfinance.
  • GO    — PriceHistory was stale (~2026-05-20); the export extends it to 06-26.
  • WTI / Brent / HO — already current via their own live sources; we only INSERT
           genuinely-missing dates and NEVER overwrite existing rows, so the
           curated WTI/Brent series (their separate DB source) stays untouched.

Front-month (c1) only → daily OHLCV. Units are standardised to match the existing
PriceHistory convention in services/data_loader.py:
    HO, RBOB : ¢/gal → $/bbl  (× 42)
    GO (LGO) : $/MT  → $/bbl  (÷ 7.45)
    WTI, Brent: as-is ($/bbl)

Idempotent: re-running only adds dates not already present per symbol.
Run:  python backend/scripts/backfill_ohlcv_history.py [--dry-run]
"""
import os
import sys
import sqlite3
import argparse

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_BACKEND)
DATA_DIR = os.path.join(_ROOT, "Data")
DB_PATH = os.path.join(_BACKEND, "energy.db")

# product folder -> (front-month filename, PriceHistory symbol, unit multiplier)
PRODUCTS = {
    "CL":   {"file": "CLc1.csv",  "symbol": "WTI",   "mult": 1.0},
    "LCO":  {"file": "LCOc1.csv", "symbol": "Brent", "mult": 1.0},
    "HO":   {"file": "HOc1.csv",  "symbol": "HO",    "mult": 42.0},
    "LGO":  {"file": "LGOc1.csv", "symbol": "GO",    "mult": 1.0 / 7.45},
    "RBOB": {"file": "RBc1.csv",  "symbol": "RBOB",  "mult": 42.0},
}


def _resample_daily(csv_path: str, mult: float) -> pd.DataFrame:
    """Hourly Refinitiv bars -> daily OHLCV (UTC date), units scaled by `mult`."""
    # Row 0 is a meta line ("#RIC,..."); the real header is also row 0 here since
    # the first token is "#RIC". Columns: #RIC, Alias Underlying RIC, Domain,
    # Date-Time, GMT Offset, Type, Open, High, Low, Last, Volume.
    df = pd.read_csv(csv_path)
    df = df.rename(columns={c: c.strip() for c in df.columns})
    if "Date-Time" not in df.columns or "Last" not in df.columns:
        raise ValueError(f"unexpected columns in {csv_path}: {list(df.columns)}")

    df["Date-Time"] = pd.to_datetime(df["Date-Time"], utc=True, errors="coerce")
    df = df.dropna(subset=["Date-Time"])
    df["date"] = df["Date-Time"].dt.strftime("%Y-%m-%d")
    for col in ("Open", "High", "Low", "Last", "Volume"):
        df[col] = pd.to_numeric(df.get(col), errors="coerce")
    df = df.dropna(subset=["Last"]).sort_values("Date-Time")

    daily = df.groupby("date").agg(
        open=("Open", "first"),
        high=("High", "max"),
        low=("Low", "min"),
        close=("Last", "last"),
        volume=("Volume", "sum"),
    )
    # Fall back to close if OHLC missing on a bar
    for col in ("open", "high", "low"):
        daily[col] = daily[col].fillna(daily["close"])
    daily["volume"] = daily["volume"].fillna(0.0)
    for col in ("open", "high", "low", "close"):
        daily[col] = daily[col] * mult
    return daily


def backfill(dry_run: bool = False) -> None:
    conn = sqlite3.connect(DB_PATH)
    total_inserted = 0
    for folder, meta in PRODUCTS.items():
        symbol = meta["symbol"]
        csv_path = os.path.join(DATA_DIR, folder, meta["file"])
        if not os.path.exists(csv_path):
            print(f"[skip] {symbol}: {csv_path} not found")
            continue

        daily = _resample_daily(csv_path, meta["mult"])
        existing = {
            r[0] for r in conn.execute(
                "SELECT date FROM price_history WHERE symbol = ?", (symbol,)
            ).fetchall()
        }
        new_dates = [d for d in daily.index if d not in existing]
        span = f"{daily.index.min()} -> {daily.index.max()}" if len(daily) else "empty"
        print(f"[{symbol:6}] export {len(daily):5d} days ({span}); "
              f"already in DB {len(existing):5d}; NEW {len(new_dates):5d}")

        if dry_run or not new_dates:
            continue

        records = []
        for d in new_dates:
            row = daily.loc[d]
            records.append((
                f"{symbol}_{d}", symbol,
                float(row["open"]), float(row["high"]), float(row["low"]),
                float(row["close"]), float(row["volume"]), d,
                f"{d} 00:00:00",
            ))
        conn.executemany(
            "INSERT OR IGNORE INTO price_history "
            "(id, symbol, open, high, low, close, volume, date, timestamp) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            records,
        )
        conn.commit()
        total_inserted += len(records)

    conn.close()
    print(f"\n{'DRY-RUN — ' if dry_run else ''}Inserted {total_inserted} new daily rows.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="report only, no writes")
    args = ap.parse_args()
    backfill(dry_run=args.dry_run)
