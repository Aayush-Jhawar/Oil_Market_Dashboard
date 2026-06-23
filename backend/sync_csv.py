import json, csv, sys
sys.path.insert(0, "backend")

state = json.load(open("backend/paper_state.json"))
closed = state.get("closed_trades", [])

fieldnames = ["entry_time","exit_time","direction","symbol","structure","spread","fly",
              "entry","exit","target","stop","pnl_dollars","exit_reason","indicator",
              "hold_min","pnl","duration_h","signal","regime","entry_z","exit_z",
              "instrument_type","slippage_ticks"]

with open("backend/paper_state_log.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for t in closed:
        writer.writerow(t)

with open("backend/paper_state_log.csv", newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

pnl = state["realized_pnl_ticks"]
print("JSON trades :", len(closed))
print("CSV rows    :", len(rows))
print("Match       :", len(closed) == len(rows))
print("Net PnL     :", pnl, "ticks =", "$" + f"{pnl*10:,.0f}")
