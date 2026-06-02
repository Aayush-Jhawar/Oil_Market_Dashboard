import json
import re
import requests

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Referer': 'https://finance.yahoo.com/',
}
url = 'https://finance.yahoo.com/quote/CL=F'
text = requests.get(url, headers=headers, timeout=20).text
print('len', len(text))
print(repr(text[:300]))
for marker in ['"symbol":"CL=F"', '"headSymbolAsString":"CL=F"', 'CL=F', '\\"symbol\\":"CL=F\\"', 'symbol":"CL=F', 'headSymbolAsString":"CL=F']:
    print('marker', marker, 'count', text.count(marker))

for pat in ['root.App.main', 'root.App', 'window.__', 'QuoteSummaryStore', 'context', 'application/json', 'id="feature"', 'data-store', 'initialState', '__INITIAL_STATE__']:
    print(pat, 'count', text.count(pat))

idx = text.find('window.__')
print('window.__ idx', idx)
if idx != -1:
    print(text[idx-200:idx+200])
    idxb = text.find('window.__', idx + 1)
    print('second window.__ idx', idxb)
    if idxb != -1:
        print(text[idxb-200:idxb+200])
idx2 = text.find('App.main')
print('App.main idx', idx2)
idx3 = text.find('"regularMarketPrice"')
print('first regularMarketPrice idx', idx3)
if idx3 != -1:
    print(text[idx3-400:idx3+400])

print('=== script tags ===')
script_positions = [m.start() for m in re.finditer(r'<script', text)][:20]
for i, pos in enumerate(script_positions):
    end = text.find('</script>', pos)
    snippet = text[pos:end if end != -1 else pos+200]
    print('script', i, 'pos', pos, 'len', len(snippet))
    print(snippet[:200])
    print('---')

idx_cl = text.find('Crude Oil Jul 26')
print('Crude Oil Jul 26 idx', idx_cl)
if idx_cl != -1:
    print(text[idx_cl-200:idx_cl+400])

idx_header = text.find('quote-header-info')
print('quote-header-info idx', idx_header)
if idx_header != -1:
    print(text[idx_header-200:idx_header+600])

for needle in ['"symbol":"CL=F"', '"shortName":"Crude Oil Jul 26"', '"regularMarketPrice"', '"chart":{"result"', '"quoteResponse"']:
    idx = text.find(needle)
    print(f'needle {needle}', 'idx', idx)
    if idx != -1:
        print(text[idx-200:idx+800])
        print('---')

indices = [pos for pos in range(len(text)) if text.startswith('CL=F', pos)]
print('total indices', len(indices))
for i, idx in enumerate(indices[:5]):
    print('first occurrence', i, idx)
    print(text[idx - 100:idx + 200])
    print('---')
for i, idx in enumerate(indices[-5:], start=max(0, len(indices)-5)):
    print('last occurrence', i, idx)
    print(text[idx - 100:idx + 200])
    print('---')
