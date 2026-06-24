"""
================================================================================
  SYSTEMATIC EIA INVENTORY-IMPACT FRAMEWORK  (Phase 1, standalone)
================================================================================
Builds a pre-trade signal, measures intraday price reactions, runs trader
analytics (hit-rate / fade / entry-timing / P&L), conditions on regime, scores a
composite amplifier model, analyses the full WTI term-structure reaction, and
produces a trading memo for the next EIA release (2026-06-03).

Data lives in ../Data relative to this script.  Outputs (CSV + PNG) go to
./output.  See the prompt spec for section-by-section detail.

NOTES ON DATA REALITY (verified before coding):
  * 13 EIA releases 2026-03-11 .. 2026-06-03.  Release #12 (2026-05-28) is a
    THURSDAY 11:00 ET print (Memorial-Day shift).  Windows are parameterised off
    each release's actual print time.
  * 1-min price data ends ~2026-05-22, so intraday reactions exist for 11
    releases (03-11 .. 05-20).  05-28 & 06-03 are inventory-only; 06-03 is the
    forecast target.  Missing windows -> NaN and are excluded from stats.
  * US10Y in the macro file is stored /10 (0.4453 == 4.453%); rescaled to %.
  * RBOB (RB) 1-min price data is NOT available -> gasoline signal expressed via
    the HO crack proxy.  Flagged for Phase-2 data acquisition.
================================================================================
"""

import os
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.colors import TwoSlopeNorm
from scipy import stats

# ------------------------------------------------------------------ paths -----
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "Data")
OUT = os.path.join(HERE, "output")
os.makedirs(OUT, exist_ok=True)

RBOB_NOTE = ("RBOB price data not available - gasoline inventory signal expressed "
             "via HO crack proxy. Flagged for Phase 2 data acquisition.")

ET = "US/Eastern"

# Map our internal product key -> standalone EIA csv file
EIA_FILES = {
    "crude":       "eia_Crude_Oil_Stocks_US.csv",
    "cushing":     "eia_Cushing_Crude_Stocks.csv",
    "refinery_in": "eia_Crude_Inputs_Refineries_US.csv",
    "distillate":  "eia_Distillate_Stocks_US.csv",
    "gasoline":    "eia_Gasoline_Stocks_US.csv",
    "jet":         "eia_Jet_Fuel_Stocks_US.csv",
    "propane":     "eia_Propane_Stocks_US.csv",
    "residual":    "eia_Residual_FO_Stocks_US.csv",
    "total_petro": "eia_Total_Petroleum_Stocks_US.csv",
}

# Price products that have 1-min data, with parquet source + unit handling.
# bbl_factor converts native unit -> $/bbl for crack maths.
PRICE_PRODUCTS = {
    "WTI":   {"parquet": None,                 "bbl_factor": 1.0},      # uses MAM csv
    "Brent": {"parquet": "LCO_data.parquet",   "bbl_factor": 1.0},      # $/bbl
    "HO":    {"parquet": "HO_data.parquet",    "bbl_factor": 42.0},     # $/gal*42
    "LGO":   {"parquet": "LGO_data.parquet",   "bbl_factor": 1.0/7.45}, # $/MT /7.45
}

# ---------------------------------------------------------------- weights -----
# Composite signal (Section 5) is a linear model: score = sum_k w_k * feature_k.
# Each feature is sign-locked to economic intuition and scaled to ~[-1, 1]
# (bullish-for-crude == positive).  These PRIORS reproduce the original hand-set
# rule-based weights; autotune_weights.py can override them via tuned_weights.json.
COMPOSITE_WEIGHTS_PRIOR = {
    "crude":         2.0,   # crude draw (vs build)
    "distillate":    0.3,   # distillate draw
    "gasoline":      0.3,   # gasoline draw
    "cushing":       0.5,   # Cushing-driven (delivery point)
    "days_supply":   0.3,   # days-of-supply tightening
    "backwardation": 0.5,   # WTI M1-M2 backwardation
    "dxy":           0.4,   # USD weakness
    "gold":          0.3,   # gold falling (risk-on)
}
TUNED_WEIGHTS_FILE = os.path.join(HERE, "tuned_weights.json")


def composite_feature_row(inv, pre, dt, dos_change):
    """Continuous, sign-locked features in ~[-1,1] for one release.
    inv/pre are DataFrames indexed by release_date.  NaN inputs -> 0 (neutral)."""
    f = {}

    def g(df, col):
        return df.loc[dt, col] if (dt in df.index and col in df.columns) else np.nan

    cc = g(inv, "crude_chg")
    f["crude"] = float(np.clip(-cc / 4000.0, -1, 1)) if pd.notna(cc) else 0.0
    dc = g(inv, "distillate_chg")
    f["distillate"] = float(np.clip(-dc / 3000.0, -1, 1)) if pd.notna(dc) else 0.0
    gc = g(inv, "gasoline_chg")
    f["gasoline"] = float(np.clip(-gc / 3000.0, -1, 1)) if pd.notna(gc) else 0.0
    cdr = g(inv, "cushing_driven")
    f["cushing"] = float(1 if (cdr and pd.notna(cc) and cc < 0) else (-1 if (cdr and pd.notna(cc) and cc > 0) else 0))
    f["days_supply"] = float(np.clip(-dos_change / 0.5, -1, 1)) if pd.notna(dos_change) else 0.0
    m12 = g(pre, "wti_m1_m2")
    f["backwardation"] = float(np.clip(m12 / 1.0, -1, 1)) if pd.notna(m12) else 0.0
    dx = g(pre, "dxy_dod")
    f["dxy"] = float(np.clip(-dx / 0.5, -1, 1)) if pd.notna(dx) else 0.0
    gd = g(pre, "gold_dod")
    f["gold"] = float(-np.clip(gd / 2.0, -1, 1)) if pd.notna(gd) else 0.0
    return f


def build_feature_matrix(D):
    """Feature matrix (release_date x feature) for the composite linear model."""
    inv = D["inv"].set_index("release_date")
    pre = D["pre"].set_index("release_date")
    dos = inv["days_of_supply"]
    rows = []
    for i, dt in enumerate(inv.index):
        dd = (dos.iloc[i] - dos.iloc[i - 1]) if (i > 0 and pd.notna(dos.iloc[i])
                                                 and pd.notna(dos.iloc[i - 1])) else np.nan
        f = composite_feature_row(inv, pre, dt, dd)
        f["release_date"] = dt
        rows.append(f)
    return pd.DataFrame(rows).set_index("release_date")


def score_features(feat_df, weights):
    """Linear score per release given a {feature: weight} dict."""
    keys = list(COMPOSITE_WEIGHTS_PRIOR.keys())
    w = np.array([weights.get(k, 0.0) for k in keys])
    return feat_df[keys].values @ w


def load_active_weights():
    """tuned_weights.json if present, else the priors."""
    if os.path.exists(TUNED_WEIGHTS_FILE):
        import json
        with open(TUNED_WEIGHTS_FILE) as fh:
            tuned = json.load(fh).get("weights", {})
        w = dict(COMPOSITE_WEIGHTS_PRIOR)
        w.update({k: float(v) for k, v in tuned.items()})
        return w, "TUNED (tuned_weights.json)"
    return dict(COMPOSITE_WEIGHTS_PRIOR), "PRIOR (hand-set)"


# ============================================================================
#  HELPERS
# ============================================================================
def _to_et(ts_series):
    """str/naive/utc timestamps -> tz-aware US/Eastern."""
    s = pd.to_datetime(ts_series, utc=True)
    return s.dt.tz_convert(ET)


def _parse_print_time(s):
    """'10:30 AM ET' -> (10, 30).  '11:00 AM ET' -> (11, 0)."""
    s = str(s).strip()
    hm = s.split()[0]
    h, m = hm.split(":")
    h, m = int(h), int(m)
    if "PM" in s.upper() and h != 12:
        h += 12
    return h, m


def _mins(h, m):
    return h * 60 + m


def window_mean(df, day, start_min, end_min, col):
    """Mean of `col` for rows on `day` (ET date) whose minute-of-day is in
    [start_min, end_min] inclusive.  df must have 'ts_et' and a 'min_of_day'."""
    if col not in df.columns:
        return np.nan
    m = (df["et_date"] == day) & (df["min_of_day"] >= start_min) & (df["min_of_day"] <= end_min)
    sub = df.loc[m, col]
    return sub.mean() if len(sub) else np.nan


def iso_week(dt):
    return pd.Timestamp(dt).isocalendar().week


def fmt(x, d=2):
    return "n/a" if (x is None or (isinstance(x, float) and np.isnan(x))) else f"{x:,.{d}f}"


def sign(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return np.nan
    return 1 if x > 0 else (-1 if x < 0 else 0)


# ============================================================================
#  LOAD DATA
# ============================================================================
def load_data():
    print("=" * 64)
    print("  LOADING DATA")
    print("=" * 64)
    D = {}

    # ---- EIA standalone weekly series (full 2020-2026 history) ----------
    eia = {}
    for key, fname in EIA_FILES.items():
        df = pd.read_csv(os.path.join(DATA, fname))
        df["period"] = pd.to_datetime(df["period"])
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df[["period", "value", "units"]].sort_values("period").reset_index(drop=True)
        df["wow"] = df["value"].diff()
        df["iso_week"] = df["period"].apply(iso_week)
        eia[key] = df
        print(f"  EIA {key:11s}: {len(df):3d} obs  {df['period'].min().date()} -> {df['period'].max().date()}")
    D["eia"] = eia

    # ---- EIA release-level file (PADDs, timing) -------------------------
    rel = pd.read_csv(os.path.join(DATA, "eia_mar_may_2026.csv"))
    D["eia_release_raw"] = rel
    D["eia_wide"] = pd.pivot_table(rel, index="period_week_ending_fri",
                                   columns="series_label", values="value")

    # Build the canonical RELEASES table (13 rows)
    rcols = ["release_date", "release_weekday", "release_time_et", "period_week_ending_fri"]
    releases = rel[rcols].drop_duplicates().sort_values("release_date").reset_index(drop=True)
    releases["release_date"] = pd.to_datetime(releases["release_date"]).dt.date
    releases["week_ending"] = pd.to_datetime(releases["period_week_ending_fri"]).dt.date
    releases[["ph", "pm"]] = releases["release_time_et"].apply(
        lambda s: pd.Series(_parse_print_time(s)))
    releases["print_min"] = releases.apply(lambda r: _mins(r.ph, r.pm), axis=1)
    D["releases"] = releases
    print(f"\n  Releases: {len(releases)}  "
          f"({releases['release_date'].iloc[0]} .. {releases['release_date'].iloc[-1]})")

    # ---- Macro -----------------------------------------------------------
    macro = pd.read_excel(os.path.join(DATA, "gold_dxy_us10y_mar_may_2026.xlsx"))
    macro["Date"] = pd.to_datetime(macro["Date"])
    macro = macro.sort_values("Date").reset_index(drop=True)
    # US10Y stored /10 -> rescale to percent if it looks fractional
    if macro["US10Y"].median() < 1.5:
        macro["US10Y_pct"] = macro["US10Y"] * 10.0
    else:
        macro["US10Y_pct"] = macro["US10Y"]
    macro["DXY_dod"] = macro["DXY"].pct_change() * 100
    macro["Gold_dod"] = macro["Gold"].pct_change() * 100
    D["macro"] = macro
    print(f"  Macro: {len(macro)} days  {macro['Date'].min().date()} -> {macro['Date'].max().date()}"
          f"  (US10Y rescaled x10 -> %)")

    # ---- WTI term structure (MAM csv: clean header; parquet is broken) ---
    wti = pd.read_csv(os.path.join(DATA, "CL_wti_2026_MAM.csv"))
    mid = {c: f"m{c.split('||')[0][1:]}" for c in wti.columns if "weighted_mid" in c}
    wti = wti.rename(columns=mid)
    keep = ["timestamp"] + [c for c in wti.columns if c.startswith("m") and c[1:].isdigit()]
    wti = wti[keep].copy()
    wti["ts_et"] = _to_et(wti["timestamp"])
    wti["et_date"] = wti["ts_et"].dt.date
    wti["min_of_day"] = wti["ts_et"].dt.hour * 60 + wti["ts_et"].dt.minute
    D["WTI"] = wti
    print(f"  WTI (MAM): {len(wti):,} rows  {wti['ts_et'].min()} -> {wti['ts_et'].max()}")

    # ---- Other 1-min products (parquet, slice to 2026 window) -----------
    for prod, cfg in PRICE_PRODUCTS.items():
        if prod == "WTI":
            continue
        pq = pd.read_parquet(os.path.join(DATA, cfg["parquet"]))
        midp = {c: f"m{c.split('||')[0][1:]}" for c in pq.columns if "weighted_mid" in c}
        pq = pq.rename(columns=midp)
        keepp = ["timestamp"] + [c for c in pq.columns if c.startswith("m") and c[1:].isdigit()]
        pq = pq[keepp].copy()
        pq["ts_et"] = _to_et(pq["timestamp"])
        # slice from 2026-02-01 onward (enough for 30d vol before first release)
        pq = pq[pq["ts_et"] >= pd.Timestamp("2026-02-01", tz=ET)].copy()
        pq["et_date"] = pq["ts_et"].dt.date
        pq["min_of_day"] = pq["ts_et"].dt.hour * 60 + pq["ts_et"].dt.minute
        D[prod] = pq.reset_index(drop=True)
        print(f"  {prod}: {len(pq):,} rows (>=2026-02)  ends {pq['ts_et'].max()}")

    print(f"\n  {RBOB_NOTE}\n")
    return D


# ============================================================================
#  SECTION 2A : INVENTORY WoW, SEASONAL NORMS, SURPRISES
# ============================================================================
def seasonal_norm(df, week, years=range(2020, 2025)):
    """5yr (2020-2024) average WoW change for the given ISO calendar week."""
    m = (df["iso_week"] == week) & (df["period"].dt.year.isin(list(years)))
    v = df.loc[m, "wow"]
    return v.mean() if len(v) else np.nan


def seasonal_norm_table(df, years=range(2020, 2025)):
    """52-week seasonal mean & std of WoW (for plots / context)."""
    h = df[df["period"].dt.year.isin(list(years))]
    g = h.groupby("iso_week")["wow"]
    return pd.DataFrame({"mean": g.mean(), "std": g.std()})


def compute_inventory_wow(D):
    print("=" * 64)
    print("  SECTION 2A : INVENTORY WoW CHANGES, SEASONAL NORMS, SURPRISES")
    print("=" * 64)
    eia = D["eia"]
    rel = D["releases"]
    wide = D["eia_wide"]

    rows = []
    for _, r in rel.iterrows():
        we = pd.Timestamp(r["week_ending"])
        rec = {"release_date": r["release_date"], "week_ending": r["week_ending"],
               "print_min": r["print_min"], "weekday": r["release_weekday"]}

        def chg(key):
            s = eia[key]
            hit = s[s["period"] == we]
            return float(hit["wow"].iloc[0]) if len(hit) else np.nan

        def lvl(key):
            s = eia[key]
            hit = s[s["period"] == we]
            return float(hit["value"].iloc[0]) if len(hit) else np.nan

        rec["crude_chg"] = chg("crude")
        rec["crude_lvl"] = lvl("crude")
        rec["cushing_chg"] = chg("cushing")
        rec["cushing_lvl"] = lvl("cushing")
        rec["distillate_chg"] = chg("distillate")
        rec["distillate_lvl"] = lvl("distillate")
        rec["gasoline_chg"] = chg("gasoline")
        rec["gasoline_lvl"] = lvl("gasoline")
        rec["jet_chg"] = chg("jet")
        rec["propane_chg"] = chg("propane")
        rec["residual_chg"] = chg("residual")
        rec["total_petro_chg"] = chg("total_petro")
        rec["refinery_input_lvl"] = lvl("refinery_in")
        rec["refinery_input_chg"] = chg("refinery_in")  # MBBL/D

        # cushing share of crude move (%), flag if >40
        rec["cushing_share_pct"] = (
            abs(rec["cushing_chg"]) / abs(rec["crude_chg"]) * 100
            if rec["crude_chg"] not in (0, np.nan) and not np.isnan(rec["crude_chg"]) and rec["crude_chg"] != 0
            else np.nan)
        rec["cushing_driven"] = (rec["cushing_share_pct"] > 40) if not np.isnan(rec["cushing_share_pct"]) else False

        # total product draws ex-crude
        rec["total_product_chg"] = np.nansum([rec["distillate_chg"], rec["gasoline_chg"],
                                              rec["jet_chg"], rec["propane_chg"], rec["residual_chg"]])

        # implied demand proxy: crude_chg - refinery_input*7  (7-day equiv)
        rec["implied_demand_proxy"] = rec["crude_chg"] - rec["refinery_input_chg"] * 7

        # days of supply = crude stocks / refinery inputs (MBBL/D)
        rec["days_of_supply"] = (rec["crude_lvl"] / rec["refinery_input_lvl"]
                                 if rec["refinery_input_lvl"] else np.nan)

        # surprise vs seasonal norm (5yr same-week)
        wk = iso_week(we)
        for key, col in [("crude", "crude"), ("distillate", "distillate"),
                         ("gasoline", "gasoline"), ("jet", "jet"),
                         ("propane", "propane"), ("residual", "residual")]:
            sn = seasonal_norm(eia[key], wk)
            rec[f"{col}_seasonal_norm"] = sn
            rec[f"{col}_surprise"] = rec[f"{col}_chg"] - sn if not np.isnan(sn) else np.nan

        # PADD breakdown from release file
        wkey = str(r["week_ending"])
        for p in range(1, 6):
            lab = f"PADD{p} Crude Stocks"
            try:
                rec[f"padd{p}_lvl"] = float(wide.loc[wkey, lab])
            except Exception:
                rec[f"padd{p}_lvl"] = np.nan

        rows.append(rec)

    inv = pd.DataFrame(rows)
    # PADD WoW
    for p in range(1, 6):
        inv[f"padd{p}_chg"] = inv[f"padd{p}_lvl"].diff()
    inv.to_csv(os.path.join(OUT, "tbl_inventory_wow.csv"), index=False)

    # console summary
    show = inv[["release_date", "crude_chg", "crude_seasonal_norm", "crude_surprise",
                "cushing_chg", "cushing_share_pct", "distillate_chg", "gasoline_chg",
                "days_of_supply"]].copy()
    print(show.to_string(index=False,
          formatters={c: (lambda v: fmt(v, 0)) for c in
                      ["crude_chg", "crude_seasonal_norm", "crude_surprise", "cushing_chg",
                       "distillate_chg", "gasoline_chg"]}))
    print()
    D["inv"] = inv
    return inv


# ============================================================================
#  SECTION 1 : PRE-TRADE SIGNAL  (trend + curve + macro composite)
# ============================================================================
def _eff_day(df, day, s, e, col="m1"):
    """Return (effective_date, used_fallback). If `day` has data in the window
    use it; else fall back to the most recent prior session that does (needed for
    the 06-03 target, whose intraday window is empty -> use last snapshot)."""
    if not np.isnan(window_mean(df, day, s, e, col)):
        return day, False
    for d in sorted([d for d in df["et_date"].unique() if d <= day], reverse=True):
        if not np.isnan(window_mean(df, d, s, e, col)):
            return d, True
    return day, False


def _curve_regime(m1, m2, m3, m6, m12):
    vals = [m1, m2, m3, m6, m12]
    if any(np.isnan(v) for v in vals):
        return "Unknown"
    if m1 > m2 > m3 > m6 > m12:
        return "Full Backwardation"
    if m1 < m2 < m3 < m6 < m12:
        return "Full Contango"
    if m1 > m2:
        return "Front Backwardation"
    return "Mixed"


def build_pretrade_signal(D):
    print("=" * 64)
    print("  SECTION 1 : PRE-TRADE SIGNAL (trend + curve + macro)")
    print("=" * 64)
    eia = D["eia"]
    rel = D["releases"]
    macro = D["macro"]
    inv = D["inv"]

    rows = []
    for _, r in rel.iterrows():
        we = pd.Timestamp(r["week_ending"])
        day = r["release_date"]
        pmin = int(r["print_min"])
        rec = {"release_date": day}

        # ---- 1A inventory trend signal (pre-release) ----
        cs = eia["crude"]
        idx = cs.index[cs["period"] == we]
        recent_trend = np.nan
        if len(idx):
            i = idx[0]
            recent_trend = cs["wow"].iloc[max(0, i - 4):i].mean()  # WoW[t-4:t-1]
        wk = iso_week(we)
        snorm = seasonal_norm(cs, wk)
        implied = (snorm if not np.isnan(snorm) else 0) + 0.5 * (recent_trend if not np.isnan(recent_trend) else 0)
        rec["crude_recent_trend_4w"] = recent_trend
        rec["crude_seasonal_norm"] = snorm
        rec["implied_expectation"] = implied
        rec["pre_dir"] = "Bullish (draw)" if implied < 0 else "Bearish (build)"

        # base inventory-trend score (note: draw == negative chg == bullish)
        ie = implied
        if ie < -3000:
            base = 1.5
        elif ie < -500:
            base = 0.8
        elif ie <= 500:
            base = 0.0
        elif ie <= 3000:
            base = -0.8
        else:
            base = -1.5
        rec["base_score"] = base

        # ---- 1B curve structure signal (~print-10min .. print-1) ----
        wti = D["WTI"]
        s, e = pmin - 10, pmin - 1
        cday, fb = _eff_day(wti, day, s, e, "m1")  # fallback to last snapshot (06-03 target)
        rec["curve_asof"] = cday
        rec["curve_fallback"] = fb
        m1 = window_mean(wti, cday, s, e, "m1")
        m2 = window_mean(wti, cday, s, e, "m2")
        m3 = window_mean(wti, cday, s, e, "m3")
        m6 = window_mean(wti, cday, s, e, "m6")
        m12 = window_mean(wti, cday, s, e, "m12")
        rec["wti_m1"] = m1
        rec["wti_m1_m2"] = m1 - m2 if not np.isnan(m1) and not np.isnan(m2) else np.nan
        rec["wti_m1_m3"] = m1 - m3 if not np.isnan(m1) and not np.isnan(m3) else np.nan
        rec["wti_m1_m12"] = m1 - m12 if not np.isnan(m1) and not np.isnan(m12) else np.nan
        rec["regime"] = _curve_regime(m1, m2, m3, m6, m12)

        ho = D["HO"]
        hday, _ = _eff_day(ho, day, s, e, "m1")
        hm1 = window_mean(ho, hday, s, e, "m1")
        hm2 = window_mean(ho, hday, s, e, "m2")
        rec["ho_m1_m2"] = hm1 - hm2 if not np.isnan(hm1) and not np.isnan(hm2) else np.nan
        lgo = D["LGO"]
        lday, _ = _eff_day(lgo, day, s, e, "m1")
        lm1 = window_mean(lgo, lday, s, e, "m1")
        lm2 = window_mean(lgo, lday, s, e, "m2")
        rec["lgo_m1_m2"] = lm1 - lm2 if not np.isnan(lm1) and not np.isnan(lm2) else np.nan

        # HO crack level + 5-day trend (uses same as-of snapshot as WTI)
        crack = hm1 * 42 - m1 if not np.isnan(hm1) and not np.isnan(m1) else np.nan
        rec["ho_crack"] = crack
        # 5-day avg crack: mean of daily (pre-window) crack over prior 5 sessions
        crack_hist = []
        prior_days = sorted([d for d in wti["et_date"].unique() if d < cday])[-5:]
        for d in prior_days:
            a = window_mean(ho, d, s, e, "m1")
            b = window_mean(wti, d, s, e, "m1")
            if not np.isnan(a) and not np.isnan(b):
                crack_hist.append(a * 42 - b)
        crack_5d = np.mean(crack_hist) if crack_hist else np.nan
        rec["ho_crack_5d"] = crack_5d
        crack_up = (not np.isnan(crack) and not np.isnan(crack_5d) and crack > crack_5d)
        crack_dn = (not np.isnan(crack) and not np.isnan(crack_5d) and crack < crack_5d)

        # curve amplifiers
        amp_curve = 0.0
        if not np.isnan(rec["wti_m1_m2"]):
            if rec["wti_m1_m2"] > 0.5:
                amp_curve += 0.5
            elif rec["wti_m1_m2"] < -0.5:
                amp_curve -= 0.5
        if crack_up:
            amp_curve += 0.3
        elif crack_dn:
            amp_curve -= 0.3
        rec["amp_curve"] = amp_curve

        # ---- 1C macro (prior close) ----
        mday = macro[macro["Date"] < pd.Timestamp(day)]
        amp_macro = 0.0
        if len(mday):
            last = mday.iloc[-1]
            rec["dxy"] = last["DXY"]
            rec["dxy_dod"] = last["DXY_dod"]
            rec["us10y"] = last["US10Y_pct"]
            rec["gold_dod"] = last["Gold_dod"]
            if last["DXY_dod"] < -0.3:
                amp_macro += 0.3
            if last["DXY_dod"] > 0.5:
                amp_macro -= 0.5
            if last["US10Y_pct"] < 4.5 and last["Gold_dod"] < 0:
                amp_macro += 0.2
        else:
            rec["dxy"] = rec["dxy_dod"] = rec["us10y"] = rec["gold_dod"] = np.nan
        rec["amp_macro"] = amp_macro

        # ---- 1D composite ----
        score = base + amp_curve + amp_macro
        rec["pretrade_score"] = score
        if score > 1.0:
            lab = "Strong Bullish"
        elif score >= 0.3:
            lab = "Mild Bullish"
        elif score > -0.3:
            lab = "Neutral"
        elif score >= -1.0:
            lab = "Mild Bearish"
        else:
            lab = "Strong Bearish"
        rec["pretrade_label"] = lab
        rows.append(rec)

    pre = pd.DataFrame(rows)
    pre.to_csv(os.path.join(OUT, "tbl_pretrade_signal.csv"), index=False)
    show = pre[["release_date", "implied_expectation", "base_score", "amp_curve",
                "amp_macro", "pretrade_score", "pretrade_label", "regime"]]
    print(show.to_string(index=False,
          formatters={"implied_expectation": lambda v: fmt(v, 0)}))
    print()
    D["pre"] = pre
    return pre


# ============================================================================
#  SECTION 2B / 6 : PRICE REACTIONS + CURVE REACTIONS
# ============================================================================
def _daily_vol(df, col, day, lookback=30):
    """30-day rolling daily-return vol (%) of `col` using EOD-ish last price."""
    days = sorted([d for d in df["et_date"].unique() if d <= day])[-(lookback + 1):]
    closes = []
    for d in days:
        sub = df[(df["et_date"] == d) & (df["min_of_day"] <= 17 * 60)]
        if col in df.columns and len(sub):
            closes.append(sub[col].iloc[-1])
    if len(closes) < 5:
        return np.nan
    rets = pd.Series(closes).pct_change().dropna() * 100
    return rets.std()


def compute_price_reactions(D):
    print("=" * 64)
    print("  SECTION 2B : INTRADAY PRICE REACTIONS (per product)")
    print("=" * 64)
    rel = D["releases"]
    rows = []
    for _, r in rel.iterrows():
        day = r["release_date"]
        p = int(r["print_min"])
        rec = {"release_date": day, "print_min": p}
        # windows (relative to print) : pre [p-10,p-1], r10 [p,p+9], r30 [p,p+29]
        # EOD 16:30-17:00 (fixed) ; pre-position drift 10:00->10:20 & 10:20->10:30
        for prod in PRICE_PRODUCTS:
            df = D[prod]
            pre = window_mean(df, day, p - 10, p - 1, "m1")
            r10 = window_mean(df, day, p, p + 9, "m1")
            r30 = window_mean(df, day, p, p + 29, "m1")
            eod = window_mean(df, day, 16 * 60 + 30, 17 * 60, "m1")
            rec[f"{prod}_pre"] = pre
            rec[f"{prod}_r10_pct"] = (r10 - pre) / pre * 100 if pre and not np.isnan(pre) and not np.isnan(r10) else np.nan
            rec[f"{prod}_r30_pct"] = (r30 - pre) / pre * 100 if pre and not np.isnan(pre) and not np.isnan(r30) else np.nan
            rec[f"{prod}_eod_pct"] = (eod - pre) / pre * 100 if pre and not np.isnan(pre) and not np.isnan(eod) else np.nan
            # absolute price levels for P&L
            rec[f"{prod}_p_pre"] = pre
            rec[f"{prod}_p_r10"] = r10
            rec[f"{prod}_p_r30"] = r30
            rec[f"{prod}_p_eod"] = eod
            # pre-release drift (front-running): [p-30,p-20] -> [p-10,p-1]
            d_early = window_mean(df, day, p - 30, p - 20, "m1")
            d_late = window_mean(df, day, p - 10, p - 1, "m1")
            rec[f"{prod}_drift_pre_pct"] = (d_late - d_early) / d_early * 100 \
                if d_early and not np.isnan(d_early) and not np.isnan(d_late) else np.nan
            # immediate drift [p-10] -> [p] (10:20->10:30)
            d_imm0 = window_mean(df, day, p - 10, p - 1, "m1")
            d_imm1 = window_mean(df, day, p, p + 0, "m1")
            rec[f"{prod}_drift_2030_pct"] = (d_imm1 - d_imm0) / d_imm0 * 100 \
                if d_imm0 and not np.isnan(d_imm0) and not np.isnan(d_imm1) else np.nan
            # 30d vol for risk-adjusting
            rec[f"{prod}_vol30"] = _daily_vol(df, "m1", day)

        # ---- WTI spread reactions (pre vs r10 delta) ----
        wti = D["WTI"]
        for a, b in [("m1", "m2"), ("m1", "m3"), ("m1", "m6"), ("m1", "m12"),
                     ("m2", "m3"), ("m3", "m6"), ("m6", "m12")]:
            pa = window_mean(wti, day, p - 10, p - 1, a)
            pb = window_mean(wti, day, p - 10, p - 1, b)
            ra = window_mean(wti, day, p, p + 9, a)
            rb = window_mean(wti, day, p, p + 9, b)
            pre_sp = pa - pb
            post_sp = ra - rb
            rec[f"wti_{a}_{b}_pre"] = pre_sp
            rec[f"wti_{a}_{b}_post"] = post_sp
            rec[f"wti_{a}_{b}_delta"] = post_sp - pre_sp

        # ---- HO crack reaction (HO*42 - WTI) pre vs post ----
        ho = D["HO"]
        hpre = window_mean(ho, day, p - 10, p - 1, "m1")
        hpost = window_mean(ho, day, p, p + 9, "m1")
        wpre = window_mean(wti, day, p - 10, p - 1, "m1")
        wpost = window_mean(wti, day, p, p + 9, "m1")
        rec["crack_pre"] = hpre * 42 - wpre if not np.isnan(hpre) and not np.isnan(wpre) else np.nan
        rec["crack_post"] = hpost * 42 - wpost if not np.isnan(hpost) and not np.isnan(wpost) else np.nan
        rec["crack_delta"] = (rec["crack_post"] - rec["crack_pre"]) \
            if not np.isnan(rec["crack_pre"]) and not np.isnan(rec["crack_post"]) else np.nan
        # crack reaction pct (proxy instrument for gasoline / distillate signal)
        rec["crack_r10_pct"] = (rec["crack_delta"] / abs(rec["crack_pre"]) * 100) \
            if rec["crack_pre"] and not np.isnan(rec["crack_pre"]) and rec["crack_pre"] != 0 \
            and not np.isnan(rec["crack_delta"]) else np.nan

        # ---- WTI-Brent spread ----
        lco = D["Brent"]
        bpre = window_mean(lco, day, p - 10, p - 1, "m1")
        bpost = window_mean(lco, day, p, p + 9, "m1")
        rec["wti_brent_pre"] = wpre - bpre if not np.isnan(wpre) and not np.isnan(bpre) else np.nan
        rec["wti_brent_post"] = wpost - bpost if not np.isnan(wpost) and not np.isnan(bpost) else np.nan
        rec["wti_brent_delta"] = (rec["wti_brent_post"] - rec["wti_brent_pre"]) \
            if not np.isnan(rec["wti_brent_pre"]) and not np.isnan(rec["wti_brent_post"]) else np.nan

        rows.append(rec)

    rx = pd.DataFrame(rows)
    rx.to_csv(os.path.join(OUT, "tbl_price_reactions.csv"), index=False)
    show = rx[["release_date", "WTI_r10_pct", "WTI_r30_pct", "WTI_eod_pct",
               "Brent_r10_pct", "HO_r10_pct", "LGO_r10_pct", "crack_r10_pct"]]
    n_px = rx["WTI_r10_pct"].notna().sum()
    print(f"(intraday data covers {n_px}/13 releases; later releases lack 1-min price data)\n")
    print(show.to_string(index=False, formatters={
        c: (lambda v: fmt(v, 3)) for c in show.columns if c != "release_date"}))
    print()
    D["rx"] = rx
    return rx


# ============================================================================
#  SECTION 3 : TRADER ANALYTICS
# ============================================================================
def run_trader_analytics(D):
    print("=" * 64)
    print("  SECTION 3 : TRADER ANALYTICS")
    print("=" * 64)
    inv = D["inv"].set_index("release_date")
    rx = D["rx"].set_index("release_date")
    pre = D["pre"].set_index("release_date")
    results = {}

    # signal direction from inventory: draw (neg chg) -> bullish (+1)
    def inv_sig(col, thresh=500):
        s = inv[col]
        out = s.apply(lambda v: 0 if (np.isnan(v) or abs(v) < thresh) else (1 if v < 0 else -1))
        return out

    # ---- 3A hit rate ----
    print("\n--- 3A HIT RATE ANALYSIS ---")
    hit_rows = []
    pairs = [
        ("Crude->WTI", "crude_chg", "WTI_r10_pct", "WTI_eod_pct"),
        ("Crude->Brent", "crude_chg", "Brent_r10_pct", "Brent_eod_pct"),
        ("Distillate->HO", "distillate_chg", "HO_r10_pct", "HO_eod_pct"),
        ("Distillate->LGO", "distillate_chg", "LGO_r10_pct", "LGO_eod_pct"),
        ("Gasoline->HOcrack", "gasoline_chg", "crack_r10_pct", "crack_r10_pct"),
    ]
    for name, scol, r10col, eodcol in pairs:
        sd = inv_sig(scol)
        d10, deod, n10, neod = [], [], 0, 0
        for dt in rx.index:
            if dt not in sd.index:
                continue
            s = sd.loc[dt]
            r10 = rx.loc[dt, r10col]
            eod = rx.loc[dt, eodcol]
            if s != 0 and not np.isnan(r10):
                d10.append(int(s == sign(r10))); n10 += 1
            if s != 0 and not np.isnan(eod):
                deod.append(int(s == sign(eod))); neod += 1
        hr10 = np.mean(d10) if d10 else np.nan
        hreod = np.mean(deod) if deod else np.nan
        hit_rows.append({"pair": name, "n_10min": n10, "hit_rate_10min": hr10,
                         "n_eod": neod, "hit_rate_eod": hreod})
        a = name.split("->")
        print(f"  {a[0]:10s} signal predicted {a[1]:9s} 10-min direction "
              f"{sum(d10)}/{n10} times (hit rate: {fmt(hr10*100,0) if not np.isnan(hr10) else 'n/a'}%)"
              f" | EOD {sum(deod)}/{neod} ({fmt(hreod*100,0) if not np.isnan(hreod) else 'n/a'}%)")
    pd.DataFrame(hit_rows).to_csv(os.path.join(OUT, "tbl_hit_rate.csv"), index=False)
    results["hit"] = pd.DataFrame(hit_rows)

    # ---- 3B fade vs follow-through (WTI) ----
    print("\n--- 3B FADE vs FOLLOW-THROUGH (WTI) ---")
    ft30, fteod, drift = [], [], []
    up_hold = up_fade = dn_hold = dn_fade = 0
    up_drifts, dn_drifts = [], []
    for dt in rx.index:
        r10, r30, eod = rx.loc[dt, "WTI_r10_pct"], rx.loc[dt, "WTI_r30_pct"], rx.loc[dt, "WTI_eod_pct"]
        if not np.isnan(r10) and not np.isnan(r30):
            ft30.append(int(sign(r10) == sign(r30)))
        if not np.isnan(r10) and not np.isnan(eod):
            fteod.append(int(sign(r10) == sign(eod)))
            drift.append(eod - r10)
            if r10 > 0:
                (up_hold, up_fade) = (up_hold + 1, up_fade) if sign(eod) == 1 else (up_hold, up_fade + 1)
                up_drifts.append(eod - r10)
            elif r10 < 0:
                (dn_hold, dn_fade) = (dn_hold + 1, dn_fade) if sign(eod) == -1 else (dn_hold, dn_fade + 1)
                dn_drifts.append(eod - r10)
    n = len(fteod)
    print(f"  10-min -> 30-min follow-through:  {sum(ft30)}/{len(ft30)} "
          f"({fmt(np.mean(ft30)*100,0) if ft30 else 'n/a'}%)")
    print(f"  10-min -> EOD follow-through:     {sum(fteod)}/{n} "
          f"({fmt(np.mean(fteod)*100,0) if fteod else 'n/a'}%)")
    print(f"\n  When WTI rallied in first 10-min ({up_hold+up_fade} times):")
    print(f"    Held through EOD: {up_hold}  |  Faded by EOD: {up_fade}")
    print(f"    Avg additional 10min->EOD drift: {fmt(np.mean(up_drifts),3) if up_drifts else 'n/a'}%")
    print(f"  When WTI sold off in first 10-min ({dn_hold+dn_fade} times):")
    print(f"    Held through EOD: {dn_hold}  |  Faded by EOD: {dn_fade}")
    print(f"    Avg additional 10min->EOD drift: {fmt(np.mean(dn_drifts),3) if dn_drifts else 'n/a'}%")
    ft_rate = np.mean(fteod) if fteod else np.nan
    implication = ("HOLD to EOD" if not np.isnan(ft_rate) and ft_rate >= 0.6 else
                   "EXIT/FADE at 10-min" if not np.isnan(ft_rate) and ft_rate <= 0.4 else
                   "Situational - exit at 10-30min")
    print(f"\n  TRADER IMPLICATION: {implication}")
    results["fade"] = {"ft30": ft30, "fteod": fteod, "up_hold": up_hold, "up_fade": up_fade,
                       "dn_hold": dn_hold, "dn_fade": dn_fade, "implication": implication,
                       "avg_drift": np.nanmean(drift) if drift else np.nan}

    # ---- 3C entry timing ----
    print("\n--- 3C ENTRY TIMING (pre-position 10:20 vs print 10:30) ---")
    bull_drift, bear_drift, correct = [], [], 0
    nd = 0
    pnl_adv = []
    for dt in rx.index:
        d = rx.loc[dt, "WTI_drift_2030_pct"]
        r10 = rx.loc[dt, "WTI_r10_pct"]
        if np.isnan(d) or np.isnan(r10):
            continue
        nd += 1
        if r10 > 0:
            bull_drift.append(d)
        elif r10 < 0:
            bear_drift.append(d)
        if sign(d) == sign(r10):
            correct += 1
        # P&L advantage of pre-positioning: capture the drift in the correct dir
        pre_p = rx.loc[dt, "WTI_p_pre"]
        if not np.isnan(pre_p):
            pnl_adv.append(d / 100 * pre_p * sign(r10))  # $ per bbl gained by being early
    print(f"  Avg drift on bullish 10-min releases: {fmt(np.mean(bull_drift),3) if bull_drift else 'n/a'}%")
    print(f"  Avg drift on bearish 10-min releases: {fmt(np.mean(bear_drift),3) if bear_drift else 'n/a'}%")
    print(f"  Drift in correct direction: {correct}/{nd}")
    print(f"  Avg pre-position $ advantage/contract (1000 bbl): "
          f"${fmt(np.nanmean(pnl_adv)*1000,2) if pnl_adv else 'n/a'}")
    timing = ("Pre-position at 10:20" if (bull_drift or bear_drift) and nd and correct/nd > 0.55
              else "Wait for the print at 10:30")
    print(f"  TRADER IMPLICATION: {timing}")
    results["timing"] = {"correct": correct, "n": nd, "rec": timing}

    # ---- 3D P&L simulation: raw inventory direction strategy ----
    print("\n--- 3D P&L SIMULATION (raw inventory-direction strategy) ---")
    sim_rows = []
    strat = [("WTI", "crude_chg"), ("Brent", "crude_chg"),
             ("HO", "distillate_chg"), ("LGO", "distillate_chg")]
    for prod, scol in strat:
        sd = inv_sig(scol)
        for hold, pcol, retcol in [("10min", "WTI_p_r10", f"{prod}_r10_pct"),
                                    ("30min", "WTI_p_r30", f"{prod}_r30_pct"),
                                    ("EOD", "WTI_p_eod", f"{prod}_eod_pct")]:
            wins, losses, pnls = [], [], []
            for dt in rx.index:
                if dt not in sd.index:
                    continue
                s = sd.loc[dt]
                ret = rx.loc[dt, retcol]
                if s == 0 or np.isnan(ret):
                    continue
                pnl = s * ret  # long if draw, short if build; %-return per bbl proxy
                pnls.append(pnl)
                (wins if pnl > 0 else losses).append(pnl)
            n_act = len(pnls)
            sim_rows.append({
                "product": prod, "signal": scol, "hold": hold, "active": n_act,
                "hit_rate": (len(wins) / n_act if n_act else np.nan),
                "avg_win": (np.mean(wins) if wins else np.nan),
                "avg_loss": (np.mean(losses) if losses else np.nan),
                "total_pnl_pct": (np.sum(pnls) if pnls else np.nan)})
        # print best holding period for product
        sub = [r for r in sim_rows if r["product"] == prod]
        best = max(sub, key=lambda r: (r["total_pnl_pct"] if not np.isnan(r["total_pnl_pct"]) else -1e9))
        print(f"  {prod:5s} ({scol}): active={best['active']:2d}  "
              f"10/30/EOD totalP&L%="
              f"{'/'.join(fmt(r['total_pnl_pct'],2) for r in sub)}  "
              f"-> best hold: {best['hold']}")
    sim = pd.DataFrame(sim_rows)
    sim.to_csv(os.path.join(OUT, "tbl_pnl_simulation.csv"), index=False)
    results["sim"] = sim

    # composite pre-trade signal strategy (score>0.5 long / <-0.5 short)
    print("\n  Composite pre-trade signal strategy (WTI, |score|>0.5):")
    cp_pnl = []
    cp_hit = []
    for dt in rx.index:
        if dt not in pre.index:
            continue
        sc = pre.loc[dt, "pretrade_score"]
        ret = rx.loc[dt, "WTI_r10_pct"]
        if np.isnan(sc) or np.isnan(ret) or abs(sc) <= 0.5:
            continue
        s = 1 if sc > 0 else -1
        cp_pnl.append(s * ret)
        cp_hit.append(int(s == sign(ret)))
    print(f"    active={len(cp_pnl)}  hit={sum(cp_hit)}/{len(cp_hit)} "
          f"({fmt(np.mean(cp_hit)*100,0) if cp_hit else 'n/a'}%)  "
          f"total 10-min P&L%={fmt(np.sum(cp_pnl),2) if cp_pnl else 'n/a'}")
    results["composite_strat"] = {"pnl": cp_pnl, "hit": cp_hit}

    # ---- 3E best instrument per release (risk-adjusted) ----
    print("\n--- 3E BEST PRODUCT/SPREAD PER RELEASE (risk-adjusted 10-min) ---")
    instruments = ["WTI", "Brent", "HO", "LGO"]
    winners_raw, winners_radj = [], []
    be_rows = []
    for dt in rx.index:
        scores_raw, scores_radj = {}, {}
        for prod in instruments:
            r = rx.loc[dt, f"{prod}_r10_pct"]
            v = rx.loc[dt, f"{prod}_vol30"]
            if not np.isnan(r):
                scores_raw[prod] = abs(r)
                if v and not np.isnan(v) and v > 0:
                    scores_radj[prod] = abs(r) / v
        # WTI M1-M2 spread (delta) & HO crack as instruments (raw magnitude only)
        sp = rx.loc[dt, "wti_m1_m2_delta"]
        if not np.isnan(sp):
            scores_raw["WTI_M1M2"] = abs(sp)
        ck = rx.loc[dt, "crack_r10_pct"]
        if not np.isnan(ck):
            scores_raw["HO_crack"] = abs(ck)
        if not scores_raw:
            continue
        wr = max(scores_raw, key=scores_raw.get)
        winners_raw.append(wr)
        rowd = {"release_date": dt, "winner_raw": wr}
        if scores_radj:
            wa = max(scores_radj, key=scores_radj.get)
            winners_radj.append(wa)
            rowd["winner_risk_adj"] = wa
        be_rows.append(rowd)
    pd.DataFrame(be_rows).to_csv(os.path.join(OUT, "tbl_best_instrument.csv"), index=False)
    if winners_radj:
        from collections import Counter
        c = Counter(winners_radj)
        top, cnt = c.most_common(1)[0]
        print(f"  In {cnt}/{len(winners_radj)} releases, {top} gave the highest "
              f"risk-adjusted 10-min return.")
        print(f"  Full risk-adj winner tally: {dict(c)}")
    results["best"] = pd.DataFrame(be_rows)

    print("\n  [!] SAMPLE SIZE: only ~11 releases with price data - results are")
    print("      directionally indicative, NOT statistically significant.\n")
    D["analytics"] = results
    return results


# ============================================================================
#  SECTION 4 : REGIME CONDITIONING
# ============================================================================
def regime_conditioning(D):
    print("=" * 64)
    print("  SECTION 4 : WHEN DID INVENTORIES MATTER? (regime conditioning)")
    print("=" * 64)
    rx = D["rx"].set_index("release_date")
    pre = D["pre"].set_index("release_date")
    inv = D["inv"].set_index("release_date")

    # 4A significance filter
    print("\n--- 4A SIGNIFICANCE FILTER (|WTI 10-min|) ---")
    cat = {}
    for dt in rx.index:
        r = rx.loc[dt, "WTI_r10_pct"]
        if np.isnan(r):
            cat[dt] = "NoData"
        elif abs(r) > 0.5:
            cat[dt] = "Mattered"
        elif abs(r) <= 0.2:
            cat[dt] = "Muted"
        else:
            cat[dt] = "Mixed"
    from collections import Counter
    print(f"  {dict(Counter(cat.values()))}")
    for grp in ["Mattered", "Muted", "Mixed"]:
        dts = [d for d, c in cat.items() if c == grp]
        if not dts:
            continue
        surp = np.nanmean([abs(inv.loc[d, "crude_surprise"]) for d in dts if d in inv.index])
        dxy = np.nanmean([pre.loc[d, "dxy_dod"] for d in dts if d in pre.index])
        regs = Counter([pre.loc[d, "regime"] for d in dts if d in pre.index])
        print(f"  {grp:9s} (n={len(dts)}): avg|crude surprise|={fmt(surp,0)} MBBL  "
              f"avg DXY DoD={fmt(dxy,2)}%  regimes={dict(regs)}")

    # 4B regime-conditional hit rate
    print("\n--- 4B REGIME-CONDITIONAL HIT RATE (crude->WTI) ---")
    rows = []
    for reg in ["Full Backwardation", "Front Backwardation", "Full Contango", "Mixed"]:
        dts = [d for d in rx.index if d in pre.index and pre.loc[d, "regime"] == reg]
        hits, rets, pnls = [], [], []
        for d in dts:
            cc = inv.loc[d, "crude_chg"] if d in inv.index else np.nan
            r10 = rx.loc[d, "WTI_r10_pct"]
            if np.isnan(cc) or np.isnan(r10) or abs(cc) < 500:
                continue
            s = 1 if cc < 0 else -1
            hits.append(int(s == sign(r10)))
            rets.append(r10)
            pnls.append(s * r10)
        rows.append({"regime": reg, "n": len(hits),
                     "hit_rate": np.mean(hits) if hits else np.nan,
                     "avg_reaction_pct": np.mean(rets) if rets else np.nan,
                     "avg_pnl_pct": np.mean(pnls) if pnls else np.nan})
    rdf = pd.DataFrame(rows)
    rdf.to_csv(os.path.join(OUT, "tbl_regime_hitrate.csv"), index=False)
    print(rdf.to_string(index=False, formatters={
        "hit_rate": lambda v: fmt(v, 2), "avg_reaction_pct": lambda v: fmt(v, 3),
        "avg_pnl_pct": lambda v: fmt(v, 3)}))
    valid = rdf.dropna(subset=["hit_rate"])
    if len(valid):
        best = valid.loc[valid["hit_rate"].idxmax()]
        print(f"\n  KEY: inventory signal most reliable in '{best['regime']}' "
              f"(hit rate {fmt(best['hit_rate'],2)}, n={int(best['n'])}).")

    # 4C seasonal positioning context
    print("\n--- 4C SEASONAL POSITIONING (2026 vs 5yr norm) ---")
    sdev = inv[["crude_surprise", "distillate_surprise", "gasoline_surprise"]].copy()
    print(sdev.assign(release=inv.index).to_string(index=False, formatters={
        c: (lambda v: fmt(v, 0)) for c in ["crude_surprise", "distillate_surprise", "gasoline_surprise"]}))
    D["regime_cat"] = cat
    D["regime_hit"] = rdf
    print()
    return rdf


# ============================================================================
#  SECTION 5 : AMPLIFIERS & COMPOSITE (with actual print)
# ============================================================================
def compute_amplifiers(D):
    print("=" * 64)
    print("  SECTION 5 : COMPOSITE SIGNAL (incl. actual inventory print)")
    print("=" * 64)
    rx = D["rx"].set_index("release_date")

    # linear feature model: score = sum_k w_k * feature_k  (weights: tuned or prior)
    feat = build_feature_matrix(D)
    weights, wsrc = load_active_weights()
    print(f"  Active composite weights: {wsrc}")
    print("  " + "  ".join(f"{k}={weights[k]:.2f}" for k in COMPOSITE_WEIGHTS_PRIOR))
    keys = list(COMPOSITE_WEIGHTS_PRIOR.keys())

    comp = feat.copy()
    for k in keys:                      # per-feature contribution (feature * weight)
        comp[f"contrib_{k}"] = feat[k] * weights[k]
    comp["composite_score"] = score_features(feat, weights)
    D["feat"] = feat
    D["composite_weights"] = weights
    comp.to_csv(os.path.join(OUT, "tbl_composite_score.csv"))
    print(comp[["composite_score"]].assign(
        wti_r10=[rx.loc[d, "WTI_r10_pct"] if d in rx.index else np.nan for d in comp.index]).to_string(
        formatters={"composite_score": lambda v: fmt(v, 2), "wti_r10": lambda v: fmt(v, 3)}))

    # Pearson r between composite score and 10-min WTI reaction
    merged = pd.DataFrame({
        "score": comp["composite_score"],
        "react": [rx.loc[d, "WTI_r10_pct"] if d in rx.index else np.nan for d in comp.index]
    }).dropna()
    if len(merged) >= 3:
        r, p = stats.pearsonr(merged["score"], merged["react"])
        print(f"\n  Composite score explains {r**2*100:.1f}% of variance in 10-min WTI "
              f"reactions (r={r:.2f}, p={p:.2f}, n={len(merged)}).")
        D["composite_r"] = (r, p, len(merged))
    else:
        D["composite_r"] = (np.nan, np.nan, len(merged))
    print()
    D["comp"] = comp
    return comp


# ============================================================================
#  SECTION 6 : FULL CURVE REACTION ANALYSIS
# ============================================================================
def curve_reaction_analysis(D):
    print("=" * 64)
    print("  SECTION 6 : WTI TERM-STRUCTURE REACTION")
    print("=" * 64)
    rx = D["rx"].set_index("release_date")
    spreads = ["m1_m2", "m1_m3", "m1_m6", "m1_m12", "m2_m3", "m3_m6", "m6_m12"]
    cols = [f"wti_{s}_delta" for s in spreads]
    heat = rx[cols].copy()
    heat.columns = spreads
    heat = heat.dropna(how="all")
    heat.to_csv(os.path.join(OUT, "tbl_curve_reaction_heatmap.csv"))
    print("  Spread deltas (post-10min minus pre), bp of $:")
    print(heat.to_string(formatters={c: (lambda v: fmt(v, 3)) for c in heat.columns}))

    # front vs back: |m1_m2 delta| vs |m6_m12 delta|
    fb = heat[["m1_m2", "m6_m12"]].abs().mean()
    if not fb.isna().all():
        print(f"\n  Avg |front (M1-M2)| move = {fmt(fb['m1_m2'],3)}  vs  "
              f"avg |back (M6-M12)| move = {fmt(fb['m6_m12'],3)}")
        print("  -> " + ("Front end reacts more (as expected: inventory is a near-term shock)."
                         if fb["m1_m2"] > fb["m6_m12"] else
                         "Back end moved as much/more (unusual - check macro overlay)."))
    D["heat"] = heat
    print()
    return heat


# ============================================================================
#  SECTION 7 : TRADING MEMO (2026-06-03)
# ============================================================================
def generate_trading_memo(D):
    inv = D["inv"].set_index("release_date")
    pre = D["pre"].set_index("release_date")
    comp = D["comp"]
    rx = D["rx"].set_index("release_date")
    regime_hit = D["regime_hit"]
    target = D["releases"].iloc[-1]["release_date"]  # 2026-06-03

    iv = inv.loc[target]
    cs = comp.loc[target, "composite_score"] if target in comp.index else np.nan
    # pre-trade signal for target (curve/macro use last available data)
    pr = pre.loc[target] if target in pre.index else None

    L = []
    A = L.append
    A("=" * 64)
    A("  EIA WEEKLY PETROLEUM STATUS REPORT - TRADING MEMO")
    A(f"  Release: Wednesday {target}, 10:30 AM ET")
    A("  Analyst: Systematic EIA Framework (Phase 1)")
    A("=" * 64)
    A("")
    A(f"INVENTORY PRINT (Week Ending {iv['week_ending']}):")
    A("+" + "-" * 78 + "+")
    A(f"| {'Product':20s}| {'Stocks':>10s} | {'WoW':>8s} | {'vs 5yr Norm':>12s} | {'Signal':>8s} |")
    A("|" + "-" * 79 + "|")

    def sig(chg, bull_on_draw=True):
        if np.isnan(chg):
            return "n/a"
        if bull_on_draw:
            return "BULL" if chg < 0 else "BEAR"
        return "BULL" if chg > 0 else "BEAR"

    def line(name, lvl, chg, surp, s):
        A(f"| {name:20s}| {fmt(lvl,0):>10s} | {fmt(chg,0):>8s} | "
          f"{(fmt(surp,0) if surp is not None and not np.isnan(surp) else '-'):>12s} | {s:>8s} |")

    line("Crude Oil (US)", iv["crude_lvl"], iv["crude_chg"], iv["crude_surprise"], sig(iv["crude_chg"]))
    amp = "AMPLIFY" if iv.get("cushing_driven", False) else "context"
    line("Cushing OK", iv["cushing_lvl"], iv["cushing_chg"], np.nan, amp)
    line("Distillate", iv["distillate_lvl"], iv["distillate_chg"], iv["distillate_surprise"], sig(iv["distillate_chg"]))
    line("Gasoline", iv["gasoline_lvl"], iv["gasoline_chg"], iv["gasoline_surprise"], sig(iv["gasoline_chg"]))
    line("Jet Fuel", np.nan, iv["jet_chg"], iv["jet_surprise"], sig(iv["jet_chg"]))
    line("Propane", np.nan, iv["propane_chg"], iv["propane_surprise"], sig(iv["propane_chg"]))
    line("Residual FO", np.nan, iv["residual_chg"], iv["residual_surprise"], sig(iv["residual_chg"]))
    line("Total Petroleum", np.nan, iv["total_petro_chg"], np.nan, sig(iv["total_petro_chg"]))
    line("Refinery Inputs", iv["refinery_input_lvl"], iv["refinery_input_chg"], np.nan,
         "demand+" if iv["refinery_input_chg"] > 0 else "demand-")
    A(f"| {'Days of Supply':20s}| {fmt(iv['days_of_supply'],1):>10s} | {'':>8s} | {'':>12s} | "
      f"{'tight' if not np.isnan(iv['days_of_supply']) else '-':>8s} |")
    A("+" + "-" * 78 + "+")
    A(f"RBOB Gasoline: {RBOB_NOTE}")
    A("")

    # curve context (last available pre-release snapshot for target)
    asof = pr["curve_asof"] if (pr is not None and "curve_asof" in pr.index) else "n/a"
    A(f"CURVE CONTEXT (WTI, last snapshot {asof} ~10:20 ET):")
    if pr is not None:
        A(f"  M1: {fmt(pr['wti_m1'],2)}  |  M1-M2: {fmt(pr['wti_m1_m2'],2)}  |  M1-M3: {fmt(pr['wti_m1_m3'],2)}")
        A(f"  M1-M12: {fmt(pr['wti_m1_m12'],2)}  |  Regime: {pr['regime']}")
        A(f"  HO crack: {fmt(pr['ho_crack'],2)} $/bbl")
    A("")
    if pr is not None:
        A("MACRO CONTEXT (last available close):")
        dxy_sig = ("TAILWIND" if pr["dxy_dod"] < -0.3 else
                   "HEADWIND" if pr["dxy_dod"] > 0.5 else "NEUTRAL")
        A(f"  DXY: {fmt(pr['dxy'],2)}  DoD: {fmt(pr['dxy_dod'],2)}%  |  "
          f"US10Y: {fmt(pr['us10y'],2)}%  |  Gold DoD: {fmt(pr['gold_dod'],2)}%")
        A(f"  DXY signal: {dxy_sig}")
        A("")

    # pre-trade signal
    A("PRE-TRADE SIGNAL (what we knew before the print):")
    if pr is not None:
        A(f"  Seasonal norm this week: {fmt(pr['crude_seasonal_norm'],0)} MBBL")
        A(f"  4-week crude trend: {fmt(pr['crude_recent_trend_4w'],0)} MBBL/wk")
        A(f"  Implied expectation: {fmt(pr['implied_expectation'],0)} MBBL "
          f"({'draw->bullish' if pr['implied_expectation']<0 else 'build->bearish'})")
        A(f"  Pre-trade composite score: {fmt(pr['pretrade_score'],2)} -> {pr['pretrade_label']}")
    A("")
    A("=" * 64)
    A("  TRADING RECOMMENDATION")
    A("=" * 64)

    # directional view from composite (actual print) score
    if np.isnan(cs):
        view, conf = "NEUTRAL", "LOW"
    elif cs > 1.0:
        view, conf = "BULLISH", "HIGH"
    elif cs > 0.3:
        view, conf = "BULLISH", "MEDIUM"
    elif cs > -0.3:
        view, conf = "NEUTRAL", "LOW"
    elif cs > -1.0:
        view, conf = "BEARISH", "MEDIUM"
    else:
        view, conf = "BEARISH", "HIGH"
    A(f"\nDIRECTIONAL VIEW:  {view}")
    A(f"CONFIDENCE:        {conf}")
    A("")
    A("WHY THIS VIEW:")
    cdir = "drew" if iv["crude_chg"] < 0 else "built"
    A(f"  1. Crude {cdir} {fmt(abs(iv['crude_chg']),0)} MBBL vs seasonal norm "
      f"{fmt(iv['crude_seasonal_norm'],0)} MBBL "
      f"-> {fmt(iv['crude_surprise'],0)} MBBL surprise vs seasonal.")
    if pr is not None:
        A(f"  2. WTI curve regime {pr['regime']} (M1-M2 {fmt(pr['wti_m1_m2'],2)}) "
          f"{'amplifies' if (not np.isnan(pr['wti_m1_m2']) and pr['wti_m1_m2']>0) else 'tempers'} bullish prints.")
        A(f"  3. Macro: DXY DoD {fmt(pr['dxy_dod'],2)}%, US10Y {fmt(pr['us10y'],2)}% "
          f"-> {'USD tailwind' if pr['dxy_dod']<-0.3 else 'USD headwind' if pr['dxy_dod']>0.5 else 'neutral macro'}.")
    cushing_amp = iv.get("cushing_driven", False)
    A("")
    A("WHAT TO TRADE (ranked by risk-adjusted priority):")
    primary = "WTI M1 outright" if view != "NEUTRAL" else "Stand aside / small size"
    A(f"  1. {primary}: crude {cdir}; "
      f"Cushing share {fmt(iv['cushing_share_pct'],0)}% "
      f"({'Cushing-driven, tightest at WTI delivery point' if cushing_amp else 'broad national move'}).")
    A(f"  2. WTI M1-M2 calendar spread: {'front backwardation in place; draw should steepen front' if pr is not None and not np.isnan(pr['wti_m1_m2']) and pr['wti_m1_m2']>0 else 'lower delta risk than outright'}.")
    A(f"  3. HO crack: distillate {('drew' if iv['distillate_chg']<0 else 'built')} "
      f"{fmt(abs(iv['distillate_chg']),0)} MBBL - trade crack if HO reacts more than WTI.")
    A("")

    # historical context: same-regime comparable releases
    A("HISTORICAL CONTEXT FOR THIS SETUP:")
    tgt_reg = pr["regime"] if pr is not None else "Unknown"
    sim_dts = [d for d in rx.index if d in pre.index and pre.loc[d, "regime"] == tgt_reg
               and not np.isnan(rx.loc[d, "WTI_r10_pct"])]
    if sim_dts:
        reacts = [rx.loc[d, "WTI_r10_pct"] for d in sim_dts]
        eods = [(rx.loc[d, "WTI_eod_pct"], rx.loc[d, "WTI_r10_pct"]) for d in sim_dts
                if not np.isnan(rx.loc[d, "WTI_eod_pct"])]
        ft = sum(1 for e, r in eods if sign(e) == sign(r))
        A(f"  Same regime ({tgt_reg}) sample: {', '.join(str(d) for d in sim_dts[:4])}")
        A(f"  Hist WTI 10-min reaction: avg {fmt(np.mean(reacts),3)}%  "
          f"range [{fmt(min(reacts),3)}%, {fmt(max(reacts),3)}%]")
        A(f"  Follow-through to EOD: {ft}/{len(eods)} "
          f"({fmt(ft/len(eods)*100,0) if eods else 'n/a'}%)")
    else:
        A(f"  No same-regime ({tgt_reg}) releases with price data in sample.")
    A("")
    A("RISK MANAGEMENT:")
    px = pr["wti_m1"] if (pr is not None and not np.isnan(pr["wti_m1"])) else np.nan
    typ_move = np.nanmean([abs(rx.loc[d, "WTI_r10_pct"]) for d in rx.index]) if len(rx) else np.nan
    adverse = (typ_move / 100 * px) if not np.isnan(typ_move) and not np.isnan(px) else np.nan
    A(f"  Typical 10-min |move| in sample: {fmt(typ_move,3)}%  "
      f"(~${fmt(adverse,2)}/bbl at M1 {fmt(px,2)}).")
    A("  If move does NOT materialise within 10 min: reassess - another factor likely dominating.")
    fade = D["analytics"]["fade"]["implication"]
    A(f"  Fade/hold guide (from 3B): {fade}.")
    A("")
    A(f"COMPOSITE SIGNAL SCORE:  {fmt(cs,2)} / ~3.5 max  ->  {view} ({conf})")
    A("")
    A("FRAMEWORK EXPLANATION:")
    r = D.get("composite_r", (np.nan,))[0]
    A("  Data: 9 EIA weekly inventory series (2020-2026, 337 wks), WTI 1-min M1 +")
    A("  full term structure c1-c14, Heating Oil / ICE Gasoil / Brent 1-min, and")
    A("  daily macro (DXY, US10Y, Gold). A pre-trade signal is built from seasonal")
    A("  norms + 4-week trend + curve structure + macro BEFORE the print, then the")
    A("  actual inventory surprise vs seasonal upgrades/downgrades it. Amplifiers:")
    A("  curve regime, Cushing share, macro, cross-product confirmation.")
    A(f"  Composite score vs 10-min WTI reaction: r={fmt(r,2)} (n={D.get('composite_r',(0,0,0))[2]}).")
    A("  Calibration uses hit-rate & P&L sims across the price-covered releases.")
    A("  Flip conditions: a crude print on the opposite side of seasonal norm, a")
    A("  DXY spike >0.5% DoD, or a regime shift to Full Contango would flip/mute.")
    A("")
    A("  --- PHASE 2 (out of scope) ---")
    A("  * Half-life of post-EIA spread mean reversion (M1-M2, M1-M3)")
    A("  * Optimal structure: outright vs spread vs fly vs dfly (risk-adjusted)")
    A("  * RBOB 1-min data acquisition for full gasoline analysis")
    A("=" * 64)

    memo = "\n".join(L)
    print(memo)
    with open(os.path.join(OUT, "trading_memo_2026-06-03.txt"), "w", encoding="utf-8") as f:
        f.write(memo)
    return memo


# ============================================================================
#  PLOTS
# ============================================================================
def save_all_plots(D):
    print("=" * 64)
    print("  SAVING PLOTS")
    print("=" * 64)
    eia = D["eia"]
    inv = D["inv"]
    rel = D["releases"]
    rx = D["rx"]
    pre = D["pre"]
    comp = D["comp"]
    macro = D["macro"]
    rdates = pd.to_datetime([d for d in rel["release_date"]])

    def _save(fig, name):
        fig.tight_layout()
        fig.savefig(os.path.join(OUT, name), dpi=110, bbox_inches="tight")
        plt.close(fig)
        print(f"  saved {name}")

    prods9 = [("crude", "Crude"), ("cushing", "Cushing"), ("distillate", "Distillate"),
              ("gasoline", "Gasoline"), ("jet", "Jet"), ("propane", "Propane"),
              ("residual", "Residual FO"), ("total_petro", "Total Petro"),
              ("refinery_in", "Refinery Inputs")]

    # 01 inventory levels 6yr with 5yr seasonal band
    try:
        fig, axes = plt.subplots(3, 3, figsize=(16, 11))
        for ax, (k, lbl) in zip(axes.ravel(), prods9):
            df = eia[k]
            ax.plot(df["period"], df["value"], lw=0.8, color="navy")
            snt = seasonal_norm_table(df)  # weekly mean of WoW - not level; show level band via 5yr pct
            ax.set_title(lbl, fontsize=10)
            ax.grid(alpha=0.3)
        fig.suptitle("01 - 6yr Inventory Levels (all 9 series)", fontsize=13)
        _save(fig, "01_inventory_levels_6yr.png")
    except Exception as e:
        print("  [skip 01]", e)

    # 02 seasonal curves (52-wk avg WoW +-1std)
    try:
        fig, axes = plt.subplots(2, 3, figsize=(16, 9))
        for ax, (k, lbl) in zip(axes.ravel(), prods9[:6]):
            t = seasonal_norm_table(eia[k])
            ax.plot(t.index, t["mean"], color="darkgreen")
            ax.fill_between(t.index, t["mean"] - t["std"], t["mean"] + t["std"], alpha=0.2, color="green")
            ax.axhline(0, color="k", lw=0.6)
            ax.set_title(f"{lbl} seasonal WoW", fontsize=10); ax.grid(alpha=0.3)
        fig.suptitle("02 - Seasonal WoW change (5yr avg +-1std)", fontsize=13)
        _save(fig, "02_seasonal_curves.png")
    except Exception as e:
        print("  [skip 02]", e)

    # 03 WoW bar chart 2026
    try:
        bars = [("crude_chg", "Crude"), ("distillate_chg", "Distillate"),
                ("gasoline_chg", "Gasoline"), ("jet_chg", "Jet"),
                ("propane_chg", "Propane"), ("residual_chg", "Residual")]
        fig, axes = plt.subplots(3, 2, figsize=(15, 11))
        for ax, (c, lbl) in zip(axes.ravel(), bars):
            vals = inv[c].values
            cols = ["green" if v < 0 else "red" for v in vals]  # draw green (bullish)
            ax.bar(range(len(vals)), vals, color=cols)
            ax.set_xticks(range(len(inv)))
            ax.set_xticklabels([str(d)[5:] for d in inv["release_date"]], rotation=60, fontsize=7)
            ax.axhline(0, color="k", lw=0.6); ax.set_title(lbl, fontsize=10); ax.grid(alpha=0.3)
        fig.suptitle("03 - WoW changes Mar-Jun 2026 (green=draw/bullish, red=build)", fontsize=13)
        _save(fig, "03_wow_changes_2026.png")
    except Exception as e:
        print("  [skip 03]", e)

    # 04 price reactions all
    try:
        fig, ax = plt.subplots(figsize=(14, 7))
        x = range(len(rx))
        w = 0.2
        for i, (prod, c) in enumerate([("WTI", "black"), ("Brent", "brown"),
                                       ("HO", "orange"), ("LGO", "purple")]):
            ax.bar([xi + i * w for xi in x], rx[f"{prod}_r10_pct"].values, w, label=prod, color=c)
        ax.set_xticks([xi + 1.5 * w for xi in x])
        ax.set_xticklabels([str(d)[5:] for d in rx["release_date"]], rotation=60, fontsize=8)
        ax.axhline(0, color="k", lw=0.6); ax.legend(); ax.grid(alpha=0.3)
        ax.set_ylabel("10-min reaction %")
        ax.set_title("04 - 10-min M1 reaction by product per release")
        _save(fig, "04_price_reactions_all.png")
    except Exception as e:
        print("  [skip 04]", e)

    # 05 curve term structure time series w/ release markers
    try:
        wti = D["WTI"]
        daily = wti.groupby("et_date").agg(m1=("m1", "last"), m2=("m2", "last"),
                                           m3=("m3", "last"), m6=("m6", "last"), m12=("m12", "last"))
        idx = pd.to_datetime(daily.index)
        fig, ax = plt.subplots(figsize=(14, 7))
        for a, b, lbl in [("m1", "m2", "M1-M2"), ("m1", "m3", "M1-M3"),
                          ("m1", "m6", "M1-M6"), ("m1", "m12", "M1-M12")]:
            ax.plot(idx, daily[a] - daily[b], label=lbl)
        for d in rdates:
            ax.axvline(d, color="grey", ls=":", lw=0.7)
        ax.axhline(0, color="k", lw=0.6); ax.legend(); ax.grid(alpha=0.3)
        ax.set_title("05 - WTI term-structure spreads (dotted = EIA release)")
        _save(fig, "05_curve_term_structure.png")
    except Exception as e:
        print("  [skip 05]", e)

    # 06 curve reaction heatmap
    try:
        heat = D["heat"]
        fig, ax = plt.subplots(figsize=(11, 8))
        data = heat.values.astype(float)
        vmax = np.nanmax(np.abs(data)) or 1
        im = ax.imshow(data, cmap="RdYlGn", aspect="auto",
                       norm=TwoSlopeNorm(vcenter=0, vmin=-vmax, vmax=vmax))
        ax.set_xticks(range(len(heat.columns))); ax.set_xticklabels(heat.columns, rotation=45)
        ax.set_yticks(range(len(heat.index)))
        ax.set_yticklabels([str(d)[5:] for d in heat.index], fontsize=8)
        for i in range(data.shape[0]):
            for j in range(data.shape[1]):
                if not np.isnan(data[i, j]):
                    ax.text(j, i, f"{data[i,j]:.2f}", ha="center", va="center", fontsize=7)
        fig.colorbar(im, ax=ax, label="post-pre delta")
        ax.set_title("06 - WTI curve reaction heatmap (spread delta)")
        _save(fig, "06_curve_reaction_heatmap.png")
    except Exception as e:
        print("  [skip 06]", e)

    # 07 hit rate summary
    try:
        hit = D["analytics"]["hit"]
        fig, ax = plt.subplots(figsize=(12, 6))
        x = range(len(hit)); w = 0.35
        ax.bar([i - w/2 for i in x], hit["hit_rate_10min"] * 100, w, label="10-min", color="steelblue")
        ax.bar([i + w/2 for i in x], hit["hit_rate_eod"] * 100, w, label="EOD", color="indianred")
        ax.axhline(50, color="k", ls="--", lw=0.8)
        ax.set_xticks(list(x)); ax.set_xticklabels(hit["pair"], rotation=30, fontsize=8)
        ax.set_ylabel("Hit rate %"); ax.legend(); ax.grid(alpha=0.3)
        ax.set_title("07 - Hit rate by signal->product (vs 50% coin-flip)")
        _save(fig, "07_hit_rate_summary.png")
    except Exception as e:
        print("  [skip 07]", e)

    # 08 fade vs follow-through scatter
    try:
        fig, ax = plt.subplots(figsize=(9, 8))
        x = rx["WTI_r10_pct"]; y = rx["WTI_eod_pct"]
        draw = inv.set_index("release_date")["crude_chg"]
        colors = ["green" if draw.get(d, 0) < 0 else "red" for d in rx["release_date"]]
        ax.scatter(x, y, c=colors, s=80, edgecolor="k")
        lim = np.nanmax(np.abs([x.min(), x.max(), y.min(), y.max()])) or 1
        ax.plot([-lim, lim], [-lim, lim], "k--", lw=0.8)
        ax.axhline(0, color="grey", lw=0.6); ax.axvline(0, color="grey", lw=0.6)
        ax.set_xlabel("10-min reaction %"); ax.set_ylabel("EOD reaction %")
        ax.set_title("08 - Fade vs follow-through (green=draw, red=build)")
        ax.grid(alpha=0.3)
        _save(fig, "08_fade_vs_followthrough.png")
    except Exception as e:
        print("  [skip 08]", e)

    # 09 cumulative P&L simulation (WTI 3 holds)
    try:
        sim = D["analytics"]["sim"]
        invd = inv.set_index("release_date")
        sd = invd["crude_chg"].apply(lambda v: 0 if (np.isnan(v) or abs(v) < 500) else (1 if v < 0 else -1))
        fig, ax = plt.subplots(figsize=(13, 6))
        rxi = rx.set_index("release_date")
        for hold, col in [("10min", "WTI_r10_pct"), ("30min", "WTI_r30_pct"), ("EOD", "WTI_eod_pct")]:
            cum, xs = [], []
            run = 0
            for d in rxi.index:
                s = sd.get(d, 0); r = rxi.loc[d, col]
                if s != 0 and not np.isnan(r):
                    run += s * r
                cum.append(run); xs.append(str(d)[5:])
            ax.plot(xs, cum, marker="o", label=f"{hold} hold")
        ax.axhline(0, color="k", lw=0.6); ax.legend(); ax.grid(alpha=0.3)
        ax.set_ylabel("cum P&L (% per bbl)"); plt.setp(ax.get_xticklabels(), rotation=60, fontsize=8)
        ax.set_title("09 - Cumulative P&L: raw crude-inventory signal (WTI)")
        _save(fig, "09_pnl_simulation.png")
    except Exception as e:
        print("  [skip 09]", e)

    # 10 composite score vs reaction + regression
    try:
        m = pd.DataFrame({"score": comp["composite_score"],
                          "react": [rx.set_index("release_date").loc[d, "WTI_r10_pct"]
                                    if d in rx["release_date"].values else np.nan for d in comp.index]}).dropna()
        fig, ax = plt.subplots(figsize=(9, 7))
        ax.scatter(m["score"], m["react"], s=80, color="teal", edgecolor="k")
        if len(m) >= 2:
            b1, b0 = np.polyfit(m["score"], m["react"], 1)
            xs = np.linspace(m["score"].min(), m["score"].max(), 50)
            ax.plot(xs, b0 + b1 * xs, "r-")
            r, p = stats.pearsonr(m["score"], m["react"])
            ax.text(0.05, 0.92, f"r={r:.2f}, R2={r**2:.2f}, n={len(m)}", transform=ax.transAxes)
        ax.axhline(0, color="grey", lw=0.6); ax.axvline(0, color="grey", lw=0.6)
        ax.set_xlabel("Composite score"); ax.set_ylabel("10-min WTI reaction %")
        ax.set_title("10 - Composite score vs 10-min WTI reaction"); ax.grid(alpha=0.3)
        _save(fig, "10_composite_score_vs_reaction.png")
    except Exception as e:
        print("  [skip 10]", e)

    # 11 macro context 3 panels
    try:
        fig, axes = plt.subplots(3, 1, figsize=(13, 10), sharex=True)
        for ax, col, lbl, c in [(axes[0], "DXY", "DXY", "blue"),
                                 (axes[1], "US10Y_pct", "US10Y %", "green"),
                                 (axes[2], "Gold", "Gold", "goldenrod")]:
            ax.plot(macro["Date"], macro[col], color=c)
            for d in rdates:
                ax.axvline(d, color="grey", ls=":", lw=0.6)
            ax.set_ylabel(lbl); ax.grid(alpha=0.3)
        axes[0].set_title("11 - Macro context (dotted = EIA release)")
        _save(fig, "11_macro_context.png")
    except Exception as e:
        print("  [skip 11]", e)

    # 12 crack spreads pre/post
    try:
        fig, ax = plt.subplots(figsize=(13, 6))
        x = range(len(rx))
        ax.plot(x, rx["crack_pre"], marker="o", label="HO crack pre", color="orange")
        ax.plot(x, rx["crack_post"], marker="s", label="HO crack post-10min", color="red")
        ax.set_xticks(list(x)); ax.set_xticklabels([str(d)[5:] for d in rx["release_date"]], rotation=60, fontsize=8)
        ax.legend(); ax.grid(alpha=0.3); ax.set_ylabel("$/bbl")
        ax.set_title("12 - HO crack (vs WTI) pre/post each EIA release")
        _save(fig, "12_crack_spreads.png")
    except Exception as e:
        print("  [skip 12]", e)

    # 13 days of supply
    try:
        crude = eia["crude"]; refin = eia["refinery_in"]
        dos = pd.merge(crude[["period", "value"]], refin[["period", "value"]],
                       on="period", suffixes=("_crude", "_ref"))
        dos["dos"] = dos["value_crude"] / dos["value_ref"]
        dos["iso_week"] = dos["period"].apply(iso_week)
        hist = dos[dos["period"].dt.year.isin(range(2020, 2025))]
        band = hist.groupby("iso_week")["dos"].agg(["mean", "std"])
        fig, ax = plt.subplots(figsize=(14, 6))
        ax.plot(dos["period"], dos["dos"], color="navy", lw=0.9)
        ax.set_title("13 - Days of supply (crude stocks / refinery inputs)")
        ax.grid(alpha=0.3); ax.set_ylabel("days")
        _save(fig, "13_days_of_supply.png")
    except Exception as e:
        print("  [skip 13]", e)

    # 14 forward curve snapshots (c1-c12 at print-10 vs print+10) per release
    try:
        wti = D["WTI"]
        fig, axes = plt.subplots(3, 4, figsize=(18, 11))
        ncols = [f"m{i}" for i in range(1, 13)]
        for ax, (_, r) in zip(axes.ravel(), rel.iterrows()):
            day = r["release_date"]; p = int(r["print_min"])
            pre_c = [window_mean(wti, day, p - 10, p - 1, c) for c in ncols]
            post_c = [window_mean(wti, day, p + 9, p + 10, c) for c in ncols]
            if all(np.isnan(pre_c)):
                ax.set_title(f"{str(day)[5:]} (no px)", fontsize=8); ax.axis("off"); continue
            ax.plot(range(1, 13), pre_c, marker="o", label="10:20", color="blue")
            ax.plot(range(1, 13), post_c, marker="s", label="10:40", color="red")
            ax.set_title(str(day)[5:], fontsize=9); ax.grid(alpha=0.3)
        axes.ravel()[0].legend(fontsize=7)
        fig.suptitle("14 - WTI forward curve c1-c12: pre (10:20) vs post (10:40)", fontsize=13)
        _save(fig, "14_forward_curve_snapshots.png")
    except Exception as e:
        print("  [skip 14]", e)

    # 15 pretrade signal vs actual reaction
    try:
        fig, ax = plt.subplots(figsize=(13, 6))
        x = range(len(pre))
        ax.bar(x, pre["pretrade_score"], color="slateblue", alpha=0.6, label="pre-trade score")
        ax2 = ax.twinx()
        rxi = rx.set_index("release_date")
        actual = [rxi.loc[d, "WTI_r10_pct"] if d in rxi.index else np.nan for d in pre["release_date"]]
        ax2.plot(x, actual, color="black", marker="o", label="actual WTI 10-min %")
        ax.set_xticks(list(x)); ax.set_xticklabels([str(d)[5:] for d in pre["release_date"]], rotation=60, fontsize=8)
        ax.axhline(0, color="grey", lw=0.6)
        ax.set_ylabel("pre-trade score"); ax2.set_ylabel("actual 10-min %")
        ax.legend(loc="upper left"); ax2.legend(loc="upper right")
        ax.set_title("15 - Pre-trade signal vs actual WTI 10-min reaction")
        _save(fig, "15_pretrade_signal_vs_actual.png")
    except Exception as e:
        print("  [skip 15]", e)

    print()


# ============================================================================
#  MAIN
# ============================================================================
def main():
    D = load_data()
    compute_inventory_wow(D)
    build_pretrade_signal(D)
    compute_price_reactions(D)
    run_trader_analytics(D)
    regime_conditioning(D)
    compute_amplifiers(D)
    curve_reaction_analysis(D)
    generate_trading_memo(D)
    save_all_plots(D)
    print("=" * 64)
    print(f"  DONE. Outputs in: {OUT}")
    print("=" * 64)


if __name__ == "__main__":
    main()
