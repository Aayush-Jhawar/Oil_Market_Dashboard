import sqlite3
conn = sqlite3.connect('bars_15min_latest.db')
try:
    print("CL_N26:", conn.execute("SELECT * FROM CL_N26 WHERE timestamp LIKE '2026-06-18%' ORDER BY timestamp DESC LIMIT 1").fetchone())
except Exception as e: print("CL_N26 error", e)
try:
    print("CO_N26:", conn.execute("SELECT * FROM CO_N26 WHERE timestamp LIKE '2026-06-18%' ORDER BY timestamp DESC LIMIT 1").fetchone())
except Exception as e: print("CO_N26 error", e)
