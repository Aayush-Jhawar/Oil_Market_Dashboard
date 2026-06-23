import requests
import time

BASE = "http://localhost:8000"

endpoints = [
    "/api/prices/all",
    "/api/prices/WTI/historical?period=3mo",
    "/api/eia/weekly",
    "/api/cftc/latest",
    "/api/rigs/latest",
    "/api/macro/all",
    "/api/news/enhanced",
    "/api/signals/composite",
    "/api/signals/enhanced",
    "/api/analytics/forward-curve",
    "/api/analytics/correlations",
    "/api/analytics/indicators?symbol=WTI&period=3mo&ema_periods=20,50&atr_period=14",
    "/api/analytics/structure?symbol=WTI",
    "/api/spreads/all",
    "/api/alerts/active",
    "/api/prediction/regime?symbol=WTI",
    "/api/prediction/forecast?symbol=WTI",
    "/api/prediction/trades/all",
    "/api/paper/state",
    "/api/eia/weekly-anchor",
    "/api/storms/active",
    "/api/tankers/positions",
    "/api/v1/risk/portfolio",
    "/api/backtest/strategies",
    "/api/backtest/journal",
]

for url in endpoints:
    try:
        t0 = time.time()
        r = requests.get(BASE + url, timeout=15)
        elapsed = time.time() - t0
        status = r.status_code
        # Check if data is empty
        try:
            j = r.json()
            data = j.get("data")
            if data is None:
                data_info = "NULL"
            elif isinstance(data, list) and len(data) == 0:
                data_info = "EMPTY[]"
            elif isinstance(data, dict) and len(data) == 0:
                data_info = "EMPTY{}"
            else:
                data_info = "OK"
        except:
            data_info = "NO_JSON"
        
        flag = ""
        if status != 200:
            flag = " *** BROKEN ***"
        elif data_info in ("NULL", "EMPTY[]", "EMPTY{}"):
            flag = " *** NO DATA ***"
        elif elapsed > 5:
            flag = " *** SLOW ***"
            
        print(f"[{status}] {elapsed:5.1f}s {data_info:10s} {url}{flag}")
    except requests.exceptions.Timeout:
        print(f"[TIMEOUT] >15s           {url} *** TIMEOUT ***")
    except requests.exceptions.ConnectionError:
        print(f"[CONN_ERR]              {url} *** CONNECTION ERROR ***")
    except Exception as e:
        print(f"[ERROR] {str(e)[:50]:50s} {url}")
