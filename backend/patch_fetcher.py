import re

with open(r'C:\Users\aayush.jhawar\OneDrive - hertshtengroup.com\Desktop\Dashboard_v3\backend\services\price_fetcher.py', 'r') as f:
    code = f.read()

# 1. Inject _get_eod_from_15min_db above fetch_historical
eod_method = """    @staticmethod
    def _get_eod_from_15min_db(symbol: str) -> List[Dict]:
        try:
            import sqlite3
            import os
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            db_path = os.path.join(base_dir, "DB", "bars_15min_latest.db")
            if not os.path.exists(db_path):
                return []
            prefix = "CL" if symbol == "WTI" else ("CO" if symbol in ("Brent", "BRN") else None)
            if not prefix: return []
            
            conn = sqlite3.connect(db_path)
            tables = [t[0] for t in conn.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '{prefix}_%'").fetchall()]
            
            def parse_contract(t):
                suffix = t.split('_')[1]
                months = {'F':1, 'G':2, 'H':3, 'J':4, 'K':5, 'M':6, 'N':7, 'Q':8, 'U':9, 'V':10, 'X':11, 'Z':12}
                try:
                    return (int(suffix[1:]), months.get(suffix[0], 99))
                except:
                    return (99, 99)
            tables.sort(key=parse_contract)
            
            if not tables:
                return []
                
            front_month = tables[0]
            query = f\"\"\"
                SELECT DATE(timestamp) as d, 
                       (SELECT open FROM {front_month} t2 WHERE DATE(t2.timestamp) = DATE(t1.timestamp) ORDER BY t2.timestamp ASC LIMIT 1) as o,
                       MAX(high) as h,
                       MIN(low) as l,
                       (SELECT close FROM {front_month} t2 WHERE DATE(t2.timestamp) = DATE(t1.timestamp) ORDER BY t2.timestamp DESC LIMIT 1) as c,
                       SUM(volume) as v
                FROM {front_month} t1
                GROUP BY DATE(timestamp)
                ORDER BY d ASC
            \"\"\"
            rows = conn.execute(query).fetchall()
            conn.close()
            
            result = []
            for r in rows:
                if r[0] >= "2026-06-12":
                    result.append({
                        "timestamp": r[0],
                        "open": float(r[1]),
                        "high": float(r[2]),
                        "low": float(r[3]),
                        "close": float(r[4]),
                        "volume": float(r[5]) if r[5] else 0.0
                    })
            return result
        except Exception as e:
            logger.error(f"Error fetching EOD from 15min DB: {e}")
            return []

    @staticmethod
    def fetch_historical(symbol: str, period: str = "1mo") -> Optional[List[Dict]]:"""

code = code.replace('    @staticmethod\n    def fetch_historical(symbol: str, period: str = "1mo") -> Optional[List[Dict]]:', eod_method)

# 2. Replace the Try database first section inside fetch_historical
historical_stitch = """        if symbol in ["WTI", "Brent", "BRN"]:
            import pandas as pd
            yf_history = []
            ticker_symbol = PriceFetcher.SYMBOLS.get("Brent" if symbol == "BRN" else symbol)
            if ticker_symbol:
                try:
                    yf_period = period
                    if period in ("1d", "5d"):
                        yf_period = "5d"
                    ticker = yf.Ticker(ticker_symbol, session=_SESSION)
                    hist = ticker.history(period=yf_period, interval="1d", actions=False)
                    if hist is not None and not hist.empty:
                        for idx, row in hist.iterrows():
                            date_str = idx.strftime("%Y-%m-%d")
                            if date_str >= "2026-06-12":
                                continue
                            
                            close = row.get("Close")
                            if pd.isna(close): continue
                            open_p = row.get("Open") if not pd.isna(row.get("Open")) else close
                            high = row.get("High") if not pd.isna(row.get("High")) else close
                            low = row.get("Low") if not pd.isna(row.get("Low")) else close
                            vol = row.get("Volume") if not pd.isna(row.get("Volume")) else 0.0
                            
                            yf_history.append({
                                "timestamp": date_str,
                                "open": float(open_p),
                                "high": float(high),
                                "low": float(low),
                                "close": float(close),
                                "volume": float(vol)
                            })
                except Exception as e:
                    logger.error(f"YF fetch error stitched for {symbol}: {e}")
            
            db_history = PriceFetcher._get_eod_from_15min_db(symbol)
            return yf_history + db_history

        # Try database first"""

code = code.replace('        # Try database first', historical_stitch)

with open(r'C:\Users\aayush.jhawar\OneDrive - hertshtengroup.com\Desktop\Dashboard_v3\backend\services\price_fetcher.py', 'w') as f:
    f.write(code)
