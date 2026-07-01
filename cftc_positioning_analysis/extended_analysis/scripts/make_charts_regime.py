"""Charts for the combined curve + regime + cross-instrument deck."""
import pandas as pd, numpy as np, os, warnings
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
warnings.filterwarnings('ignore')
SCRATCH=os.path.dirname(os.path.abspath(__file__))
ROOT=r"c:/Users/aayush.jhawar/OneDrive - hertshtengroup.com/Desktop/Dashboard_v3"
OUT=os.path.join(ROOT,"cftc_positioning_analysis","extended_analysis","charts"); os.makedirs(OUT,exist_ok=True)
NAVY='#16324f'; INK='#1a1a1a'; GREEN='#1e8b54'; RED='#c0392b'; GOLD='#c8862a'; GREY='#8a949c'; BLUE='#2c6fbb'
plt.rcParams.update({'font.size':12,'font.family':'DejaVu Sans','axes.edgecolor':'#cfd6dc','axes.linewidth':1.0,
    'axes.grid':True,'grid.color':'#eef2f5','figure.dpi':150,'savefig.dpi':150,'axes.spines.top':False,'axes.spines.right':False})
Aw=pd.read_parquet(os.path.join(SCRATCH,'panel_wti_full.parquet'))
Ab=pd.read_parquet(os.path.join(SCRATCH,'panel_brent_full.parquet'))
def prep(A):
    A=A.copy(); A['CURVE']=np.where(A['sp12']>0,'Backwardation','Contango')
    A['VOL']=np.where(A['rv20']<=A['rv20'].median(),'LoVol','HiVol')
    A['spterc']=pd.qcut(A['sp12'],3,labels=['Contango','Flat','Backwardation']); return A
Aw=prep(Aw); Ab=prep(Ab)
def m(A,mask): y=A.loc[mask,'fwd_4w'].dropna(); return (y.mean()*100,(y>0).mean()*100,len(y))

# ---------- CHART 1: the curve signal (spread terciles) WTI + Brent ----------
fig,ax=plt.subplots(figsize=(10.5,5.6)); x=np.arange(3); w=0.38
labs=['Contango\n(oversupplied)','Flat','Backwardation\n(tight)']
for i,(nm,A,col) in enumerate([('WTI',Aw,GOLD),('Brent',Ab,BLUE)]):
    vals=[m(A,A['spterc']==t)[0] for t in ['Contango','Flat','Backwardation']]
    hits=[m(A,A['spterc']==t)[1] for t in ['Contango','Flat','Backwardation']]
    pos=x+(i-0.5)*w; ax.bar(pos,vals,w,color=col,label=nm,alpha=0.9)
    for p,v,h in zip(pos,vals,hits): ax.text(p,v+(0.12 if v>=0 else -0.35),f'{v:+.1f}%\n{h:.0f}% hit',ha='center',fontsize=8.5,fontweight='bold')
ax.axhline(0,color='#333',lw=0.9); ax.set_xticks(x); ax.set_xticklabels(labs)
ax.set_ylabel('WTI/Brent return over next 4 weeks (%)')
ax.set_title('The forward curve predicts crude better than positioning does',fontsize=14,fontweight='bold',color=NAVY,pad=26)
ax.text(0.5,1.03,'Contango tends to precede a rally; backwardation precedes weakness. Holds on both crudes.',transform=ax.transAxes,ha='center',fontsize=10.5,color='#555',style='italic')
ax.legend(fontsize=11,frameon=False,loc='upper right'); ax.set_ylim(-4,6.2)
fig.tight_layout(); fig.savefig(os.path.join(OUT,'chart_curve_signal.png'),bbox_inches='tight'); plt.close(fig)

# ---------- CHART 2: regime grid Curve x Vol (WTI, Brent) ----------
fig,axes=plt.subplots(1,2,figsize=(12,5.3))
for ax,(nm,A) in zip(axes,[('WTI (2021-2026)',Aw),('Brent (2016-2026)',Ab)]):
    rows=['Contango','Backwardation']; cols=['LoVol','HiVol']
    M=np.array([[m(A,(A['CURVE']==r)&(A['VOL']==c))[0] for c in cols] for r in rows])
    H=np.array([[m(A,(A['CURVE']==r)&(A['VOL']==c))[1] for c in cols] for r in rows])
    N=np.array([[m(A,(A['CURVE']==r)&(A['VOL']==c))[2] for c in cols] for r in rows])
    base=A['fwd_4w'].mean()*100
    norm=TwoSlopeNorm(vmin=min(M.min(),base-1),vcenter=base,vmax=max(M.max(),base+1))
    ax.imshow(M,cmap='RdYlGn',norm=norm,aspect='auto')
    for i in range(2):
        for j in range(2):
            ax.text(j,i-0.12,f'{M[i,j]:+.1f}%',ha='center',va='center',fontsize=19,fontweight='bold',color=INK)
            ax.text(j,i+0.2,f'{H[i,j]:.0f}% hit  n={N[i,j]}',ha='center',va='center',fontsize=9.5,color='#333')
    # highlight Contango+HiVol (row0,col1)
    ax.add_patch(plt.Rectangle((0.5,-0.5),1,1,fill=False,edgecolor=NAVY,lw=3))
    ax.set_xticks([0,1]); ax.set_xticklabels(['Low vol','High vol']); ax.set_yticks([0,1]); ax.set_yticklabels(['Contango','Backwardation'])
    ax.set_title(nm,fontsize=12,fontweight='bold',color=NAVY)
    ax.set_xticks(np.arange(-.5,2,1),minor=True); ax.set_yticks(np.arange(-.5,2,1),minor=True)
    ax.grid(which='minor',color='white',linewidth=3); ax.grid(which='major',visible=False); ax.tick_params(which='minor',length=0)
fig.suptitle('The tradeable edge: Contango + High volatility (boxed) precedes strong crude gains',fontsize=14,fontweight='bold',color=NAVY,y=1.02)
fig.tight_layout(); fig.savefig(os.path.join(OUT,'chart_regime_grid.png'),bbox_inches='tight'); plt.close(fig)

# ---------- CHART 3: positioning does not replicate (WTI vs Brent) ----------
def q(A,mask): return m(A,mask)[0]
tests=[('Crowded long\n(top 10%)', lambda A:A['z']>=A['z'].quantile(.9)),
       ('Light\n(bottom 10%)', lambda A:A['z']<=A['z'].quantile(.1)),
       ('Stale crowded\n(4+ wks)', None),('Fast unwind\n(flow)', None)]
# staleness & flow need helper columns
def add(A):
    A=A.copy(); terc=pd.qcut(A['z'],3,labels=['L','M','H'])
    def rl(msk):
        o=np.zeros(len(msk),int);k=0
        for i,v in enumerate(msk):k=k+1 if v else 0;o[i]=k
        return o
    A['rh']=rl((terc=='H').values); A['fdec']=pd.qcut(A['chg4'],10,labels=False,duplicates='drop'); return A
Aw2=add(Aw); Ab2=add(Ab)
def vals(A):
    return [q(A,A['z']>=A['z'].quantile(.9)), q(A,A['z']<=A['z'].quantile(.1)),
            m(A,A['rh']>=4)[0], m(A,A['fdec']==0)[0]]
fig,ax=plt.subplots(figsize=(10.5,5.4)); x=np.arange(4); w=0.38
vw=vals(Aw2); vb=vals(Ab2)
ax.bar(x-w/2,vw,w,color=GOLD,label='WTI (2021-2026)')
ax.bar(x+w/2,vb,w,color=BLUE,label='Brent (2016-2026)')
for xs,vv in [(x-w/2,vw),(x+w/2,vb)]:
    for p,v in zip(xs,vv): ax.text(p,v+(0.1 if v>=0 else -0.4),f'{v:+.1f}',ha='center',fontsize=9,fontweight='bold')
ax.axhline(Aw['fwd_4w'].mean()*100,color=GREY,ls='--',lw=1); ax.text(3.4,Aw['fwd_4w'].mean()*100+0.15,'~baseline',color=GREY,fontsize=8,ha='right')
ax.axhline(0,color='#333',lw=0.9); ax.set_xticks(x); ax.set_xticklabels([t[0] for t in tests])
ax.set_ylabel('Next 4-week return (%)')
ax.set_title('Positioning signals are WTI-specific: they vanish on Brent',fontsize=14,fontweight='bold',color=NAVY,pad=26)
ax.text(0.5,1.03,'The WTI extremes/staleness/flow edges do not replicate on Brent\'s longer sample. Positioning is a weak, regime-dependent factor.',transform=ax.transAxes,ha='center',fontsize=9.5,color='#555',style='italic')
ax.legend(fontsize=11,frameon=False,loc='upper left')
fig.tight_layout(); fig.savefig(os.path.join(OUT,'chart_replication.png'),bbox_inches='tight'); plt.close(fig)
print('regime charts written:', os.listdir(OUT))
