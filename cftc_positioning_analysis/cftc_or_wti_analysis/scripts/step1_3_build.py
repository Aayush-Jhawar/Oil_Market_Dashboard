"""
STEP 1-3: Clean CFTC OR-net, build roll-adjusted continuous front-month WTI from
local CL_data.parquet, merge on releasedate (look-ahead fix), construct signals.
Saves merged weekly panel to scratchpad for later steps.
"""
import pandas as pd, numpy as np, os, warnings
warnings.filterwarnings('ignore')
pd.set_option('display.width', 200); pd.set_option('display.max_columns', 40)

ROOT = r"c:/Users/aayush.jhawar/OneDrive - hertshtengroup.com/Desktop/Dashboard_v3"
SCRATCH = os.path.dirname(os.path.abspath(__file__))

# ---------------- STEP 1: CLEAN CFTC ----------------
cf = pd.read_excel(os.path.join(ROOT, "Data/CFTC 2016-2026 CL.xlsx"))
n0 = len(cf)
cf = cf.drop_duplicates()                      # drop the 3 exact-dup rows
cf['date'] = pd.to_datetime(cf['date'])         # Tuesday as-of
cf['releasedate'] = pd.to_datetime(cf['releasedate'])  # Friday publication
cf = cf.sort_values('date').reset_index(drop=True)
cf = cf.rename(columns={'actual': 'or_net'})    # Other Reportables NET (confirmed STEP0)
cf = cf[['date', 'releasedate', 'or_net']]
print(f"STEP1: rows {n0} -> {len(cf)} after dedup. "
      f"date {cf['date'].min().date()}..{cf['date'].max().date()}")
gap = (cf['releasedate'] - cf['date']).dt.days
print(f"  release-date gap days: min {gap.min()} med {int(gap.median())} max {gap.max()}")

# ---------------- STEP 2a: BUILD WTI DAILY (roll-adjusted continuous front-month) ----
# parquet lacks contract symbols; read 5 cols from CSV (1st line is a #meta header -> skiprows=1)
cols = ['timestamp', 'c1||contract', 'c1||weighted_mid', 'c2||contract', 'c2||weighted_mid']
px = pd.read_csv(os.path.join(ROOT, "Data/CL_data.csv"), skiprows=1, usecols=cols)
px['timestamp'] = pd.to_datetime(px['timestamp'], utc=True)
px['et'] = px['timestamp'].dt.tz_convert('America/New_York')
px['d'] = px['et'].dt.normalize().dt.tz_localize(None)  # ET calendar date
px = px.dropna(subset=['c1||weighted_mid']).sort_values('timestamp')

# daily = last print per ET date
daily = px.groupby('d').agg(
    c1=('c1||weighted_mid', 'last'),
    c1c=('c1||contract', 'last'),
    c2=('c2||weighted_mid', 'last'),
    c2c=('c2||contract', 'last'),
).reset_index().sort_values('d').reset_index(drop=True)
print(f"\nSTEP2: WTI daily {daily['d'].min().date()}..{daily['d'].max().date()} n={len(daily)}")

# roll-adjusted continuous return:
#   normal day: c1_t / c1_{t-1} - 1
#   roll day (c1 contract changed): c1_t / c2_{t-1} - 1   (c2_{t-1} == same contract as c1_t)
daily['c1_prev'] = daily['c1'].shift(1)
daily['c1c_prev'] = daily['c1c'].shift(1)
daily['c2_prev'] = daily['c2'].shift(1)
daily['c2c_prev'] = daily['c2c'].shift(1)
roll = daily['c1c'] != daily['c1c_prev']
roll.iloc[0] = False
# verify roll maps c1_t == c2_{t-1}
roll_ok = roll & (daily['c1c'] == daily['c2c_prev'])
roll_bad = roll & (daily['c1c'] != daily['c2c_prev'])
print(f"  rolls detected: {int(roll.sum())}; clean(c1_t==c2_(t-1)): {int(roll_ok.sum())}; "
      f"non-standard: {int(roll_bad.sum())}")
ret = daily['c1'] / daily['c1_prev'] - 1.0           # default within-contract
ret = ret.where(~roll_ok, daily['c1'] / daily['c2_prev'] - 1.0)  # roll: use c2 overlap
ret = ret.where(~roll_bad, np.nan)                    # non-standard roll -> drop that day's ret
ret.iloc[0] = 0.0
ret = ret.fillna(0.0)
daily['ret'] = ret
daily['adj'] = 100.0 * (1.0 + daily['ret']).cumprod()  # roll-adjusted continuous index
daily['raw'] = daily['c1']                              # raw front-month level (for price chart)
wti = daily[['d', 'adj', 'raw']].copy()

# sanity: adjusted vs raw cumulative
print(f"  raw front-month: {wti['raw'].iloc[0]:.2f} -> {wti['raw'].iloc[-1]:.2f}; "
      f"adj index: {wti['adj'].iloc[0]:.1f} -> {wti['adj'].iloc[-1]:.1f}")

# ---------------- STEP 2b: MERGE (look-ahead fix) ----------------
# join each CFTC obs to FIRST WTI daily close on/after releasedate (post-release close = P0)
cf = cf.sort_values('releasedate')
TOL = pd.Timedelta('7D')   # only match if a WTI close exists within a week (else NaN -> excludes pre-2021)
m = pd.merge_asof(cf, wti.rename(columns={'d': 'p0_date', 'adj': 'p0_adj', 'raw': 'p0_raw'}),
                  left_on='releasedate', right_on='p0_date', direction='forward', tolerance=TOL)
# Tuesday (as-of) close: first WTI close on/after 'date' (for decay probe pre-release window)
m = pd.merge_asof(m.sort_values('date'),
                  wti.rename(columns={'d': 'tue_date', 'adj': 'tue_adj'}),
                  left_on='date', right_on='tue_date', direction='forward', tolerance=TOL)
# forward-horizon closes from releasedate: +1/2/4 weeks (calendar), first close on/after target
for h in (1, 2, 4):
    tgt = (m['releasedate'] + pd.to_timedelta(7 * h, 'D'))
    tmp = m[['releasedate']].copy(); tmp['tgt'] = tgt
    tmp = tmp.sort_values('tgt')
    j = pd.merge_asof(tmp, wti.rename(columns={'d': f'h{h}_date', 'adj': f'h{h}_adj'}),
                      left_on='tgt', right_on=f'h{h}_date', direction='forward',
                      tolerance=pd.Timedelta('10D'))
    j = j.sort_index()
    m[f'h{h}_date'] = j[f'h{h}_date'].values
    m[f'h{h}_adj'] = j[f'h{h}_adj'].values

m = m.sort_values('date').reset_index(drop=True)

# forward returns from post-release close (adjusted)
for h in (1, 2, 4):
    m[f'fwd_{h}w'] = m[f'h{h}_adj'] / m['p0_adj'] - 1.0
# pre-release (untradeable) Tue->Fri return, from adjusted index
m['pre_ret'] = m['p0_adj'] / m['tue_adj'] - 1.0

# ---------------- STEP 3: SIGNALS (on FULL 2016-2026 history) ----------------
m = m.sort_values('date').reset_index(drop=True)
m['or_chg'] = m['or_net'].diff()                       # week-over-week flow
W = 52
roll_obj = m['or_net'].rolling(W, min_periods=52)
m['z'] = (m['or_net'] - roll_obj.mean()) / roll_obj.std(ddof=1)
m['z_chg'] = (m['or_chg'] - m['or_chg'].rolling(W, min_periods=52).mean()) / \
             m['or_chg'].rolling(W, min_periods=52).std(ddof=1)
m['pctile'] = m['or_net'].rolling(W, min_periods=52).apply(
    lambda x: (x < x[-1]).mean() * 100.0, raw=True)   # rolling percentile of latest vs trailing 52w

# analysis window = where we have post-release price AND a valid rolling z
has_px = m['p0_adj'].notna()
print(f"\nSTEP3: total CFTC obs {len(m)}; with post-release WTI price {int(has_px.sum())} "
      f"(from {m.loc[has_px,'date'].min().date()})")
print("  fwd-return availability:",
      {f'{h}w': int(m[f'fwd_{h}w'].notna().sum()) for h in (1, 2, 4)})

# save
out = os.path.join(SCRATCH, "panel.parquet")
m.to_parquet(out)
wti.to_parquet(os.path.join(SCRATCH, "wti_daily.parquet"))
print("saved", out)

# quick describe of signals in the priced window
win = m[has_px]
print("\nz describe (priced window):"); print(win['z'].describe()[['min','25%','50%','75%','max']])
print("or_net describe (priced window):"); print(win['or_net'].describe()[['min','25%','50%','75%','max']])
