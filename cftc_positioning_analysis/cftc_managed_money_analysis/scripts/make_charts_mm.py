"""Managed Money charts -> project/cftc_managed_money_analysis/charts/"""
import pandas as pd, numpy as np, json, os, warnings
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.patches import Patch
warnings.filterwarnings('ignore'); np.random.seed(7)
SCRATCH=os.path.dirname(os.path.abspath(__file__))
ROOT=r"c:/Users/aayush.jhawar/OneDrive - hertshtengroup.com/Desktop/Dashboard_v3"
OUT=os.path.join(ROOT,"cftc_positioning_analysis", "cftc_managed_money_analysis","charts"); os.makedirs(OUT,exist_ok=True)
A=pd.read_parquet(os.path.join(SCRATCH,"mm_window.parquet")).sort_values('date').reset_index(drop=True)
res=json.load(open(os.path.join(SCRATCH,"mm_results.json")))
NAVY='#1f3b57'; RED='#c0392b'; GREEN='#1e8449'; GREY='#7f8c8d'; GOLD='#b9770e'
plt.rcParams.update({'font.size':11,'axes.edgecolor':'#444','axes.linewidth':0.8,'figure.dpi':140,'savefig.dpi':140})

def ci(y,fl,h,n=4000):
    s=pd.DataFrame({'y':y,'f':fl.astype(bool)}).dropna().reset_index(drop=True)
    yv=s['y'].values; fv=s['f'].values; N=len(yv); L=max(h,3); nb=int(np.ceil(N/L)); o=np.empty(n)
    for b in range(n):
        st=np.random.randint(0,N,nb); idx=(st[:,None]+np.arange(L)[None,:]).ravel()%N; idx=idx[:N]
        o[b]=yv[idx][fv[idx]].mean() if fv[idx].sum()>0 else np.nan
    return np.nanpercentile(o,2.5),np.nanpercentile(o,97.5)

# CHART 1: MM net vs WTI with extreme bands
fig,ax=plt.subplots(figsize=(11,5.2))
ax.plot(A['date'],A['sig']/1000,color=NAVY,lw=1.6); ax.set_ylabel('Managed Money net (000s contracts)',color=NAVY)
ax.tick_params(axis='y',labelcolor=NAVY); ax.axhline(0,color=NAVY,lw=0.6,ls=':')
ax2=ax.twinx(); ax2.plot(A['date'],A['p0_raw'],color=GOLD,lw=1.4,alpha=0.9); ax2.set_ylabel('WTI front-month ($/bbl)',color=GOLD); ax2.tick_params(axis='y',labelcolor=GOLD)
for _,r in A[A['ext_long']].iterrows(): ax.axvspan(r['date']-pd.Timedelta('3D'),r['date']+pd.Timedelta('3D'),color=RED,alpha=0.20,zorder=0)
for _,r in A[A['ext_short']].iterrows(): ax.axvspan(r['date']-pd.Timedelta('3D'),r['date']+pd.Timedelta('3D'),color=GREEN,alpha=0.18,zorder=0)
ax.set_title('Managed Money NET positioning vs WTI, 2021-2026   (shaded: |rolling 52w Z| >= 2)',fontsize=12.5,fontweight='bold')
leg=[Patch(color=NAVY,label='MM net (left)'),Patch(color=GOLD,label='WTI (right)'),
     Patch(color=RED,alpha=0.35,label='Extreme LONG (only 6 wks / 2 episodes)'),Patch(color=GREEN,alpha=0.3,label='Extreme SHORT (27 wks / 11 ep)')]
ax.legend(handles=leg,loc='upper center',ncol=4,fontsize=8.5,frameon=False,bbox_to_anchor=(0.5,-0.08))
ax.text(0.005,0.97,'Real CFTC Managed Money (NOT the supplied file, which is Other Reportables). WTI roll-adj front-month NYMEX CL.',transform=ax.transAxes,fontsize=8,color=GREY,va='top')
fig.tight_layout(); fig.savefig(os.path.join(OUT,'mm_chart1_position_vs_wti.png'),bbox_inches='tight'); plt.close(fig)

# CHART 2: forward returns by bucket
HOR=[1,2,4]; buckets=[('Extreme LONG (Z>=+2)','ext_long',RED),('Extreme SHORT (Z<=-2)','ext_short',GREEN),('Unconditional','uncond',GREY)]
fig,ax=plt.subplots(figsize=(10.5,5.6)); x=np.arange(len(HOR)); w=0.26
for i,(lab,key,col) in enumerate(buckets):
    means=[];los=[];his=[];meds=[]
    for h in HOR:
        y=A[f'fwd_{h}w']
        fl=pd.Series(True,index=A.index) if key=='uncond' else A[key]
        sub=y[fl].dropna(); means.append(sub.mean()*100); meds.append(sub.median()*100)
        lo,hi=ci(y,fl,h); los.append(means[-1]-lo*100); his.append(hi*100-means[-1])
    pos=x+(i-1)*w
    ax.bar(pos,means,w,color=col,alpha=0.85,label=lab,yerr=[los,his],capsize=4,error_kw=dict(lw=1.1,ecolor='#333'))
    ax.scatter(pos,meds,marker='D',s=34,color='white',edgecolor='#222',zorder=5)
    for p,mn in zip(pos,means): ax.text(p,mn+(0.2 if mn>=0 else -0.5),f'{mn:.1f}',ha='center',fontsize=8.5,fontweight='bold')
ax.axhline(0,color='#222',lw=0.8); ax.set_xticks(x); ax.set_xticklabels([f'{h} week' for h in HOR]); ax.set_ylabel('Forward WTI return (%)')
ax.set_title('Forward WTI return after extreme Managed Money positioning\nbars = mean (95% block-bootstrap CI), white diamond = median',fontsize=12.5,fontweight='bold')
ax.legend(loc='lower left',fontsize=9.5,frameon=False)
ax.text(0.005,-0.12,'Window 2021-2026. Extreme LONG rests on only 6 weeks / 2 episodes, so its bars are fragile despite the low p-value.',transform=ax.transAxes,fontsize=8,color=GREY)
fig.tight_layout(); fig.savefig(os.path.join(OUT,'mm_chart2_forward_returns.png'),bbox_inches='tight'); plt.close(fig)

# CHART 3: flow / capitulation (MM = momentum, opposite of OR)
A['chg4']=A['sig'].diff(4); F=A.dropna(subset=['chg4']).copy(); F['dec']=pd.qcut(F['chg4'],10,labels=False,duplicates='drop'); mx=F['dec'].max()
groups=[('Fastest UNWIND\n(capitulation)',F['dec']==0,RED),('Neutral',F['dec'].isin([4,5]),GREY),('Fastest BUILD',F['dec']==mx,GREEN)]
fig,ax=plt.subplots(figsize=(9.6,5.4)); x=np.arange(len(HOR)); w=0.26
for i,(lab,fl,col) in enumerate(groups):
    means=[F.loc[fl,f'fwd_{h}w'].mean()*100 for h in HOR]; pos=x+(i-1)*w
    ax.bar(pos,means,w,color=col,alpha=0.88,label=lab.replace('\n',' '))
    for p,mn in zip(pos,means): ax.text(p,mn+0.12 if mn>=0 else mn-0.32,f'{mn:+.1f}',ha='center',fontsize=8.6,fontweight='bold')
ax.axhline(0,color='#222',lw=0.8); ax.set_xticks(x); ax.set_xticklabels([f'{h} week' for h in HOR]); ax.set_ylabel('Mean forward WTI return (%)')
ax.set_title('Managed Money: a fast unwind precedes FURTHER weakness (momentum)\n'
             f"fastest unwind {res['flow']['4']['mean']*100:+.1f}% over 4 weeks ({res['flow']['4']['hit']*100:.0f}% hit, bootstrap p={res['flow']['4']['boot_p']:.3f})",fontsize=12,fontweight='bold')
ax.legend(fontsize=9.5,frameon=False,loc='lower left')
ax.text(0.005,-0.12,'4-week change in Managed Money net, decile-ranked. Window 2021-2026. Opposite sign to the Other Reportables rebound.',transform=ax.transAxes,fontsize=8,color=GREY)
fig.tight_layout(); fig.savefig(os.path.join(OUT,'mm_chart3_flow.png'),bbox_inches='tight'); plt.close(fig)
print('MM charts written to',OUT); print(os.listdir(OUT))
