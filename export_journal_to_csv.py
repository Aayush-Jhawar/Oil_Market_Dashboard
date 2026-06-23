import sqlite3
import pandas as pd

# Connect to the SQLite database
conn = sqlite3.connect('backtest_journal.db')

# Read the trades table into a pandas DataFrame
df = pd.read_sql_query("SELECT * FROM trades", conn)

# Export the DataFrame to a CSV file
df.to_csv('backtest_journal.csv', index=False)

print("Successfully exported backtest_journal.db to backtest_journal.csv")
conn.close()
