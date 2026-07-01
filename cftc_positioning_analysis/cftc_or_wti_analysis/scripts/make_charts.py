"""STEP 7: charts -> project/cftc_or_wti_analysis/charts/"""
import pandas as pd, numpy as np, json, os, warnings
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
warnings.filterwarnings('ignore'); np.random.seed(7)

SCRATCH = os.path.dirname(os.path.abspath(__file__))
ROOT = r"c:/Users/aayush.jhawar/OneDrive - hertshtengroup.com/Desktop/Dashboard_v3"
OUT = os.path.join(ROOT, "cftc_positioning_analysis", "cftc_or_wti_analysis", "charts")
os.makedirs(OUT, exist_ok=True)
W = pd.read_parquet(os.path.join(SCRATCH, "window.parquet")).sort_values('date').reset_index(drop=True)
res = json.load(open(os.path.join(SCRATCH, "results.json")))

NAVY='#1f3b57'; RED='#c0392b'; GREEN='#1e8449'; GREY='#7f8c8d'; GOLD='#b9770e'
plt.rcParams.update({'font.size':11,'axes.edgecolor':'#444','axes.linewidth':0.8,
                     'figure.dpi':140,'savefig.dpi':140,'font.family':'DejaVu Sans'})

def block_boot_mean_ci(y, fl, h, n=4000):
    s=pd.DataFrame({'y':y,'f':fl.astype(bool)}).dropna().reset_index(drop=True)
    yv=s['y'].values; fv=s['f'].values; N=len(yv); L=max(h,3); nb=int(np.ceil(N/L))
    out=np.empty(n)
    for b in range(n):
        st=np.random.randint(0,N,nb); idx=(st[:,None]+np.arange(L)[None,:]).ravel()%N; idx=idx[:N]
        ys=yv[idx]; fs=fv[idx]; out[b]=ys[fs].mean() if fs.sum()>0 else np.nan
    return np.nanpercentile(out,2.5), np.nanpercentile(out,97.5)

# ============ CHART 1: OR net vs WTI dual-axis, extreme bands ============
fig, ax = plt.subplots(figsize=(11,5.2))
ax.plot(W['date'], W['or_net']/1000, color=NAVY, lw=1.6, label='Other Reportables NET (k contracts)')
ax.set_ylabel('Other Reportables net  (000s contracts)', color=NAVY)
ax.tick_params(axis='y', labelcolor=NAVY); ax.axhline(0, color=NAVY, lw=0.6, ls=':')
ax2 = ax.twinx()
ax2.plot(W['date'], W['p0_raw'], color=GOLD, lw=1.4, alpha=0.9, label='WTI front-month ($/bbl)')
ax2.set_ylabel('WTI front-month  ($/bbl)', color=GOLD); ax2.tick_params(axis='y', labelcolor=GOLD)
# shade extremes
for _,r in W[W['ext_long']].iterrows():
    ax.axvspan(r['date']-pd.Timedelta('3D'), r['date']+pd.Timedelta('3D'), color=RED, alpha=0.18, zorder=0)
for _,r in W[W['ext_short']].iterrows():
    ax.axvspan(r['date']-pd.Timedelta('3D'), r['date']+pd.Timedelta('3D'), color=GREEN, alpha=0.18, zorder=0)
ax.set_title('Other Reportables NET positioning vs WTI, 2021–2026   (shaded: |rolling 52w Z| ≥ 2)',
             fontsize=12.5, fontweight='bold')
leg = [Patch(color=NAVY,label='OR net (left)'), Patch(color=GOLD,label='WTI front-month (right)'),
       Patch(color=RED,alpha=0.3,label='Extreme LONG (Z≥+2)'), Patch(color=GREEN,alpha=0.3,label='Extreme SHORT (Z≤−2)')]
ax.legend(handles=leg, loc='upper center', ncol=4, fontsize=9, frameon=False, bbox_to_anchor=(0.5,-0.08))
ax.text(0.005,0.97,'Series = CFTC Other Reportables (NOT Managed Money). WTI = roll-adj front-month, NYMEX CL.',
        transform=ax.transAxes, fontsize=8, color=GREY, va='top')
fig.tight_layout(); fig.savefig(os.path.join(OUT,'chart1_position_vs_wti.png'), bbox_inches='tight'); plt.close(fig)

# ============ CHART 2: mean forward return by bucket x horizon, error bars ============
HOR=[1,2,4]
buckets=[('Extreme LONG (Z≥+2)','ext_long',RED),
         ('Extreme SHORT (Z≤−2)','ext_short',GREEN),
         ('Unconditional (all weeks)',None,GREY)]
fig, ax = plt.subplots(figsize=(10.5,5.6))
x=np.arange(len(HOR)); width=0.26
for i,(lab,flagcol,col) in enumerate(buckets):
    means=[]; los=[]; his=[]; meds=[]
    for h in HOR:
        y=W[f'fwd_{h}w']
        if flagcol is None:
            sub=y.dropna(); means.append(sub.mean()*100); meds.append(sub.median()*100)
            bs=block_boot_mean_ci(y, pd.Series(True,index=W.index), h)
        else:
            fl=W[flagcol]; sub=y[fl].dropna(); means.append(sub.mean()*100); meds.append(sub.median()*100)
            bs=block_boot_mean_ci(y, fl, h)
        los.append(means[-1]-bs[0]*100); his.append(bs[1]*100-means[-1])
    pos=x+(i-1)*width
    ax.bar(pos, means, width, color=col, alpha=0.85, label=lab,
           yerr=[los,his], capsize=4, error_kw=dict(lw=1.1,ecolor='#333'))
    ax.scatter(pos, meds, marker='D', s=34, color='white', edgecolor='#222', zorder=5)
    for p,mn in zip(pos,means):
        ax.text(p, mn+(0.25 if mn>=0 else -0.5), f'{mn:.1f}', ha='center', fontsize=8.5, fontweight='bold')
ax.axhline(0,color='#222',lw=0.8)
ax.set_xticks(x); ax.set_xticklabels([f'{h} week' for h in HOR])
ax.set_ylabel('Forward WTI return  (%)');
ax.set_title('Mean forward WTI return after extreme Other-Reportables positioning\n'
             'bars = mean (95% block-bootstrap CI) · white ◇ = median',
             fontsize=12.5, fontweight='bold')
ax.legend(loc='upper left', fontsize=9.5, frameon=False)
ax.text(0.005,-0.12,'Window 2021–2026 (n=282 wks). Long: 8 wks/4 episodes · Short: 18 wks/10 episodes. '
        'Means can diverge from medians (outlier-driven).', transform=ax.transAxes, fontsize=8, color=GREY)
fig.tight_layout(); fig.savefig(os.path.join(OUT,'chart2_forward_returns.png'), bbox_inches='tight'); plt.close(fig)

# ============ CHART 3: summary stats table ============
fwd={ (r['bucket'],r['horizon_w']):r for r in res['forward'] }
rows=[]
for bk,lab in [('extreme_long','Extreme LONG'),('extreme_short','Extreme SHORT')]:
    for h in HOR:
        r=fwd[(bk,h)]; u=res['uncond'][str(h)]
        rows.append([lab,f'{h}w',f"{r['n_weeks']}",f"{r['n_episodes']}",
                     f"{r['mean']*100:+.1f}%",f"{r['median']*100:+.1f}%",f"{r['hit_pos']*100:.0f}%",
                     f"{u['mean']*100:+.1f}%",f"{r['diff_vs_uncond']*100:+.1f}%",
                     f"{r['hac_t']:.2f}" if r['hac_t'] is not None else '–',
                     f"{r['boot_p']:.3f}" if r['boot_p'] is not None else '–'])
cols=['Bucket','Horizon','n wks','n epi','Mean','Median','Hit+','Uncond','Excess','HAC t','Boot p']
fig, ax = plt.subplots(figsize=(12,3.3)); ax.axis('off')
cw=[0.135,0.085,0.07,0.07,0.085,0.085,0.07,0.085,0.085,0.075,0.085]
tb=ax.table(cellText=rows, colLabels=cols, loc='center', cellLoc='center', colWidths=cw)
tb.auto_set_font_size(False); tb.set_fontsize(9.5); tb.scale(1,1.55)
for j in range(len(cols)):
    c=tb[0,j]; c.set_facecolor(NAVY); c.set_text_props(color='white',fontweight='bold')
for i in range(1,len(rows)+1):
    base = '#fdecea' if rows[i-1][0].startswith('Extreme LONG') else '#eafaf1'
    for j in range(len(cols)):
        tb[i,j].set_facecolor(base)
# highlight the significant cell (short 2w boot p)
for i in range(1,len(rows)+1):
    if rows[i-1][0].startswith('Extreme SHORT') and rows[i-1][1]=='2w':
        for j in range(len(cols)): tb[i,j].set_facecolor('#c8f0d8')
        tb[i,len(cols)-1].set_text_props(fontweight='bold')
ax.set_title('Forward-return summary — conditional vs unconditional (HAC SE, block-bootstrap p)\n'
             'green row = only nominally significant cell (does not survive 6-test multiple comparison)',
             fontsize=12, fontweight='bold', pad=14)
fig.savefig(os.path.join(OUT,'chart3_summary_table.png'), bbox_inches='tight'); plt.close(fig)

# ============ CHART 4: decay probe (pre vs post-release) ============
dec={d['bucket']:d for d in res['decay']}
order=[('extreme_short','Extreme SHORT'),('extreme_long','Extreme LONG'),('unconditional','Unconditional')]
fig, ax = plt.subplots(figsize=(8.8,4.8))
x=np.arange(len(order)); w=0.38
pre=[dec[k]['pre_mean']*100 for k,_ in order]; post=[dec[k]['post1_mean']*100 for k,_ in order]
b1=ax.bar(x-w/2, pre, w, color='#aaaaaa', label='Pre-release  Tue→Fri (UNtradeable)')
b2=ax.bar(x+w/2, post, w, color=NAVY, label='Post-release  Fri→+1wk (tradeable)')
for bars in (b1,b2):
    for bar in bars:
        ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.08,
                f'{bar.get_height():.2f}', ha='center', fontsize=9, fontweight='bold')
for i,(k,_) in enumerate(order):
    sh=dec[k]['pre_share_of_move']
    ax.text(i, max(pre[i],post[i])+0.9, f'{sh*100:.0f}% of move\npre-release', ha='center', fontsize=8.5, color=GREY)
ax.axhline(0,color='#222',lw=0.8); ax.set_xticks(x); ax.set_xticklabels([l for _,l in order])
ax.set_ylabel('Mean WTI return (%)'); ax.set_ylim(0, 8)
ax.set_title('Decay probe: where does the move happen?\nShort signal is mostly POST-release (tradeable); long is mostly pre-release',
             fontsize=12, fontweight='bold')
ax.legend(fontsize=9, frameon=False, loc='upper right')
fig.tight_layout(); fig.savefig(os.path.join(OUT,'chart4_decay_probe.png'), bbox_inches='tight'); plt.close(fig)

print("charts written to", OUT)
print(os.listdir(OUT))
