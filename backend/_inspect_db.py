import sqlite3

conn = sqlite3.connect('energy.db')

# Get date range of historical_term_structure per symbol
rows = conn.execute("""
    SELECT symbol, MIN(timestamp), MAX(timestamp), COUNT(*)
    FROM historical_term_structure 
    GROUP BY symbol
""").fetchall()

print("=== Historical Term Structure Coverage ===")
for r in rows:
    print(f"  {r[0]}: {r[1][:10]} to {r[2][:10]} ({r[3]} bars)")

# Get symbols in price_history
print("\n=== Price History Coverage ===")
rows2 = conn.execute("""
    SELECT symbol, MIN(date), MAX(date), COUNT(*)
    FROM price_history 
    GROUP BY symbol
""").fetchall()
for r in rows2:
    print(f"  {r[0]}: {r[1]} to {r[2]} ({r[3]} rows)")

# Check trade_recommendations count per symbol
print("\n=== Trade Recommendations Coverage ===")
rows3 = conn.execute("""
    SELECT symbol, MIN(date), MAX(date), COUNT(*)
    FROM trade_recommendations
    GROUP BY symbol
    ORDER BY COUNT(*) DESC
""").fetchall()
for r in rows3[:20]:
    print(f"  {r[0]}: {r[1][:10]} to {r[2][:10]} ({r[3]} recs)")

# Check for bars_15min DBs
import glob, os
bars_files = glob.glob("DB/bars_15min_latest.db") + glob.glob("bars_15min_latest.db")
print(f"\n=== 15-min bars DB files: {len(bars_files)} ===")
for f in bars_files[:10]:
    print(f"  {f}")

conn.close()
