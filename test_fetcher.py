import sys
from pathlib import Path
import time
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

from services.price_fetcher import PriceFetcher

symbols = ["WTI", "Brent", "RBOB", "HO", "3-2-1CRACK", "GASCRACK", "DIESELCRACK", "WTI_FLY", "BRENT_FLY", "RBOB_FLY", "HO_FLY"]

print("Testing PriceFetcher for all symbols...")
for sym in symbols:
    start = time.time()
    try:
        hist = PriceFetcher.fetch_historical(sym, "3mo")
        print(f"{sym:<15} | Got {len(hist) if hist else 0:<4} bars | {time.time() - start:.2f}s")
    except Exception as e:
        print(f"{sym:<15} | ERROR | {time.time() - start:.2f}s | {e}")
