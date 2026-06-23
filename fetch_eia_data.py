import requests
import pandas as pd
import time

EIA_KEY = "cl0z9I7mx5VbZDcu1arMj8XwnEiJ7fqcHufbN6Yy"

SERIES = {
    "WRESTUS1": "Residual_FO_Stocks_US",
    "WKJSTUS1": "Jet_Fuel_Stocks_US",
    "WPRSTUS1": "Propane_Stocks_US",
    "WTTSTUS1": "Total_Petroleum_Stocks_US",
    "WGTSTUS1": "Gasoline_Stocks_US",
    "WDISTUS1": "Distillate_Stocks_US",
    "WCRSTUS1": "Crude_Oil_Stocks_US",
    "W_EPC0_SAX_YCUOK_MBBL": "Cushing_Crude_Stocks",
    "WCRRIUS2": "Crude_Inputs_Refineries_US",
}

def fetch_eia(series_id, name, start="2020-01-01", end="2026-07-01"):
    url = "https://api.eia.gov/v2/petroleum/stoc/wstk/data/"
    params = {
        "api_key": EIA_KEY,
        "frequency": "weekly",
        "data[0]": "value",
        "facets[series][]": series_id,
        "start": start,
        "end": end,
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "length": 5000,
    }
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()["response"]["data"]
            if not data:
                print(f"  WARNING: {series_id} returned 0 rows")
                return pd.DataFrame()
            df = pd.DataFrame(data)
            df["value"] = pd.to_numeric(df["value"], errors="coerce")
            df["period"] = pd.to_datetime(df["period"])
            cols = [c for c in ["period","series","series-description","product-name","value","units"] if c in df.columns]
            return df[cols]
        except Exception as e:
            print(f"  Retry {attempt+1}/3: {e}")
            time.sleep(2)
    return pd.DataFrame()

if __name__ == "__main__":
    results = {}
    for sid, name in SERIES.items():
        print(f"Fetching {sid} ({name})...")
        df = fetch_eia(sid, name)
        if not df.empty:
            out = f"Data/eia_{name}.csv"
            df.to_csv(out, index=False)
            date_min = str(df["period"].min().date())
            date_max = str(df["period"].max().date())
            print(f"  Saved {len(df)} rows -> {out}")
            print(f"  Range: {date_min} to {date_max}")
            print(df.tail(3)[["period","value","units"]].to_string())
            results[name] = {"rows": len(df), "start": date_min, "end": date_max, "file": out}
        else:
            print(f"  FAILED - no data returned")
            results[name] = {"rows": 0}
        print()

    print("=" * 60)
    print("DOWNLOAD SUMMARY")
    print("=" * 60)
    for name, info in results.items():
        status = f"{info['rows']} rows ({info.get('start','')} to {info.get('end','')})" if info["rows"] > 0 else "FAILED"
        print(f"  {name:40s}: {status}")
