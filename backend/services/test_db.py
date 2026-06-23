import sqlite3
import pandas as pd
import os

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
db_path = os.path.join(base_dir, "DB", "bars_15min_latest.db")
conn = sqlite3.connect(db_path)

def get_latest(prefix):
    tables = [t[0] for t in conn.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '{prefix}_%'").fetchall()]
    latest_row = None
    latest_ts = ''
    for t in tables:
        row = conn.execute(f"SELECT * FROM {t} ORDER BY timestamp DESC LIMIT 1").fetchone()
        if row and row[0] > latest_ts:
            latest_ts = row[0]
            latest_row = row
    return latest_row

print('WTI:', get_latest('CL'))
print('Brent:', get_latest('CO'))
