"""Compare to friend's deck: run THEIR tests (corr, Levene variance, flow/capitulation) on MY data."""
import pandas as pd, numpy as np, warnings
from scipy import stats
warnings.filterwarnings('ignore'); np.random.seed(7)
SCRATCH = r"C:/Users/AAYUSH~1.JHA/AppData/Local/Temp/claude/c--Users-aayush-jhawar-OneDrive---hertshtengroup-com-Desktop-Dashboard-v3/909d8bd0-27b4-4439-b318-9c417b33fbc6/scratchpad"
import os
m = pd.read_parquet(os.path.join(SCRATCH,"panel.parquet")).sort_values('date').reset_index(drop=True)
m['or_chg4'] = m['or_net'].diff(4)                  # 4-week change in net (flow), full history
W = m[m['p0_adj'].notna() & m['z'].notna()].copy().reset_index(drop=True)
W['ext_long'] = W['z'] >= 2.0
W['ext_short'] = W['z'] <= -2.0
print(f"Window n={len(W)}  {W['date'].min().date()}..{W['date'].max().date()}  (OR net, 2021-2026)\n")

# ---- A) correlations ----
c_level = W['or_net'].corr(W['p0_raw'])             # contemporaneous level vs price
c_pred  = W['or_net'].corr(W['fwd_1w'])             # level -> next-week return
c_predz = W['z'].corr(W['fwd_1w'])
# significance of predictive corr
r=c_pred; n=W['fwd_1w'].notna().sum(); t=r*np.sqrt((n-2)/(1-r**2)); p=2*(1-stats.t.cdf(abs(t),n-2))
print("A) CORRELATIONS")
print(f"   contemporaneous corr(OR level, WTI price) = {c_level:+.2f}   (friend MM: -0.49)")
print(f"   predictive corr(OR level, +1w return)     = {c_pred:+.3f} (p={p:.2f})   (friend MM: +0.003, p=0.94)")
print(f"   predictive corr(rolling Z,  +1w return)   = {c_predz:+.3f}\n")

# ---- C) FINDING 1: crowding = risk (variance expansion) ----
base4 = W['fwd_4w'].dropna()
long4 = W.loc[W['ext_long'],'fwd_4w'].dropna()
short4= W.loc[W['ext_short'],'fwd_4w'].dropna()
def semidev(x):
    x=np.asarray(x); neg=x[x<0]; return np.sqrt((neg**2).mean()) if len(neg) else 0.0
print("C) CROWDING = RISK  (forward 4-week return distribution)")
print(f"   std:  baseline {base4.std()*100:5.1f}%   extreme-LONG {long4.std()*100:5.1f}%   extreme-SHORT {short4.std()*100:5.1f}%")
print(f"        (friend: baseline 12.8% -> after extreme LONG 24.9%)")
print(f"   P(4w return < -10%): baseline {(base4<-0.10).mean()*100:4.0f}%   extreme-LONG {(long4<-0.10).mean()*100:4.0f}%   (friend: 13% -> 29%)")
print(f"   downside semidev:    baseline {semidev(base4)*100:4.1f}%   extreme-LONG {semidev(long4)*100:4.1f}%")
if len(long4)>1:
    lev = stats.levene(long4, base4, center='median')
    print(f"   Levene (extreme-LONG vs baseline 4w var): W={lev.statistic:.2f} p={lev.pvalue:.3f}   (friend: p<0.001)\n")

# ---- D) FINDING 2: rate-of-change / capitulation (flow signal) ----
print("D) FLOW SIGNAL  (4-week change in OR net, decile-ranked)")
F = W.dropna(subset=['or_chg4']).copy()
F['dec'] = pd.qcut(F['or_chg4'], 10, labels=False, duplicates='drop')
maxdec = F['dec'].max()
unwind = F[F['dec']==0]          # most negative 4w change = fastest unwind / capitulation
build  = F[F['dec']==maxdec]     # most positive = fastest build
neutral= F[F['dec'].isin([4,5])]
for nm,grp in [('fastest UNWIND (capitulation)',unwind),('NEUTRAL',neutral),('fastest BUILD',build)]:
    row=[]
    for h in (1,2,4):
        y=grp[f'fwd_{h}w'].dropna()
        tt=stats.ttest_1samp(y,0) if len(y)>1 else None
        row.append(f"{h}w {y.mean()*100:+.1f}% (hit {(y>0).mean()*100:.0f}%, p={tt.pvalue:.3f})")
    print(f"   {nm:32s} n={len(grp):3d}: " + " | ".join(row))
# friend headline: fastest unwind -> +3.7% over 4w, 63% hit, t=2.14, p=0.037
u4=unwind['fwd_4w'].dropna()
tt=stats.ttest_1samp(u4,0)
print(f"\n   >> fastest-unwind 4w: mean {u4.mean()*100:+.1f}%, hit {(u4>0).mean()*100:.0f}%, t={tt.statistic:.2f}, p={tt.pvalue:.3f}")
print(f"      (friend MM full-sample: +3.7%, 63% hit, t=2.14, p=0.037)")

# ---- B) extreme-cohort mean forward returns (their slide-3 bars) ----
print("\nB) EXTREME-COHORT MEAN FORWARD RETURNS (their slide-3 comparison)")
for nm,fl in [('Extreme LONG (top, Z>=2)',W['ext_long']),('Extreme SHORT (bottom, Z<=-2)',W['ext_short'])]:
    vals=[f"{h}w {W.loc[fl,f'fwd_{h}w'].mean()*100:+.1f}%" for h in (1,2,4)]
    print(f"   {nm:30s}: "+"  ".join(vals))
vals=[f"{h}w {W[f'fwd_{h}w'].mean()*100:+.1f}%" for h in (1,2,4)]
print(f"   {'Baseline (all weeks)':30s}: "+"  ".join(vals))
