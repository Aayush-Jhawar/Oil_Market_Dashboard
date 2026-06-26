import sqlite3 as _sqlite3
import os
import shutil
import tempfile
import time

start = time.time()
src_db = r"I:\Public\Summer Interns Energy\DB\bars_15min_20260623.db"
dest_db = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Dashboard_v3', 'DB', 'bars_15min_latest.db')

temp_dir = tempfile.gettempdir()
base_name = os.path.basename(src_db)
temp_db = os.path.join(temp_dir, base_name)

print("Copying files...")
shutil.copy2(src_db, temp_db)
for ext in ["-wal", "-shm"]:
    if os.path.exists(src_db + ext):
        shutil.copy2(src_db + ext, temp_db + ext)

print(f"Copied in {time.time() - start:.2f}s")
start = time.time()

src_conn = _sqlite3.connect(temp_db, timeout=10)
dest_conn = _sqlite3.connect(dest_db, timeout=10)
dest_conn.execute("PRAGMA journal_mode=WAL")

tables = [t[0] for t in src_conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(f"Found {len(tables)} tables")

for tbl in tables:
    ddl = src_conn.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{tbl}'").fetchone()
    if ddl and ddl[0]:
        dest_conn.execute(ddl[0].replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS", 1))
        dest_conn.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{tbl}_ts ON {tbl}(timestamp)")
    rows = src_conn.execute(f"SELECT timestamp, open, high, low, close, volume FROM {tbl}").fetchall()
    if rows:
        dest_conn.executemany(f"INSERT OR IGNORE INTO {tbl} (timestamp, open, high, low, close, volume) VALUES (?,?,?,?,?,?)", rows)
    dest_conn.commit()

print(f"Merged in {time.time() - start:.2f}s")
src_conn.close()
dest_conn.close()

for ext in ["", "-wal", "-shm"]:
    if os.path.exists(temp_db + ext):
        os.remove(temp_db + ext)
