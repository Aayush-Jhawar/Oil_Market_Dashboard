"""Volatility x Positioning regime analysis (no reliance on rare contango). Both crudes, bootstrap + cross-instrument."""
import pandas as pd, numpy as np, warnings, os
warnings.filterwarnings('ignore'); np.random.seed(7); pd.set_option('display.width',200)
SCRATCH=os.path.dirname(os.path.abspath(__file__))
Aw=pd.read_parquet(os.path.join(SCRATCH,'panel_wti_full.parquet'))
Ab=pd.read_parquet(os.path.join(SCRATCH,'panel_brent_full.parquet'))
def boot_p(y_all,mask,h=4,n=4000):
    s=pd.DataFrame({'y':y_all,'f':mask}).dropna().reset_index(drop=True)
    yv=s['y'].values; fv=s['f'].values.astype(bool); N=len(yv)
    if fv.sum()<3: return np.nan
    obs=yv[fv].mean()-yv.mean(); L=max(h,3); nb=int(np.ceil(N/L)); d=np.empty(n)
    for b in range(n):
        st=np.random.randint(0,N,nb); idx=(st[:,None]+np.arange(L)[None,:]).ravel()%N; idx=idx[:N]
        d[b]=yv[idx][fv[idx]].mean()-yv[idx].mean() if fv[idx].sum()>0 else 0
    return (np.abs(d-d.mean())>=abs(obs)).mean()
def cell(A,mask):
    y=A.loc[mask,'fwd_4w'].dropna(); return (y.mean()*100,(y>0).mean()*100,len(y),boot_p(A['fwd_4w'],mask))
def show(A,mask):
    m,h,n,p=cell(A,mask); return f"{m:+5.1f}% (hit {h:3.0f}%, n={n:3d}, p={p:.2f})"

for A in (Aw,Ab):
    A['VOLt']=pd.qcut(A['rv20'],3,labels=['LoVol','MidVol','HiVol'])
    A['POSt']=pd.qcut(A['z'],3,labels=['Light','Mid','Crowded'])
base={'WTI':Aw['fwd_4w'].mean()*100,'BRENT':Ab['fwd_4w'].mean()*100}
print(f"baseline fwd4w: WTI {base['WTI']:+.2f}%  BRENT {base['BRENT']:+.2f}%\n")

print("[VOL alone] fwd4w by volatility tercile")
for t in ['LoVol','MidVol','HiVol']:
    print(f"  {t:7s}: WTI {show(Aw,Aw['VOLt']==t)} | BRENT {show(Ab,Ab['VOLt']==t)}")
print("\n[POSITION alone] fwd4w by positioning tercile")
for t in ['Light','Mid','Crowded']:
    print(f"  {t:8s}: WTI {show(Aw,Aw['POSt']==t)} | BRENT {show(Ab,Ab['POSt']==t)}")

print("\n[VOL x POSITION 2x2] (median splits)")
Aw['V2']=np.where(Aw['rv20']<=Aw['rv20'].median(),'LoVol','HiVol'); Aw['P2']=np.where(Aw['z']<=Aw['z'].median(),'Light','Crowded')
Ab['V2']=np.where(Ab['rv20']<=Ab['rv20'].median(),'LoVol','HiVol'); Ab['P2']=np.where(Ab['z']<=Ab['z'].median(),'Light','Crowded')
print(f"{'cell':18s} | {'WTI':30s} | {'BRENT':30s} | agree")
for v in ['LoVol','HiVol']:
    for p in ['Light','Crowded']:
        mw=(Aw['V2']==v)&(Aw['P2']==p); mb=(Ab['V2']==v)&(Ab['P2']==p)
        cw=cell(Aw,mw); cb=cell(Ab,mb)
        agree='YES' if np.sign(cw[0]-base['WTI'])==np.sign(cb[0]-base['BRENT']) else ''
        print(f"{v}+{p:8s} | {show(Aw,mw):30s} | {show(Ab,mb):30s} | {agree}")

print("\n[VOL x POSITION 3x3] fwd4w  (WTI / BRENT)")
for v in ['LoVol','MidVol','HiVol']:
    row=[]
    for p in ['Light','Mid','Crowded']:
        mw=(Aw['VOLt']==v)&(Aw['POSt']==p); mb=(Ab['VOLt']==v)&(Ab['POSt']==p)
        w=cell(Aw,mw); b=cell(Ab,mb)
        row.append(f"{p[:4]}:{w[0]:+.1f}/{b[0]:+.1f}")
    print(f"  {v:7s}: "+"   ".join(row))
