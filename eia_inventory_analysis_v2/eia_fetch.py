"""
================================================================================
  EIA DIRECT FETCH (v2)  -  production + refinery utilization
================================================================================
Downloads weekly series straight from EIA's public dnav .xls exports (no API key
needed).  These supply the 'production' factor and refinery-utilization context
the inventory study needs.

  WCRFPUS2 : Weekly US Field Production of Crude Oil (Mbbl/d)
  WPULEUS3 : Weekly US % Utilization of Refinery Operable Capacity (%)

Output: data/eia_production.csv, data/eia_refinery_utilization.csv
"""
import os
import io
import requests
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)

SERIES = {
    "WCRFPUS2": ("crude_production", "eia_production.csv"),
    "WPULEUS3": ("refinery_utilization", "eia_refinery_utilization.csv"),
}


def fetch(series):
    url = f"https://www.eia.gov/dnav/pet/hist_xls/{series}w.xls"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    df = pd.read_excel(io.BytesIO(r.content), sheet_name="Data 1", skiprows=2)
    df.columns = ["period", "value"]
    df["period"] = pd.to_datetime(df["period"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna().sort_values("period").reset_index(drop=True)
    df["wow"] = df["value"].diff()
    return df


def main():
    print("=" * 60)
    print("  EIA DIRECT FETCH: production + refinery utilization")
    print("=" * 60)
    for series, (name, fname) in SERIES.items():
        df = fetch(series)
        df.to_csv(os.path.join(DATA, fname), index=False)
        print(f"  {series} ({name}): {len(df)} wks  {df['period'].min().date()} -> "
              f"{df['period'].max().date()}  latest={df['value'].iloc[-1]:.0f}  "
              f"-> {fname}")


if __name__ == "__main__":
    main()
