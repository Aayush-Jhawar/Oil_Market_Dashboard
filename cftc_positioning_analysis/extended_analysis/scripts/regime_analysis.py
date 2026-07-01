"""Regime classification to find tradeable edges: curve x volatility x positioning.
Validated across WTI and Brent + block-bootstrap p. All factors known at decision time (post-release close)."""
import pandas as pd, numpy as np, json, os, warnings
warnings.filterwarnings('ignore'); np.random.seed(7); pd.set_option('display.width',220)
SCRATCH=os.path.dirname(os.path.abspath(__file__))
Aw=pd.read_parquet(os.path.join(SCRATCH,'panel_wti_full.parquet'))
Ab=pd.read_parquet(os.path.join(SCRATCH,'panel_brent_full.parquet'))

def prep(A):
    A=A.copy()
    A['CURVE']=np.where(A['sp12']>0,'Backwardation','Contango')      # sign of C1-C2
    A['VOL']=np.where(A['rv20']<=A['rv20'].median(),'LoVol','HiVol')
    A['POS']=np.where(A['z']<=A['z'].median(),'Light','Crowded')
    A['FLOW']=np.where(A['chg4']<=0,'Unwind','Build')
    return A
Aw=prep(Aw); Ab=prep(Ab)

def boot_p(y_all, mask, h=4, n=4000):
    s=pd.DataFrame({'y':y_all,'f':mask}).dropna().reset_index(drop=True)
    yv=s['y'].values; fv=s['f'].values.astype(bool); N=len(yv)
    if fv.sum()<3: return np.nan
    obs=yv[fv].mean()-yv.mean(); L=max(h,3); nb=int(np.ceil(N/L)); d=np.empty(n)
    for b in range(n):
        st=np.random.randint(0,N,nb); idx=(st[:,None]+np.arange(L)[None,:]).ravel()%N; idx=idx[:N]
        d[b]=yv[idx][fv[idx]].mean()-yv[idx].mean() if fv[idx].sum()>0 else 0
    return (np.abs(d-d.mean())>=abs(obs)).mean()

def cell(A,mask):
    y=A.loc[mask,'fwd_4w'].dropna()
    return dict(n=int(len(y)),mean=float(y.mean()),hit=float((y>0).mean()),
                p=float(boot_p(A['fwd_4w'],mask)))

def grid(A,factors):
    from itertools import product
    levels=[sorted(A[f].unique()) for f in factors]
    rows=[]
    for combo in product(*levels):
        mask=np.ones(len(A),bool)
        for f,v in zip(factors,combo): mask &= (A[f]==v).values
        c=cell(A,mask); c['regime']=' + '.join(combo); rows.append(c)
    return pd.DataFrame(rows)

base={'WTI':Aw['fwd_4w'].mean(),'BRENT':Ab['fwd_4w'].mean()}
print("baseline fwd 4wk: WTI %+.2f%%  BRENT %+.2f%%"%(base['WTI']*100,base['BRENT']*100))

for factors in [['CURVE','POS'],['CURVE','VOL'],['CURVE','VOL','POS']]:
    print("\n"+"="*90); print("REGIME:", ' x '.join(factors))
    gw=grid(Aw,factors).set_index('regime'); gb=grid(Ab,factors).set_index('regime')
    allr=sorted(set(gw.index)|set(gb.index))
    print(f"{'regime':38s} | {'WTI 4wk (hit,n,p)':26s} | {'BRENT 4wk (hit,n,p)':26s} | agree")
    for r in allr:
        w=gw.loc[r] if r in gw.index else None; b=gb.loc[r] if r in gb.index else None
        ws=f"{w['mean']*100:+5.1f}% ({w['hit']*100:.0f}%,{int(w['n'])},p{w['p']:.2f})" if w is not None else "-"
        bs=f"{b['mean']*100:+5.1f}% ({b['hit']*100:.0f}%,{int(b['n'])},p{b['p']:.2f})" if b is not None else "-"
        agree=''
        if w is not None and b is not None:
            same=np.sign(w['mean']-base['WTI'])==np.sign(b['mean']-base['BRENT'])
            agree='YES' if same else ''
        print(f"{r:38s} | {ws:26s} | {bs:26s} | {agree}")

# Save the 3-factor grid for charting
gw=grid(Aw,['CURVE','VOL','POS']); gb=grid(Ab,['CURVE','VOL','POS'])
json.dump({'wti':gw.to_dict('records'),'brent':gb.to_dict('records'),'base':base},
          open(os.path.join(SCRATCH,'regime_results.json'),'w'),indent=2)
print("\nsaved regime_results.json")
