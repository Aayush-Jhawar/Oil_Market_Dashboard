import pandas as pd
import sqlite3
import os
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = r"c:\Users\aayush.jhawar\OneDrive - hertshtengroup.com\Desktop\Dashboard_v3\backend\energy.db"
DATA_DIR = r"c:\Users\aayush.jhawar\OneDrive - hertshtengroup.com\Desktop\Dashboard_v3\Data"

def setup_db(conn):
    cursor = conn.cursor()
    cursor.execute('DROP TABLE IF EXISTS historical_term_structure')
    cursor.execute('''
        CREATE TABLE historical_term_structure (
            id VARCHAR PRIMARY KEY,
            symbol VARCHAR NOT NULL,
            timestamp DATETIME NOT NULL,
            m1 FLOAT,
            m2 FLOAT,
            m3 FLOAT,
            m4 FLOAT,
            m5 FLOAT,
            m6 FLOAT,
            m7 FLOAT,
            m8 FLOAT,
            m9 FLOAT,
            m10 FLOAT,
            m11 FLOAT,
            m12 FLOAT,
            m13 FLOAT,
            m14 FLOAT
        )
    ''')
    cursor.execute('CREATE INDEX idx_term_symbol_timestamp ON historical_term_structure(symbol, timestamp)')
    conn.commit()

def process_1min_file(conn, filename, symbol):
    filepath = os.path.join(DATA_DIR, filename)
    if not os.path.exists(filepath):
        logger.warning(f"File {filepath} not found. Skipping.")
        return

    logger.info(f"Processing {filename} for {symbol} (1-minute resolution, NO downsampling)...")
    
    chunksize = 250000
    
    header_df = pd.read_csv(filepath, skiprows=1, nrows=0)
    cols = header_df.columns.tolist()
    
    usecols = ['timestamp']
    for i in range(1, 15):
        col_name = f'c{i}||weighted_mid'
        if col_name in cols:
            usecols.append(col_name)
            
    # Map the columns to standard names
    col_mapping = {'timestamp': 'timestamp'}
    for i in range(1, 15):
        col_name = f'c{i}||weighted_mid'
        if col_name in cols:
            col_mapping[col_name] = f'm{i}'

    total_inserted = 0
    
    # We clear the symbol first
    cursor = conn.cursor()
    cursor.execute("DELETE FROM historical_term_structure WHERE symbol = ?", (symbol,))
    conn.commit()
    
    for chunk in pd.read_csv(filepath, skiprows=1, usecols=usecols, chunksize=chunksize):
        chunk = chunk.dropna(subset=['timestamp'])
        if chunk.empty: continue
            
        chunk = chunk.rename(columns=col_mapping)
        chunk['symbol'] = symbol
        chunk['id'] = chunk['symbol'] + "_" + chunk['timestamp'].astype(str)
        
        # Insert chunk directly
        chunk.to_sql('historical_term_structure', conn, if_exists='append', index=False)
        total_inserted += len(chunk)
        logger.info(f"  Inserted {total_inserted} rows so far for {symbol}...")

    logger.info(f"Finished. Total inserted for {symbol}: {total_inserted}")

def main():
    if not os.path.exists(os.path.dirname(DB_PATH)):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        
    conn = sqlite3.connect(DB_PATH)
    setup_db(conn)
    
    process_1min_file(conn, "CL_data.csv", "WTI")
    process_1min_file(conn, "LCO_data.csv", "Brent")
    process_1min_file(conn, "HO_data.csv", "HO")
    process_1min_file(conn, "LGO_data.csv", "GO")

    conn.close()
    logger.info("Data ingestion complete.")

if __name__ == "__main__":
    main()
