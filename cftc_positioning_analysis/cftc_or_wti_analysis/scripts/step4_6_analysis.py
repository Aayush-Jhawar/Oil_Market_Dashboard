"""
STEP 4-6: extremes, forward-return tests (HAC + block bootstrap), decay probe.
Reads panel.parquet (priced window only). Writes results.json for charts + deck.
"""
import pandas as pd, numpy as np, json, os, warnings
import statsmodels.api as sm
warnings.filterwarnings('ignore')
np.random.seed(7)
pd.set_option('display.width', 220); pd.set_option('display.max_columns', 40)
SCRATCH = os.path.dirname(os.path.abspath(__file__))

m = pd.read_parquet(os.path.join(SCRATCH, "panel.parquet"))
# integrity: post-release close must be within 7 days of releasedate
chk = (m['p0_date'] - m['releasedate']).dt.days
print("INTEGRITY p0_date-releasedate days (where priced): min %s max %s" %
      (chk.min(), chk.max()))
W = m[m['p0_adj'].notna() & m['z'].notna()].copy().reset_index(drop=True)
W = W.sort_values('date').reset_index(drop=True)
print("Priced+signal window: n=%d  %s .. %s" %
      (len(W), W['date'].min().date(), W['date'].max().date()))

# ---------------- STEP 4: EXTREMES ----------------
ZT = 2.0
W['ext_long']  = (W['z'] >=  ZT)
W['ext_short'] = (W['z'] <= -ZT)
# decile (rolling percentile) alternative
W['dec_long']  = (W['pctile'] >= 90)
W['dec_short'] = (W['pctile'] <= 10)

def episodes(flag, dates, max_gap_weeks=1):
    """count distinct episodes = runs of True separated by > max_gap_weeks non-True weeks"""
    idx = np.where(flag.values)[0]
    if len(idx) == 0: return 0, []
    eps = []; start = idx[0]; prev = idx[0]
    for i in idx[1:]:
        if i - prev > max_gap_weeks:
            eps.append((start, prev)); start = i
        prev = i
    eps.append((start, prev))
    spans = [(dates.iloc[a].date(), dates.iloc[b].date(), b - a + 1) for a, b in eps]
    return len(eps), spans

for nm, fl in [('ext_long', W['ext_long']), ('ext_short', W['ext_short']),
               ('dec_long', W['dec_long']), ('dec_short', W['dec_short'])]:
    ne, sp = episodes(fl, W['date'])
    print(f"\n{nm}: {int(fl.sum())} weeks, {ne} episodes")
    for s in sp: print("   ", s)

# ---------------- STEP 5: FORWARD-RETURN TESTS ----------------
HOR = [1, 2, 4]
uncond = {h: W[f'fwd_{h}w'].dropna() for h in HOR}

def hac_diff(y, d, lag):
    """OLS y = a + b*d ; b = mean(y|d=1)-mean(y|d=0); HAC(Newey-West) t-stat on b."""
    s = pd.DataFrame({'y': y, 'd': d.astype(float)}).dropna()
    if s['d'].sum() < 2 or (s['d'] == 0).sum() < 2: return np.nan, np.nan, np.nan
    X = sm.add_constant(s['d'])
    r = sm.OLS(s['y'], X).fit(cov_type='HAC', cov_kwds={'maxlags': max(lag, 1)})
    return r.params['d'], r.bse['d'], r.tvalues['d']

def block_boot_diff(y, flag, h, n=5000):
    """circular block bootstrap of difference mean(extreme)-mean(all); two-sided p vs 0."""
    s = pd.DataFrame({'y': y, 'f': flag.astype(bool)}).dropna().reset_index(drop=True)
    yv = s['y'].values; fv = s['f'].values; N = len(yv)
    if fv.sum() < 2: return np.nan, (np.nan, np.nan)
    obs = yv[fv].mean() - yv.mean()
    L = max(h, 3)  # block length ~ horizon
    nb = int(np.ceil(N / L))
    diffs = np.empty(n)
    for b in range(n):
        starts = np.random.randint(0, N, nb)
        idx = (starts[:, None] + np.arange(L)[None, :]).ravel() % N
        idx = idx[:N]
        ys = yv[idx]; fs = fv[idx]
        diffs[b] = (ys[fs].mean() - ys.mean()) if fs.sum() > 0 else 0.0
    # two-sided p: H0 diff=0 -> recenter bootstrap dist on 0
    centered = diffs - diffs.mean()
    p = (np.abs(centered) >= abs(obs)).mean()
    ci = (np.percentile(diffs, 2.5), np.percentile(diffs, 97.5))
    return p, ci

rows = []
for bucket, fl in [('extreme_long', W['ext_long']), ('extreme_short', W['ext_short'])]:
    ne, _ = episodes(fl, W['date'])
    for h in HOR:
        y = W[f'fwd_{h}w']
        sub = y[fl].dropna()
        if len(sub) == 0:
            continue
        u = uncond[h]
        b, se, t = hac_diff(y, fl, lag=h - 1 + 1)  # NW lag covers overlap (h-1) + buffer
        p, ci = block_boot_diff(y, fl, h)
        rows.append(dict(
            bucket=bucket, horizon_w=h, n_weeks=int(len(sub)), n_episodes=ne,
            mean=float(sub.mean()), median=float(sub.median()), std=float(sub.std()),
            hit_pos=float((sub > 0).mean()),
            uncond_mean=float(u.mean()), uncond_median=float(u.median()),
            diff_vs_uncond=float(sub.mean() - u.mean()),
            hac_se=float(se) if se == se else None,
            hac_t=float(t) if t == t else None,
            boot_p=float(p) if p == p else None,
            boot_ci_lo=float(ci[0]) if ci[0] == ci[0] else None,
            boot_ci_hi=float(ci[1]) if ci[1] == ci[1] else None,
        ))
res = pd.DataFrame(rows)
print("\n================ STEP 5: FORWARD-RETURN RESULTS (returns in %) ================")
show = res.copy()
for c in ['mean','median','std','hit_pos','uncond_mean','uncond_median','diff_vs_uncond',
          'hac_se','boot_ci_lo','boot_ci_hi']:
    show[c] = (show[c]*100).round(2)
show['hit_pos'] = (res['hit_pos']*100).round(0)
show['hac_t'] = res['hac_t'].round(2); show['boot_p'] = res['boot_p'].round(3)
print(show[['bucket','horizon_w','n_weeks','n_episodes','mean','median','hit_pos',
            'uncond_mean','diff_vs_uncond','hac_se','hac_t','boot_p']].to_string(index=False))

print("\nUNCONDITIONAL (all priced weeks):")
for h in HOR:
    u = uncond[h]
    print(f"  {h}w: n={len(u)} mean={u.mean()*100:.2f}% median={u.median()*100:.2f}% "
          f"std={u.std()*100:.2f}% hit+={(u>0).mean()*100:.0f}%")

# ---------------- STEP 6: DECAY PROBE ----------------
print("\n================ STEP 6: DECAY PROBE (pre-release Tue->Fri vs post-release) ======")
W['pre'] = W['pre_ret']            # Tue(as-of) -> Fri(release) : untradeable
W['post1'] = W['fwd_1w']           # Fri -> Fri+1w : tradeable
W['tot_tue_to_1w'] = (1 + W['pre']) * (1 + W['post1']) - 1
decay = []
for bucket, fl in [('extreme_long', W['ext_long']), ('extreme_short', W['ext_short']),
                   ('unconditional', pd.Series(True, index=W.index))]:
    sub = W[fl]
    pre = sub['pre'].dropna(); post = sub['post1'].dropna()
    d = dict(bucket=bucket, n=int(fl.sum()),
             pre_mean=float(pre.mean()), post1_mean=float(post.mean()),
             pre_median=float(pre.median()), post1_median=float(post.median()))
    tot = d['pre_mean'] + d['post1_mean']
    d['pre_share_of_move'] = float(d['pre_mean']/tot) if abs(tot) > 1e-9 else np.nan
    decay.append(d)
dec = pd.DataFrame(decay)
showd = dec.copy()
for c in ['pre_mean','post1_mean','pre_median','post1_median']:
    showd[c] = (showd[c]*100).round(3)
showd['pre_share_of_move'] = (dec['pre_share_of_move']*100).round(0)
print(showd.to_string(index=False))
print("\nNote: pre window = Tue->Fri (~3 trading days, UNTRADEABLE; data not yet public).")
print("      post1 window = Fri release -> +1 week (tradeable). pre_share = pre/(pre+post1).")

# ---------------- SAVE ----------------
out = dict(
    window=dict(n=len(W), start=str(W['date'].min().date()), end=str(W['date'].max().date()),
                price_series="roll-adjusted continuous front-month WTI (NYMEX CL, local 1-min)",
                signal="Other Reportables NET (CFTC Disaggregated, futures-only); OI not in local file -> level + rolling 52w Z"),
    extremes={k: dict(weeks=int(W[k].sum()), episodes=episodes(W[k], W['date'])[0])
              for k in ['ext_long','ext_short','dec_long','dec_short']},
    forward=res.to_dict(orient='records'),
    uncond={h: dict(n=int(len(uncond[h])), mean=float(uncond[h].mean()),
                    median=float(uncond[h].median()), std=float(uncond[h].std()),
                    hit_pos=float((uncond[h]>0).mean())) for h in HOR},
    decay=dec.to_dict(orient='records'),
)
with open(os.path.join(SCRATCH, "results.json"), "w") as f:
    json.dump(out, f, indent=2, default=str)
W.to_parquet(os.path.join(SCRATCH, "window.parquet"))
print("\nsaved results.json + window.parquet")
