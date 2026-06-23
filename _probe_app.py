import httpx, json
BASE = "https://yourgrimreaper-energy-dashboard.hf.space"
try:
    r = httpx.get(BASE + "/api/prices/all", timeout=20)
    d = r.json().get("data", {})
    for s in ("WTI", "Brent"):
        if s in d:
            print(f"{s}: close={d[s].get('close')} chg%={round(d[s].get('change_pct',0),3)}")
    r2 = httpx.get(BASE + "/api/analytics/forward-curve?symbol=WTI", timeout=20)
    c = r2.json().get("data", {})
    print(f"WTI curve: shape={c.get('curve_shape')} m1_m12={c.get('m1_m12_spread')} src={c.get('data_source')} pts={len(c.get('forward_curve',[]))}")
except Exception as e:
    print("probe error:", e)
