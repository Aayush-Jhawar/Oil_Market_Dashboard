import sqlite3
import os

db_path = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Dashboard_v3', 'DB', 'bars_15min_latest.db')
conn = sqlite3.connect(db_path)
tables = [t[0] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
res = []
for t in tables:
    try:
        rows = conn.execute(f"SELECT * FROM {t} ORDER BY timestamp DESC LIMIT 50").fetchall()
        for r in rows:
            for val in r:
                if isinstance(val, (float, int)) and abs(float(val) - 69.37) < 0.05:
                    res.append((t, r))
    except Exception as e:
        pass
print("Exact matches for 69.37 (+- 0.05):")
for r in res:
    print(r)
conn.close()
