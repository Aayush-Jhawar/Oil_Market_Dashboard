"""Expiry-window analysis: contract expiry = 3 business days before the 25th.
Window [expiry-7, expiry]; relate the pre-expiry price move to CFTC positioning as of expiry-7."""
import pandas as pd, numpy as np, os, warnings
from scipy import stats
warnings.filterwarnings('ignore'); pd.set_option('display.width',200)
ROOT=r"c:/Users/aayush.jhawar/OneDrive - hertshtengroup.com/Desktop/Dashboard_v3"
SCRATCH=os.path.dirname(os.path.abspath(__file__))

def derolled(curve):
    c=curve.sort_values('d').reset_index(drop=True)
    r1=c['c1'].pct_change(); r2=c['c2'].pct_change(); roll=(r1-r2).abs()>0.015
    r=r1.where(~roll,r2); r.iloc[0]=0.0
    c['adj']=100*(1+r.fillna(0)).cumprod(); return c[['d','adj']]

def expiries(dmin,dmax):
    out=[]
    for y in range(dmin.year,dmax.year+1):
        for m in range(1,13):
            E=np.busday_offset(f'{y}-{m:02d}-25',-3,roll='backward')
            E=pd.Timestamp(E)
            if dmin<=E<=dmax: out.append(E)
    return pd.DataFrame({'E':out})

NS=lambda s: pd.to_datetime(s).astype('datetime64[ns]')
def run(name,pos,curve):
    adj=derolled(curve); adj['d']=NS(adj['d']); dmin,dmax=adj['d'].min(),adj['d'].max()
    P=pos.sort_values('date').copy(); P['date']=NS(P['date']); P['sig']=P['mm_net']
    r=P['sig'].rolling(52,min_periods=52); P['z']=(P['sig']-r.mean())/r.std(ddof=1)
    ex=expiries(dmin,dmax); ex['E']=NS(ex['E'])
    ex['E7']=NS(ex['E']-pd.Timedelta(days=7)); ex['Ep7']=NS(ex['E']+pd.Timedelta(days=7))
    def px(dates):
        t=pd.DataFrame({'x':NS(dates)}).sort_values('x')
        j=pd.merge_asof(t,adj.rename(columns={'d':'x','adj':'a'}),on='x',direction='backward')
        return j.sort_index()['a'].values
    ex=ex.sort_values('E').reset_index(drop=True)
    ex['aE']=px(ex['E']); ex['a7']=px(ex['E7']); ex['ap7']=px(ex['Ep7'])
    ex['pre']=ex['aE']/ex['a7']-1        # expiry-7 -> expiry (into expiry)
    ex['post']=ex['ap7']/ex['aE']-1      # expiry -> expiry+7
    # positioning z as of E-7
    j=pd.merge_asof(ex[['E7']].sort_values('E7'),P[['date','z']].rename(columns={'date':'E7'}),
                    on='E7',direction='backward').sort_index()
    ex['z']=j['z'].values
    ex=ex.dropna(subset=['pre'])
    # baseline: any 7-cal-day move across the sample
    a=adj.dropna().reset_index(drop=True)
    base7=(a['adj']/a['adj'].shift(5)-1).dropna()   # ~5 trading days ~ 7 cal
    print("="*70); print(f"{name}: {len(ex)} monthly expiries {ex['E'].min().date()}..{ex['E'].max().date()}")
    t=stats.ttest_1samp(ex['pre'],0)
    print(f"  PRE-expiry (E-7->E) return: mean {ex['pre'].mean()*100:+.2f}%  median {ex['pre'].median()*100:+.2f}%  "
          f"hit+ {(ex['pre']>0).mean()*100:.0f}%  t={t.statistic:.2f} p={t.pvalue:.3f}")
    print(f"  baseline any ~7d move:     mean {base7.mean()*100:+.2f}%  (so pre-expiry vs baseline diff "
          f"{ (ex['pre'].mean()-base7.mean())*100:+.2f}%)")
    print(f"  POST-expiry (E->E+7):      mean {ex['post'].mean()*100:+.2f}%  hit+ {(ex['post']>0).mean()*100:.0f}%")
    # conditioned on positioning as of E-7
    e=ex.dropna(subset=['z'])
    lo=e[e['z']<=e['z'].quantile(.5)]; hi=e[e['z']>e['z'].quantile(.5)]
    print(f"  PRE-expiry by positioning at E-7:  light {lo['pre'].mean()*100:+.2f}% (n={len(lo)})   "
          f"crowded {hi['pre'].mean()*100:+.2f}% (n={len(hi)})")
    ext_hi=e[e['z']>=2]; ext_lo=e[e['z']<=-2]
    print(f"     crowded-long (z>=2) pre: {ext_hi['pre'].mean()*100:+.2f}% (n={len(ext_hi)})   "
          f"light (z<=-2) pre: {ext_lo['pre'].mean()*100:+.2f}% (n={len(ext_lo)})")
    return ex

wpos=pd.read_csv(os.path.join(ROOT,'Data/cftc_managed_money_wti_2016_2026.csv')); wpos['date']=pd.to_datetime(wpos['date'])
wcur=pd.read_parquet(os.path.join(SCRATCH,'wti_curve_daily.parquet'))
run("WTI expiry", wpos, wcur)
bpos=pd.read_csv(os.path.join(ROOT,'Data/brent_managed_money_cftc.csv')); bpos['date']=pd.to_datetime(bpos['date'])
bcur=pd.read_parquet(os.path.join(SCRATCH,'brent_curve_daily.parquet'))
run("BRENT expiry (WTI-style rule; Brent's real expiry differs)", bpos, bcur)
