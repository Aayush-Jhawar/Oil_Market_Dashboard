import sys
import os
from pathlib import Path
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

from core.data.fetcher import PriceFetcher
from prediction.regime.hmm_classifier import compute_multi_factor_score
import time

start = time.time()
print("Fetching Brent 3mo...")
hist = PriceFetcher.fetch_historical("Brent", "3mo")
print(f"Got {len(hist) if hist else 0} bars in {time.time() - start:.2f}s")
