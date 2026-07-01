"""Deeper Managed Money analysis (2021-2026): vol x position equations, persistence, extremes."""
import pandas as pd, numpy as np, json, os, warnings
from scipy import stats
warnings.filterwarnings('ignore'); np.random.seed(7); pd.set_option('display.width',200)
SCRATCH=os.path.dirname(os.path.abspath(__file__))
A=pd.read_parquet(os.path.join(SCRATCH,"mm_window.parquet")).sort_values('date').reset_index(drop=True)
wti=pd.read_parquet(os.path.join(SCRATCH,"wti_daily.parquet")).sort_values('d').reset_index(drop=True)

# ---- realized volatility known at decision time (trailing 20 trading days up to p0_date) ----
wti['lr']=np.log(wti['adj']/wti['adj'].shift(1))
wti['rv20']=wti['lr'].rolling(20).std()*np.sqrt(252)*100   # annualized %, as of each day
A['p0_date']=pd.to_datetime(A['p0_date'])
A=pd.merge_asof(A.sort_values('p0_date'), wti[['d','rv20']].rename(columns={'d':'p0_date'}),
                on='p0_date', direction='backward').sort_values('date').reset_index(drop=True)

# ---- factor states (median splits, 2x2) ----
vol_med=A['rv20'].median(); pos_med=A['z'].median()
A['VOL']=np.where(A['rv20']<=vol_med,'Low vol','High vol')
A['POS']=np.where(A['z']<=pos_med,'Low position','High position')
print(f"vol median {vol_med:.1f}%  | position(z) median {pos_med:.2f}")

def cell(sub):
    y=sub['fwd_4w'].dropna()
    t=stats.ttest_1samp(y,0) if len(y)>2 else None
    return dict(n=int(len(y)), mean=float(y.mean()), hit=float((y>0).mean()),
               med=float(y.median()), p=float(t.pvalue) if t else None)

print("\n=== 2x2 GRID: mean forward 4-week WTI return ===")
grid={}
for v in ['Low vol','High vol']:
    for p in ['Low position','High position']:
        c=cell(A[(A['VOL']==v)&(A['POS']==p)]); grid[f"{v} + {p}"]=c
        print(f"  {v:9s} + {p:14s}: {c['mean']*100:+5.1f}%  hit {c['hit']*100:3.0f}%  n={c['n']:3d}  p={c['p']:.3f}")
# baseline
b=cell(A); print(f"  {'BASELINE (all weeks)':28s}: {b['mean']*100:+5.1f}%  hit {b['hit']*100:3.0f}%  n={b['n']}")

# also 1w/2w for the four corners
print("\n  same cells at 1w / 2w / 4w:")
for v in ['Low vol','High vol']:
    for p in ['Low position','High position']:
        sub=A[(A['VOL']==v)&(A['POS']==p)]
        row=" ".join(f"{h}w {sub[f'fwd_{h}w'].mean()*100:+.1f}%" for h in (1,2,4))
        print(f"    {v} + {p}: {row}")

# ---- EQUATIONS (4wk) ----
print("\n=== EQUATIONS (forward 4-week) ===")
eqs=[]
for k,c in sorted(grid.items(), key=lambda kv:-kv[1]['mean']):
    sign='+ve' if c['mean']>0 else '-ve'
    eqs.append(dict(rule=k, mean=c['mean'], hit=c['hit'], n=c['n'], p=c['p'], sign=sign))
    print(f"  {k:30s} => CL {c['mean']*100:+.1f}% / 4wk  ({c['hit']*100:.0f}% hit, n={c['n']}, p={c['p']:.3f})")

# ---- PERSISTENCE: forward 4w by consecutive weeks in top/bottom tercile of positioning ----
print("\n=== PERSISTENCE: sustained positioning ===")
A['ptile_terc']=pd.qcut(A['z'],3,labels=['Low','Mid','High'])
def runlen(mask):
    out=np.zeros(len(mask),int); r=0
    for i,m in enumerate(mask):
        r=r+1 if m else 0; out[i]=r
    return out
A['run_high']=runlen((A['ptile_terc']=='High').values)
A['run_low']=runlen((A['ptile_terc']=='Low').values)
def dur_bucket(r): return '1 wk' if r==1 else ('2-3 wks' if r<=3 else '4+ wks')
persist={}
for nm,col in [('High position (crowded long)','run_high'),('Low position (light/short)','run_low')]:
    print(f"  {nm}:")
    sub=A[A[col]>=1].copy(); sub['db']=sub[col].apply(dur_bucket)
    d={}
    for db in ['1 wk','2-3 wks','4+ wks']:
        s=sub[sub['db']==db]; y=s['fwd_4w'].dropna()
        if len(y)==0: continue
        d[db]=dict(mean=float(y.mean()),hit=float((y>0).mean()),n=int(len(y)))
        print(f"     {db:8s}: {y.mean()*100:+5.1f}% / 4wk  hit {(y>0).mean()*100:3.0f}%  n={len(y)}")
    persist[nm]=d

# ---- EXTREMES: top/bottom 10% decile AND |z|>=2 (assignment) ----
print("\n=== EXTREMES (assignment): forward returns ===")
A['p10']=A['z']<=A['z'].quantile(0.10); A['p90']=A['z']>=A['z'].quantile(0.90)
ext={}
for nm,fl in [('Top 10% (most long)',A['p90']),('Bottom 10% (least long)',A['p10']),
              ('Z>=+2 (extreme long)',A['z']>=2),('Z<=-2 (extreme short)',A['z']<=-2)]:
    e={}
    for h in (1,2,4):
        y=A.loc[fl,f'fwd_{h}w'].dropna(); e[h]=dict(mean=float(y.mean()),hit=float((y>0).mean()),n=int(len(y)))
    ext[nm]=e
    print(f"  {nm:24s}: "+"  ".join(f"{h}w {e[h]['mean']*100:+.1f}%(hit{e[h]['hit']*100:.0f}%)" for h in (1,2,4))+f"  n={e[4]['n']}")
uncond={h:float(A[f'fwd_{h}w'].mean()) for h in (1,2,4)}
print("  Baseline (all weeks)    : "+"  ".join(f"{h}w {uncond[h]*100:+.1f}%" for h in (1,2,4)))

out=dict(vol_median=float(vol_med),pos_median=float(pos_med),grid=grid,baseline_4w=b,
         equations=eqs,persistence=persist,extremes=ext,uncond=uncond,
         n=len(A),start=str(A['date'].min().date()),end=str(A['date'].max().date()))
json.dump(out,open(os.path.join(SCRATCH,"mm_deep_results.json"),"w"),indent=2,default=str)
A.to_parquet(os.path.join(SCRATCH,"mm_deep_window.parquet"))
print("\nsaved mm_deep_results.json + mm_deep_window.parquet")
