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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historical_term_structure (
            id VARCHAR PRIMARY KEY,
            symbol VARCHAR NOT NULL,
            date VARCHAR NOT NULL,
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
    conn.commit()

def process_1min_file(conn, filename, symbol):
    filepath = os.path.join(DATA_DIR, filename)
    if not os.path.exists(filepath):
        logger.warning(f"File {filepath} not found. Skipping.")
        return

    logger.info(f"Processing {filename} for {symbol}...")
    
    # The files have a meta header on row 0, the real header is row 1
    # We load in chunks to avoid memory issues with 500MB+ files
    chunksize = 100000
    
    # First, let's identify columns
    header_df = pd.read_csv(filepath, skiprows=1, nrows=0)
    cols = header_df.columns.tolist()
    
    # We only care about timestamp and cX||weighted_mid
    usecols = ['timestamp']
    for i in range(1, 15):
        col_name = f'c{i}||weighted_mid'
        if col_name in cols:
            usecols.append(col_name)

    # To group by day without holding entire dataset in memory, we can use a dictionary
    # to hold the latest price for each day
    daily_latest = {}
    
    for chunk in pd.read_csv(filepath, skiprows=1, usecols=usecols, chunksize=chunksize):
        # Drop rows where timestamp is null or invalid
        chunk = chunk.dropna(subset=['timestamp'])
        
        # Parse timestamp, extract date
        # The timestamp looks like "2021-01-04 01:00:00+00:00"
        try:
            # use str.slice to get the date part efficiently (first 10 chars "YYYY-MM-DD")
            chunk['date'] = chunk['timestamp'].astype(str).str[:10]
            
            # Since data is chronological within chunk, grouping by date and taking last is fine
            # We then merge with daily_latest to always keep the latest seen across chunks
            last_in_chunk = chunk.groupby('date').last()
            
            for date, row in last_in_chunk.iterrows():
                daily_latest[date] = row.to_dict()
                
        except Exception as e:
            logger.error(f"Error processing chunk: {e}")
            continue

    logger.info(f"Found {len(daily_latest)} unique daily dates for {symbol}. Inserting...")
    
    records = []
    for date, row in daily_latest.items():
        record = {
            'id': f"{symbol}_{date}",
            'symbol': symbol,
            'date': date
        }
        for i in range(1, 15):
            col_name = f'c{i}||weighted_mid'
            val = row.get(col_name)
            record[f'm{i}'] = float(val) if pd.notna(val) else None
            
        records.append(record)
        
    df_insert = pd.DataFrame(records)
    if not df_insert.empty:
        # Delete existing records for this symbol to avoid PK constraint issues
        cursor = conn.cursor()
        cursor.execute("DELETE FROM historical_term_structure WHERE symbol = ?", (symbol,))
        conn.commit()
        
        df_insert.to_sql('historical_term_structure', conn, if_exists='append', index=False)
        logger.info(f"Successfully inserted {len(df_insert)} records for {symbol}.")

def main():
    if not os.path.exists(os.path.dirname(DB_PATH)):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        
    conn = sqlite3.connect(DB_PATH)
    setup_db(conn)
    
    # Process primary WTI file
    process_1min_file(conn, "CL_data.csv", "WTI")
    
    # Process primary Brent file
    process_1min_file(conn, "LCO_data.csv", "Brent")

    # Process Heating Oil
    process_1min_file(conn, "HO_data.csv", "HO")

    # Process Gasoil (mapped to RBOB proxy for now if needed, or keeping as GO)
    process_1min_file(conn, "LGO_data.csv", "GO")

    conn.close()
    logger.info("Data ingestion complete.")

if __name__ == "__main__":
    main()
