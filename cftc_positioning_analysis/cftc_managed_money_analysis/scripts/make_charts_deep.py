"""Polished charts for the deep Managed Money deck."""
import pandas as pd, numpy as np, json, os, warnings
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
warnings.filterwarnings('ignore')
SCRATCH=os.path.dirname(os.path.abspath(__file__))
ROOT=r"c:/Users/aayush.jhawar/OneDrive - hertshtengroup.com/Desktop/Dashboard_v3"
OUT=os.path.join(ROOT,"cftc_positioning_analysis","cftc_managed_money_analysis","charts"); os.makedirs(OUT,exist_ok=True)
R=json.load(open(os.path.join(SCRATCH,"mm_deep_results.json")))
A=pd.read_parquet(os.path.join(SCRATCH,"mm_deep_window.parquet"))

NAVY='#16324f'; INK='#1a1a1a'; GOLD='#c8862a'; GREEN='#1e8b54'; RED='#c0392b'; GREY='#9aa3ab'; TEAL='#2a9d8f'
plt.rcParams.update({'font.size':12,'font.family':'DejaVu Sans','axes.edgecolor':'#cfd6dc','axes.linewidth':1.0,
    'axes.grid':True,'grid.color':'#eef2f5','grid.linewidth':1.0,'figure.dpi':150,'savefig.dpi':150,
    'axes.spines.top':False,'axes.spines.right':False})

# ============ HERO: PERSISTENCE (staleness) ============
P=R['persistence']; durs=['1 wk','2-3 wks','4+ wks']
hi=[P['High position (crowded long)'][d]['mean']*100 for d in durs]
hihit=[P['High position (crowded long)'][d]['hit']*100 for d in durs]
hin=[P['High position (crowded long)'][d]['n'] for d in durs]
lo=[P['Low position (light/short)'][d]['mean']*100 for d in durs]
lohit=[P['Low position (light/short)'][d]['hit']*100 for d in durs]
lon=[P['Low position (light/short)'][d]['n'] for d in durs]
fig,ax=plt.subplots(figsize=(11,5.9)); x=np.arange(3)
ax.plot(x,hi,'-o',color=GOLD,lw=3,ms=11,label='Funds CROWDED LONG (heavily bullish)',zorder=5)
ax.plot(x,lo,'-o',color=TEAL,lw=3,ms=11,label='Funds LIGHT / SHORT (bearish)',zorder=5)
for xi,v,h in zip(x,hi,hihit):
    ax.text(xi,v+0.6,f'{v:+.1f}%',ha='center',fontweight='bold',fontsize=13,color=GOLD)
    ax.text(xi,v+0.25 if xi<2 else v-0.95,f'{h:.0f}% hit',ha='center',fontsize=9,color='#7a5a1e')
for xi,v,h in zip(x,lo,lohit):
    ax.text(xi,v-0.95,f'{v:+.1f}%',ha='center',fontweight='bold',fontsize=13,color=TEAL)
    ax.text(xi,v-1.5 if xi<2 else v+0.35,f'{h:.0f}% hit',ha='center',fontsize=9,color='#1d6f66')
ax.axhline(R['uncond']['4']*100,color=GREY,ls='--',lw=1.2); ax.text(0.02,R['uncond']['4']*100+0.25,f"average week +{R['uncond']['4']*100:.1f}%",color=GREY,fontsize=9)
ax.axhline(0,color='#333',lw=0.9)
ax.annotate('momentum:\nride it',xy=(0,9),xytext=(0.35,9.6),fontsize=9.5,color='#7a5a1e',ha='left',va='center')
ax.annotate('exhausted:\nfade / exit',xy=(2,-0.8),xytext=(1.45,-2.4),fontsize=9.5,color='#7a5a1e',
            arrowprops=dict(arrowstyle='->',color=GOLD,lw=1.5))
ax.annotate('reversal:\naccumulate',xy=(2,3.8),xytext=(1.42,5.0),fontsize=9.5,color='#1d6f66',
            arrowprops=dict(arrowstyle='->',color=TEAL,lw=1.5))
ax.set_xticks(x); ax.set_xticklabels(['Just turned\n(1 week)','Building\n(2-3 weeks)','SUSTAINED / STALE\n(4+ weeks)'],fontsize=11)
ax.set_xlim(-0.35,2.45); ax.set_ylim(-4,11)
ax.set_ylabel('WTI return over the NEXT 4 weeks (%)')
ax.set_title('What happens after positioning stays extreme for several weeks',fontsize=15,fontweight='bold',color=NAVY,pad=30)
ax.text(0.5,1.045,'Fresh extremes keep trending. Once positioning goes stale, it reverses.',
        transform=ax.transAxes,ha='center',fontsize=11.5,color='#555',style='italic')
ax.legend(loc='upper right',fontsize=10,frameon=False)
fig.tight_layout(); fig.savefig(os.path.join(OUT,'deep_persistence.png'),bbox_inches='tight'); plt.close(fig)

# ============ HEATMAP: VOL x POSITION ============
rows=['Low vol','High vol']; cols=['Low position','High position']
M=np.array([[R['grid'][f"{r} + {c}"]['mean']*100 for c in cols] for r in rows])
HIT=np.array([[R['grid'][f"{r} + {c}"]['hit']*100 for c in cols] for r in rows])
NN=np.array([[R['grid'][f"{r} + {c}"]['n'] for c in cols] for r in rows])
base=R['uncond']['4']*100
fig,ax=plt.subplots(figsize=(8.4,5.6))
from matplotlib.colors import TwoSlopeNorm
norm=TwoSlopeNorm(vmin=min(M.min(),base-1),vcenter=base,vmax=max(M.max(),base+1))
im=ax.imshow(M,cmap='RdYlGn',norm=norm,aspect='auto')
for i in range(2):
    for j in range(2):
        ax.text(j,i-0.13,f'{M[i,j]:+.1f}%',ha='center',va='center',fontsize=22,fontweight='bold',color=INK)
        ax.text(j,i+0.18,f'{HIT[i,j]:.0f}% hit   n={NN[i,j]}',ha='center',va='center',fontsize=10.5,color='#333')
ax.set_xticks([0,1]); ax.set_xticklabels(['LOW position\n(funds light)','HIGH position\n(funds crowded long)'],fontsize=11)
ax.set_yticks([0,1]); ax.set_yticklabels(['LOW\nvolatility','HIGH\nvolatility'],fontsize=11)
ax.set_title('WTI return over next 4 weeks, by volatility and positioning',fontsize=14,fontweight='bold',color=NAVY,pad=14)
ax.text(0.5,-0.22,f'Green = better than the average week (+{base:.1f}%). Median splits, 2021-2026.',transform=ax.transAxes,ha='center',fontsize=9.5,color='#666')
ax.set_xticks(np.arange(-.5,2,1),minor=True); ax.set_yticks(np.arange(-.5,2,1),minor=True)
ax.grid(which='minor',color='white',linewidth=3); ax.tick_params(which='minor',length=0)
fig.tight_layout(); fig.savefig(os.path.join(OUT,'deep_grid.png'),bbox_inches='tight'); plt.close(fig)

# ============ EXTREMES (assignment) ============
E=R['extremes']; HOR=[1,2,4]
series=[('Top 10% most long',E['Top 10% (most long)'],RED),('Average week',None,GREY),
        ('Bottom 10% least long',E['Bottom 10% (least long)'],GREEN)]
fig,ax=plt.subplots(figsize=(10,5.4)); x=np.arange(3); w=0.26
for i,(lab,d,col) in enumerate(series):
    vals=[(R['uncond'][str(h)] if d is None else d[str(h)]['mean'])*100 for h in HOR]
    pos=x+(i-1)*w; ax.bar(pos,vals,w,color=col,alpha=0.9,label=lab)
    for p,v in zip(pos,vals): ax.text(p,v+(0.12 if v>=0 else -0.34),f'{v:+.1f}',ha='center',fontsize=9,fontweight='bold')
ax.axhline(0,color='#333',lw=0.9); ax.set_xticks(x); ax.set_xticklabels([f'{h} week' for h in HOR])
ax.set_ylabel('Mean WTI forward return (%)'); ax.set_ylim(-2.8,4.4)
ax.set_title('Stretched positioning leans gently against price',fontsize=14,fontweight='bold',color=NAVY,pad=34)
ax.text(0.5,1.05,'When funds are most long, WTI tends to slip; when least long, it tends to rise. Modest on its own.',transform=ax.transAxes,ha='center',fontsize=10,color='#555',style='italic')
ax.legend(loc='lower left',fontsize=9.5,frameon=False,ncol=3)
fig.tight_layout(); fig.savefig(os.path.join(OUT,'deep_extremes.png'),bbox_inches='tight'); plt.close(fig)

print('deep charts written:', [f for f in os.listdir(OUT) if f.startswith('deep_')])
