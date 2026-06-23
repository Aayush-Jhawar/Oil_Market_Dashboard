import sys
from pathlib import Path
import time

backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

from services.price_fetcher import PriceFetcher
from services.multi_factor_engine import compute_multi_factor_score
from signal_calc import SignalCalculator
from services.macro_fetcher import MacroFetcher

def test_predictions():
    print("\n--- Running Predictions Strategy Test ---")
    start = time.time()
    
    print("Fetching macro data...")
    try:
        macro = MacroFetcher.fetch_all_macro()
    except Exception as e:
        print(f"Failed to fetch macro: {e}. Using empty macro.")
        macro = {}
    print(f"Macro fetched in {time.time() - start:.2f}s")

    all_target_symbols = ["WTI", "Brent", "RBOB", "HO", "3-2-1CRACK", "GASCRACK", "DIESELCRACK", "WTI_FLY", "BRENT_FLY", "RBOB_FLY", "HO_FLY"]
    
    print("\n" + "="*80)
    print(f"{'SYMBOL':<15} | {'SCORE':<8} | {'REGIME':<12} | {'SIGNAL':<8} | {'VOL':<6} | {'TIME':<5}")
    print("-" * 80)
    
    for sym in all_target_symbols:
        s = time.time()
        try:
            hist = PriceFetcher.fetch_historical(sym, "3mo")
            prices_list = [float(h["close"]) for h in (hist or [])] if hist else []
            
            sym_mf = compute_multi_factor_score(
                symbol=sym,
                candles=hist or [],
                macro=macro,
                eia_data=None,
                cftc_data=None,
            ) if hist else {}
            
            sym_vol = SignalCalculator.calculate_realized_volatility(prices_list) if prices_list else 0.0
            
            score = sym_mf.get("composite_score", 0.0)
            regime = sym_mf.get("regime", "NEUTRAL")
            signal = sym_mf.get("signal", "NEUTRAL")
            
            elapsed = time.time() - s
            print(f"{sym:<15} | {score:>8.2f} | {regime:<12} | {signal:<8} | {sym_vol:>5.1f}% | {elapsed:>4.1f}s")
        except Exception as e:
            print(f"{sym:<15} | ERROR: {str(e)[:50]}")

if __name__ == "__main__":
    test_predictions()
