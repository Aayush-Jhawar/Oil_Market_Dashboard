"""
Seed the `inventory` table from the local EIA weekly CSVs in Data/.

WHY: EIAFetcher pulls live from the EIA Open Data API (52 weeks) and, when the
API key is missing or the call fails, falls back to a single flat constant.
These CSVs hold real weekly history back to 2020, so seeding them lets the EIA
service fall back to the last *real* observed value (see EIAFetcher._db_latest)
instead of a made-up number — no extra live dependency, purely local history.

Only the standard long-format files are ingested:
    period, series, series-description, product-name, value, units
The wide WPSR pivot and the small mar_may sample are intentionally skipped
(redundant / non-standard shape).

Idempotent: rows are keyed id = "{series}_{period}" and INSERT OR REPLACE'd.
Run:  python backend/scripts/backfill_eia_history.py [--dry-run]
"""
import os
import glob
import argparse
import sqlite3

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_BACKEND)
DATA_DIR = os.path.join(_ROOT, "Data")
DB_PATH = os.path.join(_BACKEND, "energy.db")

# Standard long-format EIA stock/flow files (period,series,...,value,units).
STANDARD_FILES = [
    "eia_Crude_Oil_Stocks_US.csv",
    "eia_Cushing_Crude_Stocks.csv",
    "eia_Gasoline_Stocks_US.csv",
    "eia_Distillate_Stocks_US.csv",
    "eia_Jet_Fuel_Stocks_US.csv",
    "eia_Propane_Stocks_US.csv",
    "eia_Residual_FO_Stocks_US.csv",
    "eia_Total_Petroleum_Stocks_US.csv",
    "eia_Crude_Inputs_Refineries_US.csv",
]


def backfill(dry_run: bool = False) -> None:
    conn = sqlite3.connect(DB_PATH)
    total = 0
    for fname in STANDARD_FILES:
        path = os.path.join(DATA_DIR, fname)
        if not os.path.exists(path):
            print(f"[skip] {fname} not found")
            continue
        df = pd.read_csv(path)
        cols = {c.lower().strip(): c for c in df.columns}
        if not {"period", "series", "value"} <= set(cols):
            print(f"[skip] {fname}: unexpected columns {list(df.columns)}")
            continue
        df = df.rename(columns={cols["period"]: "period", cols["series"]: "series",
                                cols["value"]: "value",
                                cols.get("units", "units"): "units"})
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna(subset=["value", "period", "series"])
        series_id = str(df["series"].iloc[0])
        unit = str(df["units"].iloc[0]) if "units" in df.columns else ""

        records = [
            (f"{r['series']}_{r['period']}", str(r["series"]), float(r["value"]),
             str(r.get("units", unit)), str(r["period"]), f"{r['period']} 00:00:00")
            for _, r in df.iterrows()
        ]
        print(f"[{series_id:24}] {fname}: {len(records)} weekly rows "
              f"({df['period'].min()} -> {df['period'].max()})")
        if dry_run:
            continue
        conn.executemany(
            "INSERT OR REPLACE INTO inventory "
            "(id, series_id, value, unit, period, timestamp) VALUES (?,?,?,?,?,?)",
            records,
        )
        conn.commit()
        total += len(records)
    conn.close()
    print(f"\n{'DRY-RUN — ' if dry_run else ''}Wrote {total} inventory rows.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    backfill(dry_run=ap.parse_args().dry_run)
