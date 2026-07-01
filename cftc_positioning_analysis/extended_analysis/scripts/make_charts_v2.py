"""Structural charts: concentration timeline (crowding) + OI x price regime."""
import pandas as pd, numpy as np, os, warnings
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
warnings.filterwarnings('ignore')
ROOT=r"c:/Users/aayush.jhawar/OneDrive - hertshtengroup.com/Desktop/Dashboard_v3"
SCRATCH=os.path.dirname(os.path.abspath(__file__))
OUT=os.path.join(ROOT,"cftc_positioning_analysis","extended_analysis","charts")
NAVY='#16324f'; GOLD='#c8862a'; RED='#c0392b'; BLUE='#2c6fbb'; GREEN='#1e8b54'; GREY='#8a949c'; INK='#1a1a1a'
plt.rcParams.update({'font.size':12,'font.family':'DejaVu Sans','axes.edgecolor':'#cfd6dc','axes.linewidth':1.0,
    'axes.grid':True,'grid.color':'#eef2f5','figure.dpi':150,'savefig.dpi':150,'axes.spines.top':False,'axes.spines.right':False})

# ---- CONCENTRATION (WTI MM, per-firm book size) ----
R=pd.read_csv(os.path.join(ROOT,'Data/cftc_mm_rich_wti.csv')); R['date']=pd.to_datetime(R['date'])
R=R[R['date']>=pd.Timestamp('2016-01-01')].sort_values('date')
R['long_pf']=R['m_money_positions_long_all']/R['traders_m_money_long_all']
R['short_pf']=R['m_money_positions_short_all']/R['traders_m_money_short_all']
fig,ax=plt.subplots(figsize=(11,5.4))
ax.plot(R['date'],R['long_pf'],color=GOLD,lw=1.8,label='LONG side (contracts per firm)')
ax.plot(R['date'],R['short_pf'],color=RED,lw=1.8,label='SHORT side (contracts per firm)')
il=R['long_pf'].idxmax(); ish=R['short_pf'].idxmax()
ax.scatter([R.loc[il,'date']],[R.loc[il,'long_pf']],color=GOLD,s=60,zorder=5)
ax.annotate(f"longs most crowded\nsummer 2020 ({R.loc[il,'long_pf']:.0f}/firm)",(R.loc[il,'date'],R.loc[il,'long_pf']),
            xytext=(R['date'].quantile(0.12),7300),fontsize=9,color='#7a5a1e',ha='center',
            arrowprops=dict(arrowstyle='->',color=GOLD,lw=1.3))
ax.scatter([R.loc[ish,'date']],[R.loc[ish,'short_pf']],color=RED,s=60,zorder=5)
ax.annotate(f"shorts most crowded NOW\n2026 ({R.loc[ish,'short_pf']:.0f}/firm) = squeeze risk",(R.loc[ish,'date'],R.loc[ish,'short_pf']),
            xytext=(R['date'].quantile(0.45),R['short_pf'].max()+300),fontsize=9,color=RED,ha='center',
            arrowprops=dict(arrowstyle='->',color=RED,lw=1.3))
ax.set_ylabel('Contracts per firm (crowding)'); ax.legend(fontsize=10,frameon=False,loc='upper right')
ax.set_title('Crowding gauge: Managed Money book size per firm (WTI)',fontsize=14,fontweight='bold',color=NAVY,pad=24)
ax.text(0.5,1.03,'Net positioning hides this. The short side is now the most concentrated in the sample: a small, squeeze-prone group.',
        transform=ax.transAxes,ha='center',fontsize=10,color='#555',style='italic')
fig.tight_layout(); fig.savefig(os.path.join(OUT,'chart_concentration.png'),bbox_inches='tight'); plt.close(fig)

# ---- OI x PRICE REGIME (WTI + Brent) ----
def regime(panelf,richf):
    A=pd.read_parquet(os.path.join(SCRATCH,panelf)); A['date']=pd.to_datetime(A['date'])
    Rr=pd.read_csv(os.path.join(ROOT,richf)); Rr['date']=pd.to_datetime(Rr['date'])
    m=A.merge(Rr[['date','open_interest_all']],on='date',how='left',suffixes=('','_r')).sort_values('date')
    oi=m['open_interest_all'] if 'open_interest_all' in m.columns else m['open_interest_all_r']
    m['dOI']=oi.diff(); m['cret']=m['adj'].pct_change()
    out={}
    for lab,c in [('Price+ OI+\n(new longs)',(m['cret']>0)&(m['dOI']>0)),('Price+ OI-\n(short cover)',(m['cret']>0)&(m['dOI']<0)),
                  ('Price- OI+\n(new shorts)',(m['cret']<0)&(m['dOI']>0)),('Price- OI-\n(liquidation)',(m['cret']<0)&(m['dOI']<0))]:
        y=m.loc[c,'fwd_4w'].dropna(); out[lab]=(y.mean()*100,(y>0).mean()*100,len(y))
    return out
rw=regime('panel_wti_full.parquet','Data/cftc_mm_rich_wti.csv'); rb=regime('panel_brent_full.parquet','Data/cftc_mm_rich_brent.csv')
labs=list(rw.keys())
fig,ax=plt.subplots(figsize=(10.5,5.4)); x=np.arange(4); w=0.38
for i,(nm,d,col) in enumerate([('WTI',rw,GOLD),('Brent',rb,BLUE)]):
    vals=[d[l][0] for l in labs]; hits=[d[l][1] for l in labs]
    pos=x+(i-0.5)*w; ax.bar(pos,vals,w,color=col,label=nm,alpha=0.9)
    for p,v,h in zip(pos,vals,hits): ax.text(p,v+(0.1 if v>=0 else -0.3),f'{v:+.1f}%\n{h:.0f}%',ha='center',fontsize=8.5,fontweight='bold')
ax.axhline(0,color='#333',lw=0.9); ax.set_xticks(x); ax.set_xticklabels(labs,fontsize=10)
ax.set_ylabel('Next 4-week return (%)'); ax.legend(fontsize=11,frameon=False,loc='upper right')
ax.set_title('Open interest confirms trend quality (WTI): price up on rising OI is the best regime',fontsize=13.5,fontweight='bold',color=NAVY,pad=24)
ax.text(0.5,1.03,'New money entering an uptrend (price+ OI+) continues best on WTI. Weaker/mixed on Brent, so use as WTI colour.',transform=ax.transAxes,ha='center',fontsize=10,color='#555',style='italic')
fig.tight_layout(); fig.savefig(os.path.join(OUT,'chart_oi_regime.png'),bbox_inches='tight'); plt.close(fig)
print('v2 charts written:', [f for f in os.listdir(OUT) if f in ('chart_concentration.png','chart_oi_regime.png')])
