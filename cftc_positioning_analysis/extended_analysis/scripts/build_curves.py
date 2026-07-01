"""Build WTI & Brent forward-curve daily series (C1, C2, C12) for spread + expiry analysis."""
import pandas as pd, numpy as np, os
ROOT=r"c:/Users/aayush.jhawar/OneDrive - hertshtengroup.com/Desktop/Dashboard_v3"
SCRATCH=os.path.dirname(os.path.abspath(__file__))

# --- WTI curve from local 1-min (2021-2026) ---
cols=['timestamp','c1||weighted_mid','c2||weighted_mid','c12||weighted_mid']
w=pd.read_csv(os.path.join(ROOT,'Data/CL_data.csv'),skiprows=1,usecols=cols)
w['timestamp']=pd.to_datetime(w['timestamp'],utc=True)
w['d']=w['timestamp'].dt.tz_convert('America/New_York').dt.normalize().dt.tz_localize(None)
w=w.dropna(subset=['c1||weighted_mid']).sort_values('timestamp')
wd=w.groupby('d').agg(c1=('c1||weighted_mid','last'),c2=('c2||weighted_mid','last'),
                      c12=('c12||weighted_mid','last')).reset_index()
wd.to_parquet(os.path.join(SCRATCH,'wti_curve_daily.parquet'))
print(f'WTI curve: {wd["d"].min().date()}..{wd["d"].max().date()} n={len(wd)}')
print(f'  C1-C2 spread mean {(wd["c1"]-wd["c2"]).mean():+.2f}  C1-C12 mean {(wd["c1"]-wd["c12"]).mean():+.2f}')

# --- Brent curve from local ICE Brent settle CSV (2016-2026), robust DD-MM-YY parse ---
raw=pd.read_csv(os.path.join(ROOT,'Data/LCOSettle 2.csv'),header=None,skiprows=2)
def col(k): return pd.to_numeric(raw[2*(k-1)+1],errors='coerce')  # settle of contract k
bd=pd.DataFrame({'d':pd.to_datetime(raw[0],format='%d-%m-%y',errors='coerce'),
                 'c1':col(1),'c2':col(2),'c12':col(12)}).dropna(subset=['d','c1']).sort_values('d').reset_index(drop=True)
bd=bd[bd['d']<=pd.Timestamp('2026-07-01')]  # guard against any misparsed future dates
bd.to_parquet(os.path.join(SCRATCH,'brent_curve_daily.parquet'))
print(f'Brent curve: {bd["d"].min().date()}..{bd["d"].max().date()} n={len(bd)}')
print(f'  C1-C2 spread mean {(bd["c1"]-bd["c2"]).mean():+.2f}  C1-C12 mean {(bd["c1"]-bd["c12"]).mean():+.2f}')
print(bd.head(2).to_string(index=False)); print(bd.tail(2).to_string(index=False))
