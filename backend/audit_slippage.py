import json

data = json.load(open('paper_state.json'))
closed = data.get('closed_trades', [])

# Check slippage values used
slippage_counts = {}
for t in closed:
    slip = t.get('slippage_ticks', 'MISSING')
    inst = t.get('instrument_type', 'unknown')
    key = f'{inst}:{slip}'
    slippage_counts[key] = slippage_counts.get(key, 0) + 1

print('=== SLIPPAGE AUDIT ===')
for k, v in sorted(slippage_counts.items()):
    print(f'  {k}: {v} trades')

# Check if any trade has wrong slippage
print()
print('=== WRONG SLIPPAGE TRADES ===')
wrong = [t for t in closed if
    (t.get('instrument_type') == 'double_fly' and t.get('slippage_ticks') != 8.0) or
    (t.get('instrument_type') == 'fly' and t.get('slippage_ticks') != 4.0) or
    (t.get('instrument_type') == 'spread' and t.get('slippage_ticks') != 2.0)
]
print(f'  Trades with incorrect slippage: {len(wrong)}')
for t in wrong[:10]:
    sym = t.get('symbol', '?')
    inst = t.get('instrument_type', '?')
    slip = t.get('slippage_ticks', '?')
    pnl = t.get('pnl', '?')
    print(f'  sym={sym} | type={inst} | slippage={slip} | pnl={pnl}')

# Total realized ticks
print()
print('=== PNL SUMMARY ===')
realized = sum(t.get('pnl', 0) for t in closed)
total_slippage = sum(t.get('slippage_ticks', 0) for t in closed)
gross = realized + total_slippage
print(f'  Total closed trades: {len(closed)}')
print(f'  Gross ticks (before slip): {round(gross, 1)}')
print(f'  Total slippage charged: {round(total_slippage, 1)}')
print(f'  Net realized ticks: {round(realized, 1)}')
print(f'  From paper_state field: {data.get("realized_pnl_ticks")}')

# Check entry/exit sanity - look for same-bar entries and exits (look-ahead)
print()
print('=== LOOK-AHEAD / SAME-BAR TRADE AUDIT ===')
same_bar = [t for t in closed if t.get('entry_time') == t.get('exit_time')]
print(f'  Trades entered AND exited on the same bar: {len(same_bar)} (should be 0)')
for t in same_bar[:5]:
    sym = t.get('symbol', '?')
    et = t.get('entry_time', '?')
    pnl = t.get('pnl', '?')
    print(f'  sym={sym} | time={et} | pnl={pnl}')

# Check for any trade with suspiciously high per-trade pnl (lookahead symptom)
print()
print('=== HIGH PNL OUTLIER TRADES (>100 ticks net) ===')
outliers = sorted([t for t in closed if abs(t.get('pnl', 0)) > 100], key=lambda x: -abs(x.get('pnl', 0)))
print(f'  Count: {len(outliers)}')
for t in outliers[:10]:
    sym = t.get('symbol', '?')
    pnl = t.get('pnl', '?')
    slip = t.get('slippage_ticks', '?')
    entry = t.get('entry', '?')
    exit_ = t.get('exit', '?')
    direction = t.get('direction', '?')
    print(f'  {direction} {sym}: entry={entry}, exit={exit_}, pnl={pnl}, slippage={slip}')
