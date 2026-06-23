import sqlite3, re
import pandas as pd

db_path = "DB/bars_15min_latest.db"
conn = sqlite3.connect(db_path)

month_map = {"F":1,"G":2,"H":3,"J":4,"K":5,"M":6,"N":7,"Q":8,"U":9,"V":10,"X":11,"Z":12}

def parse_expiry(tbl):
    m = re.match(r"CL_([A-Z])(\d+)$", tbl)
    if m:
        return (2000 + int(m.group(2)), month_map.get(m.group(1), 0))
    return (9999, 0)

cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cursor.fetchall()]
cl_tables = sorted([t for t in tables if t.startswith("CL_")], key=parse_expiry)

# WTI_DFLY_4_5_6_7 -> legs 4,5,6,7 (1-indexed) -> CL_V26, CL_X26, CL_Z26, CL_F27
legs = [cl_tables[i] for i in [3, 4, 5, 6]]
print(f"Legs: {legs}")

# Load each leg
dfs = {}
for tbl in legs:
    df = pd.read_sql(f"SELECT timestamp, open, close FROM [{tbl}] ORDER BY timestamp", conn)
    df.index = pd.to_datetime(df["timestamp"])
    dfs[tbl] = df

# DFLY formula: L1 - 3*L2 + 3*L3 - L4
# Find common timestamps
common_idx = dfs[legs[0]].index
for tbl in legs[1:]:
    common_idx = common_idx.intersection(dfs[tbl].index)

L1_o = dfs[legs[0]].loc[common_idx, "open"]
L2_o = dfs[legs[1]].loc[common_idx, "open"]
L3_o = dfs[legs[2]].loc[common_idx, "open"]
L4_o = dfs[legs[3]].loc[common_idx, "open"]

L1_c = dfs[legs[0]].loc[common_idx, "close"]
L2_c = dfs[legs[1]].loc[common_idx, "close"]
L3_c = dfs[legs[2]].loc[common_idx, "close"]
L4_c = dfs[legs[3]].loc[common_idx, "close"]

dfly_open = L1_o - 3*L2_o + 3*L3_o - L4_o
dfly_close = L1_c - 3*L2_c + 3*L3_c - L4_c

# Find bars around 2026-06-14 22:00
mask = [str(ts).startswith("2026-06-14 21") or str(ts).startswith("2026-06-14 22") or str(ts).startswith("2026-06-14 23") for ts in common_idx]
print("\nDFLY values 2026-06-14 21:xx - 22:xx - 23:xx (open used for fills, close for signal):")
for ts, o, c in zip(common_idx[mask], dfly_open[mask], dfly_close[mask]):
    print(f"  {ts}  open={o:.4f}  close={c:.4f}")

# Rolling z-score over 20 bars using CLOSE
closes_all = dfly_close.tolist()
idx_all = list(common_idx)

print()
print("Signal and fill details for the 22:00 trade entry:")
for i, ts in enumerate(idx_all):
    if str(ts).startswith("2026-06-14 22:00"):
        # z-score from bar i-1 (signal bar)
        WINDOW = 20
        if i >= WINDOW:
            w = closes_all[i - WINDOW: i]   # the 20 bars BEFORE bar i
            mean = sum(w) / WINDOW
            var = sum((x - mean) ** 2 for x in w) / WINDOW
            std = var ** 0.5
            z = (closes_all[i-1] - mean) / std if std > 0 else None
            print(f"  Signal bar (i-1={i-1}): ts={idx_all[i-1]}, close={closes_all[i-1]:.4f}")
            print(f"  Rolling mean={mean:.4f}, std={std:.4f}, z={z:.4f}")
            print(f"  Fill bar  (i={i}): ts={ts}, open (fill price) = {dfly_open.iloc[i]:.4f}")
            print()
            print(f"  Logged entry_price = 3.42 (from paper_state.json)")
            print(f"  DB computed open   = {dfly_open.iloc[i]:.4f}")
            if abs(dfly_open.iloc[i] - 3.42) < 0.1:
                print("  ✓ MATCH — entry price is consistent with DB")
            else:
                print(f"  ✗ MISMATCH — DB gives {dfly_open.iloc[i]:.4f}, log says 3.42")
        break

conn.close()
