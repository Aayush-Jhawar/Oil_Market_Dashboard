"""STEP 8 (v2): hand-build a valid .pptx (offline, no python-pptx).
Humanised prose, no em dashes. 5 slides, verdict-first, with the flow/capitulation finding."""
import os, zipfile
from PIL import Image

ROOT = r"c:/Users/aayush.jhawar/OneDrive - hertshtengroup.com/Desktop/Dashboard_v3"
OUTDIR = os.path.join(ROOT, "cftc_positioning_analysis", "cftc_or_wti_analysis")
CH = os.path.join(OUTDIR, "charts")
PPTX = os.path.join(OUTDIR, "WTI_OtherReportables_positioning_study_v2.pptx")
EMU_IN = 914400
SW, SH = 12192000, 6858000
A='http://schemas.openxmlformats.org/drawingml/2006/main'
def esc(s): return s.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
NAVY='1F3B57'; RED='C0392B'; GREEN='1E8449'; GREY='5D6D7E'; DARK='1A1A1A'
IN=lambda v:int(v*EMU_IN)

def fit(p,bx,by,bw,bh):
    w,h=Image.open(p).size; s=min(bw/w,bh/h); cx,cy=int(w*s),int(h*s)
    return bx+(bw-cx)//2, by+(bh-cy)//2, cx, cy
_sid=[10]
def nid(): _sid[0]+=1; return _sid[0]
def pic(rid,x,y,cx,cy,name="img"):
    return (f'<p:pic><p:nvPicPr><p:cNvPr id="{nid()}" name="{name}"/>'
            f'<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
            f'<p:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>'
            f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>')
def para(runs,bullet=False,space_after=500,align='l'):
    bu=('<a:buFont typeface="Arial"/><a:buChar char="&#8226;"/>' if bullet else '<a:buNone/>')
    ind=' indent="-228600" marL="274320"' if bullet else ''
    rx=''
    for txt,sz,color,b in runs:
        rx+=(f'<a:r><a:rPr lang="en-US" sz="{sz}" b="{1 if b else 0}" dirty="0">'
             f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
             f'<a:latin typeface="Calibri"/></a:rPr><a:t>{esc(txt)}</a:t></a:r>')
    return f'<a:p><a:pPr algn="{align}"{ind}><a:spcAft><a:spcPts val="{space_after}"/></a:spcAft>{bu}</a:pPr>{rx}</a:p>'
def textbox(x,y,cx,cy,paras,name="tx",fill=None,anchor='t'):
    sf=f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>' if fill else '<a:noFill/>'
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{nid()}" name="{name}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>{sf}</p:spPr>'
            f'<p:txBody><a:bodyPr wrap="square" lIns="91440" tIns="45720" rIns="91440" bIns="45720" anchor="{anchor}"><a:normAutofit/></a:bodyPr>'
            f'<a:lstStyle/>{"".join(paras)}</p:txBody></p:sp>')
def slide_xml(shapes,bg='FFFFFF'):
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<p:sld xmlns:a="{A}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            f'<p:cSld><p:bg><p:bgPr><a:solidFill><a:srgbClr val="{bg}"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>'
            '<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
            '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
            f'{"".join(shapes)}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>')
def title_bar(text):
    return [textbox(0,0,SW,IN(0.95),[para([(text,2500,'FFFFFF',True)])],fill=NAVY,anchor='ctr')]

# ================= SLIDE 1 =================
s1=[textbox(0,0,SW,IN(1.6),[para([('Does CFTC positioning predict WTI returns?',2400,'FFFFFF',True)])],fill=NAVY,anchor='ctr')]
s1+=[textbox(IN(0.6),IN(1.85),IN(12.1),IN(1.0),
     [para([('The level does not time direction. The 4-week ',2150,DARK,True),
            ('change',2150,GREEN,True),(' does, and crowding flags ',2150,DARK,True),('risk',2150,RED,True),('.',2150,DARK,True)])])]
s1+=[textbox(IN(0.6),IN(2.95),IN(12.1),IN(3.7),[
    para([('The level of Other Reportables net carries almost no directional information. Its correlation with next week’s return is +0.02 (p=0.75), and extreme readings do not beat the base rate.',1450,DARK,False)],bullet=True),
    para([('The rate of change is the real story. When positioning capitulates (the fastest 4-week unwind), WTI rebounds about 5.6% over the next month, with a 72% hit rate (bootstrap p=0.04).',1450,DARK,False)],bullet=True),
    para([('Crowded longs come with more risk than reward: forward volatility roughly doubles after an extreme long reading (10.6% to 21.4% in this sample).',1450,DARK,False)],bullet=True),
    para([('Worth flagging up front: the supplied series is CFTC Other Reportables, not Managed Money. We verified that against CFTC and labelled the deck accordingly.',1450,RED,True)],bullet=True),
])]
s1+=[textbox(IN(0.6),IN(6.75),IN(12.1),IN(0.5),
     [para([('CFTC Disaggregated futures-only WTI. Roll-adjusted front-month NYMEX CL. 2021 to 2026, 282 weekly observations.',1050,GREY,False)])])]

# ================= SLIDE 2 =================
s2=title_bar('How we tested it, and how we avoided fooling ourselves')
s2+=[textbox(IN(0.6),IN(1.15),IN(12.1),IN(5.95),[
    para([('Signal. ',1450,NAVY,True),('CFTC Disaggregated, futures-only, WTI Other Reportables net. We confirmed the identity by matching the file to CFTC’s published numbers on five dates. It is not Managed Money, even though the brief was framed that way.',1450,DARK,False)],bullet=True),
    para([('Price. ',1450,NAVY,True),('Roll-adjusted continuous front-month WTI (NYMEX CL), built from local one-minute data with 65 clean monthly rolls. The window is 2021 to 2026 because local WTI starts in 2021, and we used true WTI rather than a Brent stand-in.',1450,DARK,False)],bullet=True),
    para([('No look-ahead. ',1450,NAVY,True),('Every forward return starts from the first WTI close on or after the Friday release date, never the Tuesday as-of date. CFTC publishes about three days late.',1450,DARK,False)],bullet=True),
    para([('Extremes and flow. ',1450,NAVY,True),('A 52-week rolling z-score (no full-sample leakage), flagged at |Z| of 2 or more, with long and short kept separate. We also tested the 4-week change in positioning, because the level and the flow can say different things.',1450,DARK,False)],bullet=True),
    para([('Significance. ',1450,NAVY,True),('Conditional returns are compared with the unconditional base rate, using Newey-West (HAC) standard errors for overlapping windows and 5,000-draw block-bootstrap p-values.',1450,DARK,False)],bullet=True),
    para([('Limitation. ',1450,NAVY,True),('Open interest is not in the local file, so signals use the net level rather than a share of open interest.',1450,DARK,False)],bullet=True),
])]

# ================= SLIDE 3 (LEVEL) =================
s3=title_bar('The positioning level tracks price but does not forecast it')
x,y,cx,cy=fit(os.path.join(CH,'chart1_position_vs_wti.png'),IN(0.25),IN(1.0),IN(6.45),IN(4.55))
s3+=[pic('rId2',x,y,cx,cy,'chart1')]
x,y,cx,cy=fit(os.path.join(CH,'chart2_forward_returns.png'),IN(6.85),IN(1.0),IN(6.25),IN(4.55))
s3+=[pic('rId3',x,y,cx,cy,'chart2')]
s3+=[textbox(IN(0.5),IN(5.65),IN(12.4),IN(1.5),[
    para([('The contemporaneous correlation between the level and price is weak in this window (-0.09), and on a forward basis the level is essentially noise.',1300,DARK,True)],bullet=True),
    para([('Extreme longs show no upside (the positive means are driven by a few outliers, the medians are negative). Extreme shorts did bounce over 2021 to 2026, strongest at two weeks (+2.9% above the base rate), but that one cell does not survive a multiple-comparison correction and rests on just 10 episodes.',1250,GREY,False)],bullet=True),
])]

# ================= SLIDE 4 (CHANGE & RISK) =================
s4=title_bar('Where the signal actually lives: the change, and the risk')
x,y,cx,cy=fit(os.path.join(CH,'chart5_flow_capitulation.png'),IN(0.3),IN(1.05),IN(7.35),IN(5.8))
s4+=[pic('rId2',x,y,cx,cy,'chart5')]
s4+=[textbox(IN(7.8),IN(1.2),IN(5.3),IN(5.7),[
    para([('The flow beats the level.',1550,GREEN,True)]),
    para([('After the fastest 4-week unwind (capitulation), WTI rebounds about +5.6% over the next month: 72% hit, bootstrap p=0.04, HAC t=2.0. The 1-week move is also significant (+2.2%, p=0.01).',1400,DARK,False)],bullet=True),
    para([('This is the one robust directional signal in the data, and it matches the same result on the full 2016 to 2026 sample.',1400,DARK,False)],bullet=True),
    para([('Crowding is a risk gauge.',1550,RED,True)]),
    para([('After an extreme long, forward 4-week volatility roughly doubles (10.6% to 21.4%) and the odds of a 10%-plus drawdown rise. The direction is clear; our short window is too small to certify it, but the full-sample version of this test is highly significant.',1400,DARK,False)],bullet=True),
])]

# ================= SLIDE 5 (CONCLUSION) =================
s5=title_bar('Conclusion and desk use')
x,y,cx,cy=fit(os.path.join(CH,'chart4_decay_probe.png'),IN(7.0),IN(1.35),IN(6.1),IN(4.5))
s5+=[pic('rId2',x,y,cx,cy,'chart4')]
s5+=[textbox(IN(0.5),IN(1.1),IN(6.35),IN(5.95),[
    para([('Treat positioning as context, not a trigger. ',1450,NAVY,True),('The level will not give you direction. The change and the crowding will tell you about inflections and risk.',1450,DARK,False)],bullet=True),
    para([('Is it tradeable? ',1450,NAVY,True),('The capitulation rebound and the short-side bounce both happen mostly after the Friday release (about 70% of the move), so they are at least actionable. Costs are not modelled.',1450,DARK,False)],bullet=True),
    para([('Two practical uses: ',1450,NAVY,True),('trim size or hedge tails when positioning is crowded, and treat a fast unwind as a contrarian inflection flag alongside the fundamentals.',1450,DARK,False)],bullet=True),
    para([('Caveats: ',1450,NAVY,True),('this is Other Reportables, not Managed Money; the window is 2021 to 2026 only; episode counts are small; the April-2020 extreme sits before our window.',1450,DARK,False)],bullet=True),
    para([('To extend: ',1450,NAVY,True),('rebuild with true WTI back to 2016 to recover the 2018 and 2020 episodes, and add open interest for share-of-OI signals.',1450,DARK,False)],bullet=True),
])]

slides=[slide_xml(s1),slide_xml(s2),slide_xml(s3),slide_xml(s4),slide_xml(s5)]
slide_imgs={1:[],2:[],3:[('rId2','image1.png'),('rId3','image2.png')],4:[('rId2','image3.png')],5:[('rId2','image4.png')]}
media={'image1.png':'chart1_position_vs_wti.png','image2.png':'chart2_forward_returns.png',
       'image3.png':'chart5_flow_capitulation.png','image4.png':'chart4_decay_probe.png'}

THEME=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
 f'<a:theme xmlns:a="{A}" name="Office Theme"><a:themeElements>'
 '<a:clrScheme name="Office"><a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>'
 '<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>'
 '<a:dk2><a:srgbClr val="1F3B57"/></a:dk2><a:lt2><a:srgbClr val="EEECE1"/></a:lt2>'
 '<a:accent1><a:srgbClr val="1F3B57"/></a:accent1><a:accent2><a:srgbClr val="C0392B"/></a:accent2>'
 '<a:accent3><a:srgbClr val="1E8449"/></a:accent3><a:accent4><a:srgbClr val="B9770E"/></a:accent4>'
 '<a:accent5><a:srgbClr val="5D6D7E"/></a:accent5><a:accent6><a:srgbClr val="8E44AD"/></a:accent6>'
 '<a:hlink><a:srgbClr val="0563C1"/></a:hlink><a:folHlink><a:srgbClr val="954F72"/></a:folHlink></a:clrScheme>'
 '<a:fontScheme name="Office"><a:majorFont><a:latin typeface="Calibri Light"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>'
 '<a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme>'
 '<a:fmtScheme name="Office">'
 '<a:fillStyleLst><a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
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
 f'<p:sldMaster xmlns:a="{A}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
 'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
 '<p:cSld><p:bg><p:bgPr><a:solidFill><a:schemeClr val="bg1"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>'
 '<p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
 '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
 '</p:spTree></p:cSld>'
 '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" '
 'accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
 '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
 '<p:txStyles>'
 '<p:titleStyle><a:lvl1pPr><a:defRPr sz="4400"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill><a:latin typeface="+mj-lt"/></a:defRPr></a:lvl1pPr></p:titleStyle>'
 '<p:bodyStyle><a:lvl1pPr><a:defRPr sz="1800"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill><a:latin typeface="+mn-lt"/></a:defRPr></a:lvl1pPr></p:bodyStyle>'
 '<p:otherStyle><a:lvl1pPr><a:defRPr sz="1800"><a:solidFill><a:schemeClr val="tx1"/></a:solidFill></a:defRPr></a:lvl1pPr></p:otherStyle>'
 '</p:txStyles></p:sldMaster>')

LAYOUT=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
 f'<p:sldLayout xmlns:a="{A}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
 'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" type="blank" preserve="1">'
 '<p:cSld name="Blank"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
 '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
 '</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>')

PRES=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
 f'<p:presentation xmlns:a="{A}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
 'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" saveSubsetFonts="1">'
 '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
 '<p:sldIdLst>' + ''.join(f'<p:sldId id="{256+i}" r:id="rId{2+i}"/>' for i in range(5)) + '</p:sldIdLst>'
 f'<p:sldSz cx="{SW}" cy="{SH}" type="screen16x9"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>')

CT=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
 '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
 '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
 '<Default Extension="xml" ContentType="application/xml"/>'
 '<Default Extension="png" ContentType="image/png"/>'
 '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
 '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
 '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
 '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
 + ''.join(f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>' for i in range(1,6)) +
 '</Types>')
RELS_ROOT=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/></Relationships>')
PRES_RELS=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>'
 + ''.join(f'<Relationship Id="rId{2+i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{1+i}.xml"/>' for i in range(5)) +
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
    for rid,fn in imgs:
        r+=f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/{fn}"/>'
    return r+'</Relationships>'

with zipfile.ZipFile(PPTX,'w',zipfile.ZIP_DEFLATED) as z:
    z.writestr('[Content_Types].xml',CT); z.writestr('_rels/.rels',RELS_ROOT)
    z.writestr('ppt/presentation.xml',PRES); z.writestr('ppt/_rels/presentation.xml.rels',PRES_RELS)
    z.writestr('ppt/theme/theme1.xml',THEME)
    z.writestr('ppt/slideMasters/slideMaster1.xml',MASTER); z.writestr('ppt/slideMasters/_rels/slideMaster1.xml.rels',MASTER_RELS)
    z.writestr('ppt/slideLayouts/slideLayout1.xml',LAYOUT); z.writestr('ppt/slideLayouts/_rels/slideLayout1.xml.rels',LAYOUT_RELS)
    for i,sx in enumerate(slides,1):
        z.writestr(f'ppt/slides/slide{i}.xml',sx); z.writestr(f'ppt/slides/_rels/slide{i}.xml.rels',slide_rels(slide_imgs[i]))
    for fn,src in media.items(): z.write(os.path.join(CH,src), f'ppt/media/{fn}')
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
