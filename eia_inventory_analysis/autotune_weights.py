"""
================================================================================
  COMPOSITE WEIGHT AUTOTUNER
================================================================================
Starts from the hand-set priors (inventory_impact_framework.COMPOSITE_WEIGHTS_PRIOR)
and tunes the 8 composite weights to MAXIMISE DIRECTIONAL P&L jointly across all
three horizons (10-min / 30-min / EOD).

Design choices made to fight the n=11 overfit problem:
  * Objective standardises each horizon's reactions (so big EOD moves don't swamp
    the 10-min signal) and AVERAGES across horizons -> improves all three at once.
  * Weights are non-negative and multiply sign-locked features, so the economic
    sign of every term is preserved (a crude draw can never become bearish).
  * L2 regularisation pulls weights toward the priors.
  * The honest scorecard is LEAVE-ONE-OUT cross-validation (refit on 10, predict
    the held-out release).  In-sample numbers are shown too but are optimistic.

Outputs: tuned_weights.json, output/tbl_weight_tuning.csv,
         output/16_weight_tuning.png, output/17_pnl_tuning_compare.png
================================================================================
"""
import os
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats
from scipy.optimize import differential_evolution

import inventory_impact_framework as fw

HORIZONS = [("10min", "WTI_r10_pct"), ("30min", "WTI_r30_pct"), ("EOD", "WTI_eod_pct")]
LAMBDA = 0.05          # L2 strength toward priors
SEED = 42
KEYS = list(fw.COMPOSITE_WEIGHTS_PRIOR.keys())
PRIOR = np.array([fw.COMPOSITE_WEIGHTS_PRIOR[k] for k in KEYS])
BOUNDS = [(0.0, 3.0 * p) for p in PRIOR]   # non-negative, capped at 3x prior


# ---------------------------------------------------------------- data --------
def get_features_and_targets():
    D = fw.load_data()
    fw.compute_inventory_wow(D)
    fw.build_pretrade_signal(D)
    fw.compute_price_reactions(D)
    feat = fw.build_feature_matrix(D)
    rx = D["rx"].set_index("release_date")
    # releases that have ALL three horizon reactions (clean joint sample)
    tgt = {}
    for name, col in HORIZONS:
        tgt[name] = rx[col].reindex(feat.index)
    tdf = pd.DataFrame(tgt)
    mask = tdf.notna().all(axis=1)
    X = feat.loc[mask, KEYS].values
    Y = tdf.loc[mask].values            # columns: 10min, 30min, EOD
    dates = list(feat.index[mask])
    return D, feat, X, Y, dates


# ---------------------------------------------------------------- objective ---
def _std_cols(Y):
    s = Y.std(axis=0, ddof=0)
    s[s == 0] = 1.0
    return s


# Objectives to sweep. Each maps weights -> a scalar to MAXIMISE, averaged over
# the 3 horizons, all standardised so no single horizon dominates.
OBJECTIVES = ["pnl", "sharpe", "hit", "corr"]


def _objective_value(scores, Y, std, kind):
    """Scalar (higher=better), averaged across the 3 standardised horizons."""
    pos = np.sign(scores)
    Z = Y / std
    if kind == "pnl":                            # directional P&L
        return (pos[:, None] * Z).mean(axis=0).mean()
    if kind == "sharpe":                         # mean/std of per-release P&L
        p = pos[:, None] * Z
        mu, sd = p.mean(axis=0), p.std(axis=0, ddof=0)
        sd[sd == 0] = 1.0
        return (mu / sd).mean()
    if kind == "hit":                            # sign-agreement rate
        return np.mean([(pos == np.sign(Y[:, j])).mean() for j in range(Y.shape[1])])
    if kind == "corr":                           # Pearson r (scale-invariant)
        if np.std(scores) == 0:
            return -1.0
        return np.mean([stats.pearsonr(scores, Y[:, j])[0] for j in range(Y.shape[1])])
    raise ValueError(kind)


def neg_objective(w, X, Y, std, kind):
    obj = _objective_value(X @ w, Y, std, kind)
    reg = LAMBDA * np.sum(((w - PRIOR) / PRIOR) ** 2)
    return -(obj) + reg


def fit_weights(X, Y, std, kind, maxiter=80, seed=SEED):
    res = differential_evolution(
        neg_objective, BOUNDS, args=(X, Y, std, kind),
        seed=seed, maxiter=maxiter, popsize=18, tol=1e-7,
        mutation=(0.5, 1.0), recombination=0.7, polish=True)
    return res.x


# ---------------------------------------------------------------- metrics -----
def metrics_for(w, X, Y):
    """Raw directional P&L (%), hit rate, and Pearson r per horizon."""
    scores = X @ w
    pos = np.sign(scores)
    out = {}
    for j, (name, _) in enumerate(HORIZONS):
        y = Y[:, j]
        pnl = float(np.sum(pos * y))
        hit = float(np.mean(pos == np.sign(y)))
        r = float(stats.pearsonr(scores, y)[0]) if np.std(scores) > 0 else np.nan
        out[name] = {"pnl": pnl, "hit": hit, "r": r}
    return out


def loo_metrics(X, Y, std, kind):
    """Leave-one-out: refit on n-1, score the held-out release. Honest scorecard."""
    n = X.shape[0]
    pos_oos = np.zeros(n)
    scores_oos = np.zeros(n)
    for i in range(n):
        tr = [k for k in range(n) if k != i]
        w_i = fit_weights(X[tr], Y[tr], std, kind, maxiter=50, seed=SEED + i)
        s = float(X[i] @ w_i)
        scores_oos[i] = s
        pos_oos[i] = np.sign(s)
    out = {}
    for j, (name, _) in enumerate(HORIZONS):
        y = Y[:, j]
        out[name] = {
            "pnl": float(np.sum(pos_oos * y)),
            "hit": float(np.mean(pos_oos == np.sign(y))),
            "r": float(stats.pearsonr(scores_oos, y)[0]) if np.std(scores_oos) > 0 else np.nan,
        }
    return out, scores_oos


# ---------------------------------------------------------------- main --------
def _total_pnl(metrics):
    return sum(metrics[h]["pnl"] for h, _ in HORIZONS)


def main():
    print("=" * 64)
    print("  COMPOSITE WEIGHT AUTOTUNER  (objective sweep, all 3 horizons)")
    print("=" * 64)
    D, feat, X, Y, dates = get_features_and_targets()
    std = _std_cols(Y)
    n = X.shape[0]
    print(f"\n  Joint sample (all 3 horizons present): n={n} releases")
    print(f"  {', '.join(str(d) for d in dates)}")
    print(f"  Sweeping objectives: {OBJECTIVES}\n")

    base_in = metrics_for(PRIOR, X, Y)
    base_pnl = _total_pnl(base_in)

    # ---- sweep every objective ----
    results = {}
    for kind in OBJECTIVES:
        w_t = fit_weights(X, Y, std, kind)
        is_m = metrics_for(w_t, X, Y)
        loo_m, _ = loo_metrics(X, Y, std, kind)
        results[kind] = {"w": w_t, "is": is_m, "loo": loo_m,
                         "pnl_is": _total_pnl(is_m), "pnl_loo": _total_pnl(loo_m)}
        print(f"  objective={kind:6s} | totalP&L  in-sample={results[kind]['pnl_is']:+.3f}%  "
              f"LOO(out-of-sample)={results[kind]['pnl_loo']:+.3f}%  "
              f"(baseline {base_pnl:+.3f}%)")

    # ---- comparison table (LOO is the honest column) ----
    print("\n--- OBJECTIVE COMPARISON (totals across 3 horizons) ---")
    cmp_rows = [{"objective": "baseline(prior)", "pnl_in_sample": round(base_pnl, 3),
                 "pnl_LOO": round(base_pnl, 3),
                 "beats_baseline_LOO": "-"}]
    for kind in OBJECTIVES:
        cmp_rows.append({
            "objective": kind,
            "pnl_in_sample": round(results[kind]["pnl_is"], 3),
            "pnl_LOO": round(results[kind]["pnl_loo"], 3),
            "beats_baseline_LOO": "YES" if results[kind]["pnl_loo"] > base_pnl + 1e-9 else "no",
        })
    cmp = pd.DataFrame(cmp_rows)
    print(cmp.to_string(index=False))
    cmp.to_csv(os.path.join(fw.OUT, "tbl_objective_sweep.csv"), index=False)

    # ---- pick winner by honest LOO P&L; require it to beat baseline ----
    best_kind = max(OBJECTIVES, key=lambda k: results[k]["pnl_loo"])
    best = results[best_kind]
    beats = best["pnl_loo"] > base_pnl + 1e-9
    print(f"\n  Best objective by out-of-sample P&L: '{best_kind}' "
          f"(LOO {best['pnl_loo']:+.3f}% vs baseline {base_pnl:+.3f}%)  "
          f"-> {'BEATS baseline' if beats else 'does NOT beat baseline'}")

    # per-horizon scorecard for the winner
    sc = pd.DataFrame([{
        "horizon": h,
        "pnl_baseline": round(base_in[h]["pnl"], 3),
        "pnl_winner_IS": round(best["is"][h]["pnl"], 3),
        "pnl_winner_LOO": round(best["loo"][h]["pnl"], 3),
        "hit_baseline": round(base_in[h]["hit"], 2),
        "hit_winner_LOO": round(best["loo"][h]["hit"], 2),
    } for h, _ in HORIZONS])
    print(f"\n--- WINNER ('{best_kind}') PER-HORIZON SCORECARD ---")
    print(sc.to_string(index=False))
    sc.to_csv(os.path.join(fw.OUT, "tbl_tuning_scorecard.csv"), index=False)

    # ---- decide what to ship: only deploy tuned if it beats baseline OOS ----
    if beats:
        ship_w = best["w"]; ship_kind = best_kind; ship = "tuned"
    else:
        ship_w = PRIOR; ship_kind = "prior"; ship = "prior"
        if os.path.exists(fw.TUNED_WEIGHTS_FILE):
            os.remove(fw.TUNED_WEIGHTS_FILE)
        print("\n  No objective beats the prior out-of-sample -> KEEPING PRIORS.")
        print("  (removed any stale tuned_weights.json so the framework uses priors)")

    wt = pd.DataFrame({"feature": KEYS, "prior": PRIOR,
                       "best_" + best_kind: [round(float(x), 3) for x in best["w"]],
                       "shipped": [round(float(x), 3) for x in ship_w]})
    print("\n--- WEIGHTS (prior vs best-objective vs shipped) ---")
    print(wt.to_string(index=False))
    wt.to_csv(os.path.join(fw.OUT, "tbl_weight_tuning.csv"), index=False)

    if ship == "tuned":
        payload = {"weights": {k: round(float(v), 4) for k, v in zip(KEYS, ship_w)},
                   "meta": {"objective": ship_kind, "n_releases": n, "lambda_l2": LAMBDA,
                            "seed": SEED, "pnl_loo_pct": round(best["pnl_loo"], 3),
                            "pnl_baseline_pct": round(base_pnl, 3),
                            "note": "Beats prior out-of-sample on n=11 - still fragile; re-run as data grows."}}
        with open(fw.TUNED_WEIGHTS_FILE, "w") as fh:
            json.dump(payload, fh, indent=2)
        print(f"\n  wrote {fw.TUNED_WEIGHTS_FILE} (objective={ship_kind})")

    # ---- plots ----
    try:
        fig, ax = plt.subplots(figsize=(11, 6))
        x = np.arange(len(KEYS)); w = 0.8 / (len(OBJECTIVES) + 1)
        ax.bar(x - 0.4 + w / 2, PRIOR, w, label="prior", color="black")
        for i, kind in enumerate(OBJECTIVES):
            ax.bar(x - 0.4 + w * (i + 1) + w / 2, results[kind]["w"], w, label=kind)
        ax.set_xticks(x); ax.set_xticklabels(KEYS, rotation=30, ha="right")
        ax.set_ylabel("weight"); ax.legend(ncol=3); ax.grid(alpha=0.3)
        ax.set_title("16 - Composite weights: prior vs each tuning objective")
        fig.tight_layout(); fig.savefig(os.path.join(fw.OUT, "16_weight_tuning.png"), dpi=110)
        plt.close(fig); print("\n  saved 16_weight_tuning.png")

        fig, ax = plt.subplots(figsize=(11, 6))
        labels = ["baseline"] + OBJECTIVES
        is_vals = [base_pnl] + [results[k]["pnl_is"] for k in OBJECTIVES]
        loo_vals = [base_pnl] + [results[k]["pnl_loo"] for k in OBJECTIVES]
        xb = np.arange(len(labels)); w = 0.38
        ax.bar(xb - w / 2, is_vals, w, label="in-sample", color="orange")
        ax.bar(xb + w / 2, loo_vals, w, label="LOO (out-of-sample)", color="seagreen")
        ax.axhline(base_pnl, color="black", ls="--", lw=0.9, label="baseline level")
        ax.set_xticks(xb); ax.set_xticklabels(labels)
        ax.set_ylabel("total directional P&L % (3 horizons)"); ax.legend(); ax.grid(alpha=0.3)
        ax.set_title("17 - Total P&L by objective: in-sample vs out-of-sample")
        fig.tight_layout(); fig.savefig(os.path.join(fw.OUT, "17_pnl_tuning_compare.png"), dpi=110)
        plt.close(fig); print("  saved 17_pnl_tuning_compare.png")
    except Exception as e:
        print("  [plot skip]", e)

    print("\n  [!] n=11: any 'winner' is a prior-informed hypothesis, not a validated")
    print("      edge. The framework only deploys tuned weights if they beat the")
    print("      prior OUT-OF-SAMPLE; otherwise it keeps the priors. Re-run as data grows.")


if __name__ == "__main__":
    main()
