"""Friend-inspired structural + category analysis, on MY data (WTI 2021-26, Brent 2016-26). Not copied."""
import pandas as pd, numpy as np, os, warnings
from scipy import stats
warnings.filterwarnings('ignore'); pd.set_option('display.width',200)
ROOT=r"c:/Users/aayush.jhawar/OneDrive - hertshtengroup.com/Desktop/Dashboard_v3"
SCRATCH=os.path.dirname(os.path.abspath(__file__))
def load(name,panelf,richf):
    A=pd.read_parquet(os.path.join(SCRATCH,panelf)); A['date']=pd.to_datetime(A['date'])
    R=pd.read_csv(os.path.join(ROOT,richf)); R['date']=pd.to_datetime(R['date'])
    R['mm_net']=R['m_money_positions_long_all']-R['m_money_positions_short_all']
    R['or_net']=R['other_rept_positions_long']-R['other_rept_positions_short']
    newcols=['date']+[c for c in R.columns if c not in A.columns and c!='report_date_as_yyyy_mm_dd']
    m=A.merge(R[newcols],on='date',how='left').sort_values('date').reset_index(drop=True)
    if 'mm_net' not in m.columns: m['mm_net']=m['sig']
    m['cret']=m['adj'].pct_change()      # contemporaneous weekly return
    m['dnet']=m['mm_net'].diff(); m['dOI']=m['open_interest_all'].diff()
    return m,R
def sp(a,b):
    s=pd.DataFrame({'a':a,'b':b}).dropna(); r,p=stats.spearmanr(s['a'],s['b']); return r,p

for name,pf,rf in [('WTI (2021-26)','panel_wti_full.parquet','Data/cftc_mm_rich_wti.csv'),
                   ('BRENT (2016-26)','panel_brent_full.parquet','Data/cftc_mm_rich_brent.csv')]:
    m,R=load(name,pf,rf)
    print("="*80); print(name,'| priced weeks',m['fwd_4w'].notna().sum())
    # 1) MM momentum vs OR contrarian
    r0,p0=stats.pearsonr(*[m[['dnet','cret']].dropna()[c] for c in ['dnet','cret']])
    r1,p1=stats.pearsonr(*[m[['dnet','fwd_1w']].dropna()[c] for c in ['dnet','fwd_1w']])
    print(f"[MM behaviour] corr(dNet, same-week ret)={r0:+.3f} (p={p0:.3f})  corr(dNet, +1wk ret)={r1:+.3f} (p={p1:.3f})  [+ = momentum/coincident]")
    rmm,pmm=sp(m['mm_net'],m['fwd_4w']); ror,por=sp(m['or_net'],m['fwd_4w'])
    print(f"[Category] Spearman(net, fwd4w): Managed Money {rmm:+.3f} (p={pmm:.3f})  |  Other Reportables {ror:+.3f} (p={por:.3f})")
    # crowded-long extreme median contrast
    def top_med(col):
        q=m[col].quantile(.9); y=m.loc[m[col]>=q,'fwd_4w'].dropna(); return y.median()*100,(y>0).mean()*100,len(y)
    mmm=top_med('mm_net'); mor=top_med('or_net')
    print(f"   crowded-long (top decile) -> 4wk median: MM {mmm[0]:+.1f}% ({mmm[1]:.0f}% up,n={mmm[2]})  |  OR {mor[0]:+.1f}% ({mor[1]:.0f}% up,n={mor[2]})")
    # 2) OI x price regime
    print("[OI x price regime] fwd 4wk (baseline %+.1f%%)"%(m['fwd_4w'].mean()*100))
    for lab,cond in [('Price+ OI+ (new longs)',(m['cret']>0)&(m['dOI']>0)),
                     ('Price+ OI- (short cover)',(m['cret']>0)&(m['dOI']<0)),
                     ('Price- OI+ (new shorts)',(m['cret']<0)&(m['dOI']>0)),
                     ('Price- OI- (liquidation)',(m['cret']<0)&(m['dOI']<0))]:
        y=m.loc[cond,'fwd_4w'].dropna()
        print(f"   {lab:26s}: mean {y.mean()*100:+5.1f}%  med {y.median()*100:+5.1f}%  hit {(y>0).mean()*100:3.0f}%  n={len(y)}")
    # 3) flow decomposition: conviction (longs added) vs covering (shorts cut)
    conv=m[(m['change_in_m_money_long_all']>0)&(m['dnet']>0)]; cov=m[(m['change_in_m_money_short_all']<0)&(m['dnet']>0)]
    print(f"[Flow] net rose via NEW LONGS: 4wk mean {conv['fwd_4w'].mean()*100:+.1f}% med {conv['fwd_4w'].median()*100:+.1f}% (n={len(conv)})  | "
          f"via SHORT COVERING: mean {cov['fwd_4w'].mean()*100:+.1f}% med {cov['fwd_4w'].median()*100:+.1f}% (n={len(cov)})")
    # 4) concentration/breadth (full history, no price)
    R=R.sort_values('date')
    R['long_pf']=R['m_money_positions_long_all']/R['traders_m_money_long_all']
    R['short_pf']=R['m_money_positions_short_all']/R['traders_m_money_short_all']
    lastp=R.iloc[-1]
    print(f"[Concentration] per-firm LONG now {lastp['long_pf']:.0f} (max {R['long_pf'].max():.0f} on {R.loc[R['long_pf'].idxmax(),'date'].date()}) | "
          f"per-firm SHORT now {lastp['short_pf']:.0f} (max {R['short_pf'].max():.0f} on {R.loc[R['short_pf'].idxmax(),'date'].date()})")
    def si(v): return int(v) if pd.notna(v) else -1
    print(f"[Breadth] firms long now {si(lastp['traders_m_money_long_all'])} vs short {si(lastp['traders_m_money_short_all'])}; "
          f"avg L/S firms {R['traders_m_money_long_all'].mean():.0f}/{R['traders_m_money_short_all'].mean():.0f}")
