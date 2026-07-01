"""Combined trading deck v2 (honest): positioning=momentum; term structure + structural signals are the edge. 8 slides."""
import os, zipfile
from PIL import Image
ROOT=r"c:/Users/aayush.jhawar/OneDrive - hertshtengroup.com/Desktop/Dashboard_v3"
BASE=os.path.join(ROOT,"cftc_positioning_analysis"); CHX=os.path.join(BASE,"extended_analysis","charts")
CHM=os.path.join(BASE,"cftc_managed_money_analysis","charts")
PPTX=os.environ.get("PPTX_OUT", os.path.join(BASE,"WTI_Brent_positioning_structure_trading.pptx"))
A='http://schemas.openxmlformats.org/drawingml/2006/main'; EMU_IN=914400; SW,SH=12192000,6858000; NSLIDES=10
def esc(s): return s.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
NAVY='16324F'; INK='1A1A1A'; GREEN='1E8B54'; RED='C0392B'; GOLD='B07A1E'; BLUE='2C6FBB'; GREY='5D6D7E'
IN=lambda v:int(v*EMU_IN)
def fit(p,bx,by,bw,bh):
    w,h=Image.open(p).size; s=min(bw/w,bh/h); return bx+(bw-int(w*s))//2,by+(bh-int(h*s))//2,int(w*s),int(h*s)
_sid=[10]
def nid(): _sid[0]+=1; return _sid[0]
def pic(rid,x,y,cx,cy):
    return (f'<p:pic><p:nvPicPr><p:cNvPr id="{nid()}" name="i"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
            f'<p:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>'
            f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>')
def para(runs,bullet=False,sa=440,align='l',line=None):
    bu=('<a:buFont typeface="Arial"/><a:buChar char="&#8226;"/>' if bullet else '<a:buNone/>')
    ind=' indent="-210000" marL="255000"' if bullet else ''
    ln=f'<a:lnSpc><a:spcPct val="{line}"/></a:lnSpc>' if line else ''
    rx=''.join(f'<a:r><a:rPr lang="en-US" sz="{sz}" b="{1 if b else 0}" dirty="0"><a:solidFill><a:srgbClr val="{c}"/></a:solidFill><a:latin typeface="Calibri"/></a:rPr><a:t>{esc(t)}</a:t></a:r>' for t,sz,c,b in runs)
    return f'<a:p><a:pPr algn="{align}"{ind}>{ln}<a:spcAft><a:spcPts val="{sa}"/></a:spcAft>{bu}</a:pPr>{rx}</a:p>'
def tb(x,y,cx,cy,paras,fill=None,anchor='t'):
    sf=f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>' if fill else '<a:noFill/>'
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{nid()}" name="t"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom>{sf}</p:spPr>'
            f'<p:txBody><a:bodyPr wrap="square" lIns="91440" tIns="50000" rIns="91440" bIns="50000" anchor="{anchor}"><a:normAutofit/></a:bodyPr><a:lstStyle/>{"".join(paras)}</p:txBody></p:sp>')
def sld(shapes,bg='FFFFFF'):
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<p:sld xmlns:a="{A}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            f'<p:cSld><p:bg><p:bgPr><a:solidFill><a:srgbClr val="{bg}"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>'
            '<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
            f'{"".join(shapes)}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>')
def band(t): return [tb(0,0,SW,IN(0.9),[para([(t,2100,'FFFFFF',True)])],fill=NAVY,anchor='ctr')]
def L(bx,by,bw,bh,f): x,y,cx,cy=fit(os.path.join(CHX,f),bx,by,bw,bh); return pic('rId2',x,y,cx,cy)
def LM(bx,by,bw,bh,f): x,y,cx,cy=fit(os.path.join(CHM,f),bx,by,bw,bh); return pic('rId2',x,y,cx,cy)

# S1 verdict
s1=[tb(0,0,SW,IN(1.7),[para([('Crude positioning, structure, and what actually trades',2300,'FFFFFF',True)]),
     para([('WTI and Brent  |  CFTC Managed Money + term structure',1250,'D9E2EA',False)])],fill=NAVY,anchor='ctr')]
s1+=[tb(IN(0.55),IN(1.95),IN(12.3),IN(1.05),[para([
     ('Positioning is a ',1700,INK,False),('momentum / context',1700,GOLD,True),
     (' gauge, not a contrarian timing signal. The durable, tradeable edge is in the ',1700,INK,False),('term structure',1700,GREEN,True),(' and structural COT columns.',1700,INK,False)],line=100000)])]
s1+=[tb(IN(0.55),IN(3.15),IN(12.3),IN(3.3),[
   para([('Managed Money is coincident and trend-following (it adds as price rises). Its net extremes give no robust forward edge, and the apparent edges do not survive on Brent.',1350,INK,False)],bullet=True),
   para([('The one robust, cross-validated price signal is the curve: deep backwardation is a forward-return headwind (contango is too rare to trade).',1350,GREEN,True)],bullet=True),
   para([('Structural columns add real risk information: the short side is now the most crowded in the sample (squeeze-prone), and rising price on rising open interest is the best trend-continuation tell.',1350,INK,False)],bullet=True),
   para([('Use all of this as an overlay and risk filter on your main factors, never as a standalone trigger.',1350,INK,False)],bullet=True)])]
s1+=[tb(IN(0.55),IN(6.55),IN(12.3),IN(0.6),[para([('WTI 2021-2026, Brent 2016-2026. De-rolled returns; no look-ahead; validated by bootstrap and cross-instrument replication.',1000,GREY,False)])],fill='F2F5F7')]

# S2 method
s2=band('How we tested it, and how we made it credible')
s2+=[tb(IN(0.55),IN(1.1),IN(12.3),IN(5.95),[
  para([('Instruments. ',1350,NAVY,True),('WTI (2021-2026) and Brent (2016-2026), local price curves, de-rolled so contract rolls do not create fake jumps.',1350,INK,False)],bullet=True),
  para([('Positioning. ',1350,NAVY,True),('CFTC Managed Money net, plus the structural columns: gross positions, trader counts, open interest, weekly flows. Brent positioning uses the CFTC NYMEX Brent Last Day proxy (ICE\'s own COT is gated).',1350,INK,False)],bullet=True),
  para([('Factors and returns. ',1350,NAVY,True),('all known at the Friday close; forward returns at 1, 2 and 4 weeks versus the base rate.',1350,INK,False)],bullet=True),
  para([('Validation. ',1350,NAVY,True),('block-bootstrap p-values, and replication across two independent crude markets. Single-market results are treated as fragile.',1350,INK,False)],bullet=True),
  para([('Cross-check. ',1350,NAVY,True),('an independent study on 2019-2021 CME data reached similar structural conclusions; where our newer, longer sample disagrees (e.g. the Other-Reportables contrarian tilt), we flag it as regime-specific rather than durable.',1350,INK,False)],bullet=True)])]

# S3 positioning
s3=band('Positioning is coincident, and its edges do not generalize')
s3+=[L(IN(0.3),IN(1.05),IN(7.7),IN(5.75),'chart_replication.png')]
s3+=[tb(IN(8.15),IN(1.2),IN(4.95),IN(5.6),[
  para([('Momentum, not contrarian.',1450,NAVY,True)]),
  para([('Managed Money adds length as price rises (change in net vs same-week return +0.19, p=0.002). It confirms moves, it does not predict them.',1320,INK,False)],bullet=True),
  para([('Its extremes, staleness and flow looked tradeable on WTI 2021-2026 but collapse to the base rate on Brent.',1320,INK,False)],bullet=True),
  para([('The Other-Reportables "contrarian" tilt seen in 2019-2021 does not hold out of sample (it turns positive on WTI 2021-2026). Category signals are regime-specific.',1320,RED,True)],bullet=True)])]

# S4 curve
s4=band('The one durable price signal: deep backwardation is a headwind')
s4+=[L(IN(0.3),IN(1.05),IN(7.7),IN(5.75),'chart_curve_signal.png')]
s4+=[tb(IN(8.15),IN(1.2),IN(4.95),IN(5.6),[
  para([('Fade deep backwardation, do not chase it.',1450,NAVY,True)]),
  para([('The most backwardated third of weeks precedes weak returns: WTI -2.6%, Brent -0.9% over 4 weeks (bootstrap p<0.01), on both crudes.',1320,GREEN,True)],bullet=True),
  para([('Contango precedes strong gains, but it is rare and episodic (18% of WTI weeks, mostly the 2020 and 2016 crises), so it is not a standing rule.',1320,INK,False)],bullet=True),
  para([('Usable version: treat deep backwardation as a reason to reduce or fade, not a green light.',1320,INK,False)],bullet=True)])]

# S5 crowding
s5=band('Crowding: a risk gauge that net positioning hides')
s5+=[L(IN(0.3),IN(1.05),IN(7.7),IN(5.75),'chart_concentration.png')]
s5+=[tb(IN(8.15),IN(1.2),IN(4.95),IN(5.6),[
  para([('Book size per firm = fragility.',1450,NAVY,True)]),
  para([('Dividing gross positions by the number of firms shows how concentrated each side is.',1320,INK,False)],bullet=True),
  para([('Longs were most crowded in summer 2020 (a recovery bet in very few hands). The short side is the most crowded in the whole sample now (2026): a small, squeeze-prone group.',1320,RED,True)],bullet=True),
  para([('Use: when one side is this concentrated, respect short-covering / squeeze risk in sizing and stops.',1320,INK,False)],bullet=True)])]

# S6 OI
s6=band('Open interest confirms trend quality')
s6+=[L(IN(0.3),IN(1.05),IN(7.7),IN(5.75),'chart_oi_regime.png')]
s6+=[tb(IN(8.15),IN(1.2),IN(4.95),IN(5.6),[
  para([('Is new money behind the move?',1450,NAVY,True)]),
  para([('Crossing the weekly change in open interest with the price change sorts trends by quality.',1320,INK,False)],bullet=True),
  para([('On WTI, price up on RISING open interest (new money in the trend) is the best 4-week continuation (+3.0%). Price up on FALLING open interest (short covering) is the weakest: a lower-quality bounce to fade.',1320,GREEN,True)],bullet=True),
  para([('Weaker and mixed on Brent, so use it as WTI colour rather than a universal rule.',1320,INK,False)],bullet=True)])]

# S7 roll
s7=band('The roll is invisible to COT; watch the curve instead')
s7+=[tb(IN(0.6),IN(1.2),IN(12.1),IN(5.4),[
  para([('A front-month roll closes CL1 and reopens CL2. It is net-neutral, and it is not a CFTC "spread" (which needs simultaneous long and short legs), so weekly positioning literally cannot see it. Positioning in the pre-expiry week looks like any other week (our test: Managed Money net and %-spreading are statistically unchanged into the roll).',1450,INK,False)],bullet=True),
  para([('The roll\'s risk lives in the CL1 minus CL2 spread, not in the COT. It is orderly in normal cycles but carries severe tail risk at stressed expiries (the April-2020 negative-price roll printed roughly -58 $/bbl the day before expiry).',1450,INK,False)],bullet=True),
  para([('Practical use: ',1450,NAVY,True),('do not look for a roll signal in positioning. Read the spread, and roll a few sessions early to cut delivery and squeeze exposure. Our WTI data shows a mild pre-expiry softening that is worse when funds are crowded long, but it is small and not significant.',1450,INK,False)],bullet=True)])]

# S8b equations (WTI conditioning + staleness)
seq=band('WTI conditioning rules, written as equations')
seq+=[LM(IN(0.3),IN(1.05),IN(6.05),IN(4.55),'deep_grid.png')]
seq+=[tb(IN(6.5),IN(1.0),IN(6.6),IN(4.7),[
  para([('Next 4 weeks on WTI 2021-2026. Base rate +2.2% (52% hit).',1150,GREY,False)],sa=260),
  para([('MARKET x POSITION',1300,NAVY,True)],sa=240),
  para([('Calm market + Light position',1250,INK,True),('  =  CL +2.9%  (56% hit)',1250,GREEN,True)],bullet=True,sa=200),
  para([('Calm market + Crowded long',1250,INK,True),('  =  CL +1.9%  (51% hit)',1250,GREEN,True)],bullet=True,sa=200),
  para([('Choppy market + Light position',1250,INK,True),('  =  CL +1.6%  (52% hit)',1250,INK,True)],bullet=True,sa=200),
  para([('Choppy market + Crowded long',1250,INK,True),('  =  CL +2.5% but 47% hit (coin-flip)',1250,RED,True)],bullet=True,sa=240),
  para([('STALENESS (how long the bet has lasted)',1300,NAVY,True)],sa=240),
  para([('Fresh crowded long',1250,INK,True),('  =  CL +9.0%  (80% hit, ride it)',1250,GREEN,True)],bullet=True,sa=200),
  para([('Crowded long, gone STALE',1250,INK,True),('  =  CL ~0%  (33% hit, step aside)',1250,RED,True)],bullet=True,sa=200),
  para([('Light book, gone STALE',1250,INK,True),('  =  CL +3.8%  (63% hit, accumulate)',1250,GREEN,True)],bullet=True,sa=200)])]
seq+=[tb(IN(0.3),IN(5.78),IN(12.8),IN(1.05),[para([('Read as WTI desk colour, not universal law: ',1050,NAVY,True),
  ('these conditioning and staleness effects are strong on WTI 2021-2026 but do not replicate on Brent. Use them to size and time WTI risk on top of your main factors, never as standalone triggers.',1050,GREY,False)],line=100000)],fill='F2F5F7')]

# S8c curve + expiry equations
seq2=band('Curve (CL1-CL2) and expiry, written as equations')
seq2+=[L(IN(0.3),IN(1.05),IN(5.75),IN(4.5),'chart_regime_grid.png')]
seq2+=[tb(IN(6.15),IN(1.0),IN(6.95),IN(4.75),[
  para([('CALENDAR SPREAD  (CL1 minus CL2), next 4 weeks',1250,NAVY,True)],sa=220),
  para([('Near / in contango (least backwardated third)',1200,INK,True),('  =  +4.6% (67% hit) | Brent +3.1%',1200,GREEN,True)],bullet=True,sa=170),
  para([('Deep backwardation (tightest third)',1200,INK,True),('  =  -2.6% (29% hit) | Brent -0.9%',1200,RED,True)],bullet=True,sa=170),
  para([('Contango + High volatility',1200,INK,True),('  =  +3.7% | Brent +4.8%  (best long, both crudes)',1200,GREEN,True)],bullet=True,sa=170),
  para([('Deep backwardation + High volatility',1200,INK,True),('  =  +0.1% | Brent +0.3%  (~flat, stand aside)',1200,RED,True)],bullet=True,sa=280),
  para([('EXPIRY WINDOW  (last ~7 days, WTI/NYMEX rule)',1250,NAVY,True)],sa=220),
  para([('Crowded long into expiry',1200,INK,True),('  =  CL -1.4%, then +0.9% after (roll / de-risk)',1200,GOLD,True)],bullet=True,sa=170),
  para([('Light book into expiry',1200,INK,True),('  =  CL +0.7%',1200,GREEN,True)],bullet=True,sa=170),
  para([('All expiries pooled',1200,INK,True),('  =  CL -0.3% (mild, NOT significant; base +0.3%)',1200,GREY,True)],bullet=True,sa=170)])]
seq2+=[tb(IN(0.3),IN(5.72),IN(12.8),IN(1.15),[para([('Squeeze logic: ',1050,NAVY,True),
  ('the crowded side is the one forced to unwind into expiry. Measured here it is crowded LONGS de-risking (mild selling, rebounds after); the mirror image is a crowded SHORT book (where WTI sits now) that risks a squeeze HIGHER. The effect is small and not significant (t=-0.69), Brent uses the WTI expiry rule so it is only a proxy, and true contango is just ~18% of WTI weeks (the label is a tercile).',1050,GREY,False)],line=100000)],fill='F2F5F7')]

# S8 playbook
s8=band('Playbook: overlays for your main factors')
s8+=[tb(IN(0.45),IN(1.05),IN(6.3),IN(5.3),[
  para([('USE AS OVERLAYS',1350,NAVY,True)]),
  para([('Deep backwardation',1250,INK,True),('  =  headwind, fade or reduce longs',1250,RED,True)],bullet=True),
  para([('Contango (rare)',1250,INK,True),('  =  tailwind, opportunistic only',1250,GREEN,True)],bullet=True),
  para([('One side extremely crowded (shorts now)',1250,INK,True),('  =  squeeze risk, tighten risk, expect sharp counter-moves',1250,RED,True)],bullet=True),
  para([('Price up + OI up (WTI)',1250,INK,True),('  =  quality uptrend, stay / add',1250,GREEN,True)],bullet=True),
  para([('Price up + OI down',1250,INK,True),('  =  covering bounce, fade',1250,RED,True)],bullet=True),
  para([('Crowded into the expiry week',1250,INK,True),('  =  roll early, expect de-risk softness then rebound',1250,GOLD,True)],bullet=True)])]
s8+=[tb(IN(6.95),IN(1.05),IN(6.15),IN(5.3),[
  para([('DO NOT',1350,NAVY,True)]),
  para([('Trade Managed Money net extremes as a contrarian signal (it is momentum).',1250,INK,False)],bullet=True),
  para([('Use COT for roll timing (it cannot see the roll).',1250,INK,False)],bullet=True),
  para([('Rely on a single market or single window (demand cross-instrument replication).',1250,INK,False)],bullet=True),
  para([('How to use: ',1250,NAVY,True),('a context and risk layer on top of your primary fundamentals / flow model. It sizes and filters; it does not trigger.',1250,INK,False)],bullet=True)])]
s8+=[tb(IN(0.45),IN(6.4),IN(12.7),IN(0.9),[para([('Caveats: ',1050,RED,True),
  ('Brent positioning is a NYMEX proxy (ICE COT gated); results are gross of costs; much of the apparent positioning edge in prior studies is the 2020 dislocation; the curve edge partly reflects 2021-2026 regimes.',1050,GREY,False)],line=100000)],fill='F2F5F7')]

slides=[sld(s1),sld(s2),sld(s3),sld(s4),sld(s5),sld(s6),sld(s7),sld(seq),sld(seq2),sld(s8)]
slide_imgs={1:[],2:[],3:[('rId2','image1.png')],4:[('rId2','image2.png')],5:[('rId2','image3.png')],6:[('rId2','image4.png')],7:[],8:[('rId2','image5.png')],9:[('rId2','image6.png')],10:[]}
media={'image1.png':os.path.join(CHX,'chart_replication.png'),'image2.png':os.path.join(CHX,'chart_curve_signal.png'),
       'image3.png':os.path.join(CHX,'chart_concentration.png'),'image4.png':os.path.join(CHX,'chart_oi_regime.png'),
       'image5.png':os.path.join(CHM,'deep_grid.png'),'image6.png':os.path.join(CHX,'chart_regime_grid.png')}

THEME=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
 f'<a:theme xmlns:a="{A}" name="Office Theme"><a:themeElements>'
 '<a:clrScheme name="Office"><a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1><a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>'
 '<a:dk2><a:srgbClr val="16324F"/></a:dk2><a:lt2><a:srgbClr val="EEECE1"/></a:lt2>'
 '<a:accent1><a:srgbClr val="16324F"/></a:accent1><a:accent2><a:srgbClr val="C0392B"/></a:accent2><a:accent3><a:srgbClr val="1E8B54"/></a:accent3>'
 '<a:accent4><a:srgbClr val="B07A1E"/></a:accent4><a:accent5><a:srgbClr val="2C6FBB"/></a:accent5><a:accent6><a:srgbClr val="8E44AD"/></a:accent6>'
 '<a:hlink><a:srgbClr val="0563C1"/></a:hlink><a:folHlink><a:srgbClr val="954F72"/></a:folHlink></a:clrScheme>'
 '<a:fontScheme name="Office"><a:majorFont><a:latin typeface="Calibri Light"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>'
 '<a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme>'
 '<a:fmtScheme name="Office"><a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
 '<a:gradFill rotWithShape="1"><a:gsLst><a:gs pos="0"><a:schemeClr val="phClr"><a:lumMod val="110000"/><a:satMod val="105000"/><a:tint val="67000"/></a:schemeClr></a:gs>'
 '<a:gs pos="50000"><a:schemeClr val="phClr"><a:lumMod val="105000"/><a:satMod val="103000"/><a:tint val="73000"/></a:schemeClr></a:gs>'
 '<a:gs pos="100000"><a:schemeClr val="phClr"><a:lumMod val="105000"/><a:satMod val="109000"/><a:tint val="81000"/></a:schemeClr></a:gs></a:gsLst><a:lin ang="5400000" scaled="0"/></a:gradFill>'
 '<a:gradFill rotWithShape="1"><a:gsLst><a:gs pos="0"><a:schemeClr val="phClr"><a:satMod val="103000"/><a:lumMod val="102000"/><a:tint val="94000"/></a:schemeClr></a:gs>'
 '<a:gs pos="50000"><a:schemeClr val="phClr"><a:satMod val="110000"/><a:lumMod val="100000"/><a:shade val="100000"/></a:schemeClr></a:gs>'
 '<a:gs pos="100000"><a:schemeClr val="phClr"><a:lumMod val="99000"/><a:satMod val="120000"/><a:shade val="78000"/></a:schemeClr></a:gs></a:gsLst><a:lin ang="5400000" scaled="0"/></a:gradFill></a:fillStyleLst>'
 '<a:lnStyleLst><a:ln w="6350" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/><a:miter lim="800000"/></a:ln>'
 '<a:ln w="12700" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/><a:miter lim="800000"/></a:ln>'
 '<a:ln w="19050" cap="flat" cmpd="sng" algn="ctr"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/><a:miter lim="800000"/></a:ln></a:lnStyleLst>'
 '<a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle>'
 '<a:effectStyle><a:effectLst><a:outerShdw blurRad="57150" dist="19050" dir="5400000" rotWithShape="0"><a:srgbClr val="000000"><a:alpha val="63000"/></a:srgbClr></a:outerShdw></a:effectLst></a:effectStyle></a:effectStyleLst>'
 '<a:bgFillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
 '<a:solidFill><a:schemeClr val="phClr"><a:tint val="95000"/><a:satMod val="170000"/></a:schemeClr></a:solidFill>'
 '<a:gradFill rotWithShape="1"><a:gsLst><a:gs pos="0"><a:schemeClr val="phClr"><a:tint val="93000"/><a:satMod val="150000"/><a:shade val="98000"/><a:lumMod val="102000"/></a:schemeClr></a:gs>'
 '<a:gs pos="50000"><a:schemeClr val="phClr"><a:tint val="98000"/><a:satMod val="130000"/><a:shade val="90000"/><a:lumMod val="103000"/></a:schemeClr></a:gs>'
 '<a:gs pos="100000"><a:schemeClr val="phClr"><a:shade val="63000"/><a:satMod val="120000"/></a:schemeClr></a:gs></a:gsLst><a:lin ang="5400000" scaled="0"/></a:gradFill></a:bgFillStyleLst>'
 '</a:fmtScheme></a:themeElements></a:theme>')
MASTER=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
 f'<p:sldMaster xmlns:a="{A}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
 '<p:cSld><p:bg><p:bgPr><a:solidFill><a:schemeClr val="bg1"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>'
 '<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
 '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld>'
 '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
 '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
 '<p:txStyles><p:titleStyle><a:lvl1pPr><a:defRPr sz="4400"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill><a:latin typeface="+mj-lt"/></a:defRPr></a:lvl1pPr></p:titleStyle>'
 '<p:bodyStyle><a:lvl1pPr><a:defRPr sz="1800"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill><a:latin typeface="+mn-lt"/></a:defRPr></a:lvl1pPr></p:bodyStyle>'
 '<p:otherStyle><a:lvl1pPr><a:defRPr sz="1800"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill></a:defRPr></a:lvl1pPr></p:otherStyle></p:txStyles></p:sldMaster>')
LAYOUT=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
 f'<p:sldLayout xmlns:a="{A}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1">'
 '<p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
 '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld>'
 '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>')
PRES=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
 f'<p:presentation xmlns:a="{A}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" saveSubsetFonts="1">'
 '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
 '<p:sldIdLst>'+''.join(f'<p:sldId id="{256+i}" r:id="rId{2+i}"/>' for i in range(NSLIDES))+'</p:sldIdLst>'
 f'<p:sldSz cx="{SW}" cy="{SH}" type="screen16x9"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>')
CT=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
 '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
 '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
 '<Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/>'
 '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
 '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
 '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
 '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
 +''.join(f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>' for i in range(1,NSLIDES+1))+'</Types>')
RELS_ROOT=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/></Relationships>')
PRES_RELS=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>'
 +''.join(f'<Relationship Id="rId{2+i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{1+i}.xml"/>' for i in range(NSLIDES))+
 f'<Relationship Id="rId{2+NSLIDES}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/></Relationships>')
MASTER_RELS=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
 '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/></Relationships>')
LAYOUT_RELS=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/></Relationships>')
def slide_rels(imgs):
    r=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
       '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>')
    for rid,fn in imgs: r+=f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/{fn}"/>'
    return r+'</Relationships>'
with zipfile.ZipFile(PPTX,'w',zipfile.ZIP_DEFLATED) as z:
    z.writestr('[Content_Types].xml',CT); z.writestr('_rels/.rels',RELS_ROOT)
    z.writestr('ppt/presentation.xml',PRES); z.writestr('ppt/_rels/presentation.xml.rels',PRES_RELS)
    z.writestr('ppt/theme/theme1.xml',THEME)
    z.writestr('ppt/slideMasters/slideMaster1.xml',MASTER); z.writestr('ppt/slideMasters/_rels/slideMaster1.xml.rels',MASTER_RELS)
    z.writestr('ppt/slideLayouts/slideLayout1.xml',LAYOUT); z.writestr('ppt/slideLayouts/_rels/slideLayout1.xml.rels',LAYOUT_RELS)
    for i,sx in enumerate(slides,1):
        z.writestr(f'ppt/slides/slide{i}.xml',sx); z.writestr(f'ppt/slides/_rels/slide{i}.xml.rels',slide_rels(slide_imgs[i]))
    for fn,src in media.items(): z.write(src,f'ppt/media/{fn}')
print('wrote',PPTX)
from lxml import etree
bad=0
with zipfile.ZipFile(PPTX) as z:
    assert z.testzip() is None
    for n in z.namelist():
        if n.endswith(('.xml','.rels')):
            try: etree.fromstring(z.read(n))
            except Exception as e: bad+=1; print('XMLERR',n,e)
    print('parts',len(z.namelist()),'xml-errors',bad)
