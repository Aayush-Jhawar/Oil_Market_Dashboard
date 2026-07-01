"""
Seed the `macro_indicators` table from the local macro CSV in Data/.

WHY: MacroFetcher pulls live macro (DXY/US10Y/VIX/Gold/…) from yfinance and,
when yfinance is unavailable, returns None (UI shows "—"). macro_daily holds
real daily history 2022 → 2026-05, so seeding it lets MacroFetcher fall back to
the last *real* observed value (see MacroFetcher._db_latest) rather than a blank.

Source: Data/macro_daily_2022_to_2026-05-22 1.csv
    Date, US10Y, US2Y, DXY, DXY_BROAD, VIX, Gold
We map the columns the dashboard actually surfaces to macro_indicators.indicator_name:
    DXY -> DXY, US10Y -> TNX (10Y yield %), VIX -> VIX, Gold -> GOLD
(The gold_dxy_us10y_*.xlsx is skipped — its US10Y column is on a different,
inconsistent scale, and macro_daily already covers DXY/Gold.)

Idempotent: id = "{indicator}_{date}", INSERT OR REPLACE.
Run:  python backend/scripts/backfill_macro_history.py [--dry-run]
"""
import os
import argparse
import sqlite3

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_BACKEND)
DATA_DIR = os.path.join(_ROOT, "Data")
DB_PATH = os.path.join(_BACKEND, "energy.db")

SRC = "macro_daily_2022_to_2026-05-22 1.csv"
# macro_daily column -> macro_indicators.indicator_name
COL_MAP = {"DXY": "DXY", "US10Y": "TNX", "VIX": "VIX", "Gold": "GOLD"}


def backfill(dry_run: bool = False) -> None:
    path = os.path.join(DATA_DIR, SRC)
    if not os.path.exists(path):
        print(f"[skip] {SRC} not found")
        return
    df = pd.read_csv(path)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).sort_values("Date")
    df["date"] = df["Date"].dt.strftime("%Y-%m-%d")

    conn = sqlite3.connect(DB_PATH)
    total = 0
    for col, name in COL_MAP.items():
        if col not in df.columns:
            print(f"[skip] column {col} absent")
            continue
        sub = df[["date", col]].copy()
        sub[col] = pd.to_numeric(sub[col], errors="coerce")
        sub = sub.dropna(subset=[col])
        sub["chg"] = sub[col].pct_change() * 100.0

        records = [
            (f"{name}_{r['date']}", name, float(r[col]),
             float(r["chg"]) if pd.notna(r["chg"]) else 0.0, f"{r['date']} 00:00:00")
            for _, r in sub.iterrows()
        ]
        print(f"[{name:5}] {len(records)} daily rows ({sub['date'].min()} -> {sub['date'].max()})")
        if dry_run:
            continue
        conn.executemany(
            "INSERT OR REPLACE INTO macro_indicators "
            "(id, indicator_name, value, change_pct, timestamp) VALUES (?,?,?,?,?)",
            records,
        )
        conn.commit()
        total += len(records)
    conn.close()
    print(f"\n{'DRY-RUN — ' if dry_run else ''}Wrote {total} macro_indicator rows.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    backfill(dry_run=ap.parse_args().dry_run)
