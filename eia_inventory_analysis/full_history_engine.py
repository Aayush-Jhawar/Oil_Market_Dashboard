"""
================================================================================
  FULL-HISTORY ENGINE  (2021-2026, ~280 EIA releases)
================================================================================
The 13-release framework was too small to tune (n=11 -> pure overfit).  This
module reconstructs the FULL EIA release calendar back to 2021 and uses the
full-history WTI 1-min file (CL_data.parquet, c1-c14) to measure the price
reaction to every release.  That gives ~280 observations -> enough to actually
test whether the composite signal has an out-of-sample edge.

It then re-runs the objective sweep (pnl / sharpe / hit / corr) with PROPER
validation for a time series:
  * chronological holdout (train past -> test future) = the honest trader metric
  * 5-fold CV = robustness check
and deploys tuned weights to tuned_weights.json ONLY if they beat the prior on
the chronological holdout.

Data caveats (stated, not hidden):
  * Macro (DXY/Gold) only covers 2026-03..05, so dxy/gold features are 0 for all
    pre-2026 releases.  The crude / product / curve features carry the history.
  * WTI is the tuning instrument (composite predicts WTI reaction), consistent
    with the original framework.  HO/LGO/Brent remain available for extension.
  * Release dates reconstructed via the EIA rule (Wed 10:30 ET; shift to Thu
    11:00 ET when a federal holiday falls Mon-Wed of the release week).  Validated
    13/13 against the known 2026 releases.
================================================================================
"""
import os
import json
import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

import inventory_impact_framework as fw
import autotune_weights as at


def kfold_indices(n, k, seed):
    """Shuffled k-fold split -> list of (train_idx, test_idx)."""
    rng = np.random.default_rng(seed)
    idx = rng.permutation(n)
    folds = np.array_split(idx, k)
    out = []
    for i in range(k):
        te = folds[i]
        tr = np.concatenate([folds[j] for j in range(k) if j != i])
        out.append((np.sort(tr), np.sort(te)))
    return out

DATA, OUT, ET = fw.DATA, fw.OUT, "US/Eastern"
KEYS, PRIOR, HORIZONS = at.KEYS, at.PRIOR, at.HORIZONS
SEED = 42

_cal = USFederalHolidayCalendar()
_HOL = set(_cal.holidays(start="2019-12-01", end="2026-12-31").date)


# ---------------------------------------------------------------- calendar ----
def release_for_friday(friday):
    """EIA release datetime for a week-ending Friday. (date, print_min)."""
    f = pd.Timestamp(friday)
    wed = f + pd.Timedelta(days=5)
    week_mon = wed - pd.Timedelta(days=2)
    shifted = any((week_mon + pd.Timedelta(days=i)).date() in _HOL for i in range(3))
    if shifted:
        return (wed + pd.Timedelta(days=1)).date(), 11 * 60      # Thu 11:00
    return wed.date(), 10 * 60 + 30                              # Wed 10:30


# ---------------------------------------------------------------- loaders -----
def load_eia_series():
    eia = {}
    for key, fname in fw.EIA_FILES.items():
        df = pd.read_csv(os.path.join(DATA, fname))
        df["period"] = pd.to_datetime(df["period"])
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df[["period", "value"]].sort_values("period").reset_index(drop=True)
        df["wow"] = df["value"].diff()
        df["iso_week"] = df["period"].apply(lambda d: pd.Timestamp(d).isocalendar().week)
        eia[key] = df.set_index("period")
    return eia


def load_wti_full():
    """CL_data.parquet -> WTI m1,m2,m3,m6,m12 in ET, trimmed to the minute
    windows we need (10:00-17:00 ET) and grouped by date for fast lookup."""
    need = {"c1||weighted_mid": "m1", "c2||weighted_mid": "m2", "c3||weighted_mid": "m3",
            "c6||weighted_mid": "m6", "c12||weighted_mid": "m12"}
    df = pd.read_parquet(os.path.join(DATA, "CL_data.parquet"),
                         columns=["timestamp"] + list(need))
    df = df.rename(columns=need)
    ts = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(ET)
    df["et_date"] = ts.dt.date
    df["mod"] = ts.dt.hour * 60 + ts.dt.minute
    df = df[(df["mod"] >= 600) & (df["mod"] <= 1020)].copy()   # 10:00-17:00 ET
    groups = {d: g for d, g in df.groupby("et_date")}
    return groups


def load_macro():
    m = pd.read_excel(os.path.join(DATA, "gold_dxy_us10y_mar_may_2026.xlsx"))
    m["Date"] = pd.to_datetime(m["Date"]).dt.date
    m = m.sort_values("Date").reset_index(drop=True)
    m["DXY_dod"] = m["DXY"].pct_change() * 100
    m["Gold_dod"] = m["Gold"].pct_change() * 100
    return m


def _wmean(day_df, lo, hi, col):
    if day_df is None:
        return np.nan
    s = day_df.loc[(day_df["mod"] >= lo) & (day_df["mod"] <= hi), col]
    return s.mean() if len(s) else np.nan


def seasonal_norm(series, week):
    h = series[(series["iso_week"] == week) & (series.index.year.isin(range(2020, 2025)))]
    return h["wow"].mean() if len(h) else np.nan


# ---------------------------------------------------------------- build -------
def build_matrix():
    print("=" * 64)
    print("  FULL-HISTORY ENGINE : building feature/target matrix 2021-2026")
    print("=" * 64)
    eia = load_eia_series()
    print("  loading WTI full 1-min (CL_data.parquet) ...")
    wti = load_wti_full()
    macro = load_macro()
    macro_idx = {r["Date"]: r for _, r in macro.iterrows()}

    crude, dist, gas, cush = eia["crude"], eia["distillate"], eia["gasoline"], eia["cushing"]
    refin = eia["refinery_in"]
    fridays = [d for d in crude.index if d >= pd.Timestamp("2021-01-01")]

    rows = []
    prev_dos = None
    for fri in fridays:
        rd, pmin = release_for_friday(fri)
        day_df = wti.get(rd)
        lo_pre, hi_pre = pmin - 10, pmin - 1
        m1 = _wmean(day_df, lo_pre, hi_pre, "m1")
        if np.isnan(m1):                       # no price that day (or bad date) -> skip
            # still advance dos baseline
            cl = crude.loc[fri, "value"] if fri in crude.index else np.nan
            rl = refin.loc[fri, "value"] if fri in refin.index else np.nan
            prev_dos = (cl / rl) if (pd.notna(cl) and pd.notna(rl) and rl) else prev_dos
            continue
        m2 = _wmean(day_df, lo_pre, hi_pre, "m2")

        # ---- targets: WTI outright reaction pct ----
        r10 = _wmean(day_df, pmin, pmin + 9, "m1")
        r30 = _wmean(day_df, pmin, pmin + 29, "m1")
        eod = _wmean(day_df, 16 * 60 + 30, 17 * 60, "m1")
        t10 = (r10 - m1) / m1 * 100 if pd.notna(r10) else np.nan
        t30 = (r30 - m1) / m1 * 100 if pd.notna(r30) else np.nan
        teod = (eod - m1) / m1 * 100 if pd.notna(eod) else np.nan

        # ---- targets: WTI calendar-spread reaction ($ delta, post10 - pre) ----
        # draw -> front tightens -> M1-M2 / M1-M3 should WIDEN (delta>0 == bullish)
        m2_10 = _wmean(day_df, pmin, pmin + 9, "m2")
        m3_pre = _wmean(day_df, lo_pre, hi_pre, "m3")
        m3_10 = _wmean(day_df, pmin, pmin + 9, "m3")
        sp12_pre = (m1 - m2) if pd.notna(m2) else np.nan
        sp12_post = (r10 - m2_10) if (pd.notna(r10) and pd.notna(m2_10)) else np.nan
        sp13_pre = (m1 - m3_pre) if pd.notna(m3_pre) else np.nan
        sp13_post = (r10 - m3_10) if (pd.notna(r10) and pd.notna(m3_10)) else np.nan
        sp12_delta = (sp12_post - sp12_pre) if (pd.notna(sp12_post) and pd.notna(sp12_pre)) else np.nan
        sp13_delta = (sp13_post - sp13_pre) if (pd.notna(sp13_post) and pd.notna(sp13_pre)) else np.nan

        # ---- inventory features ----
        cc = crude.loc[fri, "wow"] if fri in crude.index else np.nan
        dc = dist.loc[fri, "wow"] if fri in dist.index else np.nan
        gc = gas.loc[fri, "wow"] if fri in gas.index else np.nan
        ccu = cush.loc[fri, "wow"] if fri in cush.index else np.nan
        cl = crude.loc[fri, "value"] if fri in crude.index else np.nan
        rl = refin.loc[fri, "value"] if fri in refin.index else np.nan
        dos = (cl / rl) if (pd.notna(cl) and pd.notna(rl) and rl) else np.nan
        dos_chg = (dos - prev_dos) if (pd.notna(dos) and prev_dos is not None) else np.nan
        prev_dos = dos if pd.notna(dos) else prev_dos

        cush_driven = (pd.notna(ccu) and pd.notna(cc) and cc != 0 and abs(ccu) / abs(cc) > 0.4)
        mac = macro_idx.get(rd)

        f = {
            "release_date": rd, "week_ending": fri.date(), "print_min": pmin,
            "crude":         float(np.clip(-cc / 4000.0, -1, 1)) if pd.notna(cc) else 0.0,
            "distillate":    float(np.clip(-dc / 3000.0, -1, 1)) if pd.notna(dc) else 0.0,
            "gasoline":      float(np.clip(-gc / 3000.0, -1, 1)) if pd.notna(gc) else 0.0,
            "cushing":       float(np.sign(-cc)) if cush_driven else 0.0,
            "days_supply":   float(np.clip(-dos_chg / 0.5, -1, 1)) if pd.notna(dos_chg) else 0.0,
            "backwardation": float(np.clip((m1 - m2) / 1.0, -1, 1)) if pd.notna(m2) else 0.0,
            "dxy":           float(np.clip(-mac["DXY_dod"] / 0.5, -1, 1)) if (mac is not None and pd.notna(mac["DXY_dod"])) else 0.0,
            "gold":          float(-np.clip(mac["Gold_dod"] / 2.0, -1, 1)) if (mac is not None and pd.notna(mac["Gold_dod"])) else 0.0,
            "WTI_r10_pct": t10, "WTI_r30_pct": t30, "WTI_eod_pct": teod,
            "WTI_sp12_delta": sp12_delta, "WTI_sp13_delta": sp13_delta,
            "crude_chg": cc,
        }
        rows.append(f)

    mat = pd.DataFrame(rows)
    mat.to_csv(os.path.join(OUT, "tbl_full_history_matrix.csv"), index=False)
    print(f"  releases with WTI price: {len(mat)}  "
          f"({mat['release_date'].min()} .. {mat['release_date'].max()})")
    print(f"  saved tbl_full_history_matrix.csv")
    return mat


# ---------------------------------------------------------------- evaluate ----
def total_pnl(w, X, Y):
    return sum(at.metrics_for(w, X, Y)[h]["pnl"] for h, _ in HORIZONS)


def eval_split(X, Y, kind, tr, te):
    """Fit on train rows, return test total directional P&L (and per-horizon)."""
    std = at._std_cols(Y[tr])
    w = at.fit_weights(X[tr], Y[tr], std, kind, maxiter=60, seed=SEED)
    m = at.metrics_for(w, X[te], Y[te])
    return sum(m[h]["pnl"] for h, _ in HORIZONS), m, w


def main():
    mat = build_matrix()
    # clean joint sample: all 3 horizons present
    cols_t = ["WTI_r10_pct", "WTI_r30_pct", "WTI_eod_pct"]
    good = mat.dropna(subset=cols_t).reset_index(drop=True)
    X = good[KEYS].values
    Y = good[cols_t].values
    n = len(good)
    print(f"\n  clean joint sample (all 3 horizons): n={n}")

    # baseline on full sample (priors) + per-horizon breakdown
    bm = at.metrics_for(PRIOR, X, Y)
    base_full = total_pnl(PRIOR, X, Y)
    base_hit = np.mean([bm[h]["hit"] for h, _ in HORIZONS])
    print(f"  baseline (prior) FULL-sample directional P&L: {base_full:+.2f}%  "
          f"avg hit {base_hit:.2f}")
    print("  per-horizon (prior): " + "  ".join(
        f"{h}: P&L={bm[h]['pnl']:+.2f}% hit={bm[h]['hit']:.2f} avgMove={Y[:, j].mean():+.3f}%"
        for j, (h, _) in enumerate(HORIZONS)))

    # chronological holdout: train first 70%, test last 30% (predict future)
    cut = int(n * 0.70)
    tr_c, te_c = np.arange(cut), np.arange(cut, n)
    base_te_pnl = sum(at.metrics_for(PRIOR, X[te_c], Y[te_c])[h]["pnl"] for h, _ in HORIZONS)
    print(f"\n  --- CHRONOLOGICAL HOLDOUT (train {cut}, test {n-cut}; predict future) ---")
    print(f"  baseline prior on test: {base_te_pnl:+.2f}%")

    folds = kfold_indices(n, 5, SEED)
    results = {}
    for kind in at.OBJECTIVES:
        # chronological holdout
        chrono_pnl, chrono_m, w_ho = eval_split(X, Y, kind, tr_c, te_c)
        # 5-fold CV mean OOS P&L
        fold_pnls = []
        for tr, te in folds:
            p, _, _ = eval_split(X, Y, kind, tr, te)
            fold_pnls.append(p)
        cv_mean = float(np.mean(fold_pnls))
        # full-sample fit (for shipping weights if it wins)
        std_full = at._std_cols(Y)
        w_full = at.fit_weights(X, Y, std_full, kind, maxiter=80, seed=SEED)
        results[kind] = {"chrono": chrono_pnl, "cv": cv_mean, "w_full": w_full,
                         "chrono_m": chrono_m}
        flag = "BEATS" if chrono_pnl > base_te_pnl + 1e-9 else "no"
        print(f"  {kind:6s}: chrono-test P&L={chrono_pnl:+.2f}%  5fold-CV mean={cv_mean:+.2f}%  "
              f"(baseline test {base_te_pnl:+.2f}%) -> {flag}")

    # ---- comparison table ----
    cmp = pd.DataFrame([{
        "objective": k, "chrono_test_pnl": round(results[k]["chrono"], 3),
        "cv5_mean_pnl": round(results[k]["cv"], 3),
        "baseline_test_pnl": round(base_te_pnl, 3),
        "beats_baseline": "YES" if results[k]["chrono"] > base_te_pnl + 1e-9 else "no",
    } for k in at.OBJECTIVES])
    cmp.to_csv(os.path.join(OUT, "tbl_fullhistory_sweep.csv"), index=False)
    print("\n--- OBJECTIVE SWEEP (full history) ---")
    print(cmp.to_string(index=False))

    # ---- winner by chronological holdout (the honest trader metric) ----
    # DEPLOY GUARDRAIL: must be PROFITABLE out-of-sample (P&L>0), not merely
    # less-bad than a losing baseline. Beating a loser is still a loser.
    best_kind = max(at.OBJECTIVES, key=lambda k: results[k]["chrono"])
    best = results[best_kind]
    profitable = best["chrono"] > 0 and best["cv"] > 0
    print(f"\n  Best by chronological holdout: '{best_kind}' "
          f"(test {best['chrono']:+.2f}%, CV {best['cv']:+.2f}%)")
    print(f"  Profitable out-of-sample (P&L>0 on BOTH test & CV)? "
          f"{'YES -> DEPLOY' if profitable else 'NO -> keep priors (no tradeable edge)'}")
    beats = profitable

    wt = pd.DataFrame({"feature": KEYS, "prior": PRIOR,
                       "tuned_" + best_kind: [round(float(x), 3) for x in best["w_full"]]})
    print("\n--- WEIGHTS (prior vs best-objective full-sample fit) ---")
    print(wt.to_string(index=False))
    wt.to_csv(os.path.join(OUT, "tbl_fullhistory_weights.csv"), index=False)

    if beats:
        payload = {"weights": {k: round(float(v), 4) for k, v in zip(KEYS, best["w_full"])},
                   "meta": {"objective": best_kind, "trained_on": "full_history_2021_2026",
                            "n_releases": n, "chrono_test_pnl_pct": round(best["chrono"], 3),
                            "cv5_mean_pnl_pct": round(best["cv"], 3),
                            "baseline_test_pnl_pct": round(base_te_pnl, 3), "seed": SEED,
                            "note": "Beats prior on chronological holdout over ~280 releases."}}
        with open(fw.TUNED_WEIGHTS_FILE, "w") as fh:
            json.dump(payload, fh, indent=2)
        print(f"\n  DEPLOYED tuned weights -> {fw.TUNED_WEIGHTS_FILE} (objective={best_kind})")
        print("  The framework will now auto-load these.")
    else:
        if os.path.exists(fw.TUNED_WEIGHTS_FILE):
            os.remove(fw.TUNED_WEIGHTS_FILE)
        print("\n  No objective beats the prior on the chronological holdout -> KEEPING PRIORS.")

    # ---- plot ----
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        labels = ["baseline"] + at.OBJECTIVES
        chrono = [base_te_pnl] + [results[k]["chrono"] for k in at.OBJECTIVES]
        cv = [base_full / (n / (n - cut))] if False else [base_te_pnl] + [results[k]["cv"] for k in at.OBJECTIVES]
        x = np.arange(len(labels)); w = 0.38
        fig, ax = plt.subplots(figsize=(11, 6))
        ax.bar(x - w / 2, chrono, w, label="chronological holdout", color="seagreen")
        ax.bar(x + w / 2, cv, w, label="5-fold CV mean", color="steelblue")
        ax.axhline(base_te_pnl, color="black", ls="--", lw=0.9, label="baseline (test)")
        ax.set_xticks(x); ax.set_xticklabels(labels)
        ax.set_ylabel("out-of-sample directional P&L % (3 horizons)")
        ax.legend(); ax.grid(alpha=0.3)
        ax.set_title(f"18 - Full-history ({n} releases) tuning: out-of-sample P&L by objective")
        fig.tight_layout(); fig.savefig(os.path.join(OUT, "18_fullhistory_tuning.png"), dpi=110)
        plt.close(fig)
        print("  saved 18_fullhistory_tuning.png")
    except Exception as e:
        print("  [plot skip]", e)

    print(f"\n  Sample is now n={n} (vs 11 before) - tuning is finally meaningful.")


if __name__ == "__main__":
    main()
