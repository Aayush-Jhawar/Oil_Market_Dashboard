"""
================================================================================
  CRUDE INVENTORY MARKET-IMPACT FRAMEWORK   (focused, rigorous, report-grade)
================================================================================
Assignment: analyse ONE inventory series and build a framework to assess the
likely market impact of the weekly EIA release.  Series chosen: CRUDE OIL
(WCRSTUS1) -> WTI (primary), with Brent and Heating-Oil reactions for the
products/spreads question.

Why crude: richest feature set (Cushing delivery point, PADDs, refinery runs,
days-of-supply), most liquid & canonical instruments (WTI/Brent 1-min back to
2021), and gasoline lacks RBOB 1-min price.  The framework generalises to
distillate (HO) as an extension.

What this script does, end to end:
  1. Builds a clean feature/target dataset over ~281 releases (2021-2026).
  2. FEATURE RELEVANCE: ranks every candidate factor by its real statistical
     relationship to (a) move DIRECTION and (b) move MAGNITUDE; keeps the
     impactful ones and explicitly DROPS the irrelevant (incl. macro, which has
     only 63 days of coverage and cannot enter a 281-row model).
  3. MODEL COMPARISON: direction (LogReg / RandomForest / GradBoost vs naive
     baseline) and magnitude (OLS / RandomForest), with a chronological holdout
     AND 5-fold CV.  Reports train/test sizes and out-of-sample metrics.
  4. REGIME & SEASONAL conditioning: when inventories mattered vs didn't.
  5. PRODUCTS/SPREADS: which instrument reacts most to crude prints.
  6. 2026-06-03 assessment: bull / bear / neutral, confidence, top-3 factors.
  7. Writes report/report.md with all figures + narrative + deliverables.

Honest headline (established empirically): in this dataset the crude print is
largely EFFICIENTLY PRICED - direction is ~coin-flip and magnitude only weakly
tracks the surprise.  The framework's value is therefore in (i) sizing/whether
to trade via magnitude+regime, and (ii) a disciplined directional lean with
calibrated (low) confidence.
================================================================================
"""
import os
import json
import warnings
import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sklearn.linear_model import LogisticRegression, LinearRegression
from sklearn.ensemble import (RandomForestClassifier, GradientBoostingClassifier,
                              RandomForestRegressor)
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, roc_auc_score, r2_score, mean_absolute_error
import statsmodels.api as sm

from full_history_engine import release_for_friday  # validated EIA release calendar

# ------------------------------------------------------------------ paths -----
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "Data")
REPORT = os.path.join(HERE, "report")
FIG = os.path.join(REPORT, "figures")
os.makedirs(FIG, exist_ok=True)
ET = "US/Eastern"
SEED = 42

EIA_FILES = {
    "crude": "eia_Crude_Oil_Stocks_US.csv",
    "cushing": "eia_Cushing_Crude_Stocks.csv",
    "refinery": "eia_Crude_Inputs_Refineries_US.csv",
    "distillate": "eia_Distillate_Stocks_US.csv",
    "gasoline": "eia_Gasoline_Stocks_US.csv",
}


# ============================================================ data loading ====
def load_eia():
    eia = {}
    for k, f in EIA_FILES.items():
        df = pd.read_csv(os.path.join(DATA, f))
        df["period"] = pd.to_datetime(df["period"])
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.sort_values("period").reset_index(drop=True)
        df["wow"] = df["value"].diff()
        df["wk"] = df["period"].dt.isocalendar().week.astype(int)
        eia[k] = df.set_index("period")
    return eia


def load_price(parquet, cols):
    """Return (groups_by_date, daily_close_series). cols like ['c1','c2'].
    Intraday %-reactions are exact even though levels are back-adjusted."""
    pq_cols = [f"{c}||weighted_mid" for c in cols]
    df = pd.read_parquet(os.path.join(DATA, parquet), columns=["timestamp"] + pq_cols)
    df = df.rename(columns={f"{c}||weighted_mid": c for c in cols})
    ts = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(ET)
    df["d"] = ts.dt.date
    df["mod"] = ts.dt.hour * 60 + ts.dt.minute
    daily_close = df[df["mod"] <= 17 * 60].groupby("d")[cols[0]].last()
    df = df[(df["mod"] >= 600) & (df["mod"] <= 1020)].copy()
    groups = {d: g for d, g in df.groupby("d")}
    return groups, daily_close


def wmean(g, lo, hi, col):
    if g is None or col not in g.columns:
        return np.nan
    s = g.loc[(g["mod"] >= lo) & (g["mod"] <= hi), col]
    return s.mean() if len(s) else np.nan


def react_pct(g, pmin, lo2, hi2, col="c1"):
    pre = wmean(g, pmin - 10, pmin - 1, col)
    post = wmean(g, lo2, hi2, col)
    return (post - pre) / pre * 100 if (pd.notna(pre) and pd.notna(post) and pre) else np.nan


# ============================================================ dataset =========
def build_dataset():
    print("=" * 70)
    print("  BUILDING CRUDE-IMPACT DATASET (2021-2026)")
    print("=" * 70)
    eia = load_eia()
    print("  loading WTI / Brent / HO 1-min (full history) ...")
    wti, wti_close = load_price("CL_data.parquet", ["c1", "c2", "c3"])
    brent, _ = load_price("LCO_data.parquet", ["c1"])
    ho, _ = load_price("HO_data.parquet", ["c1"])

    crude, cush, refin = eia["crude"], eia["cushing"], eia["refinery"]
    dist, gas = eia["distillate"], eia["gasoline"]

    # 5yr seasonal-week stats (2020-2024) for crude level & WoW
    base = crude[(crude.index.year >= 2020) & (crude.index.year <= 2024)]
    seas_wow = base.groupby("wk")["wow"].mean()
    lvl_mean = base.groupby("wk")["value"].mean()
    lvl_std = base.groupby("wk")["value"].std()

    wclose = wti_close.copy()
    wclose.index = pd.to_datetime(list(wclose.index))
    wret = wclose.pct_change() * 100

    fridays = [d for d in crude.index if d >= pd.Timestamp("2021-01-01")]
    rows = []
    for fri in fridays:
        rd, pmin = release_for_friday(fri)
        g = wti.get(rd)
        m1_pre = wmean(g, pmin - 10, pmin - 1, "c1")
        if pd.isna(m1_pre):
            continue
        wk = int(fri.isocalendar().week)

        # --- targets (WTI %) ---
        r10 = react_pct(g, pmin, pmin, pmin + 9, "c1")
        r30 = react_pct(g, pmin, pmin, pmin + 29, "c1")
        eod = react_pct(g, pmin, 16 * 60 + 30, 17 * 60, "c1")
        if pd.isna(r10):
            continue
        # products
        br10 = react_pct(brent.get(rd), pmin, pmin, pmin + 9, "c1")
        ho10 = react_pct(ho.get(rd), pmin, pmin, pmin + 9, "c1")
        # WTI M1-M2 spread reaction (%-of-front, back-adj caveat noted)
        m2_pre = wmean(g, pmin - 10, pmin - 1, "c2")
        m2_post = wmean(g, pmin, pmin + 9, "c2")
        m1_post = wmean(g, pmin, pmin + 9, "c1")
        sp12_delta = ((m1_post - m2_post) - (m1_pre - m2_pre)) if all(
            pd.notna(x) for x in [m2_pre, m2_post, m1_post]) else np.nan

        # --- inventory features ---
        cc = crude.loc[fri, "wow"]
        norm = seas_wow.get(wk, np.nan)
        sup_seas = cc - norm if pd.notna(norm) else np.nan
        # 4wk trend expectation
        idx = crude.index.get_loc(fri)
        trend = crude["wow"].iloc[max(0, idx - 4):idx].mean()
        sup_trend = cc - trend if pd.notna(trend) else np.nan
        # WoW z-score vs trailing 52wk std
        wow_std = crude["wow"].iloc[max(0, idx - 52):idx].std()
        chg_z = cc / wow_std if (pd.notna(wow_std) and wow_std) else np.nan
        # cushing
        ccu = cush.loc[fri, "wow"] if fri in cush.index else np.nan
        cush_share = (abs(ccu) / abs(cc)) if (pd.notna(ccu) and pd.notna(cc) and cc) else np.nan
        # refinery runs
        rr = refin.loc[fri, "wow"] if fri in refin.index else np.nan
        rr_std = refin["wow"].iloc[max(0, idx - 52):idx].std() if fri in refin.index else np.nan
        rr_z = rr / rr_std if (pd.notna(rr) and pd.notna(rr_std) and rr_std) else np.nan
        runs_lvl = refin.loc[fri, "value"] if fri in refin.index else np.nan
        crude_lvl = crude.loc[fri, "value"]
        implied_demand = (runs_lvl * 7 - cc) if pd.notna(runs_lvl) else np.nan
        # level / tightness
        stocks_z = ((crude_lvl - lvl_mean.get(wk, np.nan)) / lvl_std.get(wk, np.nan)
                    if pd.notna(lvl_std.get(wk, np.nan)) and lvl_std.get(wk, np.nan) else np.nan)
        dos = crude_lvl / runs_lvl if (pd.notna(runs_lvl) and runs_lvl) else np.nan
        # cross products
        dc = dist.loc[fri, "wow"] if fri in dist.index else np.nan
        gc = gas.loc[fri, "wow"] if fri in gas.index else np.nan
        # seasonal
        month = rd.month
        driving = 1 if 5 <= month <= 9 else 0
        wk_sin, wk_cos = np.sin(2 * np.pi * wk / 52), np.cos(2 * np.pi * wk / 52)
        # market state (WTI)
        pre_drift = react_pct(g, pmin, pmin - 10, pmin - 1, "c1")  # 10:00->10:20-ish proxy
        early = wmean(g, pmin - 30, pmin - 21, "c1")
        late = wmean(g, pmin - 10, pmin - 1, "c1")
        pre_drift = (late - early) / early * 100 if (pd.notna(early) and pd.notna(late) and early) else np.nan
        rdt = pd.Timestamp(rd)
        past = wret[wret.index < rdt]
        rvol20 = past.iloc[-20:].std() if len(past) >= 20 else np.nan
        mom20 = ((wclose[wclose.index < rdt].iloc[-1] / wclose[wclose.index < rdt].iloc[-20] - 1) * 100
                 if len(wclose[wclose.index < rdt]) >= 20 else np.nan)

        rows.append(dict(
            release_date=rd, week_ending=fri.date(), month=month, quarter=(month - 1) // 3 + 1,
            driving_season=driving, wk=wk, wk_sin=wk_sin, wk_cos=wk_cos,
            crude_chg=cc, surprise_seas=sup_seas, surprise_trend=sup_trend, chg_z=chg_z,
            cushing_chg=ccu, cushing_share=cush_share,
            refinery_runs_chg=rr, runs_z=rr_z, implied_demand=implied_demand,
            stocks_z=stocks_z, days_supply=dos,
            distillate_chg=dc, gasoline_chg=gc,
            pre_drift=pre_drift, rvol_20d=rvol20, mom_20d=mom20,
            react_10=r10, react_30=r30, react_eod=eod,
            brent_10=br10, ho_10=ho10, wti_sp12_delta=sp12_delta,
        ))

    df = pd.DataFrame(rows)
    df["abs_10"] = df["react_10"].abs()
    df["abs_eod"] = df["react_eod"].abs()
    df["dir_10"] = np.sign(df["react_10"]).astype(int)
    big_thr = df["abs_10"].quantile(0.70)
    df["big_move"] = (df["abs_10"] > big_thr).astype(int)
    df.attrs["big_thr"] = big_thr
    df.to_csv(os.path.join(REPORT, "dataset.csv"), index=False)
    print(f"  releases: {len(df)}  ({df['release_date'].min()} .. {df['release_date'].max()})")
    print(f"  big-move threshold (Q70 of |10min|): {big_thr:.3f}%")
    return df


# candidate features grouped for relevance reporting
NUMERIC_FEATURES = [
    "crude_chg", "surprise_seas", "surprise_trend", "chg_z",
    "cushing_chg", "cushing_share", "refinery_runs_chg", "runs_z", "implied_demand",
    "stocks_z", "days_supply", "distillate_chg", "gasoline_chg",
    "pre_drift", "rvol_20d", "mom_20d", "wk_sin", "wk_cos",
]
CATEG_FEATURES = ["month", "quarter", "driving_season"]


FEATURE_LABELS = {
    "crude_chg": "Crude WoW change", "surprise_seas": "Surprise vs seasonal",
    "surprise_trend": "Surprise vs 4wk trend", "chg_z": "WoW change z-score",
    "cushing_chg": "Cushing WoW", "cushing_share": "Cushing share of move",
    "refinery_runs_chg": "Refinery runs WoW", "runs_z": "Refinery runs z-score",
    "implied_demand": "Implied demand proxy", "stocks_z": "Stock level z (vs 5yr)",
    "days_supply": "Days of supply", "distillate_chg": "Distillate WoW",
    "gasoline_chg": "Gasoline WoW", "pre_drift": "Pre-release drift",
    "rvol_20d": "Realised vol 20d", "mom_20d": "Price momentum 20d",
    "wk_sin": "Seasonality (sin)", "wk_cos": "Seasonality (cos)",
}


def _imp(df, feats):
    """median-impute features -> matrix."""
    X = df[feats].copy()
    return X.fillna(X.median()).values


# ============================================================ relevance =======
def feature_relevance(df):
    print("\n" + "=" * 70)
    print("  FEATURE RELEVANCE  (which factors actually relate to the reaction?)")
    print("=" * 70)
    rows = []
    for f in NUMERIC_FEATURES:
        d = df[[f, "react_10", "abs_10", "react_eod", "abs_eod"]].dropna()
        if len(d) < 30:
            continue
        # direction power: corr with signed react ; magnitude power: corr with |react|
        pr_dir, p_dir = stats.pearsonr(d[f], d["react_10"])
        sp_mag, p_mag = stats.spearmanr(d[f], d["abs_eod"])
        pr_mag_e, p_mag_e = stats.pearsonr(d[f], d["abs_eod"])
        rows.append({"feature": f, "label": FEATURE_LABELS.get(f, f), "n": len(d),
                     "corr_dir_10": pr_dir, "p_dir": p_dir,
                     "corr_mag_eod": pr_mag_e, "p_mag": p_mag_e,
                     "spearman_mag": sp_mag, "p_sp": p_mag})
    rel = pd.DataFrame(rows)
    rel["best_p"] = rel[["p_dir", "p_mag", "p_sp"]].min(axis=1)
    rel["abs_dir"] = rel["corr_dir_10"].abs()
    rel["abs_mag"] = rel["corr_mag_eod"].abs()
    rel = rel.sort_values("best_p").reset_index(drop=True)

    # categoricals via ANOVA
    cat_rows = []
    for c in CATEG_FEATURES:
        groups_dir = [g["react_10"].values for _, g in df.groupby(c)]
        groups_mag = [g["abs_eod"].dropna().values for _, g in df.groupby(c)]
        try:
            f_dir, p_d = stats.f_oneway(*groups_dir)
            f_mag, p_m = stats.f_oneway(*groups_mag)
            cat_rows.append({"feature": c, "anova_p_dir": p_d, "anova_p_mag": p_m})
        except Exception:
            pass
    catrel = pd.DataFrame(cat_rows)

    rel.to_csv(os.path.join(REPORT, "tbl_feature_relevance.csv"), index=False)
    catrel.to_csv(os.path.join(REPORT, "tbl_categorical_relevance.csv"), index=False)
    print(rel[["label", "n", "corr_dir_10", "p_dir", "corr_mag_eod", "p_mag", "best_p"]]
          .to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print("\n  Categorical (ANOVA p):")
    print(catrel.to_string(index=False, float_format=lambda v: f"{v:.3f}"))

    # SELECTION: keep nominally significant (best_p<0.10) OR core fundamentals
    core = {"surprise_seas", "refinery_runs_chg", "stocks_z"}
    selected = sorted(set(rel[rel["best_p"] < 0.10]["feature"]) | core)
    dropped = [f for f in NUMERIC_FEATURES if f not in selected]
    print(f"\n  KEPT ({len(selected)}): {selected}")
    print(f"  DROPPED as irrelevant ({len(dropped)}): {dropped}")
    print("  DROPPED a-priori: macro DXY/Gold/US10Y -> only 63 days coverage, "
          "cannot enter a 281-row model (retained only as live qualitative overlay).")
    return rel, catrel, selected


# ============================================================ models ==========
def _chrono_split(df, frac=0.70):
    n = len(df); cut = int(n * frac)
    return df.iloc[:cut], df.iloc[cut:], cut, n - cut


def model_comparison(df, selected):
    print("\n" + "=" * 70)
    print("  MODEL COMPARISON  (direction & magnitude, with proper validation)")
    print("=" * 70)
    d = df.dropna(subset=["react_10", "react_eod"]).reset_index(drop=True)
    tr, te, ntr, nte = _chrono_split(d)
    print(f"  Total releases: {len(d)}  |  TRAIN (oldest 70%): {ntr}  |  "
          f"TEST (newest 30%): {nte}  |  + 5-fold CV")

    Xtr, Xte = _imp(tr, selected), _imp(te, selected)
    sc = StandardScaler().fit(Xtr)
    Xtr_s, Xte_s = sc.transform(Xtr), sc.transform(Xte)

    # ---------- DIRECTION (up vs down) ----------
    ytr = (tr["react_10"] > 0).astype(int).values
    yte = (te["react_10"] > 0).astype(int).values
    res_dir = []

    # naive fundamental baselines
    base_pred = (-te["surprise_seas"].fillna(0) > 0).astype(int).values   # draw vs norm -> up
    fade_pred = (te["surprise_seas"].fillna(0) > 0).astype(int).values    # contrarian
    res_dir.append(("Baseline: draw->up", accuracy_score(yte, base_pred), np.nan))
    res_dir.append(("Baseline: fade (build->up)", accuracy_score(yte, fade_pred), np.nan))

    models = {
        "LogisticRegression": LogisticRegression(max_iter=1000, C=0.5),
        "RandomForest": RandomForestClassifier(n_estimators=300, max_depth=3,
                                               min_samples_leaf=10, random_state=SEED),
        "GradientBoosting": GradientBoostingClassifier(n_estimators=100, max_depth=2,
                                                       learning_rate=0.03, random_state=SEED),
    }
    from sklearn.model_selection import cross_val_score, StratifiedKFold
    Xall = _imp(d, selected); yall = (d["react_10"] > 0).astype(int).values
    skf = StratifiedKFold(5, shuffle=True, random_state=SEED)
    for name, mdl in models.items():
        m = mdl.fit(Xtr_s, ytr)
        acc = accuracy_score(yte, m.predict(Xte_s))
        try:
            auc = roc_auc_score(yte, m.predict_proba(Xte_s)[:, 1])
        except Exception:
            auc = np.nan
        cv = cross_val_score(mdl, StandardScaler().fit_transform(Xall), yall,
                             cv=skf, scoring="accuracy").mean()
        res_dir.append((f"{name} (CV acc {cv:.3f})", acc, auc))

    dir_df = pd.DataFrame(res_dir, columns=["model", "test_accuracy", "test_AUC"])
    print("\n  DIRECTION (predict 10-min up/down):")
    print(dir_df.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print(f"  [base rate up = {yall.mean():.3f}; >0.55 OOS would indicate real skill]")

    # ---------- MAGNITUDE (|EOD move|) ----------
    print("\n  MAGNITUDE (predict |EOD move| %):")
    ytr_m, yte_m = tr["abs_eod"].fillna(0).values, te["abs_eod"].fillna(0).values
    # OLS for interpretability
    Xo = sm.add_constant(_imp(d, selected))
    ols = sm.OLS(d["abs_eod"].fillna(0).values, Xo).fit()
    rf = RandomForestRegressor(n_estimators=300, max_depth=3, min_samples_leaf=10,
                               random_state=SEED).fit(Xtr, ytr_m)
    r2_ols_oos = r2_score(yte_m, sm.add_constant(_imp(te, selected),
                                                 has_constant="add") @ ols.params)
    r2_rf_oos = r2_score(yte_m, rf.predict(Xte))
    print(f"    OLS  : in-sample R2={ols.rsquared:.3f}  |  holdout R2={r2_ols_oos:+.3f}")
    print(f"    RF   : holdout R2={r2_rf_oos:+.3f}  MAE={mean_absolute_error(yte_m, rf.predict(Xte)):.3f}%")
    # most significant OLS coefs
    coefs = pd.DataFrame({"feature": ["const"] + selected, "coef": ols.params,
                          "p": ols.pvalues}).sort_values("p")
    print("    OLS coefficients by significance (top 6):")
    print(coefs.head(6).to_string(index=False, float_format=lambda v: f"{v:.3f}"))

    # ---------- "DID IT MATTER" (big move classifier) ----------
    yb_tr, yb_te = tr["big_move"].values, te["big_move"].values
    gbm = GradientBoostingClassifier(n_estimators=100, max_depth=2, learning_rate=0.03,
                                     random_state=SEED).fit(Xtr, yb_tr)
    try:
        auc_big = roc_auc_score(yb_te, gbm.predict_proba(Xte)[:, 1])
    except Exception:
        auc_big = np.nan
    print(f"\n  'DID IT MATTER' (|10min|>Q70={df.attrs.get('big_thr',0):.2f}%): "
          f"GBM holdout AUC={auc_big:.3f}  [>0.6 = useful for sizing]")

    out = {"dir_df": dir_df, "ols": ols, "coefs": coefs, "rf_mag": rf,
           "r2_ols_oos": r2_ols_oos, "r2_rf_oos": r2_rf_oos, "auc_big": auc_big,
           "base_rate_up": yall.mean(), "ntr": ntr, "nte": nte, "n": len(d)}
    dir_df.to_csv(os.path.join(REPORT, "tbl_model_direction.csv"), index=False)
    coefs.to_csv(os.path.join(REPORT, "tbl_ols_magnitude.csv"), index=False)
    return out


# ============================================================ regime ==========
def regime_seasonal(df):
    print("\n" + "=" * 70)
    print("  REGIME & SEASONAL CONDITIONING  (when did inventories matter?)")
    print("=" * 70)
    d = df.dropna(subset=["react_10", "surprise_seas"]).copy()
    d["sup_dir"] = np.sign(-d["surprise_seas"])  # draw-vs-norm -> bullish
    d["hit"] = (d["sup_dir"] == np.sign(d["react_10"])).astype(int)

    def grp(col, bins=None, labels=None):
        x = pd.qcut(d[col], q=3, labels=labels, duplicates="drop") if bins is None else d[col]
        return d.groupby(x).agg(n=("hit", "size"), hit_rate=("hit", "mean"),
                                mean_abs_10=("abs_10", "mean"),
                                mean_abs_eod=("abs_eod", "mean"))

    tables = {}
    print("\n  By |surprise| tercile:")
    d["abs_sup"] = d["surprise_seas"].abs()
    t = grp("abs_sup", labels=["small", "mid", "large"]); tables["surprise"] = t
    print(t.to_string(float_format=lambda v: f"{v:.3f}"))
    print("\n  By realised-vol regime (tercile):")
    t = grp("rvol_20d", labels=["low", "mid", "high"]); tables["vol"] = t
    print(t.to_string(float_format=lambda v: f"{v:.3f}"))
    print("\n  By quarter:")
    t = d.groupby("quarter").agg(n=("hit", "size"), hit_rate=("hit", "mean"),
                                 mean_abs_10=("abs_10", "mean"), mean_abs_eod=("abs_eod", "mean"))
    tables["quarter"] = t
    print(t.to_string(float_format=lambda v: f"{v:.3f}"))
    print("\n  By driving season (May-Sep) vs rest:")
    t = d.groupby("driving_season").agg(n=("hit", "size"), hit_rate=("hit", "mean"),
                                        mean_abs_10=("abs_10", "mean"), mean_abs_eod=("abs_eod", "mean"))
    tables["driving"] = t
    print(t.to_string(float_format=lambda v: f"{v:.3f}"))
    for k, v in tables.items():
        v.to_csv(os.path.join(REPORT, f"tbl_regime_{k}.csv"))
    return tables


# ============================================================ products ========
def products_spreads(df):
    print("\n" + "=" * 70)
    print("  PRODUCTS / SPREADS MOST AFFECTED BY CRUDE PRINTS")
    print("=" * 70)
    rows = []
    for col, lab in [("react_10", "WTI M1"), ("brent_10", "Brent M1"),
                     ("ho_10", "Heating Oil M1"), ("wti_sp12_delta", "WTI M1-M2 (delta)")]:
        s = df[col].dropna()
        rows.append({"instrument": lab, "n": len(s), "mean_abs_react": s.abs().mean(),
                     "median_abs_react": s.abs().median(), "std_react": s.std()})
    pr = pd.DataFrame(rows)
    # vol-adjusted: mean|react| / std (response per unit of own noise)
    pr["response_ratio"] = pr["mean_abs_react"] / pr["std_react"]
    pr = pr.sort_values("mean_abs_react", ascending=False)
    pr.to_csv(os.path.join(REPORT, "tbl_products.csv"), index=False)
    print(pr.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    # correlation of each product reaction with crude surprise
    print("\n  corr(crude surprise, product 10-min reaction):")
    for col, lab in [("react_10", "WTI"), ("brent_10", "Brent"), ("ho_10", "HO")]:
        dd = df[["surprise_seas", col]].dropna()
        r, p = stats.pearsonr(-dd["surprise_seas"], dd[col])
        print(f"    {lab:6s}: r={r:+.3f} (p={p:.3f})")
    return pr


# ============================================================ 2026 call =======
def assess_release(df, selected, models, target_friday="2026-05-29"):
    print("\n" + "=" * 70)
    print(f"  ASSESSMENT - RELEASE FOR WEEK ENDING {target_friday}")
    print("=" * 70)
    eia = load_eia()
    crude, cush, refin = eia["crude"], eia["cushing"], eia["refinery"]
    dist, gas = eia["distillate"], eia["gasoline"]
    fri = pd.Timestamp(target_friday)
    rd, pmin = release_for_friday(fri)
    wk = int(fri.isocalendar().week)
    base = crude[(crude.index.year >= 2020) & (crude.index.year <= 2024)]
    seas = base.groupby("wk")["wow"].mean().get(wk, np.nan)

    cc = crude.loc[fri, "wow"]
    sup = cc - seas
    rr = refin.loc[fri, "wow"]
    dc = dist.loc[fri, "wow"]; gc = gas.loc[fri, "wow"]
    ccu = cush.loc[fri, "wow"]
    idx = crude.index.get_loc(fri)
    lvlmean = base.groupby("wk")["value"].mean().get(wk, np.nan)
    lvlstd = base.groupby("wk")["value"].std().get(wk, np.nan)
    stocks_z = (crude.loc[fri, "value"] - lvlmean) / lvlstd

    # historical analog: same-sign surprise of similar magnitude
    dd = df.dropna(subset=["surprise_seas", "react_10", "react_eod"])
    same = dd[np.sign(dd["surprise_seas"]) == np.sign(sup)]
    near = same.reindex(same["surprise_seas"].sub(sup).abs().sort_values().index).head(20)
    hist_hit = (np.sign(-near["surprise_seas"]) == np.sign(near["react_10"])).mean()
    hist_r10 = near["react_10"].mean()
    hist_eod = near["react_eod"].mean()

    # fundamental lean: draw vs seasonal norm -> bullish
    lean = "BULLISH" if sup < 0 else ("BEARISH" if sup > 0 else "NEUTRAL")
    # empirical reality: immediate reaction is weakly CONTRARIAN / mean-reverting
    # (corr(surprise, react_10)=+0.11, momentum corr=-0.16) and analogs hit ~50%,
    # so a textbook-bullish draw is held at low conviction.
    big = abs(sup) > dd["surprise_seas"].abs().quantile(0.66)
    conf = "LOW"
    if big and abs(hist_hit - 0.5) > 0.12:
        conf = "MEDIUM"
    # synthesised headline view (fundamentals vs weak contrarian empirics)
    if conf == "LOW":
        bias = "bullish" if lean == "BULLISH" else ("bearish" if lean == "BEARISH" else "no")
        view = f"NEUTRAL (slight {bias} bias)"
    else:
        view = lean
    print(f"  Release date: {rd}  ({'Thu 11:00' if pmin>=660 else 'Wed 10:30'} ET)")
    print(f"  Crude WoW: {cc:+,.0f} MBBL  |  seasonal norm: {seas:+,.0f}  |  "
          f"SURPRISE vs seasonal: {sup:+,.0f} MBBL")
    print(f"  Refinery runs WoW: {rr:+,.0f} MBBL/D  |  Distillate: {dc:+,.0f}  Gasoline: {gc:+,.0f}")
    print(f"  Stock level z (vs 5yr): {stocks_z:+.2f}  |  Cushing WoW: {ccu:+,.0f}")
    print(f"  Fundamental lean: {lean}  (draw vs seasonal = bullish)")
    print(f"  Nearest-20 analogs (same-sign surprise): hit={hist_hit:.2f}  "
          f"avg 10min={hist_r10:+.3f}%  avg EOD={hist_eod:+.3f}%")
    print(f"  SYNTHESISED VIEW: {view}  |  CONFIDENCE: {conf}")
    return {"rd": rd, "cc": cc, "seas": seas, "sup": sup, "rr": rr, "dc": dc, "gc": gc,
            "ccu": ccu, "stocks_z": stocks_z, "lean": lean, "view": view, "conf": conf,
            "hist_hit": hist_hit, "hist_r10": hist_r10, "hist_eod": hist_eod}


if __name__ == "__main__":
    from crude_report import run_all
    run_all()
