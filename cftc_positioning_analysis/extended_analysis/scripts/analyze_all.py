"""C1-C2 spread, expiry-window, and core positioning->returns for WTI and Brent (Managed Money)."""
import pandas as pd, numpy as np, json, os, warnings
from scipy import stats
warnings.filterwarnings('ignore'); np.random.seed(7); pd.set_option('display.width',210)
ROOT=r"c:/Users/aayush.jhawar/OneDrive - hertshtengroup.com/Desktop/Dashboard_v3"
SCRATCH=os.path.dirname(os.path.abspath(__file__))

def derolled(curve):
    c=curve.sort_values('d').reset_index(drop=True)
    r1=c['c1'].pct_change(); r2=c['c2'].pct_change()
    roll=(r1-r2).abs()>0.015
    r=r1.where(~roll,r2); r.iloc[0]=0.0
    c['adj']=100*(1+r.fillna(0)).cumprod()
    c['rv20']=np.log(c['adj']/c['adj'].shift(1)).rolling(20).std()*np.sqrt(252)*100
    return c

def build_panel(pos, curve):
    curve=derolled(curve)
    P=pos.sort_values('date').copy()
    P['sig']=P['mm_net']
    r=P['sig'].rolling(52,min_periods=52); P['z']=(P['sig']-r.mean())/r.std(ddof=1)
    P['rel']=P['date']+pd.Timedelta(days=3)   # Tue report -> Fri release
    cur=curve.rename(columns={'d':'p0d'})
    m=pd.merge_asof(P.sort_values('rel'),cur[['p0d','adj','c1','c2','c12','rv20']],
                    left_on='rel',right_on='p0d',direction='forward',tolerance=pd.Timedelta('7D'))
    for h in (1,2,4):
        tgt=m['rel']+pd.Timedelta(days=7*h); tmp=m[['rel']].copy(); tmp['t']=tgt
        j=pd.merge_asof(tmp.sort_values('t'),curve.rename(columns={'d':'hd','adj':'hadj'})[['hd','hadj']],
                        left_on='t',right_on='hd',direction='forward',tolerance=pd.Timedelta('10D')).sort_index()
        m[f'h{h}']=j['hadj'].values
    for h in (1,2,4): m[f'fwd_{h}w']=m[f'h{h}']/m['adj']-1
    m['sp12']=m['c1']-m['c2']; m['sp1_12']=m['c1']-m['c12']
    m['chg4']=m['sig'].diff(4)
    return m[m['adj'].notna() & m['z'].notna()].sort_values('date').reset_index(drop=True)

def st(y):
    y=pd.Series(y).dropna(); return f"{y.mean()*100:+5.1f}% (hit {(y>0).mean()*100:3.0f}%, n={len(y)})" if len(y) else "n/a"

def analyze(name, pos, curve):
    A=build_panel(pos,curve)
    print("="*78); print(f"{name}  | panel n={len(A)}  {A['date'].min().date()}..{A['date'].max().date()}")
    unc={h:A[f'fwd_{h}w'].mean() for h in (1,2,4)}
    print(f"baseline fwd: 1w {unc[1]*100:+.2f}%  2w {unc[2]*100:+.2f}%  4w {unc[4]*100:+.2f}%")

    # ---- CORE extremes ----
    print("\n[CORE] extremes -> forward returns")
    A['pl']=A['z']<=A['z'].quantile(.1); A['ph']=A['z']>=A['z'].quantile(.9)
    for lab,fl in [('Z>=+2 long',A['z']>=2),('Top10% long',A['ph']),('Z<=-2 short',A['z']<=-2),('Bot10% short',A['pl'])]:
        print(f"  {lab:14s}: 1w {st(A.loc[fl,'fwd_1w'])}  2w {st(A.loc[fl,'fwd_2w'])}  4w {st(A.loc[fl,'fwd_4w'])}")

    # ---- STALENESS ----
    terc=pd.qcut(A['z'],3,labels=['Low','Mid','High'])
    def rl(mask):
        o=np.zeros(len(mask),int); k=0
        for i,v in enumerate(mask): k=k+1 if v else 0; o[i]=k
        return o
    A['rh']=rl((terc=='High').values); A['rl_']=rl((terc=='Low').values)
    print("[STALENESS] fwd 4wk by duration in regime")
    for nm,col in [('High(crowded long)','rh'),('Low(light/short)','rl_')]:
        f=A[(A[col]>=1)&(A[col]<=1)]; b=A[(A[col]>=2)&(A[col]<=3)]; s=A[A[col]>=4]
        print(f"  {nm:20s}: fresh {st(f['fwd_4w'])}  build {st(b['fwd_4w'])}  stale {st(s['fwd_4w'])}")

    # ---- SPREAD (C1-C2) ----
    print("[SPREAD] C1-C2 (backwardation>0). corr(z, spread)=%.2f  corr(z, C1-C12)=%.2f"
          % (A['z'].corr(A['sp12']), A['z'].corr(A['sp1_12'])))
    bk=A['sp12']>0; ct=A['sp12']<=0
    print(f"  backwardation weeks n={bk.sum()} fwd4w {st(A.loc[bk,'fwd_4w'])} | contango n={ct.sum()} fwd4w {st(A.loc[ct,'fwd_4w'])}")
    # spread x position (median splits)
    hz=A['z']>A['z'].median()
    print("  spread x position (fwd 4wk):")
    print(f"    backwardation + light : {st(A.loc[bk&~hz,'fwd_4w'])}   backwardation + crowded: {st(A.loc[bk&hz,'fwd_4w'])}")
    print(f"    contango      + light : {st(A.loc[ct&~hz,'fwd_4w'])}   contango      + crowded: {st(A.loc[ct&hz,'fwd_4w'])}")
    # does spread predict returns on its own?
    A['spterc']=pd.qcut(A['sp12'],3,labels=['contango','flat','backwardation'])
    for t in ['contango','flat','backwardation']:
        print(f"    spread tercile {t:14s}: fwd4w {st(A.loc[A['spterc']==t,'fwd_4w'])}")
    return A

# WTI
wpos=pd.read_csv(os.path.join(ROOT,'Data/cftc_managed_money_wti_2016_2026.csv')); wpos['date']=pd.to_datetime(wpos['date'])
wcur=pd.read_parquet(os.path.join(SCRATCH,'wti_curve_daily.parquet'))
Aw=analyze("WTI (Managed Money, local 2021-2026)", wpos, wcur)
# Brent
bpos=pd.read_csv(os.path.join(ROOT,'Data/brent_managed_money_cftc.csv')); bpos['date']=pd.to_datetime(bpos['date'])
bcur=pd.read_parquet(os.path.join(SCRATCH,'brent_curve_daily.parquet'))
Ab=analyze("BRENT (CFTC Brent-Last-Day MM + ICE price, 2016-2026)", bpos, bcur)
Aw.to_parquet(os.path.join(SCRATCH,'panel_wti_full.parquet')); Ab.to_parquet(os.path.join(SCRATCH,'panel_brent_full.parquet'))
print("\nsaved panels")
