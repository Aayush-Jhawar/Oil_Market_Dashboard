"""Re-run the study on REAL Managed Money (2021-2026, local roll-adj WTI). Same methods as the OR study.
Reuses price/return columns from panel.parquet (signal-independent); swaps signal to mm_net."""
import pandas as pd, numpy as np, json, os, warnings
import statsmodels.api as sm
from scipy import stats
warnings.filterwarnings('ignore'); np.random.seed(7)
pd.set_option('display.width',220)
SCRATCH=os.path.dirname(os.path.abspath(__file__))
ROOT=r"c:/Users/aayush.jhawar/OneDrive - hertshtengroup.com/Desktop/Dashboard_v3"

# price/return panel (signal-independent), + Managed Money signal
p=pd.read_parquet(os.path.join(SCRATCH,"panel.parquet"))
p['date']=pd.to_datetime(p['date'])
mm=pd.read_csv(os.path.join(ROOT,"Data","cftc_managed_money_wti_2016_2026.csv"))
mm['date']=pd.to_datetime(mm['date'])
m=p.merge(mm[['date','mm_net']], on='date', how='left').sort_values('date').reset_index(drop=True)
m['sig']=m['mm_net']

# signals on full history then restrict
W=52
r=m['sig'].rolling(W,min_periods=52)
m['z']=(m['sig']-r.mean())/r.std(ddof=1)
m['pctile']=m['sig'].rolling(W,min_periods=52).apply(lambda x:(x[:-1]<x[-1]).mean()*100, raw=True)
m['chg4']=m['sig'].diff(4)
A=m[m['p0_adj'].notna() & m['z'].notna()].copy().reset_index(drop=True)
A['ext_long']=A['z']>=2; A['ext_short']=A['z']<=-2
print(f"MANAGED MONEY | window n={len(A)} {A['date'].min().date()}..{A['date'].max().date()}")
print(f"MM net range in window: {int(A['sig'].min())}..{int(A['sig'].max())}")

def episodes(flag,dates,gap=1):
    idx=np.where(flag.values)[0]
    if len(idx)==0: return 0
    eps=1; prev=idx[0]
    for i in idx[1:]:
        if i-prev>gap: eps+=1
        prev=i
    return eps

# ---- extremes ----
nl,ns=int(A['ext_long'].sum()),int(A['ext_short'].sum())
el,es=episodes(A['ext_long'],A['date']),episodes(A['ext_short'],A['date'])
print(f"\nExtreme LONG |Z|>=2: {nl} wks / {el} episodes | Extreme SHORT: {ns} wks / {es} episodes")

# ---- forward returns ----
def hac(y,d,lag):
    s=pd.DataFrame({'y':y,'d':d.astype(float)}).dropna()
    if s['d'].sum()<2 or (s['d']==0).sum()<2: return np.nan,np.nan
    R=sm.OLS(s['y'],sm.add_constant(s['d'])).fit(cov_type='HAC',cov_kwds={'maxlags':max(lag,1)})
    return R.params['d'],R.tvalues['d']
def boot(y,fl,h,n=5000):
    s=pd.DataFrame({'y':y,'f':fl.astype(bool)}).dropna().reset_index(drop=True)
    yv=s['y'].values; fv=s['f'].values; N=len(yv)
    if fv.sum()<2: return np.nan
    obs=yv[fv].mean()-yv.mean(); L=max(h,3); nb=int(np.ceil(N/L)); d=np.empty(n)
    for b in range(n):
        st=np.random.randint(0,N,nb); idx=(st[:,None]+np.arange(L)[None,:]).ravel()%N; idx=idx[:N]
        d[b]=yv[idx][fv[idx]].mean()-yv[idx].mean() if fv[idx].sum()>0 else 0
    return (np.abs(d-d.mean())>=abs(obs)).mean()

HOR=[1,2,4]; uncond={h:A[f'fwd_{h}w'].dropna() for h in HOR}
print("\nFORWARD RETURNS vs unconditional (%)")
print("bucket          h  n  ep   mean   med   hit  uncond  excess  HACt  bootp")
fwd_rows=[]
for nm,fl,ep in [('ext_long',A['ext_long'],el),('ext_short',A['ext_short'],es)]:
    for h in HOR:
        y=A[f'fwd_{h}w']; sub=y[fl].dropna(); u=uncond[h]
        b,t=hac(y,fl,h); bp=boot(y,fl,h)
        fwd_rows.append(dict(bucket=nm,h=h,n=int(len(sub)),ep=ep,mean=float(sub.mean()),
            median=float(sub.median()),hit=float((sub>0).mean()),uncond=float(u.mean()),
            excess=float(sub.mean()-u.mean()),hac_t=float(t) if t==t else None,boot_p=float(bp) if bp==bp else None))
        print(f"{nm:14s} {h} {len(sub):2d} {ep:2d} {sub.mean()*100:6.1f} {sub.median()*100:6.1f} {(sub>0).mean()*100:4.0f} {u.mean()*100:6.1f} {(sub.mean()-u.mean())*100:6.1f} {t:5.2f} {bp:.3f}")
print("unconditional:", {h:f"{uncond[h].mean()*100:+.2f}%" for h in HOR})

# ---- correlations ----
c_level=A['sig'].corr(A['p0_raw']); c_pred=A['sig'].corr(A['fwd_1w'])
print(f"\nCorr(level,price)={c_level:+.2f}  Corr(level,+1w ret)={c_pred:+.3f}")

# ---- crowding/variance ----
base4=A['fwd_4w'].dropna(); long4=A.loc[A['ext_long'],'fwd_4w'].dropna()
lev=stats.levene(long4,base4,center='median') if len(long4)>1 else None
print(f"\nCROWDING: 4w std baseline {base4.std()*100:.1f}% vs extreme-LONG {long4.std()*100:.1f}%  | "
      f"P(4w<-10%) {(base4<-.1).mean()*100:.0f}% -> {(long4<-.1).mean()*100:.0f}%  | "
      f"Levene p={lev.pvalue:.3f}" if lev else "n/a")

# ---- flow / capitulation ----
F=A.dropna(subset=['chg4']).copy(); F['dec']=pd.qcut(F['chg4'],10,labels=False,duplicates='drop')
mx=F['dec'].max(); unwind=F['dec']==0; build=F['dec']==mx
print("\nFLOW (4w change deciles)")
flow={}
for nm,fl in [('fastest_unwind',unwind),('fastest_build',build)]:
    for h in HOR:
        y=F[f'fwd_{h}w']; sub=y[fl].dropna(); bp=boot(F[f'fwd_{h}w'],fl,h)
        if nm=='fastest_unwind': flow[h]=dict(mean=float(sub.mean()),hit=float((sub>0).mean()),boot_p=float(bp),n=int(fl.sum()))
        print(f"  {nm:16s} {h}w: {sub.mean()*100:+.1f}% (hit {(sub>0).mean()*100:.0f}%, n={int(fl.sum())}, bootp={bp:.3f})")

# ---- decay ----
A['pre']=A['pre_ret']; A['post1']=A['fwd_1w']
print("\nDECAY (pre Tue->Fri vs post Fri->+1w)")
decay=[]
for nm,fl in [('ext_short',A['ext_short']),('ext_long',A['ext_long']),('uncond',pd.Series(True,index=A.index))]:
    sub=A[fl]; pre=sub['pre'].mean(); post=sub['post1'].mean(); tot=pre+post
    sh=pre/tot if abs(tot)>1e-9 else np.nan
    decay.append(dict(bucket=nm,pre=float(pre),post1=float(post),pre_share=float(sh)))
    print(f"  {nm:10s}: pre {pre*100:+.2f}%  post1 {post*100:+.2f}%  pre-share {sh*100:.0f}%")

# save
out=dict(series="Managed Money (CFTC Disaggregated futures-only, WTI 067651)",
    window=dict(n=len(A),start=str(A['date'].min().date()),end=str(A['date'].max().date()),
                mm_net_min=int(A['sig'].min()),mm_net_max=int(A['sig'].max())),
    extremes=dict(long_wks=nl,long_ep=el,short_wks=ns,short_ep=es),
    forward=fwd_rows, uncond={h:dict(mean=float(uncond[h].mean()),median=float(uncond[h].median()),
        std=float(uncond[h].std()),hit=float((uncond[h]>0).mean()),n=int(len(uncond[h]))) for h in HOR},
    corr=dict(level_price=float(c_level),level_fwd1=float(c_pred)),
    crowding=dict(std_base=float(base4.std()),std_long=float(long4.std()),
        p_dd_base=float((base4<-.1).mean()),p_dd_long=float((long4<-.1).mean()),
        levene_p=float(lev.pvalue) if lev else None),
    flow=flow, decay=decay)
json.dump(out, open(os.path.join(SCRATCH,"mm_results.json"),"w"), indent=2, default=str)
A.to_parquet(os.path.join(SCRATCH,"mm_window.parquet"))
print("\nsaved mm_results.json + mm_window.parquet")
