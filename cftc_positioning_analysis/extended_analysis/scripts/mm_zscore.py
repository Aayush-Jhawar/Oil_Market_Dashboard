"""Z-score robustness for the Managed Money study: window, threshold, monotonicity, def-vs-decile."""
import pandas as pd, numpy as np, os, warnings
from scipy import stats
warnings.filterwarnings('ignore'); pd.set_option('display.width',200)
SCRATCH=os.path.dirname(os.path.abspath(__file__))
ROOT=r"c:/Users/aayush.jhawar/OneDrive - hertshtengroup.com/Desktop/Dashboard_v3"
p=pd.read_parquet(os.path.join(SCRATCH,"panel.parquet")); p['date']=pd.to_datetime(p['date'])
mm=pd.read_csv(os.path.join(ROOT,"Data","cftc_managed_money_wti_2016_2026.csv")); mm['date']=pd.to_datetime(mm['date'])
m=p.merge(mm[['date','mm_net']],on='date',how='left').sort_values('date').reset_index(drop=True)
m['sig']=m['mm_net']
for W in (26,52,104):
    r=m['sig'].rolling(W,min_periods=W)
    m[f'z{W}']=(m['sig']-r.mean())/r.std(ddof=1)
m['lvl_pct']=m['sig'].rolling(52,min_periods=52).apply(lambda x:(x[:-1]<x[-1]).mean()*100,raw=True)
A=m[m['p0_adj'].notna() & m['z52'].notna()].copy().reset_index(drop=True)
print(f"window n={len(A)}  {A['date'].min().date()}..{A['date'].max().date()}")
unc={h:A[f'fwd_{h}w'].mean() for h in (1,2,4)}
print("baseline 4wk:", f"{unc[4]*100:+.2f}%")

def st(s):
    y=s.dropna(); return f"{y.mean()*100:+5.1f}% (hit {(y>0).mean()*100:3.0f}%, n={len(y)})" if len(y) else "n/a"

# 1) monotonicity: forward 4wk by z52 decile
print("\n[1] Monotonic response: fwd 4wk by z52 decile (low z = least long)")
A['zdec']=pd.qcut(A['z52'],5,labels=[1,2,3,4,5])
for d in [1,2,3,4,5]:
    s=A[A['zdec']==d]; print(f"  quintile {d} (z~{s['z52'].mean():+.2f}): {st(s['fwd_4w'])}")
r=A[['z52','fwd_4w']].dropna(); rho=r['z52'].corr(r['fwd_4w'])
print(f"  corr(z52, fwd_4w) = {rho:+.3f}  (linear predictive power)")

# 2) definition agreement: |z|>=2 vs top/bottom 10% of z vs top/bottom 10% of raw level
print("\n[2] Extreme definitions agree? (forward 4wk)")
q90z,q10z=A['z52'].quantile(.9),A['z52'].quantile(.1)
q90l,q10l=A['lvl_pct'].quantile(.9),A['lvl_pct'].quantile(.1)
print("  LONG  |z|>=2        :",st(A.loc[A['z52']>=2,'fwd_4w']))
print("  LONG  top10% of z   :",st(A.loc[A['z52']>=q90z,'fwd_4w']))
print("  LONG  top10% of level:",st(A.loc[A['lvl_pct']>=90,'fwd_4w']))
print("  SHORT |z|<=-2       :",st(A.loc[A['z52']<=-2,'fwd_4w']))
print("  SHORT bot10% of z   :",st(A.loc[A['z52']<=q10z,'fwd_4w']))
print("  SHORT bot10% level  :",st(A.loc[A['lvl_pct']<=10,'fwd_4w']))

# 3) threshold sensitivity
print("\n[3] Threshold sensitivity (fwd 4wk)")
for thr in (1.5,2.0,2.5):
    print(f"  |z|>={thr}:  LONG {st(A.loc[A['z52']>=thr,'fwd_4w'])}   SHORT {st(A.loc[A['z52']<=-thr,'fwd_4w'])}")

# 4) window sensitivity 26/52/104
print("\n[4] Look-back window sensitivity (|z|>=2, fwd 4wk)")
for W in (26,52,104):
    zc=f'z{W}'; sub=A[A[zc].notna()]
    print(f"  {W}-wk z: LONG {st(sub.loc[sub[zc]>=2,'fwd_4w'])}   SHORT {st(sub.loc[sub[zc]<=-2,'fwd_4w'])}")

# 5) z of the 4-week CHANGE (flow) vs z of level
print("\n[5] z-score of the 4-week CHANGE (flow) -- does standardizing the flow help?")
m['chg4']=m['sig'].diff(4); rr=m['chg4'].rolling(52,min_periods=52)
m['zchg']=(m['chg4']-rr.mean())/rr.std(ddof=1)
A=m[m['p0_adj'].notna() & m['z52'].notna()].copy().reset_index(drop=True)
print("  flow z<=-2 (fast unwind): ",st(A.loc[A['zchg']<=-2,'fwd_4w']))
print("  flow z>=+2 (fast build):  ",st(A.loc[A['zchg']>=2,'fwd_4w']))
