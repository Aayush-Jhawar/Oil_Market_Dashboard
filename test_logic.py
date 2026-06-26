import sqlite3
import os
from datetime import datetime, timedelta

def test_logic():
    db_path = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Dashboard_v3', 'DB', 'bars_15min_latest.db')
    conn = sqlite3.connect(db_path)
    tables = [t[0] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'CL_%'").fetchall()]
    
    def parse_contract(t):
        suffix = t.split('_')[1]
        months = {'F':1, 'G':2, 'H':3, 'J':4, 'K':5, 'M':6, 'N':7, 'Q':8, 'U':9, 'V':10, 'X':11, 'Z':12}
        try:
            return (int(suffix[1:]), months.get(suffix[0], 99))
        except:
            return (99, 99)
            
    tables.sort(key=parse_contract)
    
    table_max_ts = {}
    global_max = ""
    for t in tables:
        row = conn.execute(f"SELECT MAX(timestamp) FROM {t}").fetchone()
        if row and row[0]:
            ts = row[0]
            table_max_ts[t] = ts
            if ts > global_max:
                global_max = ts
                
    print(f"Global max timestamp: {global_max}")
    
    clean_max = global_max.replace("T", " ")[:19]
    max_dt = datetime.strptime(clean_max, "%Y-%m-%d %H:%M:%S")
    cutoff_str = (max_dt - timedelta(days=4)).strftime("%Y-%m-%d %H:%M:%S")
    print(f"Cutoff: {cutoff_str}")
    
    for t in tables:
        ts = table_max_ts.get(t, "")
        clean_ts = ts.replace("T", " ")[:19]
        is_active = clean_ts >= cutoff_str
        expiry = parse_contract(t)
        print(f"Table {t}: max_ts={ts}, is_active={is_active}, expiry={expiry}")
        
    for t in tables:
        ts = table_max_ts.get(t, "")
        clean_ts = ts.replace("T", " ")[:19]
        if clean_ts >= cutoff_str:
            row = conn.execute(f"SELECT timestamp, open, high, low, close, volume FROM {t} ORDER BY timestamp DESC LIMIT 1").fetchone()
            print(f"SELECTED: {t} with price {row[4]} at {row[0]}")
            break
            
test_logic()
