import polars as pl
import os
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "Data"))

class DatasetEngine:
    """Lazy evaluation query engine for high-frequency datasets using Polars."""

    # Map standard symbols
    SYMBOL_MAP = {
        "WTI": "CL_data.parquet",
        "Brent": "LCO_data.parquet",
        "HO": "HO_data.parquet",
        "GO": "LGO_data.parquet",
        "WTI-Brent": "wtcl_lco_outrights_1min.parquet"
    }
    
    # fallback to .csv if parquet doesn't exist
    for key, val in SYMBOL_MAP.items():
        if not os.path.exists(os.path.join(DATA_DIR, val)):
            SYMBOL_MAP[key] = val.replace(".parquet", ".csv")

    @staticmethod
    def get_file_path(symbol: str) -> str:
        filename = DatasetEngine.SYMBOL_MAP.get(symbol)
        if not filename:
            raise ValueError(f"No dataset file mapped for symbol {symbol}")
        return os.path.join(DATA_DIR, filename)

    @staticmethod
    def query_intraday_price(symbol: str, limit: int = 1000) -> List[Dict[str, Any]]:
        """Queries the trailing `limit` 1-minute ticks from the dataset."""
        filepath = DatasetEngine.get_file_path(symbol)
        if not os.path.exists(filepath):
            logger.warning(f"Dataset {filepath} not found.")
            return []

        try:
            # We want the timestamp and the c1||weighted_mid (front month price)
            # Due to the large size, we tail the file. Polars tail on lazyframe scans the end.
            
            # The CSVs have a comment header on line 1, column names on line 2.
            # Polars might struggle with the comment line `#meta:1min...`
            # We skip the first row (skip_rows=1) for CSVs.
            
            if filepath.endswith('.parquet'):
                lazy_df = pl.scan_parquet(filepath)
            else:
                lazy_df = pl.scan_csv(filepath, skip_rows=1)
            
            # The column names for timestamp and c1
            # "timestamp" and "c1||weighted_mid"
            
            # Note: The column names might have spaces or exact matches are needed.
            # Let's select by index if names are tricky, but name is better.
            
            df = (
                lazy_df
                .select([pl.col("timestamp"), pl.col("c1||weighted_mid").alias("price")])
                .drop_nulls()
                .tail(limit)
                .collect()
            )
            
            records = df.to_dicts()
            return records
        except Exception as e:
            logger.error(f"Error querying dataset for {symbol}: {e}")
            return []
