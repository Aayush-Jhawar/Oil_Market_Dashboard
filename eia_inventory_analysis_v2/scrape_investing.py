"""
================================================================================
  INVESTING.COM PETROLEUM CALENDAR SCRAPER  (v2)
================================================================================
Pulls the weekly US petroleum events with ACTUAL / CONSENSUS(forecast) / PREVIOUS
from investing.com's economic-calendar AJAX service.  This is the only piece that
gives us the EXPECTATION baseline (analyst consensus) and the API (American
Petroleum Institute) early estimate alongside the EIA actuals.

Anti-block approach (the homepage is Cloudflare-protected, but the AJAX service
responds to a plain XHR):
  * realistic browser User-Agent + Referer + X-Requested-With
  * request the JSON service endpoint directly (not the HTML pages)
  * chunked date windows (smaller, calendar-like queries)
  * jittered polite delays + exponential backoff retries
Be a good citizen: this runs a few dozen requests, slowly.

Output: data/investing_petroleum_raw.csv (long) + data/investing_petroleum_wide.csv
"""
import os
import re
import time
import random
import csv
import requests
from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)

URL = "https://www.investing.com/economic-calendar/Service/getCalendarFilteredData"
UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]

# events we care about (regex -> canonical label)
WANT = [
    (r"^API Weekly Crude Oil Stock", "API_Crude"),
    (r"^Crude Oil Inventories", "EIA_Crude"),
    (r"^Cushing Crude Oil Inventories", "EIA_Cushing"),
    (r"^EIA Weekly Distillates Stocks|^Distillate Fuel Inventories", "EIA_Distillate"),
    (r"^Gasoline Inventories", "EIA_Gasoline"),
    (r"^EIA Weekly Refinery Utilization Rates", "EIA_RefineryUtil"),
    (r"^EIA Refinery Crude Runs", "EIA_RefineryRuns"),
    (r"^Crude Oil Imports", "EIA_Imports"),
    (r"^Gasoline Production", "EIA_GasolineProd"),
    (r"^Distillate Fuel Production", "EIA_DistillateProd"),
    (r"Crude Oil Production", "EIA_CrudeProd"),
]


def _session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(UAS),
        "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.investing.com/economic-calendar/",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://www.investing.com",
    })
    return s


def _num(txt):
    """'-7.418M'->-7.418 ; '0.2%'->0.2 ; '163.7K'->163.7 ; ''->None (units kept separate)."""
    if not txt or txt.strip() in ("", "&nbsp;", "\xa0"):
        return None
    t = txt.replace(",", "").replace("%", "").strip()
    m = re.match(r"^(-?\d+\.?\d*)\s*([MKB%]?)", t)
    if not m:
        return None
    return float(m.group(1))


def _unit(txt):
    if txt and "%" in txt:
        return "%"
    if txt and txt.strip().endswith("M"):
        return "M"
    if txt and txt.strip().endswith("K"):
        return "K"
    return ""


def fetch_window(s, date_from, date_to, tries=6):
    data = {"country[]": "5", "timeZone": "8", "timeFilter": "timeRemain",
            "currentTab": "custom", "dateFrom": date_from, "dateTo": date_to,
            "limit_from": "0"}
    for attempt in range(tries):
        try:
            s.headers["User-Agent"] = random.choice(UAS)
            r = s.post(URL, data=data, timeout=25)
            if r.status_code == 200:
                try:
                    return r.json().get("data", "")
                except Exception:
                    return r.text
            if r.status_code == 429:
                cool = 60 * (attempt + 1) + random.uniform(0, 20)   # hard cooldown
                print(f"    HTTP 429 on {date_from}..{date_to} -> cooldown {cool:.0f}s")
                time.sleep(cool)
                continue
            print(f"    HTTP {r.status_code} on {date_from}..{date_to} (try {attempt+1})")
        except Exception as e:
            print(f"    error {str(e)[:60]} (try {attempt+1})")
        time.sleep((2 ** attempt) + random.uniform(0.5, 2.0))   # backoff
    return None


def parse(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for tr in soup.select("tr[id^=eventRowId_]"):
        ev = tr.select_one("td.event")
        if not ev:
            continue
        name = ev.get_text(" ", strip=True)
        label = next((lab for pat, lab in WANT if re.search(pat, name, re.I)), None)
        if not label:
            continue
        dt = tr.get("data-event-datetime", "")

        def cell(pre):
            el = tr.find("td", id=re.compile("^" + pre))
            return el.get_text(strip=True) if el else ""
        a, f, p = cell("eventActual_"), cell("eventForecast_"), cell("eventPrevious_")
        rows.append({"datetime": dt, "event": name, "label": label,
                     "actual": _num(a), "consensus": _num(f), "previous": _num(p),
                     "unit": _unit(a) or _unit(p)})
    return rows


def daterange_chunks(start, end, days=60):
    import datetime as dt
    s = dt.date.fromisoformat(start); e = dt.date.fromisoformat(end)
    cur = s
    while cur <= e:
        nxt = min(cur + dt.timedelta(days=days - 1), e)
        yield cur.isoformat(), nxt.isoformat()
        cur = nxt + dt.timedelta(days=1)


def main(start="2021-01-01", end="2026-06-30"):
    print("=" * 64)
    print("  SCRAPING INVESTING.COM PETROLEUM CALENDAR")
    print(f"  range {start} .. {end}")
    print("=" * 64)
    s = _session()
    all_rows = []
    raw_path = os.path.join(DATA, "investing_petroleum_raw.csv")
    # 12-day windows fit in a single (un-paginated) page; smaller = complete data
    chunks = list(daterange_chunks(start, end, days=12))

    def save(rows):
        seen, dedup = set(), []
        for r in sorted(rows, key=lambda x: x["datetime"]):
            k = (r["datetime"], r["label"])
            if k in seen:
                continue
            seen.add(k); dedup.append(r)
        with open(raw_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["datetime", "event", "label", "actual",
                                              "consensus", "previous", "unit"])
            w.writeheader(); w.writerows(dedup)
        return dedup

    for i, (a, b) in enumerate(chunks, 1):
        html = fetch_window(s, a, b)
        n = 0
        if html:
            rows = parse(html)
            all_rows.extend(rows)
            n = len(rows)
        print(f"  [{i:3d}/{len(chunks)}] {a}..{b}: {n} petroleum events", flush=True)
        if i % 10 == 0:
            save(all_rows)   # incremental checkpoint
        time.sleep(random.uniform(7.0, 12.0))   # polite jittered delay

    dedup = save(all_rows)
    print(f"\n  saved {len(dedup)} events -> {raw_path}")

    # coverage summary
    from collections import Counter
    c = Counter(r["label"] for r in dedup)
    have_actual = Counter(r["label"] for r in dedup if r["actual"] is not None)
    have_cons = Counter(r["label"] for r in dedup if r["consensus"] is not None)
    print("\n  label                 events  w/actual  w/consensus")
    for lab in sorted(c):
        print(f"  {lab:20s}  {c[lab]:6d}  {have_actual[lab]:8d}  {have_cons[lab]:11d}")
    dates = sorted(r["datetime"][:10] for r in dedup if r["actual"] is not None and r["datetime"])
    if dates:
        print(f"\n  actual-data span: {dates[0]} .. {dates[-1]}")
    return dedup


if __name__ == "__main__":
    main()
