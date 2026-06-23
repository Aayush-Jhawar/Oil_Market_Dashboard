import os
import sqlite3

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
db_path = os.path.join(base_dir, "DB", "bars_15min_latest.db")
print("DB Path:", db_path)
print("Exists?", os.path.exists(db_path))

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    tables = [t[0] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print("Tables:", tables)
