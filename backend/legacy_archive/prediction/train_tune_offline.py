import sys
import os
import pandas as pd
import numpy as np
from datetime import timedelta
from sklearn.metrics import accuracy_score, precision_score, recall_score, classification_report

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from prediction.features.feature_matrix import add_target_variables
from prediction.features.feature_store_service import FeatureStoreService
from prediction.regime.regime_engine import RegimeEngine
from prediction.models.ensemble import ModelEnsemble

data_files = [
    ("WTI", r"..\..\Data\CL_data.csv"),
    ("HO", r"..\..\Data\HO_data.csv"),
    ("Brent", r"..\..\Data\LCO_data.csv"),
    ("GO", r"..\..\Data\LGO_data.csv"),
]

def load_data(filepath):
    print(f"Loading {filepath} (this may take a minute)...")
    try:
        # Load timestamp and all c1 to c12 weighted mid prices
        # First row is #meta... so skip it.
        # Find which columns correspond to cX||weighted_mid
        df_head = pd.read_csv(filepath, nrows=0, skiprows=[0])
        cols = list(df_head.columns)
        
        usecols = ["timestamp"]
        for i in range(1, 13):
            col_name = f"c{i}||weighted_mid"
            if col_name in cols:
                usecols.append(col_name)
                
        df = pd.read_csv(filepath, usecols=usecols, skiprows=[0])
        
        # We need c1 for the price history
        c1_col = "c1||weighted_mid"
        if c1_col not in df.columns:
            print("Missing front month data")
            return pd.DataFrame(), pd.DataFrame()
            
        df.dropna(subset=[c1_col], inplace=True)
        
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        if df["timestamp"].dt.tz is not None:
            df["timestamp"] = df["timestamp"].dt.tz_convert(None)
        df["date"] = df["timestamp"].dt.date
        
        # Build price_history (Daily OHLCV of front month)
        price_history = df.groupby("date")[c1_col].agg(
            open="first",
            high="max",
            low="min",
            close="last"
        )
        price_history["volume"] = 10000 # Dummy volume
        price_history.index = pd.to_datetime(price_history.index)
        
        # Build curve_history (Daily close of all months)
        curve_agg = {}
        for i in range(1, 13):
            col_name = f"c{i}||weighted_mid"
            if col_name in df.columns:
                curve_agg[f"M{i}"] = (col_name, "last")
        
        curve_history = df.groupby("date").agg(**curve_agg)
        curve_history.index = pd.to_datetime(curve_history.index)
        
        return price_history, curve_history
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return pd.DataFrame(), pd.DataFrame()

def tune_and_train(symbol, price_df, curve_df, horizon_days=5):
    print(f"\n{'='*60}")
    print(f"--- Tuning and Training {symbol} ---")
    print(f"{'='*60}")
    if price_df.empty:
        print("No price history found.")
        return 0, ""

    print("Building features...")
    feature_store = FeatureStoreService(use_pca=False)
    raw_feature_matrix, feature_matrix = feature_store.fit_transform_historical(
        price_history=price_df, 
        curve_history=curve_df, 
        eia_history=None, 
        cftc_history=None, 
        macro_history=None
    )
    feature_store.save()

    is_spread = False
    df = add_target_variables(feature_matrix, price_df, {f"{horizon_days}d": horizon_days}, is_spread=is_spread)
    target_dir_col = f"target_direction_{horizon_days}d"
    target_ret_col = f"target_return_{horizon_days}d"
    df = df.dropna(subset=[target_dir_col, target_ret_col])

    if len(df) < 100:
        print(f"Not enough data: {len(df)}")
        return 0, ""

    max_date = df.index.max()
    split_date = max_date - pd.DateOffset(months=2)
    
    train_df = df[df.index <= split_date]
    test_df = df[df.index > split_date]
    
    print(f"Total samples: {len(df)}. Train: {len(train_df)}. Test: {len(test_df)}.")
    
    print("Fitting Regime Engine on train data...")
    y_ret_train = train_df[target_ret_col]
    regime_engine = RegimeEngine()
    regime_engine.fit(train_df, y_ret_train)
    regime_engine.save_all()
    
    regime_history = regime_engine.classify_history(raw_feature_matrix)
    df["regime_label"] = regime_history["regime_label"]
    df = df.dropna(subset=["regime_label"])
    
    train_df = df[df.index <= split_date]
    test_df = df[df.index > split_date]

    print(f"Regime breakdown in training data:")
    print(train_df["regime_label"].value_counts())

    print("Training and Tuning Ensemble on train data...")
    ensemble = ModelEnsemble(horizon=horizon_days, symbol=symbol)
    X_train = train_df.drop(columns=[target_dir_col, target_ret_col, "regime_label"])
    y_dir_train = train_df[target_dir_col]
    
    ensemble.fit(X_train, y_dir_train, y_ret_train, train_df["regime_label"], tune=True)
    ensemble.save_all()
    
    if len(test_df) == 0:
        print("No test data available for the last 2 months.")
        return 0, ""

    print("Evaluating on test data...")
    X_test = test_df.drop(columns=[target_dir_col, target_ret_col, "regime_label"])
    y_dir_test = test_df[target_dir_col]
    regimes_test = test_df["regime_label"]
    
    predictions = []
    
    for i, (idx, row) in enumerate(X_test.iterrows()):
        features_dict = row.to_dict()
        reg_label = regimes_test.iloc[i]
        
        pred = ensemble.predict(features_dict, regime_label=reg_label)
        pred_label = pred["prediction_label"]
        pred_val = 1 if pred_label == "UP" else 0
        predictions.append(pred_val)

    y_test_values = y_dir_test.values
    acc = accuracy_score(y_test_values, predictions)
    rep = classification_report(y_test_values, predictions, target_names=["DOWN (0)", "UP (1)"], zero_division=0)
    
    print("\n" + "="*50)
    print(f"TESTING STATS for {symbol} (Last 2 Months)")
    print("="*50)
    print(rep)
    print(f"Accuracy: {acc:.4f}")
    return acc, rep

if __name__ == "__main__":
    results = {}
    for sym, path in data_files:
        price_df, curve_df = load_data(path)
        if not price_df.empty:
            acc, rep = tune_and_train(sym, price_df, curve_df, horizon_days=5)
            results[sym] = {"accuracy": acc, "report": rep}
    
    print("\n\n" + "#"*50)
    print("FINAL SUMMARY ACROSS ALL TUNED DATASETS (Last 2 Months Forward Testing)")
    print("#"*50)
    for sym, res in results.items():
        print(f"{sym}: {res['accuracy']:.2%} Accuracy")
