import ast
import re
import shutil

# The endpoints we want to KEEP in main.py
keep_endpoints = {
    '/ws', '/ws/prices', '/ws/signals',
    '/api/paper/state', '/api/paper/trade', '/api/paper/close/{symbol}',
    '/api/prediction/trades/all', '/api/prediction/forecast', '/api/prediction/regime',
    '/api/signals/composite', '/api/signals/enhanced',
    '/api/analytics/correlations', '/api/analytics/forward-curve', '/api/v1/risk/portfolio',
    '/api/backtest/journal', '/api/backtest/run', '/api/backtest/strategies',
    '/api/news/enhanced', '/api/macro/all',
    '/api/prices/all', '/api/prices/{symbol}/historical',
    '/api/eia/weekly', '/api/eia/weekly-anchor', '/api/cftc/latest', '/api/rigs/latest',
    '/api/storms/active', '/api/tankers/positions'
}

with open('backend/main.py', 'r', encoding='utf-8') as f:
    code = f.read()

# We will just do a simple regex block extractor for dead endpoints to be perfectly safe
# Let's find all `@app.get`, `@app.post` etc
pattern = re.compile(r'^@app\.(get|post|put|delete|websocket)\([\'"]([^\'"]+)[\'"].*?^(?=@app|# ====================|if __name__)', re.MULTILINE | re.DOTALL)

legacy_code = ""
new_code = code

for match in pattern.finditer(code):
    full_block = match.group(0)
    path = match.group(2)
    
    # If path is NOT in the keep list, we extract it and remove from main.py
    if path not in keep_endpoints:
        legacy_code += full_block + "\n\n"
        new_code = new_code.replace(full_block, "")

with open('backend/legacy_archive/dead_endpoints.py', 'w', encoding='utf-8') as f:
    f.write(legacy_code)

with open('backend/main.py', 'w', encoding='utf-8') as f:
    f.write(new_code)

print(f"Extracted {len(legacy_code.split('@app.')) - 1} endpoints to legacy_archive.")
