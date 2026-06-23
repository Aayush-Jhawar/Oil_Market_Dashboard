import sqlite3
import os

source_db = r"I:\Public\Summer Interns Energy\DB\bars_15min_20260612.db"
dest_db = os.path.join(os.path.dirname(__file__), "DB", "bars_15min_latest.db")

print(f"Backing up {source_db} to {dest_db}")
source_conn = sqlite3.connect(source_db)
dest_conn = sqlite3.connect(dest_db)
with dest_conn:
    source_conn.backup(dest_conn)
source_conn.close()
dest_conn.close()
print("Backup successful.")
