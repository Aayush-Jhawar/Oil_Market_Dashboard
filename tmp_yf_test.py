import yfinance as yf
symbols = ["CL=F","BZ=F","RB=F","HO=F","AEX=F","B0=F","NG=F","QCL=F","DX-Y.NYB","^GSPC","^TNX","^VIX","GC=F","USO","UNG"]
for sym in symbols:
    try:
        t = yf.Ticker(sym)
        info = t.info
        print(sym, "price=", info.get("regularMarketPrice"), "hasInfo=", bool(info), "keys=", list(info.keys())[:10])
    except Exception as e:
        print(sym, "ERROR", e)
