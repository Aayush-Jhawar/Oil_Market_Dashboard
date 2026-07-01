"""Polished, self-explanatory Managed Money DEEP deck (offline pptx, no em dashes)."""
import os, zipfile
from PIL import Image
ROOT=r"c:/Users/aayush.jhawar/OneDrive - hertshtengroup.com/Desktop/Dashboard_v3"
OUTDIR=os.path.join(ROOT,"cftc_positioning_analysis","cftc_managed_money_analysis"); CH=os.path.join(OUTDIR,"charts")
PPTX=os.path.join(OUTDIR,"WTI_ManagedMoney_DEEP_positioning.pptx")
EMU_IN=914400; SW,SH=12192000,6858000
A='http://schemas.openxmlformats.org/drawingml/2006/main'
def esc(s): return s.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
NAVY='16324F'; INK='1A1A1A'; GREEN='1E8B54'; RED='C0392B'; GOLD='B07A1E'; TEAL='1D6F66'; GREY='5D6D7E'
IN=lambda v:int(v*EMU_IN)
def fit(p,bx,by,bw,bh):
    w,h=Image.open(p).size; s=min(bw/w,bh/h); cx,cy=int(w*s),int(h*s)
    return bx+(bw-cx)//2,by+(bh-cy)//2,cx,cy
_sid=[10]
def nid(): _sid[0]+=1; return _sid[0]
def pic(rid,x,y,cx,cy,name="img"):
    return (f'<p:pic><p:nvPicPr><p:cNvPr id="{nid()}" name="{name}"/>'
            f'<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
            f'<p:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>'
            f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>')
def para(runs,bullet=False,space_after=500,align='l',line=None):
    bu=('<a:buFont typeface="Arial"/><a:buChar char="&#8226;"/>' if bullet else '<a:buNone/>')
    ind=' indent="-228600" marL="274320"' if bullet else ''
    ln=f'<a:lnSpc><a:spcPct val="{line}"/></a:lnSpc>' if line else ''
    rx=''
    for txt,sz,color,b in runs:
        rx+=(f'<a:r><a:rPr lang="en-US" sz="{sz}" b="{1 if b else 0}" dirty="0">'
             f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill><a:latin typeface="Calibri"/></a:rPr><a:t>{esc(txt)}</a:t></a:r>')
    return f'<a:p><a:pPr algn="{align}"{ind}>{ln}<a:spcAft><a:spcPts val="{space_after}"/></a:spcAft>{bu}</a:pPr>{rx}</a:p>'
def textbox(x,y,cx,cy,paras,name="tx",fill=None,anchor='t',line=None):
    sf=f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>' if fill else '<a:noFill/>'
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{nid()}" name="{name}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>{sf}</p:spPr>'
            f'<p:txBody><a:bodyPr wrap="square" lIns="100000" tIns="55000" rIns="100000" bIns="55000" anchor="{anchor}"><a:normAutofit/></a:bodyPr>'
            f'<a:lstStyle/>{"".join(paras)}</p:txBody></p:sp>')
def slide_xml(shapes,bg='FFFFFF'):
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<p:sld xmlns:a="{A}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            f'<p:cSld><p:bg><p:bgPr><a:solidFill><a:srgbClr val="{bg}"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>'
            '<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
            f'{"".join(shapes)}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>')
def band(t):  # title bar
    return [textbox(0,0,SW,IN(0.9),[para([(t,2300,'FFFFFF',True)])],fill=NAVY,anchor='ctr')]

# ===== S1 =====
s1=[textbox(0,0,SW,IN(1.7),[para([('Do oil speculators’ bets predict WTI prices?',2500,'FFFFFF',True)]),
      para([('Managed Money positioning in WTI crude   |   2021 to 2026',1300,'D9E2EA',False)])],fill=NAVY,anchor='ctr')]
s1+=[textbox(IN(0.6),IN(2.0),IN(12.1),IN(1.25),[para([
      ('On its own, no. But once you know how ',1900,INK,False),('STALE',1900,GOLD,True),
      (' the positioning is and how ',1900,INK,False),('CALM',1900,TEAL,True),
      (' the market is, clear and usable patterns appear.',1900,INK,False)],line=100000)])]
s1+=[textbox(IN(0.6),IN(3.35),IN(12.1),IN(2.5),[
   para([('Fresh crowding keeps rising; once it has been crowded for a month it stalls.',1500,INK,False)],bullet=True),
   para([('A book that stays light for a month tends to set up a rebound.',1500,INK,False)],bullet=True),
   para([('A calm market with light positioning is the steadiest setup for gains (+2.9% over 4 weeks).',1500,INK,False)],bullet=True),
])]
s1+=[textbox(IN(0.6),IN(5.95),IN(12.1),IN(1.0),[
   para([('In plain terms:  ',1250,NAVY,True),
         ('"Managed Money" = the large speculative funds.  "Net position" = how much they are betting prices rise, minus betting they fall.',1250,GREY,False)],line=100000)],
   fill='F2F5F7')]

# ===== S2 method =====
s2=band('What we measured, in plain terms')
s2+=[textbox(IN(0.6),IN(1.1),IN(12.1),IN(5.95),[
  para([('The data. ',1450,NAVY,True),('Each week the US regulator (CFTC) reports how heavily the big funds are betting on WTI. We pulled the real Managed Money series straight from the CFTC archive.',1450,INK,False)],bullet=True),
  para([('The price. ',1450,NAVY,True),('WTI front-month crude, 2021 to 2026.',1450,INK,False)],bullet=True),
  para([('"Extreme" positioning. ',1450,NAVY,True),('The most-long and least-long weeks (top and bottom 10%), and a z-score that says how unusual this week is versus the past year.',1450,INK,False)],bullet=True),
  para([('A fair test. ',1450,NAVY,True),('The data is measured on a Tuesday but only published on the Friday, so we only ever act from the Friday close. No hindsight.',1450,INK,False)],bullet=True),
  para([('The deeper cuts. ',1450,NAVY,True),('How long positioning stays extreme (its staleness), and whether the market is calm or choppy (volatility).',1450,INK,False)],bullet=True),
  para([('Is it real? ',1450,NAVY,True),('We measure WTI 1, 2 and 4 weeks later versus an average week, and check it with t-tests and bootstrap resampling.',1450,INK,False)],bullet=True),
])]

# ===== S3 basic relationship =====
s3=band('First look: stretched bets lean gently against price')
x,y,cx,cy=fit(os.path.join(CH,'mm_chart1_position_vs_wti.png'),IN(0.25),IN(1.0),IN(6.5),IN(4.6)); s3+=[pic('rId2',x,y,cx,cy,'rel')]
x,y,cx,cy=fit(os.path.join(CH,'deep_extremes.png'),IN(6.85),IN(1.0),IN(6.25),IN(4.6)); s3+=[pic('rId3',x,y,cx,cy,'ext')]
s3+=[textbox(IN(0.5),IN(5.7),IN(12.4),IN(1.4),[
  para([('When the funds are most long, WTI tends to slip over the next month (about -2.1%). When they are least long, it tends to rise (about +3.4%).',1350,INK,True)],bullet=True),
  para([('Useful, but gentle. The size of the bet on its own is a weak timer. The stronger signal is on the next slide.',1300,GREY,False)],bullet=True),
])]

# ===== S4 hero persistence =====
s4=band('The key: it is the staleness, not the size')
x,y,cx,cy=fit(os.path.join(CH,'deep_persistence.png'),IN(0.25),IN(1.0),IN(7.7),IN(5.85)); s4+=[pic('rId2',x,y,cx,cy,'pers')]
s4+=[textbox(IN(8.05),IN(1.15),IN(5.05),IN(5.7),[
  para([('Same bet, opposite meaning.',1550,NAVY,True)]),
  para([('A FRESH crowded long keeps rising: +9.0% over the next 4 weeks (80% hit). Ride it.',1380,GOLD,True)],bullet=True),
  para([('Once it has been crowded for a month it is exhausted: -0.8% (33% hit). Step aside.',1380,GOLD,True)],bullet=True),
  para([('A book that has stayed LIGHT for a month tends to rebound: +3.8% (63% hit). Accumulate.',1380,TEAL,True)],bullet=True),
  para([('So how long the positioning has lasted flips the conclusion. This staleness effect is the real signal.',1380,INK,False)],bullet=True),
])]

# ===== S5 playbook / equations =====
s5=band('The playbook: simple equations')
x,y,cx,cy=fit(os.path.join(CH,'deep_grid.png'),IN(0.3),IN(1.05),IN(6.2),IN(4.5)); s5+=[pic('rId2',x,y,cx,cy,'grid')]
s5+=[textbox(IN(6.7),IN(1.0),IN(6.4),IN(4.7),[
  para([('Conditioning rules (next 4 weeks)',1450,NAVY,True)]),
  para([('Calm market + Light position',1350,INK,True),('  =  CL +2.9%  (56% hit)',1350,GREEN,True)],bullet=True),
  para([('Calm market + Crowded long',1350,INK,True),('  =  CL +1.9%  (51% hit)',1350,GREEN,True)],bullet=True),
  para([('Choppy market + Light position',1350,INK,True),('  =  CL +1.6%  (52% hit)',1350,INK,True)],bullet=True),
  para([('Choppy market + Crowded long',1350,INK,True),('  =  CL +2.5% but only 47% hit (coin-flip)',1350,RED,True)],bullet=True),
  para([('Fresh crowded long',1350,INK,True),('  =  CL +9.0%  (80% hit, ride momentum)',1350,GREEN,True)],bullet=True),
  para([('Crowded long, gone STALE',1350,INK,True),('  =  CL ~0%  (33% hit, step aside)',1350,RED,True)],bullet=True),
  para([('Light book, gone STALE',1350,INK,True),('  =  CL +3.8%  (63% hit, accumulate)',1350,GREEN,True)],bullet=True),
])]
s5+=[textbox(IN(0.3),IN(5.75),IN(12.8),IN(1.25),[
  para([('Desk use: ',1200,NAVY,True),('size with volatility, ride fresh extremes, fade stale ones. ',1200,INK,False),
        ('Caveats: ',1200,RED,True),('2021 to 2026 only, extreme-long has few episodes, returns are gross of costs. The full 2016 to 2026 sample would make the equations firmer.',1200,GREY,False)],line=100000)],fill='F2F5F7')]

slides=[slide_xml(s1),slide_xml(s2),slide_xml(s3),slide_xml(s4),slide_xml(s5)]
slide_imgs={1:[],2:[],3:[('rId2','image1.png'),('rId3','image2.png')],4:[('rId2','image3.png')],5:[('rId2','image4.png')]}
media={'image1.png':'mm_chart1_position_vs_wti.png','image2.png':'deep_extremes.png','image3.png':'deep_persistence.png','image4.png':'deep_grid.png'}

# ---- proven static OOXML ----
THEME=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
 f'<a:theme xmlns:a="{A}" name="Office Theme"><a:themeElements>'
 '<a:clrScheme name="Office"><a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1><a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>'
 '<a:dk2><a:srgbClr val="16324F"/></a:dk2><a:lt2><a:srgbClr val="EEECE1"/></a:lt2>'
 '<a:accent1><a:srgbClr val="16324F"/></a:accent1><a:accent2><a:srgbClr val="C0392B"/></a:accent2><a:accent3><a:srgbClr val="1E8B54"/></a:accent3>'
 '<a:accent4><a:srgbClr val="B07A1E"/></a:accent4><a:accent5><a:srgbClr val="1D6F66"/></a:accent5><a:accent6><a:srgbClr val="8E44AD"/></a:accent6>'
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
 '<p:sldIdLst>'+''.join(f'<p:sldId id="{256+i}" r:id="rId{2+i}"/>' for i in range(5))+'</p:sldIdLst>'
 f'<p:sldSz cx="{SW}" cy="{SH}" type="screen16x9"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>')
CT=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
 '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
 '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
 '<Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/>'
 '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
 '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
 '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
 '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
 +''.join(f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>' for i in range(1,6))+'</Types>')
RELS_ROOT=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/></Relationships>')
PRES_RELS=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>'
 +''.join(f'<Relationship Id="rId{2+i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{1+i}.xml"/>' for i in range(5))+
 '<Relationship Id="rId7" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="theme/theme1.xml"/></Relationships>')
MASTER_RELS=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
 '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/></Relationships>')
LAYOUT_RELS=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/></Relationships>')
def slide_rels(imgs):
    r=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
       '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
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
    for fn,src in media.items(): z.write(os.path.join(CH,src),f'ppt/media/{fn}')
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
