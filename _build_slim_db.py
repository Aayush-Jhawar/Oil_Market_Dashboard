"""Build a slim, deployable energy.db: full schema for every table, but row
data only for the small tables the app needs at startup (historical charts read
price_history). Huge tables (prediction_features, etc.) ship empty and refill at
runtime. Output: backend/energy_deploy.db -> shipped as backend/energy.db.
"""
import os
import sqlite3

SRC = os.path.join("backend", "energy.db")
OUT = os.path.join("backend", "energy_deploy.db")
ROW_LIMIT = 100_000  # copy data only for tables smaller than this

if os.path.exists(OUT):
    os.remove(OUT)

src = sqlite3.connect(SRC)
cur = src.cursor()
tables = [r[0] for r in cur.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]

print("table row counts:")
counts = {}
for t in tables:
    try:
        counts[t] = cur.execute(f"SELECT count(*) FROM \"{t}\"").fetchone()[0]
    except Exception as e:
        counts[t] = -1
    print(f"  {t:<28} {counts[t]}")

# Build slim DB via the SQLite backup-less manual copy.
out = sqlite3.connect(OUT)
# 1) recreate every object's schema (tables, indexes) exactly
for sql, in src.execute(
        "SELECT sql FROM sqlite_master WHERE type IN ('table','index') AND sql IS NOT NULL "
        "AND name NOT LIKE 'sqlite_%'").fetchall():
    out.execute(sql)
out.commit()

# Big tables we still need a *recent slice* of (table -> rows to keep, newest first).
# historical_term_structure (6.9M rows) drives the WTI/Brent forward curve ->
# spreads/flies/dflies. The curve fallback only reads the latest row per symbol,
# so a recent tail is plenty and keeps the file small.
RECENT_TAIL = {"historical_term_structure": 20000}

# 2) copy data: full for small tables, recent tail for the listed big ones
copied = []
for t in tables:
    if t in RECENT_TAIL:
        n = RECENT_TAIL[t]
        rows = src.execute(f'SELECT * FROM "{t}" ORDER BY timestamp DESC LIMIT {n}').fetchall()
    elif 0 <= counts[t] < ROW_LIMIT:
        rows = src.execute(f'SELECT * FROM "{t}"').fetchall()
    else:
        rows = []
    if rows:
        ncols = len(rows[0])
        out.executemany(
            f"INSERT INTO \"{t}\" VALUES ({','.join(['?']*ncols)})", rows)
        copied.append(f"{t}({len(rows)})")
out.commit()
out.execute("VACUUM")
out.commit()
out.close()
src.close()

size_mb = round(os.path.getsize(OUT) / 1024 / 1024, 2)
print(f"\nslim DB -> {OUT} ({size_mb} MB)")
print("data copied for:", ", ".join(copied))
