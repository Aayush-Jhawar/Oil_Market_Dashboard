import sqlite3
import pandas as pd

try:
    conn = sqlite3.connect(r'I:\Public\Summer Interns Energy\DB\bars_15min_20260612.db')
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
    print("Tables in I: drive DB:", tables)
except Exception as e:
    print("Error on I: drive:", e)

try:
    conn2 = sqlite3.connect('DB/bars_15min_latest.db')
    tables2 = conn2.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
    print("Tables in local DB:", tables2)
except Exception as e:
    print("Error on local drive:", e)
