import re

endpoints_to_restore = [
    '/api/analytics/indicators',
    '/api/spreads/all',
    '/api/spreads/{spread_name}',
    '/api/alerts/active',
    '/api/alerts/{alert_id}/acknowledge'
]

with open('backend/legacy_archive/dead_endpoints.py', 'r', encoding='utf-8') as f:
    code = f.read()

pattern = re.compile(r'^@app\.(get|post|put|delete|websocket)\([\'"]([^\'"]+)[\'"].*?^(?=@app|# ====================|if __name__|$)', re.MULTILINE | re.DOTALL)

restored_code = "\n"
new_dead_code = code

for match in pattern.finditer(code):
    full_block = match.group(0)
    path = match.group(2)
    
    if path in endpoints_to_restore:
        restored_code += full_block + "\n\n"
        new_dead_code = new_dead_code.replace(full_block, "")

with open('backend/main.py', 'a', encoding='utf-8') as f:
    f.write(restored_code)

with open('backend/legacy_archive/dead_endpoints.py', 'w', encoding='utf-8') as f:
    f.write(new_dead_code)

print(f"Restored {len(restored_code.split('@app.')) - 1} endpoints back to main.py")
