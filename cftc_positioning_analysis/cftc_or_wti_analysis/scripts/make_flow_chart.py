"""chart5: flow / capitulation signal (4-week change in OR net, decile buckets) with HAC + bootstrap."""
import pandas as pd, numpy as np, os, json, warnings
import statsmodels.api as sm
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
warnings.filterwarnings('ignore'); np.random.seed(7)
SCRATCH = os.path.dirname(os.path.abspath(__file__))
ROOT = r"c:/Users/aayush.jhawar/OneDrive - hertshtengroup.com/Desktop/Dashboard_v3"
OUT = os.path.join(ROOT, "cftc_positioning_analysis", "cftc_or_wti_analysis", "charts")
NAVY='#1f3b57'; RED='#c0392b'; GREEN='#1e8449'; GREY='#95a5a6'
plt.rcParams.update({'font.size':11,'axes.edgecolor':'#444','axes.linewidth':0.8,'figure.dpi':140,'savefig.dpi':140})

m = pd.read_parquet(os.path.join(SCRATCH,"panel.parquet")).sort_values('date').reset_index(drop=True)
m['or_chg4'] = m['or_net'].diff(4)
W = m[m['p0_adj'].notna() & m['z'].notna()].dropna(subset=['or_chg4']).copy().reset_index(drop=True)
W['dec'] = pd.qcut(W['or_chg4'], 10, labels=False, duplicates='drop')
mx = W['dec'].max()
groups = [('Fastest UNWIND\n(capitulation)', W[W['dec']==0], GREEN),
          ('Neutral', W[W['dec'].isin([4,5])], GREY),
          ('Fastest BUILD', W[W['dec']==mx], RED)]

def boot_p(y_all, mask, h, n=5000):
    s=pd.DataFrame({'y':y_all,'f':mask.astype(bool)}).dropna().reset_index(drop=True)
    yv=s['y'].values; fv=s['f'].values; N=len(yv); obs=yv[fv].mean()-yv.mean()
    L=max(h,3); nb=int(np.ceil(N/L)); d=np.empty(n)
    for b in range(n):
        st=np.random.randint(0,N,nb); idx=(st[:,None]+np.arange(L)[None,:]).ravel()%N; idx=idx[:N]
        d[b]=yv[idx][fv[idx]].mean()-yv[idx].mean() if fv[idx].sum()>0 else 0
    return (np.abs(d-d.mean())>=abs(obs)).mean()

HOR=[1,2,4]
fig, ax = plt.subplots(figsize=(9.6,5.4))
x=np.arange(len(HOR)); width=0.26
flowstats={}
for i,(lab,grp,col) in enumerate(groups):
    means=[grp[f'fwd_{h}w'].mean()*100 for h in HOR]
    pos=x+(i-1)*width
    ax.bar(pos, means, width, color=col, alpha=0.88, label=lab.replace('\n',' '))
    for p,mn in zip(pos,means):
        ax.text(p, mn+0.12 if mn>=0 else mn-0.35, f'{mn:+.1f}', ha='center', fontsize=8.6, fontweight='bold')
# significance stars on unwind bucket (vs baseline, block-bootstrap)
unwind = W['dec']==0
for j,h in enumerate(HOR):
    p=boot_p(W[f'fwd_{h}w'], unwind, h)
    flowstats[h]=dict(mean=float(W.loc[unwind,f'fwd_{h}w'].mean()),
                      hit=float((W.loc[unwind,f'fwd_{h}w']>0).mean()), boot_p=float(p),
                      n=int(unwind.sum()))
    star='**' if p<0.01 else ('*' if p<0.05 else '')
    if star:
        ax.text(x[j]-width, W.loc[unwind,f'fwd_{h}w'].mean()*100+0.9, star, ha='center', color=GREEN, fontsize=15, fontweight='bold')
ax.axhline(0,color='#222',lw=0.8); ax.set_xticks(x); ax.set_xticklabels([f'{h} week' for h in HOR])
ax.set_ylabel('Mean forward WTI return (%)')
ax.set_title('The change beats the level: positioning capitulation precedes rebounds\n'
             f"fastest unwind  +{flowstats[4]['mean']*100:.1f}% over 4 weeks  ({flowstats[4]['hit']*100:.0f}% hit, bootstrap p={flowstats[4]['boot_p']:.3f})",
             fontsize=12, fontweight='bold')
ax.legend(fontsize=9.5, frameon=False, loc='upper left')
ax.text(0.005,-0.12,'4-week change in Other-Reportables net, decile-ranked. Window 2021-2026. * bootstrap p<0.05 vs all-weeks baseline.',
        transform=ax.transAxes, fontsize=8, color='#7f8c8d')
fig.tight_layout(); fig.savefig(os.path.join(OUT,'chart5_flow_capitulation.png'), bbox_inches='tight'); plt.close(fig)

# HAC t for unwind 4w (consistency with deck)
W['uw']=unwind.astype(float)
r=sm.OLS(W['fwd_4w'], sm.add_constant(W['uw']), missing='drop').fit(cov_type='HAC',cov_kwds={'maxlags':4})
flowstats['hac_t_4w']=float(r.tvalues['uw'])
json.dump(flowstats, open(os.path.join(SCRATCH,'flowstats.json'),'w'), indent=2)
print('chart5 written. flowstats:', json.dumps(flowstats, indent=2))
