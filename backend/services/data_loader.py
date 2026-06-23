import os
import pandas as pd
import numpy as np
import math
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from models import PriceHistory
from database import SessionLocal

logger = logging.getLogger(__name__)

# Repo-relative Data dir (…/Dashboard_v3/Data). Works on any machine and inside
# the container. On HF the Data/ folder isn't shipped (it's 3.6GB), but the
# populate pipeline is skipped there because energy.db is deployed pre-populated.
DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "Data"
)

def get_best_dataset(pattern_list):
    """Select the most complete file from a list of possibilities based on size."""
    best_file = None
    max_size = -1
    for f in pattern_list:
        path = os.path.join(DATA_DIR, f)
        if os.path.exists(path):
            size = os.path.getsize(path)
            if size > max_size:
                max_size = size
                best_file = path
    return best_file

def resample_1min_csv_to_daily(file_path, symbol_name):
    """Resamples a 1-minute CSV file to daily OHLCV.
    Handles columns with and without volume.
    """
    logger.info(f"Resampling 1-minute dataset: {file_path} for symbol {symbol_name}")
    try:
        # Read the first line to get columns
        # Since files are large, we can read chunks
        chunks = pd.read_csv(file_path, skiprows=1, chunksize=100000)
        daily_dfs = []
        
        for chunk in chunks:
            if chunk.empty:
                continue
            
            chunk['timestamp'] = pd.to_datetime(chunk['timestamp'], errors='coerce')
            chunk = chunk.dropna(subset=['timestamp'])
            chunk['date'] = chunk['timestamp'].dt.strftime('%Y-%m-%d')
            
            # Identify columns for frontline contract (c1)
            # Find weighted_mid and volume columns
            price_col = None
            vol_col = None
            
            for col in chunk.columns:
                if 'c1||weighted_mid' in col:
                    price_col = col
                elif 'c1||volume' in col:
                    vol_col = col
            
            if not price_col:
                # If no c1||weighted_mid, check if it's the spread file
                for col in chunk.columns:
                    if 'c1||' in col and 'contract' not in col:
                        price_col = col
                        break
            
            if not price_col:
                continue
            
            # Clean numeric values
            chunk[price_col] = pd.to_numeric(chunk[price_col], errors='coerce')
            if vol_col:
                chunk[vol_col] = pd.to_numeric(chunk[vol_col], errors='coerce').fillna(0)
            
            # Group by date
            grouped = chunk.groupby('date')
            
            # Calculate daily OHLCV
            daily_chunk = grouped.agg(
                open=(price_col, 'first'),
                high=(price_col, 'max'),
                low=(price_col, 'min'),
                close=(price_col, 'last'),
                volume=(vol_col, 'sum') if vol_col else (price_col, lambda x: 0.0)
            )
            daily_dfs.append(daily_chunk)
            
        if not daily_dfs:
            return pd.DataFrame()
            
        # Combine chunks
        combined = pd.concat(daily_dfs)
        # Re-aggregate combined daily results since a date could span across chunks
        final_daily = combined.groupby(combined.index).agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        })
        
        final_daily = final_daily.dropna(subset=['close'])
        
        # Unit Standardization
        if symbol_name in ['HO', 'RBOB']:
            final_daily['open'] *= 42.0
            final_daily['high'] *= 42.0
            final_daily['low'] *= 42.0
            final_daily['close'] *= 42.0
        elif symbol_name == 'GO':
            final_daily['open'] /= 7.45
            final_daily['high'] /= 7.45
            final_daily['low'] /= 7.45
            final_daily['close'] /= 7.45

        final_daily['symbol'] = symbol_name
        return final_daily
        
    except Exception as e:
        logger.error(f"Error resampling {file_path}: {e}")
        return pd.DataFrame()

def _build_synthetic_spread_history(symbol_name: str) -> pd.DataFrame:
    """
    Build a synthetic spread price series from component 1-minute histories.
    Used to train dedicated LightGBM models on crack spreads and cal spreads.
    
    DIESELCRACK  = HO*42 - WTI          (HO converted ¢/gal → $/bbl)
    WTI_CAL_SPREAD = computed from M1-M2 of WTI (approximated as 0 for training, 
                     since we only have front-month data)
    BRENT_CAL_SPREAD = same approximation for Brent
    """
    logger.info(f"Building synthetic spread history for {symbol_name}...")
    try:
        if symbol_name == "DIESELCRACK":
            ho_df = load_full_1min_history("HO")   # already in $/bbl
            wti_df = load_full_1min_history("WTI")
            if ho_df.empty or wti_df.empty:
                logger.error("DIESELCRACK synthesis failed: missing HO or WTI data")
                return pd.DataFrame()
            # Align on common timestamps
            spread = ho_df["close"].reindex(wti_df.index, method="nearest", tolerance="2min") - wti_df["close"]
            spread = spread.dropna()
            result = pd.DataFrame({
                "open": spread, "high": spread, "low": spread, "close": spread, "volume": 0.0
            }, index=spread.index)
            result["symbol"] = "DIESELCRACK"
            logger.info(f"DIESELCRACK synthetic series: {len(result)} rows")
            return result

        elif symbol_name in ("WTI_CAL_SPREAD", "BRENT_CAL_SPREAD"):
            # For cal spreads, we proxy using the WTI or Brent front-month returns
            # The model learns directional price dynamics; actual spread level is added via live curve
            base = "WTI" if symbol_name == "WTI_CAL_SPREAD" else "Brent"
            base_df = load_full_1min_history(base)
            if base_df.empty:
                logger.error(f"{symbol_name} synthesis failed: missing {base} data")
                return pd.DataFrame()
            # Use 1-period log-return as a proxy for spread change
            base_df["close"] = base_df["close"].pct_change().fillna(0) * 100
            base_df["open"] = base_df["close"]
            base_df["high"] = base_df["close"]
            base_df["low"] = base_df["close"]
            base_df["symbol"] = symbol_name
            logger.info(f"{symbol_name} synthetic series (return-based): {len(base_df)} rows")
            return base_df

    except Exception as e:
        logger.error(f"Error building synthetic spread for {symbol_name}: {e}")
    return pd.DataFrame()


def load_full_1min_history(symbol_name: str) -> pd.DataFrame:
    """Load the complete 1-minute historical dataset for a given symbol.
    Does NOT compress to daily. Used for high-frequency model training.
    """
    mapping = {
        "WTI": ["CL_outrights_1min_t.csv", "CL_data.csv"],
        "Brent": ["LCO_data.csv", "LCO_3_year_test.csv"],
        "HO": ["HO_data.csv"],
        "GO": ["LGO_data.csv"],
        "WTI-Brent": ["wtcl_lco_outrights_1min.csv"],
        # Synthetic spread symbols — computed from component CSVs below
        "DIESELCRACK": "__synthetic__",
        "WTI_CAL_SPREAD": "__synthetic__",
        "BRENT_CAL_SPREAD": "__synthetic__",
    }
    
    candidates = mapping.get(symbol_name)
    if not candidates:
        logger.warning(f"No 1-minute dataset mapping found for {symbol_name}")
        return pd.DataFrame()

    # ── Synthetic spread construction ────────────────────────────────────────
    if candidates == "__synthetic__":
        return _build_synthetic_spread_history(symbol_name)
        
    file_path = get_best_dataset(candidates)
    if not file_path or not os.path.exists(file_path):
        logger.error(f"1-minute dataset file not found for {symbol_name}")
        return pd.DataFrame()
        
    logger.info(f"Loading full 1-minute history from {file_path} for {symbol_name}...")
    try:
        # Read the file
        df = pd.read_csv(file_path, skiprows=1)
        if df.empty:
            return df
            
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        df = df.dropna(subset=['timestamp'])
        df = df.set_index('timestamp')
        df = df.sort_index()
        
        # Identify price and volume columns
        price_col = None
        vol_col = None
        for col in df.columns:
            if 'c1||weighted_mid' in col:
                price_col = col
            elif 'c1||volume' in col:
                vol_col = col
                
        if not price_col:
            for col in df.columns:
                if 'c1||' in col and 'contract' not in col:
                    price_col = col
                    break
                    
        if not price_col:
            logger.error(f"Could not identify price column in {file_path}")
            return pd.DataFrame()
            
        # Extract OHLCV
        result = pd.DataFrame(index=df.index)
        result['close'] = pd.to_numeric(df[price_col], errors='coerce')
        # Since it's 1-min data, open=high=low=close is a reasonable approximation if we only have weighted_mid
        result['open'] = result['close']
        result['high'] = result['close']
        result['low'] = result['close']
        
        if vol_col:
            result['volume'] = pd.to_numeric(df[vol_col], errors='coerce').fillna(0)
        else:
            result['volume'] = 0.0
            
        result = result.dropna(subset=['close'])
        
        # Unit Standardization
        if symbol_name in ['HO', 'RBOB']:
            result['open'] *= 42.0
            result['high'] *= 42.0
            result['low'] *= 42.0
            result['close'] *= 42.0
        elif symbol_name == 'GO':
            result['open'] /= 7.45
            result['high'] /= 7.45
            result['low'] /= 7.45
            result['close'] /= 7.45
            
        result['symbol'] = symbol_name
        logger.info(f"Successfully loaded {len(result)} 1-minute rows for {symbol_name}")
        return result
        
    except Exception as e:
        logger.error(f"Error loading full 1-min history for {symbol_name}: {e}")
        return pd.DataFrame()

def load_excel_daily_data():
    """Load daily datasets from output (5).xlsx and COc1.xlsx."""
    daily_records = []
    
    # Process output (5).xlsx
    out_xlsx = os.path.join(DATA_DIR, "output (5).xlsx")
    if os.path.exists(out_xlsx):
        try:
            logger.info(f"Loading daily data from {out_xlsx}")
            df = pd.read_excel(out_xlsx)
            df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
            df = df.dropna(subset=['timestamp'])
            df['date'] = df['timestamp'].dt.strftime('%Y-%m-%d')
            
            for _, row in df.iterrows():
                inst = row.get('instrument')
                symbol = 'Brent' if inst == 'CO1' else 'Brent12' if inst == 'CO12' else inst
                daily_records.append({
                    'symbol': symbol,
                    'date': row['date'],
                    'open': float(row.get('open', row['close'])),
                    'high': float(row.get('high', row['close'])),
                    'low': float(row.get('low', row['close'])),
                    'close': float(row['close']),
                    'volume': float(row.get('volume', 0.0))
                })
        except Exception as e:
            logger.error(f"Error reading output (5).xlsx: {e}")
            
    # Process COc1.xlsx
    co_xlsx = os.path.join(DATA_DIR, "COc1.xlsx")
    if os.path.exists(co_xlsx):
        try:
            logger.info(f"Loading daily data from {co_xlsx}")
            df = pd.read_excel(co_xlsx)
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
            df = df.dropna(subset=['Date'])
            df['date'] = df['Date'].dt.strftime('%Y-%m-%d')
            
            for _, row in df.iterrows():
                # LCOc1 is frontline brent, LCOc12 is 12-month spread
                close_val = row.get('LCOc1 (TRDPRC_1)')
                # Check for header indicator or strings
                if isinstance(close_val, str) or pd.isna(close_val):
                    continue
                daily_records.append({
                    'symbol': 'Brent_Settle',
                    'date': row['date'],
                    'open': float(close_val),
                    'high': float(close_val),
                    'low': float(close_val),
                    'close': float(close_val),
                    'volume': 0.0
                })
        except Exception as e:
            logger.error(f"Error reading COc1.xlsx: {e}")
            
    return pd.DataFrame(daily_records)

def populate_database_pipeline():
    """Main function to populate SQLite database with integrated datasets."""
    db: Session = SessionLocal()
    try:
        # Check if price_history is already populated
        existing_count = db.query(PriceHistory).count()
        if existing_count > 0:
            logger.info(f"Database already has {existing_count} price history records. Skipping initialization.")
            return

        logger.info("Initializing energy dashboard database with integrated datasets...")
        
        # 1. Select files
        wti_file = get_best_dataset(["CL_outrights_1min_t.csv", "CL_data.csv"])
        brent_file = get_best_dataset(["LCO_data.csv", "LCO_3_year_test.csv"])
        ho_file = get_best_dataset(["HO_data.csv"])
        go_file = get_best_dataset(["LGO_data.csv"])
        spread_file = get_best_dataset(["wtcl_lco_outrights_1min.csv"])
        
        dfs_to_combine = []
        
        # 2. Resample 1min files
        if wti_file:
            wti_df = resample_1min_csv_to_daily(wti_file, "WTI")
            if not wti_df.empty:
                dfs_to_combine.append(wti_df.reset_index())
                
        if brent_file:
            brent_df = resample_1min_csv_to_daily(brent_file, "Brent")
            if not brent_df.empty:
                dfs_to_combine.append(brent_df.reset_index())
                
        if ho_file:
            ho_df = resample_1min_csv_to_daily(ho_file, "HO")
            if not ho_df.empty:
                dfs_to_combine.append(ho_df.reset_index())
                
        if go_file:
            go_df = resample_1min_csv_to_daily(go_file, "GO")
            if not go_df.empty:
                dfs_to_combine.append(go_df.reset_index())

        if spread_file:
            spread_df = resample_1min_csv_to_daily(spread_file, "WTI-Brent")
            if not spread_df.empty:
                dfs_to_combine.append(spread_df.reset_index())
                
        # 3. Load Excel daily data
        excel_df = load_excel_daily_data()
        if not excel_df.empty:
            dfs_to_combine.append(excel_df)
            
        if not dfs_to_combine:
            logger.warning("No datasets were successfully parsed!")
            return
            
        # Combine all dataframes
        all_data = pd.concat(dfs_to_combine, ignore_index=True)
        # Drop duplicates based on symbol + date
        all_data = all_data.drop_duplicates(subset=['symbol', 'date'])
        
        logger.info(f"Saving {len(all_data)} daily records to database...")
        
        # Batch insert
        records = []
        for _, row in all_data.iterrows():
            record = PriceHistory(
                id=f"{row['symbol']}_{row['date']}",
                symbol=row['symbol'],
                open=float(row['open']),
                high=float(row['high']),
                low=float(row['low']),
                close=float(row['close']),
                volume=float(row['volume']),
                date=row['date'],
                timestamp=datetime.strptime(row['date'], '%Y-%m-%d')
            )
            records.append(record)
            if len(records) >= 1000:
                db.bulk_save_objects(records)
                db.commit()
                records = []
                
        if records:
            db.bulk_save_objects(records)
            db.commit()
            
        logger.info("Database populator complete.")
        
    except Exception as e:
        logger.error(f"Error populating database: {e}")
        db.rollback()
    finally:
        db.close()

def get_intraday_prices(symbol_name, max_points=1440):
    """Retrieve the latest 1-minute intraday prices for a symbol from the CSV file.
    Uses an optimized file read (tailing the file) to be fast.
    """
    # Map symbols to CSVs
    mapping = {
        "WTI": ["CL_outrights_1min_t.csv", "CL_data.csv"],
        "Brent": ["LCO_data.csv", "LCO_3_year_test.csv"],
        "HO": ["HO_data.csv"],
        "GO": ["LGO_data.csv"],
        "WTI-Brent": ["wtcl_lco_outrights_1min.csv"]
    }
    
    candidates = mapping.get(symbol_name)
    if not candidates:
        return []
        
    file_path = get_best_dataset(candidates)
    if not file_path or not os.path.exists(file_path):
        return []
        
    try:
        # Seek near the end of the file
        # Each line is approx 150-300 bytes. To get ~2000 lines, seek back 600KB.
        chunk_size = 800000
        with open(file_path, 'rb') as f:
            f.seek(0, 2) # seek to end
            file_size = f.tell()
            seek_pos = max(0, file_size - chunk_size)
            f.seek(seek_pos)
            bytes_data = f.read()
            
        text = bytes_data.decode('utf-8', errors='ignore')
        lines = text.splitlines()
        
        # Discard first partial line
        if len(lines) > 1 and seek_pos > 0:
            lines = lines[1:]
            
        # Parse the headers to get column indexes
        with open(file_path, 'r') as f:
            f.readline() # Skip meta comment
            header = f.readline().strip().split(',')
            
        price_idx = None
        vol_idx = None
        
        for idx, col in enumerate(header):
            if 'c1||weighted_mid' in col:
                price_idx = idx
            elif 'c1||volume' in col:
                vol_idx = idx
                
        if price_idx is None:
            for idx, col in enumerate(header):
                if 'c1||' in col and 'contract' not in col:
                    price_idx = idx
                    break
                    
        if price_idx is None:
            return []
            
        records = []
        for line in lines[-max_points:]:
            parts = line.strip().split(',')
            if len(parts) <= max(price_idx, vol_idx or 0):
                continue
            
            timestamp = parts[0]
            try:
                price = float(parts[price_idx])
                volume = float(parts[vol_idx]) if vol_idx is not None and parts[vol_idx] else 0.0
                records.append({
                    "timestamp": timestamp,
                    "close": price,
                    "volume": volume
                })
            except ValueError:
                continue
                
        return records
        
    except Exception as e:
        logger.error(f"Error reading tail of {symbol_name}: {e}")
        return []

def get_intraday_curve(symbol_name: str) -> dict[str, float]:
    """Retrieve the latest full curve (M1-M12) from the CSV dataset."""
    mapping = {
        "WTI": ["CL_outrights_1min_t.csv", "CL_data.csv"],
        "Brent": ["LCO_data.csv", "LCO_3_year_test.csv"],
        "HO": ["HO_data.csv"],
        "GO": ["LGO_data.csv"],
        "WTI-Brent": ["wtcl_lco_outrights_1min.csv"]
    }
    
    candidates = mapping.get(symbol_name)
    if not candidates:
        return {}
        
    file_path = get_best_dataset(candidates)
    if not file_path or not os.path.exists(file_path):
        return {}
        
    try:
        chunk_size = 100000
        with open(file_path, 'rb') as f:
            f.seek(0, 2)
            file_size = f.tell()
            seek_pos = max(0, file_size - chunk_size)
            f.seek(seek_pos)
            bytes_data = f.read()
            
        text = bytes_data.decode('utf-8', errors='ignore')
        lines = text.splitlines()
        
        if len(lines) > 1 and seek_pos > 0:
            lines = lines[1:]
            
        with open(file_path, 'r') as f:
            f.readline()
            header = f.readline().strip().split(',')
            
        # Map month to column index
        month_to_idx = {}
        for m in range(1, 13):
            for idx, col in enumerate(header):
                if f'c{m}||weighted_mid' in col:
                    month_to_idx[m] = idx
                    break
                elif f'c{m}||' in col and 'contract' not in col and 'volume' not in col:
                    # fallback
                    month_to_idx[m] = idx
                    
        if not month_to_idx:
            return {}
            
        last_line = lines[-1].strip().split(',')
        curve = {}
        for m, idx in month_to_idx.items():
            if idx < len(last_line):
                try:
                    val = float(last_line[idx])
                    if not math.isnan(val):
                        curve[f"M{m}"] = val
                except ValueError:
                    pass
                    
        return curve
    except Exception as e:
        logger.error(f"Error fetching historical curve for {symbol_name}: {e}")
        return {}
