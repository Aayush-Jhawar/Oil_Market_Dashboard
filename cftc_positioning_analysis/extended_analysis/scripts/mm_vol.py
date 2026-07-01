"""Volatility compression analysis for the Managed Money study (2021-2026). Analysis only."""
import pandas as pd, numpy as np, os, warnings
from scipy import stats
warnings.filterwarnings('ignore'); np.random.seed(7); pd.set_option('display.width',200)
SCRATCH=os.path.dirname(os.path.abspath(__file__))
A=pd.read_parquet(os.path.join(SCRATCH,"mm_deep_window.parquet")).sort_values('date').reset_index(drop=True)
wti=pd.read_parquet(os.path.join(SCRATCH,"wti_daily.parquet")).sort_values('d').reset_index(drop=True)
wti['lr']=np.log(wti['adj']/wti['adj'].shift(1))
# FORWARD 20-trading-day realized vol (outcome, look-ahead OK as it's what we predict)
wti['fwd_rv20']=(wti['lr'].rolling(20).std()*np.sqrt(252)*100).shift(-20)
A['p0_date']=pd.to_datetime(A['p0_date'])
A=pd.merge_asof(A.sort_values('p0_date'), wti[['d','fwd_rv20']].rename(columns={'d':'p0_date'}),
                on='p0_date', direction='backward').sort_values('date').reset_index(drop=True)

# compression measures (all known at decision time)
A['rv']=A['rv20']
A['rv_terc']=pd.qcut(A['rv'],3,labels=['Low(compressed)','Mid','High'])
A['rv_chg4']=A['rv']-A['rv'].shift(4)               # falling vol = compressing
A['compressing']=A['rv_chg4']<0
A['rv_min12']=A['rv'].rolling(12).min()
A['squeeze']=A['rv']<=A['rv_min12']*1.02            # at/near a 12-week low
A['vol_ratio']=A['fwd_rv20']/A['rv']                # >1 => vol expanded after
A['absret4']=A['fwd_4w'].abs()

print(f"n={len(A)}  rv terciles cutoffs ~ {A['rv'].quantile([.33,.66]).round(1).tolist()} (annualized %)")

# 1) MEAN REVERSION: does compressed vol expand?
print("\n[1] VOL MEAN-REVERSION  (current vol -> next 4wk vol)")
for t in ['Low(compressed)','Mid','High']:
    s=A[A['rv_terc']==t]
    print(f"  {t:16s}: now {s['rv'].mean():5.1f}%  -> next-4wk {s['fwd_rv20'].mean():5.1f}%   ratio {s['vol_ratio'].mean():.2f}  (n={len(s)})")

# 2) MOVE SIZE: does compression precede bigger moves?
print("\n[2] SUBSEQUENT 4wk ABSOLUTE move (size, ignoring direction)")
for t in ['Low(compressed)','Mid','High']:
    s=A[A['rv_terc']==t]; print(f"  {t:16s}: |4wk move| {s['absret4'].mean()*100:4.1f}%   (n={len(s)})")
print(f"  compressing(vol falling): |4wk move| {A.loc[A['compressing'],'absret4'].mean()*100:4.1f}%  vs rising {A.loc[~A['compressing'],'absret4'].mean()*100:4.1f}%")
print(f"  squeeze(12wk low):        |4wk move| {A.loc[A['squeeze'],'absret4'].mean()*100:4.1f}%  vs not {A.loc[~A['squeeze'],'absret4'].mean()*100:4.1f}%")

# 3) DIRECTION: does compression sharpen the positioning signal?
def stat(s):
    y=s['fwd_4w'].dropna();
    return (f"{y.mean()*100:+5.1f}% (hit {(y>0).mean()*100:3.0f}%, n={len(y)})") if len(y) else "n/a"
print("\n[3] DIRECTION: forward 4wk return, COMPRESSED (low-vol tercile) split by positioning")
comp=A[A['rv_terc']=='Low(compressed)']
print(f"  compressed + Low position : {stat(comp[comp['POS']=='Low position'])}")
print(f"  compressed + High position: {stat(comp[comp['POS']=='High position'])}")
print(f"  (for contrast) HIGH-vol + Low position : {stat(A[(A['rv_terc']=='High')&(A['POS']=='Low position')])}")
print(f"  (for contrast) HIGH-vol + High position: {stat(A[(A['rv_terc']=='High')&(A['POS']=='High position')])}")

print("\n[4] DIRECTION by 'compressing' (vol falling) x positioning")
for cf,lab in [(True,'falling/compressing'),(False,'rising')]:
    sub=A[A['compressing']==cf]
    print(f"  {lab:20s} + Low pos : {stat(sub[sub['POS']=='Low position'])}   + High pos: {stat(sub[sub['POS']=='High position'])}")

print("\n[5] SQUEEZE (vol at 12wk low) x positioning")
sq=A[A['squeeze']]
print(f"  squeeze overall: {stat(sq)}")
print(f"  squeeze + Low pos : {stat(sq[sq['POS']=='Low position'])}    squeeze + High pos: {stat(sq[sq['POS']=='High position'])}")

print("\n[6] COMPRESSED + position staleness (does calm + stale sharpen reversal?)")
terc=pd.qcut(A['z'],3,labels=['Low','Mid','High'])
def runlen(m):
    o=np.zeros(len(m),int); r=0
    for i,v in enumerate(m): r=r+1 if v else 0; o[i]=r
    return o
A['rh']=runlen((terc=='High').values); A['rl']=runlen((terc=='Low').values)
comp=A[A['rv_terc']=='Low(compressed)']   # re-slice now that rh/rl exist
print(f"  compressed + crowded-long FRESH(1wk):  {stat(comp[comp['rh']==1])}")
print(f"  compressed + crowded-long STALE(4+):   {stat(comp[comp['rh']>=4])}")
print(f"  compressed + light FRESH(1wk):         {stat(comp[comp['rl']==1])}")
print(f"  compressed + light STALE(4+):          {stat(comp[comp['rl']>=4])}")
