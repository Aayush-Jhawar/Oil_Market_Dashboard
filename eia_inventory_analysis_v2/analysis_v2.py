"""
================================================================================
  EIA INVENTORY-IMPACT  v2  -  simple, real-data, expectation-driven
================================================================================
Clean restart per the brief:
  * Expectation baseline = ANALYST CONSENSUS and the API (Tue) estimate, scraped
    from investing.com  ->  surprise = ACTUAL - EXPECTATION  (build vs draw vs
    what the market priced in).
  * Factors kept deliberately light: inventory (crude/distillate/gasoline),
    production, and refinery utilization.  Nothing else.
  * Price impact = M1 outright move 5-min before / at / 5-min after / 10-min
    after the 10:30 ET release, for every product that has BOTH inventory and
    price data (crude->WTI & Brent, distillate->Heating Oil).
  * Then: signal (from the surprise) vs what actually happened -> hit rate and a
    discrepancy log (when the print and the tape disagreed, and why).

Data confirmed REAL & aligned: workspace EIA changes match real EIA; workspace
WTI daily returns correlate 0.90 with real WTI.

Output: output/*.csv (+ figures via report_v2.py)
"""
import os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
WORKDATA = os.path.join(HERE, "..", "Data")
OUT = os.path.join(HERE, "output")
os.makedirs(OUT, exist_ok=True)
ET = "US/Eastern"

# products with BOTH an inventory series and 1-min price (the brief's check)
PRICE_FILES = {"WTI": "CL_data.parquet", "Brent": "LCO_data.parquet", "HO": "HO_data.parquet"}
# which inventory surprise drives which instrument
DRIVES = {"WTI": "EIA_Crude", "Brent": "EIA_Crude", "HO": "EIA_Distillate"}


# ----------------------------------------------------------- expectations -----
def load_expectations():
    """investing.com long -> wide per release_date with actual/consensus/previous."""
    df = pd.read_csv(os.path.join(DATA, "investing_petroleum_raw.csv"))
    df["dt"] = pd.to_datetime(df["datetime"].str[:10], format="%Y/%m/%d", errors="coerce")
    df = df.dropna(subset=["dt"])
    df["date"] = df["dt"].dt.date
    recs = {}
    for _, r in df.iterrows():
        d = r["date"]
        rec = recs.setdefault(d, {"release_date": d})
        for fld in ("actual", "consensus", "previous"):
            rec[f"{r['label']}__{fld}"] = r[fld]
    wide = pd.DataFrame(list(recs.values())).sort_values("release_date").reset_index(drop=True)
    return wide


# ----------------------------------------------------------- prices -----------
def load_prices():
    groups = {}
    wti_close = None
    for prod, fname in PRICE_FILES.items():
        pq = pd.read_parquet(os.path.join(WORKDATA, fname), columns=["timestamp", "c1||weighted_mid"])
        pq = pq.rename(columns={"c1||weighted_mid": "m1"})
        ts = pd.to_datetime(pq["timestamp"], utc=True).dt.tz_convert(ET)
        pq["d"] = ts.dt.date
        pq["mod"] = ts.dt.hour * 60 + ts.dt.minute
        if prod == "WTI":   # daily close for realised-vol context
            dc = pq[pq["mod"] <= 17 * 60].groupby("d")["m1"].last()
            wti_close = pd.Series(dc.values, index=pd.to_datetime(list(dc.index)))
        pq = pq[(pq["mod"] >= 600) & (pq["mod"] <= 720)]   # 10:00-12:00 ET
        groups[prod] = {d: g for d, g in pq.groupby("d")}
    return groups, wti_close


def _wmean(g, lo, hi):
    if g is None:
        return np.nan
    s = g.loc[(g["mod"] >= lo) & (g["mod"] <= hi), "m1"]
    return s.mean() if len(s) else np.nan


def reactions(groups, day):
    """For each product: %-move 5-min before vs at / +5 / +10, plus max spike."""
    import datetime as dt
    wd = dt.date.fromisoformat(str(day)).weekday()      # Thu(3)=holiday-shifted 11:00
    p = 11 * 60 if wd == 3 else 10 * 60 + 30
    out = {}
    for prod, gdict in groups.items():
        g = gdict.get(day)
        pre5 = _wmean(g, p - 5, p - 1)
        at = _wmean(g, p, p)
        post5 = _wmean(g, p + 1, p + 5)
        post10 = _wmean(g, p + 1, p + 10)
        out[f"{prod}_pre5"] = pre5
        out[f"{prod}_at_pct"] = (at - pre5) / pre5 * 100 if pre5 and pd.notna(at) else np.nan
        out[f"{prod}_post5_pct"] = (post5 - pre5) / pre5 * 100 if pre5 and pd.notna(post5) else np.nan
        out[f"{prod}_post10_pct"] = (post10 - pre5) / pre5 * 100 if pre5 and pd.notna(post10) else np.nan
        # max absolute spike within +10 min
        if g is not None and pd.notna(pre5) and pre5:
            win = g.loc[(g["mod"] >= p) & (g["mod"] <= p + 10), "m1"]
            out[f"{prod}_spike_pct"] = ((win - pre5) / pre5 * 100).abs().max() if len(win) else np.nan
        else:
            out[f"{prod}_spike_pct"] = np.nan
    return out


# ----------------------------------------------------------- build ------------
def build():
    exp = load_expectations()
    groups, wti_close = load_prices()
    wret = wti_close.pct_change() * 100 if wti_close is not None else None
    prod = pd.read_csv(os.path.join(DATA, "eia_production.csv"))
    prod["period"] = pd.to_datetime(prod["period"]).dt.date

    # one row per EIA release (Wed/Thu); API (Tue) is matched in from the days prior
    exp = exp.sort_values("release_date").reset_index(drop=True)
    eia = exp[exp["EIA_Crude__actual"].notna()].copy()
    rows = []
    for _, e in eia.iterrows():
        d = e["release_date"]
        rec = {"release_date": d}
        for c in e.index:
            if c.startswith("EIA_"):
                rec[c] = e[c]
        # match the week's API estimate from the 1-3 days before the EIA print
        prior = exp[(exp["release_date"] < d)
                    & (exp["release_date"] >= (pd.Timestamp(d) - pd.Timedelta(days=3)).date())]
        api_a = api_c = np.nan
        ap = prior[prior["API_Crude__actual"].notna()]
        if len(ap):
            api_a = ap["API_Crude__actual"].iloc[-1]
            api_c = ap["API_Crude__consensus"].iloc[-1]
        rec["API_Crude__actual"], rec["API_Crude__consensus"] = api_a, api_c

        def s(lbl, fld="consensus"):
            a = e.get(f"{lbl}__actual"); c = e.get(f"{lbl}__{fld}")
            return (a - c) if (pd.notna(a) and pd.notna(c)) else np.nan
        rec["crude_surp_cons"] = s("EIA_Crude")                 # +ve = bigger build than expected (bearish)
        rec["crude_surp_API"] = (e["EIA_Crude__actual"] - api_a) if pd.notna(api_a) else np.nan
        rec["API_surp_cons"] = (api_a - api_c) if (pd.notna(api_a) and pd.notna(api_c)) else np.nan
        rec["dist_surp_cons"] = s("EIA_Distillate")
        rec["gas_surp_cons"] = s("EIA_Gasoline")
        rec["util_surp_cons"] = s("EIA_RefineryUtil")
        pr = prod[prod["period"] <= d]
        rec["prod_wow"] = pr["wow"].iloc[-1] if len(pr) else np.nan
        # realised vol (20d) before the release
        if wret is not None:
            past = wret[wret.index < pd.Timestamp(d)]
            rec["rvol_20d"] = past.iloc[-20:].std() if len(past) >= 20 else np.nan
        rec.update(reactions(groups, d))
        # cross-product spreads (relative %-move): WTI-Brent (US-specific) & HO crack
        rec["wti_brent_react10"] = (rec.get("WTI_post10_pct", np.nan) - rec.get("Brent_post10_pct", np.nan))
        rec["crack_react10"] = (rec.get("HO_post10_pct", np.nan) - rec.get("WTI_post10_pct", np.nan))
        rows.append(rec)

    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, "v2_dataset.csv"), index=False)
    return df


# ----------------------------------------------------------- compare ----------
def compare(df):
    """Signal (from surprise) vs actual reaction across HORIZONS (at / +5 / +10)
    -> hit rate + discrepancy log."""
    out = {}
    specs = [("crude_surp_cons", "WTI", "EIA crude vs consensus, on WTI"),
             ("crude_surp_cons", "Brent", "EIA crude vs consensus, on Brent"),
             ("crude_surp_API", "WTI", "EIA crude vs API (confirmation), on WTI"),
             ("API_surp_cons", "WTI", "API crude vs consensus (Tue), on WTI"),
             ("dist_surp_cons", "HO", "EIA distillate vs consensus, on heating oil")]
    horizons = [("at_pct", "hit_at_release"), ("post5_pct", "hit_+5min"),
                ("post10_pct", "hit_+10min")]
    res = []
    for scol, prod, label in specs:
        row = {"signal": label}
        n_ref = 0
        for hcol, hname in horizons:
            n, hit, corr = _hitcorr(df, scol, f"{prod}_{hcol}")
            row[hname] = hit
            n_ref = max(n_ref, n)
        # correlation at +10min for reference
        _, _, corr10 = _hitcorr(df, scol, f"{prod}_post10_pct")
        row["n"] = n_ref
        row["corr_+10min"] = corr10
        res.append(row)
    comp = pd.DataFrame(res)[["signal", "n", "hit_at_release", "hit_+5min", "hit_+10min", "corr_+10min"]]
    comp.to_csv(os.path.join(OUT, "v2_signal_vs_reaction.csv"), index=False)
    out["comparison"] = comp

    # discrepancy log: EIA crude consensus signal vs WTI reaction disagreed
    d = df.dropna(subset=["crude_surp_cons", "WTI_post10_pct"])
    d = d[d["crude_surp_cons"].abs() > 0.5]            # material surprise (>0.5M bbl)
    d = d.assign(pred_dir=-np.sign(d["crude_surp_cons"]), act_dir=np.sign(d["WTI_post10_pct"]))
    disc = d[d["pred_dir"] != d["act_dir"]].copy()
    keep = ["release_date", "EIA_Crude__actual", "EIA_Crude__consensus", "API_Crude__actual",
            "crude_surp_cons", "crude_surp_API", "WTI_post10_pct", "WTI_spike_pct"]
    disc[keep].to_csv(os.path.join(OUT, "v2_discrepancies.csv"), index=False)
    out["discrepancies"] = disc[keep]
    out["n_material"] = len(d)
    return out


def _hitcorr(sub, scol, ycol):
    """surprise>0 (bigger build than expected) -> bearish -> expect price down."""
    d = sub.dropna(subset=[scol, ycol])
    d = d[d[scol].abs() > 1e-9]
    if len(d) < 8:
        return len(d), np.nan, np.nan
    hit = (-np.sign(d[scol]) == np.sign(d[ycol])).mean()
    corr = np.corrcoef(d[scol], d[ycol])[0, 1]
    return len(d), round(float(hit), 3), round(float(corr), 3)


def conditioned_edges(df):
    """Search for a directional edge in conditioned buckets (the user's ask).
    Tests crude surprise -> {WTI outright, WTI-Brent spread} and distillate ->
    {HO outright, HO crack}, across agreement / surprise-size / vol buckets."""
    print("\n" + "=" * 64)
    print("  CONDITIONED-EDGE SEARCH  (does an edge appear in any regime?)")
    print("=" * 64)
    rows = []

    def add(name, sub, scol, ycol, inst):
        n, hit, corr = _hitcorr(sub, scol, ycol)
        rows.append({"bucket": name, "instrument": inst, "n": n, "hit": hit, "corr": corr})

    d = df.copy()
    d["agree"] = np.where(np.sign(d["crude_surp_cons"]) == np.sign(d["API_surp_cons"]),
                          "API+EIA agree", "API/EIA diverge")
    for scol, ycol, inst in [("crude_surp_cons", "WTI_post5_pct", "WTI +5min"),
                             ("crude_surp_cons", "WTI_post10_pct", "WTI +10min"),
                             ("crude_surp_cons", "wti_brent_react10", "WTI-Brent spread"),
                             ("dist_surp_cons", "HO_post5_pct", "HO +5min"),
                             ("dist_surp_cons", "HO_post10_pct", "HO +10min"),
                             ("dist_surp_cons", "crack_react10", "HO crack")]:
        add("ALL", d, scol, ycol, inst)
        # API/EIA agreement (crude only)
        if scol == "crude_surp_cons":
            for ag in ["API+EIA agree", "API/EIA diverge"]:
                add(ag, d[d["agree"] == ag], scol, ycol, inst)
        # surprise-size terciles
        dd = d.dropna(subset=[scol]).copy()
        if len(dd) > 12:
            dd["sz"] = pd.qcut(dd[scol].abs(), 3, labels=["small", "mid", "large"], duplicates="drop")
            for sz in ["small", "large"]:
                add(f"|surp| {sz}", dd[dd["sz"] == sz], scol, ycol, inst)
        # vol regime terciles
        dv = d.dropna(subset=["rvol_20d", scol]).copy()
        if len(dv) > 12:
            dv["vr"] = pd.qcut(dv["rvol_20d"], 3, labels=["lowvol", "midvol", "highvol"], duplicates="drop")
            for vr in ["lowvol", "highvol"]:
                add(f"{vr}", dv[dv["vr"] == vr], scol, ycol, inst)

    res = pd.DataFrame(rows)
    res.to_csv(os.path.join(OUT, "v2_conditioned_edges.csv"), index=False)
    print(res.to_string(index=False))
    # flag buckets that deviate from coin-flip (hit<=0.42 or >=0.58, or |corr|>=0.18, n>=30)
    edge = res[(res["n"] >= 30) & ((res["hit"] >= 0.58) | (res["hit"] <= 0.42)
                                   | (res["corr"].abs() >= 0.18))]
    print(f"\n  buckets deviating from coin-flip (hit<=0.42 or >=0.58 or |corr|>=0.18, n>=30): {len(edge)}")
    if len(edge):
        print(edge.to_string(index=False))
    return res, edge


def seasonal_regime(df):
    """Seasonal & regime effects: crude surprise -> WTI hit & move size by quarter,
    driving season (May-Sep), and realised-vol regime."""
    d = df.dropna(subset=["crude_surp_cons", "WTI_post10_pct", "WTI_spike_pct"]).copy()
    d["rd"] = pd.to_datetime(d["release_date"])
    d["quarter"] = "Q" + d["rd"].dt.quarter.astype(str)
    d["season"] = np.where(d["rd"].dt.month.between(5, 9), "driving (May-Sep)", "off-season")
    d["hit"] = (-np.sign(d["crude_surp_cons"]) == np.sign(d["WTI_post10_pct"])).astype(int)

    def agg(g):
        return pd.Series({"n": len(g), "hit_rate": round(g["hit"].mean(), 3),
                          "mean_spike_pct": round(g["WTI_spike_pct"].mean(), 3)})
    tables = {"quarter": d.groupby("quarter").apply(agg),
              "season": d.groupby("season").apply(agg)}
    if d["rvol_20d"].notna().sum() > 30:
        d["vol_regime"] = pd.qcut(d["rvol_20d"], 3, labels=["low", "mid", "high"], duplicates="drop")
        tables["vol_regime"] = d.groupby("vol_regime").apply(agg)
    for k, v in tables.items():
        v.to_csv(os.path.join(OUT, f"v2_seasonal_{k}.csv"))
    return tables


def when_mattered(df):
    """When did inventories matter? Split by the SIZE of the WTI move and see what
    characterises the big-move releases (surprise size, vol, API divergence)."""
    d = df.dropna(subset=["WTI_spike_pct", "crude_surp_cons"]).copy()
    d["grp"] = pd.qcut(d["WTI_spike_pct"], 3, labels=["muted", "mid", "mattered"], duplicates="drop")
    d["api_div"] = (np.sign(d["crude_surp_cons"]) != np.sign(d["API_surp_cons"])).astype(float)
    g = d.groupby("grp").agg(
        n=("WTI_spike_pct", "size"),
        mean_spike_pct=("WTI_spike_pct", "mean"),
        mean_abs_surprise=("crude_surp_cons", lambda s: s.abs().mean()),
        mean_rvol=("rvol_20d", "mean"),
        api_divergence_rate=("api_div", "mean"),
    ).round(3)
    g.to_csv(os.path.join(OUT, "v2_when_mattered.csv"))
    return g


def intraday_curve(df, groups=None, offsets=range(-5, 16)):
    """Minute-by-minute reaction relative to the pre-release baseline, averaged
    across releases, to locate the time range where the bulk of the move happens.
    Returns mean |move| at each minute offset from the print, per product."""
    import datetime as dt
    if groups is None:
        groups, _ = load_prices()
    offsets = list(offsets)
    bucket = {prod: {k: [] for k in offsets} for prod in groups}
    for d in df["release_date"]:
        wd = dt.date.fromisoformat(str(d)).weekday()
        p = 11 * 60 if wd == 3 else 10 * 60 + 30
        for prod, gdict in groups.items():
            g = gdict.get(d)
            if g is None:
                continue
            pre5 = _wmean(g, p - 5, p - 1)
            if not pre5 or pd.isna(pre5):
                continue
            for k in offsets:
                px = _wmean(g, p + k, p + k)
                if pd.notna(px):
                    bucket[prod][k].append((px - pre5) / pre5 * 100)
    rows = []
    for k in offsets:
        row = {"minute": k}
        for prod in groups:
            vals = bucket[prod][k]
            row[f"{prod}_absmove"] = round(float(np.mean(np.abs(vals))), 4) if vals else np.nan
            row[f"{prod}_n"] = len(vals)
        rows.append(row)
    cur = pd.DataFrame(rows)
    # share of the +10min move already realised by each minute (WTI), and per-minute step
    base = cur.loc[cur["minute"] == 10, "WTI_absmove"]
    base = float(base.iloc[0]) if len(base) and pd.notna(base.iloc[0]) else np.nan
    cur["WTI_share_of_10min"] = (cur["WTI_absmove"] / base).round(3) if base else np.nan
    cur["WTI_step"] = cur["WTI_absmove"].diff().round(4)
    cur.to_csv(os.path.join(OUT, "v2_intraday_curve.csv"), index=False)
    return cur


def signal_accuracy(df):
    """Accuracy of the GENERATED signal vs the actual move (WTI), by horizon.
    Naive = follow every print; Rule = follow small surprises, fade large ones."""
    d = df.dropna(subset=["crude_surp_cons"]).copy()
    d = d[d["crude_surp_cons"].abs() > 1e-9]
    qlo, qhi = d["crude_surp_cons"].abs().quantile([1 / 3, 2 / 3])
    abss = d["crude_surp_cons"].abs()
    d["sz"] = np.where(abss > qhi, "large", np.where(abss < qlo, "small", "mid"))
    d["sig_naive"] = -np.sign(d["crude_surp_cons"])               # draw -> long
    d["sig_rule"] = np.where(d["sz"] == "small", -np.sign(d["crude_surp_cons"]),
                             np.where(d["sz"] == "large", np.sign(d["crude_surp_cons"]), 0.0))
    horizons = [("WTI_at_pct", "acc_at_release"), ("WTI_post5_pct", "acc_+5min"),
                ("WTI_post10_pct", "acc_+10min")]

    def acc_row(name, sub, sigcol):
        row = {"signal": name}
        nmax = 0
        for mcol, hn in horizons:
            s = sub.dropna(subset=[mcol])
            s = s[(s[sigcol] != 0) & (s[mcol].abs() > 1e-9)]
            row[hn] = round(float((np.sign(s[mcol]) == s[sigcol]).mean()), 3) if len(s) else np.nan
            nmax = max(nmax, len(s))
        row["n_trades"] = nmax
        return row

    rows = [
        acc_row("Naive: follow every print", d, "sig_naive"),
        acc_row("Rule: follow small, fade large", d[d["sz"] != "mid"], "sig_rule"),
        acc_row("   small surprises (follow)", d[d["sz"] == "small"], "sig_naive"),
        acc_row("   large surprises (fade)", d[d["sz"] == "large"], "sig_rule"),
    ]
    res = pd.DataFrame(rows)[["signal", "n_trades", "acc_at_release", "acc_+5min", "acc_+10min"]]
    res.to_csv(os.path.join(OUT, "v2_signal_accuracy.csv"), index=False)
    return res


def main():
    print("=" * 64)
    print("  EIA INVENTORY-IMPACT v2  (consensus/API surprise -> price)")
    print("=" * 64)
    df = build()
    n_px = df["WTI_post10_pct"].notna().sum()
    print(f"  releases: {len(df)}  | with WTI price reaction: {n_px}")
    print(f"  consensus coverage: crude={df['crude_surp_cons'].notna().sum()}, "
          f"API={df['API_surp_cons'].notna().sum()}, dist={df['dist_surp_cons'].notna().sum()}, "
          f"util={df['util_surp_cons'].notna().sum()}")
    r = compare(df)
    print("\n  SIGNAL vs REACTION (hit = surprise-implied direction matched +10min move):")
    print(r["comparison"].to_string(index=False))
    print(f"\n  Material-surprise releases: {r['n_material']}  |  "
          f"discrepancies (signal != tape): {len(r['discrepancies'])}")
    print("\n  Sample discrepancies (print said one thing, tape did the other):")
    print(r["discrepancies"].head(8).to_string(index=False))
    print("\n--- SIGNAL GENERATION ACCURACY (WTI, by horizon) ---")
    print(signal_accuracy(df).to_string(index=False))
    print("\n--- INTRADAY REACTION CURVE (mean |move| by minute from print) ---")
    cur = intraday_curve(df, groups=load_prices()[0])
    print(cur[["minute", "WTI_absmove", "WTI_step", "WTI_share_of_10min",
               "Brent_absmove"]].to_string(index=False))
    conditioned_edges(df)
    print("\n--- SEASONAL / REGIME (crude surprise -> WTI) ---")
    for k, v in seasonal_regime(df).items():
        print(f"  by {k}:"); print(v.to_string())
    print("\n--- WHEN DID INVENTORIES MATTER? (by size of WTI move) ---")
    print(when_mattered(df).to_string())
    return df, r


if __name__ == "__main__":
    main()
