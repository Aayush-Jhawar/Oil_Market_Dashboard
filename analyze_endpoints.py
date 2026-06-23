import os
import re

backend_endpoints = []
frontend_api_calls = []

# Scan backend for endpoints
for root, dirs, files in os.walk('backend'):
    for file in files:
        if file.endswith('.py'):
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    matches = re.findall(r'@(?:app|router)\.(get|post|put|delete|websocket)\(([\'"])([^\'"]+)\2', content)
                    for match in matches:
                        backend_endpoints.append({
                            'method': match[0].upper(),
                            'path': match[2],
                            'file': file
                        })
            except Exception:
                pass

# Scan frontend for API calls
for root, dirs, files in os.walk('frontend/src'):
    for file in files:
        if file.endswith(('.ts', '.tsx', '.js', '.jsx')):
            path = os.path.join(root, file)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    matches = re.findall(r'(?:api|axios)\.(get|post|put|delete)\(([\'"`])(.*?)\2', content)
                    for match in matches:
                        frontend_api_calls.append({
                            'method': match[0].upper(),
                            'path': match[2],
                            'file': file
                        })
            except Exception:
                pass

print("--- BACKEND ENDPOINTS ---")
backend_paths = {e['path'] for e in backend_endpoints}
for p in sorted(list(backend_paths)):
    print(p)

print("\n--- FRONTEND API CALLS ---")
frontend_paths = {e['path'] for e in frontend_api_calls}
for p in sorted(list(frontend_paths)):
    print(p)

print("\n--- DEAD ENDPOINTS (In backend, not called by frontend) ---")
# Basic matching (ignoring path params like {symbol} for now, just rough)
def clean_path(p):
    return re.sub(r'\{[^}]+\}', '*', p).replace('${API_BASE}', '').replace('${API_URL}', '').replace('${', '*')

clean_frontend = {clean_path(p) for p in frontend_paths}
for bp in sorted(list(backend_paths)):
    cbp = clean_path(bp)
    # Check if any frontend path matches the backend path pattern
    matched = False
    for cfp in clean_frontend:
        # turn backend pattern /api/prices/* into regex
        regex = '^' + cbp.replace('*', '.*') + '$'
        try:
            if re.match(regex, cfp):
                matched = True
                break
        except:
            pass
    if not matched:
        print(bp)
