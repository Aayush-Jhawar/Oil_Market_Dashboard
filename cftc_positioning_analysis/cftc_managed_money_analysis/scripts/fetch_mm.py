"""Pull real CFTC Managed Money + Other Reportables net for WTI (code 067651), full history."""
import urllib.request, urllib.parse, json, pandas as pd, os
BASE='https://publicreporting.cftc.gov/resource/72hh-3qpy.json'
params={
 '$select':'report_date_as_yyyy_mm_dd,m_money_positions_long_all,m_money_positions_short_all,'
           'other_rept_positions_long,other_rept_positions_short,open_interest_all',
 '$where':"cftc_contract_market_code='067651' AND report_date_as_yyyy_mm_dd >= '2015-12-01T00:00:00.000'",
 '$order':'report_date_as_yyyy_mm_dd',
 '$limit':'5000',
}
url=BASE+'?'+urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
req=urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
data=json.loads(urllib.request.urlopen(req, timeout=60).read().decode())
df=pd.DataFrame(data)
for c in df.columns:
    if c!='report_date_as_yyyy_mm_dd': df[c]=pd.to_numeric(df[c])
df['date']=pd.to_datetime(df['report_date_as_yyyy_mm_dd']).dt.date
df['mm_net']=df['m_money_positions_long_all']-df['m_money_positions_short_all']
df['or_net']=df['other_rept_positions_long']-df['other_rept_positions_short']
print('ROWS', len(df), '| range', df['date'].min(), '->', df['date'].max())
print('MM net range:', int(df['mm_net'].min()), 'to', int(df['mm_net'].max()))
print('OR net range:', int(df['or_net'].min()), 'to', int(df['or_net'].max()))
ROOT=r"c:/Users/aayush.jhawar/OneDrive - hertshtengroup.com/Desktop/Dashboard_v3"
out=os.path.join(ROOT,'Data','cftc_managed_money_wti_2016_2026.csv')
df[['date','mm_net','or_net','m_money_positions_long_all','m_money_positions_short_all','open_interest_all']].to_csv(out,index=False)
print('saved', out)

# cross-check vs the local OR file on the STEP-0 dates
loc=pd.read_excel(os.path.join(ROOT,'Data','CFTC 2016-2026 CL.xlsx')).drop_duplicates()
loc['date']=pd.to_datetime(loc['date']).dt.date
mrg=df.merge(loc[['date','actual']], on='date', how='inner')
print('\nProof: file actual vs fetched OR net vs fetched MM net (5 dates)')
print('date        file_actual  fetched_OR  fetched_MM')
for d in ['2016-01-05','2018-01-23','2020-04-21','2022-03-08','2026-06-16']:
    import datetime as dt
    dd=dt.date.fromisoformat(d); r=mrg[mrg['date']==dd]
    if len(r): print(f"{d}  {int(r['actual'].iloc[0]):>10}  {int(r['or_net'].iloc[0]):>10}  {int(r['mm_net'].iloc[0]):>10}")
match=(mrg['actual'].round()==mrg['or_net'].round()).mean()
print(f"\nFile == Other Reportables on {match*100:.1f}% of {len(mrg)} overlapping weeks")
