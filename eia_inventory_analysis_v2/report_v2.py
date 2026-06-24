"""
================================================================================
  EIA INVENTORY-IMPACT  v2  -  figures + pipeline helper
================================================================================
run_pipeline() runs analysis_v2 end to end and returns every result object;
build_all_figures() writes the PNGs.  The Word docs (report_v2_docx.py) consume
both.  Exploratory research framing throughout.
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats

import analysis_v2 as a2

OUT = a2.OUT
FIG = os.path.join(OUT, "figures")
os.makedirs(FIG, exist_ok=True)


def _save(fig, name):
    fig.tight_layout(); fig.savefig(os.path.join(FIG, name), dpi=115, bbox_inches="tight")
    plt.close(fig); return os.path.join(FIG, name)


# ----------------------------------------------------------- pipeline ---------
def api_agreement(df):
    d = df.dropna(subset=["crude_surp_cons", "API_surp_cons", "WTI_post10_pct"]).copy()
    d["eia_dir"] = -np.sign(d["crude_surp_cons"])
    d["agree"] = np.where(d["eia_dir"] == -np.sign(d["API_surp_cons"]),
                          "API & EIA agree", "API vs EIA diverge")
    g = d.groupby("agree").apply(lambda x: pd.Series({
        "n": len(x),
        "EIA_hit_rate": round((np.sign(x["WTI_post10_pct"]) == x["eia_dir"]).mean(), 3),
        "mean_WTI_spike_pct": round(x["WTI_spike_pct"].mean(), 3)}))
    return g


def run_pipeline():
    df = a2.build()
    r = a2.compare(df)
    edges, edge_hits = a2.conditioned_edges(df)
    seasonal = a2.seasonal_regime(df)
    when = a2.when_mattered(df)
    api_g = api_agreement(df)
    accuracy = a2.signal_accuracy(df)
    curve = a2.intraday_curve(df)
    return {"df": df, "comp": r["comparison"], "disc": r["discrepancies"],
            "n_material": r["n_material"], "edges": edges, "seasonal": seasonal,
            "when": when, "api_g": api_g, "accuracy": accuracy, "curve": curve}


# ----------------------------------------------------------- figures ----------
def fig_surprise_scatter(df):
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for ax, prod in zip(axes, ["WTI", "Brent"]):
        d = df.dropna(subset=["crude_surp_cons", f"{prod}_post10_pct"])
        ax.scatter(d["crude_surp_cons"], d[f"{prod}_post10_pct"], s=18, alpha=.5, color="teal")
        if len(d) > 2:
            b1, b0 = np.polyfit(d["crude_surp_cons"], d[f"{prod}_post10_pct"], 1)
            xs = np.linspace(d["crude_surp_cons"].min(), d["crude_surp_cons"].max(), 50)
            ax.plot(xs, b0 + b1 * xs, "r-")
            r, p = stats.pearsonr(d["crude_surp_cons"], d[f"{prod}_post10_pct"])
            ax.set_title(f"{prod}: surprise vs +10min  (r={r:+.2f}, p={p:.2f}, n={len(d)})")
        ax.axhline(0, color="grey", lw=.6); ax.axvline(0, color="grey", lw=.6)
        ax.set_xlabel("EIA crude surprise = actual minus consensus (Mbbl)  [positive = bigger build]")
        ax.set_ylabel(f"{prod} M1 move +10min (%)"); ax.grid(alpha=.3)
    fig.suptitle("Fig 1. Does the consensus surprise move price? "
                 "(on fundamentals, a bigger build should mean a lower price)", y=1.02)
    return _save(fig, "F1_surprise_vs_reaction.png")


def fig_hitrate(comp):
    fig, ax = plt.subplots(figsize=(11, 5.5))
    hcols = ["hit_at_release", "hit_+5min", "hit_+10min"]
    x = np.arange(len(comp)); w = 0.26
    for i, c in enumerate(hcols):
        ax.bar(x + (i - 1) * w, comp[c], w, label=c.replace("hit_", ""))
    ax.axhline(0.5, color="k", ls="--", lw=1, label="coin flip (0.50)")
    short = [s.replace(", on ", "\n").replace("EIA ", "").replace(" vs consensus", "/cons")
             for s in comp["signal"]]
    ax.set_xticks(x); ax.set_xticklabels(short, rotation=20, ha="right", fontsize=8)
    ax.set_ylim(0.35, 0.65); ax.set_ylabel("hit rate (signal direction matched move)")
    ax.set_title("Fig 2. Directional hit rate by signal and horizon (at release, +5 and +10 min)")
    ax.legend(fontsize=8); ax.grid(alpha=.3, axis="y")
    return _save(fig, "F2_hitrate.png")


def fig_magnitude(df):
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    d = df.dropna(subset=["crude_surp_cons", "WTI_spike_pct"]).assign(
        abss=lambda x: x["crude_surp_cons"].abs())
    axes[0].scatter(d["abss"], d["WTI_spike_pct"], s=18, alpha=.5, color="purple")
    if len(d) > 2:
        r, p = stats.pearsonr(d["abss"], d["WTI_spike_pct"])
        axes[0].set_title(f"|surprise| vs WTI peak move (r={r:+.2f}, p={p:.2f})")
    axes[0].set_xlabel("|crude surprise| (Mbbl)"); axes[0].set_ylabel("WTI peak |move| in +10min (%)")
    axes[0].grid(alpha=.3)
    d["t"] = pd.qcut(d["abss"], 3, labels=["small", "mid", "large"], duplicates="drop")
    g = d.groupby("t")["WTI_spike_pct"].mean()
    axes[1].bar(range(len(g)), g.values, color="slateblue")
    axes[1].set_xticks(range(len(g))); axes[1].set_xticklabels(g.index)
    axes[1].set_title("Mean WTI peak move by surprise size"); axes[1].set_ylabel("mean peak |move| (%)")
    axes[1].grid(alpha=.3, axis="y")
    fig.suptitle("Fig 3. Bigger surprise, bigger move (magnitude is conditionable, "
                 "direction is not)", y=1.02)
    return _save(fig, "F3_magnitude.png")


def fig_api_eia(api_g):
    g = api_g
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].bar(range(len(g)), g["EIA_hit_rate"], color=["seagreen", "indianred"][:len(g)])
    axes[0].axhline(0.5, color="k", ls="--"); axes[0].set_xticks(range(len(g)))
    axes[0].set_xticklabels(g.index, fontsize=9); axes[0].set_ylim(0.35, 0.7)
    axes[0].set_title("EIA-signal hit rate"); axes[0].set_ylabel("hit rate")
    axes[1].bar(range(len(g)), g["mean_WTI_spike_pct"], color="slateblue")
    axes[1].set_xticks(range(len(g))); axes[1].set_xticklabels(g.index, fontsize=9)
    axes[1].set_title("Mean WTI peak move"); axes[1].set_ylabel("mean peak |move| (%)")
    for a in axes:
        a.grid(alpha=.3, axis="y")
    fig.suptitle("Fig 4. The Tuesday API as a tell: does the Wednesday EIA confirming it help?", y=1.02)
    return _save(fig, "F4_api_eia.png")


def fig_conditioned(edges):
    d = edges[edges["instrument"] == "WTI +10min"].dropna(subset=["hit"])
    order = ["ALL", "API+EIA agree", "API/EIA diverge", "|surp| small", "|surp| large",
             "lowvol", "highvol"]
    d = d.set_index("bucket").reindex([b for b in order if b in set(d["bucket"])]).reset_index().dropna(subset=["hit"])
    fig, ax = plt.subplots(figsize=(11, 5))
    colors = ["seagreen" if v >= 0.58 else "indianred" if v <= 0.42 else "grey" for v in d["hit"]]
    ax.bar(range(len(d)), d["hit"], color=colors)
    ax.axhline(0.5, color="k", ls="--", lw=1, label="coin flip")
    ax.set_xticks(range(len(d))); ax.set_xticklabels(d["bucket"], rotation=20, ha="right", fontsize=9)
    for i, (v, nn) in enumerate(zip(d["hit"], d["n"])):
        ax.text(i, v + 0.008, f"{v:.2f}\n(n={int(nn)})", ha="center", fontsize=8)
    ax.set_ylim(0.25, 0.72); ax.set_ylabel("hit rate (crude surprise vs WTI +10min)")
    ax.set_title("Fig 5. Conditioned edge: small surprises follow, large surprises fade")
    ax.legend(); ax.grid(alpha=.3, axis="y")
    return _save(fig, "F5_conditioned.png")


def fig_seasonal(seasonal):
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    q = seasonal["quarter"]
    axes[0].bar(range(len(q)), q["hit_rate"], color="steelblue")
    axes[0].axhline(0.5, color="k", ls="--"); axes[0].set_xticks(range(len(q)))
    axes[0].set_xticklabels(q.index); axes[0].set_ylim(0.4, 0.65)
    axes[0].set_title("Hit rate by quarter"); axes[0].set_ylabel("hit rate"); axes[0].grid(alpha=.3, axis="y")
    v = seasonal.get("vol_regime")
    if v is not None:
        ax2 = axes[1]; x = range(len(v))
        ax2.bar(x, v["mean_spike_pct"], color="slateblue", label="mean peak move %")
        ax3 = ax2.twinx(); ax3.plot(x, v["hit_rate"], color="darkorange", marker="o", label="hit rate")
        ax3.axhline(0.5, color="grey", ls="--", lw=.8); ax3.set_ylim(0.4, 0.65)
        ax2.set_xticks(list(x)); ax2.set_xticklabels(v.index)
        ax2.set_title("By volatility regime"); ax2.set_ylabel("mean peak move %"); ax3.set_ylabel("hit rate")
    fig.suptitle("Fig 6. Seasonal and regime effects (weak seasonality; vol regime matters most)", y=1.02)
    return _save(fig, "F6_seasonal_regime.png")


def fig_when_mattered(when):
    g = when
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    x = range(len(g))
    axes[0].bar(x, g["mean_rvol"], color="indianred")
    axes[0].set_xticks(list(x)); axes[0].set_xticklabels(g.index)
    axes[0].set_title("Realised vol by size of the WTI move"); axes[0].set_ylabel("mean 20d realised vol")
    axes[0].grid(alpha=.3, axis="y")
    axes[1].bar(x, g["mean_abs_surprise"], color="grey")
    axes[1].set_xticks(list(x)); axes[1].set_xticklabels(g.index)
    axes[1].set_title("|surprise| by size of the WTI move (flat)"); axes[1].set_ylabel("mean |surprise| Mbbl")
    axes[1].grid(alpha=.3, axis="y")
    fig.suptitle("Fig 7. When did inventories matter? Big reactions track the volatility "
                 "regime, not the surprise size", y=1.02)
    return _save(fig, "F7_when_mattered.png")


def fig_signal_accuracy(acc):
    fig, ax = plt.subplots(figsize=(11, 5.5))
    hcols = ["acc_at_release", "acc_+5min", "acc_+10min"]
    x = np.arange(len(acc)); w = 0.26
    for i, c in enumerate(hcols):
        ax.bar(x + (i - 1) * w, acc[c], w, label=c.replace("acc_", ""))
    ax.axhline(0.5, color="k", ls="--", lw=1, label="coin flip (0.50)")
    labels = [s.strip() for s in acc["signal"]]
    ax.set_xticks(x); ax.set_xticklabels(labels, rotation=12, ha="right", fontsize=8)
    ax.set_ylim(0.4, 0.75); ax.set_ylabel("accuracy (signal direction matched the move)")
    ax.set_title("Fig 8. Signal generation accuracy on WTI (the rule beats the coin flip)")
    for i, row in acc.reset_index(drop=True).iterrows():
        ax.text(i, 0.405, f"n={int(row['n_trades'])}", ha="center", fontsize=7, color="dimgrey")
    ax.legend(fontsize=8); ax.grid(alpha=.3, axis="y")
    return _save(fig, "F8_signal_accuracy.png")


def fig_intraday_curve(curve):
    c = curve[curve["minute"] >= -5]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    # left: cumulative reaction path, all three products
    for prod, col in [("WTI", "teal"), ("Brent", "darkorange"), ("HO", "slateblue")]:
        axes[0].plot(c["minute"], c[f"{prod}_absmove"], marker="o", ms=3, color=col, label=prod)
    axes[0].axvline(0, color="k", lw=1); axes[0].axvspan(0, 5, color="gold", alpha=.15)
    axes[0].text(2.5, axes[0].get_ylim()[1] * 0.05, "bulk of the move", ha="center", fontsize=8, color="darkgoldenrod")
    axes[0].set_xlabel("minutes from the release (0 = print)")
    axes[0].set_ylabel("mean |move| from pre-release (%)")
    axes[0].set_title("Reaction builds fastest in the first minutes"); axes[0].legend(); axes[0].grid(alpha=.3)
    # right: WTI share of the +10min move already realised
    cc = c[c["minute"] >= 0]
    axes[1].bar(cc["minute"], cc["WTI_share_of_10min"] * 100, color="teal", alpha=.8)
    axes[1].axhline(100, color="grey", ls="--", lw=.8)
    axes[1].set_xlabel("minutes from the release"); axes[1].set_ylabel("share of the +10min move (%)")
    axes[1].set_title("WTI: how much of the move is in by minute X"); axes[1].grid(alpha=.3, axis="y")
    fig.suptitle("Fig 9. Time range of most change: the move lands at the print and is ~80% "
                 "done within 5 minutes", y=1.02)
    return _save(fig, "F9_intraday_curve.png")


def build_all_figures(P):
    return {
        "scatter": fig_surprise_scatter(P["df"]),
        "hitrate": fig_hitrate(P["comp"]),
        "magnitude": fig_magnitude(P["df"]),
        "api_eia": fig_api_eia(P["api_g"]),
        "conditioned": fig_conditioned(P["edges"]),
        "seasonal": fig_seasonal(P["seasonal"]),
        "when": fig_when_mattered(P["when"]),
        "accuracy": fig_signal_accuracy(P["accuracy"]),
        "curve": fig_intraday_curve(P["curve"]),
    }


if __name__ == "__main__":
    P = run_pipeline()
    figs = build_all_figures(P)
    print("figures:", *[os.path.basename(f) for f in figs.values()])
