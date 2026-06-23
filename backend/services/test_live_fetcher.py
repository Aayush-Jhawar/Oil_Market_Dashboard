import sqlite3
import os

def _fetch_live_db_price(symbol: str):
    try:
        # Locate the bars_15min_latest.db file
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        db_path = os.path.join(base_dir, "DB", "bars_15min_latest.db")
        
        if not os.path.exists(db_path):
            return None
            
        prefix = ""
        if symbol == "WTI":
            prefix = "CL"
        elif symbol == "Brent":
            prefix = "CO"
        else:
            return None
            
        conn = sqlite3.connect(db_path)
        tables = [t[0] for t in conn.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '{prefix}_%'").fetchall()]
        
        latest_row = None
        latest_ts = ""
        latest_table = ""
        
        for t in tables:
            row = conn.execute(f"SELECT timestamp, open, high, low, close, volume FROM {t} ORDER BY timestamp DESC LIMIT 1").fetchone()
            if row and row[0] > latest_ts:
                latest_ts = row[0]
                latest_row = row
                latest_table = t
                
        conn.close()
        
        if latest_row:
            # Need prev_close for change_pct?
            change_pct = 0.0
            if latest_table:
                conn = sqlite3.connect(db_path)
                prev_rows = conn.execute(f"SELECT close FROM {latest_table} ORDER BY timestamp DESC LIMIT 2").fetchall()
                conn.close()
                if len(prev_rows) > 1 and prev_rows[1][0] and prev_rows[1][0] != 0:
                    change_pct = ((latest_row[4] - prev_rows[1][0]) / prev_rows[1][0]) * 100

            # Formulate response
            ts_iso = latest_row[0]
            if " " in ts_iso:
                ts_iso = ts_iso.replace(" ", "T")
            
            return {
                "symbol": symbol,
                "open": float(latest_row[1]),
                "high": float(latest_row[2]),
                "low": float(latest_row[3]),
                "close": float(latest_row[4]),
                "volume": float(latest_row[5]) if latest_row[5] else 0.0,
                "change_pct": change_pct,
                "timestamp": ts_iso,
            }
    except Exception as e:
        print(f"Error fetching live db price for {symbol}: {e}")
    return None

print("WTI:", _fetch_live_db_price("WTI"))
print("Brent:", _fetch_live_db_price("Brent"))
