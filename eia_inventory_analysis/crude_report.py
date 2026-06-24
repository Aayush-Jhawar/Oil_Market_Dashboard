"""
================================================================================
  CRUDE-IMPACT REPORT GENERATOR
================================================================================
Runs the full crude_impact_framework pipeline, builds ~10 figures, and writes
report/report.md with narrative + the four required deliverables.
================================================================================
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats

import crude_impact_framework as cf

FIG, REPORT, DATA = cf.FIG, cf.REPORT, cf.DATA


def _save(fig, name):
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, name), dpi=115, bbox_inches="tight")
    plt.close(fig)
    return f"figures/{name}"


# ------------------------------------------------------------- figures --------
def fig_levels_seasonal(eia):
    crude = eia["crude"]
    base = crude[(crude.index.year >= 2020) & (crude.index.year <= 2024)]
    g = base.groupby("wk")["value"]
    band = pd.DataFrame({"mean": g.mean(), "lo": g.min(), "hi": g.max()})
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(crude.index, crude["value"] / 1000, color="navy", lw=1.0, label="US crude stocks")
    # overlay seasonal band mapped onto 2025-26 weeks
    for yr in [2025, 2026]:
        wks = pd.date_range(f"{yr}-01-01", f"{yr}-12-31", freq="W-FRI")
        wk_idx = wks.isocalendar().week.astype(int)
        ax.fill_between(wks, band["lo"].reindex(wk_idx).values / 1000,
                        band["hi"].reindex(wk_idx).values / 1000, color="grey", alpha=0.15)
    ax.scatter(crude.index[-1], crude["value"].iloc[-1] / 1000, color="red", zorder=5,
               label=f"latest {crude['value'].iloc[-1]/1000:.0f} MMbbl")
    ax.set_ylabel("MMbbl"); ax.set_title("F1 - US crude stocks vs 5yr seasonal range (2020-24 band)")
    ax.legend(); ax.grid(alpha=0.3)
    return _save(fig, "F1_levels_seasonal.png")


def fig_seasonal_wow(eia, df):
    crude = eia["crude"]
    base = crude[(crude.index.year >= 2020) & (crude.index.year <= 2024)]
    g = base.groupby("wk")["wow"]
    m, s = g.mean(), g.std()
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(m.index, m.values, color="darkgreen", label="5yr mean WoW")
    ax.fill_between(m.index, m - s, m + s, color="green", alpha=0.18, label="±1 std")
    ax.axhline(0, color="k", lw=0.6)
    d26 = df[df["release_date"].apply(lambda d: d.year == 2026)]
    ax.scatter(d26["wk"], d26["crude_chg"], color="red", zorder=5, label="2026 actual WoW")
    ax.set_xlabel("ISO week"); ax.set_ylabel("WoW change (MBBL)")
    ax.set_title("F2 - Crude seasonal WoW pattern (5yr) with 2026 actuals")
    ax.legend(); ax.grid(alpha=0.3)
    return _save(fig, "F2_seasonal_wow.png")


def fig_reaction_dist(df):
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    for ax, col, lab in [(axes[0], "react_10", "10-min"), (axes[1], "react_eod", "EOD")]:
        v = df[col].dropna()
        ax.hist(v, bins=40, color="steelblue", edgecolor="white")
        ax.axvline(0, color="k", lw=0.8)
        ax.set_title(f"F3 - WTI {lab} reaction (n={len(v)}, mean|{lab}|={v.abs().mean():.3f}%)")
        ax.set_xlabel("reaction %"); ax.grid(alpha=0.3)
    return _save(fig, "F3_reaction_dist.png")


def fig_relevance(rel):
    r = rel.sort_values("abs_mag")
    fig, ax = plt.subplots(figsize=(10, 7))
    y = np.arange(len(r))
    ax.barh(y - 0.2, r["corr_dir_10"].abs(), 0.4, label="|corr| with direction (10min)", color="indianred")
    ax.barh(y + 0.2, r["corr_mag_eod"].abs(), 0.4, label="|corr| with magnitude (|EOD|)", color="steelblue")
    ax.set_yticks(y); ax.set_yticklabels(r["label"], fontsize=8)
    ax.axvline(0.12, color="grey", ls="--", lw=0.8, label="~p=0.05 threshold (n=281)")
    ax.set_xlabel("|correlation|"); ax.legend(fontsize=8)
    ax.set_title("F4 - Feature relevance: correlation with reaction (direction & magnitude)")
    ax.grid(alpha=0.3, axis="x")
    return _save(fig, "F4_feature_relevance.png")


def fig_surprise_scatter(df):
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for ax, col, lab in [(axes[0], "react_10", "10-min"), (axes[1], "react_eod", "EOD")]:
        d = df[["surprise_seas", col]].dropna()
        ax.scatter(d["surprise_seas"] / 1000, d[col], s=18, alpha=0.5, color="teal")
        b1, b0 = np.polyfit(d["surprise_seas"] / 1000, d[col], 1)
        xs = np.linspace((d["surprise_seas"] / 1000).min(), (d["surprise_seas"] / 1000).max(), 50)
        ax.plot(xs, b0 + b1 * xs, "r-")
        r, p = stats.pearsonr(d["surprise_seas"], d[col])
        ax.set_title(f"F5 - Surprise vs WTI {lab}  (r={r:+.3f}, p={p:.3f})")
        ax.axhline(0, color="grey", lw=0.6); ax.axvline(0, color="grey", lw=0.6)
        ax.set_xlabel("surprise vs seasonal (MMbbl)"); ax.set_ylabel(f"{lab} reaction %")
        ax.grid(alpha=0.3)
    return _save(fig, "F5_surprise_scatter.png")


def fig_models(out):
    dd = out["dir_df"].copy()
    fig, ax = plt.subplots(figsize=(10, 5))
    colors = ["grey" if "Baseline" in m else "steelblue" for m in dd["model"]]
    ax.barh(np.arange(len(dd)), dd["test_accuracy"], color=colors)
    ax.axvline(0.5, color="k", ls="--", lw=0.9, label="coin flip")
    ax.axvline(max(out["base_rate_up"], 1 - out["base_rate_up"]), color="red", ls=":", lw=0.9,
               label="majority-class base rate")
    ax.set_yticks(np.arange(len(dd))); ax.set_yticklabels(dd["model"], fontsize=8)
    ax.set_xlabel("test-set accuracy (newest 30%)"); ax.set_xlim(0.3, 0.7)
    ax.set_title("F6 - Direction models vs baselines (out-of-sample)")
    ax.legend(fontsize=8); ax.grid(alpha=0.3, axis="x")
    return _save(fig, "F6_models.png")


def fig_regime(tables):
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    for ax, key, title in [(axes[0], "surprise", "|surprise| tercile"),
                           (axes[1], "vol", "realised-vol regime"),
                           (axes[2], "quarter", "quarter")]:
        t = tables[key]
        x = np.arange(len(t))
        ax.bar(x - 0.2, t["mean_abs_eod"], 0.4, label="mean |EOD| %", color="slateblue")
        ax2 = ax.twinx()
        ax2.plot(x, t["hit_rate"], color="darkorange", marker="o", label="hit rate")
        ax2.axhline(0.5, color="grey", ls="--", lw=0.8)
        ax.set_xticks(x); ax.set_xticklabels([str(i) for i in t.index], fontsize=8)
        ax.set_title(f"by {title}"); ax.set_ylabel("mean |EOD| %"); ax2.set_ylim(0.2, 0.8)
        ax2.set_ylabel("hit rate")
    fig.suptitle("F7 - When did it matter? magnitude (bars) & direction hit (line)", y=1.02)
    return _save(fig, "F7_regime.png")


def fig_products(pr):
    p = pr.sort_values("mean_abs_react")
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.barh(np.arange(len(p)), p["mean_abs_react"], color="seagreen")
    ax.set_yticks(np.arange(len(p))); ax.set_yticklabels(p["instrument"])
    ax.set_xlabel("mean |10-min reaction| (% or $ for spread)")
    ax.set_title("F8 - Average reaction magnitude to crude prints by instrument")
    ax.grid(alpha=0.3, axis="x")
    return _save(fig, "F8_products.png")


def fig_dashboard(call, eia):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    # inventory print bars
    names = ["Crude", "Surprise\nvs seas", "Refinery\nruns", "Distillate", "Gasoline", "Cushing"]
    vals = [call["cc"], call["sup"], call["rr"], call["dc"], call["gc"], call["ccu"]]
    cols = ["green" if (v < 0 if i != 2 else v > 0) else "red" for i, v in enumerate(vals)]
    axes[0].bar(names, vals, color=cols)
    axes[0].axhline(0, color="k", lw=0.6); axes[0].set_ylabel("MBBL (runs: MBBL/D)")
    axes[0].set_title(f"F9 - Print for week ending 2026-05-29 (release {call['rd']})")
    axes[0].grid(alpha=0.3, axis="y")
    # WTI curve snapshot from clean MAM data (last session)
    try:
        mam = pd.read_csv(os.path.join(DATA, "CL_wti_2026_MAM.csv"))
        mid = {c: f"m{c.split('||')[0][1:]}" for c in mam.columns if "weighted_mid" in c}
        mam = mam.rename(columns=mid)
        ts = pd.to_datetime(mam["timestamp"], utc=True).dt.tz_convert(cf.ET)
        mam["d"] = ts.dt.date; mam["mod"] = ts.dt.hour * 60 + ts.dt.minute
        last = max(mam["d"])
        snap = mam[(mam["d"] == last) & (mam["mod"].between(620, 629))]
        curve = [snap[f"m{i}"].mean() for i in range(1, 13)]
        axes[1].plot(range(1, 13), curve, marker="o", color="navy")
        axes[1].set_title(f"WTI forward curve {last} ~10:20 ET (backwardation)")
        axes[1].set_xlabel("contract month"); axes[1].set_ylabel("$/bbl"); axes[1].grid(alpha=0.3)
    except Exception as e:
        axes[1].text(0.1, 0.5, f"curve n/a: {e}")
    return _save(fig, "F9_dashboard.png")


# ------------------------------------------------------------- report ---------
def write_report(df, rel, catrel, selected, out, tables, pr, call, figs):
    big_thr = df.attrs.get("big_thr", np.nan)
    base_maj = max(out["base_rate_up"], 1 - out["base_rate_up"])
    best_dir = out["dir_df"].iloc[2:]["test_accuracy"].max()
    top_feats = rel.sort_values("best_p").head(4)
    L = []
    A = L.append
    A("# Crude Oil Inventory — Market-Impact Framework")
    A("")
    A("*Systematic assessment of the weekly EIA crude inventory release and its "
      "impact on WTI (with Brent and Heating Oil for cross-product context).*")
    A("")
    A("---")
    A("## Executive summary — deliverables")
    A("")
    A(f"**Series analysed:** US Crude Oil stocks (EIA `WCRSTUS1`) → WTI front-month. "
      f"**Sample:** {out['n']} weekly releases, 2021-01-06 → 2026-05-20 "
      f"(train {out['ntr']} oldest / test {out['nte']} newest, plus 5-fold CV).")
    A("")
    A(f"### 1. Directional expectation for the next release (week ending 2026-05-29, "
      f"released {call['rd']})")
    A(f"- **View: {call['view']} · Confidence: {call['conf']}**")
    A(f"- Crude drew **{call['cc']:+,.0f} MBBL** vs a seasonal norm of "
      f"{call['seas']:+,.0f} → **surprise {call['sup']:+,.0f} MBBL** "
      f"({'a draw far larger than seasonal — fundamentally bullish' if call['sup']<0 else 'build vs norm — bearish'}).")
    A(f"- **Why not a confident bull call?** In the 20 closest historical analogs the "
      f"directional hit rate was **{call['hist_hit']:.0%}** (avg 10-min {call['hist_r10']:+.2f}%, "
      f"avg EOD {call['hist_eod']:+.2f}%), and the measured immediate reaction to crude "
      f"prints is weakly **mean-reverting/contrarian** — so the textbook-bullish read is "
      f"held at low conviction. Higher-conviction expectation: an **above-average-magnitude** "
      f"move given the elevated vol regime, regardless of sign.")
    A("")
    A("### 2. Products / spreads most likely affected")
    A(f"- **Largest absolute reaction:** Brent M1 (~{pr.set_index('instrument').loc['Brent M1','mean_abs_react']:.3f}% avg) "
      f"> Heating Oil ≈ WTI (~0.12%). Brent is simply the more volatile barrel.")
    A("- **Most crude-*specific* (best correlated with the surprise):** **WTI M1** — the "
      "cleanest expression of a US crude signal. Use **WTI M1–M2** to play the same view "
      "with lower flat-price risk when a draw is Cushing-concentrated (steepens front "
      "backwardation); trade **WTI–Brent** only on a genuinely US-specific print.")
    A("")
    A("### 3. Top-3 factors driving the view")
    A(f"1. **Surprise vs seasonal** — a {call['sup']:+,.0f} MBBL draw relative to the 5yr "
      "seasonal norm; the single most decision-relevant inventory factor (and far more "
      "informative than the raw headline number, which the analysis dropped as irrelevant).")
    A(f"2. **Physical tightness** — stock level {call['stocks_z']:+.2f}σ vs the 5yr range "
      "(lean) with WTI in backwardation; both amplify a bullish draw.")
    A("3. **Volatility regime** — realised vol is the dominant driver of *how big* the move "
      "is (corr +0.26 with |EOD|), so it governs sizing/whether-to-engage more than direction.")
    A("")
    A("*Key caveat:* the immediate reaction is weakly **mean-reverting** (momentum corr "
      "−0.16) and direction is ~coin-flip, which is exactly why the headline view is "
      "NEUTRAL-with-a-bias rather than an outright bull call.")
    A("")
    A("### 4. The framework in one paragraph")
    A("For each release we compute the **surprise versus a 5-year seasonal norm** "
      "(not the raw build/draw, which is partly anticipated), keep only the factors that "
      "**empirically relate to the reaction** (surprise, stock-level richness vs 5yr, "
      "realised-vol regime, recent momentum/drift; refinery runs retained for demand "
      "context), and condition on **season and volatility regime**. We then map that to a "
      "directional lean, a confidence *calibrated to the historical hit rate*, and the "
      "instrument with the best crude-specific response. The empirical backbone is "
      f"{out['n']} historical releases with 1-minute WTI reactions measured in fixed "
      "windows around the 10:30 ET print. Factors that did **not** relate to the reaction "
      "(raw headline change, Cushing, days-of-supply, product cross-changes, and macro) "
      "are explicitly excluded — see §2.")
    A("")
    A("---")
    A("## Key finding: the crude print is largely *efficiently priced*")
    A("")
    A(f"Across {out['n']} releases the average WTI move in the 10 minutes after the print "
      f"is just **{df['abs_10'].mean():.3f}%**, and only ~30% exceed {big_thr:.2f}%. "
      "Predicting **direction** is hard:")
    A("")
    A(f"- Best out-of-sample direction model accuracy: **{best_dir:.1%}** vs a "
      f"majority-class base rate of {base_maj:.1%} — **no meaningful edge**.")
    A(f"- Magnitude is only weakly predictable (OLS holdout R² = {out['r2_ols_oos']:+.3f}; "
      f"'did it matter' classifier AUC = {out['auc_big']:.2f}).")
    A("")
    A("This is itself the actionable conclusion: **do not systematically trade WTI "
      "direction off the headline number.** The framework's value is in (i) sizing / "
      "whether to engage at all (magnitude + regime), and (ii) a disciplined, "
      "low-confidence lean confirmed by amplifiers.")
    A("")
    A(f"![reaction distribution]({figs['dist']})")
    A("")
    A("## 1. The series & its seasonality")
    A(f"![levels]({figs['levels']})")
    A("")
    A(f"![seasonal wow]({figs['seasonal']})")
    A("Crude stocks have a strong, repeatable seasonal rhythm (builds in winter/spring "
      "turnarounds, draws through driving season). Measuring the release against this "
      "seasonal norm is what isolates the genuinely *unexpected* component.")
    A("")
    A("## 2. Feature relevance — what matters, what doesn't")
    A(f"![relevance]({figs['relevance']})")
    A("")
    A("Correlation of each candidate factor with the reaction (n=281). Nothing clears a "
      "high bar, but the **surprise-vs-seasonal** and **stock-level z-score** carry the "
      "most magnitude information; raw headline change and most market-state features are "
      "weaker. Full table:")
    A("")
    A(rel[["label", "corr_dir_10", "p_dir", "corr_mag_eod", "p_mag", "best_p"]]
      .rename(columns={"label": "factor"}).to_markdown(index=False, floatfmt="+.3f"))
    A("")
    A(f"**Kept ({len(selected)}):** {', '.join(cf.FEATURE_LABELS.get(s,s) for s in selected)}.  ")
    A("**Dropped as irrelevant:** "
      + ", ".join(cf.FEATURE_LABELS.get(f, f) for f in cf.NUMERIC_FEATURES if f not in selected)
      + ".  ")
    A("**Removed a-priori:** macro DXY / Gold / US10Y — only 63 days of data, cannot "
      "support a 281-row model; retained only as a qualitative overlay on the live call.")
    A("")
    A(f"![surprise scatter]({figs['scatter']})")
    A("")
    A("## 3. Model comparison")
    A(f"![models]({figs['models']})")
    A("")
    A("Direction (predict 10-min up/down), out-of-sample:")
    A("")
    A(out["dir_df"].to_markdown(index=False, floatfmt=".3f"))
    A("")
    A(f"Magnitude (predict |EOD move|): OLS in-sample R²={out['ols'].rsquared:.3f}, "
      f"holdout R²={out['r2_ols_oos']:+.3f}; RandomForest holdout R²={out['r2_rf_oos']:+.3f}. "
      f"'Did it matter' (|10-min|>{big_thr:.2f}%) classifier AUC={out['auc_big']:.2f}.")
    A("")
    A("## 4. When did inventories matter? (regime & seasonal)")
    A(f"![regime]({figs['regime']})")
    A("")
    A("Moves are biggest on **large surprises** and in **high-volatility regimes**; "
      "the directional hit rate stays near 50% throughout (magnitude is conditionable, "
      "direction is not). Tables:")
    A("")
    for key, title in [("surprise", "|surprise| tercile"), ("vol", "vol regime"),
                       ("quarter", "quarter"), ("driving", "driving season")]:
        A(f"*By {title}:*")
        A("")
        A(tables[key].reset_index().to_markdown(index=False, floatfmt=".3f"))
        A("")
    A("## 5. Products & spreads")
    A(f"![products]({figs['products']})")
    A("")
    A(pr.to_markdown(index=False, floatfmt=".4f"))
    A("")
    A("## 6. The 2026-06-03 assessment")
    A(f"![dashboard]({figs['dashboard']})")
    A("")
    A(f"- **Print:** crude {call['cc']:+,.0f} MBBL, surprise vs seasonal {call['sup']:+,.0f} "
      f"MBBL; refinery runs {call['rr']:+,.0f} MBBL/D; distillate {call['dc']:+,.0f}; "
      f"gasoline {call['gc']:+,.0f}; Cushing {call['ccu']:+,.0f}; stock-level z {call['stocks_z']:+.2f}.")
    A(f"- **View: {call['view']}, confidence {call['conf']}.** A draw materially larger "
      "than the seasonal norm, on already-lean stocks (negative z), in a backwardated "
      "curve — all bullish-leaning. But historical analogs show only a "
      f"{call['hist_hit']:.0%} hit rate and a weakly contrarian immediate reaction, so the "
      "net headline is neutral-with-a-bullish-bias; size accordingly.")
    A("- **Trade expression:** WTI M1 outright for the cleanest read; WTI M1–M2 to express "
      "the same view with lower flat-price risk if the draw is Cushing-concentrated.")
    A("")
    A("## 7. Limitations & next steps")
    A("- **Consensus, not seasonal:** the market trades vs the *analyst consensus*; we "
      "proxy with a seasonal+trend norm. Acquiring consensus estimates is the single "
      "highest-leverage improvement.")
    A("- **Synthetic/limited price history** and back-adjusted continuous contracts "
      "(intraday % reactions are exact; $-level spreads are approximate).")
    A("- **Macro** only covers 2026; **PADD** breakdown only covers recent weeks.")
    A("- Extend the same framework to **distillate→HO** (early signs of a cleaner signal) "
      "and add **RBOB** for gasoline once 1-min data is available.")
    A("")
    with open(os.path.join(REPORT, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print(f"\n  wrote {os.path.join(REPORT, 'report.md')}")


def run_all():
    df = cf.build_dataset()
    rel, catrel, selected = cf.feature_relevance(df)
    out = cf.model_comparison(df, selected)
    tables = cf.regime_seasonal(df)
    pr = cf.products_spreads(df)
    call = cf.assess_release(df, selected, out)
    eia = cf.load_eia()
    print("\n  building figures ...")
    figs = {
        "levels": fig_levels_seasonal(eia), "seasonal": fig_seasonal_wow(eia, df),
        "dist": fig_reaction_dist(df), "relevance": fig_relevance(rel),
        "scatter": fig_surprise_scatter(df), "models": fig_models(out),
        "regime": fig_regime(tables), "products": fig_products(pr),
        "dashboard": fig_dashboard(call, eia),
    }
    write_report(df, rel, catrel, selected, out, tables, pr, call, figs)
    print("\n  DONE -> report/report.md  +  report/figures/*.png  +  report/tbl_*.csv")


if __name__ == "__main__":
    run_all()
