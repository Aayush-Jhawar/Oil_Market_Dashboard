"""
Purged Walk-Forward Cross-Validation
=======================================
Implements the Purged and Embargoed Cross-Validation framework from
López de Prado, "Advances in Financial Machine Learning" (2018), Ch. 7.

Key Concepts:
    - **Purging**: Removes training samples whose label (forward-looking target)
      overlaps with the test period, preventing information leakage.
    - **Embargoing**: Adds a temporal buffer after each test fold to prevent
      autocorrelation from features with long look-back windows from leaking
      test information into training.
    - **Brier Score**: Measures probability calibration — critical for
      Kelly-based position sizing.

This replaces the naive expanding-window validation that had no purging.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def purge_train_indices(
    train_indices: np.ndarray,
    test_start: int,
    test_end: int,
    all_timestamps: pd.DatetimeIndex,
    horizon_periods: int,
) -> np.ndarray:
    """
    Remove training samples whose label period overlaps with the test window.

    A training sample at index i has a label that depends on data from
    i+1 to i+horizon_periods. If any of those rows fall within the test
    window [test_start, test_end], the sample must be purged.

    Args:
        train_indices: Array of integer indices into the full DataFrame.
        test_start: Integer index of the first test sample.
        test_end: Integer index of the last test sample.
        all_timestamps: Full DatetimeIndex of the dataset.
        horizon_periods: Number of periods in the forward-looking label.

    Returns:
        Purged training indices.
    """
    # A training sample at position i has label depending on i+1 to i+horizon_periods.
    # If i+horizon_periods >= test_start, it leaks into the test set.
    # Remove samples where i >= test_start - horizon_periods AND i < test_start.
    purge_start = max(0, test_start - horizon_periods)
    purge_end = test_start  # exclusive

    mask = ~((train_indices >= purge_start) & (train_indices < purge_end))
    purged = train_indices[mask]

    n_purged = len(train_indices) - len(purged)
    if n_purged > 0:
        logger.debug(f"Purged {n_purged} training samples (indices {purge_start}-{purge_end-1})")

    return purged


def embargo_train_indices(
    train_indices: np.ndarray,
    test_end: int,
    embargo_periods: int,
    total_length: int,
) -> np.ndarray:
    """
    Remove training samples that fall within the embargo window after the test set.

    After the test set ends at test_end, the next `embargo_periods` samples
    must not be used for training because their features may contain
    autocorrelated information from the test period.

    Args:
        train_indices: Array of integer indices (already purged).
        test_end: Integer index of the last test sample.
        embargo_periods: Number of periods to embargo after test_end.
        total_length: Total number of rows in the dataset.

    Returns:
        Embargoed training indices.
    """
    embargo_start = test_end + 1
    embargo_end = min(test_end + 1 + embargo_periods, total_length)

    mask = ~((train_indices >= embargo_start) & (train_indices < embargo_end))
    embargoed = train_indices[mask]

    n_embargoed = len(train_indices) - len(embargoed)
    if n_embargoed > 0:
        logger.debug(f"Embargoed {n_embargoed} training samples (indices {embargo_start}-{embargo_end-1})")

    return embargoed


def generate_purged_walk_forward_splits(
    n_samples: int,
    min_train_size: int,
    test_size: int,
    horizon_periods: int,
    embargo_periods: int = 0,
    expanding: bool = True,
    step_size: Optional[int] = None,
) -> List[Tuple[np.ndarray, np.ndarray]]:
    """
    Generate purged + embargoed walk-forward splits.

    Args:
        n_samples: Total number of samples.
        min_train_size: Minimum training window size.
        test_size: Size of each test window.
        horizon_periods: Forward-looking label horizon (for purging).
        embargo_periods: Number of periods to embargo after test end.
        expanding: If True, training window expands; if False, fixed rolling window.
        step_size: Step size between consecutive test windows. Defaults to test_size.

    Returns:
        List of (train_indices, test_indices) tuples.
    """
    if step_size is None:
        step_size = test_size

    splits = []
    test_start = min_train_size

    while test_start + test_size <= n_samples:
        test_end = test_start + test_size - 1  # inclusive

        # Training window
        if expanding:
            train_start = 0
        else:
            train_start = max(0, test_start - min_train_size)

        train_indices = np.arange(train_start, test_start)
        test_indices = np.arange(test_start, test_end + 1)

        # Apply purging: remove train samples whose labels overlap with test
        train_indices = purge_train_indices(
            train_indices, test_start, test_end,
            all_timestamps=None,  # Not needed for index-based purging
            horizon_periods=horizon_periods,
        )

        # Apply embargo: remove train samples in the embargo zone after previous test sets
        # (For walk-forward, embargo only applies to samples AFTER the test set,
        # which would only matter in rolling/non-expanding windows)
        if embargo_periods > 0 and not expanding:
            train_indices = embargo_train_indices(
                train_indices, test_end, embargo_periods, n_samples
            )

        if len(train_indices) < 100:
            logger.warning(
                f"Skipping fold: only {len(train_indices)} training samples "
                f"after purging (test_start={test_start})"
            )
            test_start += step_size
            continue

        splits.append((train_indices, test_indices))
        test_start += step_size

    logger.info(
        f"Generated {len(splits)} purged walk-forward splits "
        f"(horizon={horizon_periods}, embargo={embargo_periods}, "
        f"expanding={expanding})"
    )
    return splits


def calculate_brier_score(probabilities: np.ndarray, actuals: np.ndarray) -> float:
    """
    Calculate the Brier Score for probability calibration assessment.

    Brier Score = mean((predicted_prob - actual_outcome)^2)

    Range: [0, 1] where 0 = perfect calibration, 0.25 = random baseline.
    A score above 0.25 means the model is worse than random.

    Args:
        probabilities: Predicted probabilities of the positive class.
        actuals: Actual binary outcomes (0 or 1).

    Returns:
        Brier score (lower is better).
    """
    if len(probabilities) == 0:
        return 0.25  # random baseline

    return float(np.mean((probabilities - actuals) ** 2))


def calculate_calibration_curve(
    probabilities: np.ndarray,
    actuals: np.ndarray,
    n_bins: int = 10,
) -> Dict[str, List[float]]:
    """
    Compute a calibration curve (reliability diagram data).

    For each probability bin, compute the mean predicted probability
    and the actual observed frequency. Well-calibrated models should
    have these values close to the diagonal.

    Returns:
        Dict with 'mean_predicted', 'fraction_positive', 'bin_counts'.
    """
    bin_edges = np.linspace(0, 1, n_bins + 1)
    mean_predicted = []
    fraction_positive = []
    bin_counts = []

    for i in range(n_bins):
        mask = (probabilities >= bin_edges[i]) & (probabilities < bin_edges[i + 1])
        if i == n_bins - 1:  # include right edge for last bin
            mask = (probabilities >= bin_edges[i]) & (probabilities <= bin_edges[i + 1])

        count = mask.sum()
        if count > 0:
            mean_predicted.append(float(probabilities[mask].mean()))
            fraction_positive.append(float(actuals[mask].mean()))
            bin_counts.append(int(count))
        else:
            mean_predicted.append(float(bin_edges[i] + bin_edges[i + 1]) / 2)
            fraction_positive.append(0.0)
            bin_counts.append(0)

    return {
        "mean_predicted": mean_predicted,
        "fraction_positive": fraction_positive,
        "bin_counts": bin_counts,
    }


def run_purged_walk_forward_validation(
    feature_matrix: pd.DataFrame,
    price_history: pd.DataFrame,
    horizon_periods: int = 60,
    symbol: str = "WTI",
    expanding: bool = True,
    test_window_periods: int = 500,
    embargo_pct: float = 0.01,
) -> Dict:
    """
    Run purged + embargoed walk-forward validation.

    This replaces the naive split-based validation with proper temporal
    purging and embargo following de Prado (2018).

    Args:
        feature_matrix: Transformed feature matrix with DatetimeIndex.
        price_history: Price history for target computation.
        horizon_periods: Number of periods for the forward-looking label.
        symbol: Asset symbol.
        expanding: Expanding vs. rolling window.
        test_window_periods: Number of periods per test window.
        embargo_pct: Embargo as fraction of training size.

    Returns:
        Dict with metrics, predictions, and calibration data.
    """
    from prediction.features.feature_matrix import add_target_variables
    from prediction.regime.regime_engine import RegimeEngine
    from prediction.models.ensemble import ModelEnsemble
    from prediction.models.spread_model import SpreadModel

    logger.info(
        f"Starting PURGED walk-forward validation "
        f"(horizon={horizon_periods}p, symbol={symbol})"
    )

    is_spread = any(tag in symbol for tag in ["SPREAD", "FLY", "CRACK", "-"])

    # Add targets
    df = add_target_variables(
        feature_matrix, price_history,
        {f"{horizon_periods}p": horizon_periods},
        is_spread=is_spread,
    )
    target_dir_col = f"target_direction_{horizon_periods}p"
    target_ret_col = f"target_return_{horizon_periods}p"
    df = df.dropna(subset=[target_dir_col, target_ret_col])

    if len(df) < 1000:
        return {"error": f"Insufficient data: {len(df)} rows (need ≥1000)"}

    # Compute embargo periods
    min_train_size = max(500, int(len(df) * 0.5))
    embargo_periods = max(horizon_periods, int(len(df) * embargo_pct))

    logger.info(
        f"Data: {len(df)} rows | Min train: {min_train_size} | "
        f"Test window: {test_window_periods} | Embargo: {embargo_periods} | "
        f"Purge horizon: {horizon_periods}"
    )

    # Generate purged splits
    splits = generate_purged_walk_forward_splits(
        n_samples=len(df),
        min_train_size=min_train_size,
        test_size=test_window_periods,
        horizon_periods=horizon_periods,
        embargo_periods=embargo_periods,
        expanding=expanding,
        step_size=test_window_periods,
    )

    if not splits:
        return {"error": "Could not generate any valid walk-forward splits"}

    all_predictions = []
    fold_metrics = []

    for fold_idx, (train_idx, test_idx) in enumerate(splits):
        logger.info(
            f"Fold {fold_idx + 1}/{len(splits)}: "
            f"train={len(train_idx)}, test={len(test_idx)}, "
            f"purged={min_train_size - len(train_idx) if not expanding else 'N/A'}"
        )

        train_data = df.iloc[train_idx]
        test_data = df.iloc[test_idx]

        # Feature transformation (fit on train only)
        from prediction.features.transformations import FeatureTransformer
        transformer = FeatureTransformer(use_pca=False)

        X_train_raw = train_data.drop(columns=[target_dir_col, target_ret_col], errors="ignore")
        X_test_raw = test_data.drop(columns=[target_dir_col, target_ret_col], errors="ignore")

        transformer.fit(X_train_raw)
        X_train = transformer.transform(X_train_raw)
        X_test = transformer.transform(X_test_raw)

        y_train_dir = train_data[target_dir_col]
        y_train_ret = train_data[target_ret_col]

        # Regime classification (from raw features for correct thresholds)
        regime_engine = RegimeEngine()
        regime_engine.fit(X_train, y_train_ret)

        train_regimes = regime_engine.classify_history(X_train_raw)
        test_regimes = regime_engine.classify_history(X_test_raw)

        X_train_with_regime = X_train.copy()
        X_train_with_regime["regime_label"] = train_regimes["regime_label"]
        X_train_with_regime = X_train_with_regime.dropna(subset=["regime_label"])

        # Sample weights (recency bias)
        weights = np.linspace(0.8, 1.2, len(X_train_with_regime))

        # Fit model
        if is_spread:
            model = SpreadModel(horizon=horizon_periods, name=symbol)
            X_fit = X_train_with_regime.drop(columns=["regime_label"])
            model.fit(X_fit, y_train_ret.loc[X_train_with_regime.index], sample_weight=weights)
        else:
            model = ModelEnsemble(horizon=horizon_periods, symbol=symbol)
            X_fit = X_train_with_regime.drop(columns=["regime_label"])
            model.fit(
                X_fit,
                y_train_dir.loc[X_train_with_regime.index],
                y_train_ret.loc[X_train_with_regime.index],
                X_train_with_regime["regime_label"],
                sample_weight=weights,
            )

        # Predict on test set
        for i, (dt, row) in enumerate(test_data.iterrows()):
            features = X_test.loc[dt].to_dict() if dt in X_test.index else {}
            if not features:
                continue

            reg_label = test_regimes["regime_label"].iloc[i] if i < len(test_regimes) else "NEUTRAL"
            reg_age = int(test_regimes["regime_age_days"].iloc[i]) if i < len(test_regimes) else 1

            if is_spread:
                pred = model.predict_single(features)
                prob = 0.5 + (pred.get("prediction_value", 0.0) * 5.0)  # scale for Brier
                prob = max(0.0, min(1.0, prob))
            else:
                pred = model.predict(features, regime_label=reg_label, regime_age_days=reg_age)
                prob = pred.get("ensemble_prob", 0.5)

            actual_dir = row[target_dir_col]
            actual_ret = row[target_ret_col]

            is_correct = (
                (pred["prediction_label"] in ["UP", "WIDEN"] and actual_dir == 1) or
                (pred["prediction_label"] in ["DOWN", "NARROW"] and actual_dir == 0)
            )

            all_predictions.append({
                "date": dt,
                "fold": fold_idx,
                "regime_label": reg_label,
                "ensemble_prob": round(prob, 4),
                "prediction_label": pred["prediction_label"],
                "confidence": pred.get("confidence", 0.0),
                "expected_return": pred.get("expected_return", pred.get("prediction_value", 0.0)),
                "actual_direction": actual_dir,
                "actual_return": actual_ret,
                "is_correct": is_correct,
            })

    if not all_predictions:
        return {"error": "No predictions generated across all folds"}

    preds_df = pd.DataFrame(all_predictions).set_index("date")

    # ── Compute Metrics ──────────────────────────────────────────────────
    traded = preds_df[preds_df["prediction_label"] != "NEUTRAL"]

    # Brier Score
    probs = traded["ensemble_prob"].values
    actuals = traded["actual_direction"].values
    brier = calculate_brier_score(probs, actuals)

    # Calibration curve
    calibration = calculate_calibration_curve(probs, actuals)

    # Per-fold metrics
    for fold_idx in range(len(splits)):
        fold_preds = traded[traded["fold"] == fold_idx]
        if len(fold_preds) > 0:
            fold_metrics.append({
                "fold": fold_idx,
                "n_predictions": len(fold_preds),
                "accuracy": round(fold_preds["is_correct"].mean(), 4),
                "brier_score": round(calculate_brier_score(
                    fold_preds["ensemble_prob"].values,
                    fold_preds["actual_direction"].values,
                ), 4),
            })

    # Per-regime accuracy
    regime_metrics = {}
    for regime, group in traded.groupby("regime_label"):
        regime_metrics[regime] = {
            "count": len(group),
            "accuracy": round(group["is_correct"].mean(), 4),
        }

    metrics = {
        "total_predictions": len(preds_df),
        "traded_predictions": len(traded),
        "trade_frequency": round(len(traded) / len(preds_df), 4) if len(preds_df) > 0 else 0,
        "overall_accuracy": round(traded["is_correct"].mean(), 4) if not traded.empty else 0,
        "brier_score": round(brier, 4),
        "brier_vs_random": round(brier - 0.25, 4),  # negative = better than random
        "n_folds": len(splits),
        "n_purged_per_fold": horizon_periods,
        "n_embargoed_per_fold": embargo_periods,
        "fold_metrics": fold_metrics,
        "regime_breakdown": regime_metrics,
        "calibration": calibration,
        "validation_method": "purged_walk_forward",
    }

    high_conf = traded[traded["confidence"] >= 0.6]
    if not high_conf.empty:
        metrics["high_conf_accuracy"] = round(high_conf["is_correct"].mean(), 4)
        metrics["high_conf_brier"] = round(calculate_brier_score(
            high_conf["ensemble_prob"].values,
            high_conf["actual_direction"].values,
        ), 4)

    logger.info(
        f"Purged WF validation complete: "
        f"Accuracy={metrics['overall_accuracy']:.2%}, "
        f"Brier={brier:.4f} (vs random 0.25: {brier - 0.25:+.4f}), "
        f"Folds={len(splits)}"
    )

    return {
        "metrics": metrics,
        "predictions": preds_df,
    }
