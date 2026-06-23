import sys
import os
import pandas as pd
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prediction.validation.walk_forward import run_walk_forward_validation
from services.price_fetcher import PriceFetcher
from prediction.features.feature_matrix import build_historical_feature_matrix

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    symbols = [
        "WTI", "Brent", "RBOB", "HO", "NG", 
        "WTI_CAL_SPREAD", "BRENT_CAL_SPREAD", 
        "WTI_FLY", "BRENT_FLY", "RBOB_FLY", "HO_FLY",
        "3-2-1CRACK", "GASCRACK", "DIESELCRACK"
    ]
    
    results = []
    
    for sym in symbols:
        logger.info(f"--- Running Analysis for {sym} ---")
        try:
            hist_data = PriceFetcher.fetch_historical(sym, "10y")
            if not hist_data:
                continue
                
            prices_df = pd.DataFrame(hist_data)
            if "timestamp" in prices_df.columns:
                prices_df["date"] = pd.to_datetime(prices_df["timestamp"])
                prices_df.set_index("date", inplace=True)
            elif "date" in prices_df.columns:
                prices_df["date"] = pd.to_datetime(prices_df["date"])
                prices_df.set_index("date", inplace=True)
                
            feature_matrix = build_historical_feature_matrix(prices_df)
            
            # horizon is 5 days
            preds = run_walk_forward_validation(feature_matrix, prices_df, horizon_days=5, symbol=sym)
            
            if "error" in preds:
                logger.error(f"Error for {sym}: {preds['error']}")
                continue
                
            wf_metrics = preds["metrics"]
            bt_metrics = preds["backtest"]["metrics"]
            
            is_spread = "SPREAD" in sym or "FLY" in sym or "CRACK" in sym
            model_type = "Kalman Spread / SpreadModel" if is_spread else "HMM + LightGBM Ensemble"
            
            results.append({
                "Symbol": sym,
                "Model Type": model_type,
                "Accuracy": f"{wf_metrics.get('overall_accuracy', 0):.1%}",
                "High Conf Accuracy": f"{wf_metrics.get('high_conf_accuracy', 0):.1%}",
                "Trade Freq": f"{wf_metrics.get('trade_frequency', 0):.1%}",
                "Total PnL": f"{bt_metrics.get('total_return', 0):.1%}",
                "Ann. Return": f"{bt_metrics.get('annualized_return', 0):.1%}",
                "Ann. Vol": f"{bt_metrics.get('annualized_volatility', 0):.1%}",
                "Sharpe": f"{bt_metrics.get('sharpe_ratio', 0):.2f}",
                "Max DD": f"{bt_metrics.get('max_drawdown', 0):.1%}",
                "Win Rate": f"{bt_metrics.get('win_rate', 0):.1%}",
                "Profit Factor": f"{bt_metrics.get('profit_factor', 0):.2f}"
            })
            
        except Exception as e:
            logger.error(f"Failed {sym}: {e}")
            
    df = pd.DataFrame(results)
    
    md_output = "# AI Forecasting Strategy & Accuracy Audit\n\n"
    md_output += "This document details the complete out-of-sample performance statistics for every instrument across outrights, calendar spreads, cracks, and butterflies. All models were tested individually utilizing their respective specific mathematical implementations (e.g. Dynamic Kalman Filters for pairs, LightGBM/HMM for outrights) using our 60/20/20 expanding window methodology.\n\n"
    md_output += "## Consolidated Performance Matrix\n\n"
    
    # Custom markdown table generation to avoid tabulate dependency
    if not df.empty:
        headers = df.columns.tolist()
        md_output += "| " + " | ".join(headers) + " |\n"
        md_output += "| " + " | ".join(["---"] * len(headers)) + " |\n"
        for _, row in df.iterrows():
            md_output += "| " + " | ".join(str(row[c]) for c in headers) + " |\n"
    else:
        md_output += "*No data generated.*\n"
    
    with open("strategy_analysis_v2.md", "w") as f:
        f.write(md_output)
        
    print("Done! Saved to strategy_analysis_v2.md")

if __name__ == "__main__":
    main()
