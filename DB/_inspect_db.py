import sqlite3
import pandas as pd

conn = sqlite3.connect('bars_15min_latest.db')
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
print("Tables:", tables)
if tables:
    for t in tables:
        tname = t[0]
        cnt = conn.execute(f"SELECT COUNT(*) FROM {tname}").fetchone()[0]
        print(f"Table {tname} has {cnt} rows")
        if cnt > 0:
            df = pd.read_sql(f"SELECT * FROM {tname} LIMIT 5", conn)
            print(df.head())
