"""Combined trading deck: positioning + forward curve + regime edge + Brent + expiry. 7 slides, offline pptx."""
import os, zipfile
from PIL import Image
ROOT=r"c:/Users/aayush.jhawar/OneDrive - hertshtengroup.com/Desktop/Dashboard_v3"
BASE=os.path.join(ROOT,"cftc_positioning_analysis")
CHX=os.path.join(BASE,"extended_analysis","charts"); CHM=os.path.join(BASE,"cftc_managed_money_analysis","charts")
PPTX=os.path.join(BASE,"WTI_Brent_positioning_curve_regime.pptx")
A='http://schemas.openxmlformats.org/drawingml/2006/main'; EMU_IN=914400; SW,SH=12192000,6858000
NSLIDES=7
def esc(s): return s.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
NAVY='16324F'; INK='1A1A1A'; GREEN='1E8B54'; RED='C0392B'; GOLD='B07A1E'; BLUE='2C6FBB'; GREY='5D6D7E'
IN=lambda v:int(v*EMU_IN)
def fit(p,bx,by,bw,bh):
    w,h=Image.open(p).size; s=min(bw/w,bh/h); return bx+(bw-int(w*s))//2,by+(bh-int(h*s))//2,int(w*s),int(h*s)
_sid=[10]
def nid(): _sid[0]+=1; return _sid[0]
def pic(rid,x,y,cx,cy,name="img"):
    return (f'<p:pic><p:nvPicPr><p:cNvPr id="{nid()}" name="{name}"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
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
def band(t,sz=2200): return [tb(0,0,SW,IN(0.9),[para([(t,sz,'FFFFFF',True)])],fill=NAVY,anchor='ctr')]

# S1
s1=[tb(0,0,SW,IN(1.7),[para([('Crude positioning, the forward curve, and a regime edge',2350,'FFFFFF',True)]),
     para([('Managed Money vs WTI and Brent  |  with a tradeable overlay',1250,'D9E2EA',False)])],fill=NAVY,anchor='ctr')]
s1+=[tb(IN(0.55),IN(1.95),IN(12.3),IN(1.05),[para([
     ('Positioning alone is a weak, regime-specific signal. The forward ',1750,INK,False),('curve',1750,GOLD,True),
     (' is the robust driver, and ',1750,INK,False),('curve + volatility',1750,GREEN,True),(' give a cross-validated edge.',1750,INK,False)],line=100000)])]
s1+=[tb(IN(0.55),IN(3.05),IN(12.3),IN(3.4),[
   para([('Positioning extremes and staleness looked strong on WTI 2021-2026 but did NOT replicate on Brent. Use positioning as context, not a trigger.',1400,INK,False)],bullet=True),
   para([('The curve does travel: contango precedes gains, backwardation precedes weakness, on both crudes.',1400,INK,False)],bullet=True),
   para([('The tradeable regime: Contango + High volatility precedes strong gains (WTI +3.7%, Brent +4.8% per 4 weeks, ~67% hit, Brent p=0.02).',1400,GREEN,True)],bullet=True),
   para([('Deploy it as an overlay on your main factors, with positioning as a secondary confirmer.',1400,INK,False)],bullet=True)])]
s1+=[tb(IN(0.55),IN(6.55),IN(12.3),IN(0.6),[para([('CFTC Managed Money. WTI local curve 2021-2026, Brent (ICE price) 2016-2026. No look-ahead; validated by bootstrap and cross-instrument replication.',1000,GREY,False)])],fill='F2F5F7')]

# S2 method
s2=band('How we tested it, and how we made it credible')
s2+=[tb(IN(0.55),IN(1.1),IN(12.3),IN(5.95),[
  para([('Instruments. ',1400,NAVY,True),('WTI (local front curve, 2021-2026) and Brent (local ICE settle curve, 2016-2026). Returns are de-rolled so contract rolls do not create fake jumps.',1400,INK,False)],bullet=True),
  para([('Positioning. ',1400,NAVY,True),('CFTC Managed Money net. Brent uses the CFTC NYMEX Brent Last Day series as a proxy, because ICE\'s own Brent COT is gated; z-scoring makes the size comparable.',1400,INK,False)],bullet=True),
  para([('Factors (all known at the Friday close, no hindsight). ',1400,NAVY,True),('curve shape (C1 minus C2), volatility (trailing realized), positioning (52-week z-score).',1400,INK,False)],bullet=True),
  para([('Tests. ',1400,NAVY,True),('extremes via z-score and top/bottom 10%; forward returns at 1, 2 and 4 weeks versus the base rate.',1400,INK,False)],bullet=True),
  para([('Validation. ',1400,NAVY,True),('block-bootstrap p-values, and most importantly, replication across two independent crude markets. A signal that shows up in only one is treated as fragile.',1400,INK,False)],bullet=True)])]

# S3 positioning alone
s3=band('Positioning alone is weak and does not generalize')
x,y,cx,cy=fit(os.path.join(CHX,'chart_replication.png'),IN(0.3),IN(1.05),IN(7.7),IN(5.75)); s3+=[pic('rId2',x,y,cx,cy)]
s3+=[tb(IN(8.15),IN(1.2),IN(4.95),IN(5.6),[
  para([('WTI in-sample vs Brent out-of-sample.',1500,NAVY,True)]),
  para([('On WTI 2021-2026, crowded longs, staleness and fast unwinds all looked tradeable.',1350,INK,False)],bullet=True),
  para([('On Brent 2016-2026, a longer and independent sample, those same signals collapse to the base rate or flip sign.',1350,INK,False)],bullet=True),
  para([('Lesson: the WTI positioning edges were regime and sample specific. Positioning is a context and risk gauge, not a standalone timing signal.',1350,RED,True)],bullet=True)])]

# S4 curve
s4=band('The forward curve is the signal that travels')
x,y,cx,cy=fit(os.path.join(CHX,'chart_curve_signal.png'),IN(0.3),IN(1.05),IN(7.7),IN(5.75)); s4+=[pic('rId2',x,y,cx,cy)]
s4+=[tb(IN(8.15),IN(1.2),IN(4.95),IN(5.6),[
  para([('Contango up, backwardation down.',1500,NAVY,True)]),
  para([('Sorting weeks by the C1 minus C2 spread: contango (oversupply) precedes a rally; backwardation (tight) precedes weakness.',1350,INK,False)],bullet=True),
  para([('WTI: contango +4.6%, backwardation -2.6% over 4 weeks. Brent: +3.1% versus -0.9%.',1350,INK,False)],bullet=True),
  para([('It holds on both crudes, so it is far more credible than the single-instrument positioning results.',1350,INK,False)],bullet=True)])]

# S5 regime
s5=band('The tradeable edge: Contango + High volatility')
x,y,cx,cy=fit(os.path.join(CHX,'chart_regime_grid.png'),IN(0.25),IN(1.05),IN(9.3),IN(4.4)); s5+=[pic('rId2',x,y,cx,cy)]
s5+=[tb(IN(9.7),IN(1.1),IN(3.4),IN(5.7),[
  para([('Buy the stressed, oversupplied tape.',1450,NAVY,True)]),
  para([('When the curve is in contango AND volatility is high, crude rebounds hard.',1300,INK,False)],bullet=True),
  para([('WTI +3.7% (69% hit, n=36); Brent +4.8% (67% hit, n=109, p=0.02) over 4 weeks vs a ~1.4% base rate.',1300,GREEN,True)],bullet=True),
  para([('The opposite corner, backwardation + high vol, gives about 0%: do not chase a tight, volatile market.',1300,RED,True)],bullet=True)])]
s5+=[tb(IN(0.3),IN(5.6),IN(9.2),IN(1.2),[para([('Boxed cell = the edge, and it agrees across both crudes (which is the real robustness test, given single-signal t-stats are weak).',1150,GREY,False)])],fill='F2F5F7')]

# S6 positioning confirmer + expiry
s6=band('Where positioning still adds value')
x,y,cx,cy=fit(os.path.join(CHM,'deep_persistence.png'),IN(0.3),IN(1.1),IN(7.3),IN(5.5)); s6+=[pic('rId2',x,y,cx,cy)]
s6+=[tb(IN(7.75),IN(1.2),IN(5.35),IN(5.6),[
  para([('Use positioning to size, not to trigger.',1450,NAVY,True)]),
  para([('Confirmer: within contango, heavier Managed Money longs coincide with the strongest returns (WTI contango + crowded +5.4%).',1330,INK,False)],bullet=True),
  para([('Staleness (WTI, chart): a fresh crowded long ran about +9% over 4 weeks, a stale one stalled. Useful colour, but WTI-specific.',1330,INK,False)],bullet=True),
  para([('Expiry (WTI): price softens mildly into the monthly expiry (3 business days before the 25th), more so when crowded long (-1.4% vs +0.7%), then recovers. Small tweak, not significant. Brent expires differently.',1330,INK,False)],bullet=True)])]

# S7 playbook
s7=band('Playbook: use this alongside your main factors')
s7+=[tb(IN(0.5),IN(1.05),IN(6.15),IN(5.4),[
  para([('PRIMARY  (curve + volatility, cross-validated)',1400,NAVY,True)]),
  para([('Contango + High vol',1300,INK,True),('   =  go long / add  (WTI +3.7%, Brent +4.8% per 4wk, ~67% hit)',1300,GREEN,True)],bullet=True),
  para([('Backwardation + High vol',1300,INK,True),('   =  stand aside  (~0%)',1300,RED,True)],bullet=True),
  para([('Contango (any)',1300,INK,True),('   =  long bias  (+3 to +4.6%)',1300,GREEN,True)],bullet=True),
  para([('Backwardation (any)',1300,INK,True),('   =  neutral to short bias',1300,INK,True)],bullet=True)])]
s7+=[tb(IN(6.85),IN(1.05),IN(6.25),IN(5.4),[
  para([('SECONDARY  (positioning, confirmation only)',1400,NAVY,True)]),
  para([('Crowded long inside contango',1300,INK,True),('  =  confirms the long',1300,GREEN,True)],bullet=True),
  para([('Crowded long inside backwardation',1300,INK,True),('  =  weakest, avoid adding',1300,RED,True)],bullet=True),
  para([('Trim WTI longs into monthly expiry when crowded.',1300,INK,False)],bullet=True),
  para([('How to use: ',1300,NAVY,True),('let the curve + vol regime set bias and size; let positioning confirm; never trade positioning alone.',1300,INK,False)],bullet=True)])]
s7+=[tb(IN(0.5),IN(6.35),IN(12.6),IN(0.95),[para([('Caveats: ',1100,RED,True),
  ('Brent positioning is a NYMEX proxy (ICE COT gated); the curve edge partly reflects the 2020 and 2022 regimes; results are gross of costs; positioning does not generalize across crudes.',1100,GREY,False)],line=100000)],fill='F2F5F7')]

slides=[sld(s1),sld(s2),sld(s3),sld(s4),sld(s5),sld(s6),sld(s7)]
slide_imgs={1:[],2:[],3:[('rId2','image1.png')],4:[('rId2','image2.png')],5:[('rId2','image3.png')],6:[('rId2','image4.png')],7:[]}
media={'image1.png':os.path.join(CHX,'chart_replication.png'),'image2.png':os.path.join(CHX,'chart_curve_signal.png'),
       'image3.png':os.path.join(CHX,'chart_regime_grid.png'),'image4.png':os.path.join(CHM,'deep_persistence.png')}

# ---- static OOXML ----
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
