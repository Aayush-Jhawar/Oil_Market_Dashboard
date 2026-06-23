import sqlite3, pandas as pd
conn = sqlite3.connect('energy.db')
df = pd.read_sql('SELECT symbol, direction, entry_low, entry_high, target_price, stop_loss, created_at FROM trade_recommendations WHERE symbol = "WTI" ORDER BY created_at DESC LIMIT 1', conn)
print(df.to_string())
